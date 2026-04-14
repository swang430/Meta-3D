"""
Hardware Pipeline Synthesis Endpoint

POST /api/v1/synthesize_hardware_pipeline

基于 MIMO_First_Integration_Spec.md v1.0 实现。
接收 MIMO-First 下发的完整仿真参数，返回 .asc 硬件驱动文件和控制指令。
"""

import time
import io
import os
import sys
import zipfile
import base64
import logging
import numpy as np
from typing import Dict, List, Any

from fastapi import APIRouter, HTTPException
from app.models.hardware_pipeline_models import (
    HardwarePipelineRequest,
    HardwarePipelineResponse,
    HardwareArtifacts,
    ControlInstructions,
    Diagnostics,
)

logger = logging.getLogger(__name__)

router = APIRouter()

# Channel Engine 算法库路径
CHANNEL_ENGINE_PATH = os.environ.get(
    'CHANNEL_ENGINE_PATH',
    os.path.expanduser('~/ChannelEgine')
)


def _get_simulator():
    """按需导入 Channel Engine 核心库"""
    if CHANNEL_ENGINE_PATH not in sys.path:
        sys.path.insert(0, CHANNEL_ENGINE_PATH)
    try:
        from mimo_ota_simulator.simulator import OTASimulator
        return OTASimulator
    except ImportError:
        logger.warning("OTASimulator not available, using mock mode")
        return None


@router.post(
    "/synthesize_hardware_pipeline",
    response_model=HardwarePipelineResponse,
    summary="合成硬件流水线",
    description="接收暗室配置、校准数据、仿真规则和 CDL 模型数据，"
                "生成 .asc 硬件驱动文件和控制指令。"
)
async def synthesize_hardware_pipeline(
    request: HardwarePipelineRequest,
) -> HardwarePipelineResponse:
    """
    核心合成端点

    处理流程：
    1. 解析请求参数
    2. 调用 Channel Engine 算法库生成 A_Matrix
    3. 导出 .asc 文件并 ZIP 打包
    4. 计算硬件控制指令（基带功率 + 衰减器）
    5. 返回 Base64 编码的 ZIP 和控制指令
    """
    start_time = time.time()

    try:
        # 提取核心参数
        chamber = request.chamber_config
        sim_rules = request.simulation_rules
        cdl_data = request.cdl_model_data
        cal_data = request.calibration_data

        num_tx = sim_rules.tx_antenna.num_rows * sim_rules.tx_antenna.num_cols
        num_ports = chamber.num_probes * (2 if chamber.dual_polarized else 1)
        total_files = num_tx * num_ports

        logger.info(
            f"Hardware pipeline [{cdl_data.model_name}]: "
            f"{chamber.num_probes} probes, "
            f"{len(cdl_data.clusters)} clusters, "
            f"freq={sim_rules.center_frequency_hz/1e9:.2f} GHz"
        )

        # -----------------------------------------------------------
        # 尝试调用真实算法库
        # -----------------------------------------------------------
        OTASimulatorClass = _get_simulator()
        asc_content_map: Dict[str, bytes] = {}

        if OTASimulatorClass is not None:
            asc_content_map = _run_real_synthesis(
                OTASimulatorClass, request
            )
        else:
            # Mock 模式：生成合理的占位 .asc 文件
            asc_content_map = _run_mock_synthesis(
                num_tx=num_tx,
                num_ports=num_ports,
                clusters=cdl_data.clusters,
                frequency_hz=sim_rules.center_frequency_hz,
                velocity_kph=sim_rules.ue_velocity_kph,
            )

        # -----------------------------------------------------------
        # ZIP 打包并 Base64 编码
        # -----------------------------------------------------------
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
            for filename, content in asc_content_map.items():
                zf.writestr(filename, content)

        zip_base64 = base64.b64encode(zip_buffer.getvalue()).decode('ascii')

        # -----------------------------------------------------------
        # 计算硬件控制指令
        # -----------------------------------------------------------
        control = _compute_control_instructions(
            sim_rules=sim_rules,
            cdl_data=cdl_data,
            cal_entries=cal_data.entries,
            num_probes=chamber.num_probes,
        )

        # -----------------------------------------------------------
        # 诊断信息
        # -----------------------------------------------------------
        diagnostics = Diagnostics(
            spatial_correlation=_estimate_spatial_correlation(cdl_data.clusters),
            matrix_energy_scaling_factor=float(np.sqrt(num_tx)),
        )

        elapsed_ms = (time.time() - start_time) * 1000

        logger.info(
            f"Hardware pipeline complete: {len(asc_content_map)} files, "
            f"{elapsed_ms:.0f}ms"
        )

        return HardwarePipelineResponse(
            status="success",
            computation_time_ms=round(elapsed_ms, 1),
            hardware_artifacts=HardwareArtifacts(
                f64_asc_files_zip_base64=zip_base64,
                total_files_generated=len(asc_content_map),
                cdl_model_name=cdl_data.model_name,
            ),
            control_instructions=control,
            diagnostics=diagnostics,
        )

    except Exception as e:
        elapsed_ms = (time.time() - start_time) * 1000
        logger.exception(f"Hardware pipeline failed: {e}")
        return HardwarePipelineResponse(
            status="error",
            computation_time_ms=round(elapsed_ms, 1),
            error_message=str(e),
        )


