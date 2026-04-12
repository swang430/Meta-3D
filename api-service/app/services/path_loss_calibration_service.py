"""
Path Loss and RF Chain Calibration Services

探头路损校准和 RF 链路增益校准业务逻辑。

CAL-02: 探头路损校准 (SGH → 探头空间路损)
CAL-03: 上行链路校准 (含 LNA)
CAL-04: 下行链路校准 (含 PA)

参考: docs/design/MPAC-OTA-Chamber-Topology.md
"""
import numpy as np
from typing import List, Dict, Optional, Any, Tuple
from datetime import datetime, timedelta
from uuid import UUID, uuid4
from sqlalchemy.orm import Session
from sqlalchemy import desc
import logging
import statistics

from app.models.probe_calibration import (
    ProbePathLossCalibration,
    RFChainCalibration,
    MultiFrequencyPathLoss,
    CalibrationStatus,
)
from app.models.chamber import ChamberConfiguration
from app.schemas.probe_calibration import (
    PolarizationType,
    CalibrationJobStatus,
    ChainTypeEnum,
)

logger = logging.getLogger(__name__)


# ==================== 校准常数 ====================

# 路损校准有效期 (天)
PATH_LOSS_VALIDITY_DAYS = 180  # 6 个月

# RF 链路校准有效期 (天)
RF_CHAIN_VALIDITY_DAYS = 90  # 3 个月

# 多频点校准有效期 (天)
MULTI_FREQ_VALIDITY_DAYS = 180

# 路损不确定度阈值 (dB)
PATH_LOSS_UNCERTAINTY_THRESHOLD_DB = 1.0

# 增益测量不确定度阈值 (dB)
GAIN_UNCERTAINTY_THRESHOLD_DB = 0.5

# 探头数量
NUM_PROBES = 32
NUM_POLARIZATIONS = 2


# ==================== 数据类 ====================

class PathLossMeasurement:
    """单个路损测量结果"""
    def __init__(
        self,
        probe_id: int,
        polarization: str,
        path_loss_db: float,
        uncertainty_db: float = 0.5
    ):
        self.probe_id = probe_id
        self.polarization = polarization
        self.path_loss_db = path_loss_db
        self.uncertainty_db = uncertainty_db


class ChainGainMeasurement:
    """RF 链路增益测量结果"""
    def __init__(
        self,
        total_gain_db: float,
        lna_gain_db: Optional[float] = None,
        pa_gain_db: Optional[float] = None,
        duplexer_loss_db: Optional[float] = None,
        cable_loss_db: Optional[float] = None
    ):
        self.total_gain_db = total_gain_db
        self.lna_gain_db = lna_gain_db
        self.pa_gain_db = pa_gain_db
        self.duplexer_loss_db = duplexer_loss_db
        self.cable_loss_db = cable_loss_db


class CalibrationResult:
    """校准结果"""
    def __init__(
        self,
        success: bool,
        message: str,
        data: Optional[Dict[str, Any]] = None,
        warnings: Optional[List[str]] = None
    ):
        self.success = success
        self.message = message
        self.data = data or {}
        self.warnings = warnings or []


# ==================== 路损计算函数 ====================

def calculate_fspl(frequency_mhz: float, distance_m: float) -> float:
    """
    计算自由空间路径损耗

    FSPL = 20*log10(d) + 20*log10(f) - 27.55  (d in m, f in MHz)

    Args:
        frequency_mhz: 频率 (MHz)
        distance_m: 距离 (m)

    Returns:
        路径损耗 (dB)，正值
    """
    if distance_m <= 0 or frequency_mhz <= 0:
        raise ValueError("Distance and frequency must be positive")

    fspl_db = 20 * np.log10(distance_m) + 20 * np.log10(frequency_mhz) - 27.55
    return fspl_db


