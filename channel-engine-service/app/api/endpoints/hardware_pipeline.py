"""
Hardware Pipeline Synthesis Endpoint

POST /api/v1/synthesize_hardware_pipeline

基于 `ChannelEgine/doc/MIMO_First_Integration_Spec.md` **v2.0** 实现
(2026-05-18 P0-7 重写; 升级注意事项见该 spec §0 audit batch 2)。
接收 MIMO-First 下发的完整仿真参数，返回 .asc 硬件驱动文件和控制指令。
"""

import re
import time
import io
import os
import sys
import shutil
import zipfile
import base64
import logging
import tempfile
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

# ---------------------------------------------------------------------------
# Configuration — CHANNEL_ENGINE_PATH + MOCK_ASC_MODE
# ---------------------------------------------------------------------------
#
# CHANNEL_ENGINE_PATH: 本地 ChannelEgine clone 的绝对路径. 必须设置.
#   无 sane default — 上一版默认 ~/ChannelEgine 在大多数环境不存在,
#   导致 ImportError → 静默 fallback 到 mock → 操作员拿到假 .asc.
#   2026-05-18 P0-7 修复: 启动期 fail-fast (除非 MOCK_ASC_MODE=1).
#
# MOCK_ASC_MODE: 显式 mock-only 调试模式. 设为 "1"/"true"/"yes" 时:
#   - 启动期跳过 CHANNEL_ENGINE_PATH 校验
#   - 所有 synthesize_hardware_pipeline 请求返回占位 .asc + mock_mode=True
#   - 适用场景: 本地开发, 没装 ChannelEgine 时验证 endpoint 形状
#   - 生产**严禁**启用.
# ---------------------------------------------------------------------------

CHANNEL_ENGINE_PATH = os.environ.get('CHANNEL_ENGINE_PATH', '').strip()

MOCK_ASC_MODE = os.environ.get('MOCK_ASC_MODE', '').strip().lower() in (
    '1', 'true', 'yes',
)


class ChannelEngineUnavailable(RuntimeError):
    """ChannelEgine 库不可导入 (路径不存在 / Python module 找不到 / 类名漂移)."""


def _import_simulator_class():
    """Import the ChannelEgine `MIMO_OTA_Simulator` class.

    Raises `ChannelEngineUnavailable` with an actionable message on failure;
    never returns None (callers that want a mock-only path must check
    `MOCK_ASC_MODE` upstream and skip the call entirely).
    """
    if not CHANNEL_ENGINE_PATH:
        raise ChannelEngineUnavailable(
            "CHANNEL_ENGINE_PATH env var is not set. "
            "Point it at a local ChannelEgine clone "
            "(e.g. CHANNEL_ENGINE_PATH=/Users/yourname/Tools/ChannelEgine), "
            "or set MOCK_ASC_MODE=1 for debug-only mock synthesis."
        )
    if not os.path.isdir(CHANNEL_ENGINE_PATH):
        raise ChannelEngineUnavailable(
            f"CHANNEL_ENGINE_PATH does not exist or is not a directory: "
            f"{CHANNEL_ENGINE_PATH!r}. Check the path or set MOCK_ASC_MODE=1 "
            f"for debug-only mock synthesis."
        )
    if CHANNEL_ENGINE_PATH not in sys.path:
        sys.path.insert(0, CHANNEL_ENGINE_PATH)
    try:
        from mimo_ota_simulator.simulator import MIMO_OTA_Simulator
    except ImportError as e:
        raise ChannelEngineUnavailable(
            f"Failed to import MIMO_OTA_Simulator from {CHANNEL_ENGINE_PATH}: {e}. "
            f"The clone must include Phase 1+ (strict_pfs rollout, PR #1 onward). "
            f"Update the clone with `git pull` in {CHANNEL_ENGINE_PATH}."
        ) from e
    return MIMO_OTA_Simulator


