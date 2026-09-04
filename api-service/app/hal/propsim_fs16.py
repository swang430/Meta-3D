"""
Keysight PROPSIM FS16 (model F8820A) Channel Emulator HAL Driver
================================================================

Sibling of ``propsim_f64.py`` but for the FS16 chassis, which despite
sharing the "PROPSIM" brand has a very different SCPI dialect and a
much narrower instruction set:

* **No GCM-native pipeline**: FS16 only does file-based playback
  (``D:\\User Playbacks\\``), so it advertises only
  ``EXTERNAL_WAVEFORM`` mode.
* **No ``*OPT?``**: FS16 firmware answers with
  ``-100,"ATE command not supported"`` — option enumeration must come
  from config, not SCPI probing.
* **No ``FAD:*`` namespace, no ``CH:MOD:STATe?``, no
  ``CALC:FILT:FILE?``**, no ``SYST:EXT:LIST?`` — all the F64
  configuration commands are absent.
* **Channel-indexed queries fail until a simulation is OPEN**:
  ``INP:LEV:AMP:CH? 1`` returns ``-200,"Channel input not found"`` in
  the idle/CLOSED state, then becomes valid after ``DIAG:SIMU:OPEN``.

What FS16 *does* support (empirically verified on the site unit
``Keysight Technologies,F8820A,MY62500170,10.2``):

============================  ==================================
SCPI                          Note
============================  ==================================
``*IDN?``                     standard
``*OPC?``  ``*STB?``  ``*ESR?``  ``*TST?``  ``*CLS``    IEEE 488.2
``SYST:INFO?``                ``PROPSIM FS16,4,RF,v2.0,4,Band: 3MHz - 6000MHz,Main license,Bandwidth:100.000MHz``
``SYST:VERS?``                returns ``1999.0``
``SYST:ERR?``                 SCPI error queue
``DIAG:SIMU:STATe?``          ``CLOSED`` / ``OPEN`` / ``RUNNING``
``SYST:CALibration:USER:GET?``    returns ``0`` when no alignment
``SYST:CALibration:USER:INFO?``   alignment info (empty when ``GET?`` = 0)
``MMEM:CDIR?``                current dir on F8820A (``d:\\User Playbacks``)
``MMEM:CAT?``                 directory listing
============================  ==================================

This first-cut driver therefore implements only what we can do safely
without a loaded simulation:

* connect / disconnect via raw TCP SOCKET on port 5025
* identity verification (``F8820`` in IDN, ``PROPSIM FS16`` in
  ``SYST:INFO?``)
* channel-count extraction from ``SYST:INFO?``
* simulation-state polling via ``DIAG:SIMU:STATe?``
* directory listing via ``MMEM:CAT?``
* metrics + capability reporting

All higher-level ``ChannelEmulatorDriver`` methods (``set_channel_model``,
``upload_asc_files``, ``start_emulation``, ``set_path_loss``, calibration
tone, etc.) fall through to the abstract base's ``NotImplementedError``.
Add them as the FS16 SCPI for each operation is discovered on-site.

Why a separate file from ``propsim_f64.py``
-------------------------------------------
F64 and FS16 share branding but the SCPI dialects are different enough
that a shared base class would be a bunch of ``if self.model == "FS16"``
branches — easier to read as a dedicated module, easier to evolve as
we learn more FS16 SCPI.
"""
from __future__ import annotations

import asyncio
from app.hal.scpi_lock import ReentrantAsyncLock
import logging
from datetime import datetime
from typing import ClassVar, Any, Dict, List, Optional

from app.hal.base import (
    InstrumentCapability,
    InstrumentMetrics,
    InstrumentStatus,
    resolve_configured_instrument_host,
    redact_instrument_command_text,
)
from app.hal.channel_emulator import (
    CalibrationToneCapability,
    ChannelEmulatorDriver,
    ChannelLoadMode,
)
from app.hal.channel_emulator_manifest import (
    ChannelEmulatorLoadModeCapability,
    ChannelEmulatorManifest,
    ChannelEmulatorOperationCapability,
)

logger = logging.getLogger(__name__)


# Default working directory on F8820A firmware 10.2 (matches MMEM:CDIR? output).
# F64 uses "D:\\User Emulations" — different folder semantics.
FS16_PLAYBACK_DIR = r"D:\User Playbacks"

