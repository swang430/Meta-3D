# Onsite Logging Sprint Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Complete P1-44, P1-42, P1-40, and P1-37 in one draft PR without mixing in Discovered-scope work.

**Architecture:** Keep the existing JSON log contract and ContextVar model. Improve presentation after parsing, make request context propagation pure ASGI, attach one context-aware execution file handler to the root logger, and make mock transports emit the same structured SCPI evidence shape as real transports while marking responses simulated.

**Tech Stack:** React 18, TypeScript, Mantine, FastAPI/Starlette ASGI, Python logging, SQLAlchemy, pytest, Vite.

---

### Task 1: P1-44 — group continuations before sorting

**Files:**
- Create: `gui/src/utils/logEntries.ts`
- Modify: `gui/src/features/Reports/components/SystemLogViewer.tsx`
- Modify: `gui/src/features/Dashboard/ZoneLogsAlerts.tsx`
- Test: `api-service/tests/test_rule_gates.py`

**Step 1: Write the failing rule gate**

Restore G15 so it requires `groupLogContinuations`, `Set<string>`, immutable reversal, sort-aware auto-scroll, full-field stable identities, and detail rows inside `Table.Tbody`.

**Step 2: Run the gate and verify RED**

Run: `api-service/.venv/bin/pytest api-service/tests/test_rule_gates.py::test_g15_log_sort_groups_continuations_and_uses_stable_identity -q`

Expected: FAIL because `gui/src/utils/logEntries.ts` and component integration do not exist.

**Step 3: Implement continuation grouping and stable keys**

Expose a pure utility with this public shape:

```ts
export type GroupedSystemLogEntry = SystemLogEntry & {
  continuation_lines: string[]
  grouped_raw: string | null
}

export function groupLogContinuations(
  entries: SystemLogEntry[],
): GroupedSystemLogEntry[]
```

RAW rows append to the previous structured row. Build keys from `JSON.stringify` over all entry fields plus `continuation_lines`; count equal entries from newest to oldest so prepending a history page does not renumber existing rows.

**Step 4: Integrate both panels**

Add an ascending/descending control with descending as default. In `SystemLogViewer`, render each parent row and its optional detail row as adjacent keyed fragments and track expansion with `Set<string>`. In `ZoneLogsAlerts`, group first, reverse a copy, and scroll to `0` for descending or `scrollHeight` for ascending.

**Step 5: Verify GREEN and build**

Run:

```bash
api-service/.venv/bin/pytest api-service/tests/test_rule_gates.py::test_g15_log_sort_groups_continuations_and_uses_stable_identity -q
npm run build --prefix gui
```

Expected: gate PASS; Vite production build exits 0.

**Step 6: Commit**

```bash
git add api-service/tests/test_rule_gates.py gui/src/utils/logEntries.ts gui/src/features/Reports/components/SystemLogViewer.tsx gui/src/features/Dashboard/ZoneLogsAlerts.tsx
git commit -m "feat(logs): add stable newest-first views"
```

### Task 2: P1-42 — carry execution context through audit middleware

**Files:**
- Modify: `api-service/app/core/audit_middleware.py`
- Modify: `api-service/app/api/test_execution.py`
- Test: `api-service/tests/test_p1_42_audit_execution_context.py`
- Test: `api-service/tests/test_p1_34_log_timeline.py`
- Test: `api-service/tests/test_p1_36_execution_id.py`

**Step 1: Write failing direct-ASGI tests**

Construct one ASGI app that sets `current_execution_id` in an async endpoint and assert the emitted `app.audit` record contains that exact ID. Call the same middleware instance twice in one task and assert the unrelated second request records `-`. Add WebSocket coverage asserting a non-default request ID is visible downstream. Keep 4xx/5xx exclusion-path behavior covered.

**Step 2: Run tests and verify RED**

Run: `api-service/.venv/bin/pytest api-service/tests/test_p1_42_audit_execution_context.py -q`

Expected: FAIL because `BaseHTTPMiddleware` loses the endpoint ContextVar and bypasses WebSockets.

**Step 3: Replace BaseHTTPMiddleware with pure ASGI**

