# SPDX-License-Identifier: GPL-3.0-or-later
"""Per-frame post-processing of Blender outputs (runs in worker processes)."""
import os

os.environ.setdefault("OPENCV_IO_ENABLE_OPENEXR", "1")

import cv2  # noqa: E402
import numpy as np  # noqa: E402

from . import imageops as io  # noqa: E402

PNG_FLAGS = [cv2.IMWRITE_PNG_COMPRESSION, 4]
EXR_FLAGS = [cv2.IMWRITE_EXR_TYPE, cv2.IMWRITE_EXR_TYPE_FLOAT,
             cv2.IMWRITE_EXR_COMPRESSION, cv2.IMWRITE_EXR_COMPRESSION_ZIP]
_maps = {}


def _write(path, img, flags):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    root, ext = os.path.splitext(path)
    tmp = root + ".tmp" + ext
    if not cv2.imwrite(tmp, img, flags):
        raise IOError(f"cannot write {path}")
    os.replace(tmp, path)


def read_exr(path):
    img = cv2.imread(path, cv2.IMREAD_UNCHANGED)
    if img is None:
        raise IOError(path)
    return img


def warp_map(path):
    if path not in _maps:
        _maps[path] = io.BilinearMap.load(path)
    return _maps[path]


def crop_pinhole(lin_big, margins, W, H, ss):
    mL, _, mT, _ = margins
    return io.box2(lin_big[ss * mT: ss * (mT + H), ss * mL: ss * (mL + W)])


def distort_image(lin_big, map_path):
    return io.box2(warp_map(map_path)(lin_big))


def run(job):
    kind, p = job["kind"], job["post"]
    src = job["out"]
    if kind in ("rgb", "bg"):
        big = cv2.imread(src, cv2.IMREAD_UNCHANGED)
        if big is None or big.dtype != np.uint16:
            raise IOError(f"bad render {src}")
        lin = io.decode_srgb16(big)  # BGR order is kept throughout
        _write(p["pinhole_out"], io.encode_srgb8(crop_pinhole(lin, p["margins"], p["W"], p["H"], p["ss"])), PNG_FLAGS)
        if p.get("distorted_out"):
            _write(p["distorted_out"], io.encode_srgb8(distort_image(lin, p["map_path"])), PNG_FLAGS)
        os.remove(src)
    elif kind == "aux":
        a = read_exr(src)  # B, G, R = 0, pass index, z
        z = np.ascontiguousarray(a[..., 2], dtype=np.float32)
        idx = a[..., 1]
        _write(p["depth_out"], z, EXR_FLAGS)
        _write(p["mask_out"], np.where(idx > 0.5, 255, 0).astype(np.uint8), PNG_FLAGS)
        os.remove(src)
    elif kind in ("markers", "clock"):
        pass  # kept as-is for validation
    else:
        raise ValueError(kind)
    return job["id"]
