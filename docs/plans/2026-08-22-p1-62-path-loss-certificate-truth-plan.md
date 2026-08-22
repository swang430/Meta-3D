# P1-62 Path-Loss Application Truth Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 让 MEASURE、warning、正式报告与 GUI 同时如实表达路损补偿是否应用及证书是否可信，杜绝“已应用但来源未知”被写成“无证书/未补偿”，且不放宽任何正式 KPI 或判决门。

**Architecture:** 在路损选择层返回版本化的选择原因，在 MEASURE 的实际应用点生成唯一 `path_loss_application` 快照。后端 warning、报告与 GUI 只消费该快照；ANALYSIS、历史 verdict 和 `formal_path_loss_verified` 继续使用现有 explicit-real 白名单。旧执行缺少新快照时保守显示“应用状态未知”，不从证书 ID 或数值反推。

**Tech Stack:** Python 3.12、FastAPI、SQLAlchemy、Pydantic、pytest、React 18、TypeScript、Mantine、Node test runner。

---

### Task 1: 用 RED 锁定选择原因与应用状态契约

**Files:**
- Create: `api-service/tests/test_p1_62_path_loss_application_truth.py`
- Create: `api-service/app/services/mimo_ota/path_loss_application.py`
- Modify: `api-service/app/services/path_loss_calibration_service.py`
- Reference: `api-service/app/services/mimo_ota/executors/precheck.py`
- Reference: `api-service/app/services/mimo_ota/executors/measure.py`

**Step 1: Write the failing selection tests**

在新测试中用 SQLite fixture 分别种入：

- 当前有效且 mode/frequency 匹配的 explicit-real 证书；
- 匹配但 `use_mock=None` 的 legacy 证书；
- 过期证书；
- 频率窗口外的有效证书；
- 只有其他 operating mode 的有效证书；
- 完全无证书。

断言新的只读解析器返回证书及精确 reason：

```python
selection = service.resolve_latest_calibration(
    chamber.id,
    frequency_mhz=3500.0,
    operating_mode="mimo_ota",
    require_real=False,
)
assert selection.reason == "expired"
assert selection.certificate is None
```

再参数化 `PathLossApplicationTruth` 构造器，锁定三轴合法组合：

```python
truth = build_path_loss_application(
    selected_certificate=legacy_cert,
    applied_certificate=legacy_cert,
    selection_reason="selected",
    gate_mode="mock_not_applicable",
)
assert truth == {
    "schema_version": 1,
    "status": "applied",
    "provenance": "unknown",
    "reason": "selected",
    "gate_mode": "mock_not_applicable",
    "certificate_id": str(legacy_cert.id),
    "value_disclosure": "hidden_unverified",
}
```

覆盖 `applied/real`、`applied/simulated`、`not_applied/rejected_untrusted`、
missing/expired/frequency/mode mismatch，以及 malformed/缺失历史对象降级
`unknown/legacy_unclassified`。

**Step 2: Run tests to verify RED**

Run:

```bash
cd api-service && .venv/bin/pytest -q tests/test_p1_62_path_loss_application_truth.py
```

Expected: FAIL because `resolve_latest_calibration` and `path_loss_application` do not exist.

**Step 3: Implement the minimal selection result**

在 `path_loss_calibration_service.py` 增加冻结 dataclass：

```python
@dataclass(frozen=True)
class PathLossCalibrationSelection:
    certificate: Optional[ProbePathLossCalibration]
    reason: Literal[
        "selected", "missing", "expired",
        "frequency_mismatch", "operating_mode_mismatch",
    ]
```

实现 `resolve_latest_calibration()`：

1. 先用现有 active/valid/frequency/mode/require_real 规则选证书；
2. 未选中时只读同一 chamber 的候选全集；
3. 按 `expired -> frequency_mismatch -> operating_mode_mismatch -> missing` 的互斥证据分类；
4. 任何查询异常或无法唯一分类时返回 `missing` 之外的保守内部 unknown，并由应用构造器降级
   `legacy_unclassified`，不得猜最近一张；
5. `get_latest_calibration()` 保持兼容包装，只返回 `.certificate`。

**Step 4: Implement the immutable application truth helper**

在 `path_loss_application.py` 定义 token 常量、`build_path_loss_application()`、
`parse_path_loss_application()` 与 `path_loss_application_message()`。parser 对未知 token、错误类型和
非法组合统一返回：

```python
{
    "schema_version": 1,
    "status": "unknown",
    "provenance": "unknown",
    "reason": "legacy_unclassified",
    "gate_mode": "strict",
    "certificate_id": None,
    "value_disclosure": "none",
}
```

