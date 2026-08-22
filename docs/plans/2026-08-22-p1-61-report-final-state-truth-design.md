# P1-61 正式 MIMO 报告最终状态真值设计

## 背景与可观察故障

2026-08-22 最近一次手工执行导出 `app_export (1).jsonl`，执行
`e974e199-c1b7-4852-9e93-9246c8cd9165` 最终已完成，数据库记录耗时
`89.195194` 秒；自动生成的正式报告
`1779d5e8-8f98-41b3-92ab-347aacfa7da1` 却写成 `running`、`Pending=1`、
`0.0 seconds`。这不是展示延迟，而是报告生成器在 REPORT 相位把执行标为完成之前读取了
生命周期字段，并把“执行完成但没有可信正式判决”的 `UNKNOWN` 错写成等待中的 `pending`。

正式 PDF 会交付客户与认证机构，因此必须反映报告落盘时可证明的最终执行状态；不能把已经
结束的执行说成仍在运行，也不能用零秒覆盖真实耗时。

## 全集与边界

本片处理同一事实的全部正式消费方：

- REPORT 执行器构造 `content_data`、创建报告、生成 PDF、再提交执行生命周期；
- `_build_mimo_ota_content_data()` 的 `test_plan.status`、`duration_s`、
  `execution_summary`、首末时间与四态计数；
- `ReportService` 对历史 completed 执行的安全重建；
- `PDFGenerator` 已有的 `undetermined` / `incomplete` / `pass_rate=None` 渲染契约；
- 与旧 `UNKNOWN -> pending` 镜像绑定的回归测试。

本片不改 KPI、校准或报告恢复资格，不改数据库 schema，不处理 P1-62 的路损叙事问题。

## 方案裁决

### 采用：不可公开 staging、只读最终状态投影与数据库条件终态裁决

REPORT 开始时计算一次共同的 `completed_at` 与 `duration_sec`，以显式投影参数传给内容构造器。
报告内容和 `ReportService` 的内部安全重建都使用该投影；ORM 对象仍保持原状态，PDF 先写入
不可下载的 staging 路径，pending/generating 报告行不写入 completed `content_data` 或正式
`file_path`。随后只允许数据库中的 `running -> completed` 条件更新，与独立会话的
`running -> cancelled` 竞争，保证只有一个终态赢家。若取消先赢，在 staging 内按数据库赢家
重建为 `cancelled/incomplete`；最终只把赢家 PDF、`content_data` 与下载路径一次性公开。
因此不存在“先发布错误 completed 报告、再事后覆盖”的可下载窗口。

历史重建不传投影，继续读取数据库中已经提交的最终生命周期。

### 未采用：生成 PDF 前先把 ORM 状态提交为 completed

该方案代码较短，但会破坏 REPORT 相位的取消语义：PDF 仍在生成、甚至随后失败时，其他请求已
看到 completed；取消请求也可能被提前完成覆盖。它把展示问题变成生命周期竞态，因此拒绝。

### 未采用：先发布 completed，再事后补丁 PDF 内容

后续重建无法追回已经下载的错误文件，因此任何 completed 投影都不得在终态裁决前进入正式
路径。取消先赢时可以在 staging 内重建同一报告，但对外始终只有一次发布。

## 最终状态契约

内容构造器先确定有效生命周期，再确定正式判决：

| 生命周期 | 可信判决 | 报告四态 | Pass Rate |
|---|---|---|---|
| completed | PASS/MARGINAL | passed=1 | 100% |
| completed | FAIL | failed=1 | 0% |
| completed | UNKNOWN / 证据不足 | undetermined=1 | 未判定 (`None`) |
| pending | 任意 | pending=1 | 未判定 (`None`) |
| running/cancelled/skipped | 任意 | incomplete=1 | 未判定 (`None`) |
| failed | 任意 | failed=1 | 0% |

任何状态下四态计数只能有一项为 1。`UNKNOWN` 是判决状态，不再冒充生命周期 `pending`。
报告的 `test_plan.status`、`duration_s`、`total_duration_sec`、`last_execution` 必须来自同一
有效生命周期投影。

## 失败与取消语义

- PDF 生成失败仍沿用现有策略：执行测量已结束，生命周期提交 completed，并把报告失败写入 warning；
- REPORT 运行期间 ORM 状态不提前改变；完成与 operator cancel 通过数据库条件更新裁决；
- operator cancel 自身也只允许 `running -> cancelled` 条件更新；取消端先读 running、REPORT
  先完成时，迟到取消必须返回冲突，不能用旧 ORM 快照反向覆盖 completed；
