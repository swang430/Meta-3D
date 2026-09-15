# CMW500 + F64 Onsite Diagnostics Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 CMW500 + F64 单步现场诊断保留可审计原始证据、拒绝隐式人工结论，并移除三个已失效的旧脚本。

**Architecture:** 延续现有 Sequence Runner 与 `diagnostic_runs` 单一载体，在浅参数 schema 上增加可选枚举，不创建新的执行通道。F64 health 仅扩充既有运行结果证据，handback 将 GUI 输入改为显式三态并保留旧 API 参数兼容。

**Tech Stack:** Python 3.13、FastAPI/Pydantic、React 19、TypeScript、Mantine、pytest、Node test runner。

**Spec:** `docs/plans/2026-09-15-cmw500-f64-onsite-diagnostics-hardening-design.md`

## Global Constraints

- 不新增、猜测或修改任何 SCPI 字面量与厂商语义。
- 不改变正式 provenance 白名单、qualification、site certification 或 KPI 判据。
- 模拟、未知和人工观察证据不得进入正式 KPI。
- `api-service/.venv` 与 `gui/node_modules` 是本地依赖链接，不得提交。
- 既有历史现场记录保持原样；只更新当前运行说明和当前代码镜像。

---

### Task 1: 参数枚举与 Local handback 显式状态

**Files:**
- Modify: `api-service/app/api/diagnostic_sequence.py`
- Modify: `api-service/app/diagnostics/protocol.py`
- Modify: `api-service/app/diagnostics/sequences/cmw500_fdd_matrix_probe.py`
- Modify: `api-service/app/diagnostics/sequences/propsim_f64_local_handback_check.py`
- Modify: `api-service/tests/test_diagnostic_sequences.py`
- Modify: `api-service/tests/test_p1_65_propsim_f64_local_handback_check.py`
- Modify: `api-service/tests/test_p2_70_cmw_fdd_matrix_probe.py`
- Modify: `gui/src/api/diagnosticService.ts`
- Create: `gui/src/features/Diagnostics/diagnosticSequenceParams.ts`
- Create: `gui/test/diagnosticSequenceParams.test.ts`
- Modify: `gui/src/features/Diagnostics/SequenceRunnerPanel.tsx`

**Interfaces:**
- Consumes: `SequenceMetadata.params_schema: list[dict]` and `RunSequenceRequest.params`.
- Produces: optional `SequenceParamSpec.choices`, `operator_local_state`, and GUI helpers `initialSequenceParamValues()` / `sequenceParamSelectData()`.

- [ ] **Step 1: Write backend failing tests**

Add assertions that list metadata preserves labeled choices, CMW exposes only `tm1_one` / `tm3_two`, handback exposes `release` / `confirm` and a blank-default `operator_local_state`, missing state is UNDETERMINED, explicit `local`/`remote` map to SUCCESS/BLOCKER, invalid values abort without SCPI, and the deprecated boolean remains accepted only as an API compatibility input.

- [ ] **Step 2: Run backend RED**

Run: `.venv/bin/python -m pytest -q tests/test_p1_65_propsim_f64_local_handback_check.py tests/test_p2_70_cmw_fdd_matrix_probe.py tests/test_diagnostic_sequences.py -k 'handback or choices or cmw500_fdd_matrix'`

Expected: failures because `choices` is dropped and `operator_local_state` is absent.

- [ ] **Step 3: Implement minimal backend support**

Add a strict choice response model (`value: str`, `label: str`), preserve choices through metadata listing, declare the three enumerated fields, and map the new handback state without issuing SCPI in confirm. Keep sequence-side validation authoritative.

- [ ] **Step 4: Run backend GREEN**

Run the command from Step 2.

Expected: all selected tests pass.

- [ ] **Step 5: Write GUI failing test**

Create literal fixtures proving that choice-backed params initialize to explicit defaults or blank, render labeled Select data, and never synthesize boolean `false` for `operator_local_state`.

- [ ] **Step 6: Run GUI RED**

Run: `node --test test/diagnosticSequenceParams.test.ts`

Expected: module-not-found failure because the helper does not exist.

- [ ] **Step 7: Implement minimal GUI support**

Add optional labeled choices to the handwritten service type, implement the pure helpers, use them in `SequenceRunnerPanel`, and render a Mantine `Select` before the existing number/boolean/string branches.

- [ ] **Step 8: Run GUI GREEN and build**

Run: `node --test test/diagnosticSequenceParams.test.ts test/diagnosticSequenceEvidence.test.ts`

Run: `npm run build`

Expected: Node tests pass and production build exits 0.

- [ ] **Step 9: Commit Task 1**

Commit message: `feat(diagnostics): require explicit onsite sequence choices`

### Task 2: F64 Phase A 原始回复证据

**Files:**
- Modify: `api-service/app/diagnostics/sequences/propsim_f64_health.py`
- Modify: `api-service/tests/test_diagnostic_sequences.py`

**Interfaces:**
- Consumes: existing `ce._query`, `_parse_err`, `_categorize_status`, `SequenceStepResult.raw`.
- Produces: `SequenceRunResult.extra["scpi_observations"]: list[dict]` with query/error-queue raw evidence.

- [ ] **Step 1: Write failing evidence tests**

Use hand-authored replies for `MMEM:CDIR?` and `MMEM:CAT?`. Assert that target raw, error-queue raw, parsed status and critical flag persist even when normal SUPPORTED steps are hidden; assert emitted steps use target raw; assert empty reply remains `""` and query exception remains `null` plus an error string.

- [ ] **Step 2: Run RED**