Implement `async def __call__(scope, receive, send)`. For HTTP, intercept `http.response.start` to capture status, preserve exception propagation and existing exclusion semantics, log after downstream completion, then reset both request and execution ContextVar tokens in `finally`. For WebSocket, set/reset request context around the downstream app without emitting an HTTP summary.

**Step 4: Handle cancellation endpoint context**

Convert `cancel_case_execution` to `async def` only if its existing synchronous DB work remains behaviorally identical; otherwise pass the resolved execution ID through request state at that one boundary. Do not change other execution setters.

**Step 5: Verify GREEN and regression**

Run:

```bash
api-service/.venv/bin/pytest api-service/tests/test_p1_42_audit_execution_context.py api-service/tests/test_p1_34_log_timeline.py api-service/tests/test_p1_36_execution_id.py -q
```

Expected: all selected tests PASS.

**Step 6: Commit**

```bash
git add api-service/app/core/audit_middleware.py api-service/app/api/test_execution.py api-service/tests/test_p1_42_audit_execution_context.py api-service/tests/test_p1_34_log_timeline.py api-service/tests/test_p1_36_execution_id.py
git commit -m "feat(logs): link audit summaries to executions"
```

### Task 3: P1-40 — route detailed logs into execution files

**Files:**
- Modify: `api-service/app/core/logging_config.py`
- Modify: `api-service/app/services/test_case_runner.py`
- Modify: `api-service/app/api/system_logs.py`
- Test: `api-service/tests/test_p1_40_execution_logs.py`
- Test: `api-service/tests/test_system_logs_tail_filter.py`

**Step 1: Write failing handler lifecycle tests**

Assert that `execution_id == "-"` never creates an execution file, that two IDs route to separate flat `exec-<uuid>.log` files, that DEBUG is absent from `app.log` but present in the execution file, and that closing one execution releases its handler without affecting another.

**Step 2: Run tests and verify RED**

Run: `api-service/.venv/bin/pytest api-service/tests/test_p1_40_execution_logs.py -q`

Expected: FAIL because no execution-aware handler exists and `app.log` still accepts DEBUG.

**Step 3: Implement the execution-aware handler**

Add one root handler that inspects the ContextFilter-populated `execution_id`, validates UUID-like safe IDs, lazily opens `exec-<execution_id>.log`, formats with the existing `JsonFormatter`, and exposes `close_execution_log(execution_id)`. Set the persistent `file_app` handler to INFO. Mark `exec-*` files non-current in `/system-logs/files`.

**Step 4: Wire lifecycle cleanup**

Close the execution file in `_run_case` finalization and equivalent local execution completion paths. The repository currently has no TestExecution deletion endpoint, so do not add an unreachable deletion hook; record file deletion coupling as a follow-up prerequisite for any future execution-delete API.

**Step 5: Verify GREEN**

Run:

```bash
api-service/.venv/bin/pytest api-service/tests/test_p1_40_execution_logs.py api-service/tests/test_system_logs_tail_filter.py api-service/tests/test_p1_36_execution_id.py -q
```

Expected: all selected tests PASS.

### Task 4: P1-40 — suppress duplicate bursts without hiding evidence

**Files:**
- Modify: `api-service/app/core/logging_config.py`
- Test: `api-service/tests/test_p1_40_execution_logs.py`

**Step 1: Write failing suppression tests**

Use a fake clock and assert the first N equal `(logger, message template)` records are retained, subsequent records are suppressed within the window, and the next different/expired record emits exactly one `same message suppressed xN` summary before normal output. Assert different logger or message does not share a bucket.

**Step 2: Run the focused test and verify RED**

Run: `api-service/.venv/bin/pytest api-service/tests/test_p1_40_execution_logs.py -k suppression -q`

Expected: FAIL because duplicate suppression is absent.

**Step 3: Implement one reusable suppression policy**

Keep bounded state keyed by logger and `record.msg` template, not rendered exception text. Apply it to execution files and the dedicated SCPI file. Summary records bypass their own suppression path and retain execution/instrument context.

**Step 4: Verify GREEN and commit P1-40**

Run: `api-service/.venv/bin/pytest api-service/tests/test_p1_40_execution_logs.py api-service/tests/test_system_logs_tail_filter.py api-service/tests/test_p1_35_log_value_policy.py api-service/tests/test_p1_36_execution_id.py -q`

