# P2-67 — BaseStation 日志与导出可追溯性设计

**日期**：2026-09-02

**状态**：已批准 roadmap 的实施细化
**Roadmap**：P2-67（依赖 P1-75、P2-65、P2-66）

## 1. 可观察故障与本片目标

CMW500 执行 `31d3e29d-3b0f-4e5c-b391-0b629824e72d` 的公共租约收尾日志仍写成
“F64/UXM 控制会话已释放”，把 BaseStation 逻辑槽位误写成某一家仪表。另一次现场排查中，
两份附件虽然文件名不同，字节内容却完全相同，只能证明第一条执行
`7ae66c69-edc5-422e-8681-d8ad56c23e64`；现有导出文件名不含 execution id，文件正文也没有
筛选上下文、冻结 adapter/binding、TestCase RAT 或 compatibility verdict，附件脱离 GUI 后无法独立证明
“导出的到底是哪一次执行”。

P2-67 只修可追溯性：公共租约日志使用 vendor-neutral 文案并携带结构化冻结身份；按执行筛选的 JSONL
导出以服务器权威执行冻结为首条元记录，文件名包含完整 execution id，后续日志行保持原字节语义。
原始全量下载完全不变。

## 2. AGENTS.md 0.5 全集

| 事实 | 唯一真值 / 产生方 | 消费方全集 |
|---|---|---|
| 日志 execution id | `logging_config.current_execution_id` → `ContextFilter` | `app.log`、`scpi.log`、execution 文件、tail/history/export、GUI |
| 公共租约生命周期 | `InstrumentTestLease.hold()` | case runner、commissioning、诊断、自检、仪器控制、校准；取得/释放/idle park 三类公共日志 |
| 冻结 BaseStation 身份 | `config[base_station_adapter_profile_freeze]` | 锁内 validator、qualification、P2-66 outcome、本片租约审计上下文与导出元记录 |
| frozen adapter | freeze `resolution.adapter` | 租约审计、导出元记录；不得读当前 HAL driver 名称补真 |
| frozen binding | freeze `binding_digest` | 租约审计、导出元记录；不得用当前 LabProfile/connection 重算历史值 |
| TestCase RAT | freeze `compatibility.requirements.requested_rat` | 导出元记录；不得读已可修改的当前 TestCase 配置 |
| compatibility verdict | P2-66 `project_execution_evidence_outcome()` + 同一 freeze | 导出元记录；畸形冻结显式 invalid，不抛毒整个日志导出 |
| 屏幕/历史/导出筛选 | 后端 `_group_matches()`；GUI `buildLogQuery()` | `/tail`、`/history`、`/export`、SystemLogViewer 三个调用点 |
| 原始下载 | `/system-logs/download/{filename}` | GUI“下载原始日志（全量）”；本片不得改变 |

逐条同改判定：

1. `instrument_test_lease.py` 的取得、释放、idle park 文案都去厂商化；只有带执行冻结 validator 的租约
   才能携带 frozen adapter/binding，普通诊断/校准不得从 loaded driver 或 purpose 文本猜测。
2. `build_frozen_base_station_validator()` 把同一 freeze 投影为不可变审计上下文；commissioning 的组合
   validator 必须透传，不能在包装时丢失。
3. `/tail`、`/history` 和 `/export` 继续共用 `_group_matches()`；本片只在执行筛选导出的首行之前增加元记录，
   不把元记录送进屏幕查询，也不重写日志原行。
4. GUI 屏幕、翻页和导出继续三次调用唯一 `buildLogQuery()`；客户端不提交 adapter/RAT/verdict。
5. `/download`、execution 独立日志 writer、日志轮转、SCPI 专用日志与正式 KPI 无需同改。

## 3. 方案比较

### 采用：复用冻结 validator 通道 + 服务器执行投影

`build_frozen_base_station_validator()` 已通过 `validation_identity` 把冻结 digest 带到租约锁内。本片在同一个
回调对象上再携带不可变、只含 `adapter_id` 与 `binding_digest` 的审计上下文；租约只消费这份冻结上下文和
`ContextFilter` 自动注入的 execution id，不查询 DB、不读取当前 driver 名称，也不增加仪器 I/O。

