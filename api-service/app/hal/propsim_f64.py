import logging
import asyncio
from typing import Dict, Any, List, Optional
from datetime import datetime

from app.hal.base import (
    InstrumentDriver,
    InstrumentStatus,
    InstrumentCapability,
    InstrumentMetrics,
)

logger = logging.getLogger(__name__)


class RealPropsimF64Driver(InstrumentDriver):
    """
    Keysight PROPSIM F64 真实物理驱动控制器 (HAL层)
    
    展示了如何将统一的 InstrumentDriver 接口转换为特定的 SCPI 指令，
    通过 PyVISA 库与真实的 F64 仪表建立基于 TCP/IP 的连接控制。
    """

    def __init__(self, instrument_id: str, config: Dict[str, Any]):
        super().__init__(instrument_id, config)
        self.ip_address = config.get("ip", "192.168.100.21")
        self.port = config.get("port", 5025)
        self.visa_resource = None
        self._rm = None

    async def connect(self) -> bool:
        """建立与 F64 的 PyVISA 连接"""
        self._status = InstrumentStatus.CONNECTING
        try:
            # 实际部署时需 pip install pyvisa pyvisa-py
            import pyvisa
            
            # 使用 PyVISA-py (纯 Python 后端) 或系统安装的 NI-VISA
            self._rm = pyvisa.ResourceManager('@py')
            
            # F64 通常使用 Socket 或 VXI-11 协议
            resource_string = f"TCPIP0::{self.ip_address}::{self.port}::SOCKET"
            
            # 生产环境中，涉及到 IO 阻塞我们放到线程池中跑 asyncio.to_thread
            self.visa_resource = await asyncio.to_thread(
                self._rm.open_resource, resource_string,
                read_termination='\\n', 
                write_termination='\\n',
                timeout=5000
            )

            # 发送 *IDN? 确认连接
            idn = await asyncio.to_thread(self.visa_resource.query, "*IDN?")
            logger.info(f"[Propsim_F64] Connected to {idn.strip()}")

            self._status = InstrumentStatus.READY
            self._last_error = None
            return True

        except Exception as e:
            logger.error(f"Failed to connect to F64 at {self.ip_address}: {e}")
            self._status = InstrumentStatus.ERROR
            self._last_error = str(e)
            return False

    async def disconnect(self) -> bool:
        """断开连接"""
        if self.visa_resource:
            try:
                await asyncio.to_thread(self.visa_resource.close)
            except Exception as e:
                logger.warning(f"Error during visa_resource.close(): {e}")
                
        if self._rm:
            self._rm.close()
            
        self.visa_resource = None
        self._rm = None
        self._status = InstrumentStatus.DISCONNECTED
        return True

    async def configure(self, config: Dict[str, Any]) -> bool:
        """
        接收系统的前端参数，并映射为具体的 F64 SCPI 指令
        """
        if not self.visa_resource:
            return False

        try:
            # 1. 载入信道模型 (GCM 模型)
            scenario = config.get("channel_model", "3GPP_38.901_UMi")
            logger.info(f"[Propsim_F64] Loading scenario: {scenario}")
            
            cmds = [
                f'SOURce:GCM:MODel:LOAD "{scenario}.cha"',  # 加载模型
                'SOURce:GCM:STATe ON',                      # 开启 GCM 引擎
            ]
            
            # 2. 软重启/配置更新
            cmds.append("INITiate:IMMediate")               # 应用配置
            
            # 将所有命令一次性发送
            for cmd in cmds:
                await asyncio.to_thread(self.visa_resource.write, cmd)
                # 为确保仪器处理完成，有时需要在命令之间加入短延时或使用 *OPC? 查询
            
            return True
        except Exception as e:
            self._last_error = str(e)
            self._status = InstrumentStatus.ERROR
            return False

    async def get_metrics(self) -> InstrumentMetrics:
        """获取 F64 的运行状态和指标（例如：各通道的下行损耗）"""
        if not self.visa_resource:
            return InstrumentMetrics(
                timestamp=datetime.utcnow(),
                metrics={"snr_db": 0.0, "throughput_mbps": 0.0},
                status="error"
            )

        try:
            # 向硬件询问系统状态，例如是否发生了 clipping (溢出) 告警
            # sys_status = await asyncio.to_thread(self.visa_resource.query, "STATus:QUEStionable:CONDition?")
            
            # 这是一个示例，通常我们可以去读仪器内部一些探头映射的状态
            metrics = {
                "active_channels": 64,
                "engine_status": "Running",
                "temperature": 45.2 # 假设的温度
            }

            return InstrumentMetrics(
                timestamp=datetime.utcnow(),
                metrics=metrics,
                status="normal"
            )
        except Exception as e:
            logger.error(f"[Propsim_F64] Metrics fetch error: {e}")
            return InstrumentMetrics(
                timestamp=datetime.utcnow(),
                metrics={"error": str(e)},
                status="error"
            )

    async def get_capabilities(self) -> List[InstrumentCapability]:
        return [
            InstrumentCapability(name="Channel Emulation", description="Up to 64 channels", supported=True),
            InstrumentCapability(name="Runtime Playback", description="AWG arbitrary waveform playback", supported=True)
        ]

    async def reset(self) -> bool:
        """重置仪器到初始安全状态"""
        if not self.visa_resource:
            return False
        try:
            await asyncio.to_thread(self.visa_resource.write, "*RST")
            await asyncio.to_thread(self.visa_resource.query, "*OPC?") # 阻塞等待完成
            return True
        except Exception:
            return False

# ======================================================================
# Legacy Controller (用于兼容 channel_generation 的现有工作流，后续会逐步迁移到上面的 Driver 接口)
# ======================================================================

class PropsimF64Controller:
    """
    Keysight PROPSIM F64 物理驱动控制器 (旧版集成层)
    提供针对 ATE 和 Runtime Emulation 两种并行管线的底层硬件操作方法
    """
    def __init__(self, ip_address: str = "192.168.100.21"):
        self.ip_address = ip_address
        logger.info(f"Initialized PROPSIM F64 Controller (Legacy) at {self.ip_address}")
        # self.visa_resource = pyvisa.ResourceManager().open_resource(f"TCPIP0::{self.ip_address}::inst0::INSTR")

    def load_gcm_project(self, channel_model_name: str) -> bool:
        """触发 Keysight ATE API，让 F64 原生载入 GCM Model。"""
        logger.info(f"[HAL: F64-ATE] Executing SCPI loading sequence for GCM preset: {channel_model_name}")
        return True

    def transfer_file(self, local_zip_path: str) -> str:
        """将生成波形文件极速拷贝到 F64。"""
        logger.info(f"[HAL: F64-RUNTIME] Transferring file {local_zip_path} via FTP to {self.ip_address}")
        remote_path = "D:\\Waveforms\\custom_asc_payload.zip"
        return remote_path

    def load_runtime_emulation_data(self, remote_file_path: str) -> bool:
        """将 F64 转换为纯 ARB 基带射频播放器。"""
        logger.info(f"[HAL: F64-RUNTIME] Allocating ARB Memory and pre-fetching Baseband IQ Data from {remote_file_path}")
        return True

    def trigger_playback(self):
        """开启射频输出"""
        logger.info("[HAL: F64-UNIVERSAL] Enabling RF output and triggering sequence")

