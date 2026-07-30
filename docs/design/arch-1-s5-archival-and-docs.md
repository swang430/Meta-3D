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
| `docs/roadmap-first-call.md` | **不动**（v2 追加） | 它是活路线图，但正文主体是 "✅ Done" 完成记录与`[discovered YYYY-MM-DD]` 当日 backlog。内审把 G8 跑在 main 上，该文件 5 条命中**真阳性率 0/5** —— 全落在历史记录里。跟已在网外的 `roadmap-archive.md` 是同一种文本，同事同待遇 |
| `docs/project-retrospective.md` | **不动** | 复盘 = 历史 |
| `docs/design/`（**整个目录**，含本文） | **不动** | 设计稿是**当时的决策记录**；改它等于伪造决策过程。门里排的是整目录而非 `arch-1-*` 通配 —— 理由同样适用于其它片的设计稿，且不用维护通配（内审 F14 核准）|

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

### D-1 → **G7【不变量档】Tab 标签集合相等**（实现时比设计稿强一档，随后又被内审打回一次）

```
真值 = TestManagement.tsx 每个 <Tabs.Tab> 后面的中文标签, 按渲染顺序
marker = 文档行尾 <!-- gate:tabs=测试用例库,执行历史,虚拟路测 -->
断言① marker 必须出现在 CLAUDE.md 与 GUI README (指名文件, 不是"≥1处")
断言② marker 声明的标签列表(有序) == 从 JSX 派生的列表
断言③ marker 同一行的散文里逐字含每个标签
```

比设计稿 v1 的"Tab **数**相等"强：中文标签也在 JSX 里，所以重命名 / 改序 /
CLAUDE.md 那个"列了四个已删名字"的 bug 全都会红，不只数量变化。

> ⚠️ **内审 F1（P1）打回一次，值得记：我第一版的"不变量档"是假的。**
> 判定器写成一条正则 `<Tabs\.Tab\b.*?>\s*(?P<label>[^<>{}]+?)\s*</Tabs\.Tab>` 配 `re.S`，
> 内审用**三种常规 JSX 写法**把它绕过去了，每种都让门保持绿：
> 标签写 `{t('key')}` / 标签包 `<Text>...</Text>` / `<Tabs.Tab ... />` 自闭合。
> 根因是 `.*?` **允许跨越 `</Tabs.Tab>`** —— 遇到抽不出的标签就回溯到下一个 Tab 的
> 开标签，那个 Tab 于是凭空消失，真值集从 3 变不成 4，`declared == truth` 照样成立。
> 我原来加的 `len(labels) >= 2` 挡不住：真实失效形态是"**新增一个**用别的写法"，
> 那时还剩 3 个标签。
> **教训**：写着"集合相等"的门，如果集合的**抽取**不忠实，实际强度就是"某一种写法的
> 存在性门"。现在改成逐个开标签手扫、抽不出就记 `None` 让上层喊出来，并断言
> **开标签数 == 抽出标签数**，静默漏抽变成显式失败。
>
> 内审 F2（P2）同类：marker 存在性写成"≥1 处"，于是单删 CLAUDE.md 那一行门照样绿 ——
> 而那正是原始 bug 的发生地。改成指名文件。

### D-2 → **G8【不变量档】文档引用的计划链路径必须真实存在**

判据不是"不许出现那 36 条已删路由"（设计稿 v1 的写法），而是**集合成员**：

```
断言 = 现状文档里每一条 /test-plans* /test-sequences* 路径 ∈ 真实路由表
```

好三处：① 抓 36 条已删的；② 也抓**从来没实现过的**（文档里躺着 `/batch`、
`/versions`、`/validate` 这类从没建过的端点，v1 的清单式判据对它们完全无感）；
③ **共享前缀陷阱结构性消失** —— `/test-plans/cases` 在路由表里天然绿，
不需要像 G5 那样特判例外前缀（S4a 踩过：写成"不许出现 `/test-plans`"会误杀用例链）。

> ⚠️ 实现 + 内审各抓到一个**误红**（"门红在正确的文字上比漏判更难查"，三次）：
> ① README 里 CTIA 的 `https://api.ctia.org/test-plans` 被当成我们的路由 → 加绝对 URL 豁免；
> ② 内审 F3：豁免写成"token 里有 `://` 就放过"太宽，
> `curl http://localhost:8000/api/v1/test-plans/{id}/start` 被整条放过，
> 而仓库里 quickstart / implementation-roadmap / data-architecture 全是这个写法
> → 收窄成只豁免**外部 host**；
> ③ 内审 F9：`roadmap-first-call.md` 5 条命中**真阳性率 0/5**，全落在 "✅ Done" 完成
> 记录与 `[discovered YYYY-MM-DD]` backlog 里。我当时的应对是把历史里的路径字面量
> 逐个抹掉躲门 —— 其中一处还在代码块里造了个不存在的符号 `_DELETED_PLAN_CREATE_ROUTE`，
> **比原来那行真实的历史代码更假**。已全部回退，并把该文件移出网（同
> `roadmap-archive.md` 的待遇）。
> 代价不对称：漏判一条 stale path = 读者一次 404；误红在正确记录上 = 有人去改记录。
> **轻的那一侧是漏判，所以网该更窄。**

### D-3 【已撤销】禁词存在性门

原计划断言"计划管理 / 步骤编排 / 执行队列"三词不出现在现状文档。**实现时撤销**：
本片要加的封存 banner 本身就写着"这三个 Tab 已随 ARCH-1 S4a 删除"—— 那是**正确**的
文字，却会让门红。它要防的东西已被 G7 断言③ 精确覆盖（旧 Tab 名若出现在"当前 Tab
列表"那一行就红，出现在别处本来就合法）。

### D-4 【申报：无门】§2.4 的 C 类判定

逐处判"这句话今天真不真"，是**语义判断，没有任何机械门能守**。
诚实写进 PR body，不假装有覆盖。

> ⚠️ **这不是理论风险 —— 内审在无门区实打实找到 6 条**：状态枚举漏 `pending`（3 处）/
> 新引入"✅ 创建用例"而 GUI 无该入口（4 处）/ design-guide 换源换了主语没换谓词
> （给暗室安上了计划的状态机）/ 监控卡片文案 / 序列族整族漏在 grep 模式之外（2 站点）。
> 全部已修。**申报"无门"必须同时说清"内审在无门区找到了几条"**，否则读者会以为
> 无门区是干净的。

### D-5 【新增，内审 F13】文档网必须确定

原先用 `rglob("*.md")`，把两个 `.venv` 里 site-packages 的 40+ 个 markdown
（playwright skill 文档、各 LICENSE.md）和 `.pytest_cache` 一起扫进了网 ——
门的结论会取决于**本机装了哪些 pip 包**。换成 `git ls-files`，并加一条常驻断言。

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
