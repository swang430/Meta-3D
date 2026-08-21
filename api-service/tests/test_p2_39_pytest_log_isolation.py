"""P2-39: pytest 进程不得读写或轮转用户的运行日志目录。"""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import time


API_ROOT = Path(__file__).resolve().parents[1]


def _snapshot(directory: Path) -> dict[str, tuple[bytes, int, int]]:
    return {
        path.name: (path.read_bytes(), path.stat().st_size, path.stat().st_mtime_ns)
        for path in sorted(directory.iterdir())
        if path.is_file()
    }


def test_child_pytest_does_not_touch_preconfigured_runtime_log_dir(tmp_path: Path):
    protected_log_dir = tmp_path / "runtime-logs-must-not-change"
    protected_log_dir.mkdir()

    current = protected_log_dir / "app.log"
    current.write_bytes(b'2026-06-01 runtime evidence\n')
    old_timestamp = time.time() - 90 * 24 * 60 * 60
    os.utime(current, (old_timestamp, old_timestamp))
    for day in range(1, 36):
        (protected_log_dir / f"app.log.2026-06-{day:02d}").write_bytes(
            f"archive-{day}\n".encode()
        )

    before = _snapshot(protected_log_dir)
    env = os.environ.copy()
    env["LOG_DIR"] = str(protected_log_dir)

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/test_rule_gates.py::test_g17_tests_never_bring_up_hal_in_real_mode",
            "-q",
        ],
        cwd=API_ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert _snapshot(protected_log_dir) == before
