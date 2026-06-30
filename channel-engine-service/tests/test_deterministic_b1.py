"""P2-16 S3-2b — 确定性相位 B-1 烘焙端点 synthesize_deterministic_b1 (合成 RT)。

接线悬空的 F5 phase_continuous: 确定性相位 RT 射线 (每条带 phase_rad) → §6 判决确认 B1_baked
(大质心 → GCM/ESCALATE 422) → phase_continuous_fit (subray_sum ACP) → bake_b1_annotated →
per-(Tx,Probe) .asc zip。需 CHANNEL_ENGINE_PATH。RT 射线为合成 mock (真实 RT 数据 S5 现场)。
"""
import base64
import io
import os
import zipfile

import pytest
from fastapi.testclient import TestClient

if not os.environ.get("CHANNEL_ENGINE_PATH"):
    pytest.skip("CHANNEL_ENGINE_PATH 未设, 跳过确定性 B-1 端点测试", allow_module_level=True)

from app.main import app  # noqa: E402

client = TestClient(app)


def _rays(phase=True):
    rays = [
        {"delay_s": 0.0, "power_linear": 1.0, "aoa_deg": 30.0, "aod_deg": 10.0},
        {"delay_s": 1e-9, "power_linear": 0.8, "aoa_deg": 31.0, "aod_deg": 10.5},
        {"delay_s": 2e-9, "power_linear": 0.6, "aoa_deg": 29.0, "aod_deg": 9.5},
    ]
    if phase:
        for i, r in enumerate(rays):
            r["phase_rad"] = 0.5 + 0.3 * i
    return rays


def _body(rays=None, velocity=(10.0, 0.0, 0.0), fc=3.5e9, f64=None, test_class="isac_sensing"):
    body = {
        "chamber_config": {"num_probes": 8, "radius_m": 1.0, "dual_polarized": False},
        "simulation_rules": {"center_frequency_hz": fc, "ue_velocity_mps": list(velocity)},
        "rt_rays": _rays() if rays is None else rays,
        "test_class": test_class,
        "pathloss_db": 80.0,
    }
    if f64:
        body["f64_profile"] = f64
    return body


def _post(**kw):
    return client.post("/api/v1/synthesize_deterministic_b1", json=_body(**kw))


def test_deterministic_b1_happy_path():
    """低质心确定性相位 (isac + phase_rad + 低速) → 200, B1_baked + subray_sum .asc zip。"""
    resp = _post(f64={"large_centroid_thresh_hz": 1e6})
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["target_path"] == "B1_baked"
    assert data["clustering_algo"] == "phase_continuous"
    assert data["num_subray_clusters"] >= 1
    assert data["total_files"] > 0
    raw = base64.b64decode(data["asc_zip_base64"])
    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        ascs = [n for n in zf.namelist() if n.endswith(".asc")]
    assert len(ascs) == data["total_files"]      # zip 真含 total_files 个 .asc


def test_deterministic_b1_missing_phase_rad_422():
    """射线缺 phase_rad → §6 判决 422 (确定性类要求每子径确定性相位)。"""
    assert _post(rays=_rays(phase=False)).status_code == 422


def test_deterministic_b1_escalate_422():
    """大质心 + 无 GCM → ESCALATE → 422 fail-loud (绝不静默回落 B1_baked)。"""
    resp = _post(f64={"large_centroid_thresh_hz": 100.0, "has_gcm": False})
    assert resp.status_code == 422, resp.text
    assert "ESCALATE" in resp.json()["detail"]


def test_deterministic_b1_gcm_rejected_422():
    """大质心 + 有 GCM → GCM_native → 422 (本端点只出 .asc; GCM 需 F64 .smu 现场)。"""
    resp = _post(f64={"large_centroid_thresh_hz": 100.0, "has_gcm": True})
    assert resp.status_code == 422, resp.text
    assert "GCM" in resp.json()["detail"]


def test_deterministic_b1_rejects_statistical_class():
    """统计类 (throughput_psd) → schema 422 (走 B-2 参数化端点 cluster_b2_*)。"""
    assert _post(test_class="throughput_psd").status_code == 422
