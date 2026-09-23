"""P2-32B probe-pattern production activation contracts."""

from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.database import Base
from app.models.chamber import ChamberConfiguration
from app.models.probe_calibration import ProbePattern
from app.schemas.probe_calibration import (
    PatternCalibrationResponse,
    PolarizationType,
    StartPatternCalibrationRequest,
)
from app.services.calibration.rf_chain_resolver import (
    RFChainResolution,
    RFChainSpec,
)
from app.services.calibration_report_generator import CalibrationReportGenerator
from app.services.probe_calibration_service import (
    CalibrationResult,
    PatternCalibrationService,
    PatternMeasurement,
)
from app.services.mimo_ota.switch_orchestrator import _build_probe_binding
from app.services.probe_pattern.consumer import get_probe_gain_at_azimuth


def _session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def _pattern(**overrides):
    now = datetime.utcnow()
    values = {
        "probe_id": 1,
        "chamber_id": uuid4(),
        "use_mock": False,
        "source": "in_chamber_measured",
        "polarization": "V",
        "frequency_mhz": 3500.0,
        "azimuth_deg": [0.0],
        "elevation_deg": [90.0],
        "gain_pattern_dbi": [5.0],
        "peak_gain_dbi": 5.0,
        "chain_correction_db": 0.0,
        "measured_at": now,
        "valid_until": now + timedelta(days=365),
        "status": "valid",
    }
    values.update(overrides)
    return ProbePattern(**values)


def test_probe_binding_uses_connection_ce_port_not_shared_instrument_label():
    """The physical output identity lives on the topology connection.

    A shared channel-emulator node labels the instrument, not one of its 32
    output connectors.  Using that label makes every connection indistinct.
    """
    binding = _build_probe_binding(
        {
            "id": "conn_ce_b17_to_probe_5v",
            "source": "ce_f64",
            "target": "probe_5v",
            "ce_port": "B17",
        },
        {
            "ce_f64": {
                "id": "ce_f64",
                "type": "channel_emulator",
                "label": "PROPSIM F64",
            },
            "probe_5v": {
                "id": "probe_5v",
                "type": "probe",
                "label": "Probe 5 V",
                "params": {"probe_id": 5, "polarization": "V"},
            },
        },
    )

    assert binding is not None
    assert binding.ce_port == "B17"

    blank = _build_probe_binding(
        {
            "id": "conn_blank",
            "source": "ce_f64",
            "target": "probe_5v",
            "ce_port": "",
        },
        {
            "ce_f64": {
                "id": "ce_f64",
                "type": "channel_emulator",
                "label": "PROPSIM F64",
            },
            "probe_5v": {
                "id": "probe_5v",
                "type": "probe",
                "label": "Probe 5 V",
                "params": {"probe_id": 5, "polarization": "V"},
            },
        },
    )
    assert blank is not None
    assert blank.ce_port == "", "explicit blank must remain invalid, not fall back"


def test_probe_pattern_persists_execution_provenance_and_warnings():
    columns = {column.key for column in inspect(ProbePattern).columns}
    assert {
        "warnings",
        "lab_profile_id",
        "operating_mode",
        "topology_id",
        "chain_id",
        "ce_port",
        "chain_correction_db",
    } <= columns

    db = _session()
    lab_profile_id = uuid4()
    pattern = _pattern(
        warnings=["tone cleanup rejected"],
        lab_profile_id=lab_profile_id,
        operating_mode="mimo_ota",
        topology_id="topology-1",
        chain_id="chain-1",
        ce_port="B1.1",
        chain_correction_db=1.25,
    )
    db.add(pattern)
    db.commit()
    db.refresh(pattern)

    assert pattern.warnings == ["tone cleanup rejected"]
    assert pattern.lab_profile_id == lab_profile_id
    assert pattern.operating_mode == "mimo_ota"
    assert pattern.topology_id == "topology-1"
    assert pattern.chain_id == "chain-1"
    assert pattern.ce_port == "B1.1"
    assert pattern.chain_correction_db == 1.25

    response = PatternCalibrationResponse.model_validate(pattern)
    assert response.warnings == ["tone cleanup rejected"]
    assert response.lab_profile_id == lab_profile_id
    assert response.topology_id == "topology-1"
    assert response.chain_id == "chain-1"
    assert response.ce_port == "B1.1"
    assert response.chain_correction_db == 1.25
    db.close()


