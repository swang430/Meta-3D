"""
RF Switch Matrix Calibration Service

射频开关矩阵校准业务逻辑。

CAL-02: RF Switch 校准
- 开关插入损耗 (Insertion Loss)
- 端口间隔离度 (Isolation)
- 切换一致性 (Repeatability)

参考: docs/features/calibration/calibration-topology.md (Path B')
"""
import numpy as np
from typing import List, Dict, Optional, Any
from datetime import datetime, timedelta
from uuid import UUID, uuid4
from sqlalchemy.orm import Session
from sqlalchemy import desc
import logging

from app.models.probe_calibration import RFSwitchCalibration

logger = logging.getLogger(__name__)


# ==================== 校准常数 ====================

# RF Switch 校准有效期 (天)
RF_SWITCH_VALIDITY_DAYS = 180  # 6 个月

# 插入损耗阈值 (dB) - 超过此值告警
INSERTION_LOSS_THRESHOLD_DB = 2.0

# 隔离度阈值 (dB) - 低于此值告警 (负值，越小越好)
ISOLATION_THRESHOLD_DB = -60.0

# 切换一致性阈值 (dB) - 超过此值告警
REPEATABILITY_THRESHOLD_DB = 0.1


# ==================== 数据类 ====================

class SwitchPortMeasurement:
    """单个开关端口测量结果"""
    def __init__(
        self,
        input_port: int,
        output_port: int,
        insertion_loss_db: float,
        phase_deg: float = 0.0,
        uncertainty_db: float = 0.05
    ):
        self.input_port = input_port
        self.output_port = output_port
        self.insertion_loss_db = insertion_loss_db
        self.phase_deg = phase_deg
        self.uncertainty_db = uncertainty_db


class IsolationMeasurement:
    """端口间隔离度测量结果"""
    def __init__(
        self,
        port_a: int,
        port_b: int,
        isolation_db: float
    ):
        self.port_a = port_a
        self.port_b = port_b
        self.isolation_db = isolation_db


class SwitchCalibrationResult:
    """开关校准结果"""
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


# ==================== RF Switch 校准服务 ====================

