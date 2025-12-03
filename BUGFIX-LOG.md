# Bug 修复日志

记录系统中发现的重要 Bug 及修复过程。

---

## 🐛 BUG-001: 测试步骤编辑保存失败

**优先级**: 🔴 高
**状态**: ✅ 已修复
**发现时间**: 2025-11-23 17:20
**修复时间**: 2025-11-23 18:30
**影响范围**: 测试步骤管理

### 症状描述

用户在步骤编辑器 (StepEditor) 中修改执行配置（超时时间、重试次数、失败后继续）并点击"保存更改"后，数据没有被持久化到数据库。

**复现步骤**:
1. 打开测试管理 → 步骤编排
2. 选择一个测试计划
3. 选择一个测试步骤进行编辑
4. 修改"超时时间"从 300 改为 900
5. 修改"重试次数"从 0 改为 3
6. 修改"失败后继续执行"从关闭改为开启
7. 点击"保存更改"
8. **预期**: 数据保存成功
9. **实际**: 刷新后数据仍然是原来的值

### 根本原因分析

#### 发现的问题

通过后端日志分析发现：

```
2025-11-23 17:25:28,199 INFO - COMMIT
2025-11-23 17:25:28,200 INFO - Updated test step: 5209f2ce-...
2025-11-23 17:25:28,203 INFO - ROLLBACK  # ❌ 事务被回滚！
```

**问题链**：

1. ✅ 前端发送 PATCH 请求
2. ✅ 后端endpoint 接收请求 (返回 200 OK)
3. ✅ `TestStepService.update_test_step()` 执行 setattr 更新字段
4. ✅ 服务层调用 `db.commit()` 提交事务
5. ❌ FastAPI `get_db()` 依赖在请求结束时调用 `db.close()`
6. ❌ SQLAlchemy 在 close 时**隐式回滚**所有未commit的事务

**核心问题**: FastAPI 依赖注入的会话管理机制与服务层的事务管理冲突。

#### 原始代码 (有问题)

```python
# api-service/app/db/database.py (BEFORE)
def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()  # ❌ 关闭时会回滚未提交的事务
```

### 尝试的修复

#### 修复 1: 在 get_db 中添加 commit

```python
# api-service/app/db/database.py (AFTER)
def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
        if db.in_transaction():  # ⚠️ 这个检查可能有问题
            db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
```

**测试结果**: ❌ 仍然失败，数据未保存

**可能的原因**:
1. `db.in_transaction()` 可能在服务层 commit 后返回 False
2. 服务层 commit 后创建了新事务，但在 endpoint 层又被回滚
3. SQLAlchemy autocommit模式配置问题

### ✅ 最终解决方案

#### 真正的根本原因

经过深入调查发现，问题根本不在事务管理，而是 **Pydantic 模式定义不完整**：

`api-service/app/schemas/test_plan.py` 中的 `TestStepUpdate` 模式缺少以下字段：
- `timeout_seconds`
- `retry_count`
- `continue_on_failure`

前端发送的这些字段被 Pydantic 验证器**静默忽略**，导致 `request.dict(exclude_unset=True)` 返回空字典。

#### 修复代码

在 `TestStepUpdate` 类中添加缺失的字段：

```python
class TestStepUpdate(BaseModel):
    """Request to update a test step"""
    # ... 其他字段 ...

    # Execution configuration fields (新添加)
    timeout_seconds: Optional[int] = Field(None, ge=1, description="Step timeout in seconds")
    retry_count: Optional[int] = Field(None, ge=0, description="Number of retries on failure")
    continue_on_failure: Optional[bool] = Field(None, description="Whether to continue execution if this step fails")
```

