"""FS16 add-emulation sequence.

This sequence intentionally edits an existing FS16 ``.smu`` template instead of
trying to recreate the GUI Scenario Wizard from scratch. The public SCPI surface
observed for FS16 supports opening an existing emulation, applying selected
runtime/edit parameters, connecting it to hardware, and reading back model/path
state. It does not yet expose a reliable API for Finish/Build/save-as.
"""
from __future__ import annotations

import asyncio
import ntpath
import re
import time
from typing import Any, Callable, Dict, Iterable, List, Optional

from app.diagnostics.protocol import (
    SequenceMetadata,
    SequenceRunResult,
    SequenceStepResult,
    driver_not_loaded_summary,
    mock_driver_refusal_summary,
)
from app.services.diagnostic_context import DiagnosticContext


DEFAULT_SOURCE_SMU = r"D:\User Emulations\Emulation15.wiz\Emulation15.smu"
DEFAULT_MODEL = "3GPP_5GNR_2x2_TDLA30-5_low_correlation.ctap"
DEFAULT_CONNECTOR_MAP = "BS1.1=RF1,BS1.2=RF2,UE1.1=RF3,UE1.2=RF4"


metadata = SequenceMetadata(
    name="FS16 add emulation",
    description=(
        "Open an existing FS16 .smu, edit supported parameters, connect it to "
        "hardware, and read back model/connector state. Does not create or "
        "save a new .smu in v1."
    ),
    required_categories=["channelEmulator"],
    params_schema=[
        {
            "name": "source_smu_file",
            "label": "源 .smu 文件（FS16 内）",
            "type": "string",
            "default": DEFAULT_SOURCE_SMU,
        },
        {
            "name": "verify_source_file_exists",
            "label": "编辑前校验源 .smu 存在",
            "type": "boolean",
            "default": True,
        },
        {
            "name": "emulation_name",
            "label": "Step 1 - Emulation name",
            "type": "string",
            "default": "Emulation16",
        },
        {
            "name": "emulation_description",
            "label": "Step 1 - Description",
            "type": "string",
            "default": "",
        },
        {
            "name": "working_directory",
            "label": "Step 1 - Working directory",
            "type": "string",
            "default": "D:\\User Emulations\\",
        },
        {
            "name": "bandwidth_mhz",
            "label": "Step 1 - Bandwidth (MHz)",
            "type": "number",
            "default": 100,
        },
        {
            "name": "creation_style",
            "label": "Step 1 - Creation style",
            "type": "string",
            "default": "Cellular systems",
            "options": ["Cellular systems", "Mobile Ad-hoc network (MANET/Mesh)"],
        },
        {
            "name": "radio_technology",
            "label": "Step 2 - Radio technology",
            "type": "string",
            "default": "5G TDD",
        },
        {
            "name": "bs_name",
            "label": "Step 2 - BS name",
            "type": "string",
            "default": "5G BS 1",
        },
        {
            "name": "ms_name",
            "label": "Step 2 - MS name",
            "type": "string",
            "default": "5G MS 1",
        },
        {
            "name": "link_bandwidth_mhz",
            "label": "Step 2 - Link bandwidth (MHz)",
            "type": "number",
            "default": 100,
        },
        {
            "name": "bs_tx_antennas",
            "label": "Step 2 - BS TX antennas",
            "type": "number",
            "default": 2,
        },
        {
            "name": "bs_rx_antennas",
            "label": "Step 2 - BS RX antennas",
            "type": "number",
            "default": 2,
        },
        {
            "name": "ms_tx_antennas",
            "label": "Step 2 - MS TX antennas",
            "type": "number",
            "default": 2,
        },
        {
            "name": "ms_rx_antennas",
            "label": "Step 2 - MS RX antennas",
            "type": "number",
            "default": 2,
        },
        {
            "name": "connector_selection",
            "label": "Step 2 - Connector selection",
            "type": "string",
            "default": "Automatic",
            "options": ["Automatic", "Manual"],
        },
        {
            "name": "downlink_channel_model",
            "label": "Step 2 - Downlink .ctap model",
            "type": "string",
            "default": DEFAULT_MODEL,
        },
        {
            "name": "uplink_channel_model",
            "label": "Step 2 - Uplink .ctap model",
            "type": "string",
            "default": DEFAULT_MODEL,
        },
        {
            "name": "distribution_seed",
            "label": "Step 2 - Distribution seed",
            "type": "string",
            "default": "Unique",
            "options": ["Unique", "Common", "User defined"],
        },
        {
            "name": "insertion_delay_optimization",
            "label": "Step 2 - Insertion delay optimization",
            "type": "string",
            "default": "Standard",
        },
        {
            "name": "shadowing",
            "label": "Step 2 - Shadowing",
            "type": "string",
            "default": "off",
            "options": ["off", "on"],
        },
        {
            "name": "band",
            "label": "Step 3 - Band",
            "type": "string",
            "default": "n34",
        },
        {
            "name": "channel_number",
            "label": "Step 3 - Channel",
            "type": "number",
            "default": 402000,
        },
        {
            "name": "center_frequency_mhz",
            "label": "Step 3 - Center frequency (MHz)",
            "type": "number",
            "default": 2010.0,
        },
        {
            "name": "crest_factor_db",
            "label": "Step 3 - Crest factor (dB)",
            "type": "number",
            "default": 12.0,
        },
        {
            "name": "dl_max_tx_power_dbm",
            "label": "Step 3 - DL max TX power (dBm)",
            "type": "number",
            "default": 20.0,
        },
        {
            "name": "ul_max_tx_power_dbm",
            "label": "Step 3 - UL max TX power (dBm)",
            "type": "number",
            "default": 23.0,
        },
        {
            "name": "in_loss_db",
            "label": "Step 3 - In loss (dB)",
            "type": "number",
            "default": 0.0,
        },
        {
            "name": "dl_path_loss_db",
            "label": "Step 3 - DL path loss (dB)",
            "type": "number",
            "default": 52.0,
        },
        {
            "name": "ul_path_loss_db",
            "label": "Step 3 - UL path loss (dB)",
            "type": "number",
            "default": 55.0,
        },
        {
            "name": "out_loss_db",
            "label": "Step 3 - Out loss (dB)",
            "type": "number",
            "default": 0.0,
        },
        {
            "name": "out_level_dbm",
            "label": "Step 3 - Out level (dBm)",
            "type": "number",
            "default": -32.0,
        },
        {
            "name": "channel_numbers",
            "label": "Step 3/4 - FS16 channel numbers",
            "type": "string",
            "default": "1,2,3,4",
        },
        {
            "name": "input_numbers",
            "label": "Step 3 - Input channels",
            "type": "string",
            "default": "1,2",
        },
        {
            "name": "output_numbers",
            "label": "Step 3 - Output channels",
            "type": "string",
            "default": "1,2",
        },
        {
            "name": "apply_center_frequency",
            "label": "Step 3 - Apply center frequency",
            "type": "boolean",
            "default": True,
        },
        {
            "name": "apply_input_levels",
            "label": "Step 3 - Apply input levels",
            "type": "boolean",
            "default": True,
        },
        {
            "name": "apply_output_levels",
            "label": "Step 3 - Apply output levels",
            "type": "boolean",
            "default": True,
        },
        {
            "name": "connector_map",
            "label": "Step 4 - Expected connector map",
            "type": "string",
            "default": DEFAULT_CONNECTOR_MAP,
        },
        {
            "name": "connect_after_edit",
            "label": "Step 5 - CALC:FILT:CONN",
            "type": "boolean",
            "default": True,
        },
        {
            "name": "start_after_connect",
            "label": "Step 5 - Start after connect",
            "type": "boolean",
            "default": False,
        },
        {
            "name": "cleanup_on_finish",
            "label": "Step 5 - Stop if started",
            "type": "boolean",
            "default": False,
        },
    ],
    safe_during_test=False,
)


