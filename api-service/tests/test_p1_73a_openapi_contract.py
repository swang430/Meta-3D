"""P1-73A Task 5：基站通用字段的 API 镜像保持同向。"""

from pathlib import Path

import yaml

from app.main import app
from app.schemas.mimo_ota.config import MIMOOTAConfiguration


REPO_ROOT = Path(__file__).resolve().parents[2]
GENERIC_MODE_DESCRIPTION = (
    "Vendor-neutral base-station configuration mode; inherit is diagnostic-only."
)


def test_configuration_schema_keeps_only_one_generic_writer_and_deprecated_reader():
    properties = MIMOOTAConfiguration.model_json_schema()["properties"]

    assert properties["base_station_config_mode"].get("deprecated") is not True
    assert properties["uxm_config_mode"]["deprecated"] is True
    assert "base_station_dl_power_dbm_per_bw" not in properties
    assert properties["uxm_dl_power_dbm_per_bw"].get("deprecated") is not True


def test_live_and_checked_openapi_describe_generic_commissioning_mode_identically():
    live = app.openapi()["components"]["schemas"]["CreateSessionRequest"]
    checked = yaml.safe_load((REPO_ROOT / "api/openapi.yaml").read_text())[
        "components"
    ]["schemas"]["CreateSessionRequest"]

    for schema in (live, checked):
        properties = schema["properties"]
        assert properties["base_station_config_mode"]["description"] == (
            GENERIC_MODE_DESCRIPTION
        )
        assert "uxm_config_mode" not in properties
        assert "base_station_dl_power_dbm_per_bw" not in properties


def test_checked_openapi_keeps_rat_aware_channel_identity_fields():
    schemas = yaml.safe_load((REPO_ROOT / "api/openapi.yaml").read_text())[
        "components"
    ]["schemas"]

    for schema_name in ("AddChannelModelRequest", "SCDCreateRequest"):
        properties = schemas[schema_name]["properties"]
        assert properties["radio_technology"]["enum"] == ["nr5g", "lte"]
        assert properties["channel_kind"]["enum"] == [
            "nr_arfcn",
            "lte_dl_earfcn",
        ]
