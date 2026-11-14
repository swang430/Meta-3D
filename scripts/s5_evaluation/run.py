"""S5c只读离线评估；不调用资产执行器或设备，不输出验收判词。"""
from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import math
import subprocess
import sys
import statistics
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


def scalar(value):
    if isinstance(value, list):
        if len(value) != 1:
            raise ValueError('只支持单频标量路径')
        value = value[0]
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError('路径字段必须是有限数值')
    return float(value)


def decode_frames(document):
    """显式采用S5a候选单位，仅作条件性离线研究；不升级来源可信度。"""
    if document.get('schema_version') != 's5-raw-paths/1':
        raise ValueError('不支持的适配文件版本')
    directions = document.get('directions', [])
    if len(directions) != 2 or {d.get('direction') for d in directions} != {'downlink','uplink'}:
        raise ValueError('需要上下行各一份')
    result = []
    try:
        for direction in directions:
            table = direction['raw_tables']['CHANNEL']
            links = direction['raw_tables']['LINK']
            n = len(table['LINK_ID'])
            names = ('DELAY','AOA','AOD','ZOA','ZOD','CHANNEL_TYPE')
            if any(len(table[k]) != n for k in names) or any(len(table['H'][k]) != n for k in ('real','imag')):
                raise ValueError('路径列长度不一致')
            if table.get('DOPPLER') is not None and len(table['DOPPLER']) != n:
                raise ValueError('多普勒列长度不一致')
            seen, identities, previous = set(), set(), None
            frames = direction['frames']
            if not frames or len(frames) != len(links['LINK_ID']):
                raise ValueError('帧和LINK行数不一致')
            for frame in frames:
                time = scalar(frame['time_s'])
                if previous is not None and (time <= previous or not math.isfinite(time-previous)):
                    raise ValueError('时间必须严格递增且间隔有限')
                previous = time
                identity = frame['frame_id']
                if type(identity) is not int or identity in identities:
                    raise ValueError('帧身份重复或无效')
                identities.add(identity)
                link_row = frame['link_row']
                if type(link_row) is not int or not 0 <= link_row < len(links['LINK_ID']):
                    raise ValueError('LINK行号无效')
                if links['LINK_ID'][link_row] != frame['link_id'] or links['FRAME_ID'][link_row] != identity:
                    raise ValueError('帧身份与LINK不一致')
                frequency = scalar(links['FREQUENCY'][link_row])
                if frequency <= 0:
                    raise ValueError('频率必须为正数')
                paths = []
                for row in frame['sample_rows']:
                    if type(row) is not int or not 0 <= row < n or row in seen or table['LINK_ID'][row] != frame['link_id']:
                        raise ValueError('路径行重复、越界或LINK对应错误')
                    seen.add(row)
                    real, imag = (scalar(table['H'][key][row]) for key in ('real','imag'))
                    power = real*real + imag*imag
                    if not math.isfinite(power):
                        raise ValueError('路径功率溢出')
                    path = dict(source_row=row, h_real=real, h_imag=imag, power_linear=power,
                                delay_s=scalar(table['DELAY'][row]),
                                channel_type=scalar(table['CHANNEL_TYPE'][row]),
                                doppler_hz=None if table.get('DOPPLER') is None else scalar(table['DOPPLER'][row]))
                    if path['delay_s'] < 0 or not path['channel_type'].is_integer():
                        raise ValueError('时延或路径类型无效')
                    path['channel_type'] = int(path['channel_type'])
                    for src, dst in [('AOA','aoa_deg'),('AOD','aod_deg'),('ZOA','zoa_deg'),('ZOD','zod_deg')]:
                        path[dst] = scalar(table[src][row])
                    if any(not 0 <= path[k] <= 180 for k in ('zoa_deg','zod_deg')):
                        raise ValueError('天顶角不在候选度制范围')
                    paths.append(path)
                result.append(dict(direction=direction['direction'], frame_id=identity,
                                   time_s=time, frequency_hz=frequency, paths=paths,
                                   angle_coordinate_system=direction['source_document'].get('meta',{}).get('lauraycsPlatform',{}).get('angleCoordinateSystem'),
                                   interpretation='candidate_units_only',
                                   ce_block_reason='缺少已核验的运动端及角度坐标系内速度；本工具不猜测天线旋转'))
            if seen != set(range(n)):
                raise ValueError('部分原始路径未关联到帧')
        down = [(f['frame_id'],f['time_s']) for f in result if f['direction']=='downlink']
        up = [(f['frame_id'],f['time_s']) for f in result if f['direction']=='uplink']
        if down != up:
            raise ValueError('上下行时间或帧身份不一致')
    except (KeyError, TypeError, IndexError) as exc:
        raise ValueError(f'适配数据缺字段或形状无效：{exc}') from exc
    return result


