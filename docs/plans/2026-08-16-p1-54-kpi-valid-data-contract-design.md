# P1-54 吞吐 KPI 有效性正式数据契约设计

## 可观察故障

UXM 已能识别每一项 KPI 查询是否真的返回有效值，但这个真值只写进
`measurement.log`，没有进入 `ThroughputMetrics` / `to_dict()`。当 UXM 返回 NaN、
查询失败或统计窗口尚无样本时，驱动仍把构造默认值 `0.0` 交给 MIMO MEASURE；
MEASURE 将它当真样本求平均，ANALYSIS 可能据此生成假的低吞吐 FAIL 与正式报告 KPI。

同一契约问题也存在于 CMW500 与实时吞吐字段：缺测与真实零值目前不可区分；但仓库没有
可核对的 CMW500 手册章节证明 ETHRoughput 响应字段顺序、单位与 sentinel，因此本片只能
保留原始诊断证据，四个正式吞吐字段一律 fail-closed，不能从有限数值反推有效。

## 改前全集

### 生产者

- `ThroughputMetrics`：共享吞吐载荷与 `to_dict()`。
- `RealUxmDriver.get_throughput_metrics()`：已有局部 `valid` 真值，但仅写日志。
- `RealCmw500Driver.get_throughput_metrics()`：成功、空响应、解析失败均落到默认零值。
- `MockBaseStation.get_throughput_metrics()`：产生模拟数值；正式链另由
  `is_mock_driver()` / `measurement_verified=False` 排除。
- `BaseStationDriver.measure_throughput_window()`：默认窗口读取入口；UXM 覆写清零窗口。

### 读取与正式消费

- `ThroughputMetrics.to_dict()` → HAL 监控 `InstrumentMetrics.metrics`。
- MIMO `MeasureExecutor` → 窗口样本、方位均值/标准差、attach milestone、JSONB phase result。
- MIMO `AnalysisExecutor` → 吞吐平均、比例、PASS/FAIL 与执行级 `validation_pass`。
- MIMO `ReportExecutor` → 正式统计与逐方位表；现有格式器已经能把 `None` 渲染为 `N/A`。
- GUI 当前没有直接消费 `kpi_valid`；实时字段若经通用 metrics API 到达 GUI，nullable
  能阻止缺测被画成零线。

### 历史兼容

- 历史 phase result 没有 `throughput_verified`，正式重算必须 fail-closed 为 UNKNOWN，
  不可通过旧数值形状猜可信。
- 新生成报告写精确整数 `throughput_trust_schema_version=1`；报告列表、详情与下载只有
  路损、吞吐两枚服务端 trust marker 都存在时才视为已净化。
- 已生成历史报告不回填、不批量改写。只有旧路损 marker 的报告同样 fail-closed，复用
  P2-26 的安全重新生成入口；重建后缺少历史 `throughput_verified` 时只输出 UNKNOWN/N/A。

## 方案比较

### A. 只在 MEASURE 读取 UXM 私有日志标记

改动最小，但 CMW500、`to_dict()`、实时曲线和其他调用方仍分不清缺测与零值；且正式层
反向依赖日志副作用，不是数据契约。否决。

### B. nullable 数值 + 显式字段有效性（采用）

`ThroughputMetrics` 的四个吞吐字段改为 `Optional[float]`，并携带 `kpi_valid` 白名单。
各真实驱动以实际解析成功为真值；Mock 可保留模拟字段有效性，但正式 provenance 门继续
把模拟值排除。MEASURE 只收 `kpi_valid["dl_throughput"] is True` 的样本；真实 `0.0`
仍是有效样本，缺测为 `None`。这是现有局部真值向正式契约的最短延伸。

### C. 新建 KPI Result 联合类型与独立数据库表

表达力更强，但会引入一套平行状态、迁移和报告机制；本故障已有明确的局部真值，不需要
新机制。否决。

## 采用方案

### 数据契约

- `dl_throughput_mbps`、`ul_throughput_mbps`、
  `dl_throughput_current_mbps`、`ul_throughput_current_mbps` 均为 nullable。
- `kpi_valid` 进入对象与 `to_dict()`；至少包含上述四项的独立有效性。
- 只有显式 `True` 才可进入正式 KPI。字段缺失、`None`、False 都按不可信处理。
- 有效性不靠 `value > 0` 推断：真实测得 `0.0` 是有效零吞吐。

### MEASURE

- 每个统计窗只收显式有效的 DL average；无有效窗的方位写
  `throughput_mbps=None`、`throughput_std_mbps=None`、`throughput_valid=False`。
- 方位有至少一个有效窗时，按有效窗求平均/标准差并写 `throughput_valid=True`。
- phase result 写 `throughput_verified=True` 仅当所有请求方位都有可信吞吐。
- attach milestone：无可信样本时 `ok=None/mean_mbps=None`；有效零值时
  `ok=False/mean_mbps=0.0`，两者不可折叠。

### ANALYSIS 与报告

- `measurement_verified`、频率身份、路损 provenance 之外，再要求
  `throughput_verified is True`。否则整个正式结论保持 UNKNOWN，吞吐 KPI 与判词为 None。
- 报告沿用现有 nullable 过滤与 `N/A` 格式，不把缺测计入统计。
- 报告写独立吞吐 trust marker；历史执行/报告缺标记默认 UNKNOWN，并通过既有恢复入口
  重新生成审计记录，不猜测、不回填。

### 失败与安全方向

- 把缺测误判为有效零值会生成假 KPI，代价高；把一个缺标记的旧值拒绝进入正式判词只会
  要求重测，代价低。因此所有正式门采用显式 allowlist。
- 本片不修改 SCPI 命令、参数、窗口控制或硬件时序。

## 验收

1. UXM 真测 `0.0` 时值为 `0.0` 且 `kpi_valid.dl_throughput=True`。
2. UXM NaN/查询失败时 DL average/current 为 None，valid=False；`to_dict()` 保留两者。
3. CMW500 在响应契约缺少厂商出处时，任意响应都保持 nullable/invalid；原始响应只作诊断证据。
4. MEASURE 不收无效零值；有效零值仍计样本。
5. 任一方位无可信吞吐时 ANALYSIS 为 UNKNOWN，执行级 `validation_pass=None`。
6. 报告中缺测显示 N/A，不出现假的 `0.0 Mbps` 或正式 FAIL。
7. Mock 数值仍被既有模拟 provenance 门挡在正式 KPI 外。
8. 只有旧路损 trust marker 的历史报告不能查看/下载；安全重建后吞吐保持 UNKNOWN/N/A，
   新报告同时带路损与吞吐两枚精确整数 trust marker。
