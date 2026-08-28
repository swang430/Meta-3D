# 2026-08-27 CAICT LTE CMW500 MIMO OTA 现场测试总结

## 1. 本次目标与边界

本次在 `CAICT-Lab-1` 用真实 CMW500、PROPSIM F64、R&S FSVA3044、Aerotech
转台和 ETS-Lindgren EMCenter，建立 LTE 20 MHz MIMO OTA TestCase 的真实硬件链，
并用现场事实修正配置同步、CMW500 SCPI、仪器并发和诊断探针。

本次没有宣称完成正式交付测试：UE 未 Attach 是当日已知边界，现场没有有效路径损耗
校准，UXM 也不在场。因此结果只证明“配置和硬件链已推进到 Attach 前”，没有产生可交付
的正式吞吐、BLER 或路径损耗补偿 KPI。

## 2. 现场设备与网络事实

| 角色 | 现场地址 / 身份 | 结果 |
|---|---|---|
| CMW500 Base Station | `192.168.0.149` | SCPI 已连通；`172.22.1.4/16` 是面板旧信息，不是本次控制地址，已撤销临时网段 |
| PROPSIM F64 | `192.168.0.132` | ATE/SMU 控制可用；LTE UMa 20 MHz 工程加载后可测到 CMW500 信号 |
| R&S FSVA | `192.168.0.134:5025`；`Rohde&Schwarz,FSVA3044,1330.5000K44/101122,1.50SP1` | SCPI 与 IQ 能力探针通过 |
| Aerotech Positioner | `192.168.0.16:8000` | 单轴反馈、单位、速度和坐标偏置完成现场证明；小步前进/返回诊断最终通过 |
| ETS-Lindgren EMCenter | `TCPIP0::192.168.0.50::inst0::INSTR`；固件 `2.5.1` | VXI-11 与继电器回读可用；该固件不支持 `INTLK? SAFETYRELAY` |
| Keysight UXM | `192.168.1.112` | 当日不在现场，不纳入本次验收 |

F64 使用的目标工程为：

`D:\Scenario Packs\F9809A TS LTE MIMO OTA 2x2\1.0 RC1\TS_LTE_MIMO_OTA_SCME_UMa_8DP.wiz\TS_LTE_MIMO_OTA_SCME_UMa_8DP.smu`

测试工作点按 LTE 20 MHz 配置。CMW500 自身回读是其配置和状态的权威来源；F64
文件名、旧缓存或 GUI 镜像不能替代仪器回读。

## 3. LTE TestCase 实际推进结果

1. “仪器资源配置”的 CMW500 型号、连接和内部七字段 Route 可以显式同步进
   `CAICT-Lab-1`，保存错误会在 GUI 明确显示，不再出现“看起来保存了但 LabProfile 没变”。
2. LTE MIMO OTA TestCase 已能在“测试管理 → 我的用例”显示并启动。
3. CMW500 能按请求配置 LTE 小区；选件 token、FDD/TDD 写入顺序和内部 Route 回读按
   现场仪器语义修正。
4. F64 加载 LTE UMa 20 MHz SMU 后，现场已在 F64 输入侧测到 CMW500 射频信号。
5. 执行到 UE Attach 前的硬件链已打通；UE 未 Attach 是当日预期结果，不作为软件假成功。
6. 当日经操作员明确授权，仅该 LTE 首测用例设置 `precheck_strict_cal=false`。无校准数据
   不进入路径损耗补偿或正式 KPI；“长期允许无校准诊断测试”只登记为产品需求，没有现场
   临时扩张正式判定规则。

## 4. 当日代码修复

### 4.1 配置与 GUI

- 新增 Instrument Catalog → LabProfile 的服务端同步入口，并同步 OpenAPI、生成类型和 GUI。
- CMW500 七字段内部 Route 缺失、为 `null` 或保存失败时 fail-loud；GUI 不再把失败显示成成功。

### 4.2 CMW500

- 按仪器返回的裸选件 token（如 `KS520`）判定能力，不再要求显示名中的 `CMW-` 前缀。
- 先选择 FDD/TDD，再下发 band，避免设备按旧双工模式拒绝新 band。
- Route 回读只把仪器真正返回的六个物理路径字段当权威；回包中的保留 Controller 字段不是
  `PCCBBBoard`。写入被接受且错误队列干净仍不能证明 `PCCBBBoard` 已应用，因此当前 Route
  只允许诊断使用，正式 KPI 保持 UNKNOWN/N/A。
- **离场后的本地半（仍待真机复验）**：依据 LTE UE Manual 1173.9628.02-41 §2.6.8.1
  pp.630–631 与 Remote Control via SCPI 1179.4592.02-04 §3.6 p.22，已实现
  `ROUTe:LTE:SIGN<i>:SCENario:TRO:FLEXible?` 七字段严格回读，并与原通用 query 的六个物理
  路径交叉确认。真机未返回完整一致的两份回读时仍 fail-closed，不把请求值回填成结果。
