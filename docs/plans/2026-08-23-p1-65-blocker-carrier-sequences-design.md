# P1-65 硬件 Blocker 载体序列补齐 — 设计

> 2026-08-23 用户拍板：「把所有硬件 blocker 的脚本在这个 PR 中就位」，并明确设计完成后直接开工。
> 本文是动手前的四行契约 + 全集枚举 + 每条命令的手册出处。**仪器语义只认手册原文**
> （本地原件 `Instrument_API_Doc/**` 直接 grep，NotebookLM 二次核对并要求区分原文/推断）。

## 四行契约

- **搜索命中**：memory `feedback_instrument_debug_via_diagnostic_sequence`（载体只能是 checked-in 序列）、
  `feedback_query_notebooklm_for_uxm_f64_driver`（必查 + 只认原文）、`feedback_review_findings_verify_premise_first`；
  目标目录禁令 grep（`app/diagnostics/sequences/`）：「禁盲试」「先查状态再决定发不发」「每步后读错误队列」。
- **必要性**：roadmap「Blocked on hardware」区 2026-08-23 覆盖矩阵：16 行里 **8 行完全在 first-call 流程外**、
  其中 5 行**没有任何载体** —— 到了现场只能临时补脚本，正是 P1-45 立的规矩禁止的。
- **范围**：新增 8 条序列 + 1 组 GUI 无改动（序列面板按 loader 自动发现）+ 每条序列一组行为门；
  **不改任何驱动**（本片查出的驱动盲试命令登记为 Discovered，见 §5）；不改 roadmap 正文（收口时集中改）。
- **爆炸半径**：新增文件为主；序列全部只读或"显式确认参数 + 先查状态 + 每步读错误队列"的剧本；
  mock 驱动一律拒绝（`mock_driver_refusal_summary`）。原最坏 = 现场无载体临时敲命令；修完最坏 = 某条序列判定不准但留有原始回复。Y ≤ X。

## 1. 全集：每一行 blocker 的载体决定

| 行 | 本片载体 | 决定 |
|---|---|---|
| P2-9 EMCenter | **新** `emcenter_switch_health` | 只读握手 + 逐槽卡识别 + 继电器位回读 + 互锁 |
| NEW-1 F64 各口电平窗口 | **新** `propsim_f64_output_level_windows` | 逐口 `LIMits?` + `CH?`，当前值落窗外即标红 |
| P1-2 F64 license | **新** `propsim_f64_license_truth` | 用手册有的命令读许可与用户对齐状态，并与驱动自称的 `_installed_options` 对账 |
| NEW-2 面板 Local | **新** `propsim_f64_local_handback_check` | 两段式人工确认步（手册：回 Local 只有 GUI 按钮，无 SCPI，§20.1） |
| NEW-3 OffsetToCarrier | **新** `uxm_offset_to_carrier_probe` | 默认只读（PointA / OTCarrier / ARFCN / 小区状态）；写只在 `confirm_write` 且小区 OFF 时发，写后回读 + 错误队列，不 APPLY |
| P1-17 UXM fresh-start | **新** `uxm_fresh_start_truth` | 只读状态导入机制真值（`SYSTem:SCPI:*`、`APPLication:NAME?`、`LICense:AVAilable:ALL?`）；可选 `confirm_action` 走 `SYSTem:SCPI:IMPort` + `STATus?` |
| P2-4 / P1-6 idle-drop | **新** `connection_idle_hold_probe` | `*IDN?` → 空置 N 秒 → `*IDN?`，记录会话是否存活 / 是否触发重连（C 类观察载体） |
| P2-13 SIM 一致性 | **新** `uxm_sim_identity_truth` | 读 `BSE:INFO:NR5G:<cell>:UEReported:IMSI?` 与 LabProfile 绑定的 SIMProfile 对账 |
| P1-4 重复性 | 不在本片 | 载体是 MIMO_OTA TestCase 跑两次 + 报告对比契约（plan 级 → execution 级）：另一片 |
| P1-5 相位校准 | 不在本片 | 不在 first-call 范围（PFS power-only，memory `project_pfs_phase_cal_decision`） |
| P2-10 / P2-12 F64 工程精细化 / 标准信道文件 | 不在本片 | 协议 §7 的 11 项各需逐项手册核对，多数是运行时写命令；本片只读序列不盲建。本片 `license_truth` / `level_windows` 给它们提供前置事实 |
| P0-5 / P0-8 / NEW-4 | 已有载体 | 不动 |

## 2. 命令清单与出处（每条都要能在原件里指到）

