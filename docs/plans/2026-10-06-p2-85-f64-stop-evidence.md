# P2-85 实施计划

> **For agentic workers:** 使用 executing-plans 顺序实施，完成后一次独立只读内审；不派并行实现者。

**Goal:** 已停止的 F64 不再因 GOS 拒绝而失去停止目标证据，且不伪造命令应用或 rewind。
**Architecture:** 在真实 F64 回执处换源到已有 STATE 权威回读；共享 GOS 判据和最终 CLOSED 拒绝策略不放宽。
**Tech Stack:** Python、pytest、现有 SCPI capture/receipt/session。
**Spec:** `docs/design/2026-10-06-p2-85-f64-stop-evidence.md`

## Global Constraints

- 不连接硬件，不新增 SCPI，不改正式 provenance 白名单，无数据库迁移/冻结回执 schema 变化；手工 API 的目标语义与 typed 响应同步四镜像。
- 当前 main 基线 b3f06500，独立 worktree，严格 WIP=1；依赖链接不得提交。
- 共享证据/安全生命周期档：最后稳定输入必须后端全量；无 GUI 输入变化则不重复 build。

### Task 1：停止目标的实际回读

Files: `api-service/app/hal/propsim_f64.py`、`api-service/tests/test_p2_60_channel_operation_receipt.py`、`api-service/tests/test_f64_state_truth_source_f64r1.py`。
接口保持 `stop_emulation() -> bool` 和同步 `project_channel_operation_evidence` 不变。

- [x] RED：在既有停止回执 fixture 中增加第二次 STATE 与查询后清队列，拒绝 GOS + STOPPED/CLOSED 应为 confirmed/runtime_state/实际回读值；RUNNING、矛盾状态和缺尾队列为 unknown。
- [x] 运行定点并记录 AssertionError，不能用导入失败冒充功能 RED。
- [x] GREEN：stop 方法保存两次状态一致性并读取末尾错误队列；projection 只在同归属、同事务终态白名单上确认 runtime_state。保留全部错误索引、共享 GOS recipe，不宣称 rewind。
- [x] 运行上述测试、F64 状态/SCPI证据回归。核心变异：恢复旧 stop projection 时正例红；放行矛盾/异仪器时反例红。

### Task 2：生产 recorder 到正式消费者

Files: 同一 receipt 测试文件；只在必要同根缺口时改生产消费者。

- [x] 使用真实 F64 stop/projection/recorder，只替换传输和存储，连续两次执行验证身份、原错误索引和 confirmed STOPPED；正式终态消费通过。
- [x] 保留并运行最终 CLOSED 拒绝、缺链/释放失败、Mock、不正确 attempt 的既有反例，不将停止目标升级成整体合格。

### Task 3：验证和交付

Files: `docs/roadmap-first-call.md` 与本计划。

- [x] 相关回归、rule gates、完整后端、compileall、Alembic heads、diff-check；记录实际退出码/结尾/输入版本。
- [x] 一次独立只读功能内审；有 P1 最小 TDD 收口，不让 reviewer 重跑同输入全量。
- [ ] 更新当前条目与镜像状态，提交推送，Ready PR，确认远端/PR HEAD 后去重请求 Codex R1→R2；只在最新 HEAD 无 P1 且 checks/mergeable 满足时合并。
- [ ] fetch、主目录 ff-only 同步、清理本片链接/worktree/本地分支，保留未跟踪仪器资料，汇报软件完成与现场未验边界。

## 本地验证台账（2026-10-06）

- RED：新增 P2-85 定点在旧实现上 4 failed /15 passed，均为真实断言失败；旧诊断文案另 1 failed。
- GREEN：P2-85 专项21 passed；相关 P2-85/P2-60/F64状态/rule gates 269 passed；P08 文案修复后 P08+P2-85 58 passed，退出码均0。
- 最终测试输入：`1ac6d8be479f62aa3f313e1df94073272b20ec3e` 的生产/测试/目录文件，无未提交受控代码、fixture或依赖变化；仅本计划的非测试输入台账后补。依赖链接不提交。
- 完整后端：`python -m pytest -q --color=no -o log_cli=false --tb=short`，退出码0；`6952 passed, 17 skipped, 5304 warnings in 246.12s (0:04:06)`，原输出 `/tmp/p2-85-backend-final.log`。此前运行因内审发现P08文案遗漏而新增输入，被主动中断，不算通过；同输入重复全量0次。
- `python -m compileall -q app`、base-to-working `git diff --check` 退出码0；`alembic heads` 单一 `c1e3f5a7b9d2 (head)`，无迁移。
- 独立只读内审：初审P1=0，P08文案P2严格TDD收口，增量复审CLEAN。reviewer只读内存恢复旧projection的两正例RED，旧stop矛盾状态返回True/当前False；尾查询错误与取消安全路径已核对。没有硬件连接或软件结果冒充现场验收。
- 上述首轮验证输入无公共schema/API/GUI变化；R1发现手工API契约仍把停止目标描述成倒回，后续收口新增明确detail与typed响应，同步四镜像并执行production build。外审、合并与同步时间/HEAD在PR台账记录，不为完成时间创建额外待审HEAD。
