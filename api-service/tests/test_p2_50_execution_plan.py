"""P2-50：Capability-driven BaseStation Execution Plan。

门覆盖（各配变异，见 PR 记录）：
  ① 计划冻结与漂移拒绝 —— attempt 路径缺计划 / 计划与加载 adapter 漂移都 fail-loud；
  ② 四类站点只消费冻结计划项 —— 用「计划与散点属性互相矛盾」的交叉场景当行为门，
     任何回退成散点 getattr 判断的变异会当场红；
  ③ 旧 evidence（无计划字段）兼容 —— parse 往返仍接受，present-but-None 拒绝；
  ④ mock simulated 形态 —— mock 声明推导出的计划形状固定，simulated 语义不变。
"""

from __future__ import annotations

from tests.base_station_mock_factory import registered_mock_base_station

import inspect
from copy import deepcopy

from app.services.mimo_ota.base_station_execution_evidence import (
    canonical_snapshot_digest,
)
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.hal.base_station import (
    BaseStationExecutionPlan,
    BaseStationExecutionPlanItem,
    MockBaseStation,
    resolve_base_station_execution_plan,
)
from app.hal.cmw500_base_station import RealCmw500Driver
from app.hal.uxm_base_station import RealUxmDriver
from app.services import instrument_test_lease
from app.services.instrument_test_lease import ActiveBaseStationLeaseIdentity
from app.services.mimo_ota.base_station_execution_evidence import (
    BaseStationExecutionEvidence,
    parse_base_station_execution_evidence,
)
from app.services.mimo_ota.executors.measure import (
    MeasureExecutor,
    _formal_mac_configuration_blocker,
    _reconfigure_rrc_if_supported,
)
from tests.p1_73c_evidence_fixtures import valid_cmw_evidence
from tests.channel_emulator_plan_helpers import runtime_measure_plan


def _item(
    dimension: str,
    planned: bool,
    reason: str = "测试计划项",
) -> BaseStationExecutionPlanItem:
    return BaseStationExecutionPlanItem(
        dimension=dimension,
        planned=planned,
        capability_source="adapter_attribute:test",
        reason=reason,
    )


# ---------------------------------------------------------------------------
# 推导函数：vendor-neutral、声明为源、漂移拒绝
# ---------------------------------------------------------------------------


def test_plan_builder_has_no_adapter_identity_branch():
    source = inspect.getsource(resolve_base_station_execution_plan)

    assert "cmw500" not in source.lower()
    assert '"uxm"' not in source.lower()


def test_real_uxm_plan_derives_from_manifest_and_profile_declarations():
    uxm = RealUxmDriver(
        "uxm",
        {"ip_address": "192.0.2.1", "uxm_profile": "irat"},
    )

    plan = resolve_base_station_execution_plan(
        uxm, manifest=RealUxmDriver.adapter_manifest
    )

    assert plan.adapter_id == "uxm"
    # manifest 声明了 input_level_control token → 来源标 manifest
    assert plan.input_level_control.planned is True
    assert (
        plan.input_level_control.capability_source
        == "manifest.operations:input_level_control"
    )
    # P2-54 后 MAC profile 是 manifest 的正式能力声明，不再依赖实例属性。
    assert plan.mac_throughput.planned is True
    assert (
        plan.mac_throughput.capability_source
        == "manifest.operations:mac_throughput_config"
    )
    # UXM 未声明 SCell 权威回读 → 未 planned
    assert plan.scell.planned is False
    assert "激活态权威回读" in plan.scell.reason


def test_real_cmw_plan_keeps_input_level_fail_closed_with_declared_reason():
    cmw = RealCmw500Driver("cmw", {"ip_address": "192.0.2.2"})

    plan = resolve_base_station_execution_plan(
        cmw, manifest=RealCmw500Driver.adapter_manifest
    )

    assert plan.adapter_id == "cmw500"
    assert plan.input_level_control.planned is False
    # P2-51：CMW500 声明手册取证的正式 MAC 配置能力（manifest token 镜像）。
    assert plan.mac_throughput.planned is True
    assert (
        plan.mac_throughput.capability_source
        == "manifest.operations:mac_throughput_config"
    )
    assert plan.rrc_reconfiguration.planned is False
    assert plan.scell.planned is False
    # CMW 声明了 input_level_unavailable_reason → 吸收进计划项 reason
    declared = getattr(cmw, "input_level_unavailable_reason", None)
    if isinstance(declared, str) and declared:
        assert plan.input_level_control.reason == declared


