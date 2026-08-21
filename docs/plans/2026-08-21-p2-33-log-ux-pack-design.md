# P2-33 日志体验包 — 设计稿

> Roadmap: P2-33（Discovered 四条日志类条目打包）。
> 原则：四条各自修、各配行为门与变异；一个 PR；不碰 P2-36 的"入口/跳转"面
> （`initialExecutionFilter` / `isolateExecution` / `isolateRequest` 及 P1-39 useEffect 原样不动）。

## 双实证

- memory：可用，已查（`feedback_enumerate_before_changing` / `feedback_value_form_space` /
  `feedback_gui_two_verification_gates` / `feedback_doc_mirror_sweep`）。
- NotebookLM：**不适用** —— 纯日志过滤 / GUI，无任何仪器语义断言。

---

## ① 重复抑制桶不按日志级别隔离

**故障**（Codex #303 R1，`app/core/logging_config.py`）：
`_DuplicateBurstLimiter._key` = `(execution_id, instrument_id, logger名, 渲染文本)`，
不含级别。同一秒内先有 ≥ `repeat_limit` 条相同文本的 INFO，随后相同文本以 ERROR
输出时，该 ERROR 落进已满额的 INFO 桶被直接抑制；窗口到期的摘要又是从桶内
`sample`（首条 INFO）复制的 —— 日志里完全看不到级别升级。突发限流因此可能吞掉
真正的告警。

**改法**：`_key` 末尾追加 `record.levelno`，同步改 `_key` 返回注解与 `_buckets`
的 dict 注解（`tuple[str, str, str, str, int]`）。消费方全集已枚举：
- `process()`：唯一构造点，追加安全；
- `drain(execution_id=…)`：只读 `key[0]`，末尾追加不影响；
- `max_buckets` 逐出：按 `started_at` 不看 key 结构；
- `_summary`：桶按级别隔离后 `sample` 级别自然与桶一致，摘要级别随之正确。

**门**（行为门，`test_p2_33_log_ux_pack.py`）：`ExecutionFileHandler(repeat_limit=2,
window=1s, 假时钟)`，同秒发 3 条同文本 INFO（第 3 条应被抑制）+ 1 条同文本 ERROR：
- ERROR 必须以独立行存活（level=ERROR、原文完整）；
- 时钟推进后 INFO 桶摘要 `suppressed_count == 1`（只算 INFO，不含 ERROR）。

**变异**：把 `_key` 里的 `record.levelno` 去掉 → ERROR 被吞、门红。

---

## ② 关键词过滤匹配不到 traceback 续行

**故障**（Codex #303 R1，`app/api/system_logs.py`）：反向扫描把 RAW 续行积在
`pending_continuations`，遇到父记录时**只对父记录**调谓词，随后无条件清空续行；
`/export` 的 `emit_group` 同样只查 `group[0][1]`。关键词只出现在续行时
（父 `request failed`、续行 `ValueError: broken`），搜 `broken` 在 `/tail`、
`/history`、`/export` 三处同时消失。

**改法**（保持"三入口共用一份谓词"的既有硬约束）：
1. 关键词判定从 `_entry_matches` 抽成 `_keyword_hit(entry, kw_lower)`，
   `_entry_matches` 内部改调它（单条语义不变，关键词逻辑全仓唯一一份）；
2. 新增组谓词 `_group_matches(parent, continuations, level, keyword, session_id,
   hal_mode, execution_id)`：非关键词维度只看父记录（保留父级 level/session 语义）；
   关键词由父或组内任一续行满足；
3. `_scan_reverse_entries` 的 `predicate` 升级为二参 `(entry, continuations)`：
   两处父判定传 `pending_continuations`，孤儿 RAW 分支传 `[]`（legacy 单条行为不变）；
   谓词须同步消费续行列表（调用后即被 clear）；
4. `/tail`、`/history` 的 lambda 与 `/export` 的 `emit_group` 全部改走
   `_group_matches`。

**同步更新既有门**：`test_p1_35_log_value_policy.py::test_tail_and_export_share_one_filter_predicate`
的 token 从 `_entry_matches(` 改为 `_group_matches(`（意图不变：/export 不得自抄
谓词；行为仍由 `test_tail_and_export_return_the_same_rows` 行为门兜底）。
后端集合语义两 token（`wanted = {…}` / `not in wanted`）原样保留。

