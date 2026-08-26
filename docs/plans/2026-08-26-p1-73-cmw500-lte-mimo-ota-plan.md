# P1-73 CMW500 LTE 2×2 MIMO OTA Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 在不复制顶层测试流、不回归 UXM 的前提下，让 R&S CMW500 通过通用 BaseStation HAL 完成 LTE 单载波 2×2 MIMO OTA；所有正式吞吐/BLER 必须绑定真实型号、固件、选件、配置/内部路由回读与同一测量窗口证据。

**Architecture:** 分三片交付。P1-73A 先清除 MIMO OTA 顶层的 UXM 厂商泄漏并建立兼容迁移；P1-73B 按厂商手册重写 CMW500 的只读连接、内部 `1CC - nx2` 路由、状态机与 Extended BLER 窗口；P1-73C 才接入正式证据、OperationalLab、报告和 GUI。外部 RF router 不进入能力准入或运行硬门；端到端功率预算、外部补偿和 F64 输入余量延后到正式发布阶段。

**Tech Stack:** Python 3.12、FastAPI、Pydantic v2、SQLAlchemy、PyVISA、pytest/pytest-asyncio、React 18、TypeScript、Mantine、Vite、OpenAPI。

---

## 0. 固定边界与验收口径

实施中不得重新解释以下已获用户批准的固定边界；本文其余细节仍须通过本 PR 设计评审：

- LabProfile 的 `baseStation` 是逻辑角色；一次执行选择 UXM 或 CMW500，不在顶层复制两套流程。
- CMW500 首期仅 LTE、单载波、2×2、F64 射频域下游链；不做 DAU/IP 吞吐、CA、4×4、数字 IQ 外部衰落。
- CMW500 硬件 eligibility 只消费**型号、固件版本、选件快照**；独立 rollout approval 默认关闭、
  由专用持久化入口显式开启并冻结到新 execution。外部 RF router 不参与任一准入键，也不成为逐次执行硬门。
- CMW500 仪表内部 `1CC - nx2` 的 RX/TX1/TX2 route 属于驱动应用态，必须写后回读核对；它不是外部 RF router。
- adapter 可以注册，正式能力默认关闭；现场未验证项显示 Warning，不以 Hardware Blocked 阻止开发。
- 开发阶段不建设“请求功率 + 外部补偿 + 开关/线缆路径 + F64 输入上限 + 校准证书”的端到端功率门；该项在正式发布前单独设计。
- `inherit` 是显式 debug 模式，默认关闭；其产物只能诊断使用，不能获得正式 KPI/verdict。
- 新证据默认白名单；旧 CMW 原型没有可晋升为正式证据的兼容路径。

每片都必须遵循：先 RED，确认针对当前故障真实变红；再最小 GREEN；focused 回归；fresh 内审；最后才开 Ready PR。

---

## P1-73A：共享 HAL 清理与无损兼容

### Task 1：建立厂商无关的 BaseStation 应用契约

**Files:**

- Modify: `api-service/app/hal/base_station.py`
- Modify: `api-service/app/hal/uxm_base_station.py`
- Modify: `api-service/app/services/mimo_ota/cell_config_consistency.py`
- Modify: `api-service/tests/test_cell_config_consistency.py`
- Create: `api-service/tests/test_p1_73a_base_station_contract.py`

**Step 1: 写 RED**

新增 contract 测试，要求 `AppliedCellConfig`、配置应用结果、能力准入快照定义在通用 HAL；`cell_config_consistency.py` 不得导入 `uxm_base_station`。最小形态：

```python
@dataclass(frozen=True)
class BaseStationIdentity:
    adapter_id: Literal["uxm", "cmw500"]
    model: str
    firmware_version: str | None
    options: tuple[str, ...]

@dataclass(frozen=True)
class AppliedCellConfig:
    ue_max_dl_layers: int | None = None
    ue_max_modulation_dl: str | None = None

@dataclass(frozen=True)
class BaseStationConfigResult:
    requested: dict[str, Any]
    applied: dict[str, Any] | None
    confirmed: bool
    reason: str

@dataclass(frozen=True)
class BaseStationCleanupResult:
    stop_signaling_confirmed: bool
    safe_idle_confirmed: bool
    warnings: tuple[str, ...]

@dataclass(frozen=True)
class BaseStationRemoteSessionResult:
    adapter_id: Literal["uxm", "cmw500"]
    session_token: str
    acquired_confirmed: bool
    warnings: tuple[str, ...]

@dataclass(frozen=True)
class BaseStationControlReleaseResult:
    measurement_attempt_id: str | None
    lease_id: str
    adapter_id: Literal["uxm", "cmw500"]
    session_token: str
    remote_session_acquired_confirmed: bool
    transport_session_released_confirmed: bool
    front_panel_local_confirmed: bool | None
    warnings: tuple[str, ...]
```

测试还应证明通用基类不再包含 `build_uxm_downlink_power_command` 这种厂商 builder。

**Step 2: 运行 RED**

```bash
cd api-service
./.venv/bin/python -m pytest -q \
  tests/test_p1_73a_base_station_contract.py \
  tests/test_cell_config_consistency.py
```

预期：新类型不存在、共享服务仍依赖 UXM，测试失败。

**Step 3: 最小 GREEN**

- 把真正跨驱动的类型移到 `base_station.py`。
- `adapter_id` 由 `instrument_hal_service.get_real_driver_class(category_key, model_name)` 命中的注册类
  的固定类属性产生；registry 初始化校验唯一值，业务层不得从型号/类名前缀或 connection params 猜。
- `BaseStationCleanupResult` 是共享 MEASURE cleanup 的唯一结果，只保存该阶段真实拥有的
  stop signaling/SAFE_IDLE；任何字段只有驱动返回精确 `True` 且相应状态回读确认后才为 true。
  它不拥有基站 transport close，不得调用 `disconnect()` 抢在 lease control release 之前关闭会话。
- `BaseStationControlReleaseResult` 按唯一 `lease_id` 分开保存 Remote session 取得、transport/session
  释放与前面板 Local 状态；它只能由 `instrument_test_lease` 的真实控制会话结果产生，不能用 cleanup、
  finally 或“无异常”推导。关闭 VISA/HiSLIP 只确认 transport release；没有厂商动作与确认信号时
  `front_panel_local_confirmed` 必须为 null/unknown，不能因类名或旧方法名写成 true。
- `BaseStationRemoteSessionResult` 的 `session_token` 只能由真实驱动在成功建立新 transport session 后
  生成并返回；使用不可预测 opaque UUID，不编码地址、凭证或仪表身份。每次新 session/重连必须新建
  token，旧 token 永不复用；业务层和 lease 不得读取 `_visa_session` 或自行造第二个 lease id 代替。
- UXM 改为导入通用类型，不复制定义。
- UXM 专属功率 builder 下沉到 UXM profile/driver。
- 只改归属，不改变 UXM 命令、返回值或执行顺序。

**Step 4: 运行 GREEN**

```bash
./.venv/bin/python -m pytest -q \
  tests/test_p1_73a_base_station_contract.py \
  tests/test_cell_config_consistency.py \
  tests/test_uxm_cell_config_orchestration.py
```

**Step 5: 提交**

```bash
git add api-service/app/hal/base_station.py \
  api-service/app/hal/uxm_base_station.py \
  api-service/app/services/mimo_ota/cell_config_consistency.py \
  api-service/tests/test_cell_config_consistency.py \
  api-service/tests/test_p1_73a_base_station_contract.py
git commit -m "refactor: establish vendor-neutral base station contract"
```

### Task 2：将配置字段迁移为通用名称并严格处理双写

**Files:**

- Modify: `api-service/app/schemas/mimo_ota/config.py`
- Modify: `api-service/app/services/test_plan_service.py`
- Create: `api-service/tests/test_p1_73a_config_compatibility.py`
- Modify: `api-service/tests/test_commissioning_strict_gate_overrides.py`
- Modify: `gui/src/components/TestCaseConfig/MIMOOTAConfigForm.tsx`
- Modify: `gui/src/components/Commissioning/api.ts`
- Create: `gui/test/baseStationConfigTruth.test.ts`

**Step 1: 写 RED**

覆盖四类输入：

1. 仅新字段 `base_station_config_mode`；
2. 仅旧字段 `uxm_config_mode`；
3. 新旧同时且值相同；
4. 新旧同时但值冲突，必须在保存或 I/O 前 422/fail-loud。

GUI 契约要求只写新字段；旧字段只读兼容，不再由表单产生。

**Step 2: 运行 RED**

```bash
cd api-service
./.venv/bin/python -m pytest -q \
  tests/test_p1_73a_config_compatibility.py \
  tests/test_commissioning_strict_gate_overrides.py
cd ../gui
node --test test/baseStationConfigTruth.test.ts
```

**Step 3: 最小 GREEN**

- 在 `MIMOOTAConfiguration` 增加通用 `base_station_config_mode`，旧 `uxm_config_mode` 标记 deprecated。
- `canonicalize_mimo_ota_configuration_payload()` 负责唯一兼容翻译；不得在执行器再写第二份回退。
- 冲突立即拒绝；缺省模式仍为 `dispatch`。
- `inherit` 文案改成“基站当前态调试继承”，并明确结果不进入正式判定。
- 不新增通用整带宽功率字段；`uxm_dl_power_dbm_per_bw` 保持 UXM 兼容语义，CMW 不消费它。
- 不在本 Task 重命名数据库列或删除旧 JSON 键。

**Step 4: 运行 GREEN**

```bash
cd api-service
./.venv/bin/python -m pytest -q \
  tests/test_p1_73a_config_compatibility.py \
  tests/test_commissioning_strict_gate_overrides.py
cd ../gui
node --test test/baseStationConfigTruth.test.ts
npm run build
```

**Step 5: 提交**

```bash
git add api-service/app/schemas/mimo_ota/config.py \
  api-service/app/services/test_plan_service.py \
  api-service/tests/test_p1_73a_config_compatibility.py \
  api-service/tests/test_commissioning_strict_gate_overrides.py \
  gui/src/components/TestCaseConfig/MIMOOTAConfigForm.tsx \
  gui/src/components/Commissioning/api.ts \
  gui/test/baseStationConfigTruth.test.ts
git commit -m "refactor: canonicalize base station configuration fields"
```

### Task 2A：把 PCell 真值扩展为显式 LTE/NR 联合契约

**Files:**

- Modify: `api-service/app/schemas/mimo_ota/config.py`
- Modify: `api-service/app/api/commissioning.py`
- Modify: `api-service/app/services/mimo_ota/factory.py`
- Modify: `api-service/app/models/standard_channel.py`
- Modify: `api-service/app/api/standard_channel.py`
- Modify: `api-service/app/api/channel_asset.py`
- Modify: `api-service/app/api/instrument.py`
- Modify: `api-service/app/services/channel_asset_service.py`
- Modify: `api-service/app/hal/channel_emulator.py`
- Modify: `api-service/app/services/smu_project_inventory.py`
- Modify: `api-service/app/services/mimo_ota/channel_naming.py`
- Modify: `api-service/app/services/mimo_ota/executors/measure.py`
- Modify: `api-service/app/services/mimo_ota/frequency_consistency.py`
- Modify: `api-service/app/services/mimo_ota/channel_asset_resolver.py`
- Modify: `api-service/app/services/standard_channel_service.py`
- Create: `api-service/alembic/versions/c73a19f4e602_add_rat_to_standard_channels.py`
- Create: `api-service/app/hal/lte_earfcn.py`
- Create: `api-service/tests/test_p1_73a_lte_operating_point.py`
- Modify: `api-service/tests/test_commissioning_strict_gate_overrides.py`
- Modify: `api-service/tests/test_commissioning_smoke.py`
- Create: `api-service/tests/test_p1_73a_asset_frequency_identity.py`
- Modify: `api-service/tests/test_p1_55_carrier_truth_source.py`
- Modify: `api-service/tests/test_channel_naming.py`
- Modify: `api-service/tests/test_channel_asset_resolver.py`
- Modify: `api-service/tests/test_channel_asset_migration.py`
- Modify: `api-service/tests/test_standard_channel.py`
- Modify: `api-service/tests/test_channel_models_crud.py`
- Modify: `api-service/tests/test_channel_models_db_fallback.py`
- Modify: `api-service/tests/test_f64_channel_model_listing.py`
- Modify: `api-service/tests/test_smu_project_inventory.py`
- Modify: `api-service/tests/test_smu_project_scan_api.py`
- Modify: `gui/src/components/TestCaseConfig/MIMOOTAConfigForm.tsx`
- Modify: `gui/src/components/Commissioning/api.ts`
- Modify: `gui/src/components/Commissioning/index.tsx`
- Modify: `gui/src/components/TestCaseConfig/carrierTruth.ts`
- Modify: `gui/src/api/standardChannelService.ts`
- Modify: `gui/src/api/channelAssetService.ts`
- Modify: `gui/src/api/service.ts`
- Modify: `gui/src/features/ChannelWorkbench/ChannelAssetForm.tsx`
- Create: `gui/src/features/ChannelWorkbench/channelFrequencyIdentityTruth.test.ts`
- Modify: `gui/src/components/StandardChannelDefinitionCard.tsx`
- Modify: `gui/src/App.tsx`
- Create: `gui/src/components/TestCaseConfig/lteOperatingPointTruth.test.ts`
- Modify: `api/openapi.yaml`
- Modify: `gui/src/types/api.generated.ts`

