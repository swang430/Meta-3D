# P2-31 SMB `.smu` Project Truth Scan Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace filename/manual-table frequency registration with a bounded read-only scan of an explicitly mounted F64 SMB project tree, then atomically synchronize only exact, provable ChannelAsset matches.

**Architecture:** A pure inventory service reads configured local `.smu` copies and derives truth only from `[Channel Group 0] CenterFrequency`. Static ChannelAsset endpoints expose preview and server-side re-scan/sync. Sync updates an exact-path vendor asset plus its `available_channel_models` projection in one transaction; ambiguous, unregistered, non-raster, or malformed items remain visible and untouched.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy, Pydantic v2, React 18, TanStack Query, Mantine, TypeScript, pytest, Node test runner, OpenAPI.

---

### Task 1: Build the bounded read-only inventory

**Files:**
- Create: `api-service/tests/test_smu_project_inventory.py`
- Create: `api-service/app/services/smu_project_inventory.py`
- Modify: `api-service/app/hal/smu_project.py`

**Step 1: Write RED tests**

Use `tmp_path` as a fake SMB mount and cover:

- lying filename `..._3600M.smu` with group 0 = `3549990000 Hz`;
- multiple groups preserved, but missing group 0 is an explicit parse failure;
- deterministic Windows path mapping from configured roots;
- UTF-8 BOM / UTF-16 BOM / single-byte text;
- symlink entries skipped; relative/missing/symlink root refused;
- file/count/total-byte limits fail the whole inventory rather than returning a partial result.

**Step 2: Verify RED**

Run:

```bash
cd api-service
.venv/bin/python -m pytest -q tests/test_smu_project_inventory.py -o log_cli=false
```

Expected: import/service failures because the inventory does not exist.

**Step 3: Implement the smallest pure scanner**

Add frozen result/item dataclasses and one scanner that accepts the already-resolved local root and F64 root.
Reuse `parse_smu_project_center_freqs_hz`; do not call `parse_smu_center_freq_mhz`. Compute SHA-256 while
reading bounded bytes. Require group 0 for a sync candidate and sort by normalized relative path.

**Step 4: Verify GREEN and mutation**

Run the focused tests. Temporarily replace parsed group 0 with a filename token and confirm the lying-filename
test fails, then restore.

**Step 5: Commit**

```bash
git add api-service/app/hal/smu_project.py api-service/app/services/smu_project_inventory.py api-service/tests/test_smu_project_inventory.py
git commit -m "feat: scan mounted smu projects for internal truth"
```

### Task 2: Classify exact ChannelAsset matches and synchronize atomically

**Files:**
- Modify: `api-service/tests/test_smu_project_inventory.py`
- Modify: `api-service/app/services/smu_project_inventory.py`
- Modify: `api-service/app/services/channel_asset_service.py`

**Step 1: Write RED service tests**

Build SQLite fixtures for the unique `channelEmulator` connection, vendor assets, and raw
`available_channel_models`. Cover:

1. exact Windows-path match with null legacy binding becomes `syncable`;
2. one-click sync updates asset ARFCN, top-level Hz, binding, provenance, canonical name, and the channel-model
   projection together;
3. unknown payload and projection keys remain byte-for-byte equivalent;
4. unregistered, duplicate-path, inactive, other-binding, parse-failed and non-raster items are not written;
5. duplicate canonical name or any validation error rolls back every planned write.

**Step 2: Verify RED**

Run the focused file; expected failures are missing classify/sync functions.

**Step 3: Implement preflight plus one transaction**

Resolve scan config only from the unique channelEmulator connection. Normalize Windows paths in one helper.
Precompute final payload/canonical/projection entries and validate every candidate before mutating ORM objects.
Commit once. Do not call the existing per-asset `update_channel_asset()` because it commits each row.

**Step 4: Verify GREEN and rollback behavior**

Run the focused tests and assert database snapshots before/after a forced last-candidate conflict are identical.

**Step 5: Commit**

```bash
git add api-service/app/services/channel_asset_service.py api-service/app/services/smu_project_inventory.py api-service/tests/test_smu_project_inventory.py
git commit -m "feat: synchronize exact smu truth matches atomically"
```

### Task 3: Add static preview and sync endpoints

**Files:**
- Create: `api-service/tests/test_smu_project_scan_api.py`
- Modify: `api-service/app/api/channel_asset.py`

**Step 1: Write RED API tests**

Prove:

- preview is read-only and reports item status/reason/frequencies/hash;
- sync ignores client frequency (no such request field), performs a fresh scan, and returns counts;
- missing config/mount/limit failures return a client-actionable error without DB writes;
- `/vendor-files/smu-scan` and `/vendor-files/smu-sync` are reachable and are not captured by `/{asset_id}`;
- response never contains SMB credentials or an arbitrary local file body.