async def _maybe_await(value: Any) -> Any:
    if hasattr(value, "__await__"):
        return await value
    return value


def _compact_detail(value: Any) -> str:
    if value is None or value is True:
        return "ok"
    text = str(value)
    return text if len(text) <= 240 else text[:237] + "..."


def _driver_last_error(driver: Any) -> str:
    try:
        err = getattr(driver, "last_error", None)
        if callable(err):
            err = err()
    except Exception:  # noqa: BLE001
        err = None
    if err:
        return str(err)
    try:
        err = getattr(driver, "_last_error", None)
    except Exception:  # noqa: BLE001
        err = None
    return str(err) if err else ""


async def _step(
    steps: List[SequenceStepResult],
    wizard_steps: List[Dict[str, Any]],
    log: Callable[[str], None],
    label: str,
    action: Any,
    *,
    wizard_step: Optional[int] = None,
    require_truthy: bool = True,
    false_detail: Callable[[], str] | None = None,
    extra: Optional[Dict[str, Any]] = None,
) -> Any:
    started = time.monotonic()
    try:
        value = action() if callable(action) else action
        result = await _maybe_await(value)
        if require_truthy and result is False:
            detail = false_detail() if false_detail else ""
            suffix = f": {detail}" if detail else ""
            raise RuntimeError(f"driver returned False{suffix}")
        detail = _compact_detail(result)
        duration_ms = int((time.monotonic() - started) * 1000)
        steps.append(
            SequenceStepResult(
                label=label,
                success=True,
                detail=detail,
                duration_ms=duration_ms,
            )
        )
        if wizard_step is not None:
            wizard_steps.append(
                {
                    "step": wizard_step,
                    "label": label,
                    "success": True,
                    "detail": detail,
                    "duration_ms": duration_ms,
                    **(extra or {}),
                }
            )
        log(f"  ✓ {label}")
        return result
    except Exception as exc:  # noqa: BLE001
        detail = f"{type(exc).__name__}: {exc}"
        duration_ms = int((time.monotonic() - started) * 1000)
        steps.append(
            SequenceStepResult(
                label=label,
                success=False,
                detail=detail,
                duration_ms=duration_ms,
            )
        )
        if wizard_step is not None:
            wizard_steps.append(
                {
                    "step": wizard_step,
                    "label": label,
                    "success": False,
                    "detail": detail,
                    "duration_ms": duration_ms,
                    **(extra or {}),
                }
            )
        log(f"  ✗ {label}: {detail}")
        raise


