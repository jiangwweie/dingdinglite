# K 线读取时机修复 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复 K 线读取时机问题，确保只在 K 线闭合时刻读取并验证，避免未闭合 K 线产生错误信号。

**Architecture:** 新增同步轮询调度器（scheduler.py），每秒检查是否到达周期闭合时刻，到达时读取 K 线并验证闭合，通过后传递给信号管道。

**Tech Stack:** Python 3.11+, asyncio, ccxt, pydantic

---

## 文件结构

| 文件 | 类型 | 职责 |
|------|------|------|
| `scheduler.py` | 新增 | 时间判断 + 闭合验证 + 轮询循环 |
| `lite.py` | 修改 | 移除旧轮询逻辑，集成 Scheduler |
| `tests/test_scheduler.py` | 新增 | Scheduler 单元测试 |
| `tests/test_lite.py` | 修改 | 集成测试更新 |

---

## Task 1: 创建 Scheduler 模块

**Files:**
- Create: `scheduler.py`
- Test: `tests/test_scheduler.py`

### 任务分解

- [ ] **Step 1: 创建 scheduler.py 骨架**

```python
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

```

- [ ] **Step 2: 编写 is_kline_close_time 测试**

```python
# tests/test_scheduler.py
import pytest
from unittest.mock import patch
from datetime import datetime
from scheduler import is_kline_close_time


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

```

- [ ] **Step 3: 编写 is_kline_closed 测试**

```python
# tests/test_scheduler.py (续)
import time
from scheduler import is_kline_closed


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

```

- [ ] **Step 4: 运行测试验证**

```bash
source venv/bin/activate
pytest tests/test_scheduler.py -v
```

Expected: 8 个测试全部通过

- [ ] **Step 5: 提交**

```bash
git add scheduler.py tests/test_scheduler.py
git commit -m "feat: add scheduler module for kline close time detection"
```

---

## Task 2: 重构 lite.py 主循环

**Files:**
- Modify: `lite.py:176-220` (subscribe_klines 方法), `lite.py:448-482` (main 函数循环部分)

### 任务分解

- [ ] **Step 1: 修改 subscribe_klines 为同步轮询模式**

```python
# lite.py - 替换原 subscribe_klines 方法 (约 176-216 行)
async def subscribe_klines(
    self,
    symbols: list,
    timeframes: list,
    callback
) -> None:
    """订阅 K 线数据（同步轮询模式）

    在每个周期的 K 线闭合时刻读取并验证，确保只处理已闭合 K 线。

    Args:
        symbols: 交易对列表
        timeframes: 周期列表
        callback: K 线数据回调函数，接收 KlineData 参数
    """
    from scheduler import is_kline_close_time, is_kline_closed

    self.logger.info("同步轮询调度器启动")

    while True:
        triggered = False

        # 检查每个周期是否到达闭合时刻
        for symbol in symbols:
            for timeframe in timeframes:
                if is_kline_close_time(timeframe):
                    try:
                        # 读取最近 2 根 K 线，使用前一根（确保已闭合）
                        ohlcv = await self.get_klines(symbol, timeframe, limit=2)

                        if len(ohlcv) < 2:
                            continue

                        # 使用倒数第二根 K 线（确保已闭合）
                        candle = ohlcv[-2]
                        kline_timestamp = int(candle[0])

                        # 验证闭合
                        if not is_kline_closed(kline_timestamp, timeframe):
                            self.logger.debug(
                                f"[{symbol}] {timeframe} K 线未闭合，跳过"
                            )
                            continue

                        # 构建 KlineData
                        kline = KlineData(
                            symbol=symbol,
                            timeframe=timeframe,
                            timestamp=kline_timestamp,
                            open=Decimal(str(candle[1])),
                            high=Decimal(str(candle[2])),
                            low=Decimal(str(candle[3])),
                            close=Decimal(str(candle[4])),
                            volume=Decimal(str(candle[5])),
                            is_closed=True
                        )

                        await callback(kline)
                        triggered = True

                    except Exception as e:
                        logging.getLogger("dingpang-lite").error(
                            f"获取 {symbol} {timeframe} K 线失败：{e}"
                        )

        # 如果没有触发任何周期，等待 1 秒
        if not triggered:
            await asyncio.sleep(1)

```

