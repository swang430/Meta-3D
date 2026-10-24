"""真实采集→确认→冻结→实际端口补偿，不用认证/来源替身。"""
import pytest
from tests.test_pc04a2_route_freeze import (db_session,chamber,topology_two_chains,lab_profile,client,
    configured,real_capture,legacy,launch,confirm,payload)
from app.services.channel_engine_client import ChannelEngineClient
from app.services.mimo_ota.path_loss_preflight import evaluate_path_loss_preflight
from app.services.mimo_ota.route_calibration_freeze import frozen_route_identity_error
from app.services.mimo_ota.switch_orchestrator import orchestrate_switch_topology


@pytest.mark.asyncio
@pytest.mark.parametrize('source_kind',['confirmed','legacy'])
@pytest.mark.parametrize('consumer',['entries','preflight'])
async def test_crossed_ce_outputs_cannot_claim_or_build_waveform_compensation(client,configured,
        real_capture,legacy,launch,db_session,topology_two_chains,chamber,source_kind,consumer):
    # 实际接线B1.2→0V/B1.1→0H；没有输出重排消费者，不能仍向ASC 1/2写V/H值。
    topology_two_chains.nodes=[{**n,'label':{'ce_b1':'B1.2','ce_b2':'B1.1'}.get(n['id'],n['label'])}
        for n in topology_two_chains.nodes]
    legacy.path_loss_db_by_rf_chain={key:{**row,'ce_port':'B1.2' if key=='conn_p0v' else 'B1.1'}
        for key,row in legacy.path_loss_db_by_rf_chain.items()}
    db_session.commit()
    if source_kind=='confirmed':
        run=real_capture(output=2)
        response=confirm(client,configured,payload(client,configured,run))
        assert response.status_code==201,response.text
    execution=await launch()
    if consumer=='entries':
        with pytest.raises(ValueError,match='映射'):
            ChannelEngineClient(db_session)._query_calibration_entries(chamber.id,2595e6,chamber,
                path_loss_calibration=None,route_compensation=execution.config['route_calibration_freeze'])
    else:
        from app.services.mimo_ota.path_loss_application import applied_route_by_probe_pol,path_loss_measurement_is_verified
        # 托管会话读JSON冻结ID（str），MEASURE传ORM UUID；两入口同一拒绝判据。
        for strict,mode,chamber_value in ((True,'real',chamber.id),(True,'real',str(chamber.id)),
                (False,'real',chamber.id),(True,'mock',chamber.id)):
            verdict=evaluate_path_loss_preflight(db_session,execution,chamber_id=chamber_value,frequency_mhz=2595,
                operating_mode='mimo_ota',precheck_strict_cal=strict,channel_emulator_execution_mode=mode)
            assert verdict.application['status']=='not_applied'
            assert verdict.application['reason']=='unsupported_compensation_mode'
            assert verdict.applied_certificate is None and applied_route_by_probe_pol(verdict.application)=={}
            assert not path_loss_measurement_is_verified({'path_loss_application':verdict.application})
            assert (verdict.blocker is not None)==(strict and mode=='real')


