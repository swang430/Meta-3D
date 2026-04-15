import logging
from typing import Dict, Any

from app.services.channel_generation.base_generator import BaseChannelGenerator
from app.hal.propsim_f64 import PropsimF64Controller

logger = logging.getLogger(__name__)

class PropsimNativeGCMStrategy(BaseChannelGenerator):
    """
    Keysight GCM 原生合成策略 (Benchmarking Target)
    利用 F64 的 ATE 环境控制接口，下发 3GPP 参数给 F64 内置的 Channel Studio GCM 生成 `.cha` 并在内部运行。
    """

    def __init__(self, f64_controller: PropsimF64Controller, chamber_config: Any, calibration_entries: list):
        super().__init__(chamber_config, calibration_entries)
        self.f64_controller = f64_controller

    async def generate_and_load(self, simulation_rules: Dict[str, Any], cdl_model_data: Dict[str, Any]) -> bool:
        logger.info("[GCM Strategy] Starting Keysight Native Channel Generation")

        # 1. 解析参数为 GCM 能识别的格式 (例如转换为 GCM XML/JSON 预设)
        model_name = cdl_model_data.get("model_name", "3GPP_CDL-C")
        
        # 2. 调用 F64 内部的 GCM ATE subsystem
        logger.info(f"Commanding F64 to native-compile GCM project for model: {model_name}")
        
        # 在真实的 ATE 下：通常先生成工程文件，再传输给 F64 Server 执行 load
        # 伪代码：
        # gcm_project_file = self._build_gcm_project(simulation_rules, cdl_model_data)
        # self.f64_controller.scpi.upload(gcm_project_file)
        
        success = self.f64_controller.load_gcm_project(model_name)
        
        if success:
            logger.info("[GCM Strategy] Native .cha channel successfully loaded into F64 DSP")
        else:
            logger.error("[GCM Strategy] Failed to load GCM project")
            
        return success
