# P2-40 Development Artifact Governance Implementation Plan

> **For Codex:** REQUIRED SUB-SKILL: Use `executing-plans` to implement this plan task-by-task.

**Goal:** Produce a deterministic, read-only inventory of development DB/log/worktree/Docker artifacts, stop four calibration tests from leaving repository SQLite files, and prepare an exact reversible-cleanup approval packet without deleting anything in this PR.

**Architecture:** A standard-library inventory module discovers only registered Git worktrees and explicit artifact roots, collects identity evidence, then applies a conservative pure classification function. JSON and Markdown renderers share that model. Test databases move to pytest-owned temporary paths. Actual backup/quarantine/delete operations remain outside the CLI and behind user approval.

**Tech Stack:** Python 3.13, pathlib, sqlite3 read-only URI, subprocess, pytest, existing Git/Docker CLIs.

---

### Task 1: Lock the conservative inventory contract in RED tests

**Files:**
- Create: `api-service/tests/test_p2_40_dev_artifact_inventory.py`
- Create: `api-service/scripts/dev_artifact_inventory.py`

**Step 1: Write failing tests for the pure model and scanner**

Build temporary registered-worktree fixtures containing logs, symlinks, known empty legacy test SQLite,
unknown/non-empty SQLite and unrelated untracked files. Assert:

- only explicit artifact roots are scanned;
- symlinks are reported or skipped without following their target;
- known test DB requires both exact legacy path and empty schema;
- unknown/non-empty/open DB stays `protect`;
- JSON ordering is deterministic and Markdown derives from the same entries;
- no delete/move/execute CLI option exists.

**Step 2: Run and verify RED**

```bash
cd api-service
.venv/bin/python -m pytest tests/test_p2_40_dev_artifact_inventory.py -q
```

Expected: FAIL because the inventory implementation does not exist.

**Step 3: Commit RED**

```bash
git add api-service/tests/test_p2_40_dev_artifact_inventory.py \
  api-service/scripts/dev_artifact_inventory.py
git commit -m "test: define artifact inventory safety contract"
```

### Task 2: Implement read-only filesystem and SQLite inventory

**Files:**
- Modify: `api-service/scripts/dev_artifact_inventory.py`
- Test: `api-service/tests/test_p2_40_dev_artifact_inventory.py`

**Step 1: Implement the minimal model and discovery**

Parse `git worktree list --porcelain`; record worktree identity and dirty state. Scan only each worktree's
`api-service/logs` plus exact SQLite extensions outside pruned dependency/manual roots. Use `lstat`, never
follow symlinks, and open SQLite with `file:<path>?mode=ro`.

**Step 2: Implement conservative classification**

Default every entry to `protect`. Only four exact legacy test DB basenames under repository root or
`api-service`, with a valid SQLite header, empty schema, ignored/untracked state and no detected open handle,
may become `quarantine_candidate`. Detection unavailable means `protect`.

**Step 3: Implement JSON and Markdown output**

Default output is JSON on stdout. `--format markdown` renders the same sorted model. The parser exposes no
mutation option.

**Step 4: Run focused tests and verify GREEN**

```bash
.venv/bin/python -m pytest tests/test_p2_40_dev_artifact_inventory.py -q
```

**Step 5: Commit**

```bash
git add api-service/scripts/dev_artifact_inventory.py \
  api-service/tests/test_p2_40_dev_artifact_inventory.py
git commit -m "feat: add read-only development artifact inventory"
```

### Task 3: Add optional Docker metadata without weakening safety

**Files:**
- Modify: `api-service/scripts/dev_artifact_inventory.py`
- Modify: `api-service/tests/test_p2_40_dev_artifact_inventory.py`

**Step 1: Add RED fixtures for Docker states**

Mock CLI output for mounted named volume, unmounted anonymous volume, Docker unavailable and malformed
records. Assert mounted is `protect`, anonymous unmounted is `review`, and unavailable/malformed never
becomes a candidate.

**Step 2: Implement read-only Docker collection**

Use only `docker ps`, `docker volume ls/inspect` and `docker system df -v`; record commands that were
unavailable. Never invoke run, exec, stop, rm, prune or compose mutation commands.

**Step 3: Run focused tests and commit**

```bash
.venv/bin/python -m pytest tests/test_p2_40_dev_artifact_inventory.py -q
git add api-service/scripts/dev_artifact_inventory.py \
  api-service/tests/test_p2_40_dev_artifact_inventory.py
git commit -m "feat: inventory Docker database volumes safely"
```

### Task 4: Stop fixed-path calibration SQLite residue

