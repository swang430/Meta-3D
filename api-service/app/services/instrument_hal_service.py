"""
Instrument HAL Service

Manages instrument drivers (Mock or Real) and provides unified interface
for monitoring data collection.

Phase 2.4.5: Mock drivers for development
Phase 3+: Real drivers for production
"""

import asyncio
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from enum import Enum

from app.hal.base import InstrumentDriver, InstrumentStatus
from app.hal.channel_emulator import MockChannelEmulator
from app.hal.base_station import MockBaseStation
from app.hal.signal_analyzer import MockSignalAnalyzer


logger = logging.getLogger(__name__)


class MetricsCache:
    """
    Simple TTL cache for monitoring metrics

    Reduces redundant HAL queries while ensuring data freshness
    """

    def __init__(self, ttl_seconds: float = 0.5):
        """
        Initialize cache

        Args:
            ttl_seconds: Time-to-live in seconds (default: 0.5s)
        """
        self.ttl_seconds = ttl_seconds
        self._cache: Optional[Dict[str, Any]] = None
        self._cache_time: Optional[datetime] = None
        self._lock = asyncio.Lock()
        self._hits = 0
        self._misses = 0

    async def get(self) -> Optional[Dict[str, Any]]:
        """Get cached metrics if still valid"""
        async with self._lock:
            if self._cache is None or self._cache_time is None:
                self._misses += 1
                return None

            age = datetime.utcnow() - self._cache_time
            if age.total_seconds() > self.ttl_seconds:
                # Cache expired
                self._misses += 1
                logger.debug(f"Cache expired (age: {age.total_seconds():.3f}s)")
                return None

            self._hits += 1
            logger.debug(f"Cache hit (age: {age.total_seconds():.3f}s)")
            return self._cache

    async def set(self, metrics: Dict[str, Any]):
        """Update cache with new metrics"""
        async with self._lock:
            self._cache = metrics
            self._cache_time = datetime.utcnow()
            logger.debug("Cache updated")

    async def clear(self):
        """Clear the cache"""
        async with self._lock:
            self._cache = None
            self._cache_time = None
            logger.debug("Cache cleared")

    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        total = self._hits + self._misses
        hit_rate = (self._hits / total * 100) if total > 0 else 0.0
        return {
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate_percent": round(hit_rate, 2),
            "ttl_seconds": self.ttl_seconds
        }


class DriverMode(str, Enum):
    """Driver operation mode"""
    MOCK = "mock"  # Mock drivers for development/testing
    REAL = "real"  # Real hardware drivers for production


