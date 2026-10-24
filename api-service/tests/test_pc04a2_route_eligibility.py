"""只读采用预览；真实驱动类仅替换外部VISA，不模拟评估结论。"""
import copy
from types import SimpleNamespace
from uuid import UUID

import pytest

from tests.test_rf_chain_resolver import db_session, chamber, topology_two_chains, lab_profile
from tests.test_pc_04a_fixed_route_api import client, configured, start, finish
from app.models.diagnostic_run import DiagnosticRun
from app.models.instrument import InstrumentCategory


@pytest.fixture
def real_capture(client, configured, db_session, monkeypatch):
    def capture(source='-30',received='-60',catalog='0,10000'):
        from app.services.calibration import fixed_route_jobs as jobs
        from app.hal.propsim_f64 import RealPropsimF64Driver
        from app.hal.rs_fsva import RealRsFsvaDriver
        from app.hal.base import InstrumentStatus
        from app.services.instrument_test_lease import InstrumentTestLease
        from tests.test_p1_66_f64_probe_truth import _ScriptedVisaResource
        ce=RealPropsimF64Driver('ce-real-script',{'ip':'192.0.2.10'})
        sa=RealRsFsvaDriver('sa-real-script',{'ip':'192.0.2.10'})
        ce_resource=_ScriptedVisaResource({'*IDN?':'Keysight Technologies,F8800A,SN-CE,8.0',
            'SYSTem:ERRor?':'0,"No error"','DIAG:SIMU:STATE?':'RUNNING',
            'OUTPut:INTERFerence:GET?':'0','OUTPut:LOSS:GET? 1':'0',
            'OUTPut:MEASure:RESult:GET? 1,1':source,'SYSTem:CALIBration:VALid?':'1,1',
            'SYSTem:CALIBration:USER:GET?':'','OUTPut:GAIN:CH? 1':'0'})
        sa_resource=_ScriptedVisaResource({'*IDN?':'Rohde&Schwarz,FSVA3044,SN-SA,1.0',
            'SENSe:CORRection:TRANsducer:CATalog?':catalog,
            'SENSe:CORRection:TRANsducer:STATe?':'0','INITiate:IMMediate; *OPC?':'1',
            'CALCulate:MARKer:FUNCtion:POWer:RESult? CPOWer':received})
        ce._visa_resource,sa._visa_session=ce_resource,sa_resource
        ce._status=InstrumentStatus.READY;ce._local_control_reserved=False;ce.has_interference_generator=True
        hal=SimpleNamespace(drivers={'channelEmulator':ce,'signalAnalyzer':sa})
        lease=InstrumentTestLease(lambda:hal)
        monkeypatch.setattr(jobs,'get_hal_service',lambda:hal)
        monkeypatch.setattr(jobs,'instrument_test_lease',lease.hold)
        configured.instrument_bindings=[{**binding,'driver_mode':'real'} for binding in configured.instrument_bindings]
        db_session.query(InstrumentCategory).update({'driver_mode':'real'});db_session.commit()
        response=start(client,configured)
        assert response.status_code==202,response.text
        value=finish(client,configured,response.json()['run_id'])
        assert value['status']=='completed',value
        return db_session.get(DiagnosticRun,UUID(value['run_id']))
    return capture


def preview(client,lab,row):
    return client.get(f'/api/v1/lab-profiles/{lab.id}/fixed-route-acquisitions/{row.id}/application-preview')


@pytest.mark.parametrize('source,received,expected',[('-30','-60',28.0),('-20','-10',-12.0)])
def test_real_capture_may_be_adopted_without_claiming_certification(client,configured,real_capture,source,received,expected):
    row=real_capture(source,received)
    original=copy.deepcopy(row.sequence_evidence)
    response=preview(client,configured,row)
    assert response.status_code==200,response.text
    result=response.json()
    assert result['eligibility']['eligible_for_adoption'] is True,result
    assert result['eligibility']['measurement_provenance']=='real'
    assert result['eligibility']['certification_status']=='unknown'
    assert result['new_net_loss_db']==expected
    assert result['old_value_db'] is None and result['delta_db'] is None
    assert result['expected_current_application_id'] is None
    assert result['eligibility']['warnings']
    assert row.sequence_evidence==original
    assert original['extra']['fixed_route_acquisition']['formal_eligible'] is False


