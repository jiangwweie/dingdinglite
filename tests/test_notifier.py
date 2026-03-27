"""notifier.py 单元测试"""
import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, patch, MagicMock
import asyncio
import aiohttp

from models import Direction, SignalResult, Trend
from notifier import format_signal_message, send_feishu_notification


class TestFormatSignalMessage:
    """format_signal_message 测试"""

    def test_format_long_message(self):
        """格式化做多消息"""
        signal = SignalResult(
            symbol="BTC/USDT:USDT",
            timeframe="15m",
            direction=Direction.LONG,
            entry_price=Decimal("67850.00"),
            stop_loss=Decimal("67200.00"),
            big_trend=Trend.BULLISH,
            pinbar_quality=0.72,
            reason="1h 多头趋势 + 15m 看涨 Pinbar",
        )

        message = format_signal_message(signal)

        assert "🐶 盯盘狗 - Pinbar 信号" in message
        assert "BTC/USDT:USDT" in message
        assert "15m" in message
        assert "🟢" in message
        assert "做多" in message
        assert "$67,850.00" in message
        assert "$67,200.00" in message
        assert "1h EMA 多头" in message
        assert "盯盘狗 Lite v0.1.0" in message

    def test_format_short_message(self):
        """格式化做空消息"""
        signal = SignalResult(
            symbol="ETH/USDT:USDT",
            timeframe="1h",
            direction=Direction.SHORT,
            entry_price=Decimal("3500.00"),
            stop_loss=Decimal("3600.00"),
            big_trend=Trend.BEARISH,
            pinbar_quality=0.65,
            reason="1h 空头趋势 + 15m 看跌 Pinbar",
        )

        message = format_signal_message(signal)

        assert "🐶 盯盘狗 - Pinbar 信号" in message
        assert "ETH/USDT:USDT" in message
        assert "1h" in message
        assert "🔴" in message
        assert "做空" in message
        assert "$3,500.00" in message
        assert "$3,600.00" in message
        assert "1h EMA 空头" in message
        assert "盯盘狗 Lite v0.1.0" in message

    def test_message_contains_quality(self):
        """消息包含形态质量"""
        signal = SignalResult(
            symbol="BTC/USDT:USDT",
            timeframe="15m",
            direction=Direction.LONG,
            entry_price=Decimal("67850.00"),
            stop_loss=Decimal("67200.00"),
            big_trend=Trend.BULLISH,
            pinbar_quality=0.72,
            reason="1h 多头趋势 + 15m 看涨 Pinbar",
        )

        message = format_signal_message(signal)

        assert "72%" in message
        assert "形态质量" in message

    def test_message_contains_reason(self):
        """消息包含 reason"""
        signal = SignalResult(
            symbol="SOL/USDT:USDT",
            timeframe="15m",
            direction=Direction.LONG,
            entry_price=Decimal("150.00"),
            stop_loss=Decimal("145.00"),
            big_trend=Trend.BULLISH,
            pinbar_quality=0.80,
            reason="1h 多头趋势 + 15m 看涨 Pinbar 突破阻力位",
        )

        message = format_signal_message(signal)

        assert "reason:" in message
        assert "1h 多头趋势 + 15m 看涨 Pinbar 突破阻力位" in message


class TestSendNotification:
    """send_feishu_notification 测试"""

    @pytest.mark.asyncio
    async def test_send_feishu_success(self):
        """推送成功"""
        from aioresponses import aioresponses

        signal = SignalResult(
            symbol="BTC/USDT:USDT",
            timeframe="15m",
            direction=Direction.LONG,
            entry_price=Decimal("67850.00"),
            stop_loss=Decimal("67200.00"),
            big_trend=Trend.BULLISH,
            pinbar_quality=0.72,
            reason="1h 多头趋势 + 15m 看涨 Pinbar",
        )

        webhook_url = "https://open.feishu.cn/webhook/test"

        with aioresponses() as m:
            m.post(webhook_url, status=200, payload={"code": 0})

            result = await send_feishu_notification(signal, webhook_url, timeout=10)

        assert result is True

    @pytest.mark.asyncio
    async def test_send_feishu_failure(self):
        """推送失败（网络错误）"""
        signal = SignalResult(
            symbol="BTC/USDT:USDT",
            timeframe="15m",
            direction=Direction.LONG,
            entry_price=Decimal("67850.00"),
            stop_loss=Decimal("67200.00"),
            big_trend=Trend.BULLISH,
            pinbar_quality=0.72,
            reason="1h 多头趋势 + 15m 看涨 Pinbar",
        )

        with patch("notifier.aiohttp.ClientSession") as mock_session_class:
            mock_session_class.side_effect = aiohttp.ClientError("Network error")

            result = await send_feishu_notification(
                signal, "https://open.feishu.cn/webhook/test", timeout=10
            )

        assert result is False

    @pytest.mark.asyncio
    async def test_send_feishu_timeout(self):
        """推送超时"""
        signal = SignalResult(
            symbol="BTC/USDT:USDT",
            timeframe="15m",
            direction=Direction.LONG,
            entry_price=Decimal("67850.00"),
            stop_loss=Decimal("67200.00"),
            big_trend=Trend.BULLISH,
            pinbar_quality=0.72,
            reason="1h 多头趋势 + 15m 看涨 Pinbar",
        )

        with patch("notifier.aiohttp.ClientSession") as mock_session_class:
            mock_session_class.side_effect = asyncio.TimeoutError()

            result = await send_feishu_notification(
                signal, "https://open.feishu.cn/webhook/test", timeout=10
            )

        assert result is False


# 导入 aiohttp 用于异常模拟
import aiohttp
