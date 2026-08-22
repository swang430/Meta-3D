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
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath
from typing import Mapping, Sequence
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.hal.nr_arfcn import freq_mhz_to_nr_arfcn, nr_arfcn_to_freq_mhz
from app.hal.smu_project import parse_smu_project_center_freqs_hz
from app.models.channel_asset import ChannelAsset
from app.models.instrument import InstrumentCategory, InstrumentConnection


DEFAULT_MAX_FILES = 1024
DEFAULT_MAX_FILE_BYTES = 8 * 1024 * 1024
DEFAULT_MAX_TOTAL_BYTES = 64 * 1024 * 1024


class SMUProjectInventoryError(ValueError):
    """The configured root or bounded scan cannot produce a complete trustworthy inventory."""


class SMUProjectSyncError(ValueError):
    """The database projection could not be synchronized as one atomic operation."""


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


@dataclass(frozen=True)
class SMUProjectSyncItem:
    relative_path: str
    instrument_path: str
    size_bytes: int
    sha256: str
    center_frequencies_hz: Mapping[int, int]
    primary_center_frequency_hz: int | None
    scan_status: str
    scan_detail: str | None
    sync_status: str
    sync_detail: str
    connection_id: UUID
    asset_id: UUID | None = None
    asset_name: str | None = None
    target_arfcn: int | None = None


@dataclass(frozen=True)
class SMUProjectSyncPreview:
    connection_id: UUID
    items: Sequence[SMUProjectSyncItem]
    protected_paths: Sequence[str]
    total_files: int
    total_bytes: int


@dataclass(frozen=True)
class SMUProjectSyncResult:
    updated_count: int
    already_synced_count: int
    preview: SMUProjectSyncPreview


@dataclass(frozen=True)
class _SyncPlan:
    item: SMUProjectInventoryItem
    asset: ChannelAsset
    payload: dict
    canonical_name: str
    target_arfcn: int
    truth: dict


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


def _normalise_windows_path(value: object) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    return str(PureWindowsPath(value.strip())).casefold()


def _resolve_scan_context(db: Session) -> tuple[InstrumentConnection, SMUProjectInventory]:
    category = (
        db.query(InstrumentCategory)
        .filter(InstrumentCategory.category_key == "channelEmulator")
        .one_or_none()
    )
    if category is None:
        raise SMUProjectInventoryError("channelEmulator 仪器类别不存在，无法解析 SMB 扫描绑定")
    connection = (
        db.query(InstrumentConnection)
        .filter(InstrumentConnection.category_id == category.id)
        .one_or_none()
    )
    if connection is None:
        raise SMUProjectInventoryError("channelEmulator 连接不存在，无法读取 smu_project_scan 配置")
    params = connection.connection_params
    if not isinstance(params, dict):
        raise SMUProjectInventoryError("channelEmulator.connection_params 必须是对象")
    config = params.get("smu_project_scan")
    if not isinstance(config, dict):
        raise SMUProjectInventoryError(
            "缺少 channelEmulator.connection_params.smu_project_scan 只读挂载配置"
        )
    local_root = config.get("local_mount_root")
    instrument_root = config.get("instrument_root")
    if not isinstance(local_root, str) or not isinstance(instrument_root, str):
        raise SMUProjectInventoryError(
            "smu_project_scan.local_mount_root 与 instrument_root 必须是非空字符串"
        )
    return connection, scan_smu_projects(local_root, instrument_root)


def _exact_nr_arfcn(center_frequency_hz: int) -> int | None:
    try:
        arfcn = freq_mhz_to_nr_arfcn(center_frequency_hz / 1e6)
        round_trip_hz = round(nr_arfcn_to_freq_mhz(arfcn) * 1e6)
    except ValueError:
        return None
    return arfcn if abs(round_trip_hz - center_frequency_hz) <= 1 else None


def _project_truth(item: SMUProjectInventoryItem) -> dict:
    return {
        "schema_version": 1,
        "instrument_path": item.instrument_path,
        "sha256": item.sha256,
        "size_bytes": item.size_bytes,
        "primary_group": 0,
        # JSON object keys are strings by definition.  Build that shape before comparison so
        # PostgreSQL JSONB and SQLite JSON produce the same idempotency decision.
        "center_frequencies_hz": {
            str(group): frequency
            for group, frequency in sorted(item.center_frequencies_hz.items())
        },
    }


