# P1-61 Report Final-State Truth Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 让正式 MIMO PDF、持久化 `content_data` 与最终 `TestExecution` 对同一执行状态、耗时和四态判决给出一致结论，同时保留 REPORT 期间取消与失败语义。

**Architecture:** REPORT 执行器只计算一次最终完成时间和耗时，通过不可变 `ReportLifecycleProjection` 传给内容构造器与 `ReportService`；构造器以“投影优先、数据库状态兜底”的单一有效生命周期生成全部状态字段。PDF 先写不可公开 staging，随后用数据库条件更新裁决 completed 与外部 cancel；取消先赢则在 staging 内以数据库赢家重建，最后只发布赢家版本。历史报告重建不传投影，缺失时间保持未知而不猜值。

**Tech Stack:** Python 3.12、FastAPI、SQLAlchemy、pytest、ReportLab。

---

### Task 1: 用红测锁定最终状态投影与四态契约

**Files:**
- Create: `api-service/tests/test_p1_61_report_final_state_truth.py`
- Reference: `api-service/app/services/mimo_ota/executors/report.py`

**Step 1: Write the failing tests**

- 构造 ORM 状态 `running`、`duration_sec=None`、可信性不足的执行；传入 completed 投影，断言：
  - `test_plan.status == "completed"`；
  - `duration_s == total_duration_sec == 89.195194`；
  - `pending == 0`、`undetermined == 1`、`pass_rate is None`；
  - `last_execution` 使用投影完成时间。
- 构造历史 completed 执行且不传投影，断言相同 UNKNOWN → undetermined 契约。
- 参数化 completed PASS、completed FAIL、pending、running/cancelled/skipped、failed，断言四态互斥和 pass rate。

**Step 2: Run test to verify it fails**

Run: `cd api-service && .venv/bin/pytest -q tests/test_p1_61_report_final_state_truth.py`

Expected: FAIL because the projection API and `undetermined` summary do not exist; the old builder reports running/0 seconds/pending.

**Step 3: Commit the RED evidence**

Commit only after capturing the exact failing assertions in the task evidence; do not weaken expectations.

### Task 2: Implement one effective lifecycle source

**Files:**
- Modify: `api-service/app/services/mimo_ota/executors/report.py`
- Test: `api-service/tests/test_p1_61_report_final_state_truth.py`

**Step 1: Add the minimal immutable projection**

- Add a frozen `ReportLifecycleProjection` containing `status`, `completed_at`, and `duration_sec`.
- Add a helper that returns an explicit projection when present, otherwise derives one from the execution row.
- Do not mutate the ORM object in this helper.

**Step 2: Make all report lifecycle consumers use it**

- Extend `_build_mimo_ota_content_data()` with a keyword-only optional projection.
- Derive `test_plan.status`, `duration_s`, `execution_summary.total_duration_sec`, `first_execution`, and `last_execution` from the effective lifecycle.
- Centralize the four-state summary:
  - completed + trusted PASS/MARGINAL → passed;
  - completed + trusted FAIL → failed;
  - completed + UNKNOWN/untrusted → undetermined;
  - pending → pending;
  - running/cancelled/skipped → incomplete;
  - failed → failed.
- Use `pass_rate=None` for pending, incomplete, and undetermined.

**Step 3: Run focused GREEN**

Run: `cd api-service && .venv/bin/pytest -q tests/test_p1_61_report_final_state_truth.py`

Expected: PASS.

**Step 4: Commit**

`git commit -m "fix: project final lifecycle into MIMO reports"`

### Task 3: Connect ReportExecutor without early lifecycle mutation

**Files:**
- Modify: `api-service/app/services/mimo_ota/executors/report.py`
- Modify: `api-service/tests/test_p1_61_report_final_state_truth.py`
- Reference: `api-service/tests/test_arch1_case_runner.py`

**Step 1: Add the failing integration test**

