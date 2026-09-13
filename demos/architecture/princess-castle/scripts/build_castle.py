"""公主城堡 (fairy-tale princess castle): 程序化建模 + 渲染。

    blender -b --factory-startup --python demos/architecture/princess-castle/scripts/build_castle.py -- \
        [--out <png>] [--engine cycles|eevee] [--samples 128] [--res 1440]

奶油色石墙 + 粉紫锥顶 + 金色顶尖 + 旗帜, 中央主塔配四座角塔、城墙垛口、拱门门楼、
台阶与岩石台基, 夕阳侧逆光。跑完存 princess_castle.blend。
"""
import math
import os
import random
import sys

import bmesh
import bpy
from mathutils import Vector

# --- 总体尺寸 (Blender 单位 ~ 米) ---
KEEP_R = 1.15               # 主塔半径
KEEP_H = 6.4                # 主塔墙体高度
TOWER_SPEC = [              # 角塔: (x, y, 半径, 墙高)
    (-3.1, -3.1, 0.62, 4.2),
    (3.1, -3.1, 0.62, 4.6),
    (-3.1, 3.1, 0.70, 5.2),
    (3.1, 3.1, 0.55, 3.8),
]
WALL_H = 2.7                # 城墙高度
WALL_T = 0.42               # 城墙厚度
BASE_R = 5.6                # 台基半径
GATE_W = 1.5                # 门洞宽

OUT = ""
ENGINE = "cycles"
SAMPLES = 128
RES_X = 1440
RNG = random.Random(11)


def log(msg):
    print("[castle]", msg, flush=True)


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
        OUT = os.path.join(os.path.dirname(here), "render", "princess_castle.png")


def clean_scene():
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)


def set_in(node, name, value):
    sock = node.inputs.get(name)
    if sock is not None:
        sock.default_value = value


def mat(name, color, roughness=0.6, metallic=0.0, emission=None, emission_strength=0.0,
        noise=0.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    set_in(bsdf, "Base Color", (*color, 1.0))
    set_in(bsdf, "Roughness", roughness)
    set_in(bsdf, "Metallic", metallic)
    if emission is not None:
        set_in(bsdf, "Emission Color", (*emission, 1.0))
        set_in(bsdf, "Emission Strength", emission_strength)
    if noise:                       # 石材/屋瓦的细微起伏
        tex = nt.nodes.new("ShaderNodeTexNoise")
        tex.inputs["Scale"].default_value = 22.0
        tex.inputs["Detail"].default_value = 6.0
        bump = nt.nodes.new("ShaderNodeBump")
        bump.inputs["Strength"].default_value = noise
        bump.inputs["Distance"].default_value = 0.02
        nt.links.new(tex.outputs["Fac"], bump.inputs["Height"])
        nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    return m


def shade(obj, smooth=True):
    for p in obj.data.polygons:
        p.use_smooth = smooth
    return obj


def cyl(name, r1, r2, h, material, loc=(0, 0, 0), rot=(0, 0, 0), verts=40, smooth=True):
    bpy.ops.mesh.primitive_cone_add(radius1=r1, radius2=r2, depth=h, vertices=verts,
                                    location=loc, rotation=rot)
    obj = bpy.context.object
    obj.name = name
    obj.data.materials.append(material)
    return shade(obj, smooth)


def box(name, size, material, loc=(0, 0, 0), rot=(0, 0, 0)):
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=loc, rotation=rot)
    obj = bpy.context.object
    obj.name = name
    obj.scale = size
    obj.data.materials.append(material)
    return obj


def ball(name, r, material, loc=(0, 0, 0), scale=(1, 1, 1)):
    bpy.ops.mesh.primitive_uv_sphere_add(radius=r, segments=32, ring_count=16, location=loc)
    obj = bpy.context.object
    obj.name, obj.scale = name, scale
    obj.data.materials.append(material)
    return shade(obj)


def ring(name, major, minor, material, loc=(0, 0, 0), rot=(0, 0, 0)):
    bpy.ops.mesh.primitive_torus_add(major_radius=major, minor_radius=minor,
                                     major_segments=40, minor_segments=12,
                                     location=loc, rotation=rot)
    obj = bpy.context.object
    obj.name = name
    obj.data.materials.append(material)
    return obj


