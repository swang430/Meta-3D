# Test Plan Management Design

## 文档信息

- **文档版本**: 1.0.0
- **创建日期**: 2025-11-16
- **所属子系统**: Test Orchestration Subsystem (测试编排子系统)
- **优先级**: P0 (CRITICAL)
- **状态**: Draft

## 1. 概述

### 1.1 目标

测试计划管理（Test Plan Management）提供完整的测试生命周期管理，从测试计划创建、编辑、执行到结果归档。

**核心功能**:
- **测试计划CRUD**: 创建、读取、更新、删除测试计划
- **模板系统**: 预定义测试计划模板（日常测试、认证测试等）
- **参数化测试**: 支持测试变量和参数扫描
- **版本控制**: 测试计划版本管理
- **权限管理**: 基于角色的访问控制

### 1.2 测试层级

```
测试计划 (Test Plan)
  ├─ 测试套件 (Test Suite)
  │   ├─ 测试例 (Test Case)
  │   │   ├─ 测试步骤 (Test Step)
  │   │   │   ├─ 配置操作
  │   │   │   ├─ 执行操作
  │   │   │   └─ 验证操作
  │   │   └─ 断言 (Assertions)
  │   └─ 前置/后置操作
  └─ 全局配置
```

### 1.3 使用场景

| 测试类型 | 说明 | 典型规模 | 执行频率 |
|---------|------|---------|---------|
| 日常回归测试 | 快速验证基本功能 | 10-20 test cases | 每日 |
| 完整功能测试 | 验证所有功能点 | 50-100 test cases | 每周 |
| 认证测试 | 3GPP/CTIA符合性测试 | 100-500 test cases | 发布前 |
| 校准验证测试 | 校准后系统验证 | 20-30 test cases | 校准后 |
| 探索性测试 | 自定义参数扫描 | 变量（1-1000+） | 按需 |

## 2. 系统架构

### 2.1 分层架构

```
┌─────────────────────────────────────────────────────────────────┐
│                          UI Layer                                │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐           │
│  │ Test Plan    │  │ Template     │  │ Execution    │           │
│  │ Editor       │  │ Library      │  │ Monitor      │           │
│  └──────────────┘  └──────────────┘  └──────────────┘           │
└─────────────────────────────────────────────────────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Business Logic Layer                        │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │            Test Plan Service                             │   │
│  │  - CRUD operations                                       │   │
│  │  - Template management                                   │   │
│  │  - Version control                                       │   │
│  │  - Validation                                            │   │
│  └──────────────────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │            Execution Scheduler                           │   │
│  │  - Queue management                                      │   │
│  │  - Priority scheduling                                   │   │
│  │  - Resource allocation                                   │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Data Access Layer                           │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │              PostgreSQL Database                         │   │
│  │  - test_plans                                            │   │
│  │  - test_suites                                           │   │
│  │  - test_cases                                            │   │
│  │  - test_executions                                       │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 核心组件

#### 2.2.1 Test Plan Service
管理测试计划生命周期。

#### 2.2.2 Template Engine
处理测试模板和参数化。

#### 2.2.3 Validation Engine
验证测试计划完整性和正确性。

#### 2.2.4 Execution Scheduler
调度测试计划执行。

## 3. 数据模型

### 3.1 测试计划 (Test Plan)

```typescript
interface TestPlan {
  id: string
  name: string
  description: string
  version: string  // Semantic versioning: "1.2.3"

  // 分类和标签
  category: 'daily' | 'weekly' | 'certification' | 'calibration' | 'custom'
  tags: string[]  // ['5G', 'FR1', 'TRP', 'EIS']

  // 测试套件
  test_suites: TestSuite[]

  // 全局配置
  global_config: {
    // DUT配置
    dut: {
      type: 'smartphone' | 'vehicle' | 'module'
      model: string
      imei?: string
    }

    // 测试环境
    environment: {
      temperature_celsius: number
      humidity_percent: number
      chamber_config: string  // 暗室配置ID
    }

    // 硬件配置
    hardware: {
      channel_emulator_id: string
      base_station_id: string
      probe_array_config_id: string
    }

    // 超时和重试
    timeout: {
      test_case_timeout_seconds: number
      retry_on_failure: boolean
      max_retries: number
    }
  }

