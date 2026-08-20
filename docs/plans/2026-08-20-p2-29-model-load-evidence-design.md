# P2-29：ASC/B2 正式模型加载证据 hook 设计

**状态**：设计完成，随片实施（2026-08-20 用户指示继续，连续流程）
**可观察故障**：正式执行的 `f64.model_loaded` 证据要求对三种信道管线都登记
（measure.py，fail-closed），但归档只在 `engine_mode == GCM_NATIVE` 分支触发 ——
ASC / B-2 的执行抓了 SCPI 交换却永不落证，`formal_acceptance` 恒为 false。
诚实，但这两条管线永远无法正式验收（P1-47C 收口时明确按设计保留的缺口，本片补上）。

## 1. 双实证前置

**memory（恒适用）**：
- `project_f64_ate_server_capabilities` —— CAICT 那台 F64 的 FTP(21) 关闭，ASC 管线
  在该机上传不了文件。**本片只管「加载发生时的证据」，不修 FTP 部署问题**（非目标）。
- `project_asc_synthesis_not_strict_pfs` —— ASC 由 ChannelEgine 产 .asc；驱动注释已有
  手册确认：.asc/.rtc 都要**编译成 .smu** 才能下发。

**NotebookLM（必查，已查，原文非推断）**：2026-08-20 查「PROPSIM 资料」
（conversation f7dcb528），三问三答全部给出手册出处：
1. **状态机与文件来源无关** —— AN §2.1（Emulation states 四态）+ UR §20.4.3.14
   （7 枚举 CLOSED/OPENING/STOPPING/STOPPED/RUNNING/EDITING/CLOSING）；
   按文件来源区分状态机的说法「**手册未说明**」。
2. **判成功流程不分文件类型** —— AN §2.2.2/§2.2.4：任何 .smu 都是
   `CALC:FILT:FILE → *OPC?（回 1）→ SYST:ERR?（回 0,"No error"）`。
3. **加载未 GO = STOPPED** —— AN §2.1 原文
   "Stopped: When an emulation file has been loaded to PROPSIM but has not been started"。

## 2. 根因（代码事实，已逐行核对）

三管线的加载**同一条命令、同一事务形态**（`CALC:FILT:FILE` + `*OPC?` + `SYST:ERR?`，
GCM=`_load_smu_with_preflight`、ASC=`upload_asc_files`、B2=`load_parametric_tdl`）。
差异只有两处：

| # | 缺口 | 后果 |
|---|---|---|
| ① | ASC/B2 成功分支缺 GCM preflight 里的两条证据探针：`_query_model_state_for_evidence()`（`DIAG:SIMU:MODEL:STATE?` = 目录 `f64.model_state`）与 `_query_simulation_state()`（`DIAG:SIMU:STATe?` = 目录 `f64.simulation_state`） | 证据窗口里没有 readback/state 交换，recipe 永远到不了 APPLIED |
| ② | measure.py 的 `record_f64_command_capture` 调用被 `engine_mode == EngineMode.GCM_NATIVE` 锁死 | ASC/B2 即使窗口完整也不归档 |

## 3. 改法（换源/收窄，零新机制）

1. **驱动**：ASC 与 B2 成功分支在 `_readback_topology()` 之前各加同样两条探针
   （锁内、与 GCM 顺序一致）。**不引入任何新 SCPI** —— 两条查询都已在
   G12 严格目录里有 confirmed 条目（UR §20.4.3.x），手册确认其语义与文件来源无关（§1）。
2. **measure.py**：归档条件从「GCM_NATIVE 且驱动有 build 能力」收窄为
   「驱动有 build 能力」（`hasattr(emulator, "build_p0_5_command_evidence")`）——
   能力即真值，管线枚举是错误的判据来源。同步改掉上方「当前正式 recipe 只对 GCM…」
   的注释（镜像）。
3. **不动**：证据 builder（现有 APPLIED 门 state∈{STOPPED,RUNNING,EDITING} 已覆盖手册
   语义）、G12 目录（零新条目）、`uxm_config_mode=inherit` 写入事务（roadmap 同段的
   另一件事，**非本片**）、FTP 部署、转台偏置。

## 4. 爆炸半径

原故障最坏 = ASC/B2 永远无法正式验收（诚实缺失）。修完最坏 = 证据链仍 fail-closed
（任一环缺失/异常 → 停在 TRANSPORT/unknown，探针失败只 warning 不改加载业务契约，
与 GCM 现状完全一致）。**不存在把假证据判绿的新路径**：builder 判定逻辑零改动。
Y ≤ X ✓

## 5. 验收

1. mock 全链回归：GCM 证据行为不变（现有 47C 套件全绿）。
2. 新门：ASC 与 B2 形态的完整 wire 窗口经真实 builder 到 `APPLIED`/`PASSED`，
   `formal_acceptance=True`；缺 state 探针的窗口停在 APPLIED 之下（fail-closed 保持）。
3. 变异实跑：删掉任一探针行 → 红；归档条件改回 GCM-only → 红。
4. 真机验证（Hardware Blocked，不阻本片）：ASC/B2 管线在真 F64 上的证据留待现场，
   与 P0-5 正式复验同窗口。