class InstrumentHALService:
    """
    Manages instrument driver lifecycle and data collection

    Responsibilities:
    - Initialize and manage instrument drivers
    - Collect metrics from all instruments
    - Aggregate data for monitoring
    - Handle driver errors and reconnection
    """

    def __init__(self, mode: DriverMode = DriverMode.MOCK, cache_ttl: float = 0.5):
        self.mode = mode
        self.drivers: Dict[str, InstrumentDriver] = {}
        self._initialized = False
        self._monitoring_task: Optional[asyncio.Task] = None
        self._metrics_cache = MetricsCache(ttl_seconds=cache_ttl)

    async def initialize(self):
        """Initialize all instrument drivers"""
        if self._initialized:
            logger.warning("InstrumentHALService already initialized")
            return

        logger.info(f"Initializing InstrumentHALService in {self.mode} mode")

        try:
            if self.mode == DriverMode.MOCK:
                await self._initialize_mock_drivers()
            else:
                await self._initialize_real_drivers()

            self._initialized = True
            logger.info(f"Initialized {len(self.drivers)} instrument drivers")

        except Exception as e:
            logger.error(f"Failed to initialize HAL service: {e}")
            raise

    async def _initialize_mock_drivers(self):
        """Initialize mock drivers for development"""

        # Channel Emulator
        channel_emulator = MockChannelEmulator(
            instrument_id="channel_emulator_1",
            config={
                "model": "Keysight PROPSIM F64",
                "tx_ports": 4,
                "rx_ports": 4
            }
        )
        await channel_emulator.connect()
        await channel_emulator.configure({
            "channel_model": "3GPP_38.901",
            "scenario": "UMi",
            "tx_antennas": 4,
            "rx_antennas": 4
        })
        self.drivers["channel_emulator"] = channel_emulator

        # Base Station Emulator
        base_station = MockBaseStation(
            instrument_id="base_station_1",
            config={
                "model": "Keysight 5G Network Emulator",
                "frequency_range_mhz": [450, 6000]
            }
        )
        await base_station.connect()
        await base_station.configure({
            "frequency_mhz": 3500.0,
            "bandwidth_mhz": 100.0
        })
        await base_station.start_cell()
        self.drivers["base_station"] = base_station

        # Signal Analyzer
        signal_analyzer = MockSignalAnalyzer(
            instrument_id="signal_analyzer_1",
            config={
                "model": "Rohde & Schwarz FSW",
                "frequency_range_mhz": [9, 6000]
            }
        )
        await signal_analyzer.connect()
        await signal_analyzer.configure({
            "center_freq_mhz": 3500.0,
            "span_mhz": 200.0
        })
        await signal_analyzer.start_measurement()
        self.drivers["signal_analyzer"] = signal_analyzer

        logger.info("Mock drivers initialized successfully")

    async def _initialize_real_drivers(self):
        """
        Initialize real hardware drivers

        Phase 3+: Implement real driver initialization based on configuration
        """
        # TODO: Phase 3 - Implement real driver factory and initialization
        raise NotImplementedError("Real drivers not yet implemented")

    async def shutdown(self):
        """Shutdown all drivers and cleanup"""
        logger.info("Shutting down InstrumentHALService")

        # Log cache statistics before shutdown
        cache_stats = self._metrics_cache.get_stats()
        logger.info(f"Cache statistics: {cache_stats}")

        # Clear cache
        await self._metrics_cache.clear()

        if self._monitoring_task:
            self._monitoring_task.cancel()
            try:
                await self._monitoring_task
            except asyncio.CancelledError:
                pass

        for name, driver in self.drivers.items():
            try:
                await driver.disconnect()
                logger.info(f"Disconnected driver: {name}")
            except Exception as e:
                logger.error(f"Error disconnecting {name}: {e}")

        self.drivers.clear()
        self._initialized = False

    async def get_aggregated_metrics(self) -> Dict[str, Any]:
        """
        Get aggregated metrics from all instruments

        Returns monitoring data in the format expected by monitoring.py
        Uses cache to reduce redundant HAL queries
        """
        if not self._initialized:
            logger.warning("HAL service not initialized, returning empty metrics")
            return {}

        # Check cache first
        cached_metrics = await self._metrics_cache.get()
        if cached_metrics is not None:
            return cached_metrics

        try:
            # Cache miss - collect metrics from all drivers
            metrics_tasks = [
                driver.get_metrics()
                for driver in self.drivers.values()
            ]
            all_metrics = await asyncio.gather(*metrics_tasks, return_exceptions=True)

            # Aggregate metrics from different instruments
            now = datetime.utcnow().isoformat()

            # Extract relevant metrics
            channel_metrics = None
            base_station_metrics = None
            analyzer_metrics = None

            for i, result in enumerate(all_metrics):
                if isinstance(result, Exception):
                    logger.error(f"Error getting metrics from driver {i}: {result}")
                    continue

                driver_name = list(self.drivers.keys())[i]
                if driver_name == "channel_emulator":
                    channel_metrics = result.metrics
                elif driver_name == "base_station":
                    base_station_metrics = result.metrics
                elif driver_name == "signal_analyzer":
                    analyzer_metrics = result.metrics

            # Build monitoring data structure
            # Map instrument metrics to monitoring display metrics
            aggregated = self._build_monitoring_data(
                channel_metrics,
                base_station_metrics,
                analyzer_metrics,
                now
            )

            # Update cache with fresh data
            await self._metrics_cache.set(aggregated)

            return aggregated

        except Exception as e:
            logger.error(f"Error aggregating metrics: {e}")
            return {}

    def _build_monitoring_data(
        self,
        channel_metrics: Optional[Dict[str, Any]],
        base_station_metrics: Optional[Dict[str, Any]],
        analyzer_metrics: Optional[Dict[str, Any]],
        timestamp: str
    ) -> Dict[str, Any]:
        """
        Build monitoring data structure from instrument metrics

        Maps instrument-specific metrics to standardized monitoring metrics
        """

        # Default values
        throughput = 0.0
        snr = 0.0
        eirp = 0.0
        quiet_zone_uniformity = 0.0
        temperature = 23.0

        # Extract throughput from channel emulator
        if channel_metrics:
            throughput = channel_metrics.get("throughput_mbps", 0.0)
            snr = channel_metrics.get("snr_db", 0.0)

        # Extract EIRP from analyzer
        if analyzer_metrics:
            power_dbm = analyzer_metrics.get("measured_power_dbm", -50.0)
            # EIRP approximation (power + antenna gain)
            # Assuming 3dBi antenna gain for now
            eirp = power_dbm + 3.0

        # Calculate quiet zone uniformity (simplified)
        # In real system, this would be calculated from multiple probe measurements
        if channel_metrics:
            path_loss = channel_metrics.get("path_loss_db", 80.0)
            # Uniformity inversely related to path loss variation
            # This is simplified; real calculation uses spatial correlation
            quiet_zone_uniformity = max(0.5, 1.0 - (abs(path_loss - 80.0) / 100.0))

        # Temperature from base station (if available)
        if base_station_metrics:
            # Mock base stations don't expose temperature yet
            # This would come from environmental sensors
            pass

        # Status determination
        def get_status(value: float, warning_threshold: float, critical_threshold: float,
                       is_higher_better: bool = True) -> str:
            if is_higher_better:
                if value < critical_threshold:
                    return "critical"
                elif value < warning_threshold:
                    return "warning"
            else:
                if value > critical_threshold:
                    return "critical"
                elif value > warning_threshold:
                    return "warning"
            return "normal"

        return {
            "throughput": {
                "value": round(throughput, 2),
                "unit": "Mbps",
                "timestamp": timestamp,
                "status": get_status(throughput, 140, 120)
            },
            "snr": {
                "value": round(snr, 2),
                "unit": "dB",
                "timestamp": timestamp,
                "status": get_status(snr, 22, 18)
            },
            "quiet_zone_uniformity": {
                "value": round(quiet_zone_uniformity, 3),
                "unit": "dB",
                "timestamp": timestamp,
                "status": get_status(quiet_zone_uniformity, 0.7, 0.6)
            },
            "eirp": {
                "value": round(eirp, 2),
                "unit": "dBm",
                "timestamp": timestamp,
                "status": get_status(eirp, 43, 41)
            },
            "temperature": {
                "value": round(temperature, 1),
                "unit": "°C",
                "timestamp": timestamp,
                "status": get_status(temperature, 25, 28, is_higher_better=False)
            }
        }

    async def get_driver_status(self) -> Dict[str, Dict[str, Any]]:
        """Get status of all drivers"""
        status = {}
        for name, driver in self.drivers.items():
            status[name] = {
                "instrument_id": driver.instrument_id,
                "status": driver.get_status().value,
                "last_error": driver.get_last_error(),
                "config": driver.config
            }
        return status

    async def reconnect_driver(self, driver_name: str) -> bool:
        """Reconnect a specific driver"""
        if driver_name not in self.drivers:
            logger.error(f"Driver not found: {driver_name}")
            return False

        try:
            driver = self.drivers[driver_name]
            await driver.disconnect()
            await asyncio.sleep(0.5)
            success = await driver.connect()

            if success:
                logger.info(f"Successfully reconnected driver: {driver_name}")
            else:
                logger.warning(f"Failed to reconnect driver: {driver_name}")

            return success

        except Exception as e:
            logger.error(f"Error reconnecting driver {driver_name}: {e}")
            return False

    def get_cache_stats(self) -> Dict[str, Any]:
        """Get metrics cache statistics"""
        return self._metrics_cache.get_stats()


# Global singleton instance
_hal_service: Optional[InstrumentHALService] = None


def get_hal_service() -> InstrumentHALService:
    """Get the global HAL service instance"""
    global _hal_service
    if _hal_service is None:
        _hal_service = InstrumentHALService(mode=DriverMode.MOCK)
    return _hal_service


async def initialize_hal_service(mode: DriverMode = DriverMode.MOCK):
    """Initialize the global HAL service"""
    global _hal_service
    _hal_service = InstrumentHALService(mode=mode)
    await _hal_service.initialize()
    logger.info("Global HAL service initialized")


async def shutdown_hal_service():
    """Shutdown the global HAL service"""
    global _hal_service
    if _hal_service:
        await _hal_service.shutdown()
        _hal_service = None
        logger.info("Global HAL service shutdown complete")
