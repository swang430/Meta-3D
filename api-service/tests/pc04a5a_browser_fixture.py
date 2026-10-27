"""PC04A5a 专用新库；仅 ORM 种多图，绝不依赖待实现的 copy。"""
import json
import os
import re
from copy import deepcopy
from datetime import datetime
from pathlib import Path

url = os.environ.get('DATABASE_URL', '')
path = Path(url.removeprefix('sqlite:///'))
assert re.fullmatch(r'sqlite:////tmp/pc04a5a-[A-Za-z0-9]+/browser.sqlite', url)
assert path.parent.is_dir() and not path.exists()
assert os.environ.get('USE_MOCK_INSTRUMENTS') == 'true'
assert os.environ.get('BOOTSTRAP_ON_STARTUP') == 'true'

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
    with SessionLocal() as db:
        categories = db.query(InstrumentCategory).all()
        assert categories
        bindings = []
        for category in categories:
            category.driver_mode = 'mock'
            connection = db.query(InstrumentConnection).filter_by(category_id=category.id).one_or_none()
            if category.category_key == 'signalAnalyzer':
                category.selected_model_id = db.query(InstrumentModel).filter_by(
                    category_id=category.id, model='FSVA3000').one().id
            if connection is not None and category.category_key in ('channelEmulator', 'signalAnalyzer'):
                connection.endpoint = '192.0.2.10' if category.category_key == 'channelEmulator' else '192.0.2.11'
            if category.selected_model_id and connection is not None:
                bindings.append(dict(category_id=str(category.id), instrument_model_id=str(category.selected_model_id),
                                     connection_endpoint=connection.endpoint, driver_mode='mock'))
        switches = [next(c for c in categories if c.category_key == 'rfSwitch'),
                    InstrumentCategory(category_key='pc04a5aSecondSwitch', category_name='隔离开关乙', driver_mode='mock')]
        db.add(switches[1]); db.flush()
        manifest = {'database': str(path), 'labs': [], 'categories': [str(c.id) for c in switches],
                    'boundary': '全Mock软件夹具，非现场实测'}
        for index in range(2):
            chamber = create_chamber_from_preset(ChamberType.TYPE_C.value, name=f'PC04A5a暗室{index}')
            db.add(chamber); db.flush()
            lab = LabProfile(name=f'PC04A5a实验室{index}', chamber_config_id=chamber.id,
                             is_active=True, instrument_bindings=deepcopy(bindings))
            db.add(lab); db.flush()
            entry = {'lab_id': str(lab.id), 'chamber_id': str(chamber.id), 'topologies': []}
            for category_index, category in enumerate(switches):
                for number in range(101 if index == category_index == 0 else 2):
                    nodes = [dict(id='ce', type='ce_port', label='B1.1', position={'x': 50, 'y': 90},
                                  params={'ports': ['out'], 'opaque': {'bool': True, 'number': '2'}}),
                             dict(id='probe', type='probe', label='探头0V', position={'x': 500, 'y': 90},
                                  params={'ports': ['in'], 'probe_id': 0, 'polarization': 'V',
                                          'rf_path_selection': {'connection_ids': ['e'], 'switch_mappings': []}})]
                    edges = [dict(id='e', source='ce', source_pin='out', target='probe', target_pin='in',
                                  cable_loss_db='1.25', calibrated_loss_db=2.5,
                                  calibrated_phase_deg=None, opaque={'missing_preserved': True})]
                    topology = SwitchTopology(switch_category_id=category.id, chamber_id=chamber.id,
                        name=f'隔离原图-{index}-{category_index}-{number:03}', nodes=nodes, connections=edges,
                        operating_modes=[dict(id='mimo_ota', name='MIMO OTA', active_connections=['e'])],
                        is_active=number < 2, is_default=number == 0,
                        updated_at=datetime(2020 + min(number, 1), 1, 1))
                    topology.update_statistics(); db.add(topology); db.flush()
                    entry['topologies'].append(str(topology.id))
            manifest['labs'].append(entry)
            if index == 0:
                shared = LabProfile(name='PC04A5a共享暗室Lab', chamber_config_id=chamber.id,
                                    is_active=True, instrument_bindings=deepcopy(bindings))
                db.add(shared); db.flush()
                manifest['shared_lab_id'] = str(shared.id)
        # bootstrap 的 Lab 也明确改为 Mock，不能只检查新建 Lab。
        for lab in db.query(LabProfile).all():
            lab.instrument_bindings = [dict(binding, driver_mode='mock') for binding in (lab.instrument_bindings or [])]
        db.commit(); db.expire_all()
        assert all(c.driver_mode == 'mock' for c in db.query(InstrumentCategory).all())
        assert all(b['driver_mode'] == 'mock' for l in db.query(LabProfile).all() for b in (l.instrument_bindings or []))
        manifest['mock_verified_after_commit'] = True
        print(json.dumps(manifest, ensure_ascii=False))


if __name__ == '__main__':
    seed()
