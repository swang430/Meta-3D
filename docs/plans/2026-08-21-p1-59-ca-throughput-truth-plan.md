# P1-59 CA Throughput Truth Implementation Plan

> **For Codex:** REQUIRED SUB-SKILL: Use executing-plans to implement this plan task-by-task.

**Goal:** 正式 NR-CA 执行只有在全部 SCell 激活获确认后才使用 UXM `OTA:ALL?` 聚合吞吐，并让 scope 证明贯穿 KPI、Analysis、报告与历史信任门。

**Architecture:** 在 `ThroughputMetrics` 定义最小 scope 契约，由 MeasureExecutor 根据已确认的载波激活结果传入驱动；UXM 依据 scope 选择 per-cell 或 ALL 查询。正式聚合和报告均再次核对 scope，报告吞吐 trust schema 升级为 2，使无口径证明的历史 schema 1 fail-closed。

**Tech Stack:** Python 3.13、asyncio、pytest、FastAPI/Pydantic、现有 SCPI evidence catalog。

---

### Task 1: 锁住 UXM scope 与命令选择

**Files:**
- Create: `api-service/tests/test_p1_59_ca_throughput_truth.py`
- Modify: `api-service/app/hal/base_station.py`
- Modify: `api-service/app/hal/uxm_command_profiles.py`
- Modify: `api-service/app/hal/uxm_base_station.py`
- Modify: `api-service/app/hal/cmw500_base_station.py`

**Step 1: Write the failing tests**

新增行为测试：单载波只发 `{cell}?` 并返回 `pcell`；CA 只发 DL/UL `ALL?` 并返回
`nr_all_cells`；聚合模板为 `None` 时不发 per-cell fallback，值为 `None`、validity=false、
scope=`unknown`；`to_dict()` 保留 scope。

**Step 2: Run tests to verify RED**

Run: `/Users/simon/Tools/MIMO-First/api-service/.venv/bin/python -m pytest -q tests/test_p1_59_ca_throughput_truth.py`

Expected: FAIL，原因是 API 尚不接受 scope、profile 没有 ALL 模板、返回对象没有 scope。

**Step 3: Write minimal implementation**

给 `ThroughputMetrics` 增加四个 scope 常量和字段；给 BaseStation/Mock/CMW500/UXM 的
读取与窗口接口增加 keyword-only `throughput_scope`。IRAT profile 用手册章节注释定义
DL/UL ALL 模板。UXM 只按显式 scope 选命令；请求 CA 但模板缺失时保持 unknown，不回退。

**Step 4: Run tests to verify GREEN**

Run: `/Users/simon/Tools/MIMO-First/api-service/.venv/bin/python -m pytest -q tests/test_p1_59_ca_throughput_truth.py tests/test_uxm_kpi_readback.py tests/test_p1_54_kpi_valid_contract.py`

Expected: PASS。

**Step 5: Commit**

```bash
git add api-service/tests/test_p1_59_ca_throughput_truth.py api-service/app/hal/base_station.py api-service/app/hal/uxm_command_profiles.py api-service/app/hal/uxm_base_station.py api-service/app/hal/cmw500_base_station.py
git commit -m "fix: add explicit CA throughput scope"
```

### Task 2: CA 激活全有或全无并贯穿正式聚合

**Files:**
- Modify: `api-service/tests/test_p1_59_ca_throughput_truth.py`
- Modify: `api-service/app/services/mimo_ota/executors/measure.py`

**Step 1: Write the failing tests**

为可独立调用的 CA 配置 helper 写参数化测试：inherit、缺 add、缺 activate、任一 add
返回 False、activate 返回 False 都返回阻塞原因；全部成功返回完整 SCell 清单和
`nr_all_cells`。再锁住 `_trusted_throughput_value()` 必须匹配 required scope，真实零仍有效。

**Step 2: Run tests to verify RED**