**Step 1: 写 RED**

扩展 `component_carriers[0]`，但不创建第二个工作点真源。契约至少覆盖：

- `radio_technology="nr5g"` 保持当前默认与 NR ARFCN/SCS 行为不变；
- `radio_technology="lte"` 时只允许单个 PCell，要求显式 LTE band、`lte_dl_earfcn`、
  frequency、bandwidth、duplex，禁止 SCell、NR ARFCN 与 NR SCS；
- LTE 的 band/EARFCN/frequency 关系由独立 LTE helper 校验；不调用 `freq_mhz_to_nr_arfcn()`；
- LTE helper 的唯一映射出处固定为本地 CMW LTE UE User Manual §2.2.23 第 91–95 页：
  第 91 页公式 `N = 10 × (F - FOffset)/MHz + NOffset`，Tables 2-54/2-55/2-56 的 FDD UL、
  FDD DL 与 TDD ranges；每组 offset/range 紧邻标注表号，未知/SCC-only/选件不满足 band 拒绝；
- LTE 缺 EARFCN、沿用原型 1575 默认、RAT/顶层/CC 冲突，全部在保存或硬件 I/O 前 422；
- 活跃 `/commissioning/sessions` 入口同样覆盖：`CreateSessionRequest` 能表达 RAT、LTE duplex、
  band、DL EARFCN 和可选 LTE theoretical peak，`_request_overrides()` 形成同一个显式 PCell；
  `build_mimo_ota_test_case()` 必须先调用与普通 TestCase API 相同的 canonicalizer 再持久化，不能
  直接 `MIMOOTAConfiguration.model_validate()` 后静默落入 NR 默认；adhoc 与 run-all 两个调用点
  都走同一 factory 契约；
- 当前 `theoretical_peak_throughput_mbps=450` 只保留为 legacy NR 兼容。LTE 不得继承该默认；
  LTE 未显式提供有限正值时，绝对吞吐可独立可信，但 `throughput_ratio`、ratio pass、依赖 ratio
  的 verdict/delta/repeatability 必须 UNKNOWN/N/A，不得从 bandwidth、当前 DB 或 NR 默认猜值；
- `measure.py`、`channel_asset_resolver.py`、`standard_channel_service.py` 三个 NR identity 生产者
  全部消费同一 RAT-aware working point；SCD/ChannelAsset 明示 channel kind，禁止把
  `scd_config.arfcn` 无条件解释为 NR，也禁止把 LTE EARFCN 与 NR ARFCN 直接比较；
- StandardChannel 加法迁移新增非空 `radio_technology` / `channel_kind`：迁移时现有行因旧 schema
  唯一只允许 NR 而精确写为 `nr5g/nr_arfcn`；迁移完成后移除数据库默认，新 API 写入必须显式；
  migration revision=`c73a19f4e602`、down_revision=`b7c9e1f3a5d7`，不得生成第二个 Alembic head；
- ChannelAsset JSON 不回填历史行；只读 legacy translator 仅接受完整通过旧 NR validator 的
  pre-P1-73 `scd_config`，映射为 `nr5g/nr_arfcn`。新 create/update、GUI 表单、OpenAPI 与
  `available_channel_models` projection 都必须显式携带两个字段，缺失/冲突在写入前拒绝；
- `api/instrument.py` 的 channel model CRUD/list 和 GUI channel-model consumer 同样透传并校验
  RAT/channel kind；旧 projection 只经同一个 legacy-NR translator 读取，不另写第二套兼容规则；
- `channel_emulator.normalize_channel_model_entries` 保留 typed identity，不再为所有频率无条件派生
  NR ARFCN；`smu_project_inventory` 按目标资产的显式 RAT/kind 选择 LTE/NR converter，再把同一
  identity 写回 ChannelAsset 与 projection，未知/冲突时 protect 整项；`ChannelModelsCard` 的
  活跃手工写入口要求 operator 显式选择 RAT/kind，不能继续产生无法分类的新条目；
- 旧 `available_channel_models` 按身份来源精确分流：带 `scd_id` 的从迁移后 SCD 取 typed identity，
  带 `channel_asset_id` 的经资产 legacy translator；只有 filename/bare string 的手工项保留显示为
  `legacy_unknown`，不从文件名补 NR、不参与正式频率匹配，也不因升级而从列表消失；
- 标准信道命名器也消费 typed identity：legacy NR 继续精确生成/解析现有
  `MF_N78_640000_...`；LTE 新名显式包含 RAT 与 channel kind（例如
  `MF_LTE_B3_EARFCN1575_...`），不得把 LTE EARFCN 填进旧 NR ARFCN 槽或与同号 NR 资产碰撞；
- 跨 RAT 的资产一致性仅比较经各自有出处 converter 得到的中心频率与带宽；缺 RAT、缺 converter
  或 channel kind 冲突都保护资产并在 I/O 前 fail-loud，不从文件名或当前 DB 猜测；
- executor 将同一个 typed `BaseStationRequestedConfig` 交给 fake UXM/CMW，不按厂商类分支；
- GUI TestCase 表单与 Commissioning 启动页选择 LTE 时都要求上述显式字段并发送到同一
  canonicalizer，不写 NR 默认值；LTE peak 未提供时界面明确显示 ratio/相关判决不可用。

**Step 2: 运行 RED**

```bash
cd api-service
./.venv/bin/python -m pytest -q \
  tests/test_p1_73a_lte_operating_point.py \
  tests/test_p1_55_carrier_truth_source.py \
  tests/test_channel_naming.py \
  tests/test_channel_asset_resolver.py \
  tests/test_channel_asset_migration.py \
  tests/test_standard_channel.py \
  tests/test_channel_asset.py \
  tests/test_channel_models_crud.py \
  tests/test_channel_models_db_fallback.py \
  tests/test_f64_channel_model_listing.py \
  tests/test_smu_project_inventory.py \
  tests/test_smu_project_scan_api.py \
  tests/test_p1_73a_asset_frequency_identity.py \
  tests/test_commissioning_strict_gate_overrides.py \
  tests/test_commissioning_smoke.py
cd ../gui
node --test \
  src/components/TestCaseConfig/lteOperatingPointTruth.test.ts \
  src/features/ChannelWorkbench/channelFrequencyIdentityTruth.test.ts
```

预期：当前 schema 是 NR-only，LTE 输入会被 NR ARFCN 路径解释，测试失败。

**Step 3: 最小 GREEN**

- 给 PCell 增加显式 RAT 与互斥 channel-number 字段；旧记录缺 RAT 精确兼容为 NR。
- 把 `theoretical_peak_throughput_mbps` 改成 RAT-aware 输入：legacy NR translator 精确保留现有
  450 Mbps 行为；LTE 只接受本次显式有限正值，缺失时不生成 ratio 或相关判决。
- `CreateSessionRequest` / `_request_overrides()` 产生与 TestCase 表单相同的 typed PCell；factory
  复用唯一 canonicalizer。Commissioning API/GUI 不另写 LTE 默认或第二套转换器。
- LTE converter 只实现 CMW LTE UE User Manual §2.2.23 Tables 2-54/2-55/2-56 明确列出的、
  且当前型号/选件快照支持的 band；未知、SCC-only、选件不足 band fail-loud，不猜公式。
- MEASURE 先按 RAT 建立 requested config，再交给通用 driver；LTE 路径不导入 NR converter。
- MEASURE、ChannelAsset resolver 与 StandardChannel service 复用同一 typed frequency identity；
  频率一致性结果携带 RAT/channel kind，禁止把 LTE EARFCN 与 NR ARFCN 比较。
- StandardChannel model/API/service、ChannelAsset validator/API、GUI 两个资产入口与三份 API
  镜像同步写入 RAT/channel kind；legacy translator 只在读取旧 NR-only 行时生效，不为新请求补值。
- normalizer、SMU project scanner/sync、instrument channel-model CRUD 与 `ChannelModelsCard` 复用同一
  typed identity/legacy source classifier；bare-string 历史项只保留展示，不获得正式身份。
- channel naming/parser 对 NR 保持字节级兼容，对 LTE 使用不与 NR 混淆的新 canonical family；
  vendor 文件仍以项目内部 `[Channel Group 0] CenterFrequency` 为频率真值，文件名不反压频率。
- 保留 P1-55 的顶层镜像一致性门，不能因扩展 RAT 放宽旧冲突检查。

**Step 4: 运行 GREEN 并提交**

```bash
cd api-service
./.venv/bin/python -m pytest -q \
  tests/test_p1_73a_lte_operating_point.py \
  tests/test_p1_55_carrier_truth_source.py \
  tests/test_channel_naming.py \
  tests/test_frequency_consistency.py \
  tests/test_channel_asset_resolver.py \
  tests/test_channel_asset_migration.py \
  tests/test_standard_channel.py \
  tests/test_channel_asset.py \
  tests/test_channel_models_crud.py \
  tests/test_channel_models_db_fallback.py \
  tests/test_f64_channel_model_listing.py \
  tests/test_smu_project_inventory.py \
  tests/test_smu_project_scan_api.py \
  tests/test_p1_73a_asset_frequency_identity.py \
  tests/test_commissioning_strict_gate_overrides.py \
  tests/test_commissioning_smoke.py \
  tests/test_uxm_cell_config_orchestration.py
cd ../gui
node --test \
  src/components/TestCaseConfig/lteOperatingPointTruth.test.ts \
  src/features/ChannelWorkbench/channelFrequencyIdentityTruth.test.ts
npm run build
cd ..
git add api-service/app/schemas/mimo_ota/config.py \
  api-service/app/api/commissioning.py \
  api-service/app/services/mimo_ota/factory.py \
  api-service/app/models/standard_channel.py \
  api-service/app/api/standard_channel.py \
  api-service/app/api/channel_asset.py \
  api-service/app/api/instrument.py \
  api-service/app/services/channel_asset_service.py \
  api-service/app/hal/channel_emulator.py \
  api-service/app/services/smu_project_inventory.py \
  api-service/app/services/mimo_ota/channel_naming.py \
  api-service/app/services/mimo_ota/executors/measure.py \
  api-service/app/services/mimo_ota/frequency_consistency.py \
  api-service/app/services/mimo_ota/channel_asset_resolver.py \
  api-service/app/services/standard_channel_service.py \
  api-service/alembic/versions/c73a19f4e602_add_rat_to_standard_channels.py \
  api-service/app/hal/lte_earfcn.py \
  api-service/tests/test_p1_73a_lte_operating_point.py \
  api-service/tests/test_commissioning_strict_gate_overrides.py \
  api-service/tests/test_commissioning_smoke.py \
  api-service/tests/test_p1_55_carrier_truth_source.py \
  api-service/tests/test_channel_naming.py \
  api-service/tests/test_channel_asset_resolver.py \
  api-service/tests/test_channel_asset_migration.py \
  api-service/tests/test_standard_channel.py \
  api-service/tests/test_channel_asset.py \
  api-service/tests/test_channel_models_crud.py \
  api-service/tests/test_channel_models_db_fallback.py \
  api-service/tests/test_f64_channel_model_listing.py \
  api-service/tests/test_smu_project_inventory.py \
  api-service/tests/test_smu_project_scan_api.py \
  api-service/tests/test_p1_73a_asset_frequency_identity.py \
  gui/src/components/TestCaseConfig/MIMOOTAConfigForm.tsx \
  gui/src/components/Commissioning/api.ts \
  gui/src/components/Commissioning/index.tsx \
  gui/src/components/TestCaseConfig/carrierTruth.ts \
  gui/src/api/standardChannelService.ts \
  gui/src/api/channelAssetService.ts \
  gui/src/api/service.ts \
  gui/src/features/ChannelWorkbench/ChannelAssetForm.tsx \
  gui/src/features/ChannelWorkbench/channelFrequencyIdentityTruth.test.ts \
  gui/src/components/StandardChannelDefinitionCard.tsx \
  gui/src/App.tsx \
  gui/src/components/TestCaseConfig/lteOperatingPointTruth.test.ts \
  api/openapi.yaml gui/src/types/api.generated.ts
git commit -m "feat: add explicit LTE MIMO operating point truth"
```

