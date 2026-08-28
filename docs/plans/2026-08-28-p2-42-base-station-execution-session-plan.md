# P2-42 BaseStation 单一执行会话实施计划

> 按 `executing-plans` 与严格 TDD 执行；每一任务先确认 RED，再写最小 GREEN。不得改动厂商命令、adapter SPI、正式 KPI provenance 白名单或 P2-43～45 范围。

**目标：** 用唯一应用层 BaseStation execution session 取代 formal runner、commissioning saved phase、adhoc、run-all 四处重复的 acquire/attempt/cleanup/release 拼装，并在整个会话期间隔离后台监控。

**结构：** 新服务组合现有 `instrument_test_lease`、`base_station_adapter_profile` validator 与 `execution_scpi_evidence` helper。入口只保留阶段选择、业务操作及自身错误响应映射；证据与终态始终由会话服务在真实 release 之后落库。

**技术栈：** Python 3.11、FastAPI、SQLAlchemy、Pydantic v2、pytest/pytest-asyncio。

---

## Task 1：锁定统一状态机契约

**文件：**
- 新建：`api-service/tests/test_p2_42_base_station_execution_session.py`
- 新建：`api-service/app/services/base_station_execution_session.py`

1. 写 RED，覆盖 Remote acquire 先于 attempt、server-owned lease/session 回绑、业务成功后 release 落库、返回失败、异常、取消、acquire 失败、release 失败。
2. 写 RED，证明服务内部固定 `enable_monitoring=False`，调用方无覆盖入口。
3. 运行新测试，记录模块/行为缺失的预期失败。
4. 最小实现 result envelope、session error 与 `run_base_station_execution_session()`。
5. 运行新测试到 GREEN；复跑 execution evidence 与 lease 定点集。

## Task 2：收口不完整生命周期的假成功

**文件：**
- 修改：`api-service/app/services/base_station_execution_session.py`
- 修改：`api-service/tests/test_p2_42_base_station_execution_session.py`
- 视需要修改：`api-service/app/services/execution_scpi_evidence.py`

1. 写 RED：业务返回成功但 current attempt 未达到完整 config/window/cleanup/release 时必须 fail-loud，且不得继续正式化。
2. 写 RED：旧 attempt、错 lease/session 的 release 不能完成 current attempt；重复落终态不得覆盖首个失败。
3. 最小 GREEN，优先读取现有版本化 evidence 真值，不复制状态枚举。
4. 回归 `test_p1_73c_measurement_attempt_lifecycle.py`、`test_p1_73c_base_station_control_release.py`。

## Task 3：迁移 formal runner

**文件：**
- 修改：`api-service/app/services/test_case_runner.py`
- 修改：`api-service/tests/test_instrument_test_lease.py`
- 修改：`api-service/tests/test_p1_56_positioner_motion_truth.py`
- 视需要修改正式 runner 相关测试。

1. 写/调整 RED：MEASURE 只调用统一 session 一次；PRECHECK/ANALYSIS/REPORT 不创建空 attempt；Analysis/Report 只能在已确认 release 之后运行。
2. 最小迁移，删除 runner 自有 begin/persist/failure 拼装及监控开关。
3. 覆盖业务失败、异常、取消、取得/释放控制失败，保持现有 TestExecution 状态与错误文本契约。
4. 运行 runner、lease、positioner 与 evidence 相关集到 GREEN。

## Task 4：迁移 commissioning 三类入口

**文件：**
- 修改：`api-service/app/api/commissioning.py`
- 修改：`api-service/tests/test_commissioning_adhoc.py`
- 修改：`api-service/tests/test_commissioning_smoke.py`
- 修改：`api-service/tests/test_commissioning_device_selfcheck.py`

1. 分别写 RED：saved phase、adhoc、run-all 的 MEASURE 使用同一 session；ANALYSIS/REPORT 不新建空 lease。
2. 写 RED：run-all 仅在 MEASURE release/terminal evidence 落库后进入 ANALYSIS→REPORT。
3. 最小迁移并删除三处直接 lease/attempt/release helper 调用。
4. 覆盖成功、返回失败、异常、取消、acquire/release 失败到 GREEN。

## Task 5：监控隔离与入口全集回归

**文件：**
- 修改：`api-service/tests/test_p2_42_base_station_execution_session.py`
- 视需要修改：`api-service/tests/test_instrument_test_lease.py`
- 视需要修改：`api-service/tests/test_p1_47c_execution_scpi_evidence.py`

1. 写 RED：会话活动期间 REST/WS 监控门关闭，不调用 HAL 聚合指标；退出后恢复。
2. 写 RED：会话外缓存、晚到回复、错 attempt/lease/session 不能写入 current attempt。
3. 最小 GREEN 只复用既有监控门与 evidence writer，不新增 transport 或厂商查询。
4. 用 `rg` 复核四类入口不再直接拥有 BaseStation 生命周期拼装，并记录每个旧站点的处置。

## Task 6：文档、完整验证与交付

**文件：**
- 修改：`docs/roadmap-first-call.md`
- 视结果修改：本设计/计划文档的实施结果段。

1. 更新 P2-42 状态、验证统计与明确保留的 P2-43～45/现场项，不改历史记录。
2. 运行相关回归、规则门、全后端、compileall、单一 Alembic head、diff-check。
3. 做 fresh 独立功能内审，按 P1/P2/P3 分栏；测试类发现最高 P2。
4. P1=0 后提交、推送、开 Ready PR，执行 Codex R1→R2；覆盖最新 HEAD 的 R2 无 P1才 merge。
5. fetch 验证 `origin/main`，主目录 fast-forward，同步后清理 worktree/本地分支；保留未跟踪仪器资料。
