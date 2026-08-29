# P2-49 BaseStation Metric Registry 设计

## 目标与边界

本片解决一个可观察故障：BaseStation 指标的键、方向、单位、作用域与正式资格目前散落在驱动字段、
`kpi_valid`、execution evidence writer 的两条硬编码映射、正式 evaluator 的 `_METRIC_UNITS`、报告投影和
GUI 兼容字段中。CMW500 只公开 DL throughput/BLER，UXM 已经回读 UL throughput/BLER、CQI、RI，
但共同 evidence 丢掉了这些真实能力；同时 UXM 手册把 BLER 返回定义为 ratio，现有兼容路径却把原值写成
`percent`，RI histogram 的 bin 是 RI 值，现有路径又把它改写成“层数”。这些分叉会同时造成能力丢失和
单位/语义被错误升级。

本片只建立 profile-scoped、execution-frozen、vendor-neutral 的逐指标 registry 与 observation 合同，
并让现有 CMW500、UXM 与 Mock 映射已有回读。零新增/猜测 SCPI，零数据库迁移，不改变正式 provenance
白名单；不提前实现 P2-50 capability-driven execution plan、P2-51 CMW500 MAC/FRC 配置或 P2-52 UXM
closed-window。

## 动手前全集

### 当前产生方

1. `BaseStationMetricCapability` 已在 adapter manifest 中声明 `key/direction/unit/scopes/evidence/source`，
   但只允许 `mbps/percent/index/raw/not_applicable`，没有 profile-scoped registry 或稳定 digest。
2. CMW500 manifest 声明 `dl_throughput_mbps` 与 `dl_bler_percent` 两项；Extended BLER window 提供已有
   authoritative closed 生命周期。
3. UXM 公共 manifest 因两个 Test App 的保守交集而声明 measurement unavailable、metrics 为空；实际
   loaded command profile 决定哪些命令存在。
4. `RealUxmDriver.get_throughput_metrics()` 已回读 DL/UL 平均与当前吞吐、DL/UL BLER ratio、CQI average、
   RI histogram，以及单位未知的 UE report raw 值；结果被压入 legacy `ThroughputMetrics` 字段与
   `kpi_valid`。
5. `RealCmw500Driver.measure_base_station_window()` 产生 DL throughput/BLER 与 P2-48 window trust。
6. Mock/Fake driver 可产生模拟或缺失值，必须保留 simulated/diagnostic provenance。

### 当前消费方

1. `BaseStationMeasurementWindow` 只携带 legacy `ThroughputMetrics` 与 window trust，没有冻结 registry、
   registry digest 或逐指标 observation。
2. `append_base_station_measurement_window()` 只硬编码 `dl_throughput_mbps` 与 `dl_bler_percent`，并从
   `kpi_valid` 推断是否写入。
3. `base_station_execution_evidence.py` 用固定 `_METRIC_UNITS` 和固定两项投影判 trust。
4. MEASURE 聚合 legacy DL/UL/CQI/RI 字段；旧 RF KPI 路径还能把 `rank_indicator` 当正式值消费。
5. Analysis、Report、详情、重建、下载、比较、ReportDataCollector、history、commissioning 与 GUI 当前只
   认识两项兼容投影。
6. P2-45 qualification/site certification、P2-48 window trust、attempt/lease/session/cleanup/release 是正式
   值的独立门；逐指标 registry 不得替代它们。
7. 历史 execution evidence 没有 metric-registry 版本，必须继续按旧两项合同读取；显式出现新版本但畸形
   时必须 fail-closed。

### 对称路径与失败路径

- 真实 CMW500 / 真实 UXM IRAT profile / UXM NR profile / 显式 Mock / diagnostic_unbound。
- DL / UL / link；PCell / all-cells；engineering unit / ratio / index / raw。
- 回读成功 / 部分缺失 / 设备拒绝 / 错误队列 / 超时 / 取消。
- 生成 / 窗口聚合 / execution 写入 / 当前读取 / 重算 / 下载 / 历史读取。
- capability declared-but-missing、observation undeclared、unit/scope/digest drift、非有限值、模拟值。

## 仪器语义依据

- UXM DL/UL OTA throughput 与 BLER：
  `Instrument_API_Doc/Keysight UXM NR SCPI/5G_NR_Test_Application_SCPI_Reference.zip` 中
  `UXM5G_SCPI_02_NR_PHY_Measurements.md` 的 “NR BLER/Tput > DL OTA / UL OTA”。BLER 数组字段名是
  `ack-ratio`、`nack-ratio`、`pdschBlerRatio`，因此稳定键使用 `*_bler_ratio`，不把原值改名为 percent。
- UXM CQI：同文件 “NR CSI > CQI”，索引 4 明确为 `cqi_average`，稳定键使用 `cqi_index`。
- UXM RI：同文件 “NR CSI > RI”，histogram bin 是 RI 值 0..7。共同 observation 保留应用层加权得到的
  `ri_index`，不再将 `(bin+1)` 解释成空间层数。
