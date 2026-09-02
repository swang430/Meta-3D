# P2-56 — CMW500 LTE TDD 与真机认证（设计稿，待 review）

**日期**：2026-09-02　**状态**：✅ 已 review，声明半已实现　**对应条目**：P2-56 ①（声明半）

---

## 1. 可观察故障

`LteRmcMacTestProfileV1.duplex` 是 `Literal["fdd"]`（[`base_station_mac_profile.py:293`](../../api-service/app/hal/base_station_mac_profile.py)），
而驱动在 [`cmw500_base_station.py:2240`](../../api-service/app/hal/cmw500_base_station.py) 对
活体 TDD 整体 fail-loud：

> 活体 duplex='TDD'：LTE TDD 配比是 `CELL[:PCC]:ULDL` 0..6（p.687）+ 特殊子帧，
> NR 形态 frozen LTE profile 要求 FDD……TDD 正式 MAC 配置为平台缺口

所以今天：**LTE TDD 用例根本进不了正式路径**，系统也答不出「TDD 的哪些配比可以正式配」。

---

## 2. 双实证前置记录

### 2.1 memory（恒适用）

- `feedback_enumerate_before_changing` —— 打开 `duplex` 要列的是**整个 TDD 全集**
  （配比 / 特殊子帧 / RMC version / 表 2-39 / 选件 / 固件），不是"我这次想加的那两个字段"。
- `feedback_value_form_space` —— 本片引入一个**新的形态维度**：条件不再挂在维度上，
  而是挂在**取值**上（某些取值要更高固件、某些取值互斥）。
- `feedback_gate_itself_can_be_fake` —— 刚在 #442 花了八轮外审验证这条：
  判自然语言的门不收敛。本片的新门要尽量落在**结构化取值**上，不落在措辞上。
- `feedback_query_notebooklm_for_uxm_f64_driver` —— 已查 CMW500 notebook 并本地核对（见 §2.2）。

### 2.2 NotebookLM + 本地 PDF 逐字核对

这次 NotebookLM 的回答**带完整 `cited_text` 引用**（不像 P2-55 那次是空的），
但仍全部本地核过。底本同 P2-51/P2-55。

| 命令 | 印刷页 | Type / Range | *RST | Options 原文 |
|---|---|---|---|---|
| `CONFigure:LTE:SIGN<i>:CELL[:PCC]:ULDL <UplinkDownlink>` | 687-688 | `integer`，`0 to 6` | `1` | **`R&S CMW-KS550 and R&S CMW-KS510`**；`R&S CMW-KS512 for carrier-specific configuration` |
| `CONFigure:LTE:SIGN<i>:CELL[:PCC]:SSUBframe <SpecialSubframe>` | 688 | `integer`，`0 to 9` | `7` | `R&S CMW-KS550`；`R&S CMW-KS512 for value 7 plus extended cyclic prefix / for value 9 / for carrier-specific configuration` |
| `CONFigure:LTE:SIGN<i>:CONNection[:PCC]:RMC:VERSion:DL<s> <Version>` | 803 | `integer`，`0 to 1` | `0` | 条目本身无 Options 行 |
| `CONFigure:LTE:SIGN<i>[:PCC]:DMODe <Mode>` | 366 | `FDD \| TDD` | — | `R&S CMW-KS500/-KS550 for FDD/TDD` |

**四条直接影响设计的原文**（都是逐字核对的，不是转述）：

1. **ULDL 的选件是「and」不是「or」** —— `R&S CMW-KS550 **and** R&S CMW-KS510`。
   而 P2-55 建的 `satisfying_options` 是「装任一即可」的 **OR** 语义 —— **表达不了它**。
2. **取值级的固件下限**：ULDL 的 `Firmware/software: V3.0.10, **V3.0.50 value 0, 2, 3, 4, 6**`
   —— 即值 1/5 只要 V3.0.10，值 0/2/3/4/6 要 V3.0.50。SSUBframe 同型：
   `V2.1.20, **V3.5.10 value 9**`。
3. **取值级的互斥前置**：SSUBframe 原文 `Value 8 and 9 can only be used with the
   normal cyclic prefix.` —— 这是取值对**另一个参数**的依赖。
4. **表 2-39 比 FDD 的表 2-38 多一个 Version 列**，且只有两行有取值：
   10 MHz/50RB/16-QAM/TBS13 → `0: R.11` / `1: R.11-1`；20 MHz/100RB/16-QAM/TBS13 →
   `0: R.30` / `1: R.30-1`。其余行都是 `-`。
   `RMC:VERSion:DL` 的描述原文：`This command is only relevant for certain downlink
   RMCs for TDD multiple antenna configurations, see Section 2.2.19.4`。

