# GUI「新建测试用例」入口 — 设计稿

> 状态：**已拍板，实施中**（v1.1，2026-07-31 用户拍板：待决①-④全部甲案，
> 「描述 ⊇ 枚举」门按 §5 建议进 backlog 不在本片做）
> 起因：ARCH-1 S6（浏览器闭环总验）的验收第一步「建用例」在 GUI 上不可达
> Roadmap：ARCH-1 S6 前置（roadmap `Discovered during X` 区
> `[discovered 2026-07-29 during ARCH-1 S4a]` 那条）
> 双实证：memory ✅（5 条，见 §0）/ NotebookLM **不适用**（GUI + 已有 API 接线，不涉 UXM / F64 SCPI）

---

## 0. 先摆事实（全部当场核过，不凭记忆）

### 0.1 断在哪一环

| 环节 | 状态 | 证据 |
|---|---|---|
| 后端 `POST /api/v1/test-plans/cases` | ✅ 在 | 真实路由表 |
| 前端 API 函数 `createTestCase` | ✅ 在 | `api/service.ts:407`、`api/testPlanService.ts:186` |
| `App.tsx:74` 导入它 | ⚠️ **死 import** | 全仓零调用点 |
| `TestCaseLibrary` 新建按钮 | ❌ 被 `{onCreateNew && …}` 守着 | `TestCaseLibrary.tsx:321` |
| 唯一渲染点 | ❌ **没传 `onCreateNew`** | `TestManagement.tsx:63` `<TestCaseLibrary enableExecute={true} />` |

**后端和 API 客户端都是通的，只是没有任何 UI 元素能走到它们。**

**为什么删的时候没人发现**：`onCreateNew` 是**可选 prop** + `{onCreateNew && ...}` 条件渲染。
入口原本挂在 StepsTab 上，S4a 删了 StepsTab 之后 —— TypeScript 不报错（可选 prop 不传合法）、
按钮不是崩而是**静默消失**、GUI 侧无测试框架。**三层保护全都不响。**

### 0.2 建一个「能真执行」的 MIMO_OTA 用例，最少需要什么？

**实测：一个名字。**

```
MIMOOTAConfiguration.model_validate({})  →  ✅ 通过（54 个字段全有默认值）
```

执行正门不直接吃 `configuration`，而是把它当 **overrides** 喂给工厂
（`test_case_runner.py:139` → `build_mimo_ota_test_case(config_overrides=...)`），
工厂再 `MIMOOTAConfiguration.model_validate(overrides)` 并从
`resolve_lab_profile(db, None)` 兜底拿实验室。

**所以 MVP 的表单可以极小** —— 这条实测把本片的成本判断整个改了。

### 0.3 ⚠️ 最大的坑：**照默认建出来的用例会立刻隐形**

| 事实 | 出处 |
|---|---|
| 用例库端点默认只列模板 | `list_test_cases_grouped(is_template: Optional[bool] = True)` |
| `TestCaseCreate.is_template` **默认 `False`** | `schemas/test_plan.py:28` |

**合起来：新建 → 不是模板 → 库里看不到 → 既不能编辑也不能执行。**
用户点了「新建」，东西进了库但界面上消失了。**这个洞必须在本片堵掉**，否则新入口等于没有。

### 0.4 库里现在有什么（S6 的另一条退路是否成立）

真库 `MIMO_OTA` 共 **188** 行，但：

| 构成 | 数量 |
|---|---|
| `is_template=True`（**库里可见的模板**） | **6** |
| `created_by=commissioning_api`（暗室首测会话行） | ~180 |
| 执行快照 / runner 产物 | 1 |

库端点的 `is_template=True` 默认值把那 180 行挡在视图外，**所以库是干净的**，
S6 的退路（「改现有 MIMO_OTA 模板」）**成立** —— 有 6 个可用。
本片不是"没它就不能干活"，而是**补齐一条被误删的能力**。

### 0.5 顺带核出的两处不一致（本片不一定修，见 §4）

- **`TestCaseCreate.test_type` 的描述漏了 `MIMO_OTA`** ——
  枚举 `TestCaseType` 里有（`models/test_plan.py:41`），但请求 schema 的 description 写的是
  `TRP | TIS | Throughput | Handover | MIMO | ChannelModel | VirtualRoadTest | Custom`。
  **这段描述进 OpenAPI，是 GUI 开发和外部调用方唯一会读的东西。**
- **`create_test_case` 不校验 `test_type`**，也不校验 `configuration` —— 裸插行。
  MIMO_OTA 的校验只在 execute 时由工厂做（fail-loud，报错明确）。

### §0 附：memory 实证命中

| 规则 | 对本片的约束 |
|---|---|
| `feedback_gui_two_verification_gates` | GUI 改动两道门：`npm run build`（`tsc -b`）+ **浏览器实测闭环**。build 绿只是入场券 |
| `feedback_effective_end_not_nominal` | **"入口可达"要打在真实生效端** —— 验收不是"传了 prop"，是**点得到按钮、建得出用例、建完看得见、看得见的能执行** |
| `feedback_api_contract_sync_after_pydantic_change` | 若改 Pydantic 字段，走契约四步（openapi.yaml + 生成类型 + service.ts + mockServer） |
| `feedback_react_query_shape_change_needs_new_key` | 若改列表查询的返回 shape，必须同时换 queryKey |
| `project_testcase_driven_instrument_arch` | TestCase 是驱动全仪表层级的单一真值源；**路径 B 绝不用默认 fallback 静默兜底** —— 见 §3 待决③ |

