# SPDX-License-Identifier: GPL-3.0-or-later
"""courtyard: an outdoor paved courtyard enclosed on three sides, seen by a wide arc.

The action is around the origin. Building walls stand at x = -7.5, x = +7.5 and y = +6.5;
the cameras stand on the open (-y) side, on an arc of radius ~5.5 m.
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
    lib.hdri_world(ctx, "urban_courtyard", strength=0.9, rot_z_deg=200)
    lib.light(ctx, "sun", "SUN", (0, 0, 10), rotation=(math.radians(50), 0, math.radians(35)), energy=3.2, angle_deg=1.5,
              color=(1.0, 0.95, 0.88))

    ground = lib.pbr(ctx, "cobbles", "cobblestone_floor_04", scale=0.45)
    brick = lib.pbr(ctx, "brick", "brick_wall_001", scale=0.35)
    plaster = lib.pbr(ctx, "plaster", "plaster_brick_01", scale=0.35)
    wood = lib.pbr(ctx, "wood", "kitchen_wood", scale=0.8)
    metal = lib.solid("galvanised", (0.55, 0.56, 0.58), roughness=0.4, metallic=1.0)
    paint = lib.solid("green_paint", (0.08, 0.25, 0.12), roughness=0.5)

    lib.plane(ctx, "ground", (30, 30), (0, 0, 0), mat=ground)
    lib.box(ctx, "wall_back", (15.4, 0.4, 6.0), (0, 6.7, 3.0), mat=brick)
    lib.box(ctx, "wall_left", (0.4, 14.0, 5.0), (-7.7, -0.3, 2.5), mat=plaster)
    lib.box(ctx, "wall_right", (0.4, 14.0, 5.5), (7.7, -0.3, 2.75), mat=plaster)
    # doorways and window recesses for structure
    for x in (-4.5, 0.0, 4.5):
        lib.box(ctx, "door", (1.1, 0.06, 2.2), (x, 6.48, 1.1), mat=wood)
        for dx in (-2.0, 2.0):
            lib.box(ctx, "window", (0.9, 0.05, 1.1), (x + dx * 0.55, 6.48, 3.7), mat=lib.solid("glass_dark", (0.05, 0.07, 0.08), 0.1))
    for y in (-3.0, 1.0, 4.5):
        lib.box(ctx, "window_l", (0.05, 1.0, 1.2), (-7.48, y, 2.0), mat=lib.solid("shutter", (0.2, 0.3, 0.45), 0.6))
        lib.box(ctx, "window_r", (0.05, 1.0, 1.2), (7.48, y, 2.0), mat=lib.solid("shutter2", (0.45, 0.25, 0.15), 0.6))

    # props
    lib.import_gltf(ctx, "painted_wooden_bench", location=(-3.0, 4.2, 0), rot_z_deg=0)
    lib.import_gltf(ctx, "painted_wooden_bench", location=(3.4, 4.0, 0), rot_z_deg=10)
    lib.import_gltf(ctx, "planter_box_01", location=(-5.5, 2.0, 0), rot_z_deg=90)
    lib.import_gltf(ctx, "planter_box_01", location=(5.6, 1.5, 0), rot_z_deg=90)
    lib.import_gltf(ctx, "street_lamp_01", location=(-1.6, 5.2, 0))
    lib.import_gltf(ctx, "street_lamp_01", location=(5.8, -2.5, 0))
    lib.import_gltf(ctx, "wooden_crate_01", location=(4.6, 5.3, 0), rot_z_deg=12)
    lib.import_gltf(ctx, "wooden_crate_01", location=(4.9, 5.0, 0.6), rot_z_deg=40)
    lib.import_gltf(ctx, "barrel_03", location=(-6.4, 5.2, 0))
    lib.import_gltf(ctx, "potted_plant_01", location=(1.8, 5.6, 0))
    lib.import_gltf(ctx, "potted_plant_01", location=(-6.6, -1.8, 0))

    # thin structures: wire fence panel, a bicycle rack, a clothesline
    for i in range(25):
        x = -6.0 + i * 0.1
        lib.rod(ctx, "fence_v", (x, -4.0, 0.0), (x, -4.0, 1.2), 0.003, mat=metal)
    for j in range(6):
        lib.rod(ctx, "fence_h", (-6.0, -4.0, 0.05 + j * 0.23), (-3.6, -4.0, 0.05 + j * 0.23), 0.003, mat=metal)
    for k in range(5):
        x = 1.0 + k * 0.5
        lib.rod(ctx, "rack_l", (x, 5.6, 0), (x, 5.6, 0.7), 0.012, mat=metal)
        lib.rod(ctx, "rack_r", (x + 0.35, 5.6, 0), (x + 0.35, 5.6, 0.7), 0.012, mat=metal)
        lib.rod(ctx, "rack_t", (x, 5.6, 0.7), (x + 0.35, 5.6, 0.7), 0.012, mat=metal)
    lib.rod(ctx, "pole_a", (-6.0, 3.0, 0), (-6.0, 3.0, 2.6), 0.025, mat=paint)
    lib.rod(ctx, "pole_b", (-2.5, 3.0, 0), (-2.5, 3.0, 2.6), 0.025, mat=paint)
    lib.rod(ctx, "clothesline", (-6.0, 3.0, 2.45), (-2.5, 3.0, 2.45), 0.003, mat=metal)

    # ---------------- dynamic objects
    chk = lib.checker
    # football rolling slowly diagonally
    ball = lib.sphere(ctx, "mover_ball", 0.11, (0, 0, 0), mat=chk("c_ball", (0.95, 0.95, 0.95), (0.05, 0.05, 0.05), 6),
                      coll="dynamic")
    lib.make_dynamic(ctx, ball)
    lib.keyframe_path(ctx, ball, lambda t: ((-2.5 + 0.45 * t, -1.0 + 0.25 * t, 0.11),
                                            (math.degrees(-0.25 * t / 0.11), math.degrees(0.45 * t / 0.11), 0)), tA, tB, step)
    # barrel rolling at medium speed
    barrel = lib.cylinder(ctx, "mover_barrel", 0.28, 0.8, (0, 0, 0), mat=chk("c_barrel", (0.5, 0.25, 0.1), (0.8, 0.6, 0.3), 5),
                          coll="dynamic")
    lib.make_dynamic(ctx, barrel)
    lib.keyframe_path(ctx, barrel, lambda t: ((3.5 - 0.9 * t, 2.2, 0.28), (math.degrees(0.9 * t / 0.28), 90, 0)),
                      tA, tB, step)
    # crate sliding on a cart (slow) and turning
    crate = lib.box(ctx, "mover_crate", (0.5, 0.4, 0.4), (0, 0, 0), mat=chk("c_crate", (0.2, 0.4, 0.8), (0.9, 0.85, 0.7), 4),
                    coll="dynamic", bevel=0.01)
    lib.make_dynamic(ctx, crate)
    lib.keyframe_path(ctx, crate, lambda t: ((1.2, 3.6 - 0.2 * t, 0.2), (0, 0, 12 * t)), tA, tB, step)
    # bicycle-like wheel: thin spokes, rotating in place on a stand
    parts = [lib.torus(ctx, "rim", 0.33, 0.012, (0, 0, 0), rotation=(math.pi / 2, 0, 0), mat=metal, coll="dynamic")]
    for k in range(16):
        a = k * math.pi / 8
        parts.append(lib.rod(ctx, "spoke", (0, 0, 0), (0.33 * math.cos(a), 0, 0.33 * math.sin(a)), 0.0015, mat=metal,
                             coll="dynamic"))
    parts.append(lib.cylinder(ctx, "hub", 0.03, 0.06, (0, 0, 0), rotation=(math.pi / 2, 0, 0), mat=paint, coll="dynamic"))
    wheel = lib.join(parts, "mover_wheel")
    lib.make_dynamic(ctx, wheel)
    lib.box(ctx, "wheel_stand", (0.05, 0.05, 0.62), (-1.2, 2.8, 0.31), mat=paint)
    lib.keyframe_path(ctx, wheel, lambda t: ((-1.2, 2.75, 0.62), (0, 140 * t, 0)), tA, tB, step)
    # burst: a frisbee thrown across the courtyard in 15 frames (0.25 s), slow drift otherwise
    disc = lib.cylinder(ctx, "burst_disc", 0.13, 0.025, (0, 0, 0), mat=chk("c_disc", (0.95, 0.85, 0.05), (0.9, 0.15, 0.1), 10),
                        coll="dynamic")
    lib.make_dynamic(ctx, disc)
    b0, b1 = 2.0, 2.0 + 15 / fps

    def disc_path(t):
        s = _burst(t, b0, b1, 0.05, 16.0)
        spin = _burst(t, b0, b1, 30, 2400)
        return (-3.0 + s, 0.8 + 0.1 * s, 1.4 + 0.08 * math.sin(s)), (8, 0, spin)
    lib.keyframe_path(ctx, disc, disc_path, tA, tB, step)
    # traffic cone: appears at 1.0 s, disappears at 3.5 s
    cone = lib.cone(ctx, "appear_cone", 0.16, 0.5, (0, 0, 0), mat=chk("c_cone", (1.0, 0.35, 0.0), (0.95, 0.95, 0.95), 3),
                    coll="dynamic")
    lib.make_dynamic(ctx, cone)
    lib.keyframe_path(ctx, cone, lambda t: ((0.6, -0.6, 0.25), (0, 0, 20 * t)), tA, tB, step)
    lib.visibility_window(ctx, cone, 1.0, 3.5)

    # cloth: a towel on the clothesline in gusty wind
    lib.cloth_sheet(ctx, "cloth_towel", (0.8, 1.0), (32, 40), (-4.2, 3.0, 1.95), (math.radians(90), 0, 0),
                    lib.pbr(ctx, "denim", "denim_fabric", scale=3.0), pin="top")
    lib.wind(ctx, "wind", (-4.2, 0.5, 1.8), (-80, 0, 15), strength=320.0, noise=1.5, seed=11, gust_period=0.3)
    lib.turbulence(ctx, "turb", (-4.2, 3.0, 1.9), strength=25.0, size=0.4)

    # person walking diagonally through the courtyard
    lib.character(ctx, "quaternius_animated_human", 1.76,
                  lambda t: ((-3.8 + 1.2 * max(t, 0.0), 3.4 - 0.55 * max(t, 0.0), 0.0), 90 - math.degrees(math.atan2(0.55, 1.2))),
                  tA, tB, step, clip="Walk")
