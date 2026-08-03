# 设计稿 — UXM KPI 回读命令全错（吞吐量/BLER/CQI/RI/RSRP/SINR 八个字段没一个真的）

> 状态：**✅ 已实现**（用户 2026-08-03 review 后拍板：吞吐量 average 与 current
> **两个都存成独立字段**；`uxm_kpi_readback` 诊断序列**单独一片**，本 PR 不放）
> 立项来源：2026-08-03 用户在看 P1-30 的日志时问「为什么会有吞吐量 JSON 记录在 log 里？
> 是实际的吞吐量还是吞吐量指标？」—— 一问问出根因。
> 用户定的口径：**「不需要记录真实传输的数据，而是要记录仪表和终端上报的真实参数，
> 从而获得吞吐量的实际结果。」**

---

## 0. 双实证前置（⓪⁺ ①）

| 项 | 结论 |
|---|---|
| **memory 查询** | 已做。命中 `feedback_query_notebooklm_for_uxm_f64_driver`（本片正是它管的场景）、`feedback_effective_end_not_nominal`（"猜键名"是标称端）、`feedback_review_findings_verify_premise_first`（仪器语义先查手册）、`project_f64_driver_review_20260723`（F64 也做过同型 review，主线是"该问仪器的地方在猜"——**UXM 这次是同一个主线**） |
| **NotebookLM** | **必查已查**（UXM notebook `236d9621`，三轮追问）。所有命令形式、返回元素个数、字段含义、单位、前置条件均有手册出处 |

---

## 1. 目的 —— 要修的那**一个**可观察故障

> **`RealUxmDriver.get_throughput_metrics()` 在真机上返回的 8 个 KPI，没有一个是真的。**

这是**测量链路的终点** —— 吞吐量、BLER、CQI、RI、RSRP、SINR 就是这套 MIMO OTA 系统要交付的东西。

### 实证：真机日志里每条命令实际回了什么

口径：全部 31 个 `scpi.log*`，按 `query` 字段配平。

| 字段 | 现用命令 | 真机实际回复 | 我们解析成 | 判定 |
|---|---|---|---|---|
| `dl_throughput_mbps` | `BSE:…:BTHRoughput:DL:TSTatistics:JSON?` | `{"CellIndex":0,"ProgressCount":1000,"Tx1Info":{"Counts":{"Ack":1240,…` **（HARQ 重传统计，无吞吐量字段）** | **0.0** | ❌ 命令语义完全不对 |
| `dl_bler` | `…:DL:BLER:STATistical:ALL?` | `IDLE,UNKN,0,0` **（Early Pass/Fail 状态机，不是 BLER）** | **0.0** | ❌ 命令语义不对 |
| `ul_throughput_mbps` | `MEASure:NR5G:…:UL:TSTatistics:JSON?` | **发 1 次、无回音** | 0.0 | ❌ 命令不存在 |
| `ul_bler` | `MEASure:NR5G:…:UL:BLER:STATistical:ALL?` | **从没发过** | 0.0 | ❌ |
| `cqi` | `MEASure:NR5G:…:CSI:CQI:STATistics?` | `7.92E+04, 0.0, 9.91E+37, …` | **79200** | ❌ **取错下标**（idx0 是**首个 CSI 样本的绝对子帧号**，不是 CQI 也不是样本数）—— 比 0 更糟，是个假的大数 |
| `rank_indicator` | `MEASure:NR5G:…:CSI:RI:HISTogram?` | 全 `0` 或全 `9.91E+37` | **0** | ⚠️ **加权逻辑本来是对的**（`(i+1)`）；真正错的是命令缺 `BSE:` 前缀 + 缺 `CSI:STARt` 前置 + NaN 当真值。**我一度把权重改成 `i`，那是回归，已撤回**（见 §4⁺④） |
| `rsrp_dbm` | `MEASure:NR5G:…:UEReport:RSRP:STATistics?` | **发 1 次、无回音** | -999.0 | ❌ **手册里没有这条命令** |
| `sinr_db` | `MEASure:NR5G:…:UEReport:SINR:STATistics?` | **发 1 次、无回音** | 默认 | ❌ 同上 |

⚠️ **谓词**：「发 1 次、无回音」只能说**有去无回**，不能断言"仪器拒绝了" —— P1-30 之前日志不记 ERR 行，判断不了（这正是 P1-30 那片留下的缺口）。但结合"手册里没有这条命令"，最可能的解释是 undefined header。

