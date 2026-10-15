# SPDX-License-Identifier: GPL-3.0-or-later
"""Write the dataset-level files (LICENSE, DATASET_CARD.md, ASSETS.md, VERSION) into the
dataset root and then SHA256SUMS covering every file.

  .venv/bin/python tools/finalize_dataset.py configs/tiny.yaml configs/tiny_unsync.yaml ...
"""
import hashlib
import json
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.join(HERE, "..")
sys.path.insert(0, REPO)

from synth import pipeline  # noqa: E402
from synth.package import dist_model  # noqa: E402


def sha256(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 22), b""):
            h.update(chunk)
    return h.hexdigest()


def render_hours(sc):
    """Sum of the per-job render seconds that render.py printed (JOBDONE id seconds)."""
    import glob
    t = 0.0
    for f in glob.glob(os.path.join(sc.work, "render_*.log")):
        for line in open(f, errors="replace"):
            if line.startswith("JOBDONE"):
                t += float(line.split()[2])
    return t / 3600


def scenes_table(scenes):
    L = ["| Scene | Layouts (frames) | Cameras | Size | fps | Frames | Lens | Rig | Notes |",
         "| --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for sc in scenes:
        c = sc.cfg
        lays = ", ".join(f"{l['layout']} ({l['frames']})" for l in c["layouts"])
        models = sorted({dist_model(k["D"]) for k in sc.cams})
        rig = c["rig"]
        rd = (f"{rig['type']}, r={rig['radius']} m" + (f", heights {rig['heights']}" if "heights" in rig else ""))
        notes = []
        if c.get("ccm"):
            notes.append("ccm_<n> identity in intri.yml")
        if c.get("sync"):
            o = list(sc.offsets.values())
            notes.append(f"unsynchronized, offsets {min(o):+.4f}..{max(o):+.4f} s")
        if c.get("seq") and c["seq"] != sc.name:
            notes.append(f"selfcap seq `{c['seq']}`")
        L.append(f"| `{sc.name}` | {lays} | {len(sc.cams)} | {c['width']}x{c['height']} | {c['fps']} | {c['frames']} | "
                 f"{', '.join(models)} | {rd} | {'; '.join(notes)} |")
    return "\n".join(L)


def validation_table(scenes):
    rep = json.load(open(os.path.join(pipeline.WORK, "validation_report.json")))
    L = ["| Scene | 1 markers pinhole / distorted, max px (n) | 2 undistort mean / median / p95 levels | 3 poses err | 4 YAML | 5 clock time err | 6 archives | videos |",
         "| --- | --- | --- | --- | --- | --- | --- | --- |"]
    for sc in scenes:
        r = rep[sc.name]
        m = r["1_marker_projection"]
        mk = f"{m['max_pinhole_px']:.3f} ({m['n_pinhole']})" + (f" / {m['max_distorted_px']:.3f} ({m['n_distorted']})" if "max_distorted_px" in m else "")
        u = r["2_undistort_roundtrip"]
        us = "n/a" if "skipped" in u else f"{u['mean_abs']:.2f} / {u['median']:.0f} / {u['p95']:.0f} (half-px shifted: {u['mean_abs_if_principal_point_off_by_half_pixel']:.2f})"
        p = r["3_poses_bounds"]
        ps = "n/a" if "skipped" in p else f"{p['max_pose_error']:.1e}"
        y = r["4_yaml_readback"]
        ys = "n/a" if "skipped" in y else ("exact" if y["pass"] else "FAIL")
        s = r["5_sync_and_times"]
        ss = f"{s['clock_time_max_err_ms']:.2f} ms ({s['clock_frames_checked']} renders)"
        a = r["6_archives"]
        as_ = "n/a" if "skipped" in a else ("exact" if a["pass"] else "FAIL")
        v = r["videos_ffprobe"]
        allp = all(x["pass"] for x in r.values())
        L.append(f"| `{sc.name}` {'PASS' if allp else 'FAIL'} | {mk} | {us} | {ps} | {ys} | {ss} | {as_} | {v['videos_checked']} ok |")
    return "\n".join(L)


def main(cfgs):
    scenes = [pipeline.Scene(c) for c in cfgs]
    D = pipeline.DATA
    ver = open(os.path.join(REPO, "dataset", "VERSION")).read().strip()
    shutil.copy(os.path.join(REPO, "dataset", "LICENSE"), os.path.join(D, "LICENSE"))
    shutil.copy(os.path.join(REPO, "dataset", "VERSION"), os.path.join(D, "VERSION"))
    shutil.copy(os.path.join(REPO, "ASSETS.md"), os.path.join(D, "ASSETS.md"))
    tests = [f"- `{sc.name}`: camera `{sc.cfg['sync']['test_camera']}` is the held-out test camera."
             for sc in scenes if (sc.cfg.get("sync") or {}).get("test_camera")]
    r = scenes[0].cfg["render"] if scenes else {}
    rs = ", ".join(f"`{sc.name}`: {sc.cfg['render']['samples']} spp at 2x" for sc in scenes)
    rs += "; OpenImageDenoise (albedo + normal, prefilter accurate, quality high, GPU); seed 0; clamp indirect 10"
    rs += (". Blender render time on one RTX 4090 (sum of jobs, excluding post-processing and encoding): "
           + ", ".join(f"`{sc.name}` {render_hours(sc):.1f} h" for sc in scenes if render_hours(sc) >= 0.05) + ".")
    card = open(os.path.join(REPO, "dataset", "DATASET_CARD.template.md")).read()
    card = card.replace("{VERSION}", ver).replace("{BLENDER}", "5.2.2 LTS")
    card = card.replace("{SCENES_TABLE}", scenes_table(scenes)).replace("{VALIDATION_TABLE}", validation_table(scenes))
    card = card.replace("{RENDER_SETTINGS}", rs).replace("{TEST_CAMERAS}", "\n".join(tests) or "n/a")
    card = card.replace("{DECISIONS}", open(os.path.join(REPO, "dataset", "decisions.md")).read().strip())
    open(os.path.join(D, "DATASET_CARD.md"), "w").write(card)
    files = []
    for d, _, fs in os.walk(D):
        for f in fs:
            rp = os.path.relpath(os.path.join(d, f), D)
            if rp != "SHA256SUMS":
                files.append(rp)
    with open(os.path.join(D, "SHA256SUMS.tmp"), "w") as out:
        for rp in sorted(files):
            out.write(f"{sha256(os.path.join(D, rp))}  {rp}\n")
    os.replace(os.path.join(D, "SHA256SUMS.tmp"), os.path.join(D, "SHA256SUMS"))
    print(f"finalized {D}: {len(files)} files")


if __name__ == "__main__":
    main(sys.argv[1:])
