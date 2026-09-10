"""P1-76：实时监控只发布观测，不编造数值。"""

from datetime import datetime
from pathlib import Path

import pytest
import yaml


EXPECTED_METRICS = {"throughput", "snr", "eirp", "temperature"}


def _assert_unavailable_observations(
    metrics: dict[str, dict[str, object]],
) -> None:
    assert set(metrics) == EXPECTED_METRICS
    for observation in metrics.values():
        assert observation["value"] is None
        assert observation["status"] in {"unavailable", "simulated"}
        assert observation["provenance"] in {"unknown", "real", "simulated"}
        assert isinstance(observation["reason"], str)
        assert observation["reason"]


class _RealBaseStation:
    def __init__(self, throughput_mbps: object, scope: str = "pcell") -> None:
        self.throughput_mbps = throughput_mbps
        self.scope = scope
        self.calls = 0

    async def get_metrics(self):
        from app.hal.base import InstrumentMetrics

        self.calls += 1
        return InstrumentMetrics(
            timestamp=datetime(2026, 9, 10, 0, 0, 0),
            metrics={
                "dl_throughput_current_mbps": self.throughput_mbps,
                "kpi_valid": {"dl_throughput_current": True},
                "throughput_scope": self.scope,
            },
        )


class _PoisonChannelEmulator:
    async def get_metrics(self):
        raise AssertionError(
            "channel-emulator demo metrics must not be polled as live KPI truth"
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("throughput_mbps", "scope"),
    [(0.0, "pcell"), (10.0, "pcell"), (90.0, "nr_all_cells")],
)
async def test_real_base_station_current_throughput_remains_distinguishable(
    throughput_mbps,
    scope,
):
    from app.services.instrument_hal_service import InstrumentHALService

    base_station = _RealBaseStation(throughput_mbps, scope)
    service = InstrumentHALService(cache_ttl=0)
    service._initialized = True
    service.drivers = {
        "channelEmulator": _PoisonChannelEmulator(),
        "baseStation": base_station,
    }

    metrics = await service.get_aggregated_metrics()

    assert metrics["throughput"] == {
        "value": throughput_mbps,
        "unit": "Mbps",
        "timestamp": "2026-09-10T00:00:00",
        "status": "observed",
        "provenance": "real",
        "reason": None,
    }
    assert base_station.calls == 1
    assert metrics["snr"]["value"] is None
    assert metrics["eirp"]["value"] is None
    assert metrics["temperature"]["value"] is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "metrics_payload",
    [
        {},
        {
            "dl_throughput_current_mbps": 0.0,
            "kpi_valid": {"dl_throughput_current": False},
            "throughput_scope": "pcell",
        },
        {
            "dl_throughput_current_mbps": float("nan"),
            "kpi_valid": {"dl_throughput_current": True},
            "throughput_scope": "pcell",
        },
        {
            "dl_throughput_current_mbps": -1.0,
            "kpi_valid": {"dl_throughput_current": True},
            "throughput_scope": "pcell",
        },
        {
            "dl_throughput_current_mbps": 150.0,
            "kpi_valid": {"dl_throughput_current": True},
            "throughput_scope": "simulated",
        },
        {
            "dl_throughput_current_mbps": 150.0,
            "kpi_valid": {"dl_throughput_current": True},
            "throughput_scope": "unknown",
        },
        {
            "dl_throughput_current_mbps": 150.0,
            "kpi_valid": {"dl_throughput_current": True},
        },
    ],
)
async def test_missing_invalid_or_simulated_throughput_never_becomes_a_number(
    metrics_payload,
):
    from app.hal.base import InstrumentMetrics
    from app.services.instrument_hal_service import InstrumentHALService

    class _Driver:
        async def get_metrics(self):
            return InstrumentMetrics(
                timestamp=datetime(2026, 9, 10, 0, 0, 0),
                metrics=metrics_payload,
            )

    service = InstrumentHALService(cache_ttl=0)
    service._initialized = True
    service.drivers = {"baseStation": _Driver()}

    metrics = await service.get_aggregated_metrics()

    assert metrics["throughput"]["value"] is None
    assert metrics["throughput"]["status"] != "observed"


