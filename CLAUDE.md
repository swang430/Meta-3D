# CLAUDE.md

本文件为 Claude Code (claude.ai/code) 提供在此代码库中工作的指导。

> **沟通语言：一律使用简体中文。** 与用户的所有对话、PR / commit 描述、文档、说明性注释均用简体中文；仅代码标识符、SCPI / 命令 / 路径等字面量、以及 `fix:` / `feat:` / `chore:` 等 commit prefix 保留英文。不要因 git log 历史或既有英文注释就 convention drift 回英文。(2026-05-27 用户明确要求)

## ⭐ 工作准则 — 适用于所有 agent / session（最高优先级）

> 本节是项目契约。任何非琐碎改动开始前必须遵守。

### ⓪ 动手前照做（7 条动作句，最高优先级）

> 这 7 条是**动作**不是原则 —— 每条都能在聊天里看出做没做。
> 背景：memory 里有 70+ 条规则，靠"关键时刻想起来"已被证明不管用
> （2026-07-26：我三天前自己写下的禁令，动手时没想起来，做了它明令禁止的事）。
> 所以判据必须**外化**：写在聊天里、写在 commit 里、由会红的测试兜住。

**① 动手前写四行**（缺一不可，写在聊天里）：
```
搜索命中：memory 规则 / 目标文件自己的禁令 / 仓库已有的权威清单
必要性：要修的**那一个**可观察故障
范围：动 N 个文件；枚举到 M 处，这次只做 1 处，其余进 backlog
爆炸半径：原 bug 最坏 X → 修完最坏 Y，**Y ≤ X**
```

**② 改文件前先 grep 它自己的禁令**：`绝不|不许|禁止|must not|别把`。
   十秒钟。2026-07-26 F64R-10 的 P1 回归就死在这 —— `_silent_reconnect_visa`
   的 docstring 白纸黑字写着"绝不置 `_visa_resource=None`"。

**③ 枚举结果进 backlog，不进当前改动** —— 除非用户明说"全都修"。
   **枚举 ≠ 修复**：枚举回答"这条规则还适用于哪里"(情报)，不等于"这次必须全做完"(工单)。
   一次改一处 + 把清单留下，既不逐点漏镜像，也不做超出验证能力的大改。

   **③⁺ 改动落定后，把改动那句话当关键词全仓 grep 一遍。** 十秒钟。
   ③ 管的是**代码**的镜像站点；同一件事在 README / quickstart / roadmap / 条目 /
   backlog / 注释里通常还说过好几遍，**文档的镜像站点** ③ 管不到。
   关键词取那句话的主语/宾语（`readiness 派生` / `8000` / `systemStatus`），
   命中的每一处都问"它现在还成立吗"。
   > 这类漏改**任何门都抓不到** —— 编译过、测试绿、看 diff 也看不出，因为问题不在
   > diff 里，在 diff 没覆盖到的那几处。2026-08-02 一晚三次：#268 端口标签 6 处只改 3；
   > P1-25 quickstart 改了端口表、**同一文件下方**的示例四处仍反着；#269 改准了
   > P1-25 条目、**紧邻的** Discovered 仍写着已撤回的方案。

**④ 每加一道门，附上让它红的变异并实跑** —— **门不过变异 = 门不算数**。
   门的强度分四档，**至少要到"不变量"档**：
   | 档 | 形态 | 能防什么 |
   |---|---|---|
   | 行为门 | 造故障场景，断言**可观察后果** | 实质错误 |
   | 不变量门 | 从代码派生**恒成立的关系**(数量对等/集合相等) | 新站点漏做 |
   | 存在性门 | 某 token 在不在 | 只防"完全没写"，**可被保留 token 的错写法绕过** |
   | 恒真断言 | — | 什么都不防 |
   存在性门只能当粗筛，**旁边必须配行为门**。

