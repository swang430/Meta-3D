"""BS -> CE -> DUT conducted smoke execution service.

This is the minimum useful conducted automation loop for on-site debugging:
put the channel emulator in passthrough, bring up one base-station cell, wait
for a DUT to attach, then sample throughput over independent stat windows.

The module deliberately avoids FastAPI / diagnostic-run dependencies. The
diagnostic sequence adapts this result into SequenceRunResult, while future
formal TestPlan executors can call the same function directly.
"""
from __future__ import annotations

import asyncio
import statistics
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


LogFn = Callable[[str], None]


class ConductedSmokeConfig(BaseModel):
    """Configuration for one conducted BS -> CE -> DUT smoke run."""

    model_config = ConfigDict(extra="ignore")

    frequency_mhz: float = Field(default=3500.0, gt=0)
    bandwidth_mhz: float = Field(default=100.0, gt=0)
    scs_khz: int = Field(default=30, gt=0)
    band: str = Field(default="n78", min_length=1)
    mimo_layers: int = Field(default=2, ge=1, le=8)
    dl_power_dbm: float = Field(default=-50.0, ge=-120.0, le=0.0)

    ce_input_port: str = Field(default="A1", min_length=1)
    ce_output_port: str = Field(default="MAIN", min_length=1)

    attach_timeout_s: float = Field(default=15.0, ge=0.0)
    attach_poll_interval_s: float = Field(default=1.0, gt=0.0)

    throughput_windows: int = Field(default=3, ge=1, le=100)
    throughput_window_s: float = Field(default=0.2, gt=0.0, le=60.0)

    cleanup_on_finish: bool = True

    @model_validator(mode="after")
    def _strip_ports_and_band(self) -> "ConductedSmokeConfig":
        self.band = self.band.strip()
        self.ce_input_port = self.ce_input_port.strip()
        self.ce_output_port = self.ce_output_port.strip()
        if not self.band:
            raise ValueError("band must not be blank")
        if not self.ce_input_port:
            raise ValueError("ce_input_port must not be blank")
        if not self.ce_output_port:
            raise ValueError("ce_output_port must not be blank")
        return self


@dataclass
class ConductedSmokeStep:
    label: str
    success: bool
    detail: str = ""
    duration_ms: Optional[int] = None


@dataclass
class ConductedSmokeResult:
    success: bool
    summary: str
    steps: List[ConductedSmokeStep] = field(default_factory=list)
    extra: Dict[str, Any] = field(default_factory=dict)


async def _maybe_await(value: Any) -> Any:
    if hasattr(value, "__await__"):
        return await value
    return value


def _compact_detail(value: Any) -> str:
    if value is None:
        return "ok"
    if value is True:
        return "ok"
    text = str(value)
    return text if len(text) <= 240 else text[:237] + "..."


async def _step(
    steps: List[ConductedSmokeStep],
    log: LogFn,
    label: str,
    action: Any,
    *,
    require_truthy: bool = True,
    require_not_none: bool = False,
) -> Any:
    started = time.monotonic()
    try:
        value = action() if callable(action) else action
        result = await _maybe_await(value)
        if require_truthy and result is False:
            raise RuntimeError("driver returned False")
        if require_not_none and result is None:
            raise RuntimeError("driver returned None")
        duration_ms = int((time.monotonic() - started) * 1000)
        steps.append(
            ConductedSmokeStep(
                label=label,
                success=True,
                detail=_compact_detail(result),
                duration_ms=duration_ms,
            )
        )
        log(f"  ✓ {label}")
        return result
    except Exception as exc:  # noqa: BLE001
        duration_ms = int((time.monotonic() - started) * 1000)
        detail = f"{type(exc).__name__}: {exc}"
        steps.append(
            ConductedSmokeStep(
                label=label,
                success=False,
                detail=detail,
                duration_ms=duration_ms,
            )
        )
        log(f"  ✗ {label}: {detail}")
        raise


async def _optional_step(
    steps: List[ConductedSmokeStep],
    log: LogFn,
    label: str,
    action: Any,
) -> Any:
    started = time.monotonic()
    try:
        value = action() if callable(action) else action
        result = await _maybe_await(value)
        steps.append(
            ConductedSmokeStep(
                label=label,
                success=True,
                detail=_compact_detail(result),
                duration_ms=int((time.monotonic() - started) * 1000),
            )
        )
        log(f"  ✓ {label}")
        return result
    except Exception as exc:  # noqa: BLE001
        detail = f"{type(exc).__name__}: {exc}"
        steps.append(
            ConductedSmokeStep(
                label=label,
                success=False,
                detail=detail,
                duration_ms=int((time.monotonic() - started) * 1000),
            )
        )
        log(f"  ⚠ {label}: {detail}")
        return None


