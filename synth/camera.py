# SPDX-License-Identifier: GPL-3.0-or-later
"""Camera conventions.

World: right-handed, metres, z up. Cameras: OpenCV axes (x right, y down, z forward),
world-to-camera x_cam = R x + t, camera centre C = -R^T t.

Pixel conventions:
  continuous: the image spans [0, W] x [0, H]; pixel (u, v) is sampled at (u + 0.5, v + 0.5).
  opencv:     integer pixel centres, so c_opencv = c_continuous - 0.5.
All internal pixel maths uses the continuous convention.

Blender (measured with tools/probe_blender_camera.py, re-checked by validate/v1_markers.py):
  sensor_fit HORIZONTAL, sensor_width 36 mm:
    f_px = lens / 36 * W
    cx_continuous = W/2 - shift_x * W
    cy_continuous = H/2 + shift_y * W
  Blender cameras look down -z with y up: R_c2w_blender = R_c2w_opencv @ diag(1, -1, -1).
"""
import numpy as np

FLIP = np.diag([1.0, -1.0, -1.0])
SENSOR_WIDTH_MM = 36.0


def look_at(center, target, up=(0.0, 0.0, 1.0), roll_deg=0.0):
    """World-to-camera (R, t) for a camera at `center` looking at `target`."""
    C = np.asarray(center, float)
    fwd = np.asarray(target, float) - C
    fwd /= np.linalg.norm(fwd)
    right = np.cross(fwd, np.asarray(up, float))
    right /= np.linalg.norm(right)
    down = np.cross(fwd, right)
    R = np.stack([right, down, fwd])
    if roll_deg:
        a = np.radians(roll_deg)
        Rz = np.array([[np.cos(a), -np.sin(a), 0], [np.sin(a), np.cos(a), 0], [0, 0, 1]])
        R = Rz @ R
    t = -R @ C
    return R, t


def center_of(R, t):
    return -R.T @ t


def world_to_camera_4x4(R, t):
    M = np.eye(4)
    M[:3, :3] = R
    M[:3, 3] = t
    return M


def blender_matrix_world(R, t):
    M = np.eye(4)
    M[:3, :3] = R.T @ FLIP
    M[:3, 3] = center_of(R, t)
    return M


def K_matrix(fx, fy, cx, cy):
    return np.array([[fx, 0.0, cx], [0.0, fy, cy], [0.0, 0.0, 1.0]])


def K_continuous_to_opencv(Kc):
    K = np.array(Kc, float).copy()
    K[0, 2] -= 0.5
    K[1, 2] -= 0.5
    return K


def blender_params(W, H, f, cx, cy):
    """Blender camera settings that render a W x H image with focal f and principal point
    (cx, cy) in continuous pixel coordinates (square pixels)."""
    return {
        "resolution": [int(W), int(H)],
        "lens": float(f / W * SENSOR_WIDTH_MM),
        "sensor_width": SENSOR_WIDTH_MM,
        "shift_x": float((W / 2.0 - cx) / W),
        "shift_y": float((cy - H / 2.0) / W),
    }


def rodrigues(R):
    """Rotation matrix -> axis-angle vector (3,), stable near 0 and pi."""
    import cv2
    v, _ = cv2.Rodrigues(np.asarray(R, float))
    return v.reshape(3)
