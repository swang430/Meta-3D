"""5c 全新隔离库；路径、Mock 与不存在检查严格先于任何应用导入。"""
import argparse
import asyncio
from copy import deepcopy
import json
import os
from pathlib import Path
import re


def bootstrap_mock_database() -> dict:
    url = os.environ.get('DATABASE_URL', '')
    assert re.fullmatch(r'sqlite:////tmp/pc04a5c-[A-Za-z0-9]+/(browser|test)\.sqlite', url), url
    path = Path(url.removeprefix('sqlite:///'))
    assert path.parent.is_dir() and not path.exists(), path
    assert os.environ.get('USE_MOCK_INSTRUMENTS') == 'true'
    assert os.environ.get('BOOTSTRAP_ON_STARTUP') == 'true'
    from app.main import app
    from app.db.database import Base, engine, SessionLocal
    from app.services.bootstrap import run_bootstrap_on_startup
    from app.models.instrument import InstrumentCategory, InstrumentConnection, InstrumentModel
    from app.models.lab_profile import LabProfile
    Base.metadata.create_all(engine)
    assert run_bootstrap_on_startup(SessionLocal) is True
    with SessionLocal() as db:
        bindings = []
        for category in db.query(InstrumentCategory).all():
            category.driver_mode = 'mock'
            if category.category_key == 'signalAnalyzer':
                category.selected_model_id = db.query(InstrumentModel).filter_by(
                    category_id=category.id, model='FSVA3000').one().id
            connection = db.query(InstrumentConnection).filter_by(category_id=category.id).one_or_none()
            if connection is not None:
                connection.endpoint = '192.0.2.10'
                if category.selected_model_id:
                    bindings.append(dict(category_id=str(category.id),
                        instrument_model_id=str(category.selected_model_id),
                        connection_endpoint='192.0.2.10', driver_mode='mock'))
        assert bindings
        if not db.query(LabProfile).count():
            db.add(LabProfile(name='PC04A5c bootstrap Mock Lab', is_active=True,
                              instrument_bindings=deepcopy(bindings)))
        for lab in db.query(LabProfile).all():
            lab.instrument_bindings = [dict(b, driver_mode='mock', connection_endpoint='192.0.2.10')
                                       for b in lab.instrument_bindings or bindings]
        db.commit()
        db.expire_all()
        categories = db.query(InstrumentCategory).all()
        actual = [b for lab in db.query(LabProfile).all() for b in lab.instrument_bindings or []]
        assert categories and all(c.driver_mode == 'mock' for c in categories)
        assert actual and all(b['driver_mode'] == 'mock' and b['connection_endpoint'] == '192.0.2.10' for b in actual)
    from app.services.instrument_hal_service import InstrumentHALService, is_mock_driver
    async def verify_hal():
        hal = InstrumentHALService()
        try:
            await hal.initialize()
            result = {key: dict(class_name=type(driver).__name__, is_mock_driver=is_mock_driver(driver))
                      for key, driver in hal.drivers.items()}
            assert result and all(row['is_mock_driver'] for row in result.values()), result
            return result
        finally:
            await hal.shutdown()
    return dict(database=str(path), category_count=len(categories), binding_count=len(actual),
                all_category_and_lab_bindings_mock=True, selected_hal=asyncio.run(verify_hal()),
                boundary='新SQLite与Mock软件夹具，非现场实测；不访问默认库')


def seed() -> dict:
    manifest = bootstrap_mock_database()
    assert manifest['database'].endswith('/browser.sqlite')
    from app.db.database import SessionLocal
    from app.models.chamber import ChamberType, create_chamber_from_preset
    from app.models.instrument import InstrumentCategory
    from app.models.lab_profile import LabProfile
    from app.models.switch_topology import SwitchTopology
    source = json.loads((Path(__file__).parent / 'fixtures/pc04a5c_caict_source.json').read_text())
    with SessionLocal() as db:
        category = db.query(InstrumentCategory).filter_by(category_key='rfSwitch').one()
        bindings = deepcopy(db.query(LabProfile).first().instrument_bindings)
        manifest['labs'] = []
        for index in range(2):
            chamber = create_chamber_from_preset(ChamberType.TYPE_C.value, name=f'PC04A5c隔离暗室{index}')
            db.add(chamber); db.flush()
            lab = LabProfile(name=f'PC04A5c隔离实验室{index}', chamber_config_id=chamber.id,
                             is_active=True, instrument_bindings=deepcopy(bindings))
            db.add(lab); db.flush()
            manifest['labs'].append(dict(lab_id=str(lab.id), chamber_id=str(chamber.id)))
            if index == 0:
                row = SwitchTopology(name='PC04A5c完整原raw（隔离旧行）', chamber_id=chamber.id,
                    switch_category_id=category.id, description=source.get('description'),
                    version=source['version'], nodes=deepcopy(source['nodes']),
                    connections=deepcopy(source['connections']), operating_modes=deepcopy(source['operating_modes']),
                    is_active=True, is_default=True)
                row.update_statistics(); db.add(row); db.flush()
                manifest['source_id'] = str(row.id)
        db.commit()
        actual = [b for lab in db.query(LabProfile).all() for b in lab.instrument_bindings or []]
        assert actual and all(b['driver_mode'] == 'mock' and b['connection_endpoint'] == '192.0.2.10' for b in actual)
    manifest['source_origin'] = '明确legacy ORM夹具，仅替换外层DB身份；三个raw数组完全原样'
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--bootstrap-only', action='store_true')
    args = parser.parse_args()
    print(json.dumps(bootstrap_mock_database() if args.bootstrap_only else seed(), ensure_ascii=False))
