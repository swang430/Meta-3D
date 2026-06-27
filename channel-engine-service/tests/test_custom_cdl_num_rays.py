"""P2-15 Codex P2 #170: num_rays 接收端 schema 声明 — client 传的不被 Pydantic 丢。

client (api-service) 把 custom CDL 簇 num_rays 发到本微服务; 此前接收 CDLCluster model 无
该字段 → Pydantic 当 extra key 丢 → 真合成静默落默认。本测试钉住接收 schema 显式声明
num_rays (不丢) + 默认 20 + gt0。adapter→ChannelEgine 端到端转发 (line 292) 由真合成覆盖。
"""
import pytest
from pydantic import ValidationError

from app.models.hardware_pipeline_models import CDLCluster


def test_model_accepts_num_rays():
    """接收 schema 声明 num_rays → client 传的保留 (不被 Pydantic 当 extra 丢)。"""
    c = CDLCluster.model_validate({
        "delay_s": 0.0, "power_relative_linear": 1.0, "aoa_deg": 30.0, "num_rays": 12})
    assert c.num_rays == 12


def test_model_num_rays_default_20():
    c = CDLCluster.model_validate({
        "delay_s": 0.0, "power_relative_linear": 1.0, "aoa_deg": 0.0})
    assert c.num_rays == 20      # 38.901 默认


def test_model_num_rays_must_be_positive():
    with pytest.raises(ValidationError):
        CDLCluster.model_validate({
            "delay_s": 0.0, "power_relative_linear": 1.0, "aoa_deg": 0.0, "num_rays": 0})
