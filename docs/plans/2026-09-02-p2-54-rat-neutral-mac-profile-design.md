# P2-54 — RAT-neutral MAC Test Profile 设计

## 1. 可观察故障

当前 `MIMOOTAConfiguration`、`MeasureExecutor` 与 `BaseStationDriver`
共享一组由 NR 语义主导的扁平参数。UXM 可以解释 `mcs`、NR TDD slot
pattern、HARQ process、SCS 与 CSI-RS；CMW500 的正式窄路径实际使用 LTE
RMC/RB/TM，却仍接收这些 NR 参数并把大部分记为 `no_equivalent`。

这会产生两个假象：

1. 一个 adapter 接受了调用，不代表它能表达该 TestCase 的全部 MAC 意图；
2. 同一扁平表可同时承载 LTE 与 NR 字段，保存、预览、冻结、执行和证据可能
   各自挑选一部分，无法证明本次测试究竟采用了哪一套语义。

P2-54 只修复这个平台边界，不扩大 CMW500 的组合能力、不补 LTE TDD，也不新增
或猜测任何 SCPI。P2-55/P2-56 继续拥有 capability matrix 与 LTE TDD 的实现范围。

## 2. 改动前全集

按 `AGENTS.md` 0.5，在写代码前把产生方与消费方列全：

| 事实 | 产生方 | 消费方 | P2-54 处置 |
|---|---|---|---|
| TestCase MAC 参数 | `schemas/mimo_ota/config.py::MIMOOTAConfiguration`、commissioning 创建/adhoc overrides、GUI `MIMOOTAConfigForm` | compatibility preview、execution freeze、MEASURE、MCS 一致性、统计窗口、结果 payload | 收敛为可辨识 profile；旧扁平字段只作输入迁移 |
| 仪表 bootstrap topology 参数 | `UxmTopologyProfile`、DB `InstrumentTopologyProfile`、`TopologyProfileEditor` | HAL 初始化 `apply_topology_profile` | 保留为仪表初始化配置；不得再成为 TestCase 执行 MAC 真值 |
| compatibility requirements | `build_measure_execution_requirements_from_configuration` | 保存预览、LabProfile sync、readiness、freeze、P2-66 outcome、日志导出 | 同一 projection 冻结 profile snapshot + digest |
| adapter 接受边界 | UXM/CMW500 `BaseStationAdapterManifest` | P1-75 evaluator、binding preview、freeze 与 I/O 前复核 | manifest 声明接受的 profile kind/version/RAT/source |
| MAC 下发 SPI | `BaseStationDriver.configure_mac_throughput_test`、UXM、CMW500、Mock | MEASURE 唯一调用点及认证测试 | 只接收一个冻结 profile snapshot；结果结构移回 vendor-neutral 模块 |
| MAC 下发结果 | `MacThroughputConfigResult`、CMW receipt、UXM command/error queue | `_mac_config_blocker`、日志、执行证据 | 绑定 profile digest；不再把 `no_equivalent` 当作成功维度 |
| 统计基 | 旧 `stat_count`、P1-74 window request | `window_s`、CMW `SFrames`、窗口 evidence、结果摘要 | 由 profile 的共同 statistical window 唯一产生 |
| NR 生效 MCS 核对 | 旧 `mcs/enable_amc` | `check_mcs_consistency` | 只对 NR profile 执行；LTE RMC 不套 NR MCS 判据 |
| API/GUI 镜像 | live OpenAPI、`api/openapi.yaml`、generated TS、手写类型、TestCase 表单 | readiness/配置编辑 | 四镜像同步；GUI 按 profile kind 渲染，不按厂商名分支 |
| 历史 compatibility digest | P1-75/P2-65 旧 freeze（`mac_profile` 缺失或 `null`） | P2-66 evidence outcome、日志导出、报告/历史 | 显式识别为 pre-P2-54 legacy-profile snapshot；可读但不补真为新 profile |

commissioning 的 session、saved phase、run-all 与 adhoc 最终都构造或读取
`MIMOOTAConfiguration` 并走同一 freeze，因此不另建 commissioning profile。

