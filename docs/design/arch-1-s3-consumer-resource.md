# ARCH-1 S3 设计稿 — 消费方换源（HAL reload 闸门 / dashboard / preflight）

> **状态**：设计稿，待 review，**尚未动代码**。
> **上游**：[`arch-1-testcase-first-simplification.md`](arch-1-testcase-first-simplification.md) §3 的 S3 行 + §5.1 顺序纪律。
> **实证前置**：
> - memory 查询（恒适用）**命中 3 条**：`feedback_whole_not_local`（枚举影响集）/
>   `feedback_effective_end_not_nominal`（验证打生效端）/ `feedback_review_loop_scope_discipline`（修法优先级）。
> - NotebookLM：**不适用**（HAL 重载策略是进程内驱动生命周期，不涉及 UXM/F64 的 SCPI 语义）。
> **代码事实**：2026-07-28 盘点，行号以 main `806b2b9` 为准。

---

## 0. 一句话

上游设计稿把 S3 定性成"为 S4 拆表做准备的顺序纪律"。**盘点后要更正这个定性**：
HAL reload 闸门只认 `TestPlan.status`，而 S1 的用例直接执行**根本不写 TestPlan** ——
**这个保护空窗从 S1 上线那天（`124d7e5`）就已经存在，不是 S4 才会出现的风险**。
现在跑着用例点一下「重载驱动」，驱动会被拆掉、执行链当场崩，而闸门一声不吭。
S3 因此从"预防性换源"升级为"修一个已在生产的洞"。

---

## 1. 现状地图

### 1.1 闸门只看得见计划链（真实空窗）

`hal_reload_policy.py:78-89`：

```python
BLOCKING_TEST_PLAN_STATUSES = (RUNNING, PAUSED)
plans = db.query(TestPlan).filter(TestPlan.status.in_(BLOCKING_TEST_PLAN_STATUSES))
```

`find_reload_blockers()`（`:105-108`）今天只聚合这一个来源，注释自己写着
"future extensions land here"。调用点：`instrument.py:371-395`（`POST /instruments/hal/reload`
的拒绝臂，`force=true` 可绕过）。

**谁在保护圈外**：

**枚举维度要选对**（Codex #241 C1/C3 纠正）：第一版我枚举的是"**建 TestExecution 行**的地方"
（4 处建行），但闸门要的是"**占着 HAL 驱动**的地方"—— 两个集合不一样。按后者重新枚举
（= `dispatch_step` 的调用方 + VRT 的硬件模式）：

| 执行入口 | 跑起来时行的 `status` | 占 HAL？ | 写 TestPlan？ | 闸门看得见？ |
|---|---|---|---|---|
| case-runner（S1 正门） | `running`（`test_case_runner.py:142`） | 是 | **否** | **✗ 空窗** |
| plan-runner 每步 | `running`（`test_plan_runner.py:287`） | 是 | 是 | ✓（靠 plan 那条） |
| **commissioning run-all（暗室首测）** | **`pending`**（建行 `commissioning.py:374`，全程不改） | 是 | 否 | **✗ 空窗** |
| **commissioning run_phase（单相位，GUI 有入口）** | **`pending`**（`commissioning.py` run_phase 段**无任何 status 写入**） | 是 | 否 | **✗ 空窗** |
| commissioning adhoc（诊断单相位） | `pending` → 终态（S2 #239 补的收尾） | 是 | 否 | **✗ 空窗** |
| **VRT digital_twin** | `running`（`vrt_execution_service.py:154-160`） | **否（纯仿真）** | 否 | **⚠ 会被误拦** |

- 中间三行是**现场真正在用的链**（07-03 / 07-21 两次现场都走它），一样裸奔。
- 最后一行是反方向的错：`status == "running"` 裸判据会让一个纯数字仿真把无关的 HAL
  reload 拦住一整段时间。**S2 给历史列表加过 `mode IS NULL` 排除 VRT，这里是同一个母题
  第二次出现** —— 判据必须带 `mode IS NULL`。

### 1.2 dashboard 的两个数字都只数计划

