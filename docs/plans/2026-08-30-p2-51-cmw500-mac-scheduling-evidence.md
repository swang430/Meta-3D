# P2-51 取证清单 — CMW500 LTE MAC/调度配置（非现场半）

> 底本：R&S CMW290/500 LTE UE Firmware Applications User Manual **1173.9628.02 ─ 41**
> （PDF 原件 `Instrument_API_Doc/R&S CMW500/CMW_LTE_UE_UserManual_V4-0-250_en_41 (2).pdf`，
> manifest `manual_sources` 已登记；页码 = 正文 "User Manual 1173.9628.02 ─ 41" 旁的印刷页码，
> **PDF 页码与印刷页码一致**，表格部分已用 PDF 原件逐页目视复核 pp.70-72 / pp.77-79）。
>
> 本清单是 P2-51 非现场半的取证产物；每条 SCPI 的最终判据以现场真机复验为准
> （roadmap P2-51 条目明示：真机复验不由本地测试替代）。

## 0. 查询形的手册通则（本清单所有「查询形」的共同出处）

印刷 p.15，§1.2.4 Command reference 原文：

> "Most commands have a command form and a query form. Exceptions are marked by
> 'Setting only', 'Query only' or 'Event'."

即：命令参考里**未标** Setting only / Query only / Event 的命令，设置形与查询形并存。
下表逐条核对过标记（全部无 "Setting only" 标记）。查询响应的**字面形态**（枚举缩写、
CSV 字段数）手册未逐条给出 → 驱动按「⚠ 推断 + 错误队列核对 + 严格白名单解析」处理
（同 `rs_fsva.py` 形态），真机复验时核对。

## 1. 命令取证表（命令 → 页码 → 设置/查询 → 选件 → 固件 → 值域）

