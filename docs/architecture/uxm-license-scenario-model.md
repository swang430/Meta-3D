# UXM 多 Lab License × Scenario × Topology 长期架构

> **Status**: 架构参考, 非 first-call 路线图项目。
>
> **Why this exists**: 把 UXM 当成"一台仪表 + 一堆 SCPI"理解, 在
> 单 lab 单场景的 first-call 路径上够用。但产品形态走向多 lab /
> 多 license / 多 scenario 之后, 需要更结构化的模型, 否则每加一
> 个客户就重写一套 driver。这份 memo 沉淀长期架构方向。
>
> **关系到 first-call**: 正交。first-call 路径继续走
> [docs/roadmap-first-call.md](../roadmap-first-call.md)。此 memo
> 描述的是更长期的多 lab 产品演化方向, 在所有 P0 完成 + 至少 1
> 个 second-lab 客户进来之前不主动启动。
>
> **来源**: 2026-05-17 session 外部架构 review (主题:
> "UXM license 结构与测试"), 经选取 + 跟当前 codebase 映射后
> 沉淀。

## 1. 核心认知 — UXM 不是仪表, 是平台

Keysight E7515B UXM 不是传统综测仪, 是一个 **多制式网络仿真与测
试平台**:

- 支持 5G NR / LTE / RedCap / NB-IoT / Cat-M / W-CDMA / GSM /
  C-V2X / WLAN 等技术
- 频率 380 MHz - 15 GHz, 最多 8 个 RF 端口 (4 个 DL+UL, 4 个
  DL-only)
- NR 聚合带宽最高 800 MHz
- 同一硬件上跑多个 **Test Application** (5G_NR_Test /
  LTE_NR_IRAT / RF / Protocol Cert / 其它), 每个有自己的 UI +
  SCPI 命令集 + 测试状态机
- 每个能力都受 **license** 控制

把 UXM 当成"一台仪表"的传统抽象在多客户场景下会爆炸 — 一个客户
买了 NR+LTE 不等于另一个客户也买了 IMS+VoNR+FR2+CA。需要把
license / scenario / topology / SCPI domain 当成独立维度建模。

## 2. License — 5 类分层

License 是 **能力闸门**, 决定操作员"能不能做"。按 5 类分层:

### A. RAT license — "能不能跑这个制式"

| 类别 | 含义 | 自动化设计影响 |
|---|---|---|
| LTE | LTE signaling / callbox / RF | LTE 脚本、LTE cell、attach、throughput |
| 5G NR | NR SA/NSA signaling / RF | NR cell、gNB、PDU session、throughput |
| NB-IoT / Cat-M / RedCap | 物联网 / 轻量 NR | 协议栈状态机不同 |
| WLAN / C-V2X | 非蜂窝扩展 | 通常是独立测试应用 |

"买了 NR + LTE" 不等于自动具备 ENDC / CA / MIMO / FR2 / IMS /
RedCap 能力 — 这些是独立 license 维度。

### B. 部署形态 license — "能不能做这个网络拓扑"

| 拓扑 | 网络结构 | 测试目的 |
|---|---|---|
| LTE only | eNB + EPC | LTE attach / 吞吐 / RF / VoLTE |
| NR SA | gNB + 5GC | NR registration / PDU session / NR RF / VoNR |
| NR NSA / EN-DC | LTE eNB anchor + NR gNB SCG | LTE anchor 下 NR 数据承载, ENDC 吞吐 |
| LTE CA | 多 LTE carrier | LTE CA throughput / RF |
| NR CA | 多 NR carrier | NR CA, FR1+FR1, FR1+FR2 |
| LTE+NR mobility | LTE/NR 重选 / handover / SCG add | 移动性, beam/cell 切换 |

**采购时必须问**: NR license 只支持 SA 还是 NSA/ENDC? CA 是否
另算? FR2 是否另算? MIMO layer 是否另算?

### C. RF / 物理层 license — "能不能测对应 RF 指标"

| 能力 | 影响 |
|---|---|
| FR1 | sub-6 GHz NR / LTE |
| FR2 | 毫米波, 需 OTA / mmWave 拓扑 |
| 带宽 | 100/200/400/800 MHz 聚合能力 |
| MIMO | 2x2/4x4/更多 layer, 受 RF port 数限制 |
| CA / DC | 多载波 / 多小区 / 多制式并发 |
| RF parametric | EVM / ACLR / SEM / 功率 / 灵敏度 |

