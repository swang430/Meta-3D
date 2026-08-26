# P1-73 CMW500 LTE 2×2 MIMO OTA Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 在不复制顶层测试流、不回归 UXM 的前提下，让 R&S CMW500 通过通用 BaseStation HAL 完成 LTE 单载波 2×2 MIMO OTA；所有正式吞吐/BLER 必须绑定真实型号、固件、选件、配置/内部路由回读与同一测量窗口证据。

**Architecture:** 分三片交付。P1-73A 先清除 MIMO OTA 顶层的 UXM 厂商泄漏并建立兼容迁移；P1-73B 按厂商手册重写 CMW500 的只读连接、内部 `1CC - nx2` 路由、状态机与 Extended BLER 窗口；P1-73C 才接入正式证据、OperationalLab、报告和 GUI。外部 RF router 不进入能力准入或运行硬门；端到端功率预算、外部补偿和 F64 输入余量延后到正式发布阶段。

**Tech Stack:** Python 3.12、FastAPI、Pydantic v2、SQLAlchemy、PyVISA、pytest/pytest-asyncio、React 18、TypeScript、Mantine、Vite、OpenAPI。

---

## 0. 固定边界与验收口径

实施中不得重新解释以下批准事实：

- LabProfile 的 `baseStation` 是逻辑角色；一次执行选择 UXM 或 CMW500，不在顶层复制两套流程。
- CMW500 首期仅 LTE、单载波、2×2、F64 射频域下游链；不做 DAU/IP 吞吐、CA、4×4、数字 IQ 外部衰落。
- CMW500 正式能力准入只消费**型号、固件版本、选件快照**；外部 RF router 不参与准入键，也不成为逐次执行硬门。
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
- Create: `gui/src/components/TestCaseConfig/baseStationConfigTruth.test.ts`

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
node --test src/components/TestCaseConfig/baseStationConfigTruth.test.ts
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
node --test src/components/TestCaseConfig/baseStationConfigTruth.test.ts
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
  gui/src/components/TestCaseConfig/baseStationConfigTruth.test.ts
git commit -m "refactor: canonicalize base station configuration fields"
```

### Task 2A：把 PCell 真值扩展为显式 LTE/NR 联合契约

**Files:**

- Modify: `api-service/app/schemas/mimo_ota/config.py`
- Modify: `api-service/app/services/mimo_ota/executors/measure.py`
- Modify: `api-service/app/services/mimo_ota/frequency_consistency.py`
- Modify: `api-service/app/services/mimo_ota/channel_asset_resolver.py`
- Modify: `api-service/app/services/standard_channel_service.py`
- Create: `api-service/app/hal/lte_earfcn.py`
- Create: `api-service/tests/test_p1_73a_lte_operating_point.py`
- Modify: `api-service/tests/test_p1_55_carrier_truth_source.py`
- Modify: `api-service/tests/test_channel_asset_resolver.py`
- Modify: `api-service/tests/test_standard_channel.py`
- Modify: `gui/src/components/TestCaseConfig/MIMOOTAConfigForm.tsx`
- Modify: `gui/src/components/TestCaseConfig/carrierTruth.ts`
- Create: `gui/src/components/TestCaseConfig/lteOperatingPointTruth.test.ts`

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
- `measure.py`、`channel_asset_resolver.py`、`standard_channel_service.py` 三个 NR identity 生产者
  全部消费同一 RAT-aware working point；SCD/ChannelAsset 明示 channel kind，禁止把
  `scd_config.arfcn` 无条件解释为 NR，也禁止把 LTE EARFCN 与 NR ARFCN 直接比较；
- 跨 RAT 的资产一致性仅比较经各自有出处 converter 得到的中心频率与带宽；缺 RAT、缺 converter
  或 channel kind 冲突都保护资产并在 I/O 前 fail-loud，不从文件名或当前 DB 猜测；
- executor 将同一个 typed `BaseStationRequestedConfig` 交给 fake UXM/CMW，不按厂商类分支；
- GUI 选择 LTE 时要求上述显式字段，不写 NR 默认值。

**Step 2: 运行 RED**

```bash
cd api-service
./.venv/bin/python -m pytest -q \
  tests/test_p1_73a_lte_operating_point.py \
  tests/test_p1_55_carrier_truth_source.py \
  tests/test_channel_asset_resolver.py \
  tests/test_standard_channel.py
