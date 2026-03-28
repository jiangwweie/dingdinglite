"""lite.py 集成测试"""
import asyncio
import os
import tempfile
import time
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import yaml

from models import (
    Direction,
    ExchangeConfig,
    KlineData,
    LiteConfig,
    NotificationConfig,
    PinbarConfig,
    SignalResult,
    StrategyConfig,
    Trend,
)
from lite import (
    CONFIG_FILE,
    COOLDOWN_SECONDS,
    HIGHER_TIMEFRAME_MAP,
    ExchangeGateway,
    SignalPipeline,
    load_config,
    setup_logging,
)


# =============================================================================
# 测试工具函数
# =============================================================================

def create_test_kline(
    symbol: str = "BTC/USDT:USDT",
    timeframe: str = "15m",
    timestamp: int = 1000000,
    open: float = 50000.0,
    high: float = 50100.0,
    low: float = 49900.0,
    close: float = 50050.0,
    volume: float = 1000.0,
    is_closed: bool = True
) -> KlineData:
    """创建测试 K 线数据"""
    return KlineData(
        symbol=symbol,
        timeframe=timeframe,
        timestamp=timestamp,
        open=Decimal(str(open)),
        high=Decimal(str(high)),
        low=Decimal(str(low)),
        close=Decimal(str(close)),
        volume=Decimal(str(volume)),
        is_closed=is_closed
    )


def create_test_signal(
    symbol: str = "BTC/USDT:USDT",
    timeframe: str = "15m",
    direction: Direction = Direction.LONG,
    entry_price: float = 50000.0,
    stop_loss: float = 49900.0,
    big_trend: Trend = Trend.BULLISH,
    pinbar_quality: float = 0.7,
    reason: str = "1h 多头趋势 + 15m 看涨 Pinbar"
) -> SignalResult:
    """创建测试信号"""
    return SignalResult(
        symbol=symbol,
        timeframe=timeframe,
        direction=direction,
        entry_price=Decimal(str(entry_price)),
        stop_loss=Decimal(str(stop_loss)),
        big_trend=big_trend,
        pinbar_quality=pinbar_quality,
        reason=reason
    )


def create_test_config(
    api_key: str = "test_key",
    api_secret: str = "test_secret",
    testnet: bool = True,
    symbols: list = None,
    timeframes: list = None,
    feishu_webhook: str = "https://test.feishu.cn/webhook"
) -> LiteConfig:
    """创建测试配置"""
    return LiteConfig(
        exchange=ExchangeConfig(
            name="binance",
            api_key=api_key,
            api_secret=api_secret,
            testnet=testnet
        ),
        symbols=symbols or ["BTC/USDT:USDT", "ETH/USDT:USDT"],
        timeframes=timeframes or ["15m", "1h"],
        strategy=StrategyConfig(
            ema_period=60,
            pinbar=PinbarConfig(min_wick_ratio=0.6, max_body_ratio=0.3)
        ),
        notification=NotificationConfig(feishu_webhook=feishu_webhook)
    )


# =============================================================================
# TestLoadConfig 测试类
# =============================================================================

class TestLoadConfig:
    """测试配置加载"""

    def test_load_valid_config(self, tmp_path):
        """测试加载有效配置文件"""
        config_data = {
            "exchange": {
                "name": "binance",
                "api_key": "test_key",
                "api_secret": "test_secret",
                "testnet": True
            },
            "symbols": ["BTC/USDT:USDT", "ETH/USDT:USDT"],
            "timeframes": ["15m", "1h"],
            "strategy": {
                "ema_period": 60,
                "pinbar": {
                    "min_wick_ratio": 0.6,
                    "max_body_ratio": 0.3
                }
            },
            "notification": {
                "feishu_webhook": "https://test.feishu.cn/webhook"
            }
        }

        config_file = tmp_path / "config.yaml"
        config_file.write_text(yaml.dump(config_data))

        config = load_config(str(config_file))

        assert config.exchange.api_key == "test_key"
        assert config.exchange.api_secret == "test_secret"
        assert config.exchange.testnet is True
        assert len(config.symbols) == 2
        assert "BTC/USDT:USDT" in config.symbols
        assert len(config.timeframes) == 2
        assert config.strategy.ema_period == 60

    def test_load_missing_file(self):
        """测试加载不存在的配置文件"""
        with pytest.raises(FileNotFoundError):
            load_config("/nonexistent/path/config.yaml")

    def test_load_invalid_yaml(self, tmp_path):
        """测试加载无效 YAML 文件"""
        config_file = tmp_path / "config.yaml"
        config_file.write_text("invalid: yaml: content: [")

        with pytest.raises(yaml.YAMLError):
            load_config(str(config_file))

    def test_load_missing_required_fields(self, tmp_path):
        """测试加载缺少必填字段的配置"""
        config_data = {
            "exchange": {
                "name": "binance"
                # 缺少 api_key 和 api_secret
            }
            # 缺少 symbols, timeframes, notification
        }

        config_file = tmp_path / "config.yaml"
        config_file.write_text(yaml.dump(config_data))

        with pytest.raises(Exception):
            load_config(str(config_file))


