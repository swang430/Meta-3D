"""
Instrument HAL Service

Manages instrument drivers (Mock or Real) and provides unified interface
for monitoring data collection.

Phase 2.4.5: Mock drivers for development
Phase 3+: Real drivers for production
"""

import asyncio
import logging
import re
from dataclasses import dataclass
from typing import Dict, Any, Optional, List, Tuple, TYPE_CHECKING
from datetime import datetime, timedelta
from enum import Enum

from app.hal.base import (
    InstrumentDriver,
    InstrumentStatus,
    resolve_configured_tcpip_connection,
)
from app.hal.base_station_manifest import (
    BaseStationAdapterRegistration,
    validate_base_station_adapter_registrations,
)

if TYPE_CHECKING:
    # P3-5: only needed for the type annotation on _log_readiness_report;
    # the runtime import lives inside _initialize_from_db so the existing
    # lazy-import discipline at the top of the module stays uniform.
    from app.services.readiness import ReadinessReport
from app.hal.channel_emulator import MockChannelEmulator
from app.hal.base_station import MockBaseStation
from app.hal.signal_analyzer import MockSignalAnalyzer
from app.hal.vna import MockVNA
from app.hal.positioner import MockPositioner
from app.hal.signal_generator import MockSignalGenerator
from app.hal.rf_switch import MockRfSwitch, EtslSwitchDriver

# Driver registry: maps (category_key, model_name) → DriverClass.
# Lazy-built so the HAL driver modules (which import each other + the
# service layer) don't form an import cycle at module-load time.
# Single source of truth for: (a) which real drivers exist, (b) which
# DriverClass HAL bootstrap instantiates, (c) per-model capability
# declarations exposed in the catalog API (P2-3).
_REAL_DRIVER_REGISTRY_CACHE: Optional[Dict[str, Dict[str, type]]] = None


def _validate_base_station_adapter_ids(drivers: Dict[str, type]) -> None:
    """兼容旧调用点：由声明式 manifest 校验注册身份。"""
    registrations = {
        model_name: BaseStationAdapterRegistration(
            manifest=getattr(driver_class, "adapter_manifest", None),
            driver_class=driver_class,
            profile_model=getattr(driver_class, "adapter_profile_model", None),
        )
        for model_name, driver_class in drivers.items()
    }
    validate_base_station_adapter_registrations(registrations)


def get_base_station_adapter_registration(
    model_name: str,
) -> BaseStationAdapterRegistration:
    """Return the single registered adapter declaration for a catalog model."""
    driver_class = _real_driver_registry()["baseStation"].get(model_name)
    if driver_class is None:
        raise KeyError(f"unknown base-station model: {model_name!r}")
    registration = BaseStationAdapterRegistration(
        manifest=driver_class.adapter_manifest,
        driver_class=driver_class,
        profile_model=getattr(driver_class, "adapter_profile_model", None),
    )
    validate_base_station_adapter_registrations({model_name: registration})
    return registration


def _real_driver_registry() -> Dict[str, Dict[str, type]]:
    """Lazy-init + cache the (category_key, model_name) → DriverClass table.

    Imports are deferred to first call because the driver modules pull in
    base classes / VISA shims that take real time to load, and they may
    themselves import from this service module — top-level imports would
    deadlock on first import.
    """
    global _REAL_DRIVER_REGISTRY_CACHE
    if _REAL_DRIVER_REGISTRY_CACHE is not None:
        return _REAL_DRIVER_REGISTRY_CACHE

    from app.hal.propsim_f64 import RealPropsimF64Driver
    from app.hal.propsim_fs16 import RealPropsimFs16Driver
    from app.hal.uxm_base_station import RealUxmDriver
    from app.hal.cmw500_base_station import RealCmw500Driver
    from app.hal.ets_positioner import RealEtsEmcenterDriver
    from app.hal.aerotech_positioner import RealAerotechDriver
    from app.hal.keysight_ena import RealKeysightEnaDriver
    from app.hal.keysight_mxg import RealKeysightMxgDriver
    from app.hal.rs_smw200a import RealRsSmw200aDriver
    from app.hal.keysight_x_series_sa import RealKeysightXSeriesSaDriver
    from app.hal.rs_fsw import RealRsFswDriver
    from app.hal.rs_zna import RealRsZnaDriver
    from app.hal.rs_fsva import RealRsFsvaDriver

    registry = {
        "channelEmulator": {
            "PROPSIM F64": RealPropsimF64Driver,
            "PROPSIM FS16": RealPropsimFs16Driver,
        },
        "baseStation": {
            "UXM 5G E7515B": RealUxmDriver,
            "CMW500": RealCmw500Driver,
        },
        "signalAnalyzer": {
            "N9020B MXA": RealKeysightXSeriesSaDriver,
            "FSW43": RealRsFswDriver,
            "FSVA3000": RealRsFsvaDriver,
        },
        "vectorSignalGenerator": {
            "N5182B MXG": RealKeysightMxgDriver,
            "SMW200A": RealRsSmw200aDriver,
            "SMU200A": RealRsSmw200aDriver,
        },
        "vna": {
            "E5071C ENA": RealKeysightEnaDriver,
            "ZNA67": RealRsZnaDriver,
        },
        "positioner": {
            "EMCenter": RealEtsEmcenterDriver,
            "A3200": RealAerotechDriver,
        },
        "rfSwitch": {
            "EMCenter Switch": EtslSwitchDriver,
        },
    }
    _validate_base_station_adapter_ids(registry["baseStation"])
    _REAL_DRIVER_REGISTRY_CACHE = registry
    return _REAL_DRIVER_REGISTRY_CACHE


def get_real_driver_class(category_key: str, model_name: str) -> Optional[type]:
    """P2-3: look up the registered real-driver class for a catalog entry,
    without instantiating or connecting. Returns ``None`` if no real
    driver is registered (caller falls back to mock or marks as
    pending_dev).

    Catalog API uses this to read ``DriverClass.model_capabilities`` so
    "what does FS16 support?" can be answered before HAL Reload —
    operator can see capability mismatches at binding-edit time, not at
    runtime.
    """
    return _real_driver_registry().get(category_key, {}).get(model_name)


