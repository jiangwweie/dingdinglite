# 盯盘狗 Lite - 进度日志

---

## 2026-03-27 - 会话 1

### 开始时间
10:52

### 完成工作

#### 1. 需求讨论与确认
- 确定 Direction 枚举：LONG/SHORT（不添加 NEUTRAL）
- 确定 Trend 枚举：BULLISH/BEARISH/NEUTRAL
- 确定 KlineData 字段：timestamp 用 int，不需要 open_interest
- 确定 SignalResult 字段：添加 reason，big_trend 用枚举
- 确定配置验证：symbols 至少 1 个，timeframes 只能包含{15m, 1h, 4h}
- 确定周期映射：15m→1h, 1h→4h, 4h→1d
- 确定通知格式：包含 reason 字段

#### 2. Task 1: 数据模型实现
- 创建 `models.py`
- 创建 `tests/test_models.py`
- 测试结果：**10 passed**

#### 3. Task 2: 策略逻辑实现
- 创建 `strategy.py`
- 创建 `tests/test_strategy.py`
- 测试结果：**20 passed**

#### 4. Task 3: 飞书推送实现
- 创建 `notifier.py`
- 创建 `tests/test_notifier.py`
- 更新 `requirements.txt`（添加 aiohttp）
- 测试结果：**7 passed**

#### 5. Task 4: 主入口实现
- 创建 `lite.py`
- 创建 `tests/test_lite.py`
- 测试结果：**21 passed**

#### 6. Task 5: 配置文件和 Docker
- 创建 `config.yaml`
- 创建 `Dockerfile`
- 创建 `docker-compose.yml`
- 创建 `README.md`
- 创建 `logs/.gitkeep`

#### 7. Task 6: 辅助文件
- 创建 `.gitignore`

#### 8. 配置填入
- 填入 Binance 实盘 API 密钥（⚠️ 已泄露，建议撤销）
- 填入飞书 Webhook URL

### 测试结果汇总

```
============================= test session starts ==============================
58 passed in ~3s
```

| 测试文件 | 通过数 |
|---------|--------|
| `test_models.py` | 10 |
| `test_strategy.py` | 20 |
| `test_notifier.py` | 7 |
| `test_lite.py` | 21 |

### 待办事项

全部完成！系统已在 Docker 中运行。

### 遇到的问题

| 问题 | 解决方案 |
|------|---------|
| Agent 工具不支持 custom subagent_type | 使用 general-purpose 代替 |
| API 密钥在聊天中泄露 | 建议用户撤销并重新生成 |
| 程序运行无日志，黑盒状态 | 增加 DEBUG 级别日志，心跳、K 线检测、Pinbar 分析全输出 |
| 日志时间为 UTC 而非北京时间 | Docker 容器设置 TZ=Asia/Shanghai 环境变量 |
| 启动后无法检测信号（缺 EMA 上下文） | 启动时预加载 60 根历史 K 线，立即建立 EMA 缓存 |

### 结束时间
待用户后续测试验证

---

## 2026-03-27 - 会话 2 (日志增强 + 预加载)

### 开始时间
19:00

### 完成工作

#### 1. 日志系统增强
- 日志级别改为 DEBUG，输出详细信息
- 添加心跳日志（每 30 秒）：显示检查 K 线数和信号数
- 添加 K 线闭合日志：显示 O/H/L/C 价格
- 添加 Pinbar 检测日志：显示影线分析详情
- 添加 EMA 趋势判断日志
- 添加信号产生日志

#### 2. 时区修复
- 修改 `scheduler.py` 使用北京时间判断 K 线闭合
- 修改 `lite.py` 日志输出使用北京时间
- 修改 `docker-compose.yml` 添加 `TZ=Asia/Shanghai` 环境变量

