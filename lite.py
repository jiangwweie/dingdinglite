"""盯盘狗 Lite 版主入口 - Pinbar 信号监控"""
import asyncio
import logging
import os
import time
import datetime
import pytz
from decimal import Decimal
from typing import Any, Dict, Optional

import ccxt.async_support as ccxt
import yaml

from models import KlineData, LiteConfig, SignalResult, Trend
from notifier import send_feishu_notification
from strategy import check_pinbar_signal

# =============================================================================
# 常量定义
# =============================================================================

CONFIG_FILE = "config.yaml"
LOG_FILE = "logs/lite.log"
LOG_FORMAT = "%(asctime)s %(levelname)s  %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# 周期映射（写死）
HIGHER_TIMEFRAME_MAP = {
    "15m": "1h",
    "1h": "4h",
    "4h": "1d"
}

# 冷却时间（2 分钟）
COOLDOWN_SECONDS = 120

# 版本
VERSION = "v0.1.0"

# 全局计数器
klines_checked = 0
signals_found = 0
last_status_time = 0


# =============================================================================
# 日志系统
# =============================================================================

def setup_logging() -> logging.Logger:
    """配置日志系统

    Returns:
        配置好的 logger
    """
    # 创建 logs/ 目录
    log_dir = os.path.dirname(LOG_FILE)
    if log_dir and not os.path.exists(log_dir):
        os.makedirs(log_dir, exist_ok=True)

    # 配置日志
    logger = logging.getLogger("dingpang-lite")
    logger.setLevel(logging.DEBUG)  # 允许 DEBUG 日志通过

    # 清空已有处理器
    logger.handlers.clear()

    # 文件处理器 - 记录 DEBUG 级别 (使用北京时间)
    file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(LOG_FORMAT, DATE_FORMAT))
    # 使用北京时间 (UTC+8)
    beijing_tz = pytz.timezone("Asia/Shanghai")
    def beijing_converter(*args):
        import datetime
        return beijing_tz.localize(datetime.datetime(*args[:6])).timetuple()
    file_handler.converter = beijing_converter
    logger.addHandler(file_handler)

    # 终端处理器 - 显示 DEBUG 级别 (使用北京时间)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.DEBUG)
    console_handler.setFormatter(logging.Formatter(LOG_FORMAT, DATE_FORMAT))
    console_handler.converter = beijing_converter
    logger.addHandler(console_handler)

    return logger


# =============================================================================
# 配置加载
# =============================================================================

def load_config(config_path: str) -> LiteConfig:
    """从 YAML 文件加载配置

    Args:
        config_path: 配置文件路径

    Returns:
        验证后的配置对象

    Raises:
        FileNotFoundError: 配置文件不存在
        yaml.YAMLError: YAML 解析失败
        ValueError: 配置验证失败
    """
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"配置文件不存在：{config_path}")

    with open(config_path, "r", encoding="utf-8") as f:
        config_data = yaml.safe_load(f)

    return LiteConfig.model_validate(config_data)


# =============================================================================
# 交易所网关
# =============================================================================

