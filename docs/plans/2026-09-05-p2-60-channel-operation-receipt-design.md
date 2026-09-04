# P2-60 设计稿 —— Vendor-neutral Channel Operation Receipt

> 状态：**已批准 roadmap 的实施细化**。用户已批准按 P2-60 → P2-61 → P2-62 连续推进；本稿不扩大到现场复验、P2-63 或新的厂商命令。
> 基线：`64b43e95`（P2-59② PR #456 合并后）；事实盘点于 2026-09-05 在独立工作树完成。

## ⓪ 动手前四行

- **搜索命中**：P2-59 已建立 `ChannelEmulatorManifest`、execution-frozen plan、唯一 `channel_emulator_execution_scope`、SAFE_IDLE/release 与 `channel_emulator_terminal_evidence`；P2-66 的 `_channel_emulator_terminal_projection` 已是正式输出门；P2-67 的 execution-filtered JSONL 首条 `export_metadata` 已公开冻结执行身份与共同 outcome。
- **必要性**：现有终态只证明“一次 CE 会话最终安全结束”，`operation_succeeded=True` 仍是调用者布尔握手。它不能回答某次 load/configure/start/adjust 到底请求了什么、设备接受了什么、回读确认了什么，也不能把拒绝、超时或取消绑定到原始 exchange。
- **范围**：只覆盖 execution-bound 的 MIMO OTA 四类入口（formal、commissioning run-phase、adhoc、run-all）及它们的唯一公共 CE 会话；手工仪表端点、路径损耗校准和诊断序列已枚举，但它们没有 execution-frozen binding/plan，保持诊断语义且不得生成正式 receipt。
- **爆炸半径**：新会话写 v2 终态并要求逐操作 receipt；既有 v1 终态按原规则解析，不追溯重判历史。F64 只映射已有 exchange/回读；FS16 未实现操作为 `unavailable`；Mock 为 `simulated`。不新增/猜测 SCPI，不改变正式 provenance 白名单。

## 1. AGENTS.md 0.5 全集

### 1.1 权威产生方

1. **静态能力**：`app/hal/channel_emulator_manifest.py` 的 26 项 `operation × support` 与 load mode；它只回答“允许调用什么”，不回答“本次是否生效”。
2. **冻结意图**：`app/hal/channel_emulator_execution_plan.py` 与 `app/services/channel_emulator_execution_plan.py`；冻结 adapter、load mode、26 项 planned、阶段顺序、binding/plan digest。
3. **会话身份与安全终态**：`app/services/channel_emulator_execution_session.py`；唯一 session id、operation scope、lease/instrument、SAFE_IDLE、transport release 与 v1 terminal evidence。
4. **原始往返索引**：`app/hal/scpi_evidence.py::capture_scpi_exchanges()`；每条 exchange 带 execution/capture/instrument/sequence/result_type/simulated，响应正文不进入 receipt。
5. **F64 已有权威回读**：`app/hal/propsim_f64.py` 现有加载文件、仿真状态、旁路、中心频率、输入/输出/crest/拓扑等回读与 `f64.*` 已确认目录项。没有目录/回读的字段保持 unknown。
6. **FS16 与 Mock**：FS16 manifest 明确未实现的操作不得用基类桩或布尔默认值伪装成功；Mock 复用真实命令拼装，但所有观察值均 simulated。

### 1.2 execution-bound 消费/调用点

- **load**：`services/channel_generation/{gcm,asc,external_asc,b2_parametric}_strategy.py` 经 `load_channel` 或已有加载原语。
- **configure/adjust**：`MeasureExecutor` 的 output level/gain、input reference、crest、topology 与 input-level closed loop；`InputLevelController` 的 autoset、measurement mode、trigger、measure/limits/clipping/status。
- **start/stop**：attach 直通、fading start、普通运行启动；`channel_emulator_execution_scope` 的 `stop_emulation` / `clear_passthrough_mode` SAFE_IDLE。
- **cleanup/release**：scope 内唯一 SAFE_IDLE 与 `instrument_test_lease` 的真实 Remote/Local release 结果；旧 `cleanup_chamber_instruments` 在 scope 内不重复停止。
- **正式消费**：`execution_evidence_outcome.py` → history/report/analysis/download/API/GUI 共同输出；`system_logs.py` 的 execution-filtered JSONL metadata 用于离线审计。

### 1.3 已枚举但不进入正式 receipt 的入口

- `api/instrument.py` 的手工 topology/output/input 操作；
- `path_loss_calibration_service.py` 的 tone/passthrough；
- `diagnostics/sequences/*` 的 F64 原子诊断；
- scope 外的旧 cleanup。

这些入口没有同一 execution 的 asset/binding/plan digest。给它们补“半套正式 receipt”会制造第二真值；本片只保证它们不能被 P2-66 当成正式执行证据。