def _metrics_to_dict(metrics: Any) -> Dict[str, Any]:
    if hasattr(metrics, "to_dict"):
        data = metrics.to_dict()
    elif isinstance(metrics, dict):
        data = dict(metrics)
    else:
        raise TypeError(
            "throughput metric must be a dict-like object or expose to_dict()"
        )
    return data


def _is_attached(info: Any) -> bool:
    if not isinstance(info, dict):
        return False
    if info.get("connected") is True or info.get("rrc_connected") is True:
        return True
    state = str(
        info.get("rrc_state")
        or info.get("cell_state")
        or info.get("state")
        or ""
    ).upper()
    return state in {"CONNECTED", "CONN", "RRC_CONNECTED"}


async def _wait_for_attach(
    bs: Any,
    config: ConductedSmokeConfig,
    steps: List[ConductedSmokeStep],
    log: LogFn,
) -> tuple[bool, Optional[Dict[str, Any]]]:
    started = time.monotonic()
    deadline = started + config.attach_timeout_s
    last_info: Optional[Dict[str, Any]] = None

    while True:
        try:
            info = await _maybe_await(bs.get_ue_info())
            if isinstance(info, dict):
                last_info = info
            if _is_attached(info):
                duration_ms = int((time.monotonic() - started) * 1000)
                steps.append(
                    ConductedSmokeStep(
                        label="DUT attach",
                        success=True,
                        detail=_compact_detail(info),
                        duration_ms=duration_ms,
                    )
                )
                log(f"  ✓ DUT attached: {info}")
                return True, last_info
        except Exception as exc:  # noqa: BLE001
            last_info = {"query_error": f"{type(exc).__name__}: {exc}"}

        if time.monotonic() >= deadline:
            duration_ms = int((time.monotonic() - started) * 1000)
            detail = (
                "No UE attached within timeout"
                if last_info is None
                else f"No UE attached within timeout; last_ue_info={last_info}"
            )
            steps.append(
                ConductedSmokeStep(
                    label=f"DUT attach (timeout {config.attach_timeout_s:.1f}s)",
                    success=False,
                    detail=detail,
                    duration_ms=duration_ms,
                )
            )
            log(f"  ✗ DUT attach: {detail}")
            return False, last_info

        await asyncio.sleep(
            min(config.attach_poll_interval_s, max(0.0, deadline - time.monotonic()))
        )


def _numeric_summary(samples: List[Dict[str, Any]]) -> Dict[str, Dict[str, float]]:
    numeric_fields: Dict[str, List[float]] = {}
    for sample in samples:
        for key, value in sample.items():
            if key == "window_index":
                continue
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                numeric_fields.setdefault(key, []).append(float(value))

    summary: Dict[str, Dict[str, float]] = {}
    for key, values in numeric_fields.items():
        if not values:
            continue
        item = {
            "mean": round(statistics.fmean(values), 4),
            "min": round(min(values), 4),
            "max": round(max(values), 4),
        }
        if len(values) > 1:
            item["std"] = round(statistics.pstdev(values), 4)
        else:
            item["std"] = 0.0
        summary[key] = item
    return summary


def _passed_summary(kpi_summary: Dict[str, Dict[str, float]]) -> str:
    dl = kpi_summary.get("dl_throughput_mbps", {}).get("mean")
    ul = kpi_summary.get("ul_throughput_mbps", {}).get("mean")
    parts = ["Conducted BS-CE-DUT smoke passed"]
    if dl is not None:
        parts.append(f"avg DL {dl:.2f} Mbps")
    if ul is not None:
        parts.append(f"avg UL {ul:.2f} Mbps")
    return "; ".join(parts)


async def _cleanup(
    bs: Any,
    ce: Any,
    *,
    stop_bs: bool,
    clear_ce: bool,
) -> List[str]:
    warnings: List[str] = []
    if stop_bs and hasattr(bs, "stop_signaling"):
        try:
            await _maybe_await(bs.stop_signaling())
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"stop_signaling cleanup raised {type(exc).__name__}: {exc}")
    if clear_ce and hasattr(ce, "clear_passthrough_mode"):
        try:
            await _maybe_await(ce.clear_passthrough_mode())
        except Exception as exc:  # noqa: BLE001
            warnings.append(
                f"clear_passthrough_mode cleanup raised {type(exc).__name__}: {exc}"
            )
    return warnings


