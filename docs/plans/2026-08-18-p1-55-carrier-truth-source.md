# P1-55 Carrier Truth Source Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make `component_carriers[0]` the only MIMO OTA operating-point truth while rejecting explicit legacy-mirror conflicts before persistence or hardware I/O.

**Architecture:** `MIMOOTAConfiguration` owns the raw-input conflict gate and exposes a `primary_carrier` accessor. `TestCaseService` canonicalizes every MIMO_OTA create/update payload through the same schema before commit, while executors and GUI consume the PCell rather than legacy top-level mirrors. Missing mirrors remain backward compatible; explicit conflicts fail loud.

**Tech Stack:** Python 3.13, Pydantic v2, FastAPI, SQLAlchemy, pytest, React 18, TypeScript, Mantine, Node test runner.

---

### Task 1: Lock the carrier truth contract with RED tests

**Files:**
- Create: `api-service/tests/test_p1_55_carrier_truth_source.py`
- Create: `gui/test/carrierTruthSource.test.ts`

**Step 1: Write schema conflict and compatibility tests**

Add focused tests for:

```python
def test_explicit_top_level_frequency_conflict_is_rejected():
    with pytest.raises(ValidationError, match="frequency_hz.*component_carriers\\[0\\]"):
        MIMOOTAConfiguration.model_validate({
            "frequency_hz": 3.6e9,
            "component_carriers": [{
                "frequency_hz": 3.5e9,
                "bandwidth_mhz": 100,
                "subcarrier_spacing_khz": 30,
            }],
        })


def test_missing_legacy_mirrors_are_filled_from_pcell():
    config = MIMOOTAConfiguration.model_validate({
        "component_carriers": [{
            "frequency_hz": 3.54999e9,
            "bandwidth_mhz": 40,
            "subcarrier_spacing_khz": 30,
        }],
    })
    assert config.frequency_hz == config.primary_carrier.frequency_hz == 3.54999e9
    assert config.bandwidth_mhz == config.primary_carrier.bandwidth_mhz == 40
```

Repeat the conflict case for bandwidth and SCS; assert no-CC legacy input constructs one PCell and that SCells remain unchanged.

**Step 2: Write service/API persistence tests**

Use a real SQLite session to prove create and update reject conflicts before commit and that missing mirrors are stored canonically. Include a non-MIMO control row whose free-form configuration is unchanged.

**Step 3: Write execution-source tests**

Pin the wished-for API (`config.primary_carrier`) and behavior for factory convenience columns, PRECHECK lookup frequency, REFERENCE SA setup, and MEASURE path-loss/pattern/ASC inputs. Each assertion must fail if its production consumer is changed back to `config.frequency_hz` or `config.bandwidth_mhz`.

**Step 4: Write GUI helper tests**

Specify a pure helper contract:

```ts
assert.equal(primaryCarrierValue(conflict, 'frequency_hz'), 3_500_000_000)
assert.deepEqual(updatePrimaryCarrierValue(caConfig, 'bandwidth_mhz', 40), {
  ...expectedWithTopLevelAndPCellUpdated,
  component_carriers: [updatedPCell, unchangedSCell],
})
```

**Step 5: Run RED**

Run:

```bash
/Users/simon/Tools/MIMO-First/api-service/.venv/bin/pytest -q \
  tests/test_p1_55_carrier_truth_source.py
cd gui && npx tsx --test test/carrierTruthSource.test.ts
```

Expected: failures because the conflict gate, accessor, service canonicalizer and GUI helper do not exist.

**Step 6: Commit RED tests**

```bash
git add api-service/tests/test_p1_55_carrier_truth_source.py gui/test/carrierTruthSource.test.ts
git commit -m "test: define P1-55 carrier truth contract"
```

### Task 2: Implement schema canonicalization and the PCell accessor

**Files:**
- Modify: `api-service/app/schemas/mimo_ota/config.py`
- Modify: `api-service/tests/test_p1_55_carrier_truth_source.py`