### Task 3：将执行证据从 UXM 命名收敛为 BaseStation 命名

**Files:**

- Modify: `api-service/app/services/execution_scpi_evidence.py`
- Modify: `api-service/app/services/mimo_ota/executors/measure.py`
- Modify: `api-service/tests/test_p1_47c_execution_scpi_evidence.py`
- Create: `api-service/tests/test_p1_73a_base_station_evidence.py`

**Step 1: 写 RED**

证明新的执行只能调用：

```python
record_base_station_config_capture(...)
record_base_station_throughput_capture(...)
```

并使用通用 requirement/evidence key。旧 `uxm.*` 只能经精确 legacy translator 读取；新写方不得继续产生旧键。translator 遇到非 UXM identity、缺字段或冲突时必须返回 unknown。

**Step 2: 运行 RED**

```bash
cd api-service
./.venv/bin/python -m pytest -q \
  tests/test_p1_73a_base_station_evidence.py \
  tests/test_p1_47c_execution_scpi_evidence.py
```

**Step 3: 最小 GREEN**

- 改名并收敛 helper；保留窄兼容 wrapper 仅服务旧测试/旧行读取。
- evidence 环境身份记录 adapter、model、firmware、options。
- 不把 adapter 名称本身当作真实性；仍由 instrument HAL 的 real/mock 白名单判定。

**Step 4: 运行 GREEN 并提交**

```bash
./.venv/bin/python -m pytest -q \
  tests/test_p1_73a_base_station_evidence.py \
  tests/test_p1_47c_execution_scpi_evidence.py
git add api-service/app/services/execution_scpi_evidence.py \
  api-service/app/services/mimo_ota/executors/measure.py \
  api-service/tests/test_p1_47c_execution_scpi_evidence.py \
  api-service/tests/test_p1_73a_base_station_evidence.py
git commit -m "refactor: generalize base station execution evidence"
```

### Task 4：清除 MEASURE 与输入闭环的 UXM 类型依赖

**Files:**

- Modify: `api-service/app/services/mimo_ota/executors/measure.py`
- Modify: `api-service/app/services/input_level_controller.py`
- Modify: `api-service/tests/test_measure_input_and_param_branches.py`
- Modify: `api-service/tests/test_mimo_ota_measure_input_level.py`
- Modify: `api-service/tests/test_input_level_controller.py`
- Create: `api-service/tests/test_p1_73a_vendor_neutral_measure.py`

**Step 1: 写 RED**

用一个 UXM fake 和一个最小 CMW fake 跑同一个 executor 入口，断言：

- 顶层不 `isinstance(RealUxmDriver)` 或导入 CMW 类型分支；
- `dispatch`/`inherit`、配置结果、吞吐窗口都只调用通用接口；
- UXM 的既有功率字段/结果保持兼容，但不得晋升为跨厂商契约；
- CMW fake 证据不完整时安全得到 UNKNOWN，而不是因顶层硬编码 UXM 崩溃。

**Step 2: 运行 RED**

```bash
cd api-service
./.venv/bin/python -m pytest -q \
  tests/test_p1_73a_vendor_neutral_measure.py \
  tests/test_measure_input_and_param_branches.py \
  tests/test_mimo_ota_measure_input_level.py \
  tests/test_input_level_controller.py
```

**Step 3: 最小 GREEN**

- 变量和结果改成 base-station 语义，但不把 UXM 的功率单位推广成跨厂商契约。
- 厂商差异只能由 driver/profile 覆写，不允许 executor 拼 CMW SCPI。
- `inherit` 继续执行安全 cleanup，但显式 evidence gate 阻止正式判定。
- 保留旧 UXM 结果键作只读兼容镜像，并在同一 helper 中生成，避免双真源。
- CMW 的 input-level/power capability 在 P1-73 保持关闭并显示 Warning；不得调用 UXM 功率字段或
  用默认值补齐。UXM 现有 input-level 行为必须原样回归通过。

**Step 4: 运行 GREEN 并提交**

```bash
./.venv/bin/python -m pytest -q \
  tests/test_p1_73a_vendor_neutral_measure.py \
  tests/test_measure_input_and_param_branches.py \
  tests/test_mimo_ota_measure_input_level.py \
  tests/test_input_level_controller.py \
  tests/test_uxm_cell_config_orchestration.py
git add api-service/app/services/mimo_ota/executors/measure.py \
  api-service/app/services/input_level_controller.py \
  api-service/tests/test_p1_73a_vendor_neutral_measure.py \
  api-service/tests/test_measure_input_and_param_branches.py \
  api-service/tests/test_mimo_ota_measure_input_level.py \
  api-service/tests/test_input_level_controller.py
git commit -m "refactor: make MIMO measure base-station neutral"
```

### Task 4A：落地 profile-driven baseStation.DL1…DLN/UL1 逻辑拓扑

**Files:**

- Create: `api-service/app/services/base_station_port_mapping.py`
- Modify: `api-service/scripts/dev-fixtures/topology-templates/caict_v4.py`
- Modify: `api-service/app/services/mimo_ota/switch_orchestrator.py`
- Modify: `api-service/app/hal/uxm_test_profiles.py`
- Create: `api-service/tests/test_p1_73a_base_station_topology.py`
- Modify: `api-service/tests/test_switch_topology_chamber_binding.py`
- Modify: `api-service/tests/test_uxm_driver_profile.py`
- Modify: `gui/src/features/TopologyEditor/CustomNodes.tsx`
- Create: `gui/src/features/TopologyEditor/baseStationPortsTruth.test.ts`

**Step 1: 写 RED**

要求 topology 使用一个逻辑 `baseStation` 节点及 profile-driven `DL1…DLN/UL1`：

- MIMO OTA 连接数来自本次显式 `mimo_port_preset` 和已应用 route snapshot：DL1…DLN 对应
  F64 input 1…N，UL1 回到当前 baseStation；CMW500 首期 N=2；
- UXM 物理映射不得硬编码：普通 2×2 保留 RF1/RF2，alternate 2×2 保留 RF3/RF4，4×4
  保留 RF1…RF4，UL 及其他现有映射从当前 profile/route snapshot 取得；
- RED 分别覆盖 UXM 普通 2×2、alternate 2×2、4×4 与 CMW500 2×2，证明接入 CMW 不会
  把 UXM 4×4 收窄成两路或把 alternate preset 静默改回 RF1/RF2；
- CMW adapter 映射到内部 route 的 TX1/TX2/RX 逻辑角色，具体 connector 来自当前驱动回读，
  不在模板猜固定 RF 口；
- LabProfile 选择不同 baseStation 后，编辑器/解析器显示对应 adapter 映射，但连接图不复制；
- 外部源选择开关缺回读只产生 Warning，不把 topology validate 变成运行硬门。
- 只迁移 `mimo_ota` active connections；CAICT 模板的 TRP/TIS/passive UXM RF5、VNA 与垂直环
  路径逐项保持不变，避免 CMW MIMO 施工破坏其他测试类型。

**Step 2: 运行 RED**

```bash
cd api-service
./.venv/bin/python -m pytest -q \
  tests/test_p1_73a_base_station_topology.py \
  tests/test_switch_topology_chamber_binding.py \
  tests/test_uxm_driver_profile.py
cd ../gui
node --test src/features/TopologyEditor/baseStationPortsTruth.test.ts
```

**Step 3: 最小 GREEN**

- 模板仅把 MIMO OTA 信号源从固定 `uxm` 节点改为逻辑 `baseStation`，逻辑 DL 端口数量由
  preset/profile 决定，保留 adapter map 作为显示/审计元数据；非 MIMO 的 UXM/VNA 物理节点
  和连接不改。
- 新 resolver 只消费 OperationalLab 已选中的 baseStation identity 与当前 driver route snapshot；
  不按节点 label 或型号前缀猜 adapter。
- switch orchestrator 输出逻辑 port 与可选 physical display，不让物理 display 反向成为连接真源。
- GUI 的 port 方向由 port role 决定，不再用 `port === "RF6"` 判断输入/输出。

**Step 4: 运行 GREEN 并提交**

```bash
cd api-service
./.venv/bin/python -m pytest -q \
  tests/test_p1_73a_base_station_topology.py \
  tests/test_switch_topology_chamber_binding.py \
  tests/test_uxm_driver_profile.py \
  tests/test_p1_57_topology_lab_context.py
cd ../gui
node --test src/features/TopologyEditor/baseStationPortsTruth.test.ts
npm run build
cd ..
git add api-service/app/services/base_station_port_mapping.py \
  api-service/scripts/dev-fixtures/topology-templates/caict_v4.py \
  api-service/app/services/mimo_ota/switch_orchestrator.py \
  api-service/app/hal/uxm_test_profiles.py \
  api-service/tests/test_p1_73a_base_station_topology.py \
  api-service/tests/test_switch_topology_chamber_binding.py \
  api-service/tests/test_uxm_driver_profile.py \
  gui/src/features/TopologyEditor/CustomNodes.tsx \
  gui/src/features/TopologyEditor/baseStationPortsTruth.test.ts
git commit -m "feat: model vendor-neutral base station topology ports"
```

### Task 5：同步 API 镜像并收口 P1-73A

**Files:**

- Modify: `api/openapi.yaml`
- Modify: `gui/src/types/api.generated.ts`
- Create: `api-service/tests/test_p1_73a_openapi_contract.py`
- Create: `gui/src/types/baseStationApiTruth.test.ts`
- Modify: `docs/roadmap-first-call.md`

**Step 1: RED/GREEN**

先写方向性契约，证明 live OpenAPI、checked-in YAML、generated TS 三者都以通用字段为主、旧字段 deprecated；再生成/更新镜像。

```bash
cd api-service
./.venv/bin/python -m pytest -q tests/test_p1_73a_openapi_contract.py
cd ../gui
node --test src/types/baseStationApiTruth.test.ts
npm run build
```

**Step 2: P1-73A 回归**

```bash
cd ../api-service
./.venv/bin/python -m pytest -q \
  tests/test_p1_73a_base_station_contract.py \
  tests/test_p1_73a_config_compatibility.py \
  tests/test_p1_73a_lte_operating_point.py \
  tests/test_p1_73a_base_station_evidence.py \
  tests/test_p1_73a_vendor_neutral_measure.py \
  tests/test_p1_73a_base_station_topology.py \
  tests/test_p1_73a_openapi_contract.py \
  tests/test_p1_47c_execution_scpi_evidence.py \
  tests/test_uxm_cell_config_orchestration.py \
  tests/test_rule_gates.py
./.venv/bin/python -m compileall -q app tests
./.venv/bin/alembic heads
cd ..
git diff --check
```

要求单一 Alembic head；fresh 内审 P1=0 后更新 roadmap，单独 Ready PR，按仓库 R1→R2 规则合并。P1-73A 不启用 CMW 正式能力。

---

## P1-73B：CMW500 驱动核心

### Task 6：建立带手册出处的 CMW command profile 与 parser

**Files:**

- Create: `api-service/app/hal/cmw500_command_profile.py`
- Modify: `api-service/app/hal/cmw500_base_station.py`
- Create: `api-service/tests/test_p1_73b_cmw_command_profile.py`
- Create: `api-service/tests/test_p1_73b_cmw_parsers.py`

**Step 1: 写 RED**

建立 command catalog 测试，要求每条可达真机的新/保留命令都带手册页码/章节与用途。首批至少覆盖：

