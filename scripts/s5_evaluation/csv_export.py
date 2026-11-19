"""按方向和链路编号比较原始路径及实际导出的聚簇文件。"""
import argparse
import json
import math
from pathlib import Path

from .metrics import compare_paths
from .run import decode_frames, sha, summarize

OFFSETS = [-5000000, -2500000, 0, 2500000, 5000000]
from .export_trajectory import CLUSTER, QUALITY, cluster_path, read_groups


def compare_group(link, raw, rows, quality, budget=24):
    if (quality is not None and quality['LINK_ID'] != link) or any(row['LINK_ID'] != link for row in rows):
        raise ValueError('链路编号不匹配')
    if len(rows) != budget or (quality is not None and (
            quality['N_CLUSTERS'] != len(rows) or quality['N_RAYS'] != len(raw))):
        raise ValueError(f'原始路径数或 {budget} 簇计数不匹配')
    if quality is not None:
        forward, backward, overall = (quality[k] for k in ('FORWARD', 'BACKWARD', 'OVERALL'))
        if not all(0 <= score <= 1 for score in (forward, backward, overall)):
            raise ValueError('质量评分超出 0 到 1 的范围')
        if abs(overall - (forward + backward) / 2) > 1e-7:
            raise ValueError('综合评分与正反向评分平均值不一致')
    if len({tuple(row[k] for k in CLUSTER) for row in rows}) != len(rows):
        raise ValueError('簇记录重复，无法区分')
    return compare_paths(raw, [cluster_path(row) for row in rows], OFFSETS)


def evaluate_export(adapted, archive, directory, budget=24, allow_missing_quality=False):
    if budget not in (8, 16, 24):
        raise ValueError('仅支持 8、16、24 簇')
    tag = '' if budget == 24 else f'_n{budget}'
    document = json.loads(adapted.read_bytes())
    hashes = {p.name: sha(p) for p in (archive, adapted)}
    if hashes[archive.name] != document['source_files'][0]['sha256']:
        raise ValueError('原始压缩包校验值不匹配')
    frames = decode_frames(document)
    results = []
    for direction in document['directions']:
        name = direction['direction']
        prefix = 'R0B0S0' + ('D' if name == 'downlink' else 'U')
        groups = []
        for suffix, columns in [('cdl', CLUSTER), ('quality', QUALITY)]:
            path = directory / f'{prefix}_cluster_{suffix}{tag}.csv'
            if suffix == 'quality' and allow_missing_quality and not path.exists():
                groups.append(None)
                continue
            groups.append(read_groups(path, columns))
            hashes[path.name] = sha(path)
        clusters, qualities = groups
        units = direction['candidate_units']
        if any(units.get(k) != 'deg' for k in ('AOA', 'AOD', 'ZOA', 'ZOD')) or units.get('DELAY') != 's':
            raise ValueError(f'{name} 原始时延或角度单位依据不符')
        links = {f['frame_id']: f['link_id'] for f in direction['frames']}
        expected = set(links.values())
        if len(expected) != len(links) or set(clusters) != expected or (qualities is not None and set(qualities) != expected):
            raise ValueError(f'{name} 链路编号重复或覆盖不一致，簇表差异 {set(clusters)^expected}，质量表差异 {set(qualities or {})^expected}')
        previous = None
        for frame in (f for f in frames if f['direction'] == name):
            link = links[frame['frame_id']]
            if frame['angle_coordinate_system'] != 'LCS':
                raise ValueError(f'{name} 局部角度坐标未确认')
            if qualities is not None and len(qualities[link]) != 1:
                raise ValueError(f'{name} 链路 {link} 质量记录重复')
            quality = qualities[link][0] if qualities is not None else None
            try:
                metrics = compare_group(link, frame['paths'], clusters[link], quality, budget)
            except ValueError as exc:
                raise ValueError(f'{name} 链路 {link}：{exc}') from exc
            powers = metrics['power']
            change = None
            if previous:
                time, raw, clustered = previous
                change = dict(interval_s=frame['time_s']-time,
                              raw_power_change=powers['raw_total']-raw,
                              clustered_power_change=powers['clustered_total']-clustered)
            previous = frame['time_s'], powers['raw_total'], powers['clustered_total']
            results.append(dict(direction=name, link_id=link, frame_id=frame['frame_id'],
                                time_s=frame['time_s'], budget=budget, status='evaluated_conditionally',
                                zero_amplitude_rows=sum(r['PL'] == math.inf for r in clusters[link]),
                                quality=quality, metrics=metrics, adjacent_change=change))
    return dict(input_sha256=hashes, frequency_offsets_hz=OFFSETS, frames=results,
                summary=summarize(results))


def compare_budgets(adapted, archive, directory):
    frames = []
    hashes = {}
    for budget in (8, 16, 24):
        result = evaluate_export(adapted, archive, directory, budget, allow_missing_quality=True)
        hashes.update(result['input_sha256'])
        for frame in result['frames']:
            frame['quality_status'] = 'available' if frame['quality'] is not None else 'unknown'
            frames.append(frame)
    return dict(input_sha256=hashes, frequency_offsets_hz=OFFSETS, frames=frames,
                summary=summarize(frames))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in ('adapted', 'archive', 'directory', 'output'):
        parser.add_argument(arg, type=Path)
    parser.add_argument('--compare-budgets', action='store_true', help='比较 8、16、24 簇，缺少质量表时保留物理误差')
    args = parser.parse_args()
    if args.compare_budgets:
        result = compare_budgets(args.adapted, args.archive, args.directory)
    else:
        result = evaluate_export(args.adapted, args.archive, args.directory)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False)+'\n',
                           encoding='utf-8')
