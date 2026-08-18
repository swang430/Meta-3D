# P2-28 Diagnostic Sequence Evidence Persistence Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 让诊断序列的完整结构化 raw 证据与 `DiagnosticRun` 同生命周期持久化，并可从 GUI 最近运行重新打开。

**Architecture:** 新增 sequence-only nullable JSONB 字段，保存与 live response 同源且带 schema version 的完整 evidence envelope；列表保持 2KB 摘要，详情才返回大载荷。GUI 通过详情 API 读取旧运行并复用 live 结果展示，旧行 null 时明确 fail-closed，不从摘要猜测。

**Tech Stack:** FastAPI, Pydantic v2, SQLAlchemy/Alembic, PostgreSQL JSONB/SQLite JSON, React/TypeScript, Mantine, pytest, Node test runner

---

### Task 1: 用 RED 锁住 sequence-only 数据库契约

**Files:**
- Create: `api-service/tests/test_p2_28_diagnostic_sequence_evidence.py`
- Create: `api-service/alembic/versions/a4c6e8f0b2d4_add_diagnostic_sequence_evidence.py`
- Modify: `api-service/app/models/diagnostic_run.py`
- Modify: `api-service/app/services/diagnostic_context.py`
- Modify: `api-service/tests/test_alembic_chain.py`

**Step 1: Write the failing persistence tests**

新增行为测试：

- `DiagnosticContext.record_run(..., sequence_evidence=evidence)` 后 JSON 逐字段原样保存，
  包括 `raw=""`、换行、引号与嵌套 extra；
- 不传该参数的 SCPI/commissioning 行保持 `sequence_evidence is None`；
- 模型 metadata 与 Alembic 迁移均包含 nullable `sequence_evidence`，greenfield/brownfield 可升级。

**Step 2: Run test to verify it fails**

Run:
`/Users/simon/Tools/MIMO-First/api-service/.venv/bin/python -m pytest -q api-service/tests/test_p2_28_diagnostic_sequence_evidence.py api-service/tests/test_alembic_chain.py`

Expected: FAIL，模型/record_run 尚无 `sequence_evidence`。

**Step 3: Write minimal model and migration**

- `DiagnosticRun.sequence_evidence = Column(_JSON_PG_OR_SQLITE, nullable=True)`；
- `record_run()` 增加同名 optional dict 参数并原样写入；
- 新迁移以当前唯一 head `f8a1c3e5b7d9` 为 down revision，复用 `table_exists/column_exists`
  保护 brownfield 与 baseline 已建列场景；downgrade 对称删除。

**Step 4: Run tests to verify they pass**

Expected: focused persistence + Alembic PASS，`alembic heads` 仍只有一个 head。

**Step 5: Commit**

Commit: `feat: add diagnostic sequence evidence storage`

### Task 2: 用 RED 锁住 live response 与历史详情同源

**Files:**
- Create: `api-service/app/schemas/diagnostic_evidence.py`
- Modify: `api-service/app/api/diagnostic_sequence.py`
- Modify: `api-service/app/api/diagnostic_run.py`
- Modify: `api-service/tests/test_p2_28_diagnostic_sequence_evidence.py`
- Modify: `api-service/tests/test_diagnostic_sequences.py`

**Step 1: Write the failing API behavior tests**

通过真实 `POST /diagnostic-sequences/raw_stub/run` 产生超过 2KB 的 raw 与 `raw=""`，随后读取：

- live response 的 `summary/duration_ms/log/steps/extra` 与详情 `sequence_evidence` 一致；
- `schema_version == 1`；
- `output_excerpt` 已截断仍不影响 evidence；
- `GET /diagnostic-runs` item 不含大载荷；
- 旧行 detail 返回 null；failure/exception/cancelled 行有同形 envelope，未拿到 partial 时 steps 为空且
  `partial_result_available=false`。

**Step 2: Run test to verify it fails**

Expected: detail schema 没有 sequence evidence，endpoint 也未写入。

**Step 3: Write shared schema and endpoint wiring**

- 在 `app/schemas/diagnostic_evidence.py` 定义共享 `SequenceStepEvidence` 与
  `SequenceEvidence(schema_version=1, summary, duration_ms, log, steps, extra)`；
