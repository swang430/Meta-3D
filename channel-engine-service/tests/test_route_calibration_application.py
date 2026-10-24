"""端口净损耗只消费一次：普通预算与真实确定性ASC数值。"""
import base64
import io
import zipfile
import pytest
from tests.test_deterministic_b1 import client,_body
from app.models.hardware_pipeline_models import CalibrationEntry,SimulationRules,CDLModelData
from app.api.endpoints.hardware_pipeline import _compute_control_instructions


def entry(loss,**changes):
    return dict(port_id=1,cable_loss_db=loss,probe_gain_dbi=0,cable_phase_deg=0,
        method='fixed_route_port_to_reference_v1',reference_plane='ce_output_to_reference_antenna_output',**changes)


@pytest.mark.parametrize('loss',[28,-12])
def test_budget_uses_signed_net_once(loss):
    cal=CalibrationEntry.model_validate(entry(loss))
    result=_compute_control_instructions(SimulationRules(center_frequency_hz=3.5e9,target_tx_power_dbm=0,
        target_rsrp_dbm=0),CDLModelData(model_name='UMa CDL-C NLOS',pathloss_db=80),[cal],1)
    assert result.target_achieved_rsrp_dbm==(-108 if loss==28 else -68)


def amplitudes(response):
    assert response.status_code==200,response.text
    data=response.json()
    assert not data.get('control_instructions')  # ASC内预失真不能再附加预算补偿
    return zip_amplitudes(data['asc_zip_base64'])


def zip_amplitudes(encoded):
    with zipfile.ZipFile(io.BytesIO(base64.b64decode(encoded))) as archive:
        samples=[]
        for name in sorted(archive.namelist()):
            for line in archive.read(name).decode().splitlines():
                fields=line.split()
                if fields and len(fields)%3==0:
                    try:
                        values=[float(field) for field in fields]
                        samples.extend(abs(complex(values[i+1],values[i+2])) for i in range(0,len(values),3))
                    except ValueError: pass
        return samples


@pytest.mark.parametrize('routing_mode',['legacy','annotated_b1'])
@pytest.mark.parametrize('loss,want',[(28,25.1188643151),(-12,0.251188643151)])
def test_ordinary_waveform_opt_in_bakes_net_once_without_second_control_correction(routing_mode,loss,want):
    import numpy as np
    from tests.test_annotated_b1_routing import _request
    body=_request(routing_mode).model_dump(mode='json')
    body['calibration_application']='waveform'
    def synthesize(value):
        body['calibration_data']={'entries':[entry(value)|{'port_id':p} for p in range(1,9)]}
        np.random.seed(42)
        response=client.post('/api/v1/synthesize_hardware_pipeline',json=body)
        assert response.status_code==200,response.text
        return response.json()
    baseline=synthesize(0);actual=synthesize(loss)
    before=zip_amplitudes(baseline['hardware_artifacts']['f64_asc_files_zip_base64'])
    after=zip_amplitudes(actual['hardware_artifacts']['f64_asc_files_zip_base64'])
    assert len(after)==len(before)>0 and any(value>1e-12 for value in before)
    assert all(a/b==pytest.approx(want,rel=2e-6) for a,b in zip(after,before) if b>1e-12)
    assert actual['calibration_application']=='waveform'
    assert actual['control_instructions']==baseline['control_instructions']


@pytest.mark.parametrize('loss,want',[ (28,25.1188643151),(-12,0.251188643151)])
def test_deterministic_asc_contains_exactly_one_signed_net_correction(loss,want):
    body=_body(f64={'large_centroid_thresh_hz':1e6})
    body['calibration_data']={'entries':[entry(0)|{'port_id':p} for p in range(1,9)]}
    baseline=amplitudes(client.post('/api/v1/synthesize_deterministic_b1',json=body))
    body['calibration_data']={'entries':[entry(loss)|{'port_id':p} for p in range(1,9)]}
    actual=amplitudes(client.post('/api/v1/synthesize_deterministic_b1',json=body))
    assert len(actual)==len(baseline)>0
    assert all(a/b==pytest.approx(want,rel=2e-6) for a,b in zip(actual,baseline) if b>1e-12)


@pytest.mark.parametrize('change',[{'reference_plane':'DUT'}, {'probe_gain_dbi':8}])
def test_new_method_rejects_wrong_reference_plane_or_second_probe_gain(change):
    with pytest.raises(ValueError):
        CalibrationEntry.model_validate(entry(28)|change)
