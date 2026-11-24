"""OTA独立准备；模拟证据不授予真实暗室执行资格。"""
import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session
from app.api.road_test import _get_custom_scenario
from app.data.scenario_library import get_scenario_by_id
from app.db.database import get_db
from app.models.lab_profile import LabProfile
from app.models.chamber import ChamberConfiguration
from app.models.probe import Probe
from app.schemas.road_test import TestExecution, TestMode
from app.services.instrument_hal_service import get_hal_service, is_mock_driver
from app.services.road_test.vrt_execution_service import vrt_execution_service

router = APIRouter(prefix='/road-test/ota', tags=['Virtual Road Test'])


class Selection(BaseModel):
    model_config = ConfigDict(extra='forbid')
    scenario_id: str = Field(min_length=1)
    lab_profile_id: UUID | None = None
    chamber_id: UUID | None = None
    asset_id: UUID | None = None
    direction: str = 'downlink'


def registrations(lab):
    metadata = lab.extra_metadata if isinstance(lab.extra_metadata,dict) else {}
    entries = metadata.get('vrt_ota', [])
    return [x for x in entries if isinstance(x, dict)] if isinstance(entries, list) else []


@router.get('/options')
def options(db: Session = Depends(get_db)):
    labs = db.query(LabProfile).filter(LabProfile.is_active.is_(True)).all()
    assets = {}
    for lab in labs:
        for r in registrations(lab):
            try:
                key = str(UUID(r['asset_id']))
            except (KeyError, ValueError, TypeError):
                continue
            assets[key] = dict(id=key, name=r.get('name') or 'OTA工程', mock_only=True)
    return dict(labs=[dict(id=str(x.id), name=x.name) for x in labs],
                chambers=[dict(id=str(x.id), name=x.name) for x in db.query(ChamberConfiguration).all()],
                assets=list(assets.values()))


def manifest_asset(registration, playback_files):
    directory = Path(registration['manifest_dir'])
    if not directory.is_absolute():
        raise ValueError('OTA工程目录必须是服务端绝对路径。')
    raw = (directory/'manifest.json').read_bytes()
    doc = json.loads(raw)
    if doc.get('mode') != 'ota' or doc.get('direction') != 'downlink':
        raise ValueError('资产必须是下行 OTA 工程，传导工程不能代用。')
    links = doc['links']
    if not isinstance(links, list) or not links:
        raise ValueError('OTA资产缺少波形文件。')
    seen = set()
    for row in links:
        name = row['file']
        if not isinstance(name, str) or Path(name).name != name or not name.lower().endswith('.asc') or name in seen:
            raise ValueError('OTA波形文件名无效或重复。')
        seen.add(name)
        if (directory/name).is_symlink():
            raise ValueError('OTA波形不能通过符号链接引用外部文件。')
        if hashlib.sha256((directory/name).read_bytes()).hexdigest() != row['sha256']:
            raise ValueError('OTA波形内容与文件摘要不一致。')
    digest = hashlib.sha256(raw).hexdigest()
    if digest != registration['sha256']:
        raise ValueError('OTA清单内容与登记摘要不一致。')
    if playback_files is not None:
        playback_files['directory'] = str(directory)
    return dict(id=registration['asset_id'], name=registration['name'], sha256=digest, links=links,
                mock_only=True, kind='ota_manifest', mock_ref='mock-ota:'+digest)