def has_real_driver(category_key: str, model_name: str) -> bool:
    """Helper to check if a real driver is backed by HAL implementation."""
    return get_real_driver_class(category_key, model_name) is not None

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

    # ⚠ P1-35：这四个方法里**不要再加 per-event 日志**（原先每次命中/失效/
    # 更新/清空各打一条 `logger.debug`）。
    #
    # 为什么删：这些行**没有一条能回答将来会被问到的问题**。命中率由下面的
    # `_hits` / `_misses` 计数器如实记着，每次再打一行日志是**同一事实的
    # 第二份记录**，而且是最贵的那份。
    #
    # ⚠ 如实申报这次删除的**代价**（内审 F2）：计数器目前**唯一**被读出的
    # 地方是 `shutdown()` 里那行 `Cache statistics` —— 也就是说
    #   · 运行中看不到缓存状态（`get_cache_stats()` 全仓零调用方）；
    #   · `docker kill` / OOM / SIGKILL 时那行根本不会打，计数器一次都没
    #     被读过就随进程消失。
    # 判断这个缺口可接受：TTL 只有 0.5 秒，判错的代价是指标陈旧半秒。
    # 要运行中可见，正解是把它接进指标端点 —— **另立片**，别在这里加。
    #
    # 有多贵（2026-08-05 实测容器 app.log）：这四条占 **90.1%**
    # （6273 / 6965 行）。监控广播器是 `while True: if active_connections:
    # ... sleep(1.0)` —— 也就是**只在 GUI 连着时以 1 Hz 刷**，
    # 恰好在操作员盯着日志面板的时候刷得最凶：200 行窗口只覆盖 53 秒，
    # 里面约 4 行是有用的。
    #
    # 要观测缓存，正确形态是**计数器/指标**，不是每次一行日志。
    async def get(self) -> Optional[Dict[str, Any]]:
        """Get cached metrics if still valid"""
        async with self._lock:
            if self._cache is None or self._cache_time is None:
                self._misses += 1
                return None

            age = datetime.utcnow() - self._cache_time
            if age.total_seconds() > self.ttl_seconds:
                self._misses += 1
                return None

            self._hits += 1
            return self._cache

    async def set(self, metrics: Dict[str, Any]):
        """Update cache with new metrics"""
        async with self._lock:
            self._cache = metrics
            self._cache_time = datetime.utcnow()

    async def clear(self):
        """Clear the cache"""
        async with self._lock:
            self._cache = None
            self._cache_time = None

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
    """Driver operation mode.

    Three semantics distinguish what happens to instruments with a
    per-instrument ``InstrumentCategory.driver_mode`` override:

    - ``MOCK``: global default is mock; per-instrument ``'real'``
      override IS still honoured (drivers for those categories
      connect to hardware). The usual dev / GUI HAL switch target —
      operators set one instrument to ``'real'`` specifically to
      keep it live even in mock dev.
    - ``REAL``: global default is real; per-instrument ``'mock'``
      override is still honoured.
    - ``MOCK_FORCE``: per-instrument ``'real'`` is **overridden**.
      Every driver loads as Mock, no hardware traffic. Use this
      from one-shot inspection tools (``scripts/driver_selftest``,
      smoke checks) where the operator must not accidentally poke
      configured equipment.
    """
    MOCK = "mock"  # Mock by default; per-instrument 'real' STILL connects to hardware
    REAL = "real"  # Real by default; per-instrument 'mock' STILL goes mock
    MOCK_FORCE = "mock_force"  # Hard mock; overrides per-instrument 'real' too (no hardware traffic)


# 类目 → mock 驱动类。**这是唯一一份**，装载时按它选类、``is_mock_driver`` 按它判真假。
#
# ⚠️ 2026-08-10 P1-48 S0：这里原来有两份 —— 模块级一份手写的 ``_MOCK_DRIVER_CLASSES``，
#    方法 ``_initialize_from_db`` 里另一份 ``MOCK_FALLBACK``，靠一句注释"keep in sync"
#    维持一致；另有第三处 ``isinstance(driver, tuple(MOCK_FALLBACK.values()))`` 在就地
#    重新推导同一件事。外审连续三轮攻破为此写的守门测试（它只能靠解析源码猜有没有人
#    改过那份局部表，而写法枚举不完）。**合成一份之后，"两份分叉"这件事不复存在。**
_MOCK_FALLBACK_BY_CATEGORY: Dict[str, type] = {
    "channelEmulator": MockChannelEmulator,
    "baseStation": MockBaseStation,
    "signalAnalyzer": MockSignalAnalyzer,
    "vectorSignalGenerator": MockSignalGenerator,
    "vna": MockVNA,
    "positioner": MockPositioner,
    "rfSwitch": MockRfSwitch,
}

# 从上表派生，不再手写 —— 供 service 之外的调用方（如 commissioning 建会话）
# 问"这是不是真驱动"。见 ``is_mock_driver``。
_MOCK_DRIVER_CLASSES: tuple = tuple(_MOCK_FALLBACK_BY_CATEGORY.values())


def is_mock_driver(driver) -> bool:
    """True iff ``driver`` is a mock-fallback instance (not real hardware).

    ``None`` (driver absent) → ``False`` — absence is not the same as "mock";
    the caller decides what an absent driver means for its gate. A real driver
    instance (any class outside ``_MOCK_DRIVER_CLASSES``) → ``False``.
    """
    return driver is not None and isinstance(driver, _MOCK_DRIVER_CLASSES)


@dataclass(frozen=True)
class Cmw500Lte2x2Readiness:
    """Read-only preview bound to the selected LabProfile connection."""

    status: str
    adapter_registered: bool
    connection_id: str | None
    model: str | None
    identity_verified: bool | None
    firmware_version: str | None
    options: list[str]
    formal_enabled: bool
    formal_updated_at: str | None
    fdd_ready: bool
    tdd_ready: bool
    detail: str
    binding_digest: str | None = None


