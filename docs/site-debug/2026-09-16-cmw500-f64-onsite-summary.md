# 2026-09-16 CMW500 + F64 现场总结与 roadmap triage

> 整理日期 2026-09-17。事实全部取自当日 `api-service/logs/`（`app.log.2026-09-16`、`scpi.log`、
> `exec-*.log`、`audit.log.2026-09-16`）、开发库 `diagnostic_runs` / `test_executions` 的只读查询，以及本地
> git 历史。本文只记现场事实、逐项裁决与下一轮安排；状态与顺序的唯一入口仍是
> [`docs/roadmap-first-call.md`](../roadmap-first-call.md)。时间均为北京时间。

## 1. 一句话结论

CMW500 + F64 + 真实 DUT 链**第一次跑通到真实吞吐**：执行 `dbd53e6f` 在 LTE B2 / FDD / 20 MHz / TM3 2×2、
SCME UMa 衰落下，单发 5000 子帧窗口读到 **45.82 Mbps、ACK 100 %、BLER 0 %**（`RELative?` 同时给出 NACK 0 % / DTX 0 %：调度的传输块全部被确认，即该调度下的满额），报告生成、
小区关闭与租约释放都有同次证据。正式判词仍是 `UNKNOWN`：无路损校准、无现场认证，另有一组**纯软件缺口（出在与校准无关的资格、强制证据两层）**：
正式证据链的基站一侧目前只有 UXM 驱动实现了，CMW500 永远拿不到正式判词（§4 D4 / D5 / D6；F64 输出态与转台方位两条也是 `unknown`，见 §3）。

**2026-09-17 用户裁决**：① **P0-9 整项关闭**；② **P2-56 现场半关闭** —— B41 下 attach 超时是因为被测手机不支持 B41 频段；
③ **校准尚未正式启动，现在做校准只浪费时间** —— 因「缺路损校准」而挂着的关闭条件不再阻塞当前项，校准正式启动时另立项。

代价：现场提交了 6 次（1 次文档 + 5 次代码：3 处 CMW 驱动 / 执行器真机缺口、1 个功率观察功能、1 处 GUI 布局），后端当天启动 16 次（HAL 关停 17 次）；这些提交**尚未过审**，已原样保存在远端分支 `onsite/2026-09-16-wip`（不在 `main`，见 §5 第 0 步）。

## 2. 当日时间线

