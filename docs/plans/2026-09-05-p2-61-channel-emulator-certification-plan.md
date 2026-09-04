# P2-61 Channel Emulator Diagnostic/Formal Certification Implementation Plan

> **执行要求：** 使用 executing-plans 严格逐 Task 实施；用户已要求单 Agent 串行，禁止派发或复用 subagent。

**Goal:** 建立服务器权威、可撤销、只影响后续执行的 Channel Emulator site certification，并让正式输出只放行同一冻结 scope 下通过完整现场证据认证的新执行。

**Architecture:** `InstrumentConnection` 保存 CE 当前 certification；新 terminal v3 冻结真实硬件 identity/options；CE binding/plan 后新增独立 execution qualification。认证 API 只从一条真实 completed execution 的 binding/plan/asset、identity/options、P2-60 receipts、频率/level/path-loss、SAFE_IDLE/release 派生。P2-66 合并 BaseStation 与 CE qualification，全部正式消费者继续只读共同 outcome。

**Tech Stack:** Python 3.11、Pydantic v2、SQLAlchemy/Alembic、FastAPI/OpenAPI、React/TypeScript、pytest、Node test/build。

---

### Task 1：持久化 CE certification 与严格 schema

**Files:**
- Create: `api-service/app/services/channel_emulator_certification.py`
- Modify: `api-service/app/models/instrument.py`
- Modify: `api-service/app/schemas/instrument.py`
- Create: `api-service/alembic/versions/<revision>_add_channel_emulator_site_certification.py`
- Create: `api-service/tests/test_p2_61_channel_emulator_certification.py`

**Step 1: Write failing tests**

覆盖 certification/proofs strict/frozen schema、canonical options/digest、active/revoked 审计互斥、八类 proofs 缺一拒绝、普通 connection update 无整份 certification 写入口、migration 旧行 null、单一 Alembic head。

**Step 2: Verify RED**

Run: `PYTHONPATH=api-service api-service/.venv/bin/python -m pytest -q api-service/tests/test_p2_61_channel_emulator_certification.py -k 'schema or migration or connection'`

Expected: FAIL，模块/列/schema 尚不存在。

**Step 3: Minimal GREEN**

实现不可变 `ChannelEmulatorCertificationProofs`、`ChannelEmulatorSiteCertification`、parse/digest helper；新增 nullable server-owned JSON 列和 migration。只读 response 暴露，create/update request 不接受该字段。

**Step 4: Verify GREEN and commit**

运行同一测试、Alembic heads 与 diff-check；提交 Task 1。

### Task 2：terminal v3 冻结硬件 identity/options

**Files:**
- Modify: `api-service/app/services/channel_emulator_certification.py`
- Modify: `api-service/app/services/channel_emulator_execution_session.py`
- Modify: `api-service/app/hal/channel_emulator.py`
- Modify: `api-service/app/hal/propsim_f64.py`
- Modify: `api-service/app/hal/propsim_fs16.py`
- Modify: `api-service/tests/test_p2_61_channel_emulator_certification.py`
- Modify: `api-service/tests/test_p2_59_3_channel_emulator_session.py`
- Modify: `api-service/tests/test_p2_60_channel_operation_receipt.py`

**Step 1: Write failing tests**

覆盖 live cached identity/options 的纯投影、无新增 I/O、Mock simulated、identity 缺 model/firmware/serial 或 `options_observed=false` fail-closed、已确认零选件可表示、session acquire 身份与冻结身份漂移、terminal v3 digest；固定原始 v1/v2 fixtures 确认历史摘要不重算。

**Step 2: Verify RED**

Run targeted P2-59/P2-60/P2-61 tests with `-k 'identity or terminal or legacy or simulated'`。

Expected: FAIL，当前 terminal 没有硬件 identity/options。

**Step 3: Minimal GREEN**

新增同步、只读 `capture_channel_emulator_certification_identity()` adapter protocol；F64/FS16 仅投影 connect 已有缓存与既有出处，Mock 返回 simulated。session 在 lease acquire 后固定 identity，terminal writer 升 v3；不发新命令，不访问 current connection 回填终态。

