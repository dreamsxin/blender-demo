"""清明上河图 低多边形长卷动画: 程序化建城 + 横移镜头 + EEVEE 出片。

    blender -b --factory-startup --python demos/scene/qingming-scroll/scripts/build_scroll.py -- \
        [--seconds 3] [--fps 24] [--res 1280] [--samples 32] [--engine eevee|cycles] [--still-only]

沿 X 轴铺开一条汴河: 虹桥、两岸木构屋舍酒楼、货船、垂柳、赶集的人;
镜头像展开长卷一样横向平移。默认先出 3 秒 720p 预览, 同时存一张海报图和场景。
"""
import math
import os
import random
import sys

import bmesh
import bpy
from mathutils import Vector

SECONDS = 3.0
FPS = 24
RES_X = 1280
SAMPLES = 32
ENGINE = "eevee"
STILL_ONLY = False
OUT_DIR = ""

RIVER_HALF = 3.4            # 河道半宽
BANK_H = 0.55               # 岸高
SCROLL_FROM = -13.0         # 镜头起点 x
SCROLL_TO = 9.0             # 镜头终点 x
RNG = random.Random(20250912)


def log(msg):
    print("[scroll]", msg, flush=True)


def parse_args():
    global SECONDS, FPS, RES_X, SAMPLES, ENGINE, STILL_ONLY, OUT_DIR
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    for flag in ("--seconds", "--fps", "--res", "--samples", "--engine", "--out-dir"):
        if flag not in argv:
            continue
        v = argv[argv.index(flag) + 1]
        if flag == "--seconds":
            SECONDS = float(v)
        elif flag == "--fps":
            FPS = int(v)
        elif flag == "--res":
            RES_X = int(v)
        elif flag == "--samples":
            SAMPLES = int(v)
        elif flag == "--engine":
            ENGINE = v.lower()
        else:
            OUT_DIR = v
    STILL_ONLY = "--still-only" in argv
    if not OUT_DIR:
        here = os.path.dirname(os.path.abspath(globals().get("__file__", ".")))
        OUT_DIR = os.path.join(os.path.dirname(here), "render")


def clean_scene():
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)


def set_in(node, name, value):
    sock = node.inputs.get(name)
    if sock is not None:
        sock.default_value = value


def mat(name, color, roughness=0.62, metallic=0.0, emission=None, emission_strength=0.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    bsdf = m.node_tree.nodes["Principled BSDF"]
    set_in(bsdf, "Base Color", (*color, 1.0))
    set_in(bsdf, "Roughness", roughness)
    set_in(bsdf, "Metallic", metallic)
    if emission is not None:
        set_in(bsdf, "Emission Color", (*emission, 1.0))
        set_in(bsdf, "Emission Strength", emission_strength)
    return m


def flat(obj):
    """低多边形风格: 全部平面着色。"""
    for p in obj.data.polygons:
        p.use_smooth = False
    return obj


def box(name, size, material, loc=(0, 0, 0), rot=(0, 0, 0)):
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=loc, rotation=rot)
    obj = bpy.context.object
    obj.name, obj.scale = name, size
    obj.data.materials.append(material)
    return obj


def cyl(name, r1, r2, h, material, loc=(0, 0, 0), rot=(0, 0, 0), verts=8):
    bpy.ops.mesh.primitive_cone_add(radius1=r1, radius2=r2, depth=h, vertices=verts,
                                    location=loc, rotation=rot)
    obj = bpy.context.object
    obj.name = name
    obj.data.materials.append(material)
    return flat(obj)


def ico(name, r, material, loc=(0, 0, 0), scale=(1, 1, 1), subdiv=1):
    bpy.ops.mesh.primitive_ico_sphere_add(radius=r, subdivisions=subdiv, location=loc)
    obj = bpy.context.object
    obj.name, obj.scale = name, scale
    obj.data.materials.append(material)
    return flat(obj)


def wedge(name, w, d, h, material, loc=(0, 0, 0), rot=(0, 0, 0)):
    """三角棱柱: 低多边形屋顶用。"""
    bm = bmesh.new()
    pts = [(-w / 2, -d / 2, 0), (w / 2, -d / 2, 0), (0, -d / 2, h),
           (-w / 2, d / 2, 0), (w / 2, d / 2, 0), (0, d / 2, h)]
    vs = [bm.verts.new(p) for p in pts]
    for f in ((0, 1, 2), (5, 4, 3), (0, 2, 5, 3), (2, 1, 4, 5), (1, 0, 3, 4)):
        bm.faces.new([vs[i] for i in f])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    obj = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(obj)
    obj.location, obj.rotation_euler = loc, rot
    obj.data.materials.append(material)
    return flat(obj)