- 普通完成、相位失败、快照缺失与执行器顶层异常同样只能通过共享的数据库条件终态裁决；
  取消成功后，任何持有旧 `running` ORM 快照的收尾不得覆盖成 completed/failed，失败告警也只由
  真正赢得 failed 终态的一方发布；
- cancel 先赢时，同一报告按 cancelled/incomplete 重建；completed 先赢后 cancel 返回冲突；
- 历史行缺少 `duration_sec` 或 `completed_at` 时保持 `None` 并渲染 `N/A`，不得猜 0 秒或重建时刻；
- commissioning adhoc 包装层只收尾仍为 running 的相位，不覆盖 REPORT 已拥有的终态时间；
- 正式 runner 与 commissioning 的 REPORT 必须延迟到仪表租约成功退出、F64/UXM 已确认交还
  Local 后才允许生成或发布；交接失败时不得留下 completed/可下载报告；
- 业务异常与 Local 交接异常同时发生时，交接失败不能被前一个异常遮蔽；既有业务错误、取消
  或完成证据必须保留，并把最终生命周期降级为 failed。若交接失败收尾的第一次 CAS 输给并发
  取消，必须重读终态赢家后再裁决，不能静默漏掉硬件仍可能处于 Remote 的事实；
- 公开恢复入口只允许权威执行已经处于终态时取得 writer claim；运行中的内部 pending 报告
  只能由同时携带 typed projection 与数据库 resolver 的 REPORT executor 继续；
- 外部取消方若先写入 cancelled/completed_at，也必须把同一终态的 duration_sec 落到执行行；
  报告不得独占一份只存在于 PDF 投影里的耗时；
- 内容投影不写数据库、不创建第二份状态缓存；
- 可信性门仍优先于 PASS/FAIL：校准或吞吐证据不足时，completed 执行只能是 undetermined。

## 验证策略

先用 TDD 证明五个核心故障：

1. running ORM + completed 投影生成 completed/89.195 秒/undetermined；
2. 构造报告时 ORM 仍是 running，证明没有提前提交 completed；
3. 历史 completed 执行无需投影也保持相同四态契约；
4. `ReportService` 不得用数据库 running 摘要覆盖内部最终投影；
5. PDF 生成期间取消先赢时，执行保持 cancelled 且同一报告在 staging 内重建为 incomplete；
6. 裁决前报告行仍为 generating、没有正式路径和 completed 内容；
7. 历史 completed 行缺时间时 payload/PDF 显示未知/N/A；
8. commissioning adhoc REPORT 保留 executor 已裁决的终态、完成时间与耗时。
9. 运行中的内部 pending 报告不能被公开 regeneration 抢占 writer claim；
10. cancel 先赢时，执行行与重建报告持有相同的非空真实耗时。
11. cancel 先读 running、REPORT completion CAS 先赢时，迟到 cancel 返回 False，数据库与
    报告都保持 completed。
12. runner 已读到 phase failure 后，cancel CAS 先赢时，普通失败收尾不得覆盖 cancelled，
    也不得发布 `execution_failed` 告警。
13. 正式 runner、commissioning 单相位/adhoc/run-all 均在仪表租约成功退出后才调用 REPORT；
14. 业务异常与 lease release 异常同时出现时，外层必须收到包含两者的
    `InstrumentTestLeaseError`；
15. Local 交接失败发生在 completed/cancelled/failed 既有终态后时，最终统一 failed，保留
    原错误并写入交接诊断与失败告警；
16. Local 交接失败的第一次终态 CAS 若输给并发 cancel，重读 cancelled 赢家后再次裁决为
    failed，并保留取消证据。
17. commissioning 单阶段与 run-all 的 Local 交接失败必须留下 failed 终态与失败告警，不能由
    `_execution_marked_running` 恢复成 pending 后允许重复操作硬件。
18. Remote 获取失败与 Local 归还失败必须由不同异常类型表达；只有后者能覆盖既有业务终态并
    标记仪表可能仍处于 Remote。
19. 同一执行已有已确认/已解决告警时，后续 Local 交接失败只刷新告警正文，不重开告警生命周期；
    数据库主错误字段、配置镜像与告警正文必须共同包含新的安全事实和此前业务错误。

随后更新旧镜像测试，运行报告链、runner/取消链、完整规则门、全后端回归、`compileall`、
单一 Alembic head 与 `diff-check`，再做 fresh 内审与 Codex 外审。