cd ../gui
node --test src/components/TestCaseConfig/lteOperatingPointTruth.test.ts
```

预期：当前 schema 是 NR-only，LTE 输入会被 NR ARFCN 路径解释，测试失败。

**Step 3: 最小 GREEN**

- 给 PCell 增加显式 RAT 与互斥 channel-number 字段；旧记录缺 RAT 精确兼容为 NR。
- LTE converter 只实现 CMW LTE UE User Manual §2.2.23 Tables 2-54/2-55/2-56 明确列出的、
  且当前型号/选件快照支持的 band；未知、SCC-only、选件不足 band fail-loud，不猜公式。
- MEASURE 先按 RAT 建立 requested config，再交给通用 driver；LTE 路径不导入 NR converter。
- MEASURE、ChannelAsset resolver 与 StandardChannel service 复用同一 typed frequency identity；
  频率一致性结果携带 RAT/channel kind，禁止把 LTE EARFCN 与 NR ARFCN 比较。
- 保留 P1-55 的顶层镜像一致性门，不能因扩展 RAT 放宽旧冲突检查。

**Step 4: 运行 GREEN 并提交**

```bash
cd api-service
./.venv/bin/python -m pytest -q \
  tests/test_p1_73a_lte_operating_point.py \
  tests/test_p1_55_carrier_truth_source.py \
  tests/test_frequency_consistency.py \
  tests/test_channel_asset_resolver.py \
  tests/test_standard_channel.py \
  tests/test_uxm_cell_config_orchestration.py
cd ../gui
node --test src/components/TestCaseConfig/lteOperatingPointTruth.test.ts
npm run build
cd ..
git add api-service/app/schemas/mimo_ota/config.py \
  api-service/app/services/mimo_ota/executors/measure.py \
  api-service/app/services/mimo_ota/frequency_consistency.py \
  api-service/app/services/mimo_ota/channel_asset_resolver.py \
  api-service/app/services/standard_channel_service.py \
  api-service/app/hal/lte_earfcn.py \
  api-service/tests/test_p1_73a_lte_operating_point.py \
  api-service/tests/test_p1_55_carrier_truth_source.py \
  api-service/tests/test_channel_asset_resolver.py \
  api-service/tests/test_standard_channel.py \
  gui/src/components/TestCaseConfig/MIMOOTAConfigForm.tsx \
  gui/src/components/TestCaseConfig/carrierTruth.ts \
  gui/src/components/TestCaseConfig/lteOperatingPointTruth.test.ts
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

### Task 8：实现 CMW 内部 1CC-nx2 route 的写后回读

**Files:**

- Modify: `api-service/app/hal/cmw500_base_station.py`
- Create: `api-service/tests/test_p1_73b_cmw_route_truth.py`

**Step 1: 写 RED**

覆盖：

- 根据显式 `pcc_bb_board/rx_connector/rx_converter/tx1_connector/tx1_converter/tx2_connector/tx2_converter` 构造 TRO flexible 命令；
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
    evidence: tuple[InstrumentEvidenceItem, ...]
    confirmed: bool
    reason: str
