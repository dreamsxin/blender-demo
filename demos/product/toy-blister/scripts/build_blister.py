"""Ya Ya 90 年代动作人物泡罩包装 (blister pack) 程序化建模 + 渲染。

    blender -b --factory-startup --python demos/product/toy-blister/scripts/build_blister.py -- \
        [--out <png>] [--engine cycles|eevee] [--samples 96] [--res 1080]

左侧泡罩里是 Q 版 3D 打印风人物, 右侧 6 个小泡罩装配件, 卡纸底板印卡通篮球场,
大标题 "Ya Ya", 右上角小字 "Designed by yaya"。
"""
import math
import os
import sys

import bmesh
import bpy
import numpy as np
from mathutils import Vector

# --- 画面 / 版式参数 (Blender 单位, 卡片立在 XZ 平面, 泡罩朝 -Y 即镜头方向) ---
CARD_W, CARD_H = 2.30, 3.20
CARD_T = 0.035                      # 卡纸厚度
TEX_PX = 1400                       # 底板印刷贴图分辨率
HANG_Z = CARD_H - 0.17              # 挂孔中心高度
LOGO_Z = CARD_H - 0.40              # "Ya Ya" 标题
CREDIT_Z = CARD_H - 0.18            # 右上角小字
FIG_BUBBLE = (0.92, 0.80, 1.96)     # 人物泡罩 (宽, 深, 高)
FIG_CENTER = (-0.60, 1.26)          # 人物泡罩中心 (x, z)
FIG_HEIGHT = 1.80                   # 人物总高, 头身比 1:2.5
ACC_COLS = (0.32, 0.86)             # 配件泡罩两列 x
ACC_ROWS = (0.52, 1.28, 2.04)       # 配件泡罩三行 z
ACC_BUBBLE = (0.44, 0.32, 0.60)

OUT = ""
ENGINE = "cycles"
SAMPLES = 96
RES_X = 1080


def log(msg):
    print("[blister]", msg, flush=True)


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
        OUT = os.path.join(os.path.dirname(here), "render", "yaya_blister.png")


def clean_scene():
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    for coll in (bpy.data.meshes, bpy.data.materials, bpy.data.images, bpy.data.curves):
        for item in list(coll):
            if item.users == 0:
                coll.remove(item)


def set_in(node, name, value):
    sock = node.inputs.get(name)
    if sock is not None:
        sock.default_value = value


def mat(name, color, roughness=0.45, metallic=0.0, transmission=0.0, ior=1.5,
        sheen=0.0, coat=0.0, layer_lines=0.0):
    """Principled material; layer_lines>0 fakes 3D-print layering with a wave bump."""
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    set_in(bsdf, "Base Color", (*color, 1.0))
    set_in(bsdf, "Roughness", roughness)
    set_in(bsdf, "Metallic", metallic)
    set_in(bsdf, "IOR", ior)
    set_in(bsdf, "Transmission Weight", transmission)
    set_in(bsdf, "Sheen Weight", sheen)
    set_in(bsdf, "Coat Weight", coat)
    if layer_lines:
        wave = nt.nodes.new("ShaderNodeTexWave")
        wave.wave_type = "BANDS"
        wave.bands_direction = "Z"
        wave.inputs["Scale"].default_value = 220.0
        wave.inputs["Distortion"].default_value = 0.0
        bump = nt.nodes.new("ShaderNodeBump")
        bump.inputs["Strength"].default_value = layer_lines
        bump.inputs["Distance"].default_value = 0.004
        nt.links.new(wave.outputs["Fac"], bump.inputs["Height"])
        nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    if transmission:
        m.use_backface_culling = False
        m.blend_method = "BLEND" if hasattr(m, "blend_method") else m.blend_method
    return m


