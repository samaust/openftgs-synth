# SPDX-License-Identifier: GPL-3.0-or-later
"""Orchestration: build -> render (streamed post-processing and encoding) -> package."""
import concurrent.futures as cf
import json
import math
import os
import shutil
import subprocess
import sys
import time

import numpy as np

from . import camera as cm
from . import encode
from . import imageops as io
from . import post
from . import rig as rg

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BLENDER = os.environ.get("OPENFTGS_SYNTH_BLENDER", os.path.expanduser("~/opt/blender-5.2.2-linux-x64/blender"))
DATA = os.environ.get("OPENFTGS_SYNTH_DATA", os.path.expanduser("~/datasets/openftgs-synth"))
WORK = os.environ.get("OPENFTGS_SYNTH_WORK", os.path.expanduser("~/datasets/openftgs-synth-work"))
ASSETS = os.environ.get("OPENFTGS_SYNTH_ASSETS", os.path.expanduser("~/datasets/openftgs-synth-assets"))
LAYOUT_DIRS = {"n3dv": "n3dv", "enerf_outdoor": "enerf_outdoor", "selfcap": "selfcap"}


class Scene:
    """Everything derived from a config: rig, geometry, times, paths."""

    def __init__(self, cfg_path):
        self.cfg = rg.load_config(cfg_path)
        c = self.cfg
        self.name = c["name"]
        self.work = os.path.join(WORK, self.name)
        self.gt = os.path.join(DATA, "ground_truth", self.name)
        self.cams = rg.build_rig(c)
        self.names = [k["name"] for k in self.cams]
        self.timing = rg.timing(c)
        self.offsets = rg.sync_offsets(c, self.names)
        self.times = rg.frame_times(c, self.offsets)
        self.ss = c.get("supersample", rg.SS)
        self.layouts = c["layouts"]
        self.distorted = any(l["frames"] == "distorted" for l in self.layouts)
        self.blend = os.path.join(self.work, "scene.blend")
        self.scene_info = os.path.join(self.work, "scene_info.json")
        self._geo = None

    # ------------------------------------------------------------ names per layout
    def layout_name(self, layout, i):
        if layout == "n3dv":
            return f"cam{i:02d}"
        return f"{i:04d}"

    def seq(self):
        return self.cfg.get("seq", self.name)

    def video_paths(self, layout, i, lossless):
        n = self.layout_name(layout, i)
        root = os.path.join(DATA, "lossless") if lossless else DATA
        if layout == "n3dv":
            return os.path.join(root, "n3dv", self.name, n + ".mp4")
        if layout == "enerf_outdoor":
            return os.path.join(root, "enerf_outdoor", self.name, "videos", n + ".mp4")
        if layout == "selfcap":
            if lossless:
                return os.path.join(root, "selfcap", self.seq(), "videos", n + ".mp4")
            return os.path.join(self.work, "selfcap_stage", f"{self.seq()}-release", "videos", n + ".mp4")
        raise ValueError(layout)

    # ------------------------------------------------------------ geometry
    def geometry(self):
        if self._geo is None:
            os.makedirs(os.path.join(self.work, "maps"), exist_ok=True)
            geo = []
            for k in self.cams:
                g = rg.render_geometry(k, self.ss, margin_min_frac=self.cfg.get("margin_min_frac", 0.075)
                                       if self.distorted else 0.0)
                mp = os.path.join(self.work, "maps", k["name"] + ".npz")
                if "map_U" in g:
                    if not os.path.exists(mp):
                        bw, bh = g["big"]["resolution"]
                        io.BilinearMap(g.pop("map_U"), g.pop("map_V"), bw, bh).save(mp)
                    else:
                        g.pop("map_U"), g.pop("map_V")
                    g["map_path"] = mp
                geo.append(g)
            self._geo = geo
        return self._geo


# ---------------------------------------------------------------- build

def build(sc):
    from . import markers
    os.makedirs(sc.work, exist_ok=True)
    pts, counts = markers.choose(sc.cams, sc.cfg["markers"])
    print(f"[{sc.name}] {len(pts)} markers; per camera {min(counts)}..{max(counts)}")
    spec = {"name": sc.name, "builder": sc.cfg["builder"], "timing": sc.timing, "assets_root": ASSETS,
            "blend_path": sc.blend, "scene_info_path": sc.scene_info, "cfg": sc.cfg,
            "markers": {"points": pts, "radius": sc.cfg["markers"]["radius"]}, "clock": sc.cfg["clock"]}
    p = os.path.join(sc.work, "build_spec.json")
    json.dump(spec, open(p, "w"), indent=1)
    t0 = time.time()
    r = subprocess.run([BLENDER, "-b", "--factory-startup", "--python-exit-code", "1",
                        "-P", os.path.join(REPO, "blender", "build.py"), "--", p],
                       capture_output=True, text=True)
    log = os.path.join(sc.work, "build.log")
    open(log, "w").write(r.stdout + r.stderr)
    if r.returncode != 0 or "BUILD_OK" not in r.stdout:
        raise RuntimeError(f"build failed, see {log}")
    print(f"[{sc.name}] built in {time.time() - t0:.1f}s")


