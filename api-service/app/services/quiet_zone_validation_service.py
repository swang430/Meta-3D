"""
Quiet-Zone Validation Service (3GPP TR 38.151 § 7.2)

实现 3GPP MIMO OTA cert 必查的两个 QZ sub-test:
  1. **Field uniformity** (§ 7.2.x): SGH 在静区内多点扫描, 测各点功率,
     计算 std/range, 验证 ≤ ±1 dB (cert spec).
  2. **XPD / Cross-pol isolation** (§ 7.2.x): 同位置 V vs H 极化功率比,
     验证 ≥ 25 dB.

设计原则 (跟 CE+SA 路径一致, 不引入 VNA):
- **复用 path_loss 服务的 acquire_sa_power_via_ce_tone() helper** —
  它把 D/B capability dispatch + BSE 优先 + finally-stop + auto-routing 封好了,
  所以 QZ 服务自动继承所有这些行为.
- **复用 channel_calibration_service 的数学 helper** (calculate_uniformity_stats,
  validate_quiet_zone_uniformity), 它们已经存在且 production-ready.
- **PositionerDriver 驱动 SGH/QZ 扫描** — abstract 已有 move_to(az, el),
  Aerotech / ETS / Mock 都实现了. 真实 cert 暗室通常用 X-Y 平移台 (cm 单位),
  本服务把 (x_cm, y_cm) 当作小角度近似映射到 az/el — 方便 driver 抽象统一,
  cert 部署时按需替换或加专用 X-Y driver.
- **持久化到 QuietZoneCalibration model** — 已有 30+ 字段, 不动 schema.

CalibrationOrchestrator dispatch 接 CalibrationItem.QUIET_ZONE_UNIFORMITY.

参考: docs/design/MPAC-OTA-Chamber-Topology.md, 3GPP TR 38.151 § 7.2
"""
import logging
import statistics
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

import numpy as np
from sqlalchemy.orm import Session

from app.models.calibration import QuietZoneCalibration
from app.models.chamber import ChamberConfiguration
from app.schemas.probe_calibration import PolarizationType
from app.services.channel_calibration_service import (
    calculate_uniformity_stats,
    validate_quiet_zone_uniformity,
)
from app.services.path_loss_calibration_service import (
    CalibrationResult,
    ProbePathLossCalibrationService,
)

logger = logging.getLogger("app.calibration.quiet_zone")

# 3GPP TR 38.151 § 7.2 cert thresholds
QZ_AMPLITUDE_THRESHOLD_DB = 1.0  # ±1 dB field uniformity (cert spec)
QZ_PHASE_THRESHOLD_DEG = 30.0    # ±30° phase uniformity (used by amp-only check too)
XPD_THRESHOLD_DB = 25.0          # ≥25 dB cross-pol isolation (3GPP MIMO OTA)

# QZ validation 有效期 (跟 CALIBRATION_CONFIG 里 QUIET_ZONE_UNIFORMITY 一致)
QZ_VALIDITY_DAYS = 365

# 默认扫描偏移 (cm) — 5 点平面网格: center + ±5 cm in {x, y}
# 真实 cert 用 7-9 点 3D 球面/立方网格, 由 caller 传 scan_offsets_cm 覆盖
DEFAULT_SCAN_OFFSETS_CM: List[Tuple[float, float, float]] = [
    (0.0, 0.0, 0.0),
    (5.0, 0.0, 0.0),
    (-5.0, 0.0, 0.0),
    (0.0, 5.0, 0.0),
    (0.0, -5.0, 0.0),
]


