import unittest

import numpy as np

from scripts.imt_conducted_spectrum import describe, reconstruct, spectrum


class SpectrumTest(unittest.TestCase):
    def test_signed_tone_survives_both_anchor_advances(self):
        for doppler in (-17.0, 17.0):
            rate = 128.0
            times = np.array([0.0, 1.0, 2.0])
            grid = np.arange(257) / rate
            groups = [
                (
                    np.exp(2j * np.pi * doppler * np.array([t])),
                    np.zeros(1),
                    np.array([doppler]),
                )
                for t in times
            ]
            actual = reconstruct(groups, times, grid)
            np.testing.assert_allclose(
                actual[:, 1], np.exp(2j * np.pi * doppler * grid), atol=1e-12
            )
            f, p = spectrum(actual[:, 1], rate)
            self.assertEqual(describe(f, p, 20.0)["peak_hz"], doppler)
