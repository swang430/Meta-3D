"""按方向和链路编号比较原始路径及实际导出的 24 簇。"""
import argparse
import cmath
import csv
import json
import math
from collections import defaultdict
from pathlib import Path

from .metrics import compare_paths
from .run import decode_frames, sha, summarize

OFFSETS = [-5000000, -2500000, 0, 2500000, 5000000]
CLUSTER = 'LINK_ID CHANNEL_TYPE DELAY PL PHASE_DEG AOA ZOA AOD ZOD DOPPLER'.split()
QUALITY = 'LINK_ID N_RAYS N_CLUSTERS OVERALL FORWARD BACKWARD'.split()


def read_groups(path, columns):
    groups = defaultdict(list)
    with path.open(encoding='utf-8-sig', newline='') as source:
        reader = csv.DictReader(source)
        if sorted(reader.fieldnames or []) != sorted(columns):
            raise ValueError(f'{path.name} 列名不匹配')
        for row in reader:
            try:
                if None in row:
                    raise ValueError('多余列')
                values = {k: (int(v) if k in ('LINK_ID', 'CHANNEL_TYPE', 'N_RAYS', 'N_CLUSTERS')
                              else float(v)) for k, v in row.items()}
                # H2PL(0) = +∞；仅这一列的正无穷有明确的零幅度逆像。
                if any(not math.isfinite(v) and not (k == 'PL' and v == math.inf)
                       for k, v in values.items()):
                    raise ValueError('存在非有限数值')
            except (TypeError, ValueError) as exc:
                raise ValueError(f'{path.name} 第 {reader.line_num} 行数据无效') from exc
            groups[values['LINK_ID']].append(values)
    return groups


def cluster_path(row):
    if row['DELAY'] < 0 or any(not 0 <= row[k] <= 180 for k in ('ZOA', 'ZOD')):
        raise ValueError('时延或天顶角超出范围')
    amplitude = 10 ** (-row['PL'] / 20)
    h = cmath.rect(amplitude, math.radians(row['PHASE_DEG']))
    return dict(delay_s=row['DELAY'], aoa_deg=row['AOA'], aod_deg=row['AOD'],
                zoa_deg=row['ZOA'], zod_deg=row['ZOD'], h_real=h.real,
                h_imag=h.imag, power_linear=amplitude ** 2)


def compare_group(link, raw, rows, quality):
    if quality['LINK_ID'] != link or any(row['LINK_ID'] != link for row in rows):
        raise ValueError('链路编号不匹配')
    if len(rows) != 24 or quality['N_CLUSTERS'] != len(rows) or quality['N_RAYS'] != len(raw):
        raise ValueError('原始路径数或 24 簇计数不匹配')
    if len({tuple(row[k] for k in CLUSTER) for row in rows}) != len(rows):
        raise ValueError('簇记录重复，无法区分')
    return compare_paths(raw, [cluster_path(row) for row in rows], OFFSETS)


def evaluate_export(adapted, archive, directory):
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
            path = directory / f'{prefix}_cluster_{suffix}.csv'
            groups.append(read_groups(path, columns))
            hashes[path.name] = sha(path)
        clusters, qualities = groups
        units = direction['candidate_units']
        if any(units.get(k) != 'deg' for k in ('AOA', 'AOD', 'ZOA', 'ZOD')) or units.get('DELAY') != 's':
            raise ValueError(f'{name} 原始时延或角度单位依据不符')
        links = {f['frame_id']: f['link_id'] for f in direction['frames']}
        expected = set(links.values())
        if len(expected) != len(links) or set(clusters) != expected or set(qualities) != expected:
            raise ValueError(f'{name} 链路编号重复或覆盖不一致，簇表差异 {set(clusters)^expected}，质量表差异 {set(qualities)^expected}')
        previous = None
        for frame in (f for f in frames if f['direction'] == name):
            link = links[frame['frame_id']]
            if frame['angle_coordinate_system'] != 'LCS':
                raise ValueError(f'{name} 局部角度坐标未确认')
            if len(qualities[link]) != 1:
                raise ValueError(f'{name} 链路 {link} 质量记录重复')
            quality = qualities[link][0]
            try:
                metrics = compare_group(link, frame['paths'], clusters[link], quality)
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
                                time_s=frame['time_s'], budget=24, status='evaluated_conditionally',
                                zero_amplitude_rows=sum(r['PL'] == math.inf for r in clusters[link]),
                                quality=quality, metrics=metrics, adjacent_change=change))
    return dict(input_sha256=hashes, frequency_offsets_hz=OFFSETS, frames=results,
                summary=summarize(results))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in ('adapted', 'archive', 'directory', 'output'):
        parser.add_argument(arg, type=Path)
    args = parser.parse_args()
    result = evaluate_export(args.adapted, args.archive, args.directory)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False)+'\n',
                           encoding='utf-8')
