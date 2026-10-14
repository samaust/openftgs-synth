# SPDX-License-Identifier: GPL-3.0-or-later
"""Resolve Poly Haven asset ids to direct file URLs (one-off helper).

Writes a YAML fragment for assets.yaml. Uses the public API with an identifying
User-Agent, as its terms require. Only metadata is fetched here; downloads are done
by fetch_assets.py from the recorded URLs.
"""
import json
import sys
import urllib.request

import yaml

UA = "openftgs-synth-asset-fetcher/0.1"
API = "https://api.polyhaven.com"


def get(path):
    req = urllib.request.Request(API + path, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def resolve(kind, asset_id, res):
    info = get(f"/info/{asset_id}")
    files = get(f"/files/{asset_id}")
    out = []
    if kind == "hdri":
        f = files["hdri"][res]["hdr"]
        out.append({"url": f["url"], "md5": f["md5"], "size": f["size"], "path": f["url"].rsplit("/", 1)[1]})
    elif kind == "texture":
        diffuse = "Diffuse" if "Diffuse" in files else "col_1"  # multi-colour sets: first colourway
        for m in (diffuse, "nor_gl", "Rough"):
            if m not in files:
                continue
            f = files[m][res]["jpg"]
            out.append({"url": f["url"], "md5": f["md5"], "size": f["size"], "path": f["url"].rsplit("/", 1)[1]})
    elif kind == "model":
        g = files["gltf"][res]["gltf"]
        out.append({"url": g["url"], "md5": g["md5"], "size": g["size"], "path": g["url"].rsplit("/", 1)[1]})
        for rel, f in sorted(g.get("include", {}).items()):
            out.append({"url": f["url"], "md5": f["md5"], "size": f["size"], "path": rel})
    authors = sorted(info.get("authors", {}).keys())
    return {
        "id": asset_id,
        "source": "polyhaven",
        "kind": kind,
        "name": info.get("name", asset_id),
        "page": f"https://polyhaven.com/a/{asset_id}",
        "author": ", ".join(authors),
        "resolution": res,
        "files": out,
    }


if __name__ == "__main__":
    spec = yaml.safe_load(open(sys.argv[1]))
    res = [resolve(a["kind"], a["id"], a.get("res", "1k")) for a in spec]
    yaml.safe_dump(res, sys.stdout, sort_keys=False, width=200)