`dashboard.py:44-47` 与 `:184-187`（两处重复）：
- `active_test_plans` = `TestPlan.status ∈ (RUNNING, QUEUED)` → 用例执行不计
- `total_executions` = `TestPlanExecution.count()` → 用例执行不计
- `recent_executions`（`:75-76`）= `TestPlanExecution` 排序 → 用例执行不出现

（注：`/test-executions/recent` 那个卡片 S2 已换源，本节说的是 dashboard.py 自己这三处。）

### 1.3 preflight 是计划形状，且 S4 后会失去入口

- `validate_plan(plan, lab, db, hal_drivers)`（`preflight.py:434`）迭代
  `TestStep`（`:502-505`）产出 gap 列表；
- 端点 `POST /test-plans/{id}/preflight`（`test_plan.py:736-775`）；
- GUI 入口 `PreflightModal` 挂在 **PlansTab**（`TestPlanList.tsx:430-433`）——
  **那个 Tab 正是 S4 要砍的**。所以 preflight 不只是换源，还要重新安家。

---

## 2. 目标形态

### 2.1 闸门：并集，不是替换（零空窗的关键）

```
blockers = 占 HAL 的活跃执行行  ∪  TestPlan ∈ (RUNNING, PAUSED)

占 HAL 的活跃执行行 = TestExecution.status == "running"
                     AND TestExecution.mode IS DISTINCT FROM "digital_twin"
                         ← 只排"纯仿真"这一种, 不排整个 VRT (D1)
```

**判据是"占不占 HAL"，不是"是不是 VRT"**（Codex #241 D1 纠正我上一轮修过头）：

| mode | 含义 | 占 HAL？ | 该拦 reload？ |
|---|---|---|---|
| `NULL` | 非 VRT（用例 / 计划 / 暗室首测 / 诊断） | 是 | ✓ |
| `digital_twin` | 纯数字仿真 | **否** | ✗ 排除 |
| `conducted` | 传导，**需要拓扑**（`road_test.py:546,556-559` 强制 topology_id） | **是** | ✓ |
| `ota` | 走 MPAC 暗室 | **是** | ✓ |

上一轮我照搬 S2 历史列表的 `mode IS NULL`，等于把 conducted / ota 这两种**真硬件 VRT**
也放过 —— 硬件路测跑着时 reload 照样拆驱动。**同一个谓词不能跨语义复制**：
历史列表要的是"非 VRT"（VRT 有独立面板），闸门要的是"占 HAL"，两者只是碰巧在
`digital_twin` 上重合。SQLite 无 `IS DISTINCT FROM`，实现用
`or_(mode.is_(None), mode != "digital_twin")`。

**为什么是并集而不是"改查 TestExecution"**（上游设计稿原话是"改查"，这里要修正）：
计划在 **PAUSED** 时步骤间没有任何 running 的执行行，但驱动状态仍被持有
（`hal_reload_policy.py:76-80` 的原注释讲得很清楚：暂停期间 reload 会让 corruption
在 resume 时才爆出来）。直接换源 = 暂停的计划失去保护 —— **保护退化**。
plan 那半截等 S4 拆掉计划链时随之删除，那时它自然变成纯 TestExecution 判据。

`ReloadBlocker.kind` 现在是 `"test_plan"`，新增 `"test_execution"`（该字段本来就是为
多来源留的）。

### 2.2 "活跃"的判据 —— 这是本片唯一的真难点

`status == "running"` 只覆盖 case-runner 和 plan-runner。commissioning 两条链的行
一直是 `pending`，而 `pending` **不能进闸门**：历史僵尸 pending 行（S2 内审 F6 记录在案）
一多，reload 会被永久拦死。

**建议：先让 commissioning 如实写 running，再让闸门只认 running。**

| 改动 | 位置 | 说明 |
|---|---|---|
| run-all 开跑置 `running`，收尾落终态 | `commissioning.py` run_all_phases | 顺带清掉 S2 backlog F6 的一半（run-all 僵尸 pending 行） |
| **run_phase 开跑置 `running`，收尾落终态** | `commissioning.py` run_phase | **Codex #241 C1 抓的漏网**：GUI 有入口、跑真硬件相位、全段无 status 写入 |
| adhoc 开跑置 `running` | `commissioning.py` run_adhoc_phase | 收尾已在 S2 #239 补过，只差开跑这一下 |

