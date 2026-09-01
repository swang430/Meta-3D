"""P2-64: a diagnostic BaseStation mock is scoped by one adapter manifest."""

from __future__ import annotations

import pytest

from app.hal.base_station import MockBaseStation, RadioTechnology
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

