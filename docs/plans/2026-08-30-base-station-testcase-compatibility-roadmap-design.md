# BaseStation TestCase × Adapter 兼容性 Roadmap 设计

**日期**：2026-08-30

**状态**：P1-75 已合并；P2-64/P2-65/P2-66 已由 PR #433/#434/#435 完成；P2-67 本地实现完成、正在验证/审查

**对应条目**：P1-75、P2-64～P2-67

## 1. 可观察故障

在 HAL Mock 模式下，仪表资源选择 UXM、LabProfile 与 loaded Mock adapter 也都一致指向 UXM，
但 LTE CMW500 TestCase 仍能完成执行并生成诊断报告。冻结证据同时出现 `adapter=uxm`、
UXM manifest `rats=[nr5g]` 与 requested `radio_technology=lte`，系统没有在首次仪表 I/O 前拒绝。

同次调查还确认：

- 两份用户附件字节级相同，只包含第一条 execution；第二条 CMW500 execution 存在于应用日志与数据库；
- 两次执行实际均使用 MockBS，正式数据门正确把结果保持为 UNKNOWN/N/A，没有发现正式 KPI 污染；
- MockBS 无条件声明 NR5G 与 LTE，且通过型号字符串是否包含 `CMW` 猜 adapter；
- Readiness 的 `5/5 instruments ready` 只证明资源在线，不证明当前 TestCase 与 Adapter 兼容；
- CMW500 execution 的公共 release 日志仍写成 `F64/UXM`；导出文件名不含 execution id，容易混淆附件。

## 2. 根因边界

当前 resolver/freeze 已能校验 selected model、LabProfile binding、InstrumentConnection、厂商 profile、
loaded driver、endpoint/transport 与 real/mock 模式，但没有把 TestCase 的结构化需求投影为 required
capabilities，并与冻结 Adapter Manifest 对账。真实驱动在 `apply_requested_config()` 还有 RAT 拒绝门，
Mock 的双 RAT 能力却绕过了这道后置保护。

因此根因不是“UXM 名字没有匹配 CMW500 测试例名字”，而是缺少结构化的
`TestCase requirements × Adapter Manifest` 执行准入合同。测试例名称只能用于展示，不能成为判据。

## 3. 方案比较与批准决策

### 方案 A：最小 P1 + 分层收口（采用）

P1 只关闭错误组合可以启动执行的故障；Mock、Readiness、证据终态与日志导出分别作为后续 P2。
优点是每片只有一个可观察故障，保持 WIP=1 和外审边界清晰。

### 方案 B：一个综合 P1

一次修改执行、Mock、Readiness、GUI、证据、终态和日志。范围跨越过多真值与消费方，容易制造新的
镜像漂移，拒绝。

### 方案 C：只修 Mock

只能遮住本次复现，不能保护真实驱动、未来 Adapter 或 operation/profile/参数维度，拒绝。

用户批准的执行顺序为（2026-08-31 修订）：

`P1-74 → P1-75 → P2-64 → P2-65 → P2-66 → P2-67 → P2-54～P2-62 → P2-63（HOLD）`

P1-75 插在既有 P1-74 之后。**2026-08-31 修订**：初版把 P2-64～P2-67 叠加在 P2-63 之后，
四片派生治理前面压着 P2-54～P2-56、P2-57～P2-62 与 P2-63 共十片，轮到时本次复盘的上下文已冷却；
且 P2-67 要解决的取证混淆（两份附件字节级相同、公共日志硬编码 `F64/UXM`）是已实际发生的问题。
用户批准把四片整组前移到 P1-75 之后。四片不拆开，是因为它们同源于一次复盘、共享同一套
requirements projection 与 digest —— **不是**因为依赖逼着它们连续：旧顺序下这四片的依赖同样
全部满足。前移后重算依赖图零违反。条目本体本次共动三处：P1-74 与 P1-75 两条的「先于」表述
换源到 roadmap 顶部顺序串，P2-54 补记本次前移新产生的 compatibility digest 版本迁移义务；
其余各条的依赖关系逐条复核后仍成立、未动。

## 4. 条目设计

### P1-75 — TestCase × Adapter 执行兼容性硬门

先从当前已有的 `primary_carrier.radio_technology` 与执行所需 operations 构造不可变需求投影，在首次
仪表 I/O 前与冻结 Adapter Manifest 对账。P2-54 落地后只扩展同一 projection 的 MAC profile
kind/version 槽位，不另建判据。Real、Mock、Diagnostic 使用同一判据；不兼容即拒绝创建可运行
execution，不生成报告。兼容性 verdict 与输入 digest 一并冻结，锁内复核 binding/manifest/driver
漂移。不得按测试例名称或 adapter 名称前缀判断。

