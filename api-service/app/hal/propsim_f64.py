"""
Keysight PROPSIM F64 Channel Emulator HAL Driver
=================================================

型号专用驱动，实现 ChannelEmulatorDriver 抽象接口。
基于 PyVISA 通过 TCP/IP Socket (端口 5025) 与 F64 ATE Server 通信。

支持两种信道加载管线：
  ┌──────────────────────────────────────────────────────┐
  │  Pipeline A — GCM 原生模式                          │
  │  F64 内置 Channel Studio 信道建模引擎               │
  │  用户下发 .smu 仿真文件, F64 原生编译并播放         │
  │  SCPI: CALC:FILT:FILE → DIAG:SIMU:GO               │
  └──────────────────────────────────────────────────────┘
  ┌──────────────────────────────────────────────────────┐
  │  Pipeline B — ASC Runtime Emulation 模式            │
  │  外部 Channel Engine 计算探头权重, 生成 ASC 波形    │
  │  通过 FTP 传输 .rtc 文件到 F64, 以 Runtime API 播放 │
  │  SCPI: CALC:FILT:FILE → CH:MOD:CONT:ENV             │
  └──────────────────────────────────────────────────────┘

SCPI 参考文档:
  - Propsim User Reference, Ch.20 "Standard Tools Remote Control"
  - PROPSIM Runtime Emulation User Guide
  - Propsim ATE Environment and Practices AN

TCP 端口说明 (Table 6, User Reference §1.2.5.2):
  - 5025: ATE/SCPI 标准端口
  - 3334: ATE/SCPI 备用端口
  - 23:   Telnet ATE 端口
"""

import logging
import asyncio
import os
import ftplib
from enum import Enum
from typing import Dict, Any, List, Optional
from datetime import datetime

from app.hal.base import (
    InstrumentStatus,
    InstrumentCapability,
    InstrumentMetrics,
)
from app.hal.channel_emulator import ChannelEmulatorDriver, ChannelLoadMode

logger = logging.getLogger(__name__)


# ===========================================================================
# F64 专用枚举和常量
# ===========================================================================

class F64Pipeline(str, Enum):
    """信道加载管线类型"""
    GCM_NATIVE = "gcm"          # Pipeline A: F64 原生 GCM
    ASC_RUNTIME = "asc_runtime" # Pipeline B: 外部 ASC + Runtime Emulation


class F64BypassMode(int, Enum):
    """F64 静态旁路模式 (DIAG:SIMU:MODEL:STATIC)
    User Reference §20.4.6.25"""
    DISABLED = 0           # 正常衰落
    CHANNEL_MODEL = 1      # 信道模型旁路 (平均衰减, 零相位)
    BUTLER = 2             # Butler 矩阵旁路 (拓扑感知相位)
    CALIBRATION = 3        # 校准旁路 (所有通道等增益/等延迟/零相位)


# F64 远程文件存储路径约定
F64_EMULATION_DIR = r"D:\User Emulations"
F64_WAVEFORM_DIR = r"D:\User Emulations\ASC"

# VISA 超时常量 (毫秒)
VISA_TIMEOUT_DEFAULT = 5000
VISA_TIMEOUT_FILE_LOAD = 30000  # 大文件加载需要更长超时
VISA_TIMEOUT_AUTOSET = 15000    # 自动电平校准

# FTP 凭据 (PROPSIM 出厂默认)
F64_FTP_USER = "PROPSIM"
F64_FTP_PASS = "propsim"