def test_probe_pattern_warning_null_and_empty_list_remain_distinct():
    db = _session()
    historical = _pattern(probe_id=1, warnings=None)
    newly_recorded = _pattern(probe_id=2, warnings=[])
    db.add_all([historical, newly_recorded])
    db.commit()

    assert db.query(ProbePattern).filter_by(probe_id=1).one().warnings is None
    assert db.query(ProbePattern).filter_by(probe_id=2).one().warnings == []
    db.close()


def test_pattern_start_request_carries_explicit_execution_context():
    lab_profile_id = uuid4()
    chamber_id = uuid4()
    request = StartPatternCalibrationRequest(
        lab_profile_id=lab_profile_id,
        chamber_id=chamber_id,
        operating_mode="mimo_ota",
        probe_ids=[1, 2],
        polarizations=["V", "H"],
        frequency_mhz=3500.0,
        ce_tx_power_dbm=-20.0,
        sgh_gain_dbi=10.0,
        chain_correction_db=1.25,
        use_mock=False,
        calibrated_by="operator",
    )

    assert request.lab_profile_id == lab_profile_id
    assert request.chamber_id == chamber_id
    assert request.operating_mode == "mimo_ota"
    assert request.ce_tx_power_dbm == -20.0
    assert request.sgh_gain_dbi == 10.0
    assert request.chain_correction_db == 1.25
    assert request.use_mock is False


def test_real_pattern_request_requires_explicit_chain_correction():
    with pytest.raises(ValidationError, match="chain_correction_db"):
        StartPatternCalibrationRequest(
            lab_profile_id=uuid4(),
            chamber_id=uuid4(),
            probe_ids=[0],
            frequency_mhz=3500.0,
            use_mock=False,
            calibrated_by="operator",
        )


@pytest.mark.parametrize(
    ("probe_ids", "polarizations"),
    [([], ["V"]), ([0], []), ([0, 0], ["V"]), ([0], ["V", "V"])],
)
def test_pattern_request_rejects_empty_or_duplicate_measurement_axes(
    probe_ids, polarizations
):
    with pytest.raises(ValidationError):
        StartPatternCalibrationRequest(
            lab_profile_id=uuid4(),
            chamber_id=uuid4(),
            probe_ids=probe_ids,
            polarizations=polarizations,
            frequency_mhz=3500.0,
            calibrated_by="operator",
        )


@pytest.mark.parametrize("ce_tx_power_dbm", [-50.1, 20.1])
def test_pattern_request_rejects_ce_power_outside_existing_hal_domain(
    ce_tx_power_dbm,
):
    with pytest.raises(ValidationError, match="ce_tx_power_dbm"):
        StartPatternCalibrationRequest(
            lab_profile_id=uuid4(),
            chamber_id=uuid4(),
            probe_ids=[0],
            frequency_mhz=3500.0,
            ce_tx_power_dbm=ce_tx_power_dbm,
            calibrated_by="operator",
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [("sgh_gain_dbi", float("nan")), ("chain_correction_db", float("inf"))],
)
def test_pattern_request_rejects_non_finite_gain_inputs(field, value):
    values = {
        "lab_profile_id": uuid4(),
        "chamber_id": uuid4(),
        "probe_ids": [0],
        "frequency_mhz": 3500.0,
        "use_mock": False,
        "chain_correction_db": 0.0,
        "calibrated_by": "operator",
    }
    values[field] = value
    with pytest.raises(ValidationError, match=field):
        StartPatternCalibrationRequest(**values)


def test_pattern_start_request_preserves_mock_compatibility_default():
    request = StartPatternCalibrationRequest(
        lab_profile_id=uuid4(),
        chamber_id=uuid4(),
        probe_ids=[1],
        frequency_mhz=3500.0,
        calibrated_by="operator",
    )

    assert request.use_mock is True
    assert request.operating_mode == "mimo_ota"


