# P2-68 — 损坏仪器认证不能隐藏整张仪器目录 设计

> 状态：**v1 已批准**（2026-09-11 用户：「都按你的推荐来」），随实现分支入仓。roadmap 条目：`docs/roadmap-first-call.md` `### P2-68`。
> 来源：#458 行内发现 3938243884（P2，Codex，2026-09-04）+ 2026-09-05 复盘独立 triage 复现。

## 1. 可观察故障与目标

**故障**：`GET /api/v1/instruments/catalog`（`app/api/instrument.py::get_instrument_catalog`）把每条
`InstrumentConnection` 的 JSON 列原样塞进严格 Pydantic 模型 `FEInstrumentConnection`。任何一条连接的
`channel_emulator_site_certification` / `base_station_site_certification` 缺字段或 schema 不符，
`_convert_connection` 抛 `ValidationError`；端点尾部 `except Exception` 捕获后返回
`FEInstrumentsResponse(categories=[])`。结果：**一条坏认证 → GUI 整张仪器目录消失**，操作员既看不到
坏在哪，也无法用正常入口修复；同一个兜底还把真实 DB 故障伪装成「零仪器」。

2026-09-05 复现（`a0c671c4`，生产函数 + 内存对象 + fake query）：损坏认证 → 0 类；同一连接改为无认证 → 1 类。
2026-09-11 复核 HEAD `b4e840e0`：`instrument.py:468-470` 仍是 `except Exception → categories=[]`；
`_convert_connection`（:247-288）仍直接构造。

**目标**：一条连接的某个存储字段损坏，只影响那个字段的投影 —— 该字段显式标 invalid、其余
category / model / connection 照常显示；正式资格门对损坏证据继续 fail-closed；DB 故障照实返回 5xx。

## 2. 全集与权威源（生产入口 → 权威判据 → 正式消费者 → 可观察断言）

> 本节行号是 2026-09-11 复核 HEAD `b4e840e0` 时的值，改动合入后会漂移；以符号名为准。

### 2.1 会让「整目录丢失」的路径（同一入口、同一机制，全部枚举）

`get_instrument_catalog` → 逐 category `_convert_category`（:416）→ `_convert_connection`（:247）。
`_convert_connection` 里五个来自 JSON 列的子投影，任一抛错即整目录为空：

| # | 存储字段（`InstrumentConnection` 列） | 现在怎么解析 | 畸形输入下 | 权威判据（写方 / 正式门共用） |
|---|---|---|---|---|
| 1 | `base_station_site_certification` | 直接进 `Optional[BaseStationSiteCertification]` | `ValidationError` | `execution_qualification.parse_base_station_site_certification`（:225，畸形 → `ValueError("stored BaseStation site certification is invalid")`） |
| 2 | `channel_emulator_site_certification` | 同上（CE 模型） | `ValidationError` | `channel_emulator_certification.parse_channel_emulator_site_certification`（:734，畸形 → `ValueError`） |
| 3 | `base_station_model_presets` | `parse_base_station_model_presets`（:61） | `ValueError`（docstring：malformed stored data fails loud） | 同函数 |
| 4 | `channel_emulator_model_presets` | `parse_channel_emulator_model_presets`（:75） | `ValueError`（docstring：库里存坏了就大声失败，绝不静默丢项） | 同函数 |
| 5 | `connection_params` | 直接进 `Optional[Dict[str, Any]]` | 非对象（如 list / 字符串）→ `ValidationError` | 无专用解析器；判据 = `isinstance(dict)` |

另一个能进同一函数的入口：`PUT /instruments/{category_key}`（`update_instrument_category`，:2248）的三个
返回点 :2398 / :2519 / :2634 都经 `_convert_category` → 同一 `_convert_connection`。但 PUT 在到达响应投影**之前**
就先 `parse_*(connection.xxx_model_presets)`、先 `dict(connection.connection_params or {})`（内审探针实跑：
三列坏值下 PUT 一律 500、什么都没写；两认证列不在 PUT 读取路径上，PUT 200）。所以修 `_convert_connection`
覆盖的是：**目录入口 × 五列 + PUT 入口 × 两认证列**；PUT 对坏 preset / connection_params 的 500 是 PUT 自己的
逻辑（main 上已如此），进 Discovered，不在本片。

`InstrumentConnectionResponse`（`app/schemas/instrument.py:89`）也带两个认证字段，但 `app/` 下**零使用点**
（grep 只命中 schema 自身），不是活路径。

### 2.2 不在「整目录丢失」路径上、但读的是同一份坏数据（枚举结果，本片不改）

