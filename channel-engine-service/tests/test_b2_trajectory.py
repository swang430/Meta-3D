"""P2-16 S3-2a — F4 多快照轨迹端点 cluster_b2_trajectory (合成 RT)。

接线悬空的 native_fit_trajectory 进生产: 多快照 RT → 逐快照 native-fit + 跨快照跟踪 →
逐快照 per-tap 参数表 + 簇生灭标注。需 CHANNEL_ENGINE_PATH。RT 射线为合成 mock (真实 RT
数据需 RT-Release / 现场, S5)。端点级镜像 ChannelEgine test_spatiotemporal_tracking 的
持续/生/灭模式。
"""
import os

import numpy as np
import pytest
from fastapi.testclient import TestClient

if not os.environ.get("CHANNEL_ENGINE_PATH"):
    pytest.skip("CHANNEL_ENGINE_PATH 未设, 跳过 F4 轨迹端点测试", allow_module_level=True)

from app.main import app  # noqa: E402

client = TestClient(app)

TRAJ = {"skeleton_rate_hz": 100.0, "delta_d_geo_m": 1.0, "route_len_m": 100.0}


def _grp(aoa, n=6, delay=0.0):
    """一簇射线 (aoa 附近小幅展开), 镜像 ChannelEgine F4 测试 _grp。float() 保 JSON 可序列化。"""
    return [{"delay_s": float(delay), "power_linear": 1.0,
             "aoa_deg": float(aoa + o), "aod_deg": float(-aoa)}
            for o in np.linspace(-2, 2, n)]


def _post(snapshots, test_class="throughput_psd", velocity=(40.0, 0.0, 0.0)):
    return client.post("/api/v1/cluster_b2_trajectory", json={
        "snapshots": snapshots,
        "ue_velocity_mps": list(velocity),
        "center_frequency_hz": 3.5e9,
        "test_class": test_class,
        **TRAJ,
    })


def test_trajectory_per_snapshot_taps_and_tracking():
    """两快照同簇小幅漂移 (30°→32°) → 200, 逐快照 tap 参数表 + 同 cluster_id 跟踪 (持续簇)。"""
    resp = _post([_grp(30), _grp(32)])
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["num_snapshots"] == 2
    assert data["num_tracked_clusters"] >= 1
    assert len(data["snapshots"]) == 2
    for snap in data["snapshots"]:
        assert len(snap["tap_params"]) >= 1          # 逐快照 per-tap 参数表
        assert len(snap["clusters"]) >= 1
    # 持续簇: 两快照共享 cluster_id (跨快照身份一致)
    ids0 = {c["cluster_id"] for c in data["snapshots"][0]["clusters"]}
    ids1 = {c["cluster_id"] for c in data["snapshots"][1]["clusters"]}
    assert ids0 == ids1
    assert all(c["power_ramp"] == "stable"
               for s in data["snapshots"] for c in s["clusters"])


def test_trajectory_birth_tracked():
    """快照1 多一个新簇 (90°@200ns) → birth 标注 (birth_index=1, ramp=birth)。"""
    resp = _post([_grp(30), _grp(30) + _grp(90, delay=200e-9)])
    assert resp.status_code == 200, resp.text
    data = resp.json()
    born = [c for c in data["snapshots"][1]["clusters"] if c["power_ramp"] == "birth"]
    assert born and all(c["birth_index"] == 1 for c in born)
    ids0 = {c["cluster_id"] for c in data["snapshots"][0]["clusters"]}
    ids1 = {c["cluster_id"] for c in data["snapshots"][1]["clusters"]}
    assert len(ids1) == len(ids0) + 1                # 多一个跟踪簇


def test_trajectory_tap_param_has_doppler_fields():
    """逐快照 tap 参数行含多普勒质心/展宽/仰角展宽 (B-2 native 参数表完整性)。"""
    resp = _post([_grp(30), _grp(31)])
    assert resp.status_code == 200, resp.text
    tap = resp.json()["snapshots"][0]["tap_params"][0]
    assert {"delay_s", "power_linear", "doppler_kind", "doppler_centroid_hz",
            "doppler_spread_hz", "as_zoa_deg", "native_fit_residual"}.issubset(tap.keys())


def test_trajectory_rejects_single_snapshot():
    """单快照 (min_length=2) → schema 422 (单快照用 cluster_b2_native)。"""
    assert _post([_grp(30)]).status_code == 422


def test_trajectory_rejects_deterministic_class():
    """确定性类 (isac_sensing) → schema 422 (走 F5 phase_continuous 烘焙路, 非本端点)。"""
    assert _post([_grp(30), _grp(32)], test_class="isac_sensing").status_code == 422


def test_trajectory_gates_non_representable_snapshot():
    """Codex #177 P1: 某快照 native 不可表示 (残差 > rho_thresh) → §6 判决门 422,
    不当成功 B-2 资产返回 tap。镜像 ChannelEgine test_path_decision 的 throughput→B1_baked:
    5 射线同时延 + aoa 0/45/90/135/180 (doppler 多模) + tap_budget=1 不分裂 → resid 大。"""
    bad = [{"delay_s": 0.0, "power_linear": 1.0, "aoa_deg": float(a), "aod_deg": 0.0}
           for a in (0, 45, 90, 135, 180)]
    resp = client.post("/api/v1/cluster_b2_trajectory", json={
        "snapshots": [_grp(30), bad],        # 快照0 可表示, 快照1 不可表示 → 门拦
        "ue_velocity_mps": [40.0, 0.0, 0.0],
        "center_frequency_hz": 3.5e9,
        "test_class": "throughput_psd",
        "f64_profile": {"tap_budget": 1, "rho_thresh": 0.01},
        **TRAJ,
    })
    assert resp.status_code == 422, resp.text
    assert "B1_baked" in resp.json()["detail"]    # 判决路由到 B-1 (非可表示 B-2) → fail-loud
