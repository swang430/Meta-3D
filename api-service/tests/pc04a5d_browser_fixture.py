"""5d 专用隔离世界；任何 app 导入必须晚于 checked_path 的全部守卫。"""
import argparse
import asyncio
from contextlib import redirect_stdout
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys


SOURCE = Path(__file__).parent / 'fixtures/pc04a5c_caict_source.json'


def checked_path(kind: str) -> Path:
    url = os.environ.get('DATABASE_URL', '')
    assert kind in ('browser', 'test', 'full'), kind
    assert re.fullmatch(r'sqlite:////tmp/pc04a5d-[A-Za-z0-9]+/' + kind + r'\.sqlite', url), url
    path = Path(url.removeprefix('sqlite:///'))
    assert path.parent.is_dir() and not path.exists(), path
    assert os.environ.get('USE_MOCK_INSTRUMENTS') == 'true'
    assert os.environ.get('BOOTSTRAP_ON_STARTUP') == 'true'
    return path


def canonical_hash(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(',', ':')).encode()).hexdigest()


def audit_mock(db):
    """必须逐 Lab 非空；空类别、空 bindings 不构成 Mock 证明。"""
    from app.models.instrument import InstrumentCategory, InstrumentConnection
    from app.models.lab_profile import LabProfile
    db.expire_all()
    categories = [dict(id=str(c.id), key=c.category_key, driver_mode=c.driver_mode)
                  for c in db.query(InstrumentCategory).order_by(InstrumentCategory.category_key)]
    connections = [dict(id=str(c.id), endpoint=c.endpoint)
                   for c in db.query(InstrumentConnection).order_by(InstrumentConnection.id)]
    labs = [dict(id=str(l.id), bindings=deepcopy(l.instrument_bindings))
            for l in db.query(LabProfile).order_by(LabProfile.id)]
    assert categories and all(c['driver_mode'] == 'mock' for c in categories)
    assert connections and all(c['endpoint'] == '192.0.2.10' for c in connections)
    assert labs and all(l['bindings'] for l in labs)
    assert all(b['driver_mode'] == 'mock' and b['connection_endpoint'] == '192.0.2.10'
               for l in labs for b in l['bindings'])
    return dict(categories=categories, connections=connections, labs=labs)


def configure_mock(db):
    from app.models.instrument import InstrumentCategory, InstrumentConnection, InstrumentModel
    from app.models.lab_profile import LabProfile
    bindings = []
    for category in db.query(InstrumentCategory).all():
        category.driver_mode = 'mock'
        if category.category_key == 'signalAnalyzer':
            category.selected_model_id = db.query(InstrumentModel).filter_by(
                category_id=category.id, model='FSVA3000').one().id
        for connection in db.query(InstrumentConnection).filter_by(category_id=category.id):
            connection.endpoint = '192.0.2.10'
        if category.selected_model_id:
            bindings.append(dict(category_id=str(category.id),
                instrument_model_id=str(category.selected_model_id),
                connection_endpoint='192.0.2.10', driver_mode='mock'))
    assert bindings
    if not db.query(LabProfile).count():
        db.add(LabProfile(name='5d bootstrap Mock Lab', is_active=True,
                          instrument_bindings=deepcopy(bindings)))
    for lab in db.query(LabProfile):
        lab.instrument_bindings = deepcopy(bindings)
    db.commit()
    return audit_mock(db)


async def verify_hal():
    from app.services.instrument_hal_service import InstrumentHALService, is_mock_driver
    hal = InstrumentHALService()
    try:
        await hal.initialize()
        result = {key: dict(class_name=type(driver).__name__, is_mock_driver=is_mock_driver(driver))
                  for key, driver in hal.drivers.items()}
        assert {'channelEmulator', 'signalAnalyzer'} <= set(result), result
        assert all(row['is_mock_driver'] for row in result.values()), result
        return result
    finally:
        await hal.shutdown()


def bootstrap_mock_database(kind: str = 'browser') -> dict:
    path = checked_path(kind)
    from app.main import app  # noqa: F401；必须留在全部守卫之后。
    from app.db.database import Base, engine, SessionLocal
    from app.services.bootstrap import run_bootstrap_on_startup
    Base.metadata.create_all(engine)
    assert run_bootstrap_on_startup(SessionLocal) is True
    with SessionLocal() as db:
        audit = configure_mock(db)
    result = dict(database=str(path), mock_audit=audit, selected_hal=asyncio.run(verify_hal()),
                  source_fixture_canonical_hash=canonical_hash(json.loads(SOURCE.read_text())),
                  boundary='新SQLite/全绑定Mock软件验收，非现场实测、采集资格或正式校准')
    result['source_commit'] = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()
    result['tracked_diff_sha256'] = hashlib.sha256(subprocess.check_output(['git', 'diff', 'HEAD'])).hexdigest()
    result['input_sha256'] = {str(path.relative_to(SOURCE.parents[2])):hashlib.sha256(path.read_bytes()).hexdigest()
        for path in (SOURCE,Path(__file__),Path(__file__).with_name('test_pc04a5d_topology_acceptance.py'),
                     SOURCE.parents[2] / 'scripts/pc04a5c_independent_pa.py')}
    return result


