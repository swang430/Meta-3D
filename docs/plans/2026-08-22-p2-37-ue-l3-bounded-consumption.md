# P2-37 UE L3 Report Bounded Consumption Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Stop background monitoring from fetching the unbounded UXM UE L3 report queue while preserving a fail-closed, explicitly cleared L3 evidence window for formal throughput measurements.

**Architecture:** Keep the existing documented SCPI commands and parser. Add an internal opt-out for the L3 fetch, use it from background `get_metrics()`, and make `measure_throughput_window()` clear and verify the UE report queue before the observation window. If clear cannot be trusted, skip only L3 evidence and retain all other KPI reads.

**Tech Stack:** Python 3.13, asyncio, pytest, existing UXM HAL template methods and SCPI error-queue helpers.

---

### Task 1: Lock the background-consumer failure with RED tests

**Files:**
- Modify: `api-service/tests/test_uxm_kpi_readback.py`

**Step 1: Strengthen the connected monitoring test**

Extend `TestMonitoringStateGate.test_get_metrics_reads_kpis_when_cell_is_connected` so the fake has a recognizable UE report response and assert:

```python
assert any("THRoughput:OTA" in cmd for cmd in queries)
assert not any("MEASurement:JSON:REPort:FETCh" in cmd for cmd in queries)
```

This locks the product behavior: background monitoring still reads displayed KPI values but does not fetch undisplayed raw L3 history.

**Step 2: Run the test and verify RED**

Run:

```bash
cd api-service
.venv/bin/python -m pytest \
  tests/test_uxm_kpi_readback.py::TestMonitoringStateGate::test_get_metrics_reads_kpis_when_cell_is_connected -q
```

Expected: FAIL because current `get_metrics()` calls the L3 `FETCh?` through `get_throughput_metrics()`.

**Step 3: Commit the RED test**

Do not commit production code yet. Keep the failing test in the worktree for Task 2.

### Task 2: Remove L3 fetching from background monitoring

**Files:**
- Modify: `api-service/app/hal/uxm_base_station.py:3077-3260`
- Test: `api-service/tests/test_uxm_kpi_readback.py`

**Step 1: Add an internal L3-read switch**

Change the signature to:

```python
async def get_throughput_metrics(
    self,
    *,
    throughput_scope: str = ThroughputMetrics.SCOPE_PCELL,
    _read_ue_report: bool = True,
) -> ThroughputMetrics:
```

Gate only the existing `MEAS_UE_REPORT_JSON` block with `_read_ue_report`. When false, keep `valid["rsrp"]` and `valid["sinr"]` false and emit at most a debug explanation; do not issue a clear or fetch from this method.

**Step 2: Make background monitoring opt out**

In `RealUxmDriver.get_metrics()` call:

```python
await self.get_throughput_metrics(_read_ue_report=False)
```

Do not change the non-connected gate or formal callers.

**Step 3: Run the focused test and verify GREEN**

Run the Task 1 command.

Expected: PASS; trace contains the cell-state and ordinary KPI queries but no UE report fetch.

**Step 4: Run direct-reader regressions**

Run:

```bash
.venv/bin/python -m pytest \
  tests/test_uxm_kpi_readback.py::TestUeMeasurementReportParsing \
  tests/test_uxm_kpi_readback.py::TestUnverifiedUnitsNotClaimedAsEngineering -q
```

Expected: PASS; direct/formal default behavior still retains raw unverified evidence.

**Step 5: Commit**

```bash
git add api-service/app/hal/uxm_base_station.py \
  api-service/tests/test_uxm_kpi_readback.py
git commit -m "fix: stop background UE report queue fetches"
```

### Task 3: Define a verified L3 observation window with RED tests

**Files:**
- Modify: `api-service/tests/test_uxm_kpi_readback.py`

**Step 1: Add formal-window tests**

Add `TestFormalUeReportWindow` with cases that use `_stub_io()` and trace ordering:

1. `test_clear_precedes_formal_l3_fetch`: `MEAS_UE_REPORT_CLEAR` write occurs before the L3 fetch and the fetched raw value remains in `kpi_raw_unverified` only.
2. `test_missing_clear_suppresses_only_l3_fetch`: set the instance profile clear command to `None`; ordinary throughput is read, L3 fetch is absent, and RSRP/SINR remain invalid.
3. `test_clear_write_exception_suppresses_l3_fetch`: inject an exception for the clear write; ordinary KPI reads remain.
4. `test_clear_rejection_suppresses_l3_fetch`: baseline error queue is clean, clear write queues an instrument error, and the L3 fetch is absent.

The fake error queue must return `0,"No error"` except for the specific rejected-clear case so acceptance is attributed to the correct write.

**Step 2: Run the new class and verify RED**

Run:

```bash
.venv/bin/python -m pytest tests/test_uxm_kpi_readback.py::TestFormalUeReportWindow -q
```

Expected: failures because the production window currently clears only throughput and always fetches L3.

