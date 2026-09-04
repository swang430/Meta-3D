# P2-59 ③ Channel Emulator Single Session Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 让四类 MIMO OTA 执行入口共用一个 execution-frozen 的信道仿真器会话，在首个 CE I/O 前核对身份，并在所有退出路径完成 safe idle、release 与终态证据闭环。

**Architecture:** 在 `run_base_station_execution_session` 的唯一公共入口中，用新的 `channel_emulator_execution_scope` 包住既有 `instrument_test_lease`。scope 复用租约协调锁和驱动既有 Remote/Local 方法；binding/plan 冻结件是唯一身份输入，live HAL 仅用于逐字段核对，不读取可变数据库配置。终态记录追加到 execution config，P2-66 outcome 用它阻断模拟、未知或不完整 CE 生命周期进入正式输出。

**Tech Stack:** Python 3.11、async context manager、Pydantic v2、SQLAlchemy、pytest/pytest-asyncio。

---

### Task 1: 冻结 execution mode 与纯身份校验器

**Files:**
- Modify: `api-service/app/services/channel_emulator_binding.py`
- Test: `api-service/tests/test_p2_59_3_channel_emulator_session.py`

**Step 1: Write the failing test**

新增测试证明 binding freeze 包含 `execution_mode` 且摘要覆盖该字段；真机逐字段拒绝 module/name/connection/mode 漂移，模拟只接受权威 Mock，所有拒绝均未调用驱动方法。

**Step 2: Run test to verify it fails**

Run: `api-service/.venv/bin/python -m pytest -q api-service/tests/test_p2_59_3_channel_emulator_session.py -k 'binding or identity'`
Expected: FAIL，原因是冻结件缺 `execution_mode` / 校验器尚不存在。

**Step 3: Write minimal implementation**

把 `execution_mode` 加进 `CE_FREEZE_IDENTITY_KEYS` 与冻结 payload，新增只读 `validate_frozen_channel_emulator_before_remote(hal, frozen)`；复用既有 digest、transport 与 `is_mock_driver` 判据，不做 I/O。

**Step 4: Run test to verify it passes**

Run: 同 Step 2。
Expected: PASS。

### Task 2: 租约暴露真实 CE acquire/release 结果

**Files:**
- Modify: `api-service/app/services/instrument_test_lease.py`
- Test: `api-service/tests/test_p2_59_3_channel_emulator_session.py`
- Test: `api-service/tests/test_instrument_test_lease.py`

**Step 1: Write the failing test**

覆盖 acquire 成功/拒绝、release 成功/拒绝与无 Remote 契约的模拟驱动；断言 outcome 只记录实际结果，模拟保持 `None`（not applicable）。

**Step 2: Run test to verify it fails**

Run: `api-service/.venv/bin/python -m pytest -q api-service/tests/test_p2_59_3_channel_emulator_session.py -k lease api-service/tests/test_instrument_test_lease.py`
Expected: FAIL，原因是 outcome 尚无 CE 字段。

**Step 3: Write minimal implementation**

给 `InstrumentTestLeaseOutcome` 增加 CE instrument/acquire/release 字段；只在实际调用并确认对应驱动方法后写 True，拒绝/异常写 False，未调用保持 None。

**Step 4: Run test to verify it passes**

Run: 同 Step 2。
Expected: PASS。

### Task 3: 单一 scope、safe idle 与受控模拟

**Files:**
- Create: `api-service/app/services/channel_emulator_execution_session.py`
- Modify: `api-service/app/services/base_station_execution_session.py`
- Modify: `api-service/app/services/mimo_ota/cleanup.py`
- Modify: `api-service/app/services/mimo_ota/executors/measure.py`
- Test: `api-service/tests/test_p2_59_3_channel_emulator_session.py`
- Test: `api-service/tests/test_p2_42_base_station_execution_session.py`

**Step 1: Write the failing test**

覆盖四类入口的公共插入点、严格路损门在任何仪器 I/O 前先行、首 I/O 前 CE 对账、真实 HAL 缺失拒绝、模拟 HAL 缺失仅在 execution task-local HAL view 暴露 Mock、并发全局 HAL 读者不可见、BaseStation 先于 CE acquire，以及成功/设备拒绝/异常/取消都按 `operation → terminal safe_idle → release` 排序；safe idle False/异常必须 fail-loud 且 release 仍发生。普通链断言 `stop_emulation` 恰好一次；纯直通链的前置 stop 不能冒充 STATIC 之后的终态动作，退出必须以既有 `clear_passthrough_mode` 收口并留 action 证据；直通后若再 `start_emulation`，则必须在 start 前重置终态所有权，成功、返回 False、异常、真实取消或部分生效均在 release 前再次 GOS；真实 task cancellation 不能截断任一终态动作或 release；scope 内旧 cleanup 不得重复停止，scope 外调用仍保留安全收尾。