Run: `.venv/bin/python -m pytest -q tests/test_diagnostic_sequences.py -k 'PropsimF64HealthSequence and raw'`

Expected: failures because `scpi_observations` does not exist and step raw is null.

- [ ] **Step 3: Implement minimal capture**

Capture the return of each existing target query before the existing error-queue read; return the unnormalized error-queue raw alongside its parsed tuple; append one observation for every attempted row; do not change command ordering, support categorization or overall verdict.

- [ ] **Step 4: Run GREEN and health regression**

Run: `.venv/bin/python -m pytest -q tests/test_diagnostic_sequences.py tests/test_p1_66_f64_probe_truth.py -k 'PropsimF64HealthSequence or f64_probe_truth'`

Expected: all selected tests pass.

- [ ] **Step 5: Commit Task 2**

Commit message: `fix(f64): preserve health probe raw replies`

### Task 3: 退役旧脚本并发布现场 runbook

**Files:**
- Delete: `scripts/onsite-fix-f64-scenario-assets.py`
- Delete: `scripts/onsite-run-channel-throughput.sh`
- Delete: `scripts/cleanup-test-queue.py`
- Modify: `scripts/README.md`
- Modify: `api-service/app/api/commissioning.py`
- Modify: `api-service/tests/test_p2_54_mac_profile_schema.py`
- Modify: `api-service/tests/test_p2_72_category_hal_activation.py`
- Modify: `docs/design/arch-1-testcase-first-simplification.md`
- Modify: `docs/roadmap-first-call.md`
- Create: `docs/guides/2026-09-16-cmw500-f64-onsite-runbook.md`

**Interfaces:**
- Consumes: current Sequence Runner, `CreateSessionRequest.channel_asset_id`, CMW FDD matrix probe, F64 controlled API and roadmap blocker definitions.
- Produces: one current operator path and a dated evidence checklist; no new runtime interface.

- [ ] **Step 1: Remove the three superseded scripts**

Delete only the three approved files. Preserve `scripts/onsite-f64-control.py` and every historical site record.

- [ ] **Step 2: Repair current references**

Remove the dead script from the active-entrypoint inventory, replace current comments that describe the PATCH workaround, record queue cleanup retirement in the ARCH-1 closeout row, and document the supported operator entrypoints in `scripts/README.md`.

- [ ] **Step 3: Update current roadmap facts**

Change P2-71 from “health does not retain raw replies” to the new scoped behavior; keep device byte/version/rollback blocked. Update NEW-2 to name the explicit Local/Remote selection without claiming that socket close proves Local.

- [ ] **Step 4: Write the onsite runbook**

Document preflight, exclusive-maintenance warnings, F64 and CMW sequence order, FDD-before-TDD policy, required run/execution IDs, formal blockers (calibration/site certification/DUT attach), and stop conditions. State that persisted connected, Mock runs and diagnostic SUCCESS are not formal hardware qualification.

- [ ] **Step 5: Verify no active dead references remain**

Run: `rg -n 'onsite-fix-f64-scenario-assets|onsite-run-channel-throughput|cleanup-test-queue' api-service gui scripts CLAUDE.md docs/roadmap-first-call.md docs/design/arch-1-testcase-first-simplification.md`

Expected: only an explicit retirement/history explanation remains; no live command tells operators to execute a deleted script.

- [ ] **Step 6: Commit Task 3**

Commit message: `docs(onsite): retire obsolete hardware scripts`

### Task 4: 全验证、内审与 PR

**Files:**
- Verify all files changed since `origin/main`.

**Interfaces:**
- Consumes: Tasks 1–3.
- Produces: verified Ready PR with no untracked dependency links staged.

- [ ] **Step 1: Run affected backend and rule gates**

Run: `.venv/bin/python -m pytest -q tests/test_p1_65_propsim_f64_local_handback_check.py tests/test_p2_70_cmw_fdd_matrix_probe.py tests/test_diagnostic_sequences.py tests/test_p1_66_f64_probe_truth.py tests/test_rule_gates.py tests/test_p2_54_mac_profile_schema.py tests/test_p2_72_category_hal_activation.py`

- [ ] **Step 2: Run full backend**

Run: `.venv/bin/python -m pytest -q`

- [ ] **Step 3: Run affected GUI contracts and full production build**

Run: `node --test test/diagnosticSequenceParams.test.ts test/diagnosticSequenceEvidence.test.ts`

Run: `npm run build`

说明：仓库没有统一 GUI test script；直接把全部 `.test.ts(x)` 交给原生 Node runner
会命中不同历史模块解析约定与过期 fixture，不是可复现的本片门。这里跑本片全部 GUI
消费契约，再用 production build 覆盖全量 TypeScript 与打包。

- [ ] **Step 4: Run static/repository gates**

Run: `.venv/bin/python -m compileall -q app tests`

Run: `.venv/bin/python -m alembic heads`

Run: `git diff --check origin/main...HEAD`

Run: `git status --short`

Expected: compile succeeds, one Alembic head, no whitespace errors, and only the local `api-service/.venv` dependency link remains untracked.

- [ ] **Step 5: Perform fresh functional review**

Re-enumerate every changed field’s producers/consumers and the four failure paths (success, rejection, exception, cancellation). Confirm no new SCPI, no formal-gate expansion, raw evidence survives persistence, choices cannot bypass sequence validation, and deleted scripts have no live callers.

- [ ] **Step 6: Push and open Ready PR**

Push `codex/cmw500-f64-onsite-diagnostics-hardening`, open a Ready PR against `main`, include the observable failures and exact verification outputs, and keep the worktree for review feedback.
