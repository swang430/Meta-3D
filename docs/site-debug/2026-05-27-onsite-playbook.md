# 5/27 现场攻略 — 打通第一个现场 first-call

> **本文是 5/27 当天的执行手册**，是 [`on-site-debug-protocol.md`](../guides/on-site-debug-protocol.md)
> 的一次性落地版：把通用协议 + CAICT 实测教训 + 截至 5/26 的最新软件改动
> (P1-11/12/13/14/15) 合成一份当天照着走的攻略。
>
> **一句话目标：现场只调硬件 / RF / 校准 / DUT，不写 driver 代码，端到端跑出第一个真 first-call PDF。**
>
> 配套：[`roadmap-first-call.md`](../roadmap-first-call.md) 的 P0-3/4/5；
> [`multi-subnet-instrument-network.md`](../guides/multi-subnet-instrument-network.md) 方案 A。

---

## 0. 整体流程一图

```
出发前(D-1, 在本地)          到场环境准备              现场分阶段执行(gate 不过不进下一步)
─────────────────       ─────────────────       ──────────────────────────────────────
软件链路 mock 跑通    →   网络 bring-up        →   P0  网络/连通 ─┐
driver 冻结打 tag         (方案A 多IP别名)         P1  逐仪表 SCPI 握手
物理清单 + 仪表表         关掉 VPN/代理(★新)       P2  SA 入 HAL (P0-4) ─┐ 参考 TRP
LabProfile 配好          后端+DB 本地起           P3  路损校准+证书(P0-3)─┘ 依赖 P2
cockpit mock 全绿        cockpit 开起来           P4  DUT attach→吞吐(P0-5)
                                                  P5  完整真 first-call → PDF
```

**P0 依赖链 / 推进顺序（WIP=1，一次一个 gate）**：
`P0-4 (SA 入 HAL) → P0-3 (路损校准，需要 SA) → P0-5 (DUT 吞吐)` → 完整 first-call。

---

## 1. 铁律（违反即停）

1. **现场不写 driver 代码。** driver 是出发前本地 mock 跑通的产物。现场冒 driver bug =
   本地验证有洞：记 backlog、能绕则绕，**不当场重写**。
2. **WIP = 1 on P0。** 按 P0-4 → P0-3 → P0-5 推进，一个 gate 过了再进下一个。
3. **Timebox 救火 30 min。** 单仪表/单问题 bring-up 超 30 min 未通 → 标 blocked，转向能推进的，收工 review 再定。别让一个仪表吃掉一天（CAICT 的陷阱）。
4. **区分两类问题：**
   - **software bug**（本地 mock 跑通的现场崩）→ 异常，记 backlog + 截图/日志，**不当场 debug**，绕过继续别的 Phase。
   - **hardware / RF / config / network**（仪表、连线、子网、校准、DUT）→ 合法现场工作，当场解。
   - 判别工具：cockpit 就绪带的 **unreachable vs SCPI-fail** 区分 + 现象。
5. **现场发现 → backlog，不 detour。** 当日格式：`[discovered on-site 2026-05-27 during PhaseN] <一句话>`。
6. **验证手段排序：SCPI 探测 > GUI > RDP。** RDP 是最后手段，不当首选诊断（F64 的 3389 开着，但不靠它）。

---

## 2. 出发前硬门槛（D-1 在本地，不过不出发）

> 这一关是整个攻略的杠杆点。出发前把软件链路彻底走通，现场才可能"只调硬件"。

