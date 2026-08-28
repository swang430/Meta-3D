# P2-45 无校准诊断模式与 BaseStation 现场认证设计

## 目标与边界

本片解决两个相连的可观察故障：现场需要在校准尚未完成时先打通硬件，但今天只能把
`precheck_strict_cal=false` 写进 TestCase 配置；该字段属于客户端可写配置，缺少操作员、原因、
服务器时间和执行冻结审计。另一方面，BaseStation adapter “代码可运行”与“本 LabProfile 可发布
正式 KPI”仍由 CMW500 专用开关或 UXM 历史 provenance 分别表达，没有统一的站点晋级记录。

本片定义明确的 `diagnostic` / `formal` 两阶段：

- Diagnostic 是 TestCase 级、服务器管理的执行策略。它允许缺失校准或部分现场证明时继续完成硬件
  打通，但所有结果必须保持诊断身份，不能产生正式路径损耗补偿、PASS/FAIL 或可汇总的正式 KPI。
- Formal 是 LabProfile + BaseStation connection/binding 级的站点认证。认证只能从一条已经完成且带
  本次 BaseStation 身份、config/route readback、cleanup/release 的 execution evidence 晋级；认证可撤销，
  并记录服务器时间和审计人。
- 两类状态都在 execution 创建时冻结。随后修改只影响后续 execution，历史报告只读执行快照。

不引入功率预算、外部路径补偿、RF router 准入、自动发现或新 SCPI；不放宽既有逐指标 provenance
白名单，也不把 `DiagnosticRun` 当作正式 TestExecution 的替代品。

## 动手前全集

### 策略与认证产生方

1. TestCase CRUD 当前允许任意 `configuration`，其中可携带 `precheck_strict_cal=false`。
2. TestCase 直接执行由 `launch_test_case_execution()` 创建快照与正式 execution。
3. Commissioning session、saved phase、run-all 共用 session TestCase，但 session create 可直接接收
   `precheck_strict_cal`；GUI 的两个 `calBypass` 控件直接发送该字段。
4. Commissioning adhoc 独立创建带 `diagnostic_ad_hoc` 标签的 TestCase/TestExecution，并写
   `DiagnosticRun`；它已经不进入正式 commissioning 列表，但仍需统一公开诊断投影。
5. InstrumentConnection 的 CMW500 专用 `formal_enabled/updated_at` 是当前唯一 rollout 真值；UXM
   manifest 仍写 `legacy_provenance`。
6. P2-44 resolver 生成 `ResolvedBaseStationBinding`/`binding_digest`，execution freeze 保存 binding 与
   runtime identity；P2-43 evidence 保存本次 config/route/window/cleanup/release 事实。

### 策略与认证消费方

1. PRECHECK 用 `precheck_strict_cal` 决定缺失/无效路径损耗校准是否阻断。
2. MEASURE 用同一字段决定是否选择/应用路径损耗证书，并形成 path-loss application evidence。
3. REFERENCE 在 bypass 时把 TRP 标成未验证。
4. ANALYSIS 以 path-loss、throughput、RF KPI、quiet-zone、BaseStation evidence 决定三态判词并写
   `TestExecution.validation_pass`。
5. REPORT 生成顶层 verdict、statistics、逐方位表和四组 `formal_*_verified`；ReportService 的详情、
   重建与下载再次校验该投影。
6. ReportComparisonService、ReportDataCollector、execution history 和 commissioning 结果面板消费
   validation/KPI/正式标记。
7. Instrument Catalog 与 readiness GUI 展示当前 BaseStation 正式能力；TestCase 编辑和 commissioning
   GUI 需要展示诊断策略的黄色状态、原因、操作员与服务器时间。
8. live OpenAPI、checked-in YAML、generated TS 与手写 GUI 类型是同一公开合同的四个镜像。

## 方案比较

### 方案 A：专用服务器状态 + execution-frozen qualification（采用）

在 TestCase 增加不对通用 CRUD 开放的 `execution_policy` JSON 列；在 InstrumentConnection 增加不对
通用连接保存开放的 `base_station_site_certification` JSON 列。两者只由专用端点写入。公共服务把
当前策略、P2-44 binding 和当前认证解析成不可变 `ExecutionQualification`，在 execution 创建时冻结。
所有生产消费方只读冻结投影。

