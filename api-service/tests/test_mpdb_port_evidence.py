import io
import json
import zipfile

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import mpdb_projects as projects


def zipped(name, data):
    out = io.BytesIO()
    with zipfile.ZipFile(out, 'w') as archive:
        archive.writestr(name, data)
    return out.getvalue()


app = FastAPI()
app.include_router(projects.router)
client = TestClient(app)
url = '/channel-assets/mpdb-projects/port-evidence'
source = zipped('R0B0S0D.mpdb', zipped('mpdb.json', b'{}'))


@pytest.mark.parametrize('changes', [
    {'points': '2'}, {'points': '4'}, {'points': '259'}, {'bandwidth_mhz': '10001'}, {'amplitude_floor': '0'}, {'bandwidth_mhz': '0'}, {'amplitude_floor': '-1'},
])
def test_invalid_parameters(changes):
    response = client.post(url, files={'archive': ('input.zip', source)},
                           data={'points': '3', 'bandwidth_mhz': '20', **changes})
    assert response.status_code == 422


def test_read_only_report_with_optional_floor(tmp_path, monkeypatch):
    from pathlib import Path
    report = {'status': 'partial', 'message': '成员记录缺失', 'summary': ['部分未核验'],
              'frames': [], 'parameters': {'points': 3}}
    scripts = tmp_path / 'scripts'
    scripts.mkdir()
    (scripts / 'mpdb_port_evidence.py').touch()
    monkeypatch.setattr(projects, 'ROOT', tmp_path)
    monkeypatch.setattr(projects, 'worker_environment', lambda root: {})
    def worker(command, env):
        assert '--members' not in command
        assert command[command.index('--amplitude-floor') + 1] == '0.01'
        assert Path(command[command.index('--expected') + 1]).read_text() == '{}'
        Path(command[command.index('--output') + 1]).write_text(json.dumps(report))
        return 0, ''
    monkeypatch.setattr(projects, 'run_worker', worker)
    response = client.post(url, files={'archive': ('../../input.zip', source),
                                       'expected': ('results.json', '{}')},
                           data={'points': 3, 'bandwidth_mhz': 20, 'amplitude_floor': .01})
    assert response.status_code == 200
    assert response.json() == report
    assert 'attachment' in response.headers['content-disposition']
