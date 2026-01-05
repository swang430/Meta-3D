# GEMINI 项目审查与记忆库

## 项目概览
- **名称:** MIMO-First
- **日期:** 2026-01-04
- **目标:** 从底层进行代码审查，发现问题并收敛公共逻辑（DRY原则），并修复关键 Bug 和用户体验问题。

## 1. 审查与修复日志 (Audit & Fix Log)

### 已解决的关键问题 (Resolved Critical Issues)
- [x] **路由冲突 (Routing Conflict):**
    - **问题:** 前端无法访问 Channel Engine (`/api/v1/ota`)，因为 Vite 代理错误地将其路由到了 API Service (8000)。
    - **修复:** 在 `gui/vite.config.ts` 中添加了针对 `/api/v1/ota` 到端口 8001 的专用代理规则。
- [x] **WebSocket 连接失败:**
    - **问题:** 浏览器受系统代理影响或 Vite 代理 WebSocket 不稳定，导致 `ws://localhost:5173` 连接失败。
    - **修复:** 修改前端 (`useMonitoringWebSocket.ts`, `App.tsx`) 在开发模式下绕过代理，直接连接 `ws://localhost:8000` (或 `127.0.0.1`)。
- [x] **报告生成 500 错误:**
    - **问题:** 报告生成逻辑在处理 Route Waypoints 时，错误地将字典 (`dict`) 当作对象属性 (`obj.lat`) 访问，导致 `AttributeError`。
    - **修复:** 在 `api-service/app/api/road_test.py` 中引入 `get_attr_or_item` 辅助函数，并全量重构 `_generate_execution_report` 以安全处理数据访问。
- [x] **数据/物理模型不匹配 (Data Mismatch):**
    - **问题:** `init_probes.py` 生成的探头数量 (24) 与仿真需求 (32) 不符。
    - **修复:** 重写初始化脚本，生成正确的 32 探头 3D 布局。

### 优化与增强 (Optimizations & Enhancements)
- [x] **场景数据准确性:**
    - **速度计算:** 修复前端场景创建时的距离计算公式 (缺少 `/ 3.6`)，解决了报告中速度显示错误 (5 vs 18 km/h) 的问题。
    - **基站数量:** 前端 `CreateScenarioDialog` 不再硬编码 1 个基站，而是添加了“基站数量”输入框，支持动态生成指定数量的基站。
- [x] **报告展示体验:**
    - **Tab 重命名:** 将“执行结果”标签重命名为“执行过程”，消除歧义。
    - **参数可视化:** 将测试步骤参数展示从原始 JSON 代码块 (`JSON.stringify`) 优化为用户友好的 Key-Value 列表。
- [x] **数据持久化 (Persistence):**
    - **场景保存:** 为自定义场景实现了 JSON 文件持久化 (`data/custom_scenarios.json`)，解决了重启服务后测试例丢失的问题。
- [x] **Schema 收敛基础设施:**
    - 添加了 `scripts/export_channel_engine_schema.py` 和 npm 脚本，用于从 Channel Engine 自动生成 OpenAPI 规范，为未来前后端类型同步打下基础。

## 2. 共享知识 (Facts)
- **技术栈:** Python 3.9+ (FastAPI), React 18 (Vite), PostgreSQL。
- **端口:** API(8000), Engine(8001), GUI(5173)。
- **依赖:** Channel Engine 依赖本地路径 `/Users/Simon/Tools/ChannelEgine`。
- **数据存储:**
    - 结构化数据 (Topology, Users): PostgreSQL (Docker: `gaokao_db`).
    - 临时/自定义场景: JSON 文件 (`api-service/data/custom_scenarios.json`).

## 3. 待办事项与未来计划 (Backlog & Future Plans)

### Phase 2: 硬件驱动与深度集成
- [ ] **HAL 实现:** 目前 `api-service/app/hal` 仅有 Mock 实现。需要编写真实的 VISA/SCPI 驱动程序以连接 R&S/Keysight 仪表。
- [ ] **Auth 强化:** 完善 JWT 验证逻辑，增加数据库用户状态检查。

### Phase 3: 数据库迁移与架构收敛
- [ ] **场景数据入库:** 将目前的 JSON 文件持久化迁移到 PostgreSQL 数据库，设计完整的 `scenarios` 表结构。
- [ ] **Schema 自动同步:** 配置 CI/CD 或 pre-commit hook，自动运行 `openapi-typescript`，确保前端类型定义与后端 Pydantic 模型始终保持一致。
- [ ] **统一错误处理:** 在前后端建立统一的错误码规范，前端实现全局错误拦截与友好的 Toast 提示。

### 体验优化
- [ ] **高级场景配置:** 在前端提供更丰富的基站配置 UI（不仅仅是数量，还可以配置位置、功率等）。
- [ ] **实时波形图:** 优化 WebSocket 数据流，支持更高频率的波形数据推送与前端 Canvas/WebGL 渲染。
