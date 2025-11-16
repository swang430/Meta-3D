# Test Execution Engine Design

## 文档信息

- **文档版本**: 1.0.0
- **创建日期**: 2025-11-16
- **所属子系统**: Test Orchestration Subsystem
- **优先级**: P0 (CRITICAL)
- **状态**: Draft

## 1. 概述

### 1.1 目标

测试执行引擎（Test Execution Engine）负责执行测试计划，管理测试队列，协调硬件资源，实时采集数据并生成测试报告。

**核心功能**:
- **队列管理**: 测试任务排队、调度、优先级管理
- **并行执行**: 支持多测试并行执行
- **资源管理**: 硬件资源分配和释放
- **实时监控**: 执行进度、性能指标实时反馈
- **故障恢复**: 测试中断后自动恢复
- **结果收集**: 测量数据采集和结果聚合

### 1.2 执行流程

```
测试计划提交 → 队列调度 → 资源分配 → 执行测试 → 数据采集 → 结果验证 → 报告生成
```

## 2. 系统架构

```
┌─────────────────────────────────────────────────────────────────┐
│                    Test Execution Engine                         │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │         Execution Orchestrator                           │   │
│  │  - 主控制循环                                             │   │
│  │  - 状态机管理                                             │   │
│  └──────────────────────────────────────────────────────────┘   │
│                              ▼                                   │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │         Queue Manager                                    │   │
│  │  - 优先级队列                                             │   │
│  │  - 调度策略                                               │   │
│  └──────────────────────────────────────────────────────────┘   │
│                              ▼                                   │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │         Resource Manager                                 │   │
│  │  - 硬件资源池                                             │   │
│  │  - 资源锁                                                 │   │
│  └──────────────────────────────────────────────────────────┘   │
│                              ▼                                   │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │         Step Executor                                    │   │
│  │  - 步骤解释器                                             │   │
│  │  - HAL调用                                                │   │
│  └──────────────────────────────────────────────────────────┘   │
│                              ▼                                   │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │         Data Collector                                   │   │
│  │  - 实时测量采集                                            │   │
│  │  - 数据缓存                                               │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

## 3. 核心组件

### 3.1 Execution Orchestrator

```typescript
class ExecutionOrchestrator {
  async executeTestPlan(planId: string, context: ExecutionContext): Promise<TestExecution> {
    // 1. 加载测试计划
    const plan = await this.loadTestPlan(planId)

    // 2. 创建执行记录
    const execution = await this.createExecution(plan, context)

    // 3. 状态机循环
    while (!this.isTerminalState(execution.status)) {
      switch (execution.status) {
        case 'queued':
          await this.allocateResources(execution)
          execution.status = 'initializing'
          break

        case 'initializing':
          await this.initializeHardware(execution)
          execution.status = 'running'
          break

        case 'running':
          await this.executeSuites(execution)
          execution.status = 'finalizing'
          break

        case 'finalizing':
          await this.cleanupResources(execution)
          execution.status = 'completed'
          break
      }
    }

    return execution
  }
}
```

### 3.2 Queue Manager

```typescript
interface QueueManager {
  enqueue(execution: TestExecution, priority: number): void
  dequeue(): TestExecution | null
  getQueueStatus(): QueueStatus
  cancelExecution(executionId: string): void
}

interface QueueStatus {
  pending_count: number
  running_count: number
  max_concurrent: number
  estimated_wait_time_seconds: number
}
```

### 3.3 Resource Manager

```typescript
class ResourceManager {
  private resources: Map<string, ResourceLock> = new Map()

  async acquireResources(required: ResourceRequirement[]): Promise<ResourceHandle> {
    // 检查资源可用性
    for (const req of required) {
      if (!this.isAvailable(req)) {
        throw new Error(`Resource ${req.type} not available`)
      }
    }

    // 锁定资源
    const handle = await this.lockResources(required)
    return handle
  }

  async releaseResources(handle: ResourceHandle): Promise<void> {
    await this.unlockResources(handle)
  }
}

interface ResourceRequirement {
  type: 'channel_emulator' | 'base_station' | 'positioner' | 'chamber'
  id?: string  // 特定设备ID，如果为空则自动分配
  exclusive: boolean  // 是否独占
}
```

### 3.4 Step Executor

```typescript
class StepExecutor {
  async executeStep(step: TestStep, context: ExecutionContext): Promise<StepResult> {
    const startTime = Date.now()

    try {
      // 参数替换
      const params = this.substituteVariables(step.action.parameters, context)

      // 执行操作
      const result = await this.performAction(step.action.operation, params)

      // 等待（如果需要）
      if (step.wait_seconds) {
        await this.sleep(step.wait_seconds * 1000)
      }

      return {
        step_id: step.id,
        status: 'passed',
        duration_ms: Date.now() - startTime,
        output: result
      }
    } catch (error) {
      return {
        step_id: step.id,
        status: 'failed',
        duration_ms: Date.now() - startTime,
        error: error.message
      }
    }
  }

  private async performAction(operation: string, params: any): Promise<any> {
    switch (operation) {
      case 'configure_channel':
        return await channelEmulatorHAL.configureChannel(params)
      case 'register_ue':
        return await baseStationHAL.registerUE(params)
      case 'measure_throughput':
        return await baseStationHAL.getThroughput()
      // ... 其他操作
    }
  }
}
```

## 4. 数据库模式

```sql
-- 执行队列表
CREATE TABLE execution_queue (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  execution_id UUID REFERENCES test_executions(id),
  priority INTEGER DEFAULT 5,  -- 1 (highest) to 10 (lowest)
  queued_at TIMESTAMP DEFAULT NOW(),
  estimated_duration_seconds INTEGER,

  INDEX idx_priority_queued (priority, queued_at)
);

-- 资源锁表
CREATE TABLE resource_locks (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  resource_type VARCHAR(100),
  resource_id VARCHAR(255),
  execution_id UUID REFERENCES test_executions(id),
  locked_at TIMESTAMP DEFAULT NOW(),
  expires_at TIMESTAMP,

  UNIQUE(resource_type, resource_id),
  INDEX idx_execution_id (execution_id)
);
```

## 5. REST API

```typescript
// POST /api/v1/executions/{id}/pause
// POST /api/v1/executions/{id}/resume
// POST /api/v1/executions/{id}/cancel

// GET /api/v1/executions/queue
interface GetQueueResponse {
  queue: Array<{
    execution_id: string
    test_plan_name: string
    priority: number
    position: number
    estimated_start_time: Date
  }>
}

// WebSocket: /ws/executions/{id}
// 实时执行状态推送
interface ExecutionUpdateMessage {
  execution_id: string
  status: string
  progress_percent: number
  current_test_case: string
  measurements?: any
}
```

## 6. 实现计划

### Phase 1: 核心引擎 (2周)
- [ ] Execution Orchestrator
- [ ] Step Executor
- [ ] 状态机实现

### Phase 2: 队列和资源管理 (1周)
- [ ] Queue Manager
- [ ] Resource Manager
- [ ] 并发控制

### Phase 3: 监控和恢复 (1周)
- [ ] 实时监控
- [ ] 故障恢复
- [ ] WebSocket推送

## 7. 总结

Test Execution Engine实现：
- **高效调度**: 优先级队列，智能资源分配
- **并行执行**: 充分利用硬件资源
- **实时监控**: WebSocket实时推送执行状态
- **故障恢复**: 中断后自动恢复执行

是整个测试系统的核心执行引擎。