| 站点 | 现状 | 处置 |
|---|---|---|
| readiness `base_station_site_certification`（`instrument.py:4261-4266`） | `model_validate` 失败 → `except ValidationError: None`，损坏被当作「未认证」静默投影 | 与本片同母题但可观察面不同（readiness 显示「未认证」而非「损坏」），⑦ 判越界 → 报告，进 Discovered 候选 |
| readiness `channel_emulator_site_certification_preview`（`channel_emulator_certification.py:554-563`） | 已按权威解析器 fail → `status="invalid"`、`reasons=("site_certification_invalid",)`、detail「服务器保存的信道仿真器现场认证无效」 | **本片的形态参照**（#458 意见原文：consistent with the readiness projection） |
| 正式门 BS：`freeze_execution_qualification`（`execution_qualification.py:283`，:338 调 parse，无 try） | `ValueError` 直接上抛 → `base_station_adapter_profile.py:352` → 启动拒绝 | 已 fail-closed；本片只加回归证明它不因目录修复而松动 |
| 正式门 CE：`freeze_channel_emulator_execution_qualification`（`channel_emulator_certification.py:804`，:900 调 parse，无 try） | 同上，上抛到 `test_case_runner.py:319` / `commissioning.py:1731` | 同上 |
| 认证写入/撤销（`activate_* / revoke_*`，:575 / :1313 调 parse） | 当前值损坏 → `ValueError` → 422 | 保持：坏数据不能被「撤销」路径静默覆盖；操作员修复入口是重新认证（PUT certification）或人工清库，本片不新增修复端点 |

### 2.3 GUI / 契约消费方（改契约就要四镜像同改）

| 镜像 | 位置 |
|---|---|
| 后端 schema | `app/api/instrument.py::FEInstrumentConnection`（:100-120） |
| checked OpenAPI | `api/openapi.yaml::InstrumentConnection`（:2735，`additionalProperties: false` + `required` 全列） |
| 生成 TS | `gui/src/types/api.generated.ts`（`npm run openapi:generate`） |
| 手写 TS | `gui/src/types/api.ts::InstrumentConnection`（:81-94） |
| mock 数据（类型约束） | `gui/src/api/mockDatabase.ts` :1052-1053 / :1102 / :1124 / :1166 / :1208 五处 connection 字面量 |
| 显示 | BS 认证徽标 `App.tsx:2587-2596`（今天二态：active → 绿「已认证」，否则黄「未认证或已撤销」——损坏会被显示成「未认证」）；CE 抽屉走 readiness preview（:2512-2521，已有 `invalid` 红态） |

### 2.4 值的形态空间（每个 JSON 列都过一遍）

`NULL`（未认证 / 无 preset，合法）｜合法对象｜合法但 `status="revoked"`（合法，不是 invalid）｜
缺必填键｜类型错（list / 字符串 / 数字）｜未知 `schema_version`｜preset map 键 ≠ `model_id`（解析器判为坏）。
前三种维持今天行为；后四种 = 本片的「损坏」。

### 2.5 库里真实分布（加标记前先查）

见本稿末尾「实测分布」；设计前提：开发库绝大多数连接这五列为 NULL，坏数据来自 #458 时代的 schema 演进与
手工写库，不是常态 —— 所以「白名单式：解析成功才显示，失败显式标记」不会把大批正常数据误标。

## 3. 方案选择

| 方案 | 做法 | 评价 |
|---|---|---|
| A（推荐） | `_convert_connection` 改为**容错投影**：五个子投影各自用权威判据解析；失败 → 该字段投影为 `null` / `{}`，并写入新字段 `invalid_fields: {字段名: 原因}`；其余字段照常。`get_instrument_catalog` **去掉** `except Exception → []`，DB / 编码故障按 FastAPI 默认 500 上抛 | 修法形状 = 去掉（兜底）+ 换源（认证改走 parse_*）+ 收窄（失败面从整目录收到单字段）；一处改动覆盖两入口五路径；与 CE readiness `invalid` 形态一致 |
| B | 只隔离两个认证字段，preset / connection_params 不动 | 「一条坏字段 → 整目录消失」在相邻三列上原样存在；同根同机制却分两片做 |
| C | 逐 category 兜底：某 category 转换失败就整条丢弃、其余保留 | 操作员仍找不到坏项（那台仪器整个不见了），也没有「明确 invalid」；不满足验收 |
| D | 只置 `null` 不加字段 | 损坏与「未认证」不可区分，违反「损坏认证明确 invalid/unavailable」 |

**A 的边界**：只动读投影，不动任何解析器（它们的 fail-loud 是写方 / 正式门的契约，保持）；不新增修复端点；
不改 readiness。

## 4. API 与 GUI 合同（方案 A）

`FEInstrumentConnection` 新增：