def _bool_param(params: Dict[str, Any], key: str, default: bool) -> bool:
    value = params.get(key, default)
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}
    return bool(value)


def _float_param(params: Dict[str, Any], key: str, default: float) -> float:
    try:
        return float(params.get(key, default))
    except (TypeError, ValueError):
        return default


def _int_param(params: Dict[str, Any], key: str, default: int) -> int:
    try:
        return int(float(params.get(key, default)))
    except (TypeError, ValueError):
        return default


def _str_param(params: Dict[str, Any], key: str, default: str) -> str:
    value = params.get(key, default)
    return str(value if value is not None else default)


def _csv_ints(value: Any, default: Iterable[int]) -> List[int]:
    text = str(value or "")
    found: List[int] = []
    for part in re.split(r"[,;\s]+", text):
        if not part:
            continue
        try:
            found.append(int(float(part)))
        except ValueError:
            continue
    return found or list(default)


def _normalize_token(value: Any) -> str:
    return re.sub(r"[^A-Z0-9]+", "", str(value).upper())


def _basename(value: str) -> str:
    return ntpath.basename(value.strip().strip('"').strip("'"))


def _matches_model(expected: str, actual: str) -> bool:
    if not expected:
        return True
    expected_name = _basename(expected).lower()
    actual_name = _basename(actual).lower()
    return expected_name == actual_name or expected_name in actual.lower()


