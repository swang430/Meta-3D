# P1-73 CMW500 单载波 LTE 2×2 MIMO OTA 设计

**日期**：2026-08-26
**状态**：设计评审中；架构方案 #1 与本文“固定边界”已获用户批准，其余细节以本 PR 评审结论为准
**安全回滚基线**：`v0.9.1` → `0df700f9e4eb46a5e3f50c6bb22f71c93ff27087`

## 1. 可观察缺口与范围

仓库虽然已有 `RealCmw500Driver`，但它仍是早期原型：普通连接会 preset 并改变仪表，LTE
route 仍按 `1CC - 1x1` 配置，Extended BLER 的返回字段也没有按厂商手册进入正式 provenance
白名单。直接接入 MIMO OTA，可能让双路下行没有真正建立，或把状态/可靠性字段误当作 KPI。

本片让 CMW500 通过与 UXM 相同的通用 BaseStation HAL 运行 LTE 单载波 2×2 MIMO OTA，
只发布有完整仪表证据的 DL transport-block throughput 与 DL BLER。

首期包含：

- LTE 单载波 FDD/TDD（按实机选件启用）；
- `1CC - nx2`，两路下行和一路上行；
- CMW500 → 既有两路 F64 输入 → 既有 MPAC 下游链；
- UE attach；
- 有边界的 Extended BLER 测量窗口；
- 统一 evidence、Analysis、报告、历史和 GUI。

首期排除：DAU/IP 层吞吐、LTE CA、4×4、CMW 数字 IQ 外部衰落链，以及无独立手册出处的
RSRP/SINR/CQI/RI。端到端功率预算、开关/线缆损耗、F64 输入余量与路径补偿延后到正式发布
阶段，不作为当前 P1-73 开发阻塞项。

## 2. 架构与通用 BaseStation HAL

### 2.1 逻辑拓扑

LabProfile 中 `baseStation` 是互斥逻辑角色，现场选择 UXM 或 CMW500。两者复用相同的
`baseStation.DL1…DLN`、`baseStation.UL1` 逻辑端口以及相同的 F64/MPAC 下游链；端口数 N
由本次执行显式选择的 MIMO port preset 和已应用 route snapshot 决定。CMW500 首期固定 N=2；
UXM 继续支持现有 SISO、普通 2×2、alternate 2×2 与 4×4，不因 CMW500 接入被收窄。
两台仪表同时存在时，现场射频开关或固定接线决定信号源；当前开发不要求把外部 RF router
状态纳入正式能力准入或逐次执行门。

MIMO OTA 拓扑节点保存逻辑端口及 adapter 映射：UXM 物理端口不得硬编码，必须从当前
`mimo_port_preset`、已应用 topology profile 和 route snapshot 解析，因此普通 2×2 的 RF1/RF2、
alternate 2×2 的 RF3/RF4、4×4 的 RF1…RF4 与现有 UL 映射均保持原行为；CMW500 首期把
DL1/DL2/UL1 映射到当前 internal route 回读确认的 TX1/TX2/RX。拓扑编辑器、模板和运行解析器
只以逻辑端口连接对应数量的 F64 inputs；adapter 物理映射只用于展示与审计，不把外部源选择
开关提升为硬门。CAICT 模板中既有 TRP/TIS/passive 的 UXM RF5 与 VNA 路径不属于 P1-73，
必须原样保留。

CMW500 内部仍必须选择 `1CC - nx2` 并配置 RX/TX1/TX2，因为这是仪表生成双路 LTE 下行的
必要内部状态，不等同于外部 RF router。

### 2.2 顶层契约

MIMO OTA 顶层只允许使用：

- `BaseStationCapabilities`
- `BaseStationRequestedConfig`
- `BaseStationAppliedConfig`
- `BaseStationLinkState`
- `BaseStationMeasurementWindow`
- `BaseStationKpiSnapshot`
- `BaseStationCleanupResult`
- `BaseStationRemoteSessionResult`
- `BaseStationControlReleaseResult`
- `BaseStationExecutionEvidence`

顶层不得出现 `uxm_*`、`cmw_*`、具体 SCPI、厂商类判断或 Test Application/Signaling Task
分支。厂商差异只存在于驱动和 command profile。

### 2.3 能力准入

