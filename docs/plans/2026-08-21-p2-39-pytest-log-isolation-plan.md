# P2-39 pytest Log Isolation Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Ensure every pytest process writes and rotates logs only inside its own temporary directory, never the user/runtime log directory.

**Architecture:** Establish the log root in `tests/conftest.py` before importing `app.main`, so the existing `Settings` and `setup_logging()` pipeline remains the single runtime path. Prove isolation through a child pytest process that is deliberately launched with a protected `LOG_DIR` and verify that directory is byte-for-byte untouched.

**Tech Stack:** Python 3.13, pytest, Pydantic Settings, standard-library `tempfile`, existing logging configuration and rule gates.

---

### Task 1: Add the end-to-end isolation regression

**Files:**
- Create: `api-service/tests/test_p2_39_pytest_log_isolation.py`

**Step 1: Write the failing subprocess test**

Create a protected directory containing an old `app.log` plus rotated archives. Snapshot every file's bytes and metadata. Launch:

```python
subprocess.run(
    [
        sys.executable,
        "-m",
        "pytest",
        "tests/test_rule_gates.py::test_g17_tests_never_bring_up_hal_in_real_mode",
        "-q",
    ],
    cwd=API_ROOT,
    env={**os.environ, "LOG_DIR": str(protected_dir)},
    check=False,
    capture_output=True,
    text=True,
)
```

Assert the child succeeds and the protected directory's names, bytes, sizes and mtimes are unchanged.

**Step 2: Run the test and verify RED**

Run:

```bash
.venv/bin/python -m pytest tests/test_p2_39_pytest_log_isolation.py -q
```

Expected: FAIL because the child pytest imports `app.main` with the caller-provided protected directory and creates or rotates runtime log files there.

**Step 3: Commit the RED test**

```bash
git add api-service/tests/test_p2_39_pytest_log_isolation.py
git commit -m "test: prove pytest can mutate runtime logs"
```

### Task 2: Switch pytest to a process-local temporary log root

**Files:**
- Modify: `api-service/tests/conftest.py`
- Test: `api-service/tests/test_p2_39_pytest_log_isolation.py`

**Step 1: Add the minimal pre-import isolation**

Before importing `app.main`, create a module-lifetime `TemporaryDirectory` and force the environment source:

```python
import tempfile

_PYTEST_LOG_ROOT = tempfile.TemporaryDirectory(prefix="meta3d-pytest-logs-")
os.environ["LOG_DIR"] = _PYTEST_LOG_ROOT.name
```

Keep the object referenced at module scope so it survives for the entire pytest process. Do not add branches to `app.main` or `setup_logging()`.

**Step 2: Run the focused test and verify GREEN**

Run:

```bash
.venv/bin/python -m pytest tests/test_p2_39_pytest_log_isolation.py -q
```

Expected: PASS; the child uses its own temporary log root and the protected directory remains unchanged.

**Step 3: Run logging and order regressions**

Run:

```bash
.venv/bin/python -m pytest \
  tests/test_rule_gates.py -k 'g17 or logging or log' \
  tests/test_p1_40_execution_logs.py \
  tests/test_p1_47a_scpi_exchange_evidence.py \
  tests/test_system_logs_tail_filter.py -q
```

Expected: all selected tests PASS.

**Step 4: Commit the implementation**

```bash
git add api-service/tests/conftest.py api-service/tests/test_p2_39_pytest_log_isolation.py
git commit -m "fix: isolate pytest from runtime logs"
```

### Task 3: Add a stable source-order rule gate

**Files:**
- Modify: `api-service/tests/test_rule_gates.py`
- Test: `api-service/tests/test_rule_gates.py`

**Step 1: Write the failing rule assertion**

Extend the conftest ordering contract to require the exact `LOG_DIR` assignment before the first `from app.main import app`. Also assert the assignment uses direct overwrite rather than `setdefault`.

**Step 2: Mutate the source and verify the gate can fail**

Temporarily move the assignment below the application import or replace it with `setdefault`; run the focused gate and observe FAIL. Restore the GREEN source immediately.

**Step 3: Run the rule gates**

Run:

```bash
.venv/bin/python -m pytest tests/test_rule_gates.py -q
```

Expected: all rule gates PASS.

**Step 4: Commit the gate**

```bash
git add api-service/tests/test_rule_gates.py
git commit -m "test: lock pytest log isolation order"
```

### Task 4: Close the roadmap and verify the complete slice

**Files:**
- Modify: `docs/roadmap-first-call.md`
- Modify: `docs/plans/2026-08-21-p2-39-pytest-log-isolation-design.md`

**Step 1: Record exact verification commands and results**

Update the design and roadmap only after the current HEAD passes focused logging tests, complete rule gates, `compileall`, and diff-check. Mark P2-39 as ready for review, not complete.

**Step 2: Run complete verification**

Run:

```bash
.venv/bin/python -m pytest \
  tests/test_p2_39_pytest_log_isolation.py \
  tests/test_p1_40_execution_logs.py \
  tests/test_p1_47a_scpi_exchange_evidence.py \
  tests/test_system_logs_tail_filter.py \
  tests/test_rule_gates.py -q
.venv/bin/python -m compileall -q app tests
git diff --check origin/main...HEAD
```

Expected: tests PASS; compileall and diff-check exit 0. Then run the repository's full backend suite because conftest affects every test process.

**Step 3: Commit the verification state**

```bash
git add docs/roadmap-first-call.md docs/plans/2026-08-21-p2-39-pytest-log-isolation-design.md
git commit -m "docs: record P2-39 verification"
```

**Step 4: Fresh review and PR**

Perform a fresh internal review against the observable failure and AGENTS.md rules. Fix any P1 with RED→GREEN before opening a Ready PR. Trigger Codex R1; after R1 fixes trigger R2, and if R2 or later still has P1 continue P1-only reviews until the latest HEAD has no P1.
