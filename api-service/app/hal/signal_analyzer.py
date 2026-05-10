"""
Signal Analyzer HAL

Provides abstract interface for Spectrum Analyzers / Signal Analyzers.

3GPP TR 38.151 § 7.3 channel-model validation extends this driver with three
additional acquisition primitives — measure_pdp, measure_doppler_spectrum,
capture_iq — that map onto the SA's vector-signal-analysis (VSA) capability.
Real drivers implement them via SCPI options like 89600 VSA, FSV K7N, etc.
Mock impl synthesizes the expected shapes from analytical models so the
service layer can be developed end-to-end without hardware.
"""

import asyncio
import logging
import random
from typing import Dict, Any, List, Tuple
from datetime import datetime

import numpy as np

from app.hal.base import (
    InstrumentDriver,
    InstrumentStatus,
    InstrumentCapability,
    InstrumentMetrics,
)

logger = logging.getLogger(__name__)


class SignalAnalyzerDriver(InstrumentDriver):
    """
    Abstract interface for Signal Analyzers (HAL Layer 2)
    """

    async def setup_spectrum(self, center_freq_hz: float, span_hz: float, rbw_hz: float) -> bool:
        """
        Configure basic spectrum analysis parameters.
        """
        raise NotImplementedError

    async def measure_channel_power(self, bandwidth_hz: float) -> float:
        """
        Measure RMS channel power over a specific bandwidth.
        Returns:
            dbm: Power in dBm
        """
        raise NotImplementedError

    async def get_trace(self) -> List[float]:
        """
        Fetch the current Amplitude trace in dBm.
        """
        raise NotImplementedError

    # ==================================================================
    # Channel-model validation acquisition (3GPP TR 38.151 § 7.3)
    # ==================================================================

    async def measure_pdp(
        self,
        center_freq_hz: float,
        max_delay_ns: float = 2000.0,
        resolution_ns: float = 10.0,
    ) -> Tuple[List[float], List[float]]:
        """[A2] Measure Power Delay Profile of received CE-emulated channel.

        Real drivers (89600 VSA option B7Q, FSV K7N, etc.) acquire IQ on
        the burst, compute time-domain channel impulse response via
        autocorrelation or matched-filter, return (delay_ns, power_db) bins.

        Args:
            center_freq_hz: SA center frequency (matches CE channel center)
            max_delay_ns: PDP window length in ns (typical 2000 ns for UMa)
            resolution_ns: time-bin resolution (typical 10 ns at 100 MHz BW)

        Returns:
            (delay_bins_ns: List[float], power_db: List[float])
            Both same length; power normalized so the strongest tap is 0 dB.
        """
        raise NotImplementedError

    async def measure_doppler_spectrum(
        self,
        center_freq_hz: float,
        max_doppler_hz: float = 500.0,
        num_bins: int = 256,
    ) -> Tuple[List[float], List[float]]:
        """[A2] Measure Doppler power spectrum at SA RF input.

        Real drivers acquire long IQ capture (multiple Doppler periods),
        FFT, normalize. Returns symmetric spectrum around DC.

        Args:
            center_freq_hz: SA center frequency
            max_doppler_hz: spectrum spans [-max, +max] Hz
            num_bins: number of frequency bins (FFT length)

        Returns:
            (frequency_bins_hz: List[float], power_density_db: List[float])
            Both same length; power normalized so peak is 0 dB.
        """
        raise NotImplementedError

    async def capture_iq(
        self,
        center_freq_hz: float,
        sample_rate_hz: float,
        num_samples: int,
    ) -> Tuple[List[float], List[float]]:
        """[A2] Capture raw IQ samples for offline correlation analysis.

        Used by spatial-correlation validation: capture at multiple SGH
        positions, compute Pearson correlation between captured streams
        to derive the measured spatial correlation matrix.

        Args:
            center_freq_hz: SA center frequency
            sample_rate_hz: complex IQ sample rate
            num_samples: capture length

        Returns:
            (i_samples: List[float], q_samples: List[float])
            Same length, real/imag parts of complex baseband. Caller
            reconstructs complex array via np.array(I) + 1j*np.array(Q).
        """
        raise NotImplementedError