# ==================== 真实合成 ====================

def _run_real_synthesis(
    OTASimulatorClass,
    request: HardwarePipelineRequest,
) -> Dict[str, bytes]:
    """
    调用 Channel Engine 核心算法库进行真实合成。

    将 Spec v1.0 的 Payload 转换为 OTASimulator 的输入格式，
    运行仿真并导出 .asc 文件。
    """
    original_cwd = os.getcwd()
    try:
        os.chdir(CHANNEL_ENGINE_PATH)

        # 构造簇参数（从 cdl_model_data 转化）
        cdl_data = request.cdl_model_data
        cluster_params = []
        for c in cdl_data.clusters:
            cluster_params.append({
                "delay_s": c.delay_s,
                "power_linear": c.power_relative_linear,
                "aoa_phi": c.aoa_deg,
                "aod_phi": c.aod_deg,
                "zoa_theta": c.zoa_deg,
                "zod_theta": c.zod_deg,
                "as_aoa": c.as_aoa_deg,
            })

        # 构造校准查找表
        cal_lookup = {}
        for entry in request.calibration_data.entries:
            cal_lookup[entry.port_id] = {
                "cable_loss_db": entry.cable_loss_db,
                "cable_phase_deg": entry.cable_phase_deg,
                "probe_gain_dbi": entry.probe_gain_dbi,
            }

        sim = OTASimulatorClass(
            center_frequency_hz=request.simulation_rules.center_frequency_hz,
            num_probes=request.chamber_config.num_probes,
            chamber_radius_m=request.chamber_config.radius_m,
            dual_polarized=request.chamber_config.dual_polarized,
            tx_array_config={
                "type": request.simulation_rules.tx_antenna.array_type,
                "rows": request.simulation_rules.tx_antenna.num_rows,
                "cols": request.simulation_rules.tx_antenna.num_cols,
                "spacing_h": request.simulation_rules.tx_antenna.spacing_h,
            },
            ue_velocity_kph=request.simulation_rules.ue_velocity_kph,
            calibration_data=cal_lookup,
        )

        # 注入外部簇参数并运行
        results = sim.run_with_external_clusters(
            clusters=cluster_params,
            pathloss_db=cdl_data.pathloss_db,
            is_los=cdl_data.is_los,
        )

        # 收集导出的 .asc 文件
        asc_files = {}
        export_dir = results.get("export_dir", ".")
        for fname in os.listdir(export_dir):
            if fname.endswith(".asc"):
                fpath = os.path.join(export_dir, fname)
                with open(fpath, 'rb') as f:
                    asc_files[fname] = f.read()

        return asc_files

    finally:
        os.chdir(original_cwd)


# ==================== Mock 合成 ====================

