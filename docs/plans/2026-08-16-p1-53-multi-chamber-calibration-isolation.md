# P1-53 Multi-Chamber Calibration Isolation Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Ensure probe calibration writes, reads, validity summaries, formal consumers, reports, and GUI caches never mix records between chambers that reuse the same probe numbers.

**Architecture:** Make `chamber_id` an explicit required boundary value for active REST/GUI workflows, then apply strict equality at every probe-calibration SQL source. Preserve legacy NULL rows for audit only; formal consumers and reports never fall back to them. Keep the current computed validity service as the authority instead of reviving the unused materialized validity table.

**Tech Stack:** FastAPI, Pydantic v2, SQLAlchemy, Alembic-aware SQLite/PostgreSQL tests, React 18, TypeScript, TanStack Query, Mantine, pytest, Node test runner.

---

### Task 1: Lock the full chamber-scoping contract RED

**Files:**
- Create: `api-service/tests/test_p1_53_multi_chamber_calibration_isolation.py`
- Modify: `api-service/tests/test_rule_gates.py`

**Step 1: Write failing model/service tests**

Create A/B chamber fixtures with the same `probe_id`, distinct calibration values, plus a newer legacy NULL row. Assert strict A reads return only A and A missing does not fall back to B/NULL for amplitude, phase, polarization, and pattern.

**Step 2: Write failing writer tests**

Exercise amplitude/phase/polarization/pattern start and phase/pattern import. Assert every new row receives the requested chamber and replace-existing invalidates only the same chamber.

**Step 3: Write failing validity/report tests**

Assert validity report, expiring/expired lists, comprehensive probe data, and report collector include only A. Plant a newer B record to prove latest selection cannot cross chambers.

**Step 4: Add a rule-gate inventory**

Enumerate production query/write sites for the four chamber-scoped models and require active latest/history/validity/report sites to consume `chamber_id`. The gate protects the full source inventory, not SQL formatting.

**Step 5: Run RED**

Run:

```bash
/Users/simon/Tools/MIMO-First/api-service/.venv/bin/pytest -q \
  tests/test_p1_53_multi_chamber_calibration_isolation.py \
  tests/test_rule_gates.py --no-header --tb=short
```

Expected: failures show unscoped queries/writers and legacy fallback.

**Step 6: Commit RED**

```bash
git add api-service/tests/test_p1_53_multi_chamber_calibration_isolation.py api-service/tests/test_rule_gates.py
git commit -m "test: expose cross-chamber probe calibration reuse"
```

### Task 2: Scope schemas and all live writers

**Files:**
- Modify: `api-service/app/schemas/probe_calibration.py`
- Modify: `api-service/app/api/probe_calibration.py`
- Modify: `api-service/app/services/probe_phase_calibration_import.py`
- Modify: `api-service/app/services/probe_pattern/import_service.py`
- Modify: `api-service/app/services/probe_calibration_service.py`
- Test: `api-service/tests/test_p1_53_multi_chamber_calibration_isolation.py`

**Step 1: Add required chamber IDs**

Add `chamber_id: UUID` to the four start request models and required multipart form values to phase/pattern import.

**Step 2: Validate chamber/probe ownership before writing**

Use one shared resolver that verifies the chamber exists and each requested probe number belongs to it. Reject missing/mismatched ownership before creating rows.

**Step 3: Persist exact chamber IDs**

Pass the same validated UUID through API constructors and service/import writers. Add chamber equality to replace-existing invalidation queries.

**Step 4: Run focused GREEN**

Run the P1-53 writer tests. Expected: writer cases pass; read/report cases remain RED.

**Step 5: Commit**

```bash
git add api-service/app/schemas/probe_calibration.py api-service/app/api/probe_calibration.py \
  api-service/app/services/probe_phase_calibration_import.py \
  api-service/app/services/probe_pattern/import_service.py \
  api-service/app/services/probe_calibration_service.py \
  api-service/tests/test_p1_53_multi_chamber_calibration_isolation.py
git commit -m "fix: bind probe calibration writes to chambers"
```

### Task 3: Scope latest, history, comprehensive data, and formal consumers

