"""P1-75：TestCase × BaseStation Adapter 执行兼容性硬门。

验收对照（设计稿 §6，四拒两放 + 判据红线）：
  ① UXM manifest + requested lte → 拒（freeze，零 connect / 零 SCPI 之前）
  ② CMW manifest + requested nr5g → 拒
  ③ manifest 缺所需 operation（fake manifest 缺 measurement_window）→ 拒
  ④ 冻结后 manifest 漂移 → 站点 B 拒绝进入首次 I/O
  ⑤ UXM + nr5g → 放行
  ⑥ CMW500 + lte → 放行
  ⑦ diagnostic_unbound 保持既有语义（verdict=no_adapter，可诊断运行）
  ⑧ 判据红线：TestCase 名字含 "CMW500" / driver 自报双 RAT 都不影响 verdict

另（任务补充）：
  ⑨ freeze 拒绝时 execution 不排后台（runner 层 CaseNotExecutable）
  ⑩ 旧 frozen dict（无 compatibility key）不崩、不回填（P2-66 终态语义）

变异自验对应表（⓪-④，各条在报告里实跑）：
  - evaluator 砍 RAT 成员检查 → ①② 红
  - evaluator 砍 operations ⊆ 检查 → ③ 红
  - freeze 不 raise（只记 verdict）→ ①②(freeze 级) + ⑨ 红
  - identity 不含 compatibility 再算 digest → 封存测试红
  - measure 站点砍 verify 调用 → ④ wiring 红
  - verify 对缺失 compatibility 返回错误 → ⑩ 红
"""

from __future__ import annotations

import inspect
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.database import Base
from app.hal.base_station import MockBaseStation
from app.hal.base_station_compatibility import (
    MEASURE_REQUIRED_OPERATIONS,
    BaseStationCompatibilityVerdict,
    BaseStationExecutionRequirements,
    build_frozen_compatibility_payload,
    build_measure_execution_requirements,
    build_no_adapter_verdict,
    evaluate_base_station_compatibility,
    manifest_compatibility_digest,
    verify_frozen_base_station_compatibility,
)
from app.hal.cmw500_base_station import RealCmw500Driver
from app.hal.uxm_base_station import RealUxmDriver
from app.models.instrument import (
    InstrumentCategory,
    InstrumentConnection,
    InstrumentModel,
)
from app.models.lab_profile import LabProfile
from app.models.test_plan import TestCase, TestExecution
from app.hal.base_station_compatibility import (
    MEASURE_REQUIRED_OPERATIONS,
    build_measure_execution_requirements,
    canonical_payload_digest,
)
from app.services.base_station_adapter_profile import (
    FREEZE_CONFIG_KEY,
    freeze_base_station_adapter_profile,
)


UXM_MODEL_NAME = "UXM 5G E7515B"
CMW_MODEL_NAME = "CMW500"

# 合法 LTE PCell（与 test_p1_73a_lte_operating_point.LTE_B3_PCELL 同形）。
LTE_B3_PCELL = {
    "radio_technology": "lte",
    "band": "B3",
    "duplex": "fdd",
    "lte_transmission_mode": "TM3",
    "lte_dl_earfcn": 1575,
    "frequency_hz": 1_842_500_000.0,
    "bandwidth_mhz": 20.0,
    "role": "pcell",
}
LTE_CONFIGURATION = {"component_carriers": [LTE_B3_PCELL]}


def _cmw_profile() -> dict:
    return {
        "schema_version": 1,
        "adapter": "cmw500",
        "lte_2x2_internal_route": {
            "pcc_bb_board": "BB1",
            "rx_connector": "RF1C",
            "rx_converter": "RX1",
            "tx1_connector": "RF1C",
            "tx1_converter": "TX1",
            "tx2_connector": "RF2C",
            "tx2_converter": "TX2",
        },
    }


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)


