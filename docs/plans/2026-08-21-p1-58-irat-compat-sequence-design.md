# P1-58 设计稿：`uxm_scpi_compatibility` 的 critical 判定集从当前方言 profile 派生

> 2026-08-21 · 分支 `codex/p1-58-irat-compat-sequence` · 来源：roadmap Discovered
> 「`uxm_scpi_compatibility` 在 IRAT 方言上永远不可能成功（P1，活 bug）」

## 1. 可观察故障（动手前实证，非转述）

判定用的 critical 集是**跨方言全局并集**（`_CORE_CRITICAL_NAMES | _MAC_CRITICAL_NAMES`
− `_NO_EQUIVALENT_NAMES`，36 条），而 `critical_undefined` 拿它对**单方言** profile 逐条要
str —— 任何一个方言都不可能覆盖全集，于是 `success` 恒 `False`。本棚实跑
（`_CRITICAL_NAMES` 对两个 profile 逐条 `isinstance(getattr(...), str)`）：

| 方言 | critical 中「profile 未定义」条数 | 名单 |
|---|---|---|
| LTE_NR_IRAT（现场方言） | **4** | `APP_SELECT` `MIMO_RX_ANT_PORT` `MIMO_TX_ANT_PORT` `PDSCH_AMC_ENABLE` |
| 5G_NR_Test | **20** | `MAC_CFG_MANDATORY` 大部（BSE: 形式只在 IRAT 有）+ `MEAS_TPUT_*_OTA` / `MEAS_BLER_*` / `MEAS_UE_REPORT_JSON` / `HARQ_*` / `CSIRS_PORTS` 等 |

⚠️ Discovered 条目里点名的 `TDD_PATTERN` 已被 P1-46 移出清单（`test_legacy_tdd_pattern_*`
守着），但**故障形态原样存活** —— 这已是同一形态第三次露头（`MEAS_BTHROUGHPUT_DL_BLER`
→ `TDD_PATTERN` → 本次 4 条）。逐条摘名字是打地鼠；病根是**判据源错位**：拿「全宇宙
关键能力清单」当「本方言应有命令清单」用。

## 2. 双实证记录

**memory（可用，显式记）**：命中 `feedback_query_notebooklm_for_uxm_f64_driver`（必查
+ 只认原文）、`feedback_review_findings_verify_premise_first`、`feedback_whole_not_local`
（判据取当前真值 / 全集 —— 正是本片病根的镜像）。

**NotebookLM（「Keysight UXM5G 网络测试 SCPI 编程指南」`236d9621-...`，2026-08-21 查，
逐点要求区分原文与推断）**，对 IRAT 上那 4 条未定义命令：

手册原件 = 本机 `Instrument_API_Doc/Keysight UXM NR SCPI/UXM5G_SCPI_0X_*.md`（厂商 HTML 手册的
markdown 导出，未入库的本地文件；行号以 2026-08-21 本机副本为准）。Codex #358 R1 P2 要求每条结论
给出可核查的出处，以下「出处」列为 2026-08-21 主 agent 直接 grep 原件的结果，NotebookLM 只作二次核对：

