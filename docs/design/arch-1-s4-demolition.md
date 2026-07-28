# ARCH-1 S4 设计稿 — 拆除计划链

> **状态**：设计稿 **v2**（外审一轮后修订），三条待决已拍板，**尚未动代码**。
> **修订记录**：v1 → v2 由 Codex #243 两条 P1 打回 —— 我的枚举漏了 GUI 第二棵组件树
> （含一个**可达**的建计划入口）和后端 `test_plan_runner` 的两处活引用。详见 §1.3 / §1.4。
> **上游**：[`arch-1-testcase-first-simplification.md`](arch-1-testcase-first-simplification.md) §2.4 / §3 的 S4 行。
> **前置**：S1（`124d7e5`）/ S2（`3f66474` + 两轮迟到修复）/ S3a（`c4502dd`，HAL 闸门换源）全部 merged。
> **实证前置**：
> - memory 查询（恒适用）**命中 4 条**：`feedback_whole_not_local`（枚举影响集）/
>   `feedback_effective_end_not_nominal`（验证打生效端）/ `feedback_review_loop_scope_discipline`（修法优先级）/
>   `feedback_bulk_mutation_scope_and_restrict_fk`（删父行前 audit 外键）。
> - NotebookLM：**不适用**（纯架构拆除，零仪器 SCPI 语义）。
> **代码事实**：2026-07-28 盘点，行号以 main `c4502dd` 为准。

---

## 0. 一句话

S4 是 ARCH-1 唯一的**纯删除**片：把计划链（路由 / runner / Service / GUI 两棵组件树）整个摘掉。

盘点纠正了上游设计稿**三处数字/事实错误**，其中一条会**直接搞崩 VRT 场景库**（§1.5）；
外审又打回**两处我自己的漏枚举**，都是"删了承载物、活引用还在"（§1.3 / §1.4）。

**三次踩的是同一个坑**：拿"我列的清单"当"全部影响集"。所以 v2 的每条删除都带一个
**集合断言**（D-b / D-h）或**行为断言**（D-g / D-i），不靠清单本身正确。

---

## 1. 盘点：上游三处错误 + 外审打回的两处漏枚举

### 1.1 路由是 28 条不是 27 条，且分类不同

`/test-plans` 前缀下共 **36 条**（上游盘点时是 34，S1 加了 execute/status 两条）：

| 组 | 条数 | 去留 |
|---|---|---|
| cases CRUD | 6 | ✅ 保留 |
| cases 执行（S1 加的 execute / status） | 2 | ✅ 保留 |
| plan CRUD（POST "" / GET "" / GET,PATCH,DELETE /{id} / duplicate） | 6 | ❌ 删 |
| queue | 7 | ❌ 删 |
| steps | 6 | ❌ 删 |
| 执行控制（mark-ready / start / pause / resume / cancel / complete） | **6** | ❌ 删（上游写 5） |
| **`PUT /{id}/topology-profile`** | 1 | ❌ 删 — **上游完全没提，见 §2.2** |
| `POST /{id}/preflight` | 1 | ❌ 删（S3 外审移交，见 §2.1） |
| `GET /{id}/executions` | 1 | ❌ 删（S2 已换源到 `/test-executions`） |

**合计删 28 条**，另加 scenario 组 2 条（create-test-plan 桥）+ test_sequence 组 4 条 = **34 条**。

### 1.2 Service 层：7 个类 2128 行，只留 1 个

| 类 | 行数 | 外部引用 | 去留 |
|---|---|---|---|
| `TestPlanService` | 700 | `api/test_plan.py`、`api/scenario.py`（要删的桥）、`vrt_service.py`（**仅 docstring 引用**，非代码依赖） | ❌ 删 |
| **`TestCaseService`** | **88** | `api/test_plan.py` 的 cases 路由 | ✅ **保留**（cases 组唯一依赖） |
| `TestStepService` | 210 | 只有 `api/test_plan.py` | ❌ 删 |
| `TestQueueService` | 391 | 只有 `api/test_plan.py` | ❌ 删 |
| `TestExecutionService` | 529 | `api/test_plan.py` + `test_plan_runner.py`（都要删） | ❌ 删 |
| `TestSequenceService` | 57 | `api/test_sequence.py`（要删的 4 条路由） | ❌ 删 |
| `StatisticsService` | 131 | **零引用 —— 死代码**（`api/report.py` 用的是 `services/statistics_service.py` 里的**同名类**） | ❌ 删 |

