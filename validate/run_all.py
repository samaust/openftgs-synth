# SPDX-License-Identifier: GPL-3.0-or-later
"""Run all validation checks for the given scene configs.

  .venv/bin/python validate/run_all.py configs/tiny.yaml [...] [--sha256sums]
Writes <work>/validation_report.json and prints a summary. Exit code 1 if anything fails.
"""
import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from synth import pipeline  # noqa: E402
from validate import checks  # noqa: E402

CHECKS = [
    ("1_marker_projection", checks.check_markers),
    ("2_undistort_roundtrip", checks.check_undistort),
    ("3_poses_bounds", checks.check_poses_bounds),
    ("4_yaml_readback", checks.check_yaml),
    ("5_sync_and_times", checks.check_sync),
    ("6_archives", checks.check_archives),
    ("videos_ffprobe", checks.check_videos),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("configs", nargs="*")
    ap.add_argument("--sha256sums", action="store_true")
    ap.add_argument("--only", default=None)
    a = ap.parse_args()
    report, ok = {}, True
    for cfg in a.configs:
        sc = pipeline.Scene(cfg)
        r = {}
        for name, fn in CHECKS:
            if a.only and not name.startswith(a.only):
                continue
            t0 = time.time()
            try:
                r[name] = fn(sc)
            except Exception as e:  # noqa: BLE001
                r[name] = {"pass": False, "error": f"{type(e).__name__}: {e}"}
            r[name]["seconds"] = round(time.time() - t0, 1)
            ok &= r[name]["pass"]
            print(f"[{sc.name}] {name}: {'PASS' if r[name]['pass'] else 'FAIL'} "
                  f"{json.dumps({k: v for k, v in r[name].items() if k not in ('cameras', 'per_camera', 'files')}, default=str)[:400]}",
                  flush=True)
        report[sc.name] = r
    if a.sha256sums:
        r = checks.check_sha256sums()
        report["SHA256SUMS"] = r
        ok &= r["pass"]
        print("SHA256SUMS:", "PASS" if r["pass"] else "FAIL", json.dumps(r)[:300])
    out = os.path.join(pipeline.WORK, "validation_report.json")
    old = json.load(open(out)) if os.path.exists(out) else {}
    old.update(report)
    json.dump(old, open(out, "w"), indent=1, default=str)
    print("ALL PASS" if ok else "SOME CHECKS FAILED")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
