from copy import deepcopy
from datetime import datetime
from types import SimpleNamespace
from dataclasses import asdict

import pytest

from app.services.mimo_ota.executors.report import _build_mimo_ota_content_data
from app.services.base_station_adapter_profile import FREEZE_CONFIG_KEY
from app.hal.base_station_compatibility import canonical_payload_digest
from app.schemas.mimo_ota.config import MIMOOTAConfiguration, dump_canonical_mimo_ota_configuration
from tests.test_p2_66_execution_evidence_outcome import _freeze
from tests.test_p2_66_execution_evidence_outcome import _modern_uxm_mac_evidence
from tests.test_p2_21_report_flags_cert_cjk import _rendered_text
from tests.test_p2_59_channel_emulator_execution_plan import db


def _execution(frozen=None):
    return SimpleNamespace(
        id="execution-1", config={FREEZE_CONFIG_KEY: frozen} if frozen else {},
        measurements={"phases": {"measure": {"sampling": {"num_windows_per_azimuth": 3}}}},
        status="completed", started_at=datetime(2026, 10, 7),
        completed_at=datetime(2026, 10, 7, 0, 1, 30), duration_sec=90.0,
        validation_pass=None,
    )


def test_frozen_parameters_reach_pdf_and_existing_gui_step_configs_without_secrets():
    frozen = _freeze(no_adapter=True)
    frozen["mimo_ota_configuration"] = dump_canonical_mimo_ota_configuration(
        MIMOOTAConfiguration.model_validate(frozen["mimo_ota_configuration"])
    )
    frozen["digest"] = canonical_payload_digest({k: v for k, v in frozen.items() if k != "digest"})
    ex = _execution(frozen)
    ex.config["sim_credentials"] = {"ki": "SECRET-NOT-FOR-REPORT"}
    content = _build_mimo_ota_content_data(ex, datetime.utcnow(), "one shot")
    audit = content["execution_traceability"]
    assert audit["parameters"]["azimuths_deg"]["requested"] == [0, 90, 180, 270]
    assert audit["parameters"]["mac_profile.profile.statistical_window.count"]["requested"] == 5000
    assert audit["parameters"]["azimuths_deg"]["source"] == "untraceable"
    assert audit["execution_mode"] == "simulated"
    assert audit["duration_s"] == 90
    assert audit["recorded_window_count"] is None  # 不借 sampling 把计划数冒充实际
    assert "SECRET-NOT-FOR-REPORT" not in str(content)
    text = _rendered_text(content)
    assert "5000" in text
    assert "冻结请求参数" in text
    assert "来源不可追溯" in text
    assert content["step_configs"][0]["parameters"] == content["step_results"][0]["parameters"]


@pytest.mark.parametrize("kind", ["missing", "tampered", "malformed"])
def test_unavailable_freeze_never_fills_defaults(kind):
    frozen = _freeze(no_adapter=True)
    if kind == "missing":
        frozen = None
    elif kind == "tampered":
        frozen["mimo_ota_configuration"]["power_dbm"] = 123
    else:
        frozen["mimo_ota_configuration"] = []
        frozen["digest"] = canonical_payload_digest({k: v for k, v in frozen.items() if k != "digest"})
    ex = _execution(frozen)
    ex.test_case = SimpleNamespace(configuration={"power_dbm": 999})
    audit = _build_mimo_ota_content_data(ex, datetime.utcnow())["execution_traceability"]
    assert audit["parameters"] == {}
    assert audit["status"] == "unavailable"
    assert "999" not in str(audit)


