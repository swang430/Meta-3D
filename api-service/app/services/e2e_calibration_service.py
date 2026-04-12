"""
End-to-End Calibration Service (E2E)

端到端校准业务逻辑。

CAL-03: 端到端校准
- 全链路综合补偿矩阵生成
- 整合探头路损、RF Switch、UL/DL 链路校准数据
- 验证系统一致性

参考: docs/features/calibration/calibration-topology.md (Path A)

信号路径 (下行链路):
BS Emulator → Channel Emulator → RF Switch → PA → Probe → QZ → DUT
"""
import numpy as np
from typing import List, Dict, Optional, Any
from datetime import datetime, timedelta
from uuid import UUID, uuid4
from sqlalchemy.orm import Session
from sqlalchemy import desc
import logging

from app.models.probe_calibration import E2ECompensationMatrix

logger = logging.getLogger(__name__)


# ==================== 校准常数 ====================

# E2E 校准有效期 (天)
E2E_VALIDITY_DAYS = 30  # 1 个月

# 系统一致性阈值 (dB)
SYSTEM_CONSISTENCY_THRESHOLD_DB = 1.0

# 最大允许补偿值 (dB)
MAX_COMPENSATION_DB = 50.0


# ==================== 数据类 ====================

class ProbeCompensation:
    """单个探头的综合补偿数据"""
    def __init__(
        self,
        probe_id: int,
        polarization: str,
        frequency_mhz: float,
        # 各段补偿值
        path_loss_db: float = 0.0,
        switch_loss_db: float = 0.0,
        pa_gain_db: float = 0.0,
        lna_gain_db: float = 0.0,
        cable_loss_db: float = 0.0,
        # 综合补偿
        total_dl_compensation_db: float = 0.0,
        total_ul_compensation_db: float = 0.0
    ):
        self.probe_id = probe_id
        self.polarization = polarization
        self.frequency_mhz = frequency_mhz
        self.path_loss_db = path_loss_db
        self.switch_loss_db = switch_loss_db
        self.pa_gain_db = pa_gain_db
        self.lna_gain_db = lna_gain_db
        self.cable_loss_db = cable_loss_db
        self.total_dl_compensation_db = total_dl_compensation_db
        self.total_ul_compensation_db = total_ul_compensation_db

    def to_dict(self) -> Dict[str, Any]:
        return {
            "probe_id": self.probe_id,
            "polarization": self.polarization,
            "frequency_mhz": self.frequency_mhz,
            "path_loss_db": self.path_loss_db,
            "switch_loss_db": self.switch_loss_db,
            "pa_gain_db": self.pa_gain_db,
            "lna_gain_db": self.lna_gain_db,
            "cable_loss_db": self.cable_loss_db,
            "total_dl_compensation_db": self.total_dl_compensation_db,
            "total_ul_compensation_db": self.total_ul_compensation_db
        }


class CompensationMatrix:
    """综合补偿矩阵"""
    def __init__(
        self,
        chamber_id: UUID,
        frequency_mhz: float,
        num_probes: int,
        calibrated_at: datetime
    ):
        self.chamber_id = chamber_id
        self.frequency_mhz = frequency_mhz
        self.num_probes = num_probes
        self.calibrated_at = calibrated_at
        self.probes: Dict[str, ProbeCompensation] = {}

    def add_probe(self, compensation: ProbeCompensation):
        key = f"{compensation.probe_id}_{compensation.polarization}"
        self.probes[key] = compensation

    def get_compensation(self, probe_id: int, polarization: str) -> Optional[ProbeCompensation]:
        key = f"{probe_id}_{polarization}"
        return self.probes.get(key)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "chamber_id": str(self.chamber_id),
            "frequency_mhz": self.frequency_mhz,
            "num_probes": self.num_probes,
            "calibrated_at": self.calibrated_at.isoformat(),
            "probes": {k: v.to_dict() for k, v in self.probes.items()}
        }


class E2ECalibrationResult:
    """E2E 校准结果"""
    def __init__(
        self,
        success: bool,
        message: str,
        compensation_matrix: Optional[CompensationMatrix] = None,
        validation_results: Optional[Dict] = None,
        warnings: Optional[List[str]] = None
    ):
        self.success = success
        self.message = message
        self.compensation_matrix = compensation_matrix
        self.validation_results = validation_results or {}
        self.warnings = warnings or []


# ==================== E2E 校准服务 ====================

