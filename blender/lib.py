# SPDX-License-Identifier: GPL-3.0-or-later
"""Scene-building helpers for Blender 5.2 (bpy). Imported by blender/build.py and the
per-scene builders in blender/scenes/.

Collections used by the renderer:
  static   background geometry (always rendered)
  dynamic  everything that moves, deforms, appears or disappears (pass_index >= 1)
  lights   lamps
  markers  small emissive validation spheres (hidden in normal renders)
  clock    one emissive sphere on a known linear trajectory (validation of render times)
"""
import glob
import math
import os

import bpy
from mathutils import Matrix, Vector

COLLECTIONS = ("static", "dynamic", "lights", "markers", "clock")


class Ctx:
    def __init__(self, spec):
        self.spec = spec
        self.fps = spec["timing"]["fps"]
        self.F0 = spec["timing"]["F0"]
        self.frame_start = spec["timing"]["frame_start"]
        self.frame_end = spec["timing"]["frame_end"]
        self.duration = spec["timing"]["frames"] / self.fps
        self.assets = spec["assets_root"]
        self.coll = {}
        self._pass = 0
        self.markers = []
        self.clock = None
        self.dynamic_names = []

    def F(self, t):
        """Blender frame showing scene time t (seconds)."""
        return self.F0 + t * self.fps

    def t_of(self, F):
        return (F - self.F0) / self.fps


# ---------------------------------------------------------------- scene setup

def reset(ctx):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.unit_settings.system = "METRIC"
    sc.unit_settings.scale_length = 1.0
    sc.render.fps = ctx.fps
    sc.render.fps_base = 1.0
    sc.frame_start = ctx.frame_start
    sc.frame_end = ctx.frame_end
    sc.frame_set(ctx.frame_start)
    sc.render.engine = "CYCLES"
    for name in COLLECTIONS:
        c = bpy.data.collections.new(name)
        sc.collection.children.link(c)
        ctx.coll[name] = c
    ctx.coll["markers"].hide_render = True
    ctx.coll["clock"].hide_render = True
    return sc


def move_to(obj, coll):
    for c in list(obj.users_collection):
        c.objects.unlink(obj)
    coll.objects.link(obj)
    return obj


def make_dynamic(ctx, obj):
    """Mark an object as dynamic: dynamic collection, unique pass_index >= 1."""
    move_to(obj, ctx.coll["dynamic"])
    for o in [obj] + list(obj.children_recursive):
        if o.type in {"MESH", "CURVE", "SURFACE", "META", "FONT"}:
            ctx._pass += 1
            o.pass_index = ctx._pass
            ctx.dynamic_names.append(o.name)
        if o is not obj:
            move_to(o, ctx.coll["dynamic"])
    return obj


# ---------------------------------------------------------------- materials

def _texture_files(ctx, tex_id):
    d = os.path.join(ctx.assets, tex_id)
    def one(*tags):
        for tag in tags:
            hits = sorted(glob.glob(os.path.join(d, f"{tex_id}_{tag}_*.jpg")))
            if hits:
                return hits[0]
        return None
    return one("diff", "diffuse", "col_1"), one("nor_gl"), one("rough", "roughness")


def _new_material(name):
    m = bpy.data.materials.new(name)
    try:
        m.use_nodes = True
    except Exception:
        pass
    return m


def pbr(ctx, name, tex_id, scale=1.0, tint=None, roughness_scale=1.0, normal_strength=1.0):
    """Box-projected PBR material from a Poly Haven texture set (object-space coordinates,
    `scale` = texture repeats per metre)."""
    diff, nor, rough = _texture_files(ctx, tex_id)
    m = _new_material(name)
    nt = m.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    tc = nt.nodes.new("ShaderNodeTexCoord")
    mp = nt.nodes.new("ShaderNodeMapping")
    mp.inputs["Scale"].default_value = (scale, scale, scale)
    nt.links.new(tc.outputs["Object"], mp.inputs["Vector"])

    def img(path, noncolor):
        n = nt.nodes.new("ShaderNodeTexImage")
        n.image = bpy.data.images.load(path, check_existing=True)
        if noncolor:
            n.image.colorspace_settings.name = "Non-Color"
        n.projection = "BOX"
        n.projection_blend = 0.25
        nt.links.new(mp.outputs["Vector"], n.inputs["Vector"])
        return n

    d = img(diff, False)
    col = d.outputs["Color"]
    if tint is not None:
        mix = nt.nodes.new("ShaderNodeMix")
        mix.data_type = "RGBA"
        mix.blend_type = "MULTIPLY"
        mix.inputs["Factor"].default_value = 1.0
        mix.inputs["B"].default_value = tuple(tint) + (1.0,)
        nt.links.new(col, mix.inputs["A"])
        col = mix.outputs["Result"]
    nt.links.new(col, bsdf.inputs["Base Color"])
    if rough:
        r = img(rough, True)
        mul = nt.nodes.new("ShaderNodeMath")
        mul.operation = "MULTIPLY"
        mul.inputs[1].default_value = roughness_scale
        nt.links.new(r.outputs["Color"], mul.inputs[0])
        nt.links.new(mul.outputs[0], bsdf.inputs["Roughness"])
    if nor:
        n = img(nor, True)
        nm = nt.nodes.new("ShaderNodeNormalMap")
        nm.inputs["Strength"].default_value = normal_strength
        nt.links.new(n.outputs["Color"], nm.inputs["Color"])
        nt.links.new(nm.outputs["Normal"], bsdf.inputs["Normal"])
    return m


