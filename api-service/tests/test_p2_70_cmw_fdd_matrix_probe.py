"""P2-70: real diagnostic path, only transport/storage replaced; no RF activation."""
import asyncio
from types import SimpleNamespace

import pytest

from app.diagnostics import loader
from app.hal.cmw500_base_station import RealCmw500Driver
from app.hal.cmw500_command_profile import Cmw500LteCommandProfile
from app.services.base_station_binding import resolve_base_station_binding
from tests.test_p2_44_base_station_binding_resolver import db, _configured


ROOT = "CONFigure:LTE:SIGN1:CONNection:PCC:"


class Transport:
    def __init__(self):
        self.commands = []
        self.overrides = {}
        self.state = {
            ROOT + "STYPe": "RMC",
            ROOT + "RMC:RBPosition:DL1": "LOW",
            ROOT + "RMC:RBPosition:DL2": "LOW",
            ROOT + "RMC:RBPosition:UL": "LOW",
            ROOT + "DLEQual": "ON",
            ROOT + "TRANsmission": "TM3",
            ROOT + "NENBantennas": "TWO",
            ROOT + "DCIFormat": "D2A",
            ROOT + "RMC:DL1": "N100,Q16,T13",
            ROOT + "RMC:DL2": "N100,Q16,T13",
            ROOT + "RMC:UL": "N100,QPSK,T2",
        }

    def write(self, command):
        self.commands.append(command)
        header, value = command.split(" ", 1)
        self.state[header] = value

    def query(self, command):
        self.commands.append(command)
        if command in self.overrides:
            value = self.overrides[command]
            if isinstance(value, BaseException):
                raise value
            return value
        fixed = {
            "*IDN?": "Rohde&Schwarz,CMW,123456,4.0.250",
            "SYSTem:BASE:OPTion:LIST? SWOPtion,VALid": "KS500,KS520",
            "SYSTem:BASE:OPTion:LIST? HWOPtion,FUNCtional": "",
            "SYSTem:ERRor:ALL?": '0,"No error"', "*OPC?": "1",
            "SOURce:LTE:SIGN1:CELL:STATe:ALL?": "OFF,ADJ",
            "CONFigure:LTE:SIGN1:DMODe?": "FDD",
            "CONFigure:LTE:SIGN1:CELL:BANDwidth:DL?": "B200",
            "ROUTe:LTE:SIGN1?": "TRO,RESERVED,RF1C,RX1,RF1C,TX1,RF2C,TX2",
            "ROUTe:LTE:SIGN1:SCENario:TRO:FLEXible?": "BB1,RF1C,RX1,RF1C,TX1,RF2C,TX2",
            ROOT + "MCLuster:UL?": "OFF",
        }
        if command in fixed:
            return fixed[command]
        if command.endswith("?") and command[:-1] in self.state:
            return self.state[command[:-1]]
        raise AssertionError(f"Unscripted command: {command}")


@pytest.fixture
def rig(db, monkeypatch):
    _, _, _, lab = _configured(db, model_name="CMW500")
    driver = RealCmw500Driver("cmw", {"ip_address": "192.0.2.10"})
    driver._visa_session = object()
    driver._identity_model = "CMW"
    driver._identity_model_verified = True
    driver._firmware_version = "4.0.250"
    driver._options_snapshot_verified = True
    driver._installed_options = ["KS500", "KS520"]
    transport = Transport()
    monkeypatch.setattr(driver, "_do_write", transport.write)
    monkeypatch.setattr(driver, "_do_query", transport.query)
    hal = SimpleNamespace(drivers={"baseStation": driver})
    binding = resolve_base_station_binding(db, hal, lab)
    return driver, transport, hal, binding, lab


def test_verified_dci_builder_rejects_outside_probe_domain():
    assert Cmw500LteCommandProfile.build_mac_dci(1, "D1A") == ROOT + "DCIFormat D1A"
    assert Cmw500LteCommandProfile.mac_dci_query(1) == ROOT + "DCIFormat?"
    with pytest.raises(ValueError):
        Cmw500LteCommandProfile.build_mac_dci(1, "D2C")


