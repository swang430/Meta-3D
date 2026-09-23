# P2-32A 多频路损真实入口闭环实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 删除随机 TRP/TIS 多频生产入口，并让 GUI、数据库与报告共同消费已有 CE+SA 多频路损真实链。

**Architecture:** 服务器权威入口保持 `StartMultiFrequencyPathLossRequest -> MultiFrequencyPathLossService`，GUI 只负责显式提交模式与当前 LabProfile 暗室。每个 probe 独立保存 warnings；响应和报告只投影持久真值，不从 warning 文本或客户端选择重算 provenance。

**Tech Stack:** FastAPI、Pydantic v2、SQLAlchemy、Alembic、React 18、TypeScript、Mantine、Node test runner、pytest。

**Spec:** `docs/plans/2026-09-23-p2-32a-multi-frequency-real-activation-design.md`

## Global Constraints

- 不新增或修改任何 SCPI 命令。
- 模拟结果不得进入正式 PASS/FAIL、KPI 或报告分母。
- 旧随机端点必须删除，不允许失败后 fallback 到 Mock。
- `warnings=NULL` 表示历史未记录；新写入必须是明确列表。
- 静区继续 Hardware Blocked；探头方向图留给独立 P2-32B。
- 所有生产代码改动先有失败测试并确认 RED。

---

### Task 1: warnings 数据库真值与迁移

**Files:**
- Modify: `api-service/app/models/probe_calibration.py`
- Create: `api-service/alembic/versions/<revision>_add_multi_frequency_warnings.py`
- Test: `api-service/tests/test_p2_32a_multi_frequency_activation.py`

**Interfaces:**
- Produces: `MultiFrequencyPathLoss.warnings: list[str] | None`
- Migration semantics: brownfield `NULL`; new rows accept JSON arrays on PostgreSQL and SQLite.

- [ ] **Step 1: Write the failing model/migration tests**

Create tests that instantiate a row with `warnings=["cleanup failed"]`, round-trip it through SQLite,
and assert the migration source adds only `multi_frequency_path_losses.warnings` with nullable JSON.
The production mutation “omit the model column or migration” must fail these tests.

- [ ] **Step 2: Run RED**

Run: `cd api-service && .venv/bin/python -m pytest tests/test_p2_32a_multi_frequency_activation.py -q`

Expected: FAIL because `warnings` is not a model field/migration.

- [ ] **Step 3: Implement the nullable column and guarded migration**

Use the repository’s dialect-agnostic `table_exists/column_exists` migration pattern. Do not backfill
historical rows; downgrade removes only this column when present.

- [ ] **Step 4: Run GREEN and migration checks**

Run the targeted test plus `alembic heads`; expect one head.

- [ ] **Step 5: Commit**

Commit message: `feat: persist multi-frequency calibration warnings`

### Task 2: per-probe warning persistence and authoritative response

**Files:**
- Modify: `api-service/app/services/path_loss_calibration_service.py`
- Modify: `api-service/app/api/path_loss_calibration.py`
- Modify: `api-service/app/schemas/probe_calibration.py`
- Test: `api-service/tests/test_p2_32a_multi_frequency_activation.py`

**Interfaces:**
- Consumes: `MultiFrequencyPathLoss.warnings`
- Produces: `CalibrationJobResponse.use_mock: bool | None`
- Produces: per-probe row warnings and job-level ordered warning aggregation.

- [ ] **Step 1: Write RED tests for warning ownership and response provenance**

Test two probes with distinct injected warnings. Assert each row contains only its own list, the response
aggregates both, and `use_mock=false` is returned when the service was constructed real. Mutating the
service to share one global list, omit persistence, or omit response provenance must fail.

- [ ] **Step 2: Run RED**

Run the new tests; confirm failures name missing persistence/provenance.

- [ ] **Step 3: Implement minimal service/API changes**

Create one `probe_warnings` list per probe, pass it to the existing real sweep, persist a copy, extend the
job list after the probe finishes, and return `use_mock=request.use_mock`. Do not change command builders,
lease boundaries, or SCPI.

- [ ] **Step 4: Run GREEN and affected backend tests**

Run the new file plus `test_path_loss_calibration.py`, `test_path_loss_ce_sa.py`,
`test_p1_68_calibration_real_reachability.py`, and `test_p2_30_task_level_lease.py`.

- [ ] **Step 5: Commit**

Commit message: `feat: expose multi-frequency calibration provenance`

### Task 3: remove the legacy random endpoint

**Files:**
- Modify: `api-service/app/api/calibration.py`
- Modify: `api-service/app/schemas/calibration.py`
- Modify: `gui/src/api/calibrationService.ts`
- Test: `api-service/tests/test_p2_32a_multi_frequency_activation.py`
- Test: `gui/test/multiFrequencyCalibrationTruth.test.ts`

**Interfaces:**
- Removes: `POST /api/v1/calibration/multi-frequency`
- Removes: legacy `MultiFrequencyCalibrationRequest/Response` and GUI fallback generator.

- [ ] **Step 1: Write RED tests that enumerate all legacy entry points**