def validate_channel_engine_at_startup() -> None:
    """启动期 fail-fast 校验. 由 main.py startup_event 调用.

    - MOCK_ASC_MODE=1: 跳过校验, 写显眼 WARNING 日志.
    - 否则: 尝试 import; 失败时让异常冒泡 → uvicorn 启动 fail.
    """
    if MOCK_ASC_MODE:
        logger.warning(
            "=" * 60 + "\n"
            "MOCK_ASC_MODE=1 — ChannelEgine validation skipped at startup.\n"
            "All synthesize_hardware_pipeline requests will return placeholder\n"
            ".asc with mock_mode=true in the response. DO NOT USE IN PRODUCTION.\n"
            + "=" * 60
        )
        return
    try:
        _import_simulator_class()
        logger.info(
            f"ChannelEgine validation passed at startup "
            f"(CHANNEL_ENGINE_PATH={CHANNEL_ENGINE_PATH})"
        )
    except ChannelEngineUnavailable as e:
        logger.error(f"ChannelEgine validation FAILED at startup: {e}")
        raise


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

        # cdl_data.clusters is None in standard mode (ChannelEgine generates them)
        cluster_count_str = (
            f"{len(cdl_data.clusters)} clusters (custom)"
            if cdl_data.clusters is not None
            else f"{request.input_mode} mode (clusters from ChannelEgine)"
        )
        logger.info(
            f"Hardware pipeline [{cdl_data.model_name}]: "
            f"{chamber.num_probes} probes, "
            f"{cluster_count_str}, "
            f"freq={sim_rules.center_frequency_hz/1e9:.2f} GHz"
        )

        # -----------------------------------------------------------
        # 路由: MOCK_ASC_MODE (debug-only) vs 真实算法库
        # 2026-05-18 P0-7: 不再静默 ImportError fallback. 真实路径失败
        # 一定 raise → 500; mock 路径只在显式 MOCK_ASC_MODE=1 时生效.
        # 两条路径都返回 (zip_base64, total_files) — 真实路径用 ChannelEgine
        # PropsimASCIIExporter.export_to_zip_memory 直出 base64, 不落盘.
        # -----------------------------------------------------------
        if MOCK_ASC_MODE:
            zip_base64, total_files = _run_mock_synthesis(
                num_tx=num_tx,
                num_ports=num_ports,
                clusters=cdl_data.clusters,
                frequency_hz=sim_rules.center_frequency_hz,
                velocity_kph=sim_rules.ue_velocity_kph,
            )
        else:
            simulator_cls = _import_simulator_class()  # raises on failure
            # P2-16 S3: routing_mode 选合成脊。'annotated_b1' 走标注式烘焙路
            # (装配 AnnotatedCDLProfile + bake_b1_annotated, 接线悬空 baker);
            # 'legacy' (默认) 走现 CustomCDLBuilder + run() 直路, 零行为变更。
            if request.routing_mode == "annotated_b1":
                zip_base64, total_files = _run_annotated_bake_synthesis(request)
            else:
                zip_base64, total_files = _run_real_synthesis(simulator_cls, request)

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
            f"Hardware pipeline complete: {total_files} files, "
            f"{elapsed_ms:.0f}ms (mock_mode={MOCK_ASC_MODE})"
        )

        return HardwarePipelineResponse(
            status="success",
            computation_time_ms=round(elapsed_ms, 1),
            hardware_artifacts=HardwareArtifacts(
                f64_asc_files_zip_base64=zip_base64,
                total_files_generated=total_files,
                cdl_model_name=cdl_data.model_name,
            ),
            control_instructions=control,
            diagnostics=diagnostics,
            mock_mode=MOCK_ASC_MODE,
        )

    except ChannelEngineUnavailable as e:
        # 配置错误 (CHANNEL_ENGINE_PATH 不存在 / import fail) — 503 表达
        # "服务暂时不可用, 不是请求错误". 跟 generic Exception 区分.
        elapsed_ms = (time.time() - start_time) * 1000
        logger.error(f"ChannelEgine unavailable: {e}")
        raise HTTPException(
            status_code=503,
            detail=(
                f"Channel Engine library unavailable: {e}. "
                f"Fix the microservice configuration or set MOCK_ASC_MODE=1 "
                f"for debug-only mock synthesis."
            ),
        ) from e
    except Exception as e:
        elapsed_ms = (time.time() - start_time) * 1000
        logger.exception(f"Hardware pipeline failed: {e}")
        return HardwarePipelineResponse(
            status="error",
            computation_time_ms=round(elapsed_ms, 1),
            error_message=str(e),
            mock_mode=MOCK_ASC_MODE,
        )


# ==================== 真实合成 ====================

