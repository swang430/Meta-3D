"""Task3 专用新库，全 Mock；不触碰用户数据库。"""
import os
import json
import re
import datetime
import uuid
from pathlib import Path

url = os.environ.get('DATABASE_URL', '')
path = Path(url.removeprefix('sqlite:///'))
if (not re.fullmatch(r'sqlite:////tmp/pc04a4d-[A-Za-z0-9]+/browser.sqlite', url)
        or path.exists() or not path.parent.is_dir()
        or os.environ.get('USE_MOCK_INSTRUMENTS') != 'true'
        or os.environ.get('BOOTSTRAP_ON_STARTUP') != 'true'):
    raise RuntimeError('仅允许新专用 SQLite、默认 bootstrap 和 Mock')

from fastapi.testclient import TestClient
from app.main import app
from app.db.database import Base, engine, SessionLocal
from app.services.bootstrap import run_bootstrap_on_startup
from app.models.chamber import ChamberType, create_chamber_from_preset
from app.models.instrument import InstrumentCategory, InstrumentConnection, InstrumentModel
from app.models.lab_profile import LabProfile
from app.models.switch_topology import SwitchTopology
from app.models.test_plan import TestExecution
from app.models.calibration import CalibrationCertificate

Base.metadata.create_all(engine)
assert run_bootstrap_on_startup(SessionLocal)
manifest = {'database': url, 'labs': [], 'boundary': '隔离软件声明，全Mock，非实物验收'}
with SessionLocal() as db:
    bindings = []
    categories = db.query(InstrumentCategory).all()
    for i, category in enumerate(categories):
        category.driver_mode = 'mock'
        if category.category_key == 'signalAnalyzer':
            category.selected_model_id = db.query(InstrumentModel).filter_by(category_id=category.id, model='FSVA3000').one().id
        connection = db.query(InstrumentConnection).filter_by(category_id=category.id).one_or_none()
        if connection and category.selected_model_id:
            connection.endpoint = f'192.0.2.{i+10}'
            bindings.append(dict(category_id=str(category.id), instrument_model_id=str(category.selected_model_id),
                connection_endpoint=connection.endpoint, driver_mode='mock'))
    switch_id = str(next(c for c in categories if c.category_key == 'rfSwitch').id)
    second_switch = InstrumentCategory(category_key='pc04a4dSwitch', category_name='PC04A4d第二射频开关',
        category_name_en='Task4 second switch', driver_mode='mock', is_active=True, display_order=999)
    db.add(second_switch); db.flush()
    second_switch_id = str(second_switch.id)
    manifest['second_switch_id'] = second_switch_id
    for suffix in ('甲', '乙'):
        chamber = create_chamber_from_preset(ChamberType.TYPE_C.value, name=f'PC04A4d暗室{suffix}')
        db.add(chamber); db.flush()
        lab = LabProfile(name=f'PC04A4d转换{suffix}', chamber_config_id=chamber.id, is_active=True, instrument_bindings=bindings)
        db.add(lab); db.flush()
        manifest['labs'].append(dict(name=lab.name, lab_id=str(lab.id)))
    # bootstrap 自带 Lab 同样显式改为 Mock。
    for lab in db.query(LabProfile).all():
        lab.instrument_bindings = [{**b, 'driver_mode': 'mock'} for b in lab.instrument_bindings]
    db.commit()
