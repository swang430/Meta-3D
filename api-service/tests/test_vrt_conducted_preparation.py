import pytest

from tests.test_road_test_executions import _isolated_db

ROOT = "/api/v1/road-test"


def test_unready_draft_roundtrip(client):
    selection = {"scenario_id": client.get(ROOT + "/scenarios").json()[0]["id"]}
    preview = client.post(ROOT + "/conducted/prepare", json=selection)
    assert preview.status_code == 200
    snapshot = preview.json()
    assert snapshot["ready"] is False and len(snapshot["reasons"]) >= 3
    saved = client.post(ROOT + "/conducted/executions", json=selection)
    assert saved.status_code == 201
    url = ROOT + "/executions/" + saved.json()["execution_id"]
    assert client.get(url).json()["config"]["conducted"] == snapshot
    assert client.post(url + "/control", json={"action": "start"}).status_code == 409
    assert client.get(url).json()["status"] == "idle"


@pytest.mark.parametrize("physical", [False, True])
def test_verified_selection_and_changed_wiring(client, sample_topology_data, monkeypatch, tmp_path, physical):
    from types import SimpleNamespace
    from uuid import uuid4

    from app.api import road_test_conducted as api
    from app.models.channel_asset import ChannelAsset
    from app.models.lab_profile import LabProfile
    from tests.test_road_test_executions import _TestingSessionLocal
    from tests.test_smu_project_inventory import _OLD_SCD

    scenario = client.get(ROOT + "/scenarios").json()[0]
    scenario = client.get(ROOT + "/scenarios/" + scenario["id"]).json()
    if physical:
        scenario["network"].update(band="n78", bandwidth_mhz=100)
        scenario["base_stations"] = scenario["base_stations"][:1]
        scenario["step_configuration"] = None
        scenario = client.post(ROOT + "/scenarios", json=scenario).json()
    data = sample_topology_data
    data["base_station"]["tx_ports"] = data["channel_emulator"]["input_ports"] = 4
    for i in (3, 4):
        data["connections"].append(dict(data["connections"][0], connection_id=f"bs-{i}", source_port=i, target_port=i))
    topology = client.post(ROOT + "/topologies", json=data).json()["id"]
    assert client.post(ROOT + "/topologies/" + topology + "/validate").is_success
    digest = "ab" * 32
    path = "route.smu"
    connection, model = uuid4(), uuid4()
    monkeypatch.setattr(api, "resolve_channel_emulator_binding", lambda *args: SimpleNamespace(
        execution_mode="real" if physical else "simulated", status="configured", binding_digest="a" * 64,
        instrument_model_id=str(model), instrument_connection_id=str(connection)))
    if physical:
        monkeypatch.setattr(api, "resolve_base_station_binding", lambda *_: SimpleNamespace(
            execution_mode="real", status="configured", binding_digest="b" * 64, instrument_connection_id=str(uuid4())))
    mapping = [dict(tx=tx, rx=rx, input_port=tx, output_port=rx) for tx in range(1, 5) for rx in (1, 2)]
    preview = client.post(ROOT + "/conducted/prepare", json={"scenario_id": scenario["id"]}).json()
    with _TestingSessionLocal() as db:
        asset = ChannelAsset(name="已扫描工程", source_type="vendor_file", allowed_targets=["gcm_native"],
                             associated_file_path=path, instrument_connection_id=connection, instrument_model_id=model,
                             center_frequency_hz=3600000000, payload={"scd_config": dict(_OLD_SCD, mimo="4x2"),
                             "smu_project_truth": {"schema_version": 1, "primary_group": 0, "sha256": digest,
                             "size_bytes": 10, "instrument_path": path, "center_frequencies_hz": {"0": 3600000000}}})
        db.add(asset)
        db.flush()
        selection = dict(scenario_id=scenario["id"], topology_id=topology, asset_id=str(asset.id), direction="downlink")
        registration = dict(selection, scenario_sha256=preview["scenario_sha256"], scenario_version=scenario["version"], sha256=digest, port_mapping=mapping)
        lab = LabProfile(name="实验室", extra_metadata={"vrt_conducted": [registration]})
        db.add(lab)
        db.commit()
        selection["lab_profile_id"] = str(lab.id)
        choices = client.get(ROOT + "/conducted/options").json()
        for key, field in (("labs", "lab_profile_id"), ("assets", "asset_id"), ("topologies", "topology_id")):
            assert selection[field] in {r["id"] for r in choices[key]}
        if physical:
            import json
            from tests.test_vrt_port_calibration import _site_files
            monkeypatch.setenv("VRT_CALIBRATION_APPROVED_DIR", str(tmp_path))
            current = client.post(ROOT + "/conducted/prepare", json=selection).json()
            assert not current["ready"]
            scope = current["binding"]["real_preflight"]["calibration"]["scope"]
            doc, _ = _site_files(tmp_path)
            doc["scope"] = scope
            for port in doc["ports"]:
                port.update(tx_reference_plane=f'{scope["base_station_id"]}/out/{port["tx"]}',
                            emulator_input_reference_plane=f'{scope["channel_emulator_id"]}/in/{port["input_port"]}',
                            emulator_output_reference_plane=f'{scope["channel_emulator_id"]}/out/{port["output_port"]}',
                            dut_reference_plane=f'{scope["dut_id"]}/in/{port["rx"]}')
            (tmp_path / "report.json").write_text(json.dumps(doc))
            imported = client.post(ROOT + "/conducted/calibrations", json={"report_file": "report.json"})
            assert imported.status_code == 201, imported.text
            selection["calibration_id"] = imported.json()["id"]
        saved = client.post(ROOT + "/conducted/executions", json=selection).json()["config"]["conducted"]
        assert saved["ready"] is physical, saved["reasons"]
        if not physical:
            assert any("模拟专用播放清单" in r for r in saved["reasons"])
        assert saved["asset"]["sha256"] == digest and saved["port_mapping"] == mapping
        limited = client.post(ROOT + "/conducted/prepare", json={
            **selection, "test_settings": {"traffic": {"type": "ftp", "direction": "DL"}, "playback_seconds": 0.5}
        }).json()
        assert not limited["ready"] and any("仅模拟清单" in reason for reason in limited["reasons"])
        if physical:
            calibration = saved["binding"]["real_preflight"]["calibration"]
            assert calibration["applicable"] and len(calibration["ports"]) == 8
            assert {(p["output_port"], p["emulator_output_setting_dbm"], p["emulator_output_dbm"])
                    for p in calibration["ports"]} == {(1, -17, -9), (2, -18, -10)}
            client.post(ROOT + "/conducted/calibrations/" + selection["calibration_id"] + "/revoke",
                        json={"reason": "更换物理电缆"})
            changed = client.post(ROOT + "/conducted/prepare", json=selection).json()
            assert not changed["ready"] and "更换物理电缆" in str(changed["reasons"])
        mapping[0]["input_port"] = 2
        lab.extra_metadata = {"vrt_conducted": [dict(registration, port_mapping=mapping)]}
        from sqlalchemy.orm.attributes import flag_modified
        flag_modified(lab, "extra_metadata")
        db.commit()
        preview = client.post(ROOT + "/conducted/prepare", json=selection).json()
        assert not preview["ready"] and any("电缆" in r for r in preview["reasons"])
        history = client.get(ROOT + "/executions?mode=conducted").json()
        assert history[0]["conducted"] == saved


