# ARCH-1 S4b 设计稿 — 后端计划链拆除

> **状态**：设计稿 **v3**（外审两轮后定稿），**尚未动代码**。
> **修订记录**：
> - v1 → v2（Codex #245 round 1，1×P1+1×P2）：B2 只写"搬字段"漏了搬应用路径；D-f 还写着 34 条。
> - v2 → v3（round 2，2×P1）：apply 是 **best-effort**（失败照跑）+ profile 与
>   `mimo_port_preset`/`mimo_layers` **优先级未定义**（两套机制拧同一个硬件旋钮）。
>   三条 P1 加起来说明 B2 **不是搬家、是改仪表配置真值源语义** →
>   **topology-profile 整个移出 S4b**（§1.8），本片自此是纯删除，零行为变更。
> **外审收口**：轮次上限 = 2，本轮到顶。v3 的改动是**缩范围**（去掉一整批），
> 不再送审；用例级拓扑覆盖单独立项，届时带自己的设计与门。
> **上游**：[`arch-1-s4-demolition.md`](arch-1-s4-demolition.md)（#243 定稿 v3）的 S4b 行。
> **前置**：S4a（`211bec3`）已 merge —— GUI 侧零调用计划路由，G5 门常驻守着不回潮。
> **实证前置**：
> - memory 查询（恒适用）**命中 4 条**：`feedback_whole_not_local`（枚举影响集）/
>   `feedback_effective_end_not_nominal`（验证打生效端）/
>   `feedback_bulk_mutation_scope_and_restrict_fk`（删父行前 audit 外键）/
>   `feedback_addcolumn_migration_dialect_agnostic`（写迁移先分类）。
> - NotebookLM：**不适用**（纯架构拆除，零仪器 SCPI 语义）。
> **代码事实**：2026-07-28 盘点，行号以 main `211bec3` 为准。**全部重新实测**，
> 没有沿用 S4 伞稿的数字 —— S4a 已经改动过这些文件。

---

## 0. 一句话

把计划链的后端整个摘掉：**36 条路由（28 计划 + 2 scenario 桥 + 4 test_sequence +
2 读旧表的孤儿）+ 6 个 Service 类 + `test_plan_runner.py`**，约 2500 行。
表原地封存（不迁移不删除），模型留到 S4c 标 deprecated。

**这一片跟 S4a 的根本区别**：S4a 删的是"用户看得见的东西"，改坏了浏览器一眼看出来；
S4b 删的是**运行时骨架**，改坏了可能要到下次现场跑真硬件才发现。所以门的形态要以
**行为门**为主，不能靠"编译过了 + 页面还在"。

---

## 1. 盘点（全部重测，含对伞稿的三处更正）

### 1.1 `test_plan.py` 的 36 条路由 = 留 8 删 28

> ⚠️ 别跟 §0 的「36 条」混淆: 这里的 36 是 **`test_plan.py` 一个文件内**的路由数;
> §0 的 36 是**本片总删除数** (28 + scenario 桥 2 + test_sequence 4 + §1.7 孤儿 2)。
> 两个 36 是巧合。

`api/test_plan.py` 实测 36 条。**保留集全部是 `/cases*`**：

| # | 路由 | 用途 |
|---|---|---|
| 1 | `POST /cases` | 建用例（GUI 暂无入口，见 task #96） |
| 2 | `GET /cases` | 用例库列表 |
| 3 | `GET /cases/grouped` | 按类别分组（用例库主视图用） |
| 4 | `GET /cases/{id}` | 用例详情（编辑弹窗用） |
| 5 | `PATCH /cases/{id}` | 改用例（含 MIMO_OTA 仪表参数，S4a 搬来的） |
| 6 | `DELETE /cases/{id}` | 删用例 |
| 7 | `POST /cases/{id}/execute` | **ARCH-1 S1 的执行正门** |
| 8 | `GET /cases/executions/{id}` | 执行状态查询 |

**删除 28 条**，四组：

