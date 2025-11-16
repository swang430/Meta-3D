"""
Mock instrument drivers for development without hardware.

These classes simulate the behavior of real instruments with realistic data
and controlled randomness to enable testing of calibration workflows.
"""
import random
import numpy as np
from typing import Dict, List, Tuple, Optional
from datetime import datetime


class MockBaseStationEmulator:
    """
    Mock Base Station Emulator (BSE)

    Simulates: Keysight UXM 5G, R&S CMW500
    """

    def __init__(self):
        self.is_connected = False
        self.cell_active = False
        self.ue_registered = False

    async def connect(self, ip: str) -> bool:
        """Connect to BSE (mocked)"""
        self.is_connected = True
        return True

    async def configure_cell(
        self,
        frequency_mhz: float,
        bandwidth_mhz: float,
        modulation: str
    ) -> bool:
        """Configure 5G NR cell"""
        self.cell_active = True
        return True

    async def register_ue(self) -> bool:
        """Register UE (DUT)"""
        self.ue_registered = True
        return True

    async def start_dl_traffic(self, tx_power_dbm: float) -> bool:
        """Start downlink traffic"""
        return True

    async def get_throughput(self) -> float:
        """Get current throughput (Mbps)"""
        # Simulate realistic 5G throughput with some variation
        base_throughput = 800.0  # Mbps
        variation = random.gauss(0, 50)  # ±50 Mbps std dev
        return max(0, base_throughput + variation)

    async def get_radio_measurements(self) -> Dict[str, float]:
        """Get radio measurements (RSRP, RSRQ, SINR)"""
        return {
            'rsrp_dbm': random.gauss(-80.0, 2.0),  # -80 dBm ± 2 dB
            'rsrq_db': random.gauss(-10.0, 1.0),   # -10 dB ± 1 dB
            'sinr_db': random.gauss(20.0, 2.0),    # 20 dB ± 2 dB
        }

    async def disconnect(self) -> bool:
        """Disconnect from BSE"""
        self.is_connected = False
        return True


class MockChannelEmulator:
    """
    Mock Channel Emulator

    Simulates: Keysight PROPSIM F64, Spirent VR5
    """

    def __init__(self):
        self.is_connected = False
        self.channel_active = False
        self.current_scenario = None

    async def connect(self, ip: str) -> bool:
        """Connect to channel emulator"""
        self.is_connected = True
        return True

    async def configure_channel(
        self,
        scenario: str,
        frequency_mhz: float,
        doppler_hz: float = 0.0
    ) -> bool:
        """Configure 3GPP channel model"""
        self.current_scenario = scenario
        self.channel_active = True
        return True

    async def set_probe_weights(
        self,
        weights: List[Dict[str, float]]
    ) -> bool:
        """Set probe complex weights"""
        # In mock mode, just accept the weights
        return True

    async def start(self) -> bool:
        """Start channel emulation"""
        return True

    async def stop(self) -> bool:
        """Stop channel emulation"""
        return True

    async def disconnect(self) -> bool:
        """Disconnect"""
        self.is_connected = False
        return True


class MockSignalAnalyzer:
    """
    Mock Signal Analyzer / Spectrum Analyzer

    Simulates: Keysight N9040B, R&S FSW
    """

    def __init__(self):
        self.is_connected = False

    async def connect(self, ip: str) -> bool:
        """Connect to signal analyzer"""
        self.is_connected = True
        return True

    async def measure_power(
        self,
        center_freq_mhz: float,
        span_mhz: float
    ) -> float:
        """Measure power in specified bandwidth (dBm)"""
        # Simulate realistic power measurement
        base_power = -20.0  # dBm
        noise = random.gauss(0, 0.2)  # ±0.2 dB measurement uncertainty
        return base_power + noise

    async def measure_spectrum(
        self,
        start_freq_mhz: float,
        stop_freq_mhz: float,
        rbw_khz: float
    ) -> Tuple[np.ndarray, np.ndarray]:
        """Measure spectrum (frequency, power arrays)"""
        num_points = 1001
        freqs = np.linspace(start_freq_mhz, stop_freq_mhz, num_points)

        # Simulate spectrum with signal + noise
        powers = -80 * np.ones(num_points)  # Noise floor
        # Add signal peak at center
        center_idx = num_points // 2
        signal_shape = np.exp(-((np.arange(num_points) - center_idx) / 50) ** 2)
        powers += 60 * signal_shape  # Signal peak at -20 dBm

        # Add measurement noise
        powers += np.random.normal(0, 0.5, num_points)

        return freqs, powers

    async def disconnect(self) -> bool:
        """Disconnect"""
        self.is_connected = False
        return True


class MockProbeController:
    """
    Mock Probe Control System

    Simulates RF switch matrix and probe power control
    """

    def __init__(self, num_probes: int = 32):
        self.num_probes = num_probes
        self.is_connected = False
        self.active_probe = None

    async def connect(self) -> bool:
        """Connect to probe controller"""
        self.is_connected = True
        return True

    async def select_probe(self, probe_id: int, polarization: str = 'V') -> bool:
        """Select active probe"""
        if probe_id < 1 or probe_id > self.num_probes:
            raise ValueError(f"Invalid probe_id: {probe_id}")

        self.active_probe = probe_id
        return True

    async def set_attenuation(self, probe_id: int, attenuation_db: float) -> bool:
        """Set probe attenuation"""
        return True

    async def get_probe_status(self, probe_id: int) -> Dict[str, any]:
        """Get probe health status"""
        return {
            'probe_id': probe_id,
            'connected': True,
            'vswr': random.uniform(1.1, 1.3),  # Good VSWR
            'temperature_c': random.uniform(20, 25),
            'healthy': True
        }

    async def disconnect(self) -> bool:
        """Disconnect"""
        self.is_connected = False
        return True


