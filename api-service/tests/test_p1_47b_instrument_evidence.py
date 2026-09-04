"""P1-47B：仪器接受/生效证据必须按手册范围和真实状态分层。"""
from __future__ import annotations

import itertools
import json
from pathlib import Path

import pytest

from app.hal.base import InstrumentDriver, InstrumentStatus
from app.hal.scpi_evidence import (
    EvidenceLevel,
    EvidenceStatus,
    EvidenceVerdict,
    InstrumentEnvironment,
    ScpiExchangeRef,
    build_f64_evidence,
    build_positioner_evidence,
    build_uxm_evidence,
    build_uxm_throughput_evidence,
    capture_scpi_exchanges,
    evaluate_catalog_scope,
    load_p0_5_catalog,
    validate_catalog_document,
)
from app.hal.aerotech_positioner import RealAerotechDriver
from app.hal.propsim_f64 import F64SysInfo, RealPropsimF64Driver
from app.hal.uxm_base_station import RealUxmDriver
from app.core.logging_config import current_execution_id


CATALOG = (
    Path(__file__).parents[1]
    / "app"
    / "data"
    / "scpi_evidence"
    / "p0_5_commands.json"
)
_SEQUENCE = itertools.count()


@pytest.fixture(autouse=True)
def _bind_test_execution_context():
    token = current_execution_id.set("test-execution")
    try:
        yield
    finally:
        current_execution_id.reset(token)


class _Driver(InstrumentDriver):
    def _do_query(self, cmd: str, **kwargs):
        return "VALUE"

    def _do_write(self, cmd: str, **kwargs):
        return None

    async def connect(self): return True
    async def disconnect(self): return True
    async def configure(self, config): return True
    async def get_capabilities(self): return []
    async def get_metrics(self): return None
    async def reset(self): return True


def _env(*, app: str | None = None) -> InstrumentEnvironment:
    return InstrumentEnvironment(
        instrument_id="dut-control",
        instrument="uxm" if app else "f64",
        model="E7515B" if app else "PROPSIM F64",
        firmware_version="28.21.0.32" if app else "v1.0",
        test_application=app,
        captured_from_live_connection=True,
    )


def _positioner_scope():
    environment = InstrumentEnvironment(
        instrument_id="dut-control",
        instrument="positioner",
        model="A3200",
        firmware_version="1.0",
        captured_from_live_connection=True,
    )
    return evaluate_catalog_scope(
        load_p0_5_catalog(CATALOG).entries["positioner.position_feedback"],
        environment,
    )


def _exchange(
    exchange_id: str,
    command: str,
    *,
    result_type: str = "response",
    response: str | None = "VALUE",
    instrument_id: str = "dut-control",
    operation: str | None = None,
) -> ScpiExchangeRef:
    return ScpiExchangeRef(
        exchange_id=exchange_id,
        instrument_id=instrument_id,
        operation=operation or ("query" if "?" in command else "command"),
        command=command,
        execution_id="test-execution",
        capture_id="test-capture",
        sequence=next(_SEQUENCE),
        result_type=result_type,
        response=response,
    )


def test_catalog_covers_p0_5_critical_instrument_semantics():
    catalog = load_p0_5_catalog(CATALOG)
    required = {
        "f64.model_load",
        "f64.operation_complete",
        "f64.error_queue",
        "f64.simulation_state",
        "f64.model_state",
        "f64.center_frequency",
        "f64.input_reference",
        "f64.crest_factor",
        "f64.output_gain",
        "f64.output_loss",
        "f64.bypass_mode",
        "f64.topology_model_info",
        "f64.topology_group_count",
        "f64.topology_group_channels",
        "f64.topology_group_inputs",
        "f64.topology_group_outputs",
        "f64.input_measurement",
        "f64.input_level_limits",
        "f64.group_clipping",
        "f64.system_status",
        "uxm.config_readback",
        "uxm.config_apply",
        "uxm.cell_status",
        "uxm.error_queue",
        "uxm.dl_throughput",
        "positioner.move_absolute",
        "positioner.position_feedback",
    }
    assert required <= set(catalog.entries)
    assert all(catalog.entries[key].mandatory for key in required)


def test_catalog_rejects_missing_source_and_duplicate_ids():
    raw = json.loads(CATALOG.read_text(encoding="utf-8"))
    raw["commands"][0]["source"] = {}
    with pytest.raises(ValueError, match="source"):
        validate_catalog_document(raw)

    raw = json.loads(CATALOG.read_text(encoding="utf-8"))
    raw["commands"].append(dict(raw["commands"][0]))
    with pytest.raises(ValueError, match="duplicate"):
        validate_catalog_document(raw)

    raw = json.loads(CATALOG.read_text(encoding="utf-8"))
    raw["schema_version"] = 999
    with pytest.raises(ValueError, match="schema_version"):
        validate_catalog_document(raw)


@pytest.mark.parametrize(
    "status", [EvidenceStatus.UNVERIFIED, EvidenceStatus.ONSITE_OBSERVED]
)
def test_non_confirmed_catalog_entries_never_match_formal_scope(status):
    catalog = load_p0_5_catalog(CATALOG)
    entry = catalog.entries["uxm.error_queue"].model_copy(update={"status": status})
    decision = evaluate_catalog_scope(entry, _env(app="LTE_NR_IRAT"))
    assert decision.eligible is False
    assert status.value in decision.reason


def test_actual_test_application_must_match_confirmed_scope():
    catalog = load_p0_5_catalog(CATALOG)
    apply_entry = catalog.entries["uxm.config_apply"]
    assert evaluate_catalog_scope(apply_entry, _env(app="5G_NR_Test")).eligible
    mismatch = evaluate_catalog_scope(apply_entry, _env(app="LTE_NR_IRAT"))
    assert mismatch.eligible is False
    assert "test_application" in mismatch.reason

    status_entry = catalog.entries["uxm.cell_status"]
    assert evaluate_catalog_scope(status_entry, _env(app="5G_NR_Test")).eligible
    assert not evaluate_catalog_scope(status_entry, _env(app="LTE_NR_IRAT")).eligible
    throughput_entry = catalog.entries["uxm.dl_throughput"]
    assert evaluate_catalog_scope(
        throughput_entry, _env(app="5G_NR_Test")
    ).eligible
    assert not evaluate_catalog_scope(
        throughput_entry, _env(app="LTE_NR_IRAT")
    ).eligible


def test_config_or_unknown_environment_cannot_impersonate_live_snapshot():
    catalog = load_p0_5_catalog(CATALOG)
    entry = catalog.entries["f64.simulation_state"]
    configured = _env().model_copy(update={"captured_from_live_connection": False})
    unknown_fw = _env().model_copy(update={"firmware_version": None})
    assert not evaluate_catalog_scope(entry, configured).eligible
    assert not evaluate_catalog_scope(entry, unknown_fw).eligible


def test_f64_environment_snapshot_uses_live_identity_not_config_claims():
    driver = RealPropsimF64Driver(
        "f64-live",
        {"model": "FAKE-CONFIG-MODEL", "firmware_version": "fake-fw"},
    )
    assert driver.capture_evidence_environment().captured_from_live_connection is False

    driver._visa_resource = object()
    driver._status = InstrumentStatus.READY
    driver._identity_response = "Keysight Technologies,F8800A,SN-F64,9.8.7"
    driver.sys_info = F64SysInfo(
        raw="PROPSIM F64,64,RF,v1.0,16",
        product_family="PROPSIM F64",
        channel_count=64,
        signal_type="RF",
        firmware_version="v1.0",
        secondary_count=16,
    )
    driver.product_family = "PROPSIM F64"
    driver.firmware_version = "v1.0"
    env = driver.capture_evidence_environment()
    assert env.model == "PROPSIM F64"
    assert env.firmware_version == "9.8.7"
    assert env.hardware_firmware_version == "v1.0"
    assert env.serial_number == "SN-F64"
    assert "FAKE" not in env.model
    assert env.captured_from_live_connection is True

    driver._identity_response = "Keysight Technologies,F8800A,SN-F64"
    missing_idn_firmware = driver.capture_evidence_environment()
    assert missing_idn_firmware.firmware_version is None
    assert missing_idn_firmware.hardware_firmware_version == "v1.0"


def test_uxm_environment_snapshot_requires_live_detected_test_app():
    driver = RealUxmDriver(
        "uxm-live",
        {
            "model": "FAKE-CONFIG-MODEL",
            "firmware_version": "fake-fw",
            "detected_test_app": "FAKE_APP",
        },
    )
    driver._visa_session = object()
    driver._status = InstrumentStatus.CONNECTED
    driver._identity_response = "Keysight Technologies,E7515B,SN-UXM,28.21.0.32"
    driver._platform_identity_response = (
        "Keysight Technologies,E7515B Platform,SN-UXM,3.39.0.2"
    )
    first = driver.capture_evidence_environment()
    assert first.test_application is None

    driver.detected_test_app = "LTE_NR_IRAT"
    env = driver.capture_evidence_environment()
    assert env.model == "E7515B Platform"
    assert env.firmware_version == "28.21.0.32"
    assert env.serial_number == "SN-UXM"
    assert env.test_application == "LTE_NR_IRAT"
    assert env.captured_from_live_connection is True


