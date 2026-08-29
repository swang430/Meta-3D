# P2-46 BaseStation Capability Manifest v2 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 将 BaseStation 的 RAT、配置字段、Attach 阶段、测量窗口和指标能力收敛为单一结构化 manifest，消除 UXM/CMW500 声明与运行时分叉，并保持 CMW500 profile v1 兼容。

**Architecture:** 扩展现有 P2-44 `BaseStationAdapterManifest`，不新建 registry 或数据库真值。manifest v2 是唯一静态能力源，旧 `rats/capabilities` 由结构化字段派生；real driver 的技术访问器和兼容 class var 受 registry 一致性校验。公开 API/GUI 同步新结构，profile envelope 使用独立 `profile_schema_version`。

**Tech Stack:** Python 3.13、Pydantic v2、FastAPI、React 18、TypeScript、OpenAPI、pytest、Node test、Vite。

---

## Task 1：定义 Manifest v2 严格结构与派生镜像

**Files:**

- Modify: `api-service/app/hal/base_station_manifest.py`
- Create: `api-service/tests/test_p2_46_base_station_capability_manifest.py`
- Modify: `api-service/tests/test_p2_44_base_station_manifest.py`

**Step 1: Write the failing test**

写 RED 锁定以下合同：

- `schema_version=2` 与 `profile_schema_version` 分离；required profile 必须有正整数 profile version，
  not-applicable 必须为 null；
- `rat_capabilities` 只接受 `lte|nr5g`；legacy `rats` 精确从它派生，显式矛盾被拒绝；
- `operations` 精确派生 legacy `capabilities`；
- `config_fields` 必须覆盖 `dataclasses.fields(BaseStationRequestedConfig)` 的全部字段且唯一；
- Attach stage 精确覆盖四个稳定阶段；measurement 的 scope/metric key 唯一；
- authoritative 声明必须有非空 `source_reference`，diagnostic/unavailable 不得伪装 authoritative。

示例断言：

```python
assert manifest.rats == tuple(item.rat for item in manifest.rat_capabilities)
assert {item.field for item in manifest.config_fields} == {
    field.name for field in dataclasses.fields(BaseStationRequestedConfig)
}
with pytest.raises(ValidationError, match="legacy rats mirror"):
    BaseStationAdapterManifest.model_validate({**payload, "rats": ["lte"]})
```

**Step 2: Run test to verify it fails**

```bash
cd api-service
./.venv/bin/python -m pytest -q \
  tests/test_p2_46_base_station_capability_manifest.py \
  tests/test_p2_44_base_station_manifest.py
```

Expected: FAIL，因为 v2 nested models 与 profile version 尚不存在。

**Step 3: Write minimal implementation**

在 `base_station_manifest.py` 增加 frozen Pydantic models：

- `BaseStationRatCapability`
- `BaseStationConfigFieldCapability`
- `BaseStationAttachStageCapability`
- `BaseStationMetricCapability`
- `BaseStationMeasurementCapability`

使用 `model_validator(mode="before")` 在调用方未给 legacy mirrors 时派生 `rats/capabilities`，再在
after validator 精确复核。只允许设计稿列出的 enum/token，不解释仪器命令。

**Step 4: Run tests to verify they pass**

重复 Task 1 命令；再运行 `tests/test_p2_43_base_station_receipts.py`，确保 receipt 不受影响。

**Step 5: Commit**

```bash
git add api-service/app/hal/base_station_manifest.py \
  api-service/tests/test_p2_46_base_station_capability_manifest.py \
  api-service/tests/test_p2_44_base_station_manifest.py
git commit -m "feat: define base station capability manifest v2"
```

## Task 2：迁移 CMW500/UXM 声明并统一 RAT 真值

**Files:**

- Modify: `api-service/app/hal/base_station.py`
- Modify: `api-service/app/hal/cmw500_base_station.py`
- Modify: `api-service/app/hal/uxm_base_station.py`
- Modify: `api-service/tests/test_p2_46_base_station_capability_manifest.py`
- Modify: `api-service/tests/test_p1_73a_base_station_contract.py`
- Modify: `api-service/tests/test_p2_43_base_station_adapter_certification.py`

**Step 1: Write the failing tests**

RED 覆盖：

- CMW500 structured RAT 仅 LTE；UXM 仅 NR5G；
- `get_supported_technologies()` 对 real driver 从 manifest 派生，不再由各厂商覆写另一份列表；
- CMW 配置字段、Attach、PCC 单窗口与 DL throughput/BLER 声明精确反映现有实现；
- UXM adapter 级声明只取全部可选 Test App 方言的有出处保守交集；IRAT 专属 MAC/RRC/clear-read
  指标不冒充整机无条件能力，只有 IRAT 具备受控出处的配置下发/回读也不静态声明为整机权威能力；
  当前 profile 的运行时能力与 receipt 仍由命令全集和真实回读派生；
