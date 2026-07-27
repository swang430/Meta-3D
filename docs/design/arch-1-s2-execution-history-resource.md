# ARCH-1 S2 设计稿 — 执行历史与报告换源到 TestExecution

> **状态**：设计稿，待 review，**尚未动代码**。
> **上游**：[`arch-1-testcase-first-simplification.md`](arch-1-testcase-first-simplification.md) §3 的 S2 行 +
> 任务 #90（含 PR #237 Codex C3「导航丢 activeRun」的落点）。
> **实证前置**：
> - memory 查询（恒适用）**命中 5 条**：`feedback_effective_end_not_nominal`（验证打真实生效端）/
>   `feedback_whole_not_local`（动手前枚举影响集）/ `feedback_value_form_space`（nullable 三态）/
>   `feedback_react_query_shape_change_needs_new_key`（返回形状变必须换 queryKey）/
>   `feedback_api_contract_sync_after_pydantic_change`（契约 4 步）。逐条落点见 §5。
> - NotebookLM：**不适用**（GUI / API 数据源重接，零仪器 SCPI 语义）。
> **代码事实**：2026-07-27 盘点，行号以 main `124d7e5` 为准。

---

## 0. 一句话

历史 Tab、驾驶舱「最近执行」、报告页「待归档执行」三处读的都是**计划级摘要表**
（`test_plan_executions`），而 S1 的用例执行**根本不写那张表** —— 点执行、跑完 5 相位、
落了执行行，历史里一片空白。S2 把这几处的数据源换到**执行行本表**（`test_executions`），
顺带修好一条早就断了的线：历史行点「生成报告」递过去的 id 属于另一张表，报告收集器
按它一行都查不到。**全程「换源」，唯一的"加"是一个新的列表响应 schema（老的那个用不了，
见 §5.3）**。

---

## 1. 现状地图（每条带出处，可自查）

### 1.1 两张表的分工

| | `test_plan_executions`（计划级摘要） | `test_executions`（执行行本表） |
|---|---|---|
| 谁写 | 计划收尾时建 1 行摘要（`test_plan_service.py:1620` / `:1897`） | **5 处**：case-runner（`test_case_runner.py:140`）/ plan-runner 每步（`test_plan_runner.py:283`）/ 暗室首测 run-all（`commissioning.py:372`）/ 单相位诊断（`commissioning.py:558`）/ VRT（`vrt_execution_service.py:82`） |
| 主键 | 自己的 uuid4（`models/test_plan.py:285`） | 自己的 uuid4（`models/test_plan.py:218`） |
| S1 用例执行 | **不写** | 写 |
| 粒度 | 一次计划 = 1 行 | 一次执行 = 1 行（含 5 相位进度、测量、报告产物） |

**两张表的 id 各自随机生成，永远不会撞上** —— 这是 §1.4 那条断线的成因。

### 1.2 路由名早就和内容错位

前缀写着 `/test-executions`，查的却是 `TestPlanExecution`：
- 列表 `test_execution.py:89`
- 单条 `test_execution.py:130`
- 删除 `test_execution.py:145`
- 最近 N 条 `test_execution.py:47`

S1 加执行状态轮询时被这条错位挡过一次，只好另挂在 `/test-plans/cases/executions/{id}`，
并在 docstring 里写了「S2 统一收口」（`test_plan.py:564-565`）。本片就是那个收口。

### 1.3 消费方枚举（换源的影响集 = 4 处，不是 1 处）

| # | 消费方 | 调用点 | 现在拿到的形状 |
|---|---|---|---|
| ① | 测试管理「执行历史」Tab | `HistoryTab.tsx:73` → `useTestHistory` → `testManagementAPI.ts:313` | 计划摘要行 |
| ② | 报告页「待归档执行」 | `PendingExecutionsList.tsx:47`（`status=completed`） | 同上 |
| ③ | 驾驶舱「最近执行」 | `ZoneActiveRun.tsx:116` → `service.ts:182` | 同上（前端类型却叫 `TestExecutionItem`，`types/api.ts:268` —— 名字和内容错位的老账，本片一并了结） |
| ④ | 仪表盘「最近测试」卡片 | `App.tsx:4360` → `/test-executions/recent` | 计划摘要行（简化成 id/name/dut/result/date） |

①②③ 共用同一个 wire 形状；④ 是后端自己拍平的小形状。**只改后端不改这四处 = 白屏。**

### 1.4 报告链断在哪（真 bug，换源即修）