def _parse_connector_map(value: str) -> Dict[str, str]:
    mapping: Dict[str, str] = {}
    for item in re.split(r"[,;\n]+", value or ""):
        if not item.strip():
            continue
        if "=" in item:
            left, right = item.split("=", 1)
        elif ":" in item:
            left, right = item.split(":", 1)
        else:
            continue
        mapping[left.strip()] = right.strip()
    return mapping


def _wizard_config(params: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "source_smu_file": _str_param(params, "source_smu_file", DEFAULT_SOURCE_SMU),
        "step1": {
            "emulation_name": _str_param(params, "emulation_name", "Emulation16"),
            "description": _str_param(params, "emulation_description", ""),
            "working_directory": _str_param(
                params, "working_directory", "D:\\User Emulations\\"
            ),
            "bandwidth_mhz": _float_param(params, "bandwidth_mhz", 100.0),
            "creation_style": _str_param(params, "creation_style", "Cellular systems"),
        },
        "step2": {
            "radio_technology": _str_param(params, "radio_technology", "5G TDD"),
            "bs_name": _str_param(params, "bs_name", "5G BS 1"),
            "ms_name": _str_param(params, "ms_name", "5G MS 1"),
            "link_bandwidth_mhz": _float_param(params, "link_bandwidth_mhz", 100.0),
            "bs_tx_antennas": _int_param(params, "bs_tx_antennas", 2),
            "bs_rx_antennas": _int_param(params, "bs_rx_antennas", 2),
            "ms_tx_antennas": _int_param(params, "ms_tx_antennas", 2),
            "ms_rx_antennas": _int_param(params, "ms_rx_antennas", 2),
            "connector_selection": _str_param(params, "connector_selection", "Automatic"),
            "downlink_channel_model": _str_param(
                params, "downlink_channel_model", DEFAULT_MODEL
            ),
            "uplink_channel_model": _str_param(
                params, "uplink_channel_model", DEFAULT_MODEL
            ),
            "distribution_seed": _str_param(params, "distribution_seed", "Unique"),
            "insertion_delay_optimization": _str_param(
                params, "insertion_delay_optimization", "Standard"
            ),
            "shadowing": _str_param(params, "shadowing", "off"),
        },
        "step3": {
            "band": _str_param(params, "band", "n34"),
            "channel_number": _int_param(params, "channel_number", 402000),
            "center_frequency_mhz": _float_param(params, "center_frequency_mhz", 2010.0),
            "crest_factor_db": _float_param(params, "crest_factor_db", 12.0),
            "dl_max_tx_power_dbm": _float_param(params, "dl_max_tx_power_dbm", 20.0),
            "ul_max_tx_power_dbm": _float_param(params, "ul_max_tx_power_dbm", 23.0),
            "in_loss_db": _float_param(params, "in_loss_db", 0.0),
            "dl_path_loss_db": _float_param(params, "dl_path_loss_db", 52.0),
            "ul_path_loss_db": _float_param(params, "ul_path_loss_db", 55.0),
            "out_loss_db": _float_param(params, "out_loss_db", 0.0),
            "out_level_dbm": _float_param(params, "out_level_dbm", -32.0),
            "channel_numbers": _csv_ints(params.get("channel_numbers"), [1, 2, 3, 4]),
            "input_numbers": _csv_ints(params.get("input_numbers"), [1, 2]),
            "output_numbers": _csv_ints(params.get("output_numbers"), [1, 2]),
        },
        "step4": {
            "connector_map": _str_param(params, "connector_map", DEFAULT_CONNECTOR_MAP),
        },
        "step5": {
            "connect_after_edit": _bool_param(params, "connect_after_edit", True),
            "start_after_connect": _bool_param(params, "start_after_connect", False),
            "cleanup_on_finish": _bool_param(params, "cleanup_on_finish", False),
        },
    }


def _unsupported_fields() -> List[str]:
    return [
        "v1 does not create a Scenario Wizard from scratch",
        "v1 does not import new .ctap channel model files",
        "v1 does not guarantee saving or Save As back to a .smu file",
        "Step 1 basic info is recorded for traceability/readback comparison only",
        "Step 2 topology/model fields are read back from the existing template",
        "Step 3 band/channel/path-loss fields are recorded unless public SCPI exists",
    ]