def build_cmw500_lte_2x2_readiness(
    db,
    *,
    lab_profile_id,
    hal,
    binding_preview=None,
) -> Cmw500Lte2x2Readiness:
    """Project current CMW readiness without opening or changing a session."""

    from app.services.base_station_binding import build_base_station_binding_preview
    from app.services.lab_resolution import resolve_lab_profile

    def unavailable(
        detail: str,
        *,
        status: str = "warning",
        adapter_registered: bool = False,
        preview=None,
        model: str | None = None,
    ) -> Cmw500Lte2x2Readiness:
        resolved = (
            preview.resolved_binding
            if preview is not None and isinstance(preview.resolved_binding, dict)
            else {}
        )
        formal = resolved.get("formal_capability")
        if not isinstance(formal, dict):
            formal = {}
        return Cmw500Lte2x2Readiness(
            status=status,
            adapter_registered=adapter_registered,
            connection_id=(
                preview.instrument_connection_id if preview is not None else None
            ),
            model=model or (preview.model_name if preview is not None else None),
            identity_verified=None,
            firmware_version=None,
            options=[],
            formal_enabled=formal.get("enabled") is True,
            formal_updated_at=formal.get("updated_at"),
            fdd_ready=False,
            tdd_ready=False,
            detail=detail,
            binding_digest=(preview.binding_digest if preview is not None else None),
        )

    lab = resolve_lab_profile(db, lab_profile_id)
    if binding_preview is None:
        binding_preview = build_base_station_binding_preview(db, hal, lab)
    if binding_preview.status == "invalid":
        return unavailable(binding_preview.detail, preview=binding_preview)
    if binding_preview.adapter_id != "cmw500":
        return unavailable(
            "selected baseStation is not the registered CMW500 adapter",
            status="not_applicable",
            preview=binding_preview,
        )
    if binding_preview.execution_mode == "simulated":
        return unavailable(
            "CMW500 is using the diagnostic mock driver",
            status="diagnostic",
            adapter_registered=True,
            preview=binding_preview,
        )
    drivers = getattr(hal, "drivers", None)
    driver = drivers.get("baseStation") if isinstance(drivers, dict) else None
    if driver is None:
        return unavailable(
            "selected CMW500 driver is not loaded",
            adapter_registered=True,
            preview=binding_preview,
        )

    identity = driver.get_base_station_identity()
    identity_verified = driver.identity_snapshot_verified is True
    resolved = binding_preview.resolved_binding or {}
    approval = resolved.get("formal_capability") or {}
    preview = {
        "resolution": {
            "adapter": "cmw500",
            "status": "configured",
            "execution_mode": "real",
        },
        "instrument_connection_id": binding_preview.instrument_connection_id,
        "cmw500_lte_2x2_formal_capability": approval,
    }
    fdd = driver.evaluate_lte_2x2_formal_capability(preview, duplex="fdd")
    tdd = driver.evaluate_lte_2x2_formal_capability(preview, duplex="tdd")
    status = "ready" if fdd.ready or tdd.ready else "warning"
    return Cmw500Lte2x2Readiness(
        status=status,
        adapter_registered=True,
        connection_id=binding_preview.instrument_connection_id,
        model=identity.model or binding_preview.model_name,
        identity_verified=identity_verified,
        firmware_version=identity.firmware_version,
        options=list(identity.options),
        formal_enabled=approval["enabled"],
        formal_updated_at=approval["updated_at"],
        fdd_ready=fdd.ready,
        tdd_ready=tdd.ready,
        detail=f"FDD: {fdd.reason}; TDD: {tdd.reason}",
        binding_digest=binding_preview.binding_digest,
    )


def connected_log_fields(driver, category_key: str, vendor: str, model: str):
    """算出「connected →」那行日志的正文与结构化字段。

    抽成纯函数是为了**能被门直接测到**（内审 F1：原先这几行嵌在
    ``_initialize_from_db`` 里，把它整条改回「按全局开关标」测试照样全绿 ——
    本片最主要的那处修复零门守着）。

    ⚠️ 前缀与 ``driver_source`` 字段**同源**（内审 F4）：两者都从
    ``is_mock_driver(driver)`` 这一个判断派生。原先前缀用 is_mock_driver、
    字段用 ``getattr(driver, "driver_source", "-")``，两个来源会打架，
    而且 ``"-"`` 不在日志过滤器的白名单里、会静默回落成全局开关的值。
    """
    src = "mock" if is_mock_driver(driver) else "real"
    msg = (
        f"[HAL-{src.upper()}] {category_key}: connected → "
        f"{vendor} {model} "
        # 实际装上的驱动类名 —— 就绪表的 detail 里早有，只有这行丢了它
        f"(driver={type(driver).__name__})"
    )
    extra = {
        "instrument_id": category_key,
        "driver_source": src,
        "simulated": src == "mock",
    }
    return msg, extra


_IPV4_RE = re.compile(r"^\d{1,3}(?:\.\d{1,3}){3}$")


def preflight_target(binding) -> Optional[Tuple[str, int]]:
    """Resolve ``(host, port)`` for the TCP reachability preflight from a
    connection binding.

    P1-13: consume the same structured ``controller_ip`` / ``port`` and
    VISA/endpoint source set as the real drivers
    (``TCPIP0::192.168.0.132::inst0::INSTR`` / ``192.168.0.132:5025``). Before
    this, the preflight only fired when controller_ip+port were both set, so
    bindings that store the address only in the resource string were NEVER
    network-probed — their connect failure got classified ``scpi`` and their
    subnet looked reachable even with no route to it.

    P1-51: conflicting explicit sources return ``None`` so readiness never probes
    one host before the driver rejects a resource targeting another host.

    Only the HOST decides the network-reachability verdict (a reachable host
    refuses a closed port = "alive"); the port is best-effort — an explicit
    ``:PORT`` in the string if present, else 5025 (raw-SCPI). Returns ``None``
    when no IPv4 host can be resolved or the binding conflicts (caller skips preflight → row stays
    network_reachable=None / 未探测)."""
    if binding is None:
        return None
    if isinstance(binding, dict):
        config = binding
    else:
        config = {
            "controller_ip": getattr(binding, "controller_ip", None),
            "port": getattr(binding, "port", None),
            "endpoint": getattr(binding, "endpoint", None),
        }
    host, port, _, error = resolve_configured_tcpip_connection(
        config
    )
    if error or not host or not _IPV4_RE.fullmatch(host):
        return None
    return host, port if port is not None else 5025


async def tcp_preflight(
    host: str,
    port: int,
    timeout_s: float = 1.0,
) -> tuple[bool, Optional[str]]:
    """Quick TCP-reachability probe before a heavier VISA/socket open.

    Returns ``(host_alive, reason_when_dead)``.

    What "alive" means here is "we got a TCP-level reply within
    ``timeout_s``". That covers two cases:
    - Clean connect — the instrument is listening on this exact port.
    - Connection refused — host is up, port is closed. Driver may still
      succeed if it uses a different port (e.g. VISA HiSLIP on 4880 when
      we preflighted 5025). We treat host-up-port-closed as "alive" so
      we don't skip legitimately-reachable instruments.

    What "dead" means is timeout / no route / DNS failure — connecting
    won't succeed without operator intervention. Surfacing this in 1 s
    instead of the 10 s VISA default × N instruments is the whole point
    of this preflight.

    Field motivation (CAICT 2026-05-13): switching the Mac between F64's
    subnet (192.168.0.x) and UXM's subnet (192.168.1.x) leaves half the
    instruments unreachable. Pre-#15 HAL init took ~60 s waiting for
    each VISA timeout in series; with preflight it's ~5 s.
    """
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port),
            timeout=timeout_s,
        )
    except asyncio.TimeoutError:
        return False, f"SYN timeout after {timeout_s:.1f}s — host {host} unreachable"
    except ConnectionRefusedError:
        # Host responded with RST. It's up, just not listening on this port.
        # Treat as alive so VISA-on-different-port drivers aren't skipped.
        return True, None
    except OSError as e:
        # ENETUNREACH / EHOSTUNREACH / DNS failure / etc — driver can't recover.
        return False, f"{type(e).__name__}: {e}"
    try:
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass
    except Exception:
        pass
    return True, None


