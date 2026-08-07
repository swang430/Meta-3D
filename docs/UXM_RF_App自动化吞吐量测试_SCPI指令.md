# Keysight UXM RF App 自动化吞吐量测试 SCPI 指令

> **适用应用**：S8714A UXM 5G RF Application（RF App / RA）
> **依据手册**：S8714A UXM RF Application Cellular SCPI Manual，Rev 3.5.20231103
> **适用场景**：5G NR UE 已完成 Attach，准备通过 SCPI 自动执行下行、上行 OTA 吞吐量及 BLER 测试。
> **默认示例小区**：`CELL1`

---

# 0. 已打通的软件最大 DL 吞吐控制闭环

本节是当前 Meta-3D 软件在真实 UXM RF App（`IRAT_LITE`）上实际使用并完成
30 秒现场验收的命令集合。后续章节还包括 UL、IP 吞吐量、调度参数等手册参考
内容；这些参考内容不代表当前第一版 DL 诊断序列会自动写入对应配置。

当前诊断序列只临时控制以下项目：

- DL MAC Padding；
- BTPut State；
- BTPut Continuous；
- BTPut Length；
- BTPut 和 TMONitor 统计复位。

诊断序列不会修改 Band、ARFCN、带宽、Cell Power、Scheduling Scenario、MCS、
RB、MIMO 或小区开关，也不会重启小区。

## 0.1 实际使用的 SCPI 指令清单

| 阶段 | SCPI 指令 | 类型 | 软件用途 |
|---|---|---|---|
| 清理错误 | `SYSTem:ERRor?` | 查询 | 读取并保存测试前已有错误；测试过程中用于逐条命令校验 |
| 清空状态 | `*CLS` | 写入 | 清除仪表状态寄存器和错误队列 |
| 仪表识别 | `*IDN?` | 查询 | 保存仪表型号、序列号和版本 |
| App 校验 | `SYSTem:APPLication:NAME?` | 查询 | 必须返回 `IRAT_LITE`，否则拒绝发送 RF App 吞吐命令 |
| UE 状态 | `BSE:STATus:NR5G:CELL1?` | 查询 | 启动前必须为 `CONN`/`CONNected`，结束后再次确认 |
| Band 快照 | `BSE:CONFig:NR5G:CELL1:OBANd?` | 查询 | 只读保存当前频段 |
| ARFCN 快照 | `BSE:CONFig:NR5G:CELL1:DL:ARFCN?` | 查询 | 只读保存当前下行频点 |
| DL BW 快照 | `BSE:CONFig:NR5G:CELL1:DL:BW?` | 查询 | 只读保存当前下行带宽 |
| UL BW 快照 | `BSE:CONFig:NR5G:CELL1:UL:BW?` | 查询 | 只读保存当前上行带宽 |
| 功率快照 | `BSE:CONFig:NR5G:CELL1:DL:POWer:CHANnel?` | 查询 | 只读保存当前 Cell Power，单位 dBm/BW |
| Padding 原值 | `BSE:CONFig:NR5G:CELL1:SCHeduling:DL:PADDing:STATe?` | 查询 | 保存原值，结束时按原值恢复 |
| BTPut 状态 | `BSE:MEASure:NR5G:BTPut:STATe?` | 查询 | 保存原值并确认没有接管其他正在运行的测量 |
| 连续模式原值 | `BSE:MEASure:NR5G:BTPut:CONTinuous:ALL?` | 查询 | 保存原值，结束时恢复 |
| 测量长度原值 | `BSE:MEASure:NR5G:BTPut:LENGth:ALL?` | 查询 | 保存原值，结束时恢复 |
| 停止旧测量 | `BSE:MEASure:NR5G:BTPut:STATe OFF` | 写入 | 在配置本次测量前确保 BTPut 停止 |
| 开启 DL Padding | `BSE:CONFig:NR5G:CELL1:SCHeduling:DL:PADDing:STATe ON` | 条件写入 | 仅当原值为 OFF 时写入 |
| 开启连续窗口 | `BSE:MEASure:NR5G:BTPut:CONTinuous:ALL ON` | 写入 | 一个 BTPut 窗口结束后自动进入下一窗口 |
| 设置窗口长度 | `BSE:MEASure:NR5G:BTPut:LENGth:ALL 200` | 写入 | 当前软件默认 200 个有效 DL Slot |
| 清除 BTPut | `BSE:MEASure:NR5G:BTPut:RESet` | 写入 | 清除旧 BLER/吞吐结果 |
| 清除实时统计 | `BSE:METRics:RESet` | 写入 | 清除旧 TMONitor Current/Peak/Average/Transferred |
| 启动测量 | `BSE:MEASure:NR5G:BTPut:STATe ON` | 写入 | 启动 DL BTPut 窗口测量 |
| 读取 BTPut | `BSE:MEASure:NR5G:CELL1:BTPut:DL?` | 周期查询 | 读取 9 字段 DL 吞吐量、BLER 和计数 |
| 读取 TMONitor | `BSE:METRics:TMONitor:OTA:DL:NR?` | 周期查询 | 读取 4 字段实时 NR DL OTA 吞吐量 |
| 停止测量 | `BSE:MEASure:NR5G:BTPut:STATe OFF` | 写入 | 放在清理流程中，正常结束、异常、取消或超时都会执行 |
| 恢复长度 | `BSE:MEASure:NR5G:BTPut:LENGth:ALL <原值>` | 写入 | 恢复启动前 Length |
| 恢复连续模式 | `BSE:MEASure:NR5G:BTPut:CONTinuous:ALL <原值>` | 写入 | 恢复启动前 Continuous |
| 恢复 Padding | `BSE:CONFig:NR5G:CELL1:SCHeduling:DL:PADDing:STATe OFF` | 条件写入 | 仅当软件曾把原 OFF 改为 ON 时执行 |

所有写命令和结果查询后都立即执行一次：

```scpi
SYSTem:ERRor?
```

期望返回：

```text
0,"No error"
```

