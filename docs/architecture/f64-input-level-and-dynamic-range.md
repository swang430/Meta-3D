# F64 输入信号参考与动态范围管理 — 设计文档

> **状态**: 设计提案（2026-05-27 起草，来源 CAICT 现场实证）。
> **关联**: roadmap `P0-8`（F64 driver 落地）Step 2 的重定义；`U-6`（现场实测真值）。
> **定位**: 这是把"F64 输入电平 / 动态范围管理"从一个零散步骤提升为**系统级 RF
> 子系统**的设计，也是后续现场调试这条链路的**主参考文档**。

---

## 0. 背景与动机（为什么必须做这个设计）

### 0.1 现场实证（2026-05-27 CAICT）

| 条件 | F64 状态 | 结果 |
|---|---|---|
| UXM CELL1 (N78, BW40, DL ARFCN 636666) + 单层 | `DIAG:SIMU:MODEL:STATIC 3`（calibration 直通，无衰落） | **DL PDSCH 100% ACK** ✓（DUT 正常收发） |
| 同上 + 换 3600M 衰落模型（4 输入 MIMO OTA） | 真实信道仿真（数字缩放/衰落处理） | **0% ACK / all-NACK** ✗（DUT attach 成功、能收到、但解不出 PDSCH） |

两者唯一变量 = F64 是否做**衰落信道的数字处理**。clean 直通不缩放 → 不失真；衰落模型对
输入做数字缩放 → **若输入信号参考（平均电平 + crest factor）没设对，数字域削顶
(digital clipping) → 下行失真 → DUT 解不出**。这正是 User Reference §4.x 警告的
"Scaling signal up digitally can cause clipping depending on used fading, input
signals and their phases"。

### 0.2 现状缺口

- driver 里 `autoset_input_level()` / `set_baseband_power()` 已存在，但**没有任何上层
  调用**（commissioning / measure 全链路零调用）。
- 没有任何系统级机制去设定/校验/监控 F64 的输入操作点。
- 后果：衰落模型一上来就 clipping，吞吐量为 0，且操作员无从诊断（输入口不变绿是唯一
  外部征兆）。

### 0.3 目标（系统价值 — 不只是修一个 bug）

把输入电平 / 动态范围管理做成**核心 RF 操作点子系统**，让整个系统从中获得额外性能：

1. **最大化 F64 动态范围利用** → 静区最高 SNR/最低 EVM → **支撑最大吞吐量测试**（硬需求）。
2. **杜绝 digital clipping** → 下行不失真 → 正确解调。
3. **保持 path loss 保真** → 32 链路校准有效、可重复（P0-3 的前提）。
4. **按输入方向适配特性**：下行静态、上行/双向/WiFi 变输入走 AGC keep pathloss（见 §3）。
5. **操作点 + clipping/cut-off 状态作为系统遥测**暴露给 readiness/cockpit → 操作员一眼
   看到 RF 健康，调试不再靠"猜输入口为什么不绿"。

---

## 1. F64 输入前端模型（手册依据）

数据通路：`BS 下行信号 → 线缆/衰减 → F64 输入前端（ADC）→ 数字衰落处理 → 输出 → 探头`。
输入前端的工作点由两个量定义，二者都可读可设、各有硬限：

| 量 | 设/读 SCPI（§20.4.4） | 限值查询 | 实测范围（现场/手册例） |
|---|---|---|---|
| 平均电平 avg (dBm) | `INP:LEV:AMP:CH <in>,<dBm>` / `?` | `INP:LEV:AMP:LIM? <in>` | input1 = **-23..0 dBm** |
| crest factor (dB) = PAPR | `INP:CRE:SET <in>,<dB>` / `INP:CRE:GET? <in>` | `INP:CRE:LIM? <in>` | input6 = **0..23 dB** |

**核心物理约束**：

```
峰值功率 = avg + crest   ——   必须落在前端 ADC 满量程内
若 avg + crest 超过预留动态  →  digital clipping（数字削顶）  →  失真
```

