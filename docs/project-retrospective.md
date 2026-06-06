# MIMO-First 项目历程回顾 —— 从第一次现场到现在

> **范围**：2025-11 首 commit → 2026-06（371 commits / 149 PR），重点是两次 CAICT 现场
> 及其间诞生的治理基线。
> **数据来源**：git 历史、`announcements/2026-05-14-roadmap-baseline.md`、`site-debug/*`、
> `guides/on-site-debug-protocol.md`、`roadmap-first-call.md` 的 dated 复盘块、项目 memory。
> **一句话主线**：**"软件先在本地走通，现场只调硬件"** —— 两次现场都用反面验证了这条；
> 整套 governance 和此后所有本地工作都是它的推论。

---

## 速览

| 阶段 | 时间 | 一句话 |
|------|------|--------|
| 0 现场前积累 | 2025-11 → 2026-05-11 | 前后端 + HAL + 校准三件套 + TestCase-first 架构，但 **commissioning 从未对真仪器跑通** |
| 1 ⭐ 第一次现场 CAICT | 2026-05-12/13 | 两天 99% 耗在 driver 层，first-call PDF 没出 —— 8 个坑同一个 DNA |
| 2 ⭐ Governance Baseline | 2026-05-14 | 第一次现场的制度后果：WIP=1、不顺手优化、现场不写 driver、单一路线图 |
| 3 本地"链路走通"主线 | 2026-05-14 → 05-26 | 真 P0 现场 blocked，本地把链路补严（mock first-call + 一串 fail-loud gate） |
| 4 第二次现场 CAICT | 2026-05-27 | 首个经暗室 OTA call 打通（100% ACK，手动直通单层），但完整校准 first-call 仍没出 |
| 5 第二次现场后收口 | 2026-05-28 → 现在 | 现场 driver 发现系统性收敛为 **TestCase 驱动仪表配置**架构 + 三层声明/实测交叉校验 |

---

## 阶段 0 — 现场前的本地积累（2025-11 → 2026-05-11）

理解"为什么现场全卡 driver"的前提。

- **2025-11 奠基**：React+TS+Vite 前端 / FastAPI+Pydantic 后端骨架；测试计划/测试例分离、VRT、ChannelEngine 微服务、系统校准后端 —— 基本是 mock + 设计文档驱动。
- **2025-12 ~ 2026-01**：测试管理统一架构（4-Tab）、Queue↔Monitoring 执行同步、VRT 执行历史。仍几乎全是前端 + mock，无真硬件。
- **2026-04 HAL 集中爆发**：硬件目录 + 动态 driver 工厂 + GUI mock/real 切换、5-stage commissioning 引擎、结构化日志 + SCPI trace、ZNA/FSVA/Aerotech/UXM 各 driver。
- **2026-05-04/05 两个奠基决策**：
  - **TestCase-first**：测试管理基础单元是 **TestCase 而非 TestPlan**；TestPlan=执行集合；VRT=复杂衍生。
  - **数据库栈**：生产一律 PostgreSQL，SQLite 仅测试隔离。
  - **校准三件套**（一晚完成）：path-loss 校准按每条 RFChain 迭代而非全暗室一个平均，闭合跨实验室可移植性。

> **关键状态**：到现场前，commissioning 引擎（~1386 LOC，5 phase）在 mock 下写好，但**从未对真仪器跑通**。这是后面失败的伏笔。

---

## 阶段 1 — ⭐ 第一次现场：CAICT 2026-05-12/13（转折点）

**原定**：交付一次完整暗室 first-call。**实际**：两天 99% 耗在 driver 层，PDF 没出。

复盘把 8 个失败归纳为同一个 DNA：**"driver 是否活着"的状态散落在 3+ 处，任意两处可悄悄打架而无人发觉**。

- **Day 1（E5071C ENA）**：HAL init-once 永不重读 DB（时序）/ pyvisa 没装进 venv 被吞成通用 "Connection failed"（环境漂移）/ 只开 SICL-LAN 但 driver 用 VXI-11（协议方言不可见）/ PNA 语法 ≠ E5071C 原生 SCPI（方言错）。
- **Day 2（F8820A / PROPSIM FS16）**：GUI 选 F64 实际是 FS16（选错型号）/ 基类 `_query` 同步但 driver async → coroutine 喂给 `.strip()` 被吞（框架 bug）/ `*TST?` 触发 30s 自检期间全超时无熔断（SCPI 副作用未审计）/ FS16 SOCKET 单 client + idle-close 卡死（半关）。

