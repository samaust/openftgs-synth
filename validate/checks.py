# SPDX-License-Identifier: GPL-3.0-or-later
"""Dataset validation checks 1-6 (see README). Each check returns a dict with 'pass' and
numbers for the report."""
import glob
import hashlib
import json
import math
import os
import tarfile
import tempfile

os.environ.setdefault("OPENCV_IO_ENABLE_OPENEXR", "1")

import cv2  # noqa: E402
import numpy as np  # noqa: E402

from synth import encode  # noqa: E402
from synth import imageops as io  # noqa: E402
from synth import package  # noqa: E402
from synth import post  # noqa: E402
from synth.pipeline import DATA  # noqa: E402


def _cams(sc):
    return json.load(open(os.path.join(sc.gt, "cameras.json")))


def _pose(c):
    M = np.array(c["world_to_camera"])
    return M[:3, :3], M[:3, 3]


def _conic_center(Xc, r):
    A = np.outer(Xc, Xc) - (Xc @ Xc - r * r) * np.eye(3)
    return np.linalg.solve(A[:2, :2], -A[:2, 2])


def _centroid(img, uv, rad_px):
    """Intensity-weighted centroid in a window around uv (OpenCV pixel coordinates)."""
    win = int(math.ceil(2 * rad_px + 4))
    u0, v0 = int(round(uv[0])), int(round(uv[1]))
    H, W = img.shape[:2]
    if u0 - win < 0 or v0 - win < 0 or u0 + win >= W or v0 + win >= H:
        return None
    p = img[v0 - win: v0 + win + 1, u0 - win: u0 + win + 1].astype(np.float64).mean(-1)
    s = p.sum()
    if s <= 0:
        return None
    border = np.concatenate([p[0], p[-1], p[:, 0], p[:, -1]])
    if border.max() > 1e-4 * p.max():
        return None  # blob truncated by the window or touching another marker
    ys, xs = np.mgrid[-win: win + 1, -win: win + 1]
    return np.array([u0 + (p * xs).sum() / s, v0 + (p * ys).sum() / s])


# ---------------------------------------------------------------- 1. marker projection

def check_markers(sc, cams=None):
    cj = _cams(sc)
    mk = json.load(open(os.path.join(sc.gt, "markers.json")))["markers"]
    X = np.array([m["position"] for m in mk])
    r = mk[0]["radius"]
    geo = sc.geometry()
    out = {"cameras": {}}
    all_p, all_d, all_c = [], [], []
    for i, c in enumerate(cj["cameras"]):
        if cams is not None and i not in cams:
            continue
        R, t = _pose(c)
        K = np.array(c["K_opencv"])
        D = np.array(c["distortion"])
        Xc = X @ R.T + t
        big = post.read_exr(os.path.join(sc.work, "validation", "markers", c["name"] + ".exr"))
        g = geo[i]
        pin = post.crop_pinhole(big, g["margins"], c["width"], c["height"], sc.ss)
        rad = K[0, 0] * r / Xc[:, 2]
        uv = (Xc[:, :2] / Xc[:, 2:]) * [K[0, 0], K[1, 1]] + K[:2, 2]
        conic = np.array([_conic_center(x, r) for x in Xc]) * [K[0, 0], K[1, 1]] + K[:2, 2]
        dist_img = post.distort_image(big, g["map_path"]) if g.get("map_path") else None
        if dist_img is not None:
            uvd, _ = cv2.projectPoints(X, cv2.Rodrigues(R)[0], t, K, D)
            uvd = uvd.reshape(-1, 2)
        ep, ed, ec = [], [], []
        for j in range(len(X)):
            if Xc[j, 2] <= 0:
                continue
            others = np.delete(uv, j, axis=0)
            if len(others) and np.min(np.linalg.norm(others - uv[j], axis=1)) < 2 * (2 * rad[j] + 4) + 3:
                continue  # not isolated
            cen = _centroid(pin, uv[j], rad[j])
            if cen is None:
                continue
            ep.append(np.linalg.norm(cen - uv[j]))
            ec.append(np.linalg.norm(cen - conic[j]))
            if dist_img is not None:
                cd = _centroid(dist_img, uvd[j], rad[j] * 1.2)
                if cd is not None:
                    ed.append(np.linalg.norm(cd - uvd[j]))
        out["cameras"][c["name"]] = {"n_pinhole": len(ep), "max_pinhole": max(ep, default=None),
                                     "n_distorted": len(ed), "max_distorted": max(ed, default=None)}
        all_p += ep
        all_d += ed
        all_c += ec
    out.update(n_pinhole=len(all_p), max_pinhole_px=max(all_p), mean_pinhole_px=float(np.mean(all_p)),
               max_vs_conic_centre_px=max(all_c), marker_radius_px_range=None)
    if sc.distorted:
        out.update(n_distorted=len(all_d), max_distorted_px=max(all_d), mean_distorted_px=float(np.mean(all_d)))
    ok = out["max_pinhole_px"] < 0.1 and min(v["n_pinhole"] for v in out["cameras"].values()) >= 5
    if sc.distorted:
        ok = ok and out["max_distorted_px"] < 0.1 and min(v["n_distorted"] for v in out["cameras"].values()) >= 5
    out["pass"] = bool(ok)
    return out


