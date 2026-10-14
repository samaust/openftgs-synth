# SPDX-License-Identifier: GPL-3.0-or-later
"""tiny: a small room corner with every scene ingredient, for end-to-end smoke tests."""
import math

import lib


def build(ctx):
    lib.hdri_world(ctx, "comfy_cafe", strength=0.7, rot_z_deg=40)
    lib.light(ctx, "sun", "SUN", (0, 0, 5), rotation=(math.radians(40), 0, math.radians(-35)), energy=2.5, angle_deg=3)
    lib.light(ctx, "fill", "AREA", (1.5, -2.5, 3.0), rotation=(math.radians(50), 0, math.radians(30)), energy=300, size=2)

    floor = lib.pbr(ctx, "floor", "cobblestone_floor_04", scale=0.6)
    brick = lib.pbr(ctx, "brick", "brick_wall_001", scale=0.5)
    plaster = lib.pbr(ctx, "plaster", "plaster_brick_01", scale=0.5)
    wood = lib.pbr(ctx, "wood", "kitchen_wood", scale=1.0)
    metal = lib.solid("metal", (0.6, 0.6, 0.62), roughness=0.35, metallic=1.0)

    lib.plane(ctx, "floor", (9, 9), (0, 0.5, 0), mat=floor)
    lib.box(ctx, "wall_back", (9, 0.1, 3.2), (0, 2.05, 1.6), mat=brick)
    lib.box(ctx, "wall_left", (0.1, 4.5, 3.2), (-2.65, -0.2, 1.6), mat=plaster)
    lib.box(ctx, "wall_right", (0.1, 4.5, 3.2), (2.65, -0.2, 1.6), mat=plaster)

    # low table with thin legs
    lib.box(ctx, "table_top", (1.2, 0.7, 0.04), (0, 0.55, 0.45), mat=wood, bevel=0.005)
    for sx in (-1, 1):
        for sy in (-1, 1):
            lib.rod(ctx, "table_leg", (sx * 0.55, 0.55 + sy * 0.3, 0), (sx * 0.55, 0.55 + sy * 0.3, 0.43), 0.012, mat=metal)
    lib.import_gltf(ctx, "wooden_crate_01", location=(-1.7, 1.4, 0), rot_z_deg=20)
    lib.import_gltf(ctx, "potted_plant_01", location=(1.8, 1.5, 0), rot_z_deg=0)
    lib.import_gltf(ctx, "ceramic_vase_01", location=(0.35, 0.7, 0.47))

    # thin structures: a wire grid panel (3 mm wires)
    for i in range(9):
        x = 0.9 + i * 0.1
        lib.rod(ctx, "wire_v", (x, 1.2, 0.0), (x, 1.2, 1.3), 0.003, mat=metal)
    for j in range(7):
        z = 0.1 + j * 0.2
        lib.rod(ctx, "wire_h", (0.85, 1.2, z), (1.75, 1.2, z), 0.003, mat=metal)

    T = ctx.duration
    tA, tB = ctx.t_of(ctx.frame_start), ctx.t_of(ctx.frame_end)

    # rigid movers (different speeds)
    cube = lib.box(ctx, "mover_cube", (0.18, 0.18, 0.18), (0, 0, 0), mat=lib.checker("chk1", (0.9, 0.2, 0.1), (0.95, 0.9, 0.8), 8), coll="dynamic")
    lib.make_dynamic(ctx, cube)
    lib.keyframe_path(ctx, cube, lambda t: ((-0.4 + 0.25 * t, 0.5, 0.56), (0, 0, 40 * t)), tA, tB, 1 / ctx.fps)
    ball = lib.sphere(ctx, "mover_ball", 0.14, (0, 0, 0), mat=lib.checker("chk2", (0.1, 0.3, 0.9), (0.9, 0.9, 0.2), 6), coll="dynamic")
    lib.make_dynamic(ctx, ball)
    lib.keyframe_path(ctx, ball, lambda t: ((-1.2 + 1.0 * t, 0.0, 0.14), (0, math.degrees(1.0 * t / 0.14), 0)), tA, tB, 1 / ctx.fps)

    # fast burst: a torus that whips across and spins quickly for frames 1..10
    tor = lib.torus(ctx, "burst_torus", 0.12, 0.035, (0, 0, 0), mat=lib.checker("chk3", (0.1, 0.8, 0.3), (0.1, 0.1, 0.1), 12), coll="dynamic")
    lib.make_dynamic(ctx, tor)
    b0, b1 = 1 / ctx.fps, 11 / ctx.fps

    def burst(t):
        if t < b0:
            s = t * 0.1
        elif t < b1:
            s = b0 * 0.1 + (t - b0) * 2.0
        else:
            s = b0 * 0.1 + (b1 - b0) * 2.0 + (t - b1) * 0.1
        spin = 30 * t if t < b0 else 30 * b0 + 1500 * (min(t, b1) - b0) + 30 * max(0, t - b1)
        return (0.6 + 0.3 * s, -0.2 + 0.5 * s, 1.0 + 0.2 * s), (spin * 0.3, spin, 0)
    lib.keyframe_path(ctx, tor, burst, tA, tB, 1 / ctx.fps)

    # appears at frame 3, disappears at frame 9
    cn = lib.cone(ctx, "appear_cone", 0.12, 0.3, (-0.7, 0.2, 0.15), mat=lib.checker("chk4", (0.9, 0.5, 0.1), (0.2, 0.1, 0.4), 10), coll="dynamic")
    lib.make_dynamic(ctx, cn)
    lib.keyframe_path(ctx, cn, lambda t: ((-0.7, 0.2, 0.15), (0, 0, 90 * t)), tA, tB, 1 / ctx.fps)
    lib.visibility_window(ctx, cn, 3 / ctx.fps, 9 / ctx.fps)

    # cloth flag on a thin bar, blown by wind
    lib.rod(ctx, "flag_bar", (-1.35, 0.9, 1.45), (-0.65, 0.9, 1.45), 0.008, mat=metal)
    lib.rod(ctx, "flag_post", (-1.35, 0.9, 0.0), (-1.35, 0.9, 1.45), 0.012, mat=metal)
    lib.cloth_sheet(ctx, "cloth_flag", (0.62, 0.5), (24, 20), (-1.0, 0.9, 1.2), (math.radians(90), 0, 0),
                    lib.pbr(ctx, "fabric", "fabric_pattern_07", scale=3.0), pin="top")
    lib.wind(ctx, "wind", (-1.0, -1.0, 1.2), (90, 0, 20), strength=250.0, noise=1.0, seed=7, gust_period=0.25)
    lib.turbulence(ctx, "turb", (-1.0, 0.9, 1.2), strength=20.0, size=0.3)

    # person walking behind the table
    lib.character(ctx, "quaternius_animated_human", 1.72,
                  lambda t: ((-1.6 + 1.1 * t, 1.55, 0.0), 90.0), tA, tB, 1 / ctx.fps, clip="Walk")
