"""models.py 单元测试"""
import pytest
from pydantic import ValidationError
from decimal import Decimal

from models import (
    KlineData,
    SignalResult,
    LiteConfig,
    Direction,
    Trend,
    ExchangeConfig,
    StrategyConfig,
    NotificationConfig,
)


class TestKlineData:
    """KlineData 测试"""

    def test_valid_kline(self):
        """正常创建 K 线"""
        kline = KlineData(
            symbol="BTC/USDT:USDT",
            timeframe="15m",
            timestamp=1711584000000,
            open=Decimal("67850.0"),
            high=Decimal("67900.0"),
            low=Decimal("67800.0"),
            close=Decimal("67880.0"),
            volume=Decimal("100.5"),
            is_closed=True,
        )
        assert kline.symbol == "BTC/USDT:USDT"
        assert kline.timeframe == "15m"
        assert kline.is_closed is True
        assert kline.close == Decimal("67880.0")

    def test_decimal_conversion(self):
        """字符串自动转 Decimal"""
        kline = KlineData(
            symbol="BTC/USDT:USDT",
            timeframe="15m",
            timestamp=1711584000000,
            open="67850.5",
            high="67900.0",
            low="67800.0",
            close="67880.5",
            volume="100.5",
            is_closed=True,
        )
        assert isinstance(kline.open, Decimal)
        assert isinstance(kline.high, Decimal)
        assert isinstance(kline.low, Decimal)
        assert isinstance(kline.close, Decimal)
        assert isinstance(kline.volume, Decimal)
        assert kline.close == Decimal("67880.5")

    def test_missing_field(self):
        """缺失必填字段报错"""
        with pytest.raises(ValidationError) as exc_info:
            KlineData(
                symbol="BTC/USDT:USDT",
                timeframe="15m",
                # 缺失 timestamp, open, high, low, close, volume, is_closed
            )
        assert "timestamp" in str(exc_info.value) or "open" in str(exc_info.value)


class TestSignalResult:
    """SignalResult 测试"""

    def test_valid_signal(self):
        """正常创建信号"""
        signal = SignalResult(
            symbol="BTC/USDT:USDT",
            timeframe="15m",
            direction=Direction.LONG,
            entry_price=Decimal("67850.0"),
            stop_loss=Decimal("67200.0"),
            big_trend=Trend.BULLISH,
            pinbar_quality=0.72,
            reason="1h 多头趋势 + 15m 看涨 Pinbar",
        )
        assert signal.direction == Direction.LONG
        assert signal.stop_loss == Decimal("67200.0")
        assert signal.big_trend == Trend.BULLISH
        assert signal.pinbar_quality == 0.72

    def test_str_representation(self):
        """__str__ 输出格式"""
        signal = SignalResult(
            symbol="BTC/USDT:USDT",
            timeframe="15m",
            direction=Direction.LONG,
            entry_price=Decimal("67850.0"),
            stop_loss=Decimal("67200.0"),
            big_trend=Trend.BULLISH,
            pinbar_quality=0.72,
            reason="1h 多头趋势 + 15m 看涨 Pinbar",
        )
        text = str(signal)
        assert "BTC/USDT:USDT" in text
        assert "做多" in text
        assert "多头" in text
        assert "67,850.00" in text
        assert "67,200.00" in text

    def test_short_signal_str(self):
        """做空信号输出格式"""
        signal = SignalResult(
            symbol="ETH/USDT:USDT",
            timeframe="1h",
            direction=Direction.SHORT,
            entry_price=Decimal("3500.0"),
            stop_loss=Decimal("3600.0"),
            big_trend=Trend.BEARISH,
            pinbar_quality=0.65,
            reason="1h 空头趋势 + 15m 看跌 Pinbar",
        )
        text = str(signal)
        assert "ETH/USDT:USDT" in text
        assert "做空" in text
        assert "空头" in text