| 时间 | 事件 | 证据 |
|---|---|---|
| 10:11 | 信号分析仪 FSVA `192.168.0.134:5025` 连不上，该品类随后停用 | app.log |
| 10:45 | `instrument_idn_sweep` 报 7/7 无响应 —— 序列契约问题，不是仪器离线 | DiagnosticRun `94a93c8a` |
| 11:22–11:49 | `chamber_configuration_integrity` ✓；`emcenter_switch_health` UNDETERMINED（`INTLK?` 已知不支持，与 08-27 一致）；`aerotech_positioner_health` ✓（az=90°） | `c122afd8` / `c2c2330c` / `0b39e487` |
| 11:49 / 11:54 | `propsim_f64_license_truth` 两次 UNDETERMINED，稳定复现 `-200 No simulation opened` + `-100` | `e916b910` / `c3a445a2` |
| 11:58 | `propsim_f64_p08_gate` 参数门拒绝（UXM 专属，误启动） | `78aa4816` |
| 12:03 | `cmw500_fdd_matrix_probe` 预检拒绝：「仅接受已配置 FDD」—— 当时 CMW 在 TDD | `a0395c8a` |
| 12:13 | 执行 `7d347c03`（B41 TDD）：CMW 拒 `set_cell_config`；转台 `MOVEABS X -90` 途中连接被 reset → 结局未知 → 急停（零速度确认） | exec log |
| 12:29 | 提交 `a5206310`：`apply_route` 挪到 `apply_config` 之前 | git |
| 12:31–13:54 | 执行 `31ec74a2` `804ca4fe` `d058d9de` `f8f5fd90`（B41 TDD，EARFCN 40340）：配置全部被真机接受，**UE 60 s attach 超时 ×4**（PS 状态恒 `ON`，仅一次瞬时 `SIGN`） | scpi.log |
| 13:05 | 提交 `dc0d3ecc`：Cell ON 后、attach 计时前的 F64 功率观察窗 | git |
| 13:24 | 操作员经原始 SCPI 端点对 F64 发 12 条查询（STATE / WRAP / TRIG / MODEL:STATE / MODEL:CONT / `CH:MOD:TIME?`，含 3 次 `SYST:ERR?` —— 它会消费错误队列，不算纯只读） | DiagnosticRun ×12 |
| 13:46–13:47 | 执行 `accad7ff` `0cb7e0ac`：路由 `…RF2C,TX2` 被拒 `-221 Invalid path settings`；改回 `RF3C,TX2` 后接受 | scpi.log |
| 14:46 | 用例改为 **B2 FDD EARFCN 900**；执行 `f7afe522` 被 P2-11 拦：资产登记仍是 B41/40340（F64 已接受 `CENT 1960.0`） | scpi.log / audit |
| 14:48 | 改资产后执行 **`a4168179` completed**：UE **3 s** 挂上；旧 CONTinuous 窗口路径 → `Tput=N/A` | exec log |
| 15:23 / 15:33 | 提交 `fc3fbccc`（单发窗口）/ `4c5fa624`（`SINGle`→`SINGleshot`）；中间执行 `86fa0f98` 因 `SINGle` 被拒失败 | git / exec log |
| 15:35 | 执行 **`dbd53e6f` completed**：UE 30 s 挂上，窗口 RUN→RDY 5.2 s，45.82 Mbps / ACK 100 % | scpi.log |

## 3. 关键原始证据（`dbd53e6f`）

- **路由**：写 `ROUTe:LTE:SIGN1:SCENario:TRO:FLEXible SUA1,RF1C,RX1,RF1O,TX1,RF3C,TX2`；专用七字段回读
  `…TRO:FLEXible?` → `SUA1,RF1C,RX1,RF1O,TX1,RF3C,TX2`（逐字段一致）；通用 `ROUTe:LTE:SIGN1?` →
  `TRO,"No Connection",RF1C,RX1,RF1O,TX1,RF3C,TX2`（Controller 字段不可用作 BB board 证据，与设计预期一致）。
- **小区配置**：`DMODe FDD` / `BAND OB2` / `B200` / `CHANnel:DL 900` / `RSEPre -50` / `TM3` / `NENBantennas TWO`，逐条
  OPC=1、错误队列 `0,"No error"`、回读一致；MAC profile 回执 `confirmed=True`。
- **Cell-ready 功率观察（60 s）**：CMW RS-EPRE 配置回读 −50 dBm；F64 输入 1/2 = −29.35 / −27.70 dBm →
  −28.51 / −28.75 dBm；16 路输出 −39.3 ～ −58.7 dBm；仿真 `RUNNING`，拓扑来源 `readback`，查询零错误。
- **吞吐窗口**：`TOUT 0` → `REPetition SINGleshot` → `SCONdition NONE` → `SFRames 5000`（回读 5000）→ `INIT` →
  `STATe? RUN` → 5.2 s 后 `RDY`；`EBLer:PCC:ABSolute?` →
  `0,9000,0,5000,4.582000E+004,4.582000E+004,4.582000E+004,0,4500,INV`；`RELative?` →
  `0,1.000000E+002,0.000000E+000,0.000000E+000,1.000000E+002,0.000000E+000`。
- **收尾**：`PSWitched DISConnect` → `CELL:STATe OFF` → 回读 `OFF,ADJ`；F64 GOS 停止并回卷、ATE socket 释放；
  租约 `formal-case:dbd53e6f…` 释放；`control_releases` 记 `transport_session_released` 已确认，CMW 前面板 Local 无有据确认 → unknown。