@pytest.mark.asyncio
@pytest.mark.parametrize('node_type',['ce_port','channel_emulator'])
@pytest.mark.parametrize('multihop',[False,True])
async def test_declared_ce_port_not_display_label_drives_actual_target(client,configured,real_capture,
        legacy,launch,db_session,topology_two_chains,chamber,node_type,multihop):
    topology_two_chains.nodes=[{**n,'type':node_type,'label':'Display F64',
        'params':{**n.get('params',{}),'ce_port':'B1.1'}} if n['id']=='ce_b1' else n
        for n in topology_two_chains.nodes]
    if multihop:
        topology_two_chains.nodes=[*topology_two_chains.nodes,{'id':'pad','type':'pad','label':'显示衰减器','params':{'ports':['in','out']}}]
        topology_two_chains.connections=[{**edge,'source':'pad'} if edge['id']=='conn_p0v' else edge
            for edge in topology_two_chains.connections]+[{'id':'feed-pad','source':'ce_b1','target':'pad','source_pin':'out','target_pin':'in','modes':['mimo_ota']}]
        topology_two_chains.operating_modes=[{'id':'mimo_ota','name':'normal','active_connections':['feed-pad','conn_p0v','conn_p0h']}]
    db_session.commit()
    run=real_capture()
    response=confirm(client,configured,payload(client,configured,run))
    assert response.status_code==201,response.text
    execution=await launch()
    actual=orchestrate_switch_topology(db_session,chamber.id,'mimo_ota')
    assert next(row.ce_port for row in actual.probe_bindings if row.connection_id=='conn_p0v')=='B1.1'
    assert frozen_route_identity_error(db_session,execution.config['route_calibration_freeze'],resolved_topology=actual) is None
    verdict=evaluate_path_loss_preflight(db_session,execution,chamber_id=chamber.id,frequency_mhz=2595,
        operating_mode='mimo_ota',precheck_strict_cal=True,channel_emulator_execution_mode='real')
    assert verdict.blocker is None and verdict.application['status']=='applied'
    entries=ChannelEngineClient(db_session)._query_calibration_entries(chamber.id,2595e6,chamber,
        path_loss_calibration=None,route_compensation=verdict.route_compensation)
    assert [(row['port_id'],row['cable_loss_db']) for row in entries]==[(1,28),(2,30)]


@pytest.mark.asyncio
@pytest.mark.parametrize('source,received,want',[('-30','-60',28),('-20','-10',-12)])
@pytest.mark.parametrize('tag_fallback',[False,True])
async def test_real_multihop_mixed_freeze_reaches_compensation_once(client,configured,real_capture,legacy,
        launch,db_session,topology_two_chains,chamber,monkeypatch,tmp_path,source,received,want,tag_fallback):
    topology_two_chains.nodes=[*topology_two_chains.nodes,
        {'id':'pad-middle','type':'pad','label':'衰减器','params':{'ports':['in','out']}}]
    topology_two_chains.connections=[{**edge,**({'source':'pad-middle','calibrated_loss_db':3} if edge['id']=='conn_p0v' else {})}
        for edge in topology_two_chains.connections]+[
        {'id':'feed-pad','source':'ce_b1','target':'pad-middle','source_pin':'out','target_pin':'in','modes':['mimo_ota']}]
    topology_two_chains.operating_modes=[{'id':'mimo_ota','name':'normal',
        'active_connections':[] if tag_fallback else ['feed-pad','conn_p0v','conn_p0h']}]
    chamber.has_pa=True;chamber.pa_gain_db=10;chamber.typical_cable_loss_db=3;chamber.probe_gain_dbi=8
    db_session.commit()
    run=real_capture(source,received)
    response=confirm(client,configured,payload(client,configured,run))
    assert response.status_code==201,response.text
    execution=await launch()
    verdict=evaluate_path_loss_preflight(db_session,execution,chamber_id=chamber.id,frequency_mhz=2595,
        operating_mode='mimo_ota',precheck_strict_cal=True,channel_emulator_execution_mode='real')
    assert verdict.blocker is None
    actual=orchestrate_switch_topology(db_session,chamber.id,'mimo_ota')
    assert next(b.ce_port for b in actual.probe_bindings if b.connection_id=='conn_p0v')=='B1.1'
    assert frozen_route_identity_error(db_session,verdict.route_compensation,resolved_topology=actual) is None
    engine=ChannelEngineClient(db_session)
    monkeypatch.setattr(engine,'_query_phase_compensation',lambda *args,**kwargs:{})
    entries=engine._query_calibration_entries(chamber.id,2595e6,chamber,path_loss_calibration=None,
        route_compensation=verdict.route_compensation)
    assert [(e['port_id'],e['cable_loss_db'],e['probe_gain_dbi']) for e in entries]==[(1,want,0),(2,30,8)]
    assert entries[0]['method']=='fixed_route_port_to_reference_v1'
    assert entries[0]['reference_plane']=='ce_output_to_reference_antenna_output'
    import os
    if not tag_fallback and os.environ.get('CHANNEL_ENGINE_PATH'):
        await assert_final_loaded_asc(engine,entries,chamber,monkeypatch,tmp_path,want)
    assert verdict.application['status']=='applied'
    assert verdict.application['applied_chain_ids']==['conn_p0v','conn_p0h']
    assert verdict.applied_certificate is None  # 混合新旧不是一张旧证书
    from app.services.mimo_ota.path_loss_application import applied_route_by_probe_pol,path_loss_measurement_is_verified
    used=applied_route_by_probe_pol(verdict.application)
    assert used[(0,'V')]['value_db']==want
    assert used[(0,'V')]['source_kind']=='confirmed_route'
    assert used[(0,'H')]['value_db']==30
    assert path_loss_measurement_is_verified({'path_loss_application':verdict.application}) is True
    from datetime import datetime
    from tests.test_mimo_ota_report_verified_backcompat import _exec,_path_loss_report_phases
    from app.services.mimo_ota.executors.report import _build_mimo_ota_content_data
    content=_build_mimo_ota_content_data(_exec(_path_loss_report_phases(verdict.application,verified=True)),datetime.utcnow())
    assert content['formal_path_loss_verified'] is True
    from app.services.mimo_ota.path_loss_application import path_loss_application_message
    assert '认证资格未知' in path_loss_application_message(verdict.application)
    for mode in ('keysight_gcm','external_asc','b2_parametric_tdl'):
        unsupported=evaluate_path_loss_preflight(db_session,execution,chamber_id=chamber.id,frequency_mhz=2595,
            operating_mode='mimo_ota',precheck_strict_cal=True,channel_emulator_execution_mode='real',engine_mode=mode)
        assert unsupported.application['status']=='not_applied'
        assert unsupported.application['reason']=='unsupported_compensation_mode'
        assert unsupported.blocker is not None


