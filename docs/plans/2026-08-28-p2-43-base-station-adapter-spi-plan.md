# P2-43 BaseStation Adapter SPI 实施计划

> 依据 `docs/plans/2026-08-28-p2-43-base-station-adapter-spi-design.md` 执行。严格 TDD；每个任务先运行 RED 并确认失败原因，再做最小 GREEN。不得新增或修改 SCPI 字面量。

## Task 1：冻结共同回执不变量

**文件**

- 修改：`api-service/app/hal/base_station.py`
- 修改：`api-service/tests/test_p1_73a_base_station_contract.py`
- 新增：`api-service/tests/test_p2_43_base_station_receipts.py`

**RED**

1. 为 `BaseStationFieldReceipt` 写参数化测试：confirmed 必须 requested/applied 精确一致；unknown 的 applied 必须为空；not_applicable 不得伪装失败读取。
2. 为 `BaseStationApplyReceipt` 写测试：总 confirmed 只能由全部适用字段确认派生；exchange id 必须非空、唯一且等于字段证据并集。
3. 把 adapter/session/release 的 adapter id 合同从两值 Literal 收窄为非空稳定字符串，同时保留 registry 负责是否已注册。
4. 运行新测试，确认因共同类型缺失而失败。

**GREEN**

1. 在共同 HAL 实现不可变字段回执与 apply 回执，不允许调用方直接传入总 confirmed。
2. 给 `BaseStationDriver` 增加稳定 `apply_config()`、`apply_route()` 合同；默认 route 只返回真正的 not_applicable，不借请求值伪造 applied。
3. 旧 `apply_requested_config()` 作为兼容壳，从 `apply_config().confirmed` 派生。
4. 运行新测试和 `test_p1_73a_base_station_contract.py`。

**提交**：`feat: define base station adapter receipts`

## Task 2：CMW500 配置与 route 产生共同回执

**文件**

- 修改：`api-service/app/hal/cmw500_base_station.py`
- 修改：`api-service/tests/test_p1_73b_cmw_route_truth.py`
- 修改：`api-service/tests/test_p1_73b_cmw_state_machine.py`
- 新增：`api-service/tests/test_p2_43_cmw_adapter_receipts.py`

**RED**

1. 证明七字段 route 全部精确回读时，每个字段 individually confirmed；专用查询失败但六路径成功时，六字段可保留诊断 applied，PCC 为 unknown，总结果不确认。
2. 证明配置回读部分缺失/异常/不匹配时，只保留已证明字段，未知字段 applied 为空，总结果不确认；不得从请求值或旧缓存回填。
3. 证明错误队列、超时、异常、取消仍 fail-closed，且 SAFE_IDLE/cleanup 语义不变。

**GREEN**

1. 将 CMW 专属 `BaseStationRouteResult` 替换为共同 apply receipt；复用现有七字段与六路径双回读、现有手册出处和 exchange capture。
2. 将现有 `set_cell_config()` 的校验/写入/回读主体抽成结构化配置结果；布尔兼容入口只读总 confirmed。
3. 不新增任何查询，不改变命令顺序或错误队列边界。
4. 运行 CMW route/state/config/窗口相关回归。

**提交**：`refactor: return CMW adapter receipts`

## Task 3：UXM 配置与 route 产生共同回执

**文件**

- 修改：`api-service/app/hal/uxm_base_station.py`
- 新增：`api-service/tests/test_p2_43_uxm_adapter_receipts.py`
- 修改：与 UXM config readback 直接相关的既有测试文件（以 `rg _readback_verify` 结果为准）

**RED**

1. 证明现有 profile 明确支持且权威回读一致的字段 individually confirmed。
2. 证明 profile 不支持读、查询异常或部分回读的字段为 unknown，而不是用缓存/请求值确认。
3. 证明错误队列拒绝、APPLY 后状态未生效、取消/异常不产生确认回执。
4. 证明 UXM route 返回 not_applicable，不能带 applied route。

**GREEN**

1. 让现有 UXM 校验、写入、错误队列和 `_readback_verify` 同时产出字段级回读结果；不新增 SCPI。
2. 旧布尔路径只由共同回执派生，不改变厂商内部安全恢复。
3. 运行 UXM config/state/session 相关回归。

**提交**：`refactor: return UXM adapter receipts`

## Task 4：共享 evidence writer 只消费共同类型

**文件**

- 修改：`api-service/app/services/execution_scpi_evidence.py`
- 修改：`api-service/app/services/mimo_ota/base_station_execution_evidence.py`
- 修改：`api-service/tests/test_p1_73c_base_station_window_writer.py`
- 新增：`api-service/tests/test_p2_43_base_station_adapter_evidence.py`

