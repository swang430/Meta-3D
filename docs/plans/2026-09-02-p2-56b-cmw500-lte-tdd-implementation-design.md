# P2-56 ② — CMW500 LTE TDD 实现半（设计稿，待 review）

**日期**：2026-09-02　**状态**：✅ 已 review（用户 2026-09-02 拍板四条，见 §9）　**对应条目**：P2-56 ②

> ① 声明半已由 PR #444 合并（squash `e25d2b17`），收口 #445。
> 本片是 ②：把矩阵已经声明的 TDD 取值域**变成可达的正式路径**。

---

## 1. 可观察故障

`configure_mac_throughput_test` 在活体 duplex 非 FDD 时**整体 fail-loud**，
所以 LTE TDD 用例至今进不了正式路径。① 让系统能**回答**「TDD 哪些配比能正式配」，
但答案仍是「一个都不能」——因为本驱动没有下发路径。

## 2. 双实证前置

### 2.1 memory（恒适用）

- `feedback_enumerate_before_changing` —— 放开 `duplex` 要列的是**所有拿它做判断的地方**，
  不只是矩阵那一处（见 §4 的枚举）。
- `feedback_effective_end_not_nominal` —— 验证要打在**活体回读**上，不是打在「我发过了」上。
  本片每条新命令都必须走既有的 `_confirm(写 → OPC/错误队列门 → 回读严格比对)`。
- `feedback_value_form_space` —— `duplex` 从 `Literal["fdd"]` 变两值，
  「profile 说 TDD、活体是 FDD」这一格是**本片新造出来的**，必须同片堵上。
- `feedback_instrument_debug_via_diagnostic_sequence` —— 现场验证走诊断序列，不写临时脚本。

### 2.2 手册取证（本地 PDF **页面图像**逐格目视，不用 pdftotext）

> ⚠️ 表格类取证必须读页面图像：`pdftotext` 会把 RMC 表打散
> （实测：`10 MHz` 行标掉到行尾、`64-QAM 18` 渗到下一页表头下）。
> P2-55 在表格取证上把同一句断言写错过四遍，教训见 roadmap Discovered。

**表 2-39「DL RMCs for TDD, multiple TX antennas」（印刷 pp.78-79）逐行录入：**

| 带宽 | Alloc. RBs | Modulation | TBS index | Version |
|---|---|---|---|---|
| 1.4 MHz | 0 / **6** | QPSK / **QPSK** | 0 / **4** | - |
| 3 MHz | 0 / **15** | QPSK / **QPSK** | 0 / **5** | - |
| 5 MHz | 0 / **25** | QPSK / **16-QAM** | 0 / **12** | - |
| 10 MHz | 0 / 40 / **50** | QPSK / 16-QAM / **QPSK, 16-QAM, 64-QAM** | 0 / 13 / **5, 13, 18** | -，**唯 16-QAM/13 = `0: R.11` / `1: R.11-1`** |
| 15 MHz | 0 / **75** | QPSK / **QPSK** | 0 / **5** | - |
| 20 MHz | 0 / **100** | QPSK / **16-QAM** | 0 / **13** | **`0: R.30` / `1: R.30-1`** |

**与 FDD（表 2-38）逐格比对的结论**——现驱动的选行规则
（「每带宽取满配行里调制最高、且不需选件的那一行」）套到 TDD 上，**六个带宽的 DL 选行与 FDD 完全相同**：

| 带宽 token | DL 选行 | TDD 侧是否带 Version 歧义 |
|---|---|---|
| B014 | N6 / QPSK / T4 | 否 |
| B030 | N15 / QPSK / T5 | 否 |
| B050 | N25 / Q16 / T12 | 否 |
| B100 | N50 / Q64 / T18 | **否**（歧义在同组的 16-QAM/13 那行，我们不选它） |
| B150 | N75 / QPSK / T5 | 否 |
| B200 | N100 / Q16 / T13 | **是** → 必须显式下发 `RMC:VERSion:DL` |

⚠️ 唯一的 FDD/TDD 结构差异：**5 MHz/25RB 在 FDD 有两行（QPSK/5 与 16-QAM/12），
TDD 只有一行（16-QAM/12）**。选行结果碰巧相同，但**理由不同** —— 不能写成「TDD 同 FDD」。