def solid(name, color, roughness=0.5, metallic=0.0):
    m = _new_material(name)
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = tuple(color) + (1.0,)
    b.inputs["Roughness"].default_value = roughness
    b.inputs["Metallic"].default_value = metallic
    return m


def checker(name, c1, c2, scale=10.0, roughness=0.5):
    """Procedural checker / noise pattern (used for small dynamic props so they texture well)."""
    m = _new_material(name)
    nt = m.node_tree
    b = nt.nodes["Principled BSDF"]
    tc = nt.nodes.new("ShaderNodeTexCoord")
    ch = nt.nodes.new("ShaderNodeTexChecker")
    ch.inputs["Scale"].default_value = scale
    ch.inputs["Color1"].default_value = tuple(c1) + (1.0,)
    ch.inputs["Color2"].default_value = tuple(c2) + (1.0,)
    nt.links.new(tc.outputs["Object"], ch.inputs["Vector"])
    nt.links.new(ch.outputs["Color"], b.inputs["Base Color"])
    b.inputs["Roughness"].default_value = roughness
    return m


def emission(name, color=(1, 1, 1), strength=1.0):
    m = _new_material(name)
    nt = m.node_tree
    nt.nodes.clear()
    o = nt.nodes.new("ShaderNodeOutputMaterial")
    e = nt.nodes.new("ShaderNodeEmission")
    e.inputs["Color"].default_value = tuple(color) + (1.0,)
    e.inputs["Strength"].default_value = strength
    nt.links.new(e.outputs[0], o.inputs["Surface"])
    return m


def aux_material():
    """Material override for the auxiliary render: emission colour = (planar z-depth,
    object pass index, 0). Rendered with 1 sample at the pixel centre into float EXR."""
    m = _new_material("__aux__")
    nt = m.node_tree
    nt.nodes.clear()
    o = nt.nodes.new("ShaderNodeOutputMaterial")
    e = nt.nodes.new("ShaderNodeEmission")
    cd = nt.nodes.new("ShaderNodeCameraData")
    oi = nt.nodes.new("ShaderNodeObjectInfo")
    comb = nt.nodes.new("ShaderNodeCombineXYZ")
    nt.links.new(cd.outputs["View Z Depth"], comb.inputs["X"])
    nt.links.new(oi.outputs["Object Index"], comb.inputs["Y"])
    nt.links.new(comb.outputs[0], e.inputs["Color"])
    e.inputs["Strength"].default_value = 1.0
    nt.links.new(e.outputs[0], o.inputs["Surface"])
    return m


# ---------------------------------------------------------------- geometry

def _finish(ctx, obj, mat, coll, smooth=False):
    if mat is not None:
        obj.data.materials.clear()
        obj.data.materials.append(mat)
    if smooth:
        for p in obj.data.polygons:
            p.use_smooth = True
    move_to(obj, ctx.coll[coll] if isinstance(coll, str) else coll)
    return obj


def box(ctx, name, size, location, rotation=(0, 0, 0), mat=None, coll="static", bevel=0.0):
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=location, rotation=rotation)
    o = bpy.context.active_object
    o.name = name
    o.scale = size
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    if bevel > 0:
        md = o.modifiers.new("bevel", "BEVEL")
        md.width = bevel
        md.segments = 2
    return _finish(ctx, o, mat, coll)