class TestLiteConfig:
    """LiteConfig 测试"""

    def test_load_valid_config(self):
        """加载完整配置"""
        config_dict = {
            "exchange": {
                "name": "binance",
                "api_key": "test_key",
                "api_secret": "test_secret",
                "testnet": True,
            },
            "symbols": ["BTC/USDT:USDT"],
            "timeframes": ["15m", "1h"],
            "strategy": {
                "ema_period": 60,
                "pinbar": {
                    "min_wick_ratio": 0.6,
                    "max_body_ratio": 0.3,
                },
            },
            "notification": {
                "feishu_webhook": "https://test.webhook",
            },
        }
        config = LiteConfig(**config_dict)
        assert config.exchange.name == "binance"
        assert config.exchange.testnet is True
        assert config.strategy.ema_period == 60
        assert len(config.symbols) == 1
        assert config.symbols[0] == "BTC/USDT:USDT"

    def test_validate_symbols(self):
        """symbols 验证"""
        # 空 symbols 应该报错
        with pytest.raises(ValidationError) as exc_info:
            LiteConfig(
                exchange=ExchangeConfig(
                    name="binance", api_key="key", api_secret="secret"
                ),
                symbols=[],
                timeframes=["15m"],
                notification=NotificationConfig(feishu_webhook="https://test.webhook"),
            )
        assert "至少" in str(exc_info.value) or "symbols" in str(exc_info.value).lower()

        # 至少 1 个 symbol 应该通过
        config = LiteConfig(
            exchange=ExchangeConfig(name="binance", api_key="key", api_secret="secret"),
            symbols=["BTC/USDT:USDT"],
            timeframes=["15m"],
            notification=NotificationConfig(feishu_webhook="https://test.webhook"),
        )
        assert len(config.symbols) == 1

    def test_validate_timeframes(self):
        """timeframes 验证"""
        # 空 timeframes 应该报错
        with pytest.raises(ValidationError) as exc_info:
            LiteConfig(
                exchange=ExchangeConfig(
                    name="binance", api_key="key", api_secret="secret"
                ),
                symbols=["BTC/USDT:USDT"],
                timeframes=[],
                notification=NotificationConfig(feishu_webhook="https://test.webhook"),
            )
        assert "至少" in str(exc_info.value) or "timeframes" in str(exc_info.value).lower()

        # 非法周期应该报错
        with pytest.raises(ValidationError) as exc_info:
            LiteConfig(
                exchange=ExchangeConfig(
                    name="binance", api_key="key", api_secret="secret"
                ),
                symbols=["BTC/USDT:USDT"],
                timeframes=["15m", "1d"],  # 1d 不合法
                notification=NotificationConfig(feishu_webhook="https://test.webhook"),
            )
        assert "15m" in str(exc_info.value) or "1h" in str(exc_info.value) or "4h" in str(exc_info.value)

        # 合法的 timeframes 应该通过
        config = LiteConfig(
            exchange=ExchangeConfig(name="binance", api_key="key", api_secret="secret"),
            symbols=["BTC/USDT:USDT"],
            timeframes=["15m", "1h", "4h"],
            notification=NotificationConfig(feishu_webhook="https://test.webhook"),
        )
        assert len(config.timeframes) == 3
        assert "15m" in config.timeframes
        assert "1h" in config.timeframes
        assert "4h" in config.timeframes

    def test_default_values(self):
        """测试默认值"""
        config = LiteConfig(
            exchange=ExchangeConfig(
                name="binance", api_key="key", api_secret="secret"
            ),
            symbols=["BTC/USDT:USDT"],
            timeframes=["15m"],
            notification=NotificationConfig(feishu_webhook="https://test.webhook"),
        )
        # 测试默认值
        assert config.exchange.name == "binance"
        assert config.exchange.testnet is False
        assert config.strategy.ema_period == 60
        assert config.strategy.pinbar.min_wick_ratio == 0.6
        assert config.strategy.pinbar.max_body_ratio == 0.3
        assert config.logging.level == "INFO"
        assert config.logging.file == "logs/lite.log"