| 命令 | 手册原文结论 | 出处（文件 · 章节 · 行） |
|---|---|---|
| `SYSTem:APPLication[:NAME]`（APP_SELECT） | **原文存在**：`Application Mode : NSA \| SA`；`Range : NRSI \| NRNS \| NSA \| NRCW \| NRSA \| NREL1 \| LTE_NR_IRAT \| LTEV2X`；`Default : LTE_NR_IRAT`。**在 LTE_NR_IRAT 运行期间可不可用 —— 手册未说明**（该条目无任何切换限制描述） | `UXM5G_SCPI_06_General_Examples_Shared.md` · `General > Miscellaneous commands > Test Application Mode` · 第 227–245 行（`- **SCPI**` 在 232 行） |
| `ROUTe:NR5G:<cell>:HARDware:TX/RX:ANTenna<n>:PORT`（MIMO_TX/RX_ANT_PORT） | **六份手册里没有任何 `ROUTe:` 子系统**：`grep -n ROUTe` 的全部命中都是 `…IPV6:ROUTer…`（IPv6 路由器设置）；`HARDware:TX` / `HARDware:RX` / `ANTenna<n>:PORT` 在 NR Core 文件 0 命中。NR 侧天线口相关的只有 `BSE:CONFig:NR5G:<cell>:DL:PANTenna:PORTs`（物理天线口**数量**，枚举 N1/N2/…，不是天线→物理口路由，不作等价替换） | 反向证据：`grep -n ROUTe *.md` 命中 `UXM5G_SCPI_03_LTE.md:6090/6107/6122/6137/15786`、`UXM5G_SCPI_04_NB-IoT.md:9605/9623`、`UXM5G_SCPI_06_…:1562`，全是 `ROUTer`；正向对照：`UXM5G_SCPI_01_NR_Core.md` · `DL Physical Antenna Ports` · 第 2455–2470 行 |
| `...PDSCH:AMC:ENABle`（PDSCH_AMC_ENABLE） | **六份手册里 `:AMC:` 零命中**；DL 自适应由 `BSE:CONFig:NR5G:<cell>:SCHeduling[:<BWP>]:<fc>:<sc>:DL:RRESource:APOLicy` 控制（`Range : FIXed \| BLER \| DYNamic \| CQI \| PMI \| RI \| CQIRi \| PMIRi \| CQIPmiri \| CR`）—— 与 profile 既有注释一致 | 反向证据：`grep -n -i ':AMC:' *.md` 0 命中；正向：`UXM5G_SCPI_01_NR_Core.md` 第 13032 行（`DL:RRESource:APOLicy`）、13445（`DL:TDOMain:APOLicy`）、13930 / 14357（UL 同款） |

结论：**没有任何一条有手册原文说「LTE_NR_IRAT 下可用」**，其中 3 条命令形式本身手册
查无。因此本片**不发明任何「IRAT 支持/不支持」断言**，按 profile 现状收敛；报告措辞
沿用 `uxm_command_profiles.py:627-648` 已定口径 ——「未在本方言 profile 定义 ≠ 已验证
不支持；未探测、无结论」。

（查证顺带发现：5G_NR_Test profile 里定义的 `MIMO_TX/RX_ANT_PORT` 两条同样是手册查无
的形式 —— 不属本片，记入交付报告待 triage，不动 profile。）

## 3. 方案：判据换源 + 判决四态（不加机制）

新增一个纯函数，把全局 critical 能力清单按**当前方言 profile 的实际赋值**二分：

```python
def _critical_partition(profile):
    applicable = frozenset(
        n for n in _CRITICAL_NAMES if isinstance(getattr(profile, n, None), str))
    not_in_profile = sorted(_CRITICAL_NAMES - applicable)
    return applicable, not_in_profile
```

- **判定**（`is_critical`、blocker 归集）一律用 `applicable` —— 判据单源；
- **`critical_undefined` 从「BLOCKER 失败项」降为如实披露**：改名 `critical_not_in_profile`，
  进 `extra` + log + summary 披露，**不再被报成仪器拒绝**；
- **但它仍挡 `success`**（Codex #358 R1 P1，初版把它放行了 = 假绿）：profile 口径 `None` =
  未经查证（`uxm_command_profiles.py:22-24`），GUI `SequenceRunnerPanel` 直接拿 `success`
  画绿牌，生产驱动 `configure_mac_throughput_test` 对同一批 None 会拒绝配置 —— 健康检查报绿、
  生产路径拒绝，就是假绿。`success = (not critical_unsupported) and (not
  critical_unverified_actions) and (not aborted_early) and (not critical_not_in_profile)`；
