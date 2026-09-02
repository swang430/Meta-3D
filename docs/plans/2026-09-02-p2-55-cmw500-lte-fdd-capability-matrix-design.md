# P2-55 — CMW500 LTE FDD MAC 能力矩阵（设计稿，待 review）

**日期**：2026-09-02　**状态**：待用户 review，未动代码　**对应条目**：P2-55

---

## 1. 可观察故障与现状

`BaseStationMacProfileCapability`（[`base_station_manifest.py:301`](../../api-service/app/hal/base_station_manifest.py)）
今天只声明「本 adapter 接受 `lte_rmc@1` 这个 profile 形状」：

```python
BaseStationMacProfileCapability(
    kind="lte_rmc", profile_version=1, rat="lte",
    application_evidence="authoritative_readback",
    source_reference=CMW500_LTE_PROFILE_SOURCE,
)
```

它**不声明该 profile 内部任何维度的取值域**。目前之所以没出事，是因为
`LteRmcMacTestProfileV1` 把每个维度都锁成了单值：

| 维度 | 当前类型 | 含义 |
|---|---|---|
| `resource_allocation` | `Literal["full"]` | 只有满 RB |
| `enable_amc` | `Literal[False]` | 只有固定调制 |
| `duplex` | `Literal["fdd"]` | 只有 FDD |
| `transmission_mode` | `Literal["TM3"]` | 只有 TM3 |
| `mimo_layers` | `Literal[2]` | 只有 2 层 |

**故障在于：一旦打开任何一个维度，manifest 的声明就退化成一个过宽的布尔** ——
系统能回答「接不接受 lte_rmc@1」，但答不出「TM1 能不能正式配」「1×1 行不行」
「部分 RB 有没有依据」。P2-51 闭环的是 FDD/2×2/满 RB/固定 RMC 这一条窄路径，
矩阵从来没有被表达过。

所以本片的顺序是**先建矩阵、再打开维度**，不能反过来。

---

## 2. 双实证前置记录

### 2.1 memory（恒适用）

命中并实际影响了设计的三条：

- `feedback_query_notebooklm_for_uxm_f64_driver` —— 涉仪器语义必查 notebook，
  且**查到的必须是手册原文、不是它的推断**。本次照做，并因此抓到一处错误（见 §2.2）。
- `feedback_enumerate_before_changing` —— 改之前先列全集。本片的"全集"是
  §3 那张维度表，而不是"我这次想打开的那两个维度"。
- `feedback_effective_end_not_nominal` —— 判据打在真实生效端。矩阵必须落在
  manifest（执行前被消费的那份），不是文档里的一张表。

### 2.2 NotebookLM（必查：涉 CMW500 SCPI 语义）

查了「R&S CMW500」资料库。**回答里 6 组有 5 组经本地 PDF 逐字核对成立，1 组是错的**。

> ⚠️ **本次查询的 `sources_used` 与 `citations` 都是空的**（上一次查 UXM 时两者都有内容、
> 还带 `cited_text` 原文摘录）。它仍然逐条声称「手册原文写明」。这是必须本地核对的直接信号。

**错的那一组（第 5 组 HARQ）**：我问的是 `HARQ:DL:ENABle` 与 `HARQ:DL:NHT`，
它答的是 **UL** 的两条（p.782），并称「NHT 条目有独立、完整的……**选件依赖声明行**」。

本地核对结果：

| 命令 | 印刷页 | Range | *RST | Options 行 |
|---|---|---|---|---|
| `…:HARQ:DL:ENABle` | 783 | `OFF \| ON` | `OFF` | **有**：`R&S CMW-KS510 for scenarios without carrier aggregation` / `R&S CMW-KS512 for scenarios with carrier aggregation` |
| `…:HARQ:DL:NHT` | 784 | `2 to 4` | `2` | **没有**（属性块只有 Firmware/software 与 Manual operation） |
| `…:HARQ:UL:NHT` | 782 | `1 to 5` | `4` | 有：`R&S CMW-KS510` |

