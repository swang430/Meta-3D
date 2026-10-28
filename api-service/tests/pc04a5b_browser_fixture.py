"""5b 专用全新 Mock 库。路径校验严格先于任何应用导入。"""
import argparse
import asyncio
import json
import os
import re
from copy import deepcopy
from pathlib import Path
from uuid import UUID


def checked_path(full=False):
    url = os.environ.get('DATABASE_URL', '')
    filename = 'full.sqlite' if full else 'browser.sqlite'
    assert re.fullmatch(r'sqlite:////tmp/pc04a5b-[A-Za-z0-9]+/' + filename, url), url
    path = Path(url.removeprefix('sqlite:///'))
    assert path.parent.is_dir() and not path.exists(), path
    assert os.environ.get('USE_MOCK_INSTRUMENTS') == 'true'
    assert os.environ.get('BOOTSTRAP_ON_STARTUP') == 'true'
    return path


def bootstrap_mock_database(full=False):
    path = checked_path(full)
    from app.main import app
    from app.db.database import Base, engine, SessionLocal
    from app.services.bootstrap import run_bootstrap_on_startup
    from app.models.instrument import InstrumentCategory, InstrumentConnection, InstrumentModel
    from app.models.lab_profile import LabProfile
    Base.metadata.create_all(engine)
    assert run_bootstrap_on_startup(SessionLocal) is True
    with SessionLocal() as db:
        default_bindings = []
        for category in db.query(InstrumentCategory).all():
            category.driver_mode = 'mock'
            if category.category_key == 'signalAnalyzer':
                category.selected_model_id = db.query(InstrumentModel).filter_by(
                    category_id=category.id, model='FSVA3000').one().id
            connection = db.query(InstrumentConnection).filter_by(category_id=category.id).one_or_none()
            if connection is not None:
                connection.endpoint = '192.0.2.10'
                if category.selected_model_id:
                    default_bindings.append(dict(category_id=str(category.id),
                        instrument_model_id=str(category.selected_model_id),
                        connection_endpoint=connection.endpoint,driver_mode='mock'))
        assert default_bindings
        if not db.query(LabProfile).count():
            db.add(LabProfile(name='PC04A5b bootstrap Mock Lab', is_active=True,
                              instrument_bindings=deepcopy(default_bindings)))
            db.flush()
        for lab in db.query(LabProfile).all():
            lab.instrument_bindings = [dict(b, driver_mode='mock', connection_endpoint='192.0.2.10')
                                       for b in (lab.instrument_bindings or default_bindings)]
        db.commit()
        db.expire_all()
        categories = db.query(InstrumentCategory).all()
        bindings = [b for lab in db.query(LabProfile).all() for b in (lab.instrument_bindings or [])]
        assert categories and all(c.driver_mode == 'mock' for c in categories)
        assert bindings and all(b['driver_mode'] == 'mock' for b in bindings)
        manifest = {'database': str(path), 'category_count': len(categories), 'binding_count': len(bindings),
                    'all_category_and_lab_bindings_mock': True, 'boundary': 'synthetic软件夹具，非现场实测'}
    return manifest