def test_manifest_token_without_instance_declaration_is_drift():
    driver = SimpleNamespace(
        adapter_id="uxm",
        input_level_control_supported=False,
    )
    manifest = SimpleNamespace(
        adapter_id="uxm",
        operations=("input_level_control",),
    )

    with pytest.raises(ValueError, match="declaration drift"):
        resolve_base_station_execution_plan(driver, manifest=manifest)


def test_foreign_manifest_is_rejected():
    driver = SimpleNamespace(adapter_id="uxm")
    manifest = SimpleNamespace(adapter_id="cmw500", operations=())

    with pytest.raises(ValueError, match="does not belong"):
        resolve_base_station_execution_plan(driver, manifest=manifest)


def test_plan_digest_is_stable_and_payload_json_safe():
    import json

    driver = SimpleNamespace(
        adapter_id="uxm",
        SCELL_ACTIVATION_READBACK_AUTHORITATIVE=True,
    )

    first = resolve_base_station_execution_plan(driver, manifest=None)
    second = resolve_base_station_execution_plan(driver, manifest=None)

    assert first.digest == second.digest
    json.dumps(first.as_payload())  # JSON-safe
    assert first.measurement_window_contract_version == 1
    with pytest.raises(TypeError, match="must not be used as bool"):
        bool(first)
    with pytest.raises(TypeError, match="must not be used as bool"):
        bool(first.scell)


def test_mock_simulated_plan_shape_is_fixed():
    """④ mock 计划严格镜像所选 adapter manifest，不发布能力并集。"""

    expected_by_model = {
        "UXM 5G E7515B": ("uxm", False, True, False, True),
        "CMW500": ("cmw500", False, True, False, False),
    }
    for model, expected in expected_by_model.items():
        mock = registered_mock_base_station("mock", {"model": model})

        plan = resolve_base_station_execution_plan(
            mock, manifest=getattr(mock, "adapter_manifest", None)
        )

        adapter_id, scell, mac, rrc, input_level = expected
        assert plan.adapter_id == adapter_id
        assert plan.scell.planned is scell
        assert plan.mac_throughput.planned is mac
        assert plan.rrc_reconfiguration.planned is rrc
        assert plan.input_level_control.planned is input_level


# ---------------------------------------------------------------------------
# ② 四类站点消费冻结计划项 —— 交叉场景行为门
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rrc_site_consumes_plan_not_scattered_attribute():
    """计划未 planned 而属性声明 True：散点回退变异会调用 stub → 红。"""

    class _AttrSaysYes:
        rrc_reconfiguration_supported = True

        async def reconfigure_rrc(self, **_kwargs):
            raise AssertionError("unplanned RRC must not be dispatched")

    result = await _reconfigure_rrc_if_supported(
        _AttrSaysYes(),
        plan=_item("rrc_reconfiguration", False),
        mimo_layers=2,
        modulation="64QAM",
    )

    assert result is None


@pytest.mark.asyncio
async def test_rrc_planned_but_missing_method_is_plan_drift():
    with pytest.raises(RuntimeError, match="reconfigure_rrc"):
        await _reconfigure_rrc_if_supported(
            SimpleNamespace(),
            plan=_item("rrc_reconfiguration", True),
            mimo_layers=2,
            modulation="64QAM",
        )


def test_mac_site_consumes_plan_not_scattered_attribute():
    """非 mock 驱动：blocker 只看计划项；属性与计划矛盾时以计划为准。"""

    attr_yes_plan_no = SimpleNamespace(
        adapter_id="uxm",
        mac_throughput_configuration_supported=True,
    )
    blocker = _formal_mac_configuration_blocker(
        attr_yes_plan_no,
        plan=_item("mac_throughput", False, reason="计划未开放"),
    )
    assert blocker is not None
    assert "计划未开放" in blocker

    attr_no_plan_yes = SimpleNamespace(
        adapter_id="uxm",
        mac_throughput_configuration_supported=False,
    )
    assert _formal_mac_configuration_blocker(
        attr_no_plan_yes,
        plan=_item("mac_throughput", True),
    ) is None