| # | 命令 | 印刷页 | 设置形 | 查询形 | 选件依赖 | 最低固件 | 值域 / 备注 |
|---|------|--------|--------|--------|----------|----------|-------------|
| 1 | `CONFigure:LTE:SIGN<i>:CONNection[:PCC]:STYPe <Type>[,<CQIMode>]` | p.743 | ✅ | ✅（p.15 通则，无 Setting only 标记） | **RMC 无选件**；UDCH/UDTT/SPS/CQI-TTIB 需 KS510；CQI 非 TTIB 需 KS510/KS512；EMA/EMCS 需 KS590 | V3.0.10 | Type ∈ RMC\|UDCHannels\|UDTTibased\|CQI\|SPS\|EMAMode\|EMCSched；\*RST=RMC。**正式路径只用 RMC**，其余类型保持 diagnostic/fail-loud |
| 2 | `CONFigure:LTE:SIGN<i>:CONNection[:PCC]:RMC:DL<s> <NumberRB>,<Modulation>,<TransBlockSizeIdx>` | pp.799-800 | ✅ | ✅（p.15 通则） | DL 256-QAM 需 KS504/KS554、1024-QAM 需 KS505/KS555；**QPSK/Q16/Q64 无选件** | V3.0.20 | `<s>`∈1..2；NumberRB ∈ ZERO\|N1..N100；Modulation ∈ QPSK\|Q16\|Q64\|Q256\|Q1024；TBS ∈ ZERO\|T1..T37（KEEP 选兼容值）。合法组合见表 2-38/2-39（§2.2.19.4） |
| 3 | `CONFigure:LTE:SIGN<i>:CONNection[:PCC]:RMC:UL <NumberRB>,<Modulation>,<TransBlockSizeIdx>` | pp.800-801 | ✅ | ✅（p.15 通则） | UL 64-QAM/256-QAM 需 KS504/KS554；**QPSK/Q16 无选件** | V3.0.20 | 值域同上（UL 无 Q1024）。合法组合见表 2-33（§2.2.19.1） |
| 4 | `CONFigure:LTE:SIGN<i>:CONNection[:PCC]:RMC:RBPosition:DL<s> <Position>` | pp.801-802 | ✅ | ✅（p.15 通则） | 无 | V3.2.50 | Position ∈ LOW\|HIGH\|P5\|P10\|P23\|P35\|P48；"Set the same value for both streams"（p.801）。满配时 LOW=HIGH，本驱动固定发 LOW |
| 5 | `CONFigure:LTE:SIGN<i>:CONNection[:PCC]:RMC:RBPosition:UL <Position>` | p.802 | ✅ | ✅（p.15 通则） | 无 | V3.0.20 | Position ∈ LOW\|HIGH\|MID\|P0..P99（长枚举）；本驱动固定发 LOW |
| 6 | `CONFigure:LTE:SIGN<i>:CONNection[:PCC]:DLEQual <Enable>` | p.794 | ✅ | ✅（p.15 通则） | 无 | V3.2.60 | OFF\|ON；ON = "settings for DL stream 1 are applied to all DL streams"。本驱动发 ON，使 2 流 MIMO 下 DL1 配置覆盖全部流 |
| 7 | `CONFigure:LTE:SIGN<i>:CONNection:DLPadding <Value>` | p.742 | ✅ | ✅（p.15 通则） | 无 | V1.0.15.20 | OFF\|ON，\*RST=ON。**Extended BLER 的手册明示前置**（见 §3 下） |
| 8 | `CONFigure:LTE:SIGN<i>:CONNection[:PCC]:MCLuster:UL <Multicluster>` | pp.743-744 | ⛔ 不写（选件） | ✅ 仅查询（p.15 通则） | **KS510/KS512**（multi-cluster 特性本身选件门控） | V3.5.20 | OFF=contiguous（资源分配 type 0）。本驱动**只查询**确认 OFF——RMC:UL 写的是 contiguous 通道，multi-cluster ON 时该前提破。查询被拒时 fail-closed（真机复验项） |
| 9 | `CONFigure:LTE:SIGN<i>:CONNection:HARQ:DL:ENABle <Enable>` | pp.783-784 | ⛔ 不写（选件） | ✅ 仅探测查询 | **KS510（无 CA）/KS512（CA）** | V3.0.50 | OFF\|ON，\*RST=OFF。选件门控 → 本片不驱动，仅探测回读记档（rs_fsva「⚠ 推断+错误队列核对」形态）；探测失败只记档不致命 |
| 10 | `CONFigure:LTE:SIGN<i>:CONNection:HARQ:DL:NHT <Number>` | p.784 | ⛔ 不写（选件） | —（不使用） | 手册只在 ENABle 挂 KS510/KS512 Options；NHT 条目无 Options 行——「组整体门控」为 ⚠ 推断（保守不驱动） | V3.0.50 | Range 2..4，\*RST=2。`harq_max_trans` 的 LTE 对应命令**存在但选件门控** → 本片保持 diagnostic，不下发 |
| 11 | `CONFigure:LTE:SIGN<i>:EBLer:SFRames <Subframes>` | p.953 | 存在（本片不发） | ✅（p.15 通则） | 无 | V3.0.30 | Range 100..400E+3，\*RST=10E+3。`stat_count` 的对应命令。⚠ 内审 F1 纠偏：p.953「只影响 trace 长度」限定 **confidence** 模式（SCONdition CLEVel）；正式窗口是 **continuous**（SCONdition NONE，P1-73B），该模式下 SFRames = 每周期统计子帧数（§3.3.1 p.940 示例明示 "1000 subframes per measurement cycle"）。命令归窗口层所有、当前全仓未驱动——**统计基继承仪器旧状态是已登记缺口**（Discovered：窗口层驱动 SFRames），不在 MAC 配置层越权下发 |
| 12 | `CONFigure:LTE:SIGN<i>:CONNection[:PCC]:RMC:VERSion:DL<s> <Version>` | p.803 | 存在（本片不发） | ✅（p.15 通则） | 无 | V3.2.70 | 0..1，仅用于区分 **TDD** 多天线下同参数的歧义 RMC（R.11/R.11-1、R.30/R.30-1）。本片正式路径 FDD-only（见 §4），TDD fail-loud → 不发 |