  // 参数化（变量定义）
  variables?: {
    [key: string]: {
      type: 'number' | 'string' | 'boolean' | 'array'
      default_value: any
      description: string
    }
  }

  // 元数据
  created_by: string
  created_at: Date
  updated_at: Date

  // 版本控制
  parent_version?: string  // 父版本ID（用于版本追溯）
  is_template: boolean  // 是否为模板
  template_id?: string  // 如果由模板创建，记录模板ID

  // 状态
  status: 'draft' | 'approved' | 'archived'
}
```

### 3.2 测试套件 (Test Suite)

```typescript
interface TestSuite {
  id: string
  name: string
  description: string

  // 测试例列表
  test_cases: TestCase[]

  // 前置/后置操作
  setup?: TestStep[]  // 在所有test cases前执行
  teardown?: TestStep[]  // 在所有test cases后执行

  // 执行策略
  execution_strategy: {
    parallel: boolean  // 是否并行执行test cases
    max_parallel: number  // 最大并行数
    stop_on_failure: boolean  // 失败时是否停止
  }

  // 排序
  order: number
}
```

### 3.3 测试例 (Test Case)

```typescript
interface TestCase {
  id: string
  name: string
  description: string

  // 测试类型
  test_type: 'TRP' | 'TIS' | 'EIS' | 'BLER' | 'Throughput' | 'Custom'

  // 测试步骤
  steps: TestStep[]

  // 前置/后置
  setup?: TestStep[]
  teardown?: TestStep[]

  // 断言（期望结果）
  assertions: Assertion[]

  // 超时
  timeout_seconds: number

  // 重试
  retry_on_failure: boolean
  max_retries: number

  // 排序
  order: number

  // 标签
  tags: string[]
}
```

### 3.4 测试步骤 (Test Step)

```typescript
interface TestStep {
  id: string
  name: string
  description: string

  // 步骤类型
  type: 'config' | 'execute' | 'verify' | 'wait' | 'loop'

  // 操作
  action: {
    // 操作类型
    operation:
      | 'configure_channel'
      | 'configure_base_station'
      | 'register_ue'
      | 'start_traffic'
      | 'measure_throughput'
      | 'measure_trp'
      | 'set_probe_weights'
      | 'rotate_dut'
      | 'custom_script'

    // 参数（根据operation不同而不同）
    parameters: {
      [key: string]: any
    }

    // 参数可以引用变量
    // 例如: { "frequency_ghz": "${freq}" }
  }

  // 条件执行
  condition?: {
    variable: string
    operator: '==' | '!=' | '>' | '<' | '>=' | '<='
    value: any
  }

  // 循环（用于参数扫描）
  loop?: {
    variable: string  // 循环变量名
    range: {
      start: number
      stop: number
      step: number
    } | any[]  // 数值范围或数组
  }

  // 等待时间
  wait_seconds?: number

  // 排序
  order: number
}
```

### 3.5 断言 (Assertion)

```typescript
interface Assertion {
  id: string
  name: string

  // 断言类型
  type: 'value' | 'range' | 'threshold' | 'custom'

  // 目标（要验证的值）
  target: {
    source: 'measurement' | 'variable' | 'constant'
    path: string  // 例如: "throughput.downlink.average_mbps"
  }

  // 断言条件
  condition: {
    operator: '==' | '!=' | '>' | '<' | '>=' | '<=' | 'between' | 'contains'
    expected_value: any
    tolerance?: number  // 容差（用于浮点数比较）
  }

  // 严重性
  severity: 'critical' | 'major' | 'minor'

  // 失败处理
  on_failure: 'stop' | 'continue' | 'retry'
}
```

### 3.6 测试执行 (Test Execution)

```typescript
interface TestExecution {
  id: string
  test_plan_id: string
  test_plan_version: string

  // 执行状态
  status: 'queued' | 'running' | 'completed' | 'failed' | 'cancelled'

  // 时间
  queued_at: Date
  started_at?: Date
  completed_at?: Date
  duration_seconds?: number

