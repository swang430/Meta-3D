# ARCH-1 设计稿 — 测试管理简化:砍计划/队列,TestCase 直接驱动

> **状态**:设计稿,待 review,**尚未动代码**。
> **拍板依据**:用户 2026-07-21 现场拍板(砍「计划管理」+「执行队列」,保留「测试用例库」
> 「步骤编排」「执行历史」「虚拟路测」,TestCase 直接驱动,批量/队列后续增量补)
> + 2026-05-04 决策(测试管理基础单元是 TestCase 不是 TestPlan)。
> **对应 todo**:[`guides/onsite-20260721-todo.md`](../guides/onsite-20260721-todo.md) ARCH-1。
> **实证前置**:memory 命中 3 条(07-21 拍板 / TestCase-first / TestCase 驱动仪表配置);
> NotebookLM **不适用**(架构重组,非仪器 SCPI 语义)。
> 代码事实全部来自 2026-07-27 全仓盘点(98 次工具调用),行号以盘点时为准。

---

## 0. 一句话

**"TestCase 直接驱动"的执行链已经存在,而且是现场验证过的那条** ——
就是 GUI 主控台的**「暗室首测 (Sandbox)」面板**那条链(内部: `TestCase →
TestExecution → dispatch_step 5 相位`,全程不碰 TestPlan,
`commissioning.py:351-383/684-703`)和现场脚本
(`onsite-run-channel-throughput.sh` 只用 `/test-plans/cases*` + commissioning 会话)
走的都是它。ARCH-1 不是新建执行链,是**把 GUI 正门从 plan 链切换到这条已验证链,
然后拆掉 plan 链** —— 修法全程「去掉 > 换源」,唯一的"加"是一个薄执行入口和一个
最小协作式 cancel。

---

## 1. 现状地图(盘点定案的关键事实)

### 1.1 两条执行链并存

| | 计划链(开关3, 2026-07-20) | 暗室首测链(现场验证过) |
|---|---|---|
| 入口 | `POST /test-plans/{id}/start` → `test_plan_runner.py` | `POST /commissioning/sessions` + `run-all` |
| 参数真值 | **`TestStep.parameters`**(TestCase 模板拷贝进计划后的副本) | `TestCase.configuration` |
| 执行体 | 每步新建**快照 TestCase** + TestExecution(挂 plan+case) | 新建 TestCase + TestExecution(**不挂 plan**) |
| 5 相位 | 同一个 `dispatch_step`(registry.py:62) | 同一个 `dispatch_step` |
| 现场用过 | 否 | **是**(07-03 / 07-21 两次现场) |

两条链在 executor 层(`measure.py` 等)完全共用;差异只在"谁建 TestCase + 谁循环相位"。

### 1.2 复杂度的来源(要砍的东西的清单)

- **7 张表里 4 张是 plan 专属**:`test_plans` / `test_steps`(FK plan NOT NULL)/
  `test_queue`(FK plan NOT NULL)/ `test_plan_executions`(FK plan NOT NULL)。
- **34 条 `/test-plans` 路由里 27 条是 plan/queue/steps/执行控制**,只有 6 条 cases
  CRUD + 1 条 preflight 与 TestCase 有关。
- **队列没有状态机也没有消费者**:`TestQueue.status` 全仓只写 `"queued"` 一个值,
  `dependencies`/`blocked_by` 零读取方,没有后台 dispatcher —— "队列"实际是一张
  会积垃圾的展示表(dev DB 曾积 801 条残留,有专门的清理脚本)。
- **8 级计划状态机**(draft/ready/queued/running/paused/completed/failed/cancelled)
  × 步骤 5 状态 × 队列 4 状态(3 个从未被写过) —— 正是拍板说的"状态机太复杂"。
- **数据流三级复制**:TestCase(模板) --拷贝→ TestStep(计划内副本,编辑不回写)
  --执行→ 快照 TestCase。同一份参数三个家,`plan.test_case_ids[step.order]`
  按**下标**反查,注释自认 reorder 后会漂。
- **GUI 实际 6 个 Tab**(README 说 4,注释说 5),feature 8498 行,另有 5 个
  无 import 方的死组件 + 三套并存的 API client。

