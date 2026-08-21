"""Read-only inventory for Meta-3D development DB and log artifacts.

The command intentionally has no mutation mode.  Unknown identity, unavailable
probes, active handles, and non-empty databases all fail closed to ``protect``.
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import subprocess
from pathlib import Path
from typing import Any, Callable, Iterable


KNOWN_TEST_DATABASES = frozenset(
    {
        "test_channel_calibration.db",
        "test_probe_calibration.db",
        "test_probe_calibration_service.db",
        "test_probe_calibration_integration.db",
    }
)
SQLITE_SUFFIXES = frozenset({".db", ".sqlite", ".sqlite3"})
CommandRunner = Callable[[list[str]], Any]


def _default_command_runner(args: list[str]):
    return subprocess.run(args, check=False, capture_output=True, text=True)


def _command_output(command_runner: CommandRunner, args: list[str]) -> tuple[int, str]:
    result = command_runner(args)
    if isinstance(result, str):
        return 0, result
    return int(result.returncode), str(result.stdout)


def _parse_worktrees(text: str) -> list[dict[str, str | None]]:
    worktrees: list[dict[str, str | None]] = []
    current: dict[str, str | None] | None = None
    for line in [*text.splitlines(), ""]:
        if line.startswith("worktree "):
            if current:
                worktrees.append(current)
            current = {"path": line.removeprefix("worktree "), "head": None, "branch": None}
        elif current is not None and line.startswith("HEAD "):
            current["head"] = line.removeprefix("HEAD ")
        elif current is not None and line.startswith("branch "):
            current["branch"] = line.removeprefix("branch refs/heads/")
        elif not line and current:
            worktrees.append(current)
            current = None
    return worktrees


def _git_state(worktree: Path, path: Path) -> str:
    relative = os.fspath(path.relative_to(worktree))
    ignored = subprocess.run(
        ["git", "-C", os.fspath(worktree), "check-ignore", "-q", "--", relative],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if ignored.returncode == 0:
        return "ignored"
    tracked = subprocess.run(
        ["git", "-C", os.fspath(worktree), "ls-files", "--error-unmatch", "--", relative],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return "tracked" if tracked.returncode == 0 else "untracked"


def detect_open_state(path: Path) -> str:
    """Return open/closed/unknown without changing the target."""
    return detect_open_states([path])[path.resolve()]


def detect_open_states(
    paths: Iterable[Path],
    *,
    directory: Path | None = None,
) -> dict[Path, str]:
    """Probe a group of files in one ``lsof`` call.

    Log directories can contain hundreds of files; invoking ``lsof`` once per
    file makes a dry-run slower than the application startup it is auditing.
    ``-Fn`` keeps output machine-readable without opening file contents.
    """
    resolved = tuple(dict.fromkeys(path.resolve() for path in paths))
    if not resolved:
        return {}
    try:
        selection = (
            ["+D", os.fspath(directory.resolve())]
            if directory is not None
            else ["--", *(os.fspath(path) for path in resolved)]
        )
        result = subprocess.run(
            ["lsof", "-Fn", *selection],
            check=False,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        return {path: "unknown" for path in resolved}
    # macOS lsof can return 1 for +D while still emitting valid matches (for
    # example when one process exits during the directory walk).  Valid name
    # records are positive evidence and must not be discarded with the status.
    if result.stdout:
        open_paths = {
            Path(line[1:]).resolve()
            for line in result.stdout.splitlines()
            if line.startswith("n/")
        }
        return {path: "open" if path in open_paths else "closed" for path in resolved}
    if result.returncode == 1:
        return {path: "closed" for path in resolved}
    return {path: "unknown" for path in resolved}


def _sqlite_evidence(path: Path) -> tuple[list[str], bool]:
    try:
        with path.open("rb") as stream:
            if stream.read(16) != b"SQLite format 3\x00":
                return ["sqlite_invalid"], False
        uri = f"file:{path.as_posix()}?mode=ro"
        with sqlite3.connect(uri, uri=True) as db:
            tables = tuple(
                row[0]
                for row in db.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
                )
            )
    except (OSError, sqlite3.DatabaseError):
        return ["sqlite_invalid"], False
    if tables:
        return ["sqlite_valid", "sqlite_schema_nonempty"], False
    return ["sqlite_valid", "sqlite_schema_empty"], True


def _known_test_location(worktree: Path, path: Path) -> bool:
    if path.name not in KNOWN_TEST_DATABASES:
        return False
    relative = path.relative_to(worktree).parts
    return relative == (path.name,) or relative == ("api-service", path.name)


def _artifact_entry(
    worktree: dict[str, Any],
    path: Path,
    *,
    kind: str,
    open_state: str | None = None,
) -> dict[str, Any]:
    root = Path(str(worktree["path"])).resolve()
    path = path.resolve()
    stat = path.stat()
    open_state = open_state or detect_open_state(path)
    git_state = _git_state(root, path)
    evidence = [f"git_{git_state}", f"worktree_head:{worktree.get('head') or 'unknown'}"]
    disposition = "protect"
    reason = "identity is not sufficient for cleanup"

    if kind == "log":
        evidence.append("explicit_log_root")
        if open_state == "closed":
            disposition = "review"
            reason = "closed log still requires retention and provenance review"
        elif open_state == "open":
            reason = "active process has the log open"
        else:
            reason = "open-handle detection unavailable or inconclusive"
    else:
        sqlite_evidence, schema_empty = _sqlite_evidence(path)
        evidence.extend(sqlite_evidence)
        known_location = _known_test_location(root, path)
        if known_location:
            evidence.append("known_test_producer")
        if (
            known_location
            and schema_empty
            and git_state in {"ignored", "untracked"}
            and open_state == "closed"
        ):
            disposition = "quarantine_candidate"
            reason = "exact legacy test producer, empty SQLite schema, and no open handle"
        elif open_state == "open":
            reason = "database is open by a process"
        elif open_state == "unknown":
            reason = "open-handle detection unavailable or inconclusive"
        elif not schema_empty:
            reason = "database is invalid or has a non-empty schema"

    return {
        "bytes": stat.st_size,
        "disposition": disposition,
        "git_state": git_state,
        "identity_evidence": sorted(evidence),
        "kind": kind,
        "mtime_ns": stat.st_mtime_ns,
        "open_state": open_state,
        "path": os.fspath(path),
        "reason": reason,
        "worktree_branch": worktree.get("branch"),
        "worktree_head": worktree.get("head"),
        "worktree_path": os.fspath(root),
    }


def _candidate_database_paths(worktree: Path) -> Iterable[Path]:
    for directory in (worktree, worktree / "api-service", worktree / "api-service" / "app"):
        if not directory.is_dir():
            continue
        for path in directory.iterdir():
            if path.is_symlink() or not path.is_file() or path.suffix.lower() not in SQLITE_SUFFIXES:
                continue
            yield path


def _filesystem_artifacts(worktrees: list[dict[str, Any]]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    seen: set[str] = set()
    for worktree in worktrees:
        root = Path(str(worktree["path"])).resolve()
        log_root = root / "api-service" / "logs"
        if log_root.is_dir() and not log_root.is_symlink():
            log_paths = [
                path
                for path in sorted(log_root.rglob("*"))
                if not path.is_symlink() and path.is_file()
            ]
            open_states = detect_open_states(log_paths, directory=log_root)
            for path in log_paths:
                key = os.fspath(path.resolve())
                if key not in seen:
                    entries.append(
                        _artifact_entry(
                            worktree,
                            path,
                            kind="log",
                            open_state=open_states[path.resolve()],
                        )
                    )
                    seen.add(key)
        for path in _candidate_database_paths(root):
            key = os.fspath(path.resolve())
            if key not in seen:
                entries.append(_artifact_entry(worktree, path, kind="sqlite"))
                seen.add(key)
    return sorted(entries, key=lambda entry: entry["path"])


def classify_docker_volume(volume: dict[str, Any]) -> dict[str, Any]:
    entry = dict(volume)
    mounted_by = list(entry.get("mounted_by") or [])
    labels = dict(entry.get("labels") or {})
    name = str(entry.get("name", "unknown"))
    evidence = list(entry.get("identity_evidence") or [])
    if mounted_by:
        disposition = "protect"
        reason = "volume is referenced by a container"
        evidence.append("container_mounted")
    elif name == "meta3d_postgres_data":
        disposition = "protect"
        reason = "named Meta-3D development database volume"
        evidence.append("meta3d_named_volume")
    elif "com.docker.volume.anonymous" in labels:
        disposition = "review"
        reason = "unmounted anonymous volume has insufficient project identity"
        evidence.append("docker_anonymous")
    else:
        disposition = "protect"
        reason = "unmounted volume has unknown ownership"
        evidence.append("docker_owner_unknown")
    entry.update(
        {
            "disposition": disposition,
            "identity_evidence": sorted(evidence),
            "kind": "docker_volume",
            "mounted_by": mounted_by,
            "name": name,
            "path": f"docker://volume/{name}",
            "reason": reason,
        }
    )
    return entry


def _collect_docker_volumes(command_runner: CommandRunner) -> list[dict[str, Any]]:
    code, output = _command_output(command_runner, ["docker", "volume", "ls", "-q"])
    if code != 0:
        raise RuntimeError("docker volume ls failed")
    volumes: list[dict[str, Any]] = []
    for name in sorted(filter(None, output.splitlines())):
        inspect_code, inspect_output = _command_output(
            command_runner,
            ["docker", "volume", "inspect", name, "--format", "{{json .}}"],
        )
        mount_code, mount_output = _command_output(
            command_runner,
            ["docker", "ps", "-a", "--filter", f"volume={name}", "--format", "{{.Names}}"],
        )
        if inspect_code != 0 or mount_code != 0:
            volumes.append(
                classify_docker_volume(
                    {"name": name, "labels": {}, "mounted_by": [], "probe_state": "incomplete"}
                )
            )
            continue
        try:
            metadata = json.loads(inspect_output)
        except json.JSONDecodeError:
            metadata = {}
        volumes.append(
            classify_docker_volume(
                {
                    "created_at": metadata.get("CreatedAt"),
                    "labels": metadata.get("Labels") or {},
                    "mounted_by": sorted(filter(None, mount_output.splitlines())),
                    "name": name,
                    "probe_state": "available" if metadata else "malformed",
                }
            )
        )
    return volumes


def build_inventory(
    repo_root: Path | str,
    *,
    include_docker: bool = True,
    command_runner: CommandRunner = _default_command_runner,
) -> dict[str, Any]:
    repo_root = Path(repo_root).resolve()
    code, output = _command_output(
        command_runner,
        ["git", "-C", os.fspath(repo_root), "worktree", "list", "--porcelain"],
    )
    if code != 0:
        raise RuntimeError("git worktree inventory failed")
    worktrees = _parse_worktrees(output)
    for worktree in worktrees:
        path = Path(str(worktree["path"])).resolve()
        status = subprocess.run(
            ["git", "-C", os.fspath(path), "status", "--porcelain"],
            check=False,
            capture_output=True,
            text=True,
        )
        worktree["path"] = os.fspath(path)
        worktree["dirty"] = bool(status.stdout.strip()) if status.returncode == 0 else None

    docker_volumes: list[dict[str, Any]] = []
    docker_probe = "skipped"
    if include_docker:
        try:
            docker_volumes = _collect_docker_volumes(command_runner)
            docker_probe = "available"
        except (FileNotFoundError, RuntimeError, OSError):
            docker_probe = "unavailable"

    return {
        "artifacts": _filesystem_artifacts(worktrees),
        "docker_volumes": sorted(docker_volumes, key=lambda entry: entry["name"]),
        "probes": {"docker": docker_probe},
        "repo_root": os.fspath(repo_root),
        "schema_version": 1,
        "worktrees": sorted(worktrees, key=lambda entry: str(entry["path"])),
    }


def render_json(manifest: dict[str, Any]) -> str:
    return json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def render_markdown(manifest: dict[str, Any]) -> str:
    lines = [
        "# Meta-3D development artifact inventory",
        "",
        f"Repository: `{manifest['repo_root']}`",
        "",
        "## Filesystem artifacts",
        "",
        "| Disposition | Kind | Bytes | Open | Path | Reason |",
        "|---|---|---:|---|---|---|",
    ]
    for entry in manifest["artifacts"]:
        lines.append(
            f"| {entry['disposition']} | {entry['kind']} | {entry['bytes']} | "
            f"{entry['open_state']} | {entry['path']} | {entry['reason']} |"
        )
    lines.extend(["", "## Docker volumes", "", "| Disposition | Volume | Mounted by | Reason |", "|---|---|---|---|"])
    for entry in manifest["docker_volumes"]:
        lines.append(
            f"| {entry['disposition']} | {entry['path']} | "
            f"{', '.join(entry['mounted_by']) or '-'} | {entry['reason']} |"
        )
    return "\n".join(lines) + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate a read-only DB/log/worktree inventory")
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--format", choices=("json", "markdown"), default="json")
    parser.add_argument("--no-docker", action="store_true", help="Skip read-only Docker metadata probes")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    manifest = build_inventory(args.repo_root, include_docker=not args.no_docker)
    print(render_markdown(manifest) if args.format == "markdown" else render_json(manifest), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
