# P2-33 日志体验包 — 执行 plan

> 设计稿：`2026-08-21-p2-33-log-ux-pack-design.md`（故障/改法/门/变异见彼处，本文件只列步骤）。

## 步骤

1. **RED**：新建 `api-service/tests/test_p2_33_log_ux_pack.py`，四条各自的门先写先跑，
   确认按预期红（①② 行为门对现状红；③④ 结构/不变量门对现状红）。
2. **GREEN ①**：`app/core/logging_config.py` —— `_key` 末尾加 `record.levelno` + 2 处注解。
3. **GREEN ②**：`app/api/system_logs.py` —— `_keyword_hit` 抽出、`_group_matches` 新增、
   扫描器 predicate 升二参（2 处父判定 + 孤儿分支）、tail/history lambda 与 export
   `emit_group` 改走组谓词；同步更新 `test_p1_35` 的 `_entry_matches(` token 门。
4. **GREEN ③**：`gui/src/features/Dashboard/ZoneLogsAlerts.tsx` —— 四处加 CRITICAL。
5. **GREEN ④**：`gui/src/features/Reports/components/SystemLogViewer.tsx` —— 多选化；
   同步更新 `test_p1_35` 两门（ISSUE_LEVELS 用法、哨兵 → join 恰一处）。
6. **变异实跑**：四条各至少一变异（设计稿列的），确认门红后还原（git 快照对照）。
7. **全量**：`cd api-service && .venv/bin/python -m pytest -q --color=no -p no:cacheprovider`；
   已知失败 `test_p1_36_execution_id::test_no_execution_means_default_not_empty` 除外零失败。
8. **build**：`cd gui && npm run build`。
9. **镜像 grep**（③⁺）：`CRITICAL`、`仅异常`、`ISSUES`、`SegmentedControl`、`级别过滤`、
   `suppressed` 等关键词全仓扫，命中处逐一问"现在还成立吗"。
10. commit（中文、`-F`、trailer）→ push 分支，不开 PR。

## 边界（不碰）

- SystemLogViewer 的入口/跳转面：`initialExecutionFilter`、`isolateExecution`、
  `isolateRequest`、P1-39 useEffect（P2-36 在做）。
- 后端 `_entry_matches` 的集合语义两 token、G14/G15 的全部断言 token。
- roadmap 文件、迁移、openapi.yaml（后端契约无变化）。