**⑤ 审查一轮里想"加机制"= 停下来报告**，不自己往下滚。
   一轮只**删 / 收窄 / 换源**是健康的；一轮**加机制或加文件**说明丢了主线。
   修法优先级恒为：**去掉 > 换源 > 收窄 > 加机制**。

**⑥ 说"已跑 / 已验证"前，先看那条命令的输出。**
   没跑就说"这就跑"，不说"已跑"。(2026-07-26 实证：我写了"现在重跑 agent 门"
   然后直接进了汇报，那句话当时是假的。)

**⑦ PR 只做开它的那件事 —— 每个改动文件标一个字：修 / 顺带 / 越界。**
   （2026-08-02 用户定："为什么开的 PR，要针对这个目的，不能自己发挥。"）
   - **修** = 不改它，①里那个可观察故障还在
   - **顺带** = 同一次排查暴露的、跟故障同源、不修下次还踩同一个坑
   - **越界** = 都不是 —— **哪怕它真的是个好改动**。一律撤回 backlog。

   **判据不是"这改动好不好"，是"它对应目的里的哪个字"。** 前者的答案永远是"好"——
   越界从来不是一个坏决定造成的，是一串**每步单看都合理**的决定累积出来的。
   文件数超出目的那句话的自然范围，就停下来报告。

   **⭐ 判据在动手前问，不是提交前标**：**「不改它，①里那个可观察故障还在吗？」**
   答"不在了" = 不该动手。
   > 本条立完**当天下一片**（P1-25）就复发了 —— 不是规则写错，是触发点错了：
   > 把"标 修/顺带/越界"当成提交前自查表，而越界发生在**决定做什么**那一刻；
   > 等到标注时代码已写完，标注就退化成给既成事实找归属。P1-25 实证：多做的两件事
   > （`executionMode` 换源 readiness、"修正" `DashboardResponse` 形态）用这个问句
   > 一秒就否掉，而实际是内审替我问的，代价一整轮返工 —— 且那两件各自又引入了新缺陷
   > （前者会把演示脚本标成绿色「真实执行」，后者**修一层谎又造一层谎**）。

   > 铁证（本条来源）：修 `dev:safe:all` 启动失败，真正需要的是**五行**（`kill` 前问
   > 一句"这 PID 是不是 Docker 的"）。做成了 250 行 / 9 文件。内审 11 条 findings 里
   > **我新造的 6 条一条不落全长在多做的那 245 行上**（自加的 `exit 1` 控制流 → 3 条、
   > compose profile → 1 条、纯装饰的 `docker_publishers` → 挂死整个启动流程 25 秒、
   > 复制两份守门 → 当场漂出行为分叉），**核心那五行零 finding**。
   >
   > ⑦ 补的是 ③⑤ 中间的洞：③ 管**横向铺开**（同一规则的其它站点），⑤ 触发在**审查轮**，
   > 两条都没覆盖"实现阶段在同一处纵向加深"这个形态。

> 用户给的任何规则增强，当场存进 memory；能下沉成 lint / 结构断言 / 本文件硬规则的，
> **从 memory 挪走** —— 少依赖记忆，多依赖会红的门。

### ⓪⁺ 每个 todo 功能的标准生命周期（2026-07-26 用户定，六步不跳步）

> 复盘实证：出过的问题几乎都落在**两个实证缺位**上 —— 该查 memory 没查、
> 该查 NotebookLM 没查，靠猜。所以第 1 步是硬前置，不是建议。

**① 双实证前置** —— 动手前逐项过，适用性判定要**显式**（别默认跳过）：
- **memory 查询（恒适用，每个 todo 都做）**：带着具体问题查 `MEMORY.md` 索引
  （它是查询用的参考，不指望自己浮现）。索引在会话所属用户的 memory 目录，
  **不随仓库分发** —— 新 clone / 其他工作站 / 无 memory 的会话里它不可用，
  这种环境**显式记"memory 不可用"即过，不阻塞**，以 `CLAUDE.md` 本文 +
  `docs/` 既有权威文档为替代实证源；