**现场修了**：PR #8-#14（FS16 全栈 / F64 identity gate / UXM 多 app / SCPI 排除 mock / Aerotech 单轴 / 信道清单 / **idle-close 透明重连 + TCP keepalive + pre-flight 可达性**）。

**提炼**：6 类根因 + 6 条 driver 铁律（probe 无副作用 / identity 多 substring / 同品牌≠共享 SCPI / 跨厂 lookalike 是雷 / driver 必暴露 `_query`·`_write` / 独立 pyvisa 脚本是 first-touch 工具）。现场硬事实写进 memory（F64 真 IP/IDN/端口、`*OPT?`/MMEM/FTP 不可用、`-100`=命令不存在、Aerotech 在 .16 单轴、~30s idle-close）。

📄 `site-debug/2026-05-13-retrospective.md` / `2026-05-13-summary.md`

---

## 阶段 2 — ⭐ Roadmap Governance Baseline（2026-05-14）

第一次现场最重要的**制度后果**。

**诊断**："driver 调试和 commissioning 调试是两件事，混在一次现场跑就一定卡 driver"；"顺手修"是 silent killer；review feedback 是黑洞；多 session 各自局部最优、无人维护全局路线。

**7 条工作准则**（写进 `CLAUDE.md` 顶部 + roadmap，每条对应一类失败）：① 先读路线图 ② **WIP=1 on P0** ③ 非路线图改动分琐碎/中等/大改三档 ④ **严禁顺手优化**（mess 不是 bug）⑤ PR 必声明 roadmap 对齐 ⑥ review 反馈 P0/P1 当下修、P2/P3 进 backlog ⑦ 每周 drift review。

配套：`roadmap-first-call.md`（单一真相源）+ PR 模板强制 `Roadmap:` 字段。

📄 `announcements/2026-05-14-roadmap-baseline.md` / `CLAUDE.md`

---

## 阶段 3 — 本地"软件链路走通"主线（2026-05-14 → 05-26）

真 P0（P0-3/4/5：路损校准 / 真 SA 读 TRP / 真 DUT attach）全现场 blocked，按治理在本地推进 P0-6 mock 彩排 + 一长串 P1/P2/P3 把链路补严。

- **P0-1/P0-2/P0-6**：DB 自动 bootstrap / Lab Profile wizard / **mock-data first-call 端到端出真 PDF**（出发前硬门槛的杠杆点）。
- **P1-7**：commissioning → ChannelEgine **第一次完整闭环**（拆 hardcoded mock cluster，走 24-cluster 38.901）。
- **P1-8/9/10**：commissioning precheck 三道 **fail-loud gate**（校准缺失 / DUT-attach / non-ring 几何）。
- **P2-8**：主控制台重设计为 4 区操作驾驶舱。
- **P1-11/13/15**：多子网仪表 runbook + 可达性诊断 + **canary 负对照**（识破 VPN 伪造可达 —— 直接为 5/27 现场 Mac 挂 VPN 准备）。
- **P1-12**：一批静默兜底值改成显著标"未验证"。
- **PFS/相位决策**：核 TR 37.977 F.2（MPAC 校准 power-only），**保留** phase cal 全套基建为将来 **PWS**（平面波合成需相位相干）。
- **on-site 协议**（`on-site-debug-protocol.md`）：把 CAICT 教训固化成纪律 —— 6 条铁律（现场不写 driver 居首）+ 出发前硬门槛 + Phase 0-5 go/no-go gate + 每日 review + retro 喂回 roadmap。

---

## 阶段 4 — 第二次现场：CAICT 2026-05-27

**原定**：Phase 5 完整 first-call。**实际**：上午**首个经暗室 OTA call 打通**（UXM→F64 直通→暗室探头→真 DUT，下行 PDSCH **100% ACK**）—— CAICT 两天没到这一步。但范围诚实：F64 **手动直通、无信道仿真、单层**。下午又大量耗在 F64 driver，完整校准 first-call PDF 仍没出。

**关键发现**：
1. **F64 两天 blocker 根因坐实 = 端口错**：driver 连 5025，PROPSIM 固定 ATE 口是 **3334**。真机 3334 上 load/run/改参全 0 error。早上"-200 通道不匹配"被当场推翻（真因=文件从未加载，`*OPC?=1≠成功`）。
2. **当天最大设计发现 — F64 输入信号参考 + crest factor**：能 attach、输入口变绿、DL 不失真的关键。driver 有 autoset 但无人调用 → 跨 driver 操作点闭环缺口 → 催生 `f64-input-level-and-dynamic-range.md`。
3. **UXM 纯 SCPI cell-cycle 演练成功**：停 cell→重设 7 参数→重启→自动重附着→测吞吐，全程零错误。证明软件能纯 SCPI 编排 UXM。
4. **诊断洞察**：客户端"超时" ↔ RDP "-113 Undefined header" 是同一现象两面 → 铁证"不能只凭没报错判命令成功，必须 gate `SYST:ERR?`"。
5. EMCenter switch 不吃 raw SCPI → P2-9；转台无结论 → U-5；scpi-command slow-op desync → P1-16。