def palette():
    return {
        "water": mat("Water", (0.16, 0.42, 0.52), roughness=0.18),
        "earth": mat("Earth", (0.60, 0.48, 0.34), roughness=0.85),
        "road": mat("Road", (0.74, 0.64, 0.48), roughness=0.8),
        "grass": mat("Grass", (0.40, 0.56, 0.28), roughness=0.8),
        "wood": mat("Wood", (0.44, 0.27, 0.16), roughness=0.7),
        "wood2": mat("WoodLight", (0.70, 0.50, 0.30), roughness=0.7),
        "tile": mat("RoofTile", (0.34, 0.33, 0.38), roughness=0.6),
        "thatch": mat("Thatch", (0.74, 0.57, 0.29), roughness=0.8),
        "wall": mat("Wall", (0.91, 0.87, 0.77), roughness=0.7),
        "red": mat("Lacquer", (0.76, 0.21, 0.17), roughness=0.5),
        "banner": mat("Banner", (0.93, 0.83, 0.38), roughness=0.6),
        "cloth": mat("Cloth", (0.86, 0.81, 0.64), roughness=0.75),
        "leaf": mat("Leaf", (0.33, 0.55, 0.27), roughness=0.75),
        "leaf2": mat("Leaf2", (0.46, 0.63, 0.30), roughness=0.75),
        "lantern": mat("Lantern", (1.0, 0.72, 0.34), roughness=0.4,
                       emission=(1.0, 0.62, 0.26), emission_strength=3.0),
        "skin": mat("Skin", (0.93, 0.76, 0.60), roughness=0.6),
    }


PEOPLE_COLORS = [(0.80, 0.30, 0.24), (0.24, 0.34, 0.55), (0.36, 0.46, 0.32),
                 (0.86, 0.82, 0.70), (0.55, 0.35, 0.60), (0.90, 0.62, 0.24)]


def terrain(P):
    box("River", (60.0, RIVER_HALF * 2, 0.2), P["water"], (-2, 0, -0.10))
    for s in (-1, 1):
        box("Bank%d" % s, (60.0, 9.0, BANK_H), P["earth"],
            (-2, s * (RIVER_HALF + 4.5), BANK_H / 2 - 0.02))
        box("Road%d" % s, (60.0, 2.6, 0.06), P["road"],
            (-2, s * (RIVER_HALF + 1.5), BANK_H + 0.01))
        box("Quay%d" % s, (60.0, 0.5, 0.5), P["wood2"],
            (-2, s * (RIVER_HALF + 0.2), BANK_H - 0.22))
    box("Field", (60.0, 10.0, 0.1), P["grass"], (-2, 12.5, BANK_H - 0.02))


def rainbow_bridge(x0, P, people):
    """虹桥: 拱形木桥面 + 栏杆 + 桥下叠梁 + 桥上行人。"""
    span, rise, seg = RIVER_HALF * 2 + 2.4, 1.55, 14
    for i in range(seg):
        t0, t1 = i / seg, (i + 1) / seg
        y0, y1 = -span / 2 + span * t0, -span / 2 + span * t1
        z0 = BANK_H + rise * math.sin(math.pi * t0)
        z1 = BANK_H + rise * math.sin(math.pi * t1)
        dy, dz = y1 - y0, z1 - z0
        length = math.hypot(dy, dz)
        box("BridgeDeck%d" % i, (2.2, length, 0.14), P["wood2"],
            (x0, (y0 + y1) / 2, (z0 + z1) / 2), (math.atan2(dz, dy), 0, 0))
        for s in (-1, 1):
            box("BridgeRail%d%d" % (i, s), (0.10, length, 0.42), P["wood"],
                (x0 + 1.05 * s, (y0 + y1) / 2, (z0 + z1) / 2 + 0.28),
                (math.atan2(dz, dy), 0, 0))
        if i % 3 == 0:                      # 桥下叠梁
            box("BridgeBeam%d" % i, (1.9, length * 1.1, 0.1), P["wood"],
                (x0, (y0 + y1) / 2, (z0 + z1) / 2 - 0.34), (math.atan2(dz, dy), 0, 0))
    for i in range(7):                      # 桥上赶集的人
        t = 0.14 + 0.12 * i
        people.append((x0 + RNG.uniform(-0.7, 0.7),
                       -span / 2 + span * t,
                       BANK_H + rise * math.sin(math.pi * t) + 0.07))


