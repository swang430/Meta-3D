"""P1-60: 最近一次手工执行暴露出的真值错位回归契约。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from importlib import import_module
from types import SimpleNamespace
from uuid import uuid4

import pytest

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
