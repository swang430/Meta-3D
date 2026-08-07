# Keysight UXM RF App 常用基站配置 SCPI 指令

> **适用应用**：S8714A UXM 5G RF Application（RF App，RA）
> **依据手册**：S8714A UXM RF Application Cellular SCPI Manual，Rev 3.5.20231103
> **内容范围**：以 5G NR 基站/小区配置为主，附常用 LTE 基础配置。
> **命令说明**：`<cell>` 通常替换为 `CELL1`、`CELL2`、`CELL3` 或 `CELL4`。

---

## 1. 使用约定

### 1.1 SCPI 长格式与短格式

SCPI 关键字中大写字母表示最短可用缩写。例如：

```scpi
BSE:CONFigure:NR5G:CELL1:OBANd N78
```

可缩写为：

```scpi
BSE:CONF:NR5G:CELL1:OBAN N78
```

为提高可读性，本文主要使用手册中的混合大小写格式。

### 1.2 设置与查询

参数类命令通常使用以下方式：

```scpi
BSE:CONFig:NR5G:CELL1:OBANd N78
BSE:CONFig:NR5G:CELL1:OBANd?
```

第一条用于设置，第二条用于查询。

### 1.3 建议的错误检查流程

关键配置后建议执行：

```scpi
*OPC?
SYSTem:ERRor?
```

- `*OPC?`：等待前序命令执行完成，完成后返回 `1`。
- `SYSTem:ERRor?`：弹出并返回错误队列中最早的一条错误。
- `*CLS`：清空当前 SCPI 会话的错误队列。

---

# 2. 系统模式与配置管理

## 2.1 设置 SA/NSA 模式

```scpi
SYSTem:MODE NSA|SA
```

示例：

```scpi
SYSTem:MODE SA
SYSTem:MODE?
```

- 默认值：`NSA`
- 修改该参数会触发一次系统 Full Preset。
- Full Preset 不会改变当前的 SA/NSA 模式。

---

## 2.2 系统完整预置

```scpi
SYSTem:PRESet:FULL
```

作用：

- 关闭各小区 RF；
- 将大部分配置恢复为默认值；
- 再开启各小区 RF。

以下配置不会被 Full Preset 清除：

- System Mode；
- Path Loss；
- SIM Card 等手册特别说明的非易失配置。

---

## 2.3 保存 RF App 配置

```scpi
SYSTem:CONFig:SAVE "<RF App配置文件路径>"
```

示例：

```scpi
SYSTem:CONFig:SAVE "C:\RA\Config\n78_sa_config"
```

保存内容包括 RF App 的链路配置和测量配置。

---

## 2.4 加载 RF App 配置

```scpi
SYSTem:CONFig:LOAD "<RF App配置文件路径>"
```

示例：

```scpi
SYSTem:CONFig:LOAD "C:\RA\Config\n78_sa_config"
*OPC?
SYSTem:ERRor?
```

执行加载时，RF App 会先关闭所有小区 RF，再加载指定配置。

---

# 3. 小区选择、状态与连接控制

## 3.1 选择当前 NR 小区

```scpi
BSE:SELected:CELL:NR CELL1|CELL2|CELL3|CELL4
```

示例：

```scpi
BSE:SELected:CELL:NR CELL1
BSE:SELected:CELL:NR?
```

该参数用于指定省略 `<cell>` 节点时所针对的 NR 小区。

---

## 3.2 NR 小区启用状态

```scpi
BSE:CONFig:NR5G:<cell>:ACTive[:STATe] OFF|ON|0|1
```

示例：

```scpi
BSE:CONFig:NR5G:CELL1:ACTive:STATe OFF
BSE:CONFig:NR5G:CELL1:ACTive:STATe ON
BSE:CONFig:NR5G:CELL1:ACTive:STATe?
```

说明：

- `OFF`：关闭该 NR 小区。
- `ON`：开启该 NR 小区。
- 关闭主小区 `CELL1` 时，其他 NR SCell 也会被关闭。
- 如果主小区已连接 UE，关闭主小区会触发 RRC 释放。

---

## 3.3 NR 小区 RF 输出开关

```scpi
BSE:CONFIG:NR5G:<cell>:RF OFF|ON|0|1
```

示例：

```scpi
BSE:CONFIG:NR5G:CELL1:RF OFF
BSE:CONFIG:NR5G:CELL1:RF ON
```

注意：该命令与 `ACTive:STATe` 不是同一个参数。

- `ACTive:STATe` 控制小区是否运行；
- `RF` 控制该小区的射频输出状态。

---

## 3.4 重启指定 NR 小区