## 2. 值选型取证（表格，已用 PDF 原件目视复核）

### 2.1 DL 满配 RMC（表 2-38 "DL RMCs for FDD, multiple TX antennas"，印刷 p.78，§2.2.19.4）

§2.2.19 开篇（p.69）：RMC = "Reference measurement channels (RMC) as defined in 3GPP
TS 36.521"。§2.2.19.4（p.77）适用 TM 2 到 TM 6（覆盖本驱动 TM3 2x2 正式路径）。
本驱动取**每带宽满 RB 行的最高无选件调制**（DL 256/1024-QAM 需选件，见 §1 表第 2 行）：

| 带宽 | token | 满配 RB | 选用调制 | TBS index | 表内同行其它组合（未选用） |
|------|-------|---------|----------|-----------|--------------------------|
| 1.4 MHz | B014 | N6 | QPSK | T4 | — |
| 3 MHz | B030 | N15 | QPSK | T5 | — |
| 5 MHz | B050 | N25 | Q16 | T12 | QPSK/T5 |
| 10 MHz | B100 | N50 | Q64 | T18 | QPSK/T5、Q16/T13（另有 40RB Q16/T13 部分分配行） |
| 15 MHz | B150 | N75 | QPSK | T5 | — |
| 20 MHz | B200 | N100 | Q16 | T13 | — |

（TDD 对应表 2-39 pp.78-79 也已核：5MHz 25RB 仅 16-QAM/12；10MHz 50RB 16-QAM/13 带
Version R.11/R.11-1；20MHz 100RB 16-QAM/13 带 Version R.30/R.30-1 —— 本片 TDD fail-loud，
留作后续片；见 §4。）

### 2.2 UL 满配 RMC（表 2-33 "UL RMCs for FDD and TDD, contiguous"，印刷 pp.70-71，§2.2.19.1）

UL 取 QPSK（UL 64/256-QAM 需 KS504/KS554）；TBS Idx 取表中 QPSK 列对应行：

| 带宽 | 满配 RB | 调制 | TBS index（QPSK 列） |
|------|---------|------|----------------------|
| 1.4 MHz | N6 | QPSK | T6 |
| 3 MHz | N15 | QPSK | T6（表注 "6 for 3 MHz, else 5"） |
| 5 MHz | N25 | QPSK | T5 |
| 10 MHz | N50 | QPSK | T6 |
| 15 MHz | N75 | QPSK | T3 |
| 20 MHz | N100 | QPSK | T2 |

RB 起始位置通则（p.72 "Position of first RB, contiguous allocation"）：
"Two start positions are always allowed: Low … High …"。满配时 LOW 恒合法。

## 3. Extended BLER 前置（任务取证项 3）

- §3.1 "Performing a BLER measurement"（p.921）原文：
  "To measure the downlink BLER, you must set up a connection and transfer data via the
  downlink. **In test mode, activate downlink padding** to transfer data."
- §3.3.1 "Configuring a BLER measurement"（p.940）手册自身编程示例的**第一步**即
  `CONFigure:LTE:SIGN:CONNection:DLPadding ON`。
- → `DLPadding ON` 纳入本驱动 MAC 配置的必要组（§1 表第 7 行）。
- p.922 另有两条**建议**（非命令前置，本片记录不实现）：BLER 评估期间建议关闭邻区测量、
  建议不启用 "Reduced PDCCH"。→ 进 Discovered 候选。
- 既有 EBLer 窗口配置（TOUT/REPetition/SCONdition，pp.950-953）由 P1-73B
  `measure_base_station_window` 拥有，本片不重复驱动（防 UXM 曾踩的双路径漂移）。

## 4. 取证不到 / 不可如实翻译的维度（保持 diagnostic，逐条 reason）

