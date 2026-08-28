# P2-44 BaseStation 单一 Binding Resolver 与 manifest 驱动注册设计

## 目标与边界

本片解决一个可观察故障：`InstrumentCategory.selected_model_id`、LabProfile
`instrument_bindings`、唯一 `InstrumentConnection`、厂商 profile、进程内 loaded driver 与
execution freeze 由多段代码分别解释，曾出现 GUI 显示已保存，但同步、readiness 或执行冻结读取到
另一份配置的情况。

本片建立唯一 `ResolvedBaseStationBinding` 与 adapter manifest。预览、LabProfile 同步、readiness
和 execution freeze 必须消费同一 resolver 结果与同一 `binding_digest`；GUI 的 adapter profile
表单由服务端 manifest 字段描述生成。数据库仍只保留现有 catalog、connection 和 LabProfile JSONB，
不新增数据库真值、不做自动发现、不修改或猜测任何 SCPI，也不实现 P2-45 的 Diagnostic/Formal
站点认证状态。

## 动手前全集

### 真值产生方

1. `bootstrap/instruments.py` 建立 BaseStation 型号目录并初始化 `selected_model_id`。
2. `PUT /instruments/{category_key}` 保存 selected model、唯一 connection 和
   `connection_params["base_station_adapter_profile"]`。
3. `PUT /lab-profiles/{id}/instrument-bindings/{category}/sync-current` 把当前 catalog 选择复制到
   LabProfile binding。
4. `LabProfileWizard` 创建新 LabProfile 时直接提交 `instrument_bindings`。
5. HAL reload 根据 selected model、connection 和 registry 装载 driver。
6. CMW500 专用接口只更新现有 connection 上的正式能力授权；本片不改变该授权真值。

### 真值消费方

1. `freeze_base_station_adapter_profile()` 重走 model/binding/connection/profile/registry 校验并写
   execution freeze。
2. `build_cmw500_lte_2x2_readiness()` 独立重走同一批查询并另造 preview。
3. LabProfile sync 独立校验 CMW profile 后拼 binding。
4. HAL bootstrap 独立从 selected model 和 connection 拼 driver config。
5. Instrument Catalog GUI 按 `model === "CMW500"` 决定七字段表单和保存形状。
6. HAL readiness/OpenAPI/手写 TS 只暴露 CMW 专属镜像。
7. formal runner 与 commissioning 通过同一 freeze helper 进入 P2-42 session；本片保留这一入口。
8. 诊断上下文、通用 LabProfile wizard 与 positioner 也读取 `instrument_bindings`，但不解释
   BaseStation adapter profile；它们只需保持现有通用行为，不在本片改造。

## 方案比较

### 方案 A：共同 resolver + 驱动类静态 manifest（采用）

真实 driver registry 继续是 `(category, model) -> DriverClass` 唯一注册表。每个已注册 BaseStation
driver class 增加一个严格、不可变的 `adapter_manifest`；公共 helper 校验 manifest，并把内部
profile Pydantic schema 投影成可序列化字段描述。唯一 resolver 在一次数据库读取中解析 category、
binding、model、connection、profile、registry class、loaded driver 与 transport identity，返回
不可变 `ResolvedBaseStationBinding`。

优点：不复制第二张 registry；第三种 BS 只新增 driver + manifest；现有数据库无需迁移；所有活入口
可逐步换源到同一对象。缺点：要同步后端、OpenAPI 与 GUI，但这是验收要求本身。

### 方案 B：在每个 API 端点外包一层 facade（拒绝）

freeze/readiness/sync 各自调用 facade，再由 facade 读取现有对象。它能减少部分重复代码，但 facade
仍无法保证每条入口用同一 digest，HAL bootstrap 和 GUI 仍有厂商分支，下一 adapter 还会修改多处。

### 方案 C：把 model/connection/profile 全部复制进 LabProfile 新表（拒绝）

新增规范化 binding 表或把 connection id/profile 再持久化一遍，看似能固定快照，却制造第二份数据库
真值并需要迁移/回填。它也不能证明 loaded driver 与冻结 transport 同源，违背本片最小范围。

## Adapter manifest

新增严格不可变合同：

- `schema_version`：当前为 1；
- `adapter_id`、`model_name`、`vendor`：与 registry key 和 driver `adapter_id` 精确一致；
- `rats`：应用支持的规范 token；
- `capabilities`：vendor-neutral BaseStation SPI 能力 token，不复述瞬时仪器状态；
- `profile_requirement`：`required | not_applicable`；
- `profile_schema`：公开字段路径、标签、必填性、示例和说明；不携带自由 Python/SCPI 代码；
- `manual_sources`：仓库内厂商资料的审计指针；不把推断写成仪器能力；
- `diagnostic_supported` 与 `formal_gate`：只描述 adapter 合同边界。`formal_gate` 仅允许现有
  `legacy_provenance` 或 `connection_approval`，不创建 P2-45 的站点认证状态。

