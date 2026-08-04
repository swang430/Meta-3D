# P1-33 设计稿 — 按手册补齐 IRAT 的 MAC 配置命令（本地半）

> 2026-08-04 立稿。承接 P1-32（#279）：那片让缺命令时**不崩、不假成功、调用方中止**；
> 本片补上**命令本身**。现场半（真机验收）另计。

## 双实证前置

- **memory**：`project_testcase_driven_instrument_arch`（路径 B 单一真值源 + fail-loud）/
  `feedback_value_form_space`（**值的形态空间**——本片的核心风险就在这）/
  `feedback_query_notebooklm_for_uxm_f64_driver`（两层规则）。
- **手册原件（单点权威，2026-08-04 实查）**：
  `Instrument_API_Doc/Keysight UXM NR SCPI/*.md`，块内精确抽取（见下表）。
  ⚠️ **不用 NotebookLM 的转述** —— 它在 P1-32 期间把推断说成结论、后来自己撤回；
  用户定：**单点问题手册原件是权威**。

## 这不是盲试

每条命令都能在手册里逐字指到（下表给出 Type / Range / Default）。
**唯一的未知量是「LTE_NR_IRAT 这个 TAP 认不认」** —— 而这个未知量本片**不猜**：

1. 命令按手册补进 profile；
2. **每组下发后查 `SYST:ERR?`**，被拒的逐条记名；
3. 发完按开关态补 `BSE:CONFig:<celltype>:APPLY`（手册：小区 ON 时多数配置
   不发 APPLY 不进协议栈）；
4. 有 P1-32 的 fail-loud 兜底 —— 必要项没配上就 `FAILED`，绝不静默往下测。

于是「未经查证」在**现场一跑就变成实测结果**，而不是靠推断提前下结论。

## 手册核实过的命令与值形态（块内精确抽取）

| 现在发的（IRAT 上为 `None`） | 手册命令 | Type / Range | 值形态转换 |
|---|---|---|---|
| `... FULLBUFFER` | `BSE:CONFig:NR5G:SCHeduling:QCONFig:SCENario` | Enum `BASIc\|FULL_TPUT\|DL_RMC\|UL_RMC\|APC_RMC\|EVM_RMC` | → **`FULL_TPUT`** |
| `PDSCH\|PUSCH:AMC:ENABle ON/OFF` | `…:SCHeduling[:<BWP>]:<fc>:<sc>:DL:RRESource:APOLicy` | Enum `FIXed\|BLER\|DYNamic\|CQI\|…` | **不是开关**：关 AMC = **`FIXed`**，开 = `CQI` |
| `PDSCH:MCS <n>` | `BSE:CONFig:NR5G:SCHeduling:QCONFig:DL:MCS` | Integer `0..28`（默认 4） | 同为整数 |
| `RB "ALL"` | `BSE:CONFig:NR5G:SCHeduling:QCONFig:DL:NUM:PRBs` | Integer `1..273`（默认 273） | `"ALL"` → **按带宽算 PRB 数** |
| `TDD:PATTern "DDDSU"` | `…:SCHeduling:TDDPATtern:STATE` / `PERiod` / `DLSLots` / `DLSYmbols` / `ULSLots` / `ULSYmbols` | Bool；Enum `MS0P5…MS10`；Int `0..160`；Int **`0..14`** | 字符串 → **六个数**（见下） |
| `TDD:PERiod "5MS"` | `…TDDPATtern:PERiod` | Enum，默认 `MS5` | `"5MS"` → **`MS5`** |
| `HARQ:MaxTrans 4` | `…:PHY:DL:HARQ:MAXTrans` | Enum `N1…N28`，默认 `N4` | `4` → **`N4`** |
| `HARQ:PROCesses 16` | `…:PHY:DL:HARQ:PROCesses` | Enum `N1…N32`，默认 `N16` | `16` → **`N16`** |
| `CSIRS:PORTs <n>` | `…:CSI:RESource:CONFig:NZP:<cri>:RM:NPORts` | Enum **`P1\|P2\|P4\|P8\|P12\|P16\|P24\|P32`** | `4` → **`P4`**，且多一个 `<cri>` 维度 |
| `BTHRoughput:DL:TSTatistics:COUNt` | ⛔ **NR5G 非边链路无此命令** | — | 见「stat_count」一节 |
| —（新增前置） | `BSE:CONFig:<celltype>:APPLY` | Imm Action | 小区 ON 时必发 |

