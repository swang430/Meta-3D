from __future__ import annotations

import importlib.util
import json
import sqlite3
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "dev_artifact_inventory.py"


def _load_module():
    if not SCRIPT.exists():
        pytest.fail("P2-40 read-only inventory script has not been implemented")
    spec = importlib.util.spec_from_file_location("dev_artifact_inventory", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _init_repo(path: Path) -> None:
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    subprocess.run(
        ["git", "-C", str(path), "config", "user.email", "p2-40@example.invalid"],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(path), "config", "user.name", "P2-40 Test"],
        check=True,
    )
    (path / ".gitignore").write_text("api-service/logs/\napi-service/*.db\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(path), "add", ".gitignore"], check=True)
    subprocess.run(["git", "-C", str(path), "commit", "-qm", "fixture"], check=True)


def _sqlite(path: Path, *, table: str | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path)
    try:
        if table:
            db.execute(f"CREATE TABLE {table} (id INTEGER PRIMARY KEY)")
        else:
            # Match SQLAlchemy's create_all/drop_all residue: valid SQLite header,
            # but no remaining application tables.
            db.execute("CREATE TABLE _p2_40_probe (id INTEGER PRIMARY KEY)")
            db.execute("DROP TABLE _p2_40_probe")
        db.commit()
    finally:
        db.close()


def test_inventory_only_scans_explicit_roots_and_never_follows_symlinks(tmp_path: Path) -> None:
    module = _load_module()
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)

    logs = repo / "api-service" / "logs"
    logs.mkdir(parents=True)
    (logs / "app.log").write_text("runtime evidence\n", encoding="utf-8")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.log").write_text("must not be followed\n", encoding="utf-8")
    (logs / "external-link.log").symlink_to(outside / "secret.log")
    (repo / "Instrument_API_Doc").mkdir()
    _sqlite(repo / "Instrument_API_Doc" / "manual-evidence.db", table="evidence")

    manifest = module.build_inventory(repo, include_docker=False)
    paths = {entry["path"] for entry in manifest["artifacts"]}

    assert str((logs / "app.log").resolve()) in paths
    assert str(logs / "external-link.log") not in paths
    assert str((outside / "secret.log").resolve()) not in paths
    assert str((repo / "Instrument_API_Doc" / "manual-evidence.db").resolve()) not in paths


def test_known_empty_test_sqlite_requires_every_identity_signal(tmp_path: Path) -> None:
    module = _load_module()
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    api = repo / "api-service"
    api.mkdir()

    candidate = api / "test_channel_calibration.db"
    _sqlite(candidate)
    unknown_name = api / "test_user_session.db"
    _sqlite(unknown_name)
    nonempty = api / "test_probe_calibration.db"
    _sqlite(nonempty, table="probe_amplitude_calibrations")

    manifest = module.build_inventory(repo, include_docker=False)
    entries = {Path(entry["path"]).name: entry for entry in manifest["artifacts"]}

    assert entries[candidate.name]["disposition"] == "quarantine_candidate"
    assert "known_test_producer" in entries[candidate.name]["identity_evidence"]
    assert "sqlite_schema_empty" in entries[candidate.name]["identity_evidence"]
    assert entries[unknown_name.name]["disposition"] == "protect"
    assert entries[nonempty.name]["disposition"] == "protect"


def test_invalid_and_open_state_unknown_sqlite_are_protected(tmp_path: Path, monkeypatch) -> None:
    module = _load_module()
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    api = repo / "api-service"
    api.mkdir()
    invalid = api / "test_channel_calibration.db"
    invalid.write_text("not sqlite", encoding="utf-8")

    monkeypatch.setattr(module, "detect_open_state", lambda _path: "unknown")
    manifest = module.build_inventory(repo, include_docker=False)
    entry = next(item for item in manifest["artifacts"] if item["path"] == str(invalid.resolve()))

    assert entry["disposition"] == "protect"
    assert entry["open_state"] == "unknown"
    assert "sqlite_invalid" in entry["identity_evidence"]


def test_renderers_share_one_stably_sorted_manifest(tmp_path: Path) -> None:
    module = _load_module()
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    logs = repo / "api-service" / "logs"
    logs.mkdir(parents=True)
    (logs / "z.log").write_text("z", encoding="utf-8")
    (logs / "a.log").write_text("a", encoding="utf-8")

    manifest = module.build_inventory(repo, include_docker=False)
    json_text = module.render_json(manifest)
    markdown = module.render_markdown(manifest)
    decoded = json.loads(json_text)
    paths = [entry["path"] for entry in decoded["artifacts"]]

    assert paths == sorted(paths)
    for path in paths:
        assert path in markdown
    assert json_text == module.render_json(manifest)


def test_cli_has_no_mutation_option() -> None:
    module = _load_module()
    parser = module.build_parser()
    option_strings = {
        option
        for action in parser._actions
        for option in action.option_strings
    }

    assert "--execute" not in option_strings
    assert "--delete" not in option_strings
    assert "--move" not in option_strings
    assert "--prune" not in option_strings


@pytest.mark.parametrize(
    ("volume", "expected"),
    [
        ({"name": "meta3d_postgres_data", "mounted_by": ["meta3d_db"], "labels": {}}, "protect"),
        ({"name": "anonymous", "mounted_by": [], "labels": {"com.docker.volume.anonymous": ""}}, "review"),
        ({"name": "unknown", "mounted_by": [], "labels": {}}, "protect"),
    ],
)
def test_docker_volume_classification_never_guesses_identity(volume: dict, expected: str) -> None:
    module = _load_module()
    entry = module.classify_docker_volume(volume)
    assert entry["disposition"] == expected


def test_docker_unavailable_is_explicit_and_safe(tmp_path: Path) -> None:
    module = _load_module()
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)

    def unavailable(args):
        if args[0] == "docker":
            raise FileNotFoundError("docker")
        return subprocess.run(args, check=False, capture_output=True, text=True)

    manifest = module.build_inventory(repo, include_docker=True, command_runner=unavailable)

    assert manifest["probes"]["docker"] == "unavailable"
    assert not any(item["disposition"] == "quarantine_candidate" for item in manifest["docker_volumes"])


def test_lsof_partial_success_keeps_positive_open_evidence(tmp_path: Path, monkeypatch) -> None:
    module = _load_module()
    log = tmp_path / "app.log"
    log.write_text("evidence", encoding="utf-8")

    monkeypatch.setattr(
        module.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(
            returncode=1,
            stdout=f"p123\nf4\nn{log}\n",
            stderr="",
        ),
    )

    assert module.detect_open_states([log], directory=tmp_path)[log.resolve()] == "open"
