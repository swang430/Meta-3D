# 现场首测执行计划 — 信道模型下测吞吐量（2026-07-02）

> 本计划**不替代** [`on-site-debug-protocol.md`](on-site-debug-protocol.md)（铁律 + Phase 0–5 go/no-go gate），
> 而是把它**聚焦到明天的具体目标**：让暗室首测在**一个信道模型下测出下行吞吐量**，并叠加
> S4 / deprecate-legacy 刚落地的 **ChannelAsset 信道资产链路**的现场要点。

## 0. 目标（今天定义清楚，现场就不飘）

一次成功 = 一个 TestCase「MIMO_OTA 步骤」引用一个**信道资产（ChannelAsset）** →
F64 真加载该信道模型 → UXM 对真 DUT 测下行吞吐 → **4 方位扫出 4 个不同吞吐值**（旋转 sanity）。

这正好是 **P0-5 acceptance**（真吞吐 + 旋转 sanity）叠加**信道模型注入验证**。

## 1. 今晚出发前硬门槛（不过不出发 —— 整个协议的杠杆点）

沿用 protocol §2，**新增信道资产链路 3 项**（★ 是本次新增，其余见 protocol §2）：

- [ ] mock-data first-call（P0-6）本地端到端跑通，PDF 出得来
- [ ] ★ **信道模型链路本地走通**：信道工作台建 **① 一个 `vendor_file`（GCM `.smu`）+ ② 一个 `standard_3gpp`（ASC）** 资产 → 一个 TestCase 的 MIMO_OTA 步骤用「统一信道资产」引用它 → mock measure 跑通 → 确认 `resolve_channel_asset` 派生的 `engine_mode` 正确（vendor→`GCM_NATIVE` / standard→`ASC_SYNTHESIS`）。**这条今晚必须在本地点一遍**（S4-5/deprecate-legacy 刚落地，现场第一次真用）。
- [ ] ★ **确认信道资产的频率与 TestCase 频率一致**：GCM `.smu` 频率编码在文件里，TestCase 频率 ≠ .smu 频率 → measure 频率一致性网 fail-loud（P2-11）。今晚把要用的 .smu 频率与 TestCase 频率对齐。
- [ ] ★ **确认 F64 上有对应频率的 `.smu` 文件**：GCM 路 F64 从 `D:\User Emulations\` 加载真 .smu（默认 3600M 4x4）。首测频率若不是 3600M，现场要么有对应 .smu，要么改用 ASC 合成路。
- [ ] driver 冻结 + `git tag onsite-baseline-20260702`
- [ ] cockpit readiness 在 **mock 模式全绿**（驱动链 / 活动 Lab / 校准证书；DUT 灰 = 占位不算阻塞）
- [ ] 仪表清单表：F64 `192.168.0.x:3334`（单 client SOCKET）/ UXM `192.168.1.x`（Test App 要起）/ SA `192.168.1.x` FSVA3000
- [ ] LabProfile 配好（**今天修了 LabProfileWizard 崩溃 bug**，wizard 可用了）
- [ ] plan-level preflight（P1-1）对目标 plan 通过
- [ ] 物理清单：horn 天线（含 datasheet TRP）/ 测试 SIM / 备用线缆 / 转接头

## 2. 现场 Phase 序列（每 gate 不过不进下一）

完全按 protocol §3 的 Phase 0–5，下面只标**信道模型/吞吐相关的落点**：

| Phase | 目标 | 信道/吞吐落点 | Gate |
|---|---|---|---|
| **0 网络** | 控制 PC 够到 3 子网 | F64 端口 **3334**（**不是** 5025）；`nc -vz 192.168.0.x 3334` | 3 子网全可达 |
| **1 SCPI 握手** | 各仪表 `*IDN?` ✓ | F64 身份查 `SYST:INFO?`（**不是** `*OPT?`）；UXM **Test App 先起**（5G NR FR1）；SA IDN | 全 IDN ✓ + capabilities 符合 |
| **2 SA 入 HAL（P0-4）** | 真 SA 读参考 TRP | GUI 把 signalAnalyzer model 选 FSVA3000 | measured TRP 在 horn datasheet ±1 dB |
| **3 路损校准（P0-3）** | CE+SA 跑 32 链路 → cert | cert 让 measure 的 RSRP 基线补偿生效；关掉 cal warning | cert 32 链路 + `overall_pass` + 重复 ±0.5 dB |
| **4 DUT attach（P0-5）** | 真 DUT 接入 UXM | 真吞吐的前提；UE capability 层数 ≥ 配置层数 | attach ✓ + 单方位**非零**吞吐 |
| **5 信道模型下测吞吐（★核心）** | 见下方展开 | — | 4 方位 **4 个不同**吞吐值 + PDF |

### Phase 5 展开（本次核心 —— 信道模型注入 + 吞吐）

1. **切 Real 驱动模式**：仪器资源配置页把 F64/UXM/SA 从「仿真模拟(Mock)」切 **Real**（见 §3 风险①，别忘）。
2. **备/选信道资产**：信道工作台确认要用的资产在（首测建议 **GCM `.smu`（vendor_file）**，理由见 §4）。
3. **TestCase 引用**：测试管理 → 步骤编排 → MIMO_OTA 步骤 →「统一信道资产」选它（会禁用下方传统信道字段并提示「按 source_type 派生引擎 + 覆盖」）。
4. **跑 measure**：
   - resolve_channel_asset → engine_mode（vendor→GCM）
   - F64 `load_channel(NATIVE_MODEL)` → SCPI `CALC:FILT:FILE <.smu>` 真加载
   - UXM `set_cell_config`（显式 ARFCN，P2-11）→ `start_signaling` → `measure_throughput_window`（SCPI `MEAS:BTHROUGHPUT:DL:JSON?`）
   - 转台逐方位 `move_to(azimuth)` → 每方位读吞吐
5. **验收 sanity**：4 方位吞吐值应**不同**（旋转改变空间信道实现）；若 4 个值全相同 → 疑 mock 未切 Real（见 §3 风险①）或信道未真加载。

## 3. 第一次真跑风险序列（按 likelihood × impact）

| # | 风险 | 第一症状 | 排查（SCPI 探测 > GUI > RDP） | 修复 |
|---|---|---|---|---|
| **①** | **忘切 Real，跑的是 Mock 驱动** | 吞吐固定 ~200 Mbps、4 方位**全相同**、无视信道 | 仪器页看是否「仿真模拟」；cockpit 驱动标 mock | 切 Real 模式 + reload HAL；strict gate 打开会自动拦「无真校准就测」 |
| ② | UXM Test App 未起 | precheck 显示 UXM 在线但 SCPI 超时 | Phase 1 IDN 探测 | 重启 Test App（5G NR FR1） |
| ③ | F64 端口 3334 被占/防火墙/单 client 被 GUI 占 | F64 connect timeout | `nc -vz 192.168.0.x 3334` + 确认无别的客户端占 F64 | 释放端口/关占用 GUI |
| ④ | `.smu` 文件缺失或频率不符 | measure `CALC:FILT:FILE` 返回 -200/-300，或频率一致性网 fail-loud | 查 F64 `D:\User Emulations\` 有无对应频率 .smu | 上传 .smu / 改 TestCase 频率对齐 / 改走 ASC |
| ⑤ | DUT 未 attach 或 RRC 断 | P1-9 DUT gate fail 或吞吐 = 0 | P1-9 gate 报的原因（RRC/IMSI） | 重新 attach，按 gate 提示改配置（**不是 driver**） |
| ⑥ | 路损 cert 缺失 | RSRP/吞吐基线异常低 + cal warning | precheck cal gate | 跑 Phase 3 校准 |
| ⑦ | 连接 idle-close（P2-4 NAT/FW） | 一段时间后 SCPI 断 | 周期 poke 保活 | 记 P2-4 backlog，**不当 driver bug 改** |

## 4. 首测信道模型选型建议（重要）

- **首选 GCM `.smu`（`vendor_file` 资产）** —— F64 加载内置真 .smu，**不依赖 channel-engine-service**，硬件路最短、变量最少。适合首测「先跑通」。
- **ASC 合成（`standard_3gpp` / `custom_static`）作进阶** —— 需 channel-engine-service 网络可达 + FTP 上传 `.rtc` 到 F64。多一层依赖，首测通过后再验。
- **`rt_dynamic` 多快照**现场**不可执行**（resolver 对多快照 fail-loud，轨迹执行是 P2-16 S5）；单快照 rt_dynamic 可走 B-2 参数化，但仍属进阶。首测别用。

## 5. 铁律（禁区 —— 违反即停）

- **现场不写 driver 代码**：bug 记 `[discovered on-site 2026-07-02 during PhaseN] …`，能绕就绕别的 Phase。
- **单 gate 卡 > 半天且非纯硬件物理问题** → 停下，整理 SCPI trace，远程协作。**绝不**当场吃时间 debug（CAICT 陷阱）。
- **排查顺序 SCPI 探测 > GUI > RDP**，不靠 RDP。
- **卡点归类**：hardware/RF/config/network = 合法；**software 异常 = 本地验证有洞**（说明出发前门槛没做足）。

## 6. 收工 review（15 min）

三问（protocol §4）：今天到哪个 gate？卡点是硬件（合法）还是软件（异常）？明日 Phase？
产出：当日 `[discovered on-site …]` backlog 行 + 明日计划 + 已过 gate 记录 → 喂回 roadmap。

---

**一句话**：本地软件链路（含新的 ChannelAsset 信道注入）**今晚点一遍确认全绿 + driver 冻结**；现场按 Phase 0→5 走，**核心是 Phase 5 用 GCM .smu 信道资产 + 真 DUT 测出 4 方位不同吞吐**；第一大坑是**忘切 Real 跑成 mock**。
