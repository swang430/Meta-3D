import numpy as np
import pytest


def test_split_preserves_coherent_sum_and_budget_is_ceiling():
    from scripts import mpdb_budget as b
    h=np.array([1+2j, 2-1j, -1j]); t=np.array([0., 1e-8, 3e-8])
    data=[(h,t,np.array([0,0,0])) for _ in range(8)]
    result=b.scan_frame(data,np.array([-5e7,0,5e7]),[24,26,31],1e-8)
    assert set(result['methods']) == {f'{s}-{k}' for s in ('independent','shared') for k in (24,26,31)}
    for name, counts in result['used_taps'].items():
        assert max(counts) <= int(name.split('-')[1])
        assert max(counts) < 24
    assert result['carrier_max_absolute_error'] < 1e-12
    assert len(result['ranking']['independent']) == 1


def test_single_cluster_24_budget_matches_ce_and_preserves_deltas():
    from scripts import mpdb_budget as b
    from mimo_ota_simulator.tap_budget import compare_tap_budgets
    data=[(np.array([1+2j,2-1j]),np.array([0.,3e-8]),np.array([0,0])) for _ in range(8)]
    offsets=np.array([-5e7,0,5e7])
    direct=compare_tap_budgets(data,offsets,b.PHASE_PAIRS)
    adapted=b.scan_frame(data,offsets,[24,26,31],1e-8)
    for strategy in b.STRATEGIES:
        for budget in b.BUDGETS:
            name=f'{strategy}-{budget}'
            expected=direct['strategies'][strategy]['budgets'][str(budget)]
            assert adapted['used_taps'][name]==expected['used_taps']==[2]*8
            assert adapted['methods'][name]==expected['metrics']['methods']['candidate']
            assert adapted['delta'][name]==expected['delta']
            assert adapted['baseline'][strategy]==expected['metrics']['methods']['baseline']
            assert adapted['split_clusters'][name]==expected['split_clusters']
    assert adapted['base_cluster_count']==1


def test_invalid_source_rejected(tmp_path):
    from scripts.tests.test_mpdb_comparison import fixture
    from scripts import mpdb_budget as b
    args=fixture(tmp_path)
    np.savez(args.members,source_sha256='wrong',**{f'L{i}':np.array([0,1]) for i in range(16)})
    with pytest.raises(ValueError,match='同源'):
        b.analyze(args)


def test_small_nonzero_float32_rays_keep_finite_delays():
    from scripts import mpdb_budget as b
    data=[(np.array([1e-25+1e-25j,2e-25j],dtype=np.complex64),np.array([1e-8,2e-8]),np.array([0,0])) for _ in range(8)]
    result=b.scan_frame(data,np.array([-5e7,0,5e7]),[24,26,31],1e-30)
    assert all(x is not None for x in result['methods']['independent-24']['matrix_nmse'])


def test_real_38_frames_match_independent_research_baseline(tmp_path):
    from pathlib import Path
    from types import SimpleNamespace
    from scripts.mpdb_budget import analyze,write_report
    root=Path('/Users/Simon/Tools/MIMO-First')
    baseline=Path('/Users/Simon/.codex/visualizations/2026/10/06/01a11166-83b0-7532-8f2f-30ee597e6d2f/two-delay-comparison/points.npz')
    if not baseline.is_file(): pytest.skip('缺少外部研究基准')
    args=SimpleNamespace(archive=next((root/'RT-IMT-2030').glob('*MPDB.zip')),members=root/'docs/evidence/imt-three/members.npz',bandwidth_mhz=100.,points=41,amplitude_floor=1e-8)
    r=analyze(args)
    assert r['frame_ids']==list(range(38))
    assert r['formal_verdict'] is None
    assert r['summary']['shared-26']['used_taps_min']==24
    assert r['summary']['independent-31']['worse']>0
    with np.load(baseline,allow_pickle=False) as historical:
        for si,s in enumerate(r['strategies']):
            for k in r['tap_budgets']:
                name=f'{s}-{k}'
                matrix=np.array([f['methods'][name]['matrix_nmse'] for f in r['frames']],float)
                phase=np.array([f['methods'][name]['phase_error_deg'] for f in r['frames']],float)
                np.testing.assert_allclose(matrix,historical['matrix_nmse'][si,k-24],rtol=0,atol=1e-10)
                np.testing.assert_allclose(phase,historical['abs_phase_error_deg'][si,k-24],rtol=0,atol=1e-7)
                np.testing.assert_array_equal([f['used_taps'][name] for f in r['frames']],24+historical['extra_active_taps'][si,k-24])
    write_report(r,tmp_path/'result')
    assert (tmp_path/'result/points.csv').read_text().count('\n')==38*6*16*41+1


def test_single_cluster_file_report_and_csv_keep_ce_counts(tmp_path):
    import csv
    import hashlib
    import json
    from scripts.tests.test_mpdb_comparison import fixture
    from scripts.mpdb_budget import analyze,write_report
    args=fixture(tmp_path)
    np.savez(args.members,source_sha256=hashlib.sha256((tmp_path/'raw.mpdb').read_bytes()).hexdigest(),
        **{f'L{i}':np.array([0,0]) for i in range(16)})
    report=analyze(args)
    assert all(f['base_cluster_count']==1 for f in report['frames'])
    assert all(f['used_taps']['independent-24']==[2]*8 for f in report['frames'])
    write_report(report,args.output)
    saved=json.loads((args.output/'report.json').read_text())
    assert saved['frames'][0]['ce_metrics']['shared-24']['methods']['candidate']==saved['frames'][0]['methods']['shared-24']
    rows=list(csv.DictReader((args.output/'points.csv').open()))
    assert all(row['used_taps_a']==row['used_taps_b']=='2' for row in rows)
    assert any(abs(float(row['matrix_delta']))>0 for row in rows)
