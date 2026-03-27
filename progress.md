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

*最后更新：2026-03-27*