任一命令产生 SCPI 错误都会保留原始错误并将控制流程判为失败；软件不会继续用
其他未知命令反复重试。

## 0.2 实际启动、采样和停止顺序

以下为当前软件使用的顺序模板。`<原值>` 来自启动前查询；每条命令后的错误队列
检查未在代码块中重复展开。

```scpi
*CLS
*IDN?
SYSTem:APPLication:NAME?
BSE:STATus:NR5G:CELL1?
BSE:CONFig:NR5G:CELL1:OBANd?
BSE:CONFig:NR5G:CELL1:DL:ARFCN?
BSE:CONFig:NR5G:CELL1:DL:BW?
BSE:CONFig:NR5G:CELL1:UL:BW?
BSE:CONFig:NR5G:CELL1:DL:POWer:CHANnel?
BSE:CONFig:NR5G:CELL1:SCHeduling:DL:PADDing:STATe?
BSE:MEASure:NR5G:BTPut:STATe?
BSE:MEASure:NR5G:BTPut:CONTinuous:ALL?
BSE:MEASure:NR5G:BTPut:LENGth:ALL?
BSE:MEASure:NR5G:BTPut:STATe OFF
BSE:CONFig:NR5G:CELL1:SCHeduling:DL:PADDing:STATe ON
BSE:MEASure:NR5G:BTPut:CONTinuous:ALL ON
BSE:MEASure:NR5G:BTPut:LENGth:ALL 200
BSE:MEASure:NR5G:BTPut:RESet
BSE:METRics:RESet
BSE:MEASure:NR5G:BTPut:STATe ON
BSE:MEASure:NR5G:BTPut:STATe?
BSE:MEASure:NR5G:CELL1:BTPut:DL?
BSE:METRics:TMONitor:OTA:DL:NR?
BSE:MEASure:NR5G:BTPut:STATe OFF
BSE:MEASure:NR5G:BTPut:LENGth:ALL <原值>
BSE:MEASure:NR5G:BTPut:CONTinuous:ALL <原值>
BSE:CONFig:NR5G:CELL1:SCHeduling:DL:PADDing:STATe OFF
BSE:STATus:NR5G:CELL1?
BSE:MEASure:NR5G:BTPut:STATe?
SYSTem:ERRor?
```

其中 DL Padding 的 ON/OFF 命令是条件命令：如果启动前已经为 ON，则启动时不
重复写入，结束时也保持 ON。软件如果发现 BTPut 启动前已经处于 ON，会拒绝接管
该测量，避免破坏其他任务。

## 0.3 BTPut 与 TMONitor 的样本合并规则

每个采样周期依次读取：

```scpi
BSE:MEASure:NR5G:CELL1:BTPut:DL?
BSE:METRics:TMONitor:OTA:DL:NR?
```

- BTPut 索引 7（第 8 个字段）为有效值时，使用它作为 DL Mbps，并使用索引 6
  （第 7 个字段）作为真实 DL BLER；
- 连续模式的新窗口尚未完成时，BTPut 可能返回 `NaN`。此时使用 TMONitor 的
  `Current` 作为真实 DL Mbps，样本来源记为 `TMONITOR`；
- TMONitor 的四字段响应没有 BLER，因此 TMONitor 样本的 BLER 必须保存为
  `null`/`–`，不能复制上一条 BLER，也不能伪造为 0；
- 如果两条命令都没有有效吞吐量，该采样记为无效。全程没有任何有效样本时，
  控制流程失败。

本测试不设置性能门限。低吞吐或高 BLER（包括超过 60%）只记录，不导致控制流程
失败。

---

# 1. 测试方法概览

RF App 中与吞吐量测试相关的统计主要分为两类。

## 1.1 BLER/Throughput 窗口测量：`BTPut`

用于按照设定的测量长度统计：

- PDSCH BLER；
- PUSCH BLER；
- 下行平均吞吐量；
- 上行平均吞吐量；
- ACK、NACK、DTX 等计数。

核心命令树：

```scpi
BSE:MEASure:NR5G:BTPut...
```

适合：

- 灵敏度测试；
- 不同功率点吞吐量测试；
- BLER 曲线测试；
- 固定统计窗口的性能测试；
- 自动生成每个测试点的稳定结果。

## 1.2 实时吞吐量统计：`TMONitor`

用于持续查询：

- Current：当前统计周期平均吞吐量；
- Peak：峰值吞吐量；
- Average：自上次复位以来的累计平均吞吐量；
- Transferred：累计传输比特数。

核心命令树：

```scpi
BSE:METRics:TMONitor...
```

适合：

- 实时监控吞吐量变化；
- 每秒轮询并绘制吞吐量曲线；
- 长时间稳定性测试；
- SA/NSA 总吞吐量监控。

---

# 2. 自动化测试前的状态确认

## 2.1 查询系统模式

```scpi
SYSTem:MODE?
```

可能返回：

```text
SA
NSA
```

系统模式会影响吞吐量统计范围：

- SA：只有 NR；
- NSA：可能同时包含 LTE 和 NR。

---

## 2.2 查询 NR 小区连接状态

```scpi
BSE:STATus:NR5G:CELL1?
```

可能返回：

| 返回值 | 含义 |
|---|---|
| `OFF` | 小区关闭 |
| `ON` | 小区开启，但尚未连接 |
| `IDLE` | 主小区已驻留，但当前没有 RRC 连接 |
| `CONNected` | 主小区或 PSCell 已连接 |
| `ACTivated` | NR SCell 已激活 |

执行 `BTPut` 测量时，`CELL1` 应处于：

```text
CONNected
```

手册明确说明，NR BLER/Throughput 结果只有在以下条件同时满足时才会更新：

1. `CELL1` 的 Connection Status 为 `CONNected`；
2. NR BLER/Throughput Measurement State 为 `ON`。

---

## 2.3 UE 处于 IDLE 时主动发起连接

```scpi
BSE:CONNect
```

- SA 模式：RF App 发送 SA Paging；
- NSA 模式：RF App 发送 LTE Paging。