class ExchangeGateway:
    """交易所网关 - 封装 ccxt 交易所操作"""

    def __init__(self, config: Any) -> None:
        """初始化交易所网关

        Args:
            config: ExchangeConfig 配置对象
        """
        self.config = config
        self.exchange: Optional[ccxt.binance] = None
        self.logger = logging.getLogger("dingpang-lite")

    async def connect(self) -> None:
        """初始化 ccxt.binance 交易所"""
        self.exchange = ccxt.binance({
            "apiKey": self.config.api_key,
            "secret": self.config.api_secret,
            "enableRateLimit": True,
            "options": {
                "defaultType": "future",  # 合约交易
                "test": self.config.testnet
            }
        })

        # 加载市场数据
        await self.exchange.load_markets()

    async def get_ema(self, symbol: str, timeframe: str, period: int) -> Decimal:
        """获取 EMA 值（指数移动平均线）

        Args:
            symbol: 交易对，如 "BTC/USDT:USDT"
            timeframe: 周期，如 "1h"
            period: EMA 周期

        Returns:
            EMA 值
        """
        if self.exchange is None:
            raise RuntimeError("交易所未连接，请先调用 connect()")

        # 获取 K 线数据（需要 period 根来计算 EMA）
        ohlcv = await self.exchange.fetch_ohlcv(symbol, timeframe, limit=period)

        if len(ohlcv) < period:
            raise ValueError(f"K 线数据不足：需要{period}根，实际{len(ohlcv)}根")

        # 提取收盘价
        close_prices = [Decimal(str(candle[4])) for candle in ohlcv]

        # 计算 EMA：EMA = 价格 (t) * k + EMA(t-1) * (1-k)
        # k = 2 / (period + 1)
        k = Decimal("2") / Decimal(str(period + 1))

        # 第一个 EMA 用 SMA 近似
        ema = sum(close_prices[:period]) / Decimal(str(period))

        # 迭代计算后续 EMA
        for price in close_prices[period:]:
            ema = price * k + ema * (Decimal("1") - k)

        return ema

    async def get_klines(self, symbol: str, timeframe: str, limit: int = 1) -> list:
        """获取 K 线数据

        Args:
            symbol: 交易对
            timeframe: 周期
            limit: 获取数量

        Returns:
            K 线数据列表
        """
        if self.exchange is None:
            raise RuntimeError("交易所未连接")

        return await self.exchange.fetch_ohlcv(symbol, timeframe, limit=limit)

    async def subscribe_klines(
        self,
        symbols: list,
        timeframes: list,
        callback
    ) -> None:
        """订阅 K 线数据（同步轮询模式）

        在每个周期的 K 线闭合时刻读取并验证，确保只处理已闭合 K 线。

        Args:
            symbols: 交易对列表
            timeframes: 周期列表
            callback: K 线数据回调函数，接收 KlineData 参数
        """
        from scheduler import is_kline_close_time, is_kline_closed
        import datetime

        self.logger.info("同步轮询调度器启动")
        loop_count = 0

        while True:
            triggered = False
            loop_count += 1

            # 每 30 秒输出一次心跳
            if loop_count % 30 == 0:
                now_str = datetime.datetime.now().strftime("%H:%M:%S")
                self.logger.info(f"♥ 心跳 [{now_str}] 检查 {klines_checked} 根 K 线，发现 {signals_found} 个信号")

            # 检查每个周期是否到达闭合时刻
            for symbol in symbols:
                for timeframe in timeframes:
                    if is_kline_close_time(timeframe):
                        try:
                            # 读取最近 2 根 K 线，使用前一根（确保已闭合）
                            ohlcv = await self.get_klines(symbol, timeframe, limit=2)

                            if len(ohlcv) < 2:
                                self.logger.debug(f"[{symbol}] {timeframe} K 线数据不足，跳过")
                                continue

                            # 使用倒数第二根 K 线（确保已闭合）
                            candle = ohlcv[-2]
                            kline_timestamp = int(candle[0])

                            # 验证闭合
                            if not is_kline_closed(kline_timestamp, timeframe):
                                self.logger.debug(
                                    f"[{symbol}] {timeframe} K 线未闭合，跳过"
                                )
                                continue

                            # 构建 KlineData
                            kline = KlineData(
                                symbol=symbol,
                                timeframe=timeframe,
                                timestamp=kline_timestamp,
                                open=Decimal(str(candle[1])),
                                high=Decimal(str(candle[2])),
                                low=Decimal(str(candle[3])),
                                close=Decimal(str(candle[4])),
                                volume=Decimal(str(candle[5])),
                                is_closed=True
                            )

                            self.logger.debug(
                                f"[{symbol}] {timeframe} K 线闭合 O={float(candle[1]):.2f} "
                                f"H={float(candle[2]):.2f} L={float(candle[3]):.2f} C={float(candle[4]):.2f}"
                            )

                            await callback(kline)
                            triggered = True

                        except Exception as e:
                            logging.getLogger("dingpang-lite").error(
                                f"获取 {symbol} {timeframe} K 线失败：{e}"
                            )

            # 如果没有触发任何周期，等待 1 秒
            if not triggered:
                await asyncio.sleep(1)

    async def close(self) -> None:
        """关闭连接"""
        if self.exchange:
            await self.exchange.close()


# =============================================================================
# 信号处理管道
# =============================================================================

