# P1-64 静区测量证据真值设计

## 可观察故障

MIMO OTA PRECHECK 在没有真实静区场扫描证据时，仍把 ProbePattern 峰值离散代理量或固定
`0.7 dB` 当作 `quiet_zone_ripple_db`，再计算 `quiet_zone_pass=true`。该布尔被
PRECHECK 顶部绿灯、ANALYSIS、报告与 GUI 消费，最终会把“诊断流程能够继续”叙述成
“静区已实测合格”。

## 全集与当前真值

### 产生方

1. `probe_pattern.consumer.estimate_quiet_zone_ripple_db()` 只计算不同探头
   `peak_gain_dbi` 的最大最小差，函数文档已明确它是静区中心的代理量，不是静区体积内
   多点场扫描。
2. `mimo_ota.executors.precheck` 在代理量缺失时写入固定 `0.7 dB`，两种来源都会形成
   `quiet_zone_pass`。
3. `QuietZoneValidationService` 的 mock 路径会生成随机网格；真实 `ce_sa` 网格路径在
   缺少厘米单位线性 XY 平台时明确 fail-closed。因此当前系统没有可自动晋升为正式静区
   判定的真实写方。
4. 旧 `POST /calibration/quiet-zone` 固定使用 `MockInstrumentOrchestrator`，其历史行
   不能从字段形状或 `validation_pass` 反推为真实证据。

### 消费方

1. PRECHECK 用 `quiet_zone_pass` 参与 `overall_pass`，并用同一布尔决定步骤是否失败。
2. ANALYSIS 把 `quiet_zone_pass` 折叠成 bool，参与最终 PASS/MARGINAL/FAIL。
3. 报告 builder 用 `quiet_zone_verified` 或旧 `probe_pattern_peak_spread` 来源恢复
   “已验证”，并输出步骤结果、历史详情与 PDF。
4. ReportService 的历史详情/下载可信门目前不要求静区证据快照，旧报告仍可能继续发布 PASS。
5. GUI PRECHECK 顶部只按 `overall_pass` 显示红绿，并无条件显示
   `quiet_zone_ripple_db`。

## 方案比较

### A. 只把固定 0.7 改为 null

改动最小，但 ProbePattern 代理量仍能被叙述为实测，历史 `quiet_zone_verified=true`
仍能绕过，不能闭环。

### B. 直接消费现有 QuietZoneCalibration 行

能够较快恢复正式 PASS/FAIL，但现有表混有 mock、旧 Mock API 和来源未知历史行；仅凭
`measurement_method` 或 `validation_pass` 晋升会猜测历史来源。

### C. 诊断代理与正式证据物理分离（采用）

当前 PRECHECK 只发布版本化的“无正式证据/诊断代理”快照；ProbePattern 差值保留在明确命名的
诊断字段，固定 0.7 完全删除。正式静区结论保持三态，步骤继续权与正式判决分离。未来只有经过
独立设计、能产生服务器端 explicit-real 多点扫描快照的写方，才能扩展同一白名单为
`measured`；本片不猜测或回填历史行。

该方案优先采用“去掉错误行为 + 收窄白名单”，不新建硬件动作，不改仪器命令。

## 数据契约

PRECHECK 新增版本化 `quiet_zone_evidence`：

- `schema_version=1`
- `status`: 当前只允许 `unavailable` 或 `diagnostic_proxy`
- `source`: `missing` 或 `probe_pattern_peak_spread`
- `formal_verified=false`
- `measured_ripple_db=null`
- `proxy_ripple_db`: 仅代理来源可为有限数，否则 null
- `calibration_id=null`

同步字段：

- `quiet_zone_verified=false`
- `quiet_zone_pass=null`
- `quiet_zone_ripple_db=null`
- `quiet_zone_proxy_ripple_db` 可选，仅诊断展示
- `quiet_zone_can_continue=true`，表示静区证据缺失本身不阻塞诊断流程

PRECHECK 的 `overall_pass` 改为三态：

- 任一真实运行门失败：`false`，步骤 FAILED。
- 所有运行门通过但静区正式证据缺失：`null`，步骤 SUCCESS，界面显示“预检未判定，可继续诊断”。
- 未来正式静区证据明确通过：`true`；明确失败：`false`。

本片不会产生后两种 measured 状态；契约保留三态而不伪造正式来源。

## 下游规则

1. ANALYSIS 在静区快照缺失、畸形、旧格式或非正式时直接给
   `verdict=UNKNOWN`、`qz_pass=null`、`validation_pass=null`。
2. 报告只接受规范快照；旧 `quiet_zone_verified` 和
   `probe_pattern_peak_spread` 不再救回正式 PASS。
3. ReportService 把静区 schema、快照和 formal 标志加入服务端可信门及客户端 attestation
   剥离清单；旧报告必须安全重建或保持不可发布。
4. GUI 对 `overall_pass=null` 显示黄色“预检未判定”，不显示绿色“预检通过”；
   “静区纹波”显示 N/A，代理值另行标成“ProbePattern 诊断代理，非静区实测”。
5. 历史数据不从数值、旧布尔、来源字符串或当前数据库猜测；统一 UNKNOWN/N/A。

## 安全与范围

- 缺静区证据不会阻止 mock/诊断流程继续，但永远不能形成正式 verdict。
- 不新增或修改任何 SCPI、线性平台或真实静区采集动作。
- 不把现有 QuietZoneCalibration 历史行自动晋升为真实。
- 不修 R2 的非阻塞 ProbePattern/RSRP 过时日志意见；该意见不属于静区判决故障。

## 验收

1. 无 ProbePattern：无 0.7 数值、`quiet_zone_pass=null`、步骤可继续、GUI 非绿。
2. 有 ProbePattern：代理值可观察但正式静区字段为 N/A，ANALYSIS/报告仍 UNKNOWN。
3. 旧 `quiet_zone_verified=true` 或旧来源字符串不能恢复 PASS/详情/PDF。
4. 其它真实运行门失败仍按原行为 FAILED，不能被“可继续诊断”绕过。
5. mock、缺失、畸形与历史未知均 fail-closed；所有相关回归、GUI build、规则门和全后端通过。
