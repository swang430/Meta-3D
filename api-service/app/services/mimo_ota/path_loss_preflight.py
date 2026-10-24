"""Pure/query-only path-loss gate evaluated before any instrument I/O."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from app.services.execution_evidence_outcome import project_execution_evidence_outcome
from types import SimpleNamespace
from app.services.mimo_ota.path_loss_application import build_frozen_path_loss_application,build_path_loss_application
from app.services.mimo_ota.route_calibration_freeze import read_execution_route_compensation,frozen_legacy_certificate,frozen_selected_legacy_certificate,frozen_route_identity_error


@dataclass(frozen=True)
class PathLossPreflight:
    """One common selection/application verdict for session and MEASURE."""

    selection: Any
    selected_certificate: Any | None
    applied_certificate: Any | None
    application: dict[str, Any]
    blocker: str | None
    route_compensation: dict[str,Any] | None = None


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
    """只读本执行冻结。历史缺失明确未知，不从当前证书/图补填。"""
    channel_emulator_is_real = channel_emulator_execution_mode == "real"
    frozen=read_execution_route_compensation(execution)
    if frozen.get('version')==1 and (frozen['frequency_mhz']!=frequency_mhz or frozen['operating_mode']!=operating_mode):
        raise ValueError('执行频率/模式与路损冻结身份不一致')
    legacy_adapter=frozen_legacy_certificate(frozen)
    selected=legacy_adapter or frozen_selected_legacy_certificate(frozen)
    selection=SimpleNamespace(certificate=selected,reason=frozen.get('legacy_selection_reason','legacy_unclassified'),
        coverage_complete=legacy_adapter is not None)
    outcome = (
        execution_evidence_outcome
        if execution_evidence_outcome is not None
        else project_execution_evidence_outcome(execution)
    )
    reason='incomplete_coverage'
    if frozen.get('version')!=1:
        reason='legacy_unclassified'
    elif any(row['source_kind']=='confirmed_route' for row in frozen['route_entries']):
        reason='pending_compensation_wiring'
    elif frozen['route_entries'] and all(row['source_kind']=='legacy_certificate' for row in frozen['route_entries']) and legacy_adapter is None:
        reason='pending_compensation_wiring'
    usable=False
    blocker=None
    if selected is not None:
        usable, blocker = _evaluate_path_loss_provenance_for_measure(
            selected.use_mock,
            channel_emulator_is_real=channel_emulator_is_real,
            strict=precheck_strict_cal,
            diagnostic=(outcome.qualification_classification == "diagnostic"),
        )
        if outcome.compatibility_classification in {"diagnostic", "invalid"}:
            usable = False
        if not usable:
            reason='diagnostic'
    if legacy_adapter is None:
        usable=False
    if not usable and blocker is None and channel_emulator_is_real and precheck_strict_cal:
        blocker=(f'path-loss calibration is missing or expired (frozen selection: {selection.reason})'
            if selection.reason in ('missing','expired') else f'path-loss frozen source unavailable: {reason}')
    route_error=frozen_route_identity_error(db,frozen)
    if route_error is not None:
        usable=False
        blocker=route_error
        reason='route_identity_mismatch'
    applied = selected if usable else None
    gate_mode = (
        "mock_not_applicable"
        if not channel_emulator_is_real
        else "strict"
        if precheck_strict_cal
        else "operator_bypass"
    )
    application=build_frozen_path_loss_application(frozen,gate_mode=gate_mode,applied=applied is not None,reason=reason)
    # 单份拒绝旧候选/旧缺失原因仍沿v1表达；从冻结读取，不借此给未知链赋值。
    if reason!='route_identity_mismatch' and frozen.get('version')==1 and not any(
        row['source_kind']=='confirmed_route' for row in frozen['route_entries']):
        if selected is not None and selected.use_mock is not False:
            application=build_path_loss_application(selected_certificate=selected,applied_certificate=None,
                selection_reason='selected',gate_mode='strict' if gate_mode=='mock_not_applicable' else gate_mode)
        elif selected is None and selection.reason in ('missing','expired','frequency_mismatch','operating_mode_mismatch'):
            application=build_path_loss_application(selected_certificate=None,applied_certificate=None,
                selection_reason=selection.reason,gate_mode=gate_mode)
    return PathLossPreflight(
        selection=selection,
        selected_certificate=selected,
        applied_certificate=applied,
        application=application,
        blocker=blocker,
        route_compensation=frozen,
    )