### 为什么这些命令在现场"看起来在跑"

现场用的是 `UxmLteNrIratProfile`，它**只覆盖了 DL 那一条**（补上 `BSE:` 前缀），
CQI / RI / RSRP / SINR / UL 全部**继承基类的无前缀形式**。而 IRAT Test App 的命令
**全部根在 `BSE:` 下** —— 所以那几条一发就是 undefined header，而
`get_throughput_metrics()` 每个字段都是 `except: pass`，**一句话都不报**。

### 附带的第三个错：前置条件全缺

手册明确（三处独立出处）：

- 吞吐量 / BLER 累积由**全局** `BSE:MEASure:NR5G:BTHRoughput:STATe ON` 开启，
  `:CLEar` 清零。我们**从没发过**。
- CSI（CQI/RI）必须显式 `BSE:MEASure:NR5G:<cell>:CSI:STARt`，否则查询恒返
  `9.91E+37`（SCPI 的 NaN）—— **跟我们观测到的一模一样**。我们**从没发过**。
- 我们在发的 `BTHRoughput:DL:TSTatistics:STARt` / `:STOP`，**手册的命令树里根本不存在**。
  代码里那句 `[UXM] BTHR:DL:START failed — falling back to plain query` 的 warning
  说明它一直在失败，只是没人看。

---

## 2. 范围（⓪① 四行契约）

```
搜索命中：memory feedback_query_notebooklm_for_uxm_f64_driver（本片正是它管的场景）
          目标文件禁令：uxm_command_profiles.py:349「attach/状态判定一律用
          CELL_STATUS_QUERY」—— 本片不碰状态判定，不冲突
必要性：真机上 get_throughput_metrics() 的 8 个 KPI 没有一个是真的
        （测量链路的终点，也就是这套系统要交付的东西）
范围：动 2 个生产文件（uxm_command_profiles.py 命令表 + uxm_base_station.py 解析与前置序列）
      枚举到 F64 侧同型问题、CMW500 的同名函数、UE 测量报告的 L3/L1 两条路径，本次一处不做
爆炸半径：原 bug 最坏 = 报告里的 KPI 全是假的（0 / 79200 / -999）且无告警
          修完最坏 = 命令改错导致 undefined header → 该字段回到"没有数据"
          → Y ≤ X（改前是**假数据冒充真数据**，改后最坏是**没数据**，后者响亮）
```

**每个改动文件标一个字（⓪⑦）**：

| 文件 | 字 | 理由 |
|---|---|---|
| `app/hal/uxm_command_profiles.py` | **修** | 不改它，命令还是错的 |
| `app/hal/uxm_base_station.py` | **修** | 不改它，取值下标/单位/前置序列还是错的 |
| `tests/test_uxm_kpi_readback.py`（新） | **修** | ⓪④ 要求门 + 变异 |

---

## 3. 改法

### 3.1 命令表 —— **换源**（换成手册给的那条）

全部走 `BSE:` 前缀（IRAT App 的根），写进 `UxmLteNrIratProfile`：

| KPI | 正确命令 | 返回 | 取哪个 |
|---|---|---|---|
| DL 吞吐量 | `BSE:MEASure:NR5G:BTHRoughput:DL:THRoughput:OTA:{cell}?` | 6 doubles：`progress, current, min, max, average, current-scheduled`，**单位 bps** | **`average`（idx4）** |
| UL 吞吐量 | `BSE:MEASure:NR5G:BTHRoughput:UL:THRoughput:OTA:{cell}?` | 同上 | `average`（idx4） |
| DL BLER | `BSE:MEASure:NR5G:BTHRoughput:DL:BLER:{cell}?` | 10 doubles：`progress, ack-count, ack-ratio, nack-count, nack-ratio, statdtx-count, statdtx-ratio, pdschBlerCount, pdschBlerRatio, pdschTputRatio` | **`pdschBlerRatio`（idx8）** |
| UL BLER | `BSE:MEASure:NR5G:BTHRoughput:UL:BLER:{cell}?` | 6 doubles：`progress, ack-count, ack-ratio, nack-count, nack-ratio` | **`nack-ratio`（idx4）** |
| CQI | `BSE:MEASure:NR5G:{cell}:CSI:CQI:STATistics?` **（命令本来就对）** | 6 doubles：`[0]=绝对子帧号 [1]=count [2]=min [3]=max [4]=average [5]=median` | **`average`（idx4）** ← 原来取的 idx0 是绝对子帧号 |
| RI | `BSE:MEASure:NR5G:{cell}:CSI:RI:HISTogram?` **（命令本来就对）** | 8 doubles = **RI 码点 0..7** 各自计数 | 加权均值，权重 **`(i+1)`**（码点 → rank）—— **保持原样不动** |
| RSRP/RSRQ/SINR | `BSE:CONFig:NR5G:{cell}:MEASurement:JSON:REPort:FETCh?`（L3 RRC 测量报告） | JSON，含 `RSRP` / `RSRQ` / `SINR` / `CSI_RS_*` | 见 §3.3 |

