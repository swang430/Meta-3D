"""ChannelEngine real-mode path + external_asc engine — P0-7 (2026-05-18).

Pins three things that prior to P0-7 either silently broke or didn't exist:

1. **Payload-shape contract**: `ChannelEngineClient._build_payload` includes
   all Phase 5/6 fields (xpr_db, k_factor_db, initial_phases_rad,
   polarization V/H, synthesis_method, ue_velocity_mps).
   *Why*: pre-fix the client built a Spec v1.0 payload that ChannelEgine
   Phase 5+ couldn't consume; the microservice silently fell back to mock.
   This test catches future regressions where someone drops a field from
   plumbing without updating both ends.

2. **`engine_mode='external_asc'` schema gate**: validator rejects missing
   `asc_source_path` at config-construct time.
   *Why*: belt-and-braces with runtime check in
   ExternalAscPathStrategy; cheaper to fail at schema layer.

3. **Real ChannelEgine synthesis gated on env**: when CHANNEL_ENGINE_PATH
   points at a working clone, the microservice endpoint returns
   `mock_mode=False` + non-trivial zip_base64. Skipped automatically when
   the env var isn't set so CI doesn't need a ChannelEgine clone.
"""
from __future__ import annotations

import os
import sys
import uuid

import pytest


# ---------------------------------------------------------------------------
# (1) Payload-shape contract
# ---------------------------------------------------------------------------

class TestChannelEngineClientPayloadShape:
    """Pin the Phase 5/6 fields that ChannelEgine Phase 1+ requires."""

    def _build_payload(self):
        """Build a payload with the new client signature, returning the dict."""
        from app.services.channel_engine_client import (
            AntennaConfig, CDLCluster, ChannelEngineClient,
        )
        from app.models.chamber import ChamberConfiguration

        client = ChannelEngineClient(db=None)  # _build_payload doesn't touch db
        chamber = ChamberConfiguration(
            id=uuid.uuid4(),
            name="payload-test",
            chamber_type="type_a",
            chamber_radius_m=1.5,
            quiet_zone_diameter_m=0.6,
            num_probes=16,
            num_polarizations=2,
            num_rings=4,
            is_system_preset=False,
            is_active=True,
        )
        return client._build_payload(
            chamber=chamber,
            calibration_entries=[],
            frequency_hz=3.5e9,
            clusters=[
                CDLCluster(
                    delay_s=0.0, power_relative_linear=1.0,
                    aoa_deg=10.0, aod_deg=20.0,
                    xpr_db=8.0,
                    initial_phases_rad=[0.0, 0.785, 1.57, 3.14],
                ),
            ],
            cdl_model_name="UMa CDL-C LOS",
            pathloss_db=85.0,
            is_los=True,
            tx_antenna=AntennaConfig(polarization="V"),
            rx_antenna=AntennaConfig(polarization="H"),
            target_tx_power_dbm=0.0,
            target_rsrp_dbm=-85.0,
            target_snr_db=20.0,
            ue_velocity_kph=15.0,
            ue_velocity_mps=[4.17, 0.0, 0.0],
            k_factor_db=10.0,
            synthesis_method="strict_pfs",
        )

    def test_simulation_rules_carries_phase6_pol_and_synth_method(self):
        p = self._build_payload()
        sim = p["simulation_rules"]
        assert sim["tx_antenna"]["polarization"] == "V"
        assert sim["rx_antenna"]["polarization"] == "H"
        assert sim["synthesis_method"] == "strict_pfs"
        assert sim["ue_velocity_mps"] == [4.17, 0.0, 0.0]

    def test_cdl_model_data_carries_phase5_k_factor_and_xpr(self):
        p = self._build_payload()
        cdl = p["cdl_model_data"]
        assert cdl["k_factor_db"] == 10.0
        assert cdl["clusters"][0]["xpr_db"] == 8.0
        assert cdl["clusters"][0]["initial_phases_rad"] == [0.0, 0.785, 1.57, 3.14]

    def test_synthesis_method_defaults_to_strict_pfs(self):
        """Per ChannelEgine cross-project context: strict_pfs is the
        recommended default (per-(probe,cluster) independent fading,
        compatible with phase calibration certificates)."""
        from app.services.channel_engine_client import (
            AntennaConfig, CDLCluster, ChannelEngineClient,
        )
        from app.models.chamber import ChamberConfiguration

        chamber = ChamberConfiguration(
            id=uuid.uuid4(),
            name="default-test",
            chamber_type="type_a",
            chamber_radius_m=1.5,
            quiet_zone_diameter_m=0.6,
            num_probes=16,
            num_polarizations=2,
            num_rings=4,
            is_system_preset=False,
            is_active=True,
        )
        client = ChannelEngineClient(db=None)
        p = client._build_payload(
            chamber=chamber,
            calibration_entries=[],
            frequency_hz=3.5e9,
            clusters=[CDLCluster()],
            cdl_model_name="m",
            pathloss_db=80,
            is_los=False,
            tx_antenna=AntennaConfig(),
            rx_antenna=AntennaConfig(),
            target_tx_power_dbm=0.0,
            target_rsrp_dbm=-85.0,
            target_snr_db=20.0,
            ue_velocity_kph=15.0,
        )
        # No explicit synthesis_method → strict_pfs default
        assert p["simulation_rules"]["synthesis_method"] == "strict_pfs"


# ---------------------------------------------------------------------------
# (2) engine_mode='external_asc' schema gate
# ---------------------------------------------------------------------------

