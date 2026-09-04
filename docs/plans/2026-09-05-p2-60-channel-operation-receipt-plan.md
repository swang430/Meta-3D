# P2-60 Vendor-neutral Channel Operation Receipt Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 为 execution-bound 的信道仿真器 load/configure/start/adjust/stop/cleanup/release 建立逐操作、逐字段、可审计的不可变 receipt，并让 P2-66 正式输出门只放行同一冻结执行内完整且有据的真实操作链。

**Architecture:** 在 P2-59 的唯一 `channel_emulator_execution_scope` 中建立 task-local recorder owner；所有正式执行里的 effectful CE 调用通过共同 async recorder，捕获原始 exchange 索引并调用 adapter 的纯证据投影。receipt 独立追加到 execution config，新会话 terminal 升级为 v2 并绑定 receipt-chain digest；历史 terminal v1 保持原语义。P2-66、API/GUI 与 P2-67 JSONL 导出只消费服务器共同投影。

**Tech Stack:** Python 3.11、Pydantic v2、SQLAlchemy、FastAPI/OpenAPI、React/TypeScript、pytest、Node test/build。

---

### Task 1: 不可变 receipt schema、链摘要与追加存储

**Files:**
- Create: `api-service/app/services/channel_emulator_operation_receipt.py`
- Create: `api-service/tests/test_p2_60_channel_operation_receipt.py`

**Step 1: Write the failing tests**

覆盖严格 schema、逐字段六态、canonical digest、simulated/confirmed 矛盾、unavailable 零 exchange、失败不得声称成功、重复 receipt 幂等/冲突、跨 execution/session/lease/instrument 身份漂移、sequence/chain digest 篡改。

**Step 2: Run tests to verify RED**

Run: `PYTHONPATH=api-service /Users/simon/Tools/MIMO-First/api-service/.venv/bin/python -m pytest -q api-service/tests/test_p2_60_channel_operation_receipt.py -k 'schema or persist or chain'`

Expected: FAIL，模块/模型/持久化入口不存在。

**Step 3: Write minimal GREEN implementation**

实现 `FrozenChannelOperationField`、`FrozenChannelOperationReceipt`、原始 payload digest、按 sequence 的 chain digest、纯 validator 与 TestExecution 行锁 append。只存 JSON-safe requested/applied 和 exchange id，不存原始响应。

**Step 4: Run tests to verify GREEN**

Run: 同 Step 2。Expected: PASS。

### Task 2: task-local recorder 与异常/取消分类

**Files:**
- Modify: `api-service/app/services/channel_emulator_operation_receipt.py`
- Modify: `api-service/app/services/channel_emulator_execution_session.py`
- Modify: `api-service/app/hal/channel_emulator.py`
- Modify: `api-service/app/hal/propsim_f64.py`
- Modify: `api-service/app/hal/propsim_fs16.py`
- Modify: `api-service/tests/test_p2_60_channel_operation_receipt.py`

**Step 1: Write the failing tests**

覆盖 scope 内身份继承、scope 外正式调用拒绝、plan 未 planned/unavailable 零 I/O、True/False/异常/timeout/cancel 分类、同一 capture/execution/instrument 校验、Mock simulated，以及 receipt 持久化失败不能被业务布尔成功吞掉。

**Step 2: Run tests to verify RED**

Run: `PYTHONPATH=api-service /Users/simon/Tools/MIMO-First/api-service/.venv/bin/python -m pytest -q api-service/tests/test_p2_60_channel_operation_receipt.py -k 'record or cancel or unavailable or mock'`

Expected: FAIL，recorder owner 与 adapter 证据协议不存在。

**Step 3: Write minimal GREEN implementation**

在 session acquire 后安装 task-local owner；实现 async recorder，内部复用 `capture_scpi_exchanges()`，原样返回/重抛。基类声明纯 `project_channel_operation_evidence` 协议；F64 只读取现有公开状态/目录范围，FS16 未实现返回 unavailable，Mock 返回 simulated/unknown。不新增或改写任何命令。

**Step 4: Run tests to verify GREEN**

Run: 同 Step 2。Expected: PASS。

### Task 3: load/configure/start/adjust 全部正式调用接入共同 recorder

