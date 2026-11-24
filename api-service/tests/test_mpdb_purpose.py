import json
from pathlib import Path
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.api import mpdb_projects as projects

app=FastAPI(); app.include_router(projects.router)
client=TestClient(app)
URL='/channel-assets/mpdb-projects/purpose-evaluations'

def test_purpose_route_validates_frozen_plan(monkeypatch):
    monkeypatch.setattr(projects,'worker_environment',lambda root:{})
    def forbidden(*args,**kwargs):raise AssertionError('不应扫描重叠源帧计划')
    monkeypatch.setattr(projects,'run_worker',forbidden)
    r=client.post(URL,files={k:(k,b'bad') for k in ('archive','members')},data={'selection_end':26,'holdout_start':26})
    assert r.status_code==422

@pytest.mark.parametrize('change',[{'points':4},{'tap_budget_max':0},{'matrix_nmse_p95_max':-1},{'objective':'unknown'},{'mode':'unknown'}])
def test_invalid_purpose_settings(change):
    r=client.post(URL,files={k:(k,b'bad') for k in ('archive','members')},data=change)
    assert r.status_code==422

def test_purpose_report_download_and_frozen_arguments(tmp_path,monkeypatch):
    (tmp_path/'scripts').mkdir(); (tmp_path/'scripts/mpdb_purpose.py').touch()
    monkeypatch.setattr(projects,'ROOT',tmp_path)
    monkeypatch.setattr(projects,'storage',lambda:tmp_path)
    monkeypatch.setattr(projects,'worker_environment',lambda root:{'HYPERRT_PATH':'forbidden'})
    def worker(command,env):
        assert 'HYPERRT_PATH' not in env
        assert command[command.index('--selection-end')+1]=='25'
        assert command[command.index('--holdout-start')+1]=='26'
        out=Path(command[command.index('--output')+1]); out.mkdir()
        summary={'schema':'mpdb-purpose/1','formal_verdict':None,'alignment_status':'unverified','hardware_verified':False,'status':'no_candidate'}
        (out/'summary.json').write_text(json.dumps(summary)); (out/'report.json').write_text(json.dumps(summary))
        (out/'points.csv').write_text('frame,partition\n37,holdout\n')
        return 0,''
    monkeypatch.setattr(projects,'run_worker',worker)
    r=client.post(URL,files={k:(k,b'bad') for k in ('archive','members')})
    assert r.status_code==200,r.text
    assert r.json()['status']=='no_candidate'
    for field in ('download_url','points_url'):
        assert client.get(r.json()[field].removeprefix('/api/v1')).status_code==200


def test_authoritative_openapi_matches_purpose_routes_and_referenced_schemas():
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


@pytest.mark.parametrize('failure',['worker','missing_artifact','formal_verdict'])
def test_failed_or_incomplete_analysis_never_publishes(tmp_path,monkeypatch,failure):
    (tmp_path/'scripts').mkdir(); (tmp_path/'scripts/mpdb_purpose.py').touch()
    monkeypatch.setattr(projects,'ROOT',tmp_path)
    monkeypatch.setattr(projects,'storage',lambda:tmp_path)
    monkeypatch.setattr(projects,'worker_environment',lambda root:{})
    def worker(command,env):
        if failure=='worker':return 1,'source mismatch'
        out=Path(command[command.index('--output')+1]);out.mkdir()
        (out/'summary.json').write_text(json.dumps(dict(schema='mpdb-purpose/1',formal_verdict=True if failure=='formal_verdict' else None,alignment_status='unverified',hardware_verified=False)))
        return 0,''
    monkeypatch.setattr(projects,'run_worker',worker)
    r=client.post(URL,files={k:(k,b'bad') for k in ('archive','members')})
    assert r.status_code==(502 if failure=='formal_verdict' else 422)
    assert not list(tmp_path.glob('purpose-evaluation-*.zip'))


def test_optional_asc_is_forwarded_and_uses_common_frame_default(tmp_path,monkeypatch):
    (tmp_path/'scripts').mkdir(); (tmp_path/'scripts/mpdb_purpose.py').touch()
    monkeypatch.setattr(projects,'ROOT',tmp_path)
    monkeypatch.setattr(projects,'storage',lambda:tmp_path)
    monkeypatch.setattr(projects,'worker_environment',lambda root:{})
    def worker(command,env):
        assert '--asc' in command
        assert Path(command[command.index('--asc')+1]).read_bytes()==b'actual asc upload'
        assert command[command.index('--holdout-end')+1]=='36'
        assert command[command.index('--manual-candidate')+1]=='existing-asc'
        return 1,'intentional rejection after forwarding'
    monkeypatch.setattr(projects,'run_worker',worker)
    response=client.post(URL,files={k:(k,b'actual asc upload' if k=='asc' else b'bytes') for k in ('archive','members','asc')},data={'manual_candidate':'existing-asc'})
    assert response.status_code==422
    assert '比较未完成' in response.json()['detail']


def test_real_seven_candidates_survive_both_downloads(tmp_path,monkeypatch):
    import csv,io,zipfile
    from collections import Counter
    root=Path('/Users/Simon/Tools/MIMO-First')
    sample=root/'RT-IMT-2030'
    engine=Path('/private/tmp/p2110-ce')
    if not sample.is_dir() or not (engine/'mimo_ota_simulator/candidate_evaluation.py').is_file():
        pytest.skip('缺少真实样本或本片CE')
    monkeypatch.setenv('CHANNEL_ENGINE_PATH',str(engine))
    monkeypatch.setattr(projects,'storage',lambda:tmp_path)
    asc=tmp_path/'source-asc.zip'
    with zipfile.ZipFile(asc,'w') as z:
        for path in sample.glob('R0B0S0D_TX*_RX*_H.asc'):z.write(path,path.name)
    with next(sample.glob('*MPDB.zip')).open('rb') as a,(root/'docs/evidence/imt-three/members.npz').open('rb') as m,asc.open('rb') as existing:
        response=client.post(URL,files={'archive':('source.zip',a),'members':('members.npz',m),'asc':('asc.zip',existing)},data={'manual_candidate':'existing-asc'})
    assert response.status_code==200,response.text
    summary=response.json()
    package=client.get(summary['download_url'].removeprefix('/api/v1'))
    points=client.get(summary['points_url'].removeprefix('/api/v1'))
    assert package.status_code==points.status_code==200
    with zipfile.ZipFile(io.BytesIO(package.content)) as z:
        assert z.read('points.csv')==points.content
        report=json.loads(z.read('report.json'))
    rows=list(csv.DictReader(io.StringIO(points.content.decode())))
    counts=Counter(row['candidate_id'] for row in rows)
    assert set(counts)==set(summary['evaluation']['candidate_parameters'])
    assert len(counts)==7
    assert counts['existing-asc']==37*16*41==24272
    assert all(counts[name]==38*16*41 for name in counts if name!='existing-asc')
    asc_rows=[row for row in rows if row['candidate_id']=='existing-asc']
    assert {int(row['frame']) for row in asc_rows}==set(range(37))
    assert {row['partition'] for row in asc_rows}=={'selection','holdout'}
    assert report['excluded_source_frame_review']['frame_id']==37
    assert report['excluded_source_frame_review']['existing_asc'] is None
    assert report['evaluation']['provenance']['existing_asc_reference']['unmatched_frames']==[37]
    assert len(rows)==173840
