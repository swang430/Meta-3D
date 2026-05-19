# MIMO-First — First-Call Roadmap

> **Single source of truth for what we're working on next.** All non-trivial
> development MUST reference an item on this roadmap. Off-roadmap work needs
> explicit justification (see [governance rules](#governance-rules) below).

---

## 🎯 Current Focus

**P1-8 — Commissioning precheck cal-missing fail-loud gate (next).**

P1-7 (#59) merged。本 PR (#60, docs catch-up) review 过程中 Codex P2 抓到一个
真错误: architecture note 初版宣称 "precheck gate + lazy DB lookup + silent
fallback 三层保护", 但 [`precheck.py:236`](../api-service/app/services/mimo_ota/executors/precheck.py#L236)
`overall_pass = critical_online and qz_pass and ue_cap_pass` **不读校准状态** —
没建过任何 cal cert / 没跑过路损校准的 chamber 也能从 precheck 通过, measure phase
silently 用 `typical_cable_loss_db + duplexer - pa_gain` fallback 跑出 .asc,
没人会报错 (详见
[`docs/architecture/channel-engine-data-flow.md`](architecture/channel-engine-data-flow.md)
surprising #3)。当前规避只有 GUI workflow 主观顺序 "先 cal 后 commission"。

P1-8 把这条 backlog 条目升级为正式 P1 项目, 修 `precheck.py` 加 fail-loud gate:
路损校准 / cert 缺失或 cert `overall_pass=False` → precheck FAIL with 具体
错误。不阻断真校准的 chamber, 但拒绝未校准的。Next 现场之前修掉是 first-call
repeatability (P1-4) 的硬 prerequisite。

> **关于 P1-6**: 之前 (本 PR 初版) Current Focus 错选 P1-6, 没验证它的 trigger
> condition。看 P1-6 entry: `"pulled forward only if a real production
> idle-close is seen on those drivers"` —— 这是 incident-conditional, 跟
> [2026-05-13 现场 summary](site-debug/2026-05-13-summary.md) 一致 (当时只在
> Aerotech 上看到 idle-close, F64/UXM/ENA 都没看到)。trigger 没满足前不该启动。
> 这次 ad-hoc triage 把 P1-8 提到 next focus, P1-6 继续 hold 等真 incident。

P0 全部 on-site-blocked (P0-3/4/5 都需要现场 SA + DUT + CE/SA 联调), P1 里
P1-2/P1-4/P1-5 on-site half 全 hardware-blocked, P1-6 incident-conditional
hold。**P1-8 是当前唯一 fully-remote-doable 的 P1 项目** + 是 next 现场的
prerequisite。

下次现场打开时, Current Focus 必须切回 **P0-3** (或最先解锁的 P0) per WIP=1。
P1-5 on-site half + P2-4 + P2-7 在 P0 解锁前排队。

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

**What**: Bind a Keysight N9020B MXA (or equivalent) to the HAL
`signalAnalyzer` category and connect it to a known-gain reference horn
antenna in the chamber. Reference phase reads real channel power, applies
the offset, and emits a real TRP — not the current mock 23.5 dBm fallback.

**Why**: The `_MOCK_TRP_DBM` fallback means the compensation factor is
fake. Real first-call needs the real path:
`measured_TRP = SA_power + offset → compensation_factor = horn_gain - (measured - nominal)`.

**Acceptance**:
- `signalAnalyzer` driver is loaded (readiness table shows ✓)
- Reference phase logs `measurement_source: "hal_signal_analyzer"` (not
  `"mock"`)
- Measured TRP within ±1 dB of horn datasheet TRP at the tested
  frequency

**Status**: `[ ]` not started — `RealKeysightXSeriesSaDriver` exists,
needs config + on-site connection
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
不阻塞 P1-8 (next focus, per 本 PR review-driven re-triage)。

---

### P1-8 — Commissioning precheck cal-missing fail-loud gate

**What**: [`PrecheckExecutor`](../api-service/app/services/mimo_ota/executors/precheck.py)
当前 `overall_pass` 只读 `critical_online and qz_pass and ue_cap_pass`
(precheck.py:236), 校准状态完全没进:

```python
# 当前 (broken):
overall_pass = critical_online and qz_pass and ue_cap_pass
# path_loss_calibration_valid / cal_cert.overall_pass 写进 result_payload
# 但不参与 overall_pass 计算
```

修法: 把校准状态升进 `overall_pass`, 默认 strict (未校准就拒):

```python
# 目标 (strict default):
cal_pass = (
    path_loss_calibration_valid
    and (cal_cert is None or cal_cert.overall_pass)
    # cal_cert is None 还是 allow? 见 acceptance 讨论
)
overall_pass = critical_online and qz_pass and ue_cap_pass and cal_pass
```

**Why P1 (not P2)**: 直接威胁 P1-4 first-call repeatability。production 运行
时 random 踩 (operator 忘了先 cal 就直接跑 commissioning) → 测出来的 KPI 基于
`ChamberConfiguration.typical_cable_loss_db` 折算 fallback, 不是真测过的路损 →
不可能 first-call repeatable (不同 chamber 误差不同, 不同时段未跑 cal 测出来
的"基线"漂)。Next 现场之前修掉是硬 prerequisite。

**Why discovered now**: Codex P2 on PR #60 commit 81f6923 — 写 architecture note
"跟 cal cert 工作链的衔接" 节时假设 precheck 是 fail-loud gate, Codex 抓了我的
错记并指向 precheck.py:236 的真实计算。

**Design 决策** (本 PR review 中已定, 2026-05-19):

1. **cal_cert 缺失 → warning, 不 FAIL**。`cal_cert` 是 LabProfile / TestCase
   binding, 实验室初始化阶段可能 None — 不能因为没绑 cert 就拦 commissioning。
   但 cal_cert 存在但 `overall_pass=False` → **FAIL** (是 cert 自己显式标 broken,
   不该 silently 接受)。

2. **path_loss_calibration 缺失 → FAIL**。这是 measure phase 真用的数据,
   没这个就走 `typical_cable_loss_db + duplexer - pa_gain` fallback (silent
   失真, 见 [`channel-engine-data-flow.md`](architecture/channel-engine-data-flow.md)
   surprising #1)。严格拒, 这是 P1-8 的核心目的。

3. **加 strict-mode flag, default True (用户决定 2026-05-19)**:

   ```python
   # api-service/app/schemas/mimo_ota/config.py
   class MIMOOTAConfiguration:
       precheck_strict_cal: bool = True  # production-safe default
       # ...
   ```

   - **Default True**: production / 现场 / GUI commissioning 走严格路径, cal
     缺失就 FAIL。这是 P1-8 "防 silent fallback" 的 raison d'être。
   - **显式 opt-out**: lab dev 写 yaml / 测试 fixture 灌 config / TestCase
     configuration override 都可以 `False`, 跳过 cal gate 维持旧行为
     ("先跑通流程, cal 后补"工作流)。
   - **GUI 不暴露 bypass**: 避免 operator 误点。要 bypass 走 config 文件 /
     测试 fixture, 显式 opt-in 让人知道在做什么。
   - **Bypass 时 precheck 不静默**: `result_payload["cal_pass_reason"]` 写
     `"bypassed via precheck_strict_cal=False"`, audit trail 保留。

**Scope** (single PR):

| Step | File | What |
|---|---|---|
| 1 | `api-service/app/schemas/mimo_ota/config.py` | 加 `precheck_strict_cal: bool = True` 字段, default True (production-safe) |
| 2 | `api-service/app/services/mimo_ota/executors/precheck.py` | `overall_pass` 计算加 `cal_pass`; `cal_pass = path_loss_calibration_valid AND (cal_cert is None OR cal_cert.overall_pass)`; 若 `config.precheck_strict_cal == False` → cal_pass 强制 True (跳过 gate) |
| 3 | `api-service/app/services/mimo_ota/executors/precheck.py` | failure_reason 列表加 cal 缺失原因 (跟 critical_online / qz / ue_cap 分类一致); bypass 时 `result_payload["cal_pass_reason"] = "bypassed via precheck_strict_cal=False"` audit trail |
| 4 | `api-service/tests/test_mimo_ota_precheck.py` | 加 cartesian: (cal_cert: None / valid / overall_pass=False) × (path_loss_cal: None / VALID) × (precheck_strict_cal: True / False) = 12 cases |
| 5 | 现有 precheck 测试 audit | 没灌 cal 的现有测试要么补 cal fixture (推荐, 跟 production 路径一致), 要么显式 `precheck_strict_cal=False`。每个测试明确意图: "测 strict 路径" 或 "测 bypass 路径" |

**Acceptance**:

- (strict, default) 未校准 chamber (no `ProbePathLossCalibration` VALID) 跑
  precheck → FAIL with `error_message` 含 "path-loss calibration missing or invalid"
- (strict, default) `cal_cert.overall_pass = False` 跑 precheck → FAIL with
  `error_message` 含 "calibration_certificate not passed"
- (strict, default) 完整 cal 的 chamber 跑 precheck → 维持 PASS (不回归)
- (strict, default) `cal_cert is None` 跑 precheck → 跟旧行为一致 (warning,
  不 fail), 因为 cal_cert binding 是 LabProfile 阶段事情, 不该拦 commissioning
- **(bypass) `precheck_strict_cal=False` 时**: 未校准 chamber 跑 precheck
  → PASS (跟旧行为一致), 但 `result_payload["cal_pass_reason"]` 含 `"bypassed
  via precheck_strict_cal=False"` audit trail
- `result_payload["cal_pass"]` (bool) 在 strict PASS / strict FAIL / bypass
  三种情况都正确反映
- 12 个 cartesian test 全过
- 现有 precheck 测试不回归 (补 fixture 或显式 bypass 都可以)

**Out of scope**:

- ChannelEngineClient 端的 fallback 行为不动 (precheck 已经拦, fallback 就是
  纯防御 dead code, 不删因为别的调用路径还可能用到)
- GUI 端 cal-missing UX 改进 (现在 commissioning 一上来就 fail, GUI 自然弹
  error; 后续 P3-level polish 可以做 inline 提示 "请先跑 cal")

**Status**: `[ ]` ad-hoc triage 2026-05-19 — promoted from `[discovered
2026-05-19 during P1-7 docs catch-up review]` per user decision in PR #60
review (走 ad-hoc 而不是 weekly triage 因为 next 现场之前必须有 fail-loud gate)
**Estimate**: 0.5-1 day local

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

### P2-7 — 非 ring 暗室 probe 几何支持 (cross-repo)

**What**: 当前 commissioning → ChannelEgine 链路写死 `chamber_config.distribution
= "ring"`, probe 物理 azimuth/elevation 角度**不进** HTTP payload。ChannelEgine
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

---

## 🗂️ Discovered during X — triage backlog

> Items added mid-task. Reviewed weekly; promoted to P1/P2/P3 or dropped.

> **Triage history**: 2026-05-17 — promoted 4 active entries to P3
> slots (P3-6: chamber preset Type-C test reconciliation; P3-7: VSCode
> interpreter settings + `.vscode/` policy; P3-8: VRT pydantic
> regression; P3-9: catalog status enum drift). Resolved entries kept
> below for audit trail.

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
- ~~`[discovered 2026-05-19 during P1-7 docs catch-up review]` **Commissioning precheck 不拦未校准 chamber** (Codex P2 on PR #60)~~. → **Promoted to P1-8** (2026-05-19 ad-hoc triage, in response to Codex P2 on PR #60; 走 ad-hoc 因为 next 现场之前必须有 fail-loud gate, 不能等 weekly review)。

---

## 📊 Summary

> Counts as of 2026-05-19 (post P0-7 #56 + P1-5 local-half #57 + chore #58 + P1-7 #59 merged + 本 docs-catchup PR + P1-8 ad-hoc promotion from Codex P2 review)。
> Full-sweep flaky count remains **0**。10 个 open items 里, 7 个
> 🚧 blocked-on-hardware (3 × P0 + P1-5 on-site half + P1-2 + P1-4 + P2-4);
> 1 个 fully-remote-doable (**P1-8 precheck cal-missing fail-loud gate**, next
> Current Focus); 1 个 incident-conditional hold (P1-6 FS16/UXM/ENA silent-reconnect,
> trigger 没满足); 1 个 architecture gap 没即时 trigger (P2-7, 非 ring distribution,
> 等 PWS / 非标暗室触发)。

| Priority | Count | Total estimate | On-site share |
|----------|-------|---------------|---------------|
| ✅ Done | 36 | — | — |
| 🔴 P0 (first-call critical) | 3 open / 7 total | 4 days | 4 days |
| 🟠 P1 (confidence) | 5 open / 8 total | 3.5 days | 1.5 days |
| 🟡 P2 (abstraction debt) | 2 open / 7 total | 2.5 days | 0.5 day |
| 🟢 P3 (polish) | 0 open / 13 total | 0 | 0 |
| **Total open** | **10** | **~10 days** | **6 days** |

---

*This roadmap is a living document. Update Current Focus, append to
backlog, mark items done. All changes go through git so we have an audit
trail of what we said vs what we did.*
