"""隔离brownfield迁移，原JSON文本逐字不变。"""
import json
import os
import subprocess
from pathlib import Path
from uuid import uuid4
import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

def load_migration():
    import importlib.util
    path = Path('alembic/versions/f28a91c7d6b3_topology_revisions.py')
    spec = importlib.util.spec_from_file_location('revision_migration', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_brownfield_upgrade_preserves_raw_and_is_idempotent(tmp_path):
    engine = create_engine('sqlite:///' + str(tmp_path / 'brownfield.sqlite'))
    values = [json.dumps([{'opaque':[True,1,'1',None], 'null':None}], ensure_ascii=False),
              '[{"id":"e","opaque":false}]', '[{"id":"m"}]']
    ident = uuid4().hex
    with engine.begin() as conn:
        conn.exec_driver_sql('PRAGMA foreign_keys=ON')
        conn.exec_driver_sql('CREATE TABLE switch_topologies (id UUID PRIMARY KEY, nodes JSON, connections JSON, operating_modes JSON)')
        conn.execute(text('INSERT INTO switch_topologies VALUES (:id,:n,:c,:m)'), dict(id=ident,n=values[0],c=values[1],m=values[2]))
        with Operations.context(MigrationContext.configure(conn)):
            load_migration().upgrade()
            load_migration().upgrade()
        row = conn.exec_driver_sql('SELECT nodes,connections,operating_modes,revision FROM switch_topologies').one()
        assert list(row[:3]) == values and row[3] == 0
        assert conn.exec_driver_sql('SELECT count(*) FROM switch_topology_revisions').scalar() == 0
        conn.execute(text('INSERT INTO switch_topology_revisions (id,topology_id,revision,operation,snapshot,recorded_metadata) VALUES (:id,:tid,0,\'baseline\',\'{}\',\'{}\')'),dict(id=uuid4().hex,tid=ident))
        with pytest.raises(IntegrityError):
            conn.execute(text('DELETE FROM switch_topologies WHERE id=:id'),dict(id=ident))
    with engine.begin() as conn:
        with Operations.context(MigrationContext.configure(conn)):
            load_migration().downgrade()
        assert conn.exec_driver_sql('SELECT nodes,connections,operating_modes FROM switch_topologies').one() == tuple(values)
    engine.dispose()


def test_fresh_alembic_head(tmp_path):
    env = dict(os.environ, DATABASE_URL='sqlite:///' + str(tmp_path / 'fresh.sqlite'), USE_MOCK_INSTRUMENTS='true',
               BOOTSTRAP_ON_STARTUP='true', LOG_DIR=str(tmp_path / 'logs'))
    result = subprocess.run([str(Path('.venv/bin/alembic').resolve()), 'upgrade', 'head'], env=env,
                            text=True, capture_output=True)
    assert result.returncode == 0, result.stdout + result.stderr
    engine = create_engine(env['DATABASE_URL'])
    with engine.connect() as conn:
        assert conn.exec_driver_sql('SELECT version_num FROM alembic_version').scalar() == 'f28a91c7d6b3'
        assert conn.exec_driver_sql('SELECT count(*) FROM switch_topology_revisions').scalar() == 0
    engine.dispose()
