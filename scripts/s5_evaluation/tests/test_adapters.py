"""离线适配器：直接调用外部仓库算法，不替换依赖或算法。"""
import ast
import importlib
import inspect
import os
from pathlib import Path

import pytest

from scripts.s5_evaluation import ce_adapter, lr_adapter

CE = Path(os.environ.get('S5_CE_REPO', '/Users/Simon/Tools/ChannelEgine'))
LR = Path(os.environ.get('S5_LR_REPO', '/Users/Simon/Tools/Lauraycs-source'))
EVIDENCE = '合成参考：接收端速度和到达角均在同一右手坐标系，以米、秒、度表示'


def path(**changes):
    result = dict(delay_s=37e-9, power_linear=5., aoa_deg=23., aod_deg=-41.,
                  zoa_deg=67., zod_deg=112., h_real=1., h_imag=2.,
                  channel_type=1, doppler_hz=None)
    return result | changes


@pytest.fixture
def ce_ready():
    try:
        ce_adapter._load(CE)
    except (ImportError, OSError) as exc:
        pytest.skip(f'CE真实入口依赖不可用：{exc}')


@pytest.fixture
def lr_ready():
    # 只将正常加载依赖失败标为跳过；算法执行失败仍会使测试失败。
    try:
        lr_adapter._load(LR)
        importlib.import_module('torch')
        importlib.import_module('HyperRT.MiRT.MPDB.MPUDF')
    except (ImportError, OSError, RuntimeError) as exc:
        pytest.skip(f'LR真实入口依赖不可用：{exc}')
    except NameError as exc:
        if exc.name != 'AbstractCameraF':
            raise
        pytest.skip(f'LR原生绑定导入阻塞：HyperRT/CG.py:22，{exc}')


@pytest.mark.parametrize('kwargs', [dict(), dict(velocity_mps=[1, 0, 0], frequency_hz=3.5e9),
    dict(coordinate_evidence=EVIDENCE, velocity_mps=5, frequency_hz=3.5e9),
    dict(coordinate_evidence=EVIDENCE, velocity_mps=[1, float('nan'), 0], frequency_hz=3.5e9),
    dict(coordinate_evidence=EVIDENCE, velocity_mps=[1, 0, 0], frequency_hz=0)])
def test_ce_rejects_unconfirmed_coordinates(kwargs):
    with pytest.raises(ValueError):
        ce_adapter.cluster([path()], 1, repo=CE, **kwargs)


@pytest.mark.parametrize('adapter', [ce_adapter, lr_adapter])
@pytest.mark.parametrize('budget', [0, -1, 1.5, True])
def test_invalid_budget(adapter, budget):
    with pytest.raises(ValueError):
        adapter.cluster([path()], budget, repo='/missing')


def test_ce_real_single_path(ce_ready):
    result = ce_adapter.cluster([path()], 1, repo=CE, velocity_mps=[5, 0, 0],
                                frequency_hz=3.5e9, coordinate_evidence=EVIDENCE)
    p = result['paths'][0]
    for key in ('delay_s', 'power_linear', 'aoa_deg', 'aod_deg', 'zoa_deg', 'zod_deg'):
        assert p[key] == pytest.approx(path()[key])
    assert 'h_real' not in p and 'h_imag' not in p
    assert result['raw_result']['snapshots'][0]['clusters'][0]['subrays']
    assert result['input_count'] == result['retained_count'] == 1
    assert result['filtered_count'] == result['filtered_power'] == 0


def test_ce_real_budget(ce_ready):
    result = ce_adapter.cluster([path(), path(delay_s=200e-9)], 1, repo=CE,
        velocity_mps=[5, 0, 0], frequency_hz=3.5e9, coordinate_evidence=EVIDENCE)
    assert len(result['paths']) == 1
    assert result['paths'][0]['power_linear'] == pytest.approx(10.)
    assert result['retained_count'] == 2


