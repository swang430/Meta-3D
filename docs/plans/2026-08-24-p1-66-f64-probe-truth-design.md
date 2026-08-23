# P1-66 F64 连接路径盲试探针换手册真值 — 设计

> 来源：P1-65（#380）手册对账查出、roadmap Discovered「2026-08-23 P1-65 查出的驱动层事实」第 1 条；
> 2026-08-24 用户批准（"继续，整体完成"）。手册原件 = `Propsim User Reference.pdf` Rev 10.2
> （pdftotext 文本在 scratchpad/manuals/，章节行号见 P1-65 设计稿 §2）。

## 四行契约
- 搜索命中：`propsim_f64.py` 禁令 grep；memory 禁盲试 / 只认原文；P1-65 设计稿 §2/§5。
- 必要性：每次 connect 发两条手册查无的命令（`SYSTem:CALibration:USER:LIST?`、`OUTPut:INTERFerence:LIST?`），
  各留一条 -100 在错误队列（08-07 一天 269 次连接）；且 -100 payload 当响应串回时被当 ACK →
  **许可假阳性**（08-07 实测驱动自称 ['INT-GEN','USER-ALIGN'] 全来自探针）。
- 范围：`app/hal/propsim_f64.py`（`_F64_OPTION_PROBES` 两条目及其执行分支）+
  `app/diagnostics/sequences/propsim_f64_health.py:176` 第三站点 + 对应测试。不动其它驱动方法。
- 爆炸半径：原最坏 = 错误队列残留 + 许可假阳性（把没有的能力当有）；修完最坏 = 能力少判
  （fail-closed，config 显式声明可兜）。Y < X。

## 事实（已核）
- 现场 `SYST:INFO?` 真实回复含 **"AWGN interferences:32"** → INT-GEN 由既有
  `_F64_SYSTINFO_KEYWORDS`（"interference"）判出，探针多余。
- USER-ALIGN：connect 流程本就调 `get_user_alignment_status()`（`SYSTem:CALIBration:USER:GET?`，
  §20.4.2.19，未启用返回空串）→ `_update_user_alignment_capability()` —— 真来源已在，探针多余。
- `_probe_installed_options` 的探针分支把"有响应"当 ACK；F64 会把 `-100,"…"` 当响应串回
  （`_is_unsupported_error_payload` 就是为此存在）→ 探针机制本身不可靠。

## 修法（去掉 > 换源）
1. 删除 `_F64_OPTION_PROBES` 全部条目与其执行循环（保留 SYST:INFO? 关键字扫描）；
   `_installed_options` 只来自 SYST:INFO? 扫描 + USER:GET? 状态（若现逻辑把 USER-ALIGN 也放进
   options，改为由 `_update_user_alignment_capability` 的真值驱动）。日志措辞改
   "licenses from SYSTem:INFO?（手册 §20.4.2.4）"，删除 "feature-probed" 字样。
2. `propsim_f64_health.py` 第 176 行 INT_LIST 探针行：删除（该文件探针表是只读普查；
   `OUTPut:INTERFerence:GET?` 需仿真已加载，health 不保证前置 —— P1-65 的
   `propsim_f64_license_truth` 已按前置正确地探它，不在 health 里重复）。
3. 行为门：假驱动 connect 全流程 → 收到的命令集合**不含**两条编造命令；SYST:INFO? 含
   "AWGN interferences" → has_interference_generator True；不含 → False（除非 config 显式）；
   USER:GET? 空串 → 无 USER-ALIGN；error-payload 回复不再造成假阳性。
4. 变异：把任一编造命令加回 → 门红；SYST:INFO? 关键字扫描去掉 → 门红。

## 不做
- 不改 `set_calibration_tone` 的 fail-closed 门；不改 config 显式声明通道；不动 UXM。