# ---------------------------------------------------------------- jobs

def make_jobs(sc, kinds=("rgb", "aux", "bg", "markers", "clock"), cams=None, frames=None):
    geo = sc.geometry()
    T = sc.timing
    jobs = []
    for i, k in enumerate(sc.cams):
        if cams is not None and i not in cams:
            continue
        name, g = k["name"], geo[i]
        rdir = os.path.join(sc.work, "render")
        base = {"cam": i, "cam_name": name}
        post_common = {"margins": g["margins"], "W": k["W"], "H": k["H"], "ss": sc.ss,
                       "map_path": g.get("map_path")}
        tl = sc.times[name]
        if frames is not None:
            tl = [tl[n] for n in frames]
        for n, t in tl:
            F = T["F0"] + t * T["fps"]
            if "rgb" in kinds:
                jobs.append(dict(base, id=f"rgb/{name}/{n:06d}", kind="rgb", n=n, time=t, frame=F,
                                 out=os.path.join(rdir, "rgb", name, f"{n:06d}.png"),
                                 post=dict(post_common,
                                           pinhole_out=os.path.join(sc.gt, "pinhole", name, f"{n:06d}.png"),
                                           distorted_out=os.path.join(sc.work, "distorted", name, f"{n:06d}.png")
                                           if sc.distorted else None)))
        for n, t in tl:
            F = T["F0"] + t * T["fps"]
            if "aux" in kinds:
                jobs.append(dict(base, id=f"aux/{name}/{n:06d}", kind="aux", n=n, time=t, frame=F,
                                 out=os.path.join(rdir, "aux", name, f"{n:06d}.exr"),
                                 post={"depth_out": os.path.join(sc.gt, "depth", name, f"{n:06d}.exr"),
                                       "mask_out": os.path.join(sc.gt, "masks", name, f"{n:06d}.png")}))
        if "bg" in kinds:
            jobs.append(dict(base, id=f"bg/{name}", kind="bg", n=0, time=0.0, frame=float(T["F0"]),
                             out=os.path.join(rdir, "bg", name + ".png"),
                             post=dict(post_common, pinhole_out=os.path.join(sc.gt, "background", name + ".png"),
                                       distorted_out=None)))
        if "markers" in kinds:
            jobs.append(dict(base, id=f"markers/{name}", kind="markers", n=0, time=0.0, frame=float(T["F0"]),
                             out=os.path.join(sc.work, "validation", "markers", name + ".exr"), post={}))
        if "clock" in kinds:
            nn = sorted({0, sc.cfg["frames"] // 2, sc.cfg["frames"] - 1})
            for n in nn:
                t = sc.times[name][n][1]
                jobs.append(dict(base, id=f"clock/{name}/{n:06d}", kind="clock", n=n, time=t,
                                 frame=T["F0"] + t * T["fps"],
                                 out=os.path.join(sc.work, "validation", "clock", name, f"{n:06d}.exr"), post={}))
    return jobs


def blender_spec(sc, jobs):
    geo = sc.geometry()
    cams = []
    for k, g in zip(sc.cams, geo):
        cams.append({"name": k["name"], "matrix_world": cm.blender_matrix_world(k["R"], k["t"]).tolist(),
                     "big": g["big"], "aux": g["aux"]})
    return {"render": sc.cfg["render"], "cameras": cams, "jobs": jobs}


def _done_log(sc):
    return os.path.join(sc.work, "done.txt")


def load_done(sc):
    p = _done_log(sc)
    return set(open(p).read().split()) if os.path.exists(p) else set()


def run_blender(sc, jobs, tag, on_done=None):
    p = os.path.join(sc.work, f"jobs_{tag}.json")
    json.dump(blender_spec(sc, jobs), open(p, "w"))
    log = open(os.path.join(sc.work, f"render_{tag}.log"), "w")
    proc = subprocess.Popen([BLENDER, "-b", sc.blend, "--factory-startup", "--python-exit-code", "1",
                             "-P", os.path.join(REPO, "blender", "render.py"), "--", p],
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
    ok = False
    for line in proc.stdout:
        log.write(line)
        if line.startswith("JOBDONE "):
            if on_done:
                on_done(line.split()[1])
        elif line.startswith("RENDER_OK"):
            ok = True
    proc.wait()
    log.close()
    if proc.returncode != 0 or not ok:
        raise RuntimeError(f"blender render failed ({tag}); see {log.name}")


def render(sc, workers=12, cams=None, frames=None, encode_videos=True, tag="main", kinds=None):
    """Render all outstanding jobs (one Blender process per camera), post-process them as they
    finish, and encode each camera's videos once its frames are complete. Resumable: finished
    jobs and encodes are recorded in <work>/done.txt."""
    kinds = kinds or ("rgb", "aux", "bg", "markers", "clock")
    jobs = make_jobs(sc, kinds=kinds, cams=cams, frames=frames)
    done = load_done(sc)
    todo = [j for j in jobs if j["id"] not in done]
    print(f"[{sc.name}] {len(todo)} of {len(jobs)} jobs to render", flush=True)
    by_id = {j["id"]: j for j in jobs}
    per_cam_rgb = {}
    for j in jobs:
        if j["kind"] == "rgb":
            per_cam_rgb.setdefault(j["cam"], set()).add(j["id"])
    rgb_done = {c: {i for i in ids if i in done} for c, ids in per_cam_rgb.items()}
    dlog = open(_done_log(sc), "a")
    t_start = time.time()
    futures = {}
    enc_pool = cf.ThreadPoolExecutor(max_workers=4)
    enc_futs = {}

    def mark(jid):
        dlog.write(jid + "\n")
        dlog.flush()
        done.add(jid)

    def maybe_encode(c):
        eid = f"enc/{sc.names[c]}"
        if (encode_videos and frames is None and eid not in done and c not in enc_futs
                and rgb_done[c] == per_cam_rgb[c]):
            enc_futs[c] = enc_pool.submit(encode_camera, sc, c)

    import threading
    err = []
    by_cam = {}
    for j in todo:
        by_cam.setdefault(j["cam"], []).append(j)
    with cf.ProcessPoolExecutor(max_workers=workers) as pool:
        def on_done(jid):
            futures[pool.submit(post.run, by_id[jid])] = jid

        def blender_thread():
            try:
                for c, cj in sorted(by_cam.items()):
                    run_blender(sc, cj, f"{tag}_{sc.names[c]}", on_done)
            except Exception as e:  # noqa: BLE001
                err.append(e)
        th = threading.Thread(target=blender_thread)
        th.start()
        for c in per_cam_rgb:
            maybe_encode(c)
        while th.is_alive() or futures or any(not f.done() for f in enc_futs.values()):
            fin = [f for f in list(futures) if f.done()]
            for f in fin:
                jid = futures.pop(f)
                f.result()
                mark(jid)
                j = by_id[jid]
                if j["kind"] == "rgb":
                    rgb_done[j["cam"]].add(jid)
                    maybe_encode(j["cam"])
            for c, f in list(enc_futs.items()):
                if f.done() and f"enc/{sc.names[c]}" not in done:
                    f.result()
                    mark(f"enc/{sc.names[c]}")
            if err:
                break
            if not fin:
                time.sleep(0.05)
        th.join()
        if err:
            raise err[0]
    enc_pool.shutdown()
    dlog.close()
    dt = time.time() - t_start
    print(f"[{sc.name}] rendered {len(todo)} jobs in {dt:.1f}s", flush=True)
    return dt


def encode_camera(sc, c):
    """Encode lossy + lossless videos for camera index c in every layout, check them, and
    remove the temporary distorted frames."""
    name = sc.names[c]
    fps = sc.cfg["fps"]
    for lay in sc.layouts:
        src = (os.path.join(sc.gt, "pinhole", name) if lay["frames"] == "pinhole"
               else os.path.join(sc.work, "distorted", name))
        for lossless in (False, True):
            out = sc.video_paths(lay["layout"], c, lossless)
            encode.encode(src, fps, out, lossless)
            s = encode.probe(out)
            if (s["nb_read_frames"], s["width"], s["height"]) != (sc.cfg["frames"], sc.cfg["width"], sc.cfg["height"]):
                raise RuntimeError(f"ffprobe mismatch for {out}: {s}")
            if lossless:
                encode.check_lossless(out, src, sc.cfg["width"], sc.cfg["height"])
    if sc.distorted and not sc.cfg.get("keep_distorted_frames", False):
        shutil.rmtree(os.path.join(sc.work, "distorted", name), ignore_errors=True)
    print(f"[{sc.name}] encoded camera {name}", flush=True)