def test_missing_route_or_unknown_history_cannot_claim_applied():
    from app.services.mimo_ota.path_loss_application import applied_route_by_probe_pol,path_loss_measurement_is_verified
    assert applied_route_by_probe_pol(None)=={}
    assert path_loss_measurement_is_verified({'path_loss_verified':True,'path_loss_calibration_use_mock':False}) is False


@pytest.mark.asyncio
async def test_real_new_route_with_missing_other_chain_remains_not_applied(client,configured,real_capture,
        legacy,launch,db_session,chamber):
    legacy.path_loss_db_by_rf_chain={'conn_p0v':legacy.path_loss_db_by_rf_chain['conn_p0v']}
    db_session.commit()
    run=real_capture()
    assert confirm(client,configured,payload(client,configured,run)).status_code==201
    execution=await launch()
    result=evaluate_path_loss_preflight(db_session,execution,chamber_id=chamber.id,frequency_mhz=2595,
        operating_mode='mimo_ota',precheck_strict_cal=True,channel_emulator_execution_mode='real')
    assert result.blocker is not None
    assert result.application['status']=='not_applied'
    assert result.application['reason']=='incomplete_coverage'
    assert result.application['applied_chain_ids']==[]
    assert result.application['route_compensation']['route_entries'][1]['value_db'] is None


