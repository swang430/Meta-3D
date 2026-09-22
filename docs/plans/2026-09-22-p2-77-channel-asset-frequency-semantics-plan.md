# P2-77 Channel Asset Frequency Semantics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让可受控调频的 vendor `.smu` 资产以工程中心频率作为默认值，并以 F64 每组运行时限值和写后回读证明本次 TestCase 频率实际生效。

**Architecture:** 在 ChannelEmulator manifest/execution plan 中新增 `set_center_frequency_bounded` 能力；F64 通过统一的不可变应用证据实现“限值查询、全组预检、写入、错误门、全组回读”。MEASURE 根据冻结能力区分 vendor asset 的 project-default 与固定身份语义，其他来源和历史冻结件维持 fail-closed。

**Tech Stack:** Python 3.11、FastAPI、Pydantic v2、SQLAlchemy、pytest、React 18、TypeScript、Mantine、OpenAPI。

**Spec:** `docs/plans/2026-09-22-p2-77-channel-asset-frequency-semantics-design.md`

## Global Constraints

- 全程严格 TDD：每个生产行为先看见目标测试因旧实现失败，再写最小实现。
- 不新增或猜测 SCPI；新查询仅使用 PROPSIM User Reference Rev 10.2 §20.4.6.8 的 `CALCulate:FILTer:CENTer:LIMits?`。
- 不改变正式 provenance 白名单，不让 Mock/unknown 数据进入正式 KPI。
- 历史 manifest、execution plan 与 execution evidence 不按新 schema 回填或重解释。
- `api-service/.venv` 与 `gui/node_modules` 是未跟踪依赖链接，不得提交。

---

### Task 1: 冻结有界调频能力与共同证据契约

**Files:**
- Modify: `api-service/app/hal/channel_emulator_manifest.py`
- Modify: `api-service/app/hal/channel_emulator_execution_plan.py`
- Modify: `api-service/app/hal/channel_emulator.py`
- Modify: `api-service/app/hal/propsim_f64.py`
- Modify: `api-service/app/services/channel_emulator_execution_plan.py`
- Test: `api-service/tests/test_p2_57_channel_emulator_manifest.py`
- Test: `api-service/tests/test_p2_59_channel_emulator_execution_plan.py`
- Test: `api-service/tests/test_p2_77_channel_asset_frequency_semantics.py`

**Interfaces:**
- Produces: `ChannelEmulatorDriver.set_center_frequency_bounded(center_frequency_mhz: float) -> CenterFrequencyApplicationEvidence`。
- Produces: `ChannelEmulatorDriver.get_center_frequency_application_evidence() -> CenterFrequencyApplicationEvidence | None`。
- Produces: manifest v4 与 execution-plan v3 中的 `set_center_frequency_bounded` 操作。
- Produces: `CenterFrequencyRange`, `CenterFrequencyGroupApplication`, `CenterFrequencyApplicationEvidence` 不可变模型。

- [ ] **Step 1: 写 manifest/plan 历史兼容 RED**

  新测试构造 v3 manifest，断言其仍只接受旧词汇；构造 F64 v4 manifest，断言新操作进入 plan v3；旧 plan v2 调 `planned("set_center_frequency_bounded")` 必须显式拒绝并提示重建，而不是默认为支持。

- [ ] **Step 2: 运行 RED**

  Run: `cd api-service && .venv/bin/python -m pytest tests/test_p2_57_channel_emulator_manifest.py tests/test_p2_59_channel_emulator_execution_plan.py -q`

  Expected: FAIL，因为 manifest v4、plan v3 和新操作尚不存在。

- [ ] **Step 3: 最小实现版本化词汇**

  固定 `CHANNEL_EMULATOR_MANIFEST_V3_OPERATIONS`，新增 v4 词汇；固定 plan v2 词汇，新增 plan v3。`resolve_channel_emulator_execution_plan()` 只把 manifest v4 映射到 plan v3。F64 升 v4 并声明 implemented；FS16 与 Mock 保持 v3，不获得新能力。

- [ ] **Step 4: 写共同证据模型 RED**

  测试要求范围上下界有限且 `lower <= upper`、组号/代表通道为正整数、组唯一、confirmed 证据必须具有非空组且每组 applied 等于 requested；畸形 payload fail-closed。

