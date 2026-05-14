# CLAUDE.md

本文件为 Claude Code (claude.ai/code) 提供在此代码库中工作的指导。

## ⭐ 工作准则 — 适用于所有 agent / session（最高优先级）

> 本节是项目契约。任何非琐碎改动开始前必须遵守。

### 1. 先读路线图

任何非琐碎改动开始前，**先读 [`docs/roadmap-first-call.md`](docs/roadmap-first-call.md)**，
明确这次改动对应哪个 roadmap 编号（P0-X / P1-X / P2-X / P3-X）。

### 2. WIP = 1 on P0

路线图顶部 `Current Focus` 字段是当前唯一允许 in-progress 的 P0 项。
该项 PR merged + acceptance criteria 验证通过之前，**不开新的 P0**。

**注意**：本规则约束的是 **WIP 上限**（最多一个 P0 并发），不是
"必须永远有 P0 在做"。如果剩余 P0 全部物理 blocked（例如等下次现场、
等硬件采购），降级到 P1 不算违规 —— 这时把 Current Focus 字段挪到
具体 P1 项，并在路线图的 "🚧 Blocked on hardware" 区显式标注哪些 P0
在排队等什么。一旦 blocker 消失（下次现场），P0 自动回到队首,
此时不能再启动新 P1。

### 3. 不在路线图上的改动 — 三种处理

- **琐碎 (<30 分钟)**：直接做，commit message 标 `chore:` 前缀。
- **中等大小**：在 roadmap.md 的 "Discovered during X" backlog 区加一行
  (`[discovered YYYY-MM-DD during P0-X] <一句话>`)，然后**回到当前 P0**。
- **大改**：停下来跟人讨论。

### 4. 严禁"顺手优化"

看到代码 mess 不要清理。Mess 不是 bug。如果它不让当前 P0 更容易，
就进 P3 backlog，不是 inline cleanup。

### 5. PR 必须声明 roadmap 对齐

PR 描述必须包含：
```
Roadmap: P0-X  (或)  Out-of-roadmap, reason: ...
```
模板在 [`.github/pull_request_template.md`](.github/pull_request_template.md)。

### 6. Review 反馈的处理

Codex / 人类 reviewer 的 P0/P1 安全问题：当下修。
P2/P3 风格类反馈：appended to backlog, not 当下修，避免 review 黑洞。

### 7. 周度短 review

每周五 15 分钟自问 3 个问题：
1. 这周原本要做的是哪个 P0，实际做了什么？
2. 偏移程度（0% / 30% / 100%）？
3. 偏移原因属于上面 1-5 的哪一类？

**这些规则的存在原因**：CAICT 2026-05-12/13 两天现场调试本应交付 first-call，
实际全部消耗在 driver 层（F64 IDN / UXM Test App / Aerotech 单轴 / idle-close）。
工作本身有价值，但 first-call 没出来。下次去现场前，软件链路要先在本地走通
（mock-data first-call），现场只调硬件，不写 driver 代码。

详细 governance 论证见 [`docs/announcements/2026-05-14-roadmap-baseline.md`](docs/announcements/2026-05-14-roadmap-baseline.md)。

---

## 项目概述

这是一个面向汽车无线通信的 MIMO OTA（空中接口）测试系统。系统采用多探头暗室（Multi-Probe Anechoic Chamber, MPAC）技术，在可控的电磁环境中测试全尺寸车辆。

**核心理念**：系统实现了"软件定义静区"（Software-Defined Quiet Zone），测试区域的质量由软件算法和校准决定，而非暗室的物理尺寸。

## 常用命令

### 前端开发 (gui/)
```bash
cd gui
npm install              # 安装依赖
npm run dev              # 启动开发服务器（支持热重载）
npm run build            # TypeScript 编译 + Vite 生产构建
npm run lint             # 运行 ESLint 检查
npm run preview          # 本地预览生产构建
```

### 类型生成
```bash
cd gui
npm run openapi:generate # 从 ../api/openapi.yaml 生成 TypeScript 类型
```
此命令读取 OpenAPI 规范并生成 `gui/src/types/api.generated.ts`。每当 API 规范更改时都需要运行。

## 架构