### 1.4 历史与失败路径

| 形态 | 新行为 |
|---|---|
| pre-P2-60、terminal schema v1 | 继续按 P2-59 规则校验；不要求不存在的 receipt |
| 新 schema v2、receipt 缺失/畸形/摘要漂移 | `invalid`，阻断正式输出 |
| 写返回 False / 设备拒绝 | 记录 `rejected`，不得写 applied/confirmed |
| 异常 / timeout | 记录 `failed` + error type；不吞主异常 |
| cancellation | 记录 `cancelled`；仍继续 SAFE_IDLE/release |
| SAFE_IDLE 失败 | receipt 与 terminal 都保留失败，正式门 fail-closed |
| release 未确认 | release receipt/terminal 均不确认，正式门 fail-closed |
| Mock | receipt 可供诊断，但 `simulated=true`，不进入正式 KPI |
| FS16 未实现 | `unavailable`，首个 I/O 前拒绝，不补占位成功 |

## 2. 方案比较

### A. 追加式、逐操作的独立 receipt 链（采用）

每次 effectful CE 调用由共同 recorder 包裹，追加一条不可变 receipt；会话 terminal v2 只引用 receipt 链摘要/数量和最终安全结果。

优点：失败与取消也能在 terminal 之前落证；重试可按 `(session_id, operation_scope, invocation_id)` 区分；不把巨大操作明细塞进一个终态对象；P2-66 可以独立重算。

### B. 把所有操作嵌进 terminal evidence（不采用）

只有退出 scope 时才形成对象，异常期间数据库失败会同时丢操作与终态；重试/commissioning append 语义复杂，且终态 schema 会承担两类职责。

### C. 复用 BaseStation SCPI evidence（不采用）

现有 envelope 的 identity、attempt/window 与 adapter profile 都是 BaseStation 语义。硬塞 CE 会引入跨仪表字段和第二套 compatibility 真值。

## 3. 数据模型

新增 `app/services/channel_emulator_operation_receipt.py`，保存到：

```text
TestExecution.config.channel_emulator_operation_receipts
```

### 3.1 `FrozenChannelOperationField`

- `field`: 稳定字段路径；
- `requested`: canonical JSON 值或 `null`；
- `applied`: 只有现有权威回读/终态证明时才有值；
- `status`: `requested | applied | confirmed | unknown | not_applicable | unavailable`；
- `provenance`: `authoritative_readback | command_error_queue | runtime_state | transport_release | simulated | unavailable`；
- `exchange_ids`: 只保存脱敏索引；
- `source_reference`: 仅复用现有目录/手册出处，未知则为 `null`。

`requested` 不是“已生效”；错误队列 clean 最多证明命令未被该队列拒绝，不能单独把字段升级为 applied/confirmed。

### 3.2 `FrozenChannelOperationReceipt`

- identity：`schema_version=1`、`receipt_id`、`session_id`、`operation_scope`、`execution_id`、`measurement_attempt_id`；
- frozen chain：`binding_digest`、`binding_freeze_digest`、`plan_digest`、可选 `asset_digest`；
- lease：`lease_id`、`instrument_id`、`adapter_id`、`execution_mode`；
- invocation：严格递增 `sequence`、`phase`（load/configure/start/adjust/stop/cleanup/release）、`operation`、`invocation_id`；
- outcome：`terminal_state`（completed/rejected/failed/cancelled）、`operation_succeeded`、`simulated`、`error_type`；
- evidence：字段 tuple、全部 exchange ids、error-queue exchange ids；
- `digest`：覆盖原始 payload 的 canonical digest。

组合约束：

- simulated receipt 不得有 confirmed 字段；
- rejected/failed/cancelled 不得声称 operation_succeeded；
- unavailable 必须零 exchange；
- real completed 也不自动等于 confirmed；
- 每个 exchange 必须属于同一 execution/capture/instrument，sequence 保持原始顺序；
- receipt identity 必须与同 session 的 frozen binding/plan/lease 精确一致。

### 3.3 terminal evidence v2

`FrozenChannelEmulatorTerminalEvidence` 接受 v1/v2；新 scope 只写 v2。v2 额外冻结：

- `operation_receipt_count`；
- `operation_receipts_digest`（按 receipt sequence 的 canonical 链摘要）；
- `required_operation_scopes`/最终 `safe_idle` 与 `release` receipt identity。

v1 校验继续对原始 v1 payload 算摘要；不得先补字段再重算旧 digest。

## 4. recorder 与调用约束

共同入口提供 async `record_channel_emulator_operation(...)`：

