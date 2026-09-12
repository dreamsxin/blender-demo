"""水晶幻想中式宝剑 (crystal jian): 程序化建模 + Cycles 渲染。

    blender -b --factory-startup --python demos/props/crystal-sword/scripts/build_sword.py -- \
        [--out <png>] [--engine cycles|eevee] [--samples 128] [--res 1080]

剑身走菱形截面、逐段收窄的水晶; 剑格/剑首为云纹金属; 剑柄缠绳 + 红色剑穗;
剑身内部带一层冷光, 四周漂浮几块碎晶。跑完存 crystal_sword.blend。
"""
import math
import os
import random
import sys

import bmesh
import bpy
from mathutils import Vector

# --- 尺寸 (Blender 单位, 剑竖直朝 +Z, 正面朝 -Y) ---
BLADE_LEN = 0.95
BLADE_HALF_W = 0.048        # 剑身最宽处半宽
BLADE_HALF_T = 0.012        # 菱形截面半厚
GUARD_Z = 0.0               # 剑格所在高度, 剑身由此往上
GRIP_LEN = 0.24
TASSEL_LEN = 0.26
SHARD_COUNT = 7

OUT = ""
ENGINE = "cycles"
SAMPLES = 128
RES_X = 1080


def log(msg):
    print("[sword]", msg, flush=True)


def parse_args():
    global OUT, ENGINE, SAMPLES, RES_X
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    for flag in ("--out", "--engine", "--samples", "--res"):
        if flag not in argv:
            continue
        v = argv[argv.index(flag) + 1]
        if flag == "--out":
            OUT = v
        elif flag == "--engine":
            ENGINE = v.lower()
        elif flag == "--samples":
            SAMPLES = int(v)
        else:
            RES_X = int(v)
    if not OUT:
        here = os.path.dirname(os.path.abspath(globals().get("__file__", ".")))
        OUT = os.path.join(os.path.dirname(here), "render", "crystal_sword.png")


def clean_scene():
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)


def set_in(node, name, value):
    sock = node.inputs.get(name)
    if sock is not None:
        sock.default_value = value