def resolve(db, selection, *, playback_files=None):
    ids = selection.model_dump(mode='json')
    scenario = get_scenario_by_id(selection.scenario_id) or _get_custom_scenario(db, selection.scenario_id)
    if not scenario:
        raise HTTPException(404, '所选场景不存在。')
    snapshot = scenario.model_dump(mode='json', exclude={'created_at','updated_at'})
    digest = hashlib.sha256(json.dumps(snapshot, sort_keys=True, separators=(',',':'), ensure_ascii=False).encode()).hexdigest()
    reasons = []
    lab = db.get(LabProfile, selection.lab_profile_id) if selection.lab_profile_id else None
    chamber = db.get(ChamberConfiguration, selection.chamber_id) if selection.chamber_id else None
    if not lab or not lab.is_active:
        reasons.append('请选择已启用的实验室。')
    if not chamber:
        reasons.append('请选择本次 OTA 使用的暗室。')
    elif lab and lab.chamber_config_id != chamber.id:
        reasons.append('所选暗室与实验室实际绑定不一致。')
    if selection.direction != 'downlink':
        reasons.append('当前仅支持下行 OTA 模拟执行；其他方向需要独立资产与验证。')
    matches = [r for r in registrations(lab) if all(r.get(k)==ids[k] for k in ('scenario_id','chamber_id','asset_id','direction'))] if lab and lab.is_active else []
    asset, mapping, calibration = None, [], None
    chamber_snapshot = None
    if chamber:
        chamber_snapshot = dict(id=str(chamber.id), name=chamber.name, quiet_zone_diameter_m=chamber.quiet_zone_diameter_m,
                                freq_min_mhz=chamber.freq_min_mhz, freq_max_mhz=chamber.freq_max_mhz)
    if len(matches) != 1:
        reasons.append('实验室缺少唯一匹配场景、暗室、方向和 OTA 资产的登记。')
    else:
        reg = matches[0]
        if reg.get('scenario_version') != scenario.version or reg.get('scenario_sha256') != digest:
            reasons.append('场景版本或内容已变化，请重新核对 OTA 登记。')
        if reg.get('kind') != 'ota_manifest':
            reasons.append('真实 OTA 执行仍待暗室场、功率和安全停机现场验收。')
        else:
            try:
                asset = manifest_asset(reg, playback_files)
            except (KeyError, ValueError, TypeError, OSError) as exc:
                reasons.append(f'OTA资产校验失败：{exc}')
        rows = reg.get('probe_mapping')
        probes = db.query(Probe).filter(Probe.chamber_config_id==selection.chamber_id, Probe.is_active.is_(True)).all() if chamber else []
        expected = {str(p.id):p for p in probes}
        try:
            if not isinstance(rows,list) or not rows or len(rows)!=len(expected) or len({r['probe_id'] for r in rows})!=len(rows):
                raise ValueError('需完整映射本暗室全部已启用探头，不能重复或遗漏。')
            ports = set()
            for row in rows:
                if not isinstance(row,dict):
                    raise ValueError('探头映射行格式无效。')
                p = expected.get(row['probe_id'])
                if not p:
                    raise ValueError('映射中的探头不属于本次暗室或未启用。')
                position = row['position']
                if set(position)!={'azimuth','elevation','radius'} or any(type(v) not in (float,int) or not math.isfinite(v) for v in position.values()) or not (0<=position['azimuth']<360 and -90<=position['elevation']<=90 and position['radius']>0) or position!=p.position:
                    raise ValueError('探头位置缺失、无效或与暗室登记不符。')
                if row['polarization'] not in ('H','V') or row['polarization']!=p.polarization:
                    raise ValueError('探头极化与暗室登记不一致。')
                port=row['output_port']
                if type(port) is not int or port<1 or port!=p.channel_port or port in ports or not chamber.ce_num_ota_ports or port>chamber.ce_num_ota_ports:
                    raise ValueError('探头输出端口映射不一致或端口冲突。')
                ports.add(port)
            mapping=rows
        except (KeyError,TypeError,ValueError) as exc:
            reasons.append(f'OTA探头映射校验失败：{exc}')
        calibration=reg.get('calibration') if isinstance(reg.get('calibration'),dict) else None
        try:
            c=calibration
            expiry=datetime.fromisoformat(c['valid_until'])
            frequency=(scenario.step_configuration.network_config.frequency_mhz if scenario.step_configuration and scenario.step_configuration.network_config else None)
            # 频段名称只确定频率范围，不能证明本次中心频率。
            if type(frequency) not in (int, float) or not math.isfinite(frequency) or frequency <= 0:
                raise ValueError('场景缺少可核对的中心频率，校准适用性尚未确认。')
            numeric=[c[k] for k in ('frequency_min_mhz','frequency_max_mhz','bandwidth_mhz','quiet_zone_diameter_m')]
            if any(type(v) not in (int,float) or not math.isfinite(v) or v<=0 for v in numeric):
                raise ValueError('校准范围数值无效。')
            if not chamber or not (c['frequency_min_mhz']<=frequency<=c['frequency_max_mhz'] and chamber.freq_min_mhz<=frequency<=chamber.freq_max_mhz) or c['bandwidth_mhz']<scenario.network.bandwidth_mhz or c['quiet_zone_diameter_m']<chamber.quiet_zone_diameter_m or expiry.tzinfo is None or expiry<=datetime.now(timezone.utc):
                raise ValueError('校准已过期或未覆盖频率、带宽及暗室测试区域。')
            if c.get('mock_only') is not True:
                raise ValueError('真实 OTA 校准需要现场独立验收，不能使用传导校准代替。')
        except (KeyError,TypeError,ValueError,AttributeError) as exc:
            reasons.append(f'OTA校准不适用：{exc}')
    if not all(is_mock_driver(get_hal_service().drivers.get(k)) for k in ('baseStation','channelEmulator')):
        reasons.append('当前 OTA 工程和校准仅限模拟，基站和信道仿真器必须同时使用模拟驱动。')
    return dict(**ids,scenario_version=scenario.version,scenario_sha256=digest,scenario_snapshot=snapshot,
                lab_name=lab.name if lab else None,chamber=chamber_snapshot,asset=asset,
                binding=dict(execution_mode='simulated',mock_only=True),probe_mapping=mapping,calibration=calibration,
                ready=not reasons,reasons=reasons)


class Preparation(Selection):
    scenario_version: str
    scenario_sha256: str
    scenario_snapshot: dict
    lab_name: str | None
    chamber: dict | None
    asset: dict | None
    binding: dict
    probe_mapping: list[dict]
    calibration: dict | None
    ready: bool
    reasons: list[str]


@router.post('/prepare',response_model=Preparation)
def prepare(selection: Selection, db: Session=Depends(get_db)):
    return resolve(db,selection)


@router.post('/executions',response_model=TestExecution,status_code=201)
def create(selection: Selection,db: Session=Depends(get_db)):
    row=vrt_execution_service.create(db,mode=TestMode.OTA,scenario_id=selection.scenario_id,ota_setup=resolve(db,selection))
    return vrt_execution_service.to_test_execution(row)