- **判决四态**透出在 `extra["verdict"]` 与 summary 前缀：`ABORTED` / `BLOCKER`（有实测
  失败因子；未定义只作披露后缀，不混进失败清单）/ `UNDETERMINED`（无实测失败、但有未定义
  critical → 未探测、不能判健康）/ `SUCCESS`（全定义且全支持）；
- 成功 summary 从「All 36 critical supported」改为「All N **applicable** critical
  supported on profile X」+ 未定义条数披露 —— #275 P2 那道「不撒谎」防线的真实意图
  （不把没探测过的报成已验证）**换实现保留**，不是拆除。

**修后四态**（②⁺ 全集）：

| 态 | success | summary |
|---|---|---|
| aborted_early | False | `ABORTED`（不变） |
| 有实测 UNSUPPORTED critical | False | `BLOCKER` 列名；未定义只在「；另有 N 条…未探测、无结论」披露后缀里，不混进失败清单 |
| 有 INFERRED_ONLY mandatory ACTION | False | `BLOCKER` 列名（P1-46，不变） |
| 无实测失败、但有未定义 critical | **False** | `UNDETERMINED`：applicable 全支持 + N 条未定义（未探测、不能判健康；≠ 已验证不支持） |
| 全定义且全支持 | **True** | `SUCCESS`：All 36 critical supported |

⚠ **在 P1-46 拍板下，生产 profile 上 `SUCCESS` 结构性不可达**：`CONFIG_APPLY` /
`QCONFIG_APPLY_ALL` 在 critical 清单里，定义了 → 只读普查验证不了 → BLOCKER；不定义 →
UNDETERMINED。今天 IRAT = BLOCKER（2 条 ACTION）、5G_NR_Test = UNDETERMINED（20 条未定义）。
这不是本片引入，是如实状态；要让它能绿，只有两条路且都要用户拍板：(a) 改 P1-46 策略
（把 mandatory ACTION 的 INFERRED_ONLY 降为披露）；(b) 另建能直接验证 apply 的剧本式序列
（apply 后读 `SYST:ERR?` 拿直接证据）。门 ①c 用补满 profile + 临时清空 mandatory 集证明
判决逻辑本身可达 SUCCESS（防恒 False 的退化写法）。

## 4. 边界（两个方向都不走偏）

- **fail-closed 原样保留**：profile 有定义、实测 -113/-114 → 仍 BLOCKER；
  `CONFIG_APPLY` / `QCONFIG_APPLY_ALL`（IRAT 已定义的 mandatory ACTION，只读普查
  在原理上验证不了）的 `INFERRED_ONLY` fail-closed 是 P1-46 拍板、
  `test_immediate_apply_actions_*` 守着的**另一机制，本片不动** —— 它们是 profile
  实际有的命令，放行 = 为绿而放水。修后 IRAT 全 clean 的结果是
  `BLOCKER`、失败原因**收窄且如实**（只剩那 2 条 ACTION，4 条未定义只在披露后缀）；
  5G_NR_Test 全 clean 是 `UNDETERMINED`（不再是把 20 条当"不支持"的 BLOCKER，也不是绿）
  ——「方言没有的命令不再被报成仪器拒绝」在两个方言上都可观察。
- **不发明仪器断言**：改动只引用 profile 赋值这一仓库事实；措辞恒为「未定义/未探测/
  无结论」，never「不支持」。
- **与 P3-21 边界**：不碰错误队列读取实现（`SYSTem:ERRor?` 收发与解析原样）。
- **G12/G18**：不新增 SCPI 命令模板、不改 `required_categories`，两门不触发。

## 5. 门与变异（RED → GREEN → 变异实跑）

新文件 `tests/test_p1_58_irat_compat_sequence.py`：