- `HistoryTab.tsx:123-136` 生成报告时递 `test_execution_ids: [record.id]`；
- 而 `record` 来自 `/test-executions` = **计划摘要行**，`record.id` 是 `TestPlanExecution` 主键；
- 收集器按 `TestExecution.id.in_(...)` 查（`report_data_collector.py:266-273`）；
- 两表主键各自随机 → **命中 0 行** → `collect()` 的第 3–10 步（执行摘要 / 测量 / 统计 /
  时间序列 / 异常检测 / 表格 / 图表）整段跳过（`report_data_collector.py:228-252`）。

现在**没有任何测试盯着这条路**（后端测试里引用 `/test-executions` 的只有
`test_arch1_case_runner.py` 的 cancel 端点）。换源后 `record.id` 天然就是 `TestExecution.id`，
断线自动接上 —— 但**必须配一条会红的门**，否则等于没证明（§4 的 G-c）。

### 1.5 5 相位链自己已经出过一份报告

REPORT 相位在执行末尾就建 `TestReport` + 生成 PDF，`content_data` 直接喂 `PDFGenerator`
（`executors/report.py:58-76`），**不走收集器**。它的标题写死：

```
MIMO OTA Test Report — Unknown Plan      # executors/report.py:62
plan_info["name"] = "Unknown Plan"       # executors/report.py:141
```

因为用例执行不挂计划，且 `execution.test_plan` 关系本身是注释掉的
（`models/test_plan.py:273-274`），两处 `getattr(execution, "test_plan", None)` 恒为 None。
所谓「无 plan 路径体面化」，落点就是这两行：名字换成**快照 TestCase 的名字**。

好消息：PDF 生成器对缺 plan 段是安全的（`pdf_generator.py:248` 有 `if data.get('test_plan')`，
`:356` 有 `test_plan_name = 'N/A'` 兜底）—— 不会因为没有计划就生成失败。

---

## 2. 目标形态

### 2.1 一张表、一个诚实的前缀

`GET /test-executions` 改查 `TestExecution`，谓词 **`mode IS NULL`**。

这个谓词不是新发明：VRT 自己的列表用 `mode IS NOT NULL` 圈自己的行
（`vrt_execution_service.py:117-118`），我们取它的镜像。VRT 有独立面板和独立历史，
不该在测试历史里重复出现。

### 2.2 新的列表项形状（字段名说真话）

| 字段 | 来源 | 说明 |
|---|---|---|
| `id` | `TestExecution.id` | **报告 `test_execution_ids` 引用的就是它** |
| `case_name` | 快照 `TestCase.name`（显式 join，关系是注释掉的） | 执行时的名字，已含 `[执行 时间戳]` 后缀 |
| `source_test_case_id` | `config.source_test_case_id` | 用例库据此把「执行中」徽标挂回原用例行 |
| `status` | `TestExecution.status` | running / completed / failed / cancelled |
| `phases_total` / `phases_done` / `phases_failed` | `config.step_descriptors` 的条数 + `config.phase_progress` 逐条计数 | 进度记录的实际形状是 `{"type": 相位名, "status": completed/failed}`（`test_case_runner.py:308-310`）；用例执行的"进度"单位是相位，不是步骤 |
| `duration_sec` | `TestExecution.duration_sec` | 秒，不再前端换算分钟后又乘回来 |
| `started_at` / `completed_at` | 同名列 | |
| `executed_by` | 同名列 | **来源列**：`test_case_runner` / `test_plan_runner` / `commissioning_api` / `commissioning_adhoc` |
| `error_message` | 同名列 | |
| `validation_pass` | 同名列 | 三态：True / False / None（未判定） |

**不再有** `test_plan_name` / `test_plan_version` / `total_steps` / `success_rate` ——
用例执行没有"计划版本"和"步骤"，硬塞只会造出新的名不副实（正是 ③ 现在那笔老账）。

### 2.3 消费方逐个换（改动都很薄）

| # | 改什么 | 备注 |
|---|---|---|
| ① 历史 Tab | 表头列换成：用例 / 状态 / 相位 / 时长 / 来源 / 时间；搜索改搜 `case_name` + `executed_by`；删除按钮**去掉**（见 §6 待决①）；详情弹窗展示相位逐条 | 单文件 |
| ② 待归档执行 | 表格字段改名；`TestPlanExecutionRecord` 类型改名为 `ExecutionRecord` 并换字段 | 与 ① 共用 `useReportGeneration`，一起改 |
| ③ 驾驶舱最近执行 | 卡片：成功率进度条 → 相位进度（`phases_done/phases_total`）；标题用 `case_name` | 单组件 |
| ④ 仪表盘最近测试 | **只换后端源**，wire 形状（id/name/dut/result/date）不变；`name` 取 `case_name` | 前端零改动 |

