# BaseStation Diagnostic Lifecycle Hotfix Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 让冻结为 diagnostic 的 BaseStation 执行在完整安全收尾后成功结束，同时保持正式 evidence/KPI 全部 fail-closed。

**Architecture:** 将“执行是否完整安全收尾”与“证据是否足以发布正式 KPI”拆成两个判据。`persist_execution_base_station_release()` 只读取本次 execution 冻结的 qualification 选择判据，不读取当前可变状态。

**Tech Stack:** Python 3.12、FastAPI/SQLAlchemy、Pydantic v2、pytest/pytest-asyncio。

---

### Task 1: 冻结分类与诊断完成判据

**Files:**
- Modify: `api-service/app/services/mimo_ota/base_station_execution_evidence.py`
- Test: `api-service/tests/test_base_station_diagnostic_lifecycle_hotfix.py`

**Step 1: Write the failing tests**

新增最小 evidence fixture，证明：

- config 未确认但 diagnostic windows、cleanup、lease release 完整时，诊断完成判据返回 true；
- 缺方位、窗口索引漂移、trust 不允许诊断、cleanup 或 release 未确认时返回 false；
- 现有正式生命周期判据对相同 diagnostic evidence 仍返回 false。

**Step 2: Run tests to verify RED**

Run: `api-service/.venv/bin/pytest -q api-service/tests/test_base_station_diagnostic_lifecycle_hotfix.py`

Expected: FAIL，因为专用诊断完成判据尚不存在。

**Step 3: Write minimal implementation**

在 evidence 模块增加只验证当前 attempt、方位/窗口形状、diagnostic trust、cleanup 与 release 的纯函数；复用现有解析与 shape 校验，不放宽正式判据。

**Step 4: Run tests to verify GREEN**

Run: `api-service/.venv/bin/pytest -q api-service/tests/test_base_station_diagnostic_lifecycle_hotfix.py`

Expected: PASS。

**Step 5: Commit**

提交测试与最小 evidence 判据。

### Task 2: 执行会话按冻结 qualification 选择终态判据

**Files:**
- Modify: `api-service/app/services/execution_scpi_evidence.py`
- Test: `api-service/tests/test_base_station_diagnostic_lifecycle_hotfix.py`

**Step 1: Write the failing tests**

覆盖 `persist_execution_base_station_release()`：

- 显式 diagnostic qualification + 完整诊断 attempt → `completed`；
- formal、缺失或畸形 qualification + config 未确认 → `failed`；
- transport release 未确认仍抛错；
- 只更新传入的 current attempt。

**Step 2: Run tests to verify RED**

Run: `api-service/.venv/bin/pytest -q api-service/tests/test_base_station_diagnostic_lifecycle_hotfix.py`

Expected: diagnostic case FAIL，现实现只调用正式生命周期判据。

**Step 3: Write minimal implementation**

从 execution.config 严格解析冻结 qualification classification；只有精确
`diagnostic` 才调用诊断完成判据，其他状态继续调用正式判据。

**Step 4: Run focused regressions**

Run: `api-service/.venv/bin/pytest -q api-service/tests/test_base_station_diagnostic_lifecycle_hotfix.py api-service/tests/test_p2_42_base_station_execution_session.py api-service/tests/test_p2_48_measurement_window_evidence.py api-service/tests/test_p2_52_uxm_window_boundary.py api-service/tests/test_execution_qualification.py`

Expected: PASS。

**Step 5: Commit**

提交 execution session 收口。

### Task 3: 全量验证与审查

**Files:**
- Modify only if review finds a functional defect.

**Step 1: Run affected and rule-gate suites**

运行 BaseStation session/evidence/qualification/formal consumers 与 rule gates。

**Step 2: Run full backend suite**

Run: `cd api-service && .venv/bin/pytest -q`

Expected: 0 failed。

**Step 3: Run structural checks**

运行 compileall、单一 Alembic head、base-to-HEAD diff-check。

**Step 4: Fresh independent functional review**

按 AGENTS.md 0.5 重新枚举 execution terminal、diagnostic/formal consumers 与历史兼容入口；功能 P1 必须为零。

**Step 5: Push, open Ready PR, and run Codex R1→R2**

覆盖最新 HEAD 的 R2 无 P1 且 PR mergeable/checks 通过或无必需 checks 后 merge commit；随后同步本地 main 并清理 worktree/branch。
