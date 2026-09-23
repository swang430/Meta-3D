# P2-32B 探头方向图真实入口闭环实施计划

> **For Codex:** 按 `executing-plans` 与 `test-driven-development` 逐任务执行；每个生产改动必须先有
> 能在旧实现上失败的行为测试。严格 WIP=1，不启动 P2-32C 或其他 feature。

**Goal:** 把已有 CE+SA+positioner 方向图真实服务接入生产 API/GUI，冻结并验证 LabProfile RF
路由，让来源、warning 和正式消费语义在数据库、报告与前端形成同一闭环。

**Architecture:** API 只调用 `PatternCalibrationService`。Real 由服务在首次 I/O 前通过
`resolve_rf_chains` 一次性解析全部 requested `(probe, polarization)`，并把冻结身份与 warning
写入每条 `ProbePattern`。厂商导入方向图保持 route-independent；现场实测方向图只有在当前
LabProfile/Topology/chain/CE-port 与冻结值一致时才可被正式执行消费。GUI 只提交显式模式和
操作员参数，不允许手填硬件端口，也不重算服务器 verdict。

**Spec:** `docs/plans/2026-09-23-p2-32b-pattern-real-activation-design.md`

## 全局约束

- 不新增、修改或盲试任何 SCPI。
- Real 必须显式冻结来自有效链路/路损校准的 `chain_correction_db`；缺失时在首次硬件 I/O 前
  fail-closed，不能让相对方向图峰值进入正式增益补偿。
- 模拟、历史未知和 route drift 结果不得进入正式 KPI、补偿或报告 PASS 分母。
- `vendor_datasheet` 方向图不绑定现场路由，不能因新增字段被误拒。
- API 省略 `use_mock` 的兼容默认值保持 `true`；GUI 必须显式发送。
- 真实失败不得 fallback Mock；cleanup warning 不得只沉日志。
- Real 的 CE、SA、positioner、switch 与 signal source 任一为 Mock 时，必须在首次硬件动作前拒绝。
- P2-32C 静区保持 Hardware Blocked。

---

### Task 1：ProbePattern 来源、路由与 warning 数据库真值

**Files:**

- Modify: `api-service/app/models/probe_calibration.py`
- Modify: `api-service/app/schemas/probe_calibration.py`
- Create: `api-service/alembic/versions/<revision>_probe_pattern_execution_provenance.py`
- Test: `api-service/tests/test_p2_32b_pattern_real_activation.py`
- Test: `api-service/tests/test_probe_calibration_models.py`
- Test: `api-service/tests/test_probe_calibration_schemas.py`

**Step 1: 写 RED**

覆盖：

- `ProbePattern` 可持久化 `warnings/lab_profile_id/operating_mode/topology_id/chain_id/ce_port`；
- `PatternCalibrationResponse` 原样投影这些字段；
- `StartPatternCalibrationRequest` 接收
  `lab_profile_id/operating_mode/use_mock/ce_tx_power_dbm/sgh_gain_dbi/chain_correction_db`；
- `use_mock` 省略时仍为 `true`；
- warnings 历史 NULL 与新空列表语义可区分。

先运行新测试并确认因字段不存在而 RED。

**Step 2: 最小 GREEN**

增加 nullable 模型字段与方言无关 Alembic 迁移，revision 连接当前唯一 head
`a8c1e3f5b7d9`。新写入由服务显式传列表，不给数据库 server default，保留历史 NULL。

**Step 3: 验证迁移形状**

运行模型/schema 定点测试、`alembic heads`，并在隔离测试数据库执行 upgrade。

**Step 4: 提交**

Commit message: `feat: persist probe pattern execution provenance`

---

### Task 2：真实服务冻结 LabProfile 路由并在 I/O 前 fail-closed

**Files:**

- Modify: `api-service/app/services/probe_calibration_service.py`
- Reuse: `api-service/app/services/calibration/rf_chain_resolver.py`
- Reuse: `api-service/app/services/path_loss_calibration_service.py`
- Test: `api-service/tests/test_p2_32b_pattern_real_activation.py`
- Test: `api-service/tests/test_probe_pattern_real.py`
- Test: `api-service/tests/test_p2_30_task_level_lease.py`

**Step 1: 写路由全集 RED**

在旧实现上证明以下反例会被错误放行或无法表达：

- LabProfile 不存在、无 chamber、request chamber 漂移；
- topology 缺失/无 ID；
- requested probe/polarization 为 0 条或多条链；
- chain ID、CE port 缺失或 `?`；
- 两个 probe/polarization 解析为不同 chain 时，各自必须收到自己的 `ce_port/route_target`；
- 任何路由错误发生在 positioner/CE/SA 首次调用之前。