- **NotebookLM（条件适用）**：**涉 UXM / F64 驱动 SCPI 时必查**对应 notebook
  （见「必查 NotebookLM」一节），仪器语义的裁决权在手册，不在代码注释也不在
  审查意见；非仪器语义任务（GUI / 普通 API / 文档等）此项**显式记"不适用"即过，
  不阻塞** —— 但凡需要外部事实，按「能用工具查证的状态主动查」穷尽公开可查证源
  （web / 开源实现 / 官方手册镜像 / 行业标准），别拿"文档没有"当结论。

**② 先 review plan，后写代码**：出设计稿（`docs/design/` 或 todo 条目内嵌方案）
供用户 review，**用户过目后才动代码**。

**③ 实现**：⓪ 六条照做（四行契约 / grep 禁令 / 枚举进 backlog / 门配变异 /
一轮只删不加 / 看输出再说已跑）。

**④ 内审 = pre-commit-reviewer agent 硬门**：代码 push 前必过；agent 不可用
（额度 / 故障）时**如实声明"审查未发生"**，不得当"审过无问题"，并在 PR body
标注由外审独挑。

> **调用时必须在 prompt 里给三样东西**（2026-08-03 定，缺了 agent 的时间预算
> 就落空）：① `git diff --cached` 原文，别让它自己摸索改动范围；② **你已经跑过
> 的命令与其输出原文**（全量测试、变异清单、构建），并明写"**这些别重跑**"；
> ③ 你**已经造过的变异清单**，让它去造你没想到的那几条。
>
> ⚠️ **②里的全量测试输出对代码改动是必给的** —— 给不出就**别说你跑过**，
> agent 会自己补跑一次（它按"prompt 里有没有可核验的全量输出"做完全划分，
> 没有就补跑）。**不许出现"我没跑全量、agent 也默认不跑"** 这种两头落空
> ——那等于内审失效。（Codex #274 P2 抓出：初版只列了三条复跑触发信号，
> 恰好漏掉"主 agent 如实说没跑"这一格。）
>
> ⚠️ **贴的输出必须是跑在你交给它审的那个版本上的** —— 最常见的破法是
> 「先跑全量 → 又补修了几处 → 把旧输出贴过去」，那批最后的改动**从未经过
> 全量**却过了内审。要么**跑完就别再改**，要么改完**重跑再贴**；
> 无论哪种，都在 prompt 里明写一句"此输出跑在当前 staged 版本上，此后未再改动"。
> （Codex #274 R2 抓出。）
> 实证：P1-30 那轮内审跑了 30 分钟，8–10 分钟耗在把全量重跑 3–4 遍上，
> 而最值钱的三条 finding 全来自它自己造的变异（单条 0.1 秒）——
> 我 prompt 里那句"不要只采信我的说法"直接招来了这笔浪费。
> 细则在 [`.claude/agents/pre-commit-reviewer.md`](.claude/agents/pre-commit-reviewer.md) 的 ⓿ 节。

**⑤ 外审 = Codex**：PR 开出 / 修复推送即触发；**270s 定时器**从触发时刻起算，
到点主动查**三通道**（reviews / inline / issue comments，"usage limits" 提示 =
review 未发生 ≠ clean）；**Codex 无问题或 5 分钟无 comment 即 squash merge**
（持久授权）；审查-修复循环**轮次上限 = 2**，第二轮 findings 主要由上轮修复
引入即收口。

**⑥ merge 后迟到回查**：squash 后挂回查定时器再扫一轮三通道；迟到真 finding
走新分支（原分支只读）。

> 细则备查：memory `feedback_merge_workflow_codex_clean`（外审全细节）/
> `feedback_precommit_test_agent_gate`（内审）/
> `feedback_review_loop_scope_discipline`（轮次纪律）/
> `feedback_query_notebooklm_for_uxm_f64_driver`（实证①）。

### 1. 先读路线图

任何非琐碎改动开始前，**先读 [`docs/roadmap-first-call.md`](docs/roadmap-first-call.md)**，
明确这次改动对应哪个 roadmap 编号（P0-X / P1-X / P2-X / P3-X）。