- **判词**：`execution_qualification=diagnostic`（`test_case_policy_diagnostic` + `site_certification_not_active`）；
  `scpi_evidence.formal_acceptance=false`，`reason=frequency_identity_not_fully_verified`，
  `missing_requirements=[base_station.pcell.config_applied, base_station.throughput.azimuth.000]`；路损 `missing`（1960 MHz 无校准）。
  同一份 `scpi_evidence.items` 里另有两条为 `unknown`：`f64.output_state`（`invalid_evidence_provenance:live_environment_missing_or_mismatched`）、
  `positioner.azimuth.000`（`live_environment_missing_model_or_firmware_version`，与 roadmap U-8「Aerotech 型号 / 固件只读确认」同源）；`f64.model_loaded` 为 `passed`。
- **TDD 半场的配置事实**（`f8f5fd90`）：`DMODe TDD`、`ULDL 1`、`SSUBframe 1`、`DLEQual ON` 后 `RMC:DL1 N100,Q16,T13`，
  `RMC:DL2?` 与 `RMC:VERSion:DL2?` 回读均跟随 DL1；选件含 `KS510,KS512,KS550`；F64 接受 `CENT 2565.0`。配置层全部通过，失败只在 UE attach。

## 4. 逐项裁决

### 4.1 标注完成 / 关闭

| 项 | 裁决 | 依据 |
|---|---|---|
| **P0-9A** 诊断主线（真实 Attach + PRECHECK→MEASURE→ANALYSIS→REPORT） | ✅ 完成 | `a4168179`、`dbd53e6f` 两次 completed；attach 终态 `data_bearer_established` 为 authoritative confirmed；报告 PDF 生成 |
| **P0-9B-1** `PCCBBBoard` 专用七字段 query 真机复验 | ✅ 完成 | 专用回读逐字段一致、原始回复在 scpi.log；通用 query 的 Controller 字段确为 `"No Connection"` |
| **P0-8b** DUT Attach 后 DL 非 0 % ACK / 不失真 | ✅ 完成（P0-8 整项收口） | 衰落下 ACK 100 % / BLER 0 %，`RELative?` 为 ACK 100 % / NACK 0 % / DTX 0 % —— 调度的传输块全部被确认，即该 RMC 在此调度下的满额（45.82 Mbps）。最难的衰落态已满额，bypass 半不再单独要求 |
| **P2-55（现场半）** 矩阵抽样 | ✅ 改验收后收口（用户现场结论） | 探针未跑成（预检拒 TDD）。开测前的抽样对「这次测试」不必要 —— 探针产出零消费者，正式执行自带同次的写→错误队列→回读证据，TM1/1TX 在正式 schema 不可达，探针要的 FDD 前置只有正式执行才会建立。TM3+2TX 格由 `dbd53e6f` 的同次 config / MAC 回执签收；TM1+1TX 格降为「正式 schema 开放 TM1 时的扩域前置」 |
| **P2-56（现场半）** LTE TDD 真机认证 | ✅ 关闭（用户 2026-09-17 裁决） | 真机接受 `ULDL` / `SSUBframe`（本机选件齐）、`DLEQual ON` 先于 RMC 时 DL2 跟随 DL1、顺序未见拒绝。B41 下 attach 4/4 超时的原因：**被测手机不支持 B41 频段**，不是系统缺陷。TDD 下的真实 Attach / 窗口尚无真机样本，由首个用支持 TDD 频段 DUT 的正式 TDD 执行自带的同次证据验证，不再单独排现场项 |
| **P0-9**（整项） | ✅ 关闭（用户 2026-09-17 裁决） | A / B-1 见本表前两行。B-2（路损校准）与 C（正式验收）以校准为前提，校准未正式启动，不再作为本项关闭条件，启动时另立项。B-3（多方位 / HOME 复验；当日 `-90°` 移动结局未知并急停）的内容同时挂在 P0-5 行与 NEW-4 / P1-56 行，随那两行走；转台断连本身见 D8 |
| **P2-51（现场半）** CMW MAC requested/applied 真机闭环 | ✅ 完成 | 同一 execution/attempt：MAC 回执 confirmed、窗口生命周期 confirmed（统计基 requested 5000 / applied 5000）、SAFE_IDLE（`OFF,ADJ`）、transport release、报告 |

