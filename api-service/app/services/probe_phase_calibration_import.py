"""Probe phase calibration — offline CSV import service (P1-5 local half).

操作员用外部 VNA 测好每个 probe 相对参考 probe 的 phase offset + group delay +
phase uncertainty (per frequency), 导出 CSV, 通过 POST /probe-calibrations/
phase/import-csv 上传, 本服务负责:
  1. 解析 CSV (4 列: frequency_mhz, phase_offset_deg, group_delay_ns,
     phase_uncertainty_deg)
  2. 验证数据完整性 + 物理合理性
  3. 写一行 ProbePhaseCalibration (status=VALID, valid_until=now+90d)
  4. 可选: 把同 (probe_id, polarization) 的旧记录置 INVALIDATED

CSV 不带 metadata: probe_id / polarization / reference / VNA model 全部由
multipart Form 字段给出, CSV 只是 frequency-indexed 数据矩阵。这跟
`probe_pattern.import_service` 一致, 让操作员手工编辑 CSV 时少出错。

P1-5 完整工作分两半:
- ✅ Local half (this module): offline CSV-import 路径, 数据已用外部仪器测好
- 🔄 On-site half (later): replace `start_phase_calibration` mock body with real
  SCPI sequence (CE → probe → SA), 需要现场硬件
"""
from __future__ import annotations

import csv
import io
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import List, Optional

from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.models.probe_calibration import (
    CalibrationStatus,
    ProbePhaseCalibration,
)
from app.services.probe_calibration_service import PROBE_ID_MAX

logger = logging.getLogger("app.calibration.phase_csv_import")

# Phase cal cert default validity — 跟 start_phase_calibration mock 端点保持一致
PHASE_CAL_VALIDITY_DAYS = 90

# Physical bounds for sanity-checking — 跟 IEEE/3GPP convention 对齐
PHASE_OFFSET_DEG_BOUNDS = (-180.0, 180.0)  # unwrapped phase 也可能 ±180+; 这里
# 是 wrap-after-import 默认值; 操作员要传 unwrapped 时显式 disable bound check
GROUP_DELAY_NS_MIN = 0.0
PHASE_UNCERTAINTY_DEG_MIN = 0.0

CSV_REQUIRED_COLUMNS = (
    "frequency_mhz",
    "phase_offset_deg",
    "group_delay_ns",
    "phase_uncertainty_deg",
)


@dataclass
class ImportResult:
    """Service-layer result, callers map to HTTP response model."""

    success: bool = False
    calibration_id: Optional[str] = None
    invalidated_id: Optional[str] = None
    num_frequency_points: int = 0
    warnings: List[str] = field(default_factory=list)
    error: Optional[str] = None


