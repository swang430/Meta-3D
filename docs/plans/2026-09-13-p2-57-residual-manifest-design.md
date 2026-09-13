# P2-57 声明面残项：资产支持与注册对账设计

## 可观察故障与裁决

P2-57/#448 的 `ChannelEmulatorManifest` 已使操作和加载模式显式化，但仍只含
`schema_version`、`adapter_id`、`model_name`、`vendor`、`load_modes`、`operations`。
同一个 `external_waveform` 加载模式可以来自 `standard_3gpp` 或 `custom_static`；
当前执行请求虽冻结 `ChannelAsset.source_type`，却只用加载模式判断驱动能否执行。
将来若某 adapter 仅实现其中一种资产来源，它可通过当前静态兼容门，在实际加载时才失败。
另一缺口是操作声明与类实现的对账主要依赖测试期 AST 门：运行时注册一个错误声明的
adapter，可能在现场才触发基类的 `NotImplementedError`。

本片只补这两个静态缺口，不按 #448 的旧清单重建整套执行证据。P2-59～62 已把
SAFE_IDLE、release、逐操作 receipt 和现场认证分别放到 execution plan、session、
operation receipt、certification；它们是逐次执行的事实，不能复制为 manifest 的
“已证实”常量。`ChannelAsset` 承载随 `.smu` 变化的通道/端口拓扑，不进 per-driver
manifest；拓扑解析仍需 OTA 样本与 Direction 手册依据，保持独立待评估项。

## 路径选择

1. **采用：v3 静态资产支持声明 + 注册期实现对账。** 在当前 manifest 上增加四种
   `ChannelAsset.source_type` 的逐项支持声明；冻结显式资产时，使用同一冻结来源同时核对
   source type 与已存在的 load mode。注册期用纯类检查拒绝声称 implemented 但仅继承
   基类拒绝桩的驱动。没有新仪器 I/O。
2. 不采用“把证据强度、SAFE_IDLE、release 结果都写进 manifest”：它会复制随 attempt
   变化的 receipt/session 真值，还容易把“命令完成”误当“字段生效”。
3. 不采用只改文档：这样不能阻止下一个型号在运行时错误声明能力。

## 数据与权限边界

`ChannelEmulatorManifest` v3 增加不可变 `asset_sources`：
`standard_3gpp`、`custom_static`、`vendor_file`、`rt_dynamic` 恰好各一项，状态为
`implemented` / `not_implemented` / `not_applicable`，带非空解释及可选手册/代码出处。
`implemented` 必须对应本仓既有 source-type → engine-mode → load-mode 映射中已实现的
加载模式；反向不成立，因为没有显式 ChannelAsset 的历史执行仍可请求加载模式。
F64、FS16、Mock 逐项字面声明；FS16 不得因继承基类而宣称可加载资产，Mock 的声明只
说明诊断覆盖，不构成正式资格。未经既有实现和来源证实的格子保守填
`not_implemented`，不把 NotebookLM 的推断作为设备已生效证明。

v1/v2 的词汇、冻结 payload 与原始 digest 保持原样解析；不得在读历史件时填入 v3
字段、重算旧 digest 或补授正式资格。新冻结件使用 v3。说明性 `reason` 与出处不进
binding digest；source type 与 support 状态进 digest，因此支持矩阵改变会被漂移门发现。
执行计划是另一份独立版本化契约：v3 manifest 仍映射到现有 **v2 execution plan**
操作词汇，不把 manifest 版本直接赋给 plan 版本。现有冻结 binding 校验接受 v2
历史与 v3 当前 manifest；旧 plan 的原始 digest 不变，现代新写入仍需完整 load request。

## 产生方与消费方全集

| 事实 | 权威产生方 | 本片消费或核对方 |
|---|---|---|
| 资产来源 | `ChannelAsset.source_type` → `FrozenChannelAssetResolution` | execution load request / freeze / MEASURE 重验；不能从文件扩展名反推 |
| 请求加载模式 | `engine_mode_for_channel_asset_source_type` 与 `requested_channel_emulator_load_mode` | v3 静态校验、既有 execution plan；旧无资产路径只走既有 load-mode 门 |
| 驱动能力 | F64、FS16、Mock 类级 manifest | real-driver registry、HAL loaded-driver/binding 对账、执行冻结 |
| 逐次证据 | operation receipt、session terminal、site certification | formal outcome 与报告；本片不更改判词，也不从 manifest 补真 |

注册对账对每个被注册的真实 CE 类在首次取注册表时运行，检查 manifest 的类型、
adapter 身份、每个 implemented 操作是否有非基类拒绝桩的有效方法、资产支持与加载
模式不矛盾；失败为可读配置错误，发生在任何 CE I/O 前。诊断 Mock 在既有 mock 注册
边界接受相同纯检查，但仍由 HAL 的模拟白名单限制正式使用。实例级 manifest 与注册
类声明不一致继续由现有 binding 对账拒绝，不另造注册表或客户端真值。

## 失败与兼容行为

- 显式资产来源未声明、重复、非法或状态不支持：manifest 构造或执行冻结 fail-loud；
  不回退到相同加载模式，也不继续取得真实仪器租约。
- 已注册类声称实现却仅继承基类拒绝桩：注册时拒绝；不能以 `hasattr` 作为证据。
- 当前驱动与冻结 manifest、source type 或 load mode 漂移：沿用 P2-58/59 的
  loaded-driver 与 digest 拒绝门，不重新查询可变 TestCase 或资产补真。
- 旧 v1/v2 冻结件按原 schema/digest 历史读取；缺少资产声明不算已证实的 v3 支持。
- SAFE_IDLE、release、错误队列、频率/电平/路损/多普勒回读继续只由现有实际 exchange
  与 receipt/session 判定；模拟或未知证据不得进入正式 KPI。

## 取证边界

2026-09-13 查询 PROPSIM NotebookLM 的 User Reference 指针包括 §20.4.1.7
`*OPC?`、§20.4.2.1 错误队列、§20.4.3 运行状态。其回答把完成/无错进一步概括为
“完整证明配置已生效”，这超出所引原文；本片不采纳该推断、不新增或猜测 SCPI。
若实现中需要新的仪器语义，必须先回到仓内手册原文逐项核对，否则保持 unknown。

## 验收与验证

严格 TDD：先用合成 adapter 证明同一 load mode 下错误 source type 旧实现会放行，
再证明错误 implemented 声明在旧注册边界不会被拒；每条先 RED 后最小 GREEN。
覆盖 F64/FS16/Mock 声明矩阵、显式资产和历史无资产路径、v1/v2 原摘要兼容、
binding/plan/current runtime 漂移以及正式证据不受静态声明升级。运行受影响链、
全后端、GUI 若有消费契约则定点与 build、compileall、单一 Alembic head、diff-check；
fresh 独立功能内审确认 P1=0 后按仓库外审流程开 Ready PR。

本片不改数据库、正式 provenance 白名单、厂商命令或现场验收状态；P2-63 仍 HOLD。