@pytest.mark.asyncio
@pytest.mark.parametrize("sample,tm,ant,dci,dl", [
    ("tm1_one", "TM1", "ONE", "D1A", "N100,QPSK,T5"),
    ("tm3_two", "TM3", "TWO", "D2A", "N100,Q16,T13"),
])
async def test_samples_are_fixed_diagnostic_rows(rig, sample, tm, ant, dci, dl):
    driver, transport, hal, binding, _ = rig
    # Explicit preexisting device settings; values aren't computed by production builders.
    transport.state.update({
        ROOT + "STYPe": "RMC",
        ROOT + "RMC:RBPosition:DL1": "LOW",
        ROOT + "RMC:RBPosition:DL2": "LOW",
        ROOT + "RMC:RBPosition:UL": "LOW",
        ROOT + "DLEQual": "ON",
    })
    sequence = loader.get_sequence("cmw500_fdd_matrix_probe")
    result = await sequence.run(None, hal, {"sample": sample}, log=lambda _: None,
                                resolved_binding=binding)
    assert result.success, result.summary
    assert transport.state[ROOT + "TRANsmission"] == tm
    assert transport.state[ROOT + "NENBantennas"] == ant
    assert transport.state[ROOT + "DCIFormat"] == dci
    assert transport.state[ROOT + "RMC:DL1"] == dl
    assert result.extra["formal_eligible"] is False
    assert result.extra["cleanup"]["safe_idle"] is True
    assert result.extra["exchanges"]
    assert not any("CELL:STATe ON" in command for command in transport.commands)


@pytest.mark.asyncio
async def test_unknown_sample_cannot_send_any_io(rig):
    _, transport, hal, binding, _ = rig
    result = await loader.get_sequence("cmw500_fdd_matrix_probe").run(
        None, hal, {"sample": "tm1_one", "tbs": 13}, log=lambda _: None,
        resolved_binding=binding)
    assert not result.success
    assert transport.commands == []


@pytest.mark.asyncio
@pytest.mark.parametrize("query,value", [
    ("CONFigure:LTE:SIGN1:DMODe?", "TDD"),
    ("CONFigure:LTE:SIGN1:CELL:BANDwidth:DL?", "B100"),
    ("ROUTe:LTE:SIGN1?", "SAL,RESERVED,RF1C,RX1,RF1C,TX1,RF2C,TX2"),
    ("ROUTe:LTE:SIGN1:SCENario:TRO:FLEXible?", "BB1,RF1C,RX1,RF1C,TX1,RF3C,TX2"),
    (ROOT + "MCLuster:UL?", "ON"),
    ("SYSTem:ERRor:ALL?", '-113,"undefined"'),
    ("SOURce:LTE:SIGN1:CELL:STATe:ALL?", "UNKNOWN"),
    (ROOT + "DCIFormat?", ""),
])
async def test_bad_readback_never_claims_diagnostic_success(rig, query, value):
    _, transport, hal, binding, _ = rig
    transport.overrides[query] = value
    result = await loader.get_sequence("cmw500_fdd_matrix_probe").run(
        None, hal, {"sample": "tm1_one"}, log=lambda _: None, resolved_binding=binding)
    assert not result.success
    assert result.extra["formal_eligible"] is False