> **为什么 DL 吞吐量取 `average` 不取 `current`**：用户要的是"**吞吐量的实际结果**"，
> 一次测试例的结论是统计窗口内的平均值，不是某一瞬的瞬时值。`current` 会随调度抖动。
> **六个值全部记进 `measurement.log`**，不丢信息；`dl_throughput_mbps` 这个"结论字段"
> 取 `average`。这条是**可推翻的判断** —— 若现场认为该用 `current`，改一个下标即可。

> **单位**：手册明确 SCPI 层是 **bps**（GUI 显示 Mbps）。所以要 `/ 1e6`。
> 这是**新引入的换算**，必须配门 —— 漏了会得到 4.2e8 Mbps 这种数。

### 3.2 前置序列 —— **加机制（唯一一处，手册强制）**

没有前置，正确的命令也只会返回 `9.91E+37`。三件事：

1. `BSE:MEASure:NR5G:BTHRoughput:STATe ON` —— 开吞吐量/BLER 累积（**全局**，不带 cell）
2. `BSE:MEASure:NR5G:{cell}:CSI:STARt` —— 开 CSI（CQI/RI）累积
3. 删掉 `TSTatistics:STARt` / `:STOP`（**手册里不存在**），清零改用
   `BSE:MEASure:NR5G:BTHRoughput:CLEar`

放在 `configure_mac_throughput_test()`（已有的"设定统计窗口"入口），不是每轮 metrics 里发。

⚠️ **这是本片唯一"加机制"的地方，理由**：前三种修法（去掉/换源/收窄）都取不到数据 ——
手册说测量不开就没有数据，这不是判据问题，是仪器状态机的硬前置。

### 3.3 NaN 哨兵 —— **收窄**

`9.91E+37` 是 SCPI 的 NaN（手册反复强调）。现在我们会把它当成真值算进去。
统一加一个 `_scpi_nan(v)` 判据：`v >= 9.9e37` → `None`，并让该字段**保持"无数据"
而不是 0.0**。

⚠️ **这条会改变 `ThroughputMetrics` 的默认语义**（0.0 vs None）。为控制爆炸半径，
本片**只在驱动内部区分**，对外仍填默认值，但**在 `measurement.log` 里显式记
`<field>_valid: false`** —— 让日志能分辨"测到 0"和"没测到"（跟 P1-30 同一个母题）。
把 `Optional[float]` 一路推到 schema / DB / 报告是**独立片**，进 backlog。

---

## 4. 明确不做（枚举进 backlog，⓪③）

| 项 | 去向 |
|---|---|
| DL 重传统计（HARQ ACK/NACK/StatDTX 按传输次序）本身是**有用数据**，现在被浪费了 —— 应作为独立 KPI 记录，而不是当吞吐量 | Discovered → 独立片 |
| `ThroughputMetrics` 各字段改 `Optional[float]`，把"没测到"一路透到 schema/DB/报告 | Discovered → 独立片（契约破坏面大） |
| L1 RSRP（`L1:RSRPower:REPorts:JSON?` + `L1:RSRPower:STARt`）作为 L3 之外的第二条路径 | Discovered |
| `CMW500BaseStation.get_throughput_metrics()` 是否同病 | Discovered → 需同样查手册 |
| `Uxm5GNRTestAppProfile`（非 IRAT）的同一批命令是否也错 | Discovered —— 本片只改现场在用的 IRAT profile，**其余 profile 不动**（改了也没法验） |
| 补一个 `uxm_kpi_readback` 诊断序列供现场对账 | **出发前必须有**（CLAUDE.md 的诊断序列规矩）→ 单独 chore |

---

## 4⁺. 实现期的三个发现（都不在原方案里）

### ① `configure_mac_throughput_test()` 在 IRAT 方言上 **11/11 条命令都是 None**

