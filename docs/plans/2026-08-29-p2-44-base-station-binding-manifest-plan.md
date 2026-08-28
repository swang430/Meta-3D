# P2-44 BaseStation Binding Resolver 与 Manifest 实施计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 让 BaseStation 保存、LabProfile 同步、readiness/预览与 execution freeze 使用同一个不可变 resolver 结果和 binding digest，并让 adapter profile GUI 由 manifest schema 驱动。

**Architecture:** 保留现有真实 driver registry 和数据库表；每个 BaseStation driver class 声明严格 manifest，唯一 `resolve_base_station_binding()` 解析 catalog、LabProfile、connection、profile 与 loaded driver。API 只序列化 resolver，GUI 只消费 public manifest；兼容 CMW readiness 镜像由共同结果派生。

**Tech Stack:** FastAPI、Pydantic v2、SQLAlchemy、React 18、TypeScript、OpenAPI、pytest、Node test、Vite。

---

## Task 1：定义并注册不可变 Adapter Manifest

**Files:**

- Create: `api-service/app/hal/base_station_manifest.py`
- Modify: `api-service/app/hal/uxm_base_station.py`
- Modify: `api-service/app/hal/cmw500_base_station.py`
- Modify: `api-service/app/services/instrument_hal_service.py`
- Create: `api-service/tests/test_p2_44_base_station_manifest.py`

**Step 1: Write the failing test**

为 public manifest、profile field、内部 registration 写 RED：

- UXM/CMW manifest 的 model、adapter 与 registry key/class 精确一致；
- adapter id 唯一；
- CMW profile required 且公开七个规范字段路径；UXM profile not-applicable；
- 缺 manifest、重复 adapter、非法 RAT/capability/formal gate、字段路径重复立即拒绝；
- public dump 不暴露 Python class 或命令字面量。

**Step 2: Run test to verify it fails**

Run:

```bash
cd api-service
./.venv/bin/python -m pytest -q tests/test_p2_44_base_station_manifest.py
```

Expected: FAIL，原因是 manifest 合同/helper 尚不存在。

**Step 3: Write minimal implementation**

实现 frozen Pydantic models：

- `BaseStationProfileFieldManifest`
- `BaseStationAdapterManifest`
- `BaseStationAdapterRegistration`

给两家真实 driver class 增加 `adapter_manifest`，并让 registry 初始化校验 model/adapter/字段全集。
只声明现有应用能力和资料指针，不增加 SCPI 或动态发现。

**Step 4: Run test to verify it passes**

Run Task 1 测试和既有 registry/catalog 测试。

**Step 5: Commit**

```bash
git add api-service/app/hal/base_station_manifest.py \
  api-service/app/hal/uxm_base_station.py \
  api-service/app/hal/cmw500_base_station.py \
  api-service/app/services/instrument_hal_service.py \
  api-service/tests/test_p2_44_base_station_manifest.py
git commit -m "feat: register base station adapter manifests"
```

## Task 2：建立唯一 ResolvedBaseStationBinding

**Files:**

- Create: `api-service/app/services/base_station_binding.py`
- Modify: `api-service/app/services/base_station_adapter_profile.py`
- Create: `api-service/tests/test_p2_44_base_station_binding_resolver.py`
- Modify: `api-service/tests/test_p1_73b_cmw_adapter_profile.py`

**Step 1: Write the failing test**

先列全 resolver 状态并逐个 RED：

- real CMW/UXM 正确解析相同公共形状；
- configured mock 保留同一 manifest/profile 并标 simulated；
- 两端均空时只有权威 Mock 可得到 `diagnostic_unbound`；
- 缺/错 selected model、重复或缺 binding、重复或缺 connection、endpoint 漂移、profile 缺失/多余、registry/driver/transport 不同源均 fail-loud；
- 相同数据库真值得到稳定 `binding_digest`；修改 profile、endpoint、model 或 approval 必须改变 digest；
- resolver 零 connect/SCPI。

**Step 2: Verify RED**

Run 新 resolver 测试，确认因类型/helper 缺失失败，而不是 fixture 错误。

**Step 3: Minimal GREEN**

实现 frozen `ResolvedBaseStationBinding` 与唯一 `resolve_base_station_binding()`：

- 一次解析 category、单一 binding、model、单一 connection、manifest、profile 与 loaded driver；
- `lock=True` 时维持既有 category → LabProfile/connection 锁顺序；
- `binding_digest` 只覆盖持久化真值和 expected transport；
- runtime driver identity 另存，不污染稳定 digest。

把既有 freeze helper 收窄为 resolver 适配壳，保留旧 freeze schema key 与历史读取合同。

**Step 4: Verify GREEN**

Run resolver、P1-73B profile、P2-42 session 与 freeze 相关测试。

**Step 5: Commit**

