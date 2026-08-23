# P1-65 实施计划

设计稿：`2026-08-23-p1-65-blocker-carrier-sequences-design.md`（先读它；命令出处全在 §2）。

## 分工（并行，文件互不相交；开发 agent 不 commit、不跑全量、不动驱动）
- A 组：`emcenter_switch_health`、`connection_idle_hold_probe`
- B 组：`propsim_f64_output_level_windows`、`propsim_f64_license_truth`、`propsim_f64_local_handback_check`
- C 组：`uxm_offset_to_carrier_probe`、`uxm_fresh_start_truth`、`uxm_sim_identity_truth`

## 每条序列的步骤
1. RED：先写 `tests/test_p1_65_<seq>.py`（回放假驱动 + mock 拒绝 + 只读不变量 + 错误队列门），跑红。
2. GREEN：写 `app/diagnostics/sequences/<seq>.py`（只用设计稿 §2 列出的命令；G18 声明）。
3. 变异实跑（内存快照还原，replace 必 assert 命中）→ 还原复绿。
4. 报告：文件清单（修/顺带/越界）、门与变异输出、未做事项。

## 主 agent
- 全量 + `test_rule_gates`（G12/G17/G18）+ GUI 面板不改（loader 自动列出）→ 内审全套 → commit → PR → Gemini。
