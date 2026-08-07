# Keysight UXM 基站参数配置：SCPI 指令与建议值

> 更新时间：2026-07-13
> 适用设备：Keysight UXM E7515B
> 当前现场应用：C8714000A RF Application Framework 3.5.134.12281（`IRAT_LITE`）
> 当前现场 VISA 端点：`TCPIP0::201.20.2.1::hislip2::INSTR`
> 说明：仪表 IP 必须由 GUI“仪器资源配置”保存，软件不得在驱动中写死 IP。

## 1. 软件必须先区分 RF App 与 Test App

UXM 的 RF App 和 Test App 使用不同 SCPI 命令树，不能混发。GUI 中的“UXM 应用类型”应保存到：

```json
{
  "uxm_app_mode": "rf_app"
}
```

可选值：

| GUI 选项 | 保存值 | 软件使用的命令 Profile |
|---|---|---|
| RF App | `rf_app` | `IRAT_LITE`，主要使用 `BSE:CONFig:NR5G:*` |
| Test App | `test_app` | `5G_NR_Test`，使用原 `CONFig:NR5G:*` |

连接后可读取实际应用名称：

```scpi
SYSTem:APPLication:NAME?
```

当前 RF App 返回：

```text
IRAT_LITE
```

如果仪表返回的应用名称与 GUI 选择不一致，软件应告警并停止自动配置，避免向错误的 App 反复发送命令并触发 `-113 Undefined header`。

## 2. UE Attach 成功的现场验证基线

以下参数已在真实 UXM 上读回，UE 已成功 Attach：

| 参数 | 建议/验证值 | 读回结果 | 说明 |
|---|---:|---:|---|
| NR Cell | `CELL1` | `CELL1` | RF App 主小区 |
| Band | `N66` | `N66` | FDD Band |
| Duplex | 自动派生 | `FDD` | 只读，不要强制写入 |
| Common SCS | `MU0` | `MU0` | 15 kHz，适用于当前 n66 配置 |
| DL ARFCN | `429000` | `429000` | 现场成功值 |
| UL ARFCN | 建议由仪表派生 | `349000` | 如无特殊测试要求，不强制覆盖 |
| DL Bandwidth | `BW10` | `BW10` | 10 MHz |
| UL Bandwidth | `BW10` | `BW10` | 10 MHz |
| Cell Power | `-12 dBm/BW` | `-12 dBm/BW` | 使用 `:CHANnel` 命令 |
| EPRE | 联动换算 | `-39.95 dBm/SCS` | 不要与 Cell Power 混淆 |
| Cell Status | 期望 `CONNected` | `CONN` | UE 已成功连接 |

这组值可作为当前实验室 n66 UE Attach 的初始基线。更换 DUT、射频路径或衰减配置后，功率值仍需重新评估。

## 3. RF App 参数与 SCPI 指令

以下指令适用于当前 `IRAT_LITE` RF App。

### 3.1 小区开关与状态

```scpi
BSE:CONFig:NR5G:CELL1:ACTive:STATe 0
BSE:CONFig:NR5G:CELL1:ACTive:STATe 1
BSE:CONFig:NR5G:CELL1:ACTive:STATe?
BSE:STATus:NR5G:CELL1?
```

状态查询可能返回 `OFF`、`ON`、`IDLE`、`CONN`/`CONNected` 或 `ACTivated`。

### 3.2 Band

```scpi
BSE:CONFig:NR5G:CELL1:OBANd N66
BSE:CONFig:NR5G:CELL1:OBANd?
```

RF App 必须使用 `OBANd`，不要使用 `BAND`。

### 3.3 双工方式

```scpi
BSE:CONFig:NR5G:CELL1:DUPLex:MODE?
```

双工方式由 Band 自动派生。n66 的当前读回值为 `FDD`，建议只查询、不写入。

### 3.4 Common SCS

```scpi
BSE:CONFig:NR5G:CELL1:SUBCarrier:SPACing:COMMon MU0
BSE:CONFig:NR5G:CELL1:SUBCarrier:SPACing:COMMon?
```

枚举映射：

| RF App 枚举 | SCS |
|---|---:|
| `MU0` | 15 kHz |
| `MU1` | 30 kHz |
| `MU3` | 120 kHz |

软件参数到 RF App 枚举的映射应为：`15 → MU0`、`30 → MU1`、`120 → MU3`。

### 3.5 DL/UL 带宽

```scpi
BSE:CONFig:NR5G:CELL1:DL:BW BW10
BSE:CONFig:NR5G:CELL1:UL:BW BW10
BSE:CONFig:NR5G:CELL1:DL:BW?
BSE:CONFig:NR5G:CELL1:UL:BW?
```

