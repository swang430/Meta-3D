import io
import zipfile

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.mpdb_projects import router


def test_isolated_api_image_imports_without_optional_workspace_scripts(tmp_path):
    import os
    from pathlib import Path
    import shutil
    import subprocess
    import sys
    from app.api import mpdb_projects

    copied = tmp_path / "image/app/api/mpdb_projects.py"
    copied.parent.mkdir(parents=True)
    shutil.copyfile(mpdb_projects.__file__, copied)
    probe = """
import runpy
from fastapi import FastAPI
from fastapi.testclient import TestClient
module = runpy.run_path('app/api/mpdb_projects.py')
app = FastAPI()
app.include_router(module['router'])
client = TestClient(app)
assert client.get('/openapi.json').status_code == 200
result = client.post('/channel-assets/mpdb-projects/import', files={'file':('input.zip', b'input')})
assert result.status_code == 503, result.text
assert '离线' in result.json()['detail']
"""
    env = {**os.environ, "TMPDIR":str(tmp_path)}
    out = subprocess.run([sys.executable,"-I","-c",probe],cwd=copied.parents[2],
                         env=env,text=True,capture_output=True)
    assert out.returncode == 0, out.stderr
    assert not (tmp_path/"meta3d-mpdb-projects").exists()


def test_rejects_archive_without_downlink_and_unknown_source():
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as out:
        out.writestr("R0B0S0U.mpdb", b"")
    response = client.post(
        "/channel-assets/mpdb-projects/import",
        files={"file": ("test.zip", archive.getvalue())},
    )
    assert response.status_code == 422
    response = client.post(
        "/channel-assets/mpdb-projects/00000000-0000-0000-0000-000000000000/build",
        json={"mode": "conducted"},
    )
    assert response.status_code == 404
    response = client.post(
        "/channel-assets/mpdb-projects/00000000-0000-0000-0000-000000000000/build",
        json={"mode": "conducted", "clustering_method": "hyperrt"},
    )
    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "clustering_method"]


