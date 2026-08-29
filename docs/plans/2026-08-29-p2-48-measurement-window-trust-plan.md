# P2-48 Measurement Window Trust Contract 实施计划

> 按 `executing-plans` 逐 Task 执行；每个 Task 先 RED，再做最小 GREEN，不跨到 P2-49。

**Goal:** 用 execution-frozen request 与结构化 trust receipt 统一窗口 scope、cardinality、生命周期和
attempt/session/cleanup/release 信任，保留 UXM 诊断能力但不升级正式 KPI。

**Architecture:** manifest 产生共同 request；驱动只映射既有仪器事实；MEASURE 校验完整批次；writer
持久化同一 request/receipt；正式消费者按显式版本边界读取，新合同 fail-closed、历史缺字段保持兼容。

**Tech Stack:** Python 3.13、frozen dataclasses、Pydantic v2、pytest、现有 SCPI evidence capture。

---

## Task 1：共同 window request / trust receipt

**Files:**
- Modify: `api-service/app/hal/base_station.py`
- Create: `api-service/tests/test_p2_48_measurement_window_receipts.py`

**RED:** request 拒绝非法 scope、count、cardinality、index 与 digest；trust 拒绝 shape/digest 分叉、重复/空
exchange id、clear-read-only 伪 closed、unavailable 伪确认；禁止隐式 bool。确认
authoritative-closed、clear-read-only、unavailable、simulated 四种完整状态。

**GREEN:** 增加不可变 request、stage truth 与 trust receipt；formal/diagnostic 资格只由共同合同派生。

**Commit:** `feat: add measurement window trust receipts`

## Task 2：从冻结 manifest 生成唯一窗口计划

**Files:**
- Modify: `api-service/app/hal/base_station_manifest.py`
- Modify: `api-service/app/hal/uxm_base_station.py`
- Modify: `api-service/app/services/mimo_ota/executors/measure.py`
- Create: `api-service/tests/test_p2_48_measurement_window_plan.py`
- Modify: P2-46 manifest 合同测试

**RED:** CMW500 single、UXM requested、PCell/all-cells、显式 CMW Mock、diagnostic_unbound；冻结 manifest
与 loaded driver drift、非法 count/scope、回执 request digest 分叉、少窗/多窗/重复序号全部 fail-loud，且
零厂商分支。真实 manifest 缺窗口声明不得从 class var 补正式资格。

**GREEN:** common executor 从 frozen manifest 创建 request；调用次数、scope、cardinality 与序号均由 request
控制。UXM 只声明公共、非正式 lifecycle，不扩展指标 registry。

**Commit:** `refactor: freeze base station window requests`

## Task 3：CMW500 / UXM / Mock 映射现有窗口事实

**Files:**
- Modify: `api-service/app/hal/cmw500_base_station.py`
- Modify: `api-service/app/hal/uxm_base_station.py`
- Modify: `api-service/app/hal/base_station.py`
- Create: `api-service/tests/test_p2_48_adapter_window_truth.py`
- Modify: 既有 CMW/UXM/Mock 窗口测试

**RED:** CMW 完整 OFF/RUN/RDY/OFF 才正式；任一拒绝/错误/超时/取消不得确认。UXM 缺 closed 保持
unconfirmed，只可诊断；Mock 始终 simulated/diagnostic。所有回执精确回绑 request，禁止使用旧
`unconfirmed_window_allows_diagnostic_execution()`。

**GREEN:** 仅把已有命令与回读映射为共同 trust，不新增或更改 SCPI。

**Commit:** `refactor: map adapter windows to common trust`

## Task 4：持久化 request/receipt 并验证 attempt 生命周期

**Files:**
- Modify: `api-service/app/services/execution_scpi_evidence.py`
- Modify: `api-service/app/services/mimo_ota/base_station_execution_evidence.py`
- Modify: `api-service/app/services/mimo_ota/executors/measure.py`
- Create: `api-service/tests/test_p2_48_measurement_window_evidence.py`
- Modify: 既有 writer、attempt、metric trust fixture/tests

**RED:** 新 evidence 必须带 contract version；每方位窗口数/序号、scope、request digest、阶段、attempt、
lease、session、cleanup/release 任一分叉均 fail-closed。显式畸形不能降级历史读取；真正缺版本的历史
fixture 保持旧合同。

**GREEN:** writer 持久化共同 request/trust；formal envelope presence-aware 校验完整批次。诊断值可审计，
但无 closed 边界时 formal value 仍为 null/UNKNOWN。

**Commit:** `feat: persist measurement window trust evidence`

## Task 5：生产入口与消费者门

**Files:**
- Modify: `api-service/tests/test_rule_gates.py`
- Create: `api-service/tests/test_p2_48_measurement_window_production_paths.py`
- Modify: 必要的生产消费者与合同测试

**RED/GREEN:** 生产 MEASURE 不再消费 `measurement_window_count()`、`window.confirmed` 或
`unconfirmed_window_allows_diagnostic_execution()`；正式消费者不按 adapter 名称选择新窗口信任；
生成/读取/重算/下载/历史路径全部经同一 formal envelope。测试门发现严重度上限 P2。

**Commit:** `test: gate measurement window trust consumers`

## Task 6：文档镜像与完整验证

**Files:**
- Modify: `docs/roadmap-first-call.md`
- Modify: 本设计/计划（只同步实施结果与验证统计）

**Focused:** P2-48、CMW/UXM/Mock window、P2-43/46/47、writer、attempt lifecycle、metric trust、
P2-45 formal consumers、rule gates。

**Full:** 全后端；compileall；单一 Alembic head；base-to-HEAD diff-check。若未改 GUI/OpenAPI schema，
明确不运行其契约/build。

**Fresh review:** 按 AGENTS.md 0.5 再列全集，缺陷与建议分栏；功能 P1=0 后提交、推送、Ready PR，执行
Codex R1→R2。覆盖最新 HEAD 的 R2 无 P1才 merge commit；R2 若仍有 P1，最小修复并继续 P1-only
复审。合并后同步本地 main、保留未跟踪仪器资料、清理 worktree/分支，再开始 P2-49。

**Commit:** `test: close measurement window trust contract`
