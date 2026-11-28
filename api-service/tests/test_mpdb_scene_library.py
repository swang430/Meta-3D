import hashlib
import json
import shutil
from uuid import uuid4
from zipfile import ZipFile

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import mpdb_projects as projects


def test_scene_reference_survives_workbench_cleanup_and_rejects_wrong_file(tmp_path, monkeypatch):
    source, project = uuid4(), uuid4()
    pending = tmp_path / "workbench"
    folder = pending / str(source)
    folder.mkdir(parents=True)
    monkeypatch.setattr(projects, "storage", lambda: pending)
    monkeypatch.chdir(tmp_path)
    digest = hashlib.sha256(b"mpdb").hexdigest()
    with ZipFile(folder / "source.zip", "w") as archive:
        archive.writestr("R0B0S0D.mpdb", b"mpdb")
    link = {"file":"a.asc","tx":0,"rx":0,"sha256":hashlib.sha256(b"asc").hexdigest()}
    manifest = dict(source={"mpdb":digest}, mode="conducted", direction="downlink",
                    frames=[0],tx_ports=[0],rx_ports=[0],header={"carrier_hz":2e9},links=[link])
    (folder / "timing.json").write_text(json.dumps(dict(frame_ids=[0],tx_ports=[0],rx_ports=[0],
                                                         source_times_s=None,time_source=None)))
    def package(contents):
        with ZipFile(folder / f"{project}.zip","w") as archive:
            archive.writestr("manifest.json", json.dumps(manifest))
            archive.writestr("a.asc",contents)
    app = FastAPI()
    app.include_router(projects.router)
    client = TestClient(app)
    url = f"/channel-assets/mpdb-projects/{source}/{project}/scene"
    package(b"bad")
    assert client.post(url,json={"name":"测试道路"}).status_code == 422
    package(b"asc")
    options = client.get("/channel-assets/mpdb-projects/scene-candidates").json()
    assert [(p["mode"], p["project_id"]) for p in options] == [("conducted", str(project))]
    manifest["source"]["mpdb"] = "f" * 64
    package(b"asc")
    assert client.post(url, json={"name":"测试道路"}).status_code == 422
    manifest["source"]["mpdb"] = digest
    package(b"asc")
    for _ in range(2):
        assert client.post(url,json={"name":"测试道路"}).status_code == 200
    assert client.post(url, json={"name":"其他名称"}).status_code == 409
    shutil.rmtree(pending)
    rows = client.get("/channel-assets/mpdb-projects/scenes").json()
    assert len(rows) == 1
    assert rows[0]["source_sha256"] == digest and rows[0]["source_frames"] == 1
    assert rows[0]["available"] and "tx_power_dbm" not in rows[0]
    saved = next((tmp_path / "data/road-scenes").glob("*/*/project.zip"))
    saved.unlink()
    assert client.get("/channel-assets/mpdb-projects/scenes").json()[0]["available"] is False


def test_registered_ota_clock_matches_dynamic_manifest(tmp_path, monkeypatch):
    from app.api.mpdb_projects import SceneName

    source, project = uuid4(), uuid4()
    folder = tmp_path / str(source)
    folder.mkdir()
    monkeypatch.setattr(projects, "storage", lambda: tmp_path)
    monkeypatch.chdir(tmp_path)
    with ZipFile(folder / "source.zip", "w") as archive:
        archive.writestr("R0B0S0D.mpdb", b"mpdb")
    timing = dict(frame_ids=[0, 1], tx_ports=[0], rx_ports=[0], time_source=None, source_times_s=None)
    (folder / "timing.json").write_text(json.dumps(timing))
    with ZipFile(folder / f"{project}.zip", "w") as archive:
        for prefix in ("baseline/", "dynamic/"):
            manifest = dict(source_sha256=hashlib.sha256(b"mpdb").hexdigest(), mode="ota",
                            direction="downlink", tx_ports=[0], rx_ports=[0], header={"carrier_hz":2e9},
                            links=[{"file":"a.asc","sha256":hashlib.sha256(b"asc").hexdigest()}])
            if prefix == "dynamic/":
                manifest.update(time_source="operator_constant_speed", source_times_s=[0., 1.25])
            archive.writestr(prefix+"manifest.json", json.dumps(manifest))
            archive.writestr(prefix+"a.asc", b"asc")
    record = projects.register_scene(source, project, SceneName(name="恒速轨迹"))
    assert (record["time_source"], record["source_times_s"]) == ("operator_constant_speed", [0., 1.25])


