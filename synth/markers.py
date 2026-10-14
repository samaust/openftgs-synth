# SPDX-License-Identifier: GPL-3.0-or-later
"""Choose validation marker positions that project well separated in every camera."""
import numpy as np


def choose(cams, cfg_markers):
    m = cfg_markers
    rng = np.random.default_rng(m.get("seed", 0))
    box = np.array(m["box"], float)
    cand = rng.uniform(box[:, 0], box[:, 1], (m.get("candidates", 20000), 3))
    r = m["radius"]
    sep = m.get("min_sep_px", 18.0)
    proj = []
    for k in cams:
        Xc = cand @ k["R"].T + k["t"]
        z = Xc[:, 2]
        uv = Xc[:, :2] / np.maximum(z, 1e-9)[:, None] * k["K"][0, 0] + k["K"][:2, 2]
        rad = k["K"][0, 0] * r / np.maximum(z, 1e-9)
        pad = 2 * rad + 8
        vis = (z > 0.3) & (uv[:, 0] > pad) & (uv[:, 0] < k["W"] - pad) & (uv[:, 1] > pad) & (uv[:, 1] < k["H"] - pad)
        vis &= rad <= m.get("max_radius_px", 12.0)
        proj.append((uv, vis))
    chosen = []
    per_cam = [[] for _ in cams]
    order = np.argsort(-sum(v.astype(int) for _, v in proj), kind="stable")  # visible in many cameras first
    for j in order:
        if len(chosen) >= m["count"]:
            break
        if not any(v[j] for _, v in proj):
            continue
        ok = True
        for c, (uv, vis) in enumerate(proj):
            if vis[j] and per_cam[c] and np.min(np.linalg.norm(uv[per_cam[c]] - uv[j], axis=1)) < sep:
                ok = False
                break
        if ok:
            chosen.append(j)
            for c, (_, vis) in enumerate(proj):
                if vis[j]:
                    per_cam[c].append(j)
    counts = [len(p) for p in per_cam]
    return cand[chosen].tolist(), counts