- 删除现场不支持且没有手册出处的 `UEReport:SINR?` 后台监控查询。
- 配置前清理旧错误队列，配置后仍独立核对本次写入，避免旧错误冒充新结果。
- 正式 LTE 执行不再让无关 FSVA 监控流量或 reference 测量介入；CMW/F64/转台失败立即终止后续动作。

### 4.3 FSVA

- 测量超时后发送有手册依据的 `ABORt`，关闭已污染会话；后续重连使用新会话，避免驱动挂死
  阻塞整个执行。
- IQ 能力探针由“在 IQ OFF 时直接盲查”改为：读取初始状态 → 临时确认 ON → 每条查询后立即
  归属并清理错误队列 → `finally` 确认恢复 OFF。
- 2026-08-27 真机最终结果：
  - `TRACe:IQ:SRATe?` → `32000000`
  - `TRACe:IQ:BWIDth?` → `25600000`
  - `TRACe:IQ:RLENgth?` → `1001`
  - 初始 / 最终 IQ 状态均为 OFF，错误队列零残留。
- 程序证据：DiagnosticRun `df640983-f2e8-4d2c-ab64-de99fa38814f` 与操作员复跑
  `4241e370-560f-459a-b77a-0754ba7bf7f8` 均为 SUCCESS。

### 4.4 Aerotech 转台

- Socket2 按 Ensemble 协议逐字节读取 `%` / `!` / `#` 响应标记，忽略遗留 CR/LF，避免上一条
  命令的换行错配给下一条查询。
- `GETPARM X,129` 实测单位为 `deg`，`GETPARM X,2` 为 `3500 counts/unit`；默认速度
  `20 deg/s`、最大 Jog `120 deg/s` 均已只读归档。
- 对阻塞式 `MOVEABS` / `WAIT INPOS` 使用动作完成预算，不再拿普通查询超时误判动作失败。
- 两次独立动作证明 PFBK 与程序坐标存在固定 `+90°` 关系；正式移动只在该偏置和 degree 单位均
  显式确认后执行。DiagnosticRun `aerotech_positioner_motion_truth` 最终为成功。该现场事实尚未
  接入 execution-frozen position evidence，因此正式 TestCase 的位置证据继续保持 UNKNOWN；
  HOME 的最终 PFBK 也未获独立证明，非零偏置站点会在发送 HOME 前拒绝。

## 5. 硬件诊断状态

| 项目 | 当前结论 | 证据边界 |
|---|---|---|
| CMW500 SCPI / LTE 配置 | 通过 | 真机回读与错误队列 |
| F64 SMU / LTE 信号输入 | 通过 | F64 界面与执行日志均观察到目标信号 |
| F64 32 口电平窗口 | 人工接受 | 16 个在用端口返回合法窗口，另 16 个未回复；当前序列仍记 UNDETERMINED |
| F64 license / calibration 只读探测 | 人工接受 | 现场清掉历史 `-100` 后继续；当日没有新的 SUCCESS 序列记录 |
| F64 120 秒连接保持 | 通过 | DiagnosticRun `61806523-a365-483f-9891-63211a0360d2` |
| F64 Local 交还 | 尚未形成程序化通过证据 | 数据库中只有 UNDETERMINED / BLOCKER，需按面板事实重新确认 |
| Aerotech health / motion truth | 通过 | 最终 health 与 motion DiagnosticRun 成功 |
| EMCenter 继电器链 | 人工接受 | 固件 2.5.1 对互锁命令返回 `ERROR 3`，序列仍记 BLOCKER |
| FSVA IQ 能力 | 通过 | 两次 SUCCESS；最终恢复 OFF、错误队列零残留 |
| UE Attach / LTE KPI / 报告 | 未完成 | 当日 UE 未 Attach，无正式吞吐/BLER/报告 |
| UXM | 未测试 | 当日不在现场 |

## 6. 后续 Todo（已编入 roadmap 优先级）

本文件只保留 CMW500 现场视图，不建立第二套总队列。执行时必须先按地点选队列：

- **在现场**：把时间用于真实 Attach、仪器权威回读、校准、转台 HOME/方位、真实报告与
  cleanup/release 证据；不在仪器旁临时开展 P2-42～45 架构开发。无需代码修改的既有诊断
  可以穿插留证；发现探针缺口只保存原始回复，回到非现场再修。
- **非现场**：先处理本次已暴露的最小代码/手册缺口，并明确标记“待现场复验”；随后才按
  P2-42 → P2-43 → P2-44 → P2-45 做架构收敛。非现场回归不能替代现场通过。

