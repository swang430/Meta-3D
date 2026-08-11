# P1-27 Calibration Mock Provenance Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Persist path-loss calibration provenance and make real-hardware strict precheck reject mock or unknown-source calibration records.

**Architecture:** Add a nullable `ProbePathLossCalibration.use_mock` Boolean whose three states mean real, simulated, and unknown. Stamp both live generation paths, expose the field through API responses, then include an explicit-real allowlist in precheck and the direct MEASURE entry.

**Tech Stack:** FastAPI, SQLAlchemy, Alembic, Pydantic, pytest, SQLite/PostgreSQL.

---

### Task 1: Lock the strict provenance gate with failing tests

**Files:**
- Modify: `api-service/tests/test_mimo_ota_precheck_cal_gate.py`

**Step 1: Make unrelated calibration fixtures explicitly real**

Add `use_mock=False` to `_seed_path_loss_cal` so the existing cartesian and frequency-window tests keep testing their original contracts rather than historical provenance.

**Step 2: Write the failing provenance cases**

Add cases proving that a real live channel emulator with strict mode:

- accepts a VALID path-loss record only when `use_mock is False`;
- rejects `use_mock is True` with a reason naming simulated calibration provenance;
- rejects `use_mock is None` with a reason naming unknown provenance;
- records both would-fail causes without blocking when strict mode is explicitly disabled.

Also assert the payload exposes `path_loss_calibration_use_mock` unchanged.

**Step 3: Run RED**

Run:

```bash
/Users/simon/Tools/MIMO-First/api-service/.venv/bin/python -m pytest \
  api-service/tests/test_mimo_ota_precheck_cal_gate.py -q
```

Expected: new provenance assertions fail because the model has no persisted field and precheck does not consume it.

**Step 4: Commit the RED tests**

```bash
git add api-service/tests/test_mimo_ota_precheck_cal_gate.py
git commit -m "test: reproduce mock calibration passing strict precheck"
```

### Task 2: Persist and expose the provenance tri-state

**Files:**
- Create: `api-service/alembic/versions/c2d4e6f8a1b3_add_path_loss_use_mock_provenance.py`
- Modify: `api-service/app/models/probe_calibration.py`
- Modify: `api-service/app/services/path_loss_calibration_service.py`
- Modify: `api-service/app/schemas/probe_calibration.py`
- Test: `api-service/tests/test_path_loss_calibration.py`

**Step 1: Write producer tests before production changes**

Extend the existing path-loss service tests to assert a `use_mock=True` run persists `True`. Add a real-path unit case with instrument acquisition replaced by a deterministic real-like measurement and assert it persists `False`. Cover both chamber and lab-profile creation paths where their existing fixtures permit.

**Step 2: Run producer RED**

Run the selected test names and confirm failure is the missing provenance field/value.

**Step 3: Add the nullable model and migration**

Declare `use_mock = Column(Boolean, nullable=True)` with a comment defining `False` / `True` / `NULL`. Add an idempotent Alembic migration from `f6c2d8a41b73`; do not set a server default and do not backfill brownfield rows.

**Step 4: Stamp and expose the value**

Set `use_mock=self.use_mock` in both live `ProbePathLossCalibration` constructors. Add `Optional[bool]` to `ProbePathLossCalibrationResponse`. Do not modify the stale `CalibrationOrchestrator` export/import methods: they still target removed per-probe columns and have no live caller, so that dead-chain repair is a separate Discovered item.

**Step 5: Run producer GREEN and migration checks**

Run the selected producer tests, `alembic heads`, and a temporary SQLite upgrade/downgrade/upgrade cycle or the repository migration tests.

**Step 6: Commit**

```bash
git add api-service/app api-service/alembic/versions api-service/tests/test_path_loss_calibration.py
git commit -m "feat: persist path-loss calibration provenance"
```

### Task 3: Enforce the explicit-real gate at every live execution entrance

**Files:**
- Modify: `api-service/app/services/mimo_ota/executors/precheck.py`
- Modify: `api-service/app/services/mimo_ota/executors/measure.py`
- Test: `api-service/tests/test_mimo_ota_precheck_cal_gate.py`

**Step 1: Implement the minimal allowlist**

Read `latest_pl.use_mock` into `path_loss_calibration_use_mock`. Under real live CE + strict mode, require `path_loss_valid` and `use_mock is False`; produce separate mock and unknown failure reasons. Under mock CE or explicit strict bypass, keep `cal_pass=True` but include the same would-fail provenance reason.

**Step 2: Run GREEN**

Run the full precheck calibration test file and confirm all previous cartesian/frequency cases plus new provenance cases pass.

**Step 3: Close the direct-MEASURE bypass**

Resolve the selected path-loss certificate before any instrument `connect()`. For a real channel emulator, only explicit `use_mock=False` may be applied. Strict mode returns FAILED before hardware touch; explicit bypass continues without applying the untrusted certificate and records its id/provenance for audit. Mock CE rehearsal may continue using mock calibration because its entire measurement is already excluded from formal KPI.

**Step 4: Run adjacent regressions**

Run commissioning precheck, measure compensation, mode filtering, readiness, and rule-gate tests.

**Step 5: Commit**

```bash
git add api-service/app/services/mimo_ota/executors/precheck.py \
  api-service/tests/test_mimo_ota_precheck_cal_gate.py
git commit -m "fix: reject untrusted calibration provenance in strict mode"
```

### Task 4: Close P1-27 and publish

**Files:**
- Modify: `docs/roadmap-first-call.md`

**Step 1: Update all roadmap mirrors**

Mark P1-27 complete, advance Current Focus and LOCAL-OPEN to P2-22, and record the tri-state migration, all production writers, strict allowlist and verification evidence. Any non-P1 review suggestion goes to Discovered rather than inline expansion.

**Step 2: Run fresh verification**

Run:

```bash
/Users/simon/Tools/MIMO-First/api-service/.venv/bin/python -m pytest \
  api-service/tests/test_mimo_ota_precheck_cal_gate.py \
  api-service/tests/test_path_loss_calibration.py \
  api-service/tests/test_path_loss_mode_filter.py \
  api-service/tests/test_commissioning_e2e_p06.py \
  api-service/tests/test_rule_gates.py
git diff --check origin/main
git status --short
```

Expected: all selected tests pass, one Alembic head remains, diff check is clean, and only intended files differ.

**Step 3: Internal review and PR**

Run the repository-specific internal review against `origin/main...HEAD`. Fix P1 without limit; record P2/P3 once. Push `codex/p1-27-calibration-mock-provenance`, open a Ready PR, trigger `@codex review`, and apply the already-approved auto-merge policy when the latest HEAD has no P1/major issue.