不要从 `path_loss_compensation_db`、旧 certificate ID 或自由文本恢复状态。

**Step 5: Run GREEN and commit**

Run the focused test and `tests/test_path_loss_mode_filter.py`.

Expected: PASS.

Commit:

```bash
git add api-service/app/services/mimo_ota/path_loss_application.py \
  api-service/app/services/path_loss_calibration_service.py \
  api-service/tests/test_p1_62_path_loss_application_truth.py
git commit -m "feat: model path-loss application truth"
```

### Task 2: 让 PRECHECK 与 MEASURE 写入同一真值

**Files:**
- Modify: `api-service/app/services/mimo_ota/executors/precheck.py`
- Modify: `api-service/app/services/mimo_ota/executors/measure.py`
- Modify: `api-service/tests/test_p1_62_path_loss_application_truth.py`
- Test: `api-service/tests/test_mimo_ota_precheck_cal_gate.py`
- Test: `api-service/tests/test_path_loss_mode_filter.py`

**Step 1: Add RED tests for the manual-test failure**

构造 mock channel emulator + `use_mock=None`、平均路损 `56.77`、完整逐链记录的 legacy 证书，执行
MEASURE，断言：

```python
application = result.measurements["path_loss_application"]
assert application["status"] == "applied"
assert application["provenance"] == "unknown"
assert application["certificate_id"] == str(cert.id)
assert "已应用路损补偿" in result.warnings[0]
assert "无 path-loss certificate" not in result.warnings[0]
assert "未补偿" not in result.warnings[0]
assert "56.77" not in result.warnings[0]
```

同时保留：`path_loss_verified is False`、`measurement_verified is False`，后续 ANALYSIS 为 UNKNOWN。

增加真实 strict 与真实 bypass RED：

- strict unknown/mock 候选在任何 HAL connect/query/write 前失败；
- bypass 继续执行但 `status=not_applied`、`reason=rejected_untrusted`、补偿不进入逐方位计算；
- explicit-real 仍为 `applied/real/value_disclosure=verified`。

**Step 2: Run RED**

Run:

```bash
cd api-service && .venv/bin/pytest -q \
  tests/test_p1_62_path_loss_application_truth.py \
  tests/test_mimo_ota_precheck_cal_gate.py
```

Expected: the legacy rehearsal still emits “no certificate / uncompensated” and has no structured truth.

**Step 3: Wire PRECHECK to the selection result**

- 用 `resolve_latest_calibration()` 替代本地重复查询；
- 写入 `path_loss_calibration_reason` 的完整 token；
- strict error 与 bypass audit 继续使用 existing `use_mock is False` allowlist；
- 不将 expired/mismatch 候选作为实际证书返回。

**Step 4: Wire MEASURE at the actual application point**

- `selected_path_loss_cert` 表示选择/诊断候选；
- `path_loss_cert` 仍是唯一实际应用证书；
- 只有 `path_loss_cert` 进入 `_query_calibration_entries()`、平均/逐链补偿和逐方位计算；
- 在 `result_payload` 中由共享构造器写 `path_loss_application`；
- warning 改用共享 message helper；
- 保留既有兼容字段，但不再让 warning 从 `path_loss_verified` 推断“是否应用”。

**Step 5: Run GREEN and regression**

Run:

```bash
cd api-service && .venv/bin/pytest -q \
  tests/test_p1_62_path_loss_application_truth.py \
  tests/test_mimo_ota_precheck_cal_gate.py \
  tests/test_path_loss_mode_filter.py \
  tests/test_commissioning_smoke.py
```

Expected: PASS; explicit-real/missing/bypass behavior unchanged except corrected structured reason and wording.

**Step 6: Commit**

```bash
git add api-service/app/services/mimo_ota/executors/precheck.py \
  api-service/app/services/mimo_ota/executors/measure.py \
  api-service/tests/test_p1_62_path_loss_application_truth.py \
  api-service/tests/test_mimo_ota_precheck_cal_gate.py
git commit -m "fix: preserve applied path-loss truth"
```

### Task 3: 收口 ANALYSIS、报告与历史重建消费全集

**Files:**
- Modify: `api-service/app/services/mimo_ota/executors/report.py`
- Modify if needed: `api-service/app/services/report_service.py`
- Modify: `api-service/tests/test_p1_62_path_loss_application_truth.py`
- Modify: `api-service/tests/test_mimo_ota_report_verified_backcompat.py`
- Test: `api-service/tests/test_arch1_history_resource.py`
- Test: `api-service/tests/test_p1_22_report_trustworthy.py`
- Test: `api-service/tests/test_p2_21_report_flags_cert_cjk.py`