执行后再次查询：

```scpi
BSE:STATus:NR5G:CELL1?
```

---

## 2.4 NSA 模式查询 LTE 锚点状态

```scpi
BSE:STATus:LTE:CELL1?
```

NSA 场景中，LTE `CELL1` 通常应处于：

```text
CONNected
```

---

# 3. 配置空口数据调度

## 3.1 为什么要开启 MAC Padding

仅仅启动吞吐量统计，不代表 RF App 一定会持续产生下行或上行数据。

开启 MAC Padding 后：

- DL Padding：网络持续向 UE 调度下行 MAC 填充数据；
- UL Padding：UE 按照网络调度持续发送上行 MAC 填充数据。

因此，即使没有 iperf、FTP 或其他真实 IP 业务，也可以测试：

- PDSCH/PUSCH 空口吞吐量；
- BLER；
- 无线链路承载能力。

注意：

> MAC Padding 产生的是空口 MAC 层测试负载。它可以产生 OTA 吞吐量，但不一定产生 IP 吞吐量。

---

## 3.2 配置 NR 调度场景

```scpi
BSE:CONFig:NR5G:SCHeduling:SCENario RMC
```

查询：

```scpi
BSE:CONFig:NR5G:SCHeduling:SCENario?
```

支持：

```text
RMC
FULL
```

- `RMC`：按照 3GPP TS 38.521 的 RMC 方式调度；
- `FULL`：调度完整配置的 DL/UL Slot 和 Symbol。

对一般吞吐量测试，建议优先使用：

```text
RMC
```

注意：已连接状态下改变 Scheduling Scenario 可能触发 RRC Reconfiguration with Sync。

---

## 3.3 开启下行 MAC Padding

```scpi
BSE:CONFig:NR5G:CELL1:SCHeduling:DL:PADDing:STATe ON
```

查询：

```scpi
BSE:CONFig:NR5G:CELL1:SCHeduling:DL:PADDing:STATe?
```

关闭：

```scpi
BSE:CONFig:NR5G:CELL1:SCHeduling:DL:PADDing:STATe OFF
```

---

## 3.4 开启上行 MAC Padding

```scpi
BSE:CONFig:NR5G:CELL1:SCHeduling:UL:PADDing:STATe ON
```

查询：

```scpi
BSE:CONFig:NR5G:CELL1:SCHeduling:UL:PADDing:STATe?
```

关闭：

```scpi
BSE:CONFig:NR5G:CELL1:SCHeduling:UL:PADDing:STATe OFF
```

注意：

- SDL 小区不适用 UL Padding；
- 某些 PUCCH 测量配置可能自动关闭 UL Padding；
- `FULL` Scheduling Scenario 会自动开启所有 NR 小区的 UL Padding；
- 自动化脚本应在启动吞吐量测量前再次查询 Padding 状态。

---

# 4. 可选：配置高吞吐量调度参数

如果当前 UE 已经采用目标 MCS、MIMO 和 RB 配置，可以跳过本节，避免已连接状态下触发额外 RRC 重配置。

## 4.1 下行 RMC 快速配置

```scpi
BSE:CONFig:NR5G:CELL1:SCHeduling:DL:QCONfig QAM256
```

可选值：

```text
QPSK
QAM64
QAM256
```

说明：

- 该命令会联动配置相关下行 RMC 参数；
- FR2 不支持 `QAM256`；
- 在已连接状态执行时可能触发 RRC Reconfiguration。

---

## 4.2 上行 RMC 快速配置

例如 CP-OFDM 64QAM：

```scpi
BSE:CONFig:NR5G:CELL1:SCHeduling:UL:QCONfig CQAM64
```

常用值：

| 枚举 | 含义 |
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

---

## 4.3 使用全部下行 RB

```scpi
BSE:CONFig:NR5G:CELL1:SCHeduling:DL:PRB:CALLocation FRB
```

查询：

```scpi
BSE:CONFig:NR5G:CELL1:SCHeduling:DL:PRB:CALLocation?
```

- `FRB`：Full RB；
- `CUSTom`：自定义连续 RB。

---

## 4.4 使用上行 Outer-Full RB

```scpi
BSE:CONFig:NR5G:CELL1:SCHeduling:UL:PRB:CALLocation OFULl
```

查询：

```scpi
BSE:CONFig:NR5G:CELL1:SCHeduling:UL:PRB:CALLocation?
```

常见取值：

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

---

## 4.5 设置下行 MCS Table 和 MCS Index

```scpi
BSE:CONFig:NR5G:CELL1:SCHeduling:DL:MCS:TABLe Q256
BSE:CONFig:NR5G:CELL1:SCHeduling:DL:MCS:INDex 27
```

查询：

```scpi
BSE:CONFig:NR5G:CELL1:SCHeduling:DL:MCS:TABLe?
BSE:CONFig:NR5G:CELL1:SCHeduling:DL:MCS:INDex?
```

MCS Table 可选：

```text
Q64
Q256
Q64Lse
```

MCS Index 范围：

```text
0 ... 28
```

并非所有 MCS Table 都支持全部 Index。

---

## 4.6 设置上行 MCS Table 和 MCS Index

```scpi
BSE:CONFig:NR5G:CELL1:SCHeduling:UL:MCS:TABLe Q64
BSE:CONFig:NR5G:CELL1:SCHeduling:UL:MCS:INDex 20
```

查询：

```scpi
BSE:CONFig:NR5G:CELL1:SCHeduling:UL:MCS:TABLe?
BSE:CONFig:NR5G:CELL1:SCHeduling:UL:MCS:INDex?
```

---

## 4.7 配置所有下行和上行 RMC Slot

下行：

```scpi
BSE:CONFig:NR5G:CELL1:DL:SCHedule BRMC
```

上行：

```scpi
BSE:CONFig:NR5G:CELL1:UL:SCHedule ASLots
```

含义：

- `BRMC`：调度 Basic RMC 下行 Slot；
- `ASLots`：调度全部 RMC 上行 Slot。

