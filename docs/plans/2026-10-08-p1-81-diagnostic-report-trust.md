# P1-81：诊断报告空指标镜像与可信性门一致

## 已批准方案与边界

用户 2026-10-08 批准将诊断中发现的报告故障加入 roadmap、排序并开 PR 修复。采用收窄 writer，不放宽可信性校验：缺席注册指标的兼容镜像保持原来的 unknown/null；已注册指标仍按诊断资格禁止 formal_value。无 SCPI、仪器值域或单位语义改动，NotebookLM 不适用。memory 查询仅作历史边界参考，当前依据为 main `3673470b`、本地只读数据库和日志。

## 四行契约与全集

- 输入：同次 execution 的冻结证据、权威 metric registry、生命周期；不读当前 TestCase/LabProfile。
- 输出：PDF/content_data 的通用 metrics 与吞吐/BLER兼容镜像满足既有可信性门；诊断数据不进入正式 KPI。
- 失败：畸形指标、镜像分叉、attestation/digest 篡改仍拒绝；不能通过取消读门恢复访问。
- 非目标：不修改 Mock 驱动、注册表、正式资格、报告状态机、失败执行筛选或批量改生产数据。

产生方：`mimo_ota/executors/report.py::_build_mimo_ota_content_data`。共同投影来自 BaseStation execution evidence。
消费方：`report_service.py::report_has_provenance_trust` / `_base_station_projection_is_sanitized`，API `report.py` 的 generate、详情、下载、列表恢复状态；PDFGenerator；自动 REPORT executor 与公开手动重建均复用 writer。
对称路径：实际注册/缺席指标，吞吐/BLER镜像，formal/diagnostic/invalid/legacy，自动生成/公开重建。仪器方言、CE 三管线、硬件写操作不变。

## 实施与验收顺序

1. 用真实 writer 构造 CQI/RI-only 诊断执行；先证明 writer 输出被既有可信性门拒绝（RED），并测试自动/公开报告可读路径。
2. 最小 GREEN：只对注册指标作诊断降级，缺席镜像保留共同投影 unknown/null；同一输出计算 attestation。
3. 回归实际吞吐/BLER诊断、正式与伪造镜像；旧失败报告经正常重建可恢复，不自动篡改数据库或绕过下载门。
4. 共享报告证据档：受影响链与 rule gates，稳定输入一次后端全量、compileall、diff-check。未改 GUI/API schema，四镜像和 production build 不适用。
5. 提交前审查后 push/Ready PR，核实实际 HEAD 再请求一次 Codex R1；R1 本片功能 P1/P2 收口后 R2。当前用户仅要求开 PR，本片不未经请求自动合并。

## 验证记录

测试基准：main `3673470b`；输入为本片 writer diff 与新增 `test_p1_81_diagnostic_report_trust.py`，依赖复用主目录 `.venv`（不提交链接）。下述无关 roadmap/计划记账不参与测试输入。

- 基线：`cd api-service && .venv/bin/python -m pytest -q tests/test_p2_49_metric_registry_consumers.py tests/test_p2_45_diagnostic_formal_consumers.py --color=no`，exit 0，`14 passed, 40 warnings in 0.06s`。
- RED：`.venv/bin/python -m pytest -q tests/test_p1_81_diagnostic_report_trust.py --color=no -o log_cli=false --show-capture=no --tb=short`，exit 1，`4 failed, 1 passed, 44 warnings in 0.16s`。三项真实 writer 内容未通过 trust；一项 SQLite + 真实 PDF + 公开 generate API 在落盘后被 409 拒绝。此 RED 已证明核心修复回退可检出，无需为审查身份再跑相同变异。
- GREEN：同命令，exit 0，`5 passed, 44 warnings in 0.10s`。涵盖两镜像各自缺席、全部缺席、全部注册，以及公开重建/详情/下载/恢复状态；伪造缺席镜像后重算 attestation 仍拒绝。
- 受影响链：`.venv/bin/python -m pytest -q tests/test_p1_81_diagnostic_report_trust.py tests/test_p2_49_metric_registry_consumers.py tests/test_p2_45_diagnostic_formal_consumers.py tests/test_p1_73c_formal_consumers.py tests/test_mimo_ota_report_verified_backcompat.py tests/test_p2_66_api_projection.py tests/test_p2_66_formal_consumers.py tests/test_p1_48_report_provenance.py tests/test_p1_61_report_final_state_truth.py tests/test_p2_88_report_traceability.py tests/test_rule_gates.py --color=no -o log_cli=false --show-capture=no --tb=short`，exit 0，`244 passed, 123 warnings in 5.53s`。
- 真实历史只读回放：SessionLocal 执行 `SET TRANSACTION READ ONLY`，查询 `TestReport.generated_at >= 2026-10-06` 的 12 份报告；5 份旧内容不通过 BaseStation projection trust。逐份读取关联 TestExecution，调用新 `_build_mimo_ota_content_data`，5 份新内容均 `report_has_provenance_trust=True` 且 `formal_eligible=False`。无生产写入、无历史 PDF 替换。
- `.venv/bin/python -m compileall -q app` 与 `git diff --check` exit 0；`.venv/bin/alembic heads` exit 0，单一 head `c1e3f5a7b9d2`。
- 后端全量：`.venv/bin/python -m pytest -q --color=no -o log_cli=false --show-capture=no --tb=short`，exit 0，`7028 passed, 17 skipped, 5397 warnings in 269.50s (0:04:29)`。本片稳定输入一次全量，不为审查身份重复执行。
- 独立只读内审：CLEAN，功能与测试发现均无；核实 writer/validator 对称关系，并独立复算真实 12/5 分布与 5 份只读恢复结果。复用上述 RED/GREEN 和相关链；全量由主代理唯一执行。

外审请求与轮次台账留在本片 PR 的 Review tracking；不为更新外审状态另加待审提交。
