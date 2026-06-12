"""PROPSIM FS16 playback extension driver.

This module deliberately leaves ``propsim_fs16.py`` untouched.  The original
``RealPropsimFs16Driver`` remains the read-only / health-probe MVP; this
subclass adds the HAL primitives needed by ``ChannelLoadMode.EXTERNAL_WAVEFORM``
without changing the old class' contract.

FS16 file handling is different from F64.  The site-verified FS16 surface is
small (identity, state, directory listing), so the playback SCPI is deliberately
configuration-friendly:

* Default path: load a playback file that already exists under
  ``D:\\User Playbacks``.
* Optional path: upload local files with the common SCPI ``MMEM:DATA`` binary
  block, only when ``enable_scpi_file_upload`` is explicitly true.
* Load/start/stop command templates can be overridden in connection_params if
  a specific firmware build uses a different mnemonic.
"""
from __future__ import annotations

import asyncio
import logging
import ntpath
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.hal.base import InstrumentCapability, InstrumentMetrics, InstrumentStatus
from app.hal.channel_emulator import ChannelLoadMode
from app.hal.propsim_fs16 import (
    FS16_PLAYBACK_DIR,
    VISA_TIMEOUT_LONG,
    RealPropsimFs16Driver,
)

logger = logging.getLogger(__name__)


FS16_DEFAULT_LOAD_TEMPLATE = "CALC:FILT:FILE {path}"
FS16_DEFAULT_START_COMMAND = "DIAG:SIMU:GO"
FS16_DEFAULT_STOP_COMMAND = "DIAG:SIMU:GOS"
FS16_DEFAULT_CLOSE_COMMAND = "DIAG:SIMU:CLOSE"

_DEFAULT_ACCEPTED_EXTS = (".smu", ".rtc", ".asc", ".zip")
_ENTRY_PRIORITY = (".smu", ".rtc", ".zip", ".asc")


