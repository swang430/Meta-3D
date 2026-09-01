"""P2-54: RAT-neutral MAC profiles stay identical across API mirrors."""

from pathlib import Path

import yaml

from app.main import app


REPO_ROOT = Path(__file__).resolve().parents[2]


def _checked() -> dict:
    return yaml.safe_load((REPO_ROOT / "api/openapi.yaml").read_text())


def test_live_and_checked_openapi_publish_the_same_discriminated_profile():
    live = app.openapi()["components"]["schemas"]
    checked = _checked()["components"]["schemas"]

    for schemas in (live, checked):
        frozen = schemas["FrozenMacTestProfile"]
        profile = frozen["properties"]["profile"]
        assert profile["discriminator"] == {
            "propertyName": "kind",
            "mapping": {
                "nr_throughput": "#/components/schemas/NrMacTestProfileV1",
                "lte_rmc": "#/components/schemas/LteRmcMacTestProfileV1",
            },
        }
        assert profile["oneOf"] == [
            {"$ref": "#/components/schemas/NrMacTestProfileV1"},
            {"$ref": "#/components/schemas/LteRmcMacTestProfileV1"},
        ]
        requirements = schemas["BaseStationExecutionRequirements"]
        mac_profile = requirements["properties"]["mac_profile"]
        alternatives = mac_profile.get("anyOf") or mac_profile.get("oneOf")
        assert {tuple(item.items()) for item in alternatives} == {
            (("$ref", "#/components/schemas/FrozenMacTestProfile"),),
            (("type", "null"),),
        }


def test_checked_profiles_keep_rat_specific_fields_disjoint():
    schemas = _checked()["components"]["schemas"]
    nr = set(schemas["NrMacTestProfileV1"]["properties"])
    lte = set(schemas["LteRmcMacTestProfileV1"]["properties"])

    assert {"mcs", "tdd_pattern", "harq_processes", "csi_rs_ports"} <= nr
    assert not {"scheduling_mode", "resource_allocation", "transmission_mode"} & nr
    assert {"scheduling_mode", "resource_allocation", "transmission_mode"} <= lte
    assert not {"mcs", "tdd_pattern", "harq_processes", "csi_rs_ports"} & lte


def test_generated_and_handwritten_types_expose_both_profile_variants():
    generated = (REPO_ROOT / "gui/src/types/api.generated.ts").read_text()
    handwritten = (REPO_ROOT / "gui/src/types/api.ts").read_text()

    for source in (generated, handwritten):
        assert "NrMacTestProfileV1" in source
        assert "LteRmcMacTestProfileV1" in source
        assert "FrozenMacTestProfile" in source
