"""
Channel Engine HTTP Client

MIMO-First 侧的 Channel Engine 客户端服务。
负责：
1. 从 PostgreSQL 查询暗室配置和校准数据
2. 组装 Spec v1.0 Payload（使用统一的 CDL 模型命名）
3. 调用 CE 的 synthesize_hardware_pipeline 端点
4. 解压 .asc ZIP 文件到本地
5. 返回控制指令供 HAL 层使用

CDL 模型命名规范
================
- 3GPP 标准模型: ``{Scenario} {CDL_Model} {LOS/NLOS}``  例: "UMa CDL-C NLOS"
- Ray-Tracing 数据: ``{ScenarioName} CDL Snapshot-{N}``  例: "Highway_Beijing CDL Snapshot-42"

校准数据默认值
==============
当数据库中没有校准数据时，回退使用暗室配置的默认值：
- cable_loss_db:  ChamberConfiguration.typical_cable_loss_db (默认 5.0 dB)
- cable_phase_deg: 0.0° (相位校准表尚未接入)
- probe_gain_dbi:  ChamberConfiguration.probe_gain_dbi (默认 8.0 dBi)
"""

import os
import io
import base64
import zipfile
import logging
from typing import List, Dict, Optional, Any
from uuid import UUID
from dataclasses import dataclass, field
from enum import Enum

import httpx
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.models.chamber import ChamberConfiguration
from app.models.probe_calibration import (
    ProbePathLossCalibration,
    CalibrationStatus,
)

logger = logging.getLogger(__name__)

# Channel Engine 服务地址
CE_BASE_URL = os.environ.get("CHANNEL_ENGINE_URL", "http://localhost:8001")
CE_TIMEOUT_SECONDS = 60.0

# 硬件产物存储根目录
HARDWARE_ARTIFACTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "hardware_artifacts"
)


# ==================== CDL 模型命名工具 ====================

class CDLModelSource(str, Enum):
    """CDL 模型数据来源"""
    STANDARD_3GPP = "3GPP"
    RAY_TRACING = "RayTracing"


def build_cdl_model_name(
    source: CDLModelSource,
    scenario: str = "UMa",
    cdl_model: str = "CDL-C",
    is_los: bool = False,
    scene_name: Optional[str] = None,
    snapshot_id: Optional[int] = None,
) -> str:
    """
    构造标准化的 CDL 模型名称。

    Args:
        source: 数据来源 (3GPP 标准 / Ray-Tracing)
        scenario: 3GPP 场景类型 (UMa, UMi, RMa, InH)
        cdl_model: CDL 模型标识 (CDL-A ~ CDL-E)
        is_los: 是否为视距条件
        scene_name: Ray-Tracing 场景名称
        snapshot_id: Ray-Tracing 快照编号

    Returns:
        格式化的 CDL 模型名称

    Examples:
        >>> build_cdl_model_name(CDLModelSource.STANDARD_3GPP, "UMa", "CDL-C", False)
        "UMa CDL-C NLOS"
        >>> build_cdl_model_name(CDLModelSource.RAY_TRACING, scene_name="Highway_Beijing", snapshot_id=42)
        "Highway_Beijing CDL Snapshot-42"
    """
    if source == CDLModelSource.STANDARD_3GPP:
        condition = "LOS" if is_los else "NLOS"
        return f"{scenario} {cdl_model} {condition}"
    elif source == CDLModelSource.RAY_TRACING:
        name = scene_name or "Unknown"
        sid = snapshot_id if snapshot_id is not None else 0
        return f"{name} CDL Snapshot-{sid}"
    else:
        return f"Custom CDL Model"


# ==================== 数据类 ====================

@dataclass
class AntennaConfig:
    """天线阵列配置"""
    array_type: str = "ULA"
    num_rows: int = 1
    num_cols: int = 2
    spacing_h: float = 0.5
    spacing_v: float = 0.5


@dataclass
class CDLCluster:
    """
    CDL 模型簇参数

    表示一个多径簇的物理特征。
    可来自 3GPP 标准参数表或 Ray-Tracing 仿真输出。
    """
    delay_s: float = 0.0
    power_relative_linear: float = 1.0
    aoa_deg: float = 0.0
    aod_deg: float = 0.0
    zoa_deg: float = 90.0
    zod_deg: float = 90.0
    as_aoa_deg: float = 2.0


