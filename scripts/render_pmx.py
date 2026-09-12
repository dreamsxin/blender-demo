"""Import an MMD .pmx model and render three stills with Blender 5.2 + mmd_tools.

    blender -b --factory-startup --python scripts/render_pmx.py -- --model <pmx> [--out <dir>] [--name <prefix>]

渲完顺手把场景存成 <模型目录>/<name>_render.blend (--blend 改路径, --no-blend 关掉,
--no-render 只搭场景不渲图)。不给 --model 时用 demos/character/claret。
"""
import math
import os
import sys

import addon_utils
import bpy
from mathutils import Vector


def repo_root():
    """Repo root = parent of scripts/, so the defaults survive moving the repo."""
    here = globals().get("__file__")
    if here:
        return os.path.dirname(os.path.dirname(os.path.abspath(here)))
    return r"D:\work\blender"


MODEL = os.path.join(repo_root(), "demos", "character", "claret", "克拉蕾.pmx")
OUTDIR = ""
NAME = ""
BLEND = ""
DO_RENDER = True
SCALE = 0.08
RES = (1080, 1440)
SAMPLES = 64
# (name, azimuth deg from -Y front, elevation deg)
VIEWS = [("front", 0, 8), ("three_quarter", 35, 10), ("side", 85, 8)]


def parse_args():
    global MODEL, OUTDIR, NAME, SCALE, BLEND, DO_RENDER
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    for flag in ("--model", "--out", "--name", "--scale", "--blend"):
        if flag not in argv:
            continue
        value = argv[argv.index(flag) + 1]
        if flag == "--model":
            MODEL = value
        elif flag == "--out":
            OUTDIR = value
        elif flag == "--name":
            NAME = value
        elif flag == "--blend":
            BLEND = value
        else:
            SCALE = float(value)
    if "--no-render" in argv:
        DO_RENDER = False
    if not OUTDIR:
        OUTDIR = os.path.join(os.path.dirname(MODEL), "render")
    if not NAME:
        NAME = os.path.splitext(os.path.basename(MODEL))[0]
    if not BLEND and "--no-blend" not in argv:
        BLEND = os.path.join(os.path.dirname(MODEL), NAME + "_render.blend")


def log(msg):
    print("[render]", msg, flush=True)


def clean_scene():
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)


def import_model():
    addon_utils.enable("bl_ext.user_default.mmd_tools", default_set=False)
    bpy.ops.mmd_tools.import_model(
        filepath=MODEL, scale=SCALE, types={"MESH", "ARMATURE", "MORPHS"},
        clean_model=True, log_level="ERROR",
    )
    meshes = [o for o in bpy.data.objects if o.type == "MESH"]
    if not meshes:
        raise RuntimeError("no mesh imported")
    log(f"imported {len(meshes)} mesh object(s), {sum(len(m.data.vertices) for m in meshes)} verts")
    return meshes


def bounds(objs):
    lo = Vector((1e9, 1e9, 1e9))
    hi = Vector((-1e9, -1e9, -1e9))
    for o in objs:
        for c in o.bound_box:
            w = o.matrix_world @ Vector(c)
            for i in range(3):
                lo[i] = min(lo[i], w[i])
                hi[i] = max(hi[i], w[i])
    return lo, hi


def setup_lights(center, size):
    def area(name, loc, energy, sz):
        light = bpy.data.lights.new(name, type="AREA")
        light.energy = energy
        light.size = sz
        light.color = (1.0, 1.0, 1.0)
        obj = bpy.data.objects.new(name, light)
        bpy.context.scene.collection.objects.link(obj)
        obj.location = loc
        d = (center - Vector(loc)).normalized()
        obj.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
        return obj

    r = size * 1.6
    area("key", (center.x - r * 0.7, center.y - r * 0.8, center.z + r * 0.6), 120, size * 1.2)
    area("fill", (center.x + r * 0.9, center.y - r * 0.5, center.z + r * 0.2), 45, size * 1.5)
    area("rim", (center.x + r * 0.2, center.y + r * 1.0, center.z + r * 0.9), 90, size)

    world = bpy.data.worlds[0] if bpy.data.worlds else bpy.data.worlds.new("W")
    bpy.context.scene.world = world
    if not world.node_tree:
        world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    if bg:
        bg.inputs[0].default_value = (0.62, 0.66, 0.72, 1.0)
        bg.inputs[1].default_value = 0.22


def setup_camera(center, size):
    cam_data = bpy.data.cameras.new("Cam")
    cam_data.lens = 85.0
    cam = bpy.data.objects.new("Cam", cam_data)
    bpy.context.scene.collection.objects.link(cam)
    bpy.context.scene.camera = cam
    # distance so the model height fits the vertical sensor with margin
    sensor_v = cam_data.sensor_width * RES[1] / RES[0]
    dist = size * cam_data.lens / sensor_v * 1.25
    return cam, dist