F64 为衰落计算预留必要动态（User Reference §"Digital clipping", 手册第 5232 行附近）；
预留量由你告诉它的 **crest factor** 决定。给错 crest（尤其给小了）→ headroom 不足 →
真实峰值削顶。clipping 以 **per-mille（千分比削顶样本数）** 在 FADING 元件 + System log
指示；cut-off（输入过强、ADC 饱和）则进硬件告警/状态寄存器。

### 1.1 测量（autoset 的基础）

| SCPI | 作用 |
|---|---|
| `INP:LEV:MEAS? <in>,<t>` → `<avg>,<crest>` | 测量但不设（例 `-21.4,4`）。**无信号 / 输出过强 → device error** |
| `INP:LEV:AUTOSET <in>,<t>` | 测量并设 avg+crest（失败不改旧值、报错）。`<in>=0` → 全输入同测（**保 MIMO 平衡**） |
| `INP:LEV:AUTOSETCANCEL` | 取消进行中的 autoset（并行命令） |
| `INP:MEAS:MODE:SET <in>,<0/1/2/3>` | 测量模式：disabled / basic / **continuous** / **burst** |
| `INP:MEAS:BURST:TRIG:SET …`（§20.4.4.27） | burst 模式触发电平 |
| `INP:MEAS:FREEZE`（§20.4.4.25/26） | 冻结测量值 |

测量时间 `<t>` = 0.5 / 1 / 3 / 5 / 10 秒（User Reference 权威；ATE AN 旧版写 1/3/10/30）。

**TDD 必须用 burst 模式**：5G NR TDD 下行只在 DL 时隙有信号。`continuous` 会把 UL/保护
间隔的静默一起平均进去 → 低估 DL 电平 → 参考设低 → 业务峰值削顶。`burst` = "measurement
done during duty period of signal"，抓 DL 突发的真实 avg+crest。

### 1.2 自动输入电平控制 Ailc（连续闭环，三模式）

`INP:LEV:AUTO:ENA <in>,<state>`（ATE AN §2.4.x）。三模式（User Reference §4.3.4，
手册 5396-5525 行）：

| 模式 | 行为 | path loss | 适用 |
|---|---|---|---|
| **Prevent cut-off** | 电平逼近削顶时自动衰减，回落后撤销 | ❌ **不保持**（衰减时 path loss 变） | 输入会瞬间过冲的场景 |
| **AGC** | 输入增益动态跟随来波功率，输出平均恒定 | ❌ **不保持** | 不在意绝对 path loss |
| **AGC keep pathloss** | 同 AGC，但用数字补偿维持 path loss | ✅ 保持（有条件） | 输入会变 + 仍需 path loss。**"数字不能放大" → 必须预留初始衰减 headroom** |

MIMO 组内所有输入一起测/调（保平衡）；AGC 模式下"最高功率输入决定整组调整量"。

---

## 2. 4G/5G 信号功率结构（为什么"测量条件"是关键）

5G NR（及 4G）信号不是恒包络，平均功率与 PAPR 随**所发内容**剧烈变化：

| 态 | 内容 | 平均功率 | 测到的 crest |
|---|---|---|---|
| 空载 / 只播广播 | SSB (PSS/SSS/PBCH) + 偶发 SIB/寻呼 | 低（占空比低） | SSB 突发的，不代表业务 |
| 满业务 | 满 RB PDSCH | 高 | OFDM PAPR **~10-12 dB** |

加上 **TDD 本身是突发的**（只 DL 时隙有）。

**失真链（0% ACK 的机理）**：若在**空载/广播态**做 autoset（或根本没设）→ F64 按低 avg +
小 crest 预留 headroom → DUT attach 后**满 PDSCH 业务灌入，峰值超预留 → digital clipping
→ 下行失真 → 收得到、解不出（all-NACK）**。

**设计结论**：autoset **必须在代表性最坏条件下做** —— 即 **满 RB DL PDSCH（最大吞吐
配置）**，这也正是系统的吞吐量测试目标态。用 UXM 的 5G NR Test App 配置（§4.2）。

---

