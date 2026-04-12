"""
Measurement Compensation Service

测量补偿服务 - 为 TRP/TIS 测量提供路损和链路增益补偿。

CAL-05: TRP 测量补偿
CAL-06: TIS 测量补偿

补偿公式:
- TRP: P_dut_tx = P_measured_at_CE + PathLoss - UL_Gain
- TIS: P_at_DUT = P_delivered_from_CE - DL_Gain + PathLoss

其中:
- PathLoss: SGH 到探头的空间路径损耗 (正值)
- UL_Gain: 上行链路总增益 (含 LNA，正值)
- DL_Gain: 下行链路总增益 (含 PA，正值)

参考: docs/design/MPAC-OTA-Chamber-Topology.md
"""
from typing import Dict, Optional, List, Tuple
from uuid import UUID
from sqlalchemy.orm import Session
import numpy as np
import logging

from app.models.chamber import ChamberConfiguration
from app.services.calibration_orchestrator import CalibrationOrchestrator

logger = logging.getLogger(__name__)


class MeasurementCompensator:
    """
    测量补偿器

    为 OTA 测量提供系统级补偿，确保测量结果准确反映 DUT 性能。
    """

    def __init__(self, db: Session, use_mock: bool = True):
        self.db = db
        self.orchestrator = CalibrationOrchestrator(db, use_mock)

    def get_trp_compensation(
        self,
        chamber_id: UUID,
        probe_id: int,
        polarization: str,
        frequency_mhz: float
    ) -> Dict[str, float]:
        """
        获取 TRP 测量补偿值

        TRP 测量场景:
        - DUT 发射 → 探头接收 → LNA 放大 → 信道仿真器接收
        - 测量点在信道仿真器输入端
        - 需要补偿路损和 LNA 增益来还原 DUT 发射功率

        补偿公式: P_dut_tx = P_measured + PathLoss - UL_Gain

        Args:
            chamber_id: 暗室配置 ID
            probe_id: 探头 ID
            polarization: 极化类型 ("V" 或 "H")
            frequency_mhz: 测量频率

        Returns:
            补偿值字典 {
                path_loss_db: 路损值,
                ul_gain_db: 上行链路增益,
                total_compensation_db: 总补偿值 (路损 - 上行增益),
                valid: 是否有有效校准数据
            }
        """
        factors = self.orchestrator.get_compensation_factors(
            chamber_id, probe_id, polarization, frequency_mhz
        )

        if "error" in factors:
            logger.warning(f"Compensation error: {factors['error']}")
            return {
                "path_loss_db": 0.0,
                "ul_gain_db": 0.0,
                "total_compensation_db": 0.0,
                "valid": False,
                "warning": factors.get("error", "Unknown error")
            }

        # TRP 补偿: P_dut = P_measured + PathLoss - UL_Gain
        path_loss = factors.get("path_loss_db", 0.0)
        ul_gain = factors.get("ul_gain_db", 0.0)
        total = path_loss - ul_gain

        return {
            "path_loss_db": path_loss,
            "ul_gain_db": ul_gain,
            "total_compensation_db": total,
            "valid": path_loss > 0  # 至少需要路损数据
        }

    def get_tis_compensation(
        self,
        chamber_id: UUID,
        probe_id: int,
        polarization: str,
        frequency_mhz: float
    ) -> Dict[str, float]:
        """
        获取 TIS 测量补偿值

        TIS 测量场景:
        - 信道仿真器发射 → PA 放大 → 探头发射 → DUT 接收
        - 控制点在信道仿真器输出端
        - 需要补偿 PA 增益和路损来计算 DUT 接收功率

        补偿公式: P_at_DUT = P_delivered - PathLoss + DL_Gain

        Args:
            chamber_id: 暗室配置 ID
            probe_id: 探头 ID
            polarization: 极化类型
            frequency_mhz: 测量频率

        Returns:
            补偿值字典
        """
        factors = self.orchestrator.get_compensation_factors(
            chamber_id, probe_id, polarization, frequency_mhz
        )

        if "error" in factors:
            logger.warning(f"Compensation error: {factors['error']}")
            return {
                "path_loss_db": 0.0,
                "dl_gain_db": 0.0,
                "total_compensation_db": 0.0,
                "valid": False,
                "warning": factors.get("error", "Unknown error")
            }

        # TIS 补偿: P_at_DUT = P_delivered - PathLoss + DL_Gain
        path_loss = factors.get("path_loss_db", 0.0)
        dl_gain = factors.get("dl_gain_db", 0.0)
        total = dl_gain - path_loss

        return {
            "path_loss_db": path_loss,
            "dl_gain_db": dl_gain,
            "total_compensation_db": total,
            "valid": path_loss > 0
        }

    def compensate_trp_measurement(
        self,
        raw_power_dbm: float,
        chamber_id: UUID,
        probe_id: int,
        polarization: str,
        frequency_mhz: float
    ) -> Tuple[float, Dict[str, float]]:
        """
        对 TRP 测量值进行补偿

        Args:
            raw_power_dbm: 原始测量功率 (dBm)
            chamber_id: 暗室配置 ID
            probe_id: 探头 ID
            polarization: 极化类型
            frequency_mhz: 测量频率

        Returns:
            (补偿后功率, 补偿详情)
        """
        compensation = self.get_trp_compensation(
            chamber_id, probe_id, polarization, frequency_mhz
        )

        compensated = raw_power_dbm + compensation["total_compensation_db"]

        return compensated, compensation

    def compensate_tis_measurement(
        self,
        delivered_power_dbm: float,
        chamber_id: UUID,
        probe_id: int,
        polarization: str,
        frequency_mhz: float
    ) -> Tuple[float, Dict[str, float]]:
        """
        对 TIS 测量值进行补偿

        Args:
            delivered_power_dbm: 信道仿真器输出功率 (dBm)
            chamber_id: 暗室配置 ID
            probe_id: 探头 ID
            polarization: 极化类型
            frequency_mhz: 测量频率

        Returns:
            (DUT 接收功率, 补偿详情)
        """
        compensation = self.get_tis_compensation(
            chamber_id, probe_id, polarization, frequency_mhz
        )

        # P_at_DUT = P_delivered + total_compensation
        # 其中 total = dl_gain - path_loss
        power_at_dut = delivered_power_dbm + compensation["total_compensation_db"]

        return power_at_dut, compensation

    def get_bulk_trp_compensation(
        self,
        chamber_id: UUID,
        probe_ids: List[int],
        polarization: str,
        frequency_mhz: float
    ) -> Dict[int, Dict[str, float]]:
        """
        批量获取多个探头的 TRP 补偿值

        用于球面积分时一次性获取所有探头的补偿数据。

        Args:
            chamber_id: 暗室配置 ID
            probe_ids: 探头 ID 列表
            polarization: 极化类型
            frequency_mhz: 测量频率

        Returns:
            {probe_id: compensation_dict}
        """
        compensations = {}

        for probe_id in probe_ids:
            compensations[probe_id] = self.get_trp_compensation(
                chamber_id, probe_id, polarization, frequency_mhz
            )

        return compensations

    def compute_compensated_trp(
        self,
        raw_powers_dbm: Dict[int, float],
        chamber_id: UUID,
        polarization: str,
        frequency_mhz: float,
        theta_step_deg: float = 15.0,
        phi_step_deg: float = 15.0
    ) -> Tuple[float, Dict[str, any]]:
        """
        计算补偿后的 TRP

        对每个探头的测量值分别进行补偿，然后球面积分。

        Args:
            raw_powers_dbm: {probe_id: raw_power_dbm}
            chamber_id: 暗室配置 ID
            polarization: 极化类型
            frequency_mhz: 测量频率
            theta_step_deg: theta 步进角度
            phi_step_deg: phi 步进角度

        Returns:
            (compensated_trp_dbm, details)
        """
        probe_ids = list(raw_powers_dbm.keys())
        compensations = self.get_bulk_trp_compensation(
            chamber_id, probe_ids, polarization, frequency_mhz
        )

        # 补偿每个探头
        compensated_powers = {}
        for probe_id, raw_power in raw_powers_dbm.items():
            comp = compensations.get(probe_id, {})
            total_comp = comp.get("total_compensation_db", 0.0)
            compensated_powers[probe_id] = raw_power + total_comp

        # 转换为线性功率用于积分
        powers_linear = [10 ** (p / 10) for p in compensated_powers.values()]

        # 球面积分
        trp_dbm = self._spherical_integration(
            powers_linear, theta_step_deg, phi_step_deg
        )

        # 计算平均补偿量
        avg_compensation = np.mean([
            c.get("total_compensation_db", 0)
            for c in compensations.values()
        ])

        return trp_dbm, {
            "num_probes": len(probe_ids),
            "avg_compensation_db": avg_compensation,
            "compensations": compensations
        }

    def _spherical_integration(
        self,
        powers_linear: List[float],
        theta_step_deg: float,
        phi_step_deg: float
    ) -> float:
        """
        球面积分计算 TRP

        TRP = ∫∫ ERP(θ, φ) · sin(θ) dθ dφ / (4π)
        """
        theta_step_rad = np.radians(theta_step_deg)
        phi_step_rad = np.radians(phi_step_deg)

        num_theta = int(180 / theta_step_deg) + 1
        num_phi = int(360 / phi_step_deg)

        # 确保数据量匹配
        expected_points = num_theta * num_phi
        if len(powers_linear) != expected_points:
            # 如果数据点不匹配，使用平均值填充
            if len(powers_linear) < expected_points:
                avg_power = np.mean(powers_linear)
                powers_linear = powers_linear + [avg_power] * (expected_points - len(powers_linear))
            else:
                powers_linear = powers_linear[:expected_points]

        powers_grid = np.array(powers_linear).reshape(num_theta, num_phi)

        thetas = np.arange(0, 181, theta_step_deg)
        thetas_rad = np.radians(thetas)
        sin_theta = np.sin(thetas_rad)

        total_power = 0.0
        for i in range(num_theta):
            for j in range(num_phi):
                total_power += powers_grid[i, j] * sin_theta[i] * theta_step_rad * phi_step_rad

        trp_linear = total_power / (4 * np.pi)
        trp_dbm = 10 * np.log10(trp_linear) if trp_linear > 0 else -np.inf

        return trp_dbm