def window(prefix, cx, cy, r, z, ang, M, w=0.20, h=0.40):
    """朝外的拱窗: 石框 + 暖光玻璃 + 半圆拱顶。"""
    ca, sa = math.cos(ang), math.sin(ang)
    px, py = cx + (r - 0.02) * ca, cy + (r - 0.02) * sa
    box("%sFrame" % prefix, (0.10, w + 0.10, h + 0.10), M["trim"], (px, py, z), (0, 0, ang))
    box("%sGlass" % prefix, (0.12, w, h), M["glass"],
        (px + 0.03 * ca, py + 0.03 * sa, z), (0, 0, ang))
    ball("%sArch" % prefix, (w + 0.10) / 2, M["trim"],
         (px, py, z + h / 2), scale=(0.5, 1.0, 0.8))
    ball("%sArchGlass" % prefix, w / 2, M["glass"],
         (px + 0.03 * ca, py + 0.03 * sa, z + h / 2), scale=(0.6, 1.0, 0.8))


def tower(name, x, y, r, h, M, roof_ratio=2.6, flag_color="pink", windows=True):
    """圆塔: 台座 + 塔身 + 檐口 + 锥顶 + 尖顶 + 旗。"""
    cyl("%sBase" % name, r * 1.16, r * 1.02, 0.40, M["stone"], (x, y, 0.20))
    cyl("%sBody" % name, r, r * 0.97, h, M["stone"], (x, y, h / 2))
    ring("%sCornice" % name, r * 1.02, 0.055, M["trim"], (x, y, h * 0.98))
    ring("%sBand" % name, r * 1.01, 0.035, M["trim"], (x, y, h * 0.52))
    roof_h = r * roof_ratio
    cyl("%sRoof" % name, r * 1.20, 0.0, roof_h, M["roof"], (x, y, h + roof_h / 2), verts=32)
    top = h + roof_h
    cyl("%sSpire" % name, 0.05, 0.0, 0.42, M["gold"], (x, y, top + 0.18), verts=16)
    ball("%sFinial" % name, 0.075, M["gold"], (x, y, top + 0.02))
    # 旗: 细旗杆 + 一面小旗
    cyl("%sPole" % name, 0.018, 0.018, 0.62, M["trim"], (x, y, top + 0.62), verts=8)
    box("%sFlag" % name, (0.02, 0.34, 0.20), M[flag_color],
        (x, y + 0.17, top + 0.82), (0, 0, RNG.uniform(-0.3, 0.3)))
    if windows:
        for i, ang in enumerate((-0.5, 0.9, 2.4)):
            window("%sW%d" % (name, i), x, y, r, h * 0.42, ang, M)
        for i, ang in enumerate((-0.2, 1.6)):
            window("%sV%d" % (name, i), x, y, r, h * 0.75, ang, M, w=0.16, h=0.30)


def wall(name, p0, p1, M, height=None):
    """城墙: 墙体 + 走道 + 垛口。"""
    height = WALL_H if height is None else height
    p0, p1 = Vector(p0), Vector(p1)
    d = p1 - p0
    length = d.length
    ang = math.atan2(d.y, d.x)
    mid = (p0 + p1) / 2
    box("%sBody" % name, (length, WALL_T, height), M["stone"],
        (mid.x, mid.y, height / 2), (0, 0, ang))
    box("%sWalk" % name, (length, WALL_T * 1.24, 0.10), M["trim"],
        (mid.x, mid.y, height + 0.05), (0, 0, ang))
    n = max(2, int(length / 0.66))
    for i in range(n):
        t = (i + 0.5) / n
        p = p0 + d * t
        box("%sMerlon%d" % (name, i), (0.36, WALL_T * 1.18, 0.34), M["stone"],
            (p.x, p.y, height + 0.27), (0, 0, ang))


