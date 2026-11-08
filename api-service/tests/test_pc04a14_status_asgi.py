"""真实ASGI线程读取与同loop后台事务交错；屏障不替代commit/pop。"""
import asyncio
import threading
from uuid import UUID

import httpx
import pytest
from sqlalchemy import event

from app.main import app
from app.db.database import get_db
from app.models.diagnostic_run import DiagnosticRun
from app.services.calibration import fixed_route_jobs as single, route_batch_jobs as batch
from tests.test_pc04a14_status_read_race import store
from tests.test_pc04a14_start_ownership import starter, db_session
from tests.test_rf_chain_resolver import chamber, topology_two_chains, lab_profile
from tests.test_pc_04a_fixed_route_api import configured


@pytest.fixture
async def api(store):
    previous = dict(app.dependency_overrides)
    def request_db():
        with store.factory() as db:
            yield db
    app.dependency_overrides[get_db] = request_db
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
            yield client
    finally:
        app.dependency_overrides.clear(); app.dependency_overrides.update(previous)


def root(lab, parent):
    kind = 'route-calibration-batches' if parent else 'fixed-route-acquisitions'
    return f'/api/v1/lab-profiles/{lab.id}/{kind}'


@pytest.mark.parametrize('parent', [False, True])
@pytest.mark.parametrize('endpoint', ['progress', 'history'])
async def test_asgi_thread_old_read_overlaps_real_terminal_commit(api, store, starter, monkeypatch, parent, endpoint):
    module = batch if parent else single
    loop = asyncio.get_running_loop()
    loop_thread = threading.get_ident()
    release = asyncio.Event()
    done = threading.Event()
    execute = module._execute
    async def held_execute(*args):
        await release.wait()
        await execute(*args)
    monkeypatch.setattr(module, '_execute', held_execute)
    started = await starter.start(parent)
    ident = UUID(started['job_id']) if parent else started.run_id
    task = batch._running[ident].task if parent else single._running[ident][0]
    module.request_cancel(ident)
    async def completed():
        await task
        done.set()
    watcher = loop.create_task(completed())
    original = module.record
    observed = []
    def pause_old_read(*args, **kwargs):
        if not observed:
            observed.append(threading.get_ident())
            assert observed[0] != loop_thread, '状态GET必须在线程池，不能阻塞取消事件循环'
            loop.call_soon_threadsafe(release.set)
            assert done.wait(5), '后台任务没有完成真实提交及退出'
        return original(*args, **kwargs)
    monkeypatch.setattr(module, 'record', pause_old_read)
    try:
        url = root(starter.lab, parent) + (f'/{ident}' if endpoint=='progress' else '')
        response = await api.get(url)
        assert response.status_code == 200, response.text
        value = response.json() if endpoint=='progress' else response.json()[0]
        assert value['status'] in ('running', 'cancelled'), value
        assert observed and done.is_set()
        with store.factory() as db:
            row = db.get(DiagnosticRun, ident)
            extra = row.sequence_evidence['extra']
            assert extra[batch.TARGET if parent else 'fixed_route_acquisition']['status'] == 'cancelled'
        final = await api.get(root(starter.lab, parent)+f'/{ident}')
        assert final.json()['status'] == 'cancelled'
    finally:
        release.set()
        await watcher


@pytest.mark.parametrize('parent', [False, True])
async def test_asgi_history_sql_can_overlap_new_start_without_false_orphan(api, store, starter, monkeypatch, parent):
    module = batch if parent else single
    loop = asyncio.get_running_loop()
    loop_thread = threading.get_ident()
    start_go = asyncio.Event()
    execute_go = asyncio.Event()
    registered = threading.Event()
    execute = module._execute
    async def held_execute(*args):
        await execute_go.wait()
        await execute(*args)
    monkeypatch.setattr(module, '_execute', held_execute)
    started = []
    async def producer():
        await start_go.wait()
        started.append(await starter.start(parent))
        registered.set()
    producer_task = loop.create_task(producer())
    intercepted = []
    def before_sql(conn, cursor, statement, parameters, context, executemany):
        if (threading.get_ident() != loop_thread and not intercepted
                and statement.lstrip().upper().startswith('SELECT') and 'diagnostic_runs' in statement):
            intercepted.append(True)
            loop.call_soon_threadsafe(start_go.set)
            assert registered.wait(5), '新任务未完成真实注册与提交'
    event.listen(store.engine, 'before_cursor_execute', before_sql)
    try:
        response = await api.get(root(starter.lab, parent))
        assert response.status_code == 200, response.text
        assert intercepted and registered.is_set()
        assert len(response.json()) == 1
        assert response.json()[0]['status'] == 'running'
    finally:
        event.remove(store.engine, 'before_cursor_execute', before_sql)
        start_go.set()
        await producer_task
        if started:
            ident = UUID(started[0]['job_id']) if parent else started[0].run_id
            task = batch._running[ident].task if parent else single._running[ident][0]
            module.request_cancel(ident)
            execute_go.set()
            await task
