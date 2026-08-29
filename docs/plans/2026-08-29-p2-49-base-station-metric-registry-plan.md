# P2-49 BaseStation Metric Registry 实施计划

> 按 `executing-plans` 逐 Task 执行；每个 Task 先 RED，再做最小 GREEN，不跨到 P2-50。

**Goal:** 建立 profile-scoped、execution-frozen 的逐指标 registry，让 CMW500/UXM/Mock 以共同 observation
保留真实能力与单位，同时阻止 raw、simulated、unknown 或缺 closed-window 的值进入正式 KPI。

**Architecture:** 扩展现有 `BaseStationMetricCapability`；loaded driver 零 I/O 解析 registry；Remote acquire 后
冻结 snapshot/digest；窗口返回 registry-bound observation；writer、evaluator 与全部消费者从 registry 驱动
generic metric map，并仅保留两项兼容镜像。历史缺版本继续旧合同，新版本显式畸形 fail-closed。

**Tech Stack:** Python 3.13、frozen dataclasses、Pydantic v2、pytest、React/TypeScript、OpenAPI。

---

## Task 1：共同 registry / observation 合同

**Files:**
- Modify: `api-service/app/hal/base_station_manifest.py`
- Modify: `api-service/app/hal/base_station.py`
- Create: `api-service/tests/test_p2_49_metric_registry_contract.py`

**RED:** unit 支持 ratio；registry 拒绝重复/乱序键、非法 adapter/profile、空 source 与 digest 漂移；observation
拒绝未声明键、scope/digest 分叉、非有限值、重复 exchange id，并能显式表示 unknown/simulated；禁止隐式
bool 和从 legacy sentinel 推断成功。

**GREEN:** 增加不可变 `BaseStationMetricRegistry`、`BaseStationMetricObservation` 与 canonical digest；继续复用
唯一 `BaseStationMetricCapability`。

**Commit:** `feat: add base station metric registry contract`

## Task 2：CMW500 / UXM / Mock profile registry

**Files:**
- Modify: `api-service/app/hal/base_station.py`
- Modify: `api-service/app/hal/cmw500_base_station.py`
- Modify: `api-service/app/hal/uxm_base_station.py`
- Modify: `api-service/app/hal/uxm_command_profiles.py`
- Create: `api-service/tests/test_p2_49_adapter_metric_registry.py`
- Modify: P2-46 manifest 与现有 UXM metric tests

**RED:** CMW 两项保持原合同；UXM IRAT/NR profile 逐项按现有 command field 分流；BLER 是 ratio，CQI/RI 是
index，单位未知 UE report 只能 raw/diagnostic；profile drift 与未知 profile fail-loud；解析过程零 connect/SCPI。
Mock shape 可诊断但不正式。

**GREEN:** `resolve_metric_registry()` 默认从 manifest 解析；UXM 仅按当前已加载 command profile 覆写，不新增
命令；CMW 复用静态 manifest；Mock 保留 simulated 边界。

**Commit:** `feat: resolve profile metric registries`

## Task 3：驱动返回共同 metric observations

**Files:**
- Modify: `api-service/app/hal/base_station.py`
- Modify: `api-service/app/hal/cmw500_base_station.py`
- Modify: `api-service/app/hal/uxm_base_station.py`
- Modify: `api-service/app/services/mimo_ota/executors/measure.py`
- Create: `api-service/tests/test_p2_49_metric_observations.py`
- Modify: 既有 CMW/UXM/Mock measurement tests

**RED:** CMW 两项、UXM DL/UL throughput、DL/UL BLER ratio、CQI index、RI index 的真实/缺失/异常/超时/
取消形态；声明但缺失为 null，设备拒绝不从请求、缓存或 sentinel 回填；RI 不再二次解释成层数，raw 值不得
伪工程单位。每个 observation 精确回绑 registry digest/scope/exchange。

**GREEN:** 在保持 legacy fields 兼容的同时生成共同 observations；MEASURE 按冻结 registry 聚合，Mock 全部
simulated/diagnostic。

**Commit:** `refactor: emit registered base station metrics`

## Task 4：冻结 registry 并持久化 generic evidence

**Files:**
- Modify: `api-service/app/services/execution_scpi_evidence.py`
- Modify: `api-service/app/services/mimo_ota/base_station_execution_evidence.py`
- Create: `api-service/tests/test_p2_49_metric_registry_evidence.py`
- Modify: 既有 writer、window trust、attempt lifecycle 与 historical fixture tests

