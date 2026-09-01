# P2-66 — BaseStation 执行证据不变量与终态语义设计

**日期**：2026-09-01
**状态**：已批准 roadmap 的实施细化
**Roadmap**：P2-66（依赖 P1-75、P2-65）

## 1. 可观察故障与本片目标

Mock 对照复盘中，一条执行同时记录了 UXM adapter、只声明 NR5G 的 manifest 与 LTE TestCase
请求，流水线仍以 `TestExecution.status=completed` 生成 PDF。既有 Diagnostic/Formal 与 provenance
门正确把正式 KPI 保持为 UNKNOWN/N/A，但历史列表、报告标题、下载和比较仍容易把“流水线跑完”
解释成“配置正确、测试有效”。

P1-75 已在新执行首次仪器 I/O 前拒绝不兼容组合，P2-65 已让 preview/sync/readiness/freeze 共用
同一 requirements/verdict。P2-66 负责读侧与证据终态：任何带新 compatibility snapshot 的执行，
都只能由它自己的冻结证据判定为有效测试、诊断执行或证据无效；历史没有 snapshot 的行保留
既有 provenance 规则，不用今天的 catalog、manifest 或配置猜测回填。

## 2. AGENTS.md 0.5 全集

| 事实 | 唯一真值 / 产生方 | 消费方全集 |
|---|---|---|
| 流水线生命周期 | `TestExecution.status` 列及其终态 CAS writer | 用例轮询、执行历史、报告生命周期、站点认证 |
| BaseStation binding freeze | `config[base_station_adapter_profile_freeze]`，由 `freeze_base_station_adapter_profile()` 一次写入 | measure 首次 I/O 前复核、qualification、P2-66 读侧投影 |
| compatibility snapshot | freeze 内的 `compatibility.requirements + verdict` | P1-75 锁内复核、P2-65 preview/readiness、P2-66 全部读侧 |
| freeze outer digest | freeze 除 `digest` 外 canonical JSON 的 SHA-256 | P2-66 解析；不得只验证内层、放过同行字段篡改 |
| requirements digest | `BaseStationExecutionRequirements.digest` | verdict 归属校验、P2-54 未来版本边界 |
| manifest digest | 冻结 verdict 的 `manifest_digest`，必须与同一 freeze 的 `resolved_binding.manifest` 对账 | 只作为当时声明的不可变指纹；历史读取不得查当前 registry 反推，也不得拼接另一 adapter 的 compatibility |
| Diagnostic/Formal | `config[execution_qualification]` 的冻结 qualification + digest | analysis/report/history/compare/ReportDataCollector |
| 执行证据终态投影 | 本片新增的纯 `project_execution_evidence_outcome()` | 证据解析、轮询、历史、报告构造/重建/详情/下载、比较、GUI |
| 正式 KPI | 既有 qualification、SCPI、校准、逐指标 trust 白名单的 AND 门 | 本片不放宽；invalid/diagnostic 只再增加 fail-closed 条件 |

需要逐条同改的生产消费路径：

1. `base_station_adapter_profile.py`：已有 freeze 的复用与新 freeze 持久化；
2. `execution_scpi_evidence.py`：公开证据解析/终态公开；
3. `mimo_ota/executors/analysis.py` 与 `report.py`：正式判词、数值与 PDF content；
4. `report_data_collector.py`：汇总、数值、统计、表格和 SCPI evidence；
5. `report_service.py`：重建、stored content、详情/下载 trust、执行对比；
6. `api/test_execution.py` 与 `api/test_plan.py`：历史列表和执行详情；
7. `api/report.py`：列表、详情、下载；
8. GUI History、ExecutionSelector、ReportList/Viewer 及 API/OpenAPI 四镜像。

## 3. 方案比较

### 采用：执行自己的冻结证据派生单一只读投影

新增不可变 `ExecutionEvidenceOutcome`，不写数据库，只输出：

- `compatibility_classification`：`compatible | diagnostic | legacy | invalid`；
- `completion_semantic`：`valid_test_completed | diagnostic_completed | pipeline_completed | not_completed`；
- `formal_eligible`：只有显式 compatible + formal qualification 才为 `true`；
- `compatibility_digest`、`qualification_classification` 与结构化 `reasons`；
- 原始 `pipeline_status`，明确它仍是生命周期而不是测试有效性。

解析只读执行自身：

1. 无 freeze 或无 compatibility 键是 `legacy`，继续既有 provenance 行为；
2. 显式 freeze 必须是封闭结构，outer digest 必须匹配；
3. requirements/verdict 必须通过 Pydantic，requirements digest 必须匹配 verdict；
4. `compatible` 必须与冻结 adapter/binding 形状自洽；
5. `no_adapter` 只允许 frozen `diagnostic_unbound + simulated + adapter=null`；
6. `incompatible`、畸形、digest 漂移一律 `invalid`；
7. qualification 的 binding digest/status、execution mode 与 adapter 必须和同一 freeze 的 resolution
   精确一致；formal 只允许 real + configured，模拟 binding 即使被错误标成 formal 也 fail-closed；
