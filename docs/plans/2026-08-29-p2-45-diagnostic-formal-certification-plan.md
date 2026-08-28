# P2-45 Diagnostic / Formal 与 BaseStation 现场认证实施计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 让无校准硬件打通成为服务器审计的 Diagnostic execution，并让 BaseStation 只有经真实 execution evidence 认证后才能成为 Formal candidate；诊断值在所有正式消费者中保持 UNKNOWN/N/A。

**Architecture:** TestCase 专用 `execution_policy` 与 InstrumentConnection 专用 `base_station_site_certification` 是当前服务器状态；统一 qualification service 在 execution 创建时冻结 policy、P2-44 binding 和 certification。PRECHECK/MEASURE/ANALYSIS/REPORT 及全部报告消费者只读冻结投影；认证只从既有真实 execution evidence 提取，不发仪器命令。

**Tech Stack:** FastAPI、Pydantic v2、SQLAlchemy/Alembic、React 18、TypeScript、OpenAPI、pytest、Node test、Vite。

---

## Task 1：持久化专用 Diagnostic policy 与 Site certification

**Files:**

- Modify: `api-service/app/models/test_plan.py`
- Modify: `api-service/app/models/instrument.py`
- Create: `api-service/alembic/versions/e6a8c0d2f4b6_add_execution_qualification.py`
- Create: `api-service/app/services/execution_qualification.py`
- Create: `api-service/tests/test_p2_45_execution_qualification_models.py`
- Modify: `api-service/tests/test_rule_gates.py`

**Step 1: Write the failing test**

先写 RED 锁定：

- TestCase 只有严格版本化 `formal|diagnostic` policy，diagnostic 必须有非空 operator/reason/server time；
- InstrumentConnection certification 只有严格 `active|revoked` 形状，active 必须绑定 LabProfile、connection、
  binding digest、adapter/model/firmware/options、source execution 与四类 proof；
- JSON projection 不可变、JSON-safe、digest 稳定；畸形显式数据 fail-loud；
- Alembic 只新增两列，旧行 null = formal policy + no certification，不自动晋级；
- 通用 TestCase/InstrumentConnection schema 不出现两个写字段。

**Step 2: Verify RED**

Run:

```bash
cd api-service
./.venv/bin/python -m pytest -q tests/test_p2_45_execution_qualification_models.py
```

Expected: FAIL，原因是列、严格模型与 parser 尚不存在。

**Step 3: Minimal GREEN**

新增 frozen Pydantic 模型、canonical digest、严格 parse helper 和迁移。列只存当前状态；历史由 execution
快照保留。不得给 generic CRUD schema 增加写字段。

**Step 4: Verify GREEN**

Run Task 1、migration helper 与 rule gates。

**Step 5: Commit**

```bash
git add api-service/app/models/test_plan.py api-service/app/models/instrument.py \
  api-service/alembic/versions/e6a8c0d2f4b6_add_execution_qualification.py \
  api-service/app/services/execution_qualification.py \
  api-service/tests/test_p2_45_execution_qualification_models.py \
  api-service/tests/test_rule_gates.py
git commit -m "feat: persist diagnostic and site certification state"
```

## Task 2：实现专用审计端点与真实 Evidence 晋级

**Files:**

- Modify: `api-service/app/api/test_plan.py`
- Modify: `api-service/app/api/instrument.py`
- Modify: `api-service/app/schemas/test_plan.py`
- Modify: `api-service/app/schemas/instrument.py`
- Modify: `api-service/app/services/execution_qualification.py`
- Create: `api-service/tests/test_p2_45_diagnostic_policy_api.py`
- Create: `api-service/tests/test_p2_45_site_certification_api.py`

**Step 1: Write the failing tests**

Policy RED：专用 PUT 记录 TestCase/operator/reason/server time；formal 关闭也审计；通用 POST/PATCH、旧
`precheck_strict_cal=false` 和 env/connection params 不能授权。

Certification RED：从一条真实 completed execution 的 frozen binding + BaseStation identity +
config/route/cleanup/release evidence 可 active；wrong LabProfile/connection/digest、simulated、unknown、旧
attempt、错 config/route、cleanup/release 缺失或执行未完成均 422；客户端提交伪造 identity/proof 字段
被 extra-forbid；撤销记录 operator/reason/server time 且保留原证据。