### Task 4: Implement fail-closed UE report clearing

**Files:**
- Modify: `api-service/app/hal/uxm_base_station.py:3291-3331`
- Test: `api-service/tests/test_uxm_kpi_readback.py`

**Step 1: Add a narrow helper**

Add a private synchronous helper beside the throughput reader:

```python
def _clear_ue_report_window(self) -> bool:
    clear_cmd = self._cmds.MEAS_UE_REPORT_CLEAR
    if not clear_cmd:
        logger.warning("...")
        return False
    try:
        baseline = self._drain_errors()
        if self._error_queue_unusable(baseline):
            logger.warning("...")
            return False
        self._write(clear_cmd)
        errors = self._drain_errors()
        if errors:
            logger.warning("...")
            return False
        return True
    except Exception as exc:
        logger.warning("...")
        return False
```

Historical baseline errors may be logged after being drained; only an unusable error-query path blocks the write. Any post-write error blocks L3 fetch. Do not add a new SCPI command.

**Step 2: Integrate it into the formal window**

At the beginning of `measure_throughput_window()`, before sleep, evaluate the helper independently of throughput clear:

```python
ue_report_window_ready = self._clear_ue_report_window()
```

Pass `_read_ue_report=ue_report_window_ready` to every `get_throughput_metrics()` return path, including the branch where the throughput clear command is absent.

**Step 3: Run the formal-window tests**

Run the Task 3 command.

Expected: all tests PASS.

**Step 4: Run the complete focused group**

```bash
.venv/bin/python -m pytest \
  tests/test_uxm_kpi_readback.py \
  tests/test_uxm_kpi_readback_sequence.py -q
```

Expected: PASS. The independent diagnostic sequence keeps its existing clear/window/fetch behavior.

**Step 5: Commit**

```bash
git add api-service/app/hal/uxm_base_station.py \
  api-service/tests/test_uxm_kpi_readback.py
git commit -m "fix: bound formal UE report observation windows"
```

### Task 5: Enumerate downstream consumers and run complete regressions

**Files:**
- Modify if needed: `api-service/tests/test_p1_54_kpi_valid_contract.py`
- Modify if needed: `api-service/tests/test_p1_59_ca_throughput_truth.py`
- Modify: `docs/plans/2026-08-22-p2-37-ue-l3-bounded-consumption-design.md`
- Modify: `docs/roadmap-first-call.md`

**Step 1: Re-run the producer/consumer inventory**

```bash
git grep -n 'MEAS_UE_REPORT_' -- api-service/app api-service/tests
git grep -n 'get_throughput_metrics(' -- api-service/app api-service/tests
git grep -n 'measure_throughput_window' -- api-service/app api-service/tests
```

Confirm every production caller is one of background monitoring, formal window, or the independent diagnostic sequence. Add tests only for an actual uncovered active path.

**Step 2: Run related and rule-gate tests**

```bash
.venv/bin/python -m pytest \
  tests/test_uxm_kpi_readback.py \
  tests/test_uxm_kpi_readback_sequence.py \
  tests/test_p1_54_kpi_valid_contract.py \
  tests/test_p1_59_ca_throughput_truth.py \
  tests/test_mimo_ota_executor.py \
  tests/test_rule_gates.py -q
```

Expected: PASS.

**Step 3: Run full backend and static verification**

```bash
.venv/bin/python -m pytest -q
.venv/bin/python -m compileall -q app tests
git diff --check origin/main...HEAD
```

Expected: all tests pass; compileall and diff-check exit 0.

**Step 4: Record evidence**

Update the design and roadmap with exact commit, commands, pass counts, and the statement that L3 units remain unverified and no new SCPI was introduced. Mark P2-37 ready for review, not complete.

**Step 5: Commit**

```bash
git add docs/plans/2026-08-22-p2-37-ue-l3-bounded-consumption-design.md \
  docs/roadmap-first-call.md
git commit -m "docs: record P2-37 verification"
```

### Task 6: Fresh review and external closure

**Files:**
- Review all files changed from `origin/main...HEAD`.

**Step 1: Fresh internal review**

Review against AGENTS.md, especially: complete producer/consumer inventory, hardware write error consumption, safety asymmetry, no new undocumented SCPI, and unverified values staying out of formal KPI. Fix P1 with RED→GREEN until P1=0.

**Step 2: Open a Ready PR and request Codex review**

Push the branch, open a Ready PR, and trigger R1. Apply executable in-scope R1 findings with TDD, fresh review, and regression before requesting R2.

**Step 3: Merge rule**

If R2 has no P1 and the PR is mergeable with required checks passing or absent, merge with a merge commit. If R2 or later has P1, repair it and continue P1-only review until a Codex review covers the latest HEAD with no P1. Later-round P2/P3 are reported but do not block or auto-enter backlog.

**Step 4: Continue queue**

After verifying `origin/main`, delete the P2-37 automation and start P2-38 from latest main unless the user asks to pause.