def _resolution(lab_profile_id, chamber_id, chains, *, warnings=None):
    return RFChainResolution(
        lab_profile_id=lab_profile_id,
        chamber_id=chamber_id,
        topology_id="topology-1",
        topology_name="Production topology",
        operating_mode="mimo_ota",
        chains=chains,
        warnings=list(warnings or []),
    )


def _add_chamber(db, chamber_id, *, num_probes):
    db.add(
        ChamberConfiguration(
            id=chamber_id,
            name="Pattern chamber",
            chamber_type="custom",
            chamber_radius_m=3.0,
            num_probes=num_probes,
        )
    )
    db.commit()


@pytest.mark.asyncio
async def test_real_pattern_requires_lab_profile_before_measurement(monkeypatch):
    db = _session()
    service = PatternCalibrationService()
    service._real_pattern_measurements = AsyncMock()

    result = await service.execute_pattern_calibration(
        db=db,
        chamber_id=uuid4(),
        probe_ids=[1],
        polarizations=[PolarizationType.V],
        frequency_mhz=3500.0,
        calibrated_by="operator",
        chain_correction_db=0.0,
        use_mock=False,
    )

    assert result.success is False
    assert "LabProfile" in result.message
    service._real_pattern_measurements.assert_not_awaited()
    db.close()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("probe_ids", "polarizations"),
    [([], [PolarizationType.V]), ([0], []), ([0, 0], [PolarizationType.V])],
)
async def test_pattern_service_rejects_empty_or_duplicate_axes_before_measurement(
    probe_ids, polarizations
):
    db = _session()
    service = PatternCalibrationService()

    result = await service.execute_pattern_calibration(
        db=db,
        chamber_id=uuid4(),
        probe_ids=probe_ids,
        polarizations=polarizations,
        frequency_mhz=3500.0,
        calibrated_by="operator",
        use_mock=True,
    )

    assert result.success is False
    assert "non-empty and unique" in result.message
    db.close()


@pytest.mark.asyncio
async def test_real_pattern_maps_zero_based_pattern_id_to_one_based_rf_chain(
    monkeypatch,
):
    db = _session()
    lab_profile_id = uuid4()
    chamber_id = uuid4()
    _add_chamber(db, chamber_id, num_probes=2)
    chains = [
        RFChainSpec(f"chain-{probe_id}", f"B{probe_id}.1", probe_id, "V")
        for probe_id in (1, 2)
    ]
    monkeypatch.setattr(
        "app.services.calibration.rf_chain_resolver.resolve_rf_chains",
        lambda *_args, **_kwargs: _resolution(lab_profile_id, chamber_id, chains),
    )
    service = PatternCalibrationService()

    async def _measure(**kwargs):
        assert kwargs["probe_id"] == 0
        assert kwargs["route_target"] == "chain-1"
        assert kwargs["ce_port"] == "B1.1"
        return [PatternMeasurement(0.0, 0.0, 5.0)]

    service._real_pattern_measurements = AsyncMock(side_effect=_measure)
    result = await service.execute_pattern_calibration(
        db=db,
        lab_profile_id=lab_profile_id,
        chamber_id=chamber_id,
        probe_ids=[0],
        polarizations=[PolarizationType.V],
        frequency_mhz=3500.0,
        azimuth_step_deg=360.0,
        elevation_step_deg=181.0,
        calibrated_by="operator",
        chain_correction_db=0.0,
        use_mock=False,
    )

    assert result.success is True
    row = db.query(ProbePattern).one()
    assert row.probe_id == 0
    assert row.chain_id == "chain-1"
    db.close()