def test_uxm_taf_identity_cannot_impersonate_missing_platform_identity():
    driver = RealUxmDriver("uxm-taf-only", {})
    driver._visa_session = object()
    driver._status = InstrumentStatus.READY
    driver._identity_response = (
        "Keysight Technologies,E7515B TAF,SN-TAF,28.21.0.3252"
    )
    driver._platform_identity_response = None
    driver.detected_test_app = "5G_NR_Test"
    env = driver.capture_evidence_environment()
    assert env.model is None
    assert env.serial_number is None
    assert env.hardware_firmware_version is None
    assert env.firmware_version == "28.21.0.3252"
    scope = evaluate_catalog_scope(
        load_p0_5_catalog(CATALOG).entries["uxm.config_apply"], env
    )
    assert scope.eligible is False


def test_uxm_snapshot_keeps_platform_hardware_identity_after_framework_redirect():
    driver = RealUxmDriver("uxm-redirected", {})
    driver._visa_session = object()
    driver._status = InstrumentStatus.READY
    driver._platform_identity_response = (
        "Keysight Technologies,E7515B Platform,SN-HW,3.39.0.2"
    )
    driver._identity_response = (
        "Keysight Technologies,Test Application Framework,SN-TAF,28.21.0.3252"
    )
    driver.detected_test_app = "5G_NR_Test"
    env = driver.capture_evidence_environment()
    assert env.model == "E7515B Platform"
    assert env.serial_number == "SN-HW"
    assert env.firmware_version == "28.21.0.3252"
    assert env.application_version == "28.21.0.3252"
    assert env.hardware_firmware_version == "3.39.0.2"
    scope = evaluate_catalog_scope(
        load_p0_5_catalog(CATALOG).entries["uxm.config_apply"], env
    )
    assert scope.eligible


@pytest.mark.asyncio
async def test_uxm_direct_taf_connection_probes_live_platform_identity(monkeypatch):
    opened: list[str] = []

    class Session:
        def __init__(self, *, platform: bool):
            self.platform = platform
            self.closed = False
            self.read_termination = None
            self.write_termination = None

        def query(self, command):
            if self.platform:
                return "Keysight Technologies,E7515B Platform,SN-HW,3.39.0.2"
            return {
                "*IDN?": (
                    "Keysight Technologies,C8700200A Test Application "
                    "Framework,SN-TAF,28.21.0.3252"
                ),
                "SYSTem:APPLication:NAME?": "5G_NR_Test",
                "*OPC?": "1",
            }.get(command.strip(), "0")

        def write(self, _command):
            return None

        def close(self):
            self.closed = True

    main_session = Session(platform=False)
    platform_session = Session(platform=True)

    class ResourceManager:
        def open_resource(self, resource, **_kwargs):
            opened.append(resource)
            return platform_session if "hislip0" in resource else main_session

    monkeypatch.setattr("pyvisa.ResourceManager", lambda: ResourceManager())
    driver = RealUxmDriver(
        "uxm-direct-taf",
        {"visa_resource": "TCPIP0::10.0.0.9::5125::SOCKET"},
    )
    assert await driver.connect() is True
    env = driver.capture_evidence_environment()
    assert "TCPIP::10.0.0.9::hislip0::INSTR" in opened
    assert env.model == "E7515B Platform"
    assert env.serial_number == "SN-HW"
    assert env.application_version == "28.21.0.3252"
    assert env.hardware_firmware_version == "3.39.0.2"
    assert platform_session.closed is True
    assert main_session.closed is False


def test_positioner_environment_is_honest_when_protocol_has_no_identity_query():
    driver = RealAerotechDriver(
        "turntable-live",
        {"model": "A3200", "firmware_version": "pretend"},
    )
    driver._reader = object()
    driver._writer = object()
    driver._status = InstrumentStatus.CONNECTED
    env = driver.capture_evidence_environment()
    assert env.captured_from_live_connection is True
    assert env.model is None
    assert env.firmware_version is None


def test_leftover_transport_on_error_is_not_a_live_environment():
    f64 = RealPropsimF64Driver("f64-stale", {})
    f64._visa_resource = object()
    f64._identity_response = "Keysight,F8800A,SN,FW"
    f64._status = InstrumentStatus.ERROR
    assert not f64.capture_evidence_environment().captured_from_live_connection

    uxm = RealUxmDriver("uxm-stale", {})
    uxm._visa_session = object()
    uxm._identity_response = "Keysight,E7515B,SN,FW"
    uxm._status = InstrumentStatus.ERROR
    assert not uxm.capture_evidence_environment().captured_from_live_connection


def test_exchange_capture_returns_ordered_terminal_refs_without_raw_secret():
    driver = _Driver("capture-test", {})
    token = current_execution_id.set("execution-live")
    try:
        with capture_scpi_exchanges() as exchanges:
            driver._write("CONF:AUTHENT:KEY:VALUE topsecret")
            assert driver._query("READ?") == "VALUE"
    finally:
        current_execution_id.reset(token)

    assert [item.operation for item in exchanges] == ["command", "query"]
    assert all(item.exchange_id for item in exchanges)
    assert exchanges[0].command.endswith("[REDACTED]")
    assert "topsecret" not in repr(exchanges)
    assert [item.result_type for item in exchanges] == ["ok", "response"]
    assert {item.execution_id for item in exchanges} == {"execution-live"}
    assert len({item.capture_id for item in exchanges}) == 1
    assert [item.sequence for item in exchanges] == [0, 1]


def test_f64_needs_opc_clean_error_readback_and_running_for_e3():
    scope = evaluate_catalog_scope(
        load_p0_5_catalog(CATALOG).entries["f64.simulation_state"], _env()
    )
    item = build_f64_evidence(
        evidence_key="f64.simulation_state",
        requested={"model": "CDL-C"},
        preclear_exchanges=[
            _exchange("preclear", "SYST:ERR?", response='0,"No error"')
        ],
        command_exchange=_exchange(
            "tx", "DIAG:SIMU:GO", result_type="ok", response=None
        ),
        opc_exchange=_exchange("opc", "*OPC?", response="1"),
        error_exchange=_exchange("err", "SYST:ERR?", response='0,"No error"'),
        readback_exchange=_exchange(
            "readback", "DIAG:SIMU:MOD:STATE?", response="CDL-C"
        ),
        state_exchange=_exchange("state", "DIAG:SIMU:STATE?", response="RUNNING"),
        scope=scope,
    )
    assert item.evidence_level is EvidenceLevel.APPLIED
    assert item.verdict is EvidenceVerdict.PASSED


def test_f64_bypass_requires_static_readback_and_reaches_e3():
    scope = evaluate_catalog_scope(
        load_p0_5_catalog(CATALOG).entries["f64.bypass_mode"], _env()
    )
    item = build_f64_evidence(
        evidence_key="f64.bypass_mode",
        requested=2,
        preclear_exchanges=[
            _exchange("bp-pre", "SYST:ERR?", response='0,"No error"')
        ],
        command_exchange=_exchange(
            "bp-set", "DIAG:SIMU:MODEL:STATIC 2", result_type="ok", response=None
        ),
        opc_exchange=_exchange("bp-opc", "*OPC?", response="1"),
        error_exchange=_exchange(
            "bp-err", "SYST:ERR?", response='0,"No error"'
        ),
        readback_exchange=_exchange(
            "bp-read", "DIAG:SIMU:MODEL:STATIC?", response="2"
        ),
        state_exchange=_exchange(
            "bp-state", "DIAG:SIMU:STATE?", response="STOPPED"
        ),
        scope=scope,
    )
    assert item.evidence_level is EvidenceLevel.APPLIED
    assert item.verdict is EvidenceVerdict.PASSED
    assert item.readback["value"] == 2.0

    wrong_readback = build_f64_evidence(
        evidence_key="f64.bypass_mode",
        requested=2,
        preclear_exchanges=[
            _exchange("bp2-pre", "SYST:ERR?", response='0,"No error"')
        ],
        command_exchange=_exchange(
            "bp2-set", "DIAG:SIMU:MODEL:STATIC 2", result_type="ok", response=None
        ),
        opc_exchange=_exchange("bp2-opc", "*OPC?", response="1"),
        error_exchange=_exchange(
            "bp2-err", "SYST:ERR?", response='0,"No error"'
        ),
        readback_exchange=_exchange(
            "bp2-read", "DIAG:SIMU:MODEL:STATE?", response="2"
        ),
        state_exchange=_exchange(
            "bp2-state", "DIAG:SIMU:STATE?", response="STOPPED"
        ),
        scope=scope,
    )
    assert wrong_readback.verdict is EvidenceVerdict.UNKNOWN

    no_readback = build_f64_evidence(
        evidence_key="f64.simulation_state",
        requested={"model": "CDL-C"},
        preclear_exchanges=[
            _exchange("preclear", "SYST:ERR?", response='0,"No error"')
        ],
        command_exchange=_exchange(
            "tx", "DIAG:SIMU:GO", result_type="ok", response=None
        ),
        opc_exchange=_exchange("opc", "*OPC?", response="1"),
        error_exchange=_exchange("err", "SYST:ERR?", response='0,"No error"'),
        readback_exchange=None,
        state_exchange=_exchange("state", "DIAG:SIMU:STATE?", response="RUNNING"),
        scope=scope,
    )
    assert no_readback.evidence_level is EvidenceLevel.TRANSPORT
    assert no_readback.verdict is EvidenceVerdict.UNKNOWN