### 2. WIP = 1 on P0

路线图顶部 `Current Focus` 字段是当前唯一允许 in-progress 的 P0 项。
该项 PR merged + acceptance criteria 验证通过之前，**不开新的 P0**。

**注意**：本规则约束的是 **WIP 上限**（最多一个 P0 并发），不是
"必须永远有 P0 在做"。如果剩余 P0 全部物理 blocked（例如等下次现场、
等硬件采购），降级到 P1 不算违规 —— 这时把 Current Focus 字段挪到
具体 P1 项，并在路线图的 "🚧 Blocked on hardware" 区显式标注哪些 P0
在排队等什么。一旦 blocker 消失（下次现场），P0 自动回到队首,
此时不能再启动新 P1。

### 3. 不在路线图上的改动 — 三种处理

- **琐碎 (<30 分钟)**：直接做，commit message 标 `chore:` 前缀。
- **中等大小**：在 roadmap.md 的 "Discovered during X" backlog 区加一行
  (`[discovered YYYY-MM-DD during P0-X] <一句话>`)，然后**回到当前 P0**。
- **大改**：停下来跟人讨论。

### 4. 严禁"顺手优化"

看到代码 mess 不要清理。Mess 不是 bug。如果它不让当前 P0 更容易，
就进 P3 backlog，不是 inline cleanup。

### 5. PR 必须声明 roadmap 对齐

PR 描述必须包含：
```
Roadmap: P0-X  (或)  Out-of-roadmap, reason: ...
```
模板在 [`.github/pull_request_template.md`](.github/pull_request_template.md)。

### 6. Review 反馈的处理

Codex / 人类 reviewer 的 P0/P1 安全问题：当下修。
P2/P3 风格类反馈：appended to backlog, not 当下修，避免 review 黑洞。

### 7. 周度短 review

每周五 15 分钟自问 3 个问题：
1. 这周原本要做的是哪个 P0，实际做了什么？
2. 偏移程度（0% / 30% / 100%）？
3. 偏移原因属于上面 1-5 的哪一类？

**这些规则的存在原因**：CAICT 2026-05-12/13 两天现场调试本应交付 first-call，
实际全部消耗在 driver 层（F64 IDN / UXM Test App / Aerotech 单轴 / idle-close）。
工作本身有价值，但 first-call 没出来。下次去现场前，软件链路要先在本地走通
（mock-data first-call），现场只调硬件，不写 driver 代码。

详细 governance 论证见 [`docs/announcements/2026-05-14-roadmap-baseline.md`](docs/announcements/2026-05-14-roadmap-baseline.md)。

---

## 项目概述

这是一个面向汽车无线通信的 MIMO OTA（空中接口）测试系统。系统采用多探头暗室（Multi-Probe Anechoic Chamber, MPAC）技术，在可控的电磁环境中测试全尺寸车辆。

**核心理念**：系统实现了"软件定义静区"（Software-Defined Quiet Zone），测试区域的质量由软件算法和校准决定，而非暗室的物理尺寸。

## 常用命令

### 前端开发 (gui/)
```bash
cd gui
npm install              # 安装依赖
npm run dev              # 启动开发服务器（支持热重载）
npm run build            # TypeScript 编译 + Vite 生产构建
npm run lint             # 运行 ESLint 检查
npm run preview          # 本地预览生产构建
```

### 类型生成
```bash
cd gui
npm run openapi:generate # 从 ../api/openapi.yaml 生成 TypeScript 类型
```
此命令读取 OpenAPI 规范并生成 `gui/src/types/api.generated.ts`。每当 API 规范更改时都需要运行。

## 架构