- [ ] **Step 5: 运行 RED 并实现最小模型/基类接口**

  Run: `cd api-service && .venv/bin/python -m pytest tests/test_p2_77_channel_asset_frequency_semantics.py -q`

  Expected before implementation: import/validation failure。实现 Pydantic frozen models；基类 setter 抛 `NotImplementedError`，getter 默认返回 `None`。

- [ ] **Step 6: 跑 Task 1 GREEN 并提交**

  Run: `cd api-service && .venv/bin/python -m pytest tests/test_p2_57_channel_emulator_manifest.py tests/test_p2_59_channel_emulator_execution_plan.py tests/test_p2_77_channel_asset_frequency_semantics.py tests/test_rule_gates.py -q`

  Commit: `feat(p2-77): freeze bounded center frequency capability`

### Task 2: F64 逐组限值预检与写后回读

**Files:**
- Modify: `api-service/app/hal/propsim_f64.py`
- Modify: `api-service/app/data/scpi_evidence/p0_5_commands.json`
- Test: `api-service/tests/test_p2_77_channel_asset_frequency_semantics.py`
- Test: `api-service/tests/test_f64_center_freq_dispatch.py`
- Test: `api-service/tests/test_f64_topology_readback_f64r2.py`

**Interfaces:**
- Consumes: Task 1 的 `CenterFrequencyApplicationEvidence`。
- Produces: F64 `set_center_frequency_bounded()` 和 `get_center_frequency_application_evidence()`。
- Produces: `_parse_center_frequency_limits(response: str) -> tuple[CenterFrequencyRange, ...]` 纯解析器。

- [ ] **Step 1: 写限值解析 RED**

  覆盖 `350,6000`、`350,900;1800,6000`、空回复、非数值、NaN/Inf、反向区间、空分段。合法响应保持手册顺序；非法响应抛受控 `ValueError`。

- [ ] **Step 2: 运行 RED 后实现纯解析器**

  Run: `cd api-service && .venv/bin/python -m pytest tests/test_p2_77_channel_asset_frequency_semantics.py -k limits -q`

  Expected before implementation: parser missing。实现只解析手册形态，不添加隐式系统范围。

- [ ] **Step 3: 写“全组预检后才允许首个写入”RED**

  用真实驱动 fake transport 构造两组：一组允许、一组越界；断言零条 `CALC:FILT:CENT:CH <...>` 写命令、返回 unconfirmed evidence、programmed 仍 false。再覆盖任一组限值空/畸形同样零写入。

- [ ] **Step 4: 写“写后逐组回读”RED**

  覆盖：全部回读等于请求成功；某组被钳位；某组空回复；写后错误队列非空。后三者均失败且缓存不得声明请求值已生效。

- [ ] **Step 5: 实现原子有界调频**

  在同一 `_scpi_lock` 内读取当前 `_group_repr_channels`，逐组执行手册 §20.4.6.8 查询并完成全量预检；再复用 `_gated_write_transaction` 写入；随后按 §20.4.6.2 逐组回读。仅 confirmed 后更新 `_center_freq_mhz`、`_center_freq_programmed` 和 last evidence。

- [ ] **Step 6: 让 GCM 加载调用共同 setter**

  `set_channel_model()` 在加载/拓扑回读后调用 `set_center_frequency_bounded()`，不再保留第二份 CENT 写逻辑。缺省频率仍零 CENT I/O，并清除上次 application evidence。

- [ ] **Step 7: 登记命令来源并跑 GREEN**

  `p0_5_commands.json` 为 `CENT:LIM?` 增加紧邻手册 §20.4.6.8/page 282 来源；保留既有 `CENT` 与 `CENT?` 来源。运行：

  `cd api-service && .venv/bin/python -m pytest tests/test_p2_77_channel_asset_frequency_semantics.py tests/test_f64_center_freq_dispatch.py tests/test_f64_topology_readback_f64r2.py tests/test_rule_gates.py -q`

  Commit: `feat(p2-77): verify F64 center frequency per channel group`