净删约 **2040 行**（2128 − 88）。加 `test_plan_runner.py` 389 行 = **~2430 行后端**。

### 1.3 GUI 侧 —— 本轮外审（Codex #243 P1）打回后重做的枚举

初稿只写了「PlansTab + QueueTab + 6 个 App.tsx import，~2400 行，拆的时候按编译门走」。
**这是漏的**：GUI 的计划链有**两棵树**，初稿只数了一棵。

**树 A：`features/TestManagement/components/`**（初稿数过）—— PlansTab 439 + QueueTab 521 + 子组件。

**树 B：`components/TestPlanManagement/`**（初稿完全没出现，2884 行 8 文件）：

| 文件 | 行 | 可达性 | S4 处置 |
|---|---|---|---|
| `TestCaseLibrary.tsx` | 595 | **活**（`TestManagement.tsx:22`） | ✅ **保留** —— 用例库正是 case-first 的主体 |
| `TestCaseEditModal.tsx` | 220 | 活（被上者 import） | ✅ 保留 |
| `CreateTestPlanWizard.tsx` | 424 | **⚠️ 活且可达** | ❌ 删（见下） |
| `TestPlanManagement.tsx` | 113 | **死**（零外部 import） | ❌ 删 |
| `TestPlanList.tsx` | 424 | 死（仅被上者 import） | ❌ 删 |
| `EditTestPlanWizard.tsx` | 496 | 死（同上，与树 A 同名文件是**两份副本**） | ❌ 删 |
| `TestQueue.tsx` | 313 | 死 | ❌ 删 |
| `TestExecutionHistory.tsx` | 299 | 死 | ❌ 删 |

删 **2069 行**、留 815 行。

**⚠️ `CreateTestPlanWizard` 是初稿最危险的漏项** —— 它不在 PlansTab 里，删 PlansTab 碰不到它：

- `TestManagement.tsx:60-66` 渲染「**新建测试计划 (N)**」按钮（用例库选中 ≥1 条即出现）
- `TestManagement.tsx:130-137` 渲染 wizard，`onCreated` 回调还 `setActiveTab('plans')`
- wizard 内部 `createTestPlan()` → `POST /test-plans`，随后 `mark-ready`

只删 PlansTab 而留这条：S4b 删掉路由后，用户**照样能点开这个 wizard**，提交时拿一个
"设计上就该 404" 的失败。**编译门和 happy-path 浏览器门都抓不到**（前者语法合法，
后者根本不会去点一个"应该已经没有的按钮"）。所以 S4a 必须连按钮 + wizard + `'plans'`
跳转一起清，并配**否定式**浏览器门（见 §4 D-h）。

**`App.tsx` 远不止 6 个 import**：全文 4800 行里 **143 行**触及 `Plan` ——
`executingPlanInfo` / `executingPlanDetail` 两个 state、`syncPlanSummary`、
`_mutatePlanStatus`、pause/stop/resume 三个 handler 各带 `executingPlanInfo` 分支、
demo-run 完成后的报告快照（805/813 行读 `executingPlanDetail.caseName`）、
`activePlan` 队列恢复（884-893）。**这些是 S4a 的主要工作量，不是顺手 6 行。**

### 1.4 ⚠️ 后端：`test_plan_runner` 有活引用，不是"无调用方"（Codex #243 P1）

初稿 §3 写 S4b 时把 `test_plan_runner.py` 当"此时无调用方"直接删。**错的** ——
S1 建的用例执行正门**当场就依赖它**：