也就是说：它把 UL 的属性当成了 DL 的答案，**没有声明自己换了主语**。
[P2-51 取证清单](2026-08-30-p2-51-cmw500-mac-scheduling-evidence.md) 第 10 行的原始记载
（「NHT 条目无 Options 行 —— 组整体门控为 ⚠ 推断（保守不驱动）」）才是对的。

**说对的那一组值得单独记**：它说 LTE 侧**没有** AMC 开关命令。本地全文核对
（108882 行文本）`AMC` / `adaptive modulation` **零命中**，结论成立 —— 否定结论也核过才敢用。

---

## 3. 手册取证结果（全部经本地 PDF 逐字核对）

底本与 P2-51 同一份：`Instrument_API_Doc/R&S CMW500/CMW_LTE_UE_UserManual_V4-0-250_en_41 (2).pdf`
（印刷页码 = PDF 页码）。

### 3.1 命令级取值域（属性块原文，可机械提取、可复现）

| 维度 | 命令 | 印刷页 | Range 原文 | *RST | Options 原文 |
|---|---|---|---|---|---|
| 传输模式 | `CONFigure:LTE:SIGN<i>:CONNection[:PCC]:TRANsmission <Mode>` | 752 | `TM1 \| TM2 \| TM3 \| TM4 \| TM6 \| TM7 \| TM8 \| TM9` | `TM1` | `R&S CMW-KS520 or -KS540 for TM 2, 3, 4, 6, 7, 9`；`R&S CMW-KS520 for TM 8` |
| DL 天线数 | `CONFigure:LTE:SIGN<i>:CONNection[:PCC]:NENBantennas <Antennas>` | 753 | `ONE \| TWO \| FOUR` | `ONE` | `TWO (2x2): KS520`；`TWO (2x4): KS540`；`FOUR (4x2): KS521`；`FOUR (4x4): KS540` |
| DL HARQ 开关 | `…:CONNection:HARQ:DL:ENABle <Enable>` | 783 | `OFF \| ON` | `OFF` | `KS510`（无 CA）/ `KS512`（有 CA） |
| DL HARQ 次数 | `…:CONNection:HARQ:DL:NHT <Number>` | 784 | `2 to 4` | `2` | **无 Options 行** |

**注意三点**（都是原文，不是推断）：

1. **Range 里没有 TM5** —— 是 `TM1|TM2|TM3|TM4|TM6|TM7|TM8|TM9`，中间跳过 5。
   任何"TM1..TM9 连续"的写法都是错的。
2. **TM 与天线数互相约束**：`NENBantennas` 的描述原文是
   「Selects the number of downlink TX antennas **for transmission mode 1 to 6**.
   The value must be compatible to the active **scenario and transmission mode**, see Table 2-32.」
   `TRANsmission` 那条也写「must be compatible to the active scenario, see Table 2-32」。
   → **这两个维度不是正交的**，合法性由 Table 2-32（scenario × TM × 天线）决定。
3. **TM9 走另一条命令**：`…:CONNection[:PCC]:TM<no>:NTXantennas`（`TWO|FOUR|EIGHt`，p.766），
   不归 `NENBantennas` 管。

另外发现一条现成的回读源：`SENSe:LTE:SIGN<i>:CONNection[:PCC]:TSCHeme?`（查询传输方案），
以及一个未列入本片的耦合维度 `…:CONNection[:PCC]:DCIFormat`（同样「must be compatible to
the transmission mode, see Table 2-32」）。

### 3.2 表格级组合（只能目视复核，不能机械提取）

| 表 | 标题 | 印刷页 |
|---|---|---|
| 2-33 | UL RMCs for FDD and TDD, contiguous | 71 起 |
| 2-37 | **DL RMCs, single TX antenna** | 76–77 |
| 2-38 | DL RMCs for FDD, multiple TX antennas | 78 |
| 2-39 | DL RMCs for TDD, multiple TX antennas | 79 |

**这些表 `pdftotext` 提取不出来**：列被打散，带宽标签掉到行尾，行列对应关系丢失：

```
Table 2-38: DL RMCs for FDD, multiple TX antennas
Bandwidth / Allocated RBs / Modulation / TBS index
0 / QPSK / 0 / 6 / QPSK / 4 / 0 / QPSK / 0 / 15 / QPSK / 5 …
1.4 MHz / 3 MHz            ← 带宽跑到最后
```

