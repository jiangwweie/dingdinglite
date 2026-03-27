"""Lite 版策略逻辑 - Pinbar + EMA 趋势"""
from decimal import Decimal
from typing import Optional

from models import KlineData, SignalResult, Direction, Trend


def calculate_wick_ratio(kline: KlineData) -> tuple[Decimal, Decimal, Decimal]:
    """
    计算 K 线的影线占比
    返回：(上影线占比，下影线占比，实体占比)
    """
    high = kline.high
    low = kline.low
    open_price = kline.open
    close_price = kline.close

    # K 线总长度
    total_range = high - low
    if total_range == 0:
        return Decimal("0"), Decimal("0"), Decimal("0")

    # 上影线 = 最高价 - max(开盘，收盘)
    upper_wick = high - max(open_price, close_price)

    # 下影线 = min(开盘，收盘) - 最低价
    lower_wick = min(open_price, close_price) - low

    # 实体 = abs(收盘 - 开盘)
    body = abs(close_price - open_price)

    upper_ratio = upper_wick / total_range
    lower_ratio = lower_wick / total_range
    body_ratio = body / total_range

    return upper_ratio, lower_ratio, body_ratio


def is_bullish_pinbar(kline: KlineData, min_wick: float = 0.6, max_body: float = 0.3) -> bool:
    """
    检测看涨 Pinbar（长下影线，实体在顶部）
    条件:
        - 下影线占比 >= min_wick (默认 60%)
        - 实体占比 <= max_body (默认 30%)
        - 实体位于 K 线顶部 10% 区间
    """
    upper_ratio, lower_ratio, body_ratio = calculate_wick_ratio(kline)

    # 下影线占比 >= min_wick
    if lower_ratio < Decimal(str(min_wick)):
        return False

    # 实体占比 <= max_body
    if body_ratio > Decimal(str(max_body)):
        return False

    # 实体位于 K 线顶部 10% 区间
    # 即：min(open, close) 位于总区间的顶部 10%
    open_price = kline.open
    close_price = kline.close
    high = kline.high
    low = kline.low
    total_range = high - low

    if total_range == 0:
        return False

    body_top = max(open_price, close_price)
    body_bottom = min(open_price, close_price)

    # 实体底部距离最低价的比例应该 >= 0.9 (即实体位于顶部 10%)
    position_ratio = (body_bottom - low) / total_range
    position_tolerance = Decimal("0.1")

    # 实体位于顶部 10% 区间意味着 position_ratio >= 0.9
    if position_ratio < Decimal("0.9") - position_tolerance:
        return False

    return True


def is_bearish_pinbar(kline: KlineData, min_wick: float = 0.6, max_body: float = 0.3) -> bool:
    """
    检测看跌 Pinbar（长上影线，实体在底部）
    条件:
        - 上影线占比 >= min_wick (默认 60%)
        - 实体占比 <= max_body (默认 30%)
        - 实体位于 K 线底部 10% 区间
    """
    upper_ratio, lower_ratio, body_ratio = calculate_wick_ratio(kline)

    # 上影线占比 >= min_wick
    if upper_ratio < Decimal(str(min_wick)):
        return False

    # 实体占比 <= max_body
    if body_ratio > Decimal(str(max_body)):
        return False

    # 实体位于 K 线底部 10% 区间
    open_price = kline.open
    close_price = kline.close
    high = kline.high
    low = kline.low
    total_range = high - low

    if total_range == 0:
        return False

    body_top = max(open_price, close_price)

    # 实体顶部距离最低价的比例应该 <= 0.1 (即实体位于底部 10%)
    position_ratio = (body_top - low) / total_range
    position_tolerance = Decimal("0.1")

    if position_ratio > position_tolerance:
        return False

    return True


def get_ema_trend(close: Decimal, ema: Decimal) -> Trend:
    """
    根据收盘价与 EMA 的关系判断趋势
    返回：
        - Trend.BULLISH: close > ema
        - Trend.BEARISH: close < ema
        - Trend.NEUTRAL: close == ema
    """
    if close > ema:
        return Trend.BULLISH
    elif close < ema:
        return Trend.BEARISH
    else:
        return Trend.NEUTRAL


def calculate_stop_loss(kline: KlineData, direction: Direction) -> Decimal:
    """
    计算止损价
    LONG: Pinbar 最低价下方 0.1% (kline.low * 0.999)
    SHORT: Pinbar 最高价上方 0.1% (kline.high * 1.001)
    """
    if direction == Direction.LONG:
        return kline.low * Decimal("0.999")
    else:  # SHORT
        return kline.high * Decimal("1.001")


def check_pinbar_signal(kline_15m: KlineData, context: dict) -> Optional[SignalResult]:
    """
    检查是否产生 Pinbar 信号（顺大逆小逻辑）

    Args:
        kline_15m: 15 分钟 K 线
        context: 上下文信息，包含:
            - ema_higher: 更高周期的 EMA 值
            - close_higher: 更高周期的收盘价
            - higher_timeframe: 更高周期名称（如 "1h"）
            - current_timeframe: 当前周期名称（如 "15m"）

    Returns:
        SignalResult if signal detected
        None otherwise
    """
    ema_higher = context.get("ema_higher")
    close_higher = context.get("close_higher")
    higher_timeframe = context.get("higher_timeframe", "1h")
    current_timeframe = context.get("current_timeframe", "15m")

    if ema_higher is None or close_higher is None:
        return None

    # 1. 判断大周期趋势
    big_trend = get_ema_trend(close_higher, ema_higher)

    # 2. 顺大逆小：只做顺势方向的 Pinbar
    direction = None
    is_pinbar = False

    if big_trend == Trend.BULLISH:
        # Bullish 趋势：只做看涨 Pinbar → LONG 信号
        if is_bullish_pinbar(kline_15m):
            direction = Direction.LONG
            is_pinbar = True
    elif big_trend == Trend.BEARISH:
        # Bearish 趋势：只做看跌 Pinbar → SHORT 信号
        if is_bearish_pinbar(kline_15m):
            direction = Direction.SHORT
            is_pinbar = True
    # Neutral 趋势：无信号

    if not is_pinbar or direction is None:
        return None

    # 3. 计算止损价
    stop_loss = calculate_stop_loss(kline_15m, direction)

    # 4. 计算形态质量（影线占比）
    upper_ratio, lower_ratio, body_ratio = calculate_wick_ratio(kline_15m)
    if direction == Direction.LONG:
        pinbar_quality = float(lower_ratio)
    else:
        pinbar_quality = float(upper_ratio)

    # 5. 生成 reason 字符串
    trend_text = "多头" if big_trend == Trend.BULLISH else "空头"
    pinbar_type = "看涨" if direction == Direction.LONG else "看跌"
    reason = f"{higher_timeframe} {trend_text}趋势 + {current_timeframe} {pinbar_type} Pinbar"

    # 6. 生成 SignalResult
    return SignalResult(
        symbol=kline_15m.symbol,
        timeframe=current_timeframe,
        direction=direction,
        entry_price=kline_15m.close,
        stop_loss=stop_loss,
        big_trend=big_trend,
        pinbar_quality=pinbar_quality,
        reason=reason
    )
