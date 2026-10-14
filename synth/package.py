# SPDX-License-Identifier: GPL-3.0-or-later
"""Write ground-truth metadata and the three dataset layouts for one scene."""
import glob
import gzip
import io as _io
import json
import os
import shutil
import tarfile

os.environ.setdefault("OPENCV_IO_ENABLE_OPENEXR", "1")

import cv2  # noqa: E402
import numpy as np  # noqa: E402

from . import camera as cm  # noqa: E402
from .pipeline import DATA  # noqa: E402

TAR_MTIME = 1791849600  # 2026-10-13T00:00:00Z, fixed so archives are reproducible


def dist_model(D):
    n = len(D)
    return "pinhole" if n == 0 or not np.any(D) else {4: "opencv4", 5: "opencv5", 8: "opencv8", 12: "opencv12"}[n]


def cameras_json(sc):
    cams = []
    for i, k in enumerate(sc.cams):
        lay_names = {l["layout"]: sc.layout_name(l["layout"], i) for l in sc.layouts}
        Kc = k["K"]
        cams.append({
            "name": k["name"],
            "layout_names": lay_names,
            "width": k["W"], "height": k["H"],
            "K_opencv": cm.K_continuous_to_opencv(Kc).tolist(),
            "K_continuous": Kc.tolist(),
            "distortion_model": dist_model(k["D"]),
            "distortion": [float(d) for d in k["D"]],
            "world_to_camera": cm.world_to_camera_4x4(k["R"], k["t"]).tolist(),
            "camera_center": cm.center_of(k["R"], k["t"]).tolist(),
            "sync_offset": sc.offsets[k["name"]],
            "frames": [{"n": n, "t": t} for n, t in sc.times[k["name"]]],
        })
    frames_by_layout = {l["layout"]: l["frames"] for l in sc.layouts}
    return {
        "scene": sc.name,
        "fps": sc.cfg["fps"],
        "num_frames": sc.cfg["frames"],
        "layouts": frames_by_layout,
        "test_camera": (sc.cfg.get("sync") or {}).get("test_camera") or sc.cfg.get("test_camera"),
        "conventions": {
            "world": "right-handed, metres, z up",
            "camera": "OpenCV axes (x right, y down, z forward); world_to_camera maps x_world to x_cam = R x + t; centre = -R^T t",
            "K_opencv": "integer pixel centres (OpenCV)",
            "K_continuous": "image spans [0,W]x[0,H], pixel (u,v) sampled at (u+0.5, v+0.5); c_continuous = c_opencv + 0.5",
            "distortion": "OpenCV coefficient order k1 k2 p1 p2 k3 [k4 k5 k6 [s1 s2 s3 s4]]; applies to the 'distorted' videos only",
            "time": "frame n of camera c shows the scene at t = n/fps - sync_offset_c (seconds)",
            "ground_truth_images": "pinhole/, depth/, masks/ and background/ are undistorted, with K_continuous / K_opencv and no distortion",
            "depth": "float32 EXR, single channel 'Y', z-depth along the optical axis in metres, 0 = no surface (sky)",
            "masks": "8-bit PNG, 255 = dynamic object visible at the pixel centre, 0 = static",
        },
        "cameras": cams,
    }


def write_yaml_intri(path, sc, ccm=False):
    fs = cv2.FileStorage(path, cv2.FILE_STORAGE_WRITE)
    names = [sc.layout_name("enerf_outdoor", i) for i in range(len(sc.cams))]
    fs.startWriteStruct("names", cv2.FileNode_SEQ)
    for n in names:
        fs.write("", n)
    fs.endWriteStruct()
    for n, k in zip(names, sc.cams):
        fs.write(f"K_{n}", cm.K_continuous_to_opencv(k["K"]))
        fs.write(f"D_{n}", np.asarray(k["D"], np.float64).reshape(-1, 1))
        fs.write(f"H_{n}", int(k["H"]))
        fs.write(f"W_{n}", int(k["W"]))
        if ccm:
            fs.write(f"ccm_{n}", np.eye(3))
    fs.release()


def write_yaml_extri(path, sc):
    fs = cv2.FileStorage(path, cv2.FILE_STORAGE_WRITE)
    names = [sc.layout_name("enerf_outdoor", i) for i in range(len(sc.cams))]
    fs.startWriteStruct("names", cv2.FileNode_SEQ)
    for n in names:
        fs.write("", n)
    fs.endWriteStruct()
    for n, k in zip(names, sc.cams):
        fs.write(f"R_{n}", cm.rodrigues(k["R"]).reshape(3, 1))
        fs.write(f"Rot_{n}", np.asarray(k["R"], np.float64))
        fs.write(f"T_{n}", np.asarray(k["t"], np.float64).reshape(3, 1))
    fs.release()