### Task 3: 分离 vendor 工程默认频率与本次执行频率

**Files:**
- Modify: `api-service/app/services/mimo_ota/channel_asset_resolver.py`
- Modify: `api-service/app/services/mimo_ota/executors/measure.py`
- Modify: `api-service/app/services/mimo_ota/frequency_consistency.py`（仅在现有类型不足时扩展来源表达，不改变判决算法）
- Test: `api-service/tests/test_channel_asset_resolver.py`
- Test: `api-service/tests/test_mimo_ota_precheck_cal_gate.py`
- Test: `api-service/tests/test_p2_77_channel_asset_frequency_semantics.py`

**Interfaces:**
- Consumes: frozen plan 的 `planned("set_center_frequency_bounded")`。
- Consumes: driver 的 `get_center_frequency_application_evidence()`。
- Produces: `ResolvedChannelAsset.project_default_frequency_identity` 与 `declared_bandwidth_mhz`，替代 vendor 路径上含混的排他 `scd_freq_identity`。
- Produces: frequency-consistency evidence schema v3，含 project default、requested、ranges、per-group applied 与 confirmation。

- [ ] **Step 1: 写合法跨频 vendor asset RED**

  构造工程默认 2565 MHz、TestCase 1960 MHz、F64 frozen plan 有 bounded capability、应用证据全部 confirmed；断言执行不会再产生 `SCD` 中心频率 mismatch，CE 实际回读与 TestCase 匹配且保留 project default 审计字段。

- [ ] **Step 2: 写保守矩阵 RED**

  覆盖：同一资产但旧 plan/FS16/Mock 无 bounded capability 仍按固定身份拒绝；standard/custom/rt 资产仍保持原频率门；bounded plan 缺证据、unconfirmed、requested 漂移或组回读漂移均 fail-closed。

- [ ] **Step 3: 运行 RED**

  Run: `cd api-service && .venv/bin/python -m pytest tests/test_channel_asset_resolver.py tests/test_p2_77_channel_asset_frequency_semantics.py tests/test_mimo_ota_precheck_cal_gate.py -k 'frequency or vendor' -q`

- [ ] **Step 4: 最小实现 resolver 与 MEASURE 判据换源**

  vendor resolver 同时提供 project default 与带宽；MEASURE 仅在 frozen bounded capability + confirmed evidence 同时成立时，不把 project default 加为排他 peer。CE 身份由实际中心回读与资产带宽组成；其他路径保持原逻辑。

- [ ] **Step 5: 跑受影响链并提交**

  Run: `cd api-service && .venv/bin/python -m pytest tests/test_channel_asset_resolver.py tests/test_frequency_consistency.py tests/test_mimo_ota_precheck_cal_gate.py tests/test_p2_61_channel_emulator_certification.py tests/test_p2_62_channel_emulator_adapter_certification.py tests/test_p2_66_execution_evidence_outcome.py tests/test_rule_gates.py -q`

  Commit: `fix(p2-77): separate project default from execution frequency`

### Task 4: API、OpenAPI 与 GUI 语义镜像

**Files:**
- Modify: `api-service/app/api/channel_asset.py`
- Modify: `api/openapi.yaml`
- Modify: `gui/src/types/api.generated.ts`（由既有生成命令生成）
- Modify: `gui/src/api/channelAssetService.ts`
- Modify: `gui/src/features/ChannelWorkbench/ChannelWorkbench.tsx`
- Modify: `gui/src/features/ChannelWorkbench/ChannelAssetForm.tsx`
- Modify: `gui/src/components/TestCaseConfig/MIMOOTAConfigForm.tsx`
- Test: `api-service/tests/test_p2_77_channel_asset_frequency_semantics.py`
- Test: `gui/src/features/ChannelWorkbench/ChannelWorkbench.test.tsx`（若现有测试载体名称不同，使用同目录既有契约测试文件）
- Test: `gui/src/components/TestCaseConfig/MIMOOTAConfigForm.test.tsx`（若现有测试载体名称不同，使用同目录既有契约测试文件）

