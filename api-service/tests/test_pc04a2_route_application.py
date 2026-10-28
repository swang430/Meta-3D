"""确认采用的真实API/数据库行为；仅外部VISA transport使用合成脚本。"""
import copy
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Barrier
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, inspect, text, event
from sqlalchemy.orm import sessionmaker

from app.db.database import Base, get_db
from app.main import app
from tests.test_rf_chain_resolver import chamber, topology_two_chains, lab_profile
from tests.test_pc_04a_fixed_route_api import client, configured, start, finish
from tests.test_pc04a2_route_eligibility import real_capture, preview


@pytest.fixture
def db_session(tmp_path):
    engine=create_engine(f'sqlite:///{tmp_path / "application.db"}',connect_args={'check_same_thread':False})
    Base.metadata.create_all(engine)
    factory=sessionmaker(bind=engine,expire_on_commit=False)
    with factory() as session:
        yield session
    engine.dispose()


def payload(client,lab,row,**changes):
    candidate=preview(client,lab,row).json()
    value=dict(acquisition_run_id=str(row.id),route_digest=candidate['selection']['route_digest'],
        expected_current_application_id=candidate['expected_current_application_id'],
        idempotency_key=str(uuid4()),confirmed=True,
        adoption_valid_until=(datetime.now(timezone.utc)+timedelta(days=1)).isoformat())
    value.update(changes)
    return value


def confirm(client,lab,value):
    return client.post(f'/api/v1/lab-profiles/{lab.id}/route-calibration-applications',json=value)


def counts(db):
    # RED阶段表尚未出现时也能证明无写入，不以缺模型import替代行为测试。
    names=inspect(db.get_bind()).get_table_names()
    return tuple(db.execute(text(f'SELECT count(*) FROM {table}')).scalar() if table in names else 0
        for table in ('route_calibration_applications','route_calibration_selections'))


def test_real_confirmation_freezes_server_value_and_preserves_history(client,configured,real_capture,db_session):
    row=real_capture();original=copy.deepcopy(row.sequence_evidence)
    assert counts(db_session)==(0,0)
    request=payload(client,configured,row)
    assert counts(db_session)==(0,0)  # preview不写入
    response=confirm(client,configured,request)
    assert response.status_code==201,response.text
    first=response.json()
    assert first['net_loss_db']==28 and first['predecessor_id'] is None
    assert first['certification_status']=='unknown' and first['operator_confirmed'] is True
    assert first['confirmed_by'] is None  # API没有可验证的登录身份，不造姓名
    assert first['coverage_snapshot']['validity_source']=='operator_declared_adoption_window'
    assert first['coverage_snapshot']['frequency_mhz']==2595
    assert first['reference_snapshot']['identity_description']=='SN-REF 静区中心V'
    assert first['reference_snapshot']['receive_cable_source']=='SN-CABLE 2595MHz记录'
    assert first['reference_snapshot']['receive_cable_identity']=='SN-CABLE 2595MHz记录'
    assert first['adoption_evidence_snapshot']['measurement_provenance']=='real'
    assert first['adoption_evidence_snapshot']['checked_exchange_indices']
    assert row.sequence_evidence==original
    assert original['extra']['fixed_route_acquisition']['formal_eligible'] is False
    assert counts(db_session)==(1,1)
    state=preview(client,configured,row).json()
    assert state['expected_current_application_id']==first['id']
    assert state['old_value_db']==28 and state['delta_db']==0
    second_row=real_capture('-20','-10')
    second=confirm(client,configured,payload(client,configured,second_row))
    assert second.status_code==201,second.text
    assert second.json()['predecessor_id']==first['id'] and second.json()['net_loss_db']==-12
    history=client.get(f'/api/v1/lab-profiles/{configured.id}/route-calibration-applications',
        params={'topology_id':first['selection_snapshot']['topology_id'],'chain_id':'conn_p0v'})
    assert history.status_code==200,history.text
    assert len(history.json())==2 and first in history.json()
    assert counts(db_session)==(2,1)


def test_idempotency_and_stale_current_are_conflicts(client,configured,real_capture,db_session):
    row=real_capture();request=payload(client,configured,row)
    first=confirm(client,configured,request)
    assert first.status_code==201,first.text
    replay=confirm(client,configured,request)
    assert replay.status_code==200 and replay.json()==first.json()
    assert confirm(client,configured,{**request,'adoption_valid_until':
        (datetime.now(timezone.utc)+timedelta(days=2)).isoformat()}).status_code==409
    assert confirm(client,configured,{**request,'idempotency_key':str(uuid4())}).status_code==409
    assert counts(db_session)==(1,1)