async def run_conducted_smoke(
    *,
    base_station: Any,
    channel_emulator: Any,
    config: ConductedSmokeConfig | Dict[str, Any] | None = None,
    log: LogFn | None = None,
) -> ConductedSmokeResult:
    """Run one conducted BS -> CE -> DUT smoke sequence.

    The caller supplies already-loaded HAL drivers. This function never creates
    fallback drivers; an absent real driver should be handled by the caller as a
    fail-loud setup problem.
    """
    cfg = (
        config
        if isinstance(config, ConductedSmokeConfig)
        else ConductedSmokeConfig.model_validate(config or {})
    )
    log_fn: LogFn = log or (lambda _msg: None)
    steps: List[ConductedSmokeStep] = []
    cleanup_warnings: List[str] = []
    ce_passthrough_active = False
    bs_signaling_attempted = False

    extra: Dict[str, Any] = {
        "config": cfg.model_dump(mode="json"),
        "samples": [],
        "kpi_summary": {},
        "ue_info": None,
        "ue_capability": None,
        "cleanup_warnings": cleanup_warnings,
    }

    try:
        await _step(steps, log_fn, "connect channelEmulator", channel_emulator.connect())
        await _step(steps, log_fn, "connect baseStation", base_station.connect())

        await _step(
            steps,
            log_fn,
            f"CE passthrough {cfg.ce_input_port} -> {cfg.ce_output_port}",
            channel_emulator.set_passthrough_mode(
                ce_port=cfg.ce_output_port,
                ce_input_port=cfg.ce_input_port,
            ),
        )
        ce_passthrough_active = True

        cell_config = {
            "frequency_mhz": cfg.frequency_mhz,
            "bandwidth_mhz": cfg.bandwidth_mhz,
            "scs_khz": cfg.scs_khz,
            "band": cfg.band,
            "mimo_layers": cfg.mimo_layers,
            "dl_power_dbm": cfg.dl_power_dbm,
        }
        await _step(
            steps,
            log_fn,
            (
                "BS set_cell_config "
                f"{cfg.frequency_mhz:g}MHz/{cfg.bandwidth_mhz:g}MHz/"
                f"{cfg.scs_khz}kHz/{cfg.band}/{cfg.mimo_layers}L"
            ),
            base_station.set_cell_config(cell_config),
        )

        if hasattr(base_station, "set_downlink_power"):
            await _step(
                steps,
                log_fn,
                f"BS set_downlink_power {cfg.dl_power_dbm:g} dBm",
                base_station.set_downlink_power(cfg.dl_power_dbm),
            )

        bs_signaling_attempted = True
        await _step(
            steps,
            log_fn,
            f"BS start_signaling timeout={cfg.attach_timeout_s:g}s",
            base_station.start_signaling(timeout_s=cfg.attach_timeout_s),
        )

        attached, ue_info = await _wait_for_attach(
            base_station, cfg, steps, log_fn
        )
        extra["ue_info"] = ue_info
        if not attached:
            return ConductedSmokeResult(
                success=False,
                summary="DUT did not attach within timeout",
                steps=steps,
                extra=extra,
            )

        if hasattr(base_station, "query_ue_capability"):
            extra["ue_capability"] = await _optional_step(
                steps,
                log_fn,
                "query_ue_capability",
                base_station.query_ue_capability(),
            )

        samples: List[Dict[str, Any]] = []
        for idx in range(cfg.throughput_windows):
            metrics = await _step(
                steps,
                log_fn,
                f"throughput window {idx + 1}/{cfg.throughput_windows}",
                base_station.measure_throughput_window(cfg.throughput_window_s),
                require_truthy=False,
                require_not_none=True,
            )
            sample = _metrics_to_dict(metrics)
            sample["window_index"] = idx
            samples.append(sample)

        kpi_summary = _numeric_summary(samples)
        extra["samples"] = samples
        extra["kpi_summary"] = kpi_summary

        return ConductedSmokeResult(
            success=True,
            summary=_passed_summary(kpi_summary),
            steps=steps,
            extra=extra,
        )
    except Exception as exc:  # noqa: BLE001
        return ConductedSmokeResult(
            success=False,
            summary=f"Conducted BS-CE-DUT smoke aborted: {type(exc).__name__}: {exc}",
            steps=steps,
            extra=extra,
        )
    finally:
        if cfg.cleanup_on_finish:
            cleanup_warnings.extend(
                await _cleanup(
                    base_station,
                    channel_emulator,
                    stop_bs=bs_signaling_attempted,
                    clear_ce=ce_passthrough_active,
                )
            )
