# MIMO-First — First-Call Roadmap

> **Single source of truth for what we're working on next.** All non-trivial
> development MUST reference an item on this roadmap. Off-roadmap work needs
> explicit justification (see [governance rules](#governance-rules) below).

---

## 🎯 Current Focus

**当前状态（现场链事实截至 2026-08-07；本地队列截至 2026-08-22）**：ARCH-1 整案收官（S1–S6 全 ✅，见下方 ARCH-1 表）。P0-5
已经完成 DUT attach 与转台四方向吞吐，证明物理链路可工作；P1-47A/B/C 已补齐关键
SCPI“发送 → 接受 → 生效 → 业务结果”的同次执行机制，但现场身份、坐标偏置与正式
TestCase 复验尚未补齐，故 **P0-5 正式自动化验收仍未关闭**。P0-8
现场半同样仍 blocked（见 Blocked on hardware 表）。
**六项自 Discovered 区按既定 triage 出口提升为正式 P 编号 + 两项门候选直接立项**
（P3-16/17，无 Discovered 来源条目）。**执行顺序与当前片记在本段，完成状态在各 P 条目/表处**：
**2026-08-06 用户批准把 P0-5 SCPI 证据闭环整体前置**：
**~~P1-25~~ ✅ → ~~P1-26~~ ✅ → ~~P1-30~~ ✅ → ~~P1-31~~ ✅ → ~~P1-32~~ ✅ → ~~P1-33（本地半）~~ ✅ → ~~P1-34~~ ✅ → ~~P1-35~~ ✅ → ~~P1-36~~ ✅ → ~~P1-39~~ ✅ → ~~P1-45~~ ✅ → ~~P1-46~~ ✅ → ~~P1-41~~ ✅ → ~~P1-47A~~ ✅ → ~~P1-47B~~ ✅ → ~~P1-47C~~ ✅ → ~~P1-28~~ ✅ → ~~P1-43~~ ✅ → ~~P1-44~~ ✅ → ~~P1-42~~ ✅ → ~~P1-40~~ ✅ → ~~P1-37~~ ✅ → ~~P1-48~~ ✅ → ~~P1-29~~ ✅ → ~~P1-38~~ ✅ → ~~P1-27~~ ✅ → ~~P2-22~~ ✅ → ~~P2-23~~ ✅ → ~~P2-24~~ ✅ → ~~P3-18~~ ✅ → ~~P3-19~~ ✅。

**Current Focus = P1-63「正式 RF KPI 必须具有逐指标真实来源证据」**。最近一次手工测试日志
证明报告四态、路损应用叙事已按 P1-61/P1-62 收口，同时暴露 MEASURE 在真实驱动组合下仍会
用目标功率、探头增益与 `random.gauss()` 合成 RSRP/SINR，并把默认 RI 当作仪器样本写入正式
判决链。P1-63 将删除这条合成正式数据路径，只允许有限数值、驱动逐指标 `kpi_valid` 明确为真、
且整条执行 provenance 为真实的 RSRP/SINR/RI 进入 ANALYSIS、报告、历史与 verdict；诊断/模拟
执行仍可完成并生成诊断报告，但正式结论保持 UNKNOWN/N/A。设计与证据见
[`P1-63 设计`](plans/2026-08-23-p1-63-rf-kpi-provenance-truth-design.md)。
实现已按 TDD 完成：MEASURE 不再合成正式 RSRP/SINR，也不再把默认 RI 当样本；ANALYSIS、
报告、详情/下载、执行历史与 GUI 统一消费版本化逐指标白名单。两次 fresh 内审发现的六条 P1
已按 TDD 收口：快照必须绑定当前有限数值、精确请求方位全集与当前 explicit-real provenance；
额外方位、模拟来源、非对象/畸形历史行和失配旧快照全部安全降级，不能进入正式统计或生成
不可查看的恢复报告。当前验证为相关链与完整规则门 **203 passed**、受影响历史/报告链
**143 passed**、全后端 **4339 passed / 5 skipped**、GUI 契约 **3 passed** 与 production build；
compileall、单一 Alembic head、diff-check 均通过；当前进入最终 fresh 尾审，尚未合并。

**下一顺位 = P1-64「静区纹波无真实测量证据不得显示预检通过」**。当前无 ProbePattern 时的
0.7 dB 兜底会形成 `quiet_zone_pass=true`，并被 ANALYSIS、报告与 GUI 解释为正式通过。P1-64
将把“诊断流程允许继续”与“正式静区判定通过”分离；无真实证据时显示 N/A/未验证并保持正式
UNKNOWN，不把 0.7 dB 叙述为实测值。P1-64 只占位，须在 P1-63 合并后从最新 main 独立实施。

> **~~P1-62~~ ✅ 2026-08-22 由 PR #373 完成**：版本化 `path_loss_application` 已贯穿
> PRECHECK、MEASURE、Analysis、报告、历史与 GUI；旧/畸形快照和旧 PDF 均不能凭遗留布尔标记
> 救回正式 PASS。Codex R1/R2 的正式判定与旧报告信任绕过已按 TDD 修复，R3 覆盖最终 HEAD
> `aa9cc58` 且无重大问题；merge commit `6b2b064`。

> **~~P1-61~~ ✅ 2026-08-22 由 PR #372 完成**：报告由最终执行生命周期 CAS 赢家发布，
> 四态、真实耗时、取消仲裁与 UXM/F64 Local 交还事实同源；Codex R1～R3 的缺失 verdict 假
> FAIL、顶层 pass rate 漏镜像、交还失败告警生命周期 P1 均已按 TDD 修复，R4 覆盖最终 HEAD
> `7b43b10` 且无重大问题；merge commit `425e389`。设计见
> [`P1-61 设计`](plans/2026-08-22-p1-61-report-final-state-truth-design.md)。

> **~~P1-60~~ ✅ 2026-08-22 由 PR #371 完成**：探头/端口编号、相位校准、ChannelAsset
> 场景、带宽 warning 与操作员时区五项真值已收口；Codex R1/R2 的 vendor 文件与时区 P2、
> R3 的 model/scenario 假冲突 P1 均按 TDD 修复，R4 覆盖最终 HEAD `cb10d65` 且无重大问题；
> merge commit `ebccb1e`。设计与证据见
> [`P1-60 设计`](plans/2026-08-22-p1-60-execution-truth-alignment-design.md)。

> **~~P2-31~~ ✅ 2026-08-22 由 PR #368 完成**：服务端只从固定只读挂载中解析 `.smu`
> `[Channel Group 0] CenterFrequency`，文件名永不作为频率真值；完整 Windows 路径只精确匹配
> 已登记 `vendor_file` 资产，未登记、重复、跨绑定、非栅格和坏工程全部保护。无请求体的 scan/sync
> API、GUI 预览/显式确认、live OpenAPI / checked-in YAML / generated TS 已同步。sync 在写入前
> 重新锁定并刷新连接与完整 ChannelAsset 规范名空间，在锁内二次扫描分类，资产 provenance、ARFCN、
> 顶层频率、绑定与 `available_channel_models` 单事务更新；不创建资产、不写 SMB/F64、不双写
> legacy SCD。相关组 **252 passed**、GUI 契约 **3 passed**、production build、`compileall`、
> 全后端最新 **4228 passed / 5 skipped**、单一 Alembic head、`diff-check` 通过；fresh 内审发现的并发旧快照覆盖与 `MF_` 文件名反压
> group 0 两条 P1 均已按 TDD 收口。Codex R1 又发现运行 resolver 仍会用旧 `MF_` 文件名拒绝
> 已同步资产，以及提交后 SMB 复扫失败会把已提交成功误报为失败；两条均已按 TDD 收口，工程证据判据
> 收敛为执行与编辑共用的服务端白名单，成功响应不再做 fallible post-commit I/O，fresh 尾审
> **P1/P2/P3=0**。
> R2 对 0 Hz 的 P1 经执行链复核为误报：正整数 ARFCN 门已在任何写入前将其分类为
> `invalid_asset`，定点诊断证明资产与 `available_channel_models` 均不变；R2 的 legacy
> projection P2 按规则仅报告、不阻塞。merge commit `2c9d5ff`。

> **P3-22 当前设计证据**：`git ls-files 'api-service/tests/**' 'gui/test/**'`
> 复算为 216 个 tracked 文件、82,803 行，全后端基线
> **4228 passed / 5 skipped**。首轮归一化候选审计仅确认 HAL 模式决策表满足同 fixture、
> 同路径、同断言语义；已收敛 40 行重复源码，仍保留 10 个具名参数 cell 与 2 个枚举 wire
> 契约。三组反向变异分别让 1 / 2 / 4 个对应 cell 变红；focused + 完整 rule gates
> **65 passed**，全后端仍为 **4228 passed / 5 skipped**，`compileall`、`diff-check` 通过，
> 产品代码零改动。静态/UUID 路由和两个不同生命周期数据库 fixture 的失败场景不同，明确不删。
> Codex R1 的测试行数基线 P3 已换成可复现的 tracked-file 口径；R2 覆盖修正 HEAD
> `78cd070` 且无重大问题，PR #369 完成后暂停，不自动启动维护池条目。
> P2-40 的已批准实际清理已完成；精确删除范围与保护范围见下方收口记录。

> **~~P2-36~~ ✅ 2026-08-22 现状核验收口**：该条目的“执行历史一键跳本次执行日志”
> 已由 P1-39 / PR #292 在提交 `5c89a60` 完整交付；当前 main 仍保留
> `HistoryTab → App → ReportsPage → SystemLogViewer` 四段接线，传递与过滤使用完整
> execution ID，并以一次性交接避免后续页面劫持。2026-08-21 从旧 Discovered 再次提升为
> P2-36 属 roadmap 重复项，不重复实现。核验证据见
> [`P2-36 现状核验`](plans/2026-08-22-p2-36-execution-history-log-jump-reconciliation.md)。

> **~~P2-38~~ ✅ 2026-08-22 由 PR #366 完成**：R1 的缓存假绿 P1 已按 TDD 收口，
> R2 覆盖最终 HEAD `f5d28dd` 且无重大问题；merge commit `e017f4b`。

> **P2-38 开发证据**：Dashboard 只有在顶部存在显式 LabProfile 选择时才读取 readiness，
> 查询参数与 React Query key 共同使用该 ID；后端通过 active 白名单精确解析，按请求重建
> LabProfile 与校准段，missing/inactive 返回 422 且不回退。HAL unavailable、无显式选择、
> 轮询错误保留旧缓存三类假绿路径均已 fail-closed。Codex R1 进一步指出切回已有 query key
> 时会短暂发布缓存旧绿；现只在 `fetchStatus === 'idle'` 时发布结论，`fetching` 与离线
> `paused` 均明确阻断。focused readiness / resolver / OpenAPI / 完整 rule gates **116 passed**，
> GUI 契约 **23 passed**，全后端
> **4201 passed / 5 skipped**，production build、`compileall`、`diff-check` 通过；修后 fresh
> 尾审 **P1=0、P2=0**（P3=1 组件运行测试建议按规则不阻塞）。设计与证据见
> [`P2-38 设计`](plans/2026-08-22-p2-38-dashboard-readiness-lab-profile-design.md)。

> **~~P2-37~~ ✅ 2026-08-22 由 PR #365 完成**：后台 connected 监控不再读取未展示的
> 全量 UE L3 队列；正式 MIMO OTA 窗口只有在 report clear 经传输与设备错误队列确认后才
> 读取 L3，clear 不可确认时只跳过未验证 L3，普通 KPI 继续。Codex R1 无重大问题；R2
> 仅一条验证输出留存 P3，按规则不阻塞，merge commit `406ff71`。

> **P2-37 开发证据**：后台 connected 监控不再读取未展示的全量 UE L3 队列；正式
> MIMO OTA 窗口只有在全局 report clear 命令存在、传输成功且设备错误队列确认接受后，
> 才在窗口末读取 L3。clear 缺失/异常/被拒时只将 L3 保持 UNKNOWN，其他可信 KPI 继续；
> 未新增 SCPI，未确认单位的 L3 仍只进 `kpi_raw_unverified`。RED 覆盖后台旧读取和正式
> clear 四类失败，GREEN focused **109 passed**、相关链与完整 rule gates **226 passed**、
> 全后端 **4193 passed / 5 skipped**，`compileall`、`diff-check` 通过；fresh 内审
> **P1/P2/P3=0**。设计与证据见
> [`P2-37 设计`](plans/2026-08-22-p2-37-ue-l3-bounded-consumption-design.md)。

> **~~P2-40~~ ✅ 2026-08-22 由 PR #364 完成**：只读 inventory 与测试 SQLite
> 临时目录隔离已由 merge commit `65765ce` 合入；Codex R2 覆盖最终 HEAD 且无 P1，
> 仅提示实际隔离前必须重新确认 open state。PR 本身未移动、备份或删除任何 DB、日志、
> volume 或 worktree；合并后经用户逐级批准，20 个零 schema、closed 的测试 SQLite 已先按
> manifest 隔离，再永久删除，共 21,299,200 bytes。运行日志、生产 PostgreSQL、Docker
> volume 与 worktree 均未纳入删除范围；删除后数据不可恢复，SHA-256、原路径与操作回执保存在
> `/Users/simon/Meta3D-Artifacts/quarantine/2026-08-22-p2-40-deletion-receipt.json` 和
> `/Users/simon/Meta3D-Artifacts/quarantine/2026-08-22-p2-40-moves.json`。

> **~~P2-39~~ ✅ 2026-08-21 由 PR #363 完成**：pytest 在导入 `app.main`
> 前无条件将 `LOG_DIR` 换到进程级 `TemporaryDirectory`，生产日志链零改动；子进程回归证明
> 运行日志文件名、字节、大小与 mtime 均不再被 pytest 改写或轮转。R1 无重大问题；R2
> 只有一条基于错误提交祖先前提的 P3，复核后不改功能。merge commit `9417fee`。
> 验证：日志相关 **66 passed**、完整 rule gates **53 passed**、全后端
> **4172 passed / 5 skipped**，全量前后运行日志 manifest 一致，`compileall`、
> `diff-check` 通过。

> **P2-40 清理前只读实证（历史快照）**：主工作区日志 338 个文件 / 约 2.6 GB，
> 其中当前日志仍被运行服务打开；P1-59 worktree 约 242 MB，Claude worktree 约 11 MB；
> 四组校准测试在不同 cwd 留下多份约 1 MB 的空 schema SQLite；活跃
> `meta3d_postgres_data` 约 79.7 MB，必须备份保护；另有 14 个未挂载匿名 Docker
> volume，仅凭匿名标签无法证明属于本项目，暂列人工复核而非清理候选。设计与实施计划见
> [`P2-40 设计`](plans/2026-08-21-p2-40-dev-artifact-governance-design.md) 和
> [`P2-40 计划`](plans/2026-08-21-p2-40-dev-artifact-governance-plan.md)。PR 只建立只读
> manifest 与阻止测试 SQLite 继续沉积；实际清理是合并后取得用户明确批准的独立操作，范围
> 仅限上段 20 个已确认测试 SQLite。

> **P2-40 合并前开发证据快照（实际清理仍未执行）**：只读 inventory 已覆盖注册 worktree、
> 显式日志根、三层 SQLite 白名单与 Docker volume/mount/size；未知身份默认 protect，关闭日志
> 也只进入 review。真实 dry-run 共识别 filesystem 383 项 / 3,037,840,761 bytes：protect
> 339 项（含 10 个确定活跃日志，以及目录级 `lsof` 非零时 328 个不猜 closed 的 UNKNOWN 日志）、
> review 24 项、候选 20 项 / 21,299,200 bytes；候选全部为精确
> 产生方 + 空 schema + closed 的四类测试 SQLite。Docker 2 个 mounted volume 保护，14 个
> unmounted anonymous volume / 520.5 MB 只 review。四个测试产生方已换到 pytest 临时目录，
> 子进程 RED 留 4 个 DB，GREEN 留 0 个；R1 指出的 view-only schema 漏判已收窄为检查全部
> `sqlite_schema` 对象。四模块+inventory **230 passed**，相关+规则门 **283 passed**，
> 全后端 **4189 passed / 5 skipped**；尾修 fresh 内审 **P1/P2/P3=0**。所有现存文件、日志、
> volume 与 worktree 均未移动或删除；批准单与恢复方案记录在 P2-40 设计。

> **~~P1-59~~ ✅ 2026-08-21 由 PR #362 完成**：正式测量新增显式
> `pcell` / `nr_all_cells` scope；CA 只允许使用 Keysight 手册有出处的
> `DL/UL ...OTA:ALL?`，PCell query 不再作为回退。SCell inherit、能力缺失、部分添加、
> 仪器清单不匹配、错误队列拒绝任一路都会在正式采样前失败。报告重新核对载波数、顶层与
> 逐方位 scope，吞吐 trust schema 升到 2，旧 schema 1 全部 fail-closed。
> 当前 `LTE_NR_IRAT` profile 尚缺完整且有出处的 SCell 逐载波配置/激活命令，因此真实
> IRAT CA 会明确阻断而不会再生成 PCell-only 假报告；现场兼容性证据补齐前不猜另一方言。
> R1 指出“命令接受不等于 UE 实际激活全部 SCell”的 P1，已在 `93acacc` 按 TDD
> 收紧：两种真实 UXM profile 均缺逐 SCell 激活态权威回读，因此不发送激活动作并保持
> CA UNKNOWN/阻断。R2 进一步指出旧 CA verdict 仍能从 Analysis 写回和执行历史泄漏；
> 两条消费路径现与正式报告复用同一个“载波数 + 顶层 scope + 逐方位 scope”证明，旧证据
> 一律保持 UNKNOWN。R3 又指出部分 SCell 添加失败后的清理结果会被直接返回吞掉；现已消费
> `remove_all_secondary_cells()` 的布尔契约，并把未确认清理与残留 SCell 风险写入失败结果。
> R4 进一步指出已知无法证明激活的真实 UXM 仍会先写 SCell 再失败；现将逐 SCell 激活态
> 权威回读设为显式白名单能力，所有真实驱动在首次 SCell 写入前阻断，只有完整掌握内存
> SCell 集合的 Mock 显式放行。R5 覆盖最终 HEAD `1be7484` 且无 P1，merge commit
> `af27b2e`。验证：相关及安全对称链 **349 passed**；全后端 **4171 passed / 5 skipped**；
> `compileall`、`diff-check` 通过；fresh 尾审 **P1/P2/P3=0**。逐 SCell 激活态与 IRAT
> 完整配置/激活命令的现场真值仍保持 Hardware Blocked，不猜测补全。

> **2026-08-21 并行批次收口 + Discovered 价值复核（用户批准）**：第一波
> P1-58 / P2-35 / P2-30 / P2-33 / P2-34 已全部合并（PR #358 / #357 / #359 /
> #360 / #361）。第二波不再机械照旧编号施工：保留并收窄 P2-31；P2-36 当时被保留，
> 但 2026-08-22 后续核验确认它已由 PR #292 交付，因此按重复项关闭；
> P2-32 转功能启用池，P3-20/P3-21 转非阻塞维护池。新晋升仍可复现的产品故障
> P1-59 / P2-37 / P2-38 / P2-39，以及用户要求的开发沉积治理 P2-40 / P3-22。
> 设计与裁决依据见
> [`2026-08-21 Roadmap / Discovered 收口设计`](plans/2026-08-21-roadmap-discovered-triage-design.md)。

> **~~P2-29~~ ✅ 2026-08-21 由 PR #354 完成**（ASC/B2 正式模型加载证据 hook）。零新 SCPI：四条管线（GCM/ASC/B2/external_asc）统一走 CALC:FILT:FILE 事务证据；驱动 ASC/B2 成功分支补 MODEL:STATE?/STATE? 探针（手册确认状态机与文件来源无关：AN §2.1 + UR §20.4.3.14，NotebookLM 原文查证）；归档 requested 换驱动真值 `_loaded_emulation_file`（内审 F1 P1：意图值直传会把成功的加载谎报成 rejected —— 比诚实 unknown 更糟）。验证：全量 4068 passed（唯一失败与 main 基线同条 —— Discovered 里的 contextvar 泄漏，相对 main 零新失败）、变异 8+ 条实跑红、相关组 199 passed。**顺带修**：08-18 起挂死一切全量运行的 47a 死锁测试已按现契约重写（此前全量在本机根本跑不完）。外审由 Gemini 承担（Codex 额度尽）：R1 一条已修，R2 两条 medium（测试风格：未用的驱动实例化残留、函数内重复 import）按 R2+ 规则**报备不修**。ASC/B2 真机证据链保持 Hardware Blocked，与 P0-5 复验同窗口。

> **~~P1-57~~ ✅ 2026-08-20 由 PR #353 完成**（全局 LabProfile / 当前暗室上下文统一）。运行态唯一真值 = 全局显式 LabProfile → `chamber_config_id` → 暗室；顶部唯一选择器，拓扑/探头/首测/OTA Mapper/诊断/RF chain/校准页全部收编（校准页原来写死 **P1-28 已删除的孤儿暗室 id**，外审 R3 抓出）；topology API 按 `lab_profile_id` 走 `resolve_current_chamber()`；未保存拓扑与在途硬件工作（provider 级登记，页面卸载不消失）阻断切换。外审 R1 3P2 / R2 1P1+2P2 / R3 3P1 全修；R4 因 Codex 额度改由 Gemini 承担，无 P1 级发现（1 条 medium：模板导入无条件让位默认拓扑 —— 属 main 遗留、影响面今日为零，按 R2+ 规则只报告不修，记录在 PR 对话）。验证：后端相关 + 全部规则门 127 passed、GUI 契约 42 条、build、compileall、diff-check 全过；手工验收环境（worktree 服务 + 双 lab 场景说明）已交付用户，用户指示继续下一项。

P2-28 已由 PR #352 完成并合并。P1-55
已由 PR #349（merge `b6f631a`）完成顶层配置与 `component_carriers[0]` 真值源收敛；P1-54
已由 PR #348 合并；用户已确认继续下一项。P2-26 已由 PR #347
（merge `ef50070`）完成历史 MIMO 报告 UNKNOWN/N/A 的安全重建与恢复界面。P1-54 将 UXM
已有的 `kpi_valid` 真值推进 `ThroughputMetrics`、`to_dict()`、MEASURE、ANALYSIS 与报告：
真实零吞吐仍是有效样本，缺测/NaN/查询失败保持 `None/UNKNOWN`，不得再以默认 `0.0`
生成假的低吞吐 KPI；旧报告还必须经吞吐 trust marker 或安全重建，不能复用历史默认零值。
设计见 [`P1-54 设计`](plans/2026-08-16-p1-54-kpi-valid-data-contract-design.md)。P1-50 已由 PR #343（merge `e10afa4`）
完成留存失败告警上下文隔离，内审与两轮 Codex 外审均无 P1；告警仍进入 app/console，但不再
回流重开执行文件或泄漏 fd。P1-49 已由 PR #342（merge `3e0a11d`）
完成两个静态 GET 路由顺序修复、真实 HTTP 回归与 G19 零例外收口；内审与两轮 Codex 外审均无 P1。
P2-25 已由 PR #340（merge `ece3965`）
完成实现、两轮外审与合并：系统日志已分为当前/历史，历史再分分类/执行；历史可按日期、时间、中文分类、
文件名或 execution ID 搜索。2026-08-12 用户批准新队列并明确 P2-25 完成后回到
P1-49～P1-53；2026-08-16 用户明确一个编号项默认连续走完设计、开发、内审、两轮外审、合并，
随后自动开始下一项。P1-51 的实施依据保留在
[`P1-51 设计`](plans/2026-08-16-p1-51-no-guessed-instrument-ip-design.md)：
全部真实驱动与 fresh bootstrap 已删除猜测地址；缺少、冲突或与活动 HAL 会话不一致的显式连接配置，
均在任何外部 I/O 前明确失败，已有数据库连接值不自动清空。

**2026-08-12 批准队列（稳定编号，逐片 WIP=1）**：
**P2-25 → P1-49 → P1-50 → P1-51 → P1-52 → P1-53 → P2-26 → P1-54 → P1-55 → P1-56 → P2-27 →
P2-28 → ~~P1-57~~ ✅ → ~~P2-29~~ ✅ → ~~P2-30~~ ✅ → ~~P2-33~~ ✅ →
~~P2-34~~ ✅ → ~~P2-35~~ ✅ → ~~P1-58~~ ✅ → ~~P1-59~~ ✅ → **~~P2-39~~ ✅ → ~~P2-40~~ ✅ →
~~P2-37~~ ✅ → ~~P2-38~~ ✅ → ~~P2-36~~ ✅ → ~~P2-31~~ ✅ → ~~P3-22~~ ✅ →
~~P1-60~~ ✅ → ~~P1-61~~ ✅ → ~~P1-62~~ ✅ → **P1-63 → P1-64**。

| ID | 正式条目 | 当前状态 |
|---|---|---|
| **P1-49** | 修复 `/calibration/channel/temporal/latest`、`/topologies/default` 静态路由遮挡 | ✅ PR #342 |
| **P1-50** | 日志留存清理失败时禁止回流重开执行文件并泄漏 fd | ✅ PR #343 |
| **P1-51** | 删除仪表默认 IP 猜测；缺配置时 fail-closed | ✅ PR #344 |
| **P1-52** | TestCase 编辑时 LabProfile 列表加载失败不得清空原绑定 | ✅ PR #345 |
| **P1-53** | 多暗室校准数据隔离，禁止跨暗室误用校准结果 | ✅ PR #346 |
| **P2-25** | 当前/历史日志分类；历史按分类/执行分组并支持时间、名称、execution ID 搜索 | ✅ PR #340 |
| **P2-26** | 历史 MIMO 报告 UNKNOWN/N/A 的重新生成与恢复界面 | ✅ PR #347 |
| **P1-54** | `kpi_valid` 进入正式数据契约；缺测吞吐不得以默认 0.0 进入 MEASURE/KPI | ✅ PR #348 |
| **P1-55** | 收敛顶层配置与 `component_carriers[0]`；统一写入、显示与执行真值源 | ✅ PR #349 |
| **P1-56** | 转台命令成功但编码器不动：本地动作真值门与诊断载体 | ✅ PR #350；[补充 Codex 结论](https://github.com/swang430/Meta-3D/pull/350#issuecomment-5327846839)明确 reviewed commit `0f981339c5`（包含尾修 `bd71879`）且无重大问题；物理现场验证保持 Hardware Blocked |
| **P2-27** | 修复 9 组前端手写契约与 live OpenAPI 不一致 | ✅ PR #351 |
| **P2-28** | 诊断序列完整证据持久化 | ✅ PR #352；R1/R2 均无重大问题 |
| **~~P1-57~~** | 全局 LabProfile / 当前暗室上下文统一；拓扑、探头与首测不得各自选暗室 | ✅ PR #353（R1–R3 全修；R4 Gemini 无 P1） |
| **~~P2-29~~** | ASC/B2 正式模型加载证据 hook | ✅ PR #354（内审 F1 P1 已修；Gemini R1 已修 / R2 两条 medium 报备不修） |
| **P2-30** | 校准/方向图任务级仪表租约，避免逐点重连 | ✅ PR #359 |
| **P2-31** | P2-18 剩余交付片：SMB `.smu` 工程真值扫描（EMQuest 10-band 表已交付） | ✅ PR #368；merge `2c9d5ff` |
| **P2-32** | QZ/方向图/多频 warning 的 real API、GUI、DB、报告闭环 | ↪ 功能启用池；当前无完整 real 入口/production caller |
| **P2-33** | 日志体验包：CRITICAL、traceback 搜索、级别多选、重复请求抑制 | ✅ PR #360 |
| **P2-34** | 正式执行失败告警的发布结果契约 | ✅ PR #361 |
| **P3-20** | 删除或重写失效的校准导入/导出链 | ↪ 非阻塞维护池；无 live caller |
| **P3-21** | 统一 UXM 两套诊断错误队列读取逻辑 | ↪ 非阻塞维护池；诊断 helper 已有上界 |
| **P1-58** | `uxm_scpi_compatibility` 判据按当前方言 profile 派生，四态结果不再折叠 | ✅ PR #358（最终 HEAD 经 R3 覆盖，无 P1） |
| **P2-35** | `current_execution_id` 测试间泄漏隔离 | ✅ PR #357 |
| **P2-36** | 执行历史一键跳本次执行日志 | ✅ 已由 P1-39 / PR #292（`5c89a60`）交付；2026-08-22 核验为重复项 |
| **P1-59** | CA 多小区正式吞吐使用聚合真值；PCell-only 不得冒充 CA 总吞吐 | ✅ PR #362（R5 覆盖最终 HEAD，无 P1）；逐 SCell 激活态回读现场证据仍 Hardware Blocked |
| **P2-37** | UE L3 报告队列有界消费，避免后台监控响应/日志无界增长 | ✅ PR #365；merge `406ff71` |
| **P2-38** | Dashboard readiness 显式消费顶部选定 LabProfile | ✅ PR #366；merge `e017f4b`；R2 覆盖最终 HEAD 无 P1 |
| **P2-39** | pytest 与运行日志目录隔离，测试不得轮转删除历史仪器证据 | ✅ PR #363；merge `9417fee` |
| **P2-40** | 开发环境 DB / 日志沉积盘点、备份与可恢复清理 | ✅ PR #364；merge `65765ce`；合并后经用户批准永久删除 20 个空测试 SQLite（21,299,200 bytes），其余资产保持保护 |
| **P3-22** | 测试冗余按产品契约收敛，不降低核心保护 | ✅ PR #369；R2 无 P1 |
| **P1-60** | 最近一次手工执行的校准、信道与时间真值对齐 | ✅ PR #371；R4 覆盖最终 HEAD 无 P1；merge `ebccb1e` |
| **P1-61** | 正式 MIMO 报告必须使用最终执行状态、真实耗时与四态判决 | ✅ PR #372 / merge `425e389`；Codex R4 覆盖最终 HEAD 且无重大问题 |
| **P1-62** | 已应用但来源未知的路损证书不得被叙述为“无证书/未补偿” | ✅ PR #373；R3 覆盖最终 HEAD 无 P1；merge `6b2b064` |
| **P1-63** | 正式 RSRP/SINR/RI 必须具有逐指标真实来源证据，禁止合成值/默认值进入判决 | 🔄 Current Focus；TDD、全量回归与 fresh P1 尾修完成，fresh 尾审中 |
| **P1-64** | 无真实静区纹波证据时不得显示预检通过或把 0.7 dB 兜底叙述为实测 | ⏭ P1-63 合并后独立实施；已占位 |

> **~~P1-48~~ ✅ 2026-08-10 完成**（2026-08-09 插队，兼作 Gemini 外审首测对象）。五片全部 merge 进 main：#308 日志线 / #313 删掉四条整体返回随机数的报告接口（−955 行）/ #312 路损校准拒绝模拟驱动 / #310 报告线 / #314 虚拟路测不再编数。
> **代价记录**：外审 27 轮 30 条，其中 #314 一个 PR 占 12 轮 22 条；复盘后 ①内审改成每次 push 前都过（新增轻量档）②「改之前先列全集」写进三份规则文档 ③规则整理 #316（消 8 处手工同步契约、轮次上限改分级）。
> **Gemini 外审实验结论**：接通了，但唯一那条 finding 是幻觉（指着正确的字符串说它是笔误，全仓 grep 0 命中），后续外审仍以 Codex 为准。

> **2026-08-07/08 现场插队批次已收口**：PR #303（日志四片）+ #304（现场驱动阻塞 + 内审收口）
> 均已 merge 进 main（`1430a6e` / `7e4f602`）。**现场半仍 blocked** —— 三个 attach 里程碑
> 零现场实证、四条新待验（NEW-1..4）载体全部待建，见「Blocked on hardware」表。
>
> ⚠ **两个 PR 的尾部 commit 都没过外审**（Codex 额度耗尽 + 「push 新 commit 不触发 Codex」
> 这个已知陷阱）：#303 的 `af51abb`（代码）/ `df33191`（文档）、#304 的 `9f29419` / `a7819ff`
> （均为代码）。2026-08-09 已接入 Gemini Code Assist 补审，`/gemini review` 已在 #303 触发。
>
> ⚠ **`add-new-features` 分支尚未处理**（乾径科技，49 文件 +16167，无 PR）——
> 内容是 2026-06 积压的 FS16/UXM 功能线，跟 8/7 现场无关，按用户 2026-08-08 判断「放在最后」。
> 它与已 merge 的现场分支有 **3 处硬冲突**，最要紧的是 `send_scpi_command` 里它新增的
> `manual_local` 闸门 vs 现场分支的 `instrument_test_lease` 租约 —— 两套控制权语义抢同一位置，
> 且那道闸门对**所有**仪器类别泛化生效。**合并前必须先裁决哪套语义算数，不能靠解冲突糊过去。**

> **2026-08-07/08 现场插队**（用户当日拍板）：CAICT 现场暴露的驱动阻塞 + 其内审收口。
> 这批 out-of-roadmap，19 个 commit（Codex 现场 1 个 + 修复 18 个），全量
> **3542 passed / 0 failed**。做了什么：
> ① 现场阻塞（TDD pattern 与周期对不上、AMC 组 -113 拦死 measure、attach 判据用错
>    对象、现场基线被写进共享 schema 默认值会改写全库既有用例）；
> ② 内审 11 条 findings 全部处置（P1 与「修复不算数」那批已修并配会红的门，
>    F4/F8/F9/F10/F12 进 Discovered 并写明不做的理由）；
> ③ **测试第一次能跑完全量** —— 此前 conftest 以 REAL 模式拉起 HAL 去连
>    `192.168.100.x`，本机 TUN 下挂死 11m47s，内审那道「全量输出」硬门一直落空。
>
> ⚠ 现场半仍 blocked：三个 attach 里程碑**零现场实证**，四条新的现场待验
> （NEW-1..4）载体全部待建 —— 见下方「Blocked on hardware」表。

P1-45/46/41/47A-C 不是六条互不相干的插队需求，而是同一条
SCPI 闭环依赖链：先把现场项映射到载体 → 用手册证据修判定和缺失载体 → 止住错误队列
无限循环 → 补传输配对 → 补仪器接受/生效语义 → 接入正式 TestCase。该本地链已完成；
P0-5 保持 ON-SITE-BLOCKED；P1-44/42/40/37 已在 Draft PR #303 完成本地实现与回归，
本地序列现切到 **P3-18 / 手写类型递归审计收口子片**（P1-29 已由 PR #320、P1-38 已由 PR #321、P1-27 已由 PR #322、P2-22 已由 PR #323、P2-23 已由 PR #324、P2-24 已由 PR #325、P3-18 PDF/G11/p08/诊断序列子片已由 PR #326/#327/#328/#329 收口）。本轮日志设计与逐片实施计划见
[`plans/2026-08-07-log-sprint-design.md`](plans/2026-08-07-log-sprint-design.md) /
[`plans/2026-08-07-log-sprint.md`](plans/2026-08-07-log-sprint.md)；SCPI 闭环设计与实施计划见
[`plans/2026-08-06-scpi-evidence-closure-design.md`](plans/2026-08-06-scpi-evidence-closure-design.md) /
[`plans/2026-08-06-scpi-evidence-closure-implementation.md`](plans/2026-08-06-scpi-evidence-closure-implementation.md)。一句话索引：
- **P1-25** GUI 主控台"系统状态"面板恒空修复 + api.ts 手写镜像同尺审计
- **P1-26** GUI 改频同步 component_carriers（**GUI 写侧**收口；后端收敛点与显示端同源另立片）
- **P1-30** SCPI 往返日志的证据能力（截断显式化 + OK/ERR 配对 + `instrument_id` 收窄）
- **P1-31** `uxm_kpi_readback` 诊断序列（#275 那批 KPI 命令的现场对账载体）✅
- **P1-32** `configure_mac_throughput_test()` 在 IRAT 上 11/11 命令为 `None`（不崩 + 不假成功 + 调用方消费）✅
- **P1-33（本地半）** 按手册重写 IRAT 的 8 组 MAC 配置命令（含值形态转换；现场半在 Blocked 表）✅
- **P1-34** 日志时间线可读（本地时区 + `request_id` 把一次操作串起来 + 排除只吞成功那一行）
- **P1-35** 日志噪音治理（`Cache updated` 每秒两条占 26%）—— **从 P3-19 摘出提前**，2026-08-05 用户手工测试当场要求
- **P1-36** 测试执行身份进日志（`execution_id` 串链，把 P1-34 那套复制到执行维度）
- ~~**P1-39**~~ ✅ 让人拿得到 ID：执行/用例编号在界面上可见可复制 + 一键跳日志（#292 已合）
- ~~**P1-43**~~ ✅ 日志翻页：看得到 200 行 / 20000 行扫描窗口以外的历史（2026-08-07 完成）
- ~~**P1-44**~~ ✅ 日志排序方向 + traceback 续行归组（PR #303）
- ~~**P1-42**~~ ✅ `app.audit` 汇总行进 `execution_id` 链；纯 ASGI + WebSocket `request_id`（PR #303）
- ~~**P1-40**~~ ✅ 日志按 `execution_id` 扁平分文件 + 空闲 INFO 基线 + 重复突发抑制（PR #303）
- **P1-41** 修 UXM 排错误队列停不下来的循环（7.6 秒 20 万行 / 一次 24 GB 的根因；**动手前必查 NotebookLM**）
- **P1-47A** ✅ SCPI 往返配对/取消超时/脱敏/30天留存上限；**P1-47B/C**：B=UXM/F64/转台接受与生效；C=TestCase持久化+GUI/报告
- ~~**P1-37**~~ ✅ 五类现场 mock 产真实命令格式并记 `scpi.log`；回复带 per-driver `simulated=true`，正式证据门拒绝模拟来源（PR #303）
- ~~**P1-38**~~ ✅ 活动告警卫生：确认 P3-15 的 SQLite override 已切断测试污染源，以 G20 常驻门锁住；新增精确 dry-run 清理工具，并把大面板收成 summary badge（PR #321；生产告警生产者后由 P3-19 最后一片补齐）

> **⭐ 2026-08-05 用户定方向：「今后 log 是我们主要的调试手段，让它尽快
> 完整 / 正确 / 高效的就位。」** —— 这句话是 P1-30 / P1-34 / P1-35 / P1-36 /
> P1-37 这条线**排在其它本地项前面**的依据，不是一次性偏好。按三个字对号：
> **完整** = 该有的都有（P1-37 补上 mock 下恒空的整个 SCPI 层；P1-36 补执行身份）；
> **正确** = 有的都是真的（P1-37 回读侧标 `simulated`；P1-38 隔离并精确清理 674 条测试告警，不把测试污染当当前告警状态展示）；
> **高效** = 找得到（P1-35 去噪 90.1%；P1-34 按请求/时间定位）。
> 后续再有日志相关发现，默认按此线插队，不必每次重新论证优先级。

- ~~**P1-45**~~ ✅ 现场验证项 → 载体序列 / 正式 TestCase 映射（表逐行核对 + 修 stale；docs-only）
- **P1-46** 补现场载体与判定缺口：ON 态同值写剧本 + `uxm_scpi_compatibility` 对齐 mandatory；inherit 层数因无生效观测手段继续留 Discovered（**动手前必查手册**）
- ~~**P1-27**~~ ✅ P1-8 校准门拒 mock cert（provenance + real 模式 strict 拒；直接 MEASURE 同样前置拦截）
- **P1-28** 「当前暗室」双真值源收口（active chamber vs active lab 绑定暗室）
- ~~**P2-22**~~ ✅ F64 disconnect 冷缓存判 GOS 换真值源（F64R-1 / #225 已交付；本轮 NotebookLM 复核厂商依据后纠正 roadmap 滞后状态）
- ~~**P2-23**~~ ✅ 会话资产 is_active 预检 + MEASURE resolver 同病收口
- ~~**P2-24**~~ ✅ 测试用例契约补 lab_profile_id（契约四步 + GUI 创建/编辑绑定）
- ~~**P1-48**~~ ✅ 日志/报告分不出哪台仪表是真的 —— P1-37 的标记只到 `scpi.log`，app.log / 报告 / VRT 三个消费端一个没接上（2026-08-10 五片全合）
- ~~**P1-29**~~ ✅ `/dashboard/alerts/summary` 被 `/alerts/{alert_id}` 遮蔽 → 驾驶舱告警计数条恒坏（一行声明顺序 + G19 遮蔽门，PR #320）
- **P3-18** 门/测试精化批（G11 三覆盖面 / p08 零残留站点 / PDF 转义收口 / 诊断序列串行化 / **手写类型审计尺子改逐层递归**）
- **P3-19** 日志/告警/留痕卫生批（tail 上限与逻辑组边界 / 正式执行失败告警 / 校准 warnings 持久化+清理警告可见 / UXM 两组 P3 / **mock-only 遗留响应类型与 handler 收口** / **端口清理改项目身份 allowlist**）

**2026-08-01 拍板的本地队列 10/10 全部收口**（P1-22 ✅ #256 / P1-23 ✅ #257 / P2-19 ✅ #258 / P2-20 ✅ #259 / P1-24 ✅ #260 / P2-21 ✅ #261 / P3-14 ✅ #262 / P3-15 ✅ #263 / P3-16 ✅ #264 / P3-17 ✅ done 本 PR）。**这是 2026-08-01 的历史快照，不表示当前队列为空；当前执行片只看本节顶部 Current Focus。** 原顺序备查 **P1-22 → P1-23 → P2-19 → P2-20 → P1-24 → P2-21 → P3-14 → P3-15 → P3-16 → P3-17**
（逐片 WIP=1；P1-24/P2-21 为 2026-08-01 用户二次拍板从 Discovered 提升，插在 P3 批前）。一句话索引（详情见各 P 区条目）：
- **P1-22** 报告可信化：`overall_pass` 死键 + PDF CJK 字体 + `Test Plan: N/A` 残留（设计稿 [`design/p1-22-report-trustworthy-fix.md`](design/p1-22-report-trustworthy-fix.md)）
- **P1-23** 现场协议补 P0-8 gate（纯文档，行前必办）
- **P2-19** 执行观测一致性：相位计数 token 错配 + 日志面板多选/默认态
- **P2-20** VRT 场景库健壮：`_list_custom_scenarios` 单行坏配置 500 + 死 kwarg 清单
- **P1-24** 写 `propsim_f64_p08_gate` 诊断序列（P0-8a 唯一合法载体，出发前硬门槛；要求①-⑦见 Discovered 原条）
- **P2-21** P1-12 可信化标志渲染可达化（三标志挪 `parameters`，与 P1-22 同构）+ `pdf_certificate.py` CJK 字体
- **P3-14** 契约收尾 + 门 G-A（schema 描述⊇枚举）
- **P3-15** 数据/测试卫生批（`test_feature_gaps` DB 隔离 / 2 flaky / vendor_file 频率漂移 / 队列僵尸 triage）
- **P3-16** 门 G-B：状态列注释 ⊇ 全仓状态字面量
- **P3-17** 门 G-C：文档 (动词,路径,参数,响应键) ⊇ 真实实现

**明确 defer**（拍板记录，防翻旧账）：~~`lab_profile_id` 契约字段~~（2026-08-02 拍板提升
**P2-24** 覆盖此 defer —— 排期与禁令不能并存，以后者拍板为准）/
`created_by` 占位（等 Auth Context）/ UXM 幂等·inherit 层数·InputLevelController（半现场，
等仪器窗口）/ B-2 战略缺口·校准表 chamber 维度（大项另立项）。

---

**历史状态 (2026-06-07)**：本地工作队列已基本清空。本地可启动的 P 项全部收口 ——
P2-13 SIMProfile 三阶段 (#140/#141/#142)、DUTProfile 四阶段 (#134-#137)、P2-10/11/12
本地半、#2001(1) imbalance metric (#143)、P1-6 reconnect 本地测试 (#149)、CAICT-FS 满天星
暗室 (#154) + probe_number 按 chamber 局部化 (#155) + 校准 chamber-scoping foundation (本 PR,
#155 Codex P2 (1) 的基础版)。`#2001(2)(3)` / `#2002` 经评估**保持现状不推进** (见
[`architecture/multi-port-input-level-semantics.md`](architecture/multi-port-input-level-semantics.md) §5)。

**P2-14（B-2 信道注入）本地实现 ✅ 完成 (2026-06-21)** —— 设计 V1.0 (#165) + F1–F7 八 PR 全 merge
(详见下方 P2-14 区 Status)。这是 P0 全现场 blocked 期间挪的本地理论层项；纯本地、不依赖现场。
设计见 [`design/RT-MPDB-CDL-F64-channel-injection-design_V1.0.md`](design/RT-MPDB-CDL-F64-channel-injection-design_V1.0.md)。

**本地实现完成后，又无活跃本地 in-progress 项** (回到 2026-06-07 的"本地队列空"状态)。真 P0 (P0-3/4/5)
仍现场 blocked。

**▶ 2026-06-27 P2-15（自定义 CDL 簇编辑）✅ 完成 (2026-06-28)** —— P0 全现场 blocked + 本地队列空期间挪的本地软件功能项（同 P2-14 逻辑：P0 blocked 期间做本地项不违反 WIP=1）。#170 后端 + #171 前端，Codex 1P1+5P2 全修，S5 浏览器闭环。详见下方 P2-15 区。

**▶ 2026-06-28 启动 P2-16（信道资产多态化）** —— 同上逻辑（P0 现场 blocked 期间本地软件项，不违反 WIP=1）。P2-15 暴露「信道资产四分五裂」（GCM `.smu` / B-1 `.asc` / B-2 `.tap` / RT 动态 各自一套引用+耦合），本项收口为单一 `ChannelAsset` 多态实体 + 独立信道工作台 GUI；起步软件半 S1–S4，零现场依赖。设计 [`design/channel-asset-polymorphism-design_V0.1.md`](design/channel-asset-polymorphism-design_V0.1.md)，详见下方 P2-16 区。

**▶ 2026-06-30 P2-16 软件半 (S1–S4) ✅ 完成** —— S1–S3 后端/微服务 (#173–179) + **S4 独立信道工作台 GUI 四 `source_type` 编辑器 + `channel_asset_id` 消费接通 (#181–185)**，让工作台真正驱动 test 执行（验收①②③④达成，各切片浏览器闭环）。

**▶ 2026-07-01 P2-16 deprecate-legacy ✅ 完成**（用户拍板做的本地切片）—— S4-5 消费接通后暴露的双向 stale-copy 根因（迁移实体两份副本 `custom_cdl_profiles`/`standard_channel_definitions` + `channel_assets` × 两条消费路径），用**消费收敛到 ChannelAsset** 根治：`cdl_profile_id`（#187）/ `scd_id`（#188）消费时若同 id 的 ChannelAsset 存在则读它 → ChannelAsset 成单一真值源，无需双写；旧 CDL/SCD 编辑器加 deprecation 引导到信道工作台（#189，保留功能不硬禁用，存量未迁移档案仍可编辑）。**本地队列又回到空** —— P2-16 余项全是现场半（S5/S6: rt 真实数据 + 多快照轨迹执行 + `.tap` 落地）；真 P0（P0-3/4/5）仍现场 blocked。

**▶ 2026-07-03 CAICT 现场日（P0-5 推进至最后一步 + 控制面全量化）** —— DUT 已测到 -96 dBm RSRP
（F64 直通链路终验通过），正式 attach 注册与 ★四方位吞吐未跑（仪表重启 + EMQuest 多写方干扰消耗窗口）。
当日 12 commit 在分支 `onsite-20260703`：现场热修 ×2（2c6f6b1 measure 频率桥接 / 122eeae 频率网
loose 软化）+ 18 条 F64 场景资产工程真值化 + 四台仪器控制面量化（UXM 延迟矩阵 / 转台 12/12 +
断连 <11s / EMCenter VXI-11 打通 / F64 直通语义）+ EMQuest prm 10/10 破译。权威详录
[`guides/onsite-tasks-20260703.md`](guides/onsite-tasks-20260703.md)（收工总结 + discovered 区）。

**▶ 2026-07-03 晚 用户授权 triage（现场发现 → roadmap）**：修单条目化为 **P1-18/19/20/21**
（下次现场 attach→吞吐的软件必要条件）+ **P2-17/18**（直通编排 / 资产真值自动化）+ P2-4/P2-9
状态更新。**执行序（WIP=1，一次一项）**：① `onsite-20260703` 分支 PR 收口 ✅（#193）→ ② P1-20
✅（#194 转台懒重连）→ ③ P1-19 ✅（#195 UXM 编排，Codex 六轮 3P1+4P2 全修）→ ④ P1-18 ✅
（#196 缺省不写 CENT + smu_project 真值解析）→ ⑤ P1-21 ✅（#197 会话卫生）→ P2-17 ✅
（#199/#201 直通编排诊断）+ P2-9 本地半 ✅（#198 EtslSwitchDriver VXI-11）。

**▶ 2026-07-04 整理队列全收口 + 质量补扫体系** —— 上述 ①-⑤ + P2-17/P2-9 本地半全 merge。
另:Codex 流量 limit 漏扫欠账（#196-198 约 1550 行零 review 进 main）建补扫体系 —— review-only
PR（#199 扫欠账 / #202 dry 循环）+ 每轮 findings 新分支修（R1-R5 共 9 条全修,#200/#203-206）+
**提交前独立 Codex subagent 内审硬门**（严格遵循 `.claude/agents/pre-commit-reviewer.md`，Codex limit
期间 agent 主审）。P0-3/P0-4 现场验证补标收口（32 链路证书 / TRP ±1dB,见各条目）。P2-18 独立
排期。本地队列空 —— 下次现场 = **P0-5 attach 正式注册 → ★四方位吞吐**（15 分钟开跑清单就绪）。

**▶ 2026-07-20 晚 三开关 + 正常测试流程传动轴（用户逐项指示）** —— ① 开关 1/2 (#216,
UXM 配置 dispatch/inherit 知情继承 + F64 直通模式参数化 + EMQuest 基线默认 profile);
② **开关 3 = 测试计划 runner**: 补上「计划 → 真执行」缺环（此前 start 只翻状态步骤永停
pending）— 逐 MIMO_OTA 步骤展开为 5 相位链（复用 commissioning 同套 executors）,
执行快照 TestCase（步骤参数固化不回写原例, 防 stale-copy 污染）, 步骤/计划状态实时推进,
协作式 pause/cancel/resume 续跑, 收尾自动历史行+报告（GUI 零改动: 开始按钮/步骤轮询/
历史 Tab 全是现成消费端）; ③ **仪表使用参数进 TestCase 配置面**（调试灵活应变, 全部
None=现行为）: f64_bypass_mode（直通态测量, Butler 无衰落基线正式入口）/
f64_input_ref_dbm+f64_crest_db（手动定标跳 AUTOSET 闭环+读回反馈）/ f64_output_gain_db /
input_loop_initial_dl_power_dbm（闭环起点参数化, 替 -10 硬编码）。计划路端到端彩排 ×2
PASS（含拨挡）。**"正常测试流程蜕变"的传动轴落地** — 明天现场可用测试管理页建计划→
调参→执行→看报告/日志闭环调试。

**▶ 2026-07-20 出发前准备（次日 2026-07-21 现场）** —— 两 agent 全面核查（现场坑→修复状态
逐行核实 9/11 已修 + 执行链路默认值三新雷）后收口:① **BW40 拍板**（用户,跟 EMQuest n78
基线;资产 UMa_3600M 重登记 BW40 三处同步,其余 17 条留待实测）;② **UXM BW 幂等**
（set_cell_config 预读相同免 OFF→ON 环绕 —— 堵"attach 后每次 run 必掉 DUT"序列雷,mock
测不出）;③ 脚本对齐（BW_MHZ=40 / TX_POWER_DBM=-46 注入堵 schema 0.0 冲基线 / AZIMUTHS
环境变量退化预案 / stale 注释）;④ mock 彩排端到端 PASS + 本地 DB 资产真值验证。执行计划
[`guides/onsite-plan-20260721.md`](guides/onsite-plan-20260721.md)（15 分钟开跑序列 + 风险
预案 + 机动项含 **★获取 F64 手册**——根因定性: 手头只有 FS16 手册,全部命令形式照 FS16 写,
CENT/INP:LEV:AMP 回读盲区系手册源错配）。遗留知情项: P1-8 校准 provenance 未修（mock cert
real 模式假过,吞吐 smoke 不信绝对值可接受）。

**▶ 2026-07-27 ~ 08-01 ARCH-1 测试管理拆平（S1–S6 全部 ✅，整案收官）** —— 2026-07-21 现场
拍板的「砍掉计划 + 队列，只留 TestCase」落地。**正式测试的层级从四层拍成两层**：
TestCase（自带 `configuration`，单一真值源）→ TestExecution（每次执行一行）。
**11 个 PR merged**（7 个切片 + 2 篇设计稿 + 2 条迟到修复），
**净删约 1.1 万行**（`git diff --shortstat 124d7e5^ f6bec91` = 123 files / +7113 / −18155）：

| 片 | PR / commit | 内容 |
|---|---|---|
| **S1** ✅ | #237 `124d7e5` | 用例直接执行正门 — case-runner + 双向单飞 + 协作取消 + GUI 按钮 |
| **S2** ✅ | #238 `3f66474`；迟到修复 #239 `31bf648`、#240 `806b2b9` | 执行历史与报告换源到 `test_executions` 本表 |
| **S3a** ✅ | #242 `c4502dd` | HAL reload 闸门换源 —— 堵上 S1 以来的生产空窗（判据只查 TestPlan，跑着用例点重载会静默拆驱动） |
| **S4** ✅ | 设计 #243 `a5543a4`、#245 `e55fa28`；**S4a** #244 `211bec3`、**S4b** #246 `0ff692e`、**S4c** #247 `754e7a9` | 拆除计划链：36 路由 / 6 Service / 计划 runner / **三个 GUI Tab**（Plans / Steps / Queue，6 Tab → 3 Tab）/ mock 层 |
| **S5** ✅ | #248 `f6bec91` | 封存与文档：G7/G8 两道会红的门 + 4 篇归档 + 27 文件换源 + 两处真值源修正 |
| **S6** ✅ | 2026-08-01 总验通过 | 浏览器闭环总验：建用例 → 配参数 → 执行 → 看历史 → 出报告。**五步全部在 GUI 真实走通**（用例「S6-验收-五步闭环」：新建入口建壳 → MHz 口径输 3549.99/带宽 40/绑 vendor_file 资产（DB 核实精确落库）→ 执行 5 相位全 success → 历史行「已完成」→ 报告 201/generate 200/PDF 落盘）。**报告腿抓出 2 个内容缺陷**（机制通、产物有伤，记 Discovered 区不挡收口）：① 执行报告 Pass Rate 显示 0.0%（自动报告路径读不存在的 `overall_pass` 键恒 0；且"相位机械成功"与"KPI 通过"是两层，详见 Discovered 条）② PDF 中文全豆腐块（生成器缺 CJK 字体）。顺带：历史表相位计数对所有行恒 0（后端 token 错配，Discovered 已定案）。 |

> ⚠️ **S3 只完成了 S3a 这一半**：另两半分别是 dashboard 统计换源（随 S4b 做掉）与
> 用例级 preflight（**随计划链删除并转独立立项**，见本文 P1-1 条目下的 ARCH-1 注）。
>
> ~~⚠️ S6 有前置缺口~~ **前置已解除（2026-07-31，#250 GUI 新建入口）**：当时的缺口是
> "可直接执行的 MIMO_OTA 用例无法从 GUI 新建"（新建按钮被可选 prop 守着、全仓无人传，
> 入口随 S4a 删 StepsTab 一并消失），拍板走了「补入口」路 ——
> 设计稿 [`design/gui-create-test-case-entry.md`](design/gui-create-test-case-entry.md)。
> S6 总验（2026-08-01）即用该入口从零建例走完五步。

设计与拆除推理：[`design/arch-1-testcase-first-simplification.md`](design/arch-1-testcase-first-simplification.md)（总纲）/
[`design/arch-1-s2-execution-history-resource.md`](design/arch-1-s2-execution-history-resource.md) /
[`design/arch-1-s4-demolition.md`](design/arch-1-s4-demolition.md) /
[`design/arch-1-s4b-backend-demolition.md`](design/arch-1-s4b-backend-demolition.md) /
[`design/arch-1-s5-archival-and-docs.md`](design/arch-1-s5-archival-and-docs.md)。
归档的旧文档在 [`archive/`](archive/)（计划链架构 / TestPlan 状态机 / QueueTab 同步 / 场景→计划步骤继承）。

**五张表原地封存**（`TestPlan` / `TestStep` / `TestQueue` / `TestPlanExecution` /
`TestSequence`）—— **无业务写入方**（`TestPlan` / `TestStep` 仅启动时被
`reset_orphaned_plan_chain_rows` 复位成终态，其余三张无任何写入方），各带封存 banner。
**新代码不要引用它们。**

⬜ **批量执行 = 后续增量，目前零实现**（总纲 §4 明确划走）。原计划链的"执行队列"随 S4b
删除，队列重排（`Master-Progress-Tracker.md` 的待实现项）随之作废。要做批量时按
「多个 TestCase 排队执行」重新设计，**不要复活 `TestQueue` 表**。

> **WIP=1 说明**：ARCH-1 是 2026-07-21 现场后用户拍板的架构简化，跑在 P0 现场 blocked
> 期间（同 P2-14/P2-15/P2-16 的逻辑）。
>
> ⚠️ **P0 现状别在这儿抄一份** —— 唯一真值源是本文这两处（**按标题找，别记行号**）：
> 「📋 可规划工作 audit」分桶表的 **`ON-SITE-BLOCKED` 行**，以及
> 「🚧 Blocked on hardware (on-site queue —— **P0 优先**)」段的表。
> 本条目只说两件确定的事：
> ① P0-3 / P0-4 **已 2026-07-03 现场完成**（见「Blocked on hardware」表里那两条删除线行）；
> ② 下次现场的**主线**是 P0-5（DUT attach → bearer → PDSCH）。
> **"只剩 P0-5"是错的** —— 还有 **P0-8 的现场半**（real F64 上 load→run→改参全 0
> error + 输入口变绿 + DL 不失真，见 `### P0-8` 条目），跟 attach 是同一台 F64、
> 同一段窗口的活。⚠️ 「Blocked on hardware」表**此前漏列 P0-8**，本 PR 一并补上 ——
> 否则"权威表"和 `ON-SITE-BLOCKED` 行会各说各话（Codex #249 抓到）。
> ⚠️ 2026-06-21 原记录曾写“切回依赖链 P0-4 → P0-3 → P0-5”，那是 P0-3/4
> 完成前的历史快照；P1-45 已把现行规则换成 Blocked 表指针，**不要恢复该旧链**。


P2-14 的**现场验证半**(V1.0 §9：.tap schema / gaussian 谱 / f_upd_max / RT→MPC 接入)
已进 on-site 队列。**原开发的现场验证基线已打 tag** `onsite-verification-baseline-2026-06-21`（留在 main）。
**下次现场窗口按下方「🚧 Blocked on hardware」表排程**；P1-47C 已完成，现场优先执行
P0-5 正式 TestCase 复验，P0-3 / P0-4 已完成，不要求重跑
（执行协议见 [`guides/on-site-debug-protocol.md`](guides/on-site-debug-protocol.md)）。
现场只调硬件、不写 driver 代码；P2-14 现场验证可在 P0 链路间隙穿插。

> **完整项目历程** (第一次现场 → 现在的全程 + 5 条主线) 见
> [`project-retrospective.md`](project-retrospective.md)；**现场经验文档归类**见
> [`field-experience.md`](field-experience.md)。Current Focus 不再堆叠历史快照 (已迁出至
> retrospective，git 保留全量审计轨迹)。

### 📋 可规划工作 audit (除现场工作外还能规划什么 — 2026-06-06)

按"能否本地、现在做"分桶：

| 桶 | 内容 |
|----|------|
| **LOCAL-OPEN (roadmap 内)** | P1-63，WIP=1；P1-64 已占位且只在 P1-63 合并后启动。P2-32 位于功能启用池，P3-20/P3-21 位于非阻塞维护池，均不得自动启动。现场物理单位/方向/偏置/型号实证仍保持 Hardware Blocked。完整编号、范围与状态只看顶部 Current Focus 表。 |
| **ON-SITE-BLOCKED** | P0-5 正式复验（物理 attach + 转台四方向已完成；P1-47C 本地机制已具备，但转台身份与坐标偏置仍须补证并现场跑正式 TestCase）+ P1-2 + P1-4 + P2-4，以及 P0-8 / P1-5 / P1-17 / **P1-33** / P2-9 / P2-10 / P2-12 / P2-13 的现场半 (详见下方「Blocked on hardware」) |
| **HOLD** | P1-6 现场半 (真 idle-close 复现验证；本地测试覆盖已补 #149) |
| **已决策不做 / 保持现状** | `#2000` (依赖 #2001(2) → 连带搁置) / `#2001(2)(3)` / `#2002` |
| **off-roadmap 候选 (需先 triage，非积压)** | GUI 测试框架引入 (与 `feedback_browser_test_frontend_work` 对齐，ROI 最高) / HTTP distributed pytest 缺口 / 后端告警规则引擎 / CLAUDE.md 列的 Queue 重排序·Auth Context·报告对比 |

> ⚠️ off-roadmap 候选是"可做"不是"应做"：多为显式 deferred、无 demonstrated problem。**不因
> "本地队列空了"就拉进来**；按价值由用户排 (per memory `feedback_dont_manufacture_decisions_no_problem`)。

- **WIP limit: 1.** 同一时间只允许一个 Current Focus 项 in-progress。
- 非 Current Focus 且非琐碎 (<30min) 的发现先进入 Discovered 待评估池，不 inline 做；只有 triage 明确判为延后，才进入正式 backlog。

Last review: 2026-06-07 (校准 chamber-scoping foundation; #155 Codex P2 (1) 基础版收口)
Baseline commit: see [announcement](announcements/2026-05-14-roadmap-baseline.md)

---

## 🚧 Blocked on hardware (on-site queue —— **P0 优先**)

> ⚠️ **「正式载体」这一列必须填得出**（2026-08-06 用户定，正式条目见 `### P1-45`）——
> **填不出 = 不能带到现场临时补**。它继续留在原有 Discovered / Blocked / HOLD 分区，
> 只有经 triage 批准的两项 P1-46 交付物才能并入 P1-46，不能借映射审计自动扩 scope。
> CLAUDE.md 早写了「每记一条
> 『这个得现场验』的发现或 backlog，同时问它落在哪个序列里」，但**从来没人做过这个映射**；
> 本列就是让它跑不掉。诊断载体只能是 `api-service/app/diagnostics/sequences/` 下
> checked-in 的序列；正式测试载体只能是 MIMO_OTA TestCase，**不是临时脚本**
> （理由见 CLAUDE.md「仪表驱动调试走诊断序列」一节）。
>
> **注册证据（P1-45 已逐层核对）**：诊断序列由
> [`diagnostics/loader.py`](../api-service/app/diagnostics/loader.py) 按文件名发现，经
> [`GET /api/v1/diagnostic-sequences`](../api-service/app/api/diagnostic_sequence.py) 列表端点与
> `POST /api/v1/diagnostic-sequences/{key}/run` 执行端点；GUI
> [`apiClient`](../gui/src/api/client.ts) 以 `/api/v1` 为 `baseURL`，由
> [`SequenceRunnerPanel`](../gui/src/features/Diagnostics/SequenceRunnerPanel.tsx) 发起列表/执行请求。因此下表写出的
> 序列 key 都确实能在「调试维护 → 调试序列」选择并执行。正式 MIMO_OTA TestCase 则由
> [`TestManagement`](../gui/src/features/TestManagement/TestManagement.tsx) 打开执行入口，经
> [`executeTestCase`](../gui/src/api/testPlanService.ts) 调用
> [`test_case_runner`](../api-service/app/services/test_case_runner.py)；该 runner 当前明确只接受
> `test_type='MIMO_OTA'`。下表凡写“正式 TestCase”均指这条已注册路径，不把普通页面、旧计划链
> 或手工操作冒充正式载体。

| ID | Item | Blocker | 正式载体（P1-45 核对结论） |
|----|------|---------|---------|
| ~~P0-3~~ | ~~Path-loss calibration loop closure + cal cert~~ | ✅ 2026-07-03 现场完成 (余复测 ±0.5dB → P1-4) | — 已完成 |
| ~~P0-4~~ | ~~SignalAnalyzer in HAL for reference TRP~~ | ✅ 2026-07-03 现场完成 | — 已完成 |
| P0-5 | DUT attach → bearer → PDSCH on UXM 5G NR | 2026-07-21 物理 attach + 转台四方向已跑通；P1-47C 已完成本地同次执行证据机制。当前阻塞为：Aerotech 实时型号/固件依据、可信坐标偏置/标定状态，以及 on-site real DUT 的正式 TestCase 复验 | ✅ 诊断：[`baseStation_attach_check`](../api-service/app/diagnostics/sequences/baseStation_attach_check.py)；正式关闭：MIMO_OTA TestCase。只有受支持环境下同一 execution 的 mandatory E0–E4 全部成立才可关闭；`uxm_config_mode=inherit`、ASC/B2 模型加载和未标定转台路径会按设计保持 unknown，**现场已观察事实不等于正式通过** |
| P0-8 **现场半** | F64 driver 现场修复落地 —— real F64 上 load→run→改参全 0 error + 输入口变绿 + DL 不失真 | on-site real F64 (本地半已 Done, 见 `### P0-8`；跟 P0-5 attach 同一段窗口) | ✅ P0-8a：[`propsim_f64_p08_gate`](../api-service/app/diagnostics/sequences/propsim_f64_p08_gate.py)；P0-8b（DL 不失真）：同一条 MIMO_OTA TestCase |
| P1-2 | F64 license probe SCPI 现场验证 | ⚠️ **2026-08-07 拿到部分答案** | **实测**：连接流程每次都会发 `SYSTem:CALibration:USER:LIST?`，该机回 **"ATE command not supported"**（-100 族），且这条 -100 会留在错误队列里跨会话带走。所以「校准侧没有这条命令」这半个前提**不成立** —— 命令发了，是**本机不支持**。剩余未答：按 license presence/absence 判定的那半。⚠ 条目原文写「没有事项要求的 `SYSTem:CALibration:USER:LIST?`」，与实测矛盾，已按实测改写。保留 Blocked（判定逻辑未做）；不并入 P1-46 |
| P1-4 | first-call repeatability test | on-site 全链路 | ⚠️ **部分载体**：MIMO_OTA TestCase 可重复执行；但现有 [`ReportComparison`](../api-service/app/models/report.py) 契约仍比较已封存的 `plan_id`，不是 TestExecution 级对比，不能宣称“报告对比闭环”。保留 Blocked，缺口不并入 P1-46 |
| P1-5 **现场半** | CAL-04 phase calibration | on-site 真校准链路 | ⚠️ **正式校准流程部分载体**：正式入口是 [`POST /api/v1/calibration/probe/phase/start`](../api-service/app/api/probe_calibration.py)；当前 endpoint body 会生成 `job_id` 并直接落库相位校准行，但这些行仍由 mock 数据生成，尚未替换为 CE→SA 实测循环。保留 Blocked，不判完成、不并入 P1-46 |
| P1-17 **现场半** | UXM fresh-start 配置落地 | on-site real UXM | ⚠️ **部分载体**：[`uxm_config_truth_probe`](../api-service/app/diagnostics/sequences/uxm_config_truth_probe.py) 只在已 ON 小区扰动/恢复 ARFCN；不触发 fresh-start/HAL reload、`default_state_file` recall、默认 profile/state 自动应用、全配置/MIMO 对齐或 `.state` 盘点。保留 Blocked；不并入 P1-46 |
| P2-4 | NAT/firewall idle-drop 假设验证 | on-site 现场网络 | ❌ **无载体**：C 类长连接放置后观察。保留 Blocked，待独立 triage；不并入 P1-46 |
| P2-9 **现场半** | EMCenter switch bring-up | on-site EMCenter | ❌ **无载体**：[`rf_switch.py`](../api-service/app/hal/rf_switch.py) 有驱动不等于有 GUI 诊断载体，当前 12 个已注册序列里没有 EMCenter。保留 Blocked；不并入 P1-46 |
| P2-10 **现场半** | F64 工程精细化（配置资产 / 外部输出 / 内部 cal） | on-site real F64 | ⚠️ **部分载体**：[`propsim_f64_health`](../api-service/app/diagnostics/sequences/propsim_f64_health.py) / [`propsim_f64_state_machine`](../api-service/app/diagnostics/sequences/propsim_f64_state_machine.py) 只覆盖公共能力与状态语义，配置资产/外部输出/内部 cal 仍须在 P2-10 内逐项拆；不并入 P1-46 |
| P2-12 **现场半** | 标准信道文件定义 | on-site real F64 | ❌ **无事项级载体**：F64 公共序列只能验健康/状态，不能证明标准信道文件定义端到端正确。保留 P2-12，跟 P2-10 同批拆；不并入 P1-46 |
| P2-13 **现场半** | SIMProfile + SIM↔UXM 一致性 | on-site 真 SIM | ⚠️ **正式 TestCase 半覆盖**：[`MIMOOTAConfiguration.sim_profile_id`](../api-service/app/schemas/mimo_ota/config.py) 已由 [`precheck`](../api-service/app/services/mimo_ota/executors/precheck.py) 核对 SIMProfile；但 UXM 实测 IMSI 当前多数仍回退 attach 手填值，不能证明真卡身份闭环。保留 Blocked；不并入 P1-46 |
| **NEW-1** 现场半 | **F64 各输出口的电平合法窗口** —— `OUTP:LEV:AMP:LIM? <out>` 逐口读上下限 | on-site real F64。⚠ 2026-08-07 实测：口 1 = `-166.60000,-51.6100`，而我们发的 `-50.00` 超上限 1.61 dB 被 `-200 Parameter exceeds set limits` 拒 → **当轮 measure 当场 FAILED**。其余 31 口未知；限值由什么决定（是否随已加载模型 / `OUTP:LOSS` 变）**手册未说明** | ❌ **待建**：现有 [`propsim_f64_health`](../api-service/app/diagnostics/sequences/propsim_f64_health.py) 只查 ch1，无 per-port。出发前须扩它或新写只读普查序列 |
| **NEW-2** 现场半 | **关掉 ATE socket 后 F64 前面板 Local 是否真的可用** | on-site real F64 + 人在面板前。⚠ 这是整套租约 / `release_to_local_control` 机制的**地基假设**，而手册原文（PROPSIM User Reference §20.1）说的是：发第一条 ATE 命令后自动进 remote，**回 local 要操作员在 GUI 右上角点 Local Mode 按钮** —— 方向与实现前提相反。代码里 `control_mode` 已改成如实措辞 `ate_socket_released`（不再替仪器宣布「它在 Local」），但**真相要现场 5 分钟测出来** | ❌ **无载体**：不是 SCPI 能问的，属「发一条命令 + 人看面板」的观察项。可挂在任一 F64 序列末尾做人工确认步 |
| **NEW-3** 现场半 | **`OffsetToCarrier` 要不要一并下发 102** | on-site real UXM。⚠ `nr_band_baselines.json:11-20` 有 `offset_to_carrier: 102` 但**全仓零写方**；而 `1bb0acc` **第一次**在 IRAT 上真正打开了 PointA 下发（改动前 `CELL_DL_POINTA=None`，从不发）。PointA 632946 只有配 OffsetToCarrier=102 才与 ARFCN 636666 / BW40 自洽，仪器上为 0 或残留值时载波栅格错位 —— 是 2026-08-07 后两轮 **attach 60s 超时**的候选解释之一（未证实） | ❌ **待建**：属「下发 + 回读 + 看 attach」的剧本式序列 |
| **NEW-4 / P1-56 现场半** | **转台收到 `MOVEABS X 0` 为什么不动** | on-site real Aerotech。⚠ 2026-08-07 实测：14:23–17:44 共 **6 个 execution / 15 次** `MOVEABS X 0.0000`，编码器 `PFBK(X)` 一个计数都没动，而 `move_to` 仍返回成功并打印「Arrived: Az=90.00°」。**最危险的一条**：功率问题一旦修好走进方位循环，四个方位测的是同一个物理位置，产出一份看不出破绽的假数据，现有的门一个都不会红。⚠ 仓内厂商文档对象是 **Ensemble**，而驱动文件头写 **A3200**，型号不符待确认 | ✅ **本地载体已由 P1-56 / PR #350 收口**：[`aerotech_positioner_motion_truth`](../api-service/app/diagnostics/sequences/aerotech_positioner_motion_truth.py) 只在站点显式确认 degree user-units 与安全坐标范围后，使用仓内指南有出处的 `MOVEABS ... XF...` 做小步前进/返回，每 200ms 连采 `VFBK + PFBK` 最多 10s 并落 raw；ABORT 后只以全部实际轴有限 VFBK 精确为零保守确认停止。[补充 Codex 结论](https://github.com/swang430/Meta-3D/pull/350#issuecomment-5327846839)明确 reviewed commit `0f981339c5`（包含尾修 `bd71879`）且无重大问题。真实单位、方向、偏置、型号与机械目视动作仍须现场，继续 Hardware Blocked |
| P1-6 **（HOLD 行）** | FS16 / UXM / ENA silent-reconnect 集成测试 | 需真 idle-close 证据 | ❌ **无 C 类载体**：[`propsim_fs16_health`](../api-service/app/diagnostics/sequences/propsim_fs16_health.py) / [`uxm_scpi_compatibility`](../api-service/app/diagnostics/sequences/uxm_scpi_compatibility.py) / [`vna_ena_health`](../api-service/app/diagnostics/sequences/vna_ena_health.py) 都不会制造 idle-close。继续 HOLD；不并入 P1-46 |
| ~~P1-33 **现场半**~~ ✅ **2026-08-07 现场完成** | ~~验证按手册重写的 MAC 配置命令在真机上被接受~~ —— **实测：14 条全部被仪器接受、0 条被拒**（execution `ea016f0f`，17:38:18 与 17:41:29 两轮一致；逐组 `SYST:ERR?` 回读为证）。唯一的 `-113` 来自一条**只读探测** `UL:IMCS:FIXed?`，不在那 14 条之内 —— 那正是本项要问的「IRAT 认不认」的实测答案：DL 侧 `RRESource:APOLicy?` 回读 `FIX`（认），UL 侧那条不认。⚠ 由此产生的**新**现场待验见下方新增行。原描述（本地半可先做，见 `### P1-33`） | on-site real UXM。⚠️ **不再 gate 在 P1-31 上**（Codex #276 P2 抓出错误依赖）：P1-31 只跑那 9 项 KPI 对账、且限定「手册有依据 + 驱动已在用」的命令，**产不出 MAC 配置命令的形式**；而 2026-08-03 查手册发现**这 8 组命令 `BSE:` 形式手册里全都有** —— 卡点不是「不知道命令」，是「没在真机上验过」 | ⚠️ **半覆盖** [`uxm_scpi_compatibility`](../api-service/app/diagnostics/sequences/uxm_scpi_compatibility.py)：命令被枚举，但判定集错（`TDD_PATTERN` 恒 `None` 仍在 critical；`MAC_CFG_MANDATORY` 多数未进 critical）。这是表内唯一并入 P1-46 的缺口，见其第 2 件交付物 |

**P1-45 triage 结论**：13 条未完成/现场半/HOLD 行中，2 条已有合规载体，7 条只有
部分载体，4 条没有合规载体，即已有 **9 条可复跑承载路径**；这只是入口/路径存在，
不等于现场事项完成。**P1-46 只接**已批准的
`uxm_idempotent_write_probe` 与 P1-33 判定集对齐；其余缺口保持上表注明的
Blocked / HOLD / 原 P 项，不写临时脚本替代，也不因本轮审计自动升级为 backlog。

⚠️ 表里 **P1-33 现场半不是 P0**，不抢 P0-5 / P0-8 的窗口，排在 P0 之后。
**不依赖 P1-31** —— 命令形式手册里有，本地半已完成；
现场只验「真机接不接受」。

These are still the highest-priority items overall. P0-5 的物理链已跑通，
P1-47C 已补齐可判定的自动化证据机制，但未补写现场事实；下一次现场窗口必须先补齐
转台身份/坐标偏置并立即切回 P0-5 正式复验。现场窗口到来前，本地序列以顶部
Current Focus 为准。

> ⚠️ **P0-5 是主线，但不是当天唯一的 P0 活** —— P0-8 的现场半（见上表对应行）
> 需要同一台 real F64，排窗口时一起算。两者都在「📋 可规划工作 audit」的
> `ON-SITE-BLOCKED` 行里；本表此前漏列 P0-8，2026-07-30 补上。
>
> ✅ **协议已覆盖 P0-8（P1-23，2026-08-01）**：Phase 1.5 = P0-8a gate
> （load→run→改参 + 输入口电平，载体 `propsim_f64_p08_gate` 序列 —— **✅ 已写好并
> mock 跑通**，见 `### P1-24`（Done）与协议 §2 的勾选项。本行原写「序列本身待写」，
> 2026-08-06 发现是 stale），Phase 4 gate 清单含 P0-8b（DL 非 0% ACK）。
> 此前"协议不覆盖 P0-8、需手动排入"的告警随 P1-23 作废。

> **下次现场执行按 [`docs/guides/on-site-debug-protocol.md`](guides/on-site-debug-protocol.md)
> 走**（现场首测调试协议）。当天 P0 队列以上方「Blocked on hardware」表为准
> （协议自 P1-23 起不再硬编码队列），Phase 结构 = 网络 → 握手 → **F64 信道链
> (P0-8a)** → SA → 校准 → DUT attach(P0-5+P0-8b) → 真 first-call，gate 标准 =
> 各 P0 的 acceptance；并固化 CAICT 教训: 出发前硬门槛 + 铁律「现场不写 driver
> 代码」+ timebox 救火 + 收工 review + retro 喂回本 roadmap。

---

## ⚠️ 已合并但未过外审的批次（只增不减，周度回扫）

> **为什么要有这张表**（2026-08-03 用户提出）：审查-修复循环上限 = 2，
> 第二轮 findings 若由上轮修复引入即收口 —— **收口意味着最后那批修复
> 没有外审盖章就合进去了**。这件事我每次都在 commit message 和 PR 评论里
> 如实申报，但**仓库里没有任何一处能让人一眼看出"哪些已合并内容没被审过"**，
> 要查得一条条翻 commit message。下次谁基于这些改动开工，不会知道最后一版
> 没人审过。
>
> **用法**：一行一条，**只增不减**（处置完在「处置」列标结果，不删行）。
> 进[周度短 review](#governance-rules) 的固定检查项：下次动到「未审内容」
> 那几个文件时，**优先给它补一轮外审**，别等到出事。

> ⚠️ **每个 PR 都记一行，不只记有缺口的**（Codex #276 R3）——
> 只记「有缺口」的话，最右那列**做不了趋势**：它的取样条件本身就是「已经出了
> 审查缺口」，clean 的、全覆盖的、以及本 PR 都会被排除，数字升降可能只是
> **哪些 PR 有资格进表**变了。要当质量信号，样本必须是全集。

| 日期 | PR | 外审覆盖 | 未审内容 | 为什么没派 | R1 findings | 处置 |
|---|---|---|---|---|---|---|
| 2026-08-03 | [#271](https://github.com/swang430/Meta-3D/pull/271) | ✅ 全覆盖 | —（R2 后的合并 commit `42a1202` 净变化 = #272 已审过的 15 行文档） | — | 1 | ✅ 无需处置 |
| 2026-08-03 | [#272](https://github.com/swang430/Meta-3D/pull/272) | ✅ 全覆盖 | —（首轮即 clean） | — | 0 | ✅ 无需处置 |
| 2026-08-03 | [#273](https://github.com/swang430/Meta-3D/pull/273) | ✅ 全覆盖 | —（R2 审的 `8d0781f` 就是合并时的 HEAD） | — | 2 | ✅ 无需处置 |
| 2026-08-03 | [#274](https://github.com/swang430/Meta-3D/pull/274) | ⚠️ 有缺口 | `1c5d960` —— 内审 agent 时间预算的 R2 两条修复（全量输出必须绑当前版本 / 脏工作区先还原再跑基线） | 轮次上限=2，R2 findings 由 R1 修复引入 | 1 | ⬜ 未处置 —— 下次动 `.claude/agents/pre-commit-reviewer.md` 或 `CLAUDE.md` ⓪⁺④ 时补审 |
| 2026-08-03 | [#275](https://github.com/swang430/Meta-3D/pull/275) | ⚠️ 有缺口 | `b1dc9df` `dea10ea` —— UXM KPI 的 R2 两条修复（未知口径不写进 `_dbm` 字段 / 两种 blocker 一起报）+ 现场核验 9 项清单 | 同上 | 2 | ⬜ 未处置 —— 下次动 `uxm_base_station.py` KPI 段或 `uxm_scpi_compatibility.py` 时补审 |
| 2026-08-03 | [#276](https://github.com/swang430/Meta-3D/pull/276) | ⚠️ 有缺口 | R3 四条修复（本 commit）—— 用户指示补审后 Codex 仍出 1 P1 + 3 P2，修完未再派第四轮 | 用户已额外授权一轮（R3）；R3 findings 仍主要是同文档内部镜像 | **4** | ⬜ 未处置 —— 下次动本文件 P1-31/32/33 段时补审 |
| 2026-08-04 | [#277](https://github.com/swang430/Meta-3D/pull/277) | ⚠️ 有缺口 | `b985cbc` —— **R4 两条 P2 的修复**（⑦ 接 P3b 的结果 / 「没变小」那格不算通过）及配套的 4 门 3 变异 | 用户拍板走完 **R1–R4** 后 merge，未再派 R5；**内审也已跑满两轮**，内审 R2 六条的修复同样无覆盖。四轮走势 **2 P1 → 3 P2 → 1 P1+1 P2 → 2 P2**（严重度递减；R4 两条已被新增的不变量门 `test_no_green_verdict_branch_hedges_in_its_text` 覆盖）| 2 | ⬜ 未处置 —— 下次动 `uxm_kpi_readback` 时补审 |
| 2026-08-04 | [#278](https://github.com/swang430/Meta-3D/pull/278) | <!--278-coverage-->⚠️ 有缺口 | <!--278-gap-->**回填本行这两格的 commit 自己**（docs 一行）—— R1 `8caaba1` / R2 `889db34` 都过了审，回填 commit 没有 | docs-only 一行登记；R1 两条 P2 均**当下修**（`R1 findings` 列被我塞了四轮合计 / 漏了本 PR 自己）。R2 唯一一条 P2 = 「合并前把这两格填掉」—— 而**回填 commit 自己**要么每次都得再派一轮（无穷递归），要么就此收口。选收口并如实标注：这行说的话在合并那一刻就是真的，此后也一直是真的| 2 | ⬜ 未处置 |
| 2026-08-04 | [#279](https://github.com/swang430/Meta-3D/pull/279) | ✅ 全覆盖 | —（R1 唯一一条 P2 修完后 R2 在 `7f49414` 上 clean，而 `7f49414` 就是合并时的 HEAD）| — | 1 | ✅ 无需处置 |
| 2026-08-04 | [#280](https://github.com/swang430/Meta-3D/pull/280) | ⚠️ 有缺口 | **修 R3 那条 P2 的 commit 自己**（docs 一段）—— R1 `1d3e762` / R2 `7c28ddb` / R3 `a5a6bab` 都过了审，这次修复没有 | 用户授权破例走到 R3（超轮次上限）；R1/R2/R3 三轮各 1 条 P2，**全是同一母题的不同镜像站点**（表漏本 PR → Discovered 源条目 stale → P1-32 条目本体 stale）。R3 后按母题全量扫，确认无第四处 | 1 | ✅ 无需处置 —— ⚠️ 与 [#278](https://github.com/swang430/Meta-3D/pull/278) R1 **同一条**：「每个 PR 都记一行、含本 PR」我一个 PR 之后又漏了 |
| 2026-08-05 | [#281](https://github.com/swang430/Meta-3D/pull/281) | ⚠️ 有缺口 | `a72ea7a` —— **R2 三条 P1 的修复**（TDD 校验改读**实时** SCS / pattern 排布可编码性 `D*S?U*` / CSI-RS 显式端口不被推导覆盖）及配套的门与变异 | 轮次上限=2 已到，交回用户后拍板 merge。两轮走势 **2 P1 → 3 P1**（**没有收敛**）—— 我在交回时明说了「再审一轮大概率还有」，这行如实记着它 | 2 | ⬜ 未处置 —— 下次动 `uxm_base_station.py` 的 MAC 配置段或 `executors/measure.py` 时**优先补审** |
| 2026-08-05 | [#282](https://github.com/swang430/Meta-3D/pull/282) | <!--282-coverage-->✅ 全覆盖 | <!--282-gap-->—（R3 在 `bd43c8d` 上 clean，而 `bd43c8d` 就是合并时的代码 HEAD）**唯一没覆盖的是回填本行这两格的 docs commit 自己** —— 与 [#278](https://github.com/swang430/Meta-3D/pull/278) 同一个无穷递归，按那次的拍板就此收口 | 用户授权破例走到 R3（超轮次上限=2）。三轮走势 **1 P2 → 1 P2 → clean**，且**每轮那条 P2 都是本片自己在治的母题在新代码上复发**（R1 id 太短会静默合并两条链／R2 按钮名叫「只看这一次请求」实际给的是交集）—— 不是外部挑刺，是我自己没收敛。R3 clean 才算真收敛 | 1 | ✅ 无需处置 |
| 2026-08-05 | [#283](https://github.com/swang430/Meta-3D/pull/283) | <!--283-coverage-->✅ 全覆盖 | <!--283-gap-->—（R1 在 `3a4a7b8` 上即 clean，而 `3a4a7b8` 就是合并时的代码 HEAD）。唯一没覆盖的是回填本行的 docs commit 自己 —— 与 [#278](https://github.com/swang430/Meta-3D/pull/278) 同一个无穷递归，按那次拍板收口 | P1-35 本片；按 #278 R1 的教训**开片即建行**。**首轮即 clean** —— 内审 8 条（含 1 条 P1：三道新门全是存在性档、内审造的 5 条变异全绿）在派外审前就修完了，这是本轮最值得记的一次前后对照 | **0** | ✅ 无需处置 |
| 2026-08-05 | [#284](https://github.com/swang430/Meta-3D/pull/284) | ✅ 全覆盖 | —（R2 在 `3c9d051` 上 clean，而 `3c9d051` 就是合并时的代码 HEAD）| 琐碎仓库卫生（.gitignore）。R1 唯一一条 P2 **抓得准**：不带锚点的 `data/` 匹配任何叫 data 的目录，遮住 **23 个已跟踪源文件** —— 我踩了这个 PR 自己在警告的那个坑（全局规则误伤源码）。该失效**静默**（测试绿、构建过、git status 干净，只有新加文件时才暴露），除外审外无任何东西能抓到 → 已落成门 **G9** 并过变异 | 1 | ✅ 无需处置 |
| 2026-08-05 | [#287](https://github.com/swang430/Meta-3D/pull/287) | <!--287-coverage-->✅ 全覆盖 | <!--287-gap-->—（R1 在 `b3a007c` 上即 clean，而 `b3a007c` 就是合并时的**规则正文** HEAD）。唯一没覆盖的是回填本行的 docs commit 自己 —— 与 [#278](https://github.com/swang430/Meta-3D/pull/278) 同一个无穷递归，按那次拍板收口 | 流程改动（内审提速三条规则），无产品代码。**首轮即 clean** | **0** | ✅ 无需处置 |
| 2026-08-05 | [#289](https://github.com/swang430/Meta-3D/pull/289) | <!--289-coverage-->✅ 全覆盖 | <!--289-gap-->—（R1 在 `27ac85d` 上即 clean，而 `27ac85d` 就是合并时的 HEAD）。唯一没覆盖的是回填本行的 docs commit 自己 —— #278 拍板的无穷递归 | 从 compose 拆掉 api 服务（用户直接指令）。**首轮即 clean，但这是内审替它挡下来的**：内审出 5 条（2 P2 值得记）——`down -v` 遇遗留容器变 orphan 会**半途而废且退出码 0**（内审实测复现）、以及拆服务时把「calibration_data/certificates 必须挂持久卷」的唯一记录一起拆没了而新文档又叫人 `docker run`（重建即丢数据）。后者是我 **③⁺ 扫漏的一处** —— 我用的三个关键词全命不中 `Dockerfile:33` 那句 `bind-mounted via docker-compose` | **0** | ✅ 无需处置 |
| 2026-08-05 | [#288](https://github.com/swang430/Meta-3D/pull/288) | <!--288-coverage-->⚠️ 有缺口 | <!--288-gap-->**本行本身**——#288 已于 `6c65132` 合并，而它的台账行**当时没建成**：我那条 `python3 - <<'PY'` heredoc 撞了 `SyntaxError: Non-UTF-8 code`，commit 空转，我**没看输出就往下走**（违反 ⓪⑥），于是 PR 带着「无行」合了。本行由 [#290](https://github.com/swang430/Meta-3D/pull/290) 补建 | docs-only 登记（日志爆量定位数据）。**R1 那条 P2 抓得对**：条目写着「本条比 P1-37 更该先做」，而队列里**没有它的位置**——排序指令指向一个不存在的 slot，等于没说。处置=在 #290 里升格 **P1-41** 并入队。⚠️ 另：同一个 commit `bade48b` 上 Codex 先出这条 P2、我再跑一次回 **clean** ——**与 [#285](https://github.com/swang430/Meta-3D/pull/285) 完全同型的第二次实例**，「clean 有随机性」现在有两次独立证据 | 1 | ✅ 已处置（→ #290 的 P1-41）|
| 2026-08-06 | [#290](https://github.com/swang430/Meta-3D/pull/290) | <!--290-coverage-->✅ 全覆盖 | <!--290-gap-->—（R1 在 `86ae54a` 上出 1 条 P2，已在本 PR 内修完；修复 commit 未再派 R2 —— 轮次纪律：R1 findings 修完即收口，尾部修复无外审照旧如实申报） | P1-39/P1-40 立项 + 队列插队（docs-only）。**R1 那条 P2 是本轮最值钱的一条**：我把每执行日志写成 `logs/executions/<id>.log`，而 `_safe_filename()` 的 `^[\w\-\.]+$` 把 `/` 直接判 400、`/system-logs/files` 又只扫顶层跳目录 ——**照这个设计做出来，每执行文件列不出/tail 不了/导不出/下不了**，承诺的工作流当场是坏的。这是**立项文字里的设计缺陷**，代码没写就被拦下，正是立项该过外审的理由。修法走「去掉」（扁平 `exec-<uuid>.log`，零后端改动）不走「加机制」（递归列目录+路径安全） | 1 | ✅ 无需处置 |
| 2026-08-06 | [#292](https://github.com/swang430/Meta-3D/pull/292) | <!--292-coverage-->✅ 全覆盖 | <!--292-gap-->—（末轮在 `8a70b50` 上 **clean**，而 `8a70b50` 就是合并时的 HEAD）。唯一没覆盖的是回填本行的 docs commit 自己 | P1-39。**走了 5 轮，前 4 轮每轮都是「修完引入新的」**：R1 2 P2 → R2 2 P2 → R3 2 P2 → 拆分后 1 P2 → **末轮 clean**。⚠️ **拆掉排序之后才收敛** —— 三轮 6 条 P2 的分布是「排序 5 / 跳转 1 / ID 展示 **0**」，用户拍板把排序摘成 P1-44，摘完一轮就干净了。**这是 `feedback_review_loop_scope_discipline` ② 那条（上限触发条件不适用时看 finding 的文件分布，不看轮数）的第二次实证**，第一次是 S5。⚠️ 另记两次流程漏洞：① 我说「270 秒后去查」但**没有计时器**，一轮结束就停了，连着两次要用户来问，后改用后台任务兜；② `8a70b502` 推完**没发 `@codex review`**（push 不触发），差点带着一个从没审过的竞态修复合进去，是用户问「哪个在 review」才发现 | 2 | ✅ 无需处置 |
| 2026-08-06 | [#291](https://github.com/swang430/Meta-3D/pull/291) | <!--291-coverage-->✅ 全覆盖 | <!--291-gap-->—（R1 在 `5eb623f` 上出 1 条 P2，已在本 PR 内修完；修复 commit 未再派 R2 —— R1 findings 修完即收口，尾部修复无外审如实申报，与 [#290](https://github.com/swang430/Meta-3D/pull/290) 同处置） | P1-42 立项（docs-only），用户从 Discovered 升格并指定优先。**R1 那条 P2 是「核前提」的教科书案例**：它说纯 ASGI 后上一个请求的 `execution_id` 会漏进下一个请求。我没有直接采信也没有直接驳回，做了**两层探针** —— ① 同一个 task 里连调两次 ASGI app：**确实泄漏**（机制成立）；② 真 uvicorn 同一条 keep-alive 连接连发两请求：**不泄漏**（uvicorn 每个请求周期起独立 task）。所以准确定性是「**机制为真，今天的服务器不触发**」，比「对」或「不对」都精确。修法照收（三行，缺了就是静默错误归属），并额外要求那条门**必须在同一 task 里直调 ASGI app** —— 走 TestClient 或 uvicorn 都天然干净，门会**恒绿等于没有** | 1 | ✅ 无需处置 |
| 2026-08-06 | [#295](https://github.com/swang430/Meta-3D/pull/295) | <!--295-coverage-->✅ 全覆盖 | <!--295-gap-->—（R2 在 `36bc478` 上 clean，而 `36bc478` 是 R1 修复 HEAD；唯一未覆盖是回填本行本身，按 [#278](https://github.com/swang430/Meta-3D/pull/278) 无穷递归约定收口） | P1-45 docs-only 映射；R1 在 `c7094ec` 上指出诊断证据持久化承诺过度、P1-5 正式校准载体误判，两条 P2 均已修；R2 在 `36bc478` 上 clean | **2** | ✅ 无需处置 |
| 2026-08-06 | [#296](https://github.com/swang430/Meta-3D/pull/296) | ⚠️ 有缺口 | 尾部提交 `8d464f8`：R2 要求把诊断关键 observations 持久化、不能只留在会截断的 2KB 摘要；修复新增 `DiagnosticRun.result_extra`、迁移与取消审计，**这批修复本身未再外审** | 两轮上限已到，不发 R3；PR 评论已如实申报。走势 R1 1 P2（同步 VISA 阻塞事件循环）→ R2 1 P2（关键现场证据未持久化），两条均已修并过独立内审/全量测试 | **1** | ⬜ 未处置 —— 下次动 `diagnostic_sequence.py`、`DiagnosticRun` 或诊断持久化时优先补审 |
| 2026-08-07 | [#297](https://github.com/swang430/Meta-3D/pull/297) | ✅ 全覆盖 | —（R2 在 `53061f4` 上 clean，而 `53061f4` 是 R1 修复 HEAD；唯一未覆盖是回填本行本身，按 [#278](https://github.com/swang430/Meta-3D/pull/278) 无穷递归约定收口） | P1-41；R1 在 `3e594cc` 上出 1 条 P2，指出“归属未知”被误报为“业务命令被拒”。已补契约门并把不可用判定移到记录 rejection 之前；#296 漏行也随 R1 修复进入 R2。R2 在 `53061f4` 上 clean | **1** | ✅ 无需处置 |
| 2026-08-07 | [#298](https://github.com/swang430/Meta-3D/pull/298) | ⚠️ 有缺口 | R2 后尾部修复（本 commit）：覆盖 `AUTHentication` 从最短 `AUTH` 到全写之间的全部合法 SCPI 缩写；该修复本身未再外审 | 两轮上限已到，不发 R3；走势 R1 1 P1 + 1 P2（分层鉴权末操作数泄漏 / SCPI 复制进长期 `app.log`）→ R2 1 P1（漏识别 `AUTHENT` 等中间缩写），三条均已修并过独立内审与全量测试 | **2** | ⬜ 未处置 —— 下次动 `base.py` 的 SCPI 脱敏器或仪器日志副本时优先补审 |
| 2026-08-07 | [#301](https://github.com/swang430/Meta-3D/pull/301) | ⚠️ 有缺口 | R2 后尾部修复（本 PR 最终 commit）：后台 refetch 保留已验证暗室缓存；activate 成功先用权威响应替换 cache；新建/复制/直接选择均携带发起时 `labProfileId`。这批修复本身未再外审 | 两轮上限已到，不发 R3；走势 R1 **2 P1**（失败校准部分行可被后续提交 / 断绑时 GUI 无法列出替代暗室）→ R2 **2 P2**（后台刷新会丢 OTA 阵列 / 丢探头选择与未保存编辑）。四条外审 finding 均已修；尾部又经内审抓出并修复两个 mutation 时序窗口，最终 CLEAN | **2** | ⬜ 未处置 —— 下次动 `ChamberConfigCard.tsx` 的暗室切换/创建/复制 mutation 时优先补审 |
| 2026-08-07 | [#302](https://github.com/swang430/Meta-3D/pull/302) | ✅ 全覆盖 | —（R1 在 `d696d7a` 上 clean，而 `d696d7a` 是合并代码 HEAD；唯一未覆盖是回填本行的 docs commit，按 [#278](https://github.com/swang430/Meta-3D/pull/278) 无穷递归约定收口） | P1-43 日志历史分页；内审两轮先后拦下 4 P2 + 2 P2，尾修复最终 CLEAN；GitHub Codex R1 “Didn't find any major issues” | **0** | ✅ 无需处置 |
| 2026-08-05 | [#285](https://github.com/swang430/Meta-3D/pull/285) | <!--285-coverage-->✅ 全覆盖 | <!--285-gap-->—（R3 在 `e2ad982` 上出的唯一一条就是「补本行」，除此之外的立项正文三轮全过；`e2ad982` rebase 到 #287 之后内容逐字未变，已用 `git diff` 核过）。唯一没覆盖的是回填本行的 commit 自己 —— #278 拍板的无穷递归 | docs-only 立项。**我把轮次走到了 R3 而没有拿授权** —— 规则是上限 2，例外要用户点头（上次 #282 的 R3 是用户明说「走R3」）。这次 R2 那条不是 R1 修复引入的（是立项正文里独立的错误前提），我就自然而然续了一轮，如实记着。三轮 **1 P2 → 1 P2 → 1 P2**，无一条由上轮修复引入。**R2 那条最值钱**：我写「`hal_mode` 字段已存在、不重复造标记」，而它取自**全局** HAL mode，HAL 明确支持 per-instrument 覆盖 —— 全局 real 下被强制 mock 的仪器会把假回复标成 `hal_mode=real`，正好打穿 P1-37 唯一要防的那件事。另：R1 那个 commit `ba41c26` 上，Codex 先出 1 条 P2，我再发一次 `@codex review` 它在**同一个 commit** 上回了 clean —— 同 commit 两种结论，说明「clean」有随机性，别把单次 clean 当保证 | 1 | ✅ 无需处置 |
| 2026-08-05 | [#286](https://github.com/swang430/Meta-3D/pull/286) | <!--286-coverage-->✅ 全覆盖（代码） | <!--286-gap-->—（R2 审的 `6e58a1b` 就是 R1 修复本身，代码全过；rebase 到 #285/#287 之后 `api-service/` `gui/` `api/` **零字节差异**，已用 `git diff --stat` 核过）。没覆盖的只有回填本行 + 记 backlog 的 docs commit | P1-36 本片。**轮次上限 2 已到，R2 那条 P2 未修、转 backlog** —— 前提我实证过是**真的**（最小 app 探针：同一请求里 endpoint 那行带 `EXEC1234`、`app.audit` 汇总行是 `-`），不修的判据是 ⑦「不改它，P1-36 那个可观察故障还在吗」答**不在了**：R1 修完后执行的开始/过程/结束/取消都在链上，缺的是同一事实的第二份记录且**一跳可达**；三种修法全属「加机制」（最低优先级修法）。两轮 **1 P2 → 1 P2**，都不是上轮修复引入的，且**是同一母题的两个站点**（"执行的痕迹漏在请求侧"）—— R1 补上了 case-runner 那两行，R2 指出 middleware 那行结构上补不了 | 1 | ⬜ 未处置 —— 下次动 `audit_middleware.py` 或再往 `execution_id` 链上加东西时一并评估 |
### 📉 更值得看的信号：第一轮 findings 数

上表最后一列不是装饰。**收口本身不是问题，反复需要收口才是** ——
连着三个 PR 走到「我修完但外审没盖章」这一步，说明的不是审查太严，
而是**第一轮交出去的东西每次都要靠外审来发现自相矛盾**。

2026-08-03 当晚：#272 首轮 clean（0）→ #271 (1) → #273 (2) → #274 (1)
→ #275 (2) → **#276 (4)**。#276 那四条**全是条目内部自己打架**
（写「只读」又列了三条写命令 / 拆出本地半却不排进队列 / 改了表行没改
紧邻的注 / 依赖设反）—— **这些不需要外审也该自己看出来**。

⚠️ 更难看的是 #276 的后续：用户额外授权补审（R3）后，Codex **又出了
1 P1 + 3 P2**，其中 **3 条仍是同一份文档里的镜像**（What 段还写着「只读」
而下面列着三条写命令 / Discovered 清单还留着已删的第 ⑩ 项 / 这张表自己
的取样有偏还宣称能看趋势）。**同一份文档、连审三轮、每轮都还能挖出
自相矛盾** —— 这不是审查太严，是我改一处不扫镜像的老毛病在一份纯文档上
被放大到极致。唯一那条 P1（`DDDSU` 翻六参数信息不够）是真的规划缺口，
不是镜像 —— 也说明**方案里真的有需要外审才看得出的东西**，两类要分开看。

这一列是**可观察的质量信号**，比「我会注意」有用。周度 review 时看趋势：
持续走高 = 第一轮质量在退，该收紧动手前的自查而不是加审查轮次。

---

## Governance rules

These rules exist because at CAICT 2026-05-12/13 a 2-day on-site that was
supposed to deliver a chamber first-call ended up consumed by driver-layer
firefighting (F64 IDN / UXM Test App / Aerotech single-axis / idle-close).
The work was real and necessary, but the trip cost was a first-call we
didn't get. Mechanisms below are designed to prevent that pattern.

1. **WIP = 1 on P0.** Finish (PR merged + acceptance criteria verified)
   before starting the next P0.
2. **Read this file before non-trivial work.** Any agent / contributor
   must confirm which item they're working on. Off-roadmap requires an
   explicit `Out-of-roadmap, reason: ...` field in the PR.
3. **Mid-task discoveries → Discovered intake, not detour.** Append to the
   "Discovered during X" section at the bottom of this file with a
   one-line note + date. It is not backlog and not approved work until triage
   explicitly chooses roadmap / existing item / deferred backlog / blocked / resolved / dropped.
4. **No "顺手优化".** Mess is not a bug. If it doesn't make the current
   P0 easier, it enters Discovered for triage rather than becoming inline cleanup or an automatic P3.
5. **Codex / review fixes that are not on the critical path** get their
   own commit on the next P0 branch, not a separate detour PR — unless
   they block merge.
6. **Periodic review (weekly).** Four questions:
   - Last week's focus was X — what did we actually do?
   - How much did we drift (0% / 30% / 100%)?
   - If we drifted, which of rules 1-5 broke?
   - **扫一遍[「已合并但未过外审的批次」表](#️-已合并但未过外审的批次只增不减周度回扫)**
     （2026-08-03 用户加）：① 本周动过的文件里，有没有落在某行「未审内容」上的？
     有就**先给那批补一轮外审**再动。② 看「R1 findings」列的趋势 ——
     持续走高 = 第一轮质量在退，该收紧动手前的自查，**而不是加审查轮次**。

---

## ✅ Done — do not redo

> **已完成项（D1–D33 done log）详情已迁出** → [`roadmap-archive.md`](roadmap-archive.md)（只读审计存档）。本文件保持聚焦 open / active 工作。已完成项**不要重做**；正文各处 “see DXX” 引用现指向该存档。

---

## 🔴 P0 — Critical path to first-call

Each one is "won't run first-call without it".

### P0-1 — DB auto-bootstrap on startup ✅ Done (PR #17)

> **Repo path note**: 本项 (以及后续 P0 中提到的 `app/...`) 路径全部相对
> `api-service/` 子包。FastAPI 入口是 [`api-service/app/main.py`](../api-service/app/main.py),
> 播种器在 [`api-service/app/services/bootstrap/`](../api-service/app/services/bootstrap/),
> 手动 CLI 是 `cd api-service && python -m scripts.bootstrap`。
> 不要在仓库根新建 `app/` —— 它不存在。

**What**: [`api-service/app/main.py`](../api-service/app/main.py) lifespan
calls `run_all()` after `init_db()`. The 4 chamber presets (A/B/C/D),
instrument model catalog, sequence library, report templates, and test-case
templates land in the DB on first boot.

**Why**: New installs see empty everything → operators can't get past the
"create your first chamber" step without running
`cd api-service && python -m scripts.bootstrap` manually. The seeders +
idempotent `bootstrap_history` are already built — nobody wired the pipe
to lifespan startup.

**Acceptance**:
- `docker-compose up` on an empty DB seeds 4 chambers + 12+ instrument
  models + 8+ sequences + report templates
- Restart on an already-seeded DB is a no-op (`bootstrap_history` records
  match)
- `BOOTSTRAP_ON_STARTUP=false` env var disables auto-run (escape hatch)
- HAL readiness table shows a `[bootstrap]` row summarising what was seeded
- Tests: empty-DB cold start → 4 chambers visible; warm-restart → no
  duplicates

**Status**: ✅ Done — PR #17 (merged 2026-05-14). Codex P1 follow-up
on the same PR added a PG advisory lock to serialise startup across
concurrent gunicorn workers.

---

### P0-2 — Lab Profile init wizard ✅ Done (PR #18)

**What**: GUI detects `LabProfile.count() == 0` on first launch and shows a
3-step wizard (chamber dimension editing deferred to existing chamber config
tab — out of wizard scope, per 2026-05-14 scope decision):
1. Pick chamber template (A/B/C/D cards) + name your lab
2. Bind instruments (model + IP/port for each category)
3. Confirm + create LabProfile

**Why**: Without this, even seeded chambers don't help — operators don't
know that the chamber template needs to be cloned + assigned to a Lab
Profile before tests can run.

**Acceptance**:
- Fresh install → GUI shows wizard, not empty dashboard
- Wizard completes → at least one active LabProfile exists with a
  Chamber + at least one Instrument bound
- Cancellable + resumable (don't lose progress on browser refresh)
- Existing lab → wizard does not appear

**Implementation prerequisites**:
- LabProfile API is currently read-only (`GET /lab-profiles` only,
  designed for deployment-seeded profiles). The wizard needs a new
  `POST /lab-profiles` endpoint covering name + chamber_config_id +
  instrument_bindings + is_active. *(Done in PR #18.)*

**Status**: ✅ Done — PR #18 (merged 2026-05-14). Codex P1 follow-up
fixed the wizard to send the real `InstrumentCategory.id` UUID
instead of the catalog key string, so downstream diagnostics resolve
`category_key` correctly.

---

### P0-3 — Path-loss calibration (CAL-01) loop closure + cal cert generation ✅ 主体 Done (2026-07-03 现场)

> 收口: 真硬件 CE+SA 校准端到端跑通, 32 链路证书生成 + 绑 lab (现场任务
> Phase 3)。余一条 acceptance = 复测重复性 ±0.5 dB, 归并 P1-4 下次现场。

**What**: Run the CE+SA path-loss calibration end-to-end on real hardware,
producing a `CalibrationCertificate` row with the 32-element
`path_loss_db_by_rf_chain` map. The MIMO_OTA `MEASURE` phase already
consumes this — currently fails open with `avg_path_loss_db=0.0` when
absent.

**Why**: Without per-chain path loss, throughput/RSRP measurements are
uncalibrated — the first-call output is unverifiable. Precheck warns but
doesn't block, so operator can "complete" first-call with garbage
numbers.

**Acceptance**:
- Calibration run produces a CalibrationCertificate with all 32 chains
  populated (non-zero)
- `overall_pass = True`
- `valid_until > now()` (typically +30 days)
- Precheck phase sees the cert and stops warning
- A repeat measurement gives the same path-loss values within ±0.5 dB

**Status**: `[x]` 主体 done 2026-07-03 现场 (32 链路证书 + 绑 lab); 余复测 ±0.5 dB → P1-4
**Estimate**: on-site 1 day + local 0.5 day

---

### P0-4 — SignalAnalyzer in HAL for reference TRP ✅ Done (2026-07-03 现场)

> 收口: 真 FSVA3000 入 HAL, reference 相位真读数, TRP 基线 ±1 dB 达标
> (现场任务 Phase 2)。三条 acceptance 全过。

**What**: Bind the on-site **R&S FSVA3000** signal analyzer (driver
`RealRsFsvaDriver`, model `FSVA3000`) to the HAL `signalAnalyzer` category
and connect it to a known-gain reference horn antenna in the chamber.
Reference phase reads real channel power, applies the offset, and emits a
real TRP — not the current mock 23.5 dBm fallback. (Catalog also carries
R&S FSW43 + Keysight X-Series as alternates, but CAICT's receiver is the
FSVA3000 — see `caict_v4` topology template.)

**Why**: The `_MOCK_TRP_DBM` fallback means the compensation factor is
fake. Real first-call needs the real path:
`measured_TRP = SA_power + offset → compensation_factor = horn_gain - (measured - nominal)`.

**Acceptance**:
- `signalAnalyzer` driver is loaded (readiness table shows ✓)
- Reference phase logs `measurement_source: "hal_signal_analyzer"` (not
  `"mock"`)
- Measured TRP within ±1 dB of horn datasheet TRP at the tested
  frequency

**Status**: `[x]` done 2026-07-03 现场 — FSVA3000 真连接入 HAL, reference
相位 `measurement_source: "hal_signal_analyzer"`, TRP ±1 dB 达标。
**Estimate**: on-site 0.5 day + local 0.5 day

---

### P0-5 — DUT attach → bearer → PDSCH on UXM 5G NR 🚧 物理链已跑通，待证据闭环后正式复验

**What**: Put a real DUT in the chamber, attach it to UXM via SIM + RRC,
establish a default bearer, push PDSCH traffic, and read back actual
throughput. The MEASURE phase needs this to compute real RSRP/SINR/Tput.

**Why**: 2026-07-21 现场已完成 attach 与转台四方向测试，证明物理链可工作；但驱动层
缺少关键 SCPI 的发送、回复、仪器接受、生效状态与业务结果的同次执行关联，现有记录不能证明
正式 TestCase 完整按预期参数运行。关闭标准因此从“再证明能跑”升级为“证明软件闭环正确”。

**Acceptance**:
- POST /test-executions/{id}/attach-dut succeeds, records only an IMSI hash/last-four identifier,
  and proves RRC connected + bearer active
- The same execution snapshot records the live instrument model, firmware, and UXM Test Application
- F64 current model matches the request and simulation state is RUNNING
- After coordinate-offset compensation, all four requested/feedback angles differ by no more than ±1°
- All four directions return valid throughput values greater than zero; numerical values need not be distinct
- The same `TestExecution` carries machine-checkable E0 intent / E1 transport /
  E2 accepted / E3 applied / E4 outcome evidence for every critical UXM, F64,
  and positioner control; only in-scope `confirmed` manual evidence can make the gate green

**Status**: `[ ]` formal acceptance open — physical attach + four-direction run completed
on 2026-07-21; P1-45 mapping is complete, now blocked on local P1-46/41/47A-C evidence work, then one on-site
formal TestCase revalidation.

> **历史记录 — 5/27 现场部分重现 (非验收)**: DUT 经 SCPI 控制的 UXM + F64(3600M/N78) 稳定 **CONN + DL live**,
> 但吞吐 **0% ACK / all-NACK** (DUT 收到但解不出 PDSCH) —— 根因是 F64 输入信号参考/crest 没设对
> 致 DL 失真 (见 P0-8), **不是** attach 链路问题。`attach-dut` 端点的 `query_ue_capability` 在
> LTE_NR_IRAT profile 上不支持 (走 Swagger 手动)。**当日转台 (Aerotech) 4 方位扫未做** (转台本身
> 测试无结论, 见 U-5)。当日真验收仍待 P0-8 输入参考闭环 + 真 DUT + 转台；当前量化标准以上方 Acceptance 为准。

**Estimate**: on-site 1-2 days

---

### P0-6 — Mock-data first-call end-to-end (local rehearsal) ✅ Done (PR #19)


**What**: Run all 5 commissioning phases locally with mock cal cert /
mock SA / mock DUT to **confirm the software pipeline has no blind
spots**. The 5 phase executors exist (1386 LOC total) but the full chain
was never exercised in one run.

**Why**: Going on-site without this means we again debug driver layer +
commissioning at the same time. Decouple them: software pipeline first,
hardware second.

**Acceptance**:
- One TestExecution row with `test_type=MIMO_OTA` runs all 5 phases to
  completion
- `phase_statuses` ends at `{"precheck": "passed", "reference":
  "passed", "mimo_test": "passed", "analysis": "passed", "report":
  "passed"}` — implementation note: the API derives status from
  measurement payloads as `pending` / `failed` / `completed`; the
  roadmap-informal "passed" maps to `completed`.
- A PDF report is generated
- No phase errors surfaced

**Status**: ✅ Done — PR #19 (merged 2026-05-15). Root cause of
"completes without PDF" was a swallowed `AttributeError` on
`execution.test_plan` (relationship commented out in the model);
fix added in `report.py` + strict E2E test
`test_commissioning_e2e_p06.py` pins PDF-on-disk acceptance going
forward. Codex P2 follow-up added `db.expire_all()` to those tests
to defend against SQLAlchemy identity-map stale reads under
non-StaticPool configurations.

---

### P0-7 — Channel-Engine real-mode path + external_asc debug mode ✅ Done (PR #56)

**What** (three coupled issues fixed together):

1. **`mimo_first_asc` engine mode 永远跑 mock**: [`channel-engine-service/app/api/endpoints/hardware_pipeline.py:40-49`](../channel-engine-service/app/api/endpoints/hardware_pipeline.py#L40)
   - L45 `from mimo_ota_simulator.simulator import OTASimulator` — 真实类名是 `MIMO_OTA_Simulator`, ImportError 被静默吞掉
   - L208 构造签名错 — 真实构造无参数
   - L224 `sim.run_with_external_clusters(...)` — 真实 API 是 `.run(chamber, config, synthesis_method=...)`, `run_with_external_clusters` 是 ChannelEgine D11 决定**不实现**的别名
   - 任何 real-mode 请求 → ImportError → fallback `_run_mock_synthesis` → 1-tap Doppler shift placeholder .asc → 操作员收到假信道, 没有 warning
   - 默认 `CHANNEL_ENGINE_PATH=~/ChannelEgine` 在本机不存在 (实际 clone 在 `/Users/Simon/Tools/ChannelEgine`), 这是 ImportError 的双重根因

2. **端到端参数链路缺 Phase 5/6 字段**: ChannelEgine 远端已 merge PR #5/#6, 但 MIMO-First `HardwarePipelineRequest` schema + `ChannelEngineClient` 都不知道这些字段存在
   - per-cluster: `xpr_db`, `initial_phases_rad: [4]` (4-ray init phases)
   - top-level: `k_factor_db` (LOS boost), `synthesis_method: strict_pfs|ray|cluster_legacy`
   - antenna: `polarization: V|H` 字段 (Tx + Rx 各一个)
   - 速度: `ue_velocity_mps: [vx, vy, vz]` (现有 scalar `velocity_kph` 是简化, ChannelEgine 期望 3-vector m/s)

3. **手工搬 ASC 调试能力是隐式 hack**: 操作员当前调试 commissioning 时直接跑 ChannelEgine `app.py` Streamlit 在本机产 .asc, 然后绕过 api-service 用 FTP 直接塞 F64。这条路径没有 first-class 支持, 操作员手工干预的 audit trail 也没记录。

**Why P0** (production-fake-data 严重 + 下次现场前 must-fix):
- Commissioning 宣称的"two-engine PFS" 实际只有 `keysight_gcm` 一条能用; `mimo_first_asc` 在生产 100% fake. 下次现场前必须修否则现场也跑假数据。
- 当前所有真 P0 (P0-3/4/5) 都 on-site-blocked → P0-7 补位 Current Focus 是 WIP=1 合规的 (不是 "顺手优化", 是 P0-tier 补位)
- "外部 ASC 调试通道"上 production 路径后特别有价值: 出 bug 时操作员用 ChannelEgine GUI 产已知好的 .asc 喂进 MIMO-First, 立刻分辨 bug 在 MIMO-First 端还是集成链路

**Scope** (single PR, P0):

| Step | Subject | Files |
|------|---------|-------|
| 0 | `CHANNEL_ENGINE_PATH` fail-fast on microservice startup; remove silent ImportError → mock fallback; mock 升级为显式 `MOCK_ASC_MODE=1` env flag (debug-only) | `channel-engine-service/app/main.py`, `.../api/endpoints/hardware_pipeline.py`, `.env.example` |
| 1 | api-service 加 `EngineMode.EXTERNAL_ASC` + `asc_source_path` 字段 + measure dispatch 分支 (external_asc 跳过 ChannelEngineClient, 直接读本地目录, metadata 仍要求填) | `api-service/app/schemas/mimo_ota/`, `.../services/mimo_ota/executors/measure.py` |
| 2 | `HardwarePipelineRequest` schema 加 6 个 Phase 5/6 字段 | `channel-engine-service/app/models/hardware_pipeline_models.py` |
| 3 | 重写 `_run_real_synthesis`: `MIMO_OTA_Simulator().run(chamber, config, synthesis_method='strict_pfs')` + `CustomCDLProfile.from_dict()` + `ChamberConfig` + `TargetChannelConfig` (per [`ChannelEgine/CLAUDE.md`](../../ChannelEgine/CLAUDE.md) "MIMO-First 集成路径") | `channel-engine-service/app/api/endpoints/hardware_pipeline.py` |
| 4 | `ChannelEngineClient.synthesize_hardware_pipeline()` payload 透传新字段 | `api-service/app/services/channel_engine_client.py` |

OpenAPI contract sync (4 步标准流程: openapi.yaml + `npm run openapi:generate` + service.ts + mockServer), GUI commissioning 引擎下拉三选一 + external_asc 路径输入。

**Acceptance**:
- ChannelEgine 真路径打通, e2e 测试 (gated on `CHANNEL_ENGINE_PATH` 存在且 import 成功) 验证 .asc 内容**不是** placeholder Doppler shift
- `external_asc` 模式: 给定一个目录, 系统能扫到所有 `channel_InX_OutY.asc` 文件, FTP 上传 F64, audit trail 记录 `external_asc_source_path` + metadata
- ImportError 路径: 微服务启动期 fail-fast (而不是 runtime 静默假数据); 显式 `MOCK_ASC_MODE=1` 启用时 response 中带 `"mock_mode": true` 警告
- 单元测试: payload shape 含全部新字段; assertion 错误指向具体字段
- Memory + roadmap: 3 个 PFS memory 更新到 post-Phase-6 现状, P2-6 标 Done (指向 ChannelEgine PR #1-#6), 两条 backlog 关闭

**Status**: ✅ Done — PR #56 (merged 2026-05-18). Codex P2 follow-up in
the same PR moved the engine-selector + asc_source_path TextInput from
post-session unreachable code into pre-session UI so external_asc
sessions can actually be created.
**Estimate**: 2-3 days planned, actual ~1 day

---

### P0-8 — F64 driver 现场修复落地 (port 3334 + 输入信号参考/crest + 加载 gate + 默认 .smu) ✅ 本地半 Done, 🚧 现场半 on-site

> **来源**: 2026-05-27 现场。F64 是 first-call 两天 blocker 的核心。现场把根因挖到底、
> 在真机上验证了修法, 但都是裸改 (未提交); "输入信号参考"另立专项设计 (driver 有方法却无人调用, 需跨 driver 操作点闭环)。本项把验证过的修法
> offline 正式化, 让下次现场只做硬件实测、不再写 driver —— **这正是治理铁律「现场不写 driver
> 代码」的补救路径**。完整诊断见 [`docs/site-debug/2026-05-27-morning-log.md`](site-debug/2026-05-27-morning-log.md) §10。

**根因 (现场坐实)**:
1. **端口**: PROPSIM F64 的 ATE/SCPI 端口硬件固定 **3334** (User Reference §1.1.2.1)。早期默认/配置误用 **5025** (Keysight/R&S 风格 SCPI-RAW 口) → 响应 desync + 文件加载报 -300。[`api-service/app/hal/propsim_f64.py:285`](../api-service/app/hal/propsim_f64.py) 现场已强制 3334 (**未提交**); 文件头注释 28-29 行还写反 ("5025 standard / 3334 backup"); DB channelEmulator 绑定默认端口也还是 5025。
2. **输入信号参考缺失 (今天最大新发现)**: F64 每个输入需设平均电平 (dBm) + crest factor (dB), 否则前端增益错 → 输入口不变绿 → DL 失真 → DUT 能 attach 却解不出 PDSCH (0% ACK)。**纠正"完全没有"**: driver 其实已有 `autoset_input_level()` (`INP:LEV:MEAS?`+`INP:LEV:AUTOSET`, 含 crest) + `set_baseband_power()` (`INP:LEV:AMP:CH`), 但**无任何上层调用** —— 真实缺口 = 有方法没人调用 + 缺正确测量条件 (满 RB / burst) + 是个**跨 driver 操作点闭环** (UXM 功率↔F64 参考, 非 `set_channel_model` 加一行)。完整设计 (含静态 vs AGC、WiFi/双向) 见 [f64-input-level-and-dynamic-range](architecture/f64-input-level-and-dynamic-range.md)。命令族 (运行态亦可下发): `INP:LEV:AMP:CH <in>,<dBm>` / `INP:CRE:SET <in>,<dB>` / `INP:LEV:AUTOSET <in>,<t>` (自动测+设, in=0=全部) / `INP:LEV:MEAS? <in>,<t>` (返回 level,crest; 无信号=-300) / `INP:LEV:AMP:LIM? <in>` (限值)。
3. **加载无 gate**: 早上 -200 误诊根因 —— 文件加载后只看 `*OPC?=1` 就当成功, 实际文件没加载 ("No simulation opened")。必须加载后 `SYST:ERR?` gate。
4. **channel_count 应从 `SYST:INFO?` 读** (现场确认: 射频通道恒 32, 2x2/4x4 是逻辑通道 2x32/4x32, 不需重新编译)。

**Scope (single PR, 本地可启动)**:

| Step | Subject | Files |
|------|---------|-------|
| 0 | 端口正式化: 强制 3334 + 忽略 config port (硬件固定) + 修文件头 28-29 行注释 | `api-service/app/hal/propsim_f64.py` |
| 1 | DB channelEmulator 绑定默认端口 5025→3334 (seeder / catalog) | bootstrap seeder + catalog |
| 2 | **输入参考操作点子系统** (重定义, 见[设计文档](architecture/f64-input-level-and-dynamic-range.md)): driver 原子能力 (autoset-all / MEAS / burst 模式 / limits·clipping 状态) + CE↔BS 闭环 + **下行静态 AUTOSET** (满 RB 测一次锁定; AGC 留 WiFi/双向, 仅记录不实现) | `propsim_f64.py` + 操作点管理服务 |
| 3 | 加载后 `SYST:ERR?` fail-loud gate (不靠 `*OPC?=1` 误判) + 加载前 drain 队列 (避免 stale FIFO 误判, Codex) | ✅ **PR #93** (in review) |
| 4 | 默认信道配置文件 = 今天的 3600M .smu (见下), 允许操作员改路径/名称 | channelEmulator 默认 scenario 配置 |
| 5 | 单元测试: 端口固定 / 输入参考命令序列 / SYST:ERR? gate / SYST:INFO? channel_count 解析 (mock SCPI 交换, 不需硬件) | `tests/` |

**默认信道配置文件 (用户 2026-05-27 指定)**:
`D:\Scenario Packs\F9815064A TS 5G FR1 MIMO OTA\1.1\3GPP_FR1_OTA_CDLC_UMa_3600M.wiz\3GPP_FR1_OTA_CDLC_UMa_3600M.smu`
—— 3GPP FR1 OTA CDL-C UMa, **3600 MHz (N78)**, 4 输入 MIMO OTA 模型。今天真机加载/运行通过, 设为 F64 默认供今后使用 (路径 / 名称可改)。

**Acceptance**:
- **本地半 (offline, 本 PR)**: 端口固定 3334 + 文件头注释修正 + DB 端口改 + 输入参考操作点子系统 (下行静态 AUTOSET) + 加载后 `SYST:ERR?` gate + channel_count 从 `SYST:INFO?` + 默认 .smu 配好; 单元测试全过 (mock SCPI)。
- **现场半 (下次现场实测)**: real F64 上 load→run→改参全 0 error; 设对输入参考后 **输入口变绿**; DL 不失真 (DUT attach 后非 0% ACK)。正确的 level / crest 真值待实测 (见 U-6)。

**Status**: **本地半 ✅ Done** (2026-05-28) —— Step 0+1 (端口 3334 + DB seeder) ✅ PR #92;
Step 3 (加载后 `SYST:ERR?` gate + drain) ✅ PR #93; Step 2 输入参考操作点子系统 ✅:
Phase 1 (atomic) PR #95 + Phase 2 (InputLevelController stand-alone) PR #96 +
Phase 2b (接入 measure phase 闭环) PR #98; Step 4 (默认 3600M .smu + connection_params
override + 加载默认时拓扑同步) ✅ PR #97; Step 5 (单元测试) 跟 Step 2/3/4 一起 ✅. 🚧
**现场半待下次现场实测**: real F64 上 load→run→改参全 0 error + 输入口变绿 + DL 不失真
(DUT attach 后非 0% ACK); 正确的 level / crest 真值由 [`InputLevelController` 默认参数]
(`api-service/app/services/input_level_controller.py`) 兜底, 真值待标 (U-6)。
**Estimate**: 本地 ~1.5 day (实际 ~2.5 day 含 6 个 PR + Codex review iterate) + 现场实测 ~0.5 day

---

## 🟠 P1 — First-call confidence / repeatability

### P1-1 — Capability registry + plan-level pre-flight ✅ Done (see D10)

**What**: Standard vocabulary of capability tokens
(`ce.gcm_native`, `ce.interference_gen`, `bs.5g_nr`, `pos.single_axis_az`,
…). Each step template declares `needs: List[str]`. Each driver, post-
connect, declares `capabilities: Set[str]`. A `validate_plan(plan, lab)`
function returns the gap list. GUI shows a "预检" button on each plan.

**Why**: Discovers capability mismatches at plan-edit time, not at
runtime. Today the chain is "compose plan → run → step 4 fails because
F64 license not installed → diagnose 30 minutes".

**Acceptance** (concrete now P2-2 is done):
- `TestStep` declares `needs: List[str]` of canonical tokens (column,
  default `[]`).
- `validate_plan(plan, lab, db, hal)` returns a typed `PreflightResult`
  with `gaps: List[Gap]` where each Gap names step + missing token +
  category. Empty `gaps` == plan is runnable for that lab.
- `POST /api/v1/test-plans/{plan_id}/preflight` returns the result.
  ⚠️ **ARCH-1 S4b 已删除该端点**（连同整条计划链）；用例级 preflight 需先建
  "相位/模板 → 能力"数据源，是独立立项（task #100）。
- ≥1 seeded step template ships with a real `needs` declaration as
  dogfood proof (F64 calibration-tone → `ce.interference_generator`).
- GUI plan row gains a "预检" button calling the endpoint and
  showing gap details in a Mantine Modal (PR B).

**Implementation split (2026-05-16)**:
- **PR A** — backend: column + validator + endpoint + seed update +
  tests. Independently usable via curl.
- **PR B** — GUI: button + Mantine Modal listing gaps. Lands after PR A.

**Status**: ✅ Done — see D10 in [`roadmap-archive.md`](roadmap-archive.md). All four PRs in main:
#22 (PR A backend), #23 (PR B GUI), #24 (Codex P1 iter 2: per-binding
endpoint scoping with `mismatched_drivers` field distinct from
`not_loaded_categories`), #25 (Codex P2: VISA + plain endpoint alias
matching, preserving HiSLIP / VXI-11 named resources verbatim so
`hislip0` ≠ `hislip2` on the same UXM host).
**Estimate**: 2 days (actual: ~6 hours implementation + 4 review iterations
across 4 PRs — review surface dominated, see Codex retrospective notes
in the relevant PR descriptions)

### P1-2 — F64 license probe SCPI on-site verification

**What**: The soft-probe SCPIs in PR #15 (`OUTPut:INTERFerence:LIST?` /
`SYSTem:CALibration:USER:LIST?`) are placeholders — they're shaped right
but unverified on real F64. Verify on next site visit.

**Acceptance**: probe correctly reports presence/absence of each license
on a unit where the licensed state is known a priori.

**Status**: `[ ]` not started
**Estimate**: on-site 1 hour

### P1-3 — PyVISA "not installed" investigation ✅ Done (2026-05-16)

**What**: Reproduce the "PyVISA missing" condition seen during ENA
debugging. Run `which python && python -c "import pyvisa"` in the same
context. Confirm whether it was IDE-warning misread, wrong-venv, or
genuinely missing.

**Outcome**: IDE-warning misread. PyVISA 1.16.2 is installed and
working in the project venv (`api-service/.venv/`); it's missing
from the system Python at `/opt/homebrew/bin/python3`, which is
what the IDE was statically analyzing against. Same root cause as
the 2026-05-14 IDE-diagnostics backlog entry — they were two faces
of the same interpreter-path-drift problem. Real fix (committing
`.vscode/settings.json`) is the IDE-diagnostics backlog item;
deferred here because `.vscode/` is currently gitignored and that
decision needs its own scoped change.

**Acceptance**: root cause documented — see
[`docs/site-debug/2026-05-16-pyvisa-ide-interpreter-investigation.md`](site-debug/2026-05-16-pyvisa-ide-interpreter-investigation.md).

**Status**: ✅ Done

### P1-4 — first-call repeatability test

**What**: Run first-call 3x back-to-back on the same config. Plot RSRP /
SINR / Throughput variance. Establish the noise floor for "this is the
same lab".

**Acceptance**: variance documented; outliers explained.

**Status**: `[ ]` not started — depends on P0-3..P0-5 being on site
**Estimate**: on-site 1 day

### P1-5 — CAL-04 phase calibration

**What**: 32 probes need phase calibration so the spatial sum forms a
proper quiet zone. Endpoint exists (`phase_router`), workflow needs to
be exercised on-site.

**Why we're building this even though 3GPP TR 37.977 PFS doesn't
require it**: see [`docs/features/calibration/pfs-phase-immunity.md`](features/calibration/pfs-phase-immunity.md).
TR 37.977 §F.2 (MPAC normative cal) is power-only; PFS-mode is
mathematically immune to per-probe chamber phase errors via per-probe
independent fading. **But** the project is planned to extend to PWS
(Plane Wave Synthesis) mode in the future — PWS uses coherent
per-probe signals, immunity breaks, per-probe phase cal becomes
mandatory. Keeping the infrastructure (DB table, service, endpoint,
tests) avoids a costly rebuild when PWS lands.

**Acceptance**: phase cal cert generated; quiet zone metric improves
vs uncalibrated baseline.

**Two halves**:

| Half | Scope | Status |
|---|---|---|
| **Local** | Offline CSV import: operator measures per-probe per-frequency phase with external VNA → exports CSV → `POST /api/v1/probe-calibrations/phase/import-csv` ingests directly into `probe_phase_calibrations`. No SCPI, no hardware. Enables phase-cert workflow to exist on the production code path before live measurement is built. | ✅ Done — this PR |
| **On-site** | Replace the mock body of `POST /phase/start` with real SCPI sequence (CE injects tone → SA measures phase per probe, looped through topology switch). Requires real CE+SA at chamber. | 🔄 Not started, blocked on next on-site |

**Status**: 🟡 Half done — local CSV-import path shipped (this PR);
on-site SCPI workflow still pending real-chamber measurement
**Estimate**: 0.5 day local (this PR), 0.5 day on-site (next trip)

### P1-6 — FS16 / UXM / ENA silent-reconnect integration tests

**What**: F64 has 12 integration tests for the silent-reconnect pattern
(PR #15). FS16, UXM, ENA inherit the pattern but don't have driver-
specific integration tests. Add them once we see real idle-close
evidence.

**Status**: `[ ]` not started — pulled forward only if a real
production idle-close is seen on those drivers
**Estimate**: 0.5 day

---

### P1-7 — CDL data source wire-up: commissioning → ChannelEgine standard 38.901 ✅ Done (PR #59)

**What** (closes P0-7's upstream mock gap):

P0-7 (PR #56) 把 client + 微服务 + ChannelEgine library 三层之间的 API mismatch
全修了, 端到端 e2e gated test 也跑通。但 commissioning `mimo_first_asc` 实际
被调用站点 [`asc_strategy.py:62-77`](../api-service/app/services/channel_generation/asc_strategy.py#L62)
仍然是:

```python
pipeline_result = await self.ce_client.synthesize_hardware_pipeline(
    chamber_id=...,
    frequency_hz=...,
    clusters=[
        CDLCluster(delay_s=0.0, power_relative_linear=1.0)   # ← Mock, 1 cluster
    ],
    cdl_model_name=cdl_model_data.get("model_name", "UMa CDL-C NLOS"),
    # synthesis_method / ue_velocity_mps / k_factor_db: 完全没传, 走 default
    ...
)
```

操作员选 "UMa CDL-C NLOS" 等 3GPP 标准模型, 通过 GUI 触发 commissioning measure
phase → 实际打到 ChannelEgine 的是 strict_pfs 算 **1 簇** 的 OTA 信道, 不是 38.901
完整 multi-path。P0-7 在 client 加的 Phase 5/6 字段 (xpr_db / k_factor_db /
initial_phases_rad / polarization / synthesis_method / ue_velocity_mps) 在这个
调用站点全部没透传, 全部走 client signature 的 default。

**Why P1 (not P0)**: 不是 silently broken — `cdl_model_name` 透传到 microservice
response 里, 操作员能看到。`keysight_gcm` 走 vendor F64 GCM Studio 路径不受影响,
`external_asc` 走操作员手工 .asc 也不受影响。所以现场可以用其他两个 mode 跑
first-call。但 `mimo_first_asc` 是宣称的"production default", 这条不修等于这条
路径还停在 placeholder 状态, 不能算 GA。

**Design — ChannelEgine 当 3GPP 权威源** (B 方案):

ChannelEgine 已经在 [`mimo_ota_simulator/channel_builders.py:17`](/Users/Simon/Tools/ChannelEgine/mimo_ota_simulator/channel_builders.py#L17)
实现 `Standard3GPPBuilder`, 通过 `TargetChannelConfig(input_mode='standard',
model_name=..., cluster_model_name=...)` 调用 `ChannelSimulator` 内部 38.901
generator。MIMO-First **不复制** 38.901 表到本 repo, 只:

- 解析 `cdl_model_name` "UMa CDL-C NLOS" → `(scenario="UMa", cluster_model="CDL-C", condition="NLOS")`
  — 这只是字符串规约, 不是 3GPP 数据
- 透传 scenario + cluster_model + force_condition + bs/ue position + velocity 给微服务
- 微服务发 `input_mode='standard'` 给 ChannelEgine, 后者用自己的表生成簇

合理性: A 方案 (MIMO-First 复制 38.901 表) 在 ChannelEgine 升级时会漂; B 方案
单点 source of truth, 任何 ChannelEgine 模型更新对 MIMO-First 透明。

**Scope** (6 steps, single PR):

| Step | Subject | Files |
|------|---------|-------|
| 1 | 微服务 `HardwarePipelineRequest` schema 加 `input_mode: Literal['standard','custom']` + standard-path 字段 (`scenario_name`, `cluster_model_name`, `force_condition`, `bs_position`, `ue_position`, `random_seed`). Custom path 字段保持向后兼容。 | `channel-engine-service/app/models/hardware_pipeline_models.py` |
| 2 | 微服务 `_run_real_synthesis` 按 `input_mode` 分路: standard → `TargetChannelConfig(input_mode='standard', model_name=..., cluster_model_name=..., ...)`; custom → 现有 `CustomCDLProfile` 路径不变。 | `channel-engine-service/app/api/endpoints/hardware_pipeline.py` |
| 3 | api-service 新 `cdl_model_parser` 服务: `"UMa CDL-C NLOS"` → `(scenario, cluster_model, condition)`. 规约表 (7 scenarios × 7 cluster_models × 2 conditions) 枚举为 Python 常量, 不是 3GPP 数据。未知名 → raise ValueError。 | `api-service/app/services/cdl_model_parser.py` (new) |
| 4 | `ChannelEngineClient.synthesize_hardware_pipeline` 签名加 `input_mode` + standard-path 参数, `_build_payload` 按 mode 分路。`clusters` 改 Optional (standard 模式不用)。向后兼容: 不传 `input_mode` 默认 `'custom'` 保持 P0-7 行为。 | `api-service/app/services/channel_engine_client.py` |
| 5 | `asc_strategy.py.generate_and_load` 重写: 删 `Mock` cluster, 调解析器拿 (scenario, cluster_model, condition), 调 client `input_mode='standard'` + 透传 Phase 5/6 字段 (synthesis_method='strict_pfs', ue_velocity_mps 从 simulation_rules 派生, k_factor_db None 让 ChannelEgine 内部默认)。 | `api-service/app/services/channel_generation/asc_strategy.py` |
| 6 | 测试: 解析器单元 (7×7×2 + 几个 invalid) + payload-shape (standard mode 不带 clusters, 带 scenario/cluster) + e2e gated on `CHANNEL_ENGINE_PATH` (standard 路径返回非 placeholder, total_files > 1 cluster baseline). Revert-reapply 验证。 | `tests/test_cdl_model_parser.py` (new), `tests/test_channel_engine_real_path.py` (扩展) |

**Acceptance**:

- 解析器覆盖 7 scenarios (`UMa`/`UMi-StreetCanyon`/`UMi-OpenArea`/`RMa`/`InH-Office`/`SMa`/`InF`) × 7 cluster_models (`Stochastic`/`CDL-A..E`/`SCME`) × 2 conditions (`LOS`/`NLOS`) — 命中即可拆, 不命中 raise ValueError
- 微服务 `input_mode='standard'` 路径调 ChannelEgine 后, response 跟 P0-7 的 custom 路径行为一致 (status='success' / mock_mode=False / 非 1-cluster placeholder zip 大小)
- `asc_strategy.py` 不再 grep 到 `# Mock` 注释或 `delay_s=0.0, power_relative_linear=1.0` 硬编码 cluster
- e2e gated test (`CHANNEL_ENGINE_PATH` 设好): standard 模式生成的 zip 包含**多于 1 簇** 的 channel impulse response (通过 PropsimASCIIExporter 输出文件数 / 总 zip 大小验证)
- 现有 P0-7 e2e (`test_channelegine_api_still_callable_with_our_adapter_args`) 不回归

**Out of scope**:

- HTTP distributed test (api-service → 真的 HTTP → 微服务): P0-7 留下的同一个 gap, 单独跟进
- 操作员 GUI 加 `scenario` / `cluster_model` 独立下拉: 现有 `cdl_model_name` 单字符串足够, 解析器在 api-service 端拆。GUI 后续要细化 (例如让操作员单独改 force_condition) 时再开 PR
- UMa CDL-C **LOS** 模式 K-factor 操作员定制 (现在用 ChannelEgine 内部默认值)

**Status**: ✅ Done — PR #59 (merged 2026-05-19). Codex P1 follow-up
(commit c5a2068, 同一 PR 内 push) 修了一个真 regression: 初版 parser 假设 token
顺序 `{Scenario} {ClusterModel} {Condition}`, 但 GUI `MIMOOTAConfigForm.tsx`
的 `CDL_OPTIONS` 实际用 `{Scenario} {Condition} {ClusterModel}` + 有 alias
(`UMi`→`UMi-StreetCanyon`, `InH`→`InH-Office`) + bare cluster (`CDL-A`...`CDL-E`),
所以每个 operator 选择都会被旧 parser 拒。改成 token-order-agnostic classification
(按 `SCENARIO_NAMES`/`CLUSTER_MODEL_NAMES`/`CONDITION_NAMES` 三个 disjoint 集合
归类, 不按位置) + 加 `SCENARIO_ALIASES` + 1-3 token 支持。Parser tests 113 → 239。
Architecture note 全景图见 [`docs/architecture/channel-engine-data-flow.md`](architecture/channel-engine-data-flow.md)
(本 PR 同步落)。

**Estimate**: 1-1.5 days (实际 1 天 + Codex follow-up ~30 分钟)

**On-site followup**: 真 F64 硬件 + commissioning `mimo_first_asc` 模式 + 24-cluster
.asc 落地 + KPI 跟 P0-7 1-cluster baseline 对比 — hardware-blocked, 等下次现场。
HTTP distributed pytest (api-service → 真 HTTP → 微服务): P0-7 留下的 namespace
冲突 gap 没修, 生产代码路径用真 httpx 但 pytest 没独立验证 HTTP layer。两者
不阻塞后续工作。

---

### P1-8 — Commissioning precheck cal-missing fail-loud gate ✅ Done (PR #61)

**What**: 修 [`PrecheckExecutor`](../api-service/app/services/mimo_ota/executors/precheck.py)
原 `overall_pass = critical_online and qz_pass and ue_cap_pass` 不读校准状态的
silent failure mode (Codex P2 抓在 PR #60 commit 81f6923 写 architecture note 时
被 catch)。没建 cal cert / 没跑路损校准的 chamber 也能从 precheck 通过, measure phase
silently fallback 到 `typical_cable_loss_db + duplexer - pa_gain` 标量。

**Why P1**: 直接威胁 P1-4 first-call repeatability。No code-level safety net 等于
所有 first-call quality 依赖 GUI workflow 主观顺序 "先 cal 后 commission"。

**Why discovered**: 写 PR #60 architecture note 时假设 precheck 是 fail-loud gate, Codex
P2 抓了错记并指向 `precheck.py:236` 真实计算 — 直接 promote 为 P1-8。

**3 个 design 决策** (user 2026-05-19 lock):

1. `cal_cert` 缺失 → warning, 不 FAIL (cert binding 是 LabProfile 阶段事情);
   `cal_cert.overall_pass=False` → FAIL (cert 显式标 broken)
2. `path_loss_calibration` 缺失 → FAIL (measure phase 真用的数据)
3. `MIMOOTAConfiguration.precheck_strict_cal: bool = True` flag, production-safe
   default; 显式 opt-out 跳过 gate 维持旧行为, audit trail 保留; GUI 不暴露

**Codex P1 follow-up** (commit 743789c on PR #61): 初版 strict gate 用 chamber-only
查询 (只 filter `chamber_id` + `status == VALID`), **没过滤频率**。但 measure phase
用 `ProbePathLossCalibrationService.get_latest_calibration(chamber_id, freq_mhz)` 走
±5% 频率窗口 (3500 MHz → 3325-3675 MHz)。一个老 700 MHz cert 能让 strict gate 通过
然后 measure 找不到 frequency-matched cert 走 fallback — 跟修 P1-8 之前同一个 silent
failure mode, 只是入口换了。修法: precheck 调跟 measure 同一个 service.get_latest_
calibration(), 单一真源。新加 6 个 frequency boundary tests (±5% edge / mismatch /
out-of-window / audit trail), 总测试 12 cartesian + 6 frequency = 18.

**Status**: ✅ Done — PR #61 (merged 2026-05-19, 2 commits: feat 42af8ca + Codex
P1 fix 743789c)
**Test coverage**: 18 passed (12 cartesian + 6 frequency boundary). 全 sweep 1468
passed / 0 failed.
**On-site followup**: GUI commissioning workflow 真 chamber smoke — 没 cal → precheck
FAIL with 具体原因 (`no_cert_for_chamber` / `frequency_out_of_window`); cal 跑完 →
PASS, measure 用真路损。Hardware-blocked, 等下次现场。

---

### P1-9 — Commissioning precheck DUT-attach fail-loud gate ✅ Done (PR #63)

**What**: 修 [`PrecheckExecutor`](../api-service/app/services/mimo_ota/executors/precheck.py)
section 2.4 `dut_attach` 缺失 / `rrc_connected != True` 时**只 warning 不 gate**
的 silent failure mode (跟 P1-8 cal gate 完全同 pattern)。

**Why discovered**: PR #62 (P1-8 docs catch-up) Current Focus 段提议"主动 audit
silent failure modes"; 用户同意后我盘查了 precheck.py 跟 measure phase 的字段
契约, 发现 [`precheck.py:78-91`](../api-service/app/services/mimo_ota/executors/precheck.py#L78-L91)
原版只 `warnings.append("Test will proceed assuming DUT is already in chamber")`,
`overall_pass` 不消费 `dut_attach`, measure.py 也完全不读 `dut_attach`
(`grep dut_attach measure.py` → 0 hits)。

**Why P1**: 直接威胁 first-call quality。操作员忘 `POST /attach-dut` 直接跑
commissioning → measure phase 合成 RSRP (target - path_loss + 高斯噪声), BS
mock 返回 canned throughput → analysis 可能 PASS, 但**整个测试没有真 DUT
attached**。这跟 P1-8 cal gate 完全同 pattern。

**3 个 design 决策** (跟 P1-8 平行套用):

1. `dut_attach is None` (没 POST /attach-dut) → **FAIL** (不像 P1-8 `cal_cert is
   None` 只 warning — 因为 cal_cert binding 是 LabProfile 阶段事情可能没绑就跑,
   但 dut_attach 是 per-execution 必须的, 不该有"先跑后绑"场景)
2. `dut_attach present 但 rrc_connected != True` → **FAIL** (RRC 没 connected
   等于 BS 找不到 DUT, measure phase 跑没意义)
3. `MIMOOTAConfiguration.precheck_strict_dut: bool = True` flag, default True
   (跟 `precheck_strict_cal` 同 pattern); GUI 不暴露; bypass 留 audit trail
   `dut_pass_reason: "bypassed via precheck_strict_dut=False (would-fail-under-strict:
   ...)"`.

**Scope** (single PR):

| Step | File | What |
|---|---|---|
| 1 | `api-service/app/schemas/mimo_ota/config.py` | 加 `precheck_strict_dut: bool = True` 字段 + 注释 |
| 2 | `api-service/app/services/mimo_ota/executors/precheck.py` | section 5b 加 dut gate (strict / bypass 分路); section 6 overall_pass 加 `and dut_pass`; failure_reason 加 dut 原因; section 2.4 warning 文本根据 strict 模式区分 |
| 3 | `api-service/tests/test_mimo_ota_precheck_dut_gate.py` (NEW) | 6 cartesian (dut_state × strict) + 1 independence test (cal + dut 两 gate 同时 fail 时 error_message 都体现) |
| 4 | `tests/test_mimo_ota_precheck_cal_gate.py` (existing) audit | `_build_context` 加 `precheck_strict_dut: False` 让 P1-8 cartesian 不被 P1-9 dut gate fight |
| 5 | `tests/test_commissioning_smoke.py` + `tests/test_commissioning_e2e_p06.py` audit | 显式 `precheck_strict_dut=False`, smoke 走 bypass 维持 5-phase chain 跑通的语义 |

**Acceptance**:

- (strict, default) `dut_attach is None` → FAIL with `error_message` 含
  "DUT attach record missing"
- (strict) `dut_attach.rrc_connected != True` → FAIL with `error_message` 含
  "rrc_connected=False" (或其他 truthy 不 True 值)
- (strict) `dut_attach.rrc_connected = True` → PASS
- (bypass) 三种 dut_state 都 PASS, 但 `dut_pass_reason` 记录 would-fail-under-strict
- `result_payload["dut_pass"]` (bool) 在 strict PASS / strict FAIL / bypass 三
  种情况都正确反映
- cal gate + dut gate 两条独立 — 一个 fail 不掩盖另一个的 audit trail
- 7 个 new tests 全过 (6 cartesian + 1 independence)
- 现有 cal_gate / smoke / e2e_p06 tests 不回归 (cal_gate 加 strict_dut=False
  fixture; smoke/e2e 加 strict_dut=False override)

**Out of scope**:

- measure.py 真消费 `dut_attach` 数据 (e.g. compare imsi against BS attached
  imsi) — P0-5 prerequisite (真 DUT attach via UXM 5G NR RRC), P1-9 只防
  precheck 层放过, 不动 measure 真测逻辑
- GUI 端 "请先 attach DUT" inline 提示 — P3 polish, 当前 GUI 自然弹 precheck
  FAIL error message 含具体原因
- Roadmap mark P1-9 ✅ Done + Summary counts 同步 — 本 PR 是 in-progress, merge
  后跟之前 P1-8 pattern 一致用 docs catch-up chore PR 收口 (per memory
  `feedback_d_row_stale_this_pr_reflex.md`)

**Status**: ✅ Done — PR #63 (merged 2026-05-19)
**Estimate**: 0.5 day (实际 ~1 day local audit + impl + tests)

---

### P1-10 — Non-Ring Chamber 几何 plumbing (closes P2-7 cross-repo half) ✅ Done (PR #64)

**What**: 关掉 [`docs/architecture/channel-engine-data-flow.md`](architecture/channel-engine-data-flow.md)
点名的 "ring-only silent constraint" — `ChannelEngineClient._build_payload`
此前硬编码 `chamber_config.distribution = "ring"`, probe 物理 az/el **不进**
HTTP payload, 非标 chamber 配置 ChannelEgine silently 按 ring 等距推算, 物理
几何跟 .asc 反映角度不符无人报错。本 PR 接通 MIMO-First 这边的 schema +
DB plumbing (P2-7 step 4/5/6), 完成跨 repo 闭环。

**Why ad-hoc promoted from P2-7**: ChannelEgine 那边 2026-05-19 主动 ship 了
Phase 8 (cross-repo trigger 来自我们这条 architecture note), 加完 `ChamberConfig`
新枚举 `'ring' / 'multi-ring' / 'custom'` + `probe_positions: Optional[List[ProbePosition]]`
+ `_check_distribution_consistency` validator + `_calculate_probe_positions` /
`_calculate_weights_for_cluster` 真消费 az/el (不再 `(p × 360°/N)` 推算)。
MIMO-First 这边不收尾就是浪费 cross-repo 协作 — 0.5-1 天 plumbing 把整条
silent constraint 关掉, ROI 远好于继续 ⏸️ 等 PWS trigger。Promotion 走的就是
"P1-8/P1-9 主动 audit silent failure mode → fail-loud gate" 同 spirit。

**3 个 design 决策**:

1. distribution enum 取值跟 ChannelEgine Phase 8 wire 完全一致 (`"ring"` /
   `"multi-ring"` / `"custom"`) — 不发明新名字。历史 microservice schema
   列了 `"sphere"` 但没人 actually 传过 (`channel_engine_client.py` 只写
   `"ring"`), 现替换为 `"multi-ring"` 跟 ChannelEgine 对齐。
2. ring 路径完全向后兼容: `ChamberConfiguration.probe_distribution` 列默认
   `"ring"`, `server_default='ring'` 历史行回填同值 → payload 不带
   `probe_positions` 字段, ChannelEgine 走原有 ring 公式, 现有 8-probe ring
   lab smoke 0 回归。
3. 非 ring fail-loud 三处 (defense in depth): (a) `channel-engine-service`
   `ChamberConfig` Pydantic validator 422; (b) `ChannelEngineClient
   ._build_probe_positions` `ValueError` (DB 无 probe / 缺 az / 数对不上);
   (c) ChannelEgine `ChamberConfig` 自己也 validate 同语义。任何一层先 fail
   都比 silent mis-synthesis 强。

**Scope** (single PR):

| Step | File | What |
|---|---|---|
| 1 | `api-service/app/models/chamber.py` | 加 `ProbeDistribution` 枚举 + `ChamberConfiguration.probe_distribution` 列 (default `"ring"`) |
| 2 | `api-service/alembic/versions/f1d23a7b9c84_add_probe_distribution_p1_10.py` (NEW) | `server_default='ring'` 回填历史行, `column_exists` idempotent guard |
| 3 | `channel-engine-service/app/models/hardware_pipeline_models.py` | 加 `ProbePosition` 模型 + `ChamberConfig.probe_positions` 字段 + `_check_distribution_consistency` validator; `distribution` Literal 跟 ChannelEgine 对齐 (`'sphere'` → `'multi-ring'`) |
| 4 | `channel-engine-service/app/api/endpoints/hardware_pipeline.py` `_build_chamber_config` | `probe_positions` 翻译成 ChannelEgine `ProbePosition` list 透传 |
| 5 | `api-service/app/services/channel_engine_client.py` | 加 `_build_probe_positions` (DB query Probe 表 + dedupe + fail-loud); `_build_payload` 用 `chamber.probe_distribution` + emit `probe_positions` 进 chamber_config |
| 6 | `api-service/tests/test_channel_engine_probe_positions.py` (NEW) | 15 tests: 6 helper unit + 3 `_build_payload` chamber_config wire + 5 microservice schema validator + 1 sphere-rename alignment |

**Acceptance**:

- ring (默认) chamber → payload `chamber_config` 不带 `probe_positions`,
  `distribution = "ring"`, 现有 8-probe ring lab smoke 完全不回归 (`tests/
  test_channel_engine_real_path.py` P0-7 payload-shape regression 7/7 不掉)
- custom chamber + 匹配 DB Probe → `payload.chamber_config.probe_positions`
  == 物理 probe 列表 (按 `probe_number` 顺序, dual-pol 按 (az, el) dedupe)
- multi-ring chamber 走 custom 同一路径
- 非 ring + DB 无 probe / probe 缺 azimuth / 物理 probe 数对不上
  `num_probes` → fail-loud (MIMO-First `ValueError`, microservice
  `ValidationError`)
- 15 new tests 全过 (P1-10) + existing `channel_engine_real_path` 8/8 不回归
- commissioning smoke + e2e_p06 + cal/dut gate (62 tests downstream) 全过

**Out of scope**:

- Roadmap mark P1-10 ✅ Done + Summary counts 同步 + P2-7 entry 完整 ✅ archive
  — 本 PR 是 in-progress, merge 后跟 P1-8/P1-9 pattern 一致用 docs catch-up
  chore PR 收口 (per memory `feedback_d_row_stale_this_pr_reflex.md`)
- GUI 端 chamber 编辑器加 `probe_distribution` 下拉 — P3 polish, 当前没
  chamber CRUD UI 触发场景
- ChannelEgine real-mode E2E 跑非 ring chamber — 本地有 `CHANNEL_ENGINE_PATH`
  clone 就可以手测, 但 CI 跑不了 (P0-7 已有同 pattern env-gated skip)
- measure phase 真消费 per-probe az/el — 现 ChannelEgine 内部已经做 (Phase 8
  `_calculate_weights_for_cluster` 读真 az), MIMO-First 这边只负责把数据
  透下去

**Status**: ✅ Done — PR #64 (merged 2026-05-19)
**Estimate**: 0.5 day (实际 ~0.5 day local impl + tests + 1 cross-repo schema
naming 对齐)

---

### P1-11 — 多子网仪表连接 (runbook + 可达性诊断) ✅ Done (PR #71)

**What**: 仪表默认 IP 分布在不同 `/24` 子网 (CAICT: F64 `192.168.0.x` / UXM +
SA `192.168.1.x`), 控制 Mac 单网卡一次只在一个子网, 操作员被迫手工切静态 IP ——
CAICT 两天现场相当一部分时间耗在这种来回上。本项**不改仪表 IP**, 从两层解决:
(1) 网络/OS 层 runbook (怎么让单网卡 PC 同时够到多子网); (2) 软件层可达性诊断
增强 (连不上时看得懂是子网问题还是仪表问题)。

**Why**: 这直接打中 CAICT 一天耗掉的那个阻塞 —— 控制电脑够不到全部仪表, first-call
就根本起不来。纯网络层是 ops, 但软件诊断把「甩一个 -1073807339 看不懂」变成
actionable, 跟 P1-8/9 fail-loud + P2-8 就绪带哲学一脉相承。现场拓扑确认是**同一
哑交换机、平坑 L2、无 VLAN 隔离** → 网络层最优解是「单网卡多 IP 别名」, 零硬件。

**两层方案**:
1. **网络/OS 层 (runbook, 不是代码)**: 见
   [`docs/guides/multi-subnet-instrument-network.md`](guides/multi-subnet-instrument-network.md)。
   - 方案 A 单网卡多 IP 别名 (平坑 L2 首选, 零硬件) ← CAICT 现场即此情形
   - 方案 B 三层交换机/路由器 (固定实验室/VLAN 分隔)
   - 方案 C 多物理网卡 (兜底) + 选型决策树 + 故障排查 (unreachable vs SCPI)
2. **软件层 (本 PR 代码)**: readiness 区分 `unreachable` (TCP preflight 挂, 多半
   子网不对) vs `scpi_fail` (TCP 通但 *IDN? 超时, 仪表/会话问题); 按 `/24` 子网
   聚合可达性 + actionable 提示, surfaced 进 P2-8 主控制台就绪带。

**Scope** (single PR):

| Step | File | What |
|---|---|---|
| 1 | `docs/guides/multi-subnet-instrument-network.md` (NEW) | runbook: 方案 A/B/C + 命令 + 决策树 + 故障排查 |
| 2 | `api-service/app/services/readiness.py` (+ `instrument_hal_service.py`) | DriverReadinessRow 用 tcp_preflight 区分 unreachable vs scpi_fail; 不再糊成单一 fail |
| 3 | `api-service/app/services/readiness.py` | 按 `/24` 子网聚合 + per-subnet reachable 汇总 + guidance 文案 |
| 4 | 契约同步 | readiness response schema 加 reachability 维度 → openapi.yaml + generate + service.ts + mock |
| 5 | `gui/src/features/Dashboard/ZoneReadiness.tsx` | 就绪带展示 per-subnet 可达性 + unreachable 提示链到 runbook |
| 6 | tests | unreachable vs scpi_fail 区分的回归测试 (现 `test_hal_tcp_preflight.py` 没覆盖 SCPI-timeout 分离) |

**Acceptance**:
- readiness 对「TCP 连不上」标 unreachable, 对「TCP 通但 IDN 超时」标 scpi_fail,
  二者状态/文案可区分 (memory `project_caict_network_topology` 的 ○ skipped vs ✗
  failed 诉求)
- 就绪带按子网分组显示哪些子网可达, 不可达给「按 runbook 方案 A 加别名」提示
- runbook 命令在 macOS + Linux 实测可用 (alias 配置 + nc 验证)
- 回归测试覆盖 SCPI-timeout vs network-unreachable 两条路径
- 现有 readiness 消费方 (P2-8 cockpit) 不回归

**Out of scope**:
- 给 InstrumentConnection 加 `source_ip`/`source_interface` 字段做源地址绑定 ——
  YAGNI: 网卡在目标子网有 IP 后 OS 自动选对源地址, 这字段多数时候没用, 纯 model
  churn; 出现具体需要再单开
- 实际网络硬件采购/布线 (方案 B/C 的物理部分) —— ops, 非代码

**Status**: ✅ Done — PR #71 (merged 2026-05-20)
**Estimate**: 1.5 day (runbook 0.5 + readiness 区分/聚合 0.5 + 契约+cockpit+测试 0.5)

---

### P1-12 — Silent-fallback audit: 兜底/未实测值显著标"未验证" ✅ Done (PR #79/#80/#81)

**What**: 主动 audit silent failure modes (roadmap 指定的本地工作) 挖到一批"无真实
校准/实测数据时静默套兜底值、还当干净 PASS / 实测呈现"的失败模式, 逐个改成在
precheck / 报告 / cockpit GUI **显著标"未验证(兜底值)"**。

**Why**: 跑完整 mock first-call (P0-6 + 在家彩排) 时暴露这些静默兜底——现场真测时
操作员会分不清"真测值"还是"没数据的兜底值"。「软件定义静区」的可信度恰恰压在
"合格性来自真实校准/实测"上, 静默兜底直接侵蚀这个前提。

**取向: mark 不 fail-loud** —— 本地/mock 彩排没有真实数据仍必须能跑完整链路;
标"未验证"既不阻断、又杜绝"把兜底当实测/合格"的静默失败。(real 模式的硬拦由
P1-8 precheck cal gate + P0-7 fail-fast 负责, 那是 fail-loud 的正确场景。)

| 静默兜底 | 修复 | PR |
|---|---|---|
| QZ ripple 无 ProbePattern → 套 0.7 dB 当 PASS | `quiet_zone_verified` 标 + 兜底时 message/GUI/报告显著标未验证 | #79 |
| reference TRP 无/mock SA → 套 23.5 dBm, 补偿因子也假 | `trp_verified` keyed on **real SA** (is_mock_driver); 覆盖 no-SA + mock-SA 两路 | #80 |
| measure 无 path-loss cert → RSRP 未补偿 (兜底 0 dB) | `path_loss_verified` 标 + warning "非校准值, 运行 CAL-01" | #81 |
| CE real-mode ImportError → 静默 1-tap mock .asc | **已由 P0-7 #56 fail-fast 修复** (启动期 fail-fast + 显式 `MOCK_ASC_MODE`/`mock_mode=True`); 非遗留项 | #56 |

**横切设计 (Codex on #80)**: report 渲染历史/迁移记录时, 缺失的 verified flag **绝不
默认 True** —— 从 provenance 推导 (quiet_zone_ripple_source / measurement_source /
path_loss_certificate_id); GUI 标记条件用 `!== true` 让 false 与缺失都显示未验证。
(进 memory candidate: 默认值偏向"无证据=未验证"的安全方向。)

**Drive-by 修复 (audit 副产物, out-of-roadmap bug fixes, 不单列 D-row)**: precheck
失败不显示原因 (#73) / mock 模式被 strict DUT 门误拦 → runtime mock-aware gate (#75,
Codex 推到 runtime 重判而非 create-time 冻结) / external_asc 选择 auto-fire 422 +
post-session 无路径输入 (#76/#77) / cockpit success_rate 0-1 vs 0-100 标度 (#70) /
完整 mock first-call 默认 config 回归守卫 (#78)。

**Status**: ✅ Done — PR #79 (QZ) + #80 (reference TRP) + #81 (path-loss), 均 merged
2026-05-25; 第四项 (CE real-mode) 早由 P0-7 #56 覆盖。
**Estimate**: ~1.5 day (3 marking PR + backward-compat + 测试)

---

### P1-13 — 子网可达性假阳性: preflight 走 VISA endpoint + "未探测"三态 ✅ Done (PR #83)

**What**: 操作员 manual 测试 cockpit 就绪带时发现: Mac 单网卡在 WiFi `192.168.1.98/24`,
本该最可达的 `1.x` 显示不可达, 而无路由的 `0.x` / `100.x` 反而"可达" —— 现象完全反了。
是 P1-11 子网可达性的两个洞 (audit 自己挖出来的回归):

1. preflight gate 只在 `controller_ip` + `port` 两列都填时跑。很多 binding 把 IP 存在
   VISA endpoint 串里 (那两列空) → preflight **被跳过** → connect 直接失败 → 归
   `fail_kind=scpi` (而非 network) → 子网无 network-fail。
2. 子网判据把"没有 network-fail"当"可达" → never-probed 的子网被误标**可达**。

**Why**: 假"可达"现场会误导操作员 —— 以为网络通了去调 SCPI, 实际根本没路由。可达性
信号必须诚实区分"探到可达 / 探到不可达 / 没探过"。

**修复 (A 根治 + B 防御)**:
- **A**: `preflight_target(conn)` —— `controller_ip/port` 缺失时从 VISA/endpoint 串
  解析 IPv4(+端口, 默认 5025; 只 HOST 定网络可达性)。所有能定位 IP 的仪表都被探;
  解析不出 (hostname) → 跳过 → "未探测"。
- **B**: `DriverReadinessRow.network_reachable` (True/False/None) + `SubnetReachability
  .probed`; `build_subnet_reachability` 三态: 任一 dead→不可达; 否则有 alive→可达;
  全 None→**未探测**(不再假可达)。mock 模式不探网络 → 全"未探测"(更诚实)。
- 契约同步 (openapi+generate+types+mock) + GUI SubnetSection 三态 (灰❔/绿/红)。

**Status**: ✅ Done — PR #83 (merged 2026-05-25)
**Estimate**: ~0.5 day (preflight 解析 + 三态 + 契约 + GUI + 测试)

---

### P1-14 — 硬件健康探针对 mock 驱动给出可操作拒绝信息 ✅ Done (PR #86)

**What**: 操作员现场 manual 调试时, HAL 在 mock 模式下从诊断序列跑 F64 Probe, 撞到
`Identity check failed: IDN='', SYST:INFO=''; expected any of ('PROPSIM','F8800')`
—— 对操作员毫无指引的报错。根因: 硬件探针把 mock 驱动返回的空/占位值当真机应答去校验
`*IDN?`/`SYST:INFO?`, 要么静默"通过"(无意义), 要么以看不懂的字符串失败。只有
`aerotech_positioner_health` 之前有自己的 inline mock guard, 其余探针都没有。

**Why**: 探针在 mock 下报"硬件身份不符"是答非所问 —— 真正问题是"你在 mock 模式跑了
一个只对真机有意义的探针"。诚实信号应该是"切 real 连真机再跑", 而不是一个 IDN 校验失败。

**修复**:
- `protocol.py` 新增共享 `mock_driver_refusal_summary(category, driver)`: 驱动类名以
  `Mock` 开头返回中文拒绝说明 (本探针针对真实硬件、对 mock 无意义、切 real 连真机后再跑),
  否则 `None`。判定沿用 aerotech 已有的 name-based 方式 (Mock* 家族之外一律视为 real)。
- 5 个硬件探针 (`propsim_f64` / `propsim_fs16` / `vna_ena` / `uxm_scpi_compatibility`
  / `baseStation_attach_check`) 在"无驱动"返回后插入该 guard; aerotech 已有 inline guard 不动。
- 新增 2 个测试 (F64 + uxm) 注入 `Mock*` 驱动, 断言 summary 含 "mock 驱动"/"real 模式"
  且不含 "Identity check failed"。

**Why P1-14**: 跟 P1-12/P1-13 同源 —— 都是跑完整 mock first-call / manual 测试时挖到的
可用性洞。承接 Current Focus 段"下一轮若再 audit/manual 测试挖到东西 = candidate for
P1-14"的占位。

**Status**: ✅ Done — PR #86 (merged 2026-05-26)
**Estimate**: ~0.25 day (helper + 5 探针 guard + 2 测试)

---

### P1-15 — preflight canary 负对照: 识破代理/VPN 伪造的子网"可达" ✅ Done (PR #88)

**What**: 操作员 manual 测试 cockpit: real 模式、**实际无任何设备**, 子网可达性却把三个
子网全标"✅可达", 同时所有驱动报"SCPI 无响应" —— 自相矛盾。根因不是 P1-13 那个洞(已修),
而是更深一层: `tcp_preflight` 的 "connect 成功或被 RST 拒绝 = 主机在线" 启发式, 在链路上有
**透明代理 / 公司 VPN / 强制门户 / blackhole 网关** 时被骗 —— 它们替不可路由的目标 IP 应答
SYN, 于是每个 IP 都"alive"、每个子网都"可达"。实测连 RFC5737 TEST-NET 死地址都返回 alive。

**Why**: 跟 P1-13 同一类假"可达", 但 P1-13 修的是"VISA-only binding 被跳过 preflight →
从没探过 → 默认可达"; 没碰"preflight 的 connect-or-refused 启发式在代理环境下本身不可信"。
假"可达"会误导现场操作员去调 SCPI, 实际网络层在说谎。**对 5/27 现场直接相关**: 现场 Mac
若挂 VPN/代理, 子网面板会(正确地)拒绝给可达性判定。

**修复 (canary 负对照)**:
- `detect_preflight_trustworthy()`: 并发探一组保证不可路由的 canary 地址 (RFC5737
  TEST-NET-1/2)。任一 canary "alive" → 网络在说谎 → 返回 False(不可信); 全 dead → True。
- `_initialize_from_db`: 首个 real preflight 前**惰性**跑一次 canary(纯 mock init 不付成本),
  缓存整轮。不可信时整体跳过 preflight, `host_reachable` 留 None → 子网回落"未探测", 而非假
  "可达"; connect 照常跑(仍能区分 ok/scpi)。
- `build_subnet_reachability(network_trustworthy=...)`: 不可信时"未探测"提示改成点名真正
  原因(透明代理/VPN)。复用现有 `probed=false` 三态渲染, **无契约/GUI 改动**。

**Why P1-15**: 跟 P1-12/13/14 同源 —— 跑完整 mock first-call / manual 测试挖到的 readiness
假阳性。承接 Current Focus 段"下一轮 manual 挖到东西 = candidate for P1-15"的占位。

**Status**: ✅ Done — PR #88 (merged 2026-05-26)
**Estimate**: ~0.5 day (canary + 惰性接入 + 三态 hint + 6 测试)

---

### P1-16 — backend scpi-command 端点 slow-op desync (timeout_ms 透传) ✅ Done (PR #99)

**What**: `POST /api/v1/instruments/{cat}/scpi-command` 端点不把 `timeout_ms` 传给
`driver._query` → 慢操作 (F64 加载后 `*OPC?`、`INP:LEV:MEAS?` / `INP:LEV:AUTOSET` 等几秒级命令)
用默认短超时 → 超时返回 → 迟到的真响应串进**下一次**读取 (desync 级联), 后续每条 command 都读到
上一条的回包。直连 socket (LF 逐字节读帧) 无此问题。

**Why P1**: 不硬阻断 first-call (现场有 `/tmp/f64ctl.py` 直连 workaround), 但让 GUI/后端的 SCPI
通道对任何慢操作都不可靠 —— 5/27 现场正是它挡住了"经后端可靠设置 F64 输入参考"(P0-8 现场半没闭环的
直接原因之一)。修了之后 P0-8 的输入参考 step 才能经后端稳定下发。

**Scope**: scpi-command 端点把 `timeout_ms` (或 per-command 超时) 透传到 `driver._query`; 慢操作
给足超时; 必要时读前 drain 残留帧。**来源**: 2026-05-27 现场, 见 [morning-log](site-debug/2026-05-27-morning-log.md) §10.5。

**Acceptance**: 经后端连发 F64 `*OPC?` (加载后) + `INP:LEV:AUTOSET` + `SYST:ERR?`, 每条都读到
**自己**的回包, 无错位; 慢操作不被默认短超时截断。

**Status**: ✅ Done — PR #99 (merged 2026-05-29). reconcile: 本条 status 之前 stale 写 in-progress, #99 已 merged。
**Estimate**: ~0.5 day

---

### P1-17 — UXM fresh-start 配置落地 (对称 P0-8: 现场不再临时配 UXM) ✅ 本地半 Done (PR #107), 🚧 现场半 on-site

**What**: 给 UXM 加"默认测试参数集 fresh-start 自动应用"那一层, 让 UXM 从开机/重连到就位是可复现的, 消除现场"快速路"(手动前面板点 / 临时 SCPI)。对称 P0-8 对 F64 做的 (默认 .smu 自动加载)。

**Why P1**: 5/27 现场 UXM 走了快速路 —— 能跑通但靠手动配, 没 offline 可复现入口。下次现场要么重复手动 (慢 + 易漏), 要么出发前把"参数集 + 自动应用"备好、现场只验硬件。这是 first-call repeatability (P1-4) 的前提, 也是"现场不临时配"铁律对 UXM 的落实。

**现状盘点 (2026-05-29 调研)**:
- ✅ 基建零件齐: `load_state_file()` (UXM .state 一键 recall) + Topology Profile (P2-1, DB 持久化参数集 cell/MIMO/power/FRC, 7 内置模板) + Test App 自动检测 (`SYSTem:APPLication:NAME?`) + `MIMO_PORT_PRESETS`。
- ✅ auto-apply 机制有: HAL reload 时若 binding 的 `connection_params["topology_profile_id"]` 已设, 自动 `apply_topology_profile()` (instrument_hal_service.py:719)。
- ❌ **缺"默认 profile"**: fresh-start 时若 binding 没设 profile_id, 不 apply 任何基线 → 空配置。对称 F64 有 `F64_DEFAULT_EMULATION_FILE` 自动加载, UXM 无对称默认。
- ❓ **remote .state 盘点空白**: 现场 UXM 上 save 过哪些 .state、路径、内容 —— 未盘点 (见 U-7)。

**Scope (本地半, 出发前)**:

| Step | Subject |
|------|---------|
| 1 | 默认 Topology Profile: 标一个内置 profile 为 default (e.g. 3600M/N78 4x4 对齐 F64 默认 .smu), fresh-start binding 无显式 profile 时自动 apply (对称 P0-8 Step 4 默认 .smu + connection_params override) |
| 2 | .state 路径 override: connection_params 支持 `default_state_file`, `configure()` 优先 recall (机制已有 `load_state_file`, 补默认 + override 链) |
| 3 | fresh-start 编排 runbook: UXM 开机 → Test App 检测 → 默认参数集应用 的可复现文档 |
| 4 | 单测: 默认 profile fresh-start 自动 apply / override 优先级 / 无 profile 不再空配 |

**Acceptance**:
- **本地半**: 全新 binding (无显式 profile) HAL reload → 自动 apply 默认参数集 (3600M/N78 对齐 F64); connection_params override 默认 profile / state_file 生效; 单测全过 (mock UXM)。
- **现场半 (下次现场)**: real UXM fresh-start 一键就位 (cell live + 对齐 F64 频率/MIMO) 无需手动前面板; .state 盘点完成 (U-7)。

**依赖**: P2-1 (✅ Done)。关联: U-7 (参数集真值), P0-5 (DUT attach 用 UXM), P1-4 (repeatability)。
**Status**: ✅ 本地半 Done — PR #107 (默认 Topology Profile fresh-start 自动应用, 对齐 F64 3600M/N78; Codex follow-up 36e9d07 给 3600 profile 显式设 `arfcn=640000`)。🚧 现场半待下次现场: real UXM fresh-start 一键就位 (cell live + 对齐 F64 频率/MIMO, 无需手动前面板) + remote `.state` 盘点 (U-7)。
**Estimate**: 本地 ~1.5 day ✅ + 现场 ~0.5 day。

---

### P1-18 — F64 频率下发正修 (3500 覆盖 bug 驱动侧正解 + 真值比对层) ✅ Done (2026-07-04 #196)

> 收口: ①-④ 全落地 — Step 4 缺省不写 CENT (+None 边缘 + 缺省重载复位 programmed +
> configure 直通); `smu_project` 工程 INI 真值解析器进 repo (P2-18 地基); 三 fallback
> 调用点审计落款; 10 用例。measure 桥接保留 (TestCase 显式驱动是路径 B 正路)。

**What**: ① 驱动 `set_channel_model` Step 4 参数缺省时**不写 CENT**(保留 .smu 工程频率), 写了必置 `_center_freq_programmed`(上报=下发); ② 现场热修 2c6f6b1(measure sim_rules 桥接 `center_frequency_mhz`)正规化 + 单测(TestCase 频率显式下发是正路, EMQuest 同构印证); ③ 现场热修 122eeae(频率一致性网 loose 档软化)正规化 + 加"下发后真值比对"层 —— CENT 回读在此 ATE 不可靠, 预期真值源 = .smu 工程解析值(`CenterFrequency` INI 键, 解析器已验证); ④ `parse_smu_center_freq_mhz` 文件名 fallback 全调用点审计(厂商文件名系统性说谎, 只可作 loose 提示不可作真值)。

**Why P1**: 当日最重 bug(⭐⭐⭐)的正修。不修则任何不带显式频率的加载路径仍写默认 3500 冲掉工程频率, 输入测量/AUTOSET/吞吐全链错位。

**Acceptance**: 参数缺省加载后 CENT=工程值(mock 断言不发 CENT 写); 显式频率路径 programmed 标志置位且上报一致; 两热修有单测锁定; greenfield 全链 mock run 频率一致性网过。
**来源**: [`guides/onsite-tasks-20260703.md`](guides/onsite-tasks-20260703.md) discovered ⭐⭐⭐ 条 + "文件名≠工程真值"条。**Estimate**: ~1 day。

---

### P1-19 — UXM set_cell_config 编排正修 (OFF→配→ON + 回读对账 + SSB 三件套) ✅ Done (2026-07-04 #195)

> 收口: ①-⑤ 全落地 + EMQuest 10-band 基线表进 repo (`app/data/nr_band_baselines.json`)。
> Codex 六轮 3P1+4P2 全修 (小区恢复 finally / inst0 重定向可达且 host 复用资源串 / 5G 文本态
> 反向判定 / OFF 写布尔契约 / _duplex 缓存绑 band / **执行链消费布尔契约** — measure Phase 2
> 与诊断序列 `_step` 对 False fail-loud)。mock 单测 43 用例; 真机验收待下次现场。

**What**: ① BW 等 ON 态禁改参数的 **OFF→配→ON 编排**(-221 实证) + BW 值令牌形式(`BW100`) + TDD 下跳过 UL:BW(跟随 DL); ② `band` None-guard(键在值 None 视同缺失走推断, feedback_endpoint_null_field_cartesian)+ duplex/tdd_pattern/sched_algo 同型审计; ③ **写后回读对账 fail-loud**(回读=echo 设置值 ≠ 生效, 但 ARFCN/BW/POWer 回读今日实证可用, 对账仍有值); ④ **SSB 三件套下发/核对能力**(SSB ARFCN / PointA / OffsetToCarrier) —— EMQuest prm 破译出的 band→(dl_arfcn/ssb_arfcn/point_a/offset/duplex) 权威查表进 repo 数据文件(10 band 全集在 onsite 文档); ⑤ Platform→hislip2 重定向条件补 `inst0`(或绑定钉死 TAF 端点文档化)。

**Why P1**: attach 与吞吐的 UXM 配置全自动化前提; 今日全部序列已现场实证(3550→3600→基线 636666 三轮重配全人肉), 不落驱动则下次现场重复人肉。

**Acceptance**: mock UXM 单测覆盖 OFF→配→ON / 令牌形式 / None-guard / 回读对账 fail-loud / SSB 查表下发; 真机验收(下次现场)= 一次 set_cell_config 从任意起始态收敛到目标基线并回读全绿。
**来源**: onsite 文档 discovered "BW 卡 40 根因"/"None.upper 根因已闭环"/"EMQuest prm 全集"条。**Estimate**: ~1.5 day。

---

### P1-20 — Aerotech 转台断连韧性 (move 前懒重连) ✅ Done (2026-07-03 #194)

> 收口: move_to/get_position/reset 前 transport 探活 + 懒重连一次; mock
> 断连注入自愈 + 4 方位序列单测过。现场验收 (完整 4 方位零人工干预) 随★核心。

**What**: 驱动 `move_to`/`get_position`/`reset` 前检测 transport closed → 自动重连一次再执行(懒重连); 可选周期 keepalive poke(≤5s, 实测断连窗口 <11s); mock transport 单测(断连→自愈)。

**Why P1**: 实测 move 完成后 ~10s 空闲连接即被控制器掐(比 5/27 记录的 ~2min 严得多); 4 方位吞吐的方位间隔(~1min 测量)必踩 → **方位 2 的 move 必失败 = ★核心 gate 直接阻塞**。今日 30° 步进 12/12 验证靠"每步前重载 HAL"人肉绕行。最小修(~半天), 收益最直接。

**Acceptance**: mock 断连注入后 move 自愈成功; 集成层 4 方位序列(方位间 sleep 60s mock)全过; 现场验收 = 完整 4 方位 run 转台零人工干预。
**来源**: onsite 文档 discovered "转台验证"条。**Estimate**: ~0.5 day。

---

### P1-21 — HAL 会话卫生 (命令互斥 + 超时排水恢复 + 延迟应答语义) ✅ Done (2026-07-04 #197)

> 收口: ①-④ 全落地 — F64/FS16 `_scpi_lock` 互斥 (并发度探针=1) / 超时 SYST:ERR?
> 排水 (读到 0 止, 上限 4, 原异常照抛) / `_inp_meas_timeout_ms` 动态超时 /
> `output_powers_frozen` metrics 标注。8 用例; "measure 期间暂停 broadcaster"
> 备选不再需要 (锁即互斥)。真机验收 (监控开着跑测量零串线) 待下次现场。

**What**: ① per-instrument asyncio 命令锁 —— monitoring broadcaster 与测量序列共用 F64 单 socket 无互斥是当日 P1 级根因(应答串线/错位/僵死全家桶), 或 measure 期间暂停 broadcaster; ② F64 超时后**轻量恢复策略**: 自动排水 SYST:ERR? N 条 + 功能查询验证(实测 2 条即净), 失败才升级重载(替代今日"超时必重载 HAL"人肉纪律; UXM 丝滑度测试实证恢复成本极低); ③ INP 测量族 deferred-response 语义适配(结果就绪才回, 固定超时读法必错位); ④ F64 输出功率测量 STOPPED 态冻结语义(驱动注释 + cockpit 监控层"停止态读数不可信"标注)。

**Why P1**: 今日全天串线/wedge 的系统性正解; 不修则下次现场仍靠"关主控台页 + 每次重载"人肉纪律, 且 cockpit 监控与测量互斥的产品矛盾未解。

**Acceptance**: 并发 broadcaster+测量序列 mock 压测零串线; 超时注入后自动恢复(不重载)成功率量化; 单测锁定。
**来源**: onsite 文档 discovered "监控广播器争用 P1"/"UXM 丝滑度"/"INP 延迟应答"/"输出测量冻结"条。**Estimate**: ~1.5 day。

---

### P1-22 — 报告可信化（死键谓词 + CJK 字体 + 模板残留）✅ Done (2026-08-01)

**What**: `executors/report.py` 死键母题三站点一次收口（`overall_pass` 恒 False 致自动报告
恒 failed/0.0%、透传/`pass_criteria_summary` 死站点；precheck 站点经内审核实写方健康不动）+
`pdf_generator.py` 注册 CJK 字体（中文全豆腐块）+ `Test Plan: N/A` 计划链残留 3 处。
**Why P1**: 报告是测试系统最终交付物，当前对成功的测试说谎（恒报 failed）。
**设计稿**: [`design/p1-22-report-trustworthy-fix.md`](design/p1-22-report-trustworthy-fix.md)（含修法红线四条）。
**来源**: Discovered 区 `[discovered 2026-08-01 during ARCH-1 S6 总验]` 报告条 + CJK 条（详细根因在彼处，[→ P1-22] 已标）。**Estimate**: ~1 day。
**收口 (2026-08-01)**: 谓词换 `validation_pass` 列（缺列兜 verdict 三值，未知保守 failed；两红线变异实跑：死键回退 2 红（含列优先判别用例）/ completed 谓词 4 红含 KPI-FAIL 谎报通过卫兵（初报 4 红系 FAILED 计数未锚定 short summary 行双计，内审 F2 纠正））；CJK 三族收敛单一 `CJK_FONT` 常量（样式表遍历 + Table FONTNAME + 显式位点，源码零 Helvetica 由存在性门守）；封面 Test Plan 行按报告类型分流（计划类保留真名，execution 类显示「来源」）。S6 真执行重生报告实证：中文标题可读 + pass 口径为真值（mock KPI FAIL 如实报 failed）。新文件 12 单测（+既有回归 4）+ 全量 2775 过。

### P1-23 — 现场协议补 P0-8 gate（纯文档，行前必办）✅ Done (2026-08-01)

**What**: `guides/on-site-debug-protocol.md` 补 P0-8 执行 gate（两个设计决策：塞哪个 Phase /
gate 按 DUT attach 依赖拆两半）+ 同源 stale 句清理（"P0-4→P0-3→P0-5 推进"已过时）。
**Why P1**: 当前 checklist 走完会漏 F64 验证 —— 比没有 checklist 更危险，不能带到下次出发。
**来源**: Discovered 区 `[discovered 2026-07-30 during ARCH-1 roadmap 补记]` 条（[→ P1-23] 已标）。**Estimate**: ~0.5 day。
**收口 (2026-08-01)**: 两个设计决策落定 —— ①P0-8 独立成 **Phase 1.5**（比握手重、不依赖 SA/校准，排 Phase 1 后即验；与 §7 能力探测清单显式区分"验已知 vs 探未知"）；②gate 拆两半 —— **P0-8a**（load→run→改参 0 error + 输入口变绿）挂 Phase 1.5，**P0-8b**（DL 非 0% ACK，依赖 DUT）挂 Phase 4 gate 清单。stale 句根治：开篇配套句与铁律 2 的硬编码 P0 队列**换源指向 Blocked on hardware 表**（硬编码已两次 stale，队列永远查表）。


### P1-24 — `propsim_f64_p08_gate` 诊断序列（P0-8a 唯一合法载体，出发前硬门槛）✅ Done（本 PR）

**What**: 覆盖 load→AUTOSET→run→改参→两态电平判据的 checked-in 诊断序列。七点要求（Discovered 原条 [→ P1-24] 已标）：①手册有据 + 生产驱动在用命令（涉 F64 SCPI，**动手前查 NotebookLM PROPSIM notebook**）②前置激活 UXM 满 RB DL（CE↔BS 协调；⚠ 原文"无信号 `INP:LEV:MEAS?` 返 -300"经手册查证为**哨兵语义不实** —— -300 是错误队列里的设备错误码（2026-05-27 现场实证），不是查询返回值，判据 = 队列出现测量失败错误，NotebookLM 2026-08-01）③每步后读错误队列零残留 ④电平按合法范围真判定 ⑤bypass 态电平窗口复验（同窗口）⑥输入参考 AUTOSET 闭环 —— **stopped 态命令排 GO 前**（§20.4.4.7，同为本片对协议的时序纠错），收敛判定 = `SYST:STAT?`（clipping/cut-off 正确读法）⑦mock 跑通列入出发前门槛。
**Why P1**: 现有两序列干不了这活，现场又禁临时脚本 —— 没有它下次现场做不了 P0-8a。

**落地（本 PR）**: 设计稿 [`design/p1-24-f64-p08-gate-sequence.md`](design/p1-24-f64-p08-gate-sequence.md)（§0 手册实证表 + §0.4 实现期修正）；序列复用生产原子（`load_local_scenario`/`autoset_inputs`/`start_emulation`/`set_bypass_mode`/`set_output_gain`/`measure_input`），新增 SCPI 仅 `OUTP:GAIN:CH?`/`OUTP:GAIN:LIM?`（§20.4.5.7/8，NotebookLM 过手册）；退 bypass **不假设自动续跑**（手册说续、2026-07-03 实证不续，两种固件行为都兜并如实归档）；收尾 GOS 留驻不发 CLOSE（绕驱动直发会让身份缓存 stale）。D-1 = 真驱动+假 SCPI 层行为门 18 测 + 5 变异实跑全红（AUTOSET 时序 / 不带病 GO / 增益回读 / 显式 GO 恢复 / 零残留）。真机行为（AUTOSET 收敛、bypass 电平窗口）只能现场验 —— 序列是载体不是替身。

### P1-25 — GUI 主控台"系统状态"面板恒空修复 + api.ts 手写镜像审计 ✅（2026-08-02 完成）

**What（原定）**: `App.tsx` 读 `dashboardData?.systemStatus`（手写 camel 三键，`gui/src/types/api.ts`）而 live `/api/v1/dashboard` 返回 snake 四键 → 面板恒 undefined 走空态。修 = App.tsx/api.ts 换 live 键形态；同一把尺子过 api.ts 其余手写镜像类型 + 清理死导出 `InstrumentCategoryResponse`。**来源**: P3-17 内审 F2（[→ P1-25] 已标）。
**Why P1**: 用户天天看的主控台面板对真后端是坏的 —— 可见度最高的存量缺陷。

**⚠️ 开工后推翻的前提**：条目写的"换 live 键形态"**这条路不存在** —— 后端真值源 `app/schemas/dashboard.py` 的 `DashboardResponse` **从来没有 `system_status` 字段**（只有 summary / live_metrics / active_alerts / recent_tests），openapi 里的 `SystemStatusItem` 是零响应引用的孤儿 schema。也就是说那个面板在 live API 里**没有数据源**可换。

**实际落地（只做目的那件事）**：① 删掉主控台「系统快照」面板 —— 它是 P2-8 之前的遗留，驾驶舱 `ZoneReadiness` 早已用正确数据源 `/instruments/hal/readiness` 做了同一件事且更全；② 删掉随之悬空的 `/dashboard` 查询、以及 `hardwareOnline` / `preferMockExecution` / 强制回落 useEffect / `handleExecutionPreferenceChange` 这条**死机器**（`onExecutionModeChange` 从未传给 `Monitoring`，`preferMockExecution` 初值 true ⇒ `executionMode` 恒 `'mock'`，`hardwareOnline` 取什么值都观察不到 —— 对它做变异连红都红不了），`executionMode` 按常量 `'mock'` 固定，**与改动前逐位同行为**；③ 删死导出 `InstrumentCategoryResponse`。

**⚠️ 内审否掉的越界（本片一度做了，已全部撤回）**：曾把 `executionMode` 换源到 readiness 判"真仪表 vs mock"。内审 F1 指出那两个徽章挂在**演示回放播放器**上（同卡片副标题：「演示回放 —— 真实测试请到「测试管理 → 测试用例库」执行用例」，数据源 `/tests/demo-run` 实测 404 且 query `enabled:false`）——按 HAL 真假去判，现场全真部署会把演示脚本标成绿色「真实执行」，比恒 `'mock'` 更糟；F2 进一步指出该判据在 `detail` 缺省/类改名时一律倒向 `real`（代价高的那侧），且后端权威判据是 `instrument_hal_service.py` 的 `is_mock_driver()`（`isinstance` + `_MOCK_DRIVER_CLASSES` allowlist），不是我引的 `api/instrument.py` 里那份 `startswith("Mock")` **副本**。同时撤回的还有 `DashboardResponse` 的形态修正 —— 那次修正自己引入了新谎（`recent_tests` 声明成 `RecentTest{id,name,dut,result,date}`，而 live 元素是 `{id,plan_name,status,executed_at,duration_minutes}`，即 `/test-executions/recent` 的形状），与本片正在消灭的母题一模一样。该类型现与另外三个"说谎但无人消费"的同类一起进 Discovered，同等处置。

**审计结果（18 组 手写类型 × live 端点）**：6 组有问题 —— 4 组形态错但 fetch 零消费（含 `DashboardResponse`，全进 Discovered）、1 组是后端路由顺序 bug（`/dashboard/alerts/summary` 恒 422，进 Discovered）、1 组端点 404 但查询已带 `enabled:false` 并注释申明（不动）。⚠️ **"其余 12 组 OK"这个结论不可信** —— 尺子是"手写类型顶层键 ⊆ live 顶层键"，只看一层：内审 F5 实证 `/monitoring/feeds` 被判 OK 但元素形态全错（`name` vs `label`、number vs string），已单列 Discovered。

**验证**：编译门 `npm run build` ✓；运行门浏览器实测 —— 面板与"暂无数据"空态消失、主控台其余内容完好；`executionMode` 为常量故无行为可变异（行为与改前逐位一致，这正是收敛的目的）。内审全量 2830 passed / 4 skipped、eslint 改动行零命中。

### P1-26 — GUI 改频同步 component_carriers（**GUI 写侧**收口）✅（2026-08-03 完成）

**What**: factory `model_dump` 落库自带 CC，validator 在 CC 非空时忽略顶层频率（measure 权威 = CC[0]），而 GUI `MIMOOTAConfigForm` 只写顶层 → 顶层与 CC[0] 漂移时执行按旧 PCell 跑。P3-14 已让显示与执行同源（CC[0] 优先），本片修 **GUI 写侧**（二选一里选了「写侧同步 CC[0]」，未选「PATCH 时 drop CC 重构造」—— 后者会静默抹掉真 CA 用例的 SCell）。**来源**: Codex #262 R1（[→ P1-26] 已标）。
**Why P1**: "用户以为改了新频、硬件跑旧频"是现场误导级；P2-11 一致性门兜不住"CC[0] 旧频恰与 SCD 一致"的形态。

**链条实证（全部打在真实生效端，非推断）**：GUI `TestCaseEditModal` 把 `configuration` **整包**读进来（含 CC）→ `MIMOOTAConfigForm` 的频率框绑的是**顶层** `frequency_hz`，CC 不在编辑器中暴露 → 提交整包回传（CC 原样带旧频）→ 服务层 `setattr(test_case, 'configuration', value)` **整体替换**不合并 → schema `_resolve_component_carriers()` 在 CC 非空时**只归一化 role，从不拿顶层校 CC[0]** → `measure.py` 取 `component_carriers[0]` 当 PCell 下发。

**可达性（我数错过两次，最终判据是机制不是计数）**：① 初次抽查 8 个用例得"8/8 已落库" —— 那批全是执行快照，错；② 改按"名字含执行/Session"分类得"可编辑 17 个中 14 个" —— **仍错**，那 14 个是 `created_by='test_case_runner'` 的执行快照，GUI 根本打不开（内审 F1 纠正）。③ **正确判据**：GUI 用例库硬编码只列模板（`TestCaseLibrary.tsx` 的 `listTestCases(0, 500, filterType, true)`），本机 **28 个模板 / 12 个 MIMO，带 CC 的 0 个** —— 所以**本机当前 GUI 路径不可达**。但缺陷本身可达且会随新部署出现：bootstrap 种子经 `legacy_to_mimo_ota_config` → `MIMOOTAConfiguration(...).model_dump()` 落库，**新部署的模板自带 CC**；本机模板是 Phase 2g 之前种下的存量（种子按名幂等跳过、不回补）。

**落地**：新增 `updateCarrierField(key, next)`，频率 / 带宽 / 子载波间隔三个框写顶层的**同时**同步 PCell = `component_carriers[0]`。值形态四种分别处理：`undefined`/`null`/`[]` → **不凭空造 CC**，只写顶层交给后端 validator 构造；`[pcell]` → 两者一起改；`[pcell, ...scells]` → **只改 pcell**（SCell 是独立载波）。`next` 非有效数字（清空输入框）时**两边都不写、模型保持原值**（内审 F2 纠正：早先写的「会 422」是**假的** —— `TestCaseUpdate.configuration` 是 `Dict[str, Any]`、`update_test_case` 是 `setattr` 整体替换，**全链零校验**，实测掉键返回 **200**；顶层键一丢就落到 schema 默认 3.5e9 与 CC[0] 分叉，而 `.asc` 合成 / 路损查表 / 方向图增益 / reference 按顶层、UXM·F64 按 CC[0]、一致性网参考又正是 CC[0] → **四方分叉零告警**）。

**`band` 一律不动**：本片一度改成「改频顺带删 band」让驱动按新频重推，**被 Codex #271 P1 否掉并撤回** —— `FREQ_TO_BAND_MAP` 只覆盖 7 个区间且**未命中硬回落 `("N78","TDD")`**，且该表 per-lab 可被 `InstrumentCategory.config` 覆盖，**前端没有资格判断推断能不能成功**。详见 Discovered 同日条。

**验证**：编译门 `npm run build` ✓。**运行门 = 用户在真实 GUI 里操作**，完整步骤（**第 1 步是承重的，早先漏写导致按原文不可复现**，内审 F1 纠正）：
1. **先用 API 给模板 `one shot` (cad57d35) 注入 CC**（本机模板原本 `CC=null`，不注入的话点了也只会走"CC 为空"的早退分支，读库根本没有 CC[0] 这一项）：`PATCH configuration` 设 `frequency_hz=3.5e9` + `component_carriers=[{frequency_hz:3.5e9, bandwidth_mhz:100, subcarrier_spacing_khz:30, role:'pcell'}]`；
2. GUI：测试管理 → 用例库 → `one shot` → 编辑 → 中心频率 3500 → **3600** → 保存；
3. 读库：`顶层=3600000000 / CC[0]=3600000000` **同步** ✅。

用户第二次点击（`CC[0]` 带 `band:"n78"`，3500→3400）同样确认同步、且 `role`/`scs`/`bw` 未被误动 ✅。⚠️ 那一轮跑的是**撤回前**的代码（当时会删 band，实测 band 确实消失）；`band` 删除已被 Codex #271 P1 否掉撤回，**现版本保持 band 不变、未重跑**，如实申报。另：`next` 无效时的早退分支（纯 `return`，不触发 `onChange`）也只过了编译门与代码审阅。

**对照**：用旧代码实际产生的 payload 形态（`{...value, frequency_hz: next}`，CC 一字不动）复现 → `顶层=3700000000 / CC[0]=3600000000`，**漂移 100 MHz** 🔴。实验用例事后逐字段还原（`逐字段一致=True`）。

### P1-27 — P1-8 校准门拒 mock cert（provenance + real 模式 strict 拒）✅（2026-08-11 本地完成）

**What**: cal 记录带 `use_mock` provenance 标记；real 模式 precheck strict 门拒 mock cert（门现在只查存在/频率/时效）。**来源**: 2026-07-03 现场实证（[→ P1-27] 已标）—— mock 路损 cert 在 real 模式 `cal_pass: true`，真测静默应用 mock 补偿值。
**Why P1**: 现场实证穿透，下次现场前必修（runtime-gate-not-frozen-snapshot 同母题）。

**收口**：`ProbePathLossCalibration.use_mock` 采用 `False=真仪器 / True=模拟 / NULL=历史来源未知` 三态，迁移不设默认值、不回填旧行；两条 live 生成路径均在落库时写入来源，latest API、precheck 与 measure payload 均显式暴露。真实 CE + strict 只允许来源明确为 real、状态为 valid 且 `valid_until > now` 的记录；真实执行从 explicit-real 白名单内选最新证书，更新的 mock 演练证书不会遮住仍有效的真实证书；mock CE 则保留 mock 证书以演练完整校准链。missing / expired / mock / unknown 在 PRECHECK 与单阶段 MEASURE 的任何仪表 connect/SCPI 下发前 fail-loud。显式 bypass 只允许无路损补偿调试，不能应用不可信证书。ASC 三条生成路径只消费 MEASURE 已筛选的证书，TRP/TIS 补偿、校准状态与校准报告采用同一白名单。历史 MIMO execution 即使旧 `path_loss_verified=true`，缺少 `path_loss_calibration_use_mock=false` 仍重生成成 UNKNOWN/N/A；旧报告详情与 PDF 在重生成前 409，新 builder 以 trust schema 区分“可审计 UNKNOWN”与“可作正式结论”，且创建入口会剥离客户端伪造的 trust 字段，只有服务端重建可写入。模拟、未知或过期证书不进入真实 KPI、有效状态或正式报告分母。最新相关回归（含 commissioning、readiness、历史报告、全仓规则门）**256 passed**；SQLite migration 已完成 f6→head→f6→head 往返且仅一条 Alembic head。

### P1-28 — 「当前暗室」双真值源收口 ✅（2026-08-02 拍板；2026-08-07 完成）

**What**: `ChamberConfiguration.is_active`（activate 端点强制唯一的"当前工作暗室"单选器）与 `LabProfile.chamber_config_id`（lab 绑定）是两个同名不同义的真值源，之间**零约束零同步**；消费方分两派（`commissioning`/`mimo_ota.factory`/`trp.factory` 走 `resolve_lab_profile` → lab 绑定暗室；`chamber.py` 列表默认过滤 + `workflow_engine` 的 `probe_ids="auto"` 走 `chamber.is_active`），同一时刻拿到不同 chamber 行。修法按 **去掉 > 换源 > 收窄 > 加机制**：推荐**去掉**双源之一（「当前暗室」:= active lab 所绑暗室，`chamber.is_active` 退役或降为派生只读显示），两派消费方换源统一走单一 resolver；最次才是 activate 端点双写同步（双写自身会再漂）。配套门 = 不变量门（全仓解析"当前暗室"的代码路径 ⊆ 单一真值源，`test_rule_gates.py` G 门同款结构断言）+ 诊断序列加 DB 两值一致性 fail-loud。
**Why P1（2026-08-02 实证抬档，原记 P2）**: 校准数据按 `chamber_id` 键控，dev 库实测已在失配：① `chamber.is_active` 指的「3GPP 16 Probe Dual」(`1b531e5c`) 在**所有校准表里零行** —— 按 active chamber 查校准今天就查不到；② 校准行分散在 `59c73fbe`（active lab 绑的 CAICT-16-Probe-Dual：rf_chain 6 / channel_phase 6 / probe_path_loss 7）与 `b7cd8de0`（calibration_baselines 1 / probe_path_loss 2 / rf_chain 1）；③ **`b7cd8de0` 这个 chamber 行已不存在** = 孤儿引用，根因是**校准类表全无指向 `chamber_configurations` 的外键约束**（现有 FK 仅 `probes` / `probe_configurations` / `switch_topologies` / `lab_profiles` 四条），DB 层拦不住（非 active lab 绑的 `06ca91a2` 同为孤儿）。下次现场要跑路损校准复测，带着双真值源进现场 = 把静默失配带进真测。
**同批收口候选**（实施时定，别扩成大改）：校准类表补 chamber FK 或显式 orphan 巡检；存量孤儿行 triage（保留/迁移/清理，走 dry-run 脚本模式）。

**实施实况（2026-08-07，已收口）**：新增唯一解析器
`resolve_current_chamber()`，只接受显式 LabProfile 或唯一 active LabProfile，并只返回
`LabProfile.chamber_config_id` 指向的暗室；无绑定、丢行、无 active lab、多个 active lab
均 fail-loud。`GET /chambers/active`、列表派生标志、`POST /activate` 和 workflow
`probe_ids="auto"` 已全部换源；activate 现在重绑 LabProfile，不再全表双写暗室标志。
`ChamberConfiguration.is_active` 仅保留为 brownfield 兼容列，更新 schema 禁止写入，响应中的
同名字段由所选 LabProfile 绑定动态派生。GUI 暗室管理、探头管理与 OTA Mapper 在多活动
LabProfile 时提供显式选择器，不会随便取第一行。

内审把本片从“解析器已统一”继续压到了**可执行闭环**：探头校准 workflow 原先导入不存在的
`ProbeCalibrationService`，live 端点必然失败，现已改接既有异步
`AmplitudeCalibrationService` / `PhaseCalibrationService`；同步 executor 在 API 中移到线程池，
每次校准只解析一次当前暗室，并把同一个 `chamber.id` 传进实际校准写入。端到端回归同时核对
workflow 结果与 `probe_amplitude_calibrations.chamber_id`，不再只测 `probe_ids="auto"` 辅助函数。
两个 CAICT 初始化脚本也已停止读取 legacy active flag。

同批采用候选中的**只读 orphan 巡检**，没有自动迁移/删除存量：新增
`chamber_configuration_integrity` 诊断序列，检查 LabProfile 绑定存在性及 13 张带
`chamber_id` 的校准表是否引用不存在暗室，发现即红并列出表名/ID。旧列已经退役为选择器，
因此不再要求它与 LabProfile “两值一致”——继续把废弃列纳入一致性反而会迫使 activate
恢复双写；G13 常驻门直接禁止生产接口与 workflow 再读回旧选择器，是更强的不变量。
物理 FK 与存量孤儿迁移仍需先决定 brownfield 数据归属，不在本片破坏性处理。
为避免继续制造新孤儿，删除暗室前会复用同一张 13 表目录做引用预检；只要存在校准历史就
409 拒绝并列出表名/行数，不级联删除测量证据。探头管理与 OTA Mapper 在 LabProfile
未选、绑定解析失败或切换暗室时均 fail-closed：不再回退全量探头，并清除旧暗室来源的已加载配置。
专项回归 16 case、G13 规则门及完整后端 `3390 passed / 5 skipped` 通过；GUI production
build 通过（仅保留既有 chunk/dynamic-import 提示）。GitHub Codex 外审两轮依次出
`2 P1 → 2 P2`，四条均修；R2 尾部修复又经内审收紧两个 mutation 时序窗口后终审 `CLEAN`。
按两轮上限不再发 R3，未外审的尾部范围已在 #301 台账行如实登记。

---

### ~~P1-48~~ — 日志与报告分不出哪台仪表是真的（P1-37 的三个缺口）✅（2026-08-10 完成，五片全合）

> **✅ 2026-08-10 收官记录**（下面原文是开工前写的方案，保留备查）
>
> | 片 | PR | 做了什么 |
> |---|---|---|
> | 日志线 | [#308](https://github.com/swang430/Meta-3D/pull/308) | `hal_mode` 改成按每台仪表自己的标取值，不再读全局单例；`app.hal.scpi` 之外的三处直连 logger 也接上标记 |
> | 删编数接口 | [#313](https://github.com/swang430/Meta-3D/pull/313) | 删掉四条整体返回随机数的报告接口（**−955 行**）：`/statistics/compare`、`/benchmark`、`/time-series` 等 |
> | 路损校准 | [#312](https://github.com/swang430/Meta-3D/pull/312) | 要求真测时拒绝模拟驱动，**四层入口**（VNA 旧路径 / CE+SA 主路径 / B 路径上游信号源 / 射频开关）共用 `is_mock_driver()` |
> | 报告线 | [#310](https://github.com/swang430/Meta-3D/pull/310) | 标签由验证状态派生（不单看 source）；未确认来源的数值一律不印，含**提示文案里的兜底数字** |
> | 虚拟路测 | [#314](https://github.com/swang430/Meta-3D/pull/314) | 删掉编数 fallback + `import random`；浏览器算的合格判定一律不采信；结论四态（`passed`/`failed`/`undetermined`/`incomplete`）；`pass_rate` 可空 |
>
> **代价与复盘**：外审 **27 轮 30 条**，其中 #314 一个 PR 就占 **12 轮 22 条**。
> 那 22 条里约 **77%** 是本地就该发现的 —— 自己修出来的约 7 条、
> 「改了值没追全下游」约 10 条。根因是 13 个 commit 里 **12 个修复一次内审都没过**，
> 全部推上去等外审当编译器用。
>
> **由此产生的三条流程改动**（都已落地）：
> ① 内审改成**每一次 push 前都过**，并新增轻量档（读 diff + 一步最小域枚举 + 造变异，1–2 分钟）；
> ② 「改之前先列全集」写进 `AGENTS.md` 0.5 节 + `CLAUDE.md` ⓪②⁺ + memory；
> ③ 规则整理 [#316](https://github.com/swang430/Meta-3D/pull/316)：消掉 8 处手工同步契约、
> 轮次上限改成按严重度分级、把 42 个规则门显式化。
>
> **未做的（已进 Discovered）**：给「真假标注上线前归档的旧报告」挂警示 —— 整条支线撤回，
> 三个踩过的洞（判据别按形状猜 / 判据别取客户端能写的数据 / 警示要挂在真正走得通的出口上）
> 已完整记录，重做时照着避。⚠️ 它的实际影响面当时为零（库里 214 份报告全是 `single_execution`，
> 一份虚拟路测报告都没有）—— **加防将来的机制前先查库里现在有多少条**。
>
> **Gemini 外审实验结论**：接通了（`.gemini/config.yaml` 由用户自己提交并关掉了自动 review），
> 但唯一那条 finding 是幻觉 —— 指着一个正确的中文字符串说它是笔误，全仓 grep 0 命中。
> 后续外审仍以 Codex 为准。

> ⚠️ **先读这条：本条目的证据成色不均匀。** 2026-08-09 六路并行只读调查 + 对抗性核实，
> **核实阶段被月度额度上限打断** —— 下面 **B / C / 「8-7 现场无法追溯」三段未经对抗性核实**；
> 已完成的 10 条核实**全部判「需收窄」、零条判「成立」**。随后的**内审**（`pre-commit-reviewer`，
> 精简档）抽查 12 项事实，9 项完全命中、**3 项被证伪或判过强**，已按其结论改写（F1/F2/F3/F6/F7/F8）。
> **未核实那三段按「待验」看，别当定论直接引用。**

**What**: P1-37（PR #303）**已经把仪表粒度的真假标记做出来了** —— 每个驱动类带
`driver_source`(real/mock) + `simulated`(bool) 两个 ClassVar（`app/hal/base.py` 里搜
`driver_source: ClassVar`，五个 Mock 类覆盖），逐行打进 SCPI 往返记录的 TX/RX/OK/ERR 四种行。

**两个字段的落地程度不一样，别混为一谈**（内审 F2 收窄）：
- **`simulated` 已经有一个活消费方** —— 正式证据门
  （`app/services/execution_scpi_evidence.py` 里 `simulated_exchange_not_authoritative`）
  会拒收模拟来源，roadmap 的 P1-37 索引行原话也是这么写的。**收口时绝不能把这个门改坏。**
  它今天不具区分力的原因另有其他（`formal_acceptance` 全库 0 次为 true，见次生栏）。
- **`driver_source` 才是零消费方** —— `grep -rn "driver_source" app/ | grep -v "^app/hal/"` = **0 命中**。

本片是**产出侧补齐 + 消费侧接上**的收口，不是从零开发。

**Why P1**: 2026-08-09 用户手工测试时的原话 ——「我在 log 里是不是看不出哪些是 mock，
哪些是 real 仪表？」**是的，看不出。** 而这条线的方向早已定死（2026-08-05 用户：
「今后 log 是我们主要的调试手段，让它尽快完整/正确/高效的就位」），本片正落在**「正确」**
那个字上：有的都是真的 —— 现在**分不清哪些是真的**。

按危害排三片（**建议 C → B → A，但用户拍板**）：

---

#### A — `app.log` 里的仪表真假只有一行自由文本，且 `hal_mode` 这个字段会说谎

⚠️ **本段标题原写「app.log 里看不到仪表真假」，被内审 F3 判过强，已改。** 实况是：
`app.log` 里**每台在册仪器、每次 HAL 初始化各有一条**声明行，形如
`[HAL] signalAnalyzer: mode=auto, use_real=True (auto (global=real))`
（实测 `app.log.2026-08-08`：baseStation 132 / channelEmulator 129 / positioner 129 /
rfSwitch 129 / signalAnalyzer 129 / vectorSignalGenerator 7 / vna 7）。
**真实缺口是三件别的事**：
① 声明在自由文本 `msg` 里，**不是可过滤的结构化字段**；
② **只覆盖初始化那一刻**，不覆盖后续每一行；
③ `use_real` 是**配置意图**不是**实际落地的驱动类** —— **真驱动类没注册时，
  选类阶段会回落 Mock，而 `use_real` 仍是 `True`**。
  ⚠️ **别写成"连接失败回退 mock"**（外审纠正）：连接失败**不会**替换驱动 ——
  驱动只在 `connect()` 成功时才进 `self.drivers`，失败的两条路都只记一行 fail，
  从不换成 Mock 顶上。照"连接失败回退"去写 S2/S3 的门，会测一条**不存在的路径**，
  同时漏掉真正的选类阶段回落。

**A1 结构化标记被命名空间过滤器挡掉**：`file_app` handler 挂了 `exclude_scpi_from_app`
（在 `app/core/logging_config.py` 里搜这个名字，以及 `ExcludeLoggerPrefixesFilter`），
把 `app.hal.scpi.*` 整个命名空间挡在 app.log 之外。实测 `app.log.2026-08-05/06/07/08`
四个文件 + 当前 `app.log`，`driver_source` 出现 **0 次**。
⚠️ **那个过滤器是对的，修法是换源不是去掉** —— 但它的**出处是 P1-47A（#298 `66b09a0`），
不是 P1-40**（内审 F6 用 `git log -S` 纠正，两个 token 都只命中那一个 commit）。

**A2 `hal_mode` 与仪表事实矛盾**：它读的是「写这条日志那一刻**全局单例**的 mode」
（`logging_config.py` 里搜 `get_hal_service().mode.value`），跟这行说的是哪台仪表无关。
⚠️ **本条目一律用可 grep 的稳定锚，不写行号**（内审 F5：P1-48 的 A1/A2 修法必然改
`logging_config.py`，改完所有行号全部下移；memory「指针四问」里「坐标稳吗——绝不写行号」）。
- **铁证一**：8/7 的 `scpi.log` **第一批行**标着 `hal_mode="mock"`，内容却是在跟**真 F64**
  通信、拿回了带真实序列号的 IDN。
- **铁证二**：`app.log.2026-08-08` 里同一行（内审实测该行在 8/8 出现 **4 次**、当前 app.log 0 次）—— `{"hal_mode": "mock", "msg": "[HAL] channelEmulator:
  mode=real, use_real=True (per-instrument (forced real))"}`。全局说 mock，那台仪表说 real。
- **二义性**：`get_hal_service()` 发现单例是 `None` 会**现场 new 一个 `DriverMode.MOCK`**
  顶上（`instrument_hal_service.py` 里搜 `if _hal_service is None`），所以 `mock` 也可能意思是
  「**这个进程压根没初始化过 HAL**」。`app.log.2026-08-08` 里 120 次热重载，每次头 26 行 boot 日志全被误标。
- **副作用**：日志 filter 会把这个假单例**写回全局变量**，此后判空逻辑看到的不再是 `None`。
- **取值实际有四种**：`app.log.2026-08-08` 里 real 14939 / mock 14859 / `<MagicMock ...>` 347 / `-` 31（共 30176 行）；
  8/7 现场 mock 107632 / real 72087 / `-` 821 / MagicMock 1490。
  下游按 hal_mode 过滤的代码（`app/api/system_logs.py` 里搜 `entry.hal_mode.lower()`）只认 mock/real 两种。

**A3 `instrument_id` 94–95% 是 `-`**：不是字段死了（`app.log.2026-08-08` 有 1810 行 / `app.log.2026-08-07` 有 9043 行带真 id），
是**结构性**的 —— 30 个填充点里 20 个挂在被过滤掉的 `app.hal.scpi*` 上；
`current_instrument_id` contextvar 在**生产代码里零设置方**（只有两个测试文件 set 过）。

---

#### A4 — 手动 SCPI 终端那条路根本不产真假字段（内审 F8 补，**正是手工测试走的路**）

`app/api/instrument.py` 有三处 `logging.getLogger("app.hal.scpi")`，发出的
`[SCPI-TERM via HAL]` / `[SCPI-TERM]` / `[SCPI-PROBE]` 行，`extra` 只带
`instrument_id / direction / command`，**没有 `driver_source` / `simulated`** ——
它们不走 `app/hal/base.py` 的四个共享 helper，所以 P1-37 的标记完全绕过。
实测 `scpi.log`（8/8，P1-37 之后）里 **80 行**无这两个字段，**全部**来自 exact logger
`app.hal.scpi` 这条路；8/7 同类 263 行。
⚠️ **这正是用户手工测试时用的那条路** —— 把本片定性成「三个**消费端**的收口」会低估工作量，
**产出侧还差这一处**。

---

#### B — 报告不说自己是 mock

2026-08-08 那份 mock 报告的 PDF **有三处「未验证」标注 + 一处 UNKNOWN 判词，没有假称 PASS**
（这点是对的，不要在收口时把它改坏）。但：
- **没有任何一句话说明「本次为模拟模式」**，不写 hal_mode，不写哪几台是假的；
- 把 mock 编出来的 TRP 数值**当普通数字印了出来**，且「TRP 来源」栏写的是 `hal_signal_analyzer`；
- precheck 阶段那句明确说「这是 mock」的原话**落了库**，**报告渲染器把它丢了**；
- `report_service.py` / `report_data_collector.py` / `pdf_generator.py` 三个文件里
  `mock|simulat|verified|hal_mode|trust` 五个词的命中数**都是 0** —— 通用报告链完全不知道这回事；
- `TestExecution` 表**没有任何** hal_mode / is_mock / 数据来源列；
- 唯一带真假标注的地方是 MIMO_OTA 报告执行器自己拼的 `content_data`，标注是塞进
  `step_results[].parameters` 的**中文字符串**，不是结构化字段。

---

#### C — VRT 报告用 `random.uniform()` 现编 KPI（**最危险，建议先做**）

虚拟路测报告链会用 `random.uniform()` 现编 KPI，标 `passed=True`，写进 PDF，
**全程零标注、零证据段**。**2026-08-08 23:09** 就产出了一份这样的 PDF（内审 F1 纠正：原写 2026-08-09，那是个**未来时间戳**，全仓无 8/9 的 PDF）。
内审独立复核了 C 段的核心断言，**成立** —— `app/api/road_test.py` 的 KPI 确实用
`random.uniform` 且硬编 `passed=True`；`app/api/report.py` 的 `POST /compare` 端点
整体返回 random 编造的 similarity / confidence。
报告比对端点 `POST /api/v1/reports/compare` 整体返回 random 编造的 KPI 差异与
「趋势/置信度」，路由已注册（GUI 侧未发现调用方）。

⚠️ **设计勘察查出这是两层假**：**GUI 也在编** —— `TestExecutionModal.tsx` 用
`Math.random()` 现编样本、经 `POST /metrics` 落库，而**后端注释管它叫 `Use real collected data`**；
**PASS/FAIL 判决是浏览器算的**，后端原样落库、原样打印。
⚠️ **只治后端那一层，会把前端编的数「洗成真实采集」，比现状更隐蔽** —— 所以删后端编数
必须在后端落库入口无条件标成模拟、并在报告构造处新加一个读这个标记的地方（设计稿 S1；
  原先打算靠一句免责声明的 S7 已取消 —— 标注代替不了剔除）。

**VRT 全链零 HAL 引用** —— 是「从来没做」不是「做了被顶掉」；唯一像接线的模块自己的
docstring 里写着"全仓零调用方"。

⚠️ **仓里有一道旧门在给谎言背书**：`tests/test_feature_gaps.py` 的 `TestReportComparison`
两个用例 assert `POST /reports/compare` 返回 200。删端点那片**必须把它一起删**，
否则落地当天全量红在一个没预料的文件上。

**为什么排最危险**：A/B 是「看不出真假」，C 是「**编出来的数标着通过进了正式报告**」。

---

#### 次生（记录在案，本片不一定做 —— 按 ⓪③ 进 Discovered 待评估池）

- **日志行里没有 PID** —— `JsonFormatter` 显式把 `process`/`processName` 排除
  （`logging_config.py` 里搜 `standard_keys`）。服务进程 + pytest + 热重载子进程写同一个文件，无法切分。
  8/7 全天 `hal_mode` 「变化」**1977 次**，真正的模式切换**只有 6 次**，其余 1971 次是
  多进程交织造成的**假切换**。
- **`driver_source="real"` ≠ 「真硬件答的」** —— 它是**基类默认值**，只有 5 个 Mock 类覆盖了它。
  pytest 的 MagicMock 桩不是 Mock 驱动类，照样标 `real`/`false`。`scpi.log`（8/8 数据）里
  pytest 夹具 `uxm-1`（20050 行）、`uxm-irat`（19530 行，均为 `scpi.log` 的 8/8 数据）跟真实注册的
  `channelEmulator_37fb0c01`，这两个字段**完全一样**。
- **`MockVNA` / `MockSignalGenerator` 漏声明**这两个 ClassVar，会继承基类 `"real"`/`False`
  （目前不可达 —— 这两类零 SCPI 日志调用；换句话说是**装着的地雷**）。
- **`driver_source` 丢在后端不是 GUI**（内审 F7 指正层级）—— 截断发生在
  `app/api/system_logs.py` 的 `LogEntry` Pydantic 模型（`ts/level/logger/hal_mode/
  session_id/execution_id/instrument_id/msg` 八个固定字段 + `raw`）。GUI 拿不到是因为
  **API 不给**；按「改 GUI」去做改不动这件事。
- **pytest 写进生产日志** —— `scpi.log`（8/8 数据）里绝大多数行来自单元测试，不是运行中的服务。
- **`Result_Report/` 与 `api-service/data/reports/` 下存在没有对应 `test_reports` 行、
  也没有对应日志行的 PDF** —— 报告产物与数据库记录会脱钩。
- **`formal_acceptance` 全库 0 次为 true** —— SCPI 证据链是最强的真假门，但目前对
  mock/real **不构成区分力**（`measurement_verified` 全库 395 行里只有 1 行有值，
  且该字段 2026-08-07 21:03 才引入，**晚于 8/7 现场真机时段**）。

---

**⚠ 8/7 现场那批数据无法追溯**：`driver_source` / `simulated` 是 **8/7 21:03 提交、
21:33 首次落盘**的。现场测量窗口 **11:00–19:00 那 173,124 行** SCPI 记录完全没有这两个字段
（最后一行无字段 20:14:06，第一行有字段 21:33:20，**零重叠**）。
**恰恰是最需要回答「哪台是真的」的那批数据，机制不存在。** 本片修不回来，只能防下次。

**调查方法与证据留存**: 2026-08-09 六路并行**只读**调查（hal_mode 来源 / 单机真假判定 /
SCPI 日志标记 / instrument_id / 报告与 KPI / 8-7 现场日志实证）+ 对抗性核实。
⚠️ **核实阶段被月度额度上限打断**：`per-instrument-truth` / `report-kpi-leakage` /
`onsite-real-log-evidence` 三路的发现**未经对抗性核实**；已完成的 10 条核实
**全部判「需收窄」，零条判「成立」** —— 上文已按核实结论改写，未核实那三路**按「待验」看**。

**配门**（⓪④：每加一道门必须附让它红的变异并**实跑**；至少到「不变量」档）:
- **A** `hal_mode` 二义性门 —— 懒建单例那条路径不得产出与真实模式无法区分的 `mock` 标签
- **A** 仪表真假不变量门 —— ⚠️ **原措辞「每台在册仪器有且仅有一条真假声明行」已作废**
  （内审 F3 当场判死：按「有没有声明」判 → **今天就绿**，一行代码不改也绿 = ⓪④ 最低档的
  恒真断言；按「有且仅有一条」判 → **今天就红**，因为 8/8 有约 129 次热重载 = 129 条/仪器，
  红的原因跟本片缺陷毫无关系）。**改成打在**「结构化字段存在 **且** 与该驱动类实际的
  `simulated` 属性一致」上 —— 判据取**驱动实例的真值**，不取「日志里有没有那句话」。
- **B** 报告不变量门 —— 任一 step 的 `simulated=true` ⟹ 报告正文**必须**含模拟声明
- **C** VRT 门 —— `random` 产出的 KPI **不得**标 `passed=True`

**设计稿已出**：[`docs/design/P1-48-instrument-provenance.md`](design/P1-48-instrument-provenance.md)
（2026-08-09，三套对立方案 + 四维判官评审 + 综合）。**切成 9 片**，修法分布
**删掉 4 / 换地方取数 4 / 收紧 1 / 新加一套东西 1 处**（S7 已取消；但外审指出虚拟路测那条链没有读模拟标记的地方，S1 里必须新加一处）。
> 这个数改过四次（0 → 1(S7) → S7 取消回 0 → 外审指出虚拟路测那条链没有读模拟标记的地方
> 必须新加一处 → 1 处），**四次都是被外审纠出来的**。。**零新数据库列、零新 API 字段、零新服务。**
⏸️ **等用户拍板 5 个决策点后才动代码。**

最要紧的一处纠错：两套候选方案都用"遍历 `app.routes` 断言那四条 path 不在里面"当门、
**并写着"今天必红"**，判官实测**今天就是绿的** —— 本仓 fastapi 版本下 `include_router`
不展平。而这坑仓里**已经踩过并立了碑**（`test_rule_gates.py` 的 `_expand_app_routes`）。

<!-- 历史留存：本条原文 -->
**⚠ 先出设计稿再动代码**（⓪⁺②「先 review plan，后写代码」）。设计稿落
`docs/design/P1-48-instrument-provenance.md`，用户过目后才动代码。

**本片是 Gemini Code Assist 外审首测对象**（2026-08-09 用户定）—— Codex 月度额度已耗尽，
本片走 `/gemini review`，并与 Codex 的历史表现做能力对比。

---

### P1-29 — `/dashboard/alerts/summary` 被路由遮蔽（驾驶舱告警计数条恒坏）✅（PR #320，2026-08-11）

**What**: `api-service/app/api/alert.py` 里 `@router.get("/alerts/{alert_id}")` 声明在 `@router.get("/alerts/summary")` **之前**，FastAPI 按声明顺序匹配 → `summary` 被当成 `alert_id` 解析 → `uuid_parsing` **422，该端点不可达**。
**Why P1**: 有**活消费者**且用户可见 —— 驾驶舱 `gui/src/features/Dashboard/ZoneLogsAlerts.tsx` 每 **10 秒**轮询 `fetchAlertSummary`，所以「按 severity 的告警计数条」恒坏；同时每 10 秒往 app.log 灌一条 422 + 一条 DB rollback（app.log 已 16MB，与 P3-19 的噪声治理同源但那是卫生批、这是功能坏了）。修法是**挪一行声明顺序**。
**实证（两份独立）**: ① `curl -s localhost:8000/api/v1/dashboard/alerts/summary` → `{"detail":[{"type":"uuid_parsing","loc":["path","alert_id"],"input":"summary"}]}`；② GUI 实时日志面板每几秒刷一条 `GET /api/v1/dashboard/alerts/summary → 422`，栈里明写 `alert.py line 102, in get_alert`。
**旁证**: `gui/src/api/mockServer.ts` 自己有注释「summary registered before /alerts so the exact-string summary route isn't shadowed by the list route」—— **mock 侧作者意识到了这个坑并规避了，真后端没有**。
**配门**: 字面量段不得被同级 path 参数遮蔽（可做成 G12 不变量门：对每个含 `{param}` 的路由，检查同前缀下是否存在声明在其**之后**的字面量兄弟路由）。**来源**: P1-25 全量审计。

**收口（PR #320）**：`/alerts/summary` 已移到 `/alerts/{alert_id}` 之前；HTTP 定点测试由 422 转为 200。新增 G19 按 FastAPI 真实懒加载路由树与声明顺序扫描同方法遮蔽，并用正反两个合成 router 自测判定器。全量枚举同时发现的 calibration `latest` 与 topology `default` 两条存量已进入 Discovered，以精确例外棘轮锁住，不在本片越界处理。

---

### P1-30 — SCPI 往返日志的证据能力（log 撑不起调试复现）✅（2026-08-03 完成）

**What**: 现场调试人员打开 `scpi.log`，看不出一次仪器往返实际发生了什么。三处收口，动 3 个生产文件（`app/hal/base.py` + `app/core/logging_config.py` + `app/config.py`）：
- **截断显式化** —— `[:200]` 静默截断 → 上限放宽到 **2000**（`app/config.py` 的 Settings 项 `log_scpi_resp_max`，`.env` 里写 `LOG_SCPI_RESP_MAX=200` 可调回），超限时消息体附 `…[truncated 2000/3412]`，且 `resp_len` **永远记截断前的真实长度**。⚠️ 旋钮**刻意不用 `os.getenv`** —— 本项目的 `.env` 由 pydantic-settings 直接读进 Settings 对象、**不注入 `os.environ`**（实证：import `app.config` 前后 `os.environ` 里都没有 `DATABASE_URL`），用 `os.getenv` 会让 `.env` 里配的值被静默忽略、旋钮形同虚设。这条由变异 M9 守着。
- **往返配对** —— TX 行只表示"打算发"；新增 `OK`（写命令完成 + 耗时）/ `ERR`（异常类型 + 耗时，**异常原样重抛，控制流零变化**）。sync 与 async 两条路径都覆盖（异常在 `await` 时刻才抛，外层 try 拦不住 —— 这是最易漏的一半）。RX 行补 `duration_ms`。
- **`instrument_id` 收窄** —— `ContextFilter` 的 contextvar 只做兜底，不再覆盖调用方 `extra=` 显式给出的值。

**Why P1（实测，口径写在括号里）**: 全部 31 个 `scpi.log*` 里 `hal_mode=real` 的 RX 共 **171,170** 条 ——
| 现象 | 条数 | 占 real RX |
|---|---|---|
| 长度**恰好 200**（= 被截断） | **22,914** | 13.4% |
| 长度 0（`RX:` 后空白） | **60,565** | 35.4% |

**RX 的最大长度就是 200** → 日志里**从未出现过任何一条长响应的全貌**。被砍最多的是 `BSE:MEASure:NR5G:CELL1:BTHRoughput:DL:TSTatistics:JSON?`（**22,608** 条，= 下行吞吐量统计，**项目的核心测量数据**），另有 `SYST:INFO?` 140 / `BSE:STATus?` 136 / `SYSTem:ERRor?` 1（**错误队列自己被砍了**）。

**查询发出后日志里没有下文**：**90,585** 条（口径：`hal_mode=real` 的含 `?` 的 TX 共 261,755，RX 共 171,170，差值即无下文）。

⚠️ **谓词一（别归因）**：只能说"有去无回" —— 是超时、异常、还是 coroutine 从未 await，**日志本身没记所以判断不了**；**不得**把这个数说成"失败了 9 万次"。
⚠️ **谓词二（别按相邻行数）**：早先按"TX 之后紧接着不是 RX"数得 110,185，**偏高 21.6%，已作废** —— TX 记在 `_scpi_lock` **之外**，并发（broadcaster 1 Hz × 32+ 查询与测量序列并行）与嵌套（F64 超时后在同一命令窗口内排水，每条 `SYST:ERR?` 各产生一对 TX/RX）都会打断相邻性。**配对要按 `query` 字段，不能按行序**。内审 F3 抓出。
⚠️ **谓词三（别说本片修好了）**：本片让"仪器回了空串"（有 RX 行 + `resp_len:0` + 耗时）与"有去无回"（没有 RX 行）分开了，但**"被上层取消"与"coroutine 从未 await"仍是同一种签名** —— `CancelledError` 继承 `BaseException`，`except Exception` 抓不到（内审 F4 实跑：`asyncio.wait_for(driver._query(...), 0.05)` 超时后 scpi.log 里**只有 TX、没有 ERR**）。要覆盖须改 `except BaseException` + 裸 raise，**已进 backlog，本片没做**。

**`instrument_id` 在全部 759,894 行 SCPI 日志里恒为 `-`（100%）**：驱动传了 `extra={"instrument_id": ...}`，`ContextFilter.filter()` 随后**无条件重写**成 contextvar 默认值（SCPI 路径上无人 set 过它）。仪器身份只在 logger 名里侥幸留存 —— 标称端 vs 生效端同母题。

**门与实证**: 数字与口径以设计稿 [§5](design/P1-30-scpi-log-evidence.md) 为准，**本条不重复列**（P1-25/#268/#269 连栽四次的就是"两处各记一份、改一处漏一处"）。要点：门在 `api-service/tests/test_scpi_log_evidence.py`，配套变异脚本逐条实跑过；**其中 4 条变异是内审 agent 自己造出来、我原来的门没兜住的**（上限常量写死成字面量 → 旋钮当场死掉；8 处耗时全换成 `0.0` → 恒真断言测不出），已补门。

**明确不做，已进 backlog**: 约 **160–175 处** `except` 吞异常不记日志（**这个数不要当精确值用** —— 三个略有差异的粗筛口径分别得 162 / 165 / 175，`pass` 计数 38–51 不等；要用它定范围就先跑 Discovered 条里那段脚本，内审 F11 抓出）；`app.log` 78.4% 是 `Cache updated`/`Cache expired` 一对 DEBUG 心跳（各 52,650 次 / 共 134,362 行）→ P3-19；`logs/` 3.5 GB / 253 文件 → P3-19；驱动层"空回复 vs not-ready"语义判定（`propsim_f64.py` 把两者合并成 `None` 且不进 `query_errors`，实测 60,565 条空回复）→ 需查 NotebookLM 的独立片。

**设计稿**: [`docs/design/P1-30-scpi-log-evidence.md`](design/P1-30-scpi-log-evidence.md)

---

### P1-31 — `uxm_kpi_readback` 诊断序列（#275 那批 KPI 命令的现场对账载体）✅（2026-08-04 完成）

**What**: 一个只读诊断序列，把 #275 换上的那批 KPI 命令**逐条发出并打印原始回复**，供现场对着 UXM 面板核验。不做任何解析判定 —— 它的产出就是"真机回了什么"。

**Why 当时优先**: #275 已合并，但**本地零真机验证** —— 命令形式 / 元素下标 / 单位 / 前置条件全部来自手册与真机历史日志。现有 `uxm_scpi_compatibility` 只能回答"通不通"（命令存不存在），**回答不了"回了几个元素、第几个是什么、单位是什么"** —— 而 #275 的正确性恰恰全押在这上面。现场日期不由我们定，**没有它，下次现场这批改动就白跑一趟**。当前执行片永远见顶部 Current Focus。

**要打印/回答的 9 项**（判据见 Discovered 同日「#275 整批必须现场核验」条）：
① OTA 吞吐量回不回 6 个 double ② 单位 bps 还是 Mbps（跟面板比，差 10⁶）③ `idx4=average`/`idx1=current` ④ BLER DL 10 个 / UL 6 个、`idx8`/`idx4` ⑤ CQI `result[4]=average`（idx3 是 maximum，取错一位系统性乐观）⑥ RI 8 个 bin 是码点（rank=码点+1）⑦ RSRP/SINR 口径（**差 156 = 码点，相等 = dBm**）⑧ 三条前置真被接受 ⑨ `BTHRoughput:CLEar` 真能圈窗口

⚠️ **原第 ⑩ 项「现场探出 `Uxm5GNRTestAppProfile` 的无前缀形式」已删**（Codex #276 R2）——
与本条目的约束**自相矛盾**：约束是「只探手册有依据的命令、禁猜」，而无前缀形式
恰恰**手册里没有**，现场探它只能靠猜拼写。该方言的命令形式是**独立问题**，
出路是**查手册**（像 2026-08-03 查 IRAT 那样）而不是现场试 —— 已进 Discovered。

**9 项 ↔ 序列步骤的对应**（2026-08-04 落地，可逐条核）：
①②③ → `① DL OTA 吞吐量` / `② UL OTA 吞吐量`（元素个数 + idx1/idx4 + bps/Mbps 两种候选读数并排）；
④ → `③ DL BLER` / `④ UL BLER`（10/6 个元素 + idx8/idx4 并排）；
⑤ → `⑤ CQI 统计`（idx4 与 idx3 并排，取错一位一眼看出）；
⑥ → `⑥ RI 直方图`（**码点+1 与 bin 即 rank 两种加权都算出来**）；
⑦ → `⑦ UE L3 测量报告`（步骤里直接写判法：差 156 = 码点，相等 = dBm）；
⑧ → 前置步骤 `P1/P2/P3`（三条各记错误队列回复）；
⑨ → `⑧ BTHRoughput:CLEar 能否圈窗口`（清零前后 progress 并排）。

**⚠️ 实现期两处修正**（内审 12 条 + NotebookLM 复核，见 PR）：
① **不是只读序列** —— 第 ⑧ 项要发 `BTHRoughput:STATe ON` / `CSI:STARt` / `REPort ON`，第 ⑨ 项要发 **`CLEar`（清零正在跑的窗口）**。`safe_during_test=False`，写过的在 `finally` 写回。
② **前置不能只发不回读** —— 手册原文：`CSI:STARt` 在「已在跑」或「小区关闭」时**被忽略**。所以序列回读 `CSI:STATe?`（手册 Query only，返回 STOP|WAIT|MEAS），**不是 MEAS/WAIT 就说明前置没生效** —— 那样 ⑤⑥ 的 NaN 是前置问题、不是命令形式问题，两者分不开会让整片结论建在错前提上。
⚠️ 而 `BTHRoughput:STATe?` / `REPort?` 的 **`?` 形式手册未说明**（NotebookLM 明确回「未说明」）—— 序列把「读不到原值」当**预期内**处理：不猜一个值写回去，但必留一条步骤说明「没有写回、请手动确认」。

**约束**: 只放**手册有依据 + 生产驱动已在用**的命令（禁盲试）；出发前用 mock 跑一遍**只证序列本身不崩，不算验收**。

⚠️ **`safe_during_test=False`**（Codex #276 P1 抓出我方案自相矛盾）—— 本序列**不是只读**：
第 ⑧ 项要发 `BTHRoughput:STATe ON` / `CSI:STARt` / `CONFig:MEASurement:REPort ON`，
第 ⑨ 项要发 **`BTHRoughput:CLEar`**（**会把正在跑的测量窗口清零**）。
标 `safe_during_test=True` 会让 `SequenceRunnerPanel.tsx` 告诉操作员「测试中可跑」——
**跑一下就把正在测的 KPI 毁了**。要么整条标不安全（当前选择），要么把 ⑧⑨ 拆成
独立的不安全序列 —— 拆分留给实现期定，但**不许标成安全**。

### P1-32 — `configure_mac_throughput_test()` 在 IRAT 上 11/11 命令为 `None`（本地半）✅（2026-08-04 完成，#279）

> **✅ 收口（#279 / `2d3796e`）—— 下面 What / Why 两段描述的是**修之前**的状态，留作背景，别当现状读。**
>
> **已落地**：8 组写入改走 `_cmd()` graceful-skip（不再抛 `AttributeError`）；返回
> `bool` → `MacThroughputConfigResult(applied / skipped / missing_mandatory / error)`；
> 必要 8 / 可选 3 分级只放驱动一处；**调用方 `measure.py` 真消费** ——
> 必要项缺失或下发出错即 `StepExecutionStatus.FAILED`，且**在 `start_signaling()` 之前返回**
> （判定收窄成 `MeasureExecutor._mac_config_blocker`，才打得了行为门）。
> 门 27 条 / 变异 16 条全红。
>
> **⚠️ 仍未解决、留给 P1-33**：
> ① 补正确命令形式（见本文件 P1-33 段的手册裁决表）；
> ② **`BSE:CONFig:<celltype>:APPLY` 前置** —— 手册明写小区 ON 时多数配置改动要发 APPLY
> 才进协议栈，而上游 `set_cell_config` 收尾恰好把小区恢复 ON，所以现在只保证"命令发出去了"，
> 日志措辞是 `commands sent (**not** confirmed applied)`。**不补的话，P1-33 一填命令就从
> 「报错」变成「配错了还看起来配上了」**；
> ③ 「IRAT 到底支不支持这 11 条」**未经查证** —— 手册的 `Application Mode` 字段答不了
> （我们已定义、现场在用的 `CELL_BAND`/`DL:ARFCN`/`DL:BW` 同样标 `NSA | SA`），
> 且这批命令从未被真机普查过（`uxm_scpi_compatibility` 跳过 `None` 模板）。

**What（只做本地半）**: ① 走仓库已有的 `RealUxmDriver._cmd()` graceful-skip，不再在第一条 `.format()` 上抛 `AttributeError`；② **跳过了哪些必须显式返回给调用方**；③ **调用方必须消费它** —— 光返回不够（Codex #276 P1）：`app/services/mimo_ota/executors/measure.py:390-401` **丢弃** `configure_mac_throughput_test()` 的返回值、然后无条件往下 `start_signaling`。不改调用方，加了返回值也只是换个姿势**继续在没配置过的链路上跑测试**。必修的两半：驱动返回「跳过了哪些」+ 消费方在必要命令被跳过时**中止或显式标 degraded**。补齐正确命令形式那半是 **P1-33**。

**Why P1**: `UxmLteNrIratProfile` 继承的是 `UxmTestApp` **基类**（不是 `Uxm5GNRTestAppProfile`），`PDSCH_SCHED_ALGO` / `PDSCH_AMC_ENABLE` / `PUSCH_AMC_ENABLE` / `PDSCH_MCS` / `PDSCH_RB_ALLOC` / `TDD_PATTERN` / `TDD_PERIOD` / `HARQ_MAX_TRANS` / `HARQ_PROCESSES` / `CSIRS_PORTS` / `MEAS_TPUT_STAT_COUNT` **11 条全没覆盖** → 函数第一行就抛、整段 `except` 捕获、`return False`。**即 3GPP MIMO OTA MAC 层吞吐量测试的全部配置（Full Buffer / AMC 关 / 固定 MCS / 全 RB / TDD 格式 / HARQ / CSI-RS 端口 / 统计窗口）在现场那台仪器上从来没生效过。** #275 把 KPI 读对了，但**测的仍是没配置过的链路** —— 严重度高于本项之后的队列各片。

**注意**: #275 已把 KPI 前置（`_enable_kpi_measurements`）挪到该函数第 **0** 步、排在崩点之前，所以 KPI 前置目前是发得出去的；本片不要把它挪回去（有 `M10b` 变异守着）。

**来源**: #275 的生效端门 `test_configure_actually_sends_them` 一加上就红，才暴露出来。

### P1-33 — 按手册重写 IRAT 的 MAC 配置命令（本地半 ✅ #281 / 现场半 ⬜）（2026-08-03 立项）

> **本地半 2026-08-05 收口（#281）**：8 组命令按手册原件补齐 + 值形态转换
> （`FULL_TPUT` / `APOLicy` 枚举 / `MS5` / `N4`·`N16` / `P1`…`P8` / TDD 六整数）
> + 两条 apply（`QCONFig:APPLy:ALL` 先于 slot 级 AMC，再 `CONFig:<celltype>:APPLY`）。
> 下方那条 ⛔ TDD 前置阻塞**按方案 ① 解**：special-slot 符号数走函数参数（手册默认
> 6/4），**但 TestCase schema 的契约四步没做** → 拆出 **P1-33b**（见 Discovered）。
> 外审覆盖有缺口，见[外审表](#️-已合并但未过外审的批次只增不减周度回扫)。

> **⭐ 2026-08-04（P1-32 期间）—— 用**手册原件**裁掉了下表的三处错，并纠正一个前提**
>
> 单点问题以仓库里的厂商手册原件为准（`Instrument_API_Doc/Keysight UXM NR SCPI/*.md`）——
> NotebookLM 更全面但**会把推断说成结论**（本轮它先断言「LTE_NR_IRAT 就是 NSA」，
> 追问后自己撤回「在手册原文里完全没有依据」）。以下均为 **grep 手册原件**所得：
>
> **① 前提纠正：`Application Mode` 字段答不了「这条命令在 IRAT TAP 下能不能用」。**
> 手册确实把 `IRAT` 当独立取值用（`IRAT` 20 处 / `NSA | SA | IRAT` 38 / `SA | IRAT` 16 /
> `NSA | IRAT` 15 / `NSA | SA | IRAT | NREL1` 14 / `IRAT-SA` 13），而这 11 条标 `NSA | SA`
> 不含 IRAT ——**但对照组证伪了这个推论**：我们 IRAT profile 里**已定义、现场在用**的
> `CELL_BAND` / `CELL_DL_ARFCN` / `CELL_DL_BW` **同样标 `NSA | SA`**。
> 所以这个标注**既不证明支持也不证明不支持**。
> **两个方向都没有证据 = 未经查证。**
>
> ⚠️ 而且这批命令**从未被真机普查过** —— `uxm_scpi_compatibility` 的模板遍历
> **显式跳过 `None` 属性**，2026-05-13 那次现场普查探的是"已定义的"。
> **P1-33 第一步 = 先探，再决定补什么**（要先把候选命令临时写进 profile 才探得到）。
>
> **② 下表三处错，已用手册裁定：**
>
> | 下表哪一格 | 手册原件实况 |
> |---|---|
> | AMC 开关 `SCHeduling:CRNti:DL:IMCS:FIXed` | ❌ **手册 0 命中，这条不存在**。存在的是 `...:SCHeduling[:<BWP>]:<fc>:<sc>:DL:RRESource:APOLicy`（枚举 `FIXed`/`BLER`/`CQI`/…，`FIXed` = 关 AMC）；UL 侧是 `...:UL[:<ultype>]:IMCS:FIXed` |
> | 统计窗口「手册确认不存在」 | ✅ 下表对：`BTHRoughput:DL:TSTatistics:COUNt` **未命中**；`BSE:MEASure:NR5G:BTHRoughput:LENGth[:ALL]` **命中**。（我 08-04 一度写成「手册未说明」，是 NotebookLM 漏了 —— 已撤回） |
> | TDD 六条含 `DLSYmbols`/`ULSYmbols` | ✅ 下表对，`TDDPATtern:DLSYmbols` / `ULSYmbols` 手册均命中。**「`DDDSU` → 六参数欠定」那个卡点因此可解**：DL/UL 用 `DLSLots`/`ULSLots`，特殊时隙用 `DLSYmbols`/`ULSYmbols` |
>
> **③ 新增前置（内审 F7）：`BSE:CONFig:<celltype>:APPLY`。**
> 手册原文：「Update the stack with the changes … **This is not needed if the Cell if Off**」，
> 且「**most configuration changes won't be applied until this command** … is used」。
> 而 `measure.py` 的顺序是 `set_cell_config`（收尾把小区恢复 **ON**）→
> `configure_mac_throughput_test` → 所以这批写入**只进缓存**。
> P1-32 只保证"发出去了"（日志措辞已改成 `commands sent (**not** confirmed applied)`），
> **补 APPLY + 发后查 `SYST:ERR?` 是 P1-33 的显式前置**（`set_cell_config` 已有成型逻辑可复用）。
> ⚠️ 不补的话，P1-33 一把命令填进 profile，就从"报错"变成"**配错了还看起来配上了**"。


**背景**: P1-32 让 `configure_mac_throughput_test()` 不再崩、不再假成功，但那 11 条命令在 IRAT 上仍是 `None` —— **实际配置一条也没下发**。本片补齐它们。

**⚠️ 2026-08-03 查手册（NotebookLM）后，本片形态变了** —— 原以为"命令形式不知道、必须现场探"，**实际手册里 8 组全都有 `BSE:` 形式**。所以卡点不是「不知道命令」，是「没在真机上验过」，**本地半现在就能做**（Codex #276 P2 抓出原来 gate 在 P1-31 上是错误依赖）。

**而且不是加前缀那么简单 —— 值形态与机制都变了**（这正是"照抄旧形式改前缀"会踩的坑）：

| 项 | 现用（无前缀，IRAT 上为 `None`） | 手册的 `BSE:` 形式 | 差异性质 |
|---|---|---|---|
| Full Buffer | `PDSCH:SchedAlgoritm ... FULLBUFFER` | `BSE:CONFig:NR5G:SCHeduling:QCONFig:SCENario` 枚举含 `Full Throughput` | **完全不同的机制**（Quick Config 场景，不是逐 BWP 设调度算法） |
| AMC 开关 | `PDSCH\|PUSCH:AMC:ENABle ON/OFF` | `...:SCHeduling:CRNti:DL:IMCS:FIXed`（Bool） | **语义反过来**：ON = 固定 MCS = **关** AMC |
| 固定 MCS | `PDSCH:MCS <n>` | `...:SCHeduling:CRNti:DL:IMCS`（0..28） | 路径不同 |
| 全 RB | 一个值 `"ALL"` | **三条**：`RBALlocation:FIXed` + `RBSTart` + `RBNumber`（0..275） | **一条拆三条** |
| TDD | `TDD:PATTern "DDDSU"` + `TDD:PERiod "5MS"` | **六条**：`TDDPATtern:STATE` / `PERiod`（枚举 **`MS5`**）/ `DLSLots` / `DLSYmbols` / `ULSLots` / `ULSYmbols` | **pattern 字符串→slot/symbol 计数**；周期是 `MS5` 不是 `5MS` |
| HARQ | `HARQ:MaxTrans 4` / `HARQ:PROCesses 16` | `PHY:DL:HARQ:MAXTrans`（枚举 **`N4`**）/ `PHY:DL:HARQ:PROCesses`（枚举 **`N16`**）；UL 另有一套且 PROCesses 是 **Integer** 不是枚举 | **裸整数→枚举**；DL/UL 分开且类型不同 |
| CSI-RS ports | `CSIRS:PORTs <n>` | `...:CSI:RESource:CONFig:NZP:<cri>:RM:NPORts`（带 `<cri>` 维度） | 多一个资源索引维度 |
| 统计窗口 | `BTHRoughput:DL:TSTatistics:COUNt` | **手册确认不存在** → `BSE:MEASure:NR5G:BTHRoughput:LENGth[:ALL]`（全局） | **原命令是编的** |

**本地半**: 按上表重写 profile + 驱动里的值形态转换（`"5MS"` → `MS5`、`16` → `N16`、`"ALL"` → `FIXed`+`RBSTart`+`RBNumber`）。

⛔ **TDD 那条是本片的前置阻塞点，不能直接排期**（Codex #276 R3 P1）——
`"DDDSU"` 翻成手册的六条参数**信息不够**：`D`/`U` 的整槽数能从字符串数出来，
但 **`S`（special）槽不编码它含几个 DL 符号、几个 UL 符号**，而手册要的正是
`DLSYmbols` / `ULSYmbols` 两个数。我们的 schema 目前只有 `tdd_pattern` +
`tdd_period` 两个字段，**拿不出这个信息** —— 硬转就是替操作员**猜一个真实的
TDD 配置**，猜错会让整批吞吐量结果失效（比现在"一条都没下发"更糟：
现在是没配置，那样是**配错了还看起来配上了**）。

**动手前必须先定这一件事**（二选一，属设计决策不是实现细节）：
① TestCase schema 增加显式的 special-slot 符号参数（`tdd_special_dl_symbols` /
   `tdd_special_ul_symbols`），由测试例声明 —— 符合「TestCase 是单一真值源」；
② 或在 LabProfile 里放一个**有文档依据的**实验室默认值，并在下发时显式记进
   `measurement.log`（让报告能看出这个数从哪来）。
**在这条定下来之前，本片的 TDD 部分不排期**；其余 7 组不受影响，可先做。
**现场半**: 真机验证被接受（见 Blocked on hardware 表）。

**依赖**: P1-32 先做（不崩 + 不假成功 + 调用方消费），否则改完也看不出对错。

### P1-34 — 日志时间线可读（本地时区 + 噪音抑制 + `request_id` 串联）⬜（2026-08-05 立项）

**目的（用户原话，2026-08-05 手工测试当场）**：
> 「重要的是帮助使用者了解状况，不会是无头苍蝇……我们想看到针对**什么时候**的操作，
> 能看到**什么操作流程**，**什么结果**。」

**可观察故障**：操作员打开日志面板，看不出自己刚做的那次操作 —— 时间对不上手表、
真信息被背景轮询淹掉、同一次操作产生的多条日志无法聚在一起。

**实证（2026-08-05 从运行中的容器实测，非推断）**：

| 判据 | 实测 | 断点 |
|---|---|---|
| 什么时候 | 宿主机 `10:57 CST` / 容器 `02:57 UTC` | 后端 `ts` **带** `+00:00`，前端 `formatTs` 用正则 `/T(\d{2}:\d{2}:\d{2}\.\d{3})/` **切字符串把偏移丢了** |
| 什么操作 | 最近 400 行 = 175 HAL `DEBUG Cache updated` + 107 `app.audit` + 78 `app.db DEBUG` + 40 WARNING | **360/400 是背景噪音**；日志面板每 3 秒轮询两次 `system-logs/tail`，**这两次轮询又被写进它正在看的那份日志** |
| 什么流程 | `session_id` **24372 行全 `-`，非空 0 行** | ContextVar `current_session_id` 在 [`logging_config.py:34`](../api-service/app/core/logging_config.py) 定义好了，**全仓无任何 `.set()`** —— 字段是纯装饰 |
| 什么结果 | 执行器**有**流水（`test_case_runner` 15 处 `[case-runner]`） | 未跑过用例故未出现；不是缺口 |

（那 40 条 WARNING **全是 P1-29** 那个 `alerts/summary → 422` 每秒刷屏 —— 本片不修，
但它是"真 WARNING 会被淹掉"的现成实例，P1-34 做完后它会更刺眼，正好给 P1-29 当验收素材。）

**范围 —— 三件事，各自的修法优先级都取到了「去掉/换源」**：

| # | 做什么 | 修法档位 | 文件 |
|---|---|---|---|
| 1 | 前端按**本地时区**渲染 `ts`（`new Date(ts).toLocaleTimeString`），不再正则切串 | **换源**（后端早就给了带偏移的完整时刻） | `SystemLogViewer.tsx` + 核 `ZoneLogsAlerts.tsx` |
| 2a | 写侧：把日志面板**自指的**两条轮询加进已有的 `EXCLUDED_PATHS`，且**只对成功生效**（4xx/5xx 与未捕获异常照记） | **去掉** + **收窄** | `audit_middleware.py` |
| 4 | `AuditMiddleware` 每请求生成 `request_id` 并 `current_session_id.set()`；GUI 接上后端**早已存在却没法用**的 `session_id` 精确过滤（「只看这一次请求」，`/tail` 与 `/export` 同一套条件） | **换源**（基建已在，差一次赋值；**零调用点改动**，contextvar 自动贯穿 runner/HAL/SCPI） | `audit_middleware.py` + `SystemLogViewer.tsx` |

**明确不做（划界，防止越界）**：
- **读侧「隐藏轮询噪音」开关** → **不做**。立项时曾写进范围（原 2b），内审 F2 指出
  它与验收条留在原地不动、读起来像做了 —— 现移到这里并说明去向：本片给出的
  「还原一次操作」路径是**按 `request_id` 直接捞整条链**（点日志行 →「只看这一次
  请求」），不是靠过滤把噪音藏起来；而"让默认视图不刷屏"要动的是**写侧 logger
  门槛**，那是下一条的 P3-19。两件事，别混。
- **写侧 logger 门槛降级 / `Cache updated` 该不该是 DEBUG** → 留在 **P3-19**（已有条目，
  且原条目已注明「根 logger + file_app 均收 DEBUG，单纯降级站点**不会**减少行数」——
  那是另一件事，不是本片的可观察故障）
- **`alerts/summary` 422 刷屏** → 留在 **P1-29**（已在队列）
- **把 `./logs` 挂进容器** → **不做**。会与本地直跑的进程写同一个文件，正是 2026-08-05
  两个 API 抢 8000 端口那次事故的翻版
- **宿主机 `api-service/logs/` 41 GB** → 本地开发残留（容器那份 5 MB，按天轮转正常工作），
  不是产品缺陷，不进本片

**爆炸半径**：原 bug 最坏 = 排障靠猜（2026-08-05 实际发生：我自己拿宿主机文件当容器
日志讲，误导一轮）。修完最坏 = 排除名单吞掉本该看见的行 —— 所以排除**只对成功生效**
（内审 F1 的收窄：`/system-logs/frontend` 返 422 时，前端自己静默丢批、`client.ts` 又
跳过该 URL 防回环，审计这一行是**最后一处**痕迹）。加上排除只覆盖**自指**的两条，
过滤态在界面上恒可见可清除。**Y < X**。

**验收**：
1. 面板显示的时刻 == 操作员手表（含跨时区、含 `Z` / `+00:00` / `+08:00` 三种输入形态）
2. 同一次操作的 audit / runner / HAL 日志**带同一个 `request_id`**，可按它过滤成一条链；
   `/tail` 与「导出过滤结果」用**同一套**条件（内审 F3）
3. `session_id` 非 `-` 的行数 **> 0**（今天是 0）
4. 被排除的路径**失败时仍留审计痕迹**（内审 F1）
5. ⚠️ **默认视图仍会被 DEBUG 心跳刷屏**（实测最近 400 行里 253 行）—— 本片**不治**，
   见上方「明确不做」，去向 P3-19。别把本片当"日志面板已经清爽了"读。

**门**（每道配让它红的变异，见 ⓪④）：
- 行为门：走一次带中间件的请求，`session_id` **既非 `-` 也不为空**，同请求内多条日志
  **取值相同**、跨请求**取值不同**；被排除的路径**成功不记、失败照记**
- 不变量门：`logging_config.py` 里**每个写文件的 handler 都接了 `context_filter`**
  —— 内审 F4 用变异证明，拆掉 `file_app` 那一行会让本片功能对 app.log 整体归零，
  而当时 57 条测试全绿（原门只锁了测试自己挂的 filter，**没锁真实生效端的接线**）
- 不变量门：`EXCLUDED_PATHS` 双向 —— 每条都能在 OpenAPI 路径里找到（防写窄/拼错），
  且下载 / 导出 / 文件列表**不得**被任何排除前缀命中（防写宽，内审 F7）
- 不变量门：GUI 不得再「切时间戳字符串」，`datetime.ts` 不得出现 `timeZone`
  （内审 F8：`timeZone:'UTC'` 一行就能把本片修的 bug 原样装回去且全门皆绿）
- 行为门：`/tail?session_id=` 精确过滤能把整条链**完整**捞回、不夹带前缀相同的别人
  （内审 F9：这条后端路径此前零覆盖 —— 因为字段恒为 `-`，从没被真正用过）

**依赖**: 无。**现场半**: 无（纯本地可观察）。

### P1-35 — 无用日志不写 + 清晰过滤 ✅（2026-08-05 完成）

**目的（用户原话，两次）**：
> 「心跳 log 和 Cache updated log 的确很讨厌，需要 roadmap 提前解决问题。」
>
> 「**无用的 log，不能分析系统、测试、积累用于 AI 训练的 log，不应该被存储
> （无论是本地还是数据库），需要具备清晰的 filter 用于故障排除、测试分析。**」

**⭐ 由此确立的留存判据**（写日志前问自己）：

> 这一行**能不能**服务下面四件事之一 —— **分析系统 / 测试分析 /
> 积累 AI 训练语料 / 故障排除**？四件都不沾，就别写。
>
> 两条最常见的"都不沾"：
> ① **周期性无信息量心跳** —— 每次内容都一样，只证明"进程还活着"；
> ② **同一事实的第二份记录** —— 已经有更好的载体（计数器 / 别人的日志 /
>    专属文件）还要再写一遍。

**治理前后（同一容器、GUI 连着，实测）**：

| | 治理前 | 治理后 |
|---|---|---|
| app.log 增速（GUI 连着） | **228 行/分** | **0 行/分**（无操作时） |
| 心跳占比 | **90.1%**（6273 / 6965 行） | **0** |
| 4 个真实操作产生 | 淹在心跳里 | **正好 5 行**（一操作一行 + 失败那次的根因） |
| app.log 里的 DEBUG | 155 / 200 | **0** |

**删了什么**（三类，各配会红的门，见 `tests/test_p1_35_log_value_policy.py`）：

| 类 | 删的 | 判据 |
|---|---|---|
| ① 无信息量心跳 | `MetricsCache` 的 hit/expired/updated/cleared 四条 `logger.debug` | 命中率由 `_hits`/`_misses` 计数器如实记着，`get_stats()` 是读取口 —— per-event 日志是同一事实的第二份，且**监控广播器 1 Hz 只在 GUI 连着时跑**，恰好在操作员盯着看时刷得最凶 |
| ② 逐字重复第三方 | `app.db` 的 checkout / checkin / session-committed 三条 | SQLAlchemy 的 `sqlalchemy.pool` / `.engine` 已把同样事件记进 `db.log`（实测同时段 checkout 272 / checkin 272 / COMMIT 266，逐一对应） |
| ③ 说谎的死类型 | `InstrumentLog` 模型 + 三个 schema | 类名宣称"记录仪器操作历史"，实测**库里 0 行、0 写入方、0 读取方** |

**保住了什么**（删的是重复，不是信号，各配反向门）：
`DB session rollback`（WARNING，P1-29 那个 422 能查到根因的唯一来源）/
`DB connection established`（INFO，一次性）/ 缓存计数器与 `get_stats()`。

**过滤（服务"故障排除 / 测试分析"）**：
- 新增 **「🚨 仅异常」** 档 = `WARNING,ERROR,CRITICAL` 一次看全。
  后端 `level` 从单值扩成**逗号集合** —— 因为它是**精确相等不是门槛**，
  此前没有任何单档能表达「WARNING 及以上」（选 ERROR 漏 WARNING，反之亦然）。
  ⚠️ **仍是集合成员判断，不是序数比较**：`ZoneLogsAlerts`（P2-19 #258）的
  跨流去重依赖「不同 level 的流天然不相交」，改成门槛会让那里出错。
- **`/tail` 与 `/export` 合并成同一份谓词** —— `/export` 原先自己抄了一份
  （P1-34 内审 F3「屏幕 5 条、导出全量」就是这个母题）。顺带修掉本片一度
  自己引入的同类缺陷：导出发哨兵值 `__ISSUES__` → 后端精确匹配 → 导出 0 行。

**明确不做**：
- **六个专属 logger 的 `propagate` 双写原样保留** —— 关掉看着更干净，
  但那样 `app.log` 只剩 1.8%，`request_id` 的链会从操作员默认看的文件里
  消失，当场作废 P1-34。**`app.log` 的定位是总线**：故障排除天生跨切面
  （HTTP → runner → HAL → SCPI），必须有一个文件看得全。配了反向门。
- **`instrument_logs` 表本身不 drop** —— 需要 migration，而两台现场机器是
  brownfield 库，属另一类风险，进 Discovered 单独走。

**门**：13 条变异全红（含"删日志顺手把计数也删了"、"app.audit 改成不传播"、
"导出又抄一份谓词"三条**反向**变异）。全量 3111 passed。

<details><summary>原立项描述（2026-08-05 上午，仅心跳那一半）</summary>

**目的（用户原话）**：「心跳 log 和 Cache updated log 的确很讨厌，需要 roadmap 提前解决问题。」

**可观察故障**：操作员打开日志面板，**看到的绝大部分是每秒重复的心跳**，
自己刚做的那次操作被挤在中间看不见。P1-34 让时间对得上、让一次操作能串成链，
但**第一眼看到的仍是一屏噪音** —— 这是 P1-34 立项时就显式划出去的那半。

**实测（2026-08-05，容器 app.log）**：

| 来源 | 量 | 是什么 |
|---|---|---|
| `logger.debug("Cache updated")` / `("Cache expired")` | **1032 / 3976 行 = 26%**（空闲时占可视窗口 53%） | [`instrument_hal_service.py:155,167`](../api-service/app/services/instrument_hal_service.py) —— 指标缓存每秒刷一次，各打一条 |
| `app.db` 会话日志 DEBUG | 200 行窗口里 49 条 | `DB session committed` / `connection checked out|returned` |

**修法优先级从「去掉」起步，别一上来就加机制**：
1. **去掉**：`Cache updated` / `Cache expired` 有没有任何诊断价值？一次缓存刷新
   每秒两条 —— 先问该不该存在，而不是该打什么级别
2. **收窄**：`app.db` 这类**每请求必然发生**的会话日志走命名空间级门槛
   （⚠️ P3-19 原条目已注明：根 logger + `file_app` 均收 DEBUG，
   **单纯改站点级别不会减少行数**，必须配命名空间门槛一起做）
3. 只有前两条都不适用时才考虑面板侧过滤

**验收**：默认打开日志面板，**第一屏就能看见最近的真实操作**，
不需要滚动或过滤。给出治理前后的行数对比（同一段时间窗）。

**门**：不变量门 —— 每秒级重复的日志源不得再出现（按"同一 logger + 同一
消息模板在 N 秒内超过 K 条"派生，配让它红的变异）。

**依赖**: P1-34 先合（否则改完看不出差别 —— 时间还是错的、链还是串不起来）。

</details>

### P1-36 — 测试执行身份进日志（`execution_id` 串链）⬜（2026-08-05 用户提出）

**目的（用户原话）**：「如何能将测试例标注在 log 中。」

**可观察故障**：跑完一个测试用例，想知道"这次执行到底做了什么"，
只能靠时间戳前后猜。执行 id 现在**只是拼进消息文本**
（`logger.info("[case-runner] execution %s ...", execution_id)`），
不是结构化字段 —— 没法过滤、没法从执行历史一键跳过去。

**修法 = 把 P1-34 那套原样复制到执行维度**（同一个机制，零新概念）：

| 步骤 | 做什么 |
|---|---|
| 1 | `logging_config.py` 加 `current_execution_id` ContextVar，`ContextFilter` 注入（与 `session_id` / `instrument_id` 并列） |
| 2 | [`test_case_runner._run_case()`](../api-service/app/services/test_case_runner.py) 入口 `.set()` 一次 —— **零调用点改动**，这次执行期间 runner / HAL / SCPI 的每一条日志自动带上 |
| 3 | `/system-logs/tail` + `/export` 加 `execution_id` 精确过滤（与 `session_id` 同形） |
| 4 | 契约四步（新字段进 `LogEntry`）：`openapi.yaml` → `npm run openapi:generate` → `service.ts` → `mockServer` |
| 5 | GUI：日志表加「执行」列（点它隔离整条执行链）。⚠️ **「从执行历史一键跳转」本片未做** —— 内审 F7 指出：`SystemLogViewer` 不接 props、不读 URL 参数，**没有任何入口能带着 execution_id 跳过来**，那句可观察故障合并后仍成立，已进 Discovered；同条目 ⚠② 说的「显示用例名+时间而非裸 UUID」同样未做（徽章现在显示 id 前 8 位），一并进 Discovered |

⚠️ **两个必须先想清楚的点**：
① `execution_id` 与 `session_id` 是**两个不同生命周期**（一次执行跨多个请求、
   也可能完全不在请求里 —— runner 跑在后台任务），**必须各自一个字段**，
   别复用（P1-34 的注释里已经留了这句话）；
② 显示给人看的应该是**用例名 + 执行时间**，不是裸 UUID —— 但过滤判据仍用 id，
   别拿名字当键（同名用例会合并成一条假链）。

**依赖**: P1-34 先合（`ContextFilter` 注入机制与 GUI 过滤入口都在那片建好）。

### P1-37 — mock 也产真命令串并记 `scpi.log` + 回复显式标 `simulated` ✅（2026-08-07，PR #303）

**目的（用户原话）**：
> 「我们当前都是 mock，但是**下发的 SCPI 内容是不是还是应该记录**（Mock 回的消息不是真消息，**要不要也记录**呢）？」
>
> 「**今后 log 是我们主要的调试手段，让它尽快完整/正确/高效的就位。**」

**可观察故障**：本地跑在 mock 下，**`scpi.log` 恒为 0 字节** —— 整个仪器交互层
在日志里不存在。想知道"这次执行到底往仪器发了什么"，本地永远查不到。

**实测（2026-08-05）**：`/app/logs/scpi.log` = **0 字节**。根因不是"记了没写"，
是 **mock 驱动压根不生成命令串**：

```python
class MockBaseStation:
    async def connect(self):
        await asyncio.sleep(0.3)      # 就这样
        self._set_status(CONNECTED)
```

**⭐ 这一片的核心区分（想清楚再动手）**：

| | 谁决定的 | 结论 |
|---|---|---|
| **下发侧**（我们发什么命令） | **我们自己的代码** —— 跟仪器真假无关 | **必须产出真实命令串并记录**。mock 下同样能验命令**形式** |
| **回读侧**（仪器回什么） | 真机 → 真值；mock → **我们编的** | **记，但必须显式标 `simulated`**；**绝不进** measurement.log / 报告 / KPI 字段 |

**为什么下发侧值钱 —— 有现成的铁证**：P1-33 按手册补了 8 组 MAC 配置命令，
命令**形式**（`FULL_TPUT` / `APOLicy` 枚举 / `MS5` / TDD 六整数 / 两条 apply 的
先后）本来**在本地就能验**，现在只能等现场。同理 F64R 系列、UXM KPI 那批 ——
这个项目的主要痛点就是 SCPI 驱动开发，而它恰恰是本地零可观测的那一层。
外加用户点名的 **AI 训练语料**：真实的命令序列是语料主体，mock 白白产不出来。

**为什么回读侧危险**：假回复被当真值消费，是本仓库反复在治的母题
（P1-32「不假成功」/ #275「未知口径不写进 `_dbm` 字段」/ P1-25「演示脚本
被标成绿色真实执行」）。**记假回复不危险，危险的是它没被标出来。**

**范围**：
1. mock 驱动改成**走真驱动同一条下发路径**产出命令串（复用 `_log_scpi_write`，
   不新造机制），只在"发给谁"那一步分叉
2. mock 的回复走 `_log_scpi_response`，行内显式 `simulated: true`
3. **反向门**：`measurement.log` / 报告 / KPI 字段里不得出现 `simulated` 来源的值
4. ⛔ **`hal_mode` 不够用，别拿它当 `simulated` 的判据**（Codex #285 R2 抓出，
   立项时我写的「hal_mode 已存在，不重复造标记」**是错的**）——
   `ContextFilter` 注入的 `hal_mode` 取自 **HAL 服务的全局 mode**
   （`logging_config.py` 的 `get_hal_service().mode.value`），而 HAL 服务
   **明确支持 per-instrument 覆盖**（`instrument_hal_service.py` 的 docstring：
   「global default is mock；per-instrument `'real'` override **IS still
   honoured**」，反向亦然）。
   后果正好打在本片的要害上：**全局 real 下被强制 mock 的那台仪器，
   它的假回复会记成 `hal_mode=real`** —— 假数据冒充真数据，而这正是
   P1-37 要防的那件事。
   **所以 SCPI 行需要 per-driver 的来源标记**（由驱动实例自己给，
   `_log_scpi_*` 已经在传 `extra={"instrument_id": ...}`，同一处加即可），
   不能复用 `hal_mode`。

⚠️ **动手前必须先定的一件事**：mock 到底"复刻多深"？
只产命令串（不模拟状态机）最省且已能验形式；要模拟到能跑完整序列则大得多。
**建议先做前者**，把后者留成独立增量 —— 别一上来就做成第二套驱动。

**依赖**: P1-36 先做 —— 那片落地 `execution_id` 的 contextvar 之后，
本片新增的**一大批** SCPI 日志**天生就带执行身份**，不必回头补验。

**收口**：UXM/F64/X-Series SA/EMCenter 转台/EMCenter Switch 五类现场 mock 各覆盖
一个代表性操作；命令构造常量或 profile 与真实驱动共用。SCPI TX/RX 记录携带
`driver_source=mock` 与 `simulated=true`，不依赖全局 `hal_mode`。`ScpiExchangeRef`
同步保存来源，模拟往返不能满足 transport gate，也不能持久化为正式执行证据。
测量归一化边界把 Mock/缺失仪器参与的 KPI 写为 N/A，analysis 保持 UNKNOWN，报告
不再序列化随机模拟数值；RF switch 的无问号命令按真实驱动语义记录 TX/OK write。

### ~~P1-38~~ — 活动告警卫生：测试污染隔离 + 精确清理 + summary badge ✅ Done（PR #321，2026-08-11）

**目的（用户原话）**：
> 「主控台右侧的『活动告警』还有必要存在吗？是不是可以让主控台能够有空间
> 展现抽屉打开后的内容？」

**实测（2026-08-05）**：`alerts` 表 **674 行，`source` 100% 是 `test_suite`**
（2026-05-05 ~ 08-01），面板上那 **337 条"活动告警"一条真的都没有**。

**当时根因**：**没有生产者**。runner 相位失败只落日志、不进告警表
（当时 P3-19 尚有「执行失败告警通道」待办；现已由最后一片完成）。所以半屏宽度在展示测试垃圾。

**范围（两件事，别混）**：
1. **清污染** —— 674 条 `source=test_suite` 出库；**同时**堵住测试往生产库
   写告警的那条路（否则清完还会长回来 —— 这才是真修法，光清是治标）
2. **面板去留** —— 告警这个**概念**该留（P1-8 校准门 / P1-9 DUT attach 那些
   fail-loud 天然就是告警源），但现在这个**面板**该收：收窄成计数徽章，
   把腾出的宽度给日志与抽屉内容。真接生产者是独立增量（后由 P3-19 最后一片完成）。

⚠️ **顺序要求**：先查清楚「测试为什么能写生产库」再清数据 —— 反过来做，
清完下次跑测试又长回来，等于白干。

⚠️ **依赖 P1-29，必须排在它之后**（Codex #285 R1 抓出）—— 上面第 2 件事说的
「收窄成计数徽章」，那个徽章渲染自 `/dashboard/alerts/summary`，而 **P1-29
记录的正是这个端点被 `/alerts/{alert_id}` 遮蔽、恒返 422**；`AlertPanel`
现在每 10 秒轮询它一次。P1-38 若排在前面，等于把新面板建在一个已知坏掉的
端点上 —— 做完仍显示不出计数，而人会以为是 P1-38 没做好。
**队列已据此把 P1-29 提到 P1-38 之前。**

**依赖**: **P1-29**（见上）。**现场半**: 无。

**收口实况（PR #321，2026-08-11）**：当前本机开发库核对到 `alerts` 共 **674 行**，
来源只有 `test_suite`，分布为 **337 active + 337 dismissed**，创建时间覆盖
**2026-05-05 ~ 2026-08-01**；没有其它来源。追溯确认 P3-15 已把原写入测试改用
独立 SQLite engine + `get_db` override，污染源已经断开；本片新增 **G20** 常驻门，
枚举 pytest 的 `test_*.py` / `*_test.py` 两种命名下所有 `source=test_suite` 写点，
并要求所在模块同时具备 SQLite `create_engine`、`app.dependency_overrides[get_db]`
和 `Base.metadata.drop_all` teardown，防止以后换一个测试文件再次写进开发/现场库。

历史存量采用精确白名单清理工具：必须同时命中 `source=test_suite`、
`created_by=test_suite`、`created_at < 2026-08-02`，以及两套完整内容字段之一——
`WARNING: Alert / Test alert / warning / warning / active` 或
`INFO: Alert / Alert to dismiss / info / info / dismissed`
（依次为 title / message / severity / alert_type / status）。工具默认 **dry-run**，
只有显式 `--execute` 才会在单事务中删除，异常回滚。实际操作先以 dry-run 确认
`matched=674, deleted=0`；随后建立可恢复备份表
`alerts_p1_38_backup_20260811`（674 行），再执行 `--execute`，结果为
`matched=674, deleted=674`。最终本机开发库 `alerts=0`、`test_suite=0`；上述
674 行备份表保留为恢复路径。

主控台已移除活动告警详情列表与 5/12 宽大面板，只在全宽实时日志标题栏保留
`/dashboard/alerts/summary` 的紧凑 badge；告警详情 REST API 与数据模型仍保留，
供未来生产者接入复用。summary 后端改为单次 `GROUP BY` 聚合，避免五次独立查询在
并发写入时拼出互相矛盾的快照；未知 severity 仍计入 total，GUI 遇到查询失败或
`total != 四级计数之和` 时红色 fail-loud，不会把未知/不一致状态显示成绿色
“无活动告警”。**生产告警生产者没有在 P1-38 实现；后由 P3-19 最后一片补齐。**

---

### P1-39 — 让人拿得到 ID：执行/用例编号在界面上可见可复制、一键跳日志 ✅ Done（#292，2026-08-06）

**目的（用户原话）**：
> 「测试例的编号能在哪里查到？除了log以外」

**实测（2026-08-06，三个界面全查过）**：

| 界面 | 显示 ID 吗 |
|---|---|
| 测试用例库（`TestCaseLibrary.tsx`） | ❌ `tc.id` 只当 React `key`，不渲染 |
| 执行历史（`HistoryTab.tsx`） | ❌ `record.id` 只当 `key` 与「生成报告」的 loading 标记 |
| 报告详情（`ReportViewer.tsx`） | ⚠️ 有「执行ID」卡片，但 **`slice(0,12)` 截断、不可复制**，且**只有 execution id，测试例 id 一个字都没有** |
| **待归档执行**（`PendingExecutionsList.tsx`） | ❌ 同前三者 —— 内审 F7 补枚举出的**第 4 个**站点，**本片未覆盖**（见下方 ⚠️） |

⚠️ **不写行号**（内审 F6）：上一版这张表写了 `:434` / `:302/378` / `:279-284`，
本片改完**全部漂掉** —— 正是「指针本身也是未核断言，坐标要稳、绝不写行号」那条。

⚠️ **本片只覆盖前 3 个**：`PendingExecutionsList`（报告页第一个页签，跟系统日志同页并列）
两张表同样只把 id 当 React `key`。按 ⓪③「枚举进 backlog 不进当前改动」不在本片做，
但**完成判据据此改口**：P1-39 是「三处露出 + 一键跳转」，不是「全站 ID 可见」。

**这是 P1-34/P1-36 留下的半截功能** —— 日志能按 `request_id` / `execution_id`
精确过滤了，**但没有任何界面告诉你那个 ID 是什么**：过滤器有了，钥匙拿不到。
今天唯一的取数路子是绕开界面（打 API / 查 DB / 开 F12 看网络面板）。
报告页那个卡片尤其别扭：截断到 12 位而日志列表显示前 8 位、过滤要全长，
**正好卡在「看得见但用不了」**。

**范围（4 条，第 4 条是真正省事的那个）**：
1. 执行历史每行加**短标签 + ID**（短标签 `YYYYMMDD-HHMMSS` 供人认，点击复制完整 UUID）
2. 用例库卡片加测试例 ID（前 8 位 + 点击复制全长）
3. 报告页「执行ID」卡片改成**可复制全长**（去掉 `slice`）
4. **一键跳转** —— 执行历史那行加「看日志」按钮，带 `execution_id` 跳到系统日志页
   并预填过滤。前 3 条只是让人能**手抄**，第 4 条让人**不用抄**。
~~5. 系统日志默认新在最上 + 方向可切~~ → **2026-08-06 拆出 P1-44**（理由见下）。

⚠️ **短标签只做「人认得出」，索引仍是 `execution_id`**（用户原话「测试例 ID 太长，
还有什么别的唯一索引方式」）——**不造第二个真值源**：跳转/过滤一律用完整 UUID，
短标签仅用于显示与肉眼对时间。它派生自 `started_at`，**零新字段**（`TestExecution`
表里没有别的短字段，已逐列核过）。
⚠️ **短标签取本地时间，不取 UTC**：后端建执行快照的名字（`test_case_runner.py:134`
的 `one shot [执行 20260805-151251]`）用的是 `datetime.utcnow()`，而日志面板 P1-34
已统一显示**本地时间**。标签要跟**日志时间线和墙上的钟**对得上，所以取本地；
与快照名差 8 小时是**预期**，因为那是名字不是索引。

⚠️ **为什么把排序摘出去**（2026-08-06，Codex #292 走了三轮之后用户拍板）——
不是"怕再出问题"，是**证据指向明确**。三轮 6 条 P2 的分布：

| 来源 | 条数 |
|---|---|
| **排序**（详情卡位置 / key 撞车 / 窗口相对序号 / autoScroll 方向 / traceback 翻转） | **5** |
| 跳转接线（挂载竞态） | 1 |
| **ID 展示**（`CopyableId` / 短标签 / 三处显示） | **0** |

「让人拿得到 ID」那部分**三轮零 finding**，所有麻烦都来自顺手接的排序。
且每一轮的 findings 都由上一轮修复引入 —— 改动面在自我繁殖，而繁殖源可以
干净摘掉。判据与 S5 那次「9 条里 7 条集中在同一文件 → 摘出去单开」相同
（见 memory `feedback_review_loop_scope_discipline` ②：
**上限触发条件不适用时看 finding 的文件分布，不看轮数**）。

⚠️ **接缝在哪（实现时别自己造）**：`[case-runner] 用例 <test_case_id> (<名字>)
开始执行, execution=<execution_id>` 这一行**同时**带着两个 ID，是既有的天然
关联点；跳转只需把 `execution_id` 传给 `SystemLogViewer` 已有的 `executionFilter`
（P1-36 已实现，含 `buildLogQuery` 与 `isolateExecution`），**不需要新后端契约**。

⚠️ **已知不在链上的那一行**：发起/取消执行的 `app.audit` 汇总行带不上
`execution_id`（结构性，见 Discovered 里 Codex #286 R2 那条）。第 4 条跳过去
之后看不到那行 HTTP 汇总是**预期行为**，别当 bug 修 —— 要看它走「请求」那一跳。

**依赖**: 无。**现场半**: 无。

---

### P1-43 — 日志翻页：看得到 200 行（及扫描窗口）以外的历史 ✅（2026-08-07 完成）

**目的（用户原话）**：
> 「首先 200 行显示，那想看 200 行以前的 log 怎么办？」

**现状（已核）**：`/system-logs/tail` 的 `lines` 是 `default=200, ge=1, le=2000`
（`api-service/app/api/system_logs.py:271`），**天花板在后端**：反向扫描封顶
`_TAIL_SCAN_LIMIT = 20_000` 行（`:109`），带过滤时窗口也是这个。
**没有分页、没有游标、没有时间范围。**

想看更早的，今天**唯一的路是导出** —— `/export/{filename}` 是**全文件**流式过滤，
不受 20000 约束（P1-34 已确认）。但那是下载文件，不是在界面上翻。

**从 P1-39 拆出的理由**：P1-39 那几条都是「把已有的东西露出来」，纯前端展示；
本条要动**后端取数契约**（游标或时间范围），量级不同，混在一起会让 P1-39 的
范围超出它那句目的。

**实施实况（2026-08-07）**：选择游标式「加载更早 N 条」。`/tail` 保持原有
20,000 行实时扫描预算，只在响应中增加不透明 `older_cursor` / `has_older`；新增
`/system-logs/history` 由用户显式点击触发，使用独立且有界的单页扫描预算，按文件
字节边界继续反向扫描，不会从文件尾重复解析。稀疏过滤即使一页零匹配也推进游标；
游标绑定文件身份、初始快照 EOF 与固定大小的分页边界/EOF 双锚点，允许 EOF 后正常追加，
但截断、换代或锚点内容被原位改写时 fail-loud；固定样本使单页校验成本不随翻页深度增长。
输入游标在扫描前后都复验（最终页同样执行），校验、扫描和新游标生成使用同一个已打开
文件描述符，轮转时不混读两代文件。它不是全文不可变快照；归档 `*.log.*` 已进入文件选择器。

GUI 首次加载历史会自动冻结实时轮询，把更早页前插到当前快照；文件、过滤、手动刷新
或重新开启自动刷新时重建尾页，旧请求由 generation token 隔离，不能跨文件/跨过滤
污染新快照；timer 会同步清除，已排队回调也由冻结 ref 短路。OpenAPI、生成类型、手写
类型、真实 service、mock server/database 同步更新，mock 用 260 行样本提供可达的正常续页、
无效游标、过滤及稀疏空页推进，而不是固定空响应。
常驻 G14 明确禁止把历史端点接入轮询，并守住冻结与前插语义。详细契约见
[`design/p1-43-log-pagination.md`](design/p1-43-log-pagination.md)。

内审 R1 的 4 条 P2 已全部闭环：分页边界/快照尾部改写由双锚点拒绝；校验/扫描/编码绑定
同一文件描述符消除轮转 TOCTOU；历史模式同步清 timer 并短路排队回调；mock 不再是固定
空响应。配套变异分别破坏区间指纹、timer 短路与 mock 历史扫描，三道门均按预期转红；
轮转测试在游标校验后替换路径，仍只返回旧文件描述符中的同代内容。R2 又拦下扫描期间
改写会被新 hash 收编，以及累计区间 hash 导致 O(N²) 两条 P2；现已改为扫描前后复验输入
双锚点（含最终页）与恒定 64 字节级样本，并收窄为“分页连续性”而非全文快照承诺。
最终完整后端回归 `3402 passed / 5 skipped`，GUI production build exit 0；内审尾修复结论
CLEAN，GitHub Codex 外审 R1 在合并代码 HEAD `d696d7a` 上 clean。

**依赖**: 无。**现场半**: 无。

---

### P1-44 — 日志排序方向（新在最上）+ traceback 续行归组 ✅（2026-08-07，PR #303）

**目的（用户原话）**：
> 「当前系统日志显示是最新的内容在最下方，而不是最上方，每次看新内容要拉下去，
> 反使用直觉，为什么不能跟『实时日志』保持一样的方式？」

⚠️ **用户的前提要先纠正**（已实测）：两个面板**排序完全相同**（都是旧上新下），
真正的差别是 `ZoneLogsAlerts` 有 `autoScroll` 自动滚到底、`SystemLogViewer` 没有。

**⚠️ 这一片的核心不是"加个 reverse"，是先定义清楚"一条日志是什么"。**

`api-service/app/api/system_logs.py` 的 `_parse_log_line` 对**每个非 JSON 行**
（Python traceback 续行）单独造一个 `LogEntry(level="RAW", ts="")`。
所以翻转扁平数组会**把 traceback 内部的行也翻掉**，父错误跑到续行块后面 ——
而降序若是默认值，**栈回溯默认不可读**（Codex #292 R3）。
先做**续行归组到父记录**，再谈翻转，否则"翻转"这个动作在语义上就没定义好。

**已经踩过的坑（P1-39 三轮外审的全部产出，实现时直接拿去用，别重踩）**：

| # | 坑 | 修法 |
|---|---|---|
| 1 | 详情卡渲染在**整张表之后** —— 升序时用户看表尾恰好在旁边，降序后展开顶部行、详情在 200 行外，点了像没反应 | 详情改成表内 `<Table.Tr colSpan>`，紧跟自己那行 |
| 2 | 展开态按**下标**记（`Set<number>`）—— 降序+自动刷新下下标全移位，展开的行会跳到别的日志上 | 按**条目身份**记 |
| 3 | 身份用 `(ts, logger, msg)` 三元组 —— 实测 `scpi.log` 尾 200 行只有 **71 个不同三元组、最坏一组 25 次** | 身份取**全部字段**（含 `raw`/`session_id`/`execution_id`/`instrument_id`） |
| 4 | 手拼 `#N` 后缀 —— `foo` 第 2 次得 `foo#1`，而一条字面叫 `foo#1` 的消息第 1 次也是 `foo#1` | `JSON.stringify` 编码（对数组单射） |
| 5 | 出现序号按**当前窗口**计 —— 自动刷新时最旧那次滚出窗口，剩下的重编号，展开的 key 挪到内容不同的行 | 身份取全字段后此问题自然消失 |
| 6 | `ZoneLogsAlerts` 加方向开关后，`autoScroll` 仍 `scrollTo(scrollHeight)` —— 切到「最新在最上」反而把最新条目藏起来 | 滚动方向跟随 `sortDesc` |
| 7 | 就地 `reverse()` 会改掉 React state 数组 | 必须 `[...arr].reverse()` |

**门**：P1-39 里写过一版 G12（守「不就地 reverse」+「展开态按身份」+「身份含全字段」），
六条变异全红，随本次拆分一并摘出 —— **实现本片时直接恢复它**
（在 [#292](https://github.com/swang430/Meta-3D/pull/292) 的 `95dbdb0` 里）。
⚠️ 门里要**先剥注释再扫代码**，否则注释里引用后端的 `matched.reverse()` 会假红。

**依赖**: 无。**现场半**: 无。

**收口**：两个日志面板统一默认“最新在最上”，可切方向；先将 traceback/RAW
续行归到父条目再排序，展开详情留在对应表行内。稳定身份由全部字段与续行内容构成，
并从新到旧计数，历史 prepend 不会让已有展开态跳行；自动滚动跟随方向。后端
tail/history/export 同样按父行做过滤并保留整组续行，客户端多选级别也先归组再筛选。

---

### P1-45 — 现场验证项 → 诊断序列 / 正式 TestCase 映射 ✅（2026-08-06 完成）

**目的（用户原话）**：
> 「关于硬件 blocked，序列载体是什么意思，如果是验证脚本，我是想让你把它们挂在
> 『调试序列+单阶段』上，你是这么理解的吗？」

**是的，但要补一条边界。** 驱动调试载体 = `api-service/app/diagnostics/sequences/` 下
checked-in 的诊断序列，在 GUI「调试序列」面板里点一下就跑；正式测试载体 =
MIMO_OTA TestCase。两者都**不是临时脚本**。现场应当是「点它、看数、抄回来」，而不是
到了现场写代码。

**为什么必须是序列不是脚本**（CLAUDE.md 已有规矩，这里只记它的落地缺口）：
脚本不查源码 → 重复犯已经修过的错（2026-07-21 现场铁证：懒重连早已存在，脚本还在
手动重连）；脚本是一次性的 → 跑完只剩终端那一屏。序列过 review、有测试，live response
会返回完整 `steps`（含仪器原始回复 `step.raw`）；但当前 `DiagnosticRun` 审计行只持久化
参数、成败、耗时、操作人与**最多约 2048 bytes、可能截断的 `output_excerpt`**，且诊断序列
endpoint 没有传 `hal_trace_log_path`，所以不能承诺审计行永久保留完整 raw 或可追溯日志路径。
**当前现场操作要求**：离开 live 结果前必须导出或复制完整响应；截断摘要只能用于快速回顾，
**不能作为正式证据，也不能据此承诺下次可完整对照**。

**问题不是规矩没写，是映射没人做。** CLAUDE.md 早写了「每记一条『这个得现场验』的
backlog，**同时问它落在哪个序列里**；没有就出发前补一个」。P1-45 实跑 loader 确认
当前 12 个 GUI 可见序列，并逐行核对 TestCase 正式执行路径。结论已落到上方 Blocked 表：
13 条未完成/现场半/HOLD 行中，**2 条已有合规载体、7 条部分覆盖、4 条没有合规载体**。
这不是说 9 条已经现场验证，只说明它们有可复跑的承载路径；mock 跑通也不能代替真机证据。

**范围与收口（docs-only，本片没有写任何序列）**：
1. ✅ 「🚧 Blocked on hardware」表逐行写明诊断序列、正式 TestCase、部分覆盖或无载体，
   并给出 loader/API/GUI/TestCase runner 注册证据。
2. ✅ 修 stale：`propsim_f64_p08_gate` 已由 P1-24 写好并 mock 跑通；P2-13 也不是“无载体”，
   而是 TestCase precheck 半覆盖（实测 IMSI 仍有回退手填缺口）。
3. ✅ 只有 P1-33 判定集缺口并入已批准 P1-46；其余无/半载体项保留在原
   Discovered / Blocked / HOLD / P 项，不自动变 backlog。
4. ✅ 全文当前片措辞统一指向顶部 Current Focus，不再把会漂移的动态状态写进条目正文。

**诊断序列按「问的是什么」分类；正式测试/校准/对比流程另列**（沿用 CLAUDE.md 的
A–D 分类，但不拿它覆盖正式流程载体）：

| 问什么 | 载体形态 | 现状 |
|---|---|---|
| **A 通不通**（命令支不支持） | 只读普查序列 | 已有 `uxm_scpi_compatibility` / `propsim_f64_health` 等；P1-2 仍是事项级半覆盖。P1-46 在本类**只做** P1-33 `MAC_CFG_MANDATORY` 判定集对齐 |
| **B 返回什么字面值** | 同上，读 `step.raw`（**不是** `detail`） | 已有 `uxm_kpi_readback` / `propsim_f64_state_machine`；本类没有 P1-46 新增范围 |
| **C 一串动作之后会怎样** | **剧本式序列** | P1-46 在本类**只新增** `uxm_idempotent_write_probe`；P1-17、P1-6 等其它剧本缺口保留原 Blocked / HOLD，不并入 |
| **D 一轮要多久** | 序列记录 `duration_ms` | 现有序列具备计时字段；这不代表事项级或正式流程载体完整 |
| **正式测试 / 校准 / 结果对比** | MIMO_OTA TestCase 或对应正式流程 | 不属于 A–D 诊断分类；P1-4 / P1-5 / P2-13 等结论以上方 Blocked 表为准，均不并入 P1-46 |

**依赖**: 无。**现场半**: 无（本片是出发前的准备工作本身）。**代码变更**: 无；
不宣称真机 SCPI 已验证，不以 `onsite-observed` / `unverified` 代替正式通过。

---

### P1-46 — 补已批准的 UXM 载体与判定缺口 ✅ Done（2026-08-06，#296）

**缺口清单**（2026-08-06 普查，别重查）：

⚠️ **原清单里的 A / B 两条是我搞错的，已删**（Codex #293 校正，前提逐条核过）：

| 我原以为缺的 | 实况 |
|---|---|
| P1-33 的 MAC 配置命令 | ⚠️ **半覆盖，别当已完成**（这是同一问题上的**第三版**认定，前两版都错，见下方 ⚠️） |
| ~~UE L3 报告 RSRP/RSRQ/SINR 口径~~ | ✅ **已覆盖** —— `uxm_kpi_readback` 的步骤 ⑦ `UE L3 测量报告 (RSRP/RSRQ/SINR 口径)` 就是干这个的，`raw=rep_raw` 存原样回复，代码注释写着「口径未知，本序列就是来定它的」 |

⚠️ **P1-33 这一条我判了三次，前两次都错**（Codex #293 R1 → R2 逐步逼出来的）：

| 版本 | 我的说法 | 错在哪 |
|---|---|---|
| 第一版 | 「❌ 无载体，要扩 `uxm_scpi_compatibility`」 | 只读了文件头 docstring —— `_all_commands()` 是**动态枚举**，docstring 当然不会列出 P1-33 后填进去的命令 |
| 第二版 | 「✅ 已覆盖」 | **矫枉过正**：命令被探 ≠ 判定说得出「MAC 配置被接受了」 |
| **第三版（当前）** | **⚠️ 半覆盖：探了，但判定集不对** | — |

**第三版的依据（逐条核过代码）**：

1. **一边恒红** —— `TDD_PATTERN` 在 `_CRITICAL_NAMES` 里，而它在
   `UxmLteNrIratProfile` 上**是 `None`**（P1-33 逐条 grep 手册原件确认「手册 0 命中」，
   TDD 在本仪器上是**六个数**不是 pattern 字符串）。而
   `uxm_scpi_compatibility:520-533` 的 `critical_undefined` 会把所有
   「在 critical 集里但 profile 上不是 str」的收进来并让 `success = False` ——
   **这个序列在 IRAT 方言上永远不可能成功**。
   ⚠️ 这是**现有序列的活 bug**，不是本片新引入的；同一形态在 :146-152 已经处理过一次
   （`MEAS_BTHROUGHPUT_DL_BLER` 因为同样理由被移出 critical 清单），**`TDD_PATTERN` 漏了**。
2. **另一边假绿** —— P1-33 真正要求被接受的那批在
   `uxm_base_station.py:1736` 的 `MAC_CFG_MANDATORY` 里：
   `PDSCH_SCHED_ALGO / PDSCH_AMC_ENABLE / PUSCH_AMC_ENABLE / PDSCH_MCS /
   PDSCH_RB_ALLOC / TDD_PATTERN_STATE / TDD_PERIOD / TDD_DL_SLOTS /
   TDD_DL_SYMBOLS / TDD_UL_SLOTS / TDD_UL_SYMBOLS / CSIRS_PORTS /
   QCONFIG_APPLY_ALL / CONFIG_APPLY`。实测其中
   **`PUSCH_AMC_ENABLE` / `PDSCH_RB_ALLOC` / `CSIRS_PORTS` / `TDD_DL_SYMBOLS` 等都不在
   `_CRITICAL_NAMES` 里** → 它们被拒也只会总结成「non-critical unsupported … OK」。

**所以「枚举到了」不等于「验证了配置被接受」。** P1-46 的这一格改成：
**把 `uxm_scpi_compatibility` 的判定集跟 `MAC_CFG_MANDATORY` 对齐**
（并把 `MAC_CFG_NO_EQUIVALENT` 那档显式排除，别让注定 None 的命令把整轮判红），
**不是加重复探针**。

**真正的缺口（全在 C 类）**：

| 缺的 | 类 | 修法 |
|---|---|---|
| **UXM 在小区 ON 态同值写 band/duplex 会不会掉 DUT** | **C** | **新写** `uxm_idempotent_write_probe` |
| 开关1 inherit 只核对频率、层数是盲区 | C | 保留 Discovered；先找到可证明“实际生效层数”的观测手段，再决定是否升格 |
| P1-6 现场半：真 idle-close 复现 | C | ⚠️ **移出本片**，且 **我上一轮把它归错了驱动**（Codex #293 R3）—— P1-6 的正式定义是「**FS16 / UXM / ENA** silent-reconnect 集成测试」，条目原文明写 **F64 已有 12 个集成测试**、缺的是另外三个驱动。我上一轮写「F64 侧剧本、跟 `propsim_f64_state_machine` 一起排」**正好指向唯一不需要的那个**。正解：载体打在 **FS16 / UXM / ENA** 三个上 |

⚠️ **最值钱的是那条 C 类**：「ON 态同值写 band/duplex 掉不掉 DUT」是**真机零实证** ——
今天既没有载体，也没有任何依据。猜错了现场直接掉 DUT，而掉 DUT 意味着重新 attach，
在 P0-5 那段窗口里代价极高。

⚠️ **动手前必须先查手册**（NotebookLM `236d9621-e3ce-4ed1-a8e1-7819b674dbcd`）：
「小区 ON 态下同值写 band / duplex 会不会触发内部重配」这件事**手册说没说，现在不知道**。
按规矩要拿**手册原文**，不要它的推断；查得到就照手册写，查不到就如实标「手册未说明」
并让序列**先读状态再决定发不发**。

⚠️ **C 类序列的硬约束**（CLAUDE.md 已定，这里重申因为最容易违）：
① 只放**手册有依据 + 生产驱动已在用**的命令（F64 禁盲试同样适用）；
② 带动作的剧本**必须先查状态再决定发不发**，并在每步后读一次错误队列；
③ 出发前用 mock 跑一遍 —— **只证明序列本身不崩，不证明问对了问题**，别当验收。

**本片的交付物（两件，别再多）**：
1. **写 `uxm_idempotent_write_probe`**（C 类剧本，**只做 ON 态同值写 band/duplex 掉不掉 DUT**）
   —— 必须过 review 再写。

   ⚠️ **「inherit 层数盲区」已从本交付物剔除**（Codex #293 R3 的 P1）——
   原先把它跟同值写捆在一条序列里，但**没有指定怎么观测层数**，而实况是
   **今天不知道怎么观测**：① 源 backlog 明写「UE capability **测不出**小区实际
   生效在比请求更少的层数上」，配置查询**可能只是回声**；② `MIMO_DL_LAYERS` 在
   `UxmLteNrIratProfile` 上是 `None`（只有 `Uxm5GNRTestAppProfile` 有），
   而序列规矩是「只放生产驱动已在用的命令」；③ 我要求的查手册范围只写了
   band/duplex，压根没覆盖层数。
   **后果**：照原样做，序列会满足「同值写」那一半而通过，却把一个**继承下来的
   2 层小区当成 4 层实验**报上去 —— 比没有序列更危险。
   **正解**：先解决「有没有一条能读到**实际生效层数**的命令」（查手册；查不到就
   定一个显式的 raw 回复 / 面板比对判据），**有了观测手段再排**，不要捆进本片。
2. **把 `uxm_scpi_compatibility` 的判定集跟 `MAC_CFG_MANDATORY` 对齐**
   （见上方 P1-33 那条）—— 纯判定集调整，不加探针。

⚠️ **P1-6 的 FS16 / UXM / ENA idle-close 剧本不在本片**（Codex #293 R2→R3）——
它跟上面两件不同仪器、不同前置，塞进来会让本片范围失控；已单列进 Discovered。

**依赖**: P1-45 ✅（映射见上表）。**现场半**: 本片产出的序列本身要现场跑，
但**写序列不需要现场**。

**完成实况**：`uxm_idempotent_write_probe` 已实现 ON 态 BAND 同值写安全剧本；
`uxm_scpi_compatibility` 已按 mandatory / no-equivalent / manual-scope 重做判定，
诊断互斥、同步 VISA 不阻塞事件循环、取消等待真实 IO 收尾、结构化诊断证据持久化均已过门。
手册没有覆盖 LTE_NR_IRAT，故该方言仍保持 `unverified/manual_scope_mismatch`，没有假绿。

---

### P1-47 — P0-5 SCPI 指令→回复→接受→生效→结果证据闭环 ✅（2026-08-07，本地 A/B/C 已完成）

**可观察故障**：2026-07-21 现场已完成 DUT attach 与转台四方向吞吐，但同一次执行里
拿不出关键 SCPI 的完整配对、仪器接受证据和实际生效状态。今天只能证明“物理链路能跑”，
不能证明“正式 TestCase 按预期参数完整控制了 UXM/F64/转台”，所以 P0-5 不能关闭。

**不做的两个极端**：

- 不只补几列日志——那最多证明程序打算发/传输完成，仍证明不了仪器接受和生效。
- 不建设全仪器通用证据平台——本片只覆盖 P0-5 使用的 UXM、F64、转台和 TestCase；
  公共层只沉淀 SCPI 往返配对。

**证据等级**：E0 Intent → E1 Transport → E2 Accepted → E3 Applied → E4 Outcome。
每项只申报实际达到的最高级；`*OPC? == 1` 只算操作完成，普通配置 query 在手册没有
口径保证时不得冒充 E3。

**NotebookLM 双实证（2026-08-06 已实际连通并两轮纠偏）**：

- F64 notebook `982222b7-4953-46cd-9949-00fa97882353`：手册原文支持
  `DIAGnostic:SIMUlation:STATE?`、`DIAGnostic:SIMUlation:MODel:STATE?`、
  输入/输出测量状态与结果、`*OPC?`、`SYSTem:ERRor?`，且 §20.6.1.1 明确示范
  写后用对应 query 回读。严格边界：输入/输出测量返回**空字符串**时手册均未说明语义；
  只有输出结果未就绪明确返回 `not ready`，两者绝不合并。
- UXM notebook `236d9621-e3ce-4ed1-a8e1-7819b674dbcd`：手册原文明确多数配置要
  APPLY 才进入协议栈，但没有保证普通配置 query 就是当前生效值。更关键的是，
  `SYSTem:ERRor[:NEXT]?` 的手册适用范围只写 `NSA | SA`，**未确认 LTE_NR_IRAT**；
  现有 `SYSTem:ERRor?` 不得再被当跨方言通用的绿色判据。P1-46 查不到覆盖当前 Test App
  的原文就必须标 `unverified`，禁止现场猜拼写。

**三片交付**（各自单 PR，不合成大爆炸）：

| Slice | 交付 | Acceptance |
|---|---|---|
| **P1-47A 传输证据** ✅ Done（2026-08-07，本 PR） | 公共 SCPI helper 与活跃 `RealAerotechDriver._send` socket 路径的 TX/OK/RX/ERR 共用同一证据结构和 `exchange_id`；统一 command/query；timeout/cancelled 明确留痕后原样传播；IMSI/认证信息入日志前脱敏；原始 SCPI 日志默认最多保留30天 | UXM/F64/转台并发与嵌套调用均可配对；空串/空白/`not ready` 不合并；变异删除ID、绕过Aerotech、吞取消、取消脱敏/留存上限均红 |
| **P1-47B 仪器证据** ✅ Done（2026-08-07，本片） | 机器可检查的关键命令手册清单；从真实连接采集型号/固件/Test App；F64 清旧队列→写→OPC→ERR→回读→STATE；UXM 配置回读/APPLY/协议栈状态/正吞吐分层；转台请求角/反馈角/容差 | 实际环境不在证据范围，或证据为 `onsite-observed` / `unverified` 时不得判绿；回显不得冒充生效 |
| **P1-47C 正式执行** ✅ Done（2026-08-07，本片） | 同一 `TestExecution.config.scpi_evidence` 持久化 requested/command_sent/readback/exchange_ids/evidence_level/source_reference/verdict/reason 与执行环境快照；执行状态 FastAPI schema/endpoint 读回；ReportDataCollector→ReportService→PDF 活跃链传递；GUI/报告分层展示 | 证据不得 write-only；任一 mandatory 项 unknown/rejected、非confirmed或范围不匹配，正式验收不得显示通过；摘要可由 execution+exchange 精确追溯原始往返；变异让API/collector丢证据必须红 |

**P1-47A 完成实况（2026-08-07）**：公共 SCPI 模板方法和 Aerotech 活跃 socket
路径都已产生可由 `execution_id + exchange_id` 配对的结构化 TX/OK/RX/ERR；query/
command、timeout/cancelled、设备拒绝、空串/空白/`not ready` 分型独立，异常原样传播。
日志副本统一隐藏 IMSI（仅末四位）及 Ki/OPc/认证秘密，专用 `scpi.log` 的日轮转上限
固定为最多30天，且专用命名空间不再复制进保留期更长的 `app.log`（控制台传播仍保留）。
53条专项门与6类突变验证通过；内审补抓并闭环
`*OPC?` 误脱敏、裸密钥异常、启动前取消、零天留存、转台重连取消清理与
`AXISFAULT` 分类六个边界、引号内含分号的密钥被错误切段泄漏，以及分号后相对
header 继承认证路径却漏脱敏；R2 尾修复内审又拦下 `AUTHKEY` 无下划线形式的
兼容性回归。脱敏同时扩到 SCPI 终端、诊断审计副本及
UXM/F64/FS16 重连告警。GitHub Codex 外审 R1 又抓出并已修复两处：分层鉴权路径
`CONF:AUTH:KEY:VALUE <secret>` 的末操作数泄漏/查询 header 误改，以及 SCPI 证据
经 root 重复落入长期 `app.log`；R2 又抓出并已修复 `AUTHentication` 中间缩写漏判。
两轮上限已到，该尾部修复不发 R3，并已如实登记外审覆盖缺口；后端全量
`3288 passed, 5 skipped`。本片没有产生需
另行提升的 Discovered 项。该段保留 P1-47A 收口时的历史；当前状态以顶部 Current Focus 为准。

**P1-47B 完成实况（2026-08-07）**：新增18项 P0-5 强制证据清单，逐项固定来源、
章节、适用型号/Test Application、`confirmed | onsite-observed | unverified` 与最高证据等级；
任何配置声明、断线残留身份、未知型号/固件、Test App 越界或非 confirmed 来源均不能判绿。
F64 只有在同一事务具备清旧错误队列、成功写入、`*OPC?=1`、写后错误队列 clean、
回读匹配及 `RUNNING` 状态时才逐级到 E2/E3；UXM 配置回读只到 E2，成功 APPLY 加协议栈
状态才到 E3，有效且有限的正吞吐才到 E4；转台保存目标角、原始反馈、已标定坐标偏置、
修正角与 ±1° 容差。构造器直接消费 P1-47A 的成功往返对象，不能靠布尔值或漂亮回读
绕过 timeout/cancelled/device rejection。UXM 平台硬件固件与 Test Application Framework
版本分别保存，命令范围按业务端点版本核对。当前 LTE_NR_IRAT 的错误队列、通用 APPLY、
NR 状态与下行吞吐手册范围均明确保持 unknown；Aerotech 当前 AeroBasic 路径没有已佐证
的型号/固件查询，
即使反馈角合格也保持 unknown，留待 P0-5 前补齐厂商依据。内审 R1 的七项发现已全部
闭环：命令角色精确匹配、值只从真实响应与线上命令解析、同 execution/capture 严格连续
顺序、mandatory 最高等级门、UXM 重连清残留身份、转台圆周角差与 1° 上限、来源类型与
ID 双重白名单；另外补上 UXM 写入/回读同路径和线上实际写值校验。内审 R2 又用反例拦下
四个假绿：无原文的 IRAT 范围、整组旧 execution 复用、requested 与线上写值脱钩、query
冒充 command；四项均已按 fail-closed 原则闭环。最终全量后端回归与 GitHub Codex 外审
结果在本片合并前补记；内审 R3 复验四项反例与正常控制样例后结论 CLEAN，修复后全量
后端回归为 `3330 passed / 5 skipped`。GitHub Codex 外审 R1 又抓出并已修复两处现场路径：
Aerotech 原始 `%` ACK 前缀会阻断反馈角解析，以及 F64 静默重连成功/失败后旧身份仍可能
冒充实时身份；修复后相关回归 `232 passed`、完整后端 `3332 passed / 5 skipped`，外审 R2
再拦下 F64 把 `SYST:INFO?` 硬件版本优先当固件，以及 UXM 直连 TAF 未独立采集 E7515B
平台身份两处问题；尾修内审又补住缺失 IDN 固件/平台探测失败时不得回退硬件值，最终
复验 CLEAN，相关与规则回归 `227 passed`。两轮外审上限已到，尾部修复不再发 R3；最终
完整后端回归为 `3334 passed / 5 skipped`。
P1-47C 已完成；后续本地开发顺序只看顶部 Current Focus。

**P1-47C 完成实况（2026-08-07）**：正式 MIMO_OTA 执行在动作前登记 mandatory 项，
在同一 `TestExecution` 内归档 UXM PCell 配置、F64 GCM 模型加载/运行/旁路、逐方位
转台定位与 UXM 正吞吐证据；每条公开摘要由严格 schema 校验并递归脱敏，内部 provenance
另外固定同 execution/capture、真实 instrument_id、环境快照指纹和往返顺序，避免跨执行、
跨仪器或热换设备借用旧证据。UXM 同时支持初始 ON 的 write→APPLY→readback→状态与
初始 OFF 的 write→readback→CELL ON→状态两条手册合法路径；`start_signaling=False`、
转台 `move_to=False` 均立即中止，不能继续读取上一轮缓存结果或在旧角度采样。

执行状态 API、生成类型、历史详情、ReportDataCollector、ReportService 和 PDF 使用同一份
服务端 authoritative 结论；正式通过严格等于业务校验通过 **AND** `formal_acceptance=true`。
客户端报告覆盖、定制 PDF 模板、缺失/畸形证据、部分或全部不存在的 execution ID、
0/0 汇总均不能制造绿色结论。多执行报告保留逐 execution 的 missing/unknown 占位，不会
过滤掉坏行后以剩余子集判绿。GCM 真路径可以形成 FILE/GO/STATE 的 E3；ASC/B2 尚无
已确认的模型加载证据 hook，`uxm_config_mode=inherit` 也没有写入事务，二者按设计保持
missing/unknown，不冒充支持。转台坐标偏置当前明确传 `None` / `offset_calibrated=False`，
因此在补齐现场标定真值前仍不能正式通过。P1-47C 只完成本地机制，**没有关闭 P0-5**。
内审最终结论 CLEAN；GitHub Codex 首轮外审指出的 F64 旁路回读缺口已修复：正式证据
现在绑定最终目标 `STATIC` 写入，并要求 `*OPC? → SYST:ERR? → STATIC? → STATE?`
同事务闭环；内审进一步补齐 `STATE?` 缺失、传输失败或非法响应的 fail-closed 门。
当前完整后端回归为 `3369 passed / 5 skipped`，GUI production build 通过
（仅保留既有 chunk/dynamic-import 提示）。

**正式验收**：诊断序列只做出发前能力/载体验证；P0-5 仍从正式 TestCase 启动。
同一个 execution 必须证明 UXM RRC connected + bearer active、F64 模型匹配且 RUNNING、
四个目标角偏置补偿后误差均 ≤ ±1°、四方向各自吞吐有效且大于零；不要求四个数互不相同。
执行环境快照必须与 `confirmed` 手册范围匹配，不写临时脚本、不现场手敲 SCPI。全部满足才关闭 P0-5。

**依赖与顺序**：~~P1-45 → P1-46 → P1-41 → P1-47A → P1-47B → P1-47C~~ ✅；
本地下一片只看顶部 Current Focus，现场下一步仍为 P0-5 正式复验。
P1-41 提前是止血前置：错误查询自身被拒时不能让闭环序列再次产生 7.6 秒 20 万行。

**内外审**：P1-47A/B/C 全部走全套内审；最终全量测试后不再改文件，把 staged diff、
当前版本测试输出和变异清单交给完整遵循 `.claude/agents/pre-commit-reviewer.md`、只审不改的
独立 Codex subagent，主代理自审不能替代。每次 push 后用 `@codex review` 触发 GitHub
`chatgpt-codex-connector[bot]` 外审，270 秒后查 reviews / inline / issue comments 三通道，
最多两轮；本地主代理审查不算外审，merge 后再做迟到回查。完整设计与
逐片计划见 [`plans/2026-08-06-scpi-evidence-closure-design.md`](plans/2026-08-06-scpi-evidence-closure-design.md)
和 [`plans/2026-08-06-scpi-evidence-closure-implementation.md`](plans/2026-08-06-scpi-evidence-closure-implementation.md)。

---

### P1-40 — 日志按「每次运行」分文件 + 空闲期只留基本内容 ✅（2026-08-07，PR #303）

**目的（用户原话）**：
> 「我们不该一直在一个文件里存 log，而应该根据每次测试存新 log 文件，
> 程序在不跑测试例的时候只有基本内容 log，跑测试例才需要大量交互 log。」

**实测（2026-08-05/06，别重查）**：
- `api-service/logs/` 一度 **41 GB**；单个 `app.log` **13 GB**、`scpi.log` **11 GB**
- 爆点：`app.log` 首行 `2026-08-04T23:59:59.999` → 第 20 万行 `00:00:07.604`
  —— **7.6 秒 20 万行 ≈ 26,000 行/秒**，且这 20 万行**百分之百**是同一对：
  `TX: SYSTem:ERRor?` / `RX: -113,"Undefined header"`（详见 Discovered 那条）
- 轮转**是配了的**（`TimedRotatingFileHandler` 按天 + 30 个滚动文件），
  **但按天滚对秒级爆量毫无作用** —— 一天之内爆多少都进同一个文件
- 仓库根还有**第二个死 `logs/`** 89 MB（`API.log` 最后写于 7/7）——已清
- **数据库是干净的**：最大表 `diagnostic_runs` 仅 1 MB / 5 行，用户定的
  「数据库也不该存无用 log」这条目前没被违反，本片**不动 DB**

**设计（三件事，按此顺序）**：

**① 分文件的轴 = `execution_id`，不是时间**
P1-36 已经把 `execution_id` 做成了自动注入的 ContextVar，**分文件正好复用它**：
一次执行开一个 **`logs/exec-<execution_id>.log`**，执行收尾即关闭。
⚠️ **必须扁平，不许放子目录**（Codex #290 R1 抓出，前提已核）——`_safe_filename()` 的正则是 `^[\w\-\.]+$`，`/` 不在 `\w` 里 → 任何带路径的文件名直接 **400**；而 `/system-logs/files` 是 `log_dir.iterdir()` + `entry.is_file()`，**只扫顶层且跳过目录**（`api-service/app/api/system_logs.py:79-83, 249-255`）。放进 `logs/executions/` 的话，每执行文件**列不出、tail 不了、导不出、下不了**，承诺的按文件工作流当场是坏的。扁平命名 `exec-<uuid>.log` 零后端改动就能过（`\w` + `-` 覆盖 UUID 全部字符）——修法走**去掉**（去掉子目录这个需求），不走**加机制**（递归列目录 + 路径安全解析）。
⚠️ 顺带记一处小坑：`files` 端点算 `is_current` 用的是 `'.' not in entry.stem or entry.name in ('app.log','scpi.log')`，而 `exec-<uuid>` 的 stem 里没有 `.` → 所有历史执行文件都会被标成「当前活跃」。不影响可达性，但列表上会全亮，实现时一并收。
落点与 P1-36 的 set 点**逐字相同**（`test_case_runner._run_case` /
`commissioning._resolve_execution` / `VrtExecutionService.get`）——
不新增调用点，也不需要业务代码感知日志。

**② 空闲期基线 vs 执行期详情，用「有没有 execution_id」当开关**
- 常驻 `app.log`：**只收 INFO 及以上**，且不收 `app.hal.scpi.*`
  → 空闲期就是启动、迁移、健康、错误这些「基本内容」
- 每执行文件：**收到 DEBUG**，含全部 SCPI 往返
  → 「跑测试例才需要大量交互 log」
- 判据来源就是 ContextFilter 已经注入的 `execution_id != "-"`，**零新机制**

> **已前置一小步（P1-47A）**：为封住 SCPI 独立文件最多 30 天、却又经 root
> 复制进长期 `app.log` 的留存漏洞，`app.log` 排除 `app.hal.scpi.*` 已随 P1-47A
> 落地；传播仍开启，控制台可见性不变。P1-40 后续不重复实现这一项，只完成
> INFO 基线、按 execution 分文件及速率闸门。

**③ 速率闸门（本片的止血阀，不做就白搭）**
①②只解决「日志放哪」，**解决不了「7.6 秒 20 万行」** —— 那 20 万行本来就
属于一次执行，分了文件照样 13 GB。所以必须有**同一条消息的速率上限**：
同一 (logger, 消息模板) 在窗口内超过阈值 → 折叠成一行
`… same message suppressed x100000`。这条同时满足用户定的留存判据
（20 万行同一句话对「分析系统／测试／AI 训练／故障排除」四不沾）。

⚠️ **③ 不能替代修那个死循环** —— 闸门是止血，`SYSTem:ERRor?` 排不空的根因
是独立一条（见 Discovered）。两件事都要做，顺序上闸门优先（它保护磁盘）。

**留存与清理**：每执行文件跟 `TestExecution` 同生命周期，
删执行记录时一并删；常驻 `app.log` 保持按天轮转。**GUI 侧**：
`/system-logs/files` 已有文件列表端点，加上执行文件后天然可选 —— 与 **P1-39**
第 4 条（一键跳日志）**合起来才完整**：那条跳的是过滤，这条给的是文件。

**依赖**: 无（P1-36 已落地，本片直接复用它的 ContextVar）。**现场半**: 无。

**收口**：常驻 `app.log` 收 INFO+；执行期 DEBUG/SCPI 进入扁平
`exec-<execution_id>.log`；runner 与 HTTP/WebSocket ASGI 边界收尾目标句柄，并同步让全局
`scpi.log` 写出该执行的待决抑制摘要。普通重复日志按
`(execution_id, instrument_id, logger, 完整消息)` 分桶；带唯一 `exchange_id` 的
SCPI 原始证据 fail-open 不折叠，避免持久化引用找不到原始往返。收尾异常不改变执行
结果且不泄漏 DB session。当前没有 TestExecution 删除端点，故不存在可接的删除调用点；
未来新增删除端点时必须同时删除对应 `exec-*.log`，该项不伪造未存在的流程。

---

### P1-41 — 修 UXM 排错误队列停不下来的那个循环 ✅ Done（2026-08-07）

**由 Discovered 条目升格**（`[discovered 2026-08-05 during 手动测试前的环境检查]`）。原条目写着「本条比 P1-37 更该先做」，但队列里**根本没有它的位置** —— 排序指令指向一个不存在的 slot，等于没说（Codex #288 R1 抓出）。现在给它编号并入队。

**可观察故障（实测，别重查）**：`app.log` 首行 `2026-08-04T23:59:59.999` → 第 20 万行 `00:00:07.604`，**7.6 秒 20 万行 ≈ 26,000 行/秒**，这 20 万行**百分之百**是同一对（各 10 万）：
```
TX: SYSTem:ERRor?
RX: -113,"Undefined header"
```
一次爆出 13 GB `app.log` + 11 GB `scpi.log`。

**根因核对（2026-08-07）**：事故发生在 2026-08-04 23:59；当晚 23:07 的提交
`4f8bd4a` 已把旧 `_check_errors()` 的 `while True` 换成 16 次上界，并由
`configure_mac_throughput_test()` 每组调用 `_drain_errors()`。旧无界函数在此前版本
确实存在，但全仓静态调用点为零；原 24 GB 文件已不在当前磁盘，故**无法从现存证据恢复
事故进程究竟运行了哪个 revision / 由哪个外部入口触发**。同文件原 1338 行的 `while True`
已核为 APPLY 后状态轮询，带 15 秒硬上界，与错误队列无关。这里不伪造“已找到事故栈”。

**NotebookLM 手册结论**（UXM notebook `236d9621-e3ce-4ed1-a8e1-7819b674dbcd`）：
手册明确完整形式为 `SYSTem:ERRor[:NEXT]?`、查询会弹出最旧错误、空队列返回
`+0,"No error"`；但只标 Application Mode `NSA | SA`，**没有明确保证**适用于具体
`5G_NR_Test` / `LTE_NR_IRAT` Test App，也没有定义“错误查询自身返回 -113”时的终止行为。
`SYSTem:ERRor?` 是否由可选 `[:NEXT]` 推得合法只是 SCPI 语法推断，不能升级为 confirmed。

**完成修法**：不猜替代命令；`RealUxmDriver` 的三处活跃生产排错入口统一走 profile 的 `ERR`。
若连续两次拿到完全相同的 `-113/Undefined header`，保守判为“错误查询疑似不受支持”，
最多两次即停止。MAC 在基线或任一组遇到该标记会立刻 fail-closed，不继续后续组；
`set_cell_config()` 的 APPLY 后独立硬编码 `SYST:ERR? × 5` 已并入同一 helper。
一条历史 -113 后回 clean 仍按真实业务拒绝保留，不被恒判不可用；通用 16 次上界继续兜底，
且耗尽上限仍未见 clean 时同样 fail-closed，不能继续下发业务指令。

**门**：9 条 P1-41 行为门覆盖基线自增殖、首组后自增殖、真实 stale→clean、畸形回复、
0/1/16 次上限耗尽、APPLY profile 命令与两次上界；四类变异（删重复判据 / 删组后中止 /
绕过 APPLY helper / 把上限耗尽重新判成可用）
均已实证变红。**依赖**: P1-46 ✅。**现场半**: 无 —— mock 已复现根因机制；
真机只负责后续 P1-47/P0-5 的证据确认。

---

### P1-42 — `app.audit` 请求汇总行进 `execution_id` 链 ✅（2026-08-07，PR #303）

**由 Discovered 条目升格**（`[discovered 2026-08-05 during P1-36, Codex #286 R2 P2]`）。

⚠️ **我原先判它「不值一次机制改动」是错的 —— 错在选项集不全。** 当时只想到两条路，都要改调用点：① `request.state` 传值（每个端点都得写）；② 把 ContextVar 从 `str` 换成可变盒子（要动 `ContextFilter` 与全部 set 点）。**漏了第三条：把 `AuditMiddleware` 从 `BaseHTTPMiddleware` 改成纯 ASGI 中间件 —— 零调用点改动。**

**可观察故障**：按 `execution_id` 过滤日志时，发起执行 / 取消执行那几个请求的 `POST /api/v1/test-plans/cases/{id}/execute → 200 (45ms)` 这一行**不在结果里** —— 少了 HTTP 方法、状态码、耗时。P1-39 做完「一键跳日志」之后，这个洞会立刻被看见。

**根因（已实证）**：`AuditMiddleware` 继承 `BaseHTTPMiddleware`，它在 `call_next` 返回**之后**才打汇总行；而 Starlette 把下游 app 跑在**独立子上下文**里，endpoint 里 `current_execution_id.set(...)` 设的值回不到中间件。

**三形态对照实测（2026-08-06，别重做）** —— 中间件在下游返回后读到的值：

| 形态 | 结果 |
|---|---|
| A `BaseHTTPMiddleware`（现状） | ❌ 读到中间件自己设的初值 |
| B 纯 ASGI + `async def` endpoint | ✅ **看得见 endpoint 设的值** |
| C 纯 ASGI + `def`（同步）endpoint | ❌ FastAPI 丢进线程池，仍看不见 |

**端点普查（已做，别重查）** —— 纯 ASGI 改造能覆盖 5/6：

| 端点 | 形态 | 纯 ASGI 后 |
|---|---|---|
| `test_plan.py:217 execute_test_case` | `async def` | ✅ |
| `commissioning.py` 的 `create_session` / `get_session` / `run_phase` / `run_adhoc_phase` / `run_all_phases` | 全 `async def` | ✅ |
| **`test_execution.py:218 cancel_case_execution`** | **`def`（同步）** | ❌ **线程池，需单独处理** |

**修法（按 去掉 > 换源 > 收窄 > 加机制）**：
1. **主体 = 换源**：`AuditMiddleware` 改纯 ASGI（`async def __call__(scope, receive, send)`），在同一个任务里 `await self.app(...)`，之后读 ContextVar。**不动任何 set 点、不动 `ContextFilter`、不动契约。**
2. **补 `cancel_case_execution` 那一处**：优先把它改成 `async def`（它内部是同步 DB 调用，改 async 的爆炸半径要先量）；改不动就那一处显式走 `request.state`，并在注释里写明为什么只有它特殊。
3. ⚠️ **每请求初始化 + `finally` 复位，一条都不能少**（Codex #291 R1，前提已两层实证）——纯 ASGI 让中间件与 endpoint **共享同一个上下文**，这正是它能读到 `execution_id` 的原因；**但同一件事也意味着没有自动隔离**：endpoint 设的值在 `await self.app(...)` 之后**仍然活着**。做法 = 请求开头 `token = current_execution_id.set("-")`，**打完汇总行**后在 `finally` 里 `reset(token)`（顺序别反：先记日志再复位）。

   **实证（2026-08-06，两层，别重做）**：

   | 场景 | 不 reset | 加 token+finally |
   |---|---|---|
   | 同一个 task 里连调两次 ASGI app（机制层） | ❌ **泄漏** —— 第二个不相干请求继承了 `EXEC-AAA` | ✅ 干净 |
   | 真 uvicorn，同一条 keep-alive 连接连发两个请求 | ✅ 干净 —— uvicorn **每个请求周期起独立 task** | ✅ 干净 |
   | `TestClient` 连发两个请求 | ✅ 干净（同上，各自上下文副本） | ✅ 干净 |

   **所以定性是**：Codex 描述的失效**机制是真的**，只是**我们今天的服务器不触发它**。但复位只有三行，而缺了它一旦触发就是**静默的错误归属**（不相干请求的 `app.audit` 行挂上别人的 `execution_id`、P1-40 的每执行文件里混进别人的行）—— 正是这条日志线整片在治的病。**照做，不省。**

   ⚠️ **配一条反向门**（不是「设了没」，是「该没有的时候真没有」）：先发一个执行请求、紧跟一个**不相干**请求，断言后者的 `app.audit` 行 `execution_id == "-"`。⚠️ **这条门必须在同一个 task 里直调 ASGI app**——走 `TestClient` 或真 uvicorn 都天然干净，**门会恒绿，等于没有**（这正是「验证打在真实生效端」那条规则：门要打在会失效的那一端）。
4. ⚠️ **纯 ASGI 改造要自己接管 `BaseHTTPMiddleware` 白送的那些事**：异常传播、`response.status_code` 的取法（纯 ASGI 里要从 `send` 的 `http.response.start` 消息里截）、以及**现有的排除逻辑**（`EXCLUDED_PATHS` 只对成功生效 —— 这条是 P1-34 内审 F1 的成果，改造时**绝不能丢**）。

**附带收益（同一改动顺手解决另一条 Discovered）**：`[discovered 2026-08-05 during P1-34 内审 F5]` **WebSocket 流上的日志拿不到 `request_id`** —— 根因正是 `BaseHTTPMiddleware` 对 `scope["type"] != "http"` 直接透传。改纯 ASGI 后 `scope["type"]` 在我们自己手里，websocket 分支可以一并设 id。**实现时把它一起收，别让它再单独排一次。**

**门（至少到不变量档）**：行为门 —— 造一次真实执行请求，断言 `app.audit` 那行的 `execution_id` **等于**返回的 execution_id（不是「非 `-`」）；配变异：把中间件改回 `BaseHTTPMiddleware` 必须红。另加一条守 3 的门：`EXCLUDED_PATHS` 对 4xx/5xx 仍然记录。

**依赖**: 无。**现场半**: 无 —— mock 下即可验。

**收口**：`AuditMiddleware` 已改为纯 ASGI；HTTP 从 `http.response.start` 捕获状态码，
async 执行端点的 execution ContextVar 能回到汇总行。同步取消端点只在成功后通过
`request.state.execution_id` 回传。HTTP/WebSocket 均初始化 request id，并在 `finally`
复位 session/execution token；同 task 连续请求反向门确认不串链。

## 🟡 P2 — Abstraction debt

### P2-1 — UXM two-layer architecture: Test App + Topology Profile ✅ Done

**Audit-driven re-scope** (was: "InstrumentProfile abstraction layer
across UXM / CMW500 / CMP200"). Investigation found:
- **CMW500** has scalar mode fields (`MIMO_MODE`, `TM_MODE`) — not
  command-vocabulary variants. Doesn't fit Profile shape.
- **CMP200** doesn't exist (made up from audit extrapolation; not in
  Keysight product line).
- **CMX500** is a separate physical instrument from CMW500 (not a
  "mode" of it) — gets its own driver class, not a Profile.
- Real Profile use case today is UXM only.

**Two-layer architecture** (operator's framing — sticky):
- **Layer 1 — Test App** (= which Keysight software is running on UXM:
  C8700200A / C8714000A RF App / Protocol Cert / etc.). Decides SCPI
  command vocabulary (`CONFig:NR5G:*` vs `BSE:CONFig:NR5G:*`) +
  cell-index conventions (CELL0 vs CELL1) + value encoding (BW40 vs
  raw 40). **Auto-detected** at connect via
  `SYSTem:APPLication:NAME?` — operator does NOT pick (hardware
  state-of-truth).
- **Layer 2 — Topology profile** (cell/MIMO/power/FRC config WITHIN
  the running Test App). Operator-selected via GUI, persisted on the
  UXM binding, auto-applied on next HAL reload after Test App detect
  + compat verify. IRAT scenario configurations live here.

**Phase 1 deliverables** (this PR, ~2-3 days actual):

- `UxmTestProfile` (existing dataclass with 7 built-in templates, was
  orphan code zero-called from production) gains
  `compatible_test_apps: List[str]` + `is_compatible_with()`. All 7
  built-ins declare `["5G_NR_Test"]` so a future IRAT topology must
  declare its own compat explicitly rather than inheriting empty=any.
- `RealUxmDriver`:
  - `detected_test_app: Optional[str]` instance attr captured at
    `connect()` (raw value from `SYSTem:APPLication:NAME?`).
  - `readiness_metadata()` override exposes `detected_test_app` +
    `command_profile` + `primary_cell` + `hislip_index` (consumed by
    P3-5 readiness panel — clean wiring on top of the P3-5 hook).
  - `apply_topology_profile(profile_id)` method: loads profile, runs
    compat check vs active `_cmds.PROFILE_NAME`, dispatches to
    `set_cell_config` or returns structured refusal dict (caller
    surfaces test_app + compatible_with to operator).
- HAL service `_initialize_from_db` post-connect:
  - Persists driver's `detected_test_app` into
    `InstrumentConnection.connection_params["detected_test_app"]` for
    GUI audit / pre-warming the binding's compat check.
  - If binding has `connection_params["topology_profile_id"]` set,
    auto-calls `driver.apply_topology_profile()` (incompat is logged
    WARNING but doesn't fail HAL init — operator fixes via PUT
    endpoint, no need to re-reload HAL).
- New endpoints:
  - `GET /api/v1/instruments/{cat}/topology-profiles` — list
    built-in templates + per-item live compat flag against detected
    Test App + currently-persisted selection. Reason `not_a_uxm` for
    non-baseStation categories so GUI hides the picker.
  - `PUT /api/v1/instruments/{cat}/topology-profile` — operator
    selects (or nulls). Refuses 409 with structured payload when
    incompatible with detected Test App (matches P2-5 refuse
    pattern). Persists then optionally apply-now on live driver.
- `api/openapi.yaml` + regenerated TS types.
- GUI: `TopologyProfileCard` in EquipmentManager drawer, shown only
  for baseStation. Dropdown with compat-aware option labelling
  (incompat options disabled + flagged); inline status banner
  (`applied immediately to 5G_NR_Test` / `persisted, takes effect on
  next HAL reload` / refuse reason).
- 23 new tests across compat semantics + apply happy/refuse + readiness
  metadata + endpoint shapes + DB persistence + 409 refuse path.

**Phase 2** — split into 3 sub-items (2.1 / 2.3 / 2.2 by execution order):

- **Phase 2.1 ✅ Done — DB persistence + operator CRUD** (PR #38, D21).
  New `instrument_topology_profiles` table (Alembic `c7a91b3e5d04` +
  bootstrap seeder for the 7 built-ins), service layer with
  system-preset immutability (clone-to-edit), driver
  `apply_topology_profile()` takes the dataclass instead of an ID so
  HAL stays DB-free, 4 new CRUD endpoints (`POST` create / `PUT`
  update / `DELETE` delete / `POST .../duplicate`). Codex P2
  follow-up: explicit-null on non-nullable handling. Architecture
  memo cross-link → see
  [`docs/architecture/uxm-license-scenario-model.md`](architecture/uxm-license-scenario-model.md).
- **Phase 2.3 ✅ Done — Per-test topology override** (PR #39, D22).
  New `test_plans.topology_profile_id` nullable string column
  (Alembic `d8b412ca9f15`); `TestExecutionService.apply_plan_topology_profile_if_set`
  best-effort apply on `POST /test-plans/{id}/start`; dedicated
  `PUT /test-plans/{id}/topology-profile` endpoint for set/clear.
  ⚠️ **ARCH-1 S4b 已删除这两条端点**（`topology_profile_id` 列随 `test_plans`
  表原地封存）。用例级拓扑覆盖要先定语义，是独立立项（task #99）。
  Codex P2 follow-up: `topology_profile_id` carry-through across
  duplicate / export / import fan-out paths.
- **Phase 2.2 ✅ Done — Topology editor GUI + per-plan picker**
  (this PR, D23). New `TopologyProfileEditor` modal (`features/
  TopologyProfileEditor/`) with 7 Paper sections for the 25+
  knobs; create / edit / read-only-banner-on-preset modes.
  `TopologyProfileCard` (binding drawer) gains create / edit /
  duplicate / delete row-level actions. New `GET /api/v1/
  instruments/{cat}/topology-profiles/{profile_id}` endpoint for
  editor pre-fill. `EditTestPlanWizard` gains per-plan topology
  picker wired to `setPlanTopologyProfile`.

**Out of scope** (with reason — see PR description for full list):
- Name cleanup (`UxmCommandProfile` → `UxmTestApp`, `UxmTestProfile`
  → `UxmTopologyProfile`). Pure renaming, no behaviour change —
  follow-up chore PR for clarity, kept out of this functional PR.
- `self._cmds` class-vs-instance mutability fix (latent bug, not
  triggered today since nothing mutates `self._cmds.X`). Backlog
  chore.
- CMX500 driver — separate instrument, separate work item.
- Generalising Profile into `app/hal/base.py` — only one concrete
  consumer (UXM) today; premature abstraction risk.

**Status**: ✅ Done — Phase 1 (PR #36) + Phase 2.1 (PR #38) +
Phase 2.3 (PR #39) + Phase 2.2 (this PR) all merged.
**Estimate**: original 3-5 days; actual ~5 days total across all
4 sub-PRs over 2026-05-17.

### P2-2 — Capability centralisation ✅ Done (PR #21)

**What**: Collapse scattered `has_interference_generator` /
`is_single_axis` / `has_user_alignment` into `driver.capabilities:
Set[str]`. Single source of truth for "what does this driver expose
right now".

**Status**: ✅ Done — PR #21 (merged 2026-05-15). Codex P2 follow-up
on the same PR populated `ce.user_alignment` from F64's connect
path so the token isn't a documented-but-never-set placeholder.

### P2-3 — Per-model capability discovery ✅ Done (see D13)

**What**: Add `model_capabilities: ClassVar[FrozenSet[str]]` to every
driver class — the static "what this MODEL can expose" superset,
distinct from P2-2's live `self.capabilities` (post-connect subset).
Surface in catalog API (`GET /api/v1/instruments/catalog`) so the GUI
can answer "does FS16 satisfy ce.interference_generator?" at
binding-edit time, before HAL Reload.

**Why**: Today the only way to know what a bound model supports is to
connect the driver and read live `capabilities`. So picking FS16 as
channelEmulator for a plan that needs `ce.interference_generator`
silently passes binding-time validation; the mismatch only surfaces
after HAL Reload (when live `driver.capabilities` comes back empty).
Static declaration closes that gap.

**Scope clarification**: The roadmap line "without `if model == 'FS16'`
branches" turned out to be a non-issue — P2-2's registry already
gives F64 and FS16 different driver classes (`(category, model) →
DriverClass`), so no per-category branches exist to remove. Real
deliverable is the static declaration + catalog surfacing described
above.

**Acceptance**:
- `InstrumentDriver` base declares `model_capabilities: ClassVar[FrozenSet[str]] = frozenset()`.
- F64 / FS16 / Aerotech driver classes override with the canonical
  superset they can expose (F64: ce.interference_generator + ce.user_alignment;
  FS16: empty; A3200: pos.single_axis_az + pos.dual_axis_azel).
- Catalog response gains `model_capabilities: List[str]` per model,
  empty list when no real driver is registered.
- Invariant test: live `driver.capabilities` ⊆ `DriverClass.model_capabilities`
  (live can't exceed declared).
- Single source of truth: `_real_driver_registry()` lazy-init replaces
  the previous SUPPORTED_REAL_DRIVERS hardcoded list, used by both
  HAL bootstrap and catalog API.

**Status**: ✅ Done — see D13 in [`roadmap-archive.md`](roadmap-archive.md). PR #28 + Codex P2 follow-up
commit (contract sync: openapi.yaml + regen TS types) both in main.
**Estimate**: 1.5 days (actual: ~3 hours)

### P2-4 — NAT/firewall idle-drop hypothesis verification

**What**: TCP keepalive on Aerotech was added on the *assumption* that
CAICT's NAT/firewall drops idle TCP entries. Never verified. Run an
idle-then-poke test to confirm.

**▶ 2026-07-03 现场实测数据点 (假设部分证实, 窗口按仪器分化)**: Aerotech **move 完成后 ~10s
空闲即断** (比 5/27 记录的 ~2min 严得多, 重启后更严或"运动完成即短计时") → 转台切片提级为
**P1-20** (懒重连); UXM TAF 5125 **~15min 空闲被掐** (BrokenPipeError); F64 ATE 会话
wedge 是应答错位家族非纯 idle-drop (→ P1-21)。keepalive 周期设计须 per-instrument
(转台 ≤5s / UXM ~5min)。

**Status**: `[ ]` 假设验证部分完成 (2026-07-03 实测); 剩余 = per-instrument keepalive 落地 (转台半并入 P1-20)
**Estimate**: 0.5 day

### P2-5 — HAL Reload behaviour audit ✅ Done (PR #35)

**What**: When operator clicks HAL Reload mid-test, what happens to the
in-flight diagnostic? Pre-P2-5: silently fails — `TestPlan.status='running'`
row stays in DB, in-flight VISA queries raise `visa.Error` after ~30s
timeout, error surfaces to the GUI as a cryptic late HTTP response. AND
two concurrent reload requests would race the global `_hal_service`
assignment with no mutex.

**Audit findings** (pre-implementation, see PR body for full table):
- Diagnostic exceptions ARE caught + persisted to `diagnostic_runs`
  (`success=false`, `error_message=visa.Error: ...`) — the "silently
  fails" framing was inaccurate; failures are audited, just not
  surfaced to the GUI in real-time.
- `TestPlan.status` IS in DB (`running` / `paused` / `queued` / etc.) —
  cheap to check for a refuse arm.
- No mutex around `_hal_service` reassignment → concurrent reload race.

**Policy decision (A+D from the audit's table)**:
- **A — Refuse with force override**: default `POST /hal/reload`
  returns HTTP 409 with a structured blocker list when any TestPlan
  is `running` or `paused`. Operator can re-POST with `?force=true`
  to override (takes responsibility for the abort).
- **D — Lifecycle mutex**: `asyncio.Lock` serialises shutdown + init
  across concurrent reload / mode-switch calls so the global
  `_hal_service` can't be assigned mid-flight by two coroutines.

NOT done (deferred):
- **B — Pause + Drain**: needs an in-process task registry + per-
  driver pause/resume hooks. Too big for the 1-day P2-5 slot;
  belongs to a future P2 or P3 item.
- **C — Let-Fail + Notify**: reload-doesn't-refuse approach is
  anti-operator UX; rejected.

**Acceptance**:
- New `app/services/hal_reload_policy.py` with `ReloadBlocker`
  dataclass + `find_test_plan_blockers` / `find_reload_blockers`
  pure-SQL finders. `BLOCKING_TEST_PLAN_STATUSES = ("running",
  "paused")` constant pinned in tests so future additions are
  explicit (not silently inherited from the enum).
- New module-level `_hal_lifecycle_lock: asyncio.Lock` in
  `instrument_hal_service.py`. Split `_shutdown_hal_service_inner`
  / `_initialize_hal_service_inner` (no lock) from public
  `shutdown_hal_service` / `initialize_hal_service` (lock).
  New `reload_hal_service_atomic` holds the lock across both
  shutdown + init so concurrent reloads serialise. `switch_hal_mode`
  refactored to use `reload_hal_service_atomic` so it gets the
  same protection.
- `POST /api/v1/instruments/hal/reload` gains `?force=bool=false`
  query param. Default returns HTTP 409 with
  `HalReloadRefusedResult` (refused, reason, blockers list, force
  hint). Force=true sets `forced=true` on the 200 success body for
  audit-log distinction.
- `InstrumentHALService.shutdown()` logs at WARNING (not INFO) when
  drivers are still attached, listing them — post-mortem help for
  "did something else trigger HAL shutdown?".
- 15 new tests in `tests/test_hal_reload_policy.py`: per-status
  finder semantics (9), endpoint refuse/force/empty (4), lock
  serialisation (2).
- Sibling HAL endpoints (`/hal/status`, `/hal/switch`) remain
  unchanged. The reload endpoint isn't in `api/openapi.yaml`
  (consistent precedent — all `/hal/*` endpoints are GUI inline-
  typed). New `forced` field is backward-compatible additive.

**Status**: ✅ Done — PR #35 (merged 2026-05-17)
**Estimate**: 1 day (actual: ~2 hours)

### P2-6 — Strict PFS implementation in ChannelEgine (cross-repo) ✅ Done

**What**: Strict-PFS rollout (per-(probe, cluster) independent fading) plus dual-pol / external CDL synthesis pathway, delivered in the external `ChannelEgine` repo.

**Resolution (2026-05-18)**: ChannelEgine maintainer shipped the full Phase 0-6 rollout (PR #1-#6), going further than this entry's original acceptance criteria:
- **Phase 1 (PR #1)**: `synthesis_method='strict_pfs'` 生产可用; per-(probe, cluster) 独立 fading; `E[A_i·A_j*]=0` per realization
- **Phase 0 (PR #1)**: `probe_phase_jitter` UI 修到 ±180° (跟代码一致); jitter / cal mutex runtime warning + UI st.warning; strict_pfs 下 UI auto-disable jitter
- **Phase 2 (PR #2)**: Statistical validation tests — cross-corr → 0, cal superposition, ray regression golden
- **Phase 3 (PR #2)**: `cluster` + `pinv` 标 DeprecationWarning; D11 决定 `run_with_external_clusters` 不实现 (责任划在 MIMO-First adapter 侧)
- **Phase 5 (PR #5)**: `CustomCDLProfile` Pydantic schema (`from_file` / `from_dict`); K-factor LOS boost; per-ray init phases; external CDL → strict_pfs → ASC e2e
- **Phase 6 (PR #6)**: Dual-pol synthesizer with real XPR + cross-pol init phases (TR 38.901 §7.3.2 per-cluster 2×2 pol matrix); `AntennaArrayConfig.polarization: V|H`

**Cross-repo coordination**: ChannelEgine [`CLAUDE.md`](../../ChannelEgine/CLAUDE.md) "Cross-project context" 同步; Meta-3D Issue #55 跟踪 MIMO-First 侧 adapter 重写 (→ P0-7 接手)。

**MIMO-First 侧后续**: adapter API mismatch 修复 + 透传新字段 (XPR / K-factor / init_phases / polarization / synthesis_method) → **P0-7** (in progress, this PR)。

**Status**: ✅ Done — ChannelEgine PR #1-#6 (all merged 2026-05-18)
**Estimate**: 4-10 days planned, ChannelEgine 实际 ~10 days
**Cross-repo coordination**: see [`ChannelEgine/CLAUDE.md`](/Users/Simon/Tools/ChannelEgine/CLAUDE.md) "Cross-project context" section — entering that repo surfaces full status automatically.

---

### P2-7 — 非 ring 暗室 probe 几何支持 (cross-repo) — ✅ Promoted to P1-10 (2026-05-19)

**Status (2026-05-19)**: ChannelEgine 那边 Phase 8 主动 ship 完 (`'ring' /
'multi-ring' / 'custom'` enum + `probe_positions` + 真消费 az/el, 不再
`(p × 360°/N)` 假设); MIMO-First 这边 P1-10 (PR #64, merged 2026-05-19) 收口
schema + DB plumbing 半 — 本 entry 保留作为完整 cross-repo design 历史, 实际
status 跟踪挪到 [P1-10](#p1-10--non-ring-chamber-几何-plumbing-closes-p2-7-cross-repo-half--done-pr-64)。
cross-repo silent constraint 整条已关闭 (ChannelEgine Phase 8 + MIMO-First
P1-10), P2-7 不再计入 open。ad-hoc promotion 原因: cross-repo 协作成本已花,
不收 MIMO-First 侧就是浪费, 本地 P0 hardware-blocked 时 0.5 天 plumbing ROI
远好于继续 ⏸️ 等 trigger。

---

**What** (历史 design, kept for reference): 当前 commissioning → ChannelEgine
链路写死 `chamber_config.distribution = "ring"`, probe 物理 azimuth/elevation
角度**不进** HTTP payload。ChannelEgine
内部按 `(port_id - 1) × 360° / num_probes` 推 ring 等间距假设 (3GPP TR 37.977
§6.1 标准布局)。MIMO-First DB 里 `Probe` 表实际存了每个 probe 的真实
`position: {azimuth, elevation}` (PAS rotation 代码读得到), 但这些角度从来没
传给 ChannelEgine。详细数据流见
[`docs/architecture/channel-engine-data-flow.md`](architecture/channel-engine-data-flow.md)。

**Why**: 当前是 **silent failure mode** — 操作员配一个非标 chamber (sparse
layout / PWS sector / dual-ring), MIMO-First DB 不会拒, ChannelEgine 算 .asc
时 silently 当成 ring 等间距, 物理几何跟 .asc 反映的角度不符, 没人会报错。
目前 lab 唯一在用的就是 ring 8-probe (符合假设), 这个漂移**没显化**, 但
schema 层一直有 gap。任何 fail-loud (e.g. ChannelEgine 收到非 ring distribution
就 reject, 或 MIMO-First side 拦截 non-ring chamber) 都好过现在的 silent
mis-synthesis。

**触发场景** (按优先级):
- **PWS 工程** — PWS 用 sector probe geometry, 不是 ring; 是这个 P2-7 最可能
  的真触发场景 (跟 PFS / PWS phase cal 决策一致, see
  [`docs/features/calibration/pfs-phase-immunity.md`](features/calibration/pfs-phase-immunity.md))
- **Sparse probe layout** — 低成本非标暗室, 省 probe 数
- **Dual-ring / triple-ring** — vertical stacking 增强 elevation 维度

**Scope** (跨 repo, 主要在 ChannelEgine):

| Step | Repo | What |
|------|------|------|
| 1 | ChannelEgine | `ChamberConfig` 加 `probe_positions: List[Position]` 字段 (向后兼容: 不传则 fallback 现有 ring 推算) |
| 2 | ChannelEgine | **核心硬骨头**: PAS / cluster→port 映射代码读真实 `probe_positions` 角度而不是 `(port-1)×360°/N` 推算 |
| 3 | ChannelEgine | `distribution` 枚举扩 `"ring" / "sector" / "sparse" / "dual-ring"`; 加 fail-loud — 收到 explicit `non-ring` 但没 `probe_positions` 就 reject |
| 4 | MIMO-First (channel-engine-service) | `chamber_config` payload schema 加 `probe_positions: Optional[List[Position]]` 透传字段 |
| 5 | MIMO-First (api-service) | `ChannelEngineClient._build_payload` 从 DB `Probe` 表读 az/el 进 payload (仅当 `chamber.distribution != "ring"` 时, 保持 ring 路径向后兼容) |
| 6 | MIMO-First (api-service + Alembic) | `ChamberConfiguration` model 加 `distribution` enum 字段 (当前 hardcoded "ring") + 数据库迁移 |

**Acceptance**:
- ChannelEgine 能跑一个 sparse 4-probe 非均匀配置 (e.g. 0°/45°/180°/270°) 生成
  .asc, 4 个 cluster→port angle assignment 跟 `probe_positions` 一致 (不是
  `(port-1)*360/4 = 0/90/180/270` 假设)
- MIMO-First commissioning ring 配置向后兼容 (现有 8-probe ring lab smoke 不回归)
- 非 ring chamber 配置 + 旧版 ChannelEgine (不接 probe_positions) → MIMO-First
  侧 fail-loud, 不进 measure phase

**触发条件**: PWS 工程要开始 / 或者现场要接非标暗室 — 当前 (2026-05-19) lab
唯一在用的就是 ring 8-probe, 不阻塞 first-call。

**Status**: `[ ]` not started — architecture gap, 当前 lab 配置不触发,
no immediate blocker
**Estimate**: ChannelEgine 1-2 天 (核心 PAS 映射重写 + fail-loud), MIMO-First
0.5 天 (schema + DB plumbing + migration)
**Cross-repo coordination**: 主要在 ChannelEgine; MIMO-First 这边等 ChannelEgine
PR merged 后做 plumbing

---

### P2-8 — 主控制台重设计为操作驾驶舱 (Operational Cockpit) ✅ Done (PR #68)

**What**: 现有 Dashboard (`gui/src/App.tsx` 1294-1456) 本质是"统计摘要 + 导航
快捷键"——4 个静态计数 + 3 个导航按钮 + 一个后端未实现 (`/test-executions/recent`
TODO, 现 mock) 的最近测试表 + 取了不渲染的 `liveMetrics` 死字段。真正的实时
能力 (WebSocket 指标 / execution 监控 / log 流) 割裂在下方独立 `Monitoring`
组件。重设计为单屏 4 区操作驾驶舱: ①系统就绪带 ②运行态 ③实时指标 ④实时
日志+告警, 并**合并吸收 `Monitoring` 组件** (删独立组件 + 导航项), 消除割裂。

**Why**: 现 Dashboard 回答"系统里有多少东西", 不回答操作员现场真正要问的
"能不能开测 / 卡在哪 / 在跑什么 / 报错没"。后端探查确认 cockpit 所需数据全部
**已实现可用** (readiness composite snapshot + execution 状态机 + 2 个 WS 流 +
system-logs + cert 有效期 + alerts), **零新后端**, 纯前端接已有 API/WS。
①就绪带把 commissioning precheck 的 fail-loud gate 信息 (P1-8 校准 / P1-9
DUT-attach) 提前到首屏, 跟 fail-loud 哲学一脉相承。

**4 个设计原则**:
1. **计数 → 状态** — 不是"3 个告警"而是"哪 3 个、多严重、什么颜色"
2. **实时优先** — 首屏即 WS, 不靠手动刷新
3. **就绪前置** — 顶部常驻就绪带 = 一眼"能不能开测 + 被什么卡住"
4. **消灭死数据/mock** — `recentTests` TODO 与 `liveMetrics` 未渲染都清理或接真源

**Scope** (single PR, 全 4 区一把做):

| Zone | 数据源 | What |
|---|---|---|
| ① 系统就绪带 | `GET /instruments/hal/readiness` | 顶部常驻 traffic-light: 驱动链 / 活动 Lab / 校准证书(剩 N 天) / DUT attach 各 🟢🟡🔴 + 一句话总判 (可/不可开测 + 阻塞原因) |
| ② 运行态 | execution 查询 (轮询 2-3s) | 当前 execution 名称/DUT/状态机阶段/进度条/已用时 + 队列深度; 空闲时一键去 TestManagement |
| ③ 实时指标 | `WS /ws/monitoring` (1Hz) | QZ均匀度/SNR/EIRP/吞吐/温度 sparkline + 当前值 + 期望范围合规色; 复用 `RealtimeMetricsCard` / `ExecutionMetricsCard` + `useMonitoringWebSocket` |
| ④ 实时日志+告警 | `GET /system-logs/tail` + `/dashboard/alerts` | log 流 (INFO/WARN/ERR 过滤 + 搜索 + 自动滚, 迁移自 Monitoring) + 活动告警按严重度 |
| ⑤ 整合清理 | — | 删独立 `Monitoring` 组件 + 导航项, 能力并入主控制台; `liveMetrics` / `fetchRecentTests` 死路径清理 |

**Acceptance**:
- 首屏即显示 readiness 真值; DUT 未 attach / 证书过期等阻塞态用红色 + 文字明示
  (文案跟 commissioning precheck FAIL 一致)
- WS 断线自动重连, 指标卡显示 last-known + 断线标记 (不白屏)
- 有 active execution 时运行态显示真实阶段/进度; 无 execution 显示空闲态
- log 区接真 `system-logs/tail`, 过滤/搜索/自动滚动可用
- 删独立 Monitoring 导航项后无悬空引用; `liveMetrics` 死字段 + `fetchRecentTests`
  mock 路径清理或接真源
- 复用现有 `useMonitoringWebSocket` hook, 不重复造 WS 逻辑

**Out of scope**:
- 后端告警规则引擎 (自动产 alert) — 仍是独立待实现项 (CLAUDE.md 注记), 本 PR
  只消费现有 `/dashboard/alerts`
- `/test-executions/recent` 后端实现 — 若运行态/历史需要再单开; 本 PR 优先用
  现有 `/test-executions` 查询
- 暗黑模式 / 移动端响应式布局 — P3 polish

**Status**: ✅ Done — PR #68 (merged 2026-05-20)。4 区驾驶舱全接真后端
(readiness / executions / WS / system-logs / alerts), demo 播放器移到 Diagnostics
"演示回放" tab; build (tsc+vite) 过, 新代码 lint-clean。诚实性: DUT-attach 灰色
"未实现"不假装、运行态标"历史"不伪造 live、HAL 未就绪 banner、WS 断线 last-known。
契约同步 4 步全做。**未浏览器点测** (项目无 GUI 测试框架), 建议操作员 smoke 一次。
发现并 spin off (越界): api-service alert.py 路由顺序 bug (`/alerts/summary` 被
`/alerts/{alert_id}` 抢先匹配致 422, 前端容错)。
**Estimate**: 2 days (实际 ~1 天: 探查 + 实现 agent + review + 契约同步)

---

### P2-9 — EMCenter switch bring-up (协议/地址/EMQuest 调研) 🔄 本地半 done (协议调研 + driver 协议修正)

**What**: ETS-Lindgren EMCenter (AMS8947 RF switch matrix, 真实地址 `192.168.0.50`) 接入 HAL。
现状: GPIB 血统仪表, 经 EMQuest 软件控制, **不监听 raw SCPI socket** —— 5/27 现场直连探测无 SCPI
响应。需调研: 控制协议 (是否 EMQuest REST / 专有 TCP / 必须经 EMQuest 中转)、端口、认证。

**Why P2**: 核心单路 first-call (CE/BS/SA/positioner) 不需要它; 但 **path-loss 校准 (P0-3) 的 32
链路要经拓扑开关切换**, 完整校准链最终需要它。当前是 abstraction debt + 新仪表集成, 非 first-call
即时阻塞。

**Status**: 🔄 本地半 done (本 PR) — ① 协议调研 ✅ + ② driver 协议修正 ✅; ③ 接入 TopologyEditor + 现场实测 🚧 blocked。**关键发现**: `EtslSwitchDriver` 早已存在但有协议 bug (Write/Query 前缀误读文档动作标签 + LF 终止符, 极可能是 5/27 现场 raw socket 无响应真因) + 零协议单测。**① 调研结论**: AMS8947-195-1 = ETS-Lindgren EMCenter + EMSwitch 插卡, 原生 SCPI over LAN/GPIB **不必经 EMQuest** (EMQuest 是可选上位软件; 系统图 "EMQuest NET Port" 只是物理接线盘标签); 命令裸 `<slot>:<cmd>` + CR 终止 (非 Write/Query 包装)。**② 修正**: driver 改默认裸命令 + CR + 可配置回退 (`command_style`/`line_terminator`, 现场只调配置不改代码, 同 P0-8) + SP6T reset 安全跳过 + 18 例协议单测; 完整调研 + 命令集 + 拓扑 + 现场 runbook 见 [docs/site-debug/2026-06-04-emcenter-switch-protocol.md](site-debug/2026-06-04-emcenter-switch-protocol.md)。**现场缺口**: TCP 端口 (官方手册都不写; SCPI 标准 5025 首选 + 串口 9600 plan B, web 调研已收敛, 详见调研文档) + 每槽卡型号 + SP6T↔天线映射 + SP6T 复位语义。
**下一步**: ③ 现场按 runbook 定端口 (raw+CR 默认, 逃生开关试 verbose/lf) + `<slot>:*IDN?` 认卡 + 标定 SP6T 映射 → 接入 TopologyEditor 的 mapping/连线 (见 memory: TopologyEditor 核心价值是 mapping 不是设备选型)。
**▶ 2026-07-03 现场半收口**: **老固件 2.5.1 的 LAN = VXI-11 (非 raw socket)** —— rpcinfo 见 Core/Abort 通道; pyvisa `TCPIP0::192.168.0.50::inst0::INSTR`(现有绑定本就是此形式)+ 裸命令 + CR **实测全通**: 机箱 IDN / 逐槽认卡 (Slot1 EMControl 7006-001, Slot2-4 EMSwitch 7001-002/B, Slot5 7001-003/B SP6T 值域实证, Slot8 Processor 7000-009) / 继电器读态; **当日人工通路快照 Slot4 A/B/C=NO/NO/NO + Slot5 A/B=1/1**; 响应尾带 `\n\x00` NUL; `INTLK? SAFETYRELAY` 回 ERROR 3 (此固件不支持)。2025-08 RevA 文档的 raw 5025 仅适用新固件。**剩余本地半② ✅ Done (2026-07-04 #198)**: EtslSwitchDriver VXI-11 transport 落地 (`transport` 默认 vxi11 = 现场唯一实证形态, raw 保留给新固件/串口桥; pyvisa `TCPIP0::{ip}::inst0::INSTR` @py 后端 + 裸命令 + CR 交 write_termination) + NUL 尾清洗 + INTLK "ERROR 3" 容错放行 + 5 协议单测。SP6T 值域硬校验留到接 TopologyEditor mapping 时做 (需 mapping 携带 relay_type 卡型, 值域实证已录 docstring)。**剩余现场半③**: 按通路快照验证真机切换 + 接 TopologyEditor mapping。详见 [`guides/onsite-tasks-20260703.md`](guides/onsite-tasks-20260703.md) discovered "EMCenter 复盘"条。
**来源**: 2026-05-27 现场, 见 [morning-log](site-debug/2026-05-27-morning-log.md) §10.1。文档: `Instrument_API_Doc/` 下 ETS-L EMCenter / EMSwitch + CAICT Chamber Switch (TMC AMS8947)。
**Estimate**: offline 调研 0.5 day + 现场 0.5 day

---

### P2-10 — F64 工程精细化 (配置文件资产 + 外部输出 + 内部 cal 打磨) 🔄 in-progress (本地框架 done, 现场补真值)

**What**: P0-8 让 F64 first-call 链路通 (端口 / 输入参考 / 默认 .smu / 加载 gate) 之后, F64 还有一系列工程精细应用没接: remote .smu 配置文件资产的盘点/管理、外部输出端口的精细配置、内部 user alignment cal 的刷新策略。

**Why P2**: 非 first-call 即时阻塞 (P0-8 已让链路通), 是 F64 从"能跑"到"精细工程可用"的打磨 (用户 2026-05-29 复盘: "打磨 F64 内部校准、外部输出等工程精细应用")。

**现状盘点 (2026-05-29 调研)**:
- ✅ 输出端基础 method 有: `OUTP:LOSS:SET <output>,<loss_db>` (路损补偿, set_path_loss 用) + `OUTP:CON:SET` (connector 物理路由)。
- ✅ user alignment 机制有: `get_user_alignment_status` / `enable_user_alignment` / `SYST:CALIB:USER:SET`; connect() 尝试激活 preferred alignment。
- ⚠️ 缺: remote .smu 文件资产盘点 (有哪些可用模型, 现状 `available_channel_models` 是 connection_params 静态清单 → 应动态发现或盘点) + 外部输出电平/功率精细配置 (当前只有 loss 补偿) + user alignment cal 刷新策略 (何时重标 / 漂移监控)。

**Scope (拆本地 vs 现场)**:

| Step | Subject | 本地/现场 |
|------|---------|----------|
| 1 🔄 | remote .smu 配置文件 inventory: 列举 remote 可用模型 (动态发现或盘点文档, 对称 UXM .state 盘点) — **本地半 done (#116)**: inventory 加频率元数据 (`center_frequency_mhz` + `nr_arfcn`, 从文件名 token 解析或 config 显式给), 从"名字清单"变"带频率的资产盘点", 服务 emulation_file 选择 (.smu↔TestCase 频率匹配, P2-11 Phase 2)。`parse_smu_center_freq_mhz` 抽共享 (propsim 回读 + inventory 同源)。剩: F64 MMEM 不可用 → 动态发现 blocked, **现场 .smu 资产盘点**填 config | 现场盘点 + 本地 API |
| 2 🔄 | 外部输出端口精细配置: 输出电平/功率 method (超出当前 loss 补偿) + 物理路由 OUTP:CON 接入 topology — **本地 driver 框架 done (#125)**: per-output `set_output_path_loss` (单通道, vs batch set_path_loss) + `set_output_gain` (支持正增益, vs set_external_attenuators 强制衰减)。剩: OUTP:CON connector 路由 method + topology 集成 (待 topology 语义) + 现场验 | 本地 driver + 现场验 |
| 3 🔄 | user alignment cal 刷新策略: 何时重标 (温度/时间漂移) + readiness 上报 + 漂移监控 — **本地框架 done (#125)**: `alignment_freshness` 解析 INFO? 标定日期 (实测 DD.MM.YYYY 格式) + `alignment_max_age_days` 阈值 → fresh/stale/unknown; precheck 上报 + stale warning 建议重标。剩: 现场确认 INFO 格式全集 + 漂移监控 (关联 operating-point backlog) | 本地框架 + 现场真值 |

**Acceptance**:
- **本地**: .smu inventory API + 输出端口配置 method + user alignment 刷新策略 + 单测 (mock SCPI)。
- **现场 (下次现场)**: user alignment cal 真值 + 输出功率校准 + .smu 资产盘点。

**依赖**: P0-8 (✅ 本地半 Done)。关联: U-6 (输入参考真值), operating-point uncertainty backlog (#101)。
**Status**: 🔄 in-progress — Step 1 本地半 done (#116): .smu inventory 频率元数据 (`center_frequency_mhz`/`nr_arfcn`) + `parse_smu_center_freq_mhz` 共享解析器。**Step 2 + Step 3 本地框架 done (#125)**: Step 2 per-output `set_output_path_loss`/`set_output_gain` (单通道精细, vs batch set_path_loss / 强制衰减 set_external_attenuators); Step 3 `alignment_freshness` (INFO? 标定日期解析 DD.MM.YYYY + 阈值 → fresh/stale/unknown, precheck 上报 + stale warning)。剩: Step 1 现场盘点 + Step 2 OUTP:CON topology 集成 + Step 3 现场 INFO 格式全集/漂移监控 + 现场验。
**Estimate**: 本地 ~2 day + 现场 ~1 day。

---

### P2-12 — 标准信道文件定义 (Standard Channel Definition) — 软件掌控 .smu 命名 🔄 本地收口 (slice 1-4 + 扩展门 done, slice 5 现场 blocked)

**What**: 用户 2026-06-01 确立: **命名标准是我们软件的, 不是 F64 的**。软件里有一个 SCD 实体 (规范配置 `FrequencyIdentity`+CDL+MIMO+scenario + 我们掌控的标准名), 是真值; 实际 .smu 用三路之一满足: **(a) SCPI 驱动 Channel Studio 自动生成** (现场/vendor 调研) / **(b) 指导操作员手工按标准名生成** / **(c) 关联已有 .smu 到 SCD**。完整设计见 [`docs/architecture/testcase-driven-instrument-config.md`](architecture/testcase-driven-instrument-config.md) §9。

**Why**: P2-10 Step 1 的文件名解析是**被动**的 (逆向不掌控的厂商命名, 跟 #109 Codex P2 "3600M 重调 3500 文件名说谎" 同病根)。ASC 已是生成式 (config 是真值); GCM 落后的被动一半。SCD 把 .smu 拉进 "declared > inferred" 架构 (= ARFCN 规范 vs 标称, = DUT 自声明 #115)。

**核心**: Step 1 解析器**从真值源降为 cross-check** (parse 文件名 vs SCD 声明 → 不一致 fail-loud, 正好抓文件名说谎)。Phase 2 emulation_file 从裸路径 → 引用 SCD (按 FrequencyIdentity 查), 即 §5 "frequency→.smu 库映射" 的正解。

**Scope (切分见 §9, 均本地除路径 a)**: 1) `standard_channel_filename` 命名契约 + 反解 + cross-check (本地) → 2a) `StandardChannelDefinition` DB 实体 + CRUD (本地) → 2b) `associate_file` 关联实际 .smu (cross-check fail-loud) + **关联即更新 `available_channel_models` (synced projection) 后端** (本地) → 3) 路径 b/c GUI 工作流 (调 2b 后端) (本地) → 4) Phase 2 引用 SCD (本地) → 5) 路径 a SCPI 生成 (现场/vendor)。

**静态清单定位 (用户 2026-06-01)**: `available_channel_models` 不是独立手维护死清单, 而是 SCD↔文件关联的**同步投影** —— 关联即更新, 不放不存在的条目; 频率元数据来自 SCD **声明** (权威) 而非解析 (Step 1 降为关联时 cross-check)。

**依赖**: P2-10 Step 1 (parser, #116 引入即被 §9 定位为 cross-check) + P2-11 Phase 2 (emulation_file)。关联: DUT 自声明 (#115, 同架构)。
**Status**: 🔄 本地收口 — 架构已确立 (§9) + slice 1 命名契约 (#116) + slice 2a SCD 实体/CRUD (#117) + slice 2b `associate_file` + synced projection 后端 (#118) + mock 死代码清理 + 数据源地图 (#119) + slice 3 [(B) emulation_file GUI 下拉 (#120) + (A) SCD 管理建库 GUI create/list/associate/delete + 后端暴露 connection.id (#121)] + **slice 4 Phase 2 引用 SCD (scd_id + 多方频率一致性网) (#122)** + **emulation_file 扩展 fail-loud 门 (GCM 只接受 .smu, Codex #120 后端另一半) (#123)**; **本地 slice 1-4 + 扩展门全部 done, 只剩 slice 5 路径 a SCPI 生成 (现场 blocked)**。
**Estimate**: 本地 ~2-3 day + 路径 a 现场。

**Discovered (2026-06-02, slice 2b Codex review 期间排查 GUI 消费端)**: slice 3 比预想大且背死代码债 —— 现有唯一消费 `available_channel_models` 的 `.smu` 下拉 (`type:'channelModel'` → `fetchChannelModels` → `/instruments/channelEmulator/channel-models`) 挂在**死代码** `App.tsx::_TestConfig` (全库零渲染点) + mock 时代 `stepTemplateDefinitions`; 真实测试模块 `features/TestManagement` **从未实现**该字段 → **SCD 产物在真实 GUI 测试流程无消费端** (唯一露出 = 仪器抽屉 `ChannelModelsCard` 只读列表)。slice 3 需含: TestManagement 步骤编辑接 `/channel-models` + 清理/隔离 `_TestConfig` 死代码 + 隔离 mock (`mockDatabase.ts` TP-317/404/CTIA + `stepTemplateDefinitions`, 本次排查曾被其误导多轮; 教训见 memory feedback_distinguish_live_vs_mock_dead_code)。**进展**: 清死代码 + 数据源地图 #119 done; **(B) TestCase 选 emulation_file GUI #120 done** (MIMOOTAConfigForm 加 .smu 下拉, value=filename 真路径 / 显示=标准名, engine_mode=ASC 时禁用); **(A) SCD 管理建库 GUI #121 done**: StandardChannelDefinitionCard (create/list/associate/delete) + 后端暴露 connection.id, 挂信道仿真器抽屉 ChannelModelsCard 下方; associate 后 invalidate channel-models 让 (B) emulation_file 下拉刷新。**slice 3 完成**。

**Backlog [discovered 2026-06-03 during #120 review] — ✅ done (#123)**: 后端 measure precheck 给 `emulation_file` 加**扩展 fail-loud 校验** (GCM 模式只接受 `.smu`) —— 前端 filter (#120, 只列 `type==='smu'`) 是 UX 第一道防线, 但 API 直传 / 绕过前端时非 `.smu` (`.rtc` Runtime 管线 / `.asc` ASC 引擎) 仍运行时才在 F64 信道加载失败; `precheck_strict_emulation_file` 现只校验"是否指定"不校验扩展。跟 `precheck_strict_*` 同族 (防御深度), 是 Codex #120 那条的后端另一半。**实现 (#123)**: `evaluate_emulation_file_gate` 在"指定了文件"分支加扩展校验 (`.smu`, 大小写不敏感), strict→FAIL / opt-out→WARN (尊重 bring-up bypass 开关, per feedback_strict_gate_extend_bypass_toggle), 天然 mock-aware (校验在 `emulator_is_real` 之后, 只对真 F64), 对象是 `resolved_emulation_file` → 覆盖 scd_id 解析 + 裸路径两路; +5 单测。

**Discovered (2026-06-04, during #123 emulation_file 扩展门)**:
- `associate_file` 的 `vendor_associated` 路径 (路径 c) **不校验关联文件扩展** —— SCD 关联非 `.smu` (如 `.rtc`) 不在 associate 时拒绝, 要到 measure gate (#123) 才 fail-loud。gate 已兜底 (resolved=非.smu → FAIL), associate 时校验是"更早 fail" (符合 SCD 关联=.smu 语义)。同族防御深度前移, 规模小, deferred。
- ~~roadmap 详细 section stale: P1-17 (§P1-17 `[ ] not started`) 实际 #107 done; P1-16 (§P1-16 `🔄 Current Focus`) 实际 #99 done —— 底部详细 section 没跟上顶部 Current Focus 区。~~ ✅ **已修 (2026-06-04 roadmap stale catch-up chore PR)**: P1-16 header → ✅ Done (#99); P1-17 header+Status → ✅ 本地半 (#107) / 🚧 现场半; P2-10/11/12 header + Status/Scope 表 "本 PR" 指代矫正成具体 PR 号 (#116/#125/#123/#124/#126/#112); P2-11 C 类 backlog count (端口路由 #1974 done → 只剩操作点) + Estimate; Summary 表从各 section status 精确重算。当时 #123 聚焦 P2-12 不顺手跨线改 (per feedback_d_row_stale_this_pr_reflex), 留给本专项 chore 收口。

---

### P2-11 — TestCase 驱动的仪表配置下发架构 (单一真值源 + 多方一致性校验) 🔄 Phase 1/2/3/5/6 done (Phase 4 按需)

**What**: 确立并补全"TestCase 是测试配置单一真值源, 驱动整个仪表层级配置下发 + 下发后多方一致性 fail-loud 校验"的架构。完整设计见 [`docs/architecture/testcase-driven-instrument-config.md`](architecture/testcase-driven-instrument-config.md)。

**Why**: 2026-05-30 用户提出的架构级问题 —— P1-17 ARFCN review 暴露 UXM profile 标称 vs 实际下发不一致 (微观); 放大到架构层, **TestCase 频率驱动了 UXM/SA/positioner, 但 F64 GCM .smu 没被驱动 (sim_rules 不传 emulation_file → fallback 默认 3600M), 且无任何多方频率一致性校验** → GCM 模式下 TestCase 3500 / F64 默认 3600 静默打架。switch 还是 chamber-driven 非 TestCase-driven。这是测试正确性 (而非 first-call 即时阻塞) 的架构债。

**核心切分** (用户强调): **暗室首测可走捷径** (路径 A: bring-up 用默认仪表配置, P0-8/P1-17 是它的实现, 保留不推翻); **正式测试必须 TestCase 驱动** (路径 B: 单一真值源 → 全仪表层级下发 + 一致性校验)。两路正交, 边界清楚。

**现状覆盖** (measure/reference executor 调研): UXM ✅ / positioner ✅ / SA ✅ / F64-ASC ✅ / **F64-GCM ❌ (fallback 默认)** / **switch ❌ (chamber-driven)** / 信号源·VNA ❌ (未接)。

**Scope (分阶段, GCM 优先 — 用户 2026-05-30: "GCM 是首先要测的")**:

| Phase | 内容 | 本地/现场 | 优先 |
|-------|------|----------|------|
| 1 ✅ | **多方频率一致性 fail-loud 校验** (UXM ARFCN频率 ≈ F64 .smu/.asc 频率 ≈ SA ≈ TestCase) — silent-failure 防护 (P1-8/9/12 同族), 防静默错配 — **done #109 + Codex fix** | 本地 | ⭐ 最先 |
| 2 ✅ | **TestCase → F64 GCM .smu 联动**: `MIMOOTAConfiguration.emulation_file` 字段 + `sim_rules` 透传 + `precheck_strict_emulation_file` 严格门 (mock-aware, 真 F64 未指定 → fail-loud 不静默 fallback) + `.smu` 来源 audit — **done (本条 PR)** | 本地 | ⭐ 高 |
| 3 ✅ | switch topology 纳入 TestCase 驱动: `switch_mode_id` 字段 (默认 "mimo_ota" 不再硬编码) + measure 透传给 `orchestrate_switch_topology` + `precheck_strict_switch_mode` 门 (有拓扑但请求 mode 不提供 → fail-loud; 无拓扑/固定布线 → warn) — **#111 done** | 本地 | 中 |
| 4 | 信号源 / VNA 纳入 TestCase 驱动 (干扰 / 在线校准) | 按需 | 低 |
| 5 ✅ | 默认配置角色 (路径 A) 文档化 + 路径 A/B 边界代码注释固化: 架构文档 §6.1 代码锚点地图 + 三处 `路径 A/B 边界` 注释; **+ 修暗室首测捷径缺口** ("强制跳过严格门" 开关从 cal/dut 扩到覆盖全 5 道门 — GUI api.ts + 后端 CreateSessionRequest); **+ 修 Codex on #112 指出的 UXM profile isolation 注释不准** (承认 port routing/TDD/sched leak, 记 Discovered backlog) — **#112 done** | 本地 | 贯穿 |
| 6 ✅ | **一致性网从频率扩到 DL 吞吐链** — **DL MIMO layers (首条线 #114) + DL modulation (第二根线, #124) 已实现**: `get_applied_cell_config()` 读 **UE 协商能力** `max_dl_layers` + `max_modulation_dl` + `cell_config_consistency.check_*` 判**请求 > UE 上限 → fail** + measure `precheck_strict_cell_config` 门 (UE 未 attach/mock → skip)。抓 UE 撑不住请求时 UXM 静默 clamp (4→2 层 / 256QAM→64QAM)。⚠️ Codex #114: 读 UE 能力**非** `CONF:LAY?` 配置旋钮。modulation 阶数归一化容忍 SCPI 格式差异 (`256QAM`/`QAM256`/`QPSK`), 不受 AMC 影响。**DL 生效 MCS (第三条线, #126): AMC off 时 throughput 实测 mcs_dl 众数 vs 请求, clamp → fail (`check_mcs_consistency`, mock-aware + AMC on skip; 生效回读 ≠ 上两条 capability 核对)**。剩 DL power (InputLevelController 闭环改, 需操作点语义) | 本地 | ⭐ 高 (Phase 1 自然延伸) |

**Acceptance**:
- **Phase 1 (本地)**: measure/precheck 加多方频率一致性校验, mock 下 UXM/F64/TestCase 频率不一致时 FAIL; 单测覆盖一致/不一致两路。
- **Phase 2 (本地)**: TestCase 能指定 F64 .smu (GCM), measure phase 用 TestCase 派生而非默认; TestCase 频率 != .smu 频率时 fail-loud。
- **现场**: real GCM 测试一键 TestCase 驱动 UXM+F64 同频跑通。

**依赖**: P0-8 (F64 默认) + P1-17 (UXM 默认, 路径 A 实现) ✅。关联: ARFCN profile/频率 audit (spawned), U-6 (输入参考真值)。
**Status**: 🔄 Phase 1/2/3/5 done (#109/#110/#111/#112 + Codex fixes)。**2026-05-31 核心参数驱动审计 (架构文档 §8, #114)** —— 用户问"除频率外哪些核心参数需 TestCase 驱动兜底", 把 DL 测量链每个参数分 **A 类** (已驱动+fail-loud) / **B 类** (已驱动但无回读校验: MIMO/MCS/功率) / **C 类** (未驱动真缺口, 均已 backlog: UXM 端口路由泄漏 + 操作点输入参考) / **D 类** (物理量不该驱动)。审计揭出 **Phase 6** (B 类一致性网)。**Phase 6 首条线 DL MIMO layers 已实现 (#114 + Codex 修正)** —— UXM `get_applied_cell_config()` 读 **UE 协商能力** (非配置旋钮回读, Codex 指出后者 no-op) + `cell_config_consistency` 判请求 > UE 上限 + `precheck_strict_cell_config` 门, 抓 UE 撑不住请求层数的静默 clamp。**Phase 6 第二/三根线 DL modulation + 生效 MCS 已补**: modulation 读 UE `max_modulation_dl` 能力核对 (#124); MCS (#126) AMC off 时 throughput 实测 mcs_dl 众数 vs 请求 clamp → fail (`check_mcs_consistency`, mock-aware)。一致性网累计: 频率 + MIMO layers + 调制 + 生效 MCS。**UXM 端口路由/TDD/调度 path B 驱动 (#1974, 后端 #127 + GUI #128) 已收口** (C 类端口路由泄漏从 backlog 转 done)。剩: Phase 4 (信号源·VNA 按需) + Phase 6 仅剩 DL power (结合操作点 backlog, InputLevelController 闭环坑) + 1 个 C 类 Discovered backlog (操作点输入参考, 待定语义)。
**Estimate**: Phase 1 ~0.5d ✅ + Phase 2 ~1.5d ✅ + Phase 3 ✅ + Phase 5 ✅ + Phase 6 (layers/调制/MCS) ✅ (剩 DL power, 待操作点语义) + Phase 4 按需。

---

### P2-13 — SIMProfile (SIM/eSIM 身份 + 鉴权声明) + SIM↔UXM 一致性 fail-loud 🔄 in-progress (Phase 1 实体+CRUD done, 档 B Phase 2-3 继续)

**What**: 把 DUT 测试用的 SIM/eSIM 身份与鉴权 (IMSI/PLMN/Ki/OPc/算法) 从"Test App 手配的工艺前提黑箱"升级成**结构化可声明 + 下发前一致性可校验**的 `SIMProfile` 实体。跟 P2-11 (TestCase 单一真值源驱动) 同族、跟 DUTProfile (P2-11 backlog #1965, 已收口) 平行: DUTProfile = 能力层 (max layers/调制), SIMProfile = **身份/接入层** (卡凭据)。完整设计见 backlog 条目 (本文件 "Discovered during" 区, 2026-06-05 条) + [`docs/architecture/testcase-driven-instrument-config.md`](architecture/testcase-driven-instrument-config.md)。

**Why**: 2026-06-05 用户提"做测试经常 SIM/eSIM 匹配问题, 最常踩鉴权 (Ki/OPc)"。现状: UXM 驱动 SCPI 树 (`CONFig:NR5G:...` + `CALL:NR5G:...`) **无 auth/IMSI/PLMN/Ki 任何命令**, attach 的 IMSI 是操作员手敲只当审计; SIM 匹配挂了只给泛泛"attach 不上" → 正是 first-call 现场瞎调。**调研定论**: 商用卡 Ki 不可破解 (AKA 双向, emulator 没 Ki 既验不了 UE 也发不出 UE 认的 AUTN); 但 RF/吞吐测试正解是**可编程测试卡** (自写 IMSI/Ki/OPc/Milenage, emulator HSS 配同值 → 完整真鉴权), Keysight 官方做法也是测试卡跟 UXM 默认 IMSI/PLMN 预匹配。**别折腾商用卡**, 痛点正解 = 系统管住测试卡 Ki/OPc/PLMN ↔ UXM 一致性。

**核心切分 (档 A/B)**: UXM SCPI 能否配 subscriber/auth/PLMN **待现场查 S8711A SCPI command reference** (公开文档 403, 强信号能 —— UXM 卖点就是 SCPI 驱动整套 signaling/固件级测试)。**档 B (本地保底可交付)**: 声明 + 下发前 cross-check + warn + attach 后实测 IMSI 核对; **档 A (现场增强)**: 确认 SCPI 后从 SIMProfile **自动 provision UXM HSS**, 消除手配 mismatch。

**Scope (分阶段, 镜像 DUTProfile 四阶段)**:

| Phase | 内容 | 本地/现场 | 优先 |
|-------|------|----------|------|
| 1 ✅ | **SIMProfile 实体** (model/migration `d5b82c9f3e41`/CRUD `/sim-profiles`, 平行 DUTProfile) + TestCase 引用 `sim_profile_id`。字段: imsi/iccid, mcc/mnc (校验=IMSI前缀), ki/opc (脱敏)/auth_algorithm (MILENAGE/TUAK/XOR), card_kind (test_sim/operator_test/commercial 当鉴权门, commercial 不存 ki), sim_form (usim/esim), eid/esim_profile_id (一 profile 一行), extra_metadata; **不要** sqn (运行时态) — **✅ done 本 PR** (凭据脱敏不回显, 23 测, dev PG applied) | 本地 | ⭐ 先 |
| 2 ◐ | **precheck SIM↔UXM 一致性 (档 B)**: ① **attach 后 IMSI vs 声明核对 (防插错卡) — ✅ done 本 PR** (`sim_identity_check` + precheck 2.4b: dut_attach.imsi vs SIMProfile.imsi, strict `precheck_strict_sim_identity` → FAIL / opt-out warn, IMSI 脱敏; bypass 4 处同步; 10 测); ② SIMProfile vs 声明小区 PLMN cross-check — **待现场/驱动扩展** (UXM 不暴露 PLMN 读, TestCase 无小区 PLMN); ③ **鉴权 fail-loud 分根因** (MAC=Ki/OPc 不符 / sync=SQN 去同步可恢复 / no subscriber=HSS 没此卡) — **待现场/驱动扩展** (需 emulator 上报鉴权失败原因, mock 给不出) | 本地①/现场②③ | ⭐ 高 |
| 3 ✅ | **GUI** (本 PR): `simProfileService` (ki/opc write-only 脱敏) + `SIMProfileManager` CRUD 页 (凭据 PasswordInput, 编辑留空保持, commercial 禁 ki) + 侧栏「SIM 卡管理」导航 + `MIMOOTAConfigForm` SIM 选择器/严格开关/声明提示。**浏览器端到端实测**: 建卡 (Ki 脱敏 badge "Ki 已设") → TestCase 步骤选 SIM → 声明提示 IMSI/PLMN/卡类型 + 严格开关启用 | 本地 | 中 |
| 4 | **档 A 自动 provision (现场)**: 确认 UXM SCPI subscriber/auth/PLMN 命令 → 从 SIMProfile 写 UXM HSS (IMSI/Ki/OPc/算法/PLMN), 消除手配 | 现场 | 待 SCPI 确认 |

**Acceptance**:
- **Phase 1 (本地)**: SIMProfile CRUD + TestCase 引用, 字段校验 (mcc/mnc=IMSI前缀, ki/opc 脱敏, commercial 不存 ki); 单测。
- **Phase 2 (本地)**: precheck SIM↔小区 PLMN 不一致 → warn; attach 后实测 IMSI ≠ 声明 → fail-loud (防对错卡); 鉴权失败按 MAC/sync/no-subscriber 三类分根因报; 单测覆盖。
- **Phase 3 (本地)**: SIMProfile 管理页可填/编辑/删 + TestCase 选 SIM + 差异展示; tsc + 运行时验证。
- **现场 (档 A)**: 确认 UXM SCPI 鉴权命令 → 一键从 SIMProfile provision UXM HSS, 测试卡↔UXM 同凭据真鉴权跑通。

**依赖**: DUTProfile (P2-11 backlog #1965, 已收口) —— 复用脚手架 (model/CRUD/cross-check 模式 `dut_capability_crosscheck`) + GUI 模式 (`DUTProfileManager`)。档 A 待现场 UXM SCPI 确认。
**Status**: 🔄 in-progress —— **Phase 1 ✅ done** (实体/migration `d5b82c9f3e41`/CRUD + TestCase 引用 + 凭据脱敏, 27 测)。**Phase 2 本地部分 ✅ done** (①防插错卡 IMSI 核对 `sim_identity_check` + precheck 2.4b + `precheck_strict_sim_identity` 门 bypass 4 处同步; ②PLMN cross-check + ③鉴权 fail-loud 分根因 待现场/驱动扩展 —— UXM 不暴露 PLMN 读 + 鉴权失败原因 mock 给不出)。**Phase 3 GUI ✅ done** (本 PR, 浏览器实测: SIMProfileManager 凭据脱敏 + TestCase SIM 选择器 + 声明提示)。**→ P2-13 本地三阶段 (1/2本地/3) 全收口**; 剩 Phase 2②③ (PLMN/鉴权 fail-loud) + Phase 4 (档 A auto-provision) 待现场确认 S8711A SCPI / 扩 BS 驱动。曾设 Current Focus (真 P0 现场 blocked); 本地完结后 Current Focus 移下一本地项 (backlog #2001 imbalance metric)。
**Estimate**: Phase 1 ~1d (镜像 DUTProfile 阶段1) + Phase 2 ~1-1.5d + Phase 3 ~1d + Phase 4 现场。

---

### P2-14 — 信道注入 B-2 生成层（参数化 TDL + 硬件实时衰落）✅ 本地实现完成 / 🚧 现场验证待做

> **来源**: 2026-06-07 backlog 登记（docx V1.2）→ **2026-06-21 用户定向提升**。多轮设计讨论
> （接入 NotebookLM PROPSIM 资料 + 本地 PROPSIM 手册深挖）收口为完整设计。属"理论层变动"，
> 与现场验证（`onsite-verification-baseline-2026-06-21` tag）并行，纯本地、不依赖现场。

**What**: RT 子径 → ChannelEgine 多聚类（`geometric_native_fit` / `phase_continuous`，时空跟踪）
→ 标注式 CDL（`doppler_repr` 区分联合体）→ F64 B-1/B-2/GCM 分流。让吞吐/一致性类 MIMO OTA
**普及 B-2**（绕开 F64 无 custom PSD、免奈奎斯特覆盖全 f_D,max）；ISAC/波束跟踪走 B-1/GCM 确定性相位。

**Why**: F64 参数化衰落只有闭式谱集、**无任意 PSD 参数口**（手册证实），但聚类是我们的自由度 ——
按角度 native-fit 聚类使每簇落 F64 原生谱即可普及 B-2，拿到 ~100Hz 几何骨架率（不必 SD=2 高 f_upd 烘焙）。

**完整设计**: [`design/RT-MPDB-CDL-F64-channel-injection-design_V1.0.md`](design/RT-MPDB-CDL-F64-channel-injection-design_V1.0.md)
（取代 `design/B1-B2-path-decision-design_V0.1.md`）。F64 硬约束见 memory `project_b2_universal_channel_injection_design`。

**Scope（多 PR，主体在 ChannelEgine 仓）**:

| Step | 内容 | 仓 |
|------|------|-----|
| 0 | native 谱映射纯函数（簇 AS+角度+速度 → F64 原生谱参数 `f_d_centroid=f_D,max·cosφ` / `f_d_max∝AS·sinφ` + 残差）+ 单测 | ChannelEgine |
| 1 | `AnnotatedCDLProfile` schema（扩 `CustomCDLProfile`，向后兼容）+ §5.4 一致性校验 | ChannelEgine |
| 2 | `geometric_native_fit` 聚类（时空跟踪 + native 可拟合 + ≤24 tap，双高斯/分裂内置） | ChannelEgine |
| 3 | `EngineMode.B2_PARAMETRIC_TDL` + 合成分流 + F64 `.tap/.rtc` 加载 | MIMO-First |
| 4 | `phase_continuous` 聚类（确定性，B-1/GCM 路） | ChannelEgine |

**Acceptance**: B-1 金标准对照 B-2（QZ 处 Doppler PSD / 空间相关 / 衰落 CDF 容差内）；连续性用例
（`cluster_id` 跨快照平滑、F64 插值无跳变）；fail-loud 一致性校验。完整见 V1.0 §10。

**现场验证依赖**: `gaussian_model_available` / `f_upd_max` / `tap_budget` / `rho_thresh` 需现场标定（V1.0 §9）。

**Status**: ✅ **本地实现完成 (2026-06-21)** —— 设计 V1.0 (#165) + F1–F7 全 merge：
F1 native 谱映射 (CE #34) / F2 标注式 CDL schema (CE #35) / F3 geometric_native_fit 聚类 (CE #36) /
F4 时空跟踪 (CE #37) / F5 phase_continuous (CE #38) / F6 EngineMode+分流+能力门 (MF #166) /
F7 F64 PARAMETRIC_TDL 加载 (MF #167)。ChannelEgine 算法层 (F1-F5) + MIMO-First 路由/驱动层 (F6-F7)
全部纯函数 / mock 可测，Codex review 逐 PR 过 (含 1 个 P1 + 多个 P2 当下修)。
⭐ **2026-06-21 续做 (PR-1a~4 + `.tap` 破解)**：B-1 经新架构**端到端打通** (PR-1a `cluster_subrays` 旁路 CE#39 / PR-1b `b1_annotated_baker` CE#40) + §6 路径判决 (PR-3 CE#41) + B-1 金标准软件对照 (PR-2 CE#42) + B-2 per-tap 参数表 (PR-4 CE#43)。下方"下一阶段" 1/2/3 已 ✅。
🚧 **现场验证待做** (V1.0 §9)：`.tap` 是 **Channel Studio 专有格式**（2026-06-21 手册 §21 + `.ctap` 样本逆向：加密熵 7.864、手册无 `.tap` 子章节）→ B-2 `.tap` 字节必须**现场用 Channel Studio 从 per-tap 参数表 (PR-4) 生成**；+ gaussian 谱可用性 / `f_upd_max` / `.rtc` 切换抖动 + 端到端 RT→MPC 接入。**B-1 `.asc` 经手册 §21.1 验证可直接生成、零现场。**
**Estimate**: B-2 现场 (Channel Studio + F64 加载)；B-1 已端到端完成。

**🔜 下一阶段 / 未接线项**（本地算法 + schema 完成 ≠ 端到端可跑；现场验证通过后接）：

1. **✅ AnnotatedCDLProfile → 文件生成 接线**（2026-06-21 PR-1a~4）：
   - **B-1 ✅ 端到端打通**：`b1_annotated_baker.bake_b1_annotated` (PR-1b CE#40) 消费 `subray_sum`/`baked` 标注 → `.asc`（`cluster_subrays` 旁路 PR-1a CE#39 + 复用 `PropsimASCIIExporter`）；`.asc` 格式经手册 §21.1 逐字段验证、零现场。
   - **B-2 ✅ 软件半完成 / `.tap` 字节现场**：`extract_tap_parameters` (PR-4 CE#43) 出 per-tap 参数表；**MIMO-First 接线 (PR-5, 5486413) ✅** — CE 微服务 (`channel-engine-service/`) `cluster_b2_native` 端点 (RT 射线 → `geometric_native_fit` 聚类 + §6 判决 → 参数表) + `channel_engine_client.cluster_b2_native` + `b2_parametric_strategy` (RT 射线 fail-loud + 调 CE + 参数表就绪)，16 测试。**现场剩余**：`.tap` 字节 Channel Studio 生成 (手册 §21 专有格式) + F64 加载 + 真实 RT 数据 RT-Release 接入。
2. **✅ §6 路径判决代码**（PR-3 CE#41）：`select_path_and_clustering` test_class → B-1/B-2/GCM 自动分流 + ESCALATE fail-loud + GCM 门；MIMO-First `target_path→EngineMode` **动态分流待**（Codex P2 #169）：`b2_parametric_strategy` 现对非 `B2_parametric` 判决（`B1_baked`/`GCM_native`，如 isac 低质心 / 超 tap budget）**fail-loud 提示改 engine_mode**（防误当 B-2 成功）；完整动态分流（`B1_baked`→ASC 烘焙 / `GCM_native`→GCM，需 strategy 跨 engine_mode 编排 + B-1 路 RT→AnnotatedCDLProfile→`.asc` 链）属中等改动，随 PR-5 现场 / 后续。
3. **✅ B-1 金标准对照**（PR-2 CE#42，软件半）：新架构 baked 路 vs 现有直接路径逐位一致；QZ 处 PSD/相关/CDF 实测对照 (标定 `rho_thresh`) 属现场半 (§10.1)。
4. **GUI 暴露（B-2 可执行后，做在本分支）**：① `ENGINE_OPTIONS` 加 `b2_parametric_tdl`（`gui/.../MIMOOTAConfigForm.tsx:126`）；② test_class 选择 → 驱动 B-1/B-2/GCM 分流；③（可选）`native_fit` 残差 / tap 预算占用 / 聚类质量 可见性；④ 加新字段走 4 步契约同步 + 浏览器实测。**现在不做**（B-2 未可执行，暴露 = 操作员选到不工作模式）。
5. **conducted（传导）注入 = 独立条目（横切全栈，本轮 OTA-only）**：2026-06-21 用户确认本轮 B-1/B-2 只做 OTA。现有注入栈 5 策略（ASC/EXTERNAL_ASC/GCM/B2/base）+ ChannelEgine 导出层**全 OTA**（探头展开 + OTA 校准 + PAS 旋转）；conducted 仅在业务模型层（`TestMode.CONDUCTED` / `TopologyType.CONDUCTED`）声明、**注入层 0 实现**。语义与 OTA 根本不同（DUT 天线直连、线缆校准无 `probe_gain`、无探头展开/PAS、文件为天线对而非探头对），需独立设计（拓扑分流 + 线缆校准建模）+ 每引擎（ASC/GCM/B2/B1）加分支。边界 + OTA 校准注入契约见设计 V1.0 §8.1；本轮烘焙器拓扑参数默认 OTA、接口预留。

> 本轮（P2-14 本地实现）做的是**新架构的算法层 + schema + 路由/驱动骨架**（B-1 侧建了 schema F2 + 确定性聚类 F5；B-2 侧建了 F1/F3/F4 + F6/F7）。**未做** = 把新标注结构接到实际文件生成（B-1 烘 .asc / B-2 出 .tap）+ 自动判决 + 金标准 + GUI。这些挂在现场验证之后。

---

### P2-15 — 自定义 CDL 簇编辑（GUI 表单 + 后端 CRUD → 接 input_mode=custom）✅ 完成 (2026-06-28，#170 后端 + #171 前端)

**Status**: ✅ 全 5 切片完成（S1 实体/CRUD + S2 `input_mode=custom` 装配 + S3 GUI 簇编辑器 + S4 `cdl_profile_id` + S5 浏览器闭环）；Codex 1 P1（频率污染）+ 5 P2（num_rays fan-out / round-trip 保真 / engine gate / LOS-K / stale clear）全修。**衍生 → P2-16**（本项暴露信道资产四分五裂，触发多态化收口）。

**What**: 操作员在 GUI 编辑自定义 CDL 的**簇级参数**（每簇 `delay_s` / `aoa_deg` / `aod_deg` / `zoa_deg` / `zod_deg` / `power_linear` / `as_*` / `xpr_db` / `initial_phases_rad`），持久化为可复用实体，测试时选它 → 后端 `input_mode="custom"` → ChannelEgine 合成反映自定义簇。补齐"软件定义信道"在 GUI 的最后一截。

**现状 gap**（2026-06-27 两 agent 逐行查证）: GUI 对 CDL 只能 (a) 选硬编码标称名（`MIMOOTAConfigForm.tsx:104`，对应 38.901 内置表）、(b) 维护 `.smu/.asc` 文件清单（`ChannelModelsCard`）、(c) SCD 标准名→文件映射（`StandardChannelDefinitionCard`）。**簇级参数编辑零支持**（无 GUI 表单、无后端 CRUD）。但引擎侧已通大半: ChannelEgine `CustomCDLProfile` 全簇参数（`cdl_schema.py:82-153`）+ 后端 `channel_engine_client.py:584` 已支持 `input_mode="custom"` + `clusters` 透传 + `/synthesize_hardware_pipeline` 已收 custom。**缺** = MIMO-First 的 GUI 簇编辑表单 + 后端实体/CRUD（采集/校验/持久化）。同族 P2-11（TestCase 驱动）/ P2-12（SCD）/ P2-13（SIMProfile）/ DUTProfile——实体声明 + 单一真值源 + 一致性校验。

**切片**: **S1** 后端 `CustomCDLProfile` 实体（PG: UUID + JSONB clusters）+ 迁移（add-table，方言无关 + column_exists 守门）+ CRUD（`/custom-cdl-profiles`）+ 契约 4 步 + 簇参数 Pydantic 校验（角度范围 / power>0 / delay≥0 / 非空簇）→ **S2** `channel_engine_client` profile→`clusters` 接 `input_mode="custom"`（已有路径，补装配 + 测试 `.asc` 反映自定义簇）→ **S3** GUI「自定义 CDL」卡片（建/编辑/删 + 簇编辑器，支持从标称 CDL「另存为」起步）→ **S4** 接 `MIMOOTAConfigForm`（`cdl_profile_id` 选 custom + 一致性校验）→ **S5** 浏览器实测闭环（claude-in-chrome 建→改簇→测试选→确认渲染+数据+回路）。

**Acceptance**: ① GUI 建 custom CDL（改某簇 AoA/delay/power）→ 持久化 + 列表可见可再编辑；② 测试步骤选该 profile → 后端 `input_mode="custom"` → ChannelEgine 合成的 `.asc` 反映自定义簇（vs 标称 CDL 不同）；③ 簇边缘值（空簇列表 / 非法角度 / power≤0）fail-loud 422；④ 浏览器实测闭环通过。

**分支**: 在 `feat/b2-channel-injection`（信道领域分支）做——custom CDL 是信道功能；做完独立 PR + Codex + merge 回 main。

**关联**: 跟 P2-14（信道注入 B-2）衔接——custom CDL 簇是"自定义信道"入口，B-2 的 RT 子径（`MPCInput`）是更细一层。memory [[project_scd_frontend_consumption_gap]] / [[project_testcase_driven_instrument_arch]]。

---

### P2-16 — 信道资产多态化（统一 GCM/B-1/B-2/RT 四源 → ChannelAsset 多态实体 + 独立信道工作台）🔄 in-progress (2026-06-28) — S1 ✅ (#173) / S2 ✅ (#174) / S3 ✅ (#176–179) / S4 ✅ (独立工作台四编辑器 + 消费接通, #181–185, 2026-06-30) / deprecate-legacy ✅ (消费收敛到 ChannelAsset #187/#188 + 旧编辑器 deprecation 引导 #189, 2026-07-01) — 余 S5/S6 现场

**What**: 把四分五裂的四种信道源——GCM `.smu` 文件指针 / B-1 ASC 瞬态合成 `.asc` / B-2 参数 TDL `.tap` / RT 动态——统一为单一多态 `ChannelAsset` 实体，对 TestCase 暴露单一 `channel_asset_id`（取代现在 `scd_id` / `cdl_profile_id` / `asc_source_path` / `config.extra` 裸 RT dict 四套并行引用）。GUI 终态独立「信道工作台」（非 DUT/SIM 同栏）。设计见 [`design/channel-asset-polymorphism-design_V0.1.md`](design/channel-asset-polymorphism-design_V0.1.md)（2026-06-28 三路代码考古 grounded）。

**两个核心洞察**: ① **「来源」(参数从哪来：标准 / 自定义 / RT / 厂商文件) ⊥ 「路径」(怎么落硬件：.asc / .tap / .smu)** 两维被 `EngineMode` 揉成一维 → 解耦，路径由 §6 判决决定（"B-2 参数化"严格说是*路径*不是*来源*）；② **统一载体不新发明**——ChannelEgine 的 `AnnotatedCDLProfile`（snapshots + `doppler_repr` 联合体）已能装四源，`CustomCDLProfile` 是其单快照退化子集（`from_custom_profile` 已证），多态化 = 把它提升为 MIMO-First 持久实体（V1.0 §11 开放问题 #4）。

**决策（2026-06-28 用户拍板）**: (1) GUI **独立信道工作台 + 渐进迁移**（G0 现状 → G1 后端统一 → G2 独立页收口 SCD（仪器抽屉）+ custom CDL（AssetProfiles）两处分裂 → G3 接 RT/判决可视化），对标 Channel Studio；(2) 起步 **软件半全做 S1–S4**，零现场依赖。

**切片**:
- **S1** ✅ 完成 (#173) — `ChannelAsset` 实体 + migration（PG/SQLite 三路径 + `table_exists`/`column_exists` 守门）+ CRUD + 多态 payload schema（`source_type` 判别联合体：`standard_3gpp` / `custom_static` / `rt_dynamic` / `vendor_file`）+ 契约 4 步同步。
- **S2** ✅ 完成 (#174; 9 轮 Codex review / 11 个 P2 全修：filename load+accept / canonical 重派生 / arfcn NR域 / rt velocity / external_asc 旁路 / standard·rt 频率传播+center须配bw / custom pathloss·num_rays 守门 / 合并状态校验) — custom CDL + SCD 收口（数据迁移 clusters→`payload.snapshots[0]` / scd 配置→`payload.scd_config`；`cdl_profile_id`/`scd_id`→`channel_asset_id` backward-compat 复用 id）。统一频率一致性网（消除现「scd_id 进网、cdl_profile_id 不进」的不一致）。
- **S3** ✅ 完成（软件半全收口）装配层 `payload→AnnotatedCDLProfile` + §6 判决路由（接线设计 §1.2 断层 C 的三个悬空函数进生产微服务 + api-service 升路由）。**关键纠正**：装配/判决/F4/F5/bake 全在**微服务侧**（ChannelEgine 经 `CHANNEL_ENGINE_PATH` import，MIMO-First↔微服务 wire 是扁平非 ACP）；§6 `select_path_and_clustering` 早被 `cluster_b2_native` 消费（非「全悬空」）。
  - **S3-1** ✅ (#176) `bake_b1_annotated` 接线 — synthesize `routing_mode=annotated_b1`（custom→`from_custom_profile`→bake，与 legacy run() 逐位等价 golden 证）。
  - **S3-2a** ✅ (#177) `native_fit_trajectory` F4 — 新端点 `cluster_b2_trajectory`（多快照 RT→逐快照 native-fit+跨快照生灭跟踪→per-snapshot tap；先过 §6 判决门非 B2_parametric→422）。
  - **S3-2b** ✅ (#178) `phase_continuous` F5 — 新端点 `synthesize_deterministic_b1`（isac/beam 确定性相位→§6 确认 B1_baked（大质心→GCM/ESCALATE 422）→subray_sum ACP→bake→.asc；用户定 cal 烘进 .asc）。
  - **S3-3** ✅ (#179) api-service `custom_static` 升路由到标注式 B-1 烘焙脊（`routing_mode=annotated_b1`，统一 ACP 烘焙脊）+ 验收③（#176 golden 传递性证）+ 修 #178 跨服务 import 漏网 bug。
  - Codex 跨四 PR 共 2 P1（轨迹判决门绕过 §6 / 确定性 cal 丢失）+ 3 P2（annotated fail-fast / 文件名消毒 / cal parity）全修。**rt_dynamic 调 trajectory/deterministic 端点的 api 接线延 S5**（真实 rt 数据现场；合成 rt 算法测已在微服务侧做，用户 2026-06-30 定最小 scope）。
- **S4** ✅ 完成（2026-06-30）— 独立「信道工作台」GUI（G2）四 `source_type` 编辑器（**新建于工作台**，旧 AssetProfiles 簇编辑 / 仪器抽屉 SCD 卡片暂留共存，未删）+ **消费侧接通**，各切片 claude-in-chrome 浏览器实测闭环：
  - **S4-1** ✅ (#181) 工作台 shell — ChannelAsset 统一列表 / 查看详情（payload JSON）/ 软删 + source_type 分类过滤。
  - **S4-2** ✅ (#182) `standard_3gpp` + `vendor_file` 建/编辑表单（CDL 名 / scd_config + .smu）。
  - **S4-3** ✅ (#183) `custom_static` 簇编辑器（嵌套 modal 编辑 `CDLClusterPayload` 12 字段）。Codex P1 = 编辑保留 `payload.pathloss_db`（merge 既有 payload 不整体替换，类型-运行时盲区）。
  - **S4-4** ✅ (#184) `rt_dynamic` 多快照射线编辑器（Accordion 快照数组 + 嵌套射线 modal）。Codex P1 = 多快照执行 fail-loud（`channel_asset_resolver` `snapshots>1` raise，轨迹执行待 S5）+ GUI Alert 警示；P2 = per-snapshot 元数据（time/position/velocity）编辑保留。
  - **S4-5** ✅ (#185) 接消费侧 `channel_asset_id` 进 `MIMOOTAConfigForm`（统一信道资产 Select → 后端 resolver 派生 `engine_mode` + 覆盖传统字段；选了禁用下方传统选择器）。Codex P2 = 多快照 rt option 禁用 + 标注「执行待 S5」。**让信道工作台真正驱动 test 执行** —— 调研发现此前 ChannelAsset 是**孤立 authoring 层**（`channel_asset_id` 后端 resolver S2 已接，但 GUI 零处喂，测试步骤 100% 走 legacy `cdl_profile_id`/`scd_id`）；本切片补上 GUI 消费缺口（用户 2026-06-30 拍板「接消费侧」重定义原 S4-5）。
  - **deprecate-legacy** ✅ 完成（2026-07-01，用户拍板；Codex #174 cebb394 + 2026-06-30 调研）— S4-3 工作台编辑 + legacy 编辑并存让迁移实体 stale-copy 变**双向**（两份副本 `custom_cdl_profiles`/`standard_channel_definitions` + `channel_assets` × 两条消费路径 `cdl_profile_id`/`channel_asset_id`）。用户选**消费收敛到 ChannelAsset**（非 dual-write）根治：
    - **DL-1a** ✅ (#187) `cdl_profile_id` 消费收敛 — `asc_strategy` 命中同 id `custom_static` ChannelAsset 走其 payload（`find_custom_static_asset` 非 raise getter），未迁移 legacy-only 仍读旧表。
    - **DL-1b** ✅ (#188) `scd_id` 消费收敛 — `resolve_emulation_for_measure` 命中同 id `vendor_file` ChannelAsset 用其 `associated_file_path` + `scd_config` 频率（对称 `find_vendor_file_asset`）。
    - **DL-2** ✅ (#189) 旧 CDL/SCD 编辑器加 deprecation Alert 引导到信道工作台（保留功能不硬禁用 —— 存量未迁移档案仍可编辑，无对应 ChannelAsset 时消费仍读旧表）。
    - 效果：ChannelAsset 成 custom/vendor 迁移实体的**单一真值源**，双向 stale 根因消除；旧 `cdl_profile_id`/`scd_id` 路对未迁移实体仍 live 兼容（方案 A 不破坏）。物理删旧表/端点留将来（存量档案 + 向后兼容仍需要旧表）。
- **S5**（🚧 现场）`rt_dynamic` 真实 RT 数据接入（Lauraycs RT + RT-Release）+ 多快照 **轨迹执行装配**（时空跟踪逐快照合成；现 resolver 对多快照 fail-loud，待此接通后多快照 RT 资产方可执行 + GUI 解禁多快照 option）。
- **S6**（🚧 现场）`b2_parametric` `.tap` 落地 + F64 验证 + GUI engine 暴露（合 P2-14 第 4 项「GUI 暴露」）。

**Acceptance**: ① ✅ `ChannelAsset` CRUD + 四 `source_type` 多态 payload 持久化/校验（边缘值 fail-loud）（S1 #173）；② ✅ 旧 `cdl_profile_id`/`scd_id` 经映射零破坏跑通（PG / SQLite-brownfield / SQLite-greenfield 三路径测）（S2 #174）；③ ✅ 一个 `custom_static` 资产经判决路由正确分流到 `asc_baked` 合成 `.asc`（与现直连结果一致）（S3 #176/#179：custom_static→annotated_b1 烘焙脊，#176 golden 证逐位等价）；④ ✅ 独立信道工作台 GUI 浏览器闭环（建 / 切 `source_type` / 编辑簇·射线 / 选进 TestCase 驱动执行）（S4 #181–185，各切片 claude-in-chrome 闭环：建四类资产 + 测试步骤选 `channel_asset_id` → 后端 `step.parameters.channel_asset_id` 持久化指向正确资产）；⑤ ⏳ S5/S6 挂现场。

**分支**: 新分支（信道领域）；按切片独立 PR + Codex + merge 回 main（沿用 P2-14/P2-15 模式）。

**关联**: P2-15（custom CDL = 本实体 `custom_static` 特例）/ P2-12（SCD = `vendor_file` 特例）/ P2-14（B-2/RT 路径 + 现场半 S5/S6，第 4 项 GUI 暴露并入 S6）。memory [[project_b2_universal_channel_injection_design]] / [[project_testcase_driven_instrument_arch]] / [[project_scd_frontend_consumption_gap]] / [[project_ota_probe_baseband_rf_two_layer]]。

---

### P2-17 — F64 直通/衰落模式编排 (attach 默认直通态 + 状态机) ✅ Done (2026-07-04 #201)

> 收口: ① 状态机进驱动 — `set_bypass_mode` 运行态切 STATIC≠0 同步 STOPPED 状态;
> `start_emulation` 内建 GO 前清直通 (STATIC 0, 不赌加载复位); ② attach 默认直通
> 编排落 `baseStation_attach_check` (param `establish_f64_passthrough` 默认开:
> 真实 CE 在场 → stop+STATIC 3, 失败 fail-loud; 无 CE 线缆直连跳过); ③ 由 P1-21 ④
> 覆盖。9 用例 (状态机 5 + 序列 4)。真机验收 = attach→吞吐零人肉模式切换, 下次现场。

**What**: ① `set_bypass_mode` 状态机编排 —— 2026-07-03 破解的语义: STATIC(静态直通)与回放互斥, STATIC≠0 时 GO 被拒(-200 by design), 运行态切 STATIC 自动 STOPPED, **直通稳态 = STOPPED + STATIC 3**, 恢复衰落 = STATIC 0 + GO; ② commissioning 流程编排: attach 阶段默认建立直通态(DUT 好接入, -96 RSRP 实证可用), run/measure 前**显式 STATIC 0**(不赌加载复位); ③ cockpit/驱动: 输出功率测量 STOPPED 冻结语义标注(与 P1-21 ④共享)。

**Why P2**: attach 流程质量项(直通态今日人肉建立成功); 非阻塞(现场可两条命令人肉), 但产品化后 attach 全自动。
**Acceptance**: mock 单测状态机全路径(含 -200 拒绝分支); commissioning attach phase 自动直通、mimo_test phase 自动恢复衰落; 现场验收 = attach→吞吐全程零人肉模式切换。
**来源**: [`guides/onsite-tasks-20260703.md`](guides/onsite-tasks-20260703.md) discovered "F64 直通态建立"条。**Estimate**: ~1 day。

---

### P2-18 — 信道资产真值自动化 (SMB 扫描 + EMQuest 权威表数据化)

> **编号继承（2026-08-12）**：本条是早期母项；重新 triage 后，仍未交付的本地自动化范围已稳定编号为顶部队列 **P2-31**。后续施工、PR 与完成状态只更新 P2-31，避免 P2-18/P2-31 两个开放编号重复推进；本段保留来源与完整验收背景。

**What**: ① .smu 工程频率扫描器: SMB 只读挂载 → 解析 `[Channel Group 0] CenterFrequency`(解析器 2026-07-03 已验证, 金标准=面板实证)→ available_channel_models / ChannelAsset 自动真值化(今日 `scripts/onsite-fix-f64-scenario-assets.py` 手工流程的产品化: 后端周期扫描或一键同步端点); ② EMQuest prm 破译出的 band→(dl_arfcn/ssb_arfcn/point_a/offset_to_carrier/duplex) **10 band 权威查表**入 repo 数据文件(prm 二进制解析脚本一并入库), 供 P1-19 ④ SSB 下发与 onsite 脚本消费; ③ n79 栅格注意项(4700.000 非 15k 整栅格, EMQuest 用 713334)。

**Why P2**: "SCD 频率以工程实测为准"(用户定流程)的自动化; 手工 18 条已就位, 自动化防 drift + 支持后续场景包扩展。
**Acceptance**: 一键/周期扫描后 channel-models 与 vendor 资产频率=工程值(mock SMB fixture 单测); band 查表被 P1-19 消费有契约测试。
**来源**: onsite 文档 discovered "文件名≠工程频率全案终局"/"EMQuest prm 全集破译"条 + memory [[project_f64_smu_filename_freq_mismatch]]。**Estimate**: ~1.5 day。

---

### P2-19 — 执行观测一致性（相位计数 token 错配 + 日志面板收尾）✅ Done (2026-08-01)

**What**: ① `api/test_execution.py::_to_history_item` 相位计数谓词 `"completed"` vs runner 写
`"success"` token 错配 → `phases_done` 对所有行恒 0（后端一处修，历史表/主控台卡/库进度三处
全好，含错误 docstring 种子清理）；② 主控台日志面板多选/默认态仍是 P2-11 失效模式的 GUI 收尾。
**Why P2**: 现场排障靠这些面板，观测层失真直接烧现场时间（7-21 教训）。
**来源**: Discovered 区 S6 相位计数条 + P2-8 日志面板条（[→ P2-19] 已标）。**Estimate**: ~0.5 day。
**收口 (2026-08-01)**: ①计数谓词 token 对齐唯一写方（`"success"`，"completed" 从来不是合法 token —— StepExecutionStatus 四值枚举核定）；连环挖出**四处同错自洽站点**（实现谓词/docstring/测试 fixture/断言内联谓词 —— docstring 是种子，fixture 与断言照抄后门验了个寂寞），四处一次收口 + 变异实跑 3 红。②日志面板改"主流保 RAW 邻接 + WARN/ERROR 各一路下推补充流"（RAW 无 ts 且 level 精确匹配会丢，不能纯逐 level 合并）+ badge 显示"最深已扫 N 行"。浏览器三消费方实证：主控台卡 5/5 满条 / 历史表 5/5 / 面板 360 条·已扫 20000 行（补充流捞回 160 条被冲出的低频行）。

### P2-20 — VRT 场景库健壮化 ✅ Done (2026-08-01)

**What**: ① `_list_custom_scenarios` 单行坏配置 500 全列表（一行坏数据炸整库，改逐行降级）；
② 标准场景库 5 处 `channel_model=` 死 kwarg + 其余读写方 3 站点同母题清单收口。
**Why P2**: 与 #253 修掉的"场景静默消失"同族 —— 单点坏数据不该有全局爆炸半径。
**来源**: Discovered 区 #253 三条（[→ P2-20] 已标）。**Estimate**: ~0.5 day。
**收口 (2026-08-01)**: ①`_list_custom_scenarios` 逐行降级（单行坏配置跳行 + ERROR 报数，不再 500 全列表，跳行是响的不是静默）；②标准库 5 处 `channel_model=` 死 kwarg 转正为 `channel_snapshots` 单快照（5 场景 UMa/UMi/RMa/UMa/UMi 对位，兑现 #253 测试注释"修好后改为期待具体模型值"）；③报告读方 `EnvironmentInfo` 换源快照；④`ota_scenario_mapper` 5 处死字段读换源 + 零调用方状态头注申报；⑤GUI 写侧 Create/Edit 对话框把表单所选模型写进快照真值位置（此前恒发 `[]`，模型只进 tags）。运行门：Playwright 无头闭环 —— 建场景选 RMa → POST 201 payload/response 快照带 RMa → 列表卡片可见。

### P2-21 — P1-12 可信化标志渲染可达化 + 证书 CJK ✅ Done（本 PR）

**What**: ①`executors/report.py` 的 `quiet_zone_verified` / `trp_verified` / `path_loss_verified` 三标志挪 `parameters` 下（渲染器只读 name/step_name/parameters，顶层键进不了 PDF —— 修法与 P1-22 的 analysis 站点同构）；②`pdf_certificate.py`（校准证书）注册 CJK 字体（与 P1-22 的 pdf_generator 同构，证书中文今天全豆腐块）。
**Why P2**: P1-12"报告必须标注 未验证(兜底值)"的意图从未生效 —— mock TRP / 无路损校准的报告零提示，现场拿着假干净报告做判断。**来源**: Discovered 区 P1-22 内审 F3 补欠条（[→ P2-21] 已标）。
**落地（本 PR）**: ①三 step 渲染载荷整体进 parameters（中文键 + 三值可读标注"已验证 (…)/未验证 (…)/未知 (历史数据未区分)"，顶层死键删净），行为门打在渲染器实际产出（步骤区 elements 里断言标注文本可见）；②pdf_certificate 三族收敛 CJK_FONT（import 自 pdf_generator 单一真值源）+ 证书 PDF 字节含 STSong 行为门；backcompat 推导测试断言迁到新生效端。4 变异实跑全红。

### P2-22 — F64 disconnect 冷缓存判 GOS 换真值源 ✅（F64R-1 / #225 已交付；2026-08-11 复核收口）

**What / completion evidence**: 原缺口是 `disconnect()` 依赖 `_emulation_running` 冷缓存判“要不要 GOS”，HAL 重载后可能把仍在播放的 F64 留下。复核确认 #225 的 F64R-1 已将判据换成仪器 `DIAG:SIMU:STATE?` 真值：`RUNNING` 或读不到时保守 GOS，`STOPPED/CLOSED` 跳过 GOS；只有明确 `CLOSED` 才跳过幂等 CLOSE，且传输层断链单独 fail-loud。定点回归 `TestDisconnectAsksInstrument::test_stops_when_instrument_running_despite_cold_cache` 与 `test_disconnect_confirms_closed_even_with_cold_cache` 已锁住冷缓存场景。NotebookLM（“PROPSIM 资料”，2026-08-11）核对厂商原文：Propsim User Reference §20.4.3.14 定义 STATE? 七态及 RUNNING/STOPPED/CLOSED；§20.4.3.11 定义 GOS 为 stop + rewind；§20.4.3.18 与 ATE environment and practices AN §2.2.2 定义 CLOSE，后者明确未加载时 CLOSE 不会在远程接口报错、可作 fail-safe。先查 STATE? 再决定 teardown 是建立在这些原文上的工程判定，不冒充厂商直接规定。**来源**: #206 补扫（[→ P2-22] 已标）；实现：#225 / `62cd796`。

### P2-23 — 会话资产 is_active 预检 + resolver 同病排查 ✅（2026-08-11 本地完成）

**What / completion evidence**: `POST /commissioning/sessions` 在创建 TestCase/TestExecution 前以 `is_active is True` 白名单拒绝退役资产并返回 422。MEASURE 侧已枚举并收口三条 live 消费路径：①显式 `channel_asset_id` 在任何仪表连接/配置前 fail-loud；②历史 `cdl_profile_id` 命中同 UUID 的 `custom_static` ChannelAsset 时，退役资产不得进入 ASC 合成，也不得回落 legacy twin；③历史 `scd_id` 命中同 UUID 的 `vendor_file` ChannelAsset 时，退役资产不得返回 `.smu`，也不得回落 legacy twin。软删仍保留实体与历史引用，历史记录可读，但“可追溯”不再等同于“可重新执行”。HTTP 回归断言失败时 TestCase/TestExecution 均不新增；执行级回归锁住显式路径必须在硬件 connect 前失败，两条兼容回归锁住退役配置不会重新进入 ASC/GCM。**来源**: Codex #262 R2（[→ P2-23] 已标）。

### P2-24 — 测试用例契约补 lab_profile_id ✅（2026-08-11 本地完成）

**What / completion evidence**: `TestCaseCreate`/`TestCaseUpdate`/`TestCaseResponse` 已贯通可空 `lab_profile_id`；创建可绑定、编辑可换绑，PATCH 显式 `null` 可解除绑定，字段省略仍保持原值。OpenAPI 新增 TestCase CRUD 契约并重生成 TypeScript；共享 GUI service、TestCase service 与 mockServer 使用同一字段形态。创建弹窗列出 LabProfile：唯一活动实验室自动选中，多个活动实验室必须显式选择；列表加载中或失败时 fail-closed，模板异步回读不会被旧请求覆盖。编辑弹窗显示当前绑定并允许换绑/清空，已停用实验室只作历史展示、不可新选。后端创建与发生变化的换绑复用 `resolve_lab_profile()` 权威判据，仅接受活动实验室；显式清空仍保留。行为回归锁住创建→换绑→清空以及 inactive 绑定 422，契约同步回归锁住四步、两个弹窗和加载失败门；相关 84 passed，GUI production build 通过。**来源**: Codex #250 P1 遗留（[→ P2-24] 已标）。

---

## 🟢 P3 — Polish / tooling

**P3-1～P3-19 ✅ Done；P3-20/P3-21 已转非阻塞维护池，P3-22 为当前队列末项。** 已完成项的完整 What / Fix / Acceptance 详情已迁出 → [`roadmap-archive.md`](roadmap-archive.md)；新增项的当前范围与顺序只看顶部 Current Focus 表。速览：

| ID | Item | Done |
|----|------|------|
| P3-1 | HAL Reload confirm dialog | ✅ |
| P3-2 | Driver self-test CLI | ✅ (D15) |
| P3-3 | Capability gap viewer in GUI | ✅ (D14) |
| P3-4 | F64 `SYST:INFO?` structured parser | ✅ (D17) |
| P3-5 | Startup readiness summary expansion | ✅ (D18) |
| P3-6 | Chamber preset Type-C `has_lna` test reconciliation | ✅ |
| P3-7 | VSCode interpreter settings + `.vscode/` gitignore policy | ✅ |
| P3-8 | VRT pydantic regression fix | ✅ |
| P3-9 | Catalog `status` enum contract drift | ✅ |
| P3-10 | Alembic chain head hardcoded SHA | ✅ |
| P3-11 | `bootstrap_lifespan` seeder set drift | ✅ |
| P3-12 | `driver_capabilities` test-isolation pollution | ✅ |
| P3-13 | `probe_calibration_service` invalid-probe sentinel drift | ✅ |
| P3-14 | 契约收尾（`test_type` 描述 / `template_category` max_length / `CreateSessionRequest` 缺 `channel_asset_id` / 频率粒度余站点）+ 门 G-A（schema 描述⊇枚举，落地为 test_rule_gates **G9**） | ✅ 本 PR |
| P3-15 | 数据/测试卫生批 | ✅ 本 PR — ①`test_feature_gaps` SQLite 隔离（实证跑前后 dev 库计划数不变）②2 flaky triage=**已被 #211 护栏修好**（受害测试自带 `.disabled` 复位 fixture，恶意排序复现失败，Discovered 行系 stale）③vendor_file 顶层声明 vs scd_config 一致性 fail-loud（create/update 双侧、最终状态判、2 变异红）④僵尸 triage：来源已断 + 存量 1201 计划/~2700 子行走 `scripts/cleanup_zombie_test_plans.py`（dry-run 默认，删除须操作员 `--execute`——批量删库不自动执行）|
| P3-16 | 门 G-B：状态列注释 ⊇ 全仓状态字面量 | ✅ 本 PR — 落地为 test_rule_gates **G10**：真值源 = live import `TestExecution.__table__.columns['status'].comment`；写点识别双判据（`TestExecution(status=…)` 构造 + `execution/ex/test_execution` 变量属性赋值，2026-08-01 全仓 AST 普查定的；conn/session 等别的 status 域不误伤、动态值写点不归字面量门管——宁漏报不误伤）；checker 行为自测 + 变异实跑红（写入 'exploded' → 红） |
| P3-17 | 门 G-C：文档 (动词,路径,参数,响应键) ⊇ 真实实现 | ✅ 本 PR — 落地为 test_rule_gates **G11** 双半：①散文半 = 现状文档**全 API 面** (动词,路径) ⊆ 路由表（G8 只锁计划链域；实值段通配匹配器防误杀示例；设计愿景文档/跨服务路由显式豁免并申报）②契约半 = checked-in openapi.yaml (路径,动词,参数名,2xx 响应键) ⊆ live schema —— 参数/响应键维度的机械落点（散文书写形态不可机械解析，实施时定的收窄）。首跑即抓 3 条 yaml 说谎（dashboard camelCase 三键 / category 包层 / 选择 profile 的 PUT 挂错路径）+ 2 条散文死引用，全修；openapi:generate 重生成 + GUI build 绿；双变异实跑红 |
| P3-18 | 门/测试精化批（G11 三覆盖面 in=location/curl 动词/schema 类型 + p08 零残留站点参数化 + PDF 渲染管道其余转义入口 + 诊断序列 run endpoint 串行化 + 手写类型审计尺子改逐层递归比对）——2026-08-02 拍板，各配变异。PDF/G11/p08/诊断序列/手写类型五片已分别由 PR #326/#327/#328/#329/#330 合并；最后一片删除 7 条零消费 live fetch、隔离 `MockMonitoringFeedsResponse`，并把递归审计发现的 9 组活动契约差异登记 Discovered。 | ✅ |
| P3-19 | 日志/告警/留痕卫生批（~~tail 反向扫描字节上限~~ ✅ PR #331 + ~~端口清理进程 allowlist~~ ✅ PR #332 + ~~UXM 终止符大小写~~ ✅ PR #333 + ~~UXM ARFCN 三条加固~~ ✅ PR #334 + ~~mock-only 遗留响应类型与 handler~~ ✅ PR #335 + ~~校准 warnings DB 持久化~~ ✅ PR #336 + ~~借用 acquire 的清理失败警告进入底层结果~~ ✅ PR #337 + ~~超大 traceback 逻辑组 fail-closed~~ ✅ PR #338 + ~~正式执行失败告警通道~~ ✅ 本 PR）——2026-08-02 拍板。最后片在正式 runner / commissioning 终态所有者提交 `failed` 后，以独立 session 写一次性 `execution_failed` active Alert；全部生命周期去重，告警失败不回滚执行，调试/废弃/VRT/KPI 不通过均排除。⚠️ 原含的 app.log 噪声治理已由 P1-35完成；PR #338 外审指出的摘要镜像也已删除，不再施工 stale namespace 阈值。 | ✅ |

---

## ⚠️ Known unknowns (verify on-site / next session)

| ID | Question | Verification path |
|----|----------|-------------------|
| U-1 | Does CAICT NAT really drop idle TCP entries? | Idle-then-poke test, see [P2-4](#p2-4--natfirewall-idle-drop-hypothesis-verification) |
| U-2 | Are `OUTPut:INTERFerence:LIST?` / `SYSTem:CALibration:USER:LIST?` the right soft-probes on F64? | On-site execution, see [P1-2](#p1-2--f64-license-probe-scpi-on-site-verification) |
| U-3 | Which UXM Test Apps does CAICT actually use (beyond 5G NR / LTE_NR_IRAT)? | Inventory at next on-site |
| U-4 | What are the common DUT attach failure modes (IMSI / SIM / RRC state)? | First DUT attach session, see [P0-5](#p0-5--dut-attach--bearer--pdsch-on-uxm-5g-nr) |
| U-5 | 转台 (Aerotech A3200) 单轴/多轴定位与回零行为? | **offline 半 done (2026-06-04)**: driver 本就完整 (HOME/MOVEABS/PFBK/ABORT/单轴回零), "无结论"真因是**无 standalone 控制路径** → 补 `/instruments/positioner/*` 端点 + GUI 调试维护"转台控制"Tab + 12 测试 (见 [positioner-turntable runbook](site-debug/2026-06-04-positioner-turntable.md))。现场半: 按 runbook 验真机回零→定位→4方位扫 + 角度一致性, 关联 P0-5 |
| U-6 | F64 各输入"信号参考"的正确 level (dBm) + crest factor (dB) 真值 (针对 3600M/N78 模型 + UXM DL 功率)? | 下次现场用 `INP:LEV:AUTOSET` 自动测 + 看输入口变绿 + DL 不失真, 关联 P0-8 |
| U-7 | UXM 正确测试参数集真值 (band/BW/SCS/ARFCN/MIMO/power/FRC for 3600M N78) + remote 机器上现存哪些 `.state` 文件 (路径/内容)? | 下次现场: 盘点 UXM 已存 `.state` + 用默认 Topology Profile (P1-17) 验 cell live + 对齐 F64 频率/MIMO; 关联 P1-17 |
| U-8 | Aerotech AeroBasic/TCP 活跃控制路径的现场型号与固件如何只读确认？ | P0-5 前从厂商手册确认安全身份查询并接入真实环境快照；数据库/连接配置声明不能代替实时身份 |
| U-9 | 转台控制坐标到暗室 DUT 物理方位的偏置真值与标定状态是什么？ | P0-5 正式 TestCase 前完成坐标偏置标定、保存可追溯来源并验证四方位反馈误差 ≤ ±1°；当前 `None/False` 必须保持 unknown |

---

## 🗂️ Discovered during X — 待评估发现池（不是正式 backlog）

> 开发中途发现的事实先进入本区，**尚不代表已经决定要做**。每周 triage 后必须走一个
> 显式出口：①提升到 P0/P1/P2/P3；②并入已有 roadmap 项；③进入正式延后 backlog；
> ④进入 ON-SITE-BLOCKED / HOLD / Known unknown；⑤ resolved / dropped。
> 没有出口标记的条目仍是“待评估”，不得出现在 LOCAL-OPEN 执行队列里。

### 2026-08-21 triage checkpoint（以下出口覆盖下方保留的原始发现措辞）

| 原发现 / 同族 | 出口 |
|---|---|
| CA 多小区吞吐只读 PCell | → **P1-59** |
| pytest 与运行服务共用日志目录 | → **P2-39** |
| UE L3 报告队列无界读取 | → **P2-37** |
| Dashboard readiness 不消费显式 LabProfile | → **P2-38** |
| 开发环境 DB / 日志沉积 | → **P2-40** |
| 重复抑制桶级别、traceback 搜索、CRITICAL、级别多选 | ✅ **P2-33 / PR #360** |
| 校准/方向图逐点租约 | ✅ **P2-30 / PR #359** |
| `uxm_scpi_compatibility` IRAT 假失败与四态折叠 | ✅ **P1-58 / PR #358** |
| `current_execution_id` 测试间泄漏 | ✅ **P2-35 / PR #357** |
| 执行失败告警发布结果 | ✅ **P2-34 / PR #361** |
| P3-14 频率输入/显示粒度与 TestCase 摘要换源 | ✅ **P3-14 / PR #262** |
| P1-55 顶层与 PCell 真值分叉 | ✅ **P1-55 / PR #349** |
| 执行历史一键跳日志 | ✅ **P1-39 / PR #292** 已交付；P2-36 重复项已关闭 |
| SMB / EMQuest 自动化 | 保留并收窄 **P2-31 = SMB `.smu` 工程扫描**；EMQuest 10-band 表已交付 |
| QZ / Pattern / Multi real warning 闭环 | → 功能启用池（原 P2-32，不进当前执行队列） |
| 失效校准导入/导出、两套 UXM 诊断 error reader | → 非阻塞维护池（原 P3-20/P3-21） |
| G11/p08/G20/变异保护等纯测试门精化、默认关闭 mock、已执行计划文字镜像 | → 非阻塞测试/文档维护池，不再编号 |
| 无 live caller 的 helper、无害 orphan/stale 常量、单次重复请求、纯 UI 微调 | → 非阻塞维护池，等待独立可观察价值再评估 |
| 厂商手册未说明、真实硬件未核验、现场身份/坐标/偏置 | → Hardware Blocked / Known unknown，禁止本地猜测 |

> 下方原始条目保留发现时的证据和失败场景；其中“待 triage”等旧措辞不再代表当前状态，
> 当前执行真值只读本 checkpoint 与顶部 Current Focus 表。

- `[discovered 2026-08-11 during P3-18 G11 external review, Codex #327 R1]` **G11 未合并 OpenAPI Path Item 级 parameters（P3，待 triage；不阻塞已合并子片）** —— 当前 location 比对只读 operation 自身的 `parameters`；若 query/header/cookie 参数声明在 Path Item 级并对全部动词生效，它从 live 消失或换 location 时本门仍可能假绿。后续若继续精化 G11，应把 path-item 与 operation 两层参数按 OpenAPI 覆盖规则合并后再比较；按测试门意见上限记 P3，不为其启动第二轮。

- `[discovered 2026-08-11 during P3-18 p08 external review, Codex #328 R1]` **p08 参数门锁住 checkpoint 存在与标签，但未直接锁调用位置（P3，待 triage；不阻塞已合并子片）** —— 当前 fake 错误是在 `residue()` 内注入；若以后把某个 checkpoint 移到受保护写操作之前但保留标签，参数用例仍可能通过。功能实现与本轮逐站错误归档均已复核正确，本项只登记为测试精化候选，不为其启动第二轮。

- `[discovered 2026-08-11 during P3-18 G11 internal review]` **G11 curl 动词抽取仍不覆盖引号 + 反斜杠续行（P3，待 triage；本片 Ready，不阻塞）** —— 当前判据只在 URL 同一行、且动词位于 URL 前时识别 `-X/--request`；live `docs/api/swagger-guide.md` 已存在 `curl -X 'POST' \\` 后下一行写 URL 的形态，若把 POST 错改成 DELETE，门仍只核路径而假绿。后续应先把反斜杠续行归一成一条逻辑 curl 命令，再允许引号包裹的动词；不为测试门增强启动本轮第二次修复。

- `[discovered 2026-08-11 during P3-18 G11 internal review]` **G11 schema 原始类型比较尚未表达 JSON Schema 可赋值关系（P3，待 triage；本片 Ready，不阻塞）** —— 本片要收口的明确故障是 object/array 容器相反时仍只比 properties；当前 helper 同时严格比较全部显式 `type`，可能把 checked-in `number`、live `integer` 这类合法收窄误报为不兼容。后续可只对 object/array 容器做本门承诺的比较，或另片实现 JSON Schema assignability；不扩大当前边界。

- `[resolved 2026-08-16 by P1-52 / PR #345]` **TestCase 编辑弹窗吞掉 LabProfile 列表加载失败** —— 已拆开详情与列表状态：失败时冻结选择、显示可重试错误，PATCH 省略 `lab_profile_id` 以保留原绑定；仅在列表成功且操作员明确改变选择时发送新 ID 或 `null`。两轮 Codex 外审完成，组件到 PATCH 的真实 wiring 受变异会红测试保护。

- `[discovered 2026-08-11 during P2-24 internal review]` **启用前端 mock server 时缺少 `/lab-profiles` handler（P3，待 triage；当前 mock server 默认关闭）** —— TestCase 创建/编辑弹窗已经改走共享 client，并在 LabProfile 列表不可用时 fail-closed；未来若重新启用浏览器内 mock server，需要给 lab-profiles 补一组与 live 分页/active 过滤一致的 handler，否则该弹窗会正确阻止创建但无法完成演练。本轮不为默认关闭的测试辅助模式扩大实现。

- `[discovered 2026-08-11 during P1-29 G19 全路由枚举]` **[→ 提升 P1-49；PR #342 R1 无 P1，待 R2/merge] 两条存量静态路由被更早的 path 参数路由遮蔽** —— `GET /api/v1/calibration/channel/temporal/{calibration_id}` 曾先吃掉后声明的 `/temporal/latest`（GUI `channelCalibrationService.ts` 有活消费者）；`api/topology.py` 的同一个 `topology.router` 内，`GET /api/v1/topologies/{topology_id}` 也曾声明在 `/topologies/default` 之前。P1-49 已将两个字面量 GET handler 移到同级 UUID GET handler 之前，真实 HTTP 回归锁定静态端点不再返回 `uuid_parsing` 422，合法 UUID 详情路由保持 404 语义；G19 两个存量例外已删除，后续新增同类遮挡直接失败。

- `[discovered 2026-08-11 during P1-38 review]` **P1-38 测试与 G20 精化候选（P2/P3，待 triage；非本轮功能缺陷，默认不实现，归 P3-18 同族）** —— **P2**：清理测试目前用 `message` near-miss 证明内容白名单不能宽匹配，但没有再对 `title` / `severity` / `alert_type` / `status` 四个字段逐个做单字段变异；功能谓词本身已逐字段精确匹配，本项只是测试保护可更细。**P3**：G20 是 AST 语法门，常量间接传入 `source` 或声明了但未执行的 fixture 可能绕过，纯构造 payload 又可能被误判为真实写入；未来若经 triage 决定精化，应把判据换成实际 fixture / 写入链的行为验证，不继续叠加源码形状规则。
- `[discovered 2026-08-11 during P1-38 final internal review]` **P1-38 已完成计划文档的事实镜像收口（P2/P3，待 triage；不影响运行功能，本轮不修）** —— **P2**：`docs/plans/2026-08-11-p1-38-alert-hygiene-design.md` 仍称“现场数据库中的 674 条”，而本轮只核验并清理了当前本机开发库；如继续把这份已执行计划作为施工输入，应换成可核验的数据库身份。**P3**：实施计划仍引用旧测试名 `test_g20_test_suite_alert_writers_are_db_isolated`，且保留清理前 dry-run 应命中 674 的口径；当前正确终态是 live dry-run 命中 0、恢复备份表保留 674 行。后续整理计划归档时一并更正，不为其启动本轮修复循环。

- `[discovered 2026-08-11 during P1-27 final internal review]` **P1-27 三条 ASC 对称路径与 mock-CE MEASURE 演练的测试保护可补齐（P2，待 triage；功能已复核正确，本轮不为测试增强启动第二轮）** —— standard ASC 已直接断言筛选后的 `calibration_entries` 透传，mock CE 的 PRECHECK 也已证明模拟证书不会被 real-only 选择误伤；custom CDL、ChannelAsset 与 mock-CE MEASURE 目前由实现全集审查和相关回归间接覆盖。后续若进入 P3-18 测试精化批，可为三条 strategy 各加同一条 provenance 透传断言，并钉死 mock CE 的 MEASURE 仍消费 mock 证书、真实 CE 则优先 explicit-real。

- ~~`[discovered 2026-08-11 during P1-27 external review, Codex #322 R1]` **legacy MIMO 报告被 409 封锁后，GUI 没有可操作的重生成入口**~~ ✅ **[→ P2-26，本 PR 已收口，待合并]** —— completed legacy blocked 状态现已显示恢复可用性与不可恢复原因；安全形状可显式原子认领并复用 provenance-aware builder 重生成，Blob 409 detail 可读。缺可信来源仍输出 UNKNOWN/N/A，详情/下载 fail-closed 门未放宽。

**2026-08-06 SCPI 闭环专项 triage（本表是状态真值；下方原始条目保留发现上下文）**：

| 原发现 | triage 出口 | 理由 |
|---|---|---|
| cancel / timeout 没有独立 TX 证据 | → P1-47A | E1 传输证据直接缺口 |
| `OK` 事件缺查询文本，无法与 TX/RX 配对 | → P1-47A | 同一交换的 `exchange_id` 前置 |
| 两条绕过公共 SCPI 帮助器的活跃路径 | → P1-47A 开工审计 | 只收敛 P0-5 活跃调用；非活跃站点不扩范围 |
| 空回复与 F64 明确定义的 `not ready` 混用 | → P1-47B | 属于仪器接受/生效语义；手册未定义的空串保持 `unverified` |
| phase 只记 start/complete，不记实际生效参数 | ✅ P1-47C resolved | 已落到正式 TestExecution/API/GUI/报告，并以业务结果 AND formal evidence 判定 |
| 转台坐标偏置没有可信真值，执行器只能传 `None/False` | → ON-SITE-BLOCKED / U-9 | 不在本地猜偏置；补齐标定来源前 positioner mandatory 项保持 unknown |
| ASC/B2 模型加载尚无 confirmed 正式证据 hook | → 正式延后 backlog；使用该路径时保持 unknown | P0-5 可先用已闭环的 GCM 正式路径；ASC/B2 若要正式关闭需另立证据 recipe 与执行 hook |
| 与闭环无直接关系的其它未标记发现 | 保留 Discovered | 继续待评估，不因本轮自动变成 backlog |

- `[discovered 2026-08-07 during P1-44 external review, Codex #303 R1]` **重复抑制桶不按日志级别隔离（P2，待 triage）** —— `logging_config.py:185` 的抑制 key 不含 `record.levelno`：同一执行/仪器/logger 在一秒内先输出至少 100 条相同文本的 INFO，随后用**相同文本**输出 ERROR 时，该 ERROR 会被归进已经满额的 INFO 桶并直接抑制；最终摘要又复制首条 INFO，因此日志里**完全看不到级别升级**。突发限流因此可能吞掉真正的告警或错误。修法方向是把 `levelno` 纳入 key。按 CLAUDE.md ⑥ 不在 #303 当下修（P2、非本片验收边界内的安全问题），避免 review 黑洞。

- `[discovered 2026-08-07 during P1-44 external review, Codex #303 R1]` **关键词过滤匹配不到 traceback 续行（P2，待 triage）** —— `system_logs.py:364` 的反向扫描只对**父记录**调用谓词，随后无条件清空续行。于是关键词只出现在续行里时（父消息 `request failed`、续行 `ValueError: broken`），搜 `broken` 会同时从 `/tail` 和 `/history` 消失；导出路径同样只检查父记录，结果一致遗漏。修法方向是归组时让关键词能匹配组内任一续行，同时保留父级 level/session 语义。同上，不在 #303 当下修。

- `[discovered 2026-08-08 during 现场分支内审, F4]` **仪表租约的粒度落在最内层 primitive，一次校准作业要建拆几十上百次 socket（P2，待 triage）** —— `acquire_sa_power_via_ce_tone`（`path_loss_calibration_service.py:803`）自己取租约解决了「park 之后校准必撞 Local 门」，但三个调用方**没有一个**在外层持租约（`probe_calibration_service.py:1776` 是 elevation × azimuth 双重循环逐点调）。于是每点都真取真放：`release_to_local_control()` 清 `_visa_resource` → 下一点的 `acquire_remote_control()` 走完整 `connect()` → `_apply_session_reset()` 每次清 6 个缓存字段（含 running / pipeline / bypass）。一次 32 探头 × 2 极化的方向图扫描 = 64 次 socket 建拆 + 缓存复位。⚠ **不是加机制**：`hold()` 已经是引用计数、嵌套安全，只需在三个作业入口（`measure_probe_pattern` / QZ 校验 / path-loss 作业）各包一圈外层租约，内层那圈自动变 no-op。**本轮没做**：改动横跨三个服务的入口，超出「让现场分支能合进 main」这个目的（⑦）。

- `[discovered 2026-08-08 during 现场分支内审, F8/F9/F10/F12]` **内审四条 P3 待 triage** —— ① `InstrumentTestLeaseError` 统一映射 409，把「取不到控制权」与「用完归还失败」合并成同一个码：后者发生在整条链已跑完的 `finally` 里，而 409 的语义是「稍后重试」，GUI / 脚本按 409 重试会**重跑整条链**（`main.py:217`）。② 嵌套租约只校验 `control_f64` / `control_uxm`，`enable_monitoring` 被静默忽略（`instrument_test_lease.py:214`）—— 内层要求关监控却嵌进开监控的外层时，1 Hz 轮询会插进 CW tone 测量抢 SCPI 锁；今天无可达路径，属潜伏。③ 「None 不能当 0 算进均值」只有「别崩」那半有门，且镜像站点 `analysis.py:88` 保留同样的裸写法（今天安全只因 `measurement_simulated` 是循环不变量）。④ `optional_categories` 这个新字段没进 `loader.list_sequences()`，GUI 的诊断面板看不到它，声明与展示脱钩。

- `[resolved 2026-08-16 by P1-51]` **驱动与 fresh bootstrap 不再带「猜出来的」默认 IP** —— 14 个真实驱动统一只消费显式 `ip/controller_ip/ip_address/endpoint/visa_resource`；空配置在 ResourceManager/socket/SCPI 前进入 ERROR，并提示在仪表目录或 LabProfile 配置地址。UXM/CMW500 只原样使用合法 TCPIP VISA resource，普通 endpoint 先归一；结构化 host 与 resource host 冲突时在 I/O 前失败。DriverRegistry auto 在任一显式地址存在时选择真实驱动承载校验，避免把冲突配置静默伪装成 Mock。新数据库的七类 connection 只预置端口/协议，地址为空；既有数据库连接不自动清空，避免把无法区分的现场真实配置当旧 seed 删除。旧 F64 compatibility controller 也已取消默认地址。

- `[discovered 2026-08-07 during CAICT 现场]` ~~**单元测试会对生产默认 IP 发真 TCP，全量测试在 TUN 环境下挂死**~~ → **⑤ dropped（2026-08-07 用户当场裁决：「这是测试环境的问题，不是产品的问题」）**。事实记录保留备查，不进任何队列。原始描述： —— `conftest.py` 的 `client` fixture 触发 FastAPI lifespan → HAL 真去连驱动默认 IP（`propsim_f64.py:393` `192.168.100.21`、`uxm_base_station.py:296` `192.168.100.10`、`bootstrap/instruments.py:276` `TCPIP0::192.168.100.26::inst0::INSTR` 等）。平时这些地址不通、连接秒失败，测试照过；2026-08-07 本机 Clash TUN（网关 `198.18.0.1`）接管该网段后，连接不再快速失败而是挂住等超时 —— `lsof` 实证 `TCP 198.18.0.1:57661->192.168.100.27:sunrpc (ESTABLISHED)`，进程 CPU 0.3% 挂了 11 分 47 秒。**后果两层**：① 当天现场分支 46 文件 4246 行**零全量回归**，内审最后一道兜底落空；② **在现场机上跑 pytest 会真的把 F64 拽进 Remote**（F64 收到第一条 ATE 命令即进 Remote），测试本身变成一次未经批准的仪器操作。另：`pytest-timeout` 未安装，连"卡住就超时失败"的兜底都没有，一个挂住的测试能拖垮整轮。修法方向是 conftest 强制 mock + 装 `pytest-timeout`；它是「现场每个 commit 前跑门文件」这条纪律的前置。

- `[resolved 2026-08-16 by P1-50]` **留存清理失败告警回流重开执行文件与 fd 泄漏** —— 已在告警发出边界临时隔离 `current_execution_id`，并在 `finally` 精确还原；告警继续进入 app/console，执行文件 handler 因 `execution_id=-` 忽略该记录。真实根 logger 回流门证明收尾后目标 execution 不再活动、`_streams` 为空，且告警没有被吞掉。原始根因来自 #303 尾部未获外审覆盖的修复：`close_execution()` 删除过期文件失败时发 WARNING，而调用方仍持当前 execution 上下文，`ContextFilter` 将它注回记录并让同一 handler 重开文件。
- `[discovered 2026-08-07 during CAICT 现场]` **同一天三条平行分支从同一 base 分出且互不可见（流程，待 triage）** —— 2026-08-07 从 `main` (`2a47126`, 08:56) 分出三条互不相干的线：`codex/onsite-20260807`（日志线，PR #303，33 文件）、`add-new-features`（FS16/UXM 功能线，无 PR，49 文件 +16167）、`codex/uxm-driver-completion`（现场驱动线，未推送，46 文件 +4246）。**现场实际跑的是第三条**，因此当天现场排障用不上第一条刚做完的「执行日志隔离与限界」「审计摘要关联执行」—— 而那正是 Current Focus P1-44 的交付物，也正是当天排障最缺的东西（实测在 63 MB 日志里逐条 grep 了一晚上）。三条之间 12 个核心文件重叠（`api/instrument.py` / `hal/propsim_f64.py` / `hal/uxm_base_station.py` / `services/instrument_hal_service.py` / `services/mimo_ota/executors/measure.py` / `tests/test_rule_gates.py` 等），`git merge-tree` 实测第二条与第三条有 3 处硬冲突，最要命的一处是 `send_scpi_command` 里「manual_local 闸门」与「instrument_test_lease 租约」抢同一位置且前者对所有仪器类别泛化生效。**待 triage 的是流程问题**：现场作业开分支前是否必须先合掉/rebase 已完成的队列项，以及 WIP=1 在"多人/多 agent 同日并行"下如何表达。


- `[resolved 2026-08-18 by P2-28 / PR #352；原 discovered 2026-08-06 during P1-45 external review, Codex #295 R1]` **诊断序列完整 output / trace pointer 持久化缺口** —— `POST /api/v1/diagnostic-sequences/{key}/run` 的 live response 含完整 `steps/raw`，但 `DiagnosticContext.record_run()` 原来只把组合输出截成最多约 2048 bytes 的 `DiagnosticRun.output_excerpt`，该 endpoint 又没有传 `hal_trace_log_path`；离开 live 结果后，审计行可能既没有完整 raw，也没有可回取全量 trace 的指针。P2-28 已采用与审计行同生命周期的结构化 `sequence_evidence`，详情可重新打开完整证据，旧行只显示摘要并明确不可恢复，不依赖日志轮转/清理后可能失效的指针，也不从旧摘要猜测证据。

- `[resolved 2026-08-06 by P1-39 / PR #292；2026-08-22 复核并关闭重复 P2-36]` **「从执行历史一键看这次执行的日志」已完成** —— `HistoryTab` 每行按钮把完整 execution ID 经 `App` 一次性交给 `ReportsPage`，自动切到系统日志页签并让 `SystemLogViewer` 的首个请求直接携带精确过滤；执行标签显示用例名语境与本地执行时间，复制/过滤仍使用完整 UUID。2026-08-21 从本条旧文字再次提升的 P2-36 是重复项，未再实现第二套机制。

- `[discovered 2026-08-05 during P1-35]` **`instrument_logs` 孤儿表待 drop（P3）** —— P1-35 删掉了 `InstrumentLog` 模型与三个 schema（零引用、库里 0 行、0 写入方），**表本身还在**。内审已查证**无害**：① `alembic/` 里零命中，这张表从来不是任何迁移建的；② baseline 迁移 `40fd1c51ff40` 走 `Base.metadata.create_all`，所以新的 greenfield 库**不会再有它**；③ 后续迁移全是手写 `table_exists/column_exists` 守门式，本仓库不用 autogenerate。**唯一残留风险**：哪天有人跑 `alembic revision --autogenerate` 会白得一条 `drop_table`。真要 drop 需 migration，而两台现场机器是 brownfield 库，属另一类风险 —— 单独走一片，按 `feedback_addcolumn_migration_dialect_agnostic` 三路径（PG / SQLite-brownfield / SQLite-greenfield）验。
- `[discovered 2026-08-05 during P1-35 内审 F8]` **两个日志面板对「异常」有两个定义，主控台漏 CRITICAL（P3）** —— P1-35 在 `SystemLogViewer` 确立「异常 = WARNING/ERROR/CRITICAL」，而 `gui/src/features/Dashboard/ZoneLogsAlerts.tsx` 的 `LEVEL_FILTERS` 只有 `{INFO, WARNING, ERROR}`，且**没有任何 chip 能打开 CRITICAL** —— 不是"要多点一下"，是那个开关不存在，于是 CRITICAL 的行在主控台日志面板里**恒被客户端过滤掉**。P2-19 遗留，非 P1-35 造成（按 ⑦ 判据「不改它本片故障还在吗」→ 还在，故本片不顺手改）。**顺带**：`ZoneLogsAlerts` 现在可以用一个 `level=WARNING,ERROR,CRITICAL` 请求替掉那三十行两路 boost + 跨流去重（P1-35 的新能力开出来的化简机会）。

- `[discovered 2026-08-05 during P1-34 内审 F5]` **WebSocket 流上的日志拿不到 `request_id`（P3）** —— `BaseHTTPMiddleware` 对 `scope["type"] != "http"` 直接透传（`starlette/middleware/base.py`），`AuditMiddleware.dispatch` 根本不会被调用，所以 `/ws/monitoring` 那条流产生的日志 `session_id` 恒为 `-`。**HTTP 侧八条路径已实测全覆盖**（sync / async / BackgroundTasks / StreamingResponse / HTTPException / 未捕获异常 500 / CORS 预检 / 排除路径），只有 WS 是真空。当前已在 `audit_middleware.py` 注释里写明是已知边界。**要补的话**：在 WS 端点自己 `current_session_id.set()`（每条连接一个 id，语义是"连接"不是"请求"，得先想清楚该不该复用同一个键）。
- `[resolved 2026-08-06 by P1-45；原 discovered 2026-08-05 during P1-34 内审 F6]` **roadmap 两处 P1-31 状态快照已改成 Current Focus 指针** —— P1-31 已于 2026-08-04 收口（#277），两条 UXM KPI 记录现只保留载体归属与历史日期，当前执行片统一看顶部 Current Focus；同批已全文件扫描并清掉其它同类快照措辞。
- `[discovered 2026-08-05 during P1-34，被本片新加的门抓出]` **`EXCLUDED_PATHS` 里两条排除项指向不存在的路由（P3）** —— `app/core/audit_middleware.py` 的 `/api/v1/monitoring/metrics` 与 `/api/v1/monitoring/instrument-status` 在 OpenAPI 251 条路径里**都不存在**；`app/api/monitoring.py` 实际只有 `GET /monitoring/feeds` 和 `WS /ws/monitoring`。旧路由布局的残留，各自排除了个寂寞。**危害极低**（匹配不到任何请求 = 零噪音贡献，也零副作用），所以 P1-34 **没有顺手删** —— ⑦ 的判据「不改它，那个可观察故障还在吗」答"还在"。当前由 `tests/test_p1_34_log_timeline.py::_EXCLUDED_KNOWN_STALE` 显式豁免并配了**反向门**（哪天这两个路径真变成路由，门会红提醒摘掉豁免）。**修的时候要先定意图**：是想排除 `/monitoring/feeds`（那就改路径）还是这条排除已无意义（那就删）—— 别照着旧字符串猜。
- `[discovered 2026-08-05 during P1-34]` **日志面板的级别过滤是"精确相等"，选 INFO 会把 ERROR 一起滤掉（P3，与 P3-19 同堆）** —— `/system-logs/tail` 的 `_entry_matches` 用 `entry.level != level` 精确匹配，所以 `SystemLogViewer` 那个单选 SegmentedControl **没有任何一档**能给出"去掉 DEBUG 心跳但保留 INFO/WARN/ERROR"，操作员只能停在 `全部` 挨 DEBUG 刷屏（实测最近 400 行里 253 行是 DEBUG 心跳）。⚠️ **不要改后端把它变成"≥ 门槛"** —— `ZoneLogsAlerts`（P2-19 #258）正是靠"两个 level 流天然不相交"来做去重的，改成门槛会让那里的合并逻辑出错。**正解是照搬 P2-19 已拍板的做法**：前端多选 + 逐 level 各发一次请求合并去重（零后端契约变化）。P1-34 没做，因为该片已用「只看这一次请求」（复用后端既有的 `session_id` 精确过滤）达成"还原一次操作"的目的，级别多选属**另一件事**。

- `[discovered 2026-08-06 during P1-39 拆分后外审，已修主体，余项记此]` **跳转到日志时会发两次 `/tail`（P3，纯浪费不影响正确性）** —— 实测：修惰性初值前是 **3 个请求、其中 2 个不带 `execution_id`**（未过滤结果可能乱序盖掉已过滤的，而徽章已显示过滤）；`ReportsPage` + `SystemLogViewer` 两层都用惰性初值之后是 **2 个请求、0 个不带过滤** —— 竞态已消除（两个都过滤到同一执行，乱序也一样）。剩下那次重复大概率来自 `clearTextFilters()` 改了 `levelFilter`/`keyword` 触发的 refetch。修法候选：把「预填过滤 + 清文本过滤」合并成一次 state 更新，或给取数加去重/取消。⚠️ 别为此加请求管理机制 —— 量级只有一次多余请求。
- `[discovered 2026-08-06 during P1-45/46 立项，Codex #293 R2 P1 抓出]` **⚠️ `uxm_scpi_compatibility` 在 IRAT 方言上永远不可能成功（P1，活 bug）** —— `_CRITICAL_NAMES` 里含 `TDD_PATTERN`，而它在 `UxmLteNrIratProfile` 上**是 `None`**（P1-33 逐条 grep 手册原件确认「手册 0 命中」——TDD 在本仪器上是**六个数**不是 pattern 字符串）。`uxm_scpi_compatibility:520-533` 的 `critical_undefined` 把「在 critical 集里但 profile 上不是 str」的全收进来并令 `success = False` → **该序列在 IRAT 上每次都判失败**，而现场就是靠它给 P1-33 结论。⚠️ **同一形态已经处理过一次**：`:146-152` 因为完全相同的理由把 `MEAS_BTHROUGHPUT_DL_BLER` 移出了 critical 清单，**`TDD_PATTERN` 漏了**。修法随 **P1-46** 第 2 件交付物一起做（判定集跟 `MAC_CFG_MANDATORY` 对齐 + 排除 `MAC_CFG_NO_EQUIVALENT` 那档）。
- `[triaged 2026-08-07 during P1-47B；原 discovered 2026-08-07 during P1-41 内审 F2；→ 正式延后 backlog/P3]` **两条 UXM 诊断序列仍各自维护有界、硬编码的错误队列读取** —— `uxm_config_truth_probe.py` 最多读 100 次并硬编码 `SYST:ERR?`；`uxm_manual_spelling_probe.py` 也有自己的有界排队逻辑。两者不在正式 TestCase/`RealUxmDriver` 业务路径上，且已有明确上界，不影响 P1-47B 的同次执行证据构造；现在抽公共 helper 会扩大本片范围，也不能解决 LTE_NR_IRAT 手册适用性未知。结论：不并入 P1-47B，进入正式延后 backlog/P3；将来处理时必须复用 profile 命令并保持 error-query-self-rejection fail-closed。
- `[triaged 2026-08-07 during P1-47B；→ ON-SITE-BLOCKED / Known unknown]` **Aerotech 活跃 AeroBasic/TCP 路径没有已佐证的型号与固件查询** —— 现有厂商集成说明能证明 `MOVEABS`、`PFBK`、ACK/错误形态与偏置校准，但没有安全的身份查询；数据库/connection config 里的 `A3200` 只是声明，不能冒充实时环境。P1-47B 已让角度证据在型号或固件缺失时强制 unknown；P1-47C 只持久化这个 unknown，不补假值。P0-5 正式复验前必须从厂商手册找到并实现只读身份查询，或取得明确覆盖现场控制器的等价厂商证据，否则该 mandatory 环境门不能关闭。
- `[triaged 2026-08-07 during P1-47C；→ ON-SITE-BLOCKED / Known unknown U-9]` **转台坐标偏置尚未接入可信标定真值** —— 正式执行当前明确向证据构造器传 `coordinate_offset_deg=None`、`offset_calibrated=False`，因此即使 `MOVEABS` 与正确轴的 `PFBK` 往返完整、反馈误差看起来合格，也只能保持 formal unknown。P0-5 前必须用可追溯标定流程确认控制坐标到 DUT 物理方位的偏置并现场复验，禁止把默认 0° 当已标定。
- `[triaged 2026-08-07 during P1-47C；→ 正式延后 backlog]` **ASC/B2 模型加载没有已确认的正式证据 hook** —— P1-47C 会登记 F64 模型加载 mandatory 项，但目前只有 GCM 真路径能形成 FILE→OPC/ERR→MODEL STATE/RUN STATE 的闭环；ASC/B2 为避免额外 query 改变真实设备时序，按设计保持 missing/unknown。P0-5 正式复验应使用已确认的 GCM 路径；若业务必须以 ASC/B2 关闭，则另立片补手册 recipe、活跃执行 hook 与现场验证，不在本片猜测。
- `[discovered 2026-08-06 during P1-45/46 立项，Codex #293 R2→R3 两轮才判对]` **P1-6 现场半（真 idle-close 复现）没有载体序列（P3）** —— ⚠️ **我判错过一次**：R2 时写成「F64 侧剧本，跟 `propsim_f64_state_machine` 一起排」，而 P1-6 的正式定义（`### P1-6`）是「**FS16 / UXM / ENA** silent-reconnect 集成测试」，条目原文明写「**F64 已有 12 个集成测试**，FS16 / UXM / ENA 继承了同一模式但没有各自的集成测试」——**我指向了唯一已经覆盖了的那个驱动**。正解：载体要打在 **FS16**（`propsim_fs16_health` 可扩）/ **UXM** / **ENA**（`vna_ena_health` 可扩）三个上，且它是 C 类（要制造 idle 再看重连），不是只读普查。
- `[discovered 2026-08-06 during P1-39 内审 F7 域枚举 —— 判定为越界，本片未做]` **「待归档执行」是第 4 个拿不到 ID 的界面（P3）** —— `gui/src/features/Reports/components/PendingExecutionsList.tsx` 的两张表都只把 `record.id` / `record.execution_id` 当 React `key`，列是 用例名/时长/完成日期/来源/操作，**跟 P1-39 改动前那三处一模一样**。它就在报告页第一个页签，跟系统日志同页并列。修法**已经现成**：套用本片的 `CopyableId` + `formatExecutionTag`，零新机制。⚠️ 同族第二例：`gui/src/features/TestManagement/README.md` 的用法示例写 `<TestManagement />`，没提 P1-39 新加的 `onViewLogs` —— 而同一份 README 里已有一段专门讲「`onCreateNew` 没人传所以入口不可达」，同一个坑的第二次。
- `[discovered 2026-08-06 during P1-39 浏览器实测 —— pre-existing，判定为越界，本片未做]` **系统日志表「消息」列被挤到 83px，正文竖着排（P3）** —— 1280 视口实测各列宽：展开 32 / 时间 107 / 级别 70 / 请求 86 / 执行 86 / 模式 60 / **Logger 338** / **消息 83**。`Logger` 声明 `w={250}` 但被 `app.services.test_case_runner` 这类长 token 撑到 338，而**「消息」列没有 min-width 也不横向滚**（容器 `scrollWidth == clientWidth`），于是正文被压成一条竖带，等于读不了。**与 P1-39 无关**（该片一处列宽都没动，`git diff` 已核），但 P1-36 加「执行」列后更明显。修法候选：给消息列 `miw` + Logger 列 `truncate`/`ellipsis`，或整表加 `overflow-x: auto`（⚠ 后者要跟 sticky 表头一起验，别滚出错位）。
- `[discovered 2026-08-06 during P1-39]` **执行快照名里的时间戳是 UTC，跟界面上所有其它时间差一个时区（P3）** —— `test_case_runner.py:134` 用 `datetime.utcnow().strftime('%Y%m%d-%H%M%S')` 拼进快照用例名（`S6-验收-五步闭环 [执行 20260806-005515]`），而 P1-34 已把界面时间统一成**本地时区**。实测同一次执行：名字里 `20260806-005515`，P1-39 新增的执行标签 `20260806-085515`，完成时间列 `2026/8/6 08:55` —— **两个数字并排，看着像自相矛盾**。P1-39 的标签取本地是对的（它要跟日志时间线和墙上的钟对上），**错的是那个名字**。⚠️ 修它要小心：那是**已落库的历史行的名字**，改生成逻辑只影响新行，存量不一致仍在；要不要回填是单独决定。
- `[discovered 2026-08-05 during P1-36, Codex #286 R2 P2]` **[→ 提升 P1-42 (2026-08-06，用户拍板)]** **`app.audit` 的请求汇总行归不到 `execution_id` 名下（P3）** —— `AuditMiddleware` 是 `BaseHTTPMiddleware`，它在 `call_next` 返回**之后**才打那行 `POST /...  → 200 (45ms)`；而 Starlette 把下游 endpoint 跑在**独立的子上下文**里，endpoint 里 `current_execution_id.set(...)` 设的值**回不到** middleware。所以按 `execution_id` 过滤时，发起执行 / 取消执行这几个请求的 HTTP 方法+状态码+耗时那一行是缺的（`session_id` 不受影响 —— 它由 middleware 自己在 `call_next` **之前**设）。**实证**（别重做）：最小 app + `AuditMiddleware`，endpoint 内 set `EXEC1234` 后同一请求打两行，捕获结果 `('app.probe', 'EXEC1234', ...)` / `('app.audit', '-', ...)` —— 一行带、一行不带，前提成立。**本 PR 未修的理由**：① ⑦ 判据「不改它，P1-36 那个可观察故障还在吗」答**不在了** —— R1 修完后执行的开始/过程/结束/取消都已在链上，缺的这行是同一事实的第二份记录，且**一跳可达**（case-runner 那行同时印着 `request_id` 与 `execution_id`，GUI 的「只看这一次请求」按钮就是这一跳）；② 三种修法**全属"加机制"**（最低优先级）：换 `request.state` 传值要改每个调用点，正是 P1-36 刻意避开的；把 ContextVar 从 `str` 换成可变盒子要动 `ContextFilter` 与全部 set 点；middleware 改 pure ASGI 是重写。⚠️ 同形态还波及 `commissioning` 的相位请求与 `request_cancel` 的取消请求。真要做时，先问「这行的价值是否值一次机制改动」。

- `[discovered 2026-08-05 during 手动测试前的环境检查]` **[→ 提升 P1-41 (2026-08-06)]** **⚠️ 日志爆量：7.6 秒写 20 万行、一次事故 24 GB —— UXM 排错误队列的循环停不下来（P1 候选）** —— 实测 `api-service/logs/` 已占 **41 GB**（`app.log` 13 GB + `scpi.log` 11 GB + 30 个滚动文件），磁盘已用 76%。**爆点定位**：`app.log` 首行 `2026-08-04T23:59:59.999` → 第 20 万行 `2026-08-05T00:00:07.604`，**7.6 秒 20 万行 ≈ 26,000 行/秒**，且这 20 万行**百分之百**是同一对（各 10 万）：
  ```
  TX: SYSTem:ERRor?
  RX: -113,"Undefined header"
  ```
  语义 = 驱动在排 UXM 错误队列，仪器回「**`SYSTem:ERRor?` 这条命令我不认识**」（`-113` = Undefined header）→ 队列永远排不空 → 循环永远不终止。**两个 bug 叠在一起**：① 终止条件挂在"队列空了"上，而拿不认识的命令去问必然永远不空；② 该方言的错误查询命令形式可能就是错的（与 `[discovered 2026-08-03 …Uxm5GNRTestAppProfile]` 同源 —— 非 IRAT 方言用无前缀形式，`uxm_command_profiles.py:66` 的 `ERR = "SYSTem:ERRor?"` 是否适用于所有方言**未经手册确认**）。
  **已知的一半**：`uxm_base_station.py:3053-3058` 那处排队循环**已有上界**（`for _ in range(limit)`，docstring 写着「原来是 `while True`，遇到一直吐错误的仪器会挂死」）—— 所以要么爆量来自**别的入口**（同文件 1338 行还有一个 `while True`，未核），要么上界是这次爆完之后才加的。**动手第一步是定位那 20 万行的实际调用栈，别假设就是 3058 那处。**
  **轮转救不了**：`TimedRotatingFileHandler` 按天滚（30 个滚动文件在，机制是好的），一天之内爆多少都进同一个文件。真正的门是**同一条消息的速率上限 / 去重计数**（"same message x100000"），这正是 P1-35 留存判据的极端形态：20 万行同一句话，对分析系统/测试/AI 训练/故障排除**四不沾**。
  **排序建议**：本条比 P1-37 更该先做 —— P1-37 是给日志加内容，本条是止血。⚠️ 修的时候连**两侧**一起看：`scpi.log` 同步写了 11 GB，说明同一事实落了两份文件。
  ⚠️ **磁盘上那 41 GB 未清**（删日志不可逆，等用户拍板）。

- `[discovered 2026-08-03 during 立项 review, Codex #276 R2]` **`Uxm5GNRTestAppProfile`（非 IRAT 方言）的命令形式是独立问题 —— 出路是查手册，不是现场探** —— #275 把 KPI reader 换成新命令字段，只给 IRAT 填了 `BSE:` 形式；5G_NR_Test 方言继承基类的 `None`，那批 KPI 现在整组读不到（有 warn-once 兜着，不静默）。⚠️ **不能靠现场探**：该方言用的是**无前缀**形式，而手册给的两个变体（`BSE:MEASure:NR5G:...` / `BSE:NR5G:MEASure:...`）**都带 `BSE:`** —— 现场去试无前缀拼写就是猜，正是 #275 整片在治的病。**正解**：像 2026-08-03 查 IRAT 那样，直接查手册 / NotebookLM 问 5G_NR_Test 方言（Test Application 名 `5G_NR_Test`）下这批命令的根前缀与完整形式；查得到就本地补齐，查不到就如实标"该方言 KPI 不可用"并让 warn-once 继续响。**本地片，不需要现场**。


- `[discovered 2026-08-04 during P1-31, Codex #277 R2 P2 —— 判定为越界, 本 PR 未做]` **`uxm_kpi_readback` 的三条前置写没包 `try`，transport 抛异常会带走全部已收证据** —— `BTHRoughput:STATe ON` / `CSI:STARt` / `MEASurement:REPort ON` 直接裸调 `_w`，异常逃出 `run()` 后 API 只记一次 aborted run、**拿不到 `SequenceRunResult`**，于是 P0 的证据与恢复步骤全丢 —— 而硬件真出故障时那些证据恰恰最值钱。⑧ 的 `CLEar` 已经包了 `try` 正是为防这个（内审 F8）。⚠️ **不在 #277 做的理由**：① 既有缺口，不改它 #277 那个「错误漂到下一条命令头上」的故障照样不在；② 改它会**推翻现有门 `test_restored_even_when_an_exception_escapes` 的前提** —— 那条门正是靠 `MEASurement:REPort ON` 的异常逃出来验证 `finally` 恢复的，要一起重设计。做的时候连门一起改。

- `[discovered 2026-08-04 during P1-31, Codex #277 R2 P2 —— 判定为越界, 本 PR 未做]` **`_read_orig` / `_csi_state` 的 `.strip()` 让 `raw` 不再逐字，违反 `protocol.py:54` 的「原样存」约定** —— 该约定原文：「**原样存**, 不做归一化 / 大小写转换 / 去引号 …… 本字段的价值恰恰在于保留仪器真正吐出来的样子 (含空白与引号)」。⚠️ **不在 #277 做的理由**：既有写法（非本 PR 引入），且**高保真那站已经是对的** —— `_probe`（逐元素跟面板比对、下标错位是本序列的核心问题）的 `raw` 逐字保留且有变异 M10 守着；这两处只是 `ON`/`0`/`STOP`/`MEAS` 这种单 token，`.strip()` 掉的是 VISA 终止符，实际证据损失接近零。**做的时候连带收窄测试文件顶部那句「`raw` 逐字保留仪器回复」** —— 现状下那句是以偏概全。

- `[discovered 2026-08-03 during UXM KPI 修复, 用户明确要求记号]` **[→ 载体 = P1-31]** **⚠️ #275 的 KPI 回读改动 —— 本地零真机验证，整批必须现场核验** —— 命令形式 / 元素下标 / 单位 / 前置条件全部来自**手册与真机历史日志**，**没有一条在真机上跑过**。合并 #275 是"按手册应该对"的版本，不是"验过是对的"版本。**下次现场必须逐条对账**（走诊断序列，禁临时脚本）。⚠️ 原第 ⑩ 项「探出 5G 方言的无前缀形式」**已删**（Codex #276）——
  它与「只探手册有依据的命令、禁猜」自相矛盾（无前缀形式手册里没有，现场探只能猜拼写）；
  该方言的命令形式**查手册解决、不需要现场**，已另立 Discovered。


  | # | 要验什么 | 怎么判 |
  |---|---|---|
  | 1 | `BSE:MEASure:NR5G:BTHRoughput:DL\|UL:THRoughput:OTA:{cell}?` 真机接受且回 **6 个 double** | 元素个数 ≠ 6 → 下标全错位，`_pick` 会静默取错 |
  | 2 | 该返回值的**单位是 bps 还是 Mbps** | 手册只有**旁证**（兄弟条目 `DL OTA LTE + NR Result` 标 `Unit: bps`），本条目自身没有 `Unit` 字段。跟面板显示比：差 10⁶ 就是 bps |
  | 3 | `idx4 = average` / `idx1 = current` 对不对 | 跑一段稳定吞吐，面板平均值 vs idx4 |
  | 4 | `BLER:{cell}?` DL 回 **10 个**、UL 回 **6 个**；`idx8 = pdschBlerRatio` / `idx4 = nack-ratio` | 个数不对即下标错位 |
  | 5 | `CSI:CQI:STATistics?` 的 `result[4] = cqi_average`（idx3 是 maximum） | 面板 CQI 均值 vs idx4；**取错一位会系统性乐观** |
  | 6 | `CSI:RI:HISTogram?` 的 8 个 bin 是**码点 0..7**（rank = 码点+1） | 单层场景下应全落 bin0 → rank 报 1。若面板显示 rank 1 而我们算出 0，说明权重又反了 |
  | 7 | **RSRP/SINR 口径**（见下一条：码点 vs dBm，差 156） | 当前刻意不填结论字段，确认后才接线 |
  | 8 | 三条前置真被接受：`BTHRoughput:STATe ON` / `CSI:STARt` / `CONFig:MEASurement:REPort ON` | 不接受则所有 KPI 恒 `9.91E+37` |
  | 9 | `BTHRoughput:CLEar` 真能圈窗口（清零后重新累积） | 连读两次窗口值应不同；相同 = 没清 |

  **载体**：`uxm_kpi_readback` 诊断序列 = **P1-31**（2026-08-04 已完成；当前执行片见顶部 Current Focus）。现有 `uxm_scpi_compatibility` 已把这批命令加进 critical 清单、且未定义不再报假绿，可先用它做第一轮"通不通"普查；但**返回值的元素个数与下标语义它验不了**，那要专门的序列打印原始回复。
  ⚠️ **在核验之前，不要把 #275 产出的 KPI 数字当作可交付结果。**


- `[discovered 2026-08-03 during UXM KPI 修复, Codex #275 R2]` **UE L3 测量报告里 RSRP/RSRQ/SINR 的口径手册未说明 —— 现场必须对着面板比对一次** —— `BSE:CONFig:NR5G:<cell>:MEASurement:JSON:REPort:FETCh?` 返回的这几个值，究竟是 **3GPP RRC 上报的原始码点**（`rsrp-Result` 0..127，需 `value − 156` 换算成 dBm）还是**仪表已换算好的 dBm/dB**，手册对 JSON 与 legacy 两种 FETCh **都只给了示例**（示例里全是 `"NaN"`），没有单位、取值范围、换算公式（NotebookLM 三次明确回"手册未说明"，未做推断）。⚠️ 按 3GPP 通式自己换算 = **盲试**；原样写进名为 `rsrp_dbm` 的字段 = **假数据冒充真数据**。所以当前实现**只把原样值留进证据**（`scpi.log` 有完整响应，`measurement.log` 记 `kpi_raw_unverified`），`rsrp_dbm` / `sinr_db` 保持"未读到"、`kpi_valid` 标 false。**现场做法**：让 UE 驻留后同时看 UXM 面板上的 RSRP 读数与本查询返回值，差 156 就是码点、相等就是 dBm，确认后接线。落在 `uxm_kpi_readback` 序列里（**= P1-31**，2026-08-04 已完成；当前执行片见顶部 Current Focus）。


- `[discovered 2026-08-03 during UXM KPI 修复内审 F6]` **[→ P2-37 🟡 开发完成，待外审] UE L3 测量报告 `FETCh?` 不带 `<Integer>` 会取回全部可用报告** —— 手册：「Number of requested reports. **If not specified all the available reports are returned.**」；报告队列另有独立的 `:CLEAr`。P2-37 已让后台 connected 监控完全停止读取未展示的 UE L3 队列；正式吞吐窗口在等待前用已有且有出处的 `MEAS_UE_REPORT_CLEAR` 建立边界，清理命令缺失、传输异常或错误队列拒绝时只阻断 L3 读取，普通 KPI 仍可采集。因窗口时长有限，正式响应不再随进程寿命无界增长；原始 L3 仍只进入 `kpi_raw_unverified`，不进入工程字段、KPI 或报告判定。手册仍未说明多份报告顺序、`? 1` 选择哪份以及查询是否消费队列，因此不采用 `? 1` 猜测；RSRP/RSRQ/SINR 的单位与码点口径继续由 P1-31 的现场诊断确认。

- `[discovered 2026-08-03 during UXM KPI 修复内审 F7]` **CA/多小区下 `BTHRoughput:CLEar` 清全部小区，而吞吐量只读 PCell** —— `CLEar` 不带 cell（技术层全局），而 `MEAS_TPUT_DL_OTA` 读的是 `OTA:{cell}?` = PCell。SCell 是活跃配置（`executors/measure.py` 会 `add_secondary_cell` + `activate_secondary_cells`）→ CA 下报出的"吞吐量"只有 PCell 一份，**系统性低估交付 KPI**，并被 `analysis.py` 的 `throughput_pass` 直接消费。手册有 `...:DL:THRoughput:OTA:ALL?`，注明「return **sum of all NR cells** results」。修法 = 有 SCell 时换 `OTA:ALL?`，或至少在 `measurement.log` 标 `pcell_only=true`。

- ~~`[discovered 2026-08-03 during UXM KPI 修复内审 F9/F10]` **`kpi_valid` 只进日志不进 `to_dict()`，调用方仍分不清「测到 0」和「没测到」**~~ **[→ P1-54 ✅ PR #348]** —— `ThroughputMetrics` 四个吞吐字段已 nullable；UXM 以解析真值写 `kpi_valid`，CMW500 因响应字段顺序、单位与 sentinel 缺可核对厂商出处而只保留原始诊断证据、正式吞吐全部 fail-closed；MEASURE 仅收显式有效且有限的样本，并要求请求方位全部完成且逐方位可信，ANALYSIS/报告缺任一方位可信吞吐即 UNKNOWN/N/A；历史报告必须带新增吞吐 trust marker或经 P2-26 安全重建，旧默认零值不能直接重新发布。


- `[discovered 2026-08-03 during UXM KPI 修复]` **[→ P1-32 ✅ 已修（#279）／P1-33 本地半 ✅ 已修（#281, 2026-08-05）／余 P1-33 现场半]** ~~**⛔ `configure_mac_throughput_test()` 在现场用的 IRAT 方言上 11/11 条命令都是 `None`，第一行就抛 AttributeError**~~ **⚠️ 崩溃与静默继续那半已由 P1-32 修掉**：8 组写入改走 `_cmd()` graceful-skip、返回 `MacThroughputConfigResult`、调用方必要项缺失即 `FAILED`（不再无条件 `start_signaling`）。**下面这段描述的是修之前的状态，留作背景，别当现状读。****命令形式那半也已由 P1-33 本地半修掉**（#281, 2026-08-05：8 组命令按手册原件补齐 + 值形态转换 + 两条 apply 前置）。**仍未解决的只剩 P1-33 现场半** —— 「IRAT 到底支不支持这批命令」两个方向都没有证据，只能真机上跑一次看 `rejected` 列表（详见 P1-33 段的手册裁决）。原文如下 ——  —— `PDSCH_SCHED_ALGO` / `PDSCH_AMC_ENABLE` / `PUSCH_AMC_ENABLE` / `PDSCH_MCS` / `PDSCH_RB_ALLOC` / `TDD_PATTERN` / `TDD_PERIOD` / `HARQ_MAX_TRANS` / `HARQ_PROCESSES` / `CSIRS_PORTS` / `MEAS_TPUT_STAT_COUNT` —— `UxmLteNrIratProfile` 继承的是 `UxmTestApp` **基类**（不是 `Uxm5GNRTestAppProfile`），这 11 条全没覆盖。函数在第一条 `.format()` 上 `'NoneType' object has no attribute 'format'`，整段 `except` 捕获 → `return False`。**也就是说 3GPP MIMO OTA MAC 层吞吐量测试的全部配置（Full Buffer / AMC 关 / 固定 MCS / 全 RB / TDD 格式 / HARQ / CSI-RS 端口 / 统计窗口）在现场那台仪器上从来没有生效过。** 仓库已有 `RealUxmDriver._cmd()` graceful-skip helper 专治这个形态（见 `tests/test_uxm_driver_profile.py` 的 docstring），正解是全部换成它 —— 但**必须同时解决"跳过全部还报 True 就是假成功"**：跳过多少、跳了哪些要显式返回给调用方，否则比现在的 fail-loud 更糟。⚠️ **优先级高**：这是测试配置层的整体失效，比 KPI 读错更靠前 —— KPI 修好了，但测的是没配置过的链路。本次 KPI 片刻意不碰它（范围纪律），只把 KPI 前置序列挪到第 0 步、排在崩点之前，否则 KPI 修复在真正用的那个方言上是死的。

- `[discovered 2026-08-03 during UXM KPI 修复]` **现场 2026-05-27 已经查明的结论，两个多月没喂回驱动** —— `docs/site-debug/2026-05-27-morning-log.md` §9.2/§9.3 白纸黑字记着：`TSTatistics:STARt` **-113 不支持**；`UEReport:* / UL 吞吐` **-113 本 App 不支持**；`BLER:STATistical:ALL?` 停在 `IDLE,UNKN,0,0`「统计未被 enable」；`CSI:CQI:STATistics?` 返回 `7.92E+04,0,NaN...`「**字段义待查手册**」；backlog 明写「**需查手册找 IRAT 下重置/enable 统计的正确命令**」。这些正是 2026-08-03 这次查手册得到的答案 —— **情报早就有了，缺的是把它落回代码的那一步**。§9.5 还解释了为什么没人发现：未定义**查询**→客户端超时、未定义**写**→`resp=None/err=None` **静默像成功**。**该建立的机制**：现场笔记里的「命令不支持 / 字段义待查」条目要有出口，能落进 `uxm_command_profiles.py` 的注释或 backlog，而不是停在 site-debug 文档里。

- `[discovered 2026-08-03 during UXM KPI 修复]` **测试与生产共用 `api-service/logs/`，跑测试会静默删掉历史日志归档** —— pytest 进程启动时 `setup_logging()` 用默认 `log_dir`（实证：pytest 输出里 `Logging initialized: app=./logs/app.log`），于是每个 pytest 进程都在生产日志目录上建 `TimedRotatingFileHandler`；滚动时按 `backupCount` 剪枝。**实测**：本次会话为跑变异启动了 45+ 次 pytest，`logs/` 从 **253 个文件 / 3.5 GB** 掉到 **24 个 / 727 MB**，每个日志族只剩 3 个（当前 + 08-01 + 08-02），**6 月与 7 月的仪器往返归档全部消失**（含本次分析引用的那批 real 模式 scpi.log）。仓库里没有任何清理脚本，是 handler 自己剪的。**后果**：现场调试的历史证据会被本地跑测试悄悄抹掉 —— 跟 P1-30 治的是同一件事（日志要撑得起复现），但方向相反。修法 = 测试用独立 `log_dir`（conftest 里给 tmp 目录）。⚠️ 本条**由我这轮亲手造成**，如实记录。


- `[discovered 2026-08-03 during P1-26, Codex #271 P1]` **跨频段改频后 `CC[0].band` 与新频不符 —— 但 GUI 不该自己删 band** —— P1-26 让频率框同步 `CC[0].frequency_hz`；操作员若跨频段改频，`CC[0].band` 会留成旧值（`uxm_base_station.py` 只在 `"band" not in config` 时才按频率推断，显式 band 压过推断）。本片一度改成「改频顺带删 band」让驱动重推，**被 Codex P1 否掉并撤回**：`FREQ_TO_BAND_MAP` 只有 7 个区间且**未命中硬回落 `("N78","TDD")`**，而这张表 per-lab 可被 `InstrumentCategory.config` 覆盖 —— **前端没有资格判断「推断能不能成功」**。实例：N3 载波（下行 1805–1880；表里那条 1710–1785 是 N3 **上行**）改个频率 → 删 band → 回落 N78/TDD → **频段与双工一起错且静默**；保留 band 时跨频段改频得到「旧 band + 新 ARFCN」，由仪器拒绝 —— **响亮好过静默**，代价不对称。正解 = 后端在 validator 层校 `band ↔ frequency`（表在后端、可被 lab 覆盖，判断也该在那里），或表单暴露 band 选择让操作员显式改。⚠️ **不要把 `FREQ_TO_BAND_MAP` 复制进 GUI** —— 那是又一个会漂的镜像站点。

- `[discovered 2026-08-03 during P1-26 内审 F4]` **[→ P1-55，PR #349 ✅] 顶层 `frequency_hz` 与 `component_carriers[0]` 分叉时执行侧零告警** —— P1-55 已把 schema/service 设为共同写入门：显式冲突在提交前 422，缺失兼容镜像从 PCell 回填；MIMO factory、PRECHECK、REFERENCE、MEASURE 的工作点统一经 `primary_carrier` 消费，历史冲突也会在执行加载时 fail-loud；PCell 省略 SCS 时也会用其模型默认值参与冲突检查，不再静默覆盖顶层显式值。
- `[discovered 2026-08-03 during P1-26 内审 F5]` **[→ P1-55，PR #349 ✅] `MIMOOTAConfigForm` 显示端读顶层，与执行/列表（CC[0]）不同源** —— P1-55 已提取共享 GUI helper：三个控件从 PCell 显示，编辑同步兼容镜像与 PCell、保留全部 SCell；服务端继续作为最终冲突门。
- `[discovered 2026-08-03 during P1-26 内审 F6]` **P1-26 的三个同步站点无会红的门** —— 频率/带宽/SCS 三个 `onChange` 全靠人肉挂 `updateCarrierField`，把其中一行改回 `update(` → `npm run build` 绿、后端全量绿、**无人发现**。GUI 无单测基建（无 vitest/jest、`src` 下零 `*.test.*`），但**Python 侧已有扫这个文件的先例**：`api-service/tests/test_rule_gates.py` 的 G5/G7 就在读 `gui/src/**.tsx`，`tests/test_cdl_model_parser.py` 把本表单的 `CDL_OPTIONS` 钉住 —— 所以**不必引入新依赖**。修法 = 不变量档断言"频率/带宽/SCS 三个 onChange 站点必须走 `updateCarrierField`"，并配"改回 `update(` 会红"的变异实跑。归 P3-18（门/测试精化批）。

- `[discovered 2026-08-03 用户提出]` **[→ 提升 P1-30，SCPI 往返部分已 ✅ 完成；其余仍 open]** **日志能力复查 —— 现在的 log 大量是"示意式"的，撑不起调试复现** —— 用户原话：「从 log 层面能够复现，或者说给测试调试人员提供你自己在调试时的线索；而现在 log 中大量的内容是示意式的（**并不清楚是不是事实，也不清楚是不是完整，还有可能有些内容没有打印到 log**）」。

  **要治的三个病（用户的三分法，逐条给已查证的实例）**：
  1. **不知是不是事实** —— log 写的是"意图/描述"而非"实际发生了什么 + 实际值"。`_log_scpi_write()`（`app/hal/base.py`）只记 `TX: {cmd}`，**没有配对的"这条写成功了吗 / 耗时多少 / 仪器错误队列干净吗"**；读者看到 TX 只能推断"程序打算发这条"，推断不出"仪器收到并接受了"。同类形态见 memory `feedback_effective_end_not_nominal`（标称端 vs 生效端）。
  2. **不知是不是完整** —— `_log_scpi_response()` 硬截断 `response.strip()[:200]` 且**不加任何截断标记**。200 字符以内和被砍掉一半在 log 里长得一模一样，读者无从判断。`SYST:INFO?` / 多通道回读这类长响应正是最需要看全的。
  3. **有内容根本没打** —— 需要逐条排查哪些关键分支静默（异常被吞、early return、fallback 走了没记）。

  **体量已经在淹没线索**（同一目录实测）：`app.log` **31 MB**、`db.log` 21 MB、`measurement.log` 9 MB、`audit.log` 4.7 MB，而真正的仪器往返 `scpi.log` **当日文件**只有 307 KB。信噪比倒挂。
  （⚠️ 2026-08-03 P1-30 复核补正：307 KB 是**当日单文件**；31 个轮转文件**合计 179 MB**，
  别把这两个数当同一口径比 —— 上面那几个 MB 数也都是单文件。）

  **今晚的反面实证**：排查 `dev:safe:all` 启动失败时，真正定位靠的是 **Docker 自己的** `com.docker.backend.log`（"monitor exited: signal: killed" + 时间戳对齐），项目 log 零线索；而本轮所有关键验证（`lsof` 命中集、IPv4/IPv6 双栈 bind 冲突、`component_carriers` 漂移）**都无法从 log 复现**，全靠临时 curl / python 探针 —— 这些正是"调试人员需要而 log 给不出"的东西。

  **正面标杆（照它的样子改）**：GUI 实时日志面板打出的 `GET /api/v1/dashboard/alerts/summary → 422`，并在紧邻行给出 `File "api-service/app/api/alert.py", line 102, in get_alert` + 完整校验错误体 —— **可定位、带事实、能独立复现**。P1-29 那个缺陷就是这样被抓到的。

  **复查范围建议**：① SCPI 层 TX/RX 配对 + 耗时 + 截断显式标记 ② 执行相位每步的输入参数与实际生效值（不是"开始/完成"）③ 静默分支普查 ④ 分级与体量治理（跟 P3-19 的 app.log 噪声治理合并考虑，但那条只管噪声、本条管**证据能力**）。**建议提升为独立片**，工作量明显超 30 分钟。

  **2026-08-03 处置（用户"把日志提上来先完成"）**：① 已由 **P1-30 ✅ 完成**（截断显式化 + OK/ERR 配对 + 耗时 + `instrument_id` 收窄）。②③④ **未做，仍 open** —— 见紧随其后的三条子项。

- `[discovered 2026-08-03 during P1-30 内审 F4]` **取消 / `wait_for` 超时路径在 scpi.log 里零证据** —— `app/hal/base.py` 四处用的是 `except Exception`，而 `CancelledError` 在 Python 3.8+ **继承 `BaseException`**，抓不到。内审实跑探针：`asyncio.wait_for(driver._query("SLOW?"), 0.05)` 超时 → scpi 记录只有 `[('TX','TX: SLOW?')]`，**无 ERR**；`task.cancel()` 同样只有 TX。后果：P1-30 之后「被上层取消」与「coroutine 从未被 await」**仍是同一种签名**，分不开 —— 而现场超时恰恰是最常见的那一类。修法是**加机制**（`except BaseException: log; raise` —— 裸 `raise`，控制流零变化，取消展开期不 await，代价仅多一行日志），因「审查一轮里想加机制 = 停下来报告」（⓪⑤）**P1-30 只改了文档断言、机制没做**。代价不对称偏向补记：漏记 = 证据缺口延续，补记 = 一行。**小片，可与下一条同批。**

- `[discovered 2026-08-03 during P1-30 内审 F3]` **`OK` 行没有 `query` 字段，配对只能靠 msg 文本** —— `TX` / `OK` 两类记录都不带 `query`（`RX` / `ERR` 带）。而 TX 记在 `_scpi_lock` **之外**，并发与嵌套下 TX 与结果行**不相邻**（F64 超时排水时每条 `SYST:ERR?` 上界 64 次，各产生一对 TX/RX，才写外层 ERR）—— 所以"按行序配对"是错的读法，"按 `query` 配对"又对 TX/OK 不可用。给 `OK` 与 `TX` 补 `query` 字段属**加机制**，P1-30 未做（文档已改成"按 query 配对 + 说明何时不相邻"）。**小片。**

- `[discovered 2026-08-03 during P1-30 内审域枚举]` **两条 SCPI 日志旁路不经 base 模板，拿不到 P1-30 的任何改进** —— ① `app/hal/aerotech_positioner.py` 两处**自己直写 `_scpi_logger`**（不走 `_do_*`，因此无 OK/ERR/`resp_len`/`duration_ms`/截断标记）；② `app/api/instrument.py` 的 SCPI 控制台族 12 处，`instrument_id` 填的是 `category_key`、`direction` 用的是另一套 `CONNECT/WRITE/READ/ERROR` 值。P1-30 **刻意不碰**（aerotech 根本不用 `_do_*`，硬套模板是改驱动而非改日志），但 `GEMINI.md` 的四类记录表已补上这两条例外说明。要统一得逐条判「该不该走模板」。**中等，独立片。**

- `[discovered 2026-08-03 during P1-30 内审域枚举]` **`/system-logs/tail|search` 没有 `instrument_id` 过滤参数** —— P1-30 让 `instrument_id` 从恒 `-` 变成真值，但 `app/api/system_logs.py` 的过滤参数只有 `level` / `keyword` / `session_id` / `hal_mode`，GUI `SystemLogViewer.tsx` 也只在详情展开里显示它。所以现在是"**能看见、不能筛**" —— 设计稿写的收益"调试人员没法按 instrument_id 过滤"只兑现了一半。加过滤参数是**新能力**、不在 P1-30 那句话的字面里。**小片。**

- `[discovered 2026-08-03 during P1-30]` **`.env.example` 完全没有 log 段** —— `LOG_DIR` / `LOG_RETENTION_DAYS` / `LOG_SCPI_ENABLED` / `LOG_DB_ENABLED` 四个既有 Settings 项在 `.env.example` 里**一个都没有**（P1-30 新加的 `LOG_SCPI_RESP_MAX` 同理）。P1-30 判为**越界不做** —— 只补自己那一个反而更不一致，而这是先于本片存在的缺口，不改它「看不出往返发生了什么」照样修好了。要补就四个（五个）一起补。**琐碎，可 chore。**

- `[discovered 2026-08-03 during P1-30]` **165 处 `except` 吞掉异常且不记日志不重抛（③ 静默分支普查）** —— ⚠️ **这个数没有唯一值，别引用具体数字去定范围** —— 口径稍变结果就变：全块扫描得 **162 / 43**，12 行窗口得 **165 / 51**，10 行窗口得 **185 / 42**（内审 F11 独立复算得 175 / 38）。量级是 **160–185 处**，其中整块只有 `pass` 的 **40–50 处**。真要动这片，先把口径钉死成一条能跑的命令：

  ```bash
  cd api-service && python3 -c "import re,pathlib;n=p_=0\nfor p in sorted(pathlib.Path('app').rglob('*.py')):\n  src=p.read_text(encoding='utf-8',errors='replace').split(chr(10))\n  for i,l in enumerate(src):\n    m=re.match(r'^(\\s*)except\\b.*:\\s*(\\S.*)?$',l)\n    if not m: continue\n    inline=(m.group(2) or '').strip()\n    if inline:\n      if inline=='pass': n+=1;p_+=1\n      continue\n    ind=len(m.group(1));body=[]\n    for j in range(i+1,len(src)):\n      s=src[j]\n      if not s.strip(): continue\n      if len(s)-len(s.lstrip())<=ind: break\n      body.append(s)\n    if not re.search(r'logger|log\\.|_log|raise|logging',chr(10).join(body)):\n      n+=1\n      if [b.strip() for b in body]==['pass']: p_+=1\nprint(n,p_)"
  ```

  分布集中在 `app/hal/*`（`rs_fsw.py` / `aerotech_positioner.py` / `ets_positioner.py` 等驱动）。分布集中在 `app/hal/*`（`rs_fsw.py` / `aerotech_positioner.py` / `ets_positioner.py` 等驱动）。**P1-30 刻意不碰** —— 每一处都要单独判"该记日志、该重抛、还是这个 fallback 本来就对"，是逐处的语义判断而非机械改写，塞进日志片必然超范围。**建议独立片**，可能还要拆成"驱动层"与"服务层"两批。

- `[discovered 2026-08-03 during P1-30]` **驱动层把"空回复"和"not ready"合并成同一个 `None` 且不进 `query_errors`** —— `api-service/app/hal/propsim_f64.py` 的 `get_metrics()`：`if not raw_l or "not ready" in raw_l: input_powers[inp] = None`，两种**语义可能完全不同**的情况被折叠成同一个空值，且 `query_errors` 只在**抛异常**时才追加 —— 所以这两种情况在日志与 API 响应里都**零痕迹**。实测：real 模式 RX 里空回复 **60,565 条（占 35.4%）**，TOP 全是 `INP:MEAS:RES:GET? <n>` / `OUTP:MEAS:RES:GET? <n>`（各约 1 万条）。P1-30 让**日志侧**可辨识了（RX 行有 `resp_len:0` + `duration_ms`，与"有去无回"从此不同形），但**驱动侧的语义判定没做** —— "F64 回空串"和"回 not ready"到底是不是一回事，**属于仪器语义，必须先查 NotebookLM（PROPSIM 资料 `982222b7`）**，不是日志片该裁决的。**独立片**。

- `[discovered 2026-08-03 during P1-30]` **执行相位每步只记"开始/完成"，不记输入参数与实际生效值（② 未做）** —— 用户三分法里的"不知是不是事实"在**执行层**的形态：日志能告诉你"配置相位开始了/完成了"，但告诉不了你**这一步拿到的是什么参数、实际写进仪器的是什么值、回读是多少**。P1-30 只收了 SCPI 往返这一层（现在能看到每条命令与响应），但"这一步为什么发这些命令"仍缺。与 P1-26 的分叉问题同源（顶层 vs `CC[0]` 分叉时日志同样看不出用了哪个）。**独立片**，需先定"每步该记哪些字段"的清单。

- `[discovered 2026-08-02 during P1-25 全量审计]` **[→ 提升 P1-29 (2026-08-03)]** **`/api/v1/dashboard/alerts/summary` 被 `/alerts/{alert_id}` 抢先匹配 → 该端点不可达 (恒 422)** —— `api-service/app/api/alert.py` 里 `@router.get("/alerts/{alert_id}")` 声明在 `@router.get("/alerts/summary")` **之前**，FastAPI 按声明顺序匹配，`summary` 被当成 `alert_id` 解析 → `uuid_parsing` 422。**两份独立实证**：① curl 直打返回 `{"detail":[{"type":"uuid_parsing","loc":["path","alert_id"],"input":"summary"}]}`；② GUI 实时日志面板每几秒刷一条 `GET /api/v1/dashboard/alerts/summary → 422`，栈里明写 `alert.py line 102, in get_alert`。修法 = 把字面量路由挪到参数化路由**之前**（FastAPI 惯例），并配一条"字面量段不得被同级 path 参数遮蔽"的门。前端 `DashboardAlertSummary` 类型没错，是端点从来没通过。
- ~~`[discovered 2026-08-02 during P1-25 全量审计]` **[→ 提升 P3-19 (2026-08-03)]** **四个手写 *Response 形态错，但对应 fetch 函数零消费**~~ ✅ **P3-19 mock-only 子片已收口** —— P3-18 已删七条零消费 live fetch；本片继续删除 `/dashboard`、旧 `/tests/*`、REST `/monitoring/feeds` 与活动告警列表的零消费 mock handler，以及对应 `DashboardResponse` / `Test*Response` / `Recent*` / `ReportTemplatesResponse` 类型和数据库方法。`/reports/templates` 仍由活动报告模板页消费，因此保留 handler，并改为复用 `TemplateListResponse` 的 `{templates,total,page,page_size}` 权威契约。仍被 mock WebSocket 消费的监控帧保留为 `MockMonitoringFeedsResponse`；localStorage 演示用例嵌套类型改名 `MockTestCase` / `MockTestCaseDetail`，不再冒充 live TestCase 契约。
- `[discovered 2026-08-02 during P1-25 内审 F5]` **[→ 提升 P3-18 (2026-08-03)]** ~~**手写类型审计的尺子只看一层，"12 组 OK"不可信**~~ ✅ **已收口（P3-18 手写类型子片）** —— P1-25 只做“手写类型顶层键 ⊆ live 响应顶层键”，所以 `/monitoring/feeds` 顶层 `feeds` 对上就假绿，实际元素却是 `{name,value:number,unit,timestamp}`，手写为 `{label,value:string,trend?,id?}`。本片改用 live `app.openapi()` 临时生成 TypeScript 真值，再按响应 `live → manual`、请求 `manual → live` 做递归 assignability，覆盖嵌套、值类型、optional/null、数组与请求体；临时生成物不进仓。`fetchMonitoringFeeds` 与只写不读 state 已删除，剩余 mock 演示帧改名 `MockMonitoringFeedsResponse`。
- `[discovered 2026-08-11 during P3-18 手写类型递归审计]` **当前仍被 live client 消费的 18 组手写契约中，9 组方向安全、9 组仍与 live schema 不可赋值** —— 安全：Probe create/update 请求、AlertSummary、Instrument update 请求、Chamber presets/from-preset/update、required-calibrations、link-budget。差异：`ProbesResponse`（列表/批量外层与 nested Probe requiredness）、`HALReadinessResponse`（有默认值的 `subnets` 在 live schema 可选、手写必填）、`TestExecutionListResponse`、`SystemLogTailResponse`（live 默认/可空字段在生成类型可选）、`InstrumentsResponse`/`InstrumentCategory`（`selectedModelId`/connection/default 字段 optional/null 语义）、`ChamberListResponse`/`ChamberConfiguration`（默认字段 optional + live 新增 `probe_distribution`）、`CreateChamberPayload`。当前运行端多由 Pydantic 默认值补齐，未复现界面崩溃，故不在 P3 审计片批量改业务；后续按消费方逐组确认“真可空”还是“schema 默认导致生成可选”，再走换源/收窄，不能把 9 组一次性 `?` 化。
- `[discovered 2026-08-11 from Codex review #330 R1, P3]` **P3-18 roadmap 写了“52 passed / GUI production build 通过”，但提交内没有可复跑的递归审计脚本或终端证据附件** —— 外审未质疑运行功能，只指出长期文档中的验证声明缺少命令/输出留痕；按 AGENTS 第 0 条这是测试/证据 P3，不阻塞 #330，且不为它启动第二轮修复。后续统一建设验证证据附件/CI artifact 时评估；不要为单个已合 PR 把临时 live OpenAPI 生成物重新塞进仓库。
- `[discovered 2026-08-02 during P1-25 内审 F2]` **前端若要判"真驱动还是 mock"，权威源是 `is_mock_driver()` 不是名字前缀** —— `/instruments/hal/readiness` 每行的 `status` 对 mock 驱动同样是 `ok`（实测 5/5 全 ok），能区分的只有自由文本 `detail`（实际驱动类名）。而后端权威判据是 `app/services/instrument_hal_service.py` 的 `is_mock_driver()` → `isinstance(driver, _MOCK_DRIVER_CLASSES)`（**类 allowlist**）；`api/instrument.py` 里那个 `type(driver).__name__.startswith("Mock")` 是**副本不是真值源**。前端按 `detail` 前缀嗅探在 `detail` 缺省/空串/类改名时会**静默倒向 real**（代价高的那侧），跟 #268 的 `is_docker_pid` denylist 同一形态。真要在前端区分，正解 = 后端在 readiness 行上显式暴露 `is_mock: bool`（由 `is_mock_driver()` 产出），前端换源；在此之前**不要**用名字前缀猜。
- `[discovered 2026-08-02 during P1-25]` **"操作员手选真/模拟执行"开关从未接线** —— `handleExecutionPreferenceChange` 塞进了 payload（`onExecutionModeChange`），但 `<Monitoring/>` 的 props 里**根本没接**，且 `preferMockExecution` 初值 `true` → `executionMode` 恒 `'mock'`，`hardwareOnline` 取什么值都观察不到（P1-25 实证：对它做变异连红都红不了）。**P1-25 后的现状（接手前先读这句）**：整条死机器（`hardwareOnline` / `preferMockExecution` / 强制回落 useEffect / `handleExecutionPreferenceChange`）已按"去掉>换源"删除，`executionMode` 现在是**字面常量 `'mock'`**（`gui/src/App.tsx`），行为与删除前逐位一致 —— 演示回放那两个徽章恒显示「模拟执行」。

⚠️ **别把它接到 `/instruments/hal/readiness` 上判"真仪表 vs mock"** —— P1-25 试过并被内审 F1 否掉、已撤回：这两个徽章挂在**演示回放播放器**上（同卡片副标题「演示回放 —— 真实测试请到「测试管理 → 测试用例库」执行用例」，数据源 `/tests/demo-run` 实测 404 且 query `enabled:false`），按 HAL 真假去判，现场全真部署会把**演示脚本**标成绿色「真实执行」，比恒 `'mock'` 更糟。要展示"系统当前跑真仪表还是 mock"，驾驶舱 `ZoneReadiness` 已经在做。

要恢复手选能力是**独立功能**：得先把开关控件真正接到 `<Monitoring/>`（当前 props 里没有这个口），再决定"硬件不在线时禁止选 real"的策略，以及这个徽章到底该描述"演示回放模式"还是"全系统执行模式"—— 措辞和位置一起定。

- `[discovered 2026-08-02 during dev:safe:all 启动失败排查]` **[✅ 已修，本片]** **`safe-start.sh` / `cleanup-ports.sh` 的端口清理会把 Docker 引擎自己 `kill -9`** —— macOS 上容器发布端口在 host 一侧的监听者是 `com.docker.backend`（引擎本体），不是容器；`meta3d-api` 容器（compose 默认自启）占住 8000 → 脚本杀 8000 → 引擎当场死（`com.docker.backend.log` "monitor exited: signal: killed"）→ 下一步 `db-up.sh` 报 "Cannot connect to the Docker daemon"，而那时端口上已经没人了，**现象跟端口看起来毫无关系**。修法：守门判据下沉 `scripts/lib/port-guard.sh`（两脚本同源）+ compose 的 `api` 挪进 `full` profile 拆掉 8000 争抢。顺带修掉两个 pre-existing 过杀：取数没限 `-iTCP -sTCP:LISTEN` 会把**连到**该端口的客户端（实测：开着 GUI 的 Chrome tab）和同号 UDP 进程一起 `kill -9`；端口↔服务标签 6 处全把 8000/8001 标反了。
- ~~`[discovered 2026-08-02 during 上条内审 F4]` **[→ 提升 P3-19 (2026-08-03)]** **`is_docker_pid` 是 denylist，默认动作是"杀"，只覆盖 macOS/Linux 三种形态**~~ ✅ **P3-19 allowlist 子片已收口** —— 共享判据改为 `is_project_dev_pid()`：进程类型须命中 `python*` / `node` / `uvicorn` / `vite`，且由 `lsof` 取得的 cwd 必须位于当前仓库；同名其他项目、Docker、ssh、未知 helper、非法 PID、`ps`/cwd 取证失败全部受保护。`safe-start.sh` 与 `cleanup-ports.sh` 的初扫、真正 kill、复验与最终提示均改用同一正向 allowlist，未识别进程只会让端口保持占用并 fail-closed，不再静默落回 kill；操作文档中的直接 `lsof | xargs kill`/通用 `sudo kill` 旁路一并删除。

- `[discovered 2026-08-01 during P1-23, Codex #257]` **[→ 提升 P1-24 (2026-08-01)]** **写 `propsim_f64_p08_gate` 诊断序列（P0-8a 唯一合法载体，已列协议 §2 出发前硬门槛）** —— 现有 `propsim_f64_state_machine`（前提 .smu 已载、只做 GO/STATIC/GOS）与 `propsim_f64_health`（只读探测、`get_metrics` 恒判成功）都覆盖不了 P0-8a。序列要求：①手册有据 + 生产驱动在用的命令（涉 F64 SCPI，动手前查 NotebookLM PROPSIM notebook）②**前置激活 UXM 满 RB DL**（CE↔BS 协调，无信号 `INP:LEV:MEAS?` 返 -300）③每步后读错误队列 ④电平按合法范围真判定（不是恒成功）⑤**含 bypass 态电平窗口复验**（架构文档 P0-8 硬约束）⑥**含输入参考 AUTOSET 闭环**（`INP:LEV:AUTOSET` 设 avg+crest → 读回 clipping/cut-off 迭代收敛，只读判范围会假绿，Codex #257 R3）⑦mock 跑通列入出发前门槛。代码活，独立小片。⚠️ 本行是第二次登记 —— 前两次 python replace 因 #255 提升标记改变锚文本**静默未命中**（我未 assert 命中数，#256/#257 的 PR body 里"已留痕"陈述当时为假，本次补欠并如实更正）。⚠ 要求②的"返 -300"后经手册查证为哨兵语义不实（-300 是队列里的设备错误码非查询返回值，P1-24 落地时纠错，见正式条目）。
- ~~`[discovered 2026-08-01 during P1-24 内审 F4]` **[→ P3-18；2026-08-11 本地完成]** **p08 门序列零残留站点缺逐站行为保护**~~ —— 动手前按当前实现重新枚举：不自动续跑固件的成功执行路径实际有 **10 个**（9 个主流程窗口 + 共同收尾；旧条粗记 8 个），另有 1 个中止专用站点已由 `test_abort_archives_queue_before_restore` 独立保护；现已用同一条 fake 未认领错误参数化注入全部 10 站，逐站断言原样归档、fail-closed、队列排空。临时删“加载与读态后”站点的变异实跑得到 1 failed / 其余 9 passed，证明任一站点回退不再假绿。
- ~~`[discovered 2026-08-01 during P1-24, Codex #260 R2]` **[→ P3-18；2026-08-11 已收口]** **带动作的诊断序列整体无串行化（run endpoint 层）**~~ —— 回查当前 14 条序列（12 条 `safe_during_test=False`、2 条只读 safe）及 F64 手工入口后确认，此缺口由后来的两片共同修复：P1-46 / PR #296 让破坏性序列在 run endpoint 整段持 exclusion token，第二条破坏性序列与正式 TestCase 双向 409；PR #304 让 sequence body 与 F64 `scpi-command`/`scpi-probe`/`.smu`/GO/增益/输入参考/峰均比等入口共用全局 `InstrumentTestLease`，因此只能整段排队而不能逐原子交错。P3-18 补跨入口并发回归；临时绕过共享租约时 F64 GO 会在序列退出前进入驱动，定点变异 1 failed，恢复后通过。不重复实现第二套锁。
- `[discovered 2026-08-01 during P2-21 内审]` **[→ 提升 P3-18 (2026-08-02)]** **PDF 渲染管道其余自由文本入口无 XML 转义**（pre-existing，非 P2-21 引入）—— ①封面 `Paragraph(title)` 含 case_name，`<字母` 命名会炸整份报告；②共享步骤区渲染器 `_generate_step_details_section` 的 `val_str` 侧统一转义能让 VRT `step_configs` 管线同受益（P2-21 只修了 report.py 组装侧自己的面）。修法 = 渲染器入口统一 `xml.sax.saxutils.escape`，共享文件独立小片。
- `[discovered 2026-08-01 during P3-14, Codex #262 R1]` **[→ 提升 P1-26 (2026-08-02)]** **GUI 改频只写顶层 frequency_hz，带 component_carriers 的持久化用例执行仍按 CC[0] 旧频率跑**（pre-existing，非 P3-14 引入）—— factory `model_dump` 落库自带 CC，而 `MIMOOTAConfiguration` 的 validator 在 CC 非空时忽略顶层频率（measure Phase 2g 权威 = CC[0]）；GUI `MIMOOTAConfigForm` 不写 CC → 顶层与 CC[0] 漂移时**执行侧**错频（P2-11 一致性门只兜"CC[0] vs SCD 不符"的形态，兜不住"用户以为改了新频、CC[0] 旧频恰与 SCD 一致"）。P3-14 已让**显示**与执行同源（CC[0] 优先），执行侧正修 = GUI 写侧同步 CC[0] 或 PATCH 时 drop CC 重构造，独立小片。
- ~~`[discovered 2026-08-01 during P3-14, Codex #262 R2]` **[→ P2-23；2026-08-11 本地完成]** **会话创建的资产预检只查存在不查 `is_active`**~~ —— 创建入口、显式 MEASURE resolver 以及 `cdl_profile_id`/`scd_id` 两条迁移兼容入口已同时改为只放行 `is_active is True`；软删资产保留历史只读追溯，但不能再创建或执行新的测量。
- `[discovered 2026-08-02 during P3-17 内审 F2]` **[→ 提升 P1-25 (2026-08-02)]** **GUI 主控台"系统状态"面板对 live 后端恒空态** —— `gui/src/App.tsx:482` 读 `dashboardData?.systemStatus`（camelCase，`gui/src/types/api.ts` 手写三键），而 live `/api/v1/dashboard` 返回 snake 四键（summary/live_metrics/active_alerts/recent_tests）→ 恒 undefined 走空态分支。P3-17 修了 yaml 契约（判定端），生效端副本在手写 api.ts；修法 = App.tsx/api.ts 换 live 键形态，顺带同一把尺子过 api.ts 其余手写镜像类型 + 清理死导出 `InstrumentCategoryResponse`（service.ts 早已用平铺）。独立小片。⚠ 按行号引用会漂 — 动手时按 `systemStatus` 检索定位。
- ~~`[discovered 2026-08-02 during P3-17, Codex #265 R2]` **[→ P3-18；2026-08-11 本地完成]** **G11 三个覆盖面精化**~~ —— 参数 location、curl 动词与响应 schema 类型三处已统一进入 G11 生效判据，并由合成变异与 live 完整门共同保护。
- `[discovered 2026-08-01 during P1-22 内审 F3，本行补欠登记]` **[→ 提升 P2-21 (2026-08-01)]** **precheck/reference/measure 的 P1-12 可信化标志渲染不可达 — 报告对兜底数据沉默（P3）** —— `executors/report.py` step_results 里 `quiet_zone_verified` / `trp_verified` / `path_loss_verified` 是顶层键，渲染器只读 `name`/`step_name` 与 `parameters` → PDF 步骤区零显示，P1-12"标注 未验证(兜底值)"意图从未生效。修法同 P1-22 的 analysis 站点（标志挪 `parameters` 下）。顺带同域：`pdf_certificate.py`（校准证书）无 CJK 字体，证书中文同样豆腐块。

- `[discovered 2026-08-01 during ARCH-1 S6 总验, 内审定案]` **[→ 提升 P1-22 (2026-08-01)]** **自动执行报告恒报 failed/0.0% — REPORT 相位读一个从没人写的键（P2）** —— `mimo_ota/executors/report.py` 的 `overall_pass = bool(analysis.get("overall_pass", False))`：analysis 执行器写的是 `verdict`（canonical 字段是 `validation_pass`），全仓**无人写 `overall_pass` 键**（`pass_criteria_summary` 同样无人写）→ 恒 False → 自动报告 `overall_result` 恒 "failed"、`pass_rate` 恒 0.0 —— `.get` 默认值静默吞断层的教科书形态。修法=换判据来源，**精确谓词**（Codex #254 R1 校正）：首选读 `context.test_execution.validation_pass`（TestExecution **列**，analysis 执行器按 `verdict in ("PASS","MARGINAL")` 写入的 canonical 布尔 —— 注意它不在 analysis payload 里，`analysis.get("validation_pass")` 还是恒 None）；若只拿得到 payload 则用 `analysis.get("verdict") in ("PASS", "MARGINAL")`（verdict 取值就这三个字面量）。**绝不 `bool(verdict)`** —— 非空字符串恒 True，"FAIL" 也会判成通过，反向翻车。⚠️ **修法红线**：不得用 `status=='completed'` 当通过谓词 —— 相位机械成功与 KPI 通过是两层（analysis 相位对 KPI FAIL 也返回 SUCCESS），completed 判通过会让失败的测试谎报通过，代价不对称。手动路径（HistoryTab 生成的那份）走 `report_data_collector` 的 `validation_pass` 谓词，**现状正确**——它显示 0.0% 可能是如实报告 mock 环境 KPI FAIL，修自动路径前先分辨两份 PDF。⚠️ `report_service.py` 建 summary 的 `overall_result`/`.get('pass_rate', 0)` 段**不许当残留清理**（Codex #254 R2）：VRT 归档路径（`road_test.py::_archive_execution_report` 传 `ExecutionReport.model_dump()`，该 schema 无 `execution_summary` 键）**仍在消费它** —— 它只是不在用例执行路径上，对 VRT 是活代码。可同 PR 清理的只有报告模板 `Test Plan: N/A` 计划链残留字段。
- `[discovered 2026-08-01 during ARCH-1 S6 总验]` **[→ 提升 P1-22 (2026-08-01)]** **PDF 生成器缺 CJK 字体 — 中文全渲染成豆腐块（P3）** —— 报告标题/正文里所有汉字显示为 ■，中文用例名的报告不可读。`pdf_generator.py`（reportlab）需显式注册中文字体（内置 `STSong-Light` CID 字体或捆绑开源 Noto Sans CJK），并全模板换用（已核实全 `app/` 无 registerFont/TTFont/CID 调用）。
- `[discovered 2026-08-01 during ARCH-1 S6 总验, 内审定案]` **[→ 提升 P2-19 (2026-08-01)]** **执行相位计数对所有行恒 0 — 后端计数谓词 token 错配（P3）** —— `api/test_execution.py` 的 `_to_history_item` 数相位用 `p.get("status") == "completed"`，而 runner 落库写的是 `StepExecutionStatus.SUCCESS.value = "success"` → `phases_done` **全程恒 0**（不是只在终态；"进行中显示正常"是 0/N 初期像正常的观察偏差；失败行徽章正常是 "failed" token 巧合两边一致）。该函数 docstring 自己写的 `completed/failed` 就是错误谓词的种子，一并清。修后端一处，三个消费方（HistoryTab / 主控台最近执行卡 / TestCaseLibrary 执行进度）全好。
- `[discovered 2026-07-31 during GUI 新建入口片]` **[→ 提升 P3-14 (2026-08-01)]** **`TestCaseCreate.test_type` 的 schema 描述漏 `MIMO_OTA`** —— 枚举 `TestCaseType` 里有，但请求 schema description 只列 `TRP | TIS | Throughput | Handover | MIMO | ChannelModel | VirtualRoadTest | Custom`。这段进 OpenAPI，是外部调用方唯一会读的东西。改它要走契约四步；顺带候选：「描述 ⊇ 枚举」可做成会红的门（同 G7/G8 思路，属**加机制**，待拍板）。同片顺带：`template_category` 的 schema 无 `max_length` 而列是 `String(100)`，超长在 PG 直接 500（GUI 侧本片已 `maxLength={100}` 收窄，schema 约束走契约四步一并做）。
- ~~`[discovered 2026-07-31 during GUI 新建入口片, Codex #250 P1]` **[→ P2-24；2026-08-11 本地完成]** **测试用例 REST 契约无 lab_profile_id 字段 — 多 active lab 部署下 GUI 建的用例不可执行且无处补绑**~~ —— 可空字段已贯通 REST/OpenAPI/生成类型/GUI/mock；创建与编辑弹窗可显式绑定，模板起点复制绑定，多活动实验室创建时不再允许含糊放行。
- `[discovered 2026-07-31 during GUI 新建入口片]` **`created_by="gui"` 是硬编码占位** —— GUI 无认证上下文（`require_auth` 全仓零使用点，S4c 申报过），`TestCaseCreateModal` 建例统一落 `created_by="gui"`。接上认证上下文（roadmap 既有 Auth Context 待实现项）后换成真实用户名。

- `[discovered 2026-07-30 during ARCH-1 roadmap 补记]` **[→ 提升 P1-23 (2026-08-01)]** **现场协议不覆盖 P0-8，照 checklist 走完会漏掉 F64 验证** —— [`guides/on-site-debug-protocol.md`](guides/on-site-debug-protocol.md) 开篇写「配套 P0 队列（**P0-3/4/5**）使用」，五个 Phase（网络 / 逐仪表 SCPI 握手 / SA 入 HAL / 路损校准 / DUT attach）**没有 P0-8 的 gate**。而上方「Blocked on hardware」表强制要求按该协议走 —— 结果是「走完了」却漏掉 P0-8 现场半（real F64 上 load→run→改参全 0 error + 输入口变绿 + DL 不失真），**比没有 checklist 更危险**（给人已覆盖的错觉）。当前缓解：P0 队列表已补 P0-8 行 + 表下注解写明出发前手动排进当天计划。**正修要定两件事**：① P0-8 塞进哪个 Phase（比 Phase 1 SCPI 握手重，要 load→run→改参→读电平，可能单独一段或作 Phase 1 的 F64 子门）；② gate 判据怎么拆 —— P0-8 验收最后一条「DL 不失真（DUT attach 后非 0% ACK）」**依赖 DUT attach**，有一半得等 Phase 4，gate 可能要拆两半挂两个 Phase。**收口更新**：P1-23 已改协议，P1-45 已改 roadmap，现行现场排程统一指向 Blocked 表；P0-3/4 已完成，不恢复旧链。⚠️ 动之前按标题/条目名定位，**别在文档里写行号** —— 本次 PR 实证：行号会被自己的编辑挤跑。
- `[discovered 2026-07-29 during ARCH-1 S4a]` **GUI 没有「新建测试用例」入口** —— `TestCaseLibrary` 的新建按钮由 `onCreateNew` prop 守着，**全仓无人传**（`TestManagement.tsx` 只传 `enableExecute`）；入口原本挂在 StepsTab 上，随 S4a 一并删除。现状：**直接执行路径上的** MIMO_OTA 用例只能来自 bootstrap 种子，可改可执行不可新建。（GUI 并非完全建不了 TestCase —— 虚拟路测的「创建场景」会落一行 VRT 型 TestCase，但那条不走 S6 要验的直接执行路径。）S4a 已显式申报为能力缺口。⚠️ **这是 ARCH-1 S6（浏览器闭环总验）的前置** —— S6 验收第一步就是「建用例」，开工前先决定：补入口（GUI 新功能，需设计稿），还是把 S6 验收改成「改现有用例」。**✅ done (2026-07-31, GUI 新建入口片)**：走了「补入口」路 —— 设计稿 [`docs/design/gui-create-test-case-entry.md`](design/gui-create-test-case-entry.md)（四待决 2026-07-31 拍板全甲案），`TestCaseCreateModal` 建壳（`is_template=true` 堵"建完即隐形"洞）→ 复用 `TestCaseEditModal` 填参数两步流；D-1 行为门（建→可见→可执行，变异实跑）+ 浏览器闭环实测（建→见→改参→执行→历史有行）。S6 前置解除。
- `[discovered 2026-07-20 during 出发前门审 F5]` **UXM 幂等捷径生效后剩余写全在小区 ON 态执行 — ON 态同值写 band/duplex 是否触发 UXM 内部重配 (掉 DUT) 真机零实证**。ARFCN/功率有回读对账兜底; band/duplex ON 态被拒 (-221 类) 只进错误队列无对账项即静默。现场若"BW 已同仍重启"按 onsite-plan-20260721 风险⑧②排查; 正修方向 = band/duplex 也纳入幂等预读 (值同跳写) 或对账。TDD 主线 (n78) 幂等已限定 (F3 保守化: 仅 TDD + readback 能力位开才走捷径)。
- `[discovered 2026-07-20 during 三开关门审 #216]` **开关1 inherit 的"知情继承"只核对频率, 层数盲区**: 小区级层数继承仪器态但 RRC recon 仍按 TestCase 推层, CSI-RS 端口按 TestCase 层数算 — 三方可各不相同; Phase 6 读 UE 能力抓不到 cell 生效层数低于请求。正修方向 = read_live_frequency_identity 扩展读层数 (注意 #114 教训: 配置旋钮回读是 echo, 要找真生效读法) 或 inherit 下强制核对面板。当前缓解 = inherit 日志显式披露"层数未核对"。
- `[discovered 2026-07-20 during 三开关门审 #216]` **configure_mac_throughput_test 返回值无人消费**: measure 调它不查布尔契约, ON 态写 TDD pattern 被拒 (-221 类) 即静默带旧配置测。正修 = 消费返回值 fail-loud (同 set_cell_config 处理, Codex #195 R5 母题)。
- `[discovered 2026-07-21 during 队列僵尸复发排查]` **[→ 提升 P3-15 (2026-08-01)]** ~~**`test_feature_gaps.py` 无 DB 隔离, 每次全量测试往运行中的开发库塞 ~12 条队列条目 + 若干测试计划**~~ ✅ **已修 (P3-15)**: 标准 SQLite 隔离 fixture + 跑前后 dev 库计数不变实证；存量清理见 scripts/cleanup_zombie_test_plans.py。原文:(Priority Test Plan / Queue Down Test / Stats Test Plan / Auth Test Plan 等)—— 801 条僵尸的持续来源; #218 清完当晚 agent 门审跑全量即复发 13 条 (07-21 晨再清)。计划管理列表同样被污染。正修 = 该文件补项目标准 SQLite 隔离 fixture (其余测试文件已有惯例); 顺带清一次 dev 库存量测试计划。
- `[discovered 2026-07-21 during 仪表参数表单验证]` ~~**计划在执行队列中 (queued) 即锁死步骤编辑 (StepsTab 只读门)**~~ ❌ **dropped (2026-08-02 用户确认)**: StepsTab/执行队列随 ARCH-1 S4 拆除，全仓零引用，问题载体不存在。原文: —— 现场想调参数须先出队→改→重排队 (07-21 晨表单验证被迫走了这一圈)。runner 起跑时做 TestCase 快照, queued 态编辑理论安全; 设计题 = 只读门是否放宽到仅 running/paused 拦。

> **Triage history**: 2026-05-17 — promoted 4 active entries to P3
> slots (P3-6: chamber preset Type-C test reconciliation; P3-7: VSCode
> interpreter settings + `.vscode/` policy; P3-8: VRT pydantic
> regression; P3-9: catalog status enum drift). Resolved entries kept
> below for audit trail.
>
> **2026-05-27 — 用户直接 triage 4 个现场发现** (现场授权, 非 weekly review): F64 driver
> 修法 → **P0-8** (升 Current Focus, 本地); backend scpi-command desync → **P1-16** (本地);
> EMCenter switch → **P2-9** (调研+现场); 转台无结论 → **U-5** (Known-unknown)。
>
> **2026-07-03 — 用户授权 triage 全天现场发现** (收工整理): F64 频率正修 → **P1-18**; UXM
> set_cell_config 编排 + SSB 三件套 → **P1-19**; 转台断连韧性 → **P1-20** (⚡阻塞★核心最直接);
> HAL 会话卫生 (互斥/排水恢复/延迟应答) → **P1-21**; F64 直通编排 → **P2-17**; 资产真值自动化
> → **P2-18**; EMCenter VXI-11 → 并入 **P2-9** 剩余本地半; keepalive 数据点 (转台 <11s/UXM
> ~15min) → 并入 **P2-4**。全天权威详录 [`guides/onsite-tasks-20260703.md`](guides/onsite-tasks-20260703.md)。

- `[discovered on-site 2026-07-03 during precheck]` **[→ 提升 P1-27 (2026-08-02)]** **P1-8 校准门不区分数据来源 (mock/real)**: 昨晚 mock 路损校准 cert 在 real 模式 precheck 里 `cal_pass: true` (门只查存在/频率/时效, 不查 provenance) → 真测会静默应用 mock 补偿值。修法 = cal 记录带 `use_mock` 标记 + real 模式 strict 门拒 mock cert (feedback_runtime_gate_not_frozen_snapshot 同族: live source 还要 live provenance)。~~待 promote (建议 P1, 半天)~~ ✅ 已提升 **P1-27** (2026-08-02)。
- `[discovered on-site 2026-07-03 during RF体检]` **InputLevelController 闭环方向存疑**: "AUTOSET 失败→降功率"像按过载假设写的 (收不到信号应升不应降), 且起点 -10 dBm/SCS 语义过热 (BW100 满业务 = +25 dBm); UXM 510 告警实证被 HW 口限二次钳制。修法 = 闭环失败分支按"无信号/过载"分诊 + 起点从 TestCase 功率推导。待 promote (建议 P2, 半天)。

- ~~`[discovered 2026-05-15 during P2-2]` **Commissioning factory's "default lab" path is fragile**~~. ✅ Resolved 2026-05-16 — see D12 in [`roadmap-archive.md`](roadmap-archive.md).
- ~~`[discovered 2026-05-14 during P0-1]` chamber preset Type-C `has_lna` test mismatch~~. → Promoted to **P3-6** (2026-05-17 triage).
- ~~`[discovered 2026-05-14 during P0-2]` VSCode Python interpreter drift~~. → Promoted to **P3-7** (2026-05-17 triage).
- ~~`[discovered 2026-05-17 during P2-3]` VRT pydantic regression (38 failures)~~. → Promoted to **P3-8** (2026-05-17 triage).
- ~~`[discovered 2026-05-17 during P2-3]` catalog `status` enum drift~~. → Promoted to **P3-9** (2026-05-17 triage).
- ~~`[discovered 2026-05-17 during P2-1 design]` **UXM name-cleanup chore**: rename `UxmCommandProfile` → `UxmTestApp` and `UxmTestProfile` → `UxmTopologyProfile`~~. ✅ Resolved 2026-05-17 — see D27 in [`roadmap-archive.md`](roadmap-archive.md).
- ~~`[discovered 2026-05-17 during P2-1 design]` **`self._cmds` class-vs-instance mutability fix**~~. ✅ Resolved 2026-05-17 — see D27 in [`roadmap-archive.md`](roadmap-archive.md).
- ~~`[discovered 2026-05-17 during P3-8]` **VRT integration tests share dev PG state** (test-isolation)~~. ✅ Resolved 2026-05-17 — see D28 in [`roadmap-archive.md`](roadmap-archive.md).
- ~~`[discovered 2026-05-17 during PFS-doc investigation]` **`channel-engine-service` real-mode endpoint calls missing method**~~. → Promoted to **P0-7** (2026-05-18 triage) — D11 ruled `run_with_external_clusters` unimplementable in ChannelEgine; responsibility moved to MIMO-First adapter rewrite + scope broadened to include Phase 5/6 field plumbing + `external_asc` debug mode + fail-fast.
- ~~`[discovered 2026-05-17 during PFS-doc investigation]` **`probe_phase_jitter` UI label says "±10°" but code applies "±180°"**~~. ✅ Resolved 2026-05-18 — ChannelEgine Phase 0 (PR #1) updated UI label + runtime warnings to match ±180° code path; jitter / cal mutex now enforced at runtime + UI level.
- ~~`[discovered 2026-05-19 during P1-7 docs catch-up review]` **Commissioning precheck 不拦未校准 chamber** (Codex P2 on PR #60)~~. → **Promoted to P1-8** ✅ Done (PR #61 merged 2026-05-19; ad-hoc triage, 走 ad-hoc 因为 next 现场之前必须有 fail-loud gate, 不能等 weekly review)。Codex P1 follow-up on PR #61 commit 42af8ca 又抓到 strict gate 用 chamber-only 查询 (没 frequency filter) 漏过老 / 不同频段 cert, 同一 PR commit 743789c 修了, 换成跟 measure phase 同一个 `ProbePathLossCalibrationService.get_latest_calibration(chamber_id, freq_mhz)` ±5% 窗口查询。详见 P1-8 entry。
- ~~`[discovered 2026-05-27 on-site]` **F64 ATE/SCPI 端口硬件固定 3334 (误用 5025 = 两天 blocker 根因) + 输入信号参考/crest 是全新缺失 driver 能力 + 加载需 SYST:ERR? gate**~~. → 用户 2026-05-27 直接 triage 为 **P0-8** (本地可启动, 升 Current Focus; 含默认 3600M .smu 设定)。
- ~~`[discovered 2026-05-27 on-site]` **backend scpi-command 端点 slow-op desync (`timeout_ms` 没透传)**~~. → 用户 2026-05-27 triage 为 **P1-16** (本地)。
- ~~`[discovered 2026-05-27 on-site]` **EMCenter switch 不吃 raw SCPI (EMQuest/GPIB 血统, `.50`)**~~. → 用户 2026-05-27 triage 为 **P2-9** (offline 调研 + 现场)。
- ~~`[discovered 2026-05-27 on-site]` **转台 (Aerotech) 测试了但无结论, 记录供下次开发**~~. → Known-unknown **U-5** + P0-5 note (下次现场验证)。
- `[discovered 2026-05-28 post-P0-8 review]` **InputLevelController: cal-based feed-forward 粗设 + autoset 兜底验证 (hybrid)**. 当前是纯闭环 — UXM 起手 -10dBm → F64 AUTOSET → measure → 不在窗口调 UXM 重试 (最多 5 轮, 每轮 ~3-5s SCPI)。如果有 (a) UXM 输出 cal、(b) UXM-to-F64 cable_loss cal、(c) signal structure PAPR, 就能一次性算 `F64_input_avg = UXM_dBm - cable_loss` + `crest = PAPR` → `INP:LEV:AMP:CH` + `INP:CRE:SET` 粗设 → `measure_input` 一轮校验 (不 autoset) → 在窗口 + clipping OK 直接锁定; 偏差大才退到现有 autoset 闭环兜底。**核心**: 闭环不替, 给"粗设"路径并接 cal 漂移监控副产物 — (粗设值 - 实测值) 写遥测, 持续累计 = cable bend / 接头老化 / cross-band 误差的可观测信号, 知道 cable cal 该重标。GPS+末段制导哲学。依赖下一条的 UXM-to-F64 cable_loss cal 基础设施。 **【2026-06-06 决策：搁置 / backlog only】依赖下一条 #2001(2) 的 UXM-to-F64 cable_loss cal 基础设施，而 #2001(2) 已评估保持现状不推进 → 本条连带搁置，非待办。**
- `[discovered 2026-05-28 post-P0-8 review]` **多端口 MIMO input 不一致 — imbalance metric + 容忍带 + cable balance cal**. 3600M 4x4 各 input 累加 ±1-2.5 dB imbalance 是物理必然 (cable 长度/质量 ±0.5-1dB + UXM TX port ±0.3dB + F64 ADC 增益 ±0.5dB + 接头老化 ±0.2dB + 测量噪声 ±0.1-0.3dB)。当前 `_measure_and_check_window` 任一 input 越界 → strict 整体 fail, 0.3 dB 边缘越界也死, 反而不科学 — 缺 imbalance 概念。三段递进: **(1) 本地 ~半天 — ✅ done**: `InputLevelController._classify_imbalance` 算 `imbalance_db = max(avg)-min(avg)` 跨 input + 容忍带分类 (ok ≤1dB / marginal 1-2.5dB / excessive >2.5dB, 阈值可配); 收敛时填 `InputLevelResult.imbalance_db/imbalance_status` + measure `input_level_calibration` payload, marginal/excessive 加 system_warning。**纯增量遥测, 不改 converged/fail 门** (软化 per-input 硬门要配 (2) per-port cable cal + 涉及测量门语义需用户拍板 → 留现场); 4 单测。**(2) 现场+本地**: 新 cal cert 类型 `CableBalanceCalibration{cable_loss_by_port_db: Dict[int, float]}`, 现场用 SA/VNA 测一次落库, 上一条 feed-forward 用 per-port cable_loss 取代 chamber-avg; **(3) 长期**: cal 漂移监控持续 N 次差异中位数 > 阈值 → 主动告警操作员。CTIA MPAC OTA 标准做法, 我们当前缺。 **【2026-06-06 决策】(1) ✅ done (#143 遥测)；(2)(3) 经评估**保持现状不推进** —— 软化 working 的 per-input strict 门无可证明收益且有放过坏 setup 风险，(2) cable cal 真要做需现场 SA/VNA。详见 `architecture/multi-port-input-level-semantics.md` §5。backlog only，非待办。**
- `[discovered 2026-05-28 post-P0-8 review]` **operating point measurement uncertainty 进报告 uncertainty budget**. AUTOSET **不破坏任何 cal cert** (path-loss / F64 user-alignment / UXM 输出 cal 都不被写脏 —— AUTOSET 只调单 input 前端 PGA 挡位, F64 内部映射保证测出的 dBm 仍是正确绝对值, 不动 channel-to-channel 关系也不动 output 端绝对功率), 但 AUTOSET 后 F64 处于一个具体 PGA 挡位, 该挡位的 absolute 精度继承 factory ADC cal 的 ±0.5-1 dB 不确定性 + AUTOSET 单次 measurement noise ±0.3 dB。当前 reference/measure 报告把 RSRP / 吞吐当确定值呈现, 没把这部分不确定性跟 path-loss cal / SA cal 不确定性并联累加进 combined measurement uncertainty budget (报告里 "RSRP ±0" 是骗人, 实际应是 combined U)。应: reference/measure phase 输出携带 operating-point uncertainty 分量, report phase 按 GUM 累加成 combined U (k=2)。模式上 "测试前 setup + 测试中 frozen PGA" 是 RF 标准做法 (等同 SA 测前设 ref level), **不算测试中扰动**; 但记两个边界: (a) **严格 PFS / PWS 未来场景** AUTOSET 改 PGA 可能引入 group-delay→phase shift, 须 cal 后不动 PGA 或 re-cal phase (当前 power-only PFS 不受影响, TR 37.977 F.2); (b) **VRT 跨场景切 cell config** 时 PAPR 漂 → operating point 需 re-setup (VRT 当前未接 InputLevelController, 接入时一起做)。另可加 idempotency gate (setup 过 + 同 cell config 跳过) 防 azimuth loop 内误调 AUTOSET 污染跨 azimuth 可比性。 **【2026-06-06 决策：保持现状不推进 / backlog only】当前报告呈现工作正常、无 demonstrated problem；与 #2001 门同族，详见 `architecture/multi-port-input-level-semantics.md` §5。**
- `[discovered 2026-05-31 during P2-11 Phase 5]` **UXM 默认 topology profile 字段泄漏进 path B** (Codex on PR #112) — **✅ done 2026-06-04 (#127 后端 + #128 GUI, 方案 b)**. HAL-init 经 `apply_topology_profile → set_cell_config(profile.to_config_dict())` 把 profile 的 `mimo_port_preset` / `tdd_pattern` / `sched_algo` / `csi_rs_ports` 落到 UXM 硬件; measure (path B) 的 `set_cell_config` 只传 frequency/ARFCN/BW/SCS/band/`mimo_layers`/power, **不覆盖上述字段** → 它们残留进正式测试 (如 2x2 TestCase 跑在残留的 4x4 端口路由上)。频率/ARFCN/MIMO layers 已 TestCase 驱动, 但 port routing / TDD / scheduler 既没被 path B 驱动也没被 reset。**待定方向 (需用户定 port-routing 语义)**: (a) measure 从 `mimo_layers` 派生并传 `mimo_port_preset` (2→"2x2"/4→"4x4"/1→"siso") + TDD/sched 补成 TestCase 字段或显式 reset; 或 (b) `MIMOOTAConfiguration` 直接加这些字段。⚠️ 注意 layers≠preset 在某些 diversity 配置下合法, 不能盲目自动派生。属 P2-11 同族 (TestCase 单一真值源驱动) 的下一块。Phase 5 PR 已把三处误称"天然分开"的注释改准 (承认 leak)。**实现 (#127)**: 用户 2026-06-04 选**方案 b** —— `MIMOOTAConfiguration` 加 `mimo_port_preset`/`sched_algo`/`csi_rs_ports` (`tdd_pattern`/`tdd_period` 已有), measure 经 `_build_pcell_cell_config` 显式传给 set_cell_config (set_cell_config 早已支持这些 key, 只是 measure 没传); `csi_rs_ports=None` 不放进 dict (缺省哨兵, 避免 SCPI 写 "None"); 默认对齐内置 profile (backward-compat); **不**从 layers 自动派生 (尊重 diversity layers≠preset)。+9 单测。**GUI 入口 (#128)**: MIMOOTAConfigForm 暴露 mimo_port_preset (Select siso/2x2/4x4/2x2_alt) / sched_algo / csi_rs_ports, 都可空 (留空=用 profile)。注: 上文"默认对齐 profile (backward-compat)"是 cf97251 初版述, Codex P1 #127 后**默认实为 None** (= 未指定, 不覆盖旧 saved 数据)。tsc + 浏览器 smoke 验证渲染+选值。**#1974 GUI 闭环。**
- `[discovered 2026-06-01 during P2-11 Phase 6, 用户提出]` **DUT 自声明能力文件 (declared capability) + 三层能力交叉校验**. Phase 6 从 UXM `query_ue_capability()` 拿 UE **协商**能力 (max_dl_layers) 做下发后校验 —— 但这是 **attach 之后**才有的运行时值, 规划 / precheck 阶段 (未 attach / 未上硬件) 拿不到。**用户提出**: 加一个**用户可填写 / 编辑的 DUT 自声明文件** (DUT capability profile: max DL/UL layers、支持频段、最大调制、UE category、双工等), 测试**从这个自声明开始了解 DUT 能力** —— 早在 attach 前就能拿 TestCase 跟声明能力比 (e.g. TestCase 请求 4 层但 DUT 声明 max 2 → 提前 fail, 不浪费一次真跑)。**最终准确能力仍以 UXM (或其它综测仪) 上报参数为准** (`query_ue_capability`): 自声明 = "expected/spec", UXM 上报 = "actual/negotiated", 两者**交叉校验** (不一致 = DUT 实际行为跟它的 spec 声明不符, 本身是有用发现)。**三层能力**: 声明 (自声明文件, 规划期) → 协商 (UXM `query_ue_capability`, attach 后, Phase 6 用) → 运行时 (CSI RI, 测量中)。设计方向: 新建 `DUTProfile` 实体 (平行于 `LabProfile` 之于 chamber), GUI 让操作员填 / 编辑, precheck 早期拿它校验 TestCase, attach 后跟 UXM 上报交叉核对。把 D 类"DUT config (操作员 attach 时给)"从临时输入升级成**结构化可预声明 + 可校验**。属 P2-11 同族。**四阶段全 ✅ done (此线收口)**: ① 实体 (model/migration c4a91f8e2d70 / CRUD `/dut-profiles`, 15 测试); ② precheck 早期校验 (config.dut_profile_id → precheck section 2.3 拿请求 vs DUT 声明比, 请求 > 声明: strict FAIL / opt-out warn; 新 `precheck_strict_dut_capability` 门**已同步 bypass 4 处** GUI+CreateSessionRequest+_request_overrides+test, per feedback_strict_gate_extend_bypass_toggle; dut_capability_check + precheck 门集成测试; Codex P2 #135: 早期 strict fail 也持久化 phase result, UI 可见 violation); ③ GUI (`dutProfileService` 平行 labProfileService + `DUTProfileManager` CRUD 页 + 侧栏「DUT 声明」导航 + `MIMOOTAConfigForm` DUT 选择器/声明提示行/严格开关/实时越界预览; **运行时端到端验证**: alembic 迁移 apply 到 dev PG → 建档 → 表格渲染真实数据 → TestCase 步骤选 DUT → 声明提示 + 严格开关启用); ④ **声明 vs 实测协商交叉核对** (后端 `dut_capability_crosscheck.check_dut_capability_mismatch` 双向比, precheck section 2.5b hoist dut_profile 后拿声明 vs `query_ue_capability` 实测比 —— **audit-only, 不 fail, 不覆盖声明**; observed 单独记 `measurements.dut_capability_observed` + mismatch 记 `dut_capability_mismatch`; 仅 source==real_ue 核对, mock/未 attach skipped; GUI `DUTCapabilityCrosscheckCard` 在 commissioning 预检阶段展示 declared/observed 差异 + operator **显式**「采纳实测值」反写 (走 PUT /dut-profiles/{id}); 10 单测 + 4 precheck 集成测试: mismatch surface + 声明 DB 不被覆盖 + mock skip)。④ 直接回答用户问题②「准确能力是否反写回声明文件」: **不自动反写, observed 单独记录 + surface, operator 显式采纳**。**三层能力关系网闭合**: 声明 (规划期) → 协商 (attach 后交叉核对) → 运行时 (CSI RI)。
- `[discovered 2026-06-04, 用户审计暗室首测]` **暗室首测捷径被 Phase 6 cell_config 门破坏 + standalone 自检借鉴** — ✅ done (本 PR)。用户问"大量细节修复后暗室首测有没有被破坏"。**破坏**: P2-11 Phase 6 (#114/#124/#126) 的 `precheck_strict_cell_config` 门 (DL layers/调制/MCS) 没被暗室首测 lab-smoke bypass 覆盖 (GUI labSmoke + CreateSessionRequest + _request_overrides 三层全漏 + 测试也漏) → 真硬件 bring-up 撞它 (DUT 协商能力 < 默认请求 / MCS clamp) 挡住快速 first-call。`feedback_strict_gate_extend_bypass_toggle` 母题又踩 (Phase 1/2/3 当时覆盖了, Phase 6 在那之后加漏了)。**修**: 三层补 cell_config bypass + test_commissioning_strict_gate_overrides 钉死 (_P2_11_FLAGS 加 cell_config)。**借鉴**: 加暗室首测前逐设备快速自检 (`POST /commissioning/device-selfcheck` 主动探测各 driver 连接+响应 + GUI 暗室首测页"运行设备自检"按钮/结果) —— 借鉴转台 #132 / EMCenter standalone 验证理念, 把"首测中途撞设备细节"前移成"首测前先单独验设备"。+5 自检测试, commissioning 25 测全过, tsc 通过。
- `[discovered 2026-06-05 during DUTProfile 收尾, 用户提出]` **SIMProfile (SIM/eSIM 身份 + 鉴权声明) + SIM↔UXM 一致性 fail-loud** — **→ 已排期 P2-13 (2026-06-05 用户排期, 设 Current Focus); 本条留作完整设计记录, 排期/验收/分阶段见 P2-13 正式条目**。用户提"做测试经常 SIM/eSIM 匹配问题, 最常踩鉴权 (Ki/OPc)"。现状: SIM 身份/PLMN/鉴权**完全没建模** —— UXM 驱动 SCPI 树 (`CONFig:NR5G:{cell}:...` + `CALL:NR5G:{cell}:...`) 一条 auth/IMSI/PLMN/Ki 都没有, attach 的 IMSI 是操作员手敲只当审计; SIM 匹配是 Test App 手配黑箱, 挂了只给泛泛"UE capability unavailable / attach 不上" → 正是 first-call 现场瞎调。**调研定论 (商用卡)**: 商用卡 Ki 不可提取/破解 (用户判断对, AKA 双向, emulator 没 Ki 既验不了 UE 也发不出 UE 认的 AUTN); 但"所以没法测"对 RF/吞吐测试是**错结论** —— 正解是**可编程测试卡** (自写 IMSI/Ki/OPc/Milenage, emulator HSS 配同值 → 完整真鉴权), 运营商网络特性配在 emulator 侧不在卡的秘钥里; Keysight 官方做法也是测试卡跟 UXM 默认 IMSI/PLMN 预匹配。要某运营商精确网络 → 运营商测试卡 (真 PLMN + 实验室已知 Ki)。**别折腾商用卡**, 痛点正解 = 系统管住测试卡 Ki/OPc/PLMN ↔ UXM 一致性 (跟 DUTProfile 同母题: 声明 + 下发前一致性 fail-loud)。**设计已定 (用户对齐 2026-06-05)**: ① **独立 `SIMProfile` 实体** (不内嵌 DUTProfile —— DUT↔SIM **多对多**卡池复用, 内嵌会逼 Ki 重复→stale; SIM 更像 LabProfile 那样的实验室基建), TestCase 引用 `sim_profile_id` (跟 lab/dut 并列, TestCase 单一真值源驱动)。② **字段**: `imsi`(15位)/`iccid`(选); `mcc`+`mnc`(显式, 校验=IMSI 前缀, 不解析因 MNC 2/3 位歧义); `ki`(32hex)/`opc`(32hex, 统一存 OPc)/`auth_algorithm`(MILENAGE 默认 / TUAK / XOR; **排除 COMP128** 2G); `card_kind`(test_sim/operator_test/commercial —— 当鉴权可行性门, commercial **不存 Ki** 标"不可鉴权用测试卡"); `sim_form`(usim/esim); `eid`/`esim_profile_id`(eSIM: **一个 profile=一行**, 同 `eid`=同芯片多 profile, 扁平化让交叉核对永远比一个 IMSI; SM-DP+ 下载不进系统); `extra_metadata`(TUAK 冷门参数等); **不要** `sqn`(emulator 运行时态)/manufacturer/model。`ki`/`opc` 凭据 → API/日志**脱敏**(只显后4位)+ 不进导出 + 仅 test/operator 卡存。③ **档 A/B provisioning** (UXM SCPI 能否配鉴权**待现场查 S8711A SCPI command reference**, 公开文档 403 拿不到; 强信号能 —— UXM 卖点就是 SCPI 驱动整套 signaling/固件级测试): 档 A 能配 → 从 SIMProfile **自动 provision UXM HSS** 消除手配 mismatch; 档 B 不能 → **cross-check + warn 保底** (本地可交付)。④ **交叉核对**: precheck 拿 SIMProfile vs UXM 小区 PLMN + HSS 比 (下发前); **attach 后拿实测认证 IMSI vs 声明比** (强化现"防对错设备"门, **替代操作员手敲 IMSI** 弱环节, 自动抓插错卡)。⑤ **鉴权 fail-loud 分根因** (对准痛点, SQN 不入字段但用于此): **MAC failure**(Ki/OPc/算法不符→改凭据) vs **sync failure**(SQN 去同步, 卡发 AUTS→resync, **非凭据问题**) vs **no subscriber**(HSS 没此卡→provision) —— 三类不同修法, 别把 SQN 去同步误当 Ki 配错瞎调。属 P2-11 同族 (跟 DUTProfile 平行: 能力层 vs 身份/接入层)。**WIP**: 设计完成未启动, 等正式排期 (DUTProfile 刚收尾, WIP=1); 档 A 待现场 UXM SCPI 确认, 档 B (声明+cross-check+warn) 本地可启动。
- `[discovered 2026-06-06 during probe_number 局部化, Codex P2 on #155]` **跨暗室同号下: (1) 部分校准表缺 chamber 维度 + (2) NULL-chamber 复合唯一缺口**. probe_number 改按 chamber 局部 (复合唯一 uq_probes_chamber_probe_number) 后两个边界: **(1)** path-loss 校准**安全** (ProbePathLossCalibration 有 chamber_id, channel-engine measure 主路径按 chamber 取); 但 `probe_amplitude_calibrations` / `probe_phase_calibrations` 只有 `probe_id` 无 chamber_id, probe_calibration_service 按 probe_id 单独查 (line 457/819) → 多暗室同号会返回别暗室的 幅度/相位校准 (silent wrong data)。proper fix = 给这些 cal 表加 chamber_id + service 查找带 chamber (多表+迁移, 独立 PR)。**【2026-06-07 本 PR「校准 chamber-scoping foundation」✅ 完成基础版 (用户排期"#155 之后下一个 PR", scope=聚焦基础版)】**: 5 张 probe-keyed 校准表 (amplitude/phase/polarization/pattern/validity) 加 nullable+indexed `chamber_id` (迁移 `a1c3e5b7d9f2`, PG add-column / SQLite create_all no-op, down/up 已验可逆); **测量路径活跃消费方** `probe_pattern.consumer` (`get_probe_gain_at_azimuth` / `estimate_quiet_zone_ripple_db`) 改为按 chamber **prefer-exact → 回退 NULL/legacy → 绝不取其它暗室**, `measure`/`precheck` 传 `chamber.id`; service writer (`execute_*`) 持久化 chamber_id + getter (`get_latest_calibration`) 加可选 chamber 过滤; 7 新测 + 全套 1995 绿。**剩余 backlog (本 PR 故意收窄, 未做)**: ①REST/import 端点契约把 chamber_id 透传到 writer (现仍传 None); ②`ProbeCalibrationValidity` 改复合主键 `(probe_id, chamber_id)` + `check_validity`/`generate_validity_report` 的 chamber 作用域; ③报告层 chamber 作用域; ④legacy 单暗室 dummy 数据回填 chamber_id。patterns 表空 + 仅单暗室有 cal, 上述剩余项**仍未触发**, 多暗室真校准前需完成 ①②④。 **(2)** chamber_config_id nullable → 复合唯一不约束 NULL-chamber 探头 (chamber 删除 SET NULL 产生的 orphan / bulk 无 chamber 插入可重号); fix 需在 ondelete CASCADE / partial unique (NULL) / 强制 chamber 三选一 (有删除语义权衡), 需设计。 **小结**: (1) 主路径基础版本 PR 解决, 剩 ①②③④ + (2) 仍 backlog (均 Codex P2)。
- `[discovered 2026-06-07 from PROPSIM F64 信道注入 docx V1.2, 用户确认登记]` **信道注入子系统三缺口 + B-2 战略缺口 (channel-injection)** —— ✅ **2026-06-21 提升为 P2-14** (见上方 P2-14 区)。完整设计以 [`design/RT-MPDB-CDL-F64-channel-injection-design_V1.0.md`](design/RT-MPDB-CDL-F64-channel-injection-design_V1.0.md) 为准，**已远超**此处基于 docx V1.2 的理解 (native-fit 聚类 → B-2 普及 / 标注式 CDL / 按 test_class 分 B-1·B-2·GCM)。以下为 2026-06-07 登记时快照，实施以 V1.0 为准。源 `docs/hardware/PROPSIM_F64_信道注入工程文档_A-B路线_SCPI_V1.2.docx` (已升 V1.4)。现状: `gcm_strategy`(路线 A) + `asc`/`external_asc`(路线 B-1) 已实现, F64 驱动已有 `CALC:FILT:*`/`CH:MOD:CONT:ENV`/`ROUT:PATH:CONN`/`DIAG:SIMU` + 播 `.smu`/`.asc`/`.rtc`。**(1) f_upd 采样纪律一致性门 (B-1)**: 确定性 CIR 回放须 `f_upd=2·SD·v/λ` (SD=2, CIRs≥1000, `Δd=λ/(2·SD)`) 自洽; 现仅 `channel_params.update_rate_hz` 软字段 (1-1000 Hz 默认 100, 连高速 1556 / 高铁 4537-6481 / FR2 51852 Hz 都表达不了), 驱动未设 `DIAG:SIM:FIRUPD:MAN:CH` → "默认 10000 Hz 陷阱"静默错配 playback 速度/多普勒。proper = TestCase 的 v/f_c/SD ↔ 注入文件 f_upd fail-loud 一致性门 (契合 TestCase 单一真值源)。**(2) 12/24 抽头 + ≤24 簇 + 1024 逻辑通道硬件上限硬门**: `channel_engine` 跟踪 `num_clusters` 但无 ≤24 硬上限校验; TestCase 超限应进现场前 fail-loud (capability↔hardware↔gate 三方一致母题)。**(3) GCM 必要性结论**: 多普勒质心 <200 kHz (地面→高铁) 运行时频偏即可、>200 kHz (NTN Ka) 需 GCM; §10 待验证"运行时 200 vs GCM 500 kHz 是否同一硬件引擎"决定 B 路能否免 GCM 覆盖 NTN → 决定是否采购 GCM 许可。**另 (战略, 非缺陷)**: 路线 B-2 (`.tdlx`/`.tap` 参数化 TDL 生成 IP) 生成层**未实现** (驱动已能播 `.rtc`), 文档主推 B-2 用于高多普勒 / 几何骨架率受限场景。现场验证清单见 [`guides/on-site-debug-protocol.md`](guides/on-site-debug-protocol.md) §7。
- `[discovered 2026-06-28 during P2-15 S5 浏览器闭环]` **LabProfileWizard.tsx:311 空值崩溃 (`Cannot read properties of null (reading 'value')`)** —— P2-15 S5 用 Playwright 点模板 + 填 LabProfile 名时触发；**初始渲染正常**，自动化交互序列才触发（疑某 onChange/ref 在中间态读 `null.value`）。当时 curl 直接建 lab 绕过（`App.tsx:491` `needsLabProfileWizard` 只查 lab-profiles 空数组，建好就跳过向导），未深究根因。中等，下次 GUI 批次定位修。**✅ done 2026-07-02 (#191)**：根因 = React 合成事件 `e.currentTarget` 在 handler 返回后被置 null，而 onChange 在 setState **函数式 updater 内部**读 `.value`（updater 批处理异步执行时崩）；修法 = 把值先读到 updater 外的 const（labName + endpoint 两处 onChange 同 hoist）。
- `[discovered 2026-07-02 during pre-departure 走查]` **[→ 提升 P3-14 (2026-08-01)]** **CreateSessionRequest 缺 `channel_asset_id` → 统一信道资产进不了会话创建 API（P2-16 S5 前置）** —— 会话执行是 measure 唯一消费路，但 `CreateSessionRequest`/`_request_overrides` 没有该字段，「暗室首测」页同样带不进。临时可跑路 = 建会话后 `PATCH /test-plans/cases/{id}` 把 `channel_asset_id` 合进 configuration（已固化为 [`scripts/onsite-run-channel-throughput.sh`](../scripts/onsite-run-channel-throughput.sh)，2026-07-02 mock 两次端到端 PASS：engine_mode 覆盖 `keysight_gcm` + `.smu` source=testcase + 4 方位吞吐 + analysis pass）。proper fix = CreateSessionRequest + `_request_overrides` + 暗室首测 GUI 加 channel_asset_id（归 P2-16 S5）。
- `[discovered 2026-07-02 during pre-departure 走查]` **TestManagement 计划步骤无执行 runner**（✅ **ARCH-1 S4 以"删除"结案**：整条计划链已拆，正式测试改走 TestCase 直接执行）—— `POST /test-plans/{id}/start` 只转计划状态，步骤停 pending；`dispatch_step` 仅 commissioning 三端点调用（run_phase / diagnostic / run-all，作用于会话自身 5 相位描述符），计划步骤编排层与会话执行层没有接线。S4-5 在 MIMOOTAConfigForm 配好的 `channel_asset_id` 经计划路无法被消费（只能经会话 TestCase）。步骤编排↔会话执行的接线设计属 TestCase-driven（P2-11/P2-16）同族，需要排期。
- `[discovered 2026-07-02 during pre-departure 走查]` **[→ 提升 P3-15 (2026-08-01)]** ~~**执行队列 100 条 5 月自动化测试产物僵尸**~~ ✅ **triage 完 (P3-15)**: 来源已断（隔离 fixture）+ 存量入 checked-in dry-run 脚本待操作员 --execute。原文: —— Priority/Queue/Stats Test Plan 等占满队列（90 等待 + 1 条卡 `running` 曾拒绝 HAL 重载，已强制重载清掉活跃态；队列条目还在）。两件事：① 一次性清理（`DELETE /api/v1/test-plans/queue/{plan_id}` 逐条，需操作员确认 —— ✅ **ARCH-1 S4b 起不需要了**：执行队列连同它的全部端点已删除，遗留 running/paused 计划行由 `test_case_runner.reset_orphaned_plan_chain_rows` 启动时清成终态）；② 防护 —— 自动化测试不应把队列产物留进 dev PG（测试隔离 SQLite 或 teardown 清理）。
- `[discovered 2026-07-02 during pre-departure 走查]` **[→ 提升 P3-15 (2026-08-01)]** ~~**vendor_file 资产顶层 `center_frequency_hz` 与 payload.scd_config.arfcn 可漂移**~~ ✅ **已修 (P3-15)**: `_check_vendor_declared_freq` create/update 双侧 fail-loud（顶层给值必须与 SCD 一致, 容差 1 kHz; update 按最终状态判防 PATCH 绕过）。原文: —— seed 数据曾是顶层 3.5 GHz vs `arfcn=640000`（=3600 MHz）矛盾：GUI 列表/表单显示读顶层，P2-11 频率一致性网读 payload arfcn → 显示误导现场。数据已修（2026-07-02 经工作台表单 3.5→3.6 + 顶层带宽补 100M，scd_config 完整保留）；proper = 表单/服务端加"顶层物理声明 vs scd_config 一致性"校验（vendor_file 两处都有值时必须一致或只留一处）。
- `[discovered 2026-07-02 during pre-departure 走查]` ~~**StepsTab 保存 toast 步骤名显示 "null"**~~ ❌ **dropped (2026-08-02 用户确认)**: StepsTab 随 ARCH-1 S4 拆除，全仓零引用。原文:（「步骤 "null" 已更新」）—— 纯外观，取名逻辑拿错字段。琐碎，GUI 批次顺带。
- `[discovered 2026-07-04 during #206 补扫]` **[→ 提升 P3-15 (2026-08-01)]** ~~**全量测试 2 个顺序耦合 flaky（日志/输出捕获为空型）**~~ ✅ **stale — 已被 #211 修 (P3-15 triage)**: 两个受害测试自带 `.disabled` 复位护栏 fixture（memory feedback_test_logger_emit_alembic_pollution 同修法），恶意排序（迁移测试前置）复现失败、连续多次全量 0 failed。原文: —— `test_db_preflight.py::test_unreachable_emits_actionable_banner`（`'数据库不可达' in ''`）与 `test_driver_capabilities.py::test_non_canonical_token_warns_but_adds`（caplog 空）只在全量跑挂、单文件跑全过；stash 干净 HEAD 同样复现 → pre-existing，疑前序测试污染全局 logging（handler/propagate）。测试基建问题：定位污染源 + 隔离。
- ~~`[discovered 2026-07-04 during #206 补扫]` **[→ P2-22；2026-08-11 复核已由 #225 交付]** **F64 disconnect 依赖 `_emulation_running` 缓存判"要不要 GOS"**~~ —— 原缺口是 HAL 重载后的冷实例缓存 False 时可能跳过停止；F64R-1 #225 已让 disconnect 以 `DIAG:SIMU:STATE?` 为真值，并由冷缓存定点回归保护。2026-08-11 再经 NotebookLM 按 Propsim User Reference §20.4.3.11/14/18 与 ATE AN §2.2.2 核实命令语义后，P2-22 状态收口为已完成。
- ~~`[discovered 2026-07-04 during #206 补扫]` **[→ 提升 P3-19 (2026-08-02)]** **QZ 验证 / 方向图扫描 / 多频扫频借用 acquire 的清理失败警告不可见**~~ ✅ **P3-19 acquire warnings 子片已收口** —— 公共 `acquire_sa_power_via_ce_tone` 增加可选 sink/context，并在包住 inner 的 `finally` 复用既有 drain；XPD co/cross、QZ grid 每点、方向图每角度、多频每频点均在下一次 reset 前收割，异常出口同样进入各自 `CalibrationResult.warnings`。本项只完成底层结果穿透；现有 real 入口和持久化边界见下一条 Discovered。
- `[discovered 2026-08-12 during P3-19 acquire warnings 内审]` **[P2 / 测试，不阻塞] 四族异常返回的 warnings 穿透尚无直接回归保护** —— 新增四项执行级回归均锁住成功返回；QZ grid/XPD、Pattern、Multi 的异常 `CalibrationResult` 已在实现中带同一 warnings，但若未来误删失败出口的 `warnings=warnings`，本片 focused 测试未必变红。按测试意见一轮止损只登记，不阻塞本片外审。
- `[discovered 2026-08-12 during P3-19 acquire warnings 全集审计]` **三族底层 warnings 尚无现场 real 入口与持久化闭环，需另行评估** —— QZ orchestrator 与 multi-frequency live API 当前硬编码 mock，XPD/`PatternCalibrationService` 无生产 caller；GUI 又走各自另一套 mock API。`QuietZoneCalibration` / `ProbePattern` / `MultiFrequencyPathLoss` 三张结果表无 warnings，现有报告链也不消费。因此本片不得宣称“操作员/API/报告已可见”；后续若正式启用这些校准流程，应先设计 real 模式授权与硬件安全门，再分别补 API/GUI 选择、nullable warnings 留痕和报告渲染，不能只翻转 `use_mock`。
- ~~`[discovered 2026-07-04 during #206 补扫]` **[→ 提升 P3-19 (2026-08-02)]** **校准 warnings 的 DB 持久化断层（wire 已通,证书不留痕）**~~ ✅ **P3-19 warnings 持久化子片已收口** —— `ProbePathLossCalibration.warnings` 以 nullable JSON 落库，迁移前历史保持 `NULL=此前未记录`；legacy 与 lab/topology 两个 live 证书写点均精确保存 `CalibrationResult.warnings`，`/latest` response 与两条校准报告数据收集路径继续带出；RF-chain uplink/downlink 与 multi-frequency 三个失败 detail 统一为 `{message,warnings}`，成功响应也不再丢 warnings。
- `[discovered 2026-08-11 during PR #335 Codex 外审]` **[P2 / mock 契约，不阻塞] 报告模板 mock summary 未完全复用后端生成契约** —— `/reports/templates` handler 已恢复活动 `TemplateListResponse` 包层，但 fixture 仍用非 UUID id 且缺后端必填 `version`；真实后端响应保证二者，mock 下可能让消费方接受无效 id / undefined version。按 P2/P3 一轮止损规则只登记一次，不回开 #335；后续处理 mock 契约时应直接改用生成类型，不再复制 feature 手写 summary。
- ~~`[discovered 2026-07-04 during Codex 兜底 R10]` **F64 11 站点 `_check_errors` 只 log 的同型假成功平行族**~~ **✅ done 2026-07-05**:9 个参数设置方法 (`set_path_loss / set_doppler / set_baseband_power / set_external_attenuators / set_output_path_loss / set_output_gain / set_crest_factor / set_input_measurement_mode / set_burst_trigger_level`) + `upload_asc_files` 全程加载门 + `set_channel_model` CENT 段全部换 `_gated_write_transaction` (锁事务 drain → 写 → `_first_error` 门)。被拒 → False + `logger.error` (经 `ContextFilter`+`JsonFormatter` → `logs/*.jsonl` → `/system-logs/tail?level=ERROR` → GUI `ZoneLogsAlerts` 面板, 操作员可见 —— 链路契约有测试固化)。`_check_errors` 已退役删除 (它的"只 log 不判定 + `while True` 无上界"是假成功根源)。新 `test_f64_check_errors_family.py` (clean/被拒 各 9 参数 + upload 门 + CENT 门 + GUI 日志链路 + 事务原子性)。校准补偿链 (set_path_loss/set_output_gain) 与 Pipeline B 加载 (upload_asc_files, P0-8 母题) 的真硬件假成功至此堵死。
- ~~`[discovered 2026-07-05 during #202 兜底门审]` **[→ 提升 P3-19 (2026-08-02)]** **UXM SOCKET 终止符判定大小写敏感（P3,pre-existing）**~~ ✅ **P3-19 UXM SOCKET 子片已收口** —— 初次 `connect()` 与 `_silent_reconnect_visa()` 两个资源打开点均对 VISA resource token 先 `.lower()` 再识别 `socket`，小写/混合大小写资源不会再漏掉既有 LF read/write termination；资源串原值仍交给 PyVISA，SCPI 命令与仪器业务状态均未改变。两条执行级回归分别保护初次连接与静默重连。
- ~~`[discovered 2026-07-04 during R6 终审]` **[→ 提升 P3-19 (2026-08-02)]** **UXM ARFCN custom 旋钮三条 P3 加固**~~ ✅ **P3-19 UXM ARFCN 子片已收口** —— attach 的 GUI schema 与 runtime fallback 改为共用 `ATTACH_CONFIG_DEFAULTS`；`nr_band_arfcn_map` 在驱动加载时统一大写 band 键与整数 ARFCN，大小写别名值冲突、非整数/布尔/域外值均立即 `ValueError`，整数字符串归一为 `int` 后再供下发和频率身份读取。没有新增或修改 SCPI。
- `[discovered 2026-08-11 during P3-19 UXM ARFCN 内审]` **[P2 / 测试，不阻塞] custom map 的 NR-ARFCN 域界保护未被定点回归直接锁住** —— live 已在驱动加载时拒绝 `<0` / `>3279165`，但本片参数化只覆盖文本、非整数浮点与 bool；若未来误删域检查，现有 focused 仍可能全绿。按测试规则只登记一次，不在本轮追加外审循环；后续可把 `-1` / `3279166` 加到同一参数表。
- `[discovered 2026-08-11 during PR #334 Codex 外审]` **[P2 / 测试，不阻塞] attach shared-defaults 定点只比较 schema，未直接观察 run fallback 引用** —— 外审确认运行功能正确，但若把 `run()` 改回同值硬编码，当前共享源测试与既有 baseline dispatch 都可能保持绿色。按测试意见一轮止损规则登记，不在 PR #334 启动第二轮；后续如处理，应用可变 sentinel/执行级注入证明 runtime 确实从共享源读取。
- `[discovered 2026-07-31 during P2-11 现场使用]` **[→ 提升 P3-14 (2026-08-01)]** **GUI 频率输入/显示粒度粗于 NR ARFCN 栅格（母题枚举, TestCase 表单已修, 其余待收）** —— TestCase 表单「中心频率」此前 GHz 3 位小数 = 1 MHz 粒度, ARFCN 636666 (3549.99 MHz) 写不进, P2-11 频率一致性门必红 (实证只能绕道 PATCH API); 已改 MHz 3 位小数 = 1 kHz 全栅格覆盖。**同病待修**: ① `ChannelAssetForm.tsx` 的「中心频率 (GHz)」NumberInput (4 位小数 = 100 kHz 粒度, 资产登记自己就够不着 15 kHz 栅格点); ② `CustomCDLProfileManager.tsx` 的「中心频率 (GHz)」NumberInput; ③ 显示端 `ChannelWorkbench.tsx` (`toFixed(3)`/`toFixed(4)` GHz) 与 `CustomCDLProfileManager.tsx` (`toFixed(3)` GHz) 会把 3549.99 MHz 显示成 3.550 GHz (显示端说谎, 跟 `feedback_effective_end_not_nominal` 同母题); 修法同款 (MHz 口径 + 1 kHz 粒度); ④ `TestCaseLibrary.tsx` 用例卡片显示行级 `frequency_mhz` 派生列, 而 GUI 保存链只 PATCH `configuration` 不回同步该列 → 新表单改频后卡片显示 stale 旧频率 (内审 F1; 收口时修法是换源 —— 卡片改从 `configuration.frequency_hz` 派生显示, 别加同步机制)。**方向⑤ (体验升级, 需小设计稿)**: 绑定信道资产时频率/带宽从资产声明带出免手抄 —— 符合 declared > inferred 架构 (docs/architecture/testcase-driven-instrument-config.md), 但要定"预填可改 vs 锁定"语义; 现有 resolver `scd_freq_identity` fail-loud 网已兜住错配, 不修只是费手不失真。
- `[discovered 2026-07-31 during P2-8 tail 过滤语义修复]` **[→ 提升 P2-19 (2026-08-01)]** **主控台日志面板多选/默认态仍是 P2-11 失效模式（GUI 跟进,P2）** —— `/system-logs/tail` 已改"扫描中过滤",但 `ZoneLogsAlerts` 只在**单选一个 level** 时才下推 `level` 参数;默认三 chip 全开或 WARN+ERROR 双选走无过滤路径(最新 200 原始行+客户端过滤),低频失败行照样 ~48s 被冲出。修法=多选时逐 level 各发一次请求合并去重(零后端契约变化);同批顺带把 `total_lines_read` 显示成"已扫 N 行"(触顶时"无匹配日志"是假阴性,SystemLogViewer 已展示该字段,面板未展示)。
- `[discovered 2026-07-31 during P2-8 tail 过滤语义修复]` **[→ 提升 P3-19 (2026-08-02)]** ~~**tail 反向扫描字节上限缺失（P3,pre-existing）**~~ ✅ **已由 P3-19 首片收口** —— `_scan_reverse_entries` 现在以 16 MiB 单请求字节预算同时约束 `/tail` 与 `/history`；预算内找不到可推进的安全换行边界时明确返回 422，不整读损坏/巨行文件，也不生成原地打转的游标。
- ~~`[discovered 2026-08-11 during P3-19 首片 Codex 外审，P2，非本轮阻塞]` **字节预算可能从父 ERROR 行前切断超大 traceback 续行组**~~ ✅ **P3-19 traceback 逻辑组子片已收口** —— 当一组 RAW traceback 续行自身超过 16 MiB、反向扫描尚未找到父行时，tail/history 共用扫描器直接返回 422；不再返回空页并推进游标，也不会把父行与续行拆到不同页后静默丢失前半组。
- ~~`[discovered 2026-07-31 during P2-8 tail 过滤语义修复]` **[→ 提升 P3-19 (2026-08-02)]** **正式执行失败告警通道**~~ ✅ **P3-19 最后一片收口** —— `test_case_runner` / `commissioning_api` 正式执行进入终态 `failed` 后生成一次 `execution_failed` active Alert，右侧摘要下一轮轮询即可计入；执行状态先提交，告警独立事务失败不改写真实终态，已处置的同一执行告警不会重开。调试、废弃、VRT 与 KPI 不通过明确排除。原 app.log namespace 判断已证实 stale 并删除；面板 `lines=200` 的可调性仍只是独立体验候选。
- `[discovered 2026-08-01 during VRT 摘要 channel_model 换源修复]` **[→ 提升 P2-20 (2026-08-01)]** **标准场景库 5 处 `channel_model=` 死 kwarg（P3）** —— `app/data/scenario_library.py` 给 Environment 传的 `channel_model=ChannelModel.*` 被 Pydantic `extra='ignore'` 静默吞掉,标准场景 `channel_snapshots` 恒空 → 场景库列表里标准场景的信道模型列恒 None。修法=把这 5 处改成 `channel_snapshots=[ChannelSnapshot(channel_type="3GPP", standard_model=..., ...)]`;`tests/test_data.py` 的 environment 也还在用旧 `channel_model` key,同批一起换。
- `[discovered 2026-08-01 during VRT 摘要 channel_model 换源修复]` **[→ 提升 P2-20 (2026-08-01)]** **channel_model 死字段其余读/写方 3 站点（同母题清单, P3）** —— 内审全量扫出摘要行之外还有: ① `road_test.py::_generate_execution_report` 的 `EnvironmentInfo` 构造用 `get_attr_or_item(env, 'channel_model', '')`,tolerant 默认让它不崩但**恒空串**(live 路径: 列表显示 CDL-C、同场景报告显示空,两读方不同源),修法同款换源 `channel_snapshots[0].standard_model`;② `ota_scenario_mapper.py` 5 处读 `scenario.environment.channel_model`(当前全仓零调用方的死代码,任何人接线即 100% AttributeError);③ GUI 写侧 `CreateScenarioDialog`/`EditScenarioDialog` 恒发 `channel_snapshots: []`,表单选的 channelModel 只进 tags → GUI 建/编场景摘要 channel_model 恒 null、Edit 预填恒回落 'UMa',快照真值今天只有 API 直发能写。三处与标准库死 kwarg(上条)同母题,宜同批收口。
- `[discovered 2026-08-01 during VRT 摘要 channel_model 换源修复]` **[→ 提升 P2-20 (2026-08-01)]** **`_list_custom_scenarios` 单行坏配置会 500 全列表（P2）** —— `road_test.py` 列表推导逐行 `vrt_test_case_to_scenario`,任何一行 DB configuration 过不了 `VirtualRoadTestConfig.model_validate`(如旧 schema 遗留行)就 ValidationError 冒泡,整个 `/road-test/scenarios` 500,全部场景消失。比摘要降级更烈的全灭模式,与"场景数==摘要数"不变量门同母题;修法待设计(逐行 try + 降级出行 or 显式隔离坏行报表),注意别静默丢行。
- `[discovered 2026-08-02 during P1-28 triage 前置验证]` ~~**依赖静默升级打瞎规则门取数, G6/G8/G11 三门同时假红且归因错误**~~ ✅ **已修 (同批, 本 PR)**: `requirements.txt` 写 `fastapi>=0.115.0` 开放上界, 2026-08-02 19:45 一次安装拉到 **0.141.1 + starlette 1.3.1**; 新版 `include_router` 改懒加载 (`_IncludedRouter`, 子路由不再展平进 `app.routes`) → `_live_route_table()` 当场只拿到 **9 条** (真实 320) → G6 喊"用例链路由被误删"、G11 把 **44 条活引用**判成死 —— **假红且归因指向错误方向**(业务代码零问题, `app.openapi()` 251 paths 全在)。修法按 换源 > 加机制: ①取数换递归展开 `_expand_app_routes` (保真且含 WebSocket, 320 条 vs openapi 251) ②加 openapi 交叉自检 —— **取数源坏掉要自己喊出来**, 不能交残表让上层门瞎判 (变异实证: 展开器失效时门喊"取数源失效"而非"路由被误删") ③G11 里第二个会瞎的 WS 取数点删除 (取数统一到一处) ④requirements 钉 `<0.142.0` 上界 + 注释写明再放版前先跑规则门。全量 2867 passed / 0 failed。
- `[discovered 2026-08-02 during 环境恢复/暗室激活溯源]` **[→ 提升 P1-28 (2026-08-02)]** **「当前暗室」双真值源漂移: active chamber ≠ active lab 绑定暗室（~~P2~~ → **P1**, 见行尾实证补录）** —— 实测 DB: `ChamberConfiguration.is_active` 指「3GPP 16 Probe Dual」(2026-06-08 事故善后手动激活), 而唯一 active lab `CAICT-Lab-1.chamber_config_id` 指「CAICT-16-Probe-Dual」(2026-05-13 现场创建时绑定, 此后无人回头更新)。根因: 两个字段同名不同义 (`chamber.is_active` = activate 端点强制唯一的"当前工作暗室"单选器; `lab_profile.is_active` = 软删除标志, 默认 True), 且 lab 绑定与暗室激活之间**零约束零同步**。消费方分两派: `commissioning` / `mimo_ota/factory` / `trp/factory` 走 `resolve_lab_profile` → lab 绑定暗室 (解析出 CAICT 行); `chamber.py` 列表默认过滤 + `workflow_engine` `probe_ids="auto"` 走 `chamber.is_active` (解析出 3GPP 行) —— 同一时刻两派拿到不同 chamber 行。今天两行几何相同故无可观察故障, 但**校准数据按 chamber_id 键控** (`path_loss_calibration` 写入/`GET /latest/{chamber_id}`) → 校准存在 A 行、执行链按 B 行查 = 校准查不到或查到错的, 是静默失配。修法按 去掉>换源>收窄>加机制: 推荐**去掉**双真值源之一 (「当前暗室」:= active lab 所绑暗室, `chamber.is_active` 退役或降为派生只读显示), 两派消费方换源统一走单一 resolver; 最次才是 activate 端点双写同步 (双写自身会再漂)。配套门: 不变量门 (全仓解析"当前暗室"的代码路径 ⊆ 单一真值源, `test_rule_gates.py` G 门同款结构断言) + 诊断序列里加 DB 两值一致性校验 fail-loud。 **⭐ 2026-08-02 dev 库实证补录 (提升 P1-28 时抬档 P2→P1 的依据, 修的时候不必重查)**: ① 失配**已经发生**而非将来时 —— `chamber.is_active` 指的「3GPP 16 Probe Dual」(`1b531e5c`) 在**所有校准表里零行**, 按 active chamber 查校准今天就查不到; ② 校准行实际分散在两个 id: `59c73fbe` (active lab 绑的 CAICT-16-Probe-Dual — rf_chain 6 / channel_phase 6 / probe_path_loss 7) 与 `b7cd8de0` (calibration_baselines 1 / probe_path_loss 2 / rf_chain 1); ③ **`b7cd8de0` 这个 chamber 行已不存在** = 孤儿引用, 根因是**校准类表全都没有指向 `chamber_configurations` 的外键约束** (现存 FK 仅 `probes` / `probe_configurations` / `switch_topologies` / `lab_profiles` 四条), DB 层拦不住; 三个非 active lab 绑的 `06ca91a2` 同为孤儿。故正式条目把校准表 FK / orphan 巡检列为同批收口候选。

- `[discovered 2026-08-07 during P1-28 TDD]` ~~**`POST /workflows/execute` 的探头校准步骤必然在服务构造处崩溃**~~ ✅ **已并入 P1-28 收口（内审 F1 判为真值源端到端阻断项）** —— 没有补同名空壳；已改接现有 `AmplitudeCalibrationService` / `PhaseCalibrationService`，API 通过线程池隔离同步 executor 的 `asyncio.run()` 边界，映射 `CalibrationResult` 并将唯一 resolver 得到的 `chamber.id` 传入落库。新增直调 executor 与 live API 两层回归，都校验实际校准行归属所选 LabProfile 暗室。

- `[discovered 2026-08-11 during P1-27 入口全集审计]` **`CalibrationOrchestrator.export_calibration_data/import_calibration_data` 仍按已删除的逐探头列读写当前聚合 `ProbePathLossCalibration`（待 triage）** —— 方法访问/构造 `probe_id`、`polarization`、`path_loss_db`，而当前模型权威字段是聚合 JSON；全仓没有这两个 orchestrator 方法的 live API 或调用方。照现状调用会在导出属性访问或导入构造时失败，但它不是 P1-27 的 live 校准生成入口，不能为“顺手传播 provenance”先修一条无人消费的坏死链。后续先裁决删除还是按当前聚合包重写，再决定是否进 roadmap/backlog。
- `[discovered 2026-08-10 during P1-48 第 5 片外审]` **给「真假标注上线前归档的旧报告」挂警示 —— 整条支线撤回，重做时按下面三个洞设计（P2）** —— P1-48 第 5 片里我加了这条支线，外审连查三轮、每轮的洞都是上一轮修复引入的，最后**整条撤掉**（修法优先级「去掉 > 换源 > 收窄 > 加机制」的第一档）。⚠️ **实际影响面当时为零**：库里 214 份报告全是 `single_execution`，一份虚拟路测报告都没有 —— 这个机制从头到尾是防将来的，却消耗了三轮外审。重做前先问「现在有这类数据吗」。
  **踩过的三个洞（重做时逐个避开）**：
  ① **判据别按「形状」猜** —— 第一版按「有数值 pass_rate + 无 provenance + 结论 passed/failed」判新旧，而 **214 份真报告的形状恰好全部命中**，会把全部真数据标成「未经验证」（反方向的假信息，比不加更糟）。改用 `road_test_execution_id` 非空才算虚拟路测报告。
  ② **判据别取客户端能写的数据** —— 换成 `road_test_execution_id` 之后，判「新/旧」仍看 `content_data`，而 `POST /reports` 允许调用方塞任意 `content_data`：加一个 `pass_rate: null` 就能自称「已标注」绕过警示。真值源必须是服务端拥有的执行记录，不是报告创建者的自述。
  ③ **警示要挂在真正走得通的出口上** —— 试过三个出口，**一个都不通**：(a) `GET /reports/{id}` 的 JSON 字段 —— 归档报告在 GUI 里进不了 `ReportViewer`（`ReportsPage.tsx:93` 挂 `<ReportList />` 不传 `onView`，而「查看」按钮由 `{onView && ...}` 守着），照不到人；(b) `/download` 的响应头 —— 被前端 `downloadReport()` 的 `response.data` 当场丢掉；(c) 改成 409 拦下载 —— 文件是拦住了，但 axios `responseType:'blob'` 把错误体也变成 Blob，`ReportList.tsx` 只显示 `error.message`（"Request failed with status code 409"），**操作员看不到为什么**。
  **附带的独立缺陷（可单独做）**：GUI 缺「查看归档报告」入口（上面 ③a），从报告列表只能下载不能看。同族问题值得一并扫：还有多少后端字段是「加了但前端没有消费方」。

- `[discovered 2026-08-19 during P1-57 内审]` **Dashboard readiness 的 lab_profile 灯位仍走后端 unique-active 隐式解析，与 header 显式选择各说各话（P3）** —— `api-service/app/services/readiness.py`（≥2 活动 lab → `status="ambiguous"`）与 `gui/src/features/Dashboard/ZoneReadiness.tsx` 不认浏览器的全局 LabProfile 选择。P1-57 把「多活动 lab + header 显式选一个」变成常态后，该灯位会常驻 ambiguous。P1-57 的全集判据是 grep GUI 的 `fetchLabProfiles` 调用方，抓不到这类「后端隐式解析」消费面 —— 同族值得一并扫。修法方向：readiness 收显式 lab_profile_id（换源）。

- `[discovered 2026-08-21 during P2-29 全量回归]` **全量测试自 2026-08-18 起在本机挂死 + 一条遗留顺序失败（P2，两件事）** —— ① `ef33d00`（P1-56）移除 Aerotech 静默重连的握手后，P1-47A 的 `test_aerotech_reconnect_cancel_closes_half_initialized_transport` 把同步点挂在被移除的 `_tx_rx` 上 → **确定性死锁**（单跑/合跑/全量一律卡 84%，CPU 0%）——即 08-18 后没有任何人真正跑完过全量；**已在 P2-29 分支按现契约重写该测试（顺带修，`538e51b`）**。② 修活之后暴露：全量里 `test_p1_36_execution_id::test_no_execution_means_default_not_empty` 失败 —— `current_execution_id` 上下文变量被按字母序更早的文件（commissioning 端点测试，`api/commissioning.py:539` 的 `set`）泄漏，「无关日志行应为 `-`」被标上别人的 execution UUID；**main 基线复现同一条失败**（跳过死锁测试后 1 failed / 4059 passed），与 P2-29 无关。47C 的 `_execution` 帮手同样 set 后不还原（P2-29 的测试文件已自净，`af77111` 的 fixture 可直接抄）。修法待 triage：给泄漏源补 token reset，或做成全套件 autouse 隔离 fixture；顺手可加一道「测试文件不得裸 set 该变量不还原」的门。

---

## 📊 Summary

> ⚠️ **本块是 2026-06-06 的历史快照，不再随后续变动维护**（Codex #255 R2 降级：
> 快照后 P1-19~21/P2-15~17/ARCH-1 等已完成、2026-08-01 又提升 8 个 open 项，逐点追数字
> 必漏 —— 现势唯一真值源 = 顶部 Current Focus（本地队列与当前片）+ 各 P 区条目/表状态，
> 别读下表判断现状）。快照当时口径：本地队列已基本清空；P2-7 promote 到 P1-10 计非 open；
> 历史复盘见 [`project-retrospective.md`](project-retrospective.md)。

| Priority | Count | Total estimate | On-site share |
|----------|-------|---------------|---------------|
| ✅ Done | 36 | — | — |
| 🔴 P0 (first-call critical) | 4 open / 8 total | ~6 days | ~4.5 days |
| 🟠 P1 (confidence) | 5 open / 17 total | 见各 section | 见各 section |
| 🟡 P2 (abstraction debt) | 6 open / 13 total | 见各 section | 见各 section |
| 🟢 P3 (polish) | 0 open / 13 total | 0 | 0 |
| **Total open** | **15** | 见各 section | — |

---

*This roadmap is a living document. Update Current Focus, append to
backlog, mark items done. All changes go through git so we have an audit
trail of what we said vs what we did.*