  // 执行上下文
  context: {
    // 参数值（变量的实际值）
    parameters: { [key: string]: any }

    // 执行环境快照
    environment_snapshot: {
      dut: any
      hardware: any
      calibration_status: any
    }
  }

  // 执行结果
  results: {
    total_test_cases: number
    passed_test_cases: number
    failed_test_cases: number
    skipped_test_cases: number

    // 详细结果
    test_case_results: TestCaseResult[]
  }

  // 执行日志
  logs: ExecutionLog[]

  // 错误信息
  error_message?: string

  // 执行者
  executed_by: string
}
```

### 3.7 测试例结果 (Test Case Result)

```typescript
interface TestCaseResult {
  test_case_id: string
  test_case_name: string

  status: 'passed' | 'failed' | 'skipped' | 'error'

  started_at: Date
  completed_at: Date
  duration_seconds: number

  // 步骤结果
  step_results: TestStepResult[]

  // 断言结果
  assertion_results: AssertionResult[]

  // 测量数据
  measurements: {
    [key: string]: any
  }

  // 错误信息
  error_message?: string
  stack_trace?: string
}
```

## 4. 数据库模式

```sql
-- 测试计划表
CREATE TABLE test_plans (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name VARCHAR(255) NOT NULL,
  description TEXT,
  version VARCHAR(50) NOT NULL,

  category VARCHAR(50),
  tags JSONB,

  global_config JSONB,
  variables JSONB,

  created_by VARCHAR(100),
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW(),

  parent_version UUID,  -- 自引用外键
  is_template BOOLEAN DEFAULT FALSE,
  template_id UUID,

  status VARCHAR(50) DEFAULT 'draft',

  INDEX idx_category (category),
  INDEX idx_status (status),
  INDEX idx_is_template (is_template),
  INDEX idx_created_at (created_at)
);

-- 测试套件表
CREATE TABLE test_suites (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  test_plan_id UUID REFERENCES test_plans(id) ON DELETE CASCADE,

  name VARCHAR(255) NOT NULL,
  description TEXT,

  setup JSONB,
  teardown JSONB,
  execution_strategy JSONB,

  order_index INTEGER,

  INDEX idx_test_plan_id (test_plan_id)
);

-- 测试例表
CREATE TABLE test_cases (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  test_suite_id UUID REFERENCES test_suites(id) ON DELETE CASCADE,

  name VARCHAR(255) NOT NULL,
  description TEXT,
  test_type VARCHAR(50),

  steps JSONB NOT NULL,
  setup JSONB,
  teardown JSONB,
  assertions JSONB,

  timeout_seconds INTEGER DEFAULT 300,
  retry_on_failure BOOLEAN DEFAULT FALSE,
  max_retries INTEGER DEFAULT 0,

  order_index INTEGER,
  tags JSONB,

  INDEX idx_test_suite_id (test_suite_id),
  INDEX idx_test_type (test_type)
);

-- 测试执行表
CREATE TABLE test_executions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  test_plan_id UUID REFERENCES test_plans(id),
  test_plan_version VARCHAR(50),

  status VARCHAR(50) DEFAULT 'queued',

  queued_at TIMESTAMP DEFAULT NOW(),
  started_at TIMESTAMP,
  completed_at TIMESTAMP,
  duration_seconds INTEGER,

  context JSONB,
  results JSONB,

  error_message TEXT,

  executed_by VARCHAR(100),

  INDEX idx_test_plan_id (test_plan_id),
  INDEX idx_status (status),
  INDEX idx_queued_at (queued_at)
);

-- 测试例结果表（细粒度）
CREATE TABLE test_case_results (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  execution_id UUID REFERENCES test_executions(id) ON DELETE CASCADE,
  test_case_id UUID REFERENCES test_cases(id),

  status VARCHAR(50),

  started_at TIMESTAMP,
  completed_at TIMESTAMP,
  duration_seconds INTEGER,

  step_results JSONB,
  assertion_results JSONB,
  measurements JSONB,

  error_message TEXT,
  stack_trace TEXT,

  INDEX idx_execution_id (execution_id),
  INDEX idx_test_case_id (test_case_id),
  INDEX idx_status (status)
);