def _bound_execution(
    db,
    *,
    model_name: str,
    driver_mode: str,
    connection_params: dict | None,
    configuration: dict | None,
    case_name: str = "P1-75 兼容性用例",
):
    """建一条「选定 model + LabProfile 绑定 + TestCase + pending 执行行」链。"""

    category = InstrumentCategory(
        category_key="baseStation",
        category_name="Base Station",
        driver_mode=driver_mode,
    )
    db.add(category)
    db.flush()
    model = InstrumentModel(
        category_id=category.id,
        vendor="R&S" if model_name == CMW_MODEL_NAME else "Keysight",
        model=model_name,
        capabilities={},
    )
    db.add(model)
    db.flush()
    category.selected_model_id = model.id
    connection = InstrumentConnection(
        category_id=category.id,
        endpoint="192.0.2.10",
        connection_params=connection_params,
        created_by="test",
    )
    lab = LabProfile(
        name=f"lab-{uuid4()}",
        instrument_bindings=[
            {
                "category_id": str(category.id),
                "instrument_model_id": str(model.id),
                "connection_endpoint": "192.0.2.10",
                "driver_mode": driver_mode,
                "role": "baseStation",
            }
        ],
    )
    db.add_all([connection, lab])
    db.flush()
    case = TestCase(
        name=case_name,
        test_type="MIMO_OTA",
        configuration=configuration,
        created_by="test",
        lab_profile_id=lab.id,
    )
    db.add(case)
    db.flush()
    execution = TestExecution(
        test_case_id=case.id,
        status="pending",
        executed_by="test",
        config={},
    )
    db.add(execution)
    db.flush()
    return execution, lab, case


def _real_hal(model_name: str):
    if model_name == CMW_MODEL_NAME:
        driver = RealCmw500Driver("cmw", {"ip_address": "192.0.2.10"})
    else:
        driver = RealUxmDriver("uxm", {"ip_address": "192.0.2.10"})
    return SimpleNamespace(drivers={"baseStation": driver})


# ---------------------------------------------------------------------------
# 纯判定器：evaluate_base_station_compatibility
# ---------------------------------------------------------------------------


def test_uxm_manifest_rejects_lte_requirements():
    requirements = build_measure_execution_requirements("lte")

    verdict = evaluate_base_station_compatibility(
        requirements, RealUxmDriver.adapter_manifest
    )

    assert verdict.compatible is False
    assert verdict.status == "incompatible"
    assert any("lte" in reason for reason in verdict.reasons)
    assert verdict.requirements_digest == requirements.digest
    assert verdict.manifest_digest == manifest_compatibility_digest(
        RealUxmDriver.adapter_manifest
    )


def test_cmw_manifest_rejects_nr5g_requirements():
    verdict = evaluate_base_station_compatibility(
        build_measure_execution_requirements("nr5g"),
        RealCmw500Driver.adapter_manifest,
    )

    assert verdict.compatible is False
    assert any("nr5g" in reason for reason in verdict.reasons)


def test_manifest_missing_required_operation_is_rejected():
    # fake manifest：拿 UXM 真 manifest 摘掉 measurement_window（连带镜像/
    # measurement 保持自洽）。model_copy 不复跑校验，恰好允许做这种探针。
    base = RealUxmDriver.adapter_manifest
    operations = tuple(
        op for op in base.operations if op != "measurement_window"
    )
    crippled = base.model_copy(
        update={
            "operations": operations,
            "capabilities": operations,
            "measurement": None,
        }
    )

    verdict = evaluate_base_station_compatibility(
        build_measure_execution_requirements("nr5g"), crippled
    )

    assert verdict.compatible is False
    assert any("measurement_window" in reason for reason in verdict.reasons)


def test_uxm_manifest_accepts_nr5g_requirements():
    verdict = evaluate_base_station_compatibility(
        build_measure_execution_requirements("nr5g"),
        RealUxmDriver.adapter_manifest,
    )

    assert verdict.compatible is True
    assert verdict.status == "compatible"
    assert verdict.reasons == ()


def test_cmw_manifest_accepts_lte_requirements():
    verdict = evaluate_base_station_compatibility(
        build_measure_execution_requirements("lte"),
        RealCmw500Driver.adapter_manifest,
    )

    assert verdict.compatible is True
    assert verdict.reasons == ()


def test_evaluator_signature_has_no_driver_input():
    """判据红线：evaluator 的输入签名里根本不该出现 driver。"""

    parameters = inspect.signature(evaluate_base_station_compatibility).parameters
    assert set(parameters) == {"requirements", "manifest"}