- `ROUTe:LTE:SIGN<i>:SCENario:TRO:FLEXible ...`：LTE UE User Manual V4.0.250，第 630 页；最低 V3.5.40，需要 CMW-KS520。
- `ROUTe:LTE:SIGN<i>?`：第 459–460 页；返回当前 scenario 与相关 RX/TX connector/converter。
- `FETCh:LTE:SIGN<i>:EBLer[:PCC]:ABSolute?`：第 957–958 页；第 5 字段 `ThroughputAver`，单位 kbit/s。
- `FETCh:LTE:SIGN<i>:EBLer[:PCC]:RELative?`：第 959 页；第 4 字段 BLER（%），第 5 字段是 throughput 百分比，不是 Mbps。
- `INITiate:LTE:SIGN<i>:EBLer`、`STOP:LTE:SIGN<i>:EBLer`、
  `ABORt:LTE:SIGN<i>:EBLer` 与 `FETCh:LTE:SIGN<i>:EBLer:STATe?`：第 950–951 页；分别进入
  RUN、RDY、OFF，并以 `OFF | RUN | RDY` 状态查询确认。ABORt 会清空测量值并释放资源。

parser 必须拒绝字段不足、sentinel、NaN/Inf、非数值与错误枚举；不得继续把 Absolute 第 1 字段当 BLER。

**Step 2: 运行 RED**

```bash
cd api-service
./.venv/bin/python -m pytest -q \
  tests/test_p1_73b_cmw_command_profile.py \
  tests/test_p1_73b_cmw_parsers.py
```

**Step 3: 最小 GREEN**

- 把命令字面量、source reference、参数 builder 和 response parser 放进 profile。
- 原型中无出处的 `ETHRoughput`、RSRP、SINR、CQI 解释保持诊断 raw/unknown，不得进入正式 KPI。
- 所有 builder 同时供 fake/real 使用；模拟模式不另造命令。

**Step 4: 运行 GREEN 并提交**

```bash
./.venv/bin/python -m pytest -q \
  tests/test_p1_73b_cmw_command_profile.py \
  tests/test_p1_73b_cmw_parsers.py \
  tests/test_p1_54_kpi_valid_contract.py
git add api-service/app/hal/cmw500_command_profile.py \
  api-service/app/hal/cmw500_base_station.py \
  api-service/tests/test_p1_73b_cmw_command_profile.py \
  api-service/tests/test_p1_73b_cmw_parsers.py
git commit -m "feat: add sourced CMW500 LTE command profile"
```

### Task 7：让 connect 只连接和识别，不修改仪表

**Files:**

- Modify: `api-service/app/hal/cmw500_base_station.py`
- Create: `api-service/tests/test_p1_73b_cmw_connect_lifecycle.py`
- Modify: `api-service/tests/test_p1_51_no_guessed_instrument_ip.py`
- Modify: `api-service/tests/test_visa_rm_ownership.py`

**Step 1: 写 RED**

断言 `connect()` 只允许打开 session、`*IDN?`、固件查询、选件查询和必要的只读状态查询；不得发送 `*CLS`、`PRESet`、route 写、CELL ON/OFF。型号不匹配、版本不可解析、选件查询失败均记录能力 unknown，不能伪装支持。

还要覆盖 session/RM 关闭所有权与异常路径资源释放。

**Step 2: RED → GREEN**

```bash
cd api-service
./.venv/bin/python -m pytest -q \
  tests/test_p1_73b_cmw_connect_lifecycle.py \
  tests/test_p1_51_no_guessed_instrument_ip.py \
  tests/test_visa_rm_ownership.py
```

最小实现：移除 connect 中的 preset/route 写；新增严格 identity snapshot。型号 + 固件 + 选件是唯一正式能力输入，不加入 LabProfile 名称、外部 RF router 或功率预算。

**Step 3: 提交**

```bash
git add api-service/app/hal/cmw500_base_station.py \
  api-service/tests/test_p1_73b_cmw_connect_lifecycle.py \
  api-service/tests/test_p1_51_no_guessed_instrument_ip.py \
  api-service/tests/test_visa_rm_ownership.py
git commit -m "fix: make CMW500 connect read-only"
```

### Task 7A：持久化并冻结 CMW500 内部 2×2 route profile

**Files:**

- Create: `api-service/app/hal/base_station_adapter_profile.py`
- Create: `api-service/app/services/base_station_adapter_profile.py`
- Modify: `api-service/app/schemas/instrument.py`
- Modify: `api-service/app/api/instrument.py`
- Modify: `api-service/app/api/commissioning.py`
- Modify: `api-service/app/services/test_case_runner.py`
- Modify: `api-service/app/services/instrument_test_lease.py`
- Create: `api-service/tests/test_p1_73b_cmw_adapter_profile.py`
- Modify: `api-service/tests/test_instrument_api.py`
- Modify: `api-service/tests/test_commissioning_smoke.py`
- Modify: `api-service/tests/test_commissioning_adhoc.py`
- Modify: `api-service/tests/test_commissioning_strict_gate_overrides.py`
- Modify: `api-service/tests/test_instrument_test_lease.py`
- Modify: `gui/src/App.tsx`
- Create: `gui/src/types/cmwAdapterProfileTruth.test.ts`
- Modify: `api/openapi.yaml`
- Modify: `gui/src/types/api.generated.ts`

**Step 1: 写 RED**

定义唯一持久化形态：所选 LabProfile 的 `baseStation` binding 先按其 `category_id` 解析现有唯一
`InstrumentConnection`，再从
`connection_params["base_station_adapter_profile"]` 读取严格 schema：

```python
class Cmw500Lte2x2InternalRoute(BaseModel):
    model_config = ConfigDict(extra="forbid")
    pcc_bb_board: str
    rx_connector: str
    rx_converter: str
    tx1_connector: str
    tx1_converter: str
    tx2_connector: str
    tx2_converter: str

class BaseStationAdapterProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[1]
    adapter: Literal["cmw500"]
    lte_2x2_internal_route: Cmw500Lte2x2InternalRoute

class BaseStationAdapterProfileResolution(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[1]
    adapter: Literal["uxm", "cmw500"] | None
    status: Literal["diagnostic_unbound", "not_applicable", "configured"]
    execution_mode: Literal["real", "simulated"]
    profile: BaseStationAdapterProfile | None
```

组合白名单只允许 `uxm/not_applicable/profile=None`、
`cmw500/configured/profile.adapter=cmw500`，或仅限白名单 Mock 且两端型号均未配置时的
`adapter=None/diagnostic_unbound/simulated/profile=None`。`diagnostic_unbound` 只允许既有通用 Mock
诊断，不得进入 CMW/UXM adapter 专属配置、正式 evidence 或 KPI/verdict。
adapter identity 必须与 HAL 实际装载链完全同源：在同一事务锁定 `baseStation`
`InstrumentCategory`，读取其 `selected_model_id`，并要求它与所选 LabProfile binding 的
`instrument_model_id` 精确一致。真实模式下两者必须均非空；白名单 Mock 仅在两者都为空时允许
上述 `diagnostic_unbound`，只缺一端仍 fail-loud。只用非空的唯一 `InstrumentModel.model` 调用
`instrument_hal_service.get_real_driver_class(category_key, model_name)`，读取注册类固定
`adapter_id`。不得从型号/类名前缀、endpoint 或 connection params 推断。unknown、重复注册、
binding/selected model/registry/profile adapter 冲突均 fail-loud。

覆盖：CMW 完整 profile 可保存/读取；CMW 缺字段/profile、extra、空白、TX connector 复用、
TX converter 复用、非 CMW profile、LabProfile binding 与 InstrumentConnection 不一致均在硬件 I/O 前拒绝。GUI 提供
七个显式字段，不要求操作员编辑自由 JSON。该 profile 只是内部 route 输入，不进入
型号/固件/选件能力准入，也不扩展为外部 RF router。

新增唯一 `freeze_base_station_adapter_profile(db, hal, execution, selected_lab_profile)`：在同一事务
锁定 execution、所选 LabProfile、其 `baseStation` binding 指向的 `InstrumentCategory` 和唯一
InstrumentConnection；先核对 binding model 与 `InstrumentCategory.selected_model_id`，再解析
registry class/adapter，校验规范 profile 后把 resolution、profile、model/connection identity 与
digest 写入 server-owned execution config。取得 Remote 前还必须只读检查当前
`hal.drivers["baseStation"]`：不存在则阻断；以 `instrument_hal_service.is_mock_driver(driver)` 作为
唯一 real/mock 判据。real 必须满足 `type(driver) is registry_class`；白名单 Mock 可执行诊断，
但必须冻结 `execution_mode=simulated`，且 Task 12/14 的所有正式消费者永久排除。已配置型号的
Mock 仍按同一 binding/selected model/registry 解析期望 adapter，CMW 仍要求完整七字段 profile，
UXM 仍为 `not_applicable`；两端型号都未配置时只允许 `diagnostic_unbound`。不属于权威 Mock
白名单、又不与 registry real class 精确一致的类一律阻断。检查不得 connect 或发送 SCPI。
已有规范快照时幂等返回且绝不覆盖，但仍要核对当前 loaded driver 分类与冻结 identity；缺失、
选择漂移、绑定漂移或冲突均在首次硬件 I/O 前 fail-loud。

数据库冻结不能替代进程内 HAL mutation 锁。新增纯只读
`validate_frozen_base_station_before_remote(hal, frozen_resolution)`，四类入口都必须把它作为
`instrument_test_lease(validate_before_remote=...)` 的回调传入；回调由 lease 在 `_coordinated`
锁内、metrics cache clear 与 Remote acquire 之前执行，重新核对当前 loaded driver 的权威 Mock 分类、
精确 real class、adapter id 与冻结 model/profile identity。冻结后到入锁前发生 HAL reload/model switch
必须在零仪器 I/O 时 fail-loud。回调不得查询当前数据库来改写快照；嵌套 lease 只能复用外层已绑定的
同一冻结 identity，否则阻断，不能绕过原子复核。

冻结条件必须按权威 adapter 收窄：`cmw500` 缺严格七字段即阻断；`uxm` 不要求、不读取 CMW
profile，冻结显式 `uxm/not_applicable/profile=None` 后继续现有 UXM 配置、route 与证据链；adapter
unknown/冲突才阻断。不得用统一“有 profile/无 profile”布尔决定两种仪表。

现有活入口并不共用同一 runner，因此必须逐条接线：正式 `test_case_runner._run_case`；
`/commissioning/sessions` 新建 execution；commissioning 单相位在进入 lease 前；adhoc execution
建行后且 dispatch 前；run-all 在外层 lease 前。历史 session 若尚未发生硬件 I/O，可由首次硬件
phase 幂等冻结；REPORT-only 或已有 measurements/phase progress 的旧 execution 缺快照时不得从
当前 DB 补证，只能 UNKNOWN。后续 driver/evidence 只消费冻结快照；执行中修改 connection params
不得改变旧 execution，历史/报告也不得从当前数据库补 route。

RED 分别覆盖 formal runner、session create/首次 phase、adhoc 和 run-all，证明四条路径都在 lease
取得 Remote 前完成同一冻结；并覆盖第二次调用不覆盖、profile 在执行中被修改不漂移、REPORT-only
旧执行不补证。四条入口都要成对覆盖：CMW 缺 profile 必须阻断且不 dispatch；UXM 无 CMW profile
必须冻结 `not_applicable` 并正常进入既有 lease/dispatch。另以双向 RED 覆盖 binding=CMW 但
`selected_model_id`=UXM、binding=UXM 但 `selected_model_id`=CMW，以及 registry class 与当前 loaded
driver class 不一致；三者都必须在 lease/dispatch 前阻断且零仪器 I/O。unknown/冲突 adapter
同样不得放行。四条入口还要成对覆盖：registry real class mismatch 阻断；权威白名单 Mock 在
显式 CMW/UXM 配置下可以执行诊断但 resolution 标为 simulated、正式值全为 UNKNOWN/N/A；两端
型号都为空的既有 Mock 冻结 `diagnostic_unbound` 后仍可跑通用 commissioning/adhoc/run-all，
不得运行 adapter 专属分支或形成正式判决；非白名单 fake 不能借 duck typing 放行。
另加竞态 RED：冻结 CMW 后、进入 lease 前把 active driver reload 为 UXM（以及反向），证明
`validate_before_remote` 在 `_coordinated` 锁内拒绝且 acquire/clear-cache/SCPI 调用次数均为零；
同 identity 无漂移时只校验不发送命令并正常 acquire。