**Files:**
- Modify: `api-service/app/services/channel_generation/asc_strategy.py`
- Modify: `api-service/app/services/channel_generation/external_asc_strategy.py`
- Modify: `api-service/app/services/channel_generation/gcm_strategy.py`
- Modify: `api-service/app/services/channel_generation/b2_parametric_strategy.py`
- Modify: `api-service/app/services/mimo_ota/executors/measure.py`
- Modify: `api-service/app/services/input_level_controller.py`
- Modify: `api-service/tests/test_p2_60_channel_operation_receipt.py`
- Modify: `api-service/tests/test_p2_59_2_channel_emulator_runtime_plan.py`

**Step 1: Write the failing tests**

机械枚举 execution-bound effectful 调用，证明 load、output level/gain、input reference/crest、passthrough、fading start、input closed-loop 写操作均只经 recorder；只读 observation 进入对应 receipt，不从当前 TestCase/HAL 缓存补真。对未 planned 的 FS16 路径断言首个 I/O 前 unavailable/fail-loud；Mock 命令拼装仍走真实 builder 但 receipt simulated。

**Step 2: Run tests to verify RED**

Run: `PYTHONPATH=api-service /Users/simon/Tools/MIMO-First/api-service/.venv/bin/python -m pytest -q api-service/tests/test_p2_60_channel_operation_receipt.py api-service/tests/test_p2_59_2_channel_emulator_runtime_plan.py -k 'load or configure or start or adjust or callsite'`

Expected: FAIL，现有调用仍绕过 recorder。

**Step 3: Write minimal GREEN implementation**

给策略与 controller 注入同一 recorder/plan context；替换 effectful 直调，不改变参数、顺序、返回判断或厂商命令。读回只作为同一次 invocation 的 evidence，不让后续可变 current state 回填旧 receipt。

**Step 4: Run tests to verify GREEN**

Run: 同 Step 2。Expected: PASS。

### Task 4: SAFE_IDLE、release 与 terminal v2 对称闭环

**Files:**
- Modify: `api-service/app/services/channel_emulator_execution_session.py`
- Modify: `api-service/app/services/instrument_test_lease.py`
- Modify: `api-service/tests/test_p2_60_channel_operation_receipt.py`
- Modify: `api-service/tests/test_p2_59_3_channel_emulator_session.py`
- Modify: `api-service/tests/test_instrument_test_lease.py`

**Step 1: Write the failing tests**

覆盖普通 stop、passthrough clear、start 后重新 arm stop、设备拒绝、异常、真实 task cancellation、SAFE_IDLE 二次失败、release 未确认；断言 action receipt 在 release 前，release receipt 取实际 lease outcome，terminal v2 的 count/digest/receipt ids 与链一致。固定一份原始 v1 terminal fixture，证明仍按原 digest 解析。

**Step 2: Run tests to verify RED**

Run: `PYTHONPATH=api-service /Users/simon/Tools/MIMO-First/api-service/.venv/bin/python -m pytest -q api-service/tests/test_p2_60_channel_operation_receipt.py api-service/tests/test_p2_59_3_channel_emulator_session.py api-service/tests/test_instrument_test_lease.py -k 'safe_idle or release or terminal or legacy'`

Expected: FAIL，新 terminal 仍是 v1 且未绑定 receipt chain。

**Step 3: Write minimal GREEN implementation**

SAFE_IDLE 通过同一 recorder；lease 退出后生成 transport release receipt；新 scope 只写 terminal v2，引用已验证的当前 session receipt chain。v1 validator 保留原始 payload 形态；不得给历史补默认字段后重算摘要。

**Step 4: Run tests to verify GREEN**

Run: 同 Step 2。Expected: PASS。

### Task 5: P2-66 正式 outcome 与历史兼容

**Files:**
- Modify: `api-service/app/services/execution_evidence_outcome.py`
- Modify: `api-service/tests/test_p2_60_channel_operation_receipt.py`
- Modify: `api-service/tests/test_p2_66_execution_evidence_outcome.py`

**Step 1: Write the failing tests**

构造性反例覆盖：伪造 compatible terminal、缺 receipt、串 session/lease/instrument、链摘要漂移、confirmed 值没有权威 exchange、unknown 配置字段、simulated、FS16 unavailable、失败后重试、running 尚未到终态、measurement attempt 已结束但 pipeline 仍 running、以及 pre-P2-60 v1 历史。

**Step 2: Run tests to verify RED**

