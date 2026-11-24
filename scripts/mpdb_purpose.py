"""P2-110 文件适配：冻结连续源帧计划，复用 CE 评估，仅输出辅助报告。"""
import argparse
import csv
import hashlib
import json
from pathlib import Path
if __package__:
    from . import mpdb_budget as budget
else:
    import mpdb_budget as budget


def analyze(args):
    from mimo_ota_simulator.candidate_evaluation import EvaluationPlan, evaluate_candidates
    # 先固定来源和源帧范围，后计算；全帧扫描只提供描述性逐点数据。
    digest,ports,_=budget.read_downlink(args.archive)
    members_digest=hashlib.sha256(args.members.read_bytes()).hexdigest()
    holdout_end=args.holdout_end if args.holdout_end is not None else (36 if getattr(args,'asc',None) is not None else 37)
    plan=EvaluationPlan(source_sha256=digest,members_sha256=members_digest,
        selection_frames=tuple(range(args.selection_start,args.selection_end+1)),
        holdout_frames=tuple(range(args.holdout_start,holdout_end+1)),
        budget_limit=args.tap_budget_max,matrix_p95_limit=args.matrix_nmse_p95_max,
        phase_p95_limit_deg=args.phase_error_p95_max_deg,objective=args.objective,mode=args.mode)
    available=set(map(int,ports['frame_id']))
    if not set(plan.selection_frames+plan.holdout_frames)<=available:
        raise ValueError('选择集或留出集包含不存在的原始源帧')
    asc_report=None
    if getattr(args,'asc',None) is not None:
        if __package__:
            from .mpdb_comparison import analyze as compare_existing
        else:
            from mpdb_comparison import analyze as compare_existing
        asc_report=compare_existing(args)
        common=sorted(available & {f['frame'] for f in asc_report['frames']})
        if not set(plan.selection_frames+plan.holdout_frames)<=set(common):
            raise ValueError('ASC 候选只支持共同可对齐源帧；真实样本请设置留出26–36，37帧单列。')
    else:
        common=sorted(available)
    scan=budget.analyze(args)
    candidates={}
    for strategy in budget.STRATEGIES:
        for taps in budget.BUDGETS:
            name=f'{strategy}-{taps}'
            candidates[name]=dict(strategy=strategy,requested_taps=taps,frames={
                f['frame']:dict(used_taps=f['used_taps'][name],metrics=f['ce_metrics'][name],delta=f['delta'][name])
                for f in scan['frames']})
    known=Path(__file__).resolve().parents[1]/'docs/evidence/imt-three/members.npz'
    known_source=False
    if known.is_file():
        with budget.np.load(known,allow_pickle=False) as container:
            known_source=str(container['source_sha256'])==digest
    provenance=dict(source_sha256=digest,members_sha256=members_digest,
        archive_sha256=scan['source']['archive'],time_basis='同一原始源帧；未声明物理采样时间',
        delay_zero_basis='保留输入绝对时延；物理零点未核验',
        offsets_hz=scan['offsets_hz'],port_pairs=scan['port_pairs'],port_order=scan['port_order'],
        amplitude_floor=scan['amplitude_floor'],carrier_hz=scan['carrier_hz'],
        polarization=scan['polarization'],polarization_basis=scan['polarization_basis'],
        source_frames=scan['frame_ids'],method='P2-109 固定成员；原始端口复系数相干和；CE分拆与频响',
        existing_asc_reference=dict(basis='P2-108既有ASC适用范围；本入口未上传ASC、不重算ASC误差',
            declared_applicable_frames=[f for f in scan['frame_ids'] if f<=36] if known_source else [],unmatched_frames=[f for f in scan['frame_ids'] if f==37] if known_source else scan['frame_ids'],status='unverified',known_sample_source_matched=known_source))
    if asc_report is not None:
        candidates['existing-asc']=dict(strategy='existing_asc',requested_taps=24,frames={
            f['frame']:dict(used_taps=f['asc_used_taps'],metrics=dict(methods=dict(candidate=f['methods']['Lauraycs'])),delta={})
            for f in asc_report['frames']})
        provenance['asc_sha256']=asc_report['source']['asc']
        provenance['existing_asc_reference']=dict(status='unverified',applicable_frames=common,
            unmatched_frames=asc_report['unmatched_source_frames'],
            time_basis=asc_report['frames'][0]['time_basis'],delay_zero_basis=asc_report['frames'][0]['delay_zero_basis'],
            polarization_basis=asc_report['polarization_basis'],amplitude_roundoff=asc_report['amplitude_roundoff'],
            delta_basis='已有ASC没有同策略未拆簇基线，delta不适用；不能将空计数解释成零退化')
    evaluation=evaluate_candidates(plan,candidates,provenance=provenance,manual_candidate=args.manual_candidate)
    return dict(schema='mpdb-purpose/1',status=evaluation['status'],formal_verdict=None,
        alignment_status='unverified',hardware_verified=False,simulated=False,
        evaluation=evaluation,source=asc_report['source'] if asc_report else scan['source'],mpdb_sha256=digest,
        frame_ids=scan['frame_ids'],source_frame_count=scan['source_frame_count'],
        common_frame_ids=common,asc_comparison=asc_report,
        excluded_source_frame_review=dict(frame_id=37,existing_asc=None,
            fixed_member_methods=next((f['methods'] for f in scan['frames'] if f['frame']==37),{}),
            scope='仅描述源帧37；缺已有ASC参考，不参与共同范围选参') if asc_report and 37 not in common and 37 in available else None,
        descriptive_scan=scan,message='全帧扫描仅作描述；选择仅使用选择集。阈值是本次示例约束，不是认证标准。')