- live `SequenceRunResponse` 与 detail response 复用同一 step/evidence 定义；
- `run_diagnostic_sequence()` 在调用 `record_run()` 前从已经确定的局部真值构造 envelope，
  通过 `model_dump(mode="json")` 写入；返回 live response 继续使用同一对象内容；
- `DiagnosticRunDetail` 增加 nullable typed `sequence_evidence`，summary/list 不增加字段。

**Step 4: Run tests to verify they pass**

Expected: focused API + existing diagnostic sequence tests PASS。

**Step 5: Commit**

Commit: `feat: persist complete diagnostic sequence evidence`

### Task 3: 用 RED 锁住 GUI 历史证据重新打开

**Files:**
- Create: `gui/src/features/Diagnostics/sequenceEvidence.ts`
- Create: `gui/test/diagnosticSequenceEvidence.test.ts`
- Modify: `gui/src/api/diagnosticService.ts`
- Modify: `gui/src/features/Diagnostics/SequenceRunnerPanel.tsx`

**Step 1: Write the failing pure contract test**

对 helper 断言：

- typed `DiagnosticRunDetail.sequence_evidence` 能转换为现有结果展示输入，保留空 raw、日志与 extra；
- null evidence 返回明确的 legacy/unavailable 状态，不回退解析 `output_excerpt`；
- source contract 锁住 Recent Runs 的详情请求与“查看完整证据”入口。

**Step 2: Run test to verify it fails**

Run: `cd gui && npx tsx --test test/diagnosticSequenceEvidence.test.ts`

Expected: FAIL，类型/helper/UI wiring 尚不存在。

**Step 3: Write minimal GUI implementation**

- 补齐 `SequenceEvidence` 与 `DiagnosticRunDetail.sequence_evidence` 类型；
- Recent Runs 每行增加查看动作，调用 `getDiagnosticRun(id)`；
- 抽出复用的 evidence 结果展示，使 live 与历史显示同一组 summary/steps/raw/log/extra；
- null 显示“旧记录未持久化完整证据”，只可查看摘要，不标为完整；
- 加载/409/5xx 使用服务端 detail/message，失败不触发序列重跑、不清空 live result。

**Step 4: Run test and production build**

Run: `cd gui && npx tsx --test test/diagnosticSequenceEvidence.test.ts && npm run build`

Expected: PASS；production build 成功。

**Step 5: Commit**

Commit: `feat(gui): reopen persisted diagnostic sequence evidence`

### Task 4: 全集回归、roadmap 与 fresh 内审

**Files:**
- Modify: `docs/roadmap-first-call.md`
- Modify if facts changed: `docs/plans/2026-08-18-p2-28-diagnostic-evidence-persistence-design.md`

**Step 1: Run focused and full related regression**

Run:
`/Users/simon/Tools/MIMO-First/api-service/.venv/bin/python -m pytest -q api-service/tests/test_p2_28_diagnostic_sequence_evidence.py api-service/tests/test_diagnostic_context.py api-service/tests/test_diagnostic_sequences.py api-service/tests/test_diagnostic_execution_exclusion.py api-service/tests/test_commissioning_adhoc.py api-service/tests/test_scpi_console_audit.py api-service/tests/test_alembic_chain.py api-service/tests/test_rule_gates.py`

Expected: PASS；SCPI/commissioning 的既有 `result_extra` 与摘要契约不变。

**Step 2: Run compile/build hygiene**

Run: `/Users/simon/Tools/MIMO-First/api-service/.venv/bin/python -m compileall -q api-service/app api-service/tests`

Run: `cd gui && npm run build`

Run: `cd api-service && /Users/simon/Tools/MIMO-First/api-service/.venv/bin/alembic heads`

Run: `git diff --check`

Expected: all pass/clean；单一 Alembic head。

**Step 3: Update roadmap with actual evidence**

同步 Current Focus、P2-28 表项、LOCAL-OPEN 与来源 Discovered；不得预写未运行的数字。

**Step 4: Fresh internal review**

按 AGENTS.md 逐项核对成功、设备拒绝、异常、取消、旧行、列表、详情、GUI 历史、SCPI 与 commissioning
对称路径；P1 修到 0，P2/P3 分栏登记。

**Step 5: Commit and open Ready PR**

Commit: `docs: mark P2-28 ready for review`

触发最多两轮 Codex 外审并按仓库规则收口。