def test_rejected_confirmation_has_no_writes(client,configured,real_capture,db_session,topology_two_chains):
    row=real_capture();request=payload(client,configured,row)
    invalid=[{**request,'confirmed':1},{**request,'net_loss_db':0},
        {k:v for k,v in request.items() if k!='adoption_valid_until'},
        {**request,'adoption_valid_until':'2026-01-01T00:00:00Z'},
        {**request,'adoption_valid_until':'2030-01-01T00:00:00'},
        {**request,'route_digest':'0'*64}]
    for value in invalid:
        response=confirm(client,configured,value)
        assert response.status_code==422,response.text
        assert counts(db_session)==(0,0)
    wrong=confirm(client,type('Lab',(),{'id':uuid4()})(),request)
    assert wrong.status_code==404,wrong.text
    assert confirm(client,configured,{**request,'expected_current_application_id':str(uuid4())}).status_code==409
    topology_two_chains.connections=[{**edge,**({'ce_port':'B3'} if edge['id']=='conn_p0v' else {})}
        for edge in topology_two_chains.connections]
    db_session.commit()
    assert confirm(client,configured,request).status_code==422
    assert counts(db_session)==(0,0)


def test_mock_capture_cannot_be_confirmed(client,configured,db_session):
    from app.models.diagnostic_run import DiagnosticRun
    from uuid import UUID
    response=start(client,configured);value=finish(client,configured,response.json()['run_id'])
    row=db_session.get(DiagnosticRun,UUID(value['run_id']))
    response=confirm(client,configured,payload(client,configured,row))
    assert response.status_code==422,response.text
    assert counts(db_session)==(0,0)


@pytest.mark.parametrize('seeded',[False,True])
def test_parallel_confirmation_has_one_winner(client,configured,real_capture,db_session,seeded):
    row=real_capture();request=payload(client,configured,row)
    if seeded:
        assert confirm(client,configured,request).status_code==201
        request=payload(client,configured,row)
    factory=sessionmaker(bind=db_session.get_bind(),expire_on_commit=False)
    def independent_db():
        with factory() as db:
            yield db
    previous=app.dependency_overrides[get_db]
    app.dependency_overrides[get_db]=independent_db
    barrier=Barrier(2)
    def send():
        barrier.wait(timeout=10)
        return confirm(client,configured,{**request,'idempotency_key':str(uuid4())})
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses=list(pool.map(lambda _:send(),range(2)))
    finally:
        app.dependency_overrides[get_db]=previous
    assert sorted(response.status_code for response in responses)==[201,409],[r.text for r in responses]
    assert counts(db_session)==(2 if seeded else 1,1)


def test_confirmation_write_failure_rolls_back_and_old_history_does_not_drift(client,configured,real_capture,db_session):
    row=real_capture();request=payload(client,configured,row)
    engine=db_session.get_bind()
    def fail_pointer(connection,cursor,statement,parameters,context,executemany):
        if statement.startswith('INSERT INTO route_calibration_selections'):
            raise RuntimeError('test storage failure')
    event.listen(engine,'before_cursor_execute',fail_pointer)
    try:
        with pytest.raises(RuntimeError,match='test storage failure'):
            confirm(client,configured,request)
    finally:
        event.remove(engine,'before_cursor_execute',fail_pointer)
    assert counts(db_session)==(0,0)
    response=confirm(client,configured,request)
    assert response.status_code==201,response.text
    saved=response.json()
    changed=copy.deepcopy(row.sequence_evidence)
    changed['extra']['fixed_route_acquisition']['status']='simulated'
    row.sequence_evidence=changed;db_session.commit()
    history=client.get(f'/api/v1/lab-profiles/{configured.id}/route-calibration-applications',
        params={'topology_id':saved['selection_snapshot']['topology_id'],'chain_id':'conn_p0v'})
    assert history.json()==[saved]
    # 确认记录是追加式审计记录，不能原位改值。
    from app.models.route_calibration import RouteCalibrationApplication
    stored=db_session.query(RouteCalibrationApplication).one()
    stored.record={**stored.record,'net_loss_db':999}
    with pytest.raises(ValueError,match='不可修改'):
        db_session.commit()
    db_session.rollback()
    assert counts(db_session)==(1,1)


