"""P2-64: a diagnostic BaseStation mock is scoped by one adapter manifest."""

from __future__ import annotations

import pytest

import app.services.instrument_hal_service as hal_service_module
from app.hal.base_station import (
    BaseStationMeasurementWindowRequest,
    MockBaseStation,
    RadioTechnology,
    ThroughputMetrics,
    resolve_base_station_execution_plan,
)
from app.hal.cmw500_base_station import RealCmw500Driver
from app.hal.uxm_base_station import RealUxmDriver


UXM_MODEL_NAME = "UXM 5G E7515B"
CMW_MODEL_NAME = "CMW500"


def _mock(model_name: str, manifest):
    return MockBaseStation(
        "mock-base-station",
        {"model": model_name},
        adapter_manifest=manifest,
    )


def test_mock_requires_registered_adapter_manifest():
    with pytest.raises(ValueError, match="registered adapter manifest"):
        MockBaseStation("mock-base-station", {"model": UXM_MODEL_NAME})


def test_mock_rejects_model_manifest_drift():
    with pytest.raises(ValueError, match="does not match"):
        _mock(CMW_MODEL_NAME, RealUxmDriver.adapter_manifest)


@pytest.mark.parametrize(
    ("manifest", "model_name", "expected_rat"),
    (
        (RealUxmDriver.adapter_manifest, UXM_MODEL_NAME, RadioTechnology.NR5G),
        (RealCmw500Driver.adapter_manifest, CMW_MODEL_NAME, RadioTechnology.LTE),
    ),
)
def test_mock_identity_and_rat_are_manifest_scoped(
    manifest,
    model_name: str,
    expected_rat: RadioTechnology,
):
    driver = _mock(model_name, manifest)

    assert driver.adapter_id == manifest.adapter_id
    assert driver.adapter_manifest is manifest
    assert driver.get_supported_technologies() == [expected_rat]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("manifest", "model_name"),
    (
        (RealUxmDriver.adapter_manifest, UXM_MODEL_NAME),
        (RealCmw500Driver.adapter_manifest, CMW_MODEL_NAME),
    ),
)
async def test_mock_capability_projection_contains_only_manifest_truth(
    manifest,
    model_name: str,
):
    driver = _mock(model_name, manifest)

    capabilities = await driver.get_capabilities()

    assert [capability.name for capability in capabilities] == list(manifest.rats)
    assert all(capability.supported is True for capability in capabilities)
    for capability in capabilities:
        parameters = capability.parameters
        assert parameters is not None
        assert parameters["adapter_id"] == manifest.adapter_id
        assert parameters["operations"] == list(manifest.operations)
        assert parameters["config_fields"] == {
            field.field: {
                "support": field.support,
                "readback": field.readback,
            }
            for field in manifest.config_fields
        }
        expected_measurement = (
            None
            if manifest.measurement is None
            else {
                "cardinality": manifest.measurement.cardinality,
                "scopes": list(manifest.measurement.scopes),
                "lifecycle": manifest.measurement.lifecycle,
                "metrics": [metric.key for metric in manifest.measurement.metrics],
            }
        )
        assert parameters["measurement"] == expected_measurement
        assert "frequency_range" not in parameters
        assert "max_bandwidth_mhz" not in parameters


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("manifest", "model_name", "expected_rat", "forbidden_prefix"),
    (
        (RealUxmDriver.adapter_manifest, UXM_MODEL_NAME, "nr5g", "lte"),
        (RealCmw500Driver.adapter_manifest, CMW_MODEL_NAME, "lte", "nr"),
    ),
)
async def test_mock_ue_diagnostics_do_not_claim_a_foreign_rat(
    manifest,
    model_name: str,
    expected_rat: str,
    forbidden_prefix: str,
):
    driver = _mock(model_name, manifest)

    ue_info = await driver.get_ue_info()
    capability = await driver.query_ue_capability()

    assert ue_info["radio_technology"] == expected_rat
    assert capability["radio_technology"] == expected_rat
    assert capability["max_dl_layers"] == driver._mimo_layers
    assert capability["source"] == "mock"
    for value in (
        ue_info.get("ue_category"),
        *(capability.get("supported_bands") or ()),
        *(capability.get("ca_combinations") or ()),
    ):
        assert not str(value).lower().startswith(forbidden_prefix)


@pytest.mark.asyncio
async def test_mock_optional_operations_fail_closed_when_manifest_omits_them():
    driver = _mock(CMW_MODEL_NAME, RealCmw500Driver.adapter_manifest)

    assert await driver.set_downlink_power(-46.0) is False
    assert await driver.reconfigure_rrc(mimo_layers=2) is False
    assert await driver.add_secondary_cell(1, {"frequency_mhz": 3600.0}) is False
    assert not hasattr(driver, "_scells")


@pytest.mark.parametrize(
    ("manifest", "model_name"),
    (
        (RealUxmDriver.adapter_manifest, UXM_MODEL_NAME),
        (RealCmw500Driver.adapter_manifest, CMW_MODEL_NAME),
    ),
)
def test_mock_metric_registry_is_a_diagnostic_projection_of_manifest(
    monkeypatch,
    manifest,
    model_name: str,
):
    def _must_not_instantiate(*_args, **_kwargs):
        raise AssertionError("mock registry must not instantiate a real driver")

    monkeypatch.setattr(RealUxmDriver, "__init__", _must_not_instantiate)
    monkeypatch.setattr(RealCmw500Driver, "__init__", _must_not_instantiate)

    registry = _mock(model_name, manifest).resolve_metric_registry()

    assert registry.adapter_id == manifest.adapter_id
    assert registry.profile_id == f"mock_{manifest.adapter_id}"
    assert [metric.key for metric in registry.metrics] == sorted(
        metric.key for metric in manifest.measurement.metrics
    )
    assert all(metric.evidence == "diagnostic_only" for metric in registry.metrics)