def test_module_never_reads_driver_self_report_or_names():
    """粗筛（存在性门）：真正的行为门是 ⑧ 的两条冻结级测试。"""

    import app.hal.base_station_compatibility as module

    source = inspect.getsource(module)
    assert "get_supported_technologies" not in source
    assert "test_case" not in source
    assert "model_name" not in source


def test_requirements_are_frozen_with_explicit_mac_profile_slot():
    requirements = build_measure_execution_requirements("nr5g")

    assert requirements.schema_version == 1
    assert requirements.required_operations == MEASURE_REQUIRED_OPERATIONS
    assert requirements.mac_profile is None
    with pytest.raises(Exception):
        requirements.requested_rat = "lte"  # frozen
    # digest 对 requested_rat 敏感
    assert (
        requirements.digest
        != build_measure_execution_requirements("lte").digest
    )


# ---------------------------------------------------------------------------
# 站点 A：freeze 拒入口
# ---------------------------------------------------------------------------


def test_freeze_rejects_lte_case_on_uxm_binding(db):
    execution, lab, _case = _bound_execution(
        db,
        model_name=UXM_MODEL_NAME,
        driver_mode="real",
        connection_params=None,
        configuration=LTE_CONFIGURATION,
    )

    with pytest.raises(ValueError) as excinfo:
        freeze_base_station_adapter_profile(
            db, _real_hal(UXM_MODEL_NAME), execution, lab
        )

    message = str(excinfo.value)
    assert "lte" in message
    assert "uxm" in message
    assert FREEZE_CONFIG_KEY not in (execution.config or {})


def test_freeze_rejects_nr5g_case_on_cmw_binding(db):
    # configuration={} → schema 默认 nr5g（旧记录缺失时精确兼容为 nr5g）。
    execution, lab, _case = _bound_execution(
        db,
        model_name=CMW_MODEL_NAME,
        driver_mode="real",
        connection_params={"base_station_adapter_profile": _cmw_profile()},
        configuration={},
    )

    with pytest.raises(ValueError) as excinfo:
        freeze_base_station_adapter_profile(
            db, _real_hal(CMW_MODEL_NAME), execution, lab
        )

    assert "nr5g" in str(excinfo.value)
    assert FREEZE_CONFIG_KEY not in (execution.config or {})


def test_freeze_allows_nr5g_case_on_uxm_and_seals_compatibility(db):
    execution, lab, _case = _bound_execution(
        db,
        model_name=UXM_MODEL_NAME,
        driver_mode="real",
        connection_params=None,
        configuration={},
    )

    frozen = freeze_base_station_adapter_profile(
        db, _real_hal(UXM_MODEL_NAME), execution, lab
    )

    compatibility = frozen["compatibility"]
    assert compatibility["schema_version"] == 1
    assert compatibility["requirements"]["requested_rat"] == "nr5g"
    assert list(compatibility["requirements"]["required_operations"]) == list(
        MEASURE_REQUIRED_OPERATIONS
    )
    assert compatibility["requirements"]["mac_profile"] is None
    verdict = compatibility["verdict"]
    assert verdict["status"] == "compatible"
    assert verdict["compatible"] is True
    assert verdict["manifest_digest"] == manifest_compatibility_digest(
        RealUxmDriver.adapter_manifest
    )
    # 封存：compatibility 进 identity 后才算 digest —— 篡改必被 digest 抓到
    identity = {key: value for key, value in frozen.items() if key != "digest"}
    assert frozen["digest"] == canonical_payload_digest(identity)
    assert "compatibility" in identity


def test_freeze_allows_lte_case_on_cmw(db):
    execution, lab, _case = _bound_execution(
        db,
        model_name=CMW_MODEL_NAME,
        driver_mode="real",
        connection_params={"base_station_adapter_profile": _cmw_profile()},
        configuration=LTE_CONFIGURATION,
    )

    frozen = freeze_base_station_adapter_profile(
        db, _real_hal(CMW_MODEL_NAME), execution, lab
    )

    assert frozen["compatibility"]["verdict"]["compatible"] is True
    assert frozen["compatibility"]["requirements"]["requested_rat"] == "lte"


