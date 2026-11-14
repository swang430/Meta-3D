"""Lauraycs现有CLUSTER_CDL入口适配；不复制或替换聚簇算法。"""
from __future__ import annotations

from collections import Counter
import math
from pathlib import Path

if __package__:
    from .ce_adapter import _budget, _module
else:  # run.py按脚本目录导入。
    from ce_adapter import _budget, _module


def _load(repo):
    repo = Path(repo).resolve()
    native = _module('app.services.channel_analysis.clustering', [repo / 'webService', repo],
                     repo / 'webService/app/services/channel_analysis/clustering.py')
    root = repo / 'HyperRT/PyHyperRT'
    _module('HyperRT.MiRT.MPDB.MPUDF', [root], root / 'HyperRT/MiRT/MPDB/MPUDF.py')
    return native


def cluster(paths, budget, *, repo, velocity_mps=None, frequency_hz=None,
            coordinate_evidence=None):
    """秒转换为原入口delayNs，角度逐项保留；明确include_doppler=False。

    MPUDF.py::_clusterCDL不接收doppler或任意关键字参数，故不传入多普勒。
    输入记录保留原多普勒；输出doppler_hz为None，表示算法未消费此字段。
    完整返回算法输出，由runner保存原始结果后判定是否超预算。
    retained_count为实际参与聚簇的输入路径数，包含预算导致的类型排除。
    无法量化被过滤路径的功率时filtered_power为None，不补零。
    单位解释及其conditional状态由调用者记录，本适配不宣称其已确认。
    """
    _budget(budget)
    native = _load(repo)
    paths = list(paths)
    rows, valid = [], []
    for p in paths:
        delay = native._finite(p.get('delay_s'))
        power = native._finite(p.get('power_linear'))
        angles = [native._finite(p.get(k)) for k in ('aoa_deg', 'zoa_deg', 'aod_deg', 'zod_deg')]
        accepted = delay is not None and power is not None and power > 0 and all(a is not None for a in angles)
        real, imag = native._finite(p.get('h_real')), native._finite(p.get('h_imag'))
        if accepted and (real is None or imag is None):
            raise ValueError('LR有效路径缺少复响应，不能默认零相位')
        if accepted and not math.isclose(real * real + imag * imag, power, rel_tol=1e-8, abs_tol=0):
            raise ValueError('LR复响应与线性功率不一致，无法无损转换')
        kind = native._finite(p.get('channel_type'))
        rows.append(dict(delayNs=delay * 1e9 if delay is not None else None,
            powerLinear=power, phaseRad=math.atan2(imag, real) if accepted else None,
            aoaPhi=angles[0], aoaTheta=angles[1], aodPhi=angles[2], aodTheta=angles[3],
            channelType=int(kind) if kind is not None else None,
            dopplerHz=p.get('doppler_hz')))
        valid.append(accepted)
    # 使用原入口的预算分配函数识别实际被纳入的类型；不另写预算算法。
    allocation = native.allocate_cluster_budget(Counter(
        (r['channelType'] if r['channelType'] is not None else 1)
        for r, ok in zip(rows, valid) if ok), budget)
    retained = [ok and (r['channelType'] if r['channelType'] is not None else 1) in allocation
                for r, ok in zip(rows, valid)]
    filtered_powers = [r['powerLinear'] for r, keep in zip(rows, retained) if not keep]
    filtered_power = (sum(filtered_powers) if all(p is not None for p in filtered_powers) else None)
    raw = native._cluster_cdl_udf_result(rows, n_cluster=budget, include_doppler=False)
    out = []
    if raw is not None:
        for p in raw['paths']:
            out.append(dict(delay_s=p['delayNs'] * 1e-9, power_linear=p['powerLinear'],
                aoa_deg=p['aoaPhi'], aod_deg=p['aodPhi'], zoa_deg=p['aoaTheta'], zod_deg=p['aodTheta'],
                h_real=p['hReal'], h_imag=p['hImag'], channel_type=p['channelType'],
                doppler_hz=None))
    return dict(paths=out, raw_result=raw, input_count=len(paths), retained_count=sum(retained),
                filtered_count=len(paths) - sum(retained), filtered_power=filtered_power)
