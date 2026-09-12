"""MMD 角色 简易行走 / 跳跃控制脚本 (Blender 5.2 + mmd_tools)

GUI 用法:
    Scripting 工作区打开本文件 -> Run Script, 然后在 3D 视图按 N, 切到 "MMD 控制" 页签。
    场景里已有骨架就直接用, 没有才导入 MODEL 指向的 pmx。
      · 键盘控制: W/S 前进后退, A/D 转向, Shift 加速, 空格 跳跃, Esc 退出
      · 烘焙行走 / 烘焙跳跃: 生成关键帧动作 (MMD_Walk / MMD_Jump), 可播放或渲染
      · 复位: 清除全部姿势
无界面自检:
    blender -b --factory-startup --python scripts/mmd_control.py -- --selftest [--render] [--model <pmx>]

动作参数以身高 1.55 单位为基准, 换成别的模型时按实际身高自动缩放。
"""
import math
import os
import sys

import addon_utils
import bpy
from mathutils import Matrix, Vector


def repo_root():
    """Repo root = parent of scripts/, so the defaults survive moving the repo."""
    here = globals().get("__file__")
    if here:
        return os.path.dirname(os.path.dirname(os.path.abspath(here)))
    return r"D:\work\blender"


MODEL = os.path.join(repo_root(), "demos", "character", "claret", "克拉蕾.pmx")
IMPORT_SCALE = 0.08

# --- rig bone names (mmd_tools naming) ---
B_ROOT = "全ての親"
B_CENTER = "センター"
B_LOWER = "下半身"
B_UPPER = "上半身"
B_IK = {"L": "足ＩＫ.L", "R": "足ＩＫ.R"}
B_ARM = {"L": "腕.L", "R": "腕.R"}
B_ELBOW = {"L": "ひじ.L", "R": "ひじ.R"}
KEYED = [B_ROOT, B_CENTER, B_LOWER, B_UPPER] + list(B_IK.values()) \
    + list(B_ARM.values()) + list(B_ELBOW.values())

# --- motion tuning, blender units (model is ~1.55 tall, faces -Y) ---
STRIDE = 0.34          # foot travel during one stance = root advance per half cycle
FOOT_LIFT = 0.11
WALK_SPEED = 1.15      # units / second
RUN_MULT = 1.8
TURN_SPEED = math.radians(140)
BOB = 0.035
WALK_DIP = 0.047        # keep the body below rest height so the legs have IK slack
SWAY = 0.018
ARM_SWING = math.radians(26)
ARM_DOWN = math.radians(40)
ELBOW_BEND = math.radians(14)
HIP_YAW = math.radians(6)
GRAVITY = 9.8
JUMP_HEIGHT = 0.45
CROUCH_TIME = 0.12
CROUCH_DEPTH = 0.11
LAND_TIME = 0.18
REF_HEIGHT = 1.55       # tuning above is authored for this body height
_BASE_TUNING = None


def scale_tuning(height):
    """Rescale the length-based tuning to the actual model height."""
    global _BASE_TUNING, STRIDE, FOOT_LIFT, WALK_SPEED, BOB, WALK_DIP, SWAY
    global JUMP_HEIGHT, CROUCH_DEPTH
    if _BASE_TUNING is None:
        _BASE_TUNING = (STRIDE, FOOT_LIFT, WALK_SPEED, BOB, WALK_DIP, SWAY,
                        JUMP_HEIGHT, CROUCH_DEPTH)
    k = max(0.2, min(5.0, height / REF_HEIGHT))
    (STRIDE, FOOT_LIFT, WALK_SPEED, BOB, WALK_DIP, SWAY,
     JUMP_HEIGHT, CROUCH_DEPTH) = [v * k for v in _BASE_TUNING]
    return k


def model_height(arm):
    meshes = [o for o in bpy.data.objects
              if o.type == "MESH" and o.find_armature() is arm]
    if not meshes:
        meshes = [o for o in bpy.data.objects if o.type == "MESH"]
    if not meshes:
        return REF_HEIGHT
    return max((o.matrix_world @ Vector(c)).z for o in meshes for c in o.bound_box)


