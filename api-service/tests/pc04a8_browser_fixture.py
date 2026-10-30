"""PC04A8 全 Mock 隔离世界；守卫通过前不导入 app。"""
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


SOURCE = Path('/tmp/pc04a5d-BVAwTu/source-before.json')


def synthetic_graph_32() -> dict:
    """32份独立声明图；只供模拟输入，不挪用现场线缆或参考证据。"""
    from tests.pc04a5d_browser_fixture import declaration_graph
    graph = dict(nodes=[], connections=[], operating_modes=[
        dict(id='mimo_ota', name='正常', active_connections=[]),
        dict(id='calibration', name='参考', active_connections=[])])
    for i in range(1, 33):
        part = deepcopy(declaration_graph())
        prefix = f'synthetic-{i:02d}-'
        for node in part['nodes']:
            node['id'] = prefix + node['id']
            node['label'] = node['id']
            node['position']['y'] = i * 180
            if node['type'] == 'ce_port': node['params']['ce_port'] = f'B{i}'
            if node['type'] == 'probe':
                node['params'].update(probe_id=(i-1)//2, polarization='V' if i%2 else 'H')
                node['params']['rf_path_selection']['connection_ids'] = [prefix+'a', prefix+'b']
        for edge in part['connections']:
            for key in ('id', 'source', 'target'): edge[key] = prefix + edge[key]
        graph['nodes'].extend(part['nodes'])
        graph['connections'].extend(part['connections'])
        for target, mode in zip(graph['operating_modes'], part['operating_modes'], strict=True):
            target['active_connections'].extend(prefix+key for key in mode['active_connections'])
    return graph


def bootstrap_mock_database(kind: str = 'browser') -> dict:
    assert kind in ('browser', 'test', 'full')
    url = os.environ.get('DATABASE_URL', '')
    assert re.fullmatch(r'sqlite:////tmp/pc04a8-[A-Za-z0-9]+/' + kind + r'\.sqlite', url), url
    path = Path(url.removeprefix('sqlite:///'))
    assert path.parent.is_dir() and not path.exists(), path
    assert os.environ.get('USE_MOCK_INSTRUMENTS') == 'true'
    assert os.environ.get('BOOTSTRAP_ON_STARTUP') == 'true'
    from app.main import app  # noqa: F401
    from app.db.database import Base, engine, SessionLocal
    from app.services.bootstrap import run_bootstrap_on_startup
    from tests.pc04a5d_browser_fixture import configure_mock, audit_mock, verify_hal
    Base.metadata.create_all(engine)
    assert run_bootstrap_on_startup(SessionLocal) is True
    with SessionLocal() as db:
        configure_mock(db)
        audit = audit_mock(db)
    return dict(database=str(path), mock_audit=audit, selected_hal=asyncio.run(verify_hal()),
        source_commit=subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
        tracked_diff_sha256=hashlib.sha256(subprocess.check_output(['git', 'diff', 'HEAD'])).hexdigest(),
        fixture_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        boundary='synthetic单路和32路/全Mock软件演练，非实测或正式校准')


def seed_world(db, source_path: Path | None = None) -> dict:
    from app.models.chamber import ChamberType, create_chamber_from_preset
    from app.models.instrument import InstrumentCategory
    from app.models.lab_profile import LabProfile
    from app.models.switch_topology import SwitchTopology
    from tests.pc04a5d_browser_fixture import declaration_graph
    chamber = create_chamber_from_preset(ChamberType.TYPE_C.value, name='PC04A8 synthetic隔离暗室')
    db.add(chamber); db.flush()
    lab = LabProfile(name='PC04A8 synthetic Mock Lab', chamber_config_id=chamber.id,
        is_active=True, instrument_bindings=deepcopy(db.query(LabProfile).first().instrument_bindings))
    db.add(lab); db.flush()
    graph = declaration_graph()
    sa = db.query(InstrumentCategory).filter_by(category_key='signalAnalyzer').one()
    next(node for node in graph['nodes'] if node['id'] == 'sa')['params']['instrument_category_id'] = str(sa.id)
    rf = db.query(InstrumentCategory).filter_by(category_key='rfSwitch').one()
    topology = SwitchTopology(name='PC04A8 synthetic单路', chamber_id=chamber.id,
        switch_category_id=rf.id, is_active=True, is_default=True, **graph)
    topology.update_statistics(); db.add(topology); db.commit()
    result = dict(collection_id=str(topology.id), lab_id=str(lab.id), chamber_id=str(chamber.id))
    from tests.pc04a5d_browser_fixture import canonical_hash
    worlds = [('matrix', synthetic_graph_32())]
    if source_path is not None:
        source_bytes = source_path.read_bytes()  # 显式本地诊断缺快照时失败，不替代为别的图。
        source = json.loads(source_bytes)
        source_arrays = {key: deepcopy(source[key]) for key in ('nodes', 'connections', 'operating_modes')}
        worlds.insert(0, ('source', source_arrays))
    for key, world in worlds:
        extra_chamber = create_chamber_from_preset(ChamberType.TYPE_C.value, name=f'PC04A8 {key}隔离暗室')
        db.add(extra_chamber); db.flush()
        extra_lab = LabProfile(name=f'PC04A8 {key} Mock Lab', chamber_config_id=extra_chamber.id,
            is_active=True, instrument_bindings=deepcopy(lab.instrument_bindings))
        db.add(extra_lab); db.flush()
        if key == 'matrix':
            for node in world['nodes']:
                if node['type'] == 'signal_analyzer':
                    node['params']['instrument_category_id'] = str(sa.id)
        extra = SwitchTopology(name=f'PC04A8 {key}', chamber_id=extra_chamber.id,
            switch_category_id=rf.id, is_active=True, is_default=True, **world)
        extra.update_statistics(); db.add(extra); db.commit(); db.refresh(extra)
        result[key+'_id'] = str(extra.id)
        result[key+'_lab_id'] = str(extra_lab.id)
        if key == 'source':
            result['source_sha256'] = hashlib.sha256(source_bytes).hexdigest()
            result['source_arrays_hash'] = {k: canonical_hash(v) for k,v in source_arrays.items()}
            result['source_readback_hash'] = {k: canonical_hash(getattr(extra,k)) for k in source_arrays}
            assert result['source_arrays_hash'] == result['source_readback_hash']
    result['chain_to_index'] = {f'synthetic-{i+1:02d}-b': i for i in range(32)}
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--bootstrap-only', action='store_true')
    parser.add_argument('--kind', default='browser', choices=['browser', 'test', 'full'])
    parser.add_argument('--source-snapshot', type=Path, help='显式本地r6诊断快照；不用于synthetic期望')
    args = parser.parse_args()
    with redirect_stdout(sys.stderr):
        result = bootstrap_mock_database(args.kind)
        if not args.bootstrap_only:
            from app.db.database import SessionLocal
            from tests.pc04a5d_browser_fixture import audit_mock, verify_hal
            with SessionLocal() as db:
                result.update(seed_world(db, source_path=args.source_snapshot))
                result['mock_audit_after_seed'] = audit_mock(db)
            result['selected_hal_after_seed'] = asyncio.run(verify_hal())
    print(json.dumps(result, ensure_ascii=False))