def _windows_execution():
    from app.services.mimo_ota.executors.measure import _build_pcell_requested_config
    from app.services.mimo_ota.base_station_execution_evidence import canonical_snapshot_digest

    f = _freeze()
    cfg = MIMOOTAConfiguration.model_validate(f["mimo_ota_configuration"])
    cfg.azimuths_deg = [0]
    f["mimo_ota_configuration"] = dump_canonical_mimo_ota_configuration(cfg)
    f["digest"] = canonical_payload_digest({k: v for k, v in f.items() if k != "digest"})
    ex = _execution(f)
    evidence = _modern_uxm_mac_evidence()
    evidence["measurement_window_contract_version"] = 1
    payload = asdict(_build_pcell_requested_config(cfg))
    evidence["requested_config"] = {"payload": payload, "digest": canonical_snapshot_digest(payload)}
    windows = []
    for i in range(3):
        w = deepcopy(evidence["measurement_windows"][0])
        w.update(window_id=f"window-{i}", config_digest=evidence["requested_config"]["digest"],
                 started_at=f"2026-10-07T00:00:{10 + i * 5:02}Z", completed_at=f"2026-10-07T00:00:{15 + i * 5:02}Z")
        req = {"schema_version": 1, "scope": "pcell", "lifecycle": "authoritative_closed",
               "cardinality": "requested", "requested_window_count": 3,
               "expected_window_count": 3, "window_index": i, "statistical_basis_subframes": 5000}
        w["trust"] = {"schema_version": 1, "request": req, "request_digest": canonical_snapshot_digest(req),
                      "simulated": False, "exchange_ids": [], "reason": "fixture", "context_confirmed": False,
                      "stages": [{"stage": s, "status": "unknown", "reason": "fixture", "exchange_ids": []}
                                 for s in ("clear", "run", "ready", "closed")]}
        windows.append(w)
    evidence["measurement_windows"] = windows
    ex.config["base_station_execution_evidence"] = evidence
    return ex


def test_window_summary_uses_current_attempt_records_not_legacy_sampling_count():
    ex = _windows_execution()
    audit = _build_mimo_ota_content_data(ex, datetime.utcnow())["execution_traceability"]
    assert audit["requested_windows_per_azimuth"] == 100
    assert audit["recorded_window_count"] == 3
    assert audit["window_elapsed_s"] == 15
    assert audit["window_plan"][0] == {"azimuth_deg": 0.0, "requested": 3, "planned": 3, "recorded": 3}


@pytest.mark.parametrize("drift", ["execution", "connection", "adapter", "attempt", "config", "duplicate"])
def test_wrong_scope_windows_cannot_be_reported_as_this_execution(drift):
    ex = _windows_execution()
    e = ex.config["base_station_execution_evidence"]
    if drift == "execution":
        e["execution_id"] = "another-execution"
    elif drift == "connection":
        e["identity"]["instrument_connection_id"] = "another-connection"
    elif drift == "adapter":
        e["adapter"] = "cmw500"
    elif drift == "attempt":
        e["current_measurement_attempt_id"] = "another-attempt"
    elif drift == "config":
        e["measurement_windows"][0]["config_digest"] = "bad"
    else:
        e["measurement_windows"].append(deepcopy(e["measurement_windows"][0]))
    audit = _build_mimo_ota_content_data(ex, datetime.utcnow())["execution_traceability"]
    assert audit["recorded_window_count"] is None


def test_asset_label_and_path_are_captured_once_not_looked_up_by_report(monkeypatch):
    from uuid import uuid4
    from app.services.mimo_ota import channel_asset_resolver
    from app.services.channel_emulator_execution_plan import freeze_channel_asset_resolution

    asset = SimpleNamespace(id=uuid4(), name="LTE 文件名称自选", canonical_name="LTE_2x2",
                            source_type="custom_static", associated_file_path="frozen.smu")
    monkeypatch.setattr(channel_asset_resolver, "resolve_channel_asset",
                        lambda *_: SimpleNamespace(asset=asset))
    asset_freeze = freeze_channel_asset_resolution(object(), SimpleNamespace(channel_asset_id=asset.id))
    f = _windows_execution().config[FREEZE_CONFIG_KEY]
    f["mimo_ota_configuration"]["channel_asset_id"] = str(asset.id)
    f["channel_asset_resolution"] = asset_freeze
    f["digest"] = canonical_payload_digest({k: v for k, v in f.items() if k != "digest"})
    asset.name, asset.associated_file_path = "后来修改", "current.smu"
    audit = _build_mimo_ota_content_data(_execution(f), datetime.utcnow())["execution_traceability"]
    assert audit["channel_asset"]["name"] == "LTE 文件名称自选"
    assert audit["channel_asset"]["associated_file_path"] == "frozen.smu"
    assert "后来修改" not in str(audit)


