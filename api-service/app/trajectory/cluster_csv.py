"""校验聚簇文件并恢复复系数。"""
import cmath
import csv
import io
import math
from collections import defaultdict

CLUSTER = 'LINK_ID CHANNEL_TYPE DELAY PL PHASE_DEG AOA ZOA AOD ZOD DOPPLER'.split()
QUALITY = 'LINK_ID N_RAYS N_CLUSTERS OVERALL FORWARD BACKWARD'.split()


def read_groups(path, columns):
    return decode_groups(path.name, path.read_bytes(), columns)


def decode_groups(name, data, columns):
    groups = defaultdict(list)
    with io.StringIO(data.decode("utf-8-sig"), newline="") as source:
        reader = csv.DictReader(source)
        if sorted(reader.fieldnames or []) != sorted(columns):
            raise ValueError(f'{name} 列名不匹配')
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
                raise ValueError(f'{name} 第 {reader.line_num} 行数据无效') from exc
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


