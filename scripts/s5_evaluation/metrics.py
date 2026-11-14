"""仅依赖 NumPy 的离线指标；不推断单位、不补相位、不判通过。"""
import json
from numbers import Real

import numpy as np


_ANGLES = ('aoa_deg', 'aod_deg', 'zoa_deg', 'zod_deg')
_FIELDS = ('delay_s', 'power_linear', *_ANGLES)


def _number(value, name):
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, Real):
        raise ValueError(f'{name} 必须是有限实数')
    try:
        value = float(value)
    except (OverflowError, ValueError) as exc:
        raise ValueError(f'{name} 超出可计算范围') from exc
    if not np.isfinite(value):
        raise ValueError(f'{name} 必须是有限实数')
    return value


def _paths(paths, name):
    if not isinstance(paths, list) or not paths:
        raise ValueError(f'{name} 必须是非空路径列表')
    rows, responses = [], []
    for i, path in enumerate(paths):
        if not isinstance(path, dict) or any(k not in path for k in _FIELDS):
            raise ValueError(f'{name}[{i}] 缺少规范路径字段')
        row = [_number(path[k], f'{name}[{i}].{k}') for k in _FIELDS]
        if row[0] < 0 or row[1] < 0:
            raise ValueError('时延和线性功率不能为负数')
        rows.append(row)
        if ('h_real' in path) != ('h_imag' in path):
            raise ValueError('复响应实部与虚部必须同时提供或同时省略')
        responses.append(complex(_number(path['h_real'], 'h_real'),
                                 _number(path['h_imag'], 'h_imag'))
                         if 'h_real' in path else None)
    return np.asarray(rows, dtype=float), responses


def _moments(values, weights, circular=False):
    if weights is None:
        return None, None
    if circular:
        values = (values + 180) % 360 - 180
        radians = np.deg2rad(values)
        vector = np.sum(weights * np.exp(1j * radians))
        # 浮点抵消残差不代表存在可解释的圆均值。
        if abs(vector) <= 1e-12:
            return None, None
        mean = float(np.rad2deg(np.angle(vector)))
        delta = (values - mean + 180) % 360 - 180
    else:
        mean = float(np.sum(weights * values))
        delta = values - mean
    spread = float(np.sqrt(np.sum(weights * delta ** 2)))
    return mean, spread


def _summary(mean, spread, unit):
    return dict(status='available' if mean is not None else 'unavailable',
                **{f'mean_{unit}': mean, f'rms_spread_{unit}': spread})


def _error(a, b, circular=False):
    if a is None or b is None:
        return None
    delta = b - a
    return abs((delta + 180) % 360 - 180) if circular else abs(delta)


def _wasserstein(a, wa, b, wb):
    if wa is None or wb is None:
        return None
    # 一维分布距离为两条归一化累积分布之间面积，重复时延合并到同一位置。
    grid = np.unique(np.concatenate((a, b)))
    def cdf(values, weights):
        order = np.argsort(values)
        cumulative = np.concatenate(([0.0], np.cumsum(weights[order])))
        return cumulative[np.searchsorted(values[order], grid[:-1], side='right')]
    return float(np.sum(np.abs(cdf(a, wa) - cdf(b, wb)) * np.diff(grid)))


def _frequency_response(raw, clustered, rh, ch, offsets):
    result = dict(status='unavailable', reason=None, absolute_rms=None, normalized_mse=None)
    if any(h is None for h in rh + ch):
        result['reason'] = '至少一条路径缺少复响应，不能补造相位'
        return result
    def response(paths, h):
        phase = -2 * np.pi * offsets[:, None] * paths[:, 0]
        return np.exp(1j * phase) @ np.asarray(h, dtype=complex)
    reference = response(raw, rh)
    candidate = response(clustered, ch)
    mse = float(np.mean(np.abs(candidate - reference) ** 2))
    denominator = float(np.mean(np.abs(reference) ** 2))
    result.update(status='available', absolute_rms=float(np.sqrt(mse)),
                  normalized_mse=mse / denominator if denominator > 0 else None,
                  reason=None if denominator > 0 else '原频响全零，归一化误差无定义')
    return result


def compare_paths(raw: list[dict], clustered: list[dict], frequency_offsets_hz: list[float]) -> dict:
    """比较规范路径，返回可用严格 JSON 编码的字典。

    power: raw_total、clustered_total、ratio（输出总功率/原总功率）。
    delay: 两侧 mean_s、rms_spread_s，以及归一化功率分布 wasserstein_s。
    angles: 四角两侧 mean_deg、rms_spread_deg 及绝对均值/扩展误差。
    方位角采用圆均值及最短圆距离的加权均方根扩展，圆合向量长度
    不超过 1e-12 时均值和扩展置空；天顶角采用线性统计，不强制角度范围。
    complex_frequency_response: sum(H*exp(-j*2*pi*df*delay)) 的绝对
    均方根误差和均方误差/原频响平均能量；不从功率构造 H。

    所有加权统计使用 power_linear；复频响仅使用显式 H。两者的物理
    单位与关系由调用方解释，本函数不改写输入。零功率的加权统计、缺相位
    的复频响及退化圆均值以 unavailable/None 表达。显式 H 齐全时始终
    计算绝对误差，仅原频响能量为零时归一化误差置空。
    非法输入或计算溢出抛 ValueError。
    """
    a, rh = _paths(raw, 'raw')
    b, ch = _paths(clustered, 'clustered')
    if not isinstance(frequency_offsets_hz, list) or not frequency_offsets_hz:
        raise ValueError('频率偏移必须为非空列表')
    offsets = np.asarray([_number(f, 'frequency_offsets_hz') for f in frequency_offsets_hz])
    try:
        with np.errstate(over='raise', invalid='raise', divide='raise'):
            ta, tb = float(a[:, 1].sum()), float(b[:, 1].sum())
            wa = a[:, 1] / ta if ta > 0 else None
            wb = b[:, 1] / tb if tb > 0 else None
            ma, sa = _moments(a[:, 0], wa)
            mb, sb = _moments(b[:, 0], wb)
            result = dict(
                power=dict(raw_total=ta, clustered_total=tb,
                           ratio=tb / ta if ta > 0 else None,
                           status='available' if ta > 0 else 'unavailable'),
                delay=dict(status='available' if ta > 0 and tb > 0 else 'unavailable',
                           raw=_summary(ma, sa, 's'), clustered=_summary(mb, sb, 's'),
                           wasserstein_s=_wasserstein(a[:, 0], wa, b[:, 0], wb)),
                angles={})
            for index, key in enumerate(_ANGLES, start=2):
                circular = key in ('aoa_deg', 'aod_deg')
                ma, sa = _moments(a[:, index], wa, circular)
                mb, sb = _moments(b[:, index], wb, circular)
                result['angles'][key] = dict(
                    status='available' if ma is not None and mb is not None else 'unavailable',
                    raw=_summary(ma, sa, 'deg'), clustered=_summary(mb, sb, 'deg'),
                    mean_error_deg=_error(ma, mb, circular), spread_error_deg=_error(sa, sb))
            result['complex_frequency_response'] = _frequency_response(a, b, rh, ch, offsets)
        # 同时拒绝 Python 标量运算产生的无穷，保证不输出非标准 JSON 数值。
        json.dumps(result, allow_nan=False)
        return result
    except (FloatingPointError, OverflowError, ValueError) as exc:
        raise ValueError('输入导致指标超出有限数值计算范围') from exc
