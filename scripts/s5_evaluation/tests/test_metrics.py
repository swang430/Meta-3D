"""使用解析已知结果验证离线指标，不调用聚簇算法。"""
import json
import math

import pytest

from scripts.s5_evaluation.metrics import compare_paths


def path(delay=0.0, power=1.0, angle=0.0, h=None):
    p = dict(delay_s=delay, power_linear=power, aoa_deg=angle,
             aod_deg=angle, zoa_deg=angle, zod_deg=angle)
    if h is not None:
        p.update(h_real=h.real, h_imag=h.imag)
    return p


def test_known_weighted_distribution():
    result = compare_paths([path(0, 1, 0), path(4, 3, 40)], [path(2, 2, 20)], [0])
    assert result['power'] == dict(raw_total=4.0, clustered_total=2.0, ratio=0.5, status='available')
    d = result['delay']
    assert d['raw']['mean_s'] == pytest.approx(3)
    assert d['raw']['rms_spread_s'] == pytest.approx(math.sqrt(3))
    assert d['clustered']['mean_s'] == 2
    assert d['wasserstein_s'] == pytest.approx(2)
    assert result['angles']['zoa_deg']['raw']['mean_deg'] == pytest.approx(30)
    assert result['angles']['zoa_deg']['raw']['rms_spread_deg'] == pytest.approx(math.sqrt(300))
    assert result['angles']['zod_deg']['mean_error_deg'] == pytest.approx(10)
    json.dumps(result, allow_nan=False)


def test_circular_wrap_and_zenith_are_distinct():
    r = compare_paths([path(angle=179), path(angle=-179)], [path(angle=180)], [0])
    for key in ('aoa_deg', 'aod_deg'):
        a = r['angles'][key]
        assert abs(a['raw']['mean_deg']) == pytest.approx(180)
        assert a['raw']['rms_spread_deg'] == pytest.approx(1)
        assert a['mean_error_deg'] == pytest.approx(0)
        assert a['spread_error_deg'] == pytest.approx(1)
    assert r['angles']['zoa_deg']['raw']['mean_deg'] == pytest.approx(0)
    assert r['angles']['zoa_deg']['raw']['rms_spread_deg'] == pytest.approx(179)
    shifted = compare_paths([path(angle=179)], [path(angle=-179)], [0])
    assert shifted['angles']['aoa_deg']['mean_error_deg'] == pytest.approx(2)


def test_degenerate_circle():
    r = compare_paths([path(angle=0), path(angle=180)], [path()], [0])
    a = r['angles']['aoa_deg']
    assert a['raw']['status'] == 'unavailable'
    assert a['raw']['mean_deg'] is None
    assert a['raw']['rms_spread_deg'] is None
    assert a['mean_error_deg'] is None


def test_complex_known_phase_and_delay():
    # 频点0、0.5处，原响应为2、0；输出响应恒为1。
    r = compare_paths([path(0, h=1+0j), path(1, h=1+0j)], [path(h=1+0j)], [0, .5])
    c = r['complex_frequency_response']
    assert c['status'] == 'available'
    assert c['absolute_rms'] == pytest.approx(1)
    assert c['normalized_mse'] == pytest.approx(.5)
    p = [path(h=1j)]
    c = compare_paths(p, [path(h=-1j)], [0])['complex_frequency_response']
    assert c['absolute_rms'] == pytest.approx(2)
    assert c['normalized_mse'] == pytest.approx(4)


def test_identical_and_cancellation():
    p = [path(h=1+2j), path(2, h=-1j)]
    c = compare_paths(p, p, [-1, 0, 1])['complex_frequency_response']
    assert c['absolute_rms'] == 0
    assert c['normalized_mse'] == 0
    c = compare_paths([path(h=1+0j), path(h=-1+0j)], [path(h=1+0j)], [0, 1])['complex_frequency_response']
    assert c['absolute_rms'] == pytest.approx(1)
    assert c['normalized_mse'] is None


