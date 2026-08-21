# P2-34 设计稿：正式执行失败告警的发布结果契约

日期：2026-08-21 ｜ Roadmap: P2-34 ｜ 分支 `codex/p2-34-failure-alert-contract`

## 0. 双实证前置（显式记录）

- **memory**：可用（索引在会话上下文）。带问题查得三条命中：
  `feedback_value_form_space`（bool 混叠 = 值的形态空间没枚举）、
  `feedback_effective_end_not_nominal`（可观察语义要落在真实生效端）、
  `feedback_api_contract_sync_after_pydantic_change`（响应字段变更做契约同步）。
- **NotebookLM**：**不适用** —— 本片是告警发布 / DB 契约语义，不碰 HAL 驱动，
  结论里没有任何一句在断言「仪器怎么样」。

## 1. 现状盘点（告警产线已落什么）

产线由 P3-19 最后一片落地（PR #339，commit `34fdc44`），P1-50（#343）未再触碰本模块：

- **产线核心** `api-service/app/services/execution_failure_alerts.py`：
  `emit_execution_failed_alert(execution_id) -> bool`。独立 session、best-effort；
  docstring 禁令「调用方必须先提交 `status='failed'`；告警表故障不得回滚执行终态」、
  「已处置的同一执行告警不得因重试重新变成 active」（生命周期去重）。
- **7 个调用点**（全部丢弃返回值，语句形式）：
  `test_case_runner.py` 4 处（stale 复位 / 异常收尾 / 快照缺失 / 正常收尾 failed）、
  `commissioning.py` 2 处（stale 复位 / run-all 中止）＋定义处。
- **发布结果的现状可观察面**：仅进程日志（成功 `logger.info`、失败 `logger.exception`）。
  **不落库、无 API 面**。
- **返回值 bool 的语义混叠**：`False` 同时表示
  ①按设计跳过（非正式源 / 状态非 failed / 行不存在）②生命周期去重命中
  ③告警写入异常 —— 三种对读方完全不同的结果折叠成一个值。
- **既有测试** `tests/test_execution_failure_alerts.py`：3 组行为（一次性计数、
  非正式源排除、告警失败不回滚终态），断言 `is True / is False` —— 是返回值的唯一消费方。
- **历史读方**：`api/test_execution.py::_to_history_item` 已从 `execution.config`
  派生历史行（`phase_progress` / `error_message` 兜底 / 畸形收窄先例）；
  `ExecutionHistoryItem`（schemas/test_plan.py）↔ openapi `TestExecutionItem` ↔
  前端 `TestExecutionRecord`（TestManagement/types）与 `TestExecutionListResponse`
  （types/api.ts）↔ `mockDatabase.ts` 形状对齐 —— 契约镜像共 4 处。

## 2. 可观察故障（必要性）

任给一个历史失败执行，系统答不出「它的失败告警发出去了吗」：
返回值被 7 个调用点全部丢弃；即使接住，`False` 也分不清「无需告警」与「告警丢了」；
告警写入失败只有一条进程日志，操作员在 GUI / API / DB 侧零可见。

## 3. 契约设计

### 3.1 发布结果的形态空间（白名单枚举，先列全集）

| outcome | 含义 | 落库？ |
|---|---|---|
| `published` | 新告警行已 commit | ✅ 总是写（覆盖旧 `failed` 记录 = 真实状态推进） |
| `duplicate` | 生命周期去重命中（该执行已有告警） | ✅ 保留已有 `published` / `duplicate`；旧 `failed` 或畸形记录推进为 `duplicate` 并写真实 `alert_id`（现存 Alert 已证伪“发布失败”） |
| `failed` | COMMIT 之前已确定的告警链异常（查询、消息准备等） | ✅ 写（error 摘要截断 500 字符；完整 traceback 只进日志）；任何 COMMIT 异常都视为结果未知、不落库 |
| `skipped_missing` | 执行行不存在 | ❌ 没有行可落 |
| `skipped_not_failed` | 状态非 failed（防御分支） | ❌ 可从行自身重derive，非事件结果 |
| `skipped_not_formal` | 非正式源（VRT / 调试 / plan-runner），按 P3-19 设计排除 | ❌ 同上；且不污染 VRT 行的 config |
| （键缺失） | **未记录** —— P2-34 之前的历史行 / 记录写入失败 | 读方语义，见 3.3 |

落库判据：**只记录不可重derive的事件结果**（published/failed 是一次性事件；
duplicate 补缺覆盖「产线上线早于契约」的历史窗口），跳过类判定是行状态的纯函数，不记。

### 3.2 落点与写方（记进哪里）

`TestExecution.config["failure_alert"] = {"outcome", "recorded_at", "alert_id"?, "error"?}`。

- **零迁移**：config 是既有 `_JSONB` 列；runner 失败收尾已有写 config 的先例
  （`error_message` / `failed_phase`，dict 拷贝 + `flag_modified`）。
- **单点写**：记录写在 `emit_execution_failed_alert` 内部（告警事务 commit/rollback
  **之后**的第二个独立事务）。7 个调用点零改动 —— 不给每个站点发写记录的义务，
  从结构上消掉「新调用点漏记」这一类漏。