def calculate_measured_path_loss(
    received_power_dbm: float,
    transmitted_power_dbm: float,
    sgh_gain_dbi: float,
    probe_gain_dbi: float,
    cable_loss_db: float = 0.0
) -> float:
    """
    根据 S21 测量计算实际路损

    PathLoss = P_tx - P_rx + G_sgh + G_probe - CableLoss

    Args:
        received_power_dbm: 接收功率 (dBm) 或 S21 (dB)
        transmitted_power_dbm: 发射功率 (dBm)，通常为 0
        sgh_gain_dbi: SGH 增益 (dBi)
        probe_gain_dbi: 探头增益 (dBi)
        cable_loss_db: 电缆损耗 (dB)

    Returns:
        路损 (dB)，正值
    """
    # 对于 VNA S21 测量: S21 = -PathLoss + G_sgh + G_probe - CableLoss
    # 因此: PathLoss = -S21 + G_sgh + G_probe - CableLoss
    path_loss = transmitted_power_dbm - received_power_dbm + sgh_gain_dbi + probe_gain_dbi - cable_loss_db
    return abs(path_loss)


# ==================== 探头路损校准服务 ====================

class ProbePathLossCalibrationService:
    """
    探头路损校准服务

    测量 SGH 到每个探头的空间路径损耗。

    校准方法:
    1. 将 SGH 置于静区中心 (转台位置)
    2. 使用 VNA 测量 SGH 到每个探头的 S21
    3. 计算每个探头的路损: PathLoss = |S21| + G_sgh + G_probe - CableLoss
    4. 记录双极化数据 (V/H)
    """

    def __init__(self, db: Session, use_mock: bool = True):
        """
        初始化服务

        Args:
            db: 数据库会话
            use_mock: 是否使用 mock 数据 (开发模式)
        """
        self.db = db
        self.use_mock = use_mock

    async def start_calibration(
        self,
        chamber_id: UUID,
        frequency_mhz: float,
        sgh_model: str,
        sgh_gain_dbi: float,
        sgh_serial: Optional[str] = None,
        vna_id: Optional[str] = None,
        cable_loss_db: float = 0.0,
        probe_ids: Optional[List[int]] = None,
        polarizations: Optional[List[PolarizationType]] = None,
        calibrated_by: str = "System"
    ) -> CalibrationResult:
        """
        启动探头路损校准

        Args:
            chamber_id: 暗室配置 ID
            frequency_mhz: 测量频率 (MHz)
            sgh_model: SGH 型号
            sgh_gain_dbi: SGH 标定增益 (dBi)
            sgh_serial: SGH 序列号
            vna_id: VNA 设备 ID
            cable_loss_db: 测量电缆损耗 (dB)
            probe_ids: 要校准的探头 ID 列表，None 表示所有
            polarizations: 要校准的极化类型
            calibrated_by: 校准人员

        Returns:
            CalibrationResult
        """
        # 验证暗室配置
        chamber = self.db.query(ChamberConfiguration).filter(
            ChamberConfiguration.id == chamber_id
        ).first()

        if not chamber:
            return CalibrationResult(
                success=False,
                message=f"Chamber configuration {chamber_id} not found"
            )

        # 默认校准所有探头
        if probe_ids is None:
            probe_ids = list(range(chamber.num_probes))

        # 默认双极化
        if polarizations is None:
            polarizations = [PolarizationType.V, PolarizationType.H]

        warnings = []
        probe_path_losses = {}

        # 遍历每个探头
        for probe_id in probe_ids:
            probe_data = {
                "path_loss_db": 0.0,
                "uncertainty_db": 0.5,
                "pol_v_db": None,
                "pol_h_db": None
            }

            for pol in polarizations:
                try:
                    if self.use_mock:
                        measurement = self._mock_path_loss_measurement(
                            probe_id, pol, frequency_mhz,
                            chamber.chamber_radius_m, sgh_gain_dbi,
                            chamber.probe_gain_dbi
                        )
                    else:
                        measurement = await self._real_path_loss_measurement(
                            probe_id, pol, frequency_mhz, vna_id,
                            sgh_gain_dbi, chamber.probe_gain_dbi, cable_loss_db
                        )

                    # 存储极化数据
                    if pol == PolarizationType.V:
                        probe_data["pol_v_db"] = measurement.path_loss_db
                    else:
                        probe_data["pol_h_db"] = measurement.path_loss_db

                    # 更新不确定度
                    probe_data["uncertainty_db"] = max(
                        probe_data["uncertainty_db"],
                        measurement.uncertainty_db
                    )

                    # 检查不确定度
                    if measurement.uncertainty_db > PATH_LOSS_UNCERTAINTY_THRESHOLD_DB:
                        warnings.append(
                            f"Probe {probe_id} pol {pol.value}: uncertainty "
                            f"{measurement.uncertainty_db:.2f} dB exceeds threshold"
                        )

                except Exception as e:
                    logger.error(f"Path loss measurement failed for probe {probe_id}: {e}")
                    return CalibrationResult(
                        success=False,
                        message=f"Measurement failed for probe {probe_id}: {str(e)}"
                    )

            # 计算平均路损
            valid_losses = [v for v in [probe_data["pol_v_db"], probe_data["pol_h_db"]] if v is not None]
            if valid_losses:
                probe_data["path_loss_db"] = statistics.mean(valid_losses)

            probe_path_losses[str(probe_id)] = probe_data

        # 计算统计数据
        all_losses = [float(d["path_loss_db"]) for d in probe_path_losses.values() if d["path_loss_db"]]
        avg_loss = float(statistics.mean(all_losses)) if all_losses else 0.0
        max_loss = float(max(all_losses)) if all_losses else 0.0
        min_loss = float(min(all_losses)) if all_losses else 0.0
        std_dev = float(statistics.stdev(all_losses)) if len(all_losses) > 1 else 0.0

        # 创建校准记录
        calibration = ProbePathLossCalibration(
            chamber_id=chamber_id,
            frequency_mhz=frequency_mhz,
            probe_path_losses=probe_path_losses,
            sgh_model=sgh_model,
            sgh_serial=sgh_serial,
            sgh_gain_dbi=sgh_gain_dbi,
            vna_model="Mock VNA" if self.use_mock else vna_id,
            cable_loss_db=cable_loss_db,
            measurement_distance_m=chamber.chamber_radius_m,
            avg_path_loss_db=avg_loss,
            max_path_loss_db=max_loss,
            min_path_loss_db=min_loss,
            std_dev_db=std_dev,
            calibrated_at=datetime.utcnow(),
            calibrated_by=calibrated_by,
            valid_until=datetime.utcnow() + timedelta(days=PATH_LOSS_VALIDITY_DAYS),
            status=CalibrationStatus.VALID.value
        )

        self.db.add(calibration)
        self.db.commit()
        self.db.refresh(calibration)

        return CalibrationResult(
            success=True,
            message=f"Path loss calibration completed for {len(probe_ids)} probes",
            data={
                "calibration_id": str(calibration.id),
                "avg_path_loss_db": avg_loss,
                "max_path_loss_db": max_loss,
                "min_path_loss_db": min_loss,
                "std_dev_db": std_dev,
                "num_probes": len(probe_ids)
            },
            warnings=warnings
        )

    def _mock_path_loss_measurement(
        self,
        probe_id: int,
        polarization: PolarizationType,
        frequency_mhz: float,
        chamber_radius_m: float,
        sgh_gain_dbi: float,
        probe_gain_dbi: float
    ) -> PathLossMeasurement:
        """生成 mock 路损测量数据"""
        # 计算理论 FSPL
        fspl = calculate_fspl(frequency_mhz, chamber_radius_m)

        # 添加探头位置相关的变化 (±2 dB)
        position_variation = np.sin(probe_id * 0.3) * 2.0

        # 添加极化相关的变化 (±0.5 dB)
        pol_variation = 0.5 if polarization == PolarizationType.V else -0.3

        # 添加随机噪声
        noise = np.random.normal(0, 0.3)

        # 总路损
        path_loss = fspl + position_variation + pol_variation + noise

        # 不确定度
        uncertainty = 0.3 + abs(noise) * 0.5

        return PathLossMeasurement(
            probe_id=probe_id,
            polarization=polarization.value,
            path_loss_db=float(path_loss),
            uncertainty_db=float(uncertainty)
        )

    async def _real_path_loss_measurement(
        self,
        probe_id: int,
        polarization: PolarizationType,
        frequency_mhz: float,
        vna_id: str,
        sgh_gain_dbi: float,
        probe_gain_dbi: float,
        cable_loss_db: float
    ) -> PathLossMeasurement:
        """
        执行真实的路损测量

        TODO: 集成实际 VNA 驱动
        """
        # 这里应该调用 VNA HAL 驱动
        # 目前返回 mock 数据
        raise NotImplementedError("Real VNA measurement not implemented yet")

    def get_latest_calibration(
        self,
        chamber_id: UUID,
        frequency_mhz: Optional[float] = None
    ) -> Optional[ProbePathLossCalibration]:
        """获取最新的路损校准数据"""
        query = self.db.query(ProbePathLossCalibration).filter(
            ProbePathLossCalibration.chamber_id == chamber_id,
            ProbePathLossCalibration.status == CalibrationStatus.VALID.value
        )

        if frequency_mhz:
            # 查找最接近的频率
            query = query.filter(
                ProbePathLossCalibration.frequency_mhz.between(
                    frequency_mhz * 0.95, frequency_mhz * 1.05
                )
            )

        return query.order_by(desc(ProbePathLossCalibration.calibrated_at)).first()

    def get_path_loss_for_probe(
        self,
        chamber_id: UUID,
        probe_id: int,
        polarization: str = "V",
        frequency_mhz: Optional[float] = None
    ) -> Optional[float]:
        """
        获取特定探头的路损值

        用于测量补偿。

        Args:
            chamber_id: 暗室配置 ID
            probe_id: 探头 ID
            polarization: 极化类型 ("V" 或 "H")
            frequency_mhz: 频率 (MHz)，用于查找最接近的校准

        Returns:
            路损值 (dB) 或 None
        """
        calibration = self.get_latest_calibration(chamber_id, frequency_mhz)
        if not calibration:
            return None

        probe_data = calibration.probe_path_losses.get(str(probe_id))
        if not probe_data:
            return None

        if polarization.upper() == "V":
            return probe_data.get("pol_v_db") or probe_data.get("path_loss_db")
        else:
            return probe_data.get("pol_h_db") or probe_data.get("path_loss_db")


