# 执行状态同步设计指南

> 本文档记录了测试执行控制模块的设计教训和最终正确架构，供后续类似场景参考。

## 1. 问题背景

### 1.1 需求

实现"执行队列"（QueueTab）和"实时监控"（Monitoring）之间的双向状态同步：

- 从 QueueTab 发起的操作（开始/暂停/恢复/取消/完成）需要同步到 Monitoring
- 从 Monitoring 发起的操作需要同步到 QueueTab
- 页面切换或刷新后，状态需要正确恢复

### 1.2 遇到的问题

经过多轮迭代调试，发现以下问题：

| 问题 | 根因 | 分类 |
|------|------|------|
| QueueTab 暂停只发事件不调 API | 实现遗漏 | 设计不清 |
| 切换页面后状态丢失 | 无状态恢复逻辑 | 设计不清 |
| 事件触发重复 API 调用 | 职责边界不清 | 架构问题 |
| 缓存未刷新导致列表不同步 | 缺少 invalidation | 实现遗漏 |
| 暂停状态未正确处理 | useEffect 遗漏分支 | 实现错误 |
| 状态值中英文混用 | 无统一规范 | 设计不清 |
| 使用通用 API 而非专用 API | 代码混乱 | 架构问题 |
| 按钮禁用逻辑错误 | 逻辑错误 | 实现错误 |
| 开始按钮无法恢复暂停的执行 | 遗漏恢复功能 | 设计不清 |

## 2. 最终正确架构

### 2.1 状态机定义

```
                    ┌─────────────┐
                    │    idle     │
                    └──────┬──────┘
                           │ start
                           ▼
    ┌──────────────────────────────────────────┐
    │               running                     │
    │                                          │
    │   ◄────────── resume ──────────┐         │
    └──────┬───────────────────┬─────┴─────────┘
           │                   │
      pause│              cancel/complete
           ▼                   │
    ┌──────────────┐           │
    │   paused     │───────────┤
    └──────────────┘           │
           │                   │
      cancel/complete          │
           │                   ▼
           │            ┌──────────────┐
           └───────────►│  completed   │
                        │  cancelled   │
                        │   failed     │
                        └──────────────┘
```

### 2.2 状态值规范

**统一使用英文状态值**：

```typescript
type ExecutionStatus =
  | 'idle'       // 未开始
  | 'running'    // 执行中
  | 'paused'     // 已暂停
  | 'completed'  // 已完成
  | 'cancelled'  // 已取消
  | 'failed'     // 失败
```

### 2.3 组件职责划分

```
┌─────────────────────────────────────────────────────────────────┐
│                         App.tsx                                  │
│  - 持有执行状态 (demoRunProgress, executingPlanInfo)            │
│  - 提供操作函数 (handleDemoPause, handleDemoResume, etc.)       │
│  - 监听事件总线，响应子组件发起的操作                            │
│  - 调用后端 API（当操作来自 Monitoring）                         │
│  - 页面加载时恢复状态                                            │
└─────────────────────────────────────────────────────────────────┘
        │                                      │
        │ props                                │ props
        ▼                                      ▼
┌───────────────────┐                 ┌───────────────────┐
│    QueueTab       │                 │    Monitoring     │
│                   │                 │                   │
│ - 显示队列列表    │                 │ - 显示执行进度    │
│ - 调用后端 API    │                 │ - 接收 props 控制 │
│ - 发送事件通知    │                 │ - 调用 props 回调 │
│   App.tsx         │                 │                   │
└───────────────────┘                 └───────────────────┘
```

### 2.4 事件流向与 API 调用规则

**关键原则**：**谁发起操作，谁调用 API；事件只用于通知其他组件更新 UI**

#### 从 QueueTab 发起

```typescript
// QueueTab.tsx
const handlePause = (planId: string) => {
  // 1. 调用后端 API
  pauseExecution({ planId, payload: { paused_by: '当前用户' } }, {
    onSuccess: () => {
      // 2. API 成功后，发送事件通知 App.tsx 更新 UI
      appEventBus.emit({ type: 'execution:pause', payload: { planId } })
    },
  })
}
```

```typescript
// App.tsx - 监听事件
useEffect(() => {
  const unsubscribe = appEventBus.on('execution:pause', (event) => {
    if (executingPlanInfo?.id === event.payload.planId) {
      // 只更新 UI 状态，不调用 API（API 已由 QueueTab 调用）
      handleDemoPause(true) // fromEvent = true
    }
  })
  return unsubscribe
}, [executingPlanInfo, handleDemoPause])
```

#### 从 Monitoring 发起

```typescript
// Monitoring 组件
const handleTaskPause = () => {
  setExecStatus('paused')
  onPause() // 调用 App.tsx 传入的回调
}
```

```typescript
// App.tsx
const handleDemoPause = useCallback((fromEvent = false) => {
  // 1. 更新本地状态
  demoRunStatusRef.current = 'paused'
  setDemoRunProgress((prev) => ({ ...prev, status: 'paused' }))

  // 2. 如果不是来自事件（即来自 Monitoring），则调用 API 并发送事件
  if (executingPlanInfo && !fromEvent) {
    apiPauseExecution(executingPlanInfo.id, { paused_by: '当前用户' })
      .then(() => {
        queryClient.invalidateQueries({ queryKey: ['test-management', 'queue'] })
        queryClient.invalidateQueries({ queryKey: ['test-management', 'plans'] })
      })
    appEventBus.emit({ type: 'execution:pause', payload: { planId: executingPlanInfo.id } })
  }
}, [executingPlanInfo, queryClient])
```

### 2.5 fromEvent 参数模式

