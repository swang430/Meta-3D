# P2-48 Measurement Window Trust Contract 设计

## 目标与边界

本片解决一个可观察故障：当前 BaseStation 测量窗口同时由驱动类变量
`measurement_window_cardinality`、驱动返回的 `confirmed`、四个生命周期布尔、manifest 的
`measurement.lifecycle` 和正式 evidence writer 各自描述。共同执行器还会调用厂商驱动自己的
`unconfirmed_window_allows_diagnostic_execution()` 决定是否继续。它们可以静默分叉：错误的
`confirmed=True` 或错误窗口数能先进入结果，直到后续某个消费者才因形状不符变成 N/A；缺 closed
边界的窗口也没有一个共同、可审计的诊断资格来源。

本片只建立 execution-frozen、vendor-neutral 的 Measurement Window request/receipt，并让既有
CMW500、UXM 与 Mock 映射现有事实。零新增/猜测 SCPI，零数据库迁移，不改变正式 provenance
白名单，不提前实现 P2-49 指标 registry、P2-51 CMW500 MAC 配置或 P2-52 UXM closed-window。

## 动手前全集

### 当前产生方

1. `BaseStationDriver.measurement_window_cardinality` 与 `measurement_window_count()` 决定每方位窗口数。
2. `BaseStationMeasurementCapability` 在 manifest 声明 cardinality、scope 与 lifecycle；CMW500 当前声明
   `single/pcell/authoritative_closed`，UXM 因 Test App 交集不足而把 measurement 整体置空。
3. `RealCmw500Driver.measure_base_station_window()` 用既有 Extended BLER 命令形成
   pre-clear OFF → RUN → RDY → final OFF，并返回四布尔及 `confirmed`。
4. `RealUxmDriver.measure_base_station_window()` 复用既有 clear/read 路径，但没有权威 closed 边界；
   `confirmed=False`，再由 UXM 专属策略允许诊断继续。
5. `MockBaseStation.measure_base_station_window()` 生成模拟指标、四布尔 false、`confirmed=False`。
6. 单元测试 fake adapter 大量直接构造 `BaseStationMeasurementWindow`，能构造彼此矛盾的 confirmed/
   lifecycle 组合。

### 当前消费方

1. `MeasureExecutor._measure_base_station_samples()` 先读驱动窗口数，再调用窗口方法；正式与诊断分流读
   `window.confirmed` 和驱动专属 policy hook。
2. 方位循环分别聚合指标，并把每个 native window 暂存在 `pending_base_station_windows`。
3. `append_base_station_measurement_window()` 在 cleanup 后绑定 attempt、lease、session、position，复制四个
   生命周期布尔并写指标。
4. `BaseStationMeasurementWindowEvidence`、`_attempt_lifecycle_envelope()` 与
   `base_station_attempt_lifecycle_is_complete()` 按“每方位恰好一个窗口”及四布尔判生命周期完成。
5. `_formal_envelope()`、`evaluate_base_station_metric_trust()`、报告、详情、重建、下载、比较与 site
   certification 最终都依赖同一个 formal envelope。
6. `_raw_metric()` 只接受某方位恰好一个窗口；UXM requested-cardinality 多窗口的新 evidence 因而无法形成
   清晰诊断投影。
7. `base_station_metric_projection_required()` 是历史证据边界；新窗口合同不得从 adapter 名称或当前状态
   回填，但真正缺新字段的历史 execution 仍须按既有兼容合同读取。

### 对称路径与失败路径

- 真实 CMW500 / 真实 UXM / 显式 CMW500 Mock / 普通 Mock / diagnostic_unbound。
- PCell / all-cells；single / requested cardinality。
- 成功 / 设备拒绝 / 查询异常或超时 / 取消。
- 生成 / execution 写入 / 当前 attempt 完成 / 正式评估 / 诊断读取 / 历史读取。
- cleanup stop、SAFE_IDLE、同 lease control release 与 transport release 必须继续保守绑定。

## 方案比较

### 方案 A：只强化现有布尔检查

在 writer 再校验 `confirmed == all(four_flags)`，并补窗口数量断言。改动小，但 manifest、驱动类变量、
厂商 policy hook 仍是多真值；scope、cardinality 与历史边界没有被冻结。否决。

