"""PC04A4c 新库、默认 bootstrap、全 Mock；图只经真实 HTTP 写入。"""
import json
import os
import re
from pathlib import Path

url = os.environ.get('DATABASE_URL', '')
path = Path(url.removeprefix('sqlite:///'))
if (not re.fullmatch(r'sqlite:////tmp/pc04a4c-[A-Za-z0-9]+/browser.sqlite', url)
        or not path.parent.is_dir() or path.exists()
        or os.environ.get('USE_MOCK_INSTRUMENTS') != 'true'
        or os.environ.get('BOOTSTRAP_ON_STARTUP') != 'true'):
    raise RuntimeError('只允许专用新 SQLite 和全 Mock 默认 bootstrap')

from fastapi.testclient import TestClient
from app.main import app
from app.db.database import Base, engine, SessionLocal
from app.services.bootstrap import run_bootstrap_on_startup
from app.models.chamber import ChamberType, create_chamber_from_preset
from app.models.instrument import InstrumentCategory, InstrumentConnection, InstrumentModel
from app.models.lab_profile import LabProfile


def seed():
    Base.metadata.create_all(engine)
    assert run_bootstrap_on_startup(SessionLocal) is True
    manifest = {'database': url, 'labs': [], 'instrument_connections': [],
        'bootstrap_succeeded': True, 'boundary': '全 Mock；非硬件验收'}
    with SessionLocal() as db:
        categories = db.query(InstrumentCategory).all()
        assert categories
        bindings = []
        for index, category in enumerate(categories):
            category.driver_mode = 'mock'
            connection = db.query(InstrumentConnection).filter_by(category_id=category.id).one_or_none()
            if category.category_key == 'signalAnalyzer':
                category.selected_model_id = db.query(InstrumentModel).filter_by(category_id=category.id, model='FSVA3000').one().id
            if connection and category.selected_model_id:
                connection.endpoint = f'192.0.2.{index + 10}'
                bindings.append(dict(category_id=str(category.id), instrument_model_id=str(category.selected_model_id),
                    connection_endpoint=connection.endpoint, driver_mode='mock'))
                manifest['instrument_connections'].append(dict(id=str(connection.id), category_id=str(category.id),
                    endpoint=connection.endpoint, driver_mode='mock'))
        switch_id = str(next(c for c in categories if c.category_key == 'rfSwitch').id)
        manifest['category_ids'] = {c.category_key: str(c.id) for c in categories}
        manifest['bindings'] = bindings
        for suffix in ('甲', '乙'):
            chamber = create_chamber_from_preset(ChamberType.TYPE_C.value, name=f'PC04A4c暗室{suffix}')
            db.add(chamber); db.flush()
            lab = LabProfile(name=f'PC04A4c内部通路{suffix}', chamber_config_id=chamber.id,
                is_active=True, instrument_bindings=bindings)
            db.add(lab); db.flush()
            manifest['labs'].append(dict(name=lab.name, lab_id=str(lab.id), chamber_id=str(chamber.id)))
        db.commit()
    with TestClient(app) as client:
        def node(ident, kind, ports, directions, **extra):
            index = len(nodes)
            return dict(id=ident, type=kind, label='B1.1' if kind == 'ce_port' else ident,
                position=dict(x=80 + index % 4 * 280, y=80 + index // 4 * 180),
                params=dict(ports=ports, port_directions=directions, opaque={'keep': ident},
                    visible_modes=['calibration'] if extra.get('connection_scope') == 'calibration' else ['mimo_ota', 'calibration'], **extra))
        nodes = []
        nodes.append(node('ce', 'ce_port', ['OUT'], {'OUT': 'output'}))
        nodes.append(node('pa', 'amplifier', ['IN', 'OUT'], {'IN': 'input', 'OUT': 'output'},
            internal_paths=[dict(from_port='IN', to_port='OUT')], gain_db=0))
        nodes.append(node('pad', 'pad', ['IN', 'OUT'], {'IN': 'input', 'OUT': 'output'},
            internal_paths=[dict(from_port='IN', to_port='OUT')]))
        nodes.append(node('combiner', 'combiner', ['IN1', 'IN2', 'OUT'], {'IN1': 'input', 'IN2': 'input', 'OUT': 'output'},
            internal_paths=[dict(from_port='IN1', to_port='OUT')]))
        nodes.append(node('probe', 'probe', ['IN', 'REF'], {'IN': 'input', 'REF': 'output'}, probe_id=0, polarization='V',
            rf_path_selection={'connection_ids': ['n1', 'n2', 'n3', 'n4'], 'switch_mappings': []}))
        nodes.append(node('air', 'air_path', ['IN', 'OUT'], {'IN': 'input', 'OUT': 'output'},
            internal_paths=[dict(from_port='IN', to_port='OUT')], connection_scope='calibration'))
        nodes.append(node('ref', 'reference_antenna', ['IN', 'OUT'], {'IN': 'input', 'OUT': 'output'},
            internal_paths=[dict(from_port='IN', to_port='OUT')], connection_scope='calibration'))
        nodes.append(node('sa', 'signal_analyzer', ['IN'], {'IN': 'input'}, connection_scope='calibration'))
        nodes.append(node('termination', 'termination', ['IN'], {'IN': 'input'}, internal_paths=[]))
        nodes.append(node('legacy-pa', 'amplifier', ['IN', 'OUT'], {}, gain_db=0))
        normal = [('ce', 'pa'), ('pa', 'pad'), ('pad', 'combiner'), ('combiner', 'probe')]
        reference = [('probe', 'air'), ('air', 'ref'), ('ref', 'sa')]
        edges = [dict(id=f'n{i+1}', source=a, source_pin='OUT', target=b,
            target_pin='IN1' if b == 'combiner' else 'IN', cable_loss_db=0) for i, (a, b) in enumerate(normal)]
        edges += [dict(id=f'r{i+1}', source=a, source_pin='REF' if a == 'probe' else 'OUT', target=b,
            target_pin='IN', cable_loss_db=0) for i, (a, b) in enumerate(reference)]
        modes = [dict(id='mimo_ota', name='MIMO OTA 测试', active_connections=[f'n{i}' for i in range(1, 5)]),
            dict(id='calibration', name='校准接线', active_connections=[f'r{i}' for i in range(1, 4)])]
        manifest['node_ids'] = [n['id'] for n in nodes]
        manifest['connection_ids'] = [e['id'] for e in edges]
        for lab in manifest['labs']:
            response = client.post('/api/v1/switch-topologies', json=dict(name=f"PC04A4c图{lab['name'][-1]}",
                switch_category_id=switch_id, lab_profile_id=lab['lab_id'], nodes=nodes, connections=edges, operating_modes=modes))
            assert response.status_code == 201, response.text
            lab['topology_id'] = response.json()['id']
        assert client.get('/api/v1/instruments/hal/status').json()['mode'] == 'mock'
    with SessionLocal() as db:
        assert all(c.driver_mode == 'mock' for c in db.query(InstrumentCategory).all())
        assert all(b['driver_mode'] == 'mock' for lab in db.query(LabProfile).all() for b in lab.instrument_bindings)
        manifest['all_category_and_lab_bindings_mock'] = True
    print(json.dumps(manifest, ensure_ascii=False))


if __name__ == '__main__':
    seed()