class MockSignalAnalyzer(SignalAnalyzerDriver):
    """Fallback Mock implementation"""

    def __init__(self, instrument_id: str, config: Dict[str, Any]):
        super().__init__(instrument_id, config)
        self._center_freq = 1e9

    async def connect(self) -> bool:
        self._set_status(InstrumentStatus.CONNECTED)
        return True

    async def disconnect(self) -> bool:
        self._set_status(InstrumentStatus.DISCONNECTED)
        return True

    async def configure(self, config: Dict[str, Any]) -> bool:
        return True

    async def get_capabilities(self) -> list[InstrumentCapability]:
        return [
            InstrumentCapability(name="spectrum", description="Spectrum sweep", supported=True, parameters={})
        ]

    async def get_metrics(self) -> InstrumentMetrics:
        return InstrumentMetrics(
            timestamp=datetime.utcnow(),
            metrics={"center_freq": self._center_freq}
        )

    async def reset(self) -> bool:
        self._set_status(InstrumentStatus.READY)
        return True

    async def setup_spectrum(self, center_freq_hz: float, span_hz: float, rbw_hz: float) -> bool:
        self._center_freq = center_freq_hz
        return True

    async def measure_channel_power(self, bandwidth_hz: float) -> float:
        await asyncio.sleep(0.2)
        return -50.0 + random.uniform(-1, 1)

    async def get_trace(self) -> List[float]:
        return [random.uniform(-100, -80) for _ in range(500)]

    async def measure_pdp(
        self,
        center_freq_hz: float,
        max_delay_ns: float = 2000.0,
        resolution_ns: float = 10.0,
    ) -> Tuple[List[float], List[float]]:
        """Mock PDP — exponential decay with multipath clusters + noise floor.

        Shape: 3 clusters at 0/200/600 ns, 30 dB peak-to-noise, intra-cluster
        Gaussian spread σ=20 ns. Matches generate_mock_pdp() characteristics.
        """
        n_bins = int(max_delay_ns / resolution_ns)
        delays = [i * resolution_ns for i in range(n_bins)]
        delays_arr = np.array(delays)
        cluster_delays = [0.0, 200.0, 600.0]
        cluster_powers_db = [0.0, -8.0, -15.0]
        cluster_sigma_ns = 20.0

        power_lin = np.zeros(n_bins)
        for cd, cp_db in zip(cluster_delays, cluster_powers_db):
            spread = np.exp(-((delays_arr - cd) ** 2) / (2 * cluster_sigma_ns ** 2))
            power_lin += (10 ** (cp_db / 10)) * spread
        # Noise floor at -40 dB relative
        noise_floor = 10 ** (-40 / 10)
        power_lin += noise_floor * (1 + 0.1 * np.random.randn(n_bins))
        power_db = 10 * np.log10(np.maximum(power_lin, 1e-12))
        # Normalize peak to 0 dB
        power_db = power_db - float(np.max(power_db))
        return delays, power_db.tolist()

    async def measure_doppler_spectrum(
        self,
        center_freq_hz: float,
        max_doppler_hz: float = 500.0,
        num_bins: int = 256,
    ) -> Tuple[List[float], List[float]]:
        """Mock Doppler spectrum — Jakes (classical) shape: U-curve with
        peaks at ±f_d, normalized to 0 dB peak. Matches
        generate_classical_doppler_spectrum() output."""
        # Symmetric around 0
        freqs = np.linspace(-max_doppler_hz, max_doppler_hz, num_bins)
        # Jakes spectrum: S(f) = 1/(π * f_d * sqrt(1 - (f/f_d)²)) for |f| < f_d
        f_norm = freqs / max_doppler_hz
        valid = np.abs(f_norm) < 0.999  # avoid div-by-zero at edges
        power_lin = np.zeros_like(freqs)
        power_lin[valid] = 1.0 / np.sqrt(1 - f_norm[valid] ** 2 + 1e-9)
        # Add small measurement noise (0.5 dB)
        power_db = 10 * np.log10(np.maximum(power_lin, 1e-6))
        power_db = power_db - float(np.max(power_db))
        power_db = power_db + 0.5 * np.random.randn(num_bins)
        return freqs.tolist(), power_db.tolist()

    async def capture_iq(
        self,
        center_freq_hz: float,
        sample_rate_hz: float,
        num_samples: int,
    ) -> Tuple[List[float], List[float]]:
        """Mock IQ capture — Rayleigh-faded baseband (real chamber would be
        CE channel emulation output). Returns I and Q lists, caller turns
        them into complex with np.array(I) + 1j*np.array(Q)."""
        await asyncio.sleep(0.05)  # simulate acquisition time
        i = np.random.randn(num_samples)
        q = np.random.randn(num_samples)
        return i.tolist(), q.tolist()
