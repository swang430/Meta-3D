# P2-53 —— 第三种 BaseStation Adapter 接入认证套件（2026-08-30）

> 队列末片。目标：把 uxm / cmw500 两家 adapter 分散在各片测试里的认证形态
> **固化为可参数化模板**，并以第三 adapter fixture（`certfake`）证明
> **HAL 接入与诊断认证只需五件套**：adapter 实现、manifest v2、profile/schema、
> 手册来源、认证测试。当前实证的零修改边界仅包括 manifest 注册、计划 resolve 与
> MEASURE 原生窗口采样；正式 binding/profile-freeze 以及 execution evidence 的封闭
> adapter 枚举尚未泛化，已按条目登记平台缺口（见 §5），本片不借测试夹具扩大生产范围。

## 1. 实证前置（⓪⁺①）

- **memory**：已查（`feedback_pr_scope_equals_its_purpose` ⑦判据、
  `feedback_gate_itself_can_be_fake` 门配变异、G5/G6 防删过头、
  G12 SCPI 证据目录、G17 测试进程 HAL 恒 mock、
  `feedback_mutation_run_operational_hazards` 变异还原纪律）。
- **NotebookLM**：**不适用** —— 本片不新增任何 SCPI 命令、不断言任何仪器
  语义。模板全部从**既有测试的真实断言**提炼（各断言的手册出处在原片
  P2-43/47/48/49/51/52 已闭环）；`certfake` 是认证夹具非真仪器，其
  manual_sources / source_reference 是**如实标注的占位**（指向夹具契约，
  不冒充厂商手册）。

## 2. 交付物与十类维度映射

**新增两个测试域文件（生产代码零改动）：**

- `api-service/tests/base_station_certification_kit.py` —— 认证模板
  （14 个 `certify_*` 函数）+ 第三 adapter 夹具
  （`CertFakeBaseStationDriver` / `CertFakeAdapterProfile` /
  `CERTFAKE_MANIFEST`）+ 通用脚本会话 `ScriptedScpiSession`。
- `api-service/tests/test_p2_53_adapter_certification_kit.py` —— 三 subject
  （uxm / cmw500 / certfake）参数化跑同一套模板（42 用例）+ 3 个判定器
  自测 + 1 个 certfake 泄漏不变量门，共 46 用例全绿。

| # | 维度 | 模板函数 | 提炼自（真实断言源） |
|---|---|---|---|
| 1 | fake transport | certify_fake_transport_exchange_provenance | test_p2_52:347 内审 F1 成因门（wire token 只能来自真实传输模板，"command"/"query"，simulated=False）|
| 2 | 部分回读 | certify_partial_readback_receipt | test_p2_43 `_partial_config_receipt` / test_p1_73b:106（unknown 不携 applied、confirmed=False、操作接受与证据完备分离）|
| 3 | 错误队列 | certify_error_queue_consultation | test_p1_41 / test_p1_73b:177 / test_p2_51:346（被拒不 confirmed + 操作后必查错误队列）|
| 4 | 超时/取消 | certify_attach_timeout_returns_receipt / certify_cancellation_propagates | test_p02:117（超时返回 receipt 不挂死）/ test_p1_73b:762、test_uxm_cell_config_orchestration:232（取消向上传播不被吞；生命周期随后调用并确认 SAFE cleanup）|
| 5 | Attach 阶段 | certify_attach_stage_truth | test_p2_47_uxm:33 / test_p2_47_cmw:35（四阶段有序、evidence 与 manifest 声明逐字相等、confirmed 携 wire exchange）|
| 6 | 窗口 | certify_measurement_window_contract | test_p2_48:118/154 / test_p2_52:340（digest 一致、漂移请求拒绝、formally 由 lifecycle 决定、真实窗口携 wire 证据）|
| 7 | 逐指标 trust | certify_metric_registry_trust | test_p2_49_adapter_metric_registry:17（registry 零 I/O）/ test_p2_49_metric_observations:61（值绑回产生它的 exchange）|
| 8 | SAFE_IDLE | certify_safe_idle_boundary | test_p1_73b:282（OFF 可确认 → True；不可知 → False）|
| 9 | release | certify_release_token_boundary | test_p1_73c_control_release:72/193 / test_p1_73b:228（token 绑定；错/过期 token 不得报已确认释放）|
| 10 | 模拟排除 | certify_simulated_exclusion | test_p2_43:222 / test_p2_48:164 / test_p2_49:148（simulated 恒不 formal、无 confirmed 阶段、KPI 全无效、receipt 标 simulated）|
| — | 注册门（五件套） | certify_registration_gate | test_p2_46_capability_manifest:339；直接复用生产尺子 `validate_base_station_adapter_registrations`，判据不复制 |
| — | 计划中立（五件套） | certify_execution_plan_neutrality | test_p2_50（planned 恒等于 adapter 声明、digest 稳定、无 adapter 身份分支）|
| — | 共同消费者行为门 | certify_common_consumer_native_window | test_p2_43:165（生产 `MeasureExecutor._measure_base_station_samples` 原样消费、样本数由 cardinality 决定）|

