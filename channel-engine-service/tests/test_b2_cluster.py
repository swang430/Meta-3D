"""PR-5 — B-2 聚类端点 cluster_b2_native (合成 RT smoke, P2-14)。

需 CHANNEL_ENGINE_PATH 指向 ChannelEgine clone (含 PR-3/4: path_decision + b2_tap_params)。
RT 射线为合成 mock (真实 RT 数据需 RT-Release / 现场)。.tap 字节生成现场, 本测试到参数表层。
"""
import os
import pytest
from fastapi.testclient import TestClient

if not os.environ.get("CHANNEL_ENGINE_PATH"):
    pytest.skip("CHANNEL_ENGINE_PATH 未设, 跳过 B-2 端点测试", allow_module_level=True)

from app.main import app

client = TestClient(app)


def _rays(phase=False):
    rays = [
        {"delay_s": 0.0, "power_linear": 1.0, "aoa_deg": 30.0, "aod_deg": 10.0},
        {"delay_s": 1e-9, "power_linear": 0.8, "aoa_deg": 31.0, "aod_deg": 10.5},
        {"delay_s": 2e-9, "power_linear": 0.6, "aoa_deg": 29.0, "aod_deg": 9.5},
    ]
    if phase:
        for i, r in enumerate(rays):
            r["phase_rad"] = 0.5 + 0.3 * i
    return rays


def _post(test_class, phase=False, velocity=(10.0, 0.0, 0.0), fc=3.5e9, f64=None):
    body = {"rt_rays": _rays(phase), "ue_velocity_mps": list(velocity),
            "center_frequency_hz": fc, "test_class": test_class}
    if f64:
        body["f64_profile"] = f64
    return client.post("/api/v1/cluster_b2_native", json=body)


def test_throughput_native_returns_tap_params():
    """throughput + native 可表示 → B2_parametric + per-tap 参数表 + 现场说明。"""
    resp = _post("throughput_psd")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["target_path"] == "B2_parametric"
    assert len(data["tap_params"]) >= 1
    t = data["tap_params"][0]
    assert {"delay_s", "power_linear", "doppler_kind", "doppler_centroid_hz",
            "as_zoa_deg"}.issubset(t.keys())          # 含仰角展宽
    assert "Channel Studio" in data["note"]            # .tap 字节现场


def test_isac_low_centroid_is_b1_no_tap():
    """ISAC + phase_rad + 低 f_D,max → B1_baked (烘焙路, 无 tap)。"""
    resp = _post("isac_sensing", phase=True, f64={"large_centroid_thresh_hz": 1e6})
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["target_path"] == "B1_baked"
    assert data["tap_params"] == []


def test_isac_missing_phase_rad_422():
    """ISAC 缺 phase_rad → §6 fail-loud → 422 (不静默)。"""
    resp = _post("isac_sensing", phase=False)
    assert resp.status_code == 422
    assert "phase_rad" in resp.text


def test_escalate_large_centroid_no_gcm_422():
    """ISAC/beam 大质心 + 无 GCM → ESCALATE → 422 (绝不静默回落)。"""
    resp = _post("beam_tracking", phase=True,
                 f64={"large_centroid_thresh_hz": 100.0, "has_gcm": False})
    assert resp.status_code == 422
    assert "ESCALATE" in resp.text


def test_unknown_test_class_pydantic_422():
    """未知 test_class → Pydantic Literal 拒 → 422。"""
    resp = client.post("/api/v1/cluster_b2_native", json={
        "rt_rays": _rays(), "ue_velocity_mps": [10.0, 0.0, 0.0],
        "center_frequency_hz": 3.5e9, "test_class": "bad-class"})
    assert resp.status_code == 422


def test_empty_rays_422():
    resp = client.post("/api/v1/cluster_b2_native", json={
        "rt_rays": [], "ue_velocity_mps": [10.0, 0.0, 0.0],
        "center_frequency_hz": 3.5e9, "test_class": "throughput_psd"})
    assert resp.status_code == 422   # min_length=1