```python
invalid_fields: Dict[str, str] = Field(default_factory=dict)
# 键 ∈ {"base_station_site_certification", "channel_emulator_site_certification",
#        "base_station_model_presets", "channel_emulator_model_presets", "connection_params"}
# 值 = 权威解析器给出的中文/英文原因（截断到 200 字）。字段出现在这里时，其正常投影一律为 null / {}。
# 语义分两类（Codex #471 R1 P2）：两个现场认证损坏 → 正式执行不能获得资格；两个 preset map 与
# connection_params 损坏 → 只影响配置草稿 / 连接参数投影，正式门 freeze_* 不读它们。
```

- `openapi.yaml::InstrumentConnection`：加 `invalid_fields: {type: object, additionalProperties: {type: string}}`，
  进 `required`；description 写明键集合（G9 门：description ⊇ 枚举取值）。
- `api.generated.ts` 重生成；`api.ts::InstrumentConnection` 加 `invalid_fields: Record<string, string>`；
  `mockDatabase.ts` 五处 connection 字面量补 `invalid_fields: {}`（只为满足类型，mock 已禁用）。
- GUI 抽屉连接区块：`invalid_fields` 非空时显示红色 Alert，逐字段给出**按字段区分**的提示（认证：影响正式资格、可重新认证覆盖；
  preset：只影响草稿、服务器会拒绝保存需管理员修库；connection_params：已按空显示、普通保存不再发送空草稿）+ 服务器原因；
  **保存路径收窄**（Codex #471 R1 P1）：`connection_params` 被标坏且操作员未填新 JSON 时，BS / CE 的显式全字段保存**不发送**
  该键 —— 否则 `dict()` 可转换的坏形态（如 `[["k","v"]]`）会被服务器接受并用 `{}` 覆盖原值、再按 P2-72 用空配置激活 HAL；
  纯逻辑放在 `gui/src/features/Equipment/invalidStoredFields.ts`（`invalidStoredFieldHint` / `withoutSynthesizedConnectionParams`）；
  **Codex R2 / R3 P1 后定稿为三态 provenance**（用户 2026-09-11 拍板 A）：草稿带 `connection_params_origin: 'server' | 'invalid' | 'operator'`
  （`nextConnectionParamsDraft`）—— 'server' 从有效服务器值灌入且未动；'invalid' 标坏时初始化（文本恒空）；'operator' 操作员改过
  （rfSwitch JsonInput / CE alignment / BS·CE 切型号选 preset）。服务器标坏时 'operator' 保留、其余清空标 'invalid'（灌入的旧文本不可信，R3）；
  修好时 'invalid' 用服务器值重建并连带重建派生的 BS profile 草稿（R2），'server' / 'operator' 沿用（不重刷未保存编辑、不跨型号重建）。
  守卫 `connectionParamsGuarded`：origin 'invalid'，或标记存在且 origin ≠ 'operator' → 不发送 connection_params **与** BS 的
  `base_station_adapter_profile`（库里就是同一字段的子键，草稿同样是灌入派生；被守卫时也不在客户端校验合成出来的空 profile）；
  派生的 BS profile 草稿与文本共用来源：行变坏且非 operator 一起清空，修好一起重建；BS profile 字段编辑同样标 'operator'；
  alignment 输入框的禁用同一判据；BS 认证徽标改三态：active → 绿；`invalid_fields` 含 BS 认证键 →
  红「认证数据损坏」；否则黄「未认证或已撤销」。CE 侧已有 readiness `invalid` 红态，本片只保证目录侧
  同一连接 `invalid_fields` 与 preview `status="invalid"` 同时成立（回归断言）。

不新增端点、不新增 SCPI、不改 provenance 白名单、不改正式门。

## 5. 实现点

1. `app/api/instrument.py::_convert_connection`：
   - `base_station_site_certification` → `parse_base_station_site_certification`，`except ValueError` → 记 invalid；
   - `channel_emulator_site_certification` → `parse_channel_emulator_site_certification`，同上；
   - 两个 preset → 现有 parse_*，`except ValueError` → `{}` + 记 invalid；
   - `connection_params` → 非 `dict` 且非 `None` → `None` + 记 invalid；
   - 其余字段不变。
2. `get_instrument_catalog`：删除 `try/except Exception → categories=[]`（保留日志由框架异常处理器负责）。
3. 契约四镜像 + GUI 呈现（§4）。

## 6. 验收门与变异（每道门先跑红再跑绿）