def plane(ctx, name, size, location, rotation=(0, 0, 0), mat=None, coll="static"):
    bpy.ops.mesh.primitive_plane_add(size=1.0, location=location, rotation=rotation)
    o = bpy.context.active_object
    o.name = name
    o.scale = (size[0], size[1], 1.0)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    return _finish(ctx, o, mat, coll)


def sphere(ctx, name, radius, location, mat=None, coll="static", segments=48, rings=24):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=segments, ring_count=rings, radius=radius, location=location)
    o = bpy.context.active_object
    o.name = name
    return _finish(ctx, o, mat, coll, smooth=True)


def cylinder(ctx, name, radius, depth, location, rotation=(0, 0, 0), mat=None, coll="static", vertices=32):
    bpy.ops.mesh.primitive_cylinder_add(vertices=vertices, radius=radius, depth=depth, location=location, rotation=rotation)
    o = bpy.context.active_object
    o.name = name
    return _finish(ctx, o, mat, coll, smooth=True)


def cone(ctx, name, r1, depth, location, rotation=(0, 0, 0), mat=None, coll="static"):
    bpy.ops.mesh.primitive_cone_add(vertices=48, radius1=r1, radius2=0.0, depth=depth, location=location, rotation=rotation)
    o = bpy.context.active_object
    o.name = name
    return _finish(ctx, o, mat, coll, smooth=False)


def torus(ctx, name, R, r, location, rotation=(0, 0, 0), mat=None, coll="static"):
    bpy.ops.mesh.primitive_torus_add(major_radius=R, minor_radius=r, major_segments=64, minor_segments=16,
                                     location=location, rotation=rotation)
    o = bpy.context.active_object
    o.name = name
    return _finish(ctx, o, mat, coll, smooth=True)


def rod(ctx, name, p0, p1, radius, mat=None, coll="static", vertices=12):
    """Thin cylinder from p0 to p1."""
    p0, p1 = Vector(p0), Vector(p1)
    d = p1 - p0
    o = cylinder(ctx, name, radius, d.length, (p0 + p1) / 2, mat=mat, coll=coll, vertices=vertices)
    o.rotation_mode = "QUATERNION"
    o.rotation_quaternion = Vector((0, 0, 1)).rotation_difference(d.normalized())
    return o


def join(objs, name):
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    bpy.ops.object.join()
    o = bpy.context.active_object
    o.name = name
    return o


def shift_origin(obj, world_point):
    """Move obj's origin to world_point without moving its geometry."""
    wp = Vector(world_point)
    local = obj.matrix_world.inverted() @ wp
    obj.data.transform(Matrix.Translation(-local))
    obj.location = obj.matrix_world @ local
    return obj


def empty(ctx, name, location=(0, 0, 0), coll="static"):
    e = bpy.data.objects.new(name, None)
    ctx.coll[coll].objects.link(e)
    e.location = location
    return e


def import_gltf(ctx, asset_id, location=(0, 0, 0), rot_z_deg=0.0, scale=1.0, coll="static", name=None):
    """Import a glTF asset under a new empty that carries the placement transform."""
    path = sorted(glob.glob(os.path.join(ctx.assets, asset_id, "*.gltf")) +
                  glob.glob(os.path.join(ctx.assets, asset_id, "*.glb")))[0]
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=path)
    new = [o for o in bpy.data.objects if o not in before]
    root = empty(ctx, name or asset_id, coll=coll)
    for o in new:
        move_to(o, ctx.coll[coll])
        if o.parent is None:
            o.parent = root
    root.location = location
    root.rotation_euler = (0, 0, math.radians(rot_z_deg))
    root.scale = (scale, scale, scale)
    return root, new


# ---------------------------------------------------------------- lighting

def hdri_world(ctx, hdri_id, strength=1.0, rot_z_deg=0.0):
    path = sorted(glob.glob(os.path.join(ctx.assets, hdri_id, "*.hdr")))[0]
    w = bpy.data.worlds.new("world")
    try:
        w.use_nodes = True
    except Exception:
        pass
    nt = w.node_tree
    bg = nt.nodes["Background"]
    env = nt.nodes.new("ShaderNodeTexEnvironment")
    env.image = bpy.data.images.load(path)
    tc = nt.nodes.new("ShaderNodeTexCoord")
    mp = nt.nodes.new("ShaderNodeMapping")
    mp.inputs["Rotation"].default_value = (0, 0, math.radians(rot_z_deg))
    nt.links.new(tc.outputs["Generated"], mp.inputs["Vector"])
    nt.links.new(mp.outputs["Vector"], env.inputs["Vector"])
    nt.links.new(env.outputs["Color"], bg.inputs["Color"])
    bg.inputs["Strength"].default_value = strength
    bpy.context.scene.world = w
    return w


