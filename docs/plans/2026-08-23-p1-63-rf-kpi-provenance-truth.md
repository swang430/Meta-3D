# P1-63 RF KPI Formal Provenance Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 禁止合成 RSRP/SINR 与默认 RI 进入正式 MIMO OTA 判决；只有逐指标、逐方位、explicit-real 的有限仪器读数可以形成正式 RF KPI。

**Architecture:** 在 MIMO OTA 服务域新增一个小型共享 RF KPI trust 解析器，MEASURE 是唯一写方，ANALYSIS、报告、历史和报告读取门复用同一精确白名单。缺失、模拟、部分覆盖、旧版或畸形快照都 fail-closed 为 UNKNOWN/N/A；诊断执行仍可完成。

**Tech Stack:** Python 3.11、FastAPI、SQLAlchemy JSONB、pytest、React/TypeScript、Vitest、现有 MIMO OTA phase/result 与报告 trust envelope。

---

### Task 1: 锁定逐指标样本与完整性契约

**Files:**
- Create: `api-service/tests/test_p1_63_rf_kpi_provenance_truth.py`
- Create: `api-service/app/services/mimo_ota/rf_kpi_trust.py`
- Modify: `api-service/app/services/mimo_ota/executors/measure.py`

**Step 1: Write the failing test**

新增定点用例覆盖：

- 三个真实驱动但 `kpi_valid` 全 false 时，不得出现随机 RSRP/SINR 或默认 RI；
- 单指标有效、部分方位有效均不得形成完整正式状态；
- 三指标在全部请求方位都显式有效且有限时才 `formal_rf_kpi_verified=true`；
- `NaN`/`Inf` 即使 validity 为 true 也拒绝；
- mock 路径永远不能形成 explicit-real 状态。

**Step 2: Run test to verify it fails**

Run: `api-service/.venv/bin/pytest api-service/tests/test_p1_63_rf_kpi_provenance_truth.py -q`

Expected: FAIL，现实现会写随机 RSRP/SINR、默认 RI，且没有 `rf_kpi_trust`。

**Step 3: Write minimal implementation**

- 删除 MEASURE 中从目标配置、路径损耗、探头增益和 `random.gauss()` 合成正式 RF KPI 的逻辑；
- 仅当 `metrics.is_valid(key)`、数值有限且执行链非 simulated 时收样本；
- 每个方位写三个 `*_valid` 与 sample count；
- 写入版本化 `rf_kpi_trust` 和 `formal_rf_kpi_verified`；
- 在 `rf_kpi_trust.py` 提供规范化解析和 `rf_kpi_scope_is_verified()`，拒绝未知键/非法组合。

**Step 4: Run test to verify it passes**

Run: `api-service/.venv/bin/pytest api-service/tests/test_p1_63_rf_kpi_provenance_truth.py -q`

Expected: PASS。

**Step 5: Commit**

```bash
git add api-service/app/services/mimo_ota/rf_kpi_trust.py api-service/app/services/mimo_ota/executors/measure.py api-service/tests/test_p1_63_rf_kpi_provenance_truth.py
git commit -m "fix: 阻止合成 RF KPI 进入正式测量"
```

### Task 2: ANALYSIS 与执行历史复用同一 RF KPI 白名单

**Files:**
- Modify: `api-service/tests/test_p1_63_rf_kpi_provenance_truth.py`
- Modify: `api-service/app/services/mimo_ota/executors/analysis.py`
- Modify: `api-service/app/api/test_execution.py`

**Step 1: Write the failing test**

新增用例证明：缺失快照、旧布尔字段、部分指标、部分方位、simulated/unknown 和畸形组合均不能让
ANALYSIS 或执行历史发布 PASS/FAIL；完整 explicit-real 快照仍保留既有阈值行为。

**Step 2: Run test to verify it fails**

Run: `api-service/.venv/bin/pytest api-service/tests/test_p1_63_rf_kpi_provenance_truth.py -q`

Expected: FAIL，现 ANALYSIS 直接求均值，历史只检查路损与吞吐。

**Step 3: Write minimal implementation**

- ANALYSIS 在任何 RF KPI 数值运算前调用共享谓词；不通过时写 UNKNOWN/null/warning；
- 执行历史 `_formal_validation_pass()` 增加同一共享谓词；
- 不修改非 MIMO 历史行为。

**Step 4: Run test to verify it passes**

Run: `api-service/.venv/bin/pytest api-service/tests/test_p1_63_rf_kpi_provenance_truth.py -q`

Expected: PASS。

**Step 5: Commit**

```bash
git add api-service/app/services/mimo_ota/executors/analysis.py api-service/app/api/test_execution.py api-service/tests/test_p1_63_rf_kpi_provenance_truth.py
git commit -m "fix: 统一 RF KPI 正式判决白名单"
```

### Task 3: 报告生成、详情/下载与历史重建必须要求 RF KPI 信任快照

**Files:**
- Modify: `api-service/tests/test_p1_63_rf_kpi_provenance_truth.py`
- Modify: `api-service/tests/test_mimo_ota_report_verified_backcompat.py`
- Modify: `api-service/app/services/mimo_ota/executors/report.py`
- Modify: `api-service/app/services/report_service.py`

**Step 1: Write the failing test**

新增用例覆盖：

- 报告在 RF KPI 不完整时隐藏 RSRP/SINR/RI，overall/pass rate 为 UNKNOWN/N/A；
- 只有完整 explicit-real 快照才发布数值与正式 verdict；
- 旧报告即使带校准、路损和吞吐 markers，也不能绕过 RF KPI 门；
- 客户端不能在通用报告创建入口伪造 RF KPI trust 字段；
- 畸形快照进入安全重建或拒绝详情/下载。

