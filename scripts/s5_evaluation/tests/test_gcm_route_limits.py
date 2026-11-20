import pytest

from scripts.s5_evaluation.gcm_route_limits import route_limits


@pytest.mark.parametrize("last, passes", [(0.299, False), (0.73, True), (0.3, True)])
def test_cluster_spacing_preserves_terminal_position(last, passes):
    frames = [0, 1, 2]
    mobile = [(-5, 0, 0), (0, 0, 0), (last, 0, 0)]
    result = route_limits(frames, [(0, 10, 0)] * 3, mobile, 2.4e9)
    assert result["cluster_spacing_ok"] is passes
    assert result["general_editor_short_segments"] == [[1, 2]]
    assert result["last_frame"] == 2
    assert result["position_count"] == 3


@pytest.mark.parametrize('x,axis,radius', [(100000, True, False), (-100000, True, False), (100000.01, False, False), (99999.99, True, True)])
def test_coordinate_closed_and_distance_strict_boundary(x, axis, radius):
    result = route_limits([0], [(x, 0, 0)], [(0, 0, 0)], 2.4e9)
    assert result['axis_limits_ok'] is axis
    assert result['origin_distance_ok'] is radius
    assert result['link_distance_ok'] is radius


def test_length_and_count_do_not_clip():
    result = route_limits(list(range(501)), [(0, 10, 0)] * 501, [(n, 0, 0) for n in range(501)], 2.4e9)
    assert result['position_count'] == 501 and result['last_frame'] == 500
    assert result['preserves_all_positions_by_count'] is False
    assert result['cluster_length_ok'] is True
    result = route_limits([0, 1], [(0, 10, 0)] * 2, [(0, 0, 0), (0.73, 0, 0)], 2.4e9)
    assert result['cluster_length_ok'] is False


def test_extrema_and_failure_locations():
    result = route_limits([36, 37], [(0, 10, 0)] * 2, [(0, 0, 0), (0.299, 0, 0)], 2.4e9)
    assert result['segment_count'] == 1
    assert result['max_segment_m'] == 0.299
    assert result['segments'] == [{'from_frame': 36, 'to_frame': 37, 'distance_m': 0.299}]
    assert result['cluster_short_segments'] == [[36, 37]]
