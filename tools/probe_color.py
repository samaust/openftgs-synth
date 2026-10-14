# SPDX-License-Identifier: GPL-3.0-or-later
"""Check that the colour render path is the plain sRGB 'Standard' transform: a flat linear
emission of 0.5 must come out as sRGB(0.5) = 0.735357 -> 48192.6 / 65535 in the 16-bit PNG,
and 0.18 -> 0.461356 -> 30235.0. Uses blender/render.py's own settings code.

  .venv/bin/python tools/probe_color.py
"""
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))

SIDE = r'''
import bpy, sys, os
sys.path.insert(0, os.path.join(sys.argv[sys.argv.index('--') + 2], 'blender'))
import render as R, lib
out, val = sys.argv[sys.argv.index('--') + 1], float(sys.argv[sys.argv.index('--') + 3])
bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
R.setup_device()
R.common_settings({"samples": 4})
sc.world = lib.black_world()
sc.cycles.samples = 4; sc.cycles.use_denoising = False
sc.render.resolution_x, sc.render.resolution_y = 64, 48
im = sc.render.image_settings; im.file_format = 'PNG'; im.color_mode = 'RGB'; im.color_depth = '16'
m = lib.emission('e', (val, val, val), 1.0)
bpy.ops.mesh.primitive_plane_add(size=50, location=(0, 0, -5)); bpy.context.active_object.data.materials.append(m)
cd = bpy.data.cameras.new('c'); o = bpy.data.objects.new('c', cd); sc.collection.objects.link(o); sc.camera = o
sc.render.filepath = out; sc.render.use_file_extension = False
bpy.ops.render.render(write_still=True)
'''


def main():
    import cv2
    from synth.imageops import linear_to_srgb
    from synth.pipeline import BLENDER, REPO
    tmp = tempfile.mkdtemp(prefix="color_")
    side = os.path.join(tmp, "side.py")
    open(side, "w").write(SIDE)
    ok = True
    for val in (0.5, 0.18, 0.02):
        out = os.path.join(tmp, f"c{val}.png")
        subprocess.run([BLENDER, "-b", "--factory-startup", "-P", side, "--", out, REPO, str(val)], check=True,
                       capture_output=True)
        img = cv2.imread(out, cv2.IMREAD_UNCHANGED)
        got = float(img[10:-10, 10:-10].mean())
        exp = float(linear_to_srgb(val)) * 65535
        ok &= abs(got - exp) < 3
        print(f"linear {val}: PNG16 {got:.1f}, expected sRGB {exp:.1f}")
    print("PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