# =============================================================================
# TestExchangeGateway 测试类
# =============================================================================

class TestExchangeGateway:
    """测试交易所网关"""

    @pytest.mark.asyncio
    async def test_connect(self):
        """测试连接交易所"""
        config = ExchangeConfig(
            name="binance",
            api_key="test_key",
            api_secret="test_secret",
            testnet=True
        )

        gateway = ExchangeGateway(config)

        with patch.object(gateway, 'exchange', None):
            # Mock load_markets
            with patch('ccxt.async_support.binance') as mock_exchange_class:
                mock_exchange = AsyncMock()
                mock_exchange.load_markets = AsyncMock()
                mock_exchange_class.return_value = mock_exchange

                gateway.exchange = mock_exchange
                await gateway.connect()

                mock_exchange.load_markets.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_get_ema(self):
        """测试获取 EMA 值"""
        config = ExchangeConfig(
            name="binance",
            api_key="test_key",
            api_secret="test_secret",
            testnet=True
        )

        gateway = ExchangeGateway(config)

        # Mock exchange
        mock_exchange = AsyncMock()
        mock_exchange.fetch_ohlcv = AsyncMock(return_value=[
            [1000000, 50000, 50100, 49900, 50000, 1000],
            [1000001, 50000, 50100, 49900, 50000, 1000],
            [1000002, 50000, 50100, 49900, 50000, 1000],
        ])

        gateway.exchange = mock_exchange

        ema = await gateway.get_ema("BTC/USDT:USDT", "1h", 3)

        assert isinstance(ema, Decimal)
        assert ema == Decimal("50000")
        mock_exchange.fetch_ohlcv.assert_awaited_once_with("BTC/USDT:USDT", "1h", limit=3)

    @pytest.mark.asyncio
    async def test_get_ema_not_connected(self):
        """测试未连接时获取 EMA 抛异常"""
        config = ExchangeConfig(
            name="binance",
            api_key="test_key",
            api_secret="test_secret",
            testnet=True
        )

        gateway = ExchangeGateway(config)
        gateway.exchange = None

        with pytest.raises(RuntimeError, match="交易所未连接"):
            await gateway.get_ema("BTC/USDT:USDT", "1h", 60)

    @pytest.mark.asyncio
    async def test_close(self):
        """测试关闭连接"""
        config = ExchangeConfig(
            name="binance",
            api_key="test_key",
            api_secret="test_secret",
            testnet=True
        )

        gateway = ExchangeGateway(config)

        mock_exchange = AsyncMock()
        mock_exchange.close = AsyncMock()
        gateway.exchange = mock_exchange

        await gateway.close()

        mock_exchange.close.assert_awaited_once()


# =============================================================================
# TestSignalPipeline 测试类
# =============================================================================