| 组 | 条数 | 明细 |
|---|---|---|
| plan CRUD | 7 | `POST ""` / `GET ""` / `GET,PATCH,DELETE /{id}` / `duplicate` / `mark-ready` |
| queue | 7 | `POST,GET /queue` / `queue/reorder` / `DELETE queue/{id}` / `move-up` / `move-down` / `PATCH queue/{id}` |
| steps | 6 | `GET,POST /{id}/steps` / `PATCH,DELETE /{id}/steps/{sid}` / `steps/reorder` / `steps/{sid}/duplicate` |
| 生命周期 | 5 | `start` / `pause` / `resume` / `cancel` / `complete` |
| 单挂 | 3 | `POST /{id}/preflight`（**伞稿**待决①已定=删）/ `PUT /{id}/topology-profile`（**伞稿**待决②已定=搬进 `TestCase.configuration`）/ `GET /{id}/executions`（S2 已换源） |

外加 **scenario 桥 2 条**（`POST /{sid}/create-test-plan`、`GET /{sid}/test-plans`）
+ **test_sequence 组 4 条** = 34 条（与伞稿 §1.1 一致），
**再加 §1.7 查出的 2 条**（`GET`/`DELETE /test-executions/{record_id}`，读旧表零调用方）
= **合计 36 条**。

### 1.2 Service 层：7 类 2128 行，只留 `TestCaseService`

引用面实测（`grep -rl` 全后端）：

| 类 | 外部引用 | 去留 |
|---|---|---|
| `TestPlanService` | `api/test_plan.py`、`api/scenario.py`（要删的桥）、`road_test/vrt_service.py`（**仅 docstring**，`:38` 提了一句 `_create_road_test_steps`） | ❌ 删 |
| **`TestCaseService`** | `api/test_plan.py` 的 cases 组 | ✅ **保留** |
| `TestStepService` | 只有 `api/test_plan.py` | ❌ 删 |
| `TestQueueService` | 只有 `api/test_plan.py` | ❌ 删 |
| `TestExecutionService` | `api/test_plan.py` + `test_plan_runner.py`（都要删）+ `models/test_plan.py`（**仅 docstring**，`:106`） | ❌ 删 |
| `TestSequenceService` | `api/test_sequence.py`（要删的 4 条） | ❌ 删 |
| `StatisticsService` | **零引用**（`api/report.py` 用的是 `services/statistics_service.py` 的同名类） | ❌ 删（死代码） |

> **更正伞稿两处路径/描述**：
> - companion 过滤器在 **`app/services/road_test/vrt_service.py`**，不是 `app/services/vrt_service.py`。
> - `models/test_plan.py:106` 与 `road_test/vrt_service.py:38` 对 Service 类的引用**都是 docstring**，
>   不构成代码依赖 —— 伞稿只核了后者，这次两处都核了。

### 1.3 ⚠️ 顺序约束：先解耦，再删模块

`test_case_runner.py:69` 动态 `from app.services.test_plan_runner import has_active_runner`。
**先删模块 = 每一次用例执行都 `ModuleNotFoundError`**，S1 的执行正门当场炸。

S4a 之后的活引用（实测，已排除自身与自身测试）：

| 引用点 | 性质 | 处置 |
|---|---|---|
| `test_case_runner.py:69` | **代码依赖** | ① 删计划分支 |
| `main.py:70` | **代码依赖**（启动期复位，包在 try/except 里 —— 删了只刷 warning，**行为门抓不到**） | ② 删调用 + 复位职责搬家 |
| `api/test_plan.py:1053/1123/1247/1309` | 计划路由自用 | 与路由同批删 |
| `tests/test_arch1_case_runner.py:232` | `test_plan_runner_mutex` | 同批删 |
| `schemas/test_plan.py:303`、`commissioning.py:115`、`test_case_runner.py:3/15/64`、`test_execution/hydrate.py:1` | **注释/字面量**，非依赖 | 保留（`executed_by` 字面量仍要用于历史行） |

**`_active_conflict()` 删计划分支是安全的**：计划 runner 从此不存在，该分支恒 `None`。
真正在防重入的是 case-vs-case 单飞（`has_active_case_run`）+ DB dangling 双判据，两条都留。

### 1.4 ⚠️ brownfield 僵尸行是**三类**，不是一类

`reset_stale_running_plans()` 实测复位三种行：