### P2-64 — Adapter-scoped Mock 能力

Mock 的 RAT、operation、测量窗口与参数边界从所选注册 Manifest 派生；删除 NR/LTE 能力并集与型号
字符串猜 adapter 的行为。Mock 仍保留 simulated provenance，且永不进入正式 KPI。

**2026-09-01 实现状态（PR #433）**：HAL 已把 selected model 的注册 manifest 显式注入唯一 Mock；identity、RAT、
operation、route、window、metric registry 与 UE 诊断 RAT 形状均只读该 manifest。缺失/未知/漂移
fail-loud，未声明可选操作 fail-closed，`diagnostic_unbound` 只借 manifest 决定运行时模拟形状、不会
回填冻结 binding 或正式证据。G27 永久门及坏变异自测已加入；P2-65 未提前实现。

### P2-65 — Preview / Readiness 共用兼容性判定

保存预览、LabProfile 同步、Readiness 与执行冻结消费 P1-75 的同一纯判定器与同一 digest；资源在线
与 TestCase 可执行分别显示。GUI 只能展示服务器判定，不复制能力矩阵或自建 vendor 分支。

**2026-09-01 实现状态（PR #434）**：preview、sync、readiness 与 execution freeze 已共用同一 requirements
projection、compatibility evaluator 与 digest；API 单独发布 resource/binding/TestCase compatibility，
GUI 只消费服务端 status/reasons，并在未保存 TestCase/LabProfile 草稿时 fail-closed。OpenAPI、生成 TS、
手写类型与 Mock 数据镜像已同步；覆盖最终 HEAD 的 Codex R2 无 P1 后合并。

### P2-66 — 执行证据与终态语义

证据初始化/解析拒绝 adapter manifest 与 requested config 自相矛盾；显式区分流程完成、诊断完成与
有效测试完成。Diagnostic 报告可作为审计包保留，但不得形成“配置正确”或“正式成功”的假象。

**2026-09-01 实现状态（PR #435）**：冻结 compatibility 的外层/内层 digest、requirements、verdict 与
resolution 已在读取时重验；共同 outcome 已接入 SCPI evidence、执行阶段、报告、历史、比较、下载、
commissioning 和 GUI。显式畸形/不兼容 fail-closed，Diagnostic 审计包保留但正式指标隐藏，历史无
snapshot 沿旧 provenance。四份 API/TS 镜像与 G29 永久门已完成；覆盖最终 HEAD 的外审无 P1 后以
merge commit `549608cd` 合并。

### P2-67 — 日志与导出可追溯性

公共 lease/session 日志改为 adapter-neutral 或携带冻结 adapter；日志导出文件名包含 execution id 与
时间，GUI 显示并导出冻结 adapter、TestCase RAT 与 compatibility verdict，避免跨 execution 取证混淆。

**2026-09-02 本地实现状态**：公共租约日志已厂商中立并结构化携带 execution id、冻结 adapter/binding；
execution-filtered 导出文件名含完整 UUID，首行 `export_metadata` 只从该执行冻结证据与 P2-66 outcome
派生。GUI 三条路径继续复用同一 query builder，checked/live OpenAPI 已同步，普通导出与 raw download
保持原语义，G30 永久门覆盖已知回归；当前等待完整验证、fresh 内审与外审。

## 5. 不变量与非目标

1. Diagnostic 只放宽现场认证、正式校准与数据发布，不放宽逻辑上不可能的能力组合。
2. 模拟、未知、部分确认与不兼容数据不进入正式 KPI；不得从请求值、默认值或旧缓存回填。
3. P1-75 首片只使用现有 manifest 与结构化 TestCase 真值，不新增或猜测任何 SCPI。
4. P2-54 的 RAT-neutral MAC profile 仍按原计划实施；P1-75 只建立消费该 profile 的准入门，不提前
   实现 P2-54。
5. P2-64～P2-67 不改变 P2-56、P2-61、P2-63 的真机认证条件，本地测试不能替代现场复验。
6. 本设计只进入 Todo/Discovered 雷达；每片启动时仍须按 AGENTS.md 0.5 重列全部产生方、消费方、
   入口、历史读取与失败路径，并单独形成设计和实施计划。
