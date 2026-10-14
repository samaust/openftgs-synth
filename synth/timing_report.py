# SPDX-License-Identifier: GPL-3.0-or-later
"""Timing and disk estimate for one scene, from a short real render at full resolution.

Renders frames 0-2 of camera 0 (rgb + aux) plus the per-camera passes (bg, markers, clock)
into a scratch dataset, under three denoiser variants, measures post-processing and video
bit rates, runs checks 1 and 2 on the rendered frames, and extrapolates.
"""
import json
import os
import shutil
import subprocess
import time

import numpy as np
import yaml

SCRATCH = os.path.expanduser("~/datasets/openftgs-synth-work/_timing")


def _probe_packets(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "packet=size,flags",
                        "-of", "json", path], check=True, capture_output=True, text=True)
    pk = json.loads(r.stdout)["packets"]
    key = [int(p["size"]) for p in pk if "K" in p["flags"]]
    non = [int(p["size"]) for p in pk if "K" not in p["flags"]]
    return key, non


def time_scene(sc_main, frames=(0, 1, 2), cam=0):
    from . import encode, pipeline, post, rig
    cfg = rig.load_config_dict(sc_main.cfg) if hasattr(rig, "load_config_dict") else dict(sc_main.cfg)
    out = {"scene": sc_main.name}
    root = os.path.join(SCRATCH, sc_main.name)
    shutil.rmtree(root, ignore_errors=True)
    os.makedirs(root)
    # isolate everything in the scratch tree
    data, work = os.path.join(root, "data"), os.path.join(root, "work")
    old = (pipeline.DATA, pipeline.WORK)
    pipeline.DATA, pipeline.WORK = data, work
    try:
        cfg = json.loads(json.dumps(cfg))
        cfg["keep_distorted_frames"] = True
        p = os.path.join(root, "cfg.yaml")
        yaml.safe_dump(cfg, open(p, "w"))
        sc = pipeline.Scene(p)
        t0 = time.time()
        pipeline.build(sc)
        out["build_s"] = round(time.time() - t0, 1)
        variants = {}
        for vname, rset in (("oidn_cpu", {"denoise": True, "denoise_gpu": False}),
                            ("oidn_gpu", {"denoise": True, "denoise_gpu": True}),
                            ("no_denoise", {"denoise": False})):
            sc.cfg["render"].update(rset)
            jobs = pipeline.make_jobs(sc, kinds=("rgb",), cams=[cam], frames=list(frames))
            for j in jobs:
                j["out"] = j["out"].replace(".png", f".{vname}.png")
            pipeline.job_seconds.clear()
            t0 = time.time()
            pipeline.run_blender(sc, jobs, f"timing_{vname}")
            wall = time.time() - t0
            secs = [pipeline.job_seconds[j["id"]] for j in jobs]
            variants[vname] = {"per_frame_s": [round(x, 2) for x in secs], "steady_s": round(float(np.mean(secs[1:])), 2),
                               "process_wall_s": round(wall, 1)}
            if vname != "oidn_cpu":
                for j in jobs:
                    os.remove(j["out"])
        out["rgb_variants"] = variants
        # keep the CPU-OIDN renders as the real outputs for post-processing
        sc.cfg["render"].update({"denoise": True, "denoise_gpu": False})
        jobs = pipeline.make_jobs(sc, kinds=("rgb",), cams=[cam], frames=list(frames))
        for j in jobs:
            os.replace(j["out"].replace(".png", ".oidn_cpu.png"), j["out"])
        t_post = []
        for j in jobs:
            t0 = time.time()
            post.run(j)
            t_post.append(time.time() - t0)
        out["post_rgb_s_single_process"] = round(float(np.mean(t_post)), 2)
        # aux and per-camera passes
        pipeline.job_seconds.clear()
        others = pipeline.make_jobs(sc, kinds=("aux", "bg", "markers", "clock"), cams=[cam], frames=list(frames))
        t0 = time.time()
        pipeline.run_blender(sc, others, "timing_aux")
        out["aux_bg_markers_clock_wall_s"] = round(time.time() - t0, 1)
        js = pipeline.job_seconds
        aux = [js[j["id"]] for j in others if j["kind"] == "aux"]
        out["aux_steady_s"] = round(float(np.mean(aux[1:])), 3)
        for k in ("bg", "markers"):
            out[f"{k}_s"] = round(sum(js[j["id"]] for j in others if j["kind"] == k), 2)
        out["clock_s_each"] = round(float(np.mean([js[j["id"]] for j in others if j["kind"] == "clock"])), 2)
        for j in others:
            post.run(j)
        # sizes
        name = sc.names[cam]
        gt = sc.gt
        sz = lambda d, ext: float(np.mean([os.path.getsize(os.path.join(d, f)) for f in os.listdir(d) if f.endswith(ext)]))  # noqa: E731
        sizes = {"pinhole_png": sz(os.path.join(gt, "pinhole", name), ".png"),
                 "depth_exr": sz(os.path.join(gt, "depth", name), ".exr"),
                 "mask_png": sz(os.path.join(gt, "masks", name), ".png"),
                 "background_png": os.path.getsize(os.path.join(gt, "background", name + ".png"))}
        lay = sc.layouts[0]
        src = os.path.join(gt, "pinhole", name) if lay["frames"] == "pinhole" else os.path.join(sc.work, "distorted", name)
        vids = {}
        for lossless in (False, True):
            v = os.path.join(root, f"probe_{int(lossless)}.mp4")
            t0 = time.time()
            encode.encode(src, sc.cfg["fps"], v, lossless)
            et = time.time() - t0
            key, non = _probe_packets(v)
            vids["lossless" if lossless else "lossy"] = {"keyframe_bytes": key[0], "pframe_bytes_mean": float(np.mean(non)),
                                                         "encode_s_per_frame": round(et / len(frames), 2)}
        sizes["videos"] = vids
        out["sizes_bytes"] = sizes
        # checks 1 and 2 at full resolution on these frames
        from validate import checks
        from . import package
        package.package_scene_minimal(sc)
        out["check1"] = {k: v for k, v in checks.check_markers(sc, cams=[cam]).items() if k != "cameras"}
        if sc.distorted:
            out["check2"] = {k: v for k, v in checks.check_undistort_frames(sc, cam, list(frames)).items()}
    finally:
        pipeline.DATA, pipeline.WORK = old
    out["estimate"] = estimate(sc_main, out)
    json.dump(out, open(os.path.join(SCRATCH, sc_main.name + ".json"), "w"), indent=1)
    print(json.dumps(out, indent=1))
    return out


