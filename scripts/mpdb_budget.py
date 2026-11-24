"""P2-109 固定成员预算扫描；CE 计算频响和误差，仅供离线辅助分析。"""
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import numpy as np
if __package__:
    from .mpdb_comparison import PORTS, PHASE_PAIRS, checked_zip
    from .mpdb_port_evidence import read_downlink
    from .mpdb_conducted_project import validate_members_container
else:
    from mpdb_comparison import PORTS, PHASE_PAIRS, checked_zip
    from mpdb_port_evidence import read_downlink
    from mpdb_conducted_project import validate_members_container

BUDGETS=(24,26,31)
STRATEGIES=('independent','shared')


def scan_frame(data,offsets,budgets,floor):
    """仅适配 CE 的字段；分拆、预算、有效掩码及差值均由 CE 决定。"""
    from copy import deepcopy
    from mimo_ota_simulator.tap_budget import compare_tap_budgets
    result=compare_tap_budgets(data,offsets,PHASE_PAIRS,budgets=budgets,
        amplitude_floor=floor,time_basis='同一原始源帧；未声明物理采样时间',
        delay_zero_basis='保留输入绝对时延；物理零点未核验')
    first=result['strategies'][STRATEGIES[0]]['budgets'][str(budgets[0])]
    report=deepcopy(first['metrics'])
    report.update(methods={},used_taps={},ranking={},baseline={},delta={},
        requested_taps={},split_clusters={},ce_metrics={},
        ce_schema=result['schema'],base_cluster_count=result['base_cluster_count'])
    center=int(np.argmin(abs(np.asarray(offsets))))
    errors=[]
    for strategy,values in result['strategies'].items():
        report['ranking'][strategy]=[dict(r,cluster=r['cluster_id'],
            single_tap_squared_error=r['score'],extra_active_taps=r['extra_taps_per_port'])
            for r in values['ranking']]
        for budget,entry in values['budgets'].items():
            name=f'{strategy}-{budget}'
            report['methods'][name]=entry['metrics']['methods']['candidate']
            report['baseline'][strategy]=entry['metrics']['methods']['baseline']
            for field in ('used_taps','requested_taps','split_clusters','delta'):
                report[field][name]=entry[field]
            report['ce_metrics'][name]=entry['metrics']
            errors.append(float(np.max(abs(entry['response'][:,center]-result['reference'][:,center]))))
    # CE 对两策略分别使用共同掩码；顶层字段保留首策略兼容性，完整掩码见 ce_metrics。
    report['carrier_max_absolute_error']=max(errors)
    return report


