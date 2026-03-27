"""盯盘狗 Lite 版主入口 - Pinbar 信号监控"""
import asyncio
import logging
import os
import time
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

# 冷却时间（5 分钟）
COOLDOWN_SECONDS = 300

# 版本
VERSION = "v0.1.0"


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
    logger.setLevel(logging.INFO)

    # 清空已有处理器
    logger.handlers.clear()

    # 文件处理器
    file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(logging.Formatter(LOG_FORMAT, DATE_FORMAT))
    logger.addHandler(file_handler)

    # 终端处理器
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(logging.Formatter(LOG_FORMAT, DATE_FORMAT))
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
        """获取 EMA 值（用 SMA 近似简化实现）

        Args:
            symbol: 交易对，如 "BTC/USDT:USDT"
            timeframe: 周期，如 "1h"
            period: EMA 周期

        Returns:
            EMA 值
        """
        if self.exchange is None:
            raise RuntimeError("交易所未连接，请先调用 connect()")

        # 获取 K 线数据（用于计算 SMA 近似 EMA）
        ohlcv = await self.exchange.fetch_ohlcv(symbol, timeframe, limit=period)

        if len(ohlcv) < period:
            raise ValueError(f"K 线数据不足：需要{period}根，实际{len(ohlcv)}根")

        # 用 SMA 近似 EMA：取最近 period 根 K 线的收盘价平均值
        close_prices = [Decimal(str(candle[4])) for candle in ohlcv[-period:]]
        sma = sum(close_prices) / len(close_prices)

        return sma

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

        self.logger.info("同步轮询调度器启动")

        while True:
            triggered = False

            # 检查每个周期是否到达闭合时刻
            for symbol in symbols:
                for timeframe in timeframes:
                    if is_kline_close_time(timeframe):
                        try:
                            # 读取最近 2 根 K 线，使用前一根（确保已闭合）
                            ohlcv = await self.get_klines(symbol, timeframe, limit=2)

                            if len(ohlcv) < 2:
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

    async def on_kline(self, kline: KlineData) -> None:
        """K 线数据回调入口

        Args:
            kline: K 线数据
        """
        symbol = kline.symbol
        timeframe = kline.timeframe

        # 1. 如果是更高周期 K 线（1h/4h/1d），更新上下文
        if timeframe in HIGHER_TIMEFRAME_MAP.values():
            await self._update_context(kline)

        # 2. 如果是监控周期 K 线（15m/1h/4h）且已闭合，检查信号
        # 注意：轮询模式下 is_closed=False，这里我们检查所有 K 线
        if timeframe in self.config.timeframes:
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
        symbol = kline.symbol
        timeframe = kline.timeframe

        # 获取对应更高周期
        higher_timeframe = HIGHER_TIMEFRAME_MAP.get(timeframe)
        if not higher_timeframe:
            return

        # 获取更高周期上下文
        if symbol not in self.context_cache:
            return

        if higher_timeframe not in self.context_cache[symbol]:
            return

        context_data = self.context_cache[symbol][higher_timeframe]

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
            self.logger.info(
                f"[{symbol}] {timeframe} 产生信号：{signal.direction} "
                f"入场价={float(signal.entry_price):.2f}"
            )
            await self._notify_signal(signal)
            self._update_cooldown(symbol, timeframe)

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

    # 5. 订阅 K 线
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
