# P2-64 Adapter-scoped Mock Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 让 `MockBaseStation` 的身份和能力只从 selected model 对应的已注册 manifest 派生，删除型号嗅探与多厂商能力并集。

**Architecture:** HAL 继续作为 selected model → registration 的唯一解析入口，并在 Mock 构造时显式注入不可变 manifest。Mock 只投影 manifest 中已经声明的 RAT、operation、config/window/metric 形状；P1-75 继续负责执行兼容性判定，模拟 provenance 与正式 KPI 门不变。

**Tech Stack:** Python 3.13、Pydantic v2、pytest/pytest-asyncio、FastAPI HAL service。

---

### Task 1: 锁定 Manifest-bound Mock 身份与能力合同

**Files:**
- Create: `api-service/tests/test_p2_64_adapter_scoped_mock.py`
- Modify: `api-service/app/hal/base_station.py`

**Step 1: Write the failing tests**

新增行为测试：

```python
def test_mock_requires_registered_manifest():
    with pytest.raises(ValueError, match="registered adapter manifest"):
        MockBaseStation("mock", {"model": UXM_MODEL_NAME})


def test_mock_rejects_model_manifest_drift():
    with pytest.raises(ValueError, match="does not match"):
        MockBaseStation(
            "mock",
            {"model": CMW_MODEL_NAME},
            adapter_manifest=RealUxmDriver.adapter_manifest,
        )


@pytest.mark.parametrize(
    "manifest,model,expected_rat",
    [
        (RealUxmDriver.adapter_manifest, UXM_MODEL_NAME, RadioTechnology.NR5G),
        (RealCmw500Driver.adapter_manifest, CMW_MODEL_NAME, RadioTechnology.LTE),
    ],
)
def test_mock_identity_and_rats_are_manifest_scoped(manifest, model, expected_rat):
    driver = MockBaseStation(
        "mock", {"model": model}, adapter_manifest=manifest
    )
    assert driver.adapter_id == manifest.adapter_id
    assert driver.adapter_manifest is manifest
    assert driver.get_supported_technologies() == [expected_rat]
```

补充 `get_capabilities()` 断言：只出现 manifest RAT，parameters 只包含 manifest
operations/config/window 声明；旧硬编码 frequency/max bandwidth 不得出现。

**Step 2: Run tests to verify RED**

Run:

```bash
api-service/.venv/bin/python -m pytest -q \
  api-service/tests/test_p2_64_adapter_scoped_mock.py
```

Expected: FAIL，因为构造器尚不接受/要求 `adapter_manifest`，且 RAT 仍返回能力并集。

**Step 3: Write minimal implementation**

- `MockBaseStation.__init__` 新增 keyword-only `adapter_manifest`。
- 校验 `BaseStationAdapterManifest` 类型及 `config.model == manifest.model_name`。
- `adapter_id`、operation flags、measurement cardinality 由 manifest 派生。
- `get_supported_technologies()` 与 `get_capabilities()` 只投影 manifest。
- 删除型号字符串嗅探和跨厂商硬编码参数。

**Step 4: Run tests to verify GREEN**

Run Task 1 测试，Expected: PASS。

**Step 5: Commit**

```bash
git add api-service/app/hal/base_station.py \
  api-service/tests/test_p2_64_adapter_scoped_mock.py
git commit -m "refactor: bind mock base station to adapter manifest"
```

### Task 2: 从 Manifest 派生指标、窗口和执行计划

**Files:**
- Modify: `api-service/tests/test_p2_64_adapter_scoped_mock.py`
- Modify: `api-service/app/hal/base_station.py`

**Step 1: Write the failing tests**

覆盖：

- UXM Mock registry 精确等于 UXM manifest measurement metrics；CMW 同理。
- registry 全部 `diagnostic_only`，且 profile id 稳定包含 manifest adapter。
- monkeypatch 真实 UXM/CMW Driver 构造器为抛错后，Mock registry 仍可解析，证明不实例化真实 Driver。
- `resolve_base_station_execution_plan(mock, manifest=mock.adapter_manifest)` 的 operation
  计划与 manifest 一致；不再由 Mock 恒真属性开放 SCell/RRC。
- UE info/capability 不发布另一 RAT 的 category/band/CA 声明；manifest 未证明的诊断能力保持未知。
- manifest 未声明的输入电平、RRC 与 SCell 直接调用 fail-closed，不绕过 execution plan。
- CMW route 只在 manifest 声明 `internal_route` 且冻结 profile 完整时生成 simulated/unknown
  七字段；UXM route 保持 not applicable。
- measurement window 仍为 simulated/diagnostic，`kpi_valid` 全 false。

**Step 2: Run tests to verify RED**

Expected: 真实 Driver 构造器阻断测试失败，且 plan/registry 仍反映旧跨厂商行为。

**Step 3: Write minimal implementation**