### 1.3 砍不掉、必须换源的消费方(安全清单)

| 消费方 | 现状 | 换源方案 |
|---|---|---|
| **HAL reload 闸门**(`hal_reload_policy.py:66-87`) | 查 `TestPlan.status ∈ [RUNNING, PAUSED]` 拒 reload | 改查 `TestExecution.status == RUNNING`(活跃执行禁换驱动,语义不变判据换源)。**先换源后拆表,闸门零空窗** |
| Dashboard 统计(`dashboard.py:44-187`) | 活跃计划数 / TestPlanExecution 计数与最近执行 | 活跃执行数 / TestExecution 计数与最近执行 |
| 报告收集器(`report_data_collector.py`) | `test_plan_id` 有值才填计划段;`_get_step_results` 查 TestStep | plan 段本就 nullable;None 路径已被 `executors/report.py` 在用(标题落 'Unknown Plan')→ 补"用 TestCase 名当标题",步骤结果段在无 plan 时改列相位结果 |
| 执行历史 Tab | 读 `TestPlanExecution`(plan NOT NULL) | 改读 `TestExecution`(case 维度,粒度更细,含 commissioning/VRT/新执行链全部记录) |
| preflight(`preflight.py`) | `validate_plan(plan)` + 查 TestStep.needs | 改收 TestCase(单例预检),needs 从 configuration 派生 |
| scenario router 2 条(`create-test-plan`) | VRT→plan 的 legacy 桥 | 直接删;连带作废 `_create_road_test_steps` + companion-TestCase 过滤器(P3-8 那套补丁整个消失) |

**不受影响**:VRT 主链(`/road-test/*` 全程不碰 plan)、诊断序列(零引用)、
现场脚本(已是目标形态)、5 相位 executors(两链共用)。

---

## 2. 目标形态

### 2.1 概念模型(三层变一层)

```
现状:  TestCase(模板) → TestStep(计划副本) → 快照 TestCase → TestExecution
目标:  TestCase ──(执行时快照)──→ TestExecution
```

- **TestCase = 唯一的配置真值源**(呼应 P0-2:仪表从测试参数取值,这里就是那个
  "测试参数"的家)。模板(`is_template`)和实例都是 TestCase,现状已如此。
- **执行快照语义保留**:每次执行仍新建一行快照 TestCase(`created_by`
  标注来源,`config` 记 `source_test_case_id`)——执行历史的参数可追溯,
  后续编辑原 case 不改写历史。这是现状两条链都在做的事,不是新机制。
- **5 相位描述符照旧**(PRECHECK→REFERENCE→MEASURE→ANALYSIS→REPORT),
  它不是用户编排物。

### 2.2 GUI:6 Tab → 4 Tab

| Tab | 去留 | 说明 |
|---|---|---|
| 测试用例库 | **留,加执行入口** | 行内「▶ 执行」按钮 + 执行中状态徽标 |
| 计划管理 | **砍** | PlansTab + 4 个子组件(约 1900 行) |
| 步骤编排 | **改造为「用例配置」** | 核心资产 `MIMOOTAConfigForm`(1069 行)保留,编辑对象从 `TestStep.parameters` 换成 **`TestCase.configuration`**(直接回写,不再是"计划里的副本");`SaveAsTestCaseModal` 反向通道退场(编辑的就是 case 本身) |
| 执行队列 | **砍** | QueueTab(521 行) |
| 执行历史 | **留,换数据源** | 从 TestPlanExecution 换到 TestExecution;报告生成按 execution_ids |
| 虚拟路测 | **留,不动** | 本版零改动(收编是另一件事,见 §6) |

### 2.3 执行链(唯一的"加")

新入口 `POST /test-plans/cases/{id}/execute`(挂在现有 cases 路由组下,
**不换 URL 前缀** —— 前缀重构是另一件事,本版不做):

