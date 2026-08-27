# P0-9B-1 CMW500 PCCBBBoard Truth Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 用厂商手册定义的 TRO setting query 权威回读 CMW500 LTE 2×2 Route 七字段，并在交叉回读一致时允许 `route_confirmed=true`。

**Architecture:** 在现有 `Cmw500LteCommandProfile` 增加唯一 TRO-specific query 与严格七字段 parser；真实驱动在写入、错误队列检查后，同时消费 specific 和 generic 两份回读。所有异常或不一致继续 fail-closed，不新增其他真值源。

**Tech Stack:** Python 3.13、Pydantic、pytest/pytest-asyncio、现有 SCPI evidence capture。

---

### Task 1: TRO-specific query 与严格 parser

**Files:**
- Modify: `api-service/app/hal/cmw500_command_profile.py`
- Modify: `api-service/tests/test_p1_73b_cmw_command_profile.py`

**Step 1: 写 RED**

在 command profile 测试中要求：

```python
assert Cmw500LteCommandProfile.route_nx2_query(1) == (
    "ROUTe:LTE:SIGN1:SCENario:TRO:FLEXible?"
)
assert Cmw500LteCommandProfile.parse_route_nx2_readback(
    "SUA1,RF1C,RX1,RF1O,TX1,RF2C,TX2"
) == CmwNx2Route(
    pcc_bb_board="SUA1",
    rx_connector="RF1C",
    rx_converter="RX1",
    tx1_connector="RF1O",
    tx1_converter="TX1",
    tx2_connector="RF2C",
    tx2_converter="TX2",
)
```

并参数化证明字段不足、`NAV`、空值和 SCPI 分隔符被拒绝。

**Step 2: 运行 RED**

Run:

```bash
cd api-service
./.venv/bin/python -m pytest -q tests/test_p1_73b_cmw_command_profile.py
```

Expected: FAIL，因为 `route_nx2_query` / `parse_route_nx2_readback` 尚不存在。

**Step 3: 最小 GREEN**

- 在 `CMW500_LTE_COMMANDS` 登记 `route_nx2_query`；source reference 同时注明：
  - Remote Control via SCPI 1179.4592.02-04 §3.6, printed p.22；
  - LTE UE User Manual 1173.9628.02-41 §2.6.8.1, printed p.630-631。
- builder 只格式化 signaling channel。
- parser 用 `_csv(response, 7)`，逐字段调用 `normalize_cmw_route_token`，返回
  `CmwNx2Route`。

**Step 4: 运行 GREEN**

Run:

```bash
cd api-service
./.venv/bin/python -m pytest -q \
  tests/test_p1_73b_cmw_command_profile.py \
  tests/test_p1_73b_cmw_parsers.py
```

Expected: PASS。

**Step 5: 提交**

```bash
git add api-service/app/hal/cmw500_command_profile.py \
  api-service/tests/test_p1_73b_cmw_command_profile.py
git commit -m "feat: query CMW LTE nx2 route parameters"
```

### Task 2: 驱动交叉回读并形成完整 applied Route

**Files:**
- Modify: `api-service/app/hal/cmw500_base_station.py`
- Modify: `api-service/tests/test_p1_73b_cmw_route_truth.py`
- Verify: `api-service/tests/test_p1_73c_cmw_measure_integration.py`
- Verify: `api-service/tests/test_p1_73c_base_station_window_writer.py`

**Step 1: 写 RED**

修改 fake transport，使成功路径同时返回：

```python
"ROUTe:LTE:SIGN1:SCENario:TRO:FLEXible?":
    "SUA1,RF1C,RX1,RF1O,TX1,RF2C,TX2",
"ROUTe:LTE:SIGN1?":
    'TRO,"No Connection",RF1C,RX1,RF1O,TX1,RF2C,TX2',
```

断言成功结果 `confirmed is True`、`applied == requested`、两条查询均被调用。另加三条
fail-closed 用例：specific query 的 PCC 不匹配、generic physical path 不匹配、specific query
抛异常；都不得从 requested 回填 `applied` 或确认成功。

**Step 2: 运行 RED**

Run:

```bash
cd api-service
./.venv/bin/python -m pytest -q tests/test_p1_73b_cmw_route_truth.py
```

Expected: FAIL，因为驱动尚未发送 specific query，成功路径仍保持未确认。

**Step 3: 最小 GREEN**

在现有 capture 中：

1. 保持 write → 完整错误队列为零；
2. 查询并解析 TRO-specific 七字段；
3. 查询并解析 generic active route；
4. specific 七字段必须等于 requested；generic 六字段必须等于 specific 六字段；
5. 全部成立后 `applied=asdict(specific_readback)`、`confirmed=True`；否则返回结构化原因且
   `confirmed=False`。

**Step 4: 运行 GREEN 与相关回归**

Run:

```bash
cd api-service
./.venv/bin/python -m pytest -q \
  tests/test_p1_73b_cmw_command_profile.py \
  tests/test_p1_73b_cmw_parsers.py \
  tests/test_p1_73b_cmw_route_truth.py \
  tests/test_p1_73c_cmw_measure_integration.py \
  tests/test_p1_73c_base_station_window_writer.py \
  tests/test_rule_gates.py
```

Expected: PASS。

**Step 5: 提交**

```bash
git add api-service/app/hal/cmw500_base_station.py \
  api-service/tests/test_p1_73b_cmw_route_truth.py
git commit -m "fix: confirm complete CMW LTE route readback"
```

### Task 3: 状态回执与验证

**Files:**
- Modify: `docs/roadmap-first-call.md`
- Modify: `docs/site-debug/2026-08-27-lte-cmw500-onsite-summary.md`

**Step 1: 更新状态但不冒充现场通过**

记录：本地有据 query/parser 已实现并通过回归；P0-9B-1 状态为“本地半完成，待真机只读 query
复验”。不得写成 P0-9B-1 完成。

**Step 2: 验证**

Run:

```bash
git diff --check
cd api-service
./.venv/bin/python -m compileall -q app tests
./.venv/bin/python -m pytest -q tests/test_rule_gates.py
```

Expected: 全部成功。

**Step 3: 提交**

```bash
git add docs/roadmap-first-call.md \
  docs/site-debug/2026-08-27-lte-cmw500-onsite-summary.md
git commit -m "docs: mark CMW baseband query ready for site"
```
