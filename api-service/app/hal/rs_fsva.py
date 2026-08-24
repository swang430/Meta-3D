"""
R&S FSVA Signal Analyzer Driver
================================

Real HAL Driver for Rohde & Schwarz FSVA series Signal & Spectrum Analyzers.
FSVA shares core SCPI with FSW but has additional spectrum analysis capabilities.

Reference: R&S FSVA/FSV Operating Manual 1176.7510.02 ─ 13（下文简写「手册 pNNN」，
页码为手册页脚编号）。P1-70 的 TRACe:IQ 采集命令逐条对过该手册原文
（TRACe:IQ Subsystem p894-907、FORMat[:DATA] p933、返回值格式 p915、
采样率范围 p441-442、样例程序 p1036-1037、SYSTem:ERRor[:NEXT]? p969、
[SENSe:]FREQuency:CENTer p809）；查询形式手册未明示的命令在常量旁标「推断」，
运行时靠错误队列核对，队列非空一律 RuntimeError fail-loud。

> P1-70 实施对象申报：设计稿 §7 原文写「X 系列」，但现场实测
> （docs/site-debug/2026-05-27-onsite-playbook.md:68）现场 SA = R&S FSVA3000，
> P0-4 已绑本驱动；本地 Keysight X 系列两份手册均系假文件。故信道验证第一激活批
> （measure_pdp / measure_doppler_spectrum）落在本驱动。
>
> ⚠ 手册家族差距申报（P1-70 内审 F3）：1176.7510.02─13 封面覆盖机型 =
> FSVA4/7/13/30/40 + FSV 系（1321.3008Kxx/1307.9002Kxx）；现场 FSVA3000
> （料号 1330.5000Kxx）属 **FSV3000 家族，另有自己的手册**。上表页码出处
> 对现场机**不构成完备证据** —— TRACe:IQ 命令族在 FSV3000 家族是否同形，
> 两个方向都无证据（未经查证）。兜底：① 每步错误队列 fail-loud；
> ② `rs_fsva_iq_capability` 探针序列出发前实测查询形；③ 出发前应补
> FSV3000/FSVA3000 家族手册核对写路径命令（STATe ON / SET / DATA:FORMat /
> DATA?）—— 已列入 roadmap P1-70 行现场前置。
"""

import logging
import asyncio
import threading
from typing import Any, Callable, Dict, List, Tuple
from datetime import datetime

import numpy as np

from app.hal.base import (
    InstrumentStatus,
    InstrumentCapability,
    InstrumentMetrics,
    resolve_configured_instrument_host,
)
from app.hal.signal_analyzer import SignalAnalyzerDriver

logger = logging.getLogger(__name__)