with TestClient(app) as client:
    for lab in manifest['labs']:
        nodes = [dict(id=ident, type=kind, label='B1.1' if ident == 'ce' else ident,
            position={'x': 100+i*170, 'y': 150}, params=params)
            for i, (ident, kind, params) in enumerate([
                ('ce', 'ce_port', {'ports':['OUT'], 'port_directions':{'OUT':'output'}, 'opaque':{'keep':1}}),
                ('cable', 'cable', {'ports':['IN','OUT'], 'port_directions':{'IN':'input','OUT':'output'}, 'internal_paths':[{'from_port':'IN','to_port':'OUT'}]}),
                ('probe', 'probe', {'ports':['IN','REF'], 'port_directions':{'IN':'input','REF':'output'},'probe_id':0,'polarization':'V','rf_path_selection':{'connection_ids':['wire-in','wire-out'],'switch_mappings':[]}}),
                ('bse', 'bse_port', {'ports':['RF'],'port_roles':{'RF':'dl'}}), ('sa', 'sa_port', {'ports':['IN']}),
                ('new-ce', 'channel_emulator', {'ports':['P1'],'port_directions':{'P1':'unknown'},'ce_port':'B2.1'}),
                ('reference', 'receive_cable', {'connection_scope':'calibration','ports':['IN','OUT'],'port_directions':{'IN':'input','OUT':'output'},'internal_paths':[{'from_port':'IN','to_port':'OUT'}]}),
                ('air', 'air_path', {'connection_scope':'calibration','ports':['IN','OUT'],'port_directions':{'IN':'input','OUT':'output'},'internal_paths':[{'from_port':'IN','to_port':'OUT'}]}),
                ('antenna', 'reference_antenna', {'connection_scope':'calibration','ports':['IN','OUT'],'port_directions':{'IN':'input','OUT':'output'},'internal_paths':[{'from_port':'IN','to_port':'OUT'}]}),
                ('analyzer', 'signal_analyzer', {'connection_scope':'calibration','ports':['IN'],'port_directions':{'IN':'input'}})])]
        edges = [dict(id='wire-in',source='ce',source_pin='OUT',target='cable',target_pin='IN',cable_loss_db=2),
                 dict(id='wire-out',source='cable',source_pin='OUT',target='probe',target_pin='IN',cable_loss_db=2)]
        edges += [dict(id=f'ref-{i}',source=a,source_pin='REF' if a=='probe' else 'OUT',target=b,target_pin='IN',cable_loss_db=0)
            for i,(a,b) in enumerate([('probe','air'),('air','antenna'),('antenna','reference'),('reference','analyzer')])]
        response = client.post('/api/v1/switch-topologies', json=dict(name=f"PC04A4d图{lab['name'][-1]}",
            switch_category_id=switch_id, lab_profile_id=lab['lab_id'], is_default=True,
            nodes=nodes,connections=edges,operating_modes=[dict(id='mimo_ota',name='MIMO OTA 测试',active_connections=['wire-in','wire-out']),
                dict(id='calibration',name='校准接线',active_connections=[f'ref-{i}' for i in range(4)])]))
        assert response.status_code == 201, response.text
        lab['display_topology_id'] = response.json()['id']
        second = client.post('/api/v1/switch-topologies', json=dict(name=f"PC04A4d第二开关图{lab['name'][-1]}",
            switch_category_id=second_switch_id, lab_profile_id=lab['lab_id'], is_default=True,
            nodes=nodes, connections=edges, operating_modes=[dict(id='mimo_ota',name='MIMO OTA 测试',
                active_connections=['wire-in','wire-out']), dict(id='calibration',name='校准接线',
                active_connections=[f'ref-{i}' for i in range(4)])]))
        assert second.status_code == 201, second.text
        lab['second_topology_id'] = second.json()['id']
        imported = client.post('/api/v1/switch-topologies/import/from-template', params=dict(
            switch_category_id=switch_id, lab_profile_id=lab['lab_id'], template_id='caict_v4'))
        assert imported.status_code in (200, 201), imported.text
        lab['source_topology_id'] = imported.json()['id']
    assert client.get('/api/v1/instruments/hal/status').json()['mode'] == 'mock'
with SessionLocal() as db:
    for item in manifest['labs']:
        db.query(SwitchTopology).filter_by(id=uuid.UUID(item['source_topology_id'])).one().created_at = datetime.datetime(2020,1,1)
    db.add(TestExecution(status='completed',topology_id=manifest['labs'][0]['display_topology_id'],
        config={'fixture':'Task3隔离历史','snapshot':nodes},test_results={'conclusion':'unknown'}))
    db.add(CalibrationCertificate(certificate_number='pc04a4d-task3-'+path.parent.name,
        calibration_date=datetime.datetime(2026,1,1),valid_until=datetime.datetime(2027,1,1),
        overall_pass=False,system_configuration={'fixture':'Task3隔离历史','frozen':[2,None]}))
    db.commit()
    assert categories and all(c.driver_mode == 'mock' for c in db.query(InstrumentCategory).all())
    assert all(b['driver_mode'] == 'mock' for l in db.query(LabProfile).all() for b in l.instrument_bindings)
manifest['all_category_and_lab_bindings_mock'] = True
print(json.dumps(manifest, ensure_ascii=False))
