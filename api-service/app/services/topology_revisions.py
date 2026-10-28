"""同事务原始快照与逐行CAS；提交责任保留在API边界。"""
from copy import deepcopy
from datetime import date, datetime
import json
import sqlite3
import inspect
from functools import wraps
from sqlalchemy.exc import OperationalError
from sqlalchemy import select, update
from fastapi import HTTPException
from pydantic import ValidationError
from app.models.chamber import ChamberConfiguration
from app.models.switch_topology import SwitchTopology
from app.models.switch_topology_revision import SwitchTopologyRevision

RESTORABLE = ('name', 'description', 'version', 'site_name', 'system_model', 'installed_date',
              'installed_by', 'nodes', 'connections', 'operating_modes')
RECORDED = ('id', 'chamber_id', 'switch_category_id', 'created_at', 'updated_at', 'created_by', 'is_active', 'is_default')


def topology_write(function):
    """覆盖锁、候选校验和提交的回滚边界；仅SQLite已知锁码归类409。"""
    @wraps(function)
    def wrapped(*args, **kwargs):
        db = inspect.signature(function).bind_partial(*args, **kwargs).arguments['db']
        try:
            return function(*args, **kwargs)
        except Exception as exc:
            db.rollback()
            if isinstance(exc, OperationalError):
                code = getattr(exc.orig, 'sqlite_errorcode', None)
                if isinstance(code, int) and code & 0xff in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED):
                    raise HTTPException(409, detail='拓扑正在被其他会话修改，请刷新核对') from exc
            if isinstance(exc, ValidationError):
                raise HTTPException(422, detail='拓扑无法序列化，请核对已保存图') from exc
            raise
    return wrapped


def json_value(value):
    return value.isoformat() if isinstance(value, (date, datetime)) else deepcopy(value)


def raw_snapshot(row):
    return {key: json_value(getattr(row, key)) for key in RESTORABLE}


def restore_candidate(snapshot):
    """白名单raw恢复；仅清已有内嵌校准键，不补缺键或typed默认。"""
    if not isinstance(snapshot, dict) or set(snapshot) != set(RESTORABLE):
        raise HTTPException(422, detail='历史快照可恢复字段不完整')
    candidate = deepcopy(snapshot)
    for key in ('nodes', 'connections', 'operating_modes'):
        if not isinstance(candidate[key], list) or any(not isinstance(x, dict) for x in candidate[key]):
            raise HTTPException(422, detail='历史图必须为对象列表')
    for edge in candidate['connections']:
        for key in ('calibrated_loss_db', 'calibrated_phase_deg'):
            if key in edge:
                edge[key] = None
    return candidate


def field_differences(before, after):
    result = []
    for key in sorted(set(before) | set(after)):
        if key in before and key in after and same_json(before[key], after[key]):
            continue
        item = {'field': key, 'before_present': key in before, 'after_present': key in after}
        if key in before:
            item['before'] = deepcopy(before[key])
        if key in after:
            item['after'] = deepcopy(after[key])
        result.append(item)
    return result


def recorded_metadata(row):
    return {key: (str(getattr(row, key)) if key in ('id', 'chamber_id', 'switch_category_id')
                  and getattr(row, key) is not None else json_value(getattr(row, key))) for key in RECORDED}


def same_json(left, right):
    options = dict(sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(',', ':'))
    return json.dumps(left, **options) == json.dumps(right, **options)


def lock_chamber(db, chamber_id):
    # 稳定暗室行串行化空peer写；不改变暗室时间，也不表示硬件空闲。
    if db.bind.dialect.name == 'sqlite':
        result = db.execute(update(ChamberConfiguration).where(ChamberConfiguration.id == chamber_id).values(
            id=ChamberConfiguration.id, updated_at=ChamberConfiguration.updated_at)
            .execution_options(synchronize_session=False))
        exists = result.rowcount == 1
    else:
        exists = db.execute(select(ChamberConfiguration.id).where(
            ChamberConfiguration.id == chamber_id).with_for_update()).one_or_none() is not None
    if not exists:
        raise HTTPException(404, detail='暗室不存在')


def add_revision(db, row, operation, restored_from_revision=None):
    db.add(SwitchTopologyRevision(topology_id=row.id, revision=row.revision, operation=operation,
        restored_from_revision=restored_from_revision, snapshot=raw_snapshot(row), recorded_metadata=recorded_metadata(row)))


def assert_revision_deletable(db, topology_ids):
    if topology_ids and db.query(SwitchTopologyRevision.id).filter(
            SwitchTopologyRevision.topology_id.in_(topology_ids)).first() is not None:
        raise HTTPException(409, detail='拓扑已有不可变修订历史，不允许删除')


def cas_revision(db, row, expected_revision, values, *, operation='update', raw_conditions=(),
                 restored_from_revision=None, preserve_updated_at=False, force_revision=False):
    if row.revision != expected_revision:
        raise HTTPException(409, detail='服务器拓扑已变化，请刷新核对；草稿未覆盖')
    changed = any(not same_json(json_value(getattr(row, key)), json_value(value)) for key, value in values.items())
    if not changed and not force_revision:
        return row
    before, before_meta, old_revision = raw_snapshot(row), recorded_metadata(row), row.revision
    writes = dict(values, revision=old_revision + 1)
    if preserve_updated_at:
        writes['updated_at'] = SwitchTopology.updated_at
    result = db.execute(update(SwitchTopology).where(SwitchTopology.id == row.id,
        SwitchTopology.chamber_id == row.chamber_id, SwitchTopology.switch_category_id == row.switch_category_id,
        SwitchTopology.revision == expected_revision, *raw_conditions).values(**writes)
        .execution_options(synchronize_session=False))
    if result.rowcount != 1:
        raise HTTPException(409, detail='服务器拓扑已变化，请刷新核对；草稿未覆盖')
    if old_revision == 0:
        db.add(SwitchTopologyRevision(topology_id=row.id, revision=0, operation='baseline',
            snapshot=before, recorded_metadata=before_meta))
    db.refresh(row)
    add_revision(db, row, operation, restored_from_revision)
    return row


def demote_default_peers(db, target):
    peers = db.query(SwitchTopology).populate_existing().filter(
        SwitchTopology.chamber_id == target.chamber_id,
        SwitchTopology.switch_category_id == target.switch_category_id,
        SwitchTopology.is_default.is_(True), SwitchTopology.id != target.id).all()
    for peer in peers:
        cas_revision(db, peer, peer.revision, {'is_default': False})
    return peers