def test_freeze_diagnostic_unbound_records_no_adapter_and_passes(db):
    """⑦ diagnostic_unbound：无 adapter 无 manifest —— 不存在「组合」，
    verdict 记显式 no_adapter 并保持既有放行（模拟诊断语义，非本片放宽）。"""

    category = InstrumentCategory(
        category_key="baseStation",
        category_name="Base Station",
        driver_mode="mock",
    )
    db.add(category)
    db.flush()
    lab = LabProfile(
        name=f"lab-{uuid4()}",
        instrument_bindings=[
            {
                "category_id": str(category.id),
                "instrument_model_id": None,
                "connection_endpoint": None,
                "driver_mode": "mock",
                "role": "baseStation",
            }
        ],
    )
    db.add(lab)
    db.flush()
    case = TestCase(
        name="unbound 诊断",
        test_type="MIMO_OTA",
        configuration={},
        created_by="test",
        lab_profile_id=lab.id,
    )
    db.add(case)
    db.flush()
    execution = TestExecution(
        test_case_id=case.id, status="pending", executed_by="test", config={}
    )
    db.add(execution)
    db.flush()
    hal = SimpleNamespace(
        drivers={"baseStation": MockBaseStation("mock-bs", {"model": "Mock"})}
    )

    frozen = freeze_base_station_adapter_profile(db, hal, execution, lab)

    verdict = frozen["compatibility"]["verdict"]
    assert verdict["status"] == "no_adapter"
    assert verdict["compatible"] is True
    assert verdict["manifest_digest"] is None


def test_freeze_ignores_test_case_name(db):
    """⑧a 判据红线：名字写着 CMW500 的 nr5g 用例在 UXM 上照常放行。"""

    execution, lab, _case = _bound_execution(
        db,
        model_name=UXM_MODEL_NAME,
        driver_mode="real",
        connection_params=None,
        configuration={},
        case_name="CMW500 正式吞吐（名字是幌子）",
    )

    frozen = freeze_base_station_adapter_profile(
        db, _real_hal(UXM_MODEL_NAME), execution, lab
    )

    assert frozen["compatibility"]["verdict"]["compatible"] is True


def test_freeze_ignores_driver_self_reported_rats(db):
    """⑧b 判据红线：MockBS 自报双 RAT 并集（get_supported_technologies
    无条件返回 NR5G+LTE），判据源是注册 manifest —— lte × UXM 仍拒。"""

    execution, lab, _case = _bound_execution(
        db,
        model_name=UXM_MODEL_NAME,
        driver_mode="mock",
        connection_params=None,
        configuration=LTE_CONFIGURATION,
    )
    mock_driver = MockBaseStation("mock-bs", {"model": UXM_MODEL_NAME})
    technologies = mock_driver.get_supported_technologies()
    assert len(technologies) == 2  # 自报并集在场，门必须无视它
    hal = SimpleNamespace(drivers={"baseStation": mock_driver})

    with pytest.raises(ValueError, match="lte"):
        freeze_base_station_adapter_profile(db, hal, execution, lab)


def test_freeze_reuse_of_legacy_frozen_dict_keeps_it_untouched(db):
    """⑩ 旧 frozen dict：无 compatibility key —— 不崩、不回填（P2-66）。"""

    execution = TestExecution(status="pending", executed_by="test", config={})
    db.add(execution)
    db.flush()
    legacy = {
        "schema_version": 1,
        "resolution": {
            "schema_version": 1,
            "adapter": None,
            "status": "diagnostic_unbound",
            "execution_mode": "simulated",
            "profile": None,
        },
        "digest": "f" * 64,
    }
    execution.config = {FREEZE_CONFIG_KEY: dict(legacy)}
    hal = SimpleNamespace(
        drivers={"baseStation": MockBaseStation("mock-bs", {"model": "Mock"})}
    )

    reused = freeze_base_station_adapter_profile(db, hal, execution, None)

    assert reused == legacy
    assert "compatibility" not in reused


# ---------------------------------------------------------------------------
# 站点 B：verify_frozen_base_station_compatibility（measure 锁内复核）
# ---------------------------------------------------------------------------


def _frozen_compatibility(requested_rat: str, manifest) -> dict:
    requirements = build_measure_execution_requirements(requested_rat)
    verdict = evaluate_base_station_compatibility(requirements, manifest)
    assert verdict.compatible is True
    return build_frozen_compatibility_payload(requirements, verdict)