P2-51 当初就是**用 PDF 原件逐页目视复核** pp.70-72 / pp.77-79 才敢用表 2-38 的满配行。

> **✅ 2026-09-02 更正**：初稿据 `pdftotext` 的行数估计表 2-37「篇幅约为 2-38 的四倍」，
> **这个估计是错的** —— 那 444 行里绝大部分是分页噪音。按 PDF 页面实际清点：
> 表 2-37 起于 p.75 末、跨 p.76-77，**数据行约 60 行**；表 2-38 约 16 行。
> 两张表都在可逐格录入的范围内。
>
> 读图能力已校准：我读出的表 2-38 与 P2-51 当初目视复核的记载**逐格吻合**
> （5 MHz 的 25RB/16-QAM/T12、10 MHz 的 50RB/64-QAM/T18、以及 40RB/16-QAM/T13
> 那一行部分分配都对上），因此表格取证由本会话直接读 PDF 页面完成，不需要人工转录。

另有一句适用于全部 DL RMC 表的原文（表 2-37 上方）：
> `For 256-QAM, option R&S CMW-KS504/-KS554 is required. For 1024-QAM, option R&S CMW-KS505/-KS555 is required.`

**目视取证顺带拿到的三条原文，都直接影响范围**：

1. ~~**RMC 表只覆盖 TM1..TM6**……这三个值没有任何 DL RMC 表依据。~~
   > ❌ **2026-09-02 更正（这句话是错的）**：当时只读了 §2.2.19.3（TM1）与 §2.2.19.4
   > （TM 2 to 6）就下了结论，**没往后翻**。手册另有三节专门的 TM7/8/9 RMC 表：
   > §2.2.19.5「DL RMCs, transmission mode 7」（表 2-40 FDD / 2-41 TDD，**p.79**）、
   > §2.2.19.6（表 2-42 FDD **p.80** / 表 2-43 TDD **p.81**）、
   > §2.2.19.7（表 2-44 FDD / 表 2-45 TDD，**p.82**）。
   >
   > ❌ **第一次修正也是错的**：当时把理由改成「天线配置路径**手册未给**」——
   > 内审核出手册**给了**：表 2-32「Transmission scheme overview」（pp.65-67）
   > 按「场景 × TM」列出各 TM 的天线配置（例如 TM7 在 `1x1 carrier` 场景是 `1x1`、
   > 在 `nx2 carrier` 场景是 `1x2` —— **随场景取值，不是固定值**）；§2.6.15.4
   > 「MIMO beamforming settings TM 7/8」（pp.761-764）是 TM7/8 的专属命令集，
   > 含 `BEAMforming:NOLayers`（p.762，`L1|L2` = 单层/双层波束成形，*RST `L2`）。
   > 而 `TRANsmission` 与 `NENBantennas` 的描述里都写着 **see Table 2-32** ——
   > 手册自己的交叉引用，我两次都没顺着走。
   >
   > ✅ **真正的理由（第二次修正）**：手册侧证据齐全，缺的是**本驱动的实现** ——
   > `mimo_layers` 只下发 `NENBantennas`（p.753，明写只管 TM 1 to 6）；
   > TM7/TM8 的波束成形参数在 §2.6.15.4、TM9 的天线在 `TM<no>:NTXantennas`
   > （p.766，Suffix `<no>`=9），这两套本驱动都未接。
   >
   > **两次错误成因相同：把「我没找到」写成了「手册没有」。**
   > 结论方向（fail-closed）始终没变，但矩阵的全部价值就在于每格出处准确。
   >
   > 门也随之重做：原先那道只查笼统词「无依据」三连字、且坐标被开头的
   > 「命令 Range 含 TMx（p.752）」样板前缀满足 —— 内审实测 6 条变异全绿，
   > **包括完整撤销本片修复**。新门改为①禁止一切「手册没有」式的厂商侧否定断言
   > （那要穷尽全书才能证伪），②必须自述**我们**缺什么，③整条理由要有可定位坐标。

