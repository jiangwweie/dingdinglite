# K 线读取时机修复设计

**创建日期**: 2026-03-27
**版本**: v0.1.1
**状态**: 已批准

---

## 问题描述

当前轮询模式每 5 秒读取一次 K 线，无法保证在 K 线闭合时刻读取，导致：

1. **未闭合 K 线信号无效** - Pinbar 检测需要完整的 OHLC 数据
2. **错过信号** - 如果在 13:16 读取，已经是下一根 K 线了
3. **趋势判断错误** - EMA 计算基于未闭合 K 线会失真

### 具体场景

```
15m K 线周期：
  13:00-13:14 的 K 线 → 需要在 13:14:59 读取（已闭合）
  当前可能在 13:05、13:10、13:15 读取 → 都是错误的时机

1h K 线周期：
  13:00-13:59 的 K 线 → 需要在 13:59:59 读取（已闭合）
  当前可能在 13:30、13:45 读取 → K 线未闭合，信号无效
```

---

## 设计目标

1. **精确时机** - 在每个周期的 K 线闭合时刻（XX:14:59、XX:59:59）读取
2. **多周期独立** - 15m/1h/4h 各自在闭合时刻检查
3. **闭合验证** - 读取后用 timestamp 验证 K 线确实已闭合

---

## 架构设计

### 整体流程

```
┌─────────────────────────────────────────────────────────────┐
│                    同步轮询调度器                            │
├─────────────────────────────────────────────────────────────┤
│  每秒钟检查：当前时间是否到达目标周期的闭合时刻                │
│  - 15m: XX:14:59, XX:29:59, XX:44:59, XX:59:59              │
│  - 1h:  XX:59:59                                            │
│  - 4h:  03:59:59, 07:59:59, 11:59:59, ...                   │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                    K 线读取器                                 │
│  卡点时刻读取最新一根 K 线 → 验证 timestamp 是否已闭合          │
│  如果已闭合：传递给信号检查管道                              │
│  如果未闭合：跳过，等待下一轮                                │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                    信号检查管道 (不变)                        │
│  趋势判断 → Pinbar 检测 → 冷却检查 → 飞书推送                │
└─────────────────────────────────────────────────────────────┘
```

### 核心模块

```
lite.py (重构后)
├── Scheduler (新增)
│   ├── is_kline_close_time() - 判断是否是闭合时刻
│   └── run_sync_loop() - 同步轮询主循环
│
├── KlineReader (新增)
│   ├── fetch_latest_kline() - 读取最新 K 线
│   └── validate_kline_closed() - 验证 K 线已闭合
│
├── SignalPipeline (不变)
│   ├── on_kline() - K 线处理入口
│   ├── _check_signal() - 信号检查
│   └── _notify_signal() - 飞书推送
│
└── ExchangeGateway (简化)
    └── get_klines() - 获取 K 线数据
```

---

## 详细设计

### 1. 周期常量定义

```python
# 周期映射（写死）
HIGHER_TIMEFRAME_MAP = {
    "15m": "1h",
    "1h": "4h",
    "4h": "1d"
}

# 周期分钟数
TIMEFRAME_MINUTES = {
    "15m": 15,
    "1h": 60,
    "4h": 240,
}

# 周期闭合时刻配置
CLOSE_TIME_CONFIG = {
    # 15m: 每 15 分钟的最后一秒 (14:59, 29:59, 44:59, 59:59)
    "15m": {"minute_offset": 14, "second": 59},
    # 1h: 每小时的最后一秒 (59:59)
    "1h": {"minute_offset": 59, "second": 59},
    # 4h: 每 4 小时的最后一秒 (03:59, 07:59, 11:59, ...)
    "4h": {"minute_offset": 59, "second": 59, "hour_mod": 4},
}
```

### 2. 调度器 - 判断闭合时刻

```python
def is_kline_close_time(timeframe: str) -> bool:
    """判断当前时间是否是指定周期的 K 线闭合时刻

    Args:
        timeframe: 周期，如 "15m", "1h", "4h"

    Returns:
        True: 当前是闭合时刻，应该读取 K 线
        False: 不是闭合时刻，继续等待
    """
    now = datetime.now()
    config = CLOSE_TIME_CONFIG.get(timeframe)
    if not config:
        return False

    # 检查秒数
    if now.second != config["second"]:
        return False

    # 检查分钟
    if now.minute != config["minute_offset"]:
        # 对于 15m，检查是否是 14, 29, 44, 59
        if timeframe == "15m":
            if (now.minute + 1) % 15 != 0:
                return False
        else:
            return False

    # 对于 4h，检查小时
    if "hour_mod" in config:
        if (now.hour + 1) % config["hour_mod"] != 0:
            return False

    return True
```

### 3. K 线闭合验证

```python
def is_kline_closed(kline_timestamp: int, timeframe: str) -> bool:
    """验证 K 线是否已闭合

    Args:
        kline_timestamp: K 线开盘时间戳（毫秒）
        timeframe: 周期

    Returns:
        True: K 线已闭合
        False: K 线未闭合
    """
    # 计算 K 线应该闭合的时间
    minutes = TIMEFRAME_MINUTES.get(timeframe, 60)
    kline_end_time = kline_timestamp + (minutes * 60 * 1000)

    # 当前时间
    current_time = int(time.time() * 1000)

    # 当前时间 >= K 线闭合时间，说明已闭合
    return current_time >= kline_end_time
```

### 4. 主循环逻辑