class FsvaScpi:
    """R&S FSVA SCPI command set"""
    IDN = "*IDN?"
    RST = "*RST"
    OPC = "*OPC?"
    ERR = "SYST:ERR?"

    # Frequency / Span
    SET_FREQ = "SENSe:FREQuency:CENTer {freq}"
    SET_SPAN = "SENSe:FREQuency:SPAN {span}"
    SET_START_FREQ = "SENSe:FREQuency:STARt {freq}"
    SET_STOP_FREQ = "SENSe:FREQuency:STOP {freq}"

    # Bandwidth
    SET_RBW = "SENSe:BANDwidth:RESolution {rbw}"
    SET_VBW = "SENSe:BANDwidth:VIDeo {vbw}"

    # Reference level & Attenuator
    SET_REF_LEVEL = "DISPlay:WINDow:TRACe:Y:SCALe:RLEVel {level}"
    SET_ATT = "INPut:ATTenuation {att}"
    SET_ATT_AUTO = "INPut:ATTenuation:AUTO ON"
    SET_PREAMP = "INPut:GAIN:STATe {state}"         # ON/OFF

    # Sweep / Trigger
    INIT_CONT_OFF = "INITiate:CONTinuous OFF"
    INIT_CONT_ON = "INITiate:CONTinuous ON"
    TRIG = "INITiate:IMMediate; *OPC?"
    SWEEP_SINGLE = "SENSe:SWEep:MODE SINGle"
    SET_SWEEP_POINTS = "SENSe:SWEep:POINts {points}"
    SET_SWEEP_TIME = "SENSe:SWEep:TIME {time}"
    SET_SWEEP_TIME_AUTO = "SENSe:SWEep:TIME:AUTO ON"

    # Data format & Readout
    DATA_FMT_ASC = "FORMat:DATA ASCii"
    DATA_FMT_REAL32 = "FORMat:DATA REAL,32"
    READ_TRAC = "TRACe:DATA? TRACE1"

    # Marker
    MARKER_ON = "CALCulate:MARKer1:STATe ON"
    MARKER_POS = "CALCulate:MARKer1:X {freq}"
    MARKER_Y = "CALCulate:MARKer1:Y?"
    MARKER_PEAK = "CALCulate:MARKer1:MAXimum"

    # Channel Power Measurement
    MEAS_CHP = "SENSe:POWer:ACHannel:MODE ABSolute"
    SET_CHP_BW = "SENSe:POWer:ACHannel:BANDwidth:CHANnel {bw}"
    READ_CHP = "CALCulate:MARKer:FUNCtion:POWer:RESult? CPOWer"

    # Display
    DISP_UPD_ON = "SYSTem:DISPlay:UPDate ON"
    DISP_UPD_OFF = "SYSTem:DISPlay:UPDate OFF"

    # ── TRACe:IQ Subsystem（手册 p894-907）——P1-70 信道验证第一激活批 ──
    # 命令头一律用手册命令参考列出的长形式（<n> 后缀手册标 irrelevant，省略）。
    IQ_STATE_ON = "TRACe:IQ:STATe ON"       # p895；样例程序 p1036 注释原文
    #                                         "must be done before TRAC:IQ:SET !"
    IQ_STATE_OFF = "TRACe:IQ:STATe OFF"     # p895；样例程序 p1037 结尾同款
    IQ_STATE_QUERY = "TRACe:IQ:STATe?"      # ⚠ 推断：p895 只载设置形（ON|OFF），查询形
    #                                         是 SCPI 标准派生（该条未标 setting-only），
    #                                         运行时以错误队列核对
    # p904：TRACe<n>:IQ:SET NORM,<Placeholder>,<SampleRate>,<TriggerMode>,
    #       <TriggerSlope>,<PretriggerSamp>,<NumberSamples>；NORM 与 <Placeholder>
    #       "is not evaluated, but must be inserted"（占位值照 p897 例 "10MHz"）；
    #       IMM = free-run 触发（p905 "For IMM mode, gating is automatically
    #       deactivated"），显式下发以免继承面板残留的 EXT 触发挂死采集。
    #       速率数值不带单位 = Hz —— ⚠ 推断：p904 例子带 "MHz" 单位，裸数值默认 Hz
    #       是本机频率参数惯例（p809 FREQ:CENT 明写 "Default unit: Hz"），错误队列核对。
    IQ_SET = "TRACe:IQ:SET NORM,10MHz,{srate_hz},IMM,POS,0,{num_samples}"
    IQ_SRATE_QUERY = "TRACe:IQ:SRATe?"      # ⚠ 推断：p906 只载设置形，同上核对
    IQ_BWIDTH_QUERY = "TRACe:IQ:BWIDth?"    # p896 例原文 "TRAC:IQ:BWID?"（查询形有据）
    IQ_RLENGTH_QUERY = "TRACe:IQ:RLENgth?"  # ⚠ 推断：p903 只载设置形，同上核对
    # p897-898：TRACe<n>:IQ:DATA:FORMat COMPatible|IQBLock|IQPair（*RST: IQBL）。
    # 选 IQBLock：I 块在前、Q 块在后 —— 排列有样例程序 p1036-1037 实证
    # （二进制读出把块对半分，前半 I 后半 Q）。
    IQ_DATA_FORMAT_IQBLOCK = "TRACe:IQ:DATA:FORMat IQBLock"
    # p897：TRACe<n>:IQ:DATA 启动测量并返回结果列表；返回值总数 = 2×样本数（原文
    # "The number of the returned values is 2 * the number of samples"）；输出格式由
    # FORMat 子系统决定（本驱动用 ASCII CSV，p933 / p915，可靠优先、免块头解析）。
    IQ_DATA_QUERY = "TRACe:IQ:DATA?"


# ── P1-70 IQ 采集尺寸常量 ──────────────────────────────────────────────
# 手册 p442：无带宽扩展选件时采样率范围 100 Hz – 45 MHz（B40/B70 到 128 MHz，
# B160 到 400 MHz）。下限 100 Hz 是手册原文，用作请求速率的地板；上限不在
# 驱动里硬夹 —— 请求后回读 TRACe:IQ:SRATe? 实际值，以实际值定轴。
_IQ_MIN_SAMPLE_RATE_HZ = 100.0
# Welch 分段平均的段数（工程选择：段数×段长决定统计方差与采集时长的折衷，
# 非手册规定值）。
_PDP_SEGMENTS = 48
_DOPPLER_SEGMENTS = 12
# 错误队列排水上限（SYSTem:ERRor[:NEXT]? 每读一条删一条，p969）。
_IQ_ERROR_DRAIN_CAP = 50


