"""
Quiet-Zone Validation Service (3GPP TR 38.151 § 7.2)

实现 3GPP MIMO OTA cert 的 QZ sub-test:
  **Field uniformity** (§ 7.2.x): SGH 在静区内多点扫描, 测各点功率,
  计算 std/range, 验证 ≤ ±1 dB (cert spec).

设计原则 (跟 CE+SA 路径一致, 不引入 VNA):
- **复用 path_loss 服务的 acquire_sa_power_via_ce_tone() helper** —
  它把 D/B capability dispatch + BSE 优先 + finally-stop + auto-routing 封好了,
  所以 QZ 服务自动继承所有这些行为.
- **复用 channel_calibration_service 的数学 helper** (calculate_uniformity_stats,
  validate_quiet_zone_uniformity), 它们已经存在且 production-ready.
- **真实 QZ 网格要求经过验证的 X-Y 平移台（cm）**。现有 positioner 是旋转台
  （degree）且 ETS 动作协议没有仓内出处，因此真实路径在任何位置 I/O 前拒绝；
  mock 路径只用于算法演练，不形成正式校准结论。
- **持久化到 ChannelQuietZoneCalibration**（P1-71 QZ 并轨，设计稿 §2 R6）：
  probe 侧 quiet_zone_calibrations 已封存，静区唯一活载体 = channel 侧表；
  chamber / SGH / 绝对功率等 provenance 收进 measurement_grid JSON。

CalibrationOrchestrator dispatch 接 CalibrationItem.QUIET_ZONE_UNIFORMITY.

P1-71 注：原 run_xpd_validation（XPD 验证器）与 get_latest_validation 随并轨
移除 —— 两者零调用方、persist / 查询目标是已封存的 probe 侧表，且 channel
侧无 XPD 语义槽；需要时从 git 历史（P1-71 片之前）复活并先裁决落库载体。

参考: docs/design/MPAC-OTA-Chamber-Topology.md, 3GPP TR 38.151 § 7.2
"""
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

import numpy as np
from sqlalchemy.orm import Session

from app.models.channel_calibration import ChannelQuietZoneCalibration
from app.models.chamber import ChamberConfiguration
from app.schemas.probe_calibration import PolarizationType
from app.services.channel_calibration_service import (
    calculate_uniformity_stats,
    validate_quiet_zone_uniformity,
)
from app.services.path_loss_calibration_service import CalibrationResult

logger = logging.getLogger("app.calibration.quiet_zone")

# 3GPP TR 38.151 § 7.2 cert thresholds
QZ_AMPLITUDE_THRESHOLD_DB = 1.0  # ±1 dB field uniformity (cert spec)
QZ_PHASE_THRESHOLD_DEG = 30.0    # ±30° phase uniformity (used by amp-only check too)

# 有效期/status：本服务不设 valid_until（原 365 天死常量随并轨删除，零消费方）。
# 激活批统一到 channel 侧本家口径（channel_calibration_service 180 天）时一并定。

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
    """3GPP TR 38.151 § 7.2 QZ field uniformity validation（落库 channel 侧）."""

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
        if self.use_mock:
            return CalibrationResult(
                success=False,
                message=(
                    "静区校准未判定：缺少可验证的真实多点场扫描平台；"
                    "mock 网格不形成正式证据。"
                ),
            )

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

        # P1-71 QZ 并轨：落 channel 侧表。probe 侧独有的 chamber/SGH/绝对功率
        # 字段没有对应列，如实收进 measurement_grid.provenance；amplitude_* 列
        # 按其 dB（相对量）语义只存偏差统计，绝对功率留在 provenance。
        qz_diameter_m = getattr(chamber, "quiet_zone_diameter_m", None) or 0.3
        cal = ChannelQuietZoneCalibration(
            session_id=None,
            # chamber 只登记直径无形状 —— 径-only 规格按球解读（与 channel 侧
            # run_quiet_zone_calibration 的默认一致），出处见 provenance。
            quiet_zone_shape="sphere",
            quiet_zone_diameter_m=float(qz_diameter_m),
            field_probe_type="sgh",
            measurement_grid={
                "points": [
                    {
                        "x_cm": p["x"], "y_cm": p["y"], "z_cm": p["z"],
                        "power_dbm": p["measured_value"],
                    }
                    for p in grid_data
                ],
                "provenance": {
                    "chamber_id": str(chamber_id),
                    "frequency_mhz": float(frequency_mhz),
                    "sgh_model": sgh_model,
                    "sgh_gain_dbi": float(sgh_gain_dbi),
                    "polarization": polarization.value,
                    "measurement_method": "ce_sa",
                    "scan_pattern": "grid",
                    "field_mean_dbm": float(mean_dbm),
                    "field_max_dbm": float(max_dbm),
                    "field_min_dbm": float(min_dbm),
                    "quiet_zone_shape_source": "assumed sphere (chamber 仅登记直径)",
                    "units_note": (
                        "amplitude_range_db 为相对均值偏差（dB，外审 #394 R1 对齐"
                        "列名语义）；amplitude_mean_db 不填——相对均值恒 0 无信息，"
                        "绝对功率（dBm）见本 provenance 的 field_*_dbm"
                    ),
                },
            },
            num_points=len(grid_data),
            amplitude_mean_db=None,
            amplitude_std_db=float(std_db),
            amplitude_range_db=[
                float(min_dbm - mean_dbm), float(max_dbm - mean_dbm)
            ],
            amplitude_uniformity_pass=bool(amplitude_pass),
            validation_pass=bool(amplitude_pass),
            amplitude_threshold_db=float(amplitude_threshold_db),
            fc_ghz=float(frequency_mhz) / 1000.0,
            calibrated_at=datetime.utcnow(),
            calibrated_by=calibrated_by,
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
        """Fail closed until a linear-stage API with centimetre units exists."""
        raise RuntimeError(
            "Real QZ grid acquisition requires a verified linear XY stage API "
            "in centimetres; rotational PositionerDriver.move_to(degrees) "
            "must not be used for x_cm/y_cm"
        )
