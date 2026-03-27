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


def is_bullish_pinbar(kline: KlineData, min_wick: float = 0.5, max_body: float = 0.4) -> bool:
    """
    检测看涨 Pinbar（长下影线，实体在顶部）
    条件:
        - 下影线占比 >= min_wick (默认 50%)
        - 实体占比 <= max_body (默认 40%)
        - 实体位于 K 线顶部 20% 区间
    """
    import logging
    logger = logging.getLogger("dingpang-lite")

    upper_ratio, lower_ratio, body_ratio = calculate_wick_ratio(kline)
    position_ratio = float(lower_ratio)  # 下影线占比

    logger.debug(
        f"  影线分析：上={float(upper_ratio):.1%} 下={float(lower_ratio):.1%} 实体={float(body_ratio):.1%}"
    )

    # 下影线占比 >= min_wick
    if lower_ratio < Decimal(str(min_wick)):
        logger.debug(f"  ✗ 下影线占比 {float(lower_ratio):.1%} < {min_wick:.1%}，不满足")
        return False

    # 实体占比 <= max_body
    if body_ratio > Decimal(str(max_body)):
        logger.debug(f"  ✗ 实体占比 {float(body_ratio):.1%} > {max_body:.1%}，不满足")
        return False

    # 实体位于 K 线顶部 10% 区间
    open_price = kline.open
    close_price = kline.close
    high = kline.high
    low = kline.low
    total_range = high - low

    if total_range == 0:
        return False

    body_top = max(open_price, close_price)
    body_bottom = min(open_price, close_price)

    # 实体底部距离最低价的比例应该 >= 0.8 (即实体位于顶部 20%)
    position_ratio = (body_bottom - low) / total_range
    position_tolerance = Decimal("0.1")

    logger.debug(f"  实体位置：{float(position_ratio):.1%} (要求 >= {0.8 - float(position_tolerance):.1%})")

    # 实体位于顶部 20% 区间意味着 position_ratio >= 0.8
    if position_ratio < Decimal("0.8") - position_tolerance:
        logger.debug(f"  ✗ 实体位置 {float(position_ratio):.1%}，不满足顶部 20% 要求")
        return False

    logger.debug(f"  ✓ 看涨 Pinbar 确认！下影线={float(lower_ratio):.1%} 实体={float(body_ratio):.1%}")
    return True


def is_bearish_pinbar(kline: KlineData, min_wick: float = 0.5, max_body: float = 0.4) -> bool:
    """
    检测看跌 Pinbar（长上影线，实体在底部）
    条件:
        - 上影线占比 >= min_wick (默认 50%)
        - 实体占比 <= max_body (默认 40%)
        - 实体位于 K 线底部 20% 区间
    """
    import logging
    logger = logging.getLogger("dingpang-lite")

    upper_ratio, lower_ratio, body_ratio = calculate_wick_ratio(kline)

    logger.debug(
        f"  影线分析：上={float(upper_ratio):.1%} 下={float(lower_ratio):.1%} 实体={float(body_ratio):.1%}"
    )

    # 上影线占比 >= min_wick
    if upper_ratio < Decimal(str(min_wick)):
        logger.debug(f"  ✗ 上影线占比 {float(upper_ratio):.1%} < {min_wick:.1%}，不满足")
        return False

    # 实体占比 <= max_body
    if body_ratio > Decimal(str(max_body)):
        logger.debug(f"  ✗ 实体占比 {float(body_ratio):.1%} > {max_body:.1%}，不满足")
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

    # 实体顶部距离最低价的比例应该 <= 0.2 (即实体位于底部 20%)
    position_ratio = (body_top - low) / total_range
    position_tolerance = Decimal("0.1")

    logger.debug(f"  实体位置：{float(position_ratio):.1%} (要求 <= {0.2 + float(position_tolerance):.1%})")

    if position_ratio > Decimal("0.2") + position_tolerance:
        logger.debug(f"  ✗ 实体位置 {float(position_ratio):.1%}，不满足底部 20% 要求")
        return False

    logger.debug(f"  ✓ 看跌 Pinbar 确认！上影线={float(upper_ratio):.1%} 实体={float(body_ratio):.1%}")
    return True


def get_ema_trend(close: Decimal, ema: Decimal) -> Trend:
    """
    根据收盘价与 EMA 的关系判断趋势
    返回：
        - Trend.BULLISH: close >= ema (包含相等，更激进)
        - Trend.BEARISH: close < ema
    """
    # 激进模式：close >= ema 都算多头，减少中性情况
    if close >= ema:
        return Trend.BULLISH
    else:
        return Trend.BEARISH


def calculate_stop_loss(kline: KlineData, direction: Direction) -> Decimal:
    """
    计算止损价
    LONG: Pinbar 最低价下方 0.3% (kline.low * 0.997)
    SHORT: Pinbar 最高价上方 0.3% (kline.high * 1.003)
    """
    if direction == Direction.LONG:
        return kline.low * Decimal("0.997")
    else:  # SHORT
        return kline.high * Decimal("1.003")


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
    import logging
    logger = logging.getLogger("dingpang-lite")

    ema_higher = context.get("ema_higher")
    close_higher = context.get("close_higher")
    higher_timeframe = context.get("higher_timeframe", "1h")
    current_timeframe = context.get("current_timeframe", "15m")

    if ema_higher is None or close_higher is None:
        logger.debug("EMA 或收盘价数据缺失")
        return None

    # 1. 判断大周期趋势
    big_trend = get_ema_trend(close_higher, ema_higher)
    logger.debug(f"大周期趋势：{big_trend.value} (EMA={float(ema_higher):.2f}, Close={float(close_higher):.2f})")

    # 2. 顺大逆小：只做顺势方向的 Pinbar
    direction = None
    is_pinbar = False

    if big_trend == Trend.BULLISH:
        # Bullish 趋势：只做看涨 Pinbar → LONG 信号
        pinbar_result = is_bullish_pinbar(kline_15m)
        logger.debug(f"看涨 Pinbar 检测：{pinbar_result}")
        if pinbar_result:
            direction = Direction.LONG
            is_pinbar = True
    elif big_trend == Trend.BEARISH:
        # Bearish 趋势：只做看跌 Pinbar → SHORT 信号
        pinbar_result = is_bearish_pinbar(kline_15m)
        logger.debug(f"看跌 Pinbar 检测：{pinbar_result}")
        if pinbar_result:
            direction = Direction.SHORT
            is_pinbar = True

    if not is_pinbar or direction is None:
        return None

    logger.info(f"✓ Pinbar 形态确认，方向：{direction.value}")

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
