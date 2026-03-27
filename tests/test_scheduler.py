"""Scheduler 模块单元测试"""
import pytest
from unittest.mock import patch
from datetime import datetime
import time
from scheduler import is_kline_close_time, is_kline_closed, TIMEFRAME_MINUTES


class TestIsKlineCloseTime:
    """测试 K 线闭合时刻判断"""

    @patch('scheduler.datetime')
    def test_15m_close_time(self, mock_dt):
        """15m 周期在 XX:14:59 返回 True"""
        mock_dt.now.return_value = datetime(2026, 3, 27, 13, 14, 59)
        assert is_kline_close_time("15m") is True

    @patch('scheduler.datetime')
    def test_15m_not_close_time(self, mock_dt):
        """15m 周期在 XX:15:00 返回 False"""
        mock_dt.now.return_value = datetime(2026, 3, 27, 13, 15, 0)
        assert is_kline_close_time("15m") is False

    @patch('scheduler.datetime')
    def test_1h_close_time(self, mock_dt):
        """1h 周期在 XX:59:59 返回 True"""
        mock_dt.now.return_value = datetime(2026, 3, 27, 13, 59, 59)
        assert is_kline_close_time("1h") is True

    @patch('scheduler.datetime')
    def test_1h_not_close_time(self, mock_dt):
        """1h 周期在 XX:58:59 返回 False"""
        mock_dt.now.return_value = datetime(2026, 3, 27, 13, 58, 59)
        assert is_kline_close_time("1h") is False

    @patch('scheduler.datetime')
    def test_4h_close_time(self, mock_dt):
        """4h 周期在 03:59:59 返回 True"""
        mock_dt.now.return_value = datetime(2026, 3, 27, 3, 59, 59)
        assert is_kline_close_time("4h") is True

    @patch('scheduler.datetime')
    def test_4h_not_close_time(self, mock_dt):
        """4h 周期在 04:59:59 返回 False"""
        mock_dt.now.return_value = datetime(2026, 3, 27, 4, 59, 59)
        assert is_kline_close_time("4h") is False


class TestIsKlineClosed:
    """测试 K 线闭合验证"""

    def test_kline_closed(self):
        """K 线已闭合返回 True"""
        # 15 分钟前的 K 线
        kline_timestamp = int(time.time() * 1000) - (15 * 60 * 1000)
        assert is_kline_closed(kline_timestamp, "15m") is True

    def test_kline_not_closed(self):
        """K 线未闭合返回 False"""
        # 未来的 K 线时间戳
        kline_timestamp = int(time.time() * 1000) + (15 * 60 * 1000)
        assert is_kline_closed(kline_timestamp, "15m") is False