- **绝不反噬**（硬约束）：记录事务任何异常 → rollback + log，不向调用方泄漏；
  全程不触碰 `TestExecution.status`（G10 门零新增写点）。告警 commit 成功后记录
  写失败 → 告警仍在、行呈「未记录」——宁可未记录，不许错记。rollback / close
  自身失败同样只留日志，不能覆盖已经确定的 outcome；rollback 未成功的 session
  不得再用于记录事务，避免把 pending Alert 与 `failed` 一起提交。历史 `config`
  若不是对象则原样保留并跳过记录，不得为了新增键抹掉整份既有 JSON/SCPI 证据。
- **commit 后零 ORM 回读**：Alert UUID 在 commit 前显式分配并冻结为普通值；commit
  成功后日志只用函数参数。连接若在 commit 确认后断开，不能因过期对象 refresh 失败
  把已经存在的 Alert 重新分类成 `failed`。
- **COMMIT 结果不猜测**：`commit()` 抛错可能是写入前失败，也可能是数据库已落行但
  确认包丢失。旧 session 不再可信，必须用新连接按冻结的 Alert UUID 与执行关联查证：
  行存在记 `published`；一次查不到仍可能早于原事务最终提交，跟新连接不可用一样都
  保持「未记录」，不得猜成 `failed`。

### 3.3 读方语义（谁消费；白名单）

`resolve_recorded_outcome(config) -> Optional[str]`（产线模块导出，单一真值源）：
键缺失 / 形状畸形（非 dict、outcome 不在白名单）→ `None` = **未记录**。
**未记录 ≠ 发布成功** —— 历史执行没有发布记录时，读方只能说「不知道」。

消费端全集与本片选择：

| 消费端 | 本片 |
|---|---|
| DB（config JSONB，psql / 运维排查） | ✅ 3.2 |
| 进程内调用方（结构化 outcome 返回值） | ✅ 3.1 |
| 执行历史 API `GET /test-executions`（`ExecutionHistoryItem.failure_alert_outcome`，`_to_history_item` 经 resolver 派生；None = 未记录，照本 schema「别把 None 渲染成 False」三态先例注释） | ✅ |
| openapi `TestExecutionItem` + 前端类型镜像（api.generated.ts 再生成、`TestExecutionRecord` / `TestExecutionListResponse` 各一行可选字段） | ✅ 契约同步 |
| GUI 渲染（badge / 抽屉展示） | ❌ 未做事项（体验增量，契约先行） |
| mockDatabase 种子 | ✅ 补 `failure_alert_outcome: null`（后端契约恒带该键 → 前端类型非可选，种子必须补；null=未记录恰是这三行「P2-34 之前」的真实语义） |
| 告警发布失败的自动重试 | ❌ 未做事项（本片只做可观察，不加机制） |

## 4. 行为门（RED，`tests/test_p2_34_failure_alert_contract.py`）

- **门A** 失败→发布成功：返回 `published`；Alert 行在；`config["failure_alert"]`
  含 outcome/alert_id（指向真实告警行）/recorded_at；历史行透出 `published`。
- **门B** COMMIT 抛错且新连接暂未看到 Alert → 返回 `failed`；执行 status 仍 `failed`
  （不反噬）；历史保持未记录，不能把一次「查不到」永久写成失败。COMMIT 前已确定的
  外层异常仍记录 outcome==`failed` 与 error 摘要。
- **门B2** 记录也写不进（DB 全炸）：不抛异常、返回 `failed`、执行终态不变、行保持未记录。
- **门B5** COMMIT 确认丢失：若冻结 UUID 对应 Alert 已存在，返回并记录 `published`；
  若暂时不存在或新连接无法查证，返回 `failed` 但历史保持未记录，绝不永久错记失败。
- **门C** 历史行语义：config 无键 → 历史行字段为 None（未记录）；畸形形状
  （非 dict / outcome 越界值）→ 同样 None；**绝不**折叠成 `published`。
- **门D** 去重保持：已处置告警再调 → `duplicate`、不重开告警；行无记录时补记
  duplicate；行已有 published 记录时不覆盖。
- **门E** 跳过类：VRT 源 → `skipped_not_formal` 且 config 零污染；行不存在 →
  `skipped_missing`；非 failed → `skipped_not_failed`。

变异清单（开发 agent 的实跑输出未留存；下列结果为 2026-08-21 内审 + 主 agent 复跑）：
M1 resolver 白名单放行畸形值 → 门C 红；M2 删记录写入 → 门A 红；
M3 记录失败异常泄漏（except 改 re-raise）→ **门B2 不红**（初版写「门B2 红」是假的：B2 两个
commit 都炸，re-raise 被外层 except 接住后返回的恰好也是 failed）→ 内审 F2 补**门B3**
（告警 commit 成功、记录 commit 失败 → 仍 published / 告警 1 行 / 行上未记录）后 M3 红；
M4 duplicate 无条件覆盖 → 门D 红；M5 published 不记 alert_id → 门A 红；
内审另造：M8 外层 except 返回 published → 初版全绿 → 补**门B4**（查询阶段炸 → 不抛、返回
failed、会话关闭）后红；MX1 resolver 去掉 `isinstance(str)` 前置 → 门C 新增的 list / dict
脏值两条红（内审 F1：不可哈希值会让 `in set` 抛 TypeError 吞掉整页历史）。

## 5. 范围外（显式）

GUI 渲染、告警重试机制、`ExecutionHistoryItem` 之外的 API 面（commissioning 会话响应等）、
`skipped_*` 的落库。均记入产出报告的未做事项。（mockDatabase 种子**已做**，见 §3.3 ——
初版此处误列为范围外，内审 F4 纠正。）