**另一条来自 P2-55 的既有取证**（表 2-37 脚注）：带 `*` 的 TBS
`are still supported for FDD for backward compatibility reasons. They are
**not supported for TDD**` —— TDD 侧必须排除这些组合。

---

## 3. 本片要解决的结构问题

P2-55 的矩阵结构**表达不了 TDD 的三种条件**：

| 条件类型 | 实例 | 现结构能表达吗 |
|---|---|---|
| **AND 选件** | ULDL 需 `KS550` **且** `KS510` | ❌ `satisfying_options` 是 OR |
| **取值级固件下限** | ULDL 值 0/2/3/4/6 需 V3.0.50 | ❌ 只有 profile 级的 `MAC_CFG_MIN_FIRMWARE` |
| **取值级前置约束** | SSUBframe 值 8/9 只能配 normal CP | ❌ 无表达位 |

### 3.1 建议：把「条件」提升为取值的结构化字段

在 `BaseStationMacDimensionValueCapability` 上补三个字段（都可选、默认空，
**不进 digest**，与 `dimensions` 同规矩）：

```python
satisfying_options: tuple[str, ...] = ()       # 既有：装任一即可（OR）
required_options: tuple[str, ...] = ()         # 新增：必须全部装上（AND）
minimum_firmware: str | None = None            # 新增：该取值的固件下限
requires: tuple[str, ...] = ()                 # 新增：该取值的前置约束（结构化 token）
```

**为什么分成 OR / AND 两个字段而不是一个表达式**：手册这一栏只有这两种形态
（`A or B` / `A and B`），没有出现过更复杂的组合。用两个平铺字段能被门机械校验；
引入表达式语法则是「加机制」，且第一个使用者就是本片，没有第二个用例佐证。

**`requires` 用结构化 token 而不是自然语言** —— 这是 #442 那八轮换来的教训：
判自然语言的门不收敛。`requires=("normal_cyclic_prefix",)` 可以被门机械校验，
「只能配 normal cyclic prefix」这句散文不能。

### 3.2 Review 结论（用户 2026-09-02 拍板）

1. **三个字段都加**（`required_options` / `minimum_firmware` / `requires`）；
2. **`rmc_version` 本片打开**（作为矩阵维度，不作为可达取值）；
3. **`requires` 用封闭枚举**，不是自由字符串 →
   `MacDimensionPrerequisite = Literal["normal_cyclic_prefix"]`。

### 3.3 ⚠️ 实现时量到的两处前提更正（本稿 review 时没写，是错的）

**① 维度名必须是 profile 上真实存在的字段。**
`_mac_dimension_rejections` 按 `dimension in type(profile).model_fields` 取值，
声明一个 profile 没有的维度会落进「声明与 schema 脱节」那一格，把**每一条**
LTE profile 判成不兼容 —— 不是这个维度失效，是整个 adapter 失效。
所以「打开 `uldl_configuration` 维度」**必然**要动 profile schema。

由此改用 **`None`-only 字段**（`uldl_configuration: None = None`）：
字段存在 → 维度可声明；只接受 `None` → **不新增任何可达状态**；
`exclude_none` 下不进 digest → 历史冻结 profile 一字不动。
实测三条：`freeze()` 后 LTE digest 回到 main 的 `6c0ebb0e…`；
不带新键的历史 payload 原样通过 `FrozenMacTestProfile` 校验；
四条 manifest digest 全部回到 `7034550e` / `890c453c` / `c417c961` / `0c35808a`。

**② §5 的验收 2/3/4 做不到**（「造一台只装 KS550 的机器 → ULDL 应被拒」）。
兼容层没有「已装选件 / 固件版本」这两个输入 —— `satisfying_options` 自 P2-55
起就**零消费方**。新三个字段同属声明性。验收改为「**结构能区分 AND/OR、
门能机械校验**」，并加一道门把「今天它们不把关」这个现状钉住
（`test_option_and_firmware_fields_are_declarative_today`，接上消费方时会红）。
已登记 Discovered。

---

## 4. 范围建议

### 4.1 本片做

