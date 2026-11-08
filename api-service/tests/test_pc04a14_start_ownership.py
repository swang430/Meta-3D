"""PC14：真实启动事务的注册次序、失败清理及提交后生命周期归属。"""
import asyncio
from types import SimpleNamespace
from uuid import uuid4

import pytest
from app.models.diagnostic_run import DiagnosticRun
from app.hal.channel_emulator import MockChannelEmulator
from app.hal.signal_analyzer import MockSignalAnalyzer
from app.services.calibration import fixed_route_jobs as single, route_batch_jobs as batch
from app.services.calibration.route_batch_plan import build_batch_plan
from app.services.execution_exclusion_guard import active_unsafe_diagnostic
from tests.test_pc04a14_status_read_race import store, uuid_from
from tests.test_rf_chain_resolver import chamber, topology_two_chains, lab_profile
from tests.test_pc_04a_fixed_route_api import configured
from tests.test_pc06a1_batch_plan import request_for


@pytest.fixture
def db_session(store):
    return store.db


@pytest.fixture
async def starter(store, configured, topology_two_chains, monkeypatch):
    hal = SimpleNamespace(drivers={'channelEmulator': MockChannelEmulator('ce', {}),
        'signalAnalyzer': MockSignalAnalyzer('sa', {})})
    for module in (single, batch):
        monkeypatch.setattr(module, 'get_hal_service', lambda: hal)
    request = request_for(topology_two_chains, chains=('conn_p0v',), frequencies=(2595.,))
    plan = build_batch_plan(store.db, configured.id, request, hal)
    request = request.model_copy(update={'preview_digest': plan.preview_digest})
    from app.services.calibration.configuration_scope import build_calibration_scope
    single_request = plan.items[0].request.model_copy(update={'configuration_digest':
        build_calibration_scope(store.db, configured.id, 'mimo_ota', topology_id=topology_two_chains.id).digest})
    created = []
    actual_create_task = asyncio.create_task
    def tracked_create(coro, *args, **kwargs):
        task = actual_create_task(coro, *args, **kwargs)
        created.append(task)
        return task
    monkeypatch.setattr(asyncio, 'create_task', tracked_create)
    async def start(parent):
        if parent:
            return await batch.start(store.db, configured.id, request, idempotency_key=uuid4())
        return await single.start(store.db, configured.id, single_request)
    yield SimpleNamespace(start=start, tasks=created, lab=configured)
    # 测试失败也要释放真实协调器持有的互斥；不触发仪器工作。
    for _, cancel in list(single._running.values()): cancel.set()
    for active in list(batch._running.values()): active.cancel.set(); active.resume.set()
    if created:
        await asyncio.gather(*created, return_exceptions=True)


@pytest.mark.parametrize('parent', [False, True])
async def test_running_commit_is_never_visible_without_registered_task(store, starter, monkeypatch, parent):
    module = batch if parent else single
    original = store.db.commit
    observed = []
    def commit_and_observe():
        original()
        with store.factory() as reader:
            rows = reader.query(DiagnosticRun).filter_by(target_name=module.TARGET).all()
            assert rows
            for row in rows:
                observed.append(row.id)
                assert row.id in module._running, 'running提交可见时，必须已注册任务'
                if parent:
                    assert batch.record(reader, row)['status'] == 'running'
                else:
                    assert single.record(row).status == 'running'
        assert all(not task.done() for task in starter.tasks)
    monkeypatch.setattr(store.db, 'commit', commit_and_observe)
    await starter.start(parent)
    assert observed
    if parent: batch.request_cancel(observed[0])
    else: single.request_cancel(observed[0])
    await starter.tasks[-1]
    assert not module._running and active_unsafe_diagnostic() is None


@pytest.mark.parametrize('parent', [False, True])
async def test_start_commit_failure_cancels_unstarted_task_and_releases_guard(store, starter, monkeypatch, parent):
    module = batch if parent else single
    def fail():
        raise RuntimeError('start commit failed')
    with monkeypatch.context() as patch:
        patch.setattr(store.db, 'commit', fail)
        with pytest.raises(RuntimeError, match='start commit failed'):
            await starter.start(parent)
    await asyncio.gather(*starter.tasks, return_exceptions=True)
    assert not module._running and active_unsafe_diagnostic() is None
    assert len(starter.tasks) == 1
    assert all(task.cancelled() for task in starter.tasks)
    with store.factory() as reader:
        assert reader.query(DiagnosticRun).count() == 0
    # 失败后同上下文可立即重新进入，最终落盘由真实_execute完成。
    value = await starter.start(parent)
    ident = uuid_from(value['job_id']) if parent else value.run_id
    module.request_cancel(ident)
    await starter.tasks[-1]
    assert not module._running and active_unsafe_diagnostic() is None


@pytest.mark.parametrize('parent,stage', [(False,'record'), (True,'record'), (False,'refresh')])
async def test_committed_job_keeps_guard_if_response_parsing_fails(store, starter, monkeypatch, parent, stage):
    module = batch if parent else single
    def fail(*args, **kwargs):
        raise RuntimeError('response failed')
    with monkeypatch.context() as patch:
        patch.setattr(module if stage=='record' else store.db, stage, fail)
        with pytest.raises(RuntimeError, match='response failed'):
            await starter.start(parent)
    assert len(module._running) == 1
    ident = next(iter(module._running))
    task = module._running[ident].task if parent else module._running[ident][0]
    try:
        assert active_unsafe_diagnostic() == module.TARGET
        with pytest.raises(single.AcquisitionBusy):
            await starter.start(parent)
    finally:
        module.request_cancel(ident)
        await task
    assert not module._running and active_unsafe_diagnostic() is None


@pytest.mark.parametrize('parent', [False, True])
async def test_three_cancelled_runs_release_and_reenter_without_false_interruption(store, starter, parent):
    from app.api import fixed_route_acquisition as one_api, route_batch as many_api
    module = batch if parent else single
    for _ in range(3):
        value = await starter.start(parent)
        ident = uuid_from(value['job_id']) if parent else value.run_id
        module.request_cancel(ident)
        await starter.tasks[-1]
        response = (many_api.progress(starter.lab.id, ident, store.db) if parent else
                    one_api.progress(starter.lab.id, ident, store.db))
        assert response.status == 'cancelled'
        assert not module._running and active_unsafe_diagnostic() is None


@pytest.mark.parametrize('parent', [False, True])
async def test_real_final_commit_failure_releases_but_preserves_orphan(store, starter, monkeypatch, caplog, parent):
    from app.api import fixed_route_acquisition as one_api, route_batch as many_api
    module = batch if parent else single
    # 进程内迁移的fileConfig默认禁用已有logger；仅隔离本次捕获，测试后恢复。
    monkeypatch.setattr(module.logger, 'disabled', False)
    monkeypatch.setattr(module.logger, 'propagate', True)
    value = await starter.start(parent)
    ident = uuid_from(value['job_id']) if parent else value.run_id
    module.request_cancel(ident)
    def failed_session():
        db = store.factory()
        def fail(): raise RuntimeError('final commit failed')
        db.commit = fail
        return db
    with monkeypatch.context() as patch:
        patch.setattr(module, 'SessionLocal', failed_session)
        await starter.tasks[-1]
    assert 'final commit failed' in caplog.text
    assert not module._running and active_unsafe_diagnostic() is None
    response = (many_api.progress(starter.lab.id, ident, store.db) if parent else
                one_api.progress(starter.lab.id, ident, store.db))
    assert response.status == 'interrupted'
    if parent: assert response.finalization_committed is False
    else: assert response.result.cleanup_confirmed is None
