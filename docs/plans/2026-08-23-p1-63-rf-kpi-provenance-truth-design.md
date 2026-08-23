# P1-63 正式 RF KPI 逐指标真值门设计

## 可观察故障

在 MIMO OTA 的 MEASURE 阶段，即使基站、信道仿真器与转台都是真实驱动，当前代码仍会用
目标 RSRP、路径损耗、探头增益和随机噪声合成逐方位 RSRP/SINR；同时会直接消费
`ThroughputMetrics.rank_indicator` 的默认值。随后这些值被标成 `measurement_source=instrument`
与 `measurement_verified=true`，进入 ANALYSIS 的阈值判定、正式报告和执行历史。

这不是“模拟数据显示得不够清楚”，而是正式数据真值错误：仪器没有给出可信读数时，系统仍可能
生成看似合理的 PASS/FAIL。UXM 驱动已经明确说明厂商手册未定义 L3 返回值究竟是原始码点还是
工程单位，因此不能用公式猜，也不能用目标配置反推。

## 改前全集

| 环节 | 当前站点 | 当前风险 | P1-63 裁决 |
|---|---|---|---|
| 数据契约 | `hal/base_station.py::ThroughputMetrics` | RI/RSRP/SINR 有数值默认值，可信性另在 `kpi_valid` | 数值与有效性成对消费；默认值永不单独成为证据 |
| UXM 写方 | `hal/uxm_base_station.py` | RI 有明确解析门；RSRP/SINR 因单位未知已保持 invalid | 保持现状，不新增/猜测 SCPI 语义 |
| CMW500 写方 | `hal/cmw500_base_station.py` | 可回填数值，但正式链必须仍检查逐指标 validity 与真实 provenance | 只接受显式有效且有限的读数 |
| MEASURE 聚合 | `executors/measure.py` | 合成 RSRP/SINR；无条件聚合默认 RI | 删除合成正式值；逐指标白名单聚合 |
| ANALYSIS | `executors/analysis.py` | 直接对逐方位三个字段求均值并判阈值 | 任一请求方位或任一必需指标缺可信样本时整体 UNKNOWN |
| 报告生成 | `executors/report.py` | 会渲染并发布上述值 | 未验证值显示 N/A，整体正式判决保持 UNKNOWN |
| 报告信任 | `services/report_service.py`、`api/report.py` | 旧信任 envelope 不要求 RF KPI 证据 | 增加服务端拥有的版本化 RF KPI 信任快照；旧/畸形报告安全重建 |
| 执行历史 | `api/test_execution.py` | 旧 flags 可形成正式 verdict | 与 ANALYSIS/报告复用同一显式白名单 |
| GUI | `components/Commissioning/Phases.tsx` | 数值存在即直接展示 | 无可信证据显示 N/A/未验证，不显示合成数字 |

道路测试/VRT 的 RSRP/SINR 是另一条产品链，不在本片范围；P1-64 的静区证据问题也不与
P1-63 混做，只在 roadmap 保留下一顺位。

## 方案比较

### 方案 A：保留合成值，只增加 simulated/unverified 标签

拒绝。标签不能阻止值被其它消费方误当正式数据，而且真实驱动组合下合成值很容易被误标为真实。

### 方案 B：合成值移到新的“诊断估算”字段

本片不采用。当前没有明确用户需求消费这组估算值；新增平行数据机制会扩大报告与兼容面，且仍可能
被未来消费方误用。

### 方案 C：删除正式链合成值，建立逐指标显式白名单（推荐并已批准）

只有同时满足以下条件的样本进入正式聚合：

1. 对应仪器路径为 explicit-real，而不是 mock/simulated/unknown；
2. `metrics.kpi_valid[指标] is True`；
3. 数值类型与单位契约明确，且数值有限；
4. 每个请求方位都有至少一个可信样本；
5. RSRP、SINR、RI 三族全部完整。

任何条件不满足，诊断执行仍可完成并生成报告，但 RF KPI 的正式状态为 UNKNOWN，数值在正式
消费者中为 N/A，不参与阈值与 pass rate。

## 数据契约

MEASURE 写入一个版本化、服务端生成的 `rf_kpi_trust` 快照。最小语义为：

- `schema_version`：精确整数 `1`；
- `source`：只允许 `explicit_real`、`simulated`、`unknown`；
- `requested_azimuths` 与 `verified_azimuths`：用于证明全集覆盖，不从结果长度猜测；
- `metrics`：RSRP/SINR/RI 分别记录 `verified`，三个指标不可互相救回；
- `formal_rf_kpi_verified`：只在 explicit-real、方位全集和三指标全集都满足时为 true。

解析采用精确白名单。字段缺失、类型错误、额外状态组合或旧历史均不能被旧布尔字段救回；只允许
安全重建后重新发布。

## 正式消费规则

- ANALYSIS 在计算任一 RF KPI 阈值前先验证共享快照；失败时 `validation_pass=None`，RF KPI
  汇总字段为 null，并写出明确 warning。
- 报告只在共享快照通过时渲染正式 RSRP/SINR/RI；否则显示 N/A，overall 为 UNKNOWN。
- 报告详情、下载、历史恢复与执行历史 verdict 都复用同一个解析/白名单，不能各写一份近似规则。
- GUI 只显示后端已经裁决的可信值；未知状态用“未验证/N/A”，不从数值存在性推断真实性。
- 模拟执行、缺测与旧历史继续可观察，但永不计入正式 KPI。

## 安全与兼容性

- 不增加、不修改任何仪器命令，不对 UXM 原始码点做单位换算。
- 不修改数据库表；状态保存在既有 JSON 结果/报告 envelope 中。
- 旧报告默认不可信，走 P2-26 已有安全重建链；无法重建时保持 UNKNOWN/N/A。
- 本片不会让诊断执行因为缺 RF KPI 而崩溃或硬停止；它只阻止正式判决。

## 验收

1. 真实驱动但三个 KPI 均 invalid：不再产生随机 RSRP/SINR，不再采用默认 RI，执行完成且 verdict UNKNOWN。
2. 只有部分指标或部分方位可信：整体 RF KPI 不完整，正式 verdict UNKNOWN。
3. 三指标、全部请求方位均为 explicit-real 且有限：保留现有正式阈值判定。
4. mock/simulated 数值：可供诊断观察，但正式报告/历史为 N/A/UNKNOWN。
5. 旧、缺失或畸形 `rf_kpi_trust`：详情/下载不放行旧 PASS，必须安全重建或保持 UNKNOWN。
6. P1-64 在 roadmap 有独立占位，P1-63 不修改静区判据。

## 当前 HEAD 验证事实

- P1-63 + P1-54 + UXM KPI + 报告兼容 + P1-61 + 完整规则门：**203 passed**。
- 两次 fresh 内审共发现并按 TDD 收口六条 P1：持久化信任快照必须与当前逐方位有限数值、
  精确请求方位全集和当前 explicit-real provenance 完全一致；未请求的额外行与当前模拟来源均
  不得借旧快照进入正式统计；报告必须先完成信任裁决再做统计，非对象/畸形历史行只能降级为
  N/A/UNKNOWN；语义失配的旧快照须重写成服务端 unknown envelope，不能生成完成但不可查看的报告。
- 全后端（从 `api-service/` 正确工作目录运行）：**4339 passed / 5 skipped**。
- GUI 本片契约：**3 passed**；production build 通过。
- `compileall`、单一 Alembic head `b6d8f0a2c4e6`、`git diff --check` 全部通过。
- 受影响历史/报告/生命周期链：**143 passed**。
