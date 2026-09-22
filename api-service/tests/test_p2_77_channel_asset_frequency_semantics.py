"""P2-77：vendor .smu 工程默认频率与执行期有界调频语义。"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock
from pathlib import Path

import pytest

from app.hal.channel_emulator import (
    CenterFrequencyApplicationEvidence,
    CenterFrequencyGroupApplication,
    CenterFrequencyRange,
)
from app.hal.channel_emulator_execution_plan import (
    resolve_channel_emulator_execution_plan,
)
from app.hal.channel_emulator_manifest import (
    CHANNEL_EMULATOR_ASSET_SOURCE_TYPES,
    CHANNEL_EMULATOR_MANIFEST_V2_OPERATIONS,
    ChannelEmulatorAssetSourceCapability,
    ChannelEmulatorManifest,
    ChannelEmulatorLoadModeCapability,
    ChannelEmulatorOperationCapability,
)
from app.hal.propsim_f64 import RealPropsimF64Driver
from app.services.mimo_ota.executors.measure import (
    _resolve_runtime_bounded_vendor_frequency,
)
from app.services.mimo_ota.frequency_consistency import (
    CenterFrequencyBandwidthObservation,
    ChannelFrequencyIdentity,
    check_frequency_consistency,
)
from app.services.channel_emulator_certification import (
    _has_certifiable_channel_emulator_frequency_evidence,
)


def _legacy_v3_manifest() -> ChannelEmulatorManifest:
    """A historical v3 manifest must retain its original operation vocabulary."""

    return ChannelEmulatorManifest(
        schema_version=3,
        adapter_id="legacy_v3_ce",
        model_name="Legacy v3 CE",
        vendor="fixture",
        load_modes=(
            ChannelEmulatorLoadModeCapability(
                mode="native_model",
                support="implemented",
                reason="historical native load",
            ),
        ),
        operations=tuple(
            ChannelEmulatorOperationCapability(
                operation=operation,
                support="not_implemented",
                reason="historical frozen vocabulary",
            )
            for operation in CHANNEL_EMULATOR_MANIFEST_V2_OPERATIONS
        ),
        asset_sources=tuple(
            ChannelEmulatorAssetSourceCapability(
                source_type=source_type,
                support="not_implemented",
                reason="historical frozen vocabulary",
            )
            for source_type in CHANNEL_EMULATOR_ASSET_SOURCE_TYPES
        ),
    )


def test_f64_manifest_freezes_bounded_center_frequency_capability() -> None:
    manifest = RealPropsimF64Driver.adapter_manifest

    assert manifest.schema_version == 4
    assert manifest.implements("set_center_frequency_bounded") is True

    plan = resolve_channel_emulator_execution_plan(
        manifest=manifest,
        driver_source="hal",
        requested_load_mode="native_model",
        binding_digest="binding-digest",
    )
    assert plan.schema_version == 3
    assert plan.planned("set_center_frequency_bounded") is True


def test_legacy_manifest_and_plan_do_not_acquire_new_frequency_capability() -> None:
    manifest = _legacy_v3_manifest()

    assert manifest.schema_version == 3
    assert "set_center_frequency_bounded" not in {
        item.operation for item in manifest.operations
    }

    plan = resolve_channel_emulator_execution_plan(
        manifest=manifest,
        driver_source="hal",
        requested_load_mode="native_model",
        binding_digest="binding-digest",
    )
    assert plan.schema_version == 2
    with pytest.raises(ValueError, match="rebuild|重建"):
        plan.planned("set_center_frequency_bounded")


def _frequency_driver(
    *,
    representatives: list[int],
    limits: dict[int, str],
    readbacks: dict[int, str] | None = None,
) -> tuple[RealPropsimF64Driver, MagicMock]:
    driver = RealPropsimF64Driver("p2-77-f64", {})
    driver._group_repr_channels = representatives
    visa = MagicMock()
    writes: list[str] = []

    async def query(command: str, **_kwargs):
        if command == "SYST:ERR?":
            return '0,"No error"'
        if command.startswith("CALC:FILT:CENT:LIM?"):
            channel = int(command.rsplit(" ", 1)[1])
            return limits[channel]
        if command.startswith("CALC:FILT:CENT:CH?"):
            channel = int(command.rsplit(" ", 1)[1])
            return (readbacks or {})[channel]
        raise AssertionError(f"unexpected query: {command}")

    async def write(command: str, **_kwargs):
        writes.append(command)

    driver._visa_resource = visa
    driver._query = query  # type: ignore[method-assign]
    driver._write = write  # type: ignore[method-assign]
    visa.frequency_writes = writes
    return driver, visa


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("350,6000", ((350.0, 6000.0),)),
        ("350,1000;2000,6000", ((350.0, 1000.0), (2000.0, 6000.0))),
    ],
)
def test_f64_parses_manual_single_and_multiple_center_frequency_ranges(
    raw: str,
    expected: tuple[tuple[float, float], ...],
) -> None:
    ranges = RealPropsimF64Driver.parse_center_frequency_limits(raw)
    assert tuple((item.lower_mhz, item.upper_mhz) for item in ranges) == expected


@pytest.mark.parametrize("raw", ["", "350", "350,1000;", "nan,6000", "6000,350"])
def test_f64_rejects_unknown_or_malformed_center_frequency_limits(raw: str) -> None:
    with pytest.raises(ValueError):
        RealPropsimF64Driver.parse_center_frequency_limits(raw)


@pytest.mark.parametrize(
    ("group_number", "representative_channel"),
    [(True, 1), (1.5, 1), (1, False), (1, 2.5)],
)
def test_center_frequency_group_identifiers_must_be_positive_integers(
    group_number,
    representative_channel,
) -> None:
    with pytest.raises(ValueError, match="positive integers"):
        CenterFrequencyGroupApplication(
            group_number=group_number,
            representative_channel=representative_channel,
            allowed_ranges=(CenterFrequencyRange(350.0, 6000.0),),
            applied_mhz=None,
        )


async def test_bounded_frequency_preflights_every_group_before_any_write() -> None:
    driver, visa = _frequency_driver(
        representatives=[1, 9],
        limits={1: "350,6000", 9: "350,1000"},
    )

    evidence = await driver.set_center_frequency_bounded(1842.5)

    assert isinstance(evidence, CenterFrequencyApplicationEvidence)
    assert evidence.confirmed is False
    assert "9" in evidence.reason
    assert visa.frequency_writes == []
    assert driver._center_freq_programmed is False


async def test_bounded_frequency_rejects_malformed_group_limits_before_any_write() -> None:
    driver, visa = _frequency_driver(
        representatives=[1, 9],
        limits={1: "350,6000", 9: ""},
    )

    evidence = await driver.set_center_frequency_bounded(1842.5)

    assert evidence.confirmed is False
    assert "9" in evidence.reason
    assert visa.frequency_writes == []


async def test_bounded_frequency_requires_exact_readback_from_every_group() -> None:
    driver, visa = _frequency_driver(
        representatives=[1, 9],
        limits={1: "350,6000", 9: "350,6000"},
        readbacks={1: "1842.5", 9: "1842.4"},
    )

    evidence = await driver.set_center_frequency_bounded(1842.5)

    assert evidence.confirmed is False
    assert "9" in evidence.reason
    assert len(visa.frequency_writes) == 2
    assert driver._center_freq_programmed is False


async def test_bounded_frequency_confirms_every_group_before_updating_cache() -> None:
    driver, visa = _frequency_driver(
        representatives=[1, 9],
        limits={1: "350,1000;1800,2000", 9: "350,6000"},
        readbacks={1: "1842.5", 9: "1842.5"},
    )

    evidence = await driver.set_center_frequency_bounded(1842.5)

    assert evidence.confirmed is True
    assert [item.representative_channel for item in evidence.groups] == [1, 9]
    assert [item.applied_mhz for item in evidence.groups] == [1842.5, 1842.5]
    assert visa.frequency_writes == [
        "CALC:FILT:CENT:CH 1,1842.5",
        "CALC:FILT:CENT:CH 9,1842.5",
    ]
    assert driver._center_freq_programmed is True
    assert driver._center_freq_mhz == 1842.5


def _vendor_resolution(*, project_default_mhz: float = 2565.0):
    return SimpleNamespace(
        asset=SimpleNamespace(source_type="vendor_file"),
        project_default_frequency_identity=SimpleNamespace(
            center_freq_mhz=project_default_mhz,
            bandwidth_mhz=20.0,
            describe=lambda: f"project default {project_default_mhz:g} MHz",
        ),
        declared_bandwidth_mhz=20.0,
    )


def _confirmed_application(requested_mhz: float = 1960.0):
    return CenterFrequencyApplicationEvidence(
        requested_mhz=requested_mhz,
        groups=(
            CenterFrequencyGroupApplication(
                group_number=1,
                representative_channel=1,
                allowed_ranges=(CenterFrequencyRange(350.0, 6000.0),),
                applied_mhz=requested_mhz,
            ),
        ),
        confirmed=True,
        reason="all groups read back exactly",
    )


def test_vendor_project_default_is_audit_only_with_confirmed_runtime_evidence() -> None:
    plan = resolve_channel_emulator_execution_plan(
        manifest=RealPropsimF64Driver.adapter_manifest,
        driver_source="hal",
        requested_load_mode="native_model",
        binding_digest="binding-digest",
    )
    emulator = SimpleNamespace(
        get_center_frequency_application_evidence=lambda: _confirmed_application()
    )

    resolution = _resolve_runtime_bounded_vendor_frequency(
        resolved_asset=_vendor_resolution(),
        plan=plan,
        emulator=emulator,
        requested_mhz=1960.0,
    )

    assert resolution.runtime_bounded is True
    assert resolution.failure_reason is None
    assert resolution.declared_bandwidth_mhz == 20.0
    assert resolution.project_default_description == "project default 2565 MHz"
    assert resolution.application_payload["requested_mhz"] == 1960.0
    assert resolution.application_payload["groups"][0]["applied_mhz"] == 1960.0


@pytest.mark.parametrize(
    ("evidence", "reason"),
    [
        (None, "missing"),
        (
            CenterFrequencyApplicationEvidence(
                requested_mhz=1960.0,
                groups=(
                    CenterFrequencyGroupApplication(
                        group_number=1,
                        representative_channel=1,
                        allowed_ranges=(CenterFrequencyRange(350.0, 6000.0),),
                        applied_mhz=None,
                    ),
                ),
                confirmed=False,
                reason="readback missing",
            ),
            "unconfirmed",
        ),
        (_confirmed_application(1950.0), "requested"),
    ],
)
def test_bounded_vendor_frequency_evidence_fails_closed(evidence, reason) -> None:
    plan = resolve_channel_emulator_execution_plan(
        manifest=RealPropsimF64Driver.adapter_manifest,
        driver_source="hal",
        requested_load_mode="native_model",
        binding_digest="binding-digest",
    )
    emulator = SimpleNamespace(
        get_center_frequency_application_evidence=lambda: evidence
    )

    resolution = _resolve_runtime_bounded_vendor_frequency(
        resolved_asset=_vendor_resolution(),
        plan=plan,
        emulator=emulator,
        requested_mhz=1960.0,
    )

    assert resolution.runtime_bounded is True
    assert reason in resolution.failure_reason


def test_legacy_plan_keeps_vendor_project_frequency_as_fixed_identity() -> None:
    legacy_plan = resolve_channel_emulator_execution_plan(
        manifest=_legacy_v3_manifest(),
        driver_source="hal",
        requested_load_mode="native_model",
        binding_digest="binding-digest",
    )

    resolution = _resolve_runtime_bounded_vendor_frequency(
        resolved_asset=_vendor_resolution(),
        plan=legacy_plan,
        emulator=SimpleNamespace(),
        requested_mhz=1960.0,
    )

    assert resolution.runtime_bounded is False
    assert resolution.failure_reason is None
    assert resolution.application_payload is None


def test_runtime_center_and_asset_bandwidth_form_a_fully_verified_observation() -> None:
    expected = ChannelFrequencyIdentity.from_lte_earfcn(
        band="B2", dl_earfcn=900, bandwidth_mhz=20.0
    )
    actual = CenterFrequencyBandwidthObservation(
        center_frequency_hz=expected.center_frequency_hz,
        bandwidth_mhz=20.0,
        source="bounded application readback + frozen asset bandwidth",
    )

    result = check_frequency_consistency(expected, {"F64": actual})

    assert result.consistent is True
    assert result.fully_verified is True


def test_runtime_observation_rejects_asset_bandwidth_drift() -> None:
    expected = ChannelFrequencyIdentity.from_lte_earfcn(
        band="B2", dl_earfcn=900, bandwidth_mhz=20.0
    )
    actual = CenterFrequencyBandwidthObservation(
        center_frequency_hz=expected.center_frequency_hz,
        bandwidth_mhz=10.0,
        source="bounded application readback + frozen asset bandwidth",
    )

    result = check_frequency_consistency(expected, {"F64": actual})

    assert result.consistent is False
    assert "BW 10" in result.failure_reason()


def test_certification_accepts_only_complete_bounded_frequency_evidence() -> None:
    application = _center_frequency_application_payload_for_test(
        _confirmed_application()
    )
    frequency = {
        "fully_verified": True,
        "channel_emulator_evidence": {
            "schema_version": 3,
            "adapter_id": "propsim_f64",
            "instrument_id": "f64-1",
            "measurement_attempt_id": "attempt-1",
            "center_readback_mhz": 1960.0,
            "bandwidth_source": "frozen_vendor_project_declared",
            "fully_verified": True,
            "project_default_frequency": "LTE B41 default",
            "bounded_center_frequency_application": application,
        },
    }

    assert _has_certifiable_channel_emulator_frequency_evidence(
        frequency,
        current_adapter_id="propsim_f64",
        instrument_id="f64-1",
        measurement_attempt_id="attempt-1",
    )

    frequency["channel_emulator_evidence"] = {
        **frequency["channel_emulator_evidence"],
        "bounded_center_frequency_application": {
            **application,
            "requested_mhz": 1950.0,
        },
    }
    assert not _has_certifiable_channel_emulator_frequency_evidence(
        frequency,
        current_adapter_id="propsim_f64",
        instrument_id="f64-1",
        measurement_attempt_id="attempt-1",
    )


def _center_frequency_application_payload_for_test(evidence):
    return {
        "requested_mhz": evidence.requested_mhz,
        "confirmed": evidence.confirmed,
        "reason": evidence.reason,
        "groups": [
            {
                "group_number": item.group_number,
                "representative_channel": item.representative_channel,
                "allowed_ranges_mhz": [
                    [allowed.lower_mhz, allowed.upper_mhz]
                    for allowed in item.allowed_ranges
                ],
                "applied_mhz": item.applied_mhz,
            }
            for item in evidence.groups
        ],
    }


def test_channel_asset_frequency_semantics_are_mirrored_in_contract_and_gui() -> None:
    from app.main import app

    expected = (
        "vendor_file=工程默认中心频率；其他来源=执行物理身份。"
        "vendor_file 的本次执行频率仅由冻结 adapter 能力、仪器运行时范围和逐组回读裁决。"
    )
    live = app.openapi()["components"]["schemas"]
    for schema_name in (
        "ChannelAssetCreate",
        "ChannelAssetUpdate",
        "ChannelAssetResponse",
    ):
        assert (
            live[schema_name]["properties"]["center_frequency_hz"]["description"]
            == expected
        )

    repo = Path(__file__).resolve().parents[2]
    checked = (repo / "api/openapi.yaml").read_text(encoding="utf-8")
    generated = (repo / "gui/src/types/api.generated.ts").read_text(
        encoding="utf-8"
    )
    workbench = (
        repo / "gui/src/features/ChannelWorkbench/ChannelWorkbench.tsx"
    ).read_text(encoding="utf-8")
    form = (
        repo / "gui/src/features/ChannelWorkbench/ChannelAssetForm.tsx"
    ).read_text(encoding="utf-8")
    testcase_form = (
        repo / "gui/src/components/TestCaseConfig/MIMOOTAConfigForm.tsx"
    ).read_text(encoding="utf-8")

    assert expected in checked
    assert expected in generated
    assert "工程默认中心频率" in workbench
    assert "工程默认中心频率" in form
    assert "冻结 adapter 能力 + 仪表运行时范围 + 逐组回读" in testcase_form
