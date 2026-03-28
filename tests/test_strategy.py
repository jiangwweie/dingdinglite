"""strategy.py 单元测试"""
from decimal import Decimal
import pytest

from models import KlineData, Direction, Trend
from strategy import (
    calculate_wick_ratio,
    is_bullish_pinbar,
    is_bearish_pinbar,
    get_ema_trend,
    calculate_stop_loss,
    check_pinbar_signal,
)


def create_kline(
    symbol: str = "BTC/USDT:USDT",
    timeframe: str = "15m",
    timestamp: int = 1000000000000,
    open: float = 100.0,
    high: float = 100.0,
    low: float = 100.0,
    close: float = 100.0,
    volume: float = 1000.0,
    is_closed: bool = True,
) -> KlineData:
    """辅助函数：创建 KlineData"""
    return KlineData(
        symbol=symbol,
        timeframe=timeframe,
        timestamp=timestamp,
        open=Decimal(str(open)),
        high=Decimal(str(high)),
        low=Decimal(str(low)),
        close=Decimal(str(close)),
        volume=Decimal(str(volume)),
        is_closed=is_closed,
    )


class TestCalculateWickRatio:
    """测试影线占比计算"""

    def test_normal_bullish_kline(self):
        """普通阳线"""
        kline = create_kline(open=100, high=110, low=90, close=105)
        upper, lower, body = calculate_wick_ratio(kline)
        # 上影线 = 110 - 105 = 5, 下影线 = 100 - 90 = 10, 实体 = 5
        # 总长 = 20
        assert upper == Decimal("0.25")  # 5/20
        assert lower == Decimal("0.5")   # 10/20
        assert body == Decimal("0.25")   # 5/20

    def test_doji_kline(self):
        """十字星 (开盘=收盘)"""
        kline = create_kline(open=100, high=110, low=90, close=100)
        upper, lower, body = calculate_wick_ratio(kline)
        # 上影线 = 110 - 100 = 10, 下影线 = 100 - 90 = 10, 实体 = 0
        assert upper == Decimal("0.5")
        assert lower == Decimal("0.5")
        assert body == Decimal("0")

    def test_flat_kline(self):
        """一字线 (高低开收相同)"""
        kline = create_kline(open=100, high=100, low=100, close=100)
        upper, lower, body = calculate_wick_ratio(kline)
        assert upper == Decimal("0")
        assert lower == Decimal("0")
        assert body == Decimal("0")


class TestPinbarDetection:
    """测试 Pinbar 检测"""

    def test_bullish_pinbar_detected(self):
        """看涨 Pinbar 检测 - 长下影线"""
        # 下影线很长，实体在顶部
        # 总长 = 100 - 80 = 20
        # 下影线 = 95 - 80 = 15 (75%)
        # 上影线 = 100 - 97 = 3 (15%)
        # 实体 = 97 - 95 = 2 (10%)
        # 实体底部位置 = (95 - 80) / 20 = 0.75 (不在顶部 10%)
        # 需要调整：让实体位于顶部 10%
        kline = create_kline(open=99, high=100, low=80, close=99.5)
        # 总长 = 20
        # 下影线 = 99 - 80 = 19 (95%)
        # 实体 = 0.5 (2.5%)
        # 实体底部位置 = (99 - 80) / 20 = 0.95 (顶部 5%)
        assert is_bullish_pinbar(kline) is True

    def test_bearish_pinbar_detected(self):
        """看跌 Pinbar 检测 - 长上影线"""
        # 总长 = 120 - 100 = 20
        # 上影线 = 120 - 101 = 19 (95%)
        # 实体 = 1 (5%)
        # 实体顶部位置 = (101 - 100) / 20 = 0.05 (底部 5%)
        kline = create_kline(open=100.5, high=120, low=100, close=100)
        assert is_bearish_pinbar(kline) is True

    def test_normal_kline_no_pinbar(self):
        """普通 K 线非 Pinbar"""
        # 实体较大，影线较短
        kline = create_kline(open=90, high=110, low=85, close=105)
        # 实体 = 15, 总长 = 25, 实体占比 = 60% > 30%
        assert is_bullish_pinbar(kline) is False
        assert is_bearish_pinbar(kline) is False

    def test_bullish_pinbar_body_too_large(self):
        """看涨 Pinbar 但实体太大"""
        # 实体在顶部，但实体占比过大
        kline = create_kline(open=88, high=100, low=80, close=88)
        # 总长 = 20
        # 下影线 = 8, 50% ✓
        # 实体 = 12, 60% > 35% ✗
        assert is_bullish_pinbar(kline, min_wick=0.5, max_body=0.35, body_position_tolerance=0.3) is False

    def test_bearish_pinbar_wick_too_short(self):
        """看跌 Pinbar 但上影线太短"""
        # 实体在底部，但上影线太短
        kline = create_kline(open=90, high=95, low=80, close=92)
        # 总长 = 15
        # 上影线 = 3, 20% < 50% ✗
        assert is_bearish_pinbar(kline, min_wick=0.5, max_body=0.35, body_position_tolerance=0.3) is False


class TestEmaTrend:
    """测试 EMA 趋势判断"""

    def test_bullish_trend(self):
        """close > EMA"""
        trend = get_ema_trend(Decimal("105"), Decimal("100"))
        assert trend == Trend.BULLISH

    def test_bearish_trend(self):
        """close < EMA"""
        trend = get_ema_trend(Decimal("95"), Decimal("100"))
        assert trend == Trend.BEARISH

    def test_neutral_trend(self):
        """close == EMA (现在算 BULLISH，更激进)"""
        trend = get_ema_trend(Decimal("100"), Decimal("100"))
        assert trend == Trend.BULLISH  # 新逻辑：close >= EMA 算多头


