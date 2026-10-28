"""只读 SQLite 审计；绝不导入应用、初始化或 seed。"""
import hashlib
import json
import os
import re
import sqlite3
from pathlib import Path


def audit():
    url = os.environ.get('DATABASE_URL', '')
    assert re.fullmatch(r'sqlite:////tmp/pc04a5b-[A-Za-z0-9]+/browser.sqlite',url)
    assert os.environ.get('USE_MOCK_INSTRUMENTS') == 'true'
    path = Path(url.removeprefix('sqlite:///'))
    assert path.is_file()
    db = sqlite3.connect(f'file:{path}?mode=ro',uri=True)
    db.row_factory = sqlite3.Row
    tables = [row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
    result = {'database':str(path),'read_only':True,'topologies':[],'formal':{}}
    for row in db.execute('SELECT id,revision,name,chamber_id,switch_category_id,is_active,is_default,created_at FROM switch_topologies ORDER BY id'):
        history = db.execute('SELECT revision,operation,snapshot,restored_from_revision,recorded_metadata,created_at FROM switch_topology_revisions WHERE topology_id=? ORDER BY revision',(row['id'],)).fetchall()
        revisions = [r['revision'] for r in history]
        assert len(revisions) == len(set(revisions))
        assert not revisions or row['revision'] == max(revisions)
        assert revisions or row['revision'] == 0
        result['topologies'].append(dict(row,history_count=len(history),operations=[h['operation'] for h in history],
            history=[dict(h) for h in history],
            history_sha256=hashlib.sha256(json.dumps([dict(h) for h in history],sort_keys=True).encode()).hexdigest()))
    for table in tables:
        if any(token in table for token in ('execution','certificate','application','selection','route_calibration_run')):
            rows = [tuple(r) for r in db.execute(f'SELECT * FROM "{table}" ORDER BY 1')]
            result['formal'][table] = {'count':len(rows),'sha256':hashlib.sha256(repr(rows).encode()).hexdigest()}
    result['category_modes'] = [tuple(r) for r in db.execute('SELECT category_key,driver_mode FROM instrument_categories ORDER BY category_key')]
    assert all(mode == 'mock' for _,mode in result['category_modes'])
    bindings = [json.loads(row[0] or '[]') for row in db.execute('SELECT instrument_bindings FROM lab_profiles')]
    assert sum(map(len,bindings)) > 0
    assert all(binding['driver_mode'] == 'mock' for group in bindings for binding in group)
    result['binding_count'] = sum(map(len,bindings))
    db.close()
    return result


if __name__ == '__main__':
    print(json.dumps(audit(),ensure_ascii=False,indent=2))