@pytest.mark.asyncio
async def test_real_pattern_freezes_unique_resolved_chain_and_routes_measurement(
    monkeypatch,
):
    db = _session()
    lab_profile_id = uuid4()
    chamber_id = uuid4()
    _add_chamber(db, chamber_id, num_probes=1)
    chain = RFChainSpec(
        chain_id="chain-1",
        ce_port="B1.1",
        probe_id=1,
        polarization="V",
    )
    monkeypatch.setattr(
        "app.services.calibration.rf_chain_resolver.resolve_rf_chains",
        lambda *_args, **_kwargs: _resolution(
            lab_profile_id,
            chamber_id,
            [chain],
            warnings=["topology diagnostic"],
        ),
    )
    service = PatternCalibrationService()

    async def _measure(**kwargs):
        assert kwargs["ce_port"] == "B1.1"
        assert kwargs["route_target"] == "chain-1"
        kwargs["warnings"].append("cleanup diagnostic")
        return [PatternMeasurement(0.0, 0.0, 5.0)]

    service._real_pattern_measurements = AsyncMock(side_effect=_measure)

    result = await service.execute_pattern_calibration(
        db=db,
        lab_profile_id=lab_profile_id,
        operating_mode="mimo_ota",
        chamber_id=chamber_id,
        probe_ids=[0],
        polarizations=[PolarizationType.V],
        frequency_mhz=3500.0,
        azimuth_step_deg=360.0,
        elevation_step_deg=181.0,
        calibrated_by="operator",
        chain_correction_db=0.0,
        use_mock=False,
    )

    assert result.success is True
    row = db.query(ProbePattern).one()
    assert row.lab_profile_id == lab_profile_id
    assert row.operating_mode == "mimo_ota"
    assert row.topology_id == "topology-1"
    assert row.chain_id == "chain-1"
    assert row.ce_port == "B1.1"
    assert row.chain_correction_db == 0.0
    assert row.warnings == ["topology diagnostic", "cleanup diagnostic"]
    assert result.warnings == ["topology diagnostic", "cleanup diagnostic"]
    db.close()


@pytest.mark.asyncio
async def test_real_pattern_rejects_ambiguous_chain_before_measurement(monkeypatch):
    db = _session()
    lab_profile_id = uuid4()
    chamber_id = uuid4()
    _add_chamber(db, chamber_id, num_probes=1)
    chains = [
        RFChainSpec(
            chain_id=f"chain-{suffix}",
            ce_port=f"B{suffix}.1",
            probe_id=1,
            polarization="V",
        )
        for suffix in (1, 2)
    ]
    monkeypatch.setattr(
        "app.services.calibration.rf_chain_resolver.resolve_rf_chains",
        lambda *_args, **_kwargs: _resolution(lab_profile_id, chamber_id, chains),
    )
    service = PatternCalibrationService()
    service._real_pattern_measurements = AsyncMock()

    result = await service.execute_pattern_calibration(
        db=db,
        lab_profile_id=lab_profile_id,
        chamber_id=chamber_id,
        probe_ids=[0],
        polarizations=[PolarizationType.V],
        frequency_mhz=3500.0,
        calibrated_by="operator",
        chain_correction_db=0.0,
        use_mock=False,
    )

    assert result.success is False
    assert "exactly one RF chain" in result.message
    service._real_pattern_measurements.assert_not_awaited()
    assert db.query(ProbePattern).count() == 0
    db.close()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("chain_id", "ce_port"),
    [("?", "B1.1"), ("chain-1", "?"), (" ", "B1.1"), ("chain-1", " ")],
)
async def test_real_pattern_rejects_placeholder_route_identity_before_measurement(
    monkeypatch, chain_id, ce_port
):
    db = _session()
    lab_profile_id = uuid4()
    chamber_id = uuid4()
    _add_chamber(db, chamber_id, num_probes=1)
    chain = RFChainSpec(chain_id, ce_port, 1, "V")
    monkeypatch.setattr(
        "app.services.calibration.rf_chain_resolver.resolve_rf_chains",
        lambda *_args, **_kwargs: _resolution(
            lab_profile_id, chamber_id, [chain]
        ),
    )
    service = PatternCalibrationService()
    service._real_pattern_measurements = AsyncMock()

    result = await service.execute_pattern_calibration(
        db=db,
        lab_profile_id=lab_profile_id,
        chamber_id=chamber_id,
        probe_ids=[0],
        polarizations=[PolarizationType.V],
        frequency_mhz=3500.0,
        calibrated_by="operator",
        chain_correction_db=0.0,
        use_mock=False,
    )

    assert result.success is False
    assert "incomplete" in result.message
    service._real_pattern_measurements.assert_not_awaited()
    db.close()