Run: `/Users/simon/Tools/MIMO-First/api-service/.venv/bin/python -m pytest -q tests/test_p1_59_ca_throughput_truth.py`

Expected: FAIL，当前代码只 warning 后继续，trust helper 也不看 scope。

**Step 3: Write minimal implementation**

提取 `_configure_requested_secondary_cells()`：无 SCell 返回空；有 SCell 时执行四路
fail-loud，并只在全部成功后返回清单。`execute()` 消费错误并在采样前 FAILED；根据
声明/确认结果设置 required scope，传给每个 window；可信样本要求 scope 精确匹配。
方位与 measure 顶层载荷写入 scope，`throughput_verified` 同时要求全方位有效且同 scope。

**Step 4: Run tests to verify GREEN**

Run: `/Users/simon/Tools/MIMO-First/api-service/.venv/bin/python -m pytest -q tests/test_p1_59_ca_throughput_truth.py tests/test_measure_input_and_param_branches.py tests/test_mimo_ota_precheck_cal_gate.py tests/test_p1_54_kpi_valid_contract.py`

Expected: PASS。

**Step 5: Commit**

```bash
git add api-service/tests/test_p1_59_ca_throughput_truth.py api-service/app/services/mimo_ota/executors/measure.py
git commit -m "fix: fail closed on partial CA activation"
```

### Task 3: Analysis、报告与历史信任门收口

**Files:**
- Modify: `api-service/tests/test_p1_59_ca_throughput_truth.py`
- Modify: `api-service/tests/test_p1_54_kpi_valid_contract.py`
- Modify: `api-service/tests/test_mimo_ota_report_verified_backcompat.py`
- Modify: `api-service/app/services/mimo_ota/executors/report.py`
- Modify: `api-service/app/services/report_service.py`

**Step 1: Write the failing tests**

新增报告测试：CA 顶层/逐方位 scope 缺失或为 pcell 时隐藏吞吐、formal trust=false；
单载波 pcell 与 CA nr_all_cells 均可在完整证明下发布；新报告 marker=2；marker=1 不再通过
`report_has_provenance_trust()`。

**Step 2: Run tests to verify RED**

Run: `/Users/simon/Tools/MIMO-First/api-service/.venv/bin/python -m pytest -q tests/test_p1_59_ca_throughput_truth.py tests/test_p1_54_kpi_valid_contract.py tests/test_mimo_ota_report_verified_backcompat.py`

Expected: FAIL，当前 report 只看旧 boolean 且 marker 固定为 1。

**Step 3: Write minimal implementation**

报告构建器从 `carrier_aggregation.num_component_carriers` 得出期望 scope，要求顶层和每个
有效方位精确一致；否则复用现有 UNKNOWN/N/A 门。统一常量把吞吐 trust schema 升至 2，
更新 server-owned marker 产生/消费点和明确代表当前可信报告的 fixtures；保留 marker=1
作为负例。

**Step 4: Run tests to verify GREEN**

Run: `/Users/simon/Tools/MIMO-First/api-service/.venv/bin/python -m pytest -q tests/test_p1_59_ca_throughput_truth.py tests/test_p1_54_kpi_valid_contract.py tests/test_mimo_ota_report_verified_backcompat.py`

Expected: PASS。

**Step 5: Commit**

```bash
git add api-service/tests/test_p1_59_ca_throughput_truth.py api-service/tests/test_p1_54_kpi_valid_contract.py api-service/tests/test_mimo_ota_report_verified_backcompat.py api-service/app/services/mimo_ota/executors/report.py api-service/app/services/report_service.py
git commit -m "fix: require carrier scope for trusted reports"
```

### Task 4: 诊断与 SCPI 证据镜像

**Files:**
- Modify: `api-service/tests/test_p1_59_ca_throughput_truth.py`
- Modify: `api-service/tests/test_uxm_scpi_compatibility.py`
- Modify: `api-service/tests/test_p1_47b_instrument_evidence.py`
- Modify: `api-service/app/diagnostics/sequences/uxm_scpi_compatibility.py`
- Modify: `api-service/app/data/scpi_evidence/p0_5_commands.json`