def _build_custom_cdl_profile(request: HardwarePipelineRequest):
    """把 HardwarePipelineRequest 的 cdl_model_data + simulation_rules 映射到
    ChannelEgine `CustomCDLProfile`. 2026-05-18 P0-7 / Spec v2.0.

    跨 schema 字段名差异:
    - microservice CDLCluster.power_relative_linear → CDLClusterSpec.power_linear
    - microservice SimulationRules.ue_velocity_kph (scalar) → CustomCDLProfile.ue_velocity_mps (3-vec)
      优先使用显式的 ue_velocity_mps; 缺省时从 kph 派生 [kph/3.6, 0, 0].
    """
    from mimo_ota_simulator.cdl_schema import CustomCDLProfile  # type: ignore  # 运行时路径

    sim_rules = request.simulation_rules
    cdl_data = request.cdl_model_data

    if sim_rules.ue_velocity_mps is not None:
        if len(sim_rules.ue_velocity_mps) != 3:
            raise ValueError(
                f"ue_velocity_mps must be a 3-vector [vx, vy, vz]; "
                f"got {sim_rules.ue_velocity_mps!r}"
            )
        velocity_mps = tuple(sim_rules.ue_velocity_mps)
    else:
        # 默认沿 x 轴运动 (3GPP TR 37.977 现场惯例)
        velocity_mps = (sim_rules.ue_velocity_kph / 3.6, 0.0, 0.0)

    clusters_payload = []
    for c in cdl_data.clusters:
        clusters_payload.append({
            "delay_s": c.delay_s,
            "power_linear": c.power_relative_linear,
            "aoa_deg": c.aoa_deg,
            "aod_deg": c.aod_deg,
            "zoa_deg": c.zoa_deg,
            "zod_deg": c.zod_deg,
            "as_aoa_deg": c.as_aoa_deg,
            # audit batch 2 跟进: 三个角度扩展补透传 (as_zoa 兼作探头权重高斯
            # el 宽度, spec v2.0 §3); 此前 adapter 丢弃 → 库端落默认 0。
            "as_aod_deg": c.as_aod_deg,
            "as_zoa_deg": c.as_zoa_deg,
            "as_zod_deg": c.as_zod_deg,
            "xpr_db": c.xpr_db,
            # ChannelEgine 的 initial_phases_rad 接受 None (内部随机); 显式传 None
            # 而不是 omit, 这样 schema validator 仍走 Optional 分支.
            "initial_phases_rad": c.initial_phases_rad,
            # P2-15: 转发每簇子径数到 ChannelEgine CDLClusterSpec.num_rays (Codex P2 #170:
            # 接收 model 声明 + adapter 转发缺一不可, 否则 num_rays 静默丢, 合成落默认).
            "num_rays": c.num_rays,
        })

    return CustomCDLProfile.from_dict({
        "center_frequency_hz": sim_rules.center_frequency_hz,
        "pathloss_db": cdl_data.pathloss_db,
        "ue_velocity_mps": velocity_mps,
        "is_los": cdl_data.is_los,
        "k_factor_db": cdl_data.k_factor_db,
        "clusters": clusters_payload,
    })


def _build_chamber_config(request: HardwarePipelineRequest):
    """微服务 ChamberConfig → ChannelEgine ChamberConfig.

    P1-10 (2026-05-19): probe_positions 透传给 ChannelEgine Phase 8
    ``ChamberConfig.probe_positions``. ring 路径不传 (= None), 走 ChannelEgine
    ``(p × 360°/N)`` 公式; multi-ring / custom 必传, 走 sphere → Cartesian.
    """
    from mimo_ota_simulator.data_models import (  # type: ignore
        ChamberConfig as CEChamberConfig,
        ProbePosition as CEProbePosition,
    )

    chamber = request.chamber_config

    ce_probe_positions = None
    if chamber.probe_positions is not None:
        ce_probe_positions = [
            CEProbePosition(
                azimuth_deg=p.azimuth_deg,
                elevation_deg=p.elevation_deg,
            )
            for p in chamber.probe_positions
        ]

    return CEChamberConfig(
        num_probes=chamber.num_probes,
        dual_polarized=chamber.dual_polarized,
        distribution=chamber.distribution,
        radius_m=chamber.radius_m,
        probe_positions=ce_probe_positions,
    )