**Step 2: RED → GREEN 并提交**

```bash
cd api-service
./.venv/bin/python -m pytest -q \
  tests/test_p1_73b_cmw_adapter_profile.py \
  tests/test_instrument_api.py \
  tests/test_commissioning_smoke.py \
  tests/test_commissioning_adhoc.py \
  tests/test_commissioning_strict_gate_overrides.py \
  tests/test_instrument_test_lease.py
cd ../gui
node --test src/types/cmwAdapterProfileTruth.test.ts
npm run build
cd ..
git add api-service/app/hal/base_station_adapter_profile.py \
  api-service/app/services/base_station_adapter_profile.py \
  api-service/app/schemas/instrument.py \
  api-service/app/api/instrument.py \
  api-service/app/api/commissioning.py \
  api-service/app/services/test_case_runner.py \
  api-service/app/services/instrument_test_lease.py \
  api-service/tests/test_p1_73b_cmw_adapter_profile.py \
  api-service/tests/test_instrument_api.py \
  api-service/tests/test_commissioning_smoke.py \
  api-service/tests/test_commissioning_adhoc.py \
  api-service/tests/test_commissioning_strict_gate_overrides.py \
  api-service/tests/test_instrument_test_lease.py \
  gui/src/App.tsx \
  gui/src/types/cmwAdapterProfileTruth.test.ts \
  api/openapi.yaml \
  gui/src/types/api.generated.ts
git commit -m "feat: persist CMW500 internal route profile"
```

### Task 8：实现 CMW 内部 1CC-nx2 route 的写后回读

**Files:**

- Modify: `api-service/app/hal/cmw500_base_station.py`
- Create: `api-service/tests/test_p1_73b_cmw_route_truth.py`

**Step 1: 写 RED**

覆盖：

- 只从 Task 7A 的 execution-frozen adapter profile 取得完整
  `pcc_bb_board/rx_connector/rx_converter/tx1_connector/tx1_converter/tx2_connector/tx2_converter`
  并构造 TRO flexible 命令；不得读取当前 DB、沿用当前 applied route 或选择默认模块；
- 写后 `ROUTe:LTE:SIGN<i>?` 回读精确匹配 scenario、PCCBBBoard 和完整 RX/TX1/TX2 connector/converter 元组；
- TX1/TX2 的 connector 必须不同，converter/TX module 也必须不同；两个条件分别验证，不能只比较字符串元组；
- 固件低于 V3.5.40、缺 KS520、任一字段缺失、TX connector/converter 复用、readback 不一致、错误队列非空均在正式采样前失败；
- 不把外部 RF router 状态加入这个结果。

**Step 2: RED → GREEN**

```bash
cd api-service
./.venv/bin/python -m pytest -q tests/test_p1_73b_cmw_route_truth.py
```

实现返回结构化 `BaseStationRouteResult`，包含 requested/applied/source_reference/confirmed/reason/exchange_ids。只有 `confirmed=True` 才能进入正式证据。

**Step 3: 提交**

```bash
git add api-service/app/hal/cmw500_base_station.py \
  api-service/tests/test_p1_73b_cmw_route_truth.py
git commit -m "feat: confirm CMW500 internal LTE 2x2 route"
```

### Task 9：实现配置、错误队列与超时/取消的安全状态机

**Files:**

- Modify: `api-service/app/hal/cmw500_base_station.py`
- Create: `api-service/tests/test_p1_73b_cmw_state_machine.py`
- Modify: `api-service/tests/test_rule_gates.py`

**Step 1: 写 RED**

列全状态与失败路径：connected/read-only → identity/capability verified → SAFE_IDLE confirmed →
configure → route confirmed → CELL ON → UE attached/connected → measurement window → SAFE_IDLE/local。
配置和 route 的先后顺序必须服从厂商前置条件，但二者都不得越过 SAFE_IDLE。覆盖：

- connect 后先读取 Cell/RF；已经 OFF 才可继续。若为 ON，只允许发送有手册出处的关闭动作，
  且必须回读确认 OFF；unknown、关闭失败或取消均在首条配置/route 写入前停止；
- 每组写操作后 bounded error drain；非零错误使返回失败。
- `*OPC?` 只表示完成，不能单独构成成功。
- VISA timeout 必须在成功、异常、取消、设备拒绝四条路径恢复。
- attach 轮询不得 `except: pass`；状态解析只接受手册枚举，不能用宽松 substring 把 ATT 当 CONN。
- 写失败时内部缓存不得提前伪装已应用；cleanup 多失败聚合并返回。
- cancel 后仍执行安全 cleanup，但不把失败 cleanup 静默覆盖业务错误。
- CMW 驱动实现共享 async `acquire_remote_control()` / `release_remote_session()` 契约；前者的控制动作、
  返回值与确认信号必须逐项引用厂商手册，后者只确认本次活跃 VISA/HiSLIP transport 是否精确关闭。
  两者都不能用会话形状、disconnect 或未抛异常推断；前面板 Local 没有明确厂商动作与确认时保持
  unknown/Warning。每次真实 session 建立成功后由驱动生成新的 opaque UUID `session_token`，
  `acquire_remote_control()` 返回该 token；`release_remote_session(expected_session_token)` 必须核对
  驱动当前 token、关闭对应 session，并在结果中返回同一 token。session/token 缺失或错配时仍保守
  尝试关闭当前 transport，但 release 不得 confirmed；lease 活跃期间不得透明重连或复用旧 token。
  共享租约在 P1-73C 才接入并消费这些结果。

**Step 2: RED → GREEN**

```bash
cd api-service
./.venv/bin/python -m pytest -q \
  tests/test_p1_73b_cmw_state_machine.py \
  tests/test_rule_gates.py
```

**Step 3: 提交**

```bash
git add api-service/app/hal/cmw500_base_station.py \
  api-service/tests/test_p1_73b_cmw_state_machine.py \
  api-service/tests/test_rule_gates.py
git commit -m "fix: make CMW500 LTE state transitions fail closed"
```

### Task 10：实现同一 Extended BLER 窗口的吞吐与 BLER 真值

**Files:**

- Modify: `api-service/app/hal/base_station.py`
- Modify: `api-service/app/hal/cmw500_base_station.py`
- Create: `api-service/tests/test_p1_73b_cmw_extended_bler_window.py`
- Modify: `api-service/tests/test_p1_54_kpi_valid_contract.py`

**Step 1: 写 RED**

定义厂商无关测量窗口结果：

```python
@dataclass(frozen=True)
class BaseStationMeasurementWindow:
    window_id: str
    started_at: datetime
    completed_at: datetime | None
    metrics: ThroughputMetrics
    preclear_off_confirmed: bool
    running_confirmed: bool
    ready_confirmed: bool
    closed_off_confirmed: bool
    evidence: tuple[InstrumentEvidenceItem, ...]
    confirmed: bool
    reason: str
```

CMW 测试要求同一 window 中：ABORt→STATE OFF pre-clear → configure → INITiate→STATE RUN →
自然完成或 STOP→STATE RDY → Absolute/Relative fetch → ABORt→STATE OFF final close。
每个写动作都消费传输结果、错误队列和紧邻状态查询；不能用 await 完成、`*OPC?` 或 finally 推导。
`ThroughputAver` 从 kbit/s 显式除以 1000 得 Mbps；BLER 取 Relative 第 4 字段并保持百分比口径。
任一 KPI 字段缺失时该指标独立 unknown，不得用另一个指标替代，也不得保留原型 fallback；但
`confirmed=True` 还必须要求 preclear/RUN/RDY/final OFF 四项全部精确 true。

timeout、取消、fetch 异常或 STOP 失败时仍尝试 ABORt 并确认 OFF；最终 OFF 未确认则返回结构化
失败，调用方不得移动到下一方位、切换 F64 或启动另一窗口。先前取得的数值只留诊断，整次正式
throughput/BLER 均 UNKNOWN/N/A，并把 STOP/ABORt/STATE/error-drain 的全部失败聚合到 cleanup。

**Step 2: RED → GREEN**

```bash
cd api-service
./.venv/bin/python -m pytest -q \
  tests/test_p1_73b_cmw_extended_bler_window.py \
  tests/test_p1_54_kpi_valid_contract.py
```

**Step 3: 提交**

```bash
git add api-service/app/hal/base_station.py \
  api-service/app/hal/cmw500_base_station.py \
  api-service/tests/test_p1_73b_cmw_extended_bler_window.py \
  api-service/tests/test_p1_54_kpi_valid_contract.py
git commit -m "feat: measure sourced CMW500 LTE throughput and BLER"
```

### Task 11：实现 debug inherit 与正式能力默认关闭

**Files:**

- Modify: `api-service/app/models/instrument.py`
- Modify: `api-service/app/schemas/instrument.py`
- Modify: `api-service/app/api/instrument.py`
- Create: `api-service/alembic/versions/d73b5f6a1c20_add_cmw_formal_capability_approval.py`
- Modify: `api-service/app/services/base_station_adapter_profile.py`
- Modify: `api-service/app/hal/cmw500_base_station.py`
- Modify: `api-service/app/services/instrument_hal_service.py`
- Create: `api-service/tests/test_p1_73b_cmw_capability_admission.py`
- Create: `api-service/tests/test_p1_73b_cmw_inherit_debug.py`

**Step 1: 写 RED**

断言：

- CMW adapter 可由 registry 创建；
- 正式 LTE 2×2 能力默认 false；
- 唯一 rollout approval 写源为 `InstrumentConnection.cmw500_lte_2x2_formal_enabled` 非空布尔列，
  migration revision=`d73b5f6a1c20`、down_revision=`c73a19f4e602`；数据库默认 false，迁移既有行
  精确回填 false 后移除 server default，ORM/创建服务继续显式写 false；另有 server-owned
  `cmw500_lte_2x2_formal_updated_at`；
- 专用 `PUT /api/v1/instruments/connections/{connection_id}/formal-capabilities/cmw500-lte-2x2`
  只接受 `{enabled: bool}`，锁定 connection/category/model，要求逻辑类别为 `baseStation` 且 registry
  adapter 为 CMW500，随后更新布尔与服务器时间。通用 connection create/update schema 不接受这两个
  字段，`connection_params` 中的同名/相似键不生效，环境变量和进程内 flag 也不是候选真源；
- adapter profile freeze 在同一事务锁住同一 connection，把 approval 的 connection id、enabled、
  updated_at 冻结到 server-owned execution snapshot；执行前 readiness 从当前所选 LabProfile binding
  解析到的同一 connection 显式列做只读预览，runner 只从该列冻结，execution 响应与正式 evaluator
  只消费冻结快照。执行中途启停只影响后续 execution，不重写旧 execution 或历史结果；
- 显式启用后仍必须使用当前会话只读 identity/firmware/options snapshot，满足型号、固件、KS520，
  以及本次请求 FDD 对应 KS500 / TDD 对应 KS550；
  缺任一项给 Warning/unknown，不声称 ready；KS500-only 不得放行 TDD，KS550-only 不得放行 FDD；
- 选件判据紧邻引用 CMW LTE UE User Manual §2.2.1 第 17–19 页；不得用“任一 LTE 基础选件”
  泛化本次 duplex 的准入；
- 外部 RF router 的存在与否不会改变能力结果；
- `inherit` 只读核对当前 cell/route/状态，不做 preset，且 evidence gate 永远不授予 formal acceptance。
- RED 覆盖默认 false、专用 endpoint 启停、错误 category/model 422、通用 connection update 与
  `connection_params` 同名键无法启用、执行冻结后数据库开关变化不改旧 execution，以及 readiness/
  runner/evaluator 三方同源但分时：readiness 读当前列、runner 冻结、execution/evaluator 读快照；
  删除任一持久化生产/冻结/消费站点均保持 UNKNOWN。

**Step 2: RED → GREEN**

```bash
cd api-service
./.venv/bin/python -m pytest -q \
  tests/test_p1_73b_cmw_capability_admission.py \
  tests/test_p1_73b_cmw_inherit_debug.py
```

**Step 3: 提交与 P1-73B 回归**

