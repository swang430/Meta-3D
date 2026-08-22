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

### 采用：只读“最终状态投影”与数据库条件终态裁决

REPORT 开始时计算一次共同的 `completed_at` 与 `duration_sec`，以显式投影参数传给内容构造器。
报告内容和 `ReportService` 的内部安全重建都使用该投影；ORM 对象仍保持原状态，直到 PDF
尝试结束。随后只允许数据库中的 `running -> completed` 条件更新，与独立会话的
`running -> cancelled` 竞争，保证只有一个终态赢家。若取消先赢，同一报告立即按数据库赢家
重建为 `cancelled/incomplete`，PDF、持久化 `content_data` 与执行行不再分叉。

历史重建不传投影，继续读取数据库中已经提交的最终生命周期。

### 未采用：生成 PDF 前先把 ORM 状态提交为 completed

该方案代码较短，但会破坏 REPORT 相位的取消语义：PDF 仍在生成、甚至随后失败时，其他请求已
看到 completed；取消请求也可能被提前完成覆盖。它把展示问题变成生命周期竞态，因此拒绝。

### 未采用：无条件生成后再补丁 PDF 内容

常规 completed 路径只生成一次，不做事后补丁。唯一例外是数据库已证明 operator cancel
先赢：此时第一版 completed 投影已经失效，必须通过既有 `ReportService` 重建同一报告，而不是
直接改 PDF 或另建第二份报告。

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
- cancel 先赢时，同一报告按 cancelled/incomplete 重建；completed 先赢后 cancel 返回冲突；
- 内容投影不写数据库、不创建第二份状态缓存；
- 可信性门仍优先于 PASS/FAIL：校准或吞吐证据不足时，completed 执行只能是 undetermined。

## 验证策略

先用 TDD 证明五个核心故障：

1. running ORM + completed 投影生成 completed/89.195 秒/undetermined；
2. 构造报告时 ORM 仍是 running，证明没有提前提交 completed；
3. 历史 completed 执行无需投影也保持相同四态契约；
4. `ReportService` 不得用数据库 running 摘要覆盖内部最终投影；
5. PDF 生成期间取消先赢时，执行保持 cancelled 且同一报告重建为 incomplete。

随后更新旧镜像测试，运行报告链、runner/取消链、完整规则门、全后端回归、`compileall`、
单一 Alembic head 与 `diff-check`，再做 fresh 内审与 Codex 外审。
