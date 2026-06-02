# TestCase 驱动的仪表配置下发架构

> 2026-05-30 确立。来源:P1-17(UXM 默认 profile)+ ARFCN review 之后,用户提出的
> 架构级问题 —— "测试例应该来驱动 UXM、F64 使用什么样的联动配置来进行测试"。本文
> 把这个原则确立成架构契约,并划清它跟"暗室首测走捷径"的边界。

---

## 1. 核心原则:TestCase 是测试配置的单一真值源

正式测试时,**TestCase(`MIMOOTAConfiguration`)是唯一真值源**,驱动整个仪表层级的
配置下发。频率 / MIMO / 信道模型 / 功率 / 方位角等参数在 TestCase 里定义一次,然后
**逐级下发**到每一台参与测试的仪表,并在下发后**校验多方一致**。

没有"某台仪表自己有个默认频率"这回事 —— 任何仪表的工作参数,要么来自 TestCase,
要么(在 bring-up 场景)来自显式声明的默认 fallback,绝不能"半 TestCase 半默认"地
静默拼出一个错配的链路。

### 1.1 频率的规范标识 = 中心频点 ARFCN + 带宽 (用户 2026-05-30 确立)

**系统中频率的规范标识是「中心频点 ARFCN + 带宽」,不是 `frequency_mhz`。**

- **ARFCN 是 3GPP TS 38.104 标准定义的整数** channel number, 精确 → **根本没有浮点
  "容差"问题**。容差恰恰是"用近似 MHz 而非标准 ARFCN"混出来的。
- **中心频点** (不是起始/边缘频率), 带宽单独标识。
- 系统里**所有仪表** (UXM cell / F64 .smu / SA center) 都归一到 `(中心 ARFCN, 带宽)`
  再比对。

`frequency_mhz` 是给人看的**派生视图**, 不是真值。这同时是 P1-17 ARFCN bug 的根本解:
那个 bug (profile 标称 `frequency_mhz=3600` 但实际下发 ARFCN→3489) 正是因为没拿
ARFCN 当真值。工具 + 规范标识类见 `app/hal/nr_arfcn.py` (`freq_mhz_to_nr_arfcn` /
`FrequencyIdentity`)。

## 2. 两条路径的切分(关键)

系统有两条**正交**的配置路径,边界必须清楚,不能混用:

### 路径 A — bring-up / 暗室首测(无 TestCase)
```
HAL-init / fresh-start → connect → 默认仪表配置
  F64: 默认 .smu (F64_DEFAULT_EMULATION_FILE, 3600M)      ← P0-8 Step 4
  UXM: 默认 topology profile (caict_n78_3600_4x4)         ← P1-17
  ...其它仪表的默认基线
```
- **价值**:暗室首测 / 手动调试 / readiness 验证时"开机即就位到一个**被确认工作**的
  已知基准"。这正是 P0-8 选 3600M .smu 的初衷 —— 需要一个真机验证过的配置当锚点。
- **允许走捷径**:此路径不需要 TestCase,默认配置就是为了快速到一个能动的状态。
- 默认配置之间**必须自洽**(F64 默认 .smu 频率 == UXM 默认 profile 频率 == 3600M),
  否则连 bring-up 基准本身都是错配的(这就是 P1-17 新建 3600M profile 对齐 F64 的原因)。

### 路径 B — 正式测试(有 TestCase)
```
TestCase (单一真值源) → executor → 逐级下发 + 一致性校验
  UXM:        set_cell_config(TestCase.cell)          → ARFCN/band/BW/MIMO/power
  F64:        channel config from TestCase            → .smu(GCM) / .asc(ASC) + topology
  SA:         setup_spectrum(TestCase.frequency)      → center/span
  positioner: move_to(TestCase.azimuths)              → 方位角栅格
  switch:     topology from TestCase                  → RF 通路 mode
  信号源/VNA: 干扰/校准 from TestCase                  → (未来)
  ───────────────────────────────────────────────────
  ✅ 下发后校验: 所有仪表关键参数(尤其频率)互相一致 + 跟 TestCase 一致, 否则 fail-loud
```
- **默认配置在此路径不参与**。有 TestCase 就必须 TestCase 驱动到底。
- 任何"TestCase 没指定 → fallback 默认"的地方都是**潜在错配点**(默认可能跟 TestCase
  其它参数不同频),必须要么补成 TestCase 驱动,要么 fallback 时 fail-loud 警告。

