from __future__ import annotations

import importlib.util
import json
import os
import sqlite3
import subprocess
import sys
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


def test_log_rotation_during_scan_is_recorded_as_protected_probe_drift(
    tmp_path: Path, monkeypatch
) -> None:
    module = _load_module()
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    log = repo / "api-service" / "logs" / "rotating.log"
    log.parent.mkdir(parents=True)
    log.write_text("runtime evidence\n", encoding="utf-8")

    def rotate_after_discovery(paths, *, directory=None):
        resolved = {path.resolve(): "closed" for path in paths}
        log.unlink()
        return resolved

    monkeypatch.setattr(module, "detect_open_states", rotate_after_discovery)

    manifest = module.build_inventory(repo, include_docker=False)
    entry = next(item for item in manifest["artifacts"] if item["path"] == str(log.resolve()))

    assert entry["disposition"] == "protect"
    assert entry["open_state"] == "unknown"
    assert entry["probe_state"] == "snapshot_changed"
    assert entry["bytes"] is None


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


def test_known_test_sqlite_with_view_is_not_empty(tmp_path: Path, monkeypatch) -> None:
    module = _load_module()
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    api = repo / "api-service"
    api.mkdir()
    database = api / "test_channel_calibration.db"
    _sqlite(database)
    with sqlite3.connect(database) as db:
        db.execute("CREATE VIEW irreplaceable_definition AS SELECT 42 AS value")
        db.commit()
    monkeypatch.setattr(module, "detect_open_state", lambda _path: "closed")

    manifest = module.build_inventory(repo, include_docker=False)
    entry = next(item for item in manifest["artifacts"] if item["path"] == str(database.resolve()))

    assert entry["disposition"] == "protect"
    assert "sqlite_schema_nonempty" in entry["identity_evidence"]


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


def test_docker_inventory_records_read_only_size_evidence() -> None:
    module = _load_module()

    def docker_fixture(args):
        command = tuple(args)
        if command == ("docker", "volume", "ls", "-q"):
            return SimpleNamespace(returncode=0, stdout="meta3d_postgres_data\n", stderr="")
        if command[:3] == ("docker", "system", "df"):
            return SimpleNamespace(
                returncode=0,
                stdout=(
                    "VOLUME NAME             LINKS     SIZE\n"
                    "meta3d_postgres_data    1         79.65MB\n"
                ),
                stderr="",
            )
        if command[:3] == ("docker", "volume", "inspect"):
            return SimpleNamespace(
                returncode=0,
                stdout='{"CreatedAt":"2026-08-02T09:05:03Z","Labels":null}\n',
                stderr="",
            )
        if command[:2] == ("docker", "ps"):
            return SimpleNamespace(returncode=0, stdout="meta3d_db\n", stderr="")
        raise AssertionError(command)

    volumes = module._collect_docker_volumes(docker_fixture)

    assert volumes[0]["size_display"] == "79.65MB"
    assert volumes[0]["bytes"] == 79_650_000
    assert "docker_system_df" in volumes[0]["identity_evidence"]


def test_docker_non_object_inspect_is_malformed_and_protected() -> None:
    module = _load_module()

    def docker_fixture(args):
        command = tuple(args)
        if command == ("docker", "volume", "ls", "-q"):
            return SimpleNamespace(returncode=0, stdout="anonymous\n", stderr="")
        if command[:3] == ("docker", "system", "df"):
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        if command[:3] == ("docker", "volume", "inspect"):
            return SimpleNamespace(returncode=0, stdout="[]\n", stderr="")
        if command[:2] == ("docker", "ps"):
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        raise AssertionError(command)

    volumes = module._collect_docker_volumes(docker_fixture)

    assert volumes[0]["probe_state"] == "malformed"
    assert volumes[0]["disposition"] == "protect"


def test_lsof_partial_success_keeps_positive_open_evidence(tmp_path: Path, monkeypatch) -> None:
    module = _load_module()
    log = tmp_path / "app.log"
    unmatched_log = tmp_path / "unmatched.log"
    log.write_text("evidence", encoding="utf-8")
    unmatched_log.write_text("evidence", encoding="utf-8")

    monkeypatch.setattr(
        module.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(
            returncode=1,
            stdout=f"p123\nf4\nn{log}\n",
            stderr="",
        ),
    )

    states = module.detect_open_states([log, unmatched_log], directory=tmp_path)

    assert states[log.resolve()] == "open"
    assert states[unmatched_log.resolve()] == "unknown"


def test_lsof_error_without_matches_is_unknown(tmp_path: Path, monkeypatch) -> None:
    module = _load_module()
    database = tmp_path / "test_channel_calibration.db"
    _sqlite(database)

    monkeypatch.setattr(
        module.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(
            returncode=1,
            stdout="",
            stderr="lsof: status error on target: Permission denied\n",
        ),
    )

    assert module.detect_open_state(database) == "unknown"


def test_git_probe_failure_is_not_reported_as_untracked(tmp_path: Path, monkeypatch) -> None:
    module = _load_module()
    repo = tmp_path / "repo"
    repo.mkdir()
    database = repo / "test_channel_calibration.db"
    _sqlite(database)

    monkeypatch.setattr(
        module.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(returncode=128),
    )

    assert module._git_state(repo, database) == "unknown"


def test_calibration_tests_leave_no_sqlite_in_calling_directory(tmp_path: Path) -> None:
    api_root = Path(__file__).resolve().parents[1]
    protected_cwd = tmp_path / "protected-cwd"
    protected_cwd.mkdir()
    nodeids = [
        f"{api_root / 'tests/test_channel_calibration.py'}::TestChannelCalibrationService::test_create_session",
        f"{api_root / 'tests/test_probe_calibration_api.py'}::TestAmplitudeCalibrationStart::test_start_amplitude_calibration_success",
        f"{api_root / 'tests/test_probe_calibration_service.py'}::TestAmplitudeCalibrationService::test_execute_calibration_mock",
        f"{api_root / 'tests/test_probe_calibration_integration.py'}::TestCompleteCalibrationWorkflow::test_full_calibration_workflow_single_probe",
    ]
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        filter(None, [str(api_root), env.get("PYTHONPATH", "")])
    )

    result = subprocess.run(
        [sys.executable, "-m", "pytest", *nodeids, "-q"],
        cwd=protected_cwd,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert list(protected_cwd.glob("*.db")) == []