**RED:** initial evidence 在 Remote acquire/identity refresh 后冻结 registry；window 的 registry digest、key、scope、
unit/evidence/source、exchange、attempt/lease/session 任一分叉 fail-closed；新版本缺/畸形 registry 不降级历史；
真正缺版本的历史两项继续可读。

**GREEN:** 写入 `metric_registry_contract_version=1` 与 snapshot；writer 持久化 generic observations，并从 registry
复制元数据；移除新路径的硬编码两指标来源。

**Commit:** `feat: persist registered metric evidence`

## Task 5：generic 投影与全部正式消费者

**Files:**
- Modify: `api-service/app/services/mimo_ota/base_station_execution_evidence.py`
- Modify: `api-service/app/services/mimo_ota/executors/analysis.py`
- Modify: `api-service/app/services/mimo_ota/executors/report.py`
- Modify: 详情、重建、下载、比较、ReportDataCollector、history、commissioning 消费者
- Create: `api-service/tests/test_p2_49_metric_registry_consumers.py`
- Modify: `api-service/tests/test_rule_gates.py`

**RED:** generic map 保留全部声明指标；正式值要求 metric authoritative + P2-48 closed window + P2-45 formal
qualification + identity/attempt/cleanup/release 全门；UXM 当前值因 lifecycle 缺失只诊断；simulated/raw/unknown
不计统计、不出判词；legacy `rank_indicator` 不得绕过；两项兼容镜像只从 generic map 派生。生成/读取/重算/
下载/历史全部一致。

**GREEN:** registry-driven evaluator/projection；保留现有两项兼容 response，不按 adapter/vendor 分支。

**Commit:** `refactor: project registered base station metrics`

## Task 6：API / GUI 镜像

**Files:**
- Modify: live OpenAPI models/routes as required
- Modify: `api/openapi.yaml`
- Modify: `gui/src/types/api.generated.ts`
- Modify: relevant handwritten GUI types/components
- Create/Modify: backend OpenAPI and GUI contract tests

**RED:** manifest/registry/projection 的 key、direction、unit（含 ratio）、scope、source、evidence 与 formal/diagnostic
值四镜像一致；GUI generic 展示新增 UXM 指标，unknown/N/A 与 diagnostic 清晰，不能把 ratio 加 `%` 或 raw 加
工程单位；现有 DL 两项兼容显示不回归。

**GREEN:** 最小同步 API/GUI；不新增 adapter 特定条件分支。

**Commit:** `feat: expose registered base station metrics`

## Task 7：生产路径门、roadmap 与完整验证

**Files:**
- Modify: `api-service/tests/test_rule_gates.py`
- Modify: `docs/roadmap-first-call.md`
- Modify: 本设计/计划（只同步实施结果与验证统计）

**RED/GREEN:** 生产 writer/evaluator 不再用固定新指标名单或 adapter 分支；新 execution 不从 `kpi_valid`、
sentinel、当前 manifest/profile 回填冻结 registry。测试门发现严重度上限 P2。

**Focused:** P2-43/46/47/48/49、CMW/UXM/Mock metrics、writer、window/attempt trust、P2-45 formal consumers、
report/provenance、rule gates。

**Full:** 全后端；适用 GUI contracts 与 production build；live/checked-in/generated/handwritten API mirror；
compileall；单一 Alembic head；base-to-HEAD diff-check。

**Fresh review:** 按 AGENTS.md 0.5 再列全集，缺陷与建议分栏；功能 P1=0 后提交、推送、Ready PR，执行
Codex R1→R2。覆盖最新 HEAD 的 R2 无 P1 才 merge commit；R2 若仍有 P1，最小修复并继续 P1-only
复审。合并后同步本地 main、保留未跟踪仪器资料、清理 worktree/分支，再开始 P2-50。

**Commit:** `test: close base station metric registry`

## 执行结果（2026-08-29）

Task 1～7 已按 RED→最小 GREEN 顺序完成。Codex R1 的报告 generic metric 开放映射 P1 也已通过
RED→最小 GREEN 收口：服务端 attestation 绑定冻结 evidence/registry/projection，客户端自证、增删指标
或改值均 fail-closed，旧 evidence 仅保留固定两项兼容指标。修后全后端 5371 passed / 5 skipped、
适用 GUI 契约与 production build、compileall、单一 Alembic head `e6a8c0d2f4b6` 与 base-to-HEAD
diff-check 通过；fresh 尾审 P1/P2/P3=0，进入覆盖最新 HEAD 的 Codex R2。