#### 3. 激进参数调整
- `min_wick_ratio`: 0.6 → 0.5 (影线占比下限降低)
- `max_body_ratio`: 0.3 → 0.4 (实体占比上限提高)
- 实体位置要求：10% → 20%
- 止损幅度：0.1% → 0.3%
- 冷却时间：5 分钟 → 2 分钟
- EMA 趋势判断：`>` → `>=` (包含相等算多头)

#### 4. 历史 K 线预加载
- 新增 `SignalPipeline.initialize_context()` 方法
- 启动时为每个币种加载 1h/4h/1d 历史 K 线
- 计算 EMA 并缓存，立即可检测信号
- 无需等待 K 线闭合

### 修改的文件
- `lite.py`: 增加日志输出、预加载逻辑、真实 EMA 计算
- `strategy.py`: 增加 Pinbar 检测日志、激进参数
- `scheduler.py`: 使用北京时间
- `docker-compose.yml`: 添加时区环境变量
- `requirements.txt`: 添加 pytz 依赖

### 结束时间
2026-03-27 19:49 (预加载验证成功)

---

## 2026-03-28 - 会话 3 (回测 + 参数优化)

### 开始时间
20:00

### 完成工作

#### 1. 回测脚本开发
- 创建 `backtest.py` - ETH/USDT 1h 级别 Pinbar 策略回测
- 从 Binance API 拉取 7 天历史 K 线数据
- 实现盈亏计算和报告输出（JSON + CSV）

#### 2. Pinbar 参数优化
**旧参数**：
- `min_wick_ratio`: 0.5 (影线≥50%)
- `max_body_ratio`: 0.4 (实体≤40%)
- `body_position_tolerance`: 0.1 (实体位置严格在顶部/底部 20%)

**新参数**：
- `min_wick_ratio`: 0.5 (影线≥50%)
- `max_body_ratio`: 0.35 (实体≤35%)
- `body_position_tolerance`: 0.3 (实体位置放宽到 50%±30%)

#### 3. 止损逻辑调整
**旧逻辑**：
- LONG: Pinbar 最低价 × 0.997 (下方 0.3%)
- SHORT: Pinbar 最高价 × 1.003 (上方 0.3%)

**新逻辑**：
- LONG: Pinbar 最低价（极值点）
- SHORT: Pinbar 最高价（极值点）
- 止盈：止损距离 × 1.5 (盈亏比 1.5:1)

#### 4. 出场逻辑改进
- 持有 3 根 K 线或触发止盈/止损
- 统计出场原因（止盈/止损/未触达）

### 回测结果

#### 第一轮（旧参数，简化出场）
| 指标 | 结果 |
|------|------|
| 信号数 | 6 |
| 胜率 | 16.7% |
| 盈亏比 | 1.76 |

**问题**：盈亏绝对值太小（0.00%），下一根开盘价出场无意义

#### 第二轮（新参数，简化出场）
| 指标 | 结果 |
|------|------|
| 信号数 | 17 (+183%) |
| 胜率 | 11.8% |
| 盈亏比 | 3.12 |

**观察**：放宽参数后信号增加，但胜率下降

#### 第三轮（新参数，止盈 1.5R）
| 指标 | 结果 |
|------|------|
| 信号数 | 16 |
| 胜率 | **0%** (全损) |
| 总盈亏 | -11.38% |
| 止盈触发 | 0/16 (0%) |
| 止损触发 | 16/16 (100%) |

**问题分析**：
1. 所有信号都是做空（4h EMA 空头趋势）
2. 但实际行情是上涨/反弹，导致 100% 止损
3. "顺大逆小"策略在趋势反转时失效

### 修改的文件
- `strategy.py`: Pinbar 参数调整，止损逻辑修改
- `backtest.py`: 新增回测脚本，止盈止损逻辑

### 待解决问题
1. **趋势过滤不足**：仅靠 EMA 判断趋势不够，需要更多指标
2. **止损太紧**：Pinbar 极值点止损在震荡行情容易被扫
3. **参数需要优化**：不同行情需要不同参数

### 结束时间
2026-03-28 21:45

---

*最后更新：2026-03-28*
