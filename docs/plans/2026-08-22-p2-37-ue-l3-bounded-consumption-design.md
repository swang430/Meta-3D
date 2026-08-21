# P2-37：UE L3 报告队列有界消费设计

## 可观察故障

真实 UXM 处于 `CONNECTED` 时，后台 `RealUxmDriver.get_metrics()` 每轮都会调用
`get_throughput_metrics()`。后者对
`BSE:CONFig:NR5G:{cell}:MEASurement:JSON:REPort:FETCh?` 不带数量参数；厂商手册明确说明
省略数量时返回全部可用报告，却没有说明读取会消费队列。结果是后台监控运行越久，单次 SCPI
响应、JSON 解析和 SCPI 日志越大。

这批 L3 值的单位/码点尚未获手册或现场确认，当前只进入
`kpi_raw_unverified` 证据，不进入 `rsrp_dbm`、`sinr_db`、正式 KPI 或 Dashboard 展示。

## 现状全集

### 命令与产生方

- `UxmLteNrIratProfile.MEAS_UE_REPORT_STATE`：开启全局 UE report 队列；
- `UxmLteNrIratProfile.MEAS_UE_REPORT_CLEAR`：已有手册出处的全局立即动作，无查询形式；
- `UxmLteNrIratProfile.MEAS_UE_REPORT_JSON`：不带数量参数的全量 `FETCh?`；
- `RealUxmDriver._enable_kpi_measurements()`：开启队列；
- `RealUxmDriver.get_throughput_metrics()`：唯一生产代码读取点；
- `uxm_kpi_readback`：独立诊断序列，已有 clear → 明确窗口 → fetch 的完整证据链。

### 消费方

- `RealUxmDriver.get_metrics()`：后台监控入口；L3 原始值没有进入返回的监控指标；
- `RealUxmDriver.measure_throughput_window()`：正式 MIMO OTA 逐方位吞吐窗口；
- `measure.py`：只通过 `measure_throughput_window()` 消费真实 UXM；
- `measurement.log`：保存 `kpi_raw_unverified`，但不把原始 L3 值解释成工程单位；
- `uxm_kpi_readback`：人工诊断证据，不复用后台监控路径。

## 方案比较

### A. 后台停止读取 L3；正式窗口显式 clear（采用）

给 `get_throughput_metrics()` 增加只控制 L3 原始证据读取的内部关键字参数。后台
`get_metrics()` 关闭该读取；正式 `measure_throughput_window()` 在窗口开始同时清吞吐计数器和
UE report 队列，只有 clear 获得可信成功证据时才在窗口末读取 L3。

优点：删除没有产品消费方的后台无界读取；正式证据窗口仍保留；不增加跨轮状态；不改变正式
吞吐、BLER、CQI、RI。缺点：Dashboard 后台不再周期生成 L3 原始日志，但这些原始值当前本就
不展示也不参与判定。

### B. 后台维护跨轮 clear/fetch 状态机

首轮 clear 并跳过，下一轮 fetch 后再次 clear。能保留后台原始 L3 日志，但需要跨轮状态、
断连复位、并发与失败恢复，且没有活动产品消费方支撑这份复杂度。

### C. 改成 `FETCh? 1`

拒绝。手册未说明带数量时取最新还是最旧，也未说明读取后是否移除；实现会把未知顺序猜成
时间真值。

## 采用设计

1. `get_throughput_metrics()` 默认仍读取 L3，保持显式正式调用与既有测试兼容；新增内部关键字
   只允许调用方跳过 L3 查询，不改变其他 KPI。
2. 后台 `get_metrics()` 在 `CONNECTED` 时读取吞吐、BLER、CQI、RI，但显式跳过 L3
   `FETCh?`。非连接态继续零 KPI I/O。
3. `measure_throughput_window()` 在 sleep 前建立两个并列窗口：
   - `MEAS_BTHROUGHPUT_CLEAR` 定义吞吐窗口；
   - `MEAS_UE_REPORT_CLEAR` 定义 L3 报告窗口。
4. L3 clear 采用 fail-closed：命令缺失、写异常、基线错误队列不可用或写后出现新错误时，
   本轮不发 L3 `FETCh?`，但其他 KPI 照常读取。不得把“命令已发送”当成“clear 已生效”。
5. 诊断序列继续使用自己的 clear/window/fetch/restore 证据链，不改成共享隐式状态。
6. L3 数值仍只进入 `kpi_raw_unverified`；`rsrp_dbm`、`sinr_db`、`kpi_valid` 与正式报告语义
   不放宽。

## 失败与安全语义

- clear 失败却继续 fetch：可能重新读取开测以来的完整队列，故必须禁止；
- clear 失败而跳过 L3：只损失一轮尚未进入正式 KPI 的原始证据，代价更轻；
- 吞吐 clear 失败：保持现有明确 warning 与累积值语义，本片不扩张；
- L3 fetch 自身失败：保留现有 warning、`valid=false` 与其他 KPI 结果；
- 不新增 SCPI 字面量，不改变任何仪器参数或现场硬件开关。

## TDD 与验收

先写会红的行为测试：

1. connected 后台 `get_metrics()` 不发送 L3 `FETCh?`，仍读取其他 KPI；
2. 正式窗口中 L3 clear 严格早于 sleep/第一条 KPI 查询和 L3 fetch；
3. clear 命令缺失、写异常、写后错误队列非空时均不 fetch L3；
4. clear 成功时正式窗口仍保留原始 L3 证据，且不进入工程单位字段；
5. 诊断序列现有 bounded-window 契约保持全绿。

回归范围：`test_uxm_kpi_readback.py`、`test_uxm_kpi_readback_sequence.py`、MIMO OTA measure
相关测试、完整 rule gates、全后端、`compileall` 与 `git diff --check`。fresh 内审按
AGENTS.md 逐项复核命令产生/消费全集、错误队列归属和模拟/真实对称性。

## 非目标

- 不确认或换算 RSRP/RSRQ/SINR 单位；
- 不把 L3 原始值接入 Dashboard、KPI、Analysis 或报告；
- 不新增或猜测带数量参数的 SCPI；
- 不改 CMW500、Mock 或独立诊断序列的语义；
- 不处理 P2-40 的清理候选。