1. 从 task-local CE session owner 读取 session、frozen digests、lease/instrument；scope 外调用只能产生 diagnostic receipt，正式执行路径则 fail-loud。
2. 先检查 frozen plan：load 看 `load_mode_planned`，其余操作看 `plan.planned(operation)`；unavailable 在 I/O 前落证并拒绝。
3. 进入 `capture_scpi_exchanges()` 后调用原方法，按 True/False/异常/timeout/cancel 分类；不改变厂商调用顺序。
4. 调用 adapter 的**纯证据投影协议**，只解释已经存在的 exchanges/readback；共同层不匹配 SCPI 字面量、不推断厂商语义。
5. 追加 receipt；再向调用者返回原值或重抛原异常。receipt 持久化失败不能让业务结果假成功。

为防止漏站点，规则门要求 execution-bound effectful CE 调用只出现在 recorder/驱动内部/明确的诊断排除清单中。只读 getter 可保留直调，但进入正式判定的值必须来自对应 receipt 字段。

## 5. adapter 证据边界

### 5.1 F64

- load：复用已有 `f64.model_load` 的 FILE/OPC/error/model-state/center-frequency exchanges 与公开 loaded-file 真值；
- start/stop：复用现有 simulation state 终态；
- passthrough：复用已有 bypass readback；
- output gain/loss/level、input reference/crest：只在现有写后回读存在且目录范围匹配时填 applied/confirmed；
- topology/input measurements/system status：只读 observation 也形成 receipt，但 observation 不能证明此前写操作生效；
- 只有 bool 或 clean error queue、没有回读的字段保持 unknown。

### 5.2 FS16

manifest 为 `not_implemented/not_applicable` 的操作一律 `unavailable`，零 I/O；不能借 F64 命令或基类默认返回制造成功。已实现且有 FS16 自身证据的操作再单独映射，本片不补命令。

### 5.3 Mock

继续复用目标驱动的真实纯命令拼装；receipt 全部 `simulated=true`，字段最多 requested/unknown，不得 confirmed，不进入正式 KPI。

## 6. P2-66 正式门

`_channel_emulator_terminal_projection` 增加版本化分支：

- terminal v1：保持 P2-59 既有行为；
- terminal v2：验证完整 receipt 链、terminal 链摘要、身份、顺序和 SAFE_IDLE/release 对称记录；
- 当前成功 session 中任何 effectful operation 为 unavailable/rejected/failed/cancelled、receipt 缺失或有影响正式测试的字段仍 unknown → `invalid`；
- simulated → `diagnostic`；
- 只有同一 frozen execution 的 real、完整、未篡改且要求字段 confirmed 的链可保留 formal eligibility。

运行中 execution 不因尚未产生 terminal/receipt 被提前判 invalid；当 measurement attempt 已完成或 pipeline completed 时才要求完整终态链，沿用 P2-66 的既有时机规则。

## 7. 对外投影

- 后端提供只读 `ChannelEmulatorOperationEvidenceProjection`：按 session/sequence 输出状态、字段、provenance、exchange ids 与 reasons，不输出原始响应；
- Case execution status、history detail/report 使用服务器投影，不由 GUI 重算；
- P2-67 execution-filtered JSONL 的首条 `export_metadata` 加同一投影摘要与 receipt-chain digest；普通全量导出、raw download 不变；
- live OpenAPI、`api/openapi.yaml`、generated TS、手写 GUI 类型四镜像同步；History 只显示服务器状态，不把 unknown 画成绿色。

## 8. 原子性与并发

- receipt 追加与 terminal 追加都按 TestExecution 行锁；同 `receipt_id` 相同 payload 幂等，不同 payload 冲突；
- session owner 在 lease acquire 后绑定实际 instrument，替换 HAL/driver 不能混入 receipt；
- operation receipt 先持久化，terminal 最后引用已经校验的链；terminal 若引用数量/摘要不一致则 fail-closed；
- 失败业务事务先 rollback，再独立持久化失败 receipt/terminal；主异常保留，持久化失败作为 secondary failure 附加。

## 9. 明确不做

- 不新增、修改或盲试任何 SCPI；
- 不改变 F64/FS16 已有参数域和正式 provenance 白名单；
- 不把本地测试当现场复验；
- 不把手工/诊断入口伪装成 execution-bound 正式证据；
- 不启动 P2-63、现场项、P2-32、P3-20/P3-21 或其他 feature。

## 10. 验收

1. load/configure/start/adjust/stop/cleanup/release 均有可验证 receipt，拒绝/timeout/cancel/safety failure 都有消费方；
2. F64 仅有据字段 confirmed，未知保持 unknown；FS16 未实现为 unavailable；Mock 仅 diagnostic；
3. terminal v2 与 receipt chain 绑定，篡改/串 execution/session/lease/instrument/digest 均 fail-closed；
4. terminal v1 历史不追溯重判；
5. 正式 KPI 无 simulated/unknown/diagnostic 值；
6. 相关/全后端、GUI 契约/build、compileall、单一 Alembic head、diff-check 与 fresh 功能内审通过。