| 行 | 复位动作 | 删掉函数后谁来清 |
|---|---|---|
| `TestPlan.status == RUNNING` → FAILED | `:98-105` | **没人** |
| 该计划下 `TestStep.status == 'running'` → failed | `:106-115` | **没人** |
| `TestExecution(executed_by='test_plan_runner', status='running')` | `:129-131`（S2 扩的） | **没人** |

后果**不对称，前两类更难受**：

- 第三类卡住的是 **HAL 重载闸门**（S3a 的 `find_execution_blockers` 看所有 running 执行行）
  → 409 拦死，但操作员至少看得见 blocker 列表。
- 前两类被 `api/dashboard.py:44-46` / `:184-186` 计进 `active_test_plans`，
  而 **S4b 之后已经没有 cancel/complete 端点能把它们改回来** → 永久残留，无法自愈。

**处置**：把三类复位一并接管进 `test_case_runner.reset_stale_running_case_executions()`
（它已在 `main.py` 的 lifespan 里被调用），**不加迁移文件** —— 复位函数本来就在做这件事，
只是扩谓词。配门 D-i。

> 备选（不采纳）：写一次性 alembic 迁移。理由：迁移只跑一次，而僵尸行是**每次进程
> 重启都可能新产生**的（虽然 S4b 后不再产生新的 plan 行，但存量 + 未来的 case 行同理）。
> 复位函数是持续性的，迁移不是。

### 1.5 🔴 `/dashboard` 整个端点是死的（S3b 遗留，本片必须处置）

S3 当时把 dashboard 换源推给 S4，理由是"疑似死数据"。**现在有确证了**：

```
后端返回 (snake_case):  probe_count / active_test_plans / total_executions / recent_tests
前端类型声明 (camelCase): systemStatus / activeAlerts / liveMetrics
App.tsx 实际读取:        dashboardData?.systemStatus   ← 后端从不返回这个字段
```

**两套字段零交集**，所以 `systemStatus` 恒为 `undefined`，`?? []` 兜成空数组。
GUI 主控台上真正在显示的那些卡片（驱动链 / 活动 Lab / 校准证书 / 子网可达性）来自
**cockpit readiness 端点**，不是这里；「最近执行」来自 S2 换源后的 `/test-executions`。

这条死链上挂着三处对封存表的读取：`active_test_plans`（读 `TestPlan`）、
`total_executions` × 2 + `recent_executions`（读 `TestPlanExecution`）。

**待决①**（见 §5）：删端点 / 换源 / 只删计划字段。

### 1.6 schemas 层：544 行 37 个类，cases 相关 7 个

`schemas/test_plan.py` 里 TestCase 系（`TestCaseCreate/Update/Response/Summary/
ListResponse/GroupedResponse` + `TestStepCreateFromTestCase`）保留，其余计划/步骤/队列/
执行系随路由删。

### 1.7 🔴 S2 换源漏了一半：同一个路由器上挂着两张表

追 `TestPlanExecutionResponse` 的消费方时查出来的（本来准备留到实施时查，
"可查证的状态主动查"）。**`/test-executions` 这一个路由器同时在读两张不同的表**：

| 路由 | 读哪张表 | 状态 |
|---|---|---|
| `GET /test-executions`（列表，`:137`） | `test_executions` | ✅ S2 换源了 |
| `GET /test-executions/recent`（`:100`） | `test_executions` | ✅ S2 换源了 |
| **`GET /test-executions/{record_id}`（`:203`）** | **`test_plan_executions`** | ❌ **旧表** |
| **`DELETE /test-executions/{record_id}`（`:219`）** | **`test_plan_executions`** | ❌ **旧表** |
| `POST /{id}/cancel`（`:246`）、`POST /{id}/attach-dut`（`:301`） | `test_executions` | ✅ |

两张表是真的不同（`__tablename__` 分别是 `test_executions:216` 与
`test_plan_executions:283`），**id 空间不相交**。后果：**列表列出来的每一行，
拿它的 id 去查详情都会 404**。

**为什么至今没炸**：这两条路由**零调用方** —— 全 GUI 无 `/test-executions/{id}` 的
详情/删除调用（只有 `/recent`、`/{id}/cancel`、`/{id}/attach-dut` 三种），后端也没有内部调用。
它是一颗**埋着的雷**：谁将来给执行历史加个"点开看详情"，就会撞上每行都 404。

