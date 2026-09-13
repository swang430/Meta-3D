# P2-70：CMW FDD 矩阵抽样诊断载体

状态：用户已批准，非现场实现及本地验证完成；外审/合并状态以对应 PR 台账为准。
基线：`c2038019`。不代表 P2-55 现场验收。

## 可观察故障与选择

P2-55 要求分别抽样 TM1/1 TX 与 TM3/2 TX，但正式 LTE profile 只允许 TM3/2 层，
现有 `baseStation_attach_check` 也没有前一条路径。设备到场仍无法完成抽样。

选择在现有诊断入口新增 `cmw500_fdd_matrix_probe`，每次选择一个完整、固定的 sample，
不接受任意 TM、天线、调制、TBS 的自由组合。不扩展正式 profile 的 Literal；不扩展旧
Attach 序列（它负责起信令/等 DUT，职责与本次关闭小区的配置回读抽样不同）。

## 首片域与可观察结果

只覆盖已配置好的 **FDD、20 MHz、单载波 nx2 Scenario**。不自动改频率、双工、带宽、
路由或 LabProfile；前置不符返回明确原因。这里的 ONE 是一个下行 TX，nx2 场景下是
SIMO 1x2，不把它称为一条物理 RF 路径或已测 SISO。

| sample | TX / DCI | DL RMC（RB / 调制 / TBS index） | UL |
|---|---|---|---|
| `tm1_one` | ONE / D1A | 100 / QPSK / 5 | 复用已取证 B200 的 100 / QPSK / 2 |
| `tm3_two` | TWO / D2A | 100 / 16-QAM / 13 | 同上 |

TM3 开启 DLEQual 并核对 DL1/DL2；TM1 不把无活跃第二流当成必须通过的证据。
调度限定 RMC、连续满 RB、LOW，不启用 AMC、TDD、CA、4 层或额外带宽。
sample 参数由服务器严格校验（现有 GUI params_schema 仅是表单提示，不是验证器）。

结果只进入 `DiagnosticRun.sequence_evidence`。输出 sample、仪器身份/固件/选件、
绑定快照、写前/写后状态、实际命令和原样回复、每组错误队列、逐字段比较及收尾结果。
`success` 仅表示本次诊断脚本及比对通过，明确 `formal_eligible=false`，不写 TestExecution、
正式 qualification、能力认证或 KPI。Mock / fake transport 的结果必须标明模拟，不能解除现场 blocker。

## 权威来源与尚不能推广的结论

厂商源：`Instrument_API_Doc/R&S CMW500/CMW_LTE_UE_UserManual_V4-0-250_en_41 (2).pdf`，
User Manual 1173.9628.02-41。2026-09-11 查询 NotebookLM CMW notebook
`256076ee-5bd9-4f45-85f6-d7318e7556d0`，并对照本地 PDF 原文与渲染表格。

- §2.2.18，表 2-32，印刷 pp.65–66：nx2 + TM1 的 DCI 1/1A、1x2；TM3 的
  DCI 2A、2x2 对应开放环路空间复用。不能只读 TRANsmission/NENBantennas 两维。
- §2.2.19.3，表 2-37，pp.75–77：20 MHz/100 RB/QPSK/TBS 5；本片只选该行。
- §2.2.19.4，表 2-38，p.78：20 MHz/100 RB/16-QAM/TBS 13。
- §2.2.19.1，表 2-33，pp.70–71：UL 行沿用仓内已取证
  `CMW500_LTE_FULL_RB_RMC_BY_BANDWIDTH["B200"]`；不复制第二份 TM3/UL 表。
- §2.6.15.2，pp.752–753：TRANsmission / DCIFormat / NENBantennas 的值与组合约束；
  TRANsmission、DCIFormat 自 V3.2.70；NENBantennas 自 V3.0.50；nx2/TWO 需要 KS520。
  TM1 在 nx2 下仍受场景的 KS520 约束，不能因 TM1 单项没有 Options 就豁免整机前置。
- p.794：DLEQual ON 将 stream 1 设置应用于各下行流，自 V3.2.60。
- pp.799–803：RMC/RBPosition/连续分配查询，复用现有带出处的 builder 与 parser。
- §2.6.3.8.1，p.371：CELL:STATe:ALL? 的 OFF/ON/RFHandover 与 PENDing/ADJusted。
  **要求 OFF,ADJUSTED 是本项目的保守安全策略，不宣称厂商禁止在 ON 时配置。**
- 场景回读复用 route_query / route_nx2_query（pp.459–460、630–631），沿用现有命令
  最低版本校验；完整脚本按实际使用命令的最高最低版本限界（包含 V3.5.40 的 nx2 回读）。
  身份/选件查询复用已取证真实访问器，缺失、未知或不足均不进入写阶段。

