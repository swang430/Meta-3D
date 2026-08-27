# P0-9B-3 Aerotech Positioner Coordinate Freeze Implementation Plan

> **For Codex:** REQUIRED SUB-SKILL: Use `executing-plans` and `test-driven-development` task-by-task.

**Goal:** 将用户配置且已有现场证明的 Aerotech `PFBK - MOVEABS` 偏置冻结到本次 execution，
并用同一快照核对实际 MOVEABS 与最终 PFBK，消除正式位置证据的 UNKNOWN 和二次换算错误。

**Architecture:** 新增单一 positioner coordinate freeze 服务，在 TestExecution 排入后台前从锁定的
LabProfile/category/connection 与加载 driver 构造稳定快照；MEASURE 在每个方位首条 I/O 前验证
活动 driver 未漂移；现有 `positioner.angle` evidence 消费冻结快照，同时核对程序坐标和物理反馈。
不新增表、端点或第二套正式判据。

**Tech Stack:** Python 3.13、Pydantic、SQLAlchemy、pytest/pytest-asyncio、现有 SCPI evidence。

---

### Task 1: 冻结用户配置的坐标合同

**Files:**
- Create: `api-service/app/services/positioner_coordinate_profile.py`
- Modify: `api-service/app/services/test_case_runner.py`
- Modify: `api-service/app/api/commissioning.py`
- Create: `api-service/tests/test_p0_9b3_positioner_coordinate_freeze.py`

**Step 1: 写 RED**

覆盖以下全集：

- 真实 Aerotech 从所选 LabProfile 的同一 InstrumentConnection 冻结 degree、+90°、轴、范围、速度、
  容差、现场验证来源与带时区验证时间；
- binding、selected model、connection endpoint、loaded driver class/endpoint/config 任一分叉即拒绝；
- `verified` 不是精确 `True`、偏置/范围/速度/容差非有限或单位不是 degree 时拒绝；
- 已冻结 execution 重复调用不覆盖；已有硬件进度但无快照的旧 execution 拒绝回填；
- Mock/非 Aerotech 不获得正式 Aerotech 坐标证明。

**Step 2: 运行 RED**

```bash
cd api-service
./.venv/bin/python -m pytest -q tests/test_p0_9b3_positioner_coordinate_freeze.py
```

Expected: FAIL，因为冻结服务尚不存在。

**Step 3: 最小 GREEN**

- 用严格 Pydantic model 解析持久化参数，布尔值不得 truthy 放宽；
- 锁定 category、connection、LabProfile 与 execution；
- 保存 schema version、resolution、同源 identity、坐标字段、source reference、server timestamp 与
  canonical digest 到 `TestExecution.config`；
- 提供纯本地 `validate_frozen_positioner_before_motion()`；
- 在 case runner 排入后台前调用，失败转为现有 `CaseNotExecutable`；commissioning session 创建时
  在任何 phase progress 之前同时冻结 baseStation 与 positioner（否则先跑 PRECHECK 后将无法安全
  补冻），单相位/adhoc 的 MEASURE 与 run-all 在取得 Remote 前复核同一 positioner 快照；
  PRECHECK/ANALYSIS/REPORT 不发转台 I/O。

**Step 4: 运行 GREEN**

```bash
cd api-service
./.venv/bin/python -m pytest -q \
  tests/test_p0_9b3_positioner_coordinate_freeze.py \
  tests/test_p1_73b_adapter_profile_freeze.py
```

Expected: PASS。

**Step 5: 提交**

```bash
git add api-service/app/services/positioner_coordinate_profile.py \
  api-service/app/services/test_case_runner.py \
  api-service/tests/test_p0_9b3_positioner_coordinate_freeze.py
git commit -m "feat: freeze positioner coordinate contract"
```

### Task 2: 在动作前消费冻结合同

**Files:**
- Modify: `api-service/app/services/mimo_ota/executors/measure.py`
- Modify: `api-service/tests/test_p0_9b3_positioner_coordinate_freeze.py`
- Modify: `api-service/tests/test_p1_47c_execution_scpi_evidence.py`

**Step 1: 写 RED**

- +90° 快照下，请求 200° 前验证通过，动作实际发送 110°；
- 快照创建后活动 driver 的 offset、verified、axis、endpoint 或 class 漂移时，在首条 MOVEABS 前失败；
- 缺快照或旧 execution 不得读取当前 connection_params 补绿；
- 模拟/非 Aerotech 路径维持诊断语义，不伪造正式通过。

**Step 2: 运行 RED**

```bash
cd api-service
./.venv/bin/python -m pytest -q \
  tests/test_p0_9b3_positioner_coordinate_freeze.py \
  tests/test_p1_47c_execution_scpi_evidence.py
```

Expected: FAIL，因为 MEASURE 尚未在 I/O 前验证 execution snapshot。

**Step 3: 最小 GREEN**