class RealPropsimFs16PlaybackDriver(RealPropsimFs16Driver):
    """FS16 driver with playback load/start/stop support.

    The class keeps ``model_capabilities`` empty on purpose.  The existing
    capability vocabulary does not have a token for generic playback loading,
    and FS16 still must not claim F64-only tokens such as internal interference
    generator or user alignment.
    """

    model_capabilities = RealPropsimFs16Driver.model_capabilities

    def __init__(self, instrument_id: str, config: Dict[str, Any]):
        super().__init__(instrument_id, config)
        self.playback_dir = config.get("playback_dir", FS16_PLAYBACK_DIR)
        self.enable_scpi_file_upload: bool = bool(
            config.get("enable_scpi_file_upload", False)
        )
        self.auto_start_after_load: bool = bool(
            config.get("auto_start_after_load", False)
        )
        self.verify_remote_file_exists: bool = bool(
            config.get("verify_remote_file_exists", False)
        )
        self.stop_on_disconnect: bool = bool(config.get("stop_on_disconnect", False))
        self.close_on_disconnect: bool = bool(config.get("close_on_disconnect", False))

        accepted = config.get("accepted_playback_extensions") or _DEFAULT_ACCEPTED_EXTS
        if isinstance(accepted, str):
            accepted = [p.strip() for p in accepted.split(",")]
        self.accepted_playback_extensions = tuple(
            ext.lower() if str(ext).startswith(".") else f".{str(ext).lower()}"
            for ext in accepted
            if str(ext).strip()
        )

        self._load_command_template = config.get(
            "load_command_template", FS16_DEFAULT_LOAD_TEMPLATE
        )
        self._start_command = config.get("start_command", FS16_DEFAULT_START_COMMAND)
        self._stop_command = config.get("stop_command", FS16_DEFAULT_STOP_COMMAND)
        self._close_command = config.get("close_command", FS16_DEFAULT_CLOSE_COMMAND)
        self._opc_after_load = bool(config.get("opc_after_load", True))
        self._opc_after_start = bool(config.get("opc_after_start", True))
        self._opc_after_stop = bool(config.get("opc_after_stop", False))
        self._loaded_playback_file: Optional[str] = None

    async def get_capabilities(self) -> List[InstrumentCapability]:
        caps = await super().get_capabilities()
        out: List[InstrumentCapability] = []
        for cap in caps:
            if cap.name == "channel_loading":
                out.append(
                    InstrumentCapability(
                        name="channel_loading",
                        description=(
                            "EXTERNAL_WAVEFORM playback load/start/stop via "
                            "FS16 file playback. Local file upload is opt-in "
                            "with enable_scpi_file_upload."
                        ),
                        supported=True,
                        parameters={
                            "playback_dir": self.playback_dir,
                            "load_command_template": self._load_command_template,
                            "upload_enabled": self.enable_scpi_file_upload,
                        },
                    )
                )
            else:
                out.append(cap)
        return out

    async def get_metrics(self) -> InstrumentMetrics:
        metrics = await super().get_metrics()
        metrics.metrics.update(
            {
                "loaded_playback_file": self._loaded_playback_file,
                "playback_upload_enabled": self.enable_scpi_file_upload,
            }
        )
        return metrics

    def remote_playback_path(self, path_or_name: str) -> str:
        """Return the FS16-side playback path for an operator-supplied name."""
        return self._remote_path(path_or_name)

    async def remote_playback_file_exists(self, path_or_name: str) -> bool:
        """Check whether an operator-staged playback file is visible on FS16."""
        return await self._remote_file_exists(self._remote_path(path_or_name))

    async def disconnect(self) -> bool:
        if self._visa_resource:
            try:
                if self.stop_on_disconnect and self._loaded_playback_file:
                    await self.stop_emulation()
                if self.close_on_disconnect and self._loaded_playback_file:
                    await self.close_playback()
            except Exception as exc:  # noqa: BLE001
                logger.warning("[FS16/PB] cleanup during disconnect failed: %s", exc)
        return await super().disconnect()

    async def load_channel(
        self,
        mode: ChannelLoadMode,
        model_name: str,
        scenario: str,
        parameters: Dict[str, Any],
        waveform_dir: Optional[str] = None,
    ) -> bool:
        if mode != ChannelLoadMode.EXTERNAL_WAVEFORM:
            raise NotImplementedError("FS16 playback driver supports EXTERNAL_WAVEFORM only")
        if not waveform_dir and not self._configured_remote_file(parameters):
            raise ValueError(
                "waveform_dir or remote_playback_file is required for FS16 playback"
            )
        return await self.upload_asc_files(
            waveform_dir or "",
            cdl_model_name=model_name,
            parameters=parameters,
        )

    async def upload_asc_files(
        self,
        asc_files_dir: str,
        cdl_model_name: str = "",
        parameters: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Stage or select a playback payload, then load it on the FS16.

        ``asc_files_dir`` is kept for the HAL interface.  When upload is not
        enabled, the selected local filename is interpreted as a file already
        present under ``self.playback_dir`` on the FS16.
        """
        if not self._visa_resource:
            self._last_error = "[FS16/PB] No VISA resource"
            return False

        params = parameters or {}
        try:
            local_files = self._discover_local_payload_files(asc_files_dir)
        except ValueError as exc:
            self._last_error = str(exc)
            logger.error("[FS16/PB] %s", exc)
            return False

        remote_file = self._configured_remote_file(params)
        if remote_file:
            remote_file = self._remote_path(remote_file)
        elif self.enable_scpi_file_upload:
            remote_file = await self._upload_local_payloads(
                local_files,
                model_name=cdl_model_name,
                entry_filename=params.get("playback_entry_file"),
            )
            if not remote_file:
                return False
        else:
            entry = self._choose_entry_file(
                local_files,
                preferred=params.get("playback_entry_file"),
            )
            if entry is None:
                self._last_error = (
                    "FS16 playback needs either remote_playback_file, "
                    "enable_scpi_file_upload=true, or one unambiguous local "
                    "entry file (.smu/.rtc/.zip or a single .asc)."
                )
                logger.error("[FS16/PB] %s", self._last_error)
                return False
            remote_file = self._remote_path(entry.name)

        if self.verify_remote_file_exists and not await self._remote_file_exists(remote_file):
            self._last_error = f"remote playback file not found on FS16: {remote_file}"
            logger.error("[FS16/PB] %s", self._last_error)
            return False

        return await self._load_remote_playback(remote_file, cdl_model_name)

    async def start_emulation(self) -> bool:
        if not self._visa_resource or not self._loaded_playback_file:
            self._last_error = "Cannot start FS16 playback: no playback file loaded"
            logger.error("[FS16/PB] %s", self._last_error)
            return False
        try:
            await self._clear_error_queue()
            await self._write(self._start_command, timeout=VISA_TIMEOUT_LONG)
            if self._opc_after_start:
                await self._query("*OPC?", timeout=VISA_TIMEOUT_LONG)
            err = await self._first_error()
            if err:
                self._last_error = f"FS16 playback start failed: {err}"
                logger.error("[FS16/PB] %s", self._last_error)
                return False
            self._status = InstrumentStatus.BUSY
            logger.info("[FS16/PB] playback started")
            return True
        except Exception as exc:  # noqa: BLE001
            self._last_error = str(exc)
            logger.error("[FS16/PB] start_emulation failed: %s", exc)
            return False

    async def stop_emulation(self) -> bool:
        if not self._visa_resource:
            return False
        try:
            await self._clear_error_queue()
            await self._write(self._stop_command, timeout=VISA_TIMEOUT_LONG)
            if self._opc_after_stop:
                await self._query("*OPC?", timeout=VISA_TIMEOUT_LONG)
            err = await self._first_error()
            if err:
                self._last_error = f"FS16 playback stop failed: {err}"
                logger.error("[FS16/PB] %s", self._last_error)
                return False
            self._status = InstrumentStatus.READY
            logger.info("[FS16/PB] playback stopped")
            return True
        except Exception as exc:  # noqa: BLE001
            self._last_error = str(exc)
            logger.error("[FS16/PB] stop_emulation failed: %s", exc)
            return False

    async def close_playback(self) -> bool:
        if not self._visa_resource:
            return False
        try:
            await self._write(self._close_command, timeout=VISA_TIMEOUT_LONG)
            self._loaded_playback_file = None
            self._status = InstrumentStatus.READY
            return True
        except Exception as exc:  # noqa: BLE001
            self._last_error = str(exc)
            logger.warning("[FS16/PB] close_playback failed: %s", exc)
            return False

    async def _load_remote_playback(self, remote_file: str, model_name: str) -> bool:
        try:
            logger.info("[FS16/PB] loading playback file: %s", remote_file)
            await self._clear_error_queue()
            cmd = self._render_template(
                self._load_command_template,
                path=remote_file,
                filename=ntpath.basename(remote_file),
                model_name=model_name,
                remote_dir=self.playback_dir,
            )
            await self._write(cmd, timeout=VISA_TIMEOUT_LONG)
            if self._opc_after_load:
                await self._query("*OPC?", timeout=VISA_TIMEOUT_LONG)
            err = await self._first_error()
            if err:
                self._last_error = f"FS16 playback load failed: {err}"
                logger.error("[FS16/PB] %s", self._last_error)
                return False
            self._loaded_playback_file = remote_file
            self._status = InstrumentStatus.READY
            if self.auto_start_after_load:
                return await self.start_emulation()
            return True
        except Exception as exc:  # noqa: BLE001
            self._last_error = str(exc)
            logger.error("[FS16/PB] load failed: %s", exc)
            return False

    async def _upload_local_payloads(
        self,
        files: List[Path],
        *,
        model_name: str,
        entry_filename: Optional[str],
    ) -> Optional[str]:
        if not files:
            self._last_error = "enable_scpi_file_upload=true but local payload list is empty"
            logger.error("[FS16/PB] %s", self._last_error)
            return None
        entry = self._choose_entry_file(files, preferred=entry_filename)
        if entry is None:
            self._last_error = (
                "Cannot choose FS16 playback entry file from local payloads; "
                "set playback_entry_file in parameters/connection_params."
            )
            logger.error("[FS16/PB] %s", self._last_error)
            return None

        label = self._safe_remote_label(model_name or entry.parent.name or "custom")
        remote_dir = self._remote_path(label)
        await self._try_make_remote_dir(remote_dir)
        for file_path in files:
            remote_file = f"{remote_dir}\\{file_path.name}"
            await self._write_mmem_data(remote_file, file_path)
        return f"{remote_dir}\\{entry.name}"

    async def _write_mmem_data(self, remote_file: str, local_file: Path) -> None:
        if not self._visa_resource or not hasattr(self._visa_resource, "write_raw"):
            raise RuntimeError("FS16 SCPI file upload requires VISA write_raw support")
        data = local_file.read_bytes()
        length = str(len(data)).encode("ascii")
        header = (
            f'MMEM:DATA "{remote_file}",#'.encode("ascii")
            + str(len(length)).encode("ascii")
            + length
        )
        self._scpi_logger.debug(
            "TX: MMEM:DATA %s,<%d bytes>",
            remote_file,
            len(data),
            extra={"instrument_id": self.instrument_id, "direction": "TX"},
        )
        await asyncio.to_thread(self._visa_resource.write_raw, header + data)
        await self._query("*OPC?", timeout=VISA_TIMEOUT_LONG)
        err = await self._first_error()
        if err:
            raise RuntimeError(f"MMEM:DATA upload failed for {local_file}: {err}")

    async def _try_make_remote_dir(self, remote_dir: str) -> None:
        try:
            await self._clear_error_queue()
            await self._write(f'MMEM:MDIR "{remote_dir}"', timeout=VISA_TIMEOUT_LONG)
            await self._query("*OPC?", timeout=VISA_TIMEOUT_LONG)
            await self._first_error()
        except Exception as exc:  # noqa: BLE001
            logger.info("[FS16/PB] MMEM:MDIR skipped/failed non-fatally: %s", exc)

    def _discover_local_payload_files(self, asc_files_dir: str) -> List[Path]:
        if not asc_files_dir:
            return []
        root = Path(asc_files_dir)
        if not root.exists():
            raise ValueError(f"ASC/playback source path does not exist: {asc_files_dir}")
        if root.is_file():
            files = [root]
        elif root.is_dir():
            files = [p for p in root.iterdir() if p.is_file()]
        else:
            raise ValueError(f"ASC/playback source path is not a file or directory: {asc_files_dir}")
        return sorted(
            (p for p in files if p.suffix.lower() in self.accepted_playback_extensions),
            key=lambda p: (self._entry_sort_key(p), p.name.lower()),
        )

    def _choose_entry_file(
        self,
        files: List[Path],
        *,
        preferred: Optional[str],
    ) -> Optional[Path]:
        if preferred:
            preferred_name = Path(preferred).name
            for path in files:
                if path.name == preferred_name:
                    return path
            return None
        if not files:
            return None
        for ext in _ENTRY_PRIORITY:
            matches = [p for p in files if p.suffix.lower() == ext]
            if ext == ".asc" and len(matches) > 1:
                return None
            if matches:
                return matches[0]
        return files[0] if len(files) == 1 else None

    def _configured_remote_file(self, parameters: Optional[Dict[str, Any]]) -> Optional[str]:
        params = parameters or {}
        for key in ("remote_playback_file", "playback_file", "fs16_playback_file"):
            value = params.get(key) or self.config.get(key)
            if value:
                return str(value)
        return None

    def _remote_path(self, path_or_name: str) -> str:
        text = str(path_or_name).strip().strip('"').strip("'")
        if re.match(r"^[A-Za-z]:\\", text) or text.startswith("\\\\"):
            return text
        return f"{self.playback_dir}\\{text}"

    async def _remote_file_exists(self, remote_file: str) -> bool:
        target = ntpath.basename(remote_file).lower()
        directory = ntpath.dirname(remote_file)
        listings: List[str] = []
        if directory:
            raw = await self._query_directory_listing(directory)
            if raw:
                listings.append(raw)
        raw_current = await self.list_playback_directory()
        if raw_current:
            listings.append(raw_current)
        return any(target in raw.lower() for raw in listings)

    async def _query_directory_listing(self, directory: str) -> Optional[str]:
        """List an FS16 directory, tolerating firmware-specific MMEM variants."""
        try:
            raw = (await self._query(f'MMEM:CAT? "{directory}"')).strip()
            if raw:
                return raw
        except Exception as exc:  # noqa: BLE001
            logger.debug(
                "[FS16/PB] directory-specific MMEM:CAT? failed for %s: %s",
                directory,
                exc,
            )

        previous_dir: Optional[str] = None
        try:
            previous_dir = self._strip_scpi_string(
                (await self._query("MMEM:CDIR?", timeout=VISA_TIMEOUT_LONG)).strip()
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug("[FS16/PB] MMEM:CDIR? failed before listing: %s", exc)

        try:
            await self._write(f'MMEM:CDIR "{directory}"', timeout=VISA_TIMEOUT_LONG)
            raw = (await self._query("MMEM:CAT?", timeout=VISA_TIMEOUT_LONG)).strip()
            return raw or None
        except Exception as exc:  # noqa: BLE001
            logger.debug("[FS16/PB] CDIR+CAT listing failed for %s: %s", directory, exc)
            return None
        finally:
            if previous_dir and previous_dir != directory:
                try:
                    await self._write(
                        f'MMEM:CDIR "{previous_dir}"',
                        timeout=VISA_TIMEOUT_LONG,
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.debug("[FS16/PB] MMEM:CDIR restore failed: %s", exc)

    async def _first_error(self) -> Optional[str]:
        saw_stale_opc = False
        for _ in range(4):
            try:
                resp = (await self._query("SYST:ERR?", timeout=VISA_TIMEOUT_LONG)).strip()
            except Exception as exc:  # noqa: BLE001
                return f"SYST:ERR? failed: {exc}"
            if not resp:
                return None
            if resp == "1":
                # FS16 can return a delayed *OPC? response here after a slow
                # CALC:FILT:FILE load. Keep reading the actual error queue.
                saw_stale_opc = True
                logger.debug("[FS16/PB] ignored stale *OPC? response while reading SYST:ERR?")
                continue
            head = resp.split(",", 1)[0].strip()
            try:
                code = int(head)
            except ValueError:
                return resp
            return None if code == 0 else resp
        return None if saw_stale_opc else "SYST:ERR? returned no parseable response"

    @staticmethod
    def _entry_sort_key(path: Path) -> int:
        try:
            return _ENTRY_PRIORITY.index(path.suffix.lower())
        except ValueError:
            return len(_ENTRY_PRIORITY)

    @staticmethod
    def _safe_remote_label(label: str) -> str:
        cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", label).strip("._")
        return cleaned or "custom"

    @staticmethod
    def _strip_scpi_string(value: str) -> str:
        return value.strip().strip('"').strip("'")

    @staticmethod
    def _render_template(template: str, **values: Any) -> str:
        return template.format(**values)