- [ ] **mock-data first-call (P0-6) 本地端到端跑通**，PDF 报告出得来（`test_commissioning_e2e_p06.py` 绿）
- [ ] **driver 代码冻结**：打 git tag 作为出发基线 —— `git tag onsite-baseline-20260527 && git push --tags`
- [ ] **PR #88 (P1-15 canary) 已 merge 进出发基线**（决定 cockpit 子网面板在有 VPN 时的行为，见 §3-Phase0 ★）
- [ ] **cockpit readiness 在 mock 模式全绿**（驱动链 / 活动 Lab / 校准证书全绿；DUT 灰色 = 已知占位，不算阻塞；子网在 mock 下显示"未探测"= 正常，mock 不探网络）
- [ ] **多子网方案就绪**：读过 multi-subnet 方案 A，IP 别名命令背下来（§3-Phase0）
- [ ] **plan-level preflight validator (P1-1)** 对目标 plan 通过
- [ ] **仪表清单成表**（见下方速查表，逐台填好默认 IP / 子网 / 端口 / 连接模型 / 必需 Test App）
- [ ] **LabProfile 配好**（P0-2 wizard）：目标 chamber 几何 + 32 探头映射就位；active 唯一
- [ ] **物理清单**：备用网线 + Thunderbolt 多口坞（方案 C 兜底）/ horn 天线**含 datasheet TRP 值**（P0-4 gate 要拿它比对）/ 测试 SIM（IMSI 已知）/ 转接头 / 标签
- [ ] **离线可用**：本地能起后端 + **Postgres**，断网现场不依赖云端

### 仪表 bring-up 速查表（出发前填实际 IP）

| 仪表 | 典型子网 | 示例 IP | SCPI 端口 | 连接模型 | bring-up 要点 |
|------|---------|---------|----------|---------|--------------|
| PROPSIM **F64**（信道仿真器） | `192.168.0.x` | `192.168.0.132` | 5025 (SOCKET) | **单 client** | 连之前先确保**没有别的客户端/GUI 占用**；身份查 `SYST:INFO?`（**不是 `*OPT?`/`*IDN?` 之外别指望 MMEM/FTP**）；`-100` = 命令不存在，是正常分类不是 fail |
| **UXM** E7515B（基站仿真器） | `192.168.1.x` | `192.168.1.112` | hislip | 多 client 友好 | 先确认 **5G NR FR1 Test App 已在 UXM 上启动**；endpoint 走 hislip |
| **R&S FSVA3000**（SA 信号分析仪，校准接收端） | `192.168.1.x` | `192.168.1.55` | 5025 / hislip(VXI-11) | — | IDN + 频段确认；P0-4 把它 bind 到 `signalAnalyzer`，**GUI 选 model = `FSVA3000`**（HAL 自动用 `RealRsFsvaDriver`，已注册+seed，无需写 driver）；SCPI 是 R&S FSW/FSVA 命令族（`SENSe:FREQuency:*` / `INITiate:IMMediate;*OPC?`），**不是** Keysight X-Series |
| ENA / VNA | — | — | — | — | 路损校准用 **CE+SA(FSVA3000)**，VNA 非必需（仅无源测试/精密校准备查） |
| RF Switch | — | — | — | — | IDN + 通道切换（如拓扑用到） |
| Aerotech 转台 | — | — | — | — | IDN + **单轴回零/定位**（CAICT 曾卡单轴，本地探针已支持单轴模式） |

> F64 实测约束（CAICT 2026-05-13）：**FTP(21) 关、`*OPT?`/`MMEM:*` 不支持**；要列 F64 上的信道模型文件走 SMB(445)，别走 SCPI。现场不要为这些"操作 F64 文件"的需求停下来 —— 跟 first-call 无关，记 backlog。

---

## 3. 现场分阶段执行（每阶段末一个 go/no-go gate）

### Phase 0 — 网络 / 连通性 bring-up
**目标**：控制 PC 同时够到所有目标子网的所有仪表。

**步骤**：
1. **★关掉 VPN / 公司代理 / 任何透明代理。** 用直连 LAN。
   - 为什么是第一步：P1-15 给 preflight 加了 canary 负对照。如果链路上有 VPN/代理替不可路由地址应答 TCP，cockpit 子网面板会**诚实地标"❔未探测·检测到透明代理/VPN"**，而不是给你假"可达"。这是设计如此 —— 但它意味着**带着 VPN 你就看不到真实子网可达性**。自检：
     ```bash
     cd api-service && .venv/bin/python -c "import asyncio; from app.services.instrument_hal_service import detect_preflight_trustworthy as d; print(asyncio.run(d()))"
     ```
     必须打印 `True`。打印 `False` = 还有代理在通吃，先解决网络再往下走。
