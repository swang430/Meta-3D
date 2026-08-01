# 现场首测调试协议 (On-Site First-Call Protocol)

> **Governance 文档**：规范下一次现场调试流程，把 CAICT 2026-05-12/13 的教训固化成
> 可执行纪律。配套 [`docs/roadmap-first-call.md`](../roadmap-first-call.md) 的
> **「🚧 Blocked on hardware」表**使用 —— 当天的 P0 队列以那张表为准
> （本文不硬编码队列内容，P1-23 起：此前硬编码 P0-3/4/5 已两次 stale）。
>
> 一句话目标：**现场只调硬件，不写 driver 代码。**

---

## 0. 为什么有这份协议（post-mortem）

CAICT 两天现场本应交付 chamber first-call，结果全耗在 driver 层救火（F64 IDN /
UXM Test App / Aerotech 单轴 / idle-close）。工作本身有价值，但 first-call 没出来。

**根因**：软件链路没在本地走通就上现场 → 现场既调硬件又写/改 driver → 时间被吞。

本协议（连同已落地的 P0-6 mock 彩排、P1-8/9 fail-loud gate、P2-8 cockpit 就绪带、
P1-11 多子网 runbook）的全部设计目标，就是把"写软件"挪到出发前，让现场时间只花在
真硬件 / RF / 校准上。

---

## 1. 铁律（Cardinal Rules）— 违反即停

1. **现场不写 driver 代码。** driver 是出发前本地 mock 跑通的产物。现场冒出 driver
   bug = 本地验证有洞：记 backlog、能绕则绕，**不当场重写**。
2. **WIP = 1 on P0。** Current Focus 按 roadmap **「Blocked on hardware」表**的当前
   排队推进（写作本版时 = P0-5 主线 + P0-8 现场半同窗），一次一个，一个 gate 过了再进
   下一个。（此前这里硬编码"P0-4 → P0-3 → P0-5"，P0-3/4 完成后即 stale —— 队列内容
   永远查表，不抄进本文。）**例外（P1-23 定）**：P0-8 的两个子门（P0-8a@Phase 1.5 /
   P0-8b@Phase 4）是 P0-5 主线窗口内的**伴随验证**，按 Phase 顺序走、不占独立 WIP 槽 ——
   否则"P0-8 未完不能进 P0-5、P0-5 未开做不了 P0-8b"会互锁（Codex #257）。
3. **Timebox 救火。** 单仪表 / 单问题 bring-up 超 **30 min** 未通 → 标 blocked，转向
   能推进的，收工 review 再定。别让一个仪表吃掉一天。
4. **区分两类问题：**
   - **software bug**（本地 mock 跑通的东西现场崩）→ 异常，记 backlog + 日志/截图，
     **不当场 debug**，绕过继续别的 Phase。
   - **hardware / RF / config / network**（仪表、连线、子网、校准、DUT）→ 合法现场
     工作，当场解。
   判别工具：cockpit 就绪带的 **unreachable vs SCPI-fail** 区分（P1-11）+ 现象。
5. **现场发现 → backlog，不 detour**（同 roadmap 治理规则 3）。当日 backlog 行格式：
   `[discovered on-site YYYY-MM-DD during PhaseN] <一句话>`。
6. **验证手段排序：SCPI 探测 > GUI > RDP。** RDP 是最后手段，不当首选诊断。

---

## 2. 出发前硬门槛（Pre-departure Entry Gate）— 不过不出发

> 这一关是整个协议的杠杆点。出发前在本地把软件链路彻底走通，现场才可能"只调硬件"。

- [ ] **mock-data first-call (P0-6) 本地端到端跑通**，PDF 报告出得来
- [ ] **`propsim_f64_p08_gate` 诊断序列已写好并 mock 跑通**（Phase 1.5 / P0-8a 的
  唯一合法载体：load→run→改参→电平判据；没有它现场做不了 P0-8a —— P1-23 遗留行动项）
- [ ] **driver 代码冻结**：打 git tag 作为出发基线（如 `onsite-baseline-YYYYMMDD`）
- [ ] **cockpit readiness 在 mock 模式全绿**（驱动链 / 活动 Lab / 校准证书；DUT 灰色
      = 已知占位，不算阻塞）
- [ ] **多子网网络方案就绪**：读过 [`multi-subnet-instrument-network.md`](multi-subnet-instrument-network.md)，
      IP 别名命令 + 子网图准备好
- [ ] **plan-level preflight validator (P1-1)** 对目标 plan 通过
- [ ] **仪表清单成表**：每个仪表的默认 IP / 子网 / SCPI 端口 / 连接模型（单 client
      还是多 client）/ 必需的 Test App（见下方速查表）
