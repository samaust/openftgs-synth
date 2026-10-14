# SPDX-License-Identifier: GPL-3.0-or-later
"""Quick look: render a few cameras/frames of a scene at reduced resolution into a scratch
directory and write a contact sheet.

  .venv/bin/python tools/preview.py configs/kitchen.yaml OUTDIR --scale 0.5 --cams 0,10,19 --frames 0,150
"""
import argparse
import os
import sys

import yaml

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("config")
    ap.add_argument("outdir")
    ap.add_argument("--scale", type=float, default=0.5)
    ap.add_argument("--cams", default="0")
    ap.add_argument("--frames", default="0")
    ap.add_argument("--samples", type=int, default=16)
    a = ap.parse_args()
    import shutil
    shutil.rmtree(a.outdir, ignore_errors=True)  # previews never resume
    os.makedirs(a.outdir, exist_ok=True)
    os.environ["OPENFTGS_SYNTH_DATA"] = os.path.join(a.outdir, "data")
    os.environ["OPENFTGS_SYNTH_WORK"] = os.path.join(a.outdir, "work")
    from synth import pipeline, rig
    cfg = rig.load_config(a.config)
    cfg["name"] += "_preview"
    cfg["width"] = int(round(cfg["width"] * a.scale / 2)) * 2
    cfg["height"] = int(round(cfg["height"] * a.scale / 2)) * 2
    cfg["render"]["samples"] = a.samples
    cfg["markers"]["count"] = 4
    p = os.path.join(a.outdir, "preview.yaml")
    yaml.safe_dump(cfg, open(p, "w"))
    sc = pipeline.Scene(p)
    pipeline.build(sc)
    cams = [int(x) for x in a.cams.split(",")]
    frames = [int(x) for x in a.frames.split(",")]
    pipeline.render(sc, cams=cams, frames=frames, encode_videos=False, kinds=("rgb",))
    import cv2
    import numpy as np
    rows = []
    for c in cams:
        rows.append(np.hstack([cv2.imread(os.path.join(sc.gt, "pinhole", sc.names[c], f"{n:06d}.png")) for n in frames]))
    sheet = np.vstack(rows)
    cv2.imwrite(os.path.join(a.outdir, "sheet.jpg"), sheet, [cv2.IMWRITE_JPEG_QUALITY, 90])
    print(os.path.join(a.outdir, "sheet.jpg"))


if __name__ == "__main__":
    main()