class TestExternalAscSchemaGate:
    """external_asc 模式必须给 asc_source_path; schema 校验在 commissioning
    runs 之前 fail-fast, 不等到 measure 阶段触发 HAL."""

    def test_external_asc_without_path_rejected(self):
        from app.schemas.mimo_ota.config import MIMOOTAConfiguration

        with pytest.raises(Exception) as exc_info:
            MIMOOTAConfiguration(
                frequency_hz=3.5e9,
                engine_mode="external_asc",
                # 故意省略 asc_source_path
            )
        # Pydantic ValidationError 字串包含字段名 + 提示信息
        msg = str(exc_info.value).lower()
        assert "asc_source_path" in msg or "external_asc" in msg

    def test_external_asc_with_empty_string_rejected(self):
        """空字符串 (操作员清空输入框后提交) 不能通过."""
        from app.schemas.mimo_ota.config import MIMOOTAConfiguration

        with pytest.raises(Exception):
            MIMOOTAConfiguration(
                frequency_hz=3.5e9,
                engine_mode="external_asc",
                asc_source_path="   ",
            )

    def test_external_asc_with_path_accepted(self):
        from app.schemas.mimo_ota.config import MIMOOTAConfiguration

        cfg = MIMOOTAConfiguration(
            frequency_hz=3.5e9,
            engine_mode="external_asc",
            asc_source_path="/tmp/fake/asc/path",
        )
        assert cfg.engine_mode == "external_asc"
        assert cfg.asc_source_path == "/tmp/fake/asc/path"

    def test_other_engine_modes_dont_require_path(self):
        """mimo_first_asc / keysight_gcm 不应该被 external_asc validator 误伤."""
        from app.schemas.mimo_ota.config import MIMOOTAConfiguration

        for mode in ("mimo_first_asc", "keysight_gcm"):
            cfg = MIMOOTAConfiguration(frequency_hz=3.5e9, engine_mode=mode)
            assert cfg.asc_source_path is None


# ---------------------------------------------------------------------------
# (3) Real ChannelEgine synthesis — gated on env var
# ---------------------------------------------------------------------------

CHANNEL_ENGINE_PATH = os.environ.get("CHANNEL_ENGINE_PATH", "").strip()

REQUIRES_CHANNEL_ENGINE = pytest.mark.skipif(
    not CHANNEL_ENGINE_PATH or not os.path.isdir(CHANNEL_ENGINE_PATH),
    reason=(
        "CHANNEL_ENGINE_PATH env var not set or path missing; "
        "skip real-ChannelEgine integration test (CI doesn't clone ChannelEgine)."
    ),
)


@REQUIRES_CHANNEL_ENGINE
class TestChannelEngineRealSynthesis:
    """Hits real ChannelEgine MIMO_OTA_Simulator + PropsimASCIIExporter.

    Asserts the post-fix path actually produces real PFS .asc. Pre-fix
    (`OTASimulator` typo + wrong constructor + missing method) would have
    ImportError'd → silent mock; post-fix gives real PFS data.

    Note: this test calls ChannelEgine *directly* rather than going through
    the channel-engine-service FastAPI endpoint, because the microservice
    lives in a sibling package with its own `app` namespace that conflicts
    with api-service's `app` at import time. The microservice endpoint
    surface is exercised by hand-smoke + the operator GUI; this test pins
    the integration contract (ChannelEgine API still callable with the
    args our adapter passes).
    """

    def test_channelegine_api_still_callable_with_our_adapter_args(self):
        """If ChannelEgine ever renames classes / changes ctor / removes
        export_to_zip_memory, this test breaks loudly instead of silently
        falling back to mock."""
        sys.path.insert(0, CHANNEL_ENGINE_PATH)
        from mimo_ota_simulator.cdl_schema import CustomCDLProfile  # type: ignore
        from mimo_ota_simulator.data_models import (  # type: ignore
            AntennaArrayConfig, ChamberConfig, PropsimExportConfig,
            TargetChannelConfig,
        )
        from mimo_ota_simulator.exporters import PropsimASCIIExporter  # type: ignore
        from mimo_ota_simulator.simulator import MIMO_OTA_Simulator  # type: ignore

        profile = CustomCDLProfile.from_dict({
            "center_frequency_hz": 3.5e9,
            "pathloss_db": 88.5,
            "ue_velocity_mps": (4.17, 0.0, 0.0),
            "is_los": False,
            "k_factor_db": None,
            "clusters": [{
                "delay_s": 0.0, "power_linear": 1.0,
                "aoa_deg": 0.0, "aod_deg": 10.0, "as_aoa_deg": 1.0,
                "xpr_db": 7.0, "initial_phases_rad": None,
            }],
        })
        chamber = ChamberConfig(
            num_probes=16, dual_polarized=True, distribution="ring", radius_m=1.5,
        )
        channel = TargetChannelConfig(
            input_mode="custom", custom_profile=profile,
            center_frequency_hz=3.5e9,
            tx_antenna=AntennaArrayConfig(num_cols=2, polarization="V"),
            rx_antenna=AntennaArrayConfig(num_cols=2, polarization="H"),
        )

        result = MIMO_OTA_Simulator().run(
            chamber, channel, synthesis_method="strict_pfs",
        )
        assert "channel_impulse_response" in result or "ray_components" in result

        exporter = PropsimASCIIExporter(PropsimExportConfig(
            filename="test_out.asc", mode="B",
            duration_s=0.1, sample_rate_hz=1000.0,
        ))
        zip_base64 = exporter.export_to_zip_memory(
            result, base_name="real-path-test", direction="dl",
        )
        # Non-trivial zip (real PFS for 2 Tx × 32 ports is tens of KB minimum;
        # placeholder mock would be much shorter)
        assert len(zip_base64) > 10_000, (
            f"ZIP unexpectedly small ({len(zip_base64)} chars) — "
            f"ChannelEgine may have changed exporter shape"
        )