- [ ] **LabProfile 配好**（P0-2 wizard），目标 chamber 几何 + probe 映射就位
- [ ] **物理清单**：备用线缆 / horn 天线（含 datasheet TRP）/ 测试 SIM / 转接头
- [ ] **离线可用**：本地能起后端 + DB（断网现场不依赖云端服务）

### 仪表 bring-up 速查表

| 仪表 | 典型子网 | 连接模型 | bring-up 要点 |
|------|---------|---------|--------------|
| PROPSIM F64（信道仿真器） | `192.168.0.x` | **单 client SOCKET** | 连之前先确保**没有别的客户端 / GUI 占用**；身份查 `SYST:INFO?`（**不是 `*OPT?`**，F64 ATE Server 不支持）；返回 `-100` = 命令不存在，是正常分类不是 fail |
| UXM E7515B（基站仿真器） | `192.168.1.x` | 多 client 友好 | 先确认 **Test App 已启动**（5G NR FR1）；用 hislip endpoint |
| R&S FSVA3000（信号分析仪 SA，校准接收端） | `192.168.1.x` | — | IDN + 频段确认；P0-4 把它 bind 到 `signalAnalyzer`，GUI 选 model=`FSVA3000`（HAL 自动用 `RealRsFsvaDriver`）；SCPI 是 R&S FSW/FSVA 命令族，非 Keysight X-Series |
| ENA / VNA | — | — | IDN + 基本扫描 |
| RF Switch | — | — | IDN + 通道切换 |
| Aerotech 转台 | — | — | IDN + 单轴回零 / 定位（CAICT 曾卡在单轴） |

---

## 3. 现场分阶段执行（Phase-Gated Execution）

每个 Phase 末尾一个 **go/no-go gate**。**gate 不过不进下一阶段**。gate 标准直接取自
roadmap 对应 P0 项的 acceptance criteria。

### Phase 0 — 网络 / 连通性 bring-up
**目标**：控制 PC 够到所有目标子网的所有仪表。
**步骤**：
1. 按 P1-11 runbook 方案 A，给单网卡挂各子网 IP 别名（F64 `0.x` + UXM/SA `1.x`）：
   `sudo ifconfig en0 alias 192.168.1.10 netmask 255.255.255.0`
2. 逐仪表 `nc -vz <ip> <port>` 验证 TCP 层可达。
3. 打开 cockpit 就绪带，看 **per-subnet 可达性**面板。

**故障树**：
- 某仪表 cockpit 标"**网络不可达**" → 子网 / 别名 / 连线问题：查 `ifconfig` 是否真挂上
  别名、交换机口、网线。**不是 driver。**
- reachable 但 SCPI 无响应 → 留给 Phase 1。

**Gate**：cockpit 就绪带**所有目标子网 ✅**，所有目标仪表 reachable。

### Phase 1 — 逐仪表 SCPI 握手
**目标**：每个仪表 `*IDN?` ✓ + capabilities 符合声明。
**工具**：`POST /instruments/{cat}/test-connection`、`/scpi-probe`（**不是改 driver，
不是 RDP**）。也可 `python -m scripts.driver_selftest` 看 HAL 加载态。
**逐仪表**：见上方速查表（F64 单 client / UXM Test App / SA 频段 / 转台回零）。

**故障树**：
- **IDN 超时但 TCP 通** → SCPI 层问题：仪表忙 / Test App 没起 / 单 client 被占用。
  **不是网络，不是 driver bug。**
- 命令返回 `-100` / `-113` → 该命令在此仪表不存在，查 capabilities 表用替代命令。
- 连接随后 **idle-close**（P2-4 假设：NAT/FW idle drop）→ 周期 poke 保活；记录现象
  喂 P2-4，**不要**当成 driver 重连 bug 去改代码。
- 排查顺序始终 **SCPI 探测 > GUI > RDP**。

**Gate**：所有目标仪表 IDN ✓、capabilities 符合、HAL readiness 对应行 `ok`。

