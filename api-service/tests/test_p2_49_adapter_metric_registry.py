from __future__ import annotations

from tests.base_station_mock_factory import registered_mock_base_station

import pytest

from app.hal.base_station import MockBaseStation
from app.hal.cmw500_base_station import RealCmw500Driver
from app.hal.uxm_base_station import RealUxmDriver
from app.hal.uxm_command_profiles import (
    Uxm5GNRTestAppProfile,
    UxmLteNrIratProfile,
)


def _by_key(registry):
    return {metric.key: metric for metric in registry.metrics}


def test_cmw500_metric_registry_reuses_static_authoritative_manifest_without_io(
    monkeypatch,
):
    driver = RealCmw500Driver("cmw", {"ip_address": "192.0.2.10"})
    monkeypatch.setattr(
        driver,
        "_query",
        lambda *_args, **_kwargs: pytest.fail("registry resolution must not query"),
    )

    registry = driver.resolve_metric_registry()

    assert registry.adapter_id == "cmw500"
    assert registry.profile_id == "cmw500_lte"
    assert tuple(_by_key(registry)) == (
        "dl_bler_percent",
        "dl_throughput_mbps",
    )
    assert all(item.evidence == "authoritative" for item in registry.metrics)


def test_uxm_irat_registry_exposes_only_existing_profile_commands_without_io(
    monkeypatch,
):
    driver = RealUxmDriver(
        "uxm-irat",
        {"ip_address": "192.0.2.11", "uxm_profile": "irat"},
    )
    assert isinstance(driver._cmds, UxmLteNrIratProfile)
    monkeypatch.setattr(
        driver,
        "_query",
        lambda *_args, **_kwargs: pytest.fail("registry resolution must not query"),
    )

    registry = driver.resolve_metric_registry()
    metrics = _by_key(registry)

    assert registry.profile_id == "lte_nr_irat"
    assert tuple(metrics) == (
        "cqi_index",
        "dl_bler_ratio",
        "dl_throughput_current_mbps",
        "dl_throughput_mbps",
        "ri_index",
        "rsrp_raw",
        "sinr_raw",
        "ul_bler_ratio",
        "ul_throughput_current_mbps",
        "ul_throughput_mbps",
    )
    assert metrics["dl_bler_ratio"].unit == "ratio"
    assert metrics["ul_bler_ratio"].unit == "ratio"
    assert metrics["cqi_index"].unit == "index"
    assert metrics["ri_index"].unit == "index"
    assert metrics["rsrp_raw"].unit == "raw"
    assert metrics["sinr_raw"].unit == "raw"
    assert metrics["rsrp_raw"].evidence == "diagnostic_only"
    assert metrics["sinr_raw"].evidence == "diagnostic_only"
    assert metrics["dl_throughput_mbps"].scopes == ("pcell", "all_cells")
    assert metrics["ul_throughput_mbps"].scopes == ("pcell", "all_cells")
    assert all(
        (
            "5G_NR_Test_Application_SCPI_Reference.zip!"
            "5G_NR_Test_Application_SCPI_Reference.html ::"
        )
        in item.source_reference
        for item in registry.metrics
        if item.evidence == "authoritative"
    )


def test_uxm_nr_profile_does_not_inherit_irat_throughput_or_bler_commands(
    monkeypatch,
):
    driver = RealUxmDriver(
        "uxm-nr",
        {"ip_address": "192.0.2.11", "uxm_profile": "5g_nr"},
    )
    assert isinstance(driver._cmds, Uxm5GNRTestAppProfile)
    monkeypatch.setattr(
        driver,
        "_query",
        lambda *_args, **_kwargs: pytest.fail("registry resolution must not query"),
    )

    registry = driver.resolve_metric_registry()

    assert registry.profile_id == "nr5g_test"
    assert tuple(_by_key(registry)) == ("cqi_index", "ri_index")


def test_uxm_registry_tracks_live_profile_switch_and_changes_digest():
    driver = RealUxmDriver(
        "uxm",
        {"ip_address": "192.0.2.11", "uxm_profile": "irat"},
    )
    irat = driver.resolve_metric_registry()

    driver._cmds = Uxm5GNRTestAppProfile()
    nr = driver.resolve_metric_registry()

    assert irat.profile_id == "lte_nr_irat"
    assert nr.profile_id == "nr5g_test"
    assert irat.digest != nr.digest


def test_uxm_unknown_profile_fails_loud_instead_of_guessing_capabilities():
    driver = RealUxmDriver("uxm", {"ip_address": "192.0.2.11"})
    driver._cmds.PROFILE_NAME = "Unregistered App"

    with pytest.raises(ValueError, match="profile"):
        driver.resolve_metric_registry()


@pytest.mark.parametrize(
    "config,expected_profile,expected_keys",
    [
        (
            {"model": "CMW500"},
            "mock_cmw500",
            ("dl_bler_percent", "dl_throughput_mbps"),
        ),
        (
            {"model": "UXM 5G E7515B", "uxm_profile": "irat"},
            "mock_uxm",
            ("cqi_index", "ri_index"),
        ),
    ],
)
def test_mock_registry_projects_manifest_and_downgrades_all_metrics(
    config,
    expected_profile,
    expected_keys,
):
    registry = registered_mock_base_station("mock", config).resolve_metric_registry()

    assert registry.profile_id == expected_profile
    assert tuple(_by_key(registry)) == expected_keys
    assert all(item.evidence == "diagnostic_only" for item in registry.metrics)
