# SPDX-License-Identifier: GPL-3.0-or-later
"""Convention tests that need no renders. Run: .venv/bin/python -m tests.test_conventions"""
import numpy as np
import cv2

from synth import camera as cm
from synth import distortion as dist
from synth import imageops as io

D5 = [-0.12, 0.035, 0.0004, -0.0003, -0.004]
D8 = [0.11, -0.02, 0.0003, -0.0002, 0.001, 0.26, -0.015, 0.002]
D12 = D8 + [0.0012, -0.0002, -0.0009, 0.0001]


def test_distort_matches_opencv():
    rng = np.random.default_rng(0)
    K = cm.K_matrix(500.0, 500.0, 320.0, 240.0)
    for D in (D5, D8, D12):
        X = np.c_[rng.uniform(-0.7, 0.7, (500, 2)), np.ones(500)] * rng.uniform(1, 5, (500, 1))
        uv_cv, _ = cv2.projectPoints(X, np.zeros(3), np.zeros(3), K, np.array(D))
        xd, yd = dist.distort(X[:, 0] / X[:, 2], X[:, 1] / X[:, 2], D)
        uv = np.c_[500 * xd + 320, 500 * yd + 240]
        assert np.abs(uv - uv_cv.reshape(-1, 2)).max() < 1e-9, D


def test_undistort_inverse():
    rng = np.random.default_rng(1)
    for D in (D5, D8, D12):
        xd, yd = rng.uniform(-0.6, 0.6, 10000), rng.uniform(-0.45, 0.45, 10000)
        x, y, res = dist.undistort(xd, yd, D)
        assert res < 1e-12
        cvx = cv2.undistortPointsIter(np.c_[xd, yd].reshape(-1, 1, 2), np.eye(3), np.array(D), None, None,
                                      (cv2.TERM_CRITERIA_COUNT | cv2.TERM_CRITERIA_EPS, 200, 1e-15)).reshape(-1, 2)
        assert np.abs(cvx - np.c_[x, y]).max() < 1e-8


def test_look_at_and_blender_flip():
    R, t = cm.look_at([1.0, -3.0, 1.5], [0.0, 0.0, 0.5])
    assert abs(np.linalg.det(R) - 1) < 1e-12 and np.allclose(R @ R.T, np.eye(3))
    C = cm.center_of(R, t)
    assert np.allclose(C, [1.0, -3.0, 1.5])
    tgt = R @ np.array([0.0, 0.0, 0.5]) + t
    assert tgt[2] > 0 and np.allclose(tgt[:2], 0)  # target straight ahead (+z)
    assert (R @ [0, 0, 2.0] + t)[1] < 0            # world up appears with y < 0 (image up)
    M = cm.blender_matrix_world(R, t)
    # Blender camera looks down its local -z: that must be the OpenCV +z axis in world.
    assert np.allclose(-M[:3, 2], R[2]) and np.allclose(M[:3, 1], -R[1])


def test_pixel_conventions():
    K = cm.K_matrix(100.0, 100.0, 80.0, 60.0)
    assert np.allclose(cm.K_continuous_to_opencv(K)[:2, 2], [79.5, 59.5])
    p = cm.blender_params(160, 120, 100.0, 83.0, 58.0)
    assert np.isclose(160 / 2 - p["shift_x"] * 160, 83.0) and np.isclose(120 / 2 + p["shift_y"] * 160, 58.0)


def test_box_and_bilinear_alignment():
    rng = np.random.default_rng(2)
    big = rng.random((40, 60, 3)).astype(np.float32)
    # sampling the 2x image at its own pixel centres is the identity
    U, V = np.meshgrid(np.arange(60) + 0.5, np.arange(40) + 0.5)
    U[:, 0] += 1e-9; V[0] += 1e-9
    U[:, -1] -= 1e-9; V[-1] -= 1e-9
    assert np.abs(io.BilinearMap(U, V, 60, 40)(big) - big).max() < 1e-5
    assert np.allclose(io.box2(big)[3, 4], big[6:8, 8:10].reshape(-1, 3).mean(0), atol=1e-6)
    v = np.linspace(0, 1, 1001)
    assert np.abs(io.linear_to_srgb(io.srgb_to_linear(v)) - v).max() < 1e-12


if __name__ == "__main__":
    for k, fn in list(globals().items()):
        if k.startswith("test_"):
            fn()
            print("PASS", k)
