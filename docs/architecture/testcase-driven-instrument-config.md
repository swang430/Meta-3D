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
| **F64 GCM** (`keysight_gcm`) | ❌ `sim_rules` 不传 emulation_file → **fallback 默认 .smu** | **TestCase 无法驱动 .smu;频率不联动** |
| **switch** (rfSwitch) | ❌ `orchestrate_switch_topology(chamber, mode_id)` | **chamber 驱动,非 TestCase** |
| **信号源 / VNA** | ❌ executor 未接 | 干扰生成 / 在线校准未纳入 |

**两个硬证据**(GCM 缺口):
- `MIMOOTAConfiguration` **没有 `emulation_file` 字段** → TestCase 根本无法指定 F64 .smu。
- `measure.py` 的 `sim_rules` 只有 `frequency_hz/power/rsrp/snr`,**没 emulation_file**。

**后果**:GCM 模式下 TestCase 频率=3500 → UXM 配 3500、F64 用默认 3600M .smu →
**链路打架,且无人报警**。

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

## 7. 分阶段实施(建议)

| 阶段 | 内容 | 性质 | 优先 |
|------|------|------|------|
| **1** ✅ | 多方频率一致性 fail-loud 校验(measure) — **已实现 (P2-11 Phase 1)**: `nr_arfcn.py` 工具 + 各 driver `get_frequency_identity()` 归一到 (中心 ARFCN, 带宽) + `frequency_consistency.check_*` 精确比对 + measure phase `precheck_strict_frequency` gate | silent-failure 防护,本地可做,小 | ⭐ 最先(保护测试可信度)|
| **2** | TestCase → F64 GCM .smu 联动(`emulation_file` 字段 + sim_rules 透传 + 不 fallback) | GCM 优先 | ⭐ 高(下一步)|
| **3** | switch topology 纳入 TestCase 驱动(现 chamber-driven)| 架构补全 | 中 |
| **4** | 信号源 / VNA 纳入 TestCase 驱动(干扰 / 在线校准)| 架构补全 | 低(按需)|
| **5** | 默认配置角色文档化 + 路径 A/B 边界在代码注释固化 | 防认知漂移 | 贯穿 |

## 附:这跟 ARFCN 问题是同一母题的两个层次

```
微观 (P1-17 ARFCN):  UXM profile 标称 3600  vs  实际下发 ARFCN→3489        不一致
宏观 (本架构):        TestCase 频率          vs  UXM vs F64 vs SA           不一定联动
```
共同病根:**频率(及 MIMO/topology 等联动参数)缺一个单一真值源去驱动所有设备 +
fail-loud 校验一致性**。ARFCN 那层是"标称字段 vs 真实下发"的微观版;本架构是它在
"TestCase vs 多仪表"的宏观放大。两者的解药相同:单一真值源驱动 + 一致性校验。