```bash
git add api-service/app/hal/cmw500_base_station.py \
  api-service/app/models/instrument.py \
  api-service/app/schemas/instrument.py \
  api-service/app/api/instrument.py \
  api-service/alembic/versions/d73b5f6a1c20_add_cmw_formal_capability_approval.py \
  api-service/app/services/base_station_adapter_profile.py \
  api-service/app/services/instrument_hal_service.py \
  api-service/tests/test_p1_73b_cmw_capability_admission.py \
  api-service/tests/test_p1_73b_cmw_inherit_debug.py
git commit -m "feat: gate CMW500 LTE 2x2 formal capability"

./.venv/bin/python -m pytest -q \
  tests/test_p1_73b_cmw_command_profile.py \
  tests/test_p1_73b_cmw_parsers.py \
  tests/test_p1_73b_cmw_connect_lifecycle.py \
  tests/test_p1_73b_cmw_adapter_profile.py \
  tests/test_p1_73b_cmw_route_truth.py \
  tests/test_p1_73b_cmw_state_machine.py \
  tests/test_p1_73b_cmw_extended_bler_window.py \
  tests/test_p1_73b_cmw_capability_admission.py \
  tests/test_p1_73b_cmw_inherit_debug.py \
  tests/test_p1_51_no_guessed_instrument_ip.py \
  tests/test_p1_54_kpi_valid_contract.py \
  tests/test_rule_gates.py
./.venv/bin/python -m compileall -q app tests
./.venv/bin/alembic heads
cd ..
git diff --check
```

fresh 内审 P1=0 后更新 roadmap，单独 Ready PR。没有真机验证时以 Warning 说明，不把 P1-73B 标成 Hardware Blocked，也不得提前打开正式能力默认值。

---

## P1-73C：OTA、证据、报告与 GUI 集成

### Task 12：新增版本化 BaseStationExecutionEvidence 正式白名单

**Files:**

- Create: `api-service/app/services/mimo_ota/base_station_execution_evidence.py`
- Create: `api-service/tests/test_p1_73c_base_station_execution_evidence.py`
- Create: `api-service/tests/test_p1_73c_base_station_metric_trust.py`
- Modify: `api-service/app/services/execution_scpi_evidence.py`

**Step 1: 写 RED**

规范快照只接受固定 schema，例如：

```python
class BaseStationExecutionEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[1]
    adapter: Literal["uxm", "cmw500"]
    identity: BaseStationIdentitySnapshot
    formal_capability_approval: BaseStationFormalCapabilityApprovalSnapshot
    mode: Literal["dispatch"]
    config_confirmed: Literal[True]
    route_confirmed: bool | None
    requested_config: BaseStationRequestedConfigSnapshot
    requested_route: BaseStationRequestedRouteSnapshot | None
    applied_route: BaseStationAppliedRouteSnapshot | None
    requested_positions: list[PositionSnapshot]
    current_measurement_attempt_id: str | None
    current_measurement_attempt_state: Literal["running", "completed", "failed", "cancelled"] | None
    measurement_windows: list[BaseStationMeasurementWindowEvidence]
    control_releases: list[BaseStationControlReleaseResult]
    exchange_ids: list[str]

class BaseStationMeasurementWindowEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")
    window_id: str
    measurement_attempt_id: str
    lease_id: str
    session_token: str
    config_digest: str
    route_digest: str | None
    position: PositionSnapshot
    ue_link_state: Literal["connected"]
    started_at: datetime
    completed_at: datetime
    preclear_off_confirmed: Literal[True]
    running_confirmed: Literal[True]
    ready_confirmed: Literal[True]
    closed_off_confirmed: Literal[True]
    cleanup: BaseStationCleanupResult
    lifecycle_exchange_ids: list[str]
    metrics: dict[str, BaseStationMetricEvidence]
```

`BaseStationFormalCapabilityApprovalSnapshot` 只接受固定字段：`schema_version=1`、
`status: Literal["configured", "not_applicable"]`、冻结的 `instrument_connection_id`、
`capability: Literal["cmw500_lte_2x2"] | None`、`enabled: bool | None` 和服务器 `updated_at`。
组合白名单只允许 CMW 的 `configured/cmw500_lte_2x2/bool/非空 updated_at`，或 UXM 的
`not_applicable/None/None/None`；CMW 正式 evaluator 要求 `enabled is True`，并要求 connection id 与
Task 7A 冻结 adapter profile 的来源相同。客户端声明、当前数据库新值、环境变量或
`connection_params` 不能补齐/覆盖该快照。UXM 不被 CMW rollout 开关阻断。

正式判据必须：real driver、获准 adapter/profile、CMW rollout approval=true、identity 完整、dispatch、config readback、自身需要的 route readback，以及 current `measurement_attempt_id` 的 state 精确为 `completed` 且所有请求方位均有唯一 window；每个 current-attempt window 自带的结构化 MEASURE cleanup 的 stop signaling、SAFE_IDLE 两项精确为 true，且它的 `lease_id` 在 `control_releases` 中恰有一条同 attempt id、同 lease id、同 adapter、同驱动 opaque `session_token`、`remote_session_acquired_confirmed` 与 `transport_session_released_confirmed` 都精确为 true 的结果；window 内每条 KPI/lifecycle exchange 也必须携带同 attempt id/token。`front_panel_local_confirmed` 没有厂商证据时保持 null/Warning，不得由 close 推断，也不作为测量真值的替代门。CMW 必须同时携带 Task 7A 的 execution-frozen requested route、逐字段匹配的 applied route 和 route confirmed；UXM 只消费自己的既有权威配置链。current attempt 内任何 extra/missing/重复 lease result、跨 attempt/lease/token 替换、token 变化或复用、legacy CMW/inherit/mock/方位集合失配，或本 window cleanup/transport release 的 `False`/`None`/异常/仅无异常返回，均 false；其他 attempt 的 window/release 只保留审计，不参与 current attempt 的唯一性检查。

本 Task 同时实现设计稿 §4.2 的唯一逐指标入口：

```python
evaluate_base_station_metric_trust(
    evidence,
    metric_name,
    expected_config,
    expected_position,
) -> FormalMetricTrust
```

它不能只验证 envelope 或 `kpi_valid`：必须在同一个规范 window 中精确核对
`config_digest`、CMW 所需的 `route_digest`、position、UE connected、窗口起止、pre-clear OFF、
RUN、RDY、final OFF、指标字段/单位与各自 exchange IDs。任何 lifecycle confirmation 缺失或不为
精确 true 时，该 window 的所有正式指标均不可信。`expected_config` 和 `expected_position` 只来自本次执行冻结的 requested config /
requested positions，不得从当前 TestCase、LabProfile 或仪表数据库回填历史执行。

**Step 2: RED → GREEN 并提交**

```bash
cd api-service
./.venv/bin/python -m pytest -q \
  tests/test_p1_73c_base_station_execution_evidence.py \
  tests/test_p1_73c_base_station_metric_trust.py
git add api-service/app/services/mimo_ota/base_station_execution_evidence.py \
  api-service/app/services/execution_scpi_evidence.py \
  api-service/tests/test_p1_73c_base_station_execution_evidence.py \
  api-service/tests/test_p1_73c_base_station_metric_trust.py
git commit -m "feat: add formal base station execution evidence"
```

### Task 13：把 CMW 测量窗口接入通用 MIMO 方位扫描

**Files:**

- Modify: `api-service/app/services/mimo_ota/executors/measure.py`
- Modify: `api-service/app/services/mimo_ota/cleanup.py`
- Modify: `api-service/app/services/instrument_test_lease.py`
- Modify: `api-service/app/hal/uxm_base_station.py`
- Modify: `api-service/app/hal/cmw500_base_station.py`
- Modify: `api-service/app/services/test_case_runner.py`
- Modify: `api-service/app/api/commissioning.py`
- Modify: `api-service/tests/test_p1_73a_vendor_neutral_measure.py`
- Create: `api-service/tests/test_p1_73c_cmw_measure_integration.py`
- Create: `api-service/tests/test_p1_73c_base_station_cleanup_truth.py`
- Create: `api-service/tests/test_p1_73c_base_station_control_release.py`
- Create: `api-service/tests/test_p1_73c_commissioning_control_release.py`
- Modify: `api-service/tests/test_instrument_test_lease.py`
- Modify: `api-service/tests/test_commissioning_smoke.py`
- Modify: `api-service/tests/test_commissioning_adhoc.py`
- Modify: `api-service/tests/test_commissioning_strict_gate_overrides.py`
- Modify: `api-service/tests/test_p1_61_report_final_state_truth.py`
- Modify: `api-service/tests/test_p1_59_ca_throughput_truth.py`

**Step 1: 写 RED**

使用 fake transport 走完整 PRECHECK/MEASURE：CMW 配置、内部 route、UE attach、每方位 Extended BLER window、F64/转台既有链、cleanup。覆盖：

- 请求方位全集精确匹配；重复/额外/缺失 window fail-closed；
- 每次 MEASURE 调用在 lease/硬件 I/O 前生成新的 server-owned UUID `measurement_attempt_id`，
  并在同一行锁事务把 execution 的 current id 指向它、state 置 `running`；已有 running attempt 时
  409，不允许两个硬件 MEASURE 并发。所有本次 window、exchange、cleanup 和 release 都必须携带
  该 attempt id；只有匹配 cleanup/release 持久化完成后才置 `completed`，异常/取消/release失败写
  `failed`/`cancelled`。重跑 MEASURE 不覆盖旧 attempt，旧数据只审计；
  current attempt 失败或取消后不得回退到此前成功 attempt，正式值保持 UNKNOWN/N/A；
- 每方位吞吐与 BLER 各自消费同一 window 的证据；
- 每个 window 在产生时冻结 config digest、route digest、position、UE link state、起止时间和
  pre-clear/RUN/RDY/final OFF 及 metric exchange IDs；交换另一配置/route/方位的结构合法 window
  也必须 fail-closed；
- STOP 被拒、STOP 后非 RDY、final ABORt 被拒或最终状态非 OFF 时 window 不 confirmed，整次正式
  指标 UNKNOWN，且在原方位立即终止，不得移动转台、切 F64 或开始下一 window；
- route/config/error/cleanup 任一 unknown 时正式 throughput/BLER 均 UNKNOWN；
- shared cleanup 对 `stop_signaling()` 与 SAFE_IDLE 回读逐项要求 `is True`；`False`、`None`
  和异常都写入 warnings 与 `BaseStationCleanupResult`，不得因 await 完成或 finally 已运行而确认；
- shared cleanup 必须删除基站 `disconnect()` 调用；基站 session 在 stop/SAFE_IDLE 后继续存活，
  只允许最外层 `instrument_test_lease` 的 `release_remote_session()` 关闭。positioner 等其他仪表的
  既有安全断开所有权不受此规则改变；
- `measure.py` 消费该结构化结果并只由 stop/SAFE_IDLE 派生 evidence cleanup；任一失败
  时保留原业务错误全文、追加 cleanup warning，阻止正式 KPI/报告，且不得掩盖其他仪表 cleanup；
- outer lease 生成不可由请求体传入的 UUID `lease_id`；UXM/CMW 驱动在真实新 session 建立后生成
  独立 opaque UUID `session_token`，`acquire_remote_control()` 返回结构化
  `BaseStationRemoteSessionResult`。lease 通过 server-only context 把两者交给所有 SCPI exchange 与
  MEASURE window writer；window 将本次 attempt id 与 cleanup 一并冻结。多次 commissioning MEASURE
  产生不同 attempt/lease id，后一次 cleanup/release 只能追加，绝不能覆盖或替前一次 window 的证据；
  evaluator 只选择 execution 的 current attempt，并在该 scope 内要求唯一方位全集与唯一 release，
  不把旧 attempt 的额外 window/release 当冲突；
- MEASURE owner 必须把刚持久化的 current attempt id 作为 server-only
  `instrument_test_lease(measurement_attempt_id=...)` 参数传入；lease outcome 原样带回该 id，调用方
  不得在退出后从“当前指针”重猜，以免并发/重试把 release 归到错误 attempt；
- `instrument_test_lease` 把当前 `_uxm_driver` 收敛为 vendor-neutral baseStation resolver；CMW 驱动
  必须实现同一 async Remote/session-release 契约，缺方法、返回 `False`/`None` 或抛异常都不得静默跳过；