**Step 2: Verify RED**

Run the API tests; expected 404 or route/import failures.

**Step 3: Implement schemas and endpoints**

Register both static POST routes before the UUID route. Map configuration/business failures to 409 or 422 with
the original detail. Keep preview and sync response shapes explicit Pydantic models.

**Step 4: Verify GREEN and route gates**

Run the API tests plus G2/G19 route gates.

**Step 5: Commit**

```bash
git add api-service/app/api/channel_asset.py api-service/tests/test_smu_project_scan_api.py
git commit -m "feat: expose smu project preview and sync"
```

### Task 4: Add the Channel Workbench one-click flow

**Files:**
- Create: `gui/test/smuProjectScanWiring.test.ts`
- Modify: `gui/src/api/channelAssetService.ts`
- Create: `gui/src/features/ChannelWorkbench/SMUProjectScanModal.tsx`
- Modify: `gui/src/features/ChannelWorkbench/ChannelWorkbench.tsx`

**Step 1: Write the RED GUI contract test**

Assert that the workbench exposes a scan button, preview calls only the read endpoint, rows show internal group 0
truth plus status/reason, and the sync action requires explicit confirmation and invalidates both channel-assets
and channel-model query keys. Assert no filename frequency parser/token exists in the new flow.

**Step 2: Verify RED**

```bash
node --experimental-strip-types --test gui/test/smuProjectScanWiring.test.ts
```

Expected: missing service/modal/button assertions fail.

**Step 3: Implement the minimal modal**

Use server response types verbatim. Display configuration errors and item reasons. Disable sync when no item is
`syncable`; after success re-fetch preview and invalidate dependent query caches.

**Step 4: Verify GREEN and build**

Run the new test and existing Channel Workbench/API contract tests, then `npm run build --prefix gui`.

**Step 5: Commit**

```bash
git add gui/src/api/channelAssetService.ts gui/src/features/ChannelWorkbench/ChannelWorkbench.tsx gui/src/features/ChannelWorkbench/SMUProjectScanModal.tsx gui/test/smuProjectScanWiring.test.ts
git commit -m "feat: add one-click smu truth scan to the workbench"
```

### Task 5: Synchronize OpenAPI and close the mirror set

**Files:**
- Modify: `api-service/tests/test_p2_27_openapi_contract_alignment.py`
- Modify: `api/openapi.yaml`
- Modify: `gui/src/types/api.generated.ts`

**Step 1: Write RED contract assertions**

Assert live and checked-in OpenAPI both expose the two POST paths and identical response schemas/status values.
Include nullable fields and bounded integer shapes.

**Step 2: Verify RED**

Run the OpenAPI contract test; live may pass after Task 3, checked-in YAML must fail until synchronized.

**Step 3: Update YAML and regenerate types**

Update only the two new endpoint families and referenced schemas, then run:

```bash
npm run openapi:generate --prefix gui
```

**Step 4: Verify GREEN**

Run the OpenAPI pytest plus `gui/test/apiContractAlignment.test.ts`.

**Step 5: Commit**

```bash
git add api/openapi.yaml gui/src/types/api.generated.ts api-service/tests/test_p2_27_openapi_contract_alignment.py
git commit -m "docs: publish the smu scan contract"
```

### Task 6: Regression, fresh review, roadmap, and external closure

**Files:**
- Modify: `docs/plans/2026-08-22-p2-31-smb-smu-truth-scan-design.md`
- Modify: `docs/roadmap-first-call.md`

**Step 1: Run focused and complete verification**

Run scanner/API/ChannelAsset/F64 frequency tests, complete rule gates, GUI contracts/build, full backend,
`compileall`, Alembic single-head check, and `git diff --check origin/main...HEAD`. Record exact commands and
counts in the design.

**Step 2: Fresh internal review**

Enumerate every path/frequency producer and consumer. Verify no filename truth, partial scan, client-provided
frequency, guessed ARFCN, legacy SCD double-write, SMB write, or partial database commit remains. Fix P1 with TDD
and repeat until P1=0.

**Step 3: Update roadmap and commit evidence**

Mark P2-31 Ready only after all verification and fresh review. Keep P2-40 cleanup frozen.

**Step 4: Ready PR and Codex review**

Open a Ready PR. Handle in-scope R1 findings and request R2. Merge only after a Codex review covers the latest
HEAD with no P1; if R2 or later has P1, fix and continue P1-only reviews. R2+ P2/P3 are reported but do not block
or auto-enter backlog.

**Step 5: Continue queue**

After merge, verify `origin/main`, delete the P2-31 automation, and continue P3-22 from a fresh worktree unless
the user asks to pause. P2-40 actual cleanup remains frozen.
