"""P2-16 S3 — 标注式 B-1 烘焙路 (routing_mode='annotated_b1') 金标准对照。

验证经 AnnotatedCDLProfile + bake_b1_annotated 的标注式烘焙路, 对 custom CDL 簇产出与
legacy CustomCDLBuilder + run() 直路【逐位一致】的 .asc —— 接线悬空 baker (设计 §1.2
断层 C) 进生产, 零回归。parity 根据 (golden test_b1_golden_vs_legacy): run() 3GPP 路 =
[seed if random_seed] + create_builder(custom).build() + synthesize_ota; bake 复刻同三步,
from_custom_profile round-trip 对标准几何无损, cluster_subrays={} 对全 baked 簇无效。custom
模式 channel.random_seed=None → 两路都不自播种, 测试前置同 seed 即可比对。

需 CHANNEL_ENGINE_PATH 指向 ChannelEgine clone (含 b1_annotated_baker)。
"""
import base64
import io
import os
import zipfile

import numpy as np
import pytest
from pydantic import ValidationError

if not os.environ.get("CHANNEL_ENGINE_PATH"):
    pytest.skip(
        "CHANNEL_ENGINE_PATH 未设, 跳过标注式 B-1 烘焙端点测试",
        allow_module_level=True,
    )

from app.api.endpoints import hardware_pipeline as hp  # noqa: E402
from app.models.hardware_pipeline_models import HardwarePipelineRequest  # noqa: E402

SEED = 42


def _request(routing_mode="legacy", method="strict_pfs"):
    """同一 custom 请求, 两路只差 routing_mode 分派 (parity 的对照基础)。"""
    return HardwarePipelineRequest.model_validate({
        "chamber_config": {"num_probes": 8, "radius_m": 1.0, "dual_polarized": False},
        "simulation_rules": {
            "center_frequency_hz": 3.5e9,
            "ue_velocity_mps": [10.0, 0.0, 0.0],
            "synthesis_method": method,
        },
        "cdl_model_data": {
            "model_name": "S3 golden",
            "pathloss_db": 80.0,
            "is_los": False,
            "clusters": [
                {"delay_s": 0.0, "power_relative_linear": 1.0,
                 "aoa_deg": 30.0, "aod_deg": 10.0, "as_aoa_deg": 5.0},
                {"delay_s": 100e-9, "power_relative_linear": 0.5,
                 "aoa_deg": 120.0, "aod_deg": 80.0, "as_aoa_deg": 8.0},
            ],
        },
        "input_mode": "custom",
        "routing_mode": routing_mode,
    })


def _zip_asc_contents(zip_base64):
    """base64 zip → 排序后的 .asc 内容列表 (按内容比对, 不依赖 zip 打包/命名细节)。"""
    raw = base64.b64decode(zip_base64)
    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        return sorted(zf.read(n) for n in zf.namelist() if n.endswith(".asc"))


def test_annotated_b1_matches_legacy_strict_pfs():
    """金标准: annotated_b1 与 legacy 对同一 custom 簇逐位一致 (strict_pfs, 生产默认法)。"""
    hp._import_simulator_class()  # 注入 sys.path + ChannelEgine 可用性 fail-fast
    req_legacy = _request(routing_mode="legacy")
    req_annotated = _request(routing_mode="annotated_b1")

    np.random.seed(SEED)
    zip_legacy, n_legacy = hp._run_real_synthesis(
        hp._import_simulator_class(), req_legacy)
    np.random.seed(SEED)
    zip_annotated, n_annotated = hp._run_annotated_bake_synthesis(req_annotated)

    assert n_legacy == n_annotated > 0
    # 防 zip 截断掩盖文件数回归 (Codex P2 in test_b1_golden_vs_legacy)
    asc_legacy = _zip_asc_contents(zip_legacy)
    asc_annotated = _zip_asc_contents(zip_annotated)
    assert len(asc_legacy) == n_legacy
    assert asc_legacy == asc_annotated   # 逐位一致 → 标注式 baker 无回归


def test_annotated_b1_matches_legacy_ray():
    """ray 合成法下两路也逐位一致 (覆盖 strict_pfs 之外的 method)。"""
    hp._import_simulator_class()
    np.random.seed(SEED)
    zip_legacy, _ = hp._run_real_synthesis(
        hp._import_simulator_class(), _request(routing_mode="legacy", method="ray"))
    np.random.seed(SEED)
    zip_annotated, _ = hp._run_annotated_bake_synthesis(
        _request(routing_mode="annotated_b1", method="ray"))
    assert _zip_asc_contents(zip_legacy) == _zip_asc_contents(zip_annotated)


def test_routing_mode_defaults_legacy():
    """routing_mode 默认 legacy (零行为变更保证)。"""
    assert _request().routing_mode == "legacy"


def test_annotated_b1_rejects_standard_mode():
    """annotated_b1 + standard → schema 拒绝 (standard 无 clusters 可装配 ACP)。"""
    with pytest.raises(ValidationError, match="annotated_b1"):
        HardwarePipelineRequest.model_validate({
            "chamber_config": {"num_probes": 8, "radius_m": 1.0},
            "simulation_rules": {"center_frequency_hz": 3.5e9},
            "cdl_model_data": {"model_name": "x", "pathloss_db": 80.0},
            "input_mode": "standard",
            "standard_3gpp": {"scenario_name": "UMa"},
            "routing_mode": "annotated_b1",
        })