能力由驱动依据型号、固件版本和选件快照产生，不按名称猜测。CMW500 正式能力准入只绑定：

- 型号；
- 固件版本；
- 本次请求为 FDD 时的 CMW-KS500，或本次请求为 TDD 时的 CMW-KS550；
- DL MIMO 2×2 的 CMW-KS520。

选件关系依据本地原始手册 `CMW_LTE_UE_UserManual_V4-0-250_en_41 (2).pdf` §2.2.1
“Overview of options”（第 17–19 页）：CMW-KS500 是 R8 FDD basic signaling，CMW-KS550
是 R8 TDD basic signaling，CMW-KS520 增加 DL MIMO 2×2/SIMO 1×2。能力门必须按本次显式
duplex 在当前会话完成只读 identity/firmware/options snapshot 后、首次 mutating/configuration I/O
前核对；KS500+KS520 不得放行 TDD，KS550+KS520 不得放行 FDD。

外部 RF router、具体序列号和外部接线路径不属于正式能力准入键。adapter 可以注册，但正式
能力默认关闭，待用户显式启用。未完成现场确认时 GUI 显示 Warning，不使用 `Hardware Blocked`。

CMW500 的内部 `1CC - nx2` 元组不是能力准入键，也不能由驱动猜测。它以版本化
`base_station_adapter_profile` 持久化在被所选 LabProfile 的 `baseStation` binding 解析到的
`InstrumentConnection.connection_params` 中，完整保存 PCC BB board、RX connector/converter、
TX1 connector/converter 和 TX2 connector/converter。保存/API/GUI 只接受完整元组，部分字段、
未知键、TX1/TX2 connector 或 converter 复用均拒绝。执行开始且尚未发生硬件 I/O 时，runner 从
所选 LabProfile 与唯一 InstrumentConnection 解析该 profile，并把规范 route 快照冻结进本次
execution；驱动只消费冻结快照，不从当前数据库重读，也不从已有 applied route、型号或端口名反推。
共享冻结 helper 必须同时锁定 HAL 实际装载真源 `InstrumentCategory.selected_model_id` 与同一
LabProfile binding 的 `instrument_model_id`，两者必须存在且精确一致；随后只用这个唯一 model
查询 HAL real-driver registry。取得 Remote 前以权威 `is_mock_driver()` 分类当前已加载
`baseStation`：真实驱动的精确类必须与 registry 类一致；白名单 Mock 可继续开发诊断，但冻结
`execution_mode=simulated`，公开 KPI/判决永久 `UNKNOWN/N/A`。只有权威 identity 为 `cmw500`
才强制七字段 profile；`uxm` 写入显式 `not_applicable` 并继续既有 UXM route/evidence 链。
若 Mock 模式下 binding 与 selected model 均未配置，只允许冻结 `diagnostic_unbound`、执行通用
诊断且不进入任何 adapter 正式链；只缺一端、adapter 未知、两种 model 选择分叉、
registry/已加载真实类/profile 冲突均在首次硬件 I/O 前 fail-loud，且核对过程不得发送仪器命令。
不得用“缺 profile 就跳过”同时服务 UXM 与 CMW，因为那会让 CMW 缺配置静默放行。
执行冻结后还必须把同一 frozen identity 作为 lease 的 `validate_before_remote` 输入：lease 在与 HAL
reload 共用的协调锁内、Remote acquire 与任何 cache/I/O 前重新核对当前 loaded driver 的权威
real/mock 分类、精确类和 adapter；冻结后发生 reload/model switch 必须零仪器 I/O fail-loud。

### 2.4 通用配置与 debug inherit

通用请求包含显式 RAT、LTE 双工、band、DL EARFCN、bandwidth、transmission mode、2 layers、
逻辑 DL1/DL2/UL1 和 `config_mode`。不得用默认 EARFCN、route 或端口补齐缺失配置；频率、
band、EARFCN、带宽等显式分叉必须 422。P1-73 不把 UXM 的整带宽功率字段改名后推广为通用
字段，也不让 CMW 借用 UXM 的功率口径；UXM 既有行为保持兼容，CMW 功率与外部补偿延后到
正式发布前单独设计。

