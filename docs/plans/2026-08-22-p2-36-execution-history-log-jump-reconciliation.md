# P2-36 执行历史一键跳日志：现状核验与重复项收口

## 结论

P2-36 不需要再次开发。它描述的可观察故障已由 P1-39 / PR #292 在提交
`5c89a602644a6257bf6dcd987730efa6a93a7dcc` 完整修复，并且整条链仍存在于
2026-08-22 的 `origin/main`。2026-08-21 将旧 Discovered 文字再次提升为 P2-36 时，
没有同步核对 P1-39 的完成事实，形成了重复 roadmap 项。

## 当前生效链

1. `HistoryTab` 的每条执行记录在 `onViewLogs` 已接线时显示“查看这次执行的日志”按钮，
   点击时传递完整 `record.id`，而不是短标签。
2. `TestManagement` 将回调传给 `HistoryTab`；`App.handleViewExecutionLogs()` 保存完整
   execution ID，并切换到“数据归档与报告”。
3. `ReportsPage` 以一次性交接方式消费该 ID，自动切到“系统日志”页签；消费后清空
   App 侧 pending state，避免后续进入报告页时被永久劫持。
4. `SystemLogViewer` 通过 `initialExecutionFilter` 的惰性初值构造第一次日志请求，
   `buildLogQuery()` 将完整值发送为 `execution_id`，不会先发未过滤请求再由乱序结果覆盖。
5. 执行历史显示“用例名 + 本地执行时间标签”，过滤和复制仍使用完整 UUID；同名用例不会
   被合并为同一条日志链。

## 历史证据

- 引入提交：`5c89a60 feat: 让人拿得到执行/用例 ID + 一键跳日志 + 日志默认新在最上 (P1-39) (#292)`。
- 该提交描述明确列出 `HistoryTab → App → ReportsPage → SystemLogViewer` 四段接线，
  并记录浏览器实测过滤后的日志只包含目标 execution ID。
- roadmap 的 P1-39 段已标记 `✅ Done（#292，2026-08-06）`，且 P1-39 顶部索引同样写明
  “执行/用例编号在界面上可见可复制 + 一键跳日志（#292 已合）”。

## 本片处置

- 不改产品代码，不再复制现有导航或过滤机制；
- 将 P2-36 标记为由 PR #292 既有实现完成；
- 将对应 Discovered 条目标记 resolved，保留历史故障与修复来源；
- Current Focus 移到真正未完成的 P2-31。

## 验收

- 全仓核对四段产生/消费链仍完整；
- 核对过滤键始终使用完整 execution ID；
- `git diff --check` 通过；
- docs-only diff 经 fresh 内审与 Codex 外审后合并。

