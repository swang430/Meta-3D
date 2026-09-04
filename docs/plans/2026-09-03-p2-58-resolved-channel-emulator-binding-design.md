# P2-58 设计稿 — ResolvedChannelEmulatorBinding + 分型号 saved presets

> 状态：**已实现并合并（① PR #450，收口 #451；② 见 2026-09-04 设计稿与 PR #452）**（⓪⁺② 先 review plan 后写代码）
> Roadmap：P2-58，依赖 P2-57（✅ #448 / 收口 #449）

## ⓪ 动手前四行

```
搜索命中：memory —— project_testcase_driven_instrument_arch（TestCase 是配置单一真值源）、
          feedback_effective_end_not_nominal（验证打在真实生效端）、
          feedback_value_form_space（值的形态空间要枚举）、
          feedback_distinguish_live_vs_mock_dead_code（先分清活路径与死代码）；
          目标文件禁令 —— 待动手前逐个 grep；
          仓库权威清单 —— base_station_binding.py 是同等物的现成模板
必要性：**没有单一 binding 真值** —— 下一个型号会复现「GUI 已保存，执行用的是另一份
       endpoint/profile」。这是 BaseStation 已经治过、CE 还没治的同一个病
范围：动 N 个文件（待定，见 §4）；枚举到 M 个读取入口，本片收敛成 1 个 resolver，
     其余入口改为消费它；未收敛项进 Discovered
爆炸半径：原 bug 最坏 = 执行用了跟 GUI 显示不同的 CE 配置且无人察觉（静默）；
        修完最坏 = resolver 判不出时 fail-closed 拒绝执行（吵）。Y ≤ X ✅
```

## 1. NotebookLM 适用性判定

**本片显式记「不适用」**。P2-58 是 binding / 配置装配，条目自己写明「**解析过程零仪器 I/O**」。
本片的结论里没有任何一句在断言「仪器怎么样」。

⚠️ **例外**：若 §3 的开放问题①（要不要补「通道/端口基数」）答「要」，那**立刻变成适用**
—— 「F64 有几个输入/输出口」是仪器事实，裁决权在手册，必须先查 PROPSIM notebook。

## 2. 现状枚举：CE 配置今天有几个读取入口

条目列了 7 个（model / connection / LabProfile / ChannelAsset / 厂商参数 / loaded driver /
execution freeze）。实测另外查到**两条条目没点到的**：

| # | 入口 | 证据 |
|---|---|---|
| A | **两套注册表、两种品类键拼写** | 活路径 `instrument_hal_service.py:127` 用 `channelEmulator`（驼峰，注册 F64/FS16）；`app/hal/driver_registry.py` 用 `channel_emulator`（下划线），经 `app/hal/__init__.py:47` 导出，但**生产代码无人 import**（只有该 `__init__` 再导出 + `tests/test_p1_51_no_guessed_instrument_ip.py`）。⚠️ 「无人 import」需在动手前二次确认，别按一次 grep 下结论 |
| B | **消费方自己兼容两种拼写** | `instrument_test_lease.py:160`：`drivers.get("channelEmulator") or drivers.get("channel_emulator")` —— 消费方在替真值源打补丁，正是「值的形态空间」那条 |

**这两条改变了本片的形状**：条目假设「入口多但键一致」，实测是「键本身就有两种写法」。
resolver 若只统一了对象来源、没统一键，A/B 会原样留下。

## 3. 已拍板（用户 2026-09-03）

### ① 「通道/端口基数」不进 manifest；.smu 拓扑解析**单独成片**

用户提供了真实样本 `New GCM Model 5.smu`（已收进 `api-service/tests/fixtures/smu/`，
未脱敏，用户明示）。**样本直接否掉了 manifest 方案**：

| 拿得到的 | 出处 | 本样本 |
|---|---|---|
| 输入/输出/通道**数** | `[Input N]` / `[Output N]` / `[Channel N]` 节的**个数** | 4 / 4 / 8 |
| **物理连接器号** | 每节的 `Connector` | 输出是 `COMMON 3,4,1,2` —— **不是 1,2,3,4** |
| 通道路由矩阵 | `[Channel N]` 的 `Input=` / `Output=` | ch0=(0,0) … |

