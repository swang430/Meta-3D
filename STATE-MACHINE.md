# 状态机文档

本文档详细描述系统中所有实体的状态转换逻辑，确保前后端实现的一致性。

---

## 为什么需要状态机文档？

**BUG-002的教训**：我们有执行流程的设计，但缺少明确的状态机文档，导致：
- `TestPlanUpdate` schema遗漏了 `status` 字段
- 前端缺少"标记为就绪"按钮
- 用户无法执行测试计划

**状态机文档的价值**：
1. **明确所有可能的状态** - 避免遗漏
2. **定义状态转换条件** - 明确何时可以转换
3. **指导实现** - 确保schema包含status字段，UI包含转换按钮

---

## 测试计划 (TestPlan) 状态机

### 状态定义

| 状态 | 英文名 | 中文名 | 描述 | UI颜色 |
|------|-------|-------|------|--------|
| `draft` | Draft | 草稿 | 初始状态，正在编辑 | Gray |
| `ready` | Ready | 就绪 | 编辑完成，可以执行 | Blue |
| `queued` | Queued | 已排队 | 已加入执行队列 | Cyan |
| `running` | Running | 执行中 | 正在执行测试 | Green |
| `paused` | Paused | 已暂停 | 执行被暂停 | Yellow |
| `completed` | Completed | 已完成 | 测试完成 | Teal |
| `failed` | Failed | 失败 | 测试失败 | Red |
| `cancelled` | Cancelled | 已取消 | 用户取消执行 | Orange |

### 状态转换图

```
                                  ┌─────────┐
                                  │  draft  │ (Initial)
                                  └────┬────┘
                                       │
                              [Mark Ready 标记为就绪]
                                       │
                                       ▼
                                  ┌─────────┐
                         ┌───────│  ready  │
                         │        └────┬────┘
                         │             │
                    [Edit 编辑]   [Queue 加入队列]
                         │             │
                         │             ▼
                         │        ┌─────────┐
                         └───────▶│ queued  │
                                  └────┬────┘
                                       │
                              [Start 开始执行]
                                       │
      ┌────────────────────────────────┼────────────────────────────┐
      │                                │                            │
      │                                ▼                            │
      │                           ┌─────────┐                       │
      │                           │ running │                       │
      │                           └────┬────┘                       │
      │                                │                            │
      │       ┌────────────────────────┼────────────────┐           │
      │       │                        │                │           │
      │  [Pause 暂停]          [Complete 完成]   [Fail 失败]  [Cancel 取消]
      │       │                        │                │           │
      │       ▼                        ▼                ▼           ▼
      │  ┌─────────┐             ┌───────────┐    ┌────────┐  ┌───────────┐
      │  │ paused  │             │ completed │    │ failed │  │ cancelled │
      │  └────┬────┘             └───────────┘    └────────┘  └───────────┘
      │       │                                                      ▲
      │       │                                                      │
      │  [Resume 恢复]                                               │
      │       │                                                      │
      └───────┴──────────────────────────────────────────────────────┘
              [Cancel取消 - 可从任何执行状态取消]
```

### 状态转换规则

| 当前状态 | 可转换到 | 触发方式 | 权限 | UI按钮 | API Endpoint |
|---------|---------|---------|------|-------|--------------|
| `draft` | `ready` | 用户标记就绪 | 编辑者 | ✅ "标记为就绪" (绿色✓) | `PATCH /test-plans/{id}` |
| `draft` | `draft` | 用户编辑 | 编辑者 | "编辑" | `PATCH /test-plans/{id}` |
| `ready` | `queued` | 用户添加到队列 | 执行者 | ✅ "添加到队列" (蓝色🕐) | `POST /test-plans/queue` |
| `ready` | `draft` | 用户编辑 | 编辑者 | "编辑" | `PATCH /test-plans/{id}` |
| `queued` | `running` | 用户开始执行 | 执行者 | ✅ "开始执行" (绿色▶) | `POST /test-plans/{id}/start` |
| `queued` | `ready` | 用户移出队列 | 执行者 | "移出队列" | `DELETE /test-plans/queue/{id}` |
| `running` | `paused` | 用户暂停 | 执行者 | ✅ "暂停" (橙色⏸) | `POST /test-plans/{id}/pause` |
| `running` | `completed` | 测试全部通过 | 系统 | - | 自动转换 |
| `running` | `failed` | 测试失败 | 系统 | - | 自动转换 |
| `running` | `cancelled` | 用户取消 | 执行者 | ✅ "取消执行" (橙色⏹) | `POST /test-plans/{id}/cancel` |
| `paused` | `running` | 用户恢复 | 执行者 | "恢复执行" | `POST /test-plans/{id}/resume` |
| `paused` | `cancelled` | 用户取消 | 执行者 | "取消执行" | `POST /test-plans/{id}/cancel` |