async def _call_required(driver: Any, method_name: str, *args: Any) -> Any:
    method = getattr(driver, method_name, None)
    if not callable(method):
        raise RuntimeError(f"FS16 driver lacks required method {method_name}")
    return await _maybe_await(method(*args))


async def _call_optional(driver: Any, method_name: str, *args: Any) -> Any:
    method = getattr(driver, method_name, None)
    if not callable(method):
        return None
    return await _maybe_await(method(*args))


async def run(
    ctx: DiagnosticContext,
    hal: Any,
    params: Dict[str, Any],
    *,
    log: Callable[[str], None],
) -> SequenceRunResult:
    del ctx
    drivers = getattr(hal, "drivers", {}) or {}
    ce = drivers.get("channelEmulator")
    if ce is None:
        return SequenceRunResult(
            success=False,
            summary=driver_not_loaded_summary("channelEmulator"),
        )

    refusal = mock_driver_refusal_summary("channelEmulator", ce)
    if refusal:
        return SequenceRunResult(success=False, summary=refusal)

    params = params or {}
    source_smu = _str_param(params, "source_smu_file", DEFAULT_SOURCE_SMU).strip()
    if not source_smu:
        return SequenceRunResult(
            success=False,
            summary=(
                "source_smu_file is required, for example "
                "D:\\User Emulations\\Emulation15.wiz\\Emulation15.smu"
            ),
        )

    config = _wizard_config(params)
    step3 = config["step3"]
    step5 = config["step5"]
    verify_source = _bool_param(params, "verify_source_file_exists", True)
    source_already_opened = _bool_param(params, "source_already_opened", False)
    apply_center_frequency = _bool_param(params, "apply_center_frequency", True)
    apply_input_levels = _bool_param(params, "apply_input_levels", True)
    apply_output_levels = _bool_param(params, "apply_output_levels", True)

    steps: List[SequenceStepResult] = []
    wizard_steps: List[Dict[str, Any]] = []
    readback: Dict[str, Any] = {}
    applied_scpi: List[str] = []
    started = False

    try:
        if hasattr(ce, "connect"):
            await _step(
                steps,
                wizard_steps,
                log,
                "preflight connect channelEmulator",
                ce.connect(),
                false_detail=lambda: _driver_last_error(ce),
            )

        if not source_already_opened and verify_source:
            exists = await _step(
                steps,
                wizard_steps,
                log,
                f"verify source .smu exists: {source_smu}",
                _call_required(ce, "remote_emulation_file_exists", source_smu),
                require_truthy=False,
            )
            if exists is False:
                raise RuntimeError(f"source .smu not found on FS16: {source_smu}")

        if source_already_opened:
            await _step(
                steps,
                wizard_steps,
                log,
                "source .smu already opened by UI",
                source_smu,
                require_truthy=False,
            )
        else:
            applied_scpi.append(f"CALC:FILT:EDIT {source_smu}")
            await _step(
                steps,
                wizard_steps,
                log,
                "open source .smu for edit",
                _call_required(ce, "open_emulation_for_edit", source_smu),
                false_detail=lambda: _driver_last_error(ce),
            )

        await _step(
            steps,
            wizard_steps,
            log,
            "Step 1/5 record basic information",
            config["step1"],
            wizard_step=1,
            require_truthy=False,
            extra={"parameters": config["step1"]},
        )

        model_sources: Dict[str, str] = {}
        expected_dl = config["step2"]["downlink_channel_model"]
        expected_ul = config["step2"]["uplink_channel_model"]

        async def _readback_template_models() -> Any:
            for channel in step3["channel_numbers"][:2]:
                value = await _call_optional(ce, "query_channel_model_source", channel)
                if value is not None:
                    model_sources[str(channel)] = str(value)
            readback["channel_model_sources"] = model_sources
            if model_sources:
                actual_values = list(model_sources.values())
                dl_ok = any(_matches_model(expected_dl, item) for item in actual_values)
                ul_ok = any(_matches_model(expected_ul, item) for item in actual_values)
                if not (dl_ok and ul_ok):
                    raise RuntimeError(
                        "channel model readback mismatch: "
                        f"expected DL={expected_dl}, UL={expected_ul}, actual={model_sources}"
                    )
            return model_sources or "readback method unavailable"

        await _step(
            steps,
            wizard_steps,
            log,
            "Step 2/5 read back template topology/channel model",
            _readback_template_models(),
            wizard_step=2,
            require_truthy=False,
            extra={"parameters": config["step2"], "readback": model_sources},
        )

        if apply_center_frequency:
            for channel in step3["channel_numbers"]:
                applied_scpi.append(
                    "CALC:FILT:CENT:CH "
                    f"{channel},{step3['center_frequency_mhz']:.3f}"
                )
                await _step(
                    steps,
                    wizard_steps,
                    log,
                    f"apply center frequency CH{channel}",
                    _call_required(
                        ce,
                        "set_center_frequency",
                        channel,
                        step3["center_frequency_mhz"],
                    ),
                    false_detail=lambda: _driver_last_error(ce),
                )

        if apply_input_levels:
            for channel in step3["input_numbers"]:
                applied_scpi.extend(
                    [
                        f"INP:EN {channel},1",
                        f"INP:LEV:AMP:CH {channel},{step3['dl_max_tx_power_dbm']:.3f}",
                        f"INP:CRE:SET {channel},{step3['crest_factor_db']:.3f}",
                    ]
                )
                await _step(
                    steps,
                    wizard_steps,
                    log,
                    f"enable input CH{channel}",
                    _call_required(ce, "set_input_enabled", channel, True),
                    false_detail=lambda: _driver_last_error(ce),
                )
                await _step(
                    steps,
                    wizard_steps,
                    log,
                    f"apply input level CH{channel}",
                    _call_required(
                        ce,
                        "set_input_level",
                        channel,
                        step3["dl_max_tx_power_dbm"],
                    ),
                    false_detail=lambda: _driver_last_error(ce),
                )
                await _step(
                    steps,
                    wizard_steps,
                    log,
                    f"apply crest factor CH{channel}",
                    _call_required(
                        ce,
                        "set_input_crest_factor",
                        channel,
                        step3["crest_factor_db"],
                    ),
                    false_detail=lambda: _driver_last_error(ce),
                )

        if apply_output_levels:
            for channel in step3["output_numbers"]:
                applied_scpi.extend(
                    [
                        f"OUTP:EN {channel},1",
                        f"OUTP:LEV:AMP:CH {channel},{step3['out_level_dbm']:.3f}",
                    ]
                )
                await _step(
                    steps,
                    wizard_steps,
                    log,
                    f"enable output CH{channel}",
                    _call_required(ce, "set_output_enabled", channel, True),
                    false_detail=lambda: _driver_last_error(ce),
                )
                await _step(
                    steps,
                    wizard_steps,
                    log,
                    f"apply output level CH{channel}",
                    _call_required(
                        ce,
                        "set_output_level",
                        channel,
                        step3["out_level_dbm"],
                    ),
                    false_detail=lambda: _driver_last_error(ce),
                )

        freq_readback: Dict[str, str] = {}
        for channel in step3["channel_numbers"]:
            value = await _call_optional(ce, "query_center_frequency", channel)
            if value is not None:
                freq_readback[str(channel)] = str(value)
        readback["center_frequency"] = freq_readback
        await _step(
            steps,
            wizard_steps,
            log,
            "Step 3/5 apply public RF/environment parameters",
            {
                "center_frequency": freq_readback,
                "applied_center_frequency": apply_center_frequency,
                "applied_input_levels": apply_input_levels,
                "applied_output_levels": apply_output_levels,
            },
            wizard_step=3,
            require_truthy=False,
            extra={"parameters": config["step3"], "readback": freq_readback},
        )

        connector_readback: Dict[str, str] = {}
        expected_connectors = _parse_connector_map(config["step4"]["connector_map"])

        async def _readback_connectors() -> Any:
            for channel in step3["channel_numbers"]:
                value = await _call_optional(ce, "query_channel_connector", channel)
                if value is not None:
                    connector_readback[str(channel)] = str(value)
            readback["connector_map"] = connector_readback
            if connector_readback and expected_connectors:
                actual_blob = _normalize_token(" ".join(connector_readback.values()))
                missing = [
                    f"{name}={rf}"
                    for name, rf in expected_connectors.items()
                    if _normalize_token(rf) not in actual_blob
                ]
                if missing:
                    raise RuntimeError(
                        "connector readback mismatch: "
                        f"missing {missing}, actual={connector_readback}"
                    )
            return connector_readback or "readback method unavailable"

        await _step(
            steps,
            wizard_steps,
            log,
            "Step 4/5 verify active connector map",
            _readback_connectors(),
            wizard_step=4,
            require_truthy=False,
            extra={"parameters": config["step4"], "readback": connector_readback},
        )

        if step5["connect_after_edit"]:
            applied_scpi.append("CALC:FILT:CONN")
            await _step(
                steps,
                wizard_steps,
                log,
                "Step 5/5 connect edited emulation to hardware",
                _call_required(ce, "connect_edited_emulation"),
                wizard_step=5,
                false_detail=lambda: _driver_last_error(ce),
                extra={"parameters": config["step5"]},
            )
        else:
            await _step(
                steps,
                wizard_steps,
                log,
                "Step 5/5 connect skipped by operator",
                "connect_after_edit=false",
                wizard_step=5,
                require_truthy=False,
                extra={"parameters": config["step5"]},
            )

        state = await _call_optional(ce, "query_simulation_state")
        if state is not None:
            readback["simulation_state"] = state
        model_info = await _call_optional(ce, "query_model_info")
        if model_info is not None:
            readback["model_info"] = model_info

        if step5["start_after_connect"]:
            await _step(
                steps,
                wizard_steps,
                log,
                "optional start emulation",
                _call_required(ce, "start_emulation"),
                false_detail=lambda: _driver_last_error(ce),
            )
            started = True

        if started and step5["cleanup_on_finish"]:
            await _step(
                steps,
                wizard_steps,
                log,
                "cleanup stop emulation",
                _call_required(ce, "stop_emulation"),
                false_detail=lambda: _driver_last_error(ce),
            )
            started = False

        return SequenceRunResult(
            success=True,
            summary=(
                "fs16_add_emulation passed: opened existing .smu, applied supported "
                "edits, verified readback, and "
                + ("connected to hardware" if step5["connect_after_edit"] else "left unconnected")
            ),
            steps=steps,
            extra={
                "fs16_add_emulation": {
                    "source_smu_file": source_smu,
                    "source_already_opened": source_already_opened,
                    "wizard_config": config,
                    "wizard_steps": wizard_steps,
                    "applied_scpi": applied_scpi,
                    "readback": readback,
                    "unsupported_fields": _unsupported_fields(),
                    "emulation_left_running": started,
                }
            },
        )
    except Exception as exc:  # noqa: BLE001
        return SequenceRunResult(
            success=False,
            summary=f"fs16_add_emulation failed: {type(exc).__name__}: {exc}",
            steps=steps,
            extra={
                "fs16_add_emulation": {
                    "source_smu_file": source_smu,
                    "source_already_opened": source_already_opened,
                    "wizard_config": config,
                    "wizard_steps": wizard_steps,
                    "applied_scpi": applied_scpi,
                    "readback": readback,
                    "unsupported_fields": _unsupported_fields(),
                    "emulation_left_running": started,
                }
            },
        )
    finally:
        if started and step5["cleanup_on_finish"]:
            await _call_optional(ce, "stop_emulation")
        await asyncio.sleep(0)
