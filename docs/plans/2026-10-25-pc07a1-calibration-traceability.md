# PC-07A-1 最小实际采用追溯实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: 使用 `subagent-driven-development` 按任务执行（用户已授权）。每任务先 RED 后 GREEN，完成独立规格审查与代码内审后才进入下一任务；最终统一全量和 R1/R2。本文为计划，不是实现或验证完成声明。

**Goal:** 报告可读地追溯同次执行实际采用的新记录/旧证书、频率和原始证据来源；生成、读取、重建、下载保持同源。

**Architecture:** 复用执行冻结及 `measure.path_loss_application`。优先新增共享纯 helper，按冻结逐链主表关联来源快照，供报告生成与既有读取可信门重算；不查询当前配置或当前校准指针补历史。原始证据仅展示已有 run ID/indices 指针及明确未内嵌状态。

**Tech Stack:** 现有 FastAPI、SQLAlchemy、SQLite、pytest、React/Mantine、PDFGenerator 与真实浏览器；不新增框架。

**Spec:** [拓扑内校准设计](../design/2026-10-24-topology-calibration-integration.md)、[roadmap PC07](../roadmap-first-call.md#pc-roadmap)、AGENTS.md Code Review Rules、CLAUDE.md 当前架构。

**已归档任务证据：** [Task 1](2026-10-25-pc07a1-validation-evidence/task-1-report.md)、[Task 2](2026-10-25-pc07a1-validation-evidence/task-2-report.md)。本地 `.superpowers/sdd/` 为忽略的工作草稿，不作为仓库验证报告存放位置；原 scratch 副本仍保留本地。

## 全局约束

- 基线为 PC-06A-1 PR #532 合并 `7292f8ed`，分支 `codex/pc-07a1-calibration-traceability`；实施前核实 HEAD、工作树及共享台账，保留他人修改和未跟踪文件。
- 唯一 WIP 为 PC-07A-1；不整项关闭 PC-05/06/07，不宣称完整不确定度预算、撤销制度、原始审计包或 PC07B 现场认证完成。
- 不增加硬件行为或 SCPI；模拟、缺测、unknown 不进入正式判定；操作员确认采用不等于计量认证。
- 不改采用/执行冻结保存结构，不在读取时补当前配置、当前证书、当前选择或原始采集记录；历史缺项保持 unknown。
- 执行频率与记录覆盖频率分别呈现，不插值、不互相补齐。补偿展示不修改数值，不再次累计线缆/探头增益；整条仍只补偿一次。
- 原始读数来源仅为已冻结 `acquisition_run_id`、`checked_exchange_indices` 等指针；`raw_readings_embedded=false`，明确“原始读数未内嵌”。无指针不能伪装为空数组证明“已留存”。
- 保留默认 bootstrap 行为，不为测试改生产启动策略；相关和全量全部显式临时 SQLite、全 Mock、专属日志/报告目录，不用用户数据库或默认服务。
- 测试报告记录命令、退出码、结尾统计、准确 SHA 和未提交输入。历史测试数量不冒充本片结果。仅主代理安排唯一最终全后端，其他执行者不重复运行。

## 消费入口全集与处理结论

| 生产入口 | 本片动作 |
|---|---|
| `services/calibration/route_calibration.py::confirm_route_application/list_route_applications` | 保留不可变采用事实；不补当前历史值 |
| `services/mimo_ota/route_calibration_freeze.py::freeze_execution_route_compensation/read_execution_route_compensation` | 复用冻结真值，回归旧执行不补真 |
| `services/test_case_runner.py`、`api/commissioning.py` 的创建入口 | 回归三个创建入口，不另加冻结入口 |
| `services/mimo_ota/path_loss_preflight.py`、`services/base_station_execution_session.py` | 保留适用/身份/安全门，不扩大支持模式 |
| `services/channel_engine_client.py::_query_calibration_entries`、`services/mimo_ota/executors/measure.py` | 回归真实应用回执和逐链来源、只补偿一次，不改计算 |
| `services/mimo_ota/path_loss_application.py`、`executors/analysis.py` | 共享应用事实权威源；模拟/unknown 保守判定 |
| `api/test_execution.py::_formal_validation_pass` | 先 RED 复现 v2 与旧镜像差异，再按本片展示一致性裁定是否换源 |
| `executors/report.py::_build_mimo_ota_content_data` | 从关联原执行 measure 生成追溯投影与可读参数 |
| `services/report_service.py::generate_report/report_has_provenance_trust` | 生成覆盖客户端字段，server-owned 剥离；关联原执行重算，不只验证报告内部自洽 |
| `api/report.py` 列表/详情/生成/下载及既有 trust 调用点 | 同源验证新投影；旧无键报告沿原门，不全封禁 |
| `services/pdf_generator.py` | 消费报告展示内容，不读 DB；优先复用已有参数渲染 |
| `gui/src/components/Report/ReportViewer.tsx`、`gui/src/types/report.ts` | 只展示服务端投影，不另查当前配置/采用/原始采集 |

实施新增字段后全仓搜索产生方/消费方，对每处登记修改、回归或无需修改的具体原因；不得用“应该不用”省略对称路径。

## Task 1：共享冻结追溯投影及 v2 展示差异复现

**Files:** 新增 `api-service/app/services/mimo_ota/calibration_traceability.py`；新增 `api-service/tests/test_pc07a1_calibration_traceability.py`；仅复现成立后最小修改 `api-service/app/api/test_execution.py`。

**Interfaces:** `build_calibration_traceability(application: object) -> dict` 为无 DB/无 I/O 的纯函数，内部复用 `parse_path_loss_application`。结果包含 `schema_version=1`、应用状态、冻结执行频率、逐链条目及 `raw_readings_embedded=false`。逐链条目保留原 `chain_id/source_kind/source_id`，明确 `application_state` 为 selected/applied/unknown；具体来源身份、频率、参考面及证据指针只取关联冻结快照已有字段。

- [ ] RED：新增/旧证书/混合来源准确关联。以 `route_entries` 为主表，按 `(source_kind, source_id)` 找 `source_records`，不能遍历来源列表把诊断证书/未采用候选当实际采用。
- [ ] RED：同一 source ID 不同 kind 不能串源；缺失/重复匹配、未知 kind、缺损历史不崩溃、不猜来源。`status` 与 `applied_chain_ids` 共同决定实际应用；仅冻结选择不是已应用，缺损关联保持 unknown。
- [ ] RED：冻结执行频率、记录覆盖、采用 ID/predecessor/run/indices 保持原值；缺字段不补值。明确 raw 未内嵌，不读取 DiagnosticRun。
- [ ] 运行新增用例确认因缺生产能力失败，记录实际 RED；最小实现 helper，运行同命令 GREEN。

首条核心断言形态（使用现有 PC04A2 fixture 生成有效冻结，不手拼绕过验证）：

```python
projection = build_calibration_traceability(application)
assert projection['raw_readings_embedded'] is False
assert [(r['chain_id'], r['source_kind'], r['source_id'], r['application_state'])
        for r in projection['routes']] == expected_routes
```

- [ ] 单独 RED：完整真实 v2 应用、旧 `path_loss_calibration_use_mock` 缺失且其他正式证据满足时，对比 `_formal_validation_pass`、analysis/report 同次执行展示；必须复现实际不一致才修。
- [ ] 若不一致属于本片实际展示，最小换为已有 `path_loss_measurement_is_verified(measure)`，保留所有其他证据门；若未复现则不改并记录原因。不补写旧镜像，不扩大资格。
- [ ] 反例 RED/GREEN：v1 缺来源、v2 simulated/unknown/损坏/not_applied 仍拒绝，诊断执行不变正式。
- [ ] 定点及 `test_pc04a2_route_freeze.py`、`test_pc04a2_route_compensation.py`、`test_p1_62_path_loss_application_truth.py` 回归；任务独立内审后仅提交任务文件。

## Task 2：报告 JSON/PDF 与原执行关联可信门

**Files:** 修改 `api-service/app/services/mimo_ota/executors/report.py`、`api-service/app/services/report_service.py`、`api-service/app/api/report.py`；只有既有参数渲染不能满足时最小修改 `api-service/app/services/pdf_generator.py`。测试新增 `api-service/tests/test_pc07a1_report_traceability.py`。

**Interfaces:** 报告增加 `calibration_traceability`，由 Task 1 helper 对关联原 `execution.measurements.phases.measure.path_loss_application` 重算。PDF参数与 JSON 使用同一投影，显示来源身份/前序关系/频率/参考面/认证unknown/原始指针未内嵌。

- [ ] RED：builder 返回新字段，可读报告区分新采用、旧证书、冻结选择、实际应用和 unknown；新采用“认证资格未知”不被改为认证通过。
- [ ] RED：先冻结旧执行，再推进当前采用/改当前配置，首次生成、重建仍显示原 ID/频率；读取当前来源即令用例失败。
- [ ] RED：客户端 create/update/generate 传伪造 `calibration_traceability` 时，被现有 server-owned 剥离/服务器生成覆盖；不得直接进入报告。
- [ ] RED：攻击者同时改报告内部 application 与追溯投影使两者自洽，但与关联原执行不同；列表/详情/下载等现有可信入口必须拒绝或给出现有安全重建状态。不能只比较报告自身两个字段。
- [ ] 在现有入口获得原 execution，调用共享 helper 重算比较新投影；不让纯 helper 访问 DB，不新造并行可信框架。枚举原 `report_has_provenance_trust` 调用方，补齐需要原执行的关联检查。
- [ ] RED：旧报告没有新键时沿原有 provenance/lifecycle 门，不因缺新字段把所有旧报告禁用；安全重建后生成新投影。损坏/模拟历史不补真。
- [ ] 最小实现并 GREEN；保留既有重建的原执行单一来源及多执行拒绝规则。
- [ ] 生成 PDF 并提取文本，核对身份/频率/unknown/未内嵌声明；检查同次响应 JSON，不把文件存在当验收。
- [ ] 回归 `test_mimo_ota_report_verified_backcompat.py`、`test_p1_48_report_provenance.py`、`test_p1_61_report_final_state_truth.py`；任务独立内审后提交。

## Task 3：GUI 与隔离真实 API/浏览器验收

**Files:** 修改 `gui/src/components/Report/ReportViewer.tsx`、`gui/src/types/report.ts`；新增 `gui/test/pc07a1Report.browser.js`、`api-service/tests/pc07a1_browser_fixture.py`；GUI行为测试按既有目录/运行器落位，不添加测试框架。

**Interfaces:** 页面只消费报告响应 `calibration_traceability`；缺字段显示历史追溯未生成，不调用当前配置/采用历史/采集接口拼值。浏览器 fixture 仅允许临时 DB、全 Mock 和专属输出目录。

- [ ] GUI RED：混合新旧逐链来源可读；selected 不显示 applied；unknown/缺字段不显示认证或附件可用。
- [ ] 最小实现显示并 GREEN；不改原编辑器及采用流程。
- [ ] fixture 启动前验证临时 SQLite 路径、`USE_MOCK_INSTRUMENTS=true` 与无真实驱动；关闭局部种子服务 bootstrap，但不改生产默认值。专属日志/报告目录，禁止外部仪器连接。
- [ ] 启动独立 API/GUI，核真实 HAL 状态为 mock；浏览器走真实列表、生成、详情、重建、下载 API，不拦截响应伪造报告投影。
- [ ] 全 Mock 实际执行保持 simulated/unknown，无正式 PASS 或模拟数值冒充实测。
- [ ] 真实来源历史展示用明确标注的合成历史夹具，不称其为 Mock 获得的真实采用。先冻结旧记录、推进当前选择，再生成/重建；页面、JSON及下载PDF必须保留原来源。
- [ ] 篡改报告 JSON 的关联真值用例通过真实 API核对读取门；旧无键报告沿原访问/重建路径。
- [ ] 保存完整请求响应、HAL状态、截图、PDF与提取文本、临时DB快照、准确输入SHA；不覆盖旧证据。相关 GUI 行为测试与 `npm run build`，记录退出码及既有警告。
- [ ] 任务独立内审后提交任务文件，浏览器截图不是现场仪器认证证据。

## Task 4：最终回归、独立审查及 R1/R2 收口

**Files:** 新增 `docs/plans/2026-10-25-pc07a1-validation.md`；最小同步 `docs/roadmap-first-call.md` 和本计划任务状态。不修改历史归档。

- [ ] 独立内审覆盖累计 diff、Task 1/2 两项关联真值约束和全部消费入口；每个功能发现先 RED 后 GREEN，范围外建议不顺带实现。
- [ ] API目录运行下列相关集（每次采用独立临时DB；报告逐条记录准确SHA、命令和结尾统计）：

```bash
USE_MOCK_INSTRUMENTS=true DATABASE_URL=sqlite:////tmp/pc07a1-related.db BOOTSTRAP_ON_STARTUP=false .venv/bin/python -m pytest tests/test_pc07a1_calibration_traceability.py tests/test_pc07a1_report_traceability.py tests/test_pc04a2_route_freeze.py tests/test_pc04a2_route_compensation.py tests/test_p1_62_path_loss_application_truth.py tests/test_mimo_ota_report_verified_backcompat.py tests/test_p1_48_report_provenance.py tests/test_p1_61_report_final_state_truth.py -q -o log_cli=false
```

- [ ] 相关稳定后主代理安排唯一最终全后端，保留默认 bootstrap 初始化路径；不借旧全量结果宣称新版本通过：

```bash
USE_MOCK_INSTRUMENTS=true DATABASE_URL=sqlite:////tmp/pc07a1-final-full.db BOOTSTRAP_ON_STARTUP=true .venv/bin/python -m pytest -q -o log_cli=false
```

- [ ] 全量后若改生产，明确旧全量输入，补与风险相称的验证；不得把旧结果归到新 HEAD。
- [ ] 独立复核报告 PDF/JSON/页面一致、旧执行不追当前值、模拟unknown不入判定、只补偿一次、raw仅指针未内嵌。报告没有执行的检查如实写未跑。
- [ ] 按授权提交/创建PR，R1覆盖最新输入；核实并修本片可执行意见后 R2。R2无P1立即收口；仍有P1则修复、内审/回归后续审至最新HEAD无P1；R2后P2/P3不自动扩大本片或沉淀积压。
- [ ] 最终交付精确SHA、红绿证据、独立内审、浏览器/PDF/JSON、全后端及外审覆盖版本；roadmap仅关闭PC-07A-1，不关闭完整PC07/预算/撤销制度/PC07B。

## 完成判据

用户能识别本次执行当时实际使用的来源、频率与原始证据指针，并能分辨冻结选择、实际应用、unknown及未内嵌原始读数；所有展示可由原执行重算，不依赖当前配置。该结果不是完整审计包、原始附件、实物停发证明或现场计量认证。