@pytest.mark.asyncio
async def test_new_only_precheck_reports_adoption_not_missing_old_certificate(client,configured,real_capture,
        launch,db_session,chamber,topology_two_chains,monkeypatch):
    from types import SimpleNamespace
    from app.services.mimo_ota.executors.precheck import PrecheckExecutor
    from app.services.test_execution import StepExecutionContext,StepDescriptor
    topology_two_chains.operating_modes=[{'id':'mimo_ota','name':'normal','active_connections':['conn_p0v']}]
    db_session.commit()
    run=real_capture()
    assert confirm(client,configured,payload(client,configured,run)).status_code==201
    execution=await launch()
    monkeypatch.setattr('app.services.instrument_hal_service.get_hal_service',lambda:SimpleNamespace(drivers={}))
    result=await PrecheckExecutor().execute(StepExecutionContext(db=db_session,
        step=StepDescriptor(id='precheck',type='MIMO_OTA_PRECHECK',parameters={}),test_execution=execution,
        lab_profile=configured,calibration_certificate=None))
    assert result.measurements['path_loss_calibration_valid'] is True
    assert result.measurements['path_loss_calibration_use_mock'] is False
    assert result.measurements['path_loss_application']['status']=='applied'
    from contextlib import asynccontextmanager
    from app.services import base_station_execution_session as session
    from app.services.mimo_ota.executors import _helpers
    config=_helpers.load_mimo_ota_config(execution)
    config.engine_mode='keysight_gcm'
    monkeypatch.setattr(_helpers,'load_mimo_ota_config',lambda _execution:config)
    execution.config={**execution.config,'channel_emulator_binding_freeze':{'execution_mode':'real'},
        'channel_emulator_execution_plan_freeze':{}}
    observed=[]
    @asynccontextmanager
    async def before_hardware(*args,**kwargs):
        observed.append(kwargs['preflight_before_remote'](None))
        raise RuntimeError('test stops at pure gate, before any lease or hardware')
        yield
    monkeypatch.setattr(session,'channel_emulator_execution_scope',before_hardware)
    monkeypatch.setattr(session,'_get_hal_service',lambda:None)
    monkeypatch.setattr(session,'_record_exception_terminal_state',lambda *args,**kwargs:None)
    with pytest.raises(RuntimeError,match='test stops'):
        await session.run_base_station_execution_session(db_session,execution,SimpleNamespace(),purpose='test',
            step_type='MIMO_OTA_MEASURE',validate_before_remote=None,operation=None)
    assert observed[0] is not None and '没有整条参考面' in observed[0]


@pytest.mark.asyncio
@pytest.mark.parametrize('location,want',[('control',False),('waveform',True)])
async def test_asc_strategy_requires_actual_waveform_compensation_receipt(tmp_path,location,want):
    from types import SimpleNamespace
    from app.services.channel_generation.asc_strategy import ExternalWaveformStrategy
    archive=tmp_path/'asc.zip';archive.write_bytes(b'file presence isolated here; actual ASC numeric tests in CE service')
    class Client:
        async def synthesize_hardware_pipeline(self,**kwargs):
            return SimpleNamespace(success=True,asc_files_path=str(archive),calibration_application=location)
    class Emulator:
        async def load_channel(self,**kwargs):
            return True
    strategy=ExternalWaveformStrategy(Emulator(),Client(),SimpleNamespace(id=None),
        [{'port_id':1,'cable_loss_db':28,'probe_gain_dbi':0,'chain_id':'a'}])
    assert await strategy.generate_and_load({}, {'model_name':'UMa CDL-C NLOS'}) is want


@pytest.mark.asyncio
@pytest.mark.parametrize('mock_mode',[True,None])
async def test_frozen_waveform_cannot_accept_mock_or_unknown_ce_reply(db_session,chamber,monkeypatch,mock_mode):
    import httpx
    original=httpx.AsyncClient
    def reply(request):
        import json
        assert json.loads(request.content)['calibration_application']=='waveform'
        return httpx.Response(200,json={'status':'success','calibration_application':'waveform','mock_mode':mock_mode})
    monkeypatch.setattr('app.services.channel_engine_client.httpx.AsyncClient',
        lambda **kwargs:original(transport=httpx.MockTransport(reply),**kwargs))
    result=await ChannelEngineClient(db_session).synthesize_hardware_pipeline(chamber.id,2595e6,
        calibration_entries=[{'port_id':1,'cable_loss_db':28,'probe_gain_dbi':0,'chain_id':'a'}])
    assert result.success is False


