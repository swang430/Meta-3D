# P1-64 Quiet-Zone Evidence Truth Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 无真实静区多点测量证据时，诊断流程可以继续，但 PRECHECK、ANALYSIS、报告、历史与 GUI 均不得发布静区 PASS 或 0.7 dB 兜底实测值。

**Architecture:** 用一个共享的版本化静区证据解析器区分 unavailable、diagnostic proxy 与未来 measured 证据；PRECHECK 将运行许可与正式判决拆开，下游只接受规范且 formal 的白名单快照。本片不晋升现有历史校准行，也不实现真实硬件扫描。

**Tech Stack:** FastAPI/Pydantic、SQLAlchemy、pytest、React/TypeScript/Mantine、Vitest、既有 MIMO OTA phase/report lifecycle。

---

### Task 1: 版本化静区证据契约

**Files:**
- Create: `api-service/app/services/mimo_ota/quiet_zone_evidence.py`
- Create: `api-service/tests/test_p1_64_quiet_zone_evidence_truth.py`

**Step 1: Write the failing tests**

覆盖：

- missing → 规范 unavailable snapshot；
- 有限 ProbePattern proxy → diagnostic_proxy，正式 false；
- NaN/Inf/非对象/额外键/非法状态组合 → parser 拒绝；
- 旧 `quiet_zone_verified=true` 不影响正式判据。

**Step 2: Run tests to verify RED**

Run:
`/Users/simon/Tools/MIMO-First/api-service/.venv/bin/python -m pytest -q --color=no tests/test_p1_64_quiet_zone_evidence_truth.py`

Expected: FAIL，因为模块不存在。

**Step 3: Implement the minimal pure contract**

实现 schema version、规范 builder/parser 和
`quiet_zone_evidence_is_formally_verified()`。当前 builder 只产生 unavailable/proxy，
formal 必为 false；不添加 measured 伪入口。

**Step 4: Run tests to verify GREEN**

Expected: 新契约测试 PASS。

**Step 5: Commit**

`git commit -m "feat: 建立静区证据白名单契约"`

### Task 2: PRECHECK 三态与诊断继续权

**Files:**
- Modify: `api-service/app/services/mimo_ota/executors/precheck.py`
- Modify: `api-service/tests/test_p1_64_quiet_zone_evidence_truth.py`
- Modify: `api-service/tests/test_mimo_ota_precheck_dut_gate.py`
- Modify: `api-service/tests/test_mimo_ota_precheck_cal_gate.py`

**Step 1: Write the failing tests**

断言无 pattern 时不再写 0.7；有 pattern 时只写 proxy；两者
`quiet_zone_pass=None`、`overall_pass=None`、步骤 SUCCESS。再用现有门构造仪表离线、
校准失败和 DUT 失败，断言仍 FAILED。

**Step 2: Run tests to verify RED**

Expected: 旧实现分别返回 0.7/代理正式值与 true。

**Step 3: Implement the minimal PRECHECK change**

删除固定 0.7；写入规范 evidence；新增 `quiet_zone_can_continue`；以
`operational_ready` 控制步骤状态，以静区证据决定 `overall_pass` 三态。失败原因不得格式化
null 静区值。

**Step 4: Run focused PRECHECK tests**

Expected: 新测试与现有 DUT/cal gate 测试 PASS。

**Step 5: Commit**

`git commit -m "fix: 分离静区未判定与预检运行门"`

### Task 3: ANALYSIS、报告与历史可信门

**Files:**
- Modify: `api-service/app/services/mimo_ota/executors/analysis.py`
- Modify: `api-service/app/services/mimo_ota/executors/report.py`
- Modify: `api-service/app/services/report_service.py`
- Modify: `api-service/app/api/report.py`
- Modify: `api-service/tests/test_p1_64_quiet_zone_evidence_truth.py`
- Modify: `api-service/tests/test_mimo_ota_report_verified_backcompat.py`
- Modify: `api-service/tests/test_p1_48_report_provenance.py`

**Step 1: Write the failing tests**

覆盖 proxy/unavailable/旧 true/旧 source/畸形 snapshot：

- ANALYSIS 必须 UNKNOWN；
- 报告静区数值 N/A，不能写 PASS；
- 旧 content_data 不通过详情/下载可信门；
- 客户端创建报告时静区 attestation 被剥离。

**Step 2: Run tests to verify RED**

Expected: 旧 Analysis、report fallback 与 ReportService trust gate 放行至少一条。

**Step 3: Implement shared allowlist consumption**

ANALYSIS、builder 与 ReportService 全部复用同一 parser/formal predicate；报告 content_data
写入 schema/snapshot/formal false；旧 boolean/source 不再恢复。

**Step 4: Run affected lifecycle tests**

Run P1-64、report backcompat、P1-48、P1-61/P1-62/P1-63 与 history/report resource tests。

Expected: PASS。

**Step 5: Commit**

`git commit -m "fix: 收紧静区分析与报告可信门"`

### Task 4: GUI 三态展示

**Files:**
- Create: `gui/src/components/Commissioning/quietZoneEvidence.ts`
- Modify: `gui/src/components/Commissioning/Phases.tsx`
- Create: `gui/test/quietZoneEvidenceTruth.test.ts`

**Step 1: Write the failing contract test**

静态/运行契约覆盖：

- overall null 不显示“预检通过”；
- measured ripple 缺失显示 N/A；
- proxy 单独标“诊断代理，非静区实测”；
- malformed/legacy snapshot 不能显示绿色。

**Step 2: Run tests to verify RED**

Expected: 旧 JSX 仍无条件格式化数值并把 null 当失败或绿色路径。

**Step 3: Implement minimal tri-state presenter**

严格解析 evidence；顶部绿/红/黄三态；正式静区行只显示 N/A，proxy 另行显示且固定黄色。

**Step 4: Run GUI tests and production build**

Run repository GUI contract command and `npm run build`。

Expected: PASS。

**Step 5: Commit**

`git commit -m "fix: 静区未判定在 GUI 保持非绿"`

### Task 5: Roadmap、完整回归与外审

**Files:**
- Modify: `docs/roadmap-first-call.md`
- Modify: `docs/plans/2026-08-23-p1-64-quiet-zone-evidence-truth-design.md`

**Step 1: Update current facts**

记录 RED/GREEN、真实写方仍 Hardware Blocked、测试统计与 consumer 全集；不得把计划写成已实现。

**Step 2: Run verification**

- P1-64 focused + 全部相关 phase/report/history/rule gates；
- 全后端；
- GUI contract + production build；
- `compileall`；
- 单一 Alembic head；
- `git diff --check`。

**Step 3: Run fresh independent review**

要求 P1=0；按反馈以 TDD 修复并重新 review。

**Step 4: Commit, push and open Ready PR**

PR 描述写明可观察故障、全集、RED/GREEN、验证统计与真实硬件边界。

**Step 5: Codex review loop**

R1 处理本片意见后触发 R2；R2 无 P1 即 merge；R2 有 P1则继续 P1-only 复审至最新 HEAD 无 P1。
