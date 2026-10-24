"""执行创建时冻结逐链来源；读取历史不访问当前图、证书或选择指针。零仪器I/O。"""
import copy
import math
from datetime import datetime,timezone
from types import SimpleNamespace
from uuid import UUID

from app.hal.base_station_compatibility import canonical_payload_digest
from app.models.lab_profile import LabProfile
from app.models.probe_calibration import ProbePathLossCalibration,CalibrationStatus
from app.models.route_calibration import RouteCalibrationApplication,RouteCalibrationSelection
from app.schemas.route_calibration import RouteApplicationRecord
from app.services.calibration.rf_chain_resolver import resolve_rf_chains
from app.services.calibration.route_calibration import list_route_selections
from app.services.path_loss_calibration_service import ProbePathLossCalibrationService

FREEZE_KEY='route_calibration_freeze'
_PLANES={'confirmed_route':'ce_output_to_reference_antenna_output','legacy_certificate':'legacy_total_insertion_loss'}


def _plain(value):
    if isinstance(value,(UUID,datetime)):
        return value.isoformat() if isinstance(value,datetime) else str(value)
    if isinstance(value,dict):
        return {str(key):_plain(item) for key,item in value.items()}
    if isinstance(value,(list,tuple)):
        return [_plain(item) for item in value]
    return value


def _finite(value):
    return type(value) in (int,float) and math.isfinite(value)


def _execution_route(route):
    # 新显式路径还须冻结开关物理执行身份，不能只因CE/probe端点相同而套用旧量值。
    # 旧无声明路径仍仅比较节点/端口；备注、显示坐标和校准参考段均不驱动执行。
    from app.services.declared_rf_routes import rf_execution_identity
    return rf_execution_identity(route.nodes,route.connections,route.switch_execution_identity)