对核心保护做最小变异：绕过 resolver 或删掉 route_target 后新测试必须红。

**Step 2: 最小 GREEN**

给 `execute_pattern_calibration` 增加 `lab_profile_id/operating_mode`。Real 在生成角度网格后、获取
仪器前一次性调用 `resolve_rf_chains`，建立 `(probe_id, polarization) -> RFChainSpec` 严格映射。
Mock 不访问真实 resolver/I/O，但仍保存请求 LabProfile 上下文。

把冻结 `ce_port/chain_id` 传入 `_real_pattern_measurements`，后者在每次 CE+SA acquire 中传
`route_target=chain_id`。不得从 GUI 或 request 直接接收端口。

**Step 3: warning 与事务**

每个 `(probe, polarization)` 使用独立 warning 列表并写对应行；作业响应汇总。若任一测量失败，
rollback 本次作业的全部新行，不能留下半套“有效”方向图。cleanup warning 保持成功+警告语义。

**Step 4: 回归**

运行真实方向图、租约、route resolver 与新定点测试；确认既有 Mock 服务测试仍通过。

**Step 5: 提交**

Commit message: `feat: freeze RF routes for real pattern scans`

---

### Task 3：正式消费和报告按来源及路由 fail-closed

**Files:**

- Modify: `api-service/app/services/probe_pattern/consumer.py`
- Modify: `api-service/app/services/mimo_ota/executors/precheck.py`
- Modify: `api-service/app/services/mimo_ota/executors/measure.py`
- Modify: `api-service/app/services/calibration_report_generator.py`
- Test: `api-service/tests/test_p2_32b_pattern_real_activation.py`
- Test: `api-service/tests/test_p1_60_execution_truth_alignment.py`
- Test: relevant calibration report tests found by `rg 'probe_calibration.*pattern|pattern_data' api-service/tests`

**Step 1: 写消费端 RED**

覆盖：

- `vendor_datasheet + use_mock=false` 在 chamber/frequency/source/有效期合法时继续可用；
- `simulated`、`use_mock=true`、`use_mock=NULL` 不可正式消费；
- 新 `in_chamber_measured` 完整路由且与当前解析一致时可用；
- 缺任一冻结字段、LabProfile/topology/chain/CE-port 漂移时不可用；
- MIMO MEASURE 与 PRECHECK 都传同一 execution LabProfile/operating mode；
- 报告方向图行 `validation_pass=null`，不进入 passed/failed 分母；
- warning、source 和路由身份进入 JSON/PDF 数据投影。

**Step 2: 最小 GREEN**

扩展 consumer 的权威查询接口，显式接收 `lab_profile_id/operating_mode`。只对
`in_chamber_measured` 重解析路由；厂商导入不伪造 route identity。调用方从当前 execution
context 传值，不查询全局/可变“当前 LabProfile”。

报告的 pattern verdict 改为恒 `None`；状态/有效期仍作为审计字段显示，不再等价为 PASS。

**Step 3: 对称路径复核**

用 `rg` 重新枚举 `get_probe_gain_at_azimuth`、`estimate_quiet_zone_ripple_db`、`ProbePattern` 的
全部生产消费方，逐项记录“已改/route-independent/历史只读”。

**Step 4: 提交**

Commit message: `fix: gate pattern consumption on frozen provenance`

---

### Task 4：API 唯一调用权威服务，删除随机生产实现

**Files:**

- Modify: `api-service/app/api/probe_calibration.py`
- Test: `api-service/tests/test_probe_calibration_api.py`
- Test: `api-service/tests/test_probe_calibration_integration.py`
- Test: `api-service/tests/test_p2_32b_pattern_real_activation.py`
- Modify: `api-service/tests/test_rule_gates.py` only if a narrow production-path gate is required

**Step 1: 写 API RED**

断言：

- `/pattern/start` 精确 await `PatternCalibrationService.execute_pattern_calibration`；
- request 的 LabProfile、chamber、mode、probe/polarization、扫描参数和 Real/Mock 原样到达服务；
- 成功响应回填 `use_mock/warnings/calibration_job_id`；
- 服务失败返回结构化 `message/warnings`，不创建随机记录、不 fallback；
- API 生产 handler 不再包含 `random.*` 或独立方向图计算。

**Step 2: 最小 GREEN**

删除 handler 内的角度网格、随机增益、HPBW/FtB 生成和直接落库，改为调用权威服务。
`_require_chamber_probe_ids` 保持在 API 边界，服务仍做自己的安全校验。

**Step 3: 规则门**

若增加门，只保护“start API 不能重新生成数据且必须调用 service”这一功能边界；不得把测试门
加强扩成新的阻塞项。

