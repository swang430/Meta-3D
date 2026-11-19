import subprocess
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.auth.config import auth_config
from app.auth.security import create_access_token, verify_token
from app.config import Settings


def test_unsupported_required_mode_cannot_start():
    with pytest.raises(ValidationError, match="业务接口未实施统一身份认证"):
        Settings(auth_mode="required", _env_file=None)


def test_token_signing_needs_configured_key(monkeypatch):
    monkeypatch.setattr(auth_config, "SECRET_KEY", None)
    with pytest.raises(ValueError, match="JWT_SECRET_KEY"):
        create_access_token({"sub": "delivery-check"})
    assert verify_token("untrusted") is None
    monkeypatch.setattr(auth_config, "SECRET_KEY", "test-only-key")
    assert verify_token(create_access_token({"sub": "delivery-check"})).sub == "delivery-check"


def test_failed_backup_does_not_publish_or_rotate(tmp_path):
    import os
    container = "offline-del02-test"
    docker = tmp_path / "docker"
    docker.write_text(
        '#!/bin/sh\ncase "$1" in\n'
        f'ps) echo "{container}";;\n'
        'exec) echo partial-data; exit 1;;\n'
        '*) exit 9;;\nesac\n'
    )
    docker.chmod(0o700)
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    previous = backup_dir / "offline_previous.dump"
    previous.write_bytes(b"original backup")
    script = Path(__file__).resolve().parents[1] / "scripts" / "backup_db.sh"
    # launchd prepends standard tool paths; exercise the exact script with a shell
    # function overriding docker so the test cannot reach a real daemon.
    command = 'docker() { "$TEST_DOCKER" "$@"; }; . "$TEST_BACKUP_SCRIPT"'
    env = {**os.environ, "TEST_DOCKER": str(docker), "TEST_BACKUP_SCRIPT": str(script),
           "META3D_PG_CONTAINER": container, "META3D_PG_DB": "offline",
           "META3D_BACKUP_DIR": str(backup_dir), "META3D_BACKUP_RETENTION": "1"}
    result = subprocess.run(["sh", "-c", command], env=env, capture_output=True)
    assert result.returncode != 0
    assert list(backup_dir.iterdir()) == [previous]
    assert previous.read_bytes() == b"original backup"


def test_remote_process_url_skips_local_compose(tmp_path):
    import os
    import shutil

    root = Path(__file__).resolve().parents[2]
    scripts = tmp_path / "scripts"
    config = tmp_path / "api-service"
    scripts.mkdir()
    config.mkdir()
    script = scripts / "db-up.sh"
    shutil.copyfile(root / "scripts/db-up.sh", script)
    (config / ".env").write_text("DATABASE_URL=postgresql://meta3d@localhost:5432/meta3d_ota\n")
    docker = scripts / "docker"
    docker.write_text('#!/bin/sh\ntouch "$DOCKER_INVOKED"\nexit 12\n')
    docker.chmod(0o700)
    marker = tmp_path / "docker-invoked"
    env = {**os.environ, "PATH": str(scripts) + os.pathsep + os.environ["PATH"],
           "DATABASE_URL": "postgresql://audit@isolated.invalid:5432/restored",
           "DOCKER_INVOKED": str(marker)}
    result = subprocess.run(["bash", str(script)], env=env, capture_output=True)
    assert result.returncode == 0
    assert not marker.exists()