def _projection_index(params: dict) -> tuple[list[object], dict[str, list[int]]]:
    raw = params.get("available_channel_models") or []
    if not isinstance(raw, list):
        raise SMUProjectInventoryError(
            "channelEmulator.connection_params.available_channel_models 必须是数组；拒绝覆盖坏形态"
        )
    indexes: dict[str, list[int]] = {}
    for index, entry in enumerate(raw):
        if not isinstance(entry, dict):
            continue
        key = _normalise_windows_path(entry.get("filename"))
        if key is not None:
            indexes.setdefault(key, []).append(index)
    return raw, indexes


def _candidate_plan(
    db: Session,
    connection: InstrumentConnection,
    item: SMUProjectInventoryItem,
    asset: ChannelAsset,
    projection_indexes: dict[str, list[int]],
) -> tuple[_SyncPlan | None, str, str, int | None]:
    if item.primary_center_frequency_hz is None:
        return None, "parse_error", item.detail or "工程主频不可用", None
    target_arfcn = _exact_nr_arfcn(item.primary_center_frequency_hz)
    if target_arfcn is None:
        return (
            None,
            "non_nr_raster",
            f"工程主频 {item.primary_center_frequency_hz} Hz 不能精确往返 NR-ARFCN；禁止取最近栅格",
            None,
        )

    from app.services.channel_asset_service import (
        ChannelAssetError,
        _check_vendor_declared_freq,
        _scd_to_standard_name,
        _validate_payload,
    )

    payload = deepcopy(asset.payload)
    if not isinstance(payload, dict) or not isinstance(payload.get("scd_config"), dict):
        return None, "invalid_asset", "vendor_file 资产缺少 scd_config，拒绝猜测", target_arfcn
    payload["scd_config"] = dict(payload["scd_config"])
    payload["scd_config"]["arfcn"] = target_arfcn
    truth = _project_truth(item)
    payload["smu_project_truth"] = truth
    try:
        _validate_payload("vendor_file", payload)
        # The project body is the authority for this synchronization flow.  The generic asset
        # create/update path still cross-checks parseable MF_ names against operator declarations,
        # but applying that filename gate here would prevent this scanner from correcting the
        # exact stale/misleading filename condition P2-31 exists to replace.
        _check_vendor_declared_freq(
            payload["scd_config"],
            float(item.primary_center_frequency_hz),
            asset.bandwidth_mhz,
        )
        canonical_name = _scd_to_standard_name(payload["scd_config"])
    except (ChannelAssetError, ValueError, TypeError, KeyError) as exc:
        return None, "invalid_asset", str(exc), target_arfcn

    collision = (
        db.query(ChannelAsset)
        .filter(
            ChannelAsset.canonical_name == canonical_name,
            ChannelAsset.id != asset.id,
        )
        .first()
    )
    if collision is not None:
        return (
            None,
            "canonical_conflict",
            f"目标规范名 {canonical_name!r} 已被资产 {collision.name!r} 占用",
            target_arfcn,
        )

    path_key = _normalise_windows_path(item.instrument_path)
    matching_projection = projection_indexes.get(path_key or "", [])
    if len(matching_projection) > 1:
        return (
            None,
            "ambiguous_projection",
            "available_channel_models 中同一完整路径出现多次；拒绝猜测覆盖哪一条",
            target_arfcn,
        )

    plan = _SyncPlan(
        item=item,
        asset=asset,
        payload=payload,
        canonical_name=canonical_name,
        target_arfcn=target_arfcn,
        truth=truth,
    )
    params = connection.connection_params or {}
    raw_models = params.get("available_channel_models") or []
    projection_current = False
    if len(matching_projection) == 1:
        projection = raw_models[matching_projection[0]]
        projection_current = (
            isinstance(projection, dict)
            and projection.get("center_frequency_mhz") == item.primary_center_frequency_hz / 1e6
            and projection.get("channel_asset_id") == str(asset.id)
        )
    already = (
        asset.instrument_connection_id == connection.id
        and asset.associated_file_path == item.instrument_path
        and asset.center_frequency_hz == float(item.primary_center_frequency_hz)
        and asset.payload == payload
        and asset.canonical_name == canonical_name
        and projection_current
    )
    return (
        plan,
        "already_synced" if already else "syncable",
        "资产与 channel-model 投影已等于当前工程内容" if already else "完整路径唯一且工程主频可精确同步",
        target_arfcn,
    )