E7515B 8 RF 端口中只有 4 个支持 DL+UL — 直接限制 MIMO / CA /
ENDC 拓扑可行性。

### D. 协议 / 应用 license — "能不能做真实业务场景"

| 能力 | 测试内容 |
|---|---|
| IMS | VoLTE / VoNR / SMS over IMS |
| IP throughput | TCP/UDP / iPerf / DL/UL throughput |
| Application test | HTTP / FTP / video / ping / QoS |
| Protocol logging | RRC / NAS / MAC / PHY log |
| Conformance / test cases | 预定义一致性 / 回归用例 |

UXM 5G Test Application 提供的是"网络仿真 + RF 参数测试 + 功能
测试 + 应用层测试", 不是仅 RF 发信号。

### E. 自动化 / 测试软件 license — "怎么控制"

常见控制方式:

1. 直接 SCPI 控制 UXM application (我们现在的做法)
2. Keysight 测试应用的 automation API / remote interface
3. TAP / PathWave / Nemo / Test Manager 类测试管理软件
4. Python + VISA / socket / REST / .NET wrapper 自建框架

E7515A 编程文档原话: UXM 上的 measurement applications 各自有自
己的 UI + SCPI + 文档; **配置和编程主要针对这些应用, 而不是只
针对"整台仪表"**。

## 3. 三轴测试拓扑 — 网络 × RF × DUT 状态

不要用 "NR 测试" / "LTE 测试" 这种粗粒度命名, 用三轴模型:

### 第一轴: 网络拓扑

```
LTE only
NR SA
NR NSA / EN-DC
LTE CA
NR CA
LTE + NR mobility
VoLTE / VoNR / IMS
RedCap / IoT
```

例:

| 测试拓扑 | 核心网络 | 基站模拟 | DUT 状态 |
|---|---|---|---|
| LTE only | EPC | eNB | LTE attach |
| NR SA | 5GC | gNB | NR registration |
| NR NSA | EPC / LTE anchor | eNB + en-gNB | LTE attach + NR SCG |
| VoNR | 5GC + IMS | gNB | IMS registered + voice |
| ENDC throughput | EPC + LTE anchor | LTE cell + NR cell | split bearer / NR data |

### 第二轴: RF 拓扑

```
Conducted SISO
Conducted MIMO
FR1 OTA
FR2 OTA
MPAC OTA
Switch matrix
Fading channel emulator
RF shield box
```

| RF 拓扑 | 适合测试 |
|---|---|
| 单线 conducted | 基础 attach、吞吐、功率、灵敏度 |
| 多线 conducted MIMO | 2x2 / 4x4 MIMO throughput |
| RF shield box | 终端整机辐射隔离测试 |
| FR2 OTA | 毫米波 beam / EIRP / EIS |
| MPAC OTA | MIMO OTA / 空间信道 / 动态场景 (**我们当前主战场**) |
| UXM + channel emulator | fading / mobility / delay spread / Doppler |

### 第三轴: DUT 业务状态

```
Idle
Connected
RRC reconfiguration
Registration / Attach
PDU session / PDN
IMS registered
Throughput active
Voice active
Mobility active
CA / DC active
```

**SCPI 命令能不能执行依赖于 DUT 当前状态**:

- 配置小区参数: 通常在 cell off / idle 前完成
- 启动小区: cell on
- 注册 / attach: DUT 发起
- 改带宽 / 频点: 可能需要 cell restart 或重新注册
- 吞吐测试: 必须 PDU session / data bearer 已建立
- ENDC SCG add: 必须 LTE anchor connected

自动化脚本不能按命令顺序写, 必须按状态机写。

## 4. SCPI 8 控制域

SCPI 不是平面命令集, 是"多个软件组件 + 多个应用"的集合。按域划
分:

| 控制域 | 作用 | 示例 |
|---|---|---|
| System | 连接 / 版本 / license / preset / error queue | `*IDN?`, `SYST:ERR?` |
| Application | 选择 / 启动 NR / LTE / IMS / RF app | `SYSTem:APPLication:NAME?` (P2-1 Phase 1 已用) |
| Cell / Network | 配置 eNB / gNB / 小区 / PLMN / TAC / band | `CONFig:NR5G:CELL0:*`, `BSE:CONFig:NR5G:CELL1:*` |
| RF | 频点 / 功率 / 端口 / 路径损耗 / 补偿 | frequency / power / cable loss |
| Signaling | attach / registration / RRC / NAS / PDU | call control |
| Measurement | EVM / ACLR / SEM / power / BLER | RF measurement |
| Data / IP | throughput / ping / iPerf / QoS | data path |
| Logging | protocol log / trace / message capture | debug / evidence |

我们当前 `UxmCommandProfile` 130+ 个 flat attribute (CELL_BAND /
DL_POWER / MIMO_TX_ANT_PORT / etc.) 全部塞一个 class — 是"扁平
命令集"反模式。按域分组应该让 driver 调用模式更清晰。

## 5. 自动化分层框架 (5 层)

```
L0: Instrument Abstraction
    UXM connection / VISA / socket / SCPI send / error handling
L1: Application Driver
    LTE app driver
    NR app driver
    IMS app driver
    RF measurement driver
L2: Network Scenario
    LTE only / NR SA / NR NSA / ENDC / CA / VoLTE / VoNR
L3: Test Case
    attach / registration / throughput / Tx power / sensitivity
    handover / BLER / IMS call
L4: Campaign / Regression
    nightly regression / pre-certification / vendor acceptance
    production sanity
```

调用模式 (理想态):

```python
uxm.nr_sa.configure_cell(band="n78", bandwidth="100MHz", dl_power=-60)
uxm.nr_sa.start_cell()
dut.wait_for_registration()
uxm.data.start_throughput(direction="DL")
result = uxm.measurement.get_throughput()
```

底层映射到具体 SCPI, 上层不感知。

## 6. 测试用例编码约定

```
[RAT]-[MODE]-[RF]-[PURPOSE]-[CASE]
```

例:

```
LTE-CONDUCTED-SISO-ATTACH-001
LTE-CONDUCTED-MIMO-THROUGHPUT-002
NRSA-FR1-SISO-REG-001
NRSA-FR1-MIMO-THROUGHPUT-001
NRNSA-ENDC-FR1-THROUGHPUT-001
NRNSA-ENDC-FR1-SCGADD-001
NRSA-FR2-OTA-BEAM-001
```

每个 case 文件 6 字段:

```yaml
case_id: NRNSA-ENDC-FR1-THROUGHPUT-001
rat: LTE+NR
mode: NSA_ENDC
rf_topology: Conducted_MIMO
required_license:
  - LTE signaling
  - NR signaling
  - NSA / ENDC
  - NR FR1
  - MIMO
  - Throughput
required_hardware:
  - UXM E7515B
  - RF cables
  - switch matrix optional
  - DUT control interface
scpi_domains:
  - system
  - lte_cell
  - nr_cell
  - rf_path
  - signaling
  - data
  - logging
```

License / 拓扑 / SCPI / 报告统一。

## 7. 决策树 — 自动化时该用哪类 SCPI

```
你要控制的是整机状态？
    → System SCPI
你要切换 LTE/NR/IMS 测试应用？
    → Application SCPI
你要配置小区 / 频段 / 带宽 / PLMN？
    → Signaling / Cell Configuration SCPI
你要配置功率 / 频率 / 端口 / 线损？
    → RF Path / RF Level SCPI
你要让 DUT attach / register / 建立 bearer？
    → Call Control / Signaling SCPI
你要测 EVM / ACLR / SEM / BLER / Power？
    → Measurement SCPI
你要测吞吐 / ping / IP 数据？
    → Data / Application SCPI
你要抓 log / 导出 trace？
    → Logging / Trace SCPI
```

## 8. 总体架构图