@pytest.mark.parametrize(
    ("manifest", "model_name", "expected"),
    (
        (
            RealUxmDriver.adapter_manifest,
            UXM_MODEL_NAME,
            {
                "scell": False,
                "mac_throughput": False,
                "rrc_reconfiguration": False,
                "input_level_control": True,
            },
        ),
        (
            RealCmw500Driver.adapter_manifest,
            CMW_MODEL_NAME,
            {
                "scell": False,
                "mac_throughput": True,
                "rrc_reconfiguration": False,
                "input_level_control": False,
            },
        ),
    ),
)
def test_mock_execution_plan_is_scoped_by_manifest_operations(
    manifest,
    model_name: str,
    expected: dict[str, bool],
):
    driver = _mock(model_name, manifest)

    plan = resolve_base_station_execution_plan(
        driver,
        manifest=driver.adapter_manifest,
    )

    assert {
        name: getattr(plan, name).planned
        for name in (
            "scell",
            "mac_throughput",
            "rrc_reconfiguration",
            "input_level_control",
        )
    } == expected


@pytest.mark.asyncio
async def test_mock_rejects_window_shape_that_drifted_from_manifest():
    driver = _mock(CMW_MODEL_NAME, RealCmw500Driver.adapter_manifest)
    request = BaseStationMeasurementWindowRequest(
        schema_version=1,
        scope="pcell",
        lifecycle="clear_read_only",
        cardinality="requested",
        requested_window_count=2,
        expected_window_count=2,
        window_index=0,
    )

    with pytest.raises(ValueError, match="frozen manifest"):
        await driver.measure_base_station_window(0.0, request=request)


@pytest.mark.asyncio
async def test_mock_window_keeps_manifest_metrics_simulated_and_untrusted():
    manifest = RealUxmDriver.adapter_manifest
    driver = _mock(UXM_MODEL_NAME, manifest)
    await driver.start_signaling()
    request = BaseStationMeasurementWindowRequest(
        schema_version=1,
        scope="pcell",
        lifecycle=manifest.measurement.lifecycle,
        cardinality=manifest.measurement.cardinality,
        requested_window_count=1,
        expected_window_count=1,
        window_index=0,
    )

    window = await driver.measure_base_station_window(0.0, request=request)

    assert window.trust is not None
    assert window.trust.simulated is True
    assert window.confirmed is False
    assert window.metrics.throughput_scope == ThroughputMetrics.SCOPE_SIMULATED
    assert not any(window.metrics.kpi_valid.values())
    assert [item.key for item in window.metric_observations] == sorted(
        metric.key for metric in manifest.measurement.metrics
    )
    assert all(item.simulated is True for item in window.metric_observations)


@pytest.mark.asyncio
async def test_mock_route_is_enabled_only_by_manifest_operation():
    frozen_route = {
        "resolution": {
            "profile": {
                "lte_2x2_internal_route": {
                    "pcc_bb_board": "SUA1",
                    "rx_connector": "RF1C",
                    "rx_converter": "RX1",
                    "tx1_connector": "RF1O",
                    "tx1_converter": "TX1",
                    "tx2_connector": "RF3C",
                    "tx2_converter": "TX2",
                }
            }
        }
    }

    uxm_receipt = await _mock(
        UXM_MODEL_NAME,
        RealUxmDriver.adapter_manifest,
    ).apply_route(frozen_route)
    cmw_receipt = await _mock(
        CMW_MODEL_NAME,
        RealCmw500Driver.adapter_manifest,
    ).apply_route(frozen_route)

    assert [field.status for field in uxm_receipt.fields] == ["not_applicable"]
    assert {field.field for field in cmw_receipt.fields} == {
        "pcc_bb_board",
        "rx_connector",
        "rx_converter",
        "tx1_connector",
        "tx1_converter",
        "tx2_connector",
        "tx2_converter",
    }
    assert all(field.status == "unknown" for field in cmw_receipt.fields)
    assert cmw_receipt.simulated is True


@pytest.mark.parametrize(
    ("model_name", "expected_adapter"),
    (
        (UXM_MODEL_NAME, "uxm"),
        (CMW_MODEL_NAME, "cmw500"),
    ),
)
def test_hal_factory_injects_selected_models_registered_manifest(
    model_name: str,
    expected_adapter: str,
):
    driver = hal_service_module._instantiate_hal_driver(
        MockBaseStation,
        category_key="baseStation",
        model_name=model_name,
        instrument_id="baseStation-mock",
        config={"model": model_name},
    )

    registration = hal_service_module.get_base_station_adapter_registration(
        model_name
    )
    assert driver.adapter_id == expected_adapter
    assert driver.adapter_manifest is registration.manifest


def test_hal_factory_rejects_unregistered_mock_model():
    with pytest.raises(KeyError, match="unknown base-station model"):
        hal_service_module._instantiate_hal_driver(
            MockBaseStation,
            category_key="baseStation",
            model_name="Unknown BaseStation",
            instrument_id="baseStation-mock",
            config={"model": "Unknown BaseStation"},
        )


def test_hal_factory_keeps_non_base_station_constructor_contract():
    calls: list[tuple[str, dict]] = []

    class _OtherDriver:
        def __init__(self, instrument_id: str, config: dict):
            calls.append((instrument_id, config))

    driver = hal_service_module._instantiate_hal_driver(
        _OtherDriver,
        category_key="signalAnalyzer",
        model_name="Example",
        instrument_id="signalAnalyzer-example",
        config={"model": "Example"},
    )

    assert isinstance(driver, _OtherDriver)
    assert calls == [("signalAnalyzer-example", {"model": "Example"})]