**处置（S4b 一并删）**：这两条路由读的是要封存的表、且零调用方 → **删掉**，
连同 `TestPlanExecutionResponse` / `TestPlanExecutionListResponse` 两个 schema。
这是"去掉"档的修法，不是换源 —— 给一个零调用方的路由换源是纯浪费。

> 顺带（记 S4c，不在本片）：`gui/src/api/service.ts:90` 那句
> `// TODO: 后端需要实现 /test-executions/recent 端点` 是 **stale 注释** ——
> 该端点 S2 已实现（`:100`），且声明在 `/{record_id}` 之前，路由匹配顺序正确。

### 1.8 🔴 topology-profile：**移出 S4b**（外审两轮共 3 条 P1 逼出来的结论）

伞稿待决②定的是"搬进 `TestCase.configuration`"，v1 我照抄成 B2 一行。
外审两轮把它拆穿了 —— 这**不是搬家，是改仪表配置真值源的语义**，属 P0-2 地盘。

**round-1 C-1**：apply 的**生产调用方只有一处**（`test_plan_service.py:1480`
← `api/test_plan.py:1118`），就在要删的计划 start 里；`test_case_runner.py` 零 topology 调用。
只搬字段 → 用例写着 `topology_profile_id=X`，五相位全跑完，**没有任何一步把 X 下发给 UXM**
→ 测量在上一次的射频通路上完成，`status=completed`。

**round-2 C-1a（fail-loud）**：该函数 docstring 明写 **"Best-effort semantics"**，
失败只返回 `{"applied": False, "reason": ...}`（`no_live_driver` /
`driver_does_not_support_topology_profiles` / 回读失败 …），**计划照样启动**。
把这套语义原样搬进用例执行 = 显式请求的 profile 应用失败也照跑，还是在旧拓扑上。
用例级要不要改成 fail-loud，**是行为变更，不是搬家**。

**round-2 C-1b（优先级冲突）** —— 最关键的一条：
`MIMOOTAConfiguration` 已经有 `mimo_layers: int = 2`（`:182`）和
`mimo_port_preset: Optional[str]`（`:222`，取值 siso/2x2/4x4/2x2_alt）。
而 `:214` 的注释白纸黑字写着：

> *"path B (正式测试) measure 显式驱动这些, **避免残留 HAL-init 默认 topology profile 的**…"*

**现有设计是在主动对抗残留的 topology profile。** 往同一个 configuration 里再塞一个
`topology_profile_id`，等于让**两套机制拧同一个硬件旋钮**。Codex 给的具体反例：

```
用例: topology_profile_id=caict_n78_4x4 + mimo_layers=2 + mimo_port_preset=None
→ profile 先把端口设成 4x4
→ measure 的 TestCase 下发把层数设成 2, 但 preset 是 None 所以不重写端口
→ 最终 2 层跑在 4x4 路由上 (混合配置)
→ 而 D-h2 照样绿, 因为 profile "确实下发过"
```

**结论：topology-profile 移出 S4b。**

| 对象 | S4b 处置 |
|---|---|
| `PUT /{plan_id}/topology-profile` 路由 | ❌ **删**（与其余 27 条同批。GUI 入口 S4a 已随 `EditTestPlanWizard` 删除，现无调用方） |
| `apply_plan_topology_profile_if_set` + `test_plan_topology_override.py` | ❌ 随 `TestPlanService` 同批删 |
| **用例级拓扑覆盖能力** | ⏸ **显式申报为能力缺口**，单独立项 |

**为什么这样是对的**：S4b 自称"纯删除片"。上面三条 P1 表明 B2 根本不是删除，
是要新定义"profile 与 configuration 重叠字段谁优先""失败要不要 fail-loud"——
两条都得先出方案、跟 P0-2 的单一真值源对齐。硬塞进拆除片里，就是拿一个静默测错
通路的风险换一次少开 PR。**去掉 > 换源 > 收窄 > 加机制**：这里选"收窄本片范围"。

