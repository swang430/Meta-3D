"""Project cached adapter identity for the active LabProfile instrument set.

This sequence performs no instrument I/O.  It intersects historical
LabProfile bindings with the currently enabled catalog, validates each binding
against server-owned model/endpoint truth, then consumes only identity already
captured by the loaded adapter during connection.
"""
from __future__ import annotations

import logging
from dataclasses import asdict
from typing import Any, Callable, Dict

from app.diagnostics.protocol import SequenceMetadata, SequenceRunResult, SequenceStepResult
from app.services.diagnostic_context import DiagnosticContext
from app.services.instrument_hal_service import get_real_driver_class, is_mock_driver

logger = logging.getLogger(__name__)


metadata = SequenceMetadata(
    name="Instrument identity sweep",
    description=(
        "Projects cached identity from enabled adapters bound to the selected "
        "LabProfile. It performs no instrument query and explicitly reports "
        "inactive historical bindings and configuration drift."
    ),
    required_categories=[],
    params_schema=[],  # parameter-less
    safe_during_test=True,
)


def _adapter_id(driver: Any) -> str | None:
    direct = getattr(driver, "adapter_id", None)
    if isinstance(direct, str) and direct:
        return direct
    manifest = getattr(driver, "adapter_manifest", None)
    candidate = getattr(manifest, "adapter_id", None)
    return candidate if isinstance(candidate, str) and candidate else None


def _cached_identity(category_key: str, driver: Any) -> tuple[dict[str, Any], bool, str]:
    """Return (projection, live_verified, reason) without instrument I/O."""
    adapter_id = _adapter_id(driver)
    if category_key == "baseStation" and adapter_id == "cmw500":
        identity = driver.get_base_station_identity()
        verified = getattr(driver, "identity_snapshot_verified", None) is True
        return (
            {
                **asdict(identity),
                "options": list(identity.options),
                "captured_from_live_connection": verified,
            },
            verified,
            "CMW500 cached connection identity",
        )
    if category_key == "baseStation" and adapter_id == "uxm":
        environment = driver.capture_evidence_environment()
        projection = environment.model_dump(mode="json")
        verified = (
            environment.captured_from_live_connection is True
            and bool(environment.model)
            and bool(environment.firmware_version)
        )
        return (
            projection,
            verified,
            (
                "UXM cached connection environment"
                if verified
                else "UXM cached connection identity is incomplete"
            ),
        )
    if category_key == "channelEmulator" and adapter_id == "propsim_f64":
        environment = driver.capture_evidence_environment()
        projection = environment.model_dump(mode="json")
        # Keep the identity boundary aligned with the required identity fields
        # used by ChannelEmulatorCertificationIdentity without turning this
        # read-only sweep into an options/site-certification gate.
        verified = (
            environment.captured_from_live_connection is True
            and bool(environment.model)
            and bool(environment.firmware_version)
            and bool(environment.serial_number)
        )
        return (
            projection,
            verified,
            (
                "F64 cached connection identity/options"
                if verified
                else "F64 cached connection identity/options are incomplete"
            ),
        )
    return ({}, False, "adapter has no approved cached identity projection")


def _transport(host: Any, port: Any, resource: Any) -> tuple[str, int | None, str | None]:
    """Normalize the already-parsed transport identity without performing I/O."""
    normalized_port = port if isinstance(port, int) else None
    normalized_resource = str(resource).strip().casefold() if resource else None
    return (str(host or "").strip().casefold(), normalized_port, normalized_resource)