@pytest.mark.parametrize(
    ("state_result_type", "state_response", "expected_reason"),
    [
        (None, None, "state_readback_missing"),
        ("transport_error", None, "state_query_terminal=transport_error"),
        ("response", '0,"No error"', "state_readback_invalid"),
    ],
)
def test_f64_bypass_requires_valid_state_readback_for_e3(
    state_result_type, state_response, expected_reason
):
    """STATIC? 匹配不够：旁路正式证据还必须拿到合法的 STATE? 终态。"""
    scope = evaluate_catalog_scope(
        load_p0_5_catalog(CATALOG).entries["f64.bypass_mode"], _env()
    )
    item = build_f64_evidence(
        evidence_key="f64.bypass_mode",
        requested=2,
        preclear_exchanges=[
            _exchange("bp-neg-pre", "SYST:ERR?", response='0,"No error"')
        ],
        command_exchange=_exchange(
            "bp-neg-set",
            "DIAG:SIMU:MODEL:STATIC 2",
            result_type="ok",
            response=None,
        ),
        opc_exchange=_exchange("bp-neg-opc", "*OPC?", response="1"),
        error_exchange=_exchange(
            "bp-neg-err", "SYST:ERR?", response='0,"No error"'
        ),
        readback_exchange=_exchange(
            "bp-neg-read", "DIAG:SIMU:MODEL:STATIC?", response="2"
        ),
        state_exchange=(
            _exchange(
                "bp-neg-state",
                "DIAG:SIMU:STATE?",
                result_type=state_result_type,
                response=state_response,
            )
            if state_result_type is not None
            else None
        ),
        scope=scope,
    )
    assert item.evidence_level is not EvidenceLevel.APPLIED
    assert item.verdict is EvidenceVerdict.UNKNOWN
    assert item.reason == expected_reason


def test_f64_active_driver_recipes_are_reachable_without_synthetic_stages():
    catalog = load_p0_5_catalog(CATALOG)
    go_scope = evaluate_catalog_scope(
        catalog.entries["f64.simulation_state"], _env()
    )
    preclear = _exchange("live-pre", "SYST:ERR?", response='0,"No error"')
    go = _exchange(
        "live-go", "DIAG:SIMU:GO", result_type="ok", response=None
    )
    opc = _exchange("live-opc", "*OPC?", response="1")
    err = _exchange("live-err", "SYST:ERR?", response='0,"No error"')
    state = _exchange("live-state", "DIAG:SIMU:STATE?", response="RUNNING")
    go_item = build_f64_evidence(
        evidence_key="f64.simulation_state",
        requested="RUNNING",
        preclear_exchanges=[preclear],
        command_exchange=go,
        opc_exchange=opc,
        error_exchange=err,
        readback_exchange=state,
        state_exchange=state,
        scope=go_scope,
    )
    assert go_item.evidence_level is EvidenceLevel.APPLIED
    assert go_item.verdict is EvidenceVerdict.PASSED

    load_scope = evaluate_catalog_scope(catalog.entries["f64.model_load"], _env())
    load_pre = _exchange("load-pre", "SYST:ERR?", response='0,"No error"')
    load = _exchange(
        "load-file",
        r"CALC:FILT:FILE D:\\Models\\CDL-C.smu",
        result_type="ok",
        response=None,
    )
    load_opc = _exchange("load-opc", "*OPC?", response="1")
    load_err = _exchange("load-err", "SYST:ERR?", response='0,"No error"')
    model_state = _exchange(
        "load-model", "DIAG:SIMU:MODEL:STATE?", response="MODEL_READY"
    )
    stopped = _exchange(
        "load-state", "DIAG:SIMU:STATE?", response="STOPPED"
    )
    load_item = build_f64_evidence(
        evidence_key="f64.model_load",
        requested=r"D:\\Models\\CDL-C.smu",
        preclear_exchanges=[load_pre],
        command_exchange=load,
        opc_exchange=load_opc,
        error_exchange=load_err,
        readback_exchange=model_state,
        state_exchange=stopped,
        scope=load_scope,
    )
    assert load_item.evidence_level is EvidenceLevel.APPLIED
    assert load_item.verdict is EvidenceVerdict.PASSED


def test_uxm_real_order_with_controlled_interleaving_reaches_e3():
    scope = evaluate_catalog_scope(
        load_p0_5_catalog(CATALOG).entries["uxm.config_apply"],
        _env(app="5G_NR_Test"),
    )
    command = _exchange(
        "real-uc", "CONF:NR5G:CELL0:DL:ARFCN 636666",
        result_type="ok", response=None,
    )
    _exchange("real-noise-1", "CONF:NR5G:CELL0:DL:BW 100", result_type="ok")
    apply = _exchange(
        "real-ua", "BSE:CONF:NR5G:APPLY", result_type="ok", response=None
    )
    state = _exchange(
        "real-us", "BSE:STATUS:NR5G:CELL0?", response="CONNECTED"
    )
    _exchange("real-noise-2", "CONF:NR5G:CELL0:BAND?", response="N78")
    readback = _exchange(
        "real-ur", "CONF:NR5G:CELL0:DL:ARFCN?", response="636666"
    )
    item = build_uxm_evidence(
        evidence_key="uxm.config_apply",
        requested=636666,
        command_exchange=command,
        readback_exchange=readback,
        apply_exchange=apply,
        protocol_state_exchange=state,
        scope=scope,
    )
    assert item.evidence_level is EvidenceLevel.APPLIED
    assert item.verdict is EvidenceVerdict.PASSED
    assert item.exchange_ids == ["real-uc", "real-ua", "real-us", "real-ur"]


def test_f64_opc_one_never_hides_device_error():
    scope = evaluate_catalog_scope(
        load_p0_5_catalog(CATALOG).entries["f64.simulation_state"], _env()
    )
    item = build_f64_evidence(
        evidence_key="f64.simulation_state",
        requested={"model": "CDL-C"},
        preclear_exchanges=[
            _exchange("preclear", "SYST:ERR?", response='0,"No error"')
        ],
        command_exchange=_exchange(
            "a", "DIAG:SIMU:GO", result_type="ok", response=None
        ),
        opc_exchange=_exchange("b", "*OPC?", response="1"),
        error_exchange=_exchange(
            "c", "SYST:ERR?", response='-300,"No simulation opened"'
        ),
        readback_exchange=_exchange("d", "DIAG:SIMU:MOD:STATE?", response="CDL-C"),
        state_exchange=_exchange("e", "DIAG:SIMU:STATE?", response="RUNNING"),
        scope=scope,
    )
    assert item.evidence_level is EvidenceLevel.TRANSPORT
    assert item.verdict is EvidenceVerdict.REJECTED


def test_catalog_max_level_cannot_be_exceeded_by_good_looking_runtime_state():
    scope = evaluate_catalog_scope(
        load_p0_5_catalog(CATALOG).entries["f64.simulation_state"], _env()
    ).model_copy(update={"max_evidence_level": EvidenceLevel.TRANSPORT})
    item = build_f64_evidence(
        evidence_key="f64.simulation_state",
        requested={"model": "CDL-C"},
        preclear_exchanges=[
            _exchange("preclear", "SYST:ERR?", response='0,"No error"')
        ],
        command_exchange=_exchange(
            "set", "DIAG:SIMU:GO", result_type="ok", response=None
        ),
        opc_exchange=_exchange("opc", "*OPC?", response="1"),
        error_exchange=_exchange("err", "SYST:ERR?", response='0,"No error"'),
        readback_exchange=_exchange(
            "readback", "DIAG:SIMU:MOD:STATE?", response="CDL-C"
        ),
        state_exchange=_exchange("state", "DIAG:SIMU:STATE?", response="RUNNING"),
        scope=scope,
    )
    assert item.evidence_level is EvidenceLevel.TRANSPORT
    assert item.verdict is EvidenceVerdict.UNKNOWN
    assert "catalog_max_evidence_level" in item.reason