> **核心教训重演（诚实记）**：又一次大量耗在 driver 层。区别是这次**用户明确授权修 driver**（覆盖铁律）→ 属主动改优先级，不是失控 drift。补救正是 P0-8：把 driver 修法 offline 落地，让下次现场只调硬件。

📄 `site-debug/2026-05-27-morning-log.md` / `2026-05-27-onsite-playbook.md`

---

## 阶段 5 — 第二次现场后的本地收口（2026-05-28 → 现在）

现场 driver 发现全部收敛成本地 P0-8 + 一系列 P 项；主旋律是 **"TestCase 驱动仪表配置"架构**落地。

- **P0-8**：端口固定 3334 + 加载后 `SYST:ERR?` gate + F64 输入参考原子能力 + **InputLevelController CE↔BS 操作点闭环** + 默认 3600M .smu。把 5/27 手动做的事变成代码。
- **⭐ TestCase 驱动仪表配置架构**（用户 2026-05-30 确立）：两条正交路径 —— **路径 A**（bring-up，走默认配置捷径，默认之间须自洽）；**路径 B**（正式测试，TestCase 是单一真值源，下发后多方一致性 **fail-loud**，绝不静默兜底）。
- **三条 P2 本地主线（各剩现场半）**：P1-17（UXM fresh-start 默认 profile）/ P2-11（一致性网四根线：频率+MIMO layers+调制+生效 MCS + 端口路由 path B）/ P2-10（F64 精细化）/ P2-12（SCD 软件掌控 .smu 命名）。
- **三层"声明 vs 实测"交叉校验**（防错配同一母题）：**DUTProfile**（能力层）+ **SIMProfile/P2-13**（身份/接入层，防插错卡）+ GUI 收尾（DUT/SIM 合并单入口双 Tab）。
- **input-level 操作点 + 一条 meta 教训**：imbalance 遥测做完即止；后续软化门/报告不确定度经评估**保持现状不推进**。教训：当前工作正常且无 demonstrated problem 时默认保持现状，别把理论精化抬成"待拍板的决策"施压（memory `feedback_dont_manufacture_decisions_no_problem`）。
- **P1-6**：FS16/UXM/ENA silent-reconnect 本地测试覆盖补全。

📄 `architecture/testcase-driven-instrument-config.md` / `architecture/multi-port-input-level-semantics.md`

---

## 贯穿全程的 5 条主线

1. **软件先本地走通，现场只调硬件** —— 两次现场的反命题验证，是所有工作的北极星。
2. **状态多源分歧 → fail-loud** —— 从"driver 是否活着记在 3 处"，到 P1-8/9/12 gate，到 P2-11 多方一致性网，到 DUT/SIM 声明 vs 实测交叉校验，同一母题（单一真值源 + 显式校验 + 不静默兜底）反复深化。
3. **现场发现 → 结构化 P 项 → 本地收口 → 下次现场只剩硬件半** —— P0-8 / P2-9 / P1-16 / U-5 都是这个闭环的实例。
4. **真 P0（P0-3/4/5）始终现场 blocked** —— 路损校准闭环 + 真 SA 读 TRP + 真 DUT attach 需校准天线/SGH/真 DUT 到位，至今未交付完整校准 first-call。**这是尚未跨过的终点线。**
5. **诚实记录 drift** —— roadmap 多处明写"PDF 没出来"、"区别是用户授权"，不粉饰，本身是 governance 文化的一部分。

---

## 现在在哪 / 终点线还差什么

- **本地队列已基本清空**：本地可启动的 P 项（P2-13 三阶段、DUTProfile、#2001(1)、P1-6 测试）均已收口；`#2001(2)(3)`/`#2002` 经评估保持现状不推进。
- **真正卡住的全是现场依赖**：6 项纯 on-site + 7 项混合的现场半，核心是依赖链 **P0-4 → P0-3 → P0-5**。
- **下次现场**：按 `on-site-debug-protocol.md`，Current Focus 必须先切回 P0 依赖链，现场只调硬件、不写 driver 代码。**完整校准 first-call PDF = 待跨的终点线。**

> 可规划但非现场的候选（需 triage，非积压）见 `roadmap-first-call.md` 的「可规划工作 audit」段。
