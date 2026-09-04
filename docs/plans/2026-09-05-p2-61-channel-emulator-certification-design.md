# P2-61 设计稿 —— Channel Emulator Diagnostic/Formal Certification

> 状态：**已批准 roadmap 的实施细化**。用户已批准按 P2-61 → P2-62 串行推进；本稿不扩大到现场认证、P2-63 或新的厂商命令。
> 基线：`64a58832`（P2-60 PR #457 合并后）；事实盘点于 2026-09-05 在独立工作树完成。

## ⓪ 动手前四行

- **搜索命中**：P2-57～P2-60 已建立 Channel Emulator manifest、resolver/binding、分型号 preset、execution-frozen plan、唯一 execution session、逐操作 receipt、SAFE_IDLE/release 终态与 P2-66 共同正式输出门；现有持久 site certification 只有 BaseStation 一套。
- **必要性**：当前 CE 只证明“本次执行链完整”，没有“这台真实仪器在这个 LabProfile/连接/选件/资产范围内已通过本站点认证”的服务器记录。未来 adapter 只要单次运行成功，就可能被误当成可发布正式 KPI。
- **范围**：新增 CE 专用、服务器持有、可撤销的 site certification；第一次完整真实执行仍是 diagnostic，只用于派生认证；认证只影响之后新建并冻结的执行。现有执行、报告和现场结果不追溯升级。
- **爆炸半径**：新增一个 connection JSON 列、一个独立 execution qualification 冻结件、terminal v3 的硬件身份快照、专用 API/只读 readiness/GUI 投影及共同 outcome 校验。不新增/猜测 SCPI，不改变正式 provenance 白名单，不把本地测试写成现场认证。

## 1. AGENTS.md 0.5 全集

### 1.1 当前权威产生方

1. **Lab/连接与型号**：`InstrumentCategory.selected_model_id`、`InstrumentConnection` 活动连接和 `channel_emulator_model_presets`；执行真值仍是活动 connection，preset 只是分型号已保存草稿。
2. **adapter 能力**：`app/hal/channel_emulator_manifest.py::ChannelEmulatorManifest`；只声明型号能力，不证明当前站点已认证。
3. **binding**：`app/services/channel_emulator_binding.py` 的 resolver、preview 与 `channel_emulator_binding_freeze`；冻结 LabProfile、connection、transport、adapter/manifest 与 binding digest。
4. **plan/asset**：`app/services/channel_emulator_execution_plan.py` 的 load request、asset resolution、execution plan 与 plan/asset digest。
5. **真实会话与逐操作证明**：`channel_emulator_execution_session.py`、`channel_emulator_operation_receipt.py`；同一 execution/session/lease/instrument 下记录 load/configure/start/adjust/SAFE_IDLE/release，P2-60 已区分 requested/applied/confirmed/unknown/simulated。
6. **频率/level/path-loss**：频率一致性与 path-loss application 在同一 completed execution 的 MEASURE 结果中；level/path-loss 的设备应用证明来自 P2-60 receipt。不能从当前 GUI 配置、HAL 缓存或报告文本回填。
7. **正式输出**：`execution_evidence_outcome.py` 是 history/report/analysis/download/JSONL/GUI 的共同判据。P2-61 只扩展这个共同投影，不在消费者中复制 CE 厂商分支。
8. **Diagnostic 审计**：现有 `TestCaseExecutionPolicy` 是显式 policy 真值；自动因认证缺失降级时，执行创建者 `executed_by` 与服务器 reason code 共同冻结，不能留下匿名黄色状态。

### 1.2 全部冻结入口

- 正式 Case runner：`services/test_case_runner.py`；
- commissioning saved phase/session/run-all/adhoc：`api/commissioning.py::_freeze_instrument_lease` 的五类调用方；
- BaseStation profile/qualification 当前先冻结，CE binding 与 plan 随后冻结；P2-61 的 CE qualification 必须紧跟 CE plan，并位于任何仪器 I/O 前；
- 已有硬件/phase/measurement 进度的 execution 不得回填新 qualification。

