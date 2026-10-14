# SPDX-License-Identifier: GPL-3.0-or-later
"""Download the CC0 assets listed in assets.yaml and verify them.

Each asset goes into its own directory under the asset root
(default ~/datasets/openftgs-synth-assets/<id>/). Files are checked against the
publisher's MD5 when one is listed and against the SHA-256 recorded in
assets.yaml. With --record, missing SHA-256 values are written back.
"""
import argparse
import hashlib
import os
import urllib.request

import yaml

UA = "openftgs-synth-asset-fetcher/0.1"
HERE = os.path.dirname(os.path.abspath(__file__))
MANIFEST = os.path.join(HERE, "..", "assets.yaml")
DEFAULT_ROOT = os.path.expanduser("~/datasets/openftgs-synth-assets")


def digest(path, algo):
    h = hashlib.new(algo)
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=DEFAULT_ROOT)
    ap.add_argument("--record", action="store_true", help="write missing sha256 values into assets.yaml")
    args = ap.parse_args()
    text = open(MANIFEST).read()
    header = "".join(l for l in text.splitlines(True) if l.startswith("#"))
    assets = yaml.safe_load(text)
    changed = False
    for a in assets:
        d = os.path.join(args.root, a["id"])
        for f in a["files"]:
            dst = os.path.normpath(os.path.join(d, f["path"]))
            if not dst.startswith(os.path.normpath(d) + os.sep):
                raise SystemExit(f"refusing path outside asset dir: {f['path']}")
            if not os.path.exists(dst):
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                req = urllib.request.Request(f["url"], headers={"User-Agent": UA})
                with urllib.request.urlopen(req, timeout=120) as r, open(dst + ".part", "wb") as o:
                    o.write(r.read())
                os.replace(dst + ".part", dst)
            if f.get("md5") and digest(dst, "md5") != f["md5"]:
                raise SystemExit(f"MD5 mismatch: {dst}")
            sha = digest(dst, "sha256")
            if f.get("sha256") is None:
                if not args.record:
                    raise SystemExit(f"no sha256 recorded for {dst}; run with --record")
                f["sha256"] = sha
                changed = True
            elif f["sha256"] != sha:
                raise SystemExit(f"SHA-256 mismatch: {dst}")
        print("ok", a["id"])
    if changed:
        with open(MANIFEST, "w") as o:
            o.write(header + yaml.safe_dump(assets, sort_keys=False, width=200, allow_unicode=True))


if __name__ == "__main__":
    main()