def test_uxm_config_readback_is_e2_until_apply_and_protocol_state():
    readback_scope = evaluate_catalog_scope(
        load_p0_5_catalog(CATALOG).entries["uxm.config_readback"],
        _env(app="5G_NR_Test"),
    )
    accepted = build_uxm_evidence(
        evidence_key="uxm.config_readback",
        requested={"arfcn": 636666},
        command_exchange=_exchange(
            "set", "CONF:NR5G:CELL0:DL:ARFCN 636666", result_type="ok", response=None
        ),
        readback_exchange=_exchange(
            "read", "CONF:NR5G:CELL0:DL:ARFCN?", response="636666"
        ),
        apply_exchange=None,
        protocol_state_exchange=None,
        scope=readback_scope,
    )
    assert accepted.evidence_level is EvidenceLevel.ACCEPTED
    assert accepted.verdict is EvidenceVerdict.PASSED

    scope = evaluate_catalog_scope(
        load_p0_5_catalog(CATALOG).entries["uxm.config_apply"],
        _env(app="5G_NR_Test"),
    )
    applied = build_uxm_evidence(
        evidence_key="uxm.config_apply",
        requested={"arfcn": 636666},
        command_exchange=_exchange(
            "set", "CONF:NR5G:CELL0:DL:ARFCN 636666", result_type="ok", response=None
        ),
        readback_exchange=_exchange(
            "read", "CONF:NR5G:CELL0:DL:ARFCN?", response="636666"
        ),
        apply_exchange=_exchange(
            "apply", "BSE:CONF:NR5G:APPLY", result_type="ok", response=None
        ),
        protocol_state_exchange=_exchange(
            "state", "BSE:STATUS:NR5G:CELL0?", response="CONNECTED"
        ),
        scope=scope,
    )
    assert applied.evidence_level is EvidenceLevel.APPLIED


def test_uxm_offline_config_can_reach_e3_via_later_cell_activation():
    """CELL 初始 OFF：写配置不发 APPLY，后续 CELL ON 自动应用。"""
    scope = evaluate_catalog_scope(
        load_p0_5_catalog(CATALOG).entries["uxm.config_apply"],
        _env(app="5G_NR_Test"),
    )
    applied = build_uxm_evidence(
        evidence_key="uxm.config_apply",
        requested={"arfcn": 636666},
        command_exchange=_exchange(
            "offline-set",
            "CONF:NR5G:CELL0:DL:ARFCN 636666",
            result_type="ok",
            response=None,
        ),
        readback_exchange=_exchange(
            "offline-read", "CONF:NR5G:CELL0:DL:ARFCN?", response="636666"
        ),
        apply_exchange=None,
        activation_exchange=_exchange(
            "cell-on",
            "CONF:NR5G:CELL0:ACTive:STATe ON",
            result_type="ok",
            response=None,
        ),
        protocol_state_exchange=_exchange(
            "connected", "BSE:STATUS:NR5G:CELL0?", response="CONNECTED"
        ),
        scope=scope,
    )
    assert applied.evidence_level is EvidenceLevel.APPLIED
    assert applied.verdict is EvidenceVerdict.PASSED
    assert applied.reason == "cell_activated_and_protocol_state=CONNECTED"
    assert applied.exchange_ids == [
        "offline-set", "offline-read", "cell-on", "connected"
    ]


def test_uxm_initial_on_long_capture_apply_readback_then_state_reaches_e3():
    """长 capture 的真实 ON 路径：write → APPLY → readback → CONNECTED。"""
    scope = evaluate_catalog_scope(
        load_p0_5_catalog(CATALOG).entries["uxm.config_apply"],
        _env(app="5G_NR_Test"),
    )
    item = build_uxm_evidence(
        evidence_key="uxm.config_apply",
        requested=636666,
        command_exchange=_exchange(
            "on-set", "CONF:NR5G:CELL0:DL:ARFCN 636666", result_type="ok", response=None
        ),
        apply_exchange=_exchange(
            "on-apply", "BSE:CONF:NR5G:APPLY", result_type="ok", response=None
        ),
        readback_exchange=_exchange(
            "on-read", "CONF:NR5G:CELL0:DL:ARFCN?", response="636666"
        ),
        protocol_state_exchange=_exchange(
            "on-state", "BSE:STATUS:NR5G:CELL0?", response="CONNECTED"
        ),
        scope=scope,
    )
    assert item.evidence_level is EvidenceLevel.APPLIED
    assert item.verdict is EvidenceVerdict.PASSED
    assert item.exchange_ids == ["on-set", "on-apply", "on-read", "on-state"]


def test_unrelated_on_command_cannot_impersonate_uxm_cell_activation():
    scope = evaluate_catalog_scope(
        load_p0_5_catalog(CATALOG).entries["uxm.config_apply"],
        _env(app="5G_NR_Test"),
    )
    item = build_uxm_evidence(
        evidence_key="uxm.config_apply",
        requested=636666,
        command_exchange=_exchange(
            "set", "CONF:NR5G:CELL0:DL:ARFCN 636666", result_type="ok", response=None
        ),
        readback_exchange=_exchange(
            "read", "CONF:NR5G:CELL0:DL:ARFCN?", response="636666"
        ),
        apply_exchange=None,
        activation_exchange=_exchange(
            "display-on", "DISPLAY:STATE ON", result_type="ok", response=None
        ),
        protocol_state_exchange=_exchange(
            "state", "BSE:STATUS:NR5G:CELL0?", response="CONNECTED"
        ),
        scope=scope,
    )
    assert item.evidence_level is EvidenceLevel.ACCEPTED
    # config_apply 清单要求 E3；无 APPLY/CELL ON 时，即使 E2 回读匹配也不能
    # 满足 formal scope，最终必须降为 unknown。
    assert item.verdict is EvidenceVerdict.UNKNOWN


def test_uxm_scope_mismatch_forces_unknown_even_when_values_look_good():
    scope = evaluate_catalog_scope(
        load_p0_5_catalog(CATALOG).entries["uxm.config_apply"],
        _env(app="LTE_NR_IRAT"),
    )
    item = build_uxm_evidence(
        evidence_key="uxm.config_apply",
        requested={"arfcn": 636666},
        command_exchange=_exchange(
            "set", "BSE:CONF:NR5G:CELL1:DL:ARFCN 636666", result_type="ok", response=None
        ),
        readback_exchange=_exchange(
            "read", "BSE:CONF:NR5G:CELL1:DL:ARFCN?", response="636666"
        ),
        apply_exchange=_exchange(
            "apply", "BSE:CONF:NR5G:APPLY", result_type="ok", response=None
        ),
        protocol_state_exchange=_exchange(
            "state", "BSE:STATUS:NR5G:CELL1?", response="CONNECTED"
        ),
        scope=scope,
    )
    assert item.verdict is EvidenceVerdict.UNKNOWN
    assert "test_application" in item.reason


def test_uxm_positive_valid_throughput_is_e4_and_zero_is_rejected():
    scope = evaluate_catalog_scope(
        load_p0_5_catalog(CATALOG).entries["uxm.dl_throughput"],
        _env(app="5G_NR_Test"),
    )
    positive = build_uxm_throughput_evidence(
        requested={"direction_deg": 90.0},
        throughput_exchange=_exchange(
            "tput",
            "BSE:MEAS:NR5G:BTHR:DL:THR:OTA:CELL1?",
            response="1000,1000000,900000,1100000,1000000,1000000",
        ),
        scope=scope,
    )
    assert positive.evidence_level is EvidenceLevel.OUTCOME
    assert positive.verdict is EvidenceVerdict.PASSED

    zero = build_uxm_throughput_evidence(
        requested={"direction_deg": 90.0},
        throughput_exchange=_exchange(
            "tput-zero",
            "BSE:MEAS:NR5G:BTHR:DL:THR:OTA:CELL1?",
            response="1000,0,0,0,0,0",
        ),
        scope=scope,
    )
    assert zero.evidence_level is EvidenceLevel.OUTCOME
    assert zero.verdict is EvidenceVerdict.REJECTED


def test_positioner_requires_calibrated_offset_and_feedback_tolerance():
    uncalibrated = build_positioner_evidence(
        requested_angle_deg=200.0,
        coordinate_offset_deg=90.0,
        offset_calibrated=False,
        tolerance_deg=1.0,
        move_exchange=_exchange("move", "MOVEABS X 110.0000 XF5.0000"),
        feedback_exchange=_exchange(
            "feedback", "PFBK(X)", response="200.2", operation="query"
        ),
        scope=_positioner_scope(),
    )
    assert uncalibrated.evidence_level is EvidenceLevel.ACCEPTED
    assert uncalibrated.verdict is EvidenceVerdict.UNKNOWN

    calibrated = build_positioner_evidence(
        requested_angle_deg=200.0,
        coordinate_offset_deg=90.0,
        offset_calibrated=True,
        tolerance_deg=1.0,
        move_exchange=_exchange("move", "MOVEABS X 110.0000 XF5.0000"),
        feedback_exchange=_exchange(
            "feedback", "PFBK(X)", response="200.2", operation="query"
        ),
        scope=_positioner_scope(),
    )
    assert calibrated.readback["expected_program_angle_deg"] == pytest.approx(110.0)
    assert calibrated.readback["actual_program_angle_deg"] == pytest.approx(110.0)
    assert calibrated.readback["raw_feedback_angle_deg"] == pytest.approx(200.2)
    assert calibrated.readback["program_error_deg"] == pytest.approx(0.0)
    assert calibrated.readback["feedback_error_deg"] == pytest.approx(0.2)
    assert calibrated.evidence_level is EvidenceLevel.APPLIED
    assert calibrated.verdict is EvidenceVerdict.PASSED

    outside = build_positioner_evidence(
        requested_angle_deg=200.0,
        coordinate_offset_deg=90.0,
        offset_calibrated=True,
        tolerance_deg=1.0,
        move_exchange=_exchange("move", "MOVEABS X 110.0000 XF5.0000"),
        feedback_exchange=_exchange(
            "feedback", "PFBK(X)", response="202.0", operation="query"
        ),
        scope=_positioner_scope(),
    )
    assert outside.verdict is EvidenceVerdict.REJECTED

    wrong_program = build_positioner_evidence(
        requested_angle_deg=200.0,
        coordinate_offset_deg=90.0,
        offset_calibrated=True,
        tolerance_deg=1.0,
        move_exchange=_exchange("move", "MOVEABS X 200.0000 XF5.0000"),
        feedback_exchange=_exchange(
            "feedback", "PFBK(X)", response="200.0", operation="query"
        ),
        scope=_positioner_scope(),
    )
    assert wrong_program.verdict is EvidenceVerdict.REJECTED
    assert "program_target" in wrong_program.reason

    malformed_feedback = build_positioner_evidence(
        requested_angle_deg=200.0,
        coordinate_offset_deg=90.0,
        offset_calibrated=True,
        tolerance_deg=1.0,
        move_exchange=_exchange("move", "MOVEABS X 110.0000 XF5.0000"),
        feedback_exchange=_exchange(
            "feedback", "PFBK(X)", response="not-a-number", operation="query"
        ),
        scope=_positioner_scope(),
    )
    assert malformed_feedback.verdict is EvidenceVerdict.UNKNOWN
    assert malformed_feedback.reason == "position_feedback_not_numeric"