```

CMW 测试要求同一 window 中：initialize/configure → wait/poll complete → Absolute/Relative fetch。`ThroughputAver` 从 kbit/s 显式除以 1000 得 Mbps；BLER 取 Relative 第 4 字段并保持百分比口径。任一字段缺失时该指标独立 unknown，不得用另一个指标替代，也不得保留原型 fallback。

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

- Modify: `api-service/app/hal/cmw500_base_station.py`
- Modify: `api-service/app/services/instrument_hal_service.py`
- Create: `api-service/tests/test_p1_73b_cmw_capability_admission.py`
- Create: `api-service/tests/test_p1_73b_cmw_inherit_debug.py`

**Step 1: 写 RED**

断言：

- CMW adapter 可由 registry 创建；
- 正式 LTE 2×2 能力默认 false；
- 显式启用后仍必须满足型号、固件、LTE 与 KS520 选件；缺任一项给 Warning/unknown，不声称 ready；
- 外部 RF router 的存在与否不会改变能力结果；
- `inherit` 只读核对当前 cell/route/状态，不做 preset，且 evidence gate 永远不授予 formal acceptance。

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
  api-service/app/services/instrument_hal_service.py \
  api-service/tests/test_p1_73b_cmw_capability_admission.py \
  api-service/tests/test_p1_73b_cmw_inherit_debug.py
git commit -m "feat: gate CMW500 LTE 2x2 formal capability"

./.venv/bin/python -m pytest -q \
  tests/test_p1_73b_cmw_command_profile.py \
  tests/test_p1_73b_cmw_parsers.py \
  tests/test_p1_73b_cmw_connect_lifecycle.py \
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
- Modify: `api-service/app/services/execution_scpi_evidence.py`

**Step 1: 写 RED**

规范快照只接受固定 schema，例如：

```python
class BaseStationExecutionEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[1]
    adapter: Literal["uxm", "cmw500"]
    identity: BaseStationIdentitySnapshot
    mode: Literal["dispatch"]
    config_confirmed: Literal[True]
    route_confirmed: bool | None
    window_ids: list[str]
    cleanup_local_confirmed: Literal[True]
    exchange_ids: list[str]
```

正式判据必须：real driver、获准 adapter/profile、identity 完整、dispatch、config readback、自身需要的 route readback、所有请求方位均有唯一 window、cleanup confirmed。CMW 必须 route confirmed；UXM 只消费自己的既有权威配置链。任何 extra/missing/legacy CMW/inherit/mock/方位集合失配均 false。

**Step 2: RED → GREEN 并提交**

```bash
cd api-service
./.venv/bin/python -m pytest -q tests/test_p1_73c_base_station_execution_evidence.py
git add api-service/app/services/mimo_ota/base_station_execution_evidence.py \
  api-service/app/services/execution_scpi_evidence.py \
  api-service/tests/test_p1_73c_base_station_execution_evidence.py
git commit -m "feat: add formal base station execution evidence"
```

### Task 13：把 CMW 测量窗口接入通用 MIMO 方位扫描

**Files:**

- Modify: `api-service/app/services/mimo_ota/executors/measure.py`
- Modify: `api-service/tests/test_p1_73a_vendor_neutral_measure.py`
- Create: `api-service/tests/test_p1_73c_cmw_measure_integration.py`

**Step 1: 写 RED**

使用 fake transport 走完整 PRECHECK/MEASURE：CMW 配置、内部 route、UE attach、每方位 Extended BLER window、F64/转台既有链、cleanup。覆盖：

- 请求方位全集精确匹配；重复/额外/缺失 window fail-closed；
- 每方位吞吐与 BLER 各自消费同一 window 的证据；
- route/config/error/cleanup 任一 unknown 时正式 throughput/BLER 均 UNKNOWN；
- 取消、attach timeout、window timeout、F64 失败均无假成功；
- UXM 仍通过同一个 executor 且原回归行为不变。

**Step 2: RED → GREEN 并提交**

```bash
cd api-service
./.venv/bin/python -m pytest -q \
  tests/test_p1_73c_cmw_measure_integration.py \
  tests/test_p1_73a_vendor_neutral_measure.py \
  tests/test_uxm_cell_config_orchestration.py
