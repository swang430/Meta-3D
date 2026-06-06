# Roadmap Archive — 已完成项详细记录

> 从 [`roadmap-first-call.md`](roadmap-first-call.md) 迁出的**已完成**条目详情，供审计 / 考古。
> 活跃路线图（open / blocked / 可规划 audit）见 roadmap-first-call.md；本文件**只读、不驱动当前工作**。
> 迁出：2026-06-06 roadmap 收敛 chore。

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

### P3-4 — F64 SYST:INFO? structured parser ✅ Done (D17, 2026-05-17)

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

**Status**: ✅ Done (D17, 2026-05-17 已 merge; section 标题/Status 此前漏标, 本 PR 矫正 stale)
**Estimate**: 0.5 day (actual: ~30 min)

### P3-5 — Startup readiness summary expansion ✅ Done (D18, 2026-05-17)

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

**Status**: ✅ Done (D18, 2026-05-17 已 merge; section 标题/Status 此前漏标, 本 PR 矫正 stale)
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