def seed():
    manifest = bootstrap_mock_database()
    from app.main import app
    from app.db.database import SessionLocal
    from app.models.chamber import ChamberType, create_chamber_from_preset
    from app.models.instrument import InstrumentCategory, InstrumentConnection
    from app.models.lab_profile import LabProfile
    from app.models.switch_topology import SwitchTopology
    from fastapi.testclient import TestClient
    with SessionLocal() as db:
        categories = db.query(InstrumentCategory).all()
        bindings = []
        for category in categories:
            connection = db.query(InstrumentConnection).filter_by(category_id=category.id).one_or_none()
            if category.selected_model_id and connection is not None:
                bindings.append(dict(category_id=str(category.id), instrument_model_id=str(category.selected_model_id),
                                     connection_endpoint=connection.endpoint, driver_mode='mock'))
        assert bindings
        second = InstrumentCategory(category_key='pc04a5bSecondSwitch', category_name='PC04A5b隔离开关乙', driver_mode='mock')
        db.add(second); db.flush()
        switches = [next(c for c in categories if c.category_key == 'rfSwitch'), second]
        manifest['categories'] = [str(c.id) for c in switches]
        manifest['labs'] = []
        for index in range(2):
            chamber = create_chamber_from_preset(ChamberType.TYPE_C.value, name=f'PC04A5b暗室{index}')
            db.add(chamber); db.flush()
            lab = LabProfile(name=f'PC04A5b实验室{index}', chamber_config_id=chamber.id,
                             is_active=True, instrument_bindings=deepcopy(bindings))
            db.add(lab); db.flush()
            manifest['labs'].append({'lab_id': str(lab.id), 'chamber_id': str(chamber.id), 'topologies': []})
            if index == 0:
                shared = LabProfile(name='PC04A5b共享暗室Lab', chamber_config_id=chamber.id,
                                    is_active=True, instrument_bindings=deepcopy(bindings))
                db.add(shared); db.flush(); manifest['shared_lab_id'] = str(shared.id)
        legacy = SwitchTopology(chamber_id=UUID(manifest['labs'][0]['chamber_id']), switch_category_id=switches[0].id,
            name='PC04A5b legacy r0', nodes=[
                dict(id='ce', type='ce_port', label='B1.1', position={'x':50,'y':90}, params={'ce_port':'B1.1'}),
                dict(id='probe', type='probe', label='探头0V', position={'x':500,'y':90},
                     params={'ports':['in'],'probe_id':0,'polarization':'V'})],
            connections=[dict(id='e',source='ce',target='probe',cable_loss_db='1.25',calibrated_loss_db=2.5,
                              calibrated_phase_deg=3.0,opaque={'bool':True,'number':'2'})],
            operating_modes=[dict(id='mimo_ota',name='MIMO OTA',active_connections=['e'])],
            is_active=True,is_default=True)
        legacy.update_statistics(); db.add(legacy); db.flush()
        manifest['legacy_id'] = str(legacy.id)
        manifest['legacy_source'] = '明确直写ORM旧行r0，未生成历史；非用户原图'
        db.commit()
    # 新图必须经真实生产HTTP入口创建，逐次真实PATCH制造分页历史。
    client = TestClient(app)
    for i, lab in enumerate(manifest['labs']):
        for c, category in enumerate(manifest['categories']):
            response = client.post('/api/v1/switch-topologies', json=dict(name='PC04A5b同名图',
                lab_profile_id=lab['lab_id'],switch_category_id=category,nodes=[],connections=[],operating_modes=[]))
            assert response.status_code == 201, response.text
            row = response.json(); lab['topologies'].append(row['id'])
            if i == c == 0:
                for number in range(101):
                    response = client.patch(f"/api/v1/switch-topologies/{row['id']}",
                        params={'lab_profile_id':lab['lab_id']},
                        json={'expected_revision':row['revision'],'description':f'分页真实保存{number}'})
                    assert response.status_code == 200, response.text
                    row = response.json()
                manifest['pagination_id'] = row['id']
                manifest['pagination_revision'] = row['revision']
                manifest['pagination_history_count'] = 102
    from app.services.instrument_hal_service import InstrumentHALService, is_mock_driver
    async def verify_hal():
        hal = InstrumentHALService()
        await hal.initialize()
        result = {key: {'class':type(value).__name__,'is_mock_driver':is_mock_driver(value)} for key,value in hal.drivers.items()}
        assert result and all(r['is_mock_driver'] for r in result.values()), result
        await hal.shutdown()
        return result
    manifest['selected_hal'] = asyncio.run(verify_hal())
    with SessionLocal() as db:
        categories = db.query(InstrumentCategory).all()
        labs = db.query(LabProfile).all()
        bindings = [b for lab in labs for b in (lab.instrument_bindings or [])]
        assert bindings and all(c.driver_mode == 'mock' for c in categories)
        assert all(b['driver_mode'] == 'mock' for b in bindings)
        manifest.update(category_count=len(categories),binding_count=len(bindings),lab_count=len(labs))
    return manifest


def add_invalid_case():
    """仅向已建成本片隔离库新增一张明确旧r0夹具，绝不改已有历史。"""
    url = os.environ.get('DATABASE_URL', '')
    assert re.fullmatch(r'sqlite:////tmp/pc04a5b-[A-Za-z0-9]+/browser.sqlite',url)
    assert Path(url.removeprefix('sqlite:///')).is_file()
    assert os.environ.get('USE_MOCK_INSTRUMENTS') == 'true'
    assert os.environ.get('BOOTSTRAP_ON_STARTUP') == 'true'
    from app.main import app
    from app.db.database import SessionLocal
    from app.models.instrument import InstrumentCategory
    from app.models.lab_profile import LabProfile
    from app.models.switch_topology import SwitchTopology
    from fastapi.testclient import TestClient
    with SessionLocal() as db:
        assert all(c.driver_mode == 'mock' for c in db.query(InstrumentCategory).all())
        labs = db.query(LabProfile).all()
        bindings = [b for lab in labs for b in (lab.instrument_bindings or [])]
        assert bindings and all(b['driver_mode'] == 'mock' for b in bindings)
        lab = db.query(LabProfile).filter_by(name='PC04A5b实验室0').one()
        category = db.query(InstrumentCategory).filter_by(category_key='rfSwitch').one()
        assert not db.query(SwitchTopology).filter_by(name='PC04A5b非法旧r0夹具').count()
        row = SwitchTopology(name='PC04A5b非法旧r0夹具',chamber_id=lab.chamber_config_id,
            switch_category_id=category.id,nodes=[],connections=[dict(id='bad',source='missing',target='absent')],
            operating_modes=[],is_active=False,is_default=False)
        row.update_statistics();db.add(row);db.commit()
        identity, lab_id = str(row.id), str(lab.id)
    client=TestClient(app)
    result=client.patch(f'/api/v1/switch-topologies/{identity}',params={'lab_profile_id':lab_id},
        json={'expected_revision':0,'connections':[]})
    assert result.status_code == 200, result.text
    return {'database':url,'id':identity,'lab_id':lab_id,'revision':result.json()['revision'],
            'origin':'新增显式legacy r0非法引用夹具；真实PATCH修正当前图，未改任何历史行'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--bootstrap-only',action='store_true')
    parser.add_argument('--add-invalid-case',action='store_true')
    args = parser.parse_args()
    assert not (args.bootstrap_only and args.add_invalid_case)
    print(json.dumps(add_invalid_case() if args.add_invalid_case else bootstrap_mock_database(True) if args.bootstrap_only else seed(), ensure_ascii=False))
