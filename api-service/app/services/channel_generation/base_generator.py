from enum import Enum
from abc import ABC, abstractmethod
from typing import Dict, Any, List

class EngineMode(str, Enum):
    GCM_NATIVE = "keysight_gcm"       # Keysight native Channel Studio GCM
    ASC_SYNTHESIS = "mimo_first_asc"  # MIMO-First Custom ASC Synthesis Engine

class BaseChannelGenerator(ABC):
    """
    信道波形合成策略的接口基类
    定义了向硬件（F64）装载信道波形的标准化抽象。
    """

    def __init__(self, chamber_config: Any, calibration_entries: List[Dict]):
        self.chamber_config = chamber_config
        self.calibration_entries = calibration_entries

    @abstractmethod
    async def generate_and_load(self, simulation_rules: Dict[str, Any], cdl_model_data: Dict[str, Any]) -> bool:
        """
        生成信道文件并将其装载入物理硬件
        返回: 成功则为 True
        """
        pass