端口号随 .smu 变，放进 per-driver 的不可变 manifest **第一份 asset 就让它过期**；
而 [`propsim_f64.py:1179`](../../api-service/app/hal/propsim_f64.py) 已有一道
「声明 vs `MODEL:INFO?` 回读不符就拒绝」的 fail-loud 门，再加一层 manifest 声明
就是**第三份声明**进同一场比较。

三层各归其位：**manifest** 管静态能力 → **ChannelAsset** 管这份模型要什么 →
**`MODEL:INFO?`** 仍是运行时真值 + 既有那道门。

⏳ **拓扑解析单独成片**（见 §7 Discovered-1）。理由：不改它，本片的可观察故障
（没有单一 binding 真值）依然在 —— ⑦ 的判据下属越界。且动手前还欠两样：
**OTA 形态的 .smu 样本**（本样本是 2×2 双向实验室模型 4/4/8，OTA 是 4/128/32），
以及 **`Direction` 键语义的手册裁决**（样本里 `Direction = UPLINK` 而 `Group name = Downlink`，
按 `Direction` 判 DL/UL 会全判反 —— 详见固件 README）。

### ② 品类键两种拼写：只收消费方那处，删注册表进 Discovered

- **本片收**：`instrument_test_lease.py:160` 的 `drivers.get("channelEmulator") or
  drivers.get("channel_emulator")` —— 它是本片 resolver 的直接消费方，不收就得让
  新代码也兼容两种写法，等于把病带进新代码。
- **进 Discovered**：`app/hal/driver_registry.py` 那套下划线键（见 §7 Discovered-2）。

### ③ 切换型号丢未保存草稿，但切换前弹确认

草稿持久化不在条目验收里；与现有 GUI 其它切换语义一致。

## 4. 范围：**拆成两片**（本稿只覆盖 ①）

实测：CE **完全没有** BaseStation 那条链的对应物 —— 没有 `channel_emulator_binding.py` /
`_compatibility.py` / `_adapter_profile.py`，配置散在 `instrument.py` 里靠
`category_key in {"baseStation", "channelEmulator"}` 分支搭便车（2555 / 2620 / 2666 /
3330 / 3522 等处）。而 BaseStation 侧的 resolver 有 **6 个消费方**
（`lab_profile.py:403`、`base_station_compatibility.py:213`、`base_station_binding.py:157`、
`execution_qualification.py:464`、`base_station_adapter_profile.py:197`、
`base_station_execution_evidence.py:1575`）。

一次做完 = 新建 2 个模块 + 改 5 处消费方 + 契约四步（openapi / 生成类型 / service / mockServer）
+ GUI 分型号 preset + 门文件 ≈ 12+ 文件。**超出一片的自然范围**，按 P2-56 的先例拆半：

| 片 | 内容 | 性质 |
|---|---|---|
| **P2-58 ①（本稿）** | `ResolvedChannelEmulatorBinding` + resolver + preview；六个消费方复用同一 digest；收 ② 那处 `or` | **后端单一真值**，零 GUI 改动 |
| **P2-58 ②** | 分型号 saved presets：原子持久化 + 切换确认 + GUI；**并收 ① 留下的前端镜像站点**（Agent G 枚举，① 只做 openapi + 生成类型）：`gui/src/api/labProfileService.ts:115`（CE preview 的 service 函数）、`gui/src/types/api.ts:403`（手写 readiness 类型补 `channel_emulator_binding`）、`gui/src/api/mockDatabase.ts:99` / `mockServer.ts`（mock 数据与处理器）、`gui/src/features/Dashboard/ZoneReadiness.tsx:142`（readiness 灯消费点）；以及是否给 CE 镜像一份 `tests/test_p2_44_openapi_contract.py` 那种 openapi 契约测试；（`HALReadinessResponse.channel_emulator_binding` 在 yaml 里**已是 required** —— ① 初版设为非必填，被既有门 `test_p2_27_openapi_contract_alignment` 当场否掉：readiness 响应字段一律 required，因为 live schema 用 `json_schema_serialization_defaults_required=True` 字段恒出现；GUI 消费时按非空处理即可）；**并补 preview 端点对 `test_case_id` 的两格判定**（Agent B 按 ⑤ 未加机制：TestCase 存在但 `test_type != "MIMO_OTA"`、或其 `lab_profile_id` 与所选 LabProfile 不一致时，① 照读 `configuration["channel_asset_id"]`；BS 对应场景返回 compatibility `invalid`，CE 无该槽位 —— ② 决定拒还是加槽位）| 保存与 UX |

