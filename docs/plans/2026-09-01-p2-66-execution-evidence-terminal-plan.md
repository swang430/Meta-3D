# P2-66 BaseStation 执行证据不变量与终态语义实施计划

> 执行要求：严格 TDD；每项先在旧实现上看到目标断言失败，再做最小 GREEN。WIP=1，不提前实现
> P2-67/P2-54，不新增仪器命令，不改变正式 provenance 白名单。

**目标**：以本次 execution 自带的 frozen compatibility/qualification 为唯一来源，统一证据解析、
历史、报告、下载、比较和 GUI 的有效测试/诊断/流水线完成语义。

## Task 1：纯 frozen evidence parser 与终态投影

**Files**

- Create: `api-service/app/services/execution_evidence_outcome.py`
- Create: `api-service/tests/test_p2_66_execution_evidence_outcome.py`
- Modify: `api-service/app/services/base_station_adapter_profile.py`

1. RED：构造 compatible formal/diagnostic、no-adapter、legacy、incompatible、outer digest 漂移、requirements
   digest 漂移、畸形 qualification，断言四类 compatibility 与四类 completion semantic。
2. RED：已有 freeze 被复用时，outer/compatibility 任一畸形必须在硬件 I/O 前 fail-loud。
3. GREEN：实现不可变 `ExecutionEvidenceOutcome` 与纯 projector；仅读 execution 自身，不查 DB/HAL/current
   manifest。
4. GREEN：freeze 新写和复用都调用同一 parser；旧无 compatibility 行仍走 legacy 边界。
5. 运行 P1-75/P2-45/P2-65 与 Task 1 专项。

## Task 2：执行证据与正式消费者统一 fail-closed

**Files**

- Modify: `api-service/app/services/execution_scpi_evidence.py`
- Modify: `api-service/app/services/mimo_ota/executors/analysis.py`
- Modify: `api-service/app/services/mimo_ota/executors/report.py`
- Modify: `api-service/app/services/report_data_collector.py`
- Modify: `api-service/app/services/report_service.py`
- Modify/Create: P2-66 证据/报告/比较专项测试

1. RED：一条带有限诊断数值的 invalid compatibility execution，覆盖公开 SCPI evidence、ANALYSIS、REPORT、
   ReportDataCollector、重建和比较；正式数值/统计/判词必须为空或 UNKNOWN，不能进入 pass rate。
2. RED：diagnostic audit report 保留可审计内容但 title/outcome 明示 diagnostic；invalid 明示 evidence invalid；
   valid formal 仍受既有全部独立 trust 门，不因 compatibility 绿直接判绿。
3. GREEN：所有消费者调用共同 projector；不得继续只读 `execution_is_diagnostic()` 漏掉 invalid。
4. GREEN：report content 持久化 server-owned outcome；详情/下载对账关联 execution，stored projection 漂移
   fail-closed。
5. 验证历史无 snapshot 的 provenance backcompat 变异不受影响。

## Task 3：历史、详情、报告列表/下载与比较 API

**Files**

- Modify: `api-service/app/schemas/test_plan.py`
- Modify: `api-service/app/api/test_execution.py`
- Modify: `api-service/app/api/test_plan.py`
- Modify: `api-service/app/schemas/report.py`
- Modify: `api-service/app/api/report.py`
- Modify/Create: P2-66 API 专项测试

1. RED：历史与详情返回同一 `execution_evidence_outcome`；raw `status=completed` 不再是唯一展示结论。
2. RED：报告 summary/detail/download 对 diagnostic/invalid 使用审计分类；stored outcome 缺失/漂移时，显式新
   execution 409 或返回受控不可正式状态，不读取当前 manifest 修复。
3. RED：比较创建/分析对 invalid/diagnostic 不发布 formal difference；legacy 继续原有 provenance 规则。
4. GREEN：所有 API 只序列化共同 Pydantic 模型，不复制状态矩阵。

## Task 4：GUI 完成语义与 OpenAPI 四镜像

**Files**

- Modify: `gui/src/features/TestManagement/components/HistoryTab/HistoryTab.tsx`
- Modify: `gui/src/features/Reports/components/ExecutionSelector.tsx`
- Modify: `gui/src/features/Reports/components/ReportList.tsx`
- Modify: `gui/src/components/Report/ReportViewer.tsx`
- Modify: `gui/src/api/testPlanService.ts`
- Modify: `gui/src/features/TestManagement/types/index.ts`
- Modify: `gui/src/types/api.ts`
- Modify: `api/openapi.yaml`
- Modify: `gui/src/types/api.generated.ts`
- Modify/Create: P2-66 GUI/OpenAPI contract tests

1. RED：历史计数和行徽标将 valid test、diagnostic、pipeline-only 分开；只有 valid test completion 是绿色。
2. RED：报告选择/列表/Viewer 对 diagnostic 与 invalid 明示审计语义，不显示正式成功或可比假象。
3. GREEN：GUI 只消费服务端 completion semantic/reasons，不重算 compatibility/qualification。
4. GREEN：同步 live OpenAPI、checked YAML、generated TS 和手写类型；运行 production build。

## Task 5：生产路径门与 roadmap 镜像

**Files**

- Modify: `api-service/tests/test_rule_gates.py`
- Modify: `docs/roadmap-first-call.md`
- Modify: `docs/plans/2026-08-30-base-station-testcase-compatibility-roadmap-design.md`

1. RED：永久门枚举证据、报告、历史和比较生产消费者，禁止它们绕过共同 projector；GUI 禁止根据 raw
   `completed` 将 diagnostic/invalid 画绿。
2. GREEN：只加最小门；测试类发现严重度上限 P2。
3. 更新活文档：P2-65 已由 PR #434 合并、P2-66 本地实现状态、下一项 P2-67；现场 blocker 不变。

## Task 6：验证、fresh 内审与外审闭环

1. 运行 P2-66/P1-75/P2-65/P2-45/SCPI evidence/report/history/compare/rule-gates focused tests。
2. 运行全后端、GUI contract tests、production build、compileall、单一 Alembic head、
   `git diff --check main...HEAD`。
3. 对 outer digest 与 raw `completed` 两个核心故障做最小变异，确认新测试会红。
4. 按 `.claude/agents/pre-commit-reviewer.md` 做 fresh 独立功能内审；功能 P1 严格 RED→GREEN 后复审。
5. 推送 Ready PR，触发 Codex R1；处理本片功能 P1 与本片内 P2 后触发 R2。
6. 覆盖最新 HEAD 的 R2 无 P1且 mergeable/checks 通过或无必需 checks 时 merge commit；若仍有 P1，
   继续最小修复与 P1-only 外审直到最新 HEAD 无 P1。
7. fetch 验证 `origin/main`，主目录 ff-only 同步并保留未跟踪仪器资料，清理 worktree/本地分支后才
   开始 P2-67。