```
                ┌──────────────────────────┐
                │     Test Campaign        │
                │  回归 / 验收 / 认证前测试 │
                └────────────┬─────────────┘
                             │
                ┌────────────▼─────────────┐
                │      Test Case           │
                │ Attach / RF / Throughput │
                │ Mobility / IMS / OTA     │
                └────────────┬─────────────┘
                             │
                ┌────────────▼─────────────┐
                │     Scenario Layer       │
                │ LTE / NR SA / NR NSA     │
                │ CA / MIMO / VoNR / FR2   │
                └────────────┬─────────────┘
                             │
    ┌────────────────────────▼────────────────────────┐
    │              UXM Driver Layer                    │
    │ LTE Driver | NR Driver | IMS | RF | Logging      │
    └────────────────────────┬────────────────────────┘
                             │
                ┌────────────▼─────────────┐
                │      SCPI / VISA         │
                │  System / App / RF / Sig │
                └────────────┬─────────────┘
                             │
                ┌────────────▼─────────────┐
                │      UXM Hardware        │
                │ RF ports / Apps / License│
                └──────────────────────────┘
```

---

## 9. 当前 Codebase 映射 — 有什么 / 缺什么

把上面的框架映射回 [api-service/app/](../../api-service/app/) 当前状态:

### 5 类 license 维度

| 类别 | 当前 codebase | 状态 |
|---|---|---|
| A. RAT license | 无 | 缺 |
| B. 部署形态 license | `UxmTestProfile` 隐式 (cell_id 暗示 SA vs IRAT) | 没 first-class |
| C. RF 能力 license | `UxmTestProfile.mimo_layers` / `bandwidth_mhz` | 当配置, 没当 license |
| D. 协议 / 应用 license | 无 | 缺 |
| E. 自动化 license | 无 | 缺 |

### 5 层自动化框架

