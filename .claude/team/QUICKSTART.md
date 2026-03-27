# Lite 版快速开始指南

> **最后更新**: 2026-03-27

---

## 🚀 30 秒快速开始

### 方式 1：最简单 - 直接描述需求

```bash
# 输入 /coordinator 然后描述你的需求
/coordinator

我想添加一个通知重试机制：
1. 飞书推送失败后自动重试 3 次
2. 每次重试间隔递增（1s, 5s, 30s）
3. 记录重试日志
```

**会发生什么**：
1. Coordinator 自动分解任务
2. 并行调用 Backend、QA
3. 每个角色只修改自己负责的文件
4. 最后汇总输出

---

### 方式 2：指定角色 - 单点任务

```bash
# 只需要后端改动能直接调用
/backend

为 notifier.py 添加重试逻辑
使用指数退避：1s, 5s, 30s
最多重试 3 次
```

```bash
# 需要测试时调用
/qa

为通知重试功能编写测试
覆盖正常推送、重试成功、重试失败场景
```

---

## 📋 完整工作流程示例

### 示例：开发"通知重试"功能

#### 步骤 1：启动 Coordinator
```bash
/coordinator
```

#### 步骤 2：描述需求
```
我想实现一个通知重试机制：

用户故事：
- 当飞书推送失败时
- 自动重试 3 次
- 每次间隔递增（1s, 5s, 30s）
- 记录重试日志

技术要求：
- 后端实现重试逻辑
- 需要有测试覆盖
```

#### 步骤 3：Coordinator 分解任务

Coordinator 会自动创建以下任务：

```
┌─────────────────────────────────────────────────────┐
│ 任务分解结果                                        │
├─────────────────────────────────────────────────────┤
│ Task 1 [Backend]   实现通知重试逻辑                 │
│ Task 2 [Backend]   添加重试配置到 config.yaml       │
│ Task 3 [QA]        编写重试场景测试                 │
│ Task 4 [QA]        边界条件测试（超时/失败）        │
└─────────────────────────────────────────────────────┘
```

#### 步骤 4：并行执行

```python
# Coordinator 并行调用两个角色
Agent(subagent_type="backend-dev", prompt="实现通知重试逻辑...")
Agent(subagent_type="qa-tester", prompt="编写重试场景测试...")
```

#### 步骤 5：等待完成 → 汇总输出

```markdown
## 任务完成汇总

### 后端实现 (by backend-dev)
- ✅ notifier.py 添加 retry_feishu() 函数
- ✅ 指数退避重试（1s, 5s, 30s）
- ✅ 单元测试 8 个，覆盖率 95%

### 测试覆盖 (by qa-tester)
- ✅ 重试场景测试 6 个
- ✅ 边界条件测试 2 个
- ✅ 全部通过

### 验证命令
pytest tests/test_notifier.py -v
```

---

## ⚠️ 注意事项

### ✅ 推荐做法
- 完整功能开发 → 使用 `/coordinator`
- 单一角色任务 → 直接调用 `/frontend`、`/backend`、`/qa`
- 任务完成后 → 等待 Coordinator 汇总再验收

### ❌ 避免做法
- 同时调用多个角色做同一件事（会冲突）
- 跳过 Coordinator 直接并行多个 Agent
- 修改不属于自己负责的文件

---

## 🔧 故障排除

### 问题 1：角色说"无权修改此文件"
**原因**: 任务分配给了错误的角色

**解决**:
```bash
/coordinator
刚才的任务分配有误，请重新分解：
- XX 文件应该由 backend-dev 修改
```

### 问题 2：任务卡住无法继续
**原因**: 依赖任务未完成

**解决**:
```bash
/coordinator
Task X 依赖 Task Y 完成，但 Task Y 卡住了
请检查依赖关系，调整执行顺序
```

---

## 📚 相关文档

- `.claude/team/backend-dev/SKILL.md` - 后端角色详细规范
- `.claude/team/qa-tester/SKILL.md` - 测试角色详细规范
- `.claude/team/code-reviewer/SKILL.md` - 代码审查员详细规范

---

*开始使用吧！输入 `/coordinator` 然后描述你的第一个需求！*
