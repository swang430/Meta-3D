import asyncio
import hashlib
import json
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4
import pytest
from tests.test_road_test_executions import _isolated_db, _TestingSessionLocal
ROOT = '/api/v1/road-test'


def setup_ota(client, tmp_path, *, frequency_mhz=3500):
    from app.models.chamber import ChamberConfiguration
    from app.models.probe import Probe
    from app.models.lab_profile import LabProfile
    sid = client.get(ROOT+'/scenarios').json()[0]['id']
    scenario = client.get(ROOT+'/scenarios/'+sid).json()
    scenario['step_configuration'] = {'network_config': {'frequency_mhz': frequency_mhz}}
    scenario = client.post(ROOT+'/scenarios', json=scenario).json()
    sid = scenario['id']
    (tmp_path/'route.asc').write_bytes(b'ota waveform')
    raw = json.dumps(dict(mode='ota', direction='downlink', header=dict(cir_count=38, rate_hz=1), links=[dict(file='route.asc',sha256=hashlib.sha256(b'ota waveform').hexdigest())])).encode()
    (tmp_path/'manifest.json').write_bytes(raw)
    preview = client.post(ROOT+'/ota/prepare',json={'scenario_id':sid})
    assert preview.status_code == 200, preview.text
    with _TestingSessionLocal() as db:
        chamber = ChamberConfiguration(name='模拟暗室',chamber_type='type_c',chamber_radius_m=4,num_probes=1,quiet_zone_diameter_m=2,ce_num_ota_ports=2)
        db.add(chamber); db.flush()
        probe = Probe(chamber_config_id=chamber.id,probe_number=1,ring=3,polarization='H',position=dict(azimuth=0,elevation=0,radius=4),channel_port=1)
        db.add(probe); db.flush()
        sel = dict(scenario_id=sid,chamber_id=str(chamber.id),asset_id=str(uuid4()),direction='downlink')
        reg = dict(sel,scenario_version=scenario['version'],scenario_sha256=preview.json()['scenario_sha256'],name='OTA模拟工程',kind='ota_manifest',manifest_dir=str(tmp_path),sha256=hashlib.sha256(raw).hexdigest(),probe_mapping=[dict(probe_id=str(probe.id),output_port=1,polarization='H',position=dict(probe.position))],calibration=dict(mock_only=True,frequency_min_mhz=1,frequency_max_mhz=100000,bandwidth_mhz=1000,quiet_zone_diameter_m=2,valid_until=(datetime.now(timezone.utc)+timedelta(days=1)).isoformat()))
        lab = LabProfile(name='OTA模拟实验室',chamber_config_id=chamber.id,extra_metadata={'vrt_ota':[reg]})
        db.add(lab); db.commit()
        sel['lab_profile_id']=str(lab.id)
        return sel, reg, lab.id


def test_missing_ota_draft(client):
    sid=client.get(ROOT+'/scenarios').json()[0]['id']
    r=client.post(ROOT+'/ota/executions',json={'scenario_id':sid})
    assert r.status_code==201,r.text
    data=r.json()
    assert not data['config']['ota']['ready']
    assert len(data['config']['ota']['reasons'])>=3
    assert client.post(ROOT+'/executions/'+data['execution_id']+'/control',json={'action':'start'}).status_code==409


@pytest.mark.parametrize('change',['none','position','polarization','mapping','calibration','direction','bytes','missing_clock','mixed','duplicate'])
def test_ota_evidence_and_control(client,tmp_path,monkeypatch,change):
    from app.models.lab_profile import LabProfile
    sel,reg,lab_id=setup_ota(client,tmp_path)
    if change=='position': reg['probe_mapping'][0]['position']['radius']=3
    if change=='polarization': reg['probe_mapping'][0]['polarization']='V'
    if change=='mapping': reg['probe_mapping'][0]['output_port']=2
    if change=='calibration': reg['calibration']['frequency_max_mhz']=1
    if change=='direction': reg['direction']='uplink'
    if change=='bytes': (tmp_path/'route.asc').write_bytes(b'changed')
    if change=='missing_clock':
        path = tmp_path / 'manifest.json'
        manifest = json.loads(path.read_bytes())
        del manifest['header']
        raw = json.dumps(manifest).encode()
        path.write_bytes(raw)
        reg['sha256'] = hashlib.sha256(raw).hexdigest()
    if change=='mixed':
        from app.services.instrument_hal_service import get_hal_service
        monkeypatch.setitem(get_hal_service().drivers,'channelEmulator',object())
    with _TestingSessionLocal() as db:
        lab=db.get(LabProfile,lab_id);lab.extra_metadata={'vrt_ota':[reg,reg] if change=='duplicate' else [reg]};db.commit()
    r=client.post(ROOT+'/ota/prepare',json=sel)
    assert r.status_code==200,r.text
    snapshot=r.json()
    assert snapshot['ready'] is (change=='none'),snapshot
    if change=='missing_clock':
        assert any('播放文件头' in reason for reason in snapshot['reasons'])
    if change!='none':
        assert snapshot['reasons'];return
    assert snapshot['playback']['duration_s'] == 37
    created=client.post(ROOT+'/ota/executions',json=sel).json()
    url=ROOT+'/executions/'+created['execution_id']
    assert created['config']['ota']==snapshot
    assert client.post(url+'/control',json={'action':'start'}).is_success
    assert client.get(url).json()['status']=='running'
    assert client.post(url+'/control',json={'action':'pause'}).status_code==409
    assert client.post(url+'/control',json={'action':'stop'}).is_success
    assert client.get(url).json()['status']=='stopped'
    metrics=client.get(url+'/metrics').json()
    assert metrics['observations'] and all(x['provenance']=='simulated' for x in metrics['observations'])
    report=client.get(url+'/report').json()
    assert report['ota_setup']==snapshot
    assert report['kpi_summary']==[] and report['pass_rate'] is None and report['overall_result']=='incomplete'
    archived=client.post(url+'/archive-report')
    assert archived.is_success,archived.text
    assert client.get(ROOT+'/executions?mode=ota').json()[0]['ota']==snapshot