def resolve_effective_route_compensation(db,lab_id,mode,frequency_mhz):
    """新确认仅精确频点/完整路径适用；旧来源仍沿既有频率/mode政策逐链核对。"""
    lab=db.get(LabProfile,UUID(str(lab_id)))
    if lab is None or not lab.is_active:
        raise ValueError('执行路损冻结需要明确活动实验室')
    if lab.chamber_config_id is None:
        # A session can be prepared before chamber configuration. Freeze that
        # absence now; never fill it from a later current configuration.
        return dict(version=1,lab_profile_id=str(lab.id),chamber_id=None,topology_id=None,
            operating_mode=mode,frequency_mhz=frequency_mhz,route_entries=[],source_records=[],
            selected_at=datetime.now(timezone.utc).isoformat(),
            warnings=['未绑定暗室，执行校准来源不可用；创建会话不表示可以正式执行硬件'],
            legacy_selection_reason='missing_configuration',legacy_selected_certificate_id=None)
    resolution=resolve_rf_chains(db,lab.id,mode)
    routes={}
    warnings=list(resolution.warnings)
    if resolution.topology_id is not None:
        try:
            routes={route.chain_id:route for route in list_route_selections(
                db,lab.id,UUID(resolution.topology_id),mode)}
        except ValueError as exc:
            # 旧图可能不足以声明新方法完整路径；不能据旧图给新确认补真。
            warnings.append(str(exc))
    legacy=ProbePathLossCalibrationService(db,use_mock=False).resolve_latest_calibration(
        lab.chamber_config_id,frequency_mhz,operating_mode=mode,require_real=True)
    certificate=legacy.certificate
    # 沿旧VALID/有效期/±5%政策，精确mode优先、再未标记mode；逐链寻找实际覆盖，不能整份latest遮住别链。
    old_query=db.query(ProbePathLossCalibration).filter(
        ProbePathLossCalibration.chamber_id==lab.chamber_config_id,
        ProbePathLossCalibration.status==CalibrationStatus.VALID.value,
        ProbePathLossCalibration.valid_until>datetime.utcnow(),ProbePathLossCalibration.use_mock.is_(False),
        ProbePathLossCalibration.frequency_mhz.between(frequency_mhz*.95,frequency_mhz*1.05))
    old_candidates=(old_query.filter(ProbePathLossCalibration.operating_mode==mode)
        .order_by(ProbePathLossCalibration.calibrated_at.desc()).all()+
        old_query.filter(ProbePathLossCalibration.operating_mode.is_(None))
        .order_by(ProbePathLossCalibration.calibrated_at.desc()).all())
    diagnostic=legacy
    if certificate is None:
        diagnostic=ProbePathLossCalibrationService(db,use_mock=False).resolve_latest_calibration(
            lab.chamber_config_id,frequency_mhz,operating_mode=mode)
    source_records={}
    if diagnostic.certificate is not None:
        saved=diagnostic.certificate
        source_records[('legacy_certificate',str(saved.id))]=dict(source_kind='legacy_certificate',source_id=str(saved.id),
            snapshot={column.name:_plain(getattr(saved,column.name)) for column in saved.__table__.columns})
    route_entries=[]
    now=datetime.now(timezone.utc)
    # 完整路径的CE端点是身份权威；旧终端绑定可能把中间衰减器标签当端口，甚至丢链。
    chains={chain.chain_id:chain for chain in resolution.chains}
    chains.update(routes)
    for chain in chains.values():
        route=routes.get(chain.chain_id)
        entry=dict(chain_id=chain.chain_id,ce_port=chain.ce_port,probe_id=chain.probe_id,
            polarization=chain.polarization,route_digest=route.route_digest if route else None,
            execution_route_identity=_execution_route(route) if route else None,
            source_kind='unavailable',source_id=None,method=None,reference_plane=None,
            value_db=None,measurement_provenance='unknown',certification_status='unknown',reason='missing_coverage')
        candidates=[]
        if route is not None:
            pointers=db.query(RouteCalibrationSelection).filter_by(lab_profile_id=lab.id,
                topology_id=route.topology_id,operating_mode=mode,chain_id=chain.chain_id,
                frequency_mhz=frequency_mhz).all()
            for pointer in pointers:
                saved=db.get(RouteCalibrationApplication,pointer.application_id)
                if saved is None or saved.lab_profile_id!=lab.id:
                    continue
                record=RouteApplicationRecord.model_validate(saved.record)
                coverage=record.coverage_snapshot
                if (record.selection_snapshot.route_digest!=route.route_digest or
                    record.frequency_mhz!=frequency_mhz or coverage.get('frequency_mhz')!=frequency_mhz or
                    coverage.get('polarization')!=chain.polarization or
                    coverage.get('reference_identity_digest')!=pointer.reference_identity_digest or
                    record.adoption_evidence_snapshot.get('measurement_provenance')!='real'):
                    continue
                until=datetime.fromisoformat(coverage['adoption_valid_until'].replace('Z','+00:00'))
                if until.tzinfo is not None and until>now:
                    candidates.append(record)
        if len(candidates)==1:
            record=candidates[0]
            entry.update(source_kind='confirmed_route',source_id=str(record.id),method=record.method,
                reference_plane=_PLANES['confirmed_route'],value_db=record.net_loss_db,
                measurement_provenance='real',reason='selected')
            source_records[('confirmed_route',str(record.id))]=dict(source_kind='confirmed_route',
                source_id=str(record.id),snapshot=record.model_dump(mode='json'))
        elif len(candidates)>1:
            warnings.append(f'{chain.chain_id}: 多个参考身份仍在选用期，不猜测采用哪一个')
        for certificate in old_candidates if entry['source_kind']=='unavailable' else []:
            data=(certificate.path_loss_db_by_rf_chain or {}).get(chain.chain_id)
            if (isinstance(data,dict) and data.get('probe_id')==chain.probe_id and
                data.get('polarization')==chain.polarization and data.get('ce_port')==chain.ce_port and
                _finite(data.get('total_insertion_loss_db')) and
                certificate.lab_profile_id in (None,lab.id) and
                (certificate.topology_id is None or str(certificate.topology_id)==resolution.topology_id)):
                entry.update(source_kind='legacy_certificate',source_id=str(certificate.id),
                    method='legacy_probe_path_loss',reference_plane=_PLANES['legacy_certificate'],
                    value_db=data['total_insertion_loss_db'],measurement_provenance='real',reason='selected')
                snapshot={column.name:_plain(getattr(certificate,column.name)) for column in certificate.__table__.columns}
                source_records[('legacy_certificate',str(certificate.id))]=dict(source_kind='legacy_certificate',
                    source_id=str(certificate.id),snapshot=snapshot)
                break
        route_entries.append(entry)
    return dict(version=1,lab_profile_id=str(lab.id),chamber_id=str(lab.chamber_config_id),
        topology_id=resolution.topology_id,operating_mode=mode,frequency_mhz=frequency_mhz,
        route_entries=route_entries,source_records=list(source_records.values()),selected_at=now.isoformat(),
        warnings=warnings,legacy_selection_reason=diagnostic.reason,
        legacy_selected_certificate_id=str(diagnostic.certificate.id) if diagnostic.certificate is not None else None)


