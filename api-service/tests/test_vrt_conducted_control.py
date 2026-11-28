import pytest

from tests.test_road_test_executions import _isolated_db


def test_legacy_conducted_draft_cannot_start(client, sample_topology_data):
    root = "/api/v1/road-test"
    topology = client.post(root + "/topologies", json=sample_topology_data).json()
    scenario = client.get(root + "/scenarios").json()[0]
    execution = client.post(root + "/executions", json={
        "mode": "conducted", "scenario_id": scenario["id"], "topology_id": topology["id"],
    }).json()
    url = root + "/executions/" + execution["execution_id"]
    result = client.post(url + "/control", json={"action": "start"})
    assert result.status_code == 409
    assert client.get(url).json()["status"] == "idle"


@pytest.mark.parametrize("outcome", ["stop", "start_rejected", "stop_unconfirmed", "mixed_drivers", "complete", "extra_file", "changed_bytes", "scenario_changed", "missing_digest"])
def test_mock_manifest_playback_and_stop(client, sample_topology_data, tmp_path, monkeypatch, outcome):
    import hashlib
    import json
    import os
    from pathlib import Path
    from uuid import uuid4
    from app.api.road_test_conducted import mock_asset
    from app.models.lab_profile import LabProfile
    from tests.test_road_test_executions import _TestingSessionLocal

    root = "/api/v1/road-test"
    scenario = client.get(root + "/scenarios").json()[0]
    scenario = client.get(root + "/scenarios/" + scenario["id"]).json()
    if outcome in ("complete", "scenario_changed"):
        scenario["route"]["duration_s"] = 30
        scenario["name"] = "冻结场景"
        result = client.post(root + "/scenarios", json=scenario)
        assert result.status_code == 201, result.text
        scenario = result.json()
    if os.environ.get("VRT_TEST_ASC_DIRECTORY"):
        directory = Path(os.environ["VRT_TEST_ASC_DIRECTORY"])
    else:
        directory = tmp_path
        links = []
        for tx in range(4):
            for rx in range(2):
                name = f"fixture_TX{tx}_RX{rx}_H.asc"
                (directory / name).write_bytes(name.encode())
                links.append(dict(tx=tx, rx=rx, file=name, sha256=hashlib.sha256(name.encode()).hexdigest()))
        (directory / "manifest.json").write_text(json.dumps(dict(mode="conducted", direction="downlink", links=links, header=dict(cir_count=3, rate_hz=2))))
    if outcome in ("extra_file", "changed_bytes") and directory != tmp_path:
        import shutil
        directory = Path(shutil.copytree(directory, tmp_path / "source"))
    asset = mock_asset(directory, "模拟清单")
    topology = sample_topology_data
    topology["base_station"]["tx_ports"] = topology["channel_emulator"]["input_ports"] = 4
    for port in (3, 4):
        topology["connections"].append(dict(topology["connections"][0], connection_id=f"bs-{port}", source_port=port, target_port=port))
    topology_id = client.post(root + "/topologies", json=topology).json()["id"]
    assert client.post(root + "/topologies/" + topology_id + "/validate").is_success
    selection = dict(scenario_id=scenario["id"], topology_id=topology_id, asset_id=str(uuid4()), direction="downlink")
    mapping = [dict(tx=t, rx=r, input_port=t, output_port=r) for t in range(1, 5) for r in (1, 2)]
    registration = dict(selection, kind="asc_manifest", manifest_dir=str(directory), name="模拟清单",
                        sha256=asset["sha256"], scenario_version=scenario["version"], port_mapping=mapping)
    if outcome != "missing_digest":
        content = {k: v for k, v in scenario.items() if k not in ("created_at", "updated_at")}
        registration["scenario_sha256"] = hashlib.sha256(
            json.dumps(content, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
        ).hexdigest()
    with _TestingSessionLocal() as db:
        lab = LabProfile(name="模拟实验室", extra_metadata={"vrt_conducted": [registration]})
        db.add(lab)
        db.commit()
        selection["lab_profile_id"] = str(lab.id)
    if outcome == "complete":
        settings = {"traffic": {"type": "video", "direction": "DL"}}
        header = json.loads((directory / "manifest.json").read_bytes())["header"]
        span = (header["cir_count"] - 1) / header["rate_hz"]
        default = client.post(root + "/conducted/prepare", json=selection).json()
        assert default["ready"] and default["playback"]["duration_s"] == span
        preview = client.post(root + "/conducted/prepare", json={**selection, "test_settings": settings}).json()
        assert preview["ready"] and preview["playback"]["duration_s"] == span
        assert preview["playback"]["duration_source"] == "模拟文件首末响应间隔"
        exceeded = client.post(root + "/conducted/prepare", json={
            **selection, "test_settings": {**settings, "playback_seconds": span + 0.1}
        }).json()
        assert not exceeded["ready"] and any("超过整段时长" in r for r in exceeded["reasons"])
        selection["test_settings"] = {**settings, "playback_seconds": 0.08}
    saved = client.post(root + "/conducted/executions", json=selection).json()
    if outcome == "missing_digest":
        assert not saved["config"]["conducted"]["ready"]
        return
    assert saved["config"]["conducted"]["ready"], saved
    url = root + "/executions/" + saved["execution_id"]
    from app.services.instrument_hal_service import get_hal_service
    from unittest.mock import AsyncMock
    hal = get_hal_service()
    channel = hal.drivers["channelEmulator"]
    if outcome in ("extra_file", "changed_bytes"):
        original_load = channel.load_channel
        observed = {}
        if outcome == "extra_file":
            (directory / "extra.asc").write_bytes(b"not registered")

        async def inspect_load(*args, waveform_dir, **kwargs):
            if outcome == "changed_bytes":
                (directory / asset["links"][0]["file"]).write_bytes(b"replacement")
            for path in Path(waveform_dir).glob("*.asc"):
                observed[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
            return await original_load(*args, waveform_dir=waveform_dir, **kwargs)

        monkeypatch.setattr(channel, "load_channel", inspect_load)
        assert client.post(url + "/control", json={"action": "start"}).is_success
        assert client.post(url + "/control", json={"action": "stop"}).is_success
        assert observed == {link["file"]: link["sha256"] for link in asset["links"]}
        return
    if outcome == "mixed_drivers":
        load = AsyncMock()
        monkeypatch.setattr(channel, "load_channel", load)
        monkeypatch.setitem(hal.drivers, "baseStation", object())
        assert client.post(url + "/control", json={"action": "start"}).status_code == 409
        load.assert_not_awaited()
        assert client.get(url).json()["status"] == "idle"
        return
    if outcome == "start_rejected":
        monkeypatch.setattr(channel, "start_emulation", AsyncMock(return_value=False))
        assert client.post(url + "/control", json={"action": "start"}).status_code == 409
        assert client.get(url).json()["status"] == "failed"
        assert (client.get(url + "/status").json()["last_error"])
        return
    if outcome == "scenario_changed":
        changed = dict(scenario["route"], duration_s=90)
        edited = client.put(root + "/scenarios/" + scenario["id"], json={"route": changed})
        assert edited.is_success and edited.json()["version"] == scenario["version"]
        load = AsyncMock()
        monkeypatch.setattr(channel, "load_channel", load)
        assert client.post(url + "/control", json={"action": "start"}).status_code == 409
        load.assert_not_awaited()
        preview = client.post(root + "/conducted/prepare", json=selection).json()
        assert preview["scenario_sha256"] != registration["scenario_sha256"] and not preview["ready"]
        return
    if outcome == "complete":
        from app.api import road_test
        # 延迟首次归档到原场景删除之后，覆盖真正的归档生成路径。
        archive_report = road_test._archive_execution_report
        monkeypatch.setattr(road_test, "_archive_execution_report", AsyncMock())
        # prepare 仍读取当前自定义场景；重验之后的执行与报告只能读保存的版本。
        monkeypatch.setattr(road_test, "_get_custom_scenario",
                            lambda *_: pytest.fail("重新读取了可变场景"))
    start = client.post(url + "/control", json={"action": "start"})
    assert start.is_success, start.text
    if outcome == "complete":
        import time
        deadline = time.monotonic() + 5
        while client.get(url).json()["status"] == "running" and time.monotonic() < deadline:
            time.sleep(0.05)
        assert client.get(url).json()["status"] == "completed"
        report = client.get(url + "/report").json()
        assert report["route"]["duration_s"] == 30
        elapsed = client.get(url + "/status").json()["elapsed_time_s"]
        assert 0.08 <= elapsed < 5
        observations = client.get(url + "/metrics").json()["observations"]
        assert observations and all(0 <= row["time_s"] <= 0.08 for row in observations)
        assert report["conducted_setup"]["playback"]["duration_s"] == 0.08
        assert report["conducted_setup"]["test_settings"]["traffic"]["type"] == "video"
        report.pop("generated_at")
        scenario_url = root + "/scenarios/" + scenario["id"]
        for edit in (lambda: client.put(scenario_url, json={"name": "新名称"}), lambda: client.delete(scenario_url)):
            assert edit().is_success
            latest = client.get(url + "/report").json()
            latest.pop("generated_at")
            assert latest == report
            history = client.get(root + "/executions?mode=conducted").json()
            assert history[0]["scenario_name"] == "冻结场景"
        monkeypatch.setattr(road_test, "_archive_execution_report", archive_report)
        archive = client.post(url + "/archive-report")
        assert archive.is_success, archive.text
        from app.models.report import TestReport
        with _TestingSessionLocal() as db:
            record = db.query(TestReport).filter_by(road_test_execution_id=saved["execution_id"]).one()
            assert record.content_data["scenario_name"] == "冻结场景"
            assert record.content_data["conducted_setup"] == report["conducted_setup"]
        return
    assert client.get(url).json()["status"] == "running"
    for action in ("start", "pause", "complete"):
        assert client.post(url + "/control", json={"action": action}).status_code == 409
    samples = client.get(url + "/metrics").json()["observations"]
    assert samples and all(s["provenance"] == "simulated" for s in samples)
    other = client.post(root + "/conducted/executions", json=selection).json()
    other_url = root + "/executions/" + other["execution_id"]
    assert client.post(other_url + "/control", json={"action": "start"}).status_code == 409
    assert client.get(other_url).json()["status"] == "idle"
    if outcome == "stop_unconfirmed":
        monkeypatch.setattr(channel, "stop_emulation", AsyncMock(return_value=False))
        assert client.post(url + "/control", json={"action": "stop"}).status_code == 409
        assert client.get(url).json()["status"] == "failed"
        return
    assert client.post(url + "/control", json={"action": "stop"}).is_success
    assert client.get(url).json()["status"] == "stopped"

def test_recover_interrupted_conducted_execution():
    from app.schemas.road_test import TestMode
    from app.services.road_test.conducted_runner import recover_conducted_runs
    from app.services.road_test.vrt_execution_service import vrt_execution_service as service
    from tests.test_road_test_executions import _TestingSessionLocal
    with _TestingSessionLocal() as db:
        row = service.create(db, mode=TestMode.CONDUCTED, scenario_id="restart")
        service.start(db, str(row.id))
        recover_conducted_runs(db)
        db.refresh(row)
        assert row.status == "failed" and "未取得设备停止回读" in row.error_message


def test_changed_source_rejected_before_driver_receives_copy(tmp_path):
    import hashlib
    from app.services.road_test.conducted_runner import _stage_waveforms

    link = {"file": "link.asc", "sha256": hashlib.sha256(b"at preparation").hexdigest()}
    (tmp_path / "link.asc").write_bytes(b"changed before staging")
    staged = tmp_path / "staged"
    staged.mkdir()
    with pytest.raises(ValueError, match="摘要不一致"):
        _stage_waveforms(tmp_path, [link], staged)
