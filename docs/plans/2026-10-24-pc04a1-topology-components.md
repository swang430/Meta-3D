# PC-04A-1 原拓扑器件与端口编辑实施计划

> 执行：使用 subagent-driven-development 顺序实现一个交付任务，随后独立只读审查；不并行修改生产代码。

**Goal:** 操作员能在原射频拓扑添加、编辑、删除器件和连接，保存并刷新后保持一致。

**Architecture:** 复用原ReactFlow、自定义节点及现有拓扑JSON/API。统一本地草稿的nodes、connections、operating_modes，所有编辑写同一草稿；后端保存前核验合并后的完整引用关系。校准接线独立模式不进入mimo_ota活动连接。

**Tech Stack:** React、TypeScript、Mantine、ReactFlow；FastAPI、Pydantic、SQLAlchemy。

**Spec:** `docs/design/2026-10-24-topology-calibration-integration.md`

## Global Constraints

- 保留原画布拖动、连线编辑、保存；不创建替代只读画布。
- 不新增SCPI、不控制真实硬件、不修改正式资格和校准应用公式。
- 删除拓扑元素不能删除仪器资源、历史校准或执行记录。
- 当前实验室限定全部读写；配置变化只提醒复核，不自动强制重校准。
- 第一片不声称采集或校准应用完成；后续切片按roadmap顺序独立合并。

## Task 1: 器件、连接与持久化闭环

**Files:**
- 修改 `gui/src/features/TopologyEditor/TopologyEditor.tsx`：新增/编辑/删除入口、同一草稿、保存。
- 修改 `gui/src/features/TopologyEditor/CustomNodes.tsx`、`nodePortHelpers.ts`：新器件保持原视觉并使声明端口和可连接端点一致。
- 新增 `gui/src/features/TopologyEditor/topologyDraft.ts`：集中纯草稿操作，防止画布和保存载荷分叉。
- 新增 `gui/test/topologyDraft.test.ts`；扩展 `gui/test/topologyEditing.browser.js`。
- 修改 `api-service/app/api/switch_topology.py`，必要时共享纯校验 helper；新增 `api-service/tests/test_pc04a1_topology_editing.py`。

**Interfaces:** 消费已有 `SwitchTopology`/`TopologyNode`/`TopologyConnection`/`OperatingMode`；保存仍调用 `switchTopologyService.updateTopology(id, labProfileId, payload)`，载荷包含三个完整草稿集合。不另建保存接口。

- [ ] 读完整编辑器、节点、端口、API create/PATCH/import、TopologyService.validate及其现有测试，枚举生产写入口。
- [ ] 写纯草稿行为RED：添加后当前模式可见；连接加入connections与当前mode.active_connections；删节点同步删关联连接/所有模式引用；跨模式不丢位置和未知params；校准连接不加入mimo_ota。
- [ ] 运行 `npx --yes tsx --test test/topologyDraft.test.ts`，记录具体失败后实现纯草稿操作。验收例：删除节点a后，连接a→b被移除、无关b→c保留，所有mode均不再引用a→b。
- [ ] 写API RED：PATCH创建悬空引用/重复node或connection id必须受控拒绝且数据库不变；一次PATCH同时删节点及其边成功；完整合并校验允许合法局部更新。不把历史读取变成500。
- [ ] 最小实现保存前结构检查，create/import的同型完整输入一并核对；不将未配置端口伪装成真实仪器能力，不扩大到全仓格式重构。
- [ ] GUI增加器件选择及属性Drawer：明确标签/端口声明/适用模式，仪器关联复用现有目录，未知绑定仅声明不能当已连接。新增节点在当前画布可见。删除需确认受影响连接数。
- [ ] 连线新增/删除与参数更新同步草稿；端口编辑不能留下悬空连接；保存期间禁重复提交和修改，失败保留草稿。移除“先校验旧服务器图才能保存修正草稿”的错误顺序，后端校验本次完整载荷。
- [ ] 保留原节点类型及位置；补被动器件渲染，不抹掉既有params。校准接线使用明确独立模式，不更改正常模式的器件识别。
- [ ] 跑纯草稿/API/受影响拓扑与规则测试；真实Mock浏览器验证增、改、连、拖、删、保存、刷新、模式切换及旧编辑回归。禁止以响应拦截替代后端保存。
- [ ] 稳定实现跑GUI契约/build、后端最终全量（首次新增功能）、compileall、单Alembic head、diff-check。已知过期fixture失败单列证据，不改有效期规则。
- [ ] 独立只读内审；修复后按影响补验证。Ready PR，核对远端与PR SHA后R1→R2；最新HEAD无P1且检查通过后合并，同步main保留用户改动，才启动PC-04A-2。

## 后续切片边界

PC-04A-2开工时先完成实际校准消费全集与对应详细实施计划；PC-06A-1开工时先查证开关现有能力和清理行为。此计划不预造新仪器协议，不把未实现接口写成既有能力。