**Step 2: Run test to verify it fails**

Run: `api-service/.venv/bin/pytest api-service/tests/test_p1_63_rf_kpi_provenance_truth.py api-service/tests/test_mimo_ota_report_verified_backcompat.py -q`

Expected: FAIL，现 trust envelope 不包含 RF KPI。

**Step 3: Write minimal implementation**

- 报告 builder 写服务端拥有的 RF KPI schema marker、快照与 formal boolean；
- 未验证时屏蔽三个正式指标并把结果降级 UNKNOWN；
- `report_has_provenance_trust()` 要求规范快照与 formal boolean 自洽；
- `_SERVER_OWNED_REPORT_TRUST_FIELDS` 剥离客户端声明；
- 不改变 VRT 报告信任规则。

**Step 4: Run test to verify it passes**

Run: `api-service/.venv/bin/pytest api-service/tests/test_p1_63_rf_kpi_provenance_truth.py api-service/tests/test_mimo_ota_report_verified_backcompat.py -q`

Expected: PASS。

**Step 5: Commit**

```bash
git add api-service/app/services/mimo_ota/executors/report.py api-service/app/services/report_service.py api-service/tests/test_p1_63_rf_kpi_provenance_truth.py api-service/tests/test_mimo_ota_report_verified_backcompat.py
git commit -m "fix: 收紧报告 RF KPI 信任包络"
```

### Task 4: GUI 明确显示 RF KPI 未验证

**Files:**
- Create: `gui/test/rfKpiProvenanceTruth.test.ts`
- Modify: `gui/src/components/Commissioning/Phases.tsx`
- Modify: `gui/src/types/commissioning.ts`（若实际类型位于其它文件，以 grep 的唯一写方为准）

**Step 1: Write the failing test**

契约测试证明：后端值为 null 或 `formal_rf_kpi_verified!==true` 时，逐方位表显示 N/A 和未验证提示；
完整可信时显示数字。GUI 不从数值存在性自行恢复绿色状态。

**Step 2: Run test to verify it fails**

Run: `npm test -- --run gui/test/rfKpiProvenanceTruth.test.ts`

Workdir: `gui`

Expected: FAIL，现表格直接插值字段。

**Step 3: Write minimal implementation**

消费后端明确裁决，只做显示分支；不在前端复制后端白名单。

**Step 4: Run test to verify it passes**

Run: `npm test -- --run gui/test/rfKpiProvenanceTruth.test.ts`

Workdir: `gui`

Expected: PASS。

**Step 5: Commit**

```bash
git add gui/src/components/Commissioning/Phases.tsx gui/src/types gui/test/rfKpiProvenanceTruth.test.ts
git commit -m "fix: 标示未验证 RF KPI 为 N/A"
```

### Task 5: 相关回归、全量回归与 roadmap 收口

**Files:**
- Modify: `docs/roadmap-first-call.md`
- Modify: `docs/plans/2026-08-23-p1-63-rf-kpi-provenance-truth-design.md`（只补验证事实，不改设计）

**Step 1: Run focused and rule-gate tests**

Run:

```bash
api-service/.venv/bin/pytest \
  api-service/tests/test_p1_63_rf_kpi_provenance_truth.py \
  api-service/tests/test_p1_54_kpi_valid_contract.py \
  api-service/tests/test_uxm_kpi_readback.py \
  api-service/tests/test_mimo_ota_report_verified_backcompat.py \
  api-service/tests/test_p1_61_report_final_state_truth.py \
  api-service/tests/test_rule_gates.py -q
```

Expected: PASS。

**Step 2: Run GUI contracts and production build**

Run: `npm test -- --run`

Run: `npm run build`

Workdir: `gui`

Expected: PASS。

**Step 3: Run full backend and static verification**

Run:

```bash
api-service/.venv/bin/pytest api-service/tests -q
api-service/.venv/bin/python -m compileall -q api-service/app
api-service/.venv/bin/alembic heads
git diff --check origin/main...HEAD
```

Expected: 全部通过且只有一个 Alembic head。

**Step 4: Update roadmap evidence and commit**

只写当前 HEAD 的真实统计，P1-64 仍保持下一顺位占位。

```bash
git add docs/roadmap-first-call.md docs/plans/2026-08-23-p1-63-rf-kpi-provenance-truth-design.md
git commit -m "docs: 记录 P1-63 验证证据"
```

### Task 6: Fresh 内审、Ready PR 与 Codex 外审

**Step 1: Fresh independent review**

按 `AGENTS.md` 0.5 列出的全集重新审查，独立 reviewer 只读最终 diff 与现行代码，输出 P1/P2/P3。
任何 P1 先按 TDD 修复并重新回归。

**Step 2: Push and open Ready PR**

PR 描述必须含可观察故障、设计链接、RED/GREEN 与精确验证统计。

**Step 3: External review loop**

- R1：核实并处理本片内可执行意见，触发 R2；
- R2 无 P1：立即 merge commit；
- R2 或后续有 P1：按 TDD 修复并继续 P1-only 复审，直到覆盖最新 HEAD 无 P1；
- R2+ 的 P2/P3 只报告，不阻塞、不自动积压。

**Step 4: Merge and handoff**

验证 `origin/main` 包含 merge commit；主工作目录 ff-only 到最新 main，保留全部未跟踪仪器资料；
清理 P1-63 自动化/worktree/本地分支，然后从最新 main 独立启动 roadmap 已占位的 P1-64。
