from types import SimpleNamespace
import pytest
from scripts.tests.test_mpdb_comparison import fixture


def test_adapter_uses_ce_and_reports_frozen_partitions(tmp_path):
    from scripts.mpdb_purpose import analyze, write_report
    args=fixture(tmp_path)
    args.asc=None
    import zipfile, numpy as np, hashlib
    raw=tmp_path/'raw.mpdb'
    with zipfile.ZipFile(raw) as z: entries={n:z.read(n) for n in z.namelist()}
    for name,data in entries.items():
        if name.startswith('LINK/FRAME_ID/'):
            n=int.from_bytes(data[:8],'little'); offset=8+n
            values=np.frombuffer(data[offset:],dtype='<i4')
            entries[name]=data[:offset]+((values-10)//3).astype('<i4').tobytes()
    with zipfile.ZipFile(raw,'w') as z:
        for name,data in entries.items(): z.writestr(name,data)
    with zipfile.ZipFile(args.archive,'w') as z: z.write(raw,'R0B0S0D.mpdb')
    np.savez(args.members,source_sha256=hashlib.sha256(raw.read_bytes()).hexdigest(),**{f'L{i}':np.array([0,1]) for i in range(16)})
    args.selection_start=0; args.selection_end=0; args.holdout_start=1; args.holdout_end=1
    args.objective='phase'; args.mode='ota'; args.tap_budget_max=31
    args.matrix_nmse_p95_max=1e6; args.phase_error_p95_max_deg=180.; args.manual_candidate='shared-24'
    report=analyze(args)
    assert report['evaluation']['plan']['selection_frames']==(0,)
    assert report['evaluation']['holdout']['frames']==[1]
    assert report['evaluation']['manual_candidate']=='shared-24'
    assert report['evaluation']['ota_status']=='unverified'
    assert report['formal_verdict'] is None
    assert report['hardware_verified'] is False
    assert report['evaluation']['provenance']['existing_asc_reference']['declared_applicable_frames']==[]
    write_report(report,tmp_path/'result')
    assert 'partition' in (tmp_path/'result/points.csv').read_text().splitlines()[0]


def test_absent_source_frames_rejected_before_scanning(tmp_path,monkeypatch):
    from scripts import mpdb_purpose as p
    args=fixture(tmp_path)
    args.asc=None
    import zipfile, numpy as np, hashlib
    raw=tmp_path/'raw.mpdb'
    with zipfile.ZipFile(raw) as z: entries={n:z.read(n) for n in z.namelist()}
    for name,data in entries.items():
        if name.startswith('LINK/FRAME_ID/'):
            n=int.from_bytes(data[:8],'little'); offset=8+n
            values=np.frombuffer(data[offset:],dtype='<i4')
            entries[name]=data[:offset]+((values-10)//3).astype('<i4').tobytes()
    with zipfile.ZipFile(raw,'w') as z:
        for name,data in entries.items(): z.writestr(name,data)
    with zipfile.ZipFile(args.archive,'w') as z: z.write(raw,'R0B0S0D.mpdb')
    np.savez(args.members,source_sha256=hashlib.sha256(raw.read_bytes()).hexdigest(),**{f'L{i}':np.array([0,1]) for i in range(16)})
    args.selection_start=0; args.selection_end=25; args.holdout_start=26; args.holdout_end=37
    args.objective='phase'; args.mode='conducted'; args.tap_budget_max=31
    args.matrix_nmse_p95_max=1.; args.phase_error_p95_max_deg=60.; args.manual_candidate=None
    def forbidden(*args): raise AssertionError('不得先扫描再检查源帧')
    monkeypatch.setattr(p.budget,'analyze',forbidden)
    with pytest.raises(ValueError,match='源帧'):
        p.analyze(args)


def test_real_asc_is_seventh_candidate_on_common_frames(tmp_path,monkeypatch):
    from scripts.mpdb_purpose import analyze, write_report
    from scripts.mpdb_comparison import analyze as compare
    from pathlib import Path
    import zipfile
    root=Path('/Users/Simon/Tools/MIMO-First/RT-IMT-2030')
    if not root.is_dir():pytest.skip('缺少实样')
    args=SimpleNamespace(archive=next(root.glob('*MPDB.zip')),
        members=Path('/private/tmp/p2110-vrt/docs/evidence/imt-three/members.npz'),asc=tmp_path/'asc.zip',
        bandwidth_mhz=100.,points=41,amplitude_floor=1e-8,selection_start=0,selection_end=25,
        holdout_start=26,holdout_end=None,tap_budget_max=31,matrix_nmse_p95_max=1.,phase_error_p95_max_deg=60.,
        objective='phase',mode='conducted',manual_candidate='existing-asc')
    with zipfile.ZipFile(args.asc,'w') as z:
        for path in root.glob('R0B0S0D_TX*_RX*_H.asc'):z.write(path,path.name)
    import mimo_ota_simulator.candidate_evaluation as ce
    original_evaluate=ce.evaluate_candidates
    def checked_evaluate(plan,candidates,*,provenance,manual_candidate):
        for name,candidate in candidates.items():
            for frame,row in candidate['frames'].items():
                metrics=row['metrics']
                assert metrics['offsets_hz']==provenance['offsets_hz']
                assert [list(pair) for pair in metrics['port_pairs']]==[list(pair) for pair in provenance['port_pairs']]
                assert metrics['amplitude_floor']==provenance['amplitude_floor']
                if name=='existing-asc':
                    assert row.get('delta') is None
                    assert 'baseline' not in metrics['methods']
                else:
                    assert set(row['delta'])=={'matrix_nmse','phase_error_deg'}
        return original_evaluate(plan,candidates,provenance=provenance,manual_candidate=manual_candidate)
    monkeypatch.setattr(ce,'evaluate_candidates',checked_evaluate)
    report=analyze(args)
    e=report['evaluation']
    assert 'existing-asc' in e['selection']
    for summary in (e['selection']['existing-asc'],e['manual_holdout']):
        changes=summary['changes_against_same_strategy_baseline']
        for metric in ('matrix_nmse','phase_error_deg'):
            evidence=changes.get(metric) if changes is not None else None
            assert evidence['status']=='unverified'
            assert evidence['coverage']==0 and evidence['valid']==0
            assert evidence['covered_frames']==[]
            assert evidence['unverified_frames']==summary['frames']
            assert all(evidence[key] is None for key in ('improved','worse','unchanged'))
    for name,summary in e['selection'].items():
        if name=='existing-asc':continue
        assert summary['unverified_frames']==[]
        for evidence in summary['changes_against_same_strategy_baseline'].values():
            assert evidence['status']=='verified' and evidence['coverage']==1
            assert sum(evidence[key] for key in ('improved','worse','unchanged'))==evidence['valid']==evidence['total']
    assert e['manual_holdout']['frames']==list(range(26,37))
    assert report['common_frame_ids']==list(range(37))
    assert report['excluded_source_frame_review']['frame_id']==37
    assert report['excluded_source_frame_review']['existing_asc'] is None
    direct=compare(args)
    assert report['source']['asc']==direct['source']['asc']
    assert e['provenance']['existing_asc_reference']['applicable_frames']==list(range(37))
    assert e['selection']['existing-asc']['phase_error_deg']['valid']==26*16*41
    assert report['asc_comparison']['frames'][0]['methods']['Lauraycs']==direct['frames'][0]['methods']['Lauraycs']
    write_report(report,tmp_path/'result')
    import csv
    from collections import Counter
    with (tmp_path/'result/points.csv').open(newline='') as fp:
        rows=list(csv.DictReader(fp))
    counts=Counter(row['candidate_id'] for row in rows)
    assert set(counts)==set(e['candidate_parameters'])
    assert counts['existing-asc']==37*16*41
    asc_rows=[row for row in rows if row['candidate_id']=='existing-asc']
    assert {int(row['frame']) for row in asc_rows}==set(range(37))
    assert len({(row['frame'],row['offset_hz'],row['port_a'],row['port_b']) for row in asc_rows})==len(asc_rows)
    for row in asc_rows:
        frame=report['asc_comparison']['frames'][int(row['frame'])]
        pair=report['asc_comparison']['port_pairs'].index((int(row['port_a']),int(row['port_b'])))
        offset=report['asc_comparison']['offsets_hz'].index(float(row['offset_hz']))
        assert float(row['phase_error_deg'])==frame['methods']['Lauraycs']['phase_error_deg'][pair][offset]
        assert float(row['matrix_nmse'])==frame['methods']['Lauraycs']['matrix_nmse'][offset]
    args.holdout_end=37
    with pytest.raises(ValueError,match='ASC|共同'):
        analyze(args)
    args.holdout_end=36
    args.asc.write_bytes(b'not a zip')
    with pytest.raises(zipfile.BadZipFile):
        analyze(args)


def two_frame_input(tmp_path,with_asc):
    import hashlib,json,zipfile
    import numpy as np
    args=fixture(tmp_path)
    raw=tmp_path/'raw.mpdb'
    with zipfile.ZipFile(raw) as z:entries={n:z.read(n) for n in z.namelist()}
    for name,data in entries.items():
        if name.startswith('LINK/FRAME_ID/'):
            offset=8+int.from_bytes(data[:8],'little')
            values=np.frombuffer(data[offset:],dtype='<i4')
            entries[name]=data[:offset]+((values-10)//3).astype('<i4').tobytes()
    with zipfile.ZipFile(raw,'w') as z:
        for name,data in entries.items():z.writestr(name,data)
    with zipfile.ZipFile(args.archive,'w') as z:z.write(raw,'R0B0S0D.mpdb')
    np.savez(args.members,source_sha256=hashlib.sha256(raw.read_bytes()).hexdigest(),**{f'L{i}':np.array([0,1]) for i in range(16)})
    if with_asc:
        with zipfile.ZipFile(args.asc,'a') as z:
            links=[dict(tx=t,rx=r,file=f'R0B0S0D_TX{t}_RX{r}_H.asc',sha256=hashlib.sha256(z.read(f'R0B0S0D_TX{t}_RX{r}_H.asc')).hexdigest()) for t in range(4) for r in range(2)]
            z.writestr('manifest.json',json.dumps(dict(mode='conducted',rate_source='source_frame_viewer_placeholder',frames=[0,1],source=dict(mpdb=hashlib.sha256(raw.read_bytes()).hexdigest(),members=hashlib.sha256(args.members.read_bytes()).hexdigest()),links=links)))
    else:args.asc=None
    args.selection_start=0;args.selection_end=0;args.holdout_start=1;args.holdout_end=None
    args.objective='phase';args.mode='conducted';args.tap_budget_max=31
    args.matrix_nmse_p95_max=1.;args.phase_error_p95_max_deg=60.;args.manual_candidate='existing-asc' if with_asc else 'shared-24'
    return args


@pytest.mark.parametrize('with_asc',[False,True])
def test_omitted_end_uses_actual_two_frame_scope_and_rejects_explicit_unavailable(tmp_path,with_asc):
    from scripts.mpdb_purpose import analyze
    args=two_frame_input(tmp_path,with_asc)
    report=analyze(args)
    assert report['evaluation']['plan']['holdout_frames']==(1,)
    assert report['common_frame_ids']==[0,1]
    assert len(report['evaluation']['candidate_parameters'])==(7 if with_asc else 6)
    if with_asc:
        assert report['asc_comparison']['unmatched_source_frames']==[]
        assert report['evaluation']['manual_holdout']['missing_frames']==[]
    args.holdout_end=2
    with pytest.raises(ValueError,match='源帧|ASC|共同'):analyze(args)