def plaid_mat(name, base, stripe, cross):
    """Green plaid: two checkers layered, for the dress."""
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    set_in(bsdf, "Roughness", 0.55)
    c1 = nt.nodes.new("ShaderNodeTexChecker")
    c1.inputs["Color1"].default_value = (*base, 1.0)
    c1.inputs["Color2"].default_value = (*stripe, 1.0)
    c1.inputs["Scale"].default_value = 15.0
    c2 = nt.nodes.new("ShaderNodeTexChecker")
    c2.inputs["Color1"].default_value = (1, 1, 1, 1)
    c2.inputs["Color2"].default_value = (*cross, 1.0)
    c2.inputs["Scale"].default_value = 9.0
    mix = nt.nodes.new("ShaderNodeMixRGB")
    mix.blend_type = "MULTIPLY"
    mix.inputs["Fac"].default_value = 0.55
    nt.links.new(c1.outputs["Color"], mix.inputs["Color1"])
    nt.links.new(c2.outputs["Color"], mix.inputs["Color2"])
    nt.links.new(mix.outputs["Color"], bsdf.inputs["Base Color"])
    return m


def new_obj(name, mesh_data, material=None, location=(0, 0, 0)):
    obj = bpy.data.objects.new(name, mesh_data)
    bpy.context.scene.collection.objects.link(obj)
    obj.location = location
    if material:
        obj.data.materials.append(material)
    return obj


def rounded_box(name, size, radius=0.04, segments=6, material=None, location=(0, 0, 0),
                open_back=False, thickness=0.0, smooth=True):
    """Bevelled box. open_back removes the +Y faces, thickness solidifies the shell."""
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    for v in bm.verts:
        v.co.x *= size[0]
        v.co.y *= size[1]
        v.co.z *= size[2]
    geom = list(bm.verts) + list(bm.edges) + list(bm.faces)
    r = min(radius, min(size) * 0.49)
    bmesh.ops.bevel(bm, geom=geom, offset=r, segments=segments, affect="EDGES",
                    profile=0.5, clamp_overlap=True)
    if open_back:
        back = [f for f in bm.faces if f.normal.y > 0.85]
        bmesh.ops.delete(bm, geom=back, context="FACES")
    if thickness:
        bmesh.ops.solidify(bm, geom=list(bm.faces), thickness=thickness)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    if smooth:
        # flat panels stay flat, bevel fillets get smooth shading -> crisp plastic edges
        for p in me.polygons:
            n = p.normal
            p.use_smooth = max(abs(n.x), abs(n.y), abs(n.z)) < 0.999
    return new_obj(name, me, material, location)


