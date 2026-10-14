# SPDX-License-Identifier: GPL-3.0-or-later
"""Scene configuration -> camera rig, render geometry and per-camera render times.

Every rig is designed here from a handful of parameters in configs/<scene>.yaml.
"""
import math

import numpy as np
import yaml

from . import camera as cm
from . import distortion as dist

SS = 2  # supersampling factor of the oversized pinhole render


def load_config(path):
    with open(path) as f:
        cfg = yaml.safe_load(f)
    cfg.setdefault("supersample", SS)
    return cfg


def camera_names(cfg):
    n = cfg["rig"]["n"]
    style = cfg.get("names", "four_digit")
    if style == "cam":
        return [f"cam{i:02d}" for i in range(n)]
    return [f"{i:04d}" for i in range(n)]


def _positions(rig, rng):
    """Camera centres and look-at targets for each rig type."""
    n = rig["n"]
    tgt = np.array(rig["target"], float)
    out = []
    if rig["type"] == "arc":
        a0, a1 = rig["azimuth_deg"]
        for i in range(n):
            a = math.radians(a0 + (a1 - a0) * (i / (n - 1) if n > 1 else 0.5))
            a += math.radians(rng.uniform(-1, 1) * rig.get("azimuth_jitter_deg", 0.0))
            r = rig["radius"] + rng.uniform(-1, 1) * rig.get("radius_jitter", 0.0)
            hs = rig["height"]
            h = hs[i % len(hs)] if isinstance(hs, list) else hs
            h += rng.uniform(-1, 1) * rig.get("height_jitter", 0.0)
            C = np.array([tgt[0] + r * math.sin(a), tgt[1] - r * math.cos(a), h])
            out.append((C, tgt + rng.uniform(-1, 1, 3) * rig.get("target_jitter", 0.0)))
    elif rig["type"] == "ring":
        heights = rig["heights"]
        per = n // len(heights)
        for i in range(n):
            ring, k = i % len(heights), i // len(heights)
            a = 2 * math.pi * (k + ring / len(heights)) / per + math.radians(rig.get("azimuth0_deg", 0.0))
            a += math.radians(rng.uniform(-1, 1) * rig.get("azimuth_jitter_deg", 0.0))
            r = rig["radius"] + rng.uniform(-1, 1) * rig.get("radius_jitter", 0.0)
            h = heights[ring] + rng.uniform(-1, 1) * rig.get("height_jitter", 0.0)
            t = np.array(rig["targets"][ring], float)
            C = np.array([t[0] + r * math.sin(a), t[1] - r * math.cos(a), h])
            out.append((C, t + rng.uniform(-1, 1, 3) * rig.get("target_jitter", 0.0)))
    else:
        raise ValueError(rig["type"])
    return out


def build_rig(cfg):
    """Return the list of camera dicts (all values numpy float64)."""
    rng = np.random.default_rng(cfg["rig"].get("seed", 0))
    W, H = cfg["width"], cfg["height"]
    rig, lens = cfg["rig"], cfg["lens"]
    cams = []
    for name, (C, tgt) in zip(camera_names(cfg), _positions(rig, rng)):
        roll = rng.uniform(-1, 1) * rig.get("roll_jitter_deg", 0.0)
        R, t = cm.look_at(C, tgt, roll_deg=roll)
        f = (W / 2) / math.tan(math.radians(lens["hfov_deg"]) / 2)
        f *= 1 + rng.uniform(-1, 1) * lens.get("focal_jitter", 0.0)
        if lens.get("round_focal", True):
            f = round(f, 3)
        off = np.array(lens.get("principal_offset_px", [0.0, 0.0]), float)
        off = off + rng.uniform(-1, 1, 2) * lens.get("principal_jitter_px", 0.0)
        cx, cy = W / 2 + round(off[0], 3), H / 2 + round(off[1], 3)
        base = np.array(lens.get("distortion", []), float)
        jit = np.array(lens.get("distortion_jitter", [0.0] * len(base)), float)
        D = base * (1 + rng.uniform(-1, 1, len(base)) * jit) if len(base) else base
        D = np.round(D, 8)
        cams.append({
            "name": name, "W": W, "H": H,
            "K": cm.K_matrix(f, f, cx, cy),  # continuous convention
            "D": D, "R": R, "t": t,
        })
    return cams