- Patch report persistence/generation to capture the outgoing `content_data`.
- During `create_report`/`generate_report`, assert the ORM execution is still `running` while captured content is completed with the projected duration.
- After executor return, assert the ORM execution is completed with exactly the same completed time/duration.
- 用独立数据库会话在 PDF 生成期间写入 cancelled，断言条件终态裁决保留 cancelled，且同一报告按 incomplete 重建。

**Step 2: Run test to verify it fails**

Expected: current executor sends running/zero-duration content.

**Step 3: Wire the projection**

- At REPORT entry compute one timezone-normalized `completed_at` and duration.
- Pass the projection to `_build_mimo_ota_content_data()`.
- After report attempt, atomically update only `status == running` to the same completed projection.
- 先生成到不可下载的 staging 路径；pending/generating 行不得公开 completed content/path。
- 在 staging 生成后执行终态 CAS；若外部终态先赢，在 staging 内按赢家重建同一报告。
- 只把赢家 content/PDF/path 一次性发布；do not create a second report。
- Do not move ORM lifecycle mutation ahead of report generation.

**Step 4: Run focused tests**

Run: `cd api-service && .venv/bin/pytest -q tests/test_p1_61_report_final_state_truth.py tests/test_arch1_case_runner.py`

Expected: PASS, including REPORT cancellation rescue.

### Task 4: Update old contract mirrors and report regeneration coverage

**Files:**
- Modify: `api-service/tests/test_mimo_ota_report_verified_backcompat.py`
- Modify: `api-service/tests/test_p1_37_mock_scpi_logging.py`
- Modify: `api-service/tests/test_p1_54_kpi_valid_contract.py`
- Modify: `api-service/tests/test_p1_59_ca_throughput_truth.py` if assertions mirror the old pending contract
- Test: `api-service/tests/test_p1_22_report_trustworthy.py`
- Test: `api-service/tests/test_p1_48_vrt_no_fabrication.py`

**Step 1: Run the relevant report suite**

Run: `cd api-service && .venv/bin/pytest -q tests/test_p1_22_report_trustworthy.py tests/test_mimo_ota_report_verified_backcompat.py tests/test_p1_37_mock_scpi_logging.py tests/test_p1_54_kpi_valid_contract.py tests/test_p1_59_ca_throughput_truth.py tests/test_p1_48_vrt_no_fabrication.py`

Expected: tests tied to UNKNOWN → pending/0% fail.

**Step 2: Update only stale mirrors**

- For completed executions with untrusted evidence, assert `undetermined=1`, `pending=0`, and `pass_rate is None`.
- Keep actual pending lifecycle tests as pending.
- Keep trusted PASS/FAIL expectations unchanged.
- Add/retain historical regeneration assertion proving completed rows need no projection override.

**Step 3: Re-run and commit**

Expected: relevant suite PASS.

### Task 5: Full verification, roadmap evidence, and internal review

**Files:**
- Modify: `docs/roadmap-first-call.md`
- Modify if required: `docs/plans/2026-08-22-p1-61-report-final-state-truth-design.md`

**Step 1: Run product and rule gates**

- Focused report/runner suite.
- `cd api-service && .venv/bin/pytest -q tests/test_rule_gates.py`
- `cd api-service && .venv/bin/pytest -q`
- `cd api-service && .venv/bin/python -m compileall -q app tests`
- Confirm one Alembic head.
- Run `git diff --check origin/main...HEAD` and require a zero exit status.

**Step 2: Fresh internal review**

Re-enumerate all lifecycle producers/consumers, report regeneration, cancellation, PDF failure and four-state branches. P1 must be zero before opening the PR.

**Step 3: Update evidence and commit**

Record exact commands and final counts in roadmap; keep P1-62 queued and out of this diff.

### Task 5A: Close fresh-review lifecycle gaps

**Files:**
- Modify: `api-service/app/services/report_service.py`
- Modify: `api-service/app/services/pdf_generator.py`
- Modify: `api-service/app/api/commissioning.py`
- Modify: `gui/src/types/report.ts`
- Modify: `gui/src/types/roadTest.ts`
- Modify: `gui/src/components/Report/ReportViewer.tsx`

