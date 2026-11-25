import numpy as np
import pytest
from scripts.conducted_fidelity import compare_export, spectral_matrix


def test_frequency_response_and_correlated_ports(tmp_path):
    tx_ports = [1, 3]
    links = []
    for port in tx_ports:
        name = f"{port}.asc"
        links.append(dict(tx=port, rx=0, file=name))
        (tmp_path / name).write_text("\n" * 12 + "0 1 0\n")
    args = (tmp_path, links, [7], {(7,1,0):10,(7,3,0):11}, np.array([10,11]),
            np.array([1+0j,1+0j]), np.zeros(2), 1e6, np.ones((2,2))*1e-6, True)
    data = compare_export(*args)
    assert data["receiver_band_power_mw"][0]["source_mw"] == pytest.approx(4)
    assert data["phase_p95_deg"] == 0
    (tmp_path / "3.asc").write_text("\n" * 12 + "0 0 1\n")
    data = compare_export(*args)
    assert data["receiver_band_power_mw"][0]["asc_mw"] == pytest.approx(2)
    assert data["worst_complex"]["tx"] == 3
    assert data["phase_p95_deg"] == pytest.approx(90)
    assert data["worst_phase"]["frame"] == 7


def test_invalid_spectral_covariance_is_rejected():
    doc = {"tx_ports":[0,1], "unit":"mW/Hz", "frequency_model":"flat_over_band",
           "real":[[1,2],[2,1]], "imag":[[0,0],[0,0]]}
    with pytest.raises(ValueError, match="半正定"):
        spectral_matrix({"tx_spectral_covariance":doc},{"bandwidth_hz":1e6},[0,1],[0])


def test_band_integral_resolves_ripple_between_display_points():
    from scripts.conducted_fidelity import integrated_power
    paths = [(np.ones(2, dtype=complex), np.array([0,1.6e-6]))]
    assert integrated_power(paths, np.array([[1/20e6]]), 20e6) == pytest.approx(2)