# ==================== RF 链路增益校准服务 ====================

class RFChainCalibrationService:
    """
    RF 链路增益校准服务

    校准有源器件 (LNA, PA) 的增益和链路总增益。

    上行链路 (UL): 探头 → 双工器 → LNA → 电缆 → 信道仿真器
    下行链路 (DL): 信道仿真器 → 电缆 → PA → 双工器 → 探头
    """

    def __init__(self, db: Session, use_mock: bool = True):
        self.db = db
        self.use_mock = use_mock

    async def calibrate_uplink(
        self,
        chamber_id: UUID,
        frequency_mhz: float,
        vna_id: Optional[str] = None,
        power_meter_id: Optional[str] = None,
        calibrated_by: str = "System"
    ) -> CalibrationResult:
        """
        校准上行链路

        测量: 探头 → LNA → 信道仿真器 的总增益

        Args:
            chamber_id: 暗室配置 ID
            frequency_mhz: 测量频率
            vna_id: VNA 设备 ID
            power_meter_id: 功率计设备 ID
            calibrated_by: 校准人员
        """
        # 获取暗室配置
        chamber = self.db.query(ChamberConfiguration).filter(
            ChamberConfiguration.id == chamber_id
        ).first()

        if not chamber:
            return CalibrationResult(
                success=False,
                message=f"Chamber configuration {chamber_id} not found"
            )

        # 检查是否需要上行链路校准
        if not chamber.has_lna:
            return CalibrationResult(
                success=True,
                message="Chamber does not have LNA, no uplink calibration needed",
                data={"has_lna": False}
            )

        try:
            if self.use_mock:
                measurement = self._mock_uplink_measurement(chamber)
            else:
                measurement = await self._real_uplink_measurement(
                    chamber, frequency_mhz, vna_id, power_meter_id
                )

            # 创建校准记录
            calibration = RFChainCalibration(
                chamber_id=chamber_id,
                chain_type=ChainTypeEnum.UPLINK.value,
                frequency_mhz=frequency_mhz,
                has_lna=True,
                lna_gain_measured_db=measurement.lna_gain_db,
                has_duplexer=chamber.has_duplexer,
                duplexer_insertion_loss_db=measurement.duplexer_loss_db,
                cable_loss_to_ce_db=measurement.cable_loss_db,
                total_chain_gain_db=measurement.total_gain_db,
                vna_model="Mock VNA" if self.use_mock else vna_id,
                power_meter_model="Mock PM" if self.use_mock else power_meter_id,
                calibrated_at=datetime.utcnow(),
                calibrated_by=calibrated_by,
                valid_until=datetime.utcnow() + timedelta(days=RF_CHAIN_VALIDITY_DAYS),
                status=CalibrationStatus.VALID.value
            )

            self.db.add(calibration)
            self.db.commit()
            self.db.refresh(calibration)

            return CalibrationResult(
                success=True,
                message="Uplink chain calibration completed",
                data={
                    "calibration_id": str(calibration.id),
                    "lna_gain_db": measurement.lna_gain_db,
                    "total_chain_gain_db": measurement.total_gain_db
                }
            )

        except Exception as e:
            logger.error(f"Uplink calibration failed: {e}")
            return CalibrationResult(
                success=False,
                message=f"Uplink calibration failed: {str(e)}"
            )

    async def calibrate_downlink(
        self,
        chamber_id: UUID,
        frequency_mhz: float,
        vna_id: Optional[str] = None,
        power_meter_id: Optional[str] = None,
        signal_generator_id: Optional[str] = None,
        calibrated_by: str = "System"
    ) -> CalibrationResult:
        """
        校准下行链路

        测量: 信道仿真器 → PA → 探头 的总增益
        """
        chamber = self.db.query(ChamberConfiguration).filter(
            ChamberConfiguration.id == chamber_id
        ).first()

        if not chamber:
            return CalibrationResult(
                success=False,
                message=f"Chamber configuration {chamber_id} not found"
            )

        # 检查是否需要下行链路校准
        if not chamber.has_pa:
            return CalibrationResult(
                success=True,
                message="Chamber does not have PA, no downlink calibration needed",
                data={"has_pa": False}
            )

        try:
            if self.use_mock:
                measurement = self._mock_downlink_measurement(chamber)
            else:
                measurement = await self._real_downlink_measurement(
                    chamber, frequency_mhz, vna_id, power_meter_id, signal_generator_id
                )

            calibration = RFChainCalibration(
                chamber_id=chamber_id,
                chain_type=ChainTypeEnum.DOWNLINK.value,
                frequency_mhz=frequency_mhz,
                has_pa=True,
                pa_gain_measured_db=measurement.pa_gain_db,
                has_duplexer=chamber.has_duplexer,
                duplexer_insertion_loss_db=measurement.duplexer_loss_db,
                cable_loss_to_probe_db=measurement.cable_loss_db,
                total_chain_gain_db=measurement.total_gain_db,
                vna_model="Mock VNA" if self.use_mock else vna_id,
                power_meter_model="Mock PM" if self.use_mock else power_meter_id,
                signal_generator_model="Mock SG" if self.use_mock else signal_generator_id,
                calibrated_at=datetime.utcnow(),
                calibrated_by=calibrated_by,
                valid_until=datetime.utcnow() + timedelta(days=RF_CHAIN_VALIDITY_DAYS),
                status=CalibrationStatus.VALID.value
            )

            self.db.add(calibration)
            self.db.commit()
            self.db.refresh(calibration)

            return CalibrationResult(
                success=True,
                message="Downlink chain calibration completed",
                data={
                    "calibration_id": str(calibration.id),
                    "pa_gain_db": measurement.pa_gain_db,
                    "total_chain_gain_db": measurement.total_gain_db
                }
            )

        except Exception as e:
            logger.error(f"Downlink calibration failed: {e}")
            return CalibrationResult(
                success=False,
                message=f"Downlink calibration failed: {str(e)}"
            )

    def _mock_uplink_measurement(self, chamber: ChamberConfiguration) -> ChainGainMeasurement:
        """生成 mock 上行链路测量数据"""
        # LNA 增益 (基于配置 + 随机变化)
        lna_gain = chamber.lna_gain_db or 20.0
        lna_gain_measured = lna_gain + np.random.normal(0, 0.3)

        # 双工器损耗
        duplexer_loss = chamber.duplexer_insertion_loss_db or 0.0
        if chamber.has_duplexer:
            duplexer_loss += np.random.normal(0, 0.1)

        # 电缆损耗
        cable_loss = chamber.typical_cable_loss_db + np.random.normal(0, 0.2)

        # 总增益 = LNA - 双工器 - 电缆
        total_gain = lna_gain_measured - duplexer_loss - cable_loss

        return ChainGainMeasurement(
            total_gain_db=total_gain,
            lna_gain_db=lna_gain_measured,
            duplexer_loss_db=duplexer_loss,
            cable_loss_db=cable_loss
        )

    def _mock_downlink_measurement(self, chamber: ChamberConfiguration) -> ChainGainMeasurement:
        """生成 mock 下行链路测量数据"""
        # PA 增益
        pa_gain = chamber.pa_gain_db or 20.0
        pa_gain_measured = pa_gain + np.random.normal(0, 0.3)

        # 双工器损耗
        duplexer_loss = chamber.duplexer_insertion_loss_db or 0.0
        if chamber.has_duplexer:
            duplexer_loss += np.random.normal(0, 0.1)

        # 电缆损耗
        cable_loss = chamber.typical_cable_loss_db + np.random.normal(0, 0.2)

        # 总增益 = PA - 双工器 - 电缆
        total_gain = pa_gain_measured - duplexer_loss - cable_loss

        return ChainGainMeasurement(
            total_gain_db=total_gain,
            pa_gain_db=pa_gain_measured,
            duplexer_loss_db=duplexer_loss,
            cable_loss_db=cable_loss
        )

    async def _real_uplink_measurement(
        self,
        chamber: ChamberConfiguration,
        frequency_mhz: float,
        vna_id: str,
        power_meter_id: str
    ) -> ChainGainMeasurement:
        """执行真实的上行链路测量"""
        raise NotImplementedError("Real uplink measurement not implemented yet")

    async def _real_downlink_measurement(
        self,
        chamber: ChamberConfiguration,
        frequency_mhz: float,
        vna_id: str,
        power_meter_id: str,
        signal_generator_id: str
    ) -> ChainGainMeasurement:
        """执行真实的下行链路测量"""
        raise NotImplementedError("Real downlink measurement not implemented yet")

    def get_latest_uplink_calibration(
        self,
        chamber_id: UUID,
        frequency_mhz: Optional[float] = None
    ) -> Optional[RFChainCalibration]:
        """获取最新的上行链路校准"""
        query = self.db.query(RFChainCalibration).filter(
            RFChainCalibration.chamber_id == chamber_id,
            RFChainCalibration.chain_type == ChainTypeEnum.UPLINK.value,
            RFChainCalibration.status == CalibrationStatus.VALID.value
        )

        if frequency_mhz:
            query = query.filter(
                RFChainCalibration.frequency_mhz.between(
                    frequency_mhz * 0.95, frequency_mhz * 1.05
                )
            )

        return query.order_by(desc(RFChainCalibration.calibrated_at)).first()

    def get_latest_downlink_calibration(
        self,
        chamber_id: UUID,
        frequency_mhz: Optional[float] = None
    ) -> Optional[RFChainCalibration]:
        """获取最新的下行链路校准"""
        query = self.db.query(RFChainCalibration).filter(
            RFChainCalibration.chamber_id == chamber_id,
            RFChainCalibration.chain_type == ChainTypeEnum.DOWNLINK.value,
            RFChainCalibration.status == CalibrationStatus.VALID.value
        )

        if frequency_mhz:
            query = query.filter(
                RFChainCalibration.frequency_mhz.between(
                    frequency_mhz * 0.95, frequency_mhz * 1.05
                )
            )

        return query.order_by(desc(RFChainCalibration.calibrated_at)).first()

    def get_uplink_gain(self, chamber_id: UUID, frequency_mhz: Optional[float] = None) -> Optional[float]:
        """获取上行链路总增益"""
        cal = self.get_latest_uplink_calibration(chamber_id, frequency_mhz)
        return cal.total_chain_gain_db if cal else None

    def get_downlink_gain(self, chamber_id: UUID, frequency_mhz: Optional[float] = None) -> Optional[float]:
        """获取下行链路总增益"""
        cal = self.get_latest_downlink_calibration(chamber_id, frequency_mhz)
        return cal.total_chain_gain_db if cal else None