SPI 入参（`configure_mac_throughput_test` 契约，NR 形态）逐个对账：

| SPI 入参 | 处置 | 依据 |
|----------|------|------|
| `mimo_layers` | **仅 =2 接受**（满配 DL 行取自表 2-38 多天线专用〔TM2-6〕；单天线表 2-37 同带宽行是另一组调制/TBS——内审 F2 收窄）；**1/4 → fail-loud** | pp.799-800 后缀值域 `<s>` 1..2；§2.2.19.4 无 4 流 RMC 表 |
| `mcs`（NR MCS 索引） | **no_equivalent** —— LTE RMC 由 #RB/调制/TBS 三元组描述（§2.2.19 p.69），手册无「MCS 索引」命令；不发明 36.213 映射 | p.69、pp.799-800 |
| `rb_alloc` | 仅接受 "ALL"（满配，§2 表）；其它值 fail-loud 不猜 | 表 2-33/2-38 |
| `enable_amc=True` | **fail-loud** —— AMC 对应 CQI 调度类型（"follow wideband CQI"），STYPe=CQI 非 TTIB 需 KS510/KS512 选件，选件依赖类型不进正式路径 | p.743 Options |
| `tdd_pattern` / `tdd_period`（NR slot 形态） | FDD：**no_equivalent**（FDD 无子帧配比维度）；**TDD duplex：整个配置 fail-loud** —— LTE TDD 配比是 `CONFigure:LTE:SIGN<i>:CELL[:PCC]:ULDL <0..6>`（p.687）+ 特殊子帧配置，NR "DDDSU…" 字符串不可如实翻译成 3GPP 36.211 配比编号，TestCase 契约也缺 LTE TDD 配比字段 → 平台缺口进 Discovered | p.687；p.803（TDD 歧义 RMC 还需 VERSion） |
| `harq_max_trans` | **skipped（选件依赖）** —— 对应 `HARQ:DL:NHT`（p.784）但 DL HARQ 配置组需 KS510/KS512；不下发、receipt 写明选件依赖；`HARQ:DL:ENABle` 仅探测回读记档 | pp.783-784 Options |
| `harq_processes` | **no_equivalent** —— LTE DL HARQ 进程数无手册命令（3GPP 36.213 固定，FDD=8）；手册 HARQ 组（pp.783-785）只有 ENABle/NHT/RVCSequence/UDSequence | pp.783-785 |
| `stat_count` | **no_equivalent（本路径）** —— 对应 `EBLer:SFRames`（p.953）且 continuous 模式下即统计基（p.953 的「只影响 trace 长度」限定 confidence 模式）；命令归窗口层所有、当前未驱动 = 已登记缺口（Discovered），不在 MAC 层越权下发 | p.953 / §3.3.1 p.940 |
| `scs_khz` | **no_equivalent** —— LTE 子载波间隔固定 15 kHz，无命令；manifest 已声明 `subcarrier_spacing_khz` not_applicable | 全手册无 LTE SCS 配置命令 |
| `csi_rs_ports` | **no_equivalent** —— NR 概念；本驱动 LTE 正式路径 TM3 2x2（CSI-RS 属 TM9/TM10 域，本片不涉） | manifest 既有 not_applicable 声明 |

## 5. 回读可用性判定（任务取证项 4）

「可回读」= 手册有查询形（p.15 通则 + 无 Setting only 标记）**且**本驱动实发查询并
严格比对。逐字段：