---

## 1. 目标与不做

**目标**：让操作员能从「测试用例库」新建一个**可直接执行**的 MIMO_OTA 用例，
把 S6 的验收第一步接通。

**不做**：
- 不做「另存为 / 复制现有用例」的端点（后端无 duplicate 路由，加端点=加机制，超范围）
- 不改 `TestCaseEditModal` 让它兼做创建（见 §3 待决②）
- 不动 VRT 的建场景路径（那条能建 TestCase，但落 `test_type=VIRTUAL_ROAD_TEST`，
  执行正门 `test_case_runner.py:123` 明确拒绝 —— 那是有意的 fail-loud，不是缺陷）
- 不清理库里那 180 行 commissioning 会话行（库已按 `is_template` 挡住，不构成问题）

---

## 2. 方案（推荐形态）

### 2.1 新增一个轻量 `TestCaseCreateModal`

只有三个输入：

| 字段 | 说明 |
|---|---|
| **名称**（必填） | 唯一必填项 |
| **起点**（可选，默认「空白」） | 下拉选一个现有 MIMO_OTA 模板 → 把它的 `configuration` 复制进新用例当起点 |
| **类别**（可选，默认「我的用例」） | 落到 `template_category`，决定它在库里归到哪一组 |

**类型固定为 `MIMO_OTA`，不给选** —— 本片的目标就是接通直接执行路径，
其它类型今天执行正门不认（`test_type != MIMO_OTA` 直接拒）。给选=给用户造一个建完跑不了的坑。

### 2.2 提交后的动作

```
POST /api/v1/test-plans/cases
  { name, test_type: "MIMO_OTA", configuration: <空白 {} 或所选模板的 configuration>,
    is_template: true, template_category: <类别>, created_by: <见待决④> }
   ↓ 201
关闭创建弹窗 → 直接打开 TestCaseEditModal(新 id) 让用户改参数
   ↓
用户在既有的 MIMOOTAConfigForm 里调参 → 保存 → 库里点执行
```

**两步（建壳 → 编辑）而不是一个大表单**：仪表参数表单
（`components/TestCaseConfig/MIMOOTAConfigForm`，S4a 从已删的 StepsTab 搬过来的）
已经在编辑弹窗里跑得好好的，**复用它比再造一份强**，也避免"创建"和"编辑"两套表单漂移。

### 2.3 接线

`TestManagement.tsx` 加一个 state + 把 `onCreateNew` 传下去：

```tsx
const [creating, setCreating] = useState(false)
...
<TestCaseLibrary enableExecute={true} onCreateNew={() => setCreating(true)} />
<TestCaseCreateModal opened={creating} onClose={...} onCreated={(id) => { ... }} />
```

**`TestCaseLibrary` 与 `TestCaseEditModal` 都不改**（除非待决②选了另一条路）。

> **实施具体化（2026-07-31）**：编辑弹窗实际挂在 `TestCaseLibrary` **内部**
> （私有 `editingId` state），`TestManagement` 够不到它。为兑现"建完直接进编辑"
> 且不改这两个组件：`TestManagement` 自己再渲染一个 `TestCaseEditModal` 实例
> （组件可复用，闭态零开销），并用 `key={epoch}` 重挂载 `TestCaseLibrary`
> 触发列表刷新（activeRun 的挂载时恢复路径 S2 #237-C3 已建好，重挂载安全；
> epoch 递增不是一次性 latch，可重复触发）。

---

## 3. 待决（2026-07-31 已全部拍板 —— 均选甲案）

> 拍板记录：用户 2026-07-31 批准「接受你的建议」：①甲（`is_template=true` +
> 类别「我的用例」）②甲（新建独立 `TestCaseCreateModal`）③甲（create 宽松 /
> execute 严格；全默认配置定性为**捷径**非静默兜底，UI 标注"参数在编辑页填，
> 执行时校验"）④甲（`created_by="gui"`，接认证上下文后换真实用户已记 backlog）。

### 待决① 新建的用例怎么在库里可见？（**必须选一个，否则入口等于没有**）

| 选项 | 做法 | 代价 |
|---|---|---|
| **甲（我倾向）** | 建时带 `is_template=true` + `template_category="我的用例"` | 一行搞定、立刻可见、复用库既有的分组维度。**语义有点脏** —— 用户建的不是"标准模板" |
| 乙 | 库改成也拉 `is_template=false`，加「我的用例」分区 | 语义干净，但**要新造一条过滤判据**把那 180 行 commissioning 会话行挡掉（`created_by not in {commissioning_api, test_case_runner}`）——**加机制**，且判据本身会漂 |

