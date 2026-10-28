#!/usr/bin/env python3
"""CAICT 指定 raw 快照的单用途离线转换；仅文件读写，无应用/仪器依赖。

配置快照，非新测量。输入出处：
output/pc04a5b-deploy-D5Zfe4/topologies-after-ui.jsonl（SHA256 见常量）。
三个图数组与 tests/fixtures/pc04a5c_caict_source.json 的原始 JSON 完全一致才接受。
绝不回写源图、默认库、历史、绑定或端口映射；候选不是激活请求。
"""

import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path


SOURCE_ID = '87df2355-00f2-4fd6-9a38-ebacb2ccb2e5'
CHAMBER_ID = '59c73fbe-7362-4004-9a80-f72dd8779c3e'
CATEGORY_ID = '1d04e85c-6a27-4153-94a2-d2b07f2ff4a0'
LAB_ID = '7aea2b69-19d7-4e43-a6ec-9c0691156fc8'
SOURCE_FILE_SHA256 = '7d3b4a6e3786121d72b59137f9d701ca0cba4a00655c8d7c2b27ebdb38d33bed'
SOURCE_GRAPH_SHA256 = 'a7177b02fd15e91fc035fb360616b5db18ac831bc677bd16dd538767eac16153'
GRAPH_KEYS = ('nodes', 'connections', 'operating_modes')
# 用户裁决的逐对 probe_id 顺序；极化按每对 V/H，禁止按节点名称重建身份。
PROBE_ORDER = (1, 9, 2, 10, 3, 11, 4, 12, 5, 13, 6, 14, 7, 15, 8, 16)
QUANTITY_RULING = (
    '旧版20 dB仅标称/来源未核，非实测；原复合0.8 dB、5 m及cable_type完整留档，'
    '两侧未分配/未知，不进入当前补偿，不新增owner或聚合。'
    '软件声明不等于现场导通、RF认证、校准合格或B/HOLD解除。'
)


def canonical_sha256(value: object) -> str:
    """规范 JSON 的 UTF-8 SHA256；拒绝 NaN/Infinity，无尾换行。"""
    encoded = json.dumps(value, sort_keys=True, separators=(',', ':'),
                         ensure_ascii=False, allow_nan=False).encode('utf-8')
    return hashlib.sha256(encoded).hexdigest()


def _validate_identity(source: dict) -> None:
    if (source.get('id'), source.get('chamber_id'), source.get('switch_category_id')) != (
            SOURCE_ID, CHAMBER_ID, CATEGORY_ID):
        raise ValueError('仅接受授权源 UUID、chamber 与 category，不按名称选择')


def select_source(rows: list[dict], source_id: str) -> dict:
    """唯一准确 UUID 选源；重复、不存在或非授权身份均拒绝。"""
    if source_id != SOURCE_ID:
        raise ValueError('非授权源 UUID')
    selected = [row for row in rows if isinstance(row, dict) and row.get('id') == source_id]
    if len(selected) != 1:
        raise ValueError('源 UUID 必须恰好出现一次')
    _validate_identity(selected[0])
    return selected[0]