def test_missing_or_failed_evidence_cannot_be_laundered_by_completed_status(client,configured,real_capture,db_session):
    row=real_capture();original=copy.deepcopy(row.sequence_evidence)
    mutations=[
        lambda r:r.update(status='simulated'),lambda r:r.update(status='running'),
        lambda r:r.update(status='cancelled'),lambda r:r.update(status='cleanup_unconfirmed'),
        lambda r:r.update(status='interrupted'),lambda r:r.update(exchanges=[]),
        lambda r:r.update(samples=[]),lambda r:r['request'].update(receive_cable_source=None),
        lambda r:r.update(cleanup_confirmed=False),lambda r:r['states'].update(f64_control_released=False),
        lambda r:r.update(net_loss_db=999),lambda r:r['exchanges'][0].update(simulated=True),
        lambda r:r['exchanges'][0].update(error='transport failed'),
        lambda r:r['configuration']['binding'].update(execution_mode='simulated'),
        lambda r:r['exchanges'].__setitem__(slice(None),[e for e in r['exchanges'] if e['command']!='INITiate:IMMediate; *OPC?']),
        lambda r:r['exchanges'].__setitem__(slice(None),[e for e in r['exchanges'] if e['command']!='CALCulate:UNIT:POWer DBM']),
        lambda r:r['exchanges'].__setitem__(slice(None),[e for e in r['exchanges'] if e['command']!='SYSTem:ERRor?']),
        lambda r:r['exchanges'].__setitem__(slice(None),[e for e in r['exchanges'] if ':REMove ' not in e['command']]),
        lambda r:r['exchanges'].__setitem__(slice(None),[{**e,'response':'-999'} if e['command'].startswith('OUTPut:MEASure:RESult:GET?') else e for e in r['exchanges']]),
        lambda r:r['exchanges'].__setitem__(slice(None),[{**e,'command':e['command'].replace(',1',',0')} if e['command'].startswith('OUTPut:MEASure:RESult:GET?') else e for e in r['exchanges']]),
        lambda r:r['exchanges'].__setitem__(slice(None),[{**e,'response':'0'} if e['command']=='INITiate:IMMediate; *OPC?' else e for e in r['exchanges']]),
        lambda r:r['exchanges'].__setitem__(slice(None),[{**e,'response':'STOPPED'} if e['command']=='DIAG:SIMU:STATE?' else e for e in r['exchanges']]),
    ]
    for mutate in mutations:
        envelope=copy.deepcopy(original);mutate(envelope['extra']['fixed_route_acquisition'])
        row.sequence_evidence=envelope;db_session.commit()
        response=preview(client,configured,row)
        assert response.status_code==200,response.text
        value=response.json()
        assert value['eligibility']['eligible_for_adoption'] is False,value
        assert value['eligibility']['blockers']
        assert value['new_net_loss_db'] is None


def test_cosmetic_change_only_warns_but_changed_port_is_incompatible(client,configured,real_capture,topology_two_chains,db_session):
    row=real_capture()
    topology_two_chains.nodes=[{**node,'position':{'x':90,'y':70},'label':'新显示名' if node['type']=='probe' else node['label']} for node in topology_two_chains.nodes]
    db_session.commit()
    response=preview(client,configured,row)
    assert response.status_code==200,response.text
    assert response.json()['eligibility']['eligible_for_adoption'] is True,response.text
    topology_two_chains.connections=[{**edge,**({'ce_port':'B3'} if edge['id']=='conn_p0v' else {})} for edge in topology_two_chains.connections]
    db_session.commit()
    value=preview(client,configured,row).json()
    assert value['eligibility']['eligible_for_adoption'] is False,value
    assert 'route_mismatch' in value['eligibility']['blockers']