### Monorepo 结构
- **gui/**: React + TypeScript + Vite 前端应用
- **api/**: OpenAPI 3.0 规范，定义 REST API 契约
- **根目录文档**: 硬件规格和系统设计文档（AGENTS.md, Hardware.md, MPAC.md 等）

### 前端架构 (gui/)

GUI 遵循 **API优先架构**，包含以下层次：

1. **API 层** (`gui/src/api/`):
   - `client.ts`: Axios HTTP 客户端实例
   - `service.ts`: API 服务函数（fetchDashboard, fetchProbes 等）
   - `mockServer.ts`: Axios mock 适配器，用于无后端开发
   - `mockDatabase.ts`: mock 服务器的内存数据存储

2. **服务层** (`gui/src/services/`):
   - `channels/`: 信道仿真器硬件抽象层（HAL）
   - 协调 API 调用和本地状态的业务逻辑

3. **组件层** (`gui/src/components/`):
   - `ProbeLayoutView.tsx`: 探头天线阵列的 3D 可视化

4. **类型定义** (`gui/src/types/`):
   - `api.ts`: 手动定义的 API 类型
   - `api.generated.ts`: 从 OpenAPI 规范自动生成
   - `channel.ts`: 信道仿真器类型

### 核心领域概念

**测试层级**:
- **测试计划（Test Plans）**: 测试例的集合，带有执行队列和步骤编排
- **测试步骤（Test Steps）**: 计划中的可配置执行单元，每个步骤有独立参数 ⭐ NEW
- **测试例（Test Cases）**: 可保存、预览和重用的单个测试配置
- **序列库（Sequence Library）**: 测试步骤的可重用构建块模板
- 测试计划可以从头创建，也可以通过保存测试例创建

**测试管理统一架构** (v2.0):
- 项目已整合原有的 TestConfig 和 TestPlanManagement 两个模块
- 新的统一模块位于 `gui/src/features/TestManagement/`
- 详细设计文档: `TestManagement-Unified-Architecture.md`
- 4个主要 Tab: 计划管理、步骤编排、执行队列、执行历史

**硬件组件**:
- **探头（Probes）**: MPAC 阵列中的天线单元（32个双极化探头）
- **仪器（Instruments）**: 信道仿真器、基站仿真器、信号分析仪
- **被测设备（DUT, Device Under Test）**: 在静区中测试的车辆

**关键功能**:
- 实时监控数据流和告警
- 仪器目录，支持型号选择和连接管理
- 探头配置和可视化
- 测试计划生命周期：创建 → 编辑 → 排队 → 执行 → 报告

## 技术栈

### 前端
- **React 18** + TypeScript
- **Vite** 构建工具（非 Create React App）
- **Mantine UI** (@mantine/core, @mantine/hooks, @mantine/notifications) - 主要组件库
- **TanStack Query** (@tanstack/react-query) 用于服务端状态管理
- **Axios** 配合 mock 适配器进行 API 调用
- **ESLint** + TypeScript 规则

### 后端
- **FastAPI** + Pydantic v2
- **SQLAlchemy** ORM

### 数据库（⭐ 重要）
- **生产环境一律使用 PostgreSQL**，绝不依赖 SQLite
  - 真实配置：`.env` 的 `DATABASE_URL=postgresql://...`
  - `app/config.py` 中的 SQLite URL 是**注释掉的备份**，不应在生产路径中启用
  - 新增 SQLAlchemy 模型应使用 PG 兼容类型（`postgresql.UUID`、`JSONB` 等）
- **测试可以使用 SQLite**（隔离与速度优先）
  - `sqlite:///:memory:` 用于纯内存隔离测试
  - `sqlite:///./test_*.db` 用于文件隔离测试，产物已在 `.gitignore` 中忽略
  - `api-service/*.db` 与 `*.db.bak` 是本地 stale 开发产物，可安全清理

## 开发工作流

### 使用 Mock 数据
应用在开发期间完全使用 mock 服务器运行：
- Mock 服务器在 `gui/src/api/mockServer.ts` 中配置
- Mock 数据在 `gui/src/api/mockDatabase.ts` 中定义
- 添加新端点时：同时更新 mock 服务器处理器和 OpenAPI 规范

### 添加新 API 端点
1. 在 `api/openapi.yaml` 中定义端点
2. 运行 `npm run openapi:generate` 更新 TypeScript 类型
3. 在 `gui/src/api/service.ts` 中添加服务函数
4. 在 `gui/src/api/mockServer.ts` 中添加 mock 处理器
5. 在 `gui/src/api/mockDatabase.ts` 中添加/更新 mock 数据

### 状态管理模式
- 使用 **TanStack Query** 管理服务端状态（API 数据缓存、重新获取）
- 使用 **React hooks**（useState, useContext）管理 UI 状态
- Mantine 提供 `@mantine/notifications` 用于全局通知

### 样式方案
- 以 **Mantine 组件**为基础
- 自定义组件应封装 Mantine 原语以保持一致性
- 尽可能使用 Mantine 的主题系统（tokens、暗黑模式）而非自定义 CSS
- 现有的 `App.css` 是遗留代码；新代码优先使用 Mantine 的样式解决方案

## 重要文件

### 核心代码文件
- [gui/src/App.tsx](gui/src/App.tsx) - 主应用组件（非常大，178KB）
- [gui/src/main.tsx](gui/src/main.tsx) - 应用入口点
- [gui/src/api/service.ts](gui/src/api/service.ts) - 所有 API 服务函数
- [api/openapi.yaml](api/openapi.yaml) - API 契约定义
- [gui/package.json](gui/package.json) - 依赖和脚本

### 设计文档（⭐ 必读）

**API 与数据规范**:
- [API 设计指南](docs/api/design-guide.md) - ⭐ RESTful 设计原则、响应格式、错误处理
- [数据模型指南](docs/api/data-model.md) - ⭐ 数据库模型 / DTO / API Schema 三层架构
- [Swagger 使用指南](docs/api/swagger-guide.md) - 在线 API 文档

**架构设计**:
- [AGENTS.md](AGENTS.md) - 系统架构和设计文档（35K+ tokens）
- [系统集成](docs/architecture/system-integration.md) - 系统集成设计
- [硬件同步](docs/architecture/hardware-sync.md) - ⭐ L0-L3 分层同步
- [测试管理统一架构](docs/features/test-management/unified-architecture.md)
- [虚拟路测概览](docs/features/virtual-road-test/overview.md)

**开发指南**:
- [快速上手](docs/guides/quickstart.md)
- [状态机](docs/guides/state-machine.md)
- [实现检查清单](docs/guides/implementation-checklist.md)

## 设计指南（来自 AGENTS.md）

项目正在遵循分阶段的 UI 改进计划：

**Phase 1**（当前）: Mantine 集成
- 使用 MantineProvider 建立主题基线
- 封装可重用组件（PageLayout, SidebarNav 等）
- 使用 Mantine AppShell/Stack/Grid 统一布局
- 用 Mantine Notifications/Badge 替换自定义状态指示器

**Phase 2**: 功能增强
- 实现暗黑模式切换
- 增强 ProbeLayoutView（集成 D3.js 或 Three.js 实现交互式 3D 可视化）
- 用于探头参数编辑的 FormSection 组件
- 一致的间距系统（8px 基准网格）

## 注意事项

### 当前状态（2025-12-11 更新）

**已完成功能**:
- ✅ 前后端完整架构 (React + FastAPI + SQLite)
- ✅ 测试计划管理：创建、编辑、执行队列、状态机
- ✅ 测试步骤编排：序列库、参数配置
- ✅ 虚拟路测：场景库、ChannelEngine 集成
- ✅ 报告系统：PDF 生成、模板管理、执行历史
- ✅ Mock 服务器已禁用，Vite 代理配置完成

**进行中**:
- 🔄 GUI 功能完善 (Phase 4 - 约 70%)
- 🔄 硬件抽象层设计完成，驱动待实现

**待实现功能** (详见 `docs/Master-Progress-Tracker.md`):
- ⏳ Queue 重排序功能
- ⏳ 认证上下文（Auth Context）
- ⏳ 仪表盘告警系统
- ⏳ 报告对比功能
- ⏳ 硬件驱动集成
