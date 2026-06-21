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
from typing import List, Dict, Literal, Optional, Any
from uuid import UUID
from dataclasses import dataclass, field
from enum import Enum

import httpx
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.models.chamber import ChamberConfiguration, ProbeDistribution
from app.models.probe import Probe
from app.models.probe_calibration import (
    ProbePathLossCalibration,
    ChannelPhaseCalibration,
    CalibrationStatus,
)
from app.services.path_loss_calibration_service import (
    select_latest_path_loss_by_mode,
)
from app.services.channel_generation.pas_rotation import (
    align_pas_to_nearest_probe,
    PASRotationResult,
)

logger = logging.getLogger("app.channel_engine")

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
    """天线阵列配置 (跟微服务 schema 镜像)"""
    array_type: str = "ULA"
    num_rows: int = 1
    num_cols: int = 2
    spacing_h: float = 0.5
    spacing_v: float = 0.5
    # 2026-05-18 P0-7: ChannelEgine Phase 6 dual-pol synthesizer 显式要求
    polarization: str = "V"  # "V" 或 "H"


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
    # 2026-06-11 audit batch 2 跟进: 库端 CDLClusterSpec 的另三个角度扩展字段
    # (默认 0, 跟库一致)。as_zoa_deg 同时是新 (az,el) 各向异性探头权重高斯的
    # el 宽度 (spec v2.0 §3) — 3D 仰角簇 (38.901 ZoD / CAICT-FS) 必须能传。
    as_aod_deg: float = 0.0
    as_zoa_deg: float = 0.0
    as_zod_deg: float = 0.0
    # 2026-05-18 P0-7: ChannelEgine Phase 6 cross-pol ratio (dB), TR 38.901 §7.5 默认 7
    xpr_db: float = 7.0
    # 2026-05-18 P0-7: ChannelEgine Phase 5 per-ray init phases [VV, VH, HV, HH], None=随机
    initial_phases_rad: Optional[List[float]] = None


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
    # PAS 旋转 (GCM 合规性)
    pas_rotation: Optional[PASRotationResult] = None


