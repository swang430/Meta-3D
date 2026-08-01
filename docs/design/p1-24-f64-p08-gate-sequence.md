# P1-24 设计稿 — `propsim_f64_p08_gate` 诊断序列（P0-8a 唯一合法载体）

> 状态：**已实现**（v1.1 —— v1 经用户 review 后开工；实现期两处修正见 §0.4，
> 待决两项拍板见 §3）
> Roadmap：**P1-24**（2026-08-01 用户拍板提升，出发前硬门槛 —— 不写完不出发）
> 双实证：memory ✅（诊断序列规矩 / F64 禁盲试 / 现场协议 P1-23）/
> **NotebookLM ✅ 已查**（PROPSIM notebook `982222b7`，2026-08-01，逐命令拿手册出处）

---

## 0. 手册实证（NotebookLM 逐点确认，含两处对已 merge 文档的纠错）

### 0.1 命令与语义（全部有手册出处）

| 步骤 | 命令 | 手册语义 |
|---|---|---|
| 关旧仿真 | `DIAG:SIMU:CLOSE` | fail-safe 前置：未加载时发也不报错，加载前必发 |
| 加载 .smu | `CALC:FILT:FILE <filename>` | closed 态命令；大文件需**临时拉长 socket 超时**（手册例 40s），用 `*OPC?` 阻塞同步，**不轮询** |
| 加载就绪判定 | `*OPC?` 返 1 → `SYST:ERR?` 干净 → `DIAG:SIMU:STATE?` = **`STOPPED`** | STOPPED = 已驻留未启动 |
| 输入参考闭环 | `INP:LEV:AUTOSET <input>,<time>`（time ∈ 0.5/1/3/5/10s） | 测量并**同时设** average level + crest factor；**stopped 态命令**；失败（无信号/过强）不改旧值、抛设备错误 |
| 收敛判定 | `SYST:STAT?` | 返回 `1` = 干净；否则列出 `Input cut-off` / `Digital Clipping` 等活跃告警 —— **这是 clipping/cut-off 的正确读法** |
| 启动 | `DIAG:SIMU:GO` → `*OPC?` → `STATE?` = `RUNNING` | |
| 运行中改参 | `OUTP:GAIN:CH <out>,<dB>`（或 `OUTP:LEV:AMP:CH`） | **running 态明确安全**（手册 running 态命令清单在列）；无"一键全局归一化"，逐通道 |
| 电平复测 | `INP:LEV:MEAS? <input>,<time>` | 返 `<平均电平 dBm>,<crest dB>`；**失败 = 设备错误进队列（2026-05-27 现场实证错误码在 -300 段），手册无"查询返回 -300 当哨兵"的语义** |
| bypass | `DIAG:SIMU:MODEL:STATIC <state>`（0=禁用, 1=Channel Model, 2=Butler, **3=Calibration**） | **运行中可切**；启用即物理暂停仿真、信道换 1 径恒定模型；禁用后原运行态自动继续 |
| 错误队列 | `SYST:ERR?` **循环读到 `0,"No error"`** | FIFO 逐条销毁；`-100`=命令不存在，`-200`=状态不对（如未加载就 GO），**-113 手册未覆盖** |

### 0.2 ⚠️ 排雷：`GOS`（`DIAG:SIMU:GOStart`）**不是** GO+STATIC
手册原义 = **停止并倒回起点**（"stops the emulation and rewinds to the start… performs
stop operation"）。发 GOS 后 STATE? = STOPPED，需重新 GO。序列内**禁用 GOS 当启动**。

### 0.3 对已 merge 文档的两处纠错（本片随行修正）

1. **"-300 哨兵"语义不实**：`on-site-debug-protocol.md` Phase 1.5 步骤 0 与 roadmap
   P1-24 条目里"无信号 `INP:LEV:MEAS?` 返 -300"来自 Codex #257 R2 的说法。精确口径
   （实现期核准）：**-300 作为错误队列里的设备错误码有现场实证**（2026-05-27
   morning-log）且与手册"失败测量产生 device specific error"一致；**不实的是把它
   写成查询的哨兵返回值** —— 手册无任何哨兵返回值语义，判据必须是"错误队列出现
   测量失败错误"，不是"返回值==-300"。（教训：审查 finding 的仪器语义断言也要过
   手册，我当时没查就写进了两份文档。）
2. **AUTOSET 时序错排**：协议把"AUTOSET 闭环"放在 run 之后 —— 手册明确它是
   **stopped 态命令**。序列正确时序 = load(STOPPED) → AUTOSET → GO。协议 Phase 1.5
   步骤顺序随本片修正。

### 0.4 实现期修正（v1 → v1.1，物理现实/驱动真值裁决）

1. **§1 步骤 11"退出自动续跑 → 断言 RUNNING"撤回**：手册 ATE AN §2.4.5 说
   "进旁路前在跑 → 退旁路后继续跑"，但 **2026-07-03 现场实证相反**
   （`test_f64_bypass_state_machine.py` 头注：直通稳态 = STOPPED + STATIC 3，
   恢复衰落 = STATIC 0 + **显式 GO**）。断言自动续跑在真机上会假红。实现改为：
   退旁路后读 `STATE?` **如实归档**（续不续跑本身是待验语义），非 RUNNING 则
   显式 GO 恢复 —— 两种固件行为都走得通，RUNNING 断言 #2 打在恢复后。
