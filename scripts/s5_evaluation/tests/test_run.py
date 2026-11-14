import copy
import importlib.util
import sys
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location('s5_run', Path(__file__).parents[1] / 'run.py')
sys.path.insert(0, str(Path(__file__).parents[1]))
run = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(run)


def sample():
    table = dict(LINK_ID=[4, 5], CHANNEL_TYPE=[0, 1],
                 H={'real': [[1.], [0.]], 'imag': [[0.], [2.]]},
                 DELAY=[[1e-9], [2e-9]], AOA=[[0.], [20.]], AOD=[[180.], [200.]],
                 ZOA=[[90.], [90.]], ZOD=[[90.], [90.]], DOPPLER=None)
    direction = dict(direction='downlink', raw_tables={'CHANNEL': table,
                     'LINK': {'LINK_ID': [4, 5], 'FRAME_ID': [10, 11], 'FREQUENCY': [[2.4e9], [2.4e9]]}},
                     frames=[dict(frame_id=10,link_id=4,link_row=0,sample_rows=[0],time_s=0.),
                             dict(frame_id=11,link_id=5,link_row=1,sample_rows=[1],time_s=.1459)],
                     source_document={'meta': {'lauraycsPlatform': {'angleCoordinateSystem': 'LCS'}}})
    up = copy.deepcopy(direction)
    up['direction'] = 'uplink'
    return dict(schema_version='s5-raw-paths/1',directions=[direction,up])


def test_preserve_nonuniform_times_complex_and_missing():
    frames = run.decode_frames(sample())
    assert [f['time_s'] for f in frames] == [0., .1459, 0., .1459]
    assert frames[1]['paths'][0]['h_real'] == 0.
    assert frames[1]['paths'][0]['h_imag'] == 2.
    assert frames[1]['paths'][0]['power_linear'] == 4.
    assert frames[1]['paths'][0]['doppler_hz'] is None


@pytest.mark.parametrize('bad', ['time', 'row', 'nan', 'phase'])
def test_invalid_input_loud(bad):
    value = sample()
    d = value['directions'][0]
    if bad == 'time': d['frames'][1]['time_s'] = 0.
    if bad == 'row': d['frames'][1]['sample_rows'] = [0]
    if bad == 'nan': d['raw_tables']['CHANNEL']['DELAY'][0][0] = float('nan')
    if bad == 'phase': del d['raw_tables']['CHANNEL']['H']['imag']
    with pytest.raises(ValueError): run.decode_frames(value)


def test_ce_blocked_frames_are_not_dropped():
    def forbidden(*a, **k): raise AssertionError('不允许调用未知速度方向的CE')
    rows = run.evaluate(run.decode_frames(sample()), 'ce', forbidden, [8,16,24], [0.])
    assert len(rows) == 12
    assert all(r['status'] == 'blocked' for r in rows)
    assert rows[-1]['time_s'] == .1459


def test_algorithm_failure_remains_visible():
    def failing(*a, **k): raise ValueError('原函数失败')
    rows = run.evaluate(run.decode_frames(sample()), 'lr', failing, [8], [0.])
    assert len(rows) == 4
    assert all(r['status'] == 'failed' and '原函数失败' in r['reason'] for r in rows)


def test_orchestration_known_identity_and_summary_denominator():
    # 这里只测调度；真实算法能力由test_adapters的真实入口验证。
    def identity(paths, budget): return {'paths':paths,'raw_result':{'test_only':True}}
    rows = run.evaluate(run.decode_frames(sample()), 'lr', identity, [8], [0., 1e6])
    assert len(rows) == 4
    assert rows[1]['metrics']['complex_frequency_response']['absolute_rms'] == 0.
    rows[0] = dict(direction='downlink',budget=8,frame_id=10,status='failed')
    groups = run.summarize(rows)
    group = next(g for g in groups if g['direction']=='downlink')
    assert group['total'] == 2
    assert group['metrics']['delay_wasserstein_s']['available'] == 1
    assert group['metrics']['delay_wasserstein_s']['unavailable'] == 1


def test_failed_validation_preserves_algorithm_output():
    def too_many(paths, budget): return {'paths':paths * 9, 'raw_result':{'actual_count':9}}
    rows = run.evaluate(run.decode_frames(sample()), 'lr', too_many, [8], [0.])
    assert all(r['status']=='failed' for r in rows)
    assert rows[0]['output']['raw_result']['actual_count'] == 9
    assert 'metrics' not in rows[0]


def test_nonfinite_algorithm_output_still_has_serializable_failure_record():
    import json
    def invalid(paths, budget): return {'paths':paths,'raw_result':{'bad':float('nan')}}
    rows = run.evaluate(run.decode_frames(sample()), 'lr', invalid, [8], [0.])
    assert rows[0]['status'] == 'failed'
    assert 'nan' in rows[0]['unserializable_output_repr']
    assert 'metrics' not in rows[0]
    json.dumps(rows, allow_nan=False)