优点：最少新增两列和一条迁移；不复制 catalog/binding 真值；专用端点可收窄写入口；历史 execution
天然保留当时状态。缺点：列只保存当前状态而不是独立事件表；但每次执行已冻结完整快照，满足本片
审计与“只影响后续执行”边界，完整组织级身份认证可另立项。

### 方案 B：继续使用 `configuration.precheck_strict_cal` 与 CMW 专用开关（拒绝）

改动最少，但通用 TestCase PATCH、commissioning 请求、环境/debug 路径都可能直接授予绕过；UXM/下一
adapter 还要再加一套开关，也无法记录认证所依据的 execution evidence。

### 方案 C：新建通用审批/事件表（本片不采用）

独立 append-only 表能保留每次审批历史，但会同时引入审批状态机、查询/分页、并发 active 约束和
迁移回填。P2-45 只需要当前有效状态 + execution 快照；先用专用 JSON 列收窄机制，避免把现场打通
产品化扩成完整权限系统。

## 数据合同

### TestCase execution policy

`TestCase.execution_policy` 只接受严格版本化形状：

```text
schema_version: 1
mode: formal | diagnostic
reason: non-blank for diagnostic
updated_by: non-blank operator identity
updated_at: server-owned UTC timestamp
```

缺失/畸形一律解释为 `formal`，但畸形显式数据必须 fail-loud，不能回退成诊断。通用 TestCase create/
patch 不暴露该列；专用 `PUT /test-plans/cases/{id}/execution-policy` 是唯一写入口。关闭诊断同样写一份
`formal` 记录和服务器时间，不静默删除审计事实。Commissioning session create 使用同一专用请求形状
在服务器创建 session TestCase 时落策略；旧 `precheck_strict_cal` 请求不得再授权绕过。

### BaseStation site certification

`InstrumentConnection.base_station_site_certification` 保存：

```text
schema_version: 1
status: active | revoked
lab_profile_id / instrument_connection_id / binding_digest
adapter_id / model / firmware_version / options
source_execution_id / evidence_digest
required_proofs: config_readback / route_readback-or-not_applicable / cleanup / transport_release
certified_by / certified_at / reason
revoked_by / revoked_at / revocation_reason
```

专用认证端点只接受 `source_execution_id`、审计人和原因。服务器锁定 connection，重新解析 P2-44
binding，并从该 execution 的冻结 binding、BaseStation identity 和 P2-43 evidence 中提取事实；客户端
不能提交 model/firmware/options 或 proof 布尔值。source execution 可以是 diagnostic，但必须真实、
已完成、与当前 LabProfile/connection/binding digest 同源，并具有精确 config/route/cleanup/release
证明。模拟、unknown、旧 attempt、错 config/route/position、未完成 cleanup 或未确认 transport release
均拒绝认证。

撤销端点只接收审计人和原因，服务器写 `revoked_*`；不删除历史内容。CMW500 旧专用开关保留只读
兼容镜像，本片后它不能单独授予正式资格。UXM/CMW manifest 的 `formal_gate` 统一改成
`site_certification`，下一 adapter 不新增顶层开关。

## ExecutionQualification 与执行冻结

新增严格不可变投影：

- `schema_version`、`mode`；
- TestCase policy 的完整服务器审计快照；
- P2-44 `binding_digest`、adapter/model/connection/LabProfile；
- 当前 site certification 快照或明确的缺失/失效原因；
- `formal_eligible_at_start`；
- `qualification_digest`。

规则为白名单：

1. policy=`diagnostic` 时 mode 恒为 diagnostic，不因当前已有校准/认证自动升级；
2. policy=`formal` 只有 real configured binding、active 且精确匹配的 site certification 才是
   formal candidate；否则仍可按既有开发诊断边界运行，但 mode 降为 diagnostic，并明确原因；
3. `precheck_strict_cal` 的有效值只由冻结 qualification 派生：formal=true、diagnostic=false；TestCase
   configuration 或 commissioning 客户端字段不能覆盖；
4. execution 期间认证被撤销不改历史 execution；下一 execution 重新解析。

正式候选仍不等于最终正式结果。ANALYSIS/REPORT 还必须通过本次 calibration、frequency、BaseStation
config/route/window/cleanup/release 和逐指标 trust。site certification 只是一道额外 AND 门。