def test_lr_real_single_path(lr_ready):
    result = lr_adapter.cluster([path()], 1, repo=LR)
    p = result['paths'][0]
    for key in ('delay_s', 'power_linear', 'aoa_deg', 'aod_deg', 'zoa_deg', 'zod_deg', 'h_real', 'h_imag'):
        assert p[key] == pytest.approx(path()[key], rel=1e-5, abs=1e-12)
    assert p['doppler_hz'] is None
    assert result['raw_result']['paths'][0]['delayNs'] == pytest.approx(37.)
    assert result['retained_count'] == 1


def test_lr_real_filtering(lr_ready):
    result = lr_adapter.cluster([path(), path(power_linear=0, h_real=0, h_imag=0),
                                path(aoa_deg=None)], 1, repo=LR)
    assert (result['input_count'], result['retained_count'], result['filtered_count']) == (3, 1, 2)
    assert result['filtered_power'] == pytest.approx(5.)
    assert result['raw_result']['filteredPaths'] == 1


def test_lr_real_type_budget_filtering(lr_ready):
    result = lr_adapter.cluster([path(channel_type=1), path(channel_type=2)], 1, repo=LR)
    assert len(result['paths']) <= 1
    assert result['retained_count'] == 1
    assert result['filtered_count'] == 1
    assert result['filtered_power'] == pytest.approx(5.)


def test_lr_real_doppler(lr_ready):
    result = lr_adapter.cluster([path(doppler_hz=123.5)], 1, repo=LR)
    assert result['paths'][0]['doppler_hz'] is None


def test_lr_native_signature_and_disabled_doppler():
    source = LR / 'HyperRT/PyHyperRT/HyperRT/MiRT/MPDB/MPUDF.py'
    if not source.is_file():
        pytest.skip(f'缺少真实算法源码：{source}')
    tree = ast.parse(source.read_text())
    function = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == '_clusterCDL')
    names = [a.arg for a in function.args.posonlyargs + function.args.args + function.args.kwonlyargs]
    assert 'doppler' not in names
    assert function.args.kwarg is None
    adapter = ast.parse(inspect.getsource(lr_adapter.cluster))
    call = next(n for n in ast.walk(adapter) if isinstance(n, ast.Call)
                and isinstance(n.func, ast.Attribute) and n.func.attr == '_cluster_cdl_udf_result')
    value = next(k.value for k in call.keywords if k.arg == 'include_doppler')
    assert isinstance(value, ast.Constant) and value.value is False


@pytest.mark.parametrize('adapter', [ce_adapter, lr_adapter])
def test_output_conversion_does_not_apply_budget(adapter):
    # 不伪造算法超限结果：静态核验原始结果产生后不再读取预算或切片；
    # 超限结果的保存及失败判定由runner现有行为测试覆盖。
    function = ast.parse(inspect.getsource(adapter.cluster)).body[0]
    index = next(i for i, n in enumerate(function.body) if isinstance(n, ast.Assign)
                 and any(isinstance(t, ast.Name) and t.id == 'raw' for t in n.targets))
    tail = ast.Module(body=function.body[index + 1:], type_ignores=[])
    assert not any(isinstance(n, ast.Name) and n.id == 'budget' for n in ast.walk(tail))
    assert not any(isinstance(n, ast.Slice) for n in ast.walk(tail))


def test_ce_returns_all_native_clusters(ce_ready):
    result = ce_adapter.cluster([path(), path(delay_s=200e-9)], 2, repo=CE,
        velocity_mps=[5, 0, 0], frequency_hz=3.5e9, coordinate_evidence=EVIDENCE)
    raw = result['raw_result']['snapshots'][0]['clusters']
    assert len(result['paths']) == len(raw) == 2
    for output, original in zip(result['paths'], raw):
        for key in ('delay_s', 'power_linear', 'aoa_deg', 'aod_deg', 'zoa_deg', 'zod_deg'):
            assert output[key] == original[key]


@pytest.mark.parametrize('changes', [dict(power_linear=0), dict(delay_s=-1),
    dict(aoa_deg=None), dict(power_linear=float('nan'))])
def test_ce_invalid_path_rejected(changes):
    with pytest.raises(ValueError):
        ce_adapter.cluster([path(**changes)], 1, repo=CE, velocity_mps=[5, 0, 0],
                           frequency_hz=3.5e9, coordinate_evidence=EVIDENCE)