- 诊断原始 RSRP/SINR 不声明工程单位或 formal eligibility；
- 没有任何新 SCPI 字面量。

**Step 2: Verify RED**

运行 P2-46、P1-73A contract 和 P2-43 certification 定点测试，确认旧 manifest 形状和 UXM LTE 声明
导致失败。

**Step 3: Minimal GREEN**

- 两家 `adapter_manifest` 改为 v2；复用相邻已有手册 source reference，不新增命令；
- `BaseStationDriver.get_supported_technologies()` 规范地把 manifest RAT 映射成 `RadioTechnology`；
- 删除 real UXM/CMW 的重复覆写；Mock 保留明确模拟支持列表；
- 不改 `get_capabilities()` 瞬时监控输出。

**Step 4: Verify GREEN**

运行 Task 2 全部定点测试及 CMW/UXM 配置测试。

**Step 5: Commit**

```bash
git add api-service/app/hal/base_station.py \
  api-service/app/hal/cmw500_base_station.py \
  api-service/app/hal/uxm_base_station.py \
  api-service/tests/test_p2_46_base_station_capability_manifest.py \
  api-service/tests/test_p1_73a_base_station_contract.py \
  api-service/tests/test_p2_43_base_station_adapter_certification.py
git commit -m "feat: declare cmw and uxm structured capabilities"
```

## Task 3：让 Registry 拒绝能力镜像分叉

**Files:**

- Modify: `api-service/app/hal/base_station_manifest.py`
- Modify: `api-service/app/services/instrument_hal_service.py`
- Modify: `api-service/tests/test_p2_44_base_station_manifest.py`
- Modify: `api-service/tests/test_p2_46_base_station_capability_manifest.py`
- Modify: `api-service/tests/test_instrument_catalog_model_capabilities.py`

**Step 1: Write the failing tests**

构造 fake 第三 adapter，逐项变异：

- RAT mirror 与 structured RAT 不同；
- input-level/RRC/MAC class var 与 operation/config 声明不同；
- measurement cardinality 与 manifest 不同；
- required profile version/model 缺失；
- adapter/model/manifest identity 分叉。

每种必须在 registration validation fail-loud；合法第三 adapter 应无需修改 registry 生产代码即可注册。

**Step 2: Verify RED**

运行 manifest/catalog 测试，确认当前 registry 不检查这些镜像。

**Step 3: Minimal GREEN**

扩展 `validate_base_station_adapter_registrations()`：只比较可本地确定的静态合同，不实例化 driver、
不 connect、不调用 `get_capabilities()`。错误消息指出 model + 分叉字段。

**Step 4: Verify GREEN**

运行 Task 3 测试与 P2-44 binding resolver 相关测试。

**Step 5: Commit**

```bash
git add api-service/app/hal/base_station_manifest.py \
  api-service/app/services/instrument_hal_service.py \
  api-service/tests/test_p2_44_base_station_manifest.py \
  api-service/tests/test_p2_46_base_station_capability_manifest.py \
  api-service/tests/test_instrument_catalog_model_capabilities.py
git commit -m "fix: reject base station capability drift"
```

## Task 4：分离 GUI Profile Schema 版本并展示结构化能力

**Files:**

- Modify: `gui/src/types/baseStationManifest.ts`
- Modify: `gui/src/types/baseStationManifest.test.ts`
- Modify: `gui/src/App.tsx`
- Create: `gui/src/types/baseStationCapabilityManifest.test.ts`

**Step 1: Write the failing tests**

RED 锁定：

- manifest v2 + `profile_schema_version=1` 能读取/构造现有 CMW profile v1；
- helper 不再用 manifest version 作为 profile envelope version；
- not-applicable adapter 必须 profile version null，不能构造 profile；
- fake 第三 adapter 的 RAT/Attach/window/metric 能由通用 helper 投影，不按型号分支；
- diagnostic-only/unavailable 使用黄色/灰色语义，不能显示成正式绿色。

**Step 2: Verify RED**

```bash
cd gui
node --test src/types/baseStationManifest.test.ts \
  src/types/baseStationCapabilityManifest.test.ts
```

Expected: FAIL，旧 helper 仍把 `schema_version` 写入 profile。

**Step 3: Minimal GREEN**

- 更新 TS manifest/nested types；
- `readBaseStationProfileDraft()` / `buildBaseStationAdapterProfile()` 改读 `profile_schema_version`；
- 增加纯函数投影结构化能力，App 只用通用分组显示，不产生 readiness/formal 授权；
- 不增加任何 UXM/CMW 字符串分支。

**Step 4: Verify GREEN**

运行 Task 4 Node tests 与既有 binding/qualification GUI 契约。

**Step 5: Commit**

```bash
git add gui/src/types/baseStationManifest.ts \
  gui/src/types/baseStationManifest.test.ts \
  gui/src/types/baseStationCapabilityManifest.test.ts gui/src/App.tsx
git commit -m "feat: render structured base station capabilities"
```

## Task 5：同步 OpenAPI、Generated TS 与手写类型