def write_report(report,output):
    output.mkdir()
    for name,data in [('report',report),('summary',{k:v for k,v in report.items() if k not in ('descriptive_scan','asc_comparison')})]:
        (output/f'{name}.json').write_text(json.dumps(data,ensure_ascii=False,allow_nan=False),encoding='utf-8')
    # 完整保存109逐点值，并显式标明划分；CSV不参与选参。
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        directory=Path(tmp)/'scan'
        budget.write_report(report['descriptive_scan'],directory)
        selection=set(report['evaluation']['plan']['selection_frames'])
        holdout=set(report['evaluation']['plan']['holdout_frames'])
        with (directory/'points.csv').open(newline='',encoding='utf-8') as src, (output/'points.csv').open('w',newline='',encoding='utf-8') as dst:
            reader=csv.reader(src); writer=csv.writer(dst)
            writer.writerow(next(reader)+['partition','scan_scope','candidate_id'])
            for row in reader:
                frame=int(row[0]); partition='selection' if frame in selection else 'holdout' if frame in holdout else 'outside_plan'
                writer.writerow(row+[partition,'descriptive_only',f'{row[1]}-{row[2]}'])
            if report.get('asc_comparison'):
                for frame in report['asc_comparison']['frames']:
                    values=frame['methods']['Lauraycs']; used=frame['asc_used_taps']; fid=frame['frame']
                    partition='selection' if fid in selection else 'holdout' if fid in holdout else 'outside_plan'
                    for pair_index,(a,b) in enumerate(report['asc_comparison']['port_pairs']):
                        for j,offset in enumerate(report['asc_comparison']['offsets_hz']):
                            phase=values['phase_error_deg'][pair_index][j]
                            writer.writerow([fid,'existing_asc',24,used[a],used[b],offset,a,b,
                                values['matrix_nmse'][j],None,phase,None,'not_applicable',phase is not None,
                                'unverified','',partition,'descriptive_only','existing-asc'])


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('archive','members','output'): p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--asc',type=Path)
    p.add_argument('--bandwidth-mhz',type=float,default=100.)
    p.add_argument('--points',type=int,default=41)
    p.add_argument('--amplitude-floor',type=float,default=1e-8)
    for name,value in [('selection-start',0),('selection-end',25),('holdout-start',26),('holdout-end',None),('tap-budget-max',31)]:
        p.add_argument('--'+name,type=int,default=value)
    p.add_argument('--matrix-nmse-p95-max',type=float,default=1.)
    p.add_argument('--phase-error-p95-max-deg',type=float,default=60.)
    p.add_argument('--objective',choices=['phase','matrix'],default='phase')
    p.add_argument('--mode',choices=['conducted','ota'],default='conducted')
    p.add_argument('--manual-candidate')
    args=p.parse_args();write_report(analyze(args),args.output)
if __name__=='__main__': main()
