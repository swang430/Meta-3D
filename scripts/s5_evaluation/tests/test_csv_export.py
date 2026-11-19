import pytest

from scripts.s5_evaluation.csv_export import cluster_path, compare_group


def sample():
    return dict(LINK_ID=7, CHANNEL_TYPE=0, DELAY=2e-7, PL=20, PHASE_DEG=-90,
                AOA=23, AOD=31, ZOA=77, ZOD=80, DOPPLER=-2)


def test_loss_phase_and_units():
    path = cluster_path(sample())
    assert path['h_imag'] == pytest.approx(-0.1)
    assert abs(path['h_real']) < 1e-15
    assert path['power_linear'] == pytest.approx(0.01)
    assert path['delay_s'] == 2e-7
    assert path['aoa_deg'] == 23


@pytest.mark.parametrize('fault', ['link', 'missing', 'unit', 'count', 'duplicate'])
def test_reject_invalid_group(fault):
    rows = [sample() for _ in range(24)]
    for i, row in enumerate(rows):
        row['AOA'] += i
    quality = dict(LINK_ID=7, N_RAYS=1, N_CLUSTERS=24, FORWARD=0, BACKWARD=0, OVERALL=0)
    if fault == 'link':
        rows[0]['LINK_ID'] = 8
    if fault == 'missing':
        rows.pop()
    if fault == 'unit':
        rows[0]['ZOA'] = 181
    if fault == 'count':
        quality['N_RAYS'] = 2
    if fault == 'duplicate':
        rows[0] = rows[1]
    with pytest.raises(ValueError):
        compare_group(7, [cluster_path(sample())], rows, quality)


@pytest.mark.parametrize('loss', ['inf', '-inf', 'nan'])
def test_only_positive_infinite_loss_represents_zero(tmp_path, loss):
    from scripts.s5_evaluation.csv_export import CLUSTER, read_groups
    row = dict(sample(), PL=loss)
    table = tmp_path/'cluster.csv'
    table.write_text(','.join(CLUSTER)+'\n'+','.join(str(row[k]) for k in CLUSTER))
    if loss == 'inf':
        assert cluster_path(read_groups(table, CLUSTER)[7][0])['power_linear'] == 0
    else:
        with pytest.raises(ValueError):
            read_groups(table, CLUSTER)


@pytest.mark.parametrize('budget', [8, 16, 24])
def test_missing_quality_still_compares_physical_paths(budget):
    rows = [dict(sample(), AOA=i) for i in range(budget)]
    paths = [cluster_path(row) for row in rows]
    assert compare_group(7, paths, rows, None, budget)['power']['ratio'] == pytest.approx(1)
    with pytest.raises(ValueError):
        compare_group(7, paths, rows[:-1], None, budget)


@pytest.mark.parametrize('changes', [
    {'FORWARD': -0.1}, {'BACKWARD': 1.1}, {'OVERALL': 0.7},
])
def test_reject_invalid_quality_scores(changes):
    rows = [dict(sample(), AOA=i) for i in range(8)]
    quality = dict(LINK_ID=7, N_RAYS=8, N_CLUSTERS=8, FORWARD=0.2, BACKWARD=0.8, OVERALL=0.5)
    quality.update(changes)
    with pytest.raises(ValueError, match='评分'):
        compare_group(7, [cluster_path(row) for row in rows], rows, quality, 8)