```python
async def run_sync_loop(self) -> None:
    """同步轮询主循环"""
    self.logger.info("同步轮询调度器启动")

    while True:
        now = datetime.now()
        triggered = False

        # 检查每个周期是否到达闭合时刻
        for timeframe in self.config.timeframes:
            if is_kline_close_time(timeframe):
                # 到达闭合时刻，读取 K 线
                await self._fetch_and_check(timeframe)
                triggered = True

        # 如果没有触发任何周期，等待 1 秒
        if not triggered:
            await asyncio.sleep(1)

    async def _fetch_and_check(self, timeframe: str) -> None:
        """读取 K 线并验证闭合"""
        for symbol in self.config.symbols:
            try:
                # 读取最新两根 K 线（最后一根可能未闭合，前一根一定已闭合）
                ohlcv = await self.gateway.get_klines(symbol, timeframe, limit=2)

                if len(ohlcv) < 2:
                    continue

                # 使用前一根 K 线（确保已闭合）
                candle = ohlcv[-2]  # 倒数第二根
                kline_timestamp = int(candle[0])

                # 验证闭合
                if not is_kline_closed(kline_timestamp, timeframe):
                    self.logger.debug(f"[{symbol}] {timeframe} K 线未闭合，跳过")
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

                # 传递给信号管道
                await self.pipeline.on_kline(kline)

            except Exception as e:
                self.logger.error(f"[{symbol}] {timeframe} 读取 K 线失败：{e}")
```

### 5. 更高周期数据获取

```python
async def init_higher_context(self) -> None:
    """初始化更高周期上下文（启动时调用一次）"""
    for symbol in self.config.symbols:
        for timeframe in self.config.timeframes:
            higher_tf = HIGHER_TIMEFRAME_MAP.get(timeframe)
            if not higher_tf:
                continue

            try:
                # 获取足够数据计算 EMA
                ohlcv = await self.gateway.get_klines(
                    symbol, higher_tf,
                    limit=self.config.strategy.ema_period + 10
                )

                # 使用已闭合的 K 线计算 EMA
                if len(ohlcv) >= self.config.strategy.ema_period:
                    # 更新上下文
                    await self.pipeline._update_context_from_ohlcv(
                        symbol, higher_tf, ohlcv
                    )
            except Exception as e:
                self.logger.error(f"初始化 {symbol} {higher_tf} 上下文失败：{e}")
```

---

## 数据流

```
时间到达 13:14:59
       │
       ▼
is_kline_close_time("15m") → True
       │
       ▼
fetch_latest_klines("BTC/USDT:USDT", "15m", limit=2)
       │
       ▼
获取两根 K 线：
  [0] 12:45-13:00 (已闭合)
  [1] 13:00-13:15 (可能未闭合)
       │
       ▼
选择 ohlcv[-2] = 12:45-13:00 这根
       │
       ▼
is_kline_closed(timestamp, "15m") → True ✓
       │
       ▼
构建 KlineData(is_closed=True)
       │
       ▼
pipeline.on_kline(kline)
       │
       ├──► _update_context() - 如果是更高周期
       │
       └──► _check_signal() - 检测 Pinbar 信号
              │
              ├──► check_pinbar_signal() - 策略判断
              │
              └──► send_feishu_notification() - 发送通知
```

---

## 错误处理

| 错误场景 | 处理方案 |
|---------|---------|
| API 请求失败 | 记录日志，等待下一轮（1 秒后）重试 |
| K 线数据不足 | 跳过，等待数据累积 |
| 时钟不同步 | 依赖交易所返回的 timestamp 验证 |
| 网络延迟 | 闭合验证会过滤掉未闭合的 K 线 |
| 重复触发 | 冷却时间机制防止重复推送 |

---

## 测试策略

### 单元测试

```python
# test_scheduler.py
def test_is_kline_close_time_15m():
    # 13:14:59 → True
    # 13:14:58 → False
    # 13:15:00 → False

def test_is_kline_close_time_1h():
    # 13:59:59 → True
    # 13:58:59 → False

def test_is_kline_closed():
    # K 线已结束 → True
    # K 线进行中 → False
```

### 集成测试

```python
# test_integration.py
async def test_signal_triggered_at_close_time():
    """验证信号只在 K 线闭合时触发"""
    # Mock 时间到 13:14:59
    # Mock K 线数据
    # 断言：信号被触发

async def test_no_signal_before_close():
    """验证 K 线未闭合时不触发信号"""
    # Mock 时间到 13:14:58
    # 断言：无信号
```

---

## 迁移计划

### 阶段 1: 新增调度器模块
- 创建 `scheduler.py`
- 实现 `is_kline_close_time()` 和 `is_kline_closed()`
- 添加单元测试

### 阶段 2: 重构主循环
- 修改 `lite.py` 的 `main()` 函数
- 用同步轮询替代 5 秒轮询
- 保留信号管道逻辑不变

### 阶段 3: 测试验证
- 本地运行测试
- Mock 时间验证触发时机
- 实盘/测试网验证

---

## 验收标准

- [ ] 15m 周期只在 XX:14:59、XX:29:59、XX:44:59、XX:59:59 触发
- [ ] 1h 周期只在 XX:59:59 触发
- [ ] 4h 周期只在 03:59:59、07:59:59、...触发
- [ ] 所有触发都经过闭合验证
- [ ] 58 个现有测试全部通过
- [ ] 新增调度器单元测试通过

---

*最后更新：2026-03-27*