## 诊断值与报告边界

Diagnostic execution 可以保留诊断用原始采样和仪器证据，但生产投影必须满足：

- MEASURE 不应用路径损耗证书，不以 0 dB 伪装成补偿值；`path_loss_application.applied=false`，正式
  路损字段为空；
- ANALYSIS 无条件写 `validation_pass=None`、verdict=`UNKNOWN`；不得计算/保留正式 PASS/MARGINAL/FAIL；
- REPORT 顶层增加严格 `execution_qualification`/`report_classification=diagnostic` 和黄色说明；
  statistics、逐方位正式 KPI、补偿后工程值统一 N/A，诊断原始值只留在明确的 diagnostic evidence
  envelope，不进入正式表；
- ReportService 详情、重建、下载、比较、ReportDataCollector 和 execution history 都从 execution/report
  冻结 classification 重新 fail-closed，不能由旧 `validation_pass`、客户端声明或当前认证恢复正式值；
- Commissioning 与 Test Management 全程黄色显示“仅可诊断”，含原因、操作员和服务器时间。

历史 execution 没有 qualification 快照时不从当前 TestCase/connection 反推；既有已经满足完整旧
provenance 的报告保持当前兼容策略，新逻辑只对白名单要求的新执行生效。

## API 与 GUI

新增/调整公开合同：

1. TestCase response/summary 增加只读 `execution_policy`；专用 policy PUT 返回服务器快照。
2. BaseStation readiness/binding preview 增加当前 site certification 与 formal/diagnostic 分类；认证/
   撤销使用专用 InstrumentConnection endpoint。
3. Case execute/status、commissioning session/phase/run-all 响应暴露 frozen qualification。
4. MIMO OTA TestCase 编辑页增加 Diagnostic/Formal 卡片。启用 diagnostic 必填操作员和原因，黄色；
   Formal 只读显示当前站点认证，不允许从 TestCase 表单授予。
5. Instrument Catalog 的通用 manifest 卡片显示认证状态、来源 execution、审计人/时间和撤销操作；
   不写 connection params/localStorage/env。
6. 报告列表/详情/下载前提示 classification；diagnostic 导出允许作为带水印/明确标题的诊断记录，
   但不得复用正式报告接受判据。

同步 live OpenAPI、`api/openapi.yaml`、generated TS 和手写类型。

## 错误与安全边界

- 所有 policy/certification 更新先锁定服务器行、验证完整作用域，再一次 commit；失败回滚。
- 认证来源只读已落库 execution evidence，不打开仪器、不发 SCPI、不从请求值补回读。
- 对 formal/diagnostic 分类的误判代价不对称：证据不明时保守降为 diagnostic，而不是放行 formal。
- Diagnostic 不跳过 DUT、配置、route、attach、cleanup、release 或硬件安全门；只允许校准/正式资格
  缺失时继续，并将结果挡在正式消费方之外。
- 旧 CMW approval、env、通用 connection params、debug inherit、Mock 和客户端
  `precheck_strict_cal=false` 均不能创建 active site certification 或 formal execution。

## 测试与验收

1. policy 专用端点审计 operator/reason/TestCase/server time；通用 CRUD 与旧 strict flag 不能授权。
2. policy/certification 修改前创建的 execution 快照不变，之后的 execution 读取新状态。
3. 从真实完整 execution evidence 可认证；每一种 missing/wrong/simulated/unknown/unsafe 证明都拒绝。
4. 认证可撤销，撤销后只影响后续 execution；旧 execution/report 不重分类。
5. diagnostic 在 PRECHECK/MEASURE/ANALYSIS/REPORT、详情/下载/比较/history/commissioning 全路径均为
   UNKNOWN/N/A，且有黄色审计说明。
6. formal 仍需完整 calibration + per-execution provenance；site certification 不单独判绿。
7. UXM/CMW 使用同一认证合同；不新增 adapter/vendor 消费分支或命令。
8. 相关/全后端、GUI 契约与 production build、OpenAPI 镜像、compileall、单一 Alembic head、
   diff-check 和 fresh 功能内审通过。

现场认证必须用真机 execution evidence 完成；本地 fake 只能验证拒绝/冻结/投影合同，不能替代现场晋级。
