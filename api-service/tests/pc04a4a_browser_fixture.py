"""PC04A4a 专属新库：默认bootstrap、全类别Mock，真实模板导入，不复制用户数据。"""
import json
import os
import re
from pathlib import Path

_url = os.environ.get('DATABASE_URL', '')
_path = Path(_url.removeprefix('sqlite:///'))
if (os.environ.get('USE_MOCK_INSTRUMENTS') != 'true'
        or os.environ.get('BOOTSTRAP_ON_STARTUP') != 'true'
        or not re.fullmatch(r'sqlite:////tmp/pc04a4a-[A-Za-z0-9]+/browser.sqlite', _url)
        or not _path.parent.is_dir() or _path.exists()):
    raise RuntimeError('仅允许mktemp新建/tmp/pc04a4a-*目录的新SQLite及全Mock默认bootstrap')

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
    manifest = {'database': str(engine.url), 'labs': [], 'evidence_boundary': '全HAL Mock，非现场验收'}
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
            model = db.get(InstrumentModel, category.selected_model_id)
            if model is not None and connection is not None:
                bindings.append(dict(category_id=str(category.id), instrument_model_id=str(model.id),
                    connection_endpoint=connection.endpoint, driver_mode='mock'))
        switch = next(c for c in categories if c.category_key == 'rfSwitch')
        switch_id = str(switch.id)
        for suffix in ('甲', '乙'):
            chamber = create_chamber_from_preset(ChamberType.TYPE_C.value, name=f'PC04A4a暗室{suffix}')
            db.add(chamber); db.flush()
            lab = LabProfile(name=f'PC04A4a标称{suffix}', chamber_config_id=chamber.id,
                is_active=True, instrument_bindings=bindings)
            db.add(lab); db.flush()
            manifest['labs'].append({'name': lab.name, 'lab_id': str(lab.id), 'chamber_id': str(chamber.id)})
            if suffix == '甲':
                nodes = [dict(id=f'ce{i}', type='ce_port', label=f'B1.{i}', position={'x':30,'y':60+(i-1)*240}, params={'ports':['out']}) for i in (1,2)]
                nodes += [dict(id=f'probe{i}', type='probe', label=f'探头0{pol}', position={'x':540,'y':60+(i-1)*240},
                    params={'ports':['in'], 'probe_id':0, 'polarization':pol,
                        'rf_path_selection':{'connection_ids':[f'fixed-{pol.lower()}'], 'switch_mappings':[]}}) for i,pol in ((1,'V'),(2,'H'))]
                nodes += [dict(id='pa', type='amplifier', label='独立PA', position={'x':260,'y':460}, params={'ports':['in','out'],'visible_modes':['mimo_ota'],'unknown':{'keep':1}}),
                    dict(id='ref',type='reference_antenna',label='参考天线',position={'x':800,'y':60},params={'ports':['in'],'connection_scope':'calibration','visible_modes':['calibration']})]
                edges = [dict(id=f'fixed-{pol}',source=f'ce{i}',source_pin='out',target=f'probe{i}',target_pin='in',cable_loss_db=0) for i,pol in ((1,'v'),(2,'h'))]
                # 缺默认字段参考边，专门验证无关保存不注入默认键。
                edges += [dict(id='reference-sparse',source='probe1',source_pin='in',target='ref',target_pin='in')]
                topology = SwitchTopology(switch_category_id=switch.id,chamber_id=chamber.id,name='PC04A4a显式两链',
                    is_active=True,is_default=True,nodes=nodes,connections=edges,operating_modes=[
                        dict(id='mimo_ota',name='MIMO OTA 测试',active_connections=['fixed-v','fixed-h']),
                        dict(id='calibration',name='校准接线',active_connections=['reference-sparse'])])
                topology.update_statistics();db.add(topology);db.flush()
                manifest['labs'][-1]['topology_id'] = str(topology.id)
        db.commit()
        assert all(c.driver_mode == 'mock' for c in categories)
        assert all(b['driver_mode'] == 'mock' for lab in db.query(LabProfile).all() for b in lab.instrument_bindings)
    # 经真实HTTP端点导入CAICT旧图，不直接调用模板生成器。
    with TestClient(app) as client:
        lab = manifest['labs'][1]
        response = client.post('/api/v1/switch-topologies/import/from-template',params={
            'switch_category_id':switch_id,'lab_profile_id':lab['lab_id'],'template_id':'caict_v4'})
        assert response.status_code == 200, response.text
        lab['topology_id'] = response.json()['id']
        response = client.get(f"/api/v1/switch-topologies/{lab['topology_id']}",params={'lab_profile_id':lab['lab_id']})
        assert response.status_code == 200, response.text
        graph = response.json()
        assert any(e.get('pa_gain_db') is not None for e in graph['connections'])
        manifest['caict_pa_edges'] = [e for e in graph['connections'] if e.get('pa_gain_db') is not None]
        assert client.get('/api/v1/instruments/hal/status').json()['mode'] == 'mock'
    with SessionLocal() as db:
        assert all(c.driver_mode == 'mock' for c in db.query(InstrumentCategory).all())
        assert all(b['driver_mode'] == 'mock' for lab in db.query(LabProfile).all() for b in lab.instrument_bindings)
    print(json.dumps(manifest,ensure_ascii=False))


if __name__ == '__main__':
    seed()
