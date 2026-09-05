# F64 正式执行解除 SMB 运行依赖 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 让已冻结的 F64 vendor-file ChannelAsset 在没有开发机 SMB 挂载时仍进入现有 SCPI 加载与正式证据链，同时把 SMB scan/sync 明确限定为非正式开发工具。

**Architecture:** 启动冻结继续绑定 ChannelAsset 数据库可执行内容；MEASURE 只核对该冻结投影，不再访问 API 主机文件系统。F64 Windows 路径继续由 resolver 交给既有 NativeModelStrategy/PropsimF64Driver，加载是否成立仍由同次执行的 SCPI 状态、错误队列、operation receipt 和 P2-66 outcome 判定。

**Tech Stack:** Python 3.11、FastAPI、Pydantic v2、pytest、React/TypeScript、Node test、GitHub PR/Codex review。

---

### Task 1: 用生产关系测试锁住“运行不依赖 SMB”

**Files:**
- Modify: `api-service/tests/test_p2_59_channel_emulator_execution_plan.py`

**Step 1: 写失败测试**

把现有 `test_vendor_file_freeze_rejects_in_place_project_byte_replacement` 改成运行边界测试：

- 构造带 `smu_project_truth` 的 vendor_file asset 和不存在的 F64 Windows 路径映射；
- 冻结 ChannelAsset；
- monkeypatch `verify_channel_asset_smu_project_bytes` 为一旦调用就失败；
- 不传数据库 session 调用 `validate_resolved_channel_asset_against_freeze`；
- 断言返回冻结 identity，且 SMB verifier 零调用；
- 修改数据库资产 payload 后，仍断言首个远程 I/O 前以 `executable content drifted` 拒绝。

另补一个源码关系断言：MEASURE 调用该校验器时不再传 `db=context.db`，避免日后把文件系统依赖接回。

**Step 2: 运行 RED**

Run:

```bash
api-service/.venv/bin/python -m pytest -q \
  api-service/tests/test_p2_59_channel_emulator_execution_plan.py \
  -k 'vendor_file or resolved_channel_asset'
```

Expected: FAIL；旧实现要求 database session 或调用 SMB verifier。

**Step 3: 检查变异有效性**

确认若恢复 `verify_channel_asset_smu_project_bytes(db, asset)`，新增测试必红；测试只证明当前可观察故障，不扩展 SMB 工具本身。

**Step 4: 暂不提交**

RED 与最小生产修复放在同一功能提交，避免提交长期红分支。

### Task 2: 删除错误的正式运行前置门

**Files:**
- Modify: `api-service/app/services/channel_emulator_execution_plan.py`
- Modify: `api-service/app/services/mimo_ota/executors/measure.py`
- Modify: `api-service/tests/test_p2_59_channel_emulator_execution_plan.py`

**Step 1: 最小实现**

- 从 `validate_resolved_channel_asset_against_freeze` 删除 `db` 参数；
- 删除 vendor_file 专用的 `verify_channel_asset_smu_project_bytes` import/call；
- docstring 改为“只拒绝冻结 ChannelAsset identity/content drift”；
- MEASURE 调用点删除 `db=context.db`；
- 不改 resolver、NativeModelStrategy、PropsimF64Driver、operation receipt 或正式 outcome。

**Step 2: 运行 GREEN**

Run:

```bash
api-service/.venv/bin/python -m pytest -q \
  api-service/tests/test_p2_59_channel_emulator_execution_plan.py \
  api-service/tests/test_p2_60_channel_operation_receipt.py
```

Expected: 全部 PASS；重点确认 F64 `load_channel/emulation_file` 的 authoritative receipt 正反例仍绿。

**Step 3: 提交功能修复**

```bash
git add \
  api-service/app/services/channel_emulator_execution_plan.py \
  api-service/app/services/mimo_ota/executors/measure.py \
  api-service/tests/test_p2_59_channel_emulator_execution_plan.py
git commit -m "fix: 解除 F64 执行的 SMB 前置依赖"
```

### Task 3: 明确 SMB 工具定位并登记后续调研