---

# 5. 配置 NR BLER/Throughput 窗口测量

## 5.1 停止已有测量

```scpi
BSE:MEASure:NR5G:BTPut:STATe OFF
```

查询：

```scpi
BSE:MEASure:NR5G:BTPut:STATe?
```

参数范围：

```text
OFF
ON
0
1
```

默认值：

```text
OFF
```

---

## 5.2 配置单次或连续测量

### 连续测量

```scpi
BSE:MEASure:NR5G:BTPut:CONTinuous:ALL ON
```

### 单次测量

```scpi
BSE:MEASure:NR5G:BTPut:CONTinuous:ALL OFF
```

查询：

```scpi
BSE:MEASure:NR5G:BTPut:CONTinuous:ALL?
```

说明：

- `ON`：达到一次测量窗口后，自动开始下一轮；
- `OFF`：完成一个测量窗口后停止；
- 默认值为 `ON`；
- 测量运行期间修改该参数会重启当前测量。

自动功率扫描时，建议使用单次模式：

```scpi
BSE:MEASure:NR5G:BTPut:CONTinuous:ALL OFF
```

长时间稳定性测试时，建议使用连续模式：

```scpi
BSE:MEASure:NR5G:BTPut:CONTinuous:ALL ON
```

---

## 5.3 设置测量长度

```scpi
BSE:MEASure:NR5G:BTPut:LENGth:ALL 2000
```

查询：

```scpi
BSE:MEASure:NR5G:BTPut:LENGth:ALL?
```

参数定义：

| 项目 | 数值 |
|---|---:|
| 单位 | DL Slot |
| 范围 | 200～360000 |
| 步长 | 200 |
| 默认值 | 360000 |

注意：

- 输入值会向上取整到最接近的 200 的整数倍；
- TDD 中的 UL Slot 不计入测量长度；
- UXM 没有向 UE 发送数据的 DL Slot 也不计入；
- 测量长度不是固定的毫秒数。

例如：

```scpi
BSE:MEASure:NR5G:BTPut:LENGth:ALL 2000
```

表示累计 2000 个有效 DL Slot 后形成一次测量结果。

---

## 5.4 清除旧 BLER/Throughput 结果

```scpi
BSE:MEASure:NR5G:BTPut:RESet
```

该命令会：

1. 清除全部 NR BLER/Throughput 结果；
2. 停止当前测量；
3. 如果处于 Continuous 模式，则自动重新开始测量。

为避免 Reset 自动重启带来的流程歧义，推荐顺序为：

```scpi
BSE:MEASure:NR5G:BTPut:STATe OFF
BSE:MEASure:NR5G:BTPut:RESet
BSE:MEASure:NR5G:BTPut:STATe ON
```

---

## 5.5 启动测量

```scpi
BSE:MEASure:NR5G:BTPut:STATe ON
```

启动后检查：

```scpi
BSE:MEASure:NR5G:BTPut:STATe?
SYSTem:ERRor?
```

---

# 6. 查询下行 BLER 和吞吐量

## 6.1 查询命令

```scpi
BSE:MEASure:NR5G:CELL1:BTPut:DL?
```

## 6.2 返回字段顺序

返回值为逗号分隔字符串，共 9 个字段：

| 索引 | 字段 | 含义 |
|---:|---|---|
| 0 | Progress Count | 已发送给 UE 的 DL Transport Block 数 |
| 1 | DL ACK Count | 累计 ACK 数 |
| 2 | DL NACK Count | 累计 NACK 数 |
| 3 | DL StatDTX Count | 统计 DTX 数 |
| 4 | DL NACK/StatDTX Count | NACK/StatDTX 合计 |
| 5 | PDSCH BLER Count | PDSCH 错误块数 |
| 6 | PDSCH BLER Ratio | PDSCH BLER 比例 |
| 7 | DL Average Throughput | 下行平均吞吐量，Mbps |
| 8 | DL Throughput Ratio | 实测吞吐量与参考吞吐量的比例 |

解析示意：

```text
progress_count,
dl_ack_count,
dl_nack_count,
dl_statdtx_count,
dl_nack_statdtx_count,
pdsch_bler_count,
pdsch_bler_ratio,
dl_average_throughput_mbps,
dl_throughput_ratio
```

注意：

- BLER Ratio 通常为小数，例如 `0.01` 表示 1%；
- 结果仅在 `CELL1=CONNected` 且 BTPut State 为 `ON` 时更新；
- 初始阶段可能没有有效结果，自动化程序应处理空值或 `NaN`。

---

# 7. 查询上行 BLER 和吞吐量

## 7.1 查询命令

```scpi
BSE:MEASure:NR5G:CELL1:BTPut:UL?
```

## 7.2 返回字段顺序

返回值为逗号分隔字符串，共 5 个字段：

| 索引 | 字段 | 含义 |
|---:|---|---|
| 0 | Progress Count | 已发送给 UE 的 DL Transport Block 数 |
| 1 | UL ACK Count | 累计 UL ACK 数 |
| 2 | UL NACK Count | 累计 UL NACK 数 |
| 3 | PUSCH BLER Ratio | PUSCH BLER 比例 |
| 4 | UL Throughput | 上行平均吞吐量 |

解析示意：

```text
progress_count,
ul_ack_count,
ul_nack_count,
pusch_bler_ratio,
ul_throughput
```

手册说明：

> UL 结果中的 Progress Count 仍然表示已发送给 UE 的 DL Transport Block 数，与 UL ACK Count、UL NACK Count 没有直接对应关系。

手册正文将 UL Throughput 单位写成 `MBps`，但结果定义表写为 `Mbps`，并且 RF App 其他吞吐量结果统一使用 Mbps。自动化程序建议记录原始返回值，并按照当前 RF App GUI 显示单位进行最终确认。

---

# 8. 实时 OTA 吞吐量查询

## 8.1 清除实时统计

```scpi
BSE:METRics:RESet
```

该命令会清除所有 Realtime Statistics，包括：

