# P2-32B 探头方向图真实入口闭环设计

## 可观察故障

系统已经有 `PatternCalibrationService` 的 CE+SA+转台真实测量实现和定点测试，但生产入口
`POST /api/v1/calibration/probe/pattern/start` 没有调用它。该 API 仍在 handler 内用
`random.gauss()` 生成模拟方向图，并固定写入 `use_mock=true`。GUI 虽然有 client 与 hook，
Probe Calibration Dashboard 的“开始校准”动作却仍是 `TODO`，当前只有厂商方向图文件导入
具有真实界面入口。

因此，操作员不能从生产 GUI 启动已有真实测量；如果直接把 API 的 `use_mock` 翻成 false，
又会漏掉 LabProfile、SwitchTopology、RF chain 和 CE port 的冻结与校验，可能在错误物理链路上
测量并把结果签成目标探头的有效方向图。

## 目标

1. `/pattern/start` 成为 `PatternCalibrationService` 的唯一生产 caller，删除 handler 内的随机实现。
2. Real/Mock 由操作员显式选择；GUI 未选择模式时不发送请求。
3. Real 在首次仪器 I/O 前解析并冻结 LabProfile、暗室、运行模式、SwitchTopology、RF chain 与
   CE port；每个 probe/polarization 必须唯一匹配，错误或漂移 fail-closed。
4. Real 复用现有 CE+SA、positioner、RF switch 路由和任务级仪表租约，不新增或修改 SCPI。
5. acquire/cleanup warning 与测量路由身份进入 `ProbePattern` 数据库、API 和报告。
6. GUI 提供一个可达的“方向图测量”工作单元，并与厂商 Pattern 导入保持两个明确来源。
7. 模拟、历史未知和不再匹配当前路由的记录不得进入正式消费或报告 PASS 分母。

## 非目标

- 不实现 P2-32C 静区多点场扫描；它继续由厘米级 XY 扫描平台阻塞。
- 不改变 CE、SA、RF Switch 或转台的任何命令、参数域或正式 provenance 白名单。
- Real 必须显式冻结来自有效链路/路损校准的 `chain_correction_db`；缺失时在首次硬件 I/O 前
  fail-closed，不能让相对方向图峰值进入正式增益补偿。
- 不引入新的方向图认证阈值；完成真实采集不等于“校准合格”。
- 不修改厂商方向图导入格式与解析器；`vendor_datasheet` 方向图不绑定现场 RF 路由。
- 不把真实硬件现场验收替换成本地测试；本片只交付软件可达性和 fail-closed 证据。

## 现有产生方与消费方全集

### 产生方

1. `POST /calibration/probe/pattern/import`：导入厂商方向图，`source=vendor_datasheet`。
2. `POST /calibration/probe/pattern/start`：当前在 API handler 内生成随机模拟值。
3. `PatternCalibrationService.execute_pattern_calibration`：已有 Mock 与 CE+SA+positioner Real 实现，
   但没有生产 caller。

P2-32B 删除第 2 个独立生成器，使 start API 只调用第 3 个服务；导入路径保持独立。

### 消费方

1. `GET /calibration/probe/pattern/{probe_id}` 与 Probe Calibration 详情/历史界面。
2. `probe_pattern.consumer`：正式 MIMO MEASURE 的探头增益读取。
3. MIMO PRECHECK 的 ProbePattern 峰值离散诊断代理；它仍不等于静区实测。
4. 校准 JSON/PDF、证书和审计报告。
5. 校准有效性统计与 Probe Calibration Dashboard。

上述消费方必须共同识别 `use_mock`、`source`、warning 和现场测量路由身份；不得只在 start
响应里标注来源。

## 权威数据流

```text
OperationalLab.id + OperationalLab.chamberId
        + 操作员输入的 probe / polarization / frequency / scan grid / SGH / mode
        -> POST /calibration/probe/pattern/start
        -> PatternCalibrationService(use_mock=显式值)
        -> Real: resolve_rf_chains(lab_profile_id, operating_mode)
                 chamber 必须精确一致
                 每个 probe/polarization 必须唯一解析到 chain_id + ce_port
                 RF switch route_target + CE tone + SA readback + positioner scan
           Mock: 诊断方向图，use_mock=true，禁止正式判决
        -> ProbePattern(source, use_mock, warnings,
                        lab_profile/topology/chain/CE-port identity,
                        measured grid and derived pattern metrics)
        -> API/GUI/报告只投影服务器保存的来源与结果
```

## API 与服务边界

`StartPatternCalibrationRequest` 增加：

- `lab_profile_id`：真实测量冻结 RF 拓扑的唯一入口；Mock 也携带以保持审计上下文。
- `operating_mode`：默认 `mimo_ota`，用于解析活动 SwitchTopology。
- `use_mock`：保留 API 历史兼容默认 `true`；GUI 必须显式发送布尔值。
- `ce_tx_power_dbm`、`sgh_gain_dbi`：只作为既有真实测量公式的显式输入，不扩大现有参数域；
  CE 功率沿用 HAL 的 `-50..20 dBm` 边界。
- `chain_correction_db`：真实测量必须从有效 RF 链路/路损校准显式提供；不得隐式补 `0 dB`。
  缺少该值时只能得到相对方向图，其峰值不能作为正式绝对增益补偿。

不让 GUI 直接选择 `ce_port` 或 `chain_id`。Real 只从服务器权威 LabProfile/Topology 解析；
手填端口会创造第二份硬件真值。