class MockDUT:
    """
    Mock Device Under Test (DUT)

    Simulates a standard calibration DUT (e.g., reference smartphone or dipole)
    with known TRP/TIS values.
    """

    def __init__(
        self,
        model: str,
        serial: str,
        known_trp_dbm: float,
        known_tis_dbm: float
    ):
        self.model = model
        self.serial = serial
        self.known_trp_dbm = known_trp_dbm
        self.known_tis_dbm = known_tis_dbm

    def get_radiated_power_pattern(
        self,
        theta_deg: float,
        phi_deg: float
    ) -> float:
        """
        Get radiated power at specific angle (dBm)

        Simulates realistic antenna pattern
        """
        # Simple cosine pattern for demonstration
        theta_rad = np.radians(theta_deg)
        phi_rad = np.radians(phi_deg)

        # Directivity pattern (simplified)
        pattern_db = 10 * np.cos(theta_rad) ** 2

        # Base power + pattern + noise
        power_dbm = self.known_trp_dbm + pattern_db + random.gauss(0, 0.3)

        return power_dbm

    def get_sensitivity_pattern(
        self,
        theta_deg: float,
        phi_deg: float
    ) -> float:
        """
        Get sensitivity at specific angle (dBm)

        Lower value = better sensitivity
        """
        theta_rad = np.radians(theta_deg)

        # Pattern (simplified)
        pattern_db = -5 * np.cos(theta_rad) ** 2

        # Base sensitivity + pattern + noise
        sensitivity_dbm = self.known_tis_dbm + pattern_db + random.gauss(0, 0.5)

        return sensitivity_dbm


class MockInstrumentOrchestrator:
    """
    Orchestrates all mock instruments for calibration testing
    """

    def __init__(self):
        self.bse = MockBaseStationEmulator()
        self.channel_emulator = MockChannelEmulator()
        self.signal_analyzer = MockSignalAnalyzer()
        self.probe_controller = MockProbeController(num_probes=32)
        self.dut: Optional[MockDUT] = None

    async def connect_all(self) -> bool:
        """Connect to all instruments"""
        await self.bse.connect("192.168.1.100")
        await self.channel_emulator.connect("192.168.1.101")
        await self.signal_analyzer.connect("192.168.1.102")
        await self.probe_controller.connect()
        return True

    def load_standard_dut(
        self,
        model: str,
        serial: str,
        known_trp_dbm: float,
        known_tis_dbm: float
    ):
        """Load standard DUT with known calibration values"""
        self.dut = MockDUT(model, serial, known_trp_dbm, known_tis_dbm)

    async def measure_trp_at_angle(
        self,
        theta_deg: float,
        phi_deg: float,
        frequency_mhz: float,
        tx_power_dbm: float
    ) -> float:
        """
        Measure radiated power at specific angle

        Returns: Measured power in dBm
        """
        if not self.dut:
            raise ValueError("No DUT loaded")

        # Select closest probe
        await self.probe_controller.select_probe(
            probe_id=self._angle_to_probe_id(theta_deg, phi_deg)
        )

        # Configure BSE
        await self.bse.configure_cell(
            frequency_mhz=frequency_mhz,
            bandwidth_mhz=20.0,
            modulation="QPSK"
        )
        await self.bse.start_dl_traffic(tx_power_dbm=tx_power_dbm)

        # Get DUT pattern
        dut_power = self.dut.get_radiated_power_pattern(theta_deg, phi_deg)

        # Measure with signal analyzer
        measured_power = await self.signal_analyzer.measure_power(
            center_freq_mhz=frequency_mhz,
            span_mhz=20.0
        )

        # Combine DUT pattern with measurement uncertainty
        return dut_power + (measured_power - (-20.0))  # Offset adjustment

    async def measure_tis_at_angle(
        self,
        theta_deg: float,
        phi_deg: float,
        frequency_mhz: float
    ) -> float:
        """
        Measure sensitivity at specific angle

        Returns: Sensitivity in dBm (lower is better)
        """
        if not self.dut:
            raise ValueError("No DUT loaded")

        # Select probe
        await self.probe_controller.select_probe(
            probe_id=self._angle_to_probe_id(theta_deg, phi_deg)
        )

        # Configure BSE
        await self.bse.configure_cell(
            frequency_mhz=frequency_mhz,
            bandwidth_mhz=20.0,
            modulation="64QAM"
        )

        # Get DUT sensitivity pattern
        sensitivity = self.dut.get_sensitivity_pattern(theta_deg, phi_deg)

        return sensitivity

    def _angle_to_probe_id(self, theta_deg: float, phi_deg: float) -> int:
        """Map angle to closest probe ID (simplified)"""
        # Simplified: 32 probes distributed on sphere
        # In reality, would use actual probe positions
        probe_id = int((phi_deg / 360.0) * 16) + 1  # 16 in azimuth
        if theta_deg > 60:
            probe_id += 16  # Upper/lower ring
        return min(max(probe_id, 1), 32)

    async def disconnect_all(self) -> bool:
        """Disconnect from all instruments"""
        await self.bse.disconnect()
        await self.channel_emulator.disconnect()
        await self.signal_analyzer.disconnect()
        await self.probe_controller.disconnect()
        return True