**Step 2: Verify RED**

Run 两个新 API 测试，确认端点 404/模型缺失，而不是 fixture 错误。

**Step 3: Minimal GREEN**

实现行锁、server timestamp、source execution 严格提取和一次 commit。认证不连接、不发 SCPI。把旧
CMW dedicated approval 保留兼容响应，但不再单独授予 formal qualification。

**Step 4: Verify GREEN**

Run 新测试、P1-73 CMW approval、P2-43 evidence 与 P2-44 binding 回归。

**Step 5: Commit**

```bash
git add api-service/app/api/test_plan.py api-service/app/api/instrument.py \
  api-service/app/schemas/test_plan.py api-service/app/schemas/instrument.py \
  api-service/app/services/execution_qualification.py \
  api-service/tests/test_p2_45_diagnostic_policy_api.py \
  api-service/tests/test_p2_45_site_certification_api.py
git commit -m "feat: audit diagnostic policy and site certification"
```

## Task 3：在五类执行入口冻结同一 Qualification

**Files:**

- Modify: `api-service/app/services/mimo_ota/factory.py`
- Modify: `api-service/app/services/test_case_runner.py`
- Modify: `api-service/app/api/commissioning.py`
- Modify: `api-service/app/services/base_station_adapter_profile.py`
- Modify: `api-service/app/services/execution_qualification.py`
- Create: `api-service/tests/test_p2_45_execution_qualification_freeze.py`
- Modify: `api-service/tests/test_commissioning_strict_gate_overrides.py`
- Modify: `api-service/tests/test_commissioning_adhoc.py`

**Step 1: Write the failing tests**

RED 覆盖 formal runner、commissioning session、saved phase、run-all、adhoc：

- policy、binding、site certification 在 execution 创建时冻结，同一 `qualification_digest`；
- 后续改 policy/撤销认证不改已建 execution，只影响下一次；
- formal policy + active matching cert 才是 formal candidate；missing/revoked/mismatch/mock/diagnostic_unbound
  均为 diagnostic；
- 客户端 `precheck_strict_cal` 不再覆盖；commissioning diagnostic 必填 operator/reason 并落 TestCase；
- adhoc 保持 diagnostic 且不能被 certification 提升。

**Step 2: Verify RED**

Run 新 freeze 测试与既有 commissioning strict override，确认当前仍信任客户端 strict 字段。

**Step 3: Minimal GREEN**

在 BaseStation binding freeze 后调用唯一 qualification freezer；factory 复制服务器 policy。删除
commissioning raw strict override 权限，保留旧字段仅作拒绝/兼容错误说明。所有入口统一派生有效
`precheck_strict_cal`，不复制第二套逻辑。

**Step 4: Verify GREEN**

Run Task 3、P2-42 session、commissioning smoke/e2e/adhoc/run-all 与 formal runner 回归。

**Step 5: Commit**

```bash
git add api-service/app/services/mimo_ota/factory.py \
  api-service/app/services/test_case_runner.py api-service/app/api/commissioning.py \
  api-service/app/services/base_station_adapter_profile.py \
  api-service/app/services/execution_qualification.py \
  api-service/tests/test_p2_45_execution_qualification_freeze.py \
  api-service/tests/test_commissioning_strict_gate_overrides.py \
  api-service/tests/test_commissioning_adhoc.py
git commit -m "feat: freeze execution qualification"
```

## Task 4：在执行与正式消费者中硬隔离 Diagnostic

**Files:**

- Modify: `api-service/app/services/mimo_ota/executors/precheck.py`
- Modify: `api-service/app/services/mimo_ota/executors/measure.py`
- Modify: `api-service/app/services/mimo_ota/executors/reference.py`
- Modify: `api-service/app/services/mimo_ota/executors/analysis.py`
- Modify: `api-service/app/services/mimo_ota/executors/report.py`
- Modify: `api-service/app/services/report_service.py`
- Modify: `api-service/app/services/report_data_collector.py`
- Modify: `api-service/app/api/test_execution.py`
- Create: `api-service/tests/test_p2_45_diagnostic_formal_consumers.py`
- Modify: `api-service/tests/test_mimo_ota_precheck_cal_gate.py`
- Modify: `api-service/tests/test_mimo_ota_report_verified_backcompat.py`