Backend test asserts the live OpenAPI has no legacy path and retains the path-loss start path. GUI test
executes the real request builder/client boundary and asserts no exported function or source route can call
the legacy endpoint or `generateMockMultiFrequencyResult`.

- [ ] **Step 2: Run RED**

Expected: legacy backend route and GUI function make both tests fail.

- [ ] **Step 3: Delete the route, dedicated schemas, frontend function and fallback**

Remove unused imports at the same time. Do not replace the route with another synthetic implementation.

- [ ] **Step 4: Run GREEN**

Run both targeted test files and the existing OpenAPI/rule gates that enumerate live routes.

- [ ] **Step 5: Commit**

Commit message: `fix: retire synthetic multi-frequency endpoint`

### Task 4: GUI explicit real/mock request and result semantics

**Files:**
- Create: `gui/src/components/SystemCalibration/multiFrequencyCalibration.ts`
- Modify: `gui/src/components/SystemCalibration/CalibrationWizard.tsx`
- Modify: `gui/src/api/calibrationService.ts` or create a focused API client beside the helper
- Test: `gui/test/multiFrequencyCalibrationTruth.test.ts`

**Interfaces:**
- Produces: `buildMultiFrequencyPathLossRequest(input): StartMultiFrequencyPathLossRequest`
- Produces: `startMultiFrequencyPathLossCalibration(request): Promise<CalibrationJobResponse>`

- [ ] **Step 1: Write RED behavior tests**

Use literal expected payloads. Assert normalization of `"1, 2"` to `[1,2]`; reject blank/duplicate/noninteger
IDs, missing chamber, missing mode and invalid sweep range; assert explicit `use_mock=false/true` survives.
Add a UI wiring assertion that the wizard calls only the new helper and renders real completion separately
from simulated diagnostic completion. The mutation “show generic PASS for either response” must fail.

- [ ] **Step 2: Run RED**

Run: `cd gui && node --import tsx --test test/multiFrequencyCalibrationTruth.test.ts`

- [ ] **Step 3: Implement the pure builder, focused client and wizard controls**

The mode starts unset. Use current OperationalLab chamber. Display response warnings. Real completion may
be green “真实扫频完成” but must not claim threshold PASS; Mock completion is yellow and explicitly excluded
from formal judgement.

- [ ] **Step 4: Run GREEN and production build**

Run the test and `npm run build`.

- [ ] **Step 5: Commit**

Commit message: `feat: activate multi-frequency calibration in gui`

### Task 5: reports and four contract mirrors

**Files:**
- Modify: `api-service/app/services/calibration_report_generator.py`
- Modify: `api/openapi.yaml`
- Regenerate: `gui/src/types/api.generated.ts`
- Modify: relevant hand-written GUI types/client
- Test: `api-service/tests/test_p2_32a_multi_frequency_activation.py`
- Test: `gui/test/apiContractAlignment.test.ts`

**Interfaces:**
- Consumes: persisted `MultiFrequencyPathLoss.warnings`
- Produces: warnings in both chamber and probe calibration report projections.

- [ ] **Step 1: Write RED report tests**

Insert one historical `warnings=None`, one real row with warnings, and one mock row. Assert both report
collection paths preserve `None` versus list, while only explicit-real current data receives formal verdict.

- [ ] **Step 2: Run RED**

Expected: warnings absent from report projections.

- [ ] **Step 3: Add report fields and regenerate contracts**

Generate live OpenAPI, update checked YAML, regenerate TypeScript, and keep hand-written request/response
types aligned. Do not hand-edit generated TypeScript.

- [ ] **Step 4: Run GREEN and mirror checks**

Run targeted report/OpenAPI tests, GUI contract test and production build.

- [ ] **Step 5: Commit**

Commit message: `docs: publish multi-frequency calibration evidence`

### Task 6: roadmap, full verification and delivery

**Files:**
- Modify: `docs/roadmap-first-call.md`

**Interfaces:**
- Records P2-32A as delivered and leaves P2-32B next; P2-32C remains Hardware Blocked.

- [ ] **Step 1: Update roadmap facts after implementation**

State exact delivered boundaries: real CE+SA reachability, explicit mode, warning persistence/reporting,
retired random endpoint, no new SCPI. Do not mark P2-32B/C done.

- [ ] **Step 2: Run full verification**

Run focused/affected backend chain, full backend suite, GUI contract tests, production build, compileall,
single Alembic head, and base-to-HEAD diff-check.

- [ ] **Step 3: Fresh review**

Review all generation/read/report/history paths for simulated data and all success/failure/cancel paths for
warning/provenance reset. Resolve functional P1 and in-slice P2 only, per AGENTS.md.

- [ ] **Step 4: Ready PR and Codex R1 -> R2**

Open a Ready PR. Address R1 functional P1 and in-slice P2. Trigger R2 against latest HEAD. Merge only when
latest-head review has no P1 and required checks pass (or none are required).

- [ ] **Step 5: Merge, sync and clean**

Fetch origin/main, fast-forward the main checkout without touching untracked instrument files, remove the
worktree/local branch, then begin the separately planned P2-32B slice.
