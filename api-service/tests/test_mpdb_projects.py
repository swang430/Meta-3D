import io
import zipfile

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.mpdb_projects import router


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
    inner = io.BytesIO()
    with zipfile.ZipFile(inner, "w") as db:
        db.writestr(
            "mpdb.json",
            json.dumps(
                {
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
    source = client.post(
        url + "/import", files={"file": ("source.zip", outer.getvalue())}
    ).json()
    for mode, count in [("conducted", 8), ("ota", 128)]:
        response = client.post(
            f"{url}/{source['source_id']}/build", json={"mode": mode}
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
                               json={"mode": "conducted" if role == "conducted" else "ota"})
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
    assert env["HYPERRT_PATH"] == "/tools/HyperRT"
    assert env["PYTHONPATH"].split(os.pathsep)[0] == str(engine)
    assert "MOCK_ASC_MODE" not in env
    monkeypatch.setenv("HYPERRT_PATH", "/custom/HyperRT")
    assert worker_environment(tmp_path)["HYPERRT_PATH"] == "/custom/HyperRT"
