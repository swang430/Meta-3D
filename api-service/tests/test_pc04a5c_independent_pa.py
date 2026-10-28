"""PC04A5c：原 raw 配置快照，非新测量；不经应用 schema 导出。

来源 output/pc04a5b-deploy-D5Zfe4/topologies-after-ui.jsonl，整文件 SHA256
7d3b4a6e3786121d72b59137f9d701ca0cba4a00655c8d7c2b27ebdb38d33bed。
本文件只按路径导入离线脚本；pytest 的上级 conftest 仍须在进程外先隔离。
"""

from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/pc04a5c_independent_pa.py'
FIXTURE = Path(__file__).parent / 'fixtures/pc04a5c_caict_source.json'
SOURCE_ID = '87df2355-00f2-4fd6-9a38-ebacb2ccb2e5'
SOURCE_GRAPH_SHA = 'a7177b02fd15e91fc035fb360616b5db18ac831bc677bd16dd538767eac16153'
# 独立于被测实现的逐对身份裁决，不由名称或画面坐标推断。
PROBE_ORDER = [1, 9, 2, 10, 3, 11, 4, 12, 5, 13, 6, 14, 7, 15, 8, 16]


def load_converter():
    assert SCRIPT.is_file(), '缺少 PC04A5c 离线转换器'
    spec = importlib.util.spec_from_file_location('pc04a5c_independent_pa', SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def converter():
    return load_converter()


@pytest.fixture
def source():
    return json.loads(FIXTURE.read_text(encoding='utf-8'))


def test_candidate_has_exact_mapping_and_no_invented_loss(source):
    converter = load_converter()
    before = deepcopy(source)
    graph, manifest = converter.build_candidate(source)
    assert source == before
    assert set(graph) == {'nodes', 'connections', 'operating_modes'}
    assert len(graph['nodes']) == 120
    assert len(graph['connections']) == 122
    assert len(manifest['routes']) == 32
    edges = {e['id']: e for e in graph['connections']}
    nodes = {n['id']: n for n in graph['nodes']}
    assert len(edges) == 122
    assert len(nodes) == 120
    assert len({r['pa_node_id'] for r in manifest['routes']}) == 32
    for index, row in enumerate(manifest['routes']):
        old = next(e for e in source['connections'] if e['id'] == row['original_connection_id'])
        first, last = [edges[x] for x in row['replacement_connection_ids']]
        pa = nodes[row['pa_node_id']]
        probe_id, pol = PROBE_ORDER[index // 2], 'VH'[index % 2]
        assert (row['ce_port'], row['probe_id'], row['polarization']) == (f'B{index+1}', probe_id, pol)
        assert row['probe_node_id'] == old['target']
        assert row['target_pin'] == 'in'
        assert row['original_connection'] == old
        assert row['original_source_pin'] == 'out'
        assert row['declared_source_pin'] == old['ce_port']
        assert (first['source'], first['source_pin'], first['target_pin']) == ('ce_f64', old['ce_port'], 'in')
        assert (last['target'], last['target_pin'], last['source_pin']) == (old['target'], old['target_pin'], 'out')
        assert first['target'] == last['source'] == pa['id']
        for segment in (first, last):
            assert segment['cable_loss_db'] is None
            assert segment['calibrated_loss_db'] is None
            assert segment['calibrated_phase_deg'] is None
            assert not {'cable_length_m', 'cable_type', 'pa_gain_db', 'loss_owner_connection_id'} & segment.keys()
            assert segment['modes'] == old['modes']
            assert segment['direction'] == old['direction']
            assert segment['ce_port'] == old['ce_port']
        assert pa['type'] == 'amplifier'
        assert pa['params']['ports'] == ['in', 'out']
        assert pa['params']['port_directions'] == {'in': 'input', 'out': 'output'}
        assert pa['params']['internal_paths'] == [{'from_port': 'in', 'to_port': 'out'}]
        assert pa['params']['gain_db'] == old['pa_gain_db'] == 20.0
        assert pa['params']['pc04a5c_legacy_connection'] == old
        nominal = pa['params']['nominal_metadata']['gain_db']
        assert nominal['unit'] == 'dB' and nominal['frequency_range_mhz'] is None
        assert f'{SOURCE_ID}/{old["id"]}.pa_gain_db' in nominal['source_note']
        assert '旧版标称/来源未核' in nominal['source_note']
        assert old['cable_loss_db'] == 0.8 and old['cable_length_m'] == 5.0
        assert old['cable_type'] == 'Phase-matched N-N + 集成PA + Semi-rigid'
        assert old['calibrated_loss_db'] is None and old['calibrated_phase_deg'] is None
        assert old['id'] not in edges
    assert manifest['source_graph_sha256'] == SOURCE_GRAPH_SHA
    assert manifest['candidate_graph_sha256'] == converter.canonical_sha256(graph)
    assert manifest['software_only'] is True
    assert manifest['source']['id'] == SOURCE_ID
    assert manifest['source_file_sha256'] == '7d3b4a6e3786121d72b59137f9d701ca0cba4a00655c8d7c2b27ebdb38d33bed'


def test_preserves_non_targets_and_only_adds_allowed_port_declarations(converter, source):
    graph, manifest = converter.build_candidate(source)
    old_targets = {e['id'] for e in source['connections'] if e['source'] == 'ce_f64'}
    unchanged = [e for e in source['connections'] if e['id'] not in old_targets]
    assert len(unchanged) == 58
    assert [e for e in graph['connections'] if e['id'] in {x['id'] for x in unchanged}] == unchanged
    target_nodes = {e['target'] for e in source['connections'] if e['id'] in old_targets}
    new_nodes = {n['id']: n for n in graph['nodes']}
    untouched = [n for n in source['nodes'] if n['id'] not in target_nodes | {'ce_f64'}]
    assert len(untouched) == 55
    assert [new_nodes[n['id']] for n in untouched] == untouched
    declarations = {x['node_id']: x for x in manifest['node_declarations']}
    assert len(declarations) == 33
    for old in source['nodes']:
        if old['id'] not in target_nodes | {'ce_f64'}:
            continue
        new = new_nodes[old['id']]
        assert declarations[old['id']] == {'node_id': old['id'], 'before': old, 'after': new}
        stripped = deepcopy(new)
        stripped['params'].pop('ports')
        if old['id'] == 'ce_f64':
            assert new['params']['ports'] == ['in1', 'in2', 'in3', 'in4'] + [f'B{i}' for i in range(1, 33)]
            assert new['params']['port_directions'] == {f'B{i}': 'output' for i in range(1, 33)}
            stripped['params'].pop('port_directions')
        else:
            assert new['params']['ports'] == ['in']
        assert stripped == old


def test_replaces_mode_references_in_original_order(converter, source):
    graph, manifest = converter.build_candidate(source)
    targets = {e['id'] for e in source['connections'] if e['source'] == 'ce_f64'}
    changes = {x['mode_id']: x for x in manifest['mode_references']}
    unchanged = 0
    for old, new in zip(source['operating_modes'], graph['operating_modes']):
        expected = [part for ident in old['active_connections']
                    for part in ([ident+'__pa_in', ident+'__pa_out'] if ident in targets else [ident])]
        assert new['active_connections'] == expected
        assert changes[old['id']] == {'mode_id': old['id'], 'before': old['active_connections'], 'after': expected}
        restored = deepcopy(new)
        restored['active_connections'] = old['active_connections']
        assert restored == old
        if expected == old['active_connections']:
            assert new == old
            unchanged += 1
    assert unchanged == 3


def test_canonical_hash_has_exact_utf8_json_contract(converter):
    assert converter.canonical_sha256({'中': 1, 'a': [None, 0.0]}) == hashlib.sha256(b'{"a":[null,0.0],"\xe4\xb8\xad":1}').hexdigest()
    with pytest.raises(ValueError):
        converter.canonical_sha256(float('nan'))


@pytest.mark.parametrize('count', [0, 2])
def test_select_source_rejects_missing_or_ambiguous_uuid(converter, source, count):
    rows = [deepcopy(source) for _ in range(count)]
    before = deepcopy(rows)
    with pytest.raises(ValueError):
        converter.select_source(rows, SOURCE_ID)
    assert rows == before


def test_select_source_uses_uuid_not_same_name(converter, source):
    other = deepcopy(source)
    other['id'] = 'not-authorized'
    assert converter.select_source([other, source], SOURCE_ID) == source
    with pytest.raises(ValueError):
        converter.select_source([other], 'not-authorized')


BAD_CASES = [
    'identity', 'chamber', 'category', 'missing_ce', 'duplicate_ce',
    'probe_identity', 'probe_type', 'probe_ce_port', 'probe_polarization',
    'explicit_path', 'owner', 'owned', 'existing_pa', 'existing_replacement',
    'source_pin', 'target_pin', 'reference_edge', 'second_conversion',
    'duplicate_node', 'duplicate_edge', 'nominal_gain', 'composite_loss',
    'composite_length', 'changed_graph',
]


def invalid_source(source, case):
    bad = deepcopy(source)
    target = next(e for e in bad['connections'] if e['source'] == 'ce_f64')
    probe = next(n for n in bad['nodes'] if n['id'] == target['target'])
    if case == 'identity':
        bad['id'] = 'not-authorized'
    elif case == 'chamber':
        bad['chamber_id'] = 'other'
    elif case == 'category':
        bad['switch_category_id'] = 'other'
    elif case == 'missing_ce':
        bad['connections'].remove(target)
    elif case == 'duplicate_ce':
        bad['connections'][5]['ce_port'] = 'B1'
    elif case == 'probe_identity':
        probe['params']['probe_id'] = 9
    elif case == 'probe_type':
        probe['type'] = 'antenna'
    elif case == 'probe_ce_port':
        probe['params']['ce_port'] = 'B2'
    elif case == 'probe_polarization':
        probe['params']['polarization'] = 'X'
    elif case == 'explicit_path':
        bad['operating_modes'][0]['rf_paths'] = [{'connection_ids': [target['id']]}]
    elif case == 'owner':
        target['loss_owner_connection_id'] = bad['connections'][0]['id']
    elif case == 'owned':
        bad['connections'][0]['loss_owner_connection_id'] = target['id']
    elif case == 'existing_pa':
        bad['nodes'].append({'id': 'pc04a5c_pa_B1', 'type': 'amplifier'})
    elif case == 'existing_replacement':
        bad['connections'][0]['id'] = target['id']+'__pa_in'
    elif case == 'source_pin':
        target['source_pin'] = 'B1'
    elif case == 'target_pin':
        target['target_pin'] = 'changed'
    elif case == 'reference_edge':
        bad['connections'].append({'id': 'new-reference', 'source': probe['id'], 'target': 'ce_f64'})
    elif case == 'second_conversion':
        target['target'] = 'pc04a5c_pa_B1'
        probe['type'] = 'amplifier'
    elif case == 'duplicate_node':
        bad['nodes'].append(deepcopy(probe))
    elif case == 'duplicate_edge':
        bad['connections'].append(deepcopy(target))
    elif case == 'nominal_gain':
        target['pa_gain_db'] = 21
    elif case == 'composite_loss':
        target['cable_loss_db'] = 0
    elif case == 'composite_length':
        target['cable_length_m'] = 4
    elif case == 'changed_graph':
        bad['nodes'][0]['label'] = 'changed'
    return bad


@pytest.mark.parametrize('case', BAD_CASES)
def test_rejects_changed_or_ambiguous_source_without_mutation(converter, source, case):
    bad = invalid_source(source, case)
    before = deepcopy(bad)
    with pytest.raises(ValueError):
        converter.build_candidate(bad)
    assert bad == before


def invoke_cli(input_path, output_path):
    return subprocess.run([sys.executable, str(SCRIPT), '--source-jsonl', str(input_path),
                           '--source-id', SOURCE_ID, '--output-dir', str(output_path)],
                          capture_output=True, text=True)


@pytest.mark.parametrize('case', BAD_CASES + ['missing_uuid', 'duplicate_uuid'])
def test_cli_rejects_before_creating_output(converter, source, tmp_path, case):
    rows = ([invalid_source(source, case)] if case in BAD_CASES else
            [] if case == 'missing_uuid' else [source, source])
    input_path = tmp_path / 'input.jsonl'
    input_path.write_text(''.join(json.dumps(x, ensure_ascii=False)+'\n' for x in rows), encoding='utf-8')
    before = input_path.read_bytes()
    output = tmp_path / 'candidate'
    result = invoke_cli(input_path, output)
    assert result.returncode != 0, result.stdout
    assert not output.exists()
    assert input_path.read_bytes() == before


def test_cli_writes_only_complete_new_evidence_and_refuses_overwrite(converter, source, tmp_path):
    output = tmp_path / 'candidate'
    result = invoke_cli(FIXTURE, output)
    assert result.returncode == 0, result.stderr
    assert {p.name for p in output.iterdir()} == {'candidate.json', 'manifest.json', 'preview.md'}
    candidate = json.loads((output / 'candidate.json').read_text(encoding='utf-8'))
    manifest = json.loads((output / 'manifest.json').read_text(encoding='utf-8'))
    expected, _ = converter.build_candidate(source)
    assert candidate == expected
    assert manifest['input_file_sha256'] == hashlib.sha256(FIXTURE.read_bytes()).hexdigest()
    preview = (output / 'preview.md').read_text(encoding='utf-8')
    for row in manifest['routes']:
        assert row['original_connection_id'] in preview
        assert row['pa_node_id'] in preview
        assert all(x in preview for x in row['replacement_connection_ids'])
        assert f'out → {row["ce_port"]}' in preview
    assert '未分配/未知' in preview
    assert '非实测' in preview
    before = {p.name: p.read_bytes() for p in output.iterdir()}
    again = invoke_cli(FIXTURE, output)
    assert again.returncode != 0
    assert {p.name: p.read_bytes() for p in output.iterdir()} == before
