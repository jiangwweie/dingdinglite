"""飞书通知推送模块"""
import asyncio
import logging
from typing import Optional

import aiohttp

from models import Direction, SignalResult, Trend

logger = logging.getLogger(__name__)


def format_signal_message(signal: SignalResult) -> str:
    """格式化信号通知消息

    Args:
        signal: 信号结果

    Returns:
        Markdown 格式的消息文本
    """
    # 方向图标
    if signal.direction == Direction.LONG:
        direction_icon = "🟢"
        direction_text = "做多"
    else:
        direction_icon = "🔴"
        direction_text = "做空"

    # 大周期趋势文字
    if signal.big_trend == Trend.BULLISH:
        trend_text = "1h EMA 多头"
    elif signal.big_trend == Trend.BEARISH:
        trend_text = "1h EMA 空头"
    else:
        trend_text = "1h EMA 中性"

    # 格式化价格（带千分位和 2 位小数）
    entry_price = f"${float(signal.entry_price):,.2f}"
    stop_loss = f"${float(signal.stop_loss):,.2f}"

    # 形态质量百分比
    quality_percent = f"{signal.pinbar_quality:.0%}"

    message = f"""🐶 盯盘狗 - Pinbar 信号

币种：{signal.symbol}
周期：{signal.timeframe}
方向：{direction_icon} {direction_text}
入场价：{entry_price}
止损价：{stop_loss}

大周期趋势：{trend_text}
形态质量：{quality_percent}
reason: {signal.reason}

---
盯盘狗 Lite v0.1.0"""

    return message


async def send_feishu_notification(
    signal: SignalResult,
    webhook_url: str,
    timeout: int = 10
) -> bool:
    """发送飞书通知

    Args:
        signal: 信号结果
        webhook_url: 飞书 Webhook URL
        timeout: 请求超时（秒）

    Returns:
        True: 发送成功
        False: 发送失败（不抛异常，仅记录日志）
    """
    message = format_signal_message(signal)

    payload = {
        "msg_type": "text",
        "content": {
            "text": message
        }
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                webhook_url,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=timeout)
            ) as response:
                if response.status == 200:
                    logger.info("飞书通知发送成功")
                    return True
                else:
                    logger.error(f"飞书通知发送失败，状态码：{response.status}")
                    return False
    except asyncio.TimeoutError:
        logger.error(f"飞书通知发送超时（{timeout}秒）")
        return False
    except Exception as e:
        logger.error(f"飞书通知发送失败：{e}")
        return False
