# P2-62：第三种 Channel Emulator Adapter 接入认证套件实施计划

> 严格 WIP=1；每个功能改动先 RED、确认失败原因，再最小 GREEN。测试夹具只存在测试域。

## Task 1：测试域第三 adapter 与注册五件套

- 新增 `tests/channel_emulator_certification_kit.py` 与定点测试；
- 先写 manifest/实现/profile/manual evidence/临时注册 RED；
- 实现 certfake profile、fake transport、driver 与临时注册上下文；
- 加生产目录零泄漏门。

## Task 2：binding、preset 与执行计划

- 参数化复用 P2-58/P2-59 的 DB 夹具；
- RED 覆盖保存/恢复、活动 preset 漂移、错误型号/endpoint、manifest 漂移；
- 仅通过测试内临时 registry 注入 certfake，生产注册表不变；
- 证明共同 resolver/preview/freeze/plan 无型号分支。

## Task 3：操作回执与 fake transport

- RED 覆盖部分回读、错误队列、资产加载、start/stop/动态调参；
- 最小实现只记录测试协议 exchange，字段确认必须来自 fake transport 的显式权威证据；
- operation succeeded 与 field confirmed 保持分离；错误队列拒绝/异常均 fail-closed。

## Task 4：超时、取消、SAFE_IDLE、release 与模拟排除

- RED 覆盖延迟、取消、SAFE_IDLE 未确认、release 未确认；
- 复用生产 session/receipt 组合，不复制第二套生命周期；
- simulated subject 只形成 diagnostic/unknown，正式 outcome 保持不可用。

## Task 5：共同消费者中立性

- 用 certfake 完整执行证据写 RED，证明现有 F64-only certification frequency 门拒绝第三 adapter；
- MEASURE 生成冻结的 `channel_emulator_evidence` 通用投影；
- certification 换源到通用投影，保留旧 F64 镜像兼容；
- 加错 adapter、缺回读、unknown 带宽、篡改、模拟等反例；
- 复核 commissioning、P2-66、报告/下载/历史均只消费共同 outcome。

## Task 6：API/GUI 镜像与路线图

- 若通用证据进入显式 schema，同步 live OpenAPI、`api/openapi.yaml`、generated TS、手写类型；
- GUI 只显示服务器证据，不生成客户端真值；
- 更新 roadmap：P2-61 完成、P2-62 实现与验证状态；P2-63 保持 HOLD。

## Task 7：验证、内审与合并

- P2-62 定点与 P2-57～61 受影响链；
- 全后端；GUI 契约与 production build（若触 GUI/API）；
- `compileall`、单一 Alembic head、base-to-HEAD diff-check；
- 至少两项核心变异：生产泄漏、F64-only/伪证据门；
- fresh 独立功能内审到 P1=0；
- Ready PR，Codex R1→R2；覆盖最新 HEAD 的 R2 无 P1且可合并才 merge；
- fetch、主目录 ff-only、清理 worktree/分支；P2-63 不自动启动。