# P1-15: negative-control / canary addresses for the preflight trust check.
# RFC 5737 TEST-NET ranges are reserved for documentation and MUST NOT be
# routable on any correct network — a TCP probe to them can only ever come back
# "dead" (timeout / no route). If one comes back "alive", something on the path
# (transparent proxy / corporate VPN / captive portal / blackhole-accept
# gateway) is answering SYNs on behalf of destinations that cannot exist — which
# means tcp_preflight's "connect-or-refused = host alive" heuristic is fooled and
# EVERY "alive" verdict is meaningless. Field trigger: real-mode HAL with no
# instruments showed all subnets 可达 because a VPN tunnel accepted every connect.
_PREFLIGHT_CANARIES: Tuple[Tuple[str, int], ...] = (
    ("192.0.2.1", 5025),       # RFC 5737 TEST-NET-1
    ("198.51.100.1", 5025),    # RFC 5737 TEST-NET-2
)


async def detect_preflight_trustworthy(timeout_s: float = 1.0) -> bool:
    """P1-15: probe the guaranteed-unroutable canary addresses.

    Returns ``False`` (preflight signal NOT trustworthy) if ANY canary answers
    at the TCP layer — a proxy/VPN/gateway is accepting connections for
    addresses that cannot exist, so ``tcp_preflight`` can no longer tell a
    reachable instrument apart from a lying network. Returns ``True`` when every
    canary is correctly dead (timeout / no route), i.e. a normal LAN where
    preflight verdicts can be trusted.

    Probes run concurrently so the worst case (honest network → every canary
    times out) costs ``timeout_s`` once, not once-per-canary, and only the
    caller (HAL init, once per reload) pays it — never the per-instrument loop.
    """
    results = await asyncio.gather(
        *(tcp_preflight(host, port, timeout_s=timeout_s) for host, port in _PREFLIGHT_CANARIES)
    )
    for alive, _reason in results:
        if alive:
            return False
    return True


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
        # P3-5: composite readiness snapshot, refreshed on each
        # initialize() / reload. None until the first init completes.
        # See app/services/readiness.py for the dataclass shape; the
        # snapshot is what GET /instruments/hal/readiness returns to
        # the GUI, so a future driver swap that doesn't refresh this
        # would silently leak stale state — keep the refresh inside
        # _initialize_from_db so there's a single update point.
        from app.services.readiness import ReadinessReport
        self.last_readiness_report: Optional[ReadinessReport] = None

    def _decide_use_real(self, cat_mode: str) -> bool:
        """Decide whether to load a real or mock driver for one
        instrument, given that instrument's per-instrument
        ``InstrumentCategory.driver_mode`` value.

        Precedence (top-to-bottom):
        1. ``self.mode == MOCK_FORCE`` — always mock, no exceptions.
           Overrides per-instrument ``'real'`` (Codex P1 on PR #30:
           ``scripts/driver_selftest --mode mock`` must never poke
           configured hardware).
        2. per-instrument ``'mock'`` — always mock.
        3. per-instrument ``'real'`` — always real.
        4. per-instrument ``'auto'`` / unset — follow global
           (``DriverMode.REAL`` → real, ``DriverMode.MOCK`` → mock).

        Pure function (only reads ``self.mode``) so tests can
        construct an instance and exercise the table directly without
        a DB or driver factory.
        """
        if self.mode == DriverMode.MOCK_FORCE:
            return False
        if cat_mode == "mock":
            return False
        if cat_mode == "real":
            return True
        return self.mode == DriverMode.REAL

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

        # Real driver registry shared with the catalog API — single source
        # of truth (P2-3). See ``_real_driver_registry`` at module level.
        REAL_DRIVER_REGISTRY = _real_driver_registry()

        # 类目 → mock 驱动类：用模块级那份唯一的表（原先这里另有一份局部副本，
        # 靠注释"keep in sync"维持一致，已于 2026-08-10 合并）
        MOCK_FALLBACK = _MOCK_FALLBACK_BY_CATEGORY

        from app.services.readiness import (
            DriverReadinessRow,
            ReadinessReport,
            build_calibration_readiness,
            build_dut_attach_readiness,
            build_lab_profile_readiness,
            build_subnet_reachability,
        )

        db = SessionLocal()
        # Per-category readiness rows for the startup report (P3-5: now
        # typed dataclass instead of dict — same five core fields plus an
        # ``extras`` slot that the connect-success branch populates from
        # ``driver.readiness_metadata()`` so e.g. F64 firmware/band fields
        # land in the report without per-driver branches here).
        report_rows: List[DriverReadinessRow] = []
        # P1-15: preflight trust verdict from the canary negative-control.
        # Computed lazily on the first real preflight (so a pure-mock init never
        # pays the probe cost) and cached for the rest of this init. None = not
        # yet checked; True = canary dead → preflight trustworthy; False = canary
        # alive → network is lying, skip preflight network-wide.
        preflight_trustworthy: Optional[bool] = None
        try:
            categories = db.query(InstrumentCategoryModel).filter(
                InstrumentCategoryModel.is_active == True
            ).order_by(InstrumentCategoryModel.display_order).all()

            for cat in categories:
                if not cat.selected_model_id:
                    logger.info(f"[HAL-REAL] {cat.category_key}: no model selected, skipping")
                    report_rows.append(DriverReadinessRow(
                        category=cat.category_key,
                        model="(not configured)",
                        endpoint="",
                        status="skipped",
                        detail="no model selected in GUI",
                    ))
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

                # Determine driver class based on per-instrument mode + global fallback
                DriverClass = None
                cat_mode = getattr(cat, 'driver_mode', None) or "auto"

                use_real = self._decide_use_real(cat_mode)
                if self.mode == DriverMode.MOCK_FORCE:
                    mode_source = (
                        f"global MOCK_FORCE (overrides per-instrument {cat_mode!r})"
                        if cat_mode == "real"
                        else f"global MOCK_FORCE (per-instrument {cat_mode!r})"
                    )
                elif cat_mode == "mock":
                    mode_source = "per-instrument (forced mock)"
                elif cat_mode == "real":
                    mode_source = "per-instrument (forced real)"
                else:
                    mode_source = f"auto (global={self.mode.value})"

                logger.info(
                    f"[HAL] {cat.category_key}: mode={cat_mode}, "
                    f"use_real={use_real} ({mode_source})"
                )

                if use_real:
                    category_drivers = REAL_DRIVER_REGISTRY.get(cat.category_key, {})
                    DriverClass = category_drivers.get(model.model)

                if DriverClass:
                    logger.info(
                        f"[HAL] {cat.category_key}: using REAL driver "
                        f"{DriverClass.__name__} for {model.vendor} {model.model}"
                    )
                elif use_real and cat_mode == "real":
                    # 强制 real 模式但没有对应的真实驱动实现 → 不降级，跳过并报错
                    logger.error(
                        f"[HAL] {cat.category_key}: forced real mode, but no real driver "
                        f"for {model.vendor} {model.model} — skipping (will NOT fallback to mock)"
                    )
                    if conn:
                        conn.status = "error"
                        conn.last_error = f"Forced real mode but no driver for {model.model}"
                        db.commit()
                    continue
                else:
                    DriverClass = MOCK_FALLBACK.get(cat.category_key)
                    if DriverClass:
                        if use_real:
                            logger.warning(
                                f"[HAL] {cat.category_key}: auto → fallback to Mock "
                                f"(real driver not available for {model.model})"
                            )
                        else:
                            logger.info(
                                f"[HAL] {cat.category_key}: using Mock driver "
                                f"{DriverClass.__name__}"
                            )
                    else:
                        logger.info(
                            f"[HAL] {cat.category_key}: no driver available, skipping"
                        )
                        continue

                # Instantiate and connect
                driver = DriverClass(
                    instrument_id=f"{cat.category_key}_{str(cat.id)[:8]}",
                    config=driver_config,
                )
                endpoint_str = (
                    f"{conn.controller_ip}:{conn.port}" if conn and conn.controller_ip
                    else (conn.endpoint if conn and conn.endpoint else "")
                )

                # Pre-flight TCP reachability — skip driver.connect()
                # entirely when the host is unreachable. Avoids 10s × N
                # serial VISA timeouts when a subnet is wrong or an
                # instrument is offline. We only preflight real drivers
                # (mocks don't open sockets). Connection refused doesn't fail
                # preflight — host is up, driver may connect on a different port.
                # P1-13: derive (host, port) from controller_ip/port OR the VISA
                # endpoint string — so bindings that only carry the resource
                # string still get network-probed (was the false-"reachable" bug).
                # ``host_reachable`` is threaded into every row below so the
                # subnet rollup can tell probed-alive from never-probed.
                host_reachable: Optional[bool] = None
                target = (
                    None
                    if is_mock_driver(driver)
                    else preflight_target(driver_config)
                )
                if target is not None:
                    # P1-15: run the canary negative-control once (lazily) before
                    # trusting ANY preflight verdict. If the network is lying
                    # (proxy/VPN answering for unroutable canaries), connect-or-
                    # refused no longer means "host alive", so skip preflight
                    # network-wide and leave host_reachable=None → the subnet
                    # rollup reports 未探测(不可信) instead of a false 可达.
                    if preflight_trustworthy is None:
                        preflight_trustworthy = await detect_preflight_trustworthy()
                        if not preflight_trustworthy:
                            logger.warning(
                                "[HAL] preflight canary alive — 网络层有透明代理/VPN/"
                                "网关在替不可路由地址应答 TCP；子网可达性不可信，本次跳过 "
                                "preflight（所有子网标为未探测）。请在无代理/直连网络下重跑。"
                            )
                    if preflight_trustworthy:
                        alive, reason = await tcp_preflight(
                            target[0], target[1], timeout_s=1.0
                        )
                        host_reachable = alive
                        if not alive:
                            logger.warning(
                                f"[HAL] {cat.category_key}: preflight failed "
                                f"({reason}); skipping driver.connect() — set the "
                                f"correct IP/port and reload HAL."
                            )
                            if conn:
                                conn.status = "error"
                                conn.last_error = f"preflight: {reason}"
                                db.commit()
                            report_rows.append(DriverReadinessRow(
                                category=cat.category_key,
                                model=f"{model.vendor} {model.model}",
                                endpoint=endpoint_str,
                                status="fail",
                                detail=f"preflight: {reason}",
                                # P1-11: TCP preflight couldn't reach the host —
                                # the network layer can't route here (most often
                                # the control PC isn't on this /24 subnet).
                                fail_kind="network",
                                network_reachable=False,
                            ))
                            continue
                    # else: network untrusted → host_reachable stays None, fall
                    # through to driver.connect() (still surfaces ok/scpi).

                try:
                    success = await driver.connect()
                    if success:
                        self.drivers[cat.category_key] = driver
                        # 真假按**这台驱动自己**的标记，不按全局模式（P1-48）：
                        # 全局 real 时某台可能回落 Mock，全局 mock 时某台可能被
                        # 强制 real 连真硬件 —— 用全局模式打前缀会把这两种情况都说反。
                        # 实测 2026-08-07 的 app.log 里有 21 条
                        # `[HAL-MOCK] channelEmulator: connected → Keysight PROPSIM F64`，
                        # 而那台当时连的是真机。
                        _msg, _extra = connected_log_fields(
                            driver, cat.category_key, model.vendor, model.model
                        )
                        logger.info(_msg, extra=_extra)
                        # P3-5: pull driver-specific extras (F64 surfaces
                        # parsed SYST:INFO? fields here; other drivers
                        # return ``{}`` from the base default).
                        try:
                            extras = driver.readiness_metadata()
                        except Exception as e:
                            # Don't let a buggy driver subclass torpedo
                            # the whole readiness report.
                            logger.warning(
                                f"[HAL] {cat.category_key}: readiness_metadata() raised "
                                f"{type(e).__name__}: {e} — treating as no extras"
                            )
                            extras = {}

                        # Update connection status in DB.  Driver-detected
                        # Test App is runtime observation only and stays on
                        # the live driver/readiness metadata; persisting it
                        # into shared connection_params can overwrite a model
                        # switch that completed while connect() was in flight.
                        if conn:
                            conn.status = "connected"
                            conn.last_error = None
                            # Use module-level ``datetime`` (line 14). A function-local
                            # ``from datetime import datetime`` would shadow it and
                            # UnboundLocalError later when every driver fails.
                            conn.last_connected_at = datetime.utcnow()
                            db.commit()

                        # P2-1: auto-apply the binding's operator-selected
                        # topology profile (if any) after successful
                        # connect. Compat check is inside
                        # apply_topology_profile — incompatible profile
                        # logs a WARNING but doesn't fail the HAL init
                        # (operator can fix via PUT
                        # /instruments/{cat}/topology-profile without
                        # re-running HAL reload).
                        topology_id = None
                        if conn and isinstance(conn.connection_params, dict):
                            topology_id = conn.connection_params.get("topology_profile_id")
                        # P1-17: binding 没显式选 profile → fallback 到 driver 的
                        # 系统默认 (_default_topology_profile_id, 对齐 F64 默认 .smu),
                        # 消除 fresh-start "快速路" (空配置 / 手动 PUT)。operator 在
                        # connection_params 显式设 topology_profile_id 仍优先。对称
                        # F64 set_channel_model 的默认 .smu fallback。
                        # ── 路径 A/B 边界 (P2-11 Phase 5; 注释经 Codex on PR #112 修正):
                        # 这是**路径 A (bring-up) 的 HAL-init 默认** —— 经
                        # apply_topology_profile → set_cell_config(profile.to_config_dict())
                        # 把 profile 的 mimo_port_preset / tdd_pattern / sched_algo /
                        # csi_rs_ports 等落到 UXM 硬件。正式测试 (路径 B) 的 measure 只
                        # set_cell_config(frequency/ARFCN/BW/SCS/band/mimo_layers/power),
                        # **不覆盖上面那些 profile 字段** → 它们会**残留**进 path B (port
                        # routing / TDD / scheduler 仍是本默认, 非"天然分开")。频率 /
                        # ARFCN / MIMO layers 已 TestCase 驱动; port routing 等是已知 leak
                        # 点 (roadmap "Discovered" backlog: 待补成 TestCase 驱动或显式 reset)。
                        # 见 docs/architecture/testcase-driven-instrument-config.md §2/§6/§6.1。
                        if not topology_id:
                            topology_id = getattr(driver, "_default_topology_profile_id", None)
                            if topology_id:
                                logger.info(
                                    f"[HAL] {cat.category_key}: binding 未选 topology "
                                    f"profile, fallback 到系统默认 {topology_id!r} (P1-17)"
                                )
                        # P0-2 D5: 默认配置没落上就不许报 ok — 此前 applied=False
                        # 只打 WARNING 就绪照绿, 现场"重启后 UXM 变了配置"其实是
                        # 这里下发失败/被 binding 旧选择压住, 但面板全绿没人知道。
                        # warn 不挡路 (默认配置属 bring-up 捷径, 路径 B 有 measure
                        # precheck 门兜底), 但操作员必须看得见 (用户 2026-07-26
                        # 采纳 warn 方案)。
                        topo_apply_issue: Optional[str] = None
                        if topology_id and hasattr(driver, "apply_topology_profile"):
                            # P2-1 Phase 2.1: driver consumes the dataclass;
                            # lookup happens here so HAL stays DB-free.
                            # Prefer DB-persisted row (operators may have
                            # edited a built-in or created a custom one);
                            # fall back to in-code registry if the bootstrap
                            # seeder hasn't run yet (greenfield first-boot
                            # race window).
                            from app.services.topology_profile_service import (
                                TopologyProfileNotFound, get_dataclass,
                            )
                            try:
                                profile_dc = get_dataclass(db, topology_id)
                            except TopologyProfileNotFound:
                                from app.hal.uxm_test_profiles import (
                                    _PROFILE_REGISTRY, _register_builtin_profiles,
                                )
                                if not _PROFILE_REGISTRY:
                                    _register_builtin_profiles()
                                profile_dc = _PROFILE_REGISTRY.get(topology_id)
                                if profile_dc is None:
                                    logger.warning(
                                        f"[HAL] {cat.category_key}: "
                                        f"topology profile {topology_id!r} not in DB or "
                                        f"in-code registry — operator's selection is stale; "
                                        f"clearing won't happen automatically, fix via PUT "
                                        f"/instruments/{cat.category_key}/topology-profile."
                                    )
                                    topo_apply_issue = (
                                        f"topology 选择已失效 ({topology_id!r} 不存在)"
                                    )
                            if profile_dc is not None:
                                try:
                                    result = await driver.apply_topology_profile(profile_dc)
                                    if not result.get("applied"):
                                        logger.warning(
                                            f"[HAL] {cat.category_key}: "
                                            f"topology profile {topology_id!r} NOT applied — "
                                            f"reason={result.get('reason')}"
                                        )
                                        topo_apply_issue = (
                                            f"默认配置 {topology_id!r} 未应用: "
                                            f"{result.get('reason')}"
                                        )
                                except Exception as e:
                                    logger.warning(
                                        f"[HAL] {cat.category_key}: "
                                        f"apply_topology_profile({topology_id!r}) raised "
                                        f"{type(e).__name__}: {e} — driver loaded but "
                                        f"binding's topology not applied"
                                    )
                                    topo_apply_issue = (
                                        f"默认配置 {topology_id!r} 下发抛 "
                                        f"{type(e).__name__}: {e}"
                                    )

                        report_rows.append(DriverReadinessRow(
                            category=cat.category_key,
                            model=f"{model.vendor} {model.model}",
                            endpoint=endpoint_str,
                            status="warn" if topo_apply_issue else "ok",
                            detail=(
                                f"{DriverClass.__name__} — ⚠ {topo_apply_issue}; "
                                f"仪表当前配置未知, 正式测试前必须走一次下发"
                                if topo_apply_issue else f"{DriverClass.__name__}"
                            ),
                            extras=extras,
                            network_reachable=host_reachable,
                        ))
                    else:
                        # driver.connect() returned False — pull the real
                        # error from the driver itself rather than writing
                        # a generic "Connection failed during HAL init".
                        # See docs/site-debug/2026-05-13-retrospective.md
                        # category F (error message ergonomics).
                        real_err = getattr(driver, "_last_error", None) or "connect() returned False"
                        logger.error(
                            f"[HAL-REAL] {cat.category_key}: connection failed — {real_err}"
                        )
                        if conn:
                            conn.status = "error"
                            conn.last_error = real_err
                            db.commit()
                        report_rows.append(DriverReadinessRow(
                            category=cat.category_key,
                            model=f"{model.vendor} {model.model}",
                            endpoint=endpoint_str,
                            status="fail",
                            detail=real_err,
                            # P1-11: preflight passed (or was skipped — no
                            # parseable host) but the driver's session/*IDN?
                            # handshake failed — instrument problem, not a
                            # routing problem. network_reachable carries the
                            # actual probe outcome (True / None) for the rollup.
                            fail_kind="scpi",
                            network_reachable=host_reachable,
                        ))
                except Exception as e:
                    err_str = f"{type(e).__name__}: {e}"
                    logger.error(
                        f"[HAL-REAL] {cat.category_key}: exception during connect: {err_str}"
                    )
                    if conn:
                        conn.status = "error"
                        conn.last_error = err_str
                        db.commit()
                    report_rows.append(DriverReadinessRow(
                        category=cat.category_key,
                        model=f"{model.vendor} {model.model}",
                        endpoint=endpoint_str,
                        status="fail",
                        detail=err_str,
                        # P1-11: exception raised *during* driver.connect() —
                        # preflight passed (or was skipped — no parseable host),
                        # so this is a session/SCPI-layer failure, not network
                        # routing. network_reachable carries the probe outcome.
                        fail_kind="scpi",
                        network_reachable=host_reachable,
                    ))

            logger.info(
                f"[HAL-REAL] Driver factory complete: "
                f"{len(self.drivers)} drivers initialized"
            )

            # P3-5: build the full readiness snapshot (drivers + lab +
            # cal + dut-attach placeholder), persist on self for
            # GET /instruments/hal/readiness, and log the formatted
            # version. Lab + cal sections are pure SQL reads — no HAL
            # imports — so a buggy driver doesn't affect them.
            lab_section = build_lab_profile_readiness(db)
            cal_section = build_calibration_readiness(db, lab_section)
            dut_section = build_dut_attach_readiness()
            # P1-11: roll up the driver rows by /24 subnet so the operator
            # gets one "this subnet is unreachable, add an IP alias" hint
            # per subnet instead of N opaque per-instrument VISA errors.
            # P1-15: tell the rollup whether the network was trustworthy so the
            # 未探测 hint names the real cause (proxy/VPN) when the canary tripped.
            # preflight_trustworthy is None when no real preflight ran (pure mock)
            # → treat as trustworthy (the benign 未探测 hint is correct there).
            subnet_sections = build_subnet_reachability(
                report_rows, network_trustworthy=(preflight_trustworthy is not False)
            )
            report = ReadinessReport(
                drivers=report_rows,
                lab_profile=lab_section,
                calibration=cal_section,
                dut_attach=dut_section,
                generated_at_iso=datetime.utcnow().isoformat(),
                subnets=subnet_sections,
            )
            self.last_readiness_report = report
            self._log_readiness_report(report)

        finally:
            db.close()

    @staticmethod
    def _log_readiness_report(report: "ReadinessReport") -> None:
        """Print the composite readiness snapshot so operators don't have
        to grep mixed stdout to know whether HAL came up.

        P3-5: now logs three sections — drivers (the original table),
        lab profile + calibration validity, and the DUT-attach
        placeholder. The driver table format is unchanged so on-call
        screenshot diffs vs older captures still line up.

        Format:

            ═══════ HAL READINESS REPORT ═══════
            ✓ vna            E5071C ENA       192.168.0.10:5025    RealKeysightEnaDriver
            ✗ channelEmul.   PROPSIM F64      192.168.0.100:5025   ImportError: pyvisa
              └─ firmware_version=v1.0  band_label=450MHz - 3000MHz
            ○ baseStation    (not configured)
            ────────────────────────────────────
            lab profile : ok       — active LabProfile 'CAICT-Lab-1'
            calibration : expired  — certificate CAL-2025-001 expired 12 day(s) ago
            dut attach  : not_implemented — DUT attach sensing not implemented ...
            ════════════════════════════════════
            2/3 categories loaded · 1 failed · 1 skipped
        """
        rows = report.drivers
        header_label = "═" * 19 + " HAL READINESS REPORT " + "═" * 19
        divider = "─" * len(header_label)
        lines = [header_label]

        if rows:
            # Compute column widths so the table aligns at any terminal width.
            cat_w = max(max(len(r.category) for r in rows), len("category"))
            model_w = max(max(len(r.model) for r in rows), len("model"))
            endpoint_w = max(max(len(r.endpoint) for r in rows), len("endpoint"))

            icons = {"ok": "✓", "fail": "✗", "skipped": "○"}
            for r in rows:
                icon = icons.get(r.status, "?")
                lines.append(
                    f"{icon} {r.category:<{cat_w}}  "
                    f"{r.model:<{model_w}}  "
                    f"{r.endpoint:<{endpoint_w}}  "
                    f"{r.detail}"
                )
                if r.extras:
                    extras_str = "  ".join(
                        f"{k}={v}" for k, v in r.extras.items() if v is not None
                    )
                    if extras_str:
                        lines.append(f"  └─ {extras_str}")
        else:
            lines.append("(no instrument categories configured)")

        # P3-5: lab + cal + dut-attach sections. Aligned with a fixed
        # label width so the three rows form a column block under the
        # driver table.
        lines.append(divider)
        lines.append(
            f"lab profile : {report.lab_profile.status:<15}  "
            f"— {report.lab_profile.detail}"
        )
        lines.append(
            f"calibration : {report.calibration.status:<15}  "
            f"— {report.calibration.detail}"
        )
        lines.append(
            f"dut attach  : {report.dut_attach.status:<15}  "
            f"— {report.dut_attach.detail}"
        )

        lines.append("═" * len(header_label))
        # Driver tallies (unchanged from pre-P3-5).
        if rows:
            # P0-2 D5: "warn" (驱动已加载, 默认配置没落上) 也算 loaded ——
            # 否则头行报 "0/1 loaded" 跟表格自相矛盾; warn 单列不并进 fail。
            ok = sum(1 for r in rows if r.status in ("ok", "warn"))
            warn = sum(1 for r in rows if r.status == "warn")
            fail = sum(1 for r in rows if r.status == "fail")
            skipped = sum(1 for r in rows if r.status == "skipped")
            lines.append(
                f"{ok}/{len(rows)} categories loaded · "
                f"{fail} failed · {skipped} skipped"
                + (f" · {warn} warn(配置未落)" if warn else "")
            )

        for line in lines:
            logger.info("[HAL] %s", line)

    async def shutdown(self):
        """Shutdown all drivers and cleanup.

        P2-5: when drivers are still attached, log at WARNING (not INFO)
        with the driver list — any in-flight diagnostic / SCPI / test
        execution that's mid-``await driver._query()`` will fail when
        we close the underlying VISA session below. The refuse policy
        in ``app/services/hal_reload_policy.py`` warns the operator
        BEFORE we get here, but the warning log helps post-mortem
        triage ("did something else trigger HAL shutdown?").
        """
        if self.drivers:
            logger.warning(
                f"[HAL] Shutting down with {len(self.drivers)} active driver(s): "
                f"{sorted(self.drivers.keys())} — any in-flight operations "
                f"will fail with closed VISA session errors"
            )
        else:
            logger.info("Shutting down InstrumentHALService (no active drivers)")

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

        unsafe_cmw_disconnects: list[str] = []
        for name, driver in list(self.drivers.items()):
            real_cmw = (
                getattr(driver, "adapter_id", None) == "cmw500"
                and not is_mock_driver(driver)
            )
            try:
                disconnected = await driver.disconnect()
                if real_cmw and disconnected is not True:
                    unsafe_cmw_disconnects.append(name)
                    logger.error(
                        "CMW500 driver %s refused unsafe disconnect; retaining driver",
                        name,
                    )
                    continue
                logger.info(f"Disconnected driver: {name}")
            except Exception as e:
                logger.error(f"Error disconnecting {name}: {e}")
                if real_cmw:
                    unsafe_cmw_disconnects.append(name)
                    continue
            self.drivers.pop(name, None)

        if unsafe_cmw_disconnects:
            raise RuntimeError(
                "baseStation CMW500 无法确认安全断开；HAL 保留恢复会话并拒绝卸载"
            )

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

    async def clear_metrics_cache(self) -> None:
        """测试租约切换控制权时清掉跨边界的监控快照。"""
        await self._metrics_cache.clear()

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
            disconnected = await driver.disconnect()
            if disconnected is not True:
                logger.error(
                    "Refusing to reconnect %s because disconnect was unconfirmed",
                    driver_name,
                )
                return False
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