**Step 4: Verify GREEN and commit**

运行同一测试与 P2-60 receipt/session 回归；提交 Task 2。

### Task 3：服务器派生 activate/revoke certification

**Files:**
- Modify: `api-service/app/services/channel_emulator_certification.py`
- Modify: `api-service/app/services/execution_evidence_outcome.py`
- Modify: `api-service/app/services/mimo_ota/path_loss_application.py` only if a public pure validator is required
- Modify: `api-service/tests/test_p2_61_channel_emulator_certification.py`

**Step 1: Write failing tests**

构造同一真实 completed execution，逐项变异：wrong connection/Lab/model/adapter/binding/plan/asset、Mock、terminal v1/v2、identity/options 缺失或漂移、receipt 缺失/unknown/unavailable/rejected/串 execution/session/lease/instrument、频率未完整验证、level 未 confirmed、path-loss 非 real/applied/verified、SAFE_IDLE/release 不完整。覆盖 DB 异常与任一验证错误全 rollback、revoke 审计保留 source proof。

**Step 2: Verify RED**

Run: P2-61 targeted `-k 'activate or revoke or proof or rollback'`。

Expected: FAIL，派生服务不存在。

**Step 3: Minimal GREEN**

抽取 P2-60 CE terminal/receipt 的公共纯 validator，按 execution → category/LabProfile → connection 锁序派生八类 proofs 和摘要。请求只提供 source execution/actor/reason；不连接仪器、不调用 SCPI、不接受客户端 proof。成功一次 commit，错误 rollback。

**Step 4: Verify GREEN and commit**

运行 P2-61、P2-60、P2-66 相关回归；提交 Task 3。

### Task 4：execution-scoped CE qualification 与所有冻结入口

**Files:**
- Modify: `api-service/app/services/channel_emulator_certification.py`
- Modify: `api-service/app/services/test_case_runner.py`
- Modify: `api-service/app/api/commissioning.py`
- Modify: `api-service/tests/test_p2_61_channel_emulator_certification.py`
- Modify relevant commissioning freeze tests

**Step 1: Write failing tests**

覆盖 runner 与五类 commissioning 入口都在 binding/plan 后、首个 I/O 前冻结；第一次无 cert diagnostic；显式 diagnostic 永不提升；active exact-scope cert formal；revoked、binding/plan/asset/model/firmware/serial/options 漂移 diagnostic；自动 diagnostic 冻结执行者与服务器原因；已有冻结件幂等，部分/篡改/已有进度拒绝；认证变化不改变旧 execution。

**Step 2: Verify RED**

Run P2-61 targeted plus runner/commissioning freeze tests。

Expected: FAIL，CE qualification 尚未冻结。

**Step 3: Minimal GREEN**

实现 `ChannelEmulatorExecutionQualification` 与 freeze/validate/classification helper；统一插入正式 runner 和 `_freeze_instrument_lease`。只读本次 frozen binding/plan/identity 与当前 connection certification，写入 immutable envelope；所有入口共享同一 helper。

**Step 4: Verify GREEN and commit**

运行相关冻结/commissioning 回归与 diff-check；提交 Task 4。

### Task 5：P2-66 合并正式门与历史兼容

**Files:**
- Modify: `api-service/app/services/execution_evidence_outcome.py`
- Modify: `api-service/tests/test_p2_61_channel_emulator_certification.py`
- Modify: `api-service/tests/test_p2_66_execution_evidence_outcome.py`
- Modify affected report/history/download tests only when RED proves required

**Step 1: Write failing tests**

覆盖 explicit CE diagnostic → `diagnostic_completed`、formal exact scope → `valid_test_completed`；qualification/certification/identity/digest 篡改 → invalid；completed operation chain 不能越过 missing/revoked cert；current certification 变化不追溯；pre-P2-61 仍 legacy；terminal v1/v2 可读但新 certification 不适用；history/report/download/JSONL/重建全消费同一 outcome。

**Step 2: Verify RED**

Run P2-61/P2-66/report/history targeted tests。

Expected: FAIL，现有 outcome 不认识 CE qualification。

**Step 3: Minimal GREEN**