**Step 4: 提交**

Commit message: `fix: route pattern start through authoritative service`

---

### Task 5：GUI 方向图测量工作单元

**Files:**

- Create: `gui/src/features/ProbeCalibration/components/PatternMeasurementPanel.tsx`
- Create: `gui/src/features/ProbeCalibration/patternMeasurement.ts`
- Modify: `gui/src/features/ProbeCalibration/components/index.ts`
- Modify: `gui/src/features/ProbeCalibration/ProbeCalibrationPage.tsx`
- Modify: `gui/src/features/ProbeCalibration/components/ProbeCalibrationDashboard.tsx`
- Modify: `gui/src/api/probeCalibrationService.ts`
- Modify: `gui/src/hooks/useProbeCalibration.ts`
- Modify: `gui/src/types/probeCalibration.ts`
- Test: add focused Vitest files next to the pure request builder/panel

**Step 1: 写纯请求构造 RED**

覆盖：无 OperationalLab/chamber、mode=null、Real 缺链路修正、空/重复/负数/非整数/out-of-range
probe、非法频率或扫描步进不发请求；合法输入只写服务器契约字段，绝不包含
`ce_port/chain_id`。

响应断言必须拒绝 `use_mock` 缺失、与请求不一致或非 completed 状态。

**Step 2: 最小 GREEN**

实现纯 builder/assertion 和 `PatternMeasurementPanel`。Real/Mock 初始为空；Real 显示硬件动作警示，
Mock 显示诊断/不判绿说明。成功只显示完成来源、记录/warnings/采样信息。

**Step 3: 接入唯一界面**

Probe Calibration 新增“方向图测量” tab；Dashboard Pattern action 切换到同一 tab，不创建第二份
表单或请求状态。保留“Pattern 导入”作为厂商数据路径。

**Step 4: 验证与提交**

运行 focused GUI tests 和 production build。

Commit message: `feat: add explicit real pattern calibration workflow`

---

### Task 6：OpenAPI 四镜像与路线图事实

**Files:**

- Modify: live FastAPI schema through Pydantic models
- Modify: `api/openapi.yaml`
- Regenerate: `gui/src/types/api.generated.ts`
- Modify: `gui/src/types/probeCalibration.ts`
- Modify: `docs/roadmap-first-call.md`
- Test: relevant OpenAPI mirror/type-contract/rule-gate tests

**Step 1: 写镜像 RED**

断言 request/response/pattern row 新字段在 live OpenAPI、checked YAML、generated TS 和手写类型中
同名同可空性；`/pattern/start` 仍是唯一 start 路由。

**Step 2: 同步四镜像**

按仓库现有生成命令更新 YAML 与 generated TS，不手改 generated 文件。检查 request 方向
manual→live、response 方向 live→manual 的类型安全。

**Step 3: 更新 roadmap**

只在实现和验证完成后将 P2-32B 标记软件片已交付，写明真实硬件验收仍未由本地测试替代；
P2-32C 保持 Hardware Blocked。

**Step 4: 提交**

Commit message: `docs: publish pattern calibration production contract`

---

### Task 7：全验证、fresh 内审与交付

**Step 1: 受影响链**

运行：

- P2-32B 定点、ProbePattern real/service/API/model/schema/integration；
- MIMO precheck/measure、P1-60 consumer、calibration report；
- OpenAPI/type/rule gates；
- GUI focused contract tests 与 production build。

**Step 2: 全量门**

运行全后端、`compileall`、单一 Alembic head、迁移 upgrade、base-to-HEAD diff-check 和 clean status。

**Step 3: 核心变异**

至少实跑两条：

1. 绕过 RF resolver/route_target 后真实方向图测试必须红；
2. 把 simulated 或 route-drift pattern 放回正式 consumer/report 分母后测试必须红。

**Step 4: Fresh 独立功能内审**

按 AGENTS.md 检查功能 P1/P2/P3；P1 最小 TDD 修复并复审至 P1=0。测试门建议最高 P2，
不得用“继续加强测试”制造无穷回归。

**Step 5: Ready PR 与 Codex 外审**

推送并开 Ready PR。R1 处理功能 P1 与本片内 P2；触发覆盖最新 HEAD 的 R2。R2 无 P1 且
mergeable/checks 通过或无必需 checks 时立即 merge；若仍有 P1，修复后继续 latest-head
P1-only 外审。R2+ P2/P3 只报告，不阻塞、不自动积压。

**Step 6: 合并同步清理**

fetch 验证 origin/main，主目录 `git merge --ff-only origin/main`，执行新 Alembic migration，
保留未跟踪仪器资料，清理本 worktree/本地分支。P2-32C 不自动启动。
