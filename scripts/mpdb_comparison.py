"""比较已有八路传导 ASC 与同源成员方案，只输出离线辅助分析。"""
import argparse
import csv
import hashlib
import io
import json
import math
from pathlib import Path
import tempfile
import zipfile

import numpy as np

if __package__:
    from .mpdb_port_evidence import read_downlink, PAIRS
    from .mpdb_conducted_project import validate_members_container
    from .imt_conducted import inspect
else:
    from mpdb_port_evidence import read_downlink, PAIRS
    from mpdb_conducted_project import validate_members_container
    from imt_conducted import inspect

LIMIT = 256 * 1024**2
PORTS = sorted(PAIRS)
PHASE_PAIRS = [(a,b) for a in range(8) for b in range(a+1,8)
               if PORTS[a][0] == PORTS[b][0] or PORTS[a][1] == PORTS[b][1]]


def checked_zip(path):
    container = zipfile.ZipFile(path)
    entries = container.infolist()
    if len(entries) != len(set(e.filename for e in entries)) or sum(e.file_size for e in entries) > 2*LIMIT:
        container.close()
        raise ValueError('压缩包含重复条目或展开大小超过 512 MiB')
    return container


def read_asc(path, carrier):
    """只读八条明确命名的 H 系数链路，不展开用户提供的路径。"""
    names = [f'R0B0S0D_TX{t}_RX{r}_H.asc' for t,r in PORTS]
    with checked_zip(path) as z, tempfile.TemporaryDirectory() as tmp:
        actual = {n for n in z.namelist() if n.lower().endswith('.asc')}
        if actual != set(names):
            raise ValueError('需要且仅需要四发两收的八条 H 系数 ASC，文件放在压缩包根目录')
        common, data = None, []
        for name in names:
            raw = z.read(name)
            local = Path(tmp)/name
            local.write_bytes(raw)
            header = inspect(local)
            if header['taps'] != 24 or header['carrier_hz'] != carrier:
                raise ValueError('ASC 必须与原始数据同载频且每行 24 抽头')
            if common is not None and header != common:
                raise ValueError('八路 ASC 文件头不一致')
            common = header
            data.append(np.loadtxt(io.BytesIO(raw), skiprows=12).reshape(header['cir_count'],24,3))
        manifest = json.loads(z.read('manifest.json')) if 'manifest.json' in z.namelist() else None
    return np.stack(data, axis=1), common, manifest