def find_armature(context=None):
    """Locate the character armature, importing MODEL once if the scene has none."""
    if context is not None:
        active = getattr(context, "object", None)
        if active is not None and active.type == "ARMATURE":
            return active
    arms = [o for o in bpy.data.objects if o.type == "ARMATURE"]
    if arms:
        return arms[0]
    if not os.path.exists(MODEL):
        return None
    addon_utils.enable("bl_ext.user_default.mmd_tools", default_set=False)
    bpy.ops.mmd_tools.import_model(
        filepath=MODEL, scale=IMPORT_SCALE, types={"MESH", "ARMATURE", "MORPHS"},
        clean_model=True, log_level="ERROR",
    )
    return next((o for o in bpy.data.objects if o.type == "ARMATURE"), None)


class Rig:
    """Turns character-space intent into pose-bone basis values.

    Locations/rotations are given in armature space; for bones parented under
    B_ROOT that means the character's own frame (forward = -Y at yaw 0).
    """

    def __init__(self, arm):
        self.arm = arm
        self.pb = arm.pose.bones
        self._basis = {}
        self.height = model_height(arm)
        self.k = scale_tuning(self.height)

    def _b(self, name):
        m = self._basis.get(name)
        if m is None:
            m = self.pb[name].bone.matrix_local.to_3x3()
            self._basis[name] = m
        return m

    def move(self, name, offset):
        pb = self.pb.get(name)
        if pb is not None:
            pb.location = self._b(name).inverted() @ Vector(offset)

    def rotate(self, name, mat):
        pb = self.pb.get(name)
        if pb is None:
            return
        M = self._b(name)
        pb.rotation_mode = "QUATERNION"
        pb.rotation_quaternion = (M.inverted() @ mat @ M).to_quaternion()

    def clear(self):
        for pb in self.pb:
            pb.location = (0.0, 0.0, 0.0)
            pb.rotation_quaternion = (1.0, 0.0, 0.0, 0.0)
            pb.rotation_euler = (0.0, 0.0, 0.0)
            pb.scale = (1.0, 1.0, 1.0)


class State:
    """Character state, integrated by step() and rendered by apply_pose()."""

    def __init__(self):
        self.pos = Vector((0.0, 0.0))   # ground position (x, y)
        self.z = 0.0                    # height above ground
        self.vz = 0.0
        self.yaw = 0.0
        self.phase = 0.0                # walk cycle 0..1, 0 = left foot forward
        self.speed = 0.0
        self.mode = "ground"            # ground | crouch | air | land
        self.timer = 0.0


def ease_out(u):
    return 1.0 - (1.0 - u) ** 2


def stride_for(speed):
    """Stride grows with speed so the feet never slide."""
    return STRIDE * max(0.55, min(1.6, (abs(speed) / WALK_SPEED) ** 0.6))


def foot_cycle(t, stride, lift):
    """t in [0,1): first half = planted stance sliding back, second half = swing."""
    if t < 0.5:
        return stride * (0.5 - 2.0 * t), 0.0
    u = (t - 0.5) * 2.0
    return stride * (u - 0.5), lift * math.sin(math.pi * u)


def step(st, dt, fwd=0.0, turn=0.0, run=False, jump=False):
    st.yaw += turn * TURN_SPEED * dt
    if st.mode in ("ground", "land"):
        target = WALK_SPEED * (RUN_MULT if run else 1.0) * max(-0.6, min(1.0, fwd))
        if st.mode == "land":
            target *= 0.35
    else:
        target = st.speed           # keep momentum while airborne
    st.speed += (target - st.speed) * min(1.0, dt * 9.0)
    if abs(st.speed) < 0.02:
        st.speed = 0.0
    heading = Vector((math.sin(st.yaw), -math.cos(st.yaw)))
    st.pos = st.pos + heading * (st.speed * dt)
    if st.mode == "ground" and st.speed:
        st.phase = (st.phase + dt * abs(st.speed) / (2.0 * stride_for(st.speed))) % 1.0

    if jump and st.mode == "ground":
        st.mode, st.timer = "crouch", 0.0
    if st.mode == "crouch":
        st.timer += dt
        if st.timer >= CROUCH_TIME:
            st.mode, st.vz, st.timer = "air", math.sqrt(2.0 * GRAVITY * JUMP_HEIGHT), 0.0
    elif st.mode == "air":
        st.vz -= GRAVITY * dt
        st.z += st.vz * dt
        if st.z <= 0.0 and st.vz < 0.0:
            st.z, st.vz, st.mode, st.timer = 0.0, 0.0, "land", 0.0
    elif st.mode == "land":
        st.timer += dt
        if st.timer >= LAND_TIME:
            st.mode, st.timer = "ground", 0.0
    return st


