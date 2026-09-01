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
        nr_layers = schemas["NrMacTestProfileV1"]["properties"]["mimo_layers"]
        assert nr_layers["type"] == "integer"
        assert nr_layers["enum"] == [1, 2, 4]
        lte_layers = schemas["LteRmcMacTestProfileV1"]["properties"]["mimo_layers"]
        assert lte_layers["type"] == "integer"
        assert lte_layers["const"] == 2
        requirements = schemas["BaseStationExecutionRequirements"]
        mac_profile = requirements["properties"]["mac_profile"]
        alternatives = mac_profile.get("anyOf") or mac_profile.get("oneOf")
        assert {tuple(item.items()) for item in alternatives} == {
            (("$ref", "#/components/schemas/FrozenMacTestProfile"),),
            (("type", "null"),),
        }


def test_nr_profile_openapi_publishes_the_audited_uxm_value_domain():
    for schemas in (app.openapi()["components"]["schemas"], _checked()["components"]["schemas"]):
        fields = schemas["NrMacTestProfileV1"]["properties"]
        assert fields["mcs"]["type"] == "integer"
        assert fields["mcs"]["minimum"] == 0
        assert fields["mcs"]["maximum"] == 28
        assert fields["enable_amc"]["const"] is False
        assert fields["tdd_pattern"]["pattern"] == r"^D*S?U*$"
        assert fields["tdd_pattern"]["minLength"] == 1
        assert fields["tdd_period"]["enum"] == [
            "0.5MS", "0.625MS", "1MS", "1.25MS", "2MS",
            "2.5MS", "3MS", "4MS", "5MS", "10MS",
        ]
        assert fields["harq_max_trans"]["enum"] == [
            1, 2, 3, 4, 5, 6, 7, 8, 10, 12, 16, 20, 24, 28,
        ]
        assert fields["harq_processes"]["enum"] == [
            1, 2, 4, 6, 8, 10, 12, 13, 14, 16, 32,
        ]
        assert fields["subcarrier_spacing_khz"]["enum"] == [15, 30, 60, 120]
        assert fields["csi_rs_ports"]["enum"] == [1, 2, 4, 8, 12, 16, 24, 32]


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


def test_adapter_mac_application_evidence_is_mirrored_everywhere():
    live = app.openapi()["components"]["schemas"]
    checked = _checked()["components"]["schemas"]

    for schemas in (live, checked):
        capability = schemas["BaseStationMacProfileCapability"]
        evidence = capability["properties"]["application_evidence"]
        assert evidence["type"] == "string"
        assert evidence["enum"] == [
            "authoritative_readback",
            "command_error_queue",
        ]
        assert "application_evidence" in capability["required"]

    generated = (REPO_ROOT / "gui/src/types/api.generated.ts").read_text()
    handwritten = (
        REPO_ROOT / "gui/src/types/baseStationManifest.ts"
    ).read_text()
    for source in (generated, handwritten):
        normalized = source.replace("'", '"')
        assert (
            'application_evidence: "authoritative_readback" '
            '| "command_error_queue"'
        ) in normalized
