import pytest
from pathlib import Path
import sys
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))


def test_playback_preserves_dwell_and_nonuniform_times():
    import mpdb_workbench as workbench

    resolve = getattr(workbench, "resolve_playback", None)
    assert resolve is not None
    timing = dict(
        frame_ids=[0, 1, 2], distances_m=[0, 6], source_times_s=None, time_source=None
    )
    result = resolve(timing, None, [2, 3], 20)
    assert result["source_times_s"] == [0, 2, 5]
    assert result["segment_average_speeds_m_s"] == [0, 2]
    assert result["rate_source"] == "operator_supplied"
    with pytest.raises(ValueError):
        resolve(timing, 5, None, 20)
    with pytest.raises(ValueError):
        resolve(timing, None, None, 20)
    timing.update(source_times_s=[17, 19, 20], time_source="MPDB")
    assert resolve(timing, None, None, 20)["source_times_s"] == [0, 2, 3]
    with pytest.raises(ValueError):
        resolve(timing, None, [1, 1], 20)


def test_exact_output_endpoint_survives_float_roundoff_without_extrapolation():
    import mpdb_playback as clocks

    grid = getattr(clocks, "output_grid", None)
    assert grid is not None
    end = sum([0.8, 1.2] * 18 + [0.8])
    samples = grid(end, 100)
    assert len(samples) == 3681
    assert samples[-1] == end
    assert np.all(samples <= end)
    assert grid(36.79999, 100)[-1] == 36.79