> 上表按现场证据完成的各项，证据由 6 个**未过审的现场提交**产出。证据描述的是仪器行为，不因代码评审而失效；但
> 「代码落地」是独立的事，见 §5 第 0 步。若评审改变了窗口或回执语义，须在下次现场用合并后的版本复跑一次并补记。

### 4.2 取得了新事实，但不能关闭

| 项 | 现状 | 还缺什么 |
|---|---|---|
| **P1-74（现场半）** 统计基不继承 | 只有一个 `SFRames 5000` 样本；且窗口已改为单发（统计长度 = 窗口本身，每次显式写 + 回读） | 仍需两个不同 `stat_count` 的连续执行 |
| **P1-4** 重复性 | 两次 completed 不可比（第一次 `Tput=N/A`，走的是旧窗口路径） | 同一版本、同一用例连跑两次 + execution 级对比报告 |
| **P1-2** F64 许可真值 | 序列自身缺陷，转「软件修复后现场复验」（已登记） | 修序列 |

### 4.3 当日未执行（状态不变）

NEW-1（`propsim_f64_output_level_windows`）、NEW-2（`propsim_f64_local_handback_check`）、P2-71 设备半
（`propsim_f64_health` 未跑）、P2-61/62 真实 CE 认证、NEW-4 / P1-56 转台运动真值序列、P2-9（仍 UNDETERMINED，同 08-27）。

### 4.4 新 Discovered（均已写入 roadmap，出口见 §5）

