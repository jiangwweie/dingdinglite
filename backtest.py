"""Pinbar 策略回测脚本 - ETH/USDT 1h 级别"""
import asyncio
import json
import csv
import datetime
from decimal import Decimal
from typing import Optional
from dataclasses import dataclass, asdict

import ccxt.async_support as ccxt

from strategy import (
    is_bullish_pinbar,
    is_bearish_pinbar,
    calculate_wick_ratio,
    calculate_stop_loss,
)
from models import KlineData, Direction


# =============================================================================
# 配置
# =============================================================================

SYMBOL = "ETH/USDT:USDT"
TIMEFRAME = "1h"
HIGHER_TIMEFRAME = "4h"  # 趋势判断周期
EMA_PERIOD = 60
DAYS_TO_BACKTEST = 7
STOP_LOSS_PCT = 0.003  # 0.3%

# 输出文件
REPORT_JSON = f"backtest_report_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
REPORT_CSV = f"backtest_report_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"


# =============================================================================
# 数据类
# =============================================================================

@dataclass
class Signal:
    """回测信号记录"""
    timestamp: str
    direction: str
    entry_price: float
    exit_price: float
    stop_loss: float
    pnl: float
    win: bool
    pinbar_quality: float
    exit_reason: str = ""


@dataclass
class Summary:
    """回测摘要"""
    symbol: str
    timeframe: str
    higher_timeframe: str
    start_time: str
    end_time: str
    total_signals: int
    long_signals: int
    short_signals: int
    wins: int
    losses: int
    win_rate: float
    avg_pnl: float
    total_pnl: float
    max_drawdown: float
    avg_winner: float
    avg_loser: float
    exit_take_profit: int = 0
    exit_stop_loss: int = 0
    exit_other: int = 0


# =============================================================================
# 数据获取
# =============================================================================

async def fetch_klines(
    exchange: ccxt.binance,
    symbol: str,
    timeframe: str,
    days: int,
    limit: int = 1000
) -> list:
    """获取历史 K 线数据

    Args:
        exchange: 交易所实例
        symbol: 交易对
        timeframe: 周期
        days: 获取天数
        limit: 最大数量

    Returns:
        K 线数据列表 [timestamp, open, high, low, close, volume]
    """
    since = int((datetime.datetime.now() - datetime.timedelta(days=days)).timestamp() * 1000)

    print(f"[数据获取] 从 {datetime.datetime.fromtimestamp(since/1000)} 开始获取 {symbol} {timeframe} 数据...")

    ohlcv = await exchange.fetch_ohlcv(symbol, timeframe, since=since, limit=limit)

    print(f"[数据获取] 获取到 {len(ohlcv)} 根 K 线")
    return ohlcv


# =============================================================================
# EMA 计算
# =============================================================================

def calculate_ema(prices: list[Decimal], period: int) -> Decimal:
    """计算 EMA 值

    Args:
        prices: 收盘价列表
        period: EMA 周期

    Returns:
        EMA 值
    """
    if len(prices) < period:
        raise ValueError(f"数据不足：需要{period}个，实际{len(prices)}个")

    k = Decimal("2") / Decimal(str(period + 1))

    # 第一个 EMA 用 SMA 近似
    ema = sum(prices[:period]) / Decimal(str(period))

    # 迭代计算后续 EMA
    for price in prices[period:]:
        ema = price * k + ema * (Decimal("1") - k)

    return ema


# =============================================================================
# 回测逻辑
# =============================================================================