@pytest.mark.parametrize('active_mode',['digital_twin','conducted','ota'])
def test_modes_exclude_other_active_execution(client,tmp_path,active_mode):
    from app.schemas.road_test import TestMode, ExecutionStatus
    from app.services.road_test.vrt_execution_service import vrt_execution_service as service
    sel,_,_=setup_ota(client,tmp_path)
    with _TestingSessionLocal() as db:
        row=service.create(db,mode=TestMode(active_mode),scenario_id=sel['scenario_id'])
        service.start(db,str(row.id))
    created=client.post(ROOT+'/ota/executions',json=sel).json()
    assert client.post(ROOT+'/executions/'+created['execution_id']+'/control',json={'action':'start'}).status_code==409
    twin=client.post(ROOT+'/executions',json={'mode':'digital_twin','scenario_id':sel['scenario_id']}).json()
    assert client.post(ROOT+'/executions/'+twin['execution_id']+'/control',json={'action':'start'}).status_code==409


def test_ota_pdf_keeps_chamber_probe_and_simulation_evidence():
    from app.services.pdf_generator import PDFGenerator
    from reportlab.platypus import Paragraph
    gen=PDFGenerator()
    data={'ota_setup':dict(scenario_version='1',lab_name='模拟实验室',chamber={'name':'独立暗室'},asset={'name':'模拟OTA工程','sha256':'abc'},probe_mapping=[dict(probe_id='probe-001',output_port=1,polarization='H',position=dict(azimuth=0,elevation=0,radius=4))],binding={'mock_only':True})}
    # 报告来源区不能丢掉 OTA 准备证据。
    elements=gen._generate_vrt_kpi_summary_section({},data)
    text=' '.join(x.getPlainText() for x in elements if isinstance(x,Paragraph))
    assert '独立暗室' in text and 'probe-001' in text and '现场待验' in text


@pytest.mark.parametrize('failure',['changed_after_save','start_rejected','stop_unconfirmed','client_metrics','legacy','cross_mode_config'])
def test_ota_reachable_failures(client,tmp_path,monkeypatch,failure):
    from unittest.mock import AsyncMock
    from app.services.instrument_hal_service import get_hal_service
    from app.models.lab_profile import LabProfile
    sel,reg,lab_id=setup_ota(client,tmp_path)
    if failure=='cross_mode_config':
        assert client.post(ROOT+'/executions',json={'scenario_id':sel['scenario_id'],'mode':'digital_twin','config':{'ota':reg}}).status_code==400
        return
    created=client.post(ROOT+'/ota/executions',json=sel).json() if failure!='legacy' else client.post(ROOT+'/executions',json={'mode':'ota','scenario_id':sel['scenario_id']}).json()
    url=ROOT+'/executions/'+created['execution_id']
    channel=get_hal_service().drivers['channelEmulator']
    if failure=='changed_after_save':
        reg['probe_mapping'][0]['position']['radius']=3
        with _TestingSessionLocal() as db:
            lab=db.get(LabProfile,lab_id);lab.extra_metadata={'vrt_ota':[reg]};db.commit()
    if failure=='start_rejected': monkeypatch.setattr(channel,'start_emulation',AsyncMock(return_value=False))
    if failure in ('legacy','changed_after_save','start_rejected'):
        assert client.post(url+'/control',json={'action':'start'}).status_code==409
        assert client.get(url).json()['status']==('failed' if failure=='start_rejected' else 'idle')
        return
    assert client.post(url+'/control',json={'action':'start'}).is_success
    if failure=='client_metrics':
        assert client.post(url+'/metrics',json={'execution_id':created['execution_id'],'time_series':[],'kpi_summary':[],'events':[],'phases':[]}).status_code==409
    if failure=='stop_unconfirmed': monkeypatch.setattr(channel,'stop_emulation',AsyncMock(return_value=False))
    stopped=client.post(url+'/control',json={'action':'stop'})
    assert stopped.status_code==(409 if failure=='stop_unconfirmed' else 200)
    if failure=='stop_unconfirmed': assert client.get(url).json()['status']=='failed'