def test_f64_good_looking_values_cannot_skip_transport_evidence():
    scope = evaluate_catalog_scope(
        load_p0_5_catalog(CATALOG).entries["f64.simulation_state"], _env()
    )
    item = build_f64_evidence(
        evidence_key="f64.simulation_state",
        requested={"model": "CDL-C"},
        preclear_exchanges=[
            _exchange("preclear", "SYST:ERR?", response='0,"No error"')
        ],
        command_exchange=None,
        opc_exchange=_exchange("opc", "*OPC?", response="1"),
        error_exchange=_exchange("err", "SYST:ERR?", response='0,"No error"'),
        readback_exchange=_exchange(
            "readback", "DIAG:SIMU:MOD:STATE?", response="CDL-C"
        ),
        state_exchange=_exchange("state", "DIAG:SIMU:STATE?", response="RUNNING"),
        scope=scope,
    )
    assert item.evidence_level is EvidenceLevel.INTENT
    assert item.verdict is EvidenceVerdict.UNKNOWN


def test_exchange_from_another_instrument_cannot_be_cross_wired():
    scope = evaluate_catalog_scope(
        load_p0_5_catalog(CATALOG).entries["f64.simulation_state"], _env()
    )
    item = build_f64_evidence(
        evidence_key="f64.simulation_state",
        requested={"model": "CDL-C"},
        preclear_exchanges=[
            _exchange("preclear", "SYST:ERR?", response='0,"No error"')
        ],
        command_exchange=_exchange(
            "set",
            "DIAG:SIMU:GO",
            result_type="ok",
            response=None,
            instrument_id="some-other-f64",
        ),
        opc_exchange=_exchange("opc", "*OPC?", response="1"),
        error_exchange=_exchange("err", "SYST:ERR?", response='0,"No error"'),
        readback_exchange=_exchange(
            "read", "DIAG:SIMU:MOD:STATE?", response="CDL-C"
        ),
        state_exchange=_exchange("state", "DIAG:SIMU:STATE?", response="RUNNING"),
        scope=scope,
    )
    assert item.verdict is EvidenceVerdict.UNKNOWN
    assert "instrument" in item.reason


def test_f64_post_error_queue_is_not_attributable_without_clean_preclear():
    scope = evaluate_catalog_scope(
        load_p0_5_catalog(CATALOG).entries["f64.center_frequency"], _env()
    )
    item = build_f64_evidence(
        evidence_key="f64.center_frequency",
        requested={"frequency_mhz": 3600},
        preclear_exchanges=[],
        command_exchange=_exchange(
            "set", "CALC:FILT:CENT:CHAN 1,3600", result_type="ok", response=None
        ),
        opc_exchange=_exchange("opc", "*OPC?", response="1"),
        error_exchange=_exchange("err", "SYST:ERR?", response='0,"No error"'),
        readback_exchange=_exchange(
            "read", "CALC:FILT:CENT:CHAN? 1", response="3600"
        ),
        state_exchange=None,
        scope=scope,
    )
    assert item.verdict is EvidenceVerdict.UNKNOWN
    assert "preclear" in item.reason


def test_unparseable_no_error_text_does_not_count_as_clean_queue():
    scope = evaluate_catalog_scope(
        load_p0_5_catalog(CATALOG).entries["f64.center_frequency"], _env()
    )
    item = build_f64_evidence(
        evidence_key="f64.center_frequency",
        requested={"frequency_mhz": 3600},
        preclear_exchanges=[
            _exchange("preclear", "SYST:ERR?", response="garbled No error text")
        ],
        command_exchange=_exchange(
            "set", "CALC:FILT:CENT:CHAN 1,3600", result_type="ok", response=None
        ),
        opc_exchange=_exchange("opc", "*OPC?", response="1"),
        error_exchange=_exchange("err", "SYST:ERR?", response="garbled No error text"),
        readback_exchange=_exchange(
            "read", "CALC:FILT:CENT:CHAN? 1", response="3600"
        ),
        state_exchange=None,
        scope=scope,
    )
    assert item.verdict is EvidenceVerdict.UNKNOWN
    assert "preclear" in item.reason


def test_uxm_good_looking_values_cannot_skip_transport_evidence():
    scope = evaluate_catalog_scope(
        load_p0_5_catalog(CATALOG).entries["uxm.config_apply"],
        _env(app="5G_NR_Test"),
    )
    item = build_uxm_evidence(
        evidence_key="uxm.config_apply",
        requested={"arfcn": 636666},
        command_exchange=None,
        readback_exchange=_exchange(
            "read", "CONF:NR5G:CELL0:DL:ARFCN?", response="636666"
        ),
        apply_exchange=_exchange(
            "apply", "BSE:CONF:NR5G:APPLY", result_type="ok", response=None
        ),
        protocol_state_exchange=_exchange(
            "state", "BSE:STATUS:NR5G:CELL0?", response="CONNECTED"
        ),
        scope=scope,
    )
    assert item.evidence_level is EvidenceLevel.INTENT
    assert item.verdict is EvidenceVerdict.UNKNOWN


def test_one_exchange_cannot_impersonate_multiple_uxm_stages():
    scope = evaluate_catalog_scope(
        load_p0_5_catalog(CATALOG).entries["uxm.config_apply"],
        _env(app="5G_NR_Test"),
    )
    reused = _exchange("same", "BSE:CONF:NR5G:APPLY", response="CONNECTED")
    item = build_uxm_evidence(
        evidence_key="uxm.config_apply",
        requested={"arfcn": 636666},
        command_exchange=reused,
        readback_exchange=reused,
        apply_exchange=reused,
        protocol_state_exchange=reused,
        scope=scope,
    )
    assert item.verdict is EvidenceVerdict.UNKNOWN
    assert "duplicate" in item.reason


def test_unrelated_queries_cannot_impersonate_applied_state_or_feedback():
    f64_scope = evaluate_catalog_scope(
        load_p0_5_catalog(CATALOG).entries["f64.simulation_state"], _env()
    )
    f64_item = build_f64_evidence(
        evidence_key="f64.simulation_state",
        requested={"model": "CDL-C"},
        preclear_exchanges=[
            _exchange("preclear", "SYST:ERR?", response='0,"No error"')
        ],
        command_exchange=_exchange(
            "set", "DIAG:SIMU:GO", result_type="ok", response=None
        ),
        opc_exchange=_exchange("opc", "*OPC?", response="1"),
        error_exchange=_exchange("err", "SYST:ERR?", response='0,"No error"'),
        readback_exchange=_exchange(
            "read", "DIAG:SIMU:MOD:STATE?", response="CDL-C"
        ),
        state_exchange=_exchange("wrong-state", "READ?", response="RUNNING"),
        scope=f64_scope,
    )
    assert f64_item.evidence_level is EvidenceLevel.ACCEPTED

    uxm_scope = evaluate_catalog_scope(
        load_p0_5_catalog(CATALOG).entries["uxm.config_apply"],
        _env(app="5G_NR_Test"),
    )
    uxm_item = build_uxm_evidence(
        evidence_key="uxm.config_apply",
        requested={"arfcn": 636666},
        command_exchange=_exchange(
            "set-u", "CONF:NR5G:CELL0:DL:ARFCN 636666", result_type="ok", response=None
        ),
        readback_exchange=_exchange(
            "read-u", "CONF:NR5G:CELL0:DL:ARFCN?", response="636666"
        ),
        apply_exchange=_exchange(
            "wrong-apply", "CONF:DISPLAY ON", result_type="ok", response=None
        ),
        protocol_state_exchange=_exchange(
            "state-u", "BSE:STATUS:NR5G:CELL0?", response="CONNECTED"
        ),
        scope=uxm_scope,
    )
    assert uxm_item.evidence_level is EvidenceLevel.ACCEPTED

    positioner_item = build_positioner_evidence(
        requested_angle_deg=0.0,
        coordinate_offset_deg=90.0,
        offset_calibrated=True,
        tolerance_deg=1.0,
        move_exchange=_exchange("move-role", "MOVEABS X 90.0000"),
        feedback_exchange=_exchange("wrong-feedback", "VFBK(X)?", response="90.2"),
        scope=_positioner_scope(),
    )
    assert positioner_item.evidence_level is EvidenceLevel.ACCEPTED
    assert positioner_item.verdict is EvidenceVerdict.UNKNOWN