def black_world():
    w = bpy.data.worlds.get("__black__") or bpy.data.worlds.new("__black__")
    try:
        w.use_nodes = True
    except Exception:
        pass
    bg = w.node_tree.nodes["Background"]
    bg.inputs["Color"].default_value = (0, 0, 0, 1)
    bg.inputs["Strength"].default_value = 0.0
    return w


def light(ctx, name, kind, location, rotation=(0, 0, 0), energy=100.0, size=1.0, color=(1, 1, 1), angle_deg=1.0):
    ld = bpy.data.lights.new(name, kind)
    ld.energy = energy
    ld.color = color
    if kind == "AREA":
        ld.size = size
    if kind == "SUN":
        ld.angle = math.radians(angle_deg)
    if kind in ("POINT", "SPOT"):
        ld.shadow_soft_size = size
    o = bpy.data.objects.new(name, ld)
    ctx.coll["lights"].objects.link(o)
    o.location = location
    o.rotation_euler = rotation
    o.visible_camera = False
    return o


# ---------------------------------------------------------------- animation

def _set_interp(kind):
    bpy.context.preferences.edit.keyframe_new_interpolation_type = kind


def _fcurves(id_data):
    """F-curves of an ID's assigned action (Blender 5.x layered actions)."""
    from bpy_extras import anim_utils
    ad = id_data.animation_data
    cb = anim_utils.action_get_channelbag_for_slot(ad.action, ad.action_slot)
    return cb.fcurves


def keyframe(id_data, data_path, frame, interp):
    """keyframe_insert + explicit interpolation on the new keys (the user-preference default
    is not applied to keys inserted from Python in 5.2; measured)."""
    id_data.keyframe_insert(data_path, frame=frame)
    for fc in _fcurves(id_data):
        if fc.data_path == data_path:
            for kp in fc.keyframe_points:
                if abs(kp.co[0] - frame) < 1e-6:
                    kp.interpolation = interp
            fc.update()


def key(ctx, obj, t, loc=None, rot_deg=None, scale=None, interp="BEZIER"):
    """Keyframe obj at scene time t (seconds)."""
    F = ctx.F(t)
    if loc is not None:
        obj.location = loc
        keyframe(obj, "location", F, interp)
    if rot_deg is not None:
        obj.rotation_euler = tuple(math.radians(a) for a in rot_deg)
        keyframe(obj, "rotation_euler", F, interp)
    if scale is not None:
        obj.scale = scale
        keyframe(obj, "scale", F, interp)


def visibility_window(ctx, obj, t_on, t_off):
    """Object rendered only for t_on <= t < t_off (hide_render keyed with CONSTANT)."""
    targets = [obj] + [o for o in obj.children_recursive]
    for o in targets:
        for F, hidden in ((ctx.frame_start - 5, True), (ctx.F(t_on), False), (ctx.F(t_off), True)):
            o.hide_render = hidden
            keyframe(o, "hide_render", F, "CONSTANT")


def keyframe_path(ctx, obj, fn, t0, t1, step, interp="LINEAR"):
    """Sample fn(t) -> (loc, rot_deg) every `step` seconds and keyframe it."""
    n = int(math.ceil((t1 - t0) / step))
    for i in range(n + 1):
        t = min(t0 + i * step, t1)
        loc, rot = fn(t)
        key(ctx, obj, t, loc=loc, rot_deg=rot, interp=interp)


# ---------------------------------------------------------------- cloth