def test_mock_asset_checks_each_file_before_use(tmp_path):
    import hashlib
    import json
    from app.api import road_test_conducted as api
    links = []
    for tx in range(4):
        for rx in range(2):
            name = f"R0B0S0D_TX{tx}_RX{rx}_H.asc"
            (tmp_path / name).write_bytes(name.encode())
            links.append(dict(tx=tx, rx=rx, file=name, sha256=hashlib.sha256(name.encode()).hexdigest()))
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps(dict(mode="conducted", direction="downlink", links=links)))
    asset = api.mock_asset(tmp_path, "测试资产")
    assert asset["mock_only"] and asset["links"] == links and "instrument_path" not in asset
    (tmp_path / links[0]["file"]).write_bytes(b"changed")
    import pytest
    with pytest.raises(ValueError, match="摘要"):
        api.mock_asset(tmp_path, "测试资产")


def test_prepare_digest_ignores_record_timestamps(client):
    template = client.get(ROOT + "/scenarios").json()[0]["id"]
    body = client.get(ROOT + "/scenarios/" + template).json()
    body["name"] = "仅更新记录时间"
    scenario = client.post(ROOT + "/scenarios", json=body).json()
    selection = {"scenario_id": scenario["id"]}
    before = client.post(ROOT + "/conducted/prepare", json=selection).json()
    assert before["scenario_snapshot"] == {
        k: v for k, v in scenario.items() if k not in ("created_at", "updated_at")
    }
    from datetime import datetime
    from uuid import UUID
    from app.models.test_plan import TestCase
    from tests.test_road_test_executions import _TestingSessionLocal
    with _TestingSessionLocal() as db:
        case = db.get(TestCase, UUID(scenario["id"]))
        case.updated_at = datetime(2030, 1, 2)
        db.commit()
    after = client.post(ROOT + "/conducted/prepare", json=selection).json()
    assert after["scenario_sha256"] == before["scenario_sha256"]


def test_two_business_settings_freeze_separately_without_editing_the_road_scene(client):
    scenario_id = client.get(ROOT + "/scenarios").json()[0]["id"]
    original = client.get(f"{ROOT}/scenarios/{scenario_id}").json()
    saved = []
    for business, rate in (("video", 20), ("ftp", 50)):
        settings = {"traffic": {"type": business, "direction": "DL", "data_rate_mbps": rate}}
        response = client.post(ROOT + "/conducted/executions",
                               json={"scenario_id": scenario_id, "test_settings": settings})
        assert response.status_code == 201, response.text
        saved.append(response.json()["execution_id"])
    for execution, expected in zip(saved, ("video", "ftp")):
        frozen = client.get(f"{ROOT}/executions/{execution}").json()["config"]["conducted"]
        assert frozen["test_settings"]["traffic"]["type"] == expected
        assert frozen["scenario_snapshot"]["traffic"] == original["traffic"]
    assert client.get(f"{ROOT}/scenarios/{scenario_id}").json()["traffic"] == original["traffic"]


def test_prepare_rejects_missing_road_project(client, monkeypatch, tmp_path):
    from app.api import mpdb_projects
    monkeypatch.setattr(mpdb_projects, "_scene_library", lambda: tmp_path)
    scenario = client.get(ROOT + "/scenarios").json()[0]["id"]
    request = {"scenario_id": scenario, "road_project": {"source_sha256": "a"*64, "version": "b"*64}}
    response = client.post(ROOT + "/conducted/prepare", json=request)
    assert response.status_code == 200
    preview = response.json()
    assert not preview["ready"] and any("道路工程无法核对" in reason for reason in preview["reasons"])