RF App 使用 `BW10` 这种枚举形式，不是裸数字 `10`。Band、带宽和 SCS 之间存在约束，修改 Band 后仪表可能自动调整带宽。

### 3.6 DL/UL ARFCN

```scpi
BSE:CONFig:NR5G:CELL1:DL:ARFCN 429000
BSE:CONFig:NR5G:CELL1:DL:ARFCN?
BSE:CONFig:NR5G:CELL1:UL:ARFCN?
```

当前 n66 配置的 UL ARFCN 由仪表派生为 `349000`。只有测试规范明确要求时才建议单独写 UL ARFCN。

### 3.7 Cell Power（dBm/BW）

```scpi
BSE:CONFig:NR5G:CELL1:DL:POWer:CHANnel -12
BSE:CONFig:NR5G:CELL1:DL:POWer:CHANnel?
```

- 单位：dBm/BW。
- 当前 UE Attach 成功值：`-12 dBm/BW`。
- 手册范围：`-110`～`7 dBm/BW`，但实际可用范围还受硬件、端口和当前配置约束。

### 3.8 EPRE（dBm/SCS）

```scpi
BSE:CONFig:NR5G:CELL1:DL:POWer:EPRE <value>
BSE:CONFig:NR5G:CELL1:DL:POWer:EPRE?
```

- 单位：dBm/SCS。
- 手册范围：`-135`～`-17 dBm/SCS`。
- `/BW` 与 `/SCS` 是联动参数。当前 `-12 dBm/BW` 对应读回约 `-39.95 dBm/SCS`。
- 用户要求的是 Cell Power 时，应写 `:CHANnel`，不能误写 `:EPRE`。

### 3.9 错误与完成状态

```scpi
*CLS
*OPC?
SYSTem:ERRor?
```

无错误返回：

```text
0,"No error"
```

`SYSTem:ERRor?` 会弹出错误队列中的一条记录。软件应循环读取，直到返回 0；不能只记录日志后继续运行。

## 4. 推荐的 RF App 自动配置顺序

推荐先关闭小区，按依赖顺序配置，再读回验证并打开小区：

```scpi
*CLS

BSE:CONFig:NR5G:CELL1:ACTive:STATe 0
SYSTem:ERRor?

BSE:CONFig:NR5G:CELL1:OBANd N66
SYSTem:ERRor?

BSE:CONFig:NR5G:CELL1:SUBCarrier:SPACing:COMMon MU0
SYSTem:ERRor?

BSE:CONFig:NR5G:CELL1:DL:BW BW10
BSE:CONFig:NR5G:CELL1:UL:BW BW10
SYSTem:ERRor?

BSE:CONFig:NR5G:CELL1:DL:ARFCN 429000
SYSTem:ERRor?

BSE:CONFig:NR5G:CELL1:DL:POWer:CHANnel -12
SYSTem:ERRor?

BSE:CONFig:NR5G:CELL1:OBANd?
BSE:CONFig:NR5G:CELL1:DUPLex:MODE?
BSE:CONFig:NR5G:CELL1:SUBCarrier:SPACing:COMMon?
BSE:CONFig:NR5G:CELL1:DL:BW?
BSE:CONFig:NR5G:CELL1:UL:BW?
BSE:CONFig:NR5G:CELL1:DL:ARFCN?
BSE:CONFig:NR5G:CELL1:UL:ARFCN?
BSE:CONFig:NR5G:CELL1:DL:POWer:CHANnel?

BSE:CONFig:NR5G:CELL1:ACTive:STATe 1
SYSTem:ERRor?
BSE:STATus:NR5G:CELL1?
```

自动化程序应在任一关键设置返回非零错误时：

1. 停止后续配置；
2. 保持小区关闭，避免带着部分配置发射；
3. 返回失败的命令、错误码和仪表消息；
4. 不要自动重试未确认支持的替代 SCPI Header。

## 5. Test App 原指令必须独立保留

以下是原 `5G_NR_Test` Profile 的主要配置指令。仅当 GUI 选择 Test App，且仪表实际运行对应 Test App 时使用。

