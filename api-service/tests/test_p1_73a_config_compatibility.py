"""P1-73A Task 2：基站配置模式的新旧字段只在 schema 边界兼容。"""

from __future__ import annotations

import inspect

import pytest
from pydantic import ValidationError

from app.schemas.mimo_ota.config import (
    MIMOOTAConfiguration,
    canonicalize_mimo_ota_configuration_payload,
)
from app.services.mimo_ota.executors import measure


def test_new_base_station_config_mode_is_canonical():
    payload = {"base_station_config_mode": "inherit"}

    config = MIMOOTAConfiguration.model_validate(payload)
    canonical = canonicalize_mimo_ota_configuration_payload(payload)

    assert config.base_station_config_mode == "inherit"
    assert config.uxm_config_mode is None
    assert canonical["base_station_config_mode"] == "inherit"
    assert "uxm_config_mode" not in canonical


def test_legacy_uxm_config_mode_is_read_compatible_and_preserved_for_audit():
    payload = {"uxm_config_mode": "inherit"}

    config = MIMOOTAConfiguration.model_validate(payload)
    canonical = canonicalize_mimo_ota_configuration_payload(payload)

    assert config.base_station_config_mode == "inherit"
    assert config.uxm_config_mode == "inherit"
    assert canonical["base_station_config_mode"] == "inherit"
    assert canonical["uxm_config_mode"] == "inherit"


def test_matching_new_and_legacy_modes_are_accepted():
    payload = {
        "base_station_config_mode": "dispatch",
        "uxm_config_mode": "dispatch",
    }

    canonical = canonicalize_mimo_ota_configuration_payload(payload)

    assert canonical["base_station_config_mode"] == "dispatch"
    assert canonical["uxm_config_mode"] == "dispatch"


def test_conflicting_new_and_legacy_modes_fail_loud():
    with pytest.raises(ValidationError, match="base_station_config_mode.*uxm_config_mode"):
        MIMOOTAConfiguration.model_validate(
            {
                "base_station_config_mode": "dispatch",
                "uxm_config_mode": "inherit",
            }
        )


def test_default_mode_remains_dispatch_without_persisting_a_legacy_key():
    config = MIMOOTAConfiguration.model_validate({})
    canonical = canonicalize_mimo_ota_configuration_payload({})

    assert config.base_station_config_mode == "dispatch"
    assert config.uxm_config_mode is None
    assert canonical["base_station_config_mode"] == "dispatch"
    assert "uxm_config_mode" not in canonical


def test_executor_consumes_only_the_canonical_mode_field():
    source = inspect.getsource(measure)
    assert "config.base_station_config_mode" in source
    assert "config.uxm_config_mode" not in source