def test_verify_missing_compatibility_passes_legacy():
    assert (
        verify_frozen_base_station_compatibility(
            None,
            live_manifest=RealCmw500Driver.adapter_manifest,
            simulated=False,
        )
        is None
    )


def test_verify_matching_manifest_passes():
    payload = _frozen_compatibility("lte", RealCmw500Driver.adapter_manifest)

    assert (
        verify_frozen_base_station_compatibility(
            payload,
            live_manifest=RealCmw500Driver.adapter_manifest,
            simulated=False,
        )
        is None
    )


def test_verify_rejects_manifest_drift_after_freeze():
    """④：冻结时 UXM manifest，lease 后加载端却是 CMW manifest → 拒。"""

    payload = _frozen_compatibility("nr5g", RealUxmDriver.adapter_manifest)

    error = verify_frozen_base_station_compatibility(
        payload,
        live_manifest=RealCmw500Driver.adapter_manifest,
        simulated=False,
    )

    assert error is not None
    assert "drift" in error or "match" in error


def test_verify_rejects_tampered_requirements():
    payload = _frozen_compatibility("lte", RealCmw500Driver.adapter_manifest)
    payload["requirements"]["requested_rat"] = "nr5g"

    error = verify_frozen_base_station_compatibility(
        payload,
        live_manifest=RealCmw500Driver.adapter_manifest,
        simulated=False,
    )

    assert error is not None and "digest" in error


def test_verify_simulated_mock_without_manifest_passes():
    """授权 mock 不带注册 manifest（与执行计划 manifest=None 形态同构）。"""

    payload = _frozen_compatibility("nr5g", RealUxmDriver.adapter_manifest)

    assert (
        verify_frozen_base_station_compatibility(
            payload, live_manifest=None, simulated=True
        )
        is None
    )


def test_verify_real_without_manifest_is_rejected():
    payload = _frozen_compatibility("nr5g", RealUxmDriver.adapter_manifest)

    error = verify_frozen_base_station_compatibility(
        payload, live_manifest=None, simulated=False
    )

    assert error is not None


def test_verify_no_adapter_flip_is_rejected():
    requirements = build_measure_execution_requirements("nr5g")
    payload = build_frozen_compatibility_payload(
        requirements, build_no_adapter_verdict(requirements)
    )

    error = verify_frozen_base_station_compatibility(
        payload,
        live_manifest=RealUxmDriver.adapter_manifest,
        simulated=True,
    )

    assert error is not None
    # 反向：真 unbound（live 也无 manifest）仍放行
    assert (
        verify_frozen_base_station_compatibility(
            payload, live_manifest=None, simulated=True
        )
        is None
    )


def test_verify_incompatible_frozen_verdict_is_rejected():
    """frozen 里不可能出现 incompatible（freeze 已 raise）；出现即拒。"""

    requirements = build_measure_execution_requirements("lte")
    verdict = evaluate_base_station_compatibility(
        requirements, RealUxmDriver.adapter_manifest
    )
    assert verdict.compatible is False
    payload = build_frozen_compatibility_payload(requirements, verdict)

    error = verify_frozen_base_station_compatibility(
        payload,
        live_manifest=RealUxmDriver.adapter_manifest,
        simulated=False,
    )

    assert error is not None


# ---------------------------------------------------------------------------
# 站点 B wiring：_base_station_attempt_context 真的在消费 verify
# ---------------------------------------------------------------------------


def _cmw_manifest_driver(live_manifest):
    return SimpleNamespace(
        adapter_id="cmw500",
        simulated=False,
        mac_throughput_configuration_supported=True,
        adapter_manifest=live_manifest,
    )


