"""P2-31: mounted SMB .smu project truth inventory.

The filename is deliberately untrusted.  These tests use a local temporary directory as the
read-only SMB copy and prove that inventory truth comes from Channel Group 0 inside the file.
"""
from __future__ import annotations

from pathlib import Path
import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.database import Base
from app.models.channel_asset import ChannelAsset
from app.models.instrument import InstrumentCategory, InstrumentConnection
from app.services.channel_asset_service import create_channel_asset


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


_OLD_SCD = {
    "band": "N78",
    "arfcn": 640000,
    "bandwidth_mhz": 100,
    "model": "CDLC",
    "scenario": "UMa",
    "mimo": "4x4",
    "polarization": "DP",
    "version": 1,
}


@pytest.fixture
def inventory_db(tmp_path: Path):
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    category = InstrumentCategory(
        category_key="channelEmulator",
        category_name="信道仿真器",
    )
    db.add(category)
    db.flush()
    connection = InstrumentConnection(
        category_id=category.id,
        connection_params={
            "smu_project_scan": {
                "local_mount_root": str(tmp_path),
                "instrument_root": r"D:\Scenario Packs",
            },
            "available_channel_models": [],
            "unknown_connection_key": {"keep": True},
        },
    )
    db.add(connection)
    db.commit()
    try:
        yield db, connection, tmp_path
    finally:
        db.close()
        Base.metadata.drop_all(engine)


def _create_vendor_asset(
    db,
    *,
    name: str,
    path: str,
    binding_id=None,
    active: bool = True,
    payload_extra: dict | None = None,
):
    scd = dict(_OLD_SCD)
    # ChannelAsset canonical_name is globally unique.  Tests that need two assets (including the
    # deliberate duplicate-path case) vary only the irrelevant version so setup itself remains
    # valid and the scanner, not the CRUD uniqueness guard, decides the path status.
    scd["version"] = sum(ord(char) for char in name) + 1
    payload = {"scd_config": scd, **(payload_extra or {})}
    asset = create_channel_asset(
        db,
        name=name,
        source_type="vendor_file",
        payload=payload,
        associated_file_path=path,
        center_frequency_hz=3_600_000_000,
        bandwidth_mhz=100,
        instrument_connection_id=binding_id,
    )
    if not active:
        asset.is_active = False
        db.commit()
    return asset


def test_preview_matches_only_the_complete_windows_path_and_migrates_null_binding(
    inventory_db,
):
    from app.services.smu_project_inventory import preview_smu_project_sync

    db, connection, root = inventory_db
    _write_smu(
        root / "pack" / "truth.smu",
        "[Channel Group 0]\nCenterFrequency=3549990000 Hz\n",
    )
    asset = _create_vendor_asset(
        db,
        name="truth",
        path=r"d:/scenario packs/PACK/truth.smu",
    )
    # Same basename must not be considered a second match.
    _create_vendor_asset(
        db,
        name="same-basename-elsewhere",
        path=r"D:\Other\truth.smu",
    )

    preview = preview_smu_project_sync(db)

    assert len(preview.items) == 1
    item = preview.items[0]
    assert item.sync_status == "syncable"
    assert item.asset_id == asset.id
    assert item.target_arfcn == 636666
    assert item.connection_id == connection.id


def test_preview_protects_unregistered_duplicate_inactive_other_binding_and_non_raster(
    inventory_db,
):
    from app.services.smu_project_inventory import preview_smu_project_sync

    db, connection, root = inventory_db
    cases = {
        "unregistered.smu": 3_600_000_000,
        "duplicate.smu": 3_600_000_000,
        "inactive.smu": 3_600_000_000,
        "other-binding.smu": 3_600_000_000,
        "non-raster.smu": 4_700_000_000,
    }
    for filename, frequency in cases.items():
        _write_smu(
            root / filename,
            f"[Channel Group 0]\nCenterFrequency={frequency} Hz\n",
        )
    duplicate_path = r"D:\Scenario Packs\duplicate.smu"
    _create_vendor_asset(db, name="dup-a", path=duplicate_path)
    _create_vendor_asset(db, name="dup-b", path=duplicate_path)
    _create_vendor_asset(
        db,
        name="inactive",
        path=r"D:\Scenario Packs\inactive.smu",
        active=False,
    )
    _create_vendor_asset(
        db,
        name="other-binding",
        path=r"D:\Scenario Packs\other-binding.smu",
        binding_id=uuid.uuid4(),
    )
    _create_vendor_asset(
        db,
        name="non-raster",
        path=r"D:\Scenario Packs\non-raster.smu",
    )

    statuses = {
        Path(item.relative_path).name: item.sync_status
        for item in preview_smu_project_sync(db).items
    }

    assert statuses == {
        "duplicate.smu": "ambiguous_asset",
        "inactive.smu": "inactive_asset",
        "non-raster.smu": "non_nr_raster",
        "other-binding.smu": "binding_conflict",
        "unregistered.smu": "unregistered",
    }
    assert connection.connection_params["available_channel_models"] == []