# P2-5: serialise HAL lifecycle operations (initialise / shutdown / mode
# switch / reload) so two concurrent operator clicks on "HAL Reload" or
# the rare init-vs-shutdown interleave can't race the global
# ``_hal_service`` assignment. Pre-P2-5 audit found that two concurrent
# POSTs to /hal/reload would both enter shutdown_hal_service +
# initialize_hal_service, and the global could end up holding a
# half-constructed instance.
#
# This lock is module-level (not per-instance) because the thing we're
# protecting IS the instance assignment itself. Holding it across
# shutdown + init is fine — both are async and the lock yields to other
# coroutines that AREN'T touching HAL lifecycle (metrics queries,
# diagnostic sequences). Those will likely fail because the underlying
# driver was just torn down, but that's the operator-known risk of
# reload mid-test — see ``app/services/hal_reload_policy.py`` for the
# refuse + force protocol that warns them before they get there.
_hal_lifecycle_lock: Optional[asyncio.Lock] = None


def _get_lifecycle_lock() -> asyncio.Lock:
    """Lazy-init the lifecycle lock so it binds to the running event
    loop. Tests that spin up TestClient per case end up with different
    loops; module-level ``asyncio.Lock()`` would lock to the first loop
    and raise ``RuntimeError: ... attached to a different loop`` later.
    """
    global _hal_lifecycle_lock
    if _hal_lifecycle_lock is None:
        _hal_lifecycle_lock = asyncio.Lock()
    return _hal_lifecycle_lock