def evaluate(frames, engine, cluster, budgets, offsets):
    if engine not in ('ce','lr') or not budgets or any(type(b) is not int or b <= 0 for b in budgets):
        raise ValueError('算法或簇预算无效')
    if not offsets or any(type(x) not in (int,float) or not math.isfinite(x) for x in offsets):
        raise ValueError('频率偏移网格无效')
    rows = []
    for frame in frames:
        for budget in budgets:
            row = {k:v for k,v in frame.items() if k not in ('paths','ce_block_reason')}
            row.update(engine=engine, budget=budget, input_count=len(frame['paths']))
            if engine == 'ce':
                row.update(status='blocked', reason=frame['ce_block_reason'])
            else:
                try:
                    if not frame['paths']:
                        raise ValueError('原始帧无路径，不能评价')
                    output = cluster(frame['paths'], budget)
                    try:
                        json.dumps(output, allow_nan=False)
                    except (ValueError, TypeError):
                        row['unserializable_output_repr'] = repr(output)
                        raise ValueError('算法输出含非JSON或非有限数据，原始表示已保留')
                    row['output'] = output
                    if not output['paths'] or len(output['paths']) > budget:
                        raise ValueError('算法输出为空或超出预算')
                    from scripts.s5_evaluation.metrics import compare_paths
                    row.update(status='evaluated_conditionally',
                               metrics=compare_paths(frame['paths'], output['paths'], offsets))
                except Exception as exc:
                    # 离线批处理逐项保留失败；错误不变成有效数据。
                    row.update(status='failed', reason=f'{type(exc).__name__}: {exc}')
            rows.append(row)
    return rows


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def summarize(rows):
    """每个方向/预算保留失败分母；统计只针对有定义的数值，不设通过线。"""
    groups = []
    for direction, budget in sorted({(r['direction'],r['budget']) for r in rows}):
        selected = [r for r in rows if r['direction']==direction and r['budget']==budget]
        group = dict(direction=direction, budget=budget, total=len(selected),
                     status_counts=dict(Counter(r['status'] for r in selected)), metrics={})
        for name, keys in [('delay_wasserstein_s',('delay','wasserstein_s')),
                           ('power_ratio',('power','ratio')),
                           ('complex_normalized_mse',('complex_frequency_response','normalized_mse')),
                           ('complex_absolute_rms',('complex_frequency_response','absolute_rms')),
                           *[(k+'_mean_error_deg',('angles',k,'mean_error_deg')) for k in ('aoa_deg','aod_deg','zoa_deg','zod_deg')]]:
            values = []
            for row in selected:
                value = row.get('metrics',{})
                for key in keys:
                    value = value.get(key) if isinstance(value,dict) else None
                if type(value) in (int,float) and math.isfinite(value):
                    values.append((value,row['frame_id']))
            group['metrics'][name] = dict(available=len(values), unavailable=len(selected)-len(values),
                minimum=min(v for v,_ in values) if values else None,
                median=statistics.median(v for v,_ in values) if values else None,
                maximum=max(v for v,_ in values) if values else None,
                maximum_frame_id=max(values)[1] if values else None)
        groups.append(group)
    return groups


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--source-zip', type=Path, required=True)
    parser.add_argument('--repo', type=Path, required=True)
    parser.add_argument('--engine', choices=['ce','lr'], required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--candidate-units', action='store_true', required=True,
                        help='显式采用秒/度/Hz候选解释；不代表原始来源已核验')
    parser.add_argument('--frequency-offsets-hz', type=float, nargs='+', required=True)
    args = parser.parse_args()
    doc = json.loads(args.input.read_text())
    source_hash = sha(args.source_zip)
    if not doc.get('source_files') or doc['source_files'][0]['sha256'] != source_hash:
        raise ValueError('原ZIP校验值与适配文件不一致')
    frames = decode_frames(doc)
    repo = args.repo.resolve()
    commit = subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD'],text=True).strip()
    dirty = subprocess.check_output(['git','-C',str(repo),'status','--porcelain','--untracked-files=no'],text=True)
    if dirty:
        raise ValueError('算法仓库有已跟踪修改，需要先固定可复算版本')
    args.output.mkdir(parents=True, exist_ok=False)
    budgets = [8,16,24]
    module = importlib.import_module('scripts.s5_evaluation.'+args.engine+'_adapter')
    def cluster(paths, budget):
        return module.cluster(paths, budget, repo=repo)
    rows = evaluate(frames, args.engine, cluster, budgets, args.frequency_offsets_hz)
    manifest = dict(schema_version='s5-evaluation/1', engine=args.engine,
                    adapted_sha256=sha(args.input), source_zip_sha256=source_hash,
                    algorithm_commit=commit, repo=str(repo), python=sys.version,
                    budgets=budgets, frequency_offsets_hz=args.frequency_offsets_hz,
                    interpretation='候选秒/度/Hz；不确认原始物理来源',
                    verdict=None, formal_execution_eligible=False,
                    script_hashes={p.name:sha(p) for p in Path(__file__).parent.glob('*.py')})
    summary = dict(total=len(rows), status_counts=dict(Counter(r['status'] for r in rows)),
                   verdict=None, formal_execution_eligible=False,
                   groups=summarize(rows),
                   frames=[{k:v for k,v in r.items() if k!='output'} for r in rows])
    for name,value in [(args.engine+'-clusters.json',rows),('evaluation.json',summary),('manifest.json',manifest)]:
        (args.output/name).write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    print(json.dumps(summary['status_counts'],ensure_ascii=False))
    return 0 if all(r['status']=='evaluated_conditionally' for r in rows) else 2


if __name__ == '__main__':
    raise SystemExit(main())
