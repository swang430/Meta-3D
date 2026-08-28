# P2-9 EMCenter ERROR 3 精确分类 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 让 `emcenter_switch_health` 只对 CAICT 现场已确认的 EMCenter 2.5.1 精确错误回复归类为已知不支持，同时保持其他异常 fail-closed。

**Architecture:** 在诊断序列内部增加一个最小、纯函数式的互锁回复分类器；它只消费序列已经读取的软件版本和原始互锁回复，不改变驱动、不新增 SCPI。现有原始字段保持兼容，新增结构化分类字段，成功摘要不再把“不支持”伪装成“互锁 0”。

**Tech Stack:** Python 3.13、asyncio、pytest、现有 diagnostics protocol dataclasses。

---

### Task 1: 用行为测试锁定精确白名单和拒绝边界

**Files:**
- Modify: `api-service/tests/test_p1_65_emcenter_switch_health.py`

**Step 1: 写精确现场组合的失败测试**

在既有 SUCCESS / BLOCKER 测试旁增加：

```python
_KNOWN_UNSUPPORTED_INTERLOCK = "ERROR 3;(INTLK? SAFETYRELAY);"

def test_firmware_251_exact_interlock_error_is_known_unsupported_success():
    responses = dict(
        _HEALTHY_RESPONSES,
        **{
            "VERSION_SW?": "2.5.1",
            "INTLK? SAFETYRELAY": _KNOWN_UNSUPPORTED_INTERLOCK,
        },
    )
    result = _run(_ScriptedEmcenter(responses, _MAPPINGS_TWO_CARDS))
    assert result.success is True
    assert result.extra["verdict"] == "SUCCESS"
    assert result.extra["interlock"] == _KNOWN_UNSUPPORTED_INTERLOCK
    assert result.extra["interlock_classification"] == "known_unsupported"
    assert "已确认不支持" in result.summary
    assert "互锁 0" not in result.summary
    step = next(s for s in result.steps if s.label == "INTLK? SAFETYRELAY")
    assert step.success is True
    assert step.raw == _KNOWN_UNSUPPORTED_INTERLOCK
```

**Step 2: 运行测试并确认 RED**

Run:

```bash
api-service/.venv/bin/pytest -q api-service/tests/test_p1_65_emcenter_switch_health.py::test_firmware_251_exact_interlock_error_is_known_unsupported_success
```

Expected: FAIL，因为现有代码把该回复加入 blockers，且没有 `interlock_classification`。

**Step 3: 写近似输入拒绝测试**

增加参数化测试，覆盖：其他固件的完整现场回复、2.5.1 下的缩写 `ERROR 3`、不同命令回显和其他错误。每一项均断言 `success=False`、`verdict=BLOCKER`、互锁 step 保留 raw 且失败。

**Step 4: 运行拒绝测试并记录当前结果**

Run:

```bash
api-service/.venv/bin/pytest -q api-service/tests/test_p1_65_emcenter_switch_health.py -k 'firmware_251 or near_match'
```

Expected: 精确放行用例 FAIL；拒绝用例 PASS。该组合证明 RED 来自缺失的精确例外，而非 fixture 或导入错误。

**Step 5: 提交 RED**

```bash
git add api-service/tests/test_p1_65_emcenter_switch_health.py
git commit -m "test: 锁定 EMCenter 2.5.1 互锁回复"
```

### Task 2: 最小实现序列内精确分类

**Files:**
- Modify: `api-service/app/diagnostics/sequences/emcenter_switch_health.py`
- Test: `api-service/tests/test_p1_65_emcenter_switch_health.py`

**Step 1: 修改前检查目标文件禁令与全集**

Run:

```bash
rg -n '绝不|不许|禁止|must not|别把|INTERLOCK|interlock|VERSION_SW' api-service/app/diagnostics/sequences/emcenter_switch_health.py api-service/tests/test_p1_65_emcenter_switch_health.py api-service/app/hal/rf_switch.py
```

确认仅序列的 docstring、metadata、互锁判定、成功摘要和 `extra` 是本片消费方；驱动连接行为不动。

**Step 2: 加入最小分类器**

在序列常量旁定义现场证据常量，并加入纯函数：

```python
_KNOWN_UNSUPPORTED_INTERLOCK_VERSION = "2.5.1"
_KNOWN_UNSUPPORTED_INTERLOCK_REPLY = "ERROR 3;(INTLK? SAFETYRELAY);"

def _classify_interlock(version: Optional[str], reply: Optional[str]) -> str:
    if reply is None:
        return "no_response"
    value = reply.strip()
    if value == "0":
        return "inactive"
    if value == "1":
        return "active"
    if (
        (version or "").strip() == _KNOWN_UNSUPPORTED_INTERLOCK_VERSION
        and value == _KNOWN_UNSUPPORTED_INTERLOCK_REPLY
    ):
        return "known_unsupported"
    return "invalid"
```