### Phase 1.5 — F64 信道链验证（P0-8a gate，P1-23 新增）
**目标**：验证 P0-8 本地半修好的 F64 驱动在 real F64 上真落地 —— 这是 2026-07-21
现场问题的正修回归，**不做会让上次现场的修复停留在"本地绿"**。
**为什么单独成段**：比 Phase 1 的握手级检查重（要 load→run→改参→读电平），又不依赖
Phase 2/3 的 SA 与校准 —— 排在握手后立即做，问题越早暴露越好。
**步骤**（禁临时脚本；载体 = checked-in 诊断序列 **`propsim_f64_p08_gate`**，
覆盖 load→run→改参→电平四步判据 —— **该序列尚未写，已列入 §2 出发前硬门槛**，
Codex #257 核实：现有 `propsim_f64_state_machine` 前提 .smu 已加载且只做
GO/STATIC/GOS、`propsim_f64_health` 只读探测恒判成功，都干不了这三步）：
1. load 场景包（`.smu`，用 SCD 登记的实测频率对齐 TestCase）→ run → 读错误队列
2. 运行中改参（归一化功率）→ 再读错误队列
3. 读输入口电平状态并按合法范围判定
**Gate（= P0-8a，P0-8 验收中不依赖 DUT 的前两条）**：
- load → run → 改参全程 **0 error**（错误队列每步清零）
- F64 **输入口变绿**（输入电平在合法范围）
- ⚠️ P0-8 验收第三条「DL 不失真（非 0% ACK）」**依赖 DUT attach，挂在 Phase 4
  的 gate 里（P0-8b），本段不验** —— gate 拆两半是设计决策，别在这里等 DUT。
**与 §7 的关系**：§7 是 F64 **能力探测**清单（探未知，结论回填文档）；本段是
**修复验证** gate（验已知，过/不过）。同一台仪器同一段窗口，性质不同别混记。

### Phase 2 — SA 入 HAL（P0-4）
**目标**：真 SA 读参考 TRP，替掉 `_MOCK_TRP_DBM` 假值。
**步骤**：在 GUI 把 `signalAnalyzer` 的 model 选成 `FSVA3000`（HAL 自动绑 `RealRsFsvaDriver`）；
配 horn + offset；reload HAL；跑 reference phase。
**Gate（= P0-4 acceptance）**：
- `signalAnalyzer` driver loaded（readiness 表 ✓）
- reference phase 日志 `measurement_source: "hal_signal_analyzer"`（不是 mock fallback）
- measured TRP 在 horn datasheet TRP **±1 dB**

### Phase 3 — 路损校准（P0-3）+ 证书
**目标**：CE+SA 跑完 32 链路路损校准，出 CalibrationCertificate。
**步骤**：CE 出 tone → SA 收功率 → 逐链路；生成 cert；commissioning precheck 应看到
cert **停止 warning**（P1-8 gate）。
**Gate（= P0-3 acceptance）**：
- cert 含全部 **32 链路**
- `overall_pass = True`
- `valid_until > now()`（典型 +30 天）
- precheck phase 看到 cert 不再 warn
- **重复测一次，路损值在 ±0.5 dB 内**（可重复性）

### Phase 4 — DUT attach → bearer → PDSCH（P0-5）
**目标**：真 DUT 接入 UXM，跑真吞吐。
**步骤**：DUT 入舱 → `POST /test-executions/{id}/attach-dut`（记 IMSI + RRC）→ UE
capability 查询 → 单方位扫吞吐 → 4 方位扫。
**故障树**：attach 失败 → 先看 **P1-9 DUT-attach fail-loud gate** 报的原因
（RRC 未连 / IMSI 缺失），按提示修配置，**不是 driver**。
**Gate（= P0-5 acceptance + P0-8b）**：
- attach 成功，记录 IMSI + RRC 状态
- UE Capability 查询 `max_dl_layers >= 配置层数`
- 单方位扫产生**非零**吞吐读数（来自 UXM）
- 4 方位扫给出 **4 个不同**吞吐值（旋转 sanity check）
- **P0-8b（P0-8 验收第三条，依赖 DUT 故挂本段）**：DL 经 F64 衰落链路
  **非 0% ACK**（DL 不失真）—— 与 Phase 1.5 的 P0-8a 合起来才算 P0-8 现场半收口

### Phase 5 — 完整真 first-call
**目标**：端到端真 first-call，出 PDF。
**步骤**：跑完整 plan（precheck → reference → measure → analysis → report），所有
fail-loud gate 通过。
**Gate**：first-call PDF 生成；cockpit 全绿；关键指标在合理范围。

---

## 4. 每日收工 review（15 min）

现场版的 roadmap 周 review，三问：
1. 今天该推进哪个 Phase，实际到哪个 gate？
2. 卡点是 **hardware/RF/config/network（合法）** 还是 **software（异常，说明本地验证
   有洞）**？
3. 明日 Current Focus = 哪个 Phase？阻塞项记 backlog 了吗？

**产出**：当日 backlog 行（`[discovered on-site ...]`）+ 明日计划 + 已过的 gate 记录。

---

## 5. 升级 / 求助阈值

- 单 gate 卡 **> 半天**，且非纯硬件物理问题 → 停下，整理现象 + SCPI trace，远程协作，
  不死磕。