@pytest.mark.asyncio
async def test_real_pattern_keeps_cleanup_warnings_on_their_own_row(monkeypatch):
    db = _session()
    lab_profile_id = uuid4()
    chamber_id = uuid4()
    _add_chamber(db, chamber_id, num_probes=2)
    chains = [
        RFChainSpec(
            chain_id=f"chain-{probe_id}",
            ce_port=f"B{probe_id}.1",
            probe_id=probe_id,
            polarization="V",
        )
        for probe_id in (1, 2)
    ]
    monkeypatch.setattr(
        "app.services.calibration.rf_chain_resolver.resolve_rf_chains",
        lambda *_args, **_kwargs: _resolution(lab_profile_id, chamber_id, chains),
    )
    service = PatternCalibrationService()

    async def _measure(**kwargs):
        kwargs["warnings"].append(f"cleanup {kwargs['probe_id']}")
        return [PatternMeasurement(0.0, 0.0, 5.0)]

    service._real_pattern_measurements = AsyncMock(side_effect=_measure)
    result = await service.execute_pattern_calibration(
        db=db,
        lab_profile_id=lab_profile_id,
        chamber_id=chamber_id,
        probe_ids=[0, 1],
        polarizations=[PolarizationType.V],
        frequency_mhz=3500.0,
        azimuth_step_deg=360.0,
        elevation_step_deg=181.0,
        calibrated_by="operator",
        chain_correction_db=0.0,
        use_mock=False,
    )

    assert result.success is True
    rows = db.query(ProbePattern).order_by(ProbePattern.probe_id).all()
    assert rows[0].warnings == ["cleanup 0"]
    assert rows[1].warnings == ["cleanup 1"]
    assert result.warnings == ["cleanup 0", "cleanup 1"]
    db.close()


@pytest.mark.asyncio
async def test_real_pattern_rolls_back_all_rows_when_later_route_fails(monkeypatch):
    db = _session()
    lab_profile_id = uuid4()
    chamber_id = uuid4()
    _add_chamber(db, chamber_id, num_probes=2)
    chains = [
        RFChainSpec(
            chain_id=f"chain-{probe_id}",
            ce_port=f"B{probe_id}.1",
            probe_id=probe_id,
            polarization="V",
        )
        for probe_id in (1, 2)
    ]
    monkeypatch.setattr(
        "app.services.calibration.rf_chain_resolver.resolve_rf_chains",
        lambda *_args, **_kwargs: _resolution(lab_profile_id, chamber_id, chains),
    )
    service = PatternCalibrationService()

    async def _measure(**kwargs):
        if kwargs["probe_id"] == 1:
            raise RuntimeError("second route failed")
        return [PatternMeasurement(0.0, 0.0, 5.0)]

    service._real_pattern_measurements = AsyncMock(side_effect=_measure)
    result = await service.execute_pattern_calibration(
        db=db,
        lab_profile_id=lab_profile_id,
        chamber_id=chamber_id,
        probe_ids=[0, 1],
        polarizations=[PolarizationType.V],
        frequency_mhz=3500.0,
        azimuth_step_deg=360.0,
        elevation_step_deg=181.0,
        calibrated_by="operator",
        chain_correction_db=0.0,
        use_mock=False,
    )

    assert result.success is False
    assert "second route failed" in result.message
    assert db.query(ProbePattern).count() == 0
    db.close()