| 门 | 形态 | 断言 | 让它红的变异 |
|---|---|---|---|
| G1 行为门（参数化 ×5 字段） | 真 SQLite `StaticPool` + `TestClient`，两条 category：一条连接对应字段存坏值，另一条正常 | 200；两条 category 都在；坏连接该字段为 `null`/`{}` 且 `invalid_fields` 恰含该键；正常连接原样 | 把 `_convert_connection` 的某一路 `except ValueError` 删掉 → 整目录空 → 红 |
| G2 行为门 | 同上，坏 preset 的连接其**认证字段仍正常投影**（字段级隔离，不是连接级） | `base_station_site_certification` 非 null 且 `invalid_fields` 只含 preset 键 | 改成「任一失败即整个 connection 置空」→ 红 |
| G3 行为门（DB 故障诚实） | monkeypatch `Session.query` 抛 `OperationalError` | 响应 5xx，不是 200 `[]` | 把 `except Exception → []` 加回 → 红 |
| G4 正式门不松动 | 用同一份坏认证调生产 `build_channel_emulator_certification_preview` → `status == "invalid"`；两个 `parse_*_site_certification` 对同一坏值抛 `ValueError`；`freeze_execution_qualification` 源码确实调用 `parse_base_station_site_certification`（无 try）。实现记录：`services/` 零 diff，:338 / :900 两处调 parse 均无 try —— 正式门未动 | 与 G1 同一份坏数据 | 让 `_convert_connection` 把坏认证「修补」成合法对象再投影 → G4 仍绿但 G1 的 `invalid_fields` 断言红（两门互锁） |
| G5 不变量门 | `invalid_fields` 允许键集合 == `_convert_connection` 里受保护子投影集合（模块常量 `PROJECTED_STORED_FIELDS`），且 == OpenAPI description 里列出的键 | 三处相等 | 加一个受保护字段却不更新常量 → 红 |
| G6 契约门 | 既有 G11（openapi ⊆ live schema）+ `gui/test/apiContractAlignment.test.ts` 加 `invalid_fields` 断言 + `npm run build` | — | 删 openapi 字段 → G11 红 |
| G7 PUT 入口 | `PUT /instruments/{category_key}` 保存 endpoint 时该连接带坏认证 → 200 且响应含 `invalid_fields` | — | 由 G1 的变异一并覆盖（同函数） |

全量：本片改共享契约（`FEInstrumentConnection` 四镜像）→ 按验证分档跑一次后端全量 + GUI production build。

## 7. 非目标（枚举到、不做、进报告）

- readiness BS 认证的 `except ValidationError: None` 静默投影（:4261-4266）—— 同母题不同可观察面，报告待 triage。
- `PUT /instruments/{category_key}` 对库里坏 preset / `connection_params` 在投影前 500、GUI 保存无法覆盖 —— PUT 自身逻辑，main 上已如此，进 Discovered。
- GUI 目录页对 5xx 仍显示「暂无仪器信息」空态（无 `isError` 分支）—— 本片按拍板 Q3 只改 API 层；操作员视角的区分进 Discovered，待用户决定是否补一个错误分支。
- 新增「修复 / 清除损坏认证」端点 —— 修复入口仍是重新认证（PUT）或人工清库；不加机制。
- `InstrumentConnectionResponse` 死 schema 的清理 —— 与故障无关。
- 解析器行为、schema_version 迁移、认证内容的正确性 —— 不动。
- 目录 GUI 的其它显示问题 / SCD 投影归属（Discovered 既有条目）—— 不动。

## 8. 拍板记录（2026-09-11，用户对五问全部按推荐拍板）

- **Q1 隔离范围** → A：五条「整目录丢失」路径在 `_convert_connection` 内统一隔离（两认证 + 两 preset + `connection_params`）。
- **Q2 契约形态** → 单一 `invalid_fields: Dict[str, str]`，不加每字段 `*_error` 兄弟字段。
- **Q3 DB 故障** → 去掉 `get_instrument_catalog` 的 `except Exception → categories=[]`，让 5xx 上抛。
- **Q4 GUI 呈现** → 抽屉连接区块红 Alert + BS 认证徽标三态；目录卡片层不加角标。
- **Q5 readiness BS 认证 `except ValidationError: None`** → 只报告进 Discovered，不并入本片。

## 实测分布（2026-09-11 只读查询开发库 `meta3d_ota`）

`SELECT id, 五列 FROM instrument_connections`，逐行过生产解析器（`parse_base_station_site_certification` /
`parse_channel_emulator_site_certification` / `parse_base_station_model_presets` /
`parse_channel_emulator_model_presets`，`connection_params` 判 `dict`）：

| 列 | 非 NULL 行数 / 7 | 解析失败 |
|---|---|---|
| `base_station_site_certification` | 0 | 0 |
| `channel_emulator_site_certification` | 0 | 0 |
| `base_station_model_presets` | 1 | 0 |
| `channel_emulator_model_presets` | 1 | 0 |
| `connection_params` | 3 | 0 |

结论：开发库今天**没有**坏数据，故障是 #458 复盘用构造数据复现的**故障类**（schema 演进 / 不兼容版本 /
手工写库），不是现存事故；白名单式「解析成功才显示」不会误标任何现存行。现场库未查（本次不接现场）。