@pytest.mark.asyncio
@pytest.mark.parametrize("query", ["ROUTe:LTE:SIGN1?", ROOT + "DCIFormat?"])
async def test_parse_failure_archives_and_consumes_device_error(rig, monkeypatch, query):
    driver, transport, hal, binding, _ = rig
    pending = []
    original = transport.query

    def query_with_error(command):
        if command == query:
            transport.commands.append(command)
            pending.append('-221,"Settings conflict"')
            return ""
        if command == "SYSTem:ERRor:ALL?" and pending:
            transport.commands.append(command)
            return pending.pop()
        return original(command)

    monkeypatch.setattr(driver, "_do_query", query_with_error)
    result = await loader.get_sequence("cmw500_fdd_matrix_probe").run(
        None, hal, {"sample": "tm1_one"}, log=lambda _: None, resolved_binding=binding)
    assert not result.success
    assert not pending
    assert any(step.raw == "" and not step.success for step in result.steps)
    assert any(step.raw == '-221,"Settings conflict"' for step in result.steps)
    assert result.extra["formal_eligible"] is False


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["identity", "firmware", "options", "binding"])
async def test_unverified_identity_or_binding_no_io(rig, change):
    driver, transport, hal, binding, _ = rig
    if change == "identity":
        driver._identity_model_verified = False
    elif change == "firmware":
        driver._firmware_version = "3.5.20"
    elif change == "options":
        driver._installed_options = ["KS500"]
    else:
        binding = None
    result = await loader.get_sequence("cmw500_fdd_matrix_probe").run(
        None, hal, {"sample": "tm1_one"}, log=lambda _: None, resolved_binding=binding)
    assert not result.success
    assert transport.commands == []


@pytest.mark.asyncio
async def test_later_setting_cannot_clobber_final_tuple(rig, monkeypatch):
    driver, transport, hal, binding, _ = rig
    original = transport.write
    def write(command):
        original(command)
        if command == ROOT + "RMC:DL1 N100,QPSK,T5":
            transport.state[ROOT + "DCIFormat"] = "D2A"
    monkeypatch.setattr(driver, "_do_write", write)
    result = await loader.get_sequence("cmw500_fdd_matrix_probe").run(
        None, hal, {"sample": "tm1_one"}, log=lambda _: None, resolved_binding=binding)
    assert not result.success
    assert "最终组合回读漂移" in result.summary
    assert result.extra["cleanup"]["safe_idle"] is True


@pytest.mark.asyncio
async def test_cancel_preserves_partial_commands_and_cleanup(rig, monkeypatch):
    driver, transport, hal, binding, _ = rig
    original = transport.write
    def write(command):
        original(command)
        raise asyncio.CancelledError()
    monkeypatch.setattr(driver, "_do_write", write)
    from app.diagnostics.sequences.cmw500_fdd_matrix_probe import ProbeCancelled
    with pytest.raises(ProbeCancelled) as caught:
        await loader.get_sequence("cmw500_fdd_matrix_probe").run(
            None, hal, {"sample": "tm1_one"}, log=lambda _: None, resolved_binding=binding)
    partial_result = caught.value.result
    assert not partial_result.success
    assert partial_result.extra["partial_result_available"] is True
    assert partial_result.extra["cleanup"]["safe_idle"] is True
    assert any(x["command"] == ROOT + "TRANsmission TM1"
               for x in partial_result.extra["exchanges"])