**文件**: [api-service/app/schemas/test_plan.py:318-320](api-service/app/schemas/test_plan.py#L318-L320)

#### 验证结果

测试更新操作：
```bash
# 更新步骤
curl -X PATCH .../steps/{id} -d '{"timeout_seconds":1200,"retry_count":5,"continue_on_failure":false}'

# 验证保存成功
curl .../steps | jq '.[] | select(.id == "...") | {timeout_seconds, retry_count, continue_on_failure}'
{
  "timeout_seconds": 1200,  ✅
  "retry_count": 5,         ✅
  "continue_on_failure": false  ✅
}
```

#### 关键教训

1. **Schema 是 FastAPI 的数据合约** - 任何不在 Pydantic 模型中的字段都会被忽略
2. **事务管理本身没有问题** - 原有的 `get_db()` 实现是正确的
3. **详细日志至关重要** - 通过记录 `kwargs` 内容才发现了真正原因
4. **不要过早下结论** - 最初怀疑是事务问题，实际是 schema 问题

#### 测试代码

```bash
# 测试更新
curl -X PATCH http://localhost:8001/api/v1/test-plans/{plan_id}/steps/{step_id} \
  -H "Content-Type: application/json" \
  -d '{"timeout_seconds": 900, "retry_count": 3, "continue_on_failure": true}'

# 验证是否保存
curl http://localhost:8001/api/v1/test-plans/{plan_id}/steps/{step_id} | \
  jq '{timeout_seconds, retry_count, continue_on_failure}'
```

### 影响评估

**受影响的功能**:
- ✅ 测试步骤添加 - 正常 (创建操作可能在 endpoint 中 commit)
- ✅ 测试步骤列表 - 正常 (只读操作)
- ❌ 测试步骤更新 - **失败** (本 Bug)
- ⚠️  测试步骤删除 - 未测试，可能也有同样问题
- ⚠️  测试步骤重排序 - 未测试，可能也有同样问题

**潜在影响范围**:
- 所有使用 `get_db` 依赖的写操作端点都可能有问题
- 需要系统性审查所有CRUD操作

### 参考资料

- [FastAPI Database Session Management](https://fastapi.tiangolo.com/tutorial/sql-databases/)
- [SQLAlchemy Session Basics](https://docs.sqlalchemy.org/en/14/orm/session_basics.html)
- [DATA-MODEL-GUIDE.md](DATA-MODEL-GUIDE.md) - 事务管理最佳实践

---

**最后更新**: 2025-11-23 18:30
**负责人**: Claude
**优先级**: 🔴 高 - 已修复

---

## 🐛 BUG-002: 无法标记测试计划为就绪状态

**优先级**: 🔴 高
**状态**: ✅ 已修复
**发现时间**: 2025-11-23 18:50
**修复时间**: 2025-11-23 19:10
**影响范围**: 测试计划状态管理，执行队列

### 症状描述

用户创建测试计划并添加测试步骤后，无法将计划添加到执行队列，因为缺少将状态从 `draft` 改为 `ready` 的功能。

**问题链**:
1. 用户创建测试计划 → 状态为 `draft`
2. 用户添加测试步骤 → 状态仍为 `draft`
3. ❌ 没有"标记为就绪"的按钮
4. ❌ `TestPlanUpdate` schema 缺少 `status` 字段
5. ❌ 无法添加到队列（只有 `ready` 状态才能排队）
6. ❌ 无法执行测试

### 根本原因

**与 BUG-001 相同的模式**：Pydantic schema 定义不完整

`api-service/app/schemas/test_plan.py` 中的 `TestPlanUpdate` 缺少 `status` 字段，导致：
- 后端API无法更新测试计划状态
- 前端无法实现"标记为就绪"功能
- 测试计划被困在 `draft` 状态

### 修复方案

#### 后端修复 (api-service/app/schemas/test_plan.py:28)

```python
class TestPlanUpdate(BaseModel):
    """Request to update a test plan"""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    status: Optional[str] = Field(None, description="Test plan status")  # ✅ 新添加
    # ... 其他字段
```

#### 前端修复

**1. 类型定义修复 (gui/src/features/TestManagement/types/index.ts:351)**

```typescript
export interface UpdateTestPlanRequest {
  name?: string
  description?: string
  status?: string  // ✅ 新添加 - Test plan status
  dut_info?: Partial<DUTInfo>
  test_environment?: Partial<TestEnvironment>
  priority?: number
  notes?: string
  tags?: string[]
}
```

**2. UI 实现 (gui/src/features/TestManagement/components/PlansTab/TestPlanList.tsx)**

- 添加 `useUpdateTestPlan` hook
- 添加 `handleMarkReady` 函数
- 添加UI按钮：

```tsx
{plan.status === 'draft' && (
  <Tooltip label="标记为就绪">
    <ActionIcon
      variant="light"
      color="green"
      onClick={() => handleMarkReady(plan.id)}
    >
      <IconCheck size={16} />
    </ActionIcon>
  </Tooltip>
)}
```

### 关键发现：系统性问题

连续发现 BUG-001 和 BUG-002，揭示了一个**系统性的实现缺陷模式**：

**共同点**：
1. ✅ 功能设计存在（状态机、执行流程都有文档）
2. ❌ Update schema 遗漏关键字段
3. ❌ 实现时缺少系统性的检查清单

**模式识别**：
- `TestStepUpdate` 缺少 `timeout_seconds`, `retry_count`, `continue_on_failure`
- `TestPlanUpdate` 缺少 `status`
- 都是**静默失败**（Pydantic 忽略未定义字段）

### 改进建议

详见新创建的文档：
- [IMPLEMENTATION-CHECKLIST.md](IMPLEMENTATION-CHECKLIST.md) - 实现检查清单
- [STATE-MACHINE.md](STATE-MACHINE.md) - 状态机文档

---

**最后更新**: 2025-11-23 22:00
**负责人**: Claude
**优先级**: 🔴 高 - 已修复

**关键教训**：
1. **前后端类型定义要同步** - 后端 Pydantic schema 和前端 TypeScript 类型必须一致
2. **类型不匹配导致静默失败** - 前端发送的字段如果不在类型定义中，TypeScript 不会报错但会导致运行时问题
3. **422 错误通常是类型/验证问题** - 需要检查前后端的数据契约是否匹配

---

## 🐛 BUG-003: 队列和执行控制操作422/400错误

**优先级**: 🔴 高
**状态**: ✅ 已修复
**发现时间**: 2025-11-23 23:00
**修复时间**: 2025-11-23 23:30
**影响范围**: 测试计划执行控制

### 症状描述

用户尝试队列和执行测试计划时遇到验证错误：
- "BugFixTest还有400错误，其他三项有422错误"
- 队列操作失败：`{"detail":[{"type":"missing","loc":["body","queued_by"],"msg":"Field required"}]}`
- 执行控制操作失败：`{"detail":[{"type":"missing","loc":["body","test_plan_id"],"msg":"Field required"}]}`

### 根本原因

**问题1**: 后端控制请求schema包含冗余字段
- `StartTestPlanRequest`、`PauseTestPlanRequest`、`ResumeTestPlanRequest`、`CancelTestPlanRequest` 都包含 `test_plan_id` 字段
- 但该字段已在URL路径中：`POST /test-plans/{id}/start`
- 导致前端必须同时在URL和body中传递相同数据

**问题2**: 前端类型定义字段顺序问题
- `QueueTestPlanRequest` 中 `queued_by` 是必需字段但位置不明确

### 修复方案

#### 后端修复 ([api-service/app/schemas/test_plan.py:253-273](api-service/app/schemas/test_plan.py#L253-L273))

```python
class StartTestPlanRequest(BaseModel):
    """Request to start executing a test plan"""
    # REMOVED: test_plan_id: UUID (redundant - already in URL)
    started_by: str
    override_config: Optional[Dict[str, Any]] = None

class PauseTestPlanRequest(BaseModel):
    """Request to pause a running test plan"""
    # REMOVED: test_plan_id: UUID
    paused_by: str
    reason: Optional[str] = None

class ResumeTestPlanRequest(BaseModel):
    """Request to resume a paused test plan"""
    # REMOVED: test_plan_id: UUID
    resumed_by: str

class CancelTestPlanRequest(BaseModel):
    """Request to cancel a test plan"""
    # REMOVED: test_plan_id: UUID
    cancelled_by: str
    reason: Optional[str] = None
```

#### 前端修复 ([gui/src/features/TestManagement/types/index.ts:401](gui/src/features/TestManagement/types/index.ts#L401))

```typescript
export interface QueueTestPlanRequest {
  test_plan_id: string
  priority?: number
  scheduled_start_time?: string
  dependencies?: string[]
  queued_by: string  // 明确标注为必需字段
  notes?: string
}
```

### 验证结果

```bash
# 测试开始执行
curl -X POST http://localhost:8001/api/v1/test-plans/{id}/start \
  -H "Content-Type: application/json" \
  -d '{"started_by": "测试用户"}'
# Response: status="running" ✅

# 测试队列
curl -X POST http://localhost:8001/api/v1/test-plans/queue \
  -H "Content-Type: application/json" \
  -d '{"test_plan_id": "...", "queued_by": "测试用户", "priority": 5}'
# Response: 200 OK ✅
```

### 关键教训

1. **RESTful 设计原则** - 避免在请求体中重复URL路径参数
2. **Schema 设计一致性** - 所有控制操作都应遵循相同的模式
3. **必需字段要明确** - 前端类型定义应清晰标注哪些字段是必需的

---

**最后更新**: 2025-11-23 23:30
**负责人**: Claude
**优先级**: 🔴 高 - 已修复

---

## 🐛 BUG-004: 缺少状态转换功能

**优先级**: 🔴 高
**状态**: ✅ 已修复
**发现时间**: 2025-11-23 23:40
**修复时间**: 2025-11-23 23:50
**影响范围**: 测试计划状态管理

### 症状描述

用户报告："取消和暂停的测试计划无法恢复到draft，进入队列，执行等状态"

**缺少的状态转换**:
1. `paused` → `running` (恢复执行)
2. `queued` → `ready` (移出队列)
3. Terminal states (`cancelled`, `failed`, `completed`) → `draft` (重置为草稿)

### 根本原因

**UI实现不完整**：
- 后端API和hooks已经存在（`useResumeExecution`, `useRemoveFromQueue`）
- 但前端UI没有相应的按钮和处理函数
- 用户无法触发这些状态转换

### 修复方案

#### 1. 添加缺失的imports和hooks ([TestPlanList.tsx:44-55](gui/src/features/TestManagement/components/PlansTab/TestPlanList.tsx#L44-L55))

```tsx
import {
  useTestPlans,
  useDeleteTestPlan,
  useDuplicateTestPlan,
  useUpdateTestPlan,
  useQueueTestPlan,
  useStartExecution,
  usePauseExecution,
  useResumeExecution,      // ✅ 新增
  useCancelExecution,
  useRemoveFromQueue,      // ✅ 新增
} from '../../hooks'
```

#### 2. 添加handler函数 ([TestPlanList.tsx:169-196](gui/src/features/TestManagement/components/PlansTab/TestPlanList.tsx#L169-L196))

```tsx
const handleResume = (planId: string) => {
  resumeExecution({
    planId,
    payload: { resumed_by: '当前用户' },
  })
}

const handleRemoveFromQueue = (planId: string) => {
  removeFromQueue(planId, {
    onSuccess: () => {
      updatePlan({
        planId,
        payload: { status: 'ready' },
      })
    },
  })
}

const handleResetToDraft = (planId: string) => {
  updatePlan({
    planId,
    payload: { status: 'draft' },
  })
}
```

#### 3. 添加UI按钮 ([TestPlanList.tsx:389-410](gui/src/features/TestManagement/components/PlansTab/TestPlanList.tsx#L389-L410))

```tsx
{/* 恢复执行 - paused → running */}
{plan.status === 'paused' && (
  <Tooltip label="恢复执行">
    <ActionIcon variant="light" color="green" onClick={() => handleResume(plan.id)}>
      <IconPlayerPlay size={16} />
    </ActionIcon>
  </Tooltip>
)}

{/* 移出队列 - queued → ready */}
{plan.status === 'queued' && (
  <Tooltip label="移出队列">
    <ActionIcon variant="light" color="gray" onClick={() => handleRemoveFromQueue(plan.id)}>
      <IconPlayerStop size={16} />
    </ActionIcon>
  </Tooltip>
)}
```

#### 4. 添加菜单项 ([TestPlanList.tsx:441-449](gui/src/features/TestManagement/components/PlansTab/TestPlanList.tsx#L441-L449))

```tsx
{/* 重置为草稿 - terminal states → draft */}
{['cancelled', 'failed', 'completed'].includes(plan.status) && (
  <Menu.Item
    leftSection={<IconRefresh size={14} />}
    color="blue"
    onClick={() => handleResetToDraft(plan.id)}
  >
    重置为草稿
  </Menu.Item>
)}
```

### 完整的状态转换覆盖

修复后，所有状态转换都有对应的UI操作：

| 当前状态 | 转换到 | UI操作 | Handler |
|---------|--------|--------|---------|
| `draft` | `ready` | ✅ "标记为就绪" 按钮 | `handleMarkReady` |
| `ready` | `queued` | ✅ "添加到队列" 按钮 | `handleQueue` |
| `queued` | `running` | ✅ "开始执行" 按钮 | `handleStart` |
| `queued` | `ready` | ✅ "移出队列" 按钮 | `handleRemoveFromQueue` |
| `running` | `paused` | ✅ "暂停" 按钮 | `handlePause` |
| `paused` | `running` | ✅ "恢复执行" 按钮 | `handleResume` |
| `running/paused/queued` | `cancelled` | ✅ "取消执行" 菜单项 | `handleCancel` |
| `cancelled/failed/completed` | `draft` | ✅ "重置为草稿" 菜单项 | `handleResetToDraft` |

### 关键教训

1. **完整性检查** - 实现状态机时，必须确保所有转换都有UI支持
2. **参考文档** - [STATE-MACHINE.md](STATE-MACHINE.md) 明确定义了所有转换，应作为实现检查清单
3. **用户反馈驱动** - 用户实际使用时发现的缺失功能是最有价值的反馈

---

**最后更新**: 2025-11-23 23:50
**负责人**: Claude
**优先级**: 🔴 高 - 已修复