- NR OTA Throughput；
- LTE OTA Throughput；
- LTE+NR OTA Throughput；
- IP Throughput；
- Peak、Average 和 Transferred 统计。

---

## 8.2 查询 NR 下行 OTA 吞吐量

```scpi
BSE:METRics:TMONitor:OTA:DL:NR?
```

## 8.3 查询 NR 上行 OTA 吞吐量

```scpi
BSE:METRics:TMONitor:OTA:UL:NR?
```

两条命令的返回格式均为：

```text
Current,Peak,Average,Transferred
```

| 索引 | 字段 | 单位 |
|---:|---|---|
| 0 | Current | Mbps |
| 1 | Peak | Mbps |
| 2 | Average | Mbps |
| 3 | Transferred | bit |

字段含义：

- `Current`：当前 Reporting Period 的平均吞吐量；
- `Peak`：自上次 Reset 以来的峰值；
- `Average`：自上次 Reset 以来的累计平均值；
- `Transferred`：自上次 Reset 以来累计传输的比特数。

无有效结果时可能返回：

```text
NaN,NaN,NaN,0
```

吞吐量分辨率：

```text
0.01 Mbps
```

---

# 9. NSA 模式下查询 LTE+NR 总吞吐量

## 9.1 下行总 OTA 吞吐量

```scpi
BSE:METRics:TMONitor:OTA:DL:ALL?
```

## 9.2 上行总 OTA 吞吐量

```scpi
BSE:METRics:TMONitor:OTA:UL:ALL?
```

统计范围：

- NSA：LTE 和 NR Serving Cells 合计；
- SA：只有 NR Serving Cells。

返回格式：

```text
Current,Peak,Average,Transferred
```

如需分别查看 LTE 与 NR：

```scpi
BSE:METRics:TMONitor:OTA:DL:LTE?
BSE:METRics:TMONitor:OTA:UL:LTE?
BSE:METRics:TMONitor:OTA:DL:NR?
BSE:METRics:TMONitor:OTA:UL:NR?
```

---

# 10. IP 层吞吐量查询

## 10.1 下行 IP 吞吐量

```scpi
BSE:METRics:TMONitor:IP:DL?
```

## 10.2 上行 IP 吞吐量

```scpi
BSE:METRics:TMONitor:IP:UL?
```

返回格式：

```text
Current,Peak,Average,Transferred
```

其中：

- Current、Peak、Average：Mbps；
- Transferred：bit。

IP Throughput 的统计对象是所有用户面 PDCP Entity，不区分 LTE 或 NR。

重要区别：

- 开启 MAC Padding：可以产生 OTA 吞吐量；
- 查询 IP Throughput：必须存在真实 IP 用户面数据流；
- RF App 的 IP Throughput 查询命令不会自动启动 iperf、FTP 或 UDP 流量。

如果只开启 Padding，没有真实 IP 流量，可能出现：

```text
OTA Throughput > 0
IP Throughput = NaN 或 0
```

---

# 11. 查询理论最大吞吐量

## 11.1 PDSCH 理论最大吞吐量

```scpi
BSE:CONFig:NR5G:CELL1:PHY:PDSCh:TPUT:TMAX?
```

返回：

- 单位：Mbps；
- 分辨率：0.01 Mbps。

该结果会随影响 PDSCH 吞吐量的配置自动更新。

---

## 11.2 PUSCH 理论最大吞吐量

```scpi
BSE:CONFig:NR5G:CELL1:PHY:PUSCh:TPUT:TMAX?
```

返回：

- 单位：Mbps；
- 分辨率：0.01 Mbps。

---

## 11.3 计算吞吐量利用率

自动化程序可计算：

```text
DL utilization = 实测 DL Average Throughput / 理论最大 PDSCH Throughput
UL utilization = 实测 UL Throughput / 理论最大 PUSCH Throughput
```

注意：

- 理论最大吞吐量是根据当前 RF App 配置计算的理论值；
- 实测值还会受到 BLER、HARQ 重传、调度开销、控制信道、TDD Pattern 和 UE 能力影响。

---

# 12. 停止测试与恢复配置

## 12.1 停止 BTPut 测量

```scpi
BSE:MEASure:NR5G:BTPut:STATe OFF
```

---

## 12.2 关闭 Padding

下行：

```scpi
BSE:CONFig:NR5G:CELL1:SCHeduling:DL:PADDing:STATe OFF
```

上行：

```scpi
BSE:CONFig:NR5G:CELL1:SCHeduling:UL:PADDing:STATe OFF
```

---

## 12.3 清除统计结果

```scpi
BSE:MEASure:NR5G:BTPut:RESet
BSE:METRics:RESet
```

---

# 13. 手册参考：最小可执行 DL/UL 吞吐量测试命令序列

> 本节同时包含 DL 和 UL 参考命令，并使用单次窗口，不是当前软件第一版最大 DL
> 吞吐诊断的精确执行序列。当前已打通的软件命令与顺序以第 0 节为准。

以下序列假定：

- UE 已 Attach；
- NR `CELL1` 已配置完成；
- 当前 MCS、MIMO、RB 和 TDD Pattern 已满足测试要求；
- 目标是通过 MAC Padding 测试 NR OTA 吞吐量和 BLER。

> 下面的代码块只包含可发送的 SCPI 指令，不包含注释。

```scpi
*CLS
SYSTem:MODE?
BSE:STATus:NR5G:CELL1?
BSE:CONFig:NR5G:CELL1:SCHeduling:DL:PADDing:STATe ON
BSE:CONFig:NR5G:CELL1:SCHeduling:UL:PADDing:STATe ON
BSE:MEASure:NR5G:BTPut:STATe OFF
BSE:MEASure:NR5G:BTPut:CONTinuous:ALL OFF
BSE:MEASure:NR5G:BTPut:LENGth:ALL 2000
BSE:MEASure:NR5G:BTPut:RESet
BSE:METRics:RESet
BSE:MEASure:NR5G:BTPut:STATe ON
*OPC?
SYSTem:ERRor?
BSE:MEASure:NR5G:CELL1:BTPut:DL?
BSE:MEASure:NR5G:CELL1:BTPut:UL?
BSE:METRics:TMONitor:OTA:DL:NR?
BSE:METRics:TMONitor:OTA:UL:NR?
BSE:CONFig:NR5G:CELL1:PHY:PDSCh:TPUT:TMAX?
BSE:CONFig:NR5G:CELL1:PHY:PUSCh:TPUT:TMAX?
BSE:MEASure:NR5G:BTPut:STATe OFF
```

