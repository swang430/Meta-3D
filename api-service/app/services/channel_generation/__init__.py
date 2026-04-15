"""
channel_generation - 并行信道生成策略包

提供基于 Strategy 模式的多引擎信道波形合成能力：
- PropsimNativeGCMStrategy: Keysight F64 原生 GCM 通道
- MimoEngineASCStrategy: MIMO-First 自研 C++ 引擎 ASC 通道
"""

from app.services.channel_generation.base_generator import BaseChannelGenerator, EngineMode
from app.services.channel_generation.gcm_strategy import PropsimNativeGCMStrategy
from app.services.channel_generation.asc_strategy import MimoEngineASCStrategy

__all__ = [
    "BaseChannelGenerator",
    "EngineMode",
    "PropsimNativeGCMStrategy",
    "MimoEngineASCStrategy",
]
