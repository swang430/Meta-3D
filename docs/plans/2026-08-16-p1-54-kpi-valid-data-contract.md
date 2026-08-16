# P1-54 吞吐 KPI 有效性正式数据契约实施计划

> 设计依据：`docs/plans/2026-08-16-p1-54-kpi-valid-data-contract-design.md`

## Task 1：共享契约与驱动生产者

1. 在 `api-service/tests/test_p1_54_kpi_valid_contract.py` 写 RED：
   - `ThroughputMetrics()` 的吞吐字段为 None，`to_dict()` 携带显式 false；
   - 显式真实零值保持 0.0 且 valid；
   - UXM NaN 与 CMW500 坏响应不再返回默认 0.0；
   - 两个真实驱动成功解析时 valid=True。
2. 运行定点测试确认因契约尚不存在而失败。
3. 修改 `base_station.py`、UXM、CMW500；同步 nullable 日志格式与 Mock 构造。
4. 运行定点测试至 GREEN。

## Task 2：MEASURE 正式样本门

1. 写 RED：无效默认零不进入方位平均；真实有效零仍进入；phase 写
   `throughput_verified`，无有效样本的 milestone 为 unknown。
2. 修改 `measure.py`，只收显式有效样本并持久化逐方位/phase 有效性。
3. 运行定点与 MEASURE 相关回归至 GREEN。

## Task 3：ANALYSIS / 报告消费

1. 写 RED：缺少或 false 的 `throughput_verified` 使 ANALYSIS 输出 UNKNOWN；显式 true
   的健康数据保持既有 PASS/FAIL；报告缺测为 N/A 且不进统计。
2. 修改 `analysis.py`，将吞吐可信度加入正式 allowlist；报告生成写独立吞吐 trust marker，
   列表/详情/下载要求路损与吞吐两枚 marker，旧报告走 P2-26 安全重建。
3. 运行 analysis/report/commissioning 回归至 GREEN。

## Task 4：镜像、全量验证与交付

1. 更新 roadmap 的 P1-54 状态与 P1-55/P1-56 已确认定义；移除已完成 P2-26 的 stale focus。
2. 运行 P1-54、UXM/CMW500、MIMO measure/analysis/report 相关回归。
3. 运行完整 rule gates、后端全量、GUI production build（若 GUI 契约有改动）、compileall、
   Alembic head（若无迁移仅确认未新增）与 `git diff --check`。
4. fresh 内审到 P1=0；提交、推送、开 Ready PR，按既定 Codex 外审流程闭环并合并。