## 3. 仪表层级下发:现状 vs 目标

调研 `app/services/mimo_ota/executors/` 后的当前覆盖(2026-05-30):

| 仪表 | TestCase 驱动现状 | 缺口 |
|------|------------------|------|
| **UXM** (baseStation) | ✅ `set_cell_config(TestCase.component_carriers[0])` | ARFCN 一致性(P1-17 已补显式 arfcn)|
| **positioner** (转台) | ✅ `move_to(TestCase.azimuths_deg)` | — |
| **SA** (signalAnalyzer) | ✅ `setup_spectrum(TestCase.frequency_hz)` (reference phase) | — |
| **F64 ASC** (`mimo_first_asc`) | ✅ channel-engine-service 按 `frequency_hz` 生成 .asc | — |
| **F64 GCM** (`keysight_gcm`) | ✅ **P2-11 Phase 2 已补**: `emulation_file` 字段 + `sim_rules` 透传 + GCM 严格门 (真 F64 未指定 → fail-loud) | — (mock-aware: bring-up 路径 A 走默认; 正式测试 fail-loud) |
| **switch** (rfSwitch) | ✅ **P2-11 Phase 3 已补**: `orchestrate_switch_topology(chamber, mode_id=TestCase.switch_mode_id)` + `precheck_strict_switch_mode` 门 (有拓扑但请求 mode 不提供 → fail-loud; 无拓扑/固定布线 → warn) | — (`mode_id` 不再硬编码 "mimo_ota") |
| **信号源 / VNA** | ❌ executor 未接 | 干扰生成 / 在线校准未纳入 (Phase 4) |

**GCM 缺口已闭合**(P2-11 Phase 2,原"两个硬证据"已解):
- ~~`MIMOOTAConfiguration` 没有 `emulation_file` 字段~~ → **已加** `emulation_file` + `precheck_strict_emulation_file`。
- ~~`measure.py` 的 `sim_rules` 没 emulation_file~~ → **已透传**(`config.emulation_file` → `sim_rules["emulation_file"]` → F64 GCM)。
- 历史后果(GCM TestCase 3500 / F64 默认 3600 静默打架)现双重拦截:**Phase 1** 频率一致性门当场抓错配,**Phase 2** 严格门让正式 GCM 测试必须 TestCase 驱动 .smu(真 F64 未指定 → measure FAIL,不静默 fallback)。bring-up(路径 A)经 `precheck_strict_emulation_file=False` 或 mock-aware 走默认。

## 4. 一致性校验是安全网(不管谁驱动,最后都拦)

无论配置来自 TestCase(路径 B)还是默认(路径 A),measure/precheck 都应该有一道
**多方一致性 fail-loud 校验**:

```
assert UXM_cell_frequency(ARFCN) ≈ F64_channel_frequency(.smu/.asc) ≈ SA_center ≈ TestCase.frequency
  否则 → FAIL "instrument frequency mismatch: UXM=X, F64=Y, TestCase=Z"
```

这是防"静默错配"的最后防线 —— 跟 P1-8(cal gate)/ P1-9(DUT gate)/ P1-12(未验证
标记)同族的 silent-failure 防护。**它甚至比 GCM 联动更优先**:联动是"把参数传对",
校验是"传错了也能当场抓住",后者保护测试结果的可信度。

## 5. 为什么 GCM 优先

用户 2026-05-30 明确:**GCM 是首先要测的**。GCM 路径用 F64 的 .smu(Channel Studio
vendor 预生成,频率固定在文件里),目前完全没被 TestCase 驱动。所以"TestCase → F64
GCM .smu 联动"不是"看现场用哪个模式才决定做不做",而是**首要缺口**。