def _preview_with_plans(
    db: Session,
) -> tuple[SMUProjectSyncPreview, list[_SyncPlan]]:
    connection, inventory = _resolve_scan_context(db)
    params = connection.connection_params or {}
    _, projection_indexes = _projection_index(params)
    assets = db.query(ChannelAsset).filter(ChannelAsset.source_type == "vendor_file").all()
    assets_by_path: dict[str, list[ChannelAsset]] = {}
    for asset in assets:
        key = _normalise_windows_path(asset.associated_file_path)
        if key is not None:
            assets_by_path.setdefault(key, []).append(asset)

    rows: list[SMUProjectSyncItem] = []
    plans: list[_SyncPlan] = []
    for item in inventory.items:
        path_key = _normalise_windows_path(item.instrument_path)
        matches = assets_by_path.get(path_key or "", [])
        asset: ChannelAsset | None = None
        plan: _SyncPlan | None = None
        target_arfcn: int | None = None
        if item.status != "ok":
            sync_status = "parse_error"
            detail = item.detail or "工程主频不可用"
        elif not matches:
            sync_status = "unregistered"
            detail = "未找到完整 F64 路径精确相等的 vendor_file 资产；不会自动创建"
        elif len(matches) > 1:
            sync_status = "ambiguous_asset"
            detail = "同一完整 F64 路径命中多条 vendor_file 资产；拒绝猜测"
        else:
            asset = matches[0]
            if asset.is_active is not True:
                sync_status = "inactive_asset"
                detail = "命中的 vendor_file 资产已停用；历史资产不自动复活或改写"
            elif asset.instrument_connection_id not in (None, connection.id):
                sync_status = "binding_conflict"
                detail = "命中资产已绑定另一仪器连接；拒绝跨绑定改写"
            else:
                plan, sync_status, detail, target_arfcn = _candidate_plan(
                    db, connection, item, asset, projection_indexes,
                )
                if plan is not None and sync_status == "syncable":
                    plans.append(plan)
        rows.append(SMUProjectSyncItem(
            relative_path=item.relative_path,
            instrument_path=item.instrument_path,
            size_bytes=item.size_bytes,
            sha256=item.sha256,
            center_frequencies_hz=item.center_frequencies_hz,
            primary_center_frequency_hz=item.primary_center_frequency_hz,
            scan_status=item.status,
            scan_detail=item.detail,
            sync_status=sync_status,
            sync_detail=detail,
            connection_id=connection.id,
            asset_id=asset.id if asset is not None else None,
            asset_name=asset.name if asset is not None else None,
            target_arfcn=target_arfcn,
        ))

    # Two different files can derive the same canonical name even if neither collides with the
    # current database value.  Block every member before mutation rather than letting the unique
    # constraint choose a partial winner at commit time.
    plans_by_canonical: dict[str, list[_SyncPlan]] = {}
    for plan in plans:
        plans_by_canonical.setdefault(plan.canonical_name, []).append(plan)
    duplicated_ids = {
        plan.asset.id
        for grouped in plans_by_canonical.values() if len(grouped) > 1
        for plan in grouped
    }
    if duplicated_ids:
        plans = [plan for plan in plans if plan.asset.id not in duplicated_ids]
        rows = [
            SMUProjectSyncItem(
                **{
                    **row.__dict__,
                    "sync_status": "canonical_conflict",
                    "sync_detail": "本轮多个工程会派生同一规范名；全部保护且不写入",
                }
            )
            if row.asset_id in duplicated_ids else row
            for row in rows
        ]

    return SMUProjectSyncPreview(
        connection_id=connection.id,
        items=tuple(rows),
        protected_paths=inventory.protected_paths,
        total_files=inventory.total_files,
        total_bytes=inventory.total_bytes,
    ), plans


def preview_smu_project_sync(db: Session) -> SMUProjectSyncPreview:
    """Read current files and database state without mutation."""
    preview, _ = _preview_with_plans(db)
    return preview


def _upsert_projection(
    raw_models: list[object], plan: _SyncPlan,
) -> None:
    target_key = _normalise_windows_path(plan.item.instrument_path)
    match_index: int | None = None
    for index, entry in enumerate(raw_models):
        if isinstance(entry, dict) and _normalise_windows_path(entry.get("filename")) == target_key:
            match_index = index
            break
    existing = (
        deepcopy(raw_models[match_index])
        if match_index is not None and isinstance(raw_models[match_index], dict)
        else {}
    )
    existing.update({
        "filename": plan.item.instrument_path,
        "label": plan.canonical_name,
        "description": plan.asset.description or f"SMU project truth: {plan.item.instrument_path}",
        "center_frequency_mhz": plan.item.primary_center_frequency_hz / 1e6,
        "channel_asset_id": str(plan.asset.id),
    })
    if match_index is None:
        raw_models.append(existing)
    else:
        raw_models[match_index] = existing


