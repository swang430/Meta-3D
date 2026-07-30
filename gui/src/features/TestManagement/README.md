# 测试管理模块

> v4.0.0 —— ARCH-1 之后：**以测试用例（TestCase）为根**的测试管理。
> 本文是这个模块的现状说明。原来那份 1494 行的《测试管理统一架构》以计划链为主语，
> 已随 ARCH-1 S4 归档至
> [`docs/archive/test-management-unified-architecture.md`](../../../../docs/archive/test-management-unified-architecture.md)。

## 这个模块是什么

三个 Tab 的容器。它自己几乎不含业务逻辑 —— 三个 Tab 的内容分别由三个外部组件提供。

3 个主要 Tab: 测试用例库、执行历史、虚拟路测 <!-- gate:tabs=测试用例库,执行历史,虚拟路测 -->

> 上面这行由 `api-service/tests/test_rule_gates.py` 的 **G7 门**守着：行尾 marker
> 声明的标签集必须等于 `TestManagement.tsx` 里 JSX 的标签集，且散文里要逐字含这几个
> 标签。**加/删/改名 Tab 而不改这行，测试会红。**

| Tab | value | 内容由谁提供 |
|-----|-------|-------------|
| 测试用例库 | `caseLibrary` | `components/TestPlanManagement/TestCaseLibrary`（`enableExecute` 开着 —— 执行按钮在这里） |
| 执行历史 | `history` | `./components/HistoryTab` |
| 虚拟路测 | `virtualRoadTest` | `components/VirtualRoadTest` |

## 目录结构（实况）

```
TestManagement/
├── TestManagement.tsx              # 主容器 —— 三个 Tab 的壳
├── index.ts                        # 模块导出
├── README.md                       # 本文档
├── api/testManagementAPI.ts        # API 客户端
├── hooks/
│   ├── index.ts
│   └── useTestHistory.ts           # 仅剩这一个 hook
├── types/index.ts
├── components/HistoryTab/          # 仅剩这一个自有 Tab 组件
└── utils/                          # helpers / normalizeStepParameters / mockDataGenerator
```

`hooks/` 曾有七组 hook（计划 / 步骤 / 队列 / 执行控制 / 历史 / 序列库 / 统计），
`components/` 曾有四个 Tab 目录（Plans / Steps / Queue / History）。
**除历史外全部随 ARCH-1 S4a 删除** —— 它们服务的三个 Tab 已不存在。

## 用法

```typescript
import { TestManagement } from '@/features/TestManagement'

function App() {
  return <TestManagement />
}
```

执行历史：

```typescript
import { useTestHistory } from '@/features/TestManagement'
```

⚠️ **用例的编辑 / 执行入口不在本模块** —— 在
`components/TestPlanManagement/TestCaseLibrary` 与 `TestCaseEditModal`。
**新建入口今天不可达**：`TestCaseLibrary` 的「新建用例」按钮由 `onCreateNew` prop 守着，
而 `TestManagement.tsx` 只传了 `enableExecute` —— 全仓无人传 `onCreateNew`，
所以用例只能来自 bootstrap 种子（S4a 显式申报的缺口，在 backlog）
（MIMO_OTA 类型的仪表参数表单是 `components/TestCaseConfig/MIMOOTAConfigForm`，
ARCH-1 S4a 从已删的 StepsTab 搬过来的）。

## 核心概念

### TestCase —— 正式测试的单一真值源

一个 TestCase 自带 `configuration`：仪表参数、信道资产引用、相位描述符。
执行时后端把 `configuration.steps` 读成内存里的 `StepDescriptor` 派发，
**不往 `test_steps` 表落行**。

### TestExecution —— 每次执行一行

状态取值以 `TestExecution.status` 的列注释为唯一真值源（`api-service/app/models/test_plan.py`）—— 今天是 `pending`（**默认值，建出来就是它**）/ `running` / `completed` / `failed` / `cancelled` / `skipped`，另有 VRT 专用的 `idle` / `initializing` / `configured` / `paused` / `stopped`。
**别在别处抄** —— 抄一份就会漂（上一版这里漏了 `pending`）。
历史 Tab 和报告都从这张表取数。
执行正门：`POST /api/v1/test-plans/cases/{test_case_id}/execute`
（URL 里的 `test-plans` 前缀是历史包袱，改前缀契约破坏面大、收益纯美观，记 P3）。

### ⚠️ 不再存在的概念

计划（TestPlan）、执行队列、步骤编排、序列库、8 种计划状态、5 种步骤状态 ——
**ARCH-1 S4 整体拆除**。`TestPlan` / `TestStep` / `TestQueue` / `TestPlanExecution` /
`TestSequence` 五张表原地封存，只读历史、无业务写入方，
见 [`api-service/app/models/test_plan.py`](../../../../api-service/app/models/test_plan.py)
每张表顶上的封存 banner。**新代码不要引用它们。**

## 相关文档

- [CLAUDE.md](../../../../CLAUDE.md) —— 项目整体文档，「测试层级」一节是本模块的上位说明
- [ARCH-1 总纲](../../../../docs/design/arch-1-testcase-first-simplification.md) —— 为什么拆
- [ARCH-1 S4 拆除设计](../../../../docs/design/arch-1-s4-demolition.md) —— 怎么拆的
- [数据源真相](../../../../CLAUDE.md) —— CLAUDE.md 的「⭐ 数据源真相」一节：默认连真实后端，mock 已禁用

## 注意事项

- **默认连真实后端**，mock 已在 `main.tsx` 注释掉，Vite 代理转发 `/api`。
  读 `gui/src/api/mockDatabase.ts` 里的演示数据判断"功能怎么工作"会被误导。
- GUI 侧**没有测试框架** —— 本模块改动的门只有 `npm run build`（`tsc -b`）
  加浏览器实测，没有单测兜底。
