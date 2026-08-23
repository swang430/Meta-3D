# CAICT 现场日志 — 2026-05-27 上午

> 目的：精确记录上午实测数据，供下午改代码用。所有数值/错误码/命令均为现场实测原文。
> 配套已建的 backlog chips（F64 GCM 命令时序 / F64 .smu MPAC 扩展 / UXM 配置捕获）。

## 🎯 上午里程碑：首个经暗室 OTA 的 call 打通

**UXM CELL1 → F64 直通 → 暗室探头 → 真实 DUT，下行 PDSCH 数据 100% ACK。** CAICT 两天没到这一步。
范围诚实话：**F64 处于手动直通（无信道仿真）、单层**。衰落 MIMO 信道保真度待 offline 修 F64。

---

## 1. 环境 / 连通（已通）

- 控制 Mac 网卡 **en14 = 192.168.0.3/16**（/16 覆盖三子网）。手动加别名 **192.168.1.10/24**（UXM 同段源地址，否则 UXM 回包发不回）。100.x 未配（SA 今天不在）。
- 仪表真实 IP：F64 `192.168.0.132:5025`、UXM `192.168.1.112`、FSVA3000 SA `192.168.100.23`(**今日缺席**)、Aerotech `192.168.0.16:8000`、ENA `192.168.0.10`、EMCenter switch `192.168.100.26`、SMW `192.168.100.27`。
- **P1-15 canary = False**（en0 上有 `198.18.0.1` 代理/热点默认路由）→ cockpit 子网面板正确标"未探测·代理/VPN"。**设计如此**：全程以 `nc`+ARP+实时 SCPI 为准，不信 ping/面板绿。canary 在现场得到验证。
- HAL 切 real → **3/7 真驱动加载**：channelEmulator(F64)/baseStation(UXM)/positioner(Aerotech)。SA/VNA/switch/SMW 离线（SA 缺席，其余今天没上电）。

## 2. 仪表身份（实时握手）

- **F64**：`SYST:INFO?` → PROPSIM F64，固件 v2.0，450–6000MHz。（`*IDN?` 通用探针"失败"是 PROPSIM quirk，正常。）
- **UXM**：`*IDN?` → `Keysight Technologies,C8700200A Test Application Framework,MY60102098,28.21.0.3252`（早期读到 E7515B Platform FW 3.39.0.2）。Test App = **LTE_NR_IRAT**，primary cell **CELL1**，hislip#2，命令前缀 **BSE:**。
- **Aerotech**：A3200 控制器 `:8000` 连上。

---

## 3. ⭐ 给下午改代码的精确发现（F64 GCM 信道）

### 3.1 加载序列（engine_mode=keysight_gcm，干净会话复测可复现）
```
DIAG:SIMU:CLOSE
CALC:FILT:FILE  D:\User Emulations\UMa CDL-C NLOS_UMi_2x2.smu     ← *OPC? 回 1，文件加载本身 OK（文件存在）
CALC:FILT:CENT:CH 1,3500.0
CALC:FILT:CENT:CH 2,3500.0
... (逐通道 range(1, _channel_count+1))
DIAG:SIMU:GOS                                                      ← 注意是 GOS 不是 GO
```
- 干净会话复测：**207 条 `-200,"Execution error;Wrong device state for command"` + 2 条 `-350,"Queue overflow"`**。来源 = `CALC:FILT:CENT:CH N,3500.0`。
- 驱动**无视错误**仍打 `[NativeModel Strategy] Channel model successfully loaded via native engine`（**谎报成功**）。
- `DIAG:SIMU:GOS` 之后立即 `[F64] ... Invalid session handle. The resource might be closed.` → **会话死**。

### 3.2 根因（现场专家纠正，关键）
- **OTA/MPAC 模式下 .smu 要按探头数扩展**：2x2 是裸 Tx×Rx，经 MPAC 变 **2×32×2**，在 F64 上是 **2x32** 配置。
- 驱动 `set_channel_model()` (app/hal/propsim_f64.py ~648-653) 用 `{model}_{scenario}_{_tx_antennas}x{_rx_antennas}.smu`，`_tx_antennas/_rx_antennas` **默认 2x2 从没按真实 MIMO+探头数更新** → **加载了 2x2 文件**，却按 `_channel_count`(=64 或 sys_info 给的 32) 逐通道下发 CENT:CH → 超出模型通道数的 CH 全被拒。
- scenario 疑似硬编码/默认 `UMi`（模型名是 `UMa CDL-C NLOS` 却拼 `_UMi` → 文件名自相矛盾）。