def depth_bounds(sc, name, lo=0.1, hi=99.9):
    vals = []
    for p in sorted(glob.glob(os.path.join(sc.gt, "depth", name, "*.exr"))):
        d = cv2.imread(p, cv2.IMREAD_UNCHANGED)
        v = d[d > 0]
        vals.append(v[:: max(1, v.size // 20000)])
    v = np.concatenate(vals)
    return float(np.percentile(v, lo)) * 0.9, float(np.percentile(v, hi)) * 1.1


def poses_bounds(sc):
    rows = []
    for i, k in enumerate(sc.cams):
        Rc2w = k["R"].T  # columns: right, down, forward
        c0, c1, c2 = Rc2w[:, 1], Rc2w[:, 0], -Rc2w[:, 2]  # down, right, back
        f = k["K"][0, 0]
        assert np.isclose(k["K"][0, 0], k["K"][1, 1]) and np.allclose(k["K"][:2, 2], [k["W"] / 2, k["H"] / 2]), \
            "n3dv layout needs fx = fy and the principal point at the image centre"
        M = np.stack([c0, c1, c2, cm.center_of(k["R"], k["t"]), [k["H"], k["W"], f]], axis=1)
        near, far = depth_bounds(sc, k["name"])
        rows.append(np.concatenate([M.reshape(-1), [near, far]]))
    return np.array(rows, np.float64)


def _tar(out, root, members):
    """Deterministic tar.gz of `members` (paths relative to root), files only, sorted."""
    tmp = out + ".tmp"
    with open(tmp, "wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0, compresslevel=6) as gz:
            with tarfile.open(fileobj=gz, mode="w", format=tarfile.GNU_FORMAT) as tf:
                for m in sorted(members):
                    p = os.path.join(root, m)
                    ti = tarfile.TarInfo(m)
                    ti.size = os.path.getsize(p)
                    ti.mtime = TAR_MTIME
                    ti.mode = 0o644
                    ti.uid = ti.gid = 0
                    ti.uname = ti.gname = ""
                    with open(p, "rb") as f:
                        tf.addfile(ti, f)
    os.replace(tmp, out)


def selfcap_members(sc):
    seq = sc.seq()
    names = [sc.layout_name("selfcap", i) for i in range(len(sc.cams))]
    rel = [f"{seq}-release/videos/{n}.mp4" for n in names]
    rel += [f"{seq}-release/optimized/{f}" for f in ("intri.yml", "extri.yml", "sync.json")]
    cal = [f"{seq}-calib/optimized/{f}" for f in ("intri.yml", "extri.yml", "sync.json")]
    return rel, cal


def package_scene_minimal(sc):
    """cameras.json + markers.json only (used by the timing run)."""
    os.makedirs(sc.gt, exist_ok=True)
    json.dump(cameras_json(sc), open(os.path.join(sc.gt, "cameras.json"), "w"), indent=1)
    info = json.load(open(sc.scene_info))
    json.dump({"scene": sc.name, "markers": info["markers"], "clock_marker": info["clock"]},
              open(os.path.join(sc.gt, "markers.json"), "w"), indent=1)


def package_scene(sc):
    os.makedirs(sc.gt, exist_ok=True)
    cj = cameras_json(sc)
    json.dump(cj, open(os.path.join(sc.gt, "cameras.json"), "w"), indent=1)
    info = json.load(open(sc.scene_info))
    json.dump({"scene": sc.name, "note": "emissive validation spheres, hidden in all normal renders",
               "markers": info["markers"], "clock_marker": {**info["clock"],
                                                            "trajectory": "p(t) = p0 + velocity * t, t in seconds"}},
              open(os.path.join(sc.gt, "markers.json"), "w"), indent=1)
    for lay in sc.layouts:
        L = lay["layout"]
        if L == "n3dv":
            pb = poses_bounds(sc)
            for root in (DATA, os.path.join(DATA, "lossless")):
                d = os.path.join(root, "n3dv", sc.name)
                os.makedirs(d, exist_ok=True)
                np.save(os.path.join(d, "poses_bounds.npy"), pb)
        elif L == "enerf_outdoor":
            for root in (DATA, os.path.join(DATA, "lossless")):
                d = os.path.join(root, "enerf_outdoor", sc.name)
                os.makedirs(d, exist_ok=True)
                write_yaml_intri(os.path.join(d, "intri.yml"), sc, ccm=sc.cfg.get("ccm", False))
                write_yaml_extri(os.path.join(d, "extri.yml"), sc)
        elif L == "selfcap":
            seq = sc.seq()
            stage = os.path.join(sc.work, "selfcap_stage")
            names = [sc.layout_name("selfcap", i) for i in range(len(sc.cams))]
            sync = {n: sc.offsets[k["name"]] for n, k in zip(names, sc.cams)}
            for top in (f"{seq}-release", f"{seq}-calib"):
                od = os.path.join(stage, top, "optimized")
                os.makedirs(od, exist_ok=True)
                write_yaml_intri(os.path.join(od, "intri.yml"), sc, ccm=sc.cfg.get("ccm", False))
                write_yaml_extri(os.path.join(od, "extri.yml"), sc)
                json.dump(sync, open(os.path.join(od, "sync.json"), "w"), indent=1)
            ll = os.path.join(DATA, "lossless", "selfcap", seq, "optimized")
            if os.path.exists(ll):
                shutil.rmtree(ll)
            shutil.copytree(os.path.join(stage, f"{seq}-release", "optimized"), ll)
            rel, cal = selfcap_members(sc)
            out = os.path.join(DATA, "selfcap")
            os.makedirs(out, exist_ok=True)
            _tar(os.path.join(out, f"{seq}-release.tar.gz"), stage, rel)
            _tar(os.path.join(out, f"{seq}-calib.tar.gz"), stage, cal)
    print(f"[{sc.name}] packaged")