```scpi
BSE:CONFIG:NR5G:<cell>:RESTart
```

示例：

```scpi
BSE:CONFIG:NR5G:CELL1:RESTart
```

如果该小区的 Cell State 为 ON，重启完成后小区会重新开启。

---

## 3.5 查询 NR 小区连接状态

```scpi
BSE:STATus:NR5G:<cell>?
```

示例：

```scpi
BSE:STATus:NR5G:CELL1?
```

可能返回：

| 返回值 | 含义 |
|---|---|
| `OFF` | 小区关闭 |
| `ON` | 小区开启，但未处于连接状态 |
| `IDLE` | 主小区处于空闲状态 |
| `CONNected` | 主小区或 PSCell 已连接 |
| `ACTivated` | SCell 已激活 |

---

## 3.6 主动连接 UE

```scpi
BSE:CONNect
```

- NSA 模式：RF App 通过 LTE Paging 发起连接。
- SA 模式：RF App 通过 SA Paging 发起连接。

---

## 3.7 主动断开 UE

```scpi
BSE:DISConnect
```

- NSA 模式：先解除 NR 聚合，再执行 LTE RRC Release。
- SA 模式：执行 SA RRC Release。

---

# 4. NR 频段、带宽与频点配置

## 4.1 设置 NR Band

```scpi
BSE:CONFig:NR5G:<cell>:OBANd <NR_BAND>
```

示例：

```scpi
BSE:CONFig:NR5G:CELL1:OBANd N78
BSE:CONFig:NR5G:CELL1:OBANd?
```

常见值：

```text
N1, N3, N5, N7, N8, N28, N38, N40, N41,
N48, N77, N78, N79, N257, N258, N260, N261
```

重要说明：

- RF App 的官方命令节点是 **`OBANd`**，不是 `BAND`。
- 默认值为 `N78`。
- `N29`、`N67`、`N75`、`N76` 为 SDL Band，不能配置为 `CELL1`。
- 该版本中，SA 模式不允许将 `CELL1` 配置为 FR2 Band。
- 除 `CELL1` 外的其他 NR 小区不能配置为 FR2 Band。

---

## 4.2 查询双工方式

```scpi
BSE:CONFig:NR5G:<cell>:DUPLex:MODE?
```

示例：

```scpi
BSE:CONFig:NR5G:CELL1:DUPLex:MODE?
```

返回值：

```text
FDD
TDD
SDL
```

双工方式由 Operating Band 自动派生，是只读参数。

---

## 4.3 设置下行载波带宽

```scpi
BSE:CONFig:NR5G:<cell>:DL:BW <BANDWIDTH>
```

示例：

```scpi
BSE:CONFig:NR5G:CELL1:DL:BW BW100
BSE:CONFig:NR5G:CELL1:DL:BW?
```

支持枚举：

```text
BW5, BW10, BW15, BW20, BW25, BW30, BW35,
BW40, BW45, BW50, BW60, BW70, BW80, BW90, BW100
```

说明：

- 实际可用值受 Band 和 Common SCS 限制。
- 如果当前 SCS 不支持目标带宽，RF App 可能自动切换到最接近的可用 SCS。
- n78 默认带宽为 `BW100`。

---

## 4.4 设置上行载波带宽

```scpi
BSE:CONFig:NR5G:<cell>:UL:BW <BANDWIDTH>
```

示例：

```scpi
BSE:CONFig:NR5G:CELL1:UL:BW BW100
BSE:CONFig:NR5G:CELL1:UL:BW?
```

说明：

- 通常随 DL Bandwidth 一起变化；
- 实际范围由 Band、DL Bandwidth 和 Common SCS 共同决定；
- SDL 小区不适用 UL Bandwidth。

---

## 4.5 设置 Common SCS

```scpi
BSE:CONFig:NR5G:<cell>:SUBCarrier:SPACing:COMMon MU0|MU1|MU3
```

示例：

```scpi
BSE:CONFig:NR5G:CELL1:SUBCarrier:SPACing:COMMon MU1
BSE:CONFig:NR5G:CELL1:SUBCarrier:SPACing:COMMon?
```

枚举与子载波间隔对应关系：

| 枚举值 | Common SCS |
|---|---:|
| `MU0` | 15 kHz |
| `MU1` | 30 kHz |
| `MU3` | 120 kHz |

手册给出的默认规则：

- FDD Band：通常为 `MU0`；
- SDL Band：通常为 `MU0`；
- FR1 TDD Band：通常为 `MU1`；
- n51：`MU0`；
- FR2 Band：`MU3`。

Common SCS 表示 DL/UL Initial BWP 的 SCS。

