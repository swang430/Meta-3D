import pytest
from app.services.road_test.sinr_plan import Window, budget


def inputs():
    scope=dict(frame=4,receiver="RX0",plane="receiver_connector",bandwidth_hz=20e6,start_s=1,duration_s=0.1)
    return dict(scope=scope,target_sinr_db=10,additional_source="新增噪声源",correlation_real=0,
                method="equivalent_noise",injection_plane="receiver_connector",
                signal=dict(scope=scope,dbm=-70,sources=["基站"],kind="signal"),
                existing=dict(scope=scope,dbm=-83,sources=["原有干扰","接收机等效噪声"],kind="interference_and_noise"))


def test_noise_budget():
    data=inputs()
    def evaluate():
        return budget(Window.model_validate(data))
    assert evaluate()["additional_dbm"] == pytest.approx(-83.0206,abs=.0001)
    assert evaluate()["formal_measurement"] is False
    data["correlation_real"]=1
    assert evaluate()["additional_dbm"] < -90
    data["correlation_real"]=None
    assert evaluate()["additional_dbm"] is None
    data["existing"]["dbm"]=-79
    assert "超过" in evaluate()["reason"]


def test_source_overlap_and_mismatched_plane():
    data=inputs()
    data["additional_source"]="原有干扰"
    assert "重复" in budget(Window.model_validate(data))["reason"]
    data["signal"]["scope"]={**data["scope"],"plane":"receiver_combined"}
    assert "不一致" in budget(Window.model_validate(data))["reason"]


def test_correlated_port_waveform_replays_same_seed():
    import numpy as np
    from app.services.road_test.sinr_plan import Waveforms, render_waveforms
    windows=[]
    for port in ["RX0","RX1"]:
        w=inputs()
        w["scope"].update(receiver=port,bandwidth_hz=2e6,duration_s=128/2e6)
        w["method"]="waveform_covariance"
        windows.append(w)
    data=dict(windows=windows,sample_rate_hz=2e6,sample_count=128,seed=4,
              correlation_real=[[1,1],[1,1]],correlation_imag=[[0,0],[0,0]],
              interference_i=np.zeros((2,128)).tolist(),interference_q=np.zeros((2,128)).tolist())
    request=Waveforms.model_validate(data)
    first=render_waveforms(request)
    assert first==render_waveforms(request)
    np.testing.assert_allclose(first["i"][0],first["i"][1])
    assert first["rf_enabled"] is False and first["formal_measurement"] is False
    data["correlation_real"]=[[1,2],[2,1]]
    with pytest.raises(ValueError,match="半正定"):
        render_waveforms(Waveforms.model_validate(data))
