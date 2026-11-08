"""PC14：独立SQLite提交与固定交错；不连接仪器，不靠延时争抢。"""
import asyncio
import copy
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.db.database import Base
from app.models.diagnostic_run import DiagnosticRun
from app.models.lab_profile import LabProfile
from app.schemas.fixed_route_acquisition import FixedRouteRequest, FixedRouteResult
from app.services.calibration import fixed_route_jobs as single, route_batch_jobs as batch
from app.api import fixed_route_acquisition as single_api, route_batch as batch_api


@pytest.fixture
def store(tmp_path, monkeypatch):
    engine = create_engine(f'sqlite:///{tmp_path / "read-race.db"}')
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)
    monkeypatch.setattr(single, 'SessionLocal', factory)
    monkeypatch.setattr(batch, 'SessionLocal', factory)
    monkeypatch.setattr(single, '_running', {})
    monkeypatch.setattr(batch, '_running', {})
    with factory() as db:
        lab = LabProfile(name='PC14 isolated')
        db.add(lab); db.commit()
        yield SimpleNamespace(db=db, factory=factory, lab=lab, engine=engine)
    engine.dispose()


def seed(store, *, parent=False):
    request = FixedRouteRequest(chain_id='route', configuration_digest='a'*64,
        frequency_mhz=3500., requested_power_dbm=-20., reference_antenna='REF',
        receive_cable_loss_db=2., receive_cable_source='synthetic',
        fixed_route_confirmed=True, safety_confirmed=True, sample_count=2)
    result = FixedRouteResult(run_id=uuid4(), lab_profile_id=store.lab.id,
        request=request, configuration={})
    value = None
    if parent:
        job_id = uuid4()
        result.states.update(batch_job_id=str(job_id), batch_item_id='item', lease_id='lease')
        value = dict(job_id=str(job_id), lab_id=str(store.lab.id), status='running',
            current_index=0, transition_id='transition', cancel_requested=False,
            lease_id='lease', finalization_id=None, finalization_committed=False,
            persistence_failed=False, all_started_cleanup_confirmed=None, f64_control_released=None,
            plan=dict(lab_profile_id=str(store.lab.id), topology_id=str(uuid4()),
                items=[], preview_digest='a'*64),
            items=[dict(item_id='item', run_id=str(result.run_id), status='measuring',
                request=request.model_dump(mode='json'))])
        row = DiagnosticRun(id=job_id, lab_profile_id=store.lab.id,
            target_name=batch.TARGET, kind='scpi_sequence', success=False)
        batch._save_parent(row, value); store.db.add(row)
        batch._running[job_id] = batch.RunningBatch()
    else:
        single._running[result.run_id] = (None, asyncio.Event())
    child = single.build_record_row(result)
    store.db.add(child); store.db.commit()
    # 保留调用者的旧身份映射，模拟先读running的请求。
    return result, value, child


def finish(store, result, value=None, *, status='cancelled', persist=True, simulated=False):
    result.status = status
    result.cleanup_confirmed = None if simulated else True
    result.states['f64_control_released'] = not simulated
    if simulated:
        result.simulation_input_source = 'model_synthetic'
    if value is not None:
        value.update(status='cancelled' if status=='cancelled' else 'completed',
            finalization_id='final', finalization_committed=True, persistence_failed=False,
            f64_control_released=not simulated, all_started_cleanup_confirmed=not simulated)
        value['items'][0]['status'] = status
        result.states['batch_finalization_id'] = 'final'
    if persist:
        with store.factory() as writer:
            single.save_record_result(writer.get(DiagnosticRun, result.run_id), result)
            if value is not None:
                batch._save_parent(writer.get(DiagnosticRun, uuid_from(value['job_id'])), value)
            writer.commit()
    if value is None:
        single._running.pop(result.run_id)
    else:
        batch._running.pop(uuid_from(value['job_id']))


def uuid_from(value):
    from uuid import UUID
    return UUID(value)


def read_single(store, result, endpoint):
    if endpoint == 'history':
        return single_api.history(store.lab.id, 20, store.db)[0]
    return single_api.progress(store.lab.id, result.run_id, store.db)


def read_batch(store, value, endpoint):
    if endpoint == 'history':
        return batch_api.history(store.lab.id, 20, store.db)[0]
    return batch_api.progress(store.lab.id, uuid_from(value['job_id']), store.db)


@pytest.mark.parametrize('endpoint', ['progress', 'history'])
@pytest.mark.parametrize('status', ['cancelled', 'completed', 'simulated', 'cleanup_unconfirmed'])
def test_single_committed_terminal_beats_callers_stale_running(store, endpoint, status):
    result, _, stale = seed(store)
    finish(store, result, status=status, simulated=status=='simulated')
    response = read_single(store, result, endpoint)
    assert response.status == status
    assert stale.sequence_evidence['extra']['fixed_route_acquisition']['status'] == 'running'