class E2ECalibrationService:
    """
    端到端校准服务

    整合所有校准数据，生成综合补偿矩阵。

    校准流程 (Path A - 经 CE):
    1. 收集探头路损校准数据
    2. 收集 RF Switch 校准数据
    3. 收集 UL/DL 链路校准数据
    4. 计算综合补偿矩阵
    5. 验证系统一致性
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

    async def generate_compensation_matrix(
        self,
        chamber_id: UUID,
        frequency_mhz: float,
        num_probes: int = 32,
        calibrated_by: str = "System"
    ) -> E2ECalibrationResult:
        """
        生成综合补偿矩阵

        整合所有校准数据，计算每个探头的端到端补偿值。

        Args:
            chamber_id: 暗室配置 ID
            frequency_mhz: 目标频率 (MHz)
            num_probes: 探头数量
            calibrated_by: 校准人员

        Returns:
            E2ECalibrationResult
        """
        warnings = []
        logger.info(f"Generating E2E compensation matrix at {frequency_mhz} MHz")

        # 收集各阶段校准数据
        try:
            # 1. 获取探头路损数据
            path_loss_data = await self._get_path_loss_data(chamber_id, frequency_mhz)
            if not path_loss_data:
                warnings.append("No path loss calibration found, using default values")

            # 2. 获取 RF Switch 数据
            switch_data = await self._get_switch_data(chamber_id, frequency_mhz)
            if not switch_data:
                warnings.append("No RF Switch calibration found, using default values")

            # 3. 获取 UL/DL 链路数据
            ul_data, dl_data = await self._get_chain_data(chamber_id, frequency_mhz)
            if not ul_data:
                warnings.append("No uplink chain calibration found, using default values")
            if not dl_data:
                warnings.append("No downlink chain calibration found, using default values")

        except Exception as e:
            logger.error(f"Failed to collect calibration data: {e}")
            return E2ECalibrationResult(
                success=False,
                message=f"Failed to collect calibration data: {str(e)}"
            )

        # 创建补偿矩阵
        matrix = CompensationMatrix(
            chamber_id=chamber_id,
            frequency_mhz=frequency_mhz,
            num_probes=num_probes,
            calibrated_at=datetime.utcnow()
        )

        # 计算每个探头的补偿值
        for probe_id in range(num_probes):
            for polarization in ["V", "H"]:
                compensation = self._calculate_probe_compensation(
                    probe_id=probe_id,
                    polarization=polarization,
                    frequency_mhz=frequency_mhz,
                    path_loss_data=path_loss_data,
                    switch_data=switch_data,
                    ul_data=ul_data,
                    dl_data=dl_data
                )
                matrix.add_probe(compensation)

        # 验证系统一致性
        validation_results = self._validate_consistency(matrix)
        if not validation_results["consistent"]:
            warnings.append(f"System consistency check failed: variation {validation_results['max_variation_db']:.2f} dB")

        # 计算统计数据
        all_dl_comps = [p.total_dl_compensation_db for p in matrix.probes.values()]
        all_ul_comps = [p.total_ul_compensation_db for p in matrix.probes.values()]

        stats = {
            "dl_compensation": {
                "avg_db": float(np.mean(all_dl_comps)),
                "max_db": float(np.max(all_dl_comps)),
                "min_db": float(np.min(all_dl_comps)),
                "std_db": float(np.std(all_dl_comps))
            },
            "ul_compensation": {
                "avg_db": float(np.mean(all_ul_comps)),
                "max_db": float(np.max(all_ul_comps)),
                "min_db": float(np.min(all_ul_comps)),
                "std_db": float(np.std(all_ul_comps))
            }
        }

        logger.info(f"E2E calibration completed: DL avg {stats['dl_compensation']['avg_db']:.2f} dB")

        # 持久化补偿矩阵到数据库
        try:
            probe_compensations_dict = {}
            for key, comp in matrix.probes.items():
                probe_compensations_dict[key] = {
                    "probe_id": comp.probe_id,
                    "polarization": comp.polarization,
                    "path_loss_db": comp.path_loss_db,
                    "cable_loss_db": comp.cable_loss_db,
                    "switch_loss_db": comp.switch_loss_db,
                    "pa_gain_db": comp.pa_gain_db,
                    "lna_gain_db": comp.lna_gain_db,
                    "total_dl_compensation_db": comp.total_dl_compensation_db,
                    "total_ul_compensation_db": comp.total_ul_compensation_db,
                }

            db_record = E2ECompensationMatrix(
                id=uuid4(),
                chamber_id=chamber_id,
                frequency_mhz=frequency_mhz,
                num_probes=num_probes,
                probe_compensations=probe_compensations_dict,
                dl_avg_compensation_db=stats["dl_compensation"]["avg_db"],
                dl_max_compensation_db=stats["dl_compensation"]["max_db"],
                dl_std_compensation_db=stats["dl_compensation"]["std_db"],
                ul_avg_compensation_db=stats["ul_compensation"]["avg_db"],
                ul_max_compensation_db=stats["ul_compensation"]["max_db"],
                ul_std_compensation_db=stats["ul_compensation"]["std_db"],
                consistency_check_pass=validation_results.get("consistent", False),
                max_variation_db=validation_results.get("max_variation_db", 0.0),
                warnings=warnings if warnings else None,
                calibrated_at=datetime.utcnow(),
                calibrated_by=calibrated_by,
                valid_until=datetime.utcnow() + timedelta(days=E2E_VALIDITY_DAYS),
                status="valid"
            )
            self.db.add(db_record)
            self.db.commit()
            logger.info(f"E2E 补偿矩阵已持久化到数据库: {db_record.id}")
        except Exception as e:
            self.db.rollback()
            logger.error(f"E2E 补偿矩阵持久化失败: {e}")

        return E2ECalibrationResult(
            success=True,
            message=f"E2E compensation matrix generated for {num_probes} probes",
            compensation_matrix=matrix,
            validation_results={
                "consistency": validation_results,
                "statistics": stats,
                "calibrated_by": calibrated_by,
                "valid_until": (datetime.utcnow() + timedelta(days=E2E_VALIDITY_DAYS)).isoformat()
            },
            warnings=warnings
        )

    def _calculate_probe_compensation(
        self,
        probe_id: int,
        polarization: str,
        frequency_mhz: float,
        path_loss_data: Optional[Dict],
        switch_data: Optional[Dict],
        ul_data: Optional[Dict],
        dl_data: Optional[Dict]
    ) -> ProbeCompensation:
        """计算单个探头的综合补偿值"""

        # 获取探头路损
        path_loss = self._get_probe_path_loss(path_loss_data, probe_id, polarization)

        # 获取开关损耗 (假设 input_port 0 对应所有探头)
        switch_loss = self._get_switch_loss(switch_data, 0, probe_id)

        # 获取 PA/LNA 增益和电缆损耗
        pa_gain = dl_data.get("pa_gain_db", 20.0) if dl_data else 20.0
        lna_gain = ul_data.get("lna_gain_db", 20.0) if ul_data else 20.0
        cable_loss = dl_data.get("cable_loss_db", 3.0) if dl_data else 3.0

        # 计算下行链路补偿
        # DL: CE_out → Cable → Switch → PA → Probe → QZ
        # 补偿 = -(CableLoss + SwitchLoss - PA_Gain + PathLoss)
        total_dl_compensation = -(cable_loss + switch_loss - pa_gain + path_loss)

        # 计算上行链路补偿
        # UL: QZ → Probe → LNA → Switch → Cable → CE_in
        # 补偿 = -(PathLoss - LNA_Gain + SwitchLoss + CableLoss)
        total_ul_compensation = -(path_loss - lna_gain + switch_loss + cable_loss)

        # 限制最大补偿值
        total_dl_compensation = np.clip(total_dl_compensation, -MAX_COMPENSATION_DB, MAX_COMPENSATION_DB)
        total_ul_compensation = np.clip(total_ul_compensation, -MAX_COMPENSATION_DB, MAX_COMPENSATION_DB)

        return ProbeCompensation(
            probe_id=probe_id,
            polarization=polarization,
            frequency_mhz=frequency_mhz,
            path_loss_db=path_loss,
            switch_loss_db=switch_loss,
            pa_gain_db=pa_gain,
            lna_gain_db=lna_gain,
            cable_loss_db=cable_loss,
            total_dl_compensation_db=float(total_dl_compensation),
            total_ul_compensation_db=float(total_ul_compensation)
        )

    def _validate_consistency(self, matrix: CompensationMatrix) -> Dict[str, Any]:
        """验证系统一致性"""
        dl_comps = [p.total_dl_compensation_db for p in matrix.probes.values()]

        max_variation = max(dl_comps) - min(dl_comps) if dl_comps else 0
        consistent = max_variation <= SYSTEM_CONSISTENCY_THRESHOLD_DB

        return {
            "consistent": consistent,
            "max_variation_db": max_variation,
            "threshold_db": SYSTEM_CONSISTENCY_THRESHOLD_DB
        }

    async def _get_path_loss_data(
        self, chamber_id: UUID, frequency_mhz: float
    ) -> Optional[Dict]:
        """获取探头路损校准数据"""
        if self.use_mock:
            return self._mock_path_loss_data(frequency_mhz)

        # TODO: 从数据库获取实际数据
        return None

    async def _get_switch_data(
        self, chamber_id: UUID, frequency_mhz: float
    ) -> Optional[Dict]:
        """获取 RF Switch 校准数据"""
        if self.use_mock:
            return self._mock_switch_data()

        # TODO: 从数据库获取实际数据
        return None

    async def _get_chain_data(
        self, chamber_id: UUID, frequency_mhz: float
    ) -> tuple:
        """获取 UL/DL 链路校准数据"""
        if self.use_mock:
            return self._mock_ul_data(), self._mock_dl_data()

        # TODO: 从数据库获取实际数据
        return None, None

    def _get_probe_path_loss(
        self, path_loss_data: Optional[Dict], probe_id: int, polarization: str
    ) -> float:
        """从路损数据获取特定探头的值"""
        if not path_loss_data:
            return 45.0  # 默认值

        probe_key = f"{probe_id}_{polarization}"
        return path_loss_data.get(probe_key, 45.0)

    def _get_switch_loss(
        self, switch_data: Optional[Dict], input_port: int, output_port: int
    ) -> float:
        """从开关数据获取特定路径的损耗"""
        if not switch_data:
            return 1.2  # 默认值

        port_key = f"{input_port}-{output_port}"
        return switch_data.get("port_measurements", {}).get(port_key, {}).get("insertion_loss_db", 1.2)

    # ==================== Mock 数据生成 ====================

    def _mock_path_loss_data(self, frequency_mhz: float) -> Dict:
        """生成 mock 路损数据"""
        data = {}
        base_loss = 40 + (frequency_mhz - 3500) / 1000 * 5  # 频率越高损耗越大

        for probe_id in range(32):
            for pol in ["V", "H"]:
                key = f"{probe_id}_{pol}"
                variation = np.sin(probe_id * 0.2) * 3  # 探头位置差异
                pol_offset = 0.3 if pol == "V" else -0.3
                noise = np.random.normal(0, 0.2)
                data[key] = base_loss + variation + pol_offset + noise

        return data

    def _mock_switch_data(self) -> Dict:
        """生成 mock 开关数据"""
        port_measurements = {}

        for input_port in range(4):
            for output_port in range(32):
                port_key = f"{input_port}-{output_port}"
                base_loss = 1.2
                variation = np.sin(output_port * 0.2) * 0.3
                noise = np.random.normal(0, 0.05)
                port_measurements[port_key] = {
                    "insertion_loss_db": base_loss + variation + noise
                }

        return {"port_measurements": port_measurements}

    def _mock_ul_data(self) -> Dict:
        """生成 mock 上行链路数据"""
        return {
            "lna_gain_db": 20.0 + np.random.normal(0, 0.3),
            "cable_loss_db": 3.0 + np.random.normal(0, 0.1)
        }

    def _mock_dl_data(self) -> Dict:
        """生成 mock 下行链路数据"""
        return {
            "pa_gain_db": 20.0 + np.random.normal(0, 0.3),
            "cable_loss_db": 3.0 + np.random.normal(0, 0.1)
        }

    # ==================== 补偿应用 ====================

    def apply_dl_compensation(
        self,
        matrix: CompensationMatrix,
        probe_id: int,
        polarization: str,
        ce_output_power_dbm: float
    ) -> float:
        """
        应用下行链路补偿

        计算到达 DUT 的功率。

        Args:
            matrix: 补偿矩阵
            probe_id: 探头 ID
            polarization: 极化
            ce_output_power_dbm: 信道仿真器输出功率 (dBm)

        Returns:
            到达 DUT 的功率 (dBm)
        """
        compensation = matrix.get_compensation(probe_id, polarization)
        if not compensation:
            return ce_output_power_dbm

        # P_dut = P_ce + Compensation (补偿已经是负的损耗)
        return ce_output_power_dbm + compensation.total_dl_compensation_db

    def apply_ul_compensation(
        self,
        matrix: CompensationMatrix,
        probe_id: int,
        polarization: str,
        ce_input_power_dbm: float
    ) -> float:
        """
        应用上行链路补偿

        计算 DUT 实际发射功率。

        Args:
            matrix: 补偿矩阵
            probe_id: 探头 ID
            polarization: 极化
            ce_input_power_dbm: 信道仿真器接收功率 (dBm)

        Returns:
            DUT 发射功率 (dBm)
        """
        compensation = matrix.get_compensation(probe_id, polarization)
        if not compensation:
            return ce_input_power_dbm

        # P_dut = P_ce - Compensation
        return ce_input_power_dbm - compensation.total_ul_compensation_db