2. **天线数与用哪张表绑定**：`NENBantennas=ONE` ⇒ 单天线 ⇒ 表 2-37；`TWO/FOUR` ⇒ 表 2-38。
   所以**打开天线维度到 `ONE`，就必须同时有表 2-37 的行**，否则 1×1 下不知道该配什么 RMC。
3. **`Position first RB` 列与既有命令一一对应**（§2.2.19.3 原文）：
   `L: lower end of cell bandwidth` / `H: upper end` / `5, 10, 23, 35, 48: special start
   positions for 3GPP TS 36.521, table C.2-2`。这正是 `RMC:RBPosition:DL<s>` 的 Range
   `LOW|HIGH|P5|P10|P23|P35|P48`（P2-51 取证表第 4 行）。
4. 表 2-37 脚注：带 `*` 的 TBS（如 `64-QAM/25*`）`have been removed from 3GPP TS 36.521,
   but are still supported for **FDD** for backward compatibility reasons. They are
   **not supported for TDD**` —— 本片 FDD-only，可用；P2-56 做 TDD 时必须排除。

---

## 4. 范围建议

### 4.1 本片做：把矩阵建起来，并只打开命令级可复现取证的维度

| 维度 | 建议 | 依据 |
|---|---|---|
| `transmission_mode` | 打开到 `TM1/TM2/TM3/TM4/TM6`（逐值标 support + 选件）；**`TM7/TM8/TM9` 声明为 `diagnostic_only`** | 判据以驱动内矩阵声明上方那段注释为准（§3.2 第 1 条的初版理由已证伪并划掉）。TM7/8/9 手册侧证据齐全，缺的是**本驱动未实现**其下发路径 |
| DL 天线数（→ `mimo_layers`） | 打开到 `ONE/TWO`，逐值标选件；**`FOUR` 声明为 `diagnostic_only`** | `ONE`/`TWO` 分别有表 2-37 / 2-38 支撑；`FOUR` 需 KS521/KS540 且本地无真机证据 |
| DL HARQ | `enable` 与 `nht` 分别声明；两者都保持 **diagnostic_only** | §3.1：`ENABle` 选件门控、`NHT` 无 Options 行 → 组整体门控是推断，保守不驱动 |
| `enable_amc` | 保持 `Literal[False]`，理由改成**有据的**「手册无 AMC 开关，自适应须改 `STYPe`（另一维度）」 | §2.2 全文零命中 |
| `duplex` | 保持 `Literal["fdd"]` | TDD 是 P2-56 的范围，不越界 |

### 4.2 本片不做（明确留给后续，不是遗漏）

| 不做的事 | 理由 |
|---|---|
| **部分 RB / 非满配组合**（`resource_allocation` 维持 `Literal["full"]`） | 表 2-37/2-38 的**满配行**本片要录（打开天线维度的前提，见 §3.2 第 2 条），但**非满配行不打开**：那会同时改动 `RMC:DL<s>` 的 NumberRB 与 `RBPosition` 两个下发点，超出「打开 TM + 天线」这一个目的。留作独立后续。 |
| **Table 2-32 的 scenario × TM × 天线 合法性表** | 同上，是表格。本片矩阵只声明**单维度取值域**，不声明跨维度组合合法性；跨维度校验保持 fail-closed（未在白名单内的组合一律拒绝）。 |
| **`DCIFormat` / `TM<no>:NTXantennas` / `TSCHeme?`** | 本次取证顺带发现，不在 P2-55 条目的六个维度里。登记 Discovered，不在本片实现。 |
| **UL 侧维度** | 条目里的 "DL/UL RMC" 指 RMC 表，属表格类，同 4.2 第一行处理。 |
| **TDD** | P2-56。 |

### 4.3 为什么这样切

条目要求「逐组合绑定命令、参数域、回读、错误队列与证据强度」。

按**维度**声明取值域、组合走 fail-closed 白名单，能在这一片就消除可观察故障 ——
系统能准确回答每个维度哪些取值可正式配、哪些要选件、哪些无依据。

