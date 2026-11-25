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


def test_replacing_tx_applies_complex_field_only_to_its_links():
    pattern = dict(version="example", carrier_hz=1e9, local_to_global=np.eye(3).tolist(),
                   azimuth_coverage="periodic", zenith_deg=[0,180], azimuth_deg=[0,180],
                   gain_convention="absolute_field", field=[[[[0,2],[0,0]]]*2]*2)
    doc = dict(schema="ray-antenna-patterns/1", source_sha256="example", carrier_hz=1e9,
               basis="global_theta_phi_rx_effective_length_transpose", tx={"1":pattern})
    jones = np.array([[[1.],[0.]],[[1.],[0.]]])
    columns = dict(JONES_T=jones, JONES_R=jones, PHASE=np.ones(2), FADE_L=np.ones(2),
                   POLAR=np.stack([np.eye(2)]*2))
    angles = (np.zeros(2), np.full(2,90.), np.zeros(2), np.full(2,90.))
    ids = np.array([10,11])
    original = np.array([1., np.nextafter(1.,2.)], dtype=complex)
    value, evidence = apply_patterns(None,{"records":{"CHANNEL":columns}},lambda *args: columns[args[-1]],
            doc,"example",1e9,ids,np.array([1,3]),np.zeros(2),ids,original,angles)
    assert value[0] == pytest.approx(2j)
    assert value[1] == original[1]
    assert evidence["replaced_ports"] == {"tx":["1"], "rx":[]}