```bash
git add api-service/app/services/base_station_binding.py \
  api-service/app/services/base_station_adapter_profile.py \
  api-service/tests/test_p2_44_base_station_binding_resolver.py \
  api-service/tests/test_p1_73b_cmw_adapter_profile.py
git commit -m "refactor: resolve base station binding once"
```

## Task 3：让 Preview、Sync、Readiness 与 Freeze 共享 Digest

**Files:**

- Create: `api-service/app/schemas/base_station_binding.py`
- Modify: `api-service/app/api/lab_profile.py`
- Modify: `api-service/app/services/instrument_hal_service.py`
- Modify: `api-service/app/api/instrument.py`
- Modify: `api-service/tests/test_lab_profile_api.py`
- Modify: `api-service/tests/test_p1_73c_cmw_readiness.py`
- Create: `api-service/tests/test_p2_44_base_station_binding_api.py`

**Step 1: Write the failing test**

RED 覆盖：

- GET preview、sync 响应、HAL readiness 与 execution freeze 返回同一 `binding_digest`；
- sync 在写 binding 后调用 resolver，解析失败事务回滚；
- preview/readiness 不连接仪器；
- invalid 状态携带明确 reason，绝不显示 ready；
- CMW 兼容 readiness 只从共同 resolved/live 状态派生；UXM 不生成 CMW profile 要求；
- loaded transport 漂移时 preview/readiness/freeze 同样拒绝或 warning，不出现分叉。

**Step 2: Verify RED**

Run API/readiness 定点测试，确认当前独立查询产生缺字段或 digest 不一致。

**Step 3: Minimal GREEN**

- 新增 vendor-neutral preview response schema 和 GET endpoint；
- sync response 包含 binding + resolved preview；
- readiness 新增 `base_station_binding`，旧 `cmw500_lte_2x2` 从共同结果派生；
- execution freeze 直接保存 resolver 的 stable projection 与 `binding_digest`。

不删除旧响应字段，不新增数据库列。

**Step 4: Verify GREEN**

Run Task 3 测试、LabProfile、readiness、formal runner/commissioning freeze 回归。

**Step 5: Commit**

```bash
git add api-service/app/schemas/base_station_binding.py \
  api-service/app/api/lab_profile.py \
  api-service/app/services/instrument_hal_service.py \
  api-service/app/api/instrument.py \
  api-service/tests/test_lab_profile_api.py \
  api-service/tests/test_p1_73c_cmw_readiness.py \
  api-service/tests/test_p2_44_base_station_binding_api.py
git commit -m "feat: expose resolved base station binding"
```

## Task 4：让 Instrument Catalog 保存和 GUI 表单由 Manifest 驱动

**Files:**

- Modify: `api-service/app/api/instrument.py`
- Modify: `api-service/app/schemas/instrument.py`
- Modify: `api-service/tests/test_instrument_catalog_model_capabilities.py`
- Modify: `api-service/tests/test_p1_73b_cmw_adapter_profile.py`
- Create: `gui/src/types/baseStationManifest.ts`
- Create: `gui/src/types/baseStationManifest.test.ts`
- Modify: `gui/src/types/api.ts`
- Modify: `gui/src/App.tsx`

**Step 1: Write the failing tests**

后端 RED：每个已注册 BaseStation model 暴露 public manifest；保存 profile 统一经 manifest 内部
profile model 校验，UXM/无 profile adapter 不接受 CMW JSON。

GUI RED：给 fake 第三 adapter manifest 添加两个字段，通用 helper 能生成空值、读回嵌套 profile、
验证必填并构造请求；测试不得出现 `model === 'CMW500'` 或固定七字段分支。

**Step 2: Verify RED**

Run 后端定点和 `node --test gui/src/types/baseStationManifest.test.ts`，确认 manifest 投影/helper 缺失。

**Step 3: Minimal GREEN**

- Instrument model response 增加可选 `base_station_manifest`；
- 保存路径按已选 model 的 registration 校验 profile；
- GUI helper 按字段 path 做嵌套 get/set/build；
- App 的 profile card、字段说明和是否显示由 manifest 驱动；
- CMW 专用授权 endpoint 不变，只由 manifest `formal_gate` 决定是否显示控件。

不把 profile/授权写入 localStorage 或通用 env。

**Step 4: Verify GREEN**

Run 后端定点、GUI helper tests 和相关已有 CMW GUI 契约。

**Step 5: Commit**

```bash
git add api-service/app/api/instrument.py api-service/app/schemas/instrument.py \
  api-service/tests/test_instrument_catalog_model_capabilities.py \
  api-service/tests/test_p1_73b_cmw_adapter_profile.py \
  gui/src/types/baseStationManifest.ts gui/src/types/baseStationManifest.test.ts \
  gui/src/types/api.ts gui/src/App.tsx
git commit -m "feat: drive base station profile UI from manifest"
```

