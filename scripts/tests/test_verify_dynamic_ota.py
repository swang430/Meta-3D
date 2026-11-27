import numpy as np

from scripts.verify_dynamic_ota import energy, phase_error, propagate, stats


def test_two_rays_with_opposite_doppler_rotate_before_summing():
    paths = np.ones((2, 1, 1, 1), complex)
    frozen, advanced, clustered, feed = propagate(
        (np.array([-1.0, 1.0]), paths, paths, paths[..., 0]), np.array([0.0, 0.25])
    )
    np.testing.assert_allclose(
        energy(advanced, np.array([1.0]))[:, 0], [4.0, 0.0], atol=1e-15
    )
    np.testing.assert_allclose(frozen, 2.0)
    np.testing.assert_allclose(clustered, advanced)
    np.testing.assert_allclose(feed, advanced[..., 0])


def test_relative_phase_ignores_common_rotation_and_excludes_orthogonal_fields():
    a = np.array([[[[1.0, 0.0], [1.0, 0.0]]]], complex)
    b = np.array([[[[1j, 0.0], [0.0, 1.0]]]])
    angle = phase_error(a, b, 1j * a, 1j * b)
    assert stats(angle, np.array([7])) == dict(
        valid=1, excluded=1, p95_abs=0.0, worst=0.0, row=7, point=0, frequency_index=0
    )
    assert np.isclose(phase_error(a, b, a, 1j * b)[0, 0, 0], 90)
