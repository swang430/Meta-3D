# P2-59② Channel Emulator Runtime Probing Removal Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 让 MIMO OTA MEASURE 的信道仿真器路径只消费 execution-frozen `ChannelEmulatorExecutionPlan` 与 `ChannelEmulatorDriver` 明确协议，不再用对象形状或 F64 私有实现猜能力。

**Architecture:** 会触发仪器 I/O 的能力进入 `ChannelEmulatorManifest`，并由现有 execution plan 自动冻结；证据构造、加载身份和拓扑 getter 作为所有 CE 驱动都必须提供的基类协议。执行器只用 frozen plan 决定路径，协议 getter 只返回观察值，不承担能力声明。

**Tech Stack:** Python 3.11、FastAPI/Pydantic、pytest、既有 CE manifest/execution-plan/HAL 架构。

---

### Task 1: 钉住机械全集与 manifest 显式声明

**Files:**
- Create: `api-service/tests/test_p2_59_2_channel_emulator_runtime_plan.py`
- Modify: `api-service/app/hal/channel_emulator_manifest.py`
- Modify: `api-service/app/hal/channel_emulator.py`
- Modify: `api-service/app/hal/propsim_f64.py`
- Modify: `api-service/app/hal/propsim_fs16.py`

**Step 1: Write the failing test**

断言 12 个仪器操作进入唯一词汇；F64 逐项 `implemented` 且有既有源码/现场出处；FS16/Mock 逐项 `not_implemented`；声明为 implemented 的方法必须在具体驱动类上存在。

**Step 2: Run test to verify it fails**

Run: `PYTHONPATH=api-service /Users/simon/Tools/MIMO-First/api-service/.venv/bin/python -m pytest -q api-service/tests/test_p2_59_2_channel_emulator_runtime_plan.py -k manifest`
Expected: FAIL，操作词汇缺失。

**Step 3: Write minimal implementation**

扩展 manifest Literal/tuple 和三个驱动的类级声明；不改任何 SCPI 字面量或命令顺序。

**Step 4: Run test to verify it passes**

Run the same command. Expected: PASS。

### Task 2: 把证据与拓扑读取改成基类协议

**Files:**
- Modify: `api-service/tests/test_p2_59_2_channel_emulator_runtime_plan.py`
- Modify: `api-service/app/hal/channel_emulator.py`
- Modify: `api-service/app/hal/propsim_f64.py`
- Modify: `api-service/app/hal/propsim_fs16.py`
- Modify: `api-service/app/services/execution_scpi_evidence.py`

**Step 1: Write the failing test**

断言基类声明六个 getter/builder 协议，三种生产驱动显式实现；F64 public loaded getter 返回既有缓存；FS16/Mock 返回 `None`；空 evidence builder 不写正式证据。

**Step 2: Run test to verify it fails**

Run the targeted test. Expected: FAIL，协议方法缺失。

**Step 3: Write minimal implementation**

增加无 I/O 的协议方法；F64 仅公开既有字段，FS16/Mock 不制造值；evidence helper 接受 `None` 并立即返回。

**Step 4: Run test to verify it passes**

Run the targeted test. Expected: PASS。

### Task 3: MEASURE 全部探测改读 frozen plan / 明确协议

**Files:**
- Modify: `api-service/tests/test_p2_59_2_channel_emulator_runtime_plan.py`
- Modify: `api-service/app/services/mimo_ota/executors/measure.py`

**Step 1: Write the failing test**

AST/源码门断言 CE 路径不再含 16 个 `hasattr/getattr` 探测、不读 `_loaded_emulation_file`、不 import `_TOPOLOGY_ESCAPE_HINT`、不调用 `get_supported_load_modes()`；负能力走 plan reason/明确 diagnostic，planned 但方法实现漂移时 fail-loud。

**Step 2: Run test to verify it fails**

Run the targeted test. Expected: FAIL，命中旧探测。

**Step 3: Write minimal implementation**

让 `_apply_output_gain`、manual input、closed loop 与拓扑校验显式接收 CE plan；直接调用协议 getter；四处 evidence capture 无条件走可空 builder；加载身份走 public getter。

**Step 4: Run test to verify it passes**

Run the targeted test. Expected: PASS。

### Task 4: 两种生成策略消费冻结 load mode

**Files:**
- Modify: `api-service/tests/test_p2_59_2_channel_emulator_runtime_plan.py`
- Modify: `api-service/app/services/channel_generation/gcm_strategy.py`
- Modify: `api-service/app/services/channel_generation/b2_parametric_strategy.py`
- Modify: `api-service/app/services/mimo_ota/executors/measure.py`

**Step 1: Write the failing test**

断言 Native/B2 生成策略从传入 plan 的 `load_mode_planned` 判能力，不直接查询驱动；不支持时在任何 CE I/O 前返回失败。

**Step 2: Run test to verify it fails**

Run the targeted test. Expected: FAIL，仍调用 live driver manifest。

**Step 3: Write minimal implementation**

构造策略时传入同一个 `ce_plan`；删掉策略和 Measure 的运行时查询。保留 HAL `load_channel` 的本地防御门。

**Step 4: Run test to verify it passes**

Run the targeted test. Expected: PASS。

### Task 5: 受影响回归与 fresh 自审

**Files:**
- Verify only

**Step 1: Run focused and affected tests**

运行 P2-57/P2-59、MIMO MEASURE、GCM/B2、F64 输入/输出/证据相关测试；任何失败先判断是否暴露漏消费方，再最小修复。

**Step 2: Run compile and diff gates**

运行 `compileall`、单一 Alembic head（若涉及）、base-to-HEAD/working diff-check，并确认 `api-service/.venv` 未进入状态。

**Step 3: Fresh functional review**

从可观察失败场景复审能力负路径、模拟证据、拓扑未知、plan 漂移与厂商边界；P1 必须为 0。

**Step 4: Commit, but do not push**

提交到 `codex/p2-59-2-runtime-plan`，向主代理提供 SHA、RED→GREEN、验证结果与和③可能冲突的精确行。

### Task 2.5: execution plan v1/v2 兼容门（集成审计 P1）

**Files:**
- Modify: `api-service/app/hal/channel_emulator_manifest.py`
- Modify: `api-service/app/hal/channel_emulator_execution_plan.py`
- Modify: `api-service/app/services/channel_emulator_execution_plan.py`
- Modify: `api-service/tests/test_p2_57_channel_emulator_manifest.py`
- Modify: `api-service/tests/test_p2_58_channel_emulator_binding.py`
- Modify: `api-service/tests/test_p2_59_channel_emulator_execution_plan.py`

**RED:** 固定构造一份原 14 项、摘要匹配的 v1 manifest / binding / plan 冻结件；证明当前实现因全局
26 项词汇拒绝它。另证明新 resolver 仍写 v1、待执行 v1 会得到不明确的普通漂移错误，以及 v1 binding
可与 v2 plan 静默混搭。

**GREEN:** 分别固定 manifest/plan 的 v1=14、v2=26 词汇；新 resolver 写 v2/26 项；parser/validator
按版本并对原始 payload 验摘要；freeze/MEASURE 对待执行 v1 或 v1 binding×v2 plan 明确拒绝并提示重建，
纯历史 validate 保持成功。不改 P2-66 outcome、terminal 或 history 投影，因为机械搜索确认它们没有解析
该冻结键。
