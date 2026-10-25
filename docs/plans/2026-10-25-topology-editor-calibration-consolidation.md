# 拓扑编辑完整性与校准入口整合：审查及待办计划

2026-10-25 用户最初要求审查、规划并写入 todo；初始规划轮不实施功能、不恢复开发 automation，审查基线 main `ad843108`。后续 PC06A2-1 首片已完成实现 `0740620c`，任务级独立规格符合、质量 Approved，待累计整片内审及 PR 外审，未开 PR、未合并；[验证摘要](../validation/2026-10-25-pc06a2-1-calibration-status-truth.md)。本总计划其余范围未实施，继续按仓库流程逐片细化与审查，automation 未恢复。

## 审查结论与证据边界

基础编辑链已存在，但不能签“全面完成”。本次为源码审查及草稿单元测试，不是全浏览器验收，不连接真实仪器。

| 功能 | 当前证据 | 结论 |
|---|---|---|
| 增加节点、改名、拖动 | TopologyEditor.addNode/applyNodeEdit/handleNodesChange | 有实现；新增节点统一 ports=[]，包括普通双端线缆 |
| 声明/删除端口 | topologyDraft.updateDraftNode | 有实现；已连端口拒删；改名不能自动迁移连线 |
| 新建/改端口/删除连线 | addDraftConnection/applyConnectionEdit/removeDraftConnections | 有实现；不是在线插入器件的一步操作 |
| 删除器件 | deleteNodes/removeDraftNodes | 有确认及关联边/模式清理，不删除仪器资源与历史 |
| 保存/失败保留草稿 | handleSave | 调真实 API，失败不清草稿；需浏览器再次验收刷新与跨实验室保护 |
| 隐藏与恢复 | initialNodes + 器件属性“显示模式” | 空选择会使节点从所有模式消失，缺恢复入口 |
| 端口方向 | CustomNodes.withDeclaredPorts | 普通节点每个声明端口同时绘制左右接点；名称 in/out 不约束方向 |
| 显式通路引用 | removeDraftConnections 与 probe.params.rf_path_selection | 删除函数不清理其他探头的显式路径声明；保存/解析影响须定点复现，不据此宣称已发生错误执行 |

实跑：`node --import /Users/simon/.npm/_npx/fd45a72a545557e9/node_modules/tsx/dist/loader.mjs --test gui/test/topologyDraft.test.ts`：16 passed / 0 failed。该 loader 是本机路径；团队可用既有 `npx --yes tsx --test test/topologyDraft.test.ts`（cwd=gui）。没有重跑全后端或浏览器。

### 已确认缺陷

| 级别/位置 | 失败场景 | 修法形状 | 建议方向 |
|---|---|---|---|
| P2，TopologyEditor.tsx 的显示模式 MultiSelect/initialNodes | 清空显示模式并应用后，节点从所有模式消失，不能再双击恢复 | 收窄条件 | 无隐藏器件恢复功能前禁止空模式；校准节点仍仅校准模式 |
| P1，SystemCalibration/index.tsx 顶部状态卡 | 无任何证书查询即显示“有效”、固定截止日期和 TRP/TIS/重复性精度 | 去掉错误逻辑/换来源 | 删除写死的成功与精度；只有可追溯实际证据才显示，缺项 unknown；不把新路径校准结果拿来填 TRP/TIS |

### 非缺陷、体验与待核项

- 普通线缆没有默认两端是当前显式声明策略，不是硬件能力故障；应提供明确双端声明和连接指导，不能由此推断仪器能力。
- 无撤销/重做、复制或插线快捷操作不自动算缺陷；先验证最短人工流程，再按用户价值决定是否纳入。
- 端口复用、自连/环、重复边、被引用边删除及跨模式隐藏需覆盖前端、保存 API、解析三个边界。后端拒绝不等于前端体验已完整，但不能把猜测升级为 P1。

## Todo 1：PC-04A-3 编辑完整性与可恢复性

目标：普通操作员无需猜端口/编辑 JSON，能增加线缆、接入原路径、修改与删除并恢复可见性；不改变物理控制资格。

- [ ] 建立全器件能力矩阵：新增、属性、声明端口、连接、改接、删除、模式、保存、重载；覆盖线缆、接收线缆、衰减器、功放、合路器、探头、仪器和开关。
- [ ] 优先修复清空显示模式导致失去编辑入口；先增加失败测试，再收窄空选择，不强行扩大到其他模式。
- [ ] 为普通双端线缆提供明确 A/B 或 in/out 声明引导、可辨认端口标签；区分物理端口与画布入/出方向。仪器端口仍按声明/目录核验，不统一猜默认能力。
- [ ] 复现插入线缆、改端口名、删除被显式通路引用边/节点；选择明确拒绝并指出受影响通路，或要求操作员重新声明，不能静默转成另一条自动推断路径。
- [ ] 明确线缆节点与连线上的 cable_loss_db 的归属；同一物理线缆不重复计损耗，不把整条测量写进单段。
- [ ] 验收：真实 API + 临时 SQLite + 全 Mock 浏览器跑新增→声明→接线→改接→删除→保存→刷新；覆盖失败保留草稿、跨模式/实验室、采集中禁编辑。只证明软件，不解除现场 B。

