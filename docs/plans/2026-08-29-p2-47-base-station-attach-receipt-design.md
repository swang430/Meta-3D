# P2-47 BaseStation 结构化 Attach Receipt 设计

## 目标与边界

本片解决一个可观察故障：共同执行器把 `start_signaling() -> bool` 当作相同事实，但 CMW500 的
`True` 已经依次证明 `CELL ON,ADJUSTED`、`PS ATTACHED` 和 `PS CONNECTED`，UXM 的 `True` 则只来自
一个把多种 connected-like 状态折叠成 `CellState.CONNECTED` 的查询。两者不是同等强度的
Cell Ready、注册、RRC 和数据承载证据；继续用布尔值会让下游把较弱诊断事实升级成正式 Attach。

本片只建立逐阶段、版本化、vendor-neutral 的 Attach receipt，并把现有 CMW500/UXM 权威回读映射
进去。零新增/猜测 SCPI，零数据库迁移，不改变 P2-48 测量窗口、P2-49 指标 registry、P2-51 CMW
MAC 或 P2-52 UXM closed-window 范围。模拟/未知阶段可保留诊断审计，但不能进入正式 KPI。

## 动手前全集

### 当前产生方

1. `BaseStationDriver.start_signaling()` 只声明 `bool`；`start_cell()` 直接转发该布尔。
2. `RealCmw500Driver.start_signaling()` 依次读 CELL、PS ATTACHED、PS CONNECTED，却只返回最终布尔；
   独立 RRC 阶段当前没有仪器回读。
3. `RealUxmDriver.start_signaling()` 写 Cell ON 后轮询 profile 状态查询；多个枚举被折叠成
   `CellState.CONNECTED`，没有独立 registration/data-bearer 证明。
4. `MockBaseStation.start_signaling()` 直接写缓存 CONNECTED 并返回 `True`，属于 simulated 诊断值。
5. P2-46 manifest 已为两家 adapter 声明四阶段静态 evidence 强度，但每次执行没有对应 receipt。
6. SCPI 基类已经给每次 write/query 生成 exchange id；当前 Attach 路径没有把这些 id 绑定到阶段。

### 当前消费方

1. MIMO OTA MEASURE 首次 Attach 直接读取 `signaling_started`；失败时中止，成功时丢失阶段差异。
2. 同一 MEASURE 的 bypass/fading/final 三个里程碑再次调用 `get_cell_state()`，只保存
   `attached: bool|null`，会把 UXM/CMW 的不同状态强度折成同一种绿色。
3. PRECHECK 读取 `dut_attach.rrc_connected` 与 live `get_cell_state()`；历史字段仍需兼容，但新执行
   不能再由自由布尔授予正式资格。
4. commissioning saved phase、adhoc、run-all 与 formal runner 都经 P2-42 单一 execution session
   进入 MEASURE；不能各写一套 Attach 逻辑。
5. `baseStation_attach_check` 是独立诊断序列，仍可保留兼容 `start_signaling()`，但不得冒充正式证据。
6. P2-43 `BaseStationExecutionEvidence.adapter_operations` 当前只存 config/route；formal envelope、站点
   certification、Analysis/Report/详情/下载/比较/history 最终都通过该 execution evidence 消费正式值。
7. 既有 CMW/UXM 真值测试、Attach milestone 测试、诊断测试和源码顺序门直接引用
   `start_signaling()` 字面，需要保持兼容或同步为新共同入口。

## 方案比较

### 方案 A：直接把 `start_signaling()` 返回值改成 receipt（拒绝）

语义最纯，但会一次打断大量诊断与历史集成入口；更危险的是旧调用点若用对象真值判断，会把失败
receipt 也当 `True`。本片不应依赖一次全仓原子迁移来避免假成功。

### 方案 B：保留布尔，只在旁边缓存最近阶段（拒绝）

缓存会跨 attempt/session 被后一次读取，重现“旧信息当新结果”；异常、取消和 cleanup 分支也很难保证
缓存与仪器一致。它不能提供 execution-bound exchange ids。

### 方案 C：新增权威 `attach()`，`start_signaling()` 变成兼容投影（采用）

`attach()` 返回不可变 receipt，并成为生产共同入口；每个 real adapter 在同一次调用内捕获已有 SCPI
往返并构造阶段事实。`start_signaling()` 只调用 `attach()` 后投影“本 adapter 当前最强可观察阶段是否
达到”，保留诊断脚本和旧集成测试，不参与正式证据。receipt 不实现 `__bool__`，避免误用。

## Receipt 合同

### `BaseStationAttachStageReceipt`

- `stage` 精确为 `cell_ready | ue_registered | rrc_connected | data_bearer_established`；
- `requested=true` 表示本次 Attach 请求希望达到该阶段；真正不适用时为 `null`；
- `applied=true|false|null`：`true/false` 必须来自本次调用的现有仪器回读，`null` 表示未获得该事实；
- `status=confirmed|unknown|not_applicable` 描述本次回读是否足以确认 `applied`，不把“没看见成功”
  自动写成 `false`；
- `evidence=authoritative|diagnostic_only|unavailable|not_applicable` 必须与当前 adapter manifest 同阶段
  精确一致；运行时 receipt 不能自行升级静态证据强度；
- `exchange_ids` 只引用直接证明该阶段的本次 SCPI 往返，可共享但必须非空、唯一。

