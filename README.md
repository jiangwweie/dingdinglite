# 盯盘狗 Lite (dingpang-lite)

个人极简盯盘工具 - 专注于 Pinbar 形态信号推送

## 项目介绍

盯盘狗 Lite 是一个极简的加密货币盯盘工具，实时监控 Binance 合约市场的 K 线数据，当检测到 Pinbar（引脚形态）时自动推送飞书通知。

**核心特性**:
- 实时 WebSocket 数据流
- Pinbar 形态自动检测
- 顺大逆小逻辑（大周期 EMA 趋势 + 小周期 Pinbar 信号）
- 飞书通知推送
- Docker 一键部署

## 快速开始

### 方式一：Docker Compose（推荐）

```bash
# 1. 克隆仓库
git clone https://github.com/your-org/dingpang-lite.git
cd dingpang-lite

# 2. 配置 API 密钥和飞书 Webhook
cp config.yaml config.yaml.local
# 编辑 config.yaml.local，填入你的 API 密钥和 Webhook URL

# 3. 启动服务
docker-compose up -d

# 4. 查看日志
docker-compose logs -f

# 5. 停止服务
docker-compose down
```

### 方式二：本地运行

```bash
# 1. 创建虚拟环境
python -m venv venv
source venv/bin/activate  # macOS/Linux
# 或
.\venv\Scripts\activate   # Windows

# 2. 安装依赖
pip install -r requirements.txt

# 3. 配置 config.yaml

# 4. 运行程序
python lite.py
```

## 配置说明

### config.yaml 结构

```yaml
# 交易所配置
exchange:
  name: binance                     # 交易所名称（目前仅支持 binance）
  api_key: "YOUR_API_KEY"           # API Key
  api_secret: "YOUR_API_SECRET"     # API Secret
  testnet: false                    # true = 测试网，false = 实盘

# 监控币种
symbols:
  - BTC/USDT:USDT
  - ETH/USDT:USDT
  - SOL/USDT:USDT

# 监控周期（只能是 15m、1h、4h 的子集）
timeframes:
  - 15m
  - 1h
  - 4h

# 策略参数
strategy:
  ema_period: 60          # EMA 周期
  pinbar:
    min_wick_ratio: 0.6   # 最小影线占比
    max_body_ratio: 0.3   # 最大实体占比

# 日志配置
logging:
  level: INFO             # 日志级别：DEBUG, INFO, WARNING, ERROR
  file: logs/lite.log     # 日志文件路径

# 通知配置
notification:
  feishu_webhook: "https://open.feishu.cn/open-apis/bot/v2/hook/..."
```

## 策略逻辑说明

### Pinbar 形态检测

Pinbar（引脚形态）是一种单根 K 线反转形态，特征是具有长影线和短实体。

**看涨 Pinbar**:
- 下影线长度 / K 线总长度 >= 0.6
- 实体长度 / K 线总长度 <= 0.3
- 实体位于 K 线顶部 10% 区间

**看跌 Pinbar**:
- 上影线长度 / K 线总长度 >= 0.6
- 实体长度 / K 线总长度 <= 0.3
- 实体位于 K 线底部 10% 区间

### 顺大逆小逻辑

1. **大周期趋势判定**：使用 EMA(60) 判断 1h 周期趋势
   - 收盘价 > EMA → 多头趋势
   - 收盘价 < EMA → 空头趋势

2. **小周期信号生成**：仅在 15m 周期检测与大趋势同向的 Pinbar
   - 多头趋势时，只检测看涨 Pinbar（做多信号）
   - 空头趋势时，只检测看跌 Pinbar（做空信号）

## 通知格式示例

```
🐶 盯盘狗 - Pinbar 信号

币种：BTC/USDT:USDT
周期：15m
方向：🟢 做多 / 🔴 做空
入场价：$67,850.00
止损价：$67,200.00

大周期趋势：1h EMA 多头/空头
形态质量：标准 Pinbar (下影线占比 72%)

---
盯盘狗 Lite v0.1.0
```

## 工作原理

1. **同步轮询调度器** - 每秒检查时间，在 K 线闭合时刻（XX:14:59、XX:59:59）触发
2. **K 线读取** - 读取最近 2 根 K 线，使用前一根（确保已闭合）
3. **闭合验证** - 验证 K 线时间戳，过滤未闭合数据
4. **信号检测** - Pinbar 检测 + EMA 趋势判断
5. **飞书推送** - 产生信号时发送通知

## 项目结构

```
dingpang-lite/
├── Dockerfile               # 容器镜像构建
├── docker-compose.yml       # Docker Compose 配置
├── README.md                # 本文件
├── requirements.txt         # Python 依赖
├── config.yaml              # 配置文件模板
├── lite.py                  # 主入口程序
├── strategy.py              # 策略逻辑（Pinbar + EMA）
├── notifier.py              # 通知推送（飞书 Webhook）
├── models.py                # 数据模型
├── logs/                    # 日志目录
│   └── .gitkeep
└── tests/                   # 单元测试
    ├── __init__.py
    └── test_models.py
```

## 测试命令

```bash
# 运行单元测试
pytest tests/

# 或
python -m pytest tests/ -v
```

## 常见问题

### Q1: API 密钥如何获取？

前往 [Binance API 管理页面](https://www.binance.com/en/my/settings/api-management) 创建 API Key。确保开启以下权限：
- 读取信息
- 合约交易

**不要开启提现权限！**

### Q2: 飞书 Webhook 如何配置？

1. 在飞书群聊中点击「机器人」→「添加机器人」
2. 选择「自定义机器人」
3. 复制 Webhook 地址
4. 粘贴到 `config.yaml` 的 `notification.feishu_webhook` 字段

### Q3: 日志文件在哪里？

Docker 部署时，日志文件挂载在 `./logs/lite.log`
查看实时日志：
```bash
docker-compose logs -f
# 或
tail -f logs/lite.log
```

### Q4: WebSocket 断线会自动重连吗？

是的，程序实现了指数退避重连机制（1s → 2s → 4s → ... → 60s）。

### Q5: 如何添加更多监控币种？

在 `config.yaml` 的 `symbols` 列表中添加：
```yaml
symbols:
  - BTC/USDT:USDT
  - ETH/USDT:USDT
  - SOL/USDT:USDT
  - BNB/USDT:USDT    # 新增
  - XRP/USDT:USDT   # 新增
```
然后重启服务。

### Q6: 支持哪些时间周期？

目前仅支持：`15m`、`1h`、`4h`
这是为了符合「顺大逆小」策略的时间尺度要求。

### Q7: 如何修改策略参数？

编辑 `config.yaml` 中的 `strategy` 部分，然后重启服务使配置生效。

## 许可证

MIT License