① 的文件清单（预估 7）：
1. `app/services/channel_emulator_binding.py`（新）
2. `app/schemas/channel_emulator_binding.py`（新）
3. `app/api/lab_profile.py`（preview 端点 + 保存路径消费 resolver）
4. `app/api/instrument.py`（readiness / sync 面消费 resolver）
5. `app/services/test_case_runner.py`（execution freeze：在 BaseStation freeze 之后调 CE freeze；初稿误写成 `execution_qualification.py`）
6. `app/services/instrument_test_lease.py`（删 `or` 兼容 —— 决定 ②）
7. `tests/test_p2_58_channel_emulator_binding.py`（新，门）

⚠️ 契约四步（`api/openapi.yaml` → `npm run openapi:generate` → `service.ts` → `mockServer.ts`）
在 ① 里**只做前两步**（新增 preview 响应 schema 的契约声明），后两步随 ② 的 GUI 一起 ——
否则前端有类型没消费方。

## 5. 门的设想（每条须配让它变红的变异）

1. **单一 resolver 不变量**：全仓解析 CE binding 的路径只有一条（AST 派生），
   其余入口必须消费它 —— 变异：另起一处直接读 LabProfile → 红。
2. **digest 一致**：preview / 保存 / 同步 / readiness / HAL reload / execution freeze
   六个消费方拿到同一个 digest —— 变异：任一处改用重算而非复用 → 红。
3. **零仪器 I/O**：resolver 执行路径上不得出现 transport 调用 —— 变异：插一条
   `await driver.query(...)` → 红。
4. **分型号不互相覆盖**：保存型号 A 的 preset 后，型号 B 的 preset 逐字节不变 ——
   变异：保存时全量重写 → 红。
5. **fail-closed**：resolver 判不出时拒绝执行且给可操作理由，不静默降级 ——
   变异：判不出时回落到「用 loaded driver 当真值」→ 红。

## 6. 参照物

`app/services/base_station_binding.py:52` 的 `ResolvedBaseStationBinding`：
不可变（`frozen=True` + `extra="forbid"`）、`schema_version`、四态 `status`、
`binding_digest`，且 **runtime identity 刻意排除在 digest 之外**
（`stable_projection()` 排掉 `execution_mode` / `runtime_driver`）。
CE 版按同一形态做，字段按 CE 的真实需要取，不照抄恒空字段
（这正是 P2-57 拍板「不复用基站 manifest」的同一条理由）。

## 7. Discovered（本片枚举出、不在本片做）

- **Discovered-1**：`.smu` 拓扑解析 + `ChannelAsset` 拓扑字段 + resolver 离线校验。
  已备样本与键名；欠 OTA 形态样本 + `Direction` 语义的手册裁决。
- **Discovered-2**：`app/hal/driver_registry.py` 的下划线品类键（`channel_emulator`）——
  与活路径 `instrument_hal_service.py` 的驼峰键并存。生产代码疑似无人 import
  （仅 `app/hal/__init__.py:47` 再导出 + 一个测试），**动手前须二次确认再删**。
- **Discovered-3**（Agent D 枚举，越界未动）：`commissioning.py` `_freeze_instrument_lease` 的 `validation_identity`（lease 校验器比对用的身份集合）**未纳入 CE 的 `binding_digest`**。① 只让 CE freeze 在它旁边落冻结件；把 CE digest 并进 lease 校验身份属于改 lease 校验器的契约，另片评估。**内审 F1 补的具体场景**：`freeze_channel_emulator_binding` 的「已存在」分支只过结构自洽校验，**不对照当前装载的 HAL 驱动**（BS 同位置有 `validate_frozen_base_station_before_remote(hal, existing)`）。探针实跑：建会话时 HAL 装 F64@.50 → 行回 `pending` → reload 被放行（`hal_reload_policy.py:111` 只拦 `running`）→ 装载变成 F64@.51 / mock / 无 CE → `run-phase` 三种全部复用旧冻结件通过，MEASURE 对另一台仪器下发。修法形状：镜像 BS，在已存在分支用冻结件的 `expected_driver_module/name` + `expected_driver_connection` + simulated 与当前 `hal` **零 I/O 对照**，不重算 digest。P2。