class Backtester:
    """回测引擎"""

    def __init__(self, symbol: str, timeframe: str, higher_timeframe: str):
        self.symbol = symbol
        self.timeframe = timeframe
        self.higher_timeframe = higher_timeframe
        self.signals: list[Signal] = []

        # 上下文缓存
        self.higher_ema: Optional[Decimal] = None
        self.higher_close: Optional[Decimal] = None

    def update_higher_context(self, klines_4h: list, ema_period: int) -> None:
        """更新高周期上下文（4h EMA 和收盘价）"""
        if len(klines_4h) < ema_period + 1:
            return

        # 使用已闭合的 K 线（倒数第二根）
        recent_klines = klines_4h[-(ema_period + 1):-1]
        close_prices = [Decimal(str(k[4])) for k in recent_klines]

        self.higher_close = Decimal(str(klines_4h[-2][4]))
        self.higher_ema = calculate_ema(close_prices, ema_period)

    def check_signal(self, kline: list) -> Optional[tuple[Direction, float, float]]:
        """检查是否产生信号

        Args:
            kline: K 线数据 [timestamp, open, high, low, close, volume]

        Returns:
            (Direction, entry_price, stop_loss) 或 None
        """
        if self.higher_ema is None or self.higher_close is None:
            return None

        # 构建 KlineData
        kline_data = KlineData(
            symbol=self.symbol,
            timeframe=self.timeframe,
            timestamp=int(kline[0]),
            open=Decimal(str(kline[1])),
            high=Decimal(str(kline[2])),
            low=Decimal(str(kline[3])),
            close=Decimal(str(kline[4])),
            volume=Decimal(str(kline[5])),
            is_closed=True
        )

        # 判断大周期趋势
        big_trend = "BULLISH" if self.higher_close >= self.higher_ema else "BEARISH"

        # 顺大逆小检测
        direction = None
        if big_trend == "BULLISH":
            if is_bullish_pinbar(kline_data, min_wick=0.5, max_body=0.35, body_position_tolerance=0.3):
                direction = Direction.LONG
        else:
            if is_bearish_pinbar(kline_data, min_wick=0.5, max_body=0.35, body_position_tolerance=0.3):
                direction = Direction.SHORT

        if direction is None:
            return None

        # 计算止损价
        stop_loss = calculate_stop_loss(kline_data, direction)

        # 计算形态质量
        upper_ratio, lower_ratio, _ = calculate_wick_ratio(kline_data)
        quality = float(lower_ratio) if direction == Direction.LONG else float(upper_ratio)

        entry_price = float(kline_data.close)
        stop_loss_price = float(stop_loss)

        return (direction, entry_price, stop_loss_price, quality)

    def calculate_pnl(
        self,
        direction: Direction,
        entry_price: float,
        high_price: float,
        low_price: float,
        take_profit_pct: float = 1.5
    ) -> tuple[float, bool, str]:
        """计算盈亏（固定盈亏比出场）

        Args:
            direction: 方向
            entry_price: 入场价
            high_price: 持仓期间最高价
            low_price: 持仓期间最低价
            take_profit_pct: 止盈倍数（止损距离的倍数）

        Returns:
            (pnl, win, exit_reason) pnl 为收益率，win 为是否盈利，exit_reason 为出场原因
        """
        if direction == Direction.LONG:
            stop_loss = low_price  # Pinbar 最低价
            risk = entry_price - stop_loss
            take_profit = entry_price + risk * take_profit_pct

            # 检查是否触发止损
            if low_price <= stop_loss:
                pnl = (stop_loss - entry_price) / entry_price
                return (pnl, False, "止损")
            # 检查是否触发止盈
            elif high_price >= take_profit:
                pnl = (take_profit - entry_price) / entry_price
                return (pnl, True, "止盈")
            else:
                # 未触发止盈止损，假设最终平仓
                pnl = (low_price - entry_price) / entry_price
                return (pnl, False, "未止盈")
        else:  # SHORT
            stop_loss = high_price  # Pinbar 最高价
            risk = stop_loss - entry_price
            take_profit = entry_price - risk * take_profit_pct

            # 检查是否触发止损
            if high_price >= stop_loss:
                pnl = (entry_price - stop_loss) / entry_price
                return (pnl, False, "止损")
            # 检查是否触发止盈
            elif low_price <= take_profit:
                pnl = (entry_price - take_profit) / entry_price
                return (pnl, True, "止盈")
            else:
                # 未触发止盈止损
                pnl = (entry_price - high_price) / entry_price
                return (pnl, False, "未止盈")

    async def run(self, exchange: ccxt.binance, bars_to_exit: int = 3) -> None:
        """运行回测

        Args:
            exchange: 交易所实例
            bars_to_exit: 持有 K 线根数后出场（默认 3 根）
        """
        print(f"\n{'='*60}")
        print(f"回测：{self.symbol} {self.timeframe}")
        print(f"趋势判断周期：{self.higher_timeframe} EMA({EMA_PERIOD})")
        print(f"止盈倍数：1.5R (盈亏比 1.5:1)")
        print(f"出场方式：持有{bars_to_exit}根 K 线 或 触发止盈/止损")
        print(f"{'='*60}\n")

        # 获取 1h 和 4h 数据
        klines_1h = await fetch_klines(exchange, self.symbol, self.timeframe, DAYS_TO_BACKTEST)
        klines_4h = await fetch_klines(exchange, self.symbol, self.higher_timeframe, DAYS_TO_BACKTEST + 10)

        if len(klines_1h) < 10:
            print("[错误] 1h K 线数据不足")
            return

        if len(klines_4h) < EMA_PERIOD + 10:
            print(f"[错误] 4h K 线数据不足，需要至少{EMA_PERIOD + 10}根")
            return

        print(f"\n[回测] 开始处理 {len(klines_1h)} 根 1h K 线...\n")

        # 遍历每根 1h K 线（跳过前 60 根，等待 EMA 稳定）
        for i in range(EMA_PERIOD, len(klines_1h) - bars_to_exit):
            kline = klines_1h[i]

            # 更新 4h 上下文
            self.update_higher_context(klines_4h, EMA_PERIOD)

            # 检查信号
            result = self.check_signal(kline)
            if result is None:
                continue

            direction, entry_price, pinbar_stop, quality = result

            # 获取持有期间的最高/最低价
            hold_klines = klines_1h[i + 1:i + 1 + bars_to_exit]
            hold_high = max(float(k[2]) for k in hold_klines)
            hold_low = min(float(k[3]) for k in hold_klines)

            # 计算盈亏
            pnl, win, exit_reason = self.calculate_pnl(
                direction, entry_price, hold_high, hold_low, take_profit_pct=1.5
            )

            # 计算实际止损/止盈价
            if direction == Direction.LONG:
                risk = entry_price - pinbar_stop
                take_profit = entry_price + risk * 1.5
                actual_exit = pinbar_stop if exit_reason == "止损" else (take_profit if exit_reason == "止盈" else hold_low)
            else:
                risk = pinbar_stop - entry_price
                take_profit = entry_price - risk * 1.5
                actual_exit = pinbar_stop if exit_reason == "止损" else (take_profit if exit_reason == "止盈" else hold_high)

            # 记录信号
            signal = Signal(
                timestamp=datetime.datetime.fromtimestamp(kline[0]/1000).isoformat(),
                direction=direction.value,
                entry_price=entry_price,
                exit_price=actual_exit,
                stop_loss=pinbar_stop,
                pnl=pnl,
                win=win,
                pinbar_quality=quality,
                exit_reason=exit_reason
            )
            self.signals.append(signal)

            # 打印信号
            arrow = "🟢" if direction == Direction.LONG else "🔴"
            result_icon = "✓" if win else "✗"
            print(f"  [{result_icon}] {arrow} {signal.timestamp} "
                  f"{direction.value} @ {entry_price:.2f} → {actual_exit:.2f} "
                  f"PnL: {pnl:+.4f} ({pnl*100:+.2f}%) [{exit_reason}]")

    def generate_summary(self) -> Summary:
        """生成回测摘要"""
        if not self.signals:
            return Summary(
                symbol=self.symbol,
                timeframe=self.timeframe,
                higher_timeframe=self.higher_timeframe,
                start_time="",
                end_time="",
                total_signals=0,
                long_signals=0,
                short_signals=0,
                wins=0,
                losses=0,
                win_rate=0.0,
                avg_pnl=0.0,
                total_pnl=0.0,
                max_drawdown=0.0,
                avg_winner=0.0,
                avg_loser=0.0
            )

        wins = [s for s in self.signals if s.win]
        losses = [s for s in self.signals if not s.win]
        longs = [s for s in self.signals if s.direction == "LONG"]
        shorts = [s for s in self.signals if s.direction == "SHORT"]

        # 统计出场原因
        exit_take_profit = len([s for s in self.signals if s.exit_reason == "止盈"])
        exit_stop_loss = len([s for s in self.signals if s.exit_reason == "止损"])
        exit_other = len([s for s in self.signals if s.exit_reason == "未止盈"])

        # 计算最大回撤（连续亏损）
        max_drawdown = 0.0
        current_drawdown = 0.0
        for s in self.signals:
            if not s.win:
                current_drawdown += abs(s.pnl)
                max_drawdown = max(max_drawdown, current_drawdown)
            else:
                current_drawdown = 0.0

        return Summary(
            symbol=self.symbol,
            timeframe=self.timeframe,
            higher_timeframe=self.higher_timeframe,
            start_time=self.signals[0].timestamp if self.signals else "",
            end_time=self.signals[-1].timestamp if self.signals else "",
            total_signals=len(self.signals),
            long_signals=len(longs),
            short_signals=len(shorts),
            wins=len(wins),
            losses=len(losses),
            win_rate=len(wins) / len(self.signals) if self.signals else 0.0,
            avg_pnl=sum(s.pnl for s in self.signals) / len(self.signals) if self.signals else 0.0,
            total_pnl=sum(s.pnl for s in self.signals),
            max_drawdown=-max_drawdown,
            avg_winner=sum(s.pnl for s in wins) / len(wins) if wins else 0.0,
            avg_loser=sum(s.pnl for s in losses) / len(losses) if losses else 0.0,
            exit_take_profit=exit_take_profit,
            exit_stop_loss=exit_stop_loss,
            exit_other=exit_other
        )


