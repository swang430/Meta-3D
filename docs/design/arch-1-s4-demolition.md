# ARCH-1 S4 设计稿 — 拆除计划链

> **状态**：设计稿，待 review，**尚未动代码**。
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

S4 是 ARCH-1 唯一的**纯删除**片：把计划链（路由 / runner / Service / GUI 两 Tab）整个摘掉。
本次盘点纠正了上游设计稿的**三处数字/事实错误**，其中一条会**直接搞崩 VRT 场景库**（§1.4）。

---

## 1. 盘点：上游设计稿要更正的三处

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

### 1.3 GUI 侧

PlansTab（439 行主文件 + 子组件）、QueueTab（521 行）、5 个死组件、`useSequenceLibrary`、
`App.tsx` 的 6 个执行控制 import。上游估 ~2400 行，本次未逐个复核（拆的时候按编译门走）。

### 1.4 ⚠️ 上游的致命错误：companion 过滤器**不能**跟着删

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

拆掉承载物之前，先问"这上面挂着的功能怎么办"。共 4 项：

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

### 2.4 队列 —— 零损失

`TestQueue.status` 全仓只写 `"queued"` 一个值，`dependencies`/`blocked_by` 零读取方，
没有后台 dispatcher（上游 §1.2 已查证）。删掉不损失任何在用功能。
"批量执行"作为将来的增量需求记 roadmap（上游 §6 已定：薄的 case_id 列表 + 逐个调 S1 入口，
**不复活 TestPlan 状态机**）。

---

## 3. 顺序与切分

S4 体量大（后端 ~2430 行 + GUI ~2400 行），**建议切三个 PR**，每个都能独立编译+测试通过：

| 片 | 内容 | 为什么这个顺序 |
|---|---|---|
| **S4a** | GUI 先行：删 PlansTab / QueueTab / 死组件 / useSequenceLibrary，清 `App.tsx` 6 个 import，StepsTab 改造为「用例配置」 | 前端不再调用 → 后端路由变成真死路由，后续删除零风险 |
| **S4b** | 后端路由 + Service：删 34 条路由、6 个 Service 类、`test_plan_runner.py`、scenario 桥、test_sequence 组 | 此时无调用方 |
| **S4c** | 收尾：模型标 deprecated、闸门删 TestPlan 半截、sequences_seeder 删、S2/S3 backlog 清理 | 依赖前两片 |

**S4a 必须先做**：反过来（先删后端）会让 GUI 在中间态白屏。

---

## 4. 会红的门

| 门 | 档 | 断言 | 变异 |
|---|---|---|---|
| **D-a** | 行为 | **VRT 场景库仍能列出且不含 companion**（造 3 条 companion 行 → `GET /road-test/scenarios` 200 且不含它们） | 删 companion 过滤器 → Pydantic ValidationError → 红（**§1.4 的致命错误专门防线**） |
| **D-b** | 不变量 | 全仓 grep：`TestPlan` 只出现在封存模型 + 历史查询，无活跃业务引用 | 漏删任一 Service/路由 → 红 |
| **D-c** | 行为 | 用例执行全链仍通（execute → 5 相位 → 历史 → 报告） | 误删 `TestCaseService` / cases 路由 → 红 |
| **D-d** | 行为 | HAL 闸门在拆掉 TestPlan 半截后仍拦住活跃执行 | 连带删错 `find_execution_blockers` → 红 |
| **D-e** | 结构 | G2 路由门（已有）自动验无双前缀残留 | — |
| **D-f** | 行为 | 删除的 34 条路由全部 404（逐条断言，防"删了 Service 忘删路由"） | 任一路由残留 → 红 |

外加 GUI 两道门：`npm run build` + 浏览器走完整闭环（这正是 S6 的预演）。

---

## 5. 风险

1. **外审当前不可用**：Codex 2026-07-28 起回 "To use Codex here, create an environment"
   （= review 未发生，见 memory 第六形态）。S4 是最大的一片，**外审缺席下拆 4800 行风险偏高**。
   建议：等 Codex 恢复再做 S4b/S4c，或至少 S4a 先行、后端拆除等外审回来。**待决③**。
2. **companion 存量 275 行**：§1.4，过滤器必须留。
3. **`App.tsx` 的 6 个执行控制 import**：上游 §5.3 标注的 fan-out 雷，S4a 逐个清。
4. **历史数据只读不删**：TestPlan / TestStep / TestQueue / TestPlanExecution 表原地封存
   （brownfield 两台机器的历史行），只标 deprecated docstring。

---

## 6. 待决

**① preflight 随 PlansTab 删掉，功能暂时消失？**
建议：删。留一个只能对已删除计划用的端点无意义；bring-up 的能力检查有
`device-selfcheck` 覆盖。case 级 preflight 需要新建数据源，单独立项。

**② topology-profile 搬到 `TestCase.configuration`，还是随计划删掉？**
建议：搬。它是仪表配置的一部分，而 TestCase.configuration 正是"仪表配置单一真值源"。
搬家成本 = 一个 configuration 字段 + case-runner start 路径消费。
备选：先删，需要时再从 TestCase 侧重做（现场没人用过这个覆盖的话）。

**③ 外审不可用期间要不要开拆？**
建议：**S4a（GUI）可以做** —— 编译门 + 浏览器门能兜住前端删除；
**S4b/S4c（后端 2430 行）等 Codex 恢复**。理由：后端删除的失败模式是"漏删导致死代码"或
"误删导致运行时崩"，agent 内审能抓前者，后者要靠外审的独立视角 + 全量测试。
备选：全部照做，agent 内审转正主审（limit 期既定规则），merge 后挂补扫。