def _projection(binding: Any, driver: Any) -> dict[str, Any]:
    category_key = binding.category_key or "(unknown)"
    binding_endpoint = (binding.connection_endpoint or "").strip()
    current_endpoint = (binding.current_connection_endpoint or "").strip()
    loaded_driver = type(driver).__name__ if driver is not None else None
    loaded_adapter_id = _adapter_id(driver) if driver is not None else None
    expected_transport = _transport(
        binding.current_connection_host,
        binding.current_connection_port,
        binding.current_connection_resource,
    )
    loaded_transport = (
        _transport(
            getattr(driver, "_connection_host", None),
            getattr(driver, "_connection_port", None),
            getattr(driver, "_connection_resource", None),
        )
        if driver is not None
        else None
    )
    base = {
        "category_key": category_key,
        "binding_model_id": (
            str(binding.instrument_model_id)
            if binding.instrument_model_id is not None else None
        ),
        "selected_model_id": (
            str(binding.selected_model_id)
            if binding.selected_model_id is not None else None
        ),
        "selected_model": binding.selected_model_name,
        "binding_endpoint": binding_endpoint or None,
        "current_endpoint": current_endpoint or None,
        "loaded_driver": loaded_driver,
        "loaded_adapter_id": loaded_adapter_id,
        "expected_transport": {
            "host": expected_transport[0] or None,
            "port": expected_transport[1],
            "resource": expected_transport[2],
        },
        "loaded_transport": (
            {
                "host": loaded_transport[0] or None,
                "port": loaded_transport[1],
                "resource": loaded_transport[2],
            }
            if loaded_transport is not None
            else None
        ),
        "observed_identity": None,
    }

    if binding.selected_model_id is None or binding.selected_model_name is None:
        return {**base, "status": "mismatch", "reason": "no current model is selected"}
    if binding.instrument_model_id != binding.selected_model_id:
        return {
            **base,
            "status": "mismatch",
            "reason": "LabProfile binding model differs from selected_model_id",
        }
    if not current_endpoint or binding_endpoint != current_endpoint:
        return {
            **base,
            "status": "mismatch",
            "reason": "LabProfile binding endpoint differs from current saved endpoint",
        }
    if driver is None:
        return {**base, "status": "mismatch", "reason": "current enabled driver is not loaded"}
    if is_mock_driver(driver):
        return {
            **base,
            "status": "unknown",
            "reason": "loaded adapter is simulated; no real identity is admissible",
        }

    expected_class = get_real_driver_class(category_key, binding.selected_model_name)
    if expected_class is None:
        return {
            **base,
            "status": "mismatch",
            "reason": "selected model has no registered real adapter",
        }
    if not isinstance(driver, expected_class):
        return {
            **base,
            "status": "mismatch",
            "reason": "loaded driver does not match the selected model adapter",
        }
    if binding.current_connection_error or not expected_transport[0]:
        return {
            **base,
            "status": "mismatch",
            "reason": "current saved transport is invalid or unresolved",
        }
    if getattr(driver, "_connection_config_error", None) or loaded_transport != expected_transport:
        return {
            **base,
            "status": "mismatch",
            "reason": "loaded driver transport differs from current saved transport",
        }

    if category_key in {"positioner", "rfSwitch"}:
        return {
            **base,
            "status": "not_applicable",
            "reason": "no approved non-invasive identity projection exists for this adapter",
        }

    observed, verified, reason = _cached_identity(category_key, driver)
    if not verified:
        return {
            **base,
            "observed_identity": observed or None,
            "status": "unknown",
            "reason": reason,
        }
    return {
        **base,
        "observed_identity": observed,
        "status": "match",
        "reason": reason,
    }


async def run(
    ctx: DiagnosticContext,
    hal: Any,  # InstrumentHALService — typed loosely so tests can pass mocks
    params: Dict[str, Any],
    *,
    log: Callable[[str], None],
) -> SequenceRunResult:
    """Project the active binding/adapter identity set without hardware I/O."""
    if ctx.lab_profile_id is None:
        return SequenceRunResult(
            success=False,
            summary="No LabProfile selected — IDN sweep needs at least one bound instrument",
        )

    if not ctx.instrument_bindings:
        return SequenceRunResult(
            success=False,
            summary=f"LabProfile '{ctx.lab_profile_name}' has no instrument_bindings",
        )

    drivers = getattr(hal, "drivers", {}) or {}
    steps: list[SequenceStepResult] = []
    identities: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []

    for binding in ctx.instrument_bindings:
        category_key = binding.category_key or "(unknown)"
        if binding.category_is_active is not True:
            excluded.append({
                "category_key": category_key,
                "category_id": (
                    str(binding.category_id) if binding.category_id is not None else None
                ),
                "binding_endpoint": binding.connection_endpoint,
                "reason": (
                    "category_inactive"
                    if binding.category_is_active is False
                    else "category_missing"
                ),
            })
            continue
        driver = drivers.get(binding.category_key) if binding.category_key else None
        item = _projection(binding, driver)
        identities.append(item)
        status = item["status"]
        steps.append(SequenceStepResult(
            label=f"{category_key} @ {item['binding_endpoint'] or '(no endpoint)'}",
            success=status in {"match", "not_applicable"},
            detail=f"{status}: {item['reason']}",
            duration_ms=0,
        ))
        marker = "✓" if status in {"match", "not_applicable"} else "✗"
        log(f"  {marker} {category_key}: {status} — {item['reason']}")

    statuses = {item["status"] for item in identities}
    if not identities:
        success = False
        verdict = "UNDETERMINED"
        summary = "LabProfile has no currently active instrument bindings"
    elif "mismatch" in statuses:
        success = False
        verdict = "BLOCKER"
        summary = "Active instrument identity/configuration mismatch detected"
    elif "unknown" in statuses:
        success = False
        verdict = "UNDETERMINED"
        summary = "Active instrument identity is incomplete"
    else:
        success = True
        verdict = "SUCCESS"
        summary = f"All {len(identities)} active instrument bindings are consistent"
    return SequenceRunResult(
        success=success,
        summary=summary,
        steps=steps,
        extra={
            "schema_version": 1,
            "verdict": verdict,
            "identities": identities,
            "excluded": excluded,
            "included_count": len(identities),
            "excluded_count": len(excluded),
        },
    )