三处是同一个形状（开跑置 running / 收尾落终态），实现时抽一个 helper，避免第四条链
将来又漏 —— 漏一条 = 那条链继续裸奔，而且是静默的。

这**超出了上游设计稿写的 S3 范围**（它只说"闸门改查活跃 TestExecution"），但不做的话
闸门对现场真用的那条链依然是空的 —— 等于修了一半。**待决①请拍板。**

### 2.3 dashboard：数字换源

| 字段 | 现在 | 换成 |
|---|---|---|
| `active_test_plans` | 计划 RUNNING/QUEUED 数 | 活跃执行数（与闸门同谓词） |
| `total_executions` | `TestPlanExecution.count()` **+ VRT 计数**（`:49-53` 显式加上） | `TestExecution` **全表**计数（VRT 含在内，见下） |
| `recent_executions` | `TestPlanExecution` 排序 **+ VRT 合并**（`:90-95`） | `TestExecution` **全表**排序（VRT 天然在内） |

**dashboard 不能套 S2 的"非 VRT"谓词**（Codex #241 D2 纠正）：dashboard 今天是
**明确合并展示两类**的 —— `:49-53` 把 `vrt_execution_service.list()` 加进 `total_executions`，
`:90-95` 把 VRT 行并进 `recent_tests`。照搬 `mode IS NULL` 会让 VRT 执行**从总览里消失**，
是功能退化。总览查全表反而更简单：换源后 VRT 行本来就在同一张表里，**那两段"额外加 VRT"
的代码可以一并删掉**（去掉 > 换源）。

三个场景三种谓词，别再互相复制：

| 场景 | 谓词 | 理由 |
|---|---|---|
| 执行历史列表（S2） | `mode IS NULL` | VRT 有独立面板，避免重复展示 |
| HAL reload 闸门（S3a） | `mode != "digital_twin"` | 判据是"占不占 HAL" |
| dashboard 总览（S3b） | **无 mode 过滤** | 总览本来就合并展示 |

两处重复代码（`:44` 与 `:184`）合并成一个 helper —— 属于本次换源的直接连带。

### 2.4 preflight：**本片不做，整体推到 S4**（第一版方案是错的）

第一版我写的是"needs 从 `TestCase.configuration` 派生"。**这个数据源不存在**
（Codex #241 C2，已核实）：

- 能力需求只活在 `TestStep.needs`（顶层列），模型注释白纸黑字写着它是
  **step-template 契约、不是用户可配的执行参数**，"混进 parameters 会搅乱 schema"
  （`test_plan.py:391-401`）；
- `MIMOOTAConfiguration`（即 `TestCase.configuration` 的内容）里**没有任何能力 token
  字段** —— 只有 `precheck_strict_dut_capability` 这类开关，那是门的开关不是需求集；
- 所以照第一版实现出来会得到**空需求集 → 永远 ready** —— H-g 门变成恒真断言，
  比不做还危险（给操作员一个假的"已就绪"）。

要真做 case 级 preflight，得先**建一个今天不存在的东西**：或者定义并持久化
"相位/模板 → 能力 token"的映射，或者给 TestCase 加一个需求快照字段。两条路都是
**加机制**，按修法优先级（去掉 > 换源 > 收窄 > 加机制）不该塞进一个换源片里。

**处置**：S3 完全不碰 preflight，plan 版 `validate_plan` + 端点 + PlansTab 里的
`PreflightModal` 原样留着。它们跟 PlansTab 一起活到 S4 —— 那时计划链拆除，preflight
必须重新安家，**连同"能力需求从哪来"一起单独设计**（届时是新增功能，配得上一个
自己的设计稿）。

---

## 3. 切分（建议拆两片 PR，因为紧急度不同）