```
读 TestCase.configuration
→ build_mimo_ota_test_case(overrides=configuration, …)   # 复用 factory,快照
→ TestExecution(test_case_id=快照, config={step_descriptors, source_test_case_id})
→ 后台 asyncio task 逐相位 dispatch_step, failed 早停     # 从 test_plan_runner
                                                          # 抽 5 相位循环骨架,
                                                          # 砍掉全部 plan 逻辑
→ GUI 轮询 execution 状态
```

- **单飞**:沿用 runner 的"进程内标志 + DB RUNNING 双判据"拒并发(409)。
- **最小协作式 cancel**:`POST …/executions/{id}/cancel` 置状态,task 在
  **相位间**检查(runner 现有协作检查逻辑 L178-187 简化复用)。不做 pause/resume。
- **启动残留复位**:沿用 `reset_stale_running_plans` 的思路,lifespan 里把
  stale RUNNING 的 TestExecution 复位 failed(后端重启不留假 RUNNING)。
- 暗室首测链保持原样 —— 它是 bring-up 沙箱(路径 A),新入口是
  正式测试正门(路径 B),两者共用 executor 层。

### 2.4 退场方式(不删数据)

| 对象 | 处置 |
|---|---|
| 路由 27 条(plan 9 + queue 7 + steps 6 + 执行控制 5)+ scenario 2 + test_sequence 4 | **删除**(openapi.yaml 里本就一条都没有,D11 盘点=0;GUI service 函数同步删) |
| `test_plan_runner.py` / `TestPlanService` plan 部分 / `TestQueueService` | **删除**(5 相位循环骨架抽走进 case-runner 后) |
| 模型类 TestPlan / TestStep / TestQueue / TestPlanExecution | **保留,标 deprecated 只读**(docstring 写明"ARCH-1 封存,仅供历史数据查询") —— 表不 drop,brownfield 两台机器(Mac + 现场本)的历史行原地保留;greenfield create_all 仍建表(无害) |
| GUI PlansTab / QueueTab / 死组件 5 个 / `testManagementAPI.patch.ts` / `useSequenceLibrary` | **删除**(全部是 plan/queue 遗物或零引用死代码,属本改动范围,不算顺手优化) |
| bootstrap `sequences_seeder`(14 条 TestSequence,8 条只喂已删的 road-test 桥) | **删除 seeder + 封存模型**(消费方全部退场后是纯孤儿) |
| `scripts/cleanup-test-queue.py` | 保留一版(清历史残留用),README 注明表已封存 |

---

## 3. 切片(每片一个 PR,可独立验收,顺序有依赖)

| 片 | 内容 | 验收 | 依赖 |
|---|---|---|---|
| **S1 执行正门** | case-runner(抽 5 相位循环)+ `cases/{id}/execute` + cancel + 单飞 + stale 复位;GUI 用例库行内执行按钮 + 状态轮询 | mock 全链:点执行 → 5 相位跑完 → TestExecution 落行含 source_test_case_id;cancel 相位间生效;并发 409;**变异:砍 cancel 检查/砍单飞 → 各红** | 无 |
| **S2 历史与报告换源** | `GET /test-executions` 改查 TestExecution;HistoryTab 适配(展示 case 名/相位结果/时长);报告生成 payload 改 execution_ids;collector 无 plan 路径体面化(标题用 case 名) | 历史 Tab 显示 S1 产生的执行;从历史行生成 PDF 成功且标题正确;旧 TestPlanExecution 行不再展示(数据仍在 DB) | S1 |
| **S3 消费方换源** | HAL reload 闸门改查活跃 TestExecution;dashboard 统计换源;preflight 改 case 级 | 执行中 reload 被 409 拒(**变异:砍新判据 → 红**);dashboard 卡片数字来自 TestExecution | S1 |
| **S4 拆除** | 27+2+4 条路由、runner、两个 Service、GUI 两 Tab + 死代码、三套 client 里的 plan/queue 函数、`App.tsx` 的 6 个执行控制 import;StepsTab 改造为「用例配置」(编辑对象换 TestCase.configuration) | 全量测试绿(plan 相关测试删/改);`npm run build` 绿;grep 全仓 `TestPlan` 只剩封存模型 + 历史查询;G2 路由门自动验无双前缀残留 | S1-S3 |
| **S5 封存与文档** | 模型标 deprecated;sequences_seeder 删;CLAUDE.md「测试层级」+ unified-architecture 文档 + README Tab 数全部更新;roadmap 记「批量执行(后续增量)」占位 | 文档与实况一致(G3 类比:文档描述的 Tab 数 = 代码 Tab 数) | S4 |
| **S6 浏览器闭环总验** | GUI 两道门:真 build + claude-in-chrome 走「建用例→配参数→执行→看历史→出报告」完整闭环 | 四步闭环截图齐;这正是现场流程的本地彩排 | S1-S5 |

