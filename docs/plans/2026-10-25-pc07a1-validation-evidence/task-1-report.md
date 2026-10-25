# Task 1 报告

## 范围与输入

- 基准：`0b6d1f02485bf818bfdfff6b7eedc2c86638bfaa`，分支 `codex/pc-07a1-calibration-traceability`。
- 修：新增共享纯函数 `api-service/app/services/mimo_ota/calibration_traceability.py`。
- 修：新增生产 fixture 驱动的 `api-service/tests/test_pc07a1_calibration_traceability.py`。
- 未改 `api-service/app/api/test_execution.py`：见下方实际复现限制。
- 不改补偿算术、硬件/SCPI、现行资格门、当前配置或历史持久化。
- 测试输入 SHA256：helper `fe4e930bd610b503a0e3687e49619418f2e7349dd33a5974eda4641105d4a914`；测试 `b82066b767cf0e4faf7a3e8f59bd415666c5476ba5681ed9258cc12d4ed36ddb`。

## 契约与全集核对

生产冻结入口 `launch_test_case_execution` → `route_calibration_freeze` → `evaluate_path_loss_preflight` / `parse_path_loss_application` → 新投影。

正式消费者枚举：`executors/analysis.py` 和 `executors/report.py` 已读 `path_loss_measurement_is_verified`；`api/test_execution.py::_formal_validation_pass` 仍读旧镜像字段与应用可信门，但此前先经过静区正式门。

投影结构：顶层 `schema_version/status/provenance/reason/gate_mode/certificate_id/execution_frequency_mhz/routes/raw_readings_embedded`；逐链 `application_state` 区分 selected/applied/unknown，精确 `(source_kind, source_id)` 唯一匹配后才携带 `source_snapshot`。未匹配诊断来源不会成为 routes。有效快照原字段原值保留，损坏历史仅留定位标识，不猜来源。raw 只有 run/indices 指针，未查询 DiagnosticRun，未内嵌原始读数；采用不等于认证。顶层应用状态来自 parser，不覆盖逐链关联结论；原 parser 接受来源重复项时，该链仍为 unknown，消费者不可用顶层 applied 将它提升。

## RED / GREEN 证据

所有命令工作目录均为本工作树 `api-service`。运行前 `mktemp -d /tmp/pc07a1-task1-<阶段>.XXXXXX`，显式 `USE_MOCK_INSTRUMENTS=true DATABASE_URL="sqlite:///$task_tmp/bootstrap.db"`，未关默认 bootstrap，输出重定向独立目录 `result.log`；应用自身日志仍由原 conftest 隔离。

1. RED：`.venv/bin/python -m pytest tests/test_pc07a1_calibration_traceability.py -q`
   - 退出码 1；`13 failed, 152 warnings in 21.22s`。
   - 日志 `/tmp/pc07a1-task1-red.kmPIVT/result.log`。
   - 原因均为函数所在生产模块尚不存在，非采集失败或真实仪器连接；fixture 已走真实确认、冻结、parser 链。
2. 首次 GREEN 尝试：同命令。
   - 退出码 1；`1 failed, 12 passed, 152 warnings in 21.40s`。
   - 日志 `/tmp/pc07a1-task1-green.jeZEXV/result.log`。
   - 唯一失败是测试构造重复旧证书，却断言新采用链为 unknown；已按第一 route 的 `(kind,id)` 精确复制匹配项修正测试输入，生产实现未改。
3. 相关回归（旧输入过程记录）：`.venv/bin/python -m pytest tests/test_pc07a1_calibration_traceability.py tests/test_pc04a2_route_freeze.py tests/test_pc04a2_route_compensation.py tests/test_p1_62_path_loss_application_truth.py -q`
   - 退出码 1；`1 failed, 85 passed, 702 warnings in 86.59s (0:01:26)`。
   - 日志 `/tmp/pc07a1-task1-regression.vLnShc/result.log`；该进程读取的是修正前重复来源测试输入，启动后又增加用例，不作为最终版本证明。
4. 最终 GREEN：同四文件命令，日志 `/tmp/pc07a1-task1-final.tPxSu0/result.log`。
   - 退出码 0；`91 passed, 772 warnings in 99.61s (0:01:39)`；其中新增文件21项。
   - 输入是上述基准 + 两个新增代码/测试文件（SHA256见前）；其他既有输入未改。最终运行期间未再改代码/测试，之后仅填写本报告，不影响该结果复用。

## v2 详情差异：未复现，因此不修

`quiet_zone_evidence.py::parse_quiet_zone_evidence` 当前仅接受 `formal_verified=False` 的 unavailable/diagnostic_proxy 状态；其权威 `quiet_zone_scope_is_formally_verified` 对当前合法证据不返回 True。故不能在不替换正式证据门的前提下构造“其他正式证据满足”的正例。

新增同次执行场景：真实 v2 已应用，去掉旧 `path_loss_calibration_use_mock`，合法静区证据经真实 AnalysisExecutor、详情 helper、report builder，分析/详情仍 UNKNOWN，报告校准可信为 True、静区可信为 False。此为未复现的原因记录，不把校准局部可信误称为正式 PASS。不 mock 静区门，不扩大正式资格，不补旧镜像。

## 自审与边界

- 主动枚举同 ID 不同 kind、未知 kind、缺少来源、重复来源、结构损坏、partial applied、诊断选择与 v1 缺损；缺损关联不宣称 applied。
- 保持冻结执行频率 2595 与旧证书覆盖频率 2500 分别展示；原采用 ID、predecessor、run/indices 和参考面均只来自冻结快照。
- 本任务执行者自审，非 fresh 独立内审；主代理安排独立审查与后端最终全量，未跑全后端、未 push、未释放主代理认领。
- `git diff --check` 退出码 0；原有 `.playwright-cli/`、`.venv`、`output/` 未动。

## 疑虑

静区正式正例当前不可表达；详情旧镜像差异仅是潜在分叉，按 brief 不在未复现时修改。后续静区正式证据契约落地时，应重新验证同次执行消费者一致性。