**Step 1: Add report RED tests**

用 `_build_mimo_ota_content_data()` 参数化以下状态：

- applied + real：报告显示补偿值与“路损校准证书”；
- applied + unknown：显示“已应用但来源未知”，证书 ID 可见，补偿数值及 `56.77` 不出现在
  parameters/warnings/PDF input；
- applied + simulated：显示流程演练，隐藏数值；
- not_applied + rejected：显示证书存在但未应用；
- missing/expired/frequency/mode mismatch：显示精确原因与未补偿；
- absent/malformed object：显示历史应用状态未知，隐藏数值且不崩溃。

所有 unverified 行继续断言：

```python
assert content["formal_path_loss_verified"] is False
assert content["overall_result"] != "passed"
```

**Step 2: Run RED**

Run:

```bash
cd api-service && .venv/bin/pytest -q \
  tests/test_p1_62_path_loss_application_truth.py \
  tests/test_mimo_ota_report_verified_backcompat.py
```

Expected: current report collapses every unverified state to “无路损校准，未补偿”.

**Step 3: Make report presentation consume only the snapshot**

- parse `measure["path_loss_application"]` once;
- derive compensation display and validation label from parsed status/provenance/disclosure;
- retain the raw audit value in the execution measurements, but do not copy it into formal content when disclosure is
  hidden/none;
- add the structured application snapshot to `content_data` for audit;
- keep `formal_path_loss_verified` exactly `_pl_verified is True`;
- historical missing/malformed snapshot uses `unknown/legacy_unclassified` and never queries current calibration rows.

**Step 4: Prove verdict gates are unchanged**

Run:

```bash
cd api-service && .venv/bin/pytest -q \
  tests/test_arch1_history_resource.py \
  tests/test_p1_22_report_trustworthy.py \
  tests/test_p2_21_report_flags_cert_cjk.py \
  tests/test_mimo_ota_report_verified_backcompat.py
```

Expected: PASS; old reports remain UNKNOWN/unavailable until safe rebuild, explicit-real reports retain PASS/FAIL eligibility.

**Step 5: Commit**

```bash
git add api-service/app/services/mimo_ota/executors/report.py \
  api-service/app/services/report_service.py \
  api-service/tests/test_p1_62_path_loss_application_truth.py \
  api-service/tests/test_mimo_ota_report_verified_backcompat.py
git commit -m "fix: render path-loss application truth"
```

### Task 4: 让 GUI 精确显示应用状态并隐藏未验证数值

**Files:**
- Create: `gui/src/components/Commissioning/pathLossApplication.ts`
- Create: `gui/test/pathLossApplicationTruth.test.ts`
- Modify: `gui/src/components/Commissioning/Phases.tsx`
- Modify if live schema exists: `api/openapi.yaml`
- Regenerate if schema changed: `gui/src/types/api.generated.ts`

**Step 1: Write the failing GUI contract tests**

断言 helper 的类型与文案矩阵，并检查 `Phases.tsx` 不再使用
`data.path_loss_verified !== true` 推出“无证书/未补偿”：

```typescript
assert.match(helper, /applied.*unknown.*已应用路损补偿/s)
assert.match(helper, /补偿数值不展示/)
assert.doesNotMatch(measurePhase, /path_loss_verified\s*!==\s*true[\s\S]*无 path-loss certificate/)
```

PRECHECK 表格必须按 `path_loss_calibration_reason` 区分 missing、expired、frequency mismatch、mode
mismatch，而不是 `valid ? 有效 : 已过期`。

**Step 2: Run RED**

Run:

```bash
node --test --experimental-strip-types gui/test/pathLossApplicationTruth.test.ts
```

Expected: FAIL because helper and precise labels do not exist.

**Step 3: Implement the minimal TS parser/view model**

导出 `PathLossApplication`、`parsePathLossApplication()` 与 `describePathLossApplication()`：

- 缺失/非法对象返回 legacy unknown；
- `showCompensationValue` 只在 `status=applied && provenance=real && value_disclosure=verified` 为真；
- unknown/simulated applied 文案如实说明已应用但不可信；
- not-applied 文案按 reason 精确区分。

`MIMOTestPhase` 使用 view model 显示 Alert 和 certificate ID；补偿值只有
`showCompensationValue=true` 才渲染。PRECHECK 使用 reason map，不从单一 boolean 猜“已过期”。