### F64（`Propsim User Reference.pdf` Rev 10.2，pdftotext 行号为本机抽取结果）
| 命令 | 章节 | 用途 | 备注 |
|---|---|---|---|
| `*IDN?` | §20.4.1.5 | 身份门 | 既有 |
| `SYSTem:INFO?` | §20.4.2.4 | `<Device>,<channels>,<Interface>,<HW ver>,<RFLOs>,<Band…>,<License…>` | **许可列表就在这里**，不需要探针 |
| `SYSTem:ERRor?` | §20.4.2.1 | 每步后零残留 | 既有 |
| `SYSTem:STATus?` | §20.4.2.5 | 告警/caution 状态 | 只读 |
| `OUTPut:LEVel:AMPlitude:LIMits? <n>` | §20.4.5.5 | `<lower>,<higher>` dBm | NEW-1 |
| `OUTPut:LEVel:AMPlitude:CH? <n>` | §20.4.5.4 | 当前平均输出电平 | NEW-1 |
| `SYSTem:CALIBration:LIST?` | §20.4.2.12 | 有效校准列表 | P1-2 |
| `SYSTem:CALIBration:VALid?` | §20.4.2.13 | `<in use 0/1>,<valid 0/1>` | P1-2 |
| `SYSTem:CALIBration:GET?` | §20.4.2.11 | 当前加载的校准名 | P1-2 |
| `SYSTem:CALIBration:USER:GET?` | §20.4.2.19 | 当前用户对齐名，未启用返回空串 | P1-2 |
| `SYSTem:CALIBration:USER:INFO?` | §20.4.2.21 | 用户对齐附加信息 | P1-2 |
| `OUTPut:INTERFerence:GET?` | §20.4.9.5 | 干扰源列表，无则 `"0"`；**前置：仿真已加载** | P1-2，先 `STATE?` 再决定发不发 |
| `DIAG:SIMU:STATE?` | 既有 `propsim_f64_state_machine` | 状态前置 | 既有 |

**手册查无（写稿时驱动现用 → P1-66 #382 已删，本片不发、登记 Discovered）**：`SYSTem:CALibration:USER:LIST?`（驱动 USER-ALIGN 软探针）、
`OUTPut:INTERFerence:LIST?`（驱动 INT-GEN 软探针）—— 注释自承 "CAICT to-verify"；现场 -100 "ATE command not supported"
（P1-2 实测）是**命令编出来的**，不是"该机不支持"。

**Local/Remote（§20.1 原文）**："To return to local mode, click the Local Mode button in the top right corner of the GUI."
无任何 SCPI 可切回或查询 Local；ATE AN 全文无"socket 关闭即回 Local"。→ NEW-2 只能人工确认。

### UXM（本地 `UXM5G_SCPI_0X_*.md`；NotebookLM 2026-08-23 二次核对）
| 命令 | 条目 / 文件:行 | 用途 | 备注 |
|---|---|---|---|
| `BSE:CONFig:NR5G:<cell>:DL:OTCarrier[?]` | `NR Configure OffsetToCarrier DL`，01_NR_Core:2254 | Integer 0..2199，"number PRBs from PointA to first PRB" | Application Mode `NSA \| SA`；**IRAT 下可用性手册未说明**；查询形式 `?` 是按 Integer 型无 No-query 标记的推断（NotebookLM 标明为推断） |
| `BSE:CONFig:NR5G:<cell>:DL:POINta[?]` | `NR DL PointA`，01_NR_Core | Point A ARFCN | 同上 |
| `SYSTem:SCPI:IMPort "<file>"` | `Import SCPI File`，06_General（Utility > Export/Import SCPI） | "Import (i.e. load) a SCPI file, recovering a previously exported application state" | P1-17 |
| `SYSTem:SCPI:IMPort:STATus?` | 同上，Query only | 导入成功与否 | P1-17 |
| `SYSTem:SCPI:IMPort:INCLude:PRESet` | 同上 | 导入前是否复位 | P1-17 |
| `SYSTem:SCPI:FOLDer` | 同上 | 导入目录 | P1-17（查询形式同为推断） |
| `SYSTem:PRESet:FULL` / `FACTory` / `API` | 06_General 命令总表 | fresh-start 复位 | **本片不发**（破坏性），只记入 extra 作可用命令 |
| `SYSTem:APPLication[:NAME]?` | `Test Application Mode`，06_General:232 | 当前 TAP | 既有 |
| `SYSTem:LICense:AVAilable:ALL?` | 06_General 命令总表 | 许可 | 只读 |
| `BSE:INFO:NR5G:<cell>:UEReported:IMSI?` | 01_NR_Core:39014 | UE 上报 IMSI | P2-13 |
| `SYSTem:ERRor?` | 既有 | 每步后读 | 既有 |