def test_project_conditions_distinguish_port_limit_lab_and_missing_calibration(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from app.api import road_test_conducted as conducted
    from app.api.road_test import project_capabilities

    monkeypatch.chdir(tmp_path)
    source, version = 'a'*64, 'b'*64
    folder = tmp_path / 'data/road-scenes' / source / version
    folder.mkdir(parents=True)
    record = dict(mode='conducted', tx_ports=[0,1], rx_ports=[0,1])
    with ZipFile(folder/'project.zip','w') as archive:
        archive.writestr('manifest.json', b'{}')
    record['package_sha256'] = projects._file_digest(folder/'project.zip')
    (folder/'scene.json').write_text(json.dumps(record))
    check = project_capabilities(source, version, None, None)
    assert any('四发两收' in r for r in check['reasons'])
    lab = SimpleNamespace(id=uuid4(), is_active=True, extra_metadata={'vrt_conducted':[
        dict(road_project_version=version, scenario_id='fixture', asset_id=str(uuid4()))]})
    db = SimpleNamespace(get=lambda *args:lab)
    record['tx_ports'] = [0,1,2,3]
    (folder/'scene.json').write_text(json.dumps(record))
    monkeypatch.setattr(conducted,'resolve',lambda db, selection:dict(
        scenario_id=selection.scenario_id, scenario_snapshot={'name':'传导道路'},
        asset={'sha256':hashlib.sha256(b'{}').hexdigest()}, ready=False,reasons=['尚未选择已采用的逐路校准']))
    check = project_capabilities(source, version, lab.id, db)
    assert check['registrations'][0]['ready'] is False
    assert '逐路校准' in check['registrations'][0]['reasons'][0]

    entries = lab.extra_metadata['vrt_conducted']
    entries[0]['road_project_version'] = 'c' * 64
    assert not project_capabilities(source, version, lab.id, db)['registrations']
    entries[0].update(kind='asc_manifest', sha256=hashlib.sha256(b'{}').hexdigest())
    assert project_capabilities(source, version, lab.id, db)['registrations'][0]['asset_kind'] == '模拟播放清单'
    monkeypatch.setattr(conducted, 'resolve', lambda db, selection: dict(
        scenario_id=selection.scenario_id, asset={'sha256':'f'*64}, scenario_snapshot={'name':'另一份清单'},
        ready=True, reasons=[]))
    mismatched = project_capabilities(source, version, lab.id, db)
    assert not mismatched['registrations']
    assert any('实际采用' in reason for reason in mismatched['reasons'])
    entries[0]['sha256'] = 'd' * 64
    assert not project_capabilities(source, version, lab.id, db)['registrations']
    record['package_sha256'] = 'e' * 64
    (folder/'scene.json').write_text(json.dumps(record))
    assert any('入库摘要不一致' in reason
               for reason in project_capabilities(source, version, lab.id, db)['reasons'])


def test_project_simulation_keeps_source_and_playback_clocks_separate(tmp_path, monkeypatch):
    from app.services.road_test.road_project import RoadProjectReference, project_playback
    import pytest

    monkeypatch.chdir(tmp_path)
    ref = RoadProjectReference(source_sha256='a' * 64, version='b' * 64)
    root = projects._scene_library() / ref.source_sha256 / ref.version
    root.mkdir(parents=True)
    raw = json.dumps({"header": {"cir_count": 38, "rate_hz": 1}}).encode()
    with ZipFile(root / "project.zip", "w") as archive:
        archive.writestr("manifest.json", raw)
    metadata = dict(mode="conducted", direction="downlink", name="道路", source_sha256=ref.source_sha256,
                    version=ref.version, package_sha256=projects._file_digest(root / "project.zip"),
                    source_times_s=None)
    (root / "scene.json").write_text(json.dumps(metadata))
    asset = dict(mock_only=True, sha256=hashlib.sha256(raw).hexdigest())
    playback = project_playback(ref, "conducted", asset, [{}])
    assert playback["source_duration_s"] is None
    assert playback["full_duration_s"] == 37
    metadata["source_times_s"] = [5, 5.8]
    (root / "scene.json").write_text(json.dumps(metadata))
    assert project_playback(ref, "conducted", asset, [{}])["source_duration_s"] == pytest.approx(.8)
    with pytest.raises(ValueError, match="实际采用的播放清单"):
        project_playback(ref, "conducted", dict(asset, sha256="c" * 64), [{}])
    with pytest.raises(ValueError, match="内容、方向或版本"):
        project_playback(ref, "ota", asset, [{}])