def gatehouse(M):
    """门楼: 整块正面墙 + 半圆拱券 + 木门 + 侧塔 + 台阶。"""
    y = -3.1
    half = GATE_W / 2 + 0.62
    box("GateBlock", (half * 2, 1.05, 3.45), M["stone"], (0, y, 1.72))
    box("GateCap", (half * 2 + 0.22, 1.22, 0.18), M["trim"], (0, y, 3.53))
    for s in (-1, 1):
        box("GatePier%d" % s, (0.42, 1.22, 3.2), M["trim"], (half * 0.78 * s, y, 1.60))
        cyl("GateTurret%d" % s, 0.30, 0.0, 0.85, M["roof"],
            (half * 0.78 * s, y, 4.05), verts=20)
        cyl("GateTurretBody%d" % s, 0.24, 0.24, 0.55, M["stone"],
            (half * 0.78 * s, y, 3.85), verts=20)
    # 拱券: 一圈小石块
    steps = 11
    for i in range(steps):
        a = math.pi * i / (steps - 1)
        box("GateArch%d" % i, (0.26, 1.16, 0.20), M["trim"],
            (math.cos(a) * GATE_W / 2 * 1.02, y, 1.95 + math.sin(a) * GATE_W / 2 * 0.92),
            (0, -a + math.pi / 2, 0))
    box("GateDoor", (GATE_W - 0.06, 0.16, 2.05), M["wood"], (0, y - 0.44, 1.02))
    ball("GateDoorTop", (GATE_W - 0.06) / 2, M["wood"], (0, y - 0.44, 2.05),
         scale=(1.0, 0.16 / (GATE_W - 0.06) * 2, 0.34))
    for i in range(3):
        box("GateBar%d" % i, (GATE_W - 0.06, 0.06, 0.09), M["trim"],
            (0, y - 0.53, 0.40 + i * 0.62))
    for i in range(3):                          # 台阶: 全部叠在广场面之上, 避免与地面共面发黑
        w = GATE_W + 1.4 - i * 0.16
        box("Step%d" % i, (w, 0.46, 0.16), M["stone"],
            (0, y - 0.90 - i * 0.42, 0.26 - i * 0.12))


def keep(M):
    """中央主塔 + 侧附小塔 + 玫瑰窗 + 阳台 + 后侧大厅。"""
    tower("Keep", 0.0, 0.55, KEEP_R, KEEP_H, M, roof_ratio=3.1, flag_color="violet")
    tower("KeepTurret", KEEP_R * 0.92, 0.05, 0.30, KEEP_H * 0.86, M,
          roof_ratio=3.4, flag_color="pink", windows=False)
    # 玫瑰窗 (朝 -Y)
    ring("RoseFrame", 0.30, 0.055, M["trim"], (0, 0.55 - KEEP_R + 0.02, KEEP_H * 0.70),
         rot=(math.pi / 2, 0, 0))
    cyl("RoseGlass", 0.28, 0.28, 0.06, M["rose"],
        (0, 0.55 - KEEP_R + 0.04, KEEP_H * 0.70), rot=(math.pi / 2, 0, 0), verts=24)
    for i in range(6):                          # 花瓣格
        a = math.pi * i / 6
        box("RoseSpoke%d" % i, (0.56, 0.05, 0.035), M["trim"],
            (0, 0.55 - KEEP_R + 0.01, KEEP_H * 0.70), (0, a, 0))
    # 阳台
    ring("Balcony", KEEP_R * 1.20, 0.09, M["trim"], (0, 0.55, KEEP_H * 0.50))
    for i in range(18):
        a = 2 * math.pi * i / 18
        box("Baluster%d" % i, (0.06, 0.06, 0.24), M["trim"],
            (KEEP_R * 1.16 * math.cos(a), 0.55 + KEEP_R * 1.16 * math.sin(a),
             KEEP_H * 0.50 + 0.14), (0, 0, a))
    # 后侧大厅 + 双坡屋顶
    box("Hall", (3.0, 2.1, 2.3), M["stone"], (0, 2.55, 1.15))
    for s in (-1, 1):
        box("HallRoof%d" % s, (3.2, 1.30, 0.12), M["roof"],
            (0, 2.55 + 0.55 * s, 2.72), (0.62 * -s, 0, 0))
    box("HallRidge", (3.24, 0.14, 0.14), M["trim"], (0, 2.55, 3.06))
    for i, x in enumerate((-1.0, 0.0, 1.0)):
        box("HallWin%d" % i, (0.34, 0.12, 0.7), M["glass"], (x, 2.55 - 1.05, 1.35))
        box("HallWinFrame%d" % i, (0.44, 0.10, 0.8), M["trim"], (x, 2.55 - 1.09, 1.35))