**Files:**
- Modify: `api-service/app/services/smu_project_inventory.py`
- Modify: `api-service/app/api/channel_asset.py`
- Modify: `gui/src/features/ChannelWorkbench/ChannelWorkbench.tsx`
- Modify: `gui/test/smuProjectScanWiring.test.ts`
- Modify: `docs/roadmap-first-call.md`

**Step 1: 写文案契约 RED**

在 `gui/test/smuProjectScanWiring.test.ts` 增加断言，要求 ChannelWorkbench 明示：

- “开发/调试工具”；
- “不参与 Readiness、执行冻结或 MEASURE”。

Run:

```bash
node --experimental-strip-types --test gui/test/smuProjectScanWiring.test.ts
```

Expected: FAIL，现有文案只说只读挂载。

**Step 2: 最小文案与 roadmap 实现**

- 模块/端点 docstring 和 GUI Alert 明确工具是显式触发的离线开发辅助；
- 不改 API 请求/响应、数据库或 scan/sync 行为；
- 在 roadmap 新增 P2 候选“F64 文件常态化提供与版本控制调研”，明确型号/手册/现场方案未定、不得成为运行依赖；
- 将 P2-31 活状态补注为“开发工具交付已完成，正式执行依赖由 P1-78 移除”，不改历史记录。

**Step 3: 运行 GREEN**

Run:

```bash
node --experimental-strip-types --test gui/test/smuProjectScanWiring.test.ts
api-service/.venv/bin/python -m pytest -q api-service/tests/test_smu_project_scan_api.py
```

Expected: 全部 PASS；scan/sync 行为未变化。

**Step 4: 提交定位与 roadmap**

```bash
git add \
  api-service/app/services/smu_project_inventory.py \
  api-service/app/api/channel_asset.py \
  gui/src/features/ChannelWorkbench/ChannelWorkbench.tsx \
  gui/test/smuProjectScanWiring.test.ts \
  docs/roadmap-first-call.md
git commit -m "docs: 限定 SMB 工程扫描为开发工具"
```

### Task 4: 验证、主代理自查与 PR 闭环

**Files:**
- Review: all files changed from the branch base

**Step 1: 受影响链验证**

至少运行：

```bash
api-service/.venv/bin/python -m pytest -q \
  api-service/tests/test_p2_59_channel_emulator_execution_plan.py \
  api-service/tests/test_p2_60_channel_operation_receipt.py \
  api-service/tests/test_smu_project_inventory.py \
  api-service/tests/test_smu_project_scan_api.py \
  api-service/tests/test_rule_gates.py
```

**Step 2: 共享冻结/证据变化的最终全量**

运行全后端、GUI 相关契约与 production build、`compileall`、单一 Alembic head、base-to-HEAD
`diff-check`。记录 commit、命令、退出码与统计结尾；测试输入变化后不复用旧全量。

**Step 3: 单代理自查**

用户已选择单 agent。主代理按 AGENTS.md 全集规则检查：

- 正式执行中 `verify_channel_asset_smu_project_bytes` 零调用；
- scan/sync 仍可显式调用且失败只影响该工具；
- F64 load receipt/P2-66 仍 fail-closed；
- 无新增/修改 SCPI、无 provenance 白名单变化、无用户未跟踪文件进入提交。

在 PR 明写“主代理自查，非独立内审”。

**Step 4: 推送与外审**

- 推送 branch，创建 Ready PR；
- 确认远端 HEAD 后按 `(repo, PR, HEAD, Rn)` 去重触发 Codex R1；
- R1 处理本片功能 P1 与本片内 P2，触发 R2；
- R2 无 P1 且 mergeable/checks 通过或无必需 checks 时合并；仍有 P1 则只修 P1 并续审最新 HEAD；
- R2+ P2/P3 只报告，不自动积压。

**Step 5: 合并后同步与手工复验提示**

fetch 验证 `origin/main`，主目录 fast-forward，同步后清理 worktree/本地分支并保留未跟踪仪器资料。
提示用户重启/重载对应服务后复跑原 LTE CMW500 + F64 TestCase；该手工复验验证真实仪器路径，不能由本地测试替代。