### 2.4 C3（导航丢 activeRun）用现成参数解决，**不加端点**

PR #237 的 Codex C3：用例库切走再切回来，`activeRun` 状态丢了 → 取消入口跟着丢，
只能等它跑完或杀后端。

修法：用例库挂载时查一次 **`GET /test-executions?status=running&limit=1`**，
拿 `source_test_case_id` 把「执行中（相位 n/5）」徽标和取消入口恢复出来。

- 零新增端点（`status` 参数现在就有）；
- 判据在 DB 不在进程内存 → **跨进程可见**，和 S1 的双判据同源；
- 与后端单飞 409 是两层：409 保证不会双跑，这条只是把入口找回来。

### 2.5 报告链

1. 历史行「生成报告」：换源后 `record.id` 就是执行行 id → 收集器真查得到（G-c 盯住）；
   标题 `${case_name} - 执行报告`。
2. REPORT 相位的两处 `Unknown Plan` → 快照 TestCase 名（`executors/report.py:62` / `:141`）。
3. 收集器无 plan 时的相位结果：`report_data_collector.py:245-246` 现在是
   `if report.test_plan_id: step_results = 查 TestStep`；补 else 分支，从
   `execution.config['phase_progress']` 派生（数据现成，约 15 行）。

---

## 3. 改动清单（文件级）

**后端 5 个文件**
- `app/api/test_execution.py` — 列表 / recent 换源 + 新 schema；detail、delete **不动**（S4 随 plan 遗物清）
- `app/schemas/test_plan.py` — 新增 `ExecutionHistoryItem` / `ExecutionHistoryListResponse`
- `app/services/report_data_collector.py` — 无 plan 时相位结果 else 分支
- `app/services/mimo_ota/executors/report.py` — 两处 `Unknown Plan` → 快照 case 名
- （只读核对，不改）`app/services/test_case_runner.py`

**前端 6 个文件**
- `features/TestManagement/components/HistoryTab/HistoryTab.tsx`
- `features/TestManagement/api/testManagementAPI.ts` + `types/index.ts`（`TestExecutionRecord` 换形）
- `features/Reports/components/PendingExecutionsList.tsx` + `hooks/useReportGeneration.ts`
- `features/Dashboard/ZoneActiveRun.tsx` + `types/api.ts`
- `components/TestPlanManagement/TestCaseLibrary.tsx`（§2.4 恢复 activeRun）
- `api/mockServer.ts` + `api/mockDatabase.ts`（契约 4 步的第 4 步）

**契约 2 个**：`api/openapi.yaml:298-330` 改 schema 引用 → `npm run openapi:generate`

**测试 1 个新文件**：`api-service/tests/test_arch1_history_resource.py`（§4 六道门）

净增净删：后端约 +120 / -40 行，前端约 +90 / -110 行，测试 +200 行左右。

---

## 4. 会红的门（每条配变异，实跑后才算数）

| 门 | 档 | 断言 | 让它红的变异 |
|---|---|---|---|
| **G-a** | 行为 | 造 1 行 case 执行 → 列表查得到，`case_name` = 快照名，`phases_done` 与 `phase_progress` 一致 | query 换回 `TestPlanExecution` → 空列表 → 红 |
| **G-b** | 行为 | VRT 行（`mode='digital_twin'`）**不出现**在列表 | 去掉 `mode IS NULL` → 红 |
| **G-c** | 行为 | 拿列表返回的 id 建报告 → 收集器查到 1 行执行且执行摘要非空 | 改传 `TestPlanExecution.id`（= 今天的实际行为）→ 摘要为空 → 红。**这条同时把"旧路是断的"钉成证据** |
| **G-d** | 行为 | `status=running` 查得到在跑的 case 执行且带 `source_test_case_id` | 去掉 status 过滤或不回填该字段 → 红 |
| **G-e** | 不变量 | openapi.yaml `components.schemas.TestExecutionItem`（`:804` 引用它）的属性集合 **==** Pydantic `ExecutionHistoryItem` 字段集合 | Pydantic 加一个字段不同步契约 → 红（把 memory 那条"契约 4 步"下沉成门） |
| **G-f** | 行为 | 无 plan 的执行生成报告，标题含 case 名且**不含** `Unknown Plan` | 还原 `executors/report.py` 的写死标题 → 红 |

