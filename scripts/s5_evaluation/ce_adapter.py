"""ChannelEgine单帧离线适配；坐标证据由调用者核实，不推断速度方向。"""
from __future__ import annotations

import importlib
import math
from pathlib import Path
import sys

_FIELDS = ('delay_s', 'power_linear', 'aoa_deg', 'aod_deg', 'zoa_deg', 'zod_deg')


def _budget(budget):
    if isinstance(budget, bool) or not isinstance(budget, int) or budget < 1:
        raise ValueError('聚簇预算必须是正整数')


def _module(name, roots, expected):
    """正常包导入，并拒绝同进程中来自另一仓库的同名包。"""
    old = sys.path[:]
    try:
        sys.path[:0] = [str(Path(root).resolve()) for root in roots]
        module = importlib.import_module(name)
        if Path(module.__file__).resolve() != Path(expected).resolve():
            raise ImportError(f'{name} 已从另一仓库加载，请使用独立进程：{module.__file__}')
        return module
    finally:
        sys.path[:] = old


def _load(repo):
    repo = Path(repo).resolve()
    return _module('mimo_ota_simulator.geometric_native_fit', [repo],
                   repo / 'mimo_ota_simulator/geometric_native_fit.py')


def cluster(paths, budget, *, repo, velocity_mps=None, frequency_hz=None,
            coordinate_evidence=None):
    """输入秒、线性功率、度；只输出统计簇，复响应与路径类型保持未知。

    coordinate_evidence 必须非空，表示调用者已确认到达角与接收端速度
    在同一坐标系；仅有LCS标记或世界坐标位置不是此项证据。
    显式给出的真实零速度可以接受，但缺失速度绝不补零。
    完整返回算法输出，由runner保存原始结果后判定是否超预算。
    """
    _budget(budget)
    if not coordinate_evidence or (isinstance(coordinate_evidence, str) and not coordinate_evidence.strip()):
        raise ValueError('缺少到达角与接收端速度处于同一坐标系的证据')
    try:
        velocity = tuple(float(x) for x in velocity_mps)
        frequency = float(frequency_hz)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError('必须提供有效三维速度向量和正频率') from exc
    if len(velocity) != 3 or not all(math.isfinite(x) for x in velocity) or not math.isfinite(frequency) or frequency <= 0:
        raise ValueError('必须提供有效三维速度向量和正频率')
    paths = list(paths)
    converted = []
    for p in paths:
        try:
            row = {key: float(p[key]) for key in _FIELDS}
        except (KeyError, TypeError, ValueError, OverflowError) as exc:
            raise ValueError('CE路径必须包含有限时延、功率及四个角度') from exc
        if not all(math.isfinite(x) for x in row.values()) or row['delay_s'] < 0 or row['power_linear'] <= 0:
            raise ValueError('CE路径时延必须非负、功率必须为正，所有几何字段必须有限')
        converted.append(row)
    if not converted:
        raise ValueError('CE输入路径不能为空')
    native = _load(repo)
    result = native.geometric_native_fit([native.MPC(**p) for p in converted], velocity,
        frequency, native.F64CapabilityProfile(tap_budget=budget))
    raw = result.model_dump()
    clusters = raw['snapshots'][0]['clusters']
    output = []
    for c in clusters:
        # 仅native表示有单个质心；双高斯完整描述留在raw_result，不编造单值。
        doppler = c['doppler_repr']
        output.append({**{k: c[k] for k in _FIELDS},
            'channel_type': None, 'doppler_hz': doppler.get('f_d_centroid_hz')})
    return dict(paths=output, raw_result=raw, input_count=len(paths),
                retained_count=len(paths), filtered_count=0, filtered_power=0.0)
