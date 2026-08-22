# P1-60 Execution Truth Alignment Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 让 MIMO OTA 执行中的探头/端口补偿、信道场景、频率诊断和人读时间全部来自各自权威真值，并对不完整或未知 provenance fail-closed。

**Architecture:** 在 MEASURE 装配边界分离 pattern index 与 topology probe ID；校准消费采用完整集合白名单；ChannelAsset resolver 显式携带 scenario；人读时间集中到独立 helper。数据库物理时间与既有正式 KPI provenance 门不变。

**Tech Stack:** FastAPI, SQLAlchemy, Alembic, Pydantic, pytest, React/TypeScript contract gates.

---

### Task 1: 锁定手工执行的五组 RED 契约

**Files:**
- Create: `api-service/tests/test_p1_60_execution_truth_alignment.py`

**Step 1:** 写会失败的测试，覆盖 `1..16 → 1..32` 端口、四方位 `1/5/9/13`、逐链部分覆盖拒绝、UMa scenario 透传、F64 缺中心回读诊断、UTC→本地人读 token。

**Step 2:** 运行：
`api-service/.venv/bin/pytest -q api-service/tests/test_p1_60_execution_truth_alignment.py`

Expected: 至少六条断言在当前实现上失败，分别复现导出日志中的五类矛盾。

**Step 3:** 提交仅测试 RED 证据。

### Task 2: 修正物理探头、端口与逐 RF-chain 完整性

**Files:**
- Modify: `api-service/app/services/probe_pattern/consumer.py`
- Modify: `api-service/app/services/channel_engine_client.py`
- Modify: `api-service/app/services/mimo_ota/executors/measure.py`
- Test: `api-service/tests/test_p1_60_execution_truth_alignment.py`

**Step 1:** 增加显式 `select_active_rf_chain_probe_id()`，返回零基角位置对应的 `1..N` topology ID；保留 ProbePattern 既有索引契约。

**Step 2:** `_query_calibration_entries()` 只接受完整零基 legacy 或完整一基 topology probe key，并用明确 base 构造 `1..num_ports`。

**Step 3:** MEASURE 分开保存 pattern probe 与 RF-chain probe；非空逐链图缺任一请求方位时，在进入 positioner/sample loop 前返回 FAILED。

**Step 4:** 运行 RED 文件与 `test_rf_chain_resolver.py`、`test_calibration_chamber_scoping.py`，Expected: PASS。

**Step 5:** Commit: `fix: align probe and RF-chain numbering truth`

### Task 3: 给 ChannelPhaseCalibration 加 provenance 与全量门

**Files:**
- Create: `api-service/alembic/versions/<revision>_add_channel_phase_provenance.py`
- Modify: `api-service/app/models/probe_calibration.py`
- Modify: `api-service/app/services/phase_calibration_service.py`
- Modify: `api-service/app/services/channel_engine_client.py`
- Modify: `api-service/app/services/mimo_ota/executors/measure.py`
- Test: `api-service/tests/test_p1_60_execution_truth_alignment.py`
- Test: `api-service/tests/test_probe_calibration_service.py`

**Step 1:** RED：真实执行拒绝 `NULL/true`，mock dry-run 拒绝 `NULL/false`；错频、过期、非完整 `1..N` 均不注入。

**Step 2:** 新增 nullable `use_mock`，migration 不回填；mock writer 写 `true` 且生成 `1..N` channel IDs。

**Step 3:** 查询同时过滤 chamber/frequency/validity/provenance，并要求补偿 key 精确等于 payload 端口集合。

**Step 4:** 运行定点测试与 Alembic 单 head/migration upgrade-downgrade smoke，Expected: PASS。

**Step 5:** Commit: `fix: gate phase compensation by provenance and frequency`

### Task 4: 对齐 ChannelAsset scenario 与频率诊断

**Files:**
- Modify: `api-service/app/services/mimo_ota/channel_asset_resolver.py`
- Modify: `api-service/app/services/mimo_ota/executors/measure.py`
- Modify: `api-service/app/services/channel_generation/gcm_strategy.py`
- Test: `api-service/tests/test_channel_asset_resolver.py`
- Test: `api-service/tests/test_p1_60_execution_truth_alignment.py`

**Step 1:** RED：vendor asset `scenario=UMa` 不得落成 UMi；无场景不得默认 UMi；资产 BW40 + 无 F64 center 的 warning 必须指向 center readback。

**Step 2:** resolver 显式返回 scenario；MEASURE 写入 `cdl_model_data`；GCM fallback 用现有 CDL parser，解析失败 fail-loud；OOP 名称去重。

**Step 3:** 抽出基于 `f64_center_mhz/scd_freq_identity` 的诊断文案函数，保持 `fully_verified` 判据不变。

**Step 4:** 运行定点、channel asset、frequency consistency 与 GCM/OOP 测试，Expected: PASS。

**Step 5:** Commit: `fix: preserve channel scenario and frequency diagnostics`

### Task 5: 统一人读时间，不改 UTC 存储

**Files:**
- Create: `api-service/app/utils/human_time.py`
- Modify: `api-service/app/services/test_case_runner.py`
- Modify: `api-service/app/services/mimo_ota/executors/report.py`
- Modify: `api-service/app/api/commissioning.py`
- Modify: `gui/src/utils/datetime.ts`
- Test: `api-service/tests/test_p1_60_execution_truth_alignment.py`
- Test: `api-service/tests/test_p1_34_log_timeline.py`

**Step 1:** RED：同一 UTC 时刻在显式 `UTC+8` 本地时区格式化为 `20260822-103723`；三个生产调用点不再直接 `utcnow().strftime`。

**Step 2:** 实现可注入时区的纯 helper，生产默认使用 `astimezone()`；替换三类人读名称，保留 DB/API UTC。

**Step 3:** 更新 GUI 注释中“差一个时区是预期”的陈旧镜像。

**Step 4:** 运行定点与日志时间线测试，Expected: PASS。

**Step 5:** Commit: `fix: align human execution timestamps with local logs`

### Task 6: 全集回归、roadmap、内审与 PR

**Files:**
- Modify: `docs/roadmap-first-call.md`
- Modify: 本设计与计划中的最终验证统计

**Step 1:** 更新 Current Focus、P1-60 条目、手工日志 Discovered/Resolved 与验证统计。

**Step 2:** 运行相关测试、完整 rule gates、全后端、GUI production build、`compileall`、单一 Alembic head、`git diff --check`。

**Step 3:** 按 `AGENTS.md` 做 fresh 内审；P1>0 则按 TDD 修复并复审，直到 P1=0。

**Step 4:** 开 Ready PR，触发 Codex R1；处理本片意见后触发 R2；R2 或后续若有 P1，继续修复和 P1-only 复审直到覆盖最新 HEAD 无 P1。

**Step 5:** 无 P1 后 merge commit，fetch 验证 `origin/main`，主目录 `main` fast-forward，删除自动化与 worktree。