def apply_pose(rig, st):
    """Write the whole pose for one instant of state. Legs run through the mmd foot IK."""
    rig.clear()
    rig.move(B_ROOT, (st.pos.x, st.pos.y, st.z))
    rig.rotate(B_ROOT, Matrix.Rotation(st.yaw, 3, "Z"))

    feet = {"L": (0.0, 0.0), "R": (0.0, 0.0)}   # (forward, lift) in character space
    body_z = body_x = hip = lean = 0.0
    swing = {"L": 0.0, "R": 0.0}                # + = hand forward
    down = ARM_DOWN

    if st.mode == "ground" and st.speed:
        stride = stride_for(st.speed)
        d = math.copysign(1.0, st.speed)
        for side, off in (("L", 0.0), ("R", 0.5)):
            f, lift = foot_cycle((st.phase + off) % 1.0, stride, FOOT_LIFT)
            feet[side] = (f * d, lift)
        w = 2.0 * math.pi * st.phase
        body_z = -WALK_DIP - BOB * math.cos(2.0 * w)
        body_x = SWAY * math.sin(w)
        hip = -HIP_YAW * math.cos(w) * d
        lean = math.radians(4.0) * min(1.0, abs(st.speed) / WALK_SPEED)
        swing["L"] = -ARM_SWING * math.cos(w) * d
        swing["R"] = ARM_SWING * math.cos(w) * d
    elif st.mode == "crouch":
        u = min(1.0, st.timer / CROUCH_TIME)
        body_z = -CROUCH_DEPTH * ease_out(u)
        lean = math.radians(10.0) * u
        swing["L"] = swing["R"] = -ARM_SWING * 1.2 * u
    elif st.mode == "air":
        rising = st.vz > 0.0
        tuck = 1.0 if rising else 0.55
        feet["L"] = (0.10 * tuck, 0.17 * tuck)
        feet["R"] = (-0.04 * tuck, 0.11 * tuck)
        body_z = 0.02
        lean = math.radians(6.0 if rising else -3.0)
        swing["L"] = swing["R"] = ARM_SWING * (1.4 if rising else 0.5)
        down = ARM_DOWN - math.radians(22.0 if rising else 8.0)
    elif st.mode == "land":
        u = min(1.0, st.timer / LAND_TIME)
        body_z = -CROUCH_DEPTH * 0.9 * (1.0 - ease_out(u))
        lean = math.radians(8.0) * (1.0 - u)
        swing["L"] = swing["R"] = -ARM_SWING * 0.8 * (1.0 - u)

    rig.move(B_CENTER, (body_x, 0.0, body_z))
    rig.rotate(B_LOWER, Matrix.Rotation(hip, 3, "Z"))
    rig.rotate(B_UPPER, Matrix.Rotation(lean, 3, "X") @ Matrix.Rotation(-hip * 0.8, 3, "Z"))
    for side, sgn in (("L", 1.0), ("R", -1.0)):
        f, lift = feet[side]
        rig.move(B_IK[side], (0.0, -f, lift))
        tilt = math.radians(-12.0) * min(1.0, lift / FOOT_LIFT)
        rig.rotate(B_IK[side], Matrix.Rotation(tilt, 3, "X"))
        rig.rotate(B_ARM[side], Matrix.Rotation(-swing[side], 3, "X")
                   @ Matrix.Rotation(sgn * down, 3, "Y"))
        rig.rotate(B_ELBOW[side], Matrix.Rotation(-ELBOW_BEND, 3, "X"))


def start_action(arm, name):
    """Drop any previous take; the first keyframe_insert creates a fresh action."""
    ad = arm.animation_data or arm.animation_data_create()
    ad.action = None
    old = bpy.data.actions.get(name)
    if old is not None:
        bpy.data.actions.remove(old)


def finish_action(arm, name, scene, last_frame, linear_root=False):
    act = arm.animation_data.action
    act.name = name
    act.use_fake_user = True
    if linear_root:
        for fc in act.fcurves:
            if B_ROOT in fc.data_path and "location" in fc.data_path:
                for kp in fc.keyframe_points:
                    kp.interpolation = "LINEAR"
    scene.frame_start, scene.frame_end = 1, last_frame
    scene.frame_set(1)
    return act


def key_pose(rig, frame):
    for name in KEYED:
        pb = rig.pb.get(name)
        if pb is None:
            continue
        pb.keyframe_insert("location", frame=frame, group=name)
        pb.keyframe_insert("rotation_quaternion", frame=frame, group=name)