**UL 侧沿用，且已核过为什么能沿用：**
- 表 2-33 标题原文是「UL RMCs for **FDD and TDD**, contiguous」（p.70），本身覆盖两种双工；
- 另有 TDD 专属的表 2-35「Special start positions, UL RMCs for TDD, contiguous」（p.74），
  但它逐行都是**特定频段 + 网络信令条件**（Band 41 NS_04 / Band 41 CA_NS_04 / Band 39 CA_NS_07）
  下的**部分分配**例外，`Alloc. RBs` 为 24/36/12/1/50/75/25 等非满配值
  —— **满配分配走不到这张表**，故 `RBPosition:UL LOW` 在 TDD 下同样成立。

**命令属性（① 已逐条核过，此处复用）**：
`ULDL` pp.687-688（`0 to 6`，*RST 1，KS550 **and** KS510，V3.0.10 / V3.0.50 值 0,2,3,4,6）；
`SSUBframe` p.688（`0 to 9`，*RST 7，值 8/9 只能配 normal CP，KS550 + KS512 for value 9，V2.1.20 / V3.5.10 值 9）；
`RMC:VERSion:DL<s>` p.803（`0 to 1`，*RST 0，无 Options，V3.2.70）；
`DMODe` p.366（`FDD | TDD`，KS500/KS550，V2.1.20）。

---

## 3. 四件必须同片做完（缺一就留洞）

roadmap 条目已写死这四件，此处给实现形状：

| # | 内容 | 形状 |
|---|---|---|
| ③-1 | **TDD 下发路径** | 在 `configure_mac_throughput_test` 里按活体 duplex 分支；TDD 分支多发 ULDL / SSUBframe（+ 20 MHz 时的 `RMC:VERSion:DL`），每条走既有 `_confirm` 三段式 |
| ③-2 | **表 2-39 满配行录入** | 见 §5：**不新建字典**，给 `CmwLteFullRbRmcPlan` 加 TDD 侧字段 |
| ③-3 | **放开 profile 的 TDD 取值域** | `duplex` → `Literal["fdd","tdd"]`；三个字段从 `None`-only 放开到手册域（受 §6 的定档策略约束） |
| ③-4 | **活体 duplex 与 profile 的一致性校验** | 见 §4 —— 这是本片**新造出来的**那一格，必须同片堵上 |

## 4. ③-4：放开 `duplex` 新造出的那一格（本片最大的风险）

**今天**驱动只拿活体 duplex 跟字面量 `"FDD"` 比，**从不跟 profile 比**
（`if live_duplex != "FDD": fail-loud`）。`duplex` 一旦两值：

| profile | 活体 | 今天的行为 | 必须变成 |
|---|---|---|---|
| fdd | FDD | 正常 | 不变 |
| fdd | TDD | fail-loud | 不变（仍拒） |
| **tdd** | **FDD** | **静默按 FDD 配掉** ⚠️ | **拒**（profile/活体不符） |
| tdd | TDD | fail-loud | 走新的 TDD 分支 |

**枚举「所有拿 duplex 做判断的地方」**（动手前列全集，不改完再 grep）：

1. `configure_mac_throughput_test` 的 `live_duplex != "FDD"` 分支 —— 改成先比 profile 再分支；
2. `MAC_CFG_NO_EQUIVALENT["TDD_SLOT_PATTERN"]` 的说明串 —— 「TDD 下本方法整体 fail-loud」会变假；
3. `evaluate_lte_2x2_formal_capability`（`cmw500_base_station.py:1191`）—— 见 §4.1，
   它是本片开工前必须先读的第一处，且**读完发现比预想的重要**；
4. `set_cell_config` 的 `CELL_DUPLEX` 写/回读 —— 已是 authoritative config_field，形态不变；
5. `base_station_execution_evidence` 的正式 KPI 准入门 —— 需确认它有没有隐含 FDD 假设；
6. 能力矩阵 `duplex` 维度的 `tdd` 格 —— 定档从 `diagnostic_only` 上调（见 §6）。

> ⚠️ 5 仍是**开工前必须读完**的一处（它不在「我想改的文件」里，但拿 duplex 做判断）。
> 3 已在定稿前读完，结论见 §4.1。

### 4.1 已读完的第 3 处：驱动有一套**与矩阵平行的硬编码选件集**

初稿这里写的是内审转述的函数名 `_admit_formal_lte_2x2` —— **该符号不存在**
（我把审查意见里的名字直接抄进了设计稿，没核。教训同
`feedback_review_findings_verify_premise_first`：审查意见的**事实**要自己核，
哪怕它的**结论**是对的）。真名是 `evaluate_lte_2x2_formal_capability`（`:1191`）。

读完后的实际情况，比「它接受 tdd」这一句要紧：