def test_ota_capability_requires_explicit_preparation(client):
    result=client.get(ROOT+'/capabilities').json()['ota']
    assert result['available'] is True
    assert result['simulated_available'] is True
    assert result['real_available'] is False
    assert result['requires_preparation'] is True


@pytest.mark.parametrize('status',['initializing','running','paused'])
def test_restart_recovers_ota_and_releases_mode_exclusion(client,tmp_path,status):
    from app.models.test_plan import TestExecution as Row
    from app.services.road_test.conducted_runner import recover_conducted_runs
    from app.schemas.road_test import TestMode
    from app.services.road_test.vrt_execution_service import vrt_execution_service as service
    sel,_,_=setup_ota(client,tmp_path)
    with _TestingSessionLocal() as db:
        stale=service.create(db,mode=TestMode.OTA,scenario_id=sel['scenario_id'])
        stale.status=status;db.commit();key=str(stale.id)
        recover_conducted_runs(db)
        db.expire_all();stale=db.get(Row,stale.id)
        assert stale.status=='failed'
        assert stale.hardware_status['vrt_restart_recovery']['previous_status']==status
        assert stale.hardware_status['vrt_restart_recovery']['device_stop_verified'] is False
        assert '服务曾中断' in stale.error_message
        # 重复恢复不能改写原恢复证据。
        evidence=dict(stale.hardware_status)
        recover_conducted_runs(db);db.refresh(stale)
        assert stale.hardware_status==evidence
    twin=client.post(ROOT+'/executions',json={'mode':'digital_twin','scenario_id':sel['scenario_id']}).json()
    url=ROOT+'/executions/'+twin['execution_id']
    assert client.post(url+'/control',json={'action':'start'}).is_success
    assert client.post(url+'/control',json={'action':'stop'}).is_success
    ota=client.post(ROOT+'/ota/executions',json=sel).json()
    url=ROOT+'/executions/'+ota['execution_id']
    assert client.post(url+'/control',json={'action':'start'}).is_success
    assert client.post(url+'/control',json={'action':'stop'}).is_success


@pytest.mark.parametrize('probe_count', [16, 32])
def test_ota_many_probes_preserves_loaded_communication_dimensions(client, tmp_path, monkeypatch, probe_count):
    from app.models.chamber import ChamberConfiguration
    from app.models.probe import Probe
    from app.models.lab_profile import LabProfile
    from app.services.instrument_hal_service import get_hal_service
    sel, reg, lab_id = setup_ota(client, tmp_path)
    with _TestingSessionLocal() as db:
        chamber = db.get(ChamberConfiguration, UUID(sel['chamber_id']))
        chamber.num_probes = chamber.ce_num_ota_ports = probe_count
        for n in range(2, probe_count + 1):
            probe = Probe(chamber_config_id=chamber.id, probe_number=n, ring=3, polarization='H',
                          position=dict(azimuth=n, elevation=0, radius=4), channel_port=n)
            db.add(probe); db.flush()
            reg['probe_mapping'].append(dict(probe_id=str(probe.id), output_port=n,
                                            polarization='H', position=dict(probe.position)))
        db.get(LabProfile, lab_id).extra_metadata = {'vrt_ota': [reg]}
        db.commit()
    channel = get_hal_service().drivers['channelEmulator']
    original = channel.load_channel
    async def load(*args, **kwargs):
        result = await original(*args, **kwargs)
        await channel.set_mimo_config(2, 4)
        return result
    monkeypatch.setattr(channel, 'load_channel', load)
    created = client.post(ROOT+'/ota/executions', json=sel).json()
    assert created['config']['ota']['ready'], created
    url = ROOT+'/executions/'+created['execution_id']
    started = client.post(url+'/control', json={'action': 'start'})
    try:
        assert started.is_success, started.text
        assert asyncio.run(channel.get_channel_state())['mimo_config'] == {'tx': 2, 'rx': 4}
    finally:
        client.post(url+'/control', json={'action': 'stop'})


@pytest.mark.parametrize('frequency', [None, 0, -1, 3600])
def test_ota_calibration_requires_explicit_covered_center_frequency(client, tmp_path, frequency):
    from app.models.lab_profile import LabProfile
    sel, reg, lab_id = setup_ota(client, tmp_path, frequency_mhz=frequency)
    reg['calibration'].update(frequency_min_mhz=3490, frequency_max_mhz=3510)
    with _TestingSessionLocal() as db:
        db.get(LabProfile, lab_id).extra_metadata = {'vrt_ota': [reg]}
        db.commit()
    preview = client.post(ROOT+'/ota/prepare', json=sel).json()
    assert preview['ready'] is False
    assert any('校准' in reason for reason in preview['reasons'])
    created = client.post(ROOT+'/ota/executions', json=sel).json()
    assert created['config']['ota']['ready'] is False
    assert client.post(ROOT+'/executions/'+created['execution_id']+'/control', json={'action': 'start'}).status_code == 409