| 片 | 内容 | 为什么单独 |
|---|---|---|
| **S3a（急）** | 闸门并集（含 `mode IS NULL`）+ commissioning 三个入口如实写 running + 启动复位 | 这是**在修生产空窗**，越快 merge 越好；纯后端、门清晰 |
| **S3b** | dashboard 三处数字换源 | 显示准确性，不带紧急性；纯后端小改 |
| ~~preflight~~ | — | **移出 S3**，随 PlansTab 活到 S4，届时连同"能力需求从哪来"单独设计（§2.4） |

preflight 移出后，S3 变成一片纯后端工作，**没有 GUI 改动** —— 浏览器门只需要验证
"跑着用例时点重载被拒"这一个闭环。若你希望一个 PR 收，S3a+S3b 合并也可以（都是后端）。

---

## 4. 会红的门（每条配变异）

| 门 | 档 | 断言 | 变异 |
|---|---|---|---|
| **H-a** | 行为 | 有 case-runner 的 running 行时 `POST /instruments/hal/reload` 返回拒绝 + blocker.kind == "test_execution" | 砍执行行判据 → 放行 → 红（**这条就是今天的实况**，钉死空窗存在过） |
| **H-b** | 行为 | 计划 PAUSED（无 running 执行行）仍被拒 | 把并集改成"只查 TestExecution" → 放行 → 红（防退化） |
| **H-c** | 行为 | commissioning **三个入口各自**跑到一半时被拒（run-all / run_phase / adhoc 参数化同一条门） | 逐个砍其 running 写入 → 放行 → 各红（C1 抓的 run_phase 在内） |
| **H-d** | 不变量 | 历史 pending 僵尸行**不**成为 blocker（造 50 条 pending → reload 放行） | 闸门谓词误写成 `status != completed` → 红 |
| **H-e** | 行为 | `force=true` 仍能绕过（既有语义不许变） | — |
| **H-f** | 行为 | **VRT digital_twin 的 running 行不拦** reload（C3） | 谓词写成"排除全部 VRT"以外的任何形态 → 纯仿真拦住 → 红 |
| **H-g** | 行为 | **VRT conducted / ota 的 running 行照样拦** reload（D1，两种模式各一条） | 砍成 `mode IS NULL` → 硬件路测跑着时放行 → 红（**这就是我上一轮的错版**） |
| **H-h** | 行为 | dashboard 活跃数 = 活跃执行数（造 1 条 running case 行 → 数字为 1） | 换回 TestPlan 查询 → 红 |
| **H-i** | 行为 | **dashboard 总数/最近列表里仍有 VRT 行**（D2，防换源丢功能） | 给 dashboard 套上 `mode IS NULL` → VRT 消失 → 红 |

外加 `npm run build`（GUI 无改动，仅回归）+ 浏览器实测一个闭环：**跑着用例点「重载驱动」→
被拒 + 拒绝文案指出是哪条执行**。

~~原 H-g（case 级 preflight）~~ 随 §2.4 一并移出 S3 —— 它在错误前提上写的门，
留着只会给出假的"已就绪"。

---

## 5. 风险

1. **闸门变严会不会挡住正常操作**：会。现在跑着用例就不能重载驱动了 —— 这正是想要的
   （原本就该拦），但要确认拒绝文案说清"哪条执行在跑、去哪取消"。`force=true` 保留。
2. **stale running 行会把 reload 永久拦死**：case-runner 有启动复位（S1），plan-runner
   **没有**（S2 迟到 C-3 查证过：`reset_stale_running_plans` 只碰 plan+steps 不碰执行行）。
   commissioning 改成写 running 后同样需要复位。→ **待决②**。
3. **dashboard 数字会变**：活跃数与总数的口径改了，历史曲线不连续（可接受，本来就在换源）。

---

## 6. 待决（需要点头）

**① commissioning **三个**入口要不要在本片改成如实写 `running` —— 建议：要。**
（第一版写的是"两条链"，Codex C1 抓出还有 `run_phase` 这条 GUI 可点的硬件入口，已补齐。）
不改的话闸门对现场真用的链依然是空的（等于修一半），且它顺带清掉 S2 backlog 里
run-all 的僵尸 pending 行。代价：超出上游设计稿给 S3 划的范围，动 commissioning 文件。
备选：只修 case-runner 那条空窗，commissioning 的记 backlog 留 S4 —— 但那意味着
**现场最常用的链在 S4 之前一直裸奔**。

