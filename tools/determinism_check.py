# SPDX-License-Identifier: GPL-3.0-or-later
"""Render the same colour, aux and marker jobs twice in separate Blender processes and
compare the outputs.

  .venv/bin/python tools/determinism_check.py configs/tiny.yaml [cam] [frame]
"""
import json
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
os.environ.setdefault("OPENCV_IO_ENABLE_OPENEXR", "1")

import cv2  # noqa: E402
import numpy as np  # noqa: E402

from synth import pipeline  # noqa: E402


def main(cfg, cam=0, frame=3):
    sc = pipeline.Scene(cfg)
    tmp = tempfile.mkdtemp(prefix="det_", dir=sc.work)
    outs = []
    for rep in (0, 1):
        jobs = []
        for k in ("rgb", "aux", "markers"):
            j = dict(pipeline.make_jobs(sc, kinds=(k,), cams=[cam], frames=[frame])[0])
            j["out"] = os.path.join(tmp, f"{rep}_{k}." + ("png" if k == "rgb" else "exr"))
            jobs.append(j)
        p = os.path.join(tmp, f"jobs_{rep}.json")
        json.dump(pipeline.blender_spec(sc, jobs), open(p, "w"))
        subprocess.run([pipeline.BLENDER, "-b", sc.blend, "--factory-startup", "--python-exit-code", "1",
                        "-P", os.path.join(pipeline.REPO, "blender", "render.py"), "--", p], check=True, capture_output=True)
        outs.append([j["out"] for j in jobs])
    res = {}
    for a, b in zip(*outs):
        A, B = cv2.imread(a, cv2.IMREAD_UNCHANGED), cv2.imread(b, cv2.IMREAD_UNCHANGED)
        d = np.abs(A.astype(np.float64) - B.astype(np.float64))
        res[os.path.basename(a)[2:]] = {"identical": bool(np.array_equal(A, B)), "max_abs_diff": float(d.max()),
                                        "frac_pixels_differing": float((d.max(-1) > 0).mean())}
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main(sys.argv[1], *[int(x) for x in sys.argv[2:]])