`confirmed` 允许 `applied=false`，表示仪器权威证明阶段尚未达到；正式“达到”必须同时满足
`status=confirmed && applied=true && evidence=authoritative && simulated=false`。

### `BaseStationAttachReceipt`

- `schema_version=1`，四阶段精确一次、顺序固定；
- `adapter_id`、`simulated`、`reason`；
- `terminal_stage` 是 manifest 中最后一个非 unavailable/not-applicable 阶段，不能由调用方任意选择；
- `diagnostic_execution_allowed` 仅表示该 terminal stage 在本次操作中确实达到，或显式 simulated
  mock 操作成功；
- `formally_confirmed` 还要求 terminal stage 为 authoritative、本次真实且带 exchange ids；
- `exchange_ids` 从各 stage 去重派生；不保存自由 `attached=True`。

## Adapter 映射

### CMW500

复用现有同次序列，不加命令：

- `CELL ON,ADJUSTED` → `cell_ready` authoritative；
- `PS ATTACHED` → `ue_registered` authoritative；
- `rrc_connected` → unknown/unavailable（无独立回读，不从 PS 状态推断）；
- `PS CONNECTED` → `data_bearer_established` authoritative。

写被拒、状态枚举外、超时、异常或取消只保留已被本次回读证明的阶段；未证明阶段为 unknown，绝不从
请求值或 `_cell_state` 缓存回填。失败后的 SAFE cleanup 仍沿用现有保守路径。

### UXM

复用当前 profile 状态查询，不加命令。现有 parser 折叠了状态，不能拆出独立 registration/bearer：

- `cell_ready`、`ue_registered`、`rrc_connected` 按 manifest 保留 diagnostic-only；只有本次查询响应能
  给对应阶段 `applied`，其中 connected-like 只证明当前兼容 terminal `rrc_connected`；
- `data_bearer_established` 始终 unknown/unavailable；
- fallback 旧文本状态的来源强度不升级；枚举外、空回复、超时均 unknown。

因此 UXM 可继续诊断执行，但 receipt 的 `formally_confirmed=false`，直到后续手册/现场工作提供更强
的阶段证明；不能借 CMW500 的阶段语义补真。

### Mock

四阶段都输出 simulated/unknown、`applied=null`，并保留 `operation_succeeded=true` 供显式诊断流继续。
不得生成 confirmed stage 或 exchange id，正式消费者必定 fail-closed。

## Execution evidence 与共同消费

- 新增独立 `BaseStationAttachOperationEvidence`，绑定 current attempt、lease、adapter、session token 与
  receipt；同一 attempt/lease 只允许一条初始 Attach receipt。
- 新 execution 初始化显式 `attach_operations=[]`；历史 schema v1 若字段缺失保持缺失，避免重标历史。
- MEASURE 调用 `attach()`，在首次测量 I/O 前持久化 receipt；业务是否继续读
  `diagnostic_execution_allowed`，错误信息指出 terminal stage/evidence，而不是笼统 `False`。
- 新 execution 的 formal envelope 要求 current attempt 恰有一条 attach operation，且
  `formally_confirmed=true`；历史缺字段仍按原 provenance 合同读取，不从当前 policy/cert 回填。
- bypass/fading/final 里程碑改成 receipt/stage 投影：明确 stage、applied、status、evidence、simulated、
  exchange ids。后续 live probe 若只读 `get_cell_state()`，只能产生 diagnostic snapshot，不能覆盖首次
  execution-bound receipt 或恢复正式资格。
- PRECHECK 的旧 `rrc_connected` 保留显示兼容，但新结构存在时必须以 receipt/stage 为真值，畸形或
  unknown fail-closed。

## 错误与安全边界

- Attach 写操作仍消费错误队列；`*OPC?` 不单独代表成功。
- 取消继续传播；CMW 已尝试 Cell ON 后必须执行现有 shielded cleanup。UXM 本片不扩大异常集合、不新增
  自动重试或额外 stop 行为。
- exchange id 必须来自同一次 capture；confirmed authoritative stage 缺 id 时 writer 拒绝。
- `start_signaling()` 兼容布尔不得进入 production MEASURE 或正式证据 writer；规则门锁定这一点。
- 不改变 measurement window、cleanup/release 或正式 metric 白名单。

## 测试与验收

1. receipt 四阶段形状、不可变性、`confirmed false`/unknown/not-applicable 与证据强度不变量。
2. CMW 成功、CELL 未就绪、PS 未 Attach、PS 未 Connected、错误队列、超时、异常、取消均只记录本次
   已证明阶段并保留原 cleanup 行为。
3. UXM connected/idle/枚举外/profile fallback 精确映射，永不生成 authoritative/data-bearer 事实。
4. Mock 只生成 simulated unknown；任何消费方都不能把它变成正式 Attach。
5. writer 拒绝 attempt/lease/session/adapter/manifest evidence 分叉、重复写和无 exchange 的 authoritative
   confirmation；历史缺字段仍可读取。
6. formal/commissioning 五类入口共用同一 MEASURE attach 路径；生产源码不再消费
   `start_signaling()` 布尔。
7. 相关与全后端、rule gates、compileall、单一 Alembic head、diff-check、fresh 独立功能内审通过。

本片不改 GUI/OpenAPI：receipt 先作为 execution evidence 内部版本化 envelope；公开投影若确有用户入口，
必须先证明现有 API 消费路径，不能为“可能以后显示”提前扩面。