---

## 4.6 设置标准 Low/Mid/High 测试信道

```scpi
BSE:CONFig:NR5G:<cell>:TEST:CHANnel LOW|MID|HIGH
```

示例：

```scpi
BSE:CONFig:NR5G:CELL1:TEST:CHANnel MID
BSE:CONFig:NR5G:CELL1:TEST:CHANnel?
```

查询结果还可能为：

```text
CUSTom
```

注意：

- `CUSTom` 不能直接写入；
- 当手动设置的 DL/UL ARFCN 不对应 TS 38.508 定义的 Low、Mid、High 信道时，查询结果会自动显示为 `CUSTom`。

---

## 4.7 设置下行载波中心 NR-ARFCN

```scpi
BSE:CONFig:NR5G:<cell>:DL:ARFCN <INTEGER>
```

示例：

```scpi
BSE:CONFig:NR5G:CELL1:DL:ARFCN 633334
BSE:CONFig:NR5G:CELL1:DL:ARFCN?
```

说明：

- 手册总范围：`0`～`400000000`；
- 实际允许范围取决于 Band、带宽和 SCS；
- 输入值不在有效 Channel Raster 时，RF App 会向上取整到下一个有效 Raster；
- 手动改变 ARFCN 后，Test Channel 可能变成 `CUSTom`。

---

## 4.8 设置上行载波中心 NR-ARFCN

```scpi
BSE:CONFig:NR5G:<cell>:UL:ARFCN <INTEGER>
```

示例：

```scpi
BSE:CONFig:NR5G:CELL1:UL:ARFCN 633334
BSE:CONFig:NR5G:CELL1:UL:ARFCN?
```

说明：

- TDD Band 下，UL ARFCN 通常由 DL ARFCN 决定，用户不能单独修改；
- FDD Band 下可配置 UL ARFCN；
- SDL 小区不适用该参数。

---

## 4.9 查询下行中心频率

```scpi
BSE:CONFig:NR5G:<cell>:DL:FREQuency?
```

返回单位：Hz。

示例：

```scpi
BSE:CONFig:NR5G:CELL1:DL:FREQuency?
```

---

## 4.10 查询上行中心频率

```scpi
BSE:CONFig:NR5G:<cell>:UL:FREQuency?
```

返回单位：Hz。

---

## 4.11 查询 SSB ARFCN

```scpi
BSE:CONFig:NR5G:<cell>:SSB:ARFCn?
```

示例：

```scpi
BSE:CONFig:NR5G:CELL1:SSB:ARFCn?
```

说明：

- 该参数在手册中为只读结果；
- 返回 `-1` 表示当前没有可用 SSB；
- SSB ARFCN 由 Band、带宽、Common SCS、DL ARFCN 和 Test Channel 等参数共同决定。

---

## 4.12 配置上行 7.5 kHz Frequency Shift

```scpi
BSE:CONFig:NR5G:<cell>:UL:FQSHift OFF|ON|0|1
```

示例：

```scpi
BSE:CONFig:NR5G:CELL1:UL:FQSHift ON
```

适用于：

- 所有 FDD Band；
- n34、n38、n39、n40、n48、n90 等部分 TDD Band。

对于 n34、n38、n39、n40、n48，只有 15 kHz UL SCS 时适用。

---

# 5. NR 下行功率和上行功控

## 5.1 设置 Cell Power（/BW）

```scpi
BSE:CONFig:NR5G:<cell>:DL:POWer:CHANnel <DBM_PER_BW>
```

示例：

```scpi
BSE:CONFig:NR5G:CELL1:DL:POWer:CHANnel -30
BSE:CONFig:NR5G:CELL1:DL:POWer:CHANnel?
```

参数：

- 单位：dBm/BW；
- 范围：`-110`～`7`；
- 分辨率：0.01 dB；
- 默认值：`-46.85 dBm/BW`。

这是按整个载波带宽表示的 Cell Power。

---

## 5.2 设置 Cell Power（/SCS）

```scpi
BSE:CONFig:NR5G:<cell>:DL:POWer[:EPRE] <DBM_PER_SCS>
```

示例：

```scpi
BSE:CONFig:NR5G:CELL1:DL:POWer:EPRE -82
BSE:CONFig:NR5G:CELL1:DL:POWer:EPRE?
```

参数：

- 单位：dBm/SCS；
- 范围：`-135`～`-17`；
- 分辨率：0.01 dB；
- 默认值：`-82 dBm/SCS`。

`/BW` 与 `/SCS` 是联动参数。修改带宽或 SCS 时，RF App 会在保持单位带宽能量关系的前提下重新换算。