**RED**

1. 证明 writer 不接受自由 `config_confirmed` 布尔值，只接受 versioned config/route receipts。
2. 证明 requested digest 不一致、部分 unknown、重复/空 exchange id、wrong attempt/lease/session 均拒绝或保持不确认。
3. 证明 UXM/CMW 使用同一 receipt 输入形状；writer 不导入厂商模块。
4. 证明 simulated receipt 可审计但 formal metric trust 仍为 UNKNOWN/N/A。

**GREEN**

1. 增加版本化 adapter operation evidence schema；从共同 receipt 构造并绑定 execution-frozen digest。
2. `confirm_base_station_configuration_and_route()` 改为共同 config/route receipt 入口，删除 CMW 专属 import 与类型判断。
3. 保持公开 metric projection、报告与历史数据形状不变；旧 evidence schema 仍严格读取，不做黑名单式放行。
4. 运行 evidence/trust/formal consumer 相关回归。

**提交**：`refactor: persist vendor neutral adapter evidence`

## Task 5：MEASURE 与 commissioning 只调用稳定 SPI

**文件**

- 修改：`api-service/app/services/mimo_ota/executors/measure.py`
- 修改：`api-service/app/services/execution_scpi_evidence.py`
- 修改：必要的 P2-42 session orchestration 文件（仅替换 operation 回调，不复制生命周期）
- 新增：`api-service/tests/test_p2_43_base_station_adapter_certification.py`

**RED**

1. 参数化 UXM/CMW fake adapter，运行同一 certification suite：prewrite validation、error queue、partial readback、timeout/cancel、safe cleanup、attempt isolation、simulated exclusion。
2. 证明 MEASURE 不按 adapter 选择窗口；统一调用 `measure_base_station_window()`。
3. 证明 formal runner、saved phase、adhoc、run-all 无需知道 receipt 的厂商来源。

**GREEN**

1. 删除 MEASURE 中 CMW/UXM 窗口选择分支和 CMW 专属 attempt context，改为 P2-42 session 提供的共同 current attempt/lease identity。
2. 两家 adapter 均实现共同窗口合同；缺少权威生命周期时返回 unconfirmed，不回退 sleep+poll 正式值。
3. 配置/route receipt 经唯一 writer 落证据，再进入 cell/attach/window。
4. 运行 MEASURE、commissioning 四入口、session 生命周期与报告消费者回归。

**提交**：`refactor: consume base station adapter SPI`

## Task 6：生产路径门与镜像收口

**文件**

- 修改：`api-service/tests/test_rule_gates.py`
- 新增：`api-service/tests/test_p2_43_no_downstream_vendor_branch.py`（若规则门已有合适分组则合并进现有文件）
- 修改：`docs/roadmap-first-call.md`

**RED**

1. 枚举生产路径：MEASURE、commissioning、Analysis、报告、比较、下载、历史。
2. 行为门以明确路径/AST 规则禁止新增 `adapter_id/vendor` 分支；厂商 HAL、registry/readiness 与测试 fixture 显式排除。
3. 先在当前尚存分支上看到失败，再以共同 SPI 替换生产分支；不靠扩大豁免变绿。

**GREEN**

1. 门覆盖当前生产文件并提供行为自测；测试类问题最高 P2。
2. 更新 roadmap 的 P2-42 已合并事实和 P2-43 实施结果，不改历史记录、不提前标记 P2-44/P2-45。
3. 运行 rule gates、diff-check。

**提交**：`test: lock base station adapter boundary`

## Task 7：验证与 fresh 独立功能内审

1. 运行 P2-43 certification、两家 driver、P2-42 session、MEASURE、commissioning、evidence/trust、正式消费者与 rule gates focused 集。
2. 运行全后端回归。
3. 运行 `compileall`、单一 Alembic head、diff-check；若涉及 GUI/OpenAPI 镜像才运行对应契约/build，否则明确记录未改公开契约。
4. 由 fresh 独立审查按 AGENTS.md 0.5 先列全集，缺陷与建议分栏；测试发现上限 P2。功能 P1 收口到 0。
5. 推送并创建 Ready PR，触发 Codex R1；处理本片功能 P1 与本片内 P2后触发 R2。覆盖最新 HEAD 的 R2 无 P1且 mergeable/checks通过才 merge。
6. merge 后 fetch 验证 origin/main，本地主目录 `ff-only` 同步，保留未跟踪仪器资料，清理 worktree/本地分支；现场 certification 保持开放。