- formal runner 与 commissioning 单相位/adhoc/run-all 每个控制 baseStation 的 lease 都必须从 execution
  冻结快照构造 Task 7A 的 `validate_before_remote`；回调缺失、当前 loaded driver 与冻结 adapter/profile
  不一致时在协调锁内、Remote/cache clear/I/O 前阻断，不得仅依赖 lease 外的旧检查；
- control release 只在租约退出时形成 `BaseStationControlReleaseResult`。`instrument_test_lease` 必须
  `async with ... as lease_outcome` 暴露同一个 server-owned outcome handle；handle 在块内不可伪造
  `transport_session_released_confirmed`，只在 `__aexit__` 完成真实 session release 后可读。close 成功
  不得写 `front_panel_local_confirmed=true`；该字段没有厂商确认时保持 null 并产生 Warning。formal runner 与 commissioning
  的单相位、adhoc、run-all 三类直接 lease owner 都必须在退出后调用同一个幂等持久化 helper，以
  独立事务按 `measurement_attempt_id`/`lease_id` 追加到各自 execution；成功与失败都保存结构化结果，不得覆盖别的 lease、
  只在异常路径写自由文本或从另一个入口补写；每个 measurement window 在产生时冻结同一 lease id、
  驱动 acquire token 与该 window 的 cleanup；
  MEASURE lease 的 release 必须带非空 current attempt id；不产生测量的 PRECHECK/ANALYSIS/REPORT
  lease（若仍存在）只能写 `measurement_attempt_id=None`，永远不能满足正式 measurement release 门；
- formal runner 把执行链末尾连续的 `MIMO_OTA_ANALYSIS` 与 `MIMO_OTA_REPORT` 一起从租约内延迟，
  持久化同 measurement lease 的 control release 后才严格按 ANALYSIS → REPORT dispatch 并持久化最终 `validation_pass`、
  正式投影和报告。租约内不得先写一份 UNKNOWN Analysis 后只重建公开 projection；若 ANALYSIS/
  REPORT 不是末尾规范顺序则 fail-loud；
- commissioning run-all 同样在 lease 内只跑到 MEASURE，延迟末尾 ANALYSIS/REPORT；单相位和 adhoc
  若目标是 ANALYSIS 或 REPORT，不得再取得空基站 lease，只能在已有 MEASURE window 的同-id release
  已持久化后 dispatch；没有匹配结果时相位可诊断执行但正式判决保持 UNKNOWN/N/A。MEASURE 等硬件
  相位完成后也必须先持久化匹配的 control release 才能构造响应；release 失败时不 dispatch 延迟相位、不发布正式
  历史或报告，并保留原业务 winner 与错误全文；
- ANALYSIS/REPORT-only 调用只能读取 current measurement attempt，不得新建或切换 attempt；新 MEASURE
  在任何 I/O 前切换 current 指针，因此即使它在首个 window 前失败，旧成功 attempt 也不能重新发布；
- RED 明确证明调用顺序为 `stop_signaling`/SAFE_IDLE → `release_remote_session` → transport close，
  `release_remote_session` 进入时原 VISA/HiSLIP session 仍存在；MEASURE 不得提前调用
  `disconnect()`，租约也不得把“session 已经是 None”当作本次交还成功；
- 用语义准确的共享 `release_remote_session()` 取代基站正式路径上的误导性
  `release_to_local_control()`：它接收 lease acquire 得到的 `expected_session_token`。本次调用开始时
  必须存在活跃 VISA/HiSLIP session，且驱动内当前 session token 与 expected 精确一致、该 session 的
  close 精确成功后才确认 transport release；session/token 缺失或不匹配、close 失败、取消或仅清空内部
  引用均不得确认。UXM 现有兼容方法可保留为 deprecated wrapper，但不能产生 Local=true；租约只
  消费结构化公共结果，不读取驱动私有字段，也不从 status、finally 或“已断开”反推前面板 Local；
- 驱动在 lease 活跃期间禁止透明重连；连接丢失即令当前窗口失败。若底层确实换成新 session，必须
  生成新 token；release 即使为安全而关闭当前新 session，也必须返回 token mismatch/unconfirmed，
  旧 window 永久 UNKNOWN。RED 要把 acquire 后替换 fake VISA session/复用旧 token 的变异分别跑红；
- control-session release 失败时保留原业务 winner 与错误全文，再追加 release 失败；不能从
  disconnect、finally、context manager 正常退出或执行终态推导 transport 已释放或前面板 Local；
- 取消、attach timeout、window timeout、F64 失败均无假成功；
- UXM 仍通过同一个 executor 且原回归行为不变。

RED 还要覆盖：CMW 缺 Remote/session-release 契约时 fail-loud 而不是跳过；取得 Remote 失败、
transport close 失败、异常、取消与成功 release；close 成功仍必须证明 front-panel Local 为 unknown
而非 true。失败时不发布正式历史/报告且保留原业务错误，成功时只有 measurement window 绑定的
同-id release 由实际 lease owner 持久化后才允许正式 Analysis、投影与 deferred REPORT。分别覆盖 formal
runner、commissioning 单相位、adhoc、run-all，证明四类 owner 均有结构化 control release；删除任一 owner
的持久化调用都必须使对应路径保持 UNKNOWN，而不是由其他 lease/入口偶然补证；ANALYSIS/REPORT-only
调用不得新增 release result，也不得覆盖 MEASURE lease 的失败结果。

**Step 2: RED → GREEN 并提交**

```bash
cd api-service
./.venv/bin/python -m pytest -q \
  tests/test_p1_73c_cmw_measure_integration.py \
  tests/test_p1_73c_base_station_cleanup_truth.py \
  tests/test_p1_73c_base_station_control_release.py \
  tests/test_p1_73c_commissioning_control_release.py \
  tests/test_instrument_test_lease.py \
  tests/test_commissioning_smoke.py \
  tests/test_commissioning_adhoc.py \
  tests/test_commissioning_strict_gate_overrides.py \
  tests/test_p1_61_report_final_state_truth.py \
  tests/test_p1_73a_vendor_neutral_measure.py \
  tests/test_p1_59_ca_throughput_truth.py \
  tests/test_uxm_cell_config_orchestration.py
cd ..
git add api-service/app/services/mimo_ota/executors/measure.py \
  api-service/app/services/mimo_ota/cleanup.py \
  api-service/app/services/instrument_test_lease.py \
  api-service/app/hal/uxm_base_station.py \
  api-service/app/hal/cmw500_base_station.py \
  api-service/app/services/test_case_runner.py \
  api-service/app/api/commissioning.py \
  api-service/tests/test_p1_73a_vendor_neutral_measure.py \
  api-service/tests/test_p1_73c_cmw_measure_integration.py \
  api-service/tests/test_p1_73c_base_station_cleanup_truth.py \
  api-service/tests/test_p1_73c_base_station_control_release.py \
  api-service/tests/test_p1_73c_commissioning_control_release.py \
  api-service/tests/test_instrument_test_lease.py \
  api-service/tests/test_commissioning_smoke.py \
  api-service/tests/test_commissioning_adhoc.py \
  api-service/tests/test_commissioning_strict_gate_overrides.py \
  api-service/tests/test_p1_61_report_final_state_truth.py \
  api-service/tests/test_p1_59_ca_throughput_truth.py
git commit -m "feat: run CMW500 through the common MIMO measure flow"
```

### Task 14：收紧 Analysis、报告、对比、下载、历史和 Commissioning KPI 消费方

**Files:**

- Modify: `api-service/app/services/mimo_ota/executors/analysis.py`
- Modify: `api-service/app/services/mimo_ota/executors/report.py`
- Modify: `api-service/app/services/mimo_ota/rf_kpi_trust.py`
- Modify: `api-service/app/services/report_service.py`
- Modify: `api-service/app/api/test_execution.py`
- Modify: `api-service/app/api/commissioning.py`
- Modify: `gui/src/components/Commissioning/Phases.tsx`
- Create: `gui/src/components/Commissioning/baseStationMetricTruth.ts`
- Create: `gui/src/components/Commissioning/baseStationMetricTruth.test.ts`
- Create: `api-service/tests/test_p1_73c_formal_consumers.py`
- Create: `api-service/tests/test_p1_73c_commissioning_metric_projection.py`
- Modify: `api-service/tests/test_p1_72_comparison_gate.py`
- Modify: `api-service/tests/test_p1_63_rf_kpi_provenance_truth.py`
- Modify: `api-service/tests/test_p1_54_kpi_valid_contract.py`
- Modify: `api-service/tests/test_mimo_ota_report_verified_backcompat.py`
- Modify: `api-service/tests/test_arch1_history_resource.py`

**Step 1: 写 RED**

列全六类正式消费方：Analysis、报告 builder、报告对比、报告详情/下载 trust、执行历史、
Commissioning 方位 KPI 表。逐一证明：

- Analysis、报告 builder、报告详情/下载 trust、执行历史对直接来自基站窗口的 throughput/BLER
  逐指标调用唯一
  `evaluate_base_station_metric_trust(evidence, metric_name, expected_config, expected_position)`；
  只有返回 trusted 才发布吞吐/BLER，规范 envelope + `kpi_valid=true` 本身绝不充分；
- 六类消费方都必须消费实际 measurement lease owner 在租约退出后持久化的 final evidence：
  先只选择 execution 的 current `measurement_attempt_id`；该 attempt 的 window 自带 cleanup 与同
  attempt id、同 `lease_id`、同驱动 opaque `session_token` 的
  `transport_session_released_confirmed` 缺失或
  不为 true 时逐指标 UNKNOWN/N/A；不得把另一 lease 的成功 release、前面板 Local unknown、
  租约内 provisional Analysis、execution 已终态或 deferred REPORT 被调用当成 transport release；
  旧 attempt 的 window/release 仅为审计，不参与 current scope 唯一性；current attempt 内缺失、重复
  或额外方位/release 才 fail-closed。重跑失败不得回退到上一成功 attempt；
- 正式 runner 不得在 measurement lease 的 control-release 证据产生前执行最终 ANALYSIS：`_run_case_loop` 必须把末尾连续的
  ANALYSIS/REPORT 作为一个 deferred formalization bundle 返回，外层 lease owner 在持久化结构化
  release 后才按顺序执行，并把最终 `validation_pass` 与相位进度写回。transport release 失败时两者都不执行；
  只重建 projection 而不重算 Analysis 属于失败，因为会把租约内 UNKNOWN 永久写入历史；
- expected config/positions 只取本次执行冻结快照；窗口 config digest、route digest 或 position
  任一与期望不符均 UNKNOWN/N/A，历史/下载不得从当前数据库补齐；
- 旧 UXM 仅通过精确 translator；旧 CMW 原型、客户端声明、数值形状、adapter 名称均不能恢复 PASS；
- BLER unknown 不清空独立可信吞吐，吞吐 unknown 也不清空独立可信 BLER；
- 缺正式证据时数值可保留在诊断结构，但正式 KPI/verdict 为 UNKNOWN/N/A；
- 后端给每个 `azimuth_results[*]` 的 throughput/BLER 输出 server-owned 逐指标 trust projection，
  至少区分 `trusted` / `diagnostic` / `unknown` 并把正式值与诊断值分槽；projection 只由同一个
  evaluator 生成，GUI 不得用 raw 数值、`kpi_valid`、adapter 名称或顶层 bool 自行恢复信任；
- `api/commissioning.py::_execution_to_session_response` 是列表和详情的唯一活跃响应边界，必须从
  execution 的冻结 requested config/positions 与 final evidence 逐方位调用 evaluator 后生成上述
  projection，不能把 `phases["measure"]` 原样透传。单相位执行响应也复用同一 projector；租约内
  provisional 结果只能投影为 diagnostic/unknown，租约退出后的 final evidence 才可能 trusted。
  历史响应不得读取当前 TestCase、LabProfile、InstrumentConnection 或 HAL 状态补证；
- commissioning 的单相位、adhoc 与 run-all 在运行硬件相位时直接拥有自己的 lease，不能假设
  formal runner 会为它们持久化 release。三条路径必须消费 Task 13 的 lease outcome 和共享持久化
  helper；run-all 延迟 ANALYSIS/REPORT，单相位/adhoc 的 ANALYSIS/REPORT 不创建新基站 lease，只在
  measurement window 的同-id release 已落库后执行。projector 精确按 window lease id 选 final result；
  缺失、重复、跨 lease 或失败时保持 diagnostic/unknown；