-- 执行日志表
CREATE TABLE execution_logs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  execution_id UUID REFERENCES test_executions(id) ON DELETE CASCADE,

  level VARCHAR(20),  -- 'DEBUG', 'INFO', 'WARN', 'ERROR'
  message TEXT,
  timestamp TIMESTAMP DEFAULT NOW(),

  context JSONB,  -- 额外的上下文信息

  INDEX idx_execution_id (execution_id),
  INDEX idx_level (level),
  INDEX idx_timestamp (timestamp)
);
```

## 5. REST API设计

```typescript
// ============ 测试计划CRUD ============

// GET /api/v1/test-plans
interface ListTestPlansRequest {
  category?: string
  status?: string
  tags?: string[]
  is_template?: boolean
  page?: number
  page_size?: number
}

interface ListTestPlansResponse {
  test_plans: TestPlan[]
  total_count: number
  page: number
  page_size: number
}

// GET /api/v1/test-plans/{id}
interface GetTestPlanResponse {
  test_plan: TestPlan
}

// POST /api/v1/test-plans
interface CreateTestPlanRequest {
  test_plan: Omit<TestPlan, 'id' | 'created_at' | 'updated_at'>
}

interface CreateTestPlanResponse {
  test_plan: TestPlan
}

// PUT /api/v1/test-plans/{id}
interface UpdateTestPlanRequest {
  test_plan: Partial<TestPlan>
  create_new_version?: boolean  // 是否创建新版本
}

// DELETE /api/v1/test-plans/{id}
// 软删除，状态改为'archived'

// ============ 模板管理 ============

// GET /api/v1/test-plan-templates
interface ListTemplatesResponse {
  templates: TestPlan[]
}

// POST /api/v1/test-plan-templates/{id}/instantiate
interface InstantiateTemplateRequest {
  name: string
  parameters: { [key: string]: any }  // 模板变量的值
}

interface InstantiateTemplateResponse {
  test_plan: TestPlan
}

// ============ 版本管理 ============

// GET /api/v1/test-plans/{id}/versions
interface GetVersionHistoryResponse {
  versions: Array<{
    version: string
    created_at: Date
    created_by: string
    changes_summary: string
  }>
}

// POST /api/v1/test-plans/{id}/versions/{version}/restore
// 恢复到指定版本

// ============ 执行管理 ============

// POST /api/v1/test-plans/{id}/execute
interface ExecuteTestPlanRequest {
  parameters?: { [key: string]: any }  // 覆盖变量值
  priority?: 'low' | 'normal' | 'high'
  schedule?: {
    type: 'immediate' | 'scheduled'
    scheduled_at?: Date
  }
}

interface ExecuteTestPlanResponse {
  execution_id: string
  status: string
  estimated_duration_seconds: number
}

// GET /api/v1/test-executions
interface ListExecutionsRequest {
  test_plan_id?: string
  status?: string
  start_date?: Date
  end_date?: Date
}

// GET /api/v1/test-executions/{id}
interface GetExecutionResponse {
  execution: TestExecution
}

// POST /api/v1/test-executions/{id}/cancel
// 取消正在执行的测试

// ============ 验证 ============

// POST /api/v1/test-plans/{id}/validate
interface ValidateTestPlanResponse {
  valid: boolean
  errors: Array<{
    type: string
    message: string
    path: string  // 错误位置
  }>
  warnings: Array<{
    type: string
    message: string
  }>
}
```

## 6. 测试计划模板示例

### 6.1 日常回归测试模板

```yaml
name: "Daily Regression Test"
description: "快速验证系统基本功能"
category: "daily"
is_template: true

variables:
  freq_ghz:
    type: "number"
    default_value: 3.5
    description: "测试频率（GHz）"

