"""PC04A3 专属新文件库：默认bootstrap目录，全类别Mock，不复用其他证据库。"""
import json
import os
import re
from pathlib import Path

_url = os.environ.get('DATABASE_URL', '')
_path = Path(_url.removeprefix('sqlite:///'))
if (os.environ.get('USE_MOCK_INSTRUMENTS') != 'true'
        or os.environ.get('BOOTSTRAP_ON_STARTUP') != 'true'
        or not re.fullmatch(r'sqlite:////tmp/pc04a3-[A-Za-z0-9]+/browser.sqlite', _url)
        or not _path.parent.is_dir() or _path.exists()):
    raise RuntimeError('仅允许mktemp新建/tmp/pc04a3-*目录中的新文件SQLite及全Mock默认bootstrap')

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
        bindings = []
        categories = db.query(InstrumentCategory).all()
        assert categories
        for category in categories:
            category.driver_mode = 'mock'
            model = db.get(InstrumentModel, category.selected_model_id)
            connection = db.query(InstrumentConnection).filter_by(category_id=category.id).one_or_none()
            if model is not None and connection is not None:
                bindings.append(dict(category_id=str(category.id), instrument_model_id=str(model.id),
                    connection_endpoint=connection.endpoint, driver_mode='mock'))
        switch = next(c for c in categories if c.category_key == 'rfSwitch')
        assert {'channelEmulator', 'signalAnalyzer'} <= {c.category_key for c in categories
            if c.selected_model_id and c.connection is not None}
        manifest = {'database': str(engine.url), 'labs': [], 'evidence_boundary': '全HAL Mock，非现场验收'}
        for suffix in ('甲', '乙'):
            chamber = create_chamber_from_preset(ChamberType.TYPE_C.value, name=f'PC04A3暗室{suffix}')
            db.add(chamber); db.flush()
            lab = LabProfile(name=f'PC04自动采集{suffix}', chamber_config_id=chamber.id,
                is_active=True, instrument_bindings=bindings)
            db.add(lab); db.flush()
            nodes = [dict(id=f'ce{i}', type='ce_port', label=f'B1.{i}', position={'x':30,'y':60+(i-1)*240}, params={'ports':['out']}) for i in (1,2)]
            nodes += [dict(id=f'probe{i}', type='probe', label=f'探头0{pol}', position={'x':540,'y':60+(i-1)*240},
                params={'ports':['in'], 'probe_id':0, 'polarization':pol,
                    'rf_path_selection':{'connection_ids':[f'fixed-{pol.lower()}'], 'switch_mappings':[]}}) for i,pol in ((1,'V'),(2,'H'))]
            nodes += [dict(id='hidden-normal',type='pad',label='隐藏普通器件',position={'x':200,'y':500},params={'ports':['in','out'],'visible_modes':[],'unknown':{'keep':1}}),
                dict(id='hidden-calibration',type='receive_cable',label='隐藏校准器件',position={'x':400,'y':500},params={'ports':['in','out'],'visible_modes':[],'connection_scope':'calibration','unknown':{'keep':1}})]
            edges = [dict(id=f'fixed-{pol}', source=f'ce{i}', source_pin='out', target=f'probe{i}', target_pin='in', cable_loss_db=0) for i,pol in ((1,'v'),(2,'h'))]
            topology = SwitchTopology(switch_category_id=switch.id, chamber_id=chamber.id,
                name=f'PC04A3显式路径{suffix}', is_active=True, is_default=True, nodes=nodes, connections=edges,
                operating_modes=[dict(id='mimo_ota',name='MIMO OTA 测试',active_connections=['fixed-v','fixed-h']),
                    dict(id='calibration',name='校准接线',active_connections=[])])
            topology.update_statistics()
            db.add(topology); db.flush()
            manifest['labs'].append({'name':lab.name,'lab_id':str(lab.id),'topology_id':str(topology.id)})
        db.commit()
        assert all(c.driver_mode == 'mock' for c in categories)
        print(json.dumps(manifest,ensure_ascii=False))


if __name__ == '__main__':
    seed()