# =============================================================================
# 报告输出
# =============================================================================

def save_report(summary: Summary, signals: list[Signal], json_path: str, csv_path: str) -> None:
    """保存回测报告

    Args:
        summary: 摘要
        signals: 信号列表
        json_path: JSON 输出路径
        csv_path: CSV 输出路径
    """
    # JSON 报告
    report_data = {
        "summary": asdict(summary),
        "signals": [asdict(s) for s in signals]
    }

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(report_data, f, indent=2, ensure_ascii=False)

    print(f"\n[报告] JSON 报告已保存：{json_path}")

    # CSV 报告
    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["timestamp", "direction", "entry_price", "exit_price", "stop_loss", "pnl", "win", "pinbar_quality", "exit_reason"])
        for s in signals:
            writer.writerow([
                s.timestamp,
                s.direction,
                s.entry_price,
                s.exit_price,
                s.stop_loss,
                s.pnl,
                s.win,
                s.pinbar_quality,
                s.exit_reason
            ])

    print(f"[报告] CSV 报告已保存：{csv_path}")


def print_summary(summary: Summary) -> None:
    """打印回测摘要"""
    print(f"\n{'='*60}")
    print("回测摘要")
    print(f"{'='*60}")
    print(f"交易对：    {summary.symbol}")
    print(f"周期：      {summary.timeframe} (趋势判断：{summary.higher_timeframe})")
    print(f"时间范围：  {summary.start_time} ~ {summary.end_time}")
    print()
    print(f"总信号数：  {summary.total_signals}")
    print(f"  - 做多：  {summary.long_signals}")
    print(f"  - 做空：  {summary.short_signals}")
    print()
    print(f"盈利次数：  {summary.wins}")
    print(f"亏损次数：  {summary.losses}")
    print(f"胜率：      {summary.win_rate:.1%}")
    print()
    print(f"平均盈亏：  {summary.avg_pnl:+.4f} ({summary.avg_pnl*100:+.2f}%)")
    print(f"总盈亏：    {summary.total_pnl:+.4f} ({summary.total_pnl*100:+.2f}%)")
    print(f"最大回撤：  {summary.max_drawdown:.4f} ({summary.max_drawdown*100:.2f}%)")
    print()
    print(f"平均盈利：  {summary.avg_winner:+.4f} ({summary.avg_winner*100:+.2f}%)")
    print(f"平均亏损：  {summary.avg_loser:.4f} ({summary.avg_loser*100:.2f}%)")
    if summary.avg_loser != 0:
        print(f"盈亏比：    {abs(summary.avg_winner / summary.avg_loser):.2f}")
    print()
    print(f"出场原因统计:")
    print(f"  - 止盈：  {summary.exit_take_profit} ({summary.exit_take_profit/summary.total_signals*100:.1f}%)" if summary.total_signals > 0 else "")
    print(f"  - 止损：  {summary.exit_stop_loss} ({summary.exit_stop_loss/summary.total_signals*100:.1f}%)" if summary.total_signals > 0 else "")
    print(f"  - 未触达：{summary.exit_other} ({summary.exit_other/summary.total_signals*100:.1f}%)" if summary.total_signals > 0 else "")
    print(f"{'='*60}\n")


# =============================================================================
# 主函数
# =============================================================================

async def main() -> None:
    """主函数"""
    print(f"\n{'#'*60}")
    print("# Pinbar 策略回测 - ETH/USDT 1h")
    print("#" * 60)

    # 初始化交易所
    exchange = ccxt.binance({
        "enableRateLimit": True,
        "options": {
            "defaultType": "future"
        }
    })

    try:
        # 加载市场数据
        await exchange.load_markets()
        print(f"[交易所] 已连接 Binance 合约\n")

        # 运行回测
        backtester = Backtester(SYMBOL, TIMEFRAME, HIGHER_TIMEFRAME)
        await backtester.run(exchange)

        # 生成摘要
        summary = backtester.generate_summary()

        # 打印摘要
        print_summary(summary)

        # 保存报告
        save_report(summary, backtester.signals, REPORT_JSON, REPORT_CSV)

    except Exception as e:
        print(f"[错误] 回测失败：{e}")
        raise
    finally:
        await exchange.close()


if __name__ == "__main__":
    asyncio.run(main())