def cloth_sheet(ctx, name, size, subdiv, location, rotation, mat, pin="top", quality=10, mass=0.004,
                stiffness=15.0, bending=0.5, air=1.0):
    """Rectangular cloth pinned along one edge. Baked later by bake_physics()."""
    bpy.ops.mesh.primitive_grid_add(x_subdivisions=subdiv[0], y_subdivisions=subdiv[1], size=1.0,
                                    location=location, rotation=rotation)
    o = bpy.context.active_object
    o.name = name
    o.scale = (size[0], size[1], 1.0)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    vg = o.vertex_groups.new(name="pin")
    ys = [v.co.y for v in o.data.vertices]
    xs = [v.co.x for v in o.data.vertices]
    sel = {
        "top": [v.index for v in o.data.vertices if v.co.y > max(ys) - 1e-6],
        "left": [v.index for v in o.data.vertices if v.co.x < min(xs) + 1e-6],
        "corners": [v.index for v in o.data.vertices if v.co.y > max(ys) - 1e-6 and
                    (v.co.x < min(xs) + 1e-6 or v.co.x > max(xs) - 1e-6)],
    }[pin]
    vg.add(sel, 1.0, "REPLACE")
    _finish(ctx, o, mat, "dynamic", smooth=True)
    cm = o.modifiers.new("cloth", "CLOTH")
    s = cm.settings
    s.quality = quality
    s.mass = mass
    s.tension_stiffness = s.compression_stiffness = s.shear_stiffness = stiffness
    s.bending_stiffness = bending
    s.air_damping = air
    s.vertex_group_mass = "pin"
    cm.point_cache.frame_start = ctx.frame_start
    cm.point_cache.frame_end = ctx.frame_end
    sub = o.modifiers.new("subsurf", "SUBSURF")
    sub.levels = sub.render_levels = 1
    sol = o.modifiers.new("solidify", "SOLIDIFY")
    sol.thickness = 0.003
    ctx._pass += 1
    o.pass_index = ctx._pass
    ctx.dynamic_names.append(o.name)
    return o


def wind(ctx, name, location, rotation_deg, strength, noise=1.0, seed=1, flow=0.0, gust_period=0.4):
    """Wind field with deterministic gusts: strength keyed between 0.3x and 1.3x every
    gust_period seconds (pseudo-random amplitudes from `seed`)."""
    import random
    bpy.ops.object.effector_add(type="WIND", location=location,
                                rotation=tuple(math.radians(a) for a in rotation_deg))
    o = bpy.context.active_object
    o.name = name
    o.field.noise = noise
    o.field.seed = seed
    o.field.flow = flow
    rnd = random.Random(seed)
    t, tB = ctx.t_of(ctx.frame_start), ctx.t_of(ctx.frame_end)
    while t <= tB + gust_period:
        o.field.strength = strength * rnd.uniform(0.3, 1.3)
        keyframe(o, "field.strength", ctx.F(t), "BEZIER")
        t += gust_period
    move_to(o, ctx.coll["static"])
    return o


def turbulence(ctx, name, location, strength, size=1.0, seed=3):
    bpy.ops.object.effector_add(type="TURBULENCE", location=location)
    o = bpy.context.active_object
    o.name = name
    o.field.strength = strength
    o.field.size = size
    o.field.seed = seed
    move_to(o, ctx.coll["static"])
    return o


def bake_physics():
    sc = bpy.context.scene
    for o in sc.objects:
        for m in o.modifiers:
            if m.type == "CLOTH":
                m.point_cache.use_disk_cache = True
    with bpy.context.temp_override(scene=sc):
        bpy.ops.ptcache.free_bake_all()
        bpy.ops.ptcache.bake_all(bake=True)


# ---------------------------------------------------------------- markers

def add_markers(ctx, points, radius, strength=1.0):
    mat = emission("__marker__", (1, 1, 1), strength)
    for i, p in enumerate(points):
        sphere(ctx, f"marker_{i:03d}", radius, p, mat=mat, coll="markers", segments=32, rings=16)
        ctx.markers.append({"id": i, "position": [float(c) for c in p], "radius": float(radius)})


def add_clock(ctx, p0, velocity, radius, strength=1.0):
    """Emissive sphere at p(t) = p0 + velocity * t (linear keys at both timeline ends)."""
    mat = emission("__clock__", (1, 1, 1), strength)
    o = sphere(ctx, "clock_marker", radius, p0, mat=mat, coll="clock", segments=32, rings=16)
    for F in (ctx.frame_start, ctx.frame_end):
        t = ctx.t_of(F)
        key(ctx, o, t, loc=tuple(p0[k] + velocity[k] * t for k in range(3)), interp="LINEAR")
    ctx.clock = {"p0": [float(c) for c in p0], "velocity": [float(c) for c in velocity], "radius": float(radius)}
    return o


# ---------------------------------------------------------------- character