# ---------------------------------------------------------------- 2. undistort round trip

def _distorted_video(sc, name_idx, lossless=True):
    for lay in sc.layouts:
        if lay["frames"] == "distorted":
            return sc.video_paths(lay["layout"], name_idx, lossless)
    return None


def _bilinear_floor(ref, shift=0.3):
    """Error of a pure bilinear shift-and-back of an image: the interpolation floor at this
    resolution for any resample-then-undistort round trip."""
    H, W = ref.shape[:2]
    gx, gy = np.meshgrid(np.arange(W, dtype=np.float32), np.arange(H, dtype=np.float32))
    a = cv2.remap(ref, gx + shift, gy + shift, cv2.INTER_LINEAR)
    b = cv2.remap(a, gx - shift, gy - shift, cv2.INTER_LINEAR)
    return np.abs(b.astype(np.int16) - ref.astype(np.int16))[4:-4, 4:-4].reshape(-1)


def check_undistort_frames(sc, cam, frames, border=3):
    """Check 2 on kept distorted PNG frames of one camera (timing runs)."""
    cj = _cams(sc)
    c = cj["cameras"][cam]
    K, D = np.array(c["K_opencv"]), np.array(c["distortion"])
    Kh = K.copy()
    Kh[:2, 2] += 0.5
    W, H = c["width"], c["height"]
    mx, my = cv2.initUndistortRectifyMap(K, D, None, K, (W, H), cv2.CV_32FC1)
    valid = (mx >= border) & (mx <= W - 1 - border) & (my >= border) & (my <= H - 1 - border)
    d, h = [], []
    for n in frames:
        dist_img = cv2.imread(os.path.join(sc.work, "distorted", c["name"], f"{n:06d}.png"))
        ref = cv2.imread(os.path.join(sc.gt, "pinhole", c["name"], f"{n:06d}.png"))
        d.append(np.abs(cv2.undistort(dist_img, K, D).astype(np.int16) - ref.astype(np.int16))[valid].reshape(-1))
        h.append(np.abs(cv2.undistort(dist_img, Kh, D, newCameraMatrix=K).astype(np.int16) - ref.astype(np.int16))[valid].reshape(-1))
    d, h = np.concatenate(d), np.concatenate(h)
    fl = _bilinear_floor(ref)
    return {"mean_abs": float(d.mean()), "median": float(np.median(d)), "p95": float(np.percentile(d, 95)),
            "p99": float(np.percentile(d, 99)), "mean_abs_if_principal_point_off_by_half_pixel": float(h.mean()),
            "bilinear_floor_mean_abs": float(fl.mean())}