def _build_target_channel_config(request: HardwarePipelineRequest, profile):
    """微服务 SimulationRules + (CustomCDLProfile | Standard3GPPConfig) →
    ChannelEgine TargetChannelConfig. 按 request.input_mode 分路.

    - 'custom' (P0-7 路径): CustomCDLProfile 喂 ChannelEgine `CustomCDLBuilder`
    - 'standard' (P1-7 新增): 透传 scenario / cluster_model / positions, 让
      ChannelEgine `Standard3GPPBuilder` 内部 38.901 generator 生成簇集
    """
    from mimo_ota_simulator.data_models import (  # type: ignore
        AntennaArrayConfig, TargetChannelConfig as CETargetChannelConfig,
    )

    sim_rules = request.simulation_rules

    def _antenna(ant):
        return AntennaArrayConfig(
            array_type=ant.array_type,
            num_rows=ant.num_rows,
            num_cols=ant.num_cols,
            spacing_h=ant.spacing_h,
            spacing_v=ant.spacing_v,
            polarization=ant.polarization,  # Phase 6 dual-pol 关键字段
        )

    # UE velocity: 跟 _build_custom_cdl_profile 同一规则 (3-vec 优先, 否则
    # 从 kph 派生). standard 路径里 TargetChannelConfig.ue_velocity 是 m/s 3-vec.
    if sim_rules.ue_velocity_mps is not None:
        ue_velocity = list(sim_rules.ue_velocity_mps)
    else:
        ue_velocity = [sim_rules.ue_velocity_kph / 3.6, 0.0, 0.0]

    common_kwargs = dict(
        center_frequency_hz=sim_rules.center_frequency_hz,
        tx_antenna=_antenna(sim_rules.tx_antenna),
        rx_antenna=_antenna(sim_rules.rx_antenna),
        ue_velocity=ue_velocity,
    )

    if request.input_mode == "standard":
        std = request.standard_3gpp
        if std is None:
            # schema validator 应该已经拦了, 但防御性 raise 给清晰错误
            raise ValueError(
                "input_mode='standard' but request.standard_3gpp is None "
                "(schema validator should have caught this)"
            )
        return CETargetChannelConfig(
            input_mode="standard",
            model_name=std.scenario_name,
            cluster_model_name=std.cluster_model_name,
            bs_position=std.bs_position,
            ue_position=std.ue_position,
            random_seed=std.random_seed,
            # force_condition: 'auto' 不传 (让 ChannelEgine 用 None default
            # = scenario 几何概率), 显式 LOS/NLOS 才透传
            force_condition=(
                None if std.force_condition == "auto" else std.force_condition
            ),
            **common_kwargs,
        )

    # input_mode == "custom" (P0-7 路径不变)
    return CETargetChannelConfig(
        input_mode="custom",
        custom_profile=profile,
        **common_kwargs,
    )


def _run_real_synthesis(SimulatorClass, request: HardwarePipelineRequest):
    """通过 ChannelEgine `MIMO_OTA_Simulator().run()` 真实合成 .asc.

    2026-05-18 P0-7 / Spec v2.0 重写: 此前调用 `run_with_external_clusters`
    + 命名空间错误的类 `OTASimulator` + 错误的构造签名, 100% 调用 fail 静默
    fallback 到 mock. 新版按 ChannelEgine Phase 1-6 stable public API 调用,
    用 `PropsimASCIIExporter.export_to_zip_memory` 直出 base64, 不落盘.

    Returns:
        (zip_base64: str, total_files: int)
    """
    from mimo_ota_simulator.data_models import PropsimExportConfig  # type: ignore
    from mimo_ota_simulator.exporters import PropsimASCIIExporter  # type: ignore

    # 2026-05-19 P1-7: standard mode 不需要 CustomCDLProfile (ChannelEgine
    # `Standard3GPPBuilder` 内部生成簇), 跳过这一步避免对 cdl_model_data.clusters
    # 的 None 解引用 (clusters 在 standard 模式是 Optional).
    profile = (
        _build_custom_cdl_profile(request)
        if request.input_mode == "custom"
        else None
    )
    chamber_cfg = _build_chamber_config(request)
    channel_cfg = _build_target_channel_config(request, profile)

    sim_rules = request.simulation_rules
    synthesis_method = sim_rules.synthesis_method
    # ChannelEgine Phase 3 (PR #2) DEPRECATED `cluster` (内部叫 cluster).
    # 微服务 schema 用 `cluster_legacy` 显式标 legacy 意图; 翻译回原生命名.
    ce_synthesis_method = (
        "cluster" if synthesis_method == "cluster_legacy" else synthesis_method
    )

    simulator = SimulatorClass()  # ChannelEgine: 无参构造
    sim_result = simulator.run(
        chamber_cfg,
        channel_cfg,
        synthesis_method=ce_synthesis_method,
    )

    # base64-direct export, 跨进程 / 跨容器都不依赖 host filesystem
    exporter = PropsimASCIIExporter(PropsimExportConfig(
        filename=f"{request.cdl_model_data.model_name.replace(' ', '_')}.asc",
        mode="B",
        duration_s=0.1,
        sample_rate_hz=1000.0,
    ))
    base_name = request.cdl_model_data.model_name.replace(" ", "_") or "propsim_export"
    zip_base64 = exporter.export_to_zip_memory(
        sim_result, base_name=base_name, direction="dl"
    )

    # 计算 total_files: PropsimASCIIExporter 输出 (num_tx × num_effective_probes)
    # 个 .asc. 微服务 schema 跟 ChannelEgine 计算口径一致.
    num_tx = sim_rules.tx_antenna.num_rows * sim_rules.tx_antenna.num_cols
    num_ports = request.chamber_config.num_probes * (
        2 if request.chamber_config.dual_polarized else 1
    )
    total_files = num_tx * num_ports

    return zip_base64, total_files


