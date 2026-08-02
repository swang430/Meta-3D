# MIMO-First — First-Call Roadmap

> **Single source of truth for what we're working on next.** All non-trivial
> development MUST reference an item on this roadmap. Off-roadmap work needs
> explicit justification (see [governance rules](#governance-rules) below).

---

## 🎯 Current Focus

**当前状态 (2026-08-01)**：ARCH-1 整案收官（S1–S6 全 ✅，见下方 ARCH-1 表）。现场 P0 仍
blocked（P0-5 / P0-8 现场半，见 Blocked on hardware 表）。2026-08-01 用户拍板本地队列：
**六项自 Discovered 区按既定 triage 出口提升为正式 P 编号 + 两项门候选直接立项**
（P3-16/17，无 Discovered 来源条目）。**执行顺序与当前片记在本段，完成状态在各 P 条目/表处**：
**2026-08-02 二批本地队列已拍板排序（用户明示"只排好优先级，先不忙开工"——待开工指令）**：
**P1-25 → P1-26 → P1-27 → P2-22 → P2-23 → P2-24 → P3-18 → P3-19**（逐片 WIP=1，全流程照旧）。一句话索引：
- **P1-25** GUI 主控台"系统状态"面板恒空修复 + api.ts 手写镜像同尺审计
- **P1-26** GUI 改频同步 component_carriers（执行侧错频收口）
- **P1-27** P1-8 校准门拒 mock cert（provenance + real 模式 strict 拒）
- **P2-22** F64 disconnect 冷缓存判 GOS 换真值源（涉 SCPI 查 NotebookLM）
- **P2-23** 会话资产 is_active 预检 + measure resolver 同病排查
- **P2-24** 测试用例契约补 lab_profile_id（契约四步）
- **P3-18** 门/测试精化批（G11 三覆盖面 / p08 零残留站点 / PDF 转义收口 / 诊断序列串行化）
- **P3-19** 日志/告警/留痕卫生批（tail 上限 / app.log 噪声 / 校准 warnings 持久化+清理警告可见 / UXM 两组 P3）

**2026-08-01 拍板的本地队列 10/10 全部收口**（P1-22 ✅ #256 / P1-23 ✅ #257 / P2-19 ✅ #258 / P2-20 ✅ #259 / P1-24 ✅ #260 / P2-21 ✅ #261 / P3-14 ✅ #262 / P3-15 ✅ #263 / P3-16 ✅ #264 / P3-17 ✅ done 本 PR）。**当前无本地 in-progress 片；P0 队列全部 on-site-blocked（见 Blocked on hardware 表），下次现场即回队首。** 原顺序备查 **P1-22 → P1-23 → P2-19 → P2-20 → P1-24 → P2-21 → P3-14 → P3-15 → P3-16 → P3-17**
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
**提交前 pre-commit-reviewer agent 硬门**（`.claude/agents/pre-commit-reviewer.md`,Codex limit
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
> 「🚧 Blocked on hardware (P0 queue for next on-site)」段的表。
> 本条目只说两件确定的事：
> ① P0-3 / P0-4 **已 2026-07-03 现场完成**（见「Blocked on hardware」表里那两条删除线行）；
> ② 下次现场的**主线**是 P0-5（DUT attach → bearer → PDSCH）。
> **"只剩 P0-5"是错的** —— 还有 **P0-8 的现场半**（real F64 上 load→run→改参全 0
> error + 输入口变绿 + DL 不失真，见 `### P0-8` 条目），跟 attach 是同一台 F64、
> 同一段窗口的活。⚠️ 「Blocked on hardware」表**此前漏列 P0-8**，本 PR 一并补上 ——
> 否则"权威表"和 `ON-SITE-BLOCKED` 行会各说各话（Codex #249 抓到）。
> ⚠️ 本文上方 2026-06-21 那段写的"切回依赖链 P0-4 → P0-3 → P0-5"**写于 P0-3/4 完成之前，
> 已 stale**，别照它安排现场（清理它属 07-03 现场记录的收口，不在本条目范围）。


P2-14 的**现场验证半**(V1.0 §9：.tap schema / gaussian 谱 / f_upd_max / RT→MPC 接入)
已进 on-site 队列。**原开发的现场验证基线已打 tag** `onsite-verification-baseline-2026-06-21`（留在 main）。
**下次现场** (校准天线 / SGH / 真 DUT 到位) Current Focus **必须从该 tag 切回依赖链 P0-4 → P0-3 → P0-5**
（见下方「🚧 Blocked on hardware」段 + [`guides/on-site-debug-protocol.md`](guides/on-site-debug-protocol.md)），
现场只调硬件、不写 driver 代码；P2-14 现场验证可在 P0 链路间隙穿插。

> **完整项目历程** (第一次现场 → 现在的全程 + 5 条主线) 见
> [`project-retrospective.md`](project-retrospective.md)；**现场经验文档归类**见
> [`field-experience.md`](field-experience.md)。Current Focus 不再堆叠历史快照 (已迁出至
> retrospective，git 保留全量审计轨迹)。

### 📋 可规划工作 audit (除现场工作外还能规划什么 — 2026-06-06)

按"能否本地、现在做"分桶：

| 桶 | 内容 |
|----|------|
| **LOCAL-OPEN (roadmap 内)** | **P1-25 → P1-26 → P1-27 → P2-22 → P2-23 → P2-24 → P3-18 → P3-19**（2026-08-02 拍板二批队列，**待开工指令**；一批 10 片已全收 #256–#265）|
| **ON-SITE-BLOCKED** | P0-5 (P0-3/4 已 2026-07-03 现场完成) + P1-2 + P1-4 + P2-4，以及 P0-8 / P1-5 / P1-17 / P2-9 / P2-10 / P2-12 / P2-13 的现场半 (详见下方「Blocked on hardware」) |
| **HOLD** | P1-6 现场半 (真 idle-close 复现验证；本地测试覆盖已补 #149) |
| **已决策不做 / 保持现状** | `#2000` (依赖 #2001(2) → 连带搁置) / `#2001(2)(3)` / `#2002` |
| **off-roadmap 候选 (需先 triage，非积压)** | GUI 测试框架引入 (与 `feedback_browser_test_frontend_work` 对齐，ROI 最高) / HTTP distributed pytest 缺口 / 后端告警规则引擎 / CLAUDE.md 列的 Queue 重排序·Auth Context·报告对比 |

> ⚠️ off-roadmap 候选是"可做"不是"应做"：多为显式 deferred、无 demonstrated problem。**不因
> "本地队列空了"就拉进来**；按价值由用户排 (per memory `feedback_dont_manufacture_decisions_no_problem`)。

- **WIP limit: 1.** 同一时间只允许一个 Current Focus 项 in-progress。
- 非 Current Focus 且非琐碎 (<30min) 的发现进 backlog，不 inline 做。

Last review: 2026-06-07 (校准 chamber-scoping foundation; #155 Codex P2 (1) 基础版收口)
Baseline commit: see [announcement](announcements/2026-05-14-roadmap-baseline.md)

---

## 🚧 Blocked on hardware (P0 queue for next on-site)

| ID | Item | Blocker |
|----|------|---------|
| ~~P0-3~~ | ~~Path-loss calibration loop closure + cal cert~~ | ✅ 2026-07-03 现场完成 (余复测 ±0.5dB → P1-4) |
| ~~P0-4~~ | ~~SignalAnalyzer in HAL for reference TRP~~ | ✅ 2026-07-03 现场完成 |
| P0-5 | DUT attach → bearer → PDSCH on UXM 5G NR | on-site real DUT (已至 -96 dBm RSRP, 差正式注册) |
| P0-8 **现场半** | F64 driver 现场修复落地 —— real F64 上 load→run→改参全 0 error + 输入口变绿 + DL 不失真 | on-site real F64 (本地半已 Done, 见 `### P0-8`；跟 P0-5 attach 同一段窗口) |

These are still the highest-priority items overall — they just can't
be progressed from a remote dev box. When the next on-site trip
opens, the Current Focus must move back to P0-5 (or whichever P0 is
unblocked) BEFORE starting any new P1.

> ⚠️ **P0-5 是主线，但不是当天唯一的 P0 活** —— P0-8 的现场半（上表最后一行）
> 需要同一台 real F64，排窗口时一起算。两者都在「📋 可规划工作 audit」的
> `ON-SITE-BLOCKED` 行里；本表此前漏列 P0-8，2026-07-30 补上。
>
> ✅ **协议已覆盖 P0-8（P1-23，2026-08-01）**：Phase 1.5 = P0-8a gate
> （load→run→改参 + 输入口电平，载体 `propsim_f64_p08_gate` 序列 —— **序列本身
> 待写，已列入协议 §2 出发前硬门槛**），Phase 4 gate 清单含 P0-8b（DL 非 0% ACK）。
> 此前"协议不覆盖 P0-8、需手动排入"的告警随 P1-23 作废。

> **下次现场执行按 [`docs/guides/on-site-debug-protocol.md`](guides/on-site-debug-protocol.md)
> 走**（现场首测调试协议）。当天 P0 队列以上方「Blocked on hardware」表为准
> （协议自 P1-23 起不再硬编码队列），Phase 结构 = 网络 → 握手 → **F64 信道链
> (P0-8a)** → SA → 校准 → DUT attach(P0-5+P0-8b) → 真 first-call，gate 标准 =
> 各 P0 的 acceptance；并固化 CAICT 教训: 出发前硬门槛 + 铁律「现场不写 driver
> 代码」+ timebox 救火 + 收工 review + retro 喂回本 roadmap。

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
3. **Mid-task discoveries → backlog, not detour.** Append to the
   "Discovered during X" section at the bottom of this file with a
   one-line note + date. Triage to P1/P2/P3/dropped at the next weekly
   review.
4. **No "顺手优化".** Mess is not a bug. If it doesn't make the current
   P0 easier, it's a P3 entry, not inline cleanup.
5. **Codex / review fixes that are not on the critical path** get their
   own commit on the next P0 branch, not a separate detour PR — unless
   they block merge.
6. **Periodic review (weekly).** Three questions:
   - Last week's focus was X — what did we actually do?
   - How much did we drift (0% / 30% / 100%)?
   - If we drifted, which of rules 1-5 broke?

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

### P0-5 — DUT attach → bearer → PDSCH on UXM 5G NR 🚧 Blocked on-site

**What**: Put a real DUT in the chamber, attach it to UXM via SIM + RRC,
establish a default bearer, push PDSCH traffic, and read back actual
throughput. The MEASURE phase needs this to compute real RSRP/SINR/Tput.

**Why**: Today the Measure executor simulates RSRP and SINR (the BS
doesn't report them via SCPI). Throughput is real *if a DUT is attached*
— but we never closed the attach loop on-site.

**Acceptance**:
- POST /test-executions/{id}/attach-dut succeeds, records IMSI + RRC
  state
- UE Capability query returns `max_dl_layers >= configured layers`
- One azimuth sweep produces a non-zero throughput reading from UXM
- 4-azimuth sweep gives 4 distinct throughput values (sanity: rotation
  is changing the link)

**Status**: `[ ]` not started — UXM 5G NR profile already supported (PR #10)

> **5/27 现场部分重现 (非验收)**: DUT 经 SCPI 控制的 UXM + F64(3600M/N78) 稳定 **CONN + DL live**,
> 但吞吐 **0% ACK / all-NACK** (DUT 收到但解不出 PDSCH) —— 根因是 F64 输入信号参考/crest 没设对
> 致 DL 失真 (见 P0-8), **不是** attach 链路问题。`attach-dut` 端点的 `query_ue_capability` 在
> LTE_NR_IRAT profile 上不支持 (走 Swagger 手动)。**转台 (Aerotech) 4 方位扫今天未做** (转台本身
> 测试无结论, 见 U-5)。真验收 (非零吞吐 + 4 方位不同值) 仍待 P0-8 输入参考闭环 + 真 DUT + 转台。

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

### P1-25 — GUI 主控台"系统状态"面板恒空修复 + api.ts 手写镜像审计 ⬜（2026-08-02 拍板，待开工）

**What**: `App.tsx` 读 `dashboardData?.systemStatus`（手写 camel 三键，`gui/src/types/api.ts`）而 live `/api/v1/dashboard` 返回 snake 四键 → 面板恒 undefined 走空态。修 = App.tsx/api.ts 换 live 键形态；同一把尺子过 api.ts 其余手写镜像类型 + 清理死导出 `InstrumentCategoryResponse`。**来源**: P3-17 内审 F2（[→ P1-25] 已标）。
**Why P1**: 用户天天看的主控台面板对真后端是坏的 —— 可见度最高的存量缺陷。

### P1-26 — GUI 改频同步 component_carriers（执行侧错频收口）⬜（2026-08-02 拍板，待开工）

**What**: factory `model_dump` 落库自带 CC，validator 在 CC 非空时忽略顶层频率（measure 权威 = CC[0]），而 GUI `MIMOOTAConfigForm` 只写顶层 → 顶层与 CC[0] 漂移时执行按旧 PCell 跑。P3-14 已让显示与执行同源（CC[0] 优先），本片修执行侧写路径：GUI 写侧同步 CC[0] 或 PATCH 时 drop CC 重构造（实现期定）。**来源**: Codex #262 R1（[→ P1-26] 已标）。
**Why P1**: "用户以为改了新频、硬件跑旧频"是现场误导级；P2-11 一致性门兜不住"CC[0] 旧频恰与 SCD 一致"的形态。

### P1-27 — P1-8 校准门拒 mock cert（provenance + real 模式 strict 拒）⬜（2026-08-02 拍板，待开工）

**What**: cal 记录带 `use_mock` provenance 标记；real 模式 precheck strict 门拒 mock cert（门现在只查存在/频率/时效）。**来源**: 2026-07-03 现场实证（[→ P1-27] 已标）—— mock 路损 cert 在 real 模式 `cal_pass: true`，真测静默应用 mock 补偿值。
**Why P1**: 现场实证穿透，下次现场前必修（runtime-gate-not-frozen-snapshot 同母题）。

---

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

### P2-22 — F64 disconnect 冷缓存判 GOS 换真值源 ⬜（2026-08-02 拍板，待开工）

**What**: `disconnect()` 依赖 `_emulation_running` 缓存判"要不要 GOS"—— HAL 重载后冷实例缓存 False 而硬件在播 → 断开跳过 GOS/CLOSE 把发射中的 F64 丢下。换 STATE? 真值（F64R-1 同源判据）。涉 F64 SCPI，动手前查 NotebookLM。**来源**: #206 补扫（[→ P2-22] 已标）。

### P2-23 — 会话资产 is_active 预检 + resolver 同病排查 ⬜（2026-08-02 拍板，待开工）

**What**: `POST /commissioning/sessions` 的资产预检只查存在不查 `is_active`（软删资产可建会话执行退役配置）；预检处判 `asset.is_active` + 顺带查 measure resolver 对 inactive 的行为。**来源**: Codex #262 R2（[→ P2-23] 已标）。

### P2-24 — 测试用例契约补 lab_profile_id ⬜（2026-08-02 拍板，待开工）

**What**: `TestCaseCreate`/`TestCaseUpdate` 补 `lab_profile_id`（列在、runner 消费，schema 缺失 → 多 active lab 部署下 GUI 建的用例不可执行且无处补绑）；契约四步 + GUI 弹窗透传。**来源**: Codex #250 P1 遗留（[→ P2-24] 已标）。单 lab 现状不炸故 P2。

---

## 🟢 P3 — Polish / tooling

**17/19 ✅ Done，P3-18~19 ⬜ open（2026-08-02 二批队列，待开工）。** 已完成项的完整 What / Fix / Acceptance 详情已迁出 → [`roadmap-archive.md`](roadmap-archive.md)。速览：

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
| P3-18 | 门/测试精化批（G11 三覆盖面 in=location/curl 动词/schema 类型 + p08 零残留站点参数化 + PDF 渲染管道其余转义入口 + 诊断序列 run endpoint 串行化）——2026-08-02 拍板，各配变异 | ⬜ |
| P3-19 | 日志/告警/留痕卫生批（tail 反向扫描字节上限 + app.log 噪声治理/执行失败告警通道 + 校准 warnings DB 持久化 + 借用 acquire 的清理失败警告可见 + UXM 终止符大小写 + UXM ARFCN 三条加固）——2026-08-02 拍板 | ⬜ |

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

---

## 🗂️ Discovered during X — triage backlog

> Items added mid-task. Reviewed weekly; promoted to P1/P2/P3 or dropped.

- `[discovered 2026-08-01 during P1-23, Codex #257]` **[→ 提升 P1-24 (2026-08-01)]** **写 `propsim_f64_p08_gate` 诊断序列（P0-8a 唯一合法载体，已列协议 §2 出发前硬门槛）** —— 现有 `propsim_f64_state_machine`（前提 .smu 已载、只做 GO/STATIC/GOS）与 `propsim_f64_health`（只读探测、`get_metrics` 恒判成功）都覆盖不了 P0-8a。序列要求：①手册有据 + 生产驱动在用的命令（涉 F64 SCPI，动手前查 NotebookLM PROPSIM notebook）②**前置激活 UXM 满 RB DL**（CE↔BS 协调，无信号 `INP:LEV:MEAS?` 返 -300）③每步后读错误队列 ④电平按合法范围真判定（不是恒成功）⑤**含 bypass 态电平窗口复验**（架构文档 P0-8 硬约束）⑥**含输入参考 AUTOSET 闭环**（`INP:LEV:AUTOSET` 设 avg+crest → 读回 clipping/cut-off 迭代收敛，只读判范围会假绿，Codex #257 R3）⑦mock 跑通列入出发前门槛。代码活，独立小片。⚠️ 本行是第二次登记 —— 前两次 python replace 因 #255 提升标记改变锚文本**静默未命中**（我未 assert 命中数，#256/#257 的 PR body 里"已留痕"陈述当时为假，本次补欠并如实更正）。⚠ 要求②的"返 -300"后经手册查证为哨兵语义不实（-300 是队列里的设备错误码非查询返回值，P1-24 落地时纠错，见正式条目）。
- `[discovered 2026-08-01 during P1-24 内审 F4]` **[→ 提升 P3-18 (2026-08-02)]** **p08 门序列 8 个零残留站点仅 3 个有会红的行为测试**（衰落态测量后 / 中止后 / 旁路态首站间接）—— 变异删其余任一 residue 调用（加载后/AUTOSET 后/GO 后/改参后/进旁路后/退旁路后），泄漏错误被下一个生产原子的 drain 吞掉、19 测全绿。完善形态 = fake 泄漏注入点参数化逐站点打；本片按「枚举进 backlog」只收窄了已有测试的断言锚定。
- `[discovered 2026-08-01 during P1-24, Codex #260 R2]` **[→ 提升 P3-18 (2026-08-02)]** **带动作的诊断序列整体无串行化（run endpoint 层）** —— 两个客户端并发跑同一序列（或与其它 F64 操作并行）时只有单个驱动原子持 `_scpi_lock`，序列整体可交错（load-A → load-B → AUTOSET-A → GO-B），互相污染归档、甚至把对方的增益/旁路态"还原"掉。基建共性（`propsim_f64_state_machine`/`baseStation_attach_check` 同型），非 p08 序列独有；整段持锁会饿死 broadcaster 监控（state_machine 当年显式取舍过），正解大概率在 run endpoint 加序列级互斥。范围外基建债，独立小片。
- `[discovered 2026-08-01 during P2-21 内审]` **[→ 提升 P3-18 (2026-08-02)]** **PDF 渲染管道其余自由文本入口无 XML 转义**（pre-existing，非 P2-21 引入）—— ①封面 `Paragraph(title)` 含 case_name，`<字母` 命名会炸整份报告；②共享步骤区渲染器 `_generate_step_details_section` 的 `val_str` 侧统一转义能让 VRT `step_configs` 管线同受益（P2-21 只修了 report.py 组装侧自己的面）。修法 = 渲染器入口统一 `xml.sax.saxutils.escape`，共享文件独立小片。
- `[discovered 2026-08-01 during P3-14, Codex #262 R1]` **[→ 提升 P1-26 (2026-08-02)]** **GUI 改频只写顶层 frequency_hz，带 component_carriers 的持久化用例执行仍按 CC[0] 旧频率跑**（pre-existing，非 P3-14 引入）—— factory `model_dump` 落库自带 CC，而 `MIMOOTAConfiguration` 的 validator 在 CC 非空时忽略顶层频率（measure Phase 2g 权威 = CC[0]）；GUI `MIMOOTAConfigForm` 不写 CC → 顶层与 CC[0] 漂移时**执行侧**错频（P2-11 一致性门只兜"CC[0] vs SCD 不符"的形态，兜不住"用户以为改了新频、CC[0] 旧频恰与 SCD 一致"）。P3-14 已让**显示**与执行同源（CC[0] 优先），执行侧正修 = GUI 写侧同步 CC[0] 或 PATCH 时 drop CC 重构造，独立小片。
- `[discovered 2026-08-01 during P3-14, Codex #262 R2]` **[→ 提升 P2-23 (2026-08-02)]** **会话创建的资产预检只查存在不查 `is_active`** —— 软删（退役）的 ChannelAsset 仍能通过 `POST /commissioning/sessions` 的 422 预检建会话执行退役信道配置；对称先例 = active-only 列表与 lab-profile resolver 都拦 inactive。修法一行（预检处判 `asset.is_active`，消息说明"已退役"）+ 顺带查 measure resolver 对 inactive 的行为是否同病。
- `[discovered 2026-08-02 during P3-17 内审 F2]` **[→ 提升 P1-25 (2026-08-02)]** **GUI 主控台"系统状态"面板对 live 后端恒空态** —— `gui/src/App.tsx:482` 读 `dashboardData?.systemStatus`（camelCase，`gui/src/types/api.ts` 手写三键），而 live `/api/v1/dashboard` 返回 snake 四键（summary/live_metrics/active_alerts/recent_tests）→ 恒 undefined 走空态分支。P3-17 修了 yaml 契约（判定端），生效端副本在手写 api.ts；修法 = App.tsx/api.ts 换 live 键形态，顺带同一把尺子过 api.ts 其余手写镜像类型 + 清理死导出 `InstrumentCategoryResponse`（service.ts 早已用平铺）。独立小片。⚠ 按行号引用会漂 — 动手时按 `systemStatus` 检索定位。
- `[discovered 2026-08-02 during P3-17, Codex #265 R2]` **[→ 提升 P3-18 (2026-08-02)]** **G11 三个覆盖面精化**（门 docstring 已申报为已知收窄面，声明与覆盖对齐）：①契约半参数比对分 in= location（query 重名 path 参数现在穿透）②散文半动词抽取识别 curl 形态（`curl -X POST http://host/api/v1/...` 动词隔着 host 抽不出）③响应比对拒绝不兼容 schema 类型（yaml 改 object→array 时 y_props 空跳过）。各配变异，独立小片。
- `[discovered 2026-08-01 during P1-22 内审 F3，本行补欠登记]` **[→ 提升 P2-21 (2026-08-01)]** **precheck/reference/measure 的 P1-12 可信化标志渲染不可达 — 报告对兜底数据沉默（P3）** —— `executors/report.py` step_results 里 `quiet_zone_verified` / `trp_verified` / `path_loss_verified` 是顶层键，渲染器只读 `name`/`step_name` 与 `parameters` → PDF 步骤区零显示，P1-12"标注 未验证(兜底值)"意图从未生效。修法同 P1-22 的 analysis 站点（标志挪 `parameters` 下）。顺带同域：`pdf_certificate.py`（校准证书）无 CJK 字体，证书中文同样豆腐块。

- `[discovered 2026-08-01 during ARCH-1 S6 总验, 内审定案]` **[→ 提升 P1-22 (2026-08-01)]** **自动执行报告恒报 failed/0.0% — REPORT 相位读一个从没人写的键（P2）** —— `mimo_ota/executors/report.py` 的 `overall_pass = bool(analysis.get("overall_pass", False))`：analysis 执行器写的是 `verdict`（canonical 字段是 `validation_pass`），全仓**无人写 `overall_pass` 键**（`pass_criteria_summary` 同样无人写）→ 恒 False → 自动报告 `overall_result` 恒 "failed"、`pass_rate` 恒 0.0 —— `.get` 默认值静默吞断层的教科书形态。修法=换判据来源，**精确谓词**（Codex #254 R1 校正）：首选读 `context.test_execution.validation_pass`（TestExecution **列**，analysis 执行器按 `verdict in ("PASS","MARGINAL")` 写入的 canonical 布尔 —— 注意它不在 analysis payload 里，`analysis.get("validation_pass")` 还是恒 None）；若只拿得到 payload 则用 `analysis.get("verdict") in ("PASS", "MARGINAL")`（verdict 取值就这三个字面量）。**绝不 `bool(verdict)`** —— 非空字符串恒 True，"FAIL" 也会判成通过，反向翻车。⚠️ **修法红线**：不得用 `status=='completed'` 当通过谓词 —— 相位机械成功与 KPI 通过是两层（analysis 相位对 KPI FAIL 也返回 SUCCESS），completed 判通过会让失败的测试谎报通过，代价不对称。手动路径（HistoryTab 生成的那份）走 `report_data_collector` 的 `validation_pass` 谓词，**现状正确**——它显示 0.0% 可能是如实报告 mock 环境 KPI FAIL，修自动路径前先分辨两份 PDF。⚠️ `report_service.py` 建 summary 的 `overall_result`/`.get('pass_rate', 0)` 段**不许当残留清理**（Codex #254 R2）：VRT 归档路径（`road_test.py::_archive_execution_report` 传 `ExecutionReport.model_dump()`，该 schema 无 `execution_summary` 键）**仍在消费它** —— 它只是不在用例执行路径上，对 VRT 是活代码。可同 PR 清理的只有报告模板 `Test Plan: N/A` 计划链残留字段。
- `[discovered 2026-08-01 during ARCH-1 S6 总验]` **[→ 提升 P1-22 (2026-08-01)]** **PDF 生成器缺 CJK 字体 — 中文全渲染成豆腐块（P3）** —— 报告标题/正文里所有汉字显示为 ■，中文用例名的报告不可读。`pdf_generator.py`（reportlab）需显式注册中文字体（内置 `STSong-Light` CID 字体或捆绑开源 Noto Sans CJK），并全模板换用（已核实全 `app/` 无 registerFont/TTFont/CID 调用）。
- `[discovered 2026-08-01 during ARCH-1 S6 总验, 内审定案]` **[→ 提升 P2-19 (2026-08-01)]** **执行相位计数对所有行恒 0 — 后端计数谓词 token 错配（P3）** —— `api/test_execution.py` 的 `_to_history_item` 数相位用 `p.get("status") == "completed"`，而 runner 落库写的是 `StepExecutionStatus.SUCCESS.value = "success"` → `phases_done` **全程恒 0**（不是只在终态；"进行中显示正常"是 0/N 初期像正常的观察偏差；失败行徽章正常是 "failed" token 巧合两边一致）。该函数 docstring 自己写的 `completed/failed` 就是错误谓词的种子，一并清。修后端一处，三个消费方（HistoryTab / 主控台最近执行卡 / TestCaseLibrary 执行进度）全好。
- `[discovered 2026-07-31 during GUI 新建入口片]` **[→ 提升 P3-14 (2026-08-01)]** **`TestCaseCreate.test_type` 的 schema 描述漏 `MIMO_OTA`** —— 枚举 `TestCaseType` 里有，但请求 schema description 只列 `TRP | TIS | Throughput | Handover | MIMO | ChannelModel | VirtualRoadTest | Custom`。这段进 OpenAPI，是外部调用方唯一会读的东西。改它要走契约四步；顺带候选：「描述 ⊇ 枚举」可做成会红的门（同 G7/G8 思路，属**加机制**，待拍板）。同片顺带：`template_category` 的 schema 无 `max_length` 而列是 `String(100)`，超长在 PG 直接 500（GUI 侧本片已 `maxLength={100}` 收窄，schema 约束走契约四步一并做）。
- `[discovered 2026-07-31 during GUI 新建入口片, Codex #250 P1]` **[→ 提升 P2-24 (2026-08-02)]** **测试用例 REST 契约无 `lab_profile_id` 字段 — 多 active lab 部署下 GUI 建的用例不可执行且无处补绑** —— `TestCase.lab_profile_id` 是列（runner 执行时传 `source.lab_profile_id` 给工厂），但 `TestCaseCreate`/`TestCaseUpdate` 两个 schema 都没有该字段，GUI 两个弹窗结构性设不了。单 active lab（当前所有部署形态）下 `resolve_lab_profile(db, None)` 兜底完美工作；多 active lab 下执行 422 结构化 fail-loud（ambiguous 拒绝，非静默错配）。不绑 = bootstrap 种子模板明文设计（deployment-agnostic），GUI 建例同派；6 个 factory 产 MIMO_OTA 模板带绑定是快照语义的特例。**正修**（多 lab 部署真出现时）：契约加可选 `lab_profile_id` 走四步同步 + 创建/编辑弹窗加绑定口（起点=模板时顺带复制其绑定）。
- `[discovered 2026-07-31 during GUI 新建入口片]` **`created_by="gui"` 是硬编码占位** —— GUI 无认证上下文（`require_auth` 全仓零使用点，S4c 申报过），`TestCaseCreateModal` 建例统一落 `created_by="gui"`。接上认证上下文（roadmap 既有 Auth Context 待实现项）后换成真实用户名。

- `[discovered 2026-07-30 during ARCH-1 roadmap 补记]` **[→ 提升 P1-23 (2026-08-01)]** **现场协议不覆盖 P0-8，照 checklist 走完会漏掉 F64 验证** —— [`guides/on-site-debug-protocol.md`](guides/on-site-debug-protocol.md) 开篇写「配套 P0 队列（**P0-3/4/5**）使用」，五个 Phase（网络 / 逐仪表 SCPI 握手 / SA 入 HAL / 路损校准 / DUT attach）**没有 P0-8 的 gate**。而上方「Blocked on hardware」表强制要求按该协议走 —— 结果是「走完了」却漏掉 P0-8 现场半（real F64 上 load→run→改参全 0 error + 输入口变绿 + DL 不失真），**比没有 checklist 更危险**（给人已覆盖的错觉）。当前缓解：P0 队列表已补 P0-8 行 + 表下注解写明出发前手动排进当天计划。**正修要定两件事**：① P0-8 塞进哪个 Phase（比 Phase 1 SCPI 握手重，要 load→run→改参→读电平，可能单独一段或作 Phase 1 的 F64 子门）；② gate 判据怎么拆 —— P0-8 验收最后一条「DL 不失真（DUT attach 后非 0% ACK）」**依赖 DUT attach**，有一半得等 Phase 4，gate 可能要拆两半挂两个 Phase。**顺带**：该协议里「Current Focus 按依赖链 P0-4 → P0-3 → P0-5 推进」那句同样已 stale（P0-3/4 已 2026-07-03 现场完成），跟 roadmap 里那句同源，一并清。⚠️ 动之前按标题/条目名定位，**别在文档里写行号** —— 本次 PR 实证：行号会被自己的编辑挤跑。
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

- `[discovered on-site 2026-07-03 during precheck]` **[→ 提升 P1-27 (2026-08-02)]** **P1-8 校准门不区分数据来源 (mock/real)**: 昨晚 mock 路损校准 cert 在 real 模式 precheck 里 `cal_pass: true` (门只查存在/频率/时效, 不查 provenance) → 真测会静默应用 mock 补偿值。修法 = cal 记录带 `use_mock` 标记 + real 模式 strict 门拒 mock cert (feedback_runtime_gate_not_frozen_snapshot 同族: live source 还要 live provenance)。待 promote (建议 P1, 半天)。
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
- `[discovered 2026-07-04 during #206 补扫]` **[→ 提升 P2-22 (2026-08-02)]** **F64 disconnect 依赖 `_emulation_running` 缓存判"要不要 GOS"** —— HAL 重载后的冷实例缓存 False，即使仪器仍在回放，disconnect 也跳过 stop 直接断开并返回 True（假"干净断开"）。F64 无已实证的 live 回放状态查询命令；等下次现场第 0 条 SCPI 冒烟实证"已停态 GOS 是否 benign"（[onsite-tasks](guides/onsite-tasks-20260703.md)）后，可改无条件 GOS 消除缓存依赖。
- `[discovered 2026-07-04 during #206 补扫]` **[→ 提升 P3-19 (2026-08-02)]** **QZ 验证 / 方向图扫描 / 多频扫频借用 acquire 的清理失败警告不可见** —— `quiet_zone_validation_service`（XPD ×2 + grid 扫描）、`probe_calibration_service`（方向图扫描）与同文件 `MultiFrequencyPathLossService.calibrate_frequency_sweep`（agent 复审 F3 补）各自新建局部 `ProbePathLossCalibrationService` 调 acquire，清理失败 append 进 `_last_acquire_warnings` 后无人收割、且下一次 acquire 开头即清空 → 在这三族流程里静默（校准证书路径 #206 已修全出口收割 + wire 透出）。proper = helper 加 warnings 穿透（签名改动）+ 各自结果对象带 warnings；multi-frequency `/start` 端点失败 detail 一并对齐 dict 格式。
- `[discovered 2026-07-04 during #206 补扫]` **[→ 提升 P3-19 (2026-08-02)]** **校准 warnings 的 DB 持久化断层（wire 已通,证书不留痕）** —— agent 复审 F2 半修:`CalibrationJobResponse.warnings` + 两个 start 端点 + orchestrator results dict + GUI toast 已通,但 `ProbePathLossCalibration` cert 模型无 warnings 列 → 校准完成后再查证书看不到当时的清理告警（只有启动响应一次性可见）。proper = cert 模型加 warnings JSON 列（迁移,add-column 方言无关模板 `f1d23a7b9c84`）+ `/latest` 响应带出 + rf-chain / multi-frequency 端点失败 detail 对齐。
- ~~`[discovered 2026-07-04 during Codex 兜底 R10]` **F64 11 站点 `_check_errors` 只 log 的同型假成功平行族**~~ **✅ done 2026-07-05**:9 个参数设置方法 (`set_path_loss / set_doppler / set_baseband_power / set_external_attenuators / set_output_path_loss / set_output_gain / set_crest_factor / set_input_measurement_mode / set_burst_trigger_level`) + `upload_asc_files` 全程加载门 + `set_channel_model` CENT 段全部换 `_gated_write_transaction` (锁事务 drain → 写 → `_first_error` 门)。被拒 → False + `logger.error` (经 `ContextFilter`+`JsonFormatter` → `logs/*.jsonl` → `/system-logs/tail?level=ERROR` → GUI `ZoneLogsAlerts` 面板, 操作员可见 —— 链路契约有测试固化)。`_check_errors` 已退役删除 (它的"只 log 不判定 + `while True` 无上界"是假成功根源)。新 `test_f64_check_errors_family.py` (clean/被拒 各 9 参数 + upload 门 + CENT 门 + GUI 日志链路 + 事务原子性)。校准补偿链 (set_path_loss/set_output_gain) 与 Pipeline B 加载 (upload_asc_files, P0-8 母题) 的真硬件假成功至此堵死。
- `[discovered 2026-07-05 during #202 兜底门审]` **[→ 提升 P3-19 (2026-08-02)]** **UXM SOCKET 终止符判定大小写敏感（P3,pre-existing）** —— `uxm_base_station.py:349` / `:2129` 的 `"SOCKET" in resource_str` 设 `\n` 终止符仍大小写敏感（小写 `socket` 不设终止符）。#202 兜底已把 redirect 门的 token 检查归一化,但这两处终止符判定漏了 → 现在 redirect 门对 SOCKET 大小写不敏感、终止符判定敏感,两者不一致。归一化这两处（复用同一 `.lower()` 收敛点）。
- `[discovered 2026-07-04 during R6 终审]` **[→ 提升 P3-19 (2026-08-02)]** **UXM ARFCN custom 旋钮三条 P3 加固**（agent 终审备注级,不阻塞）—— ① attach 序列 `params_schema` default ↔ run() fallback 仅注释互指无守护,下次换基线只改一处会再漂移（提模块常量两处引用,或加 schema↔run 同源断言用例）；② `nr_band_arfcn_map` 键大写归一碰撞（`{"n78":A,"N78":B}`）静默择后,可在归一处检测冲突 raise；③ custom map 值为字符串 `"640000"` 时下发/回读对账正常但 `get_frequency_identity` 链 TypeError 响亮崩,可在归一处 `int(v)` 让配置错误加载时 fail-loud。
- `[discovered 2026-07-31 during P2-11 现场使用]` **[→ 提升 P3-14 (2026-08-01)]** **GUI 频率输入/显示粒度粗于 NR ARFCN 栅格（母题枚举, TestCase 表单已修, 其余待收）** —— TestCase 表单「中心频率」此前 GHz 3 位小数 = 1 MHz 粒度, ARFCN 636666 (3549.99 MHz) 写不进, P2-11 频率一致性门必红 (实证只能绕道 PATCH API); 已改 MHz 3 位小数 = 1 kHz 全栅格覆盖。**同病待修**: ① `ChannelAssetForm.tsx` 的「中心频率 (GHz)」NumberInput (4 位小数 = 100 kHz 粒度, 资产登记自己就够不着 15 kHz 栅格点); ② `CustomCDLProfileManager.tsx` 的「中心频率 (GHz)」NumberInput; ③ 显示端 `ChannelWorkbench.tsx` (`toFixed(3)`/`toFixed(4)` GHz) 与 `CustomCDLProfileManager.tsx` (`toFixed(3)` GHz) 会把 3549.99 MHz 显示成 3.550 GHz (显示端说谎, 跟 `feedback_effective_end_not_nominal` 同母题); 修法同款 (MHz 口径 + 1 kHz 粒度); ④ `TestCaseLibrary.tsx` 用例卡片显示行级 `frequency_mhz` 派生列, 而 GUI 保存链只 PATCH `configuration` 不回同步该列 → 新表单改频后卡片显示 stale 旧频率 (内审 F1; 收口时修法是换源 —— 卡片改从 `configuration.frequency_hz` 派生显示, 别加同步机制)。**方向⑤ (体验升级, 需小设计稿)**: 绑定信道资产时频率/带宽从资产声明带出免手抄 —— 符合 declared > inferred 架构 (docs/architecture/testcase-driven-instrument-config.md), 但要定"预填可改 vs 锁定"语义; 现有 resolver `scd_freq_identity` fail-loud 网已兜住错配, 不修只是费手不失真。
- `[discovered 2026-07-31 during P2-8 tail 过滤语义修复]` **[→ 提升 P2-19 (2026-08-01)]** **主控台日志面板多选/默认态仍是 P2-11 失效模式（GUI 跟进,P2）** —— `/system-logs/tail` 已改"扫描中过滤",但 `ZoneLogsAlerts` 只在**单选一个 level** 时才下推 `level` 参数;默认三 chip 全开或 WARN+ERROR 双选走无过滤路径(最新 200 原始行+客户端过滤),低频失败行照样 ~48s 被冲出。修法=多选时逐 level 各发一次请求合并去重(零后端契约变化);同批顺带把 `total_lines_read` 显示成"已扫 N 行"(触顶时"无匹配日志"是假阴性,SystemLogViewer 已展示该字段,面板未展示)。
- `[discovered 2026-07-31 during P2-8 tail 过滤语义修复]` **[→ 提升 P3-19 (2026-08-02)]** **tail 反向扫描字节上限缺失（P3,pre-existing）** —— `_scan_tail_entries` 行数封顶但字节无界:无换行的损坏/巨行文件整读进内存(旧实现同病)。修法=while 条件补累计字节上限(如 16MB)。
- `[discovered 2026-07-31 during P2-8 tail 过滤语义修复]` **[→ 提升 P3-19 (2026-08-02)]** **app.log 噪声治理 + 执行失败告警通道（P3 组合条目）** —— ① `app.audit` 有专属 audit.log 仍 `propagate:True` 双写 app.log(同文件 `sqlalchemy.engine`/`app.frontend` 均已 False);② `instrument_hal_service` 19 处 INFO + `app.db` 会话日志 ~250 条/分是冲窗主力,且开发日志里 ERROR 也有刷屏(20 分钟 200 条) —— 注意根 logger+file_app 均收 DEBUG,单纯降级站点**不会**减少 app.log 行数,需配命名空间级 logger 门槛一起做;③ runner 相位失败只落日志,不进右侧「活动告警」面板(`test_case_runner` 无告警调用),失败→告警是独立增量;④ 面板 `lines=200` 写死,可调性顺带评估。
- `[discovered 2026-08-01 during VRT 摘要 channel_model 换源修复]` **[→ 提升 P2-20 (2026-08-01)]** **标准场景库 5 处 `channel_model=` 死 kwarg（P3）** —— `app/data/scenario_library.py` 给 Environment 传的 `channel_model=ChannelModel.*` 被 Pydantic `extra='ignore'` 静默吞掉,标准场景 `channel_snapshots` 恒空 → 场景库列表里标准场景的信道模型列恒 None。修法=把这 5 处改成 `channel_snapshots=[ChannelSnapshot(channel_type="3GPP", standard_model=..., ...)]`;`tests/test_data.py` 的 environment 也还在用旧 `channel_model` key,同批一起换。
- `[discovered 2026-08-01 during VRT 摘要 channel_model 换源修复]` **[→ 提升 P2-20 (2026-08-01)]** **channel_model 死字段其余读/写方 3 站点（同母题清单, P3）** —— 内审全量扫出摘要行之外还有: ① `road_test.py::_generate_execution_report` 的 `EnvironmentInfo` 构造用 `get_attr_or_item(env, 'channel_model', '')`,tolerant 默认让它不崩但**恒空串**(live 路径: 列表显示 CDL-C、同场景报告显示空,两读方不同源),修法同款换源 `channel_snapshots[0].standard_model`;② `ota_scenario_mapper.py` 5 处读 `scenario.environment.channel_model`(当前全仓零调用方的死代码,任何人接线即 100% AttributeError);③ GUI 写侧 `CreateScenarioDialog`/`EditScenarioDialog` 恒发 `channel_snapshots: []`,表单选的 channelModel 只进 tags → GUI 建/编场景摘要 channel_model 恒 null、Edit 预填恒回落 'UMa',快照真值今天只有 API 直发能写。三处与标准库死 kwarg(上条)同母题,宜同批收口。
- `[discovered 2026-08-01 during VRT 摘要 channel_model 换源修复]` **[→ 提升 P2-20 (2026-08-01)]** **`_list_custom_scenarios` 单行坏配置会 500 全列表（P2）** —— `road_test.py` 列表推导逐行 `vrt_test_case_to_scenario`,任何一行 DB configuration 过不了 `VirtualRoadTestConfig.model_validate`(如旧 schema 遗留行)就 ValidationError 冒泡,整个 `/road-test/scenarios` 500,全部场景消失。比摘要降级更烈的全灭模式,与"场景数==摘要数"不变量门同母题;修法待设计(逐行 try + 降级出行 or 显式隔离坏行报表),注意别静默丢行。

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