def prepare_comparison(args):
    from mimo_ota_simulator.channel_comparison import (
        frequency_response, member_taps, compare_responses, power_summary, recover_asc_frames)
    if not (math.isfinite(args.bandwidth_mhz) and 0 < args.bandwidth_mhz <= 10000
            and type(args.points) is int and 3 <= args.points <= 257 and args.points % 2
            and math.isfinite(args.amplitude_floor) and args.amplitude_floor > 0):
        raise ValueError('带宽、奇数频点数或幅度下限无效')
    with checked_zip(args.archive) as outer:
        with checked_zip(io.BytesIO(outer.read('R0B0S0D.mpdb'))) as db:
            source_meta = json.loads(db.read('mpdb.json'))['meta']
    digest, ports, rays = read_downlink(args.archive)
    frames = sorted(set(ports['frame_id'].tolist()))
    keys = list(zip(ports['frame_id'],ports['tx_ant'],ports['rx_ant'],strict=True))
    lids = ports['link_id']
    if (not frames or len(set(lids)) != len(lids) or len(set(keys)) != len(keys)
            or set(keys) != {(f,t,r) for f in frames for t,r in PORTS}
            or not np.isin(rays['link_id'],lids).all()
            or len(set(ports['frequency'])) != 1 or ports['frequency'][0] <= 0
            or (rays['delay'] < 0).any()):
        raise ValueError('需要同载频、每帧唯一的四发两收完整链路和非负时延')
    validate_members_container(args.members, lids)
    with np.load(args.members, allow_pickle=False) as members:
        if str(members['source_sha256']) != digest:
            raise ValueError('成员表与 MPDB 不是同源数据')
        labels = {int(i):members[f'L{i}'].copy() for i in lids}
    for ident, lab in labels.items():
        count = np.count_nonzero((rays['link_id'] == ident) & (abs(rays['h']) > 0))
        if lab.shape != (count,) or (lab < 0).any() or (lab >= 24).any() or not count:
            raise ValueError(f'链路 {ident} 的成员数量或 24 抽头编号不符')
    data, header, manifest = read_asc(args.asc, float(ports['frequency'][0]))
    # 所有已声明的来源均先核对，不能因后续采用数值恢复而跳过明确冲突。
    source = dict(mpdb=digest, members=hashlib.sha256(args.members.read_bytes()).hexdigest())
    if manifest is not None:
        if not isinstance(manifest, dict):
            raise ValueError('ASC 来源清单格式无效')
        if 'source' in manifest:
            declared = manifest['source']
            if not isinstance(declared, dict) or any(
                    key in declared and declared[key] != value for key, value in source.items()):
                raise ValueError('ASC 声明的来源摘要与同源数据不符')
        if 'links' in manifest:
            entries = manifest['links']
            try:
                with checked_zip(args.asc) as z:
                    valid = (isinstance(entries, list) and len(entries) == 8
                        and {(e['tx'], e['rx']) for e in entries} == set(PORTS)
                        and all(e['file'] == f"R0B0S0D_TX{e['tx']}_RX{e['rx']}_H.asc"
                            and ('sha256' not in e or hashlib.sha256(z.read(e['file'])).hexdigest() == e['sha256'])
                            for e in entries))
            except (KeyError, TypeError) as exc:
                raise ValueError('ASC 文件来源清单或摘要无效') from exc
            if not valid:
                raise ValueError('ASC 文件与来源清单摘要不符')
    # 直接逐帧导出必须有来源、完整帧号和明确的占位帧率声明；相同长度不足以证明。
    direct = manifest is not None and manifest.get('rate_source') == 'source_frame_viewer_placeholder'
    if direct:
        if (manifest.get('source') != source or manifest.get('frames') != frames
                or len(data) != len(frames) or manifest.get('mode') != 'conducted'):
            raise ValueError('ASC 源帧清单与同源数据不符')
        with checked_zip(args.asc) as z:
            entries = manifest.get('links', [])
            if (len(entries) != 8 or {(e['tx'],e['rx']) for e in entries} != set(PORTS)
                    or any(e['file'] != f"R0B0S0D_TX{e['tx']}_RX{e['rx']}_H.asc"
                           or hashlib.sha256(z.read(e['file'])).hexdigest() != e['sha256'] for e in entries)):
                raise ValueError('ASC 文件与源帧清单摘要不符')
        recovered = dict(coefficients=data[:,:,:,1]+1j*data[:,:,:,2], delays_s=data[:,:,:,0]*1e-9,
            right_coefficients=data[:,:,:,1]+1j*data[:,:,:,2],right_delays_s=data[:,:,:,0]*1e-9,
            sample_positions=list(range(len(frames))),times_s=[None]*len(frames),
            unmatched_source_frames=[], time_basis='清单声明每行一个源帧；1 Hz 仅为查看占位，非源时间')
    else:
        try:
            recovered = recover_asc_frames(data, rate_hz=header['rate_hz'], source_frame_count=len(frames))
        except ValueError as exc:
            raise ValueError(f'无法唯一恢复源帧：{exc}') from exc
    return dict(digest=digest,ports=ports,rays=rays,frames=frames,labels=labels,recovered=recovered,source_meta=source_meta)


