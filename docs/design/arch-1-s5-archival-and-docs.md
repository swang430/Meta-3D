# ARCH-1 S5 设计稿 — 封存与文档

> 状态：**已定稿**（v2 —— 两条待决 2026-07-30 用户拍板，见 §5）
> 前置：S1 `124d7e5` / S2 / S3a / S4a `211bec3` / S4b `0ff692e` / S4c `754e7a9` 全部 merged
> Roadmap：ARCH-1 S5（task #93）
> 双实证：memory ✅（4 条命中，见 §0）/ NotebookLM **不适用**（不涉 UXM / F64 驱动 SCPI 语义）

---

## 0. 这一片要解决的那一个可观察故障

不是"文档不够漂亮"。是**文档在说假话，而且有人会照着它做事**：

```
CLAUDE.md:221   - 4个主要 Tab: 计划管理、步骤编排、执行队列、执行历史
代码实况         TestManagement.tsx:50/53/56 → caseLibrary / history / virtualRoadTest
```

**三个 Tab，一个都不叫那四个名字。** 而且注意日期 —— S4a 是把 6 个 Tab 砍成 3 个，
CLAUDE.md 却写着 4 个。**它在 S4 动手之前就已经是错的。** 这说明一次性手改治不好这个病：
文档和代码之间没有任何东西把它们绑在一起，改完照样会再漂。

两个具体受害者：

1. **新人 / 用户**照 README 去找"执行队列管理"，那个 Tab 不存在，路由也已经删了；
2. **agent（包括我自己）**照 `docs/api/data-model.md` 写代码，引用封存表 —— 这不是
   假想，S4 三片里我被自己写在文档里的错归因坑过一次（B1 docstring 的
   "counted into dashboard's active_test_plans"，顺着它枚举就漏了 PAUSED）。

所以 S5 的产出是两半：**把假话改成真话** + **建一道会红的门，让它下次漂的时候红**。

### §0 附：memory 实证命中

| 规则 | 对本片的约束 |
|---|---|
| `feedback_pr_owns_status_rows` | S5 恰恰是"专门动状态行"的那个 PR —— roadmap 的 Current Focus / 已完成功能列表归它动，**正当**；但别顺手动别的 PR 的状态行 |
| `feedback_whole_not_local` | 42 个文件是 grep 派生的，不是我手列的；但**枚举 ≠ 修复**，判据必须写死 |
| `feedback_effective_end_not_nominal` | 验收不能是"我改了文档"，要看**门在文档漂回去时会不会红** |
| `project_first_call_roadmap` | PR 必须 ref roadmap；Current Focus 字段本片挪 |

---

## 1. 机械派生的影响集

**不手工列清单。** 从仓库派生：

```bash
grep -rIl -e "测试计划" -e "TestPlan" -e "test_plan" -e "计划管理" \
          -e "步骤编排" -e "执行队列" --include="*.md" .
```

→ **42 个文件，500+ 处命中。**

全改是好几天的工作，且大部分收益是零。要收敛，需要两把刀。

### 1.1 第一刀：路径规则（机械可判，无需读内容）

| 命中路径 | 判定 | 理由 |
|---|---|---|
| `docs/archive/**` | **不动** | 归档区，定义就是历史 |
| `docs/site-debug/**` | **不动** | 现场日志，记的是当天的事实 |
| 文件名含日期（`onsite-20260721-todo.md` 等 4 个） | **不动** | 同上 |
| `docs/roadmap-archive.md` | **不动** | 已归档的路线图 |
| `docs/project-retrospective.md` | **不动** | 复盘 = 历史 |
| `docs/design/arch-1-*.md`（4 个，含本文） | **不动** | 设计稿是**当时的决策记录**；改它等于伪造决策过程 |

> **改历史记录不是修文档，是伪造。** 一份 2026-05-13 的现场日志写着"跑了测试计划"，
> 那天确实跑了。把它改成"跑了测试用例"是往记录里写假话。

第一刀切掉 **12 个文件 / 约 185 处命中**。剩 **30 个文件 / 约 320 处**。

### 1.2 第二刀：句子层判据（逐处过，不是逐文件）

