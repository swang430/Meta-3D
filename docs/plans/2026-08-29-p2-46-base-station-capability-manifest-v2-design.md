# P2-46 BaseStation Capability Manifest v2 设计

## 目标与边界

本片解决一个可观察故障：当前 manifest 只有扁平 `rats` / `capabilities`，真实运行能力又分散在
`get_supported_technologies()`、`get_capabilities()`、多个 class var 与测量实现中。UXM manifest
声明 LTE + NR，而实际公共运行接口只支持 NR5G；CMW500 与 UXM 又都声明
`measurement_window`，但前者能权威证明完整 Extended BLER 生命周期，后者当前只有 clear/read、
没有手册支持的 closed 边界。GUI/readiness/未来 adapter 若只读扁平 token，会把不同证明强度显示成
同一种能力。

本片只建立不可变、JSON-safe 的能力声明与注册一致性校验，并让既有兼容访问器从 manifest 派生。
不修改或猜测任何仪器命令，不改变 Attach、measurement receipt、正式 KPI 白名单或站点认证；这些
分别由 P2-47～P2-49 消费本片声明。CMW500 MAC 与 UXM 窗口缺口仍留给 P2-51/P2-52，不能用声明
替代真机证明。

## 动手前全集

### 当前产生方

1. `RealCmw500Driver.adapter_manifest` 与 `RealUxmDriver.adapter_manifest` 写扁平 RAT/能力。
2. `BaseStationDriver` 的 `input_level_control_supported`、`rrc_reconfiguration_supported`、
   `mac_throughput_configuration_supported`、`measurement_window_cardinality`、带宽/层数上限再次声明
   能力。
3. CMW500/UXM/Mock 分别覆写 `get_supported_technologies()`；UXM 的运行返回与 manifest 分叉。
4. 驱动 `get_capabilities()` 另造面向监控的自由 `InstrumentCapability` 列表，不能作为执行资格真值。
5. P2-44 registry 校验 adapter/model/profile，但不校验上述能力镜像是否一致。

### 当前消费方

1. `BaseStationDriver.apply_requested_config()` 用 `get_supported_technologies()`、最大带宽与最大层数做
   首个 I/O 前校验。
2. MEASURE 用 class var 决定 MAC、RRC、输入电平与窗口基数。
3. Catalog/OpenAPI/GUI 暴露并展示 manifest；Binding Resolver 把 manifest 身份纳入 digest。
4. GUI 用 manifest `profile_requirement/profile_fields` 构造厂商 profile；当前错误地把 manifest
   `schema_version` 当成 profile envelope 版本。
5. readiness/site certification 读取 manifest 的 `formal_gate`，但尚不解释指标/生命周期能力。
6. 测试 fixture、generated TS、手写 TS 与 checked-in OpenAPI 是公开合同镜像。

## 方案比较

### 方案 A：继续增加扁平 token（拒绝）

新增 `attach_data_bearer`、`window_closed`、`metric_ul` 等字符串最快，但字段间没有不变量；第三个
adapter 很容易声明互相矛盾的 token，无法表达每个配置字段、Attach 阶段与指标的证明级别。

### 方案 B：一次重写成万能 BaseStation 状态机（拒绝）

把 LTE 与 NR 的配置、Attach、测量阶段强行统一，范围会越过 P2-47～P2-50，并诱导共同层解释厂商
状态。它会把“共同证据语言”误做成“相同仪器状态机”。

### 方案 C：结构化 manifest + 兼容镜像（采用）

manifest v2 增加严格的 RAT、配置字段、Attach 阶段、测量窗口与指标声明；旧 `rats/capabilities`
仍公开，但只由结构化字段派生并校验，不能手填出另一份真值。现有运行 class var 暂保留给旧消费方，
registry 在启动时校验它们与 manifest 一致；P2-50 再移除分散消费。

## Manifest v2 数据合同

### 版本分离

- `schema_version=2` 只表示 public manifest 形状。
- 新增 `profile_schema_version: int | null`；CMW500 为 `1`，UXM 为 `null`。
- GUI 读取/构造 profile envelope 只使用 `profile_schema_version`，不得再复用 manifest 版本。
- 已保存的 CMW500 `BaseStationAdapterProfile.schema_version=1` 保持有效，无数据库迁移。

### 结构化声明

1. `rat_capabilities`
   - 规范 token 只允许 `lte | nr5g`，与 `BaseStationRequestedConfig.radio_technology` 同源；
   - `rats` 由其派生，UXM 当前只声明 `nr5g`，CMW500 只声明 `lte`。