def house(x, y, side, P, two_story=False, shop=False):
    """低多边形宋式屋舍: 木架 + 白墙 + 悬山瓦顶, 临街挂幌子。"""
    w, d = RNG.uniform(2.2, 3.2), RNG.uniform(2.0, 2.6)
    h = RNG.uniform(1.5, 1.9)
    z0 = BANK_H
    box("HouseBody", (w, d, h), P["wall"], (x, y, z0 + h / 2))
    for sx in (-1, 1):                      # 木柱
        box("HousePost", (0.14, 0.14, h), P["wood"], (x + sx * (w / 2 - 0.07), y, z0 + h / 2))
    roof = P["tile"] if RNG.random() < 0.65 else P["thatch"]
    wedge("HouseRoof", w + 0.7, d + 0.7, 0.75, roof, (x, y, z0 + h),
          (0, 0, math.pi / 2))
    if two_story:
        box("Floor2", (w * 0.9, d * 0.9, 1.4), P["wall"], (x, y, z0 + h + 0.7 + 0.05))
        box("Balcony", (w * 1.02, d * 1.02, 0.1), P["wood2"], (x, y, z0 + h + 0.1))
        for sx in (-1, 1):
            box("Rail2", (w * 1.02, 0.08, 0.32), P["wood"],
                (x, y + sx * d * 0.51, z0 + h + 0.28))
        wedge("Roof2", w * 0.9 + 0.8, d * 0.9 + 0.8, 0.8, roof,
              (x, y, z0 + h + 1.45), (0, 0, math.pi / 2))
    box("Door", (0.8, 0.1, 1.1), P["wood"], (x, y - side * (d / 2 + 0.02), z0 + 0.55))
    for sx in (-0.6, 0.6):
        box("Window", (0.55, 0.08, 0.5), P["wood2"],
            (x + sx * w / 2, y - side * (d / 2 + 0.02), z0 + h * 0.62))
    if shop:                                # 幌子 + 灯笼
        px = x + w / 2 + 0.25
        cyl("ShopPole", 0.05, 0.05, 2.6, P["wood"], (px, y - side * d / 2, z0 + 1.3))
        box("ShopBanner", (0.09, 0.34, 1.15), P["red"],
            (px + 0.02, y - side * (d / 2 + 0.18), z0 + 1.55))
        ico("Lantern", 0.16, P["lantern"], (px - 0.5, y - side * (d / 2 + 0.3), z0 + 1.9),
            scale=(1.0, 1.0, 1.15))


def boat(name, x, y, ang, P, people, awning=True, mast=False):
    """平底货船: 船身 + 翘起的船头船尾 + 篷 + 船工。"""
    parts = []
    parts.append(box(name + "Hull", (2.9, 0.95, 0.34), P["wood"], (x, y, 0.06), (0, 0, ang)))
    for s in (-1, 1):
        parts.append(wedge(name + "Bow%d" % s, 0.95, 0.9, 0.34, P["wood"],
                           (x + s * 1.7 * math.cos(ang), y + s * 1.7 * math.sin(ang), 0.06),
                           (0, math.pi / 2 * -s, ang)))
    parts.append(box(name + "Deck", (2.6, 0.8, 0.06), P["wood2"], (x, y, 0.24), (0, 0, ang)))
    if awning:
        for i, sz in enumerate((0.9, 1.0, 0.9)):
            parts.append(box(name + "Awn%d" % i, (0.55, sz, 0.07), P["cloth"],
                             (x + (i - 1) * 0.6 * math.cos(ang),
                              y + (i - 1) * 0.6 * math.sin(ang), 0.62 + (1 - abs(i - 1)) * 0.08),
                             (0, 0, ang)))
        for sx in (-0.85, 0.85):
            parts.append(cyl(name + "AwnPost", 0.04, 0.04, 0.42, P["wood"],
                             (x + sx * math.cos(ang), y + sx * math.sin(ang), 0.42)))
    if mast:
        parts.append(cyl(name + "Mast", 0.06, 0.05, 2.6, P["wood"], (x, y, 1.4)))
        parts.append(box(name + "Sail", (0.08, 0.9, 1.5), P["cloth"], (x, y, 1.75), (0, 0, ang)))
    people.append((x - 1.0 * math.cos(ang), y - 1.0 * math.sin(ang), 0.30))
    people.append((x + 0.9 * math.cos(ang), y + 0.9 * math.sin(ang), 0.30))
    return parts


