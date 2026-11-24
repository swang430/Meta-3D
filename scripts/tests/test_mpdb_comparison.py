import hashlib
import io
import zipfile
from types import SimpleNamespace

import numpy as np
import pytest
from scripts.tests.test_mpdb_conducted_project import sample
from scripts.mpdb_conducted_project import write_asc


def fixture(tmp_path):
    raw = tmp_path/'raw.mpdb'
    sample(raw, 16)
    archive = tmp_path/'source.zip'
    with zipfile.ZipFile(archive, 'w') as z:
        z.write(raw, 'R0B0S0D.mpdb')
    members = tmp_path/'members.npz'
    np.savez(members, source_sha256=hashlib.sha256(raw.read_bytes()).hexdigest(),
             **{f'L{i}': np.array([0, 1]) for i in range(16)})
    bundle = tmp_path/'asc.zip'
    with zipfile.ZipFile(bundle, 'w') as z:
        for t in range(4):
            for r in range(2):
                p = tmp_path/f'R0B0S0D_TX{t}_RX{r}_H.asc'
                write_asc(p, [[dict(delay_s=1e-8, real=1, imag=2), dict(delay_s=2e-8, real=2, imag=-1)]]*2, 24, 2.5e9)
                z.write(p, p.name)
    return SimpleNamespace(archive=archive, members=members, asc=bundle, bandwidth_mhz=100.,
                           points=3, amplitude_floor=1e-8, output=tmp_path/'report')


def test_file_comparison_does_not_invent_source_frame_alignment(tmp_path):
    from scripts.mpdb_comparison import analyze
    args = fixture(tmp_path)
    # 两行 ASC 没有逐帧来源清单，禁止按行数猜源帧。
    with pytest.raises(ValueError, match='源帧|恢复'):
        analyze(args)


def test_member_source_mismatch_rejected_before_calculation(tmp_path):
    from scripts.mpdb_comparison import analyze
    args = fixture(tmp_path)
    np.savez(args.members, source_sha256='wrong', **{f'L{i}': np.array([0,1]) for i in range(16)})
    with pytest.raises(ValueError, match='同源'):
        analyze(args)


def test_real_sample_37_and_unmatched_tail(tmp_path):
    import os
    from pathlib import Path
    from scripts.mpdb_comparison import analyze, write_report
    root = Path('/Users/Simon/Tools/MIMO-First/RT-IMT-2030')
    if not root.is_dir():
        pytest.skip('缺少外部真实文件')
    asc = tmp_path/'asc.zip'
    with zipfile.ZipFile(asc, 'w') as z:
        for p in root.glob('R0B0S0D_TX*_RX*_H.asc'):
            z.write(p, p.name)
    args = SimpleNamespace(archive=next(root.glob('*MPDB.zip')), asc=asc,
        members=Path('/private/tmp/p2108-vrt/docs/evidence/imt-three/members.npz'),
        bandwidth_mhz=100., points=41, amplitude_floor=1e-8, output=tmp_path/'result')
    report = analyze(args)
    assert len(report['frames']) == 37
    assert report['unmatched_source_frames'] == [37]
    assert report['formal_verdict'] is None
    from mimo_ota_simulator.channel_comparison import recover_asc_frames
    with zipfile.ZipFile(asc) as z:
        data=np.stack([np.loadtxt(io.BytesIO(z.read(f'R0B0S0D_TX{t}_RX{r}_H.asc')),skiprows=12).reshape(6188,24,3) for t in range(4) for r in range(2)],axis=1)
    recovered=recover_asc_frames(data,rate_hz=float((root/'R0B0S0D_TX0_RX0_H.asc').read_text().splitlines()[9].split()[0]),source_frame_count=38)
    assert report['amplitude_roundoff'] == recovered['amplitude_roundoff']
    assert report['alignment_status'] == 'unverified'
    assert report['offsets_hz'] == (np.arange(-20,21)*2.5e6).tolist()
    assert report['coverage']['phase_total'] == 38*16*41
    assert report['coverage']['phase_valid'] <= 37*16*41
    assert report['summary']['Lauraycs']['matrix_nmse_median'] > 0
    assert all(p['absolute_received_power_w'] is None for p in report['frames'][0]['power']['raw'])
    write_report(report, args.output)
    assert (args.output/'points.csv').read_text().count('\n') == 48545
    assert (args.output/'summary.json').is_file()
    import json
    assert json.loads((args.output/'report.json').read_text())['amplitude_roundoff'] == recovered['amplitude_roundoff']