class TestStopLoss:
    """测试止损价计算（Pinbar 极值点）"""

    def test_long_stop_loss(self):
        """LONG 止损：Pinbar 最低价"""
        kline = create_kline(low=100)
        stop_loss = calculate_stop_loss(kline, Direction.LONG)
        assert stop_loss == Decimal("100")  # 极值点，无缓冲

    def test_short_stop_loss(self):
        """SHORT 止损：Pinbar 最高价"""
        kline = create_kline(high=100)
        stop_loss = calculate_stop_loss(kline, Direction.SHORT)
        assert stop_loss == Decimal("100")  # 极值点，无缓冲


class TestPinbarSignal:
    """测试 Pinbar 信号生成"""

    def test_long_signal_in_bullish_trend(self):
        """多头趋势 + 看涨 Pinbar = LONG"""
        # 创建一个看涨 Pinbar
        kline = create_kline(symbol="BTC/USDT:USDT", timeframe="15m",
                            open=99, high=100, low=80, close=99.5)
        context = {
            "ema_higher": Decimal("90"),
            "close_higher": Decimal("95"),  # close > ema → Bullish
            "higher_timeframe": "1h",
            "current_timeframe": "15m",
        }
        result = check_pinbar_signal(kline, context)
        assert result is not None
        assert result.direction == Direction.LONG
        assert result.big_trend == Trend.BULLISH
        assert "1h 多头趋势" in result.reason
        assert "看涨 Pinbar" in result.reason

    def test_short_signal_in_bearish_trend(self):
        """空头趋势 + 看跌 Pinbar = SHORT"""
        # 创建一个看跌 Pinbar
        kline = create_kline(symbol="ETH/USDT:USDT", timeframe="15m",
                            open=100.5, high=120, low=100, close=100)
        context = {
            "ema_higher": Decimal("110"),
            "close_higher": Decimal("105"),  # close < ema → Bearish
            "higher_timeframe": "1h",
            "current_timeframe": "15m",
        }
        result = check_pinbar_signal(kline, context)
        assert result is not None
        assert result.direction == Direction.SHORT
        assert result.big_trend == Trend.BEARISH
        assert "1h 空头趋势" in result.reason
        assert "看跌 Pinbar" in result.reason

    def test_no_signal_wrong_trend_long(self):
        """空头趋势 + 看涨 Pinbar = 无信号"""
        kline = create_kline(open=99, high=100, low=80, close=99.5)  # 看涨 Pinbar
        context = {
            "ema_higher": Decimal("110"),
            "close_higher": Decimal("105"),  # close < ema → Bearish
            "higher_timeframe": "1h",
            "current_timeframe": "15m",
        }
        result = check_pinbar_signal(kline, context)
        assert result is None

    def test_no_signal_wrong_trend_short(self):
        """多头趋势 + 看跌 Pinbar = 无信号"""
        kline = create_kline(open=100.5, high=120, low=100, close=100)  # 看跌 Pinbar
        context = {
            "ema_higher": Decimal("90"),
            "close_higher": Decimal("95"),  # close > ema → Bullish
            "higher_timeframe": "1h",
            "current_timeframe": "15m",
        }
        result = check_pinbar_signal(kline, context)
        assert result is None

    def test_no_signal_no_pinbar(self):
        """多头趋势 + 普通 K 线 = 无信号"""
        kline = create_kline(open=90, high=110, low=85, close=105)  # 普通 K 线
        context = {
            "ema_higher": Decimal("90"),
            "close_higher": Decimal("95"),  # Bullish
            "higher_timeframe": "1h",
            "current_timeframe": "15m",
        }
        result = check_pinbar_signal(kline, context)
        assert result is None

    def test_no_signal_neutral_trend(self):
        """中性趋势 = 无信号（但现在没有中性趋势了）"""
        # 新逻辑中 close >= EMA 算 BULLISH，所以这个测试需要调整
        # 这里测试当 EMA 数据缺失时的情况
        kline = create_kline(open=99, high=100, low=80, close=99.5)  # 看涨 Pinbar
        context = {
            "ema_higher": None,  # EMA 数据缺失
            "close_higher": Decimal("100"),
            "higher_timeframe": "1h",
            "current_timeframe": "15m",
        }
        result = check_pinbar_signal(kline, context)
        assert result is None

    def test_signal_result_content(self):
        """验证 SignalResult 内容"""
        kline = create_kline(
            symbol="SOL/USDT:USDT",
            timeframe="15m",
            open=99, high=100, low=80, close=99.5
        )
        context = {
            "ema_higher": Decimal("90"),
            "close_higher": Decimal("95"),
            "higher_timeframe": "1h",
            "current_timeframe": "15m",
        }
        result = check_pinbar_signal(kline, context)
        assert result is not None
        assert result.symbol == "SOL/USDT:USDT"
        assert result.timeframe == "15m"
        assert result.direction == Direction.LONG
        assert result.entry_price == Decimal("99.5")
        assert result.stop_loss == Decimal("80")  # Pinbar 最低价（新逻辑）
        assert result.big_trend == Trend.BULLISH
        assert result.pinbar_quality > 0.5  # 下影线占比应该 > 50%