@pytest.mark.parametrize('operation',['delete','replace','chamber'])
def test_topology_with_adoption_history_cannot_be_hard_deleted(client,configured,real_capture,db_session,
        topology_two_chains,operation,monkeypatch):
    from fastapi.testclient import TestClient
    row=real_capture()
    saved=confirm(client,configured,payload(client,configured,row)).json()
    topology_id=topology_two_chains.id
    category_id=topology_two_chains.switch_category_id
    lab_id=configured.id
    old_chamber_id=topology_two_chains.chamber_id
    original_graph=json.dumps([topology_two_chains.nodes,topology_two_chains.connections,
                               topology_two_chains.operating_modes],sort_keys=True)
    if operation=='replace':
        from app.api import switch_topology as api
        def unexpected_delete_precheck(*args):
            pytest.fail('已有库模板覆盖应在删除预检前拒绝')
        monkeypatch.setattr(api,'assert_route_topologies_deletable',unexpected_delete_precheck)
    if operation=='chamber':
        from app.models.chamber import ChamberConfiguration,create_chamber_from_preset
        db_session.get(ChamberConfiguration,old_chamber_id).is_system_preset=False
        replacement=create_chamber_from_preset('type_c',name='改绑后的暗室')
        db_session.add(replacement);db_session.flush()
        configured.chamber_config_id=replacement.id
    db_session.commit()
    db_session.execute(text('PRAGMA foreign_keys=ON'))
    assert db_session.execute(text('PRAGMA foreign_keys')).scalar()==1
    # 外部故障也以HTTP响应观察，避免客户端重抛异常掩盖实际500。
    http=TestClient(app,raise_server_exceptions=False)
    try:
        if operation=='delete':
            response=http.delete(f'/api/v1/switch-topologies/{topology_id}',params={'lab_profile_id':str(lab_id)})
        elif operation=='replace':
            response=http.post('/api/v1/switch-topologies/import/from-template',params={
                'lab_profile_id':str(lab_id),'switch_category_id':str(category_id),
                'template_id':'caict_v4','replace_existing':True})
        else:
            response=http.delete(f'/api/v1/chambers/{old_chamber_id}')
        assert response.status_code==409,response.text
        assert ('不能覆盖导入' if operation=='replace' else '采用') in response.json()['detail']
    finally:
        http.close()
        db_session.rollback()
    assert counts(db_session)==(1,1)
    from app.models.switch_topology import SwitchTopology
    preserved=db_session.get(SwitchTopology,topology_id)
    assert preserved is not None
    if operation=='replace':
        assert json.dumps([preserved.nodes,preserved.connections,preserved.operating_modes],sort_keys=True)==original_graph
    history=client.get(f'/api/v1/lab-profiles/{lab_id}/route-calibration-applications',
        params={'topology_id':str(topology_id),'chain_id':'conn_p0v'})
    assert history.json()==[saved]


@pytest.mark.parametrize('winner_kind',['same','other_key','other_payload'])
def test_interleaved_idempotent_confirmation_rechecks_after_business_conflict(client,configured,real_capture,
        db_session,monkeypatch,winner_kind):
    from app.services.calibration import route_calibration as service
    from app.schemas.route_calibration import ConfirmRouteApplication
    row=real_capture();request=payload(client,configured,row)
    original=service._replay
    factory=sessionmaker(bind=db_session.get_bind(),expire_on_commit=False)
    winner=[]
    def interleave(db,lab_id,body):
        value=original(db,lab_id,body)
        if db is db_session and value is None and not winner:
            # A读到无幂等记录后，B用独立会话完整确认。只控制交错，不mock评估。
            other=dict(request)
            if winner_kind=='other_key':
                other['idempotency_key']=str(uuid4())
            elif winner_kind=='other_payload':
                other['adoption_valid_until']=(datetime.now(timezone.utc)+timedelta(days=2)).isoformat()
            with factory() as second:
                record,created=service.confirm_route_application(second,lab_id,
                    ConfirmRouteApplication.model_validate(other),actor=None)
                assert created is True
                winner.append(record.model_dump(mode='json'))
        return value
    monkeypatch.setattr(service,'_replay',interleave)
    response=confirm(client,configured,request)
    if winner_kind=='same':
        assert response.status_code==200,response.text
        assert response.json()==winner[0]
    else:
        assert response.status_code==409,response.text
    assert counts(db_session)==(1,1)