def get_hal_service() -> InstrumentHALService:
    """Get the global HAL service instance"""
    global _hal_service
    if _hal_service is None:
        _hal_service = InstrumentHALService(mode=DriverMode.MOCK)
    return _hal_service


async def _initialize_hal_service_inner(mode: DriverMode) -> None:
    """Init without acquiring the lifecycle lock — caller must hold it
    OR be the FastAPI lifespan path (single-process startup, no
    concurrency). Split out from the public ``initialize_hal_service``
    so the reload-atomic helper below can do shutdown + init in one
    locked region without acquiring the same non-reentrant lock twice.
    """
    global _hal_service
    _hal_service = InstrumentHALService(mode=mode)
    await _hal_service.initialize()
    logger.info("Global HAL service initialized")


async def _park_after_lifecycle() -> None:
    """初始化/重载完成后把空闲仪表停回 Local —— **必须在生命周期锁之外调**。

    ⚠ 这行原本在 `_initialize_hal_service_inner` 末尾，也就是**持着生命周期锁
    去拿租约锁**。而 `POST /hal/reload`（非 force）与 `POST /hal/switch` 是
    反过来的顺序：先 `hal_mutation_guard()` 拿租约锁，再进
    `reload_hal_service_atomic` 拿生命周期锁。两条路径顺序相反、两把锁都无超时
    —— 经典 ABBA 死锁，撞上就是租约锁被**永久持有**：此后每一次
    `instrument_test_lease` / `park` / `hal_mutation_guard` 都无限等待，
    正式执行、暗室首测、诊断序列、所有 F64/UXM 端点全部挂死，只能重启后端。
    触发路径在现场很平常：被 409 拦住后改点 force，同时另一标签页点重载。
    （2026-08-07 内审 F1，真模块探针复现。）

    修法是**去掉锁嵌套**而不是加超时/换可重入锁：park 本来就不需要在
    生命周期锁内做 —— 它操作的是刚建好的驱动实例，跟"谁在改全局 _hal_service"
    无关。移到锁外后两条路径都只在同一时刻持一把锁，环就断了。
    """
    from app.services.instrument_test_lease import park_idle_instruments

    # HAL connect/readiness 会短暂取得 F64 Remote。初始化完成即关闭 ATE socket，
    # 空闲态由仪表前面板自行控制；正式测试会通过统一租约重新取得 Remote。
    await park_idle_instruments()


