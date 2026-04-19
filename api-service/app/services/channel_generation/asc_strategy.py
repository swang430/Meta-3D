"""
外部波形合成策略 (External Waveform Pipeline)

使用 MIMO-First 自研 Channel Engine (端口 8001) 计算 WFS 参数,
输出高维 .asc 矩阵 ZIP, 通过 HAL 统一接口上传到信道仿真器播放。

本策略通过 ChannelEmulatorDriver.load_channel(EXTERNAL_WAVEFORM) 调用,
不直接依赖任何具体仪器型号的驱动或控制器。
"""

import logging
import os
from typing import Dict, Any, List

from app.services.channel_generation.base_generator import BaseChannelGenerator
from app.services.channel_engine_client import ChannelEngineClient
from app.hal.channel_emulator import ChannelEmulatorDriver, ChannelLoadMode

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
        ce_client: ChannelEngineClient,
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
            from app.services.channel_engine_client import CDLCluster

            pipeline_result = await self.ce_client.synthesize_hardware_pipeline(
                chamber_id=self.chamber_config.id,
                frequency_hz=simulation_rules.get("frequency_hz", 3.5e9),
                clusters=[
                    CDLCluster(delay_s=0.0, power_relative_linear=1.0)
                ],  # Mock
                cdl_model_name=cdl_model_data.get(
                    "model_name", "UMa CDL-C NLOS"
                ),
                target_tx_power_dbm=simulation_rules.get(
                    "target_tx_power_dbm", 0.0
                ),
                target_rsrp_dbm=simulation_rules.get("target_rsrp_dbm", -85.0),
                target_snr_db=simulation_rules.get("target_snr_db", 20.0),
                session_id=session_id,
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