---

## 5.3 设置 Advertised SSB Power

```scpi
BSE:CONFig:NR5G:<cell>:SSB:POWer:ADVertised <INTEGER>
```

示例：

```scpi
BSE:CONFig:NR5G:CELL1:SSB:POWer:ADVertised -10
BSE:CONFig:NR5G:CELL1:SSB:POWer:ADVertised?
```

参数：

- 单位：dBm/SCS；
- 范围：`-60`～`50`；
- 默认值：`0`。

该参数是基站向 UE 广播/宣告的 SSB 功率值，不应直接等同于 UXM RF 端口的实际输出总功率。

---

## 5.4 自动 Expected Input Power

```scpi
BSE:CONFig:NR5G:<cell>:EIP:AUTO OFF|ON|0|1
```

示例：

```scpi
BSE:CONFig:NR5G:CELL1:EIP:AUTO ON
```

默认值：`ON`。

---

## 5.5 手动设置 Expected Input Power

先关闭自动 EIP：

```scpi
BSE:CONFig:NR5G:CELL1:EIP:AUTO OFF
```

再设置 EIP：

```scpi
BSE:CONFig:NR5G:CELL1:EIP:VALue -33
```

参数：

- 单位：dBm；
- 范围：`-60`～`30`；
- 默认值：`-33 dBm`。

---

## 5.6 设置上行闭环功控模式

```scpi
BSE:CONFig:NR5G:<cell>:UL:CLPControl:MODE <MODE>
```

支持模式：

| 模式 | 含义 |
|---|---|
| `TARGet` | 将最大功率端口控制到目标功率 |
| `TGTall` | 将所有端口总功率控制到目标功率 |
| `MANual` | 仅在手动发送 TPC 时调整 |
| `UP` | 持续发送 +1 dB TPC |
| `DOWN` | 持续发送 -1 dB TPC |

示例：

```scpi
BSE:CONFig:NR5G:CELL1:UL:CLPControl:MODE TARGet
```

---

## 5.7 设置上行目标功率

```scpi
BSE:CONFig:NR5G:<cell>:UL:CLPControl:TARGet[:POWer] <DBM>
```

示例：

```scpi
BSE:CONFig:NR5G:CELL1:UL:CLPControl:TARGet:POWer -20
```

参数：

- 单位：dBm；
- 范围：`-90`～`50`；
- 分辨率：0.1 dB；
- 仅在 `TARGet` 或 `TGTall` 模式下生效。

---

## 5.8 手动发送 TPC 命令

```scpi
BSE:CONFig:NR5G:<cell>:UL:CLPControl:MANual:SEND NM1|N1|N3
```

含义：

| 枚举值 | TPC 调整量 |
|---|---:|
| `NM1` | -1 dB |
| `N1` | +1 dB |
| `N3` | +3 dB |

示例：

```scpi
BSE:CONFig:NR5G:CELL1:UL:CLPControl:MODE MANual
BSE:CONFig:NR5G:CELL1:UL:CLPControl:MANual:SEND N1
```

---

# 6. NR MIMO、调度和资源分配

## 6.1 设置调度场景

```scpi
BSE:CONFig:NR5G:SCHeduling:SCENario RMC|FULL
```

示例：

```scpi
BSE:CONFig:NR5G:SCHeduling:SCENario RMC
```

- `RMC`：按照 TS 38.521 的 RMC 调度方式运行。
- `FULL`：允许配置完整的 TDD UL/DL Pattern，调度全部指定的 DL/UL 时隙和符号。
- FR2 不支持 `FULL`。

---

## 6.2 上行 RMC 快速配置

```scpi
BSE:CONFig:NR5G:<cell>:SCHeduling:UL:QCONfig <MODE>
```

常用模式：

| 模式 | 波形与调制 |
|---|---|
| `PITBpsk` | DFT-s-OFDM π/2-BPSK |
| `DQPSk` | DFT-s-OFDM QPSK |
| `DQAM16` | DFT-s-OFDM 16QAM |
| `DQAM64` | DFT-s-OFDM 64QAM |
| `DQAM256` | DFT-s-OFDM 256QAM |
| `CQPSk` | CP-OFDM QPSK |
| `CQAM16` | CP-OFDM 16QAM |
| `CQAM64` | CP-OFDM 64QAM |
| `CQAM256` | CP-OFDM 256QAM |

示例：

```scpi
BSE:CONFig:NR5G:CELL1:SCHeduling:UL:QCONfig CQAM64
```

仅适用于 `RMC` 调度场景。

---

## 6.3 下行 RMC 快速配置