class SignalPipeline:
    """信号处理管道 - 处理 K 线数据并检测信号"""

    def __init__(self, config: LiteConfig) -> None:
        """初始化信号管道

        Args:
            config: 完整配置对象
        """
        self.config = config
        self.gateway: Optional[ExchangeGateway] = None
        self.logger = logging.getLogger("dingpang-lite")

        # 上下文缓存：symbol -> timeframe -> data
        self.context_cache: Dict[str, Dict[str, Dict[str, Any]]] = {}

        # 冷却缓存：(symbol, timeframe) -> last_signal_time
        self.cooldown_cache: Dict[tuple, float] = {}

    def set_gateway(self, gateway: ExchangeGateway) -> None:
        """设置交易所网关

        Args:
            gateway: 交易所网关实例
        """
        self.gateway = gateway

    async def initialize_context(self) -> None:
        """启动时预加载历史 K 线数据，建立 EMA 上下文

        为每个币种和更高周期（1h/4h）预加载 60 根 K 线并计算 EMA
        """
        self.logger.info("=" * 60)
        self.logger.info("开始预加载历史 K 线数据...")
        self.logger.info("=" * 60)

        # 需要预加载的更高周期（用于 EMA 趋势判断）
        higher_timeframes = list(set(HIGHER_TIMEFRAME_MAP.values()))

        for symbol in self.config.symbols:
            for timeframe in higher_timeframes:
                try:
                    self.logger.info(f"[{symbol}] 加载 {timeframe} 历史 K 线...")

                    # 获取 EMA 需要 period 根 K 线
                    ema_period = self.config.strategy.ema_period
                    ohlcv = await self.gateway.get_klines(symbol, timeframe, limit=ema_period + 10)

                    if len(ohlcv) < ema_period:
                        self.logger.warning(f"[{symbol}] {timeframe} K 线数据不足：{len(ohlcv)}根，需要{ema_period}根")
                        continue

                    # 使用最新的 K 线
                    latest_candle = ohlcv[-1]
                    close_price = Decimal(str(latest_candle[4]))

                    # 计算 EMA
                    ema = await self.gateway.get_ema(symbol, timeframe, ema_period)

                    self.context_cache[symbol] = self.context_cache.get(symbol, {})
                    self.context_cache[symbol][timeframe] = {
                        "ema": ema,
                        "close": close_price,
                        "timestamp": int(latest_candle[0])
                    }

                    self.logger.info(
                        f"  ✓ {timeframe} EMA={float(ema):.2f}, Close={float(close_price):.2f}"
                    )

                except Exception as e:
                    self.logger.error(f"[{symbol}] {timeframe} 预加载失败：{e}")

        # 输出预加载结果
        self.logger.info("-" * 60)
        for symbol, tf_data in self.context_cache.items():
            for tf, data in tf_data.items():
                self.logger.info(f"[{symbol}] {tf}: EMA={float(data['ema']):.2f}")
        self.logger.info("=" * 60)
        self.logger.info(f"预加载完成，共加载 {sum(len(v) for v in self.context_cache.values())} 个上下文")
        self.logger.info("=" * 60)

    async def on_kline(self, kline: KlineData) -> None:
        """K 线数据回调入口

        Args:
            kline: K 线数据
        """
        global klines_checked
        symbol = kline.symbol
        timeframe = kline.timeframe
        klines_checked += 1

        # 1. 如果是更高周期 K 线（1h/4h/1d），更新上下文
        if timeframe in HIGHER_TIMEFRAME_MAP.values():
            await self._update_context(kline)

        # 2. 如果是监控周期 K 线（15m/1h/4h），检查信号
        if timeframe in self.config.timeframes:
            self.logger.debug(f"[{symbol}] {timeframe} 开始检测 Pinbar 信号...")
            await self._check_signal(kline)

    async def _update_context(self, kline: KlineData) -> None:
        """更新更高周期上下文

        Args:
            kline: 更高周期 K 线数据
        """
        symbol = kline.symbol
        timeframe = kline.timeframe

        if symbol not in self.context_cache:
            self.context_cache[symbol] = {}

        if timeframe not in self.context_cache[symbol]:
            self.context_cache[symbol][timeframe] = {}

        # 获取 EMA
        if self.gateway:
            try:
                ema_period = self.config.strategy.ema_period
                ema = await self.gateway.get_ema(symbol, timeframe, ema_period)

                self.context_cache[symbol][timeframe] = {
                    "ema": ema,
                    "close": kline.close,
                    "timestamp": kline.timestamp
                }

                self.logger.debug(
                    f"[{symbol}] {timeframe} 上下文更新：EMA={float(ema):.2f}, Close={float(kline.close):.2f}"
                )
            except Exception as e:
                self.logger.error(f"[{symbol}] 更新 {timeframe} 上下文失败：{e}")

    async def _check_signal(self, kline: KlineData) -> None:
        """检查是否产生信号

        Args:
            kline: K 线数据
        """
        global signals_found
        symbol = kline.symbol
        timeframe = kline.timeframe

        # 获取对应更高周期
        higher_timeframe = HIGHER_TIMEFRAME_MAP.get(timeframe)
        if not higher_timeframe:
            self.logger.debug(f"[{symbol}] 无更高周期映射，跳过")
            return

        # 获取更高周期上下文
        if symbol not in self.context_cache:
            self.logger.debug(f"[{symbol}] 无上下文缓存，跳过")
            return

        if higher_timeframe not in self.context_cache[symbol]:
            self.logger.debug(f"[{symbol}] {higher_timeframe} 无上下文数据，跳过")
            return

        context_data = self.context_cache[symbol][higher_timeframe]
        ema = context_data.get("ema")
        close = context_data.get("close")

        self.logger.debug(
            f"[{symbol}] {higher_timeframe} EMA={float(ema):.2f} Close={float(close):.2f}"
        )

        # 检查冷却
        if self._check_cooldown(symbol, timeframe):
            self.logger.debug(f"[{symbol}] {timeframe} 处于冷却时间，跳过信号检查")
            return

        # 构建上下文
        signal_context = {
            "ema_higher": context_data.get("ema"),
            "close_higher": context_data.get("close"),
            "higher_timeframe": higher_timeframe,
            "current_timeframe": timeframe
        }

        # 调用 check_pinbar_signal
        signal = check_pinbar_signal(kline, signal_context)

        if signal:
            signals_found += 1
            self.logger.info(
                f"🎯 [{symbol}] {timeframe} 产生信号：{signal.direction} "
                f"入场价={float(signal.entry_price):.2f} 止损={float(signal.stop_loss):.2f}"
            )
            await self._notify_signal(signal)
            self._update_cooldown(symbol, timeframe)
        else:
            self.logger.debug(f"[{symbol}] {timeframe} 无 Pinbar 信号")

    async def _notify_signal(self, signal: SignalResult) -> None:
        """发送飞书通知

        Args:
            signal: 信号结果
        """
        webhook_url = self.config.notification.feishu_webhook

        success = await send_feishu_notification(signal, webhook_url)

        if success:
            self.logger.info("飞书通知已发送")
        else:
            self.logger.warning("飞书通知发送失败")

    def _check_cooldown(self, symbol: str, timeframe: str) -> bool:
        """检查冷却时间（防止重复推送）

        Args:
            symbol: 交易对
            timeframe: 周期

        Returns:
            True: 处于冷却时间
            False: 可以发送信号
        """
        key = (symbol, timeframe)
        current_time = time.time()

        if key in self.cooldown_cache:
            last_signal_time = self.cooldown_cache[key]
            if current_time - last_signal_time < COOLDOWN_SECONDS:
                return True

        return False

    def _update_cooldown(self, symbol: str, timeframe: str) -> None:
        """更新冷却缓存

        Args:
            symbol: 交易对
            timeframe: 周期
        """
        key = (symbol, timeframe)
        self.cooldown_cache[key] = time.time()