### 3.3 修复方向（offline）
1. 文件名按 MPAC 探头数拼 `2x32`（取 LabProfile chamber.num_probes），不是裸 Rx。
2. `_tx_antennas/_rx_antennas`/通道数从 MIMOOTAConfiguration + LabProfile 传入。
3. scenario 跟 cdl_model_name 一致，不硬编码。
4. 加载后**校验模型通道数 == 要配置的通道数**，不匹配 fail-loud；成功判定要 **gate SYST:ERR? 为 0** 才算成功（消除谎报）。
5. 核对 `DIAG:SIMU:GOS` vs `GO`（每次会话死都在 GOS 后）。

### 3.4 F64 会话生命周期
- **单 client SOCKET 会话死后不自动重连**。`GET /readiness` 的 `ok` 是**缓存快照**（HAL init 时），不反映实时死活——实时探活要 `POST /instruments/{cat}/scpi-command` 发 `SYST:ERR?`。
- 复活靠 `POST /instruments/hal/reload?force=true`。
- ⚠ **HAL reload 被僵尸 plan 挡**：reload 报 blocker = "Priority Test Plan"(id `52f750a5-...`) status=running，但 `GET /test-executions?status=running` = **0 条**。→ reload 守卫读的"running"是个**僵尸 TestPlan 状态**（无对应执行）。`?force=true` 安全绕过（0 真执行）。**offline 修**：reload 守卫应核对是否真有在跑的执行，别被僵尸状态挡。

## 4. F64 直通（passthrough）

- 驱动有 `set_passthrough_mode()` → `DIAG:SIMU:MODEL:STATIC 3`（CALIBRATION，全通道等增益/等延迟/零相位透传，User Ref §20.4.6.25）。
- **SCPI 设直通也撞墙**：发 `DIAG:SIMU:MODEL:STATIC 3` → `SYST:ERR?` 回 `-200 Wrong device state`，`DIAG:SIMU:MODEL:STATIC?` 空响应。→ 跟 CENT:CH 同一个"F64 状态机前置条件没满足"。
- **今天靠操作员在 F64 GUI 手动置直通成功**。offline 应搞清进入直通/配通道前 F64 需要的正确状态序列（可能要先 load 某 emulation / 进某模式）。
- F64 端口实测：**5025 SCPI 开 / 445 SMB 开 / 3389 RDP 开 / 21 FTP 关**。→ FTP 关 = mimo_first_asc(EXTERNAL_WAVEFORM, FTP 上传)路被堵；只能走 GCM Native。

## 5. 首个 call 的吞吐铁证（直通态）

`BSE:MEASure:NR5G:CELL1:BTHRoughput:DL:TSTatistics:JSON?`：
- 第一次：`ProgressCount 89400`，**Tx1 Total 134100 / Ack 134100 / Nack 0 → ACK 1.0000 (100%)**，Tx2/3/Other = 0（NaN 哨兵 9.91E+37）。
- 复查：Tx1 Total 93300，ACK 1.0000。
- 解读：**下行 PDSCH 单层，134100 个 TB 全 ACK、0 NACK** = DUT 经暗室收到下行数据、链路无误码。单层（Tx2+ 为 0）因 F64 直通不产生 MIMO 空间流。

## 6. UXM 工作配置（已存 `api-service/app/data/uxm_configs/caict_dut_attached_2026-05-27.json`）