⚠️ **纠正了 roadmap 08-03 表里的两处**（该表此前已被裁掉一处 AMC 错）：
- Full Buffer 的 token 是 **`FULL_TPUT`**，不是散文里的 "Full Throughput"；
- 统计窗口那格指的 `BSE:MEASure:NR5G:BTHRoughput:LENGth[:ALL]` 其实是
  **`NR5G:SLINk:`（V2X 边链路）**那条 —— 手册里带 `LENGth` 的只有
  `LTE:<cell>:` / `NBIot:<cell>:` / `NR5G:SLINk:` 三种，**普通 NR 小区没有**。

## 三个决策（2026-08-04 用户拍板）

### ① TDD 特殊槽符号数 → TestCase 加两个显式字段

`"DDDSU"` 数得出 3 个 D、1 个 U，**数不出 S 槽里几个 DL 符号 / 几个 UL 符号**，
而手册要的正是 `DLSYmbols` / `ULSYmbols`（各 `0..14`）。

→ `MIMOOTAConfiguration` 加 `tdd_dl_symbols` / `tdd_ul_symbols`，
**默认取手册默认 6 / 4**（不是我编的数）。走契约四步。

⚠️ **顺带发现的隐患**：`"DDDSU"` + `"5MS"` **只在 15 kHz SCS 下自洽** ——
5 个 slot 在 30 kHz（n78 常用）下是 **2.5 ms**。两者现在可以静默打架。
本片下发前做**一致性校验**：`slots × slot_duration(SCS) == period`，不符 fail-loud。
（同 memory「路径 B 多方一致性校验」。）

### ② `stat_count`：保留字段，显式标「本仪器不支持」

NR5G 侧手册无对应命令。**不删契约**（别的仪器可能有），
但驱动把它归进**显式的「已知无对应命令」清单**，结果里带出来、报告里写明
「统计窗口不受控」。**不假装配上了**，也不静默忽略。

### ③ Full Buffer / MCS / PRB 走 Quick Config

`QCONFig:SCENario FULL_TPUT` + `QCONFig:DL:MCS` + `QCONFig:DL:NUM:PRBs` 三条搞定，
不必定 `<BWP>/<fc>/<sc>` 三个维度。手册对 `FULL_TPUT` 的说明正是
「按选定的 TDD Pattern / RB 数 / MCS **最大化吞吐量**」，即本测试要的语义。

⚠️ AMC 那条**没有** Quick Config 形式，只能走 slot 级
`DL:RRESource:APOLicy` —— 需要定 `<BWP>/<fc>/<sc>`，用驱动现有的 `_bwp_id`
与 `FC0`/`SC0`（**这三个维度的取值是本片唯一需要现场确认的一处**，已记进现场清单）。

## 范围（本地半）

1. `uxm_command_profiles.py`：按上表补 IRAT profile；**同时核 5G profile 现有形式**
   （P1-32 已证它多处对不上手册）；
2. 驱动：值形态转换（`FULL_TPUT` / `FIXed` / PRB 数 / `MS5` / `N4` / `N16` / `P4`）
   + TDD 六参数展开 + SCS 一致性校验；
3. **`APPLY` 前置 + 每组发后查 `SYST:ERR?`**，被拒命令逐条记名进结果；
4. `stat_count` 归入显式「已知无对应命令」清单；
5. `tdd_dl_symbols` / `tdd_ul_symbols` 契约四步。

**不做**：真机验收（现场半）、GUI 表单（另计）。