**关键认识：`TestPlan` 出现 ≠ 那句话是假的。**

五张表**原地封存还在**（S4c 已给全部 5 个 model 加封存 banner），报告链**仍在读老数据**。
所以描述 schema 的句子**今天仍然准确**，不该改。

只有这三类算假话：

| 类 | 形态 | 例 |
|---|---|---|
| **F1 宣称功能今天可用** | "✅ 测试计划管理：创建、编辑、执行队列、状态机" | `CLAUDE.md:398`、`README.md:220` |
| **F2 宣称代码结构今天存在** | Tab 数 / 路由 / Service / 组件树 | `CLAUDE.md:221`、`gui/.../README.md:13` |
| **F3 指导读者今天去用计划链** | "测试计划生命周期：创建 → 编辑 → 排队 → 执行 → 报告" | `CLAUDE.md:232` |

**不改**（这些句子是真的）：描述封存表 schema、描述历史数据怎么读、描述"曾经如何"。
对这类，正确的动作是**在那一节顶上加封存 banner**（换源），不是删内容 —— 内容还准确，
只是读者需要知道"这块已经没有写入方了"。

---

## 2. 逐项改什么

### 2.1 代码内的文档（docstring / 注释）

S4c 已经把 5 张表的封存 banner 做完了（`TestPlan` / `TestPlanExecution` /
`TestSequence` / `TestStep` / `TestQueue`），本片**不重复**。剩下这些：

| # | 位置 | 现状 | 改法 |
|---|---|---|---|
| **C1** | `services/test_execution/context.py:18` | `StepLike` docstring 写「Both the ORM `TestStep` row and the lightweight `StepDescriptor` fit this protocol」 | **已查证 ORM 那支死了** —— `build_step_context` 只有两个调用方（`commissioning.py:471`、`test_case_runner.py:423`），两个传的都是 `StepDescriptor`（`commissioning.py:466` 的类型注解就写死了）。计划 runner 是唯一能产出 ORM `TestStep` 的地方，S4b 删了。→ docstring 收窄，注明 ORM 支随计划 runner 一并消失 |
| **C2** | 同上 `:54` 行内注释 `step: StepLike  # ORM TestStep row OR lightweight StepDescriptor` | 同 C1 | 同步 |

> ⚠️ **C1/C2 只改 docstring 和注释，不动 `StepLike` 协议本身、不动类型注解。**
> 协议保持宽松没有坏处，把它收窄成 `StepDescriptor` 是行为改动，超出"封存与文档"，
> 且违反"一轮只删 / 收窄 / 换源，不加机制"。要不要真收窄 → backlog。

### 2.2 报告链的 `test_plan_id`：**保留，但要把话说清楚**

枚举时发现的事，值得单独一节，因为它跟"拆干净了"的叙事冲突：

```
report_data_collector.py:212  if report.test_plan_id:  → _get_test_plan() 查封存表 TestPlan
report_data_collector.py:451  _get_step_results()      → 查封存表 TestStep
api/report.py:78/581/625      仍接受请求里的 test_plan_id
```

**判定：正当，保留。** 理由 —— ARCH-1 之前生成的老报告，`TestReport.test_plan_id` 是有值的；
删掉这条读取路径 = 老报告重新生成时丢掉计划信息段。这**正是 S4 验收里
"只剩封存模型 + 历史查询"允许的那一类**。

**但 S4 的验收语句「grep 全仓 `TestPlan` 只剩封存模型 + 历史查询」当时没人验过。**
本片验了：46 处非 model 引用里，**2 处是活的历史读取**（上面这两个），
**其余全是注释 / docstring 提及**。这个结论进文档，免得下一个人再猜。

### 2.3 A 类文档：权威现状（读者据此决定今天怎么做）