**既有测试全部保留原地**（G5/G6 精神），模板是收敛入口不是替换；uxm/cmw
的方言深断言（恰两次 -113 判据、EBLer 七条 wire 序列、预排水序等）留在
原文件。fake 形态按既有惯例跨文件收编：uxm 用 `wire_echo_visa`（P1-19）、
cmw 用 `_StateDriver`（P1-73B）/ `_WindowDriver`（EBLer）。

## 3. 第三 adapter 夹具：certfake

- 类名 `CertFakeBaseStationDriver` —— **不以 Mock 开头**
  （`app/diagnostics/protocol.py:116` 与 `app/api/instrument.py:2639` 按
  `__name__.startswith("Mock")` 判 mock，撞名会被误判）。
- **不注册进生产 HAL**：`instrument_hal_service._real_driver_registry()`
  零改动；`test_p1_73a_base_station_contract` 的封闭集门
  （`adapter_ids == {"UXM 5G E7515B": "uxm", "CMW500": "cmw500"}`）继续守
  生产注册表；注册认证以「生产注册 + certfake **合成** mapping」过同一把
  生产尺子（纯函数，不触注册表）。
- 五件套齐备：adapter_id=`certfake`、manifest v2 全维度（attach 四阶段
  authoritative、measurement lifecycle=`authoritative_closed`、
  profile_requirement=`required`）、`CertFakeAdapterProfile`
  （schema_version=1 / adapter=Literal["certfake"] / loopback_route）、
  manual_sources 占位（如实标注「认证夹具，非真实仪器手册」）、认证测试
  即本套模板。
- 传输：override `_do_write`/`_do_query`（与 cmw 系测试同层），exchange
  记账走 `base.py` 真实传输模板；每次写后读错误队列（read-after-write）。
- certfake 走 formally_confirmed=True 的全绿路径（attach + 窗口）——
  这是 uxm（clear_read_only）/cmw（attach authoritative、窗口 EBLer）今天
  各自只覆盖一半的形态，三方合起来模板的档位分支全部吃到。

## 4. 三候选评估（P2-50 移交；评估 ≠ 必做，⑦判据逐条问：
「不做它，第三 adapter 接入认证这个可观察目标是否受阻？」）

### 候选① measure.py 7 处其它鸭子类型探测收编入计划维度 → **不做**

- 现状实查：7 处 = L567 `get_mimo_route_snapshot` / L1916
  `read_live_frequency_identity` / L1930 `get_cell_state`（inherit 核对）/
  L1947 `get_frequency_identity` / L2591 `query_ue_capability` / L2813
  `get_applied_cell_config` / L2995 `get_ue_info`；另有 3 处性质不同
  （2 处 P1-47C 证据构建器 hasattr、1 处 L2426 已知恒假防御残留），不混入。
- ⑦判据：**不受阻**。本片实证：certfake 未实现其中任何可选方法，
  46 用例全绿 —— 这些散点全是「缺了就优雅跳过 / 如实记 unavailable」的
  可选增强，不挡接入不挡认证。
- 附加事实：其中 get_cell_state / get_ue_info / query_ue_capability 在
  `BaseStationDriver` 基类**有定义**（raise NotImplementedError），
  `hasattr` 对它们**恒真** —— 收编前要先裁决判据形态（P2-50 同型的
  「计划维度 + planned 缺方法 fail-loud」），属于共同消费者改造，
  正是本片明令不做的。
- 后续载体：Discovered 候选一行（见 §5）。

### 候选② SCell manifest operation token 化 → **不做**

- 现状实查：`_EXECUTION_PLAN_DIMENSIONS` 里 scell 的 token=None
  （base_station.py:826），capability_source 恒
  `adapter_attribute:SCELL_ACTIVATION_READBACK_AUTHORITATIVE`，不受
  manifest 交叉校验（声明漂移 fail-loud）保护；`operation_mirrors`
  只有三组（base_station_manifest.py:464）。生产两 adapter 该属性均为
  False（无厂商回读出处），仅 MockBaseStation 为 True。
- ⑦判据：**不受阻**。certfake 的 scell 维度经 adapter_attribute 源正常
  进入执行计划（certify_execution_plan_neutrality 三方全绿）；第三厂商
  声明 SCell 权威回读只需设类属性。
- 不做的另一半理由：今天**没有任何注册 adapter** 声明该能力，token 化
  加了也是零覆盖；且有前置设计裁决 —— 镜像门读**类属性**，而 UXM 的
  rrc/mac supported 是**实例 property**（Test App profile 派生），
  scell token 要同时定义 property 型声明如何过镜像门，不是一行改动。
- 后续载体：Discovered 候选一行（等第一个真声明 SCell 权威回读的
  adapter 出现时随那片一起做：token + operation_mirrors 第四组 +
  property 语义裁决）。

### 候选③ `_formal_mac_configuration_blocker` 的 is_mock_driver 豁免计划化 → **不做**

