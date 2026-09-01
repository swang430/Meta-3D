"""Resolve and freeze the selected base-station adapter before hardware I/O."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm.attributes import flag_modified

from app.hal.base_station_adapter_profile import (
    BaseStationAdapterProfileResolution,
)
from app.hal.base_station_compatibility import (
    build_compatibility_payload,
    build_measure_execution_requirements_from_configuration,
    canonical_payload_digest,
)
from app.models.lab_profile import LabProfile
from app.models.test_plan import TestCase, TestExecution
from app.services.base_station_binding import resolve_base_station_binding
from app.services.instrument_hal_service import is_mock_driver


FREEZE_CONFIG_KEY = "base_station_adapter_profile_freeze"
CMW_FORMAL_CAPABILITY_KEY = "cmw500_lte_2x2_formal_capability"


def _loaded_base_station(hal):
    drivers = getattr(hal, "drivers", None)
    if not isinstance(drivers, dict):
        return None
    return drivers.get("baseStation")


def _driver_connection_identity(driver) -> dict[str, Any]:
    """Return the parsed transport identity already used by the loaded driver."""

    return {
        "host": getattr(driver, "_connection_host", None),
        "port": getattr(driver, "_connection_port", None),
        "resource": getattr(driver, "_connection_resource", None),
    }


def validate_frozen_base_station_before_remote(hal, frozen: dict[str, Any]) -> str | None:
    """Pure lock-time check; never opens a session or reads the database."""

    driver = _loaded_base_station(hal)
    if driver is None:
        return "loaded driver is missing"

    resolution = frozen.get("resolution")
    if not isinstance(resolution, dict):
        return "frozen adapter resolution is missing"
    mode = resolution.get("execution_mode")
    if mode == "real":
        if is_mock_driver(driver):
            return "loaded driver changed from real to mock"
        expected_module = frozen.get("expected_driver_module")
        expected_name = frozen.get("expected_driver_name")
        if (
            type(driver).__module__ != expected_module
            or type(driver).__name__ != expected_name
        ):
            return "loaded driver does not match frozen registry class"
        if getattr(driver, "adapter_id", None) != resolution.get("adapter"):
            return "loaded driver adapter does not match frozen adapter"
        if _driver_connection_identity(driver) != frozen.get(
            "expected_driver_connection"
        ):
            return "loaded driver connection identity does not match frozen connection"
        return None
    if mode == "simulated":
        if not is_mock_driver(driver):
            return "loaded driver changed from mock to real"
        frozen_adapter = resolution.get("adapter")
        if (
            frozen_adapter is not None
            and getattr(driver, "adapter_id", None) != frozen_adapter
        ):
            return "loaded driver adapter does not match frozen adapter"
        return None
    return "frozen execution mode is invalid"


def _saved_test_case_configuration(db, execution) -> Any:
    """Return the saved TestCase configuration consumed by compatibility.

    只读 ``primary_carrier``（``component_carriers[0]``）的
    ``radio_technology`` 一个字段；缺省按 schema 默认 ``"nr5g"``
    （``ComponentCarrierConfig.radio_technology`` 的默认值 —— 旧记录缺失时
    精确兼容为 nr5g）。刻意不做整份 MIMOOTAConfiguration 校验：无关校验
    失败不得混进兼容性门的失败语义（P1-75 设计稿 §4）。
    """

    test_case_id = getattr(execution, "test_case_id", None)
    configuration: Any = None
    if test_case_id is not None:
        test_case = (
            db.query(TestCase).filter(TestCase.id == test_case_id).one_or_none()
        )
        if test_case is not None:
            configuration = test_case.configuration
    return configuration


def build_frozen_base_station_validator(frozen: dict[str, Any]):
    """Return a pure lock-time validator carrying its immutable freeze identity."""

    def _validate(hal):
        return validate_frozen_base_station_before_remote(hal, frozen)

    _validate.validation_identity = frozen.get("digest")
    return _validate


def freeze_base_station_adapter_profile(
    db,
    hal,
    execution,
    selected_lab_profile,
) -> dict[str, Any]:
    """Resolve once and persist an immutable execution-scoped adapter snapshot."""

    execution_config = execution.config if isinstance(execution.config, dict) else {}
    existing = execution_config.get(FREEZE_CONFIG_KEY)
    if isinstance(existing, dict):
        # Local import avoids a module-load cycle: the outcome projector reads
        # FREEZE_CONFIG_KEY, while this write/reuse boundary owns the freeze.
        from app.services.execution_evidence_outcome import (
            validate_frozen_compatibility_snapshot,
        )

        evidence_error = validate_frozen_compatibility_snapshot(existing)
        if evidence_error:
            raise ValueError(evidence_error)
        error = validate_frozen_base_station_before_remote(hal, existing)
        if error:
            raise ValueError(error)
        return existing
    resolved = resolve_base_station_binding(
        db,
        hal,
        selected_lab_profile,
        lock=True,
    )
    # P1-75 兼容性硬门：TestCase 结构化需求 vs 注册 manifest 声明对账。
    # configured / not_applicable 两态都有 manifest → 必须对账并拒不兼容；
    # diagnostic_unbound 无 adapter 无 manifest → 显式 no_adapter，保持
    # 既有放行（模拟诊断语义，非本片放宽）。
    requirements = build_measure_execution_requirements_from_configuration(
        _saved_test_case_configuration(db, execution)
    )
    compatibility = build_compatibility_payload(requirements, resolved.manifest)
    compatibility_verdict = compatibility["verdict"]
    if compatibility_verdict["compatible"] is not True:
        raise ValueError(
            "TestCase execution requirements are incompatible with the "
            "resolved baseStation adapter: "
            + "; ".join(compatibility_verdict["reasons"])
        )
    adapter = resolved.manifest.adapter_id if resolved.manifest is not None else None
    resolution = BaseStationAdapterProfileResolution.model_validate(
        {
            "schema_version": 1,
            "adapter": adapter,
            "status": resolved.status,
            "execution_mode": resolved.execution_mode,
            "profile": resolved.profile,
        }
    )
    stable = resolved.stable_projection()
    identity = {
        "schema_version": 1,
        "resolution": resolution.model_dump(mode="json"),
        "category_id": resolved.category_id,
        "instrument_model_id": resolved.instrument_model_id,
        "instrument_connection_id": resolved.instrument_connection_id,
        "lab_profile_id": resolved.lab_profile_id,
        "expected_driver_module": resolved.expected_driver_module,
        "expected_driver_name": resolved.expected_driver_name,
        "expected_driver_connection": (
            None
            if resolved.execution_mode == "simulated"
            or resolved.expected_transport is None
            else resolved.expected_transport.model_dump(mode="json")
        ),
        "binding_digest": resolved.binding_digest,
        "resolved_binding": stable,
        # P1-75：verdict + requirements 进 identity 再算 digest ——
        # 篡改 compatibility 也会被既有 digest 抓到。
        "compatibility": compatibility,
    }
    if resolved.formal_capability is not None:
        identity[CMW_FORMAL_CAPABILITY_KEY] = resolved.formal_capability.model_dump(
            mode="json"
        )
    frozen = {**identity, "digest": canonical_payload_digest(identity)}
    from app.services.execution_evidence_outcome import (
        validate_frozen_compatibility_snapshot,
    )

    evidence_error = validate_frozen_compatibility_snapshot(frozen)
    if evidence_error:
        raise ValueError(evidence_error)
    error = validate_frozen_base_station_before_remote(hal, frozen)
    if error:
        raise ValueError(error)

    execution.config = {**execution_config, FREEZE_CONFIG_KEY: frozen}
    flag_modified(execution, "config")
    db.flush()
    return frozen


def freeze_execution_base_station_adapter_profile(
    db,
    hal,
    execution,
    test_case,
    *,
    force_diagnostic: bool = False,
):
    """Lock execution/lab and freeze before the first hardware operation.

    Old rows that already contain hardware progress cannot acquire provenance
    from today's catalog.  A pre-existing frozen snapshot remains readable and
    is only revalidated against the loaded driver.
    """

    locked_execution = (
        db.query(TestExecution)
        .filter(TestExecution.id == execution.id)
        .with_for_update()
        .one_or_none()
    )
    if locked_execution is None:
        raise ValueError("TestExecution no longer exists")
    config = locked_execution.config if isinstance(locked_execution.config, dict) else {}
    if FREEZE_CONFIG_KEY not in config:
        has_progress = any(
            value not in (None, {}, [])
            for value in (
                locked_execution.measurements,
                locked_execution.test_results,
                locked_execution.phase_results,
                config.get("phase_progress"),
            )
        )
        if has_progress:
            raise ValueError(
                "execution already has hardware/phase progress; current adapter "
                "configuration cannot be backfilled"
            )

    lab_profile_id = getattr(test_case, "lab_profile_id", None)
    if lab_profile_id is None:
        raise ValueError("TestCase has no LabProfile for baseStation resolution")
    selected_lab = (
        db.query(LabProfile)
        .filter(LabProfile.id == lab_profile_id)
        .one_or_none()
    )
    if selected_lab is None:
        raise ValueError("selected LabProfile no longer exists")
    frozen = freeze_base_station_adapter_profile(
        db,
        hal,
        locked_execution,
        selected_lab,
    )
    from app.services.execution_qualification import freeze_execution_qualification

    freeze_execution_qualification(
        db,
        locked_execution,
        test_case,
        force_diagnostic=force_diagnostic,
    )
    return frozen