**Step 1: Add a before validator**

Copy the incoming dict before modification. When a non-empty PCell exists, compare only explicitly present top-level fields, fill absent mirrors, and raise on conflict:

```python
_PCELL_MIRROR_FIELDS = (
    "frequency_hz",
    "bandwidth_mhz",
    "subcarrier_spacing_khz",
)

@model_validator(mode="before")
@classmethod
def _reject_carrier_truth_conflicts(cls, raw):
    if not isinstance(raw, dict):
        return raw
    data = copy.deepcopy(raw)
    carriers = data.get("component_carriers")
    if not isinstance(carriers, list) or not carriers or not isinstance(carriers[0], dict):
        return data
    pcell = carriers[0]
    for field in _PCELL_MIRROR_FIELDS:
        if field not in pcell:
            continue
        if field in data and data[field] != pcell[field]:
            raise ValueError(
                f"{field} conflicts with component_carriers[0].{field}: "
                f"{data[field]!r} != {pcell[field]!r}"
            )
        data[field] = pcell[field]
    return data
```

Let field validation reject missing/invalid PCell members; do not invent another numeric parser.

**Step 2: Add `primary_carrier`**

Expose a property that returns validated CC[0] and fails loudly if the after-validator invariant is ever broken.

**Step 3: Add a narrow payload canonicalizer**

Validate with `MIMOOTAConfiguration`, then merge only canonical carrier fields and normalized carrier list back into a deep copy of the caller payload. Preserve unrelated sparse/extra keys.

**Step 4: Run schema tests GREEN**

Run the schema subset and relevant existing MIMO config/factory tests. Expected: all pass.

**Step 5: Commit**

```bash
git add api-service/app/schemas/mimo_ota/config.py api-service/tests/test_p1_55_carrier_truth_source.py
git commit -m "feat: enforce PCell carrier truth contract"
```

### Task 3: Put every TestCase write path behind the same gate

**Files:**
- Modify: `api-service/app/services/test_plan_service.py`
- Modify: `api-service/app/api/test_plan.py`
- Modify: `api-service/tests/test_p1_55_carrier_truth_source.py`

**Step 1: Add a domain error and service helper**

For final `test_type == TestCaseType.MIMO_OTA.value`, call the schema payload canonicalizer before constructing the ORM row or assigning `configuration`. Wrap Pydantic validation in `CarrierTruthConflict` with the original actionable detail.

**Step 2: Cover create and update**

- create canonicalizes before `db.add`;
- update loads the row first, computes final type, canonicalizes a supplied configuration before any `setattr`;
- updates with no configuration and all non-MIMO rows retain existing behavior.

**Step 3: Map the domain error to HTTP 422**

Catch only `CarrierTruthConflict` around create/PATCH service calls. Do not broaden all `ValueError` handling.

**Step 4: Run service/API GREEN**

Run the new test file plus existing TestCase CRUD, case-runner and LabProfile binding tests.

**Step 5: Commit**

```bash
git add api-service/app/services/test_plan_service.py api-service/app/api/test_plan.py \
  api-service/tests/test_p1_55_carrier_truth_source.py
git commit -m "fix: reject divergent MIMO carrier writes"
```

### Task 4: Move all MIMO operating-point consumers to PCell

**Files:**
- Modify: `api-service/app/services/mimo_ota/factory.py`
- Modify: `api-service/app/services/mimo_ota/executors/precheck.py`
- Modify: `api-service/app/services/mimo_ota/executors/reference.py`
- Modify: `api-service/app/services/mimo_ota/executors/measure.py`
- Modify: `api-service/tests/test_p1_55_carrier_truth_source.py`

**Step 1: Replace convenience-column reads**

Factory derives `frequency_mhz` and `bandwidth_mhz` from `config.primary_carrier`.

**Step 2: Replace PRECHECK/REFERENCE reads**

Use the same PCell for path-loss windows, pattern lookups, SA center frequency and measurement bandwidth.

**Step 3: Replace every MEASURE top-level operating-point read**