@pytest.mark.parametrize("simulated", [False, True])
def test_applied_field_is_separate_from_request_and_mock_never_confirmed(simulated):
    ex = _windows_execution()
    e = ex.config["base_station_execution_evidence"]
    w = e["measurement_windows"][0]
    e["adapter_operations"] = [{
        "schema_version": 1, "measurement_attempt_id": e["current_measurement_attempt_id"],
        "lease_id": w["lease_id"], "adapter": e["adapter"], "session_token": w["session_token"],
        "operation": "config", "frozen_request_digest": e["requested_config"]["digest"],
        "fields": [{"field": "bandwidth_mhz", "requested": 100.0, "applied": 100.0,
                    "status": "confirmed", "reason": "readback", "exchange_ids": ["config-1"]}],
        "confirmed": not simulated, "simulated": simulated, "reason": "readback", "exchange_ids": ["config-1"],
    }]
    e["exchange_ids"].append("config-1")
    audit = _build_mimo_ota_content_data(ex, datetime.utcnow())["execution_traceability"]
    field = audit["application_fields"]["config.bandwidth_mhz"]
    assert field["requested"] == 100.0
    assert field["applied"] == (None if simulated else 100.0)
    assert field["status"] == ("unknown" if simulated else "confirmed")


def test_report_distinguishes_configured_engine_from_asset_resolved_load_request(db, monkeypatch):
    from uuid import uuid4
    from tests.test_p2_59_channel_emulator_execution_plan import _execution as ce_execution, _configuration, _hal, _f64
    from app.services.mimo_ota import channel_asset_resolver
    from app.services.channel_emulator_execution_plan import freeze_channel_asset_resolution, freeze_channel_emulator_execution_plan
    from app.services.mimo_ota.report_traceability import report_traceability

    asset_id = uuid4()
    configuration = _configuration("keysight_gcm")
    configuration["channel_asset_id"] = str(asset_id)
    ex = ce_execution(db, configuration=configuration)
    monkeypatch.setattr(channel_asset_resolver, "resolve_channel_asset", lambda *_: SimpleNamespace(
        asset=SimpleNamespace(id=asset_id, source_type="standard_3gpp", name="自选名称"), engine_mode="mimo_first_asc"))
    f = ex.config[FREEZE_CONFIG_KEY]
    f["channel_asset_resolution"] = freeze_channel_asset_resolution(db, MIMOOTAConfiguration.model_validate(configuration))
    f["digest"] = canonical_payload_digest({k: v for k, v in f.items() if k != "digest"})
    ex.config = {**ex.config, FREEZE_CONFIG_KEY: f}
    freeze_channel_emulator_execution_plan(db, _hal(_f64()), ex)
    audit = report_traceability(ex, None)
    assert audit["parameters"]["engine_mode"]["requested"] == "keysight_gcm"
    assert audit["channel_load_request"]["effective_engine_mode"] == "mimo_first_asc"
    assert audit["channel_load_request"]["requested_load_mode"] == "external_waveform"
    # 损坏请求不得由配置中的引擎补真。
    ex.config["channel_emulator_load_request_freeze"]["effective_engine_mode"] = "keysight_gcm"
    assert report_traceability(ex, None)["channel_load_request"] is None


def test_historical_null_carriers_are_not_replaced_by_parser_defaults():
    from app.services.mimo_ota.report_traceability import report_traceability
    f = _windows_execution().config[FREEZE_CONFIG_KEY]
    f["mimo_ota_configuration"]["component_carriers"] = None
    f["digest"] = canonical_payload_digest({k: v for k, v in f.items() if k != "digest"})
    audit = report_traceability(_execution(f), None)
    assert audit["parameters"]["component_carriers"]["requested"] is None
    assert "component_carriers.0.frequency_hz" not in audit["parameters"]


def test_f64_power_request_is_reported_without_inventing_applied_power():
    from app.services.mimo_ota.report_traceability import report_traceability
    f = _windows_execution().config[FREEZE_CONFIG_KEY]
    f["mimo_ota_configuration"]["f64_input_ref_dbm"] = -17
    f["digest"] = canonical_payload_digest({k: v for k, v in f.items() if k != "digest"})
    audit = report_traceability(_execution(f), None)
    assert audit["parameters"]["f64_input_ref_dbm"]["requested"] == -17
    assert not audit.get("application_fields")


def test_window_provenance_reads_each_window_not_execution_mode():
    from app.services.mimo_ota.report_traceability import report_traceability
    ex = _windows_execution()
    ex.config["base_station_execution_evidence"]["measurement_windows"][0]["trust"]["simulated"] = True
    assert report_traceability(ex, 90)["window_provenance"] == "mixed"