@pytest.mark.parametrize('side', ['raw', 'clustered', 'both'])
def test_zero_power(side):
    p = [path(power=0, h=0j)]
    q = [path(h=1+0j)]
    r = compare_paths(p if side != 'clustered' else q, p if side != 'raw' else q, [0])
    assert r['power']['ratio'] == (0 if side == 'clustered' else None)
    assert r['delay']['status'] == 'unavailable'
    assert r['delay']['wasserstein_s'] is None
    c = r['complex_frequency_response']
    assert c['status'] == 'available'
    assert c['absolute_rms'] == (0 if side == 'both' else 1)
    assert c['normalized_mse'] == (1 if side == 'clustered' else None)
    for a in r['angles'].values():
        assert a['mean_error_deg'] is None
    json.dumps(r, allow_nan=False)


@pytest.mark.parametrize('raw,clustered', [([path()], [path(h=1j)]), ([path(h=1j)], [path()]), ([path(h=1j), path()], [path(h=1j)])])
def test_missing_phase(raw, clustered):
    c = compare_paths(raw, clustered, [0])['complex_frequency_response']
    assert c['status'] == 'unavailable'
    assert c['absolute_rms'] is None
    assert c['normalized_mse'] is None


@pytest.mark.parametrize('field', ['delay_s', 'power_linear', 'aoa_deg', 'aod_deg', 'zoa_deg', 'zod_deg', 'h_real', 'h_imag'])
@pytest.mark.parametrize('value', [float('nan'), float('inf'), -float('inf'), None, '1', True])
def test_invalid_scalar(field, value):
    p = path(h=1j)
    p[field] = value
    with pytest.raises(ValueError):
        compare_paths([p], [path()], [0])


@pytest.mark.parametrize('raw,clustered,grid', [([], [path()], [0]), ([path()], [], [0]), ([path()], [path()], []), (None, [path()], [0]), ([{}], [path()], [0]), ([None], [path()], [0]), ([path(power=-1)], [path()], [0]), ([path(delay=-1)], [path()], [0]), ([dict(path(), h_real=1)], [path()], [0]), ([path()], [dict(path(), h_imag=1)], [0]), ([path()], [path()], [float('nan')]), ([path()], [path()], [float('inf')]), ([path()], [path()], ['0']), ([path()], [path()], [True])])
def test_invalid_structure(raw, clustered, grid):
    with pytest.raises(ValueError):
        compare_paths(raw, clustered, grid)


def test_wasserstein_uses_weights_and_sorts_duplicate_delays():
    # 原分布在0、4处的质量为1/4、3/4；输出在0、2处各1/2。
    # [0,2]面积为2*1/4，[2,4]面积为2*3/4，总距离为2。
    raw = [path(4, 1), path(0, 1), path(4, 2)]
    clustered = [path(2, 1), path(0, 1)]
    r = compare_paths(raw, clustered, [0])
    assert r['delay']['wasserstein_s'] == pytest.approx(2)
    assert compare_paths(raw, raw[::-1], [0])['delay']['wasserstein_s'] == 0


def test_all_zero_state_and_input_unchanged():
    import copy
    p = [path(power=0, h=0j)]
    before = copy.deepcopy(p)
    r = compare_paths(p, p, [0])
    assert p == before
    assert r['power']['status'] == 'unavailable'
    assert r['delay']['raw']['mean_s'] is None
    assert r['complex_frequency_response']['status'] == 'available'
    assert r['complex_frequency_response']['absolute_rms'] == 0
    assert r['complex_frequency_response']['normalized_mse'] is None
    assert 'passed' not in json.dumps(r, allow_nan=False)


def test_overflow_rejected_instead_of_nonfinite_json():
    with pytest.raises(ValueError):
        compare_paths([path(power=1e308), path(power=1e308)], [path()], [0])


def test_zero_power_candidate_preserves_cancellation_error():
    # 原频响在0、500kHz为0、2；零输出仍须报告误差。
    raw = [path(h=1+0j), path(delay=1e-6, h=-1+0j)]
    r = compare_paths(raw, [path(power=0, h=0j)], [0, 500_000])
    c = r['complex_frequency_response']
    assert c['status'] == 'available'
    assert c['absolute_rms'] == pytest.approx(math.sqrt(2))
    assert c['normalized_mse'] == pytest.approx(1)
    assert r['delay']['status'] == 'unavailable'
    for a in r['angles'].values():
        assert a['status'] == 'unavailable'
