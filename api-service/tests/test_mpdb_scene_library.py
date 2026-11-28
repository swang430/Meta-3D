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