# VISA timeouts (ms)
VISA_TIMEOUT_DEFAULT = 5000
VISA_TIMEOUT_LONG = 30000

# Substring that distinguishes an FS16 / F8820 chassis from other PROPSIM
# family members (in particular F64, which would land in the F64 driver
# instead). We accept either tag for resilience against firmware renames.
_IDN_MODEL_TAGS = ("F8820", "FS16")
_INFO_PRODUCT_TAG = "PROPSIM FS16"


class RealPropsimFs16Driver(ChannelEmulatorDriver):
    """PROPSIM FS16 (Keysight F8820A) channel emulator driver — MVP."""

    #: P2-57：能力 manifest —— 「这个驱动支不支持某操作」的**唯一真值源**。
    #: 它替换掉了散落在服务层/API 的 `hasattr(emulator, ...)` 探测：
    #: 基类补齐 14 个 NotImplementedError 桩之后，`hasattr` 对每个驱动恒为真。
    adapter_manifest: ClassVar[ChannelEmulatorManifest] = ChannelEmulatorManifest(
        schema_version=2,
        adapter_id='propsim_fs16',
        model_name='PROPSIM FS16',
        vendor='Keysight',
        load_modes=(
            ChannelEmulatorLoadModeCapability(
                mode='native_model', support='not_implemented',
                reason='FS16 无 F64 那样的 GCM 引擎',
            ),
            ChannelEmulatorLoadModeCapability(
                mode='external_waveform', support='not_implemented',
                reason='⚠️ P2-57 修正：此前 get_supported_load_modes() 返回 [EXTERNAL_WAVEFORM]，而 upload_asc_files / start_emulation **从未实现** —— 那是假声明，调用会抛不受控的 AttributeError。真实实现前一律不宣称',
            ),
            ChannelEmulatorLoadModeCapability(
                mode='parametric_tdl', support='not_implemented',
                reason='未实现',
            ),
        ),
        operations=(
            ChannelEmulatorOperationCapability(
                operation='get_calibration_tone_capabilities', support='implemented',
                reason='已实现，但返回空列表：本机尚无经验证的内部 CW 源，也没接直通链路',
            ),
            ChannelEmulatorOperationCapability(
                operation='set_mimo_config', support='not_implemented',
                reason='FS16 驱动尚未实现该操作 —— 本驱动只做过只读普查（propsim_fs16_health）',
            ),
            ChannelEmulatorOperationCapability(
                operation='set_path_loss', support='not_implemented',
                reason='FS16 驱动尚未实现该操作 —— 本驱动只做过只读普查（propsim_fs16_health）',
            ),
            ChannelEmulatorOperationCapability(
                operation='set_doppler', support='not_implemented',
                reason='FS16 驱动尚未实现该操作 —— 本驱动只做过只读普查（propsim_fs16_health）',
            ),
            ChannelEmulatorOperationCapability(
                operation='start_emulation', support='not_implemented',
                reason='FS16 驱动尚未实现该操作 —— 本驱动只做过只读普查（propsim_fs16_health）',
            ),
            ChannelEmulatorOperationCapability(
                operation='stop_emulation', support='not_implemented',
                reason='FS16 驱动尚未实现该操作 —— 本驱动只做过只读普查（propsim_fs16_health）',
            ),
            ChannelEmulatorOperationCapability(
                operation='get_channel_state', support='not_implemented',
                reason='FS16 驱动尚未实现该操作 —— 本驱动只做过只读普查（propsim_fs16_health）',
            ),
            ChannelEmulatorOperationCapability(
                operation='upload_asc_files', support='not_implemented',
                reason='FS16 驱动尚未实现该操作 —— 本驱动只做过只读普查（propsim_fs16_health）',
            ),
            ChannelEmulatorOperationCapability(
                operation='set_external_attenuators', support='not_implemented',
                reason='FS16 驱动尚未实现该操作 —— 本驱动只做过只读普查（propsim_fs16_health）',
            ),
            ChannelEmulatorOperationCapability(
                operation='set_baseband_power', support='not_implemented',
                reason='FS16 驱动尚未实现该操作 —— 本驱动只做过只读普查（propsim_fs16_health）',
            ),
            ChannelEmulatorOperationCapability(
                operation='set_calibration_tone', support='not_implemented',
                reason='FS16 驱动尚未实现该操作 —— 本驱动只做过只读普查（propsim_fs16_health）',
            ),
            ChannelEmulatorOperationCapability(
                operation='stop_calibration_tone', support='not_implemented',
                reason='FS16 驱动尚未实现该操作 —— 本驱动只做过只读普查（propsim_fs16_health）',
            ),
            ChannelEmulatorOperationCapability(
                operation='set_passthrough_mode', support='not_implemented',
                reason='FS16 驱动尚未实现该操作 —— 本驱动只做过只读普查（propsim_fs16_health）',
            ),
            ChannelEmulatorOperationCapability(
                operation='clear_passthrough_mode', support='not_implemented',
                reason='FS16 驱动尚未实现该操作 —— 本驱动只做过只读普查（propsim_fs16_health）',
            ),
            ChannelEmulatorOperationCapability(
                operation='ensure_topology', support='not_implemented',
                reason='FS16 驱动尚未实现执行期拓扑恢复 —— 本驱动只做过只读普查（propsim_fs16_health）',
            ),
            ChannelEmulatorOperationCapability(
                operation='get_center_frequency_mhz', support='not_implemented',
                reason='FS16 驱动尚未实现执行期中心频率读取 —— 本驱动只做过只读普查（propsim_fs16_health）',
            ),
            ChannelEmulatorOperationCapability(
                operation='set_output_gain', support='not_implemented',
                reason='FS16 驱动尚未实现逐输出口增益配置 —— 本驱动只做过只读普查（propsim_fs16_health）',
            ),
            ChannelEmulatorOperationCapability(
                operation='set_output_level_dbm', support='not_implemented',
                reason='FS16 驱动尚未实现输出电平配置 —— 本驱动只做过只读普查（propsim_fs16_health）',
            ),
            ChannelEmulatorOperationCapability(
                operation='set_crest_factor', support='not_implemented',
                reason='FS16 驱动尚未实现输入 crest factor 配置 —— 本驱动只做过只读普查（propsim_fs16_health）',
            ),
            ChannelEmulatorOperationCapability(
                operation='measure_input', support='not_implemented',
                reason='FS16 驱动尚未实现输入电平测量 —— 本驱动只做过只读普查（propsim_fs16_health）',
            ),
            ChannelEmulatorOperationCapability(
                operation='autoset_inputs', support='not_implemented',
                reason='FS16 驱动尚未实现输入电平自动设定 —— 本驱动只做过只读普查（propsim_fs16_health）',
            ),
            ChannelEmulatorOperationCapability(
                operation='get_input_level_limits', support='not_implemented',
                reason='FS16 驱动尚未实现输入电平窗口读取 —— 本驱动只做过只读普查（propsim_fs16_health）',
            ),
            ChannelEmulatorOperationCapability(
                operation='set_input_measurement_mode', support='not_implemented',
                reason='FS16 驱动尚未实现输入测量模式配置 —— 本驱动只做过只读普查（propsim_fs16_health）',
            ),
            ChannelEmulatorOperationCapability(
                operation='set_burst_trigger_level', support='not_implemented',
                reason='FS16 驱动尚未实现 burst 触发电平配置 —— 本驱动只做过只读普查（propsim_fs16_health）',
            ),
            ChannelEmulatorOperationCapability(
                operation='get_group_clipping', support='not_implemented',
                reason='FS16 驱动尚未实现通道组 clipping 读取 —— 本驱动只做过只读普查（propsim_fs16_health）',
            ),
            ChannelEmulatorOperationCapability(
                operation='get_system_status', support='not_implemented',
                reason='FS16 驱动尚未实现执行期系统状态读取 —— 本驱动只做过只读普查（propsim_fs16_health）',
            ),
        ),
    )


    # P2-3: FS16 fundamentally lacks K01 internal interference gen (no
    # license SKU for that family) and user-alignment is not in MVP. Empty
    # set is the honest catalog answer: any plan needing ce.* tokens must
    # not bind FS16 as channelEmulator. Explicit frozenset() (rather than
    # relying on the base default) so the absence is grep-able when
    # someone wonders why FS16 fails pre-flight on those tokens.
    model_capabilities = frozenset()

    def __init__(self, instrument_id: str, config: Dict[str, Any]):
        super().__init__(instrument_id, config)
        self._reject_incompatible_visa_resource(allowed_type="SOCKET")
        # Connection params
        self.ip_address: str = self._connection_host
        self.port: int = self._resolved_tcp_port(5025)
        self._connection_visa_resource = self._resolved_visa_resource(
            f"TCPIP0::{self.ip_address}::{self.port}::SOCKET"
        )
        self.playback_dir: str = config.get("playback_dir", FS16_PLAYBACK_DIR)

        # PyVISA handles
        self._rm = None
        self._visa_resource = None
        # P1-21 ①: per-driver SCPI 命令互斥 (同 F64 — async to_thread IO 无锁
        # 并发会应答串线; FS16 同型预防, 排水/INP 语义是 F64 实证特有不扩)。
        self._scpi_lock = ReentrantAsyncLock()  # 可重入 (同 F64, scpi_lock 模块)

        # Identification + capability cache (filled by connect())
        self._product_family: Optional[str] = None
        self._sys_info_raw: Optional[str] = None
        self._channel_count: int = 4
        self._bandwidth_mhz: float = 100.0
        self._band_label: str = ""
        self._license_label: str = ""

    # P2-59②：所有 CE 驱动都显式实现观察/证据协议。FS16 尚无经现场验证的
    # 对应实现，所以返回 None；绝不把 F64 方言推广到这个型号。
    def build_p0_5_command_evidence(self, **kwargs: Any) -> Any | None:
        return None

    def project_channel_operation_evidence(
        self,
        *,
        operation: str,
        requested: Dict[str, Any],
        operation_succeeded: bool | None,
        exchanges: tuple[Any, ...],
        execution_mode: str,
    ) -> Dict[str, Any]:
        """FS16 has no implemented execution operation evidence in this slice."""

        del operation, operation_succeeded, exchanges, execution_mode
        return {
            "fields": [
                {
                    "field": str(name),
                    "requested": value,
                    "applied": None,
                    "applied_present": False,
                    "status": "unavailable",
                    "provenance": "unavailable",
                    "exchange_ids": [],
                    "source_reference": None,
                }
                for name, value in requested.items()
            ],
            "exchange_ids": [],
            "error_queue_exchange_ids": [],
        }

    def get_loaded_emulation_file(self) -> Optional[str]:
        return None

    def get_active_output_count(self) -> Optional[int]:
        return None

    def get_active_input_count(self) -> Optional[int]:
        return None

    def get_active_output_ports(self) -> Optional[List[int]]:
        return None

    def get_active_input_ports(self) -> Optional[List[int]]:
        return None

    # ------------------------------------------------------------------
    # 1. Load-mode capability declaration
    # ------------------------------------------------------------------

    def get_calibration_tone_capabilities(self) -> List[CalibrationToneCapability]:
        """No empirically verified internal CW gen on FS16 yet, no
        passthrough plumbing implemented. Return empty so service layer
        won't try to route path-loss cal through this driver until we
        wire it up.
        """
        return []

    # ------------------------------------------------------------------
    # 2. Connect / disconnect lifecycle
    # ------------------------------------------------------------------

    async def connect(self) -> bool:
        """Open SOCKET, verify identity, cache SYST:INFO parse."""
        if self._connection_config_error or not self.ip_address:
            return self._fail_missing_connection_address()
        self._status = InstrumentStatus.CONNECTING
        try:
            import pyvisa
            self._rm = pyvisa.ResourceManager("@py")
            resource_string = self._connection_visa_resource

            self._visa_resource = await asyncio.to_thread(
                self._rm.open_resource,
                resource_string,
                read_termination="\n",
                write_termination="\n",
                timeout=VISA_TIMEOUT_DEFAULT,
            )

            idn = (await self._query("*IDN?")).strip()
            logger.info(f"[FS16] Connected: {idn}")

            if not any(tag in idn.upper() for tag in (t.upper() for t in _IDN_MODEL_TAGS)):
                # IDN doesn't look like an FS16/F8820. Don't proceed —
                # avoid running FS16-specific SCPI against an unrelated box.
                logger.error(
                    f"[FS16] IDN check failed — got {idn!r}, expected one of "
                    f"{_IDN_MODEL_TAGS}. Aborting connect."
                )
                self._status = InstrumentStatus.ERROR
                self._last_error = f"IDN mismatch: {idn}"
                return False

            sys_info = (await self._query("SYST:INFO?")).strip()
            self._sys_info_raw = sys_info
            logger.info(f"[FS16] System info: {sys_info}")
            self._parse_sys_info(sys_info)

            # *OPT? returns ATE-not-supported on FS16 — explicitly skip the
            # base-class _probe_installed_options() path. Options for FS16
            # come from config or empirical SCPI exploration, not *OPT?.
            self._installed_options = []

            # Read simulation state once for the connect-time snapshot;
            # the diagnostic sequence will re-read it for the live view.
            try:
                state = (await self._query("DIAG:SIMU:STATe?")).strip()
                logger.info(f"[FS16] DIAG:SIMU:STATe? = {state}")
            except Exception as e:  # noqa: BLE001
                logger.debug(f"[FS16] DIAG:SIMU:STATe? query failed: {e}")

            # Drain the error queue so the first user-triggered SCPI sees
            # a clean state.
            await self._clear_error_queue()

            self._status = InstrumentStatus.READY
            self._last_error = None
            return True

        except Exception as e:  # noqa: BLE001
            logger.error(
                f"[FS16] Connection failed ({self.ip_address}:{self.port}): {e}"
            )
            self._status = InstrumentStatus.ERROR
            self._last_error = str(e)
            return False

    async def disconnect(self) -> bool:
        if self._visa_resource:
            try:
                await asyncio.to_thread(self._visa_resource.close)
            except Exception as e:  # noqa: BLE001
                logger.warning(f"[FS16] VISA close error: {e}")
        # ⚠ **不调** `self._rm.close()`: RM 是**进程级共享单例**, 关它会连带关掉其它仪表
        # 的会话 (权威说明见 `app/hal/_visa_reconnect.py` 的「ResourceManager 所有权」一节)。
        # 自己的 resource 上面已经关了, 下面只丢引用。
        self._visa_resource = None
        self._rm = None
        self._status = InstrumentStatus.DISCONNECTED
        return True

    async def configure(self, config: Dict[str, Any]) -> bool:
        """No-op for the MVP — emulation config goes through load_channel()
        once we have FS16-specific SCPI for it.
        """
        return True

    async def reset(self) -> bool:
        """Soft reset — just clear the SCPI error queue. ``*RST`` on FS16
        may have side effects we haven't characterized yet; avoid it
        until we know what it does.
        """
        if not self._visa_resource:
            return False
        try:
            await self._clear_error_queue()
            return True
        except Exception as e:  # noqa: BLE001
            logger.error(f"[FS16] reset failed: {e}")
            return False

    # ------------------------------------------------------------------
    # 3. Capability / metrics reporting
    # ------------------------------------------------------------------

    async def get_capabilities(self) -> List[InstrumentCapability]:
        """Static capability declaration — covers what the MVP driver
        actually implements.
        """
        return [
            InstrumentCapability(
                name="identification",
                description=f"Reports as {self._product_family or 'PROPSIM FS16'}",
                supported=True,
                parameters={
                    "channel_count": self._channel_count,
                    "bandwidth_mhz": self._bandwidth_mhz,
                    "band": self._band_label,
                    "license": self._license_label,
                },
            ),
            InstrumentCapability(
                name="simulation_state_query",
                description="DIAG:SIMU:STATe? readback (CLOSED/OPEN/RUNNING)",
                supported=True,
                parameters={},
            ),
            InstrumentCapability(
                name="playback_directory",
                description=f"MMEM:CDIR? = {self.playback_dir}",
                supported=True,
                parameters={"path": self.playback_dir},
            ),
            InstrumentCapability(
                name="channel_loading",
                description=(
                    "EXTERNAL_WAVEFORM (file playback) only — "
                    "upload_asc_files / start_emulation not yet implemented; "
                    "set_path_loss / set_doppler / set_mimo_config not yet implemented"
                ),
                supported=False,
                parameters={},
            ),
            InstrumentCapability(
                name="calibration_tone",
                description=(
                    "Neither INTERNAL_CW_GENERATOR nor PASSTHROUGH_ONLY "
                    "wired up — path-loss cal cannot route through this CE yet"
                ),
                supported=False,
                parameters={},
            ),
        ]

    async def get_metrics(self) -> InstrumentMetrics:
        """Lightweight runtime snapshot — safe to call on every monitoring poll."""
        metrics: Dict[str, Any] = {
            "product": self._product_family or "PROPSIM FS16",
            "channel_count": self._channel_count,
            "bandwidth_mhz": self._bandwidth_mhz,
        }
        # Optional: read live state if connected. Don't fail get_metrics on
        # transient SCPI errors — monitoring loops poll repeatedly.
        if self._visa_resource:
            try:
                state = (await self._query("DIAG:SIMU:STATe?")).strip()
                metrics["simulation_state"] = state
            except Exception:  # noqa: BLE001
                metrics["simulation_state"] = "unknown"
        return InstrumentMetrics(
            timestamp=datetime.utcnow(),
            metrics=metrics,
        )

    # ------------------------------------------------------------------
    # 4. FS16-specific read-only helpers (used by the diagnostic sequence)
    # ------------------------------------------------------------------

    async def query_simulation_state(self) -> Optional[str]:
        """Return ``DIAG:SIMU:STATe?`` token or None on error."""
        if not self._visa_resource:
            return None
        try:
            return (await self._query("DIAG:SIMU:STATe?")).strip()
        except Exception as e:  # noqa: BLE001
            logger.debug(f"[FS16] query_simulation_state error: {e}")
            return None

    async def list_playback_directory(self) -> Optional[str]:
        """Raw ``MMEM:CAT?`` response — directory listing of the current
        ``MMEM:CDIR?``. Returned as a single CSV string the way F8820A
        sends it.
        """
        if not self._visa_resource:
            return None
        try:
            return (await self._query("MMEM:CAT?")).strip()
        except Exception as e:  # noqa: BLE001
            logger.debug(f"[FS16] list_playback_directory error: {e}")
            return None

    async def query_user_alignment_name(self) -> Optional[str]:
        """Return active user-alignment name, or None if none/error.

        On FS16 ``SYST:CALibration:USER:GET?`` returns ``"0"`` when no
        alignment is active — we translate that to ``None`` so callers
        can treat it as "no alignment".
        """
        if not self._visa_resource:
            return None
        try:
            raw = (await self._query("SYSTem:CALibration:USER:GET?")).strip()
        except Exception as e:  # noqa: BLE001
            logger.debug(f"[FS16] alignment query failed: {e}")
            return None
        cleaned = raw.strip('"').strip("'").strip()
        return cleaned if cleaned and cleaned != "0" else None

    # ------------------------------------------------------------------
    # 5. SCPI primitives
    #
    # Only _do_write / _do_query are defined here — the base class's
    # _write / _query template methods now handle both sync and async
    # _do_* implementations transparently (see base.py for the dispatch
    # logic). Driver code calls ``await self._query(...)`` because our
    # _do_query is async; sync drivers would call ``self._query(...)``
    # directly without await.
    # ------------------------------------------------------------------

    # ── Connection-loss-aware retry (same shape as F64, see #15) ────
    # Shared classifier in ``app.hal._visa_reconnect`` decides which
    # VisaIOError codes mean "socket dropped" vs "timeout / state error".
    # Each driver supplies its own ``_silent_reconnect_visa`` because
    # only the driver knows its resource string + open kwargs.

    @staticmethod
    def _is_visa_conn_lost(exc: BaseException) -> bool:
        from app.hal._visa_reconnect import is_visa_conn_lost
        return is_visa_conn_lost(exc)

    async def _silent_reconnect_visa(self) -> bool:
        """Reopen the FS16 VISA resource after a PyVISA conn-lost shape.

        Closes the half-dead resource (best-effort) and re-opens with
        the same resource string. SCPI state survives the socket
        reconnect, so we skip the heavy ``connect()`` post-open work
        (alignment reload, etc.) — caller's retry just needs a fresh
        session to retransmit on.
        """
        if self._rm is None or not getattr(self, "ip_address", None):
            return False
        try:
            if self._visa_resource is not None:
                await asyncio.to_thread(self._visa_resource.close)
        except Exception:
            pass
        self._visa_resource = None
        try:
            resource_string = self._connection_visa_resource
            self._visa_resource = await asyncio.to_thread(
                self._rm.open_resource,
                resource_string,
                read_termination="\n",
                write_termination="\n",
            )
            logger.info(
                f"[FS16] silent reconnect succeeded — resource reopened "
                f"({resource_string})"
            )
            return True
        except Exception as e:
            logger.error(f"[FS16] silent reconnect failed: {e}")
            self._visa_resource = None
            return False

    async def _do_write(self, cmd: str, timeout: Optional[int] = None) -> None:
        # P1-21 ①: SCPI IO 互斥 — 见 __init__ _scpi_lock 注释
        async with self._scpi_lock:
            await self._do_write_unlocked(cmd, timeout)

    async def _do_write_unlocked(self, cmd: str, timeout: Optional[int] = None) -> None:
        safe_cmd = redact_instrument_command_text(cmd)
        for attempt in (0, 1):
            if not self._visa_resource:
                raise RuntimeError("[FS16] No VISA resource")
            if timeout is not None:
                self._visa_resource.timeout = timeout
            try:
                await asyncio.to_thread(self._visa_resource.write, cmd)
                return
            except Exception as e:
                if attempt == 0 and self._is_visa_conn_lost(e):
                    logger.warning(
                        f"[FS16] VISA connection lost on write '{safe_cmd[:40]}...' "
                        f"(code=0x{getattr(e, 'error_code', 0) & 0xFFFFFFFF:08X}) "
                        f"— silent reconnect"
                    )
                    if await self._silent_reconnect_visa():
                        continue
                raise

    async def _do_query(self, cmd: str, timeout: Optional[int] = None) -> str:
        # P1-21 ①: SCPI IO 互斥 — 见 __init__ _scpi_lock 注释
        async with self._scpi_lock:
            return await self._do_query_unlocked(cmd, timeout)

    async def _do_query_unlocked(self, cmd: str, timeout: Optional[int] = None) -> str:
        safe_cmd = redact_instrument_command_text(cmd)
        for attempt in (0, 1):
            if not self._visa_resource:
                raise RuntimeError("[FS16] No VISA resource")
            if timeout is not None:
                self._visa_resource.timeout = timeout
            try:
                return await asyncio.to_thread(self._visa_resource.query, cmd)
            except Exception as e:
                if attempt == 0 and self._is_visa_conn_lost(e):
                    logger.warning(
                        f"[FS16] VISA connection lost on query '{safe_cmd[:40]}...' "
                        f"(code=0x{getattr(e, 'error_code', 0) & 0xFFFFFFFF:08X}) "
                        f"— silent reconnect"
                    )
                    if await self._silent_reconnect_visa():
                        continue
                raise
        # Unreachable — the loop returns or raises.
        return ""

    async def _clear_error_queue(self) -> None:
        """Drain ``SYST:ERR?`` until it returns the "no error" sentinel.

        Cap the loop at a sane number so a misbehaving firmware that
        always returns a non-zero code doesn't spin forever.
        """
        for _ in range(64):
            try:
                resp = await self._query("SYST:ERR?")
            except Exception:  # noqa: BLE001
                return
            if not resp:
                return
            head = resp.strip().split(",", 1)[0]
            try:
                code = int(head)
            except ValueError:
                return
            if code == 0:
                return

    def _parse_sys_info(self, sys_info: str) -> None:
        """Extract channel count, band, license, bandwidth from FS16's
        ``SYST:INFO?`` response.

        FS16 format (verified on firmware 10.2):
            PROPSIM FS16,4,RF,v2.0,4,Band: 3MHz - 6000MHz,Main license,Bandwidth:100.000MHz

        Each field is comma-separated. Some fields are labelled (``Band:``,
        ``Bandwidth:``) so we read positionally where the format is fixed,
        and by prefix where it's labelled.
        """
        if not sys_info:
            return
        parts = [p.strip() for p in sys_info.split(",")]
        if parts:
            self._product_family = parts[0]
        if len(parts) > 1:
            try:
                self._channel_count = int(parts[1])
            except ValueError:
                pass
        for p in parts:
            if p.lower().startswith("band:"):
                self._band_label = p[len("band:"):].strip()
            elif p.lower().startswith("bandwidth:"):
                bw_str = p[len("bandwidth:"):].strip().lower().removesuffix("mhz").strip()
                try:
                    self._bandwidth_mhz = float(bw_str)
                except ValueError:
                    pass
            elif "license" in p.lower():
                self._license_label = p
