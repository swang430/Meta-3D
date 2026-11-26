import numpy as np
from scripts.mpdb_ota_spectrum import field_energy


def test_cancelled_carrier_does_not_erase_modulated_power():
    # 两条射线在中心频点相消，时延差 10 ns 使它们在 50 MHz 频偏处同相。
    energy = field_energy(np.zeros((1, 3)), np.zeros(2), np.full(2, 90),
                          np.array([[1, 0], [-1, 0]]), np.array([0, 10e-9]),
                          2e9, np.array([0, 50e6]), np.array([0.75, 0.25]))
    np.testing.assert_allclose(energy, [1.0])


def test_spectrum_must_match_source():
    import io
    import json
    import zipfile
    import pytest
    from scripts.mpdb_ota_spectrum import read_spectrum
    with zipfile.ZipFile(io.BytesIO(), "w") as archive:
        assert read_spectrum(archive, "current") is None
        archive.writestr("ota-spectrum.json", json.dumps({
            "source_sha256": "other", "offsets_hz": [0, 1], "relative_bin_power": [1, 1]
        }))
        with pytest.raises(ValueError, match="摘要不符"):
            read_spectrum(archive, "current")