def test_mock_and_legacy_captures_are_not_eligible_and_other_lab_cannot_read_preview(client,configured,db_session):
    from app.models.lab_profile import LabProfile
    response=start(client,configured)
    value=finish(client,configured,response.json()['run_id'])
    row=db_session.get(DiagnosticRun,UUID(value['run_id']))
    result=preview(client,configured,row).json()
    assert result['eligibility']['eligible_for_adoption'] is False
    assert result['eligibility']['measurement_provenance']=='simulated'
    envelope=copy.deepcopy(row.sequence_evidence)
    legacy=envelope['extra']['fixed_route_acquisition']
    legacy['version']=1;legacy['status']='completed';legacy['exchanges']=[]
    legacy['configuration']={'old_marker':'不得补当前配置'}
    row.sequence_evidence=envelope;db_session.commit()
    result=preview(client,configured,row).json()
    assert result['eligibility']['eligible_for_adoption'] is False
    assert result['selection'] is None and result['new_net_loss_db'] is None
    other=LabProfile(name='另一实验室');db_session.add(other);db_session.commit()
    assert preview(client,other,row).status_code==404


@pytest.mark.parametrize('side',['source','receiver'])
def test_pollution_preconditions_require_original_evidence(client,configured,real_capture,db_session,side):
    row=real_capture();original=copy.deepcopy(row.sequence_evidence)
    command=('OUTPut:INTERFerence:GET?' if side=='source' else
        'SENSe:CORRection:TRANsducer:CATalog?')
    responses=(['1','unknown','',None] if side=='source' else
        ["0,10000,123,'RX-correction'",'0,10000,123','unknown','',None])
    for response in responses:
        envelope=copy.deepcopy(original)
        events=envelope['extra']['fixed_route_acquisition']['exchanges']
        for event in events:
            if event['command']==command:
                event['response']=response
        row.sequence_evidence=envelope;db_session.commit()
        value=preview(client,configured,row).json()
        assert value['eligibility']['eligible_for_adoption'] is False,value
        assert value['eligibility']['blockers']
        assert value['new_net_loss_db'] is None
    envelope=copy.deepcopy(original)
    result=envelope['extra']['fixed_route_acquisition']
    result['exchanges']=[event for event in result['exchanges'] if event['command']!=command]
    row.sequence_evidence=envelope;db_session.commit()
    value=preview(client,configured,row).json()
    assert value['eligibility']['eligible_for_adoption'] is False,value
    assert value['new_net_loss_db'] is None


def test_stored_transducers_require_each_disabled_state(client,configured,real_capture,db_session):
    row=real_capture(catalog="0,10000,123,'RX-correction',456,'Other correction'")
    original=copy.deepcopy(row.sequence_evidence)
    assert preview(client,configured,row).json()['eligibility']['eligible_for_adoption'] is True
    for response in ['1','unknown',None]:
        envelope=copy.deepcopy(original)
        for event in envelope['extra']['fixed_route_acquisition']['exchanges']:
            if event['command']=='SENSe:CORRection:TRANsducer:STATe?':
                event['response']=response
        row.sequence_evidence=envelope;db_session.commit()
        value=preview(client,configured,row).json()
        assert value['eligibility']['eligible_for_adoption'] is False,value
        assert value['new_net_loss_db'] is None
    for command in ["SENSe:CORRection:TRANsducer:SELect 'Other correction'",
            'SENSe:CORRection:TRANsducer:STATe?']:
        envelope=copy.deepcopy(original)
        result=envelope['extra']['fixed_route_acquisition']
        result['exchanges']=[event for event in result['exchanges'] if event['command']!=command]
        row.sequence_evidence=envelope;db_session.commit()
        value=preview(client,configured,row).json()
        assert value['eligibility']['eligible_for_adoption'] is False,value
        assert value['new_net_loss_db'] is None