def test_attempt_context_rejects_rat_capability_drift(monkeypatch):
    """④ wiring：同 adapter_id、rats 却漂移的 live manifest 拒进首次 I/O。"""

    from app.hal.base_station import resolve_base_station_execution_plan
    from app.hal.base_station_manifest import BaseStationRatCapability
    from app.services.mimo_ota.executors.measure import MeasureExecutor
    from tests.test_p2_50_execution_plan import (
        _Db,
        _attempt_execution,
        _bind_attempt_lease,
    )

    drifted = RealCmw500Driver.adapter_manifest.model_copy(
        update={
            "rats": ("nr5g",),
            "rat_capabilities": (
                BaseStationRatCapability(
                    rat="nr5g", source_reference="drifted-for-test"
                ),
            ),
        }
    )
    driver = _cmw_manifest_driver(drifted)
    frozen_plan = resolve_base_station_execution_plan(driver, manifest=drifted)
    execution = _attempt_execution(with_plan=True, plan=frozen_plan)
    execution.config[FREEZE_CONFIG_KEY]["compatibility"] = (
        _frozen_compatibility("lte", RealCmw500Driver.adapter_manifest)
    )
    _bind_attempt_lease(monkeypatch)

    with pytest.raises(RuntimeError, match="compatibility"):
        MeasureExecutor._base_station_attempt_context(
            SimpleNamespace(test_execution=execution, db=_Db(execution)),
            driver,
        )


def test_uppercase_rat_is_rejected_at_construction_with_a_precise_reason():
    """外审 R3 收窄：大写 "LTE" 在构造层即拒，理由直指值非法。

    刻意不做 lower() 归一化 —— 大写只可能来自从未通过 schema 校验的数据；
    此前它会流进 evaluator 得到误导性的「rat 不被 manifest 支持」。
    """

    with pytest.raises(ValueError, match="case-sensitive"):
        build_measure_execution_requirements("LTE")
    with pytest.raises(ValueError, match="not a valid RAT"):
        build_measure_execution_requirements("Lte")


def test_requirements_digest_is_forward_compatible_with_absent_fields():
    """外审 R3（真 high）：omit-when-None 的前向兼容行为门。

    站点 B 用 model_validate(旧 payload) 重算 digest 与冻结值比对。升级场景
    的形态 = 旧 payload 缺新增的可选字段：它与新代码默认 None 必须算出
    **同一个** digest，否则 P2-54 加字段后所有升级前冻结的 pending 执行
    会在站点 B 全部误拒。
    """

    with_explicit_none = BaseStationExecutionRequirements.model_validate(
        {
            "schema_version": 1,
            "requested_rat": "lte",
            "required_operations": list(MEASURE_REQUIRED_OPERATIONS),
            "mac_profile": None,
        }
    )
    without_the_key = BaseStationExecutionRequirements.model_validate(
        {
            "schema_version": 1,
            "requested_rat": "lte",
            "required_operations": list(MEASURE_REQUIRED_OPERATIONS),
        }
    )
    assert with_explicit_none.digest == without_the_key.digest
    # None 字段不得进入 digest 输入 —— 行为门，不是存在性门
    dumped = with_explicit_none.model_dump(mode="json", exclude_none=True)
    assert "mac_profile" not in dumped
    assert with_explicit_none.digest == canonical_payload_digest(dumped)


def test_attempt_context_rejects_real_driver_without_live_manifest(monkeypatch):
    """内审 F1 wiring：real 驱动 + 无 adapter_manifest → 站点 B 必须拒。

    钉住调用点的 ``simulated=getattr(base_station, "simulated", False) is True``
    实参本身：把它变异成恒 True，本用例会走 simulated 放行分支而不 raise。
    纯函数级已有 test_verify_real_without_manifest_is_rejected，但内审 μ2 实测
    该实参恒 True 时 27 用例全绿 —— wiring 层此前零保护。
    """

    from app.hal.base_station import resolve_base_station_execution_plan
    from app.services.mimo_ota.executors.measure import MeasureExecutor
    from tests.test_p2_50_execution_plan import (
        _Db,
        _attempt_execution,
        _bind_attempt_lease,
    )

    manifest = RealCmw500Driver.adapter_manifest
    with_manifest = _cmw_manifest_driver(manifest)
    frozen_plan = resolve_base_station_execution_plan(
        with_manifest, manifest=manifest
    )
    execution = _attempt_execution(with_plan=True, plan=frozen_plan)
    execution.config[FREEZE_CONFIG_KEY]["compatibility"] = (
        _frozen_compatibility("lte", manifest)
    )
    _bind_attempt_lease(monkeypatch)

    # real 驱动（simulated=False）却在 measure 时不再声明 adapter_manifest
    stripped = _cmw_manifest_driver(None)

    with pytest.raises(RuntimeError, match="compatibility"):
        MeasureExecutor._base_station_attempt_context(
            SimpleNamespace(test_execution=execution, db=_Db(execution)),
            stripped,
        )