**Files:**
- Modify: `api-service/tests/test_channel_calibration.py`
- Modify: `api-service/tests/test_probe_calibration_api.py`
- Modify: `api-service/tests/test_probe_calibration_service.py`
- Modify: `api-service/tests/test_probe_calibration_integration.py`
- Modify: `api-service/tests/test_p2_40_dev_artifact_inventory.py`

**Step 1: Add the subprocess RED regression**

From a protected temporary cwd, run the four test modules and snapshot the cwd/repository DB manifests.
Before the refactor the fixed `sqlite:///./test_*.db` paths leave files in the child cwd; assert no new DB
is left.

**Step 2: Verify RED**

```bash
.venv/bin/python -m pytest tests/test_p2_40_dev_artifact_inventory.py \
  -k calibration_tests_leave_no_sqlite -q
```

**Step 3: Move engines to pytest temporary paths**

Use `tmp_path` for the function-scoped channel fixture and `tmp_path_factory` for module-scoped probe
fixtures. Build engine/session/dependency override inside the fixture so no import-time relative DB is
created; dispose the engine during teardown.

**Step 4: Run focused calibration regressions**

```bash
.venv/bin/python -m pytest \
  tests/test_channel_calibration.py \
  tests/test_probe_calibration_api.py \
  tests/test_probe_calibration_service.py \
  tests/test_probe_calibration_integration.py \
  tests/test_p2_40_dev_artifact_inventory.py -q
```

**Step 5: Commit**

```bash
git add api-service/tests/test_channel_calibration.py \
  api-service/tests/test_probe_calibration_api.py \
  api-service/tests/test_probe_calibration_service.py \
  api-service/tests/test_probe_calibration_integration.py \
  api-service/tests/test_p2_40_dev_artifact_inventory.py
git commit -m "test: isolate calibration SQLite artifacts"
```

### Task 5: Generate the real dry-run approval packet

**Files:**
- Modify: `docs/plans/2026-08-21-p2-40-dev-artifact-governance-design.md`
- Modify: `docs/roadmap-first-call.md`

**Step 1: Run inventory against the real repository**

```bash
cd api-service
.venv/bin/python scripts/dev_artifact_inventory.py \
  --repo-root .. --format json > /tmp/meta3d-p2-40-manifest.json
.venv/bin/python scripts/dev_artifact_inventory.py \
  --repo-root .. --format markdown > /tmp/meta3d-p2-40-manifest.md
```

Review every candidate against its evidence. Do not move or delete it.

**Step 2: Record reproducible totals**

Update the design with the current HEAD, exact commands, counts/bytes by disposition and explicit lists of
protected live DB/log/unknown volumes. Add the proposed external quarantine path, checksum manifest and
restore commands, clearly marked “not executed”.

**Step 3: Commit documentation state**

```bash
git add docs/plans/2026-08-21-p2-40-dev-artifact-governance-design.md \
  docs/roadmap-first-call.md
git commit -m "docs: record P2-40 dry-run manifest"
```

### Task 6: Verify, review, and stop at the cleanup approval point

**Step 1: Run complete verification**

```bash
cd api-service
.venv/bin/python -m pytest \
  tests/test_p2_40_dev_artifact_inventory.py \
  tests/test_channel_calibration.py \
  tests/test_probe_calibration_api.py \
  tests/test_probe_calibration_service.py \
  tests/test_probe_calibration_integration.py \
  tests/test_rule_gates.py -q
.venv/bin/python -m compileall -q app scripts tests
git diff --check origin/main...HEAD
```

Then run the full backend suite because calibration fixtures and shared models are imported broadly.

**Step 2: Fresh internal review**

Review the scanner's complete allowlist, every disposition transition, symlink handling, command failure,
SQLite read-only mode and output claims against AGENTS.md. Fix P1 through RED→GREEN until P1=0.

**Step 3: PR and Codex review**

Open a Ready PR. Process R1 findings, then request R2; if R2 or later still has P1, continue P1-only review
until the latest HEAD is covered with no P1.

**Step 4: Present the separate operation approval packet — ✅ completed 2026-08-22**

After merge, show the user exact quarantine candidates and recovery plan. Do not create backup, move,
delete, prune or remove worktrees until explicit approval. P2-40 code completion and artifact cleanup are
reported as separate states.

Historical outcome: the user separately approved quarantine and then permanent deletion. Exactly 20 closed,
zero-schema test SQLite files (21,299,200 bytes) were quarantined and permanently deleted. Runtime logs,
production PostgreSQL, Docker volumes and worktrees remained protected. The deleted data is not recoverable;
the immutable operation evidence is retained in
`/Users/simon/Meta3D-Artifacts/quarantine/2026-08-22-p2-40-deletion-receipt.json` and
`/Users/simon/Meta3D-Artifacts/quarantine/2026-08-22-p2-40-moves.json`. This step is complete and must not be
re-run from this plan.
