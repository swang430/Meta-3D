# P0-2 设计稿 — 仪表配置单一真值源(先落 UXM)

> **状态**:设计稿,待 review,**尚未动代码**。
> **对应 todo**:[`guides/onsite-20260721-todo.md`](../guides/onsite-20260721-todo.md) P0-2
> (2026-07-21 现场收工写的第二条 P0)。
> **上位架构**:[`architecture/testcase-driven-instrument-config.md`](../architecture/testcase-driven-instrument-config.md)
> —— 本稿是那份架构在 UXM 上的**现场验证版落地**,不新起炉灶。
> **手册依据**:NotebookLM「Keysight UXM5G 网络测试 SCPI 编程指南」
> `236d9621-e3ce-4ed1-a8e1-7819b674dbcd`,会话 `adfb5e02-4f11-450b-a91d-801d22667604`
> (2026-07-26 两轮问答,逐条出处见下)。
> **方言前提**:现场那台 UXM 跑的是 **LTE_NR_IRAT**(命令走 `BSE:` 族,
> `uxm_command_profiles.py:311` 起的 `UxmLteNrIratProfile`,2026-05-13 现场实测确认)。
> 手册覆盖的正是 `BSE:` 族;另一套方言 `5G_NR_Test`(裸 `CONFig:` / `CALL:` 族)
> **手册查不到**,本稿对它只提结论不提依据。

---

## 0. 一句话

todo 里 P0-2 原本写的是「**我错误假设 UXM 会保留配置**」。查证下来,**这个自责只对了一半**:
真正的问题不是"假设它记得",而是 —— 我们**问错了寄存器、写完不生效、核对读的是自己写进去的那份**。
跟 F64R-1 是**同一个母题的第二台仪器**:该问仪器的地方,我们在问自己。

---

## 1. 现场症状 → 查证到的七个根因

> 每条都给出**代码锚点**和**手册出处**,并标注确定性:
> 🔴 = 代码 + 手册双向对照确认;🟡 = 强推断,需现场一次验证。

### R1 🔴 ⭐ attach 轮询问的是"开关",不是"状态" —— 这条最贵

`start_signaling()` 激活小区后轮询 UE attach,查的是:

```
BSE:CONFig:NR5G:CELL1:ACTive:STATe?      ← 我们自己刚写进去的那个 0/1 开关
```