git add api-service/app/services/mimo_ota/executors/measure.py \
  api-service/tests/test_p1_73a_vendor_neutral_measure.py \
  api-service/tests/test_p1_73c_cmw_measure_integration.py
git commit -m "feat: run CMW500 through the common MIMO measure flow"
```

### Task 14：收紧 Analysis、报告、下载和历史消费方

**Files:**

- Modify: `api-service/app/services/mimo_ota/executors/analysis.py`
- Modify: `api-service/app/services/mimo_ota/executors/report.py`
- Modify: `api-service/app/services/report_service.py`
- Modify: `api-service/app/api/test_execution.py`
- Create: `api-service/tests/test_p1_73c_formal_consumers.py`
- Modify: `api-service/tests/test_p1_54_kpi_valid_contract.py`
- Modify: `api-service/tests/test_mimo_ota_report_verified_backcompat.py`
- Modify: `api-service/tests/test_arch1_history_resource.py`

**Step 1: 写 RED**

列全四类正式消费方：Analysis、报告 builder、报告详情/下载 trust、执行历史。逐一证明：

- 只有规范 `BaseStationExecutionEvidence` + 指标自身 `kpi_valid` 才发布吞吐/BLER；
- 旧 UXM 仅通过精确 translator；旧 CMW 原型、客户端声明、数值形状、adapter 名称均不能恢复 PASS；
- BLER unknown 不清空独立可信吞吐，吞吐 unknown 也不清空独立可信 BLER；
- 缺正式证据时数值可保留在诊断结构，但正式 KPI/verdict 为 UNKNOWN/N/A；
- 历史/下载不能用当前数据库的仪器配置替旧执行补证据。

**Step 2: RED → GREEN 并提交**

```bash
cd api-service
./.venv/bin/python -m pytest -q \
  tests/test_p1_73c_formal_consumers.py \
  tests/test_p1_54_kpi_valid_contract.py \
  tests/test_mimo_ota_report_verified_backcompat.py \
  tests/test_arch1_history_resource.py
git add api-service/app/services/mimo_ota/executors/analysis.py \
  api-service/app/services/mimo_ota/executors/report.py \
  api-service/app/services/report_service.py \
  api-service/app/api/test_execution.py \
  api-service/tests/test_p1_73c_formal_consumers.py \
  api-service/tests/test_p1_54_kpi_valid_contract.py \
  api-service/tests/test_mimo_ota_report_verified_backcompat.py \
  api-service/tests/test_arch1_history_resource.py
git commit -m "fix: require base station truth for formal OTA results"
```

### Task 15：接入 OperationalLab readiness 与 GUI Warning

**Files:**

- Modify: `api-service/app/services/instrument_hal_service.py`
- Modify: `api-service/app/api/instrument.py`
- Modify: `gui/src/components/TestCaseConfig/MIMOOTAConfigForm.tsx`
- Modify: `gui/src/components/Commissioning/api.ts`
- Create: `api-service/tests/test_p1_73c_cmw_readiness.py`
- Create: `gui/src/components/TestCaseConfig/cmw500ReadinessTruth.test.ts`

**Step 1: 写 RED**

readiness/GUI 必须显示：

- adapter 已注册；
- 型号、固件、选件是否满足；
- 正式能力是否显式启用；
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
  tests/test_p1_73b_cmw_route_truth.py \
  tests/test_p1_73b_cmw_state_machine.py \
  tests/test_p1_73b_cmw_extended_bler_window.py \
  tests/test_p1_73b_cmw_capability_admission.py \
  tests/test_p1_73b_cmw_inherit_debug.py \
  tests/test_p1_73c_base_station_execution_evidence.py \
  tests/test_p1_73c_cmw_measure_integration.py \
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
  src/components/TestCaseConfig/baseStationConfigTruth.test.ts \
  src/components/TestCaseConfig/cmw500ReadinessTruth.test.ts \
  src/types/baseStationApiTruth.test.ts \
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