@pytest.mark.asyncio
async def test_api_uses_binding_and_persists_probe(rig, db, monkeypatch):
    from app.api import diagnostic_sequence as api
    from app.models.diagnostic_run import DiagnosticRun
    from app.services import instrument_test_lease as leases
    driver, transport, hal, _, lab = rig
    driver._session_token = "transport-session"
    driver._visa_session = SimpleNamespace(close=lambda: None)
    monkeypatch.setattr(api, "get_hal_service", lambda: hal)
    monkeypatch.setattr(leases, "_LEASE", leases.InstrumentTestLease(lambda: hal))
    response = await api.run_diagnostic_sequence(
        "cmw500_fdd_matrix_probe",
        api.RunSequenceRequest(lab_profile_id=lab.id, params={"sample": "tm1_one"}), db)
    assert response.success, response.summary
    row = db.get(DiagnosticRun, response.diagnostic_run_id)
    assert row.sequence_evidence["extra"]["binding"]["lab_profile_id"] == str(lab.id)
    assert row.sequence_evidence["extra"]["formal_eligible"] is False
    assert row.sequence_evidence["extra"]["release"]["transport_session_released_confirmed"] is True
    assert row.sequence_evidence["extra"]["exchanges"]
    from app.api.diagnostic_run import get_diagnostic_run
    detail = get_diagnostic_run(row.id, db)
    assert detail.sequence_evidence.model_dump(mode="json") == row.sequence_evidence


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["binding", "params", "cancel", "release"])
async def test_api_failure_retains_truth_and_does_not_leak_guard(rig, db, monkeypatch, failure):
    from app.api import diagnostic_sequence as api
    from app.models.diagnostic_run import DiagnosticRun
    from app.services import instrument_test_lease as leases
    from app.services.execution_exclusion_guard import active_unsafe_diagnostic
    driver, transport, hal, _, lab = rig
    driver._session_token = "transport-session"
    def close():
        if failure == "release":
            raise OSError("transport close failed")
    driver._visa_session = SimpleNamespace(close=close)
    monkeypatch.setattr(api, "get_hal_service", lambda: hal)
    monkeypatch.setattr(leases, "_LEASE", leases.InstrumentTestLease(lambda: hal))
    params = {"sample": "tm1_one"}
    if failure == "binding":
        lab.instrument_bindings = [{**lab.instrument_bindings[0], "connection_endpoint": "192.0.2.99"}]
        db.commit()
    if failure == "params":
        params["sample"] = "tm1_one;*RST"
    if failure == "cancel":
        original = transport.write
        def write(command):
            original(command)
            raise asyncio.CancelledError()
        monkeypatch.setattr(driver, "_do_write", write)
    call = api.run_diagnostic_sequence("cmw500_fdd_matrix_probe",
        api.RunSequenceRequest(lab_profile_id=lab.id, params=params), db)
    if failure == "cancel":
        with pytest.raises(asyncio.CancelledError):
            await call
    else:
        response = await call
        assert not response.success
    row = db.query(DiagnosticRun).one()
    assert not row.success
    assert active_unsafe_diagnostic() is None
    assert row.sequence_evidence["extra"]["formal_eligible"] is False
    if failure in {"binding", "params"}:
        assert transport.commands == []
    else:
        assert row.sequence_evidence["steps"]
        assert row.sequence_evidence["extra"]["exchanges"]
        assert row.sequence_evidence["extra"]["cleanup"]["safe_idle"] is True
        if failure == "release":
            assert row.sequence_evidence["extra"]["release"]["transport_session_released_confirmed"] is False
        else:
            assert row.sequence_evidence["extra"]["partial_result_available"] is True


@pytest.mark.asyncio
async def test_repeat_switch_reads_live_configuration(rig):
    _, transport, hal, binding, _ = rig
    seq = loader.get_sequence("cmw500_fdd_matrix_probe")
    for sample in ("tm1_one", "tm3_two", "tm1_one"):
        result = await seq.run(None, hal, {"sample": sample}, log=lambda _: None,
                               resolved_binding=binding)
        assert result.success, result.summary
    transport.commands.clear()
    result = await seq.run(None, hal, {"sample": "tm1_one"}, log=lambda _: None,
                           resolved_binding=binding)
    assert result.success
    # Unchanged target does not blindly replay setters.
    assert all(command.split(" ", 1)[0].endswith("?") for command in transport.commands)


@pytest.mark.asyncio
@pytest.mark.parametrize("error", ["write_queue", "readback", "timeout", "cleanup"])
async def test_write_failure_never_becomes_clean_success(rig, monkeypatch, error):
    driver, transport, hal, binding, _ = rig
    original = transport.write
    def write(command):
        original(command)
        if error == "write_queue":
            transport.overrides["SYSTem:ERRor:ALL?"] = '-221,"Settings conflict"'
        elif error == "readback":
            transport.state[ROOT + "TRANsmission"] = "TM3"
        elif error == "timeout":
            raise TimeoutError("no reply")
        elif error == "cleanup":
            transport.overrides["SOURce:LTE:SIGN1:CELL:STATe:ALL?"] = "OFF,PEND"
    monkeypatch.setattr(driver, "_do_write", write)
    result = await loader.get_sequence("cmw500_fdd_matrix_probe").run(
        None, hal, {"sample": "tm1_one"}, log=lambda _: None, resolved_binding=binding)
    assert not result.success
    assert result.extra["exchanges"]
    if error == "cleanup":
        assert result.extra["cleanup"]["safe_idle"] is False