## 3. 静态 AUTOSET vs AGC —— 按方向/角色的操作点策略

> **修订来源**：2026-05-27 用户 review 指出本节初稿漏了**闭环功控**这条反馈回路 —— 初稿
> 只把 F64 输入建模为"BS 下行恒定信号"，错误地全局否定了 AGC。下面是吃进该反馈后的模型。
>
> **当前决策（first-call）：走下行静态 AUTOSET（§3.3）。AGC 适用场景在 §3.2/§3.4 记录，
> 供后续双向 + WiFi 测试 —— 当前不实现，只留设计。**

### 3.1 两条不同的输入：下行稳定，上行被闭环功控驱动而时变

F64 输入 = 进入 F64 被加衰落的信号。要分两类，性质完全不同：

**下行输入（BS → F64）—— 稳定**：
- 衰落/动态是 F64 对**输出**施加的；"动态信道模型"（时变 CIR、多普勒、移动）变的是 F64
  **输出**处理，不是下行输入电平。
- 基站下行 TX 功率一次测试里通常恒定（BS 不像 UE 那样对下行功控）；下行 avg 稳定，crest
  仅随链路自适应（MCS/RB）轻微漂。

**上行输入（DUT → F64，当配了双向/上行仿真时）—— 被闭环功控驱动，大幅时变**：

```
F64 给下行加动态衰落
  → DUT 测到的 RSRP 时变
  → DUT 开环功控 P_UE = P0 + α·PL  (PL 路损从下行 RSRP 反估)
  → 下行深衰落 → DUT 估路损变大 → DUT 抬高上行发射功率
  → (上行经 F64 时) F64 上行输入功率随之摆动; BS 闭环 TPC 再叠加调整
```

CDL-C 等模型衰落深度可达 20-30+ dB → **上行输入可摆动几十 dB**，远超任何静态参考的 headroom：
静态参考下，深衰落时 DUT 拉满功率会削顶、信号强时又会过低。手册自己就对这种输入建议 Ailc
（MS 功率例子："MS 链路建立期用高发射功率、之后降到标称；用 Ailc 让 PROPSIM 输入设标称仍能
注册"）。

→ 所以静态 vs AGC **不是全局二选一，而是按方向/角色分**。

### 3.2 按方向的决策表

| F64 输入 | 电平特性 | 模式 | 理由 |
|---|---|---|---|
| **下行**（BS→F64） | avg 稳定；crest 随 MCS/RB 轻微漂 | **静态 AUTOSET**（满 RB 下测一次锁定）+ 监控 crest 漂移 | path loss 保真 + 动态范围最优 + 输入稳 |
| **上行**（DUT→F64，双向/功控） | 被功控驱动，摆动几十 dB | **AGC keep pathloss**（初始衰减按 UE 功率范围预留） | 静态必削顶/过低；手册 MS 例子；数字补偿维持 path loss |
| —— | —— | **不用** plain AGC / prevent-cutoff | 破坏 path loss → 校准失效 |

### 3.3 当前决策（first-call）：下行静态

当前 first-call 主线是**下行 MIMO 吞吐**，0% ACK 也是下行侧削顶（§0.1）。所以**当前实现只做
下行静态 AUTOSET**（满 RB 下测一次锁定），上行 AGC 暂不实现，仅在 §3.4 记录设计。

### 3.4 AGC 适用场景（记录备用 —— 后续双向 + WiFi）

以下场景里 F64 某些输入电平会真实时变，届时按方向启用 **AGC keep pathloss**（初始衰减按功率
范围预留）：

1. **双向 / 闭环功控测试**：上行经 F64 时，上行输入被 §3.1 的功控回路驱动而摆动 → 上行输入
   走 AGC keep pathloss。