def test_mock_mac_blocker_semantics_unchanged():
    mock = registered_mock_base_station(
        "mock", {"model": "UXM 5G E7515B"}
    )

    assert _formal_mac_configuration_blocker(
        mock, plan=_item("mac_throughput", False)
    ) is None
    assert _formal_mac_configuration_blocker(
        mock, plan=_item("mac_throughput", True)
    ) is None


@pytest.mark.asyncio
async def test_scell_site_consumes_plan_not_scattered_attribute():
    """属性声明 True 而计划未 planned：散点回退变异会写 SCell → 红。"""

    driver = SimpleNamespace(
        SCELL_ACTIVATION_READBACK_AUTHORITATIVE=True,
        add_secondary_cell=AsyncMock(return_value=True),
        activate_secondary_cells=AsyncMock(return_value=True),
    )
    scell = SimpleNamespace(
        frequency_hz=3.7e9,
        bandwidth_mhz=100,
        subcarrier_spacing_khz=30,
        band="n78",
    )

    added, blocker = await MeasureExecutor._configure_requested_secondary_cells(
        driver,
        [scell],
        plan=_item("scell", False, reason="计划未声明权威回读"),
        inherit=False,
        execution_id="p2-50-scell",
    )

    assert added == []
    assert blocker and "计划未声明权威回读" in blocker
    driver.add_secondary_cell.assert_not_awaited()
    driver.activate_secondary_cells.assert_not_awaited()


@pytest.mark.asyncio
async def test_input_level_site_consumes_plan_not_scattered_attribute():
    """属性声明 True 而计划未 planned：闭环必须跳过且不碰 BS。"""

    class _Ce:
        async def autoset_inputs(self, *_a):
            raise AssertionError("skipped loop must not touch CE")

        async def measure_input(self, *_a):
            raise AssertionError("skipped loop must not touch CE")

        async def get_input_level_limits(self, *_a):
            raise AssertionError("skipped loop must not touch CE")

        async def set_input_measurement_mode(self, *_a):
            raise AssertionError("skipped loop must not touch CE")

        async def set_burst_trigger_level(self, *_a):
            raise AssertionError("skipped loop must not touch CE")

        async def get_group_clipping(self, *_a, **_k):
            raise AssertionError("skipped loop must not touch CE")

        async def get_system_status(self):
            raise AssertionError("skipped loop must not touch CE")

    class _Bs:
        input_level_control_supported = True

        def __init__(self):
            self.calls: list[float] = []

        async def set_downlink_power(self, power_dbm: float):
            self.calls.append(power_dbm)
            return True

    bs = _Bs()
    payload = await MeasureExecutor()._run_input_level_closed_loop(
        emulator=_Ce(),
        base_station=bs,
        config=SimpleNamespace(mimo_layers=2, precheck_strict_input_level=True),
        execution_id="p2-50-input",
        plan=_item("input_level_control", False, reason="计划未开放输入闭环"),
        channel_emulator_plan=runtime_measure_plan(),
    )

    assert payload["skipped"] is True
    assert "计划未开放输入闭环" in payload["reason"]
    assert bs.calls == []


@pytest.mark.asyncio
async def test_input_level_planned_but_missing_method_is_plan_drift():
    with pytest.raises(RuntimeError, match="set_downlink_power"):
        await MeasureExecutor()._run_input_level_closed_loop(
            emulator=SimpleNamespace(),
            base_station=SimpleNamespace(),
            config=SimpleNamespace(
                mimo_layers=2, precheck_strict_input_level=True
            ),
            execution_id="p2-50-drift",
            plan=_item("input_level_control", True),
            channel_emulator_plan=runtime_measure_plan(),
        )


# ---------------------------------------------------------------------------
# ① attempt 路径：计划冻结缺席 / 漂移拒绝
# ---------------------------------------------------------------------------