class TestSignalPipeline:
    """测试信号处理管道"""

    @pytest.mark.asyncio
    async def test_on_kline_update_context(self):
        """测试更高周期 K 线更新上下文"""
        config = create_test_config()
        pipeline = SignalPipeline(config)

        # Mock gateway
        mock_gateway = AsyncMock()
        mock_gateway.get_ema = AsyncMock(return_value=Decimal("50000"))
        pipeline.set_gateway(mock_gateway)

        # 发送更高周期 K 线（1h）
        kline = create_test_kline(timeframe="1h")

        await pipeline.on_kline(kline)

        # 验证上下文已更新
        assert kline.symbol in pipeline.context_cache
        assert "1h" in pipeline.context_cache[kline.symbol]
        context = pipeline.context_cache[kline.symbol]["1h"]
        assert context["ema"] == Decimal("50000")
        assert context["close"] == kline.close

    @pytest.mark.asyncio
    async def test_on_kline_check_signal(self):
        """测试监控周期 K 线检查信号"""
        config = create_test_config()
        pipeline = SignalPipeline(config)

        # Mock gateway
        mock_gateway = AsyncMock()
        mock_gateway.get_ema = AsyncMock(return_value=Decimal("49000"))  # EMA 低于收盘价，多头趋势
        pipeline.set_gateway(mock_gateway)

        # 先更新 1h 上下文
        kline_1h = create_test_kline(timeframe="1h", close=50000.0)
        await pipeline.on_kline(kline_1h)

        # Mock check_pinbar_signal 返回信号
        mock_signal = create_test_signal()

        with patch('lite.check_pinbar_signal', return_value=mock_signal):
            with patch.object(pipeline, '_notify_signal', new_callable=AsyncMock) as mock_notify:
                # 发送 15m K 线（看涨 Pinbar）
                kline_15m = create_test_kline(
                    timeframe="15m",
                    open=50000,
                    high=50050,
                    low=49500,  # 长下影线
                    close=50040
                )

                await pipeline.on_kline(kline_15m)

                # 验证通知被调用
                mock_notify.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_cooldown_prevents_duplicate(self):
        """测试冷却时间防止重复推送"""
        config = create_test_config()
        pipeline = SignalPipeline(config)

        symbol = "BTC/USDT:USDT"
        timeframe = "15m"

        # 设置冷却时间
        pipeline.cooldown_cache[(symbol, timeframe)] = time.time()

        # 验证在冷却期内
        assert pipeline._check_cooldown(symbol, timeframe) is True

        # 模拟冷却时间已过
        pipeline.cooldown_cache[(symbol, timeframe)] = time.time() - COOLDOWN_SECONDS - 1

        # 验证冷却期已过
        assert pipeline._check_cooldown(symbol, timeframe) is False

    @pytest.mark.asyncio
    async def test_update_cooldown(self):
        """测试更新冷却缓存"""
        config = create_test_config()
        pipeline = SignalPipeline(config)

        symbol = "BTC/USDT:USDT"
        timeframe = "15m"

        # 更新冷却
        pipeline._update_cooldown(symbol, timeframe)

        # 验证冷却缓存已更新
        assert (symbol, timeframe) in pipeline.cooldown_cache
        assert abs(pipeline.cooldown_cache[(symbol, timeframe)] - time.time()) < 1

    @pytest.mark.asyncio
    async def test_notify_signal(self):
        """测试发送飞书通知"""
        config = create_test_config()
        pipeline = SignalPipeline(config)

        signal = create_test_signal()

        with patch('lite.send_feishu_notification', new_callable=AsyncMock) as mock_send:
            mock_send.return_value = True
            await pipeline._notify_signal(signal)
            mock_send.assert_awaited_once_with(signal, config.notification.feishu_webhook)


# =============================================================================
# TestIntegration 测试类
# =============================================================================

class TestIntegration:
    """集成测试"""

    @pytest.mark.asyncio
    async def test_full_signal_pipeline(self):
        """测试完整信号流程（模拟）"""
        # 1. 创建配置
        config = create_test_config()

        # 2. 创建信号管道
        pipeline = SignalPipeline(config)

        # 3. Mock 网关
        mock_gateway = AsyncMock()
        mock_gateway.get_ema = AsyncMock(return_value=Decimal("49000"))  # 多头趋势
        pipeline.set_gateway(mock_gateway)

        # 4. Mock 通知发送
        with patch('lite.send_feishu_notification', new_callable=AsyncMock) as mock_notify:
            mock_notify.return_value = True

            # 5. 更新 1h 上下文
            kline_1h = create_test_kline(timeframe="1h", close=50000.0)
            await pipeline.on_kline(kline_1h)

            # 6. 发送 15m 看涨 Pinbar K 线
            kline_15m = create_test_kline(
                timeframe="15m",
                open=50000,
                high=50050,
                low=49500,  # 长下影线
                close=50040
            )

            # Mock check_pinbar_signal 返回信号
            mock_signal = create_test_signal(
                direction=Direction.LONG,
                big_trend=Trend.BULLISH
            )

            with patch('lite.check_pinbar_signal', return_value=mock_signal):
                await pipeline.on_kline(kline_15m)

            # 7. 验证通知已发送
            mock_notify.assert_awaited_once()

            # 8. 验证冷却已更新
            assert ("BTC/USDT:USDT", "15m") in pipeline.cooldown_cache

    @pytest.mark.asyncio
    async def test_signal_filtered_in_cooldown(self):
        """测试冷却期内信号被过滤"""
        config = create_test_config()
        pipeline = SignalPipeline(config)

        mock_gateway = AsyncMock()
        mock_gateway.get_ema = AsyncMock(return_value=Decimal("49000"))
        pipeline.set_gateway(mock_gateway)

        # 设置冷却
        pipeline._update_cooldown("BTC/USDT:USDT", "15m")

        with patch('lite.send_feishu_notification', new_callable=AsyncMock) as mock_notify:
            # 更新 1h 上下文
            kline_1h = create_test_kline(timeframe="1h", close=50000.0)
            await pipeline.on_kline(kline_1h)

            # Mock 产生信号
            mock_signal = create_test_signal()
            with patch('lite.check_pinbar_signal', return_value=mock_signal):
                kline_15m = create_test_kline(timeframe="15m")
                await pipeline.on_kline(kline_15m)

            # 冷却期内不应发送通知
            mock_notify.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_no_signal_when_context_missing(self):
        """测试缺少上下文时不产生信号"""
        config = create_test_config()
        pipeline = SignalPipeline(config)

        mock_gateway = AsyncMock()
        pipeline.set_gateway(mock_gateway)

        with patch('lite.check_pinbar_signal', new_callable=AsyncMock) as mock_check:
            # 直接发送 15m K 线，但没有 1h 上下文
            kline_15m = create_test_kline(timeframe="15m")
            await pipeline.on_kline(kline_15m)

            # check_pinbar_signal 不应被调用
            mock_check.assert_not_awaited()


