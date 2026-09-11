# P2-70 Implementation Plan

> **For agentic workers:** 使用 executing-plans 顺序执行；最终独立只读功能内审。

**Goal:** 为 P2-55 两个 FDD 样本提供现有 GUI 可调用、关闭小区、可归档的配置诊断。
**Architecture:** 自动发现序列消费共同 resolver 的租约内快照；复用 CMW builder/parser/SAFE_IDLE。
结果仅为 DiagnosticRun，不引入正式 profile 或 KPI 消费方。
**Tech Stack:** Python/FastAPI/SQLAlchemy，pytest，现有 React 诊断入口。
**Spec:** `docs/design/2026-09-11-p2-70-cmw-fdd-matrix-probe.md`

## Global Constraints

- 仅 FDD/B200/1CC-nx2，`tm1_one` 与 `tm3_two` 两个整行样本。
- 固件至少 V3.5.40，KS500/KS520；所有证据保持 `formal_eligible=false`。
- 不发 Cell ON、不改路由/带宽/频点/正式 profile；未知值拒绝，不取 *RST 默认。
- DCI 出处为手册 pp.752–753，查询规则 §1.2.4 p.15；NotebookLM 复核已记入设计。

## Task 1：固定样本与安全诊断序列

文件：新增 `api-service/app/diagnostics/sequences/cmw500_fdd_matrix_probe.py`，
修改 `api-service/app/hal/cmw500_command_profile.py`，新增
`api-service/tests/test_p2_70_cmw_fdd_matrix_probe.py`。
接口：`run(ctx, hal, params, *, log, resolved_binding=None)` 返回 `SequenceRunResult`；
取消携带相同结构的部分结果，始终先完成 SAFE_IDLE。

- [x] 写真实驱动 + 外部 fake transport 测试：固定 TM1 的 DL 为 `N100,QPSK,T5`，TM3 为
  `N100,Q16,T13`；断言 `result.extra['formal_eligible'] is False`。
- [x] 运行新文件确认缺模块 RED；补白名单 DCI builder、参数解析和 preflight。
- [x] 实现 `read → compare → conditional write → OPC + error queue → readback`，
  最终再次比较全部字段，`finally` 在写入后复用 `ensure_safe_idle()`。
- [x] 增加未知/错误/漂移/取消/再入反例；每次定点 RED→GREEN，不提前跑全量。

## Task 2：API 租约绑定、持久化与验收

文件：`api-service/app/api/diagnostic_sequence.py`、同一专项测试、设计与 roadmap。
接口：本 key 的 lease `validate_before_remote` 调共同 `resolve_base_station_binding`；
序列接收服务器快照，不接受客户端快照；禁用监控，避免夺取错误队列。

- [x] 写 API 到 DiagnosticRun 的 RED，覆盖绑定不符零 I/O、正常/失败/取消的原始归档。
- [x] 最小接入 key-specific resolver 与取消结果；在 lease exit 前保存结果，release 失败不丢部分证据。
- [x] 定点与受影响链 GREEN；两条核心回退（忽略最终比对、跳过绑定校验）须检出。
- [x] 最终运行后端全量、GUI 诊断契约/build、compileall、Alembic heads、diff-check；保留命令及统计。
- [x] 独立只读功能内审，修 P1；本地实现交付准备完毕，外审状态以 PR 台账为准。
- [ ] Codex R1→R2，最新 HEAD 无 P1 且 checks/mergeable 满足时 merge commit；fetch/ff-only/清理。

基线命令：`.venv/bin/python -m pytest -q -o log_cli=false tests/test_p2_51_cmw_mac_config.py tests/test_diagnostic_execution_exclusion.py tests/test_p2_28_diagnostic_sequence_evidence.py`；38 passed。

## 实施与验证记录（2026-09-11）

输入基线 `c2038019` 加本片受控 diff；提交后的 review 台账放 PR，不为填写时间另造提交。
memory 索引没有命中可用条目，以当前仓库及原始手册为准。NotebookLM 查询、source ID、
原文核对与被否定的推断均见设计的「权威来源」节。

- Task 1 初始 4 RED（缺 DCI builder/序列模块）→ 4 GREEN。
- Task 2 真实 API→持久化详情先 RED（缺 binding 快照），最小接入后 GREEN。
- 独立审查发现 F1：TDD + 初始 ON 被拒后，公共 lease release 仍发 OFF。
  API 反例先 RED（实际 OFF），后将只读前置换到控制 lease 之前、同一 HAL guard 内；
  不放宽共同 SAFE_IDLE。独立复查 TDD/B100/坏 route/身份漂移/非零队列均零写，
  有效 FDD 正例完成配置并确认 release；最终 P1=0。