def test_measured_pattern_requires_current_frozen_route(monkeypatch):
    db = _session()
    lab_profile_id = uuid4()
    chamber_id = uuid4()
    current_chain = RFChainSpec(
        chain_id="chain-current",
        ce_port="B1.1",
        probe_id=0,
        polarization="V",
    )
    monkeypatch.setattr(
        "app.services.calibration.rf_chain_resolver.resolve_rf_chains",
        lambda *_args, **_kwargs: _resolution(
            lab_profile_id, chamber_id, [current_chain]
        ),
    )
    matching = _pattern(
        probe_id=0,
        chamber_id=chamber_id,
        source="in_chamber_measured",
        lab_profile_id=lab_profile_id,
        operating_mode="mimo_ota",
        topology_id="topology-1",
        chain_id="chain-current",
        ce_port="B1.1",
        peak_gain_dbi=6.0,
    )
    db.add(matching)
    db.commit()

    assert get_probe_gain_at_azimuth(
        db,
        1,
        0.0,
        3500.0,
        chamber_id=chamber_id,
        lab_profile_id=lab_profile_id,
        operating_mode="mimo_ota",
    ) == 6.0

    matching.ce_port = "B9.9"
    db.commit()
    assert get_probe_gain_at_azimuth(
        db,
        1,
        0.0,
        3500.0,
        chamber_id=chamber_id,
        lab_profile_id=lab_profile_id,
        operating_mode="mimo_ota",
    ) is None
    db.close()


def test_measured_pattern_requires_explicit_chain_correction(monkeypatch):
    db = _session()
    lab_profile_id = uuid4()
    chamber_id = uuid4()
    current_chain = RFChainSpec("chain-current", "B1.1", 0, "V")
    monkeypatch.setattr(
        "app.services.calibration.rf_chain_resolver.resolve_rf_chains",
        lambda *_args, **_kwargs: _resolution(
            lab_profile_id, chamber_id, [current_chain]
        ),
    )
    db.add(
        _pattern(
            probe_id=0,
            chamber_id=chamber_id,
            lab_profile_id=lab_profile_id,
            operating_mode="mimo_ota",
            topology_id="topology-1",
            chain_id="chain-current",
            ce_port="B1.1",
            chain_correction_db=None,
        )
    )
    db.commit()

    assert get_probe_gain_at_azimuth(
        db,
        1,
        0.0,
        3500.0,
        chamber_id=chamber_id,
        lab_profile_id=lab_profile_id,
        operating_mode="mimo_ota",
    ) is None
    db.close()


def test_measured_pattern_rejects_placeholder_current_route_identity(monkeypatch):
    db = _session()
    lab_profile_id = uuid4()
    chamber_id = uuid4()
    placeholder_chain = RFChainSpec("?", "B1.1", 0, "V")
    monkeypatch.setattr(
        "app.services.calibration.rf_chain_resolver.resolve_rf_chains",
        lambda *_args, **_kwargs: _resolution(
            lab_profile_id, chamber_id, [placeholder_chain]
        ),
    )
    db.add(
        _pattern(
            probe_id=0,
            chamber_id=chamber_id,
            lab_profile_id=lab_profile_id,
            operating_mode="mimo_ota",
            topology_id="topology-1",
            chain_id="?",
            ce_port="B1.1",
        )
    )
    db.commit()

    assert get_probe_gain_at_azimuth(
        db,
        1,
        0.0,
        3500.0,
        chamber_id=chamber_id,
        lab_profile_id=lab_profile_id,
        operating_mode="mimo_ota",
    ) is None
    db.close()


@pytest.mark.asyncio
async def test_pattern_api_rejects_success_without_persisted_calibration(
    monkeypatch
):
    from app.api.probe_calibration import start_pattern_calibration

    db = _session()
    chamber_id = uuid4()
    _add_chamber(db, chamber_id, num_probes=1)
    request = StartPatternCalibrationRequest(
        lab_profile_id=uuid4(),
        chamber_id=chamber_id,
        probe_ids=[0],
        polarizations=["V"],
        frequency_mhz=3500.0,
        calibrated_by="operator",
    )
    monkeypatch.setattr(
        PatternCalibrationService,
        "execute_pattern_calibration",
        AsyncMock(
            return_value=CalibrationResult(
                success=True,
                message="completed without rows",
                data={"calibration_ids": []},
            )
        ),
    )

    with pytest.raises(HTTPException) as exc_info:
        await start_pattern_calibration(request=request, db=db)

    assert exc_info.value.status_code == 500
    assert "calibration" in str(exc_info.value.detail).lower()
    db.close()