@pytest.mark.asyncio
async def test_warm_connection_preserves_current_identity_raw(rig):
    _, _, hal, binding, _ = rig
    result = await loader.get_sequence("cmw500_fdd_matrix_probe").run(
        None, hal, {"sample": "tm1_one"}, log=lambda _: None, resolved_binding=binding)
    assert result.success
    assert any(x["command"] == "*IDN?" and x["response"] == "Rohde&Schwarz,CMW,123456,4.0.250"
               for x in result.extra["exchanges"])


@pytest.mark.asyncio
async def test_warm_identity_drift_refused_before_configuration(rig):
    _, transport, hal, binding, _ = rig
    transport.overrides["*IDN?"] = "Keysight,UXM,123,4.0.250"
    result = await loader.get_sequence("cmw500_fdd_matrix_probe").run(
        None, hal, {"sample": "tm1_one"}, log=lambda _: None, resolved_binding=binding)
    assert not result.success
    assert not any(c.startswith(ROOT) and not c.endswith("?") for c in transport.commands)


@pytest.mark.asyncio
async def test_api_preflight_rejection_does_not_stop_out_of_scope_cell(rig, db, monkeypatch):
    from app.api import diagnostic_sequence as api
    from app.services import instrument_test_lease as leases
    driver, transport, hal, _, lab = rig
    driver._session_token = "transport-session"
    driver._visa_session = SimpleNamespace(close=lambda: None)
    transport.overrides["CONFigure:LTE:SIGN1:DMODe?"] = "TDD"
    transport.overrides["SOURce:LTE:SIGN1:CELL:STATe:ALL?"] = "ON,ADJ"
    original = transport.write
    def write(command):
        original(command)
        if command == "SOURce:LTE:SIGN1:CELL:STATe OFF":
            transport.overrides["SOURce:LTE:SIGN1:CELL:STATe:ALL?"] = "OFF,ADJ"
    monkeypatch.setattr(driver, "_do_write", write)
    monkeypatch.setattr(api, "get_hal_service", lambda: hal)
    monkeypatch.setattr(leases, "_LEASE", leases.InstrumentTestLease(lambda: hal))
    response = await api.run_diagnostic_sequence("cmw500_fdd_matrix_probe",
        api.RunSequenceRequest(lab_profile_id=lab.id, params={"sample": "tm1_one"}), db)
    assert not response.success
    assert transport.overrides["SOURce:LTE:SIGN1:CELL:STATe:ALL?"] == "ON,ADJ"
    assert not any(c == "SOURce:LTE:SIGN1:CELL:STATe OFF" for c in transport.commands)
    assert response.extra["release"] is None


@pytest.mark.asyncio
async def test_api_cold_connect_and_reenter_after_release(rig, db, monkeypatch):
    import pyvisa
    from app.api import diagnostic_sequence as api
    from app.services import instrument_test_lease as leases
    driver, _, hal, _, lab = rig
    driver._visa_session = None
    driver._session_token = None
    opened, closed = [], []
    def open_resource(*args, **kwargs):
        opened.append(args)
        return SimpleNamespace(close=lambda: closed.append(True))
    monkeypatch.setattr(pyvisa, "ResourceManager", lambda: SimpleNamespace(open_resource=open_resource))
    monkeypatch.setattr(api, "get_hal_service", lambda: hal)
    monkeypatch.setattr(leases, "_LEASE", leases.InstrumentTestLease(lambda: hal))
    for sample in ("tm1_one", "tm3_two"):
        response = await api.run_diagnostic_sequence("cmw500_fdd_matrix_probe",
            api.RunSequenceRequest(lab_profile_id=lab.id, params={"sample": sample}), db)
        assert response.success, response.summary
        assert response.extra["release"]["transport_session_released_confirmed"] is True
        assert driver._visa_session is None
    assert len(opened) == len(closed) == 2