def check_undistort(sc, step=None, border=3):
    """cv2.undistort(distorted frame, K, D) vs the pinhole ground truth, border excluded.
    Also reports the same comparison with the principal point moved by +0.5 px (the error a
    wrong half-pixel convention would add) and the bilinear interpolation floor."""
    if not sc.distorted:
        return {"pass": True, "skipped": "no distorted frames"}
    cj = _cams(sc)
    step = step or sc.cfg.get("validation_frame_step", 1)
    diffs, half, floor = [], [], []
    per_cam = {}
    for i, c in enumerate(cj["cameras"]):
        K, D = np.array(c["K_opencv"]), np.array(c["distortion"])
        Kh = K.copy()
        Kh[:2, 2] += 0.5
        W, H = c["width"], c["height"]
        mx, my = cv2.initUndistortRectifyMap(K, D, None, K, (W, H), cv2.CV_32FC1)
        valid = (mx >= border) & (mx <= W - 1 - border) & (my >= border) & (my <= H - 1 - border)
        cd, ch = [], []
        for n, fr in enumerate(encode.iter_frames(_distorted_video(sc, i), W, H)):
            if n % step:
                continue
            bgr = np.ascontiguousarray(fr[..., ::-1])
            ref = cv2.imread(os.path.join(sc.gt, "pinhole", c["name"], f"{n:06d}.png"))
            und = cv2.undistort(bgr, K, D)
            sub = max(1, int(valid.sum()) * 3 // 200_000)  # cap memory: <= ~200k values per frame
            cd.append(np.abs(und.astype(np.int16) - ref.astype(np.int16))[valid].reshape(-1)[::sub])
            undh = cv2.undistort(bgr, Kh, D, newCameraMatrix=K)
            ch.append(np.abs(undh.astype(np.int16) - ref.astype(np.int16))[valid].reshape(-1)[::sub])
            if n == 0:
                floor.append(_bilinear_floor(ref))
        cd, ch = np.concatenate(cd), np.concatenate(ch)
        per_cam[c["name"]] = {"mean": float(cd.mean()), "p99": float(np.percentile(cd, 99)),
                              "mean_halfpixel_wrong": float(ch.mean())}
        diffs.append(cd[:: max(1, cd.size // 2_000_000)])
        half.append(ch[:: max(1, ch.size // 2_000_000)])
    d, h, fl = np.concatenate(diffs), np.concatenate(half), np.concatenate(floor)
    out = {"mean_abs": float(d.mean()), "median": float(np.median(d)), "p95": float(np.percentile(d, 95)),
           "p99": float(np.percentile(d, 99)), "max": int(d.max()), "frac_le_3": float((d <= 3).mean()),
           "mean_abs_if_principal_point_off_by_half_pixel": float(h.mean()),
           "bilinear_floor_mean_abs": float(fl.mean()), "bilinear_floor_median": float(np.median(fl)),
           "border_px_excluded": border, "frame_step": step, "per_camera": per_cam}
    # owner decisions 2026-10-13: floor-relative rule for every scene
    at_floor = (out["median"] <= max(1.0, out["bilinear_floor_median"])
                and out["mean_abs"] <= out["bilinear_floor_mean_abs"])
    aligned = out["mean_abs_if_principal_point_off_by_half_pixel"] >= 1.2 * out["mean_abs"]
    out["criterion"] = ("median <= max(1, floor median), mean <= floor mean (bilinear floor of the same frames), "
                        "and the half-pixel-shifted comparison >= 1.2x worse")
    out["pass"] = bool(aligned and at_floor)
    return out


# ---------------------------------------------------------------- 3. poses_bounds

def check_poses_bounds(sc):
    if not any(l["layout"] == "n3dv" for l in sc.layouts):
        return {"pass": True, "skipped": "no n3dv layout"}
    cj = _cams(sc)
    res = {}
    for root in (DATA, os.path.join(DATA, "lossless")):
        d = os.path.join(root, "n3dv", sc.name)
        pb = np.load(os.path.join(d, "poses_bounds.npy"))
        vids = sorted(os.path.basename(p) for p in glob.glob(os.path.join(d, "cam*.mp4")))
        assert pb.dtype == np.float64 and pb.shape == (len(cj["cameras"]), 17), pb.shape
        assert vids == [f"cam{i:02d}.mp4" for i in range(len(cj["cameras"]))], vids
        err = 0.0
        for row, c in zip(pb, cj["cameras"]):
            M = row[:15].reshape(3, 5)
            Rc2w = np.stack([M[:, 1], M[:, 0], -M[:, 2]], axis=1)
            R = Rc2w.T
            t = -R @ M[:, 3]
            G = np.array(c["world_to_camera"])
            err = max(err, np.abs(R - G[:3, :3]).max(), np.abs(t - G[:3, 3]).max())
            K = np.array(c["K_continuous"])
            assert np.allclose(M[:, 4], [c["height"], c["width"], K[0, 0]], rtol=0, atol=1e-12)
            assert np.isclose(K[0, 2], c["width"] / 2) and np.isclose(K[1, 2], c["height"] / 2)
            assert 0 < row[15] < row[16]
        res[os.path.relpath(d, DATA)] = float(err)
    return {"max_pose_error": max(res.values()), "files": res, "pass": max(res.values()) <= 1e-9}


# ---------------------------------------------------------------- 4. YAML read-back

def _read_yaml_pair(d):
    fi = cv2.FileStorage(os.path.join(d, "intri.yml"), cv2.FILE_STORAGE_READ)
    fe = cv2.FileStorage(os.path.join(d, "extri.yml"), cv2.FILE_STORAGE_READ)
    nn = fi.getNode("names")
    names = [nn.at(i).string() for i in range(nn.size())]
    ne = fe.getNode("names")
    assert [ne.at(i).string() for i in range(ne.size())] == names
    out = {}
    for n in names:
        e = {"K": fi.getNode(f"K_{n}").mat(), "D": fi.getNode(f"D_{n}").mat(),
             "H": fi.getNode(f"H_{n}"), "W": fi.getNode(f"W_{n}"),
             "ccm": fi.getNode(f"ccm_{n}").mat() if not fi.getNode(f"ccm_{n}").empty() else None,
             "R": fe.getNode(f"R_{n}").mat(), "Rot": fe.getNode(f"Rot_{n}").mat(), "T": fe.getNode(f"T_{n}").mat()}
        assert e["H"].isInt() and e["W"].isInt()
        e["H"], e["W"] = int(e["H"].real()), int(e["W"].real())
        out[n] = e
    return names, out


def _yaml_dirs(sc):
    dirs = []
    tmp = None
    for lay in sc.layouts:
        if lay["layout"] == "enerf_outdoor":
            dirs += [os.path.join(DATA, "enerf_outdoor", sc.name), os.path.join(DATA, "lossless", "enerf_outdoor", sc.name)]
        if lay["layout"] == "selfcap":
            tmp = tempfile.mkdtemp(prefix="v4_", dir=sc.work)
            seq = sc.seq()
            for kind in ("release", "calib"):
                with tarfile.open(os.path.join(DATA, "selfcap", f"{seq}-{kind}.tar.gz")) as tf:
                    for m in tf.getmembers():
                        if m.name.endswith((".yml", ".json")):
                            tf.extract(m, tmp, filter="data")
                dirs.append(os.path.join(tmp, f"{seq}-{kind}", "optimized"))
            dirs.append(os.path.join(DATA, "lossless", "selfcap", seq, "optimized"))
    return dirs


def check_yaml(sc):
    dirs = _yaml_dirs(sc)
    if not dirs:
        return {"pass": True, "skipped": "no opencv-yaml files"}
    cj = _cams(sc)
    worst = {"K": 0.0, "D": 0.0, "Rot": 0.0, "T": 0.0, "rodrigues_vs_Rot": 0.0}
    ccm_seen = False
    for d in dirs:
        names, y = _read_yaml_pair(d)
        assert names == [f"{i:04d}" for i in range(len(cj["cameras"]))], names
        for n, c in zip(names, cj["cameras"]):
            e = y[n]
            G = np.array(c["world_to_camera"])
            assert e["K"].shape == (3, 3) and e["D"].shape == (len(c["distortion"]), 1)
            assert e["R"].shape == (3, 1) and e["Rot"].shape == (3, 3) and e["T"].shape == (3, 1)
            assert (e["H"], e["W"]) == (c["height"], c["width"])
            worst["K"] = max(worst["K"], np.abs(e["K"] - np.array(c["K_opencv"])).max())
            worst["D"] = max(worst["D"], np.abs(e["D"].reshape(-1) - np.array(c["distortion"])).max(initial=0))
            worst["Rot"] = max(worst["Rot"], np.abs(e["Rot"] - G[:3, :3]).max())
            worst["T"] = max(worst["T"], np.abs(e["T"].reshape(-1) - G[:3, 3]).max())
            worst["rodrigues_vs_Rot"] = max(worst["rodrigues_vs_Rot"], np.abs(cv2.Rodrigues(e["R"])[0] - e["Rot"]).max())
            if sc.cfg.get("ccm"):
                assert e["ccm"] is not None and np.array_equal(e["ccm"], np.eye(3))
                ccm_seen = True
            else:
                assert e["ccm"] is None
    ok = worst["K"] == 0 and worst["D"] == 0 and worst["Rot"] == 0 and worst["T"] == 0 and worst["rodrigues_vs_Rot"] <= 1e-9
    return {"files": [os.path.relpath(d, DATA) if d.startswith(DATA) else "archive:" + os.path.basename(os.path.dirname(d))
                      for d in dirs], "max_abs_diff": {k: float(v) for k, v in worst.items()},
            "ccm_identity_checked": ccm_seen, "pass": bool(ok)}


# ---------------------------------------------------------------- 5. timing / sync

def _solve_time(K, R, t, p0, v, uv, t_init):
    def proj(tt):
        x = R @ (np.array(p0) + np.array(v) * tt) + t
        return K[:2, :2] @ (x[:2] / x[2]) + K[:2, 2]
    tt = t_init
    for _ in range(20):
        h = 1e-4
        d = (proj(tt + h) - proj(tt - h)) / (2 * h)
        e = proj(tt) - uv
        tt -= (d @ e) / (d @ d)
    return tt, float(np.linalg.norm(d)), float(np.linalg.norm(proj(tt) - uv))


def check_sync(sc):
    cj = _cams(sc)
    fps = cj["fps"]
    out = {}
    # (a) cameras.json frame times follow t = n/fps - offset
    e_t = max(abs(f["t"] - (f["n"] / fps - c["sync_offset"])) for c in cj["cameras"] for f in c["frames"])
    out["frame_time_formula_max_err"] = e_t
    # (b) sync.json matches cameras.json (selfcap only)
    if any(l["layout"] == "selfcap" for l in sc.layouts):
        tmp = tempfile.mkdtemp(prefix="v5_", dir=sc.work)
        seq = sc.seq()
        errs = []
        for kind in ("release", "calib"):
            with tarfile.open(os.path.join(DATA, "selfcap", f"{seq}-{kind}.tar.gz")) as tf:
                tf.extract(f"{seq}-{kind}/optimized/sync.json", tmp, filter="data")
            s = json.load(open(os.path.join(tmp, f"{seq}-{kind}", "optimized", "sync.json")))
            assert sorted(s) == [f"{i:04d}" for i in range(len(cj["cameras"]))]
            for i, c in enumerate(cj["cameras"]):
                errs.append(abs(s[f"{i:04d}"] - c["sync_offset"]))
                assert -0.03 <= s[f"{i:04d}"] <= 0.03
        out["sync_json_vs_cameras_json_max_err"] = max(errs)
        out["offset_range"] = [min(c["sync_offset"] for c in cj["cameras"]), max(c["sync_offset"] for c in cj["cameras"])]
    # (c) every Blender job was rendered at Blender frame F0 + t*fps with the camera's own t
    tmap = {(c["name"], f["n"]): f["t"] for c in cj["cameras"] for f in c["frames"]}
    F0 = sc.timing["F0"]
    e_job, nj = 0.0, 0
    for p in glob.glob(os.path.join(sc.work, "jobs_*.json")):
        for j in json.load(open(p))["jobs"]:
            if j["kind"] in ("rgb", "aux", "clock"):
                tt = tmap[(j["cam_name"], j["n"])]
                e_job = max(e_job, abs(j["time"] - tt), abs(j["frame"] - (F0 + tt * fps)))
                nj += 1
    out["render_jobs_checked"] = nj
    out["render_job_time_max_err"] = e_job
    # (d) image evidence: the clock marker's position gives back the render time
    mk = json.load(open(os.path.join(sc.gt, "markers.json")))["clock_marker"]
    geo = sc.geometry()
    worst_rel, worst_ms, n_clock, sep = 0.0, 0.0, 0, []
    for i, c in enumerate(cj["cameras"]):
        R, t = _pose(c)
        K = np.array(c["K_opencv"])
        for p in sorted(glob.glob(os.path.join(sc.work, "validation", "clock", c["name"], "*.exr"))):
            n = int(os.path.basename(p)[:6])
            big = post.read_exr(p)
            pin = post.crop_pinhole(big, geo[i]["margins"], c["width"], c["height"], sc.ss)
            texp = tmap[(c["name"], n)]
            x = R @ (np.array(mk["p0"]) + np.array(mk["velocity"]) * texp) + t
            uv = K[:2, :2] @ (x[:2] / x[2]) + K[:2, 2]
            cen = _centroid(pin, uv, K[0, 0] * mk["radius"] / x[2])
            if cen is None:
                continue
            that, speed, _ = _solve_time(K, R, t, mk["p0"], mk["velocity"], cen, texp)
            tol = 0.1 / speed  # 0.1 px of image motion
            worst_rel = max(worst_rel, abs(that - texp) / tol)
            worst_ms = max(worst_ms, abs(that - texp) * 1e3)
            if abs(c["sync_offset"]) > 0:
                sep.append(abs(c["sync_offset"]) / tol)
            n_clock += 1
    out.update(clock_frames_checked=n_clock, clock_time_max_err_ms=worst_ms,
               clock_err_over_tolerance=worst_rel,
               min_offset_over_tolerance=min(sep) if sep else None)
    out["pass"] = bool(e_t <= 1e-12 and out.get("sync_json_vs_cameras_json_max_err", 0) == 0 and nj > 0
                       and e_job <= 1e-9 and n_clock >= len(cj["cameras"]) and worst_rel < 1.0)
    return out


# ---------------------------------------------------------------- 6. archives and checksums

def check_archives(sc):
    if not any(l["layout"] == "selfcap" for l in sc.layouts):
        return {"pass": True, "skipped": "no archives"}
    rel, cal = package.selfcap_members(sc)
    seq = sc.seq()
    res = {}
    for kind, exp in (("release", rel), ("calib", cal)):
        with tarfile.open(os.path.join(DATA, "selfcap", f"{seq}-{kind}.tar.gz")) as tf:
            names = sorted(m.name for m in tf.getmembers())
            types_ok = all(m.isfile() for m in tf.getmembers())
        res[f"{seq}-{kind}.tar.gz"] = {"members": len(names), "exact": names == sorted(exp), "files_only": types_ok}
    return {"archives": res, "pass": all(v["exact"] and v["files_only"] for v in res.values())}


def check_sha256sums(root=DATA):
    p = os.path.join(root, "SHA256SUMS")
    listed = {}
    for line in open(p):
        h, f = line.rstrip("\n").split("  ", 1)
        listed[f] = h
    files = set()
    for d, _, fs in os.walk(root):
        for f in fs:
            rp = os.path.relpath(os.path.join(d, f), root)
            if rp != "SHA256SUMS":
                files.add(rp)
    bad = []
    for f in sorted(files & set(listed)):
        h = hashlib.sha256()
        with open(os.path.join(root, f), "rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 22), b""):
                h.update(chunk)
        if h.hexdigest() != listed[f]:
            bad.append(f)
    out = {"files": len(files), "listed": len(listed), "missing": sorted(files - set(listed))[:20],
           "extra": sorted(set(listed) - files)[:20], "mismatched": bad[:20]}
    out["pass"] = not out["missing"] and not out["extra"] and not bad
    return out


# ---------------------------------------------------------------- videos

def check_videos(sc):
    """ffprobe every video, including the ones inside the selfcap release archive (extracted
    to a temporary directory and compared byte-for-byte with the staged copies)."""
    paths = []
    tmp = None
    for lay in sc.layouts:
        for i in range(len(sc.cams)):
            for ll in (False, True):
                p = sc.video_paths(lay["layout"], i, ll)
                if lay["layout"] == "selfcap" and not ll:
                    if tmp is None:
                        tmp = tempfile.mkdtemp(prefix="vid_", dir=sc.work)
                        with tarfile.open(os.path.join(DATA, "selfcap", f"{sc.seq()}-release.tar.gz")) as tf:
                            tf.extractall(tmp, members=[m for m in tf.getmembers() if m.name.endswith(".mp4")],
                                          filter="data")
                    q = os.path.join(tmp, f"{sc.seq()}-release", "videos", os.path.basename(p))
                    if open(q, "rb").read() != open(p, "rb").read():
                        return {"pass": False, "error": f"archive member differs from staged video {q}"}
                    p = q
                paths.append(p)
    bad = []
    for p in paths:
        s = encode.probe(p)
        exp_codec = "h264"
        if (s["nb_read_frames"], s["width"], s["height"], s["codec_name"]) != (sc.cfg["frames"], sc.cfg["width"], sc.cfg["height"], exp_codec):
            bad.append((p, s))
        lossless = "/lossless/" in p
        if lossless and s["pix_fmt"] not in ("gbrp", "rgb24", "bgr0"):
            bad.append((p, s))
        if not lossless and s["pix_fmt"] != "yuv420p":
            bad.append((p, s))
    return {"videos_checked": len(paths), "bad": [str(b) for b in bad[:10]], "pass": not bad}