出处注释只引用 `docs/site-debug/2026-08-27-lte-cmw500-onsite-summary.md` 的现场原始记录；不得把它写成厂商手册通用结论。

**Step 3: 用分类结果驱动既有判定**

- `active`：沿用现有 Relay A BLOCKER；
- `known_unsupported`：step success，detail 明写仅该现场组合已确认不支持；
- `invalid`：沿用现有值域外 BLOCKER；
- `inactive`：沿用互锁未激活；
- `no_response`：由 `_ask` 既有逻辑处理。

始终把分类写入 `extra["interlock_classification"]`。SUCCESS 摘要按分类选择“互锁 0”或“互锁查询已确认不支持”。同步 docstring 与 metadata，明确这个精确例外。

**Step 4: 运行定点测试确认 GREEN**

Run:

```bash
api-service/.venv/bin/pytest -q api-service/tests/test_p1_65_emcenter_switch_health.py
```

Expected: 全部 PASS。

**Step 5: 运行驱动协议回归**

Run:

```bash
api-service/.venv/bin/pytest -q api-service/tests/test_etsl_switch_protocol.py
```

Expected: 全部 PASS，证明序列改动未改变传输和连接行为。

**Step 6: 造变异验证行为门**

临时把精确回复常量改为宽松前缀，运行新测试应出现拒绝边界失败；恢复后重跑定点测试。只记录结果，不提交变异。

**Step 7: 提交 GREEN**

```bash
git add api-service/app/diagnostics/sequences/emcenter_switch_health.py api-service/tests/test_p1_65_emcenter_switch_health.py
git commit -m "fix: 精确分类 EMCenter 互锁不支持回复"
```

### Task 3: 同步当前 roadmap 状态并完成验证

**Files:**
- Modify: `docs/roadmap-first-call.md`
- Review only: `docs/site-debug/2026-08-27-lte-cmw500-onsite-summary.md`

**Step 1: 更新当前状态镜像**

把 P2-9 当前描述改为：本地精确分类已完成，现场仍需重跑 `emcenter_switch_health` 取得 SUCCESS；TopologyEditor mapping 仍独立未完成。不要修改现场历史记录。

**Step 2: 全仓镜像扫描**

Run:

```bash
rg -n 'P2-9|ERROR 3|SAFETYRELAY|known_unsupported' README\* docs AGENTS.md CLAUDE.md api-service/app api-service/tests gui api/openapi.yaml
```

逐项确认：历史记录保持原样；未来承诺和当前 roadmap 不再说本地修复未完成；驱动宽松连接兼容只记录为独立待评估，不在本片修改。

**Step 3: 运行相关链与规则门**

Run:

```bash
api-service/.venv/bin/pytest -q \
  api-service/tests/test_p1_65_emcenter_switch_health.py \
  api-service/tests/test_etsl_switch_protocol.py \
  api-service/tests/test_diagnostic_sequences_api.py \
  api-service/tests/test_rule_gates.py
```

Expected: 全部 PASS。

**Step 4: 运行全后端与静态验证**

Run:

```bash
api-service/.venv/bin/pytest -q api-service/tests
api-service/.venv/bin/python -m compileall -q api-service/app api-service/tests
cd api-service && .venv/bin/alembic heads
git diff --check
```

Expected: pytest 0 failed；compileall 与 diff-check exit 0；Alembic 恰好一个 head。

**Step 5: 提交 roadmap**

```bash
git add docs/roadmap-first-call.md
git commit -m "docs: 更新 P2-9 本地收口状态"
```

**Step 6: fresh 内审**

按 `.claude/agents/pre-commit-reviewer.md` 的精简档调用独立 reviewer：本片只改一个源文件、没有新增协议或跨层机制。提供 staged/current diff、当前版本完整测试输出、变异清单，并要求不要重跑已有全量。P1 必须为 0；任何意见先按 receiving-code-review 核实，再逐条最小处理。

**Step 7: PR 与外审**

推送分支，开 Ready PR，描述中写 `Roadmap: P2-9`、可观察故障、严格白名单、验证和现场未完成项。触发 Codex R1；R1 的本片内 P1/P2 经 TDD 与 fresh 内审后处理并触发 R2。R2 或后续覆盖最新 HEAD 且无 P1、PR mergeable、checks 通过或无必需 checks 时合并。

**Step 8: 合并后清理**

fetch 验证 `origin/main`，主目录 `git merge --ff-only origin/main`，保留全部未跟踪仪器资料；删除工作树和本地分支。现场重跑项保持开放，不自动开始 NEW-1。