| 引用点 | 内容 | 删了会怎样 |
|---|---|---|
| `test_case_runner.py:69` | `_active_conflict()` 里动态 `from app.services.test_plan_runner import has_active_runner` | **每一次用例执行**都会 `ModuleNotFoundError`，执行行都没建出来就炸 |
| `main.py:70` | 启动期 `reset_stale_running_plans()` | 启动日志刷 warning（有 try/except 兜着，不致命） |
| `api/test_plan.py:1053/1123/1247/1309` | 计划路由自己用 | 与路由同批删，无残留 |
| `tests/test_arch1_case_runner.py:232` | `test_plan_runner_mutex` 测双向单飞 | 测试 import 失败 |
| `tests/test_test_plan_runner.py` | 整个文件 | 与模块同批删 |

**正确顺序：S4b 先解耦，再删模块。** 具体：

1. `_active_conflict()` 删掉计划分支 —— 计划 runner 从此不存在，这个分支恒为 `None`。
   **保留**的是 case-vs-case 单飞（`has_active_case_run`）+ DB dangling 双判据，这两条
   才是真正在防重入的，不受影响。同步删 `test_plan_runner_mutex` 测试。
2. `main.py` 删掉 `reset_stale_running_plans` 调用；case-runner 和 commissioning 两个
   复位**保留**（各自复位自己 `executed_by` 的行，S1/S3a 已建）。

**⚠️ 由此牵出一条 Codex 没说的后果 —— brownfield 会永久卡死 HAL 重载：**

`reset_stale_running_plans` 在 S2 里被我扩过，它同时复位 `executed_by='test_plan_runner'`
的 running 执行行。而 S3a 的 HAL 闸门看的是**所有** running 执行行（不按 `executed_by`
过滤）。两台现场机器的库里若留着一条 `test_plan_runner` 的僵尸 running 行，
删掉复位函数后**再没有任何东西会清它**，HAL 重载就被这条死行永久 409 拦住。

处置：S4b 加一次性清理 —— 要么迁移把存量 `executed_by='test_plan_runner' AND
status='running'` 置 `failed`，要么在 case-runner 的启动复位里把这个 marker 一并纳入。
**倾向后者**（不加迁移文件，复位函数本来就在做这件事，只是扩一个 marker）。配门 D-i。

### 1.5 ⚠️ 上游的致命错误：companion 过滤器**不能**跟着删

上游 §2.4 写："连带作废 `_create_road_test_steps` + companion-TestCase 过滤器
（P3-8 那套补丁整个消失）"。

**这条会搞崩 VRT 场景库。** 实测当前库：

```
TestCase 总数: 538
其中 companion 占位行 (auto_generated + scenario_id): 275   ← 超过一半
```

这些行是历史上 scenario→plan 桥创建的 FK 占位符，`configuration` 只有
`{auto_generated, scenario_id, steps_count}`，**不满足 `VirtualRoadTestConfig` schema**。
`vrt_service.py:35-50` 的过滤器就是拦它们的 —— 一旦删掉，
`vrt_test_case_to_scenario` 会对这 275 行抛 Pydantic `ValidationError`（P3-8 原始故障重现）。

**过滤器保护的是存量数据，不只是新产生的数据。** 正确处置：

| 对象 | S4 处置 |
|---|---|
| `TestPlanService._create_road_test_steps`（产生方） | ❌ 删 —— 不再产生新 companion |
| `vrt_service.py` 的 companion 过滤器（防护方） | ✅ **保留** —— 275 行存量还在库里 |
| 存量 275 行本身 | 留在库里（与 TestPlanExecution 历史行同策：不迁移不删除），过滤器负责隐身 |

若将来要清掉过滤器，得先有一次性数据清理迁移 —— 那是独立工单，不进 S4。

---

## 2. 挂在计划上的功能：逐个决定去留

拆掉承载物之前，先问"这上面挂着的功能怎么办"。共 **5 项**（第 5 项 §2.4 是 v2 补查出来的 ——
初稿只列了 4 项，又是同一个漏枚举的毛病）：