- 在方位循环首条 positioner I/O 前调用纯验证器；
- 验证失败返回 FAILED，保留预登记 evidence 为 UNKNOWN，且不发送动作；
- 将冻结快照显式传入 `record_positioner_capture()`，禁止 writer 重新读取实时 DB/config。

**Step 4: 运行 GREEN**

同 Step 2，Expected: PASS。

**Step 5: 提交**

```bash
git add api-service/app/services/mimo_ota/executors/measure.py \
  api-service/tests/test_p0_9b3_positioner_coordinate_freeze.py \
  api-service/tests/test_p1_47c_execution_scpi_evidence.py
git commit -m "fix: bind positioner motion to frozen coordinates"
```

### Task 3: 修正 position evidence 的三层坐标语义

**Files:**
- Modify: `api-service/app/hal/scpi_evidence.py`
- Modify: `api-service/app/hal/aerotech_positioner.py`
- Modify: `api-service/app/services/execution_scpi_evidence.py`
- Modify: `api-service/tests/test_p1_47b_instrument_evidence.py`
- Modify: `api-service/tests/test_p1_47c_execution_scpi_evidence.py`

**Step 1: 写 RED**

- requested=200、offset=+90、实际 `MOVEABS X 110`、PFBK=200 必须 PASSED；
- MOVEABS=200（未换算）、MOVEABS=100（错误换算）、PFBK=110（二次换算结果）分别拒绝；
- 圆周边界使用最短角误差；正式容差仍上限 1°；
- 缺失/未验证快照、错轴反馈、传输失败或设备拒绝保持既有 fail-closed 分类；
- readback 同时披露 requested physical、expected/actual program、raw PFBK、offset 与两类误差。

**Step 2: 运行 RED**

```bash
cd api-service
./.venv/bin/python -m pytest -q \
  tests/test_p1_47b_instrument_evidence.py \
  tests/test_p1_47c_execution_scpi_evidence.py
```

Expected: FAIL，因为旧构造器仍从 PFBK 再减 offset，且未解析实际 MOVEABS 目标。

**Step 3: 最小 GREEN**

- 严格解析同 capture 中 X 轴 MOVEABS 程序目标；
- `expected_program=requested-offset`，实际命令必须在容差内匹配；
- 原始 PFBK 直接与 requested 比较，不再二次减 offset；
- 两项都成立才形成 APPLIED/PASSED；禁止 requested 回填；
- writer 只消费 execution-frozen profile。

**Step 4: 运行 GREEN 与受影响回归**

```bash
cd api-service
./.venv/bin/python -m pytest -q \
  tests/test_p0_9b3_positioner_coordinate_freeze.py \
  tests/test_p1_47b_instrument_evidence.py \
  tests/test_p1_47c_execution_scpi_evidence.py \
  tests/test_p1_56_positioner_motion_truth.py \
  tests/test_p1_56_aerotech_motion_diagnostic.py \
  tests/test_rule_gates.py
```

Expected: PASS。

**Step 5: 提交**

```bash
git add api-service/app/hal/scpi_evidence.py \
  api-service/app/hal/aerotech_positioner.py \
  api-service/app/services/execution_scpi_evidence.py \
  api-service/tests/test_p1_47b_instrument_evidence.py \
  api-service/tests/test_p1_47c_execution_scpi_evidence.py
git commit -m "fix: verify positioner program and feedback coordinates"
```

### Task 4: 状态回执、完整验证与 review

**Files:**
- Modify: `docs/roadmap-first-call.md`
- Modify: `docs/site-debug/2026-08-27-lte-cmw500-onsite-summary.md`

**Step 1: 更新状态但不冒充现场完成**

记录 P0-9B-3 本地冻结与证据链已经实现，状态仍为“本地半完成，待同一 TestCase 方位复验与独立
HOME PFBK 取证”。

**Step 2: 验证**

```bash
git diff --check
cd api-service
./.venv/bin/python -m compileall -q app tests
./.venv/bin/python -m pytest -q tests/test_rule_gates.py
./.venv/bin/python -m pytest -q
```

同时核对单一 Alembic head；若本片无 GUI/OpenAPI 改动，记录为不适用而不伪造运行声明。

**Step 3: fresh 内审**

按 AGENTS.md 0.5 重新列出生产方、消费方和成功/拒绝/异常/取消路径；功能 P1/P2/P3 与测试建议
物理分栏。P1=0 后更新 roadmap 并提交。

**Step 4: PR 外审**

- 推送并创建 Ready PR，触发 Codex R1；
- R1 处理本片功能 P1 与本片内 P2，回归并逐条回复后触发 R2；
- R2 无 P1 即 merge；R2 若仍有 P1，继续 P1-only review 直到覆盖最新 HEAD 无 P1；
- 合并后同步本地 main、保留未跟踪仪器资料、清理 worktree/本地分支；
- 不自动开始下一条 roadmap。
