# P1-38 Alert Hygiene Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task.

**Goal:** Remove historical `test_suite` alert pollution safely, prevent recurrence, and replace the unsupported alert detail panel with a compact summary badge.

**Architecture:** Keep the existing alert table and summary API. Add a white-list, dry-run-first cleanup script plus a repository guard for test DB isolation; on the GUI, consume only the summary endpoint and give the released width to the log panel. Production alert producers remain a separate P3-19 increment.

**Tech Stack:** FastAPI, SQLAlchemy, pytest, React 18, TypeScript, Mantine, TanStack Query.

---

### Task 1: Lock test isolation and add the precise cleanup tool

**Files:**
- Create: `api-service/tests/test_p1_38_alert_hygiene.py`
- Create: `api-service/scripts/cleanup_test_suite_alerts.py`
- Modify: `api-service/tests/test_rule_gates.py`

**Step 1: Write failing tests**

Add SQLite-backed tests that create the two exact historical test artifacts plus near-miss rows. Assert dry-run reports two candidates without mutation; execute deletes only exact candidates; source/cutoff/content near misses remain. Add a rule-gate self-test and live-tree assertion that any test source writing `source=test_suite` also declares an isolated SQLite engine and a `get_db` dependency override.

**Step 2: Verify RED**

Run:

```bash
/Users/simon/Tools/MIMO-First/api-service/.venv/bin/python -m pytest -q \
  tests/test_p1_38_alert_hygiene.py \
  tests/test_rule_gates.py::test_g20_test_suite_alert_writers_are_db_isolated
```

Expected: FAIL because the cleanup module and G20 do not exist.

**Step 3: Implement the minimum**

Implement a dialect-independent SQLAlchemy cleanup function and CLI. Default to dry-run; require `--execute`; use the approved exact predicate and one transaction. Implement G20 using repository source enumeration, not a hard-coded single filename.

**Step 4: Verify GREEN**

Run the RED command again, then run `tests/test_feature_gaps.py`, `tests/test_alert_summary_route.py`, and complete `tests/test_rule_gates.py`.

**Step 5: Commit**

```bash
git add api-service/scripts/cleanup_test_suite_alerts.py \
  api-service/tests/test_p1_38_alert_hygiene.py api-service/tests/test_rule_gates.py
git commit -m "fix: quarantine and clean test alert pollution"
```

### Task 2: Replace the alert detail panel with a summary badge

**Files:**
- Modify: `gui/src/features/Dashboard/ZoneLogsAlerts.tsx`
- Modify: `gui/src/features/Dashboard/DashboardCockpit.tsx`
- Modify: `api-service/tests/test_p1_38_alert_hygiene.py`

**Step 1: Write the failing contract test**

Assert the live dashboard component no longer imports/calls `fetchAlerts`, no longer defines the large `AlertPanel`, still calls `fetchAlertSummary`, exposes loading/error/zero/nonzero badge states, and no longer renders the 7/5 split grid.

**Step 2: Verify RED**

Run:

```bash
/Users/simon/Tools/MIMO-First/api-service/.venv/bin/python -m pytest -q \
  tests/test_p1_38_alert_hygiene.py::test_dashboard_uses_compact_alert_summary_badge
```

Expected: FAIL because the large alert list panel still exists.

**Step 3: Implement the minimum**

Move the summary query into a compact badge in the log card heading; compute color from the highest nonzero severity; show the breakdown in a tooltip; remove only the alert list query/card and split grid. Preserve the backend detail API and service helper.

**Step 4: Verify GREEN and build**

Run the contract test, then:

```bash
npm run build
```

Expected: PASS and Vite production build completes.

**Step 5: Commit**

```bash
git add gui/src/features/Dashboard/ZoneLogsAlerts.tsx \
  gui/src/features/Dashboard/DashboardCockpit.tsx \
  api-service/tests/test_p1_38_alert_hygiene.py
git commit -m "fix: shrink dashboard alerts to summary badge"
```

### Task 3: Close P1-38 and verify the integrated slice

**Files:**
- Modify: `docs/roadmap-first-call.md`

**Step 1: Update roadmap mirrors**

Mark P1-38 complete, advance Current Focus to P1-27, record the cleanup predicate and observed production distribution, and keep production alert producers assigned to P3-19.

**Step 2: Run integrated verification**

Run the P1-38 test, feature-gap/summary regressions, complete rule gates, `git diff --check`, GUI production build, and the cleanup CLI in dry-run mode against the live database. The dry-run must report exactly 674 candidates and perform no deletion.

**Step 3: Commit**

```bash
git add docs/roadmap-first-call.md
git commit -m "docs: close P1-38 and advance roadmap"
```

### Task 4: Review and publish

Run internal spec and code-quality reviews over `origin/main..HEAD`; fix all functional P1 findings with TDD. Push `codex/p1-38-alert-panel-hygiene`, open a ready PR, request `@codex review`, and follow the established loop: P1 fixes are unbounded; P2/P3 are recorded once. When the final reviewed HEAD has no major functional issue and checks are green, merge with a merge commit and begin P1-27 from the new `origin/main`.

