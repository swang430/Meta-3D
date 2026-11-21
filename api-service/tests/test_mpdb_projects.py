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

    def fake_worker(args, **kwargs):
        output, mode = Path(args[3]), args[4]
        folder = output if mode == "conducted" else output / "dynamic"
        folder.mkdir(parents=True)
        for i in range(8 if mode == "conducted" else 128):
            (folder / f"{i}.asc").write_text(mode)
        if mode == "conducted":
            for key in ("results", "evidence"):
                (folder / f"{key}.json").write_text(json.dumps({"schema": key}))
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
            assert len([n for n in result.namelist() if n.endswith(".asc")]) == count
