# SPDX-License-Identifier: GPL-3.0-or-later
"""OpenCV lens distortion (4, 5, 8 or 12 coefficients) and its numerical inverse.

Coefficient order (OpenCV): k1 k2 p1 p2 [k3 [k4 k5 k6 [s1 s2 s3 s4]]].
"""
import numpy as np


def _coeffs(D):
    D = [float(d) for d in np.asarray(D, float).reshape(-1)]
    if len(D) not in (0, 4, 5, 8, 12):
        raise ValueError(f"unsupported number of distortion coefficients: {len(D)}")
    return D + [0.0] * (12 - len(D))


def distort(x, y, D):
    """Normalized undistorted (x, y) -> normalized distorted (xd, yd)."""
    k1, k2, p1, p2, k3, k4, k5, k6, s1, s2, s3, s4 = _coeffs(D)
    r2 = x * x + y * y
    r4 = r2 * r2
    r6 = r4 * r2
    rad = (1 + k1 * r2 + k2 * r4 + k3 * r6) / (1 + k4 * r2 + k5 * r4 + k6 * r6)
    xd = x * rad + 2 * p1 * x * y + p2 * (r2 + 2 * x * x) + s1 * r2 + s2 * r4
    yd = y * rad + p1 * (r2 + 2 * y * y) + 2 * p2 * x * y + s3 * r2 + s4 * r4
    return xd, yd


def jacobian(x, y, D, h=1e-7):
    """Central-difference Jacobian d(xd, yd)/d(x, y); returns (a, b, c, d) = [[a, b], [c, d]]."""
    xp, yp = distort(x + h, y, D)
    xm, ym = distort(x - h, y, D)
    a, c = (xp - xm) / (2 * h), (yp - ym) / (2 * h)
    xp, yp = distort(x, y + h, D)
    xm, ym = distort(x, y - h, D)
    b, d = (xp - xm) / (2 * h), (yp - ym) / (2 * h)
    return a, b, c, d


def undistort(xd, yd, D, tol=1e-13, max_iter=60):
    """Invert distort() by Newton iteration. Returns (x, y, max_residual)."""
    xd = np.asarray(xd, np.float64)
    yd = np.asarray(yd, np.float64)
    if not any(_coeffs(D)):
        return xd.copy(), yd.copy(), 0.0
    x, y = xd.copy(), yd.copy()
    for _ in range(max_iter):
        fx, fy = distort(x, y, D)
        ex, ey = fx - xd, fy - yd
        res = max(np.abs(ex).max(), np.abs(ey).max())
        if res < tol:
            break
        a, b, c, d = jacobian(x, y, D)
        det = a * d - b * c
        x = x - (d * ex - b * ey) / det
        y = y - (-c * ex + a * ey) / det
    fx, fy = distort(x, y, D)
    res = float(max(np.abs(fx - xd).max(), np.abs(fy - yd).max()))
    return x, y, res


def min_jacobian_det(x, y, D):
    a, b, c, d = jacobian(x, y, D)
    return float((a * d - b * c).min())