## Task 5：同步 OpenAPI 三镜像与 API 服务

**Files:**

- Modify: `api/openapi.yaml`
- Modify: `gui/src/types/api.generated.ts`（生成）
- Modify: `gui/src/api/labProfileService.ts`
- Modify: `gui/src/api/service.ts`
- Create: `api-service/tests/test_p2_44_openapi_contract.py`
- Create: `gui/src/types/baseStationBindingApiTruth.test.ts`

**Step 1: Write the failing tests**

RED 锁定 live OpenAPI、checked-in YAML、generated TS 与手写类型：manifest、preview、sync、readiness
字段严格一致；新增字段可选/可空性不漂移。

**Step 2: Verify RED**

Run 后端 OpenAPI test 与 GUI contract test，确认三镜像尚未同步。

**Step 3: Minimal GREEN**

更新 checked-in OpenAPI 和 API service 类型，运行：

```bash
cd gui
npm run openapi:generate
```

禁止手改 generated TS 代替生成。

**Step 4: Verify GREEN**

Run OpenAPI/GUI contract tests 和 `npm run build`。

**Step 5: Commit**

```bash
git add api/openapi.yaml gui/src/types/api.generated.ts \
  gui/src/api/labProfileService.ts gui/src/api/service.ts \
  api-service/tests/test_p2_44_openapi_contract.py \
  gui/src/types/baseStationBindingApiTruth.test.ts
git commit -m "chore: sync base station binding API mirrors"
```

## Task 6：生产路径门、Roadmap 与镜像收口

**Files:**

- Modify: `api-service/tests/test_rule_gates.py`
- Create: `api-service/tests/test_p2_44_single_binding_resolver.py`
- Modify: `docs/roadmap-first-call.md`

**Step 1: Write the failing test**

先证明现有 freeze/readiness/sync 仍各自查询 BaseStation model/binding/connection/profile。行为门锁定：

- 这些生产入口只能调用唯一 resolver；
- GUI 不再按厂商型号决定 profile 字段；
- adapter registry 的每个 BaseStation class 必须有有效 manifest；
- 测试/门问题严重度上限 P2。

**Step 2: Verify RED**

在替换完生产路径前运行门，确认它抓到残余独立 resolver/厂商分支。

**Step 3: Minimal GREEN**

删除残余重复查询或换源到共同 result；只给真正兼容镜像保留明确 adapter projection。更新 roadmap
当前状态、P2-43 合并事实与 P2-44 实施结果，不改历史记录、不提前标 P2-45 完成。

**Step 4: Verify GREEN**

Run 新门、全部 rule gates 和 diff-check。

**Step 5: Commit**

```bash
git add api-service/tests/test_rule_gates.py \
  api-service/tests/test_p2_44_single_binding_resolver.py \
  docs/roadmap-first-call.md
git commit -m "test: lock single base station binding resolver"
```

## Task 7：完整验证、Fresh 内审与 PR 收口

**Step 1: Focused regression**

运行 P2-44 manifest/resolver/API/OpenAPI/GUI、P1-73 profile/readiness、P2-42 session、P2-43
adapter/evidence、formal runner/commissioning 和 rule gates。

**Step 2: Full regression and build**

```bash
cd api-service
./.venv/bin/python -m pytest -q
./.venv/bin/python -m compileall -q app
./.venv/bin/alembic heads
cd ../gui
node --test src/types/baseStationManifest.test.ts src/types/baseStationBindingApiTruth.test.ts
npm run build
```

运行基线到 HEAD 的 diff-check；确认恰好一个 Alembic head。

**Step 3: Mirror search**

全仓搜索 `CMW500` profile UI 分支、`selected_model_id`、`base_station_adapter_profile`、
`build_cmw500_lte_2x2_readiness` 和旧 digest 文案，逐条确认仍成立或已换源。

**Step 4: Fresh independent functional review**

按 AGENTS.md 0.5 提供 staged diff、当前版本验证输出与已造变异清单；全套档 fresh 内审只审不改，
功能 P1 收口到 0。测试发现上限 P2。

**Step 5: Ready PR and external review**

推送、开 Ready PR，PR body 声明 `Roadmap: P2-44`、可观察故障、范围与验证。触发 Codex R1；
处理本片功能 P1 与本片内 P2 后触发 R2。覆盖最新 HEAD 的 R2 无 P1且 mergeable/checks通过才
merge commit；R2 若仍有 P1则继续 P1-only 复审到最新 HEAD 无 P1。

**Step 6: Merge, sync, cleanup**

fetch 验证 origin/main，本地主目录 `git merge --ff-only origin/main`，保留未跟踪仪器资料；清理
P2-44 worktree/本地分支后才开始 P2-45。