def declaration_graph():
    """独立小图：用于已存 synthetic 消费者输入及 Mock 采集，不代表 32 路图资格。"""
    def node(ident, kind, x, **params):
        return dict(id=ident, type=kind, label=ident, position={'x':x, 'y':100}, params=params)
    ports = dict(ports=['in','out'], port_directions={'in':'input','out':'output'},
                 internal_paths=[{'from_port':'in','to_port':'out'}])
    nodes = [node('ce', 'ce_port', 0, ports=['out','other'],
                  port_directions={'out':'output','other':'output'}, ce_port='B1.1'),
             node('pa', 'amplifier', 180, **deepcopy(ports), gain_db=20),
             node('probe', 'probe', 360, ports=['in','ref'],
                  port_directions={'in':'input','ref':'output'}, probe_id=0, polarization='V',
                  rf_path_selection={'connection_ids':['a','b'], 'switch_mappings':[]}),
             node('reference', 'reference_antenna', 540, **deepcopy(ports), connection_scope='calibration'),
             node('rx', 'receive_cable', 720, **deepcopy(ports), connection_scope='calibration'),
             node('sa', 'signal_analyzer', 900, ports=['in'],
                  port_directions={'in':'input'}, connection_scope='calibration')]
    connections = [dict(id=ident, source=source, source_pin=sp, target=target, target_pin=tp,
                        cable_loss_db=loss, modes=[mode])
                   for ident,source,sp,target,tp,loss,mode in [
                       ('a','ce','out','pa','in',2,'mimo_ota'),
                       ('b','pa','out','probe','in',3,'mimo_ota'),
                       ('ref','probe','ref','reference','in',0,'calibration'),
                       ('rx-in','reference','out','rx','in',2,'calibration'),
                       ('rx-out','rx','out','sa','in',0,'calibration')]]
    connections[1]['calibrated_loss_db'] = 99
    return dict(nodes=nodes, connections=connections, operating_modes=[
        dict(id='mimo_ota',name='正常',active_connections=['a','b']),
        dict(id='calibration',name='参考',active_connections=['ref','rx-in','rx-out'])])


def seed_world(db):
    from app.models.chamber import ChamberType, create_chamber_from_preset
    from app.models.instrument import InstrumentCategory
    from app.models.lab_profile import LabProfile
    from app.models.switch_topology import SwitchTopology
    source = json.loads(SOURCE.read_text())
    category = db.query(InstrumentCategory).filter_by(category_key='rfSwitch').one()
    bindings = deepcopy(db.query(LabProfile).first().instrument_bindings)
    chambers = [create_chamber_from_preset(ChamberType.TYPE_C.value, name=f'5d隔离暗室{i}') for i in range(2)]
    db.add_all(chambers); db.flush()
    labs = [LabProfile(name=f'5d隔离Lab{name}', chamber_config_id=chambers[index].id,
                       is_active=True, instrument_bindings=deepcopy(bindings))
            for name,index in [('A',0),('A共享',0),('B',1)]]
    db.add_all(labs); db.flush()
    original = SwitchTopology(name='5d完整原raw（隔离r0）', chamber_id=chambers[0].id,
        switch_category_id=category.id, version=source['version'], description=source.get('description'),
        nodes=deepcopy(source['nodes']), connections=deepcopy(source['connections']),
        operating_modes=deepcopy(source['operating_modes']), is_active=True, is_default=True)
    small = SwitchTopology(name='5d独立声明与synthetic历史输入图', chamber_id=chambers[1].id,
        switch_category_id=category.id, is_active=True, is_default=True, **declaration_graph())
    exercise = SwitchTopology(name='5d独立鼠标端口练习图', chamber_id=chambers[1].id,
        switch_category_id=category.id, is_active=False, is_default=False, **declaration_graph())
    for row in (original, small, exercise):
        row.update_statistics(); db.add(row)
    db.commit()
    return dict(category_id=str(category.id), labs=[dict(lab_id=str(l.id),chamber_id=str(l.chamber_config_id)) for l in labs],
        source_id=str(original.id), collection_id=str(small.id), port_exercise_id=str(exercise.id),
        mock_audit=audit_mock(db), source_origin='仅外层身份新建，legacy r0三个raw数组完全原样',
        synthetic_boundary='已存confirmed模型输入仅验恢复/冻结/消费者；未采集、未核采用资格')


def seed() -> dict:
    manifest = bootstrap_mock_database()
    from app.db.database import SessionLocal
    from scripts.pc04a5c_independent_pa import build_candidate
    with SessionLocal() as db:
        manifest.update(seed_world(db))
    candidate, routes = build_candidate(json.loads(SOURCE.read_text()))
    manifest.update(candidate_hash=canonical_hash(candidate), manifest_hash=canonical_hash(routes))
    manifest['selected_hal_after_seed'] = asyncio.run(verify_hal())
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--bootstrap-only', action='store_true')
    parser.add_argument('--kind', default='browser', choices=['browser','test','full'])
    args = parser.parse_args()
    assert args.bootstrap_only or args.kind == 'browser'
    # 初始化期间的既有日志写到stderr，stdout只交付一份可解析manifest。
    with redirect_stdout(sys.stderr):
        result = bootstrap_mock_database(args.kind) if args.bootstrap_only else seed()
    print(json.dumps(result, ensure_ascii=False))