**Interfaces:**
- Produces: `center_frequency_hz` 的 OpenAPI 描述：“vendor_file=工程默认；其他来源=物理身份”。
- Produces: vendor asset 的服务器字段不变，客户端仅按服务器 `source_type` 改标签，不计算允许范围。

- [ ] **Step 1: 写四镜像与 GUI 文案 RED**

  后端契约断言 live schema 与 checked YAML 描述一致；GUI 测试断言 vendor 显示“工程默认中心频率”，选择提示明确“由冻结 adapter 能力 + 仪表运行时范围裁决”，非 vendor 仍显示中心频率。

- [ ] **Step 2: 运行 RED**

  Run: `cd api-service && .venv/bin/python -m pytest tests/test_p2_77_channel_asset_frequency_semantics.py -k openapi -q`

  Run: `cd gui && npm test -- --runInBand ChannelWorkbench MIMOOTAConfigForm`

- [ ] **Step 3: 最小实现并重新生成 TS**

  只改描述与显示，不加入客户端范围计算或 adapter 白名单。使用仓库既有 OpenAPI 生成脚本更新 `api.generated.ts`。

- [ ] **Step 4: 跑 GREEN 并提交**

  Run: `cd api-service && .venv/bin/python -m pytest tests/test_p2_77_channel_asset_frequency_semantics.py tests/test_p2_44_openapi_contract.py -q`

  Run: `cd gui && npm test -- --runInBand ChannelWorkbench MIMOOTAConfigForm && npm run build`

  Commit: `feat(p2-77): explain channel asset frequency roles`

### Task 5: 路线图、完整验证与交付

**Files:**
- Modify: `docs/roadmap-first-call.md`
- Verify: base-to-HEAD diff and all affected production paths

**Interfaces:**
- Consumes: Tasks 1–4 的完整结果。
- Produces: P2-77 软件半完成记录和明确现场复验项。

- [ ] **Step 1: 更新路线图**

  记录手册章节、软件实现边界和 Hardware Blocker：在同一真实 F8800A 上验证一个工程的两个合法频点、一个越界频点、多区间回复（若该工程具备）以及全部组回读。不得把本地 fake transport 记作现场关闭。

- [ ] **Step 2: 运行 focused 与规则门**

  Run: `cd api-service && .venv/bin/python -m pytest tests/test_p2_77_channel_asset_frequency_semantics.py tests/test_f64_center_freq_dispatch.py tests/test_f64_topology_readback_f64r2.py tests/test_channel_asset_resolver.py tests/test_frequency_consistency.py tests/test_mimo_ota_precheck_cal_gate.py tests/test_p2_57_channel_emulator_manifest.py tests/test_p2_59_channel_emulator_execution_plan.py tests/test_p2_61_channel_emulator_certification.py tests/test_p2_62_channel_emulator_adapter_certification.py tests/test_p2_66_execution_evidence_outcome.py tests/test_rule_gates.py -q`

- [ ] **Step 3: 运行全量验证**

  Run: `cd api-service && .venv/bin/python -m pytest -q`

  Run: `cd api-service && .venv/bin/python -m compileall -q app tests`

  Run: `cd api-service && .venv/bin/alembic heads`

  Run: `cd gui && npm test -- --runInBand && npm run build`

- [ ] **Step 4: 自审全集与变异检查**

  全仓搜索 `set_center_frequency_bounded`、`scd_freq_identity`、`center_frequency_hz`、`CENTer:LIMits`，逐个核对产生方/消费方；临时把“任一组越界即拒绝”和“写后回读不一致即拒绝”各反转一次，确认核心测试失败，再恢复并重跑。

- [ ] **Step 5: 检查 diff 并提交最终文档**

  Run: `git diff --check && git status --short && git diff --stat 8068421a...HEAD`

  Commit: `docs(p2-77): record bounded channel frequency semantics`

- [ ] **Step 6: Ready PR 与外审**

  推送分支并创建 Ready PR。R1 处理本片功能 P1 与本片内 P2；修复后触发覆盖最新 HEAD 的 R2。R2 无 P1 且 mergeable/checks 通过即合并；R2 仍有 P1 时只修 P1 并续审至最新 HEAD 无 P1。R2+ P2/P3 仅报告，不阻塞、不自动积压。