导出端只在 `execution_id` 过滤存在时查询对应 `TestExecution`，从该行自己的 freeze 和 P2-66 outcome 构造
首条 `export_metadata`。元记录包含：导出时间、源文件、完整过滤条件、execution id、frozen adapter、binding
digest、requested RAT、compatibility classification/digest、completion semantic、formal eligibility 与 reasons。
文件名包含完整 execution id。不存在的 execution id 拒绝导出；畸形冻结仍允许导出审计日志，但元记录明确
`invalid`，未知字段保持 `null`，绝不从当前配置回填。

### 拒绝：从匹配日志的第一行推断 adapter/RAT/verdict

日志行只有 execution/instrument/logger 文本，不能证明当时冻结的 binding、RAT 或 compatibility；第一行还
可能因轮转、级别筛选或关键词过滤缺失。用它补真会把“能找到一条日志”误当成“配置证据完整”。

### 拒绝：由 GUI 把当前 adapter/RAT/verdict 一并提交给导出端

客户端状态可修改且不属于执行冻结；它会重现“界面显示一份配置，执行读取另一份配置”的 split-truth，附件
只能证明浏览器声称过什么，不能证明执行实际冻结过什么。

### 拒绝：给所有租约入口新增显式 adapter/binding 参数

多数租约用于校准、独立诊断或 idle park，没有 execution freeze。把参数穿过全部入口会扩大 API 并诱导调用方
从当前 driver/purpose 文本补值；复用已有冻结 validator 通道更窄，也天然只在有权威证据时填值。

## 4. 数据与错误语义

1. 公共租约日志文案只说“仪表控制会话”；结构化字段列出实际控制槽位，例如
   `controlled_instruments=["channelEmulator", "baseStation"]`，不再把 BaseStation 等同 UXM。
2. 有冻结上下文时，取得与释放日志同行携带 `base_station_adapter_id`、`base_station_binding_digest`；
   execution id 仍由统一 `ContextFilter` 注入。无 freeze 时字段保持缺省/空，不猜测。
3. 按 execution 筛选导出的第一行是保留类型 `record_type=export_metadata`；其后每一行仍是源日志中匹配行的
   原始 JSON/RAW 内容，保持现有顺序与 traceback 分组。
4. execution id 必须是合法 UUID 且数据库中存在；非法为 400，不存在为 404。这样附件不会声称筛过一个
   不存在的执行。
5. 显式新 freeze 畸形时，P2-66 outcome 是 invalid；导出仍是可用的故障审计包，但不生成正式有效假象。
6. 无 execution 过滤的普通导出保持既有“纯匹配日志行”形态与文件名，避免无关客户端被新增元行打破。
7. 原始 `/download` 永远不加元记录、不改名、不改内容。

## 5. 安全方向

- 把当前 GUI/HAL 值写成历史冻结值，会制造错误配置证据，可能让错误仪表组合看起来已被验证；
- 对畸形/缺失冻结保持 `null/invalid` 只会要求操作员回到执行证据排查，不会放行正式结论。

代价不对称，因此导出元数据只读 execution 自身冻结，不能从 mutable current state 补真；日志可保留用于诊断，
但元数据必须 fail-closed。

## 6. 非目标

- 不新增、修改或猜测 SCPI，不连接仪表；
- 不改变租约取得/释放顺序、安全收尾或 HAL reload 机制；
- 不修改正式 provenance 白名单、compatibility/qualification 判据或 KPI；
- 不改写历史日志内容，不批量回填旧执行；
- 不改变原始全量下载；
- 不提前实现 P2-54 及后续 roadmap 条目。

## 7. 验收

1. CMW500/UXM/未来第三 adapter 的执行租约日志使用同一 vendor-neutral 事件与结构化冻结身份。
2. 选择执行 A/B 时，屏幕与导出复用同一筛选条件；B 的导出不含 A 的日志。
3. A/B 导出文件名分别含完整 execution id，首条元记录可独立证明导出时间、过滤上下文、冻结 adapter、
   binding、RAT 与 compatibility outcome。
4. 客户端不能提交或覆盖元数据；current LabProfile、HAL driver 或 TestCase 后续变化不改变历史导出身份。
5. 畸形冻结导出明确 invalid/null，不 500、不补真、不形成正式有效假象。
6. 无 execution 过滤的普通导出与原始全量下载保持现有行为。