## 3. 方案比较

### 方案 A：只在 freeze 时从旧扁平字段临时派生

改动最小，但保存/GUI 仍允许 LTE 与 NR 字段共存；预览与执行之间仍存在两份形态，
也无法让用户在保存时看到 profile 不可表达。否决。

### 方案 B：manifest 提供自由 JSON Schema，TestCase 保存任意字典

GUI 可完全 schema-driven，但 profile 结构、枚举与 digest 都失去编译期和 Pydantic
判别联合的保护；第三 adapter 很容易把未知字段吞掉后返回成功。否决。

### 方案 C：平台拥有判别联合，manifest 只声明接受边界（采用）

平台定义版本化 `nr_throughput` 与 `lte_rmc` profile；manifest 只声明接受的
kind/version/RAT 及可审计来源。TestCase、preview、freeze、MEASURE、GUI、API 与证据
都传同一个 profile snapshot。adapter 只负责把已经通过 kind/version 门的 profile
翻译到自己的既有实现。

该方案新增机制最少：复用 P1-75 requirements/digest、P2-50 execution plan 与现有
adapter receipt，不引入新表、不自动发现能力、不新增厂商命令。

## 4. 权威模型

### 4.1 Profile 判别联合

在 vendor-neutral HAL 模块新增不可变、`extra="forbid"`、JSON-safe 模型：

- `MacStatisticalWindow`
  - `unit = "subframes"`
  - `count`
- `MacMetricRequirement`
  - 稳定 metric key
  - scope
- `NrMacTestProfileV1`
  - `kind = "nr_throughput"`、`version = 1`、`rat = "nr5g"`
  - 共同 intent/window/metric requirements
  - NR 专属 MCS、AMC、全 RB、scheduler、TDD、HARQ、SCS、CSI-RS
  - Keysight 本地手册来源
- `LteRmcMacTestProfileV1`
  - `kind = "lte_rmc"`、`version = 1`、`rat = "lte"`
  - 共同 intent/window/metric requirements
  - LTE 专属 RMC、full-RB、固定调度、TM；不出现 NR MCS/TDD pattern/HARQ
    process/SCS/CSI-RS
  - R&S 本地手册来源
- `FrozenMacTestProfile`
  - discriminated profile payload
  - payload 的 canonical digest

`mimo_layers` 与 `modulation` 仍是 MIMO OTA 的 RAT-neutral 测试意图；PCell 的 RAT、
LTE TM/SCS 仍由 `ComponentCarrierConfig` 拥有。profile 中需要引用这些值时必须逐字段
与 PCell/共同意图一致，不能静默选任一端。

### 4.2 TestCase 迁移边界

`MIMOOTAConfiguration.mac_profile` 是新执行的唯一 MAC 真值。旧记录没有该字段时，
schema 在纯内存中按 PCell RAT 做一次确定性迁移：

- NR：从旧 NR 字段构造 `nr_throughput@1`；
- LTE：只提取已有窄 RMC 路径能表达的共同意图，NR-only 字段不进入 LTE profile；
- 显式 profile 与 PCell RAT/TM/SCS 或共同 MIMO 意图冲突时 fail-loud。

旧扁平 MAC 字段只作为反序列化输入，不再由执行、GUI 或 API 输出消费。不会新增数据库
列或批量改写历史 TestCase JSON；下一次正常保存会自然写入 canonical profile。

### 4.3 Manifest 与 compatibility

`BaseStationAdapterManifest` 增加不可变 `mac_profiles` 声明：kind、version、RAT、
source reference。UXM 只声明 `nr_throughput@1`，CMW500 只声明 `lte_rmc@1`；
adapter-scoped Mock 继承其目标 manifest 边界。

P1-75 evaluator 在现有 RAT/operations 判定后继续检查：

- 新 TestCase 必须有 profile；
- profile RAT 必须等于 requested RAT；
- kind/version 必须被同一 manifest 接受。

`no_adapter` 继续只表示 diagnostic_unbound，不补任何 profile 能力。

### 4.4 历史 digest