- 出现 **software bug**（本地 mock 跑通的东西现场崩）→ 立即记 backlog + 截图/日志，
  绕过该路径继续别的 Phase。**绝不**当场 debug 吃掉现场时间——这正是 CAICT 的陷阱。

---

## 6. 收工后 retro → 喂回 roadmap

- 现场暴露的所有 **software 洞** triage 成本地 P-item（**下次出发前补**，不留到下次现场）。
- 现场完成的 P0 项标 ✅ Done + 记录 acceptance 验证结果。
- 更新 roadmap 的 on-site 队列 + Summary counts。
- 写一篇 trip retro（仿 [`2026-05-14 baseline announcement`](../announcements/2026-05-14-roadmap-baseline.md)），
  记 drift 程度（0% / 30% / 100%）+ 原因属铁律 1-6 哪一类。

---

## 7. PROPSIM F64 信道注入现场验证清单

> 源：信道注入参考 [`../hardware/PROPSIM_F64_信道注入工程文档_A-B路线_SCPI_V1.2.docx`](../hardware/PROPSIM_F64_信道注入工程文档_A-B路线_SCPI_V1.2.docx) §10。
> 这些项**只能真机确认**（符合铁律「现场只调硬件、不写 driver」），扩展 **Phase 1**（F64 SCPI 握手）+ 信道模型加载。
> 开发期能 mock 的先用同源 N7605 命令本地走通；现场逐项打勾，结论回填 docx 升版（V1.3…）+ roadmap backlog。

- [ ] **运行时多普勒上限**：GCM 内可设 ±500 kHz；GCM 外目前仅查到运行时约 200 kHz（`CH:MOD:CONT:ENV` 的 `<doppler>`）。验证非-GCM 路径能否开到 ±500 kHz（很可能同一硬件引擎，差别在 API/许可）→ 决定 B 路能否免 GCM 覆盖 NTN Ka。
- [ ] **`CALC:FILT:CENT:CH` 载频偏置**：能否当 B 路「常数大质心」频偏（载频平移 ≈ Doppler），其可设范围 + 步进精度。
- [ ] **射频前端独立频偏接口**：是否暴露独立频偏接口，用于 B 路动态大质心。
- [ ] **file-based per-link 上限**：每链路最大抽头数 + 最大 CIRs（长轨迹 / 多簇是否受限）。
- [ ] **锁定状态改速度边界**：`CIRUpdateRateLocked=1` 下运行时改速度的可行范围。
- [ ] **逐通道独立模型许可**：`.smu` 拓扑里 Concurrent / 独立每通道模型是否需额外许可（与基础 Scenario Wizard 区分）。
- [ ] **`.tdlx` / `.tap` 字段表(schema)**：真机 Channel Studio TDL Tool 另存逆向确认字段顺序、各多普勒谱形状关键字、user-defined PSD 写法。
- [ ] **per-path 衰落 SCPI mnemonics**：运行时逐抽头 delay/power/谱/fmax/K/AoA 完整 mnemonics 在客户 ATE 手册；开发期用同源 **N7605 `FSIM:FAD:PATH[1..24]:{DELay|LOSS|DFRequency|FTYPe|AOA|AOD}`** mock，需向 Keysight 求证 PROPSIM 等价命令。
- [ ] **`.rtc` 环境切换延迟**：逐点（100 Hz = 10 ms）切换 environment 的抖动是否落到 OFDM 符号尺度，实测避免切换瞬态污染。
- [ ] **mobile speed 标量 vs per-path fmax**：`DIAG:SIMU:MOB:MAN:CHG` 是整通道标量缩放；若各 path 需不同 fmax，须 per-path SCPI 或重载 `.rtc`。
- [ ] **标准谱对 RT 簇逼近误差**：B-2 用标准谱 + user-defined PSD 逼近射线追踪簇实际多普勒角度谱的误差 → 决定是否触发购买 GCM。

---

## 附：与现有资产的关系

| 资产 | 在本协议中的角色 |
|------|----------------|
| P0-6 mock-data first-call | 出发前硬门槛（本地彩排） |
| P1-1 plan preflight validator | 出发前硬门槛 |
| P1-8 cal-missing fail-loud gate | Phase 3 gate 的执行者 |
| P1-9 DUT-attach fail-loud gate | Phase 4 故障树的诊断源 |
| P1-11 多子网 runbook + 可达性诊断 | Phase 0 / Phase 1 的核心工具 |
| P2-8 cockpit 就绪带 | 全程的 go/no-go 可视化（每个 Phase 看就绪带） |
| diagnostics SCPI 工具（test-connection / scpi-probe） | Phase 1 主力，替代 RDP |