| 文件 | 命中 | 假话类型 | 改法 |
|---|---|---|---|
| `CLAUDE.md` | 7 | F1 + F2 + F3 | 「测试层级」整段重写（TestCase 为根，不是 TestPlan）；Tab 数 4→3 且换成真名字；「已完成功能」两行换源 |
| `README.md` | 5 | F1 | 功能列表 + `:181` 的测试计划段换源；`:270` 的 CTIA 外链**不动**（那是行业标准名，不是我们的功能） |
| `gui/src/features/TestManagement/README.md` | 24 | F2 | 组件树按实况重画（3 Tab）；已删组件条目移除 |
| `docs/features/test-management/unified-architecture.md` | 73 | F1+F2+F3 | 该模块的权威架构文档，命中最多。顶部加 ARCH-1 变更 banner + 分节处理：结构描述按实况改，历史设计意图整节标封存 |
| `docs/api/data-model.md` | 67 | 多数**不假**（描述 schema） | 主要动作是**加封存 banner**，不是删内容 |
| `docs/architecture/system-integration.md` | 38 | 待逐处判 | 同上判据 |
| `AGENTS.md` | 28 | 待逐处判 | 同上判据 |
| `docs/roadmap-first-call.md` | 12 | F1 + 状态行 | Current Focus 从 S4 挪走；ARCH-1 各片状态标 Done；记「批量执行（后续增量）」占位（S1 设计稿 §4 明确划走的那条） |

### 2.4 C 类：剩下 22 个文件，逐处过 §1.2 判据

`docs/api/design-guide.md`(19) / VRT 三个(11+9+5) / `system-overview.md`(9) /
`state-machine.md`(7) / `execution-engine.md`(7) / `unified-report-design.md`(7) /
`execution-sync.md`(6) / `data-architecture.md`(6) / `implementation-checklist.md`(5) /
`monitoring-components.md`(4) / `Master-Progress-Tracker.md`(4) /
`uxm-license-scenario-model.md`(3) / `hybrid-framework.md`(2) /
`data-storage.md`(2) / `virtual-road-test/overview.md`(2) 等。

**这批不预判。** 逐处过 F1/F2/F3 判据，够格才改，不够格留着。
过完之后**把每个文件的判定结果记进 PR body**（改了 / 未改 + 一句话理由）——
这样下一个人不用重新 grep 一遍。

---

## 3. 门（本片的另一半产出）

CLAUDE.md 规则 ④：**门不过变异 = 门不算数**，且**至少要到"不变量"档**。
文档是散文，能上什么门要诚实分档：

### D-1 【不变量档】Tab 数：从代码派生，断言文档一致

```
真值 = TestManagement.tsx 里 `<Tabs.Tab value=` 的出现次数
断言 = A 类文档里声明的 Tab 数 == 真值
变异 = 加一个 Tab 但不改文档 → 必须红；改文档不改代码 → 必须红（双向）
```

这是**真不变量**：数量对等关系从代码机械派生，新增或删除 Tab 都会红。

### D-2 【不变量档】文档不得出现已删路由

S4b 已经在 `test_rule_gates.py` 里建了 `_DELETED_PLAN_ROUTES`（36 条，method + path，
从真实路由表派生）。**复用它**：

```
断言 = A 类文档的正文里不出现 _DELETED_PLAN_ROUTES 中的任何 path
变异 = 往 CLAUDE.md 里塞一行 `POST /test-plans/{id}/execute` → 必须红
```

⚠️ **`/test-plans/cases*` 陷阱**（S4a 踩过）：保留的用例链就挂在这个共享前缀下，
门必须**按完整 path 精确匹配 36 条清单**，不能写成"文档里不许出现 `/test-plans`"
—— 那会把正确的文档也判红。这条写进门的注释里。

### D-3 【存在性档 —— 只能当粗筛】三个已删 Tab 名不出现在 A 类文档

```
禁词 = 计划管理 / 步骤编排 / 执行队列
```

**明确申报这是最弱的一档**：它只防"完全没写对"，可以被任何保留了词但换了说法的错写法
绕过（比如"计划编排面板"就绕过去了）。CLAUDE.md 说存在性门旁边必须配行为门 ——
这里配的是 D-1 和 D-2。**D-3 单独不算数。**

### D-4 【申报：无门】§2.4 的 C 类判定

22 个文件逐处判"这句话今天真不真"，是**语义判断，没有任何机械门能守**。
跟 S4c 的 mock 层一样，这一处如果判错或漏判，**不会有任何东西红**。
诚实写进 PR body，不假装有覆盖。