def test_confirmed_readback_mismatch_is_rejected_not_unknown():
    f64_scope = evaluate_catalog_scope(
        load_p0_5_catalog(CATALOG).entries["f64.center_frequency"], _env()
    )
    f64_item = build_f64_evidence(
        evidence_key="f64.center_frequency",
        requested={"frequency_mhz": 3600},
        preclear_exchanges=[
            _exchange("preclear", "SYST:ERR?", response='0,"No error"')
        ],
        command_exchange=_exchange(
            "set", "CALC:FILT:CENT:CHAN 1,3600", result_type="ok", response=None
        ),
        opc_exchange=_exchange("opc", "*OPC?", response="1"),
        error_exchange=_exchange("err", "SYST:ERR?", response='0,"No error"'),
        readback_exchange=_exchange("read", "CALC:FILT:CENT:CHAN? 1", response="3550"),
        state_exchange=None,
        scope=f64_scope,
    )
    assert f64_item.verdict is EvidenceVerdict.REJECTED
    assert "readback_mismatch" in f64_item.reason

    uxm_scope = evaluate_catalog_scope(
        load_p0_5_catalog(CATALOG).entries["uxm.config_readback"],
        _env(app="5G_NR_Test"),
    )
    uxm_item = build_uxm_evidence(
        evidence_key="uxm.config_readback",
        requested={"arfcn": 636666},
        command_exchange=_exchange(
            "set", "CONF:NR5G:CELL0:DL:ARFCN 636666", result_type="ok", response=None
        ),
        readback_exchange=_exchange(
            "read", "CONF:NR5G:CELL0:DL:ARFCN?", response="640000"
        ),
        apply_exchange=None,
        protocol_state_exchange=None,
        scope=uxm_scope,
    )
    assert uxm_item.verdict is EvidenceVerdict.REJECTED
    assert "readback_mismatch" in uxm_item.reason

    mismatch_with_apply = build_uxm_evidence(
        evidence_key="uxm.config_apply",
        requested={"arfcn": 636666},
        command_exchange=_exchange(
            "set-2", "CONF:NR5G:CELL0:DL:ARFCN 636666", result_type="ok", response=None
        ),
        readback_exchange=_exchange(
            "read-2", "CONF:NR5G:CELL0:DL:ARFCN?", response="640000"
        ),
        apply_exchange=_exchange(
            "apply-2", "BSE:CONF:NR5G:APPLY", result_type="ok", response=None
        ),
        protocol_state_exchange=_exchange(
            "state-2", "BSE:STATUS:NR5G:CELL0?", response="CONNECTED"
        ),
        scope=evaluate_catalog_scope(
            load_p0_5_catalog(CATALOG).entries["uxm.config_apply"],
            _env(app="5G_NR_Test"),
        ),
    )
    assert mismatch_with_apply.evidence_level is EvidenceLevel.ACCEPTED
    assert mismatch_with_apply.verdict is EvidenceVerdict.REJECTED
    assert "readback_mismatch" in mismatch_with_apply.reason


def test_positioner_device_rejection_is_explicitly_rejected():
    item = build_positioner_evidence(
        requested_angle_deg=90.0,
        coordinate_offset_deg=0.0,
        offset_calibrated=True,
        tolerance_deg=1.0,
        move_exchange=_exchange(
            "move", "MOVEABS X 90.0000", result_type="device_rejected", response="!42"
        ),
        feedback_exchange=None,
        scope=_positioner_scope(),
    )
    assert item.verdict is EvidenceVerdict.REJECTED
    assert "device_rejected" in item.reason


def test_positioner_feedback_cannot_skip_move_transport_evidence():
    item = build_positioner_evidence(
        requested_angle_deg=0.0,
        coordinate_offset_deg=90.0,
        offset_calibrated=True,
        tolerance_deg=1.0,
        move_exchange=None,
        feedback_exchange=_exchange(
            "feedback", "PFBK(X)", response="90.1", operation="query"
        ),
        scope=_positioner_scope(),
    )
    assert item.evidence_level is EvidenceLevel.INTENT
    assert item.verdict is EvidenceVerdict.UNKNOWN


def test_driver_builders_bind_semantics_to_their_own_live_environment():
    f64 = RealPropsimF64Driver("f64-bound", {})
    f64._visa_resource = object()
    f64._status = InstrumentStatus.READY
    f64._identity_response = "Keysight,F8800A,SN-F64,9.8.7"
    f64.product_family = "PROPSIM F64"
    f64.firmware_version = "9.8.7"
    def f64_ref(exchange_id, command, **kwargs):
        return _exchange(
            exchange_id, command, instrument_id=f64.instrument_id, **kwargs
        )
    f64_item = f64.build_p0_5_command_evidence(
        evidence_key="f64.simulation_state",
        requested={"model": "CDL-C"},
        preclear_exchanges=[
            f64_ref("preclear", "SYST:ERR?", response='0,"No error"')
        ],
        command_exchange=f64_ref(
            "set", "DIAG:SIMU:GO", result_type="ok", response=None
        ),
        opc_exchange=f64_ref("opc", "*OPC?", response="1"),
        error_exchange=f64_ref("err", "SYST:ERR?", response='0,"No error"'),
        readback_exchange=f64_ref(
            "model", "DIAG:SIMU:MOD:STATE?", response="CDL-C"
        ),
        state_exchange=f64_ref("state", "DIAG:SIMU:STATE?", response="RUNNING"),
    )
    assert f64_item.verdict is EvidenceVerdict.PASSED
    assert f64_item.evidence_level is EvidenceLevel.APPLIED

    uxm = RealUxmDriver("uxm-bound", {})
    uxm._visa_session = object()
    uxm._status = InstrumentStatus.READY
    uxm._identity_response = "Keysight,E7515B,SN-UXM,28.21.0.32"
    uxm._platform_identity_response = (
        "Keysight,E7515B Platform,SN-HW,3.39.0.2"
    )
    uxm.detected_test_app = "LTE_NR_IRAT"
    def uxm_ref(exchange_id, command, **kwargs):
        return _exchange(
            exchange_id, command, instrument_id=uxm.instrument_id, **kwargs
        )
    uxm_item = uxm.build_p0_5_config_evidence(
        evidence_key="uxm.config_apply",
        requested={"arfcn": 636666},
        command_exchange=uxm_ref(
            "set", "BSE:CONF:NR5G:CELL1:DL:ARFCN 636666", result_type="ok", response=None
        ),
        readback_exchange=uxm_ref(
            "read", "BSE:CONF:NR5G:CELL1:DL:ARFCN?", response="636666"
        ),
        apply_exchange=uxm_ref(
            "apply", "BSE:CONF:NR5G:APPLY", result_type="ok", response=None
        ),
        protocol_state_exchange=uxm_ref(
            "state", "BSE:STATUS:NR5G:CELL1?", response="CONNECTED"
        ),
    )
    assert uxm_item.verdict is EvidenceVerdict.UNKNOWN
    assert "test_application" in uxm_item.reason

    uxm.detected_test_app = "5G_NR_Test"
    tput_item = uxm.build_p0_5_throughput_evidence(
        requested={"direction_deg": 0.0},
        throughput_exchange=uxm_ref(
            "tput",
            "BSE:MEAS:NR5G:BTHR:DL:THR:OTA:CELL1?",
            response="1000,1200000,1100000,1300000,1200000,1200000",
        ),
    )
    assert tput_item.evidence_level is EvidenceLevel.OUTCOME
    assert tput_item.verdict is EvidenceVerdict.PASSED


def test_positioner_driver_builder_refuses_formal_green_without_live_identity():
    driver = RealAerotechDriver("turntable-bound", {})
    driver._reader = object()
    driver._writer = object()
    driver._status = InstrumentStatus.READY
    item = driver.build_p0_5_position_evidence(
        requested_angle_deg=0.0,
        coordinate_offset_deg=90.0,
        offset_calibrated=True,
        tolerance_deg=1.0,
        move_exchange=_exchange(
            "move", "MOVEABS X -90.0000", instrument_id=driver.instrument_id
        ),
        feedback_exchange=_exchange(
            "feedback",
            "PFBK(X)",
            response="0.1",
            instrument_id=driver.instrument_id,
            operation="query",
        ),
    )
    assert item.evidence_level is EvidenceLevel.APPLIED
    assert item.verdict is EvidenceVerdict.UNKNOWN
    assert "missing_model_or_firmware" in item.reason