保存 TestCase 与活跃 `/commissioning/sessions` 入口必须使用同一 RAT-aware canonicalizer。
`CreateSessionRequest`、`_request_overrides()` 和 `build_mimo_ota_test_case()` 都要显式传递 RAT、
LTE duplex、band、DL EARFCN 与 PCell；factory 不得绕过 canonicalizer 后用 NR 默认建行。

`component_carriers[0]` 继续是工作点唯一真值，但必须从 NR-only 扩展为带 RAT 的联合类型：
NR 保留现有 NR ARFCN/SCS 兼容行为；LTE 要求单载波、显式 LTE band 与 DL EARFCN，禁止调用
`freq_mhz_to_nr_arfcn()`、禁止带 SCell，也禁止从原型默认 EARFCN 补值。`measure.py`、
`channel_asset_resolver.py` 与 `standard_channel_service.py` 三个现有 NR identity 生产者必须同时
改为 RAT-aware。SCD 的加法 schema、CRUD API 和持久化列，以及 ChannelAsset `scd_config`、
payload validator、工作台表单、OpenAPI 与 generated TS 必须携带 `radio_technology` 和
`channel_kind`；`available_channel_models` projection 同源携带这两个字段。迁移前的 SCD 行与
旧 ChannelAsset payload 来自当时唯一合法的 NR-only schema，精确 legacy translator 只在其完整
通过旧 NR 契约时补成 `nr5g/nr_arfcn`；新写入缺字段一律拒绝，不能按名称或当前 DB 猜。
LTE EARFCN 与 NR ARFCN 永不直接比较。跨 RAT 只允许在各自有手册/标准出处的转换完成后比较
中心频率和带宽。RAT、频率、band、channel number 或顶层兼容镜像冲突均在保存或硬件 I/O 前 422。

现有 `theoretical_peak_throughput_mbps=450` 仅是 NR 2×2/256QAM/100 MHz 的兼容默认，LTE
不得继承。LTE 若要形成 `throughput_ratio`，必须在本次测试配置中显式给出有限正值并冻结；未给
时绝对吞吐仍可独立发布，但 ratio、ratio pass 及依赖它的 verdict 保持 UNKNOWN/N/A。不得从
NR 默认、当前数据库、带宽或数值形状猜 LTE 理论峰值。

LTE EARFCN 的首期唯一映射依据为本地原始手册
`CMW_LTE_UE_UserManual_V4-0-250_en_41 (2).pdf` §2.2.23 “Operating bands”，第 91 页的
`N = 10 × (F - FOffset)/MHz + NOffset`，以及第 92–95 页 Tables 2-54/2-55/2-56 的
FDD UL、FDD DL 与 TDD channel/frequency ranges。helper 只实现这些表中且当前型号/选件快照
明确支持的 band；每一组 offset/range 在代码旁标注表号，未列出、SCC-only、需未具备选件或
超出范围的 band 一律 fail-loud。

`inherit_debug` 默认关闭；启用要求 `DEBUG=true`、`ALLOW_BASE_STATION_INHERIT=true` 和本次
执行显式选择。它不下发静态小区配置，只读取已有状态并允许必要的可恢复运行控制；危险配置
冲突仍阻断操作。所有结果标记 `debug_inherited`，正式 KPI、pass rate 与 verdict 保持
`UNKNOWN/N/A`。

## 3. CMW500 驱动状态机与 SCPI 证据

### 3.1 状态机

```text
DISCONNECTED
  → TRANSPORT_CONNECTED
  → IDENTITY_VERIFIED
  → CAPABILITY_VERIFIED
  → SAFE_IDLE
  → INTERNAL_ROUTE_VERIFIED
  → CELL_CONFIG_VERIFIED
  → CELL_ON
  → UE_ATTACHED
  → MEASURING
  → MEASUREMENT_COLLECTED
  → SAFE_IDLE / LOCAL
```

普通 `connect()` 只能建立会话并查询身份、固件、选件、LTE application、当前 route 和状态；
不得 preset、切换场景、打开 Cell 或写功率。Preset 只能是单独的显式维护动作。

任何静态配置或 route 写入前必须进入 `SAFE_IDLE`：读取并确认 Cell/RF 已 OFF；如为 ON，只有在
有手册出处的关闭动作成功且回读确认 OFF 后才能继续。状态未知、关闭失败或取消都必须在首条
配置/route 写命令前 fail-closed。

