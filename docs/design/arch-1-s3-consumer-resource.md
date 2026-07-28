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

| 执行链 | 跑起来时行的 `status` | 写 TestPlan？ | 闸门看得见？ |
|---|---|---|---|
| case-runner（S1 正门） | `running`（`test_case_runner.py:142`） | **否** | **✗ 空窗** |
| plan-runner 每步 | `running`（`test_plan_runner.py:287`） | 是 | ✓（靠 plan 那条） |
| **commissioning run-all（暗室首测）** | **`pending`**（建行 `commissioning.py:374`，run-all 全程不改） | 否 | **✗ 空窗** |
| commissioning adhoc（单相位诊断） | `pending` → 终态（S2 #239 补的收尾） | 否 | **✗ 空窗** |

后两行是**现场真正在用的链**（07-03 / 07-21 两次现场都走它），一样裸奔。

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
blockers = 活跃 TestExecution 行  ∪  TestPlan ∈ (RUNNING, PAUSED)
```

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
| adhoc 开跑置 `running` | `commissioning.py` run_adhoc_phase | 收尾已在 S2 #239 补过，只差开跑这一下 |

这**超出了上游设计稿写的 S3 范围**（它只说"闸门改查活跃 TestExecution"），但不做的话
闸门对现场真用的那条链依然是空的 —— 等于修了一半。**待决①请拍板。**

### 2.3 dashboard：数字换源

| 字段 | 现在 | 换成 |
|---|---|---|
| `active_test_plans` | 计划 RUNNING/QUEUED 数 | 活跃执行数（与闸门同一谓词，单一真值源） |
| `total_executions` | `TestPlanExecution.count()` | `TestExecution` 非 VRT 计数（与 S2 历史列表同谓词） |
| `recent_executions` | `TestPlanExecution` 排序 | 复用 S2 的 `_history_query` |

两处重复代码（`:44` 与 `:184`）合并成一个 helper —— 属于本次换源的直接连带，不是顺手清理。

### 2.4 preflight：改收 TestCase + 新入口

- `validate_plan(plan, ...)` → `validate_case(case, ...)`：needs 从
  `TestCase.configuration` 派生（不再迭代 TestStep）；
- 新端点 `POST /test-plans/cases/{id}/preflight`（挂现有 cases 路由组，与 S1 的
  execute/status 同前缀，**不换前缀**）；
- GUI：`PreflightModal` 从 PlansTab 挪到**用例库行内**（执行按钮旁加一个「预检」），
  这样 S4 砍掉 PlansTab 时它不会一起消失。

旧的 plan 版 `validate_plan` + 端点**留到 S4 一起删**（S3 只加不删，避免计划链在
S4 之前失去预检）。

---

## 3. 切分（建议拆两片 PR，因为紧急度不同）

| 片 | 内容 | 为什么单独 |
|---|---|---|
| **S3a（急）** | 闸门并集 + 活跃判据 + commissioning 如实写 running | 这是**在修生产空窗**，越快 merge 越好；改动面小、门清晰 |
| **S3b** | dashboard 换源 + preflight 改 case 级 + GUI 入口挪家 | 显示准确性 + 为 S4 铺路，不带紧急性；含 GUI 改动，要走浏览器门 |

若你希望一个 PR 收，我按 S3a+S3b 合并做，但 S3a 的门会被 S3b 的 GUI 验证拖慢。

---

## 4. 会红的门（每条配变异）

| 门 | 档 | 断言 | 变异 |
|---|---|---|---|
| **H-a** | 行为 | 有 case-runner 的 running 行时 `POST /instruments/hal/reload` 返回拒绝 + blocker.kind == "test_execution" | 砍执行行判据 → 放行 → 红（**这条就是今天的实况**，钉死空窗存在过） |
| **H-b** | 行为 | 计划 PAUSED（无 running 执行行）仍被拒 | 把并集改成"只查 TestExecution" → 放行 → 红（防退化） |
| **H-c** | 行为 | commissioning run-all 跑到一半时被拒 | 砍 run-all 的 running 写入 → 放行 → 红 |
| **H-d** | 不变量 | 历史 pending 僵尸行**不**成为 blocker（造 50 条 pending → reload 放行） | 闸门谓词误写成 `status != completed` → 红 |
| **H-e** | 行为 | `force=true` 仍能绕过（既有语义不许变） | — |
| **H-f** | 行为 | dashboard 活跃数 = 活跃执行数（造 1 条 running case 行 → 数字为 1） | 换回 TestPlan 查询 → 红 |
| **H-g** | 行为 | case 级 preflight 对无驱动 lab 报 gap；对齐后 ready | 需求集空转 → 红 |

外加 GUI 两道门（`npm run build` + 浏览器实测预检入口在用例库可点、能出 gap 列表）。

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

**① commissioning 两条链要不要在本片改成如实写 `running` —— 建议：要。**
不改的话闸门对现场真用的链依然是空的（等于修一半），且它顺带清掉 S2 backlog 里
run-all 的僵尸 pending 行。代价：超出上游设计稿给 S3 划的范围，动 commissioning 文件。
备选：只修 case-runner 那条空窗，commissioning 的记 backlog 留 S4 —— 但那意味着
**现场最常用的链在 S4 之前一直裸奔**。

**② 启动残留复位要不要在本片补齐三条链 —— 建议：要，但只补"复位"不补别的。**
闸门变严之后，任何没被复位的 stale running 行都会把 reload 永久拦死（比今天的空窗
更难受）。case-runner 已有复位；plan-runner 与 commissioning 需要同构补上。
备选：只补 commissioning（因为它是本片新写 running 的），plan-runner 的 stale 行
留到 S4 随链退场 —— 风险是 S3 到 S4 之间那段时间里，一次后端崩溃就可能留下永久拦门的行。

**③ 切成 S3a/S3b 两个 PR，还是一个 PR 收 —— 建议：拆两片。**
S3a 在修生产空窗，应该快进快出；S3b 带 GUI 改动，验证周期长。