纯解析 CE qualification 并与 frozen binding/plan/asset/terminal v3/receipts 对齐；最终 formal eligibility 同时要求 BS 与 CE formal。无 CE qualification 保持精确 legacy；消费者不加厂商特判。

**Step 4: Verify GREEN and commit**

运行 affected chain；提交 Task 5。

### Task 6：专用 API、readiness 与 GUI 服务器投影

**Files:**
- Modify: `api-service/app/schemas/instrument.py`
- Modify: `api-service/app/api/instrument.py`
- Modify: `api/openapi.yaml`
- Modify: `gui/src/types/api.generated.ts`
- Modify: `gui/src/types/api.ts`
- Modify: `gui/src/api/service.ts`
- Modify: `gui/src/App.tsx`
- Modify: `gui/src/features/Dashboard/ZoneReadiness.tsx`
- Modify: `gui/src/api/mockDatabase.ts`
- Create: `gui/src/types/channelEmulatorCertification.test.ts`
- Modify: `api-service/tests/test_p2_61_channel_emulator_certification.py`

**Step 1: Write failing tests**

后端断言专用 certify/revoke API、404/422、普通 PUT 不可写、readiness 只给 server preview；GUI 断言 CE 抽屉可认证/撤销，Dashboard/TestCase 只消费 server status/reasons，diagnostic 明示 UNKNOWN/N/A，Mock 不呈绿色；四镜像完整。

**Step 2: Verify RED**

Run backend API/OpenAPI tests and Node targeted test。

Expected: FAIL，路由/字段/控件不存在。

**Step 3: Minimal GREEN**

新增 CE dedicated endpoints 与 `ChannelEmulatorCertificationPreview`；catalog/readiness 返回共同投影。GUI 仅渲染和提交 source execution/actor/reason，不重算 digest/scope。重新生成 `api.generated.ts`，同步 mock fixture。

**Step 4: Verify GREEN and commit**

运行 API/GUI tests 与 production build；提交 Task 6。

### Task 7：生产路径门、roadmap 与完整验证

**Files:**
- Modify: `api-service/tests/test_rule_gates.py`
- Modify: `docs/roadmap-first-call.md`
- Modify only regressions proven by failing tests

**Step 1: Add rule gates**

门控：新 execution 所有冻结入口都调用 CE qualification；普通 connection/API/client/env/rollout bool 无 certification 写入口；Mock/simulated 不可 active/formal；terminal 新 writer v3 且 v1/v2 fixture 保持；正式消费者无厂商 certification 分支；identity projector 不执行 I/O/不新增 SCPI。

**Step 2: Run affected regressions**

至少覆盖 P2-57～P2-61、P2-66/P2-67、runner、五类 commissioning、measure/frequency/path-loss、session/lease/receipts、report/history/download/JSONL、instrument API/readiness 与 rule gates。

**Step 3: Run full verification**

- 全后端 pytest；
- GUI 契约与 production build；
- `compileall`；
- 单一 Alembic head；
- base-to-HEAD/working `git diff --check`；
- 核实仅含本片受控文件，`api-service/.venv`/`gui/node_modules` 未提交。

**Step 4: Fresh single-agent functional review**

按 AGENTS.md 枚举认证写入口、冻结入口、正式消费者、历史/重建/下载与成功/拒绝/异常/取消/撤销/换机对称路径；重点检查 current state 补真、Mock 洗白、operation success 冒充 field confirmation、SAFE_IDLE/release 代价方向。功能 P1 必须为 0。

**Step 5: Finish branch**

提交、推送、开 Ready PR，走 Codex R1 → R2；R1 处理功能 P1 与本片内 P2，覆盖最新 HEAD 的 R2 无 P1且 mergeable/checks 通过或无必需 checks 才合并。R2 仍有 P1 则继续 P1-only 到最新 HEAD 无 P1；R2+ P2/P3 只报告、不阻塞、不自动积压。

**Step 6: Post-merge**

fetch 验证 origin/main，本地主目录 ff-only 同步并保留未跟踪仪器资料；运行 migration，确认旧 connection certification 为 null；不执行现场认证。清理 worktree/本地分支后才开始 P2-62。
