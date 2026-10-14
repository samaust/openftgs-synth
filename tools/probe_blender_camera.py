# SPDX-License-Identifier: GPL-3.0-or-later
"""Measure Blender's pinhole model and depth semantics instead of assuming them.

Renders grids of small emissive spheres with known positions for several (resolution,
focal, lens shift) settings, fits f, cx, cy from intensity-weighted centroids, and renders
a tilted plane with the Camera Data "View Z Depth" output to confirm planar z-depth.

  .venv/bin/python tools/probe_blender_camera.py            (runs Blender itself)
"""
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))

BLENDER_SIDE = r'''
import bpy, sys, json
from mathutils import Matrix
a = sys.argv[sys.argv.index('--')+1:]
W, H, f, sx, sy, out, mode = int(a[0]), int(a[1]), float(a[2]), float(a[3]), float(a[4]), a[5], a[6]
bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene; sc.render.engine = 'CYCLES'
p = bpy.context.preferences.addons['cycles'].preferences; p.compute_device_type = 'OPTIX'; p.get_devices()
for d in p.devices: d.use = d.type == 'OPTIX'
sc.cycles.device = 'GPU'; sc.cycles.use_adaptive_sampling = False; sc.cycles.use_denoising = False
sc.cycles.samples = 1024 if mode == 'markers' else 1
if mode != 'markers': sc.cycles.pixel_filter_type = 'BOX'; sc.cycles.filter_width = 0.01
sc.render.resolution_x, sc.render.resolution_y, sc.render.resolution_percentage = W, H, 100
im = sc.render.image_settings; im.file_format = 'OPEN_EXR'; im.color_depth = '32'; im.color_mode = 'RGB'
sc.render.filepath = out; sc.render.use_file_extension = False
w = bpy.data.worlds.new('w'); sc.world = w
w.node_tree.nodes['Background'].inputs[1].default_value = 0
cd = bpy.data.cameras.new('c'); cd.sensor_fit = 'HORIZONTAL'; cd.sensor_width = 36.0
cd.lens = f / W * 36.0; cd.shift_x = sx; cd.shift_y = sy
cam = bpy.data.objects.new('c', cd); sc.collection.objects.link(cam); sc.camera = cam
cam.matrix_world = Matrix.Identity(4)
m = bpy.data.materials.new('e'); nt = m.node_tree; nt.nodes.clear()
o = nt.nodes.new('ShaderNodeOutputMaterial'); e = nt.nodes.new('ShaderNodeEmission')
if mode != 'markers':
    c = nt.nodes.new('ShaderNodeCameraData'); xyz = nt.nodes.new('ShaderNodeCombineXYZ')
    nt.links.new(c.outputs['View Z Depth'], xyz.inputs['X']); nt.links.new(xyz.outputs[0], e.inputs['Color'])
nt.links.new(e.outputs[0], o.inputs['Surface'])
pts = []
if mode == 'markers':
    for i in range(-4, 5):
        for j in range(-3, 4):
            q = (i * 0.45 + 0.07 * j, j * 0.45 + 0.03 * i, -(5.0 + 0.2 * i))
            bpy.ops.mesh.primitive_uv_sphere_add(segments=64, ring_count=32, radius=0.02, location=q)
            bpy.context.active_object.data.materials.append(m); pts.append(q)
else:
    bpy.ops.mesh.primitive_plane_add(size=40, location=(0, 0, -6), rotation=(0.5, 0.3, 0))
    ob = bpy.context.active_object; ob.data.materials.append(m)
    pts = [list(ob.matrix_world.col[3][:3]), list(ob.matrix_world.col[2][:3])]
bpy.ops.render.render(write_still=True)
json.dump({'pts': pts}, open(out + '.json', 'w'))
'''


def main():
    os.environ.setdefault("OPENCV_IO_ENABLE_OPENEXR", "1")
    import cv2
    import numpy as np
    from synth.pipeline import BLENDER
    tmp = tempfile.mkdtemp(prefix="probe_")
    script = os.path.join(tmp, "probe_side.py")
    open(script, "w").write(BLENDER_SIDE)
    ok = True
    for W, H, f, sx, sy in [(320, 240, 300, 0, 0), (320, 240, 300, 0.05, 0.03), (320, 180, 250, -0.04, 0.02)]:
        out = os.path.join(tmp, f"m_{W}_{sx}_{sy}.exr")
        subprocess.run([BLENDER, "-b", "--factory-startup", "-P", script, "--", str(W), str(H), str(f), str(sx), str(sy),
                        out, "markers"], check=True, capture_output=True)
        I = cv2.imread(out, cv2.IMREAD_UNCHANGED).mean(-1).astype(np.float64)
        P = np.array(json.load(open(out + ".json"))["pts"]) * [1, -1, -1]  # Blender camera -> OpenCV axes
        cx, cy = W / 2 - sx * W - 0.5, H / 2 + sy * W - 0.5  # hypothesis, OpenCV convention
        uv = P[:, :2] / P[:, 2:] * f + [cx, cy]
        errs = []
        yy, xx = np.mgrid[:H, :W]
        for p in uv:
            u0, v0 = int(round(p[0])), int(round(p[1]))
            if not (6 <= u0 < W - 6 and 6 <= v0 < H - 6):
                continue
            win = I[v0 - 5: v0 + 6, u0 - 5: u0 + 6]
            c = np.array([(win * xx[v0 - 5: v0 + 6, u0 - 5: u0 + 6]).sum(), (win * yy[v0 - 5: v0 + 6, u0 - 5: u0 + 6]).sum()]) / win.sum()
            errs.append(np.linalg.norm(c - p))
        e = max(errs)
        ok &= e < 0.02
        print(f"W={W} H={H} f={f} shift=({sx},{sy}): {len(errs)} markers, max |centroid - model| = {e:.4f} px")
    out = os.path.join(tmp, "depth.exr")
    subprocess.run([BLENDER, "-b", "--factory-startup", "-P", script, "--", "320", "240", "300", "0.05", "0.03", out, "depth"],
                   check=True, capture_output=True)
    d = cv2.imread(out, cv2.IMREAD_UNCHANGED)[..., 2]
    meta = json.load(open(out + ".json"))
    o, n = np.array(meta["pts"][0]) * [1, -1, -1], np.array(meta["pts"][1]) * [1, -1, -1]
    u, v = np.meshgrid(np.arange(320) + 0.5, np.arange(240) + 0.5)
    ray = np.stack([(u - (160 - 0.05 * 320)) / 300, (v - (120 + 0.03 * 320)) / 300, np.ones_like(u)], -1)
    z = (o @ n) / (ray @ n)
    e = float(np.abs(d - z).max())
    ok &= e < 1e-4
    print(f"View Z Depth vs analytic planar z: max error {e:.2e} m")
    print("PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