---

# 14. 高吞吐量配置示例

以下示例会修改调度参数，可能触发 RRC Reconfiguration。应在确认 UE 支持目标配置后使用。

```scpi
*CLS
BSE:STATus:NR5G:CELL1?
BSE:CONFig:NR5G:SCHeduling:SCENario RMC
BSE:CONFig:NR5G:CELL1:DL:SCHedule BRMC
BSE:CONFig:NR5G:CELL1:UL:SCHedule ASLots
BSE:CONFig:NR5G:CELL1:SCHeduling:DL:QCONfig QAM256
BSE:CONFig:NR5G:CELL1:SCHeduling:DL:PRB:CALLocation FRB
BSE:CONFig:NR5G:CELL1:SCHeduling:UL:QCONfig CQAM64
BSE:CONFig:NR5G:CELL1:SCHeduling:UL:PRB:CALLocation OFULl
BSE:CONFig:NR5G:CELL1:SCHeduling:DL:PADDing:STATe ON
BSE:CONFig:NR5G:CELL1:SCHeduling:UL:PADDing:STATe ON
*OPC?
SYSTem:ERRor?
BSE:STATus:NR5G:CELL1?
BSE:MEASure:NR5G:BTPut:STATe OFF
BSE:MEASure:NR5G:BTPut:CONTinuous:ALL OFF
BSE:MEASure:NR5G:BTPut:LENGth:ALL 2000
BSE:MEASure:NR5G:BTPut:RESet
BSE:METRics:RESet
BSE:MEASure:NR5G:BTPut:STATe ON
```

---

# 15. 自动功率扫描建议流程

每个下行功率点建议按以下顺序执行：

1. 停止 BTPut 测量；
2. 设置 Cell Power；
3. 等待功率稳定；
4. 确认 UE 仍处于连接状态；
5. Reset BTPut 和 Realtime Statistics；
6. 启动单次 BTPut；
7. 轮询 DL/UL 结果；
8. 保存原始字符串和解析结果；
9. 进入下一个功率点。

功率设置命令：

```scpi
BSE:CONFig:NR5G:CELL1:DL:POWer:CHANnel <dBm_per_BW>
```

例如：

```scpi
BSE:CONFig:NR5G:CELL1:DL:POWer:CHANnel -50
```

单个功率点的推荐序列：

```scpi
BSE:MEASure:NR5G:BTPut:STATe OFF
BSE:CONFig:NR5G:CELL1:DL:POWer:CHANnel -50
*OPC?
SYSTem:ERRor?
BSE:STATus:NR5G:CELL1?
BSE:MEASure:NR5G:BTPut:CONTinuous:ALL OFF
BSE:MEASure:NR5G:BTPut:LENGth:ALL 2000
BSE:MEASure:NR5G:BTPut:RESet
BSE:METRics:RESet
BSE:MEASure:NR5G:BTPut:STATe ON
```

---

# 16. 建议的结果轮询逻辑

## 16.1 BTPut 结果轮询

轮询：

```scpi
BSE:MEASure:NR5G:CELL1:BTPut:DL?
BSE:MEASure:NR5G:CELL1:BTPut:UL?
```

建议判断：

- 返回字段数量是否正确；
- 吞吐量字段是否为有效数字；
- BLER 是否为 `NaN`；
- UE 是否仍为 `CONNected`；
- `SYSTem:ERRor?` 是否返回错误。

RF App 手册在 BTPut 章节中没有给出独立的“测量完成状态”查询。因此，自动化程序可采用以下策略之一：

- 使用 Single 模式，轮询直到结果字段变为有效值；
- 使用 Continuous 模式，按固定周期持续采集；
- 同时记录 Progress Count、吞吐量和 BLER；
- 设置总超时，防止 UE 断连后无限等待。

---

## 16.2 实时吞吐量轮询

建议每秒查询一次：

```scpi
BSE:METRics:TMONitor:OTA:DL:NR?
BSE:METRics:TMONitor:OTA:UL:NR?
```

NSA 总吞吐量：

```scpi
BSE:METRics:TMONitor:OTA:DL:ALL?
BSE:METRics:TMONitor:OTA:UL:ALL?
```

避免过高频率轮询，以免增加远程控制和 RF App 的处理负担。

---

# 17. Python 结果解析示例

## 17.1 解析实时吞吐量

```python
from dataclasses import dataclass


@dataclass
class RealtimeThroughput:
    current_mbps: float
    peak_mbps: float
    average_mbps: float
    transferred_bits: int


def parse_float(value: str) -> float:
    value = value.strip()
    if value.upper() == "NAN":
        return float("nan")
    return float(value)


def parse_realtime_throughput(response: str) -> RealtimeThroughput:
    fields = [field.strip() for field in response.split(",")]

    if len(fields) != 4:
        raise ValueError(
            f"Expected 4 throughput fields, got {len(fields)}: {response!r}"
        )

    return RealtimeThroughput(
        current_mbps=parse_float(fields[0]),
        peak_mbps=parse_float(fields[1]),
        average_mbps=parse_float(fields[2]),
        transferred_bits=int(fields[3]),
    )
```

---

## 17.2 解析下行 BTPut 结果