def test_explicit_source_frame_manifest_and_download_values(tmp_path):
    import json
    from scripts.mpdb_comparison import analyze, write_report
    args=fixture(tmp_path)
    with zipfile.ZipFile(args.asc,'a') as z:
        links=[dict(tx=t,rx=r,file=f'R0B0S0D_TX{t}_RX{r}_H.asc',
              sha256=hashlib.sha256(z.read(f'R0B0S0D_TX{t}_RX{r}_H.asc')).hexdigest())
              for t in range(4) for r in range(2)]
        z.writestr('manifest.json',json.dumps(dict(mode='conducted',rate_source='source_frame_viewer_placeholder',
            source=dict(mpdb=hashlib.sha256((tmp_path/'raw.mpdb').read_bytes()).hexdigest(),
                        members=hashlib.sha256(args.members.read_bytes()).hexdigest()),frames=[10,13],links=links)))
    report=analyze(args)
    assert report['unmatched_source_frames'] == []
    assert report['coverage']['phase_fraction'] == 1
    assert report['summary']['Meta-3D']['matrix_nmse_median'] == pytest.approx(0,abs=1e-25)
    assert report['summary']['Lauraycs']['matrix_nmse_median'] == pytest.approx(0,abs=1e-25)
    assert report['frames'][0]['asc_time_s'] is None
    assert report['frames'][0]['power']['raw'][0]['carrier_coherent_gain'] == pytest.approx(10)
    assert report['frames'][0]['power']['raw'][0]['tap_power_sum'] == pytest.approx(10)


@pytest.mark.parametrize('bad', ['duplicate','missing','wrong_carrier','wrong_members'])
def test_bad_inputs_rejected(tmp_path,bad):
    from scripts.mpdb_comparison import analyze
    args=fixture(tmp_path)
    if bad == 'wrong_members':
        np.savez(args.members,source_sha256=hashlib.sha256((tmp_path/'raw.mpdb').read_bytes()).hexdigest(),
            **{f'L{i}':np.array([0]) for i in range(16)})

    elif bad == 'duplicate':
        with zipfile.ZipFile(args.asc,'a') as z, pytest.warns(UserWarning):
            name=z.namelist()[0]
            z.writestr(name,z.read(name))
    elif bad == 'missing':
        args.asc=tmp_path/'missing.zip'
        with zipfile.ZipFile(args.asc,'w') as z:
            z.writestr('unrelated.txt','')
    else:
        with zipfile.ZipFile(args.asc) as z:
            files={n:z.read(n).replace(b'2500000000.0 Carrier_Frequency',b'3500000000.0 Carrier_Frequency') for n in z.namelist()}
        with zipfile.ZipFile(args.asc,'w') as z:
            for n,data in files.items(): z.writestr(n,data)
    with pytest.raises(ValueError, match='成员数量' if bad == 'wrong_members' else '重复|八条|载频'):
        analyze(args)


@pytest.mark.parametrize('rate_source',[None,'historical_sampled_asc'])
@pytest.mark.parametrize('conflict',['mpdb','members','file_hash'])
def test_declared_provenance_checked_for_all_rate_sources(tmp_path,rate_source,conflict):
    import json
    from scripts.mpdb_comparison import analyze
    args=fixture(tmp_path)
    source=dict(mpdb=hashlib.sha256((tmp_path/'raw.mpdb').read_bytes()).hexdigest(),
                members=hashlib.sha256(args.members.read_bytes()).hexdigest())
    with zipfile.ZipFile(args.asc,'a') as z:
        links=[dict(tx=t,rx=r,file=f'R0B0S0D_TX{t}_RX{r}_H.asc',
            sha256=hashlib.sha256(z.read(f'R0B0S0D_TX{t}_RX{r}_H.asc')).hexdigest())
            for t in range(4) for r in range(2)]
        if conflict == 'file_hash':
            links[0]['sha256']='0'*64
        else:
            source[conflict]='0'*64
        manifest=dict(source=source,links=links)
        if rate_source is not None:
            manifest['rate_source']=rate_source
        z.writestr('manifest.json',json.dumps(manifest))
    # 冲突应在尝试数值恢复前拒绝，不能退回恢复后掩盖来源矛盾。
    with pytest.raises(ValueError,match='来源|摘要|同源'):
        analyze(args)
