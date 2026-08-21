# P2-34 实施计划：正式执行失败告警的发布结果契约

设计依据：[同日设计稿](2026-08-21-p2-34-failure-alert-contract-design.md)。TDD 顺序执行。

## 步骤

1. **RED**：新建 `api-service/tests/test_p2_34_failure_alert_contract.py`
   （fixture 照 `test_execution_failure_alerts.py` 的 sqlite StaticPool +
   monkeypatch SessionLocal 模式），落设计稿 §4 六门，实跑确认红。
2. **GREEN-1** `app/services/execution_failure_alerts.py`：
   - outcome 常量 + `RECORDED_OUTCOMES` 白名单 + `CONFIG_RECORD_KEY`；
   - `emit_execution_failed_alert` 返回 outcome 字符串（拆掉 bool 混叠）；
   - `_record_publish_outcome(...)`：告警事务后的第二个独立事务，best-effort，
     异常吞 + log；duplicate 仅补缺；绝不触碰 status；
   - `resolve_recorded_outcome(config)`：白名单读方，畸形/缺失 → None（未记录）。
3. **GREEN-2** 读方接线：
   - `schemas/test_plan.py::ExecutionHistoryItem` 加 `failure_alert_outcome:
     Optional[str] = None`（注释写明 None=未记录，沿用三态先例）；
   - `api/test_execution.py::_to_history_item` 经 resolver 派生该字段；
   - `api/openapi.yaml::TestExecutionItem` 加同名可选属性；
     `cd gui && npm run openapi:generate` 再生成；
   - 前端手写镜像各一行：`TestExecutionRecord`（TestManagement/types）、
     `TestExecutionListResponse` 侧 `types/api.ts`（若该类型内联行形状）。
4. **既有测试对齐**（顺带，同源于返回值契约变更）：
   `test_execution_failure_alerts.py` 的 `is True/is False` 断言改为对应枚举值。
5. **变异实跑**：设计稿 §4 五条，逐条改源 → 跑门确认红 → `git checkout` 还原 →
   还原后复跑确认绿（脚本化替换须 assert 命中）。
6. **全量**：`cd api-service && .venv/bin/python -m pytest -q --color=no
   -p no:cacheprovider`；已知失败 `test_p1_36_execution_id::
   test_no_execution_means_default_not_empty` 之外零失败。
7. commit（中文、`-F`、Co-Authored-By trailer）→ push 分支，不开 PR。

## 硬约束核对单

- [ ] 不改 roadmap；不动他片文件；不建迁移
- [ ] G10：零新增 `TestExecution.status` 字面量写点
- [ ] 告警/记录任何失败都不改执行终态（门B/B2 守）
- [ ] 历史行缺记录 = 未记录，读方绝不折叠成成功（门C 守）