**Step 1: Write the failing tests**

用一条带有限诊断数值的 execution 逐个 RED：PRECHECK 可继续；MEASURE 不应用路径损耗；ANALYSIS
`validation_pass=None`/UNKNOWN；REPORT statistics/正式逐方位值 N/A 且 classification=diagnostic；详情、
重建、下载、比较、ReportDataCollector、execution history 不由旧 flag/current cert 恢复正式值。Formal
fixture 继续通过既有全部独立 trust 门；site cert 不能替代本次证据。

**Step 2: Verify RED**

Run 新消费者测试，确认至少 analysis/report/history 仍只靠旧字段，出现可观察的错误投影。

**Step 3: Minimal GREEN**

新增一个共享 `execution_is_diagnostic()`/strict parser；每个生产消费者在接触数值或判词前调用。报告
保留明确 diagnostic evidence envelope，不把原始诊断数值复制进正式 statistics/table。历史无快照按
既有旧 provenance 兼容，绝不读当前策略/认证反推。

**Step 4: Verify GREEN**

Run Task 4、P1-22/48/54/59/61/63/72/73C 与报告 comparison/download 回归。

**Step 5: Commit**

```bash
git add api-service/app/services/mimo_ota/executors/{precheck,measure,reference,analysis,report}.py \
  api-service/app/services/report_service.py api-service/app/services/report_data_collector.py \
  api-service/app/api/test_execution.py \
  api-service/tests/test_p2_45_diagnostic_formal_consumers.py \
  api-service/tests/test_mimo_ota_precheck_cal_gate.py \
  api-service/tests/test_mimo_ota_report_verified_backcompat.py
git commit -m "fix: keep diagnostic executions out of formal results"
```

## Task 5：Manifest、Readiness、GUI 与 OpenAPI 同步

**Files:**

- Modify: `api-service/app/hal/base_station_manifest.py`
- Modify: `api-service/app/hal/uxm_base_station.py`
- Modify: `api-service/app/hal/cmw500_base_station.py`
- Modify: `api-service/app/services/base_station_binding.py`
- Modify: `api-service/app/services/instrument_hal_service.py`
- Modify: `api-service/app/api/instrument.py`
- Modify: `api/openapi.yaml`
- Modify: `gui/src/types/api.generated.ts`（生成）
- Modify: `gui/src/types/api.ts`
- Modify: `gui/src/types/baseStationManifest.ts`
- Modify: `gui/src/api/service.ts`
- Modify: `gui/src/components/TestCaseConfig/MIMOOTAConfigForm.tsx`
- Modify: `gui/src/components/TestPlanManagement/TestCaseEditModal.tsx`
- Modify: `gui/src/components/Commissioning/sessionBody.ts`
- Modify: `gui/src/components/Commissioning/index.tsx`
- Modify: `gui/src/App.tsx`
- Create: `api-service/tests/test_p2_45_openapi_contract.py`
- Create: `gui/src/types/executionQualification.test.ts`

**Step 1: Write the failing tests**

后端/OpenAPI RED：UXM/CMW manifest 都声明 `site_certification`；readiness/binding/TestCase/execution/
commissioning/report 合同公开严格 qualification/certification；四镜像一致。

GUI RED：TestCase diagnostic 切换必须 operator+reason，黄色展示服务器快照；Formal 只读当前认证；
commissioning 不再发裸 strict flag；Instrument Catalog 认证/撤销请求不携带 identity/proof；diagnostic
execution/report/history 总判不能显示绿色或 PASS/FAIL。

**Step 2: Verify RED**

Run 后端 OpenAPI test 与 GUI Node 契约，确认合同/控件尚缺。

**Step 3: Minimal GREEN**

统一 manifest formal gate；readiness 从共同 binding + certification 派生。实现 GUI 黄色卡片和专用 API
调用，运行 `npm run openapi:generate`，不得手改 generated TS 代替生成。

**Step 4: Verify GREEN**

Run Task 5 后端/GUI 契约与 `npm run build`。

**Step 5: Commit**