- 暖连接补两条 RED（当次 identity raw 缺失、身份漂移仍成功）→ GREEN；
  身份查询复用既有 builder/parser，不另造缓存真值。
- 最终 `tests/test_p2_70_cmw_fdd_matrix_probe.py`：32 passed；与
  `tests/test_p1_73b_cmw_command_profile.py` 合跑：47 passed（exit 0，1.30s）。
  调用统一参数 `-q --color=no -o log_cli=false --show-capture=no --tb=short`。
- 两条运行时变异（没有改磁盘文件）：`inspect.getsource` + 唯一锚点断言 + `exec(compile(...))`；
  将序列最终比较改成 `if False and ...`，
  `test_later_setting_cannot_clobber_final_tuple` 红（success 错为 True）；
  将共同 resolver 的 binding endpoint 拒绝条件改成 `if False and ...`，
  `test_api_failure_retains_truth_and_does_not_leak_guard[binding]` 红（response.success 错为 True）。
  两次 pytest exit 1，外层断言 exit 1 成功；进程退出即丢弃变异。
- GUI：`node --test test/diagnosticSequenceEvidence.test.ts` → 8 passed；
  `npm run build` → exit 0（8053 modules，11.92s）；没有新增路由/schema/GUI 真值，
  现有完整证据面板消费同一详情响应。
- 首轮默认环境全量：6513 passed / 7 failed / 5 skipped（102.09s）。
  其中 1 项为新增 DCI 目录清单/来源格式未同步，已补同一审计集合后 47 passed；
  另 6 项 F64 在未修改 main 的同文件独立复跑也失败（39 passed / 6 failed），
  均因 localhost:5432 无 PostgreSQL。没有启动或改动生产库、没有修改 F64 功能。
  用临时 SQLite 测试库注入现有 DATABASE_URL 后 F64 45 passed。

最终全量使用下列独立临时存储入口，普通业务函数和 pytest 用例不替换；
`tests.conftest` 仍隔离日志和真实仪器。SQLite 仅作本地测试，不代表 PostgreSQL/真机验收：

```python
import os, tempfile
with tempfile.TemporaryDirectory(prefix="p270-test-db-") as database_dir:
    os.environ["DATABASE_URL"] = f"sqlite:///{database_dir}/isolated.sqlite"
    import tests.conftest
    from app.db.database import Base, engine
    Base.metadata.create_all(engine)
    import pytest
    code = pytest.main(["-q", "--color=no", "-o", "log_cli=false",
                        "--show-capture=no", "--tb=short"])
    engine.dispose()
    raise SystemExit(code)
```

从 `api-service` 以 `.venv/bin/python -` 执行上述脚本。
最终输出：`6520 passed, 5 skipped, 5222 warnings in 145.67s`，exit 0；
覆盖本片最终代码和测试输入（后续只有文档记录更新），没有忽略或跳过上述 F64 用例。
补充静态门：`.venv/bin/python -m compileall -q app`、`.venv/bin/alembic heads`、
`git diff --check` 均 exit 0；唯一 head `c5e7f9a1b3d6`。现场零执行，P2-55 保持开放。

### R1 增量（PR #475）

R1 覆盖 `48b53807`，review `5179344637`，无 P1；P2 inline `3989742896`：
解析异常跳过错误队列，归档缺仪器原因。route/DCI 空回复且产生 `-221` 的两条反例
先 RED（pending 错误未消费），后仅调整本序列 `read()`：普通查询先归档/核对错误队列，
再解析；异常将该 raw step 记为 False；ERR 是递归终点。没有修改公共驱动、租约或正式链。

最终相关命令（同上统一 pytest 参数）覆盖：
`tests/test_p2_70_cmw_fdd_matrix_probe.py tests/test_p1_73b_cmw_command_profile.py
tests/test_diagnostic_sequences.py tests/test_p2_51_cmw_mac_config.py
tests/test_diagnostic_execution_exclusion.py tests/test_p2_28_diagnostic_sequence_evidence.py
tests/test_rule_gates.py` → `231 passed, 174 warnings in 8.95s`，exit 0。
compileall / diff-check exit 0。本次为单一诊断局部错误处理，既有 API/共享安全/正式执行输入未变，
按验证分档不重复后端全量；上面的 6520 passed 是 `48b53807` 的全量，不冒称在本增量重跑。
GUI 和依赖未变，复用原 GUI 契约/build。独立增量内审及 R2 结果在 PR 台账留痕。