# ==================== 多频点路损校准服务 ====================

class MultiFrequencyPathLossService:
    """
    多频点路损校准服务

    存储扫频校准的路损数据，支持频率插值。
    """

    def __init__(self, db: Session, use_mock: bool = True):
        self.db = db
        self.use_mock = use_mock

    async def calibrate_frequency_sweep(
        self,
        chamber_id: UUID,
        probe_ids: List[int],
        polarization: PolarizationType,
        freq_start_mhz: float,
        freq_stop_mhz: float,
        freq_step_mhz: float,
        sgh_model: str,
        sgh_gain_dbi: float,
        vna_id: Optional[str] = None,
        calibrated_by: str = "System"
    ) -> CalibrationResult:
        """
        执行多频点扫频校准

        Args:
            chamber_id: 暗室配置 ID
            probe_ids: 探头 ID 列表
            polarization: 极化类型
            freq_start_mhz: 起始频率
            freq_stop_mhz: 终止频率
            freq_step_mhz: 频率步进
            sgh_model: SGH 型号
            sgh_gain_dbi: SGH 增益
            vna_id: VNA 设备 ID
            calibrated_by: 校准人员
        """
        chamber = self.db.query(ChamberConfiguration).filter(
            ChamberConfiguration.id == chamber_id
        ).first()

        if not chamber:
            return CalibrationResult(
                success=False,
                message=f"Chamber configuration {chamber_id} not found"
            )

        # 生成频率点
        num_points = int((freq_stop_mhz - freq_start_mhz) / freq_step_mhz) + 1
        frequency_points = [freq_start_mhz + i * freq_step_mhz for i in range(num_points)]

        calibration_ids = []

        for probe_id in probe_ids:
            try:
                if self.use_mock:
                    path_losses, uncertainties = self._mock_frequency_sweep(
                        probe_id, polarization, frequency_points,
                        chamber.chamber_radius_m, chamber.probe_gain_dbi
                    )
                else:
                    path_losses, uncertainties = await self._real_frequency_sweep(
                        probe_id, polarization, frequency_points,
                        vna_id, sgh_gain_dbi, chamber.probe_gain_dbi
                    )

                calibration = MultiFrequencyPathLoss(
                    chamber_id=chamber_id,
                    probe_id=probe_id,
                    polarization=polarization.value,
                    freq_start_mhz=freq_start_mhz,
                    freq_stop_mhz=freq_stop_mhz,
                    freq_step_mhz=freq_step_mhz,
                    num_points=num_points,
                    frequency_points_mhz=frequency_points,
                    path_loss_db=path_losses,
                    uncertainty_db=uncertainties,
                    calibrated_at=datetime.utcnow(),
                    calibrated_by=calibrated_by,
                    valid_until=datetime.utcnow() + timedelta(days=MULTI_FREQ_VALIDITY_DAYS),
                    status=CalibrationStatus.VALID.value
                )

                self.db.add(calibration)
                self.db.flush()
                calibration_ids.append(str(calibration.id))

            except Exception as e:
                logger.error(f"Multi-freq calibration failed for probe {probe_id}: {e}")
                return CalibrationResult(
                    success=False,
                    message=f"Calibration failed for probe {probe_id}: {str(e)}"
                )

        self.db.commit()

        return CalibrationResult(
            success=True,
            message=f"Multi-frequency calibration completed for {len(probe_ids)} probes",
            data={
                "calibration_ids": calibration_ids,
                "num_probes": len(probe_ids),
                "num_freq_points": num_points,
                "freq_range": f"{freq_start_mhz}-{freq_stop_mhz} MHz"
            }
        )

    def _mock_frequency_sweep(
        self,
        probe_id: int,
        polarization: PolarizationType,
        frequency_points: List[float],
        chamber_radius_m: float,
        probe_gain_dbi: float
    ) -> Tuple[List[float], List[float]]:
        """生成 mock 扫频数据"""
        path_losses = []
        uncertainties = []

        for freq in frequency_points:
            # 基础 FSPL
            fspl = calculate_fspl(freq, chamber_radius_m)

            # 频率相关变化
            freq_variation = 0.5 * np.sin((freq - frequency_points[0]) * 0.01)

            # 探头位置变化
            position_variation = np.sin(probe_id * 0.3) * 1.5

            # 极化变化
            pol_variation = 0.3 if polarization == PolarizationType.V else -0.2

            # 随机噪声
            noise = np.random.normal(0, 0.2)

            path_loss = fspl + freq_variation + position_variation + pol_variation + noise
            uncertainty = 0.3 + abs(noise) * 0.3

            path_losses.append(path_loss)
            uncertainties.append(uncertainty)

        return path_losses, uncertainties

    async def _real_frequency_sweep(
        self,
        probe_id: int,
        polarization: PolarizationType,
        frequency_points: List[float],
        vna_id: str,
        sgh_gain_dbi: float,
        probe_gain_dbi: float
    ) -> Tuple[List[float], List[float]]:
        """执行真实的扫频测量"""
        raise NotImplementedError("Real frequency sweep not implemented yet")

    def get_path_loss_at_frequency(
        self,
        chamber_id: UUID,
        probe_id: int,
        polarization: str,
        frequency_mhz: float
    ) -> Optional[float]:
        """
        获取指定频率的路损 (支持插值)

        Args:
            chamber_id: 暗室 ID
            probe_id: 探头 ID
            polarization: 极化类型
            frequency_mhz: 目标频率

        Returns:
            插值后的路损值
        """
        calibration = self.db.query(MultiFrequencyPathLoss).filter(
            MultiFrequencyPathLoss.chamber_id == chamber_id,
            MultiFrequencyPathLoss.probe_id == probe_id,
            MultiFrequencyPathLoss.polarization == polarization,
            MultiFrequencyPathLoss.status == CalibrationStatus.VALID.value,
            MultiFrequencyPathLoss.freq_start_mhz <= frequency_mhz,
            MultiFrequencyPathLoss.freq_stop_mhz >= frequency_mhz
        ).order_by(desc(MultiFrequencyPathLoss.calibrated_at)).first()

        if not calibration:
            return None

        # 线性插值
        freq_points = calibration.frequency_points_mhz
        path_losses = calibration.path_loss_db

        return float(np.interp(frequency_mhz, freq_points, path_losses))