- `resolve_metric_registry()` 直接读取 `self.adapter_manifest.measurement.metrics` 并降级 evidence。
- 不再导入或实例化 `RealUxmDriver` / `RealCmw500Driver`。
- Mock operation flags 只从 manifest operations 派生。
- manifest 声明 `mac_throughput_config` 时实现共同 Mock SPI，并只返回 simulated/unknown、
  `applied=None` 的诊断回执；未声明时返回失败结果，不从请求值伪造 applied/confirmed。
- 保留既有 simulated observation/window 结构，不改变正式消费门。

**Step 4: Run tests to verify GREEN**

Run Task 2 测试和 P2-48/P2-49/P2-50 相关测试，Expected: PASS。

**Step 5: Commit**

```bash
git add api-service/app/hal/base_station.py \
  api-service/tests/test_p2_64_adapter_scoped_mock.py
git commit -m "refactor: derive mock behavior from adapter manifest"
```

### Task 3: HAL 注入唯一注册真值并迁移测试夹具

**Files:**
- Create: `api-service/tests/base_station_mock_factory.py`
- Modify: `api-service/app/services/instrument_hal_service.py`
- Modify: `api-service/tests/test_p2_64_adapter_scoped_mock.py`
- Modify: every existing test file returned by `rg -l 'MockBaseStation\(' api-service/tests`

**Step 1: Write the failing tests**

新增 HAL 构造测试：

- selected UXM + mock/mock_force 得到携带 UXM manifest 的 Mock。
- selected CMW500 得到携带 CMW manifest 的 Mock。
- 未注册型号或 registration/model 漂移在 `connect()` 前失败。
- real 路径仍构造真实 Driver，不改变连接策略。

建立 test-only `registered_mock_base_station()` helper；它通过
`get_base_station_adapter_registration(model_name)` 取注册 manifest，禁止接受任意 manifest payload。

**Step 2: Run tests to verify RED**

Expected: HAL 仍按统一两参数构造 Mock，未注入 manifest。

**Step 3: Write minimal implementation**

- HAL 在选中 `MockBaseStation` 时取得 selected model 的 registration，并显式注入 manifest。
- 其它类别和真实 BaseStation 构造路径保持原样。
- 将旧式直接 Mock 构造测试迁移到 test-only helper；真正测试无 adapter 的场景改用 driver absent，
  不把缺 manifest Mock 当 `diagnostic_unbound`。

**Step 4: Run tests to verify GREEN**

Run P2-64、P1-75、binding、HAL mode、P2-43～P2-53 受影响链，Expected: PASS。

**Step 5: Commit**

```bash
git add api-service/app/services/instrument_hal_service.py \
  api-service/tests/base_station_mock_factory.py api-service/tests
git commit -m "refactor: inject registered manifests into mock base stations"
```

### Task 4: 生产路径门、roadmap 与完整验证

**Files:**
- Modify: `api-service/tests/test_rule_gates.py`
- Modify: `docs/roadmap-first-call.md`
- Modify: `docs/plans/2026-08-30-base-station-testcase-compatibility-roadmap-design.md`

**Step 1: Write the failing rule tests**

增加从注册真值派生的不变量门：

- 生产 HAL 的 BaseStation Mock 构造必须携带 registration manifest。
- `MockBaseStation` 不得读取型号字符串决定 adapter，也不得无条件返回多 RAT。
- Mock metric registry 不得实例化真实 BaseStation Driver。

对每道门做坏变异并实跑，确认能够变红；测试类发现严重度上限 P2。

**Step 2: Run rule tests to verify RED**

Expected: 新门先因当前实现/缺少不变量而失败。

**Step 3: Complete minimal implementation and docs**

- 更新 roadmap：P2-64 标记本地完成并保持为外审收口 WIP；合并后再把 Current Focus 移到
  P2-65；现场项不变。
- 同步 compatibility roadmap design 的当前状态，不改历史计划正文。
- 全仓搜索旧的“能力并集/型号嗅探/P2-64 未启动”活文档镜像并只更新当前真值。

**Step 4: Fresh verification**

依次运行：

```bash
api-service/.venv/bin/python -m pytest -q <focused P2-64 suite>
api-service/.venv/bin/python -m pytest -q api-service/tests/test_rule_gates.py
api-service/.venv/bin/python -m pytest -q api-service/tests
api-service/.venv/bin/python -m compileall -q api-service/app api-service/tests
cd api-service && .venv/bin/alembic heads
git diff --check main...HEAD
```

GUI/OpenAPI 若无改动，明确记录不运行其契约/build；如发生变更则补跑对应镜像与 production build。

**Step 5: Independent review and PR**

- 按 `.claude/agents/pre-commit-reviewer.md` 做 fresh 独立功能内审；P1 最小 TDD 修复并复审。
- 提交最终 roadmap/门更新，推送并创建 Ready PR。
- 触发 Codex R1，处理本片功能 P1 与本片内 P2；fresh 内审后推送并触发 R2。
- 覆盖最新 HEAD 的 R2 无 P1且 mergeable/checks 通过或无必需 checks 时 merge commit。
- fetch 验证 `origin/main`，主目录 `git merge --ff-only origin/main`，保留未跟踪仪器资料，
  清理 worktree/本地分支；不得自动开始 P2-65。
