# SPDX-License-Identifier: GPL-3.0-or-later
"""kitchen: a table in front of a kitchen counter, seen by a forward-facing arc.

Layout (metres): table centred at (0, 0.3), counter along the back wall (y = 2.2),
cameras on the -y side looking at the table.
"""
import math

import lib


def _burst_profile(t, t0, t1, slow, fast):
    """Distance travelled at speed `slow`, except `fast` during [t0, t1)."""
    if t < t0:
        return slow * t
    if t < t1:
        return slow * t0 + fast * (t - t0)
    return slow * t0 + fast * (t1 - t0) + slow * (t - t1)


def build(ctx):
    fps = ctx.fps
    tA, tB = ctx.t_of(ctx.frame_start), ctx.t_of(ctx.frame_end)
    step = 1 / fps
    lib.hdri_world(ctx, "comfy_cafe", strength=0.6, rot_z_deg=120)
    lib.light(ctx, "key", "AREA", (0.4, -0.6, 2.6), rotation=(math.radians(15), 0, 0), energy=260, size=1.4,
              color=(1.0, 0.93, 0.85))
    lib.light(ctx, "fill", "AREA", (-2.0, -2.2, 2.2), rotation=(math.radians(55), 0, math.radians(-40)),
              energy=180, size=2.0)
    lib.light(ctx, "rim", "AREA", (2.2, 1.0, 2.5), rotation=(math.radians(40), 0, math.radians(120)), energy=120, size=1.0)

    floor = lib.pbr(ctx, "floor", "brown_floor_tiles", scale=0.7)
    wall = lib.pbr(ctx, "wall", "painted_plaster_wall", scale=0.5)
    tiles = lib.pbr(ctx, "backsplash", "floor_tiles_06", scale=1.2)
    wood = lib.pbr(ctx, "wood", "kitchen_wood", scale=0.8)
    dark = lib.pbr(ctx, "darkwood", "dark_wooden_planks", scale=0.8)
    metal = lib.solid("steel", (0.62, 0.62, 0.64), roughness=0.3, metallic=1.0)
    black = lib.solid("black_metal", (0.03, 0.03, 0.03), roughness=0.4, metallic=0.8)

    # room
    lib.plane(ctx, "floor", (9, 8), (0, 0.2, 0), mat=floor)
    lib.box(ctx, "wall_back", (7, 0.1, 3.0), (0, 2.3, 1.5), mat=wall)
    lib.box(ctx, "wall_left", (0.1, 5.0, 3.0), (-3.0, 0.0, 1.5), mat=wall)
    lib.box(ctx, "wall_right", (0.1, 5.0, 3.0), (3.0, 0.0, 1.5), mat=wall)
    lib.box(ctx, "backsplash", (4.2, 0.02, 0.62), (0, 2.24, 1.22), mat=tiles)
    # counter and cabinets
    lib.box(ctx, "counter_base", (4.2, 0.6, 0.86), (0, 1.95, 0.43), mat=dark, bevel=0.004)
    lib.box(ctx, "counter_top", (4.3, 0.64, 0.04), (0, 1.94, 0.88), mat=wood, bevel=0.003)
    lib.box(ctx, "upper_cabinets", (4.2, 0.36, 0.7), (0, 2.07, 1.95), mat=dark, bevel=0.004)
    for i in range(6):  # cabinet door gaps and thin handles
        x = -1.75 + i * 0.7
        lib.rod(ctx, "handle", (x + 0.25, 1.64, 0.62), (x + 0.25, 1.64, 0.78), 0.006, mat=metal)
        lib.rod(ctx, "handle_up", (x + 0.25, 1.88, 1.66), (x + 0.25, 1.88, 1.8), 0.006, mat=metal)

    # table with chairs
    lib.box(ctx, "table_top", (1.6, 0.9, 0.04), (0, 0.3, 0.76), mat=wood, bevel=0.005)
    for sx in (-1, 1):
        for sy in (-1, 1):
            lib.box(ctx, "table_leg", (0.05, 0.05, 0.74), (sx * 0.72, 0.3 + sy * 0.38, 0.37), mat=dark)
    lib.import_gltf(ctx, "dining_chair_02", location=(-1.1, 0.35, 0), rot_z_deg=-90)
    lib.import_gltf(ctx, "dining_chair_02", location=(1.1, 0.25, 0), rot_z_deg=90)

    # props
    lib.import_gltf(ctx, "vintage_electric_kettle", location=(-1.2, 1.9, 0.9), rot_z_deg=200)
    lib.import_gltf(ctx, "ceramic_vase_01", location=(1.5, 1.95, 0.9))
    lib.import_gltf(ctx, "potted_plant_01", location=(-2.4, 1.6, 0), rot_z_deg=30)
    lib.import_gltf(ctx, "wooden_bowl_01", location=(0.45, 0.45, 0.78))

    # thin structures: dish rack (4 mm wires) on the counter, utensil rail with hooks
    for i in range(12):
        x = 0.35 + i * 0.035
        lib.rod(ctx, "rack_wire", (x, 1.78, 0.9), (x, 1.78, 1.12), 0.002, mat=metal)
        lib.rod(ctx, "rack_wire_b", (x, 2.02, 0.9), (x, 2.02, 1.05), 0.002, mat=metal)
    for z in (0.92, 1.0):
        lib.rod(ctx, "rack_rail", (0.33, 1.78, z), (0.75, 1.78, z), 0.002, mat=metal)
        lib.rod(ctx, "rack_rail_b", (0.33, 2.02, z), (0.75, 2.02, z), 0.002, mat=metal)
    lib.rod(ctx, "utensil_rail", (-1.9, 2.22, 1.6), (-0.4, 2.22, 1.6), 0.005, mat=metal)
    for i in range(7):
        x = -1.8 + i * 0.22
        lib.rod(ctx, "hook", (x, 2.22, 1.6), (x, 2.18, 1.42), 0.0025, mat=metal)

    # ---------------- dynamic objects
    chk = lib.checker
    # slow sliding mug-like cylinder
    mug = lib.cylinder(ctx, "mover_mug", 0.045, 0.1, (0, 0, 0), mat=chk("c_mug", (0.85, 0.85, 0.8), (0.2, 0.35, 0.7), 18),
                       coll="dynamic")
    lib.make_dynamic(ctx, mug)
    lib.keyframe_path(ctx, mug, lambda t: ((-0.6 + 0.08 * t, 0.15 + 0.02 * t, 0.83), (0, 0, 15 * t)), tA, tB, step)
    # apple-like ball rolling back and forth across the table (medium speed)
    ball = lib.sphere(ctx, "mover_ball", 0.045, (0, 0, 0), mat=chk("c_ball", (0.8, 0.1, 0.1), (0.95, 0.75, 0.2), 8),
                      coll="dynamic")
    lib.make_dynamic(ctx, ball)

    def ball_path(t):
        x = 0.55 * math.sin(2 * math.pi * t / 6.0)
        return (x, 0.5, 0.825), (0, math.degrees(x / 0.045), 0)
    lib.keyframe_path(ctx, ball, ball_path, tA, tB, step)
    # spinning top (fast steady rotation, slow precession)
    top = lib.cone(ctx, "mover_top", 0.05, 0.08, (0, 0, 0), rotation=(math.pi, 0, 0),
                   mat=chk("c_top", (0.1, 0.6, 0.2), (0.9, 0.9, 0.9), 14), coll="dynamic")
    lib.make_dynamic(ctx, top)
    lib.keyframe_path(ctx, top, lambda t: ((0.15 + 0.05 * math.cos(t), 0.05 + 0.05 * math.sin(t), 0.82),
                                           (6 * math.sin(2 * t), 6 * math.cos(2 * t), 720 * t)), tA, tB, step)
    # burst: a whisk (thin wires) that sweeps quickly across the table for 15 frames
    wires = []
    for k in range(8):
        a = k * math.pi / 8
        wires.append(lib.torus(ctx, "whisk_wire", 0.035, 0.0015, (0, 0, 0.07), rotation=(0, math.pi / 2, a), mat=metal,
                               coll="dynamic"))
    wires.append(lib.cylinder(ctx, "whisk_handle", 0.008, 0.14, (0, 0, -0.03), mat=black, coll="dynamic"))
    whisk = lib.join(wires, "burst_whisk")
    lib.make_dynamic(ctx, whisk)
    b0, b1 = 4.0, 4.0 + 15 / fps

    def whisk_path(t):
        s = _burst_profile(t, b0, b1, 0.03, 2.2)
        spin = _burst_profile(t, b0, b1, 20, 1800)
        return (-0.5 + s, -0.02, 0.92), (0, 70, spin)
    lib.keyframe_path(ctx, whisk, whisk_path, tA, tB, step)
    # appears at 2.5 s, drifts, disappears at 7.0 s
    box = lib.box(ctx, "appear_box", (0.12, 0.12, 0.12), (0, 0, 0), mat=chk("c_box", (0.95, 0.55, 0.1), (0.3, 0.1, 0.4), 12),
                  coll="dynamic", bevel=0.004)
    lib.make_dynamic(ctx, box)
    lib.keyframe_path(ctx, box, lambda t: ((0.35 - 0.04 * t, 0.15, 0.84), (0, 0, 25 * t)), tA, tB, step)
    lib.visibility_window(ctx, box, 2.5, 7.0)

    # cloth: kitchen towel hanging from the counter's front bar, stirred by a fan breeze
    lib.rod(ctx, "towel_bar", (-0.9, 1.6, 0.8), (-0.3, 1.6, 0.8), 0.006, mat=metal)
    lib.cloth_sheet(ctx, "cloth_towel", (0.42, 0.55), (22, 28), (-0.6, 1.585, 0.52), (math.radians(90), 0, 0),
                    lib.pbr(ctx, "towel", "fabric_pattern_07", scale=4.0), pin="top")
    lib.wind(ctx, "wind", (-0.6, -0.8, 0.6), (85, 0, 0), strength=160.0, noise=1.0, seed=3, gust_period=0.35)
    lib.turbulence(ctx, "turb", (-0.6, 1.5, 0.5), strength=15.0, size=0.25)

    # person walking along the counter, turning back at 5 s
    def walk(t):
        x0, x1, speed = -2.0, 2.0, 0.85
        tt = (x1 - x0) / speed
        u = max(t, 0.0)
        if u < tt:
            return (x0 + speed * u, 1.25, 0.0), 90.0
        if u < tt + 0.5:
            return (x1, 1.25, 0.0), 90.0 + 180.0 * (u - tt) / 0.5
        if u < 2 * tt + 0.5:
            return (x1 - speed * (u - tt - 0.5), 1.25, 0.0), 270.0
        return (x0, 1.25, 0.0), 270.0 + 180.0 * min(1.0, (u - 2 * tt - 0.5) / 0.5)
    lib.character(ctx, "quaternius_animated_human", 1.74, walk, tA, tB, step, clip="Walk")