Expected: all selected tests PASS.

```bash
git add api-service/app/core/logging_config.py api-service/app/services/test_case_runner.py api-service/app/api/system_logs.py api-service/tests/test_p1_40_execution_logs.py api-service/tests/test_system_logs_tail_filter.py
git commit -m "feat(logs): isolate and bound execution logs"
```

### Task 5: P1-37 — emit real SCPI intent from mock drivers

**Files:**
- Modify: `api-service/app/hal/base.py`
- Modify: `api-service/app/hal/base_station.py`
- Modify: `api-service/app/hal/channel_emulator.py`
- Modify: `api-service/app/hal/signal_analyzer.py`
- Modify: `api-service/app/hal/positioner.py`
- Modify: `api-service/app/hal/rf_switch.py`
- Modify only if active HAL uses it: `api-service/app/services/mock_instruments.py`
- Test: `api-service/tests/test_p1_37_mock_scpi_logging.py`
- Test: `api-service/tests/test_scpi_log_evidence.py`

**Step 1: Write failing TX/RX source tests**

For each active mock category, invoke one representative operation and capture `app.hal.scpi.*`. Assert a production-format command appears on TX/OK and a mock reply appears on RX with `simulated is True` and the concrete `instrument_id`. Add a negative test that a simulated measurement cannot be serialized as an authoritative measurement/report value.

**Step 2: Run tests and verify RED**

Run: `api-service/.venv/bin/pytest api-service/tests/test_p1_37_mock_scpi_logging.py -q`

Expected: FAIL because active mocks do not emit SCPI exchanges.

**Step 3: Add a shared simulated transport boundary**

Extend the existing `_log_scpi_write` / `_log_scpi_response` path with an explicit per-driver source field. Add a helper that records a command/query using the same exchange structure as real transport, but marks mock responses `simulated=True`. Do not infer simulation from global `hal_mode`.

**Step 4: Reuse production command builders in mocks**

Move only command-string construction needed by active operations into side-effect-free helpers shared by real and mock drivers. Mock methods call those builders and the simulated transport helper, then preserve their existing state/result behavior. Do not build a second instrument state machine.

**Step 5: Enforce the truth boundary**

At measurement/KPI/report normalization boundaries, reject or mark N/A any value carrying simulated provenance. Keep simulated responses visible in `scpi.log` and execution logs.

**Step 6: Verify GREEN and commit**

Run:

```bash
api-service/.venv/bin/pytest api-service/tests/test_p1_37_mock_scpi_logging.py api-service/tests/test_scpi_log_evidence.py api-service/tests/test_mimo_ota_precheck_cal_gate.py api-service/tests/test_mimo_ota_reference_trp_marking.py -q
git add api-service/app/hal api-service/app/services api-service/tests/test_p1_37_mock_scpi_logging.py api-service/tests/test_scpi_log_evidence.py
git commit -m "feat(logs): record simulated SCPI exchanges"
```

Expected: all selected tests PASS.

### Task 6: Contract, roadmap, full verification, and publication

**Files:**
- Modify: `docs/roadmap-first-call.md`
- Modify: `docs/plans/2026-08-07-log-sprint.md` only if implementation discoveries change exact commands
- Modify generated API types only if the wire schema changes

**Step 1: Run complete verification**

Run:

```bash
api-service/.venv/bin/pytest api-service/tests -q
npm run build --prefix gui
git diff --check origin/main...HEAD
```

Expected: backend suite has zero failures; GUI build exits 0; diff check is clean.

**Step 2: Update roadmap truthfully**

Mark only fully verified items complete, set Current Focus to the next open roadmap item, and record any incomplete edge as Backlog/Discovered rather than hiding it.

**Step 3: Commit and push**

```bash
git add docs/roadmap-first-call.md docs/plans/2026-08-07-log-sprint.md
git commit -m "docs: close onsite logging sprint"
git push origin codex/onsite-20260807
```

**Step 4: Review**

Run the established internal reviewer against the final diff. After internal findings are resolved and tests rerun, request GitHub Codex review on Draft PR #303. Do not mark ready or merge until both review channels and late comments are checked.