用于防止重复 API 调用：

```typescript
const handleDemoPause = useCallback((fromEvent = false) => {
  // 更新本地状态（总是执行）
  updateLocalState()

  // 只有非事件触发时才调用 API
  if (!fromEvent) {
    callBackendAPI()
    emitEvent()
  }
}, [])
```

### 2.6 缓存失效策略

每次状态变更后，需要使相关查询失效：

```typescript
// TanStack Query 缓存失效
queryClient.invalidateQueries({ queryKey: ['test-management', 'queue'] })
queryClient.invalidateQueries({ queryKey: ['test-management', 'plans'] })
```

在 hooks 中统一处理：

```typescript
// useTestExecution.ts
export function usePauseExecution() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({ planId, payload }) => api.pauseExecution(planId, payload),
    onSuccess: (updatedPlan) => {
      // 更新详情缓存
      queryClient.setQueryData(testPlansKeys.detail(updatedPlan.id), updatedPlan)
      // 使列表缓存失效
      queryClient.invalidateQueries({ queryKey: testPlansKeys.lists() })
      queryClient.invalidateQueries({ queryKey: testQueueKeys.list() })
    },
  })
}
```

### 2.7 状态恢复

页面加载时从后端恢复状态：

```typescript
// App.tsx
useEffect(() => {
  const restoreExecutionState = async () => {
    try {
      const queueItems = await getTestQueue()
      const activePlan = queueItems.find(
        (item) => item.test_plan.status === 'running' || item.test_plan.status === 'paused'
      )

      if (activePlan) {
        setExecutingPlanInfo({
          id: activePlan.test_plan.id,
          name: activePlan.test_plan.name,
        })

        const status = activePlan.test_plan.status === 'running' ? 'running' : 'paused'
        demoRunStatusRef.current = status
        setDemoRunProgress((prev) => ({ ...prev, status }))
      }
    } catch (error) {
      console.error('Failed to restore execution state:', error)
    }
  }

  restoreExecutionState()
}, [])
```

### 2.8 按钮状态矩阵

| 当前状态 | 开始按钮 | 暂停按钮 | 停止按钮 |
|---------|---------|---------|---------|
| idle | 可用（如有计划） | 禁用 | 禁用 |
| running | 禁用 | 可用 | 可用 |
| paused | 可用（恢复） | 禁用 | 可用 |
| completed | 可用（重新开始） | 禁用 | 禁用 |

```typescript
// Monitoring 按钮实现
<Button
  disabled={execStatus === 'running' || !hasPlanLoaded}
  onClick={handleTaskStart}
>
  开始
</Button>

<Button
  disabled={execStatus !== 'running' || !hasPlanLoaded}
  onClick={handleTaskPause}
>
  暂停
</Button>

<Button
  disabled={execStatus === 'idle' || !hasPlanLoaded}
  onClick={handleTaskStop}
>
  停止
</Button>
```

## 3. 事件总线定义

```typescript
// lib/eventBus.ts
export type ExecutionStartEvent = {
  type: 'execution:start'
  payload: { planId: string; planName: string }
}

export type ExecutionPauseEvent = {
  type: 'execution:pause'
  payload: { planId: string }
}

export type ExecutionResumeEvent = {
  type: 'execution:resume'
  payload: { planId: string }
}

export type ExecutionStopEvent = {
  type: 'execution:stop'
  payload: { planId: string }
}

export type ExecutionCompleteEvent = {
  type: 'execution:complete'
  payload: { planId: string }
}

export type AppEvent =
  | ExecutionStartEvent
  | ExecutionPauseEvent
  | ExecutionResumeEvent
  | ExecutionStopEvent
  | ExecutionCompleteEvent
```

## 4. 设计检查清单

在设计类似的双向同步功能时，确保回答以下问题：

### 4.1 状态定义
- [ ] 是否定义了完整的状态机图？
- [ ] 状态值是否统一规范（建议英文）？
- [ ] 是否涵盖所有可能的状态转换？

### 4.2 职责划分
- [ ] 哪个组件持有状态？
- [ ] 哪个组件调用后端 API？
- [ ] 事件总线的作用是什么？（只通知 UI 更新）

### 4.3 API 调用规则
- [ ] 是否使用专用 API（如 pauseExecution）而非通用 API（如 updateTestPlan）？
- [ ] 是否有 `fromEvent` 参数防止重复调用？
- [ ] API 成功后是否正确刷新缓存？

### 4.4 按钮状态
- [ ] 是否定义了按钮状态矩阵？
- [ ] 每个状态下哪些按钮可用、哪些禁用？
- [ ] 是否区分"开始新执行"和"恢复暂停执行"？

### 4.5 状态恢复
- [ ] 页面刷新后如何恢复状态？
- [ ] 切换页面后状态是否正确？

## 5. 经验总结

### 5.1 应该提前做的
1. **画状态机图** - 明确所有状态和转换
2. **定义职责边界** - 谁调 API、谁发事件、谁响应
3. **写按钮状态矩阵** - 每个状态下的 UI 表现
4. **统一命名规范** - 状态值、事件类型等

### 5.2 容易遗漏的点
1. 恢复（resume）与开始（start）是不同的操作
2. 切换页面后的状态恢复
3. 缓存失效导致列表不刷新
4. `fromEvent` 参数防止重复 API 调用

### 5.3 问题占比分析
- **设计问题（约 70%）**：状态机、职责划分、按钮矩阵未提前定义
- **迭代测试（约 30%）**：某些边界情况需要实际测试才能发现

---

*文档创建日期：2025-12-28*
*适用模块：TestManagement 执行控制*
