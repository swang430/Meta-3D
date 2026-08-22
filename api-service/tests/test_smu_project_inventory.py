"""P2-31: mounted SMB .smu project truth inventory.

The filename is deliberately untrusted.  These tests use a local temporary directory as the
read-only SMB copy and prove that inventory truth comes from Channel Group 0 inside the file.
"""
from __future__ import annotations

from pathlib import Path

import pytest


def _write_smu(path: Path, text: str, *, encoding: str = "utf-8") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode(encoding))


def test_scan_uses_group_zero_truth_instead_of_lying_filename(tmp_path: Path):
    from app.services.smu_project_inventory import scan_smu_projects

    project = tmp_path / "pack" / "3GPP_FR1_OTA_CDLC_UMa_3600M.smu"
    _write_smu(
        project,
        "[Channel Group 0]\nCenterFrequency = 3549990000 Hz\n",
    )

    result = scan_smu_projects(tmp_path, r"D:\Scenario Packs")

    assert len(result.items) == 1
    item = result.items[0]
    assert item.relative_path == "pack/3GPP_FR1_OTA_CDLC_UMa_3600M.smu"
    assert item.instrument_path == (
        r"D:\Scenario Packs\pack\3GPP_FR1_OTA_CDLC_UMa_3600M.smu"
    )
    assert item.center_frequencies_hz == {0: 3_549_990_000}
    assert item.primary_center_frequency_hz == 3_549_990_000
    assert item.status == "ok"
    assert item.sha256


def test_scan_preserves_all_groups_but_requires_explicit_group_zero(tmp_path: Path):
    from app.services.smu_project_inventory import scan_smu_projects

    _write_smu(
        tmp_path / "all.smu",
        "[Channel Group 0]\nCenterFrequency=3549990000\n"
        "[Channel Group 1]\nCenterFrequency=1842500000 Hz\n",
    )
    _write_smu(
        tmp_path / "only-scell.smu",
        "[Channel Group 1]\nCenterFrequency=2592990000 Hz\n",
    )

    result = scan_smu_projects(tmp_path, r"D:\Scenario Packs")
    by_name = {Path(item.relative_path).name: item for item in result.items}

    assert by_name["all.smu"].center_frequencies_hz == {
        0: 3_549_990_000,
        1: 1_842_500_000,
    }
    assert by_name["all.smu"].status == "ok"
    assert by_name["only-scell.smu"].center_frequencies_hz == {1: 2_592_990_000}
    assert by_name["only-scell.smu"].primary_center_frequency_hz is None
    assert by_name["only-scell.smu"].status == "parse_error"
    assert "Channel Group 0" in (by_name["only-scell.smu"].detail or "")


@pytest.mark.parametrize(
    ("encoding", "prefix"),
    [
        ("utf-8-sig", "备注=场景\n"),
        ("utf-16", "备注=场景\n"),
        ("latin-1", "Note=caf\xe9\n"),
    ],
)
def test_scan_supports_recorded_text_encodings(
    tmp_path: Path, encoding: str, prefix: str,
):
    from app.services.smu_project_inventory import scan_smu_projects

    _write_smu(
        tmp_path / f"{encoding}.smu",
        prefix + "[Channel Group 0]\nCenterFrequency=3600000000 Hz\n",
        encoding=encoding,
    )

    item = scan_smu_projects(tmp_path, r"D:\Scenario Packs").items[0]
    assert item.status == "ok"
    assert item.primary_center_frequency_hz == 3_600_000_000


def test_scan_skips_symlink_files_and_directories_without_following_them(tmp_path: Path):
    from app.services.smu_project_inventory import scan_smu_projects

    outside = tmp_path.parent / f"{tmp_path.name}-outside"
    outside.mkdir()
    _write_smu(outside / "outside.smu", "[Channel Group 0]\nCenterFrequency=1\n")
    (tmp_path / "linked.smu").symlink_to(outside / "outside.smu")
    (tmp_path / "linked-dir").symlink_to(outside, target_is_directory=True)
    _write_smu(tmp_path / "real.smu", "[Channel Group 0]\nCenterFrequency=2\n")

    result = scan_smu_projects(tmp_path, r"D:\Scenario Packs")

    assert [item.relative_path for item in result.items] == ["real.smu"]
    assert set(result.protected_paths) == {"linked-dir/", "linked.smu"}


@pytest.mark.parametrize("root_kind", ["relative", "missing", "symlink"])
def test_scan_rejects_untrusted_mount_roots(tmp_path: Path, root_kind: str):
    from app.services.smu_project_inventory import (
        SMUProjectInventoryError,
        scan_smu_projects,
    )

    if root_kind == "relative":
        root: Path | str = "relative/path"
    elif root_kind == "missing":
        root = tmp_path / "missing"
    else:
        real = tmp_path / "real"
        real.mkdir()
        link = tmp_path / "root-link"
        link.symlink_to(real, target_is_directory=True)
        root = link

    with pytest.raises(SMUProjectInventoryError):
        scan_smu_projects(root, r"D:\Scenario Packs")


def test_scan_rejects_relative_instrument_root(tmp_path: Path):
    from app.services.smu_project_inventory import (
        SMUProjectInventoryError,
        scan_smu_projects,
    )

    with pytest.raises(SMUProjectInventoryError):
        scan_smu_projects(tmp_path, "Scenario Packs")


def test_scan_fails_whole_inventory_when_file_count_limit_is_exceeded(tmp_path: Path):
    from app.services.smu_project_inventory import (
        SMUProjectInventoryError,
        scan_smu_projects,
    )

    for name in ("a.smu", "b.smu"):
        _write_smu(tmp_path / name, "[Channel Group 0]\nCenterFrequency=1\n")

    with pytest.raises(SMUProjectInventoryError, match="数量上限"):
        scan_smu_projects(tmp_path, r"D:\Scenario Packs", max_files=1)


def test_scan_fails_whole_inventory_when_single_file_limit_is_exceeded(tmp_path: Path):
    from app.services.smu_project_inventory import (
        SMUProjectInventoryError,
        scan_smu_projects,
    )

    _write_smu(tmp_path / "large.smu", "[Channel Group 0]\nCenterFrequency=1\n")

    with pytest.raises(SMUProjectInventoryError, match="单文件上限"):
        scan_smu_projects(tmp_path, r"D:\Scenario Packs", max_file_bytes=8)


def test_scan_fails_whole_inventory_when_total_byte_limit_is_exceeded(tmp_path: Path):
    from app.services.smu_project_inventory import (
        SMUProjectInventoryError,
        scan_smu_projects,
    )

    for name in ("a.smu", "b.smu"):
        _write_smu(tmp_path / name, "[Channel Group 0]\nCenterFrequency=1\n")

    with pytest.raises(SMUProjectInventoryError, match="总读取上限"):
        scan_smu_projects(tmp_path, r"D:\Scenario Packs", max_total_bytes=60)
