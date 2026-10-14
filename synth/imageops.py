# SPDX-License-Identifier: GPL-3.0-or-later
"""Image operations: sRGB transfer, 2x box downsampling, bilinear warps."""
import numpy as np


def srgb_to_linear(v):
    v = np.asarray(v, np.float64)
    return np.where(v <= 0.04045, v / 12.92, ((v + 0.055) / 1.055) ** 2.4)


def linear_to_srgb(v):
    v = np.clip(v, 0.0, 1.0)
    return np.where(v <= 0.0031308, 12.92 * v, 1.055 * np.power(v, 1 / 2.4) - 0.055)


_LUT16 = None


def decode_srgb16(img_u16):
    """uint16 sRGB-encoded image -> float32 linear."""
    global _LUT16
    if _LUT16 is None:
        _LUT16 = srgb_to_linear(np.arange(65536) / 65535.0).astype(np.float32)
    return _LUT16[img_u16]


def encode_srgb8(lin):
    """float linear -> uint8 sRGB (round to nearest)."""
    return np.round(linear_to_srgb(lin.astype(np.float32)) * 255.0).astype(np.uint8)


def box2(img):
    """2x2 box downsample, float32."""
    H, W = img.shape[0] // 2, img.shape[1] // 2
    sh = (H, 2, W, 2) + img.shape[2:]
    return img[: 2 * H, : 2 * W].reshape(sh).mean(axis=(1, 3), dtype=np.float32)


class BilinearMap:
    """Precomputed bilinear sampling of a source image at continuous pixel coordinates
    (U, V) (continuous convention: source pixel (i, j) has its centre at (i + 0.5, j + 0.5))."""

    def __init__(self, U, V, src_w, src_h):
        x = np.asarray(U, np.float64) - 0.5
        y = np.asarray(V, np.float64) - 0.5
        if x.min() < 0 or y.min() < 0 or x.max() > src_w - 1 or y.max() > src_h - 1:
            raise ValueError("sample positions fall outside the source image")
        x0 = np.minimum(np.floor(x).astype(np.int64), src_w - 2)
        y0 = np.minimum(np.floor(y).astype(np.int64), src_h - 2)
        self.shape = U.shape
        self.src = (src_h, src_w)
        self.idx = (y0 * src_w + x0).reshape(-1)
        self.wx = (x - x0).reshape(-1, 1).astype(np.float32)
        self.wy = (y - y0).reshape(-1, 1).astype(np.float32)

    def __call__(self, img):
        h, w = self.src
        assert img.shape[:2] == (h, w)
        flat = img.reshape(h * w, -1)
        i = self.idx
        top = flat[i] * (1 - self.wx) + flat[i + 1] * self.wx
        bot = flat[i + w] * (1 - self.wx) + flat[i + w + 1] * self.wx
        out = top * (1 - self.wy) + bot * self.wy
        return out.reshape(self.shape + img.shape[2:])

    def save(self, path):
        np.savez(path, idx=self.idx, wx=self.wx, wy=self.wy, shape=np.array(self.shape), src=np.array(self.src))

    @classmethod
    def load(cls, path):
        z = np.load(path)
        m = cls.__new__(cls)
        m.idx, m.wx, m.wy = z["idx"], z["wx"], z["wy"]
        m.shape, m.src = tuple(z["shape"]), tuple(z["src"])
        return m