```python
from dataclasses import dataclass


@dataclass
class DlBtputResult:
    progress_count: int
    ack_count: int
    nack_count: int
    stat_dtx_count: int
    nack_stat_dtx_count: int
    pdsch_bler_count: int
    pdsch_bler_ratio: float
    average_throughput_mbps: float
    throughput_ratio: float


def parse_dl_btput(response: str) -> DlBtputResult:
    fields = [field.strip() for field in response.split(",")]

    if len(fields) != 9:
        raise ValueError(
            f"Expected 9 DL BTPut fields, got {len(fields)}: {response!r}"
        )

    return DlBtputResult(
        progress_count=int(fields[0]),
        ack_count=int(fields[1]),
        nack_count=int(fields[2]),
        stat_dtx_count=int(fields[3]),
        nack_stat_dtx_count=int(fields[4]),
        pdsch_bler_count=int(fields[5]),
        pdsch_bler_ratio=float(fields[6]),
        average_throughput_mbps=float(fields[7]),
        throughput_ratio=float(fields[8]),
    )
```

---

## 17.3 解析上行 BTPut 结果

```python
from dataclasses import dataclass


@dataclass
class UlBtputResult:
    progress_count: int
    ack_count: int
    nack_count: int
    pusch_bler_ratio: float
    throughput: float


def parse_ul_btput(response: str) -> UlBtputResult:
    fields = [field.strip() for field in response.split(",")]

    if len(fields) != 5:
        raise ValueError(
            f"Expected 5 UL BTPut fields, got {len(fields)}: {response!r}"
        )

    return UlBtputResult(
        progress_count=int(fields[0]),
        ack_count=int(fields[1]),
        nack_count=int(fields[2]),
        pusch_bler_ratio=float(fields[3]),
        throughput=float(fields[4]),
    )
```

---

# 18. 常见异常判断

## 18.1 OTA 吞吐量为 NaN 或 0

检查：

```scpi
BSE:STATus:NR5G:CELL1?
BSE:CONFig:NR5G:CELL1:SCHeduling:DL:PADDing:STATe?
BSE:CONFig:NR5G:CELL1:SCHeduling:UL:PADDing:STATe?
BSE:MEASure:NR5G:BTPut:STATe?
SYSTem:ERRor?
```

常见原因：

- UE 只完成 Attach，但已回到 IDLE；
- Padding 被其他测量配置自动关闭；
- 当前 TDD Pattern 没有对应方向的有效 Slot；
- 上行目标功率不合适；
- MCS 过高导致大量 BLER；
- UE 不支持当前 MIMO、MCS Table 或调度配置；
- 测量窗口尚未完成。

---

## 18.2 OTA 有吞吐量，但 IP 吞吐量为 0

这通常不是故障，表示当前只有 MAC Padding，没有真实 IP 业务。

需要额外启动：

- iperf；
- UDP/TCP 数据流；
- FTP；
- 其他用户面业务。

---

## 18.3 修改调度后 UE 断开

可能原因：

- 配置触发 RRC Reconfiguration；
- UE 不支持目标 MCS、MIMO 或带宽组合；
- RF App 重启了相关小区；
- 下行功率过低；
- TDD Pattern 或调度参数与 UE 不兼容。

重新检查：

```scpi
BSE:STATus:NR5G:CELL1?
SYSTem:ERRor?
```

必要时主动连接：

```scpi
BSE:CONNect
```

---

# 19. 常用命令速查表

| 功能 | SCPI |
|---|---|
| 查询系统模式 | `SYSTem:MODE?` |
| 查询 NR 连接状态 | `BSE:STATus:NR5G:CELL1?` |
| 主动连接 UE | `BSE:CONNect` |
| 开启 DL Padding | `BSE:CONFig:NR5G:CELL1:SCHeduling:DL:PADDing:STATe ON` |
| 开启 UL Padding | `BSE:CONFig:NR5G:CELL1:SCHeduling:UL:PADDing:STATe ON` |
| 设置 RMC 调度 | `BSE:CONFig:NR5G:SCHeduling:SCENario RMC` |
| 停止 BTPut | `BSE:MEASure:NR5G:BTPut:STATe OFF` |
| 启动 BTPut | `BSE:MEASure:NR5G:BTPut:STATe ON` |
| 单次测量 | `BSE:MEASure:NR5G:BTPut:CONTinuous:ALL OFF` |
| 连续测量 | `BSE:MEASure:NR5G:BTPut:CONTinuous:ALL ON` |
| 设置测量长度 | `BSE:MEASure:NR5G:BTPut:LENGth:ALL 2000` |
| 重置 BTPut | `BSE:MEASure:NR5G:BTPut:RESet` |
| 查询 DL BTPut | `BSE:MEASure:NR5G:CELL1:BTPut:DL?` |
| 查询 UL BTPut | `BSE:MEASure:NR5G:CELL1:BTPut:UL?` |
| 重置实时统计 | `BSE:METRics:RESet` |
| 查询 NR DL OTA | `BSE:METRics:TMONitor:OTA:DL:NR?` |
| 查询 NR UL OTA | `BSE:METRics:TMONitor:OTA:UL:NR?` |
| 查询 LTE+NR DL OTA | `BSE:METRics:TMONitor:OTA:DL:ALL?` |
| 查询 LTE+NR UL OTA | `BSE:METRics:TMONitor:OTA:UL:ALL?` |
| 查询 DL IP | `BSE:METRics:TMONitor:IP:DL?` |
| 查询 UL IP | `BSE:METRics:TMONitor:IP:UL?` |
| 查询理论 PDSCH 吞吐量 | `BSE:CONFig:NR5G:CELL1:PHY:PDSCh:TPUT:TMAX?` |
| 查询理论 PUSCH 吞吐量 | `BSE:CONFig:NR5G:CELL1:PHY:PUSCh:TPUT:TMAX?` |
| 等待命令完成 | `*OPC?` |
| 查询错误 | `SYSTem:ERRor?` |
| 清空错误队列 | `*CLS` |

---

# 20. 推荐自动化主流程

