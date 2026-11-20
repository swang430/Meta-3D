"""真实解析入口的合成正反例，不依赖用户附件。"""
import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location('fixture_mpdb', Path(__file__).resolve().parents[3] / 'api-service/tests/test_mpdb_input.py')
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)


def test_audit_reads_both_endpoints_and_keeps_unknown(tmp_path):
    from scripts.s5_evaluation.gcm_audit import audit
    source = tmp_path / 'input.zip'
    fixture.fixture_zip(source, times=(0, 1, 1.146))
    result = audit(source, coordinate_units='metres', speed_m_s=5, evidence={'coordinate_system': '操作者提供的待核说明'})
    assert result['hardware_eligible'] is False
    assert result['operator_evidence']['status'] == 'operator_supplied_unverified'
    assert result['source_files'][0]['sha256'] == fixture.hashlib.sha256(source.read_bytes()).hexdigest()
    for d, endpoint in zip(result['directions'], ('RX', 'TX')):
        assert d['mobile_endpoint'] == endpoint
        assert d['route_limits']['position_count'] == 3
        assert d['route_limits']['last_frame'] == 2
        assert d['route_limits']['cluster_spacing_ok'] is True
        assert d['route_limits']['general_editor_short_segments'] == [[1, 2]]
        assert d['positions'][-1]['mobile'][0] == pytest.approx(35.73, abs=1e-5)
        assert d['coordinate_system'] is None
        assert d['antenna_orientation'] is None
        assert d['cross_frame_path_identity'] is None
        assert d['raw_sample']['H'] == {'real': 1.0, 'imag': 0.0}
    assert result['reciprocal_positions_match'] is True


def test_unit_assumption_is_required(tmp_path):
    from scripts.s5_evaluation.gcm_audit import audit
    source = tmp_path / 'input.zip'
    fixture.fixture_zip(source)
    with pytest.raises(ValueError, match='米制'):
        audit(source, coordinate_units=None, speed_m_s=5)


def test_export_batch_counts_and_unknown_membership(tmp_path):
    import csv
    from scripts.s5_evaluation.gcm_cluster_evidence import audit_exports
    hashes = {'original.zip': 'source-hash'}
    for budget in (8, 16, 24):
        tag = '' if budget == 24 else f'_n{budget}'
        for kind in ('cdl', 'quality'):
            p = tmp_path / f'R0B0S0D_cluster_{kind}{tag}.csv'
            with p.open('w', newline='') as h:
                w = csv.writer(h)
                w.writerow(['LINK_ID', 'N_RAYS', 'N_CLUSTERS', 'CHANNEL_TYPE'])
                w.writerows([[7, 15, budget, 1]] * (budget if kind == 'cdl' else 1))
            hashes[p.name] = fixture.hashlib.sha256(p.read_bytes()).hexdigest()
    source = {'source_files': [{'sha256': 'source-hash'}], 'directions': [
        {'direction': 'downlink', 'frame_link_identity': [{'frame_id': 0, 'link_id': 7, 'path_count': 15, 'raw_type_zero': 0}]}]}
    results = audit_exports(tmp_path, hashes, source)
    assert [r['cluster_rows'] for r in results] == [8, 16, 24]
    assert all(r['ray_membership'] is None and r['cross_frame_cluster_identity'] is None for r in results)
    source['directions'][0]['frame_link_identity'][0]['path_count'] = 16
    with pytest.raises(ValueError, match='原始射线数'):
        audit_exports(tmp_path, hashes, source)
    hashes['original.zip'] = 'other-batch'
    with pytest.raises(ValueError, match='本批'):
        audit_exports(tmp_path, hashes, source)


def test_empty_operator_evidence_is_preserved(tmp_path):
    from scripts.s5_evaluation.gcm_audit import audit
    source = tmp_path / 'input.zip'
    fixture.fixture_zip(source)
    result = audit(source, coordinate_units='metres', speed_m_s=5, evidence={})
    assert result['operator_evidence']['status'] == 'operator_supplied_unverified'
    assert result['cluster_tdd']['frequencies_hz'] == {'downlink': [2400000000], 'uplink': [2400000000]}


def test_mismatched_frequency_writes_unverified_report(tmp_path):
    import subprocess
    import sys
    source, output = tmp_path / 'input.zip', tmp_path / 'out.json'
    def mutate(meta, entries, direction):
        if direction == 'uplink':
            entries['LINK/FREQUENCY.safetensors'] = fixture.tensor([[2500000000]] * 3, '<i8')
    fixture.fixture_zip(source, mutate=mutate)
    command = [sys.executable, '-m', 'scripts.s5_evaluation.gcm_audit', str(source),
               '--coordinate-units', 'metres', '--speed-m-s', '5', '--output', str(output)]
    run = subprocess.run(command, capture_output=True, text=True)
    assert run.returncode == 2
    result = fixture.json.loads(output.read_text())
    assert result['status'] == 'unverified' and result['hardware_eligible'] is False
    assert 'FREQUENCY' in result['reason']
