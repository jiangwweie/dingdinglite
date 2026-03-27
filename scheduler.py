"""同步轮询调度器 - K 线闭合时刻检测"""
import time
from datetime import datetime
from typing import Optional


# 周期分钟数
TIMEFRAME_MINUTES = {
    "15m": 15,
    "1h": 60,
    "4h": 240,
}


def is_kline_close_time(timeframe: str) -> bool:
    """判断当前时间是否是指定周期的 K 线闭合时刻

    Args:
        timeframe: 周期，如 "15m", "1h", "4h"

    Returns:
        True: 当前是闭合时刻，应该读取 K 线
        False: 不是闭合时刻，继续等待
    """
    now = datetime.now()

    # 15m: XX:14:59, XX:29:59, XX:44:59, XX:59:59
    if timeframe == "15m":
        return (now.minute + 1) % 15 == 0 and now.second == 59

    # 1h: XX:59:59
    if timeframe == "1h":
        return now.minute == 59 and now.second == 59

    # 4h: 03:59:59, 07:59:59, 11:59:59, ...
    if timeframe == "4h":
        return (now.hour + 1) % 4 == 0 and now.minute == 59 and now.second == 59

    return False


def is_kline_closed(kline_timestamp: int, timeframe: str) -> bool:
    """验证 K 线是否已闭合

    Args:
        kline_timestamp: K 线开盘时间戳（毫秒）
        timeframe: 周期

    Returns:
        True: K 线已闭合
        False: K 线未闭合
    """
    minutes = TIMEFRAME_MINUTES.get(timeframe, 60)
    kline_end_time = kline_timestamp + (minutes * 60 * 1000)
    current_time = int(time.time() * 1000)
    return current_time >= kline_end_time