class QuietZoneValidationService:
    """3GPP TR 38.151 § 7.2 QZ field uniformity + XPD validation."""

    def __init__(self, db: Session, use_mock: bool = True):
        self.db = db
        self.use_mock = use_mock

    # ======================================================================
    # Field uniformity (§ 7.2.x — main cert sub-test)
    # ======================================================================

    async def run_field_uniformity_validation(
        self,
        chamber_id: UUID,
        frequency_mhz: float,
        sgh_model: str,
        sgh_gain_dbi: float,
        polarization: PolarizationType = PolarizationType.V,
        scan_offsets_cm: Optional[List[Tuple[float, float, float]]] = None,
        ce_port: Optional[str] = None,
        route_target: Optional[str] = None,
        amplitude_threshold_db: float = QZ_AMPLITUDE_THRESHOLD_DB,
        ce_tx_power_dbm: float = -20.0,
        calibrated_by: str = "System",
    ) -> CalibrationResult:
        """N 点 QZ 扫描验证 field uniformity.

        默认 5 点平面网格 (DEFAULT_SCAN_OFFSETS_CM); cert lab 用 7-9 点 3D
        网格时由 caller 传 scan_offsets_cm 覆盖.

        Args:
            chamber_id: 暗室配置 ID
            frequency_mhz: 测试频点
            sgh_model / sgh_gain_dbi: 参考 SGH 元数据 (持久化用)
            polarization: 测试极化 (默认 V)
            scan_offsets_cm: 扫描点列表 [(x, y, z) cm offsets from QZ center];
                None → 默认 5 点平面网格
            ce_port / route_target: 选 CE 输出口 + 触发 rfSwitch 路由 (跟
                path_loss CE+SA 同语义, fixed-cabling 暗室留 None 即可)
            amplitude_threshold_db: ±dB pass 阈值, 默认 ±1 dB cert spec
            ce_tx_power_dbm: CE tone 输出功率, 默认 -20 dBm
            calibrated_by: 校准操作员

        Returns:
            CalibrationResult(success, message, data, warnings)
            data 含 calibration_id, field_uniformity_pass, std/range/mean,
            grid_points 数, threshold.
        """
        chamber = self.db.query(ChamberConfiguration).filter(
            ChamberConfiguration.id == chamber_id
        ).first()
        if chamber is None:
            return CalibrationResult(
                success=False,
                message=f"Chamber {chamber_id} not found",
            )

        offsets = scan_offsets_cm if scan_offsets_cm is not None else DEFAULT_SCAN_OFFSETS_CM
        warnings: List[str] = []

        try:
            if self.use_mock:
                grid_data = self._mock_grid_powers(offsets)
            else:
                grid_data = await self._real_grid_powers_via_ce_sa(
                    offsets,
                    frequency_mhz=frequency_mhz,
                    ce_tx_power_dbm=ce_tx_power_dbm,
                    ce_port=ce_port,
                    route_target=route_target,
                    polarization=polarization,
                    warnings=warnings,
                )
        except Exception as e:  # noqa: BLE001
            logger.error("[QZ uniformity] grid scan failed: %s", e)
            return CalibrationResult(
                success=False,
                message=f"Grid scan failed: {e}",
                warnings=warnings,
            )

        powers_dbm = np.array([p["measured_value"] for p in grid_data])
        mean_dbm, std_db, (min_dbm, max_dbm) = calculate_uniformity_stats(powers_dbm)

        # Phase 不在 amp-only 子测试里 — pass 0 让 helper 只看 amplitude
        amplitude_pass, _phase_pass, _overall_pass = validate_quiet_zone_uniformity(
            amplitude_std_db=std_db,
            phase_std_deg=0.0,
            amplitude_threshold_db=amplitude_threshold_db,
            phase_threshold_deg=QZ_PHASE_THRESHOLD_DEG,
        )

        # Cert 报告通常报 max-min range (peak-to-peak) 而非 std, 两者都存
        field_range_db = float(max_dbm - min_dbm)

        cal = QuietZoneCalibration(
            chamber_id=chamber_id,
            validation_type="field_uniformity",
            frequency_mhz=frequency_mhz,
            qz_diameter_cm=getattr(chamber, "quiet_zone_diameter_cm", None) or 30.0,
            grid_points=len(grid_data),
            grid_data=grid_data,
            sgh_model=sgh_model,
            sgh_gain_dbi=sgh_gain_dbi,
            measurement_method="ce_sa" if not self.use_mock else "mock",
            scan_pattern="grid",
            field_uniformity_db=field_range_db,
            field_uniformity_pass=bool(amplitude_pass),
            field_mean_dbm=float(mean_dbm),
            field_std_dev_db=float(std_db),
            field_max_dbm=float(max_dbm),
            field_min_dbm=float(min_dbm),
            validation_pass=bool(amplitude_pass),
            threshold_value=float(amplitude_threshold_db),
            tested_at=datetime.utcnow(),
            tested_by=calibrated_by,
        )
        self.db.add(cal)
        self.db.commit()
        self.db.refresh(cal)

        if not amplitude_pass:
            warnings.append(
                f"Field uniformity FAIL: std={std_db:.2f} dB, "
                f"range={field_range_db:.2f} dB exceeds threshold "
                f"±{amplitude_threshold_db} dB"
            )

        logger.info(
            "[QZ uniformity] chamber=%s freq=%.0f MHz pol=%s — "
            "std=%.2f range=%.2f dB %s",
            chamber_id, frequency_mhz, polarization.value, std_db, field_range_db,
            "PASS" if amplitude_pass else "FAIL",
        )

        return CalibrationResult(
            success=True,
            message=f"QZ field uniformity {'PASS' if amplitude_pass else 'FAIL'}",
            data={
                "calibration_id": str(cal.id),
                "validation_type": "field_uniformity",
                "field_uniformity_pass": bool(amplitude_pass),
                "field_std_db": float(std_db),
                "field_range_db": field_range_db,
                "field_mean_dbm": float(mean_dbm),
                "grid_points": len(grid_data),
                "threshold_db": float(amplitude_threshold_db),
            },
            warnings=warnings,
        )

    # ======================================================================
    # XPD / Cross-pol isolation (§ 7.2.x)
    # ======================================================================

    async def run_xpd_validation(
        self,
        chamber_id: UUID,
        frequency_mhz: float,
        sgh_model: str,
        sgh_gain_dbi: float,
        probe_id: int = 0,
        ce_port_co: Optional[str] = None,
        ce_port_cross: Optional[str] = None,
        route_target_co: Optional[str] = None,
        route_target_cross: Optional[str] = None,
        xpd_threshold_db: float = XPD_THRESHOLD_DB,
        ce_tx_power_dbm: float = -20.0,
        calibrated_by: str = "System",
    ) -> CalibrationResult:
        """3GPP MIMO OTA XPD: co-pol vs cross-pol 功率比.

        实测顺序:
          1. CE tone 经 V probe → SGH (V-pol port) → SA: P_co
          2. CE tone 经 H probe → SGH (V-pol port) → SA: P_cross
          XPD = P_co - P_cross (dB).

        在多探头暗室里, V/H probe 是同一物理位置的双极化对; SGH 不动.
        ce_port_co + ce_port_cross 指定两个 ce_port.

        Spec ≥ 25 dB (3GPP TR 38.151).
        """
        chamber = self.db.query(ChamberConfiguration).filter(
            ChamberConfiguration.id == chamber_id
        ).first()
        if chamber is None:
            return CalibrationResult(
                success=False,
                message=f"Chamber {chamber_id} not found",
            )

        warnings: List[str] = []

        try:
            if self.use_mock:
                # Mock: 30 dB XPD 典型值 + 噪声
                p_co_dbm = -85.0 + float(np.random.normal(0, 0.2))
                p_cross_dbm = -85.0 - 30.0 + float(np.random.normal(0, 0.2))
            else:
                pl_service = ProbePathLossCalibrationService(self.db, use_mock=False)
                p_co_dbm, _, _ = await pl_service.acquire_sa_power_via_ce_tone(
                    frequency_mhz=frequency_mhz,
                    ce_tx_power_dbm=ce_tx_power_dbm,
                    ce_port=ce_port_co,
                    route_target=route_target_co,
                    probe_id=probe_id,
                    polarization=PolarizationType.V,
                    warning_sink=warnings,
                    warning_label="XPD co-pol",
                )
                p_cross_dbm, _, _ = await pl_service.acquire_sa_power_via_ce_tone(
                    frequency_mhz=frequency_mhz,
                    ce_tx_power_dbm=ce_tx_power_dbm,
                    ce_port=ce_port_cross,
                    route_target=route_target_cross,
                    probe_id=probe_id,
                    polarization=PolarizationType.H,
                    warning_sink=warnings,
                    warning_label="XPD cross-pol",
                )
        except Exception as e:  # noqa: BLE001
            logger.error("[QZ XPD] measurement failed: %s", e)
            return CalibrationResult(
                success=False,
                message=f"XPD measurement failed: {e}",
                warnings=warnings,
            )

        xpd_db = float(p_co_dbm - p_cross_dbm)
        xpd_pass = xpd_db >= xpd_threshold_db

        cal = QuietZoneCalibration(
            chamber_id=chamber_id,
            validation_type="probe_coupling",  # XPD = cross-pol coupling, 复用此 type
            frequency_mhz=frequency_mhz,
            num_probes_measured=1,
            coupling_matrix=[
                {
                    "probe_id": probe_id,
                    "co_pol_dbm": float(p_co_dbm),
                    "cross_pol_dbm": float(p_cross_dbm),
                    "xpd_db": xpd_db,
                }
            ],
            max_coupling_db=xpd_db,
            coupling_pass=bool(xpd_pass),
            sgh_model=sgh_model,
            sgh_gain_dbi=sgh_gain_dbi,
            measurement_method="ce_sa" if not self.use_mock else "mock",
            validation_pass=bool(xpd_pass),
            threshold_value=float(xpd_threshold_db),
            tested_at=datetime.utcnow(),
            tested_by=calibrated_by,
        )
        self.db.add(cal)
        self.db.commit()
        self.db.refresh(cal)

        logger.info(
            "[QZ XPD] chamber=%s freq=%.0f MHz probe=%d — "
            "co=%.2f cross=%.2f → XPD=%.2f dB %s",
            chamber_id, frequency_mhz, probe_id, p_co_dbm, p_cross_dbm, xpd_db,
            "PASS" if xpd_pass else "FAIL",
        )

        return CalibrationResult(
            success=True,
            message=f"XPD {xpd_db:.1f} dB ({'PASS' if xpd_pass else 'FAIL'})",
            data={
                "calibration_id": str(cal.id),
                "validation_type": "probe_coupling",
                "xpd_db": xpd_db,
                "xpd_pass": bool(xpd_pass),
                "co_pol_dbm": float(p_co_dbm),
                "cross_pol_dbm": float(p_cross_dbm),
                "threshold_db": float(xpd_threshold_db),
            },
            warnings=warnings,
        )

    # ======================================================================
    # Internal: grid measurement
    # ======================================================================

    def _mock_grid_powers(
        self,
        offsets_cm: List[Tuple[float, float, float]],
    ) -> List[Dict[str, Any]]:
        """Mock: nominal -85 dBm with sub-1-dB ripple — well within ±1 dB spec
        so default mock results PASS."""
        nominal_dbm = -85.0
        grid: List[Dict[str, Any]] = []
        for x, y, z in offsets_cm:
            offset_mag_cm = float(np.sqrt(x * x + y * y + z * z))
            # Slight degradation away from center (typical real-chamber behavior)
            ripple = -0.05 * offset_mag_cm + float(np.random.normal(0, 0.15))
            grid.append({
                "x": float(x), "y": float(y), "z": float(z),
                "measured_value": nominal_dbm + ripple,
            })
        return grid

    async def _real_grid_powers_via_ce_sa(
        self,
        offsets_cm: List[Tuple[float, float, float]],
        frequency_mhz: float,
        ce_tx_power_dbm: float,
        ce_port: Optional[str],
        route_target: Optional[str],
        polarization: PolarizationType,
        warnings: List[str],
    ) -> List[Dict[str, Any]]:
        """每点 positioner.move_to → CE+SA tone → SA mean dBm 入 grid。

        positioner abstract 是 (azimuth, elevation) 度数; cert lab 的
        QZ 扫描台是 (x, y) cm. 本实现用小角度近似把 cm 当度数传, 给
        Mock / Aerotech / ETS 等通用 driver 用. 真实 X-Y 平移台部署时
        应另写专用 driver (或扩展 PositionerDriver 接口加 move_to_xy_cm).
        """
        from app.services.instrument_hal_service import get_hal_service

        hal = get_hal_service()
        positioner = hal.drivers.get("positioner")
        if positioner is None:
            raise RuntimeError(
                "QZ scan needs positioner driver (SGH/QZ scan stage). "
                "Bind a PositionerDriver on the active LabProfile."
            )

        pl_service = ProbePathLossCalibrationService(self.db, use_mock=False)
        grid: List[Dict[str, Any]] = []
        for x_cm, y_cm, z_cm in offsets_cm:
            ok = await positioner.move_to(azimuth=float(x_cm), elevation=float(y_cm))
            if not ok:
                raise RuntimeError(
                    f"positioner.move_to({x_cm}, {y_cm}) failed; aborting scan"
                )
            sa_mean_dbm, _, _ = await pl_service.acquire_sa_power_via_ce_tone(
                frequency_mhz=frequency_mhz,
                ce_tx_power_dbm=ce_tx_power_dbm,
                ce_port=ce_port,
                route_target=route_target,
                probe_id=0,
                polarization=polarization,
                warning_sink=warnings,
                warning_label=f"grid point ({x_cm}, {y_cm}, {z_cm})",
            )
            grid.append({
                "x": float(x_cm), "y": float(y_cm), "z": float(z_cm),
                "measured_value": float(sa_mean_dbm),
            })

        return grid

    # ======================================================================
    # Lookup helpers
    # ======================================================================

    def get_latest_validation(
        self,
        chamber_id: UUID,
        validation_type: str = "field_uniformity",
    ) -> Optional[QuietZoneCalibration]:
        """获取最新的 QZ 验证记录 (按 validation_type 过滤)."""
        from sqlalchemy import desc

        return (
            self.db.query(QuietZoneCalibration)
            .filter(
                QuietZoneCalibration.chamber_id == chamber_id,
                QuietZoneCalibration.validation_type == validation_type,
            )
            .order_by(desc(QuietZoneCalibration.tested_at))
            .first()
        )