2. `config_fields`
   - 必须完整覆盖 `BaseStationRequestedConfig` 的所有可请求字段；
   - 每项声明 `field`、`support=authoritative|diagnostic_only|not_applicable`、`readback` 与原因；
   - `diagnostic_only`/`not_applicable` 不授予正式配置确认。
3. `attach_stages`
   - 使用稳定阶段 `cell_ready | ue_registered | rrc_connected | data_bearer_established`；
   - 每阶段声明 `authoritative | diagnostic_only | unavailable | not_applicable`；
   - 本片只描述当前已有证据，不增加命令。P2-47 才让每次执行返回 stage receipt。
4. `measurement`
   - 声明窗口基数、作用域、生命周期证明级别和 metric 列表；
   - metric 声明稳定键、方向、单位、作用域与当前证据资格；
   - CMW500 如实声明 PCC、单窗口、完整生命周期、DL throughput/DL BLER；
   - UXM 可选择的 `5G_NR_Test` 与 `LTE_NR_IRAT` 方言没有共同的 clear/OTA throughput/BLER
     命令集，因此 adapter 级 manifest 保守声明 `measurement=null`，不把 IRAT 专属能力并成
     整台 UXM 的无条件能力；已有 IRAT 诊断路径继续可运行，后续由 profile-scoped registry 投影。
5. `operations`
   - 替代手写扁平 `capabilities` 的来源；旧 `capabilities` 由它派生。

所有列表必须非空（真正不适用的嵌套项除外）、token 唯一、字段全集无重复。`authoritative` 必须带
可审计的本地手册来源指针；本片不重新解释命令，只复用现有驱动附近已经核对的来源。

## 运行时一致性

- real adapter 的 `get_supported_technologies()` 从 `adapter_manifest.rat_capabilities` 派生，移除 UXM/
  CMW 的重复覆写；Mock 继续使用自己的模拟合同且不进入 real registry。
- registry 校验：adapter/model/profile、manifest v2、legacy mirrors、adapter 级 class var 能力与结构化
  声明必须一致；声明 measurement window 时必须覆写共同方法，分叉时服务启动 fail-loud。UXM 的
  RRC/MAC 可用性由当前 Test App 命令全集实时派生，不提升成 adapter 级无条件声明；配置字段的
  adapter 级 support/readback 同样取“受控出处 + 方言交集”，只有 IRAT 具备出处与权威回读的能力
  留在运行时 receipt，不把另一套无受控出处的 pure-5G 命令静态标绿。
- `get_capabilities()` 保留为瞬时监控展示，不得反向覆盖 manifest 或执行资格。
- Binding digest 已包含完整 manifest identity；manifest 改变只影响后续 preview/freeze，不改历史
  execution。

## API 与 GUI

- Catalog、live OpenAPI、checked-in `api/openapi.yaml`、generated TS 与手写类型同步 manifest v2。
- GUI profile helper 改读 `profile_schema_version`；无 profile adapter 继续返回 `null`。
- 本片只显示结构化能力，不新增厂商专用控件，也不把 capability 声明当成实时 readiness 或正式认证。
- 旧客户端仍可读派生的 `rats/capabilities/profile_fields/formal_gate`；新增字段为服务端必出字段。

## 错误与安全边界

- 声明不完整、重复、镜像分叉或运行 class var 不一致时 fail-loud，不选择任一副本。
- `diagnostic_only` 与 `unavailable` 不能被 GUI/readiness 显示为正式可用。
- manifest 不连接仪器、不发 SCPI、不读取错误队列；现场能力不能由本地测试升级。
- 不改变 P2-45 qualification、站点认证或正式 provenance 白名单。

## 测试与验收

1. UXM 公共 RAT 真值精确为 NR5G，CMW500 精确为 LTE；旧分叉消失。
2. structured → legacy mirrors 唯一派生，显式矛盾输入被拒绝。
3. config field 声明覆盖全部共同请求字段；Attach/measurement/metric token 无重复且状态合法。
4. CMW profile v1 在 manifest v2 下仍可由 GUI 读取与构造；UXM 不产生 profile。
5. registry 对 model/adapter/profile/RAT/class var/窗口声明任一分叉 fail-loud；profile 类型由 driver
   自声明，第三 adapter 不需要修改核心 adapter-id 分支。
6. 第三 adapter fixture 只增加 manifest 即能通过 catalog/OpenAPI/GUI 类型合同，不新增厂商分支。
7. 相关后端与 GUI 契约、production build、全后端、compileall、单一 Alembic head、diff-check 和 fresh
   功能内审通过。

现场命令、CMW MAC 配置与 UXM authoritative closed window 均不属于本片验收；后两者分别保持
P2-51/P2-52 的本地取证 + 现场复验双状态。