@pytest.mark.parametrize('endpoint', ['progress', 'history'])
def test_batch_parent_and_child_read_same_committed_finalization(store, endpoint):
    result, value, stale = seed(store, parent=True)
    parent = store.db.get(DiagnosticRun, uuid_from(value['job_id']))
    finish(store, result, value)
    response = read_batch(store, value, endpoint)
    child = read_single(store, result, endpoint)
    assert response.status == 'cancelled'
    assert response.finalization_committed is True
    assert child.status == 'cancelled'
    assert child.batch_context.finalized is True
    assert child.result.states['batch_finalization_verified'] is True
    assert parent.sequence_evidence['extra'][batch.TARGET]['status'] == 'running'
    assert stale.sequence_evidence['extra']['fixed_route_acquisition']['status'] == 'running'


@pytest.mark.parametrize('parent', [False, True])
def test_final_commit_between_select_and_parse_never_invents_interruption(store, monkeypatch, parent):
    result, value, _ = seed(store, parent=parent)
    module = batch if parent else single
    original = module.record
    fired = False
    def interleaved(*args, **kwargs):
        nonlocal fired
        if not fired:
            fired = True
            finish(store, result, value)
        return original(*args, **kwargs)
    monkeypatch.setattr(module, 'record', interleaved)
    response = read_batch(store, value, 'progress') if parent else read_single(store, result, 'progress')
    assert fired
    assert response.status in ('running', 'cancelled')  # 不能把旧快照与退出拼成中断。


@pytest.mark.parametrize('parent', [False, True])
@pytest.mark.parametrize('persist', [False, True])
def test_orphan_and_failed_final_save_remain_interrupted(store, parent, persist):
    result, value, _ = seed(store, parent=parent)
    if persist:  # 模拟进程消失：数据库只有原始running。
        (batch._running if parent else single._running).clear()
    else:
        finish(store, result, value, persist=False)
    response = read_batch(store, value, 'progress') if parent else read_single(store, result, 'progress')
    assert response.status == 'interrupted'
    child = read_single(store, result, 'progress')
    assert child.status == 'interrupted'
    assert child.result.cleanup_confirmed is None and child.result.net_loss_db is None
    if parent:
        assert child.batch_context.finalized is False
        assert response.finalization_committed is False


@pytest.mark.parametrize('parent', [False, True])
async def test_cancel_response_reads_after_action_without_reusing_old_row(store, monkeypatch, parent):
    result, value, _ = seed(store, parent=parent)
    module = batch if parent else single
    def cancel(_):
        finish(store, result, value)
    monkeypatch.setattr(module, 'request_cancel', cancel)
    response = (await batch_api.cancel(store.lab.id, uuid_from(value['job_id']), store.db)
                if parent else await single_api.cancel(store.lab.id, result.run_id, store.db))
    assert response.status == 'cancelled'


async def test_continue_response_reads_after_action(store, monkeypatch):
    from app.schemas.route_batch import BatchContinueRequest
    result, value, _ = seed(store, parent=True)
    parent = store.db.get(DiagnosticRun, uuid_from(value['job_id']))
    def resume(*args, **kwargs):
        finish(store, result, value, status='completed')
    monkeypatch.setattr(batch, 'continue_job', resume)
    request = BatchContinueRequest(item_id='item', transition_id='transition',
        reference_antenna='REF', manual_confirmed=True)
    response = await batch_api.continue_job(store.lab.id, parent.id, request, store.db)
    assert response.status == 'completed'


def test_completed_batch_child_refreshes_parent_and_child_final_markers_together(store, monkeypatch):
    result, value, stale = seed(store, parent=True)
    result.status = 'completed'
    result.cleanup_confirmed = True
    single.save_record_result(stale, result); store.db.commit()
    parent = store.db.get(DiagnosticRun, uuid_from(value['job_id']))
    finish(store, result, value, status='completed')
    seen = []
    original = batch.batch_child_context
    def context(db, row, **kwargs):
        seen.append((db, row))
        return original(db, row, **kwargs)
    monkeypatch.setattr(batch, 'batch_child_context', context)
    response = single.read_record(store.db, stale)
    assert response.status == 'completed'
    assert response.batch_context.finalized is True
    assert response.result.states['batch_finalization_verified'] is True
    assert seen[-1][0] is not store.db
    assert seen[-1][1].sequence_evidence['extra']['fixed_route_acquisition']['states']['batch_finalization_id'] == 'final'
    assert parent.sequence_evidence['extra'][batch.TARGET]['finalization_id'] is None