| # | 发现 | 级 |
|---|---|---|
| D1–D3 | `instrument_idn_sweep` 范围 / 身份契约、`propsim_f64_license_truth` 空回复显示成功（并入 P1-2）、`propsim_f64_p08_gate` 硬编码 UXM —— 09-16 当场已登记 | 见原条目 |
| **D4** | CMW500 配置回执里 `radio_technology` / `channel_kind` / `frequency_mhz` 三个字段恒为 unknown → `base_station_execution_evidence.config_confirmed=False`。**配置其实回读了**：请求的 10 个非空字段里 7 个（band / 带宽 / EARFCN / duplex / TM / 层数 / 下行功率）逐条「写→回读一致」confirmed；没确认的这 3 个不是仪器参数，而是请求里的描述 / 派生字段（`"lte"`、`"lte_dl_earfcn"`、由 band + EARFCN 换算的 `1960.0`）。规则要求请求里**每个**非空字段都有权威确认（`receipt_payload()`），而 CMW500 驱动的回读字典（`_last_common_config_readback`）从不放这三项 → 恒 unknown。后果：**签发不了基站站点认证**（签发是操作员动作，09-16 审计日志里没有任何签发请求；即使去签也会被拒 —— `activate_base_station_site_certification` 要求来源执行 `config_confirmed is True`），于是每次执行都只能是 diagnostic；同一个标志还让 attempt 生命周期与正式信封返回 `config_not_confirmed`（`base_station_execution_evidence.py`），吞吐投影因此进不了 trusted。与校准无关。（更正 2026-09-17：初稿写「→ 强制证据 `config_applied` 缺失」，因果写错了 —— 那条缺失另有原因，见 D5） | P1（正式判词的软件缺口，与校准无关） |
| **D5** | **正式强制证据（`scpi_evidence`）的基站一侧只有 UXM 驱动实现了**：`build_p0_5_config_evidence` / `build_p0_5_throughput_evidence` / `get_frequency_identity`（基站侧）仅 `uxm_base_station.py` 有，`capture_evidence_environment` 也没有 CMW500 版本；`measure.py` 用 `hasattr` 守着写方，没有接口就不写。所以 CMW500 的 `base_station.pcell.config_applied` 与 `base_station.throughput.azimuth.NNN` **没有写方、恒缺失**，频率一致性网记 BaseStation「未报告(跳过)」→ `fully_verified=false` → 判词恒为 `frequency_identity_not_fully_verified`。与校准无关 | P1（同上） |
| D6 | 窗口 confirmed、吞吐 `throughput_valid=true`、45.82 Mbps 已读到，但 `base_station.throughput.azimuth.000` 仍列为缺失。**已核：不是 D4 的连带**，是 D5 —— CMW500 没有 `build_p0_5_throughput_evidence`，读到的吞吐从未被记成强制证据。同一份证据里另两条 `unknown`（§3）也与校准无关：`f64.output_state` 的命令与回读都对（RUNNING = RUNNING），但记证据那一刻 F64 的仪器身份快照被判为非 live（型号 / 固件置空）。**根因已查清，是确定性缺陷不是现场偶发**：`start_emulation()` 成功后把驱动状态置为 `InstrumentStatus.BUSY`，而 `capture_evidence_environment()` 只把 `CONNECTED` / `READY` 算作 live —— 仿真一运行，这条证据就必然记成 unknown，与基站型号无关（UXM 链走同一段 `measure.py`）。修之前先用一条 RED 测试坐实；`positioner.azimuth.000` 的角度回读无误（误差 0.0°），缺的是 Aerotech 型号 / 固件的只读确认（roadmap U-8）—— 驱动的 `capture_evidence_environment()` 把 `model` / `firmware_version` 写死为 `None`（「AeroBasic 当前路径无安全的型号 / 固件查询」），这条证据同样是构造上恒 unknown。ANALYSIS 层同一次执行的实况：`measurement_verified=true`，其余 `frequency_identity_verified` / `path_loss_verified` / `throughput_verified` / `rf_kpi_verified`（RSRP / SINR / RI 在 0° 方位均无真实来源证据）/ `qz_verified` 全为 false，首个停因是「执行冻结为 diagnostic」—— 补齐任何一层，结论只会挪到下一个原因 | P2 |
| D7 | B41 TDD（EARFCN 40340、F64 `CENT 2565`）attach 4/4 超时；同日 B2 FDD 3 s / 30 s 挂上。**用户 2026-09-17 确认原因：被测手机不支持 B41 频段** | resolved |
| D8 | Aerotech：`MOVEABS` 途中 `Connection reset by peer` → 非幂等命令结局未知 → ABORT 读 `VFBK(X)` 得空串无法证明停止 → 急停；全天 `Disconnect error [Errno 54]` ×10、「transport already closed — lazy reconnect」×9。另：单轴台每次连接都以 ERROR 级打印 `PFBK(Y)`（×30），随后才识别单轴 | P2（安全 / 稳定）+ P3（日志噪音） |
| D9 | `input_level_calibration` 在两路回读均为 `null` 时仍记 `success: true`（Cell ON 前 `measure_input` 返回空串）。功率观察窗补了后置真值，但这个字段仍在说假话 | P2 |
| D10 | **用户现场发现**：`.smu` 内置中心频可被 API 改写（`CALC:FILT:CENT:CH 1,1960.0` / `2565.0` 均被接受），文件名与资产登记频率不排他；资产层却把频率当排他身份，`f7afe522` 因此被 P2-11 拦下 | 设计（先查 PROPSIM 手册） |
| D11 | **用户现场发现**：FDD 预验证非必要（§4.1 P2-55 行）；runbook §2 由必做降为可选 | 文档 |
| D12 | `dc0d3ecc` 在 `measure.py` 用 `adapter_id == "cmw500" and … "propsim_f64"` 分支 → 规则门 `test_p2_43…` 与 `test_p2_46…` **当前为红**（全量 6559 passed / 2 failed） | 落地阻塞 |
| D13 | 3 处 CMW 真机缺口（route 须先于 config、CONTinuous+STOP 路径读不到吞吐、`SINGle` 非法 token）fake transport 全放行，只能现场撞 | P2 候选 |
| D14 | 操作员需要 F64 运行态（STATE / WRAP / TRIG / MODEL 进度）而无序列可用，改用原始 SCPI 端点 12 次（含 3 次 `SYST:ERR?`）；`CH:MOD:TIME? n` 两次空回复，语义未知 | P3 候选 |
| D15 | 信号分析仪 FSVA `192.168.0.134:5025` 当日连不上（10:11 VISA 连接失败，10:13 操作员停用该品类）。它只用于路损 / 探头校准与参考 TRP，吞吐测试链不用它，当天测试未受影响 | 不再是前置：校准正式启动时再处理 |
| D16 | 调试机开着代理 / VPN：HAL 连仪器前会先探两个按标准**不可能存在**的地址（`192.0.2.1` / `198.51.100.1`），当天它们居然「连得上」—— 说明代理在替任何地址应答，「子网通不通」的预检结果不可信，系统于是整天跳过预检（告警 ×21）。不影响测量；代价是连不上的仪器要等约 10 s 的 VISA 超时才报错，且就绪页的子网状态全显示「未探测」 | 现场 checklist：到场先关代理 |

