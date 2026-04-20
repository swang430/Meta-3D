"""
R&S ZNA Vector Network Analyzer Driver
=======================================

Real HAL Driver for Rohde & Schwarz ZNA series VNAs.
ZNA shares the same SCPI command set as ZNB with extensions.

Reference: R&S ZNA User Manual, SCPI Command Reference.
"""

import logging
import asyncio
from typing import Dict, Any, List
from datetime import datetime
import numpy as np

from app.hal.base import (
    InstrumentStatus,
    InstrumentCapability,
    InstrumentMetrics,
)
from app.hal.vna import VNADriver

logger = logging.getLogger(__name__)


class ZnaScpi:
    """R&S ZNA SCPI command set"""
    IDN = "*IDN?"
    RST = "*RST"
    OPC = "*OPC?"
    ERR = "SYST:ERR?"

    # Channel & Sweep
    SET_POINTS = "SENSe1:SWEep:POINts {points}"
    SET_START_FREQ = "SENSe1:FREQuency:STARt {freq}"
    SET_STOP_FREQ = "SENSe1:FREQuency:STOP {freq}"
    SET_CENTER_FREQ = "SENSe1:FREQuency:CENTer {freq}"
    SET_SPAN = "SENSe1:FREQuency:SPAN {span}"
    SET_IFBW = "SENSe1:BANDwidth:RESolution {bw}"

    # Trace / Measurement
    DEF_MEAS = "CALCulate1:PARameter:SDEFine 'Trc1', '{param}'"
    SEL_TRACE = "CALCulate1:PARameter:SELect 'Trc1'"
    DATA_FMT = "FORMat:DATA ASCii"

    # Trigger / Sweep control
    INIT_CONT_OFF = "INITiate1:CONTinuous OFF"
    INIT_IMM = "INITiate1:IMMediate; *OPC?"
    SWEEP_SINGLE = "SENSe1:SWEep:MODE SINGle"

    # Data readout
    READ_SDATA = "CALCulate1:DATA? SDATa"       # Complex S-data pairs
    READ_FDATA = "CALCulate1:DATA? FDATa"       # Formatted data

    # Power / Port
    SET_SOURCE_POWER = "SOURce1:POWer1 {power}"  # dBm

    # Calibration
    CORR_AUTO = "SENSe1:CORRection:COLLect:METHod:DEFine"

    # Display
    DISP_UPD_ON = "SYSTem:DISPlay:UPDate ON"
    DISP_UPD_OFF = "SYSTem:DISPlay:UPDate OFF"