2. 给单网卡挂各子网 IP 别名（方案 A，平坑 L2、零硬件）：
   ```bash
   sudo ifconfig en0 192.168.0.10 netmask 255.255.255.0          # 与 F64 同段
   sudo ifconfig en0 alias 192.168.1.10 netmask 255.255.255.0    # 追加 UXM/SA 段(关键:alias)
   ifconfig en0 | grep inet                                       # 应看到两个 inet
   ```
   > 主机位 `.10` 避开仪表已用的 `.132/.112/.55`。两个都挂着，**此后不用再手工切静态 IP**。
3. 逐仪表 TCP 层验证（比 ping 准，有些仪表禁 ICMP）：
   ```bash
   nc -vz 192.168.0.132 5025   # F64
   nc -vz 192.168.1.112 4880   # UXM (hislip 端口按实际)
   nc -vz 192.168.1.55  5025   # SA (R&S FSVA3000)
   ```
4. 起后端 + cockpit，HAL 切 real：`POST /instruments/hal/switch`（real）→ `POST /instruments/hal/reload`。看 cockpit 就绪带 **per-subnet 可达性**面板。

**故障树**：
- 某子网标 **🔴 不可达** → 子网/别名/连线问题：查 `ifconfig` 别名是否真挂上、交换机口、网线。**不是 driver。** 按步骤 2 补别名。
- 子网标 **❔ 未探测·代理/VPN** → 回步骤 1，VPN/代理没关干净。
- 子网 **✅ 可达** 但某仪表 SCPI 无响应 → 留给 Phase 1。

**Gate**：cockpit 就绪带**所有目标子网 ✅ 可达**，canary 自检 `True`，所有目标仪表 reachable。

---

### Phase 1 — 逐仪表 SCPI 握手
**目标**：每个仪表 `*IDN?` ✓ + capabilities 符合声明。

**工具（不是改 driver，不是 RDP）**：
- `POST /instruments/{cat}/test-connection` —— 快速连通+IDN
- `POST /instruments/{cat}/scpi-probe` —— 自开 socket，**不需要已加载驱动**
- 诊断序列（GUI Diagnostics）：`propsim_f64_health` / `uxm_scpi_compatibility` / `vna_ena_health` / `aerotech_positioner_health` / `instrument_idn_sweep`
- `cd api-service && .venv/bin/python -m scripts.driver_selftest` —— 看 HAL 加载态

**逐仪表要点**：F64 单 client（先清占用）/ UXM Test App 已起 / SA 频段 / 转台单轴回零。

**故障树**：
- **IDN 超时但 TCP 通** → SCPI 层：仪表忙 / Test App 没起 / 单 client 被占用。**不是网络，不是 driver bug。**
- 命令返回 `-100`/`-109`/`-113` → 该命令在此仪表不存在（F64 PROPSIM quirk），查 capabilities 用替代命令，别当 fail。
- 跑诊断探针时若提示 **"当前是 mock 驱动…对 mock 无意义"**（P1-14）→ 说明该 category 还在 mock，没真连上。回 Phase 0/HAL 切 real，别在 mock 上空跑硬件探针。
- 连接随后 **idle-close** → 周期 poke 保活，记录现象喂 P2-4，**不要**当 driver 重连 bug 去改代码。
- 排查顺序始终 **SCPI 探测 > GUI > RDP**。

**Gate**：所有目标仪表 `*IDN?` ✓、capabilities 符合、HAL readiness 对应行 `ok`。

---

### Phase 2 — SA 入 HAL（= P0-4）
**目标**：真 SA 读参考 TRP，替掉 `_MOCK_TRP_DBM`(23.5 dBm) 假值。

