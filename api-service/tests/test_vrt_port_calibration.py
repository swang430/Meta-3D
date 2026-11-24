from tests.test_road_test_executions import _isolated_db

ROOT = "/api/v1/road-test/conducted/calibrations"


def test_calibration_source_and_list(client):
    response = client.get(ROOT)
    assert response.status_code == 200
    assert response.json() == []
    forged = client.post(ROOT, json={"source": "real", "verified": True})
    assert forged.status_code == 422


def _site_files(directory, *, settings=None):
    """软件测试夹具，只写入每个测试自己的临时审核目录。"""
    import csv
    import hashlib
    import json
    from uuid import uuid4

    scope = {"lab_profile_id": str(uuid4()), "topology_id": str(uuid4()), "direction": "downlink",
             "base_station_id": "BS", "channel_emulator_id": "CE", "dut_id": "DUT",
             "center_frequency_hz": 3600000000, "bandwidth_mhz": 100, "tx_power_dbm": -20}
    for key in ("topology_sha256", "scenario_sha256", "asset_sha256", "base_station_binding_digest",
                "channel_emulator_binding_digest"):
        scope[key] = hashlib.sha256(key.encode()).hexdigest()
    doc = dict(schema_version="vrt_conducted_port_calibration_v1", source="physical_instrument_measurement",
               method="all_paths_active_peak_at_input_planes", report_number="fixture-001", issuer="隔离测试",
               meter_serial="meter-fixture", meter_certificate="fixture-cert",
               measured_at="2025-01-01T00:00:00Z", valid_until="2099-01-01T00:00:00Z",
               meter_certificate_expires_at="2100-01-01T00:00:00Z", required_margin_db=3, scope=scope,
               ports=[], readings_file="readings.csv")
    rows = []
    for tx in range(1, 5):
        for rx in range(1, 3):
            mapping = dict(tx=tx, rx=rx, input_port=tx, output_port=rx)
            def measurement(power):
                return dict(peak_dbm=power, max_safe_input_dbm=0, uncertainty_db=1,
                            limit_source="测试限值表", instrument_reply_dbm=str(power))
            doc["ports"].append(dict(**mapping, tx_reference_plane=f"BS/out/{tx}",
                                     emulator_input_reference_plane=f"CE/in/{tx}",
                                     emulator_output_reference_plane=f"CE/out/{rx}", dut_reference_plane=f"DUT/in/{rx}",
                                     emulator_input=measurement(-20-tx), dut_input=measurement(-11-rx)))
            rows.append(dict(**mapping, source=doc["source"], meter_serial=doc["meter_serial"],
                             base_station_output_dbm=-18-tx, emulator_input_dbm=-20-tx,
                             emulator_output_dbm=-8-rx, dut_input_dbm=-11-rx))
    for row in rows:
        setting = -16 - row["output_port"] if settings is None else settings(row)
        if setting is not None:
            row["emulator_output_setting_dbm"] = setting
    readings = directory / doc["readings_file"]
    with readings.open("w") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    doc["readings_sha256"] = hashlib.sha256(readings.read_bytes()).hexdigest()
    (directory / "report.json").write_text(json.dumps(doc))
    return doc, [{k: row[k] for k in ("tx", "rx", "input_port", "output_port")} for row in rows]


def test_site_record_port_evidence_and_revocation(client, monkeypatch, tmp_path):
    from uuid import UUID
    from app.services.road_test.port_calibration import applicability
    from tests.test_road_test_executions import _TestingSessionLocal

    monkeypatch.setenv("VRT_CALIBRATION_APPROVED_DIR", str(tmp_path))
    doc, mapping = _site_files(tmp_path)
    request = {"report_file": "report.json"}
    record = client.post(ROOT, json=request)
    assert record.status_code == 201, record.text
    rid = record.json()["id"]
    assert client.get(ROOT + "/" + rid).json()["readings_b64"]
    with _TestingSessionLocal() as db:
        def check(scope=doc["scope"], paths=mapping):
            return applicability(db, UUID(rid), scope, paths)
        result = check()
        assert result["applicable"], result["reasons"]
        assert [p["base_station_output_dbm"] for p in result["ports"]][::2] == [-19, -20, -21, -22]
        assert all((p["tx_cable_loss_db"], p["rx_cable_loss_db"]) == (2, 3) for p in result["ports"])
        assert {(p["output_port"], p["emulator_output_setting_dbm"], p["emulator_output_dbm"])
                for p in result["ports"]} == {(1, -17, -9), (2, -18, -10)}
        assert result["ports"][0]["dut_input_margin_db"] == 11
        for field in doc["scope"]:
            assert not check({**doc["scope"], field: "changed"})["applicable"]
        assert not check(paths=[dict(mapping[0], input_port=2), *mapping[1:]])["applicable"]
        db.rollback()
        assert client.post(ROOT + "/" + rid + "/revoke", json={"reason": "更换电缆"}).is_success
        assert "更换电缆" in str(check()["reasons"])
    assert client.post(ROOT, json=request).json()["revocation_reason"] == "更换电缆"