# =============================================================================
# 主函数
# =============================================================================

async def main() -> None:
    """主函数"""
    # 1. 设置日志
    logger = setup_logging()
    logger.info("=" * 60)
    logger.info(f"盯盘狗 Lite {VERSION} - 启动")
    logger.info("=" * 60)

    # 2. 加载配置
    logger.info(f"加载配置文件：{CONFIG_FILE}")
    try:
        config = load_config(CONFIG_FILE)
        logger.info(f"配置加载成功：监控 {len(config.symbols)} 个币种")
    except FileNotFoundError as e:
        logger.error(f"配置文件不存在：{e}")
        return
    except yaml.YAMLError as e:
        logger.error(f"配置文件解析失败：{e}")
        return
    except ValueError as e:
        logger.error(f"配置验证失败：{e}")
        return

    # 3. 连接交易所
    logger.info("连接 Binance 交易所...")
    gateway = ExchangeGateway(config.exchange)
    try:
        await gateway.connect()
        logger.info("交易所连接成功")
    except Exception as e:
        logger.error(f"交易所连接失败：{e}")
        return

    # 4. 创建信号管道
    pipeline = SignalPipeline(config)
    pipeline.set_gateway(gateway)

    # 5. 预加载历史 K 线数据（建立 EMA 上下文）
    await pipeline.initialize_context()

    # 6. 订阅 K 线
    logger.info(f"订阅 K 线：{config.symbols} ({', '.join(config.timeframes)})")

    # 定义 K 线回调
    async def on_kline_callback(kline: KlineData) -> None:
        await pipeline.on_kline(kline)

    # 6. 保持运行（同步轮询）
    try:
        logger.info("系统就绪，开始监控...")

        # 进入同步轮询循环
        await gateway.subscribe_klines(
            config.symbols,
            config.timeframes,
            on_kline_callback
        )

    except KeyboardInterrupt:
        logger.info("收到中断信号，正在关闭...")
    except Exception as e:
        logger.error(f"运行出错：{e}")
    finally:
        await gateway.close()
        logger.info("已关闭交易所连接")


# =============================================================================
# 入口点
# =============================================================================

if __name__ == "__main__":
    asyncio.run(main())