2. **脚本化下行功率扫描**（RSRP / 切换 / 功率步进测试故意变 DL 功率）。
3. **波束 / 端口动态**（beam management 切换激活的 TX 端口 → 各输入电平变）。
4. **WiFi（未来）**：WiFi 本质**双向 TDD**（AP 与 STA 都发），有速率/功率自适应 + **高 PAPR**
   （11ax/11be OFDMA、1024/4096QAM，PAPR ~10-13 dB）。两侧入 F64 的电平都可能随自适应变 →
   双向都需 AGC keep pathloss + 严格 crest 管理。且 WiFi 没有蜂窝那种集中 TPC，速率/功率自适应
   更分散、更快，**对 AGC 的响应速度要求更高** —— 这条在 WiFi 立项时要专门评估（采样/收敛
   速度、burst 触发、与 802.11 TXOP 的对齐）。

> 落点（§5）把模式做成**按输入角色可声明**：下行 = 静态、上行/WiFi = AGC keep pathloss，
> 由测试场景声明，默认下行静态。

---

## 4. 闭环设计（UXM 功率 ↔ F64 输入参考）

> 核心洞察：**输入电平由两端共同决定** —— UXM 下行功率（程序设）经线损到 F64 输入。
> 这是一个 **CE↔BS 协调的操作点闭环**，不是 F64 被动 autoset。

### 4.1 闭环流程

```
A. 粗设 UXM 下行功率 → 预期 F64 输入 avg = UXM_pwr − 线损/path loss，
   目标落窗口中部并给 crest 留 headroom（如目标 avg ≈ -15 dBm，使 avg+crest < 0 dBm）
B. UXM 发"代表性最坏信号" = 满 RB PDSCH + DL-heavy TDD 配比（= 吞吐测试态，最大 PAPR）
C. F64 设 burst 测量模式 + burst trigger（抓 TDD DL 突发真值）
D. INP:LEV:AUTOSET 0,<t>（全输入同测，保 MIMO 平衡）→ 设好各输入静态 avg+crest 参考
E. 闭环校验:
     读回 INP:LEV:AMP:CH? / INP:CRE:GET? + 查 clipping(per-mille) / cut-off 状态
     · clip 或 avg 贴顶(0 dBm) → 降 UXM 功率，重测
     · avg 太低 / 趋近噪声 / device-error(无信号) → 升 UXM 功率，重测
     收敛 = avg 在窗口内且有 crest headroom + 无 clipping + 无 cut-off
F. 锁静态参考（默认不开连续 Ailc，保 path loss）→ 跑仿真 → 测吞吐
```

### 4.2 两端 SCPI

**UXM 侧（5G NR Test App，配最大吞吐 + TDD）**：

| 项 | SCPI |
|---|---|
| TDD 配比 | `…:CARRier:SCHeduling:TDD:COMMon:PATTern:DLSLots / ULSLots / DLSYmbols / ULSYmbols / PERiod` |
| SCS | `…:CARRier:SCHeduling:TDD:COMMon:SUBCarrier:SPACing` |
| 满 RB DL 分配 | `…:DL:RBALlocation:TYPE` + `…:DL:RBALlocation:FIXed:RBNumber / RBSTart` |
| 下行功率 | DL power / SSB power（C8700200A 上查询不支持，需 set + GUI 存档核对） |
| 吞吐测量 | `…:BTHRoughput:DL:TSTatistics:JSON?`（per-Tx ACK/NACK/Total）/ `:BLER:STATistical` |

> ⚠ 现场实证：`C8700200A / LTE_NR_IRAT` profile **查询不支持** DUPLEX/MCS/RB/功率（SCPI `?`
> 超时），只能 set + 用 Test App GUI 存档核对（见现场快照 `caict_dut_attached_2026-05-27.json`）。

**F64 侧**：见 §1。关键序列 `INP:MEAS:MODE:SET <in>,3`（burst）→ `INP:LEV:AUTOSET 0,<t>`
→ 读回校验 + clipping/cut-off 状态。

---

## 5. 系统架构落点（系统价值，不是一个 phase 的实验）

> 用户明确：放进 commissioning reference phase 只是"实验意义"；要落成**系统级设计价值**。

**做成一个 RF 操作点管理子系统/服务**（暂名 `InputLevelController` / RF operating-point
service），职责：