def mat(name, color, roughness=0.4, metallic=0.0, transmission=0.0, ior=1.5,
        coat=0.0, sheen=0.0, emission=None, emission_strength=0.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    bsdf = m.node_tree.nodes["Principled BSDF"]
    set_in(bsdf, "Base Color", (*color, 1.0))
    set_in(bsdf, "Roughness", roughness)
    set_in(bsdf, "Metallic", metallic)
    set_in(bsdf, "IOR", ior)
    set_in(bsdf, "Transmission Weight", transmission)
    set_in(bsdf, "Coat Weight", coat)
    set_in(bsdf, "Sheen Weight", sheen)
    if emission is not None:
        set_in(bsdf, "Emission Color", (*emission, 1.0))
        set_in(bsdf, "Emission Strength", emission_strength)
    return m


def shade(obj, smooth=True):
    for p in obj.data.polygons:
        p.use_smooth = smooth
    return obj


def ball(name, radius, material, location=(0, 0, 0), scale=(1, 1, 1), segments=48):
    bpy.ops.mesh.primitive_uv_sphere_add(radius=radius, segments=segments,
                                         ring_count=segments // 2, location=location)
    obj = bpy.context.object
    obj.name, obj.scale = name, scale
    obj.data.materials.append(material)
    return shade(obj)


def tube(name, r1, r2, depth, material, location=(0, 0, 0), rotation=(0, 0, 0),
         verts=48, smooth=True):
    bpy.ops.mesh.primitive_cone_add(radius1=r1, radius2=r2, depth=depth, vertices=verts,
                                    location=location, rotation=rotation)
    obj = bpy.context.object
    obj.name = name
    obj.data.materials.append(material)
    return shade(obj, smooth)


def ring(name, major, minor, material, location=(0, 0, 0), rotation=(0, 0, 0)):
    bpy.ops.mesh.primitive_torus_add(major_radius=major, minor_radius=minor,
                                     major_segments=48, minor_segments=14,
                                     location=location, rotation=rotation)
    obj = bpy.context.object
    obj.name = name
    obj.data.materials.append(material)
    return obj


def rounded_box(name, size, radius, material, location=(0, 0, 0), segments=5,
                rotation=(0, 0, 0)):
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    for v in bm.verts:
        v.co.x *= size[0]
        v.co.y *= size[1]
        v.co.z *= size[2]
    bmesh.ops.bevel(bm, geom=list(bm.verts) + list(bm.edges) + list(bm.faces),
                    offset=min(radius, min(size) * 0.49), segments=segments,
                    affect="EDGES", profile=0.5, clamp_overlap=True)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    obj = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(obj)
    obj.location, obj.rotation_euler = location, rotation
    obj.data.materials.append(material)
    for p in me.polygons:
        n = p.normal
        p.use_smooth = max(abs(n.x), abs(n.y), abs(n.z)) < 0.999
    return obj


def blade_profile(t):
    """t: 0=剑格处, 1=剑尖。返回 (半宽, 半厚)。"""
    if t <= 0.88:
        w = BLADE_HALF_W * (1.0 - 0.10 * t)
    else:
        w = BLADE_HALF_W * 0.912 * (1.0 - (t - 0.88) / 0.12)
    th = BLADE_HALF_T * (1.0 - 0.55 * t)
    return max(w, 1e-4), max(th, 1e-4)


def build_blade(name, material, scale_xy=1.0, z0=None, length=None, steps=26):
    """菱形截面、逐段收窄的剑身; 平面着色让水晶棱面清爽。"""
    z0 = GUARD_Z if z0 is None else z0
    length = BLADE_LEN if length is None else length
    bm = bmesh.new()
    rings = []
    for i in range(steps):
        t = i / (steps - 1)
        w, th = blade_profile(t)
        w, th = w * scale_xy, th * scale_xy
        z = z0 + length * t
        if t >= 1.0:
            break
        rings.append([bm.verts.new((w, 0.0, z)), bm.verts.new((0.0, th, z)),
                      bm.verts.new((-w, 0.0, z)), bm.verts.new((0.0, -th, z))])
    tip = bm.verts.new((0.0, 0.0, z0 + length))
    for a, b in zip(rings, rings[1:]):
        for k in range(4):
            bm.faces.new((a[k], a[(k + 1) % 4], b[(k + 1) % 4], b[k]))
    for k in range(4):                      # 剑尖收成一点
        bm.faces.new((rings[-1][k], rings[-1][(k + 1) % 4], tip))
    bm.faces.new(tuple(reversed(rings[0])))  # 根部封口
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    obj = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(obj)
    obj.data.materials.append(material)
    return obj


def build_hilt(gold, crystal, lacquer, cord, silk, glow):
    """剑格 (云纹) + 剑柄缠绳 + 剑首 + 剑穗。"""
    # 剑格: 中间一块 + 两侧上翘的云头
    rounded_box("Guard", (0.20, 0.052, 0.042), 0.016, gold, location=(0, 0, -0.012))
    for s in (-1, 1):
        tube("GuardHorn%d" % s, 0.026, 0.004, 0.10, gold,
             (0.105 * s, 0.0, 0.030), rotation=(0, s * 1.05, 0))
        ball("GuardBead%d" % s, 0.016, crystal, (0.148 * s, 0.0, 0.062))
    ball("GuardGem", 0.026, crystal, (0, -0.028, 0.004), scale=(1.0, 0.7, 1.0))
    # 剑柄: 漆木芯 + 一圈圈缠绳
    tube("Grip", 0.026, 0.023, GRIP_LEN, lacquer, (0, 0, -0.04 - GRIP_LEN / 2))
    n = 9
    for i in range(n):
        z = -0.055 - (GRIP_LEN - 0.045) * i / (n - 1)
        ring("Wrap%d" % i, 0.026, 0.0075, cord, (0, 0, z))
    # 剑首: 云头盘 + 环
    z_pom = -0.04 - GRIP_LEN
    tube("Pommel", 0.030, 0.040, 0.036, gold, (0, 0, z_pom - 0.014), verts=32)
    ring("PommelRing", 0.030, 0.008, gold, (0, 0, z_pom - 0.040))
    ball("PommelGem", 0.020, crystal, (0, 0, z_pom - 0.058))
    # 剑穗: 结 + 一束丝线
    ball("TasselKnot", 0.024, silk, (0, 0, z_pom - 0.082), scale=(1.0, 1.0, 1.2))
    rng = random.Random(7)
    for i in range(16):
        a = 2 * math.pi * i / 16
        r = 0.012 + 0.008 * rng.random()
        length = TASSEL_LEN * (0.75 + 0.25 * rng.random())
        tube("Silk%d" % i, 0.0055, 0.0022, length, silk,
             (r * math.cos(a), r * math.sin(a) * 0.7, z_pom - 0.10 - length / 2),
             rotation=(0.10 * rng.random(), 0.10 * rng.random(), 0), verts=10)
    # 符文光带
    for i, z in enumerate((0.075, 0.135, 0.195)):
        w, th = blade_profile(z / BLADE_LEN)
        rounded_box("Rune%d" % i, (w * 2.1, th * 2.4, 0.007), 0.002, glow,
                    location=(0, 0, z), segments=2)


def build_shards(crystal, glow):
    """漂浮碎晶: 上下对顶的四棱锥 (八面体), 一部分带微弱自发光。"""
    rng = random.Random(3)
    for i in range(SHARD_COUNT):
        a = rng.uniform(0, 2 * math.pi)
        r = rng.uniform(0.16, 0.34)
        z = rng.uniform(0.15, 0.90)
        s = rng.uniform(0.018, 0.036)
        loc = (r * math.cos(a), r * math.sin(a) * 0.5, z)
        rot = (rng.uniform(-0.5, 0.5), rng.uniform(-0.5, 0.5), rng.uniform(0, 3.14))
        m = glow if i % 2 == 0 else crystal
        for sign in (1.0, -1.0):
            bpy.ops.mesh.primitive_cone_add(radius1=s, radius2=0.0, depth=s * 2.6,
                                            vertices=4, location=loc, rotation=rot)
            part = bpy.context.object
            part.name = "Shard%d%s" % (i, "T" if sign > 0 else "B")
            part.scale = (1.0, 1.0, sign)
            part.data.materials.append(m)


def build_studio():
    dark = mat("Studio", (0.012, 0.014, 0.020), roughness=0.6)
    bpy.ops.mesh.primitive_plane_add(size=24.0, location=(0, 2.6, 0))
    back = bpy.context.object
    back.name = "Backdrop"
    back.rotation_euler = (math.pi / 2, 0, 0)
    back.data.materials.append(dark)
    bpy.ops.mesh.primitive_plane_add(size=24.0, location=(0, 0, -1.15))
    floor = bpy.context.object
    floor.name = "Floor"
    floor.data.materials.append(mat("Floor", (0.018, 0.020, 0.026), roughness=0.22))

    target = Vector((0.0, 0.0, 0.14))
    for name, loc, energy, color, size in (
            ("RimL", (-1.5, 1.1, 1.5), 220, (0.62, 0.80, 1.0), 1.6),
            ("RimR", (1.6, 0.9, 0.3), 150, (0.45, 0.85, 0.95), 1.2),
            ("Fill", (-0.4, -2.0, 0.5), 22, (0.75, 0.82, 1.0), 2.4),
            ("Top", (0.3, -0.3, 2.0), 70, (0.85, 0.92, 1.0), 1.0),
            ("Warm", (-1.0, -1.2, -0.5), 26, (1.0, 0.72, 0.42), 0.8)):
        light = bpy.data.lights.new(name, type="AREA")
        light.energy, light.size = energy, size
        light.color = color
        obj = bpy.data.objects.new(name, light)
        bpy.context.scene.collection.objects.link(obj)
        obj.location = loc
        obj.visible_camera = False
        obj.rotation_euler = (target - Vector(loc)).normalized().to_track_quat("-Z", "Y").to_euler()

    world = bpy.data.worlds[0] if bpy.data.worlds else bpy.data.worlds.new("W")
    bpy.context.scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    if bg:
        bg.inputs[0].default_value = (0.012, 0.016, 0.028, 1.0)
        bg.inputs[1].default_value = 1.0

    cam_data = bpy.data.cameras.new("Cam")
    cam_data.lens = 85.0
    cam_data.sensor_fit = "HORIZONTAL"
    cam = bpy.data.objects.new("Cam", cam_data)
    bpy.context.scene.collection.objects.link(cam)
    bpy.context.scene.camera = cam
    res_y = int(RES_X * 4 / 3)
    dist = 1.34 * cam_data.lens / cam_data.sensor_width
    az, el = math.radians(14.0), math.radians(3.0)
    d = Vector((math.sin(az) * math.cos(el), -math.cos(az) * math.cos(el), math.sin(el)))
    cam.location = target + d * dist
    cam.rotation_euler = (-d).to_track_quat("-Z", "Y").to_euler()
    cam_data.dof.use_dof = True
    cam_data.dof.focus_distance = dist - 0.10
    cam_data.dof.aperture_fstop = 6.3
    log("camera dist=%.2f frame=%.2f x %.2f" % (
        dist, 1.34, 1.34 * res_y / RES_X))
    return res_y


def setup_render(res_y):
    scn = bpy.context.scene
    if ENGINE.startswith("cyc"):
        scn.render.engine = "CYCLES"
        scn.cycles.samples = SAMPLES
        scn.cycles.use_denoising = True
        scn.cycles.max_bounces = 16
        scn.cycles.transmission_bounces = 12
        scn.cycles.transparent_max_bounces = 16
    else:
        for eng in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE"):
            try:
                scn.render.engine = eng
                break
            except TypeError:
                continue
        ee = getattr(scn, "eevee", None)
        for attr, val in (("taa_render_samples", SAMPLES), ("use_raytracing", True),
                          ("use_bloom", True), ("use_shadows", True)):
            if ee is not None and hasattr(ee, attr):
                setattr(ee, attr, val)
    scn.render.resolution_x, scn.render.resolution_y = RES_X, res_y
    scn.render.image_settings.file_format = "PNG"
    for tr in ("AgX", "Filmic", "Standard"):
        try:
            scn.view_settings.view_transform = tr
            break
        except TypeError:
            continue
    scn.view_settings.exposure = 0.0
    log("engine=%s samples=%d res=%dx%d" % (scn.render.engine, SAMPLES, RES_X, res_y))


def main():
    parse_args()
    clean_scene()
    crystal = mat("Crystal", (0.72, 0.90, 0.98), roughness=0.020, transmission=1.0,
                  ior=1.62, coat=0.25)
    core = mat("CrystalCore", (0.12, 0.55, 1.0), roughness=0.20, transmission=0.20,
               ior=1.45, emission=(0.10, 0.62, 1.0), emission_strength=3.0)
    glow = mat("Glow", (0.25, 0.75, 1.0), roughness=0.2,
               emission=(0.20, 0.75, 1.0), emission_strength=2.2)
    gold = mat("Gold", (0.80, 0.62, 0.30), roughness=0.24, metallic=1.0)
    lacquer = mat("Lacquer", (0.26, 0.035, 0.05), roughness=0.32, coat=0.7)
    cord = mat("Cord", (0.38, 0.055, 0.07), roughness=0.62)
    silk = mat("Silk", (0.58, 0.05, 0.08), roughness=0.45, sheen=0.7)

    build_blade("Blade", crystal)                                   # 外层水晶剑身
    build_blade("BladeCore", core, scale_xy=0.58, z0=0.012, length=BLADE_LEN * 0.93)
    build_hilt(gold, crystal, lacquer, cord, silk, glow)
    build_shards(crystal, glow)
    res_y = build_studio()
    setup_render(res_y)

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    bpy.context.scene.render.filepath = OUT
    log("rendering -> %s" % OUT)
    bpy.ops.render.render(write_still=True)
    ok = os.path.exists(OUT)
    log("RESULT ok=%s size=%d %s" % (ok, os.path.getsize(OUT) if ok else 0, OUT))
    blend = os.path.join(os.path.dirname(os.path.dirname(OUT)), "crystal_sword.blend")
    bpy.ops.wm.save_as_mainfile(filepath=blend)
    log("saved scene -> %s" % blend)
    if not ok:
        sys.exit(3)


main()