代码锚点:[`uxm_base_station.py:1605`](../../api-service/app/hal/uxm_base_station.py#L1605)
(`CELL_STATE_QUERY`,定义在 `uxm_command_profiles.py:334`)。
紧挨着的注释白纸黑字写着「UXM 返回: "IDLE" / "ATT" / "CONN" / "OFF"」,判据是
`if "CONN" in state_str or "ATT" in state_str`。

**但这条命令返回的是 `0` / `1`** —— 它是我们写 `ACTive:STATe 1` 的那个同一个旋钮的回声。
`"CONN"` 永远不可能出现在 `"1"` 里 → **这个循环在任何情况下都不会判定 attach 成功**,
只会跑满超时然后 `return False`。

手册里真正的小区状态查询是另一条:

```
BSE:STATus:NR5G:<cell>?     →  OFF | ON | CONNected | IDLE | AGGRegated | ACTivated
```
> 手册原文(NR Cell > Config,"NR Connection Status"):
> `Range : OFF | ON | CONNected | IDLE | AGGRegated | ACTivated`

—— 正是那句注释期望的那种值。**注释描述的是对的那条命令,代码发的是错的那条。**

**⚠ 与现场 #43 的关系(必须说清,别过度声称)**:现场 07-21 记录是「DUT 已到 -96 dBm RSRP,
未完成 attach 注册」。R1 **不能**证明手机当时其实连上了 —— -96 dBm 本来就偏低,可能真没连。
**能确定的只有一件事**:即便它连上了,**当前实现也报不出来**。所以下次现场在这条修好之前,
"没 attach"这个结论本身不可信。

### R2 🔴 三个消费点,两个读错 —— 而**正确答案就写在第三个里**

`CELL_STATE_QUERY` 全驱动有三处消费:

| 处 | 位置 | 读它干什么 | 对不对 |
|---|---|---|---|
| ① | `start_signaling` 轮询(1605) | 判 UE attach | ❌ R1 |
| ② | `get_cell_state`(1651) | 对外报小区状态 | ❌ 按 `OFF/CONN/ON/IDLE` 分支,`"0"`/`"1"` 全落 `CellState.ERROR` |
| ③ | `set_cell_config` 改 BW 前探测(889) | 判"要不要 OFF→写→ON 环绕" | ✅ **合理** —— 这处问的本来就是"开关在哪个位置" |

③ 处的注释(Codex #195 复扫加的)**已经写明**:

> 「5G_NR_Test 方言回文本态 (IDLE/ATT/CONN/ON/OFF, 见 get_cell_state 先例),**IRAT 回 "0"/"1"**」

—— 也就是说,"这条命令在现场那台机器上返回 0/1"这个事实,**代码库里已经有人写下来了**,
就在同一个文件里,只是没人回头去改 ① 和 ②。这也让 R1 从推断升级为确证。

另外 `start_signaling` 写完激活命令后**无条件** `self._cell_state = CellState.ON`
(第 1591 行),这是个不问仪器的缓存断言 —— 跟 F64 那个 `_emulation_running` 一模一样。

现场那句「`ACTive=1` 但 `STATus` 持续 `OFF`」现在有了解释:
**`ACTive=1` 是我们自己写的值的回声,`STATus=OFF` 才是仪器的真话。** 两个数不矛盾,
是我们把前者当成了后者的替身。

### R3 🔴 小区 ON 态改配置,从不发 `APPLY` → 静默不生效

手册(General > Miscellaneous commands,"Apply Configured Changes"):

> "Update the stack with the changes to configuration that has been made to all the cells
> of the selected technology. **This is not needed if the Cell is Off** (any changes made
> while a cell is off will be automatically applied when that cell is turned On)."
> 并注明:"**most configuration changes won't be applied until this command** ... is used."

即:**小区 ON 时写的配置进缓存,不发 `BSE:CONFig:NR5G:APPLY` 就不进协议栈。**

全仓 grep:`APPLY` 在 UXM 驱动里只出现在 `RRC_RECONFIG_APPLY`(RRC 重配,另一回事),
**`BSE:CONFig:NR5G:APPLY` 零调用**。

我们目前只在**改带宽**时做 `OFF → 写 → ON` 环绕(P1-19,2026-07-03 实测 `-221` 逼出来的),
环绕路径靠"关了再开"天然让配置生效。**其余所有参数**(ARFCN / band / DL 功率 / SSB 功率 …)
在小区 ON 时是直写的 —— 写进缓存,没人 APPLY,协议栈还在跑旧配置。

手册补充的两条关键属性:
- **作用域是整个技术层,不是单小区**:带小区的写法(`...:CELL1:APPLY`)手册标为
  **deprecated**,且行为与不带小区完全相同 —— 都会把**所有 NR 小区**的挂起配置一起刷下去。
- **没有完成查询**:手册归类为 "Imm Action / No query",未提及 `*OPC?`。
  确认方式只能是 APPLY 之后轮询 `BSE:STATus:NR5G:<cell>?`。
- OFF 态误发 APPLY **无害**(多余而已)。

### R4 🟡 回读对账读的是缓存值 → 假绿

`_readback_verify()`([`uxm_base_station.py:695`](../../api-service/app/hal/uxm_base_station.py#L695),
P1-19 加的)对 ARFCN / BW / DL 功率逐项回读比对,读的是 `BSE:CONFig:...?` 系列。

手册**没有明说** APPLY 之前查询返回缓存值还是生效值;NotebookLM 按标准 SCPI 惯例判断
`BSE:CONFig:...?` 读的是**上层软件缓存**(要看协议栈真实状态得用 `BSE:STATus:...` 族),
并明确指出**手册没有任何命令可以查询"存在未应用的挂起修改"**。

如果这个判断成立(标 🟡,需现场验一次),那么 R3 + R4 合起来是个闭环假象:
**我们在 ON 态写了新值 → 没 APPLY → 协议栈还用旧值 → 回读读到缓存里的新值 → 对账通过 → 报绿。**
这正是 memory `feedback_test_real_dispatch_not_display_field` 的母题(测真实生效那一端,
不停在自写值回读),也是 P2-11 Phase 6 当年在 MIMO layers 上踩过的同一个坑
(Codex on #114:不能读 `CONF:...:LAY?` 配置旋钮,要读 UE 协商能力)。

**验法(现场一次即可)**:小区 ON → 写一个明显不同的 ARFCN → **先别 APPLY** → 回读
`BSE:CONFig:...:DL:ARFCN?` 看返回新值还是旧值;同时看 `BSE:STATus:NR5G:<cell>?` 和频谱。

### R5 🟡 下发顺序与手册的 16 步推荐序不符;"本机不支持"清单很可能是**命令拼错**

手册在 NR Cell > Config 给了**16 步推荐配置顺序**,理由是"频率参数之间依赖关系众多,
乱序会让中间量计算越界"。逐条对照:

| 手册序 | 手册命令 | 我们现在 |
|---|---|---|
| 1 Specification Version | `...:SPEC:VERsion` | ❌ 不设 |
| 2 Carrier Role | `...:AGGRegation:ROLE` | ❌ 不设 |
| 3 Freq Range (FR1/FR2) | `...:FREQuency:RANGe` | ❌ 不设 |
| 4 Enhanced Channel Raster | `...:ENHance:CHANnel:RASTer:STATe` | ❌ 不设(需 Rel-18 license) |
| **5 Duplex Mode** | `...:DUPLEX:MODe` | ⚠ 顺序**相反**(见下) |
| **6 Band** | `...:BAND` | ⚠ 我们先 BAND 后 DUPLex |
| **7 SCS Common** | `...:SUBCarrier:SPACing:COMMon` | ⚠ 标为"本机不支持" |
| **8 Bandwidth** | `...:DL:BW` / `...:UL:BW` | ✅ 有,但排在 SCS **之前** |
| 9 Offset To Carrier | `...:DL:OTCarrier` / `UL:OTCarrier` | ❌ 不设 |
| 10 PointA ARFCN | `...:DL:POINta` / `UL:POINta` | ⚠ 标为"本机不支持" |
| **11 ARFCN** | `...:DL:ARFCN` / `...:UL:ARFCN` | ✅ 有(只发 DL) |
| 12 SSB SCS | `...:SSB:SUBCarrier:SPACing` | ❌ 不设 |
| 13 SSB ARFCN | `...:SSB:ARFCN` | ⚠ 标为"本机不支持" |
| 14 CORESET#0 Index | `...:SSB:COReset0` | ❌ 不设 |
| 15 Tx/Rx Resource | `...:RTX` | ❌ 不设 |
| 16 Test Channel Location | `...:TESTChanLoc` | ❌ 不设 |

两处**顺序反了**:
- 我们的 `set_cell_config` docstring 明写「`DUPLex` **必须在 BAND 之后**设置」——
  手册是 **Duplex(5) 在 Band(6) 之前**。这条"必须"是哪来的,代码里没留依据。
- 我们 BW 在 SCS 之前,手册是 **SCS(7) → BW(8)**。

更值得查的是那份 **"Verified unsupported in this app"** 清单
([`uxm_command_profiles.py:371-385`](../../api-service/app/hal/uxm_command_profiles.py#L371)):
`CELL_SCS` / `CELL_DUPLEX` / `CELL_DL_POINTA` / `SSB_ARFCN` / `MIMO_DL_LAYERS` … 全被标成
本机不支持(实测 `-113 Undefined header`)。**但手册说这些命令都存在。**

本项目有**明确先例**:DL 功率和 SSB 功率当初也被判定"不支持",实测 `-113`;
后来发现是**拼写不对** —— `:PHY:DL:POWer` → 正确是 `:DL:POWer`,
`:SSB:POWer` → 正确是 `:SSB:POWer:ADVertised`(见同文件 357-364 行的注释)。
SCS 手册写的是 `SUBCarrier:SPACing:COMMon`,不是简写的 `SCS`;
duplex 手册写的是 `DUPLEX:MODe`,不是 `DUPLex`。**"这台机器不支持"很可能一直是
"我们发的命令名不对"。** 这跟 F64 review 母题⑤(禁盲试 / 发手册里不存在的命令)是同一件事,
只是方向相反:F64 是发了手册没有的,UXM 是**没发手册有的**。

### R6 🔴 HAL-init 会把默认配置写进硬件,写失败只打 WARNING,就绪照样报绿

后端每次启动 / HAL 重载,`_initialize_from_db` 会在 connect 成功后
**主动把默认拓扑 profile 下发到 UXM**:
[`instrument_hal_service.py:753-799`](../../api-service/app/services/instrument_hal_service.py#L753)
→ `apply_topology_profile()` → `set_cell_config(profile.to_config_dict())`。

所以现场那句「后端重启后 UXM 变成了别的配置」——**不是 UXM 忘了,是我们自己改的**。

而且:`if not result.get("applied"): logger.warning(...)`,然后**紧接着**就
`report_rows.append(DriverReadinessRow(status="ok", ...))`(第 803 行)。
**默认配置根本没落上,就绪面板照样绿。** 这是这一整个系列一直在删的"假成功"的又一处。

### R7 🔴 系统默认改了不一定生效 —— binding 里的显式选择压过它

`topology_profile_id` 的优先级是:`connection_params.topology_profile_id`(操作员显式选的)
**>** `driver._default_topology_profile_id`(系统默认)。

2026-07-20 #214 把系统默认改成了 `caict_n78_3550_4x4_baseline`(636666 / BW40 / -46)。
**但如果那台机器的 binding 里还存着旧的显式选择,改系统默认等于没改。** 现场观测到的
`623334 / BW100 / -50` 里,`623334` 在我们整个代码库里搜不到 —— 它不是我们任何一个
profile 的值,更像是 UXM Test App 自己的出厂默认。也就是说当时**很可能是 R6 的
"apply 失败但报绿"**,而不是我们下发了一个错的 profile。这条要现场确认(见 §6)。

---

## 2. 范围

**做**:UXM 小区级配置的「**下发 → 生效 → 核对**」闭环,以及 HAL-init 默认配置的假绿。

**不做**(明确划走,避免这份设计滚成大改):
- ARCH-1(砍计划管理 / 执行队列)—— 独立大改,先出设计。
- P2-3(内生经验配置的存储与加载)—— 那是"参数从哪来"的另一条路径,本项只管"参数怎么落到位"。
- F64 侧的 P0-4 / F64R-5 —— 另有手册答案,单独做。
- P1-3 的 UXM 查询串包防护 —— **但 R1/R2 修完可能顺带解释掉一部分**:
  `BSE:STATus?`(不带小区、不带技术)读回吞吐 JSON,而手册里小区状态是
  `BSE:STATus:NR5G:<cell>?` —— 我们那条本来就不是手册里干这活的命令。
  本稿只记录这个线索,**不在本项修 P1-3**。

**泛化**:用户在 todo 里明确要求「泛化到所有参与测试的仪表,绝不靠仪表继承来的旧值」。
本稿把这条写成 §4 的**通用契约**,但**只在 UXM 上落实现** —— 其它仪表按契约逐个补,
不在本项一次做完。

---

## 3. 设计

> 修法形状按 review 纪律的优先级排:**去掉 > 换源 > 收窄 > 加机制**。
> 本稿 6 条里 4 条是换源/去掉,只有 D2 是"加"(且是手册要求的必发命令)。

### D1 【换源】小区状态改问 `BSE:STATus:NR5G:<cell>?`

- 命令表加 `CELL_STATUS_QUERY = "BSE:STATus:NR5G:{cell}?"`(IRAT 方言;
  `5G_NR_Test` 方言手册无依据,**留 `None`**,让 `_cmd()` 返回 None 走"无此能力"路径)。
- `get_cell_state()` / `start_signaling()` 的轮询**全部换成这条**。
- 返回值按手册枚举做**白名单**解析(`OFF|ON|CONNected|IDLE|AGGRegated|ACTivated`),
  枚举外的字符串 → 记 WARNING 返回"读不到",**不猜**(照搬 F64R-1 七态白名单的做法,
  它当时正是靠白名单挡住了会话错位读回的噪声)。
- `start_signaling` 里那句无条件 `self._cell_state = CellState.ON` **去掉** ——
  状态只从这条查询来,不从"我发了命令"来。
- ⚠ 现有的 `ACTive:STATe?` **不是没用**:它是"开关位置"的合法查询,
  保留给"我到底有没有下过激活命令"的审计,但**不再当状态判据**。
  两者名字要在代码里区分开(`cell_switch` vs `cell_status`),否则下一轮又会混。

### D2 【加】补 `BSE:CONFig:NR5G:APPLY`,并写死"写入契约"

驱动内部统一一条规矩,写进 `set_cell_config` 的 docstring:

```
小区 OFF 时写配置  → 不发 APPLY(手册:开小区时自动应用)
小区 ON  时写配置  → 本批次写完后必须发一次 BSE:CONFig:NR5G:APPLY
                    → 然后轮询 BSE:STATus:NR5G:<cell>? 确认
```

- APPLY **每批一次**,不是每条参数一次(它是技术层全局动作)。
- **不发带小区的 `...:CELL1:APPLY`** —— 手册标 deprecated 且行为完全相同,徒增误解。
- APPLY **没有完成查询**,不要发 `*OPC?` 等它(手册归类 Imm Action / No query);
  确认靠 D1 的状态轮询。
- ⚠ **副作用要写进注释**:APPLY 会把**所有 NR 小区**的挂起配置一起刷下去。
  多小区(SCell)场景下,别的小区如果有半截配置,会被这一下带出去。
  当前只用 CELL1,先记录,不加机制。

### D3 【换源】核对分两层:"我写进去了" ≠ "它在用"

`_readback_verify` 现在这一层保留,但**改名并降级定位**为**配置回读**(第一层:
证明命令被接受、值没被钳位)。在它之上补**第二层生效核对**:

| 层 | 读什么 | 证明什么 |
|---|---|---|
| 一层 配置回读(现有) | `BSE:CONFig:...?` | 命令收到了、值没被拒/钳 |
| 二层 生效核对(新) | `BSE:STATus:NR5G:<cell>?` + 已有的频率一致性网 | 协议栈真的在用 |

- 二层**不新建一套** —— P2-11 Phase 1 的频率一致性网(`get_frequency_identity` /
  `read_live_frequency_identity`)已经在做这件事,本项只是把小区状态并进去,
  并把"APPLY 之后才允许判绿"这个时序钉住。
- 一层的覆盖面从 3 项(ARFCN / BW / DL 功率)扩到**本次下发过的每一项**
  (band / duplex / SCS / UL BW / SSB 功率 / layers …),用 D4 重验后确认可用的查询命令。
  **原则:下发了什么就回读什么,不下发的不读**(避免读到无关默认值当"不一致")。
- ⚠ `SUPPORTS_CONFIG_READBACK` 这个开关要重新审:`5G_NR_Test` 方言因为
  "配置查询实证超时"(2026-05-27)把回读整个关掉了。**回读关掉 = 一层二层同时没有**,
  等于裸奔。本项不改那个方言的开关(没手册依据、没现场),但要在 `readiness_metadata`
  里**如实暴露**"本方言无配置回读",别让操作员以为有。

### D4 【去掉】重验并删掉那份可能是错的"本机不支持"清单

对 R5 表里标 ⚠ 的每条,用**手册的确切写法**在真机上各试一次(`SYST:ERR?` 判 `-113`):

| 我们标"不支持" | 手册确切写法 | 备注 |
|---|---|---|
| `CELL_SCS` | `BSE:CONFig:NR5G:<cell>:SUBCarrier:SPACing:COMMon` | 名字完全不同 |
| `CELL_DUPLEX` | `BSE:CONFig:NR5G:<cell>:DUPLEX:MODe` | 少了 `:MODe` |
| `CELL_DL_POINTA` | `BSE:CONFig:NR5G:<cell>:DL:POINta` | 拼写待核 |
| `SSB_ARFCN` | `BSE:CONFig:NR5G:<cell>:SSB:ARFCN` | 拼写待核 |
| `MIMO_DL_LAYERS` | `BSE:CONFig:NR5G:<cell>:PHY[:<BWP>]:PDSCh:MMIMolayers` | 名字完全不同 |

**能通的就从"不支持"清单里删掉并接进下发序列;真不通的,把 `SYST:ERR?` 原文和试的
确切命令写进注释** —— 免得下一轮又有人"重新发现"它可能只是拼错了。
这一步**必须现场做**(禁盲试:不在没仪器的时候改命令表)。

下发顺序改成手册的 16 步子集,**按手册序**,能设的都设:
`FREQuency:RANGe → DUPLEX:MODe → BAND → SUBCarrier:SPACing:COMMon → DL/UL:BW →
DL/UL:POINta → DL/UL:ARFCN → SSB:SUBCarrier:SPACing → SSB:ARFCN → SSB:COReset0`。
现有 docstring 里那句「DUPLex 必须在 BAND 之后」**删掉**(与手册相反且无依据)。

### D5 【去掉】HAL-init 的假绿

- `apply_topology_profile` 返回 `applied=False` 时,就绪行**不许报 `ok`** ——
  报 `warn`(或 `fail`,见下)并把 `reason` 带进 `detail`,让操作员在就绪面板上直接看见。
- **`ok` / `warn` / `fail` 怎么定,是本稿唯一需要拍板的口子**(见 §7 待决①)。
- `connection_params.topology_profile_id` 指向一个已不存在的 profile 时,
  现在只打 WARNING 然后**什么都不应用**;这种"操作员的选择已失效"也要进就绪行。

### D6 【收窄】继承模式(开关 1)与本项的关系 —— 不冲突,但要补一句

`uxm_config_mode="inherit"`(#216 现场加的)是"跳过小区级下发、沿用仪器当前态",
表面上和 P0-2「绝不靠继承来的旧值」矛盾。**实际不矛盾**:inherit 已经是**知情继承**
—— 它跳过下发但**仍用 `read_live_frequency_identity()` 从仪器读回实际值跟 TestCase 比**,
对不上照样按 `precheck_strict_frequency` 拦。

本项对它只做一件事:**把 D1 的小区状态核对也纳入 inherit 路径**
(现在 inherit 只核对频率身份,不核对小区到底起没起)。
`uxm_config_mode` 字段注释里那份"inherit 仍会写 UXM 的五件事"清单要同步更新。

---

## 4. 通用契约(用户 review 要求的泛化,先立规矩后逐台落)

每个参与测试的仪表,**每个测试项开跑时**都必须走同一套:

1. **值只从测试参数来**(测试例 / 手机配置 / SIM 配置),**不用仪表上一次留下的值**。
   没给值的参数要么补成测试参数驱动,要么 fail-loud,**不静默用默认**。
2. **下发按厂商手册的推荐顺序**,不按我们觉得顺的顺序。
3. **下发完要有一次"让它生效"的动作**(UXM 是 `APPLY`;别的仪表各有各的,
   F64 是 `GO`,转台是等到位)—— 这一步**不能默认它自动发生**。
4. **核对分两层**:配置回读(命令收到了)+ 生效核对(它真在用)。
   **只有第二层能判绿。**
5. **报绿的前提是三方一致**:测试参数 == 配置回读 == 生效核对。任一读不到 →
   如实报"读不到",不当成一致。

这份契约的落点是各驱动的 `set_*` 方法 + measure 的 precheck 门。**本项只在 UXM 上兑现**,
其它仪表按此逐台补(F64 的对应工作已在 F64R-1 完成大半:`STATE?` 就是它的第二层)。

---

## 5. 切片建议

| 切片 | 内容 | 本地可做? | 依赖 |
|---|---|---|---|
| **S1** | D5(HAL-init 假绿 + stale 选择进就绪行) | ✅ 纯本地,mock 可测 | 无 |
| **S2** | D1(状态换源)+ 白名单解析 + 去掉缓存断言 | ✅ 本地写 + 假驱动测 | 无 |
| **S3** | D2(APPLY)+ D3 两层核对骨架 | ✅ 本地写 + 假驱动测 | S2 |
| **S4** | D4 命令重验 + 顺序对齐 | ❌ **必须现场** | S3 |
| **S5** | D6 inherit 路径并入状态核对 | ✅ 本地 | S2 |
| **S6** | 现场端到端:一次 attach 走通 | ❌ **必须现场** | S4 |

S1–S3 + S5 **本地可以先全做完**,这正是 governance 那条"下次去现场前软件链路先在本地走通"。
S4 是现场那 15 分钟就能跑完的命令重验,**排进 F64R-7 那份开机清单里一起做**。

---

## 6. 验收标准

**本地(S1/S2/S3/S5)**:
- 假驱动模拟"激活后状态一直 OFF" → `start_signaling` 在超时后**如实报失败并带上读到的状态字面值**
  (现在是超时报失败但没人知道读到了什么)。
- 假驱动模拟"状态返回 `CONNected`" → 判定 attach 成功。**变异自验**:把 D1 改回
  `ACTive:STATe?` 这条测试必须变红(防"绿≠覆盖")。
- 假驱动模拟"ON 态写配置" → 断言批次结束后**发过一次** `BSE:CONFig:NR5G:APPLY`;
  OFF 态写配置 → 断言**没发**。
- `apply_topology_profile` 返回 `applied=False` → 就绪行不是 `ok`。**变异自验**:
  改回报 `ok` 必须变红。

**现场(S4/S6)**:
- R5 表里 5 条命令逐条有结论(通 / 不通 + `SYST:ERR?` 原文),清单更新。
- R4 的缓存 vs 生效验一次,结论写回本文档。
- 一次完整 attach:配置 → APPLY → `BSE:STATus:NR5G:CELL1?` 读到 `CONNected`。

---

## 7. 待决 / 风险 / 已知未知

**待决①(需要拍板)**:D5 里 HAL-init 应用默认配置失败,就绪行报 `warn` 还是 `fail`?
- 报 `fail` = 后端起来后仪表直接不可用,**bring-up 会被挡住**(默认配置本来就是"锦上添花",
  失败不代表仪表坏了)。
- 报 `warn` = 操作员看得见但不挡路,**代价是可能被忽略**。
- **我的建议:`warn` + 在 detail 里写明"仪表当前配置未知,正式测试前必须走一次下发"**。
  理由:默认配置属于路径 A(bring-up 捷径),它失败不该阻断路径 A 本身;
  真正该 fail-loud 的是路径 B —— 而路径 B 有 measure 的 precheck 门兜着。

**风险①**:APPLY 是技术层全局动作,会把所有 NR 小区的挂起配置一起刷。当前只用 CELL1,
影响面为零;将来上 SCell 时这条要重新审。**已写进 D2 注释,不加机制。**

**风险②**:D4 要在现场改命令表。**禁盲试** —— 只按手册的确切写法试,一条一条试,
每条读 `SYST:ERR?`,不即兴发挥。现场不写新逻辑,只填"通/不通"。

**已知未知(不装懂)**:
- R4(回读是缓存还是生效)手册没写死,是按标准 SCPI 惯例推的 —— **必须现场验**,
  验完把结论写回本节。如果结论是"回读的就是生效值",D3 的二层可以简化,但 D2 的 APPLY 照样要发。
- `5G_NR_Test` 方言(裸 `CONFig:` / `CALL:` 族)手册查不到,本稿的 D1/D2 对它**没有依据**。
  该方言的对应命令留 `None`,走"无此能力"路径,**不照抄 IRAT 的写法去猜**。
- R7 里那个 `623334` 到底哪来的,现在只是推断(疑似 UXM 出厂默认)。现场开机第一件事
  顺手查一次 binding 的 `topology_profile_id` 和仪器实际值,把这条坐实或推翻。