任一状态无法确认时停止产生正式 KPI，不自动重发带副作用的命令，尝试有出处且幂等的安全动作，
并把状态不确定写入 cleanup 与告警。

共享 MEASURE cleanup 必须返回并消费结构化 `BaseStationCleanupResult`，只负责该阶段能够真实
确认的 `stop_signaling_confirmed`、`safe_idle_confirmed` 和 warnings。它不得调用基站
`disconnect()`：VISA/HiSLIP transport 必须一直保留到租约退出时，由同一个
`release_remote_session()` 独占完成控制会话释放。它不宣称前面板 Local。`False`、`None`、异常均不可当成功；
`cleanup_chamber_instruments()` 必须检查每个安全动作的布尔返回并聚合失败。执行证据中的 cleanup
确认只能由这个结果推导，不能由 finally 已运行或无异常直接置 true。

基站控制会话释放不属于 MEASURE cleanup：它发生在 `instrument_test_lease` 退出时，必须由独立的
`BaseStationControlReleaseResult` 保存本次 lease 的 Remote session 取得、transport/session 释放和
前面板 Local 状态三类不同事实。UXM 现有厂商资料没有证明“关闭 VISA/HiSLIP 会话 = 前面板 Local”，
因此 close 成功只能令 `transport_session_released_confirmed=true`；
`front_panel_local_confirmed` 必须保持 null/unknown 并形成 Warning，除非未来有厂商出处的控制动作与
独立确认信号。正式测量发布门消费可核实的 transport release，不得把它命名或叙述成 Local 已交还；
front-panel Local 是操作状态，不得伪造，也不因缺证据反向否定已完成的真实测量。租约的基站解析
必须 vendor-neutral，CMW500 不得因缺少 UXM 风格方法而被静默跳过。finally 已运行、disconnect
成功或没有抛异常都不能推导任一确认。release 调用开始时必须仍有本次活跃 VISA/HiSLIP session，
且 close 精确成功；session 已为 None 或 close 失败都不能确认本次 transport release。
真实 session identity 的权威源只能在驱动内部：UXM/CMW 每次成功建立新的 VISA/HiSLIP session 后
生成一个不可由请求体提供、不可从地址/型号反推且不含敏感内容的 opaque UUID `session_token`，并由
`acquire_remote_control()` 的结构化结果返回给 lease。新 session 必须产生新 token，连接丢失后禁止
在同一 lease 内透明重连；若确需重连，旧 lease/window 立即失效。所有 SCPI exchange/window 从 lease
的 server-only context 消费 acquire token；`release_remote_session(expected_token)` 只能对本次实际
关闭的 session 返回其驱动内 token。当前 session token 缺失或与 expected 不同仍应保守尝试关闭当前
会话，但 release 结果必须 unconfirmed，不能复用旧 token。业务层不得读取 `_visa_session` 等私有字段。
`instrument_test_lease` 必须向每个直接持有租约的调用方暴露同一个可在 `__aexit__` 后读取的
server-owned outcome；formal runner 以及 commissioning 的单相位、adhoc、run-all 三类 lease owner
都必须在租约退出后，通过同一个持久化 helper 把带唯一 `lease_id` 的结果追加到对应 execution，
不能覆盖此前 lease、只在异常路径记录自由文本或让 commissioning 依赖 formal runner 代写。每个
measurement window 必须绑定 lease 生成并通过 server-only context 传入的 `lease_id`、驱动 acquire
返回的 opaque `session_token` 以及该 window 自身的 cleanup；正式 evaluator 只消费同 lease/token 的
exchange、cleanup 与 release。
transport release 未确认时，业务错误仍完整保留，但公开 KPI、历史正式判决和最终报告必须保持
UNKNOWN/N/A。ANALYSIS/REPORT 本身不控制仪表，不得创建空基站 lease 来生成或替换测量 provenance。

### 3.2 `1CC - nx2` 内部 route

本地原始手册 `CMW_LTE_UE_UserManual_V4-0-250_en_41 (2).pdf` 第 630 页定义：

```text
ROUTe:LTE:SIGN<i>:SCENario:TRO:FLEXible
  <PCCBBBoard>,
  <RXConnector>, <RXConverter>,
  <TXConnector>, <TXConverter>,
  <TX2Connector>, <TX2Converter>
```

