"""Lite 版数据模型"""
from decimal import Decimal
from enum import Enum
from typing import List
from pydantic import BaseModel, Field, field_validator


class Direction(str, Enum):
    """交易方向"""
    LONG = "LONG"     # 做多
    SHORT = "SHORT"   # 做空


class Trend(str, Enum):
    """趋势方向"""
    BULLISH = "Bullish"
    BEARISH = "Bearish"
    NEUTRAL = "Neutral"


class KlineData(BaseModel):
    """K 线数据"""
    symbol: str           # "BTC/USDT:USDT"
    timeframe: str        # "15m" or "1h" or "4h"
    timestamp: int        # 毫秒时间戳
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    is_closed: bool       # K 线是否已闭合


class SignalResult(BaseModel):
    """信号结果"""
    symbol: str
    timeframe: str
    direction: Direction
    entry_price: Decimal
    stop_loss: Decimal
    big_trend: Trend
    pinbar_quality: float   # 0~1
    reason: str = ""        # 如 "1h 多头趋势 + 15m 看涨 Pinbar"

    def __str__(self) -> str:
        direction_text = "做多" if self.direction == Direction.LONG else "做空"
        trend_text = "多头" if self.big_trend == Trend.BULLISH else "空头" if self.big_trend == Trend.BEARISH else "中性"
        return (
            f"【{self.symbol}】{direction_text}\n"
            f"周期：{self.timeframe}\n"
            f"入场价：${float(self.entry_price):,.2f}\n"
            f"止损价：${float(self.stop_loss):,.2f}\n"
            f"大周期趋势：{trend_text}\n"
            f"形态质量：{self.pinbar_quality:.0%}\n"
            f"原因：{self.reason}"
        )


class ExchangeConfig(BaseModel):
    """交易所配置"""
    name: str = "binance"
    api_key: str
    api_secret: str
    testnet: bool = False


class PinbarConfig(BaseModel):
    """Pinbar 参数配置"""
    min_wick_ratio: float = 0.6
    max_body_ratio: float = 0.3


class StrategyConfig(BaseModel):
    """策略配置"""
    ema_period: int = 60
    pinbar: PinbarConfig = Field(default_factory=PinbarConfig)


class LogConfig(BaseModel):
    """日志配置"""
    level: str = "INFO"
    file: str = "logs/lite.log"
    format: str = "%(asctime)s %(levelname)s  %(message)s"


class NotificationConfig(BaseModel):
    """通知配置"""
    feishu_webhook: str


class LiteConfig(BaseModel):
    """Lite 版完整配置"""
    exchange: ExchangeConfig
    symbols: List[str]
    timeframes: List[str]
    strategy: StrategyConfig = Field(default_factory=StrategyConfig)
    notification: NotificationConfig
    logging: LogConfig = Field(default_factory=LogConfig)

    @field_validator("symbols")
    @classmethod
    def validate_symbols(cls, v: List[str]) -> List[str]:
        if len(v) < 1:
            raise ValueError("symbols 至少需要 1 个币种")
        return v

    @field_validator("timeframes")
    @classmethod
    def validate_timeframes(cls, v: List[str]) -> List[str]:
        if len(v) < 1:
            raise ValueError("timeframes 至少需要 1 个周期")
        allowed = {"15m", "1h", "4h"}
        for tf in v:
            if tf not in allowed:
                raise ValueError(f"timeframes 只能包含 {allowed}，得到：{tf}")
        return v