def test_sync_updates_asset_and_projection_together_while_preserving_unknown_keys(
    inventory_db,
):
    from app.services.smu_project_inventory import (
        preview_smu_project_sync,
        sync_smu_project_truth,
    )

    db, connection, root = inventory_db
    relative = "pack/truth.smu"
    windows_path = r"D:\Scenario Packs\pack\truth.smu"
    _write_smu(
        root / relative,
        "[Channel Group 0]\nCenterFrequency=3549990000 Hz\n"
        "[Channel Group 1]\nCenterFrequency=3600000000 Hz\n",
    )
    asset = _create_vendor_asset(
        db,
        name="truth",
        path=windows_path,
        payload_extra={"unknown_payload": {"keep": [1, 2, 3]}},
    )
    connection.connection_params = {
        **connection.connection_params,
        "available_channel_models": [
            {
                "filename": windows_path,
                "label": "old",
                "center_frequency_mhz": 3600.0,
                "unknown_projection": {"keep": True},
            },
            {
                "filename": r"D:\Other\untouched.smu",
                "label": "untouched",
                "center_frequency_mhz": 1234.5,
            },
        ],
    }
    db.commit()

    result = sync_smu_project_truth(db)
    db.expire_all()
    stored = db.get(ChannelAsset, asset.id)
    db.refresh(connection)

    assert result.updated_count == 1
    assert stored.instrument_connection_id == connection.id
    assert stored.center_frequency_hz == 3_549_990_000
    assert stored.payload["scd_config"]["arfcn"] == 636666
    assert stored.payload["unknown_payload"] == {"keep": [1, 2, 3]}
    truth = stored.payload["smu_project_truth"]
    assert truth["schema_version"] == 1
    assert truth["instrument_path"] == windows_path
    assert truth["primary_group"] == 0
    assert truth["center_frequencies_hz"] in (
        {"0": 3_549_990_000, "1": 3_600_000_000},
        {0: 3_549_990_000, 1: 3_600_000_000},
    )
    assert truth["sha256"]
    assert "636666" in stored.canonical_name

    projections = connection.connection_params["available_channel_models"]
    synced = next(p for p in projections if p["filename"] == windows_path)
    untouched = next(p for p in projections if p["filename"].endswith("untouched.smu"))
    assert synced["center_frequency_mhz"] == 3549.99
    assert synced["channel_asset_id"] == str(asset.id)
    assert synced["unknown_projection"] == {"keep": True}
    assert untouched == {
        "filename": r"D:\Other\untouched.smu",
        "label": "untouched",
        "center_frequency_mhz": 1234.5,
    }
    assert connection.connection_params["unknown_connection_key"] == {"keep": True}

    # A second scan sees both the asset and projection as current and performs no write.
    preview = preview_smu_project_sync(db)
    assert preview.items[0].sync_status == "already_synced"
    again = sync_smu_project_truth(db)
    assert again.updated_count == 0
    assert again.already_synced_count == 1


def test_sync_rolls_back_all_candidates_when_commit_fails(inventory_db, monkeypatch):
    from app.services.smu_project_inventory import (
        SMUProjectSyncError,
        sync_smu_project_truth,
    )

    db, connection, root = inventory_db
    for name, frequency in (("a.smu", 3_549_990_000), ("b.smu", 3_600_000_000)):
        _write_smu(
            root / name,
            f"[Channel Group 0]\nCenterFrequency={frequency} Hz\n",
        )
        _create_vendor_asset(
            db,
            name=name,
            path=rf"D:\Scenario Packs\{name}",
        )
    before = {
        asset.id: (asset.center_frequency_hz, dict(asset.payload))
        for asset in db.query(ChannelAsset).all()
    }

    def fail_commit():
        raise RuntimeError("forced commit failure")

    monkeypatch.setattr(db, "commit", fail_commit)
    with pytest.raises(SMUProjectSyncError, match="forced commit failure"):
        sync_smu_project_truth(db)
    db.expire_all()

    after = {
        asset.id: (asset.center_frequency_hz, dict(asset.payload))
        for asset in db.query(ChannelAsset).all()
    }
    assert after == before
    db.refresh(connection)
    assert connection.connection_params["available_channel_models"] == []
