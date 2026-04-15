import logging
import os
from typing import Dict, Any

from app.services.channel_generation.base_generator import BaseChannelGenerator
from app.services.channel_engine_client import ChannelEngineClient
from app.hal.propsim_f64 import PropsimF64Controller

logger = logging.getLogger(__name__)

class MimoEngineASCStrategy(BaseChannelGenerator):
    """
    MIMO-First Custom ASC Synthesis Strategy (Our Technology)
    利用本机 8001 端口的自研 C++ 引擎，计算 WFS 参数，输出高维 .asc 矩阵 ZIP，
    并利用 F64 Runtime Emulation API 装载原始基带波形序列，架空 F64 自带算法。
    """

    def __init__(self, f64_controller: PropsimF64Controller, ce_client: ChannelEngineClient, chamber_config: Any, calibration_entries: list):
        super().__init__(chamber_config, calibration_entries)
        self.f64_controller = f64_controller
        self.ce_client = ce_client

    async def generate_and_load(self, simulation_rules: Dict[str, Any], cdl_model_data: Dict[str, Any]) -> bool:
        logger.info("[ASC Strategy] Starting Custom MIMO-First ASC Channel Generation")

        # 1. 调用 :8001 C++ 引擎，这部分复用我们之前打通的 Client 逻辑
        session_id = cdl_model_data.get("session_id", "par_bench_session")
        try:
            # Note: 这里的 cdl_model_data 只是个壳，在真实调用前应由编排服务展平
            # 这里为了适配策略接口结构，做安全的数据解析
            from app.services.channel_engine_client import CDLCluster
            
            pipeline_result = await self.ce_client.synthesize_hardware_pipeline(
                chamber_id=self.chamber_config.id,
                frequency_hz=simulation_rules.get("frequency_hz", 3.5e9),
                clusters=[CDLCluster(delay_s=0.0, power_relative_linear=1.0)], # Mock 
                cdl_model_name=cdl_model_data.get("model_name", "UMa CDL-C NLOS"),
                target_tx_power_dbm=simulation_rules.get("target_tx_power_dbm", 0.0),
                target_rsrp_dbm=simulation_rules.get("target_rsrp_dbm", -85.0),
                target_snr_db=simulation_rules.get("target_snr_db", 20.0),
                session_id=session_id
            )
            
            if not pipeline_result.success:
                logger.error(f"[ASC Strategy] synthesize failed: {pipeline_result.message}")
                return False
                
            asc_zip_path = pipeline_result.asc_files_path
            if not asc_zip_path or not os.path.exists(asc_zip_path):
                logger.error("[ASC Strategy] Failed to locate ASC payload from Channel Engine")
                return False
                
            logger.info(f"[ASC Strategy] ASC Payload generated successfully: {asc_zip_path}")
            
            # 2. 将 ASC 压缩包挂载 / FTP 上传给 F64 Storage
            logger.info("[ASC Strategy] Transferring ASC matrix to PROPSIM F64 over LAN")
            remote_path = self.f64_controller.transfer_file(asc_zip_path)
            
            # 3. 利用 Runtime Emulation API 载入 ARB 波形并 Playback
            logger.info(f"[ASC Strategy] Issuing Runtime Emulation load for ARB waveform at {remote_path}")
            success = self.f64_controller.load_runtime_emulation_data(remote_path)
            
            if success:
                logger.info("[ASC Strategy] ASC waveform successfully staged in F64 Runtime ARB")
            return success

        except Exception as e:
            logger.error(f"[ASC Strategy] Exception during synthesis/loading: {str(e)}")
            return False
