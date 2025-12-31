# Unified Test Management Feature

> Version 2.0.0 - 统一的测试计划管理与步骤编排系统

## 概述

本模块整合了原有的 **TestConfig** 和 **TestPlanManagement** 两个功能模块，提供统一的测试管理体验。

## 目录结构

```
TestManagement/
├── TestManagement.tsx          # 主容器组件 (4个Tab)
├── index.ts                    # 模块导出
├── README.md                   # 本文档
├── api/
│   └── testManagementAPI.ts   # 统一 API 客户端
├── hooks/
│   ├── index.ts               # Hooks 统一导出
│   ├── useTestPlans.ts        # 测试计划 hooks
│   ├── useTestSteps.ts        # 测试步骤 hooks
│   ├── useTestQueue.ts        # 执行队列 hooks
│   ├── useTestExecution.ts    # 执行控制 hooks
│   ├── useTestHistory.ts      # 执行历史 hooks
│   ├── useSequenceLibrary.ts  # 序列库 hooks
│   └── useStatistics.ts       # 统计分析 hooks
├── types/
│   └── index.ts               # 类型定义 (600+ lines)
├── components/
│   ├── PlansTab/              # Phase 2: 计划管理 Tab
│   ├── StepsTab/              # Phase 3: 步骤编排 Tab
│   ├── QueueTab/              # Phase 4: 执行队列 Tab
│   ├── HistoryTab/            # Phase 4: 执行历史 Tab
│   └── shared/                # 共享组件
└── utils/                     # 工具函数
```

## 使用方法

### 导入主组件

```typescript
import { TestManagement } from '@/features/TestManagement'

function App() {
  return <TestManagement />
}
```

### 使用 Hooks

```typescript
import {
  useTestPlans,
  useCreateTestPlan,
  useTestSteps,
  useAddTestStep,
} from '@/features/TestManagement'

function MyComponent() {
  // 获取测试计划列表
  const { data: plans, isLoading } = useTestPlans({ status: 'draft' })

  // 创建测试计划
  const { mutate: createPlan } = useCreateTestPlan()

  // 获取测试步骤
  const { data: steps } = useTestSteps(planId)

  // 添加测试步骤
  const { mutate: addStep } = useAddTestStep()

  // ...
}
```

### 使用类型

```typescript
import type {
  UnifiedTestPlan,
  TestStep,
  TestPlanStatus,
  StepParameter,
} from '@/features/TestManagement'

const plan: UnifiedTestPlan = {
  id: 'plan-001',
  name: 'MIMO OTA Test',
  status: 'draft',
  // ...
}
```

### 直接调用 API

```typescript
import { testManagementAPI } from '@/features/TestManagement'

// 获取测试计划
const plan = await testManagementAPI.getTestPlan('plan-001')

// 创建测试计划
const newPlan = await testManagementAPI.createTestPlan({
  name: 'New Plan',
  // ...
})
```

## 核心概念

### 1. UnifiedTestPlan

统一的测试计划数据模型，整合了两个原有模块的概念：

- **基础信息**: id, name, description, version, status
- **DUT 信息**: 被测设备型号、序列号
- **测试环境**: 暗室ID、温度、湿度
- **步骤配置**: TestStep[] (关键集成点)
- **队列信息**: 队列位置、优先级
- **执行统计**: 总数、完成数、失败数
- **时间追踪**: 预估时长、实际时长

### 2. TestStep

测试步骤是测试计划的执行单元：

- 关联序列库模板 (sequence_library_id)
- 动态参数配置 (ParametersMap)
- 执行配置 (timeout, retry, continue_on_failure)
- 运行时状态 (status, result, error_message)

### 3. StepParameter

步骤参数支持多种类型和验证：

- **类型**: text, number, select, textarea, boolean, json
- **验证**: min/max, pattern, options, required
- **UI配置**: placeholder, unit, helpText

### 4. 状态管理

- **8种测试计划状态**: draft → ready → queued → running → paused → completed/failed/cancelled
- **5种步骤状态**: pending → running → completed/failed/skipped

## 实现进度

- [x] **Phase 1**: 基础架构 (Week 1)
  - [x] 类型定义 (600+ lines)
  - [x] API 客户端 (30+ endpoints)
  - [x] TanStack Query hooks (7个文件)
  - [x] 主容器组件
- [ ] **Phase 2**: PlansTab 迁移 (Week 2)
- [ ] **Phase 3**: StepsTab 实现 (Week 3-4)
- [ ] **Phase 4**: QueueTab & HistoryTab 迁移 (Week 5)
- [ ] **Phase 5**: 数据流集成 (Week 6)
- [ ] **Phase 6**: UI/UX 优化 (Week 7)
- [ ] **Phase 7**: 测试与部署 (Week 8)

## 技术栈

- **React 18** + TypeScript
- **Mantine UI** - 组件库
- **TanStack Query** - 服务端状态管理
- **Axios** - HTTP 客户端

## 相关文档

- [架构设计文档](../../../../TestManagement-Unified-Architecture.md) - 完整的设计规范
- [数据架构指南](../../../../docs/Data-Architecture-Guide.md) - Mock Server vs 后端 API 说明
- [CLAUDE.md](../../../../CLAUDE.md) - 项目整体文档

## 开发指南

### 添加新的 API 端点

1. 在 `types/index.ts` 中添加请求/响应类型
2. 在 `api/testManagementAPI.ts` 中添加 API 函数
3. 在对应的 hooks 文件中添加 Query/Mutation hook
4. 在 `hooks/index.ts` 中导出新的 hook

### 创建新的 Tab 组件

1. 在 `components/` 下创建新的 Tab 目录
2. 实现主组件和子组件
3. 在 `TestManagement.tsx` 中导入并使用
4. 更新此 README

## 注意事项

- ⚠️ API 端点基于设计文档，实际后端实现可能需要调整
- ⚠️ **当前使用后端 API**，Mock Server 已禁用。详见 [数据架构指南](../../../../docs/Data-Architecture-Guide.md)
- ⚠️ 组件尚未完全实现，当前为 Phase 1 基础架构