def test_one_lease_readback_does_not_confirm_all_window_leases():
    from app.services.mimo_ota.report_traceability import report_traceability
    ex = _windows_execution()
    e = ex.config["base_station_execution_evidence"]
    for w in e["measurement_windows"][1:]:
        w.update(lease_id="lease-2", session_token="session-2")
    release = deepcopy(e["control_releases"][0])
    release.update(lease_id="lease-2", session_token="session-2")
    e["control_releases"].append(release)
    e["adapter_operations"] = [{
        "schema_version": 1, "measurement_attempt_id": "attempt-1", "lease_id": "lease-1",
        "adapter": "uxm", "session_token": "session-1", "operation": "config",
        "frozen_request_digest": e["requested_config"]["digest"],
        "fields": [{"field": "bandwidth_mhz", "requested": 100.0, "applied": 100.0,
                    "status": "confirmed", "reason": "readback", "exchange_ids": ["config-1"]}],
        "confirmed": True, "simulated": False, "reason": "readback", "exchange_ids": ["config-1"],
    }]
    e["exchange_ids"].append("config-1")
    row = report_traceability(ex, 90)["application_fields"]["config.bandwidth_mhz"]
    assert row["status"] == "unknown"
    assert row["applied"] is None


def test_legacy_scd_file_is_frozen_and_reported_without_current_lookup(monkeypatch):
    from uuid import uuid4
    from app.services import channel_emulator_execution_plan as ce
    from app.services import channel_asset_ownership
    from app.services.mimo_ota.report_traceability import report_traceability
    source = SimpleNamespace(id=uuid4(), standard_name="LTE 旧文件", associated_file_path="legacy.smu",
                             instrument_connection_id=uuid4(), instrument_model_id=uuid4())
    monkeypatch.setattr(ce, "_legacy_channel_file_source", lambda *_: (source, {"associated_file_path": source.associated_file_path}))
    monkeypatch.setattr(channel_asset_ownership, "validate_channel_asset_owner", lambda *_: None)
    cfg = SimpleNamespace(channel_asset_id=None, engine_mode="keysight_gcm", scd_id=source.id)
    frozen_file = ce.freeze_legacy_channel_file_resolution(object(), cfg)
    f = _windows_execution().config[FREEZE_CONFIG_KEY]
    f["mimo_ota_configuration"].update(engine_mode="keysight_gcm", scd_id=str(source.id))
    f[ce.LEGACY_CHANNEL_FILE_RESOLUTION_FREEZE_KEY] = frozen_file
    f["digest"] = canonical_payload_digest({k: v for k, v in f.items() if k != "digest"})
    source.associated_file_path = "current.smu"
    audit = report_traceability(_execution(f), None)
    assert audit["channel_asset"]["associated_file_path"] == "legacy.smu"
    assert audit["channel_asset"]["name"] == "LTE 旧文件"


def test_full_supported_azimuth_audit_does_not_create_oversized_pdf_row(tmp_path):
    from app.services.mimo_ota.report_traceability import report_traceability_parameters
    content = _build_mimo_ota_content_data(_windows_execution(), datetime.utcnow())
    audit = content["execution_traceability"]
    audit["parameters"]["azimuths_deg"]["requested"] = list(range(361))
    audit["window_plan"] = [{"azimuth_deg": float(i), "requested": 3, "planned": 3, "recorded": 3} for i in range(361)]
    params = report_traceability_parameters(audit)
    content["step_results"][0]["parameters"] = params
    content["step_configs"][0]["parameters"] = params
    from app.services.pdf_generator import PDFGenerator
    output = tmp_path / "report.pdf"
    PDFGenerator().generate_report(content, None, str(output))
    assert output.read_bytes().startswith(b"%PDF")
    text = _rendered_text(content)
    assert "360" in text


def test_sources_follow_carrier_and_lte_frame_authoring_not_invented_defaults():
    from app.services.mimo_ota.report_traceability import capture_report_sources, _source
    origin = capture_report_sources("LTE", {
        "component_carriers": [{"duplex": "tdd", "lte_transmission_mode": "TM3", "subcarrier_spacing_khz": 30}],
        "lte_tdd_frame_structure": {"uldl_configuration": 2, "special_subframe": 7, "rmc_version": "REL8"},
    })
    paths = set(origin["saved_paths"])
    for field in ("duplex", "transmission_mode", "subcarrier_spacing_khz", "uldl_configuration", "special_subframe", "rmc_version"):
        assert _source(f"mac_profile.profile.{field}", paths) == "saved_configuration"
    assert _source("mac_profile.profile.tdd_period", {"tdd_pattern"}) == "derived"
