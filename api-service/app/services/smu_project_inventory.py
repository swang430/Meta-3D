"""Bounded, read-only inventory of F64 ``.smu`` project copies (P2-31).

The caller supplies a server-side configured local SMB mount and its corresponding F64 Windows
root.  This module never mounts a share, handles credentials, or writes either filesystem.  The
only frequency truth is ``[Channel Group 0] CenterFrequency`` inside the project; filenames are
display-only and are deliberately never parsed here.
"""
from __future__ import annotations

import hashlib
import os
import stat
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath
from typing import Mapping, Sequence

from app.hal.smu_project import parse_smu_project_center_freqs_hz


DEFAULT_MAX_FILES = 1024
DEFAULT_MAX_FILE_BYTES = 8 * 1024 * 1024
DEFAULT_MAX_TOTAL_BYTES = 64 * 1024 * 1024


class SMUProjectInventoryError(ValueError):
    """The configured root or bounded scan cannot produce a complete trustworthy inventory."""


@dataclass(frozen=True)
class SMUProjectInventoryItem:
    relative_path: str
    instrument_path: str
    size_bytes: int
    sha256: str
    center_frequencies_hz: Mapping[int, int]
    primary_center_frequency_hz: int | None
    status: str
    detail: str | None = None


@dataclass(frozen=True)
class SMUProjectInventory:
    items: Sequence[SMUProjectInventoryItem]
    protected_paths: Sequence[str]
    total_files: int
    total_bytes: int


def _raise_walk_error(error: OSError) -> None:
    raise SMUProjectInventoryError(f"SMB 扫描目录不可读: {error}") from error


def _validate_roots(
    local_mount_root: Path | str, instrument_root: str,
) -> tuple[Path, PureWindowsPath]:
    root = Path(local_mount_root)
    if not root.is_absolute():
        raise SMUProjectInventoryError(
            f"smu_project_scan.local_mount_root 必须是绝对路径，实际 {str(root)!r}"
        )
    # Check the configured object before resolve(): resolve would hide that the root itself is a
    # symlink and silently broaden the configured trust boundary.
    if root.is_symlink():
        raise SMUProjectInventoryError(
            f"smu_project_scan.local_mount_root 不得是符号链接: {root}"
        )
    try:
        resolved = root.resolve(strict=True)
    except OSError as exc:
        raise SMUProjectInventoryError(f"SMB 只读挂载不存在或不可解析: {root}: {exc}") from exc
    if not resolved.is_dir():
        raise SMUProjectInventoryError(f"SMB 只读挂载根不是目录: {resolved}")

    windows_root = PureWindowsPath(instrument_root)
    if not instrument_root or not windows_root.is_absolute():
        raise SMUProjectInventoryError(
            "smu_project_scan.instrument_root 必须是绝对 Windows/UNC 路径，"
            f"实际 {instrument_root!r}"
        )
    return resolved, windows_root


def _relative_display(path: Path, root: Path, *, directory: bool = False) -> str:
    value = path.relative_to(root).as_posix()
    return f"{value}/" if directory else value


def _enumerate_projects(root: Path, *, max_files: int) -> tuple[list[Path], list[str]]:
    candidates: list[Path] = []
    protected: list[str] = []
    for current, dirnames, filenames in os.walk(
        root, topdown=True, followlinks=False, onerror=_raise_walk_error,
    ):
        current_path = Path(current)

        # os.walk does not follow symlink directories with followlinks=False, but keeping them in
        # dirnames makes that behavior implicit and omits the protected path from the result.
        safe_dirs: list[str] = []
        for dirname in sorted(dirnames, key=str.casefold):
            child = current_path / dirname
            if child.is_symlink():
                protected.append(_relative_display(child, root, directory=True))
            else:
                safe_dirs.append(dirname)
        dirnames[:] = safe_dirs

        for filename in sorted(filenames, key=str.casefold):
            if not filename.lower().endswith(".smu"):
                continue
            child = current_path / filename
            if child.is_symlink():
                protected.append(_relative_display(child, root))
                continue
            candidates.append(child)
            if len(candidates) > max_files:
                raise SMUProjectInventoryError(
                    f".smu 数量上限 {max_files} 已超过；拒绝返回不完整清单"
                )
    candidates.sort(key=lambda path: path.relative_to(root).as_posix().casefold())
    protected.sort(key=str.casefold)
    return candidates, protected