def terrain(M):
    """岩石台基 + 草地 + 门前小路。"""
    cyl("Plaza", BASE_R, BASE_R * 0.97, 0.5, M["stone"], (0, 0, -0.25), verts=48)
    cyl("Rock1", BASE_R * 0.97, BASE_R * 0.80, 0.9, M["rock"], (0, 0, -0.95), verts=32,
        smooth=False)
    cyl("Rock2", BASE_R * 0.80, BASE_R * 0.52, 1.1, M["rock"], (0, 0, -1.95), verts=24,
        smooth=False)
    cyl("Rock3", BASE_R * 0.52, BASE_R * 0.30, 1.2, M["rock"], (0, 0, -3.10), verts=18,
        smooth=False)
    bpy.ops.mesh.primitive_plane_add(size=90.0, location=(0, 0, -3.68))
    ground = bpy.context.object
    ground.name = "Ground"
    ground.data.materials.append(M["grass"])
    for i in range(11):                         # 门前石阶小路, 缓坡下到地面
        box("Path%d" % i, (2.0 + i * 0.06, 0.9, 0.14), M["stone"],
            (0, -BASE_R - 0.4 - i * 0.85, -0.05 - i * 0.32))


def build_studio(M):
    sun = bpy.data.lights.new("Sun", type="SUN")
    sun.energy = 6.0
    sun.color = (1.0, 0.86, 0.68)
    sun.angle = math.radians(2.5)
    sun_obj = bpy.data.objects.new("Sun", sun)
    bpy.context.scene.collection.objects.link(sun_obj)
    # 主光从相机侧前方左上打来: 迎光面在正面偏左, 右侧转入暗部, 投影向右后拉长
    sun_obj.rotation_euler = (math.radians(45), 0.0, math.radians(-45))
    fill = bpy.data.lights.new("Fill", type="AREA")
    fill.energy, fill.size = 90, 12.0
    fill.color = (0.66, 0.78, 1.0)
    fill_obj = bpy.data.objects.new("Fill", fill)
    bpy.context.scene.collection.objects.link(fill_obj)
    fill_obj.location = (9.0, -9.0, 7.0)
    fill_obj.visible_camera = False
    fill_obj.rotation_euler = (Vector((0, 0, 3.0)) - Vector(fill_obj.location)
                               ).normalized().to_track_quat("-Z", "Y").to_euler()

    world = bpy.data.worlds[0] if bpy.data.worlds else bpy.data.worlds.new("W")
    bpy.context.scene.world = world
    world.use_nodes = True
    nt = world.node_tree
    for node in list(nt.nodes):
        if node.type != "OUTPUT_WORLD":
            nt.nodes.remove(node)
    out = next(n for n in nt.nodes if n.type == "OUTPUT_WORLD")
    sky = nt.nodes.new("ShaderNodeTexSky")
    try:
        sky.sky_type = "NISHITA"
        sky.sun_elevation = math.radians(18)
        sky.sun_rotation = math.radians(215)
        sky.altitude = 300
        sky.air_density = 1.2
        sky.dust_density = 1.2
    except (AttributeError, TypeError):
        pass
    # 天空只给相机看到的背景全亮度, 参与照明的部分压暗, 让太阳的方向光成为主光
    bright = nt.nodes.new("ShaderNodeBackground")
    bright.inputs[1].default_value = 1.0
    dim = nt.nodes.new("ShaderNodeBackground")
    dim.inputs[1].default_value = 0.04
    mix = nt.nodes.new("ShaderNodeMixShader")
    lp = nt.nodes.new("ShaderNodeLightPath")
    nt.links.new(sky.outputs[0], bright.inputs[0])
    nt.links.new(sky.outputs[0], dim.inputs[0])
    nt.links.new(lp.outputs["Is Camera Ray"], mix.inputs["Fac"])
    nt.links.new(dim.outputs[0], mix.inputs[1])
    nt.links.new(bright.outputs[0], mix.inputs[2])
    nt.links.new(mix.outputs[0], out.inputs[0])

    cam_data = bpy.data.cameras.new("Cam")
    cam_data.lens = 55.0
    cam_data.sensor_fit = "HORIZONTAL"
    cam = bpy.data.objects.new("Cam", cam_data)
    bpy.context.scene.collection.objects.link(cam)
    bpy.context.scene.camera = cam
    res_y = int(RES_X * 3 / 4)
    target = Vector((0.0, 0.40, 3.70))
    dist = 27.5
    az, el = math.radians(36.0), math.radians(14.0)
    d = Vector((math.sin(az) * math.cos(el), -math.cos(az) * math.cos(el), math.sin(el)))
    cam.location = target + d * dist
    cam.rotation_euler = (-d).to_track_quat("-Z", "Y").to_euler()
    log("camera dist=%.1f frame=%.1f x %.1f" % (
        dist, dist * cam_data.sensor_width / cam_data.lens,
        dist * cam_data.sensor_width / cam_data.lens * 3 / 4))
    return res_y