def analyze(args):
    if not (math.isfinite(args.bandwidth_mhz) and 0<args.bandwidth_mhz<=10000 and type(args.points) is int and 3<=args.points<=257 and args.points%2 and math.isfinite(args.amplitude_floor) and args.amplitude_floor>0):
        raise ValueError('带宽、频点或幅度下限无效')
    with checked_zip(args.archive) as z:
        z.getinfo('R0B0S0D.mpdb')
    digest,ports,rays=read_downlink(args.archive)
    lids=ports['link_id']; frames=sorted(set(ports['frame_id'].tolist()))
    keys=list(zip(ports['frame_id'],ports['tx_ant'],ports['rx_ant'],strict=True))
    if (not frames or len(set(lids))!=len(lids) or len(set(keys))!=len(keys)
        or set(keys)!={(f,t,r) for f in frames for t,r in PORTS}
        or not np.isin(rays['link_id'],lids).all() or len(set(ports['frequency']))!=1
        or ports['frequency'][0]<=0 or (rays['delay']<0).any()):
        raise ValueError('需要完整同载频八路源帧和非负时延')
    validate_members_container(args.members,lids)
    with np.load(args.members,allow_pickle=False) as members:
        if str(members['source_sha256'])!=digest: raise ValueError('成员表与 MPDB 不是同源数据')
        labels={int(i):members[f'L{i}'].copy() for i in lids}
    offsets=np.linspace(-args.bandwidth_mhz*5e5,args.bandwidth_mhz*5e5,args.points)
    lookup=dict(zip(keys,lids,strict=True)); output=[]
    for frame in frames:
        data=[]
        for tx,rx in PORTS:
            lid=lookup[frame,tx,rx]; mask=(rays['link_id']==lid)&(abs(rays['h'])>0)
            h,t=rays['h'][mask],rays['delay'][mask]; lab=labels[int(lid)]
            if not len(h) or lab.shape!=h.shape or lab.dtype.kind not in 'iu' or (lab<0).any() or (lab>=24).any():
                raise ValueError('成员数量或24簇编号无效')
            data.append((h,t,lab))
        output.append(dict(frame=int(frame),**scan_frame(data,offsets,BUDGETS,args.amplitude_floor)))
    summary={}
    for strategy in STRATEGIES:
        for budget in BUDGETS:
            name=f'{strategy}-{budget}'; matrix=[]; phase=[]; changes=[]
            for f in output:
                v=f['methods'][name]
                matrix.extend(x for x in v['matrix_nmse'] if x is not None)
                for row in v['phase_error_deg']:
                    phase.extend(x for x in row if x is not None)
                for row in f['delta'][name]['phase_error_deg']['values']:
                    changes.extend(x for x in row if x is not None)
            summary[name]=dict(tap_budget=budget,used_taps_min=min(min(f['used_taps'][name]) for f in output),used_taps_max=max(max(f['used_taps'][name]) for f in output),matrix_nmse_median=float(np.median(matrix)) if matrix else None,matrix_nmse_p95=float(np.percentile(matrix,95)) if matrix else None,phase_error_p95_deg=float(np.percentile(phase,95)) if phase else None,common_valid=len(changes),**{key:sum(f['delta'][name]['phase_error_deg'][key] for f in output) for key in ('improved','worse','unchanged')})
    return dict(schema='mpdb-budget/1',status='unverified',formal_verdict=None,alignment_status='unverified',simulated=False,hardware_verified=False,source={k:hashlib.sha256(p.read_bytes()).hexdigest() for k,p in [('archive',args.archive),('members',args.members)]},mpdb_sha256=digest,carrier_hz=float(ports['frequency'][0]),polarization='H',polarization_basis='H为原始复系数列名，不证明水平极化',tap_budgets=list(BUDGETS),strategies=list(STRATEGIES),offsets_hz=offsets.tolist(),amplitude_floor=args.amplitude_floor,port_order=PORTS,port_pairs=PHASE_PAIRS,source_frame_count=len(frames),frame_ids=frames,summary=summary,frames=output,message='仅离线辅助分析，不调用设备或HyperRT，不写回工程，不作正式判定。预算是上限；未使用簇不补零计数。')


def write_report(report,output):
    output.mkdir()
    for name,data in [('report',report),('summary',{k:v for k,v in report.items() if k!='frames'})]:
        (output/f'{name}.json').write_text(json.dumps(data,ensure_ascii=False,allow_nan=False),encoding='utf-8')
    with (output/'points.csv').open('w',newline='',encoding='utf-8') as fp:
        w=csv.writer(fp);w.writerow(['frame','strategy','tap_budget','used_taps_a','used_taps_b','offset_hz','port_a','port_b','matrix_nmse','matrix_delta','phase_error_deg','phase_delta_deg','change','phase_valid','alignment_status','formal_verdict'])
        for f in report['frames']:
            for strategy in STRATEGIES:
                for budget in BUDGETS:
                    name=f'{strategy}-{budget}'; v=f['methods'][name]
                    for pi,(a,b) in enumerate(PHASE_PAIRS):
                        for j,offset in enumerate(report['offsets_hz']):
                            phase=v['phase_error_deg'][pi][j]
                            delta=f['delta'][name]['phase_error_deg']['values'][pi][j]
                            matrix=v['matrix_nmse'][j]
                            change='invalid' if delta is None else ('improved' if delta< -1e-7 else 'worse' if delta>1e-7 else 'unchanged')
                            w.writerow([f['frame'],strategy,budget,f['used_taps'][name][a],f['used_taps'][name][b],offset,a,b,matrix,f['delta'][name]['matrix_nmse']['values'][j],phase,delta,change,phase is not None,'unverified',''])


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('archive','members','output'): p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--bandwidth-mhz',type=float,default=100.)
    p.add_argument('--points',type=int,default=41)
    p.add_argument('--amplitude-floor',type=float,default=1e-8)
    args=p.parse_args();write_report(analyze(args),args.output)
if __name__=='__main__': main()