8. qualification 缺失沿既有 legacy 规则；显式畸形继续 fail-closed 为 diagnostic。

完成语义只是一层展示/消费投影：

- `status != completed` → `not_completed`；
- explicit compatible + formal → `valid_test_completed`；
- compatible/no-adapter + diagnostic → `diagnostic_completed`；
- legacy 或 invalid 即使 `status=completed` 也只叫 `pipeline_completed`。

这样 `TestExecution.status` 仍是唯一生命周期真值，P2-66 不新增第二套状态机。

### 拒绝：扩展 `TestExecution.status` 或新增终态数据库列

`completed` 的唯一真值源已经覆盖 case runner、commissioning、取消 CAS、报告延迟发布和历史过滤。
新增枚举/列会复制状态机、引入迁移与多 writer 同步，且无法自动修正历史证据，范围远大于本片故障。

### 拒绝：报告、历史、比较各自判断

这会把同一 snapshot parser 和状态组合复制到至少七处，下一次 schema 扩展必然产生镜像漂移。

### 拒绝：用当前 manifest/catalog 重新计算历史兼容性

当前注册表会升级，TestCase 与 LabProfile 也会修改；拿今天的真值重写昨天执行，会让历史结果随部署
变化，违反执行冻结与审计不变量。

## 4. 数据与错误语义

1. `legacy` 仅表示执行早于 compatibility snapshot；不得批量回填，也不得因为缺 snapshot 直接抹掉
   既有显式真实 provenance。
2. `invalid` 表示执行声称带新 snapshot 但证据不自洽；它不能进入正式 KPI、通过率、有效测试计数或
   正式比较。可保留审计包，但标题、列表和下载元数据必须写明“证据无效/仅审计”。
3. `diagnostic` 保留既有可下载审计包；正式数值、统计与判词继续为空/UNKNOWN/N/A。
4. `valid_test_completed` 只说明兼容性和 qualification 允许进入正式判定，不替代 SCPI、校准、路径损耗、
   测量窗口和逐指标 trust 门；这些门任何一个失败，正式判决仍不可发布。
5. report content 持久化同一 server-owned outcome；详情/下载用关联 TestExecution 重新派生并与 stored
   outcome 的冻结证据轴对账，客户端不能提交或覆盖它。REPORT 运行时执行仍是 `running`，所以
   `pipeline_status`、`completion_semantic` 与 `formal_eligible` 必须以关联执行的当前终态为准，允许
   预期的 `running → completed` 跃迁；若源执行最终为 failed/cancelled 或其他状态，报告仍
   fail-closed。compatibility digest/classification、qualification 与 reasons 任一漂移同样
   fail-closed。详情 GUI 必须消费 API 顶层的当前 outcome，不得退回 content 内持久化的
   `running/not_completed` 镜像。
6. 多执行报告若含 diagnostic/invalid，只能产出明确的非正式审计汇总；不得把其数值混入统计。

## 5. 安全方向

- 把 invalid/unknown 当成有效测试，会制造正式成功假象，且可能把不兼容配置的数值带入报告；
- 把有效执行保守降为诊断，只会阻止正式发布并留下明确原因，可被现场重新核验。

代价不对称，因此所有显式新证据的解析失败都 fail-closed。历史无 snapshot 是唯一兼容边界，并且只沿
现有 provenance 白名单，不新增宽松推断。

## 6. 非目标

- 不修改 `TestExecution.status` 取值、终态 CAS 或数据库 schema；
- 不新增、修改或猜测 SCPI；
- 不改变正式 provenance 白名单、site certification 或逐指标 trust 规则；
- 不实现 P2-67 日志/导出文件命名；
- 不实现 P2-54 MAC profile 扩展，但 parser 必须保留 omit-when-None 的版本迁移边界；
- 不用本地测试替代任何现场复验。

## 7. 验收

1. outer digest、requirements digest、verdict shape 任一篡改均投影为 `invalid`，不抛出毒整页异常。
2. compatible formal completed、compatible diagnostic completed、no-adapter diagnostic completed 分别投影
   为 `valid_test_completed`、`diagnostic_completed`、`diagnostic_completed`。
3. explicit incompatible/malformed completed 只能是 `pipeline_completed`，正式值全部 fail-closed。
4. 历史无 compatibility snapshot 的行是 `legacy + pipeline_completed`，既有 provenance 行为不变。
5. 执行详情、历史、报告构造/重建/列表/详情/下载、比较、ReportDataCollector 与 GUI 同源。
6. 报告标题和列表不再把 diagnostic/invalid 的 `completed` 渲染为绿色“成功/已完成”。
7. live OpenAPI、checked YAML、generated TS 与手写类型一致；无新增 vendor 分支。
