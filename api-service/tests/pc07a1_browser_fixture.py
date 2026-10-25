"""PC07A1 隔离浏览器种子：合成历史不是真机认证，与实际 Mock 执行分开。"""
import os
import json
import sqlite3
from pathlib import Path

_url = os.environ.get('DATABASE_URL', '')
_root = Path(os.environ.get('PC07A1_OUTPUT', '/invalid')).resolve()
_db = Path(_url.removeprefix('sqlite:///')).resolve()
if (os.environ.get('USE_MOCK_INSTRUMENTS') != 'true'
        or not _url.startswith('sqlite:////tmp/pc07a1-')
        or _root.parent != Path('/tmp').resolve() or not _root.name.startswith('pc07a1-')
        or _db.parent != _root or (_db.exists() and os.environ.get('PC07A1_ACTION') not in ('forge', 'prepare-mimo'))
        or os.environ.get('BOOTSTRAP_ON_STARTUP') != 'false'):
    raise RuntimeError('仅允许全Mock、显式新建/tmp/pc07a1-* SQLite及独占输出目录')

if __name__ == '__main__' and os.environ.get('PC07A1_ACTION') == 'forge':
    from app.services.mimo_ota.path_loss_application import parse_path_loss_application
    from app.services.mimo_ota.calibration_traceability import build_calibration_traceability
    manifest = json.loads((_root / 'manifest.json').read_text())
    with sqlite3.connect(_db) as connection:
        key = manifest['report_id'].replace('-', '')
        content = json.loads(connection.execute('SELECT content_data FROM test_reports WHERE id=?', (key,)).fetchone()[0])
        (_root / 'before-forgery.json').write_text(json.dumps(content, ensure_ascii=False, indent=2))
        forged = dict(schema_version=1, status='applied', provenance='real', reason='selected',
            gate_mode='strict', certificate_id='forged-cert', value_disclosure='verified')
        content.update(path_loss_application=parse_path_loss_application(forged), formal_path_loss_verified=True,
            calibration_traceability=build_calibration_traceability(forged))
        connection.execute('UPDATE test_reports SET content_data=? WHERE id=?', (json.dumps(content), key))
    raise SystemExit(0)

if __name__ == '__main__' and os.environ.get('PC07A1_ACTION') == 'prepare-mimo':
    # 仅扩充隔离夹具的实际 Mock 设备，不改已有历史执行或生产门。
    from uuid import UUID
    from app.main import app
    from app.db.database import SessionLocal
    from app.models.instrument import InstrumentCategory, InstrumentModel, InstrumentConnection
    from app.models.lab_profile import LabProfile
    manifest = json.loads((_root / 'manifest.json').read_text())
    with SessionLocal() as db:
        assert all(row.driver_mode == 'mock' for row in db.query(InstrumentCategory))
        lab = db.get(LabProfile, UUID(manifest['lab_profile_id']))
        bindings = list(lab.instrument_bindings)
        for key, name in [('baseStation', 'UXM 5G E7515B'), ('positioner', 'EMCenter')]:
            if db.query(InstrumentCategory).filter_by(category_key=key).first():
                raise RuntimeError('专属种子不得覆盖已有同类仪器')
            category = InstrumentCategory(category_key=key, category_name=f'PC07A1 Mock {key}', driver_mode='mock')
            db.add(category); db.flush()
            model = InstrumentModel(category_id=category.id, model=name, vendor='隔离Mock', capabilities={})
            db.add(model); db.flush()
            category.selected_model_id = model.id
            db.add(InstrumentConnection(category_id=category.id, endpoint='192.0.2.10', created_by='PC07A1全Mock夹具'))
            bindings.append(dict(category_id=str(category.id), instrument_model_id=str(model.id),
                connection_endpoint='192.0.2.10', driver_mode='mock', role=key))
        lab.instrument_bindings = bindings
        db.commit()
    raise SystemExit(0)

import pytest
from tests.test_pc07a1_report_traceability import (
    archived, application, db_session, chamber, topology_two_chains, lab_profile,
    client, configured, real_capture, legacy, launch, confirm, payload,
)

@pytest.mark.asyncio
async def test_seed_browser(archived, configured, real_capture, client, db_session):
    execution, report = archived
    report.title = 'PC07A1 合成真实来源历史（非真机认证）'
    report.content_data = {**report.content_data, 'title': report.title}
    original = report.content_data['calibration_traceability']
    # 先冻结历史，再推进当前采用；fixture 的脚本化 transport 不会连接任何仪器。
    newer = real_capture('-20', '-10')
    response = confirm(client, configured, payload(client, configured, newer))
    assert response.status_code == 201
    from app.models.instrument import InstrumentCategory
    db_session.query(InstrumentCategory).update({'driver_mode': 'mock'})
    configured.instrument_bindings = [{**b, 'driver_mode': 'mock'} for b in configured.instrument_bindings]
    from app.models.test_plan import TestCase
    case = db_session.get(TestCase, execution.test_case_id)
    case.configuration = {**case.configuration, 'frequency_hz': 3500e6}
    # 独立旧无键报告沿既有读取门。
    from app.services.report_service import ReportService
    old = ReportService().create_report(db_session, title='PC07A1 旧无键报告', report_type='single_execution',
        format='pdf', generated_by='mimo_ota.executors.report', test_execution_ids=[execution.id])
    old.content_data = {k: v for k, v in report.content_data.items() if k != 'calibration_traceability'}
    old.status = 'completed'
    db_session.commit()
    assert all(c.driver_mode == 'mock' for c in db_session.query(InstrumentCategory))
    _root.mkdir(exist_ok=True)
    source = db_session.get_bind().raw_connection()
    try:
        with sqlite3.connect(_db) as target:
            source.driver_connection.backup(target)
    finally:
        source.close()
    (_root / 'manifest.json').write_text(json.dumps(dict(
        report_id=str(report.id), legacy_report_id=str(old.id), execution_id=str(execution.id),
        lab_profile_id=str(configured.id), original=original, current_source_id=response.json()['id'],
        evidence_boundary='合成历史/脚本化transport；非真机认证，与后续全Mock执行分开'), ensure_ascii=False, indent=2))