- 可靠回读：band **N78**、DL ARFCN **636666**、DL/UL **BW40**、Point A **632946**、CELL1 active=1。
- **读不到（C8700200A 查询形式不支持，`?` 超时）**：SCS / DUPLex / DL 功率 / SSB 功率 / MIMO 层数+codebook / RF 端口 / **天线→端口路由** / PDSCH MCS+RB。
- **原生 SAVE 不灵**：`SYSTem:CONFiguration:SAVE` 被接受但不生成文件（C8700200A 不适用该命令/路径）。（2026-08-24 注：P1-67 手册对账证实该命令手册查无，与"被接受但不生成文件"的实测**相符**（因果未单独证实——当日队列只见 -221 无 -113）。P1-67 #383 的 `SYSTem:SCPI:EXPort` 换源**仅覆盖 5G_NR_Test 方言**；本机 C8700200A（IRAT）下 EXPort 可用性手册未说明、profile 置 None fail-closed——**GUI「Save Configuration」仍是本机唯一可靠路径**）
- 潜伏告警：`SYST:ERR?` 有 `-221,"Settings conflict; PUCCH Resource ID 2 is enabled in Resource Set 0"`（没挡 attach/数据）。
- **完整存配置唯一可靠路径**：C8700200A app GUI「Save Configuration」。offline 修：对照厂商手册补 LTE_NR_IRAT profile 的查询/存档命令 + 给 UxmTopologyProfile 加"捕获 live 状态"。

---

## 7. 下午计划

1. **转台（Aerotech A3200）控制** —— 单轴回零/定位（CAICT 曾卡单轴；探针支持单轴模式）。
2. **开关控制器（ETS-Lindgren EMCenter switch, 192.168.100.26）** —— 需先配 100.x 别名 + 上电；IDN + 通道切换。
3. 有时间：修 F64 .smu 文件错配（2x32）+ UXM 其他控制（配置查询/存档）。

## 8. backlog chips（已建，offline 修）
- F64 GCM 加载：谎报成功 + 命令状态错乱(-200) + DIAG:SIMU:GOS 杀会话。
- F64 .smu 文件名按 MPAC 探头数扩展（2x2→2x32）。
- UXM C8700200A 配置捕获/存档：查询形式 + 原生 SAVE 都不通。
- HAL reload 守卫被僵尸 "running" TestPlan 误挡（0 真执行）。
- **SCPI 连接生命周期**：实现 acquire-use-release（单 client 仪表用完释放）+ connect 失败原因诊断 + 前序僵尸会话定向强制释放。现状仅"持有 + conn-lost 本地重开 socket 一次"（救不了 F64 单 client 服务端僵尸会话 → 上午靠 force-reload 粗暴恢复）。代码位：instrument_hal_service.py:677-679 持有 / propsim_f64.py:509-513 失败不分类 / :1957+:2012/2040 本地重连。
- **转台无 standalone 控制路径（PM 发现）**：positioner 驱动有 `move_to/get_position/HOME/stop/is_single_axis`，但 ① 无 REST move/home/position 端点（只被 cal/QZ 服务内部调）；② `scpi-command` HAL 路由(`instrument.py:1824-1847`)对查询调 `driver._query`、写调 `driver._write`，而 Aerotech 驱动只实现 `_send/_tx_rx/_query_value`（且 AeroBasic 查询不以 `?` 结尾）→ 通用 SCPI 终端无法驱动/读取转台。**现场无法经我们栈单独验证转台/单轴回零（铁律1：不现场加端点）**。已 spawn offline chip。

---

## 9. 下午追加 — UXM SCPI「拆-重建」演练（PM ~13:33，DUT 全程在场）

> 目的：验证我们的软件能否纯 SCPI 驱动完整 cell-cycle。**主动拆掉上午的 working call 重建**（用户授权高风险路径）。结果：**成功，且重建后比拆前更干净**（错误队列清零、未再生成 UL 冲突）。

### 9.1 关键正向验证 ✅（首次实测）
- **纯 SCPI 全程跑通**：停 cell → 重设 7 条参数 → 重启 cell → 自动重附着 → 测吞吐。**全程零错误**。
- 时序铁证（`/tmp/uxm_teardown_rebuild.py`）：
  - `BSE:CONFig:NR5G:CELL1:ACTive:STATe 0` → `BSE:STATus?` = **OFF**，`SYST:ERR?` clean。
  - 重设 `BAND N78 / DL:ARFCN 636666 / DL:BW BW40 / UL:BW BW40 / DL:POINta 632946 / DL:POWer -46 / SSB:POWer:ADVertised 0` —— **逐条 gate `SYST:ERR?` 全 clean**。
  - `ACTive:STATe 1` → `BSE:STATus?` **ON→ON→CONN，~6 秒**。NSA 下 LTE 锚点 hold UE，重激活 NR 后 **SCG 自动重加**，无需 GUI 介入。