def test_positioner_real_settle_poll_interleaving_can_reach_e3():
    move = _exchange(
        "move-real", "MOVEABS X -90.0000", result_type="ok", response=None
    )
    _exchange(
        "settle-real", "AXISSTATUS(X)", response="4", operation="query"
    )
    feedback = _exchange(
        "feedback-real", "PFBK(X)", response="0.1", operation="query"
    )
    item = build_positioner_evidence(
        requested_angle_deg=0.0,
        coordinate_offset_deg=90.0,
        offset_calibrated=True,
        tolerance_deg=1.0,
        move_exchange=move,
        feedback_exchange=feedback,
        scope=_positioner_scope(),
    )
    assert item.evidence_level is EvidenceLevel.APPLIED
    assert item.verdict is EvidenceVerdict.PASSED
    assert item.exchange_ids == ["move-real", "feedback-real"]


def test_confirmed_catalog_source_kind_is_allowlisted_per_instrument():
    raw = json.loads(CATALOG.read_text(encoding="utf-8"))
    raw["commands"][0]["source"]["kind"] = "runtime-config-claim"
    with pytest.raises(ValueError, match="source kind"):
        validate_catalog_document(raw)


def test_unrelated_commands_cannot_impersonate_f64_or_uxm_stages():
    f64_scope = evaluate_catalog_scope(
        load_p0_5_catalog(CATALOG).entries["f64.simulation_state"], _env()
    )
    f64_item = build_f64_evidence(
        evidence_key="f64.simulation_state",
        requested={"model": "CDL-C"},
        preclear_exchanges=[_exchange("p", "FOO:ERRCOUNT?", response="0")],
        command_exchange=_exchange("c", "*CLS", result_type="ok", response=None),
        opc_exchange=_exchange("o", "*OPC?", response="1"),
        error_exchange=_exchange("e", "FOO:ERRCOUNT?", response="0"),
        readback_exchange=_exchange(
            "r", "RANDOM?", response="CDL-C"
        ),
        state_exchange=_exchange(
            "s", "DIAG:SIMU:MODEL:STATE?", response="RUNNING"
        ),
        scope=f64_scope,
    )
    assert f64_item.verdict is EvidenceVerdict.UNKNOWN

    uxm_scope = evaluate_catalog_scope(
        load_p0_5_catalog(CATALOG).entries["uxm.config_apply"],
        _env(app="5G_NR_Test"),
    )
    uxm_item = build_uxm_evidence(
        evidence_key="uxm.config_apply",
        requested={"arfcn": 636666},
        command_exchange=_exchange("uc", "DISPLAY ON", result_type="ok", response=None),
        readback_exchange=_exchange("ur", "READ?", response="636666"),
        apply_exchange=_exchange(
            "ua", "SYST:DISPLAY:APPLY", result_type="ok", response=None
        ),
        protocol_state_exchange=_exchange(
            "us", "BSE:STATUS:LTE:CELL0?", response="CONNECTED"
        ),
        scope=uxm_scope,
    )
    assert uxm_item.verdict is EvidenceVerdict.UNKNOWN


def test_verdict_values_are_parsed_from_exchange_response_not_caller_claims():
    throughput_scope = evaluate_catalog_scope(
        load_p0_5_catalog(CATALOG).entries["uxm.dl_throughput"],
        _env(app="5G_NR_Test"),
    )
    throughput = build_uxm_throughput_evidence(
        requested={"direction_deg": 0.0},
        throughput_exchange=_exchange(
            "t",
            "BSE:MEAS:NR5G:BTHR:DL:THR:OTA:CELL1?",
            response="1000,0,0,0,0,0",
        ),
        scope=throughput_scope,
    )
    assert throughput.verdict is EvidenceVerdict.REJECTED
    assert throughput.readback["throughput_bps"] == 0.0

    position = build_positioner_evidence(
        requested_angle_deg=0.0,
        coordinate_offset_deg=90.0,
        offset_calibrated=True,
        tolerance_deg=1.0,
        move_exchange=_exchange("m", "MOVEABS X 90.0000", result_type="ok"),
        feedback_exchange=_exchange(
            "f", "PFBK(X)", response="999", operation="query"
        ),
        scope=_positioner_scope(),
    )
    assert position.verdict is EvidenceVerdict.REJECTED
    assert position.readback["raw_feedback_angle_deg"] == 999.0


def test_readback_must_match_the_value_actually_sent_on_the_wire():
    f64_scope = evaluate_catalog_scope(
        load_p0_5_catalog(CATALOG).entries["f64.center_frequency"], _env()
    )
    f64_item = build_f64_evidence(
        evidence_key="f64.center_frequency",
        requested={"frequency_mhz": 3600},
        preclear_exchanges=[_exchange("fp", "SYST:ERR?", response="0")],
        command_exchange=_exchange(
            "fc", "CALC:FILT:CENT:CHAN 1,3550", result_type="ok", response=None
        ),
        opc_exchange=_exchange("fo", "*OPC?", response="1"),
        error_exchange=_exchange("fe", "SYST:ERR?", response="0"),
        readback_exchange=_exchange(
            "fr", "CALC:FILT:CENT:CHAN? 1", response="3550"
        ),
        state_exchange=None,
        scope=f64_scope,
    )
    assert f64_item.verdict is EvidenceVerdict.REJECTED
    assert f64_item.readback["expected"] == 3600

    uxm_scope = evaluate_catalog_scope(
        load_p0_5_catalog(CATALOG).entries["uxm.config_readback"],
        _env(app="5G_NR_Test"),
    )
    uxm_item = build_uxm_evidence(
        evidence_key="uxm.config_readback",
        requested={"arfcn": 636666},
        command_exchange=_exchange(
            "uc", "CONF:NR5G:CELL0:DL:ARFCN 640000", result_type="ok", response=None
        ),
        readback_exchange=_exchange(
            "ur", "CONF:NR5G:CELL0:DL:ARFCN?", response="640000"
        ),
        apply_exchange=None,
        protocol_state_exchange=None,
        scope=uxm_scope,
    )
    assert uxm_item.verdict is EvidenceVerdict.REJECTED
    assert uxm_item.readback["expected"] == 636666


def test_uxm_readback_must_query_the_same_configuration_path_that_was_written():
    scope = evaluate_catalog_scope(
        load_p0_5_catalog(CATALOG).entries["uxm.config_readback"],
        _env(app="5G_NR_Test"),
    )
    item = build_uxm_evidence(
        evidence_key="uxm.config_readback",
        requested={"arfcn": 636666},
        command_exchange=_exchange(
            "c", "CONF:NR5G:CELL0:DL:ARFCN 636666", result_type="ok", response=None
        ),
        readback_exchange=_exchange(
            "r", "CONF:NR5G:CELL0:BAND?", response="636666"
        ),
        apply_exchange=None,
        protocol_state_exchange=None,
        scope=scope,
    )
    assert item.verdict is EvidenceVerdict.UNKNOWN
    assert "role_mismatch" in item.reason


def test_evidence_rejects_cross_execution_and_out_of_order_refs():
    scope = evaluate_catalog_scope(
        load_p0_5_catalog(CATALOG).entries["f64.simulation_state"], _env()
    )

    def tagged(
        exchange_id, command, sequence, execution_id="test-execution", **kwargs
    ):
        return _exchange(exchange_id, command, **kwargs).model_copy(
            update={
                "capture_id": "capture-1",
                "execution_id": execution_id,
                "sequence": sequence,
            }
        )

    cross_execution = build_f64_evidence(
        evidence_key="f64.simulation_state",
        requested={"model": "CDL-C"},
        preclear_exchanges=[tagged("p", "SYST:ERR?", 0, response="0")],
        command_exchange=tagged(
            "c", "DIAG:SIMU:GO", 1, result_type="ok", response=None
        ),
        opc_exchange=tagged("o", "*OPC?", 2, response="1"),
        error_exchange=tagged(
            "e", "SYST:ERR?", 3, execution_id="old-run", response="0"
        ),
        readback_exchange=tagged(
            "r", "DIAG:SIMU:MOD:STATE?", 4, response="CDL-C"
        ),
        state_exchange=tagged("s", "DIAG:SIMU:STATE?", 5, response="RUNNING"),
        scope=scope,
    )
    assert cross_execution.verdict is EvidenceVerdict.UNKNOWN
    assert "execution" in cross_execution.reason

    all_from_old_execution = build_f64_evidence(
        evidence_key="f64.simulation_state",
        requested={"model": "CDL-C"},
        preclear_exchanges=[
            tagged("old-p", "SYST:ERR?", 0, execution_id="old-run", response="0")
        ],
        command_exchange=tagged(
            "old-c",
            "DIAG:SIMU:GO",
            1,
            execution_id="old-run",
            result_type="ok",
            response=None,
        ),
        opc_exchange=tagged(
            "old-o", "*OPC?", 2, execution_id="old-run", response="1"
        ),
        error_exchange=tagged(
            "old-e", "SYST:ERR?", 3, execution_id="old-run", response="0"
        ),
        readback_exchange=tagged(
            "old-r",
            "DIAG:SIMU:MOD:STATE?",
            4,
            execution_id="old-run",
            response="CDL-C",
        ),
        state_exchange=tagged(
            "old-s",
            "DIAG:SIMU:STATE?",
            5,
            execution_id="old-run",
            response="RUNNING",
        ),
        scope=scope,
    )
    assert all_from_old_execution.verdict is EvidenceVerdict.UNKNOWN
    assert "execution" in all_from_old_execution.reason

    out_of_order = build_f64_evidence(
        evidence_key="f64.simulation_state",
        requested={"model": "CDL-C"},
        preclear_exchanges=[tagged("p2", "SYST:ERR?", 0, response="0")],
        command_exchange=tagged(
            "c2", "DIAG:SIMU:GO", 3, result_type="ok", response=None
        ),
        opc_exchange=tagged("o2", "*OPC?", 2, response="1"),
        error_exchange=tagged("e2", "SYST:ERR?", 4, response="0"),
        readback_exchange=tagged(
            "r2", "DIAG:SIMU:MOD:STATE?", 5, response="CDL-C"
        ),
        state_exchange=tagged("s2", "DIAG:SIMU:STATE?", 6, response="RUNNING"),
        scope=scope,
    )
    assert out_of_order.verdict is EvidenceVerdict.UNKNOWN
    assert "order" in out_of_order.reason

    interleaved = build_f64_evidence(
        evidence_key="f64.simulation_state",
        requested={"model": "CDL-C"},
        preclear_exchanges=[tagged("p3", "SYST:ERR?", 0, response="0")],
        command_exchange=tagged(
            "c3", "DIAG:SIMU:GO", 1, result_type="ok", response=None
        ),
        opc_exchange=tagged("o3", "*OPC?", 3, response="1"),
        error_exchange=tagged("e3", "SYST:ERR?", 4, response="0"),
        readback_exchange=tagged(
            "r3", "DIAG:SIMU:MOD:STATE?", 5, response="CDL-C"
        ),
        state_exchange=tagged("s3", "DIAG:SIMU:STATE?", 6, response="RUNNING"),
        scope=scope,
    )
    assert interleaved.verdict is EvidenceVerdict.UNKNOWN
    assert "interleaved" in interleaved.reason