内部注册 helper 同时持有严格 profile model；公开 manifest 只输出 JSON 安全字段。CMW500 的七字段
由既有 `BaseStationAdapterProfile` 验证，UXM 明确 `not_applicable` 且 profile 为空。新增 adapter 若
缺 manifest、adapter id 重复、model 名不一致或 profile schema 与验证模型不一致，registry 初始化即
fail-loud。

## 单一 resolver 与 digest

`resolve_base_station_binding(db, hal, lab_profile, *, lock=False)` 返回：

- category/model/connection/LabProfile 的稳定 id；
- 规范 binding 行与 endpoint；
- 校验后的 adapter profile resolution；
- 完整 public manifest；
- expected driver module/name/adapter；
- real 模式下锁定 connection transport identity；
- loaded driver 分类与实际 transport identity；
- 现有 CMW connection approval 快照（仅适用时）；
- `binding_digest`。

`binding_digest` 只覆盖服务器持久化的 binding 真值：schema、category/model/connection/lab id、endpoint、
adapter/profile、manifest identity、connection approval 和 expected transport。loaded driver 是执行前
复核项，不进入该稳定 digest；否则 HAL reload 会让同一已保存 binding 得到不同 preview digest。

resolver 的结果组合使用白名单：

- real：model/binding/connection/manifest/driver class/transport 必须全部同源；
- configured mock：仍解析同一 model/connection/profile/manifest，结果标 simulated；
- unbound mock：仅保留既有两端型号均为空的 `diagnostic_unbound`；
- 任一缺字段、重复 binding、歧义 connection、endpoint/transport 漂移、profile 不合 schema 或 loaded
  driver 不同源均 fail-loud；不得猜第一条或从请求值回填。

execution freeze 保存 resolver 的完整稳定投影和 `binding_digest`，再附 execution-scoped runtime
identity。`validate_frozen_base_station_before_remote()` 继续在 P2-42 锁内复核 loaded driver，不查询
数据库改写快照。

## API 与 GUI 数据流

### 保存与同步

Instrument Catalog 保存仍写现有 selected model/connection/profile。保存响应新增所选 model 的 public
manifest，不自动修改任何 LabProfile。显式 sync 在锁定 category/profile 后写 binding，再调用唯一
resolver；若 resolver 失败则事务回滚。sync 响应包含 binding 与 resolved preview，GUI 不再自行拼接
“已同步”事实。

### 预览与 readiness

新增 LabProfile BaseStation binding preview 读取端点，直接序列化 resolver；不连接、不发 SCPI。
HAL readiness 用同一 resolved preview，再叠加当前 driver identity/capability evaluation。公开响应新增
vendor-neutral `base_station_binding`；既有 `cmw500_lte_2x2` 在本片保留为兼容镜像，但必须从共同
结果派生，禁止继续独立查询数据库。后续 adapter 只新增 manifest，不新增顶层 readiness 字段。

### GUI

Instrument model 带可选 `base_station_manifest`。BaseStation 抽屉按 manifest 的 `profile_schema.fields`
渲染输入并构造嵌套 profile，不按型号字符串判断；无 profile 的 adapter 不显示字段。readiness 与
LabProfile 同步反馈展示共同 `binding_digest`、resolved adapter/model/connection 和明确冲突原因。
CMW 专用正式授权控件仍走既有专用 endpoint；它是否显示由 manifest `formal_gate` 驱动，不把授权写入
通用 connection params、本地缓存或 LabProfile。

OpenAPI、generated TS 与手写类型同步更新。旧客户端未识别新增可选字段仍可工作；既有 CMW readiness
字段本片不删除。

## 错误与安全边界

- resolver 是只读解析，不触发 HAL reload、connect 或 SCPI；sync 只有解析成功才 commit。
- `one_or_none()` 遇到多 connection 必须作为歧义拒绝，不选第一条。
- preview/readiness 不得把 resolver 失败包装成 ready；错误以结构化 `status=invalid` 与原因显示。
- mock、profile unknown、loaded driver/transport 不同源均不能授予正式资格。
- execution 仍只认 freeze；保存后修改只影响后续 execution。
- 不改变 P2-43 receipt/evidence、P2-42 cleanup/release 或正式 KPI provenance 白名单。

## 测试与验收

1. 同一 fixture 的 preview、sync 结果、readiness 与 execution freeze `binding_digest` 完全一致。
2. 缺 model/binding/connection/profile、重复 binding/connection、endpoint 漂移、registry/driver/transport
   不同源均在首个仪器 I/O 前失败。
3. CMW 与 UXM 用同一 resolver 契约；UXM 不读取 CMW profile。
4. configured mock 保留 simulated，unbound mock 只作诊断；正式 KPI 不变。
5. GUI 表单只由 manifest 字段生成；新增 fake 第三 adapter manifest 时无需修改 App 厂商分支即可渲染。
6. OpenAPI live/checked-in/generated TS/手写类型一致；适用 GUI 契约与 production build 通过。
7. 相关后端、全后端、compileall、单一 Alembic head、diff-check 与 fresh 功能内审通过。

现场 driver identity/真实 transport 与下一 adapter 真机认证仍是现场项，本地 fake 不能替代。