```python
duplex_option = "KS500" if normalized_duplex == "fdd" else "KS550"
missing = sorted({"KS520", duplex_option} - installed)
```

- `installed` 来自 `_probe_installed_options()`（`:1850`），是**真机探测**的选件表；
- 所以**驱动确实有「已装选件」这个事实**。之前登记的 Discovered
  「选件与固件下限至今没有判定消费方」按字面是对的（说的是**兼容层**
  `BaseStationExecutionRequirements` 与 `_mac_dimension_rejections`），
  但它漏掉了这半句 —— 读者容易推出「系统根本查不了选件」的错误结论。
  **该 Discovered 需补一句**（本片顺带，一行文档）。
- ⚠️ **这是同一事实的两个源**：矩阵（① 建的 `satisfying_options` / `required_options`）
  与这段硬编码集合，中间**没有任何门**。两处已经在打架：
  矩阵声明 `mimo_layers=2` 需 `KS520` **or** `KS540`（手册 p.753 两行 Options），
  而这里**无条件**要求 `KS520` —— 只装 KS540（2x4）的整机会被矩阵说「支持」、
  被运行期挡掉。方向保守（挡住 > 放行），是 P2-55 遗留、不是本片造成。

**对 ② 的直接影响**：`duplex_option` 那一行**正是 duplex 相关的选件逻辑**，
② 一放开 TDD，它的 `else "KS550"` 分支就从不可达变成活的。所以 ② 必须：

- **至少**：确认该分支与矩阵 `duplex=tdd` 的 `satisfying_options=("KS550",)` 一致
  （今天一致），并加一道**不变量门**把两处钉在一起，防止将来单边改动；
- **不做**：把整段选件判断换源到矩阵。那是「加机制」且面大（要连带处理
  `mimo_layers` 的 OR 语义与 KS520 硬要求），属独立一片。已在 §7 登记。

## 5. ③-2：不新建字典，扩现有结构

现结构是 `CmwLteFullRbRmcPlan(downlink, uplink)`，按带宽 token 索引。
TDD 的 UL 沿用、DL 选行数值恰好也相同，但**理由不同**且 20 MHz 多一个 version。

**建议形状**（供 review）：

```python
@dataclass(frozen=True)
class CmwLteFullRbRmcPlan:
    downlink: CmwRmcSelection
    uplink: CmwRmcSelection
    #: 该带宽在 **TDD** 下选同一行时，是否必须显式下发 RMC:VERSion:DL。
    #: 表 2-39 只有两行带 Version 列取值，其中被本驱动选中的只有 B200。
    tdd_dl_version: int | None = None
```

**为什么不建第二个字典**：两边 12 个取值里 11 个逐格相同，建两份等于给
「改一处忘改另一处」开门；而 `tdd_dl_version` 这一个字段就把差异说完了。
**代价**：读的人会以为「TDD 就是 FDD」——所以注释里必须写明 5 MHz 那格的
行数差异（FDD 两行 / TDD 一行），选行结果相同是**巧合不是规律**。

## 6. 定档策略（新增取值放行到哪一档）

① 把 TDD 侧全部标 `diagnostic_only`，理由是「缺本驱动的实现」。② 实现后该理由消失，
但**真机证据仍然没有**。按 P2-55 立的判据（命令 Range + RMC 表覆盖 + 本驱动已实现下发 + 真机证据）：

**建议**：② 合并时把 `duplex=tdd` 与 ULDL/SSUBframe/rmc_version 的取值**上调到
`diagnostic_only` 之上、但不到 `authoritative`** —— 问题是**今天只有两档可用**。
两个选项，请 review 时定：

- **(a) 保持 `diagnostic_only`**，等 ③ 现场半拿到真机证据再上调。
  好处：不发明未经验证的正式路径，与 `mimo_layers=4` 的处理一致（它也是「命令层有据、
  本地无真机证据」→ 降级）。坏处：② 合完 TDD 仍进不了正式路径，故障没真正修掉。
- **(b) 上调到 `authoritative`**，与 TM2/TM4/TM6 一致（它们也只有手册证据、无真机闭环）。
  好处：② 真正修掉可观察故障。坏处：`mimo_layers=4` 与 TM2/4/6 的定档本来就不一致
  （① 的矩阵注释把这条矛盾留作警示），选 (b) 等于站在 TM2/4/6 那一侧。

> **我的倾向是 (b)**，理由：P2-55 已经把「有手册证据 + 已实现下发」定为 authoritative
> 的判据（TM2/4/6 就是这样过的），真机证据是**现场半**的职责而不是本地半的。
> 选 (a) 会让 ② 变成一片「写了代码但什么都没打开」的空转。
> 但这条会顺带暴露 `mimo_layers=4` 的定档不一致 —— 需要一并决定。