### 2.1 preflight（S3 外审 Codex #241 C2 移交）

`POST /{plan_id}/preflight` + `validate_plan()` + PlansTab 里的 `PreflightModal`。

case 级 preflight **今天做不了**：能力需求只活在 `TestStep.needs`（顶层列，模型注释明写
它是 *step-template 契约、不是用户可配参数*），而 `TestCase.configuration`
（`MIMOOTAConfiguration`）里**没有任何能力 token 字段**。要做得先建
"相位/模板 → 能力"映射或 TestCase 需求快照 —— **加机制，单独出设计稿**。

**S4 处置：随 PlansTab 一起删掉**，功能暂时消失。理由：留一个只能对已删除的计划用的
端点毫无意义；而 bring-up 的能力检查另有 `POST /commissioning/device-selfcheck` 覆盖
（逐设备探连接+响应）。**待决①**。

### 2.2 topology-profile（本次盘点新发现，上游完全没提）

`PUT /{plan_id}/topology-profile`（`test_plan.py:1155`）：持久化操作员的**计划级 UXM 拓扑覆盖**，
在 `POST /{id}/start` 里 best-effort 应用到 baseStation 驱动。GUI 入口在
`EditTestPlanWizard.tsx:69`（PlansTab 内，要删）。

计划没了，这个"计划级覆盖"就没有承载物。但**功能本身对用例执行同样有意义**
（P2-1 Phase 2.3 引入，用于覆盖 UXM 拓扑）。

**S4 处置建议：搬到 `TestCase.configuration`** —— 它本来就是"仪表配置单一真值源"
（P0-2 / `project_testcase_driven_instrument_arch`），拓扑覆盖属于仪表配置的一部分。
搬家 = 加一个 configuration 字段 + case-runner 的 start 路径消费它。**待决②**。

备选：随计划一起删，需要时再从 TestCase 侧重做。

### 2.3 pause / resume —— **有意删减，不是遗漏**

计划链有 `POST /{id}/pause` + `/resume`；用例执行链**只有 cancel**。
这是 S1 设计稿 §2.3 明确写的取舍（"不做 pause/resume（拍板：状态机简化）"），
用户 2026-07-21 现场拍板。S4 只是让它成为既成事实。**本设计稿显式声明，不列为待决。**

### 2.4 演示回放（demo-run）—— 第 5 项，v2 补查，**无功能损失**

初稿 §2 只列了 4 项。写 v2 时按 §5.3 自己留的话（"拆之前要先确认 demo-run 这条链改读什么"）
去查，发现 **App.tsx 的演示回放跟计划链缠在一起**，构成第 5 项。查清后的结论是可以放心删。

演示回放有**两个入口**，只有一个挂在计划上：

| 入口 | 链路 | S4a 之后 |
|---|---|---|
| **直接播放**（调试维护 → 监控 tab） | `handleDemoRunStart()` 读 `fetchDemoRunPlan` 的演示夹具（**不是 TestPlan 行**） | ✅ **活着**，零改动 |
| **计划触发**（QueueTab 点执行 → 仪表盘看进度） | `QueueTab.tsx:153/194` emit `execution:start` → `App.tsx:726` 监听 → `startPlanExecution(plan)` 调 `apiStartExecution(plan.id)` | ❌ 随 QueueTab 一起死（**有意**） |

播放器本体仍内联在 `App.tsx`，通过 `monitoringSlot` 渲染进 `DiagnosticsPage`（P2-8 搬的），
这部分不受影响。

**S4a 之后变成不可达、要一并删的**：`execution:start` 的**唯一** emitter 是 QueueTab
（`App.tsx:675` 那处 emit 被 `executingPlanInfo` 守着，而它只由监听器自己写 —— 自环，
QueueTab 一删就永远进不去）。连带死掉：`executingPlanInfo` / `executingPlanDetail` /
`startPlanExecution` / `syncPlanSummary` / `_mutatePlanStatus` / pause·stop·resume 三个
handler 里的计划分支。