生效端门（`test_configure_actually_sends_them`）一加上就红了 ——
`'NoneType' object has no attribute 'format'`。查证：`UxmLteNrIratProfile`
继承的是 `UxmTestApp` **基类**而不是 `Uxm5GNRTestAppProfile`，
`PDSCH_*` / `TDD_*` / `HARQ_*` / `CSIRS_PORTS` / `MEAS_TPUT_STAT_COUNT`
**11 条全没覆盖**，函数第一行就抛、`return False`。

**即 MAC 层吞吐量测试的全部配置在现场那台仪器上从来没生效过。**

**本片不修**（范围纪律 —— 那是另一个可观察故障，且正解要同时解决"跳过全部还
报 True 就是假成功"）。但前置序列必须排在崩点**之前**，否则本片的修复在真正
用的那个方言上是死的 —— 所以 `_enable_kpi_measurements()` 放在第 **0** 步。
已登记 Discovered，**优先级高于本片**。

### ② 现场 2026-05-27 就查明了，两个多月没喂回驱动

`docs/site-debug/2026-05-27-morning-log.md` §9.2/§9.3 原文记着：

| 现场当时记的 | 今天查手册得到的 |
|---|---|
| `TSTatistics:STARt` → **-113 不支持** | 手册命令树里没有这条 |
| `UEReport:* / UL 吞吐` → **-113 本 App 不支持** | 手册里没有 `UEReport:*:STATistics` |
| `BLER:STATistical:ALL?` 停在 `IDLE,UNKN,0,0`「统计未被 enable」 | 它是 Early Pass/Fail 状态机，且要先 `BTHRoughput:STATe ON` |
| `CSI:CQI:STATistics?` 回 `7.92E+04,0,NaN...`「**字段义待查手册**」 | idx0 是 **progress-count**，CQI 均值在 idx3 |
| backlog：「**需查手册找 IRAT 下重置/enable 统计的正确命令**」 | `BTHRoughput:STATe` / `:CLEar` / `CSI:STARt` |

**情报早就有了，缺的是把它落回代码的那一步。** §9.5 还解释了为什么没人察觉：
未定义**查询**→客户端超时；未定义**写**→`resp=None/err=None` **静默像成功**
（所以 `TSTatistics:STARt` 的失败 warning 基本不会触发）。

### ③ 跑测试会删掉生产日志归档（**本轮亲手造成**）

pytest 进程的 `setup_logging()` 用默认 `log_dir`，于是每个 pytest 进程都在
`api-service/logs/` 上建 `TimedRotatingFileHandler`，滚动时按 `backupCount` 剪枝。
本次会话为跑变异起了 45+ 次 pytest，`logs/` 从 **253 文件 / 3.5 GB** 掉到
**24 文件 / 727 MB**，6 月与 7 月的仪器往返归档全没了 —— **包括本文引用的那批
real 模式 scpi.log**。数字是删除前提取的，口径都写在 §1；但原始文件已不可复查。
已登记 Discovered（修法 = 测试用独立 log_dir）。

### ④ 内审（pre-commit-reviewer）3 条 P1 —— 其中一条说明这片修复原本是死的

**F1（最重）：我给同步方法加了 `await`，8 个 KPI 一个都读不到。**
UXM 的 `_do_query` / `_do_write` 是**同步 `def`**，F64 的才是 `async def` ——
我按 F64 的形状写了 UXM。`await self._query(...)` 去 await 一个 `str` →
`TypeError` → 被我自己的 `except Exception` 吞成一行 warning →
**每个字段静默落回默认值**。内审用真契约探针跑出来的输出：

```
WARNING [UXM] DL OTA throughput 查询失败: object str can't be used in 'await' expression
[KPI] DL=0.0Mbps(cur 0.0) UL=0.0Mbps BLER=0.0000 CQI=0 RI=1 RSRP=-999.0dBm SINR=-999.0dB
      ⚠未读到: dl_throughput,ul_throughput,dl_bler,ul_bler,cqi,rank_indicator,rsrp,sinr
```

**而我的门全绿** —— 因为 `_stub_io` 把 `_query` 换成了 `async def`，
**mock 里改掉了 sync/async 契约**。仓库既有的
`tests/test_uxm_cell_config_orchestration.py` 是在 VISA session 层打桩、
保住了真契约，我偏离了那个先例。已把桩下沉到 `_do_*` 层，并补一条**源码级
不变量门**（本文件不允许 `await self._query|_write`）+ 两条变异（M17 语法错、
M17b 语法合法但语义错）。