| 参数 | Test App SCPI |
|---|---|
| Band | `CONFig:NR5G:<cell>:BAND <band>` |
| DL ARFCN | `CONFig:NR5G:<cell>:DL:ARFCN <arfcn>` |
| DL Bandwidth | `CONFig:NR5G:<cell>:DL:BW <mhz>` |
| UL Bandwidth | `CONFig:NR5G:<cell>:UL:BW <mhz>` |
| SCS | `CONFig:NR5G:<cell>:SCS <khz>` |
| Duplex | `CONFig:NR5G:<cell>:DUPLex <mode>` |
| DL Power | `CONFig:NR5G:<cell>:PHY:DL:POWer <dbm>` |
| Cell OFF | `CONFig:NR5G:<cell>:ACTive:STATe OFF` |
| Cell ON | `CONFig:NR5G:<cell>:ACTive:STATe ON` |
| Cell State | `CONFig:NR5G:<cell>:ACTive:STATe?` |

Test App 常用主小区为 `CELL0`；当前 RF App 主小区为 `CELL1`。软件不能把 RF App 的 `CELL1`、`OBANd`、`MU0/MU1/MU3` 编码规则覆盖到 Test App Profile 中。

## 6. 软件参数模型建议

建议后端使用与仪表品牌无关的业务参数，再由 Profile 完成 SCPI 转换：

```json
{
  "cell_id": "CELL1",
  "band": "N66",
  "duplex": "FDD",
  "scs_khz": 15,
  "bandwidth_mhz": 10,
  "dl_arfcn": 429000,
  "dl_power_dbm_per_bw": -12,
  "app_mode": "rf_app"
}
```

RF App 转换规则：

| 业务参数 | RF App 写入值 |
|---|---|
| `band=N66` | `OBANd N66` |
| `scs_khz=15` | `...COMMon MU0` |
| `bandwidth_mhz=10` | `DL:BW BW10`、`UL:BW BW10` |
| `dl_arfcn=429000` | `DL:ARFCN 429000` |
| `dl_power_dbm_per_bw=-12` | `DL:POWer:CHANnel -12` |

应分别建模 `dl_power_dbm_per_bw` 和 `dl_power_dbm_per_scs`，不要共用一个含义模糊的 `dl_power_dbm` 字段。

## 7. 避免 Undefined Header 的规则

1. RF App 与 Test App 使用独立 Profile，不覆盖彼此的指令常量。
2. GUI 明确选择 App 类型，HAL 重载后锁定对应 Profile。
3. 未在当前 App 验证的命令设为“不支持”，不得周期性试探。
4. 当前 `IRAT_LITE` 不应自动轮询旧 Test App/C870 的吞吐量命令：

   ```scpi
   BSE:MEASure:NR5G:CELL1:BTHRoughput:DL:TSTatistics:JSON?
   ```

5. 自动监控只能轮询当前 Profile 明确支持的查询。
6. 每条写命令后检查 `SYSTem:ERRor?`，防止配置失败但软件仍显示成功。

## 8. 功率安全建议

- `-12 dBm/BW` 是本次链路中 UE Attach 成功的仪表设置，不代表所有 DUT 和射频路径都安全。
- 提高功率前必须确认 UXM 输出端口、线缆/信道仿真器/功放增益、暗室路径损耗及 DUT 最大允许输入功率。
- 软件应设置可配置的功率上限，并在超过实验室安全阈值时要求人工确认。
- 修改 Band、带宽或 SCS 后必须重新读回 `/BW` 与 EPRE，因为仪表会联动换算。

## 9. 本次现场验证摘要

真实仪表：

```text
Keysight Technologies,C8714000A RF Application Framework,
MY62226143,3.5.134.12281
```

最终读回：

```text
Application : IRAT_LITE
Band        : N66
Duplex      : FDD
Common SCS  : MU0 (15 kHz)
DL ARFCN    : 429000
UL ARFCN    : 349000
DL BW       : BW10
UL BW       : BW10
Cell Power  : -12 dBm/BW
EPRE        : -39.95 dBm/SCS
Cell Status : CONN
SCPI Error  : 0,"No error"
```

该配置已由现场确认 UE 成功 Attach。

## 10. RF App 吞吐量只允许主动诊断调用

`IRAT_LITE` 已确认支持独立的 `BTPut` 与 `TMONitor` 命令树，但它们只注册在
RF App 专用 Profile 的主动诊断接口中，不恢复后台周期轮询：

```scpi
BSE:MEASure:NR5G:BTPut:STATe ON
BSE:MEASure:NR5G:CELL1:BTPut:DL?
BSE:METRics:TMONitor:OTA:DL:NR?
BSE:MEASure:NR5G:BTPut:STATe OFF
```

软件入口为诊断序列 `uxm_rf_app_max_dl_throughput`。它保持本节记录的 N66、
429000、BW10、-12 dBm/BW 和 UE Attach 状态，不调用基站重配置或小区重启命令。
旧 Test App 的 `BTHRoughput:...:TSTatistics:JSON?` 仍仅属于 TEST APP Profile。
