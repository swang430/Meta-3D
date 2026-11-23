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


def test_verified_selection_and_changed_wiring(client, sample_topology_data, monkeypatch):
    from types import SimpleNamespace
    from uuid import uuid4

    from app.api import road_test_conducted as api
    from app.models.channel_asset import ChannelAsset
    from app.models.lab_profile import LabProfile
    from tests.test_road_test_executions import _TestingSessionLocal
    from tests.test_smu_project_inventory import _OLD_SCD

    scenario = client.get(ROOT + "/scenarios").json()[0]
    scenario = client.get(ROOT + "/scenarios/" + scenario["id"]).json()
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
        execution_mode="simulated", status="configured", binding_digest="test",
        instrument_model_id=str(model), instrument_connection_id=str(connection)))
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
        saved = client.post(ROOT + "/conducted/executions", json=selection).json()["config"]["conducted"]
        assert saved["ready"], saved["reasons"]
        assert saved["asset"]["sha256"] == digest and saved["port_mapping"] == mapping
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
