# SPDX-License-Identifier: GPL-3.0-or-later
"""Run pipeline stages for one scene.

  .venv/bin/python tools/run_scene.py configs/tiny.yaml build render package
  .venv/bin/python tools/run_scene.py configs/kitchen.yaml time      # one-frame timing
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from synth import pipeline  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("config")
    ap.add_argument("stages", nargs="+", choices=["build", "render", "package", "time"])
    ap.add_argument("--workers", type=int, default=12)
    ap.add_argument("--cams", type=str, default=None, help="comma-separated camera indices")
    ap.add_argument("--frames", type=str, default=None, help="comma-separated frame indices")
    a = ap.parse_args()
    sc = pipeline.Scene(a.config)
    cams = [int(x) for x in a.cams.split(",")] if a.cams else None
    frames = [int(x) for x in a.frames.split(",")] if a.frames else None
    for st in a.stages:
        if st == "build":
            pipeline.build(sc)
        elif st == "render":
            pipeline.render(sc, workers=a.workers, cams=cams, frames=frames)
        elif st == "package":
            from synth import package
            package.package_scene(sc)
        elif st == "time":
            from synth import timing_report
            timing_report.time_scene(sc)


if __name__ == "__main__":
    main()