| 配置维度 | 回读 | 方式 |
|----------|------|------|
| 调度类型（STYPe） | ✅ | `…STYPe?`，首 CSV 字段须为 `RMC`（响应字面形态 ⚠ 推断，真机复验） |
| DL RMC（RB/调制/TBS） | ✅ | `…RMC:DL1?`（2 层时另查 `…RMC:DL2?` 验证 DLEQual 耦合生效），3 字段严格比对 |
| UL RMC | ✅ | `…RMC:UL?` 3 字段严格比对 |
| RB 位置 DL/UL | ✅ | `…RBPosition:DL1?` / `…RBPosition:UL?` == LOW |
| DL 流耦合（DLEQual） | ✅ | `…DLEQual?` == ON |
| DL MAC padding | ✅ | `…DLPadding?` == ON |
| UL contiguous 前提 | ✅（仅查询） | `…MCLuster:UL?` == OFF；读到 ON 或读不到 → fail-closed |
| DL HARQ 状态 | ⚠ 仅探测记档 | `…HARQ:DL:ENABle?`（KS510 选件域）；失败不致命，值仅入 receipt reason |
| TDD 配比 / NR MCS / HARQ 进程数 / stat_count / SCS / CSI-RS | ❌ unavailable | 见 §4 各 reason；不从 UXM 方言、请求值或旧状态补真 |

## 6. 组序与门（实现对照）

写序（每组后 `*OPC?` + `SYSTem:ERRor:ALL?` 独立验错，任何组被拒记名进 `rejected`）：

1. 前置：`ensure_safe_idle`（Cell OFF 确认，沿用既有）→ 丢弃残留错误队列（归属隔离）
   → 固件 ≥ V3.5.20（本清单所用命令最高最低固件，MCLuster:UL 探测；与代码 MAC_CFG_MIN_FIRMWARE 一致）→ 活体查询 duplex（TDD → fail-loud）
   与带宽 token（查不到/不在 §2 表 → fail-loud，不用缓存值）。
2. `STYPe RMC` → 回读。
3. `MCLuster:UL?` 探测（≠OFF → rejected）。
4. `DLEQual ON` → 回读。
5. `RMC:DL1 <N,mod,TBS>` + `RBPosition:DL1 LOW` → 回读 DL1（2 层再回读 DL2 验证耦合）。
6. `RMC:UL <N,QPSK,TBS>` + `RBPosition:UL LOW` → 回读。
7. `DLPadding ON` → 回读。
8. `HARQ:DL:ENABle?` 探测记档（不门控）。

全程 `capture_scpi_exchanges`；产 `BaseStationApplyReceipt(operation="mac_throughput_config")`
（逐字段 requested/applied/status/exchange_ids），挂在 `MacThroughputConfigResult.receipt`。

## 7. 真机复验清单（现场半，本地测试不可替代）

- [ ] 各查询形响应的字面形态（枚举缩写大小写、STYPe 响应是否带 CQIMode 第二字段）。
- [ ] `MCLuster:UL?` 在无 KS510 机器上是否可查询（本片 fail-closed，复验后可放宽）。
- [ ] `HARQ:DL:ENABle?` 探测在无选件机器上的错误行为。
- [ ] RMC 组合在真机上的接受性（写后错误队列 + 回读一致）。
- [ ] `DLPadding ON` 与 attach 的交互（手册 p.742：padding 可能影响部分 UE attach —— 本驱动在
      attach 前写 ON，若现场 UE attach 失败需按 p.742 复核）。

## 8. Discovered 候选（本片枚举出、不做）

- LTE TDD 正式路径缺口：TestCase 契约无 LTE TDD 配比字段；驱动未实现 `CELL[:PCC]:ULDL`
  （p.687）+ 特殊子帧 + `RMC:VERSion:DL<s>`（p.803）。当前 TDD duplex 下 MAC 配置 fail-loud。
- BLER 建议项未实现：邻区测量关闭、Reduced PDCCH 不启用（p.922，建议非前置）。
- `measure.py` L1483-1485 注释「CMW 尚无手册支撑的同类配置」在本片后过时（任务书明令
  不改 MEASURE/执行器，留收口时同步）。
- `MacThroughputConfigResult` 定义在 `uxm_base_station.py`，CMW 驱动跨厂商 import；
  vendor-neutral 归位（挪 `base_station.py`）留 triage。
