# 测试管理统一架构设计

> **版本**: 3.0
> **日期**: 2025-12-31
> **状态**: 已实现
> **目标**: 整合 TestConfig 和 TestPlanManagement，构建企业级测试管理平台

---

## 📋 目录

1. [背景与动机](#背景与动机)
2. [测试步骤来源](#测试步骤来源)
3. [架构概览](#架构概览)
4. [核心设计](#核心设计)
5. [数据模型](#数据模型)
6. [API 设计](#api-设计)
7. [组件结构](#组件结构)
8. [状态管理](#状态管理)
9. [用户工作流](#用户工作流)
10. [实施路线图](#实施路线图)
11. [迁移策略](#迁移策略)

---

## 背景与动机

### 当前问题

项目中存在两个功能重叠的测试计划管理模块：

#### 1. **TestConfig** (测试计划与编排) - 原始模块
```
位置: gui/src/App.tsx (2209-3900+ 行)
API:  /tests/plans (mock server, port 3000)
```

**优势**：
- ✅ 精细的步骤级参数编辑
- ✅ 拖拽排序
- ✅ 序列库集成
- ✅ TanStack Query 状态管理

**问题**：
- ❌ 代码耦合在 App.tsx 中
- ❌ 无执行队列功能
- ❌ 无历史追踪
- ❌ UI 复杂度高

#### 2. **TestPlanManagement** (测试计划管理) - 新模块
```
位置: gui/src/components/TestPlanManagement/
API:  /test-plans (real backend, port 8001)
```

**优势**：
- ✅ 完整的计划生命周期管理
- ✅ 执行队列（位置/优先级）
- ✅ 历史统计
- ✅ 8种状态工作流

**问题**：
- ❌ 缺少步骤编辑功能
- ❌ 无参数配置能力
- ❌ 未集成序列库

### 整合目标

构建**统一的测试管理平台**，融合两个模块的优势：

```
TestConfig 精华        +        TestPlanManagement 精华
     ↓                              ↓
  步骤编排                      生命周期管理
  参数配置                      队列 & 历史
  序列库集成                    状态工作流
     ↓                              ↓
            统一测试管理平台
       (Unified Test Management)
```

---

## 测试步骤来源

测试管理系统中的测试步骤来自两个不同的来源，每种来源有不同的用途和特点：

### 步骤来源概览

```
┌─────────────────────────────────────────────────────────────┐
│                    Test Plan Steps                          │
├─────────────────────────┬───────────────────────────────────┤
│  Virtual Road Test      │  Generic Test Steps               │
│  (虚拟路测步骤)          │  (通用测试步骤)                    │
├─────────────────────────┼───────────────────────────────────┤
│  8 predefined steps:    │  Flexible custom steps:           │
│  • environment_setup    │  • configure_instrument           │
│  • chamber_init         │  • run_measurement                │
│  • network_config       │  • validate_result                │
│  • base_station_setup   │  • generate_report                │
│  • ota_mapper           │  • wait                           │
│  • route_execution      │  • custom                         │
│  • kpi_validation       │                                   │
│  • report_generation    │  Parameters: JSON (flexible)      │
├─────────────────────────┴───────────────────────────────────┤
│  Auto-generated from     │  Manual creation via              │
│  scenario.step_config    │  sequence library                 │
└─────────────────────────────────────────────────────────────┘
```

### 1. Virtual Road Test Steps (虚拟路测步骤)

**来源**: `scenario.step_configuration`

当创建基于虚拟路测场景的测试计划时，系统自动生成8个预定义步骤：

| 步骤 | 名称 | 功能 |
|------|------|------|
| 1 | Configure Digital Twin Environment | 配置数字孪生环境 |
| 2 | Initialize OTA Chamber (MPAC) | 初始化暗室和转台 |
| 3 | Configure Network | 配置网络参数 |
| 4 | Setup Base Stations and Channel Model | 配置基站和信道模型 |
| 5 | Configure OTA Mapper | 配置OTA映射器 |
| 6 | Execute Route Test | 执行路径测试 |
| 7 | Validate KPIs and Performance Metrics | 验证KPI指标 |
| 8 | Generate Test Report | 生成测试报告 |

**参数优先级**:
```
scenario.step_configuration > test_environment > 默认值
```

**实现位置**: `api-service/app/services/test_plan_service.py:60-217`

### 2. Generic Test Steps (通用测试步骤)

**来源**: 序列库 (Sequence Library) + 手动创建

通用测试步骤支持灵活的自定义配置，适用于非虚拟路测场景：

| 步骤类型 | 用途 |
|----------|------|
| `configure_instrument` | 配置测试仪器 |
| `run_measurement` | 执行测量 |
| `validate_result` | 验证测试结果 |
| `generate_report` | 生成报告 |
| `wait` | 等待/延时 |
| `custom` | 自定义操作 |

**参数结构**: 灵活的 JSON 格式
```json
{
  "instrument_id": "channel_emulator_1",
  "measurement_type": "throughput",
  "frequency_mhz": 3700,
  "power_dbm": -10,
  "custom_key": "custom_value"
}
```

**Schema 定义**: `api-service/app/schemas/test_plan.py:326-408`

### 参数速查

完整的参数列表请参考:
- [参数速查表 (手动维护)](../virtual-road-test/parameter-reference.md)
- [参数速查表 (自动生成)](../virtual-road-test/parameter-reference-generated.md)

---

## 架构概览

### 系统架构图

```
┌─────────────────────────────────────────────────────────────┐
│                     前端应用 (React)                         │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌──────────────────────────────────────────────────────┐  │
│  │         统一测试管理 (Test Management)                │  │
│  ├──────────────────────────────────────────────────────┤  │
│  │                                                       │  │
│  │  ┌───────┐  ┌───────┐  ┌───────┐  ┌───────┐        │  │
│  │  │ 计划  │  │ 编排  │  │ 队列  │  │ 历史  │        │  │
│  │  │ Plans │  │ Steps │  │ Queue │  │History│        │  │
│  │  └───┬───┘  └───┬───┘  └───┬───┘  └───┬───┘        │  │
│  │      │          │          │          │             │  │
│  │      └──────────┴──────────┴──────────┘             │  │
│  │                     │                                │  │
│  │         ┌───────────▼────────────┐                  │  │
│  │         │  TanStack Query Cache  │                  │  │
│  │         └───────────┬────────────┘                  │  │
│  │                     │                                │  │
│  └─────────────────────┼────────────────────────────────┘  │
│                        │                                   │
│              ┌─────────▼─────────┐                        │
│              │  Unified API      │                        │
│              │  Service Layer    │                        │
│              └─────────┬─────────┘                        │
└────────────────────────┼─────────────────────────────────┘
                         │
                         │ HTTP/REST
                         │
┌────────────────────────▼─────────────────────────────────┐
│                   后端 API (FastAPI)                      │
├──────────────────────────────────────────────────────────┤
│                                                           │
│  /api/v1/test-management/                                │
│  ├── /plans              (计划 CRUD)                      │
│  ├── /plans/{id}/steps   (步骤管理) ⭐ NEW                │
│  ├── /queue              (执行队列)                       │
│  ├── /execution          (执行控制)                       │
│  ├── /history            (执行历史)                       │
│  └── /sequence-library   (序列库)                         │
│                                                           │
└───────────────────────────┬───────────────────────────────┘
                            │
                            ▼
                    ┌───────────────┐
                    │   PostgreSQL  │
                    │   Database    │
                    └───────────────┘
```

### 模块层次结构

```
gui/src/features/TestManagement/          ← 新的统一根目录
│
├── TestManagement.tsx                     ← 主容器 (Tab 布局)
│
├── components/                            ← UI 组件层
│   ├── PlansTab/                         ← Tab 1: 计划管理
│   ├── StepsTab/                         ← Tab 2: 步骤编排 ⭐
│   ├── QueueTab/                         ← Tab 3: 执行队列
│   └── HistoryTab/                       ← Tab 4: 执行历史
│
├── hooks/                                 ← 业务逻辑层
│   ├── useTestPlans.ts
│   ├── useTestSteps.ts                   ← NEW
│   ├── useQueue.ts
│   └── useHistory.ts
│
├── api/                                   ← API 层
│   └── testManagementAPI.ts              ← 统一 API 客户端
│
├── types/                                 ← 类型定义
│   └── index.ts                          ← 统一类型系统
│
└── utils/                                 ← 工具函数
    ├── validators.ts
    └── formatters.ts
```

---

## 核心设计

### 设计原则

1. **关注点分离** (Separation of Concerns)
   - UI 组件专注渲染
   - Hooks 封装业务逻辑
   - API 层统一数据获取

2. **单一数据源** (Single Source of Truth)
   - TanStack Query 管理所有服务端状态
   - 组件间通过 query cache 共享数据

3. **模块化** (Modularity)
   - 每个 Tab 独立开发
   - 可独立测试和维护

4. **可扩展性** (Extensibility)
   - 易于添加新的测试类型
   - 易于扩展新功能

### Tab 设计

#### Tab 1: 计划管理 (Plans)
```
功能:
- 计划列表 (Table)
- 状态过滤 (8种状态)
- 搜索 & 排序
- 创建/编辑向导
- 快捷操作 (入队、开始、删除)

来源: 主要来自 TestPlanManagement
增强: 添加内联编辑功能
```

#### Tab 2: 步骤编排 (Steps) ⭐ **核心创新**
```
功能:
- 选择当前计划
- 步骤列表 (拖拽排序)
- 添加步骤 (序列库选择器)
- 参数编辑器 (动态表单)
- 保存 & 预览

来源: TestConfig 核心功能
布局: 分割视图 (左侧列表 + 右侧编辑器)
```

#### Tab 3: 执行队列 (Queue)
```
功能:
- 队列表格
- 位置调整 (上移/下移)
- 优先级设置
- 开始/暂停/取消
- 自动刷新 (10s)

来源: TestPlanManagement
```

#### Tab 4: 执行历史 (History)
```
功能:
- 历史记录表格
- 统计卡片 (成功率、时长)
- 时间范围过滤
- 导出报告

来源: TestPlanManagement
```

---

## 数据模型

### 统一数据模型

#### 1. UnifiedTestPlan（统一测试计划）

```typescript
interface UnifiedTestPlan {
  // ===== 基础信息 =====
  id: string
  name: string
  description: string
  version: string
  status: TestPlanStatus  // 8种状态

  // ===== DUT 信息 (from TestPlanManagement) =====
  dut_info: {
    model: string        // 设备型号
    serial: string       // 序列号
    imei?: string        // IMEI (可选)
  }

  // ===== 测试环境 (from TestPlanManagement) =====
  test_environment: {
    chamber_id: string   // 暗室ID
    temperature: number  // 温度 (°C)
    humidity: number     // 湿度 (%)
  }

  // ===== 步骤配置 (from TestConfig) ⭐ 关键整合点 =====
  steps: TestStep[]      // 步骤数组

  // ===== 测试例关联 (from TestPlanManagement) =====
  test_case_ids: string[]

  // ===== 执行统计 (from TestPlanManagement) =====
  total_test_cases: number
  completed_test_cases: number
  failed_test_cases: number

  // ===== 队列信息 (from TestPlanManagement) =====
  queue_position?: number
  priority: number       // 1-10, 10最高

  // ===== 时间追踪 (from TestPlanManagement) =====
  estimated_duration_minutes?: number
  actual_duration_minutes?: number
  started_at?: string    // ISO 8601
  completed_at?: string  // ISO 8601

  // ===== 元数据 =====
  created_by: string
  created_at: string
  updated_at: string
  notes?: string
  tags?: string[]
}
```

#### 2. TestStep（测试步骤）

**当前实现** (基于 `api-service/app/schemas/test_plan.py:370-402`)

```typescript
interface TestStep {
  // ===== 标识信息 =====
  id: UUID
  test_plan_id: UUID
  sequence_library_id?: UUID           // 关联序列库模板 (可选)

  // ===== 步骤元数据 =====
  step_number?: number                 // 步骤序号
  name?: string                        // 步骤名称
  description?: string                 // 步骤描述
  type?: string                        // 步骤类型 (configure_instrument, run_measurement, etc.)
  category?: string                    // 步骤分类 (从序列库继承)

  // ===== 参数配置 =====
  parameters?: Record<string, any>     // 灵活的 JSON 参数

  // ===== 执行配置 =====
  order: number                        // 执行顺序
  timeout_seconds?: number             // 超时时间 (默认: 300s)
  retry_count?: number                 // 重试次数 (默认: 0)
  continue_on_failure?: boolean        // 失败是否继续 (默认: false)
  expected_duration_minutes?: number   // 预期时长

  // ===== 执行状态 =====
  status: 'pending' | 'running' | 'completed' | 'failed' | 'skipped'
  result?: string                      // 执行结果
  error_message?: string               // 错误信息
  actual_duration_minutes?: number     // 实际时长
  started_at?: datetime                // 开始时间
  completed_at?: datetime              // 完成时间

  // ===== 验证配置 =====
  validation_criteria?: {
    min_value?: number
    max_value?: number
    unit?: string
    pass_condition?: string            // ">=", "<=", "==", etc.
    tolerance_percent?: number
  }

  // ===== 元数据 =====
  notes?: string
  tags?: string[]
  created_at: datetime
  updated_at: datetime

  // ===== 前端兼容字段 =====
  title?: string                       // 从 sequence.name 填充
}
```

**创建步骤的两种方式**:

1. **从序列库创建** (`TestStepCreateFromSequence`):
```typescript
{
  sequence_library_id: UUID,           // 必填: 序列库ID
  order: number,                       // 必填: 执行顺序
  parameters?: Record<string, any>,    // 可选: 覆盖参数
  timeout_seconds?: number,            // 可选: 超时 (默认: 300)
  retry_count?: number,                // 可选: 重试次数 (默认: 0)
  continue_on_failure?: boolean        // 可选: 失败继续 (默认: false)
}
```

2. **手动创建** (`TestStepCreate`):
```typescript
{
  test_plan_id: UUID,                  // 必填: 测试计划ID
  step_number: number,                 // 必填: 步骤序号
  name: string,                        // 必填: 步骤名称
  type: string,                        // 必填: 步骤类型
  order: number,                       // 必填: 执行顺序
  parameters?: Record<string, any>,    // 可选: 步骤参数
  description?: string,
  expected_duration_minutes?: number,
  validation_criteria?: object,
  notes?: string,
  tags?: string[]
}
```

#### 3. StepParameter（步骤参数）

```typescript
interface StepParameter {
  // 参数元数据
  type: 'text' | 'number' | 'select' | 'textarea' | 'boolean' | 'json'
  label: string
  description?: string

  // 参数值
  value: any
  defaultValue?: any

  // 验证规则
  required: boolean
  validation?: {
    min?: number           // 数值最小值
    max?: number           // 数值最大值
    pattern?: string       // 正则表达式
    options?: string[]     // 选项列表 (for select)
  }

  // UI 配置
  placeholder?: string
  unit?: string            // 单位 (如 MHz, dBm)
  groupId?: string         // 参数分组
}
```

#### 4. TestPlanStatus（测试计划状态）

```typescript
type TestPlanStatus =
  | 'draft'         // 草稿 - 正在编辑
  | 'ready'         // 就绪 - 可以入队
  | 'queued'        // 已入队 - 等待执行
  | 'running'       // 执行中
  | 'paused'        // 已暂停
  | 'completed'     // 已完成
  | 'failed'        // 失败
  | 'cancelled'     // 已取消
```

#### 5. SequenceLibraryItem（序列库模板）

```typescript
interface SequenceLibraryItem {
  id: string
  title: string
  description: string
  category: string
  tags: string[]

  // 默认参数模板
  defaultParameters: Record<string, StepParameter>

  // 版本信息
  version: string
  author: string
  created_at: string
  updated_at: string

  // 使用统计
  usage_count: number
  popularity_score: number
}
```

### 数据库 Schema（PostgreSQL）

```sql
-- 测试计划表
CREATE TABLE test_plans (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    description TEXT,
    version VARCHAR(50) DEFAULT '1.0.0',
    status VARCHAR(50) NOT NULL,

    -- DUT 信息 (JSON)
    dut_info JSONB,

    -- 测试环境 (JSON)
    test_environment JSONB,

    -- 测试例ID数组
    test_case_ids TEXT[],

    -- 执行统计
    total_test_cases INTEGER DEFAULT 0,
    completed_test_cases INTEGER DEFAULT 0,
    failed_test_cases INTEGER DEFAULT 0,

    -- 队列信息
    queue_position INTEGER,
    priority INTEGER DEFAULT 5,

    -- 时间追踪
    estimated_duration_minutes INTEGER,
    actual_duration_minutes INTEGER,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,

    -- 元数据
    created_by VARCHAR(100),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    notes TEXT,
    tags TEXT[],

    -- 索引
    INDEX idx_status (status),
    INDEX idx_priority (priority),
    INDEX idx_created_by (created_by),
    INDEX idx_created_at (created_at)
);

-- 测试步骤表 ⭐ NEW
CREATE TABLE test_steps (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    test_plan_id UUID NOT NULL REFERENCES test_plans(id) ON DELETE CASCADE,

    order_index INTEGER NOT NULL,
    sequence_library_id UUID,

    title VARCHAR(255) NOT NULL,
    description TEXT,
    category VARCHAR(100),

    -- 参数配置 (JSON)
    parameters JSONB,

    -- 执行配置
    timeout_seconds INTEGER DEFAULT 300,
    retry_count INTEGER DEFAULT 0,
    continue_on_failure BOOLEAN DEFAULT FALSE,

    -- 状态
    status VARCHAR(50),
    result TEXT,
    error_message TEXT,

    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),

    -- 索引
    INDEX idx_test_plan_order (test_plan_id, order_index),
    UNIQUE (test_plan_id, order_index)
);

-- 序列库表
CREATE TABLE sequence_library (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title VARCHAR(255) NOT NULL,
    description TEXT,
    category VARCHAR(100),
    tags TEXT[],

    default_parameters JSONB,

    version VARCHAR(50) DEFAULT '1.0.0',
    author VARCHAR(100),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),

    usage_count INTEGER DEFAULT 0,
    popularity_score FLOAT DEFAULT 0.0,

    INDEX idx_category (category),
    INDEX idx_popularity (popularity_score DESC)
);
```

---

## API 设计

### 统一 API 端点

#### Base URL
```
http://localhost:8001/api/v1/test-management
```

### 1. 计划管理 API

#### 1.1 列表查询
```http
GET /plans?skip=0&limit=100&status=ready&search=keyword
```

**Response:**
```json
{
  "total": 42,
  "items": [
    {
      "id": "uuid",
      "name": "5G NR TRP Test Plan",
      "status": "ready",
      "priority": 8,
      "total_test_cases": 12,
      "completed_test_cases": 0,
      "created_by": "user@example.com",
      "created_at": "2025-11-18T10:00:00Z"
    }
  ]
}
```

#### 1.2 创建计划
```http
POST /plans
Content-Type: application/json

{
  "name": "5G NR TRP Test Plan",
  "description": "Complete TRP testing for 5G NR bands",
  "dut_info": {
    "model": "iPhone 15 Pro",
    "serial": "ABC123456",
    "imei": "123456789012345"
  },
  "test_environment": {
    "chamber_id": "MPAC-01",
    "temperature": 23.0,
    "humidity": 45.0
  },
  "priority": 8,
  "created_by": "user@example.com"
}
```

#### 1.3 更新计划
```http
PATCH /plans/{id}
Content-Type: application/json

{
  "name": "Updated Plan Name",
  "priority": 10
}
```

#### 1.4 删除计划
```http
DELETE /plans/{id}
```

### 2. 步骤管理 API ⭐ **NEW**

#### 2.1 获取计划步骤
```http
GET /plans/{id}/steps
```

**Response:**
```json
{
  "plan_id": "uuid",
  "steps": [
    {
      "id": "step-uuid",
      "order": 1,
      "sequence_library_id": "lib-uuid",
      "title": "Configure Test Frequency",
      "description": "Set frequency to 3.5 GHz",
      "parameters": {
        "frequency": {
          "type": "number",
          "label": "Frequency",
          "value": 3500,
          "unit": "MHz",
          "validation": { "min": 600, "max": 6000 }
        },
        "bandwidth": {
          "type": "select",
          "label": "Bandwidth",
          "value": "100",
          "validation": { "options": ["20", "40", "100"] }
        }
      },
      "timeout_seconds": 300,
      "continue_on_failure": false
    }
  ]
}
```

#### 2.2 添加步骤
```http
POST /plans/{id}/steps
Content-Type: application/json

{
  "sequence_library_id": "lib-uuid",
  "order": 2,
  "parameters": {
    "frequency": { "value": 3500 },
    "power": { "value": 23 }
  }
}
```

#### 2.3 更新步骤参数
```http
PATCH /plans/{planId}/steps/{stepId}
Content-Type: application/json

{
  "parameters": {
    "frequency": { "value": 5000 }
  }
}
```

#### 2.4 删除步骤
```http
DELETE /plans/{planId}/steps/{stepId}
```

#### 2.5 重排序步骤
```http
PUT /plans/{id}/steps/reorder
Content-Type: application/json

{
  "step_orders": [
    { "step_id": "uuid1", "order": 1 },
    { "step_id": "uuid2", "order": 2 },
    { "step_id": "uuid3", "order": 3 }
  ]
}
```

### 3. 队列管理 API

#### 3.1 获取队列
```http
GET /queue?skip=0&limit=100
```

#### 3.2 加入队列
```http
POST /queue
Content-Type: application/json

{
  "test_plan_id": "uuid",
  "priority": 8,
  "scheduled_start_time": "2025-11-18T14:00:00Z",
  "dependencies": ["uuid1", "uuid2"],
  "queued_by": "user@example.com",
  "notes": "Run after calibration"
}
```

#### 3.3 调整队列位置
```http
PATCH /queue/{planId}/reorder
Content-Type: application/json

{
  "new_position": 3
}
```

### 4. 执行控制 API

#### 4.1 开始执行
```http
POST /execution/{id}/start
Content-Type: application/json

{
  "started_by": "user@example.com"
}
```

#### 4.2 暂停执行
```http
POST /execution/{id}/pause
Content-Type: application/json

{
  "paused_by": "user@example.com",
  "reason": "Equipment maintenance"
}
```

#### 4.3 恢复执行
```http
POST /execution/{id}/resume
Content-Type: application/json

{
  "resumed_by": "user@example.com"
}
```

#### 4.4 取消执行
```http
POST /execution/{id}/cancel
Content-Type: application/json

{
  "cancelled_by": "user@example.com",
  "reason": "Test plan outdated"
}
```

### 5. 历史查询 API

```http
GET /history?skip=0&limit=20&status=completed&start_date=2025-11-01
```

### 6. 序列库 API

```http
GET /sequence-library?category=calibration
```

---

## 组件结构

### 主容器组件

**TestManagement.tsx**
```typescript
import { Container, Tabs } from '@mantine/core'
import { PlansTab } from './components/PlansTab'
import { StepsTab } from './components/StepsTab'
import { QueueTab } from './components/QueueTab'
import { HistoryTab } from './components/HistoryTab'

export function TestManagement() {
  return (
    <Container size="xl" py="md">
      <Tabs defaultValue="plans">
        <Tabs.List>
          <Tabs.Tab value="plans">计划管理</Tabs.Tab>
          <Tabs.Tab value="steps">步骤编排</Tabs.Tab>
          <Tabs.Tab value="queue">执行队列</Tabs.Tab>
          <Tabs.Tab value="history">执行历史</Tabs.Tab>
        </Tabs.List>

        <Tabs.Panel value="plans"><PlansTab /></Tabs.Panel>
        <Tabs.Panel value="steps"><StepsTab /></Tabs.Panel>
        <Tabs.Panel value="queue"><QueueTab /></Tabs.Panel>
        <Tabs.Panel value="history"><HistoryTab /></Tabs.Panel>
      </Tabs>
    </Container>
  )
}
```

### Tab 组件详细设计

#### PlansTab（计划管理）

**组件树:**
```
PlansTab
├── PlansHeader
│   ├── SearchInput
│   ├── StatusFilter
│   └── CreateButton → PlanWizard
│
├── PlansTable
│   ├── TableRow (for each plan)
│   │   ├── PlanInfo
│   │   ├── StatusBadge
│   │   ├── ProgressBar
│   │   └── ActionMenu
│   │       ├── EditAction → PlanWizard
│   │       ├── EditStepsAction → Navigate to Steps Tab
│   │       ├── QueueAction → Add to queue
│   │       └── DeleteAction → Confirmation Dialog
│   └── Pagination
│
└── PlanWizard (Modal)
    ├── Step1: BasicInfo
    ├── Step2: DUTInfo
    ├── Step3: Environment
    └── Step4: Summary
```

#### StepsTab（步骤编排）⭐

**布局:**
```
┌──────────────────────────────────────────────────────────┐
│  ┌─────────────────────────────────────────────────┐    │
│  │ 选择计划: [5G NR TRP Test Plan ▼]  [保存步骤]   │    │
│  └─────────────────────────────────────────────────┘    │
│                                                          │
│  ┌─────────────────┐  ┌─────────────────────────────┐  │
│  │  步骤列表        │  │  参数编辑器                  │  │
│  │                 │  │                              │  │
│  │  1. [⋮] Step 1  │  │  ┌─────────────────────────┐│  │
│  │  2. [⋮] Step 2  │  │  │ 步骤: Configure Freq   ││  │
│  │  3. [⋮] Step 3  │  │  ├─────────────────────────┤│  │
│  │                 │  │  │ 参数配置:               ││  │
│  │  [+ 添加步骤]    │  │  │ Frequency: [3500] MHz  ││  │
│  │                 │  │  │ Bandwidth: [100 ▼]     ││  │
│  │                 │  │  │ Power: [23] dBm        ││  │
│  │                 │  │  └─────────────────────────┘│  │
│  └─────────────────┘  └─────────────────────────────┘  │
└──────────────────────────────────────────────────────────┘
```

**组件树:**
```
StepsTab
├── StepsHeader
│   ├── PlanSelector (Dropdown)
│   └── SaveButton
│
├── SplitView
│   ├── LeftPanel: StepsList
│   │   ├── StepItem (Draggable)
│   │   │   ├── DragHandle
│   │   │   ├── StepTitle
│   │   │   ├── StepSummary
│   │   │   └── RemoveButton
│   │   └── AddStepButton → SequenceLibraryModal
│   │
│   └── RightPanel: ParameterEditor
│       ├── StepMetadata
│       ├── ParameterForm (Dynamic)
│       │   ├── TextField
│       │   ├── NumberField
│       │   ├── SelectField
│       │   └── TextareaField
│       └── ExecutionConfig
│           ├── TimeoutInput
│           ├── RetryCountInput
│           └── ContinueOnFailureToggle
│
└── SequenceLibraryModal
    ├── CategoryTabs
    ├── SearchInput
    ├── LibraryGrid
    │   └── LibraryCard (for each template)
    └── AddButton
```

---

## 状态管理

### TanStack Query 策略

#### Query Keys 结构

```typescript
const queryKeys = {
  // 计划相关
  plans: ['test-plans'] as const,
  plansList: (filters?: PlanFilters) =>
    ['test-plans', 'list', filters] as const,
  planDetail: (id: string) =>
    ['test-plans', 'detail', id] as const,

  // 步骤相关 ⭐ NEW
  steps: (planId: string) =>
    ['test-plans', planId, 'steps'] as const,

  // 队列相关
  queue: ['queue'] as const,
  queueList: () => ['queue', 'list'] as const,

  // 历史相关
  history: (filters?: HistoryFilters) =>
    ['history', filters] as const,

  // 序列库
  sequenceLibrary: ['sequence-library'] as const,
}
```

#### Hooks 实现

**useTestPlans.ts**
```typescript
export function useTestPlans(filters?: PlanFilters) {
  return useQuery({
    queryKey: queryKeys.plansList(filters),
    queryFn: () => fetchTestPlans(filters),
    staleTime: 30000, // 30秒
  })
}

export function useTestPlan(id: string) {
  return useQuery({
    queryKey: queryKeys.planDetail(id),
    queryFn: () => fetchTestPlan(id),
    enabled: !!id,
  })
}

export function useCreateTestPlan() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: createTestPlan,
    onSuccess: () => {
      // 无效化列表查询
      queryClient.invalidateQueries({
        queryKey: queryKeys.plans
      })
    },
  })
}
```

**useTestSteps.ts** ⭐ **NEW**
```typescript
export function useTestSteps(planId: string) {
  return useQuery({
    queryKey: queryKeys.steps(planId),
    queryFn: () => fetchTestSteps(planId),
    enabled: !!planId,
  })
}

export function useUpdateStepParameter() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({
      planId,
      stepId,
      parameters
    }: UpdateStepParams) =>
      updateStepParameter(planId, stepId, parameters),

    onMutate: async ({ planId, stepId, parameters }) => {
      // 乐观更新
      await queryClient.cancelQueries({
        queryKey: queryKeys.steps(planId)
      })

      const previousSteps = queryClient.getQueryData(
        queryKeys.steps(planId)
      )

      queryClient.setQueryData(
        queryKeys.steps(planId),
        (old: TestStep[]) =>
          old.map(step =>
            step.id === stepId
              ? { ...step, parameters }
              : step
          )
      )

      return { previousSteps }
    },

    onError: (err, variables, context) => {
      // 回滚
      queryClient.setQueryData(
        queryKeys.steps(variables.planId),
        context?.previousSteps
      )
    },

    onSettled: (data, error, { planId }) => {
      // 重新获取
      queryClient.invalidateQueries({
        queryKey: queryKeys.steps(planId)
      })
    },
  })
}

export function useReorderSteps() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({ planId, stepOrders }: ReorderParams) =>
      reorderSteps(planId, stepOrders),

    onSuccess: (_, { planId }) => {
      queryClient.invalidateQueries({
        queryKey: queryKeys.steps(planId)
      })
    },
  })
}
```

---

## 用户工作流

### 工作流 1: 创建完整测试计划

```
1. 用户进入 "计划" Tab
   ↓
2. 点击 "创建测试计划" 按钮
   ↓
3. 进入创建向导:
   Step 1: 填写基本信息 (名称、描述、版本)
   Step 2: 填写 DUT 信息 (型号、序列号、IMEI)
   Step 3: 配置测试环境 (暗室、温度、湿度)
   Step 4: 预览并确认
   ↓
4. 计划创建成功 (status = 'draft')
   ↓
5. 自动跳转到 "步骤" Tab 或提示用户编排步骤
   ↓
6. 用户在步骤 Tab 中:
   - 选择刚创建的计划
   - 点击 "添加步骤"
   - 从序列库选择模板
   - 配置步骤参数
   - 重复添加多个步骤
   - 拖拽调整步骤顺序
   ↓
7. 点击 "保存步骤" → 步骤持久化到后端
   ↓
8. 返回 "计划" Tab
   ↓
9. 点击计划行的 "标记就绪" 按钮
   ↓
10. 计划状态变为 'ready'，可以入队执行
```

### 工作流 2: 执行测试计划

```
1. 用户在 "计划" Tab 选择就绪的计划
   ↓
2. 点击 "加入队列" 按钮
   ↓
3. 填写队列信息:
   - 优先级 (1-10)
   - 预定开始时间 (可选)
   - 依赖关系 (可选)
   - 备注
   ↓
4. 计划加入队列 (status = 'queued')
   ↓
5. 切换到 "队列" Tab
   ↓
6. 看到计划在队列中，位置根据优先级排序
   ↓
7. 如果是第一个，显示 "开始" 按钮
   ↓
8. 点击 "开始" → 计划开始执行 (status = 'running')
   ↓
9. 执行过程中可以:
   - 暂停 (status = 'paused')
   - 取消 (status = 'cancelled')
   ↓
10. 执行完成 (status = 'completed' or 'failed')
    ↓
11. 切换到 "历史" Tab 查看结果
```

### 工作流 3: 编辑现有计划步骤

```
1. 用户在 "计划" Tab 点击计划行的 "..." 菜单
   ↓
2. 选择 "编辑步骤"
   ↓
3. 自动跳转到 "步骤" Tab，并选中该计划
   ↓
4. 加载现有步骤列表
   ↓
5. 用户可以:
   - 修改步骤参数
   - 添加新步骤
   - 删除步骤
   - 重排序
   ↓
6. 点击 "保存步骤"
   ↓
7. 如果计划已在队列中:
   - 显示警告: "计划已在队列中，修改可能影响执行"
   - 要求用户确认
   ↓
8. 保存成功，更新计划的 updated_at 时间戳
```

---

## 实施路线图

> **状态**: 所有阶段已完成 ✅

### Phase 1: 基础架构 ✅ 已完成

**目标**: 搭建新的目录结构和基础设施

**完成内容**:
- [x] 创建 `gui/src/components/TestPlanManagement/` 目录
- [x] 设置 TypeScript 类型定义文件 (`gui/src/types/testPlan.ts`)
- [x] 创建统一 API 客户端
- [x] 设置 TanStack Query hooks 基础结构
- [x] 创建主容器组件 (`TestPlanManagement.tsx`)

---

### Phase 2: Plans Tab 实现 ✅ 已完成

**目标**: 计划管理功能

**完成内容**:
- [x] 计划列表组件 (`TestPlanList.tsx`)
- [x] 过滤和搜索功能
- [x] 创建向导 (`CreateTestPlanWizard.tsx`)
- [x] 编辑向导 (`EditTestPlanWizard.tsx`)
- [x] 状态徽章和进度条

---

### Phase 3: Steps 实现 ✅ 已完成

**目标**: 步骤管理核心功能

**完成内容**:
- [x] 后端 API: `/plans/{id}/steps` 端点
- [x] TestStep Schema 定义 (`test_plan.py:326-408`)
- [x] 虚拟路测自动步骤生成 (`test_plan_service.py:60-217`)
- [x] 序列库集成 (8个 Road Test 序列)
- [x] 步骤参数优先级系统

---

### Phase 4: Queue & History 实现 ✅ 已完成

**目标**: 队列和历史功能

**完成内容**:
- [x] 执行队列组件 (`TestQueue.tsx`)
- [x] 队列重排序功能
- [x] 执行控制按钮 (开始/暂停/取消)
- [x] 执行历史组件 (`TestExecutionHistory.tsx`)
- [x] 统计卡片组件

---

### Phase 5: 数据流整合 ✅ 已完成

**目标**: 跨组件数据同步

**完成内容**:
- [x] TanStack Query 状态管理
- [x] WebSocket 实时监控
- [x] 错误处理和重试逻辑

---

### Phase 6: Virtual Road Test 集成 ✅ 已完成

**目标**: 虚拟路测与测试管理整合

**完成内容**:
- [x] Scenario → TestPlan 转换
- [x] step_configuration 自动继承
- [x] 8个预定义步骤自动生成
- [x] 参数优先级系统

---

## 迁移策略

### 迁移原则

1. **渐进式迁移**：新旧模块并存，逐步切换
2. **向后兼容**：确保现有功能不受影响
3. **数据迁移**：提供数据迁移脚本
4. **用户通知**：提前通知用户模块变更

### 迁移步骤

#### Step 1: 准备阶段
```
1. 创建新模块目录结构
2. 设置 Feature Flag (环境变量控制)
3. 添加路由切换逻辑
```

#### Step 2: 双轨运行
```
1. 新旧模块同时可用
2. 在导航栏添加 "测试管理 (Beta)" 入口
3. 收集用户反馈
4. 修复 Bug，迭代优化
```

#### Step 3: 数据迁移
```sql
-- 迁移现有测试计划到新表结构
INSERT INTO test_plans (
  id, name, description, status, ...
)
SELECT
  id, name, description, 'draft', ...
FROM old_test_plans;

-- 迁移步骤数据
INSERT INTO test_steps (
  test_plan_id, order_index, title, parameters, ...
)
SELECT
  plan_id, step_order, step_title, step_params, ...
FROM old_plan_steps;
```

#### Step 4: 功能切换
```typescript
// 环境变量控制
const USE_NEW_TEST_MANAGEMENT =
  import.meta.env.VITE_USE_NEW_TEST_MANAGEMENT === 'true'

// App.tsx 路由逻辑
{USE_NEW_TEST_MANAGEMENT ? (
  <TestManagement />  // 新模块
) : (
  <TestConfig />      // 旧模块
)}
```

#### Step 5: 完全切换
```
1. 将 Feature Flag 默认设为 true
2. 移除旧模块的导航入口
3. 标记旧代码为 @deprecated
4. 计划在下一个版本删除旧代码
```

#### Step 6: 清理
```
1. 删除旧模块代码
2. 删除 Feature Flag
3. 更新所有文档
4. 发布 Changelog
```

---

## 附录

### A. 技术栈

- **前端框架**: React 18
- **构建工具**: Vite 5
- **UI 库**: Mantine 7
- **状态管理**: TanStack Query v5
- **拖拽**: @dnd-kit/core
- **表单**: react-hook-form
- **验证**: zod
- **路由**: React Router v6
- **HTTP 客户端**: axios
- **测试**: Vitest + Testing Library + Playwright

### B. 代码规范

- **TypeScript**: Strict mode
- **ESLint**: Airbnb + TypeScript rules
- **Prettier**: 2 spaces, single quotes
- **Commit**: Conventional Commits
- **Branch**: feature/, bugfix/, hotfix/

### C. 性能目标

- **FCP** (First Contentful Paint): < 1.5s
- **LCP** (Largest Contentful Paint): < 2.5s
- **TTI** (Time to Interactive): < 3.5s
- **Bundle Size**: < 500KB (gzipped)

### D. 浏览器支持

- Chrome >= 90
- Firefox >= 88
- Safari >= 14
- Edge >= 90

---

## 变更日志

### v3.0.0 (2025-12-31)
- ✅ 更新文档状态为"已实现"
- 📝 新增"测试步骤来源"章节，详细说明两种步骤类型
- 🔄 更新 TestStep 数据模型，反映当前实现
- 📊 更新实施路线图，标记所有阶段已完成
- 🔗 添加参数速查表引用链接

### v2.0.0 (2025-11-18)
- 🎉 Initial unified architecture design
- 📝 Complete data model specification
- 🔌 API endpoint design
- 🗺️ Implementation roadmap

---

## 相关文档

- [参数速查表 (手动维护)](../virtual-road-test/parameter-reference.md) - 所有参数一览
- [参数速查表 (自动生成)](../virtual-road-test/parameter-reference-generated.md) - 从 Schema 自动生成
- [步骤配置指南](../virtual-road-test/step-configuration.md) - 虚拟路测步骤配置详解

---

**文档维护者**: Claude Code
**最后更新**: 2025-12-31
**审核状态**: ✅ 已实现并验证