def bake_walk(rig, scene, cycles=2, run=False):
    """Loopable walk: whole number of frames per cycle keeps the feet planted."""
    fps = scene.render.fps
    speed = WALK_SPEED * (RUN_MULT if run else 1.0)
    stride = stride_for(speed)
    per_cycle = max(4, int(round(2.0 * stride / speed * fps)))
    speed = 2.0 * stride * fps / per_cycle       # snap speed to the frame grid
    st = State()
    st.speed = speed
    total = per_cycle * cycles
    start_action(rig.arm, "MMD_Walk")
    for i in range(total + 1):
        st.phase = (i / per_cycle) % 1.0
        st.pos = Vector((0.0, -speed * i / fps))
        apply_pose(rig, st)
        key_pose(rig, 1 + i)
    finish_action(rig.arm, "MMD_Walk", scene, 1 + total, linear_root=True)
    return per_cycle, speed


def bake_jump(rig, scene, fwd=0.0):
    fps = scene.render.fps
    dt = 1.0 / fps
    st = State()
    st.speed = WALK_SPEED * fwd
    trigger = max(1, int(0.2 * fps))
    start_action(rig.arm, "MMD_Jump")
    launched, tail, i = False, 0.0, 0
    while True:
        step(st, dt, fwd=fwd, jump=(i == trigger))
        launched = launched or st.mode in ("crouch", "air")
        apply_pose(rig, st)
        key_pose(rig, 1 + i)
        i += 1
        if launched and st.mode == "ground":
            tail += dt
        if tail > 0.35 or i > fps * 6:
            break
    finish_action(rig.arm, "MMD_Jump", scene, i)
    return i


class CLARET_OT_control(bpy.types.Operator):
    """W/S 前后 · A/D 转向 · Shift 加速 · 空格 跳跃 · Esc 退出"""
    bl_idname = "claret.control"
    bl_label = "键盘控制"

    KEYS = {"W", "S", "A", "D", "LEFT_SHIFT", "RIGHT_SHIFT", "SPACE"}

    def invoke(self, context, event):
        arm = find_armature(context)
        if arm is None:
            self.report({"ERROR"}, "找不到骨架, 也找不到 %s" % MODEL)
            return {"CANCELLED"}
        if arm.animation_data:
            arm.animation_data.action = None     # live control beats baked keys
        self.rig = Rig(arm)
        self.st = State()
        self.keys = set()
        self.jump = False
        wm = context.window_manager
        self._timer = wm.event_timer_add(1.0 / 60.0, window=context.window)
        wm.modal_handler_add(self)
        context.workspace.status_text_set(
            "MMD: W/S 前后 · A/D 转向 · Shift 加速 · 空格 跳跃 · Esc 退出")
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        if event.type == "ESC" and event.value == "PRESS":
            return self.finish(context)
        if event.type in self.KEYS:
            if event.value == "PRESS":
                self.keys.add(event.type)
                if event.type == "SPACE":
                    self.jump = True
            elif event.value == "RELEASE":
                self.keys.discard(event.type)
            return {"RUNNING_MODAL"}
        if event.type == "TIMER":
            k = self.keys
            fwd = (1.0 if "W" in k else 0.0) - (1.0 if "S" in k else 0.0)
            turn = (1.0 if "A" in k else 0.0) - (1.0 if "D" in k else 0.0)
            run = bool(k & {"LEFT_SHIFT", "RIGHT_SHIFT"})
            step(self.st, 1.0 / 60.0, fwd, turn, run, self.jump)
            self.jump = False
            apply_pose(self.rig, self.st)
            context.view_layer.update()
            for area in context.screen.areas:
                if area.type == "VIEW_3D":
                    area.tag_redraw()
            return {"RUNNING_MODAL"}
        return {"PASS_THROUGH"}

    def finish(self, context):
        context.window_manager.event_timer_remove(self._timer)
        context.workspace.status_text_set(None)
        return {"FINISHED"}


