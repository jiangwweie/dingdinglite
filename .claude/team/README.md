# 盯盘狗 Lite 🐶 Agent Team 配置

> **最后更新**: 2026-03-27
> **适用范围**: Lite 版（无前端，仅后端 + 测试）

---

## Team 结构

Lite 版是精简个人项目，团队配置简化为：

```
┌─────────────────────────────────────────────────┐
│              Team Coordinator                    │
│         (任务分解 + 协调 + 结果整合)              │
└─────────────────────────────────────────────────┘
                      │
        ┌─────────────┼─────────────┐
        ▼             ▼             ▼
┌───────────────┐ ┌───────────┐ ┌───────────┐
│ Backend       │ │   QA      │ │  Code     │
│  (后端)       │ │  Tester   │ │ Reviewer  │
│               │ │  (测试)   │ │  (审查)   │
└───────────────┘ └───────────┘ └───────────┘
```

**注意**: Lite 版无前端角色（`/frontend`），因为 Lite 版不需要前端界面。

---

## 角色技能说明

### Team Coordinator (`/coordinator`)
- **职责**: 任务分解、角色调度、进度追踪、结果整合
- **触发场景**: 完整功能开发、跨模块任务
- **使用方式**: 输入 `/coordinator` 或直接描述需求

### Backend Developer (`/backend`)
- **职责**: Python + FastAPI + asyncio 后端实现
- **触发场景**: API、领域模型、基础设施
- **使用方式**: 输入 `/backend` 或分配后端任务

### QA Tester (`/qa`)
- **职责**: 测试策略、单元测试、集成测试
- **触发场景**: 编写测试、验证功能、回归测试
- **使用方式**: 输入 `/qa` 或分配测试任务

### Code Reviewer (`/reviewer`)
- **职责**: 代码审查、架构一致性检查、安全隐患识别
- **触发场景**: 代码完成后审查、架构把关、合并前审查
- **使用方式**: 输入 `/reviewer` 或分配审查任务

---

## 使用方式

### 方式 1: 角色切换命令
```bash
# 切换到协调器角色
/coordinator

# 切换到后端角色
/backend

# 切换到测试角色
/qa
```

### 方式 2: 直接描述需求（自动分解）
```
用户：我想添加一个飞书通知重试机制

→ Team Coordinator 自动分解：
   - 后端：实现通知重试逻辑
   - 测试：编写重试场景测试
```

### 方式 3: 并行调度（使用 Agent 工具）
```python
# 并行执行多个角色
Agent(subagent_type="backend-dev", prompt="...")
Agent(subagent_type="qa-tester", prompt="...")
```

---

## 文件边界规则 (File Boundaries)

> ⚠️ **核心原则**: 每个角色只能修改自己负责的文件，避免协作冲突

### 文件所有权矩阵

| 文件路径 | Backend | QA | Coordinator | Reviewer |
|----------|---------|----|-------------|----------|
| `src/**` | ✅ 全权 | ⚠️ 仅测试 | ⚠️ 仅协调 | 🔍 审查 |
| `tests/**` | ⚠️ 协助 | ✅ 全权 | ⚠️ 仅协调 | ✅ 修改测试 |
| `config/**` | ✅ 全权 | ❌ 禁止 | ⚠️ 仅协调 | 🔍 审查 |
| `*.py` (根目录) | ✅ 全权 | ❌ 禁止 | ⚠️ 仅协调 | 🔍 审查 |
| `README.md` | ❌ 禁止 | ❌ 禁止 | ✅ 全权 | 🔍 审查 |

**图例**: ✅ 全权负责 | ❌ 禁止修改 | ⚠️ 有限权限 | 🔍 仅审查

### 各角色详细边界

#### Backend 边界
```
✅ 可修改：
  - *.py (根目录后端代码，如 lite.py, strategy.py, notifier.py, models.py)
  - config.yaml (配置建议)
❌ 禁止：
  - tests/** (测试代码，由 QA 负责)
```

#### QA 边界
```
✅ 可修改：
  - tests/** (全部测试文件)
❌ 禁止：
  - *.py (业务代码，由 Backend 负责)
  - config.yaml
```

#### Coordinator 边界
```
✅ 可修改：
  - README.md
  - .claude/team/**
⚠️ 协调：跨角色文件变更
```

#### Reviewer 边界
```
✅ 可修改：
  - tests/** (测试代码)
🔍 审查：
  - *.py, tests/** (仅审查意见，不直接修改)
```

---

## 常用场景速查

### 场景 1：添加新功能
```bash
/backend

添加通知重试机制：
- 飞书推送失败后自动重试 3 次
- 每次重试间隔递增（1s, 5s, 30s）
- 记录重试日志
```

### 场景 2：修复 Bug
```bash
/qa

发现 Bug：Pinbar 检测在极端 K 线数据下崩溃
请编写测试复现这个问题
```

### 场景 3：完整功能开发
```bash
/coordinator

实现"账户余额查询"功能：
1. 后端添加获取账户余额 API
2. 在通知消息中显示当前余额
3. 需要有测试覆盖
```

---

## 最佳实践

### ✅ 推荐做法
- 完整功能开发优先使用 Team Coordinator 模式
- 独立任务直接调用对应角色
- 测试先行：先写测试再实现功能
- 并行执行：后端和测试任务同时进行

### ❌ 避免做法
- 单一角色处理全栈任务（效率低）
- 跳过测试直接交付
- 缺少任务追踪（使用 TaskCreate）

---

## 全局技能集成 (Global Skills Integration)

**每个 Agent Team 成员都应主动调用全局 skills 来提升工作质量：**

### 全局 Skills 与 Agent 映射

| Agent 角色 | 应调用的全局 Skills | 使用场景 |
|-----------|---------------------|----------|
| **Backend Dev** | `code-simplifier` | 代码完成后优化简化 |
| | `brainstorming` | 复杂需求分析 |
| | `systematic-debugging` | 遇到 Bug 时调试 |
| **QA Tester** | `code-simplifier` | 测试代码简化 |
| | `systematic-debugging` | 测试失败分析 |
| **Coordinator** | `brainstorming` | 需求分解前探索 |
| | `planning-with-files-zh` | 制定执行计划 |
| | `dispatching-parallel-agents` | 并行任务调度 |
| | `verification-before-completion` | 完成前验证 |
| | `requesting-code-review` | 请求正式审查 |
| **Code Reviewer** | `code-review` | 正式代码审查流程 |
| | `code-simplifier` | 识别代码复杂度问题 |

---

## 故障排除

### 问题 1：任务卡住无法继续
**原因**: 依赖任务未完成

**解决**:
```bash
/coordinator
Task X 依赖 Task Y 完成，但 Task Y 卡住了
请检查依赖关系，调整执行顺序
```

### 问题 2：测试失败需要改业务代码
**解决**:
1. QA 报告失败测试
2. Coordinator 分配给 backend-dev 修复
3. 修复后 QA 重新验证

---

## 相关文档

- `.claude/team/backend-dev/SKILL.md` - 后端角色详细规范
- `.claude/team/qa-tester/SKILL.md` - 测试角色详细规范
- `.claude/team/code-reviewer/SKILL.md` - 代码审查员详细规范
- `.claude/team/team-coordinator/SKILL.md` - 协调员详细规范

---

*Lite 版配置 - 简化自 Max 版团队配置*
