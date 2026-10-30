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
        boundary='synthetic单路/全Mock软件演练，非实测或正式校准')


def seed_world(db) -> dict:
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
    return dict(collection_id=str(topology.id), lab_id=str(lab.id), chamber_id=str(chamber.id))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--bootstrap-only', action='store_true')
    parser.add_argument('--kind', default='browser', choices=['browser', 'test', 'full'])
    args = parser.parse_args()
    with redirect_stdout(sys.stderr):
        result = bootstrap_mock_database(args.kind)
        if not args.bootstrap_only:
            from app.db.database import SessionLocal
            from tests.pc04a5d_browser_fixture import audit_mock, verify_hal
            with SessionLocal() as db:
                result.update(seed_world(db))
                result['mock_audit_after_seed'] = audit_mock(db)
            result['selected_hal_after_seed'] = asyncio.run(verify_hal())
    print(json.dumps(result, ensure_ascii=False))