原 First-call / on-site Todo 完整保留在 roadmap 的 Blocked 表：P0-5、P1-2、P1-4、P2-4，
以及 P1-5/P1-17/P2-9/P2-10/P2-12/P2-13 现场半和 P1-6 HOLD，均没有被 P0-9 或
P2-42～45 替换。

### P0-9：下一次正式 LTE 测试闭环（Current Focus）

- [ ] **P0-9A（现场）**：用真实 DUT/SIM 完成 CMW500 UE Attach，并跑完
  PRECHECK → MEASURE → ANALYSIS → REPORT。允许现有逐用例、可审计的无校准诊断运行，
  但正式 KPI 必须保持 UNKNOWN/N/A。
- [ ] **P0-9B-1（本地半完成 → 现场复验）**：手册支持来源、七字段 query/parser 与驱动双回读
  已完成；回现场保存专用 query 与通用 query 的原始响应并确认两者一致。在取得该真机证据前
  七字段 Route 仍只允许诊断，不得用请求值、写入成功或保留 Controller 字段补绿。
- [ ] **P0-9B-2（现场）**：完成真实路径损耗校准。长期“无校准诊断模式”的产品语义已提升 P2-45，
  不在现场临时扩大正式判定。
- [ ] **P0-9B-3（本地半完成 → 现场复验）**：已将操作员配置且带现场来源/时间的 Aerotech
  degree、范围、速度、容差与 `PFBK - MOVEABS` 偏置冻结到 execution；动作前复核同一
  LabProfile/model/connection/driver/digest，逐方位同时核对请求物理角、实际 MOVEABS 程序角和
  原始 PFBK，不再二次扣减偏置。回现场仍须用同一 TestCase 复验请求方位，并另行取得 HOME
  最终 PFBK；本地回归不冒充现场完成。
- [ ] **P0-9C（现场）**：生成真实 LTE execution 日志和报告，核对同一 attempt/lease/session 的
  CMW/F64/转台证据、cleanup 与 transport release；再重复执行一次，证明没有读取旧结果。

### 现场硬件诊断证据收口（不阻塞 P0-9A Attach）

- [ ] **P2-9 现场半**：EMCenter 对固件 2.5.1 的 `ERROR 3` 仅在已确认的
  `INTLK? SAFETYRELAY` 上精确归类为 unsupported；不放宽其他错误，修后重跑 SUCCESS。
- [ ] **NEW-1 现场半（本地修复已完成）**：序列现按 `MODEL:INFO?` 与逐组
  `GROUP:OUTPUTS:GET?` 的实时交叉核对只读取当前活动集合，不再用整机通道数或旧缓存扩口；
  现场仍须加载同一场景重跑并取得 SUCCESS。未进入活动集合的硬件口不探测、不阻塞。
- [ ] **P1-2 现场半**：F64 license truth 在干净错误队列上重跑并留 SUCCESS；不得恢复无手册探针。
- [ ] **NEW-2 现场半**：F64 Local 交还按 Remote 水印 / Local Mode 真实含义完成两段式确认并留记录。
- [ ] **U-12 非阻塞能力项**：FSVA 在不并发 LTE 正式执行时分别跑真实 PDP 与 Doppler，证明 IQ
  参数查询贯穿完整采集。FSVA 不属于当前 LTE MIMO OTA 必需链。

### P2-42～P2-45：降低下一种 BS Emulator 接入成本

- [ ] **P2-42**：单一 BaseStation execution session，统一四类入口的生命周期和监控隔离。
- [ ] **P2-43**：窄 Adapter SPI、逐字段结构化回执、统一正式 metric projection 和认证套件。
- [ ] **P2-44**：唯一 `ResolvedBaseStationBinding` 与 manifest 驱动的注册/readiness/GUI。
- [ ] **P2-45**：产品化无校准诊断模式及 Diagnostic/Formal 两阶段站点认证。

P2-42～P2-44 是第三种 BS Emulator 的接入前置；验收目标是新 adapter 不再修改 MEASURE、
commissioning 多入口、报告/比较/下载/历史和通用 GUI。

### 下次 UXM 在场时（并入 P2-43 认证基线）

- [ ] 恢复 `192.168.1.x` 网段，重跑 UXM identity / fresh-start / SIM / attach 诊断。
- [ ] 用相同 LTE UMa TestCase 对比 UXM 与 CMW500 顶层结果形状；adapter 专属证据只留在
  版本化 evidence envelope，不能降低正式 provenance 白名单。

## 7. 本次 PR 范围约束

- 不引入功率预算、外部路径补偿或 RF router 准入。
- 不把人工观察、模拟值、旧 attempt、未完成 cleanup/release 的数值写入正式 KPI。
- 不提交现场临时文件、浏览器输出或与本次代码无关的仪器资料。
