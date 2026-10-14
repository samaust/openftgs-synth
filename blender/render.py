# SPDX-License-Identifier: GPL-3.0-or-later
"""Render a list of jobs from a built scene.

  blender -b scene.blend --factory-startup --python-exit-code 1 -P blender/render.py -- jobs.json

Job kinds:
  rgb      oversized 2x pinhole colour render, 16-bit PNG, view transform Standard
  bg       like rgb with the dynamic collection hidden
  aux      1x pinhole, 1 sample at the pixel centre, material override -> EXR (z-depth, pass index)
  markers  oversized 2x render of the marker collection alone, linear float EXR
  clock    oversized 2x render of the clock marker alone, linear float EXR
After each job, prints a line "JOBDONE <id>".
"""
import json
import math
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy  # noqa: E402
from mathutils import Matrix  # noqa: E402

import lib  # noqa: E402


def setup_device():
    prefs = bpy.context.preferences.addons["cycles"].preferences
    prefs.compute_device_type = "OPTIX"
    prefs.get_devices()
    n = 0
    for d in prefs.devices:
        d.use = d.type == "OPTIX"
        n += d.use
    if n == 0:
        raise RuntimeError("no OptiX device")
    bpy.context.scene.cycles.device = "GPU"


def common_settings(r):
    sc = bpy.context.scene
    cy = sc.cycles
    sc.render.engine = "CYCLES"
    sc.render.use_persistent_data = os.environ.get("OPENFTGS_PERSISTENT", "1") == "1"
    sc.render.use_motion_blur = False
    sc.render.film_transparent = False
    sc.render.dither_intensity = 0.0
    sc.render.resolution_percentage = 100
    sc.render.pixel_aspect_x = sc.render.pixel_aspect_y = 1.0
    sc.render.use_border = False
    cy.use_adaptive_sampling = False
    cy.use_animated_seed = False
    cy.seed = int(r.get("seed", 0))
    cy.rolling_shutter_type = "NONE"
    cy.film_exposure = 1.0
    cy.max_bounces = r.get("max_bounces", 8)
    cy.diffuse_bounces = r.get("diffuse_bounces", 4)
    cy.glossy_bounces = r.get("glossy_bounces", 4)
    cy.transmission_bounces = 8
    cy.transparent_max_bounces = 8
    cy.sample_clamp_direct = 0.0
    cy.sample_clamp_indirect = r.get("clamp_indirect", 10.0)
    cy.caustics_reflective = cy.caustics_refractive = False
    cy.use_guiding = False
    vs = sc.view_settings
    sc.display_settings.display_device = "sRGB"
    vs.view_transform = "Standard"
    vs.look = "None"
    vs.exposure = 0.0
    vs.gamma = 1.0
    vs.use_curve_mapping = False
    sc.render.use_compositing = False
    sc.render.use_sequencer = False


class Configurator:
    def __init__(self, spec):
        self.spec = spec
        self.r = spec["render"]
        self.kind = None
        sc = bpy.context.scene
        self.main_world = sc.world
        self.black = lib.black_world()
        self.aux_mat = lib.aux_material()
        self.coll = {c.name: c for c in bpy.data.collections if c.name in lib.COLLECTIONS}

    def visible(self, names):
        for n, c in self.coll.items():
            c.hide_render = n not in names

    def apply(self, kind):
        if kind == self.kind:
            return
        sc = bpy.context.scene
        cy = sc.cycles
        vl = sc.view_layers[0]
        im = sc.render.image_settings
        if kind in ("rgb", "bg"):
            self.visible({"static", "dynamic", "lights"} if kind == "rgb" else {"static", "lights"})
            sc.world = self.main_world
            vl.material_override = None
            cy.samples = int(self.r["samples"])
            cy.use_denoising = bool(self.r.get("denoise", True))
            cy.denoiser = "OPENIMAGEDENOISE"
            cy.denoising_input_passes = "RGB_ALBEDO_NORMAL"
            cy.denoising_prefilter = "ACCURATE"
            cy.denoising_quality = "HIGH"
            cy.denoising_use_gpu = bool(self.r.get("denoise_gpu", True))
            cy.pixel_filter_type = "BLACKMAN_HARRIS"
            cy.filter_width = 1.5
            cy.use_pixel_jitter = False  # 5.2 default; True was measured to displace the image by up to ~1 px
            im.file_format = "PNG"
            im.color_mode = "RGB"
            im.color_depth = "16"
            im.compression = 15
        elif kind == "aux":
            self.visible({"static", "dynamic"})
            sc.world = self.black
            vl.material_override = self.aux_mat
            cy.samples = 1
            cy.use_denoising = False
            cy.pixel_filter_type = "BOX"
            cy.filter_width = 0.01
            cy.use_pixel_jitter = False
            im.file_format = "OPEN_EXR"
            im.color_mode = "RGB"
            im.color_depth = "32"
            im.exr_codec = "ZIP"
        elif kind in ("markers", "clock"):
            self.visible({kind})
            sc.world = self.black
            vl.material_override = None
            cy.samples = int(self.r.get("marker_samples", 512))
            cy.use_denoising = False
            cy.pixel_filter_type = "BLACKMAN_HARRIS"
            cy.filter_width = 1.5
            cy.use_pixel_jitter = False  # 5.2 default; True was measured to displace the image by up to ~1 px
            im.file_format = "OPEN_EXR"
            im.color_mode = "RGB"
            im.color_depth = "32"
            im.exr_codec = "ZIP"
        else:
            raise ValueError(kind)
        self.kind = kind


def make_cameras(spec):
    cams = []
    for c in spec["cameras"]:
        cd = bpy.data.cameras.new("cam_" + c["name"])
        cd.type = "PERSP"
        cd.sensor_fit = "HORIZONTAL"
        cd.sensor_width = 36.0
        cd.clip_start = 0.02
        cd.clip_end = 1000.0
        cd.dof.use_dof = False
        o = bpy.data.objects.new("cam_" + c["name"], cd)
        bpy.context.scene.collection.objects.link(o)
        o.matrix_world = Matrix(c["matrix_world"])
        cams.append((o, c))
    return cams


def set_camera(obj, params):
    sc = bpy.context.scene
    cd = obj.data
    cd.lens = params["lens"]
    cd.sensor_width = params["sensor_width"]
    cd.shift_x = params["shift_x"]
    cd.shift_y = params["shift_y"]
    sc.render.resolution_x, sc.render.resolution_y = params["resolution"]
    sc.camera = obj


def main():
    spec = json.load(open(sys.argv[sys.argv.index("--") + 1]))
    sc = bpy.context.scene
    setup_device()
    common_settings(spec["render"])
    conf = Configurator(spec)
    cams = make_cameras(spec)
    for job in spec["jobs"]:
        conf.apply(job["kind"])
        obj, c = cams[job["cam"]]
        set_camera(obj, c["aux"] if job["kind"] == "aux" else c["big"])
        F = job["frame"]
        fi = math.floor(F)
        sc.frame_set(fi, subframe=F - fi)
        os.makedirs(os.path.dirname(job["out"]), exist_ok=True)
        sc.render.filepath = job["out"]
        sc.render.use_file_extension = False
        t0 = time.time()
        bpy.ops.render.render(write_still=not os.environ.get("OPENFTGS_NOSAVE"))
        print("JOBDONE", job["id"], f"{time.time() - t0:.3f}", flush=True)
    print("RENDER_OK", flush=True)


if __name__ == "__main__":
    main()