- **结论**：我们**可以**用 SCPI 编排 UXM cell 建立（可设参数部分）。这跟上午"靠操作员 GUI"形成对比——配置下发路径本身是通的。
- **频率类只能原值重设**：DUT 按 N78/636666/BW40 provision，改任一频点必 attach 不回（未实测，但这是为什么重建只复原不改值）。

### 9.2 物理层指标 — SCPI 真实边界（`/tmp/uxm_measure.py` 实测）
| 指标 | 命令 | 结果 |
|---|---|---|
| DL ACK 率（=事实 BLER） | `...BTHRoughput:DL:TSTatistics:JSON?` | ✅ **Tx1 ACK ≈ 99.9% 单层**；ProgressCount 9s +9200 = 在传；Nack 60 为重附着瞬态不增长 |
| DL BLER 统计 | `...BTHRoughput:DL:BLER:STATistical:ALL?` | ◑ 命令支持但停在 `IDLE,UNKN,0,0`（统计未被 enable，缺 enable 命令/GUI） |
| 吞吐窗口重置 | `...BTHRoughput:DL:TSTatistics:STARt` | ❌ **-113 不支持** → 计数器自由运行，SCPI 无法归零窗口 |
| CSI CQI | `...CSI:CQI:STATistics?` | ◑ `CSI:STARt` **支持**(0,No error)；启动后 CQI 返回 `7.92E+04,0,NaN...`，字段义待查手册 |
| CSI RI | `...CSI:RI:HISTogram?` | ◑ 启动后全 0 直方图（单层下秩数据稀/未累积） |
| UE RSRP / SINR / capability / UL 吞吐 | `...UEReport:* / CALL:UEINFO:* / ...UL...` | ❌ 超时(-113)，本 App 不支持 |

### 9.3 新增 backlog（offline 修）
- **attach 检测改用 `BSE:STATus?`**：实测 `OFF→ON→CONN` 可靠且即时；attach-dut 端点(`test_execution.py:225` `query_ue_capability`)用的 `CALL:UEINFO:CAPability?` 在 IRAT 上超时 → 会把真已附着 DUT 误报 `rrc_connected=False`。应改读 `BSE:STATus?`(CONN/IDLE/ON/OFF)。
- **构建 UXM cell-cycle 编排**：既然纯 SCPI（停→重设→重启→轮询 `BSE:STATus?`→测吞吐）已验证可用，应在驱动/commissioning 里做成正式 `configure_cell + activate + wait_attach(BSE:STATus==CONN) + measure` 流程，而非仅靠 GUI。
- **DL/SSB 功率命令修正**（已并入"配置捕获"chip）：验证 mnemonic 是 `:DL:POWer`(读 -46)/`:SSB:POWer:ADVertised`(读 0)，读写都 clean；早上 capture 脚本的 `:PHY:DL:POWer?` / `:SSB:POWer?` 是错命令（超时）。
- **`uxm_command_profiles.py` 过保守**：`CSI:CQI/RI`、`DL:POINta` 标 None/unsupported，但 live IRAT 实际响应。应重新探测后补 profile。
- **吞吐窗口/ BLER enable**：IRAT 缺 `TSTatistics:STARt`，需查手册找 IRAT 下重置/enable 统计的正确命令（或确认只能 GUI）。

### 9.4 现场 artifact（未提交，留代码修改用）
- `api-service/app/data/uxm_configs/caict_pre_teardown_2026-05-27.json` — 拆前 live 快照 + 恢复地图 + GUI-only 不可恢复项清单。
- `/tmp/uxm_live_state.py` `/tmp/uxm_probe_phy.py` `/tmp/uxm_snapshot.py` `/tmp/uxm_teardown_rebuild.py` `/tmp/uxm_measure.py` — 本次全部探测/演练脚本。

### 9.5 诊断洞察 — 客户端"超时" ↔ RDP "-113" 是同一现象的两面
> 解释了为什么"前序调试中 UXM RDP 不断提示 undefined header"，而我们客户端却没明显报错。