**Files:**

- Modify: `api/openapi.yaml`
- Modify: `gui/src/types/api.generated.ts`（生成）
- Modify: `gui/src/types/api.ts`
- Create: `api-service/tests/test_p2_46_openapi_contract.py`
- Modify: `gui/src/types/baseStationBindingApiTruth.test.ts`

**Step 1: Write the failing tests**

列出 live OpenAPI、checked-in YAML、generated TS、手写 TS 的 manifest v2/nested schema/profile version 全集；
RED 要求字段 required/nullable/enum 一致，legacy mirrors 仍必出。

**Step 2: Verify RED**

运行后端 OpenAPI test 与 GUI API truth test，确认三镜像尚未同步。

**Step 3: Minimal GREEN**

更新 checked-in schema，然后运行：

```bash
cd gui
npm run openapi:generate
```

不得手改 generated TS 代替生成。

**Step 4: Verify GREEN**

运行 OpenAPI/GUI contract tests 与 `npm run build`。

**Step 5: Commit**

```bash
git add api/openapi.yaml gui/src/types/api.generated.ts gui/src/types/api.ts \
  api-service/tests/test_p2_46_openapi_contract.py \
  gui/src/types/baseStationBindingApiTruth.test.ts
git commit -m "chore: sync base station capability API mirrors"
```

## Task 6：生产路径门与 Roadmap 实施状态

**Files:**

- Create: `api-service/tests/test_p2_46_single_capability_truth.py`
- Modify: `api-service/tests/test_rule_gates.py`
- Modify: `docs/roadmap-first-call.md`

**Step 1: Write the failing test**

RED 锁定：

- real driver 不得覆写 `get_supported_technologies()`；
- production GUI/API/MEASURE 不得新增厂商能力判断；
- manifest legacy mirror 只能在 manifest model 内派生；
- `schema_version` 不得再被 GUI 当 profile schema；
- 每个注册 adapter 都通过 structured capability validation。

测试/门发现严重度遵循 AGENTS.md，上限 P2。

**Step 2: Verify RED**

在残余镜像/旧 GUI profile version 尚存在时确认门失败。

**Step 3: Minimal GREEN**

清掉真正残余重复真值，保留明确的兼容读取；更新 P2-46 实施状态，不提前标 P2-47 或现场项完成。

**Step 4: Verify GREEN**

运行新门、全部 rule gates、base-to-HEAD diff-check。

**Step 5: Commit**

```bash
git add api-service/tests/test_p2_46_single_capability_truth.py \
  api-service/tests/test_rule_gates.py docs/roadmap-first-call.md
git commit -m "test: lock base station capability truth"
```

## Task 7：完整验证、Fresh 内审与 PR 收口

**Step 1: Focused regression**

运行 P2-46、P2-44 manifest/binding/catalog/OpenAPI/GUI、P2-43 receipts/certification、P1-73 config/
readiness、P2-45 qualification 与 rule gates。

**Step 2: Full regression and build**

```bash
cd api-service
./.venv/bin/python -m pytest -q
./.venv/bin/python -m compileall -q app
./.venv/bin/alembic heads
cd ../gui
node --test src/types/baseStationManifest.test.ts \
  src/types/baseStationCapabilityManifest.test.ts \
  src/types/baseStationBindingApiTruth.test.ts
npm run build
```

运行 base-to-HEAD diff-check；确认恰好一个 Alembic head且本片无迁移。

**Step 3: AGENTS.md 0.5 mirror search**

全仓再次搜索 `rats`、`capabilities`、`get_supported_technologies`、三个 capability class var、
`measurement_window_cardinality`、manifest/profile `schema_version`、OpenAPI 与 GUI 消费方，逐条确认。

**Step 4: Fresh independent functional review**

按 AGENTS.md 分“功能缺陷”与“非缺陷建议”，P1/P2/P3 分栏；测试发现上限 P2。功能 P1 收口到 0，
必要修复继续严格 RED→GREEN 并重跑受影响链。

**Step 5: Ready PR and external review**

推送并创建 Ready PR，声明 `Roadmap: P2-46`、可观察故障、无新 SCPI/迁移/正式白名单变化和完整验证。
触发 Codex R1；处理本片功能 P1 与本片内 P2 后触发 R2。覆盖最新 HEAD 的 R2 无 P1且 PR
mergeable/checks通过或无必需checks时 merge commit；R2 若仍有 P1则继续最小修复与 P1-only 外审，
直到覆盖最新 HEAD 无 P1。R2+ P2/P3 只报告、不阻塞、不自动积压。

**Step 6: Merge, sync, cleanup, continue**

fetch 验证 origin/main；主目录 `git merge --ff-only origin/main`，保留未跟踪仪器资料；清理 P2-46
worktree/本地分支后，才从最新 main 建 P2-47 独立 worktree，复用同一流程。P2-47～P2-53 全部完成
前不得自动开始其它 feature 或把现场复验标完成。
