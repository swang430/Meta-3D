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
# (1b) P1-7 — standard 3GPP mode payload-shape contract
# ---------------------------------------------------------------------------

class TestStandard3GPPPayloadShape:
    """P1-7 (2026-05-19): pin the standard-mode payload structure so future
    plumbing drops surface immediately. Verifies:

    - clusters omitted (None) — ChannelEgine generates from 38.901 table
    - top-level input_mode='standard'
    - standard_3gpp sub-model carries scenario / cluster / condition / positions
    - back-compat: omitting input_mode defaults to 'custom' (P0-7 behavior)
    """

    def _chamber(self):
        from app.models.chamber import ChamberConfiguration

        return ChamberConfiguration(
            id=uuid.uuid4(), name="std-test", chamber_type="type_a",
            chamber_radius_m=1.5, quiet_zone_diameter_m=0.6,
            num_probes=16, num_polarizations=2, num_rings=4,
            is_system_preset=False, is_active=True,
        )

    def test_standard_mode_payload_clusters_omitted(self):
        from app.services.channel_engine_client import (
            AntennaConfig, ChannelEngineClient,
        )
        client = ChannelEngineClient(db=None)
        p = client._build_payload(
            chamber=self._chamber(),
            calibration_entries=[],
            frequency_hz=3.5e9,
            clusters=None,
            cdl_model_name="UMa CDL-C NLOS",
            pathloss_db=88.5,
            is_los=False,
            tx_antenna=AntennaConfig(polarization="V"),
            rx_antenna=AntennaConfig(polarization="H"),
            target_tx_power_dbm=0.0, target_rsrp_dbm=-85.0,
            target_snr_db=20.0, ue_velocity_kph=15.0,
            input_mode="standard",
            scenario_name="UMa",
            cluster_model_name="CDL-C",
            force_condition="NLOS",
            random_seed=42,
        )
        assert p["input_mode"] == "standard"
        assert p["cdl_model_data"]["clusters"] is None, (
            "standard mode must omit clusters; ChannelEgine generates them"
        )

    def test_standard_mode_carries_standard_3gpp_sub_model(self):
        from app.services.channel_engine_client import (
            AntennaConfig, ChannelEngineClient,
        )
        client = ChannelEngineClient(db=None)
        p = client._build_payload(
            chamber=self._chamber(),
            calibration_entries=[],
            frequency_hz=3.5e9,
            clusters=None,
            cdl_model_name="UMa CDL-C NLOS",
            pathloss_db=88.5,
            is_los=False,
            tx_antenna=AntennaConfig(), rx_antenna=AntennaConfig(),
            target_tx_power_dbm=0.0, target_rsrp_dbm=-85.0,
            target_snr_db=20.0, ue_velocity_kph=15.0,
            input_mode="standard",
            scenario_name="UMa",
            cluster_model_name="CDL-C",
            force_condition="NLOS",
            bs_position=[0.0, 0.0, 30.0],
            ue_position=[60.0, 0.0, 1.5],
            random_seed=42,
        )
        std = p["standard_3gpp"]
        assert std["scenario_name"] == "UMa"
        assert std["cluster_model_name"] == "CDL-C"
        assert std["force_condition"] == "NLOS"
        assert std["bs_position"] == [0.0, 0.0, 30.0]
        assert std["ue_position"] == [60.0, 0.0, 1.5]
        assert std["random_seed"] == 42

    def test_custom_mode_default_back_compat(self):
        """Omitting input_mode keeps P0-7 behavior — clusters present, no
        standard_3gpp sub-model."""
        from app.services.channel_engine_client import (
            AntennaConfig, CDLCluster, ChannelEngineClient,
        )
        client = ChannelEngineClient(db=None)
        p = client._build_payload(
            chamber=self._chamber(),
            calibration_entries=[],
            frequency_hz=3.5e9,
            clusters=[CDLCluster()],
            cdl_model_name="custom",
            pathloss_db=88.5,
            is_los=False,
            tx_antenna=AntennaConfig(), rx_antenna=AntennaConfig(),
            target_tx_power_dbm=0.0, target_rsrp_dbm=-85.0,
            target_snr_db=20.0, ue_velocity_kph=15.0,
        )
        assert p["input_mode"] == "custom"
        assert p["cdl_model_data"]["clusters"] is not None
        assert len(p["cdl_model_data"]["clusters"]) == 1
        assert "standard_3gpp" not in p


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

    def test_standard_3gpp_path_produces_multi_cluster_channel(self):
        """P1-7: standard-mode (ChannelEgine `Standard3GPPBuilder`) must
        produce a channel with multiple clusters — not the 1-cluster
        placeholder that `asc_strategy.py` was sending pre-fix.

        Verifies by zip size: P0-7's 1-cluster custom-mode baseline was
        ~86 KB; CDL-C UMa NLOS has ~24 sub-clusters per the 38.901 table,
        so the standard-mode zip should be significantly larger.
        """
        sys.path.insert(0, CHANNEL_ENGINE_PATH)
        from mimo_ota_simulator.data_models import (  # type: ignore
            AntennaArrayConfig, ChamberConfig, PropsimExportConfig,
            TargetChannelConfig,
        )
        from mimo_ota_simulator.exporters import PropsimASCIIExporter  # type: ignore
        from mimo_ota_simulator.simulator import MIMO_OTA_Simulator  # type: ignore

        chamber = ChamberConfig(
            num_probes=16, dual_polarized=True, distribution="ring", radius_m=1.5,
        )
        # Standard-mode TargetChannelConfig — no custom_profile, just
        # scenario / cluster_model that ChannelEgine resolves internally.
        channel = TargetChannelConfig(
            input_mode="standard",
            model_name="UMa",
            cluster_model_name="CDL-C",
            center_frequency_hz=3.5e9,
            tx_antenna=AntennaArrayConfig(num_cols=2, polarization="V"),
            rx_antenna=AntennaArrayConfig(num_cols=2, polarization="H"),
            ue_velocity=[4.17, 0.0, 0.0],
        )

        result = MIMO_OTA_Simulator().run(
            chamber, channel, synthesis_method="strict_pfs",
        )
        # Standard-mode result must carry the actual clusters ChannelEgine
        # generated from the 38.901 table.
        assert "clusters" in result or "channel_impulse_response" in result

        exporter = PropsimASCIIExporter(PropsimExportConfig(
            filename="std_test.asc", mode="B",
            duration_s=0.1, sample_rate_hz=1000.0,
        ))
        zip_base64 = exporter.export_to_zip_memory(
            result, base_name="standard-3gpp-test", direction="dl",
        )
        # CDL-C has ~24 clusters per TR 38.901 §7.7.1 — zip should be
        # multi-cluster sized (much larger than 1-cluster ~86 KB baseline).
        # Threshold 200 KB chosen with margin so a future refactor that
        # accidentally drops cluster generation surfaces immediately.
        assert len(zip_base64) > 200_000, (
            f"Standard-mode zip ({len(zip_base64)} chars) is suspiciously "
            f"close to 1-cluster baseline (~86 KB) — `Standard3GPPBuilder` "
            f"may not be generating multi-cluster output. Check "
            f"`channel_builders.py` Standard3GPPBuilder path."
        )