- Commissioning `Phases.tsx` 不得直接渲染 `az.throughput_mbps`/BLER raw 字段。共享 presenter
  只在逐指标 `trusted` 时显示普通 KPI；`diagnostic` 必须黄色明确标注“诊断值，非正式实测”，
  `unknown` 显示 `N/A`。debug、Mock、窗口生命周期/配置/route/方位不匹配均不能显示成普通 Mbps/%；
- 历史/下载不能用当前数据库的仪器配置替旧执行补证据；
- `ReportComparisonService` 必须按现行 `COMPARISON_METRIC_KEYS` 显式映射权威源，不能把派生/RF
  聚合指标名直接交给 base-station evaluator，也不能继续信任 analysis 聚合值或旧
  `measurement_verified=true`：
  - `avg_throughput_mbps`：对冻结请求的每个方位调用 base-station throughput evaluator 后重算均值；
  - `throughput_ratio`：只从上述受信均值与该 execution 显式提供并冻结的 LTE
    `theoretical_peak_throughput_mbps` 重算；缺失时 ratio/delta/repeatability/相关 verdict 均
    UNKNOWN，不得读取 NR 450 Mbps 默认；
  - `rsrp_variance_db` / `avg_sinr_db`：在 `rf_kpi_trust.py` 抽取并复用最小逐指标 scope helper，
    分别要求完整 requested positions 的 `rsrp_dbm` / `sinr_db` explicit-real 当前行，再重算；
  - 未来新增 BLER 对比时才对每个方位调用 base-station BLER evaluator。
- 对比的每个 execution、每个指标独立产生 trusted/unknown；只有 baseline 与目标 execution 的同一
  指标都 trusted 才计算 delta，只用 trusted 样本形成 summary/repeatability。任一展示指标不可信
  时顶层 `formal=false`；结构合法但来自另一配置、route、方位或窗口的值必须独立排除，不得连带
  清空同一 execution 的其他可信指标。

**Step 2: RED → GREEN 并提交**

```bash
cd api-service
./.venv/bin/python -m pytest -q \
  tests/test_p1_73c_formal_consumers.py \
  tests/test_p1_73c_commissioning_metric_projection.py \
  tests/test_p1_73c_base_station_metric_trust.py \
  tests/test_p1_72_comparison_gate.py \
  tests/test_p1_63_rf_kpi_provenance_truth.py \
  tests/test_p1_54_kpi_valid_contract.py \
  tests/test_mimo_ota_report_verified_backcompat.py \
  tests/test_arch1_history_resource.py
cd ../gui
node --test src/components/Commissioning/baseStationMetricTruth.test.ts
npm run build
cd ..
git add api-service/app/services/mimo_ota/executors/analysis.py \
  api-service/app/services/mimo_ota/executors/report.py \
  api-service/app/services/mimo_ota/rf_kpi_trust.py \
  api-service/app/services/report_service.py \
  api-service/app/api/test_execution.py \
  api-service/app/api/commissioning.py \
  gui/src/components/Commissioning/Phases.tsx \
  gui/src/components/Commissioning/baseStationMetricTruth.ts \
  gui/src/components/Commissioning/baseStationMetricTruth.test.ts \
  api-service/tests/test_p1_73c_formal_consumers.py \
  api-service/tests/test_p1_73c_commissioning_metric_projection.py \
  api-service/tests/test_p1_73c_base_station_metric_trust.py \
  api-service/tests/test_p1_72_comparison_gate.py \
  api-service/tests/test_p1_63_rf_kpi_provenance_truth.py \
  api-service/tests/test_p1_54_kpi_valid_contract.py \
  api-service/tests/test_mimo_ota_report_verified_backcompat.py \
  api-service/tests/test_arch1_history_resource.py
git commit -m "fix: require base station truth for formal OTA results"
```

### Task 15：接入 OperationalLab readiness 与 GUI Warning

**Files:**

- Modify: `api-service/app/services/instrument_hal_service.py`
- Modify: `api-service/app/api/instrument.py`
- Modify: `gui/src/App.tsx`
- Modify: `gui/src/components/TestCaseConfig/MIMOOTAConfigForm.tsx`
- Modify: `gui/src/components/Commissioning/api.ts`
- Create: `api-service/tests/test_p1_73c_cmw_readiness.py`
- Create: `gui/src/components/TestCaseConfig/cmw500ReadinessTruth.test.ts`

**Step 1: 写 RED**

readiness/GUI 必须显示：

- adapter 已注册；
- 型号、固件、选件是否满足；
- 正式能力是否显式启用；
- 仪器资源配置页通过 Task 11 的专用 endpoint 提供 CMW500 LTE 2×2 正式能力开关；默认关闭，
  显示服务器更新时间。GUI 不编辑通用 `connection_params` 来启用，不创建环境变量/本地缓存真源；
- readiness 从所选 LabProfile binding 的同一 InstrumentConnection 读取 approval；执行响应显示本次
  execution 冻结的 approval，二者有变化时明确提示“仅影响后续执行”，不得改写当前证据；
- 未真机确认时 Warning/UNKNOWN，允许继续开发与诊断；
- debug inherit 显式黄色诊断态；
- 不显示或要求外部 RF router 作为准入项；
- 不在本片添加 CMW 功率设置或端到端功率预算通过/失败判词；只显示发布前待确认 Warning。

**Step 2: RED → GREEN 并提交**

```bash
cd api-service
./.venv/bin/python -m pytest -q tests/test_p1_73c_cmw_readiness.py
cd ../gui
node --test src/components/TestCaseConfig/cmw500ReadinessTruth.test.ts
npm run build
git add ../api-service/app/services/instrument_hal_service.py \
  ../api-service/app/api/instrument.py \
  src/App.tsx \
  src/components/TestCaseConfig/MIMOOTAConfigForm.tsx \
  src/components/Commissioning/api.ts \
  ../api-service/tests/test_p1_73c_cmw_readiness.py \
  src/components/TestCaseConfig/cmw500ReadinessTruth.test.ts
git commit -m "feat: expose CMW500 LTE MIMO readiness warnings"
```

### Task 16：同步 OpenAPI 三镜像与端到端契约

**Files:**

- Modify: `api/openapi.yaml`
- Modify: `gui/src/types/api.generated.ts`
- Create: `api-service/tests/test_p1_73c_openapi_contract.py`
- Create: `gui/src/types/cmw500ApiTruth.test.ts`
- Create: `api-service/tests/test_p1_73c_end_to_end_contract.py`

**Step 1: 写 RED**

覆盖 live OpenAPI / checked-in YAML / generated TS 同步，以及 UXM fake、CMW fake 对同一 TestCase 的端到端输出形状一致。只允许 adapter-specific evidence 位于版本化 envelope 内，顶层报告结构不得分叉成 UXM/CMW 两套。

**Step 2: RED → GREEN**

```bash
cd api-service
./.venv/bin/python -m pytest -q \
  tests/test_p1_73c_openapi_contract.py \
  tests/test_p1_73c_end_to_end_contract.py
cd ../gui
node --test src/types/cmw500ApiTruth.test.ts
npm run build
```

**Step 3: 提交**

```bash
git add api/openapi.yaml gui/src/types/api.generated.ts \
  api-service/tests/test_p1_73c_openapi_contract.py \
  api-service/tests/test_p1_73c_end_to_end_contract.py \
  gui/src/types/cmw500ApiTruth.test.ts
git commit -m "feat: publish CMW500 LTE MIMO API contract"
```

### Task 17：最终回归、fresh 内审与 roadmap 收口

**Files:**

- Modify: `docs/roadmap-first-call.md`
- Modify: `docs/plans/2026-08-26-p1-73-cmw500-lte-mimo-ota-design.md`（只更新实施结果与实跑统计，不改批准口径）

**Step 1: focused 与对称链回归**

```bash
cd api-service
./.venv/bin/python -m pytest -q \
  tests/test_p1_73a_base_station_contract.py \
  tests/test_p1_73a_config_compatibility.py \
  tests/test_p1_73a_lte_operating_point.py \
  tests/test_p1_73a_base_station_evidence.py \
  tests/test_p1_73a_vendor_neutral_measure.py \
  tests/test_p1_73a_base_station_topology.py \
  tests/test_p1_73b_cmw_command_profile.py \
  tests/test_p1_73b_cmw_parsers.py \
  tests/test_p1_73b_cmw_connect_lifecycle.py \
  tests/test_p1_73b_cmw_adapter_profile.py \
  tests/test_p1_73b_cmw_route_truth.py \
  tests/test_p1_73b_cmw_state_machine.py \
  tests/test_p1_73b_cmw_extended_bler_window.py \
  tests/test_p1_73b_cmw_capability_admission.py \
  tests/test_p1_73b_cmw_inherit_debug.py \
  tests/test_p1_73c_base_station_execution_evidence.py \
  tests/test_p1_73c_cmw_measure_integration.py \
  tests/test_p1_73c_base_station_cleanup_truth.py \
  tests/test_p1_73c_base_station_control_release.py \
  tests/test_p1_73c_formal_consumers.py \
  tests/test_p1_73c_cmw_readiness.py \
  tests/test_p1_73c_openapi_contract.py \
  tests/test_p1_73c_end_to_end_contract.py \
  tests/test_uxm_cell_config_orchestration.py \
  tests/test_p1_47c_execution_scpi_evidence.py \
  tests/test_p1_51_no_guessed_instrument_ip.py \
  tests/test_p1_54_kpi_valid_contract.py \
  tests/test_p1_59_ca_throughput_truth.py \
  tests/test_rule_gates.py
```

**Step 2: 全量与构建**

```bash
./.venv/bin/python -m pytest -q
./.venv/bin/python -m compileall -q app tests
./.venv/bin/alembic heads
cd ../gui
node --test \
  test/baseStationConfigTruth.test.ts \
  src/components/TestCaseConfig/cmw500ReadinessTruth.test.ts \
  src/types/baseStationApiTruth.test.ts \
  src/types/cmwAdapterProfileTruth.test.ts \
  src/types/cmw500ApiTruth.test.ts
npm run build
cd ..
git diff --check
```

要求：后端 0 failed；GUI 契约与 production build 通过；compileall 通过；单一 Alembic head；diff-check 通过。

**Step 3: fresh 独立内审**

按 AGENTS.md 0.5 重新列全：配置产生/消费、真机写入口、错误队列、状态复位、每方位窗口、Analysis、报告、详情/下载、历史、GUI。P1 修到 0；测试发现按仓库规则最高 P2。

**Step 4: 文档和提交**

roadmap 只写当前实现真值与实跑统计。现场未验证项记 Warning；不得写“真机已经通过”。功率预算仍列为正式发布前独立项，不自动施工。

```bash
git add docs/roadmap-first-call.md \
  docs/plans/2026-08-26-p1-73-cmw500-lte-mimo-ota-design.md
git commit -m "docs: record P1-73 CMW500 LTE MIMO verification"
```

**Step 5: PR 与合并规则**

- P1-73C 单独开 Ready PR。
- R1 核实并处理本片可执行意见，随后触发 R2。
- 覆盖最新 HEAD 的 R2 无 P1且 mergeable/checks 通过时立即 merge commit。
- R2 或后续仍有 P1则 TDD 修复并继续 P1-only 外审，直到最新 HEAD 无 P1。
- R2+ 的 P2/P3只报告、不阻塞、不自动积压。
- 合并后 fetch 验证 `origin/main`，在主工作目录 `git merge --ff-only origin/main`，保留全部未跟踪仪器资料。

---

## 现场启用与发布前待办（不属于 P1-73A/B/C 的开发硬门）

CMW500 真机到位后，先在正式能力关闭状态运行诊断：只读连接 → identity/firmware/options → internal route 写回读 → LTE attach → 单方位 Extended BLER → 多方位。每一步保存 exchange IDs 与结构化证据；任何未知项只显示 Warning/UNKNOWN，不冒充正式通过。

准备正式发布（建议 `v0.10.0`）前，另行设计并验证端到端功率预算：请求功率、CMW 外部补偿、开关/线缆路径、F64 输入上限、校准证书适用范围。该工作不得反向污染本计划的 HAL 清理或 CMW 指令语义。

回滚优先关闭 CMW 正式能力并切回 UXM；必要时部署已验证的 annotated tag `v0.9.1`。不得删除执行、报告、数据库、日志或仪器资料作为回滚手段。
