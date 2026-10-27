"""Task4证据插件：真实TestClient HTTP与隔离SQLite前后快照，不替换响应。"""
import hashlib
import json
import os
from pathlib import Path

import pytest


def pytest_configure(config):
    target = os.environ.get('PC04A4D_EVIDENCE_DIR')
    if not target:
        return
    from starlette.testclient import TestClient
    output = Path(target)
    output.mkdir(parents=True, exist_ok=True)
    original = TestClient.request

    def request(self, method, url, *args, **kwargs):
        response = original(self, method, url, *args, **kwargs)
        try:
            body = response.json()
        except ValueError:
            body = response.text
        with (output / 'http.jsonl').open('a') as stream:
            stream.write(json.dumps(dict(test=os.environ.get('PYTEST_CURRENT_TEST'),
                method=method, url=str(response.url), request=kwargs.get('json'),
                status=response.status_code, response=body), ensure_ascii=False, default=str)+'\n')
        return response
    TestClient.request = request


def snapshot():
    from sqlalchemy import inspect, text
    from app.db.database import engine
    assert engine.dialect.name == 'sqlite' and str(engine.url).startswith('sqlite:////tmp/')
    result = {}
    with engine.connect() as connection:
        tables = set(inspect(connection).get_table_names())
        for table in ('switch_topologies', 'test_executions', 'calibration_certificates',
                      'route_calibration_applications', 'configuration_baselines'):
            if table in tables:
                rows = [dict(row) for row in connection.execute(text(f'SELECT * FROM "{table}"')).mappings()]
                result[table] = sorted(rows, key=lambda row: str(row.get('id')))
    return result


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_call(item):
    target = os.environ.get('PC04A4D_EVIDENCE_DIR')
    if not target:
        yield
        return
    before = snapshot()
    yield
    after = snapshot()
    name = hashlib.sha256(item.nodeid.encode()).hexdigest()[:16]
    Path(target, name+'.json').write_text(json.dumps(dict(test=item.nodeid,
        before=before, after=after), ensure_ascii=False, default=str, indent=2))