- 根因：`-113 Undefined header` = 命令 header 不在当前 Test App（LTE_NR_IRAT）命令树里（IRAT 是 5G_NR_Test 方言的子集）。
- 同一个未定义 header，两侧表现不同（今天实测对齐）：
  - 未定义**查询**（带 `?`）：仪器记 -113 + 输出缓冲空 → 客户端 **VI_ERROR_TMO 超时**，RDP 显示 **-113**。实测 `UEReport:RSRP:STATistics?`：客户端超时 / 队列 -113。
  - 未定义**写**（无 `?`）：仪器记 -113 + 无回包 → 客户端 **静默 resp=None/err=None 像成功**，RDP 显示 **-113**。实测 `BTHRoughput:...:TSTatistics:STARt`：客户端 resp=None/err=None / 队列 -113。
- 推论：早上"NOT capturable via SCPI（查询超时）"那批参数（SCS / PHY:DL:POWer / MIMO / 天线路由…）= RDP 上一条条 -113，同一件事的两面。
- 对修代码的意义：
  1. 客户端**不能只凭"没报错/超时"判断命令成功** —— 未定义写会被静默吞掉；要确认必须 gate `SYST:ERR?`。
  2. RDP 的 -113 流主要来自发了 IRAT 不存在的 header（错 mnemonic / `detect_profile()` 回退到 5G_NR_Test / 探测脚本），不是仪器故障。
  3. 错误队列是**全局共享** FIFO（后端 hislip2 + GUI + 任何 client）→ 任一来源的 -113 都进同一条 RDP 日志，所以看着"不断"。
  4. `get_ue_info()`(uxm_base_station.py:1531) 是 no-SCPI 桩，**不**产生 -113；`query_ue_capability()`(:1538) 只在 profile 回退到 5G_NR_Test（UE_* 非 None）时才发 `CALL:UEINFO` → -113。

---

## 10. 下午 (PM) — EMCenter + F64 驱动修复 + 暗室首测重现

> 下午主线：① EMCenter 开关 bring-up（blocked → offline）；② **现场修 F64 驱动根因（用户明确指示，override 铁律1）**；③ 用修好的驱动重现暗室首测。

### 10.1 EMCenter / AMS8947 开关 — blocked，已起 chip
真机在 `192.168.0.50`（非 DB 配的 `192.168.100.26`），但**裸 SCPI 服务不监听**（只开 22/111/863/6000）；手册证它是 **GPIB 传统仪器、控制经 EMQuest**，以太网 SCPI 端口在缺失的主手册 `399342`。`EtslSwitchDriver` 的 `Query/Write` 前缀 + 默认口 2001 + 无 REST 端点都待修。详见 backlog chip。

### 10.2 ⭐⭐ F64 驱动根因修复（现场改码，待正式 PR）
**根因 = 端口错**：驱动连 `5025`，但 **PROPSIM 固定 ATE 口是 `3334`**（User Ref §1.1.2.1 "Fixed TCP/IP port for PROPSIM is 3334"）。5025 上响应 desync + 文件加载报 -300。
- **已现场改**：`propsim_f64.py:285` `self.port` 强制 `3334`（原 `config.get("port",5025)`）。`read_termination='\n'` 本就有（:436），不是 bug。
- **验证**：切 real 后后端 SCPI 干净（快查询 1:1 不串位）；`CALC:FILT:FILE` 加载 3600M / `DIAG:SIMU:GO` / `CENT:CH` 全 `0,"No error"`；`CENT:CH? 1` 读回 3550；改参数（改中心频→读回→还原）全通。
- **待办（offline）**：① 正式 PR + roadmap 对齐（现场直接改的码）；② DB 里 channelEmulator 端点端口 5025→3334（否则 readiness 显示脱节）；③ 文件头注释（line 28-29 把 5025 写成"标准口"、3334 写成"备用"——反了）。

### 10.3 纠正早上记的 F64 -200 根因（§3 作废重写）
早上记的"加载 2x2 文件却循环 `CENT:CH 1..64` 通道数不匹配 → -200" **是错的**。真因：`CALC:FILT:FILE` 在 5025 上**从未成功加载过**（每次 `-300 corrupt/missing`，但驱动加载后没 gate `SYST:ERR?`、没发现）→ **无打开的 sim** → 之后每条 `CENT:CH` 报 `-200 "No simulation opened"`。`*OPC?=1` ≠ 成功（失败也回 1）。

