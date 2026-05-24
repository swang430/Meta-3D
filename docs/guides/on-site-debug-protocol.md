# 现场首测调试协议 (On-Site First-Call Protocol)

> **Governance 文档**：规范下一次现场调试流程，把 CAICT 2026-05-12/13 的教训固化成
> 可执行纪律。配套 [`docs/roadmap-first-call.md`](../roadmap-first-call.md) 的 on-site
> P0 队列（P0-3/4/5）使用。
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
2. **WIP = 1 on P0。** Current Focus 按依赖链 **P0-4 → P0-3 → P0-5** 推进，一次一个，
   一个 gate 过了再进下一个。
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
| N9042B / N9020B（信号分析仪 SA） | `192.168.1.x` | — | IDN + 频段确认；P0-4 要把它 bind 到 `signalAnalyzer` |
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

### Phase 2 — SA 入 HAL（P0-4）
**目标**：真 SA 读参考 TRP，替掉 `_MOCK_TRP_DBM` 假值。
**步骤**：bind N9020B/N9042B 到 `signalAnalyzer` category；配 horn + offset；跑
reference phase。
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
**Gate（= P0-5 acceptance）**：
- attach 成功，记录 IMSI + RRC 状态
- UE Capability 查询 `max_dl_layers >= 配置层数`
- 单方位扫产生**非零**吞吐读数（来自 UXM）
- 4 方位扫给出 **4 个不同**吞吐值（旋转 sanity check）

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
