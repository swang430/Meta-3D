"""Pure/query-only path-loss gate evaluated before any instrument I/O."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from app.services.execution_evidence_outcome import project_execution_evidence_outcome
from app.services.mimo_ota.path_loss_application import build_path_loss_application
from app.services.path_loss_calibration_service import ProbePathLossCalibrationService


@dataclass(frozen=True)
class PathLossPreflight:
    """One common selection/application verdict for session and MEASURE."""

    selection: Any
    selected_certificate: Any | None
    applied_certificate: Any | None
    application: dict[str, Any]
    blocker: str | None


def _evaluate_path_loss_provenance_for_measure(
    use_mock: Optional[bool],
    *,
    channel_emulator_is_real: bool,
    strict: bool,
    diagnostic: bool = False,
) -> tuple[bool, Optional[str]]:
    """Decide whether one certificate may affect this frozen execution."""

    if diagnostic:
        return False, None
    if not channel_emulator_is_real or use_mock is False:
        return True, None
    provenance = "simulated" if use_mock is True else "unknown"
    blocker = None
    if strict:
        blocker = (
            f"path-loss calibration has {provenance} provenance "
            f"(use_mock={use_mock!r}); real measurement requires explicit "
            "use_mock=False"
        )
    return False, blocker


def evaluate_path_loss_preflight(
    db: Any,
    execution: Any,
    *,
    chamber_id: Any,
    frequency_mhz: float,
    operating_mode: str,
    precheck_strict_cal: bool,
    channel_emulator_execution_mode: str,
    execution_evidence_outcome: Any | None = None,
) -> PathLossPreflight:
    """Resolve the existing calibration gate without touching any HAL driver."""

    channel_emulator_is_real = channel_emulator_execution_mode == "real"
    service = ProbePathLossCalibrationService(db, use_mock=False)
    selection = service.resolve_latest_calibration(
        chamber_id,
        frequency_mhz,
        operating_mode=operating_mode,
        require_real=channel_emulator_is_real,
    )
    if selection.certificate is None and channel_emulator_is_real:
        selection = service.resolve_latest_calibration(
            chamber_id,
            frequency_mhz,
            operating_mode=operating_mode,
        )
    selected = selection.certificate
    outcome = (
        execution_evidence_outcome
        if execution_evidence_outcome is not None
        else project_execution_evidence_outcome(execution)
    )
    if selected is None:
        usable = False
        blocker = (
            "path-loss calibration is missing or expired; real measurement "
            "strict mode requires a currently valid explicit-real certificate"
            if channel_emulator_is_real and precheck_strict_cal
            else None
        )
    else:
        usable, blocker = _evaluate_path_loss_provenance_for_measure(
            selected.use_mock,
            channel_emulator_is_real=channel_emulator_is_real,
            strict=precheck_strict_cal,
            diagnostic=(outcome.qualification_classification == "diagnostic"),
        )
        if outcome.compatibility_classification in {"diagnostic", "invalid"}:
            usable = False
    applied = selected if usable else None
    gate_mode = (
        "mock_not_applicable"
        if not channel_emulator_is_real
        else "strict"
        if precheck_strict_cal
        else "operator_bypass"
    )
    return PathLossPreflight(
        selection=selection,
        selected_certificate=selected,
        applied_certificate=applied,
        application=build_path_loss_application(
            selected_certificate=selected,
            applied_certificate=applied,
            selection_reason=selection.reason,
            gate_mode=gate_mode,
        ),
        blocker=blocker,
    )