@pytest.mark.parametrize('parent', [False, True])
def test_read_failure_propagates_and_does_not_return_fake_terminal(store, monkeypatch, parent):
    result, value, _ = seed(store, parent=parent)
    stale_parent = store.db.get(DiagnosticRun, uuid_from(value['job_id'])) if parent else None
    finish(store, result, value)
    def unavailable(): raise RuntimeError('read database unavailable')
    monkeypatch.setattr(batch if parent else single, 'SessionLocal', unavailable)
    with pytest.raises(RuntimeError, match='read database unavailable'):
        if parent: read_batch(store, value, 'progress')
        else: read_single(store, result, 'progress')


def test_read_does_not_commit_rollback_refresh_or_replace_callers_transaction(store):
    result, _, stale = seed(store)
    finish(store, result)
    store.lab.name = 'unflushed caller change'
    transaction = store.db.get_transaction()
    response = read_single(store, result, 'progress')
    assert response.status == 'cancelled'
    assert store.db.get_transaction() is transaction
    assert store.lab in store.db.dirty and store.lab.name == 'unflushed caller change'
    assert stale.sequence_evidence['extra']['fixed_route_acquisition']['status'] == 'running'
    with store.factory() as other:
        assert other.get(LabProfile, store.lab.id).name == 'PC14 isolated'


def test_transaction_parsers_never_open_independent_session(store, monkeypatch):
    from app.services.calibration.route_batch_jobs import BatchItemContext
    result, value, child = seed(store, parent=True)
    parent = store.db.get(DiagnosticRun, uuid_from(value['job_id']))
    def forbidden(): raise AssertionError('事务内解析不得另开会话')
    monkeypatch.setattr(single, 'SessionLocal', forbidden)
    monkeypatch.setattr(batch, 'SessionLocal', forbidden)
    context = batch.batch_child_context(store.db, child)
    assert single.record(child, batch_context=context).status == 'running'
    # 修改仅存在当前未提交事务；校验必须消费它而不是另一个Session的旧running。
    changed = copy.deepcopy(value); changed['status'] = 'cancelled'
    batch._save_parent(parent, changed)
    with pytest.raises(ValueError, match='批已结束'):
        batch.validated_batch_item(store.db, store.lab.id, result.request,
            BatchItemContext(parent.id, 'item'))
    assert parent in store.db.dirty


def test_synthetic_completed_history_cannot_gain_adoption_or_true_cleanup(store):
    from app.services.calibration.fixed_route_evidence import check_fixed_route_evidence
    result, _, _ = seed(store)
    finish(store, result, status='completed', simulated=True)
    response = read_single(store, result, 'progress')
    assert response.status == 'simulated'
    assert response.result.cleanup_confirmed is None
    assert response.formal_eligible is False
    provenance, blockers = check_fixed_route_evidence(response.result)
    assert provenance == 'simulated' and 'simulated_measurement' in blockers


@pytest.mark.parametrize('status', ['running', 'completed'])
def test_denied_old_child_context_does_not_invent_parent_exit(store, status):
    result, value, stale = seed(store, parent=True)
    result.status = status
    result.states['f64_control_released'] = True
    bad = result.model_copy(deep=True)
    bad.states['lease_id'] = 'old-mismatched-lease'
    single.save_record_result(stale, bad); store.db.commit()
    with store.factory() as writer:
        single.save_record_result(writer.get(DiagnosticRun, result.run_id), result)
        writer.commit()
    # 父任务始终活动；旧关联denied不能冒充已观察到退出。
    assert batch.batch_child_context(store.db, stale) == {'active': False, 'finalized': False}
    response = read_single(store, result, 'progress')
    assert response.status == status
    assert response.batch_context.active is True
    assert response.batch_context.finalized is False
    assert response.result.states['f64_control_released'] is None
    assert response.result.states['batch_finalization_verified'] is False


@pytest.mark.parametrize('phase', ['waiting_manual', 'paused_failure'])
def test_inactive_batch_waiting_and_paused_recheck_committed_terminal(store, phase):
    result, value, _ = seed(store, parent=True)
    parent = store.db.get(DiagnosticRun, uuid_from(value['job_id']))
    value['status'] = phase
    batch._save_parent(parent, value); store.db.commit()
    finish(store, result, value)
    assert read_batch(store, value, 'progress').status == 'cancelled'


@pytest.mark.parametrize('parent', [False, True])
def test_only_inactive_read_opens_one_new_session(store, monkeypatch, parent):
    result, value, stale = seed(store, parent=parent)
    stale_parent = store.db.get(DiagnosticRun, uuid_from(value['job_id'])) if parent else None
    module = batch if parent else single
    opened = []
    def counted():
        opened.append(True)
        return store.factory()
    monkeypatch.setattr(module, 'SessionLocal', counted)
    read = lambda: read_batch(store, value, 'progress') if parent else read_single(store, result, 'progress')
    assert read().status == 'running' and opened == []
    finish(store, result, value)
    assert read().status == 'cancelled' and len(opened) == 1
