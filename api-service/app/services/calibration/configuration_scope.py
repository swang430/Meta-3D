"""PC-01A：白名单配置盘点，无 HAL I/O、无持久化、无资格判定。"""
import hashlib
import json
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.chamber import ChamberConfiguration
from app.models.instrument import InstrumentCategory, InstrumentConnection
from app.models.lab_profile import LabProfile
from app.models.probe import Probe
from app.models.switch_topology import SwitchTopology
from app.schemas.calibration_scope import (
    CalibrationScopePayload, CalibrationScopeSnapshot, CalibrationScopeComparison,
)
from app.services.calibration.rf_chain_resolver import resolve_rf_chains


def _json_numbers(value):
    """JSON number 无整数/浮点类型差异；兼容浏览器 4.0 → 4 的往返。"""
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, dict):
        return {key: _json_numbers(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_numbers(item) for item in value]
    return value


def _canonical(value):
    return json.dumps(_json_numbers(value), sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)


def _ordered(values):
    return sorted(values, key=_canonical)


def scope_digest(payload: CalibrationScopePayload) -> str:
    return hashlib.sha256(_canonical(payload.model_dump(mode='json')).encode()).hexdigest()


def _fields(value, names):
    return {name: getattr(value, name) for name in names}


def build_calibration_scope(db: Session, lab_id: UUID, mode: str = 'mimo_ota') -> CalibrationScopeSnapshot:
    resolution = resolve_rf_chains(db, lab_id, mode)
    lab = db.query(LabProfile).filter(LabProfile.id == lab_id).one()
    chamber = db.query(ChamberConfiguration).filter(ChamberConfiguration.id == resolution.chamber_id).one_or_none()
    if chamber is None:
        raise ValueError('LabProfile 绑定暗室不存在')
    warnings = list(resolution.warnings)
    if not lab.is_active:
        warnings.append('LabProfile 已停用')
    # 只取保存声明；不将 UUID/端点伪装成实物序列号，不暴露凭据/自由参数。
    resources = []
    for binding in lab.instrument_bindings or []:
        if not isinstance(binding, dict):
            warnings.append('仪器绑定含畸形条目')
            continue
        raw_id = binding.get('category_id')
        try:
            category_id = UUID(str(raw_id))
        except (ValueError, TypeError):
            warnings.append('仪器绑定缺少合法 category_id')
            continue
        category = db.query(InstrumentCategory).filter(InstrumentCategory.id == category_id).one_or_none()
        connection = db.query(InstrumentConnection).filter(InstrumentConnection.category_id == category_id).one_or_none()
        row = {key: binding.get(key) for key in (
            'category_id', 'instrument_model_id', 'connection_endpoint', 'driver_mode', 'role')}
        row['saved'] = None if category is None else {
            'category_key': category.category_key, 'is_active': category.is_active,
            'selected_model_id': str(category.selected_model_id) if category.selected_model_id else None,
            'driver_mode': category.driver_mode,
            'endpoint': connection.endpoint if connection else None,
            'protocol': connection.protocol if connection else None,
            'connection_id': str(connection.id) if connection else None,
            'controller_ip': connection.controller_ip if connection else None,
            'port': connection.port if connection else None,
            'profiles': {k: (connection.connection_params or {}).get(k) for k in (
                'base_station_adapter_profile', 'channel_emulator_adapter_profile', 'topology_profile_id',
                'ip', 'controller_ip', 'ip_address', 'visa_resource', 'endpoint', 'port', 'protocol',
                'motion_truth_units_verified', 'motion_truth_user_units', 'motion_truth_coordinate_offset_deg',
                'motion_truth_coordinate_offset_verified', 'motion_truth_coordinate_offset_verification_source',
                'motion_truth_coordinate_offset_verified_at', 'motion_truth_min_deg', 'motion_truth_max_deg',
                'motion_truth_xf_speed', 'position_tolerance_deg', 'azimuth_axis')}
                if connection and isinstance(connection.connection_params, dict) else {},
        }
        resources.append(row)
        if category is None or not category.is_active:
            warnings.append(f'绑定资源未启用或已不存在：{raw_id}')
        elif (not connection or str(category.selected_model_id) != str(binding.get('instrument_model_id'))
              or connection.endpoint != binding.get('connection_endpoint')
              or category.driver_mode != binding.get('driver_mode')):
            warnings.append(f'保存资源与 LabProfile 绑定不一致：{category.category_key}')
    if not resources:
        warnings.append('尚无 LabProfile 仪器绑定')
    topology = db.query(SwitchTopology).filter(
        SwitchTopology.id == UUID(str(resolution.topology_id))).one_or_none() if resolution.topology_id else None
    graph = {'id': str(topology.id) if topology else None}
    if topology:
        selected_mode = next((m for m in topology.operating_modes or [] if m.get('id') == mode), {})
        active = set(selected_mode.get('active_connections') or [])
        connections = [c for c in topology.connections or [] if c.get('id') in active]
        node_ids = {c.get(k) for c in connections for k in ('source', 'target')}
        graph['connections'] = _ordered([{k: c.get(k) for k in (
            'id', 'source', 'source_pin', 'target', 'target_pin', 'cable_type', 'cable_length_m',
            'cable_loss_db', 'pa_gain_db', 'switch_port', 'direction', 'calibrated_phase_deg',
            'calibrated_loss_db', 'ce_port')}
                                         for c in connections])
        # label 是 CE 端口解析输入，而非纯显示名称；因此保留。
        graph['nodes'] = _ordered([{
            **{k: n.get(k) for k in ('id', 'type', 'label')},
            'parameters_digest': hashlib.sha256(_canonical(n.get('params') or {}).encode()).hexdigest(),
        } for n in topology.nodes or [] if n.get('id') in node_ids])
        graph['active_connections'] = sorted(active)
        graph['required_instruments'] = sorted(selected_mode.get('required_instruments') or [])
    probes = db.query(Probe).filter(Probe.chamber_config_id == chamber.id, Probe.is_active.is_(True)).all()
    chains = sorted([{
        'chain_id': c.chain_id, 'ce_port': c.ce_port, 'probe_id': c.probe_id,
        'polarization': c.polarization, 'cable_loss_db': c.cable_loss_db,
    } for c in resolution.chains], key=lambda c: c['chain_id'])
    if len({c['chain_id'] for c in chains}) != len(chains):
        warnings.append('解析链身份重复')
    if len({(c['probe_id'], c['polarization']) for c in chains}) != len(chains):
        warnings.append('探头/极化映射重复')
    payload = CalibrationScopePayload(
        lab_profile_id=lab.id, chamber_id=chamber.id, operating_mode=mode, lab_active=lab.is_active,
        chamber=_fields(chamber, (
            'chamber_radius_m', 'quiet_zone_diameter_m', 'num_probes', 'num_polarizations', 'num_rings',
            'probe_distribution', 'has_pa', 'pa_gain_db', 'has_lna', 'lna_gain_db', 'has_duplexer',
            'duplexer_insertion_loss_db', 'ce_num_ota_ports', 'probe_gain_dbi', 'typical_cable_loss_db',
            'cable_sgh_to_sa_loss_db', 'freq_min_mhz', 'freq_max_mhz', 'has_turntable', 'turntable_max_load_kg',
            'has_channel_emulator', 'ce_bidirectional', 'ce_min_input_dbm', 'pa_p1db_dbm',
            'lna_noise_figure_db', 'duplexer_isolation_db')),
        resources=_ordered(resources), topology=graph,
        probes=_ordered([_fields(p, ('probe_number', 'ring', 'polarization', 'position', 'hardware_id', 'channel_port',
                                    'frequency_range_mhz', 'max_power_dbm', 'gain_db'))
                         for p in probes]), chains=chains,
    )
    digest = scope_digest(payload)  # allow_nan=False，畸形数值不形成有效范围
    return CalibrationScopeSnapshot(payload=payload, digest=digest,
                                    configuration_complete=bool(chains) and not warnings, warnings=warnings)


def compare_calibration_scope(current: CalibrationScopeSnapshot, baseline: CalibrationScopeSnapshot):
    if scope_digest(baseline.payload) != baseline.digest:
        raise ValueError('保留快照摘要不匹配，请重新保留快照')
    before, after = baseline.payload.model_dump(mode='json'), current.payload.model_dump(mode='json')
    changed = sorted(k for k in after if before[k] != after[k])
    old = {c.chain_id: c.model_dump() for c in baseline.payload.chains}
    new = {c.chain_id: c.model_dump() for c in current.payload.chains}
    affected = sorted(set(old) | set(new)) if set(changed) - {'chains'} else sorted(
        key for key in set(old) | set(new) if old.get(key) != new.get(key))
    return CalibrationScopeComparison(current=current, changed_sections=changed, affected_chain_ids=affected,
                                      requires_review=bool(changed))
