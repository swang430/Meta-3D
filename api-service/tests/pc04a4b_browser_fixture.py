"""PC04A4b 新SQLite、默认bootstrap、全Mock真实HTTP浏览器前置。"""
import json
import os
import re
from pathlib import Path
from uuid import UUID

_url = os.environ.get('DATABASE_URL', '')
_path = Path(_url.removeprefix('sqlite:///'))
if (os.environ.get('USE_MOCK_INSTRUMENTS') != 'true'
        or os.environ.get('BOOTSTRAP_ON_STARTUP') != 'true'
        or not re.fullmatch(r'sqlite:////tmp/pc04a4b-[A-Za-z0-9]+/browser.sqlite', _url)
        or not _path.parent.is_dir() or _path.exists()):
    raise RuntimeError('仅允许新建/tmp/pc04a4b-*目录的新SQLite及全Mock默认bootstrap')

from fastapi.testclient import TestClient
from app.main import app
from app.db.database import Base, engine, SessionLocal
from app.services.bootstrap import run_bootstrap_on_startup
from app.models.chamber import ChamberType, create_chamber_from_preset
from app.models.instrument import InstrumentCategory, InstrumentConnection, InstrumentModel
from app.models.lab_profile import LabProfile
from app.models.switch_topology import SwitchTopology


def seed():
    Base.metadata.create_all(engine)
    assert run_bootstrap_on_startup(SessionLocal) is True
    manifest = {'database': str(engine.url), 'labs': [], 'boundary': '全HAL Mock，非现场验收'}
    with SessionLocal() as db:
        categories = db.query(InstrumentCategory).all()
        bindings = []
        for index, category in enumerate(categories):
            category.driver_mode = 'mock'
            connection = db.query(InstrumentConnection).filter_by(category_id=category.id).one_or_none()
            if category.category_key == 'signalAnalyzer':
                category.selected_model_id = db.query(InstrumentModel).filter_by(category_id=category.id, model='FSVA3000').one().id
            model = db.get(InstrumentModel, category.selected_model_id)
            if connection:
                connection.endpoint = f'192.0.2.{index + 10}'
            if model and connection:
                bindings.append(dict(category_id=str(category.id), instrument_model_id=str(model.id),
                                     connection_endpoint=connection.endpoint, driver_mode='mock'))
        switch_id = str(next(c for c in categories if c.category_key == 'rfSwitch').id)
        manifest['category_ids'] = {c.category_key: str(c.id) for c in categories}
        for suffix in ('甲', '乙'):
            chamber = create_chamber_from_preset(ChamberType.TYPE_C.value, name=f'PC04A4b暗室{suffix}')
            db.add(chamber); db.flush()
            lab = LabProfile(name=f'PC04A4b端口{suffix}', chamber_config_id=chamber.id,
                             is_active=True, instrument_bindings=bindings)
            db.add(lab); db.flush()
            manifest['labs'].append(dict(name=lab.name, lab_id=str(lab.id), chamber_id=str(chamber.id)))
        db.commit()
    with TestClient(app) as client:
        lab = manifest['labs'][0]
        nodes = []
        for index, kind in enumerate(('ce_port', 'probe', 'amplifier', 'pad', 'combiner', 'antenna',
                'cable', 'receive_cable', 'air_path', 'reference_antenna', 'signal_analyzer', 'vna',
                'termination', 'channel_emulator', 'emcenter', 'communication_tester')):
            params = {'ports': ['in', 'out'], 'unknown': {'keep': kind},
                      'visible_modes': ['mimo_ota', 'calibration']}
            if kind == 'communication_tester':
                params.update(ports=['RF5', 'DL1'], port_roles={'RF5': 'dl'})
            if kind == 'probe':
                params.update(probe_id=0, polarization='V', rf_path_selection={'connection_ids': ['fixed-v'], 'switch_mappings': []})
            nodes.append(dict(id=kind, type=kind, label=f'端口-{kind}',
                position={'x': 80+(index % 4)*300, 'y': 80+(index//4)*220}, params=params))
        next(n for n in nodes if n['id'] == 'ce_port')['label'] = 'B1.1'
        nodes += [dict(id='ce2', type='ce_port', label='B1.2', position={'x': 100, 'y': 1100}, params={'ports': ['out']}),
                  dict(id='probe2', type='probe', label='第二链探头', position={'x': 500, 'y': 1100},
                       params={'ports': ['in'], 'probe_id': 0, 'polarization': 'H',
                               'rf_path_selection': {'connection_ids': ['fixed-h'], 'switch_mappings': []}})]
        edges = [dict(id='fixed-v', source='ce_port', source_pin='out', target='probe', target_pin='in', cable_loss_db=0),
                 dict(id='fixed-h', source='ce2', source_pin='out', target='probe2', target_pin='in')]
        response = client.post('/api/v1/switch-topologies', json=dict(name='PC04A4b显式两链',
            switch_category_id=switch_id, lab_profile_id=lab['lab_id'], nodes=nodes, connections=edges,
            operating_modes=[dict(id='mimo_ota', name='MIMO OTA 测试', active_connections=['fixed-v','fixed-h']),
                             dict(id='calibration', name='校准接线', active_connections=[])]))
        assert response.status_code == 201, response.text
        lab['topology_id'] = response.json()['id']
        lab = manifest['labs'][1]
        response = client.post('/api/v1/switch-topologies/import/from-template', params=dict(
            switch_category_id=switch_id, lab_profile_id=lab['lab_id'], template_id='caict_v4'))
        assert response.status_code == 200, response.text
        lab['topology_id'] = response.json()['id']
        assert client.get('/api/v1/instruments/hal/status').json()['mode'] == 'mock'
    with SessionLocal() as db:
        if os.environ.get('PC04A4B_LEGACY_EDGE_FIXTURE') == 'true':
            # 明确构造历史样本，不能经新写边界创建；只修改本fixture新建的隔离库。
            row = db.get(SwitchTopology, UUID(manifest['labs'][0]['topology_id']))
            legacy_nodes = []
            for index, (ident, direction) in enumerate((('legacy-input-source', 'input'), ('legacy-input-target', 'input'),
                    ('legacy-output-source', 'output'), ('legacy-output-target', 'output'))):
                legacy_nodes.append(dict(id=ident, type='pad', label=ident,
                    position={'x': 80+(index % 2)*500, 'y': 1450+(index//2)*250},
                    params={'ports': ['P'], 'port_directions': {'P': direction}, 'visible_modes': ['mimo_ota']}))
            legacy_edges = [dict(id='legacy-source-input', source='legacy-input-source', source_pin='P',
                                target='legacy-input-target', target_pin='P', cable_loss_db=0),
                            dict(id='legacy-target-output', source='legacy-output-source', source_pin='P',
                                target='legacy-output-target', target_pin='P', pa_gain_db=0)]
            row.nodes = [*row.nodes, *legacy_nodes]
            row.connections = [*row.connections, *legacy_edges]
            row.operating_modes = [{**mode, 'active_connections': [*mode['active_connections'], *[e['id'] for e in legacy_edges]]}
                                   if mode['id'] == 'mimo_ota' else mode for mode in row.operating_modes]
            db.commit()
            manifest['legacy_readonly_edges'] = legacy_edges
        assert all(c.driver_mode == 'mock' for c in db.query(InstrumentCategory).all())
        assert all(b['driver_mode'] == 'mock' for lab in db.query(LabProfile).all() for b in lab.instrument_bindings)
    print(json.dumps(manifest, ensure_ascii=False))


if __name__ == '__main__':
    seed()