### 10.4 ⭐⭐ 今天最关键的设计发现 — F64 输入参考 + crest factor
**操作员结论：能 attach、输入口变绿的关键 = 设对 F64 的「输入信号参考（平均电平 dBm）+ crest factor（dB）」。设对了 attach 就没问题。**
- 命令：`INP:LEV:AMP:CH <in>,<dBm>` + `INP:CRE:SET <in>,<dB>`；或 `INP:LEV:AUTOSET <in>,<t>`（一次自动测+设两者，`<in>=0`=全部输入；无信号报 -300 不改）。范围 `INP:LEV:AMP:LIM? <in>`（本机 input1 = `-23..0`）。实测 `INP:LEV:MEAS? <in>,<t>`。状态：stopped 态（ATE AN §2.4.4）。
- 没设 → 输入前端增益不对 → 输入口不绿 + DL 失真。
- **我们 `set_channel_model()` 流程缺了"加载模型后设输入参考"这一步** → 必须补。

### 10.5 后端 F64 SCPI 慢操作 desync（待修，限制了今天可靠设输入参考）
- 慢操作（`*OPC?` after `CALC:FILT:FILE`；`INP:LEV:MEAS?`/`AUTOSET`）的 query 在后端读超时 → 读空 + 迟到响应串入后续读（desync 级联）。根因：`scpi-command` 端点不把 `timeout_ms` 透传给 `driver._query`，用默认短超时。
- 驱动自己的 `set_channel_model()` 用 `VISA_TIMEOUT_FILE_LOAD` 长超时不受影响；裸 `scpi-command` 路径受影响。今天只能靠盲等 sleep 规避 `*OPC?`，仍间歇串位。

### 10.6 暗室首测重现 — 结果
- 链路：UXM（N78 @ 3550，ARFCN 636666）→ F64（3600M @ `CENT:CH 3550`，bypass）→ 探头 → DUT。
- **达成**：纯 SCPI 控 F64 加载 3600M + UXM 小区 ON + **DUT 稳定 `BSE:STATus=CONN` + DL live**（ProgressCount 持续涨）。SCPI 控制下链路/同步首次端到端通。
- **未达成**：DL **0% ACK 全 NACK**（BUTLER `STATIC 2` + CALIBRATION `STATIC 3` 都一样）= DUT 收得到/控制 OK，但 **PDSCH 数据全解错（DL 失真，不是太弱）**。
- 真因（操作员归因）：**输入参考 + crest 未设对**（见 10.4）+ 输入电平 `-17~-23 dBm` 临界（-23 低于 F64 下限）。设对就好。
- 旁注：3600M = **4 输入 MIMO OTA 模型**（`MODEL:INFO?=4,128,32`）；单输入+bypass 是否干净透传存疑（我一度怀疑模型，但操作员归因于输入参考）。3600M 设计 3600 vs UXM 3550，F64 输入须落在处理窗口内。

### 10.7 现场 artifact（未提交）
- `propsim_f64.py:285` 已改 port 3334。
- `/tmp/f64ctl.py`（干净直连 3334 加载/运行工具）、`/tmp/f64_*.py`、`/tmp/uxm_*.py`、`caict_pre_teardown_2026-05-27.json`（§9.4）。

### 10.8 当日 trip retro（简短）
- **目标**：Phase 5 完整 first-call。**实得**：上午 first-call（F64 GUI 直通，DL 100% ACK，非校准 dry-run）✓；下午把 F64 驱动根因（端口 3334）**修了 + 硬件验证**，SCPI 加载/运行/改参跑通，DUT 经 SCPI-F64 稳定 CONN。
- **drift**：下午绝大部分时间深挖 F64 SCPI（远超铁律3 单仪表 30min）。原因：**用户明确指示现场修 F64 驱动**（override 铁律1——根因已锁定 + 硬件在手值得当场验证）。属"用户决策的正当深挖"，非盲目偏移；但 F64 一条线吃掉整个下午。
- **教训**：① 输入参考 + crest factor 是 attach 关键（设计补漏，最大收获）；② 现场改驱动需用户拍板；③ 后端慢操作 desync 限制可靠控制，得修。