@dataclass
class HardwarePipelineResult:
    """硬件流水线结果"""
    success: bool = False
    message: str = ""
    cdl_model_name: str = ""
    # 文件路径
    asc_files_path: Optional[str] = None
    total_files: int = 0
    # 控制指令
    f64_baseband_power_dbm: float = 0.0
    external_attenuators_db: List[float] = field(default_factory=list)
    target_achieved_rsrp_dbm: float = -85.0
    # 诊断
    spatial_correlation: Optional[float] = None
    matrix_energy_scaling_factor: Optional[float] = None
    computation_time_ms: float = 0.0


# ==================== 客户端 ====================

class ChannelEngineClient:
    """
    Channel Engine HTTP 客户端

    作为 MIMO-First 编排层调用 CE 微服务的唯一入口。
    """

    def __init__(self, db: Session):
        self.db = db

    async def synthesize_hardware_pipeline(
        self,
        chamber_id: UUID,
        frequency_hz: float,
        clusters: List[CDLCluster],
        cdl_model_name: str,
        pathloss_db: float = 100.0,
        is_los: bool = False,
        tx_antenna: Optional[AntennaConfig] = None,
        rx_antenna: Optional[AntennaConfig] = None,
        target_tx_power_dbm: float = 0.0,
        target_rsrp_dbm: float = -85.0,
        target_snr_db: float = 20.0,
        ue_velocity_kph: float = 15.0,
        session_id: Optional[str] = None,
    ) -> HardwarePipelineResult:
        """
        调用 Channel Engine 硬件流水线合成 API。

        完整流程：
        1. 从 DB 查询 chamber_config + calibration_data
        2. 组装 Spec v1.0 Payload（含 CDL 模型命名）
        3. POST 到 CE
        4. 解压 .asc ZIP → 本地存储
        5. 返回 control_instructions + diagnostics

        Args:
            chamber_id: 暗室配置 ID
            frequency_hz: 中心频率 (Hz)
            clusters: CDL 模型簇参数列表
            cdl_model_name: CDL 模型名称（遵循命名规范）
            pathloss_db: 路径损耗 (dB)
            is_los: 是否视距
            tx_antenna: 发射天线配置
            rx_antenna: 接收天线配置
            target_tx_power_dbm: 目标发射功率 (dBm)
            target_rsrp_dbm: 目标 RSRP (dBm)
            target_snr_db: 目标 SNR (dB)
            ue_velocity_kph: UE 速度 (km/h)
            session_id: 会话 ID（用于文件存储路径）

        Returns:
            HardwarePipelineResult
        """
        if tx_antenna is None:
            tx_antenna = AntennaConfig()
        if rx_antenna is None:
            rx_antenna = AntennaConfig()

        # ----- Step 1: 从 DB 查询暗室配置 -----
        chamber = self.db.query(ChamberConfiguration).filter(
            ChamberConfiguration.id == chamber_id
        ).first()

        if not chamber:
            return HardwarePipelineResult(
                success=False,
                message=f"Chamber configuration {chamber_id} not found"
            )

        # ----- Step 2: 从 DB 查询校准数据 -----
        calibration_entries = self._query_calibration_entries(
            chamber_id, frequency_hz, chamber
        )

        # ----- Step 3: 组装 Payload -----
        payload = self._build_payload(
            chamber=chamber,
            calibration_entries=calibration_entries,
            frequency_hz=frequency_hz,
            clusters=clusters,
            cdl_model_name=cdl_model_name,
            pathloss_db=pathloss_db,
            is_los=is_los,
            tx_antenna=tx_antenna,
            rx_antenna=rx_antenna,
            target_tx_power_dbm=target_tx_power_dbm,
            target_rsrp_dbm=target_rsrp_dbm,
            target_snr_db=target_snr_db,
            ue_velocity_kph=ue_velocity_kph,
        )

        logger.info(
            f"Sending to CE [{cdl_model_name}]: "
            f"{len(clusters)} clusters, "
            f"{len(calibration_entries)} cal entries"
        )

        # ----- Step 4: 调用 CE -----
        try:
            async with httpx.AsyncClient(timeout=CE_TIMEOUT_SECONDS) as client:
                response = await client.post(
                    f"{CE_BASE_URL}/api/v1/synthesize_hardware_pipeline",
                    json=payload,
                )
                response.raise_for_status()
                result_data = response.json()

        except httpx.ConnectError:
            logger.error(f"Cannot connect to Channel Engine at {CE_BASE_URL}")
            return HardwarePipelineResult(
                success=False,
                message=f"Channel Engine service unreachable at {CE_BASE_URL}"
            )
        except httpx.HTTPStatusError as e:
            logger.error(f"CE returned error: {e.response.status_code}")
            return HardwarePipelineResult(
                success=False,
                message=f"Channel Engine error: {e.response.text}"
            )
        except Exception as e:
            logger.exception(f"CE call failed: {e}")
            return HardwarePipelineResult(
                success=False,
                message=f"Channel Engine call failed: {str(e)}"
            )

        # ----- Step 5: 检查响应状态 -----
        if result_data.get("status") != "success":
            return HardwarePipelineResult(
                success=False,
                message=result_data.get("error_message", "Unknown CE error"),
                computation_time_ms=result_data.get("computation_time_ms", 0),
            )

        # ----- Step 6: 解压 .asc ZIP 到本地 -----
        artifacts = result_data.get("hardware_artifacts", {})
        zip_b64 = artifacts.get("f64_asc_files_zip_base64", "")
        total_files = artifacts.get("total_files_generated", 0)
        resp_cdl_name = artifacts.get("cdl_model_name", cdl_model_name)

        asc_path = None
        if zip_b64:
            asc_path = self._extract_asc_zip(
                zip_b64, session_id or str(chamber_id)
            )

        # ----- Step 7: 提取控制指令 -----
        control = result_data.get("control_instructions", {})
        diag = result_data.get("diagnostics", {})

        return HardwarePipelineResult(
            success=True,
            message=f"Generated {total_files} .asc files for [{resp_cdl_name}]",
            cdl_model_name=resp_cdl_name,
            asc_files_path=asc_path,
            total_files=total_files,
            f64_baseband_power_dbm=control.get("f64_baseband_power_dbm", 0.0),
            external_attenuators_db=control.get("external_attenuators_db", []),
            target_achieved_rsrp_dbm=control.get("target_achieved_rsrp_dbm", -85.0),
            spatial_correlation=diag.get("spatial_correlation"),
            matrix_energy_scaling_factor=diag.get("matrix_energy_scaling_factor"),
            computation_time_ms=result_data.get("computation_time_ms", 0),
        )

    # ==================== 内部方法 ====================

    def _query_calibration_entries(
        self,
        chamber_id: UUID,
        frequency_hz: float,
        chamber: ChamberConfiguration,
    ) -> List[Dict[str, Any]]:
        """
        从 PostgreSQL 查询校准数据，构造 calibration_data.entries[]。

        校准数据回退策略：
        1. 首选：最新有效的探头路损校准记录（ProbePathLossCalibration, status=VALID）
        2. 回退：暗室配置中的默认值：
           - cable_loss_db  = ChamberConfiguration.typical_cable_loss_db
             (DB 列默认=5.0 dB; 预置 Small/Medium=3.0 dB, Large/Custom=5.0 dB)
           - cable_phase_deg = 0.0° (相位校准表尚未接入)
           - probe_gain_dbi  = ChamberConfiguration.probe_gain_dbi
             (DB 列默认=8.0 dBi; 预置 Small/Medium=6.0 dBi, Large/Custom=8.0 dBi)
        """
        entries = []
        frequency_mhz = frequency_hz / 1e6

        # 查询最新的路损校准
        latest_cal = self.db.query(ProbePathLossCalibration).filter(
            ProbePathLossCalibration.chamber_id == chamber_id,
            ProbePathLossCalibration.status == CalibrationStatus.VALID.value,
        ).order_by(
            desc(ProbePathLossCalibration.calibrated_at)
        ).first()

        num_ports = chamber.num_probes * (2 if chamber.num_polarizations >= 2 else 1)

        if latest_cal and latest_cal.probe_path_losses:
            logger.info(
                f"Using calibration data from {latest_cal.calibrated_at} "
                f"for {len(latest_cal.probe_path_losses)} probes"
            )
            for probe_id_str, probe_data in latest_cal.probe_path_losses.items():
                probe_id = int(probe_id_str)
                path_loss = probe_data.get("path_loss_db", chamber.typical_cable_loss_db)

                # V 极化端口
                entries.append({
                    "port_id": probe_id * 2 + 1,
                    "cable_loss_db": float(path_loss),
                    "cable_phase_deg": 0.0,  # TODO: 从相位校准表补充
                    "probe_gain_dbi": float(chamber.probe_gain_dbi),
                })

                # H 极化端口（如果双极化）
                if chamber.num_polarizations >= 2:
                    h_loss = probe_data.get("pol_h_db", path_loss)
                    entries.append({
                        "port_id": probe_id * 2 + 2,
                        "cable_loss_db": float(h_loss) if h_loss else float(path_loss),
                        "cable_phase_deg": 0.0,
                        "probe_gain_dbi": float(chamber.probe_gain_dbi),
                    })
        else:
            # 使用暗室配置的默认值
            logger.warning(
                f"No calibration data found for chamber {chamber_id}, "
                f"using chamber defaults: "
                f"cable_loss={chamber.typical_cable_loss_db} dB, "
                f"probe_gain={chamber.probe_gain_dbi} dBi"
            )
            for port_id in range(1, num_ports + 1):
                entries.append({
                    "port_id": port_id,
                    "cable_loss_db": float(chamber.typical_cable_loss_db),
                    "cable_phase_deg": 0.0,
                    "probe_gain_dbi": float(chamber.probe_gain_dbi),
                })

        return entries

    def _build_payload(
        self,
        chamber: ChamberConfiguration,
        calibration_entries: List[Dict],
        frequency_hz: float,
        clusters: List[CDLCluster],
        cdl_model_name: str,
        pathloss_db: float,
        is_los: bool,
        tx_antenna: AntennaConfig,
        rx_antenna: AntennaConfig,
        target_tx_power_dbm: float,
        target_rsrp_dbm: float,
        target_snr_db: float,
        ue_velocity_kph: float,
    ) -> Dict[str, Any]:
        """组装 Spec v1.0 请求 Payload"""
        return {
            "chamber_config": {
                "num_probes": chamber.num_probes,
                "radius_m": float(chamber.chamber_radius_m),
                "dual_polarized": chamber.num_polarizations >= 2,
                "distribution": "ring",
            },
            "calibration_data": {
                "entries": calibration_entries,
            },
            "simulation_rules": {
                "center_frequency_hz": frequency_hz,
                "target_tx_power_dbm": target_tx_power_dbm,
                "target_rsrp_dbm": target_rsrp_dbm,
                "target_snr_db": target_snr_db,
                "tx_antenna": {
                    "array_type": tx_antenna.array_type,
                    "num_rows": tx_antenna.num_rows,
                    "num_cols": tx_antenna.num_cols,
                    "spacing_h": tx_antenna.spacing_h,
                    "spacing_v": tx_antenna.spacing_v,
                },
                "rx_antenna": {
                    "array_type": rx_antenna.array_type,
                    "num_rows": rx_antenna.num_rows,
                    "num_cols": rx_antenna.num_cols,
                    "spacing_h": rx_antenna.spacing_h,
                    "spacing_v": rx_antenna.spacing_v,
                },
                "ue_velocity_kph": ue_velocity_kph,
            },
            "cdl_model_data": {
                "model_name": cdl_model_name,
                "pathloss_db": pathloss_db,
                "is_los": is_los,
                "clusters": [
                    {
                        "delay_s": c.delay_s,
                        "power_relative_linear": c.power_relative_linear,
                        "aoa_deg": c.aoa_deg,
                        "aod_deg": c.aod_deg,
                        "zoa_deg": c.zoa_deg,
                        "zod_deg": c.zod_deg,
                        "as_aoa_deg": c.as_aoa_deg,
                    }
                    for c in clusters
                ],
            },
        }

    def _extract_asc_zip(
        self, zip_b64: str, session_id: str
    ) -> Optional[str]:
        """
        解压 Base64 编码的 ZIP 文件到本地目录。

        Returns:
            解压目录的绝对路径，或 None
        """
        try:
            zip_bytes = base64.b64decode(zip_b64)
            target_dir = os.path.join(HARDWARE_ARTIFACTS_DIR, session_id)
            os.makedirs(target_dir, exist_ok=True)

            with zipfile.ZipFile(io.BytesIO(zip_bytes), 'r') as zf:
                zf.extractall(target_dir)

            file_count = len([
                f for f in os.listdir(target_dir) if f.endswith('.asc')
            ])
            logger.info(
                f"Extracted {file_count} .asc files to {target_dir}"
            )
            return target_dir

        except Exception as e:
            logger.exception(f"Failed to extract .asc ZIP: {e}")
            return None