```scpi
BSE:CONFig:NR5G:<cell>:SCHeduling:DL:QCONfig QPSK|QAM64|QAM256
```

示例：

```scpi
BSE:CONFig:NR5G:CELL1:SCHeduling:DL:QCONfig QAM256
```

仅适用于 `RMC` 调度场景。

---

## 6.4 设置 PUSCH 波形

```scpi
BSE:CONFig:NR5G:<cell>:SCHeduling:PUSCh:WAVeform DFTS|CP
```

含义：

- `DFTS`：DFT-s-OFDM；
- `CP`：CP-OFDM。

示例：

```scpi
BSE:CONFig:NR5G:CELL1:SCHeduling:PUSCh:WAVeform CP
```

---

## 6.5 设置上行 MCS Table

```scpi
BSE:CONFig:NR5G:<cell>:SCHeduling:UL:MCS:TABLe Q64|Q256|Q64Lse
```

示例：

```scpi
BSE:CONFig:NR5G:CELL1:SCHeduling:UL:MCS:TABLe Q256
```

---

## 6.6 设置上行 MCS Index

```scpi
BSE:CONFig:NR5G:<cell>:SCHeduling:UL:MCS:INDex <INTEGER>
```

参数：

- 范围：`0`～`28`；
- 默认值：`10`。

示例：

```scpi
BSE:CONFig:NR5G:CELL1:SCHeduling:UL:MCS:INDex 20
```

---

## 6.7 设置下行 MCS Table

```scpi
BSE:CONFig:NR5G:<cell>:SCHeduling:DL:MCS:TABLe Q64|Q256|Q64Lse
```

示例：

```scpi
BSE:CONFig:NR5G:CELL1:SCHeduling:DL:MCS:TABLe Q256
```

---

## 6.8 设置下行 MCS Index

```scpi
BSE:CONFig:NR5G:<cell>:SCHeduling:DL:MCS:INDex <INTEGER>
```

参数：

- 范围：`0`～`28`；
- 默认值：`24`。

示例：

```scpi
BSE:CONFig:NR5G:CELL1:SCHeduling:DL:MCS:INDex 24
```

---

## 6.9 设置上行 MIMO

```scpi
BSE:CONFig:NR5G:<cell>:UL:MIMO:CONFig N1X1|N2X2|N2X1
```

含义：

| 枚举值 | 含义 |
|---|---|
| `N1X1` | 1×1 |
| `N2X2` | 2×2 |
| `N2X1` | 2×1 Transparent TX Diversity |

示例：

```scpi
BSE:CONFig:NR5G:CELL1:UL:MIMO:CONFig N2X2
```

---

## 6.10 设置下行 MIMO

```scpi
BSE:CONFig:NR5G:<cell>:DL:MIMO:CONFig N1X1|N1X2|N1X4|N2X2|N4X4
```

示例：

```scpi
BSE:CONFig:NR5G:CELL1:DL:MIMO:CONFig N4X4
```

实际可配置的最大阶数受当前 HCCU Scenario 和硬件资源限制。

---

## 6.11 设置上行 RB Allocation Type

```scpi
BSE:CONFig:NR5G:<cell>:SCHeduling:UL:PRB:ALLocation:TYPE CONTiguous|NCONtiguous
```

示例：

```scpi
BSE:CONFig:NR5G:CELL1:SCHeduling:UL:PRB:ALLocation:TYPE CONTiguous
```

---

## 6.12 设置连续上行 RB 分配模式

```scpi
BSE:CONFig:NR5G:<cell>:SCHeduling:UL:PRB:CALLocation <MODE>
```

支持模式：

```text
CUSTom
REFSens
E1RBLeft
E1RBRight
IFULl
OFULl
I1RBLeft
I1RBRight
```

示例：

```scpi
BSE:CONFig:NR5G:CELL1:SCHeduling:UL:PRB:CALLocation OFULl
```

---

## 6.13 自定义上行 RB 起始位置和数量

先选择 `CUSTom`：

```scpi
BSE:CONFig:NR5G:CELL1:SCHeduling:UL:PRB:CALLocation CUSTom
```

设置起始 PRB：

```scpi
BSE:CONFig:NR5G:CELL1:SCHeduling:UL:PRB:CALLocation:STARt 0
```

设置 PRB 数量：

```scpi
BSE:CONFig:NR5G:CELL1:SCHeduling:UL:PRB:CALLocation:COUNt 100
```

理论范围：

- Start：`0`～`272`；
- Count：`1`～`273`。

实际上限由带宽、SCS、波形和起始位置共同决定。

---

## 6.14 设置下行 RB 分配