At the start of `execute`, bind `pcell = config.primary_carrier` before any calibration or hardware work. Use it for path loss, probe pattern, ASC `sim_rules`, F64 inputs, evidence/log/result fields and final frequency metadata. Keep SCells from `component_carriers[1:]`.

**Step 4: Re-enumerate consumers**

Run:

```bash
rg -n 'config\.(frequency_hz|bandwidth_mhz|subcarrier_spacing_khz)' \
  api-service/app/services/mimo_ota
```

Every remaining match must be classified as a comment, non-PCell semantic, or defect. Do not leave “probably unused” matches.

**Step 5: Run execution GREEN**

Run new tests and existing factory/precheck/reference/measure/channel-engine suites.

**Step 6: Commit**

```bash
git add api-service/app/services/mimo_ota api-service/tests/test_p1_55_carrier_truth_source.py
git commit -m "fix: consume PCell as MIMO operating truth"
```

### Task 5: Align GUI display and edits with PCell

**Files:**
- Create: `gui/src/components/TestCaseConfig/carrierTruth.ts`
- Modify: `gui/src/components/TestCaseConfig/MIMOOTAConfigForm.tsx`
- Modify: `gui/src/components/TestPlanManagement/TestCaseEditModal.tsx`
- Modify: `gui/test/carrierTruthSource.test.ts`

**Step 1: Implement pure helpers**

`primaryCarrierValue` returns a finite PCell value when available, otherwise the top-level legacy value. `updatePrimaryCarrierValue` updates top-level + PCell and preserves all SCells; no CC means top-level only.

**Step 2: Wire all three controls**

Frequency, bandwidth and SCS display through `primaryCarrierValue`; their change handlers use `updatePrimaryCarrierValue` through one shared component function.

**Step 3: Preserve actionable 422 detail**

Confirm `TestCaseEditModal` catch path prefers `response.data.detail`. If it does not, reuse the existing diagnostic error helper rather than adding a second parser.

**Step 4: Run GUI GREEN and build**

```bash
cd gui
npx tsx --test test/carrierTruthSource.test.ts test/testCaseLabProfileBinding.test.ts
npm run build
```

**Step 5: Commit**

```bash
git add gui/src/components/TestCaseConfig gui/src/components/TestPlanManagement/TestCaseEditModal.tsx \
  gui/test/carrierTruthSource.test.ts
git commit -m "fix: show and edit the PCell carrier truth"
```

### Task 6: Roadmap, full verification and review handoff

**Files:**
- Modify: `docs/roadmap-first-call.md`
- Modify: `docs/plans/2026-08-18-p1-55-carrier-truth-source-design.md`
- Modify: `docs/plans/2026-08-18-p1-55-carrier-truth-source.md`

**Step 1: Update factual mirrors**

Set Current Focus to P1-55 implementation/review state, record the exact producer/consumer closure and retain P1-56 as next item. Do not claim band inference or a database migration.

**Step 2: Run focused and rule-gate verification**

Run all P1-55 focused suites, full `test_rule_gates.py`, compileall, Alembic heads and `git diff --check`.

**Step 3: Run backend and GUI regression**

Run the complete backend test suite and GUI production build. Record any pre-existing order-dependent failure separately and re-run its file in isolation before classifying it.

**Step 4: Fresh internal review**

Enumerate all producers/consumers again and require functional P1=0 before opening a Ready PR. Test findings remain P2/P3 per AGENTS.md.

**Step 5: Commit closeout**

```bash
git add docs/roadmap-first-call.md docs/plans/2026-08-18-p1-55-*.md
git commit -m "docs: record P1-55 verification"
```

**Step 6: External review and merge**

Push, open a Ready PR and trigger Codex R1. Process in-scope R1 feedback, trigger R2, then follow the repository two-round rule: R2 without P1 merges immediately; R2 P1 is fixed and internally verified before merge without R3. After merge, verify `origin/main`, remove the automation and automatically begin P1-56 unless the user changes the queue.