def dress_material(ctx, name, legs_tex="denim_fabric", shirt_tex="fabric_pattern_07",
                   skin=(0.62, 0.42, 0.32), shirt_tint=None):
    """The CC0 character ships untextured; give it trousers / shirt / skin bands by
    rest-pose height (Generated z) so it is textured enough for feature matching."""
    m = _new_material(name)
    nt = m.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    tc = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(tc.outputs["Generated"], sep.inputs[0])
    mp = nt.nodes.new("ShaderNodeMapping")
    mp.inputs["Scale"].default_value = (6.0, 6.0, 6.0)
    nt.links.new(tc.outputs["Generated"], mp.inputs["Vector"])

    def tex(tex_id, tint=None):
        diff = _texture_files(ctx, tex_id)[0]
        n = nt.nodes.new("ShaderNodeTexImage")
        n.image = bpy.data.images.load(diff, check_existing=True)
        n.projection = "BOX"
        n.projection_blend = 0.3
        nt.links.new(mp.outputs["Vector"], n.inputs["Vector"])
        out = n.outputs["Color"]
        if tint:
            mix = nt.nodes.new("ShaderNodeMix")
            mix.data_type = "RGBA"
            mix.blend_type = "MULTIPLY"
            mix.inputs["Factor"].default_value = 1.0
            mix.inputs["B"].default_value = tuple(tint) + (1.0,)
            nt.links.new(out, mix.inputs["A"])
            out = mix.outputs["Result"]
        return out
    legs = tex(legs_tex)
    shirt = tex(shirt_tex, shirt_tint)
    noise = nt.nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 40.0
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = tuple(c * 0.75 for c in skin) + (1.0,)
    ramp.color_ramp.elements[1].color = tuple(skin) + (1.0,)
    nt.links.new(noise.outputs["Fac"], ramp.inputs["Fac"])

    def step(edge):
        n = nt.nodes.new("ShaderNodeMath")
        n.operation = "GREATER_THAN"
        n.inputs[1].default_value = edge
        nt.links.new(sep.outputs["Z"], n.inputs[0])
        return n.outputs[0]
    m1 = nt.nodes.new("ShaderNodeMix")
    m1.data_type = "RGBA"
    nt.links.new(step(0.46), m1.inputs["Factor"])
    nt.links.new(legs, m1.inputs["A"])
    nt.links.new(shirt, m1.inputs["B"])
    m2 = nt.nodes.new("ShaderNodeMix")
    m2.data_type = "RGBA"
    nt.links.new(step(0.83), m2.inputs["Factor"])
    nt.links.new(m1.outputs["Result"], m2.inputs["A"])
    nt.links.new(ramp.outputs["Color"], m2.inputs["B"])
    nt.links.new(m2.outputs["Result"], bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.7
    bsdf.inputs["Metallic"].default_value = 0.0
    return m

def character(ctx, asset_id, height, path_fn, t0, t1, step, clip="Walk", rot_offset_deg=0.0):
    """Import a rigged glTF character, loop `clip`, and move its root along path_fn(t) ->
    (location, heading_deg)."""
    sc = bpy.context.scene
    root, new = import_gltf(ctx, asset_id, coll="dynamic", name="character")
    junk = [o for o in new if o.type == "MESH" and o.name.startswith("Icosphere")]  # stray helper mesh in the GLB
    new = [o for o in new if o not in junk]
    for o in junk:
        bpy.data.objects.remove(o)
    arm = next(o for o in new if o.type == "ARMATURE")
    meshes = [o for o in new if o.type == "MESH"]
    bpy.context.view_layer.update()
    zs = [(o.matrix_world @ Vector(c)).z for o in meshes for c in o.bound_box]
    s = height / (max(zs) - min(zs))
    root.scale = (s, s, s)
    act = next(a for a in bpy.data.actions if a.name.endswith("|" + clip) or a.name == clip)
    ad = arm.animation_data or arm.animation_data_create()
    for tr in list(ad.nla_tracks):
        ad.nla_tracks.remove(tr)
    ad.action = None
    track = ad.nla_tracks.new()
    start = ctx.frame_start - 10
    length = act.frame_range[1] - act.frame_range[0]
    strip = track.strips.new(clip, int(start), act)
    if hasattr(strip, "action_slot") and len(getattr(act, "slots", [])):
        strip.action_slot = act.slots[0]
    strip.repeat = math.ceil((ctx.frame_end + 20 - start) / length)
    strip.extrapolation = "HOLD"
    mat = dress_material(ctx, "character_dress")
    for o in meshes:
        o.data.materials.clear()
        o.data.materials.append(mat)
        ctx._pass += 1
        o.pass_index = ctx._pass
        ctx.dynamic_names.append(o.name)

    def fn(t):
        loc, hd = path_fn(t)
        return loc, (0, 0, hd + rot_offset_deg)
    keyframe_path(ctx, root, fn, t0, t1, step, interp="BEZIER")
    return root, act, length
