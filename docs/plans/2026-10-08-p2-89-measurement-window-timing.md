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
- Schema RED 8 failed/2 passed；GREEN 新建默认3、历史显式100不改、窗口strict1..10000、settling有限非负，联合 MAC schema 60 passed。
- 生产 MEASURE 同次冻结入口 RED：请求5却传3（1 failed/1 passed）；删除隐式cap后同一生产入口2 passed，19.71s。未替换统计计数、不改 native single/requested 规则或 SCPI。
- factory RED：未生效duration=999生成4004秒；报告 RED：历史字段无生效说明。GREEN 总预计null、历史字段明确不控制测量。报告旧窗口fixture改为显式100，证明历史值保留而不是跟新建默认漂移。
- GUI无效控件及历史MIMO卡片先RED；GREEN只屏蔽MIMO旧伪预计，非MIMO/历史DB不改。请求数不另设客户端默认；统计窗口等待参数不冒充实际墙钟时间。
- OpenAPI核验：MIMO配置在现有API中是自由configuration对象，不是独立OpenAPI component；不为同步镜像新造路由。现有CreateSessionRequest旧duration标deprecated，checked YAML/generated TS及手写GUI兼容注释同步。
- 受影响链命令（api-service）：`.venv/bin/python -m pytest tests/test_p2_89_measurement_timing.py tests/test_p2_88_report_traceability.py tests/test_p2_48_measurement_window_plan.py tests/test_rule_gates.py tests/test_commissioning_adhoc.py -q -o log_cli=false -o addopts='' --tb=short --show-capture=no --disable-warnings` → exit0，148 passed/213 warnings，97.90s。
- GUI：`node --experimental-strip-types --test test/measurementTiming.test.ts test/baseStationCompatibilityReadiness.test.ts test/reportRecovery.test.ts test/reportLifecycleTruth.test.ts src/components/TestCaseConfig/lteTddMacAuthoringTruth.test.ts src/types/executionEvidenceOutcome.test.ts` → exit0，18 passed，97.65ms；`npm run build` → exit0，11.76s，既有chunk/import警告。
- 独立只读功能内审P1=0，发现历史MIMO伪预计P2，最小修复后增量/同根复核P1/P2/P3=0。reviewer不重复全量。
- compileall、diff-check exit0；Alembic单head `c1e3f5a7b9d2`。
- 最终全量（api-service）：`.venv/bin/python -m pytest -q --color=no -o log_cli=false -o addopts='' --tb=short --show-capture=no --disable-warnings` → exit0，7001 passed/17 skipped/5376 warnings，267.06s。单人单次稳定实现全量；tracked生产/测试diff SHA256 `cd43f2024c204b45d6831466a08b43723be5680cfc0aefede452e6c0bb0c3092`、新增测试git blob `8d483fa874e3a345405cb13edd52deff352b9088` 结束核对不变。后续只填非测试输入的台账，不重复相同输入全量。