倾向甲的理由：乙引入的过滤判据是新机制，而且"哪些算会话产物"这个集合会随新增写入方漂移
（正是 ARCH-1 反复吃亏的枚举题）。甲只借用已有维度。
若你认为语义更重要，乙也能做，但建议单独一片。

### 待决② 复用 `TestCaseEditModal` 还是新建组件？

`TestCaseEditModal` 今天是**纯编辑**：`!testCaseId` 直接 return（`:74`），
保存走 `updateTestCase(testCaseId, ...)`（`:129`）。

- **甲（我倾向）新建一个 `TestCaseCreateModal`** —— 编辑弹窗保持单一语义
- 乙 给编辑弹窗加 create 分支 —— 少一个文件，但让它同时处理"有 id / 无 id"两态

倾向甲：S5 反复吃亏的就是"一个东西两套语义"（`StepLike` 的 ORM/描述符两支、
报告的三种关联落法）。两态组件的 `useEffect` 依赖和保存分支很容易漂。

### 待决③ 创建时要不要校验 `configuration`？

现状是 **create 宽松 / execute 严格**：`POST /cases` 裸插行不校验，
执行时工厂 `MIMOOTAConfiguration.model_validate` fail-loud（422，报错明确）。

- **甲（我倾向）维持现状**，UI 上说清"参数在编辑页填，执行时会校验"
- 乙 create 时也校验

倾向甲：① execute 侧已经 fail-loud 且信息足够；② 在 create 加校验=加机制；
③ 空配置本来就合法（§0.2），"先建个壳再慢慢填"是正常工作流，不该被拦。

⚠️ 但这跟 `project_testcase_driven_instrument_arch` 的"**路径 B 绝不用默认 fallback
静默兜底**"有张力 —— 需要你确认：**新建用例走全默认配置，算"捷径"还是算"静默兜底"？**
我的读法是**捷径**（跟 bring-up / 暗室首测同类，用户明知在建一个待填的壳），
而不是"正式测试路径上偷偷用默认值"。**这条请明确，它决定 UI 上要不要显眼地标"未配置"。**

### 待决④ `created_by` 填什么？

后端 `TestCaseCreate.created_by` 是**必填**，而 GUI 今天**没有认证上下文**
（`api-service/app/auth/dependencies.py` 里 `require_auth` 已零使用点，S4c 申报过）。

- **甲（我倾向）** 硬编码 `"gui"`，并在 backlog 记一条"接认证上下文后换成真实用户"
- 乙 给个输入框让用户填名字

倾向甲：多一个必填框只为凑一个没人校验的字段，是给操作员添麻烦。

---

## 4. 门（诚实分档）

### D-1 【行为门 · 后端】新建→执行 端到端

一条真行为断言（后端可测，不受 GUI 无测试框架的限制）：

```
POST /cases {test_type: MIMO_OTA, configuration: {}, is_template: true}
  → 201, 拿到 id
GET /cases/grouped  → 该 id 在返回里（**堵 §0.3 那个"建完即隐形"的洞**）
POST /cases/{id}/execute → 不 422（即工厂能从空配置构出可执行配置）
```

**变异**：把 `is_template` 改回 `false` → 第二条断言必须红。

### D-2 【编译门】`npm run build`（`tsc -b`）

新组件 + prop 接线的语法/类型层。**只是入场券。**

### D-3 【运行门】浏览器实测闭环 —— **本片的验收主体**

按 `feedback_gui_two_verification_gates`，且验收要打在**真实生效端**：
点得到按钮 → 建得出用例 → **建完在库里看得见** → 看得见的那个能执行 → 执行历史有行。
**不是"传了 prop 就算通"。**

### D-4 【申报：无门】GUI 侧没有测试框架

新组件的渲染逻辑、弹窗状态流转**没有任何会红的门**，只有 D-2 的类型层 + D-3 的人工闭环。
判错不会红 —— 如实申报，不假装有覆盖。

---

## 5. 顺带发现，本片不修（记 backlog）

- **`TestCaseCreate.test_type` 的描述漏 `MIMO_OTA`**（§0.5）——
  这段进 OpenAPI，是 GUI 开发和外部调用方唯一会读的东西。改它要走契约四步，
  且"描述 ⊇ 枚举"其实可以做成**会红的门**（同 S5 的 G7/G8 思路）——
  **加机制，规则⑤ 要求停下来报告，等拍板。**
- **`App.tsx:74` 那个死 import `createTestCase`** —— 本片接通后若仍无人用，应删。
  是否删取决于待决②（新组件从哪 import）。
- 库里 180 行 commissioning 会话行 —— 今天被 `is_template` 挡住，不构成问题；
  若将来选了待决①的乙案，它们会变成必须处理的噪声。

---

## 6. 验收

1. **D-1 行为门**通过，且"把 `is_template` 改回 false → 断言红"的变异实跑过
2. `npm run build` 绿
3. **浏览器实测闭环**：建→见→改参→执行→历史有行，截图为证
4. 待决①-④ 的选择写进 PR body（选了什么 + 为什么）
5. ⓪⁺ 全流程：内审 agent → Codex 270s 四通道 → merge → 迟到回查