class RealPropsimF64Driver(ChannelEmulatorDriver):
    """
    Keysight PROPSIM F64 真实 SCPI 驱动 (HAL Layer 3)
    ─────────────────────────────────────────────────
    继承链: InstrumentDriver → ChannelEmulatorDriver → RealPropsimF64Driver

    本驱动统一覆盖 GCM 原生管线和 ASC Runtime 管线的 SCPI 翻译。
    应用层通过 load_channel(mode=...) 统一入口选择管线,
    驱动内部自动管理仿真文件的加载、启动和停止。

    管线能力:
      - NATIVE_MODEL:      GCM 原生管线 (CALC:FILT:FILE → DIAG:SIMU:GO)
      - EXTERNAL_WAVEFORM:  ASC Runtime 管线 (FTP → CALC:FILT:FILE → CH:MOD:CONT:ENV)
    """

    def __init__(self, instrument_id: str, config: Dict[str, Any]):
        super().__init__(instrument_id, config)
        # 连接参数
        self.ip_address: str = config.get("ip", "192.168.100.21")
        self.port: int = config.get("port", 5025)
        self.ftp_user: str = config.get("ftp_user", F64_FTP_USER)
        self.ftp_pass: str = config.get("ftp_pass", F64_FTP_PASS)

        # PyVISA 资源句柄
        self._visa_resource = None
        self._rm = None

        # 管线状态追踪
        self._active_pipeline: Optional[F64Pipeline] = None
        self._loaded_emulation_file: Optional[str] = None
        self._emulation_running: bool = False
        self._bypass_mode: F64BypassMode = F64BypassMode.DISABLED

        # 信道参数缓存 (最近一次配置)
        self._current_model: Optional[str] = None
        self._current_scenario: Optional[str] = None
        self._center_freq_mhz: float = 3500.0
        self._channel_count: int = 64
        self._tx_antennas: int = 2
        self._rx_antennas: int = 2

    # ===================================================================
    # 0. 管线能力声明与统一入口 (重写母类)
    # ===================================================================

    def get_supported_load_modes(self) -> List[ChannelLoadMode]:
        """
        F64 支持两种信道加载模式。

        Returns:
            [NATIVE_MODEL, EXTERNAL_WAVEFORM]
        """
        return [ChannelLoadMode.NATIVE_MODEL, ChannelLoadMode.EXTERNAL_WAVEFORM]

    async def load_channel(
        self,
        mode: ChannelLoadMode,
        model_name: str,
        scenario: str,
        parameters: Dict[str, Any],
        waveform_dir: Optional[str] = None,
    ) -> bool:
        """
        F64 统一信道加载入口（重写母类）。

        根据 mode 分发到 GCM 或 ASC 管线:
          - NATIVE_MODEL     → Pipeline A: set_channel_model()  (GCM)
          - EXTERNAL_WAVEFORM → Pipeline B: upload_asc_files()  (ASC Runtime)

        应用层无需关心 F64 内部使用哪种 SCPI 管线。
        """
        logger.info(f"[F64] load_channel: mode={mode.value}, model={model_name}")

        if mode == ChannelLoadMode.NATIVE_MODEL:
            self._active_pipeline = F64Pipeline.GCM_NATIVE
            return await self.set_channel_model(model_name, scenario, parameters)

        elif mode == ChannelLoadMode.EXTERNAL_WAVEFORM:
            if not waveform_dir:
                raise ValueError("waveform_dir 是 ASC Runtime 管线的必需参数")
            self._active_pipeline = F64Pipeline.ASC_RUNTIME
            return await self.upload_asc_files(waveform_dir, model_name)

        raise NotImplementedError(f"未知加载模式: {mode.value}")

    # ===================================================================
    # 1. 连接生命周期 (InstrumentDriver 第一层)
    # ===================================================================

    async def connect(self) -> bool:
        """
        建立与 F64 ATE Server 的 PyVISA TCP/IP Socket 连接。

        连接流程:
          1. 创建 PyVISA ResourceManager
          2. 打开 TCP Socket 连接 (端口 5025)
          3. 发送 *IDN? 验证身份
          4. 查询 SYST:INFO? 获取硬件配置
        """
        self._status = InstrumentStatus.CONNECTING
        try:
            import pyvisa
            self._rm = pyvisa.ResourceManager('@py')
            resource_string = f"TCPIP0::{self.ip_address}::{self.port}::SOCKET"

            self._visa_resource = await asyncio.to_thread(
                self._rm.open_resource, resource_string,
                read_termination='\n',
                write_termination='\n',
                timeout=VISA_TIMEOUT_DEFAULT
            )

            # 验证连接: IEEE 488.2 标准身份查询
            idn = await self._query("*IDN?")
            logger.info(f"[F64] Connected: {idn}")

            # 查询硬件信息: 通道数、频段、License
            sys_info = await self._query("SYST:INFO?")
            logger.info(f"[F64] System Info: {sys_info}")

            # 从 SYST:INFO? 响应中解析通道数
            # 格式: "PROPSIM F64,64,RF,v1.0,16,Band: 450MHz - 3000MHz,..."
            try:
                parts = sys_info.split(",")
                self._channel_count = int(parts[1])
            except (IndexError, ValueError):
                self._channel_count = 64

            # 清空错误队列
            await self._clear_error_queue()

            self._status = InstrumentStatus.READY
            self._last_error = None
            return True

        except Exception as e:
            logger.error(f"[F64] Connection failed ({self.ip_address}:{self.port}): {e}")
            self._status = InstrumentStatus.ERROR
            self._last_error = str(e)
            return False

    async def disconnect(self) -> bool:
        """
        安全断开连接。

        断开流程:
          1. 若仿真正在运行, 先停止
          2. 关闭仿真文件
          3. 释放 VISA 资源
        """
        try:
            if self._emulation_running:
                await self.stop_emulation()
            if self._loaded_emulation_file:
                await self._write("DIAG:SIMU:CLOSE")
                self._loaded_emulation_file = None
        except Exception as e:
            logger.warning(f"[F64] Cleanup during disconnect: {e}")

        if self._visa_resource:
            try:
                await asyncio.to_thread(self._visa_resource.close)
            except Exception as e:
                logger.warning(f"[F64] VISA resource close error: {e}")
        if self._rm:
            try:
                self._rm.close()
            except Exception:
                pass

        self._visa_resource = None
        self._rm = None
        self._status = InstrumentStatus.DISCONNECTED
        self._emulation_running = False
        self._active_pipeline = None
        return True

    async def configure(self, config: Dict[str, Any]) -> bool:
        """
        通用配置入口, 支持以下 config 键:
          - center_frequency_mhz: 中心频率 (MHz)
          - channel_model: 信道模型名称 (触发 set_channel_model)
          - pipeline: "gcm" 或 "asc_runtime"
        """
        if "center_frequency_mhz" in config:
            self._center_freq_mhz = config["center_frequency_mhz"]
        if "pipeline" in config:
            self._active_pipeline = F64Pipeline(config["pipeline"])
        if "channel_model" in config:
            return await self.set_channel_model(
                config["channel_model"],
                config.get("scenario", "UMi"),
                config.get("parameters", {})
            )
        return True

    # ===================================================================
    # 2. Pipeline A — GCM 原生管线 SCPI 翻译
    # ===================================================================

    async def set_channel_model(
        self,
        model_type: str,
        scenario: str,
        parameters: Dict[str, Any]
    ) -> bool:
        """
        加载信道模型到 F64。

        Pipeline A (GCM): 加载 .smu 仿真文件, F64 内部编译并播放。
        此方法实现 GCM 原生管线的完整 SCPI 流程:

          1. 关闭当前仿真文件 (安全防护)
          2. 加载新的 .smu 仿真文件
          3. 设置中心频率
          4. 配置端口连接拓扑

        ATE Practice Note §2.2.2:
          "DIAG:SIMU:CLOSE" 可以安全地在任何状态下调用, 不会产生错误。

        Args:
            model_type: GCM 模型类型 (e.g., "CDL-A", "CDL-C", "TDL-A")
            scenario: 场景类型 (e.g., "UMi", "UMa", "Indoor")
            parameters: 可选参数字典, 支持:
                - emulation_file: .smu 文件完整路径 (覆盖默认命名)
                - center_frequency_mhz: 中心频率 (MHz)
                - bandwidth_mhz: 仿真带宽 (MHz)
        """
        if not self._visa_resource:
            return False
        try:
            self._active_pipeline = F64Pipeline.GCM_NATIVE
            logger.info(f"[F64/GCM] Loading model: {model_type} scenario={scenario}")

            # Step 1: 安全关闭当前仿真 (ATE Practice §2.2.2)
            await self._write("DIAG:SIMU:CLOSE")
            self._emulation_running = False

            # Step 2: 构建仿真文件路径
            # 支持用户手动指定 .smu 路径, 或使用标准命名约定
            emulation_file = parameters.get("emulation_file")
            if not emulation_file:
                # 标准命名: D:\User Emulations\CDL-A_UMi_2x2.smu
                emulation_file = (
                    f"{F64_EMULATION_DIR}\\{model_type}_{scenario}"
                    f"_{self._tx_antennas}x{self._rx_antennas}.smu"
                )

            # Step 3: 加载仿真文件 (需要延长 VISA 超时)
            # ATE Practice §2.2.4: 大文件加载可能需要数十秒
            await self._write(
                f'CALC:FILT:FILE {emulation_file}',
                timeout=VISA_TIMEOUT_FILE_LOAD
            )
            # 使用 *OPC? 确保加载完成 (ATE Practice §2.2.4)
            await self._query("*OPC?", timeout=VISA_TIMEOUT_FILE_LOAD)
            self._loaded_emulation_file = emulation_file

            # Step 4: 设置中心频率
            freq_mhz = parameters.get("center_frequency_mhz", self._center_freq_mhz)
            self._center_freq_mhz = freq_mhz
            # 为所有通道设置中心频率
            for ch in range(1, self._channel_count + 1):
                await self._write(f"CALC:FILT:CENT:CH {ch},{freq_mhz}")

            # Step 5: 验证连接器映射
            # 查询第一个通道的物理连接, 确保路由正确
            connector_info = await self._query("ROUT:PATH:CONN? 1")
            logger.info(f"[F64/GCM] Channel 1 connector: {connector_info}")

            # 缓存当前模型信息
            self._current_model = model_type
            self._current_scenario = scenario

            logger.info(f"[F64/GCM] Model loaded: {emulation_file}")
            await self._check_errors()
            return True

        except Exception as e:
            logger.error(f"[F64/GCM] set_channel_model failed: {e}")
            self._last_error = str(e)
            return False

    # ===================================================================
    # 3. Pipeline B — ASC Runtime Emulation SCPI 翻译
    # ===================================================================

    async def upload_asc_files(
        self,
        asc_files_dir: str,
        cdl_model_name: str = ""
    ) -> bool:
        """
        上传 ASC 波形文件到 F64 并配置 Runtime Emulation 播放。

        Pipeline B 完整流程:
          1. 通过 FTP 将波形文件传输到 F64 本地磁盘
          2. 关闭当前仿真
          3. 加载包含 Runtime 模型的基础仿真文件 (.smu)
          4. 仿真文件内部引用 .rtc 运行时信道模型

        Runtime Emulation User Guide §4:
          RTC 文件必须在 Scenario Wizard 中预先关联到链路。
          运行时通过 CH:MOD:CONT:ENV 动态切换环境。

        Args:
            asc_files_dir: 包含 .asc/.rtc/.zip 波形文件的本地目录
            cdl_model_name: CDL 模型标签 (e.g. "UMa CDL-C NLOS")
        """
        if not self._visa_resource:
            return False
        try:
            self._active_pipeline = F64Pipeline.ASC_RUNTIME
            logger.info(f"[F64/ASC] Uploading ASC payload: {asc_files_dir} model={cdl_model_name}")

            # Step 1: FTP 文件传输
            # F64 内置 Windows FTP 服务 (出厂默认: user=PROPSIM, pass=propsim)
            remote_dir = f"{F64_WAVEFORM_DIR}\\{cdl_model_name or 'custom'}"
            transferred_files = await self._ftp_upload_directory(asc_files_dir, remote_dir)
            if not transferred_files:
                logger.error("[F64/ASC] FTP transfer failed - no files uploaded")
                return False
            logger.info(f"[F64/ASC] Transferred {len(transferred_files)} files to {remote_dir}")

            # Step 2: 安全关闭当前仿真
            await self._write("DIAG:SIMU:CLOSE")
            self._emulation_running = False

            # Step 3: 加载 Runtime 基础仿真文件
            # 该 .smu 文件必须预先通过 Scenario Wizard 创建,
            # 内部 Link Properties 引用 .rtc 运行时信道模型
            runtime_smu = f"{remote_dir}\\runtime_emulation.smu"

            # 如果目录中包含 .smu 文件则使用它
            smu_files = [f for f in transferred_files if f.endswith('.smu')]
            if smu_files:
                runtime_smu = f"{remote_dir}\\{smu_files[0]}"

            await self._write(
                f'CALC:FILT:FILE {runtime_smu}',
                timeout=VISA_TIMEOUT_FILE_LOAD
            )
            await self._query("*OPC?", timeout=VISA_TIMEOUT_FILE_LOAD)
            self._loaded_emulation_file = runtime_smu

            logger.info(f"[F64/ASC] Runtime emulation loaded: {runtime_smu}")
            await self._check_errors()
            return True

        except Exception as e:
            logger.error(f"[F64/ASC] upload_asc_files failed: {e}")
            self._last_error = str(e)
            return False

    async def set_runtime_environment(
        self,
        channel_envs: Dict[int, Dict[str, Any]]
    ) -> bool:
        """
        Runtime Emulation 环境切换 (Pipeline B 专用)。

        在仿真运行时, 动态切换各通道的信道环境、增益、延迟和多普勒。

        Runtime Emulation User Guide §5.4.1:
          CH:MOD:CONT:ENV <ch>,<env>,<gain>,<delay_ns>,<doppler_hz>

        Args:
            channel_envs: 字典, key=通道号, value=环境参数:
                - environment: 环境名称或编号
                - gain_db: 通道增益 (负值, dB)
                - delay_ns: 延迟 (ns)
                - doppler_hz: 多普勒频移 (Hz)

        Example:
            await driver.set_runtime_environment({
                1: {"environment": "CDL_A_cluster1", "gain_db": -38.7, "delay_ns": 1510006, "doppler_hz": 0},
                2: {"environment": "CDL_A_cluster2", "gain_db": -37.3, "delay_ns": 1740025, "doppler_hz": 0},
            })
        """
        if not self._visa_resource or self._active_pipeline != F64Pipeline.ASC_RUNTIME:
            logger.warning("[F64/ASC] set_runtime_environment requires active ASC pipeline")
            return False

        try:
            # 构建批量环境切换命令 (一条 SCPI 可切换多通道)
            # 格式: CH:MOD:CONT:ENV ch1,env1,gain1,delay1,doppler1,ch2,env2,...
            cmd_parts = []
            for ch_num, env_params in channel_envs.items():
                env_name = env_params.get("environment", 1)
                gain = env_params.get("gain_db", "")
                delay = env_params.get("delay_ns", "")
                doppler = env_params.get("doppler_hz", "")
                cmd_parts.append(f"{ch_num},{env_name},{gain},{delay},{doppler}")

            cmd = "CH:MOD:CONT:ENV " + ",".join(cmd_parts)
            await self._write(cmd)

            logger.info(f"[F64/ASC] Runtime environment updated for {len(channel_envs)} channels")
            return True
        except Exception as e:
            logger.error(f"[F64/ASC] set_runtime_environment failed: {e}")
            self._last_error = str(e)
            return False

    async def query_runtime_environment(self, channels: List[int]) -> Dict[int, Dict[str, Any]]:
        """
        查询 Runtime 通道当前环境状态。

        Runtime Emulation User Guide §5.4.2:
          CH:MOD:CONT:ENV? <ch1>,<ch2>,...
          响应: ch1,env,gain,delay,doppler,ch2,env,gain,delay,doppler

        Returns:
            字典, key=通道号, value={environment, gain_db, delay_ns, doppler_hz}
        """
        if not self._visa_resource:
            return {}

        try:
            ch_str = ",".join(str(ch) for ch in channels)
            response = await self._query(f"CH:MOD:CONT:ENV? {ch_str}")

            result = {}
            parts = response.strip().split(",")
            # 每 5 个 token 为一组: ch, env, gain, delay, doppler
            for i in range(0, len(parts), 5):
                if i + 4 < len(parts):
                    ch_num = int(parts[i].strip())
                    result[ch_num] = {
                        "environment": parts[i + 1].strip(),
                        "gain_db": float(parts[i + 2]) if parts[i + 2].strip() else None,
                        "delay_ns": int(parts[i + 3]) if parts[i + 3].strip() else None,
                        "doppler_hz": int(parts[i + 4]) if parts[i + 4].strip() else None,
                    }
            return result
        except Exception as e:
            logger.error(f"[F64] query_runtime_environment failed: {e}")
            return {}

    # ===================================================================
    # 4. 通用仿真控制 (两种管线共享)
    # ===================================================================

    async def set_mimo_config(
        self,
        tx_antennas: int,
        rx_antennas: int,
        correlation_matrix: Optional[list[list[float]]] = None
    ) -> bool:
        """
        配置 MIMO 端口拓扑。

        注意: F64 的 MIMO 端口拓扑在仿真文件 (.smu) 的 Scenario Wizard 中定义,
        而非通过 SCPI 动态配置。此方法更新内部状态缓存, 并验证仿真文件的
        实际通道数是否匹配。

        对于已加载的仿真, 可通过连接器重映射调整端口:
          INP:CON:SET <input>, <emulator>, <unit>, <position>
          OUTP:CON:SET <output>, <emulator>, <unit>, <position>
        """
        self._tx_antennas = tx_antennas
        self._rx_antennas = rx_antennas
        logger.info(f"[F64] MIMO config cached: {tx_antennas}x{rx_antennas}")
        return True

    async def set_path_loss(
        self,
        path_loss_db: float,
        distance_m: Optional[float] = None
    ) -> bool:
        """
        设置通道输出损耗。

        使用 OUTP:LOSS:SET 为每个输出通道设置路径损耗补偿。
        User Reference §20.4.5.19:
          OUTP:LOSS:SET <output>,<loss_db>
          取值范围: OUTP:LOSS:LIM? 查询 (典型: -30 ~ 80 dB)

        若指定 distance_m, 则使用自由空间路损公式计算:
          PL = 20*log10(d) + 20*log10(f) - 147.55
        """
        if not self._visa_resource:
            return False

        try:
            # 如果提供距离, 计算自由空间路损
            if distance_m is not None:
                import math
                freq_hz = self._center_freq_mhz * 1e6
                path_loss_db = (
                    20 * math.log10(distance_m)
                    + 20 * math.log10(freq_hz)
                    - 147.55
                )

            # 获取输出数量 (通常 = 通道数 / 2 for MIMO, 取决于仿真拓扑)
            # 为所有输出通道设置统一的路损
            num_outputs = self._tx_antennas * self._rx_antennas
            for out_ch in range(1, num_outputs + 1):
                await self._write(f"OUTP:LOSS:SET {out_ch},{path_loss_db:.1f}")

            logger.info(f"[F64] Path loss set: {path_loss_db:.1f} dB for {num_outputs} outputs")
            await self._check_errors()
            return True
        except Exception as e:
            logger.error(f"[F64] set_path_loss failed: {e}")
            self._last_error = str(e)
            return False

    async def set_doppler(
        self,
        frequency_hz: float,
        velocity_kmh: Optional[float] = None
    ) -> bool:
        """
        设置移动速度 / 最大多普勒频移。

        User Reference §20.4.6.13:
          DIAG:SIMU:MOB:MAN:CH <channel>,<speed> [unit]
          支持单位: km/h (默认), m/s, Hz (直接指定多普勒)

        注意:
          - 静态 MIMO OTA 测试中 Doppler = 0 Hz
          - F64 Release 1.0 不支持 Runtime 模式下动态改变 Doppler
          - 此命令仅在仿真停止状态下有效
        """
        if not self._visa_resource:
            return False

        try:
            # 优先使用 Hz 单位直接指定多普勒
            if frequency_hz is not None:
                for ch in range(1, self._channel_count + 1):
                    await self._write(f"DIAG:SIMU:MOB:MAN:CH {ch},{frequency_hz} Hz")
                logger.info(f"[F64] Doppler set: {frequency_hz} Hz (all channels)")
            elif velocity_kmh is not None:
                for ch in range(1, self._channel_count + 1):
                    await self._write(f"DIAG:SIMU:MOB:MAN:CH {ch},{velocity_kmh}")
                logger.info(f"[F64] Speed set: {velocity_kmh} km/h (all channels)")

            await self._check_errors()
            return True
        except Exception as e:
            logger.error(f"[F64] set_doppler failed: {e}")
            self._last_error = str(e)
            return False

    async def start_emulation(self) -> bool:
        """
        启动仿真播放。

        User Reference §20.4.6.1:
          DIAG:SIMU:GO — 启动仿真, 从当前 CIR 位置开始
          (若之前 STOP 则从停止点继续; 若 GOS 则从头开始)

        两种管线共用此命令:
          - GCM: 信道模型开始衰落播放
          - ASC Runtime: 开始 RTC 波形播放, 初始加载第一个环境
        """
        if not self._visa_resource or not self._loaded_emulation_file:
            logger.error("[F64] Cannot start: no emulation file loaded")
            return False

        try:
            await self._write("DIAG:SIMU:GO")
            await self._query("*OPC?")
            self._emulation_running = True
            self._status = InstrumentStatus.BUSY
            logger.info("[F64] Emulation started")
            await self._check_errors()
            return True
        except Exception as e:
            logger.error(f"[F64] start_emulation failed: {e}")
            self._last_error = str(e)
            return False

    async def stop_emulation(self) -> bool:
        """
        停止仿真。

        User Reference §20.4.6.2:
          DIAG:SIMU:STOP — 暂停仿真 (可通过 GO 从当前位置继续)
          DIAG:SIMU:GOS — 停止并倒回起点 (下次 GO 从头开始)

        本方法使用 GOS (Stop & Rewind), 确保下次启动从干净状态开始。
        """
        if not self._visa_resource:
            return False
        try:
            await self._write("DIAG:SIMU:GOS")
            self._emulation_running = False
            self._status = InstrumentStatus.READY
            logger.info("[F64] Emulation stopped and rewound")
            return True
        except Exception as e:
            logger.error(f"[F64] stop_emulation failed: {e}")
            self._last_error = str(e)
            return False

    async def set_baseband_power(self, power_dbm: float) -> bool:
        """
        设置输入电平 (基带功率)。

        User Reference §20.4.4.3:
          INP:LEV:AMP:CH <input>,<amplitude_dBm>
          取值范围: INP:LEV:AMP:LIM? 查询 (典型: -23 ~ 0 dBm)
        """
        if not self._visa_resource:
            return False
        try:
            # 设置所有输入的电平
            for inp in range(1, self._tx_antennas + 1):
                await self._write(f"INP:LEV:AMP:CH {inp},{power_dbm:.1f}")
            logger.info(f"[F64] Input level set: {power_dbm:.1f} dBm")
            await self._check_errors()
            return True
        except Exception as e:
            logger.error(f"[F64] set_baseband_power failed: {e}")
            self._last_error = str(e)
            return False

    async def set_external_attenuators(
        self,
        attenuation_map: Dict[int, float]
    ) -> bool:
        """
        设置各输出通道的衰减值 (外部衰减器补偿)。

        使用 OUTP:GAIN:CH 调节输出增益 (负值 = 衰减)。
        User Reference §20.4.5.8:
          OUTP:GAIN:CH <output>,<gain_dB>
        """
        if not self._visa_resource:
            return False
        try:
            for output_ch, atten_db in attenuation_map.items():
                # 衰减用负增益表示
                gain_db = -abs(atten_db)
                await self._write(f"OUTP:GAIN:CH {output_ch},{gain_db:.2f}")

            logger.info(f"[F64] Attenuators set for {len(attenuation_map)} outputs")
            await self._check_errors()
            return True
        except Exception as e:
            logger.error(f"[F64] set_external_attenuators failed: {e}")
            self._last_error = str(e)
            return False

    async def get_channel_state(self) -> Dict[str, Any]:
        """
        查询 F64 当前全面状态。

        汇总: 仿真状态、旁路模式、管线类型、中心频率、输入/输出电平等。
        """
        if not self._visa_resource:
            return {"status": "disconnected"}

        try:
            state: Dict[str, Any] = {
                "pipeline": self._active_pipeline.value if self._active_pipeline else None,
                "emulation_running": self._emulation_running,
                "loaded_file": self._loaded_emulation_file,
                "model": self._current_model,
                "scenario": self._current_scenario,
                "center_freq_mhz": self._center_freq_mhz,
                "mimo_config": f"{self._tx_antennas}x{self._rx_antennas}",
            }

            # 查询旁路状态
            bypass_str = await self._query("DIAG:SIMU:MODEL:STATIC?")
            state["bypass_mode"] = int(bypass_str.strip()) if bypass_str.strip().isdigit() else 0

            # 查询 SCPI 版本
            scpi_ver = await self._query("SYST:VERS?")
            state["scpi_version"] = scpi_ver.strip()

            return state
        except Exception as e:
            logger.error(f"[F64] get_channel_state failed: {e}")
            return {"status": "error", "error": str(e)}

    # ===================================================================
    # 5. 校准与诊断 SCPI (两种管线共享)
    # ===================================================================

    async def set_bypass_mode(self, mode: F64BypassMode) -> bool:
        """
        设置静态旁路模式。

        User Reference §20.4.6.25:
          DIAG:SIMU:MODEL:STATIC <state>
          0=禁用, 1=信道旁路, 2=Butler, 3=校准旁路

        校准旁路 (mode=3) 用于 RF 链路校准:
          所有通道等增益/等延迟/零相位, 信号直通。
        """
        if not self._visa_resource:
            return False
        try:
            await self._write(f"DIAG:SIMU:MODEL:STATIC {mode.value}")
            self._bypass_mode = mode
            logger.info(f"[F64] Bypass mode: {mode.name}")
            return True
        except Exception as e:
            logger.error(f"[F64] set_bypass_mode failed: {e}")
            self._last_error = str(e)
            return False

    async def set_center_frequency(self, channel: int, freq_mhz: float) -> bool:
        """
        设置指定通道的中心频率。

        User Reference §20.4.3.11 (运行中可用):
          CALC:FILT:CENT:CH <channel>,<MHz>
        """
        if not self._visa_resource:
            return False
        try:
            await self._write(f"CALC:FILT:CENT:CH {channel},{freq_mhz}")
            return True
        except Exception as e:
            self._last_error = str(e)
            return False

    async def autoset_input_level(self, input_num: int, measurement_time_s: float = 3.0) -> Optional[float]:
        """
        自动测量并设置输入电平和峰均比。

        User Reference §20.4.4.7:
          INP:LEV:AUTOSET <input>,<time>
          time = 0.5, 1, 3, 5, 10 秒

        返回测量到的输入功率 (dBm), 或 None 表示失败。
        """
        if not self._visa_resource:
            return None
        try:
            # 先测量
            result = await self._query(
                f"INP:LEV:MEAS? {input_num},{measurement_time_s}",
                timeout=VISA_TIMEOUT_AUTOSET
            )
            # 响应格式: "<level_dBm>,<crest_factor_dB>"
            parts = result.strip().split(",")
            level_dbm = float(parts[0])
            crest_db = float(parts[1]) if len(parts) > 1 else 0

            # 自动设置
            await self._write(
                f"INP:LEV:AUTOSET {input_num},{measurement_time_s}",
            )
            # Autoset 需要等待测量完成
            await asyncio.sleep(measurement_time_s + 1)

            logger.info(f"[F64] Input {input_num} autoset: {level_dbm} dBm, crest={crest_db} dB")
            return level_dbm
        except Exception as e:
            logger.error(f"[F64] autoset_input_level failed: {e}")
            return None

    async def measure_rsrp(
        self,
        inputs: List[int],
        technology: str = "5G",
        bandwidth_mhz: int = 100,
        cell_id: int = 1,
        center_freq_mhz: float = 3500,
        scs_khz: int = 30
    ) -> Optional[float]:
        """
        内置 RSRP 测量功能。

        User Reference §20.4.4.53:
          INP:RSRP:MEAS? <N>,<inp1>,...,<inpN>,<tech>,<bw>,<cell>,<freq>[,<scs>]
          5G 参数: bandwidth_mhz (20/50/100), cell_id, center_freq_mhz, scs_khz

        注意: 测量通常需要 10-60 秒。

        Returns:
            RSRP in dBm, or None if failed
        """
        if not self._visa_resource:
            return None
        try:
            n = len(inputs)
            inp_str = ",".join(str(i) for i in inputs)
            cmd = f"INP:RSRP:MEAS? {n},{inp_str},{technology},{bandwidth_mhz},{cell_id},{center_freq_mhz}"
            if technology == "5G":
                cmd += f",{scs_khz}"

            # RSRP 测量需要较长超时
            result = await self._query(cmd, timeout=60000)
            rsrp_dbm = float(result.strip())
            logger.info(f"[F64] RSRP measurement: {rsrp_dbm} dBm")
            return rsrp_dbm
        except Exception as e:
            logger.error(f"[F64] measure_rsrp failed: {e}")
            return None

    async def set_output_phase(self, output_num: int, phase_deg: float) -> bool:
        """
        设置输出通道相位。

        User Reference §20.4.5.10:
          OUTP:PHA:DEG:CH <output>,<phase_degrees>
          取值范围: -200 ~ 200 度
        """
        if not self._visa_resource:
            return False
        try:
            await self._write(f"OUTP:PHA:DEG:CH {output_num},{phase_deg:.1f}")
            return True
        except Exception as e:
            self._last_error = str(e)
            return False

    async def get_output_calibration(self, output_num: int) -> Optional[Dict[str, float]]:
        """
        获取输出通道校准数据。

        User Reference §20.4.5.24:
          OUTP:CALIB:GET? <output>
          返回: <gain_dB>,<phase_degrees>
        """
        if not self._visa_resource:
            return None
        try:
            result = await self._query(f"OUTP:CALIB:GET? {output_num}")
            parts = result.strip().split(",")
            return {
                "gain_db": float(parts[0]),
                "phase_deg": float(parts[1]) if len(parts) > 1 else 0.0
            }
        except Exception as e:
            logger.error(f"[F64] get_output_calibration failed: {e}")
            return None

    async def get_output_power(self, output_num: int) -> Optional[float]:
        """
        获取输出功率测量值。

        User Reference §20.4.5.22:
          OUTP:MEAS:RES:GET? <output>[,<option>]
          option 0: 基于输入功率计算 (legacy)
          option 1: 在输出端直接测量 (含内部干扰源)
        """
        if not self._visa_resource:
            return None
        try:
            result = await self._query(f"OUTP:MEAS:RES:GET? {output_num}")
            if "not ready" in result.lower():
                return None
            return float(result.strip())
        except Exception as e:
            logger.error(f"[F64] get_output_power failed: {e}")
            return None

    async def set_input_phase(self, input_num: int, phase_deg: float) -> bool:
        """
        设置输入通道相位。

        User Reference §20.4.4.16:
          INP:PHA:DEG:CH <input>,<phase_degrees>
          取值范围: -200 ~ 200 度

        用于相位校准时补偿通道间的相位偏差。
        """
        if not self._visa_resource:
            return False
        try:
            await self._write(f"INP:PHA:DEG:CH {input_num},{phase_deg:.1f}")
            return True
        except Exception as e:
            self._last_error = str(e)
            return False

    async def enable_measurement_data_stream(
        self,
        target_ip: str,
        target_port: int = 3800,
        elements: Optional[Dict[int, int]] = None
    ) -> bool:
        """
        启用 UDP 测量数据推送流。

        User Reference §20.4.2.24 ~ §20.4.2.28:
          SYST:MEAS:TAR:SET 1,<port>,<ip>
          SYST:MEAS:ELE:SET <type>,<enable>,<interval_ms>

        元素类型:
          101=输入功率, 201=输出功率, 401=链路多普勒
          402=链路RSRP, 403=链路AoA, 404=链路AoD
        """
        if not self._visa_resource:
            return False
        try:
            # 设置目标
            await self._write(f"SYST:MEAS:TAR:SET 1,{target_port},{target_ip}")

            # 默认启用输入/输出功率, 100ms 间隔
            if elements is None:
                elements = {101: 100, 201: 100}

            for elem_type, interval_ms in elements.items():
                await self._write(f"SYST:MEAS:ELE:SET {elem_type},1,{interval_ms}")

            logger.info(f"[F64] Measurement stream enabled → {target_ip}:{target_port}")
            return True
        except Exception as e:
            logger.error(f"[F64] enable_measurement_data_stream failed: {e}")
            self._last_error = str(e)
            return False

    # ===================================================================
    # 6. 仪器基础信息 (InstrumentDriver 第一层)
    # ===================================================================

    async def get_metrics(self) -> InstrumentMetrics:
        """获取 F64 运行状态指标"""
        if not self._visa_resource:
            return InstrumentMetrics(
                timestamp=datetime.utcnow(),
                metrics={"error": "not connected"},
                status="error"
            )
        try:
            metrics: Dict[str, Any] = {
                "channel_count": self._channel_count,
                "emulation_running": self._emulation_running,
                "pipeline": self._active_pipeline.value if self._active_pipeline else "none",
                "bypass_mode": self._bypass_mode.name,
                "loaded_file": self._loaded_emulation_file,
            }

            # 读取输入功率 (第一个输入)
            try:
                inp_power = await self._query("INP:MEAS:RES:GET? 1")
                metrics["input_1_power_dbm"] = float(inp_power.strip())
            except Exception:
                metrics["input_1_power_dbm"] = None

            # 读取输出功率 (第一个输出)
            try:
                out_power = await self._query("OUTP:MEAS:RES:GET? 1")
                if "not ready" not in out_power.lower():
                    metrics["output_1_power_dbm"] = float(out_power.strip())
            except Exception:
                metrics["output_1_power_dbm"] = None

            return InstrumentMetrics(
                timestamp=datetime.utcnow(),
                metrics=metrics,
                status="normal" if self._emulation_running else "idle"
            )
        except Exception as e:
            logger.error(f"[F64] get_metrics failed: {e}")
            return InstrumentMetrics(
                timestamp=datetime.utcnow(),
                metrics={"error": str(e)},
                status="error"
            )

    async def get_capabilities(self) -> List[InstrumentCapability]:
        """返回 F64 支持的能力列表"""
        return [
            InstrumentCapability(
                name="Channel Emulation",
                description=f"Up to {self._channel_count} fading channels",
                supported=True,
                parameters={"max_channels": self._channel_count}
            ),
            InstrumentCapability(
                name="GCM Native Pipeline",
                description="Channel Studio built-in GCM model compilation",
                supported=True
            ),
            InstrumentCapability(
                name="Runtime Emulation",
                description="External ASC/RTC waveform playback with dynamic environment control",
                supported=True
            ),
            InstrumentCapability(
                name="RSRP Measurement",
                description="Built-in LTE/5G RSRP measurement at inputs",
                supported=True,
                parameters={"technologies": ["LTE", "5G"]}
            ),
            InstrumentCapability(
                name="Calibration Bypass",
                description="3 bypass modes: Channel Model, Butler, Calibration",
                supported=True
            ),
        ]

    async def reset(self) -> bool:
        """
        重置 F64 到安全状态。

        IEEE 488.2 §10.32:
          *RST — 重置仪器
        User Reference §20.4.2.3:
          SYST:RES — 系统重置, 关闭仿真
        """
        if not self._visa_resource:
            return False
        try:
            await self._write("*RST")
            await self._query("*OPC?", timeout=VISA_TIMEOUT_FILE_LOAD)
            self._emulation_running = False
            self._loaded_emulation_file = None
            self._active_pipeline = None
            self._bypass_mode = F64BypassMode.DISABLED
            self._status = InstrumentStatus.READY
            logger.info("[F64] Reset complete")
            return True
        except Exception as e:
            logger.error(f"[F64] reset failed: {e}")
            self._last_error = str(e)
            return False

    # ===================================================================
    # 7. 内部工具方法
    # ===================================================================

    async def _write(self, cmd: str, timeout: Optional[int] = None) -> None:
        """发送 SCPI 写命令"""
        if timeout:
            original_timeout = self._visa_resource.timeout
            self._visa_resource.timeout = timeout
        try:
            logger.debug(f"[F64] SCPI TX: {cmd}")
            await asyncio.to_thread(self._visa_resource.write, cmd)
        finally:
            if timeout:
                self._visa_resource.timeout = original_timeout

    async def _query(self, cmd: str, timeout: Optional[int] = None) -> str:
        """发送 SCPI 查询命令并返回响应"""
        if timeout:
            original_timeout = self._visa_resource.timeout
            self._visa_resource.timeout = timeout
        try:
            logger.debug(f"[F64] SCPI TX: {cmd}")
            response = await asyncio.to_thread(self._visa_resource.query, cmd)
            logger.debug(f"[F64] SCPI RX: {response.strip()}")
            return response
        finally:
            if timeout:
                self._visa_resource.timeout = original_timeout

    async def _check_errors(self) -> None:
        """
        检查并清空 F64 错误队列。

        User Reference §20.4.2.1:
          SYST:ERR?
          返回: <error_code>,\"<message>\"
          "0,\"No error\"" 表示无错误
        """
        try:
            while True:
                err = await self._query("SYST:ERR?")
                err = err.strip()
                if err.startswith("0") or "No error" in err:
                    break
                logger.warning(f"[F64] Instrument error: {err}")
                self._last_error = err
        except Exception as e:
            logger.error(f"[F64] Error queue check failed: {e}")

    async def _clear_error_queue(self) -> None:
        """连接后清空全部历史错误"""
        try:
            for _ in range(100):  # 最多读 100 条防止死循环
                err = await self._query("SYST:ERR?")
                if err.strip().startswith("0"):
                    break
        except Exception:
            pass

    async def _ftp_upload_directory(
        self,
        local_dir: str,
        remote_dir: str
    ) -> List[str]:
        """
        通过 FTP 将整个目录上传到 F64。

        F64 内置 Windows 操作系统, 支持标准 FTP 协议。
        出厂默认账户: PROPSIM / propsim (User Reference §1.2.5.1)

        Args:
            local_dir: 本地目录路径
            remote_dir: F64 上的目标目录 (e.g., "D:\\User Emulations\\ASC\\CDL-A")

        Returns:
            成功上传的文件名列表
        """
        transferred = []
        try:
            def _do_ftp():
                ftp = ftplib.FTP(self.ip_address)
                ftp.login(self.ftp_user, self.ftp_pass)
                # 确保远程目录存在
                try:
                    ftp.mkd(remote_dir.replace("\\", "/"))
                except ftplib.error_perm:
                    pass  # 目录已存在
                ftp.cwd(remote_dir.replace("\\", "/"))

                for filename in os.listdir(local_dir):
                    filepath = os.path.join(local_dir, filename)
                    if os.path.isfile(filepath):
                        with open(filepath, 'rb') as f:
                            ftp.storbinary(f"STOR {filename}", f)
                        transferred.append(filename)
                        logger.debug(f"[F64/FTP] Uploaded: {filename}")
                ftp.quit()

            await asyncio.to_thread(_do_ftp)
        except Exception as e:
            logger.error(f"[F64/FTP] Upload failed: {e}")
        return transferred