```bash
git add api-service/app/hal/base_station_manifest.py \
  api-service/app/hal/uxm_base_station.py api-service/app/hal/cmw500_base_station.py \
  api-service/app/services/base_station_binding.py \
  api-service/app/services/instrument_hal_service.py api-service/app/api/instrument.py \
  api/openapi.yaml gui/src/types/api.generated.ts gui/src/types/api.ts \
  gui/src/types/baseStationManifest.ts gui/src/api/service.ts \
  gui/src/components/TestCaseConfig/MIMOOTAConfigForm.tsx \
  gui/src/components/TestPlanManagement/TestCaseEditModal.tsx \
  gui/src/components/Commissioning/sessionBody.ts gui/src/components/Commissioning/index.tsx \
  gui/src/App.tsx api-service/tests/test_p2_45_openapi_contract.py \
  gui/src/types/executionQualification.test.ts
git commit -m "feat: expose diagnostic and site certification status"
```

## Task 6：生产路径门与 Roadmap 收口

**Files:**

- Modify: `api-service/tests/test_rule_gates.py`
- Create: `api-service/tests/test_p2_45_single_qualification_gate.py`
- Modify: `docs/roadmap-first-call.md`

**Step 1: Write the failing test**

门锁定：

- 生产代码不能从 `precheck_strict_cal`、env、connection params、旧 CMW approval 或 debug inherit 授予
  diagnostic/formal；
- 五类执行入口只能调用唯一 qualification freezer；
- Analysis/report/detail/download/comparison/history 都必须消费冻结 classification；
- UXM/CMW 不新增 vendor-specific certification 消费分支；
- 测试/门发现上限 P2。

**Step 2: Verify RED**

在残余旧入口删除前运行，确认门能命中生产授权路径。

**Step 3: Minimal GREEN**

删除残余客户端 override/旧正式授予，换源到共同 helper。更新 roadmap 的 P2-44 合并事实、P2-45
实施结果和真实统计；保留 NEW-1 与现场认证/复验未完成项，不改历史记录。

**Step 4: Verify GREEN**

Run 新门、全部 rule gates 与 diff-check。

**Step 5: Commit**

```bash
git add api-service/tests/test_rule_gates.py \
  api-service/tests/test_p2_45_single_qualification_gate.py docs/roadmap-first-call.md
git commit -m "test: enforce execution qualification boundary"
```

## Task 7：完整验证、Fresh 内审与 Ready PR

**Step 1: Focused regression**

运行 P2-45 新测试，以及 calibration/precheck/measure/analysis/report、P1-73、P2-42/43/44、
commissioning、history/comparison/download、OpenAPI 与 rule gates 的完整相关清单。

**Step 2: Full validation**

```bash
cd api-service
./.venv/bin/python -m pytest -q
./.venv/bin/python -m compileall -q app tests
./.venv/bin/alembic heads
cd ../gui
npm run build
cd ..
git diff --check origin/main...HEAD
```

确认单一 Alembic head；运行全部适用 GUI Node 契约。

**Step 3: Functional review**

按 AGENTS.md 0.5 重新列 producer/consumer 全集。缺陷与建议分栏；测试发现上限 P2。逐条检查：

- diagnostic 原始数值能否从生成、读取、重建、下载、比较或历史路径恢复正式值；
- current policy/cert 变化能否改写旧 execution；
- site cert 能否从请求值、mock、unknown 或不完整 cleanup/release 晋级；
- 硬件安全门是否仍 fail-loud。

P1=0 后提交尾审修复与真实验证统计。

**Step 4: Ready PR / Codex R1→R2**

推送并开 Ready PR，触发 Codex R1；最小处理本片功能 P1 与本片内 P2，回归/fresh 内审后逐条回复，
触发覆盖最新 HEAD 的 R2。R2 无 P1 且 mergeable/checks 通过或无必需 checks 时立即 merge commit；
若仍有 P1，继续 P1-only 外审到最新 HEAD 无 P1。R2+ P2/P3 只报告、不阻塞、不自动积压。

**Step 5: Merge / sync / cleanup**

fetch 验证 origin/main，在主目录 `git merge --ff-only origin/main`，保留未跟踪仪器资料；删除本片
worktree/本地分支，删除 `todo` 自动化并给出 NEW-1、P2-42～45 整体摘要。不得开始现场项或其他 feature。