class RFSwitchCalibrationService:
    """
    RF 开关矩阵校准服务

    测量射频开关矩阵的插入损耗、隔离度和一致性。

    校准方法 (Path B' - 旁路 CE):
    1. VNA Port 1 → Switch Input
    2. Switch Output → VNA Port 2
    3. 测量各路径的 S21 (插入损耗和相位)
    4. 测量非通路端口的 S21 (隔离度)
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

    async def calibrate_switch_matrix(
        self,
        chamber_id: UUID,
        frequency_mhz: float,
        num_input_ports: int = 4,
        num_output_ports: int = 32,
        vna_id: Optional[str] = None,
        calibrated_by: str = "System"
    ) -> SwitchCalibrationResult:
        """
        校准整个开关矩阵

        Args:
            chamber_id: 暗室配置 ID
            frequency_mhz: 测量频率 (MHz)
            num_input_ports: 输入端口数量
            num_output_ports: 输出端口数量 (对应探头数)
            vna_id: VNA 设备 ID
            calibrated_by: 校准人员

        Returns:
            SwitchCalibrationResult
        """
        warnings = []
        port_measurements = {}
        isolation_measurements = []

        logger.info(f"Starting RF Switch calibration at {frequency_mhz} MHz")

        # 测量每个路径的插入损耗
        for input_port in range(num_input_ports):
            for output_port in range(num_output_ports):
                try:
                    if self.use_mock:
                        measurement = self._mock_port_measurement(
                            input_port, output_port, frequency_mhz
                        )
                    else:
                        measurement = await self._real_port_measurement(
                            input_port, output_port, frequency_mhz, vna_id
                        )

                    port_key = f"{input_port}-{output_port}"
                    port_measurements[port_key] = {
                        "input_port": input_port,
                        "output_port": output_port,
                        "insertion_loss_db": measurement.insertion_loss_db,
                        "phase_deg": measurement.phase_deg,
                        "uncertainty_db": measurement.uncertainty_db
                    }

                    # 检查插入损耗阈值
                    if measurement.insertion_loss_db > INSERTION_LOSS_THRESHOLD_DB:
                        warnings.append(
                            f"Port {input_port}→{output_port}: insertion loss "
                            f"{measurement.insertion_loss_db:.2f} dB exceeds threshold"
                        )

                except Exception as e:
                    logger.error(f"Switch measurement failed for {input_port}→{output_port}: {e}")
                    return SwitchCalibrationResult(
                        success=False,
                        message=f"Measurement failed for port {input_port}→{output_port}: {str(e)}"
                    )

        # 测量隔离度 (相邻端口)
        for output_port in range(num_output_ports - 1):
            try:
                if self.use_mock:
                    isolation = self._mock_isolation_measurement(output_port, output_port + 1)
                else:
                    isolation = await self._real_isolation_measurement(
                        output_port, output_port + 1, frequency_mhz, vna_id
                    )

                isolation_measurements.append({
                    "port_a": isolation.port_a,
                    "port_b": isolation.port_b,
                    "isolation_db": isolation.isolation_db
                })

                # 检查隔离度阈值
                if isolation.isolation_db > ISOLATION_THRESHOLD_DB:
                    warnings.append(
                        f"Ports {output_port}↔{output_port + 1}: isolation "
                        f"{isolation.isolation_db:.1f} dB is poor (threshold: {ISOLATION_THRESHOLD_DB} dB)"
                    )

            except Exception as e:
                logger.warning(f"Isolation measurement failed for {output_port}↔{output_port + 1}: {e}")

        # 计算统计数据
        all_losses = [m["insertion_loss_db"] for m in port_measurements.values()]
        avg_loss = np.mean(all_losses) if all_losses else 0
        max_loss = np.max(all_losses) if all_losses else 0
        min_loss = np.min(all_losses) if all_losses else 0
        std_dev = np.std(all_losses) if len(all_losses) > 1 else 0

        all_isolations = [m["isolation_db"] for m in isolation_measurements]
        avg_isolation = np.mean(all_isolations) if all_isolations else 0
        worst_isolation = np.max(all_isolations) if all_isolations else 0

        # 创建校准记录 (存入数据库)
        calibration_data = {
            "chamber_id": str(chamber_id),
            "frequency_mhz": frequency_mhz,
            "num_input_ports": num_input_ports,
            "num_output_ports": num_output_ports,
            "port_measurements": port_measurements,
            "isolation_measurements": isolation_measurements,
            "statistics": {
                "avg_insertion_loss_db": float(avg_loss),
                "max_insertion_loss_db": float(max_loss),
                "min_insertion_loss_db": float(min_loss),
                "std_dev_db": float(std_dev),
                "avg_isolation_db": float(avg_isolation),
                "worst_isolation_db": float(worst_isolation)
            },
            "vna_model": "Mock VNA" if self.use_mock else vna_id,
            "calibrated_at": datetime.utcnow().isoformat(),
            "calibrated_by": calibrated_by,
            "valid_until": (datetime.utcnow() + timedelta(days=RF_SWITCH_VALIDITY_DAYS)).isoformat()
        }

        # 持久化到数据库
        try:
            db_record = RFSwitchCalibration(
                id=uuid4(),
                chamber_id=chamber_id,
                frequency_mhz=frequency_mhz,
                num_input_ports=num_input_ports,
                num_output_ports=num_output_ports,
                port_measurements=port_measurements,
                isolation_measurements=isolation_measurements,
                avg_insertion_loss_db=float(avg_loss),
                max_insertion_loss_db=float(max_loss),
                min_insertion_loss_db=float(min_loss),
                std_dev_db=float(std_dev),
                avg_isolation_db=float(avg_isolation),
                worst_isolation_db=float(worst_isolation),
                vna_model="Mock VNA" if self.use_mock else vna_id,
                calibrated_at=datetime.utcnow(),
                calibrated_by=calibrated_by,
                valid_until=datetime.utcnow() + timedelta(days=RF_SWITCH_VALIDITY_DAYS),
                status="valid"
            )
            self.db.add(db_record)
            self.db.commit()
            logger.info(f"RF Switch 校准结果已持久化到数据库: {db_record.id}")
        except Exception as e:
            self.db.rollback()
            logger.error(f"RF Switch 校准结果持久化失败: {e}")

        logger.info(f"RF Switch calibration completed: avg loss {avg_loss:.2f} dB")

        return SwitchCalibrationResult(
            success=True,
            message=f"RF Switch calibration completed for {num_input_ports}x{num_output_ports} matrix",
            data={
                "calibration": calibration_data,
                "avg_insertion_loss_db": float(avg_loss),
                "max_insertion_loss_db": float(max_loss),
                "std_dev_db": float(std_dev),
                "avg_isolation_db": float(avg_isolation),
                "worst_isolation_db": float(worst_isolation),
                "num_paths_calibrated": len(port_measurements)
            },
            warnings=warnings
        )

    async def measure_repeatability(
        self,
        input_port: int,
        output_port: int,
        frequency_mhz: float,
        num_cycles: int = 10,
        vna_id: Optional[str] = None
    ) -> SwitchCalibrationResult:
        """
        测量开关切换一致性

        多次切换开关，测量插入损耗变化。

        Args:
            input_port: 输入端口
            output_port: 输出端口
            frequency_mhz: 测量频率
            num_cycles: 切换次数
            vna_id: VNA 设备 ID

        Returns:
            SwitchCalibrationResult
        """
        measurements = []

        for cycle in range(num_cycles):
            if self.use_mock:
                measurement = self._mock_port_measurement(input_port, output_port, frequency_mhz)
            else:
                measurement = await self._real_port_measurement(
                    input_port, output_port, frequency_mhz, vna_id
                )
            measurements.append(measurement.insertion_loss_db)

        # 计算一致性指标
        peak_to_peak = max(measurements) - min(measurements)
        std_dev = np.std(measurements)

        warnings = []
        if peak_to_peak > REPEATABILITY_THRESHOLD_DB:
            warnings.append(
                f"Repeatability {peak_to_peak:.3f} dB exceeds threshold {REPEATABILITY_THRESHOLD_DB} dB"
            )

        return SwitchCalibrationResult(
            success=True,
            message=f"Repeatability test completed: {num_cycles} cycles",
            data={
                "input_port": input_port,
                "output_port": output_port,
                "num_cycles": num_cycles,
                "measurements": measurements,
                "mean_loss_db": float(np.mean(measurements)),
                "std_dev_db": float(std_dev),
                "peak_to_peak_db": float(peak_to_peak),
                "pass": peak_to_peak <= REPEATABILITY_THRESHOLD_DB
            },
            warnings=warnings
        )

    def _mock_port_measurement(
        self,
        input_port: int,
        output_port: int,
        frequency_mhz: float
    ) -> SwitchPortMeasurement:
        """生成 mock 开关端口测量数据"""
        # 基础插入损耗 (典型值 1.0 - 1.5 dB)
        base_loss = 1.2

        # 端口相关变化 (±0.3 dB)
        port_variation = np.sin(output_port * 0.2) * 0.3

        # 频率相关变化 (高频损耗略大)
        freq_factor = 1 + (frequency_mhz - 3500) / 10000 * 0.2

        # 随机噪声
        noise = np.random.normal(0, 0.05)

        insertion_loss = (base_loss + port_variation) * freq_factor + noise

        # 相位 (每个端口有不同的电气长度)
        phase = (output_port * 11.25 + input_port * 45) % 360
        phase += np.random.normal(0, 2)  # 相位噪声

        return SwitchPortMeasurement(
            input_port=input_port,
            output_port=output_port,
            insertion_loss_db=insertion_loss,
            phase_deg=phase,
            uncertainty_db=0.05
        )

    def _mock_isolation_measurement(
        self,
        port_a: int,
        port_b: int
    ) -> IsolationMeasurement:
        """生成 mock 隔离度测量数据"""
        # 典型隔离度 -60 到 -80 dB
        base_isolation = -70

        # 相邻端口隔离度略差
        if abs(port_a - port_b) == 1:
            isolation = base_isolation + 10  # -60 dB
        else:
            isolation = base_isolation - 10  # -80 dB

        # 添加随机变化
        isolation += np.random.normal(0, 3)

        return IsolationMeasurement(
            port_a=port_a,
            port_b=port_b,
            isolation_db=isolation
        )

    async def _real_port_measurement(
        self,
        input_port: int,
        output_port: int,
        frequency_mhz: float,
        vna_id: str
    ) -> SwitchPortMeasurement:
        """
        执行真实的开关端口测量

        TODO: 集成实际 VNA 和 Switch Matrix 驱动
        """
        raise NotImplementedError("Real switch measurement not implemented yet")

    async def _real_isolation_measurement(
        self,
        port_a: int,
        port_b: int,
        frequency_mhz: float,
        vna_id: str
    ) -> IsolationMeasurement:
        """
        执行真实的隔离度测量

        TODO: 集成实际 VNA 驱动
        """
        raise NotImplementedError("Real isolation measurement not implemented yet")

    def get_insertion_loss(
        self,
        input_port: int,
        output_port: int,
        calibration_data: Dict
    ) -> Optional[float]:
        """
        从校准数据获取特定路径的插入损耗

        Args:
            input_port: 输入端口
            output_port: 输出端口
            calibration_data: 校准数据字典

        Returns:
            插入损耗 (dB) 或 None
        """
        port_key = f"{input_port}-{output_port}"
        port_data = calibration_data.get("port_measurements", {}).get(port_key)
        return port_data.get("insertion_loss_db") if port_data else None

    def get_compensation_matrix(
        self,
        calibration_data: Dict
    ) -> Dict[str, float]:
        """
        生成补偿矩阵

        返回各路径的补偿值，用于测量时校正开关损耗。

        Args:
            calibration_data: 校准数据

        Returns:
            路径-补偿值字典
        """
        compensation = {}
        port_measurements = calibration_data.get("port_measurements", {})

        for port_key, data in port_measurements.items():
            # 补偿值 = -插入损耗 (加上这个值可以抵消开关损耗)
            compensation[port_key] = -data.get("insertion_loss_db", 0)

        return compensation
