<!-- SPDX-License-Identifier: GPL-3.0-or-later -->
# openftgs-synth

Generator of rendered multi-view video datasets with exact ground truth, used to validate
openftgs (an Apache-2.0 clean-room implementation of FreeTimeGS) without any dataset
licensed for non-commercial use.

- **Code license:** GPL-3.0-or-later (the Blender scripts import `bpy`). See `LICENSE`.
- **Rendered data license:** CC0-1.0 (`dataset/LICENSE`, copied into the dataset root).
- **Assets:** CC0 only, listed with checksums in `ASSETS.md`. Sources consulted are in
  `SOURCES.md`.
- **Data never goes into git.** Renders go to `~/datasets/openftgs-synth/`, intermediates to
  `~/datasets/openftgs-synth-work/` and assets to `~/datasets/openftgs-synth-assets/`.

## Requirements (pinned)

| Tool | Version | Notes |
| --- | --- | --- |
| Blender | **5.2.2 LTS**, official tarball `blender-5.2.2-linux-x64.tar.xz` from https://download.blender.org/release/Blender5.2/ | SHA-256 `84098912789dc450e95697c4184fb8a90acbe5111c2ba4aede3fecb57806a168`. Unpacked to `~/opt/blender-5.2.2-linux-x64/`; override with `OPENFTGS_SYNTH_BLENDER`. Cycles on the GPU with OptiX. |
| Python venv | `requirements.txt` | numpy, opencv-python-headless 4.14 (Apache-2.0; the 5.0 wheels lack OpenEXR), PyYAML |
| ffmpeg / ffprobe | system 6.1 | used as separate programs |

```sh
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python tools/fetch_assets.py          # downloads + verifies every CC0 asset
.venv/bin/python -m tests.test_conventions      # convention unit tests (no renders)
.venv/bin/python tools/probe_blender_camera.py  # measures Blender's camera model and depth
```

## Running

```sh
# one scene: build (scene + baked cloth) -> render (streamed post-processing + encoding) -> package
.venv/bin/python tools/run_scene.py configs/tiny.yaml build render package
# one-frame timing and disk estimate for a scene (no full render)
.venv/bin/python tools/run_scene.py configs/kitchen.yaml build time
# validation (checks 1-6 + ffprobe), then dataset-level files and SHA256SUMS
.venv/bin/python validate/run_all.py configs/*.yaml
.venv/bin/python tools/finalize_dataset.py configs/*.yaml
.venv/bin/python validate/run_all.py --sha256sums
```

`render` is resumable: finished jobs and encodes are logged in `<work>/<scene>/done.txt`.
It runs one Blender process per camera.

## Layout of the code

| Path | What |
| --- | --- |
| `configs/*.yaml` | one file per scene: rig design, lens, timing, layouts, markers, render settings |
| `blender/` | bpy side: `build.py` (scene build + cloth bake), `render.py` (job runner), `lib.py` (helpers), `scenes/*.py` (one builder per scene) |
| `synth/` | venv side: camera conventions, rigs, distortion and its inverse, image ops, post-processing, encoding, packaging |
| `validate/` | the six release checks |
| `tools/` | CLI, asset fetcher, probes, timing, finalizer |
| `dataset/` | dataset LICENSE (CC0 text), VERSION, card template, decision notes |

## Conventions (measured, and tested by `validate/`)

- World right-handed, metres, z up. Cameras in OpenCV axes (x right, y down, z forward),
  world-to-camera `x_cam = R x + t`, centre `-R^T t`. The Blender camera matrix is
  `R^T diag(1, -1, -1)`.
- Blender 5.2 pinhole, measured by `tools/probe_blender_camera.py`: `f = lens/36 * W`
  (horizontal sensor fit), `cx = W/2 - shift_x W`, `cy = H/2 + shift_y W` in continuous pixels.
  Cycles samples pixel (i, j) around (i + 0.5, j + 0.5).
- `cycles.use_pixel_jitter` stays False (its 5.2 default). True displaced markers by up to
  about 1 px.
- Keys inserted from Python ignore the interpolation preference in 5.2, so interpolation is
  set on each key.
- Determinism: fixed samples, seed, no adaptive sampling, dithering 0. The OIDN denoiser
  runs on the CPU. A repeated render then differs by at most 1/65535 in 16 bit; with GPU
  OIDN it differs by up to 115/65535 (`tools/determinism_check.py`).