### 1.3 全部消费方

- connection/catalog：`schemas/instrument.py`、`api/instrument.py::_convert_connection`、设备资源抽屉；
- readiness：`GET /instruments/hal/readiness`、Dashboard `ZoneReadiness`、TestCase 配置提示；
- execution：`project_execution_evidence_outcome`、status/detail/list、commissioning session/phase、analysis/report；
- history/download：历史页、报告详情/PDF、报告重建、execution-filtered JSONL metadata；
- 合同镜像：live OpenAPI、`api/openapi.yaml`、generated TS、手写 TS、mock fixture；
- 历史数据：pre-P2-61 execution 无 CE qualification；已有 terminal v1/v2；已有 connection 无 CE certification。

### 1.4 失败与变化路径

| 场景 | 处理 |
|---|---|
| 无认证 / 已撤销 / scope 漂移 | 新执行冻结为 diagnostic；黄色披露，正式 KPI UNKNOWN/N/A |
| 显式 diagnostic policy | 始终 diagnostic；认证不能提升 |
| Mock / simulated | 可诊断运行，永不生成或匹配 active certification |
| malformed certification / qualification | fail-closed 为 invalid/diagnostic，不从 current state 修复 |
| source execution 非 completed、非 TestCase、证据不完整 | 认证 API 422，事务回滚 |
| binding/plan/asset/identity/options/receipt/frequency/level/path-loss/SAFE_IDLE/release 任一缺失 | 认证 API 422，不降格成部分正式认证 |
| 认证撤销 | 只改变 connection 当前记录；已冻结历史执行不变 |
| connection/model/options/firmware/serial/binding 改变 | 后续执行 scope mismatch → diagnostic；历史执行不变 |
| pre-P2-61 execution | 保持 legacy 语义，不追溯要求不存在的认证 |
| terminal v1/v2 | 原始摘要仍按原版本校验；不能用于创建 P2-61 认证 |

## 2. 方案比较

### A. 独立 CE certification + 独立 CE execution qualification（采用）

connection 保存当前 CE site certification；execution 在 CE binding/plan 后冻结一份独立 qualification，并由 P2-66 将 BaseStation qualification 与 CE qualification合并。

优点：不改变 BaseStation qualification schema/digest；历史兼容边界清楚；CE 证据和撤销独立；P2-62 第三 adapter 只需实现 adapter 证据，不改共同消费者。

### B. 把 CE 字段塞进现有 `ExecutionQualification`（不采用）

现有对象是 BaseStation binding/site certification 的历史冻结件。扩版本会让大量旧摘要、历史 parser 和 BaseStation 专用 API 承担 CE 语义，也会把两个仪器的锁序与迁移绑死。

### C. 只在 completed 时查当前 connection certification（不采用）

执行期间撤销、切型号或改 connection 会追溯改变正在运行/历史结果；current state 还能给旧 execution 补真，违反“变化只影响后续执行”。

### D. 复用 rollout bool/env/GUI 开关（不采用）

它们没有 source execution 与证据摘要，无法证明站点、仪器、资产和安全终态；客户端或部署配置会变成正式授权入口。

## 3. 持久模型

### 3.1 `ChannelEmulatorHardwareIdentityEvidence`

为新 CE execution session 的 terminal v3 增加不可变硬件身份快照：

- `instrument_id`、`adapter_id`、`model`、`firmware_version`、`serial_number`；
- canonical `options`（允许“已确认无选件”的空 tuple），以及独立的 `options_observed`；
- `captured_from_live_connection`、`simulated`；
- 身份/选件各自已有的 `source_reference`；
- `digest`。

adapter 只把 **connect 已经取得并仍绑定当前 live transport** 的缓存投影到该对象；不得为认证新发命令。F64/FS16 复用既有 `*IDN?`/`SYST:INFO?`/选件探测链和手册出处；选件探测失败不能与“确认零选件”折叠，必须由 `options_observed=false` 区分。缺必需身份或未完成选件观察使 Formal 认证失败。Mock 明确 `simulated=true`。