def test_untrusted_and_invalid_sources(client, monkeypatch, tmp_path):
    import hashlib
    import json
    from uuid import UUID
    from app.services.road_test.port_calibration import applicability
    from tests.test_road_test_executions import _TestingSessionLocal

    doc, paths = _site_files(tmp_path)
    monkeypatch.delenv("VRT_CALIBRATION_APPROVED_DIR", raising=False)
    def register():
        return client.post(ROOT, json={"report_file": "report.json"})
    assert register().status_code == 422
    monkeypatch.setenv("VRT_CALIBRATION_APPROVED_DIR", str(tmp_path))
    assert client.post(ROOT, json={"report_file": "../report.json"}).status_code == 422
    original = json.dumps(doc)
    for key, value in (("source", "simulated"), ("method", "single_path")):
        (tmp_path / "report.json").write_text(json.dumps({**doc, key: value}))
        assert register().status_code == 422
    (tmp_path / "report.json").write_text(original)
    for field, value in (("valid_until", "2025-02-01T00:00:00Z"), ("required_margin_db", 50)):
        (tmp_path / "report.json").write_text(json.dumps({**doc, "report_number": field, field: value}))
        rid = register().json()["id"]
        with _TestingSessionLocal() as db:
            assert not applicability(db, UUID(rid), doc["scope"], paths)["applicable"]
    doc["ports"][0]["dut_reference_plane"] = "DUT/in/2"
    (tmp_path / "report.json").write_text(json.dumps(doc))
    assert register().status_code == 422
    doc = json.loads(original)
    (tmp_path / "report.json").write_text(original)
    rid = register().json()["id"]
    readings = tmp_path / "readings.csv"
    readings.write_text(readings.read_text().replace("physical_instrument_measurement", "simulated"))
    with _TestingSessionLocal() as db:
        assert not applicability(db, UUID(rid), doc["scope"], paths)["applicable"]
    doc["readings_sha256"] = hashlib.sha256(readings.read_bytes()).hexdigest()
    (tmp_path / "report.json").write_text(json.dumps(doc))
    assert register().status_code == 422



def test_legacy_calibration_without_output_settings_cannot_authorize_playback(client, tmp_path, monkeypatch):
    import base64
    import hashlib
    from app.models.vrt_port_calibration import VrtPortCalibration
    from app.services.road_test.port_calibration import applicability
    from tests.test_road_test_executions import _TestingSessionLocal

    monkeypatch.setenv("VRT_CALIBRATION_APPROVED_DIR", str(tmp_path))
    doc, mapping = _site_files(tmp_path, settings=lambda _: None)
    data = (tmp_path / "report.json").read_bytes()
    readings = (tmp_path / "readings.csv").read_bytes()
    with _TestingSessionLocal() as db:
        old = VrtPortCalibration(evidence_sha256=hashlib.sha256(data).hexdigest(), report_file="report.json",
                                 issuer=doc["issuer"], report_number=doc["report_number"],
                                 evidence_b64=base64.b64encode(data).decode(), readings_b64=base64.b64encode(readings).decode())
        db.add(old)
        db.commit()
        check = applicability(db, old.id, doc["scope"], mapping)
        assert not check["applicable"] and "平均功率设置" in str(check["reasons"])
        assert client.get(ROOT + "/" + str(old.id)).json()["readings_b64"] == old.readings_b64


def test_conflicting_output_setting_for_same_port(client, monkeypatch, tmp_path):
    monkeypatch.setenv("VRT_CALIBRATION_APPROVED_DIR", str(tmp_path))
    _site_files(tmp_path, settings=lambda row: -row["tx"])
    response = client.post(ROOT, json={"report_file": "report.json"})
    assert response.status_code == 422
    assert "平均功率设置" in response.json()["detail"]