**录入范围以「打开这两个维度所必需」为界**：表 2-37/2-38 的满配行必须录（否则 `ONE`
打开后无 RMC 可配），非满配行不录。判据是 ⑦ 的那句问话 —— 不录非满配行，
「打开 TM 和天线」这件事照样成立；录了则要同时改 NumberRB 与 RBPosition 两个下发点。

录入本身由本会话直接读 PDF 页面完成（§3.2 已校准），不是人工转录，
所以工作量不是这里的取舍理由；**取舍理由是改动面**。

---

## 5. 矩阵形态：复用既有结构，不新造机制

仓库已有 `BaseStationConfigFieldCapability`，它的 `support` 恰好就是本片要的三态：

```python
support: Literal["authoritative", "diagnostic_only", "not_applicable"]
readback: Literal["authoritative", "unavailable", "not_applicable"]
reason: str                      # 非空
source_reference: str | None
```

缺的只有**取值域**与**选件依赖**。建议在 `BaseStationMacProfileCapability` 下增加一个
维度级子结构（字段名待定，形如 `dimensions: tuple[MacProfileDimensionCapability, ...]`），
沿用上面四个字段并补：

- `values`：该维度的取值域（逐值，不是范围字符串）
- `option_dependencies`：逐值的选件要求（无选件的值显式标空，而不是省略）

**不新增判定机制**：兼容性判定仍走 P1-75 建立的那一个判定器，本片只是让它多消费一份
维度声明。GUI 与 OpenAPI 按既有镜像同步。

---

## 6. 验收（草案，待 review 后细化）

1. manifest 声明每个已打开维度的**逐值** support / readback / 选件 / 出处；缺出处的值不得出现。
2. profile 打开后的每个取值，若 manifest 未声明为 `authoritative`，在**首次仪表 I/O 之前**被拒。
3. 未在白名单内的**跨维度组合**（如 TM1 + 天线 TWO）一律拒绝，不猜 Table 2-32。
4. 部分 RB / TDD / UL 维度保持 `unavailable`，且拒绝理由能指到「依据在表 2-37/2-39，需目视取证」。
5. 选件缺失时的行为与 P2-51 既有约定一致：不下发、记 receipt、不当成功。
6. 每条新增声明都能被一个会红的变异抓住（不是存在性断言）。
7. 现场半：真机矩阵抽样复验，非现场测试不替代。

---

## 7. Review 结论（2026-09-02 用户拍板）

| 问题 | 结论 |
|---|---|
| 1. 范围 | **打开 TM 与天线数**。据此本稿 §4.1 已细化：TM 打开 TM1..TM6、TM7/8/9 标 `diagnostic_only`；天线打开 ONE/TWO、FOUR 标 `diagnostic_only`（理由以驱动内矩阵声明上方那段注释为准；§3.2 第 1 条的初版理由已证伪并划掉）。 |
| 2. 目视取证由谁做 | **本会话直接读 PDF 页面完成**，不需要人工转录。读图能力已用 P2-51 的既有结论校准（§3.2 更正块）。 |
| 3. 矩阵放哪 | **结构放通用层（扩展 `BaseStationMacProfileCapability`），内容跟着仪表走。** 理由见 §5.1。 |

### 5.1 为什么是「结构通用、内容跟仪表」

矩阵的**内容**完全是 R&S 特有的 —— `TM3`、`KS520`、`NENBantennas` 在 UXM 那边不存在
任何对应物。但矩阵的**形状**（维度 → 取值域 → 三态 → 选件 → 出处）与厂商无关。

仓库既有的 `BaseStationConfigFieldCapability` 已经是这个模式：`field: str` 是**字符串键**，
不是具名字段，通用层不认识任何具体字段名。P2-43 / P2-44 确立的原则也是同一条 ——
共同消费者零厂商判断，厂商差异只体现在 manifest 的**数据**里。

所以维度用字符串键（`dimension: str` + `values: tuple[...]`），
**绝不把 `transmission_mode` 这种 LTE 概念写死进通用结构**。CMW500 adapter 声明
`dimension="transmission_mode"`，UXM 将来声明它自己的维度，通用层两个都不认识。
