# MIMO-First — First-Call Roadmap

> **Single source of truth for what we're working on next.** All non-trivial
> development MUST reference an item on this roadmap. Off-roadmap work needs
> explicit justification (see [governance rules](#governance-rules) below).

---

## 🎯 Current Focus

**P2-11 (TestCase 驱动仪表配置架构) Phase 1/2/3/5/6 done + UXM 端口路由 path B (#1974) 收口。Phase 6 一致性网四根线 (频率 #109 + DL MIMO layers #114 + 调制阶数 #124 + 生效 MCS #126) 全部落地; UXM 端口路由/TDD/调度 path B TestCase 驱动 (后端 #127 + GUI #128) 闭环; 2026-05-31 核心参数审计 (架构文档 §8) 分 A/B/C/D 类。P2-10 (F64 精细化) Step 1/2/3 本地框架 done (#116/#125); P2-12 (SCD .smu) slice 1-4 + 扩展门 done (#116-#123) —— 三条 P2 线本地全收口, 各剩现场半 (P2-11 DL power 待操作点语义 / P2-10 现场真值 / P2-12 slice 5 SCPI 生成)。下一本地候选: DUTProfile (#1965, 三层能力交叉校验, 用户 6-01 提) 或停。本地可启动。**

**2026-06-02/04 — P2-12 SCD 线本地收口**: `.smu` 命名软件掌控 (SCD 实体 + 关联 + synced projection), slice 1-4 (#116-#122) + **emulation_file 扩展 fail-loud 门 (#123, Codex #120 后端另一半)** done; GCM .smu 扩展校验全链闭合 (前端 #120 filter + 后端 measure gate)。只剩 slice 5 路径 a SCPI 生成 (现场 blocked)。**下一本地候选** (该快照时列): ~~P2-11 Phase 6 MCS~~ ✅ #126 / ~~P2-10 Step 2-3~~ ✅ #125 (快照后已完成) / DUTProfile (#1965, 用户 6-01 提)。真正剩余候选 = P2-11 DL power (待操作点语义) / DUTProfile; 最新见顶部 line 11。**

**2026-06-04 — P2-11 Phase 6 第二根线 DL modulation 已补 (#124)**: `get_applied_cell_config` 读 UE `max_modulation_dl`, 请求调制阶数 > UE 上限 → fail (复用 `precheck_strict_cell_config`, `_modulation_order` 归一化容忍 SCPI 格式)。一致性网累计 = 频率 + MIMO layers + 调制阶数 + 生效 MCS (AMC off, #126)。剩 Phase 6 仅 DL power (结合操作点 backlog, 有 InputLevelController 闭环坑)。**

**2026-06-04 — P2-10 Step 2+3 本地框架 done (#125)**: Step 2 F64 per-output 输出端精细 method (`set_output_path_loss`/`set_output_gain`, 单通道 vs batch); Step 3 alignment 新鲜度 (`alignment_freshness` 解析 INFO? 标定日期 + 阈值 → stale 建议重标, precheck 上报)。F64 精细化"外部输出 + 内部校准"两面框架就位, 现场补真值 (OUTP:CON topology / INFO 格式全集 / 漂移监控)。**

**已收口** (2026-05-28/31): P0-8 本地半 ✅ (#92-#98) + P1-16 ✅ (#99) + Docker durability ✅ (#102/#103) + **P1-17 UXM fresh-start 默认 profile ✅ (#107)** + **P2-11 架构 (#108) + Phase 1 多方频率一致性门 ✅ (#109 + Codex fix) + Phase 2 GCM .smu TestCase 驱动 ✅ (#110) + Phase 3 switch mode TestCase 驱动 ✅ (#111 + Codex 路损 mode 过滤) + Phase 5 路径 A/B 边界固化 + 暗室首测捷径修复 ✅ (#112) → P2-11 Phase 1/2/3/5 done; 2026-05-31 核心参数审计 (架构文档 §8) 揭出 **Phase 6** (B 类一致性网, 本地下一个最有价值) + 2 个 C 类 Discovered backlog (端口路由泄漏 / 操作点); 剩 Phase 4 (信号源·VNA 按需) + Phase 6 按本地优先级**。所有真 P0 (P0-3/4/5) 仍 🚧 on-site blocked (校准天线/SGH/真DUT)。

**2026-05-29 全景规划** (用户复盘三大块 F64/UXM/Docker + 开关/转台 现状与前瞻): 把"仪器配置可复现性"缺口结构化成新条目 —— **P1-17 UXM fresh-start 配置落地** (对称 P0-8, 消除现场 UXM "快速路", 最大未规划缺口, 本地可启动) + **P2-10 F64 工程精细化** (配置文件资产/外部输出/user alignment cal, 部分本地) + **U-7** (UXM 参数集真值) + enrich P2-9 (射频开关下一步) / U-5 (转台)。**核心洞察**: F64 和 UXM 是同一个"配置可复现性"问题两面, UXM 落后 F64 一身位 (有 `load_state_file` + Topology Profile 但缺"默认自动应用")。**下一个 Current Focus 强候选 = P1-17** (待用户确认启动)。之前的本地 audit 流 P1-12 (#79/#80/#81) / P1-13 (#83) / P1-14 (#86) /
P1-15 (#88) 全 merged。

**5/27 现场产出 (诊断 + 真机验证, 非交付件 —— first-call PDF 未产出)**:
- ✅ F64 两天 blocker 根因坐实: ATE/SCPI 端口硬件固定 **3334**, 早期误用 5025 → 响应 desync + 文件加载 -300。真机 3334 上 load / run / 改参全 0 error。
- ✅ **今天最大新发现**: F64 每个输入需设"信号参考"(平均电平 dBm + crest factor dB), 否则前端增益错 → 输入口不变绿 → DL 失真 → DUT 能 attach 却解不出 PDSCH (0% ACK / all-NACK)。**纠正**: driver 已有 autoset 方法但无人调用; 真实缺口是跨 driver 操作点闭环 (已起草设计文档 [f64-input-level-and-dynamic-range](architecture/f64-input-level-and-dynamic-range.md))。
- ✅ 早上 -200 误诊纠正: 真因是"文件根本没加载"(错端口 5025 + 无 `SYST:ERR?` gate, `*OPC?=1≠成功`), 非通道数不匹配。
- ◐ 暗室首测重现: DUT 经 SCPI 控制的 F64 + 3600M(N78) 稳定 **CONN + DL live**, 但 **0% ACK**(DL 失真未闭环 —— 根因=输入参考没设对, 后端 desync 挡住可靠设置)。
- ✗ EMCenter switch 不吃 raw SCPI (EMQuest/GPIB 血统) → 新 **P2-9** (offline)。
- ? 转台 (Aerotech) 测试了但无结论 → 记 **U-5** 供下次。
- backend scpi-command 端点 slow-op desync (`timeout_ms` 没透传给 `driver._query`) → 新 **P1-16**。

> **核心教训重演 (诚实记)**: 现场又一次大量消耗在 driver 层, first-call PDF 没出来。区别是这次用户明确授权修 driver
> (覆盖铁律「现场不写 driver 代码」) → 属用户主动改优先级, 不是失控 drift。补救正是 P0-8: 把 driver 修法 offline
> 落地, 让下次现场回到"只调硬件"。

下次现场 (校准天线 / SGH / 真 DUT 到位) Current Focus 切回依赖链 **P0-4 → P0-3 → P0-5** per WIP=1。

P1-7 (#59) + P1-8 (#61) + P1-9 (#63) + P1-10 (#64) + P2-8 (#68) + P1-11 (#71) 全 merged。
Commissioning →
ChannelEgine 链路第一次形成完整闭环 (P1-7 拆掉 hardcoded mock cluster, 走
24-cluster 38.901; P1-8 加 strict cal gate, frequency-matched 查询跟 measure
phase 对齐; P1-9 加 DUT-attach fail-loud gate; P1-10 关掉 ring-only silent
constraint, non-ring chamber 几何透传 ChannelEgine, 同时收口 P2-7 cross-repo
半)。另 P2-8 (#68) 把主控制台重设计为 4 区操作驾驶舱 (就绪带 / 运行态 / 实时
指标 / 日志+告警), 全接真后端, demo 播放器移到 Diagnostics。另 P1-11 (#71) 加
多子网仪表连接 (runbook 方案 A/B/C + readiness 区分 unreachable vs SCPI-fail +
按子网可达性面板)。最后 P1-12 (#79/#80/#81) 把一批静默兜底 (QZ ripple / reference
TRP / path-loss 未补偿) 改成显著标"未验证(兜底值)" —— 跑完整 mock first-call 时挖到
的。再 P1-13 (#83) 修了 cockpit 子网可达性的假阳性 (preflight 跳过 VISA-only binding
→ never-probed 误标可达), 改成 preflight 走 endpoint 串 + "未探测"三态 —— manual 测试
挖到的。再 P1-15 (#88) 给 preflight 加 canary 负对照: real 模式无设备时透明代理/VPN
会让每个子网假"可达", canary 探到不可路由地址仍"alive"即判网络不可信, 子网回落"未探测" ——
manual 测试挖到的, 且对 5/27 现场直接相关 (现场 Mac 挂 VPN 时面板会拒绝给可达性判定)。WIP=1 释放。

> **本 PR 是 docs catch-up**: PR #88 (P1-15) merged 后 roadmap 没有 P1-15 entry、
> Current Focus 没提 P1-15、Summary 没计 P1-15。本 PR 把 main 矫正: 加 P1-15 entry
> (Done), Current Focus 更新, Summary counts 同步, 并链入 5/27 现场攻略 (per memory
> `feedback_d_row_stale_this_pr_reflex.md` + `feedback_recompute_aggregate_rows_from_parts.md`)。

**on-site / blocked 项 (本地启动不了, 等现场或事件触发) —— 本地可启动 P0/P1/P2
重新归零, 这些都不是 Current Focus**:

| ID | Status | 触发条件 / blocker |
|----|--------|------------------|
| P0-3/4/5 | 🚧 on-site | SA in HAL + on-site CE/SA + DUT + horn |
| P1-2 | 🚧 on-site | F64 license SCPI 现场实测 |
| P1-4 | 🚧 on-site | First-call repeatability (需要稳定 chamber + 完整校准链) |
| P1-5 on-site half | 🚧 on-site | 完整 phase cal certificate generation |
| P1-6 | ⏸️ incident-conditional hold | trigger = 真 idle-close 出现在 FS16/UXM/ENA (当前没证据) |
| P2-4 | 🚧 on-site | NAT/FW idle-drop hypothesis 现场 verify |

**5/27 现场已结束** (产出见上方 Current Focus + 下方 P0-8 / P1-16 / P2-9 + [morning-log](site-debug/2026-05-27-morning-log.md))。
现场没拿到 first-call PDF (又消耗在 F64 driver 层), 但坐实并真机验证了 F64 修法 → 收敛为本地可启动的 **P0-8** (2026-05-28 本地半全部 ✅ Done, 6 个 PR #92/#93/#95/#96/#97/#98 merged)。
silent-failure / readiness-correctness audit 已成体系且 ROI 反复证明 (P1-8 cal gate /
P1-9 DUT / P1-10 ring-only / P1-12 QZ+TRP+path-loss 兜底标记 / P1-13 子网可达性假阳性 /
P1-14 mock 探针拒绝 / P1-15 preflight canary / 一串 drive-by bug fix)。本地审计流收口;
下一轮若再 audit/manual 挖到东西 = candidate for **P1-18**。**P0-8 本地半 / P1-16 (#99) /
Docker durability (#102/#103) 全收口; 下一个 Current Focus 强候选 = P1-17 (UXM fresh-start
配置落地, 本地, 待用户确认启动)** — 所有真 P0 (P0-3/4/5) 仍 on-site blocked, 按 WIP=1
governance 在 P1 队列推进本地可启动项 (P1-17 / P2-10 本地半)。下次现场 (校准天线 / 真 DUT
到位) 按 [`on-site-debug-protocol`](guides/on-site-debug-protocol.md) **必须先切回 P0-4 →
P0-3 → P0-5** (无论本地 P1 状态)。

- **WIP limit: 1**. Only one Current Focus item may be in-progress at a time.
- Anything that's not the Current Focus item and not a triviality (<30 min)
  gets appended to the backlog instead of done inline.

**State (2026-05-17)**: 4-PR flaky-test cleanup batch complete:

| ID | Tests | Root cause | Status |
|----|-------|------------|--------|
| P3-10 ✅ | 1 | alembic chain test hardcoded head SHA | PR #46 merged |
| P3-11 ✅ | 2 | `bootstrap_lifespan` expected-seeder set drifted from new seeders | PR #47 merged |
| P3-12 ✅ | 1 | alembic `fileConfig(disable_existing_loggers=True)` silenced `app.hal.base` for downstream caplog | PR #48 merged |
| P3-13 ✅ | 5 | `probe_calibration_service` tests used `probe_id=100` literal as "invalid" sentinel; 1106cb2 widened `PROBE_ID_MAX` 63→1023 making `100` valid | PR #49 merged |

Full-sweep flaky count: 9 (pre-batch) → 8 (post-P3-10) → 6 (post-P3-11)
→ 5 (post-P3-12) → **0 (post-P3-13)**. Full test suite is clean.

Last review: 2026-05-17 (post Phase-2.3 merge)
Baseline commit: see [announcement](announcements/2026-05-14-roadmap-baseline.md)

---

## 🚧 Blocked on hardware (P0 queue for next on-site)

| ID | Item | Blocker |
|----|------|---------|
| P0-3 | Path-loss calibration (CAL-01) loop closure + cal cert | SA in HAL + on-site CE/SA |
| P0-4 | SignalAnalyzer in HAL for reference TRP | on-site real SA + horn antenna |
| P0-5 | DUT attach → bearer → PDSCH on UXM 5G NR | on-site real DUT |

These are still the highest-priority items overall — they just can't
be progressed from a remote dev box. When the next on-site trip
opens, the Current Focus must move back to P0-3 (or whichever P0 is
unblocked) BEFORE starting any new P1.

> **下次现场执行按 [`docs/guides/on-site-debug-protocol.md`](guides/on-site-debug-protocol.md)
> 走**（现场首测调试协议）。该协议把这些 P0 排成依赖链 **P0-4 → P0-3 → P0-5** 的
> 5 阶段 go/no-go gate（gate 标准 = 上面各 P0 的 acceptance），并固化 CAICT 教训:
> 出发前硬门槛 (mock first-call 跑通 + driver 冻结) + 铁律「现场不写 driver 代码」+
> timebox 救火 + 收工 review + retro 喂回本 roadmap。

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

| ID | Item | Where it landed |
|----|------|----------------|
| D1 | 3 Codex P2 fixes on PRs #12/#13/#14 + Aerotech idle-close reconnect + HAL pre-flight TCP + startup readiness display | PR #14 (merged 2026-05-13) |
| D2 | F64 channel-model GUI + dropdown (Stage 2) + curated-list CRUD endpoints | PR #15 (in review 2026-05-14) |
| D3 | silent-reconnect pattern broadcast to F64 / FS16 / UXM / ENA (PyVISA) | PR #15 |
| D4 | F64 license probe — SYST:INFO? + soft-probe replacement for `*OPT?` + Codex P1 inline error-payload guard | PR #15 |
| D5 | F64 -100 categorizer regression tests + 5/13 team summary | PR #15 |
| D6 | P0-1 — DB auto-bootstrap on FastAPI lifespan startup + PG advisory lock (Codex P1) | PR #17 (merged 2026-05-14) |
| D7 | P0-2 — Lab Profile init wizard + Codex P1 (real UUID via /instruments/catalog) | PR #18 (merged 2026-05-14) |
| D8 | P0-6 — Mock-data first-call end-to-end PDF (fix `execution.test_plan` AttributeError + Codex P2 stale-read) | PR #19 (merged 2026-05-15) |
| D9 | P2-2 — Capability centralisation (`driver.capabilities: Set[str]` + Codex P2 follow-up populating `ce.user_alignment` from F64 connect) | PR #21 (merged 2026-05-15) |
| D10 | P1-1 — Plan-level pre-flight validator + GUI 预检 button (PR #22 backend + PR #23 GUI + PR #24 Codex P1 per-binding endpoint scoping + PR #25 Codex P2 VISA-aware tuple matching with named-resource preservation) | PRs #22/#23/#24/#25 (all merged 2026-05-16) |
| D11 | P1-3 — PyVISA "not installed" investigation: IDE interpreter drift, same root cause as 2026-05-14 IDE-diagnostics backlog | PR #26 (merged 2026-05-16) |
| D12 | Commissioning default-lab fragility (was P1-candidate backlog) — extracted `app/services/lab_resolution.py` with typed `LabResolutionError`, both mimo_ota + trp factories now share it; commissioning API maps ambiguous/none to 422 with picker-ready `active_labs[]` (was 500); GUI `Commissioning/index.tsx` renders lab Select pre-session + recovers from 422 picker payload + localStorage default | PR #27 (merged 2026-05-17) |
| D13 | P2-3 — per-Model static `model_capabilities` ClassVar + catalog API surface + `_real_driver_registry()` lazy module-level helper collapsing the old `SUPPORTED_REAL_DRIVERS` drift; openapi.yaml + GUI generated types synced (Codex P2 fix in same PR). Stale-doc correction here: P2-3 was already in main when this PR (P3-3) started, but PR #28 didn't update its section status; consumed directly by D14 below so the dependency chain stays linked in one place. | PR #28 (merged 2026-05-17) |
| D14 | P3-3 — Capability gap viewer in GUI. Backend extends `PreflightResult` with `bound_models: List[BoundModelDeclaration]` (per-binding static `model_capabilities` from P2-3). GUI: PreflightModal gains "各绑定模型的声明能力" section alongside live `lab_capabilities`; EquipmentManager drawer gains `model_capabilities` badge group next to existing datasheet badges. | PR #29 (merged 2026-05-17) |
| D15 | P3-2 — Driver self-test CLI (`python -m scripts.driver_selftest`). Dumps per-loaded-driver runtime (live `capabilities`, status, endpoint, error) + declared `model_capabilities` + diffs (declared-but-not-live, invariant-breach live-not-declared) in text / json / md formats. Tears HAL down after each run so repeated invocations stay clean. **Codex P1 follow-up in same PR**: introduced `DriverMode.MOCK_FORCE` to override per-instrument `driver_mode='real'` — without it, `--mode mock` was still opening real VISA/TCP to configured hardware (operator safety bug). | PR #30 (merged 2026-05-17) |
| D16 | P3-9 — Widened `api/openapi.yaml`'s `InstrumentModel.status` enum to include `pending_dev` (which the backend has been returning since `_convert_model` started using it). Regenerated `gui/src/types/api.generated.ts`; verified GUI consumers (`App.tsx` status color + label maps) already handled the value via the hand-written `InstrumentStatus` union. Practice run of the 4-step API contract sync flow. | PR #32 (merged 2026-05-17) |
| D17 | P3-4 — Structured `SYST:INFO?` parser for F64 — new `F64SysInfo` dataclass + `parse_f64_sys_info` function extract product_family / channel_count / signal_type / firmware_version / secondary_count / band_label / extra_tokens. F64 `connect()` populates the structured fields (was only extracting channel_count). 21 new parser test cases pin positional + labeled + defensive shapes. | this PR (2026-05-17) |
| D18 | P3-5 — Composite HAL readiness snapshot. New `app/services/readiness.py` aggregates per-driver rows (with `extras` dict — F64 surfaces firmware_version / band_label / product_family via polymorphic `readiness_metadata()` hook) + active LabProfile status + active CalibrationCertificate validity + DUT-attach placeholder. Persisted on HAL service + exposed via `GET /api/v1/instruments/hal/readiness` (+ openapi schemas + TS regen). 20 new tests. | this PR (2026-05-17) |
| D19 | P2-5 — HAL Reload refuse/force policy (A+D from audit). New `app/services/hal_reload_policy.py` with TestPlan blocker finder (running / paused). `POST /hal/reload` returns HTTP 409 with structured blocker payload by default; `?force=true` overrides and marks the success response `forced=true` for audit. Module-level `asyncio.Lock` in `instrument_hal_service.py` serialises shutdown/init across concurrent reload + mode-switch calls (split into `_shutdown_hal_service_inner` / `_initialize_hal_service_inner` + atomic `reload_hal_service_atomic` helper). Shutdown logs at WARNING when drivers are still attached. 15 new tests pin per-status semantics + endpoint refuse/force/empty + lock serialisation. Deferred (with reason): pause+drain registry (B), in-flight diagnostic/SCPI detection (no DB row to query), openapi sync for `/hal/reload` (sibling endpoints precedent). | this PR (2026-05-17) |
| D20 | P2-1 Phase 1 — UXM two-layer architecture (Test App auto-detect + Topology profile operator-managed). `UxmTestProfile` gains `compatible_test_apps` + `is_compatible_with()`; 7 built-ins declare `["5G_NR_Test"]`. `RealUxmDriver` gains `detected_test_app` instance attr, `readiness_metadata()` override (exposes Test App layer to P3-5 panel), `apply_topology_profile(id)` with refuse-on-incompat (structured dict, not raise). HAL service post-connect: persists `detected_test_app` to `connection_params` + auto-applies binding's selected topology. New endpoints: `GET /instruments/{cat}/topology-profiles` (live compat flag per item), `PUT /instruments/{cat}/topology-profile` (refuse with 409 on incompat — `JSONResponse` not `HTTPException(detail=...)` per Codex P2 lesson from PR #35). `api/openapi.yaml` + TS regen. New `TopologyProfileCard` in EquipmentManager drawer (baseStation only, compat-aware option labelling). 23 new tests. Deferred to follow-up chore PRs: name cleanup (`UxmCommandProfile` → `UxmTestApp`), `self._cmds` class-vs-instance fix. Phase 2 (user-custom topology / GUI editor / per-test override) deferred to future P2. | this PR (2026-05-17) |
| D18 | P3-5 — Composite HAL readiness snapshot. New `app/services/readiness.py` aggregates per-driver rows (now with `extras` dict — F64 surfaces firmware_version / band_label / product_family via a polymorphic `readiness_metadata()` hook on `InstrumentDriver`) + active `LabProfile` status + active `CalibrationCertificate` validity + DUT-attach **placeholder** (`not_implemented` — no runtime sensing model exists; surfaced anyway for forward-compat). Snapshot is persisted on the HAL service instance and exposed via `GET /api/v1/instruments/hal/readiness` (also added to `openapi.yaml` + regenerated TS types). 20 new tests pin section semantics + endpoint shape. **Out of scope**: GUI consumption of the new endpoint (sibling HAL endpoints `/hal/status`/`/hal/reload`/`/hal/switch` still consume via inline-typed axios; consistent precedent); DUT-attach sensing implementation (future P3 item). | this PR (2026-05-17) |
| D21 | P2-1 Phase 2.1 — Topology profile DB persistence + operator CRUD. New `instrument_topology_profiles` table (flat-column schema matching `chamber_configurations`, Alembic migration `c7a91b3e5d04`) replaces the in-code-only `UxmTestProfile` dataclass registry as source of truth. New bootstrap seeder `topology_profiles_seeder` inserts 7 built-ins with `is_system_preset=true` (idempotent via natural-key `(profile_id, is_system_preset)`). New service layer `app/services/topology_profile_service.py` exposes `get_dataclass` / `list_rows` / `create` / `update` / `delete` / `duplicate`; system presets reject mutation (clone-to-edit pattern, mirrors chamber). **Driver interface change**: `RealUxmDriver.apply_topology_profile(profile_id: str)` → `apply_topology_profile(profile: UxmTestProfile)` so HAL layer stays DB-free; callers (HAL service post-connect + PUT endpoint) do the DB lookup + pass the dataclass. New endpoints: `POST /instruments/{cat}/topology-profiles` (auto-allocates `custom_<slug>` ID), `PUT /…/{profile_id}` (partial update, 409 on system preset), `DELETE /…/{profile_id}` (409 on system preset), `POST /…/{profile_id}/duplicate` (always operator-owned copy). GET endpoint now reads DB with in-code fallback for greenfield first-boot window. `api/openapi.yaml` + 4 paths + 3 schemas, regenerated TS types, service.ts CRUD wrappers. 24 new tests on top of existing 25 (seeder idempotency + service CRUD + immutability + endpoint flows + DB-vs-fallback list). **Codex P2 follow-up in same PR**: explicit-null on non-nullable field hardening (CREATE skips → defaults; UPDATE raises 400) + `_NULLABLE_MUTABLE_FIELDS` derived from ORM model introspection. **GUI editor deferred to Phase 2.2**. | PR #38 (merged 2026-05-17) |
| D22 | P2-1 Phase 2.3 — Per-plan UXM topology override. New `test_plans.topology_profile_id` column (Alembic migration `d8b412ca9f15`, nullable string ID rather than UUID FK to instrument_topology_profiles so profile delete doesn't block at FK constraint — start-time apply just logs warning and proceeds). `TestExecutionService.apply_plan_topology_profile_if_set` async helper: best-effort apply to the live baseStation driver, all failure modes return a structured dict (`no_plan_override` / `no_live_driver` / `driver_does_not_support_topology_profiles` / `profile_not_found` / `apply_raised` / driver-level `incompatible_test_app`); plan is already RUNNING by the time the apply attempts, so apply failure never fails the start. `POST /test-plans/{id}/start` async-ified to await the apply. New `PUT /test-plans/{id}/topology-profile` dedicated set/clear endpoint mirroring `PUT /instruments/{cat}/topology-profile` binding-level shape. **Codex P2 follow-up in same PR**: `topology_profile_id` carry-through across all three "plan fan-out" paths (`duplicate_test_plan` / `export_test_plans` / `import_test_plans`) — Codex caught duplicate; grep found export+import had same omission; all three fixed together. 21 tests (column persistence + set/clear/validate + 6 reason-value structured-dict shapes + end-to-end start + 5 fan-out preservation). | PR #39 (merged 2026-05-17) |
| D23 | P2-1 Phase 2.2 — Topology editor GUI + per-plan picker. New `TopologyProfileEditor` modal (under `gui/src/features/TopologyProfileEditor/`, distinct from existing `TopologyEditor` for RF switch wiring — namespace clash avoided by Profile suffix) with 7 Paper sections covering 25+ knobs (NR cell / MIMO / power / FRC / MAC throughput / advanced); supports create / edit / read-only-banner-on-system-preset modes. `TopologyProfileCard` (EquipmentManager drawer) gains `+ 新建` + `编辑 / 查看（只读）` + `复制为副本` + `删除` actions with confirm dialog on delete and clone-to-edit affordance on system presets. New backend `GET /api/v1/instruments/{cat}/topology-profiles/{profile_id}` endpoint returns full `TopologyProfileDetail` for the editor to populate the form (list endpoint returns truncated entries); Codex P2 follow-up in same PR added greenfield-first-boot in-code fallback to the new GET (mirrors the list endpoint's `_PROFILE_REGISTRY` fallback) so clicking edit on a built-in before the seeder runs doesn't 404. `EditTestPlanWizard` gains "UXM 拓扑覆盖（计划级，P2-1 Phase 2.3）" Paper section with profile picker — bound to plan via `setPlanTopologyProfile` mutation rather than the generic update PATCH (PATCH filters explicit null, can't clear). 5 new backend tests for the GET endpoint (round-trip / 404 unknown / 404 non-baseStation / greenfield fallback / no-fallback-when-seeded). Backend 79/79 in topology+plan-topology sweeps. With this PR, **all 3 P2-1 sub-items are ✅ Done**. | PR #40 (merged 2026-05-17) |
| D24 | P3-8 — VRT pydantic regression fix (test-discipline cleanup). 28 failing integration tests in `tests/test_road_test_{scenarios,executions,websocket}.py` resolved (root cause: `vrt_service.vrt_test_case_to_scenario` was being called on auto-generated companion `TestCase` rows whose 3-key placeholder `configuration` doesn't satisfy `VirtualRoadTestConfig` — companions exist solely so `TestExecution.test_case_id` NOT NULL FK has a target on legacy scenario-based TestPlans). Fix filters at the service boundary, not the schema: new `is_companion_test_case` helper + `list_vrt_test_cases(include_companions: bool = False)` (default off; companions are not real scenarios) + `vrt_test_case_to_scenario` raises a clean ValueError on companions (not opaque ValidationError) + `_get_custom_scenario` maps companion-id to 404. **Did NOT** modify the companion-creation code in `test_plan_service.py` (rule #4 — companions are intentionally minimal). 9 new SQLite-isolated unit tests in `tests/test_vrt_companion_filter.py` (detection / pagination after filter / refuse semantics). **Codex P2 follow-up in same PR**: replaced "fetch all + Python slice" with bounded-batch fetch — memory now O(batch_size) not O(table); 2 additional tests pin LIMIT-bounded SQL + loop-continues-past-companion-heavy-batches behavior. **Surfaced second-layer issue** (out of scope, promoted to backlog): 2 of the 28 tests flipped from pydantic 500 to `assert 55 == 5` — pre-existing test-isolation bug where VRT integration tests share the dev PG and assume an empty DB; was always broken, masked by the pydantic crash. | PR #41 (merged 2026-05-17) |
| D25 | Out-of-roadmap P0 — HAL real-mode init `UnboundLocalError` on `datetime`. Operator-reported blocker switching HAL mock → real with four unreachable bindings (ENA timeout, RF switch refused, SMW200A timeout, VSG timeout): `_initialize_from_db` crashed with `cannot access local variable 'datetime' where it is not associated with a value`. Root cause: function-local `from datetime import datetime` inside the per-driver success branch made `datetime` a LOCAL name throughout the entire function per Python static scoping, shadowing the module-level import. When zero drivers reached the success branch, the local was never assigned and the readiness-report builder's `datetime.utcnow()` blew up. One-line fix (delete the local import — module-level `datetime` already in scope). 2 new SQLite-isolated regression tests in `tests/test_hal_init_no_drivers.py` (4-binding scenario mirroring the operator's screenshot + degenerate zero-categories) — verified by revert/re-apply that they catch the bug. 54/54 across all `test_hal_*` suites. Out-of-roadmap drive-by, ~30 min including regression test. | PR #42 (merged 2026-05-17) |
| D26 | P3-6 (Type-C `has_lna` test reconciliation) + P3-9 (docs catch-up — engineering already shipped PR #32). **P3-6**: model defined Type-C as a unidirectional chamber compensating downlink path loss via PA (`has_pa=True, pa_gain_db=20.0, has_lna=False`, description "适用于车载 MIMO OTA 测试，配置 PA 补偿下行链路损耗"); 3 tests in `test_chamber_configuration.py` asserted `has_lna=True` — leftover from an older "any large chamber needs LNA" assumption pre-dating the unidirectional/bidirectional refactor (Type-D bidirectional has both LNA and PA because it does TIS). Model is internally consistent + physically correct, so tests were the loser — updated to assert the actual Type-C signature (`has_pa=True, pa_gain_db=20.0, has_lna=False`) which pins what makes Type-C *distinct* rather than asserting an obsolete boolean. **Codex P2 follow-up in same PR**: capability flags must match hardware gates — flipped `supports_trp: True → False` on Type-C because the calibration orchestrator's `UPLINK_CHAIN` gate requires `has_lna`; Type-C was advertising TRP that the orchestrator would refuse at calibration time. Extended tests pin the hardware-vs-capability consistency contract (`get_supported_tests() == ["MIMO_OTA"]` + JSON API round-trip). 27/27 in `test_chamber_configuration.py` (was 24/27); 122/122 across all 6 Type-C-touching test files. **P3-9**: PR #32 (merged 2026-05-17) already shipped the openapi enum widening + TS regen + GUI consumer alignment + round-trip test pinning; roadmap was never updated to mark Done. This PR is the docs catch-up — paired with P3-6 to avoid a one-PR review cycle for a 2-line docs change. | PR #43 (merged 2026-05-17) |
| D27 | P3-7 + 2 discovered-during chores deferred from P2-1. **P3-7**: `.vscode/settings.json` pins venv Python interpreter (`api-service/.venv/bin/python`) + `python.analysis.extraPaths` + pytest auto-discovery; clears the phantom `Cannot find module sqlalchemy / pydantic_settings` diagnostics VSCode was emitting against system Python (same interpreter-drift root cause as P1-3 PyVISA). Gitignore policy: standard JS/Python pattern — `.vscode/*` stays ignored but `!/.vscode/settings.json` whitelisted (personal `launch.json` / `tasks.json` / `sftp.json` don't leak). **`self._cmds` class-vs-instance fix**: `RealUxmDriver` now stores a profile **instance** (`self._cmds: UxmTestApp = ProfileClass()`) instead of the class itself; latent mutability bug — no current write path triggers it but any future `self._cmds.SOME_FIELD = value` would mutate class-level state shared across UXM driver instances. Connect-time profile-switch path uses `isinstance(self._cmds, detected)` instead of `is`; `detect_profile()` still returns the class for caller flexibility. 2 `is` assertions in `tests/test_uxm_driver_profile.py` → `isinstance`; other test fixtures unchanged (attribute-read paths work on class or instance). **Codex P2 follow-up in same PR**: caught a downstream consequence — `app/diagnostics/sequences/uxm_scpi_compatibility.py:_profile_for_driver` gated on `isinstance(profile, type)` so post-refactor IRAT instances fell through to the 5G fallback, false-flagging IRAT commands as unsupported. Helper now accepts either instance or class; downstream `_all_commands` + `_to_probe_command` annotations widened to `Union[type, UxmTestApp]`. 4 new tests in `TestProfileForDriverHelper` pin both branches + verified by revert/re-apply that they catch the bug. **UXM name cleanup**: `UxmCommandProfile` → `UxmTestApp` (the "Test App" is the operator-facing concept = which Keysight software is running), `UxmTestProfile` → `UxmTopologyProfile` (matches the DB table name + GUI vocab). Subclasses (`Uxm5GNRTestAppProfile`, `UxmLteNrIratProfile`) keep their descriptive names. File names unchanged (would touch 19 imports for cosmetic gain only). 155/155 across 8 relevant test suites; full-suite sweep matches main's pre-existing 6-9 flaky failures (none introduced by these changes). | PR #44 (merged 2026-05-17) |
| D28 | VRT integration test isolation (last discovered-during chore deferred from P3-8). Three VRT integration test files (`test_road_test_{scenarios,executions,websocket}.py`) ran against the **shared dev Postgres**, accumulating 50+ leftover VRT TestCases over time and breaking assertions like `len(scenarios) == 5` and `all(s["category"] == "standard" for s in scenarios)`. Was always broken; the P3-8 pydantic crash had been masking it. Fix per-file `_isolated_db` autouse fixture that overrides `get_db` with an in-memory SQLite TestingSessionLocal (same pattern as `test_uxm_topology_profile.py` / `test_plan_topology_override.py`). **Caveat for the websocket file**: the WS endpoint handler at `road_test.py:1312` imports `SessionLocal` directly inside the function (FastAPI's `Depends(get_db)` doesn't apply to WebSockets), so the fixture also monkeypatches `app.db.database.SessionLocal` so the function-level re-import picks up the test session — without this all 7 WS tests fail with "Execution not found" because the lookup hits the real configured DB. Result: 40/40 in the 3 integration suites (was 28 failed / 12 passed pre-PR #41, then 2 failed / 38 passed post-PR #41, now 40/40). Full-suite sweep matches main's pre-existing 9 flaky failures (none introduced by this PR). After this PR merges, all discovered-during backlog items are resolved; only on-site-blocked P0/P1 work remains on the roadmap. | PR #45 (merged 2026-05-17) |
| D29 | P3-10 — alembic chain head hardcoded SHA (1 of 4 in the flaky-test cleanup batch). `tests/test_alembic_chain.py::test_greenfield_upgrade_from_scratch` asserted `version_num == "e863f092696b"` (hardcoded constant from when the test was written); PRs #28/#38/#39 then added 3 migrations (`a1b2c3d4e5f6` / `c7a91b3e5d04` / `d8b412ca9f15`) and the constant rotted. **Structural fix** (B not A): replaced the hardcoded SHA with `ScriptDirectory.from_config(cfg).get_current_head()` so the test asserts its actual intent ("DB reaches alembic head") rather than "DB reaches specific SHA X" — same "fix the test's structure, not just the value" pattern as P3-6's Type-C signature pinning. Verified by revert/re-apply: temporarily appended `_FAKE` to the expected head, assertion correctly failed; restored, all 3 tests in `test_alembic_chain.py` pass. Full-sweep flaky count 9→8. **Also promotes P3-11/12/13 to the open roadmap as P3 slots** so the rest of the batch has explicit Current Focus targets per WIP=1 sequencing; this PR's Current Focus shifts to P3-11 after merge. | PR #46 (merged 2026-05-17) |
| D30 | P3-11 — bootstrap_lifespan seeder set drift (2 of 4 in the flaky-test cleanup batch). 2 tests in `tests/test_bootstrap_lifespan.py` failed on clean main: `test_bootstrap_history_records_each_seeder` (expected set missing `"topology_profiles"`) and `test_second_lifespan_is_idempotent` (`assert 7 == 6`). Root cause: PR #38 (P2-1 Phase 2.1) added the `topology_profiles` seeder to the bootstrap registry without updating these test expectations. **Value drift** (not structural — count and set are intrinsically tied to a fixed registry), same family as P3-6. Fixed by adding `"topology_profiles"` to the expected set + bumping `6 → 7`; tagged both with comments naming PR #38 so future seeder additions get a clearer "bump these too" signal. Verified by revert/re-apply: replaced `7` with `999` sentinel, assertion correctly failed (`assert 7 == 999`). 9/9 in `test_bootstrap_lifespan.py`; full-sweep flaky count 8 → 6. Current Focus shifts to P3-12 after merge. | PR #47 (merged 2026-05-17) |
| D31 | P3-12 — driver_capabilities test-isolation pollution (3 of 4 in the flaky-test cleanup batch). `tests/test_driver_capabilities.py::TestDriverBaseCapabilitySet::test_non_canonical_token_warns_but_adds` passed alone but failed in full sweep with `AssertionError: []` (caplog captured zero records). **Bisect**: narrowed polluter to `test_alembic_chain.py` (single test reproduces it). **Root cause**: `alembic/env.py:35` calls `logging.config.fileConfig(config.config_file_name)` which defaults to `disable_existing_loggers=True` — every already-imported logger (including `app.hal.base`, populated when pytest collects sibling modules that import HAL drivers) has its `disabled` flag flipped to `True`, silently dropping all subsequent log records and starving downstream `caplog`-based tests. Production alembic runs via CLI in a fresh process where there is nothing to disable, so the leak is pure pytest-in-process pollution — fix scoped to the test file rather than modifying `env.py` (preserves CLI behavior untouched, matches P3-10's "fix at the right layer" pattern). **Fix**: autouse fixture in `test_alembic_chain.py` snapshots every existing logger's `disabled` flag pre-test and restores on teardown. Verified by revert/re-apply: stashed the fixture, `test_alembic_chain.py + test_non_canonical_token_warns_but_adds` reproduced the failure; restored, both pass. Full-sweep flaky count 6 → 5 (only the 5 P3-13 `probe_calibration_service` mock failures remain). Current Focus shifts to P3-13 after merge. | PR #48 (merged 2026-05-17) |
| D32 | P3-13 — probe_calibration_service invalid-probe sentinel drift (4 of 4 in the flaky-test cleanup batch; closes the batch). 5 tests in `tests/test_probe_calibration_service.py` (`test_execute_calibration_invalid_probe` / `test_execute_phase_calibration_invalid_probe` / `test_execute_phase_calibration_invalid_reference` / `test_execute_polarization_calibration_invalid_probe` / `test_execute_pattern_calibration_invalid_probe`) all failed with `assert True is False`. **Root cause** (`git log -S` on `PROBE_ID_MAX = 1023` pinpointed commit 1106cb2 dated 2026-05-05 "Phase 2a 真校准链路接通"): the tests hardcoded `probe_ids=[100]` / `reference_probe_id=100` as their "deliberately invalid" sentinel back when `PROBE_ID_MAX = 63`; the Phase-2a commit widened it to 1023 (probe arrays grew) without updating these tests, so `100` became a valid id and `success` flipped `False → True`. Same family of **value drift** as P3-6 (Type-C `has_lna`) and P3-11 (seeder count) — model widened, test sentinel stale. **Structural fix** (B, not A): imported `PROBE_ID_MAX` from the service and replaced all 5 literal `100` sentinels with `PROBE_ID_MAX + 1`, so the tests now pin the validator's actual contract ("anything past the upper bound is rejected") rather than a magic number — future widening can't reintroduce this drift. Added a comment at the first call site naming the original drift cause so the choice is grep-able. Verified by revert/re-apply: stashed the fix, all 5 reproduced; restored, 126/126 in `test_probe_calibration_service.py`. **Full-sweep flaky count 5 → 0 — entire test suite is clean (1176/1176 + 2 skipped)**; closes the 4-PR flaky-test cleanup batch. After this PR merges, roadmap enters "waiting on next on-site trip" mode — Current Focus stays empty until the next on-site, at which point it must move to P0-3 (or whichever P0 is unblocked first). | PR #49 (merged 2026-05-17) |
| D33 | P3-1 — HAL Reload two-stage confirm dialog (GUI polish, only remaining non-blocked P3). Pre-fix `handleHALReload` POSTed `/instruments/hal/reload` immediately on click — accidental clicks mid-test would tear down VISA sessions and crash the in-flight diagnostic. P2-5 (PR #35) had already shipped backend-side refuse-while-in-flight (HTTP 409 + `HalReloadRefusedResult{blockers, force_hint}`) plus `?force=true` override, but the GUI ignored it: any 409 surfaced as the raw error string in `__hal__` feedback, no force option offered. **Fix** (two-stage flow): stage 1 always shows `modals.openConfirmModal` ("将会断开并重新初始化所有仪器驱动...") before the POST — accidental-click guard. Stage 2 only fires when the POST returns 409 with the structured `refused` body: a second `openConfirmModal` lists each blocker (`name` + `status`) in red and offers a "强制重新加载" button that re-POSTs with `?force=true`. Success feedback distinguishes forced (`⚠️ 已强制重新加载`) from clean (`✅ 已重新加载`) so audit-log scan stays grepable. Extracted the actual POST into `performHALReload(force: boolean)` so both entry points share the same success / cache-invalidation / 5xx-fallback paths. **Verification**: type-check + production build clean; backend 3-way smoke (no-blocker 200, with-running-plan 409 + structured body, `?force=true` 200 with `forced: true`) all match the GUI's consumption shape. Modal pattern matches the existing `ScenarioCard.tsx:113` delete-confirm idiom. **Did NOT click the button in a real browser** — no GUI test framework in the project; the implementation risk is mostly visual/ergonomic, recommend operator does a smoke click after merge. After this PR, only P1-5 local half remains as a non-blocked remote-doable item; the other 7 open items are all on-site. | this PR (2026-05-17) |

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

### P0-3 — Path-loss calibration (CAL-01) loop closure + cal cert generation 🚧 Blocked on-site

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

**Status**: `[ ]` not started — needs SA in HAL (P0-4) + on-site
**Estimate**: on-site 1 day + local 0.5 day

---

### P0-4 — SignalAnalyzer in HAL for reference TRP 🚧 Blocked on-site

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

**Status**: `[ ]` not started — `RealRsFsvaDriver` exists + registered
(`signalAnalyzer→FSVA3000`) + seeded; needs on-site connection + model
select. No driver work on-site (cardinal rule 1).
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
- ≥1 seeded step template ships with a real `needs` declaration as
  dogfood proof (F64 calibration-tone → `ce.interference_generator`).
- GUI plan row gains a "预检" button calling the endpoint and
  showing gap details in a Mantine Modal (PR B).

**Implementation split (2026-05-16)**:
- **PR A** — backend: column + validator + endpoint + seed update +
  tests. Independently usable via curl.
- **PR B** — GUI: button + Mantine Modal listing gaps. Lands after PR A.

**Status**: ✅ Done — see D10 in the Done table. All four PRs in main:
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

**Status**: ✅ Done — see D13 in the Done table. PR #28 + Codex P2 follow-up
commit (contract sync: openapi.yaml + regen TS types) both in main.
**Estimate**: 1.5 days (actual: ~3 hours)

### P2-4 — NAT/firewall idle-drop hypothesis verification

**What**: TCP keepalive on Aerotech was added on the *assumption* that
CAICT's NAT/firewall drops idle TCP entries. Never verified. Run an
idle-then-poke test to confirm.

**Status**: `[ ]` not started
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

## 🟢 P3 — Polish / tooling

### P3-1 — HAL Reload confirm dialog ✅ Done (this PR)

**What**: pre-fix `handleHALReload` in `gui/src/App.tsx` POSTed `/instruments/hal/reload` on click with no confirmation. Accidental click mid-test torched VISA sessions; the P2-5 backend refuse (HTTP 409 + `HalReloadRefusedResult`) was reduced to a raw error string in feedback, no force-override exposed.

**Fix**: two-stage modal flow using the project's existing `modals.openConfirmModal` pattern (matches `ScenarioCard.tsx:113`). Stage 1 always confirms intent before POST (accidental-click guard). Stage 2 only fires on backend 409 — surfaces each blocker (`name` + `status`) in a red dialog and offers `强制重新加载` which re-POSTs with `?force=true`. Extracted shared logic into `performHALReload(force: boolean)`.

**Verification**: type-check + production build clean; backend 3-way smoke (no-blocker / 409 with running plan / `?force=true`) returns the exact `HalReloadResult` / `HalReloadRefusedResult` shapes the GUI consumes. Did NOT click in browser — no GUI test framework in project; smoke click recommended after merge.

**Status**: ✅ Done — this PR
**Estimate**: 0.5 day (actual: ~30 min — backend was already shaped for this; GUI was the one missing piece)

### P3-2 — Driver self-test CLI ✅ Done (see D15)

**What**: `python -m scripts.driver_selftest` initialises HAL in the
same way FastAPI's lifespan does, dumps per-loaded-driver state to
stdout, then tears HAL down clean.

**Why**: GUI's HAL readiness table is a one-line-per-driver summary;
it doesn't surface canonical capability tokens (live P2-2
`driver.capabilities` + declared P2-3 `DriverClass.model_capabilities`).
For on-site debugging the operator wants to slack-paste "this is
what HAL came up with" without screenshotting the GUI, and for
offline review (post-trip log analysis) JSON output is the right
input to triage tooling.

**Acceptance**:
- New `api-service/scripts/driver_selftest.py` (single-file CLI,
  no new dependencies)
- Three output formats via `--format text|json|md` — text for
  terminal, json for `| jq` piping, md for slack/issue paste
- `--mode mock|real` selects HAL bootstrap mode (default mock so
  the script never accidentally hits hardware)
- `--category KEY` filters to one binding when only one matters
- Exit codes: 0 success, 1 HAL init raised, 2 init OK but 0 drivers
- Per-driver report surfaces both capability surfaces + the diff
  (`declared_but_not_live`, `live_but_not_declared`) so vocabulary
  drift between code + driver is visible at a glance

### P3-3 — Capability gap viewer in GUI ✅ Done (see D14)

**What**: Surface the static capability declarations (P2-3
`model_capabilities`) in the GUI so the operator sees gaps at
binding-edit time and in the pre-flight modal, not only after HAL
Reload.

**Why**: Today picking FS16 as channelEmulator for a plan needing
`ce.interference_generator` silently passes binding validation; the
mismatch only surfaces after HAL Reload (live `driver.capabilities`
comes back empty). With the catalog already carrying the declared
tokens (P2-3), the GUI can warn earlier.

**Acceptance**:
- Backend extends `PreflightResult` with `bound_models: List[BoundModelDeclaration]`
  (one entry per `lab.instrument_bindings` row, with category +
  model_name + sorted model_capabilities).
- Endpoint serializes the new field as `BoundModelDeclarationResponse`.
- PreflightModal renders the entries in a collapsible "各绑定模型的声明能力"
  section paralleling the existing "Lab 提供的能力" (LIVE) collapse,
  so operator can compare declared vs live.
- EquipmentManager drawer renders `model_capabilities` as a `blue`
  Badge group beneath the existing freeform datasheet badges so the
  binding picker UI shows canonical tokens too.
- Tests: 9 new backend cases pinning bound_models shape + HTTP
  serialization edge cases (binding without model, unregistered
  model, stable sort, independence from HAL state).

**Status**: ✅ Done — see D14 in the Done table. PR #29 merged 2026-05-17.
**Estimate**: 1 day (actual: ~3 hours, backend reuse from P2-3 made
the GUI work the bulk of it)

### P3-4 — F64 SYST:INFO? structured parser

**What**: Parse the full PROPSIM F64 `SYST:INFO?` response (was only
extracting `parts[1]` for channel count) into a structured dataclass
covering product_family, channel_count, signal_type, firmware_version,
secondary_count, band_label, and `extra_tokens` for forward-compat.

**Why**: Pre-P3-4 the F64 driver threw away firmware version, band
coverage, and the license keywords that follow position [4]. On-site
debugging needed those — operator had to read SCPI transcripts to
confirm what firmware they were talking to. Structured parse surfaces
the metadata to the readiness report (and via P3-2's
`driver_selftest` CLI). The keyword-scan license-discovery path in
`_probe_installed_options()` is unchanged (separate concern).

**Acceptance**:
- New `F64SysInfo` frozen dataclass + `parse_f64_sys_info` function
  in `app/hal/propsim_f64.py`
- F64 `connect()` calls the parser, populates `sys_info` +
  convenience attrs (`firmware_version`, `band_label`,
  `product_family`)
- 21 test cases in new `tests/test_propsim_f64_sys_info_parser.py`
  covering: positional extraction, labeled extraction (Band:
  case-insensitive), defensive shapes (empty/None/whitespace/
  skinny/non-int positions), raw preservation, fixture round-trip
- Zero regression in F64 + diagnostic test bundle (176/176)
- **NOT in scope**: FS16 has its own `_parse_sys_info` method —
  deliberately NOT refactored to share (Rule 4: no 顺手优化).
  Future PR can dedupe if FS16 picks up more fields.

**Status**: `[≈]` in review — this PR
**Estimate**: 0.5 day (actual: ~30 min)

### P3-5 — Startup readiness summary expansion

**What**: Pre-P3-5 the only "is the chamber ready?" surface was a
per-driver table logged once to stdout during HAL init; lab-profile
state, calibration validity, and any driver-specific metadata
(firmware version, band coverage from P3-4) were either invisible or
required separate API calls + manual cross-referencing. P3-5 unifies
these into a single composite snapshot persisted on the HAL service
and exposed via `GET /api/v1/instruments/hal/readiness`.

**Why**: Operators on-site lose minutes per debugging round grepping
mixed logs to answer "is the lab fully ready?" — the answer is now
a single `available + status` JSON. Surface gives the future GUI HAL
panel + Slack `curl | jq` triage one source of truth instead of three.

**Acceptance**:
- New `app/services/readiness.py` with `ReadinessReport` dataclass
  (drivers + lab_profile + calibration + dut_attach sub-sections)
  and pure SQL helpers `build_lab_profile_readiness` /
  `build_calibration_readiness` / `build_dut_attach_readiness`
  (no HAL coupling — tests synthesise DB rows directly).
- Per-driver rows gain an `extras` dict populated from a new
  polymorphic `InstrumentDriver.readiness_metadata()` hook; F64
  overrides to surface `firmware_version` / `band_label` /
  `product_family` from P3-4's parsed `sys_info`.
- HAL service stores the snapshot on `self.last_readiness_report`,
  refreshed on each `initialize()` / reload. `_log_readiness_report`
  prints the three new sections under the driver table.
- New `GET /api/v1/instruments/hal/readiness` endpoint + Pydantic
  response models; `openapi.yaml` schemas added (`HALReadinessResponse`,
  `DriverReadinessRow`, `LabProfileReadiness`, `CalibrationReadiness`,
  `DutAttachReadiness`); TS types regenerated.
- `available=false` placeholder path: when HAL hasn't initialised
  yet the endpoint returns a shaped response (all sub-sections
  present with placeholder details) instead of 404 — GUI never
  has to handle missing-field cases.
- 20 new tests in `tests/test_hal_readiness.py` covering: lab
  status branches (missing/inactive/ok/ambiguous), cal status
  branches (no_lab/missing/valid/expired), DUT-attach placeholder,
  F64 extras via `readiness_metadata`, base driver empty default,
  endpoint serialisation (available true + false), null-field
  preservation in JSON.
- **NOT in scope** (explicit deferral, see Out-of-scope below).

**Out of scope** (deliberate):
- GUI consumption of the new endpoint (panel that renders the
  snapshot). Sibling HAL endpoints (`/status` / `/reload` /
  `/switch`) all consume via inline-typed `axios.get` rather than
  generated types — consistent precedent. GUI panel is a separate
  P3-? item if/when an operator asks for it.
- DUT-attach sensing implementation. No runtime model exists
  (no probe-sensing / chamber-RFID / session table). Field is
  surfaced as `status="not_implemented"` so the contract is
  forward-compatible when sensing lands later (probably ties to
  a future positioner-driven probe-presence detection).
- FS16 / Aerotech / other drivers overriding `readiness_metadata`.
  Hook is in place, default empty is honest about not having
  parsed extras. Future PRs override when there's metadata worth
  exposing (Rule 4: no "顺手" overrides without driver-specific
  signal to surface).

**Status**: `[≈]` in review — this PR
**Estimate**: 0.5 day (actual: ~2 hours)

### P3-6 — Chamber preset Type-C `has_lna` test reconciliation ✅ Done

**What**: `tests/test_chamber_configuration.py::TestChamberPresets::test_preset_type_c_exists` plus the two `test_create_chamber_from_preset` variants failed on clean `main` (pre-existing). `has_lna` on the Type-C preset is False but the tests asserted True.

**Triage**: model is correct; tests were the loser. Model defines Type-C as a unidirectional chamber that compensates downlink path loss via a PA on the TX path — no LNA on RX since uplink isn't tested in this config (`has_pa=True, pa_gain_db=20.0, has_lna=False`, description: "适用于车载 MIMO OTA 测试，配置 PA 补偿下行链路损耗"). Type-D bidirectional has both LNA and PA because it does TIS (uplink sensitivity). The model is internally consistent (description / `has_pa` / `pa_gain_db` all agree) and physically correct; tests looked like leftover from an older "any large chamber needs LNA" assumption that pre-dated the unidirectional/bidirectional refactor.

**Fix**: updated the 3 tests to assert the Type-C signature (`has_pa=True, pa_gain_db=20.0, has_lna=False`) instead of the obsolete `has_lna=True` expectation. Tests now pin what makes Type-C *distinct* (PA-only, downlink-only) rather than asserting a random boolean.

**Acceptance**:
- 27/27 in `test_chamber_configuration.py` (was 24/27)
- Type-C preset signature pinned in tests so any future drift (someone "fixes" the model back to `has_lna=True`) trips a clear assertion failure rather than a silent semantic shift

**Status**: ✅ Done — this PR
**Estimate**: ~30 min (actual: ~15 min)

### P3-7 — VSCode interpreter settings + `.vscode/` gitignore policy ✅ Done

**What was wrong**: VSCode resolved Python imports against system Python 3.13 (`/opt/homebrew/lib/python3.13/site-packages`) instead of the project venv at `api-service/.venv/`. Every Python edit emitted phantom `Cannot find module sqlalchemy / pydantic_settings / sqlalchemy.orm` diagnostics — same interpreter-drift root cause as P1-3's PyVISA investigation. Tests passed fine; IDE noise hid real type errors when they surfaced.

**Policy decided**: standard JS/Python ecosystem pattern — keep `.vscode/` ignored by default (personal `launch.json` / `tasks.json` / `sftp.json` don't belong in the repo) but **whitelist `settings.json`** as the one file with team-wide value. `.gitignore` changed from `/.vscode` (whole dir) to `/.vscode/*` + `!/.vscode/settings.json`.

**Fix**: `.vscode/settings.json` pins the venv interpreter + `python.analysis.extraPaths` for cross-folder imports + pytest auto-discovery config. No personal prefs (theme, font, keybindings, sftp targets) shipped.

**Acceptance**: gitignore policy decided + documented (in the commit message + this entry); `.vscode/settings.json` committed; `git check-ignore` confirms only `settings.json` un-ignored; phantom imports clear on a fresh VSCode open.

**Status**: ✅ Done — this PR
**Estimate**: ~10 min code + decision (actual: ~10 min)

### P3-8 — VRT pydantic regression fix ✅ Done

**What**: `tests/test_road_test_*.py` (executions / scenarios / websocket) had 28 failures (roadmap originally said 38 — actual count was 28 on this branch) on clean `main` — every call into `GET /road-test/scenarios` blew up with `VirtualRoadTestConfig` Pydantic v2 ValidationError reporting 8 required fields missing (`mode` / `category` / `network` / `base_stations` / `route` / `environment` / `traffic` / `kpi_definitions`).

**Root cause** (neither model fields nor scenario seeder — both were correct in isolation): `TestPlanService._create_road_test_steps` auto-creates a **companion `TestCase`** row with `test_type='VirtualRoadTest'` and a 3-key placeholder `configuration={auto_generated: True, scenario_id, steps_count}` so `TestExecution.test_case_id` (NOT NULL FK) has a valid target on legacy scenario-based TestPlans. `_list_custom_scenarios` enumerated **all** VRT TestCases including those companions, calling `vrt_service.vrt_test_case_to_scenario` on each. Companions don't satisfy the schema (and aren't supposed to — they're FK-target placeholders, not user-facing scenarios), so the conversion crashed for any DB with ≥1 companion row, returning HTTP 500 to all 28 integration tests.

**Fix** (chose to filter at the service boundary, not weaken the schema): new `is_companion_test_case(tc)` helper in `vrt_service.py` encapsulates the detection rule; `list_vrt_test_cases` gains `include_companions: bool = False` parameter (default off — companions are not real scenarios; filter applied in Python after ordering, before `LIMIT`, so paging reflects real-scenario counts not raw row counts); `vrt_test_case_to_scenario` raises `ValueError` with explicit cause + alternative API when called on a companion (instead of opaque ValidationError); `_get_custom_scenario` in `road_test.py` maps a companion-id GET to a clean 404. **Did NOT modify** the companion-creation code in `test_plan_service.py` — companions are intentionally minimal (only need to satisfy the FK); adding required fields would be hindsight bloat per rule #4.

**Surfaced second-layer issue** (out of P3-8 scope; promoted to backlog): 2 of the original 28 failures (`TestScenarioList::test_list_all_scenarios` / `test_filter_by_category`) flipped from pydantic 500 to a different failure class — `assert 55 == 5` (test assumes DB has only the 5 standard scenarios, dev PG has 50 accumulated VRT TestCases from prior dev/test runs). These were always broken but **masked** by the pydantic crash. Pure test-isolation problem; needs its own triage (move VRT integration tests onto an isolated test DB or seed-and-reset fixture). See "Discovered during" below.

**Acceptance**:
- 28 pydantic-regression failures in `tests/test_road_test_{scenarios,executions,websocket}.py` resolved (28 → 2 fails of a different kind, see above)
- 9 new tests in `tests/test_vrt_companion_filter.py` pinning the contract: `is_companion_test_case` detection rules (4) + `list_vrt_test_cases(include_companions=...)` default + opt-in + pagination after filter (3) + `vrt_test_case_to_scenario` companion-refuse with clean ValueError + real-vrt round-trip (2)
- SQLite-isolated unit tests (no shared PG dependency)
- No schema weakening — `VirtualRoadTestConfig` stays strict
- No change to companion-creation flow in `test_plan_service.py`

**Status**: ✅ Done — this PR
**Estimate**: ~1 hour (actual: ~1 hour including a second-layer surface)

### P3-9 — Catalog `status` enum contract drift ✅ Done

**What**: `GET /api/v1/instruments/catalog` returned `status: "pending_dev"` for models without a registered real driver (`_convert_model` in `app/api/instrument.py`), but `api/openapi.yaml`'s `InstrumentModel.status` enum was `[available, reserved, maintenance, offline]` — `pending_dev` was added on the backend without contract update. Same drift class Codex P2 caught on PR #28 (PR #28 only fixed `model_capabilities`, deferred this one).

**Fix** (shipped in PR #32, merged 2026-05-17): widened the openapi enum to `[available, reserved, maintenance, offline, pending_dev]` with explicit per-value semantics docstring; regenerated `gui/src/types/api.generated.ts`; hand-written `gui/src/types/api.ts` `InstrumentStatus` union also includes `pending_dev`; GUI consumer in `App.tsx` handles `pending_dev` with operator-facing label "驱动未实现" and red color. Round-trip pinned by `test_instrument_catalog_model_capabilities.py::test_pending_dev_status_passes_through` (status string survives the full Pydantic serialize → JSON round-trip).

**Why this is in P3-6 PR not its own**: PR #32 fully shipped the engineering, but the roadmap's P3-9 section was never marked Done — status stayed `[≈] in review — this PR` with no PR actually in flight. This is purely a docs catch-up; pairing with P3-6 to avoid a one-PR review cycle for a 2-line docs change.

**Acceptance**:
- openapi enum + TS types + GUI consumer + round-trip test all aligned (PR #32)
- roadmap accurately reflects shipped state (this PR)

**Status**: ✅ Done — engineering in PR #32, roadmap docs catch-up in this PR
**Estimate**: ~15 min engineering (actual PR #32: ~10 min) + 2 min docs catch-up

### P3-10 — Alembic chain head hardcoded SHA ✅ Done

**What**: `tests/test_alembic_chain.py::test_greenfield_upgrade_from_scratch` hardcoded the expected migration head SHA (`"e863f092696b"`). When PR #28 / #38 / #39 added 3 new migrations (`a1b2c3d4e5f6` / `c7a91b3e5d04` / `d8b412ca9f15`), the constant wasn't bumped → test failed `AssertionError: assert 'd8b412ca9f15' == 'e863f092696b'`.

**Triage**: test had a *structural* mistake, not a value drift — the hardcoded SHA pattern guarantees breakage on every future migration. The test's intent per the docstring is "DB reaches head", not "DB reaches specific SHA X".

**Fix** (B not A): replace the hardcoded SHA with `ScriptDirectory.from_config(cfg).get_current_head()` — asks alembic what the current head is, asserts DB matches. Doesn't drift on new migrations. 1-line behaviour change + import. Same "fix the structure, not the value" pattern as P3-6 (Type-C signature pinning).

**Verified by revert/re-apply**: temporarily appended `"_FAKE"` to the expected head; the assertion correctly failed (`assert 'd8b412ca9f15' == 'd8b412ca9f15_FAKE'`), confirming the gate isn't tautological.

**Acceptance**: 3/3 in `test_alembic_chain.py`; full sweep 9→8 pre-existing failures.

**Status**: ✅ Done — this PR
**Estimate**: 20-40 min (actual: ~15 min)

### P3-11 — bootstrap_lifespan seeder set drift ✅ Done

**What**: 2 tests in `tests/test_bootstrap_lifespan.py` failed on clean main:
- `TestLifespanColdStart::test_bootstrap_history_records_each_seeder` — expected seeder set was missing `"topology_profiles"`
- `TestLifespanWarmRestart::test_second_lifespan_is_idempotent` — `assert 7 == 6` (one more seeder in registry than test expected)

**Triage** (confirmed root-cause prediction): PR #38 (P2-1 Phase 2.1) added the `topology_profiles` seeder to the bootstrap registry; both test expectations weren't updated. Test was the loser — seeder is real and shipped. Value drift, same family as P3-6 (Type-C `has_lna`) — *not* structural like P3-10.

**Fix**: added `"topology_profiles"` to the expected set + bumped `6` → `7`. Tagged both with comments noting PR #38 origin so the next seeder addition gets a clearer "you need to bump these too" signal.

**Verified by revert/re-apply**: temporarily replaced `7` with `999` sentinel; assertion correctly failed (`assert 7 == 999`); restored, all 9 tests in `test_bootstrap_lifespan.py` pass.

**Acceptance**: 9/9 in `test_bootstrap_lifespan.py`; full sweep 8 → 6.

**Status**: ✅ Done — this PR
**Estimate**: 15-20 min (actual: ~10 min — root cause confirmed on first reproduce)

### P3-12 — driver_capabilities test-isolation pollution ✅ Done (this PR)

**What**: `tests/test_driver_capabilities.py::TestDriverBaseCapabilitySet::test_non_canonical_token_warns_but_adds` passed alone but failed in full sweep with `AssertionError: []` — `caplog.records` was empty.

**Root cause** (bisect narrowed polluter to `test_alembic_chain.py`): `alembic/env.py:35` calls `logging.config.fileConfig(config.config_file_name)` which defaults to `disable_existing_loggers=True`. Every already-imported logger (including `app.hal.base`, populated by sibling tests that import HAL drivers) gets its `disabled` flag flipped to `True`, silently dropping every subsequent log record.

**Why test-scoped fix, not env.py**: production runs alembic via CLI in a fresh process where there is nothing to disable — the disable-spread is purely a pytest-in-process artifact. Changing env.py would alter CLI behavior to satisfy a test-only concern; containing the pollution at the source (the polluting test file) keeps production behavior identical. Same "fix at the right layer" pattern as P3-10.

**Fix**: autouse fixture in `test_alembic_chain.py` snapshots every existing logger's `disabled` flag pre-test and restores on teardown.

**Verified by revert/re-apply**: stashed the fixture, `test_alembic_chain.py + test_non_canonical_token_warns_but_adds` reproduced the failure (`AssertionError: []`); restored, both pass.

**Acceptance**: failing test passes in full sweep; flaky count 6 → 5; only P3-13's 5 `probe_calibration_service` failures remain.

**Status**: ✅ Done — this PR
**Estimate**: 30-45 min (actual: ~25 min — bisect narrowed in 4 runs)

### P3-13 — probe_calibration_service invalid-probe sentinel drift ✅ Done (this PR)

**What**: 5 tests in `tests/test_probe_calibration_service.py` all failed with `assert True is False`:
- `TestAmplitudeCalibrationService::test_execute_calibration_invalid_probe`
- `TestPhaseCalibrationService::test_execute_phase_calibration_invalid_probe`
- `TestPhaseCalibrationService::test_execute_phase_calibration_invalid_reference`
- `TestPolarizationCalibrationService::test_execute_polarization_calibration_invalid_probe`
- `TestPatternCalibrationService::test_execute_pattern_calibration_invalid_probe`

**Root cause** (one shared cause as the symptom uniformity suggested — but **not** mock pattern): all 5 tests hardcoded `probe_ids=[100]` / `reference_probe_id=100` as their "deliberately invalid" sentinel when the service's range was `PROBE_ID_MIN..PROBE_ID_MAX = 0..63`. Commit 1106cb2 (2026-05-05, "Phase 2a 真校准链路接通") widened `PROBE_ID_MAX` to 1023 for larger probe arrays — `100` became valid, the service completed the calibration, and `assert result.success is False` flipped. Same **value drift** family as P3-6 (Type-C `has_lna`) and P3-11 (seeder count) — model widened, test sentinel stale.

**Fix** (structural, B): imported `PROBE_ID_MAX` from the service and replaced all 5 literal `100` sentinels with `PROBE_ID_MAX + 1`, so the tests pin the validator's actual contract ("anything past the upper bound is rejected") rather than a magic number. Added a comment at the first call site naming 1106cb2 as the original drift cause so the choice is grep-able. Future widening can't reintroduce this drift.

**Verified by revert/re-apply**: stashed the fix, all 5 reproduced (`assert True is False`); restored, 126/126 in `test_probe_calibration_service.py`; **full sweep 1176/1176 + 2 skipped, 0 flaky**.

**Acceptance**: ✅ all 5 pass; ✅ full sweep clean; ✅ closes the 4-PR cleanup batch.

**Status**: ✅ Done — this PR
**Estimate**: 30-60 min (actual: ~15 min — `git log -S "PROBE_ID_MAX = 1023"` pinpointed the widening commit on the first try)

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

> **Triage history**: 2026-05-17 — promoted 4 active entries to P3
> slots (P3-6: chamber preset Type-C test reconciliation; P3-7: VSCode
> interpreter settings + `.vscode/` policy; P3-8: VRT pydantic
> regression; P3-9: catalog status enum drift). Resolved entries kept
> below for audit trail.
>
> **2026-05-27 — 用户直接 triage 4 个现场发现** (现场授权, 非 weekly review): F64 driver
> 修法 → **P0-8** (升 Current Focus, 本地); backend scpi-command desync → **P1-16** (本地);
> EMCenter switch → **P2-9** (调研+现场); 转台无结论 → **U-5** (Known-unknown)。

- ~~`[discovered 2026-05-15 during P2-2]` **Commissioning factory's "default lab" path is fragile**~~. ✅ Resolved 2026-05-16 — see D12 in Done table.
- ~~`[discovered 2026-05-14 during P0-1]` chamber preset Type-C `has_lna` test mismatch~~. → Promoted to **P3-6** (2026-05-17 triage).
- ~~`[discovered 2026-05-14 during P0-2]` VSCode Python interpreter drift~~. → Promoted to **P3-7** (2026-05-17 triage).
- ~~`[discovered 2026-05-17 during P2-3]` VRT pydantic regression (38 failures)~~. → Promoted to **P3-8** (2026-05-17 triage).
- ~~`[discovered 2026-05-17 during P2-3]` catalog `status` enum drift~~. → Promoted to **P3-9** (2026-05-17 triage).
- ~~`[discovered 2026-05-17 during P2-1 design]` **UXM name-cleanup chore**: rename `UxmCommandProfile` → `UxmTestApp` and `UxmTestProfile` → `UxmTopologyProfile`~~. ✅ Resolved 2026-05-17 — see D27 in Done table.
- ~~`[discovered 2026-05-17 during P2-1 design]` **`self._cmds` class-vs-instance mutability fix**~~. ✅ Resolved 2026-05-17 — see D27 in Done table.
- ~~`[discovered 2026-05-17 during P3-8]` **VRT integration tests share dev PG state** (test-isolation)~~. ✅ Resolved 2026-05-17 — see D28 in Done table.
- ~~`[discovered 2026-05-17 during PFS-doc investigation]` **`channel-engine-service` real-mode endpoint calls missing method**~~. → Promoted to **P0-7** (2026-05-18 triage) — D11 ruled `run_with_external_clusters` unimplementable in ChannelEgine; responsibility moved to MIMO-First adapter rewrite + scope broadened to include Phase 5/6 field plumbing + `external_asc` debug mode + fail-fast.
- ~~`[discovered 2026-05-17 during PFS-doc investigation]` **`probe_phase_jitter` UI label says "±10°" but code applies "±180°"**~~. ✅ Resolved 2026-05-18 — ChannelEgine Phase 0 (PR #1) updated UI label + runtime warnings to match ±180° code path; jitter / cal mutex now enforced at runtime + UI level.
- ~~`[discovered 2026-05-19 during P1-7 docs catch-up review]` **Commissioning precheck 不拦未校准 chamber** (Codex P2 on PR #60)~~. → **Promoted to P1-8** ✅ Done (PR #61 merged 2026-05-19; ad-hoc triage, 走 ad-hoc 因为 next 现场之前必须有 fail-loud gate, 不能等 weekly review)。Codex P1 follow-up on PR #61 commit 42af8ca 又抓到 strict gate 用 chamber-only 查询 (没 frequency filter) 漏过老 / 不同频段 cert, 同一 PR commit 743789c 修了, 换成跟 measure phase 同一个 `ProbePathLossCalibrationService.get_latest_calibration(chamber_id, freq_mhz)` ±5% 窗口查询。详见 P1-8 entry。
- ~~`[discovered 2026-05-27 on-site]` **F64 ATE/SCPI 端口硬件固定 3334 (误用 5025 = 两天 blocker 根因) + 输入信号参考/crest 是全新缺失 driver 能力 + 加载需 SYST:ERR? gate**~~. → 用户 2026-05-27 直接 triage 为 **P0-8** (本地可启动, 升 Current Focus; 含默认 3600M .smu 设定)。
- ~~`[discovered 2026-05-27 on-site]` **backend scpi-command 端点 slow-op desync (`timeout_ms` 没透传)**~~. → 用户 2026-05-27 triage 为 **P1-16** (本地)。
- ~~`[discovered 2026-05-27 on-site]` **EMCenter switch 不吃 raw SCPI (EMQuest/GPIB 血统, `.50`)**~~. → 用户 2026-05-27 triage 为 **P2-9** (offline 调研 + 现场)。
- ~~`[discovered 2026-05-27 on-site]` **转台 (Aerotech) 测试了但无结论, 记录供下次开发**~~. → Known-unknown **U-5** + P0-5 note (下次现场验证)。
- `[discovered 2026-05-28 post-P0-8 review]` **InputLevelController: cal-based feed-forward 粗设 + autoset 兜底验证 (hybrid)**. 当前是纯闭环 — UXM 起手 -10dBm → F64 AUTOSET → measure → 不在窗口调 UXM 重试 (最多 5 轮, 每轮 ~3-5s SCPI)。如果有 (a) UXM 输出 cal、(b) UXM-to-F64 cable_loss cal、(c) signal structure PAPR, 就能一次性算 `F64_input_avg = UXM_dBm - cable_loss` + `crest = PAPR` → `INP:LEV:AMP:CH` + `INP:CRE:SET` 粗设 → `measure_input` 一轮校验 (不 autoset) → 在窗口 + clipping OK 直接锁定; 偏差大才退到现有 autoset 闭环兜底。**核心**: 闭环不替, 给"粗设"路径并接 cal 漂移监控副产物 — (粗设值 - 实测值) 写遥测, 持续累计 = cable bend / 接头老化 / cross-band 误差的可观测信号, 知道 cable cal 该重标。GPS+末段制导哲学。依赖下一条的 UXM-to-F64 cable_loss cal 基础设施。
- `[discovered 2026-05-28 post-P0-8 review]` **多端口 MIMO input 不一致 — imbalance metric + 容忍带 + cable balance cal**. 3600M 4x4 各 input 累加 ±1-2.5 dB imbalance 是物理必然 (cable 长度/质量 ±0.5-1dB + UXM TX port ±0.3dB + F64 ADC 增益 ±0.5dB + 接头老化 ±0.2dB + 测量噪声 ±0.1-0.3dB)。当前 `_measure_and_check_window` 任一 input 越界 → strict 整体 fail, 0.3 dB 边缘越界也死, 反而不科学 — 缺 imbalance 概念。三段递进: **(1) 本地 ~半天**: 加 `imbalance_dB = max(avg) - min(avg)` 写 `result_payload["input_level_calibration"]`, soft 窗口 + balance 容忍带 (e.g. <2dB 收敛, 0.3-1dB 越界 marginal warning, >1dB fail); **(2) 现场+本地**: 新 cal cert 类型 `CableBalanceCalibration{cable_loss_by_port_db: Dict[int, float]}`, 现场用 SA/VNA 测一次落库, 上一条 feed-forward 用 per-port cable_loss 取代 chamber-avg; **(3) 长期**: cal 漂移监控持续 N 次差异中位数 > 阈值 → 主动告警操作员。CTIA MPAC OTA 标准做法, 我们当前缺。
- `[discovered 2026-05-28 post-P0-8 review]` **operating point measurement uncertainty 进报告 uncertainty budget**. AUTOSET **不破坏任何 cal cert** (path-loss / F64 user-alignment / UXM 输出 cal 都不被写脏 —— AUTOSET 只调单 input 前端 PGA 挡位, F64 内部映射保证测出的 dBm 仍是正确绝对值, 不动 channel-to-channel 关系也不动 output 端绝对功率), 但 AUTOSET 后 F64 处于一个具体 PGA 挡位, 该挡位的 absolute 精度继承 factory ADC cal 的 ±0.5-1 dB 不确定性 + AUTOSET 单次 measurement noise ±0.3 dB。当前 reference/measure 报告把 RSRP / 吞吐当确定值呈现, 没把这部分不确定性跟 path-loss cal / SA cal 不确定性并联累加进 combined measurement uncertainty budget (报告里 "RSRP ±0" 是骗人, 实际应是 combined U)。应: reference/measure phase 输出携带 operating-point uncertainty 分量, report phase 按 GUM 累加成 combined U (k=2)。模式上 "测试前 setup + 测试中 frozen PGA" 是 RF 标准做法 (等同 SA 测前设 ref level), **不算测试中扰动**; 但记两个边界: (a) **严格 PFS / PWS 未来场景** AUTOSET 改 PGA 可能引入 group-delay→phase shift, 须 cal 后不动 PGA 或 re-cal phase (当前 power-only PFS 不受影响, TR 37.977 F.2); (b) **VRT 跨场景切 cell config** 时 PAPR 漂 → operating point 需 re-setup (VRT 当前未接 InputLevelController, 接入时一起做)。另可加 idempotency gate (setup 过 + 同 cell config 跳过) 防 azimuth loop 内误调 AUTOSET 污染跨 azimuth 可比性。
- `[discovered 2026-05-31 during P2-11 Phase 5]` **UXM 默认 topology profile 字段泄漏进 path B** (Codex on PR #112) — **✅ done 2026-06-04 (#127 后端 + #128 GUI, 方案 b)**. HAL-init 经 `apply_topology_profile → set_cell_config(profile.to_config_dict())` 把 profile 的 `mimo_port_preset` / `tdd_pattern` / `sched_algo` / `csi_rs_ports` 落到 UXM 硬件; measure (path B) 的 `set_cell_config` 只传 frequency/ARFCN/BW/SCS/band/`mimo_layers`/power, **不覆盖上述字段** → 它们残留进正式测试 (如 2x2 TestCase 跑在残留的 4x4 端口路由上)。频率/ARFCN/MIMO layers 已 TestCase 驱动, 但 port routing / TDD / scheduler 既没被 path B 驱动也没被 reset。**待定方向 (需用户定 port-routing 语义)**: (a) measure 从 `mimo_layers` 派生并传 `mimo_port_preset` (2→"2x2"/4→"4x4"/1→"siso") + TDD/sched 补成 TestCase 字段或显式 reset; 或 (b) `MIMOOTAConfiguration` 直接加这些字段。⚠️ 注意 layers≠preset 在某些 diversity 配置下合法, 不能盲目自动派生。属 P2-11 同族 (TestCase 单一真值源驱动) 的下一块。Phase 5 PR 已把三处误称"天然分开"的注释改准 (承认 leak)。**实现 (#127)**: 用户 2026-06-04 选**方案 b** —— `MIMOOTAConfiguration` 加 `mimo_port_preset`/`sched_algo`/`csi_rs_ports` (`tdd_pattern`/`tdd_period` 已有), measure 经 `_build_pcell_cell_config` 显式传给 set_cell_config (set_cell_config 早已支持这些 key, 只是 measure 没传); `csi_rs_ports=None` 不放进 dict (缺省哨兵, 避免 SCPI 写 "None"); 默认对齐内置 profile (backward-compat); **不**从 layers 自动派生 (尊重 diversity layers≠preset)。+9 单测。**GUI 入口 (#128)**: MIMOOTAConfigForm 暴露 mimo_port_preset (Select siso/2x2/4x4/2x2_alt) / sched_algo / csi_rs_ports, 都可空 (留空=用 profile)。注: 上文"默认对齐 profile (backward-compat)"是 cf97251 初版述, Codex P1 #127 后**默认实为 None** (= 未指定, 不覆盖旧 saved 数据)。tsc + 浏览器 smoke 验证渲染+选值。**#1974 GUI 闭环。**
- `[discovered 2026-06-01 during P2-11 Phase 6, 用户提出]` **DUT 自声明能力文件 (declared capability) + 三层能力交叉校验**. Phase 6 从 UXM `query_ue_capability()` 拿 UE **协商**能力 (max_dl_layers) 做下发后校验 —— 但这是 **attach 之后**才有的运行时值, 规划 / precheck 阶段 (未 attach / 未上硬件) 拿不到。**用户提出**: 加一个**用户可填写 / 编辑的 DUT 自声明文件** (DUT capability profile: max DL/UL layers、支持频段、最大调制、UE category、双工等), 测试**从这个自声明开始了解 DUT 能力** —— 早在 attach 前就能拿 TestCase 跟声明能力比 (e.g. TestCase 请求 4 层但 DUT 声明 max 2 → 提前 fail, 不浪费一次真跑)。**最终准确能力仍以 UXM (或其它综测仪) 上报参数为准** (`query_ue_capability`): 自声明 = "expected/spec", UXM 上报 = "actual/negotiated", 两者**交叉校验** (不一致 = DUT 实际行为跟它的 spec 声明不符, 本身是有用发现)。**三层能力**: 声明 (自声明文件, 规划期) → 协商 (UXM `query_ue_capability`, attach 后, Phase 6 用) → 运行时 (CSI RI, 测量中)。设计方向: 新建 `DUTProfile` 实体 (平行于 `LabProfile` 之于 chamber), GUI 让操作员填 / 编辑, precheck 早期拿它校验 TestCase, attach 后跟 UXM 上报交叉核对。把 D 类"DUT config (操作员 attach 时给)"从临时输入升级成**结构化可预声明 + 可校验**。属 P2-11 同族, deferred 待启动。

---

## 📊 Summary

> **Counts 重算 2026-06-04** (roadmap stale catch-up chore): 下方表已从各 ### P section 当前
> status 精确重算, 口径 = roadmap P 项 (P2-7 已 promoted 到 P1-10, 计入非 open)。修正前 5/27 快照
> 漏计 2026-05-29 后新增项 → P1 16→**17** total (补 P1-17), P2 8→**12** total (补 P2-9/10/11/12),
> Total open 11→**14**; Done 口径从混合 D-row 计数改为 P 项完成数 (45→**36**)。天数列因新增项
> estimate 散落各 section 未逐项重算 (见各 section Estimate)。Full-sweep flaky count remains **0**。
>
> **5/27 现场**: first-call PDF **未产出** (又消耗在 F64 driver 层, 用户授权修), 但把两天的 F64
> blocker 根因坐实并真机验证修法 → 收敛为**本地可启动**的 P0-8 (port 3334 + 输入信号参考/crest +
> 加载 gate + 默认 3600M .smu)。另开 P1-16 (scpi-command desync, 本地) + P2-9 (EMCenter switch,
> 调研+现场) + U-5 (转台无结论) + U-6 (F64 输入参考真值)。
>
> 14 open items 现状 (2026-06-04): **本地进行中** = P2-10 (F64 精细化, Step 1/2/3 本地框架 done)
> + P2-11 (TestCase 驱动, Phase 1/2/3/5/6 done, 剩 DL power) + P2-12 (SCD .smu, slice 1-4 done,
> 剩 slice 5 现场); P2-9 (EMCenter switch) offline 调研可先做。**on-site-blocked (9)**: P0-3/4/5
> + P0-8 现场半 + P1-2 + P1-4 + P1-5 现场半 + P1-17 现场半 + P2-4。**P1-6** ⏸️ incident-conditional
> hold (trigger = 真 idle-close, 当前没证据, 仍计 open)。下一轮本地 audit/manual 再挖到 =
> candidate for **P1-18**。权威现状见顶部 Current Focus 段。
>
> (历史) P1-12 兜底标未验证 / P1-13 子网假阳性 / P1-14 mock 探针拒绝 / P1-15 preflight canary 全
> Done; 已知静默兜底扫净 + readiness 假阳性已修 + preflight 抗代理/VPN。详见 Current Focus 段。

| Priority | Count | Total estimate | On-site share |
|----------|-------|---------------|---------------|
| ✅ Done | 36 | — | — |
| 🔴 P0 (first-call critical) | 4 open / 8 total | ~6 days | ~4.5 days |
| 🟠 P1 (confidence) | 5 open / 17 total | 见各 section | 见各 section |
| 🟡 P2 (abstraction debt) | 5 open / 12 total | 见各 section | 见各 section |
| 🟢 P3 (polish) | 0 open / 13 total | 0 | 0 |
| **Total open** | **14** | 见各 section | — |

---

*This roadmap is a living document. Update Current Focus, append to
backlog, mark items done. All changes go through git so we have an audit
trail of what we said vs what we did.*