`BaseStationExecutionRequirements.mac_profile` 从固定 `None` 扩为可选 snapshot，仍使用
`exclude_none=True` 算 digest。因此旧 payload 的缺键与显式 `null` 重算值保持不变。

P2-66 读取时增加显式分类：有 compatibility snapshot、digest/manifest/verdict 都合法，
但 `mac_profile` 缺失的记录是 `legacy`，不是“没有 compatibility snapshot”，也不是
malformed。它可以读取、展示和下载，不能被新代码补成某个 profile 后取得新的正式资格。

## 5. 执行与证据

MEASURE 从 execution freeze 读取 `FrozenMacTestProfile`，不从可变 TestCase 或 topology
profile 重建。共同执行器只调用：

```text
configure_mac_throughput_test(frozen_profile)
```

UXM/CMW500/Mock 在函数入口再次验证 profile kind/version/RAT 与自身 manifest，验证完成前
不得发生 connect 以外的首个配置 I/O。结果带回 `profile_digest` 与既有逐字段 receipt；
CMW500 不再收到 NR-only 字段，所以 `no_equivalent` 不构成成功结果。旧 `no_equivalent`
字段可保留为历史解析兼容，但新 profile 路径必须为空。

执行证据保存 frozen profile digest 与 MAC receipt。`operation_succeeded` 只说明设备未拒绝
本次操作；逐字段 confirmation 仍由 receipt 表达，二者不得互相替代。模拟 receipt 全部
保持 unknown/simulated，正式 KPI 门不变。

统计窗口、窗口等待时间、P1-74 `SFrames` 请求和结果摘要全部从 frozen profile 的共同
statistical window 读取。NR MCS 一致性只在 `nr_throughput` 且 AMC 关闭时运行；LTE RMC
不再套用 NR MCS 比较。

## 6. GUI 与 API

TestCase 表单按 `profile.kind` 渲染：

- 公共区：测试意图、统计窗口、metric requirements；
- NR 区：MCS/AMC/RB/scheduler/TDD/HARQ/SCS/CSI-RS；
- LTE RMC 区：RMC/full-RB/fixed/Transmission Mode，只展示 P2-51 已支持的窄形态；
  P2-55/P2-56 未实现组合保持不可选。

分支条件只读 RAT/profile kind，不读 UXM/CMW500 型号名。OpenAPI 的 live schema、
checked-in YAML、generated TS 和手写 GUI 类型同步同一判别联合。readiness/preview 继续只
显示服务器 verdict/reasons，不在前端重算兼容性。

`TopologyProfileEditor` 保留仪表 bootstrap 用途并加清晰边界提示；它的旧 MAC 字段不再
驱动 TestCase execution profile。

## 7. 不变量与拒绝场景

1. LTE TestCase + NR profile、NR TestCase + LTE profile：保存/preview 即拒，零 I/O。
2. manifest 未声明 kind/version：preview/sync/readiness/freeze 同理由拒，零 I/O。
3. profile digest、requirements digest、manifest digest 任一漂移：执行前拒。
4. 执行期间 TestCase、LabProfile 或 topology profile 改变：不影响本次 frozen profile。
5. CMW500 新路径不接受 NR-only 字段，也不以 `no_equivalent` 换取成功。
6. Mock 只能产 simulated/unknown receipt，不能进入正式 KPI。
7. 旧 compatibility snapshot 可读但保持 legacy；不查当前 TestCase/manifest 补真。
8. 不新增数据库真值、不新增或猜测 SCPI、不改变正式 provenance 白名单。

## 8. 验证边界

- 严格 RED→GREEN：model/digest、manifest/evaluator、preview/sync/readiness/freeze、
  UXM/CMW500/Mock SPI、MEASURE/commissioning、证据/P2-66 migration、GUI/API 四镜像。
- 变异：交换 profile kind、删/改 profile digest、让 CMW 接收 NR profile、让执行器回读
  可变 TestCase、让旧 snapshot 被判 malformed、让 `no_equivalent` 继续放行，均应红。
- 最终运行相关链、全后端、GUI 契约与 production build、compileall、单一 Alembic head、
  base-to-HEAD diff-check，并做 fresh 独立功能内审。