def analyze(args, *, prepared=None):
    from mimo_ota_simulator.channel_comparison import frequency_response, member_taps, compare_responses, power_summary
    data=prepare_comparison(args) if prepared is None else prepared
    digest,ports,rays,frames,labels,recovered,source_meta=(data[key] for key in ('digest','ports','rays','frames','labels','recovered','source_meta'))
    keys=list(zip(ports['frame_id'],ports['tx_ant'],ports['rx_ant'],strict=True))
    lids=ports['link_id']
    offsets = np.arange(-(args.points//2),args.points//2+1)*(args.bandwidth_mhz*1e6/(args.points-1))
    lookup = dict(zip(keys,lids,strict=True))
    output = []
    for index in range(len(recovered['sample_positions'])):
        frame = frames[index]
        raw, grouped, asc, right = [], [], [], []
        powers = {'raw':[], 'members':[], 'asc':[]}
        used = []
        asc_used = []
        for p,(tx,rx) in enumerate(PORTS):
            ident = lookup[frame,tx,rx]
            mask = (rays['link_id'] == ident) & (abs(rays['h']) > 0)
            h, delay = rays['h'][mask], rays['delay'][mask]
            lab = labels[int(ident)]
            if lab.shape != h.shape or (lab >= 24).any():
                raise ValueError(f'链路 {ident} 的成员数量或 24 抽头编号不符')
            taps = member_taps(h, delay, lab, tap_budget=24)
            used.append(int(taps['used_taps']))
            ah, ad = recovered['coefficients'][index,p], recovered['delays_s'][index,p]
            asc_used.append(int(np.count_nonzero(abs(ah)>0)))
            raw.append(frequency_response(h,delay,offsets))
            grouped.append(frequency_response(taps['coefficients'],taps['delays_s'],offsets))
            asc.append(frequency_response(ah,ad,offsets))
            right.append(frequency_response(recovered['right_coefficients'][index,p],recovered['right_delays_s'][index,p],offsets))
            for name,values in [('raw',h),('members',taps['coefficients']),('asc',ah)]:
                powers[name].append(power_summary(values))
        raw, asc, right = map(np.asarray,(raw,asc,right))
        result = compare_responses(raw,{'Lauraycs':asc,'Meta-3D':np.asarray(grouped)},offsets,PHASE_PAIRS,
            amplitude_floor=args.amplitude_floor, time_basis=recovered['time_basis'],
            delay_zero_basis='保留输入绝对时延；未逐端口减最早时延；跨文件时延零点未核验')
        amplitude = float(np.max(abs(raw)))
        center = args.points//2
        denom = abs(raw[:,center])
        result.update(frame=frame, sample_position=float(recovered['sample_positions'][index]),
            asc_time_s=recovered['times_s'][index],used_taps=used,asc_used_taps=asc_used,power=powers,
            left_right_relative_difference=float(np.max(abs(asc-right))/amplitude) if amplitude else None,
            carrier_max_relative_error=float(np.max(abs(asc[:,center]-raw[:,center])/denom)) if (denom>0).all() else None)
        output.append(result)
    coverage = {key:sum(f['coverage'][key] for f in output) for key in ('phase_valid','matrix_valid')}
    coverage.update(phase_total=len(frames)*len(PHASE_PAIRS)*args.points,matrix_total=len(frames)*args.points)
    for kind in ('phase','matrix'):
        coverage[kind+'_fraction'] = coverage[kind+'_valid']/coverage[kind+'_total']
    summary = {}
    for method in ('Lauraycs','Meta-3D'):
        matrix = [x for f in output for x in f['methods'][method]['matrix_nmse'] if x is not None]
        phase = [x for f in output for pair in f['methods'][method]['phase_error_deg'] for x in pair if x is not None]
        summary[method] = {name:float(fn(values)) if values else None for name,fn,values in (
            ('matrix_nmse_median',np.median,matrix),('matrix_nmse_p95',lambda x:np.percentile(x,95),matrix),
            ('phase_error_p95_deg',lambda x:np.percentile(x,95),phase))}
    return dict(schema='mpdb-comparison/1', status='partial' if len(output)<len(frames) else 'unverified',
        formal_verdict=None,alignment_status='unverified',simulated=False,hardware_verified=False,
        source={k:hashlib.sha256(p.read_bytes()).hexdigest() for k,p in [('archive',args.archive),('asc',args.asc),('members',args.members)]},
        mpdb_sha256=digest,carrier_hz=float(ports['frequency'][0]),polarization='H',tap_budget=24,
        polarization_basis=dict(coefficient_column='H',source_modes=source_meta.get('polarization'),
            source_description=source_meta.get('columnDescriptions',{}).get('H'),
            asc_basis='采用文件名 _H.asc；缺少独立的极化绑定证据',status='unverified'),
        offsets_hz=offsets.tolist(),amplitude_floor=args.amplitude_floor,port_order=PORTS,port_pairs=PHASE_PAIRS,
        amplitude_roundoff=recovered.get('amplitude_roundoff'),
        source_frame_count=len(frames),unmatched_source_frames=[frames[i] for i in recovered['unmatched_source_frames']],
        coverage=coverage,summary=summary,frames=output,
        message='仅用于离线辅助分析，时间和时延零点未核验，不作正式判定。复系数不是 dBm；载频相干功率增益与抽头功率和分别记录，无输入参考时绝对接收功率为空。',
        member_row_order='同一 LINK_ID 下按源行顺序筛选 |H| > 0；成员物理身份未核验')


def write_report(report, output):
    output.mkdir()
    (output/'report.json').write_text(json.dumps(report, ensure_ascii=False,allow_nan=False),encoding='utf-8')
    (output/'summary.json').write_text(json.dumps({k:v for k,v in report.items() if k != 'frames'},ensure_ascii=False,allow_nan=False),encoding='utf-8')
    with (output/'points.csv').open('w',newline='',encoding='utf-8') as fp:
        writer=csv.writer(fp)
        writer.writerow(['frame','method','offset_hz','port_a','port_b','matrix_nmse','phase_error_deg','phase_valid','alignment_status','formal_verdict'])
        for f in report['frames']:
            for method,values in f['methods'].items():
                for pi,(a,b) in enumerate(report['port_pairs']):
                    for j,offset in enumerate(report['offsets_hz']):
                        phase=values['phase_error_deg'][pi][j]
                        writer.writerow([f['frame'],method,offset,a,b,values['matrix_nmse'][j],phase,phase is not None,'unverified',''])


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('archive','asc','members','output'):
        parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--bandwidth-mhz',type=float,default=100.)
    parser.add_argument('--points',type=int,default=41)
    parser.add_argument('--amplitude-floor',type=float,default=1e-8)
    args=parser.parse_args()
    write_report(analyze(args),args.output)

if __name__ == '__main__':
    main()