```scpi
BSE:CONFig:NR5G:<cell>:SCHeduling:DL:PRB:CALLocation FRB|CUSTom
```

- `FRB`：全 RB；
- `CUSTom`：自定义连续 RB。

自定义示例：

```scpi
BSE:CONFig:NR5G:CELL1:SCHeduling:DL:PRB:CALLocation CUSTom
BSE:CONFig:NR5G:CELL1:SCHeduling:DL:PRB:CALLocation:STARt 0
BSE:CONFig:NR5G:CELL1:SCHeduling:DL:PRB:CALLocation:COUNt 100
```

---

## 6.15 设置 UL 调度方式

```scpi
BSE:CONFig:NR5G:<cell>:UL:SCHedule ASLots|SSLot|HFRame
```

- `ASLots`：调度全部 RMC UL Slot；
- `SSLot`：只调度特定单 Slot；
- `HFRame`：按半帧方式调度特定 UL Slot。

---

## 6.16 设置 DL 调度方式

```scpi
BSE:CONFig:NR5G:<cell>:DL:SCHedule BRMC|CFORmat1|CFORmat3
```

- `BRMC`：基础 DL RMC；
- `CFORmat1`：强制 PUCCH Format 1 所需调度；
- `CFORmat3`：强制 PUCCH Format 3 所需调度。

---

# 7. NR TDD Pattern 配置

## 7.1 设置预定义 TDD UL/DL Pattern

```scpi
BSE:CONFig:NR5G:<cell>:SCHeduling:TDDPattern <PATTERN>
```

常见 Pattern：

```text
DC23MS5
CNDC33MS5
CNDC63MS2P5
CNDC71MS2P5
CNDC60MS2P5
CNDC10MS5
EUDC30MS2P5
JPDC50MS2P5
KRDC23MS2P5
USDC25MS5
CMCCN79V1
CMCCN79V2
CMCCN41
CTCUN78
RMCMU0
RMCMU1
TPUT8D1UV1
TPUT8D1UV2
TPUT3D6UV1
TPUT5D4UV1
TPUT7D2UV1
JP3D2U4DV1
FLEXIBLE
```

示例：

```scpi
BSE:CONFig:NR5G:CELL1:SCHeduling:TDDPattern CTCUN78
```

适用条件：

- Scheduling Scenario 为 `FULL`；
- Band 为 TDD；
- 适用于 FR1。

---

## 7.2 设置 Flexible TDD 配置

```scpi
BSE:CONFig:NR5G:<cell>:SCHeduling:TDDPattern:FLEXible MAXDl|MAXUl|ULDutycycle
```

示例：

```scpi
BSE:CONFig:NR5G:CELL1:SCHeduling:TDDPattern FLEXIBLE
BSE:CONFig:NR5G:CELL1:SCHeduling:TDDPattern:FLEXible MAXUl
```

仅在 TDD Pattern 选择 `FLEXIBLE` 时使用。

---

# 8. NR PRACH 常用配置

## 8.1 PRACH Configuration Index

```scpi
BSE:CONFig:NR5G:<cell>:PHY:PRACH:CONFig:INDex <INTEGER>
```

参数：

- 范围：`0`～`255`；
- 默认值：`160`。

示例：

```scpi
BSE:CONFig:NR5G:CELL1:PHY:PRACH:CONFig:INDex 160
```

实际合法值受 Band、调度场景和 TDD Pattern 限制。

---

## 8.2 MSG1-FDM

```scpi
BSE:CONFig:NR5G:<cell>:PHY:PRACH:MSG1:FDM ONE|TWO|FOUR|EIGHt
```

示例：

```scpi
BSE:CONFig:NR5G:CELL1:PHY:PRACH:MSG1:FDM FOUR
```

---

## 8.3 MSG1-SCS

```scpi
BSE:CONFig:NR5G:<cell>:PHY:PRACH:MSG1:SCS MU0|MU1
```

映射：

- `MU0`：15 kHz；
- `MU1`：30 kHz。

---

## 8.4 PRACH Preamble Received Target Power

```scpi
BSE:CONFig:NR5G:<cell>:PHY:PRACH:POWer:INITial <INTEGER>
```

参数：

- 单位：dBm；
- 范围：`-202`～`-60`；
- 默认值：`-118 dBm`。

示例：

```scpi
BSE:CONFig:NR5G:CELL1:PHY:PRACH:POWer:INITial -118
```

---

## 8.5 RACH Power Ramping Step

```scpi
BSE:CONFig:NR5G:<cell>:MAC:RACH:POWer:STEP DB0|DB2|DB4|DB6
```

示例：