> 新立项要回答的三问（不在本片）：
> ① profile 与 `mimo_port_preset` / `mimo_layers` 重叠时谁优先？（或：把 profile
>   **展开进执行快照**形成单一配置后一次性下发 —— Codex 建议的方向，跟 P0-2 一致）
> ② 显式请求的 profile 应用失败，要不要 fail-loud 中止执行？
> ③ 门要打在**下发端**且覆盖每种 `applied=False` 分支，不是"字段存进去了"。

---

## 2. 切分与顺序

**一个 PR，但 commit 分三批**，顺序不可换：

| 批 | 内容 | 为什么在这个位置 |
|---|---|---|
| **B1 解耦** | `_active_conflict` 去计划分支 + 删 `test_plan_runner_mutex` 测试；`main.py` 去复位调用；case-runner 复位扩三类谓词 | 之后任何一步删模块都不会炸执行正门 |
| **B2 删除** | 28+2+4+2 = **36 条**路由 / 6 个 Service 类 / `test_plan_runner.py` / scenario 桥 / test_sequence 组 / schemas 计划系 | 此时零调用方 |

> v1 的「B2 搬家」批**已取消** —— topology-profile 移出本片（§1.8）。
> 本片自此是**纯删除**，没有任何行为新增或语义变更。

**B1 单独可跑全量测试并通过** —— 这是"顺序对不对"的自检点：如果 B1 之后全量绿，
说明解耦干净；如果红，说明还有没找到的耦合，此时**停下来**，别往 B3 走。

---

## 3. 会红的门

| 门 | 档 | 断言 | 变异 |
|---|---|---|---|
| **D-a** | 行为 | **VRT 场景库仍列得出且不含 companion**：造 3 条 companion 行 → `GET /road-test/scenarios` 200 且不含它们 | 删 `road_test/vrt_service.py` 的过滤器 → Pydantic ValidationError → 红（**275/538 存量占位行专防**） |
| **D-c** | 行为 | **用例执行全链仍通**：`POST /cases/{id}/execute` → 5 相位 → 历史有行 → 出报告 | 误删 `TestCaseService` / cases 路由 → 红 |
| **D-d** | 行为 | HAL 闸门拆掉 TestPlan 半截后仍拦住活跃执行行 | 连带删错 `find_execution_blockers` → 红 |
| **D-f** | 行为 | 删掉的 **36 条路由逐条断言 404**（不是"少了几条"，是逐条；**含 §1.7 那两条孤儿**） | 任一路由残留 → 红。⚠️ 上一版写的是 34 —— 漏掉 §1.7 新查出的两条, 那两条可以完好幸存而所有门全绿（Codex #245 C-2） |
| **D-g** | 行为**+结构** | ① 跑真实 execute 断言 200 + 执行行落库；② **结构断言：全后端源码零 `test_plan_runner` import** | ②专防 `main.py:70` —— 那处 import 在 `try/except` 里被吞成 warning，**纯行为门是假绿** |
| **D-i** | 行为 | **三类僵尸行全清**：造 ① `TestPlan.status=RUNNING` ② 其下 `TestStep.status='running'` ③ `TestExecution(executed_by='test_plan_runner', status='running')` → 跑启动复位 → 三类都进终态 + HAL 重载不被 409 拦 | 复位只扩执行行谓词 → ①②仍 running → 红 |
| **G5**（已有） | 不变量 | GUI 无计划链路由调用（`/cases*` 除外） | S4a 已建，本片自动守着前端不回潮 |

外加：**后端全量测试**（当前基线 2838 passed）+ **浏览器闭环**（建用例→配参数→执行→看历史→出报告，
这正是 S6 的预演）。

> ⓪-④：每道新门都要附**让它红的变异并实跑**。D-f 的"逐条 404"尤其要防
> "断言写成 `assert resp.status_code != 200`" 这种恒真形态 —— 必须钉 404。

---

## 4. 风险

1. **删的是运行时骨架，不是界面** —— 改坏了可能要到现场跑真硬件才暴露。所以门以行为门为主，
   且 B1 之后先跑一次全量当自检点。
2. **`main.py` 的 import 被 try/except 吞** —— 这是本片唯一一处"删错了但一切照跑"的地方，
   必须靠结构断言（D-g②）而不是行为门。
