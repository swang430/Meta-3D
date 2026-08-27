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

## 6. 后续 Todo（本 PR 不自动实现）

### 下一次正式 LTE 测试前

- [ ] 用真实 DUT/SIM 完成 CMW500 UE Attach，并跑完 PRECHECK → MEASURE → ANALYSIS → REPORT。
- [ ] 完成真实路径损耗校准；若要产品化“无校准诊断模式”，先定义 GUI 语义、适用 TestCase、
  审计字段和报告边界，且必须继续排除正式 KPI。
- [ ] 找到手册支持的 `PCCBBBoard` 权威确认来源并完成真机取证；在此之前七字段 Route 只允许
  诊断使用。另复核最终 Route 与现场实际射频接线，六个物理路径字段以 CMW500 回读为准。
- [ ] 将现场已证明的 Aerotech `+90°` 坐标偏置接入 execution-frozen position evidence，并用
  同一 TestCase 复验四个请求方位；接入前正式位置项保持 UNKNOWN。另行取得 HOME 最终 PFBK
  的独立现场证据，不能从 MOVEABS 偏置外推。
- [ ] 生成至少一份真实 LTE execution 日志和报告，核对同一 execution 的 CMW/F64/转台证据、
  cleanup 与 transport release。

### 诊断载体收口

- [ ] EMCenter：按已知固件 2.5.1 的实测事实，将 `ERROR 3` 精确分类为“该互锁查询不支持”，
  不能把它误报成继电器链故障；不放宽其他错误。
- [ ] F64 电平窗口：让序列显式读取当前在用输出口集合；在用 16 口全部合法时可判通过，未配置
  的另 16 口保持披露而不阻塞。
- [ ] F64 license truth：在干净错误队列上重跑并留一条 SUCCESS 记录；不得恢复已删除的无手册探针。
- [ ] F64 Local 交还：按面板 Remote 水印 / Local Mode 按钮的真实含义重新完成 observe → confirm，
  修正操作员布尔值与描述相反的问题。
- [ ] FSVA：在不并发 LTE 正式执行的条件下，分别跑一次真实 PDP 与 Doppler 测量，验证刚确认的
  IQ 参数查询能够贯穿完整采集，而不只停在能力探针。

### 下次 UXM 在场时

- [ ] 恢复 `192.168.1.x` 网段，重跑 UXM identity / fresh-start / SIM / attach 诊断。
- [ ] 用相同 LTE UMa TestCase 对比 UXM 与 CMW500 的顶层结果形状；adapter 专属证据仍只留在
  版本化 evidence envelope，不能降低正式 provenance 白名单。

## 7. 本次 PR 范围约束

- 不引入功率预算、外部路径补偿或 RF router 准入。
- 不把人工观察、模拟值、旧 attempt、未完成 cleanup/release 的数值写入正式 KPI。
- 不提交现场临时文件、浏览器输出或与本次代码无关的仪器资料。