@pytest.mark.asyncio
async def test_mock_base_station_is_labelled_without_polling_random_metrics():
    from app.hal.base_station import MockBaseStation
    from app.hal.uxm_base_station import RealUxmDriver
    from app.services.instrument_hal_service import InstrumentHALService

    class _PoisonMockBaseStation(MockBaseStation):
        async def get_metrics(self):
            raise AssertionError("mock metrics must not be polled")

    service = InstrumentHALService(cache_ttl=0)
    service._initialized = True
    service.drivers = {
        "baseStation": _PoisonMockBaseStation(
            "mock-bs",
            {"model": RealUxmDriver.adapter_manifest.model_name},
            adapter_manifest=RealUxmDriver.adapter_manifest,
        )
    }

    metrics = await service.get_aggregated_metrics()

    _assert_unavailable_observations(metrics)
    assert metrics["throughput"]["status"] == "simulated"
    assert metrics["throughput"]["provenance"] == "simulated"


@pytest.mark.asyncio
async def test_hal_failure_returns_unavailable_observations_not_fallback_numbers(
    monkeypatch,
):
    import app.api.monitoring as monitoring

    class _BrokenHAL:
        async def get_aggregated_metrics(self):
            raise RuntimeError("offline")

    monkeypatch.setattr(monitoring, "is_test_monitoring_enabled", lambda: True)
    monkeypatch.setattr(monitoring, "get_hal_service", lambda: _BrokenHAL())

    metrics = await monitoring.generate_monitoring_data()

    _assert_unavailable_observations(metrics)


@pytest.mark.asyncio
async def test_idle_monitoring_clears_stale_values_without_touching_hal(monkeypatch):
    import app.api.monitoring as monitoring

    monkeypatch.setattr(monitoring, "is_test_monitoring_enabled", lambda: False)
    monkeypatch.setattr(
        monitoring,
        "get_hal_service",
        lambda: pytest.fail("idle monitoring must not read HAL"),
    )

    metrics = await monitoring.generate_monitoring_data()

    _assert_unavailable_observations(metrics)
    assert all(
        observation["reason"] == "当前没有启用实时监控的测试租约"
        for observation in metrics.values()
    )


def test_rest_metric_schema_requires_observation_provenance():
    from app.api.monitoring import MonitoringMetric

    metric = MonitoringMetric.model_validate(
        {
            "name": "snr",
            "value": None,
            "unit": "dB",
            "timestamp": "2026-09-10T00:00:00Z",
            "status": "unavailable",
            "provenance": "unknown",
            "reason": "no authoritative source",
        }
    )

    assert metric.value is None
    assert metric.status == "unavailable"
    assert metric.provenance == "unknown"


def test_live_checked_and_generated_contracts_share_monitoring_observation_shape():
    from app.main import app

    repo_root = Path(__file__).resolve().parents[2]
    live = app.openapi()["components"]["schemas"]["MonitoringMetric"]
    checked = yaml.safe_load((repo_root / "api/openapi.yaml").read_text())[
        "components"
    ]["schemas"]["MonitoringMetric"]
    generated = (repo_root / "gui/src/types/api.generated.ts").read_text()

    expected_required = {
        "name",
        "value",
        "unit",
        "timestamp",
        "status",
        "provenance",
        "reason",
    }
    assert set(live["required"]) == expected_required
    assert set(checked["required"]) == expected_required
    assert checked["properties"]["status"]["enum"] == [
        "observed",
        "unavailable",
        "simulated",
    ]
    assert checked["properties"]["provenance"]["enum"] == [
        "real",
        "simulated",
        "unknown",
    ]
    assert "MonitoringMetric:" in generated
    assert 'status: "observed" | "unavailable" | "simulated";' in generated
    assert 'provenance: "real" | "simulated" | "unknown";' in generated