- 现状实查：measure.py L582-603，`is_mock_driver` 豁免先于计划判据；
  `test_p2_50_execution_plan.py` L241-249 已把「mock 在 planned=False 和
  True 两种形态下都豁免」pin 成双向契约（docstring：mock 本不进正式
  KPI，不需要 MAC blocker）。
- ⑦判据：**不受阻**。certfake 不是 mock（`is_mock_driver` 是
  isinstance 判据，certfake 不在 `_MOCK_FALLBACK_BY_CATEGORY` 类表），
  走计划判据 —— 正是认证模板验证的形态；模拟排除（维度 10）由
  simulated 语义兜住。
- 计划化 = 改共同消费者 measure.py + 重写既有 pin 测试，而当前语义
  **没有可观察故障**（修法优先级：去掉 > 换源 > 收窄 > 加机制 ——
  这里连要修的故障都没有）。
- 后续载体：Discovered 候选一行（触发条件：出现「第三 adapter 的
  simulated 变体被 blocker 误伤」的可观察故障）。

## 5. 平台缺口与 Discovered 候选（待 triage，不自动启动）

1. **[平台缺口候选]** `BaseStationAdapterProfileResolution.adapter` 是封闭
   `Literal["uxm", "cmw500"]`（base_station_adapter_profile.py:57）——
   binding / profile-freeze / resolution 链路对第三 adapter 关闭。
   同时 `base_station_execution_evidence.py` 的 identity/config/attach/window/
   metric/release/总 envelope 模型仍使用相同封闭 Literal，
   `execution_scpi_evidence.py` 的初始化与解析也仍有两厂商分支。认证套件十类
   **不触达**正式 binding/evidence 持久化与解析链，本片不受阻；但真实第三厂商
   进入**正式执行链**前必须将这些边界统一改成注册驱动。按条目属「须登记的平台缺口」。
2. [discovered 2026-08-30 during P2-53] measure.py 7 处可选能力散点探测
   （§4 候选①清单）+「hasattr 对基类抽象方法恒真」判据缺陷，收编需
   P2-50 同型计划维度设计。
3. [discovered 2026-08-30 during P2-53] SCell operation token 化（§4
   候选②）：等首个声明 SCell 权威回读的 adapter，需同步
   operation_mirrors 第四组 + 类属性/实例 property 镜像语义裁决。
4. [discovered 2026-08-30 during P2-53] MAC blocker mock 豁免计划化（§4
   候选③）：仅当出现 simulated 变体被误伤的可观察故障时触发。

## 6. 门与变异（⓪④，全部实跑）

**永久门（留在测试里）：**

- 3 个判定器自测（照 rule_gates 自测形态，正反两向）：
  - `test_kit_catches_a_window_whose_wire_rejects_the_clear_boundary`
    （clear 写被拒的坏 fixture → 窗口模板必红）；
  - `test_kit_catches_an_attach_that_never_reaches_a_milestone`
    （attach 恒不达标当 ready 交卷 → attach 模板必红）；
  - `test_kit_catches_an_adapter_that_skips_the_error_queue`
    （从不读错误队列 → 错误队列模板必红）。
- `test_certfake_never_leaks_into_production_code`（不变量门：
  `api-service/app/` 全树不得出现 certfake token —— 若某天必须在生产代码
  提及 certfake 才能过认证，即条目明令的「必须修改共同消费者」情形，
  应登记平台缺口而非放行）。

**一次性变异（做坏 → 验红 → 还原 → 复绿，均实跑）：**

| 变异 | 打在哪 | 期望红的门 | 结果 |
|---|---|---|---|
| M1 | 生产文件 `app/hal/base_station.py` 末尾加 "certfake" 注释 | 泄漏不变量门 | 红 ✓ 还原后绿 |
| M2 | certfake attach 的 evidence 恒报 diagnostic_only（偏离 manifest 声明 authoritative） | 维度 5（evidence 逐字相等） | 红 ✓ 还原后绿 |
| M3 | certfake 窗口 trust 的 context_confirmed 恒 False | 维度 6（formally_confirmed 档位） | 红 ✓ 还原后绿 |
| M4 | **模板削弱侧**：删掉窗口模板的 formally_confirmed 断言 | 判定器自测（clear 拒绝场景 DID NOT RAISE） | 红 ✓ 还原后绿 |

判定器自测固化的三条「fixture 故意做坏」（V1 clear 写拒 / V2 attach 恒
不达标 / V3 跳过错误队列）每次全量都在跑，覆盖任务要求的「抽 3 类验红」。

## 7. 验证记录

- 本片测试：`tests/test_p2_53_adapter_certification_kit.py` 46 passed。
- 扩大相关回归（本片 + 明确列出的 P1-73b/73c、P2-43/47/48/49/50/52
  与 UXM 配置编排，共 13 个文件）：254 passed。该数字由当前 HEAD
  `pytest` 实跑得出，不沿用草稿中的历史统计。
- 规则门：59 passed；全后端：5490 passed / 5 skipped。
- `compileall`、单一 Alembic head `e6a8c0d2f4b6`、staged diff-check 通过。
- 本片未修改 GUI / OpenAPI，故未运行其契约与 production build。
