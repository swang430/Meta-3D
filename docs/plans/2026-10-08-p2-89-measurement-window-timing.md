# P2-89 测量时间与窗口配置收敛

用户已批准 P2-88→P2-89→P2-90 连续开发；前片 PR #514 已合并为 `11441ee9`。本片 WIP=1，不新增仪器命令、不解除现场阻塞、不修改正式 provenance 判据。

## 事实与边界

- 配置 `num_samples_per_azimuth` 目前默认 100，MEASURE 却用 `_DEV_SAMPLE_WINDOWS=3` 隐式截断；共同 `_measurement_window_requests` 已按冻结 manifest 区分 single/requested。去掉截断，复用该计划，不另造厂商分支。
- 新建配置窗口请求默认 3；历史显式 100 保留 100，不猜操作员意图。正整数范围与 GUI 一致为 1..10000。CMW single 仍计划 1，UXM requested 按请求数量；请求、计划、实际分列。
- `measurement_duration_s` / `sample_interval_ms` 不驱动本次测量，撤下有效控件，保留兼容字段并明确未生效；转台 settling 独立。
- 统计长度只读同次冻结 MAC `statistical_window.count`。既有 SPI 的等待参数不升级为实测时间，日志不得把其描述成真实窗口时长。
- 预计总时间目前在 factory/commissioning 使用未生效 duration 拼出，必须去掉伪精确结果。只能给出已知 settling 小计与窗口计划/统计长度；仪器测量、attach、移动、初始化、清理时间未知时总预计时间保持 null。实际耗时沿用执行/窗口 timestamps，不从计数回填。
- 报告沿用 P2-88 同执行冻结投影，历史不重新补默认；GUI 消费服务器 schema，不创建另一份默认或适配器规则。

## 手册查证

NotebookLM CMW 查询 `b9b6fb5a799c`：LTE Signaling User Manual `1173.9628.02-41` §3.2.4 pp.937–938，No. of Subframes 定义每周期处理计数，single-shot covers one measurement cycle；§3.4.3 p.953 定义 subframes (= number of transport blocks)。这些定义不是整个执行的墙钟承诺；不采纳问答工具对调度延时的额外推断。

NotebookLM UXM 查询 `7acccd83606c`：`UXM5G_SCPI_02_NR_PHY_Measurements.md` 的 NR BLER/Tput / DL Retransmit / BLER/Tput，原文“Specifies the BLER/Throughput measurement count”，Unit 未注明。未取得 count/1000 秒的手册依据，不据其承诺预计墙钟时间，也不将其他 NR 方言完成规则移植到当前 IRAT adapter。

## 全集与实施顺序

1. Schema 默认/边界、canonical 保存/冻结；GUI 四个测量控件、OpenAPI/YAML/generated TS/手写类型。
2. MEASURE 请求→共同窗口计划→真实/Mock SPI→sampling 日志与结果；去掉生产截断，数量不同必须体现。取消、失败与缺失证据不冒充完成窗口。
3. factory 的 TestCase convenience 时长、commissioning Session config_view、报告参数展示与 TestCaseLibrary 时长展示。旧数据只解释，不重写历史记录。
4. 每步严格 RED→GREEN；受影响链与 GUI 契约/build；稳定最终后端全量一次、compileall、单一 Alembic head、diff-check。
5. fresh 只读功能内审、Ready PR、最新 SHA 的 Codex R1→R2；R2 无 P1 合并/main 同步清理后进入 P2-90。

## 台账

- 基线（api-service）：`.venv/bin/python -m pytest tests/test_p2_88_report_traceability.py tests/test_commissioning_adhoc.py tests/test_p2_48_measurement_window_plan.py tests/test_p1_73a_vendor_neutral_measure.py -q -o log_cli=false -o addopts='' --tb=short --disable-warnings` → 76 passed /185 warnings，94.46s。
- 当前已完成设计枚举与手册查证；尚未声称实现或交付。