class RealRsZnaDriver(VNADriver):
    """
    Real HAL Driver for R&S ZNA Vector Network Analyzer

    Supports:
    - S-parameter measurement (S11, S21, S12, S22, multiport)
    - Frequency sweep configuration
    - Complex data readout (magnitude + phase)
    - SCPI trace logging via HAL base class

    三层架构: InstrumentDriver → VNADriver → RealRsZnaDriver
    """

    def __init__(self, instrument_id: str, config: Dict[str, Any]):
        super().__init__(instrument_id, config)
        self.ip_address: str = config.get("ip", "192.168.100.30")
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
            # R&S instruments over raw socket need read/write terminators
            self._visa_session.read_termination = "\n"
            self._visa_session.write_termination = "\n"

            idn = self._query(ZnaScpi.IDN).strip()
            logger.info(f"[ZNA] Connected to {idn}")

            # Initialize for automation
            self._write(ZnaScpi.DATA_FMT)
            self._write(ZnaScpi.DISP_UPD_OFF)   # Speed up remote operation
            self._write(ZnaScpi.INIT_CONT_OFF)   # Single sweep mode

            self._set_status(InstrumentStatus.CONNECTED)
            return True
        except Exception as e:
            logger.error(f"[ZNA] Connection failed ({self.ip_address}:{self.port}): {e}")
            self._set_status(InstrumentStatus.ERROR, str(e))
            return False

    async def disconnect(self) -> bool:
        try:
            if self._visa_session:
                self._write(ZnaScpi.DISP_UPD_ON)  # Restore display
                self._visa_session.close()
                self._visa_session = None
            if self._visa_rm:
                self._visa_rm.close()
                self._visa_rm = None
            self._set_status(InstrumentStatus.DISCONNECTED)
            return True
        except Exception as e:
            logger.error(f"[ZNA] Disconnect error: {e}")
            return False

    async def configure(self, config: Dict[str, Any]) -> bool:
        """Apply runtime configuration"""
        try:
            if "source_power_dbm" in config:
                self._write(ZnaScpi.SET_SOURCE_POWER.format(power=config["source_power_dbm"]))
            if "if_bandwidth_hz" in config:
                self._write(ZnaScpi.SET_IFBW.format(bw=config["if_bandwidth_hz"]))
            self._query(ZnaScpi.OPC)
            return True
        except Exception as e:
            logger.error(f"[ZNA] Configure failed: {e}")
            return False

    async def setup_sweep(
        self, start_freq_hz: float, stop_freq_hz: float, points: int
    ) -> bool:
        """Configure frequency sweep range and resolution"""
        try:
            self._write(ZnaScpi.SET_START_FREQ.format(freq=start_freq_hz))
            self._write(ZnaScpi.SET_STOP_FREQ.format(freq=stop_freq_hz))
            self._write(ZnaScpi.SET_POINTS.format(points=points))
            self._query(ZnaScpi.OPC)
            logger.info(
                f"[ZNA] Sweep: {start_freq_hz/1e9:.3f}-{stop_freq_hz/1e9:.3f} GHz, "
                f"{points} points"
            )
            return True
        except Exception as e:
            logger.error(f"[ZNA] Setup sweep failed: {e}")
            return False

    async def measure_s_param(self, measurement: str = "S21") -> bool:
        """
        Define and trigger an S-parameter measurement.

        Args:
            measurement: S-parameter name, e.g. 'S11', 'S21', 'S22'
        """
        try:
            self._set_status(InstrumentStatus.BUSY)
            self._write(ZnaScpi.DEF_MEAS.format(param=measurement))
            self._write(ZnaScpi.SEL_TRACE)
            self._write(ZnaScpi.SWEEP_SINGLE)

            # Trigger single sweep and wait for completion
            self._query(ZnaScpi.INIT_IMM)

            self._set_status(InstrumentStatus.READY)
            logger.info(f"[ZNA] {measurement} measurement complete")
            return True
        except Exception as e:
            logger.error(f"[ZNA] Measure {measurement} failed: {e}")
            self._set_status(InstrumentStatus.ERROR, str(e))
            return False

    async def get_trace_data(self) -> List[complex]:
        """
        Read complex S-parameter data from active trace.

        Returns:
            List of complex values (Real + jImag) per frequency point
        """
        try:
            data_str = self._query(ZnaScpi.READ_SDATA)
            values = list(map(float, data_str.strip().split(",")))
            # R&S returns Real, Imag, Real, Imag...
            real_parts = values[0::2]
            imag_parts = values[1::2]
            complex_trace = [complex(r, i) for r, i in zip(real_parts, imag_parts)]
            logger.info(f"[ZNA] Read {len(complex_trace)} complex data points")
            return complex_trace
        except Exception as e:
            logger.error(f"[ZNA] Get trace data failed: {e}")
            return []

    async def get_capabilities(self) -> list[InstrumentCapability]:
        return [
            InstrumentCapability(
                name="s_parameters",
                description="Full S-parameter measurement (S11, S21, S12, S22, multiport)",
                supported=True,
                parameters={
                    "ports": 4,
                    "frequency_range_ghz": [0.01, 67],
                },
            ),
            InstrumentCapability(
                name="time_domain",
                description="Time domain analysis (TDR/TDT)",
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
            self._write(ZnaScpi.RST)
            self._query(ZnaScpi.OPC)
            self._write(ZnaScpi.DATA_FMT)
            logger.info("[ZNA] Reset to default state")
            return True
        except Exception as e:
            logger.error(f"[ZNA] Reset failed: {e}")
            return False

    # ===================================================================
    # 内部 VISA 工具方法 (含 SCPI trace logging)
    # ===================================================================

    def _write(self, cmd: str) -> None:
        """发送 SCPI 写命令"""
        if not self._visa_session:
            raise ConnectionError("[ZNA] Not connected")
        self._log_scpi_write(cmd)
        self._visa_session.write(cmd)

    def _query(self, cmd: str) -> str:
        """发送 SCPI 查询并返回响应"""
        if not self._visa_session:
            raise ConnectionError("[ZNA] Not connected")
        self._log_scpi_write(cmd)
        response = self._visa_session.query(cmd)
        self._log_scpi_response(cmd, response)
        return response
