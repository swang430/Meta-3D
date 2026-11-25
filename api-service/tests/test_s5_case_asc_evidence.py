import hashlib
import json

import pytest
from app.services.channel_generation.conducted_asc import playback_evidence


@pytest.fixture
def bundle(tmp_path):
    header = dict(cir_count=2, taps=1, carrier_hz=2565000000., rate_hz=4.,
                  flags=["Route_Open", "CIRUpdateRate_Unlocked", "CarrierFrequency_Unlocked"],
                  delay_resolution=5, sample_density=2.)
    data = ("***** Header *****\n2 CIRs\n1 Taps/CIR\n2565000000 Carrier_Frequency\n" +
            "\n".join(header["flags"]) + "\n5 Delay_Resolution\n2 Sample_Density\n4 CIR_Update_Rate\n"
            "***** Tap data *****\nDelay Re Im\n0 1 0\n1 0 1\n").encode()
    links = []
    for tx in range(4):
        for rx in range(2):
            name = f"A_TX{tx}_RX{rx}_H.asc"
            (tmp_path / name).write_bytes(data)
            links.append(dict(file=name, tx=tx, rx=rx, sha256=hashlib.sha256(data).hexdigest()))
    raw = json.dumps(dict(mode="conducted", direction="downlink", header=header, links=links)).encode()
    (tmp_path / "manifest.json").write_bytes(raw)
    return tmp_path, raw, links, data


def test_declared_span_is_not_device_position(bundle):
    tmp_path, raw, links, data = bundle
    evidence = playback_evidence(tmp_path)
    assert evidence["manifest_sha256"] == hashlib.sha256(raw).hexdigest()
    assert evidence["first_to_last_response_s"] == .25
    assert evidence["last_asc_response_index"] == 1
    assert evidence["last_observed_device_response"] is None
    assert evidence["source_frame_times_s"] is None
    (tmp_path / links[-1]["file"]).write_bytes(data[:-6])
    with pytest.raises(ValueError):
        playback_evidence(tmp_path)

@pytest.mark.asyncio
async def test_pinned_bundle_requires_mock_and_exact_digest(bundle):
    from app.hal import MockChannelEmulator
    from app.services.channel_generation.external_asc_strategy import ExternalAscPathStrategy

    directory, raw, _, _ = bundle
    digest = hashlib.sha256(raw).hexdigest()
    unsupported = ExternalAscPathStrategy(object(), None, [], str(directory), manifest_sha256=digest)
    with pytest.raises(ValueError, match="不能作为"):
        await unsupported.generate_and_load({}, {})

    driver = MockChannelEmulator("simulated", {})
    wrong = ExternalAscPathStrategy(driver, None, [], str(directory), manifest_sha256="0" * 64)
    with pytest.raises(ValueError, match="摘要不一致"):
        await wrong.generate_and_load({}, {})


@pytest.mark.asyncio
@pytest.mark.parametrize("cancel", [False, True])
async def test_simulated_cursor_stops_at_last_response_or_cancellation(monkeypatch, cancel):
    import asyncio
    from types import SimpleNamespace
    from unittest.mock import Mock
    from app.services.channel_generation.external_asc_strategy import ExternalAscPathStrategy

    driver = Mock()
    driver.simulated_playback_elapsed.side_effect = [0.25, 2.]
    strategy = ExternalAscPathStrategy(driver, None, [], ".")
    strategy.playback_evidence = dict(rate_hz=4, last_asc_response_index=4, first_to_last_response_s=1.)
    row = SimpleNamespace(id=None, status="running", hardware_status={"asc_playback_evidence": {"device_load_accepted": None}})
    context = SimpleNamespace(db=Mock(), test_execution=row)

    def write(values, synchronize_session):
        row.hardware_status = next(iter(values.values()))
        return 1

    context.db.query.return_value.filter.return_value.update.side_effect = write

    async def advance(_seconds):
        if cancel:
            row.status = "cancelled"

    monkeypatch.setattr(asyncio, "sleep", advance)
    if cancel:
        with pytest.raises(ValueError, match="已停止"):
            await strategy._record_simulated_pass(context.db, context.test_execution)
    else:
        await strategy._record_simulated_pass(context.db, context.test_execution)
    record = row.hardware_status["asc_playback_evidence"]
    assert record["simulated_response_index"] == (1 if cancel else 4)
    assert record["simulated_last_response_reached"] is (not cancel)
    assert record["device_load_accepted"] is None


@pytest.mark.asyncio
async def test_cancel_after_file_verification_prevents_mock_load(bundle):
    from unittest.mock import AsyncMock
    from app.hal import MockChannelEmulator
    from app.services.channel_generation.external_asc_strategy import ExternalAscPathStrategy

    directory, raw, _, _ = bundle
    driver = MockChannelEmulator("simulated", {})
    driver.load_channel = AsyncMock()

    def cancelled():
        raise ValueError("用例已停止")

    strategy = ExternalAscPathStrategy(driver, None, [], str(directory),
                                       manifest_sha256=hashlib.sha256(raw).hexdigest(),
                                       check_execution_running=cancelled)
    with pytest.raises(ValueError, match="已停止"):
        await strategy.generate_and_load({}, {})
    driver.load_channel.assert_not_awaited()


def test_pinned_bundle_rejects_full_bypass_before_execution():
    from pydantic import ValidationError
    from app.schemas.mimo_ota.config import MIMOOTAConfiguration

    with pytest.raises(ValidationError, match="全程直通"):
        MIMOOTAConfiguration.model_validate(dict(
            engine_mode="external_asc", asc_source_path="/example", asc_manifest_sha256="0" * 64,
            f64_bypass_mode=3, f64_fade_after_attach=False))