Run: `PYTHONPATH=api-service /Users/simon/Tools/MIMO-First/api-service/.venv/bin/python -m pytest -q api-service/tests/test_p2_60_channel_operation_receipt.py api-service/tests/test_p2_66_execution_evidence_outcome.py -k 'outcome or formal or history or tamper'`

Expected: FAIL，P2-66 尚未消费 receipt。

**Step 3: Write minimal GREEN implementation**

让 `_channel_emulator_terminal_projection` 按 terminal version 分流；v2 从 frozen binding/plan 与 receipt 链纯重建，不查询 current state。只有全部 required effectful invocation 完整、真实、未篡改且必需字段 confirmed 才保留 formal；simulated diagnostic，unknown/unavailable/rejected/failed/cancelled invalid。v1 保持既有分类。

**Step 4: Run tests to verify GREEN**

Run: 同 Step 2。Expected: PASS。

### Task 6: 公共投影、OpenAPI/GUI 与 JSONL 审计

**Files:**
- Modify: `api-service/app/services/channel_emulator_operation_receipt.py`
- Modify: `api-service/app/api/test_plan.py`
- Modify: `api-service/app/api/test_execution.py`
- Modify: `api-service/app/api/system_logs.py`
- Modify: `api-service/app/schemas/test_plan.py`
- Modify: `api/openapi.yaml`
- Modify: `gui/src/types/api.generated.ts`
- Modify: `gui/src/features/TestManagement/types/index.ts`
- Modify: `gui/src/features/TestManagement/components/HistoryTab/HistoryTab.tsx`
- Modify: `api-service/tests/test_p2_60_channel_operation_receipt.py`
- Create: `gui/src/types/channelOperationReceipt.test.ts`

**Step 1: Write the failing tests**

断言 status/history detail 与 execution-filtered JSONL metadata 都消费同一服务器投影；投影不含原始响应，unknown/unavailable/diagnostic 不显示绿色；普通导出/raw download 不变；live/checked OpenAPI、generated TS、手写类型四镜像一致。

**Step 2: Run tests to verify RED**

Run backend targeted tests and `cd gui && node --import tsx --test src/types/channelOperationReceipt.test.ts`。

Expected: FAIL，公共字段与镜像不存在。

**Step 3: Write minimal GREEN implementation**

新增只读 projection 字段；API 只调用服务器 projector，GUI 只渲染 status/reasons/receipt digest。重新生成 `api.generated.ts`，不手改生成器输出。JSONL 首条 metadata 添加同一摘要，文件名/过滤语义不变。

**Step 4: Run tests to verify GREEN**

Run: 同 Step 2，加 GUI production build。Expected: PASS。

### Task 7: 生产路径门、roadmap 状态与完整验证

**Files:**
- Modify: `api-service/tests/test_p2_60_channel_operation_receipt.py`
- Modify: `api-service/tests/test_rule_gates.py`
- Modify: `docs/roadmap-first-call.md`
- Modify only functional regressions proven by failing tests.

**Step 1: Add rule gates**

门控：正式 execution-bound effectful CE 调用不可绕过 recorder；adapter projector 不新增无出处命令字面量；Mock confirmed 永远禁止；FS16 未实现零 I/O；terminal v1/v2 固定 fixture 均可解析且新 writer 只写 v2。

**Step 2: Run affected regressions**

至少覆盖 P2-57～P2-60、P2-66/P2-67、MIMO measure/channel generation/input controller、session/lease/cleanup/report/history/system-log export 与 rule gates。

**Step 3: Run full verification**

- 全后端 pytest；
- GUI 契约与 production build；
- `compileall`；
- 单一 Alembic head；
- base-to-HEAD/working `git diff --check`；
- 核实工作树只含本片受控文件，`api-service/.venv` 未提交。

**Step 4: Fresh functional review**

按 AGENTS.md 逐项审查真实判据来源、模拟排除、SCPI 出处、假成功、SAFE_IDLE 代价不对称、产生/消费全集、历史与失败对称路径；功能 P1 必须为 0。

**Step 5: Finish branch**

提交、推送、开 Ready PR，走 Codex R1 → R2；R1 处理功能 P1 与本片内 P2，覆盖最新 HEAD 的 R2 无 P1且 mergeable/checks 通过或无必需 checks 才合并。R2+ P2/P3 只报告、不阻塞、不自动积压。