该命令激活 `1CC - nx2`，最低版本 V3.5.40，需要 CMW-KS520。写入后用手册第 459–460 页的
`ROUTe:LTE:SIGN<i>?` 读取 active scenario、PCCBBBoard 与完整 RX/TX1/TX2 connector/converter
元组，确认内部 route 生效。两路 DL 的 TX connector 和 TX converter 都必须分别不同；缺字段、
任一回读不一致或复用同一 TX module 均不得 confirmed。
内部 route 回读失败影响本次驱动状态和 KPI 可信度，但不扩展成外部 RF router 准入机制。

### 3.3 配置证据与错误处理

关键配置均形成 `requested → dispatched → applied/read back`，至少覆盖 duplex、band、EARFCN、
bandwidth、transmission mode、TX antenna count、Cell state、PS connection 和 application
instance。P1-73 不把 CMW 功率纳入正式配置证据。命令传输完成或 `*OPC? == 1` 不证明错误队列
干净或配置生效；关键 applied
字段无法回读时保持 unverified，不从 requested 回填。

每次写操作采用有界旧错误清理、下发、等待、错误队列读取和权威回读。错误队列循环有上限，
timeout 在 `finally` 恢复，禁止裸 `except: pass`，超时不得自动重发 route、Cell ON、attach 或
测量启动命令。

### 3.4 Extended BLER 窗口

窗口经过 pre-clear/configure/initiate/running/ready/fetch/stop/closed 边界。厂商手册第 950–951 页
规定：`ABORt:LTE:SIGN<i>:EBLer` 进入 `OFF` 并清空测量值、释放资源；
`INITiate:LTE:SIGN<i>:EBLer` 进入 `RUN`；`STOP:LTE:SIGN<i>:EBLer` 进入 `RDY` 并保留结果；
`FETCh:LTE:SIGN<i>:EBLer:STATe?` 只接受 `OFF | RUN | RDY`。每个方位必须先 ABORt→OFF，
INITiate 后确认 RUN，等待自然完成或 STOP 后确认 RDY，再 fetch，最后 ABORt→OFF 释放资源。
任一写操作还要消费错误队列；只有所有边界及最终 OFF 都确认，窗口才可 `confirmed=True`。
timeout、取消或 fetch 异常仍必须尝试 STOP→RDY 与 ABORt→OFF；最终 OFF 未确认时立即停止整个
方位循环，不移动转台、不切 F64、不启动下一窗口，并把本次正式 KPI 全部降为 UNKNOWN/N/A。
正式 KPI 只取：

| KPI | 查询 | 字段 | 单位 | 手册页 |
|---|---|---:|---|---:|
| DL throughput | `FETCh:LTE:SIGN<i>:EBLer[:PCC]:ABSolute?` | 5 `ThroughputAver` | kbit/s | 957–958 |
| DL BLER | `FETCh:LTE:SIGN<i>:EBLer[:PCC]:RELative?` | 4 `BLER` | % | 959 |

Absolute 字段 1 是 reliability indicator，不是 BLER；Relative 字段 5 是最大可达吞吐的百分比，
不是 Mbps。两个 KPI 独立可信，一个缺证据不得清空另一个。

每条真实命令必须登记本地手册、revision、页码、固件、选件、操作类型、响应字段、单位、前置
条件、失败信号、验证查询和 cleanup。缺少出处的命令不得进入真实驱动。

## 4. 统一证据、判决、报告与 GUI

### 4.1 版本化证据

新 UXM 与 CMW500 执行均写 `BaseStationExecutionEvidence(schema_version=1)`，包含 adapter、
execution mode、identity、capabilities、requested/applied config、内部 route、lifecycle、
measurement windows、MEASURE cleanup 和按 `lease_id` 保存的 control-session release。
`adapter_id` 只用于审计显示与 command profile 注册，不允许
在 Analysis、报告、报告对比、历史或 GUI 中形成厂商分支。

每个窗口绑定 config digest、内部 route digest、UE link state、开始/停止时间、pre-clear OFF、
RUN、RDY 与 final OFF 的独立 exchange IDs 和 KPI。
每个方位再绑定当前窗口、F64 channel evidence、位置回读和路损应用证据。请求方位全集必须精确
匹配，缺失不当 0，多余历史方位不计入统计。