3. **三类僵尸行**（§1.4）—— 前两类删完路由后**无端点可自愈**，是不可逆的。
4. **companion 过滤器**（§1.2 更正了路径）—— 产生方删、防护方留，275/538 存量行靠它隐身。
5. **`/test-executions` 路由器上挂着两张表**（§1.7）—— 详情/删除两条读旧表且零调用方，
   是一颗埋着的雷（将来谁加"点开看详情"就会每行 404）。本片一并删。
6. **~~只搬字段不搬应用路径~~ → 已移出本片**（§1.8）。该风险连同 topology-profile
   一起转到新立项；本片删掉计划级路由后，**用例级拓扑覆盖是一个显式申报的能力缺口**。
7. **表原地封存**：`TestPlan` / `TestStep` / `TestQueue` / `TestPlanExecution` 四张表
   不迁移不删除（两台现场机器的历史行），S4c 标 deprecated docstring。

---

## 5. 待决

**① `/dashboard` 端点怎么办？→ ✅ 已拍板（2026-07-29 用户）：只删计划字段，端点留着**

删掉的：`active_test_plans`（读 `TestPlan`）、`total_executions` ×2 与
`recent_executions`（读 `TestPlanExecution`）—— 连同它们对**封存表**的读取。
保留的：`probe_count` 等不碰计划链的字段，端点本身继续在。

理由：整个端点下线是"改契约"（openapi 四步 + 前端类型 + `fetchDashboard` 调用点），
而本片是纯删除片；但把对封存表的读取留着，等于让一个零消费方的端点持续查两张要封存的表。

⚠️ 实施注意：前端 `DashboardResponse` 类型声明的是另一套驼峰字段（§1.5），
删这几个下划线字段**不会让前端红** —— 它本来就没在读。所以这一处**没有编译门兜底**，
靠 D-b（全仓 grep 无 TestPlan/TestPlanExecution 活跃业务引用）守。

> 记 S4c：`fetchDashboard` 这个调用点本身要不要留（它拿回来的东西一个都没人用），
> 连同前端 `DashboardResponse` 类型的对齐，一起在收尾片里判。

**② ~~`TestPlanExecutionResponse` 若仍有真消费方？~~ → 已查掉，无需拍板**

查了（§1.7）：它是 `GET /test-executions/{record_id}` 的 response_model，**是活的**，
但那条路由读的是**旧表** `test_plan_executions`，且**零调用方**。
处置 = 与 `DELETE /{record_id}` 一并删掉（"去掉"档修法）。已并入 §1.7，不再是待决。

**③ ~~B2（topology-profile 搬家）要不要拆成独立 PR？~~ → 已改为「移出本片」，
无需拍板，但需知会**

v1 建议"留在本 PR"。外审两轮 3 条 P1 后**推翻**（§1.8）：那不是搬家，是要新定义
"profile 与 configuration 重叠字段谁优先""应用失败要不要 fail-loud"——都得先跟
P0-2 的单一真值源对齐。硬塞进拆除片 = 拿静默测错通路的风险换少开一次 PR。

**代价（显式申报）**：S4b 之后，**用例级拓扑覆盖这个能力暂时不存在**。
计划级的入口 S4a 已经删了（`EditTestPlanWizard`），所以不是"从有到无"，
是"本来就已经点不到了，现在后端也一并清掉"。新立项补回。

---

## 6. 不做什么（显式划界）

- **不改前缀**：拆完后 `test_plan.py` 专服务 `/test-plans/cases*`，名不副实。
  改到 `/test-cases` 要动契约同步四步 + GUI 全量改调用，**独立工单**，不夹带。
- **不清 mock 层**：`mockServer.ts` / `mockDatabase.ts` 的计划端点转 S4c（mock 默认禁用，
  且用的是 `/tests/plans` 前缀，与后端不同源）。
- **不动模型**：四张表的 SQLAlchemy 模型留到 S4c 标 deprecated。
- **不补 GUI 建用例入口**（task #96）、**不改对比报告**（task #97）、
  **不做选择器分页**（task #98）—— 三条都是加机制，各自立项。
