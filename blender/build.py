# SPDX-License-Identifier: GPL-3.0-or-later
"""Build one scene, bake its physics and save it as a .blend.

  blender -b --factory-startup --python-exit-code 1 -P blender/build.py -- build_spec.json
"""
import importlib
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy  # noqa: E402

import lib  # noqa: E402


def main():
    spec = json.load(open(sys.argv[sys.argv.index("--") + 1]))
    ctx = lib.Ctx(spec)
    lib.reset(ctx)
    importlib.import_module("scenes." + spec["builder"]).build(ctx)
    lib.add_markers(ctx, spec["markers"]["points"], spec["markers"]["radius"])
    ck = spec["clock"]
    lib.add_clock(ctx, ck["p0"], ck["velocity"], ck["radius"])
    bpy.context.preferences.edit.keyframe_new_interpolation_type = "BEZIER"
    blend = spec["blend_path"]
    os.makedirs(os.path.dirname(blend), exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=blend)
    lib.bake_physics()
    bpy.ops.wm.save_mainfile(filepath=blend)
    info = {"markers": ctx.markers, "clock": ctx.clock, "dynamic_objects": sorted(ctx.dynamic_names),
            "blender_version": bpy.app.version_string}
    with open(spec["scene_info_path"], "w") as f:
        json.dump(info, f, indent=1)
    print("BUILD_OK", blend)


if __name__ == "__main__":
    main()