def distorted_sample_grid(W, H, ss):
    """Continuous coordinates of the ss x ss sub-pixel samples of a W x H image."""
    u = (np.arange(W * ss) + 0.5) / ss
    v = (np.arange(H * ss) + 0.5) / ss
    return np.meshgrid(u, v)


def render_geometry(cam, ss=SS, margin_min_frac=0.075, pad_px=3.0):
    """Oversized pinhole render for one camera, and (for distorted lenses) the inverse map.

    Returns dict with margins (output px), big-render Blender params and, if distorted,
    the undistorted continuous pixel coordinates in the big render of each 2x sample.
    """
    W, H, K, D = cam["W"], cam["H"], cam["K"], cam["D"]
    f, cx, cy = K[0, 0], K[0, 2], K[1, 2]
    geo = {}
    if len(D) and np.any(D):
        u, v = distorted_sample_grid(W, H, ss)
        xd, yd = (u - cx) / f, (v - cy) / K[1, 1]
        x, y, res = dist.undistort(xd, yd, D)
        if res > 1e-10:
            raise RuntimeError(f"distortion inverse did not converge: {res}")
        det = dist.min_jacobian_det(x, y, D)
        if det <= 0:
            raise RuntimeError("distortion model folds over inside the image")
        uu, vv = f * x + cx, K[1, 1] * y + cy  # undistorted continuous output coords
        need = (-uu.min(), uu.max() - W, -vv.min(), vv.max() - H)
        geo.update(inverse_residual=res, min_jacobian_det=det, undistorted_extent=need)
    else:
        uu = vv = None
        need = (0.0, 0.0, 0.0, 0.0)
    if uu is None and margin_min_frac == 0:
        mL = mR = mT = mB = 0
    else:
        mx = math.ceil(margin_min_frac * W)
        my = math.ceil(margin_min_frac * H)
        mL, mR = (max(mx, math.ceil(n + pad_px)) for n in need[:2])
        mT, mB = (max(my, math.ceil(n + pad_px)) for n in need[2:])
    Wb, Hb = ss * (W + mL + mR), ss * (H + mT + mB)
    fb, cxb, cyb = ss * f, ss * (cx + mL), ss * (cy + mT)
    geo.update(margins=[mL, mR, mT, mB], ss=ss, big=cm.blender_params(Wb, Hb, fb, cxb, cyb),
               big_K=cm.K_matrix(fb, fb, cxb, cyb), aux=cm.blender_params(W, H, f, cx, cy))
    if uu is not None:
        geo["map_U"] = ss * (uu + mL)
        geo["map_V"] = ss * (vv + mT)
    return geo


def timing(cfg):
    """Blender timeline: scene time t (s) is shown at Blender frame F0 + t * fps."""
    fps = cfg["fps"]
    pre = int(round(cfg.get("preroll_seconds", 1.0) * fps))
    F0 = pre + 1
    return {"fps": fps, "frames": cfg["frames"], "F0": F0, "frame_start": 1,
            "frame_end": F0 + cfg["frames"] + int(math.ceil(0.05 * fps)) + 2}


def sync_offsets(cfg, names):
    s = cfg.get("sync")
    if not s:
        return {n: 0.0 for n in names}
    rng = np.random.default_rng(s["seed"])
    r = s.get("range", 0.03)
    offs = {n: round(float(rng.uniform(-r, r)), 4) for n in names}
    for n, v in s.get("fixed", {}).items():
        offs[n] = float(v)
    return offs


def frame_times(cfg, offsets):
    """Per camera: list of (n, t) with t = n / fps - offset_c."""
    fps = cfg["fps"]
    return {c: [(n, n / fps - o) for n in range(cfg["frames"])] for c, o in offsets.items()}