def ball(name, radius, material=None, location=(0, 0, 0), scale=(1, 1, 1), segments=48):
    bpy.ops.mesh.primitive_uv_sphere_add(radius=radius, segments=segments,
                                         ring_count=segments // 2, location=location)
    obj = bpy.context.object
    obj.name = name
    obj.scale = scale
    for p in obj.data.polygons:
        p.use_smooth = True
    if material:
        obj.data.materials.append(material)
    return obj


def tube(name, r1, r2, depth, material=None, location=(0, 0, 0), rotation=(0, 0, 0)):
    bpy.ops.mesh.primitive_cone_add(radius1=r1, radius2=r2, depth=depth, vertices=48,
                                    location=location, rotation=rotation)
    obj = bpy.context.object
    obj.name = name
    for p in obj.data.polygons:
        p.use_smooth = True
    if material:
        obj.data.materials.append(material)
    return obj


def ring(name, major, minor, material=None, location=(0, 0, 0), rotation=(0, 0, 0)):
    bpy.ops.mesh.primitive_torus_add(major_radius=major, minor_radius=minor,
                                     major_segments=48, minor_segments=16,
                                     location=location, rotation=rotation)
    obj = bpy.context.object
    obj.name = name
    if material:
        obj.data.materials.append(material)
    return obj


def text_obj(name, body, size, location, material, align="CENTER", extrude=0.006, bold=True):
    cu = bpy.data.curves.new(name, type="FONT")
    cu.body = body
    cu.size = size
    cu.align_x = align
    cu.align_y = "CENTER"
    cu.extrude = extrude
    cu.space_character = 1.05
    if bold:
        cu.offset = 0.012            # fake bold: widen the outline
    obj = bpy.data.objects.new(name, cu)
    bpy.context.scene.collection.objects.link(obj)
    obj.location = location
    obj.rotation_euler = (math.pi / 2, 0, 0)
    obj.data.materials.append(material)
    return obj


def card_texture():
    """Paint the backer card artwork: retro colour bands + cartoon basketball court."""
    h = int(TEX_PX * CARD_H / CARD_W)
    w = TEX_PX
    u = np.linspace(0.0, 1.0, w)[None, :].repeat(h, 0)          # 0..1 left→right
    v = np.linspace(1.0, 0.0, h)[:, None].repeat(w, 1)          # 1..0 top→bottom
    img = np.empty((h, w, 3), dtype=np.float32)
    img[:] = np.array([0.94, 0.90, 0.80], np.float32)           # cream card stock

    def band(v0, v1, rgb):
        m = (v >= v0) & (v < v1)
        img[m] = np.array(rgb, np.float32)

    band(0.845, 1.0, (0.93, 0.24, 0.20))                        # red header
    band(0.822, 0.845, (0.99, 0.79, 0.16))                      # yellow pin stripe
    band(0.0, 0.045, (0.13, 0.34, 0.60))                        # blue footer

    # --- court plate ---
    cv0, cv1 = 0.075, 0.805
    court = (v >= cv0) & (v < cv1)
    img[court] = np.array([0.91, 0.68, 0.40], np.float32)        # wood floor
    cu = (u - 0.5) / 0.5                                        # -1..1 across card
    cvv = (v - (cv0 + cv1) / 2) / ((cv1 - cv0) / 2)             # -1..1 across court
    ar = (cv1 - cv0) * CARD_H / CARD_W                          # court aspect for circles

    def paint(mask, rgb):
        m = court & mask
        img[m] = np.array(rgb, np.float32)

    lw = 0.030
    # 木地板拼缝
    plank = (np.abs(((u * 26.0) % 1.0) - 0.5) > 0.47)
    img[court & plank] *= 0.93
    paint((np.abs(np.abs(cu) - 0.92) < lw) | (np.abs(np.abs(cvv) - 0.94) < lw),
          (1.0, 1.0, 0.98))                                     # boundary
    paint(np.abs(cvv) < lw, (1.0, 1.0, 0.98))                   # centre line
    rr = np.sqrt(cu ** 2 + (cvv * ar) ** 2)
    paint(np.abs(rr - 0.30) < lw * 0.9, (1.0, 1.0, 0.98))       # centre circle
    paint(rr < 0.10, (0.99, 0.76, 0.14))                        # tip-off dot
    for side in (-1.0, 1.0):
        keyz = np.abs(cvv - side * 0.66)
        inkey = (np.abs(cu) < 0.34) & (keyz < 0.28)
        img[court & inkey] = np.array([0.16, 0.52, 0.50], np.float32)   # painted key
        paint(inkey & ((np.abs(np.abs(cu) - 0.34) < lw) | (keyz > 0.28 - lw)),
              (1.0, 1.0, 0.98))
        arc = np.sqrt(cu ** 2 + ((cvv - side * 0.94) * ar) ** 2)
        paint((np.abs(arc - 0.62) < lw * 0.9) & (side * cvv < 0.55), (1.0, 1.0, 0.98))
        hoop = np.sqrt((cu * 1.0) ** 2 + ((cvv - side * 0.86) * ar) ** 2)
        paint(np.abs(hoop - 0.075) < lw * 1.4, (0.94, 0.30, 0.10))      # hoop
        paint((np.abs(cu) < 0.16) & (np.abs(cvv - side * 0.925) < lw * 1.6),
              (0.20, 0.20, 0.22))                                       # backboard
    # retro halftone + paper grain
    dots = 0.018 * (np.sin(u * w * 0.55) * np.sin(v * h * 0.55))
    grain = np.random.default_rng(7).normal(0.0, 0.008, (h, w)).astype(np.float32)
    img *= (1.0 + dots + grain)[:, :, None]
    np.clip(img, 0.0, 1.0, out=img)

    # punched hang hole (painted: reads correctly on a straight-on product shot)
    hu = (u - 0.5) * CARD_W
    hv = (v * CARD_H) - HANG_Z
    hole = np.sqrt(hu ** 2 + hv ** 2)
    img[hole < 0.075] = np.array([0.07, 0.06, 0.06], np.float32)
    m = (hole >= 0.075) & (hole < 0.095)
    img[m] *= 0.55

    px = np.ones((h, w, 4), dtype=np.float32)
    px[:, :, :3] = img[::-1]                                    # blender images are bottom-up
    image = bpy.data.images.new("YaYaCardArt", w, h)
    image.pixels.foreach_set(px.ravel())
    image.pack()
    return image


def build_card():
    art = card_texture()
    m = bpy.data.materials.new("CardPrint")
    m.use_nodes = True
    nt = m.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    set_in(bsdf, "Roughness", 0.72)
    set_in(bsdf, "Sheen Weight", 0.15)
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = art
    nt.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.12
    nt.links.new(tex.outputs["Color"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])

    bpy.ops.mesh.primitive_plane_add(size=2.0)
    front = bpy.context.object
    front.name = "CardFront"
    front.scale = (CARD_W / 2, CARD_H / 2, 1.0)
    front.rotation_euler = (math.pi / 2, 0, 0)
    front.location = (0.0, -0.002, CARD_H / 2)
    front.data.materials.append(m)

    body = rounded_box("CardBody", (CARD_W, CARD_T, CARD_H), radius=0.03, segments=3,
                       material=mat("Cardboard", (0.80, 0.72, 0.58), roughness=0.85),
                       location=(0.0, CARD_T / 2, CARD_H / 2), smooth=False)
    ink = mat("Ink", (0.99, 0.97, 0.90), roughness=0.35, sheen=0.3)
    text_obj("LogoYaYa", "Ya Ya", 0.34, (0.0, -0.008, LOGO_Z), ink)
    text_obj("Credit", "Designed by yaya", 0.072,
             (CARD_W / 2 - 0.14, -0.008, CREDIT_Z), ink, align="RIGHT", bold=False)
    return front, body


def build_bubbles():
    """Clear vacuum-formed blisters: one tall bubble on the left, six pockets on the right."""
    plastic = mat("Blister", (0.96, 0.99, 1.0), roughness=0.03, transmission=1.0,
                  ior=1.50)
    fw, fd, fh = FIG_BUBBLE
    fx, fz = FIG_CENTER
    rounded_box("BubbleFigure", (fw, fd * 2, fh), radius=0.14, segments=8,
                material=plastic, location=(fx, 0.0, fz), open_back=True, thickness=0.004)
    rounded_box("FlangeFigure", (fw + 0.10, 0.005, fh + 0.10), radius=0.045, segments=4,
                material=plastic, location=(fx, -0.0025, fz))
    aw, ad, ah = ACC_BUBBLE
    for col, x in enumerate(ACC_COLS):
        for row, z in enumerate(ACC_ROWS):
            rounded_box("BubbleAcc%d%d" % (col, row), (aw, ad * 2, ah), radius=0.09,
                        segments=7, material=plastic, location=(x, 0.0, z),
                        open_back=True, thickness=0.004)
            rounded_box("FlangeAcc%d%d" % (col, row), (aw + 0.05, 0.005, ah + 0.05),
                        radius=0.035, segments=3, material=plastic,
                        location=(x, -0.0025, z))


def build_figure():
    """Q 版人物: 头身比 1:2.5, 造型取两张参考照的元素 —— 高马尾 + 粉色短袖 + 格子裙 + 小手镯。"""
    fx = FIG_CENTER[0]
    fy = -FIG_BUBBLE[1] * 0.52          # 站在泡罩中间偏前
    base = 0.30

    def P(x, y, z):
        return (fx + x, fy + y, z)

    skin = mat("Skin", (0.99, 0.80, 0.68), roughness=0.42, layer_lines=0.20)
    hair_m = mat("Hair", (0.11, 0.09, 0.10), roughness=0.34, layer_lines=0.15)
    tee = mat("Tee", (0.97, 0.66, 0.73), roughness=0.52, layer_lines=0.18)
    print_m = mat("TeePrint", (0.55, 0.74, 0.93), roughness=0.45)
    dress = plaid_mat("SkirtPlaid", (0.97, 0.95, 0.96), (0.98, 0.78, 0.85),
                      (0.58, 0.76, 0.94))
    shoe = mat("Shoe", (0.97, 0.96, 0.94), roughness=0.40, layer_lines=0.2)
    shoe_sole = mat("ShoeSole", (0.97, 0.70, 0.76), roughness=0.45)
    white = mat("Collar", (0.99, 0.98, 0.96), roughness=0.40, layer_lines=0.15)
    silver = mat("Bangle", (0.86, 0.87, 0.90), roughness=0.18, metallic=0.9)
    eye_m = mat("Eye", (0.09, 0.07, 0.09), roughness=0.05, coat=1.0)
    glint = mat("Glint", (1.0, 1.0, 1.0), roughness=0.03, coat=1.0)
    mouth_m = mat("Mouth", (0.66, 0.22, 0.26), roughness=0.30)
    blush = mat("Blush", (0.98, 0.60, 0.58), roughness=0.55)
    clip_m = mat("Clip", (0.99, 0.72, 0.20), roughness=0.25, coat=0.6)

    head_r = FIG_HEIGHT / 2.5 / 2.0                     # 0.36
    head_z = base + FIG_HEIGHT - head_r                 # 1.74

    # 鞋 + 腿 (光腿, 夏天造型)
    for s in (-1, 1):
        rounded_box("Shoe%d" % s, (0.15, 0.24, 0.10), radius=0.045, segments=6,
                    material=shoe, location=P(0.115 * s, -0.02, base + 0.06))
        rounded_box("Sole%d" % s, (0.16, 0.25, 0.032), radius=0.015, segments=4,
                    material=shoe_sole, location=P(0.115 * s, -0.02, base + 0.015))
        tube("Leg%d" % s, 0.058, 0.052, 0.30, skin, P(0.108 * s, 0.0, base + 0.24))
    # 裙 (锥台) + 短袖上衣 + 领口
    tube("Skirt", 0.30, 0.165, 0.62, dress, P(0, 0, base + 0.62))
    tube("Tee", 0.175, 0.20, 0.32, tee, P(0, 0, base + 1.01))
    ball("TeePrint", 0.075, print_m, P(0.02, -0.185, base + 1.02),
         scale=(0.55, 0.18, 1.25))
    ring("Collar", 0.15, 0.035, white, P(0, -0.01, base + 1.14), rotation=(0, 0, 0))
    # 手臂: 短袖 + 光手臂 + 一只手镯
    for s in (-1, 1):
        tube("Sleeve%d" % s, 0.068, 0.058, 0.16, tee,
             P(0.235 * s, 0.0, base + 1.05), rotation=(0, s * 0.20, 0))
        tube("Arm%d" % s, 0.050, 0.044, 0.34, skin,
             P(0.262 * s, 0.0, base + 0.82), rotation=(0, s * 0.20, 0))
        ball("Hand%d" % s, 0.060, skin, P(0.292 * s, 0.0, base + 0.645))
    ring("Bangle", 0.055, 0.010, silver, P(-0.285, 0.0, base + 0.70),
         rotation=(0, -0.20, 0))
    # 头 + 脖子
    tube("Neck", 0.075, 0.075, 0.10, skin, P(0, 0, base + 1.15))
    ball("Head", head_r, skin, P(0, 0, head_z), scale=(1.0, 0.94, 0.98))
    build_face(P, head_r, head_z, eye_m, glint, mouth_m, blush)
    build_hair(P, head_r, head_z, hair_m, clip_m)


def build_face(P, head_r, head_z, eye_m, glint, mouth_m, blush):
    for s in (-1, 1):
        eye = ball("Eye%d" % s, 0.078, eye_m, P(0.135 * s, -0.295, head_z + 0.025),
                   scale=(0.95, 0.8, 1.15))
        ball("Glint%d" % s, 0.026, glint,
             (eye.location.x + 0.022 * s, eye.location.y - 0.048, eye.location.z + 0.03))
        ball("Blush%d" % s, 0.062, blush, P(0.215 * s, -0.262, head_z - 0.09),
             scale=(1.15, 0.28, 0.62))
    ball("Mouth", 0.052, mouth_m, P(0, -0.315, head_z - 0.13), scale=(1.25, 0.5, 0.6))


def build_hair(P, head_r, head_z, hair_m, clip_m):
    ball("HairBack", head_r * 1.05, hair_m, P(0, 0.055, head_z + 0.015),
         scale=(1.0, 0.95, 1.0))
    ball("HairBangs", head_r * 1.04, hair_m, P(0, -0.02, head_z + 0.20),
         scale=(1.0, 0.98, 0.42))
    # 高马尾: 头顶偏后一个发团 + 一束搭在侧后方的发尾 + 发圈 (正面能看见)
    ball("HairBun", 0.155, hair_m, P(0.02, 0.14, head_z + 0.36), scale=(1.0, 1.0, 0.85))
    ring("HairTie", 0.085, 0.026, clip_m, P(0.05, 0.16, head_z + 0.25),
         rotation=(0.30, 0, -0.35))
    tube("Ponytail", 0.115, 0.050, 0.68, hair_m, P(0.40, 0.15, head_z - 0.24),
         rotation=(0.16, 0, -0.26))
    rounded_box("Clip", (0.075, 0.032, 0.036), radius=0.012, segments=4,
                material=clip_m, location=P(-0.25, -0.305, head_z + 0.14))


def build_accessories():
    """右侧 6 个配件: 篮球 / 球鞋 / 小书包 / 水壶 / 蝴蝶 / 捕虫网。"""
    orange = mat("BallOrange", (0.92, 0.44, 0.12), roughness=0.55, layer_lines=0.25)
    seam = mat("BallSeam", (0.10, 0.08, 0.08), roughness=0.5)
    shoe_w = mat("ShoeWhite", (0.95, 0.95, 0.92), roughness=0.45, layer_lines=0.2)
    shoe_c = mat("ShoePink", (0.96, 0.60, 0.70), roughness=0.45, layer_lines=0.2)
    bag_m = mat("Bag", (0.36, 0.55, 0.82), roughness=0.55, layer_lines=0.2)
    bag_d = mat("BagDetail", (0.99, 0.78, 0.24), roughness=0.45)
    bottle = mat("Bottle", (0.30, 0.72, 0.62), roughness=0.35, coat=0.5)
    cap_m = mat("Cap", (0.95, 0.35, 0.45), roughness=0.35)
    wing_m = mat("Wing", (0.24, 0.17, 0.14), roughness=0.42, layer_lines=0.25)
    spot_m = mat("WingSpot", (0.36, 0.86, 0.72), roughness=0.35)
    body_m = mat("BugBody", (0.13, 0.11, 0.10), roughness=0.4)
    net_y = mat("NetFrame", (0.99, 0.82, 0.20), roughness=0.35, coat=0.4)
    net_m = mat("NetMesh", (0.95, 0.96, 0.94), roughness=0.45, transmission=0.55)

    ax0, ax1 = ACC_COLS
    z0, z1, z2 = ACC_ROWS
    y = -ACC_BUBBLE[1] * 0.5

    # 篮球 (左上)
    ball("Basketball", 0.135, orange, (ax0, y, z2))
    for rot in ((0, 0, 0), (math.pi / 2, 0, 0), (0, math.pi / 2, 0)):
        ring("BallSeam", 0.136, 0.007, seam, (ax0, y, z2), rotation=rot)
    # 球鞋一对 (右上)
    for i, s in enumerate((-1, 1)):
        rounded_box("Sneaker%d" % i, (0.10, 0.22, 0.09), radius=0.035, segments=5,
                    material=shoe_c, location=(ax1 + 0.062 * s, y, z2 + 0.04))
        rounded_box("Sole%d" % i, (0.11, 0.23, 0.034), radius=0.016, segments=4,
                    material=shoe_w, location=(ax1 + 0.062 * s, y, z2 - 0.035))
    # 小书包 (左中)
    rounded_box("Backpack", (0.24, 0.13, 0.28), radius=0.055, segments=6, material=bag_m,
                location=(ax0, y, z1))
    rounded_box("BagFlap", (0.225, 0.05, 0.12), radius=0.035, segments=5, material=bag_d,
                location=(ax0, y - 0.062, z1 + 0.065))
    for s in (-1, 1):
        rounded_box("Strap%d" % s, (0.032, 0.055, 0.24), radius=0.014, segments=3,
                    material=bag_d, location=(ax0 + 0.075 * s, y + 0.08, z1))
    # 水壶 (右中)
    tube("Bottle", 0.072, 0.068, 0.26, bottle, (ax1, y, z1 - 0.02))
    tube("BottleCap", 0.042, 0.042, 0.07, cap_m, (ax1, y, z1 + 0.145))
    # 蝴蝶 (左下): 参考照片里停在手上的青凤蝶
    ball("BugBody", 0.026, body_m, (ax0, y, z0), scale=(1.0, 1.1, 3.6))
    for s in (-1, 1):
        ball("WingTop%d" % s, 0.098, wing_m, (ax0 + 0.098 * s, y - 0.006, z0 + 0.060),
             scale=(1.5, 0.10, 0.95))
        ball("WingBot%d" % s, 0.070, wing_m, (ax0 + 0.070 * s, y - 0.004, z0 - 0.085),
             scale=(1.25, 0.10, 1.5))
        ball("WingSpotA%d" % s, 0.042, spot_m, (ax0 + 0.100 * s, y - 0.014, z0 + 0.040),
             scale=(1.6, 0.09, 0.50))
        ball("WingSpotB%d" % s, 0.026, spot_m, (ax0 + 0.078 * s, y - 0.012, z0 - 0.085),
             scale=(1.3, 0.09, 1.10))
        tube("WingTail%d" % s, 0.016, 0.003, 0.11, wing_m,
             (ax0 + 0.088 * s, y - 0.004, z0 - 0.185), rotation=(0, s * 0.45, 0))
        tube("Antenna%d" % s, 0.004, 0.003, 0.09, body_m,
             (ax0 + 0.030 * s, y, z0 + 0.120), rotation=(0, s * 0.55, 0))
    # 捕虫网 (右下)
    ring("NetHoop", 0.105, 0.013, net_y, (ax1, y, z0 + 0.14), rotation=(math.pi / 2, 0, 0))
    tube("NetBag", 0.100, 0.012, 0.13, net_m, (ax1, y + 0.055, z0 + 0.14),
         rotation=(math.pi / 2, 0, 0))
    tube("NetHandle", 0.019, 0.017, 0.26, net_y, (ax1, y, z0 - 0.10))


def build_studio():
    """棚拍布光: 柔和主光 + 补光 + 顶部条形光, 背景一张浅灰卡纸。"""
    backdrop = mat("Backdrop", (0.62, 0.63, 0.66), roughness=0.9)
    bpy.ops.mesh.primitive_plane_add(size=14.0, location=(0, 1.2, 0))
    bp = bpy.context.object
    bp.name = "Backdrop"
    bp.rotation_euler = (math.pi / 2, 0, 0)
    bp.data.materials.append(backdrop)
    bpy.ops.mesh.primitive_plane_add(size=14.0, location=(0, -2.0, -0.02))
    floor = bpy.context.object
    floor.name = "Floor"
    floor.data.materials.append(backdrop)

    target = Vector((0.0, 0.0, CARD_H / 2))
    for name, loc, energy, size in (("Key", (-2.6, -3.0, 4.2), 420, 4.0),
                                    ("Fill", (3.0, -2.6, 1.6), 150, 3.5),
                                    ("Top", (0.0, -1.2, 5.2), 240, 3.0),
                                    ("Kick", (0.0, 2.4, 2.0), 110, 4.0)):
        light = bpy.data.lights.new(name, type="AREA")
        light.energy, light.size = energy, size
        obj = bpy.data.objects.new(name, light)
        bpy.context.scene.collection.objects.link(obj)
        obj.location = loc
        obj.visible_camera = False
        obj.rotation_euler = (target - Vector(loc)).normalized().to_track_quat("-Z", "Y").to_euler()

    world = bpy.data.worlds.new("Studio") if not bpy.data.worlds else bpy.data.worlds[0]
    bpy.context.scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    if bg:
        bg.inputs[0].default_value = (0.55, 0.57, 0.60, 1.0)
        bg.inputs[1].default_value = 0.35

    cam_data = bpy.data.cameras.new("Cam")
    cam_data.lens = 85.0
    cam_data.sensor_fit = "HORIZONTAL"
    cam = bpy.data.objects.new("Cam", cam_data)
    bpy.context.scene.collection.objects.link(cam)
    bpy.context.scene.camera = cam
    res_y = int(RES_X * 4 / 3)
    dist = (CARD_W + 0.35) * cam_data.lens / cam_data.sensor_width
    cam.location = (0.0, -dist, CARD_H / 2)
    cam.rotation_euler = (math.pi / 2, 0, 0)
    cam_data.dof.use_dof = True
    cam_data.dof.focus_distance = dist - 0.45
    cam_data.dof.aperture_fstop = 7.0
    log("camera dist=%.2f frame=%.2f x %.2f units" % (
        dist, dist * cam_data.sensor_width / cam_data.lens,
        dist * cam_data.sensor_width * res_y / RES_X / cam_data.lens))
    return res_y


def setup_render(res_y):
    scn = bpy.context.scene
    if ENGINE.startswith("cyc"):
        scn.render.engine = "CYCLES"
        scn.cycles.samples = SAMPLES
        scn.cycles.use_denoising = True
        scn.cycles.max_bounces = 12
        scn.cycles.transmission_bounces = 8
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
    for tr in ("Standard", "AgX", "Filmic"):
        try:
            scn.view_settings.view_transform = tr
            break
        except TypeError:
            continue
    scn.view_settings.look = "None"
    log("engine=%s samples=%d res=%dx%d" % (scn.render.engine, SAMPLES, RES_X, res_y))


def main():
    parse_args()
    clean_scene()
    build_card()
    build_figure()
    build_accessories()
    build_bubbles()
    res_y = build_studio()
    setup_render(res_y)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    bpy.context.scene.render.filepath = OUT
    log("rendering -> %s" % OUT)
    bpy.ops.render.render(write_still=True)
    ok = os.path.exists(OUT)
    log("RESULT ok=%s size=%d %s" % (ok, os.path.getsize(OUT) if ok else 0, OUT))
    blend = os.path.join(os.path.dirname(os.path.dirname(OUT)), "yaya_blister.blend")
    bpy.ops.wm.save_as_mainfile(filepath=blend)
    log("saved scene -> %s" % blend)
    if not ok:
        sys.exit(3)


main()