### 4.2 唯一正式信任函数

直接来自基站测量窗口的 throughput/BLER 在 Analysis、报告、报告对比、历史、下载和 GUI 中
统一消费：

```python
evaluate_base_station_metric_trust(
    evidence,
    metric_name,
    expected_config,
    expected_position,
) -> FormalMetricTrust
```

它要求规范 schema、dispatch 模式、获准 adapter/profile、真实身份、配置回读、内部 CMW route、
完整测量窗口、正确字段/单位、当前 execution provenance、方位绑定、MEASURE cleanup，以及与该
window 的 `lease_id` 精确匹配且确认 transport/session 已释放的 control-release 结果。前面板 Local
状态另行显示为 confirmed/unknown Warning，不能由 close 推断，也不进入测量真实性判据。外部 RF router 不进入该
函数。旧 `throughput_verified`、`kpi_valid` 或 `config_applied` 不能单独恢复正式 PASS。

旧 UXM 只通过精确 legacy translator；冲突时 UNKNOWN。CMW500 原型历史没有 legacy 信任路径。

### 4.3 GUI、API、报告、报告对比和历史

GUI 继续消费 OperationalLab 唯一 `baseStation`，展示型号、固件、选件、LTE 能力、内部 route、
模式和 readiness。adapter 可注册，正式能力默认关闭；未完成现场确认显示黄色 Warning，不使用
`Hardware Blocked`。后端不可达、缓存旧数据或关键仪表状态未知不得复活旧绿。

Commissioning 方位 KPI 表也是正式消费方：不得直接格式化原始 `throughput_mbps`/BLER。后端必须
按同一个逐指标 evaluator 输出 server-owned trust projection；GUI 主 KPI 只显示 trusted 值，
diagnostic 值必须黄色标注“非正式实测”，unknown 显示 N/A。Mock、debug、生命周期未闭合以及
配置/route/方位不匹配均不能以普通 Mbps/% 外观发布。

API 使用 `base_station_*` 通用字段。旧 `uxm_*` 输入 deprecated 兼容；GUI 不再写旧字段；新旧
冲突时 422。live OpenAPI、checked-in YAML 和 GUI generated TS 必须同步。

报告只发布对应权威 trust 函数确认的 KPI。报告对比不得把全部聚合指标误交给 base-station
evaluator，而是按来源换源：`avg_throughput_mbps` 从逐方位受信 throughput 聚合；
`throughput_ratio` 只由该受信均值和本次执行显式提供并冻结的 LTE theoretical peak 重算，缺失
时保持 UNKNOWN/N/A，绝不继承 NR 的 450 Mbps 默认；
`rsrp_variance_db` / `avg_sinr_db` 分别从 P1-63 的逐方位、逐指标 RF trust 后聚合；未来新增
BLER 对比才调用 base-station BLER evaluator。未获信任的值不得进入 delta、summary statistics、
repeatability 或 `formal=true`，且一个指标 unknown 不得清空其他独立可信指标。缺测不写 0，
debug 不打印数值后再声明“不可信”。正式 Analysis 与 REPORT 都必须位于测量 lease 的 control
release 之后：formal runner 将末尾连续的 ANALYSIS/REPORT 一起从租约内延迟，租约退出并持久化
与 measurement window 同 `lease_id` 的 release 后才按
ANALYSIS → REPORT 顺序执行；不得保留一份租约内 UNKNOWN 的 `validation_pass` 再只重建显示投影。
commissioning run-all 同样延迟这两个正式化相位；单相位/adhoc 的 ANALYSIS 或 REPORT 不取得新的
基站 lease，只读取此前 MEASURE window 绑定的 release；缺失或失败保持 UNKNOWN/N/A。cleanup 与
匹配 lease 的 transport release 确定前不发布最终报告、正式历史判决或 completed 判词。历史列表只
返回摘要，详情按 execution ID 读取完整快照；旧或畸形 evidence 保持 UNKNOWN，不从当前数据库
或旧正文补证。

## 5. 开发拆分与验证

### 5.1 P1-73A：共享 HAL 清理