### Monorepo 结构
- **gui/**: React + TypeScript + Vite 前端应用
- **api/**: OpenAPI 3.0 规范，定义 REST API 契约
- **根目录文档**: 硬件规格和系统设计文档（AGENTS.md, Hardware.md, MPAC.md 等）

### 前端架构 (gui/)

GUI 遵循 **API优先架构**，包含以下层次：

1. **API 层** (`gui/src/api/`):
   - `client.ts`: Axios HTTP 客户端实例
   - `service.ts`: API 服务函数（fetchDashboard, fetchProbes 等）
   - `mockServer.ts`: Axios mock 适配器，用于无后端开发
   - `mockDatabase.ts`: mock 服务器的内存数据存储

2. **服务层** (`gui/src/services/`):
   - `channels/`: 信道仿真器硬件抽象层（HAL）
   - 协调 API 调用和本地状态的业务逻辑

3. **组件层** (`gui/src/components/`):
   - `ProbeLayoutView.tsx`: 探头天线阵列的 3D 可视化

4. **类型定义** (`gui/src/types/`):
   - `api.ts`: 手动定义的 API 类型
   - `api.generated.ts`: 从 OpenAPI 规范自动生成
   - `channel.ts`: 信道仿真器类型

### 核心领域概念

**测试层级**（ARCH-1 2026-07 拆平，只剩两层）:
- **测试例（Test Cases）**: **正式测试的单一真值源**。一个 TestCase 自带它的
  `configuration`（仪表参数、信道资产、相位描述符），可保存、复用、直接执行。
- **执行记录（Test Executions）**: 每次执行产生一行 `TestExecution`，由
  `api-service/app/services/test_case_runner.py` 驱动。历史与报告都从这里取数。
  状态取值以 `TestExecution.status` 的列注释为唯一真值源（`api-service/app/models/test_plan.py`）—— 今天是 `pending`（**默认值，建出来就是它**）/ `running` / `completed` / `failed` / `cancelled` / `skipped`，另有 VRT 专用的 `idle` / `initializing` / `configured` / `paused` / `stopped`。
  ⚠️ **别在别处抄这个清单** —— 上一版这里就漏了 `pending`（`api/commissioning.py` 两个活端点建行时用的就是它），而漏枚举正是 ARCH-1 反复踩的坑。
- 执行正门是 `POST /api/v1/test-plans/cases/{test_case_id}/execute`
  （URL 里的 `test-plans` 前缀是历史包袱，改前缀是契约破坏面大、收益纯美观的 P3）。

> ⚠️ **计划链已整体拆除**（ARCH-1 S4a #244 / S4b #246 / S4c #247，共删约 16000 行）。
> 曾经的「测试计划 → 执行队列 → 步骤编排 → 序列库」四层**全部不存在**：
> 28+ 条路由、计划 runner、六个 Service、两个 GUI Tab 均已删除，
> `TestPlan` / `TestStep` / `TestQueue` / `TestPlanExecution` / `TestSequence`
> 五张表原地封存（只读历史、无业务写入方，见
> [`api-service/app/models/test_plan.py`](api-service/app/models/test_plan.py) 的封存 banner）。
> **新代码不要引用这五张表。** 批量执行是后续增量，目前零实现。

**测试管理模块**:
- 位于 `gui/src/features/TestManagement/`，说明见
  [该目录的 README](gui/src/features/TestManagement/README.md)
- 3 个主要 Tab: 测试用例库、执行历史、虚拟路测 <!-- gate:tabs=测试用例库,执行历史,虚拟路测 -->
  （这一行由 `api-service/tests/test_rule_gates.py` 的 G7 门守着：
  行尾 marker 声明的标签集必须等于 `TestManagement.tsx` 里 JSX 的标签集，
  且散文里要逐字含这几个标签 —— 改 Tab 不改这行会红）

**硬件组件**:
- **探头（Probes）**: MPAC 阵列中的天线单元（32个双极化探头）
- **仪器（Instruments）**: 信道仿真器、基站仿真器、信号分析仪
- **被测设备（DUT, Device Under Test）**: 在静区中测试的车辆

**关键功能**:
- 实时监控数据流和告警
- 仪器目录，支持型号选择和连接管理
- 探头配置和可视化
- 测试例生命周期：建用例 → 配参数 → 执行 → 看历史 → 出报告

## 技术栈

### 前端
- **React 18** + TypeScript
- **Vite** 构建工具（非 Create React App）
- **Mantine UI** (@mantine/core, @mantine/hooks, @mantine/notifications) - 主要组件库
- **TanStack Query** (@tanstack/react-query) 用于服务端状态管理
- **Axios** 配合 mock 适配器进行 API 调用
- **ESLint** + TypeScript 规则

### 后端
- **FastAPI** + Pydantic v2
- **SQLAlchemy** ORM

### 数据库（⭐ 重要）
- **生产环境一律使用 PostgreSQL**，绝不依赖 SQLite
  - 真实配置：`.env` 的 `DATABASE_URL=postgresql://...`
  - `app/config.py` 中的 SQLite URL 是**注释掉的备份**，不应在生产路径中启用
  - 新增 SQLAlchemy 模型应使用 PG 兼容类型（`postgresql.UUID`、`JSONB` 等）
- **测试可以使用 SQLite**（隔离与速度优先）
  - `sqlite:///:memory:` 用于纯内存隔离测试
  - `sqlite:///./test_*.db` 用于文件隔离测试，产物已在 `.gitignore` 中忽略
  - `api-service/*.db` 与 `*.db.bak` 是本地 stale 开发产物，可安全清理

## 开发工作流

### ⭐ 数据源真相 — 默认连真实后端, mock 已禁用 (排查前先对照, 别被 mock 误导)

> **2026-06-02 教训**: `mockDatabase.ts` 演示数据 + 旧 mock UI 死代码曾让"GUI 实现在哪"
> 排查误导多轮。读代码判断"功能怎么工作"前, **先确认它走真实路径还是 mock/演示数据**
> (方法见 memory `feedback_distinguish_live_vs_mock_dead_code`)。

**运行时默认连真实后端**: `gui/src/main.tsx` 的 `setupMockServer()` **已注释掉**, Vite
代理把 `/api` 转发后端。前端 mock 数据 (`mockDatabase.ts` 的 TP-317/404/CTIA-01-40 等)
**不出现在运行的应用里** —— GUI 的测试例 / 步骤来自后端 DB。

**真实生效路径地图** (找"X 在哪"时认准这些):

| 关注点 | ✅ 真实生效路径 |
|--------|----------------|
| 测试管理 UI | `gui/src/features/TestManagement/` (`<TestManagement/>`) |
| 测试例 / 序列库 seed | 后端 `api-service/app/services/bootstrap/test_case_templates.py` |
| 信道模型 .smu 清单 | 仪器抽屉 `ChannelModelsCard` (只读, 读 `/instruments/{cat}/channel-models`) |

> 旧 mock 时代的 `App.tsx::_TestConfig` + `stepTemplateDefinitions` (lib-* 模板) 死代码已删
> (零渲染, 曾是误导源)。

**仅显式开发时启用 mock** (取消 `main.tsx` 注释): mock 配置在 `gui/src/api/mockServer.ts`,
数据在 `gui/src/api/mockDatabase.ts`; 启用后整个应用走 mock adapter 不连后端, TP-* 等演示
数据跟真实后端会漂移。添加新端点的 mock / 契约同步见下方「添加新 API 端点」。

### ⭐ 仪表驱动调试 / 现场验证走诊断序列, 不写临时脚本 (2026-07-26 用户定标准操作)

**仪表驱动的 debug 与现场验证，一律走 checked-in 的诊断序列**
（`api-service/app/diagnostics/sequences/`，GUI 在「诊断 / 序列执行」面板跑），
**不写临时脚本、不现场手敲 SCPI**。

**为什么**：临时脚本**不查源码**，会重复犯已经修过的错（2026-07-21 现场铁证：
懒重连早已存在，脚本还在手动重连）；脚本是一次性的，错误也一次性重犯。
序列是 checked-in 代码 —— 过 review、有测试，每次跑的记录落进 `DiagnosticRun`
（参数 / 成败 / **仪器原始回复** / 耗时 / 日志路径 / 谁跑的 / 何时跑），下次能对照。
现场时间极贵，序列让现场从"写代码"变成"点一下、看数、抄回来"。

**怎么用** —— 每记一条"这个得现场验"的 backlog，**同时问它落在哪个序列里**；
没有就出发前补一个。按问题类型选载体：

| 问的是什么 | 载体 | 例子 |
|---|---|---|
| **A 通不通**（这条命令支不支持） | 只读普查序列 | `propsim_f64_health` / `uxm_scpi_compatibility` |
| **B 返回什么字面值** | 同上，但读 `step.raw`（**不是** `detail`） | F64R-7 的 `STATE?` 在 GOS 后 / 旁路下报什么 |
| **C 一串动作之后会怎样** | 剧本式序列 | `propsim_f64_state_machine` / `baseStation_attach_check` |
| **D 一轮要多久** | 序列已记 `duration_ms` | `get_metrics` 每轮 36 条往返 |

**约束**：① 序列里只放**手册有依据 + 生产驱动已在用**的命令（禁盲试照旧适用，
新增 SCPI 先查 NotebookLM，见下条）；② 带动作的剧本必须**先查状态再决定发不发**，
并在每步后读一次错误队列；③ 出发前用 mock 跑一遍 —— 只证明序列本身不崩，
**不证明问对了问题**，别当验收。

跟「现场调试走正常 TestCase 流程」是同一条规矩的两半：**测试流程**走 TestCase，
**驱动调试 / 能力探测**走诊断序列，两者都不允许临时脚本。
详见 memory `feedback_instrument_debug_via_diagnostic_sequence`。

### ⭐ UXM / F64 驱动 SCPI 开发必查 NotebookLM (2026-07-22 用户定标准 rule)

凡改动涉及 **UXM 或 F64 驱动的 SCPI 部分**（命令形式 / 下发序列 / 状态机语义 /
前置条件 / 回读），动手或定稿前**必须先查对应 NotebookLM notebook** 拿确认和建议
（工具 `mcp__notebooklm-mcp__notebook_query`，传 notebook_id + 问题）：

- **F64 / PROPSIM** → 「PROPSIM 资料」`982222b7-4953-46cd-9949-00fa97882353`
- **UXM** → 「Keysight UXM5G 网络测试 SCPI 编程指南」`236d9621-e3ce-4ed1-a8e1-7819b674dbcd`

厂商手册是可查证权威源；**F64 禁盲试**（未验证 SCPI query 会触发 3334 session
desync）。纯移除 / 重命名 / 不引入新 SCPI 逻辑的重构不必查。第一个实打实应用点 =
P0-3（重写 F64 load .smu 前置序列）。详见 memory
`feedback_query_notebooklm_for_uxm_f64_driver`。

### 添加新 API 端点
1. 在 `api/openapi.yaml` 中定义端点
2. 运行 `npm run openapi:generate` 更新 TypeScript 类型
3. 在 `gui/src/api/service.ts` 中添加服务函数
4. 在 `gui/src/api/mockServer.ts` 中添加 mock 处理器
5. 在 `gui/src/api/mockDatabase.ts` 中添加/更新 mock 数据

### 状态管理模式
- 使用 **TanStack Query** 管理服务端状态（API 数据缓存、重新获取）
- 使用 **React hooks**（useState, useContext）管理 UI 状态
- Mantine 提供 `@mantine/notifications` 用于全局通知

### 样式方案
- 以 **Mantine 组件**为基础
- 自定义组件应封装 Mantine 原语以保持一致性
- 尽可能使用 Mantine 的主题系统（tokens、暗黑模式）而非自定义 CSS
- 现有的 `App.css` 是遗留代码；新代码优先使用 Mantine 的样式解决方案

## 重要文件

### 核心代码文件
- [gui/src/App.tsx](gui/src/App.tsx) - 主应用组件（非常大，178KB）
- [gui/src/main.tsx](gui/src/main.tsx) - 应用入口点
- [gui/src/api/service.ts](gui/src/api/service.ts) - 所有 API 服务函数
- [api/openapi.yaml](api/openapi.yaml) - API 契约定义
- [gui/package.json](gui/package.json) - 依赖和脚本

### 设计文档（⭐ 必读）

**API 与数据规范**:
- [API 设计指南](docs/api/design-guide.md) - ⭐ RESTful 设计原则、响应格式、错误处理
- [数据模型指南](docs/api/data-model.md) - ⭐ 数据库模型 / DTO / API Schema 三层架构
- [Swagger 使用指南](docs/api/swagger-guide.md) - 在线 API 文档

**架构设计**:
- [AGENTS.md](AGENTS.md) - 系统架构和设计文档（35K+ tokens）
- [系统集成](docs/architecture/system-integration.md) - 系统集成设计
- [硬件同步](docs/architecture/hardware-sync.md) - ⭐ L0-L3 分层同步
- 测试管理：现状看 [`gui/src/features/TestManagement/README.md`](gui/src/features/TestManagement/README.md)；原「统一架构」文档以计划链为主语，已随 ARCH-1 S4 归档至 [`docs/archive/test-management-unified-architecture.md`](docs/archive/test-management-unified-architecture.md)
- [虚拟路测概览](docs/features/virtual-road-test/overview.md)

**开发指南**:
- [快速上手](docs/guides/quickstart.md)
- 状态机：正式测试的状态在 `TestExecution.status`，由 `api-service/app/services/test_case_runner.py` 驱动（原 TestPlan 状态机文档已随 ARCH-1 S4 归档至 [`docs/archive/state-machine-testplan.md`](docs/archive/state-machine-testplan.md)）
- [实现检查清单](docs/guides/implementation-checklist.md)

## 设计指南（来自 AGENTS.md）

项目正在遵循分阶段的 UI 改进计划：

**Phase 1**（当前）: Mantine 集成
- 使用 MantineProvider 建立主题基线
- 封装可重用组件（PageLayout, SidebarNav 等）
- 使用 Mantine AppShell/Stack/Grid 统一布局
- 用 Mantine Notifications/Badge 替换自定义状态指示器

**Phase 2**: 功能增强
- 实现暗黑模式切换
- 增强 ProbeLayoutView（集成 D3.js 或 Three.js 实现交互式 3D 可视化）
- 用于探头参数编辑的 FormSection 组件
- 一致的间距系统（8px 基准网格）

## 注意事项

### 当前状态（2025-12-11 更新）

**已完成功能**:
- ✅ 前后端完整架构 (React + FastAPI + SQLite)
- ✅ 测试例管理：编辑、直接执行、执行历史（ARCH-1 起以 TestCase 为根）
- ⚠️ **GUI 无新建用例入口** —— `TestCaseLibrary` 的新建按钮由 `onCreateNew` prop 守着，全仓无人传它；用例来自 bootstrap 种子。S4a 显式申报的能力缺口，在 backlog。
- ⚠️ ~~测试计划管理 / 步骤编排 / 执行队列~~ —— 已随 ARCH-1 S4 整体拆除，不再是功能
- ✅ 虚拟路测：场景库、ChannelEngine 集成
- ✅ 报告系统：PDF 生成、模板管理、执行历史
- ✅ Mock 服务器已禁用，Vite 代理配置完成

**进行中**:
- 🔄 GUI 功能完善 (Phase 4 - 约 70%)
- 🔄 硬件抽象层设计完成，驱动待实现

**待实现功能** (详见 `docs/Master-Progress-Tracker.md`):
- ⏳ Queue 重排序功能
- ⏳ 认证上下文（Auth Context）
- ⏳ 仪表盘告警系统
- ⏳ 报告对比功能
- ⏳ 硬件驱动集成