class CLARET_OT_bake(bpy.types.Operator):
    """把行走 / 跳跃写成关键帧动作"""
    bl_idname = "claret.bake"
    bl_label = "烘焙动作"
    bl_options = {"REGISTER", "UNDO"}

    kind: bpy.props.EnumProperty(
        name="动作",
        items=[("WALK", "行走", "循环行走"), ("RUN", "跑步", "循环跑步"),
               ("JUMP", "跳跃", "原地起跳"), ("JUMP_FWD", "前跳", "边走边跳")],
        default="WALK",
    )

    def execute(self, context):
        arm = find_armature(context)
        if arm is None:
            self.report({"ERROR"}, "找不到骨架, 也找不到 %s" % MODEL)
            return {"CANCELLED"}
        rig = Rig(arm)
        scene = context.scene
        if self.kind in ("WALK", "RUN"):
            per_cycle, speed = bake_walk(rig, scene, cycles=2, run=self.kind == "RUN")
            self.report({"INFO"}, "MMD_Walk: %d 帧/步循环, 速度 %.2f" % (per_cycle, speed))
        else:
            n = bake_jump(rig, scene, fwd=1.0 if self.kind == "JUMP_FWD" else 0.0)
            self.report({"INFO"}, "MMD_Jump: %d 帧" % n)
        return {"FINISHED"}


class CLARET_OT_reset(bpy.types.Operator):
    """清除动作与姿势, 回到 T/A-pose"""
    bl_idname = "claret.reset"
    bl_label = "复位"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        arm = find_armature(context)
        if arm is None:
            return {"CANCELLED"}
        if arm.animation_data:
            arm.animation_data.action = None
        Rig(arm).clear()
        context.view_layer.update()
        return {"FINISHED"}


class CLARET_PT_panel(bpy.types.Panel):
    bl_label = "MMD 角色控制"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "MMD 控制"

    def draw(self, context):
        col = self.layout.column(align=True)
        col.operator("claret.control", icon="PLAY")
        col.separator()
        col.label(text="烘焙动作")
        row = col.row(align=True)
        row.operator("claret.bake", text="行走").kind = "WALK"
        row.operator("claret.bake", text="跑步").kind = "RUN"
        row = col.row(align=True)
        row.operator("claret.bake", text="跳跃").kind = "JUMP"
        row.operator("claret.bake", text="前跳").kind = "JUMP_FWD"
        col.separator()
        col.operator("claret.reset", icon="LOOP_BACK")


CLASSES = (CLARET_OT_control, CLARET_OT_bake, CLARET_OT_reset, CLARET_PT_panel)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(CLASSES):
        try:
            bpy.utils.unregister_class(cls)
        except RuntimeError:
            pass


# --- headless self test -------------------------------------------------------

def _preview_render(scene, arm, frames, outdir, prefix="walk"):
    """Minimal camera + 3-point light rig, then render a few frames."""
    from mathutils import Vector as V
    if bpy.data.objects.get("Cam") is not None:      # rig already built by a previous pass
        return _render_frames(scene, frames, outdir, prefix)
    for name in ("Cube", "Camera", "Light"):         # factory startup leftovers
        obj = bpy.data.objects.get(name)
        if obj is not None:
            bpy.data.objects.remove(obj, do_unlink=True)
    mesh = [o for o in bpy.data.objects if o.type == "MESH"]
    top = max((arm.matrix_world @ V(c)).z for o in mesh for c in o.bound_box) if mesh else 1.5
    target = V((0.0, 0.0, top * 0.55))
    for name, loc, energy in (("key", (-1.6, -2.0, 2.2), 220), ("fill", (2.0, -1.6, 1.2), 90),
                              ("rim", (0.6, 2.2, 2.4), 160)):
        light = bpy.data.lights.new(name, type="AREA")
        light.energy, light.size = energy, 2.0
        obj = bpy.data.objects.new(name, light)
        scene.collection.objects.link(obj)
        obj.location = loc
        obj.visible_camera = False          # keep the light planes out of the shot
        obj.rotation_euler = (target - V(loc)).normalized().to_track_quat("-Z", "Y").to_euler()
    cam_data = bpy.data.cameras.new("Cam")
    cam_data.lens = 50.0
    cam = bpy.data.objects.new("Cam", cam_data)
    scene.collection.objects.link(cam)
    scene.camera = cam
    d = V((0.55, -1.0, 0.12)).normalized()
    cam.location = target + d * (top * 1.8 * cam_data.lens / (cam_data.sensor_width * 720 / 540))
    cam.rotation_euler = (-d).to_track_quat("-Z", "Y").to_euler()
    for engine in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE"):
        try:
            scene.render.engine = engine
            break
        except TypeError:
            continue
    scene.render.resolution_x, scene.render.resolution_y = 540, 720
    scene.render.image_settings.file_format = "PNG"
    scene.eevee.taa_render_samples = 16
    scene.view_settings.view_transform = "Standard"
    scene.view_settings.exposure = -0.7
    _render_frames(scene, frames, outdir, prefix)


