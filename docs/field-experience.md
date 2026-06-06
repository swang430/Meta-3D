# 现场经验与教训 —— 经验性文档归类索引

> **这份索引解决什么**：项目里"由现场问题催生 / 沉淀教训"的文档散落在 `site-debug/`、
> `audits/`、`announcements/`、`guides/`、`architecture/` 多处。这里把它们**归类成册**，
> 让"下次现场前该读什么 / 某个坑当时怎么解的"一站可查。
>
> **什么算"经验性文档"**：不是设计提案或 API 规范，而是**从真实现场/真实故障中学到、
> 并固化下来防止重犯**的东西 —— 现场日志、回顾、审计、治理铁律、以及由现场发现直接
> 催生的设计文档。
>
> **全程叙事**见 [`project-retrospective.md`](project-retrospective.md)（第一次现场→现在）。

---

## 速查：按"我想解决什么"找

| 我想… | 看这个 |
|-------|--------|
| 下次现场前做准备 | [`guides/on-site-debug-protocol.md`](guides/on-site-debug-protocol.md)（6 铁律 + 出发前硬门槛 + go/no-go gate） |
| 了解项目怎么走到今天 | [`project-retrospective.md`](project-retrospective.md) |
| 知道为什么有 WIP=1 这些规矩 | [`announcements/2026-05-14-roadmap-baseline.md`](announcements/2026-05-14-roadmap-baseline.md) |
| 复现某个现场坑当时怎么解 | 下方 §1 现场记录 |
| F64/UXM/暗室真实硬件事实 | §1 现场记录 + memory `project_f64_ate_server_capabilities` / `project_caict_network_topology` |
| 某个设计为什么这么定 | §3 现场衍生设计 + §5 决策 memory |

---

## 1. 现场记录与回顾（`site-debug/`）

按时间，每次现场的原始记录 + 当日复盘。**最高价值是 retrospective**（把坑归纳成根因+铁律）。

| 文档 | 内容 |
|------|------|
| [`caict-2026-05-13.md`](site-debug/caict-2026-05-13.md) | 第一次现场前一晚（5-12）备战的 1 日联调任务表 |
| [`2026-05-13-summary.md`](site-debug/2026-05-13-summary.md) | 第一次现场（CAICT）当日简报 |
| ⭐ [`2026-05-13-retrospective.md`](site-debug/2026-05-13-retrospective.md) | 第一次现场回顾 —— 8 坑归纳成 6 类根因 + 6 条 driver 铁律（**必读**） |
| [`2026-05-16-pyvisa-ide-interpreter-investigation.md`](site-debug/2026-05-16-pyvisa-ide-interpreter-investigation.md) | PyVISA "未安装" 实为 IDE 解释器漂移（P1-3） |
| [`2026-05-27-morning-log.md`](site-debug/2026-05-27-morning-log.md) | 第二次现场日志 —— F64 端口 3334 根因坐实 + 输入参考最大发现 |
| ⭐ [`2026-05-27-onsite-playbook.md`](site-debug/2026-05-27-onsite-playbook.md) | 第二次现场实战攻略 |
| [`2026-06-04-emcenter-switch-protocol.md`](site-debug/2026-06-04-emcenter-switch-protocol.md) | EMCenter 开关协议调研（P2-9） |
| [`2026-06-04-positioner-turntable.md`](site-debug/2026-06-04-positioner-turntable.md) | 转台控制 + runbook（U-5） |

---

## 2. 治理与流程（从现场教训固化的纪律）

第一次现场"卡 driver"的**制度回应** —— 把"为什么需要纪律"变成可执行规则。

| 文档 | 内容 |
|------|------|
| ⭐ [`announcements/2026-05-14-roadmap-baseline.md`](announcements/2026-05-14-roadmap-baseline.md) | Governance baseline 论证：7 条工作准则的由来（WIP=1 / 不顺手优化 / 现场不写 driver / 单一路线图） |
| ⭐ [`guides/on-site-debug-protocol.md`](guides/on-site-debug-protocol.md) | 现场首测调试协议：6 铁律 + 出发前硬门槛清单 + Phase 0-5 go/no-go gate + 每日 review + retro 喂回 |
| [`roadmap-first-call.md`](roadmap-first-call.md) | 单一真相源（governance rules 段 + Current Focus + 可规划工作 audit） |
| `../CLAUDE.md` | 7 条工作准则的常驻副本（仓库根，所有 session 入口） |

