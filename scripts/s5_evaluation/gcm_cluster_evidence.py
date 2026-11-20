"""核实本次 S5c 六组交付表与原始链路是否对应。"""
import csv
from collections import Counter
from hashlib import sha256
from pathlib import Path


def audit_exports(directory, hashes, audit):
    if audit['source_files'][0]['sha256'] != hashes['original.zip']:
        raise ValueError('原始压缩包与本批 S5c 评估记录不同')
    results = []
    for direction in audit['directions']:
        name = direction['direction']
        prefix = 'R0B0S0D' if name == 'downlink' else 'R0B0S0U'
        raw_counts = {frame['link_id']: frame['path_count'] for frame in direction['frame_link_identity']}
        for budget in (8, 16, 24):
            tag = '' if budget == 24 else f'_n{budget}'
            tables = {}
            files = {}
            for kind in ('cdl', 'quality'):
                path = Path(directory) / f'{prefix}_cluster_{kind}{tag}.csv'
                digest = sha256(path.read_bytes()).hexdigest()
                if digest != hashes.get(path.name):
                    raise ValueError(f'{path.name} 与该批次校验值不符')
                with path.open(encoding='utf-8-sig', newline='') as handle:
                    reader = csv.DictReader(handle)
                    tables[kind] = list(reader)
                    files[path.name] = dict(sha256=digest, columns=reader.fieldnames)
            counts = Counter(int(row['LINK_ID']) for row in tables['cdl'])
            type_zero = Counter(int(row['LINK_ID']) for row in tables['cdl'] if int(row['CHANNEL_TYPE']) == 0)
            los_candidates = [
                dict(frame_id=f['frame_id'], link_id=f['link_id'], raw_type_zero=f['raw_type_zero'],
                     exported_type_zero=type_zero[f['link_id']], confirmed_gcm_los_id=None)
                for f in direction['frame_link_identity']
            ]
            quality = tables['quality']
            if (counts != {link: budget for link in raw_counts}
                    or Counter(int(row['LINK_ID']) for row in quality) != {link: 1 for link in raw_counts}
                    or any(int(row['N_RAYS']) != raw_counts[int(row['LINK_ID'])]
                           or int(row['N_CLUSTERS']) != budget for row in quality)):
                raise ValueError(f'{name} {budget}簇的链路、原始射线数或簇数不一致')
            results.append(dict(direction=name, budget=budget, files=files, links=len(counts),
                                los_candidates=los_candidates, cluster_rows=sum(counts.values()), ray_membership=None,
                                cross_frame_cluster_identity=None, intra_cluster_angle_spreads=None))
    return results
