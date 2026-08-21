# P2-38 Selected-Lab Dashboard Readiness Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make Dashboard readiness consume the browser's explicit LabProfile selection while preserving fail-closed unique-active compatibility for callers that omit it.

**Architecture:** Keep the HAL-owned driver/subnet/DUT snapshot unchanged, but rebuild the LabProfile and calibration sections from the database for every readiness request. The GUI passes `OperationalLabContext.selectedLabProfileId`, includes it in the React Query cache key, and keeps the checked-in/live OpenAPI contract synchronized.

**Tech Stack:** FastAPI, SQLAlchemy, Pydantic v2, React 18, TanStack Query, TypeScript, Node test runner, pytest, OpenAPI.

---

### Task 1: Add explicit LabProfile resolution to the readiness builder

**Files:**
- Modify: `api-service/tests/test_hal_readiness.py`
- Modify: `api-service/app/services/readiness.py`

**Step 1: Write the failing service tests**

Add tests that create two active LabProfiles and call:

```python
section = build_lab_profile_readiness(db, lab_b.id)
assert section.status == "ok"
assert section.profile_id == str(lab_b.id)
assert section.profile_name == "Lab-B"
```

Add explicit missing and inactive cases and assert `ValueError`; add a no-argument regression that still returns `ambiguous` for two active rows.

**Step 2: Run the tests to verify RED**

Run:

```bash
cd api-service
.venv/bin/python -m pytest -q tests/test_hal_readiness.py -o log_cli=false
```

Expected: the explicit-ID calls fail because the builder has no such parameter.

**Step 3: Implement the minimal builder change**

Change the signature to:

```python
def build_lab_profile_readiness(
    db: Session, lab_profile_id: Optional[uuid.UUID] = None
) -> LabProfileReadiness:
```

When `lab_profile_id` is present, call the shared `resolve_lab_profile()` and construct an `ok` section from that exact active row. Leave the existing no-argument missing/inactive/ambiguous/ok branches unchanged.

**Step 4: Run GREEN**

Run the same pytest command. Expected: all `test_hal_readiness.py` tests pass.

**Step 5: Commit**

```bash
git add api-service/app/services/readiness.py api-service/tests/test_hal_readiness.py
git commit -m "fix: resolve readiness for an explicit LabProfile"
```

### Task 2: Recompose request-time LabProfile and calibration truth

**Files:**
- Modify: `api-service/tests/test_hal_readiness.py`
- Modify: `api-service/app/api/instrument.py`

**Step 1: Write failing endpoint tests**

Cover these observable paths:

1. two active LabProfiles with different certificates and a stale HAL snapshot pointing to A; `GET .../readiness?lab_profile_id=<B>` returns B plus B's certificate;
2. explicit missing/inactive IDs return 422 and never fall back;
3. with `get_hal_service() is None`, an explicit LabProfile still returns its live Lab/calibration sections while `available=false` and drivers/subnets remain empty;
4. no parameter with multiple active rows retains `ambiguous`.

**Step 2: Verify RED**

Run the focused pytest command. Expected: explicit requests are ignored and the stale snapshot is returned.

**Step 3: Implement request-time composition**

Give `get_hal_readiness()` these dependencies:

```python
def get_hal_readiness(
    lab_profile_id: Optional[UUID] = Query(None),
    db: Session = Depends(get_db),
):
```

Build the lab section from `build_lab_profile_readiness(db, lab_profile_id)` and calibration from `build_calibration_readiness(db, lab_section)`. Convert explicit resolver `ValueError` to HTTP 422. Reuse only `report.drivers`, `report.subnets`, `report.dut_attach`, and the HAL snapshot timestamp when a report exists. When no report exists, keep `available=false` and shaped driver/DUT placeholders, but return the live DB-backed lab/calibration sections.

**Step 4: Verify GREEN and compatibility**

Run:

```bash
cd api-service
.venv/bin/python -m pytest -q tests/test_hal_readiness.py tests/test_hal_subnet_reachability.py -o log_cli=false
```

Expected: all pass; driver/subnet snapshot behavior remains unchanged.

**Step 5: Commit**

```bash
git add api-service/app/api/instrument.py api-service/tests/test_hal_readiness.py
git commit -m "fix: compose readiness from the selected lab"
```

### Task 3: Wire the global GUI context and cache identity

**Files:**
- Create: `gui/test/dashboardReadinessLabProfile.test.ts`
- Modify: `gui/src/api/service.ts`
- Modify: `gui/src/features/Dashboard/ZoneReadiness.tsx`

**Step 1: Write the failing GUI contract test**

The source-level behavior test must prove:

- `fetchReadiness(labProfileId?)` sends `{ params: { lab_profile_id: labProfileId } }` only when set;
- `ZoneReadiness` calls `useOperationalLab()`;
- the query key includes `selectedLabProfileId`;
- the query function passes the same ID;
- the Dashboard does not call `fetchLabProfiles` or maintain a page-local selection.

**Step 2: Verify RED**

Run:

```bash
node --experimental-strip-types --test gui/test/dashboardReadinessLabProfile.test.ts
```

Expected: assertions fail on the current no-argument service and fixed query key.

**Step 3: Implement the minimal GUI wiring**

Use:

```typescript
export const fetchReadiness = async (
  labProfileId?: string,
): Promise<HALReadinessResponse> => {
  const response = await client.get('/instruments/hal/readiness', {
    params: labProfileId ? { lab_profile_id: labProfileId } : undefined,
  })
  return response.data
}
```

In `ZoneReadiness`, consume `selectedLabProfileId` and `loading` from `useOperationalLab()`, use `['cockpit', 'readiness', selectedLabProfileId ?? 'implicit']`, pass the ID to `fetchReadiness`, and disable the query only while the operational-lab list is loading.

**Step 4: Verify GREEN plus P1-57 inventory**

Run:

```bash
node --experimental-strip-types --test \
  gui/test/dashboardReadinessLabProfile.test.ts \
  gui/test/operationalLabContextWiring.test.ts \
  gui/test/operationalLabConsumerInventory.test.ts
```

Expected: all pass and no new LabProfile list consumer appears.

**Step 5: Commit**

```bash
git add gui/src/api/service.ts gui/src/features/Dashboard/ZoneReadiness.tsx gui/test/dashboardReadinessLabProfile.test.ts
git commit -m "fix: scope dashboard readiness to the selected lab"
```

### Task 4: Synchronize live, checked-in, and generated OpenAPI

**Files:**
- Modify: `api-service/tests/test_p2_27_openapi_contract_alignment.py`
- Modify: `api/openapi.yaml`
- Modify: `gui/src/types/api.generated.ts`

**Step 1: Write the failing contract assertions**

Assert that both `app.openapi()` and checked-in `api/openapi.yaml` expose one optional UUID query parameter named `lab_profile_id` on `/api/v1/instruments/hal/readiness`.

**Step 2: Verify RED**

Run:

```bash
cd api-service
.venv/bin/python -m pytest -q tests/test_p2_27_openapi_contract_alignment.py -o log_cli=false
```

Expected: live may pass after Task 2, but checked-in YAML fails until synchronized.

**Step 3: Update YAML and regenerate TypeScript**

Describe the parameter as the explicit current LabProfile; document that omission requires a unique active LabProfile and may yield ambiguous readiness. Then run:

```bash
npm run openapi:generate --prefix gui
```

**Step 4: Verify GREEN and directionality**

Run the contract pytest and:

```bash
node --experimental-strip-types --test gui/test/apiContractAlignment.test.ts
```

Expected: both pass; generated endpoint parameters include optional `lab_profile_id`.

**Step 5: Commit**

```bash
git add api/openapi.yaml gui/src/types/api.generated.ts api-service/tests/test_p2_27_openapi_contract_alignment.py
git commit -m "docs: align selected-lab readiness contract"
```

### Task 5: Full verification, fresh review, and roadmap handoff

**Files:**
- Modify: `docs/plans/2026-08-22-p2-38-dashboard-readiness-lab-profile-design.md`
- Modify: `docs/roadmap-first-call.md`

**Step 1: Run focused and rule-gate regression**

Run the readiness, LabProfile resolver, OpenAPI and full rule-gate files. Record exact commands and counts in the design.

**Step 2: Run GUI verification**

Run all touched Node contract tests and:

```bash
npm run build --prefix gui
```

**Step 3: Run backend full suite and static gates**

Run:

```bash
cd api-service
.venv/bin/python -m pytest -q -o log_cli=false
.venv/bin/python -m compileall -q app
cd ..
git diff --check origin/main...HEAD
```

**Step 4: Perform fresh internal review**

Apply `AGENTS.md` rules: enumerate every readiness producer/consumer, verify explicit failures never fall back, confirm query/cache identity changes together, and check OpenAPI mirrors. Fix any P1 with TDD and repeat review until P1=0.

**Step 5: Record and commit verification**

Update roadmap status to Ready and append exact RED/GREEN/revision evidence to the design.

```bash
git add docs/plans/2026-08-22-p2-38-dashboard-readiness-lab-profile-design.md docs/roadmap-first-call.md
git commit -m "docs: record P2-38 verification"
```

### Task 6: Ready PR and Codex review closure

**Files:** none expected beyond review-driven fixes.

**Step 1: Push and open a Ready PR**

Use the roadmap item `P2-38`, observable failure, exact test evidence, and no-cleanup statement in the PR body.

**Step 2: External review rule**

Handle executable in-scope R1 findings with TDD, fresh review, regression, thread replies, and R2. If R2 has no P1 and mergeability/checks permit, merge immediately. If R2 or later has P1, fix it and continue P1-only reviews until a Codex review covers the latest HEAD with no P1. R2+ P2/P3 are reported but do not block or auto-enter backlog.

**Step 3: Continue queue**

After verifying `origin/main`, delete the P2-38 automation and start P2-36 from latest main unless the user asks to pause. P2-40 cleanup remains frozen.