| 维度 | 建议 | 依据 |
|---|---|---|
| `duplex` | 打开到 `fdd` / `tdd` | `DMODe` Range `FDD \| TDD`（p.366） |
| `uldl_configuration`（新） | 打开 0..6，**逐值标固件下限**；选件 `KS550`+`KS510`（AND） | ULDL 属性块（pp.687-688） |
| `special_subframe`（新） | 打开 0..9；值 8/9 标 `requires=("normal_cyclic_prefix",)`；值 7(+扩展CP)/9 额外需 `KS512` | SSUBframe 属性块（p.688） |
| `rmc_version`（新） | 打开 0/1，但**仅在 TDD + 多天线 + 那两行歧义 RMC 时有意义** | `RMC:VERSion:DL`（p.803）+ 表 2-39 |

### 4.2 本片不做

| 不做 | 理由 |
|---|---|
| **cyclic prefix 维度本身** | `requires` 只声明「该取值依赖 normal CP」，不打开 CP 维度 —— 那要另取证一条命令，且本片没有它的可观察故障 |
| **TDD 的 RMC 表逐行录入** | 与 P2-55 同理：满配行够用，非满配行要同时改两个下发点 |
| **带 `*` 的 TBS 在 TDD 侧的排除** | 需要 RMC 表逐行数据支撑，随上一条一起留后续；本片在 `requires` 里留位不实现 |
| **真机认证** | 现场半，本地测试不能替代 |

### 4.3 判据（沿用 P2-55，但**不再在注释里给条数清单**）

P2-55 那份「共几条」的概括数错过三次。本片**逐格的理由以各自 reason 为准**，
矩阵声明上方只写导读。新增取值的定档一律从 `diagnostic_only` 起步，
除非同时有：命令 Range + RMC 表覆盖 + 本驱动已实现下发 + 该组合的真机证据。

---

## 5. 验收（按实现结果定稿）

1. ✅ **声明 ≠ 可达**：`duplex` 仍是 `Literal["fdd"]`，三个新字段只接受 `None`；
   矩阵声明完整取值域。门：`test_tdd_side_is_declared_but_unreachable`（枚举形态空间
   `0 / 1 / "0" / True / -1` 全拒）。
2. ✅ **AND 与 OR 分开表达且被门区分**：ULDL 每个整数取值 `required_options` 排序后
   恒为 `["KS510","KS550"]` 且 `satisfying_options` 为空；`duplex` 两格反过来。
   ⚠️ 判据是「**结构能区分**」不是「装错选件会被拒」—— 见 §3.3②。
3. ✅ **取值级固件下限按取值分组集合相等**：ULDL `{1,5}→V3.0.10`、
   `{0,2,3,4,6}→V3.0.50`；SSUB `{0..8}→V2.1.20`、`{9}→V3.5.10`。
   另有一道门要求这些串能被**驱动自己的** `_firmware_at_least` 解析。
4. ✅ **`requires` 集合相等**：带前置的取值恰为 SSUBframe 的 `{8,9}`，
   token 恰为 `("normal_cyclic_prefix",)`，且全矩阵其它取值一律不带。
5. ✅ **FDD 不回归**：148 条既有相关用例全绿；四条 manifest digest 与两条
   profile digest 实测回到 main 基线（P2-55 踩过这个坑）。
6. ✅ **13 条变异全部实跑变红**（含「digest 丢 exclude_none」「AND 写回 OR 字段」
   「删掉 None 格」「删掉整个维度」「requires 退化成自由字符串」）。
7. ⏳ **实现半（P2-56 ②）**：TDD 下发路径 + 表 2-39 满配行 + 放开取值域 +
   活体 duplex 与 profile 的一致性校验 —— 四件必须同一片做完，见 roadmap 条目。
8. ⏳ **现场半（P2-56 ③）**：真机 Attach / 业务窗口 / SAFE_IDLE / release /
   正式证据认证，非现场不替代。

---

## 6. 给 review 的三个问题（✅ 已回答，见 §3.2）

1. **§3.1 加三个字段**（AND 选件 / 固件下限 / 前置约束）是否可接受？这是「加机制」，
   但 TDD 的手册事实确实表达不了 —— 替代方案是本片只打开 `duplex` 与 `uldl_configuration`
   （AND 选件仍无法表达，只能在 reason 里写散文），把另两个维度推后。
2. **`rmc_version` 要不要本片打开**？它只在两行歧义 RMC 上有意义，而那两行属于
   「RMC 表逐行数据」——按 §4.2 本该推后。但不打开它，TDD 的 10/20 MHz 满配行就有歧义。
3. **`requires` 的 token 词表**由谁定？本片只用到 `normal_cyclic_prefix` 一个，
   要不要现在就定一个封闭枚举（而不是自由字符串）？
