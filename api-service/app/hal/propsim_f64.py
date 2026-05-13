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
from app.hal.channel_emulator import (
    CalibrationToneCapability,
    ChannelEmulatorDriver,
    ChannelLoadMode,
)

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


# F64 远程文件存储路径默认 (Windows F64 ATE 出厂约定)。
# 跨实验室部署时, 在 InstrumentCategory.config 里覆盖 emulation_dir /
# waveform_dir 以匹配本地 F64 服务器文件结构 (e.g. Linux F64 用 /opt/...
# 或 Windows F64 安装在非 D:\ 盘)。
F64_EMULATION_DIR = r"D:\User Emulations"
F64_WAVEFORM_DIR = r"D:\User Emulations\ASC"

# VISA 超时常量 (毫秒)
VISA_TIMEOUT_DEFAULT = 5000
VISA_TIMEOUT_FILE_LOAD = 30000  # 大文件加载需要更长超时
VISA_TIMEOUT_AUTOSET = 15000    # 自动电平校准

# FTP 凭据 (PROPSIM 出厂默认)
F64_FTP_USER = "PROPSIM"
F64_FTP_PASS = "propsim"

# *OPT? 查询返回里, 表示 "Internal Interference Generator" license 的候选 token.
# 不同 firmware revision 用不同代号, 命中任一即认定该 license 存在. CAICT 现场首
# 测后建议把列表收紧到实际返回的唯一值.
INTERFERENCE_GEN_OPTION_TOKENS = frozenset({
    "K01", "INTGEN", "INT-GEN", "INTERFERENCE-GEN", "OPT-INT-GEN",
    "INTERFERENCE_GENERATOR", "F64-K01",
})


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
        # Phase 2h: 跨实验室部署时由 InstrumentCategory.config 覆盖
        self.emulation_dir: str = config.get("emulation_dir", F64_EMULATION_DIR)
        self.waveform_dir: str = config.get("waveform_dir", F64_WAVEFORM_DIR)

        # Calibration-tone 能力: PROPSIM Internal Interference Generator 是
        # optional license. 默认在 connect() 中通过 *OPT? 探测 (见 base
        # _probe_installed_options + 本类 _apply_discovered_capabilities).
        # config 里显式给值 (True/False) 时跳过探测, 用于 mock / CI / 手动
        # override 场景:
        #   未设置        → connect() 时探测; 探测前为 None (按无 license 处理)
        #   True / False  → 显式声明, 跳过探测
        explicit = config.get("has_interference_generator")
        self._explicit_interference_gen: bool = explicit is not None
        self.has_interference_generator: Optional[bool] = (
            bool(explicit) if self._explicit_interference_gen else None
        )
        # 固定 ID 给单 tone, 重复 set 时先 remove 旧的避免 "identifier in use".
        self._cal_tone_id: str = config.get("cal_tone_id", "ce_sa_cal_tone")
        self._cal_tone_active: bool = False

        # User alignment (Integrated Setup Calibration, optional license).
        # alignment_name 在 connect() 后会尝试 SYST:CALIB:USER:SET 1,<name>
        # 重新装载 — F64 重启后已存盘的 alignment 默认不激活, 必须显式调用 SET.
        # 留空表示这台 F64 不使用 user alignment, 仅依赖工厂校准 + 我们自己的
        # ProbePathLossCalibration.
        self._preferred_alignment_name: Optional[str] = (
            config.get("alignment_name") or None
        )
        self._active_alignment: Optional[Dict[str, Any]] = None

        # PyVISA 资源句柄
        self._visa_resource = None
        self._rm = None

        # 管线状态追踪
        self._active_pipeline: Optional[F64Pipeline] = None
        self._loaded_emulation_file: Optional[str] = None
        self._emulation_running: bool = False
        self._bypass_mode: F64BypassMode = F64BypassMode.DISABLED
        self._passthrough_active: bool = False

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

            # 启动时探测安装选件 (license). 若 config 显式声明能力字段则跳过
            # 应用阶段, 仍执行探测仅为日志可见性.
            opts = await self._probe_installed_options()
            await self._apply_discovered_capabilities(opts)

            # User alignment auto-reload (User Reference §17.5):
            #   "Auto alignment results become obsolete when the emulator
            #    shuts down" — alignment 文件保留在盘上, 但每次开机后必须调
            #    SYST:CALIB:USER:SET 1,<name> 重新激活. 当前 active 状态先
            #    存到 _active_alignment 供 precheck phase 上报.
            self._active_alignment = await self.get_user_alignment_status()
            if self._preferred_alignment_name:
                current = (
                    self._active_alignment.get("alignment_name")
                    if self._active_alignment else None
                )
                if current != self._preferred_alignment_name:
                    logger.info(
                        f"[F64] Re-loading user alignment "
                        f"\"{self._preferred_alignment_name}\" "
                        f"(was: {current!r})"
                    )
                    if await self.enable_user_alignment(self._preferred_alignment_name):
                        self._active_alignment = await self.get_user_alignment_status()
                    else:
                        logger.warning(
                            f"[F64] Could not activate user alignment "
                            f"\"{self._preferred_alignment_name}\" — "
                            f"emulator may be missing the file or the license."
                        )

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
                    f"{self.emulation_dir}\\{model_type}_{scenario}"
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
            remote_dir = f"{self.waveform_dir}\\{cdl_model_name or 'custom'}"
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
        except Exception as e:
            # SCPI 层失败 (timeout / 仪表错误) — 整体返回空, 调用方自行重试
            logger.error(f"[F64] query_runtime_environment SCPI failed: {e}")
            return {}

        result: Dict[int, Dict[str, Any]] = {}
        parts = response.strip().split(",")
        # 每 5 个 token 为一组: ch, env, gain, delay, doppler. 单组解析失败
        # 跳过该组 (e.g. 仪表临时返回畸形 token), 其他组照常返回 — 比"全
        # 部丢弃"更有用.
        skipped = 0
        for i in range(0, len(parts), 5):
            if i + 5 > len(parts):
                # 末尾不足一组 — 截断, 不算错误
                break
            try:
                ch_num = int(parts[i].strip())
                result[ch_num] = {
                    "environment": parts[i + 1].strip(),
                    "gain_db": float(parts[i + 2]) if parts[i + 2].strip() else None,
                    "delay_ns": int(parts[i + 3]) if parts[i + 3].strip() else None,
                    "doppler_hz": int(parts[i + 4]) if parts[i + 4].strip() else None,
                }
            except (ValueError, IndexError) as e:
                skipped += 1
                logger.warning(
                    f"[F64] query_runtime_environment skipped malformed group "
                    f"at index {i}: {parts[i:i+5]!r} ({e})"
                )

        if skipped:
            logger.info(
                f"[F64] query_runtime_environment: parsed {len(result)} channels, "
                f"skipped {skipped} malformed groups"
            )
        return result

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
        配置 MIMO 端口拓扑 (软 setter, F64 真正的拓扑在 .smu/.rtc 文件里).

        F64 的 MIMO 端口拓扑通过 Scenario Wizard 烘到仿真文件中, SCPI 不能
        动态改路径数. 本方法做两件事:
          1. 校验请求的 tx×rx 是否超出本机通道数 (connect 时探测)
          2. 缓存 (tx, rx) 给上层服务 (set_path_loss 等) 计算输出数

        若已有仿真文件加载, 拓扑已固定, 此时调用本方法 ≠ 缓存值就 **拒绝并
        返回 False** —— 否则 set_path_loss 等下游计算会用错误的输出数. 真要
        改拓扑必须 reload 不同的 .smu/.rtc.

        connector 重映射 (INP:CON:SET / OUTP:CON:SET) 是另一回事 (物理路由,
        不是逻辑路径数), 不在本方法范围.

        Returns:
            True  校验通过 (或与已加载文件一致, 无需改动)
            False 超出本机通道数 / 已加载文件且请求拓扑不一致
        """
        required_paths = tx_antennas * rx_antennas
        if required_paths > self._channel_count:
            msg = (
                f"requested MIMO {tx_antennas}x{rx_antennas} = {required_paths} "
                f"paths exceeds device capacity {self._channel_count}"
            )
            logger.error(f"[F64] set_mimo_config refused: {msg}")
            self._last_error = msg
            return False

        if self._loaded_emulation_file is not None:
            if (tx_antennas, rx_antennas) != (self._tx_antennas, self._rx_antennas):
                logger.warning(
                    f"[F64] set_mimo_config refused: file '{self._loaded_emulation_file}' "
                    f"is loaded with {self._tx_antennas}x{self._rx_antennas}; "
                    f"requested {tx_antennas}x{rx_antennas} would silently mismatch — "
                    f"reload a different file to change topology"
                )
                self._last_error = "topology fixed by loaded file"
                return False
            # 与已加载文件一致, no-op
            return True

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

        汇总: 仿真状态、旁路模式、管线类型、中心频率、输入/输出电平等.

        语义: 静态字段 (pipeline / center_freq 等内存缓存) 总是返回. 动态
        查询 (旁路状态 / SCPI 版本) per-query try, 失败的项不出现在 state
        里, 错误进 query_errors. 上层可据此区分:
          - status='disconnected'  → 无 visa
          - 'error' in state       → 整机故障
          - 'query_errors' present → 部分查询失败, 主体状态可用
          - 三者皆无                → 全部成功
        """
        if not self._visa_resource:
            return {"status": "disconnected"}

        # 静态字段 (内存缓存, 不会失败)
        state: Dict[str, Any] = {
            "pipeline": self._active_pipeline.value if self._active_pipeline else None,
            "emulation_running": self._emulation_running,
            "loaded_file": self._loaded_emulation_file,
            "model": self._current_model,
            "scenario": self._current_scenario,
            "center_freq_mhz": self._center_freq_mhz,
            "mimo_config": f"{self._tx_antennas}x{self._rx_antennas}",
        }
        query_errors: List[str] = []

        # 查询旁路状态
        try:
            bypass_str = await self._query("DIAG:SIMU:MODEL:STATIC?")
            state["bypass_mode"] = (
                int(bypass_str.strip()) if bypass_str.strip().isdigit() else 0
            )
        except Exception as e:
            query_errors.append(f"bypass_mode: {e}")

        # 查询 SCPI 版本
        try:
            scpi_ver = await self._query("SYST:VERS?")
            state["scpi_version"] = scpi_ver.strip()
        except Exception as e:
            query_errors.append(f"scpi_version: {e}")

        if query_errors:
            state["query_errors"] = query_errors

        return state

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

    # ===================================================================
    # 5b. CE+SA 路损校准 tone 链路 (3GPP MIMO OTA, 取代 VNA)
    # ===================================================================
    # 服务层 ProbePathLossCalibrationService.acquire_sa_power_via_ce_tone()
    # 通过 capability dispatch 选 D 路径 (CE 自己出 CW) 或 B 路径 (上游 BSE/SG
    # 出 CW + CE 透传). 两条路径都在这里实现:
    #
    #   D — Internal Interference Generator (optional license):
    #       OUTPut:INTERFerence:ADD <port>, <id>, 2  (type=2 = CW)
    #       + STRATegy:SET 1 (恒定功率) + FREQ:SET + POW:SET + STatus 1
    #       (User Reference §13 + §20.4.9)
    #   B — Calibration bypass (无 license 也支持):
    #       DIAG:SIMU:MODEL:STATIC 3  (所有通道等增益/等延迟/零相位透传)
    #       配合上游 SG/BSE 出 CW, 信号经 CE 原样输出.
    # ===================================================================

    @staticmethod
    def _ce_port_to_output_num(ce_port: Optional[str]) -> str:
        """ce_port 解析为 SCPI 用的 output number string.

        - None → "1" (主端口默认)
        - 纯数字 ("1", "12") → 直接用
        - "B1.1" / "B1.2" 等 ETSL 风格 connector 表示法 → 取小数点后部分
          作为 output index (这是 CAICT 现场约定; 跨实验室部署在
          InstrumentCategory.config 里另写映射表覆盖)
        - 解析失败 → "1" + warn (生产部署应在 LabProfile 显式声明 ce_port)
        """
        if ce_port is None:
            return "1"
        s = str(ce_port).strip()
        if s.isdigit():
            return s
        # "B1.1" / "A2.3" → 小数点后的数字
        if "." in s:
            tail = s.rsplit(".", 1)[-1]
            if tail.isdigit():
                return tail
        logger.warning(
            "[F64] ce_port=%r unrecognized format, defaulting to output 1; "
            "configure LabProfile.ce_port explicitly for production",
            ce_port,
        )
        return "1"

    def get_calibration_tone_capabilities(self) -> List[CalibrationToneCapability]:
        """声明本 PROPSIM 的 CE+SA tone 能力.

        D 路径 (INTERNAL_CW_GENERATOR) 需要 Internal Interference Generator
        optional license. has_interference_generator 在 connect() 时由
        *OPT? 探测填充 (见 _apply_discovered_capabilities); config 显式声明
        会跳过探测. 探测前 / 未连接时为 None, 按无 license 处理.

        B 路径 (PASSTHROUGH_ONLY) 任何 PROPSIM 都支持 — 走 BypassMode
        .CALIBRATION (DIAG:SIMU:MODEL:STATIC 3), 全通道等增益等延迟透传.
        """
        caps: List[CalibrationToneCapability] = [
            CalibrationToneCapability.PASSTHROUGH_ONLY,
        ]
        if self.has_interference_generator:
            caps.insert(0, CalibrationToneCapability.INTERNAL_CW_GENERATOR)
        return caps

    async def set_calibration_tone(
        self,
        frequency_hz: float,
        power_dbm: float,
        ce_port: Optional[str] = None,
    ) -> bool:
        """[D 路径] 通过 Internal Interference Generator 出已知 CW tone.

        SCPI sequence (User Reference §20.4.9):
            OUTPut:INTERFerence:ADD <out>, <id>, 2     # type=2 = CW
            OUTPut:INTERFerence:STRATegy:SET <id>, 1   # 恒定功率
            OUTPut:INTERFerence:FREQuency:SET <id>, <MHz>
            OUTPut:INTERFerence:POWer:SET <id>, <dBm>
            OUTPut:INTERFerence:STatus <id>, 1         # 启用

        前置: has_interference_generator=True (license 已开).

        重复调用安全 — 先 REMove 旧 ID 避免 "identifier in use" 错误.
        """
        if not self._visa_resource:
            return False
        if not self.has_interference_generator:
            logger.error(
                "[F64] set_calibration_tone called but has_interference_generator"
                " is False. Configure instrument with this option enabled, or "
                "fall through to PASSTHROUGH path (BSE/SG upstream)."
            )
            return False

        out_num = self._ce_port_to_output_num(ce_port)
        cal_id = self._cal_tone_id
        freq_mhz = frequency_hz / 1e6

        try:
            # 1. 先清掉同 id 的旧 interferer (重复调用幂等)
            try:
                await self._write(f"OUTPut:INTERFerence:REMove {cal_id}")
            except Exception:
                pass  # 没有旧的就忽略

            # 2. 加 CW 干扰源到指定 output (type=2 = CW)
            await self._write(
                f"OUTPut:INTERFerence:ADD {out_num},{cal_id},2"
            )
            # 3. 恒定功率策略 (而非 C/I-ratio, 校准要绝对值)
            await self._write(
                f"OUTPut:INTERFerence:STRATegy:SET {cal_id},1"
            )
            # 4. 频率 (MHz) 和功率 (dBm)
            await self._write(
                f"OUTPut:INTERFerence:FREQuency:SET {cal_id},{freq_mhz:.6f}"
            )
            await self._write(
                f"OUTPut:INTERFerence:POWer:SET {cal_id},{power_dbm:.2f}"
            )
            # 5. 启用
            await self._write(f"OUTPut:INTERFerence:STatus {cal_id},1")

            await self._check_errors()
            self._cal_tone_active = True
            logger.info(
                "[F64] Calibration tone ON: out=%s freq=%.1fMHz power=%.1fdBm id=%s",
                out_num, freq_mhz, power_dbm, cal_id,
            )
            return True
        except Exception as e:
            logger.error(f"[F64] set_calibration_tone failed: {e}")
            self._last_error = str(e)
            # 失败时尝试清理避免半状态
            try:
                await self._write(f"OUTPut:INTERFerence:REMove {cal_id}")
            except Exception:
                pass
            self._cal_tone_active = False
            return False

    async def stop_calibration_tone(self) -> bool:
        """[D 路径] 关 CW tone 并移除 interferer.

        SCPI:
            OUTPut:INTERFerence:STatus <id>, 0   # 禁用
            OUTPut:INTERFerence:REMove <id>      # 移除

        finally 块里调用避免 CE 长时间发射. 没启用过也安全 — REMove
        不存在的 id 时报 -200, 我们捕获后忽略.
        """
        if not self._visa_resource:
            return False
        cal_id = self._cal_tone_id
        try:
            try:
                await self._write(f"OUTPut:INTERFerence:STatus {cal_id},0")
            except Exception:
                pass
            try:
                await self._write(f"OUTPut:INTERFerence:REMove {cal_id}")
            except Exception:
                pass
            await self._check_errors()
            self._cal_tone_active = False
            logger.info(f"[F64] Calibration tone OFF (id={cal_id})")
            return True
        except Exception as e:
            logger.error(f"[F64] stop_calibration_tone failed: {e}")
            self._last_error = str(e)
            return False

    async def set_passthrough_mode(
        self,
        ce_port: Optional[str] = None,
        ce_input_port: Optional[str] = None,
    ) -> bool:
        """[B 路径] 切到 calibration bypass — 全通道等增益等延迟零相位透传.

        实现复用 set_bypass_mode(F64BypassMode.CALIBRATION):
            DIAG:SIMU:MODEL:STATIC 3   (User Reference §20.4.6.25)

        在此模式下上游 SG/BSE 注入的 CW 经 CE 原样从所有 output 输出, 配合
        switch 路由到指定 probe. ce_port / ce_input_port 在 CALIBRATION
        bypass 下不需要 per-port 配置 (全局透传), 仅记录到状态用于 trace.
        """
        ok = await self.set_bypass_mode(F64BypassMode.CALIBRATION)
        if ok:
            self._passthrough_active = True
            logger.info(
                "[F64] Passthrough mode ON (out=%s, in=%s, calibration bypass)",
                ce_port or "all", ce_input_port or "all",
            )
        return ok

    async def clear_passthrough_mode(self) -> bool:
        """[B 路径] 退出 calibration bypass, 恢复正常 fading 配置."""
        ok = await self.set_bypass_mode(F64BypassMode.DISABLED)
        if ok:
            self._passthrough_active = False
            logger.info("[F64] Passthrough mode OFF (bypass disabled)")
        return ok

    # ===================================================================
    # User alignment (Integrated Setup Calibration, optional license)
    # User Reference §17 + §20.4.2.18-21, .32-36.
    #
    # 用户级 alignment 补偿 F64 内部各通道随时间/温度/环境的相位&增益漂移.
    # 工厂校准 (§6.1) 给绝对计量基准, 用户 alignment 给相对一致性. 是
    # OPTIONAL license, 不是每台 F64 都激活.
    #
    # 这些方法通过 SCPI 实现的能力:
    #   - 查询当前是否激活 / alignment 名 / 元信息 (FW/SW/timestamp)
    #   - 重启后用名字重新激活 (alignment 数据本身已存盘, 但开机不自动 active)
    #   - 列出已连接的 ACU (Auto Calibration Unit) — 全自动 alignment 时用
    #
    # 不在 SCPI 接口里的 (必须人在仪器前操作):
    #   - 跑一次新 alignment (要插拔 thru 走 wizard)
    # ===================================================================

    async def get_user_alignment_status(self) -> Optional[Dict[str, Any]]:
        """查询当前激活的 user alignment 名 + 元信息.

        SCPI: SYST:CALIB:USER:GET? + SYST:CALIB:USER:INFO? (§20.4.2.19, .21)

        Returns:
            {"alignment_name": <name>, "info": <info string>}
                — 有激活的 alignment 时
            None — 未激活, 或查询失败 (firmware 不支持本组命令也会落到这里)
        """
        if not self._visa_resource:
            return None
        try:
            raw_name = await self._query("SYSTem:CALIBration:USER:GET?")
        except Exception as e:
            logger.warning(f"[F64] User alignment query failed: {e}")
            return None
        name = raw_name.strip().strip('"').strip("'")
        if not name:
            return None
        info = ""
        try:
            raw_info = await self._query("SYSTem:CALIBration:USER:INFO?")
            info = raw_info.strip().strip('"').strip("'")
        except Exception as e:
            logger.debug(
                f"[F64] User alignment info query failed (non-fatal): {e}"
            )
        return {"alignment_name": name, "info": info}

    async def enable_user_alignment(self, name: str) -> bool:
        """重新激活已存盘的 user alignment.

        典型场景: F64 重启后已存盘的 alignment 不会自动 active, 必须显式
        调用 SYST:CALIB:USER:SET 1,<name> (§20.4.2.18). 设完用 GET? 回读
        确认.

        Args:
            name: alignment 文件名 (跟 wizard 里 Configuration Name 一致)

        Returns:
            True  — set + GET? 回读匹配
            False — alignment 不存在 / VISA 异常 / 名字不匹配
        """
        if not name:
            raise ValueError("alignment name cannot be empty")
        if not self._visa_resource:
            return False
        try:
            await self._write(f"SYSTem:CALIBration:USER:SET 1,{name}")
            raw = await self._query("SYSTem:CALIBration:USER:GET?")
            active = raw.strip().strip('"').strip("'")
            if active == name:
                logger.info(f"[F64] User alignment activated: {name}")
                return True
            logger.warning(
                f"[F64] enable_user_alignment(\"{name}\"): post-set GET? "
                f"returned {active!r} — file may not exist on the emulator."
            )
            return False
        except Exception as e:
            logger.error(
                f"[F64] enable_user_alignment(\"{name}\") failed: {e}"
            )
            return False

    async def list_external_units(self) -> List[Dict[str, Any]]:
        """列出连接到 F64 的 ACU (Auto Calibration Units).

        SCPI: SYST:EXT:UNIT:LIST? 0 (§20.4.2.32)
        响应示例: "ACU 12345 (C5),ACU 67890 (C6)"
        括号里是控制电缆所连的 BNC connector (C5/C7 等).

        Returns:
            每个检测到的 ACU 一条 {"unit": "ACU 12345", "connector": "C5"}.
            空列表表示没有 ACU 连接 (那么 alignment 只能走 manual mode).
        """
        if not self._visa_resource:
            return []
        try:
            # 第二参数 0 = 仅返回缓存, 不触发 scan; 用 1 会让 F64 重新扫描所有
            # connector, 耗时, 在 precheck 路径上不必要.
            raw = await self._query("SYSTem:EXTernal:UNIT:LIST? 0")
        except Exception as e:
            logger.warning(f"[F64] External unit list query failed: {e}")
            return []
        raw = raw.strip()
        if not raw:
            return []
        units: List[Dict[str, Any]] = []
        for token in raw.split(","):
            token = token.strip().strip('"').strip("'")
            if not token:
                continue
            unit_id = token
            connector: Optional[str] = None
            # Manual 解析 "ACU 12345 (C5)" 形式 — 末尾括号 = connector
            if "(" in token and token.endswith(")"):
                head, _, rest = token.rpartition("(")
                unit_id = head.strip()
                connector = rest.rstrip(")").strip() or None
            units.append({"unit": unit_id, "connector": connector})
        return units

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
            # 用 IEEE 488.2 *OPC? 同步等待 autoset 完成 — 比硬 sleep 可靠:
            # *OPC? 阻塞直到所有挂起的 SCPI 操作完成, 立即返回 "1".
            # timeout 给 (measurement_time + 2)s 缓冲, 防止 PROPSIM 内部
            # autoset 略超额定时间.
            opc_timeout_ms = int((measurement_time_s + 2) * 1000)
            await self._query("*OPC?", timeout=opc_timeout_ms)

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

    async def get_output_calibration(
        self,
        output_num: int,
        *,
        retries: int = 3,
        retry_delay_s: float = 0.5,
    ) -> Optional[Dict[str, float]]:
        """
        获取输出通道校准数据 (含 not-ready 重试).

        User Reference §20.4.5.24:
          OUTP:CALIB:GET? <output>
          返回: <gain_dB>,<phase_degrees>

        紧接 autoset 后调用容易碰到 "not ready", retry 重试 retries 次,
        每次间 retry_delay_s; 全部 not-ready 或异常则 None.
        """
        if not self._visa_resource:
            return None
        raw = await self._query_with_retry(
            f"OUTP:CALIB:GET? {output_num}",
            retries=retries,
            delay_s=retry_delay_s,
        )
        if raw is None:
            return None
        try:
            parts = raw.split(",")
            return {
                "gain_db": float(parts[0]),
                "phase_deg": float(parts[1]) if len(parts) > 1 else 0.0,
            }
        except (ValueError, IndexError) as e:
            logger.error(f"[F64] get_output_calibration parse failed: {raw!r} ({e})")
            return None

    async def get_output_power(
        self,
        output_num: int,
        *,
        retries: int = 3,
        retry_delay_s: float = 0.5,
    ) -> Optional[float]:
        """
        获取输出功率测量值 (含 not-ready 重试).

        User Reference §20.4.5.22:
          OUTP:MEAS:RES:GET? <output>[,<option>]
          option 0: 基于输入功率计算 (legacy)
          option 1: 在输出端直接测量 (含内部干扰源)

        刚启动仿真 / 改路损 / autoset 后, F64 内部测量缓冲尚未填满会返回
        'not ready' — retry 多次后仍 not-ready 才放弃.
        """
        if not self._visa_resource:
            return None
        raw = await self._query_with_retry(
            f"OUTP:MEAS:RES:GET? {output_num}",
            retries=retries,
            delay_s=retry_delay_s,
        )
        if raw is None:
            return None
        try:
            return float(raw)
        except ValueError as e:
            logger.error(f"[F64] get_output_power parse failed: {raw!r} ({e})")
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
        """获取 F64 运行状态指标 (含逐通道功率)。

        输入电平按 _tx_antennas 数量逐路查 INP:MEAS:RES:GET? <i>;
        输出电平按 _tx_antennas × _rx_antennas (仿真路径数) 逐路查
        OUTP:MEAS:RES:GET? <i>. 单路查询失败 (含 'not ready') 不影响其他
        路 — 该路记 None, 用 query_errors 累计错误以便 dashboard 区分
        "通道未就绪" 与 "整机故障".
        """
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
                "tx_antennas": self._tx_antennas,
                "rx_antennas": self._rx_antennas,
            }
            query_errors: List[str] = []

            # 输入电平: 1..tx_antennas
            input_powers: Dict[int, Optional[float]] = {}
            for inp in range(1, self._tx_antennas + 1):
                try:
                    raw = await self._query(f"INP:MEAS:RES:GET? {inp}")
                    raw_l = raw.strip().lower()
                    if not raw_l or "not ready" in raw_l:
                        input_powers[inp] = None
                    else:
                        input_powers[inp] = float(raw.strip())
                except Exception as e:
                    input_powers[inp] = None
                    query_errors.append(f"input_{inp}: {e}")
            metrics["input_powers_dbm"] = input_powers

            # 输出电平: 1..(tx_antennas × rx_antennas), 但不超本机通道数
            num_outputs = min(
                self._tx_antennas * self._rx_antennas,
                self._channel_count,
            )
            output_powers: Dict[int, Optional[float]] = {}
            for out in range(1, num_outputs + 1):
                try:
                    raw = await self._query(f"OUTP:MEAS:RES:GET? {out}")
                    raw_l = raw.strip().lower()
                    if not raw_l or "not ready" in raw_l:
                        output_powers[out] = None
                    else:
                        output_powers[out] = float(raw.strip())
                except Exception as e:
                    output_powers[out] = None
                    query_errors.append(f"output_{out}: {e}")
            metrics["output_powers_dbm"] = output_powers

            if query_errors:
                metrics["query_errors"] = query_errors

            # 单路失败不降级整体状态 — 仿真在跑就是 normal
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
        """返回 F64 支持的能力列表 (含 *OPT? 探测出的 license-aware 能力).

        非 license 能力 (Channel Emulation / GCM / Runtime / RSRP / Bypass)
        是 F64 出厂内置, 无条件声明. license 能力 (Internal Interference
        Generator) 取决于 *OPT? 探测结果, supported 字段反映实际状态.
        """
        caps: List[InstrumentCapability] = [
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

        # License-aware: Internal Interference Generator (CW tone source).
        # has_interference_generator 在 connect() 时由 *OPT? 探测填充
        # (None = 探测前 / 探测失败, 当作不可用).
        caps.append(
            InstrumentCapability(
                name="Internal Interference Generator",
                description="Optional license for internal CW/noise tone "
                            "injection (calibration D path)",
                supported=bool(self.has_interference_generator),
                parameters={
                    "license_status": (
                        "licensed" if self.has_interference_generator
                        else "not_licensed"
                    ),
                    "matched_options": [
                        opt for opt in self._installed_options
                        if opt.upper() in INTERFERENCE_GEN_OPTION_TOKENS
                    ],
                },
            )
        )

        # 透明声明所有 *OPT? 探测出的选件 — 上层 (lab dashboard / commissioning
        # 报告) 能直接看到这台 F64 装了哪些 license, 不需要再额外查询.
        caps.append(
            InstrumentCapability(
                name="Installed Options",
                description=f"{len(self._installed_options)} license token(s) "
                            f"reported by *OPT?",
                supported=bool(self._installed_options),
                parameters={"options": list(self._installed_options)},
            )
        )

        return caps

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
    #
    # Only _do_write / _do_query are defined here — the base class's
    # _write / _query template methods handle async _do_* transparently
    # (see base.InstrumentDriver._query for the dispatch). Driver code
    # calls ``await self._query(...)`` because our _do_query is async.
    # ===================================================================

    async def _do_write(self, cmd: str, timeout: Optional[int] = None) -> None:
        """发送 SCPI 写命令（由基类 _write() 自动调用，SCPI 日志已由基类记录）"""
        if timeout:
            original_timeout = self._visa_resource.timeout
            self._visa_resource.timeout = timeout
        try:
            await asyncio.to_thread(self._visa_resource.write, cmd)
        finally:
            if timeout:
                self._visa_resource.timeout = original_timeout

    async def _do_query(self, cmd: str, timeout: Optional[int] = None) -> str:
        """发送 SCPI 查询命令并返回响应（由基类 _query() 自动调用，SCPI 日志已由基类记录）"""
        if timeout:
            original_timeout = self._visa_resource.timeout
            self._visa_resource.timeout = timeout
        try:
            response = await asyncio.to_thread(self._visa_resource.query, cmd)
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

    async def _apply_discovered_capabilities(self, options: List[str]) -> None:
        """*OPT? 解析出的 token → has_interference_generator.

        Override base no-op. config 里显式给值时不覆盖 (尊重运维 / mock 决定).
        Token 匹配大小写不敏感, 候选见 INTERFERENCE_GEN_OPTION_TOKENS.
        """
        if self._explicit_interference_gen:
            return
        upper = {opt.upper() for opt in options}
        self.has_interference_generator = bool(
            upper & INTERFERENCE_GEN_OPTION_TOKENS
        )
        logger.info(
            f"[F64] Interference Generator license: "
            f"{self.has_interference_generator} (probed from {options or '(empty)'})"
        )

    async def _query_with_retry(
        self,
        cmd: str,
        *,
        retries: int = 3,
        delay_s: float = 0.5,
    ) -> Optional[str]:
        """SCPI 查询 + not-ready / 异常重试.

        F64 在测量缓冲尚未填满时返回 'not ready' 字符串. 紧接 autoset / 仿真
        启动 / 路损改动后调用 OUTP:MEAS:RES:GET? / OUTP:CALIB:GET? 容易碰
        到. 这个 helper 把"重试 N 次, 每次间隔 delay_s"的样板封掉.

        Returns:
            stripped response 字符串 — 成功;
            None — 全部重试都 not-ready / 异常.
        """
        for attempt in range(retries):
            try:
                raw = await self._query(cmd)
                stripped = raw.strip()
                if not stripped or "not ready" in stripped.lower():
                    if attempt + 1 < retries:
                        logger.debug(
                            f"[F64] {cmd}: not ready, retry "
                            f"{attempt + 1}/{retries} in {delay_s}s"
                        )
                        await asyncio.sleep(delay_s)
                        continue
                    logger.warning(
                        f"[F64] {cmd}: not ready after {retries} attempts"
                    )
                    return None
                return stripped
            except Exception as e:
                if attempt + 1 < retries:
                    logger.warning(
                        f"[F64] {cmd} failed (attempt {attempt + 1}/{retries}): {e}"
                    )
                    await asyncio.sleep(delay_s)
                else:
                    logger.error(
                        f"[F64] {cmd} failed after {retries} attempts: {e}"
                    )
                    return None
        return None

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