@pytest.mark.parametrize('operation',['delete','replace'])
@pytest.mark.parametrize('constraint',['adoption_before_locked_precheck','unrelated_dependency'])
def test_delete_race_and_unrelated_constraint_are_distinguished(client,configured,real_capture,db_session,
        topology_two_chains,monkeypatch,operation,constraint):
    from fastapi.testclient import TestClient
    from app.api import switch_topology as api
    from app.services.calibration import route_calibration as service
    from app.schemas.route_calibration import ConfirmRouteApplication
    from app.models.switch_topology import SwitchTopology
    row=real_capture();request=payload(client,configured,row)
    topology_id=topology_two_chains.id
    category_id=topology_two_chains.switch_category_id
    lab_id=configured.id
    original_graph=json.dumps([topology_two_chains.nodes,topology_two_chains.connections,
                               topology_two_chains.operating_modes],sort_keys=True)
    # 启用整个临时连接池，避免负例DDL提交换连接后意外关闭外键检查。
    def foreign_keys_on(connection,record,proxy):
        connection.execute('PRAGMA foreign_keys=ON')
    event.listen(db_session.get_bind(),'checkout',foreign_keys_on)
    db_session.commit()
    db_session.execute(text('PRAGMA foreign_keys=ON'))
    assert db_session.execute(text('PRAGMA foreign_keys')).scalar()==1
    winner=[]
    if constraint=='adoption_before_locked_precheck':
        original=api.lock_chamber
        factory=sessionmaker(bind=db_session.get_bind(),expire_on_commit=False)
        def interleave(db,chamber_id):
            # PC04A5b锁后SQLite其它写者不能先提交；真实采用先赢，再锁内预检拒删除。
            assert not winner
            with factory() as second:
                second.execute(text('PRAGMA foreign_keys=ON'))
                record,created=service.confirm_route_application(second,lab_id,
                    ConfirmRouteApplication.model_validate(request),actor=None)
                assert created is True
                winner.append(record.model_dump(mode='json'))
            return original(db,chamber_id)
        if operation=='delete':
            monkeypatch.setattr(api,'lock_chamber',interleave)
        else:
            def unexpected_delete_precheck(*args):
                pytest.fail('已有库模板覆盖不应进入删除预检')
            monkeypatch.setattr(api,'assert_route_topologies_deletable',unexpected_delete_precheck)
    else:
        # 另一种真实外键约束，不属于采用记录；不得被转成采用冲突。
        db_session.execute(text('CREATE TABLE other_reference (topology_id UUID REFERENCES switch_topologies(id))'))
        db_session.execute(text('INSERT INTO other_reference VALUES (:id)'),{'id':topology_id.hex})
        db_session.commit()
        if operation=='replace':
            def unexpected_delete_precheck(*args):
                pytest.fail('已有库模板覆盖不应进入删除预检或外键删除')
            monkeypatch.setattr(api,'assert_route_topologies_deletable',unexpected_delete_precheck)
    http=TestClient(app,raise_server_exceptions=False)
    try:
        if operation=='delete':
            response=http.delete(f'/api/v1/switch-topologies/{topology_id}',params={'lab_profile_id':str(lab_id)})
        else:
            response=http.post('/api/v1/switch-topologies/import/from-template',params={
                'lab_profile_id':str(lab_id),'switch_category_id':str(category_id),
                'template_id':'caict_v4','replace_existing':True})
        if operation=='replace':
            # PC04A5a：现有库在删除前统一拒绝；这里不再声称验证删除竞态/FK500。
            assert response.status_code==409,response.text
            assert '不能覆盖导入' in response.json()['detail']
            assert not winner
        elif constraint=='adoption_before_locked_precheck':
            assert len(winner)==1
            assert response.status_code==409,response.text
            assert '采用' in response.json()['detail']
        else:
            assert response.status_code==500,response.text
    finally:
        http.close();db_session.rollback()
    preserved=db_session.get(SwitchTopology,topology_id)
    assert preserved is not None
    if operation=='replace':
        assert json.dumps([preserved.nodes,preserved.connections,preserved.operating_modes],sort_keys=True)==original_graph
    assert counts(db_session)==((1,1) if winner else (0,0))
    if winner:
        history=client.get(f'/api/v1/lab-profiles/{lab_id}/route-calibration-applications',
            params={'topology_id':str(topology_id),'chain_id':'conn_p0v'})
        assert history.json()==winner