**`liveHistory` 会永久空 —— 但这不是损失**：它在 `App.tsx:4395` 跟 `apiEntries` 合并成
历史视图。S4a 后没人再写 `liveHistory`，视图退化为只读 `apiEntries` ——
而 S2 之后 `apiEntries` 正是 `test_executions` 这个**权威源**。等于把一个演示时代的
客户端内存补充列表去掉，留下真数据。**S4a 顺手删 `liveHistory` state 及其合并逻辑。**

### 2.5 队列 —— 零损失

`TestQueue.status` 全仓只写 `"queued"` 一个值，`dependencies`/`blocked_by` 零读取方，
没有后台 dispatcher（上游 §1.2 已查证）。删掉不损失任何在用功能。
"批量执行"作为将来的增量需求记 roadmap（上游 §6 已定：薄的 case_id 列表 + 逐个调 S1 入口，
**不复活 TestPlan 状态机**）。

---

## 3. 顺序与切分

S4 体量大（后端 ~2430 行 + GUI ~4500 行），**切三个 PR**，每个都能独立编译+测试通过：

| 片 | 内容 | 为什么这个顺序 |
|---|---|---|
| **S4a** | GUI 全清：树 A（PlansTab / QueueTab / useSequenceLibrary）**+ 树 B 的 6 个文件**（§1.3）**+ `TestManagement.tsx` 的「新建测试计划」按钮 / wizard / `'plans'` 跳转** + `App.tsx` 143 处 Plan 面（含 §2.4 列的演示回放计划分支 + `liveHistory`），StepsTab 改造为「用例配置」 | 前端不再调用 → 后端路由变成真死路由，后续删除零风险 |
| **S4b** | 后端：**先解耦**（§1.4 两处 + 僵尸行复位扩 marker），**再**删 34 条路由、6 个 Service 类、`test_plan_runner.py`、scenario 桥、test_sequence 组 | 此时前端无调用方；解耦必须排在删模块之前 |
| **S4c** | 收尾：模型标 deprecated、闸门删 TestPlan 半截、sequences_seeder 删、S2/S3 backlog 清理 | 依赖前两片 |

**S4a 必须先做**：反过来（先删后端）会让 GUI 在中间态白屏。

**S4b 内部还有一层顺序**：§1.4 的解耦（`_active_conflict` 去计划分支、`main.py` 去复位调用、
僵尸行 marker 扩容）必须是**同一个 PR 里的第一批 commit**，删模块排在后面。
中间态若先删模块，用例执行正门直接 `ModuleNotFoundError`。

---

## 4. 会红的门

| 门 | 档 | 断言 | 变异 |
|---|---|---|---|
| **D-a** | 行为 | **VRT 场景库仍能列出且不含 companion**（造 3 条 companion 行 → `GET /road-test/scenarios` 200 且不含它们） | 删 companion 过滤器 → Pydantic ValidationError → 红（**§1.5 的致命错误专门防线**） |
| **D-b** | 不变量 | 全仓 grep：`TestPlan` 只出现在封存模型 + 历史查询，无活跃业务引用 | 漏删任一 Service/路由 → 红 |
| **D-c** | 行为 | 用例执行全链仍通（execute → 5 相位 → 历史 → 报告） | 误删 `TestCaseService` / cases 路由 → 红 |
| **D-d** | 行为 | HAL 闸门在拆掉 TestPlan 半截后仍拦住活跃执行 | 连带删错 `find_execution_blockers` → 红 |
| **D-e** | 结构 | G2 路由门（已有）自动验无双前缀残留 | — |
| **D-f** | 行为 | 删除的 34 条路由全部 404（逐条断言，防"删了 Service 忘删路由"） | 任一路由残留 → 红 |
| **D-g** | 行为 | **`test_case_runner` 不 import `test_plan_runner` 也能跑完一次执行**（S4b 解耦后跑真实 execute，断言 200 + 执行行落库） | 保留 `_active_conflict` 的计划分支 → `ModuleNotFoundError` → 红（**§1.4 Codex P1 专防**） |
| **D-h** | 不变量 | **全 GUI grep：无任何组件调 `createTestPlan` / `POST /test-plans`**（源码级集合断言，不是浏览器点击） | 漏删 `CreateTestPlanWizard` 或 `TestManagement.tsx` 的按钮 → 红（**§1.3 最危险漏项专防**） |
| **D-i** | 行为 | **legacy 僵尸行不卡 HAL 重载**：造一条 `executed_by='test_plan_runner', status='running'` 的行 → 跑启动复位 → HAL 重载不被 409 拦 | 复位函数不扩 marker → 409 → 红（**§1.4 brownfield 后果专防**） |

