"""P1-60: 最近一次手工执行暴露出的真值错位回归契约。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from importlib import import_module
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models.probe_calibration import ChannelPhaseCalibration
from app.services.phase_calibration_service import PhaseCalibrationService
from app.hal.channel_emulator import ChannelLoadMode
from app.services.channel_generation.gcm_strategy import NativeModelStrategy
from app.services.channel_engine_client import ChannelEngineClient
from app.services.mimo_ota import channel_asset_resolver
from app.services.mimo_ota.executors import measure
from app.services.probe_pattern import consumer


def _chamber(*, probes: int = 16, polarizations: int = 2) -> SimpleNamespace:
    return SimpleNamespace(
        num_probes=probes,
        num_polarizations=polarizations,
        typical_cable_loss_db=5.0,
        probe_gain_dbi=8.0,
        has_pa=False,
        pa_gain_db=None,
        has_duplexer=False,
        duplexer_insertion_loss_db=None,
    )


def test_one_based_path_loss_certificate_maps_exactly_to_ports_1_through_32():
    client = ChannelEngineClient(db=None)
    client._query_phase_compensation = lambda *args, **kwargs: {}
    cert = SimpleNamespace(
        calibrated_at=datetime.utcnow(),
        probe_path_losses={
            str(probe_id): {
                "path_loss_db": float(probe_id),
                "pol_h_db": float(probe_id) + 0.5,
            }
            for probe_id in range(1, 17)
        },
    )

    entries = client._query_calibration_entries(
        uuid4(), 3_550_000_000, _chamber(), path_loss_calibration=cert
    )

    assert [entry["port_id"] for entry in entries] == list(range(1, 33))


def test_four_cardinal_azimuths_use_one_based_rf_chain_probe_ids():
    assert hasattr(consumer, "select_active_rf_chain_probe_id")
    selector = consumer.select_active_rf_chain_probe_id
    assert [selector(16, az) for az in (0, 90, 180, 270)] == [1, 5, 9, 13]


def test_partial_per_chain_path_loss_is_rejected_instead_of_mixed_with_average():
    assert hasattr(measure, "_missing_rf_chain_path_loss_azimuths")
    missing = measure._missing_rf_chain_path_loss_azimuths(
        num_probes=16,
        azimuths_deg=[0.0, 90.0, 180.0, 270.0],
        chain_pl_by_probe_pol={(5, "V"): 12.0, (9, "V"): 13.0, (13, "V"): 14.0},
    )
    assert missing == [{"azimuth_deg": 0.0, "probe_id": 1, "polarization": "V"}]


def test_vendor_asset_resolution_exposes_uma_scenario():
    assert "scenario" in channel_asset_resolver.ResolvedChannelAsset.__dataclass_fields__
    resolved = channel_asset_resolver.ResolvedChannelAsset(
        engine_mode="keysight_gcm",
        asset=SimpleNamespace(),
        scenario="UMa",
    )
    assert resolved.scenario == "UMa"


@pytest.mark.asyncio
async def test_native_model_derives_uma_from_model_name_without_umi_default():
    class Emulator:
        def get_supported_load_modes(self):
            return [ChannelLoadMode.NATIVE_MODEL]

        async def load_channel(self, **kwargs):
            self.loaded = kwargs
            return True

    emulator = Emulator()
    ok = await NativeModelStrategy(
        emulator, SimpleNamespace(), [], generate_oop=False
    ).generate_and_load(
        {"emulation_file": r"D:\Scenario\UMa.smu"},
        {"model_name": "UMa CDL-C NLOS", "session_id": "p1-60"},
    )

    assert ok is True
    assert emulator.loaded["scenario"] == "UMa"


@pytest.mark.asyncio
async def test_native_model_rejects_declared_scenario_conflict_in_any_token_order():
    class Emulator:
        def get_supported_load_modes(self):
            return [ChannelLoadMode.NATIVE_MODEL]

        async def load_channel(self, **kwargs):
            raise AssertionError("scenario conflict must fail before hardware I/O")

    ok = await NativeModelStrategy(
        Emulator(), SimpleNamespace(), [], generate_oop=False
    ).generate_and_load(
        {"emulation_file": r"D:\Scenario\UMa.smu"},
        {
            "model_name": "CDL-C UMa NLOS",
            "scenario": "UMi",
            "session_id": "p1-60-conflict",
        },
    )

    assert ok is False


def test_frequency_warning_names_missing_center_when_bandwidth_is_declared():
    assert hasattr(measure, "_describe_f64_frequency_verification_gap")
    message = measure._describe_f64_frequency_verification_gap(
        f64_center_mhz=None,
        f64_bandwidth_source="channel_asset_or_scd_declared",
        declared_bandwidth_mhz=40.0,
    )
    assert "中心频率" in message
    assert "未回读" in message
    assert "40" in message
    assert "没有可信资产声明" not in message


def test_human_timestamp_uses_explicit_local_timezone_without_changing_instant():
    human_time = import_module("app.utils.human_time")
    instant = datetime(2026, 8, 22, 2, 37, 23, tzinfo=timezone.utc)
    china = timezone(timedelta(hours=8))

    assert human_time.format_human_local_timestamp(
        instant, timezone_override=china
    ) == "20260822-103723"
    assert instant.isoformat() == "2026-08-22T02:37:23+00:00"


def test_incomplete_or_unknown_phase_compensation_is_rejected_fail_closed():
    assert hasattr(ChannelEngineClient, "_validate_phase_compensation_map")
    validate = ChannelEngineClient._validate_phase_compensation_map
    assert validate({port: 0.0 for port in range(1, 33)}, num_ports=32) != {}
    assert validate({port: 0.0 for port in range(1, 32)}, num_ports=32) == {}
    assert validate({port: 0.0 for port in range(0, 32)}, num_ports=32) == {}


@pytest.fixture
def phase_db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    ChannelPhaseCalibration.__table__.create(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()


def _phase_row(*, chamber_id, use_mock, frequency_mhz=3550.0, ports=4, days=30):
    now = datetime.utcnow()
    return ChannelPhaseCalibration(
        chamber_id=chamber_id,
        frequency_mhz=frequency_mhz,
        reference_channel_id=1,
        channel_phases=[{"channel_id": port} for port in range(1, ports + 1)],
        phase_compensation=[
            {"channel_id": port, "compensation_deg": float(port)}
            for port in range(1, ports + 1)
        ],
        use_mock=use_mock,
        calibrated_at=now,
        valid_until=now + timedelta(days=days),
        status="valid",
    )


def test_phase_query_is_frequency_validity_provenance_and_full_set_allowlist(phase_db):
    chamber_id = uuid4()
    phase_db.add_all(
        [
            _phase_row(chamber_id=chamber_id, use_mock=False),
            _phase_row(chamber_id=chamber_id, use_mock=None),
            _phase_row(chamber_id=chamber_id, use_mock=True),
            _phase_row(chamber_id=chamber_id, use_mock=False, frequency_mhz=3500.0),
            _phase_row(chamber_id=chamber_id, use_mock=False, days=-1),
        ]
    )
    phase_db.commit()
    client = ChannelEngineClient(phase_db)

    real = client._query_phase_compensation(
        chamber_id, 3_550_000_000, num_ports=4, use_mock=False
    )
    mock = client._query_phase_compensation(
        chamber_id, 3_550_000_000, num_ports=4, use_mock=True
    )

    assert real == {1: 1.0, 2: 2.0, 3: 3.0, 4: 4.0}
    assert mock == real


@pytest.mark.asyncio
async def test_mock_phase_writer_marks_provenance_and_uses_one_based_channels(phase_db):
    chamber_id = uuid4()
    await PhaseCalibrationService(phase_db, use_mock=True).calibrate_phases(
        chamber_id=chamber_id,
        frequency_mhz=3550.0,
        num_channels=4,
    )
    record = phase_db.query(ChannelPhaseCalibration).one()
    assert record.use_mock is True
    assert record.measurement_method == "mock"
    assert [row["channel_id"] for row in record.phase_compensation] == [1, 2, 3, 4]