- Add RED coverage for pre-CAS publication, nullable historical timing, adhoc REPORT ownership, and GUI pending mapping.
- Stage PDF and delay content/path publication until lifecycle resolver returns the database winner.
- Preserve missing timing as `None`/`N/A`; never substitute zero or rebuild time.
- Let the adhoc wrapper finalize only rows still in `running`.
- Add `pending` to both GUI type mirrors and the viewer result mapping.

### Task 5B: Close second fresh-review ownership gaps

**Files:**
- Modify: `api-service/app/services/report_service.py`
- Modify: `api-service/app/services/mimo_ota/executors/report.py`
- Modify: `api-service/app/services/test_case_runner.py`
- Modify: `api-service/tests/test_p1_61_report_final_state_truth.py`
- Modify: `api-service/tests/test_p1_47c_execution_scpi_evidence.py`

- Add RED coverage proving public regeneration cannot claim an internal pending report while its
  authoritative execution is active.
- Validate the complete internal projection/resolver/MIMO/PDF/single-execution contract before the
  database writer claim; an arbitrary callable must not bypass the public terminal-state gate.
- Persist cancellation-winner duration on the authoritative `TestExecution` row with a conditional
  update, then rebuild the report from the reread database winner.
- Update the pre-P1-61 internal test mirror to exercise the complete projection plus resolver
  contract rather than the removed projection-only shape.

### Task 5C: Close late-cancel terminal overwrite race

**Files:**
- Modify: `api-service/app/services/test_case_runner.py`
- Modify: `api-service/tests/test_p1_61_report_final_state_truth.py`
- Modify: `api-service/tests/test_arch1_case_runner.py`

- Add a deterministic two-session RED test: cancel reads `running`, REPORT wins the completion CAS,
  then the late cancel resumes and must return `False` without changing the database winner.
- Replace cancellation's stale ORM assignment with `id + executed_by + status=running` conditional
  update; status, completion timestamp and duration are one atomic terminal transition.
- Remove the obsolete `config.cancel_requested` recovery mirror. The REPORT executor and cancel
  endpoint now share the same database CAS, so a second JSON lifecycle source would only risk
  overwriting concurrent phase-progress evidence.

### Task 5D: Unify ordinary runner terminal ownership

**Files:**
- Modify: `api-service/app/services/test_case_runner.py`
- Modify: `api-service/tests/test_arch1_case_runner.py`

- Add a deterministic RED test in which a phase has already failed, the runner has refreshed a
  `running` snapshot, and an independent cancel session wins before the ordinary failure write.
- Route normal completion/failure, missing-snapshot failure, top-level exception failure and cancel
  through one `id + executed_by + expected_status` database transition helper.
- Flush non-lifecycle SCPI evidence before the terminal CAS, then publish terminal config in the CAS
  itself so a pending ORM JSON flush cannot erase `failed_phase` or `error_message`.
- Emit `execution_failed` only when the failed transition wins; a late writer must reread and respect
  the existing terminal owner without publishing a contradictory alert.

### Task 6: Ready PR, Codex review, merge, then P1-62

**Files:**
- PR for branch `codex/p1-61-report-final-state-truth`

**Step 1: Open Ready PR and trigger Codex R1**

Handle in-scope executable findings with TDD, regression, fresh review, replies, and trigger R2.

**Step 2: Apply repository review policy**

- R2 latest HEAD without P1 and mergeable/checks green → merge commit.
- R2 or later with P1 → fix, review, regress and continue P1-only external review until latest HEAD has no P1.
- R2+ P2/P3 are reported once and do not block or auto-enter backlog.

**Step 3: Verify main and start P1-62**

Fetch and verify `origin/main` contains the merge commit; fast-forward local main while preserving untracked instrument materials; remove P1-61 automation/worktree; create a fresh worktree from latest main for P1-62 and execute the same complete workflow.
