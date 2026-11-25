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


def test_equal_coherent_four_port_spectrum():
    ports = [0,1,2,3]
    matrix = dict(real=np.ones((4,4)).tolist(), imag=np.zeros((4,4)).tolist(),
                  unit="mW/Hz", frequency_model="flat_over_band", tx_ports=ports)
    link = dict(antenna_response="both", coefficient_unit="power_wave_ratio",
                carrier_phase_convention="included_in_coefficient", relative_ray_phase="preserved",
                tx_plane="source", rx_plane="terminal",phase_origin="common",
                delay_origin="same",included_losses="propagation")
    basis = dict(bandwidth_hz=20e6,links={f"{p}/0":link for p in ports})
    q = spectral_matrix({"tx_spectral_covariance":matrix},basis,ports,[0])
    assert np.allclose(q, np.ones((4,4)))
    matrix["real"][0][1] += 5e-13
    matrix["real"][1][0] += 5e-13
    with pytest.raises(ValueError,match="半正定"):
        spectral_matrix({"tx_spectral_covariance":matrix},basis,ports,[0])