**F2：CQI 取的是 `maximum` 不是 `average`。**
仓库内厂商 SCPI Reference 原文：
`result[3]=cqi_maximum` / `result[4]=cqi_average`。我按 NotebookLM 的概括
（"count/avg/min/max/median"）映射成 idx3，错一位 → 系统性乐观（上报最好的
那一次）。且 `result[0]` 是**绝对子帧号**，不是我写的 progress-count。
门也漏了：原测试数据 `…,9.6,10,0` 里 `round(9.6)==10==idx4`，idx3/idx4
不可区分，内审变异 M-A 从这个缝钻过去。已换成三者两两不同的数据。

**F3：RI 权重我改坏了（原来是对的）。**
手册把 bins 写成 "RI value [0..7]"，与 "CQI value (0..15)" 并列 ——
那是 **3GPP 上报码点**，rank = 码点 + 1。我改成权重 `i` 会算出
`rank_indicator = 0`（物理上不存在），而 `analysis.py` 拿它跟
`min_avg_rank_indicator`（默认 1.8）比 → **真跑 rank 2 的 DUT 报 1.0，必 FAIL**。
已改回 `(i+1)` 并补 `rank_indicator >= 1` 不变量门。

> **交叉验证方法上的一点**（用户 2026-08-03 指出「NotebookLM 能更全面地查询，
> 手册会顾头不顾尾」）：这两条正好各证一半。RI 那条 **NotebookLM 独立确认了
> 码点语义**，还从**别的章节**拉来旁证（层数范围从 1 起、`PDSCH Max MIMO
> Layers` 0..8、链路自适应 "number of layers adapted according to the RI
> received"）—— 都在我 grep 的那几行之外。CQI 那条它**看不见**：它明说手册那段
> 在 "The returned data is a sequence of double values:" 之后**逐项列表缺失**
> （转文本时表格丢了），并主动收回了先前"首值是 count"的推断。
> **结论：语义与跨章节旁证靠 NotebookLM；逐元素布局要回原始文件核。**

其余：F4 `_parse_doubles` 空元素丢位导致下标左移（已修+门）、
F5 窗口门只验"CLEar 发过"不验"在读之前"（已改成时序断言）、
F8 现场普查序列的 critical 清单仍指着本片刚置 `None` 的命令、
且 `CLEar` 未列进动作命令表会被补 `?` 盲发（已修）。
F6/F7/F9/F10 判为范围外，全部登记 Discovered。

### ⑤ 变异脚本自己的坑：只 grep stdout 会把最严重的变异记成绿

M17（往 sync 函数里塞 `await`）是 `SyntaxError`，pytest **在输出任何东西之前
就退出**：stdout 为空、报错全在 stderr、`returncode=4`。只数 `^FAILED ` 的
计数器会报 **FAILED=0 → "门没兜住"** —— 最该红的那条看起来最像漏网。
判据已改成 `FAILED|ERROR 行数 > 0 **或** returncode != 0`。

## 5. 验收

**实跑结果（2026-08-03）**：

- 门 **29 条**全绿（`tests/test_uxm_kpi_readback.py`）；**23 条变异逐条实跑，
  全部让门变红**；还原后复跑 29 绿。
- 全量 **2921 passed, 4 skipped, 0 failed**（122s）。
- G4「静默吞异常棘轮门」按其自身规则下调基线 `get_throughput_metrics: 8 → 0`
  —— 那 8 处 `except: pass`（每个 KPI 字段一处）随本片一起消除，现在读不到
  会记 warning + 在 `measurement.log` 标 `kpi_valid=false`。

⚠️ **变异 M10 第一次是绿的** —— 门直接调 `_enable_kpi_measurements()`，
把 `configure_mac_throughput_test()` 里的**调用点**删掉抓不到。
**「门锁的是 helper，不是生效端」今晚第三次**（P1-30 内审 F1 / Codex #273 P2
是前两次）。已补 `test_configure_actually_sends_them` 打在调用点上，
并加 M10b（把前置挪到 MAC 配置之后）—— 两条现在都红。

**本地能证的**：命令字符串与手册逐条对齐（门）、解析下标正确（门 + 变异）、
单位换算（门）、NaN 哨兵（门）、前置序列被发出且顺序正确（门）。

⚠️ **本地证不了的（如实申报）**：真机是否接受这些命令、返回值是否如手册所述。
**必须现场验**，走诊断序列不写临时脚本。出发前补 `uxm_kpi_readback` 序列。
