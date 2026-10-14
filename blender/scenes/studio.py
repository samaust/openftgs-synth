# SPDX-License-Identifier: GPL-3.0-or-later
"""studio: a capture stage seen from a full ring of cameras at two heights.

A 14-sided room (inner radius ~6.5 m) with textured walls surrounds a 4 m camera ring.
The action is inside a ~2 m radius around the origin.
"""
import math

import lib


def _burst(t, t0, t1, slow, fast):
    if t < t0:
        return slow * t
    if t < t1:
        return slow * t0 + fast * (t - t0)
    return slow * t0 + fast * (t1 - t0) + slow * (t - t1)


def build(ctx):
    fps = ctx.fps
    tA, tB = ctx.t_of(ctx.frame_start), ctx.t_of(ctx.frame_end)
    step = 1 / fps
    lib.hdri_world(ctx, "brown_photostudio_02", strength=0.5, rot_z_deg=0)
    for k in range(4):
        a = math.radians(45 + 90 * k)
        lib.light(ctx, f"softbox_{k}", "AREA", (2.6 * math.cos(a), 2.6 * math.sin(a), 3.4),
                  rotation=(math.radians(40), 0, a + math.pi / 2), energy=420, size=1.6)
    lib.light(ctx, "top", "AREA", (0, 0, 4.2), energy=500, size=2.5)

    floor = lib.pbr(ctx, "floor", "concrete_floor_01", scale=0.4)
    planks = lib.pbr(ctx, "planks", "dark_wooden_planks", scale=0.5)
    plaster = lib.pbr(ctx, "plaster", "painted_plaster_wall", scale=0.4)
    brick = lib.pbr(ctx, "brick", "brick_wall_001", scale=0.35)
    tiles = lib.pbr(ctx, "tiles", "floor_tiles_06", scale=0.8)
    metal = lib.solid("alu", (0.7, 0.7, 0.72), roughness=0.35, metallic=1.0)
    black = lib.solid("black", (0.02, 0.02, 0.02), roughness=0.5)

    lib.plane(ctx, "floor", (16, 16), (0, 0, 0), mat=floor)
    lib.cylinder(ctx, "stage", 2.1, 0.06, (0, 0, -0.02), mat=lib.pbr(ctx, "stage_wood", "kitchen_wood", scale=0.7),
                 vertices=64)
    # 14 wall panels with alternating materials, so every direction has distinct texture
    N, R = 14, 6.6
    mats = [planks, plaster, brick, tiles]
    for k in range(N):
        a = 2 * math.pi * k / N
        w = 2 * R * math.tan(math.pi / N) + 0.05
        lib.box(ctx, f"wall_{k}", (w, 0.2, 4.5), (R * math.cos(a), R * math.sin(a), 2.25),
                rotation=(0, 0, a + math.pi / 2), mat=mats[k % len(mats)])
    # props near the walls (static)
    lib.import_gltf(ctx, "metal_stool_01", location=(3.1, 1.6, 0), rot_z_deg=30)
    lib.import_gltf(ctx, "metal_stool_01", location=(-2.6, -2.4, 0), rot_z_deg=-20)
    lib.import_gltf(ctx, "desk_lamp_arm_01", location=(-3.0, 2.3, 0.0), rot_z_deg=120)
    lib.import_gltf(ctx, "wooden_crate_01", location=(2.4, -3.0, 0), rot_z_deg=15)
    lib.import_gltf(ctx, "barrel_03", location=(-5.2, 0.6, 0))
    lib.import_gltf(ctx, "potted_plant_01", location=(5.2, -1.2, 0))
    lib.import_gltf(ctx, "potted_plant_01", location=(-1.0, 5.3, 0))
    # thin structures: light stands (tripods) and a truss of thin rods
    for k in range(3):
        a = math.radians(120 * k + 20)
        cx, cy = 2.8 * math.cos(a), 2.8 * math.sin(a)
        lib.rod(ctx, "stand", (cx, cy, 0.5), (cx, cy, 2.3), 0.012, mat=black)
        for j in range(3):
            b = math.radians(120 * j)
            lib.rod(ctx, "leg", (cx, cy, 0.5), (cx + 0.45 * math.cos(b), cy + 0.45 * math.sin(b), 0.0), 0.008, mat=black)
    for k in range(8):
        a, b = 2 * math.pi * k / 8, 2 * math.pi * (k + 1) / 8
        lib.rod(ctx, "truss", (5.6 * math.cos(a), 5.6 * math.sin(a), 3.9), (5.6 * math.cos(b), 5.6 * math.sin(b), 3.9),
                0.01, mat=metal)

    # ---------------- dynamic objects
    chk = lib.checker
    # turntable with two objects (slow rotation)
    tt_parts = [lib.cylinder(ctx, "turntable", 0.35, 0.05, (0, 0, 0.025), mat=chk("c_tt", (0.15, 0.15, 0.15), (0.8, 0.8, 0.8), 8),
                             coll="dynamic"),
                lib.box(ctx, "tt_box", (0.16, 0.16, 0.22), (0.2, 0, 0.16), mat=chk("c_ttb", (0.85, 0.2, 0.2), (0.95, 0.9, 0.85), 10),
                        coll="dynamic"),
                lib.sphere(ctx, "tt_ball", 0.08, (-0.18, 0.05, 0.13), mat=chk("c_tts", (0.1, 0.4, 0.9), (0.9, 0.9, 0.2), 7),
                           coll="dynamic")]
    turntable = lib.join(tt_parts, "mover_turntable")
    lib.make_dynamic(ctx, turntable)
    lib.keyframe_path(ctx, turntable, lambda t: ((0.25, -0.45, 0.03), (0, 0, 36 * t)), tA, tB, step)
    # pendulum on a thin wire from the truss (medium speed swing)
    bob = lib.sphere(ctx, "pend_bob", 0.07, (0, 0, -1.9), mat=chk("c_bob", (0.9, 0.6, 0.1), (0.2, 0.2, 0.2), 9), coll="dynamic")
    wire = lib.rod(ctx, "pend_wire", (0, 0, 0), (0, 0, -1.83), 0.0015, mat=metal, coll="dynamic")
    pend = lib.join([bob, wire], "mover_pendulum")
    lib.shift_origin(pend, (0, 0, 0))  # pivot at the top of the wire
    lib.make_dynamic(ctx, pend)
    lib.keyframe_path(ctx, pend, lambda t: ((-0.25, -0.2, 2.6), (18 * math.cos(2 * math.pi * t / 2.75),
                                                                   8 * math.sin(2 * math.pi * t / 2.75), 0)), tA, tB, step)
    # burst: a juggling club tossed up and spun fast for 18 frames, otherwise drifting
    club_parts = [lib.cylinder(ctx, "club_body", 0.035, 0.32, (0, 0, 0.06), mat=chk("c_club", (0.95, 0.95, 0.95), (0.6, 0.0, 0.6), 12),
                               coll="dynamic"),
                  lib.sphere(ctx, "club_knob", 0.045, (0, 0, -0.12), mat=black, coll="dynamic")]
    club = lib.join(club_parts, "burst_club")
    lib.make_dynamic(ctx, club)
    b0, b1 = 6.0, 6.0 + 18 / fps

    def club_path(t):
        s = _burst(t, b0, b1, 0.02, 3.5)
        spin = _burst(t, b0, b1, 15, 2200)
        h = 0.0 if not (b0 <= t < b1) else 0.5 * math.sin(math.pi * (t - b0) / (b1 - b0))
        return (0.6 - 0.25 * s, 0.4, 1.1 + h), (spin, 20, 0)
    lib.keyframe_path(ctx, club, club_path, tA, tB, step)
    # appears at 3.0 s on the stage, disappears at 7.0 s
    tor = lib.torus(ctx, "appear_ring", 0.16, 0.05, (0, 0, 0), mat=chk("c_ring", (0.1, 0.8, 0.4), (0.05, 0.1, 0.3), 14),
                    coll="dynamic")
    lib.make_dynamic(ctx, tor)
    lib.keyframe_path(ctx, tor, lambda t: ((-0.45, 0.5, 0.9 + 0.1 * math.sin(t)), (90, 0, 30 * t)), tA, tB, step)
    lib.visibility_window(ctx, tor, 3.0, 7.0)

    # cloth: a hanging banner at the stage edge, moved by a fan
    lib.rod(ctx, "banner_bar", (1.2, 1.5, 2.3), (2.0, 1.1, 2.3), 0.01, mat=metal)
    lib.cloth_sheet(ctx, "cloth_banner", (0.9, 1.2), (30, 40), (1.6, 1.3, 1.69), (math.radians(90), 0, math.radians(-26.6)),
                    lib.pbr(ctx, "jacquard", "quatrefoil_jacquard_fabric", scale=2.5), pin="top")
    lib.wind(ctx, "fan", (0.6, -0.4, 1.7), (-90, 0, -30), strength=140.0, noise=1.5, seed=17, gust_period=0.4)
    lib.turbulence(ctx, "turb", (1.6, 1.3, 1.7), strength=20.0, size=0.4)

    # person walking a circle on the stage (radius 1.3 m, one lap in ~10 s)
    def circle(t):
        w = 2 * math.pi / 10.0
        a = w * max(t, -0.2) - math.pi / 2
        loc = (1.3 * math.cos(a), 1.3 * math.sin(a), 0.03)
        heading = math.degrees(a) + 180.0  # facing the direction of travel (counter-clockwise)
        return loc, heading
    lib.character(ctx, "quaternius_animated_human", 1.75, circle, tA, tB, step, clip="Walk")