**Step 2: Run test to verify it fails**

Run: `api-service/.venv/bin/python -m pytest -q api-service/tests/test_p2_59_3_channel_emulator_session.py api-service/tests/test_p2_42_base_station_execution_session.py`
Expected: FAIL，原因是 scope 尚不存在且 MEASURE 仍自造 Mock。

**Step 3: Write minimal implementation**

实现 async scope：解析冻结 binding/plan、组合锁内 validator、按模拟边界准备 task-local HAL view、先取得 BaseStation 再最后取得 CE；租约赢锁后把实际 acquire 的完整 HAL/driver 视图固定到 execution task，后续 force reload 不得把新实例拼入业务或收尾。普通 yield 后调用既有 `stop_emulation`；直通在前置 stop 后把终态 action 切为既有 `clear_passthrough_mode`。进程级 `hal.drivers` 从不安装临时 Mock；用 task-local 所有权让 `cleanup_chamber_instruments` 在 scope 内跳过 CE 停机、但不影响 BS/转台或旧调用。`run_base_station_execution_session` 只替换一处 context manager；删掉 MeasureExecutor 的本地 Mock 构造并要求 scope 已准备 HAL。

**Step 4: Run test to verify it passes**

Run: 同 Step 2。
Expected: PASS。

### Task 4: 不可变 terminal evidence 与正式输出门

**Files:**
- Modify: `api-service/app/services/channel_emulator_execution_session.py`
- Modify: `api-service/app/services/execution_evidence_outcome.py`
- Test: `api-service/tests/test_p2_59_3_channel_emulator_session.py`
- Test: `api-service/tests/test_p2_66_execution_evidence_outcome.py`

**Step 1: Write the failing test**

覆盖完整真机成功、模拟、safe-idle 未确认、release 未确认、失败、异常、取消、摘要篡改、binding/plan digest 漂移和重复 session 冲突；断言只有完整真机 terminal 可保留 formal eligibility。

**Step 2: Run test to verify it fails**

Run: `api-service/.venv/bin/python -m pytest -q api-service/tests/test_p2_59_3_channel_emulator_session.py api-service/tests/test_p2_66_execution_evidence_outcome.py`
Expected: FAIL，原因是 terminal evidence 与 P2-66 消费尚不存在。

**Step 3: Write minimal implementation**

定义 `extra=forbid`、固定 schema version 和状态组合约束的 frozen binding/terminal payload，再校验 canonical digest，按 execution 行锁追加/幂等校验。scope 在 lease 实际退出后持久化；异常/取消先回滚业务事务，再独立提交 terminal，业务异常与 safe-idle/terminal 持久化失败并列保留。P2-66 先完整 parse，再从 frozen binding、冻结 MIMO engine mode 与固定 source 规则纯重建权威 plan，并用共同 verifier 对账；diagnostic-unbound 使用固定权威 Mock manifest，不把合法模拟终态误判 invalid。最后按冻结 bypass/fade 配置核验终态 action 并投影 terminal；只读冻结件和终态记录，将 simulated/unknown/incomplete/malformed 置 diagnostic 或 invalid、`formal_eligible=False`。

**Step 4: Run test to verify it passes**

Run: 同 Step 2。
Expected: PASS。

### Task 5: 受影响回归与完成门

**Files:**
- Modify only if a functional regression is proven by a failing test.

**Step 1: Run focused regressions**

Run: `api-service/.venv/bin/python -m pytest -q api-service/tests/test_p2_59_3_channel_emulator_session.py api-service/tests/test_p2_59_channel_emulator_execution_plan.py api-service/tests/test_p2_42_base_station_execution_session.py api-service/tests/test_instrument_test_lease.py api-service/tests/test_commissioning_smoke.py api-service/tests/test_commissioning_adhoc.py api-service/tests/test_p2_66_execution_evidence_outcome.py api-service/tests/test_rule_gates.py`
Expected: PASS。

**Step 2: Run syntax and diff checks**

Run: `api-service/.venv/bin/python -m compileall -q api-service/app api-service/tests`
Expected: exit 0。

Run: `git diff --check`
Expected: exit 0。

**Step 3: Fresh review**

逐条复核 AGENTS.md：真实判据来源、模拟排除、SCPI 零新增、safe-idle 代价不对称、四入口与四退出路径、产生/消费镜像；功能 P1 必须为 0。

**Step 4: Commit**

只提交本片受控文件；不得包含 `api-service/.venv` 或用户仪器资料。不要推送、开 PR 或合并。
