# P2-64 Adapter-scoped Mock 能力与注册身份设计

## 1. 可观察故障

`MockBaseStation` 当前根据 `config["model"]` 是否包含 `CMW` 猜测
`adapter_id`，并无条件返回 NR5G+LTE 能力。结果是 UXM Mock 可以接受 LTE
TestCase，CMW500 Mock 也可以接受 NR TestCase；未来第三种 Adapter 还可能被静默
归为 UXM。Mock 的指标和执行计划虽有 adapter 形状，却不是从注册真值派生，因而
不能证明真实 Adapter 的执行合同。

## 2. 选择方案

采用显式 Manifest 注入：HAL 已经根据数据库中的 selected model 解析真实 Driver
注册项，因此在选择 `MockBaseStation` 时，把该注册项的不可变
`BaseStationAdapterManifest` 作为构造参数传入。Mock 不再读取型号名称来决定身份，
也不反向调用 HAL 服务查询注册表。

没有采用以下方案：

- Mock 内按型号查询注册表：会形成 HAL 基类到服务层的反向依赖，并把一次解析变成
  两次可能漂移的解析。
- 为每个厂商增加 Mock 子类：会复制 Mock 生命周期实现，让第三种 Adapter 的接入
  成本继续随厂商增长。

## 3. 架构与数据流

1. HAL 从 selected model 取得唯一 `BaseStationAdapterRegistration`。
2. 真实模式继续构造注册的真实 Driver；Mock 模式构造唯一 `MockBaseStation`，并显式
   注入同一 registration 的 manifest。
3. `MockBaseStation` 构造时验证：manifest 类型正确、`config.model` 与
   `manifest.model_name` 精确一致。缺失 manifest、未知型号或身份不一致立即失败。
4. Mock 的 `adapter_id`、RAT、operations、measurement window、config field
   applicability、attach stage 和 metric declaration 只读该 manifest。
5. P1-75 的 compatibility evaluator 继续作为执行准入唯一真值；Mock 只提供与注册
   Adapter 相同的供给声明，不新增第二套兼容性判据。

`diagnostic_unbound` 继续在执行冻结中表达“没有绑定 adapter / manifest”；既有执行基础设施
仍要求加载一个模拟 Driver，因此该 Driver 也必须显式选择注册 Adapter，但它不能把自己的
manifest 回填进 unbound 冻结或正式证据。运行时的模拟命令形状、执行计划和窗口请求
仍必须使用这个 scoped Mock 的 manifest；这只决定诊断操作形状，不会把 unbound 提升为已绑定或正式。
旧式 `MockBaseStation("...", {})` 不再代表一个
模糊的 UXM，它必须失败；需要 Mock 的测试必须显式选择注册 Adapter。

## 4. Mock 行为投影

- `get_supported_technologies()` 从 `manifest.rat_capabilities` 映射到共同
  `RadioTechnology` 枚举，不返回能力并集。
- `get_capabilities()` 只发布当前 manifest 的 RAT/operation/config/window 声明；没有
  manifest 证据的频率和数值上限保持未声明，不从旧硬编码或真实 Driver 属性回填。
- `resolve_metric_registry()` 直接从 `manifest.measurement.metrics` 构造 diagnostic-only
  registry，不实例化真实 UXM/CMW Driver。所有指标保持模拟来源。
- execution plan 使用 Mock 实例携带的同一 manifest；operation 缺失即保持未计划，
  不靠 Mock 类上的跨厂商恒真属性补能力。
- `get_ue_info()` / `query_ue_capability()` 的 RAT 形状也从 manifest 派生；band、调制等
  manifest 没有证明的诊断能力保持空/未知，不再让 CMW Mock 发布 NR-DC/n78 等异制式信息。
- 直接调用 manifest 未声明的输入电平、RRC 或 SCell 操作时 fail-closed，避免绕过冻结执行计划后
  仍由 Mock 伪装成功或生成另一 adapter 的命令形状。
- CMW route 等既有厂商形状只在 manifest 明确声明对应 operation/profile 时启用；
  UXM 不得到 CMW route 行为。
- Mock 配置与窗口下发继续走共同 SPI 和已有 builder/plan 形状；不新增或猜测 SCPI。

## 5. 失败与安全语义

- selected model 未注册、manifest 缺失、model/adapter/registration 漂移：fail-loud，
  不构造 Mock，不连接仪器，不生成执行证据。
- Mock 收到 manifest 未声明的 RAT/operation/config shape：由 P1-75 或既有共同请求合同
  拒绝，不从请求值、默认值或真实 Driver 缓存补真。
- 所有 Mock readback、metric observation、window trust 继续标 `simulated=True` 或
  `diagnostic_only`；正式 KPI、判词和 site certification 不改变，仍为 UNKNOWN/N/A。
- 本片不改变 `diagnostic_unbound`、历史 execution 读取、正式 provenance 白名单。

## 6. 测试策略

严格 RED→GREEN 覆盖：

1. 缺 manifest、未知型号、model/manifest 漂移构造失败。
2. UXM Mock 只声明 NR5G，CMW500 Mock 只声明 LTE；反向组合被 P1-75 拒绝。
3. RAT、operations、window、attach/config/metric shape 与注册 manifest 同源。
4. metric registry 不实例化真实 Driver，且每个指标均降级为 diagnostic-only。
5. HAL real/mock/mock_force 路径都使用 selected model 的同一 registration；注册漂移在
   Mock 构造前失败。
6. 模拟窗口与指标继续被正式 KPI 门排除。
7. 既有 UXM+NR、CMW500+LTE 诊断路径和第三 Adapter 认证测试保持可运行。

## 7. 非目标

- 不实现 P2-65 的 Preview/Readiness/Freeze 三判展示。
- 不实现 P2-66 的历史证据和终态分类。
- 不实现 P2-67 的日志与导出改造。
- 不新增 manifest 数值范围字段，不把厂商 Driver 的类属性提升成无出处的共同真值。
- 不新增、修改或猜测任何仪器命令。