| 层 | 当前 codebase | 状态 |
|---|---|---|
| L0 Instrument abstraction | [api-service/app/hal/base.py](../../api-service/app/hal/base.py) + 各 `Real*Driver` 类 | ✅ 有 |
| L1 Application driver | `UxmCommandProfile` 子类 (5G_NR_Test / IRAT) — P2-1 Phase 1 (PR #36) 新建 | ✅ 部分 (仅 UXM Test App 层) |
| L2 Network scenario | **无 first-class**, 跟 topology 混在 [api-service/app/hal/uxm_test_profiles.py](../../api-service/app/hal/uxm_test_profiles.py) | ⚠️ 缺 |
| L3 Test case | [api-service/app/models/test_plan.py](../../api-service/app/models/test_plan.py) `TestPlan` + `TestStep` | ✅ 有 |
| L4 Campaign / regression | TestPlan 队列 + queue position | ✅ 有 |

### 3 轴 topology

我们的 `UxmTestProfile` 是 "Scenario + RF + Config" **三件套硬塞
一个 dataclass**:

| 轴 | `UxmTestProfile` 字段 | 状态 |
|---|---|---|
| 网络拓扑 (LTE / SA / NSA / VoNR) | 隐含在 `cell_id` + `band` | 混在一起 |
| RF 拓扑 (SISO / 2x2 / 4x4 / OTA / fading) | `mimo_port_preset` | ✅ 有但偏粗 |
| DUT 业务状态 (idle / attached / RRC reconfig / etc.) | 无 | 缺 |

### 8 SCPI 控制域

`UxmCommandProfile` 130+ 个 flat attribute, 没按域分组:

```python
class UxmCommandProfile:
    # 平面 (今天)
    CELL_BAND = ...
    CELL_DL_ARFCN = ...
    DL_POWER = ...
    SSB_POWER = ...
    MIMO_TX_ANT_PORT = ...
    PDSCH_MCS = ...
    # ... 130+
```

理想态 (未来):

```python
class UxmCommandProfile:
    cell: CellConfigCommands       # CELL_BAND, CELL_DL_ARFCN, ...
    rf: RfPathCommands             # DL_POWER, SSB_POWER, ...
    mimo: MimoCommands             # MIMO_TX_ANT_PORT, ...
    measurement: MeasurementCommands  # EVM, ACLR, ...
```

按域分组让 driver 调用模式更清晰, 减少操作员混淆 (e.g. "改频点
要不要重启小区" 这种问题就有明确归宿)。

---

## 10. P2-1 Phase 1 (PR #36) 在这个框架里的定位

PR #36 落地的是:

- L0 (driver) + L1 (Test App vocabulary) 的明确分层
- 操作员可选 topology profile 的 GUI 入口
- detected_test_app 审计

但**没**覆盖:

- License 维度 (5 类) — 完全缺失
- Scenario 跟 Topology 跟 Config 的拆分 — `UxmTestProfile` 仍是
  三合一
- DUT 业务状态机 — 完全缺失
- SCPI 域分组 — `UxmCommandProfile` 仍是平面 130 字段

PR #36 在 first-call 路径上是充分的 (CAICT 一个 lab 一个
scenario, MIMO OTA throughput 一个 test purpose), 但**作为多 lab
产品架构基础是不够的**。

## 11. 触发条件 — 什么时候启动这个长期架构工作

不主动启动。触发条件 (任一):

- **客户 #2 进场**: 第 2 个 lab 客户要 onboarding, 他们的 license
  组合跟 CAICT 不同 (e.g. 只买了 NR SA 没买 NSA, 或者要做 VoNR /
  FR2 / IMS), 当前 `UxmTestProfile` 单维度模型不够用 → 启动
  License + Scenario 层重构
- **CAICT 现场 IRAT 拓扑做不下去**: 如果未来某次现场要扩展到
  IRAT-specific 的 topology profile (今天 7 个 built-in 都是
  5G_NR_Test 的), 需要先把 `UxmTestProfile` 拆 Scenario / Topology
  / Config 才能干净加 IRAT 模板
- **测试用例库膨胀**: 当 TestPlan / TestCase 数量超过 50, 没有
  统一编码 (`[RAT]-[MODE]-[RF]-[PURPOSE]-[CASE]`) 检索不动 → 启动
  L3 test case 编码规范化

在以上任一触发前, [docs/roadmap-first-call.md](../roadmap-first-call.md)
P0-P3 全部优先。

---

## 12. 反推法 — 给售前 / 采购的 License 矩阵

未来给客户 / 售前用 (今天 CAICT 已采购不需要), 模板:

| 测试需求 | 是否需要 | 对应 license / option | 是否已包含 | 备注 |
|---|---|---|---|---|
| LTE signaling | ? | LTE application | ? | attach / throughput |
| LTE RF parametric | ? | LTE RF measurement | ? | Tx/Rx |
| NR SA FR1 | ? | NR SA / FR1 | ? | n78 / n41 等 |
| NR NSA / ENDC | ? | ENDC / NSA | ? | LTE anchor + NR SCG |
| NR FR2 | ? | FR2 / mmWave | ? | 需 OTA / mmWave 硬件 |
| NR CA | ? | NR CA | ? | 多 carrier |
| LTE CA | ? | LTE CA | ? | 4CC/5CC 等 |
| 4x4 MIMO | ? | MIMO / RF port | ? | 受 RF port 限制 |
| VoLTE | ? | IMS / VoLTE | ? | LTE IMS |
| VoNR | ? | IMS / VoNR | ? | NR IMS |
| RedCap | ? | RedCap | ? | Rel-17/18 |
| Protocol log | ? | logging / analysis | ? | 调试必需 |
| Automation API | ? | remote / automation | ? | SCPI / API 文档 |
| Test case package | ? | conformance / regression | ? | 是否买现成用例 |

这张表归 `docs/sales-onboarding/` 之类目录 (今天不存在), 不在
first-call 路线图上。

---

## 13. 关键判断总结

把 UXM 设计成 **"平台 + license 能力 + 测试拓扑 + SCPI 域 +
用例库"**, 而不是 "一台仪表 + 一堆命令"。

5 个维度各回答 1 个问题:

| 维度 | 回答 |
|---|---|
| License | 我能不能做? |
| Topology | 我怎么连? |
| Scenario | 我模拟什么网络? |
| SCPI domain | 我控制哪一层? |
| Test case | 我要验证什么指标? |
| Report | 结果是否通过? |

这个分层让:

- 售前: 按测试需求反推 license + 硬件清单
- 自动化工程师: 按 scenario / domain 写脚本, 不混不杂
- 测试工程师: 按 case 编码组织用例库
- Driver 开发: 按 SCPI 域组织命令, 不再 130 字段平面化
- 多 lab 客户: 每个客户的 license profile 显式声明, 不兼容直接
  refuse (跟 P2-5 / P2-1 Phase 1 的 refuse 模式一脉相承)

但**对当前 first-call 不是必要的** — 维持纪律, 继续走
[docs/roadmap-first-call.md](../roadmap-first-call.md), 到客户
#2 进场时再回来看。