---

## 3. 现场衍生的设计文档（field-derived architecture / features）

这些设计**不是凭空提案，而是某次现场发现直接催生**的 —— 读时配合对应现场记录看更透。

| 文档 | 催生于 |
|------|--------|
| [`architecture/f64-input-level-and-dynamic-range.md`](architecture/f64-input-level-and-dynamic-range.md) | 5/27 现场最大发现：F64 输入信号参考 + crest factor（否则 DL 失真、0% ACK） |
| [`architecture/multi-port-input-level-semantics.md`](architecture/multi-port-input-level-semantics.md) | 上者的通俗解释 + 操作点门"保持现状"决策（为什么 per-port 是标定不是闭环） |
| [`architecture/testcase-driven-instrument-config.md`](architecture/testcase-driven-instrument-config.md) | 5/27 现场仪表配置混乱 → 路径 A/B 切分 + 单一真值源 fail-loud |
| [`features/calibration/pfs-phase-immunity.md`](features/calibration/pfs-phase-immunity.md) | PFS power-only（TR 37.977 F.2）→ 为何保留 phase cal 基建留给将来 PWS |

---

## 4. 审计报告（`audits/`）

对某条已交付链路的"事后体检"，挖出静默漂移。

| 文档 | 内容 |
|------|------|
| [`audits/2026-05-17-commissioning-drift-audit.md`](audits/2026-05-17-commissioning-drift-audit.md) | 暗室首测 commissioning 漂移审计 |

---

## 5. 工程教训沉淀（memory，仓库外）

Agent 跨 session 的记忆库在 `~/.claude/projects/-Users-Simon-Tools-MIMO-First/memory/`，索引见该目录 `MEMORY.md`。两层：

- **`project_*`（项目知识 / 现场事实 / 设计决策，~15 条）** —— 经验性，例如：
  - `project_f64_ate_server_capabilities` —— F64 ATE Server SCPI 实测能力（`*OPT?`/MMEM/FTP 不可用、`-100`=命令不存在）
  - `project_caict_network_topology` —— CAICT 现场网络/单网卡跨子网拓扑
  - `project_pyvisa_ide_interpreter_drift` —— IDE 红波浪线 ≠ 运行时缺失
  - `project_testcase_driven_instrument_arch` / `project_testcase_first_architecture` —— 核心架构决策
  - `project_pfs_phase_cal_decision` / `project_jitter_phasecal_mutex` —— 校准/相位决策
- **`feedback_*`（工程纪律自我改进，~33 条）** —— 不是项目知识而是"怎么干活别犯错"的铁律（如 contract sync、fail-loud gate fan-out、不顺手优化、不制造议题）。属 agent 协作纪律层，不在本仓库范围，但与 §2 治理同源。

---

## 附：全量文档分类导航（7 类）

经验性文档之外的其余文档按用途分 7 类；逐篇导航见 [`README.md`](README.md)，此处只给类→目录映射：

| 类别 | 目录 / 文件 |
|------|-------------|
| 治理与流程 | `roadmap-first-call.md`、`announcements/`、`guides/on-site-debug-protocol.md`、`Master-Progress-Tracker.md` |
| 架构设计 | `architecture/`、`design/` |
| 功能设计 | `features/`（calibration / test-management / virtual-road-test / report） |
| API 与数据规范 | `api/`（design-guide / data-model / swagger-guide） |
| 硬件 HAL 规格 | `hardware/` |
| 操作运维指南 | `guides/`、`Database-Operations-Guide.md` |
| 现场经验与教训 | **本文档** + `site-debug/` + `audits/` |
| 归档（已替代/历史） | `archive/` |

> 整理备注（来自 2026-06 文档盘点）：`features/test-management/{workflow-templates,monitoring}.md`、
> `hardware/{positioner,signal-analyzer}.md` 为框架占位（待内容补齐）；`产品特性/*.docx`（旧冲刺
> 计划）已被 `roadmap-first-call.md` 接管，属可归档。这些不阻塞，记此备查。