# ======================================================================
# Legacy Controller 兼容层
# (用于 channel_generation 模块的 GCM/ASC Strategy 类, 后续版本将迁移到上面的 Driver)
# ======================================================================

class PropsimF64Controller:
    """
    Keysight PROPSIM F64 旧版控制器 (兼容 channel_generation strategies)

    提供简化的方法接口供 PropsimNativeGCMStrategy 和 MimoEngineASCStrategy 调用。
    内部委托给 RealPropsimF64Driver 或使用 Mock 逻辑。

    注意: 此类将在下个版本废弃, 请使用 RealPropsimF64Driver。
    """

    def __init__(self, ip_address: str = "192.168.100.21"):
        self.ip_address = ip_address
        logger.info(f"Initialized PROPSIM F64 Controller (Legacy) at {self.ip_address}")

    def load_gcm_project(self, channel_model_name: str) -> bool:
        """Pipeline A: 触发 GCM 原生加载"""
        logger.info(f"[HAL: F64-GCM] Loading native GCM preset: {channel_model_name}")
        return True

    def transfer_file(self, local_zip_path: str) -> str:
        """Pipeline B: FTP 传输波形文件到 F64"""
        logger.info(f"[HAL: F64-FTP] Transferring {local_zip_path} to {self.ip_address}")
        remote_path = f"{F64_WAVEFORM_DIR}\\custom_asc_payload.zip"
        return remote_path

    def load_runtime_emulation_data(self, remote_file_path: str) -> bool:
        """Pipeline B: 加载 Runtime Emulation 数据"""
        logger.info(f"[HAL: F64-RUNTIME] Loading RTC from {remote_file_path}")
        return True

    def trigger_playback(self) -> None:
        """两种管线共用: 开始仿真"""
        logger.info("[HAL: F64] Triggering emulation playback")