| 门 | 断言 | RED 状态 |
|---|---|---|
| ①a IRAT：方言没有的不判失败 | clean 固件下 `extra["critical_not_in_profile"]` == 按 profile 派生的非空清单；`critical_unsupported==[]`；失败因子仅剩 `critical_unverified_actions` | 红（extra 无该键） |
| ①b 5GNR：UNDETERMINED 不是绿 | clean 固件下 `success is False`、`verdict == "UNDETERMINED"`、summary 以 UNDETERMINED 开头且不含 BLOCKER / "实测不支持" | 红（P1-58 前是 BLOCKER 列 20 条；本片初版是 success=True 假绿） |
| ①c SUCCESS 可达 | 补满 profile + 清空 mandatory 集 + clean → `success is True`、`verdict == "SUCCESS"` | 防恒 False 退化 |
| ② 真缺失仍失败 | IRAT 下 `CELL_BAND` 探测回 -113 → `success is False` + BLOCKER 点名 `CELL_BAND`；**且 4 条未定义名字不再出现在 BLOCKER summary** | 后半红 |
| ③ 不变量 | 对每个 profile：`applicable ⊆ _all_commands(profile) 名集`；`applicable ∪ not_in_profile == _CRITICAL_NAMES` 且二者不交（partition 完整，防「第三种静默漏斗」） | 红（函数不存在） |

既有用例改造（同一故障的镜像站点，标「顺带」）：
`test_all_supported_when_firmware_responds_clean`（success 反转 + 措辞断言）、
`test_critical_undefined_in_profile_is_not_reported_green`（改为「披露而非失败」语义并
改名）、`test_state_error_categorized_as_ok`（stale 注释）。
`test_immediate_apply_actions_*`（P1-46 门）**应保持全绿，不改**。

变异（GREEN commit 后实跑，跑完 `git checkout` 还原，每条 assert 命中）：

- **M1 判据改回硬编码全局清单**：`applicable = frozenset(_CRITICAL_NAMES)` → ①a/③ 红；
- **M2 真缺失放行**：`success` 去掉 `(not critical_unsupported)` → ② 红；
- **M3 披露归零**：`extra` 不放 `critical_not_in_profile` → ①a 红。
- 2026-08-21 实跑记录：M1 → 6 红；M2 → 恰好 ②b 红（②b 用补满 profile 隔离单一因子）；M3 → 6 红；
  内审另造 N1 partition 无视入参 → 4 红、N2 summary 丢披露 → 3 红、N5 只看 CORE 清单 → 2 红；
  N3 两处 `is_critical` 回退全局 → 绿（等价变异：`_all_commands` 已按 str 过滤）；
  N4 `success` 丢 `aborted_early` → 绿（内审 F2 P3，既有代码无门，报告一次）。
- 四态判决的变异（Codex #358 R1 P1 修复后）：MV1 `success` 放行 not_in_profile → 3 红；
  MV2 UNDETERMINED 分支谎报 SUCCESS → 3 红；MV3 SUCCESS 分支写成 UNDETERMINED → 1 红（①c）；
  MV4 BLOCKER 分支丢掉披露后缀 → 1 红（①a）。

## 6. 文件清单（修 / 顺带 / 越界）

| 文件 | 标 | 说明 |
|---|---|---|
| `api-service/app/diagnostics/sequences/uxm_scpi_compatibility.py` | **修** | 判定段换源 + 四态 summary + docstring 中 stale 的「22 critical」句更新 |
| `api-service/tests/test_p1_58_irat_compat_sequence.py` | **修**（新门） | 上表四门 |
| `api-service/tests/test_diagnostic_sequences.py` | 顺带 | 3 个用例是旧行为的直接断言，不改则恒红 |
| `api-service/tests/test_uxm_scpi_compatibility.py` | 顺带（仅核对） | 预期零 diff；若需动即停下报告 |
| `docs/plans/2026-08-21-p1-58-*.md` ×2 | 修（流程件） | 本稿 + plan |

越界候选（**不做**，进报告）：5GNR profile `MIMO_TX/RX_ANT_PORT` 手册查无、roadmap
P1-33 行「判定集错」描述已 stale、metadata description 的「~76 commands」字样。