```scpi
BSE:CONFig:NR5G:CELL1:MAC:RACH:POWer:STEP DB4
```

---

# 9. 多小区与载波聚合

## 9.1 NR Carrier Aggregation

```scpi
BSE:CAGGregation[:NR5G] "<DL_CELL_LIST>","<UL_CELL_LIST>"
```

NSA 示例，聚合 NR CELL1：

```scpi
BSE:CAGGregation:NR5G "CELL1","CELL1"
```

SA 示例，聚合 NR SCell CELL2：

```scpi
BSE:CAGGregation:NR5G "CELL2","CELL2"
```

解除所有 NR 聚合：

```scpi
BSE:CAGGregation:NR5G "NONE","NONE"
```

参数含义：

- 第一个字符串：需要在 DL 聚合的 Cell 列表；
- 第二个字符串：需要在 UL 聚合的 Cell 列表；
- 多个 Cell 用逗号分隔并置于同一字符串中。

---

## 9.2 Cell Transceiver Resource Type

```scpi
BSE:CONFig:NR5G:<cell>:TRX DLUL|DL
```

示例：

```scpi
BSE:CONFig:NR5G:CELL2:TRX DLUL
```

- `DLUL`：分配上下行资源；
- `DL`：仅分配下行资源；
- `CELL1` 固定为 `DLUL`。

---

## 9.3 一次应用多小区 Desired 配置

```scpi
BSE:CONFig:MCELl:QCONfig
```

该命令将各小区的 Desired 配置一次性应用到当前配置。若关键参数发生变化，RF App 可能自动断开 UE、关闭相关小区、应用配置并重新开启主小区。

---

# 10. Path Loss 常用命令

## 10.1 启用整体 Path Loss Correction

```scpi
SYSTem:PLOSs:ENABle OFF|ON|0|1
```

示例：

```scpi
SYSTem:PLOSs:ENABle ON
```

---

## 10.2 为 UXM-1 RF 端口添加修正点

```scpi
SYSTem:PLOSs:PORT1:ADD "<TYPE>,<FREQ_MHZ>,<GAIN_DB>,..."
```

示例：

```scpi
SYSTem:PLOSs:PORT1:ADD "IN,1000,20,OUT,3500,10,INOut,3700,-3"
```

Correction Type：

```text
IN
OUT
INOut
```

每条记录由以下三项组成：

```text
Correction Type, Correction Frequency (MHz), Amplitude Gain (dB)
```

---

## 10.3 查询端口修正表

查询全部类型：

```scpi
SYSTem:PLOSs:PORT1:FETCh?
```

查询指定类型：

```scpi
SYSTem:PLOSs:PORT1:IN:FETCh?
SYSTem:PLOSs:PORT1:OUT:FETCh?
SYSTem:PLOSs:PORT1:INOut:FETCh?
```

---

## 10.4 清除端口修正表

清除指定类型：

```scpi
SYSTem:PLOSs:PORT1:OUT:CLEar
```

清除端口全部修正记录：

```scpi
SYSTem:PLOSs:PORT1:CLEar
```

---

# 11. LTE 常用基础配置

## 11.1 LTE 小区状态

```scpi
BSE:CONFig:LTE:<cell>:ACTive[:STATe] OFF|ON|0|1
```

查询连接状态：

```scpi
BSE:STATus:LTE:<cell>?
```

---

## 11.2 LTE Band

```scpi
BSE:CONFig:LTE:<cell>:OBANd <LTE_BAND>
```

示例：

```scpi
BSE:CONFig:LTE:CELL1:OBANd B3
```

RF App 中 LTE Band 同样使用 `OBANd` 节点。

---

## 11.3 LTE 带宽

```scpi
BSE:CONFig:LTE:<cell>:BW BW1P4|BW3|BW5|BW10|BW15|BW20
```

示例：

```scpi
BSE:CONFig:LTE:CELL1:BW BW20
```

---

## 11.4 LTE DL EARFCN

```scpi
BSE:CONFig:LTE:<cell>[:DL]:EARFcn <INTEGER>
```

示例：

```scpi
BSE:CONFig:LTE:CELL1:DL:EARFcn 1575
```

---

## 11.5 LTE Cell Power（/BW）

```scpi
BSE:CONFig:LTE:<cell>[:DL]:POWer:CHANnel <DBM>
```

示例：

```scpi
BSE:CONFig:LTE:CELL1:DL:POWer:CHANnel -50
```

---

## 11.6 LTE DL MIMO

```scpi
BSE:CONFig:LTE:<cell>:DL:MIMO:CONFig N1X1|N1X2|N1X4|N2X2|N4X4
```