class _Db:
    def __init__(self, execution):
        self._execution = execution

    def query(self, *_args, **_kwargs):  # pragma: no cover - not reached
        raise AssertionError("attempt context must not query in these tests")


def _attempt_execution(*, with_plan: bool, plan=None):
    evidence = valid_cmw_evidence()
    evidence["config_confirmed"] = False
    evidence["route_confirmed"] = False
    evidence["applied_route"] = None
    evidence["current_measurement_attempt_id"] = "attempt-1"
    evidence["current_measurement_attempt_state"] = "running"
    evidence["measurement_windows"] = []
    evidence["control_releases"] = []
    evidence["exchange_ids"] = []
    if with_plan:
        evidence["measurement_window_contract_version"] = 1
        evidence["execution_plan_contract_version"] = 1
        evidence["execution_plan"] = {
            **plan.as_payload(),
            "digest": plan.digest,
        }
    execution = SimpleNamespace(
        id=evidence["execution_id"],
        config={
            "base_station_execution_evidence": evidence,
            "base_station_adapter_profile_freeze": {
                "resolution": {
                    "schema_version": 1,
                    "adapter": "cmw500",
                    "execution_mode": "real",
                }
            },
        },
    )
    return execution


def _bind_attempt_lease(monkeypatch):
    lease = ActiveBaseStationLeaseIdentity(
        lease_id="lease-1",
        measurement_attempt_id="attempt-1",
        adapter_id="cmw500",
        session_token="session-1",
    )
    monkeypatch.setattr(
        instrument_test_lease,
        "active_base_station_lease_identity",
        lambda: lease,
    )


def test_attempt_without_frozen_plan_is_rejected(monkeypatch):
    execution = _attempt_execution(with_plan=False)
    _bind_attempt_lease(monkeypatch)

    with pytest.raises(RuntimeError, match="execution plan is not frozen"):
        MeasureExecutor._base_station_attempt_context(
            SimpleNamespace(test_execution=execution, db=_Db(execution)),
            SimpleNamespace(adapter_id="cmw500", simulated=False),
        )


def test_attempt_with_drifted_plan_is_rejected(monkeypatch):
    # 冻结计划来自「声明了 SCell 回读」的驱动；随后加载的驱动没有该声明。
    frozen_plan = resolve_base_station_execution_plan(
        SimpleNamespace(
            adapter_id="cmw500",
            SCELL_ACTIVATION_READBACK_AUTHORITATIVE=True,
        ),
        manifest=None,
    )
    execution = _attempt_execution(with_plan=True, plan=frozen_plan)
    _bind_attempt_lease(monkeypatch)

    with pytest.raises(RuntimeError, match="does not match the loaded adapter"):
        MeasureExecutor._base_station_attempt_context(
            SimpleNamespace(test_execution=execution, db=_Db(execution)),
            SimpleNamespace(adapter_id="cmw500", simulated=False),
        )


def test_attempt_with_matching_plan_carries_it_into_context(monkeypatch):
    loaded = SimpleNamespace(adapter_id="cmw500", simulated=False)
    frozen_plan = resolve_base_station_execution_plan(loaded, manifest=None)
    execution = _attempt_execution(with_plan=True, plan=frozen_plan)
    _bind_attempt_lease(monkeypatch)

    resolved = MeasureExecutor._base_station_attempt_context(
        SimpleNamespace(test_execution=execution, db=_Db(execution)),
        loaded,
    )

    assert resolved.attempt_id == "attempt-1"
    assert isinstance(resolved.execution_plan, BaseStationExecutionPlan)
    assert resolved.execution_plan.digest == frozen_plan.digest


# ---------------------------------------------------------------------------
# evidence 契约：冻结写入、digest 自洽、③ 旧 evidence 兼容
# ---------------------------------------------------------------------------