@pytest.mark.asyncio
async def test_frozen_entries_do_not_guess_ambiguous_physical_probe_namespace(configured,legacy,launch,
        topology_two_chains,db_session,chamber,monkeypatch):
    topology_two_chains.nodes=[{**node,'params':{**node.get('params',{}),'probe_id':1}}
        if node['type']=='probe' else node for node in topology_two_chains.nodes]
    legacy.path_loss_db_by_rf_chain={key:{**row,'probe_id':1} for key,row in legacy.path_loss_db_by_rf_chain.items()}
    db_session.commit()
    execution=await launch()
    engine=ChannelEngineClient(db_session)
    monkeypatch.setattr(engine,'_query_phase_compensation',lambda *args,**kwargs:{})
    with pytest.raises(ValueError,match='探头编号'):
        engine._query_calibration_entries(chamber.id,2595e6,chamber,path_loss_calibration=None,
            route_compensation=execution.config['route_calibration_freeze'])


@pytest.mark.asyncio
@pytest.mark.parametrize('mode',['keysight_gcm','external_asc','b2_parametric_tdl'])
async def test_legacy_only_frozen_routes_also_need_a_real_compensation_consumer(configured,legacy,launch,db_session,chamber,mode):
    execution=await launch()
    result=evaluate_path_loss_preflight(db_session,execution,chamber_id=chamber.id,frequency_mhz=2595,
        operating_mode='mimo_ota',precheck_strict_cal=True,channel_emulator_execution_mode='real',engine_mode=mode)
    assert result.application['status']=='not_applied'
    assert result.application['reason']=='unsupported_compensation_mode'
    assert result.applied_certificate is None and result.blocker is not None


async def assert_final_loaded_asc(engine,entries,chamber,monkeypatch,tmp_path,want):
    """隔离进程运行真实CE应用；仅替HTTP传输与HAL加载边界，检查加载端最终文件。"""
    import os,json,subprocess,sys
    from pathlib import Path
    import httpx
    from app.services.channel_generation.asc_strategy import ExternalWaveformStrategy
    ce_dir=Path(__file__).resolve().parents[2]/'channel-engine-service'
    script='''import sys,json,io,contextlib
body=json.load(sys.stdin)
with contextlib.redirect_stdout(io.StringIO()):
 import numpy as np
 from fastapi.testclient import TestClient
 from app.main import app
 np.random.seed(42)
 response=TestClient(app).post('/api/v1/synthesize_hardware_pipeline',json=body)
print(json.dumps({'code':response.status_code,'body':response.json()}))
'''
    def rpc(request):
        process=subprocess.run([sys.executable,'-c',script],input=request.content.decode(),text=True,
            capture_output=True,cwd=ce_dir,env=dict(os.environ),check=True)
        response=json.loads(process.stdout)
        return httpx.Response(response['code'],json=response['body'])
    original=httpx.AsyncClient
    monkeypatch.setattr('app.services.channel_engine_client.httpx.AsyncClient',
        lambda **kwargs:original(transport=httpx.MockTransport(rpc),**kwargs))
    monkeypatch.setattr('app.services.channel_engine_client.HARDWARE_ARTIFACTS_DIR',str(tmp_path))
    captured=[]
    class LoadingBoundary:
        async def load_channel(self,**kwargs):
            files=sorted(Path(kwargs['waveform_dir']).glob('*_Out1.asc'))
            assert files
            values=[]
            for path in files:
                for line in path.read_text().splitlines():
                    parts=line.split()
                    if parts and len(parts)%3==0:
                        try:
                            nums=[float(value) for value in parts]
                        except ValueError:
                            continue
                        values.extend(abs(complex(nums[i+1],nums[i+2])) for i in range(0,len(nums),3))
            captured.append(values)
            return True
    for selected in ([{**row,'cable_loss_db':0,'probe_gain_dbi':0} for row in entries],entries):
        strategy=ExternalWaveformStrategy(LoadingBoundary(),engine,chamber,selected)
        assert await strategy.generate_and_load({'frequency_hz':2595e6},{'model_name':'UMa CDL-C NLOS'}) is True
    before,after=captured
    assert len(after)==len(before)>0
    pairs=[(a,b) for a,b in zip(after,before) if b>1e-12]
    assert pairs
    ratio=25.1188643151 if want==28 else 0.251188643151
    assert all(a/b==pytest.approx(ratio,rel=2e-6) for a,b in pairs)