terminal v1/v2 继续按原始 payload/digest 解析；新 writer 只写 v3。冻结 qualification 时先取得同一 live identity 快照，session acquire 后再次取得并与冻结快照精确对齐，防止 reload/换机拼接。

### 3.2 `ChannelEmulatorCertificationProofs`

服务器从 source execution 构造，不接受请求体布尔：

- `binding_plan_asset`；
- `hardware_identity_options`；
- `operation_receipts`；
- `frequency`；
- `level`；
- `path_loss`；
- `safe_idle`；
- `transport_release`。

八项必须全为 `true`。同时保存对应 frozen/receipt/result digest，布尔只作可读分类，不能脱离摘要独立授权。

### 3.3 `ChannelEmulatorSiteCertification`

保存到：

```text
InstrumentConnection.channel_emulator_site_certification
```

严格字段：

- `schema_version=1`、`status=active|revoked`；
- scope：`lab_profile_id`、`instrument_connection_id`、`instrument_model_id`、`binding_digest`、`adapter_id`；
- plan/asset：`plan_digest`、`asset_digest`、load mode；
- hardware：model/firmware/serial/options 与 identity digest；
- source：`source_execution_id`、terminal/receipt chain/measurement evidence digest；
- proofs；
- audit：certified/revoked actor、time、reason；
- `certification_digest` 由全部原始字段 canonical 计算。

旧 connection 为 `null`，绝不 migration/backfill 为 active。客户端不能通过普通 connection PUT 写整份 certification。

### 3.4 `ChannelEmulatorExecutionQualification`

保存到：

```text
TestExecution.config.channel_emulator_execution_qualification
```

包含：

- `classification=formal|diagnostic`；
- `policy_mode`、`diagnostic_actor`、`diagnostic_reasons`；
- BaseStation qualification digest 链接；
- CE binding/plan/asset/identity digest 与 connection/adapter scope；
- 冻结的 certification + certification digest；
- `frozen_at`、qualification digest。

Formal 必须同时满足：显式/默认 Formal policy、real configured binding、v2 plan、完整 live identity、active certification，且 certification scope 与本次 binding/plan/asset/identity 精确一致。否则只冻结 diagnostic；显式 malformed 数据直接拒绝创建或在读取时 invalid。

## 4. 认证派生

专用 API 只接收：`source_execution_id`、操作人、原因。服务按统一锁序读取/锁定：

```text
source TestExecution → InstrumentCategory/LabProfile → InstrumentConnection
```

然后只从同一 source execution 验证：

1. `status=completed`、真实 TestCase/LabProfile；
2. frozen CE binding、load request、plan、asset 结构与摘要完整；
3. 当前服务器 resolver 仍解析到请求的 connection/model/adapter/binding；
4. terminal v3 hardware identity 与冻结 identity 相同，真实且 model/firmware/serial/options 完整；
5. P2-60 所有有效 session/receipt 属于同 execution/attempt/lease/instrument，链摘要一致，不能 simulated/unknown/unavailable/rejected/failed/cancelled；
6. 同一 MEASURE 结果的 frequency consistency 完整通过，且 F64/目标 CE 身份确实参与；
7. level 与 path-loss 必须分别有当前 attempt 的 confirmed receipt；path-loss application 还必须是 real/applied/verified；
8. terminal 的 final SAFE_IDLE 与 release receipt 均 confirmed。

认证动作不连接仪器、不重跑命令、不查询报告文本。任一检查失败返回 422 并 rollback；成功一次 commit 当前 active certification。source execution 自身因“认证尚缺”仍保持 diagnostic，不被追溯洗成 Formal。

## 5. 冻结与共同正式门

### 5.1 冻结顺序

所有入口统一为：

```text
BaseStation profile + BS qualification
→ CE binding
→ CE plan/load/asset
→ CE hardware identity snapshot
→ CE execution qualification
→ positioner / 其它冻结件
→ commit / 后台执行
```