def _preflight(source: dict) -> list[dict]:
    """全量预检后才构造；冻结图 hash 同时拒绝新增路径、owner 和参考接线。"""
    _validate_identity(source)
    for key in GRAPH_KEYS:
        if not isinstance(source.get(key), list):
            raise ValueError(f'{key} 必须是原始 JSON 数组')
    nodes, edges = source['nodes'], source['connections']
    for kind, rows in (('node', nodes), ('connection', edges)):
        ids = [row['id'] for row in rows]
        if any(not isinstance(ident, str) or not ident for ident in ids) or len(ids) != len(set(ids)):
            raise ValueError(f'{kind} ID 必须非空且唯一')
    by_node = {node['id']: node for node in nodes}
    if by_node.get('ce_f64', {}).get('type') != 'channel_emulator':
        raise ValueError('缺少原 channel_emulator ce_f64')
    targets = [edge for edge in edges if edge.get('source') == 'ce_f64']
    ports = [edge.get('ce_port') for edge in targets]
    if len(targets) != 32 or set(ports) != {f'B{i}' for i in range(1, 33)} or len(set(ports)) != len(ports):
        raise ValueError('必须保留32个唯一 ce_port B1～B32')
    for index, edge in enumerate(targets):
        target = by_node.get(edge['target'], {})
        params = target.get('params', {})
        actual = (edge.get('ce_port'), params.get('ce_port'), params.get('probe_id'), params.get('polarization'))
        port = f'B{index + 1}'
        if (target.get('type') != 'probe' or type(params.get('probe_id')) is not int or
                actual != (port, port, PROBE_ORDER[index // 2], 'VH'[index % 2])):
            raise ValueError('原 CE/probe 身份或显式32路对应不符')
        if (edge.get('source_pin'), edge.get('target_pin')) != ('out', 'in'):
            raise ValueError('原保存 pin 必须为 out→in；B#是本次显式声明')
        if (edge.get('pa_gain_db'), edge.get('cable_loss_db'), edge.get('cable_length_m')) != (20.0, 0.8, 5.0):
            raise ValueError('旧标称20/复合损耗0.8/长度5必须保持原证据')
        if 'pc04a5c_pa_' + port in by_node or any(
                other['id'] in (edge['id']+'__pa_in', edge['id']+'__pa_out') for other in edges):
            raise ValueError('候选 PA/连线 ID 已存在，拒绝重复转换')
    # 不推广为任意图转换器：任何额外显式路径、owner、参考边或其它图变化都拒绝。
    if canonical_sha256({key: source[key] for key in GRAPH_KEYS}) != SOURCE_GRAPH_SHA256:
        raise ValueError('原图与已跟踪 raw fixture 不一致；不转换扩展或已转换图')
    return targets


def build_candidate(source: dict) -> tuple[dict, dict]:
    """只返回三个原图数组及映射清单，不修改传入 JSON。"""
    try:
        targets = _preflight(source)
    except (KeyError, TypeError, AttributeError) as exc:
        raise ValueError('源不是支持的完整 raw 配置快照') from exc
    graph = {key: deepcopy(source[key]) for key in GRAPH_KEYS}
    by_node = {node['id']: node for node in source['nodes']}
    replacement, routes, added = {}, [], []
    for old in targets:
        pa_id = 'pc04a5c_pa_' + old['ce_port']
        incoming_id, outgoing_id = old['id'] + '__pa_in', old['id'] + '__pa_out'
        note = (f"旧版标称/来源未核：{source['id']}/{old['id']}.pa_gain_db；"
                '原复合线缆0.8 dB、5 m未分配，不进入当前补偿；非实测/非资格')
        target = by_node[old['target']]
        added.append(dict(id=pa_id, type='amplifier', label='独立 PA ' + old['ce_port'],
            position={'x': 550.0, 'y': float(target['position']['y'])}, params={
                'ports': ['in', 'out'], 'port_directions': {'in': 'input', 'out': 'output'},
                'internal_paths': [{'from_port': 'in', 'to_port': 'out'}],
                'gain_db': old['pa_gain_db'],
                'nominal_metadata': {'gain_db': {'unit': 'dB', 'source_note': note, 'frequency_range_mhz': None}},
                'pc04a5c_legacy_connection': deepcopy(old)}))
        common = dict(ce_port=old['ce_port'], direction=old['direction'],
                      modes=deepcopy(old['modes']), cable_loss_db=None,
                      calibrated_loss_db=None, calibrated_phase_deg=None)
        first = dict(deepcopy(common), id=incoming_id, source=old['source'], source_pin=old['ce_port'],
                     target=pa_id, target_pin='in')
        last = dict(deepcopy(common), id=outgoing_id, source=pa_id, source_pin='out',
                    target=old['target'], target_pin=old['target_pin'])
        replacement[old['id']] = [first, last]
        routes.append(dict(original_connection_id=old['id'], original_connection=deepcopy(old),
            original_source_pin=old['source_pin'], declared_source_pin=old['ce_port'],
            ce_port=old['ce_port'], probe_node_id=old['target'], probe_id=target['params']['probe_id'],
            polarization=target['params']['polarization'], target_pin=old['target_pin'],
            pa_node_id=pa_id, replacement_connection_ids=[incoming_id, outgoing_id]))
    declarations = []
    probe_ids = {edge['target'] for edge in targets}
    for node in graph['nodes']:
        if node['id'] != 'ce_f64' and node['id'] not in probe_ids:
            continue
        before = deepcopy(node)
        if node['id'] == 'ce_f64':
            node['params']['ports'] = ['in1', 'in2', 'in3', 'in4'] + [edge['ce_port'] for edge in targets]
            node['params']['port_directions'] = {edge['ce_port']: 'output' for edge in targets}
        else:
            node['params']['ports'] = ['in']
        declarations.append(dict(node_id=node['id'], before=before, after=deepcopy(node)))
    graph['nodes'].extend(added)
    graph['connections'] = [part for edge in source['connections']
                            for part in replacement.get(edge['id'], [deepcopy(edge)])]
    mode_references = []
    for mode in graph['operating_modes']:
        if 'active_connections' in mode:
            before = deepcopy(mode['active_connections'])
            mode['active_connections'] = [part['id'] if isinstance(part, dict) else part
                for ident in before for part in replacement.get(ident, [ident])]
            mode_references.append(dict(mode_id=mode['id'], before=before, after=deepcopy(mode['active_connections'])))
    manifest = dict(
        source={key: source[key] for key in ('id', 'name', 'version', 'chamber_id', 'switch_category_id')},
        authorized_lab_profile_id=LAB_ID,
        source_file='output/pc04a5b-deploy-D5Zfe4/topologies-after-ui.jsonl',
        source_file_sha256=SOURCE_FILE_SHA256,
        source_graph_sha256=canonical_sha256({key: source[key] for key in GRAPH_KEYS}),
        candidate_graph_sha256=canonical_sha256(graph), routes=routes,
        mode_references=mode_references, node_declarations=declarations,
        quantity_ruling=QUANTITY_RULING, software_only=True,
        evidence_kind='配置快照，非新测量')
    return graph, manifest


def _preview(manifest: dict) -> str:
    lines = ['# CAICT 独立 PA 离线候选预览', '', '配置快照，非新测量；非实测、非资格。',
             QUANTITY_RULING, '',
             '| 原 connection ID | CE 声明 | 原 probe ID / 极化 / pin | 新 PA | 两条新边 | 损耗 |',
             '| --- | --- | --- | --- | --- | --- |']
    for row in manifest['routes']:
        lines.append(f"| {row['original_connection_id']} | out → {row['ce_port']} | "
                     f"{row['probe_node_id']} / {row['probe_id']} / {row['polarization']} / {row['target_pin']} | "
                     f"{row['pa_node_id']} | {' / '.join(row['replacement_connection_ids'])} | 未分配/未知 |")
    return '\n'.join(lines) + '\n'


def main() -> None:
    parser = argparse.ArgumentParser(description='仅从指定 CAICT raw JSONL 生成离线候选；不执行写库或硬件动作')
    parser.add_argument('--source-jsonl', required=True, type=Path)
    parser.add_argument('--source-id', required=True)
    parser.add_argument('--output-dir', required=True, type=Path)
    args = parser.parse_args()
    try:
        raw = args.source_jsonl.read_bytes()
        rows = [json.loads(line) for line in raw.decode('utf-8').splitlines() if line.strip()]
        source = select_source(rows, args.source_id)
        graph, manifest = build_candidate(source)
        manifest['input_file_sha256'] = hashlib.sha256(raw).hexdigest()
        manifest['input_file'] = str(args.source_jsonl)
        # 序列化/预检全部完成后才 mkdir；已有目录拒绝覆盖，不给源/旧副本推定令牌。
        outputs = {'candidate.json': json.dumps(graph, ensure_ascii=False, allow_nan=False, indent=2) + '\n',
                   'manifest.json': json.dumps(manifest, ensure_ascii=False, allow_nan=False, indent=2) + '\n',
                   'preview.md': _preview(manifest)}
        args.output_dir.mkdir()
        for name, content in outputs.items():
            (args.output_dir / name).write_text(content, encoding='utf-8')
    except (ValueError, OSError) as exc:
        parser.exit(2, f'拒绝生成：{exc}\n')


if __name__ == '__main__':
    main()