1. **协调两端 driver**：调 BS driver（UXM 功率/信号态）+ CE driver（F64 autoset/校验）跑 §4 闭环。
   —— 因为闭环天然跨 driver，这就是它**不能**埋在单个 driver 的 `set_channel_model` 里、
   也不该只活在一个 commissioning phase 里的根本原因。
2. **生命周期触发**：DL 确认 live 后、measure 前自动建立操作点；信道模型/功率/拓扑变更后
   重新评估；模式（静态/AGC keep pathloss）由测试场景声明（§3.3）。
3. **暴露遥测**：当前操作点（每输入 avg/crest）+ clipping per-mille + cut-off 状态 →
   进 HAL readiness + cockpit。操作员看到的是"RF 工作点健康/削顶 0.3‰/输入3 贴顶"，
   而不是"输入口怎么不绿"。这是本设计对**调试效率**的直接贡献。
4. **全系统复用**：校准（path loss/参考 TRP）、measure（吞吐）、动态 MIMO 都从同一操作点
   管理获益 —— 一处实现，全局受益 = 用户要的"额外性能"。

接口分层：`driver 原子能力（§6 Phase1）` ← `操作点管理服务（闭环算法）` → `readiness/cockpit 遥测`。

---

## 6. 实现计划（分阶段；offline 先行，现场只标定真值）

| Phase | 范围 | 离线/现场 |
|---|---|---|
| **1** | F64 driver 原子能力：`autoset_all_inputs()`（`INP:LEV:AUTOSET 0`）、`measure_input()`（`MEAS?`→(avg,crest)）、`set_measurement_mode(burst)`+burst trigger、`get_input_level_limits()`/`get_crest_limits()`、`get_clipping_status()`/`get_cutoff_status()`（薄封装，大部分命令已确认）+ 单测（mock SCPI） | **离线** |
| **2** | 操作点管理服务：§4 闭环算法（含收敛/调整 UXM 功率）。**当前实现下行静态**；上行/双向/WiFi 的 AGC keep pathloss 仅预留模式接口、暂不实现（§3.4）。+ 单测（mock UXM+F64） | **离线** |
| **3** | 现场标定真值（U-6）：UXM 满 RB DL 实际功率 → F64 各输入 avg/crest 实测、burst trigger 实际值、收敛迭代、与 100% ACK 对齐 | **现场** |
| **4** | 遥测接入 readiness/cockpit（操作点 + clipping/cut-off） | 离线写 + 现场验证 |

> 与铁律一致：driver/服务代码 offline 落地，现场只调硬件 + 标定真值。

---

## 7. 现场实测待定项（细化 U-6）

- UXM 实际 TDD 配比（DLSLots/ULSLots/PERiod/SCS）与最大吞吐 FRC/MCS/RB 配置。
- 满 RB DL 条件下，F64 各输入实测 avg（dBm）+ crest（dB）真值 → 锁定标称工作点。
- burst 测量触发电平实际值。
- 闭环收敛：从 100% ACK（STATIC 3 基线）切到 3600M 衰落后，调到无 clipping + 非 0% ACK 的
  UXM 功率 / F64 参考组合。
- 验证：动态 MIMO（时变信道）下静态参考是否确实稳定（验证 §3.1 的"输入稳定"假设）。

---

## 8. 参考

- **F64 User Reference**（Rev 10.2）§20.4.4 Input commands；§4.3.4 BS/MS settings（Crest /
  Ailc 三模式）；"Digital clipping" 节（≈ 第 5232 行）。
- **F64 ATE Environment & Practices AN**（Rev 2.2）§2.4.x Input Level Control & Autoset；
  §2.5 运行态可下发命令。
- **UXM 5G NR Test Application SCPI Reference**：`CARRier:SCHeduling:TDD:COMMon:PATTern:*`、
  `DL:RBALlocation:*`、`BTHRoughput:*`。
- **现场快照** `api-service/app/data/uxm_configs/caict_dut_attached_2026-05-27.json`
  （STATIC 3 + 单层 100% ACK 的可用配置基线）。
- roadmap `P0-8`（本设计重定义其 Step 2）、`U-6`。