示例：

```scpi
BSE:CONFig:LTE:CELL1:DL:MIMO:CONFig N2X2
```

---

## 11.7 LTE DL/UL MCS

下行：

```scpi
BSE:CONFig:LTE:<cell>:SCHeduling:DL:MCS <0..28>
```

上行：

```scpi
BSE:CONFig:LTE:<cell>:SCHeduling:UL:MCS <0..28>
```

---

# 12. n78 SA 基础配置示例

以下示例用于展示典型命令顺序，具体 ARFCN、功率、MIMO 和调度参数应按实际测试要求配置。

```scpi
*CLS

SYSTem:MODE SA
*OPC?
SYSTem:ERRor?

BSE:CONFig:NR5G:CELL1:ACTive:STATe OFF
BSE:CONFIG:NR5G:CELL1:RF OFF

BSE:CONFig:NR5G:CELL1:OBANd N78
BSE:CONFig:NR5G:CELL1:DL:BW BW100
BSE:CONFig:NR5G:CELL1:UL:BW BW100
BSE:CONFig:NR5G:CELL1:SUBCarrier:SPACing:COMMon MU1

BSE:CONFig:NR5G:CELL1:TEST:CHANnel MID

BSE:CONFig:NR5G:CELL1:DL:MIMO:CONFig N4X4
BSE:CONFig:NR5G:CELL1:UL:MIMO:CONFig N1X1

BSE:CONFig:NR5G:CELL1:DL:POWer:CHANnel -30
BSE:CONFig:NR5G:CELL1:SSB:POWer:ADVertised -10

BSE:CONFig:NR5G:SCHeduling:SCENario RMC
BSE:CONFig:NR5G:CELL1:SCHeduling:DL:QCONfig QAM256
BSE:CONFig:NR5G:CELL1:SCHeduling:UL:QCONfig CQAM64

BSE:CONFig:NR5G:CELL1:ACTive:STATe ON
BSE:CONFIG:NR5G:CELL1:RF ON

*OPC?
SYSTem:ERRor?

BSE:STATus:NR5G:CELL1?
BSE:CONFig:NR5G:CELL1:OBANd?
BSE:CONFig:NR5G:CELL1:SUBCarrier:SPACing:COMMon?
BSE:CONFig:NR5G:CELL1:DL:ARFCN?
BSE:CONFig:NR5G:CELL1:SSB:ARFCn?
```

---

# 13. 自动化配置时的关键注意事项

## 13.1 Band 命令节点是 OBANd

RF App 官方手册中的命令为：

```scpi
BSE:CONFig:NR5G:CELL1:OBANd N78
```

不是：

```scpi
BSE:CONFig:NR5G:CELL1:BAND N78
```

---

## 13.2 Common SCS 不是直接写 15、30 或 120

RF App 使用：

```text
MU0 = 15 kHz
MU1 = 30 kHz
MU3 = 120 kHz
```

例如：

```scpi
BSE:CONFig:NR5G:CELL1:SUBCarrier:SPACing:COMMon MU1
```

---

## 13.3 Test Channel 与 ARFCN 会互相影响

- 设置 `LOW`、`MID`、`HIGH` 会自动计算相应的 DL/UL ARFCN；
- 手动设置 ARFCN 后，Test Channel 可能自动变为 `CUSTom`；
- `CUSTom` 不能直接设置。

---

## 13.4 修改配置可能自动触发重配置

根据 SA/NSA 模式、小区状态和参数类型，RF App 可能自动执行：

- RRC Reconfiguration with Sync；
- RRC Connection Reconfiguration；
- SCell 去聚合与重新聚合；
- Cell RF Off/On；
- UE Disconnect/Reconnect。

因此，自动化程序不应假设每条配置命令只是简单改写变量。

---

## 13.5 每个关键步骤后检查错误

推荐封装：

```text
发送配置命令
→ *OPC?
→ SYSTem:ERRor?
→ 判断是否为无错误
```

尤其应检查：

- Band；
- Bandwidth；
- Common SCS；
- DL/UL ARFCN；
- MIMO；
- TDD Pattern；
- PRACH Configuration Index；
- RB Allocation；
- HCCU Scenario 资源限制。

---

## 13.6 RF 输出功率安全

改变以下参数前，应确认测试链路总衰减、UXM 端口功率范围及 DUT 最大允许输入功率：

```scpi
BSE:CONFig:NR5G:<cell>:DL:POWer:CHANnel
BSE:CONFig:NR5G:<cell>:DL:POWer:EPRE
BSE:CONFig:LTE:<cell>:DL:POWer:CHANnel
```