**② 启动残留复位要不要在本片补齐三条链 —— 建议：要，但只补"复位"不补别的。**
闸门变严之后，任何没被复位的 stale running 行都会把 reload 永久拦死（比今天的空窗
更难受）。case-runner 已有复位；plan-runner 与 commissioning 需要同构补上。
备选：只补 commissioning（因为它是本片新写 running 的），plan-runner 的 stale 行
留到 S4 随链退场 —— 风险是 S3 到 S4 之间那段时间里，一次后端崩溃就可能留下永久拦门的行。

**③ 切成 S3a/S3b 两个 PR，还是一个 PR 收 —— 建议：拆两片，但都很小。**
preflight 移出后两片都是纯后端：S3a（闸门，修生产空窗，快进快出）/ S3b（dashboard 三处数字）。
一个 PR 合并收也可以，我按你说的来。

---

## 7. 外审改动记录（Codex #241，3 条全属实全采纳）

| # | 级 | Codex 指出 | 核实 | 设计稿改动 |
|---|---|---|---|---|
| C1 | P1 | 漏了 `POST /commissioning/sessions/{id}/phase/{phase}` —— 跑真硬件相位、行留 pending、GUI 有入口 | 属实（该段无任何 status 写入） | §1.1 表加一行、§2.2 加第三处改动 + helper、H-c 参数化到三入口 |
| C2 | P1 | `TestCase.configuration` 里没有能力需求，needs 是 TestStep 的 template 契约 → case 级 preflight 会空转报 ready，H-g 形同虚设 | 属实（模型注释明写 + config schema 无需求字段 + 全仓无 `needs=` 写入点） | **§2.4 整片移出 S3**，随 PlansTab 活到 S4 单独设计；原 H-g 删除 |
| C3 | P2 | 裸 `status == "running"` 会匹配 VRT 行，digital_twin 纯仿真不占 HAL 却拦 reload | 属实（`vrt_execution_service.start()` 置 RUNNING） | 谓词加 `mode IS NULL`（与 S2 同源）、新增 H-f 行为门 + H-g 同源不变量门 |

### 第二轮（显式 `@codex review` 触发后）

| # | 级 | Codex 指出 | 核实 | 设计稿改动 |
|---|---|---|---|---|
| D1 | P1 | **我上一轮把 C3 修过头了** —— `mode IS NULL` 排除的是全部 VRT，而 `conducted`（强制 topology_id）与 `ota`（走 MPAC）都占真硬件，被一起放过 | 属实（`road_test.py:546,556-559`） | 谓词改成只排 `digital_twin`；§2.1 加"占 HAL？"四行表；H-f 重写 + 新增 H-g（conducted/ota 各一条拦门） |
| D2 | P2 | dashboard 今天**明确合并展示** VRT（`:49-53` 加计数、`:90-95` 并列表），套 S2 的"非 VRT"谓词会让 VRT 从总览消失 | 属实 | §2.3 改成查全表 + 顺手删掉那两段"额外加 VRT"的代码；新增 H-i 防退化门 |

**我自己的复盘（两轮合起来看）**：

1. **C1/C3：枚举维度选错。** 我枚举的是"**建执行行**的地方"（4 处建行），而闸门要的是
   "**占着 HAL** 的地方"（`dispatch_step` 调用方 ∖ 纯仿真）—— 两个集合不一样。
2. **D1/D2：同一个谓词跨语义复制。** C3 之后我顺手把 S2 历史列表的 `mode IS NULL` 搬到了
   闸门和 dashboard，但**三个场景要的根本不是同一件事**：历史列表要"非 VRT"（避免与
   VRT 面板重复），闸门要"占 HAL"，dashboard 总览**什么都不该排**。它们只是碰巧在
   `digital_twin` 上重合，我把重合当成了等同。
3. 合起来一句：**"枚举影响集"之前先问清枚举的是哪个集合；复用谓词之前先问清两处要的是不是
   同一个语义。** 第 2 条是第 1 条的镜像 —— 一个是漏掉该进的，一个是带进不该进的。