def willow(x, y, P):
    cyl("Trunk", 0.11, 0.08, 1.5, P["wood"], (x, y, BANK_H + 0.75))
    for i in range(4):
        a = 2 * math.pi * i / 4 + RNG.uniform(-0.3, 0.3)
        ico("Leaves", RNG.uniform(0.55, 0.75), P["leaf"] if i % 2 else P["leaf2"],
            (x + 0.35 * math.cos(a), y + 0.35 * math.sin(a),
             BANK_H + RNG.uniform(1.5, 2.0)),
            scale=(1.0, 1.0, 0.55))


def stall(x, y, side, P, people):
    box("StallTable", (1.5, 0.8, 0.1), P["wood2"], (x, y, BANK_H + 0.55))
    for sx in (-0.65, 0.65):
        for sy in (-0.3, 0.3):
            cyl("StallLeg", 0.05, 0.05, 0.55, P["wood"], (x + sx, y + sy, BANK_H + 0.28))
    wedge("StallRoof", 1.9, 1.3, 0.35, P["cloth"], (x, y, BANK_H + 1.25), (0, 0, math.pi / 2))
    for sx in (-0.8, 0.8):
        cyl("StallPole", 0.04, 0.04, 1.25, P["wood"], (x + sx, y, BANK_H + 0.62))
    for i in range(3):
        box("Goods", (0.25, 0.25, 0.16), P["red"] if i % 2 else P["banner"],
            (x - 0.5 + i * 0.5, y, BANK_H + 0.68))
    people.append((x, y - side * 0.75, BANK_H + 0.05))


def crowd(P, spots):
    """一堆低多边形小人: 身体 + 头 + 一半戴斗笠。"""
    for i, (x, y, z) in enumerate(spots):
        c = PEOPLE_COLORS[i % len(PEOPLE_COLORS)]
        body_m = mat("Robe%d" % i, c, roughness=0.7)
        cyl("Body%d" % i, 0.105, 0.075, 0.34, body_m, (x, y, z + 0.17), verts=7)
        ico("Head%d" % i, 0.075, P["skin"], (x, y, z + 0.40), subdiv=1)
        if i % 3 == 0:
            cyl("Hat%d" % i, 0.17, 0.02, 0.09, P["thatch"], (x, y, z + 0.47), verts=8)


def build_town(P):
    people = []
    terrain(P)
    rainbow_bridge(0.0, P, people)
    for i in range(9):                      # 近岸 (朝镜头) 屋舍
        x = -14.5 + i * 2.9
        if abs(x) < 2.2:
            continue
        house(x, -(RIVER_HALF + 4.3), -1, P, two_story=(i % 4 == 1), shop=(i % 2 == 0))
    for i in range(9):                      # 对岸屋舍
        x = -13.2 + i * 2.9
        if abs(x) < 2.2:
            continue
        house(x, RIVER_HALF + 3.6, 1, P, two_story=(i % 3 == 0), shop=(i % 2 == 1))
    for x in (-11.5, -6.4, 3.2, 7.4):
        stall(x, -(RIVER_HALF + 1.4), -1, P, people)
    for x in (-9.0, -3.6, 5.6):
        stall(x, RIVER_HALF + 1.4, 1, P, people)
    for x in (-13.0, -8.2, -4.4, 2.6, 6.2, 9.4):
        willow(x, -(RIVER_HALF + 0.9), P)
    for x in (-11.0, -5.4, 1.8, 8.0):
        willow(x, RIVER_HALF + 0.9, P)
    boats = []
    for i, (x, y, ang, awn, mast) in enumerate((
            (-10.5, -1.1, 0.06, True, True), (-6.0, 1.3, -0.10, True, False),
            (-1.2, -0.6, 0.04, False, True), (2.8, 1.0, 0.12, True, False),
            (7.2, -1.3, -0.05, True, False))):
        boats.append(boat("Boat%d" % i, x, y, ang, P, people, awning=awn, mast=mast))
    for i in range(26):                     # 街上散客
        side = -1 if i % 2 else 1
        people.append((RNG.uniform(-14.5, 9.5),
                       side * (RIVER_HALF + RNG.uniform(0.9, 2.4)),
                       BANK_H + 0.05))
    crowd(P, people)
    log("people=%d boats=%d objects=%d" % (len(people), len(boats), len(bpy.data.objects)))
    return boats