规模预估:净删 ≫ 净增(删约 27 条路由 + runner 371 行 + 两个 Service 大部 +
GUI ~2400 行 + 死代码;增约一个 200 行内的 case-runner + GUI 执行按钮/轮询)。

---

## 4. 不做(明确划走)

- **批量/队列**:拍板明说后续增量补。roadmap 占位,本版零实现。
- **VRT 收编**:TestCase-first 的第二步,另出设计。本版 VRT Tab 与 `/road-test/*` 零改动。
- **`/test-plans/cases` URL 前缀改 `/test-cases`**:契约破坏面大、收益纯美观,记 P3。
- **三套 GUI API client 合并**:只删 plan/queue 成员,不合并(顺手优化禁令)。
- **P2-3 内生经验配置**:另一条加载路径,独立项。

---

## 5. 风险与顺序纪律

1. **HAL reload 闸门零空窗**:S3(换源)必须在 S4(拆表访问)之前 merge ——
   活跃测试禁 reload 的保护一刻不裸奔。
2. **报告深耦合是最大不确定面**:collector 的无 plan 路径虽已存在(executors/report.py
   在用),但"从历史 Tab 生成 PDF"这条 GUI 路径要 S2 里真点一遍(不是只跑单测)。
3. **App.tsx 的 6 个执行控制 import**(E14)是拆除时的 fan-out 雷,S4 逐个清。
4. **每片过完整 ⓪⁺ 流程**(内审 agent + Codex 270s + 迟到回查),门配变异。
5. **旧数据不迁移不删除**:TestPlanExecution/TestStep 历史行原地封存。要看老记录
   查 DB;不给"旧历史"做 GUI(见 §7 待决②)。

---

## 6. 与后续工作的接口

- **P0-2 通用契约**:TestCase.configuration 就是"仪表配置单一真值源"的载体,
  S1 的执行链天然走 P0-2 加固过的下发→APPLY→生效核对路径。
- **现场流程 PR**(todo 340 行那条,"TestCase 流程覆盖现场 bring-up + 规则固化"):
  ARCH-1 落地后它的能力保障部分即告成立,只剩规则文档化。
- **VRT 收编**:执行历史换到 TestExecution 后,VRT 执行天然进同一张历史表,
  收编时只剩 GUI/schema 层。
- **批量执行(将来)**:在 TestCase-first 上补"执行集合"时,应是**薄的
  case_id 列表 + 逐个调 S1 入口**,不复活 TestPlan 状态机。

---

## 7. 待决(需要拍板)

**待决① StepsTab 的最终形态** —— 我的建议:**保留为独立 Tab,改名「用例配置」**,
选中 TestCase 后用 MIMOOTAConfigForm 直接编辑 `TestCase.configuration`(所改即所存,
没有"计划里的副本"这层)。备选:并进用例库 Tab(点行展开编辑)——少一个 Tab 但
1069 行的表单挤在列表页里,现场小屏不友好。

**待决② 旧计划历史的可见性** —— 我的建议:**GUI 不再展示**(TestPlanExecution
数据原地封存,要看查 DB)。备选:历史 Tab 加"旧计划记录(只读)"折叠区 ——
多养一条只读代码路径,与"砍状态机"的方向相逆。

**待决③ cancel 的范围** —— 我的建议:**最小协作式 cancel 进 S1**(相位间检查,
约 20 行,复用 runner 现有协作逻辑)——现场一个 case 四方位吞吐可能十几分钟,
没有 cancel 只能等或杀后端。备选:V1 无 cancel(更简,但现场体验硬伤)。