GCM .smu 联动的实现方向(择一或组合):
- `MIMOOTAConfiguration` 加 `emulation_file` 字段,`sim_rules` 透传(显式)。
- 或建 `frequency → .smu` 库映射,TestCase 频率自动选对应 .smu(更自动,但需 .smu 资产盘点)。
- 关键:GCM 路径不再 fallback 默认 .smu;真没匹配时 fail-loud(不静默用错频率)。

## 6. 跟 bring-up 默认配置(P0-8 / P1-17)的关系 —— 不推翻

P0-8(F64 默认 .smu)+ P1-17(UXM 默认 profile)**是路径 A 的实现,正确且保留**。它们
是 bring-up fallback,**不是测试驱动**:
- P1-17 的默认 profile 只在 HAL-init 用;measure phase(路径 B)走 `set_cell_config(
  TestCase)`,**不 apply topology profile**。两条路径天然分开,不冲突。
- 本架构补的是**路径 B 的 F64 GCM 联动 + 多方一致性校验**,以及未来把 switch / 信号源
  纳入 TestCase 驱动。

一句话:**默认配置 = bring-up 锚点(走捷径);TestCase = 测试驱动(架构正道)。两者
并存,边界清楚。**

### 6.1 路径 A/B 边界代码锚点(P2-11 Phase 5 固化)

防认知漂移:**加新仪表默认前先问"这是路径 A 还是 B";加新仪表参数前先问"路径 B 有没有
从 TestCase 驱动它 + fail-loud 校验它"。** 边界在代码里的锚点(均已加 `路径 A/B 边界`
注释指回本文档):

**路径 A — bring-up 默认(在 HAL-init / 手动调试用)**:

| 默认 | 代码锚点 | path B 隔离 |
|------|---------|------------|
| F64 默认 .smu(3600M)| `app/hal/propsim_f64.py` → `F64_DEFAULT_EMULATION_FILE`(P0-8)| ✅ 干净:measure 由 `emulation_file` 覆盖 |
| UXM 默认 topology profile | `app/services/instrument_hal_service.py` → `_initialize_from_db` 的 `_default_topology_profile_id` fallback(P1-17)| ⚠️ **不完全**:见下方 leak |

