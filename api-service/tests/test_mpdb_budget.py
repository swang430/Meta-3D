import io
import json
from pathlib import Path
import zipfile

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.api import mpdb_projects as projects

app=FastAPI()
app.include_router(projects.router)
client=TestClient(app)
URL='/channel-assets/mpdb-projects/budget-comparisons'

@pytest.mark.parametrize('change',[{'points':4},{'points':259},{'amplitude_floor':0},{'bandwidth_mhz':10001}])
def test_invalid_parameters(change):
    response=client.post(URL,files={k:(k,b'bad') for k in ('archive','members')},
        data={'points':41,'bandwidth_mhz':100,'amplitude_floor':1e-8,**change})
    assert response.status_code == 422


def test_report_and_downloads(tmp_path,monkeypatch):
    scripts=tmp_path/'scripts'
    scripts.mkdir()
    (scripts/'mpdb_budget.py').touch()
    monkeypatch.setattr(projects,'ROOT',tmp_path)
    monkeypatch.setattr(projects,'storage',lambda:tmp_path)
    monkeypatch.setattr(projects,'worker_environment',lambda root:{'HYPERRT_PATH':'not-allowed'})
    def worker(command,env):
        assert 'HYPERRT_PATH' not in env
        output=Path(command[command.index('--output')+1])
        output.mkdir()
        (output/'summary.json').write_text(json.dumps({'schema':'mpdb-budget/1','formal_verdict':None,'alignment_status':'unverified','summary':{}}))
        (output/'report.json').write_text('{}')
        (output/'points.csv').write_text('frame,method\n0,Meta-3D\n')
        return 0,''
    monkeypatch.setattr(projects,'run_worker',worker)
    response=client.post(URL,files={k:('../../'+k,b'bytes') for k in ('archive','members')})
    assert response.status_code == 200, response.text
    body=response.json()
    assert body['formal_verdict'] is None
    for key,content in [('points_url',b'frame,method'),('download_url',b'PK')]:
        result=client.get(body[key].removeprefix('/api/v1'))
        assert result.status_code == 200
        assert result.content.startswith(content)
    assert client.get(URL+'/not-an-id/points.csv').status_code == 422


def test_worker_failure_does_not_publish(tmp_path,monkeypatch):
    (tmp_path/'scripts').mkdir()
    (tmp_path/'scripts/mpdb_budget.py').touch()
    monkeypatch.setattr(projects,'ROOT',tmp_path)
    monkeypatch.setattr(projects,'storage',lambda:tmp_path)
    monkeypatch.setattr(projects,'worker_environment',lambda root:{})
    monkeypatch.setattr(projects,'run_worker',lambda *a,**k:(1,'source mismatch'))
    result=client.post(URL,files={k:(k,b'bytes') for k in ('archive','members')})
    assert result.status_code == 422
    assert not list(tmp_path.glob('budget-comparison-*.zip'))


def test_authoritative_openapi_matches_budget_routes_and_referenced_schemas():
    import yaml
    documented=yaml.safe_load((Path(__file__).resolve().parents[2]/'api/openapi.yaml').read_text())
    live_app=FastAPI()
    live_app.include_router(projects.router,prefix='/api/v1')
    live=live_app.openapi()
    paths=[f'/api/v1{URL}',f'/api/v1{URL}/{{comparison_id}}/{{artifact}}']
    refs=set()
    def collect(value):
        if isinstance(value,dict):
            if '$ref' in value: refs.add(value['$ref'].rsplit('/',1)[-1])
            for item in value.values(): collect(item)
        elif isinstance(value,list):
            for item in value: collect(item)
    for path in paths:
        assert path in documented['paths'],f'权威契约缺少 {path}'
        assert documented['paths'][path]==live['paths'][path]
        collect(live['paths'][path])
    checked=set()
    while refs-checked:
        name=next(iter(refs-checked));checked.add(name)
        assert documented['components']['schemas'][name]==live['components']['schemas'][name]
        collect(live['components']['schemas'][name])