def _read_regular_file_bounded(path: Path, *, max_file_bytes: int) -> bytes:
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise SMUProjectInventoryError(f".smu 文件不可安全打开: {path}: {exc}") from exc
    try:
        file_stat = os.fstat(fd)
        if not stat.S_ISREG(file_stat.st_mode):
            raise SMUProjectInventoryError(f".smu 路径不是普通文件: {path}")
        if file_stat.st_size > max_file_bytes:
            raise SMUProjectInventoryError(
                f".smu 单文件上限 {max_file_bytes} bytes 已超过: {path} "
                f"({file_stat.st_size} bytes)"
            )
        with os.fdopen(fd, "rb", closefd=False) as stream:
            data = stream.read(max_file_bytes + 1)
        if len(data) > max_file_bytes:
            raise SMUProjectInventoryError(
                f".smu 单文件上限 {max_file_bytes} bytes 在读取期间已超过: {path}"
            )
        return data
    finally:
        os.close(fd)


def _decode_project(data: bytes) -> str:
    if data.startswith(b"\xef\xbb\xbf"):
        return data.decode("utf-8-sig")
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        # latin-1 is a lossless byte mapping.  It does not infer engineering data; it only keeps
        # the ASCII section/key tokens visible to the existing strict parser.
        return data.decode("latin-1")


def scan_smu_projects(
    local_mount_root: Path | str,
    instrument_root: str,
    *,
    max_files: int = DEFAULT_MAX_FILES,
    max_file_bytes: int = DEFAULT_MAX_FILE_BYTES,
    max_total_bytes: int = DEFAULT_MAX_TOTAL_BYTES,
) -> SMUProjectInventory:
    """Return a complete bounded inventory or fail without producing a partial result.

    Limit arguments are internal policy hooks (and make boundary tests cheap); API callers do not
    accept them from clients.
    """
    if min(max_files, max_file_bytes, max_total_bytes) <= 0:
        raise SMUProjectInventoryError("扫描上限必须全部为正整数")
    root, windows_root = _validate_roots(local_mount_root, instrument_root)
    paths, protected = _enumerate_projects(root, max_files=max_files)

    items: list[SMUProjectInventoryItem] = []
    total_bytes = 0
    for path in paths:
        data = _read_regular_file_bounded(path, max_file_bytes=max_file_bytes)
        total_bytes += len(data)
        if total_bytes > max_total_bytes:
            raise SMUProjectInventoryError(
                f".smu 总读取上限 {max_total_bytes} bytes 已超过；拒绝返回不完整清单"
            )
        relative = path.relative_to(root)
        frequencies = dict(sorted(parse_smu_project_center_freqs_hz(_decode_project(data)).items()))
        primary = frequencies.get(0)
        status = "ok" if primary is not None else "parse_error"
        detail = None if primary is not None else (
            "工程缺少可核对的 [Channel Group 0] CenterFrequency；不得用文件名或其他组回退"
        )
        items.append(SMUProjectInventoryItem(
            relative_path=relative.as_posix(),
            instrument_path=str(windows_root.joinpath(*relative.parts)),
            size_bytes=len(data),
            sha256=hashlib.sha256(data).hexdigest(),
            center_frequencies_hz=frequencies,
            primary_center_frequency_hz=primary,
            status=status,
            detail=detail,
        ))

    return SMUProjectInventory(
        items=tuple(items),
        protected_paths=tuple(protected),
        total_files=len(items),
        total_bytes=total_bytes,
    )