- UXM UE report 的 RSRP/SINR JSON 单位没有本片可核对依据；如保留，只能使用 `*_raw`、unit=`raw`、
  `diagnostic_only`，不得形成 `*_dbm` 或正式工程量。
- CMW500 两项继续沿用 P1-73C/P2-46 已冻结的手册来源与现有命令，不新增字面量。

## 方案比较

### 方案 A：只扩充静态 adapter manifest

给 UXM 公共 manifest 直接补全所有指标。改动小，但会把 IRAT profile 的命令能力错误推广到 NR profile，
并让 loaded profile drift 无法审计。否决。

### 方案 B：另建 runtime metric registry

保留 manifest，再建一套 service registry。能表达 profile 差异，但形成第二套键/单位/来源真值，未来 adapter
仍要双写。否决。

### 方案 C：扩展现有 capability，并解析 execution-frozen registry（采用）

`BaseStationMetricCapability` 继续是唯一逐指标声明。静态 adapter manifest 表达跨 profile 的保守能力；
loaded driver 在 Remote acquire/identity refresh 后、首个 measurement I/O 前，根据当前已冻结 command
profile 解析不可变 `BaseStationMetricRegistry`。registry 只引用现有命令可用性和手册来源，零仪器 I/O，
并随 execution evidence 冻结稳定 digest。窗口返回 registry-bound observations；writer 和所有下游只从
冻结 registry 读取 key/unit/scope/evidence/source，禁止厂商分支或自由文本单位。

## 合同形状

### `BaseStationMetricRegistry`

- `schema_version=1`
- `adapter_id`
- `profile_id`
- `metrics: tuple[BaseStationMetricCapability, ...]`
- canonical digest 覆盖全部字段，键必须唯一且稳定排序

unit 新增 `ratio`。`authoritative` 只证明该指标值的仪器语义与权威回读；能否进入正式 KPI 仍须同时满足
P2-48 closed-window、P2-45 formal qualification/site certification、attempt/lease/session、cleanup/release
以及本次 evidence identity 等全部独立门。

### `BaseStationMetricObservation`

- `schema_version=1`
- `registry_digest`
- `key`
- `scope`
- `value: finite number | null`
- `simulated`
- `exchange_ids`
- `reason`

observation 不携带可自报的 unit/evidence/source；这些只能从冻结 registry 解析。未声明键、scope 分叉、
digest 分叉、非有限值或 simulated 值均不得成为正式值。声明但缺回读的指标以 `value=null` 留下 unknown
审计记录，不能以 0 或 legacy sentinel 回填。

## Profile-scoped registry

- CMW500：保持 `dl_throughput_mbps` 与 `dl_bler_percent`。
- UXM IRAT profile：按现有命令字段声明 DL/UL throughput、DL/UL BLER ratio、CQI index、RI index；当前值、
  raw UE report 等只在确有现有命令时声明为 diagnostic-only。
- UXM NR profile：只声明该 profile 真实存在命令的指标，不能继承 IRAT 的 throughput/BLER。
- Mock：可以保留相同 shape 供诊断，但全部 observation simulated，正式值永远为空。

UXM 当前 P2-48 lifecycle 仍为 unavailable，所以即使某指标的语义是 authoritative，本次窗口也只能形成
诊断投影；P2-52 取得 closed-window 证据之前不得升级。

## Evidence、投影与兼容

新 execution evidence 写入 `metric_registry_contract_version=1` 与 registry snapshot。每个 window 持久化
registry digest 和 observations。共同 evaluator 生成 `metrics: {stable_key: FormalMetricTrust}`；现有
`dl_throughput_mbps`、`dl_bler_percent` 只作为由 generic map 派生的兼容镜像，不再是唯一真值。

真正缺版本字段的历史 evidence 继续使用固定两项 `_METRIC_UNITS` 兼容读取；一旦版本字段存在，缺 registry、
畸形 registry、observation key/unit/scope/digest 分叉一律 fail-closed，绝不从当前 adapter manifest、loaded
profile、legacy `kpi_valid` 或 sentinel 回填。

新合同下，旧 RF KPI 的 `rank_indicator` 不得绕过 registry 进入正式判定；UXM RI 只以 `ri_index` 按当前
窗口资格投影。其他 legacy 字段可保留兼容显示，但不能成为新 evidence 的权威来源。

## 明确不做

- 不新增或修改 CMW500/UXM SCPI 命令。
- 不实现执行前 capability-driven 编排（P2-50）。
- 不补 CMW500 MAC/FRC 正式配置（P2-51）。
- 不把 UXM 当前累计/clear-read 窗口升级为 closed-window（P2-52）。
- 不引入 adapter 特定下游分支、数据库迁移、自动发现或正式 provenance 白名单放宽。

## 基线

P2-49 focused 基线共 412 项：411 passed、1 failed。唯一失败是旧测试仍要求 roadmap Current Focus 为
P2-47，属于测试镜像陈旧，不是产品功能回归；按仓库规则严重度上限 P2。本片只在同步 roadmap 当前事实时
最小更新该镜像，不围绕测试债务扩张范围。