## 5. 下一轮安排（待用户批准顺序；WIP = 1）

**第 0 步 — 现场改动落地（建议不做完不开新片）**：现场的 6 个提交与当时未提交的 5 个代码 / 测试文件已原样保存到远端分支 `onsite/2026-09-16-wip`
（末端 `5387ac1e` = 6 个现场提交 + 1 个保存未提交改动的 WIP 提交；**仅为保全，不是评审单元**；那个 WIP 提交里还夹着三份 triage 文档的旧稿，拆 PR 时不要带出来），本地 `main` 已对回 `origin/main`。
下列提交号都可从该分支取回。各改动从 `origin/main` 另起分支，拆成独立 PR，逐片内审 + Codex R1→R2：

1. 本次 triage 文档（纯文档）。
2. `fix(cmw500)`：route 先于 config + 单发吞吐窗口 + `SINGleshot`（`a5206310` / `fc3fbccc` / `4c5fa624`）——正式 KPI 采集语义变化，全套审查。
3. `feat(onsite)`：Cell-ready 功率观察窗（`0cd48ea4` / `dc0d3ecc`）——**先把厂商分支换源到 manifest / 执行计划能力**（D12），两道红门转绿后再审。
4. `fix(f64)`：stop 回执接受 `CLOSED` 为安全空闲终态（WIP 提交 `5387ac1e` 里的 5 个代码 / 测试文件）。
5. `fix(gui)`：app shell 裁切（`660ef580`）。

**第 1 批 — 纯软件修复（不需要现场；批内先后待用户定）**：

- **P1-79 已撤销伞形项，按根因拆成子项**（用户 2026-09-17 指示；每个子项 = 1 个 PR，各自走完整生命周期；批内先后待用户定，建议 A → B → C → D，E 等手册）：
  - **P1-79A** F64 运行态身份快照被判非 live → `f64.output_state` 恒 unknown。根因确定、改动最小、与基站型号无关。修法形状：收窄 live 判据（连接在即 live，`BUSY` 不是「未连接」）。
  - **P1-79B** CMW500 配置回执三个描述 / 派生字段的确认来源 → 解锁 `config_confirmed`（站点认证签发、attempt 生命周期、正式信封 / 吞吐 trusted 三个读方）。要设计：由已确认的仪器事实派生，还是移出「须确认字段集」；CMW 语义须有 R&S 手册出处。
  - **P1-79C** 基站强制证据记录器去 UXM 写死 + CMW500 的配置 / 吞吐证据写方与仪器身份快照（`base_station.pcell.config_applied`、`base_station.throughput.azimuth.NNN`）。共享证据契约，全套审查。
  - **P1-79D** CMW500 频率身份回读（`get_frequency_identity`），让频率一致性网的 BaseStation 一方不再「未报告(跳过)」。须有 R&S 手册出处。
  - **P1-79E**（= roadmap U-8）Aerotech 型号 / 固件的安全只读确认 → `positioner.azimuth.NNN` 不再恒 unknown。前置：厂商手册里找到安全的身份查询，找不到就保持 unknown。
  判「正式」有三层：① 资格（`execution_qualification.py`）② 强制证据（`execution_scpi_evidence.py`）③ ANALYSIS 阶段的 KPI 结论（`analysis.py`）。**前两层的判据里没有路损 / 校准条件，上述子项都在这两层，不因「校准未启动」而可忽略**；第三层按顺序还要过频率身份 → 路损校准 → 吞吐 → RF 指标（RSRP / SINR / RI）→ 静区场扫描。所以这些子项做完而校准未做时：站点认证签得出、执行可归 formal、证据层通过，但报告的 KPI 结论仍是 `UNKNOWN`，原因换成路损。
  另记候选（不立项）：CMW500 的 RSRP / SINR / RI 在 ANALYSIS 层无真实来源证据（`rf_kpi_verified=false`），排在路损之后，校准启动时再评估。
