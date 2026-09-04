"""P2-62：第三种 Channel Emulator adapter 的参数化接入认证。"""

from pathlib import Path

from app.hal.channel_emulator import ChannelEmulatorDriver
from app.hal.channel_emulator_manifest import CHANNEL_EMULATOR_OPERATIONS
from tests.channel_emulator_certification_kit import (
    CERTFAKE_CE_MANIFEST,
    CERTFAKE_CE_PROFILE,
    CertFakeChannelEmulatorDriver,
    CertFakeChannelEmulatorProfile,
)


def test_certfake_ce_five_piece_registration_contract_is_complete():
    parsed = CertFakeChannelEmulatorProfile.model_validate(CERTFAKE_CE_PROFILE)

    assert parsed.adapter == "certfake_ce"
    assert CERTFAKE_CE_MANIFEST.adapter_id == "certfake_ce"
    assert {item.operation for item in CERTFAKE_CE_MANIFEST.operations} == set(
        CHANNEL_EMULATOR_OPERATIONS
    )
    assert all(
        item.source_reference and "test fixture" in item.source_reference
        for item in CERTFAKE_CE_MANIFEST.operations
    )
    assert CertFakeChannelEmulatorDriver.adapter_manifest is CERTFAKE_CE_MANIFEST


def test_certfake_ce_manifest_and_driver_cover_the_same_operations():
    declared = {
        item.operation
        for item in CERTFAKE_CE_MANIFEST.operations
        if item.support == "implemented"
    }
    implemented = {
        operation
        for operation in CHANNEL_EMULATOR_OPERATIONS
        if getattr(CertFakeChannelEmulatorDriver, operation)
        is not getattr(ChannelEmulatorDriver, operation)
    }

    assert implemented == declared


def test_certfake_ce_never_leaks_into_production_code():
    app_root = Path(__file__).resolve().parents[1] / "app"
    offenders = [
        path.relative_to(app_root).as_posix()
        for path in app_root.rglob("*.py")
        if "certfake_ce" in path.read_text(encoding="utf-8").casefold()
    ]

    assert offenders == []