async def _shutdown_hal_service_inner() -> None:
    """Shutdown without acquiring the lifecycle lock — see
    ``_initialize_hal_service_inner`` for why."""
    global _hal_service
    if _hal_service:
        await _hal_service.shutdown()
        _hal_service = None
        logger.info("Global HAL service shutdown complete")


async def initialize_hal_service(mode: DriverMode = DriverMode.MOCK):
    """Initialise the global HAL service (serialised via lifecycle lock)."""
    async with _get_lifecycle_lock():
        await _initialize_hal_service_inner(mode)
    # 锁外 —— 见 `_park_after_lifecycle` 的 ABBA 死锁说明
    await _park_after_lifecycle()


async def shutdown_hal_service():
    """Shutdown the global HAL service (serialised via lifecycle lock)."""
    async with _get_lifecycle_lock():
        await _shutdown_hal_service_inner()


async def reload_hal_service_atomic(mode: DriverMode) -> None:
    """P2-5: shutdown + reinitialise in a SINGLE locked region.

    Pre-P2-5 the reload endpoint called ``shutdown_hal_service`` then
    ``initialize_hal_service``, each acquiring and releasing the
    (newly-added) lifecycle lock. The release-then-reacquire window let
    a concurrent reload sneak in and assign to the global mid-flight,
    leaving the second reload's init clobbering the first's. Holding
    the lock across the whole shutdown + init closes that window
    without needing a re-entrant lock.
    """
    async with _get_lifecycle_lock():
        await _shutdown_hal_service_inner()
        await _initialize_hal_service_inner(mode)
    # 锁外 —— 见 `_park_after_lifecycle` 的 ABBA 死锁说明
    await _park_after_lifecycle()


async def switch_hal_mode(new_mode: DriverMode) -> Dict[str, Any]:
    """运行时切换 HAL 驱动模式 (Mock ↔ Real)。

    P2-5: shutdown + reinit run inside the lifecycle lock (via
    ``reload_hal_service_atomic``) so a concurrent reload or another
    switch can't race the global ``_hal_service`` assignment.
    """
    global _hal_service

    old_mode = _hal_service.mode if _hal_service else "none"
    logger.info(f"[HAL] Switching mode: {old_mode} → {new_mode.value}")

    await reload_hal_service_atomic(new_mode)

    # ``_hal_service`` is freshly assigned by the atomic helper — safe to
    # read the new driver list now without the lock (no other lifecycle
    # op is in progress; ordinary metric queries against the new instance
    # are independent of this caller).
    active_drivers = list(_hal_service.drivers.keys()) if _hal_service else []
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
