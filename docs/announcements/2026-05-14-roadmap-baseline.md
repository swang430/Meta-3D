# 公告：MIMO-First 项目 first-call roadmap 启用 + main 作为基线

**日期**: 2026-05-14  
**发起人**: Simon Wang  
**适用范围**: 所有 MIMO-First 项目贡献者 (人 / AI agent)  
**Baseline 提交**: [`9d5049a`](../../../../commit/9d5049aec16094b9775b9e2b4e8ffcd56341e6cf) — `feat(hal): pre-flight TCP reachability check before driver.connect()`

---

## TL;DR

从今天起，**当前 `main` 分支是新的开发基线**。今后所有 feature / fix / refactor
工作都从这个基线开始，**严格按 [first-call roadmap](../roadmap-first-call.md)
排好的优先级执行**，避免再次出现 5/12-5/13 现场两天交不出 first-call 的情况。

具体来说：

1. 单一真相源是 [`docs/roadmap-first-call.md`](../roadmap-first-call.md)。
2. 当前 in-progress 的 P0 项写在该文件顶部 `Current Focus` 字段。
3. 任何 PR 必须声明它对应哪个 roadmap 编号。模板已就位
   ([`.github/pull_request_template.md`](../../.github/pull_request_template.md))。
4. 详细工作准则 (7 条) 已加入项目级 [`CLAUDE.md`](../../CLAUDE.md) 顶部。

---

## 为什么需要这套机制

### 背景

2026-05-12 / 13 CAICT 现场连续两天调试，原本目标是完成一次完整的**暗室
first-call** (MIMO OTA static commissioning，5 phase pipeline)。

### 实际发生

两天的时间 99% 用在 **driver 层** — 让 F64 / FS16 / UXM / Aerotech 四件
仪器认得对、连得上、不掉线：

| 类别 | 现场踩的坑 | PR # |
|------|------------|------|
| F64 身份识别 | IDN 实际返回 `KEYSIGHT,F8800A` 不是 `PROPSIM,F64` | #9 |
| F64 SCPI 能力 | `*OPT?` / MMEM / FTP 全部不支持 | #13/#15 |
| FS16 driver | 紧急补 | #8 |
| UXM Test App | 端点切换 + multi-app profile 系统 | #10 |
| Aerotech 单轴 | hardcode `ENABLE X Y` 在单轴控制器上 NAK | #12 |
| Aerotech idle close | Socket2 30s 闲置后自动关 | #14 |
| 各种 Codex review fixes | 连锁 | #14/#15 |

**Commissioning 引擎本身 (5 phase, 1386 LOC) 早就写好了，但 driver 不稳定
喂不进数据。**

### 经验提炼

- driver 调试和 commissioning 调试**是两件事**。混在一次现场跑就一定卡 driver。
- "顺手修一下"是 silent killer。每个看起来是小修的 PR 累加成 sprint 偏移。
- Codex / review feedback 是 review 黑洞 — P2/P3 风格反馈连锁修，时间消失。
- 不同 session / 不同 agent 各自局部最优，没人维护全局路线。

### 这套机制是反向解药

每一条规则都对应一类失败模式 (详见 `CLAUDE.md` 工作准则段)。

---

## 新机制有哪些文件

| 文件 | 作用 |
|------|------|
| [`docs/roadmap-first-call.md`](../roadmap-first-call.md) | 路线图本体。所有优先级项 + acceptance criteria + Current Focus + governance rules |
| [`CLAUDE.md`](../../CLAUDE.md) (顶部 "工作准则" 段) | 项目级契约。所有 agent / session 启动时读到 |
| [`.github/pull_request_template.md`](../../.github/pull_request_template.md) | 强制 roadmap 字段，触发 review 时关注 |
| [`docs/announcements/2026-05-14-roadmap-baseline.md`](.) | 本公告。可以分享给团队 |

---

## 当前 Current Focus

**`P0-1` — DB 自动播种 (chamber presets / instrument catalog / sequences / templates)**

播种器框架已就绪 (`app/services/bootstrap/`)，4 chamber 模板的数据已在
`app/models/chamber.py` 里。只差把 `run_all()` 接到 FastAPI lifespan startup。

详见路线图。预估 1 天。

---

## 团队成员请做什么

### 立刻 (今天)

1. **读一遍 [`docs/roadmap-first-call.md`](../roadmap-first-call.md)** — 5 分钟，了解优先级和你正在做的事情对应哪一项。
2. **读 `CLAUDE.md` 顶部新加的 "工作准则" 段** — 5 分钟，知道游戏规则。
3. **如果你正在改的代码不对应任何 roadmap 项** — 暂停, 跟 Simon 同步是新项目还是要进 backlog。

### 下次提 PR

1. 用新的 PR 模板填 `Roadmap: P0-X` 字段。
2. 不在路线图上的改动 — 老实写 `Out-of-roadmap, reason: ...`。
3. PR 期间发现的"顺手能修的事" — **不要修**，appended to roadmap backlog。

### 下次现场

不在路线图上的 driver 层调试 = 现场禁止。所有 driver 问题在本地复现 + 修。
现场只验证硬件回路 (path-loss cal / SA / DUT attach)。

---

## 关于 PR #15

PR #15 (`feat/post-14-pending-items`) 是这次基线之前的最后一批"自由开发"
产物 (5/14 在 main 之外的延伸开发, 包括今天上午聊到的 5 个 follow-up 项)。
该 PR merge 后会成为 `main`，作为路线图的"D1-D5 done" 状态。

PR #15 之后启用的 PR 都必须严格遵守上述机制。

---

## 反馈和异议

机制本身也可以改。但改的方式是 commit 一个 PR 修
`docs/roadmap-first-call.md` 的 governance rules 段，
不是 "我觉得这次特殊"。一致性优先于个案灵活。

如果你认为某条规则在实际项目中不可行 — 提个 PR 调整。但同样需要走机制本身。

---

## 在哪里看进展

- **当前 Current Focus**: `docs/roadmap-first-call.md` 顶部
- **已完成清单**: 同文件的 "Done" 表 + git log
- **下一步**: 跑完 P0-1 的 acceptance criteria → PR merge → 更新 Current Focus → P0-2

---

*— Simon, 2026-05-14*