外加 GUI 两道门：`npm run build` + 浏览器闭环。

⚠️ **浏览器门必须含否定式检查**，不能只走 happy path：进用例库、勾选 ≥1 条用例，
**断言「新建测试计划」按钮不出现**。Codex 说得对 —— happy-path 走查不会去点一个
"本来就该没有的按钮"，而这正是 §1.3 漏项唯一能被人眼抓到的地方。

---

## 5. 风险

1. ~~**外审当前不可用**~~ **→ 已解除**。初稿写 Codex 回 "create an environment"（= review
   未发生）。**本 PR 自己就是反证**：Codex 2026-07-28 12:15:52Z 正常出了 review，抓到
   2 条 P1（§1.3 / §1.4 两处漏枚举，均已坐实并改稿）。外审通道恢复，三片都按正常流程走。
2. **companion 存量 275 行**：§1.5，过滤器必须留。
3. **`App.tsx` 的计划面是 143 行不是 6 个 import**：初稿严重低估（§1.3）。这是 S4a 的主要
   工作量 —— 三个 execution handler 各有 `executingPlanInfo` 分支、demo-run 报告快照读
   `executingPlanDetail.caseName`、队列恢复找 `activePlan`。
   ~~拆之前要先确认 demo-run 这条链改读什么~~ **→ 已查清，见 §2.4**：演示回放的直接入口
   不依赖计划，活着；计划触发那条随 QueueTab 死掉是有意的；`liveHistory` 退回只读
   `test_executions` 权威源，无损失。
4. **历史数据只读不删**：TestPlan / TestStep / TestQueue / TestPlanExecution 表原地封存
   （brownfield 两台机器的历史行），只标 deprecated docstring。
5. **brownfield 僵尸行卡死 HAL 重载**：§1.4 末尾，门 D-i 专防。

---

## 6. 待决 —— 2026-07-28 已全部拍板

**① preflight 随 PlansTab 删掉，功能暂时消失？→ ✅ 删。**
留一个只能对已删除计划用的端点无意义；bring-up 的能力检查有 `device-selfcheck` 覆盖
（逐设备探连接+响应）。case 级 preflight 需要新建"相位/模板 → 能力"数据源，
**单独立项**，进 roadmap backlog，不进 S4。

**② topology-profile 搬到 `TestCase.configuration`，还是随计划删掉？→ ✅ 搬。**
它是仪表配置的一部分，而 `TestCase.configuration` 正是"仪表配置单一真值源"
（P0-2 / `project_testcase_driven_instrument_arch`）。搬家成本 = 一个 configuration
字段 + case-runner start 路径消费。**在 S4b 里做**（与删路由同批，避免中间态功能真空）。

**③ 外审不可用期间要不要开拆？→ ✅ 三片全做，条件已满足。**
原建议是"S4a 先行，S4b/S4c 等 Codex 恢复"。**Codex 已在本 PR 上恢复**（§5.1），
条件达成 —— 三片各自走完整流程：agent 内审 → PR → `@codex review` 显式触发 →
270s 四通道查 → 修复后**再显式触发**（推 commit 不触发外审）→ merge → 迟到回查。