def _run_mock_synthesis(
    num_tx: int,
    num_ports: int,
    clusters,
    frequency_hz: float,
    velocity_kph: float,
) -> Dict[str, bytes]:
    """
    Mock 模式：生成合理的占位 .asc 文件。

    每个文件包含一条带有多普勒偏移的 TDL 抽头序列，
    格式兼容 Keysight Propsim F64。
    """
    speed_of_light = 3e8
    max_doppler_hz = (velocity_kph / 3.6) * frequency_hz / speed_of_light

    asc_files = {}
    num_taps = len(clusters)
    duration_s = 1.0
    sample_rate_hz = 1000.0
    num_samples = int(duration_s * sample_rate_hz)

    for tx_idx in range(num_tx):
        for port_idx in range(num_ports):
            filename = f"channel_In{tx_idx + 1}_Out{port_idx + 1}.asc"

            lines = []
            lines.append(f"% Channel Engine Mock ASC - Spec v1.0")
            lines.append(f"% Tx={tx_idx + 1}, Port={port_idx + 1}")
            lines.append(f"% Frequency: {frequency_hz/1e9:.3f} GHz")
            lines.append(f"% Max Doppler: {max_doppler_hz:.1f} Hz")
            lines.append(f"% Taps: {num_taps}")
            lines.append(f"% Sample Rate: {sample_rate_hz} Hz")
            lines.append(f"% Duration: {duration_s} s")
            lines.append(f"% Samples: {num_samples}")
            lines.append(f"")

            # 每个抽头生成时变幅度（含多普勒拍频效应）
            for tap_idx, cluster in enumerate(clusters):
                delay_us = cluster.delay_s * 1e6
                power_db = 10 * np.log10(
                    max(cluster.power_relative_linear, 1e-12)
                )

                # 基于 AoA 计算该端口上的匹配权重
                probe_angle = (port_idx / num_ports) * 360.0
                angle_diff = abs(cluster.aoa_deg - probe_angle)
                if angle_diff > 180:
                    angle_diff = 360 - angle_diff
                weight = float(np.exp(-(angle_diff / 30.0) ** 2))

                # 多普勒频移
                doppler_hz = max_doppler_hz * np.cos(
                    np.radians(cluster.aoa_deg - probe_angle)
                )

                lines.append(
                    f"TAP {tap_idx + 1}  "
                    f"DELAY={delay_us:.4f}us  "
                    f"POWER={power_db:.2f}dB  "
                    f"DOPPLER={doppler_hz:.2f}Hz  "
                    f"WEIGHT={weight:.6f}"
                )

                # 时变系数（简化的瑞利衰落包络）
                t = np.linspace(0, duration_s, num_samples)
                # 20 条子射线叠加生成拍频
                envelope = np.zeros(num_samples)
                for sub_ray in range(20):
                    sub_doppler = doppler_hz + np.random.uniform(-2, 2)
                    sub_phase = np.random.uniform(0, 2 * np.pi)
                    envelope += np.cos(
                        2 * np.pi * sub_doppler * t + sub_phase
                    )
                envelope = envelope / 20.0 * weight

                # 写入时变数据（每行一个采样点的实部和虚部）
                for sample_idx in range(0, num_samples, 10):
                    val = envelope[sample_idx]
                    lines.append(f"  {val:.8e}  0.00000000e+00")

            asc_files[filename] = "\n".join(lines).encode('utf-8')

    return asc_files


# ==================== 控制指令计算 ====================

def _compute_control_instructions(
    sim_rules,
    cdl_data,
    cal_entries,
    num_probes: int,
) -> ControlInstructions:
    """
    根据链路预算计算硬件控制指令。

    公式：
    RSRP_achieved = P_baseband - PathLoss + ProbeGain - CableLoss - AttenuatorSetting
    AttenuatorSetting = P_baseband - PathLoss + ProbeGain_avg - CableLoss_avg - Target_RSRP
    """
    pathloss_db = cdl_data.pathloss_db

    # 平均校准值
    if cal_entries:
        avg_cable_loss = np.mean([e.cable_loss_db for e in cal_entries])
        avg_probe_gain = np.mean([e.probe_gain_dbi for e in cal_entries])
    else:
        avg_cable_loss = 5.0   # 默认
        avg_probe_gain = 8.0   # 默认

    # 基带功率 = 目标发射功率
    baseband_power_dbm = sim_rules.target_tx_power_dbm

    # 衰减器设置 = 链路盈余
    link_budget_excess = (
        baseband_power_dbm
        - pathloss_db
        + float(avg_probe_gain)
        - float(avg_cable_loss)
        - sim_rules.target_rsrp_dbm
    )
    attenuator_db = max(0.0, float(link_budget_excess))

    # 实际达到的 RSRP
    achieved_rsrp = (
        baseband_power_dbm
        - pathloss_db
        + float(avg_probe_gain)
        - float(avg_cable_loss)
        - attenuator_db
    )

    # 每个 TX 端口一个衰减器
    num_tx = sim_rules.tx_antenna.num_rows * sim_rules.tx_antenna.num_cols
    attenuators = [round(attenuator_db, 2)] * num_tx

    return ControlInstructions(
        f64_baseband_power_dbm=round(float(baseband_power_dbm), 2),
        external_attenuators_db=attenuators,
        target_achieved_rsrp_dbm=round(float(achieved_rsrp), 2),
    )


# ==================== 诊断辅助 ====================

def _estimate_spatial_correlation(clusters) -> float:
    """
    估算空间相关性（基于簇角度扩展）。

    角度扩展越大 → 空间相关性越低。
    """
    if not clusters:
        return 1.0

    total_power = sum(c.power_relative_linear for c in clusters)
    if total_power <= 0:
        return 1.0

    # 功率加权角度扩展
    weighted_as = sum(
        c.as_aoa_deg * c.power_relative_linear for c in clusters
    ) / total_power

    # 简化经验公式: correlation ≈ exp(-0.1 * AS)
    correlation = float(np.exp(-0.1 * weighted_as))
    return round(min(max(correlation, 0.0), 1.0), 4)