主要文件：`gui/src/features/TopologyEditor/{TopologyEditor,CustomNodes,nodePortHelpers,topologyDraft}.tsx/.ts`（以实际扩展名为准）、`gui/test/topologyDraft.test.ts`、`gui/test/topologyEditing.browser.js`、`api-service/app/services/{topology_service,declared_rf_routes}.py`。优先最小局部修改，不为本片重建编辑器。

## Todo 2：PC-06A-2 校准入口职责统一

推荐架构：**系统校准是管理总入口；射频拓扑是路径校准的唯一操作工作台**。不是维护两个平行路径校准表单，也不是删除旧证书历史。

- [x] PC06A2-1 已去掉旧系统校准首页硬编码有效状态/精度，缺证据显示未知（`0740620c`，Task 1/2 独立内审通过；[验证摘要](../validation/2026-10-25-pc06a2-1-calibration-status-truth.md)）。此勾选仅表示实现/本地验证完成，待 PR 外审及合并，不代表 PC-06A-2 整项收口。
- [ ] 枚举 SystemCalibration/CalibrationWizard/CalibrationHistory/CertificateViewer、App 导航和 calibrationService 的入口/API/数据归属；逐项记录保留、跳转、历史只读、方法未验证。
- [ ] 系统校准保留概览、历史、参考件/证书与适用范围信息；“路径损耗/上下行链校准”导航到同一 LabProfile 的拓扑工作台，携带可验证上下文，不伪造已选路由。
- [ ] 拓扑负责接线、选路、单路/批测量、取消/安全清理、结果审阅与采用；复用现有作业和历史服务，不复制引擎。
- [ ] TRP/TIS/相位/静区等独立方法不冒充路径校准能力；核实原功能后保留真实能力或明确不可用及前置条件，不自动解除 PC-09/10 HOLD。
- [ ] 旧记录按原来源展示；不迁移成新真实采集，不补认证，不删证书，不重新计算历史正式结论。
- [ ] 验收双入口导航、LabProfile隔离、历史读取、缺证据 unknown、模拟不正式、唯一采集入口、报告追溯。涉及执行/冻结/安全契约再跑必需全后端。

主要文件：`gui/src/components/SystemCalibration/`、`gui/src/App.tsx`、`gui/src/api/calibrationService.ts`、`gui/src/features/TopologyEditor/RouteCalibrationPanel.tsx`，后端沿实际调用链再定最小范围。顺序为状态卡真实性小片→PC-04A-3→入口整合；WIP=1。每个功能片仍需 TDD、适当回归、独立内审、Ready PR 和 R1/R2。

## 团队共享与规则边界

| 内容 | 当前位置/事实 | 共享方式 |
|---|---|---|
| 正式队列 | docs/roadmap-first-call.md，已受 Git 跟踪 | 作为唯一正式待办；编号、计划、验收链接随对应 PR |
| 本机协作台账 | /Users/simon/Work/mimo-first，仓库外 | 只作本机 claim/交接镜像，不作为团队唯一进度 |
| SDD过程记录 | .superpowers/sdd/.gitignore 为 *，当前 git ls-files .superpowers 为空 | scratch 留本地；最终必要验证/审查摘要放 docs/plans/ 或 docs/validation/，原始大产物用共享存储与可定位链接 |
| 开发/审查规则 | AGENTS.md、CLAUDE.md、.claude/agents/pre-commit-reviewer.md 已跟踪 | 只有已提交并合并版本是团队共享规则；本机未提交规则并未共享 |
| 个人 memory / skill | 用户目录，不随本仓库分发 | 不全量上传；挑项目必需规则经脱敏与审查写入仓库权威文档，避免复制多份真值源 |

本次核查主目录 AGENTS.md 与 CLAUDE.md 均有未提交修改，保留不代提交。CLAUDE.md 已明确 memory 不随仓库分发、不可用时以仓库规则为准。没有读取或上传私人 memory 内容。本计划写入仓库不等于已同步 GitHub；必须经提交、PR、合并才对团队生效。

- [ ] 后续协作规则片：审阅主目录未提交规则差异，按用户规则归属择取需共享部分，不覆盖用户原修改。
- [ ] 每个 PR 描述带 roadmap 编号、受审 SHA、测试/审查证据；状态以 GitHub PR 为准。合并后不为更新“已合并”向受审分支追加提交；下一正常文档片同步 roadmap 快照。
- [ ] 新 clone 仅凭仓库文档即可找到待办/设计/验证/安全边界；不得要求访问某个人 memory 才能理解强制规则。

初始规划轮只登记上述两项功能计划及协作治理检查；后续实际进度见本文开头与 Todo 2 首项。PC-04A-3 及其余入口整合仍未实施，不将其他未批准扩域自动排入执行。