def import_phase_calibration_from_csv(
    db: Session,
    *,
    file_content: bytes | str,
    probe_id: int,
    polarization: str,
    reference_probe_id: int = 0,
    vna_model: Optional[str] = None,
    vna_serial: Optional[str] = None,
    calibrated_by: str = "csv_import",
    raw_data_file_path: Optional[str] = None,
    replace_existing: bool = True,
    allow_unwrapped_phase: bool = False,
) -> ImportResult:
    """Parse uploaded phase-calibration CSV and persist as ProbePhaseCalibration.

    Args:
        file_content: raw CSV bytes or string
        probe_id: which physical probe these data describe (0..PROBE_ID_MAX)
        polarization: "V" | "H" | "LHCP" | "RHCP"
        reference_probe_id: probe used as phase reference (typically 0); MUST
            differ from `probe_id` — measuring "probe X vs X" is meaningless
        vna_model / vna_serial: instrument metadata for traceability
        calibrated_by: operator/script identifier
        raw_data_file_path: optional pointer to where the raw .s2p (or
            equivalent) lives on a shared file server
        replace_existing: True → invalidate prior VALID cert for the same
            (probe_id, polarization) tuple; False → keep both (only useful
            for cross-cert comparison; risky in production)
        allow_unwrapped_phase: True → skip ±180° bound check (operator
            knows they're providing unwrapped data); default False

    Returns:
        ImportResult with calibration_id on success.
    """
    # ---- 1. Decode bytes → string ----
    if isinstance(file_content, (bytes, bytearray)):
        try:
            text = file_content.decode("utf-8-sig")
        except UnicodeDecodeError as e:
            return ImportResult(
                success=False,
                error=f"CSV file is not valid UTF-8: {e}",
            )
    else:
        text = file_content

    if not text.strip():
        return ImportResult(success=False, error="CSV is empty")

    # ---- 2. Parse CSV ----
    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None:
        return ImportResult(success=False, error="CSV has no header row")

    missing = [c for c in CSV_REQUIRED_COLUMNS if c not in reader.fieldnames]
    if missing:
        return ImportResult(
            success=False,
            error=(
                f"CSV missing required column(s): {missing}. "
                f"Required header: {','.join(CSV_REQUIRED_COLUMNS)}"
            ),
        )

    freqs_mhz: List[float] = []
    phase_offsets_deg: List[float] = []
    group_delays_ns: List[float] = []
    phase_uncertainties_deg: List[float] = []

    warnings: List[str] = []

    for row_idx, row in enumerate(reader, start=2):  # row 1 is header
        try:
            f = float(row["frequency_mhz"])
            p = float(row["phase_offset_deg"])
            g = float(row["group_delay_ns"])
            u = float(row["phase_uncertainty_deg"])
        except (KeyError, ValueError, TypeError) as e:
            return ImportResult(
                success=False,
                error=(
                    f"CSV row {row_idx} has non-numeric or missing value: "
                    f"row={row!r}, err={e}"
                ),
            )

        # Physical bounds
        if f <= 0:
            return ImportResult(
                success=False,
                error=f"Row {row_idx}: frequency_mhz must be positive, got {f}",
            )
        if not allow_unwrapped_phase:
            lo, hi = PHASE_OFFSET_DEG_BOUNDS
            if not (lo <= p <= hi):
                return ImportResult(
                    success=False,
                    error=(
                        f"Row {row_idx}: phase_offset_deg={p} outside "
                        f"[{lo}, {hi}]. Set allow_unwrapped_phase=true if you "
                        f"intend to upload unwrapped data."
                    ),
                )
        if g < GROUP_DELAY_NS_MIN:
            return ImportResult(
                success=False,
                error=(
                    f"Row {row_idx}: group_delay_ns={g} must be ≥ "
                    f"{GROUP_DELAY_NS_MIN} (negative delays are unphysical)"
                ),
            )
        if u < PHASE_UNCERTAINTY_DEG_MIN:
            return ImportResult(
                success=False,
                error=(
                    f"Row {row_idx}: phase_uncertainty_deg={u} must be ≥ "
                    f"{PHASE_UNCERTAINTY_DEG_MIN}"
                ),
            )

        freqs_mhz.append(f)
        phase_offsets_deg.append(p)
        group_delays_ns.append(g)
        phase_uncertainties_deg.append(u)

    if not freqs_mhz:
        return ImportResult(
            success=False, error="CSV header present but no data rows"
        )

    # Monotonicity is helpful but not strictly required (operator may
    # interleave; downstream interpolation works on sorted view). Warn only.
    if any(b <= a for a, b in zip(freqs_mhz, freqs_mhz[1:])):
        warnings.append(
            "frequency_mhz column is not strictly monotonic-ascending; "
            "downstream consumers may sort or de-dup."
        )

    # ---- 3. Sanity-check probe identifiers ----
    if not (0 <= probe_id <= PROBE_ID_MAX):
        return ImportResult(
            success=False,
            error=(
                f"probe_id={probe_id} out of bounds [0, {PROBE_ID_MAX}]"
            ),
        )
    if not (0 <= reference_probe_id <= PROBE_ID_MAX):
        return ImportResult(
            success=False,
            error=(
                f"reference_probe_id={reference_probe_id} out of bounds "
                f"[0, {PROBE_ID_MAX}]"
            ),
        )
    if reference_probe_id == probe_id:
        return ImportResult(
            success=False,
            error=(
                f"reference_probe_id must differ from probe_id "
                f"(both = {probe_id}); a probe can't be its own phase reference"
            ),
        )
    if polarization not in ("V", "H", "LHCP", "RHCP"):
        return ImportResult(
            success=False,
            error=(
                f"polarization={polarization!r} not in "
                f"{{'V', 'H', 'LHCP', 'RHCP'}}"
            ),
        )

    # ---- 4. Invalidate prior cert (if replace_existing) ----
    invalidated_id: Optional[str] = None
    if replace_existing:
        prior = (
            db.query(ProbePhaseCalibration)
            .filter(
                ProbePhaseCalibration.probe_id == probe_id,
                ProbePhaseCalibration.polarization == polarization,
                ProbePhaseCalibration.status == CalibrationStatus.VALID.value,
            )
            .order_by(desc(ProbePhaseCalibration.calibrated_at))
            .first()
        )
        if prior is not None:
            prior.status = CalibrationStatus.INVALIDATED.value
            invalidated_id = str(prior.id)
            logger.info(
                "Invalidated prior phase cal probe=%d pol=%s id=%s",
                probe_id, polarization, prior.id,
            )

    # ---- 5. Persist new cert ----
    now = datetime.utcnow()
    cal = ProbePhaseCalibration(
        probe_id=probe_id,
        polarization=polarization,
        reference_probe_id=reference_probe_id,
        frequency_points_mhz=freqs_mhz,
        phase_offset_deg=phase_offsets_deg,
        group_delay_ns=group_delays_ns,
        phase_uncertainty_deg=phase_uncertainties_deg,
        vna_model=vna_model,
        vna_serial=vna_serial,
        calibrated_at=now,
        calibrated_by=calibrated_by,
        valid_until=now + timedelta(days=PHASE_CAL_VALIDITY_DAYS),
        status=CalibrationStatus.VALID.value,
        raw_data_file_path=raw_data_file_path,
    )
    db.add(cal)
    db.commit()
    db.refresh(cal)

    logger.info(
        "Imported phase cal probe=%d pol=%s n_freq=%d id=%s",
        probe_id, polarization, len(freqs_mhz), cal.id,
    )

    return ImportResult(
        success=True,
        calibration_id=str(cal.id),
        invalidated_id=invalidated_id,
        num_frequency_points=len(freqs_mhz),
        warnings=warnings,
    )
