"""PC04A4e 全 Mock 隔离浏览器输入；任何应用导入前先验证环境。"""
import os
import re
import json
import uuid
import copy
import hashlib
from pathlib import Path

url = os.environ.get('DATABASE_URL', '')
path = Path(url.removeprefix('sqlite:///'))
if (not re.fullmatch(r'sqlite:////tmp/pc04a4e-[A-Za-z0-9]+/browser.sqlite', url)
        or path.exists() or not path.parent.is_dir()
        or os.environ.get('USE_MOCK_INSTRUMENTS') != 'true'
        or os.environ.get('BOOTSTRAP_ON_STARTUP') != 'true'):
    raise RuntimeError('仅允许未存在的本片 SQLite 与两个 true 开关')

from fastapi.testclient import TestClient
from app.main import app
from app.db.database import Base, engine, SessionLocal
from app.services.bootstrap import run_bootstrap_on_startup
from app.models.chamber import ChamberType, create_chamber_from_preset
from app.models.instrument import InstrumentCategory, InstrumentConnection, InstrumentModel
from app.models.lab_profile import LabProfile
from app.models.switch_topology import SwitchTopology
from app.models.test_plan import TestExecution
from app.models.diagnostic_run import DiagnosticRun
from app.models.route_calibration import RouteCalibrationApplication

Base.metadata.create_all(engine)
assert run_bootstrap_on_startup(SessionLocal)
manifest = {'database': url, 'labs': [], 'boundary': '隔离验收输入，全Mock，非实物/计量/客户报告'}
with SessionLocal() as db:
    categories = db.query(InstrumentCategory).all()
    bindings = []
    for i, cat in enumerate(categories):
        cat.driver_mode = 'mock'
        if cat.category_key == 'signalAnalyzer':
            cat.selected_model_id = db.query(InstrumentModel).filter_by(category_id=cat.id, model='FSVA3000').one().id
        conn = db.query(InstrumentConnection).filter_by(category_id=cat.id).one_or_none()
        if conn and cat.selected_model_id:
            conn.endpoint = f'192.0.2.{i+10}'
            bindings.append(dict(category_id=str(cat.id), instrument_model_id=str(cat.selected_model_id),
                connection_endpoint=conn.endpoint, driver_mode='mock'))
    primary = str(next(c for c in categories if c.category_key == 'rfSwitch').id)
    extra = []
    for key, name in [('second', '第二开关'), ('caict', 'CAICT源图'), ('legacy', '历史参考图')]:
        cat = InstrumentCategory(category_key='pc04a4eSwitch'+key, category_name='PC04A4e'+name,
            category_name_en='PC04A4e isolated fixture', driver_mode='mock', is_active=True, display_order=990+len(extra))
        db.add(cat); db.flush(); extra.append(str(cat.id))
    manifest['switch_category_id'] = primary
    manifest['second_switch_id'], manifest['caict_category_id'], manifest['legacy_category_id'] = extra
    for suffix in ('甲', '乙'):
        chamber = create_chamber_from_preset(ChamberType.TYPE_C.value, name='PC04A4e暗室'+suffix)
        db.add(chamber); db.flush()
        lab = LabProfile(name='PC04A4e验收'+suffix, chamber_config_id=chamber.id, is_active=True, instrument_bindings=bindings)
        db.add(lab); db.flush()
        manifest['labs'].append(dict(name=lab.name, lab_id=str(lab.id), chamber_id=str(chamber.id)))
    for lab in db.query(LabProfile):
        lab.instrument_bindings = [{**b, 'driver_mode':'mock'} for b in lab.instrument_bindings]
    db.commit()