# ==================== P2-16 S3: 标注式 B-1 烘焙路 ====================

def _zip_asc_files_base64(asc_paths: List[str]) -> str:
    """把 bake 写出的 .asc 文件列表打进内存 zip → base64。

    bake_b1_annotated 经 PropsimASCIIExporter.export 写盘 (无内存变体), 这里收口为
    不落盘的 base64, 与 legacy 路 export_to_zip_memory 同响应契约 (HardwareArtifacts
    .f64_asc_files_zip_base64)。arcname 用 basename, 避免 tmpdir 绝对路径泄进 zip。
    """
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in asc_paths:
            zf.write(p, arcname=os.path.basename(p))
    return base64.b64encode(buf.getvalue()).decode("ascii")


def _safe_asc_base_name(model_name: str) -> str:
    """消毒 model_name 为安全的磁盘 .asc 文件名分量 (Codex #176 P2: 防路径穿越)。

    annotated 路把 model_name 拼进 tmpdir 下的 export 路径 (legacy 用 export_to_zip_memory
    写内存无此风险)。含 '/' / '..' / 绝对路径的 model_name 会让 os.path.join 写出 tmpdir
    外。消毒: basename 去目录段 + 只留 [\\w.-] + 去首尾点/下划线 → 保证是单一文件名分量;
    空 (如 '..' / 纯符号) 回落 'propsim_export'。
    """
    return re.sub(r"[^\w.-]", "_", os.path.basename(model_name)).strip("._") or "propsim_export"


