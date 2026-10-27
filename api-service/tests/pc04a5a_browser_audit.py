"""只读核对本片新库的浏览器写入；不导入 app，不访问默认数据库。"""
import json
import re
import sqlite3
import sys
from copy import deepcopy
from pathlib import Path


def audit(database: str) -> dict:
    assert re.fullmatch(r'/tmp/pc04a5a-[A-Za-z0-9]+/browser.sqlite', database)
    path = Path(database)
    assert path.is_file()
    manifest = json.loads((path.parent / 'seed.txt').read_text().splitlines()[-1])
    assert manifest['database'] == database and manifest['mock_verified_after_commit']
    with sqlite3.connect(f'file:{database}?mode=ro', uri=True) as db:
        db.row_factory = sqlite3.Row
        rows = {row['name']: dict(row) for row in db.execute('select * from switch_topologies')}
        source, copied = rows['Task3原图仅改名称'], rows['Task3真实GUI副本']
        untouched = rows['隔离原图-0-0-002']
        graph = lambda row: [json.loads(row[key]) for key in ('nodes', 'connections', 'operating_modes')]
        # 同一 ORM seed 的未编辑姊妹图是原始图内容基线，含字符串数字和缺键。
        assert json.dumps(graph(source), sort_keys=True) == json.dumps(graph(untouched), sort_keys=True)
        expected = deepcopy(graph(source))
        for edge in expected[1]:
            for key in ('calibrated_loss_db', 'calibrated_phase_deg'):
                if key in edge:
                    edge[key] = None
        assert json.dumps(graph(copied), sort_keys=True) == json.dumps(expected, sort_keys=True)
        assert source['updated_at'].startswith('2020-01-01')
        assert source['is_active'] and source['is_default']
        assert not copied['is_active'] and not copied['is_default']
        assert graph(source)[1][0]['calibrated_loss_db'] == 2.5
        assert isinstance(graph(copied)[1][0]['cable_loss_db'], str)
        assert 'port_directions' not in graph(copied)[0][0]['params']
        active = db.execute('select id from switch_topologies where chamber_id=? and is_active=1 '
                            'order by updated_at desc limit 1', (source['chamber_id'],)).fetchone()[0]
        assert active == manifest['labs'][0]['topologies'][1].replace('-', '')
        categories = db.execute('select driver_mode from instrument_categories').fetchall()
        assert categories and all(row[0] == 'mock' for row in categories)
        bindings = [binding for row in db.execute('select instrument_bindings from lab_profiles')
                    for binding in (json.loads(row[0]) if row[0] else [])]
        assert all(binding['driver_mode'] == 'mock' for binding in bindings)
        empty = db.execute('select chamber_config_id from lab_profiles where name=?', ('Task3空库Lab',)).fetchone()[0]
        imported = db.execute('select is_active,is_default from switch_topologies where chamber_id=?', (empty,)).fetchall()
        assert len(imported) == 1 and all(not row[0] and not row[1] for row in imported)
        assert db.execute('select count(*) from switch_topologies where chamber_id=? and is_active=1', (empty,)).fetchone()[0] == 0
        return dict(database=database, source_id=source['id'], copy_id=copied['id'],
                    source_raw_graph_unchanged=True, copy_raw_exception_only=True,
                    source_updated_at=source['updated_at'], execution_selected_id=active,
                    mock_categories=len(categories), mock_bindings=len(bindings),
                    empty_template_inactive=True, boundary='仅软件Mock证据，不证明现场或正式资格')


if __name__ == '__main__':
    print(json.dumps(audit(sys.argv[1]), ensure_ascii=False, indent=2))
