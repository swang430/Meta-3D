# P1-67 UXM 状态文件命令换手册真值 — 设计

> 来源：P1-65（#380）手册对账、roadmap Discovered「驱动层事实」第 2 条；2026-08-24 用户批准。
> 手册原件 = 本地 `UXM5G_SCPI_06_General_Examples_Shared.md`「Export / Import SCPI」节
> （`SYSTem:SCPI:IMPort/:EXPort/:FOLDer/:IMPort:STATus?/:IMPort:INCLude:PRESet` 全有原文；
> `SYSTem:CONFiguration:LOAD` / `MMEMory:CATalog?` md+HTML 0 命中，NotebookLM 核对不存在）。

## 四行契约
- 搜索命中：`uxm_base_station.py` / `uxm_command_profiles.py` 禁令 grep；只认原文。
- 必要性：`configure(state_file=…)` 一键配置路径发的是手册不存在的命令 —— 真机上必 -113，
  "一键配置"从未可能工作过；`list_state_files` 同。
- 范围：`uxm_command_profiles.py`（5G profile 的 STATE_LOAD / STATE_SAVE / STATE_LIST 三个字段）+
  `uxm_base_station.py` 的 `load_state_file` / `save_state_file` / `list_state_files` 三方法 + 测试。
- 爆炸半径：原最坏 = 路径必失败且报错指向错误方向；修完最坏 = IMPort 语义差异（导入会恢复
  整机状态、`INCLude:PRESet` 可能先复位）——在 docstring 与日志里如实披露。Y < X。

## 修法（换源 + fail-closed）
1. profile（仅 5G_NR_Test；IRAT 保持 None 不变）：
   - `STATE_LOAD = 'SYSTem:SCPI:IMPort "{filepath}"'`（手册原文 "Import (i.e. load) a SCPI file,
     recovering a previously exported application state"）
   - `STATE_SAVE = 'SYSTem:SCPI:EXPort "{filepath}"'`（原文 "Export (i.e. save) the current
     application state into a SCPI file"）
   - `STATE_LIST = None` + 注释：**手册没有文件列表查询命令**（`MMEMory:CATalog?` 查无；
     未探测 ≠ 不支持，不猜替代）。
2. `load_state_file`：写后加 `SYSTem:SCPI:IMPort:STATus?` 复核（Query only，手册原文），
   非成功 → 返回 False + 错误队列读取；docstring 更新语义（整机状态恢复 + PRESet 行为披露，
   引 P1-65 `uxm_fresh_start_truth` 同源）。文件路径含引号/换行 fail-loud 拒绝（同 P1-65 序列）。
3. `list_state_files`：STATE_LIST 为 None → 返回空列表并 log "本方言无手册可依的文件列表命令"，
   不发任何 SCPI（现状大概已按 None 跳过 —— 核实并补门）。
4. 行为门：假驱动 state_file 路径 → 收到 `SYSTem:SCPI:IMPort "<f>"` + `IMPort:STATus?`，
   **不含** `SYSTem:CONFiguration:LOAD` / `MMEMory:CATalog?`；STATus? 失败 → configure 返回 False；
   注入路径拒绝；IRAT 下 state_file → 如实拒绝（STATE_LOAD None）。
5. 变异：IMPort 后不查 STATus? → 红；换回编造命令 → 红；注入放行 → 红。

## 不做
- 不动 GUI；不动 orchestrator 上层；不引入文件列表的替代猜测。