def _validate(frozen,execution_id):
    if not isinstance(frozen,dict) or frozen.get('version')!=1 or frozen.get('execution_id')!=str(execution_id):
        raise ValueError('路损冻结身份或版本非法')
    body={key:value for key,value in frozen.items() if key!='digest'}
    if frozen.get('digest')!=canonical_payload_digest(body):
        raise ValueError('路损冻结摘要不匹配')
    entries=frozen.get('route_entries')
    sources=frozen.get('source_records')
    if not isinstance(entries,list) or not isinstance(sources,list) or not _finite(frozen.get('frequency_mhz')):
        raise ValueError('路损冻结缺少逐链来源')
    keys=set()
    source_index={(source['source_kind'],source['source_id']):source['snapshot'] for source in sources}
    for entry in entries:
        identity=(entry['chain_id'],entry['probe_id'],entry['polarization'])
        if identity in keys or not entry['chain_id'] or not entry['ce_port'] or entry['polarization'] not in ('V','H'):
            raise ValueError('路损冻结链身份非法')
        keys.add(identity)
        kind=entry['source_kind']
        if kind=='unavailable':
            if entry['value_db'] is not None or entry['source_id'] is not None:
                raise ValueError('无覆盖链不能携带补偿值')
            continue
        source=source_index.get((kind,entry['source_id']))
        if source is None or entry['reference_plane']!=_PLANES.get(kind) or not _finite(entry['value_db']):
            raise ValueError('路损冻结量值与参考面缺损')
        if kind=='confirmed_route':
            record=RouteApplicationRecord.model_validate(source)
            route=record.selection_snapshot
            if (record.net_loss_db!=entry['value_db'] or route.chain_id!=entry['chain_id'] or
                any(getattr(route,key)!=entry[key] for key in ('probe_id','polarization','ce_port')) or
                _execution_route(route)!=entry['execution_route_identity'] or
                record.selection_snapshot.route_digest!=entry['route_digest'] or record.frequency_mhz!=frozen['frequency_mhz'] or
                record.adoption_evidence_snapshot.get('measurement_provenance')!='real'):
                raise ValueError('确认来源与冻结链不一致')
        elif kind=='legacy_certificate':
            data=(source.get('path_loss_db_by_rf_chain') or {}).get(entry['chain_id'],{})
            if (source.get('use_mock') is not False or data.get('total_insertion_loss_db')!=entry['value_db'] or
                any(data.get(key)!=entry[key] for key in ('probe_id','polarization','ce_port'))):
                raise ValueError('旧证书来源与冻结链不一致')
        else:
            raise ValueError('未知路损来源')
    return copy.deepcopy(frozen)


def frozen_route_identity_error(db,frozen,*,resolved_topology=None):
    """只比较实际执行接线身份，不刷新冻结来源，也不要求重新校准。"""
    if frozen.get('version')!=1 or frozen.get('topology_id') is None:
        return None
    expected={(row['chain_id'],row['ce_port'],row['probe_id'],row['polarization']) for row in frozen['route_entries']}
    if resolved_topology is not None:
        # 最终消费者提供的对象是权威，不再用另一遍DB查询替它作判定。
        actual={(row.connection_id,row.ce_port,row.probe_id,row.polarization) for row in resolved_topology.probe_bindings}
        if (resolved_topology.topology_id!=frozen['topology_id'] or resolved_topology.mode_id!=frozen['operating_mode'] or
            actual!=expected or len(resolved_topology.probe_bindings)!=len(expected)):
            return 'path-loss actual route target differs from execution freeze; create a new execution to review the saved route'
        by_chain={row.connection_id:row for row in resolved_topology.probe_bindings}
        for row in frozen['route_entries']:
            identity=row.get('execution_route_identity')
            if isinstance(identity,dict) and identity.get('switch_mappings'):
                if by_chain[row['chain_id']].execution_route_identity!=identity:
                    return 'path-loss actual switch route differs from execution freeze; create a new execution to review the saved route'
        return None
    try:
        current=resolve_rf_chains(db,UUID(frozen['lab_profile_id']),frozen['operating_mode'])
        routes={}
        if any(row['execution_route_identity'] is not None for row in frozen['route_entries']):
            routes={route.chain_id:route for route in list_route_selections(db,UUID(frozen['lab_profile_id']),
                UUID(frozen['topology_id']),frozen['operating_mode'])}
        chains={row.chain_id:row for row in current.chains}
        chains.update(routes)
        actual={(row.chain_id,row.ce_port,row.probe_id,row.polarization) for row in chains.values()}
        if current.topology_id!=frozen['topology_id'] or actual!=expected:
            return 'path-loss route identity changed; create a new execution to review the saved route'
        if any(row['execution_route_identity'] is not None for row in frozen['route_entries']):
            if any(row['execution_route_identity'] is not None and (row['chain_id'] not in routes or
                _execution_route(routes[row['chain_id']])!=row['execution_route_identity']) for row in frozen['route_entries']):
                return 'path-loss route identity changed; create a new execution to review the saved route'
    except (LookupError,ValueError):
        return 'path-loss frozen route is no longer available; create a new execution to review the saved route'
    return None