test_suites:
  - name: "基本连通性测试"
    execution_strategy:
      parallel: false
      stop_on_failure: true

    test_cases:
      - name: "UE注册测试"
        test_type: "Custom"
        steps:
          - name: "配置小区"
            type: "config"
            action:
              operation: "configure_base_station"
              parameters:
                technology: "5G_NR"
                frequency_ghz: "${freq_ghz}"
                bandwidth_mhz: 100

          - name: "注册UE"
            type: "execute"
            action:
              operation: "register_ue"
              parameters:
                imsi: "123456789012345"

        assertions:
          - name: "UE注册成功"
            type: "value"
            target:
              source: "measurement"
              path: "ue.registered"
            condition:
              operator: "=="
              expected_value: true
            severity: "critical"

      - name: "下行吞吐量测试"
        test_type: "Throughput"
        steps:
          - name: "启动下行数据"
            type: "execute"
            action:
              operation: "start_traffic"
              parameters:
                direction: "downlink"
                target_throughput_mbps: 100
                duration_seconds: 10

          - name: "测量吞吐量"
            type: "execute"
            action:
              operation: "measure_throughput"

        assertions:
          - name: "吞吐量符合预期"
            type: "threshold"
            target:
              source: "measurement"
              path: "throughput.downlink.average_mbps"
            condition:
              operator: ">="
              expected_value: 80
              tolerance: 5
            severity: "major"
```

### 6.2 TRP认证测试模板

```yaml
name: "TRP Certification Test"
description: "3GPP TRP测试（符合TS 34.114）"
category: "certification"
is_template: true

variables:
  freq_ghz:
    type: "number"
    default_value: 3.5

  theta_step_deg:
    type: "number"
    default_value: 15
    description: "方位角步长"

  phi_step_deg:
    type: "number"
    default_value: 15
    description: "俯仰角步长"

test_suites:
  - name: "TRP测量"
    test_cases:
      - name: "3D TRP扫描"
        test_type: "TRP"
        timeout_seconds: 3600  # 1小时

        steps:
          - name: "配置DUT发射"
            type: "config"
            action:
              operation: "configure_dut_tx"
              parameters:
                power_dbm: 23
                modulation: "QPSK"

          - name: "3D扫描"
            type: "loop"
            loop:
              variable: "theta"
              range:
                start: 0
                stop: 360
                step: "${theta_step_deg}"
            action:
              operation: "loop"
              parameters:
                - type: "loop"
                  loop:
                    variable: "phi"
                    range:
                      start: 0
                      stop: 180
                      step: "${phi_step_deg}"
                  action:
                    operation: "rotate_dut"
                    parameters:
                      azimuth_deg: "${theta}"
                      elevation_deg: "${phi}"
                - type: "execute"
                  action:
                    operation: "measure_power"

          - name: "计算TRP"
            type: "execute"
            action:
              operation: "calculate_trp"

        assertions:
          - name: "TRP在合理范围"
            type: "range"
            target:
              source: "measurement"
              path: "trp_dbm"
            condition:
              operator: "between"
              expected_value: [15, 30]  # dBm
            severity: "critical"
```

## 7. 实现计划

### Phase 1: 核心数据模型 (1周)
- [ ] 数据库表创建
- [ ] TypeScript类型定义
- [ ] ORM映射（Prisma/TypeORM）

### Phase 2: CRUD API (1周)
- [ ] Test Plan CRUD
- [ ] Test Suite CRUD
- [ ] Test Case CRUD
- [ ] 验证逻辑

### Phase 3: 模板系统 (3天)
- [ ] 模板存储和加载
- [ ] 参数替换引擎
- [ ] 预定义模板库

### Phase 4: 版本控制 (3天)
- [ ] 版本创建和追溯
- [ ] 差异对比
- [ ] 版本恢复

### Phase 5: UI组件 (1周)
- [ ] Test Plan Editor
- [ ] Template Browser
- [ ] Execution Monitor

## 8. 总结

Test Plan Management为Meta-3D系统提供：

- **完整生命周期管理**: 从创建到执行到归档
- **模板化**: 快速创建标准测试计划
- **参数化**: 支持大规模参数扫描
- **版本控制**: 追溯测试计划演进
- **可扩展**: 支持自定义测试类型和操作

实现后，用户可高效管理数百个测试计划，支持日常测试到认证测试的全场景。