def test_same_import_can_build_twice_and_download_independent_archives(
    tmp_path, monkeypatch
):
    import json
    from pathlib import Path
    from app.api import mpdb_projects

    base = tmp_path / "storage"
    base.mkdir()
    monkeypatch.setattr(mpdb_projects, "storage", lambda: base)
    (tmp_path / "mimo_ota_simulator").mkdir()
    monkeypatch.setenv("CHANNEL_ENGINE_PATH", str(tmp_path))

    mutations = {}
    include_evidence = True

    def fake_worker(args, **kwargs):
        output, mode = Path(args[3]), args[4]
        roles = ["conducted"] if mode == "conducted" else ["baseline", "dynamic"]
        for role in roles:
            directory = output if mode == "conducted" else output / role
            directory.mkdir(parents=True)
            names = [f"{i}.asc" for i in range(8 if mode == "conducted" else 128)]
            for name in names:
                (directory / name).write_text(mode)
            if role in mutations:
                mutations[role](directory, names)
            manifest = {"build": output.parent.name, "role": role,
                        "links": [{"file": name} for name in names]}
            (directory / "manifest.json").write_text(json.dumps(manifest))
        if mode == "conducted":
            if include_evidence:
                (output / "evidence.json").write_text(json.dumps({"schema": "evidence"}))
            (output / "results.json").write_text(json.dumps({"schema": "results"}))
        return 0, ""

    monkeypatch.setattr(mpdb_projects, "run_worker", fake_worker)
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    client = TestClient(app)
    import numpy as np
    inner = io.BytesIO()
    with zipfile.ZipFile(inner, "w") as db:
        cols = {}
        for key, values in dict(FRAME_ID=[0,1], LINK_ID=[0,1], TX_ANT=[0,0], RX_ANT=[0,0],
                                RX_ANT_POSITION=[[0,0,0],[3,4,0]]).items():
            arr = np.array(values, dtype="<i4")
            header = json.dumps({"data":{"dtype":"I32","shape":list(arr.shape),
                                        "data_offsets":[0,arr.nbytes]}}).encode()
            db.writestr(key, len(header).to_bytes(8,"little")+header+arr.tobytes())
            cols[key] = dict(dtype="torch.int32",shape=list(arr.shape),rowCount=2,
                             shards=[dict(entry=key,rowStart=0,rowEnd=2)])
        db.writestr(
            "mpdb.json",
            json.dumps(
                {
                    "records": {"LINK":cols, "CHANNEL":{"DOPPLER":cols["FRAME_ID"]}},
                    "meta": {
                        "lauraycsPlatform": {
                            "direction": "downlink",
                            "angleCoordinateSystem": "GCS",
                        },
                        "mode": "CIR",
                        "numFrequency": 1,
                    }
                }
            ),
        )
    outer = io.BytesIO()
    with zipfile.ZipFile(outer, "w") as archive:
        archive.writestr("R0B0S0D.mpdb", inner.getvalue())
    url = "/api/v1/channel-assets/mpdb-projects"
    def imported_with_meta(meta):
        variant = io.BytesIO()
        with zipfile.ZipFile(inner) as src, zipfile.ZipFile(variant, "w") as dst:
            for name in src.namelist():
                data = src.read(name)
                if name == "mpdb.json":
                    desc=json.loads(data)
                    platform=desc["meta"]["lauraycsPlatform"]
                    platform.update(meta.get("lauraycsPlatform",{}))
                    desc["meta"].update({k:v for k,v in meta.items() if k!="lauraycsPlatform"})
                    data=json.dumps(desc).encode()
                dst.writestr(name,data)
        raw = io.BytesIO()
        with zipfile.ZipFile(raw,"w") as out:
            out.writestr("R0B0S0D.mpdb",variant.getvalue())
        return client.post(url+"/import",files={"file":("source.zip",raw.getvalue())})
    stamps = {"rtSampleTimesSeconds":[7,9]}
    raw = imported_with_meta({"rtSampleIntervalSeconds":2, "lauraycsPlatform":stamps})
    assert raw.json()["timing"]["source_times_s"] == [7,9]
    assert raw.json()["timing"]["time_source"].endswith(".rtSampleTimesSeconds")
    for meta in ({"rtSampleIntervalSeconds":1,"lauraycsPlatform":stamps},
                 {"rtSampleTimesSeconds":[8,10],"lauraycsPlatform":stamps},
                 {"lauraycsPlatform":{"rtSampleTimesSeconds":[0,0]}},
                 {"lauraycsPlatform":{"rtFrameClock":{"version":1,"mode":"physical"}}}):
        assert imported_with_meta(meta).status_code == 422
    assert imported_with_meta({"rtSampleIntervalSeconds":0.5}).json()["timing"]["source_times_s"] == [0,0.5]
    source = client.post(
        url + "/import", files={"file": ("source.zip", outer.getvalue())}
    ).json()
    assert source.get("timing", {}).get("distances_m") == [5]
    assert source["timing"]["source_times_s"] is None
    assert source["clustering"] == "missing"
    import hashlib
    for identity, expected in (("wrong",422),(hashlib.sha256(inner.getvalue()).hexdigest(),200)):
        labels=io.BytesIO()
        np.savez(labels,source_sha256=identity,L0=np.array([0]),L1=np.array([0]))
        supplied_response=client.post(url+"/import",files={
            "file":("source.zip",outer.getvalue()),"members":("groups.npz",labels.getvalue())})
        assert supplied_response.status_code == expected
        if expected == 200:
            assert supplied_response.json()["clustering"] == "supplied"
    build_url = f"{url}/{source['source_id']}/build"
    assert client.post(build_url,json={"mode":"ota"}).status_code == 422
    assert client.post(build_url,json={"mode":"ota","rate_hz":100}).status_code == 422
    assert client.post(build_url,json={"mode":"ota","speed_m_s":5,"rate_hz":100}).status_code == 422
    explicit = {"speed_m_s":5,"rate_quality":"dense"}
    for mode, count in [("conducted", 8), ("ota", 128)]:
        response = client.post(
            build_url, json={"mode": mode, **(explicit if mode == "ota" else {})}
        )
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["asc_count"] == count
        if mode == "conducted":
            assert (
                data["results"]["schema"] == "results"
                and data["evidence"]["schema"] == "evidence"
            )
        with zipfile.ZipFile(
            io.BytesIO(client.get(data["download_url"]).content)
        ) as result:
            for role in (["conducted"] if mode == "conducted" else ["baseline", "dynamic"]):
                path = "manifest.json" if role == "conducted" else f"{role}/manifest.json"
                assert data["manifests"][role] == json.loads(result.read(path))
                prefix = "" if role == "conducted" else role + "/"
                assert len([n for n in result.namelist() if n.startswith(prefix) and n.endswith(".asc")]) == count

    include_evidence = False
    response = client.post(f"{url}/{source['source_id']}/build", json={"mode": "conducted"})
    assert response.status_code == 200
    assert "evidence" not in response.json()
    assert client.get(response.json()["download_url"]).status_code == 200

    def remove_both(directory, names):
        (directory / names.pop()).unlink()

    packages = set((base / source["source_id"]).glob("*.zip"))
    for role, mutate, details in [
        ("baseline", lambda folder, names: (folder / "127.asc").unlink(), ["127.asc", "缺少"]),
        ("conducted", lambda folder, names: (folder / "7.asc").rename(folder / "other.asc"),
         ["缺少", "7.asc", "额外", "other.asc"]),
        ("dynamic", remove_both, ["128", "127"]),
    ]:
        mutations.clear()
        mutations[role] = mutate
        response = client.post(f"{url}/{source['source_id']}/build",
                               json={"mode": "conducted"} if role == "conducted" else {"mode":"ota", **explicit})
        assert response.status_code == 500
        assert all(word in response.json()["detail"] for word in [role, *details])
        assert set((base / source["source_id"]).glob("*.zip")) == packages


def test_engine_paths_from_local_service_configuration(tmp_path, monkeypatch):
    import os
    from app.api.mpdb_projects import worker_environment

    folder = tmp_path / "channel-engine-service"
    folder.mkdir()
    engine = tmp_path / "本机引擎"
    (engine / "mimo_ota_simulator").mkdir(parents=True)
    (folder / ".env").write_text(
        f"CHANNEL_ENGINE_PATH='{engine}'\nHYPERRT_PATH=/tools/HyperRT\nMOCK_ASC_MODE=true\n"
    )
    for key in ("CHANNEL_ENGINE_PATH", "HYPERRT_PATH", "MOCK_ASC_MODE"):
        monkeypatch.delenv(key, raising=False)
    env = worker_environment(tmp_path)
    assert env["CHANNEL_ENGINE_PATH"] == str(engine)
    assert "HYPERRT_PATH" not in env
    assert env["PYTHONPATH"].split(os.pathsep)[0] == str(engine)
    assert "MOCK_ASC_MODE" not in env
    monkeypatch.setenv("HYPERRT_PATH", "/custom/HyperRT")
    assert "HYPERRT_PATH" not in worker_environment(tmp_path)