## 7. 本片不做

| 不做 | 理由 |
|---|---|
| **cyclic prefix 维度** | `special_subframe` 值 8/9 要求 normal CP，而 profile 没有 CP 字段。**本片把 8/9 排除在放开范围外**（只放开 0..7），比新增一个未取证的维度安全 |
| **carrier-specific 配比**（`CELL:TDD:SPECific` / KS512） | 本 profile 走 `[:PCC]` 单载波形态，无可观察故障 |
| **表 2-39 的非满配行** | 与 FDD 同理：改非满配要同时改两个下发点 |
| **把选件判断换源到矩阵** | `evaluate_lte_2x2_formal_capability` 的硬编码选件集与矩阵是两个源（§4.1）。换源要连带处理 `mimo_layers` 的 OR 语义与 KS520 硬要求，面大且与本片故障无关 —— 独立一片 |
| **真机认证** | ③ 现场半，本地不可替代 |

## 8. 验收（草案）

1. **FDD 不回归**：现有 FDD 用例逐条通过；六条 digest 基线实测回到当前 main 值。
2. **profile/活体不符被拒**：`duplex=tdd` 的 profile 撞 FDD 活体 → **首次写之前**被拒，理由指明是哪一边不符。
3. **TDD 下发逐条回读确认**：ULDL / SSUBframe（+ B200 的 version）各自走 `_confirm` 三段式，回读不符即整组失败。
4. **B200 必发 version、其余带宽不发**：由数据派生的不变量门，不是逐带宽 if。
5. **`special_subframe` 只放开 0..7**：8/9 在 profile 构造层即拒，理由指向缺 CP 维度。
6. 每条新增行为都有**会红的变异**并实跑。
7. **§4 那六处 duplex 判断点逐处交代**：改了的说改法，没改的说为什么不用改。
8. **矩阵与硬编码选件集的一致性门**（§4.1）：`duplex=tdd` 那格的 `satisfying_options` 与驱动 `duplex_option` 的 TDD 分支必须相等，单边改动即红。

## 9. Review 结论（用户 2026-09-02 拍板）

1. **(b)** —— ② 合并时把 TDD 侧取值上调 `authoritative`。
2. **可以** —— 给 `CmwLteFullRbRmcPlan` 加字段，不建第二份字典。
   ⚠️ **实现时的一处收窄**：字段改成 `tdd_dl_version_required: bool`，不存版本**值**。
   理由：表 2-39 的 20 MHz 那行有 `0: R.30` 与 `1: R.30-1` **两个都合法**，选哪个是
   用户意图（由 profile 的 `rmc_version` 携带），表只决定「这个带宽要不要指定版本」。
   存成 `int | None` 会让同一个值有两个源（计划表与 profile），又是本片在治的形态。
3. **可以** —— `special_subframe` 只放开 0..7，8/9 留给以后（避开 cyclic prefix 维度）。
4. **`mimo_layers=4` 给出仪表能力限制提示** —— 把它的降档理由从「本地无 4 天线真机证据」
   **换源**成可核的能力限制，这样它与 TM2/4/6 不再是「同样处境、不同结论」：
   - **仪表侧**：`FOUR (4x2)` 需 KS521、`FOUR (4x4)` 需 KS540（p.753 Options 两行），
     且需一个 4 条 TX 通路的场景（表 2-32 按**场景** × TM 列天线配置，pp.65-67）；
   - **本驱动侧**：内部路由只实现了 nx2 场景
     （`ROUTe:LTE:SIGN<i>:SCENario:TRO:FLEXible`，p.630-631，purpose 原文「LTE 1CC-nx2」），
     没有 4 TX 场景的路由命令。
   → TM2/4/6 在 nx2 路由下跑得起来，4 天线跑不起来 —— 定档差异从此有真实依据。

## 10. 原 review 问题（存档）

1. **§6 的定档**：(a) 保持 diagnostic_only 等现场，还是 (b) 上调 authoritative？
   选 (b) 要一并决定 `mimo_layers=4` 的不一致怎么办。
2. **§5 的结构**：给 `CmwLteFullRbRmcPlan` 加一个 `tdd_dl_version` 字段（不建第二份字典）
   是否可接受？
3. **§7 把 `special_subframe` 限到 0..7**（回避 CP 维度）是否可接受？
   替代方案是本片顺带加一个 cyclic prefix 维度，但那要另取证一条命令。