def place_camera(cam, target, dist, azimuth, elevation):
    az, el = math.radians(azimuth), math.radians(elevation)
    d = Vector((math.sin(az) * math.cos(el), -math.cos(az) * math.cos(el), math.sin(el)))
    cam.location = target + d * dist
    cam.rotation_euler = (-d).to_track_quat("-Z", "Y").to_euler()


def setup_render():
    scn = bpy.context.scene
    for engine in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE"):
        try:
            scn.render.engine = engine
            break
        except TypeError:
            continue
    log(f"engine: {scn.render.engine}")
    ee = getattr(scn, "eevee", None)
    if ee is not None:
        for attr, val in (("taa_render_samples", SAMPLES), ("use_gtao", True),
                          ("use_raytracing", True), ("use_shadows", True)):
            if hasattr(ee, attr):
                setattr(ee, attr, val)
    scn.render.resolution_x, scn.render.resolution_y = RES
    scn.render.resolution_percentage = 100
    scn.render.film_transparent = False
    scn.render.image_settings.file_format = "PNG"
    scn.render.image_settings.color_mode = "RGBA"
    # MMD toon textures are authored for a straight sRGB look
    vs = scn.view_settings
    try:
        vs.view_transform = "Standard"
    except TypeError:
        pass
    vs.look = "None"


def calibrate_exposure(cam, target, dist, tmpdir, aim=0.46):
    """Low-res probe render, then shift exposure so the subject averages `aim` luminance."""
    scn = bpy.context.scene
    scn.view_settings.exposure = 0.0
    place_camera(cam, target, dist, VIEWS[0][1], VIEWS[0][2])
    prev_pct, prev_transparent = scn.render.resolution_percentage, scn.render.film_transparent
    prev_samples = getattr(scn.eevee, "taa_render_samples", None)
    scn.render.resolution_percentage = 25
    scn.render.film_transparent = True
    if prev_samples is not None:
        scn.eevee.taa_render_samples = 16
    probe = os.path.join(tmpdir, "probe.png")
    scn.render.filepath = probe
    bpy.ops.render.render(write_still=True)

    img = bpy.data.images.load(probe)
    px = list(img.pixels)
    total = n = 0.0
    for i in range(0, len(px), 4):
        if px[i + 3] > 0.5:
            total += 0.2126 * px[i] + 0.7152 * px[i + 1] + 0.0722 * px[i + 2]
            n += 1
    bpy.data.images.remove(img)
    if os.path.exists(probe):
        os.remove(probe)                     # calibration scratch file, not a deliverable
    scn.render.resolution_percentage = prev_pct
    scn.render.film_transparent = prev_transparent
    if prev_samples is not None:
        scn.eevee.taa_render_samples = prev_samples

    if n == 0:
        log("calibration: no subject pixels found, keeping exposure 0")
        return
    mean = total / n
    ev = max(-4.0, min(2.0, math.log2(aim / max(mean, 1e-4))))
    scn.view_settings.exposure = ev
    log(f"calibration: subject mean luma={mean:.3f} over {int(n)} px -> exposure {ev:+.2f} EV")


def main():
    parse_args()
    log(f"model: {MODEL}")
    os.makedirs(OUTDIR, exist_ok=True)
    clean_scene()
    meshes = import_model()
    lo, hi = bounds(meshes)
    center = (lo + hi) / 2
    size = max((hi - lo).z, (hi - lo).x, 0.1)
    log(f"bounds {tuple(round(v, 3) for v in lo)} -> {tuple(round(v, 3) for v in hi)} size={size:.3f}")

    setup_render()
    setup_lights(center, size)
    cam, dist = setup_camera(center, size)
    # aim slightly above mid-height: reads better for a character
    target = Vector((center.x, center.y, lo.z + (hi.z - lo.z) * 0.56))

    calibrate_exposure(cam, target, dist, OUTDIR)

    written = []
    if DO_RENDER:
        for name, az, el in VIEWS:
            place_camera(cam, target, dist, az, el)
            path = os.path.join(OUTDIR, f"{NAME}_{name}.png")
            bpy.context.scene.render.filepath = path
            log(f"rendering {name} -> {path}")
            bpy.ops.render.render(write_still=True)
            ok = os.path.exists(path)
            written.append((path, ok, os.path.getsize(path) if ok else 0))
    else:
        place_camera(cam, target, dist, *VIEWS[1][1:])

    if BLEND:
        os.makedirs(os.path.dirname(BLEND), exist_ok=True)
        bpy.ops.wm.save_as_mainfile(filepath=BLEND)
        log(f"saved scene -> {BLEND} ({os.path.getsize(BLEND)} bytes)")

    for path, ok, sz in written:
        log(f"RESULT ok={ok} size={sz} {path}")
    if written and not all(ok for _, ok, _ in written):
        sys.exit(3)


main()