def test_measured_pattern_maps_zero_based_pattern_id_to_one_based_current_route(
    monkeypatch,
):
    db = _session()
    lab_profile_id = uuid4()
    chamber_id = uuid4()
    current_chain = RFChainSpec("chain-current", "B1.1", 1, "V")
    monkeypatch.setattr(
        "app.services.calibration.rf_chain_resolver.resolve_rf_chains",
        lambda *_args, **_kwargs: _resolution(
            lab_profile_id, chamber_id, [current_chain]
        ),
    )
    db.add(
        _pattern(
            probe_id=0,
            chamber_id=chamber_id,
            source="in_chamber_measured",
            lab_profile_id=lab_profile_id,
            operating_mode="mimo_ota",
            topology_id="topology-1",
            chain_id="chain-current",
            ce_port="B1.1",
            peak_gain_dbi=6.0,
        )
    )
    db.commit()

    assert get_probe_gain_at_azimuth(
        db,
        1,
        0.0,
        3500.0,
        chamber_id=chamber_id,
        lab_profile_id=lab_profile_id,
        operating_mode="mimo_ota",
    ) == 6.0
    db.close()


def test_vendor_pattern_is_route_independent(monkeypatch):
    db = _session()
    chamber_id = uuid4()
    db.add(
        _pattern(
            probe_id=0,
            chamber_id=chamber_id,
            source="vendor_datasheet",
            peak_gain_dbi=7.0,
        )
    )
    db.commit()

    def _must_not_resolve(*_args, **_kwargs):
        raise AssertionError("vendor data must not depend on current topology")

    monkeypatch.setattr(
        "app.services.calibration.rf_chain_resolver.resolve_rf_chains",
        _must_not_resolve,
    )
    assert get_probe_gain_at_azimuth(
        db,
        1,
        0.0,
        3500.0,
        chamber_id=chamber_id,
        lab_profile_id=uuid4(),
        operating_mode="mimo_ota",
    ) == 7.0
    db.close()


def test_pattern_report_discloses_route_but_never_invents_pass_verdict():
    db = _session()
    lab_profile_id = uuid4()
    chamber_id = uuid4()
    db.add(
        ChamberConfiguration(
            id=chamber_id,
            name="Pattern chamber",
            chamber_type="custom",
            chamber_radius_m=3.0,
            num_probes=32,
        )
    )
    db.add(
        _pattern(
            chamber_id=chamber_id,
            lab_profile_id=lab_profile_id,
            operating_mode="mimo_ota",
            topology_id="topology-1",
            chain_id="chain-1",
            ce_port="B1.1",
            warnings=["cleanup diagnostic"],
            source="in_chamber_measured",
        )
    )
    db.commit()

    report = CalibrationReportGenerator(db)._collect_probe_data(
        chamber_id=chamber_id,
        calibration_type="pattern",
    )
    row = report["probe_calibration"]["pattern"][0]
    assert row["validation_pass"] is None
    assert row["source"] == "in_chamber_measured"
    assert row["warnings"] == ["cleanup diagnostic"]
    assert row["lab_profile_id"] == str(lab_profile_id)
    assert row["topology_id"] == "topology-1"
    assert row["chain_id"] == "chain-1"
    assert row["ce_port"] == "B1.1"
    assert row["chain_correction_db"] == 0.0
    assert report["execution_summary"]["undetermined"] == 1
    db.close()


