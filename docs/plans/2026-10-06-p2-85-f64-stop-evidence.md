# P2-85 实施计划

> **For agentic workers:** 使用 executing-plans 顺序实施，完成后一次独立只读内审；不派并行实现者。

**Goal:** 已停止的 F64 不再因 GOS 拒绝而失去停止目标证据，且不伪造命令应用或 rewind。
**Architecture:** 在真实 F64 回执处换源到已有 STATE 权威回读；共享 GOS 判据和最终 CLOSED 拒绝策略不放宽。
**Tech Stack:** Python、pytest、现有 SCPI capture/receipt/session。
**Spec:** `docs/design/2026-10-06-p2-85-f64-stop-evidence.md`

## Global Constraints

- 不连接硬件，不新增 SCPI，不改正式 provenance 白名单，无数据库迁移/公共 schema 变化。
- 当前 main 基线 b3f06500，独立 worktree，严格 WIP=1；依赖链接不得提交。
- 共享证据/安全生命周期档：最后稳定输入必须后端全量；无 GUI 输入变化则不重复 build。

### Task 1：停止目标的实际回读

Files: `api-service/app/hal/propsim_f64.py`、`api-service/tests/test_p2_60_channel_operation_receipt.py`、`api-service/tests/test_f64_state_truth_source_f64r1.py`。
接口保持 `stop_emulation() -> bool` 和同步 `project_channel_operation_evidence` 不变。

- [ ] RED：在既有停止回执 fixture 中增加第二次 STATE 与查询后清队列，拒绝 GOS + STOPPED/CLOSED 应为 confirmed/runtime_state/实际回读值；RUNNING、矛盾状态和缺尾队列为 unknown。
- [ ] 运行定点并记录 AssertionError，不能用导入失败冒充功能 RED。
- [ ] GREEN：stop 方法保存两次状态一致性并读取末尾错误队列；projection 只在同归属、同事务终态白名单上确认 runtime_state。保留全部错误索引、共享 GOS recipe，不宣称 rewind。
- [ ] 运行上述测试、F64 状态/SCPI证据回归。核心变异：恢复旧 stop projection 时正例红；放行矛盾/异仪器时反例红。

### Task 2：生产 recorder 到正式消费者

Files: 同一 receipt 测试文件；只在必要同根缺口时改生产消费者。

- [ ] 使用真实 F64 stop/projection/recorder，只替换传输和存储，连续两次执行验证身份、原错误索引和 confirmed STOPPED；正式终态消费通过。
- [ ] 保留并运行最终 CLOSED 拒绝、缺链/释放失败、Mock、不正确 attempt 的既有反例，不将停止目标升级成整体合格。

### Task 3：验证和交付

Files: `docs/roadmap-first-call.md` 与本计划。

- [ ] 相关回归、rule gates、完整后端、compileall、Alembic heads、diff-check；记录实际退出码/结尾/输入版本。
- [ ] 一次独立只读功能内审；有 P1 最小 TDD 收口，不让 reviewer 重跑同输入全量。
- [ ] 更新当前条目与镜像状态，提交推送，Ready PR，确认远端/PR HEAD 后去重请求 Codex R1→R2；只在最新 HEAD 无 P1 且 checks/mergeable 满足时合并。
- [ ] fetch、主目录 ff-only 同步、清理本片链接/worktree/本地分支，保留未跟踪仪器资料，汇报软件完成与现场未验边界。
