"""原执行校准来源的只读投影；不查当前数据库，不补采原始读数或认证资格。"""
from copy import deepcopy
from collections.abc import Mapping

from app.services.mimo_ota.path_loss_application import parse_path_loss_application


def build_calibration_traceability(application: object) -> dict:
    """按冻结链关联来源；选择、应用与认证为不同事实。

    source_snapshot 仅透传唯一匹配且通过既有冻结校验的历史快照。
    缺损记录只保留链和来源标识用于定位，不从候选证书或当前配置猜值。
    acquisition_run_id/checked_exchange_indices 是指针，不代表已内嵌原始读数。
    """
    try:
        parsed = parse_path_loss_application(application)
    except (ValueError, TypeError, KeyError, AttributeError):
        # 历史损坏可能在旧 parser 的字典索引前失败，同样按未知处理。
        parsed = parse_path_loss_application(None)
    result = {
        'schema_version': 1,
        'status': parsed['status'],
        'provenance': parsed['provenance'],
        'reason': parsed['reason'],
        'gate_mode': parsed['gate_mode'],
        'certificate_id': parsed['certificate_id'],
        'execution_frequency_mhz': None,
        'routes': [],
        'raw_readings_embedded': False,
    }
    valid = parsed.get('schema_version') == 2
    raw = application if isinstance(application, Mapping) else {}
    frozen = parsed['route_compensation'] if valid else raw.get('route_compensation')
    if not isinstance(frozen, Mapping):
        return result
    entries = frozen.get('route_entries')
    if not isinstance(entries, list):
        return result
    sources = frozen.get('source_records')
    sources = sources if isinstance(sources, list) else []
    if valid:
        result['execution_frequency_mhz'] = deepcopy(frozen.get('frequency_mhz'))
    for entry in entries:
        if not isinstance(entry, Mapping):
            continue
        kind, source_id = entry.get('source_kind'), entry.get('source_id')
        matches = [source for source in sources if isinstance(source, Mapping)
                   and source.get('source_kind') == kind and source.get('source_id') == source_id]
        associated = (valid and kind in ('confirmed_route', 'legacy_certificate')
                      and len(matches) == 1 and isinstance(matches[0].get('snapshot'), Mapping))
        if associated:
            route = deepcopy(dict(entry))
            route['application_state'] = (
                'applied' if parsed['status'] == 'applied'
                and entry.get('chain_id') in parsed['applied_chain_ids'] else 'selected'
            )
            route['source_snapshot'] = deepcopy(matches[0]['snapshot'])
        else:
            route = {key: deepcopy(entry.get(key)) for key in ('chain_id', 'source_kind', 'source_id')}
            route.update(application_state='unknown', source_snapshot=None)
        result['routes'].append(route)
    return result