def materials():
    return {
        "stone": mat("Stone", (0.90, 0.86, 0.77), roughness=0.66, noise=0.25),
        "trim": mat("Trim", (0.97, 0.94, 0.88), roughness=0.52, noise=0.12),
        "roof": mat("Roof", (0.70, 0.36, 0.56), roughness=0.44, noise=0.30),
        "pink": mat("FlagPink", (0.95, 0.52, 0.70), roughness=0.6),
        "violet": mat("FlagViolet", (0.60, 0.42, 0.86), roughness=0.6),
        "gold": mat("Gold", (0.86, 0.68, 0.28), roughness=0.26, metallic=1.0),
        "glass": mat("WindowGlow", (1.0, 0.84, 0.55), roughness=0.25,
                     emission=(1.0, 0.78, 0.42), emission_strength=2.6),
        "rose": mat("RoseGlass", (0.95, 0.55, 0.85), roughness=0.2,
                    emission=(0.95, 0.50, 0.85), emission_strength=2.2),
        "wood": mat("Wood", (0.33, 0.20, 0.13), roughness=0.62, noise=0.3),
        "rock": mat("Rock", (0.44, 0.42, 0.41), roughness=0.85, noise=0.7),
        "grass": mat("Grass", (0.33, 0.50, 0.25), roughness=0.8, noise=0.2),
    }


def setup_render(res_y):
    scn = bpy.context.scene
    if ENGINE.startswith("cyc"):
        scn.render.engine = "CYCLES"
        scn.cycles.samples = SAMPLES
        scn.cycles.use_denoising = True
        scn.cycles.max_bounces = 8
    else:
        for eng in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE"):
            try:
                scn.render.engine = eng
                break
            except TypeError:
                continue
        ee = getattr(scn, "eevee", None)
        for attr, val in (("taa_render_samples", SAMPLES), ("use_raytracing", True),
                          ("use_gtao", True), ("use_shadows", True)):
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
    M = materials()
    terrain(M)
    keep(M)
    for i, (x, y, r, h) in enumerate(TOWER_SPEC):
        tower("T%d" % i, x, y, r, h, M,
              flag_color="pink" if i % 2 else "violet")
    c = [(-3.1, -3.1), (3.1, -3.1), (3.1, 3.1), (-3.1, 3.1)]
    wall("WallS0", c[0], (-GATE_W / 2 - 0.62, -3.1), M)
    wall("WallS1", (GATE_W / 2 + 0.62, -3.1), c[1], M)
    wall("WallE", c[1], c[2], M)
    wall("WallN", c[2], c[3], M)
    wall("WallW", c[3], c[0], M)
    gatehouse(M)
    res_y = build_studio(M)
    setup_render(res_y)
    log("objects=%d" % len(bpy.data.objects))

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    bpy.context.scene.render.filepath = OUT
    log("rendering -> %s" % OUT)
    bpy.ops.render.render(write_still=True)
    ok = os.path.exists(OUT)
    log("RESULT ok=%s size=%d %s" % (ok, os.path.getsize(OUT) if ok else 0, OUT))
    blend = os.path.join(os.path.dirname(os.path.dirname(OUT)), "princess_castle.blend")
    bpy.ops.wm.save_as_mainfile(filepath=blend)
    log("saved scene -> %s" % blend)
    if not ok:
        sys.exit(3)


main()