### 方案 B：增加独立旁路认证器

保留旧窗口对象，另建 service 根据 adapter 名称重建窗口强度。短期兼容容易，但会复制厂商分支，并让
P2-50 的 capability-driven plan 继续背负旁路。否决。

### 方案 C：冻结共同 request，驱动返回结构化 trust receipt（采用）

从 execution-frozen adapter manifest 生成不可变 request，固定 scope、lifecycle、cardinality、请求窗口数、
实际期望窗口数与序号。CMW500/UXM/Mock 只报告本次 clear/run/ready/closed 事实、模拟标记与 exchange ids；
共同类型派生 formal/diagnostic 资格，禁止隐式布尔使用。MEASURE 按冻结 request 控制调用次数并精确核对
回执，writer 持久化同一 request/receipt。新 execution 的正式 envelope 只读该结构；历史缺字段时保留旧
读取，显式存在但畸形/不完整时 fail-closed。

该方案把“计划”和“仪器事实”分开：manifest/request 决定本次要求，receipt 证明实际发生了什么；不需要
猜仪器命令，也不把 UXM 当前诊断窗口升级为正式窗口。

## 合同形状

### `BaseStationMeasurementWindowRequest`

- `schema_version=1`
- `scope`: `pcell | all_cells`
- `lifecycle`: `authoritative_closed | clear_read_only | unavailable`
- `cardinality`: `single | requested`
- `requested_window_count`、`expected_window_count`、`window_index`
- canonical digest 覆盖以上冻结字段

`single` 必须 `expected_window_count=1`；`requested` 必须等于请求数；序号必须落在
`0..expected_window_count-1`。

### `BaseStationMeasurementWindowTrust`

- `schema_version=1`
- 精确回绑 request digest 与 request shape
- `clear/run/ready/closed` 各为 `confirmed | unknown | unavailable`
- `simulated`、`exchange_ids`、`reason`

只有真实 `authoritative_closed`、四阶段全 confirmed、scope/cardinality/request digest 全匹配，才派生
`formally_confirmed=True`。`clear_read_only` 或 `unavailable` 可以显式允许诊断，但永远保持
`formally_confirmed=False`；模拟窗口只可诊断。已声明 authoritative closed 却有任一阶段不确认时阻断，
不能降级成“继续诊断”掩盖设备拒绝。

## Manifest 与 UXM 边界

CMW500 保持 `single/pcell/authoritative_closed`。UXM 的公共 adapter manifest 不宣称 profile-specific
closed-window；它只声明 requested cardinality、可请求 scope 与 `unavailable` 生命周期，且不在本片扩充
逐指标 registry。真实 UXM 回执因此可保留诊断值，但永不获得正式窗口资格。P2-52 若取得并冻结具体
Test App 的权威 closed 证据，再升级 manifest/request，而不是在本片借旧 per-metric 标志绕过。

## Evidence 与历史兼容

新初始化的 execution evidence 写入 `measurement_window_contract_version=1`。每个 window 持久化 request、
trust、attempt、lease、session、position、cleanup、release 与指标。formal envelope 对新合同逐方位校验：

1. request digest/shape 一致；
2. 每方位窗口数与 expected count 一致，序号全集且唯一；
3. receipt 正式确认；
4. current attempt、lease、session、config/route digest、cleanup/release 全部匹配；
5. lifecycle exchange ids 是 execution exchange ids 子集。

真正缺 `measurement_window_contract_version` 的历史 evidence 沿用旧四布尔读取；一旦版本字段存在，缺
request/trust、畸形字段或混入旧窗口一律 fail-closed，绝不从当前 manifest、adapter 名称或旧
`confirmed` 回填。

## 明确不做

- 不新增任何 CMW500/UXM SCPI。
- 不定义新的指标键、单位或聚合语义（P2-49）。
- 不补 CMW500 MAC/FRC 正式配置（P2-51）。
- 不把 UXM clear/read 或累计读数升级为 closed-window（P2-52）。
- 不新增数据库真值、自动发现或迁移。
- 不改变 Diagnostic/Formal policy、site certification 或正式 provenance 白名单。

