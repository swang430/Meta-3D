"""隔离的一键启动验证：不启动引擎、Docker 或现场数据库。"""
import os
from pathlib import Path
import shutil
import subprocess
import sys
from unittest.mock import patch
import runpy

import pytest


ROOT = Path(__file__).resolve().parents[2]


def test_engine_only_loads_path_from_file(tmp_path, monkeypatch):
    scripts = tmp_path / "scripts"
    service = tmp_path / "channel-engine-service"
    scripts.mkdir()
    service.mkdir()
    script = scripts / "start_channel_engine.py"
    shutil.copyfile(ROOT / "scripts" / script.name, script)
    (service / ".env").write_text("CHANNEL_ENGINE_PATH='/客户 引擎'\nMOCK_ASC_MODE=true\n")
    monkeypatch.delenv("CHANNEL_ENGINE_PATH", raising=False)
    monkeypatch.delenv("MOCK_ASC_MODE", raising=False)
    monkeypatch.chdir(tmp_path)
    with patch.object(os, "execv") as launch:
        runpy.run_path(str(script), run_name="__main__")
        assert os.environ["CHANNEL_ENGINE_PATH"] == "/客户 引擎"
        assert "MOCK_ASC_MODE" not in os.environ
        assert launch.call_args.args[1][-2:] == ["--port", "8001"]


@pytest.mark.parametrize("config,expected", [
    ("DATABASE_URL=postgresql://meta3d:url%40secret@localhost:5432/meta3d", "url@secret"),
    ("DATABASE_URL=postgresql://meta3d@localhost:5432/meta3d\nMETA3D_POSTGRES_PASSWORD = explicit-secret", "explicit-secret"),
])
def test_compose_receives_instance_password_without_printing(tmp_path, config, expected):
    scripts = tmp_path / "scripts"
    api = tmp_path / "api-service"
    scripts.mkdir()
    api.mkdir()
    (api / ".venv").symlink_to(sys.prefix, target_is_directory=True)
    (api / ".env").write_text(config + "\n")
    shutil.copyfile(ROOT / "scripts/db-up.sh", scripts / "db-up.sh")
    for name, body in {"docker": 'test "$META3D_POSTGRES_PASSWORD" = "$EXPECTED"', "nc": "exit 0"}.items():
        exe = scripts / name
        exe.write_text("#!/bin/sh\n" + body + "\n")
        exe.chmod(0o700)
    env = {k: v for k, v in os.environ.items() if k not in {"DATABASE_URL", "META3D_POSTGRES_PASSWORD"}}
    proc = subprocess.run(["bash", scripts / "db-up.sh"], env={**env, "PATH": str(scripts) + ":" + env["PATH"],
                          "EXPECTED": expected}, capture_output=True, text=True, timeout=10)
    assert proc.returncode == 0
    assert expected not in proc.stdout + proc.stderr