2. **§1 步骤 12 收尾 CLOSE 改为 GOS 留驻**：剧本绕过驱动直发 `DIAG:SIMU:CLOSE`
   会让驱动的 `_loaded_emulation_file` 身份缓存变 stale（验证打在真实生效端母题）。
   收尾稳态 = 场景包留驻 + STOPPED + STATIC 0 + 增益还原；正式测试的加载事务
   自带 CLOSE preflight，不缺这一发。
3. **实现取舍**：
   - **复用生产原子**而非重抄 SCPI：`load_local_scenario`（P0-3 手册化加载事务）/
     `autoset_inputs`（fail-loud 版；`autoset_input_level` 无错误门不用）/
     `start_emulation` / `stop_emulation` / `set_bypass_mode` / `set_output_gain` /
     `measure_input`。剧本级直查只用于原样归档回读与零残留检查。
   - **新增 SCPI 仅两条查询**：`OUTP:GAIN:CH? <out>`（§20.4.5.7，纯数字 dB）与
     `OUTP:GAIN:LIM? <out>`（§20.4.5.8，`<lo>,<hi>`，超范围写会被**静默钳位**——
     所以改参后回读比对是行为判据）。2026-08-01 NotebookLM 过手册
     （「新增 SCPI 先查」规矩）。
   - **`smu_path` 必填参数**（无默认值）：诊断序列运行时拿不到 DB 会话
     （`DiagnosticContext` 不持 session），"默认 SCD 那条"由参数 label + 空值
     报错指路 `standard_channel_definitions.associated_file_path` 承载，
     不为此加 DB 管道（去掉>加机制）。

## 1. 序列设计（`api-service/app/diagnostics/sequences/propsim_f64_p08_gate.py`）

剧本式（带动作），每步后循环读 `SYST:ERR?` 到干净（诊断序列既有约束）：

```
0. 前置声明: UXM 满 RB DL 已激活 (CE↔BS 协调, 操作员确认项 — 序列参数带
   `uxm_dl_confirmed=true` 显式声明, 不隐式假设)
1. DIAG:SIMU:CLOSE                        → ERR 清
2. 拉长 socket 超时 → CALC:FILT:FILE <p08 场景包> → *OPC? → 还原超时 → ERR
3. DIAG:SIMU:STATE?  断言 STOPPED
4. INP:LEV:AUTOSET <in>,3                 → ERR (失败=测量错误, fail gate)
5. SYST:STAT?        断言 1 (无 Input cut-off / Digital Clipping)
6. DIAG:SIMU:GO → *OPC? → STATE? 断言 RUNNING → ERR
7. OUTP:GAIN:CH <out>,<Δ> (改参) → ERR → OUTP:GAIN:CH? 回读一致
8. INP:LEV:MEAS? <in>,3 → 记录 (avg,crest) → ERR
9. DIAG:SIMU:MODEL:STATIC 3 (Calibration bypass) → ERR
10. INP:LEV:MEAS? <in>,3 → 记录 bypass 态 (avg,crest) → SYST:STAT? → ERR
11. DIAG:SIMU:MODEL:STATIC 0 (退出 bypass) → STATE? 如实记录 (§0.4-1: 不假设
    自动续跑) → 非 RUNNING 则显式 GO → 断言 RUNNING
12. 收尾: OUTP:GAIN:CH 还原(回读核对) → GOS 停住、场景包留驻 (§0.4-2: 不发
    CLOSE) → ERR
Gate 判据 (P0-8a): 全程错误队列零残留 + AUTOSET 后 SYST:STAT?=1 +
  RUNNING 断言两次 (GO 后 + 退 bypass 恢复后) + bypass 态电平读取成功 (与衰落态同窗口)
```

每步落 `DiagnosticRun`（参数/成败/**仪器原始回复**/耗时），符合诊断序列基建契约。

## 2. 范围与不做

- 复用生产驱动的连接/懒重连（不自开 socket）；命令全部走 §0.1 手册确认集
- 不做 DL ACK 判定（那是 P0-8b，挂 Phase 4，依赖 DUT）
- 不改驱动本体；序列文件 + 注册 + mock 跑通 + 文档两处纠错

## 3. 待决（2026-08-01 用户拍板：两项均按推荐）

- ① p08 场景包：**SCD 登记的 N78/ARFCN 636666/BW40 那条**（实测频率已验，S6/P1-22
  全链用过）。实现形态：`smu_path` 必填参数 + 指路 SCD（理由见 §0.4-3——序列无 DB
  会话，不硬编码站点路径）
- ② 改参步骤 Δ：**±1 dB 往返**（写 → 回读比对 → 还原），`gain_delta_db` 参数默认
  1.0、上限 3.0（防手滑真动在测链路电平）

## 4. 门

- **D-1 mock 行为门**：mock driver 跑通全序列 + 每步错误队列检查存在性断言 +
  时序断言（AUTOSET 在 GO 前 —— 变异：把 AUTOSET 挪到 GO 后 → mock 状态机若支持
  态检查则红；mock 不支持则如实申报该变异不可行，时序由代码顺序 + 内审锁）
- **D-2 全量回归 + 规则门**
- **D-3 申报**：真机行为（AUTOSET 收敛、bypass 电平窗口）只能现场验 —— 这正是
  P0-8a 现场半的内容，序列是载体不是替身