# =============================================================================
# TestSetupLogging 测试类
# =============================================================================

class TestSetupLogging:
    """测试日志系统"""

    def test_setup_logging_creates_directory(self, tmp_path):
        """测试日志系统创建目录"""
        log_dir = tmp_path / "test_logs"
        log_file = log_dir / "test.log"

        with patch('lite.LOG_FILE', str(log_file)):
            logger = setup_logging()

            assert log_dir.exists()
            assert len(logger.handlers) == 2  # 文件处理器 + 终端处理器

    def test_setup_logging_returns_logger(self):
        """测试日志系统返回 logger"""
        logger = setup_logging()
        assert logger is not None
        assert logger.name == "dingpang-lite"


# =============================================================================
# TestConstants 测试类
# =============================================================================

class TestConstants:
    """测试常量定义"""

    def test_higher_timeframe_map(self):
        """测试周期映射"""
        assert HIGHER_TIMEFRAME_MAP["15m"] == "1h"
        assert HIGHER_TIMEFRAME_MAP["1h"] == "4h"
        assert HIGHER_TIMEFRAME_MAP["4h"] == "1d"

    def test_cooldown_seconds(self):
        """测试冷却时间（2 分钟）"""
        assert COOLDOWN_SECONDS == 120

    def test_config_file(self):
        """测试配置文件名"""
        assert CONFIG_FILE == "config.yaml"


# =============================================================================
# TestSchedulerIntegration 测试类
# =============================================================================

class TestSchedulerIntegration:
    """测试调度器集成"""

    @pytest.mark.asyncio
    async def test_scheduler_kline_callback_triggered(self):
        """验证调度器在 K 线闭合时触发回调"""
        from lite import ExchangeGateway, KlineData
        from decimal import Decimal
        from unittest.mock import MagicMock, AsyncMock, patch
        import asyncio

        # Mock 闭合时刻判断和 K 线闭合验证
        with patch('scheduler.is_kline_close_time', return_value=True):
            with patch('scheduler.is_kline_closed', return_value=True):
                # 创建测试配置
                exchange_config = MagicMock()
                exchange_config.api_key = "test_key"
                exchange_config.api_secret = "test_secret"
                exchange_config.testnet = True

                gateway = ExchangeGateway(exchange_config)

                # Mock 交易所连接
                mock_exchange = AsyncMock()
                mock_exchange.load_markets = AsyncMock()
                mock_exchange.fetch_ohlcv = AsyncMock(return_value=[
                    [100000000000, 50000, 51000, 49000, 50500, 1000],  # 已闭合
                    [100000900000, 50500, 51500, 50000, 51000, 1000],  # 未闭合
                ])
                gateway.exchange = mock_exchange

                # 记录回调
                callback_called = []

                async def callback(kline: KlineData):
                    callback_called.append(kline)
                    # 收到回调后退出循环
                    raise asyncio.CancelledError("Test complete")

                # 创建任务并在收到回调后取消
                task = asyncio.create_task(
                    gateway.subscribe_klines(
                        ["BTC/USDT:USDT"],
                        ["15m"],
                        callback
                    )
                )

                # 等待一小段时间让回调执行
                await asyncio.sleep(0.1)

                # 取消任务
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

                # 验证回调被调用
                assert len(callback_called) > 0
                assert callback_called[0].symbol == "BTC/USDT:USDT"
                assert callback_called[0].timeframe == "15m"
                assert callback_called[0].is_closed is True