def node(ident, kind, index, **params):
    return dict(id=ident, type=kind, label='B1.1' if ident == 'ce' else ident,
        position=dict(x=100+(index%5)*210, y=100+(index//5)*210),
        params={'visible_modes':['calibration'] if params.get('connection_scope')=='calibration' else ['mimo_ota','calibration'], 'opaque':{'keep':True}, **params})

pair = [dict(from_port='IN',to_port='OUT')]
directions = {'IN':'input','OUT':'output'}
nodes = [node('ce','ce_port',0,ports=['OUT'],port_directions={'OUT':'output'},ce_port='B1.1'),
    node('wire','cable',1,ports=['IN','OUT'],port_directions=directions,internal_paths=pair),
    node('probe','probe',2,ports=['IN','REF'],port_directions={'IN':'input','REF':'output'},probe_id=0,polarization='V',
        rf_path_selection={'connection_ids':['wire-in','wire-out'],'switch_mappings':[]}),
    node('reference','reference_antenna',3,ports=['IN','OUT'],port_directions=directions,internal_paths=pair,connection_scope='calibration'),
    node('rx','receive_cable',4,ports=['IN','OUT'],port_directions=directions,internal_paths=pair,connection_scope='calibration'),
    node('analyzer','signal_analyzer',5,ports=['IN'],port_directions={'IN':'input'},connection_scope='calibration')]
all_types = ['channel_emulator','communication_tester','emcenter','vna','pad','amplifier','combiner','air_path',
    'termination','antenna','bse_port','switch_slot','sa_port']
for kind in all_types:
    params = dict(ports=['IN','OUT'],port_directions=directions)
    if kind in ['pad','amplifier','combiner','air_path','antenna','switch_slot']:
        params['internal_paths'] = pair
    if kind == 'termination':
        params = dict(ports=['IN'],port_directions={'IN':'input'},internal_paths=[])
    if kind == 'bse_port':
        params = dict(ports=['RF'],port_roles={'RF':'dl'},physical_port_display={'RF':'fixture逻辑映射，未核硬件'})
    if kind in ['channel_emulator','emcenter']:
        params = dict(ports=['P1'],port_directions={'P1':'unknown'})
    nodes.append(node(kind,kind,len(nodes),**params))
edges = [dict(id='wire-in',source='ce',source_pin='OUT',target='wire',target_pin='IN',cable_loss_db=2),
    dict(id='wire-out',source='wire',source_pin='OUT',target='probe',target_pin='IN',cable_loss_db=2),
    dict(id='pa-reference-edge',source='probe',source_pin='REF',target='reference',target_pin='IN',pa_gain_db=12),
    dict(id='reference-rx',source='reference',source_pin='OUT',target='rx',target_pin='IN',cable_loss_db=2),
    dict(id='rx-analyzer',source='rx',source_pin='OUT',target='analyzer',target_pin='IN',cable_loss_db=2)]
modes = [dict(id='mimo_ota',name='MIMO OTA 测试',active_connections=['wire-in','wire-out']),
    dict(id='calibration',name='校准接线',active_connections=['pa-reference-edge','reference-rx','rx-analyzer'])]
manifest['node_types'] = sorted({n['type'] for n in nodes})
manifest['http'] = []
with TestClient(app) as client:
    for lab in manifest['labs']:
        for category, key, prefix in [(primary,'display_topology_id','图'),(extra[0],'second_topology_id','第二开关图')]:
            request = dict(name='PC04A4e'+prefix+lab['name'][-1], switch_category_id=category,
                lab_profile_id=lab['lab_id'],is_default=True,nodes=nodes,connections=edges,operating_modes=modes)
            response = client.post('/api/v1/switch-topologies',json=request)
            assert response.status_code == 201,response.text
            lab[key] = response.json()['id']
            manifest['http'].append(dict(request=request,status=response.status_code,response=response.json()))
        imported = client.post('/api/v1/switch-topologies/import/from-template',params=dict(
            switch_category_id=extra[1],lab_profile_id=lab['lab_id'],template_id='caict_v4'))
        assert imported.status_code in (200,201),imported.text
        lab['source_topology_id'] = imported.json()['id']
        lab['caict_display_topology_id'] = imported.json()['id']
        manifest['http'].append(dict(kind='CAICT原import',status=imported.status_code,response=imported.json()))
    assert client.get('/api/v1/instruments/hal/status').json()['mode'] == 'mock'
with SessionLocal() as db:
    # 单独明确标注的历史输入，参考接收线故意缺声明；不是新图的可采集资格。
    lab = manifest['labs'][0]
    legacy_nodes = copy.deepcopy(nodes)
    for n in legacy_nodes:
        if n['id'] == 'rx':
            n['params'].pop('ports'); n['params'].pop('port_directions'); n['params'].pop('internal_paths')
    legacy_edges = copy.deepcopy(edges)
    legacy_edges[2]['pa_gain_db'] = '12'
    legacy = SwitchTopology(name='PC04A4e历史缺声明参考',switch_category_id=uuid.UUID(extra[2]),
        chamber_id=uuid.UUID(lab['chamber_id']),nodes=legacy_nodes,connections=legacy_edges,operating_modes=modes,is_default=True)
    db.add(legacy);db.flush();lab['legacy_topology_id']=str(legacy.id)
    history = TestExecution(status='completed',topology_id=lab['display_topology_id'],
        config={'fixture':'PC04A4e隔离历史，非客户报告','snapshot':nodes},test_results={'conclusion':'unknown'})
    db.add(history);db.flush();manifest['history_execution_id']=str(history.id)
    # root批准：仅保护既有采用FK的历史哨兵；不是confirmed、采集或资格证据。
    diagnostic = DiagnosticRun(kind='scpi_command',lab_profile_id=uuid.UUID(lab['lab_id']),
        target_name='PC04A4e隔离FK历史哨兵_非采集',success=False,
        params={'fixture':'仅测试拓扑引用保护','formal_eligible':False})
    db.add(diagnostic);db.flush()
    sentinel = RouteCalibrationApplication(lab_profile_id=uuid.UUID(lab['lab_id']),acquisition_run_id=diagnostic.id,
        topology_id=uuid.UUID(lab['display_topology_id']),chain_id='E13-FK-sentinel-not-a-route',
        idempotency_key=uuid.uuid4(),request_payload={'fixture':'隔离FK历史哨兵'},
        record={'fixture':'仅FK引用保护；非confirmed/非资格证据','formal_eligible':False,'net_loss_db':None})
    db.add(sentinel);db.flush()
    manifest['fk_sentinel']={'application_id':str(sentinel.id),'diagnostic_id':str(diagnostic.id),
        'topology_id':lab['display_topology_id'],'boundary':'仅409引用保护，不计采用/实测/confirmed'}
    manifest['history_before']={'execution':{'id':str(history.id),'config':history.config,'test_results':history.test_results},
        'sentinel_record':sentinel.record,'sentinel_request_payload':sentinel.request_payload}
    db.commit()
    manifest['mock_categories']=[dict(id=str(c.id),key=c.category_key,driver_mode=c.driver_mode) for c in db.query(InstrumentCategory)]
    manifest['mock_bindings']=[dict(lab_id=str(l.id),bindings=l.instrument_bindings) for l in db.query(LabProfile)]
    assert all(c['driver_mode']=='mock' for c in manifest['mock_categories'])
    assert all(b['driver_mode']=='mock' for l in manifest['mock_bindings'] for b in l['bindings'])
    manifest['initial_sql']=[dict(id=str(t.id),nodes=t.nodes,connections=t.connections,operating_modes=t.operating_modes) for t in db.query(SwitchTopology)]
template = Path('scripts/dev-fixtures/topology-templates/caict_v4.py')
manifest['template_hashes']={str(template):hashlib.sha256(template.read_bytes()).hexdigest()}
manifest['api_port']=18099
manifest['gui_port']=5194
manifest['all_category_and_lab_bindings_mock']=True
(path.parent/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
print(json.dumps(manifest,ensure_ascii=False))