def _run_annotated_bake_synthesis(request: HardwarePipelineRequest):
    """P2-16 S3: 经 AnnotatedCDLProfile + bake_b1_annotated 标注式 B-1 烘焙路合成 .asc。

    接线设计 §1.2 断层 C 的悬空 baker (此前仅单测消费, 零生产端点): custom CDLCluster
    → `from_custom_profile` 装单快照 AnnotatedCDLProfile (target_path=B1_baked, 全簇
    DopplerBaked) → `bake_b1_annotated` → per-(Tx,Probe) .asc。

    与 legacy `_run_real_synthesis` 逐位等价 (custom 全 baked 簇): run() 3GPP 路 =
    [seed if random_seed] + create_builder(custom).build() + synthesize_ota; bake 复刻
    同三步 (from_custom_profile round-trip 无损 + 同 builder + 同 synthesize_ota +
    cluster_subrays={} 对全 baked 簇无效), golden test_b1_golden_vs_legacy 已证。custom
    模式 channel_config.random_seed=None → 两路都不自播种, 同 ambient RNG。本路统一 ACP
    烘焙脊, 解锁 subray_sum 确定性相位 (rt_dynamic, S3 后续切片)。

    bake 经 exporter.export 写盘 → 这里 zip 进内存出 base64, tmpdir 用后即弃。
    (sys.path 注入 + ChannelEgine 可用性 fail-fast 由 caller 先调 _import_simulator_class 保证。)

    Returns: (zip_base64: str, total_files: int)
    """
    # Codex #176 P2: baker 模块比 simulator 新, _import_simulator_class() 只校验
    # MIMO_OTA_Simulator → 旧 ChannelEgine clone (有 simulator 无 baker) 能过启动门,
    # 这里裸 ImportError 会落 generic except → status='error' (200), 而非缺依赖应有的
    # 503 fail-fast。包成 ChannelEngineUnavailable 走端点 503 分支, 跟 legacy 缺依赖
    # 一致, 防新路静默带病上线。(legacy 路的 data_models/exporters import 安全 ——
    # simulator 依赖它们, 缺则 _import_simulator_class 已先 fail。)
    try:
        from mimo_ota_simulator.annotated_cdl_schema import AnnotatedCDLProfile  # type: ignore
        from mimo_ota_simulator.b1_annotated_baker import bake_b1_annotated  # type: ignore
        from mimo_ota_simulator.data_models import PropsimExportConfig  # type: ignore
    except ImportError as e:
        raise ChannelEngineUnavailable(
            f"routing_mode='annotated_b1' 需要 ChannelEgine 标注式烘焙模块 "
            f"(annotated_cdl_schema / b1_annotated_baker), 当前 CHANNEL_ENGINE_PATH "
            f"clone 缺失 (可能旧版): {e}. 升级 ChannelEgine clone 或改 routing_mode='legacy'."
        ) from e

    # 装配: custom CDLCluster → CustomCDLProfile → 单快照 AnnotatedCDLProfile (B1_baked)
    custom_profile = _build_custom_cdl_profile(request)
    annotated = AnnotatedCDLProfile.from_custom_profile(custom_profile)
    chamber_cfg = _build_chamber_config(request)
    channel_cfg = _build_target_channel_config(request, custom_profile)

    sim_rules = request.simulation_rules
    synthesis_method = sim_rules.synthesis_method
    # 与 _run_real_synthesis 同语义: cluster_legacy → 原生 'cluster' (Phase 3 改名)
    ce_synthesis_method = (
        "cluster" if synthesis_method == "cluster_legacy" else synthesis_method
    )

    # Codex #176 P2: model_name 进磁盘路径前必须消毒防路径穿越 (见 _safe_asc_base_name)。
    base_name = _safe_asc_base_name(request.cdl_model_data.model_name)
    tmpdir = tempfile.mkdtemp(prefix="b1_annotated_")
    try:
        export_cfg = PropsimExportConfig(
            filename=os.path.join(tmpdir, f"{base_name}.asc"),
            mode="B", duration_s=0.1, sample_rate_hz=1000.0,
        )
        # Codex #176 P2 (calibration): calibration_config 省略 (=None) 是**有意保 parity**,
        # 非丢校准。校准经 endpoint 在路由 if/else 之后无条件计算的 control_instructions
        # 施加 (cal_entries → external_attenuators_db + baseband power, 见
        # _compute_control_instructions), legacy 与 annotated 两路同一调用, cal 不丢。两路 exporter 都
        # calibration_config=None → .asc 都 cal-free; 若这里烘 cal 进 .asc 会与 legacy
        # 直路分叉, 破坏验收③逐位一致 (test_annotated_b1_endpoint_cal_via_control 证 cal
        # 经 control 生效)。cal 烘进 .asc 是另一套校准模型, 属未来跨两路的设计决策, 非 S3-1。
        asc_paths = bake_b1_annotated(
            annotated, chamber_cfg, channel_cfg, export_cfg,
            synthesis_method=ce_synthesis_method, direction="dl",
        )
        zip_base64 = _zip_asc_files_base64(asc_paths)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)

    return zip_base64, len(asc_paths)


# ==================== Mock 合成 ====================

def _run_mock_synthesis(
    num_tx: int,
    num_ports: int,
    clusters,
    frequency_hz: float,
    velocity_kph: float,
):
    """Mock 模式：生成占位 .asc 文件 zip + base64 (debug-only).

    每个文件包含一条带有多普勒偏移的 TDL 抽头序列, 格式兼容 Keysight
    Propsim F64. 2026-05-18 P0-7: 返回 (zip_base64, total_files) 跟真实
    路径同形, 只在显式 MOCK_ASC_MODE=1 时被调用.

    Returns:
        (zip_base64: str, total_files: int)
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

    # 把 dict-of-bytes 打 ZIP → base64, 跟真实路径同形 (调用方现在期待 tuple)
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        for filename, content in asc_files.items():
            zf.writestr(filename, content)
    zip_base64 = base64.b64encode(zip_buffer.getvalue()).decode('ascii')
    return zip_base64, len(asc_files)


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
