# P2-35 执行计划

设计稿：[2026-08-21-p2-35-contextvar-isolation-design.md](2026-08-21-p2-35-contextvar-isolation-design.md)

- [x] 勘察：grep `current_execution_id` 全部 31 处触点，逐个判"动/不动"（设计稿 §3）
- [x] RED：实跑最小顺序组合复现泄漏 —— `test_mimo_ota_report_verified_backcompat.py::test_vrt_terminal_transition_allows_only_one_archive_owner` + `test_p1_36_execution_id.py::test_no_execution_means_default_not_empty` → 1 failed（泄漏 UUID 实录在案）
- [x] GREEN-1：`tests/conftest.py` 加套件级 autouse fixture `_suite_isolate_execution_contextvar`
- [x] GREEN-2：新增行为门 `tests/test_p2_35_contextvar_isolation.py`（自带泄漏源的 a/b 两条）
- [x] 验证：RED 组合 + 行为门合跑 → `4 passed`
- [x] 变异实跑：掏空 conftest fixture → 行为门 b 红（1 failed, 1 passed）+ RED 组合 p1_36 复红（1 failed, 1 passed）→ 已恢复（无 MUTATION 残留）
- [x] 全量：`cd api-service && .venv/bin/python -m pytest -q --color=no -p no:cacheprovider` → `4071 passed, 5 skipped, 4234 warnings in 90.93s` —— **0 failed**
- [ ] 内审：主 agent 统一安排（协调者指示，本 session 未跑 —— 如实记录，不当"审过无问题"）
- [x] commit（中文、`-F`、trailer）+ push 分支（不开 PR）