@dataclass
class B2ClusterResult:
    """B-2 native-fit 聚类 + per-tap 参数表结果 (PR-5)。tap_params 仅 B2_parametric 路非空;
    .tap 字节生成需现场 Channel Studio (CE 端点到参数表层)。"""
    success: bool = False
    message: str = ""
    target_path: str = ""           # B2_parametric / B1_baked / GCM_native
    clustering_algo: str = ""
    reason: str = ""
    f_d_max_hz: float = 0.0
    is_escalation: bool = False
    tap_params: List[dict] = field(default_factory=list)
    note: str = ""


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
        clusters: Optional[List[CDLCluster]] = None,
        cdl_model_name: str = "UMa CDL-C NLOS",
        pathloss_db: float = 100.0,
        is_los: bool = False,
        tx_antenna: Optional[AntennaConfig] = None,
        rx_antenna: Optional[AntennaConfig] = None,
        target_tx_power_dbm: float = 0.0,
        target_rsrp_dbm: float = -85.0,
        target_snr_db: float = 20.0,
        ue_velocity_kph: float = 15.0,
        session_id: Optional[str] = None,
        # 2026-05-18 P0-7 / Spec v2.0: ChannelEgine Phase 5/6 透传字段
        synthesis_method: str = "strict_pfs",
        ue_velocity_mps: Optional[List[float]] = None,
        k_factor_db: Optional[float] = None,
        # 2026-05-19 P1-7 / Spec v2.1: dispatch + standard-mode 字段
        input_mode: Literal["standard", "custom"] = "custom",
        scenario_name: Optional[str] = None,
        cluster_model_name: Optional[str] = None,
        force_condition: Optional[Literal["LOS", "NLOS", "auto"]] = "auto",
        bs_position: Optional[List[float]] = None,
        ue_position: Optional[List[float]] = None,
        random_seed: Optional[int] = None,
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

        # ----- Step 2: 从 DB 查询校准数据 (含相位补偿) -----
        calibration_entries = self._query_calibration_entries(
            chamber_id, frequency_hz, chamber
        )

        # ----- Step 2.5: Automatic PAS Rotation (GCM 合规性) -----
        # P1-7: PAS rotation 只在 custom mode (操作员/上游提供簇) 才有意义;
        # standard mode 由 ChannelEgine 内部 38.901 generator 生成簇, 不需要
        # MIMO-First 这边再做旋转。clusters 是 None 时跳过.
        pas_result = None
        if clusters and input_mode == "custom":
            pas_result = self._apply_pas_rotation(
                clusters=clusters, chamber=chamber
            )

        # ----- Step 2.6: P1-10 — 非 ring chamber 时从 DB 读 probe 几何 -----
        probe_positions = self._build_probe_positions(chamber)

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
            pas_rotation=pas_result,
            synthesis_method=synthesis_method,
            ue_velocity_mps=ue_velocity_mps,
            k_factor_db=k_factor_db,
            input_mode=input_mode,
            scenario_name=scenario_name,
            cluster_model_name=cluster_model_name,
            force_condition=force_condition,
            bs_position=bs_position,
            ue_position=ue_position,
            random_seed=random_seed,
            probe_positions=probe_positions,
        )

        if input_mode == "standard":
            logger.info(
                f"Sending to CE (standard 38.901) [{cdl_model_name}]: "
                f"scenario={scenario_name} cluster_model={cluster_model_name} "
                f"force_condition={force_condition} "
                f"{len(calibration_entries)} cal entries"
            )
        else:
            logger.info(
                f"Sending to CE (custom CDL) [{cdl_model_name}]: "
                f"{len(clusters or [])} clusters, "
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
            pas_rotation=pas_result,
        )

    async def cluster_b2_native(
        self,
        rt_rays: List[dict],
        ue_velocity_mps: tuple,
        center_frequency_hz: float,
        test_class: str = "throughput_psd",
        f64_profile: Optional[dict] = None,
    ) -> "B2ClusterResult":
        """B-2 native-fit 聚类: RT 射线 → CE 微服务 geometric_native_fit + §6 路径判决 →
        per-tap 参数表 (POST /api/v1/cluster_b2_native)。

        rt_rays: [{delay_s, power_linear, aoa_deg, aod_deg, zoa_deg?, zod_deg?, phase_rad?}, ...]
        返回 B2ClusterResult; .tap 字节生成需现场 Channel Studio (CE 端点产出到参数表层)。
        ESCALATE / 未知 test_class / 确定性类缺 phase_rad → CE 返回 422 → success=False。
        """
        payload = {
            "rt_rays": rt_rays,
            "ue_velocity_mps": list(ue_velocity_mps),
            "center_frequency_hz": center_frequency_hz,
            "test_class": test_class,
        }
        if f64_profile:
            payload["f64_profile"] = f64_profile
        try:
            async with httpx.AsyncClient(timeout=CE_TIMEOUT_SECONDS) as client:
                response = await client.post(
                    f"{CE_BASE_URL}/api/v1/cluster_b2_native",
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()
        except httpx.ConnectError:
            logger.error(f"Cannot connect to Channel Engine at {CE_BASE_URL}")
            return B2ClusterResult(success=False, message=f"Channel Engine unreachable at {CE_BASE_URL}")
        except httpx.HTTPStatusError as e:
            logger.error(f"CE B-2 cluster error: {e.response.status_code} {e.response.text}")
            return B2ClusterResult(success=False, message=f"CE B-2 error ({e.response.status_code}): {e.response.text}")
        except Exception as e:
            logger.exception(f"CE B-2 cluster call failed: {e}")
            return B2ClusterResult(success=False, message=str(e))

        return B2ClusterResult(
            success=True,
            message=f"{data.get('target_path')} ({len(data.get('tap_params', []))} taps)",
            target_path=data.get("target_path", ""),
            clustering_algo=data.get("clustering_algo", ""),
            reason=data.get("reason", ""),
            f_d_max_hz=data.get("f_d_max_hz", 0.0),
            is_escalation=data.get("is_escalation", False),
            tap_params=data.get("tap_params", []),
            note=data.get("note", ""),
        )

    # ==================== 内部方法 ====================

    def _query_calibration_entries(
        self,
        chamber_id: UUID,
        frequency_hz: float,
        chamber: ChamberConfiguration,
        operating_mode: Optional[str] = None,
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
        # P2-11 Phase 3 (Codex on PR #111): 按请求的 switch operating_mode 过滤 cert
        # (精确优先, 退回 legacy NULL), 否则多 mode 同频校准的 lab 会喂错 RF 通路的
        # per-port cable_loss/probe_gain 给 channel gen。
        latest_cal = select_latest_path_loss_by_mode(
            self.db.query(ProbePathLossCalibration).filter(
                ProbePathLossCalibration.chamber_id == chamber_id,
                ProbePathLossCalibration.status == CalibrationStatus.VALID.value,
            ),
            operating_mode,
        )

        num_ports = chamber.num_probes * (2 if chamber.num_polarizations >= 2 else 1)

        # 计算缺省状态下的等效系统损耗 (用于无校准数据时的回退计算)
        # 等效损耗 = 物理线缆损耗 (Cable Loss) + 双工器插损 (Duplexer) - 功放增益 (PA Gain)
        fallback_loss = chamber.typical_cable_loss_db
        if chamber.has_pa and chamber.pa_gain_db:
            fallback_loss -= chamber.pa_gain_db
        if chamber.has_duplexer and chamber.duplexer_insertion_loss_db:
            fallback_loss += chamber.duplexer_insertion_loss_db


        if latest_cal and latest_cal.probe_path_losses:
            logger.info(
                f"Using calibration data from {latest_cal.calibrated_at} "
                f"for {len(latest_cal.probe_path_losses)} probes"
            )
            for probe_id_str, probe_data in latest_cal.probe_path_losses.items():
                probe_id = int(probe_id_str)
                path_loss = probe_data.get("path_loss_db", fallback_loss)

                # V 极化端口
                entries.append({
                    "port_id": probe_id * 2 + 1,
                    "cable_loss_db": float(path_loss),
                    "cable_phase_deg": 0.0,  # 下面由 phase_compensation_map 覆盖
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
                f"effective_loss={fallback_loss} dB, "
                f"probe_gain={chamber.probe_gain_dbi} dBi"
            )
            for port_id in range(1, num_ports + 1):
                entries.append({
                    "port_id": port_id,
                    "cable_loss_db": float(fallback_loss),
                    "cable_phase_deg": 0.0,
                    "probe_gain_dbi": float(chamber.probe_gain_dbi),
                })

        # ----- 注入相位校准数据 (P1: 打通相位补偿链路) -----
        phase_compensation_map = self._query_phase_compensation(
            chamber_id, frequency_hz
        )
        if phase_compensation_map:
            injected_count = 0
            for entry in entries:
                ch_id = entry["port_id"]
                if ch_id in phase_compensation_map:
                    entry["cable_phase_deg"] = phase_compensation_map[ch_id]
                    injected_count += 1
            logger.info(
                f"Phase calibration injected for {injected_count}/{len(entries)} ports"
            )

        return entries

    def _build_payload(
        self,
        chamber: ChamberConfiguration,
        calibration_entries: List[Dict],
        frequency_hz: float,
        clusters: Optional[List[CDLCluster]],
        cdl_model_name: str,
        pathloss_db: float,
        is_los: bool,
        tx_antenna: AntennaConfig,
        rx_antenna: AntennaConfig,
        target_tx_power_dbm: float,
        target_rsrp_dbm: float,
        target_snr_db: float,
        ue_velocity_kph: float,
        pas_rotation: Optional[PASRotationResult] = None,
        # 2026-05-18 P0-7 / Spec v2.0: Phase 5/6 透传字段
        synthesis_method: str = "strict_pfs",
        ue_velocity_mps: Optional[List[float]] = None,
        k_factor_db: Optional[float] = None,
        # 2026-05-19 P1-7 / Spec v2.1: dispatch + standard 3GPP 字段
        input_mode: Literal["standard", "custom"] = "custom",
        scenario_name: Optional[str] = None,
        cluster_model_name: Optional[str] = None,
        force_condition: Optional[Literal["LOS", "NLOS", "auto"]] = "auto",
        bs_position: Optional[List[float]] = None,
        ue_position: Optional[List[float]] = None,
        random_seed: Optional[int] = None,
        # 2026-05-19 P1-10: 非 ring chamber 几何 (ChannelEgine Phase 8)
        probe_positions: Optional[List[Dict[str, float]]] = None,
    ) -> Dict[str, Any]:
        """组装 Spec v2.1 请求 Payload (Phase 5/6 字段 + P1-7 input_mode 分路)。

        custom mode: cdl_model_data.clusters 含操作员/上游提供的簇列表。
        standard mode: cdl_model_data.clusters = None, 顶层加 standard_3gpp 子模型
        (scenario_name + cluster_model_name + force_condition + bs/ue positions
        + random_seed). 微服务按 input_mode 分路到 ChannelEgine
        `CustomCDLBuilder` 或 `Standard3GPPBuilder`.
        """
        chamber_config_payload: Dict[str, Any] = {
            "num_probes": chamber.num_probes,
            "radius_m": float(chamber.chamber_radius_m),
            "dual_polarized": chamber.num_polarizations >= 2,
            # P1-10: 跟 ChannelEgine Phase 8 wire format 一致 (ring/multi-ring/custom).
            # `chamber.probe_distribution` 默认 "ring", 历史行回填同值 → 向后兼容.
            "distribution": chamber.probe_distribution,
        }
        if probe_positions is not None:
            chamber_config_payload["probe_positions"] = probe_positions

        payload: Dict[str, Any] = {
            "chamber_config": chamber_config_payload,
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
                    "polarization": tx_antenna.polarization,
                },
                "rx_antenna": {
                    "array_type": rx_antenna.array_type,
                    "num_rows": rx_antenna.num_rows,
                    "num_cols": rx_antenna.num_cols,
                    "spacing_h": rx_antenna.spacing_h,
                    "spacing_v": rx_antenna.spacing_v,
                    "polarization": rx_antenna.polarization,
                },
                "ue_velocity_kph": ue_velocity_kph,
                "ue_velocity_mps": ue_velocity_mps,
                "synthesis_method": synthesis_method,
            },
            "cdl_model_data": {
                "model_name": cdl_model_name,
                "pathloss_db": pathloss_db,
                "is_los": is_los,
                "k_factor_db": k_factor_db,
                "clusters": (
                    [
                        {
                            "delay_s": c.delay_s,
                            "power_relative_linear": c.power_relative_linear,
                            "aoa_deg": c.aoa_deg,
                            "aod_deg": c.aod_deg,
                            "zoa_deg": c.zoa_deg,
                            "zod_deg": c.zod_deg,
                            "as_aoa_deg": c.as_aoa_deg,
                            "as_aod_deg": c.as_aod_deg,
                            "as_zoa_deg": c.as_zoa_deg,
                            "as_zod_deg": c.as_zod_deg,
                            "xpr_db": c.xpr_db,
                            "initial_phases_rad": c.initial_phases_rad,
                        }
                        for c in clusters
                    ]
                    if clusters
                    else None
                ),
            },
            "input_mode": input_mode,
        }

        if input_mode == "standard":
            payload["standard_3gpp"] = {
                "scenario_name": scenario_name,
                "cluster_model_name": cluster_model_name,
                "force_condition": force_condition,
                # bs/ue positions: 给默认值 (3GPP TR 38.901 §7.2 典型几何),
                # 操作员可以覆盖
                "bs_position": bs_position or [0.0, 0.0, 25.0],
                "ue_position": ue_position or [50.0, 0.0, 1.5],
                "random_seed": random_seed,
            }

        # 附加 PAS 旋转元数据供 CE 和上层使用
        if pas_rotation and pas_rotation.applied:
            payload["pas_rotation"] = pas_rotation.to_dict()

        return payload

    def _build_probe_positions(
        self,
        chamber: ChamberConfiguration,
    ) -> Optional[List[Dict[str, float]]]:
        """P1-10 (2026-05-19): 非 ring chamber 从 DB Probe 表读 per-probe
        az/el, 编成 ChannelEgine Phase 8 ``probe_positions`` list.

        Ring 路径 (默认): 返回 None, ChannelEgine 走 ``(p × 360°/N)`` 等距公式,
        跟当前 lab 8-probe ring smoke 行为完全一致 (backward compat).

        非 ring 路径 (multi-ring / custom): 查 DB Probe 表, 按 ``probe_number``
        排序, 按 ``(az, el)`` dedupe (dual-polarized chamber 每个物理 probe 有
        V + H 两行共享 position), 返回 ``num_probes`` 个 dict。fail-loud 三个
        前提条件:
        - 至少有 active probe (无则 chamber 配置半成品, raise);
        - 每个 probe 都有 ``position.azimuth`` (无则 schema 漂移, raise);
        - 物理 probe 个数 == ``chamber.num_probes`` (不对则 DB 跟 chamber
          spec 漂移, raise — 跟 ChannelEgine Phase 8 validator 同语义)。
        """
        if chamber.probe_distribution == ProbeDistribution.RING.value:
            return None

        probes = self.db.query(Probe).filter(
            Probe.chamber_config_id == chamber.id,
            Probe.is_active == True,  # noqa: E712
        ).order_by(Probe.probe_number).all()

        if not probes:
            raise ValueError(
                f"chamber.probe_distribution={chamber.probe_distribution!r} "
                f"requires probe_positions, but no active probes found for "
                f"chamber {chamber.id}"
            )

        seen_positions: set = set()
        positions: List[Dict[str, float]] = []
        for probe in probes:
            pos = probe.position or {}
            az = pos.get("azimuth") if isinstance(pos, dict) else None
            el = pos.get("elevation", 0.0) if isinstance(pos, dict) else 0.0
            if az is None:
                raise ValueError(
                    f"probe {probe.probe_number} (chamber {chamber.id}) has "
                    f"no azimuth in position field; cannot build probe_positions "
                    f"for distribution={chamber.probe_distribution!r}"
                )
            key = (round(float(az), 4), round(float(el or 0.0), 4))
            if key in seen_positions:
                continue
            seen_positions.add(key)
            positions.append({
                "azimuth_deg": float(az),
                "elevation_deg": float(el or 0.0),
            })

        if len(positions) != chamber.num_probes:
            raise ValueError(
                f"chamber.probe_distribution={chamber.probe_distribution!r} "
                f"expects len(probe_positions) == num_probes "
                f"({chamber.num_probes}), but DB has {len(positions)} unique "
                f"physical probe positions for chamber {chamber.id}; "
                f"check Probe seeding or num_probes consistency"
            )

        logger.info(
            f"Built {len(positions)} probe positions for chamber {chamber.id} "
            f"(distribution={chamber.probe_distribution!r})"
        )
        return positions

    def _apply_pas_rotation(
        self,
        clusters: List[CDLCluster],
        chamber: ChamberConfiguration,
    ) -> Optional[PASRotationResult]:
        """
        执行 Automatic PAS Rotation。

        从 DB 查询暗室的探头方位角，找到最强簇，旋转所有簇的 AoA 使最强簇
        精确对准最近的物理探头。对应 GCM 中的 "Automatic PAS Rotation" 功能。

        ★ 此方法会就地修改 clusters 列表中各 CDLCluster 的 aoa_deg 字段。
        """
        if not clusters:
            return None

        # 从 DB 查询水平环探头的方位角
        from app.models.probe import Probe
        probes = self.db.query(Probe).filter(
            Probe.is_active == True  # noqa: E712
        ).all()

        if not probes:
            logger.warning(
                "[PAS Rotation] 数据库中无探头数据, 跳过 PAS Rotation"
            )
            return None

        # 提取方位角 (仅水平环探头, ring=3 对应 ±30° 仰角内)
        probe_azimuths = []
        probe_ids = []
        for p in probes:
            if hasattr(p, 'position') and p.position:
                pos = p.position
                az = pos.get('azimuth', None) if isinstance(pos, dict) else getattr(pos, 'azimuth', None)
                if az is not None:
                    probe_azimuths.append(float(az))
                    probe_ids.append(p.probe_number)

        if not probe_azimuths:
            logger.warning(
                "[PAS Rotation] 无法从探头数据中提取方位角, 跳过"
            )
            return None

        # 提取簇参数
        aoa_list = [c.aoa_deg for c in clusters]
        power_list = [c.power_relative_linear for c in clusters]

        # 执行旋转
        rotated_aoas, result = align_pas_to_nearest_probe(
            cluster_aoa_degs=aoa_list,
            cluster_powers_linear=power_list,
            probe_azimuths_deg=probe_azimuths,
            probe_ids=probe_ids,
        )

        # 就地更新 clusters 的 AoA
        if result.applied:
            for i, cluster in enumerate(clusters):
                cluster.aoa_deg = rotated_aoas[i]

        return result

    def _query_phase_compensation(
        self,
        chamber_id: UUID,
        frequency_hz: float,
    ) -> Dict[int, float]:
        """
        从 DB 查询最新的相位校准补偿值。

        P1: 打通 phase_calibration_service → channel_engine_client 的数据链路。

        Returns:
            {channel_id: compensation_phase_deg} 字典，空字典表示无校准数据。
        """
        try:
            latest_phase_cal = self.db.query(ChannelPhaseCalibration).filter(
                ChannelPhaseCalibration.chamber_id == chamber_id,
                ChannelPhaseCalibration.status == "valid",
            ).order_by(
                desc(ChannelPhaseCalibration.calibrated_at)
            ).first()

            if not latest_phase_cal or not latest_phase_cal.phase_compensation:
                return {}

            phase_map: Dict[int, float] = {}
            for comp in latest_phase_cal.phase_compensation:
                ch_id = comp.get("channel_id")
                comp_deg = comp.get("compensation_deg", 0.0)
                if ch_id is not None:
                    phase_map[int(ch_id)] = float(comp_deg)

            logger.info(
                f"Phase compensation loaded: {len(phase_map)} channels "
                f"from calibration {latest_phase_cal.id}"
            )
            return phase_map

        except Exception as e:
            logger.warning(f"Failed to query phase compensation: {e}")
            return {}

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
