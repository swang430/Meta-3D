"""Read-only Cell-ready power/topology observation for onsite attach debugging.

This module deliberately consumes existing HAL read APIs only.  It does not
derive DUT power or path loss, and it never upgrades unknown values into RF
truth.
"""

from __future__ import annotations

import asyncio
import logging
import math
from collections.abc import Awaitable, Callable
from typing import Any


logger = logging.getLogger(__name__)


def _finite_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _ports(value: Any) -> list[int]:
    if not isinstance(value, (list, tuple)):
        return []
    ports: list[int] = []
    for item in value:
        if isinstance(item, bool):
            return []
        try:
            port = int(item)
        except (TypeError, ValueError):
            return []
        if port < 1 or port in ports:
            return []
        ports.append(port)
    return ports


def _power_rows(raw: Any, ports: list[int]) -> list[dict[str, Any]]:
    source = raw if isinstance(raw, dict) else {}
    return [
        {
            "port": port,
            "value_dbm": _finite_float(
                source.get(port, source.get(str(port)))
            ),
        }
        for port in ports
    ]


async def _collect_sample(
    *,
    base_station: Any,
    channel_emulator: Any,
    phase: str,
    execution_id: str,
) -> dict[str, Any]:
    cmw_power = await base_station.read_configured_downlink_power_dbm()
    instrument_metrics = await channel_emulator.get_metrics()
    metrics = (
        instrument_metrics.metrics
        if isinstance(instrument_metrics.metrics, dict)
        else {}
    )
    input_ports = _ports(metrics.get("active_input_ports"))
    output_ports = _ports(metrics.get("active_output_ports"))
    input_powers = _power_rows(metrics.get("input_powers_dbm"), input_ports)
    output_powers = _power_rows(metrics.get("output_powers_dbm"), output_ports)
    invalid_input_ports = [
        item["port"] for item in input_powers if item["value_dbm"] is None
    ]
    if not input_ports:
        invalid_input_ports = []

    sample = {
        "phase": phase,
        "cmw_configured_rs_epre_dbm": _finite_float(cmw_power),
        "loaded_file": metrics.get("loaded_file"),
        "simulation_state": metrics.get("simulation_state"),
        "topology": {
            "source": metrics.get("topology_source", "unknown"),
            "active_inputs": metrics.get("active_inputs"),
            "active_outputs": metrics.get("active_outputs"),
            "active_channels": metrics.get("active_channels"),
            "active_input_ports": input_ports,
            "active_output_ports": output_ports,
        },
        "input_powers_dbm": input_powers,
        "output_powers_dbm": output_powers,
        "output_powers_frozen": metrics.get("output_powers_frozen"),
        "query_errors": list(metrics.get("query_errors") or []),
        "metrics_status": instrument_metrics.status,
        "invalid_input_ports": invalid_input_ports,
        "input_topology_known": bool(input_ports),
    }
    logger.info(
        "[%s] Cell-ready power observation phase=%s "
        "CMW_RS_EPRE_config_dbm=%s smu=%s topology=%s "
        "F64_input_dbm=%s F64_output_dbm=%s errors=%s",
        execution_id,
        phase,
        sample["cmw_configured_rs_epre_dbm"],
        sample["loaded_file"],
        sample["topology"],
        sample["input_powers_dbm"],
        sample["output_powers_dbm"],
        sample["query_errors"],
    )
    return sample


def _input_failure(sample: dict[str, Any]) -> tuple[list[int], str | None]:
    if sample["input_topology_known"] is not True:
        return [], "F64 活动输入口拓扑未知，无法确认 Cell ON 后输入功率"
    invalid = list(sample["invalid_input_ports"])
    if invalid:
        return invalid, f"F64 活动输入口缺少有效实测功率: {invalid}"
    return [], None


async def run_attach_power_observation(
    *,
    base_station: Any,
    channel_emulator: Any,
    observation_s: float,
    strict_input_level: bool,
    execution_id: str,
    is_cancelled: Callable[[], Awaitable[bool]] | None = None,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> dict[str, Any]:
    """Collect Cell-ready power truth and optionally hold before attach polling.

    ``accepted=True`` 只表示「活动输入口都读到了有限数值、允许继续 attach」，**不判断功率是否存在**：
    真机上「无输入信号」在 F64 的实测读数里是一个很低的有限值（2026-09-16 执行 ``f8f5fd90`` 输入口 2
    两次采样均为 -108.0 dBm），不是空值，所以严格门拦不住缺一路 TX。要判有无信号须换到带该语义的
    查询并有 PROPSIM 手册出处；不凭一次观察值加阈值。状态用 ``recorded`` 而不是「通过」，读数请看 samples。
    """

    samples = [
        await _collect_sample(
            base_station=base_station,
            channel_emulator=channel_emulator,
            phase="cell_ready",
            execution_id=execution_id,
        )
    ]
    invalid_ports, failure = _input_failure(samples[0])
    if strict_input_level and failure is not None:
        logger.error("[%s] %s", execution_id, failure)
        return {
            "schema_version": 1,
            "accepted": False,
            "status": "rejected",
            "wait_seconds_requested": float(observation_s),
            "samples": samples,
            "invalid_input_ports": invalid_ports,
            "failure_reason": failure,
        }

    remaining = max(0.0, float(observation_s))
    while remaining > 0.0:
        if is_cancelled is not None and await is_cancelled():
            reason = "执行在 Cell-ready 功率观察窗口中被取消"
            logger.info("[%s] %s", execution_id, reason)
            return {
                "schema_version": 1,
                "accepted": False,
                "status": "cancelled",
                "wait_seconds_requested": float(observation_s),
                "samples": samples,
                "invalid_input_ports": invalid_ports,
                "failure_reason": reason,
            }
        interval = min(1.0, remaining)
        await sleep(interval)
        remaining -= interval

    if observation_s > 0.0:
        samples.append(
            await _collect_sample(
                base_station=base_station,
                channel_emulator=channel_emulator,
                phase="observation_complete",
                execution_id=execution_id,
            )
        )
        final_invalid, final_failure = _input_failure(samples[-1])
        if final_failure is not None:
            invalid_ports = final_invalid
            failure = final_failure
            if strict_input_level:
                logger.error("[%s] %s", execution_id, failure)
                return {
                    "schema_version": 1,
                    "accepted": False,
                    "status": "rejected",
                    "wait_seconds_requested": float(observation_s),
                    "samples": samples,
                    "invalid_input_ports": invalid_ports,
                    "failure_reason": failure,
                }

    warning = failure is not None or any(
        sample["query_errors"] or sample["metrics_status"] == "error"
        for sample in samples
    )
    return {
        "schema_version": 1,
        "accepted": True,
        "status": "warning" if warning else "recorded",
        "wait_seconds_requested": float(observation_s),
        "samples": samples,
        "invalid_input_ports": invalid_ports,
        "failure_reason": failure,
    }