def test_initial_writer_freezes_execution_plan_with_registry():
    from app.services.execution_scpi_evidence import (
        initialize_base_station_execution_evidence,
    )
    from tests.p1_73c_evidence_fixtures import POSITION
    from tests.test_p1_73c_base_station_evidence_writer import (
        _CmwDriver,
        _execution,
        _frozen,
        _request,
    )

    saved = initialize_base_station_execution_evidence(
        _execution(),
        frozen_adapter=_frozen(),
        requested_config=_request(),
        requested_positions=[POSITION],
        driver=_CmwDriver(),
    )

    expected = resolve_base_station_execution_plan(_CmwDriver(), manifest=None)
    assert saved["execution_plan_contract_version"] == 1
    assert saved["execution_plan"] == {
        **expected.as_payload(),
        "digest": expected.digest,
    }


def test_initial_writer_freezes_manifest_sourced_plan():
    """内审 F1 的 freeze 半边：生产 freeze 函数必须把 driver 自带 manifest
    传进 resolve——溯源要落成 manifest.operations 形态（变异 MB 的闭合门；
    live 半边由 test_attempt_reconciles_manifest_bearing_driver_end_to_end 守）。"""
    from app.services.execution_scpi_evidence import (
        initialize_base_station_execution_evidence,
    )
    from tests.p1_73c_evidence_fixtures import POSITION
    from tests.test_p1_73c_base_station_evidence_writer import (
        _CmwDriver,
        _execution,
        _frozen,
        _request,
    )

    class _ManifestCmwDriver(_CmwDriver):
        adapter_manifest = SimpleNamespace(
            adapter_id="cmw500",
            operations=("input_level_control",),
        )
        input_level_control_supported = True

    saved = initialize_base_station_execution_evidence(
        _execution(),
        frozen_adapter=_frozen(),
        requested_config=_request(),
        requested_positions=[POSITION],
        driver=_ManifestCmwDriver(),
    )
    assert (
        saved["execution_plan"]["input_level_control"]["capability_source"]
        == "manifest.operations:input_level_control"
    )


def _current_evidence_with_plan() -> dict:
    plan = resolve_base_station_execution_plan(
        SimpleNamespace(adapter_id="cmw500"), manifest=None
    )
    evidence = valid_cmw_evidence()
    evidence["measurement_windows"] = []
    evidence["measurement_window_contract_version"] = 1
    evidence["execution_plan_contract_version"] = 1
    evidence["execution_plan"] = {**plan.as_payload(), "digest": plan.digest}
    return evidence


def test_evidence_rejects_tampered_plan_without_recomputed_digest():
    evidence = _current_evidence_with_plan()
    tampered = deepcopy(evidence)
    tampered["execution_plan"]["scell"]["planned"] = True  # 改值不重算摘要

    BaseStationExecutionEvidence.model_validate(evidence)  # 基线合法
    with pytest.raises(ValueError, match="digest mismatch"):
        BaseStationExecutionEvidence.model_validate(tampered)


def test_evidence_plan_and_contract_version_are_gated_together():
    evidence = _current_evidence_with_plan()

    missing_plan = deepcopy(evidence)
    missing_plan.pop("execution_plan")
    with pytest.raises(ValueError, match="requires its adapter execution plan"):
        BaseStationExecutionEvidence.model_validate(missing_plan)

    unfrozen = deepcopy(evidence)
    unfrozen.pop("execution_plan_contract_version")
    with pytest.raises(ValueError, match="unfrozen execution plan"):
        BaseStationExecutionEvidence.model_validate(unfrozen)

    window_ref_drift = deepcopy(evidence)
    window_ref_drift.pop("measurement_window_contract_version")
    with pytest.raises(ValueError, match="window reference disagrees"):
        BaseStationExecutionEvidence.model_validate(window_ref_drift)


def test_historical_evidence_without_plan_fields_still_parses():
    """③ 旧 evidence 完全没有计划字段：往返解析必须原样通过。"""

    legacy = valid_cmw_evidence()
    assert "execution_plan_contract_version" not in legacy
    assert "execution_plan" not in legacy

    normalized = parse_base_station_execution_evidence(deepcopy(legacy))

    assert normalized == legacy


def test_present_but_null_plan_contract_version_is_rejected():
    legacy = valid_cmw_evidence()
    legacy["execution_plan_contract_version"] = None

    assert parse_base_station_execution_evidence(legacy) is None