---

## 4. 明确不做

- **不改历史留档**（§1.1 的 12 个文件）—— 改历史记录是伪造
- **不删封存表、不删 `report.test_plan_id` 外键** —— 老报告要读
- **不收窄 `StepLike` 协议**（只改 docstring）—— 那是行为改动
- **不动 GUI 那 4 处操作员文案**（task #101）—— 属别的卡片，按"状态行只归拥有它的 PR 动"
- **不实现批量执行** —— roadmap 只记占位，S1 设计稿 §4 已划走
- **不顺手整理任何文档的排版 / 结构** —— mess 不是 bug

---

## 5. 待决 —— **两条均已拍板（2026-07-30 用户「同意你的意见」）**

> **① 走甲案**：A 类 8 个 + C 类 22 个这次一起过，判定结果逐个记进 PR body。
> **② 建 D-1 / D-2 两道门**，用约定注释标记的"最笨形式"。
>
> D-1 定稿时比设计稿又强了一档：Tab 的**中文标签**也在 JSX 里（`TestManagement.tsx:50-58`
> 每个 `<Tabs.Tab>` 后面就是标签文本），所以门断言的不是"数量对等"而是**标签集合相等** ——
> 重命名、改序、以及 CLAUDE.md 现在这个"列了四个已删名字"的 bug，全都会红。
> marker 形态定为 `<!-- gate:tabs=测试用例库,执行历史,虚拟路测 -->`，
> 并**额外断言 marker 旁边的散文里逐字含这几个标签** —— 否则改了散文没改 marker 就漏了。

以下为拍板前的原文，保留作决策记录。

### 待决① §2.4 那 22 个文件：这次过完，还是只过 A 类？

| 选项 | 工作量 | 风险 |
|---|---|---|
| **甲（我倾向）**：A 类 8 个这次全做；C 类 22 个也过一遍判据，但**只改够格的**，判定结果逐个记进 PR body | 中 | PR 偏大，但假话一次清完，且留下判定记录 |
| 乙：只做 A 类 8 个，C 类整体进 backlog | 小 | backlog 里躺一条"22 个文件待判"，大概率一直躺着 —— 而这正是 CLAUDE.md 现在这个状态的成因 |

倾向甲的理由：C 类多数文件命中数是个位数，过判据比开 backlog 条目还快；而且"文档假话"
这类债一旦拆成两个 PR，第二个基本不会有人做。

### 待决② D-1 / D-2 两道门建不建？

建门是"加机制"，CLAUDE.md 规则 ⑤ 说一轮里想加机制要**停下来报告** —— 所以问你。

支持建的理由：**CLAUDE.md 的 Tab 数在 S4 动手之前就已经错了**（写 4，当时实际 6）。
这证明纯手改治不好 —— 没有门，改完还会漂回去，而且下一次可能又是几个月后才被发现。
两道门都是从代码派生的不变量，不是我拍脑袋定的规则。

反对的理由：文档门是新品类，此前 G1-G6 全是代码门；且 D-1 需要在文档里放一个
机器可读的标记（否则从散文里抠数字很脆）。

**我的建议：建，但用最笨的形式** —— 在 A 类文档写 Tab 数的那一行放一个约定注释
（如 `<!-- gate:tab-count -->`），门只认这个标记。脆的部分外化成显式契约，
而不是让门去猜散文。

---

## 6. 验收

1. 全量测试绿 + 新门 **D-1 / D-2 各自的变异实跑**（双向都要红，写进 PR body）
2. `npm run build` 绿（`gui/src/features/TestManagement/README.md` 改动不影响编译，
   但 C1/C2 在 Python 侧，跑后端全量）
3. **CLAUDE.md 的 Tab 数 = 代码的 Tab 数**，且三个名字逐字对上
4. A 类 8 个文件逐个在 PR body 里有一行"改了什么 / 为什么这么改"
5. C 类 22 个文件（若走甲案）逐个有"改 / 未改 + 一句话理由"
6. ⓪⁺ 全流程：内审 agent → Codex 270s 四通道 → merge → 迟到回查