### 关键状态转换的UI实现

**必须在前端实现的按钮**（来自 TestPlanList.tsx）：

```tsx
// 1. draft → ready
{plan.status === 'draft' && (
  <Tooltip label="标记为就绪">
    <ActionIcon color="green" onClick={() => handleMarkReady(plan.id)}>
      <IconCheck size={16} />
    </ActionIcon>
  </Tooltip>
)}

// 2. ready → queued
{plan.status === 'ready' && (
  <Tooltip label="添加到队列">
    <ActionIcon color="blue" onClick={() => handleQueue(plan.id)}>
      <IconClock size={16} />
    </ActionIcon>
  </Tooltip>
)}

// 3. queued → running
{plan.status === 'queued' && (
  <Tooltip label="开始执行">
    <ActionIcon color="green" onClick={() => handleStart(plan.id)}>
      <IconPlayerPlay size={16} />
    </ActionIcon>
  </Tooltip>
)}

// 4. running → paused
{plan.status === 'running' && (
  <Tooltip label="暂停">
    <ActionIcon color="orange" onClick={() => handlePause(plan.id)}>
      <IconPlayerPause size={16} />
    </ActionIcon>
  </Tooltip>
)}

// 5. 任何执行状态 → cancelled
{['running', 'paused', 'queued'].includes(plan.status) && (
  <Menu.Item
    leftSection={<IconPlayerStop size={14} />}
    color="orange"
    onClick={() => handleCancel(plan.id)}
  >
    取消执行
  </Menu.Item>
)}
```

### 后端Schema要求

**必须包含的字段**（来自 api-service/app/schemas/test_plan.py）：

```python
class TestPlanUpdate(BaseModel):
    """Update schema必须包含status字段"""
    status: Optional[str] = Field(
        None,
        description="Test plan status (draft, ready, queued, running, paused, completed, failed, cancelled)"
    )
    # ... 其他可编辑字段
```

---

## 测试步骤 (TestStep) 状态机

### 状态定义

| 状态 | 英文名 | 中文名 | 描述 |
|------|-------|-------|------|
| `pending` | Pending | 待执行 | 初始状态 |
| `running` | Running | 执行中 | 正在执行 |
| `passed` | Passed | 通过 | 执行成功 |
| `failed` | Failed | 失败 | 执行失败 |
| `skipped` | Skipped | 跳过 | 被跳过（条件不满足） |

### 状态转换图

```
┌─────────┐
│ pending │ (Initial)
└────┬────┘
     │
     │ [Test Plan执行到此步骤]
     │
     ▼
┌─────────┐
│ running │
└────┬────┘
     │
     ├──[Success]──▶ ┌────────┐
     │               │ passed │
     │               └────────┘
     │
     ├──[Failure]──▶ ┌────────┐
     │               │ failed │
     │               └────────┘
     │
     └──[Skip]────▶ ┌─────────┐
                    │ skipped │
                    └─────────┘
```

---

## 实现检查清单

基于状态机文档，实现时必须检查：

### 后端检查

```
□ 数据模型定义了status字段（Enum或String）
□ Update schema包含status字段
□ 所有状态转换都有对应的API endpoint
□ 状态转换有验证逻辑（不允许非法转换）
□ 状态转换记录了操作日志
```

### 前端检查

```
□ 所有状态都有Badge显示（颜色+文字）
□ 所有用户触发的转换都有按钮
□ 按钮显示条件正确（按当前状态显示）
□ 状态转换API调用正确
□ 转换成功后刷新数据
```

---

## 相关文档

- [BUGFIX-LOG.md](BUGFIX-LOG.md) - BUG-002记录了缺少状态转换功能的问题
- [IMPLEMENTATION-CHECKLIST.md](IMPLEMENTATION-CHECKLIST.md) - 实现检查清单
- [TestManagement-Unified-Architecture.md](docs/design/TestManagement-Unified-Architecture.md) - 测试管理架构

---

**创建时间**: 2025-11-23
**维护者**: 开发团队
**版本**: 1.0