def _render_frames(scene, frames, outdir, prefix):
    os.makedirs(outdir, exist_ok=True)
    for f in frames:
        scene.frame_set(f)
        scene.render.filepath = os.path.join(outdir, "%s_%02d.png" % (prefix, f))
        bpy.ops.render.render(write_still=True)
        print("[selftest] rendered", scene.render.filepath, flush=True)


def selftest(do_render=False):
    scene = bpy.context.scene
    arm = find_armature()
    assert arm is not None, "no armature"
    rig = Rig(arm)
    print("[selftest] armature:", arm.name)
    print("[selftest] height=%.3f tuning scale=%.3f (stride=%.3f jump=%.3f)"
          % (rig.height, rig.k, STRIDE, JUMP_HEIGHT))
    missing = [n for n in KEYED if n not in rig.pb]
    assert not missing, "missing bones: %s" % missing

    per_cycle, speed = bake_walk(rig, scene, cycles=2)
    act = arm.animation_data.action
    print("[selftest] walk action=%s fcurves=%d frames=%d..%d cycle=%d speed=%.3f"
          % (act.name, len(act.fcurves), scene.frame_start, scene.frame_end, per_cycle, speed))
    assert len(act.fcurves) >= len(KEYED), "too few fcurves"

    def sample(frame, bone):
        scene.frame_set(frame)
        bpy.context.view_layer.update()
        return arm.matrix_world @ rig.pb[bone].head

    # the body must travel forward (-Y) and the stance foot must stay planted
    y0 = sample(1, B_CENTER).y
    y1 = sample(1 + per_cycle, B_CENTER).y
    print("[selftest] center y: %.3f -> %.3f (per cycle)" % (y0, y1))
    assert y1 < y0 - 0.3 * rig.k, "body did not move forward"
    stance = [sample(1 + int(per_cycle * f), "足首.L") for f in (0.06, 0.18, 0.30, 0.42)]
    slide = max(p.y for p in stance) - min(p.y for p in stance)
    lift = max(abs(p.z - stance[0].z) for p in stance)
    print("[selftest] planted foot slide=%.4f lift=%.4f (world)" % (slide, lift))
    assert slide < 0.03 * rig.k and lift < 0.02 * rig.k, "stance foot slides"
    swing = [sample(1 + int(per_cycle * f), "足首.L").z for f in (0.55, 0.75, 0.95)]
    print("[selftest] swing foot z:", [round(v, 4) for v in swing])
    assert max(swing) > stance[0].z + 0.05 * rig.k, "foot never lifts"

    n = bake_jump(rig, scene)
    zs = []
    for f in range(1, n + 1):
        scene.frame_set(f)
        bpy.context.view_layer.update()
        zs.append((arm.matrix_world @ rig.pb[B_CENTER].head).z)
    base = zs[0]
    print("[selftest] jump action frames=%d peak=+%.3f dip=%.3f"
          % (n, max(zs) - base, min(zs) - base))
    assert max(zs) - base > 0.3 * rig.k, "no jump height"
    assert min(zs) - base < -0.05 * rig.k, "no crouch"
    assert abs(zs[-1] - base) < 0.02 * rig.k, "did not settle back"

    outdir = os.path.join(os.path.dirname(MODEL), "render", "control")
    if do_render:
        peak = 1 + zs.index(max(zs))
        _preview_render(scene, arm, [1, peak, n], outdir, prefix="jump")
    per_cycle, _ = bake_walk(rig, scene, cycles=2)
    if do_render:
        _preview_render(scene, arm, [1, 1 + per_cycle // 4, 1 + per_cycle // 2,
                                     1 + 3 * per_cycle // 4], outdir, prefix="walk")
    blend = os.path.join(os.path.dirname(MODEL),
                         os.path.splitext(os.path.basename(MODEL))[0] + "_control.blend")
    bpy.ops.wm.save_as_mainfile(filepath=blend)
    print("[selftest] saved scene -> %s (%d bytes)" % (blend, os.path.getsize(blend)))
    print("[selftest] ALL OK")


if __name__ == "__main__":
    unregister()
    register()
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    if "--model" in argv:
        MODEL = argv[argv.index("--model") + 1]
    if "--selftest" in argv:
        selftest(do_render="--render" in argv)