**门**（行为门）：父 INFO `request failed` + 续行 `Traceback…` / `ValueError: broken`：
- `/tail?keyword=broken`、`/history?keyword=broken`、`/export?keyword=broken`
  三处都返回整组（父 + 续行）；
- 反向：`level=ERROR&keyword=broken`（父是 INFO）→ 0 行 —— 非关键词维度仍只看父；
- 反向：`keyword=不存在` → 0 行。

**变异**：`_group_matches` 去掉续行扫描（只查父）→ 正向门红（三入口 3 条）；
关键词命中续行即放行整组、绕过父记录的 level 判定 → 反向门红。
（初版写的"非关键词维度改成父或续行任一满足"实跑是**等价变异**：续行 level 恒为
RAW，永远匹配不上 ERROR，门不红不是门失效 —— 2026-08-21 收尾时实跑纠正。）

**②′ 内审 F1（P1）补：生产 traceback 的真实落点是同一行 JSON 的 `exception` 键，不是 RAW 续行。**
`JsonFormatter` 把 `formatException` 结果放进 `log_entry["exception"]`，不产生任何非 JSON 续行
（主仓 16 天 `app.log*` 269,139 行 + 244 个 `exec-*.log` 只读统计：RAW 续行 **0** 条、带
`"exception":` 字段 **150** 条）。所以上面的续行修法对真实日志是空转，"搜异常类名 0 命中"原样存在。
修法（换判据来源，不改契约）：`LogEntry` 加 `PrivateAttr` `_exception_text`（不进响应、不进 schema，
`raw` 已带全文供详情展开），`_parse_log_line` 只收 str 填入，`_keyword_hit` 多看这一腿；三入口
仍走同一份 `_group_matches`。RAW 续行那条腿保留（它对中段父记录也正确，只是不是生产形态）。
**门**：`TestKeywordMatchesSameLineExceptionField` 用生产 `JsonFormatter` 真实生成 `logger.exception`
行（带前提自检：traceback 必须在同行 exception 键里），三入口正向 + 契约不变 + 反向各一条。
**变异**：`_keyword_hit` 去掉 exception 腿 → 4 红；`_parse_log_line` 不填 → 4 红。
**内审 F2 顺带**：两个场景都在父记录前放一行更早的无关行，让父记录落进反向扫描**主循环**分支
（此前父记录在文件第 1 行只走 `position == 0` 文件头分支，主循环把续行传 `[]` 三门全绿）；
复验：主循环传 `[]` → 3 红。

---

## ③ 两个日志面板对「异常」两个定义，主控台漏 CRITICAL

**故障**（P1-35 内审 F8，`gui/src/features/Dashboard/ZoneLogsAlerts.tsx`）：
`LEVEL_FILTERS` 只有 INFO/WARNING/ERROR，**没有任何 chip 能打开 CRITICAL** ——
客户端过滤 `enabledLevels.includes(level)` 恒把 CRITICAL 滤掉；且 boost 补充流
只有 WARNING/ERROR 两路，刷屏时 CRITICAL 也会被冲出主流 200 行窗口
（P2-11 失效模式对 CRITICAL 依然成立）。

**改法**（四处加 CRITICAL，均在该文件内）：
- `LEVEL_FILTERS` 加 `{ value: 'CRITICAL', label: 'CRIT' }`；
- 默认 `enabledLevels` 加 `'CRITICAL'`；
- `LOG_LEVEL_COLOR` 加 `CRITICAL: 'grape'`（与 SystemLogViewer 的 LEVEL_COLORS 一致）；
- boost 流 `['WARNING', 'ERROR']` → `['WARNING', 'ERROR', 'CRITICAL']`
  （与既有两路同型的第三路，仍按 level 精确匹配、跨流天然不相交）。

G15 门守的 3 个 token（`filterGroupedLogEntries(data?.entries ?? [],`、
`[...groupedEntries].reverse()`、`top: sortDesc ? 0 : …`）全部原样保留。

**明确不做**：条目里提的"用一个 `level=WARNING,ERROR,CRITICAL` 请求替掉两路
boost + 跨流去重"化简。⑦ 判据：不做它，"漏 CRITICAL"故障已修 —— 它是独立的
重构机会，留在 Discovered 原条目里。