def frozen_route_output_ports(frozen,num_probes,num_polarizations):
    """现有ASC不重排输出；只允许冻结CE实际口与默认ASC端口一致。零仪器I/O。"""
    from app.services.probe_pattern.consumer import infer_rf_chain_probe_id_base
    from app.hal.propsim_f64 import RealPropsimF64Driver
    rows=frozen['route_entries']
    base=infer_rf_chain_probe_id_base(num_probes,[row['probe_id'] for row in rows])
    if base is None:
        raise ValueError('冻结探头编号不能明确映射到物理端口，禁止猜测0/1基编号')
    ports=[]
    for row in rows:
        port=(row['probe_id']-base)*num_polarizations+(1 if row['polarization']=='V' else 2)
        if row['polarization']=='H' and num_polarizations<2 or not 1<=port<=num_probes*num_polarizations:
            raise ValueError('冻结探头编号/极化不属于当前物理端口范围')
        try:
            output=int(RealPropsimF64Driver._ce_port_to_output_num(row['ce_port']))
        except (ValueError,TypeError) as exc:
            raise ValueError('冻结CE输出口无法核对ASC端口映射') from exc
        if output!=port:
            raise ValueError('冻结CE输出口与ASC默认端口映射不一致；尚不支持非默认输出接线补偿')
        ports.append(port)
    return ports


def read_execution_route_compensation(execution):
    config=execution.config if isinstance(execution.config,dict) else {}
    if FREEZE_KEY not in config:
        return dict(version=0,status='legacy_unknown',route_entries=[],source_records=[])
    try:
        return _validate(config[FREEZE_KEY],execution.id)
    except (KeyError,TypeError,AttributeError) as exc:
        raise ValueError('路损冻结结构缺损') from exc


def freeze_execution_route_compensation(db,execution,test_case):
    """只在三个创建入口调用；已有冻结只验证，不重新解析任何当前来源。"""
    config=execution.config if isinstance(execution.config,dict) else {}
    if FREEZE_KEY in config:
        return read_execution_route_compensation(execution)
    from app.services.mimo_ota.executors._helpers import load_mimo_ota_config
    configuration=load_mimo_ota_config(execution)
    frozen=resolve_effective_route_compensation(db,test_case.lab_profile_id,configuration.switch_mode_id,
        configuration.primary_carrier.frequency_hz/1e6)
    frozen['execution_id']=str(execution.id)
    frozen['digest']=canonical_payload_digest(frozen)
    _validate(frozen,execution.id)
    execution.config={**config,FREEZE_KEY:frozen}
    db.flush()
    return copy.deepcopy(frozen)


def frozen_legacy_certificate(frozen):
    """仅全链同一旧证书时提供旧消费者只读适配；不把新确认伪装成旧证书。"""
    entries=frozen.get('route_entries',[])
    if not entries or any(entry['source_kind']!='legacy_certificate' for entry in entries):
        return None
    ids={entry['source_id'] for entry in entries}
    if len(ids)!=1:
        return None
    source=next(source['snapshot'] for source in frozen['source_records']
        if source['source_kind']=='legacy_certificate' and source['source_id'] in ids)
    return _legacy_object(source)


def frozen_selected_legacy_certificate(frozen):
    ident=frozen.get('legacy_selected_certificate_id')
    if ident is None:
        return None
    source=next(source['snapshot'] for source in frozen['source_records']
        if source['source_kind']=='legacy_certificate' and source['source_id']==ident)
    return _legacy_object(source)


def _legacy_object(source):
    data=copy.deepcopy(source)
    for key in ('calibrated_at','valid_until','created_at','updated_at','sgh_certificate_date'):
        if data.get(key) is not None:
            data[key]=datetime.fromisoformat(data[key]).replace(tzinfo=None)
    return SimpleNamespace(**data)