服务在首次硬件 I/O 前一次性解析全部 requested `(probe_id, polarization)`：

- LabProfile 不存在、未绑定暗室或绑定暗室与 request 不一致：失败；
- 无活动 topology、topology 无身份、零条/多条匹配链：失败；
- `chain_id` 或 `ce_port` 为空/占位符：失败；
- 解析成功后，每个 probe/polarization 扫描使用同一冻结 chain 与 CE port；
- 仪器失败、路由失败、转台失败或 lease 失败：失败，不回退 Mock。

响应复用 `CalibrationJobResponse`，必须回填 `use_mock` 和 warnings；失败 detail 保留
`message + warnings`，让清理失败不会只沉日志。

## 持久化与历史兼容

`probe_patterns` 增加 nullable 字段：

- `warnings` JSON；
- `lab_profile_id`；
- `operating_mode`；
- `topology_id`；
- `chain_id`；
- `ce_port`。
- `chain_correction_db`（绝对增益反算使用的冻结链路修正）。

语义：

- `warnings=NULL`：迁移前未记录；新写入必须是明确列表。
- `source=vendor_datasheet`：路由无关，路由字段保持 NULL，可继续正式消费。
- `source=in_chamber_measured`：新记录必须有完整路由身份与有限的
  `chain_correction_db`；现代缺损记录 fail-closed。
- 迁移前的 `in_chamber_measured` 行缺路由身份，仍可审计查看，但不得进入正式增益消费或
  报告 PASS 分母。
- `source=simulated` / `use_mock=true`：仅诊断展示。

正式消费现场实测方向图时，重新解析当前 LabProfile/Topology，并要求
`lab_profile_id + operating_mode + topology_id + chain_id + ce_port` 与冻结值精确匹配。
厂商导入方向图只按 chamber/probe/polarization/frequency/source/有效期校验，不伪造路由绑定。

## 测量值与判决语义

本片保留已有测量公式和派生指标，不新增物理语义。由于仓库没有为方向图建立权威
PASS/FAIL 阈值：

- start 成功表示“真实/模拟采集已完成”，不是“校准合格”；
- `ProbePattern` 报告行的 `validation_pass` 固定为 `null`；
- 峰值、HPBW、前后比作为测量结果展示，不参与报告 PASS 分母；
- Mock 的数值可以展示，但必须同时显示 SIMULATED，且不进入 MIMO 正式补偿/KPI；
- ProbePattern 峰值离散继续只作为 diagnostic proxy，不能变成静区 PASS。

## GUI

在 Probe Calibration 页面增加“方向图测量”页，与“Pattern 导入”并列。Dashboard 的 Pattern
开始按钮打开同一个测量表单，不复制第二套请求逻辑。

表单字段：探头 ID、极化、频率、方位/俯仰步进、测量距离、参考天线、转台标识、CE 功率、
SGH 增益、链路修正、校准人员和执行模式。LabProfile 与 chamber 只读显示当前 OperationalLab 真值。
真实模式下链路修正必填，并明确提示只能取自有效 RF 链路/路损校准，不能猜测。

行为：

- 执行模式初始为空；“真实 CE+SA+转台”带硬件动作警示，“模拟诊断”明确不进入正式判定；
- probe ID 输入拒绝空、重复、非整数和暗室范围外值；
- 提交后校验响应 `use_mock` 必须存在且与请求一致；
- 成功展示来源、记录 ID、warnings 和采样规模，不显示“通过”；
- GUI 不从输入重算服务器测量或正式 verdict。

## 报告与契约镜像

- 校准报告方向图行输出 `source/use_mock/warnings` 及冻结路由身份。
- 方向图行不进入 pass/fail 分母；历史 unknown 与 route drift 显式标为不可正式使用。
- live OpenAPI、`api/openapi.yaml`、generated TypeScript 与手写 GUI 类型同步。
- 旧 API 内随机生成实现必须从生产代码消失；保留服务层 Mock 仅供显式诊断。

## 安全与失败复位

- 继续使用 `instrument_test_lease(control_f64=True, control_uxm=False)` 包住完整扫描。
- route/CE tone/SA/positioner 任一失败都中止当前作业，不创建“成功”记录。
- CE tone 的 finally-stop warning 必须进入作业响应与记录；不因 cleanup warning 把失败改成功。
- positioner 失败沿用既有 fail-loud；本片不放宽断链或停止判据。
- Real 不允许 Mock CE、SA、switch 或 signal source；复用现有 `_reject_simulated_instrument` 门。

## 验收

1. start API 不再含 `random.*`，且精确调用 `PatternCalibrationService`。
2. GUI 无模式、无 OperationalLab、非法 probe 输入均不发送请求。
3. Real 的 LabProfile/chamber/topology/chain/CE port 在首次仪器 I/O 前完整解析；任一缺失失败。
4. 每个扫描点使用目标 probe/polarization 的冻结 route 与 CE port；错误链不会落库。
5. 仪器/转台/lease 失败不回退 Mock；cleanup warning 进入响应、DB 和报告。
6. Mock 与历史 unknown 可审计但不进入正式消费、KPI 或报告分母。
7. 厂商导入方向图继续可正式消费，且不被错误要求具有现场路由身份。
8. 当前路由漂移后，旧 `in_chamber_measured` 方向图不再供正式执行使用。
9. GUI/API/OpenAPI/generated TS/手写类型一致；production build 通过。
10. 不新增或修改 SCPI；P2-32C 保持 Hardware Blocked。