**手册查无（写稿时驱动 5G profile 现用 → P1-67 #383 已换源，本片不发、登记 Discovered）**：`SYSTem:CONFiguration:LOAD "<file>"`（`STATE_LOAD`）、
`MMEMory:CATalog? "D:\User Files"`（`STATE_LIST`）—— md 与 HTML 手册 0 命中，NotebookLM 原文核对"不存在"。

### EMCenter（`EMCenter_SCPI_Cmds_and_Errs_RevA_1801188.pdf` + `docs/site-debug/2026-06-04-emcenter-switch-protocol.md`）
| 命令 | 出处 | 用途 |
|---|---|---|
| `*IDN?` / `<slot>:*IDN?` | 手册 p.3 示例 `Query 1:*IDN?\n`…（pdftotext:114-169）；终止符 CR（:105） | 机箱 / 卡识别 |
| `VERSION_SW?` | pdftotext:243 | 系统版本 |
| `<slot>:INT_RELAY_<R>?` | pdftotext:259-271 | SPDT → `NC`/`NO`；SP6T → `1-6`（`0`=全开） |
| `INTLK? SAFETYRELAY` | 06-04 调研文档表 | 互锁 0/1 |
只读；裸命令 + CR（驱动 `EtslSwitchDriver._frame` 已按此实现）。槽位与 `relay_type` 来自驱动 `port_maps` 配置；
TCP 端口现场缺口（P2-9 表）：序列按驱动绑定的端口连，连不上即如实报告，不猜端口。

## 3. 每条序列的形状（共同约束）

- `required_categories` 精确声明（G18 门）；mock 驱动 → `mock_driver_refusal_summary` 拒绝。
- **先查状态再决定发不发**；每个会改状态的步骤后读错误队列；只读序列在结尾读一次错误队列零残留。
- 所有回复 `raw` 原样进 `SequenceStepResult.raw`；判定放 `detail`；`extra` 带结构化结论（便于 DiagnosticRun 落库）。
- 四态口径沿用 P1-58：`SUCCESS / UNDETERMINED / BLOCKER / ABORTED`（人工确认步缺失 = UNDETERMINED）。
- 措辞：未探测 ≠ 不支持；手册未说明 ≠ 支持。

## 4. 门与变异

每条序列一个测试文件 `tests/test_p1_65_<seq>.py`：回放式假驱动（照 `test_p1_58` 的 `_ScriptedBs` 形态）+
mock 拒绝门 + 只读序列"不得发写命令"不变量门（收集所有 `_query/_write` 调用，断言无写）+ 每步错误队列读取门；
剧本序列另加"不确认不写""小区 ON 不写"行为门。变异：去掉错误队列读 / 放行写 / 丢 raw → 各自门红。

## 5. 本片查出的 Discovered（登记，不在本片修）

1. **[P1 候选] F64 驱动连接路径两条软探针是编出来的命令**：`SYSTem:CALibration:USER:LIST?`、`OUTPut:INTERFerence:LIST?`
   手册查无；每次连接各留一条 -100 在错误队列（08-07 实测 269 次连接 = 269 条）。正解：许可从 `SYSTem:INFO?` 尾部
   `<License…>` 读（手册 §20.4.2.4 原文"and licenses"），用户对齐用 `USER:GET?`，干扰源用 `INTERFerence:GET?`。
2. **[P1 候选] UXM 5G profile 的 `STATE_LOAD` / `STATE_LIST` 手册查无**：手册状态导入是 `SYSTem:SCPI:IMPort` 系列。

   > ⟦2026-08-24 收口注记⟧ 第 1 条已由 P1-66 #382 修复（探针机制删除，能力单源
   > `SYSTem:INFO?`）；第 2 条已由 P1-67 #383 修复（换 `SYSTem:SCPI:IMPort/EXPort`，
   > `STATE_LIST=None`）。驱动不再含上述编造命令；本节其余为当时的调查存档。
3. 序列 runner 的租约默认 `enable_monitoring=True`，`connection_idle_hold_probe` 的"空置"会被 1 Hz 广播的流量打破
   —— 序列如实记录该 caveat 并读出期间交换计数；要真空置需 runner 支持按序列关监控（加机制，另议）。