**Step 4: Sync real API mirrors only if applicable**

若 MIMO phase payload 在 live OpenAPI 中已有结构化 response schema，则同步 live schema、
`api/openapi.yaml` 与 generated TS，并加方向性契约门；若当前端点明确仍是开放 JSON result，则不为本片
扩建新 API family，在设计证据中记录“不适用”。

**Step 5: Run GREEN and build**

Run:

```bash
node --test --experimental-strip-types gui/test/pathLossApplicationTruth.test.ts
cd gui && npm run build
```

Expected: PASS and production build succeeds.

**Step 6: Commit**

```bash
git add gui/src/components/Commissioning/pathLossApplication.ts \
  gui/src/components/Commissioning/Phases.tsx \
  gui/test/pathLossApplicationTruth.test.ts api/openapi.yaml \
  gui/src/types/api.generated.ts
git commit -m "fix: show path-loss application truth in GUI"
```

Only stage OpenAPI files when they actually changed.

### Task 5: 完整回归、roadmap 证据与 fresh 内审

**Files:**
- Modify: `docs/roadmap-first-call.md`
- Modify if required: `docs/plans/2026-08-22-p1-62-path-loss-certificate-truth-design.md`

**Step 1: Run focused backend suites**

Run:

```bash
cd api-service && .venv/bin/pytest -q \
  tests/test_p1_62_path_loss_application_truth.py \
  tests/test_mimo_ota_precheck_cal_gate.py \
  tests/test_path_loss_mode_filter.py \
  tests/test_commissioning_smoke.py \
  tests/test_mimo_ota_report_verified_backcompat.py \
  tests/test_arch1_history_resource.py \
  tests/test_p1_22_report_trustworthy.py \
  tests/test_p2_21_report_flags_cert_cjk.py
```

Expected: PASS.

**Step 2: Run rule gates and full backend**

Run:

```bash
cd api-service && .venv/bin/pytest -q tests/test_rule_gates.py
cd api-service && .venv/bin/pytest -q
cd api-service && .venv/bin/python -m compileall -q app tests
```

Expected: all tests pass with only repository-known skips; compileall exits 0.

**Step 3: Run GUI verification**

Run:

```bash
node --test --experimental-strip-types gui/test/pathLossApplicationTruth.test.ts
cd gui && npm run build
```

Expected: PASS.

**Step 4: Check repository invariants**

Run the repository's Alembic head command and require exactly one head. Then run:

```bash
git diff --check origin/main...HEAD
git status --short
```

Expected: zero diff-check errors; only intended tracked changes plus local dependency symlinks if present.

**Step 5: Fresh internal review**

Re-enumerate all P1-62 producers and consumers:

- selector, PRECHECK, strict/bypass, actual MEASURE application;
- average/per-chain/per-azimuth compensation;
- warning, ANALYSIS, report builder, regeneration, history;
- PRECHECK/MIMO GUI and any typed API mirror;
- missing, expired, frequency mismatch, mode mismatch, explicit-real, mock, unknown and malformed history.

P1 must be zero. Test-only findings are at most P2/P3 under AGENTS.md rule 0.

**Step 6: Update roadmap and commit evidence**

Record exact commands and final counts; mark P1-62 implementation complete but not merged.

```bash
git add docs/roadmap-first-call.md docs/plans/2026-08-22-p1-62-path-loss-certificate-truth-design.md
git commit -m "docs: record P1-62 verification"
```

### Task 6: Ready PR、Codex 外审与合并

**Files:**
- No product files unless review finds a verified in-scope defect.

**Step 1: Push and open a Ready PR**

Use a summary that names the observable failure, the three-axis state contract, unchanged formal gates, and exact
verification commands/counts.

**Step 2: Request Codex R1**

EYES/empty review is only acknowledgement. For each executable in-scope R1 finding:

1. verify it against current HEAD;
2. write a RED regression;
3. implement the smallest fix;
4. rerun focused/full relevant checks;
5. fresh internal review;
6. push, reply inline, and request R2.

**Step 3: Close only on a review covering latest HEAD with no P1**

- R2 no P1 + mergeable/checks green or no required checks: merge commit immediately;
- R2 with P1: TDD fix and request R3; continue P1-only review until latest HEAD has no P1;
- R2+ P2/P3: report once, do not block and do not auto-backlog.

**Step 4: Verify and clean up**

Fetch and verify `origin/main` contains the merge commit. Fast-forward local main while preserving all untracked
instrument materials. Delete the P1-62 automation, remove this worktree/local branch, then pause and report the final
P1-62 summary; do not start another feature.