def _lock_sync_truth_rows(db: Session, connection_id: UUID) -> InstrumentConnection:
    """Refresh and lock every database row that can change the synchronization decision.

    The bounded SMB scan necessarily performs filesystem I/O before the database write.  Do not
    publish from ORM objects loaded before that I/O: another request may have changed the selected
    connection, a vendor binding, or a canonical-name owner in the meantime.  The second preview
    below runs only after these rows are refreshed and locked.
    """
    bind = db.get_bind()
    if bind.dialect.name == "postgresql":
        # Row locks cannot stop a phantom vendor_file insert after classification.  This mode
        # blocks INSERT/UPDATE/DELETE on both truth tables while still allowing normal readers;
        # without it a new duplicate path could appear between the second preview and commit.
        db.execute(text(
            "LOCK TABLE instrument_connections, channel_assets "
            "IN SHARE ROW EXCLUSIVE MODE"
        ))
    db.expire_all()
    connection = (
        db.query(InstrumentConnection)
        .filter(InstrumentConnection.id == connection_id)
        .populate_existing()
        .with_for_update()
        .one_or_none()
    )
    if connection is None:
        raise SMUProjectSyncError("channelEmulator 连接在同步期间消失")

    # Lock the complete canonical-name namespace, not only the current vendor_file matches: any
    # ChannelAsset source can own the globally unique canonical_name used by a candidate.
    (
        db.query(ChannelAsset)
        .order_by(ChannelAsset.id)
        .populate_existing()
        .with_for_update()
        .all()
    )
    return connection


def sync_smu_project_truth(db: Session) -> SMUProjectSyncResult:
    """Re-scan and atomically synchronize every currently provable exact-path candidate."""
    initial_preview, _ = _preview_with_plans(db)
    try:
        _lock_sync_truth_rows(db, initial_preview.connection_id)
        # Re-scan and rebuild every plan from the refreshed, locked database truth.  This also
        # rejects a scan-root/configuration change that raced the first bounded scan instead of
        # combining old filesystem evidence with new connection metadata.
        preview, plans = _preview_with_plans(db)
    except Exception:
        db.rollback()
        raise

    already_count = sum(row.sync_status == "already_synced" for row in preview.items)
    if not plans:
        db.rollback()  # release SELECT FOR UPDATE locks on the read-only no-op path
        return SMUProjectSyncResult(
            updated_count=0,
            already_synced_count=already_count,
            preview=preview,
        )

    connection = db.get(InstrumentConnection, preview.connection_id)
    if connection is None:  # locked above; defensive fail-loud
        db.rollback()
        raise SMUProjectSyncError("channelEmulator 连接在同步期间消失")
    params = deepcopy(connection.connection_params or {})
    raw_models, _ = _projection_index(params)
    raw_models = deepcopy(raw_models)
    try:
        for plan in plans:
            plan.asset.payload = plan.payload
            plan.asset.center_frequency_hz = float(plan.item.primary_center_frequency_hz)
            plan.asset.instrument_connection_id = connection.id
            plan.asset.associated_file_path = plan.item.instrument_path
            plan.asset.canonical_name = plan.canonical_name
            _upsert_projection(raw_models, plan)
        params["available_channel_models"] = raw_models
        connection.connection_params = params
        db.commit()
    except Exception as exc:
        db.rollback()
        raise SMUProjectSyncError(f"SMU 工程真值同步已整体回滚: {exc}") from exc

    committed_ids = {plan.asset.id for plan in plans}
    committed_rows = tuple(
        SMUProjectSyncItem(
            **{
                **row.__dict__,
                "sync_status": "already_synced",
                "sync_detail": "资产与 channel-model 投影已提交为当前工程内容",
            }
        )
        if row.asset_id in committed_ids else row
        for row in preview.items
    )
    post = SMUProjectSyncPreview(
        connection_id=preview.connection_id,
        items=committed_rows,
        protected_paths=preview.protected_paths,
        total_files=preview.total_files,
        total_bytes=preview.total_bytes,
    )
    return SMUProjectSyncResult(
        updated_count=len(plans),
        already_synced_count=sum(row.sync_status == "already_synced" for row in post.items),
        preview=post,
    )