**Files:**
- Modify: `api-service/app/api/probe_calibration.py`
- Modify: `api-service/app/services/probe_calibration_service.py`
- Modify: `api-service/app/services/probe_pattern/consumer.py`
- Modify: `api-service/app/services/probe_phase_calibration_import.py`
- Modify: `api-service/app/services/probe_pattern/import_service.py`
- Test: `api-service/tests/test_p1_53_multi_chamber_calibration_isolation.py`
- Test: `api-service/tests/test_calibration_chamber_scoping.py`

**Step 1: Require chamber query parameters**

Add required `chamber_id` to amplitude/phase/polarization latest+history, pattern list, and comprehensive probe data endpoints.

**Step 2: Apply strict equality**

Every query on the four probe-scoped models must include `model.chamber_id == chamber_id`. Do not include NULL or other chambers.

**Step 3: Remove legacy fallback from formal pattern consumption**

When a chamber is provided, `get_probe_pattern` returns exact chamber or missing. It must not fall back to NULL legacy.

**Step 4: Run focused tests**

Expected: latest/history/data/consumer cases pass; validity/report tests may remain RED.

**Step 5: Commit**

```bash
git add api-service/app/api/probe_calibration.py \
  api-service/app/services/probe_calibration_service.py \
  api-service/app/services/probe_pattern/consumer.py \
  api-service/app/services/probe_phase_calibration_import.py \
  api-service/app/services/probe_pattern/import_service.py \
  api-service/tests/test_p1_53_multi_chamber_calibration_isolation.py \
  api-service/tests/test_calibration_chamber_scoping.py
git commit -m "fix: isolate probe calibration reads by chamber"
```

### Task 4: Scope validity and lifecycle lists

**Files:**
- Modify: `api-service/app/services/probe_calibration_service.py`
- Modify: `api-service/app/api/probe_calibration.py`
- Modify: `api-service/app/schemas/probe_calibration.py`
- Test: `api-service/tests/test_p1_53_multi_chamber_calibration_isolation.py`

**Step 1: Thread chamber through the validity service**

Make `check_validity`, `generate_validity_report`, `get_expiring_calibrations`, and `get_expired_calibrations` require `chamber_id`. Include it in result rows for audit.

**Step 2: Scope every model query**

Apply chamber equality to amplitude/phase/polarization/pattern. Preserve LinkCalibration's existing global semantics and label it as global rather than assigning a fake chamber.

**Step 3: Update API contracts**

Require chamber query parameters on validity endpoints and return `chamber_id` in report/status schemas where appropriate.

**Step 4: Run focused GREEN**

Expected: validity and lifecycle list tests pass.

**Step 5: Commit**

```bash
git add api-service/app/services/probe_calibration_service.py \
  api-service/app/api/probe_calibration.py api-service/app/schemas/probe_calibration.py \
  api-service/tests/test_p1_53_multi_chamber_calibration_isolation.py
git commit -m "fix: scope calibration validity to one chamber"
```

### Task 5: Scope formal probe/comprehensive reports

**Files:**
- Modify: `api-service/app/api/calibration_report.py`
- Modify: `api-service/app/services/calibration_report_generator.py`
- Modify: `api-service/tests/test_calibration_reports.py`
- Test: `api-service/tests/test_p1_53_multi_chamber_calibration_isolation.py`

**Step 1: Require chamber for probe data**

Add `chamber_id` to probe report requests. Comprehensive requests require it whenever `include_probe=true`; channel-only reports remain unchanged.

**Step 2: Filter all probe report sources**

Thread chamber to `_collect_probe_data` and apply strict equality for the four newly scoped probe models plus the existing chamber-aware path-loss, RF-chain, and multi-frequency report sources. Add `chamber_id` to each collected row and the report summary. This does not change those three families' writer contracts; it closes the formal-report read boundary.

**Step 3: Make the PDF identify its chamber**

Render the scoped chamber identifier/name in the probe section. An empty chamber scope produces an explicit no-data/UNKNOWN section, never cross-chamber substitution.

**Step 4: Run report tests**

Expected: A report contains A sentinel values and excludes B/NULL sentinels.

**Step 5: Commit**