外加 **GUI 两道门**（memory `feedback_gui_two_verification_gates`）：`npm run build` 真编译 +
浏览器实测「执行一个用例 → 历史 Tab 看到这行 → 点生成报告 → 报告页出现」。

---

## 5. 规则落点（memory 命中逐条对账）

1. **枚举影响集**（`whole_not_local`）：§1.3 的 4 个消费方 + §1.1 的 5 个写入方，
   都是先枚举后动手；VRT 写入方的存在直接决定了 §2.1 的谓词。
2. **验证打生效端**（`effective_end_not_nominal`）：G-c 不断言"传了 id"，断言
   **收集器真查到行且摘要非空**；G-f 不断言"代码里没有 Unknown Plan 字符串"，
   断言**生成出来的报告标题**。
3. **nullable 三态**（`value_form_space`）：现成的 `TestExecutionResponse`
   （`schemas/test_plan.py:214-219`）把 `test_plan_id` / `test_case_id` / `execution_order`
   声明成**必填**，而用例执行这三个字段是 NULL → 直接 500。**所以必须新建 schema，
   不能复用**。同理 `validation_pass` 是三态，前端别把 None 显示成"失败"。
4. **换形状必须换 queryKey**（`react_query_shape_change_needs_new_key`）：三个 key 全换 ——
   `['cockpit','executions']` / `['pending-test-plan-executions']` / `['test-management','history']`。
   不换的话，用户浏览器里存着旧形状的缓存，切过去当场崩（`?? []` 兜不住，旧值不是 null）。
5. **契约 4 步**（`api_contract_sync_after_pydantic_change`）：该端点**在** openapi.yaml 里
   （`:298`），不是无契约区 → openapi.yaml → generate → service.ts → mockServer，一步都不能少。
   G-e 就是这条的门。

---

## 6. 风险与明确不做

**风险**
1. 历史里会出现 **running 行**（以前只有终态）。这是 §2.4 的前提，也是好事，但 GUI 要有
   「进行中」样式，别让操作员以为是"没跑完的坏记录"。
2. 后端列表有个 `try/except` 把 DB 错误吞成空列表（`test_execution.py:113-121`）——
   换源出问题会表现成"历史一片空"而不是报错。**本片不改**（一次改一处），
   由 G-a 行为门兜住这种表现；吞异常本身记 backlog。
3. 报告有两个来源（相位自动出的、历史行手动出的），内容不同。本片只保证手动那条
   "生成成功且标题正确"；"已有报告则显示查看" 记 backlog。

**明确不做**（划走，不是忘了）
- `DELETE /test-executions/{id}` 与单条查询端点：留到 S4 跟 plan 遗物一起清；
- 旧计划历史的 GUI 可见性：按上游设计稿 §7 待决② 的已批准建议，**不再展示**（数据原地封存）；
- dashboard.py 的统计换源：属 S3；
- 分页从前端挪到后端、类型筛选下拉：backlog。

---

## 7. 待决（2026-07-27 用户"按照你的建议执行"——三条全按建议拍板）

**① 历史行的删除按钮 —— 建议：去掉。✅ 已拍板：去掉。**
换源后它指向的对象（计划摘要行）已经不展示了。而删执行行会连带毁掉报告的引用
（报告按 `test_execution_ids` 指过来）并留下孤儿快照用例。历史是报告的证据，
真要清理走脚本。备选：保留按钮 + 后端拦"已被报告引用的不许删"（多养一条判据）。

**② 暗室首测 / 单相位诊断的执行行要不要进历史 —— 建议：进，加「来源」列区分。✅ 已拍板：进。**
它们本来就是真执行（现场用过的那条链），藏起来反而让人以为没跑过。备选：只显示
`test_case_runner` 的行（历史更干净，但和"执行历史"这个名字不符）。

**③ `/test-executions/recent`（仪表盘「最近测试」卡片）要不要一并换源 —— 建议：一并换。✅ 已拍板：一并换（显式越界一小步获准）。**
它和主改动同文件同表，不换就会出现"驾驶舱的最近执行"和"仪表盘的最近测试"来自两张表、
互相矛盾。严格说 dashboard 换源属 S3，这一条我提前并进 S2，属于**显式越界一小步**，
请一并点头或否掉。