**Step 1: Write the failing tests**

锁住 IRAT compatibility critical partition 包含两条 ALL 命令，其他未定义 profile 不被猜测；
证据目录的 source section/notes 同时声明 per-cell 与 all-NR 合法形式，ALL query 能匹配
`uxm.dl_throughput` role 并解析为 E4 outcome。

**Step 2: Run tests to verify RED**

Run: `/Users/simon/Tools/MIMO-First/api-service/.venv/bin/python -m pytest -q tests/test_p1_59_ca_throughput_truth.py tests/test_uxm_scpi_compatibility.py tests/test_p1_47b_instrument_evidence.py`

Expected: FAIL，critical set 和 catalog 尚未显式覆盖 aggregate form。

**Step 3: Write minimal implementation**

把两个 ALL profile 字段加入 compatibility core critical names；更新 evidence catalog 的
来源章节、说明和 query role，使 per-cell 与 ALL 都有可审计出处。不得新增无手册 query。

**Step 4: Run tests to verify GREEN**

Run: `/Users/simon/Tools/MIMO-First/api-service/.venv/bin/python -m pytest -q tests/test_p1_59_ca_throughput_truth.py tests/test_uxm_scpi_compatibility.py tests/test_p1_47b_instrument_evidence.py tests/test_rule_gates.py`

Expected: PASS。

**Step 5: Commit**

```bash
git add api-service/tests/test_p1_59_ca_throughput_truth.py api-service/tests/test_uxm_scpi_compatibility.py api-service/tests/test_p1_47b_instrument_evidence.py api-service/app/diagnostics/sequences/uxm_scpi_compatibility.py api-service/app/data/scpi_evidence/p0_5_commands.json
git commit -m "test: cover aggregate throughput evidence"
```

### Task 5: 文档、回归与交付门

**Files:**
- Modify: `docs/roadmap-first-call.md`
- Modify: `docs/plans/2026-08-21-p1-59-ca-throughput-truth-design.md`

**Step 1: Update roadmap evidence**

把 P1-59 从 Current Focus 待开工更新为开发完成/待审，记录命令出处、scope 契约、历史
schema 1 fail-closed、测试结果；不提前标合并。

**Step 2: Run relevant and rule-gate regression**

Run: `/Users/simon/Tools/MIMO-First/api-service/.venv/bin/python -m pytest -q tests/test_p1_59_ca_throughput_truth.py tests/test_uxm_kpi_readback.py tests/test_p1_54_kpi_valid_contract.py tests/test_mimo_ota_report_verified_backcompat.py tests/test_uxm_scpi_compatibility.py tests/test_p1_47b_instrument_evidence.py tests/test_measure_input_and_param_branches.py tests/test_mimo_ota_precheck_cal_gate.py tests/test_rule_gates.py`

Expected: PASS。

**Step 3: Run compile and diff gates**

Run: `/Users/simon/Tools/MIMO-First/api-service/.venv/bin/python -m compileall -q app tests`

Run: `git diff --check`

Expected: 两者 exit 0。

**Step 4: Fresh internal review**

按 `AGENTS.md` 逐项复核命令出处、所有 CA 入口、scope 产生/消费全集、四种失败路径、
历史报告读取/下载/重生成门。P1 不为零则回到 RED→GREEN 修复并复审。

**Step 5: Commit and request external review**

```bash
git add docs/roadmap-first-call.md docs/plans/2026-08-21-p1-59-ca-throughput-truth-design.md
git commit -m "docs: record P1-59 verification"
git push -u origin codex/p1-59-ca-throughput-truth
```

开 Ready PR，触发 Codex 外审。R1 后处理本片可执行意见并触发 R2；若 R2 仍有 P1，
修复后继续 P1-only 外审直到覆盖最新 HEAD 的 review 无 P1，再 merge commit。