**步骤**：在 GUI 把 `signalAnalyzer` category 的 model 选成 **`FSVA3000`**（HAL 自动绑 `RealRsFsvaDriver`）→ 配 horn + offset → `POST /instruments/hal/reload` → 跑 reference phase。
> driver 已注册 + seed（`signalAnalyzer→FSVA3000→RealRsFsvaDriver`），**现场不需写/改 driver**；选错成 Keysight X-Series 会用错 SCPI 命令族，IDN 阶段就会暴露。

**Gate（= P0-4 acceptance）**：
- `signalAnalyzer` driver loaded（readiness 表 ✓）
- reference phase 日志 `measurement_source: "hal_signal_analyzer"`（**不是** `"mock"`）
- measured TRP 在 horn datasheet TRP **±1 dB** 内

> 注意（P1-12）：若 reference 还在用兜底值，commissioning 会显著标 **"未验证(兜底值)"**。看到这个标记 = 还没真测到，gate 没过，别往下走。

---

### Phase 3 — 路损校准（= P0-3）+ 证书
**目标**：CE+SA 跑完 **32 链路**路损校准，出 CalibrationCertificate。

**步骤**：CE 出 tone → SA 收功率 → 逐链路 → 生成 cert。commissioning precheck 应看到 cert **停止 warning**（P1-8 gate）。

**Gate（= P0-3 acceptance）**：
- cert 含全部 **32 链路**，`path_loss_db_by_rf_chain` 全非零
- `overall_pass = True`
- `valid_until > now()`（典型 +30 天）
- precheck phase 看到 cert 不再 warn（P1-8 strict gate 通过）
- **重复测一次，路损值在 ±0.5 dB 内**（可重复性 —— 这条最容易被省，别省）

> P1-8 是 runtime gate：strict = (config flag AND hardware real)。real 模式 + cert 缺失会 **fail-loud 拦住**，不会让你拿垃圾数走完。看到 fail-loud 是好事，按提示补 cert。

---

### Phase 4 — DUT attach → bearer → PDSCH（= P0-5）
**目标**：真 DUT 接入 UXM，跑真吞吐。

**步骤**：DUT 入舱 → `POST /test-executions/{id}/attach-dut`（记 IMSI + RRC）→ UE capability 查询 → 单方位扫吞吐 → 4 方位扫。

**故障树**：attach 失败 → 先看 **P1-9 DUT-attach fail-loud gate** 报的原因（RRC 未连 / IMSI 缺失），按提示修配置（SIM/Test App/小区参数），**不是 driver**。

**Gate（= P0-5 acceptance）**：
- attach 成功，记录 IMSI + RRC 状态
- UE Capability 查询 `max_dl_layers >= 配置层数`
- 单方位扫产生**非零**吞吐读数（来自 UXM）
- 4 方位扫给出 **4 个不同**吞吐值（旋转 sanity：转台真的在改链路）

---

### Phase 5 — 完整真 first-call
**目标**：端到端真 first-call，出 PDF。

**步骤**：跑完整 plan（precheck → reference → measure → analysis → report），所有 fail-loud gate 通过。

**Gate**：first-call **PDF 生成**；cockpit 全绿；报告里**没有 "未验证(兜底值)" 标记**（P1-12 —— 有标记 = 某段还在用假值，不算真 first-call）；关键指标在合理范围。

---

## 4. 现场避坑速查（高频踩点，集中放这）

