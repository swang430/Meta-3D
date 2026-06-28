"""
外部波形合成策略 (External Waveform Pipeline)

使用 MIMO-First 自研 Channel Engine (端口 8001) 计算 WFS 参数,
输出高维 .asc 矩阵 ZIP, 通过 HAL 统一接口上传到信道仿真器播放。

本策略通过 ChannelEmulatorDriver.load_channel(EXTERNAL_WAVEFORM) 调用,
不直接依赖任何具体仪器型号的驱动或控制器。
"""

import logging
import os
from typing import Dict, Any, List, TYPE_CHECKING

from app.services.channel_generation.base_generator import BaseChannelGenerator
from app.hal.channel_emulator import ChannelEmulatorDriver, ChannelLoadMode

if TYPE_CHECKING:
    # Lazy: avoid circular import at module load time
    # (channel_engine_client → channel_generation/__init__.py → asc_strategy)
    from app.services.channel_engine_client import ChannelEngineClient

logger = logging.getLogger(__name__)


class ExternalWaveformStrategy(BaseChannelGenerator):
    """
    MIMO-First 自研 ASC 合成策略 (Our Technology)

    利用 :8001 端口的自研 C++ 引擎计算 WFS 参数,
    输出高维 .asc 矩阵 ZIP, 通过 HAL 统一接口上传到仿真器,
    以 ARB/Runtime Emulation 模式播放。

    这是所有信道仿真器都支持的通用模式。
    无论底层是 F64、R&S 还是 Spirent, 本策略代码无需修改。
    """

    def __init__(
        self,
        emulator: ChannelEmulatorDriver,
        ce_client: "ChannelEngineClient",
        chamber_config: Any,
        calibration_entries: List[Dict],
    ):
        super().__init__(emulator, chamber_config, calibration_entries)
        self.ce_client = ce_client

    async def generate_and_load(
        self,
        simulation_rules: Dict[str, Any],
        cdl_model_data: Dict[str, Any],
    ) -> bool:
        logger.info(
            "[ExternalWaveform Strategy] Starting MIMO-First ASC Channel Generation"
        )

        session_id = cdl_model_data.get("session_id", "par_bench_session")

        try:
            # P2-15: custom CDL profile (cdl_profile_id) 优先于标称 cdl_model_name —
            # 查 profile + 装配簇 → input_mode=custom; 否则走 standard 38.901 路。
            cdl_profile_id = cdl_model_data.get("cdl_profile_id")
            if cdl_profile_id:
                pipeline_result = await self._synthesize_custom_cdl(
                    str(cdl_profile_id), simulation_rules, session_id,
                )
            else:
                # 2026-05-19 P1-7: 替换 P0-7 留下的 hardcoded mock cluster — 解析
                # 操作员选的 cdl_model_name → (scenario, cluster_model, condition),
                # 调 ChannelEngineClient 走 input_mode='standard', 让 ChannelEgine
                # 内部 38.901 generator 算簇.
                from app.services.cdl_model_parser import parse_cdl_model_name

                model_name = cdl_model_data.get("model_name", "UMa NLOS CDL-C")
                parsed = parse_cdl_model_name(model_name)
                logger.info(
                    f"[ExternalWaveform Strategy] {model_name} → "
                    f"scenario={parsed.scenario_name}, "
                    f"cluster_model={parsed.cluster_model_name}, "
                    f"condition={parsed.condition}"
                )

                # ue_velocity_mps 从 simulation_rules 提取 (操作员上游已经规约为
                # 3-vec m/s 优先); 否则让 client 从 kph 默认派生.
                ue_velocity_mps = simulation_rules.get("ue_velocity_mps")

                pipeline_result = await self.ce_client.synthesize_hardware_pipeline(
                    chamber_id=self.chamber_config.id,
                    frequency_hz=simulation_rules.get("frequency_hz", 3.5e9),
                    cdl_model_name=model_name,
                    pathloss_db=simulation_rules.get("pathloss_db", 100.0),
                    is_los=parsed.is_los,
                    target_tx_power_dbm=simulation_rules.get(
                        "target_tx_power_dbm", 0.0
                    ),
                    target_rsrp_dbm=simulation_rules.get("target_rsrp_dbm", -85.0),
                    target_snr_db=simulation_rules.get("target_snr_db", 20.0),
                    ue_velocity_kph=simulation_rules.get("ue_velocity_kph", 15.0),
                    session_id=session_id,
                    # 2026-05-19 P1-7: standard 3GPP dispatch + transparent passthrough
                    input_mode="standard",
                    scenario_name=parsed.scenario_name,
                    cluster_model_name=parsed.cluster_model_name,
                    force_condition=parsed.condition,  # LOS / NLOS 显式 (跳过 auto)
                    # 2026-05-18 P0-7 Phase 5/6 fields — was defaulted in P0-7,
                    # now operator-controllable from simulation_rules.
                    synthesis_method=simulation_rules.get(
                        "synthesis_method", "strict_pfs"
                    ),
                    ue_velocity_mps=ue_velocity_mps,
                    k_factor_db=simulation_rules.get("k_factor_db"),
                )

            if not pipeline_result.success:
                logger.error(
                    f"[ExternalWaveform Strategy] synthesize failed: "
                    f"{pipeline_result.message}"
                )
                return False

            asc_zip_path = pipeline_result.asc_files_path
            if not asc_zip_path or not os.path.exists(asc_zip_path):
                logger.error(
                    "[ExternalWaveform Strategy] Failed to locate ASC payload "
                    "from Channel Engine"
                )
                return False

            logger.info(
                f"[ExternalWaveform Strategy] ASC Payload generated: {asc_zip_path}"
            )

            # 通过 HAL 统一接口加载, 不关心底层是 F64 还是 R&S
            model_name = cdl_model_data.get("model_name", "CDL-C")
            success = await self.emulator.load_channel(
                mode=ChannelLoadMode.EXTERNAL_WAVEFORM,
                model_name=model_name,
                scenario=cdl_model_data.get("scenario", "UMi"),
                parameters=simulation_rules,
                waveform_dir=asc_zip_path,
            )

            if success:
                logger.info(
                    "[ExternalWaveform Strategy] ASC waveform successfully staged "
                    "in emulator"
                )
            return success

        except Exception as e:
            logger.error(
                f"[ExternalWaveform Strategy] Exception during synthesis/loading: "
                f"{str(e)}"
            )
            return False

    async def _synthesize_custom_cdl(self, cdl_profile_id, simulation_rules, session_id):
        """P2-15: 查 CustomCDLProfile + 装配簇 → synthesize(input_mode=custom)。

        路损/LOS/K因子/速度 profile 优先, 缺省落 simulation_rules / 默认。**频率**用 TestCase
        单一真值源 (profile 频率仅一致性校验, ≠ TestCase 频率 → fail-loud, Codex P1 #171)。
        簇 power_linear→power_relative_linear + num_rays 等由 cdl_clusters_from_profile_dicts
        装配 (S2)。db 从 ce_client.db 拿 (ChannelEngineClient 持有 Session)。
        """
        from uuid import UUID
        from app.services.custom_cdl_profile_service import get_custom_cdl_profile
        from app.services.channel_engine_client import cdl_clusters_from_profile_dicts

        profile = get_custom_cdl_profile(self.ce_client.db, UUID(str(cdl_profile_id)))
        clusters = cdl_clusters_from_profile_dicts(profile.clusters or [])

        # 频率一致性门 (Codex P1 #171; project_testcase_driven_instrument_arch 单一真值源):
        # TestCase frequency_hz 驱动 UXM 定频 / 校准 / 整个 measure path。若 custom CDL
        # profile.center_frequency_hz 设了且 ≠ TestCase 频率, 波形会在 profile 频率合成+校准,
        # 但系统其余按 TestCase 频率跑 → 测量污染。fail-loud mismatch (不静默用错频率);
        # 合成一律用 TestCase 频率, profile 频率仅作一致性校验、不覆盖整条 measure path。
        tc_freq = simulation_rules.get("frequency_hz", 3.5e9)
        if (profile.center_frequency_hz is not None
                and abs(profile.center_frequency_hz - tc_freq) > 1.0):
            raise ValueError(
                f"custom CDL '{profile.name}' center_frequency_hz="
                f"{profile.center_frequency_hz:.0f} ≠ TestCase frequency_hz={tc_freq:.0f} — 波形会"
                f"在 profile 频率合成+校准但系统按 TestCase 频率跑, 测量污染; 对齐两边频率, 或清空"
                f" profile 频率用 TestCase。"
            )
        logger.info(
            "[ExternalWaveform Strategy] custom CDL '%s' (%d 簇) → input_mode=custom @ %.0f Hz",
            profile.name, len(clusters), tc_freq,
        )
        return await self.ce_client.synthesize_hardware_pipeline(
            chamber_id=self.chamber_config.id,
            frequency_hz=tc_freq,
            clusters=clusters,
            cdl_model_name=profile.name,
            pathloss_db=(
                profile.pathloss_db if profile.pathloss_db is not None
                else simulation_rules.get("pathloss_db", 100.0)
            ),
            is_los=bool(profile.is_los) if profile.is_los is not None else False,
            target_tx_power_dbm=simulation_rules.get("target_tx_power_dbm", 0.0),
            target_rsrp_dbm=simulation_rules.get("target_rsrp_dbm", -85.0),
            target_snr_db=simulation_rules.get("target_snr_db", 20.0),
            ue_velocity_kph=simulation_rules.get("ue_velocity_kph", 15.0),
            session_id=session_id,
            input_mode="custom",
            synthesis_method=simulation_rules.get("synthesis_method", "strict_pfs"),
            ue_velocity_mps=(
                profile.ue_velocity_mps or simulation_rules.get("ue_velocity_mps")
            ),
            k_factor_db=profile.k_factor_db,
        )