已有 CE qualification 必须原样校验复用；部分存在、摘要漂移或已有执行进度均 fail-loud，不准重冻。

### 5.2 P2-66 合并规则

- 无 CE qualification：pre-P2-61 legacy，沿用当前 CE terminal/receipt 规则，不追溯改判；
- explicit diagnostic：共同 `qualification_classification=diagnostic`，即使 operation chain 完整也不能正式；
- formal qualification：必须在完成时再次用冻结 binding/plan/asset/terminal identity/receipt 对齐 certification；
- malformed/tampered/scope mismatch：`invalid`；
- 最终 `formal_eligible` 要求 BaseStation qualification formal、CE qualification formal、兼容性 compatible、CE terminal/receipt verified、pipeline completed。

所有 report/history/download/analysis/JSONL 继续只消费 `ExecutionEvidenceOutcome`。不得在 GUI 或报告层直接读取 certification bool 再另算绿色。

## 6. Readiness 与 GUI

服务器新增 `ChannelEmulatorCertificationPreview`：

- `status=formal_ready|diagnostic|invalid|not_applicable`；
- 当前 binding/plan/identity/certification 摘要；
- server reasons；
- 当前 active/revoked certification（只读）。

`GET /instruments/hal/readiness` 和设备 catalog 返回该共同投影。GUI：

- 信道仿真器资源抽屉提供 source execution、操作人、原因及 certify/revoke；
- Dashboard/TestCase 只按服务器 status/reasons 显示绿/黄/红；
- 黄色明确“可诊断执行，正式 KPI UNKNOWN/N/A”；
- 不在浏览器比较 binding/plan/options，不缓存旧绿色，不把 Mock 画成已认证。

## 7. 原子性与并发

- certification activate 采用 execution → category/LabProfile → connection 锁序，和 resolver/freeze 一致；
- revoke 只锁 connection，保留完整 source proof 与认证审计，不物理删除；
- qualification 与其它 execution freeze 在创建事务中原子提交；任一失败整条 execution 创建 rollback；
- 普通 connection save/preset 切换不得覆盖 certification，但 scope 改变后 readiness/新 execution 自动 diagnostic；
- 同一 connection 并发 certify/revoke 最终只有一份 canonical server-owned 状态，旧请求不能覆盖较新的 scope。

## 8. 历史兼容边界

- migration 只加 nullable JSON 列；旧行不认证；
- pre-P2-61 execution 没有 CE qualification，保持 legacy；
- terminal v1/v2 可读但不得作为新 certification source，因为缺 P2-61 hardware identity/options 冻结证据；
- 新 execution 明确带 CE qualification 后，删字段或保留旧 digest 必须 fail-closed；
- 认证撤销、代码升级或 current HAL 变化不能追溯修改历史 execution 的冻结 classification。

## 9. 明确不做

- 不执行任何现场认证，不声称 F64/FS16 已取得 Formal certification；
- 不新增、修改、试探或猜测任何 SCPI；
- 不改变 F64/FS16 manifest 支持域和正式 provenance 白名单；
- 不允许 Mock、本地测试、env、旧 rollout bool、GUI payload 生成认证；
- 不启动 P2-63、现场项、P2-32、P3-20/P3-21 或其它 feature。

## 10. 验收

1. 第一次完整真实执行只能 diagnostic，并可由服务器证据派生 active certification；该执行本身不追溯升级；
2. 后续同 scope 新执行才可 Formal；撤销或 binding/model/identity/options/asset 变化只使后续执行 diagnostic；
3. source execution 任一 proof 缺失/篡改/串 execution/session/lease/instrument 都拒绝认证；
4. Mock/simulated/unknown/diagnostic 绝不进入正式 KPI；
5. pre-P2-61 与 terminal v1/v2 历史保持原语义；
6. API/GUI/OpenAPI 四镜像只消费服务器投影；
7. 相关/全后端、GUI 契约/build、compileall、单一 Alembic head、diff-check 与 fresh 功能内审通过。