def estimate(sc, t, gb=1e9):
    c = sc.cfg
    ncam, nfr = len(sc.cams), c["frames"]
    v = t["rgb_variants"]
    per_cam_fixed = t["bg_s"] + t["markers_s"] + 3 * t["clock_s_each"] + 25.0  # + Blender start/load
    est = {}
    for var in ("oidn_cpu", "oidn_gpu", "no_denoise"):
        frame_s = v[var]["steady_s"] + t["aux_steady_s"]
        est[f"hours_{var}"] = round((ncam * nfr * frame_s + ncam * per_cam_fixed) / 3600, 1)
    s = t["sizes_bytes"]
    n = ncam * nfr
    vid = s["videos"]
    nkey = -(-nfr // 250)  # libx264 default keyint 250
    lossy = ncam * (nkey * vid["lossy"]["keyframe_bytes"] + (nfr - nkey) * vid["lossy"]["pframe_bytes_mean"])
    lossless = ncam * (nkey * vid["lossless"]["keyframe_bytes"] + (nfr - nkey) * vid["lossless"]["pframe_bytes_mean"])
    gt = (s["pinhole_png"] + s["depth_exr"] + s["mask_png"]) * n + s["background_png"] * ncam
    nlay = len(c["layouts"])
    selfcap = any(l["layout"] == "selfcap" for l in c["layouts"])
    final = gt + nlay * (lossy + lossless)
    work_peak = (s["pinhole_png"] * nfr * 1.1 if sc.distorted else 0) + (lossy if selfcap else 0) + 5e9
    est.update({
        "disk_final_GB": round(final / gb, 1),
        "disk_breakdown_GB": {"pinhole": round(s["pinhole_png"] * n / gb, 1), "depth": round(s["depth_exr"] * n / gb, 1),
                              "masks": round(s["mask_png"] * n / gb, 2), "videos_lossy": round(nlay * lossy / gb, 2),
                              "videos_lossless": round(nlay * lossless / gb, 1)},
        "note": "video sizes from P-frame sizes of 3 consecutive frames plus one keyframe per 250 frames",
        "work_peak_GB": round(work_peak / gb, 1),
        "frames_total": n,
    })
    return est