```text
开始
  ↓
查询系统模式
  ↓
查询 NR CELL1 状态
  ↓
状态不是 CONNected？
  ├─ 是 → BSE:CONNect → 等待并重新查询
  └─ 否
  ↓
配置调度、RB、MCS（可选）
  ↓
开启 DL/UL MAC Padding
  ↓
停止旧 BTPut
  ↓
配置 Single/Continuous 和 Length
  ↓
Reset BTPut 与 Realtime Statistics
  ↓
启动 BTPut
  ↓
轮询 DL/UL BTPut 结果
  ↓
同步读取实时 OTA 吞吐量
  ↓
保存原始返回值、解析结果和当前配置
  ↓
停止 BTPut
  ↓
关闭 Padding（可选）
  ↓
结束
```

---

# 21. 2026-07-13 真实 RF App 验证记录

## 21.1 仪表与应用

```text
VISA endpoint : TCPIP0::201.20.2.1::hislip2::INSTR
*IDN?         : Keysight Technologies,C8714000A RF Application Framework,MY62226143,3.5.134.12281
Application   : IRAT_LITE
CELL1 status  : CONN
```

验证时保持现场已 Attach 的小区配置不变：N66、DL ARFCN 429000、BW10。验收
开始前只读查询得到的实际 Cell Power 为 `-5.0 dBm/BW`，不是此前配置计划中的
`-12 dBm/BW`。诊断序列未修改 Band、ARFCN、带宽、功率、Scheduling Scenario、
MCS、RB 或 MIMO 参数，也未重启小区。

## 21.2 已逐条验证可用的命令

以下命令均在每次操作后读取 `SYSTem:ERRor?`，结果为 `0,"No error"`：

```scpi
BSE:STATus:NR5G:CELL1?
BSE:CONFig:NR5G:CELL1:SCHeduling:DL:PADDing:STATe?
BSE:MEASure:NR5G:BTPut:STATe?
BSE:MEASure:NR5G:BTPut:CONTinuous:ALL?
BSE:MEASure:NR5G:BTPut:LENGth:ALL?
BSE:MEASure:NR5G:BTPut:RESet
BSE:MEASure:NR5G:CELL1:BTPut:DL?
BSE:METRics:RESet
BSE:METRics:TMONitor:OTA:DL:NR?
```

初始读回：

```text
DL Padding    : 1
BTPut State   : 0
Continuous    : 1
Length        : 360000
BTPut DL      : "0,0,0,0,0,0,NaN,NaN,NaN"
TMONitor DL NR: "0,0,0,0"
```

## 21.3 五秒控制闭环实测

验证流程临时把 BTPut Length 设置为 200 DL Slot，连续模式保持 ON；结束后把
Length 恢复为 360000、Continuous 恢复为 1、BTPut State 恢复为 0。最终
`CELL1` 仍为 `CONN`，错误队列为零。

部分原始样本：

```text
BTPut : "160,82,78,0,78,78,0.4875,5.88104,0.5125"
TMON  : "5.88,12.14,8.54,895510752"

BTPut : "160,20,115,25,140,140,0.875,1.4344,0.125"
TMON  : "1.43,12.14,8.43,900574184"
```

连续模式下，一个统计窗口完成后，下一窗口刚开始时 BTPut 可能暂时返回：

```text
"0,0,0,0,0,0,NaN,NaN,NaN"
```

此时软件使用同一采样时刻 `TMONitor` 的 `Current` 作为真实 DL 吞吐样本，
BLER 保持 `null`，不能伪造为 0。待 BTPut 窗口完成后再记录其 BLER。

## 21.4 明确不兼容的旧命令

RF App `IRAT_LITE` 不支持旧 Test App/C870 的 `BTHRoughput` 统计树，例如：

```scpi
BSE:MEASure:NR5G:CELL1:BTHRoughput:DL:TSTatistics:JSON?
```

该命令会返回 `-113,"Undefined header"`，不得用于后台轮询，也不得作为
`BTPut` 的失败重试替代命令。TEST APP 原命令仍保留在独立 Profile 中，不被本
RF App Profile 覆盖。

## 21.5 软件诊断序列

系统诊断序列键：

```text
uxm_rf_app_max_dl_throughput
```

默认参数：

```json
{
  "cell": "CELL1",
  "duration_s": 30,
  "sample_interval_s": 1,
  "measurement_length_slots": 200
}
```

成功只表示：启动成功、至少一个真实 DL 吞吐样本、停止与原设置恢复成功、运行
期间无 SCPI 错误。吞吐量和 BLER 只做信息性统计；即使 BLER 超过 60% 也不会
导致控制流程失败。所有原始 BTPut/TMONitor 返回、时间戳、小区快照、汇总统计、
清理状态和错误记录都会保存到诊断历史。

## 21.6 软件序列30秒现场验收

2026-07-13 16:45–16:46（Asia/Shanghai）通过系统诊断页面对应后端接口执行：

```text
Diagnostic Run ID : da09eb89-dc52-4a23-964e-286aa44419cf
Result            : control flow success
Samples           : 30 total / 30 valid DL throughput
DL mean           : 1.502209 Mbps
DL min / max      : 0.527240 / 1.678560 Mbps
DL std            : 0.242384 Mbps
BLER mean         : 0.158984 (15.8984%)
BLER min / max    : 0.025000 / 0.693750 (2.5% / 69.375%)
Final CELL1       : CONN
Final BTPut State : 0 (OFF)
SCPI errors       : none
```

本次现场数据中 BLER 最高达到 69.375%，序列仍正确标记为控制流程成功，验证了
“高 BLER 只记录、不作为失败门限”的设计。结束时恢复了原 `Length=360000`、
`Continuous=ON`；DL Padding 在开始前已经为 ON，因此保持不变。

需注意：该次运行开始前实际只读回的 `DL:POWer:CHANnel?` 为 `-5.0 dBm/BW`，
与此前记录的 `-12 dBm/BW` 不同。诊断序列没有写入功率命令，所以本次数据对应
验收当时仪表实际的 `-5.0 dBm/BW`；软件按要求保存真实快照，不把历史建议值伪装
成本次实测值。