def test_attempt_context_passes_with_matching_compatibility(monkeypatch):
    from app.hal.base_station import resolve_base_station_execution_plan
    from app.services.mimo_ota.executors.measure import MeasureExecutor
    from tests.test_p2_50_execution_plan import (
        _Db,
        _attempt_execution,
        _bind_attempt_lease,
    )

    manifest = RealCmw500Driver.adapter_manifest
    driver = _cmw_manifest_driver(manifest)
    frozen_plan = resolve_base_station_execution_plan(driver, manifest=manifest)
    execution = _attempt_execution(with_plan=True, plan=frozen_plan)
    execution.config[FREEZE_CONFIG_KEY]["compatibility"] = (
        _frozen_compatibility("lte", manifest)
    )
    _bind_attempt_lease(monkeypatch)

    resolved = MeasureExecutor._base_station_attempt_context(
        SimpleNamespace(test_execution=execution, db=_Db(execution)),
        driver,
    )

    assert resolved.attempt_id == "attempt-1"


# ---------------------------------------------------------------------------
# ⑨ runner 层：freeze 拒绝 → CaseNotExecutable → 不排后台
# ---------------------------------------------------------------------------


def test_runner_rejects_incompatible_case_before_background_task(db):
    from app.models.chamber import ChamberType, create_chamber_from_preset
    from app.services import test_case_runner as tcr
    from app.services.instrument_hal_service import get_hal_service
    from app.services.mimo_ota.factory import build_mimo_ota_test_case

    chamber = create_chamber_from_preset(
        ChamberType.TYPE_C.value, name="P1-75 chamber"
    )
    db.add(chamber)
    db.flush()
    category = InstrumentCategory(
        category_key="baseStation",
        category_name="Base Station",
        driver_mode="mock",
        is_active=True,
    )
    positioner_category = InstrumentCategory(
        category_key="positioner",
        category_name="转台",
        driver_mode="mock",
        is_active=True,
    )
    db.add_all([category, positioner_category])
    db.flush()
    model = InstrumentModel(
        category_id=category.id,
        vendor="Keysight",
        model=UXM_MODEL_NAME,
        capabilities={},
    )
    db.add(model)
    db.flush()
    category.selected_model_id = model.id
    db.add(
        InstrumentConnection(
            category_id=category.id,
            endpoint="192.0.2.50",
            connection_params=None,
            created_by="test",
        )
    )
    lab = LabProfile(
        name="P1-75-runner-lab",
        chamber_config_id=chamber.id,
        instrument_bindings=[
            {
                "category_id": str(category.id),
                "instrument_model_id": str(model.id),
                "connection_endpoint": "192.0.2.50",
                "driver_mode": "mock",
                "role": "baseStation",
            },
            {
                "category_id": str(positioner_category.id),
                "instrument_model_id": None,
                "connection_endpoint": None,
                "driver_mode": "mock",
                "role": "positioner",
            },
        ],
        is_active=True,
    )
    db.add(lab)
    db.commit()
    source, _ = build_mimo_ota_test_case(
        db,
        name="lte-on-uxm 不可能组合",
        lab_profile_id=lab.id,
        config_overrides={"component_carriers": [LTE_B3_PCELL]},
        created_by="test",
    )

    hal = get_hal_service()
    saved = hal.drivers.get("baseStation")
    hal.drivers["baseStation"] = MockBaseStation(
        "mock-bs", {"model": UXM_MODEL_NAME}
    )
    try:
        with pytest.raises(tcr.CaseNotExecutable) as excinfo:
            tcr.launch_test_case_execution(db, source.id)
    finally:
        if saved is None:
            hal.drivers.pop("baseStation", None)
        else:
            hal.drivers["baseStation"] = saved

    assert "lte" in str(excinfo.value)
    # 拒绝发生在排后台之前：无执行行、无后台 task、零相位进度
    assert db.query(TestExecution).count() == 0
    assert tcr._RUNNING_TASKS == {}