- **建议 P2-74**：Aerotech 传输稳定性与单轴日志（D8）—— 当天唯一一次急停出在这里，下次跑多方位先得它稳。先枚举断连形态，修法优先收窄 / 换源。
- **建议 P1-80**：P1-2 序列修复（逐查询错误归属、空回复 fail-closed、license / calibration / user-alignment 分判）。
- **建议 P2-73**：`propsim_f64_p08_gate` 按服务器权威 BaseStation 身份 fail-closed 为 UXM-only（D3）。
- **建议 P2-75**：`instrument_idn_sweep` 范围与结构化身份投影（D1）。
- **建议 P2-76**：`input_level_calibration` 空回读不得记成功（D9）。

**第 2 批 — 设计先行**：

- **建议 P2-77**：信道资产频率从「排他身份」改为「默认值 + 本次执行下发/回读真值」（D10）。**开工条件**：取得并记录
  可核对的 PROPSIM 手册章节 / 页码或原文（NotebookLM 的回答要追问「是原文还是推断」），说明 `CENT` 可改范围是否受 `.smu` 内滤波器 / 带宽 / 许可限制；一次现场接受不算依据。**查不到就保持现有的 fail-closed 语义，不放宽**；查到了再出设计稿。
- P2-55 验收换源与 runbook §2 降级（D11）——随本次 triage 文档落地。
- D13 / D14 保留候选，不自动立项。

**下次现场的前置清单**：关闭调试机代理（D16）；要测 TDD 就带支持对应频段的 DUT；多方位用例等 P2-74 修完再带；
NEW-1 / NEW-2 / P1-74 / P1-4 / P2-61/62 排独立时段。**不排校准**（用户 2026-09-17 定：校准尚未正式启动），信号分析仪不需要到场。

## 6. 过程复盘

- **「现场不写 driver 代码」这条铁律当天被打破**：5 次代码提交（另有未提交的 F64 stop 回执改动），每次保存触发 uvicorn reload（`DEBUG=true`），后端全天启动 16 次（HAL 关停 17 次），
  每次都断开全部 VISA 会话。三处改动都有真机依据且方向正确，但它们暴露的是出发前的缺口：CMW 的 route / config 顺序、
  真实吞吐窗口、枚举 token 从未对着真机或带语法校验的 fake 跑过（D13）。
- 现场提交**没有过内审、没有 PR、直接落在本地 `main`**（2026-09-17 已移到保护分支 `onsite/2026-09-16-wip`，`main` 对回远端），其中一处踩了仓库自己的厂商分支门（D12）。
- 操作员 12 次使用原始 SCPI 端点，说明 F64 运行态缺一个只读快照序列（D14）。
- 做对的事：错误配置（`19600 MHz` 笔误、无效转台 profile、资产频率不符、`-221` 路由）全部被既有的门当场拦下，没有一次带着错配进测量；
  转台结局未知时执行了「不重放非幂等命令 + 急停确认」。
