"""Task6隔离浏览器种子；必须显式临时DB，绝不写用户实验室。"""
import os
import copy
import sys
from pathlib import Path

if os.environ.get('USE_MOCK_INSTRUMENTS') != 'true' or not os.environ.get('DATABASE_URL', '').startswith('sqlite:////tmp/pc06a1-'):
    raise RuntimeError('Task6 fixture仅允许显式全Mock和专属/tmp SQLite，不使用默认数据库')

from app.db.database import Base, engine, SessionLocal
from app.main import app  # 与正式启动一致，先完成路由/模型加载。
from app.models.instrument import InstrumentCategory, InstrumentModel, InstrumentConnection
from tests.test_rf_chain_resolver import chamber, topology_two_chains, lab_profile
from tests.test_pc_04a_fixed_route_api import configured


def seed(*, include_switch=True):
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        from app.models.lab_profile import LabProfile
        if db.query(LabProfile).count():
            return
        room = chamber.__wrapped__(db)
        topo = topology_two_chains.__wrapped__(db, room)
        lab = lab_profile.__wrapped__(db, room, topo)
        configured.__wrapped__(db, lab)
        lab.name = 'PC06A1 隔离全Mock验收'
        if not include_switch:
            db.commit()
            return
        cat = InstrumentCategory(category_key='rfSwitch', category_name='隔离开关', driver_mode='mock')
        db.add(cat); db.flush()
        model = InstrumentModel(category_id=cat.id, model='EMCenter', vendor='ETS', capabilities={})
        db.add(model); db.flush(); cat.selected_model_id = model.id
        db.add(InstrumentConnection(category_id=cat.id, endpoint='192.0.2.20', created_by='Task6'))
        lab.instrument_bindings = [*lab.instrument_bindings, dict(category_id=str(cat.id),
            instrument_model_id=str(model.id), connection_endpoint='192.0.2.20', driver_mode='mock')]
        topo.switch_category_id = cat.id
        topo.name = 'PC06A1 双通路与校准接线'
        nodes = copy.deepcopy(topo.nodes)
        edges = copy.deepcopy(topo.connections)
        for index, pol in enumerate(('v', 'h')):
            probe = f'probe_0_{pol}'
            for suffix, kind in [('air', 'air_path'), ('ref', 'reference_antenna'),
                                 ('rx', 'receive_cable'), ('sa', 'signal_analyzer')]:
                nodes.append(dict(id=f'{pol}_{suffix}', type=kind, label=f'{pol.upper()} {kind}',
                    params={'connection_scope': 'calibration'}))
            previous = probe
            for suffix in ('air', 'ref', 'rx', 'sa'):
                target = f'{pol}_{suffix}'
                edges.append(dict(id=f'{pol}_{suffix}_edge', source=previous, target=target,
                    modes=['calibration']))
                previous = target
        for index, node in enumerate(nodes):
            node['position'] = {'x': (index % 6) * 160, 'y': (index // 6) * 180}
        topo.nodes = list(nodes); topo.connections = list(edges)
        topo.operating_modes = [*topo.operating_modes, dict(id='calibration', name='校准接线',
            active_connections=[e['id'] for e in edges if 'calibration' in e.get('modes', [])])]
        db.commit()
        print({'lab_id': str(lab.id), 'topology_id': str(topo.id), 'database': str(engine.url)})


def damage_child(job_id):
    """仅隔离DB故障fixture，供新页面缺child身份拒绝继续验收；不增加生产端点。"""
    from uuid import UUID
    from app.models.diagnostic_run import DiagnosticRun
    from app.services.calibration.route_batch_jobs import _payload, _save_parent
    with SessionLocal() as db:
        row=db.get(DiagnosticRun,UUID(job_id))
        assert row is not None
        value=_payload(row)
        assert value['status']=='waiting_manual' and value['current_index']==2
        assert value['items'][0]['status']=='simulated' and value['items'][0]['run_id']
        value['items'][0]['run_id']=None
        _save_parent(row,value);db.commit()
        print({'damaged_job':job_id,'missing_child':value['items'][0]['item_id']})


if __name__ == '__main__':
    if len(sys.argv)==3 and sys.argv[1]=='--damage-child':
        damage_child(sys.argv[2])
    else:
        seed()