> ⚠️ **已知 leak(Codex on PR #112,roadmap "Discovered" backlog)**:UXM 默认 profile 经 `apply_topology_profile → set_cell_config(to_config_dict())` 在 HAL-init 把 `mimo_port_preset` / `tdd_pattern` / `sched_algo` / `csi_rs_ports` 落到硬件。measure(path B)的 `set_cell_config` 只传 frequency/ARFCN/BW/SCS/band/`mimo_layers`/power,**不覆盖上述 profile 字段** → 它们**残留**进正式测试(如 2x2 TestCase 跑在残留的 4x4 端口路由上)。待补成 TestCase 驱动或 measure 显式 reset。**这正是"加新仪表参数前先问 path B 有没有驱动它"准则要防的——port routing / TDD / scheduler 当前没被 path B 驱动。**

**路径 B — TestCase 驱动(measure executor,全从 `MIMOOTAConfiguration` 派生)**:

| 仪表参数 | TestCase 字段 → 下发点 | fail-loud 门 |
|---------|----------------------|-------------|
| UXM 频率 / MIMO | `frequency_hz`→ARFCN / `mimo_layers` → `set_cell_config` | `precheck_strict_frequency`(Phase 1)|
| F64 GCM .smu | `emulation_file` → `sim_rules` → F64 | `precheck_strict_emulation_file`(Phase 2)|
| switch RF 通路 | `switch_mode_id` → `orchestrate_switch_topology` | `precheck_strict_switch_mode`(Phase 3)|
| 路损 cert | `switch_mode_id` → `get_latest_calibration(operating_mode=)` + `_query_calibration_entries` | 随 switch mode 过滤(Codex on #111)|
| SA / positioner | `frequency_hz` / `azimuths_deg` → setup/move | —(同源)|

measure executor(`app/services/mimo_ota/executors/measure.py`)docstring 顶部有路径 B 总览。

## 7. 分阶段实施(建议)

| 阶段 | 内容 | 性质 | 优先 |
|------|------|------|------|
| **1** ✅ | 多方频率一致性 fail-loud 校验(measure) — **已实现 (P2-11 Phase 1)**: `nr_arfcn.py` 工具 + 各 driver `get_frequency_identity()` 归一到 (中心 ARFCN, 带宽) + `frequency_consistency.check_*` 精确比对 + measure phase `precheck_strict_frequency` gate | silent-failure 防护,本地可做,小 | ⭐ 最先(保护测试可信度)|
| **2** ✅ | TestCase → F64 GCM .smu 联动 — **已实现 (P2-11 Phase 2)**: `MIMOOTAConfiguration.emulation_file` 字段 + measure `sim_rules` 透传 + `emulation_file_gate.evaluate_*` 严格门 (`precheck_strict_emulation_file`, mock-aware, 真 F64 未指定 → fail-loud 不静默 fallback) + result_payload `.smu` 来源 audit | GCM 优先 | ⭐ 高 |
| **3** ✅ | switch topology 纳入 TestCase 驱动 — **已实现 (P2-11 Phase 3)**: `MIMOOTAConfiguration.switch_mode_id` 字段 (默认 "mimo_ota", 不再硬编码) + measure 透传给 `orchestrate_switch_topology` + `switch_mode_gate.evaluate_*` 门 (`precheck_strict_switch_mode`, 有拓扑但请求 mode 不提供 → fail-loud; 无拓扑/固定布线 → warn) | 架构补全 | 中 |
| **4** | 信号源 / VNA 纳入 TestCase 驱动(干扰 / 在线校准)| 架构补全 | 低(按需)|
| **5** ✅ | 默认配置角色文档化 + 路径 A/B 边界在代码注释固化 — **已实现 (P2-11 Phase 5)**: §6.1 代码锚点地图 + propsim_f64 / instrument_hal_service / measure docstring 三处 `路径 A/B 边界` 注释 | 防认知漂移 | 贯穿 |
| **6** ✅ | **一致性网从频率扩到 DL 吞吐链** — **已实现 (P2-11 Phase 6)**: `RealUxmDriver.get_applied_cell_config()` 读 **UE 协商能力** `max_dl_layers` + `cell_config_consistency.check_*` 判**请求层数 > UE 上限 → fail** + measure `precheck_strict_cell_config` 门 (UE 未 attach/mock → skip)。**首条线: DL MIMO layers**。⚠️ Codex on PR #114: 读 UE 能力**不读** `CONF:...:LAY?` 配置旋钮 (后者回读只原样返回配置值, 抓不到 UE 把 4 层 clamp 到 2)。MCS (受 AMC 浮动) / DL power (InputLevelController 闭环合法改) 留延伸, 见 §8。 | silent-failure 防护(频率同族)| ⭐ 高(Phase 1 自然延伸)|

## 8. 核心参数驱动审计(2026-05-31)— A/B/C/D 分类 + Phase 6 一致性网

> 用户 2026-05-31 问:"暗室首测捷径检查后,除了频率一致,测试中还有哪些核心参数需要
> 系统级兜底、由测试例驱动?" 本节是对 DL 测量链**每个核心参数**驱动状态的全审计。

**判据**:该参数 (1) 从哪来(TestCase / chamber 物理 / HAL 默认 / 硬编码);(2) 不一致会不会
**静默污染测试结果**(= 是否需要 fail-loud)。

### A 类 — ✅ 已 TestCase 驱动 **+ fail-loud 一致性**(P2-11 Phase 1-3 成果)

| 参数 | 机制 |
|------|------|
| 频率 ARFCN **+ 带宽** | Phase 1(identity = ARFCN + BW,带宽一并覆盖)|
| F64 .smu(GCM)| Phase 2 |
| switch RF 通路 mode | Phase 3 |
| 路损 cert(mode + freq 过滤)| Codex on #111 |

### B 类 — ⚠️ 已 TestCase 驱动,**但无"下发后回读校验"**(频率有,这些没有)

| 参数 | 下发 | 回读校验 |
|------|------|---------|
| `mimo_layers` | `set_cell_config` | ✅ **Phase 6 已补**: 读 UE 协商能力 `max_dl_layers`, 请求 > UE 上限 → fail (`precheck_strict_cell_config`)。读 UE 能力**非** `CONF:LAY?` 配置旋钮 (Codex #114) |
| `modulation` / `mcs` / `enable_amc` | throughput 参数下发 | ⬜ 待补(AMC on 时 MCS 浮动 → 仅 AMC off 可回读校验)|
| `tdd_pattern` / `harq_*` | throughput 参数下发 | ⬜ 待补 |
| `target_tx_power_dbm`(→DL power)/ `rsrp` / `snr` | `set_downlink_power` / `sim_rules` | ⬜ 待补,**但有坑**: InputLevelController(Phase 2b)闭环会合法改 UXM DL power,"功率==target" 会误杀;且 RSRP 当前模拟。需结合操作点 backlog 一起设计 |

> **B 类是个"类"问题,不是单点**:这些参数跟频率**同等决定吞吐**,但只 fire-and-forget 下发。
> 一个静默 clamp 的 MCS、一个没到 target 的 DL 功率 = 吞吐测错而无人报警 —— 跟频率错配**同等
> 危害,却无同等防护**。这正是 **Phase 6** 要补的。

### C 类 — ❌ 系统级兜底 / 泄漏,**未 TestCase 驱动**(真缺口,均已 backlog)

| 参数 | 现状 | backlog |
|------|------|---------|
| **MIMO 端口路由** `mimo_port_preset` / `csi_rs_ports` / `sched_algo` | UXM profile 在 HAL-init 设,`MIMOOTAConfiguration` 无对应字段,measure 不驱动也不 reset → 残留进 path B(2x2 TestCase 跑在残留 4x4 路由)| Discovered(Codex #112)🔴 高影响 |
| **操作点 / F64 输入参考**(avg 电平 + crest)| 仪表限值(`upper − 15dB`)+ 硬编码偏移(`-10` 起手 / `-30` burst)驱动,非 TestCase,且不跟 `target_tx_power` 交叉校验 | Discovered 2026-05-28(feed-forward + imbalance)🔴 CAICT 现场 0% ACK 根因 |

### D 类 — 🟢 **设计上就不该** TestCase 驱动(物理量,正确)

chamber 几何 / 探头位置·方向图 / SGH 参考天线 / DUT(SIM·IMSI)= 物理 · LabProfile · 操作员,
不进 TestCase。校准证书 = TestCase 可绑定 + LabProfile 兜底 + P1-8 strict gate,合理。

### Phase 6 — 一致性网扩展(B 类的解药)✅ 首条线已实现

Phase 1 给**频率**做了"下发后**回读**(`get_frequency_identity`)+ 精确比对"。Phase 6 把这张网扩到
B 类。**已实现的首条线 = DL MIMO layers**:

- `RealUxmDriver.get_applied_cell_config()`:读 **UE 协商能力** `query_ue_capability().max_dl_layers`
  → `AppliedCellConfig`(UE 未 attach / firmware 不支持 UEINFO / mock → None,跳过,同 Phase 1 mock-skip)。
- `app/services/mimo_ota/cell_config_consistency.check_cell_config_consistency`:判
  **TestCase 请求层数 > UE 能力上限 → fail**。
- measure 在 set_cell_config + RRC reconfig 后调用,`precheck_strict_cell_config` 门(默认 True)。
- **抓什么**:UE 撑不住请求层数时 UXM 把请求的 4 层静默 clamp 到 2 而不报错(吞吐其实 2 层却当
  4 层测)。⚠️ **Codex on PR #114**:必须读 **UE 协商能力**,**不能**读 `CONF:...:LAY?` 配置旋钮 ——
  那是 `set_cell_config` 写入的同一个值,回读只会原样返回配置的 4,对"UE 把 4 clamp 到 2"完全
  no-op。**注意**:UE 能力核对**不**覆盖 C 类端口路由泄漏(那是 cell 端口路由限制,跟 UE 能力是
  两回事);port-routing 仍是待定语义的 backlog。

**剩余 B 类(同机制延伸,各有特定坑)**:
- `MCS`:AMC on 时浮动,仅 AMC off 可回读校验(条件化)。
- `DL power`:InputLevelController 闭环会合法改它,"功率==target" 会误杀 → 需结合操作点 backlog。
- **不在范围**:C 类(端口路由泄漏、操作点)需先定语义;D 类不动。

**一句话**:频率是一致性网的第一根线,**MIMO layers 是第二根**(本 Phase);MCS / 功率是同一台
织机上待织的线。

## 9. 标准信道文件定义(Standard Channel Definition)— 软件掌控命名(2026-06-01 用户确立)

> 用户 2026-06-01:"**不管 F64 有没有自动化窗口,在我们的软件中都要标准化命名。** SCPI 能控制 F64 自动生成最好;不能,指导操作员手工产生〔按我们的标准命名〕;或者将已定义好的文件关联到我们软件中的标准信道文件上。"

### 决定:命名标准是**我们的**,不是 F64 的

§8 Step 1 的 .smu 文件名解析(`parse_smu_center_freq_mhz`)是**被动**的 —— 逆向一个我们不掌控的厂商命名约定。这跟 **#109 Codex P2 同病根**:一个 `3600M.smu` 被 `configure(3500)` 重调后文件名还说 3600,**文件名说谎**。赌"文件名忠实反映内容",而这个赌注我们不控制。

对照:**ASC 路径已经是生成式的**(`channel_engine.synthesize_hardware_pipeline` 按 TestCase 合成 .asc,config 是真值)。**GCM 是落后的被动一半。**

决定:软件里有一个**标准信道文件定义(SCD)** = 规范配置 + **我们掌控的标准名**,是真值。实际 .smu 用三种方式之一满足它(F64 能力只决定走哪条):

| 路径 | 做法 | 前提 |
|------|------|------|
| **a 自动生成** | SCPI 驱动 Channel Studio 按规范配置生成 + 标准命名 | Channel Studio 有 automation(现场/vendor 调研)|
| **b 手工按标准** | 指导操作员在 Channel Studio 生成,**用我们给的标准名** | 任何时候可做 |
| **c 关联已有** | 把已有厂商 .smu 映射到一个 SCD(SCD 的规范配置是真值,文件只是字节)| 任何时候可做 |

### SCD 实体:"信道自声明",平行 LabProfile / DUTProfile

- **规范配置**:`FrequencyIdentity`(ARFCN+带宽)+ CDL/TDL 模型 + MIMO 拓扑 + scenario + **极化**(polarization)+ **版本号**(version)+ 生成参数。
- **标准名**:`format_standard_channel_filename(SCD) -> str` —— **我们拥有的确定性函数**(config→name),格式:
  ```
  MF_<band>_<ARFCN>_BW<bw>_<model>_<scenario>_<MIMO>_<pol>_v<version>.smu
  例: MF_N78_640000_BW100_CDLC_UMa_4x4_DP_v3.smu
  ```
  - `MF_` 前缀标识"我们标准命名的"(跟厂商原始 .smu 区分);**ARFCN** 进名字(非 frequency_mhz,规范真值,贯彻 Phase 1);**极化** `<pol>`(MIMO OTA 核心参数:`V` / `H` 单极化 / `DP` 双极化〔V+H 或 ±45° slant〕);**版本号** `v<version>` 重标/重生成时递增(可追溯,关联 Step 3 alignment 漂移/重标)。
  - 字段一律 alnum 无下划线(下划线是分隔符);两个方向都我们拥有 → 反解必然正确(不像 Step 1 赌厂商约定)。
- **映射**:SCD → 实际 .smu 路径(`emulation_file`),经路径 a/b/c 填。
- **DB 实体,GUI 可编辑**,平行 `LabProfile`(chamber)/ `DUTProfile`(DUT,#115 backlog)—— 同一套 **"declared > inferred"** 架构(= ARFCN 规范 vs frequency_mhz 标称,= DUT 自声明)。

### Step 1 解析器**重新定位**:真值源 → cross-check 层

```
SCD 规范配置 (声明)            ← 真值
  ↕ 一致性校验: parse_smu_center_freq_mhz(实际文件名) vs SCD 声明频率
                不一致 → fail-loud (文件被重命名 / 重调 / 关联错)
实际 .smu 文件名               ← 不再信任, 只做 cross-check
```
Step 1 的解析器(§8/本 PR)**不白做** —— 从"真值"降为"cross-check",正好抓 #109 那种文件名说谎。

### 跟 P2-11 Phase 2 的关系

Phase 2 的 `emulation_file` 现在是裸路径。SCD 落地后,TestCase 可引用 **SCD(按规范配置)** 而非裸路径 —— "3500 MHz 用哪个 .smu" 从"赌文件名"变"查 SCD by `FrequencyIdentity`"。这也是 §5 提到的 "frequency → .smu 库映射" 的正解。

### 与静态清单(`available_channel_models`)的关系:synced projection(2026-06-01 用户确立)

用户决定:**静态清单不是独立手维护的死清单,而是 SCD↔文件关联的同步投影**。"每次 SCD 命名跟 F64 本地文件关联后,静态清单应被更新 —— 否则放一个并不存在(或不需要存在)的清单没用。"

- **SCD 是源**(规范配置真值 + 标准名);`available_channel_models`(GUI 下拉框读的那个 JSON)退化成**派生视图** —— SCD 关联即更新,**不再手敲**、不放不存在的条目。
- **路径 a/b**(我们/操作员按标准名生成):清单 entry 的 `filename` = 标准名(实际 F64 文件就叫这名)。
- **路径 c**(关联已有厂商 .smu):`filename` = **厂商实际文件**(`CALC:FILT:FILE` 要加载真文件),但 entry 用 **SCD 规范配置充实**(频率/MIMO/极化等是**声明真值**,非从名解析);关联时跑 `check_channel_filename_freq`(厂商名解析频率 vs SCD 声明 ARFCN),**不符 → fail-loud**(抓关联错文件)。
- 结果:下拉框/inventory 永远反映"**真实存在 + 已登记的 SCD**",频率元数据来自**声明**(权威)而非**解析**(§8 Step 1 降为关联时的 cross-check)。存量手敲条目在迁移成 SCD 前保留,逐步收敛。

### 实施切分(建议,均本地除路径 a)

| Step | 内容 | 本地/现场 |
|------|------|----------|
| 1 ✅ | `standard_channel_filename(config)` 命名契约函数 + 反解 + `check_channel_filename_freq` cross-check(`channel_naming.py`)| 本地 |
| 2a ✅ | `StandardChannelDefinition` DB 实体(规范配置 + 标准名 + 关联 .smu 文件)+ CRUD API + 绑定校验(必须 channelEmulator 连接)(#117)| 本地 |
| 2b ✅ | `associate_file`:关联实际 .smu(`check_channel_filename_freq` cross-check **不符 fail-loud**)+ **关联即更新 `available_channel_models`(synced projection)后端** —— 派生条目按 `scd_id` 标记重建、存量手敲条目保留、删除同步移除(`standard_channel_service.py`)| 本地 |
| 3 | 路径 c(关联已有 .smu → SCD)+ 路径 b(生成标准名给操作员)GUI 工作流(调 2b 后端)| 本地 |
| 4 | Phase 2 `emulation_file` 改引用 SCD(按 `FrequencyIdentity` 查)| 本地 |
| 5 | 路径 a(SCPI 驱动 Channel Studio 生成)| 现场 / vendor 调研 |

## 附:这跟 ARFCN 问题是同一母题的两个层次

```
微观 (P1-17 ARFCN):  UXM profile 标称 3600  vs  实际下发 ARFCN→3489        不一致
宏观 (本架构):        TestCase 频率          vs  UXM vs F64 vs SA           不一定联动
```
共同病根:**频率(及 MIMO/topology 等联动参数)缺一个单一真值源去驱动所有设备 +
fail-loud 校验一致性**。ARFCN 那层是"标称字段 vs 真实下发"的微观版;本架构是它在
"TestCase vs 多仪表"的宏观放大。两者的解药相同:单一真值源驱动 + 一致性校验。