## 8. ① 的接口契约（并行 agent 的公共依赖，先于实现定死）

> 逐项镜像 `app/services/base_station_binding.py`。**字段按 CE 真实需要取，不抄恒空字段。**

### 8.1 `app/services/channel_emulator_binding.py`

```python
class ChannelEmulatorRuntimeDriverIdentity(BaseModel):      # frozen, extra=forbid
    driver_module: str | None
    driver_name: str | None
    adapter_id: str | None            # manifest.adapter_id（Mock 也有）
    simulated: bool
    transport: dict | None            # host/port/resource；simulated 时 None

class ResolvedChannelEmulatorBinding(BaseModel):            # frozen, extra=forbid
    schema_version: Literal[1]
    status: Literal["configured", "not_applicable", "diagnostic_unbound"]
    execution_mode: Literal["real", "simulated"]
    category_id: str
    instrument_model_id: str | None
    instrument_connection_id: str | None
    lab_profile_id: str
    manifest: ChannelEmulatorManifest | None               # P2-57 的，来自 channel_emulator_manifest_of(driver)
    expected_driver_module: str | None
    expected_driver_name: str | None
    expected_transport: dict | None                         # 复用 resolve_configured_tcpip_connection 的形状
    binding_digest: str                                     # canonical_payload_digest(persistent)
    runtime_driver: ChannelEmulatorRuntimeDriverIdentity    # ⚠️ 刻意排除在 digest 外

    def stable_projection(self) -> dict: ...               # exclude={"execution_mode","runtime_driver"}

class ChannelEmulatorBindingPreview(BaseModel):            # frozen, extra=forbid
    status: Literal["configured","not_applicable","diagnostic_unbound","invalid"]
    binding_digest: str | None
    execution_mode: Literal["real","simulated"] | None
    adapter_id: str | None
    model_name: str | None
    category_id: str | None
    instrument_model_id: str | None
    instrument_connection_id: str | None
    lab_profile_id: str
    resolved_binding: dict | None
    runtime_driver: dict | None
    detail: str
    @classmethod invalid(lab_profile_id, detail) / from_resolved(resolved)

def resolve_channel_emulator_binding(db, hal, selected_lab_profile: LabProfile, *, lock: bool = False) -> ResolvedChannelEmulatorBinding
    # 零仪器 I/O。ValueError 表示真值不一致（调用方转 422 / invalid）。
    # 锁序与 BaseStation 一致：category → LabProfile → connection。
    # driver_mode 三方一致性（category / binding / loaded driver）照抄 BaseStation 的判定。
    # 品类键只认 "channelEmulator"（决定 ②：不兼容 "channel_emulator"）。

def build_channel_emulator_binding_preview(db, hal, selected_lab_profile) -> ChannelEmulatorBindingPreview
```

**与 BaseStation 的差别（有意的）**：无 `profile`（CE 没有 adapter profile 这一层）、无 `formal_capability`
（CE 的正式能力判定不在 ① 范围）。`selected asset` 是 **per-TestCase**（`MIMOOTAConfiguration.channel_asset_id`），
不是 per-LabProfile —— 所以**不进 binding digest**；预览端点接受可选 `test_case_id` 时以
`selected_asset_id` 字段附带，不影响 digest（镜像 BaseStation 把 compatibility 与 binding 分开的做法）。

### 8.1a 契约解释（Agent A 提出，主 agent 2026-09-03 定，消费方按此接线）

1. **mock 模式下 `manifest` 字段与 digest 用「所选型号在注册表里的真驱动类」的 manifest**
   （`channel_emulator_manifest_of(expected_class)`），不是装载 mock 的。否则 digest 会随
   HAL reload mock↔real 翻动，违背「runtime identity 排除在 digest 外」。mock 身份在
   `runtime_driver.adapter_id`（= `mock_channel_emulator`）。**顺带这就是「HAL reload 复用同一
   digest」在 ① 里唯一真实的落点：reload 不翻 digest。** 装载驱动的 manifest 仍取来做
   fail-closed（None → ValueError）与真驱动模式下的相等性校验（实例级漂移 → ValueError）。
