import numpy as np
import pytest

from scripts.mpdb_ray_antennas import apply_patterns


def test_missing_polarization_preserves_source_without_claiming_replacement():
    original = np.array([1 + 2j])
    doc = {
        "schema": "ray-antenna-patterns/1",
        "carrier_hz": 3500000000,
        "source_sha256": "sample",
        "basis": "global_theta_phi_rx_effective_length_transpose",
        "tx": {"0": {}},
    }
    desc = {"records": {"CHANNEL": {}}}
    port = np.array([0])
    args = (None, desc, None, doc, "sample", 3500000000, port, port, port, port, original, ())
    value, evidence = apply_patterns(*args)
    np.testing.assert_array_equal(value, original)
    assert evidence["source"] == "source_H"
    assert evidence["antenna_response"] == "unknown"
    assert "POLAR" in evidence["unverified_reason"]
    assert evidence["formal_measurement"] is False

    doc["tx"] = {"2": {}}
    with pytest.raises(ValueError, match="不存在的端口"):
        apply_patterns(*args)