**门**：
- 不变量门：ZoneLogsAlerts 的 boost 级别集 ∪ {WARNING,ERROR,CRITICAL 之外不得有}
  与 SystemLogViewer 的 `ISSUE_LEVELS` **集合相等** —— 两个面板对「异常」只剩一个定义；
- 结构门：`LEVEL_FILTERS` 与默认 `enabledLevels` 与 `LOG_LEVEL_COLOR` 都含 CRITICAL。

**变异**：LEVEL_FILTERS 去掉 CRITICAL → 门红；boost 列表去掉 CRITICAL → 不变量门红。

---

## ④ 日志面板级别过滤改多选（集合语义，不是门槛）

**故障**（P1-34 期间实测，`gui/src/features/Reports/components/SystemLogViewer.tsx`）：
级别过滤是单选 SegmentedControl（全部/仅异常/ERROR/WARNING/INFO/DEBUG），
没有任何一档能表达"去掉 DEBUG 心跳但保留 INFO 及以上"（实测 400 行里 253 行
DEBUG 心跳）。后端 `level` 自 P1-35 起已收逗号集合，GUI 却发不出任意多值组合。

**硬边界**（既有立场，全部尊重）：
- **不改后端**：集合成员判断不许变门槛（ZoneLogsAlerts 跨流去重依赖流不相交）；
- **不做前端并流**（P1-35 定论：导出是下载链接合不了流）；
- 屏幕 / 历史页 / 导出仍走**同一个** `buildLogQuery`（恰 3 处调用）。

**改法**（全部在 SystemLogViewer.tsx 内）：
- `levelFilter: string`（含 `__ISSUES__` 哨兵）→ `selectedLevels: string[]`，
  空数组 = 全部（不发 `level` 参数）；
- SegmentedControl 换 `Chip.Group multiple`：DEBUG/INFO/WARNING/ERROR/CRITICAL
  五个 chip + 「🚨 仅异常」快捷按钮（一键置为 `Array.from(ISSUE_LEVELS)`）；
- `buildLogQuery` 收 `levels: string[]`，归一化唯一一处：
  `levels.length ? levels.join(',') : null`；
- `clearTextFilters` 的 `setLevelFilter('ALL')` → `setSelectedLevels([])`；
- `ISSUES = '__ISSUES__'` 哨兵常量删除 —— 多选模型没有哨兵态，
  "哨兵值漏发给后端 → 0 行"这一类风险从源头消失；`ISSUE_LEVELS` 保留（快捷键用）。

**同步更新既有门**（保持意图、跟随形态，`test_p1_35_log_value_policy.py`）：
- `test_issues_view_covers_warning_error_and_critical`：ISSUE_LEVELS 集合断言不变；
  "只准整体 `.join`" 改为"只准整体消费（`Array.from(ISSUE_LEVELS)`），
  禁止 `slice/filter/map` 切筛"——强度等价（立门实证防的是 `.slice(0,1)` 静默退化）；
- `test_screen_history_and_export_build_their_query_from_one_place`：
  buildLogQuery 恰 3 调不变；`=== ISSUES` 哨兵恰 1 处改为
  "归一化 `join(',')` 恰 1 处（在 buildLogQuery 里）+ 全文件不得再出现 `__ISSUES__`"。

**门**：
- 结构门：viewer 无 SegmentedControl level 档、有多选 Chip.Group、
  `buildLogQuery` 收数组且归一化恰一处；
- 行为门（后端既有）：集合语义由 `test_level_filter_is_set_membership_not_threshold`
  继续守，本片不动它。

**变异**：快捷键改 `ISSUE_LEVELS.slice(0, 1)` → 门红；
buildLogQuery 外再拼一份 level 参数 → 恰 3 调门红。

---

## 验证计划

- RED → GREEN：`api-service/tests/test_p2_33_log_ux_pack.py`（四条各至少一个行为/不变量门）；
- 变异实跑：每条至少一变异让门变红（快照还原、`assert` 命中）；
- 全量：`cd api-service && .venv/bin/python -m pytest -q --color=no -p no:cacheprovider`
  零失败、无豁免（原已知失败 `test_p1_36_execution_id::test_no_execution_means_default_not_empty`
  已由 P2-35 #357 治掉）；
- GUI：`cd gui && npm run build`；
- G14/G15 必须保持绿。