def get_system_compensation_summary(
    db: Session,
    chamber_id: UUID,
    frequency_mhz: float
) -> Dict[str, any]:
    """
    获取系统补偿汇总

    用于测试前检查系统校准状态和补偿值。

    Args:
        db: 数据库会话
        chamber_id: 暗室配置 ID
        frequency_mhz: 测量频率

    Returns:
        补偿汇总信息
    """
    chamber = db.query(ChamberConfiguration).filter(
        ChamberConfiguration.id == chamber_id
    ).first()

    if not chamber:
        return {"error": "Chamber not found"}

    orchestrator = CalibrationOrchestrator(db, use_mock=True)

    # 获取典型探头的补偿值 (探头 0, V 极化)
    factors = orchestrator.get_compensation_factors(
        chamber_id, 0, "V", frequency_mhz
    )

    # 检查校准状态
    statuses = orchestrator.check_calibration_status(chamber_id, frequency_mhz)

    # 统计有效校准数
    valid_count = sum(1 for s in statuses.values() if s.is_valid)
    required_count = sum(1 for s in statuses.values() if s.is_required)

    return {
        "chamber_id": str(chamber_id),
        "chamber_name": chamber.name,
        "chamber_type": chamber.chamber_type,
        "frequency_mhz": frequency_mhz,
        "has_lna": chamber.has_lna,
        "has_pa": chamber.has_pa,
        "has_duplexer": chamber.has_duplexer,
        "typical_compensation": {
            "path_loss_db": factors.get("path_loss_db", 0),
            "ul_gain_db": factors.get("ul_gain_db", 0),
            "dl_gain_db": factors.get("dl_gain_db", 0),
            "trp_compensation_db": factors.get("trp_compensation_db", 0),
            "tis_compensation_db": factors.get("tis_compensation_db", 0),
        },
        "calibration_status": {
            "valid_calibrations": valid_count,
            "required_calibrations": required_count,
            "all_valid": valid_count >= required_count
        }
    }