保持 UXM 行为不变，建立通用 BaseStation 类型、带 RAT 的 LTE/NR 工作点、兼容字段、通用
executor/evidence key 和 `baseStation.DL1…DLN/UL1` 逻辑拓扑及 adapter 映射。不得修改 UXM
SCPI/profile/CA/SCell；普通 2×2、alternate 2×2 与 4×4 的现有 port preset 均需回归。完成标准
是共享 MIMO 路径无 UXM type import、无厂商类判断，UXM fake 行为不变，最小 CMW fake 能消费
显式 LTE EARFCN 并走到同一证据门安全 UNKNOWN。

### 5.2 P1-73B：CMW500 驱动核心

重构现有原型：只读 connect、能力探测、command evidence、`1CC - nx2` 内部 route、配置回读、
Cell/attach 状态机、Extended BLER 窗口、错误队列、timeout、cleanup 和 inherit debug。adapter
可注册但正式能力默认关闭，并以 Warning 表示现场确认尚未完成。

### 5.3 P1-73C：OTA/GUI/报告集成

把 CMW500 接入 OperationalLab、MIMO OTA 方位证据、F64/位置/路损链、正式信任函数、GUI、
报告和历史。正式启用只绑定型号、固件版本和选件组合，由用户显式开启，不绑定外部 RF router。

### 5.4 TDD 与回归

每片严格执行 RED → 最小 GREEN → 相关回归 → 全后端 → GUI build → compileall → 单一
Alembic head → diff-check → fresh 内审 → Codex R1/R2。R2 无 P1立即合并；R2 仍有 P1继续
P1-only 外审到覆盖最新 HEAD 无 P1。R2+ P2/P3只报告，不自动积压。

验证覆盖通用 HAL contract、UXM 回归、CMW builder/parser、状态机错误注入、F64/位置/路损、
Analysis/报告/历史、GUI/OpenAPI 和全量回归。模拟驱动复用真实命令拼装和解析器，但模拟值不进入
正式判决。

## 6. 现场确认、上线与回滚

### 6.1 渐进确认

现场按低风险到高风险执行：只读身份/版本/选件 → Cell/RF 关闭时验证内部 `1CC - nx2` route →
单小区 attach → 单方位短测量窗口 → 少量方位 OTA smoke → 完整方位重复性测试。

外部 RF router/开关状态只作为现场 Warning 和操作员确认信息，不作为开发或正式能力准入的硬
阻塞项。端到端功率预算、路径补偿、线缆/开关损耗和 F64 输入余量在正式发布阶段单独评估。

### 6.2 必测失败场景

覆盖缺 KS520、固件过低、LTE app/实例变化、内部 route 回读不一致、配置错误队列、UE 未 attach、
测量未启动、返回字段不足、reliability 无效、timeout、取消、cleanup 部分失败、control session
释放失败、前面板 Local 状态未知、
后端重启后的未知状态，以及 inherit debug 尝试生成正式报告。

每种失败都必须给出明确原因，不得折叠成 0 或通用“连接失败”。现场信息尚未确认时显示 Warning，
允许继续开发调试；正式 KPI 是否可信仍由当前执行的仪表配置和测量证据决定。

### 6.3 上线、版本与回滚

- 当前安全回滚点：`v0.9.1`；
- 三个软件 PR 合并：建议 `v0.9.2-rc.1`；
- CMW500 真机正式验收：建议 `v0.10.0`。

P1-73 不做破坏性数据库迁移；新 evidence 放在现有版本化 JSON envelope；新字段只增加不删除。
回滚优先关闭 CMW500 正式能力并切回 UXM，必要时部署 `v0.9.1`，不删除执行、报告或仪器资料。

P1-73 软件开发完成必须满足：顶层与厂商无关、UXM 无回归退化、CMW connect 不修改仪表、
LTE 1CC 2×2 内部 route 与配置有回读、throughput/BLER 来自有边界窗口、模拟/未知/debug 不进入
KPI、GUI/Analysis/报告/历史共用信任函数、取消和清理失败可见、正式能力只按型号/版本/选件判断
且具备默认关闭的显式启用门、真机 smoke 待确认时明确显示 Warning，并能安全回滚到 `v0.9.1`。
真机 smoke 通过是后续正式发布启用条件，不是 P1-73A/B/C 合并阻塞项。