```bash
git add api-service/app/api/calibration_report.py \
  api-service/app/services/calibration_report_generator.py \
  api-service/tests/test_calibration_reports.py \
  api-service/tests/test_p1_53_multi_chamber_calibration_isolation.py
git commit -m "fix: isolate formal probe calibration reports"
```

### Task 6: Thread chamber through GUI requests and cache keys

**Files:**
- Modify: `gui/src/types/probeCalibration.ts`
- Modify: `gui/src/api/probeCalibrationService.ts`
- Modify: `gui/src/hooks/useProbeCalibration.ts`
- Modify: `gui/src/features/ProbeCalibration/components/ProbeCalibrationDashboard.tsx`
- Modify: other active ProbeCalibration form/detail components found by the Task 1 inventory
- Create: `gui/test/probeCalibrationChamberScope.test.ts`

**Step 1: Write GUI RED**

Assert request params/body and query keys include chamber ID; assert disabled/no request when current chamber is unavailable.

**Step 2: Add chamber-aware TypeScript contracts**

Thread chamber IDs through start, latest/history, validity, expiring/expired, comprehensive data, and import helpers.

**Step 3: Bind UI to the current chamber truth source**

Consume the existing LabProfile/current-chamber result, display the chamber name, and fail closed on missing/ambiguous source.

**Step 4: Verify RED→GREEN and build**

```bash
cd gui
npx tsx --test test/probeCalibrationChamberScope.test.ts
npm run build
```

Expected: tests pass and production build succeeds.

**Step 5: Commit**

```bash
git add gui/src gui/test/probeCalibrationChamberScope.test.ts
git commit -m "fix: scope probe calibration UI by chamber"
```

### Task 7: Final rule gates, roadmap, and review handoff

**Files:**
- Modify: `docs/roadmap-first-call.md`
- Modify: `docs/plans/2026-08-16-p1-53-multi-chamber-calibration-isolation-design.md`
- Modify: `api-service/tests/test_rule_gates.py`

**Step 1: Run focused and related regression**

```bash
cd api-service
/Users/simon/Tools/MIMO-First/api-service/.venv/bin/pytest -q \
  tests/test_p1_53_multi_chamber_calibration_isolation.py \
  tests/test_calibration_chamber_scoping.py \
  tests/test_probe_calibration_models.py \
  tests/test_calibration_reports.py \
  tests/test_p1_28_chamber_truth_source.py \
  tests/test_rule_gates.py --no-header --tb=short
```

Expected: all pass.

**Step 2: Run compile/build/diff checks**

```bash
python -m compileall -q app tests
cd ../gui && npm run build
cd .. && git diff --check
```

Expected: all exit 0.

**Step 3: Update roadmap facts**

Record exact entry inventory, RED/GREEN evidence, test totals, internal/external review state, and keep WIP=1 on P1-53 until merge.

**Step 4: Internal review**

Review by AGENTS.md 0.5: all writes, latest/history, validity, pattern consumers, reports, GUI cache and legacy NULL paths. Fix functional P1 by TDD until P1=0; P2/P3 follow repository rules.

**Step 5: Open Ready PR and request Codex review**

Run the repository's standard commit/push/PR flow. External review has at most two rounds; after R2, fix any P1 and merge without R3.

### Task 8: Close fresh internal-review gaps

**Files:** probe calibration API/model/schema/service, report collector/PDF, pattern consumer,
GUI grid, Alembic migration, focused tests, design/roadmap mirrors.

1. Scope invalidate by `(calibration_id, chamber_id)` while preserving global LinkCalibration.
2. Replace fixed 32/64 probe assumptions in the four scoped families with `ChamberConfiguration.num_probes`.
3. Persist nullable `use_mock` provenance across the four probe-scoped families plus global Link,
   RF-chain and multi-frequency without backfilling history; formal validity/report/pattern consumers
   whitelist `False`, and GUI details render non-real rows as UNVERIFIED.
4. Compute polarization XPD from persisted directional isolation fields and evaluate expiry dynamically.
5. Render RF-chain and multi-frequency families that contribute to report summary totals.
6. Keep global Link out of per-probe completeness, and exclude mock/unknown Link from report and
   validity-deadline verdicts.
7. Re-run focused regressions, migration paths, GUI build, full rule gates, compileall and diff-check, then request a fresh internal review.