class RealRsFsvaDriver(SignalAnalyzerDriver):
    """
    Real HAL Driver for R&S FSVA Signal Analyzer

    Supports:
    - Spectrum analysis (center freq, span, RBW/VBW)
    - Channel power measurement
    - Marker-based peak search
    - Trace data readout (ASCII)
    - SCPI trace logging via HAL base class

    三层架构: InstrumentDriver → SignalAnalyzerDriver → RealRsFsvaDriver
    """

    def __init__(self, instrument_id: str, config: Dict[str, Any]):
        super().__init__(instrument_id, config)
        self._reject_incompatible_visa_resource(allowed_type="SOCKET")
        self.ip_address: str = self._connection_host
        self.port: int = self._resolved_tcp_port(5025)
        self._connection_visa_resource = self._resolved_visa_resource(
            f"TCPIP::{self.ip_address}::{self.port}::SOCKET",
            socket_prefix="TCPIP",
        )
        self._visa_rm = None
        self._visa_session = None
        # P1-70 内审 F2：SCPI 通道互斥。IQ 采集是分钟级多命令事务，
        # to_thread 让出事件循环后 broadcaster 的 1 Hz 轮询会插进采集
        # 命令序列中间（互吃错误队列、破坏 IQ 事务）。RLock：采集事务
        # 全程持锁（_capture_iq_block wrapper），单条查询逐条拿锁排队。
        self._scpi_rlock = threading.RLock()

    async def connect(self) -> bool:
        if self._connection_config_error or not self.ip_address:
            return self._fail_missing_connection_address()
        self._set_status(InstrumentStatus.CONNECTING)
        try:
            import pyvisa
            self._visa_rm = pyvisa.ResourceManager("@py")
            resource_string = self._connection_visa_resource
            self._visa_session = self._visa_rm.open_resource(
                resource_string, timeout=15000
            )
            self._visa_session.read_termination = "\n"
            self._visa_session.write_termination = "\n"

            idn = self._query(FsvaScpi.IDN).strip()
            logger.info(f"[FSVA] Connected to {idn}")

            # Initialize for automation
            self._write(FsvaScpi.DATA_FMT_ASC)
            self._write(FsvaScpi.INIT_CONT_OFF)
            self._write(FsvaScpi.DISP_UPD_OFF)
            self._write(FsvaScpi.SET_ATT_AUTO)
            self._write(FsvaScpi.SET_SWEEP_TIME_AUTO)

            self._set_status(InstrumentStatus.CONNECTED)
            return True
        except Exception as e:
            logger.error(f"[FSVA] Connection failed ({self.ip_address}:{self.port}): {e}")
            self._set_status(InstrumentStatus.ERROR, str(e))
            return False

    async def disconnect(self) -> bool:
        try:
            if self._visa_session:
                self._write(FsvaScpi.DISP_UPD_ON)
                self._write(FsvaScpi.INIT_CONT_ON)
                self._visa_session.close()
                self._visa_session = None
            # ⚠ **不调** `self._visa_rm.close()`: RM 是**进程级共享单例**, 关它会连带
            # 关掉其它仪表的会话 (权威说明见 `app/hal/_visa_reconnect.py` 的
            # 「ResourceManager 所有权」一节)。自己的 session 上面已经关了, 这里只丢引用。
            self._visa_rm = None
            self._set_status(InstrumentStatus.DISCONNECTED)
            return True
        except Exception as e:
            logger.error(f"[FSVA] Disconnect error: {e}")
            return False

    async def configure(self, config: Dict[str, Any]) -> bool:
        """Apply runtime configuration"""
        try:
            if "ref_level_dbm" in config:
                self._write(FsvaScpi.SET_REF_LEVEL.format(level=config["ref_level_dbm"]))
            if "attenuation_db" in config:
                self._write(FsvaScpi.SET_ATT.format(att=config["attenuation_db"]))
            if "preamp" in config:
                state = "ON" if config["preamp"] else "OFF"
                self._write(FsvaScpi.SET_PREAMP.format(state=state))
            if "sweep_points" in config:
                self._write(FsvaScpi.SET_SWEEP_POINTS.format(points=config["sweep_points"]))
            self._query(FsvaScpi.OPC)
            return True
        except Exception as e:
            logger.error(f"[FSVA] Configure failed: {e}")
            return False

    async def setup_spectrum(
        self, center_freq_hz: float, span_hz: float, rbw_hz: float
    ) -> bool:
        """Configure spectrum analysis parameters"""
        try:
            self._write(FsvaScpi.SET_FREQ.format(freq=center_freq_hz))
            self._write(FsvaScpi.SET_SPAN.format(span=span_hz))
            self._write(FsvaScpi.SET_RBW.format(rbw=rbw_hz))
            self._query(FsvaScpi.OPC)
            logger.info(
                f"[FSVA] Spectrum: center={center_freq_hz/1e9:.3f} GHz, "
                f"span={span_hz/1e6:.1f} MHz, RBW={rbw_hz/1e3:.1f} kHz"
            )
            return True
        except Exception as e:
            logger.error(f"[FSVA] Setup spectrum failed: {e}")
            return False

    async def measure_channel_power(self, bandwidth_hz: float) -> float:
        """
        Measure channel power over specified bandwidth.

        Args:
            bandwidth_hz: Channel bandwidth in Hz

        Returns:
            Channel power in dBm, or -999.0 on failure
        """
        try:
            self._set_status(InstrumentStatus.BUSY)
            self._write(FsvaScpi.MEAS_CHP)
            self._write(FsvaScpi.SET_CHP_BW.format(bw=bandwidth_hz))
            self._query(FsvaScpi.TRIG)  # Single sweep + wait

            power_str = self._query(FsvaScpi.READ_CHP)
            power_dbm = float(power_str.strip())

            self._set_status(InstrumentStatus.READY)
            logger.info(f"[FSVA] Channel power: {power_dbm:.2f} dBm (BW={bandwidth_hz/1e6:.1f} MHz)")
            return power_dbm
        except Exception as e:
            logger.error(f"[FSVA] Channel power measurement failed: {e}")
            self._set_status(InstrumentStatus.ERROR, str(e))
            return -999.0

    async def measure_peak(self) -> Dict[str, float]:
        """
        Find peak marker frequency and level.

        Returns:
            {"freq_hz": ..., "power_dbm": ...}
        """
        try:
            self._set_status(InstrumentStatus.BUSY)
            self._query(FsvaScpi.TRIG)
            self._write(FsvaScpi.MARKER_ON)
            self._write(FsvaScpi.MARKER_PEAK)
            level_str = self._query(FsvaScpi.MARKER_Y)
            power_dbm = float(level_str.strip())

            self._set_status(InstrumentStatus.READY)
            return {"power_dbm": power_dbm}
        except Exception as e:
            logger.error(f"[FSVA] Peak measurement failed: {e}")
            return {"power_dbm": -999.0}

    async def get_trace(self) -> List[float]:
        """Read current trace data (amplitude values)"""
        try:
            self._query(FsvaScpi.TRIG)
            data_str = self._query(FsvaScpi.READ_TRAC)
            values = list(map(float, data_str.strip().split(",")))
            logger.info(f"[FSVA] Read {len(values)} trace points")
            return values
        except Exception as e:
            logger.error(f"[FSVA] Get trace failed: {e}")
            return []

    async def get_capabilities(self) -> list[InstrumentCapability]:
        return [
            InstrumentCapability(
                name="spectrum_analysis",
                description="Spectrum and signal analysis",
                supported=True,
                parameters={
                    "frequency_range_ghz": [0.01, 44],
                    "analysis_bandwidth_mhz": 200,
                },
            ),
            InstrumentCapability(
                name="channel_power",
                description="Channel power measurement (CHP)",
                supported=True,
                parameters={},
            ),
            InstrumentCapability(
                name="5g_nr_demod",
                description="5G NR demodulation & EVM (optional)",
                supported=True,
                parameters={},
            ),
        ]

    async def get_metrics(self) -> InstrumentMetrics:
        return InstrumentMetrics(
            timestamp=datetime.utcnow(),
            metrics={
                "status": self.status.value,
            },
        )

    async def reset(self) -> bool:
        try:
            self._write(FsvaScpi.RST)
            self._query(FsvaScpi.OPC)
            self._write(FsvaScpi.DATA_FMT_ASC)
            logger.info("[FSVA] Reset to default state")
            return True
        except Exception as e:
            logger.error(f"[FSVA] Reset failed: {e}")
            return False

    # ===================================================================
    # 信道模型验证采集 (P1-70 第一激活批: temporal + doppler)
    # ===================================================================

    async def measure_pdp(
        self,
        center_freq_hz: float,
        max_delay_ns: float = 2000.0,
        resolution_ns: float = 10.0,
    ) -> Tuple[List[float], List[float]]:
        """真实 FSVA 的功率时延谱（PDP）测量 —— TRACe:IQ 采集 + numpy 后处理。

        数学含义（工程近似，如实声明）：对采集到的复基带样本做分段周期图平均
        （Welch，无窗）得到接收信号功率谱估计，再对其做 IFFT 得到接收信号的
        **循环自相关** r[τ]，取 |r[τ]| 作时延域功率谱。当 CE 输出的激励在分析
        带宽内近似白（OFDM 类宽带信号成立）时，r[τ] ≈ Σᵢⱼ hᵢh*ⱼ δ(τ-(dᵢ-dⱼ))
        —— 即**信道冲激响应的时延自相关（延迟差谱）**，不是真 PDP：峰的位置是
        相对最强径的**延迟差**（单强主径信道下 ≈ 各径真时延），次径电平是
        10·log10(|hᵢ||h₀|/Σ|h|²)（幅度交叉项），高于真径功率比 |hᵢ|²/Σ|h|²。
        这是工程近似，**不是**标准规定的互相关信道估计（无参考序列、无匹配
        滤波，无法分离 hᵢh*ⱼ 交叉项）；时延分辨率 = 1/实际采样率，受抗混叠
        滤波拖尾展宽。
        其它局限：先减样本均值抑制 LO 泄漏直流（会一并移除真实零频分量，PDP 场景
        无此分量）；r[0]（最强径）数学上恒为最大，故归一化后最强径 = 0 dB 满足
        接口契约（signal_analyzer.py measure_pdp docstring）。

        采样率按 resolution_ns 请求（fs = 1/resolution_ns），回读
        TRACe:IQ:SRATe? 实际值并以**实际值**生成时延轴 —— 仪器夹到别的速率时
        返回的 bin 如实反映实际分辨率，不撒谎；实际速率低到时延窗内不足两个
        bin 时 RuntimeError fail-loud。

        SCPI 逐条手册出处见 FsvaScpi 的 IQ_* 常量注释（手册 1176.7510.02─13）。
        任何解析失败 / 错误队列非空 → RuntimeError，不返回半截数据。
        """
        return await asyncio.to_thread(
            self._measure_pdp_sync, center_freq_hz, max_delay_ns, resolution_ns
        )

    def _measure_pdp_sync(
        self,
        center_freq_hz: float,
        max_delay_ns: float,
        resolution_ns: float,
    ) -> Tuple[List[float], List[float]]:
        """同步主体（asyncio.to_thread 内运行 —— P1-70 内审 F2：
        分钟级采集不再冻结事件循环；SCPI 事务互斥由
        _capture_iq_block 的 RLock 保证）。

        ⚠ 时长申报：real 采集为分钟级（Doppler 低速场景实算 63–123 s，
        失败场景含 VISA 超时最长约 6.5 min）。采集期间本 SA 驱动的 SCPI
        通道被事务锁独占 —— 其它 SCPI 调用（configure / get_trace / 诊断
        序列等）会**立即失败**（"IQ 采集事务独占中"，fail-fast 不冻结事件
        循环）；监控 get_metrics 只回内存状态、不发 SCPI，不受影响。"""
        if max_delay_ns <= 0 or resolution_ns <= 0:
            raise ValueError(
                f"[FSVA] measure_pdp 参数非法: max_delay_ns={max_delay_ns}, "
                f"resolution_ns={resolution_ns} (都必须 > 0)"
            )
        requested_fs = max(1e9 / resolution_ns, _IQ_MIN_SAMPLE_RATE_HZ)

        plan: Dict[str, int] = {}

        def _plan_samples(actual_fs: float) -> int:
            actual_res_ns = 1e9 / actual_fs
            if actual_res_ns > max_delay_ns:
                raise RuntimeError(
                    f"[FSVA] 仪器实际采样率 {actual_fs:.6g} Hz → 时延分辨率 "
                    f"{actual_res_ns:.6g} ns 已超出请求的时延窗 {max_delay_ns} ns，"
                    f"窗内不足两个 bin —— fail-loud，不返回退化 PDP"
                )
            n_bins = max(2, int(round(max_delay_ns / actual_res_ns)))
            n_fft = 256
            while n_fft < 4 * n_bins:
                n_fft *= 2
            plan["n_bins"] = n_bins
            plan["n_fft"] = n_fft
            return _PDP_SEGMENTS * n_fft

        samples, actual_fs = self._capture_iq_block(
            center_freq_hz, requested_fs, _plan_samples
        )
        n_bins, n_fft = plan["n_bins"], plan["n_fft"]
        actual_res_ns = 1e9 / actual_fs

        x = samples.reshape(_PDP_SEGMENTS, n_fft)
        x = x - x.mean()  # 去直流（LO 泄漏），见 docstring
        spectra = np.fft.fft(x, axis=1)
        psd = np.mean(np.abs(spectra) ** 2, axis=0)
        autocorr = np.fft.ifft(psd)  # 循环自相关估计（Wiener–Khinchin）
        power_lin = np.abs(autocorr[:n_bins])
        peak = float(np.max(power_lin))
        if not np.isfinite(peak) or peak <= 0.0:
            raise RuntimeError(
                "[FSVA] PDP 后处理峰值非正 / 非有限 —— 采集数据退化（全零 / NaN），"
                "不返回半截结果"
            )
        power_db = 10.0 * np.log10(np.maximum(power_lin, peak * 1e-12) / peak)
        delay_bins = [k * actual_res_ns for k in range(n_bins)]
        logger.info(
            f"[FSVA] PDP: fs={actual_fs/1e6:.3f} MHz (请求 {requested_fs/1e6:.3f}), "
            f"分辨率 {actual_res_ns:.1f} ns, {n_bins} bins"
        )
        return delay_bins, power_db.tolist()

    async def measure_doppler_spectrum(
        self,
        center_freq_hz: float,
        max_doppler_hz: float = 500.0,
        num_bins: int = 256,
    ) -> Tuple[List[float], List[float]]:
        """真实 FSVA 的多普勒功率谱测量 —— 长 TRACe:IQ 采集 + FFT。

        数学含义（工程近似，如实声明）：CE 输出经衰落信道的信号在 SA 中心频率附近
        的基带谱就是多普勒谱 —— 对复基带样本做分段 FFT 的模方平均（Welch，无窗），
        fftshift 到 ±fs/2 对称网格，再按目标 bin 宽度对细网格做**归组平均**
        （bin-average，线谱不会像点采样插值那样被漏掉；恰无细网格点落入的 bin
        回退线性插值），落到 [-max_doppler, +max_doppler] 的 num_bins 点目标网格，
        峰值归一化 0 dB（接口契约）。这是接收信号谱，**不是**参考互相关意义下的
        信道散射函数；DC bin 可能混入 LO 泄漏（不减均值 —— 零频分量在
        Rician/LOS 信道里是真实内容，减掉反而造假）。

        采集窗长 = 段数×段长/fs ≥ num_bins/max_doppler_hz 量级（覆盖多个多普勒
        周期）；采样率请求 4×max_doppler（地板 100 Hz，手册 p442），回读实际值，
        实际值 < 2×max_doppler（网格盖不住 ±max_doppler）→ RuntimeError fail-loud。

        SCPI 出处同 measure_pdp；解析失败 / 错误队列非空 → RuntimeError。
        """
        return await asyncio.to_thread(
            self._measure_doppler_sync, center_freq_hz, max_doppler_hz, num_bins
        )

    def _measure_doppler_sync(
        self,
        center_freq_hz: float,
        max_doppler_hz: float,
        num_bins: int,
    ) -> Tuple[List[float], List[float]]:
        """同步主体（asyncio.to_thread 内运行 —— P1-70 内审 F2：
        分钟级采集不再冻结事件循环；SCPI 事务互斥由
        _capture_iq_block 的 RLock 保证）。

        ⚠ 时长申报：real 采集为分钟级（Doppler 低速场景实算 63–123 s，
        失败场景含 VISA 超时最长约 6.5 min）。采集期间本 SA 驱动的 SCPI
        通道被事务锁独占 —— 其它 SCPI 调用（configure / get_trace / 诊断
        序列等）会**立即失败**（"IQ 采集事务独占中"，fail-fast 不冻结事件
        循环）；监控 get_metrics 只回内存状态、不发 SCPI，不受影响。"""
        if max_doppler_hz <= 0 or num_bins < 2:
            raise ValueError(
                f"[FSVA] measure_doppler_spectrum 参数非法: "
                f"max_doppler_hz={max_doppler_hz} (必须 > 0), "
                f"num_bins={num_bins} (必须 ≥ 2)"
            )
        requested_fs = max(4.0 * max_doppler_hz, _IQ_MIN_SAMPLE_RATE_HZ)

        plan: Dict[str, int] = {}

        def _plan_samples(actual_fs: float) -> int:
            if actual_fs < 2.0 * max_doppler_hz:
                raise RuntimeError(
                    f"[FSVA] 仪器实际采样率 {actual_fs:.6g} Hz < 2×max_doppler "
                    f"({2.0 * max_doppler_hz:.6g} Hz)，谱网格盖不住 "
                    f"±{max_doppler_hz} Hz —— fail-loud，不外插造谱"
                )
            n_fft = 256
            while n_fft < 8 * num_bins:
                n_fft *= 2
            plan["n_fft"] = n_fft
            return _DOPPLER_SEGMENTS * n_fft

        samples, actual_fs = self._capture_iq_block(
            center_freq_hz, requested_fs, _plan_samples
        )
        n_fft = plan["n_fft"]

        x = samples.reshape(_DOPPLER_SEGMENTS, n_fft)
        spectra = np.fft.fftshift(np.fft.fft(x, axis=1), axes=1)
        psd = np.mean(np.abs(spectra) ** 2, axis=0)
        grid_hz = np.fft.fftshift(np.fft.fftfreq(n_fft, d=1.0 / actual_fs))
        target_hz = np.linspace(-max_doppler_hz, max_doppler_hz, num_bins)
        # 归组平均（见 docstring）：目标 bin 边界取相邻中点，首尾各外扩半格
        half = (target_hz[1] - target_hz[0]) / 2.0
        edges = np.concatenate((
            [target_hz[0] - half],
            (target_hz[:-1] + target_hz[1:]) / 2.0,
            [target_hz[-1] + half],
        ))
        idx = np.digitize(grid_hz, edges) - 1
        valid = (idx >= 0) & (idx < num_bins)
        sums = np.bincount(idx[valid], weights=psd[valid], minlength=num_bins)
        counts = np.bincount(idx[valid], minlength=num_bins)
        power_target = np.where(
            counts > 0,
            sums / np.maximum(counts, 1),
            np.interp(target_hz, grid_hz, psd),  # 空 bin 回退
        )
        peak = float(np.max(power_target))
        if not np.isfinite(peak) or peak <= 0.0:
            raise RuntimeError(
                "[FSVA] 多普勒谱后处理峰值非正 / 非有限 —— 采集数据退化，"
                "不返回半截结果"
            )
        power_db = 10.0 * np.log10(np.maximum(power_target, peak * 1e-12) / peak)
        logger.info(
            f"[FSVA] Doppler: fs={actual_fs:.6g} Hz (请求 {requested_fs:.6g}), "
            f"±{max_doppler_hz} Hz / {num_bins} bins"
        )
        return target_hz.tolist(), power_db.tolist()

    # ── IQ 采集内部工序（两个测量方法共用） ────────────────────────────

    @staticmethod
    def _format_hz(value: float) -> str:
        """速率裸数值（Hz）——整数值不带小数点（`2000` 而非 `2000.0`）。"""
        return str(int(value)) if float(value).is_integer() else f"{value:.3f}"

    def _read_error_queue_entries(self) -> List[str]:
        """排水 SYSTem:ERRor[:NEXT]?（p969：每读一条删一条，空队列回 0,"No error"）。

        返回全部非零条目；读不出错误码（形态不认识）→ RuntimeError ——
        队列状态未知不能当干净。
        """
        entries: List[str] = []
        for _ in range(_IQ_ERROR_DRAIN_CAP):
            raw = (self._query(FsvaScpi.ERR) or "").strip()
            code_text = raw.split(",", 1)[0].strip()
            try:
                code = int(float(code_text))
            except ValueError:
                raise RuntimeError(
                    f"[FSVA] SYST:ERR? 回复解析不出错误码: {raw!r} —— "
                    f"队列状态未知，不当干净处理"
                )
            if code == 0:
                return entries
            entries.append(raw)
        entries.append(f"...(超过排水上限 {_IQ_ERROR_DRAIN_CAP} 条未读完)")
        return entries

    def _assert_error_queue_clean(self, stage: str) -> None:
        entries = self._read_error_queue_entries()
        if entries:
            raise RuntimeError(
                f"[FSVA] {stage} 后仪器错误队列非空: {entries} —— "
                f"fail-loud，不继续采集 / 不返回数据"
            )

    def _parse_iq_block_csv(self, raw: Any, num_samples: int) -> "np.ndarray":
        """解析 TRACe:IQ:DATA? 的 ASCII CSV 回复（FORMat[:DATA] ASCii，p915/933）。

        p897：返回值总数 = 2×样本数；IQBLock 排列 = I 块在前、Q 块在后
        （样例程序 p1036-1037 实证）。任何形态不符 → RuntimeError。
        """
        if not isinstance(raw, str) or not raw.strip():
            raise RuntimeError(
                f"[FSVA] TRACe:IQ:DATA? 空回复 / 非字符串 ({raw!r:.80}) —— "
                f"不返回半截数据"
            )
        try:
            # C 层解析（外审 #392 R1 建议）。坏数据 raise ValueError 依赖
            # numpy≥2（requirements 已锁地板；1.x 会静默截断且长度检查
            # 对「恰好 2N 个合法值+尾垃圾」不设防）。
            values = np.fromstring(raw.strip(), sep=",")
        except ValueError:
            raise RuntimeError(
                f"[FSVA] TRACe:IQ:DATA? 回复含非数值字段（前 80 字: "
                f"{raw.strip()[:80]!r}）—— 不返回半截数据"
            )
        if values.size != 2 * num_samples:
            raise RuntimeError(
                f"[FSVA] TRACe:IQ:DATA? 返回 {values.size} 个值，期望 "
                f"2×{num_samples}={2 * num_samples}（p897: 返回值总数 = 2×样本数）"
                f"—— 不返回半截数据"
            )
        i_block = values[:num_samples]
        q_block = values[num_samples:]
        return i_block + 1j * q_block

    def _capture_iq_block(self, *args, **kwargs):
        """事务级锁 wrapper（P1-70 内审 F2）：采集全程持 RLock，
        防其它线程的单条查询插进 IQ 命令序列中间。"""
        with self._scpi_rlock:
            return self._capture_iq_block_unlocked(*args, **kwargs)

    def _capture_iq_block_unlocked(
        self,
        center_freq_hz: float,
        requested_srate_hz: float,
        plan_samples: Callable[[float], int],
    ) -> Tuple["np.ndarray", float]:
        """一次完整 TRACe:IQ 采集：配置 → 回读实际速率 → 采集 → 解析 → 复原。

        `plan_samples(actual_fs) -> num_samples` 由调用方按实际速率定采集长度
        （也可在此 raise RuntimeError 拒绝退化速率）。

        工序（逐条手册出处见 FsvaScpi 常量注释）：
          1. FREQ:CENT（p809）
          2. TRAC:IQ:STAT ON（p895；样例程序 p1036 注释要求先于 SET）
          3. TRAC:IQ:SET 请求速率 + 占位样本数 128（p904 *RST 值）
          4. TRAC:IQ:SRAT? 回读实际速率（推断查询形，错误队列核对）
          5. TRAC:IQ:SET 实际速率 + 最终样本数（把仪器自报的值回传，消除歧义）
          6. TRAC:IQ:DATA:FORM IQBL + FORM ASC（p897/933）
          7. TRAC:IQ:DATA?（p897，超时按采集时长放大，finally 恢复）
          8. 每阶段后 SYST:ERR? 排水核对（p969）
          finally: TRAC:IQ:STAT OFF（p895，样例程序 p1037 同款收尾）
        """
        if self._visa_session is None:
            raise RuntimeError("[FSVA] Not connected —— IQ 采集需要已连接会话")

        self._write(FsvaScpi.SET_FREQ.format(freq=center_freq_hz))
        self._write(FsvaScpi.IQ_STATE_ON)
        try:
            self._write(FsvaScpi.IQ_SET.format(
                srate_hz=self._format_hz(requested_srate_hz), num_samples=128,
            ))
            self._assert_error_queue_clean("TRACe:IQ:SET（请求速率）")

            raw_srate = (self._query(FsvaScpi.IQ_SRATE_QUERY) or "").strip()
            self._assert_error_queue_clean("TRACe:IQ:SRATe?（推断查询形）")
            try:
                actual_fs = float(raw_srate)
            except ValueError:
                raise RuntimeError(
                    f"[FSVA] TRACe:IQ:SRATe? 回复解析不出数值: {raw_srate!r}"
                )
            if actual_fs <= 0:
                raise RuntimeError(
                    f"[FSVA] TRACe:IQ:SRATe? 回读到非正采样率: {actual_fs!r}"
                )

            num_samples = int(plan_samples(actual_fs))

            self._write(FsvaScpi.IQ_SET.format(
                srate_hz=self._format_hz(actual_fs), num_samples=num_samples,
            ))
            self._write(FsvaScpi.IQ_DATA_FORMAT_IQBLOCK)
            self._write(FsvaScpi.DATA_FMT_ASC)
            self._assert_error_queue_clean("IQ 采集参数配置")

            # 超时按数据量放大：采集时长 ×3 + 传输余量；finally 恢复原值
            #（照 P1-68 uxm 先例：finally + 会话 None 守卫，静默重连失败会把
            # _visa_session 置 None，此时恢复会抛 AttributeError 吃掉主异常）。
            acq_seconds = num_samples / actual_fs
            old_timeout = self._visa_session.timeout
            self._visa_session.timeout = int(
                max(15000, acq_seconds * 1000.0 * 3.0 + 30000)
            )
            try:
                raw_data = self._query(FsvaScpi.IQ_DATA_QUERY)
            finally:
                if self._visa_session is not None:
                    self._visa_session.timeout = old_timeout

            self._assert_error_queue_clean("TRACe:IQ:DATA?")
            samples = self._parse_iq_block_csv(raw_data, num_samples)
            return samples, actual_fs
        finally:
            # p895/样例程序 p1037：采集完成（或失败）都关掉 IQ 模式，恢复常规
            # 测量功能（TRAC:IQ ON 会关掉其它测量功能并 BLANK 走线显示）。
            if self._visa_session is not None:
                try:
                    self._write(FsvaScpi.IQ_STATE_OFF)
                except Exception as exc:  # noqa: BLE001 — 复原失败不掩盖主异常
                    logger.warning(f"[FSVA] TRACe:IQ:STATe OFF 复原失败: {exc}")

    # ===================================================================
    # 内部 VISA 工具方法 (SCPI 日志由基类 _write/_query 自动处理)
    # ===================================================================

    def _do_write(self, cmd: str) -> None:
        """发送 SCPI 写命令（由基类 _write() 自动调用）"""
        if not self._scpi_rlock.acquire(blocking=False):
            # 复核 F1：阻塞式拿锁会把事件循环线程冻在 acquire 上最长
            # ~6.5 min（IQ 采集事务）。非阻塞 + fail-fast：拿不到就立即
            # 报忙，调用方（端点/序列）快速失败而非冻死整个 API 服务。
            # 采集线程自己重入 RLock 不受影响（同线程 acquire 恒成功）。
            raise RuntimeError(
                "[FSVA] SCPI 通道被 IQ 采集事务独占中（分钟级）——"
                "等采集完成后重试"
            )
        try:
            if not self._visa_session:
                raise ConnectionError("[FSVA] Not connected")
            self._visa_session.write(cmd)
        finally:
            self._scpi_rlock.release()

    def _do_query(self, cmd: str) -> str:
        """发送 SCPI 查询并返回响应（由基类 _query() 自动调用）"""
        if not self._scpi_rlock.acquire(blocking=False):
            # 同 _do_write 的复核 F1 说明。
            raise RuntimeError(
                "[FSVA] SCPI 通道被 IQ 采集事务独占中（分钟级）——"
                "等采集完成后重试"
            )
        try:
            if not self._visa_session:
                raise ConnectionError("[FSVA] Not connected")
            return self._visa_session.query(cmd)
        finally:
            self._scpi_rlock.release()
