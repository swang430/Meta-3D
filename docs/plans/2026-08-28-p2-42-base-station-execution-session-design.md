# P2-42 BaseStation 单一执行会话设计

## 可观察故障

CMW500 接入时，formal runner、commissioning saved phase、adhoc 和 run-all 四类入口分别
拼装了同一套 BaseStation 生命周期：冻结配置校验、取得 Remote、刷新 transport identity、创建
current attempt、绑定 lease/session、执行、cleanup、release、落终态。四份实现已经发生过顺序漂移；
现场还出现后台监控查询污染 CMW 会话、旧回复被当作新结果，以及无关 FSVA 监控影响 LTE 流程。
继续复制这套拼装会让第三种 BaseStation adapter 重复同样的集成成本和假成功风险。

## 全集

### 生命周期产生方

1. `test_case_runner._run_case`：正式 TestCase 全链。
2. `commissioning.run_phase`：已保存 session 的单相位执行。
3. `commissioning.run_adhoc_phase`：临时单相位执行。
4. `commissioning.run_all_phases`：commissioning 五相位链。

四处当前都直接消费 `instrument_test_lease`，并各自调用
`begin_execution_base_station_measurement()`、回绑 `measurement_attempt_id`、在退出后选择
`persist_execution_base_station_release()` 或 `record_execution_base_station_attempt_failure()`。

### 权威状态与消费方

- 冻结配置与 validator：`base_station_adapter_profile`；必须在协调锁内、Remote I/O 前复核。
- lease / transport identity：`instrument_test_lease`；唯一 server-owned `lease_id`，驱动返回
  `adapter_id/session_token`。
- attempt / release / KPI provenance：`execution_scpi_evidence` 与版本化
  `BaseStationExecutionEvidence`；正式 writer 只接受 current attempt + active lease + exact session。
- 监控门：`instrument_test_lease.is_test_monitoring_enabled()`；REST/WS 监控在门关闭时不得调用
  HAL 聚合指标。正式执行不得由入口自行决定是否打开监控。
- Analysis/Report：仍只在 release 已落库后运行；本片不改变逐指标正式白名单。

## 方案比较

### A. 新建应用层 `BaseStationExecutionSession`（采用）

新增一个小型应用服务，内部组合现有冻结 validator、通用仪表租约和 execution evidence helper。
入口只提供 execution、TestCase、step type、purpose 与实际业务协程。服务固定关闭冲突监控，并
唯一负责 acquire 后 begin attempt、业务退出后的 release 持久化，以及异常/取消的 attempt 终态。

优点：删除四份顺序拼装；不把 SQLAlchemy/evidence 语义塞进通用仪表租约；不改任何厂商命令；
第三种 adapter 复用同一入口。缺点：需要迁移现有入口测试的 patch 点。

### B. 把 execution/DB 语义直接塞进 `instrument_test_lease`（不采用）

代码行更少，但会让通用 F64、校准、诊断租约依赖 TestExecution、TestCase 和 MIMO OTA evidence，
破坏它当前作为 HAL 生命周期协调层的边界，也会让非 BaseStation 调用被迫携带无关参数。

### C. 给四个入口加 decorator（不采用）

表面改动小，但 decorator 难以表达 run-all 延迟 ANALYSIS→REPORT、同步 FastAPI 错误映射和业务
结果“返回失败但不抛异常”的语义，生命周期仍会从隐藏回调泄漏到入口。

## 采用的状态机

`run_base_station_execution_session()` 按以下唯一顺序运行：

1. 接受调用方已冻结的 validator；由 `instrument_test_lease` 在协调锁内复核，并固定
   `enable_monitoring=False`。
2. 取得 BaseStation Remote 并刷新真实 `adapter_id/session_token`；acquire 未确认时不创建 attempt。
3. 仅 MEASURE 创建 current attempt，并把 attempt 回绑到本次 server-owned lease outcome。
4. 执行调用方提供的业务协程。业务只返回“值 + 是否成功”，不触碰 lease/attempt/release helper。
5. 无论成功、返回失败、抛异常或取消，先由租约完成 cleanup/release；随后用同一
   attempt/lease/session 落 release 与终态。
6. 业务成功但 attempt 未达到完整 lifecycle 时 fail-loud，禁止继续正式 Analysis/Report；业务返回
   failed 则落 failed 但保留原业务结果给入口现有响应映射。

异常和 release 同时失败时，沿用 `instrument_test_lease` 的保守聚合错误；入口只负责把该统一错误
映射到自身 HTTP/执行行状态，不再重复写 attempt。

## 监控隔离

- 正式 BaseStation execution session 内部硬编码关闭监控，API 入口不再传
  `enable_monitoring`。
- REST/WS 监控继续只读全局租约门；门关闭时不触发 `get_aggregated_metrics()`。
- evidence writer 继续要求 active lease 的 current attempt、adapter 与 session token 精确一致；会话外
  的缓存或晚到回复不能写入 current attempt。
- 本片不新增独立监控 transport，也不重写各厂商 `get_metrics()`；那会扩大命令与连接语义范围。

## 范围与验收

只新增应用层会话服务并迁移四类入口，配套修改相关测试和 roadmap。不得修改 UXM/CMW/F64/FSVA
命令，不改变 adapter SPI、binding resolver、Diagnostic/Formal 模式或正式 provenance 白名单；这些
分别留在 P2-43～45。

验收：四类入口不再直接拥有 BaseStation attempt/lease/release 拼装；成功、返回失败、异常、取消、
acquire 失败和 release 失败由同一状态机落证据；正式化发生在 release 落库之后；监控开关只有会话
服务一处决定。现有 116 项相关基线、扩展状态机测试、全后端与规则门必须通过。
