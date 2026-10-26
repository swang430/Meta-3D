"""拓扑标称声明的纯 JSON 写校验；不授予实测或硬件资格。"""
from copy import deepcopy
from math import isfinite
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator

MISSING = object()
NODE_FIELDS = {
    'amplifier': {'gain_db': 'dB'}, 'pad': {'attenuation_db': 'dB'},
    'combiner': {'loss_db': 'dB'}, 'probe': {'gain_dbi': 'dBi'},
    'antenna': {'gain_dbi': 'dBi'}, 'reference_antenna': {'gain_dbi': 'dBi'},
}
EDGE_FIELDS = {'pa_gain_db': 'dB', 'cable_loss_db': 'dB'}
CONNECTION_NUMERIC_FIELDS = {'cable_loss_db', 'cable_length_m',
                             'calibrated_loss_db', 'calibrated_phase_deg'}


class NominalFieldMetadata(BaseModel):
    model_config = ConfigDict(extra='forbid')
    unit: Literal['dB', 'dBi']
    source_note: str | None = None
    frequency_range_mhz: tuple[float, float] | None = None

    @field_validator('source_note', mode='before')
    @classmethod
    def strict_source(cls, value):
        if value is not None and not isinstance(value, str):
            raise ValueError('来源说明必须为字符串或null')
        return (value.strip() or None) if value is not None else None

    @field_validator('frequency_range_mhz', mode='before')
    @classmethod
    def strict_range(cls, value):
        if value is None:
            return None
        if (not isinstance(value, (list, tuple)) or len(value) != 2
                or any(type(v) not in (int, float) or not isfinite(v) or v <= 0 for v in value)
                or value[0] > value[1]):
            raise ValueError('频率范围必须为两个有限正数且起点不大于终点')
        return value


def same_json(left, right):
    if left is MISSING or right is MISSING:
        return left is right
    if type(left) in (int, float) and type(right) in (int, float):
        return left == right
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        return left.keys() == right.keys() and all(same_json(left[k], right[k]) for k in left)
    if isinstance(left, list):
        return len(left) == len(right) and all(same_json(a, b) for a, b in zip(left, right))
    return left == right


def validate_number(value, *, key, nonnegative=False):
    if value is None:
        return
    if type(value) not in (int, float) or not isfinite(value):
        raise ValueError(f'{key} 必须为有限数值或null')
    if nonnegative and value < 0:
        raise ValueError(f'{key} 不得小于0')


def _validate_metadata(obj, fields):
    if 'nominal_metadata' not in obj:
        return
    metadata = obj['nominal_metadata']
    if not isinstance(metadata, dict):
        raise ValueError('nominal_metadata 必须为字段说明对象')
    for key, value in metadata.items():
        if key not in fields or not isinstance(value, dict):
            raise ValueError(f'不支持的标称元数据字段：{key}')
        parsed = NominalFieldMetadata.model_validate(value)
        if parsed.unit != fields[key]:
            raise ValueError(f'{key} 的单位必须为 {fields[key]}')


def validate_nominal_write(nodes, connections, *, previous_nodes=None, previous_connections=None) -> None:
    old_nodes = {n['id']: n for n in previous_nodes or []}
    old_edges = {e['id']: e for e in previous_connections or []}
    for node in nodes:
        fields = NODE_FIELDS.get(node['type'], {})
        params = node.get('params', {})
        prior_node = old_nodes.get(node['id'], {})
        # 更换器件类型不是旧器件的未修改声明。
        previous = prior_node.get('params', {}) if prior_node.get('type') == node['type'] else {}
        for key in fields:
            value = params.get(key, MISSING)
            if value is not MISSING and not same_json(value, previous.get(key, MISSING)):
                validate_number(value, key=key, nonnegative=key in ('attenuation_db', 'loss_db'))
        _validate_metadata(params, fields)
    for edge in connections:
        value = edge.get('pa_gain_db', MISSING)
        if value is not MISSING and not same_json(value, old_edges.get(edge['id'], {}).get('pa_gain_db', MISSING)):
            validate_number(value, key='pa_gain_db')
        _validate_metadata(edge, EDGE_FIELDS)


def normalize_nominal_metadata(raw, previous=MISSING):
    """仅在已验证的节点params/连线直属位置调用，绝不递归解释opaque扩展。"""
    old = previous if isinstance(previous, dict) else {}
    return {key: (deepcopy(value) if same_json(value, old.get(key, MISSING))
                  else NominalFieldMetadata.model_validate(value).model_dump(mode='json'))
            for key, value in raw.items()}


def _preserve_unchanged_json(raw, normalized, previous=MISSING):
    if same_json(raw, previous):
        return deepcopy(previous)
    if isinstance(raw, dict) and isinstance(normalized, dict):
        old = previous if isinstance(previous, dict) else {}
        result = {}
        for key, value in raw.items():
            prior = old.get(key, MISSING)
            if same_json(value, prior):
                result[key] = deepcopy(prior)
            elif key in normalized:
                result[key] = _preserve_unchanged_json(value, normalized[key], prior)
        return result
    if isinstance(raw, list) and isinstance(normalized, list):
        old = previous if isinstance(previous, list) else []
        return [_preserve_unchanged_json(value, normalized[i], old[i] if i < len(old) else MISSING)
                for i, value in enumerate(raw)]
    return deepcopy(normalized)


def preserve_graph_rows(raw_rows, normalized_rows, previous_rows=None):
    old = {row['id']: row for row in previous_rows or []}
    saved = []
    for raw, normalized in zip(raw_rows, normalized_rows):
        previous = old.get(raw['id'], {})
        result = _preserve_unchanged_json(raw, normalized, old.get(raw['id'], MISSING))
        if 'type' in normalized and 'nominal_metadata' in raw.get('params', {}):
            result['params']['nominal_metadata'] = normalize_nominal_metadata(
                raw['params']['nominal_metadata'], previous.get('params', {}).get('nominal_metadata', MISSING))
        saved.append(result)
    return saved