def test_pattern_only_audit_report_keeps_pass_rate_undetermined(monkeypatch, tmp_path):
    db = _session()
    chamber_id = uuid4()
    db.add(
        ChamberConfiguration(
            id=chamber_id,
            name="Pattern chamber",
            chamber_type="custom",
            chamber_radius_m=3.0,
            num_probes=32,
        )
    )
    db.add(_pattern(chamber_id=chamber_id, source="in_chamber_measured"))
    db.commit()

    generator = CalibrationReportGenerator(db)
    captured = {}

    def _capture(data, _template, output_path):
        captured.update(data)
        return str(output_path)

    monkeypatch.setattr(generator.pdf_generator, "generate_report", _capture)
    generator.generate_audit_report(
        chamber_id,
        start_date=datetime.utcnow() - timedelta(days=1),
        end_date=datetime.utcnow() + timedelta(days=1),
        output_path=str(tmp_path / "audit.pdf"),
    )

    assert captured["summary"] == {
        "total_calibrations": 1,
        "passed": 0,
        "failed": 0,
        "undetermined": 1,
        "pass_rate": None,
    }
    db.close()


def test_pattern_api_contract_is_mirrored_to_checked_schema_and_generated_types():
    import yaml

    from app.main import app

    repo_root = Path(__file__).resolve().parents[2]
    live = app.openapi()
    checked = yaml.safe_load((repo_root / "api/openapi.yaml").read_text())
    route = "/api/v1/calibration/probe/pattern/start"
    assert route in live["paths"]
    assert route in checked["paths"]

    expected_request = {
        "lab_profile_id",
        "chamber_id",
        "operating_mode",
        "probe_ids",
        "polarizations",
        "frequency_mhz",
        "azimuth_step_deg",
        "elevation_step_deg",
        "measurement_distance_m",
        "reference_antenna_id",
        "turntable_id",
        "ce_tx_power_dbm",
        "sgh_gain_dbi",
        "chain_correction_db",
        "use_mock",
        "calibrated_by",
    }
    expected_response_route = {
        "warnings",
        "lab_profile_id",
        "operating_mode",
        "topology_id",
        "chain_id",
        "ce_port",
        "chain_correction_db",
        "source",
    }
    assert set(live["components"]["schemas"]["StartPatternCalibrationRequest"]["properties"]) == expected_request
    assert set(checked["components"]["schemas"]["StartPatternCalibrationRequest"]["properties"]) == expected_request
    for document in (live, checked):
        frequency = document["components"]["schemas"]["StartPatternCalibrationRequest"]["properties"]["frequency_mhz"]
        assert frequency["minimum"] == 100
        assert frequency["maximum"] == 100000
        ce_power = document["components"]["schemas"]["StartPatternCalibrationRequest"]["properties"]["ce_tx_power_dbm"]
        assert ce_power["minimum"] == -50
        assert ce_power["maximum"] == 20
        probe_ids = document["components"]["schemas"]["StartPatternCalibrationRequest"]["properties"]["probe_ids"]
        polarizations = document["components"]["schemas"]["StartPatternCalibrationRequest"]["properties"]["polarizations"]
        assert probe_ids["minItems"] == 1
        assert probe_ids["uniqueItems"] is True
        assert polarizations["minItems"] == 1
        assert polarizations["uniqueItems"] is True
    assert expected_response_route <= set(
        live["components"]["schemas"]["PatternCalibrationResponse"]["properties"]
    )
    assert expected_response_route <= set(
        checked["components"]["schemas"]["PatternCalibrationResponse"]["properties"]
    )

    generated = (repo_root / "gui/src/types/api.generated.ts").read_text()
    manual = (repo_root / "gui/src/types/probeCalibration.ts").read_text()
    for token in (route, "StartPatternCalibrationRequest", "PatternCalibrationResponse"):
        assert token in generated
    for field in expected_request | expected_response_route:
        assert field in generated
        assert field in manual


def test_pattern_gui_has_one_live_start_workflow():
    repo_root = Path(__file__).resolve().parents[2]
    app_source = (repo_root / "gui/src/App.tsx").read_text()
    page_source = (
        repo_root / "gui/src/features/ProbeCalibration/ProbeCalibrationPage.tsx"
    ).read_text()
    panel_source = (
        repo_root
        / "gui/src/features/ProbeCalibration/components/PatternMeasurementPanel.tsx"
    ).read_text()

    assert app_source.count("<ProbeCalibrationPage") == 1
    assert page_source.count("<PatternMeasurementPanel") == 1
    assert panel_source.count("useStartPatternCalibration()") == 1
    assert "ce_port" not in panel_source