2. digest 里的 manifest 剔除 `reason` / `source_reference`（镜像 BS `digest_safe_manifest_payload`）：
   改一句文案不该让已冻结执行的 digest 失配；翻一格 `support` 则会变。
3. `status="not_applicable"` 永不产出（CE 无 profile 层），Literal 按契约保留。
4. **`expected_transport` / `runtime_driver.transport` 是 `dict`**（`{"host","port","resource"}`），
   不是 BS 那种类型化模型 —— 消费方写 `["host"]`，不写 `.host`。
5. **错误消息全部简体中文 + 英文标识符**（BS 的是英文）。消费方别按 BS 风格英文子串匹配。
6. `selected_asset_id` 默认 `None`（镜像 BS `testcase_compatibility = None`）。
7. `CHANNEL_EMULATOR_CATEGORY_KEY = "channelEmulator"` 契约外多导出；消费方**用它，不再手写字面量**。
8. 消息优先级：替身在 unbound 场景先撞「没有声明 manifest」，后撞「只允许权威 mock」——两条都是正确拒绝。

### 8.2 `app/schemas/channel_emulator_binding.py`

`ChannelEmulatorBindingPreviewResponse` = 8.1 的 preview 字段 + `selected_asset_id: str | None`。

### 8.3 端点

- `GET /lab-profiles/{lab_profile_id}/instrument-bindings/channelEmulator/preview?test_case_id=`
  （与 BaseStation 同路径形态，`response_model=ChannelEmulatorBindingPreviewResponse`）
- 保存路径（`lab_profile.py` 现有 `category_key == "baseStation"` 分支旁）加 `channelEmulator` 分支，
  保存后立刻 resolve，ValueError → 422 + rollback。

### 8.4 消费方（各自复用同一 digest，不重算）

| 消费方 | 改法 |
|---|---|
| `api/lab_profile.py` | 8.3 |
| `api/instrument.py` readiness / sync 面 | 在现有 `base_station_binding` 字段旁加 `channel_emulator_binding`，取自 preview |
| `services/test_case_runner.py:271` 旁 | **execution freeze 的真正落点**（§8.4 初稿写成 `execution_qualification.py`，那是读 BaseStation 冻结件做**认证**的，CE 在 ① 无对应物 —— 实测后更正）。在 `freeze_execution_base_station_adapter_profile(...)` 之后紧接着调新模块的 `freeze_execution_channel_emulator_binding(db, hal, execution, snapshot)`；失败同样 `db.rollback()` + `CaseNotExecutable`。冻结件形状镜像 `base_station_adapter_profile.py:173-274`：`identity = {schema_version, category_id, instrument_model_id, instrument_connection_id, lab_profile_id, execution_mode, expected_driver_module, expected_driver_name, expected_driver_connection, binding_digest, resolved_binding: stable_projection()}`，`frozen = {**identity, "digest": canonical_payload_digest(identity)}`，写 `execution.config[CE_FREEZE_CONFIG_KEY]`（`"channel_emulator_binding_freeze"`）+ `flag_modified` + `flush`；已存在则校验后复用，不重算。`execution_mode` 是 P2-59③ 单一会话在远程 I/O 前区分真实/受控模拟的顶层冻结真值，并受同一外层 digest 保护；`resolved_binding` 的稳定投影仍排除其运行期 `execution_mode` / `runtime_driver` 字段。resolve 用 `lock=True`。 |
| `services/instrument_test_lease.py:160` | 删 `or drivers.get("channel_emulator")` |

⚠️ **「HAL reload 复用同一 digest」在 ① 里无载体，如实报。** 实测 `hal_reload_policy.py` 的 `find_reload_blockers` 不核任何 binding/digest，BaseStation 侧也没有这个先例（`instrument_hal_service.py:337/383/442` 的 `binding_digest` 是 `Cmw500Lte2x2Readiness` 上的 **readiness** 字段，不是 reload 门）。① 不为它发明机制；验收里这句留给后续 triage 决定要不要做、怎么做。
