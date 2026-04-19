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
from app.hal.vna import MockVNA
from app.hal.positioner import MockPositioner
from app.hal.signal_generator import MockSignalGenerator
from app.hal.rf_switch import MockRfSwitch, EtslSwitchDriver

SUPPORTED_REAL_DRIVERS = {
    "channelEmulator": ["PROPSIM F64"],
    "baseStation": ["UXM 5G E7515B", "CMW500"],
    "signalAnalyzer": ["N9020B MXA", "FSW43"],
    "vectorSignalGenerator": ["N5182B MXG", "SMW200A", "SMU200A"],
    "vna": ["E5071C ENA"],
    "positioner": ["EMCenter"],
    "rfSwitch": ["EMCenter Switch"],
}

def has_real_driver(category_key: str, model_name: str) -> bool:
    """Helper to check if a real driver is backed by HAL implementation."""
    return model_name in SUPPORTED_REAL_DRIVERS.get(category_key, [])

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
            await self._initialize_from_db()
            self._initialized = True
            logger.info(f"Initialized {len(self.drivers)} instrument drivers")

        except Exception as e:
            logger.error(f"Failed to initialize HAL service: {e}")
            raise

    async def _initialize_from_db(self):
        """
        Initialize drivers from database instrument configuration.

        Flow:
        1. Read active categories + selected models + connections from DB
        2. Look up driver class in DRIVER_REGISTRY by (category_key, model)
        3. Instantiate driver with connection config
        4. Connect and configure

        If a real driver is not yet implemented for a model, falls back to
        mock driver with a warning log.
        """
        from app.db.database import SessionLocal
        from app.models.instrument import (
            InstrumentCategory as InstrumentCategoryModel,
            InstrumentModel as InstrumentModelDB,
            InstrumentConnection as InstrumentConnectionDB,
        )

        from app.hal.propsim_f64 import RealPropsimF64Driver
        from app.hal.uxm_base_station import RealUxmDriver
        from app.hal.cmw500_base_station import RealCmw500Driver
        from app.hal.ets_positioner import RealEtsEmcenterDriver
        from app.hal.keysight_ena import RealKeysightEnaDriver
        from app.hal.keysight_mxg import RealKeysightMxgDriver
        from app.hal.rs_smw200a import RealRsSmw200aDriver
        from app.hal.keysight_x_series_sa import RealKeysightXSeriesSaDriver
        from app.hal.rs_fsw import RealRsFswDriver

        # Driver registry: maps (category_key, model_name) → DriverClass
        # When real VISA/SCPI drivers are implemented, register them here.
        # Format: "category_key": { "Model Name": RealDriverClass }
        REAL_DRIVER_REGISTRY: Dict[str, Dict[str, type]] = {
            "channelEmulator": {
                "PROPSIM F64": RealPropsimF64Driver,
            },
            "baseStation": {
                "UXM 5G E7515B": RealUxmDriver,
                "CMW500": RealCmw500Driver,
            },
            "signalAnalyzer": {
                "N9020B MXA": RealKeysightXSeriesSaDriver,
                "FSW43": RealRsFswDriver,
            },
            "vectorSignalGenerator": {
                "N5182B MXG": RealKeysightMxgDriver,
                "SMW200A": RealRsSmw200aDriver,
                "SMU200A": RealRsSmw200aDriver,
            },
            "vna": {
                "E5071C ENA": RealKeysightEnaDriver,
            },
            "positioner": {
                "EMCenter": RealEtsEmcenterDriver,
            },
            "rfSwitch": {
                "EMCenter Switch": EtslSwitchDriver,
            },
        }

        # Mock fallback registry (same category → mock driver class mapping)
        MOCK_FALLBACK: Dict[str, type] = {
            "channelEmulator": MockChannelEmulator,
            "baseStation": MockBaseStation,
            "signalAnalyzer": MockSignalAnalyzer,
            "vectorSignalGenerator": MockSignalGenerator,
            "vna": MockVNA,
            "positioner": MockPositioner,
            "rfSwitch": MockRfSwitch,
        }

        db = SessionLocal()
        try:
            categories = db.query(InstrumentCategoryModel).filter(
                InstrumentCategoryModel.is_active == True
            ).order_by(InstrumentCategoryModel.display_order).all()

            for cat in categories:
                if not cat.selected_model_id:
                    logger.info(f"[HAL-REAL] {cat.category_key}: no model selected, skipping")
                    continue

                model = db.query(InstrumentModelDB).filter(
                    InstrumentModelDB.id == cat.selected_model_id
                ).first()
                if not model:
                    logger.warning(f"[HAL-REAL] {cat.category_key}: selected model not found")
                    continue

                conn = db.query(InstrumentConnectionDB).filter(
                    InstrumentConnectionDB.category_id == cat.id
                ).first()

                # Build driver config from DB
                driver_config = {
                    "model": model.model,
                    "vendor": model.vendor,
                    "full_name": model.full_name,
                    **(model.capabilities or {}),
                }
                if conn:
                    driver_config.update({
                        "endpoint": conn.endpoint,
                        "ip": conn.controller_ip,
                        "port": conn.port,
                        "protocol": conn.protocol,
                    })
                    # Merge connection_params (e.g. port_maps for RF Switch Option B)
                    if conn.connection_params and isinstance(conn.connection_params, dict):
                        driver_config.update(conn.connection_params)

                # Determine driver class based on mode and supported models
                DriverClass = None

                if self.mode == DriverMode.REAL:
                    category_drivers = REAL_DRIVER_REGISTRY.get(cat.category_key, {})
                    DriverClass = category_drivers.get(model.model)

                if DriverClass:
                    logger.info(
                        f"[HAL-{self.mode.value.upper()}] {cat.category_key}: using REAL driver "
                        f"{DriverClass.__name__} for {model.vendor} {model.model}"
                    )
                else:
                    DriverClass = MOCK_FALLBACK.get(cat.category_key)
                    if DriverClass:
                        logger.warning(
                            f"[HAL-REAL] {cat.category_key}: no real driver for "
                            f"{model.vendor} {model.model}, falling back to {DriverClass.__name__}"
                        )
                    else:
                        logger.info(
                            f"[HAL-REAL] {cat.category_key}: no driver available, skipping"
                        )
                        continue

                # Instantiate and connect
                driver = DriverClass(
                    instrument_id=f"{cat.category_key}_{str(cat.id)[:8]}",
                    config=driver_config,
                )
                try:
                    success = await driver.connect()
                    if success:
                        self.drivers[cat.category_key] = driver
                        logger.info(
                            f"[HAL-{self.mode.value.upper()}] {cat.category_key}: connected → "
                            f"{model.vendor} {model.model}"
                        )
                        # Update connection status in DB
                        if conn:
                            conn.status = "connected"
                            from datetime import datetime
                            conn.last_connected_at = datetime.utcnow()
                            db.commit()
                    else:
                        logger.error(
                            f"[HAL-REAL] {cat.category_key}: connection failed"
                        )
                        if conn:
                            conn.status = "error"
                            conn.last_error = "Connection failed during HAL init"
                            db.commit()
                except Exception as e:
                    logger.error(
                        f"[HAL-REAL] {cat.category_key}: exception during connect: {e}"
                    )
                    if conn:
                        conn.status = "error"
                        conn.last_error = str(e)
                        db.commit()

            logger.info(
                f"[HAL-REAL] Driver factory complete: "
                f"{len(self.drivers)} drivers initialized"
            )

        finally:
            db.close()

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


async def switch_hal_mode(new_mode: DriverMode) -> Dict[str, Any]:
    """
    运行时切换 HAL 驱动模式（Mock ↔ Real）

    流程: shutdown 旧驱动 → 用新模式重新初始化
    返回切换结果和当前激活的驱动列表。
    """
    global _hal_service

    old_mode = _hal_service.mode if _hal_service else "none"
    logger.info(f"[HAL] Switching mode: {old_mode} → {new_mode.value}")

    # 1. 关闭旧驱动
    if _hal_service:
        await _hal_service.shutdown()

    # 2. 用新模式重新初始化
    _hal_service = InstrumentHALService(mode=new_mode)
    await _hal_service.initialize()

    # 3. 收集结果
    active_drivers = list(_hal_service.drivers.keys())
    logger.info(
        f"[HAL] Mode switched to {new_mode.value}, "
        f"{len(active_drivers)} drivers active: {active_drivers}"
    )

    return {
        "previous_mode": str(old_mode),
        "current_mode": new_mode.value,
        "active_drivers": active_drivers,
        "driver_count": len(active_drivers),
    }
