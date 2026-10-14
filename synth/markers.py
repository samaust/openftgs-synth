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
        inimg = (z > 0.05) & (uv[:, 0] > -pad) & (uv[:, 0] < k["W"] + pad) & (uv[:, 1] > -pad) & (uv[:, 1] < k["H"] + pad)
        vis = (z > 0.3) & (uv[:, 0] > pad) & (uv[:, 0] < k["W"] - pad) & (uv[:, 1] > pad) & (uv[:, 1] < k["H"] - pad)
        vis &= rad <= m.get("max_radius_px", 12.0)
        # perspective bias: the image of a sphere is an ellipse whose centroid is not the
        # projection of the sphere centre; keep only markers where that offset is negligible
        bias = np.full(len(cand), np.inf)
        idx = np.nonzero(vis)[0]
        for j in idx:
            x = Xc[j]
            A = np.outer(x, x) - (x @ x - r * r) * np.eye(3)
            cen = np.linalg.solve(A[:2, :2], -A[:2, 2])
            bias[j] = k["K"][0, 0] * np.linalg.norm(cen - x[:2] / x[2])
        vis &= bias <= m.get("max_bias_px", 0.02)
        proj.append((uv, vis, inimg))
    chosen = []
    per_cam = [[] for _ in cams]
    # a marker anywhere near an image must be fully usable there (else validation would
    # measure a biased, truncated or oversized blob)
    usable = np.all([(~inimg) | vis for _, vis, inimg in proj], axis=0)
    order = np.argsort(-sum(v.astype(int) for _, v, _ in proj), kind="stable")  # visible in many cameras first
    for j in order:
        if len(chosen) >= m["count"]:
            break
        if not usable[j] or not any(v[j] for _, v, _ in proj):
            continue
        ok = True
        for c, (uv, vis, _) in enumerate(proj):
            if vis[j] and per_cam[c] and np.min(np.linalg.norm(uv[per_cam[c]] - uv[j], axis=1)) < sep:
                ok = False
                break
        if ok:
            chosen.append(j)
            for c, (_, vis, _) in enumerate(proj):
                if vis[j]:
                    per_cam[c].append(j)
    counts = [len(p) for p in per_cam]
    return cand[chosen].tolist(), counts