def build_studio():
    sun = bpy.data.lights.new("Sun", type="SUN")
    sun.energy, sun.angle = 3.6, math.radians(3.0)
    sun.color = (1.0, 0.90, 0.76)
    obj = bpy.data.objects.new("Sun", sun)
    bpy.context.scene.collection.objects.link(obj)
    obj.rotation_euler = (math.radians(52), 0.0, math.radians(-38))

    world = bpy.data.worlds[0] if bpy.data.worlds else bpy.data.worlds.new("W")
    bpy.context.scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    if bg:
        bg.inputs[0].default_value = (0.58, 0.72, 0.88, 1.0)
        bg.inputs[1].default_value = 0.55

    cam_data = bpy.data.cameras.new("Cam")
    cam_data.lens = 45.0
    cam_data.sensor_fit = "HORIZONTAL"
    cam = bpy.data.objects.new("Cam", cam_data)
    bpy.context.scene.collection.objects.link(cam)
    bpy.context.scene.camera = cam
    cam.location = (SCROLL_FROM, -22.0, 13.5)
    look = Vector((3.0, 22.5, -13.0)).normalized()     # 固定朝向, 纯横移=展卷
    cam.rotation_euler = look.to_track_quat("-Z", "Y").to_euler()
    return cam


def animate(cam, boats, frames):
    scn = bpy.context.scene
    scn.frame_start, scn.frame_end = 1, frames
    # 匀速平移: 直接让新插的关键帧默认线性 (5.x 的 Action 已没有 fcurves 属性可后处理)
    try:
        bpy.context.preferences.edit.keyframe_new_interpolation_type = "LINEAR"
    except (AttributeError, TypeError):
        pass
    for frame, x in ((1, SCROLL_FROM), (frames, SCROLL_TO)):
        cam.location.x = x
        cam.keyframe_insert("location", frame=frame)
    drift = -1.6 * SECONDS / 3.0
    for parts in boats:
        for obj in parts:
            x0 = obj.location.x
            obj.keyframe_insert("location", frame=1)
            obj.location.x = x0 + drift
            obj.keyframe_insert("location", frame=frames)
            obj.location.x = x0


def setup_render(res_y):
    scn = bpy.context.scene
    scn.render.fps = FPS
    if ENGINE.startswith("cyc"):
        scn.render.engine = "CYCLES"
        scn.cycles.samples = SAMPLES
        scn.cycles.use_denoising = True
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
    for tr in ("AgX", "Filmic", "Standard"):
        try:
            scn.view_settings.view_transform = tr
            break
        except TypeError:
            continue
    scn.view_settings.exposure = 0.1
    log("engine=%s samples=%d res=%dx%d fps=%d" % (scn.render.engine, SAMPLES,
                                                   RES_X, res_y, FPS))


def main():
    parse_args()
    clean_scene()
    P = palette()
    boats = build_town(P)
    cam = build_studio()
    frames = max(2, int(round(SECONDS * FPS)))
    animate(cam, boats, frames)
    res_y = int(RES_X * 9 / 16)
    setup_render(res_y)
    os.makedirs(OUT_DIR, exist_ok=True)
    scn = bpy.context.scene

    poster = os.path.join(OUT_DIR, "qingming_poster.png")
    img = scn.render.image_settings
    if hasattr(img, "media_type"):          # 5.x: 图片/视频输出改由 media_type 区分
        img.media_type = "IMAGE"
    img.file_format = "PNG"
    scn.frame_set(frames // 2)
    scn.render.filepath = poster
    log("rendering poster -> %s" % poster)
    bpy.ops.render.render(write_still=True)
    log("poster ok=%s size=%d" % (os.path.exists(poster),
                                 os.path.getsize(poster) if os.path.exists(poster) else 0))

    video = os.path.join(OUT_DIR, "qingming_scroll_%ds.mp4" % int(round(SECONDS)))
    if not STILL_ONLY:
        if hasattr(img, "media_type"):
            img.media_type = "VIDEO"
        img.file_format = "FFMPEG"
        scn.render.ffmpeg.format = "MPEG4"
        scn.render.ffmpeg.codec = "H264"
        scn.render.ffmpeg.constant_rate_factor = "HIGH"
        scn.render.ffmpeg.ffmpeg_preset = "GOOD"
        scn.render.use_file_extension = False
        scn.render.filepath = video
        log("rendering %d frames -> %s" % (frames, video))
        bpy.ops.render.render(animation=True)
        ok = os.path.exists(video)
        log("VIDEO ok=%s size=%d %s" % (ok, os.path.getsize(video) if ok else 0, video))

    blend = os.path.join(os.path.dirname(OUT_DIR), "qingming_scroll.blend")
    bpy.ops.wm.save_as_mainfile(filepath=blend)
    log("saved scene -> %s" % blend)


main()