def test_current_evidence_with_plan_roundtrips_through_parse():
    evidence = _current_evidence_with_plan()

    normalized = parse_base_station_execution_evidence(deepcopy(evidence))

    assert normalized == evidence


class _ManifestBearingCmwDriver:
    """内审 F1 夹具：类级带 manifest 声明 input_level_control token 的驱动。

    真实 UXM 的 manifest 正是这样声明 input_level_control 的；此前对账链
    用例全走无 adapter_manifest 的夹具，capability_source 恒为
    adapter_attribute 形态——任一端把 manifest 实参换成 None 照样全绿。
    """

    adapter_manifest = SimpleNamespace(
        adapter_id="cmw500",
        operations=("input_level_control",),
    )

    def __init__(self):
        self.adapter_id = "cmw500"
        self.simulated = False
        self.input_level_control_supported = True


def test_attempt_reconciles_manifest_bearing_driver_end_to_end(monkeypatch):
    """内审 F1：freeze / live 两端 resolve 的 manifest 实参必须对称。

    freeze 端按 execution_scpi_evidence 的实参形态 resolve，live 端走
    _base_station_attempt_context 内部对账——任一端 manifest 实参退化为
    None，input_level 维溯源就从 manifest.operations 变 adapter_attribute，
    digest 漂移 → 对账 RuntimeError（变异 MB/MC 的闭合门）。
    """
    loaded = _ManifestBearingCmwDriver()
    frozen_plan = resolve_base_station_execution_plan(
        loaded, manifest=getattr(loaded, "adapter_manifest", None)
    )
    assert (
        frozen_plan.input_level_control.capability_source
        == "manifest.operations:input_level_control"
    )
    execution = _attempt_execution(with_plan=True, plan=frozen_plan)
    _bind_attempt_lease(monkeypatch)

    resolved = MeasureExecutor._base_station_attempt_context(
        SimpleNamespace(test_execution=execution, db=_Db(execution)),
        loaded,
    )
    assert resolved.execution_plan.digest == frozen_plan.digest


def test_evidence_rejects_foreign_adapter_execution_plan():
    """内审 F2：evidence.adapter 与 plan.adapter_id 错配必须被模型层拒绝，
    不能只靠 attempt 路径的 digest 对账兜底（历史/报告侧单独 validate 也要红）。"""
    evidence = _current_evidence_with_plan()
    foreign = deepcopy(evidence)
    plan = foreign["execution_plan"]
    plan["adapter_id"] = "uxm"
    # plan 自身 digest 密封——如实重算才打得到 adapter 错配那道判据
    plan["digest"] = canonical_snapshot_digest(
        {
            "schema_version": plan["schema_version"],
            "adapter_id": plan["adapter_id"],
            "scell": plan["scell"],
            "mac_throughput": plan["mac_throughput"],
            "rrc_reconfiguration": plan["rrc_reconfiguration"],
            "input_level_control": plan["input_level_control"],
            "measurement_window_contract_version": plan[
                "measurement_window_contract_version"
            ],
        }
    )
    with pytest.raises(ValueError, match="requires its adapter execution plan"):
        BaseStationExecutionEvidence.model_validate(foreign)


def test_resolve_accepts_list_operations_and_normalizes(monkeypatch):
    """外审 #417 R1：JSON 反序列化直传的 manifest.operations 是 list——
    必须与 tuple 行为等价（归一后溯源/digest 一致），其余类型仍拒绝。"""
    loaded = _ManifestBearingCmwDriver()
    plan_tuple = resolve_base_station_execution_plan(
        loaded, manifest=loaded.adapter_manifest
    )
    list_manifest = SimpleNamespace(
        adapter_id="cmw500",
        operations=list(loaded.adapter_manifest.operations),
    )
    plan_list = resolve_base_station_execution_plan(loaded, manifest=list_manifest)
    assert plan_list.digest == plan_tuple.digest

    with pytest.raises(ValueError, match="does not belong"):
        resolve_base_station_execution_plan(
            loaded,
            manifest=SimpleNamespace(
                adapter_id="cmw500", operations="input_level_control"
            ),
        )
