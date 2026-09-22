"""P2-73: the destructive F64 p08 gate is server-authoritatively UXM-only."""
from __future__ import annotations

from contextlib import asynccontextmanager
from copy import deepcopy
from types import SimpleNamespace

import pytest

from app.api import diagnostic_sequence as api
from app.diagnostics import loader
from app.models.diagnostic_run import DiagnosticRun
from app.models.instrument import InstrumentCategory
from app.services.instrument_test_lease import InstrumentTestLeaseError
from tests.test_f64_p08_gate_sequence import _OK_PARAMS, _make
from tests.test_p2_44_base_station_binding_resolver import _configured, _real_driver, db


def _add_channel_emulator_binding(db, lab) -> None:
    category = InstrumentCategory(
        category_key="channelEmulator",
        category_name="Channel Emulator",
        driver_mode="real",
    )
    db.add(category)
    db.flush()
    bindings = deepcopy(lab.instrument_bindings)
    bindings.append(
        {
            "category_id": str(category.id),
            "instrument_model_id": None,
            "connection_endpoint": "192.0.2.20:3334",
            "driver_mode": "real",
            "role": "channelEmulator",
        }
    )
    lab.instrument_bindings = bindings
    db.commit()


def _install_api_environment(monkeypatch, db, *, selected_model: str, loaded_model: str):
    _, _, _, lab = _configured(db, model_name=selected_model)
    _add_channel_emulator_binding(db, lab)
    base_station = _real_driver(loaded_model)
    channel_emulator, f64 = _make()
    hal = SimpleNamespace(
        drivers={
            "baseStation": base_station,
            "channelEmulator": channel_emulator,
        }
    )
    events: list[str] = []

    @asynccontextmanager
    async def lease(_purpose: str, **options):
        events.append("lease-enter")
        validator = options.get("validate_before_remote")
        if validator is not None:
            error = validator(hal)
            if error:
                raise InstrumentTestLeaseError(error)
        events.append("remote-acquire")
        yield SimpleNamespace()
        events.append("lease-release")

    monkeypatch.setattr(api, "get_hal_service", lambda: hal)
    monkeypatch.setattr(api, "instrument_test_lease", lease)
    monkeypatch.setattr(api, "has_active_case_run", lambda: None)
    monkeypatch.setattr(api, "has_running_case_run_row", lambda _db: None)
    monkeypatch.setattr(api, "try_acquire_unsafe_diagnostic", lambda _key: "p2-73")
    monkeypatch.setattr(api, "release_unsafe_diagnostic", lambda _token: None)
    return lab, f64, events


def test_metadata_requires_base_station_and_channel_emulator():
    sequence = loader.get_sequence("propsim_f64_p08_gate")
    assert sequence.metadata.required_categories == [
        "baseStation",
        "channelEmulator",
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("selected_model", "loaded_model", "reason"),
    [
        ("CMW500", "CMW500", "只接受真实 UXM"),
        ("UXM 5G E7515B", "CMW500", "loaded driver"),
    ],
)
async def test_non_uxm_or_drift_rejected_before_any_remote_or_f64_io(
    db, monkeypatch, selected_model, loaded_model, reason,
):
    lab, f64, events = _install_api_environment(
        monkeypatch,
        db,
        selected_model=selected_model,
        loaded_model=loaded_model,
    )

    response = await api.run_diagnostic_sequence(
        "propsim_f64_p08_gate",
        api.RunSequenceRequest(lab_profile_id=lab.id, params=dict(_OK_PARAMS)),
        db,
    )

    assert response.success is False
    assert reason in response.summary
    assert events == ["lease-enter"]
    assert f64.writes == []
    row = db.get(DiagnosticRun, response.diagnostic_run_id)
    assert row is not None
    assert reason in (row.error_message or "")


@pytest.mark.asyncio
async def test_server_resolved_real_uxm_allows_existing_p08_sequence(
    db, monkeypatch,
):
    lab, _f64, events = _install_api_environment(
        monkeypatch,
        db,
        selected_model="UXM 5G E7515B",
        loaded_model="UXM 5G E7515B",
    )

    response = await api.run_diagnostic_sequence(
        "propsim_f64_p08_gate",
        api.RunSequenceRequest(lab_profile_id=lab.id, params=dict(_OK_PARAMS)),
        db,
    )

    assert response.success is True, response.summary
    assert events == ["lease-enter", "remote-acquire", "lease-release"]
    binding = response.extra["base_station_binding"]
    assert binding["manifest"]["adapter_id"] == "uxm"
    assert binding["lab_profile_id"] == str(lab.id)
    assert binding["binding_digest"]