- [ ] **Step 2: 简化 main 函数循环部分**

```python
# lite.py - 修改 main 函数的循环部分 (约 448-482 行)
    # 5. 订阅 K 线
    logger.info(f"订阅 K 线：{config.symbols} ({', '.join(config.timeframes)})")

    # 定义 K 线回调
    async def on_kline_callback(kline: KlineData) -> None:
        await pipeline.on_kline(kline)

    # 6. 保持运行（同步轮询）
    try:
        logger.info("系统就绪，开始监控...")

        # 进入同步轮询循环
        await gateway.subscribe_klines(
            config.symbols,
            config.timeframes,
            on_kline_callback
        )

    except KeyboardInterrupt:
        logger.info("收到中断信号，正在关闭...")
```

- [ ] **Step 3: 移除不再需要的初始化 K 线获取逻辑**

删除原 main 函数中 450-473 行的初始化 K 线获取代码（已被调度器替代）

- [ ] **Step 4: 运行所有测试验证**

```bash
source venv/bin/activate
pytest tests/ -v
```

Expected: 所有测试通过（58 个）

- [ ] **Step 5: 本地运行验证**

```bash
source venv/bin/activate
timeout 30 python lite.py
```

Expected: 日志显示"同步轮询调度器启动"，然后等待闭合时刻

- [ ] **Step 6: 提交**

```bash
git add lite.py
git commit -m "refactor: use sync scheduler for kline polling"
```

---

## Task 3: 集成测试更新

**Files:**
- Modify: `tests/test_lite.py`

### 任务分解

- [ ] **Step 1: 添加 Scheduler 集成测试**

```python
# tests/test_lite.py - 新增测试类
class TestSchedulerIntegration:
    """测试调度器集成"""

    @patch('lite.is_kline_close_time')
    @patch('lite.ExchangeGateway.get_klines')
    @pytest.mark.asyncio
    async def test_signal_triggered_at_close_time(
        self, mock_get_klines, mock_is_close
    ):
        """验证信号在 K 线闭合时触发"""
        # Mock 闭合时刻
        mock_is_close.return_value = True

        # Mock K 线数据
        mock_get_klines.return_value = [
            [100000000000, 50000, 51000, 49000, 50500, 1000],  # 已闭合
            [100000900000, 50500, 51500, 50000, 51000, 1000],  # 未闭合
        ]

        # 调用 subscribe_klines 并验证
        # ... (详细实现)

```

- [ ] **Step 2: 运行新增测试**

```bash
source venv/bin/activate
pytest tests/test_lite.py::TestSchedulerIntegration -v
```

- [ ] **Step 3: 提交**

```bash
git add tests/test_lite.py
git commit -m "test: add scheduler integration tests"
```

---

## Task 4: 文档更新

**Files:**
- Modify: `README.md`

### 任务分解

- [ ] **Step 1: 更新 README 中的工作原理说明**

```markdown
## 工作原理

1. **同步轮询调度器** - 每秒检查时间，在 K 线闭合时刻（XX:14:59、XX:59:59）触发
2. **K 线读取** - 读取最近 2 根 K 线，使用前一根（确保已闭合）
3. **闭合验证** - 验证 K 线时间戳，过滤未闭合数据
4. **信号检测** - Pinbar 检测 + EMA 趋势判断
5. **飞书推送** - 产生信号时发送通知
```

- [ ] **Step 2: 提交**

```bash
git add README.md
git commit -m "docs: update architecture description"
```

---

## 验收标准

- [ ] `scheduler.py` 单元测试全部通过（8 个）
- [ ] 所有现有测试全部通过（58+ 个）
- [ ] 本地运行显示"同步轮询调度器启动"
- [ ] 日志显示在正确时刻触发 K 线读取
- [ ] 所有文件变更已提交到 git

---

*Plan created: 2026-03-27*