| 现象 | 真因 | 处置 |
|------|------|------|
| cockpit 子网"❔未探测·代理/VPN" | 链路有 VPN/透明代理（P1-15 canary 拦住） | **关 VPN/代理**，跑 canary 自检到 `True`，再 reload HAL |
| 子网"✅可达"但你怀疑没设备 | 若 canary=True 这是真可达；若带着代理则面板本就会标未探测 | 先确认 canary=True 再信"可达" |
| `F64 ✓ + UXM ✗` 交替 | 单网卡只在一个子网 | 方案 A 挂双子网别名，**别手工切静态 IP** |
| `-1073807339` / VI_ERROR_TMO 单仪表 | 八成子网不可达 | `nc -vz` 确认网络层，补别名；**不是 HAL bug** |
| `nc` 通但 `*IDN?` 不应答 | SCPI 会话层（仪表忙 / 单 client 占用 / Test App 没起） | 清 F64 其他客户端 / 起 UXM Test App；不碰 driver |
| F64 SCPI 返回 `-100` | PROPSIM quirk：命令不存在 ≠ 标准错误 | 当 UNSUPPORTED 分类，换替代命令；不当 fail |
| 探针提示"mock 驱动对探针无意义" | 该 category 还在 mock，没真连 | 切 real + reload，别在 mock 上空跑硬件探针 |
| 想列 F64 信道模型文件 | F64 FTP(21) 关、MMEM SCPI 不支持 | 走 SMB(445)，**且这跟 first-call 无关，记 backlog 别停** |
| reference/report 出现"未验证(兜底值)" | 还在用 mock/兜底，没真测到 | gate 没过，回对应 Phase 真测；不是显示 bug |
| 连上后过一会断开(idle-close) | NAT/FW idle drop 假设(P2-4) | 周期 poke 保活 + 记现象；**不改重连代码** |
| Aerotech 单轴卡住 | CAICT 老问题 | 探针单轴模式回零/定位；超 30 min 标 blocked |

---

## 5. 每日收工 review（15 min）+ 升级阈值

**三问**：① 今天该推进哪个 Phase、实际到哪个 gate？ ② 卡点是 hardware/RF/config/network（合法）还是 software（异常=本地验证有洞）？ ③ 明日 Current Focus = 哪个 Phase？阻塞项记 backlog 了吗？

**产出**：当日 backlog 行 + 明日计划 + 已过 gate 记录。

**升级阈值**：
- 单 gate 卡 **>半天** 且非纯物理硬件问题 → 停，整理现象 + SCPI trace，远程协作，不死磕。
- 出现 **software bug**（本地 mock 跑通的现场崩）→ 立即记 backlog + 截图/日志，绕过该路径继续别的 Phase。**绝不**当场 debug 吃掉现场时间。

---

## 6. 命令 / 端点速查

```bash
# —— 网络 ——
sudo ifconfig en0 192.168.0.10 netmask 255.255.255.0
sudo ifconfig en0 alias 192.168.1.10 netmask 255.255.255.0
nc -vz <ip> <port>

# —— canary 自检(关 VPN 后必须 True) ——
cd api-service && .venv/bin/python -c "import asyncio; from app.services.instrument_hal_service import detect_preflight_trustworthy as d; print(asyncio.run(d()))"

# —— HAL 加载态 ——
cd api-service && .venv/bin/python -m scripts.driver_selftest
```

| 端点 | 用途 |
|------|------|
| `POST /instruments/hal/switch` | mock ⇄ real 切换 |
| `POST /instruments/hal/reload` | 重新初始化 HAL（重跑 preflight + readiness 快照） |
| `GET  /instruments/hal/readiness` | 就绪快照（cockpit 数据源；**是缓存快照**，改了网络要 reload 才刷新） |
| `POST /instruments/{cat}/test-connection` | 单仪表连通 + IDN |
| `POST /instruments/{cat}/scpi-probe` | 自开 socket SCPI 探测（不需已加载驱动） |
| `POST /test-executions/{id}/attach-dut` | DUT attach（记 IMSI+RRC） |

> ⚠ readiness 是**缓存快照**：现场改了子网别名 / 切了 mock↔real，**必须 `POST /instruments/hal/reload`** 才会重新探测刷新，否则 cockpit 显示的是上次 init 的旧值。

---

## 7. 收工后 retro → 喂回 roadmap

- 现场暴露的 software 洞 → triage 成本地 P-item（**下次出发前补**，不留到下次现场）。
- 现场完成的 P0 标 ✅ Done + 记 acceptance 验证结果（P0-4 → P0-3 → P0-5）。
- 更新 roadmap on-site 队列 + Summary counts；Current Focus 按链推进。
- 写一篇 trip retro（仿 `docs/site-debug/2026-05-13-retrospective.md`），记 drift 程度 + 原因属铁律 1-6 哪一类。