def test_query_spelling_cannot_impersonate_a_command_role():
    scope = evaluate_catalog_scope(
        load_p0_5_catalog(CATALOG).entries["f64.simulation_state"], _env()
    )
    preclear = _exchange("p", "SYST:ERR?", response="0")
    query_as_command = _exchange(
        "c", "DIAG:SIMU:GO?", result_type="ok", response=None
    ).model_copy(update={"operation": "command"})
    item = build_f64_evidence(
        evidence_key="f64.simulation_state",
        requested={"model": "CDL-C"},
        preclear_exchanges=[preclear],
        command_exchange=query_as_command,
        opc_exchange=_exchange("o", "*OPC?", response="1"),
        error_exchange=_exchange("e", "SYST:ERR?", response="0"),
        readback_exchange=_exchange(
            "r", "DIAG:SIMU:MOD:STATE?", response="CDL-C"
        ),
        state_exchange=_exchange("s", "DIAG:SIMU:STATE?", response="RUNNING"),
        scope=scope,
    )
    assert item.verdict is EvidenceVerdict.UNKNOWN
    assert "role_mismatch" in item.reason


def test_mandatory_level_and_later_device_rejection_override_earlier_acceptance():
    f64_scope = evaluate_catalog_scope(
        load_p0_5_catalog(CATALOG).entries["f64.simulation_state"], _env()
    )
    missing_state = build_f64_evidence(
        evidence_key="f64.simulation_state",
        requested={"model": "CDL-C"},
        preclear_exchanges=[_exchange("p", "SYST:ERR?", response="0")],
        command_exchange=_exchange("c", "DIAG:SIMU:GO", result_type="ok", response=None),
        opc_exchange=_exchange("o", "*OPC?", response="1"),
        error_exchange=_exchange("e", "SYST:ERR?", response="0"),
        readback_exchange=_exchange(
            "r", "DIAG:SIMU:MOD:STATE?", response="CDL-C"
        ),
        state_exchange=None,
        scope=f64_scope,
    )
    assert missing_state.evidence_level is EvidenceLevel.ACCEPTED
    assert missing_state.verdict is EvidenceVerdict.UNKNOWN

    uxm_scope = evaluate_catalog_scope(
        load_p0_5_catalog(CATALOG).entries["uxm.config_apply"],
        _env(app="5G_NR_Test"),
    )
    rejected_apply = build_uxm_evidence(
        evidence_key="uxm.config_apply",
        requested={"arfcn": 636666},
        command_exchange=_exchange(
            "uc", "CONF:NR5G:CELL0:DL:ARFCN 636666", result_type="ok", response=None
        ),
        readback_exchange=_exchange(
            "ur", "CONF:NR5G:CELL0:DL:ARFCN?", response="636666"
        ),
        apply_exchange=_exchange(
            "ua", "BSE:CONF:NR5G:APPLY", result_type="device_rejected", response="-113"
        ),
        protocol_state_exchange=None,
        scope=uxm_scope,
    )
    assert rejected_apply.verdict is EvidenceVerdict.REJECTED


def test_uxm_reconnect_paths_clear_stale_evidence_identity():
    class Session:
        def close(self):
            return None

    class ResourceManager:
        def open_resource(self, *_args, **_kwargs):
            return Session()

    driver = RealUxmDriver("uxm-reconnect", {})
    driver._visa_rm = ResourceManager()
    driver._visa_session = Session()
    driver._active_resource_string = "TCPIP::uxm::hislip2::INSTR"
    driver._identity_response = "Keysight,E7515B,SN,FW"
    driver._platform_identity_response = "Keysight,E7515B Platform,SN,HW"
    driver.detected_test_app = "5G_NR_Test"
    assert driver._silent_reconnect_visa() is True
    assert driver._identity_response is None
    assert driver._platform_identity_response is None
    assert driver.detected_test_app is None


@pytest.mark.asyncio
@pytest.mark.parametrize("reopen_succeeds", [True, False])
async def test_f64_reconnect_paths_clear_stale_evidence_identity(reopen_succeeds):
    class Session:
        def close(self):
            return None

    class ResourceManager:
        def open_resource(self, *_args, **_kwargs):
            if not reopen_succeeds:
                raise OSError("reopen failed")
            return Session()

    driver = RealPropsimF64Driver("f64-reconnect", {"ip_address": "192.0.2.64"})
    driver._rm = ResourceManager()
    driver._visa_resource = Session()
    driver._status = InstrumentStatus.READY
    driver._identity_response = "Spirent,PROPSIM F64,SN-OLD,FW-OLD"
    driver.sys_info = F64SysInfo(
        raw="PROPSIM F64,64,RF,FW-OLD",
        product_family="PROPSIM F64",
        firmware_version="FW-OLD",
        band_label="OLD-BAND",
    )
    driver.product_family = "PROPSIM F64"
    driver.firmware_version = "FW-OLD"
    driver.band_label = "OLD-BAND"

    assert await driver._silent_reconnect_visa() is reopen_succeeds
    assert driver._identity_response is None
    assert driver.sys_info is None
    assert driver.product_family is None
    assert driver.firmware_version is None
    assert driver.band_label is None
    assert driver.capture_evidence_environment().captured_from_live_connection is False


def test_positioner_uses_circular_error_and_caps_formal_tolerance_at_one_degree():
    ack_prefixed = build_positioner_evidence(
        requested_angle_deg=0.0,
        coordinate_offset_deg=90.0,
        offset_calibrated=True,
        tolerance_deg=1.0,
        move_exchange=_exchange("ack-m", "MOVEABS X -90", result_type="ok"),
        feedback_exchange=_exchange(
            "ack-f", "PFBK(X)", response="%0.2", operation="query"
        ),
        scope=_positioner_scope(),
    )
    assert ack_prefixed.verdict is EvidenceVerdict.PASSED
    assert ack_prefixed.readback["raw_feedback_angle_deg"] == pytest.approx(0.2)

    wrapped = build_positioner_evidence(
        requested_angle_deg=0.0,
        coordinate_offset_deg=0.0,
        offset_calibrated=True,
        tolerance_deg=1.0,
        move_exchange=_exchange("m1", "MOVEABS X 0", result_type="ok"),
        feedback_exchange=_exchange(
            "f1", "PFBK(X)", response="359.8", operation="query"
        ),
        scope=_positioner_scope(),
    )
    assert wrapped.verdict is EvidenceVerdict.PASSED
    assert wrapped.readback["feedback_error_deg"] == pytest.approx(0.2)

    cannot_relax = build_positioner_evidence(
        requested_angle_deg=0.0,
        coordinate_offset_deg=0.0,
        offset_calibrated=True,
        tolerance_deg=20.0,
        move_exchange=_exchange("m2", "MOVEABS X 0", result_type="ok"),
        feedback_exchange=_exchange(
            "f2", "PFBK(X)", response="10", operation="query"
        ),
        scope=_positioner_scope(),
    )
    assert cannot_relax.verdict is EvidenceVerdict.REJECTED
    assert cannot_relax.readback["tolerance_deg"] == 1.0