NotebookLM 回答把 NENBantennas 写成 V3.0.10，与 p.753 的 V3.0.50 矛盾，已弃用该回答；
其“无需强行停止信令”是从示例推广，不用来放宽本序列安全门。
2026-09-11 针对性复查（NotebookLM query `9299baa60a94`，source
`120ade85-3102-4a77-84b4-294bc0f21863`）纠正了上述固件值，确认 D1A/D2A。
DCI 查询形式依据 §1.2.4 的通用设置/查询规则（印刷 p.15），不是声称 p.753 单独印有问号。
手册未说明 TM/天线/DCI 的切换顺序或自动耦合；本序列逐组验错、最终完整回读，
中间设置被拒则停止并归档，不靠推测联动继续下发。

## 执行与故障路径

1. 既有危险诊断互斥门阻止与正式执行并行；required_categories 仅 baseStation。
   通过共同 binding resolver 核实所选 LabProfile、保存配置和所加载 CMW 的身份一致；
   HAL mutation guard 内先完成只读连接/前置核验，通过后在同一锁内取得控制租约并复核绑定，
   不把全局 HAL 中另一台仪器当成本 LabProfile。前置拒绝时保持 HAL 所有的传输连接，
   不调用会关闭现有小区的 release_remote_session；共享安全释放本身不改。
2. 严格解析 sample；真实 CMW 白名单与 `is_mock_driver` 分开判断。不用名字前缀/hasattr
   授权硬件操作。运行快照只作审计，不新增数据库执行真值。
3. 捕获原始交互；读取并归档旧错误队列、身份、选件、当前 Cell/Scenario/FDD/B200，
   并以已有 MCLuster:UL 查询确认连续分配；开启多簇或无法确认时拒绝，不偷偷切换分配模式。
   未知状态、读取拒绝、队列不可解析都停止，不以缓存或 *RST 默认值补齐。
4. 复用 ensure_safe_idle：已 OFF,ADJUSTED 不重复停止；ON 时受控停止并核实结果。
   停止失败不发配置。每个将变更的设置先查现值，只有不匹配才写；每组完成后独立验错
   并查询核对，最后再对完整目标组合统一回读，避免后写字段悄悄改变前面字段。
5. 不发 Cell ON、不做 Attach、不跑测量窗口。成功、拒绝、异常、取消均在租约释放前确认
   安全收尾；失败不得被最后一条 clean queue 或成功 release 覆盖。保留实际发生的部分证据。
   不自动恢复旧射频 ON，也不宣称自动恢复全部配置；诊断后保留目标配置、Cell OFF。
6. 重跑/切换 sample 读取真实现状，不沿用前次 verdict。参数/绑定拒绝发生于连接前，零 I/O；
   身份/FDD/带宽/路由等前置拒绝仅保留查询，不停止原有小区。前置通过后才进入控制租约，
   该阶段失败复用 SAFE_IDLE/release；已发生写入后的失败尽力安全收尾，收尾失败明确报出。

## 产生—消费路径与文件边界

`诊断 GUI sample → API 互斥/锁内绑定与只读前置 → 控制租约 → 固定 sample + CMW 已取证 builder/parser
→ 真实交互比对 → SequenceRunResult → SequenceEvidence → DiagnosticRun → 详情/完整证据查看`。
正式 TestCase/compatibility/执行 outcome/KPI 不新增该诊断的消费入口。

拟改生产文件：

1. 新增 `api-service/app/diagnostics/sequences/cmw500_fdd_matrix_probe.py`：序列与固定 sample。
2. `api-service/app/hal/cmw500_command_profile.py`：仅补缺失且核证后的 DCI 声明/纯 builder，
   其余命令复用现有出口；不放宽正式 MAC SPI。
3. `api-service/app/api/diagnostic_sequence.py`：仅在本序列需要时接入共同 binding resolver
   与锁内校验，传递审计快照；不把其他诊断改成新的执行框架。

新测试 `api-service/tests/test_p2_70_cmw_fdd_matrix_probe.py`，必要的现有诊断契约测试；
更新本设计、roadmap 的 Current Focus/LOCAL-OPEN/P2-55 载体/P2-70/Discovered 镜像。
loader 自动发现新模块；预期不需要新增 GUI、API 路由、数据库表或迁移。

## 验证及完成标准

先 RED 后 GREEN：两种 sample、跨表行拒绝、错误驱动/绑定/选件/固件/Scenario/DCI、
未知状态和回读、非零错误队列、写后被后续设置改写、超时/取消/收尾失败、连续两次运行。
仅替换外部 transport/time/storage，至少一条测试走真实诊断 API 到持久化详情；
既有 GUI 完整证据入口复用详情响应（没有新增或假设独立 export 路由）。
证明 Mock 不进入正式证据，正式 TM3/2 层范围不变；两条核心回退变异必须检出。

增量阶段跑定点与受影响链；最终固定 HEAD 跑全后端、诊断 GUI 契约/build、compileall、
单一 Alembic head、diff-check 和独立功能内审。外审 R1 处理本片 P1/可执行 P2，
R2+ 仅 P1 阻塞；无 P1 且覆盖最新 HEAD、mergeable/checks 满足就合并，不多等空 review。
合并后同步 main、清理本片 worktree；真机两个样本的原始证据另由 P2-55 现场半签收。
