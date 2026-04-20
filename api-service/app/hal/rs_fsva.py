"""
R&S FSVA Signal Analyzer Driver
================================

Real HAL Driver for Rohde & Schwarz FSVA series Signal & Spectrum Analyzers.
FSVA shares core SCPI with FSW but has additional spectrum analysis capabilities.

Reference: R&S FSVA3000 User Manual, SCPI Command Reference.
"""

import logging
import asyncio
from typing import Dict, Any, List
from datetime import datetime

from app.hal.base import (
    InstrumentStatus,
    InstrumentCapability,
    InstrumentMetrics,
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
        self.ip_address: str = config.get("ip", "192.168.100.31")
        self.port: int = config.get("port", 5025)
        self._visa_rm = None
        self._visa_session = None

    async def connect(self) -> bool:
        self._set_status(InstrumentStatus.CONNECTING)
        try:
            import pyvisa
            self._visa_rm = pyvisa.ResourceManager("@py")
            resource_string = f"TCPIP::{self.ip_address}::{self.port}::SOCKET"
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
            if self._visa_rm:
                self._visa_rm.close()
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
    # 内部 VISA 工具方法 (含 SCPI trace logging)
    # ===================================================================

    def _write(self, cmd: str) -> None:
        """发送 SCPI 写命令"""
        if not self._visa_session:
            raise ConnectionError("[FSVA] Not connected")
        self._log_scpi_write(cmd)
        self._visa_session.write(cmd)

    def _query(self, cmd: str) -> str:
        """发送 SCPI 查询并返回响应"""
        if not self._visa_session:
            raise ConnectionError("[FSVA] Not connected")
        self._log_scpi_write(cmd)
        response = self._visa_session.query(cmd)
        self._log_scpi_response(cmd, response)
        return response
