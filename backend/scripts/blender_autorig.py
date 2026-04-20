"""
RigFlow Blender headless auto-rig script.

Pipeline:
1) Import model (FBX / GLB / OBJ)
2) Normalize mesh into consistent world space (Z-up, centered, feet on floor, fixed height)
3) Create Rigify metarig and fit it to mesh bounds (or landmarks if provided)
4) Generate full rig
5) Parent mesh to rig with automatic weights (ARMATURE_AUTO)
6) Export GLB + write Mixamo->Rigify bone map JSON
"""

import argparse
import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector

TARGET_HEIGHT = 1.75
THREE_TARGET_HEIGHT = 2.0


# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------

def enable_rigify():
    print("[RigFlow] Enabling Rigify...")
    try:
        bpy.ops.preferences.addon_enable(module="rigify")
    except Exception:
        import addon_utils
        addon_utils.enable("rigify", default_set=True, persistent=True)
    print("[RigFlow] Rigify enabled")


def parse_args():
    argv = sys.argv
    argv = argv[argv.index("--") + 1:] if "--" in argv else []

    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--bones", required=True)
    parser.add_argument("--format", default="fbx")
    parser.add_argument("--landmarks", default=None)
    return parser.parse_args(argv)


# ---------------------------------------------------------------------------
# Scene / IO
# ---------------------------------------------------------------------------

def clear_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    if bpy.context.active_object and bpy.context.active_object.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=True)
    enable_rigify()


def import_model(filepath, fmt):
    fmt = fmt.lower()
    print(f"[RigFlow] Importing {fmt}: {filepath}")
    if fmt == "fbx":
        bpy.ops.import_scene.fbx(filepath=filepath)
    elif fmt in ("glb", "gltf"):
        bpy.ops.import_scene.gltf(filepath=filepath)
    elif fmt == "obj":
        bpy.ops.wm.obj_import(filepath=filepath)
    else:
        raise ValueError(f"Unsupported format: {fmt}")


def get_meshes():
    return [o for o in bpy.data.objects if o.type == "MESH" and not o.name.startswith("WGT-")]


def select_meshes(meshes):
    bpy.ops.object.select_all(action="DESELECT")
    for m in meshes:
        m.select_set(True)
    bpy.context.view_layer.objects.active = meshes[0]


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------

def all_world_verts(meshes):
    verts = []
    for obj in meshes:
        for v in obj.data.vertices:
            verts.append(obj.matrix_world @ v.co)
    if not verts:
        raise RuntimeError("No vertices found in imported mesh")
    return verts


def bbox_from_verts(verts):
    xs = [v.x for v in verts]
    ys = [v.y for v in verts]
    zs = [v.z for v in verts]
    return {
        "min_x": min(xs), "max_x": max(xs),
        "min_y": min(ys), "max_y": max(ys),
        "min_z": min(zs), "max_z": max(zs),
        "size_x": max(xs) - min(xs),
        "size_y": max(ys) - min(ys),
        "size_z": max(zs) - min(zs),
    }


def apply_mesh_transforms(meshes, location=False, rotation=False, scale=False):
    select_meshes(meshes)
    bpy.ops.object.transform_apply(location=location, rotation=rotation, scale=scale)


def rotate_meshes(meshes, axis, degrees):
    select_meshes(meshes)
    bpy.ops.transform.rotate(value=math.radians(degrees), orient_axis=axis, orient_type="GLOBAL")
    apply_mesh_transforms(meshes, rotation=True)


def scale_meshes(meshes, factor):
    select_meshes(meshes)
    bpy.ops.transform.resize(value=(factor, factor, factor))
    apply_mesh_transforms(meshes, scale=True)


def center_and_floor(meshes):
    b = bbox_from_verts(all_world_verts(meshes))
    cx = (b["min_x"] + b["max_x"]) / 2.0
    cy = (b["min_y"] + b["max_y"]) / 2.0
    floor = b["min_z"]
    for m in meshes:
        m.location.x -= cx
        m.location.y -= cy
        m.location.z -= floor
    apply_mesh_transforms(meshes, location=True)


def armature_height_world(armature_obj, prefer_deform=False, preferred_names=None):
    bones = list(armature_obj.data.bones)

    if preferred_names:
        named = [b for b in bones if b.name in preferred_names]
        if named:
            bones = named
    elif prefer_deform:
        deform = [b for b in bones if b.name.startswith("DEF-")]
        if deform:
            bones = deform

    points = []
    for bone in bones:
        points.append(armature_obj.matrix_world @ bone.head_local)
        points.append(armature_obj.matrix_world @ bone.tail_local)

    if not points:
        return 0.0

    min_z = min(p.z for p in points)
    max_z = max(p.z for p in points)
    return max_z - min_z


# ---------------------------------------------------------------------------
# Normalization
# ---------------------------------------------------------------------------

def normalize_mesh(meshes):
    print("[RigFlow] Normalizing mesh...")
    apply_mesh_transforms(meshes, location=True, rotation=True, scale=True)

    b = bbox_from_verts(all_world_verts(meshes))
    sx, sy, sz = b["size_x"], b["size_y"], b["size_z"]
    print(f"[RigFlow] Raw dims X:{sx:.3f} Y:{sy:.3f} Z:{sz:.3f}")

    # 1) Make model upright (Z tallest)
    if sz < max(sx, sy):
        if sx >= sy and sx >= sz:
            rotate_meshes(meshes, "Y", 90)
            print("[RigFlow] Rotated X->Z")
        elif sy >= sx and sy >= sz:
            rotate_meshes(meshes, "X", -90)
            print("[RigFlow] Rotated Y->Z")

    # 2) Prefer T-pose width along X instead of Y (front/back on Y)
    b = bbox_from_verts(all_world_verts(meshes))
    if b["size_y"] > b["size_x"] * 1.15:
        rotate_meshes(meshes, "Z", -90)
        print("[RigFlow] Rotated around Z for forward alignment")

    # 3) Center on ground + scale to target height
    center_and_floor(meshes)
    b = bbox_from_verts(all_world_verts(meshes))
    h = b["size_z"]
    if h > 1e-6 and abs(h - TARGET_HEIGHT) > 0.01:
        factor = TARGET_HEIGHT / h
        scale_meshes(meshes, factor)
        center_and_floor(meshes)
        print(f"[RigFlow] Height normalized x{factor:.4f} ({h:.3f}->{TARGET_HEIGHT:.3f})")

    b = bbox_from_verts(all_world_verts(meshes))
    print(f"[RigFlow] Normalized dims X:{b['size_x']:.3f} Y:{b['size_y']:.3f} Z:{b['size_z']:.3f}")

    return {
        "height": b["size_z"],
        "width": b["size_x"],
        "depth": b["size_y"],
        "min_x": b["min_x"], "max_x": b["max_x"],
        "min_y": b["min_y"], "max_y": b["max_y"],
        "min_z": b["min_z"], "max_z": b["max_z"],
        "cx": (b["min_x"] + b["max_x"]) / 2.0,
        "cy": (b["min_y"] + b["max_y"]) / 2.0,
    }


# ---------------------------------------------------------------------------
# Landmarks
# ---------------------------------------------------------------------------

def threejs_to_blender(pt):
    scale = TARGET_HEIGHT / THREE_TARGET_HEIGHT
    x, y, z = pt
    return Vector((x * scale, -z * scale, y * scale))


# ---------------------------------------------------------------------------
# Rigify
# ---------------------------------------------------------------------------

def create_metarig():
    for op in (
        lambda: bpy.ops.object.armature_human_metarig_add(),
        lambda: bpy.ops.armature.metarig_sample_add(metarig_type="human"),
    ):
        try:
            op()
            break
        except Exception:
            pass
    metarig = bpy.context.active_object
    if not metarig or metarig.type != "ARMATURE":
        raise RuntimeError("Failed to create Rigify metarig")
    return metarig


def remove_face_rig(metarig):
    bpy.context.view_layer.objects.active = metarig
    bpy.ops.object.mode_set(mode="EDIT")

    def remove_recursive(b):
        for c in list(b.children):
            remove_recursive(c)
        metarig.data.edit_bones.remove(b)

    for name in ["face", "teeth.T", "teeth.B", "tongue"]:
        bone = metarig.data.edit_bones.get(name)
        if bone:
            remove_recursive(bone)

    bpy.ops.object.mode_set(mode="OBJECT")


def fit_metarig_to_mesh(metarig, props):
    bpy.context.view_layer.objects.active = metarig
    h = armature_height_world(
        metarig,
        preferred_names={
            "spine", "spine.001", "spine.002", "spine.003", "spine.004", "spine.005",
            "thigh.L", "thigh.R", "shin.L", "shin.R", "foot.L", "foot.R", "toe.L", "toe.R"
        },
    )
    if h <= 1e-6:
        raise RuntimeError("Metarig height invalid")

    scale = props["height"] / h
    metarig.scale = tuple(v * scale for v in metarig.scale)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)

    metarig.location = (0, 0, 0)
    bpy.ops.object.transform_apply(location=True, rotation=False, scale=False)
    print(f"[RigFlow] Metarig fit scale x{scale:.4f}")\


def place_from_landmarks(metarig, landmarks):
    bpy.context.view_layer.objects.active = metarig
    bpy.ops.object.mode_set(mode="EDIT")
    eb = metarig.data.edit_bones

    chin = landmarks["chin"]
    groin = landmarks["groin"]
    lw = landmarks["left_wrist"]
    rw = landmarks["right_wrist"]
    la = landmarks["left_ankle"]
    ra = landmarks["right_ankle"]

    body_h = max(0.2, chin.z - groin.z)

    spine = ["spine", "spine.001", "spine.002", "spine.003", "spine.004", "spine.005"]
    ratios = [0.0, 0.18, 0.38, 0.58, 0.78, 0.92]
    for i, name in enumerate(spine):
        b = eb.get(name)
        if not b:
            continue
        r0 = ratios[i]
        r1 = ratios[i + 1] if i + 1 < len(ratios) else 1.0
        b.head = groin + (chin - groin) * r0
        b.tail = groin + (chin - groin) * r1

    for side, wrist in [("L", lw), ("R", rw)]:
        shoulder_z = groin.z + body_h * 0.82
        shoulder = Vector((wrist.x, wrist.y, shoulder_z))
        elbow = shoulder + (wrist - shoulder) * 0.55 + Vector((0, 0.05, -0.02))
        hand_end = wrist + (wrist - elbow).normalized() * 0.07

        for name, h, t in [
            (f"upper_arm.{side}", shoulder, elbow),
            (f"forearm.{side}", elbow, wrist),
            (f"hand.{side}", wrist, hand_end),
        ]:
            b = eb.get(name)
            if b:
                b.head, b.tail = h, t

    for side, ankle in [("L", la), ("R", ra)]:
        hip = Vector((ankle.x, ankle.y, groin.z))
        knee = Vector((ankle.x * 0.97, ankle.y - 0.04, (groin.z + ankle.z) / 2 + 0.02))
        toe = ankle + Vector((0, -0.09, 0))

        for name, h, t in [
            (f"thigh.{side}", hip, knee),
            (f"shin.{side}", knee, ankle),
            (f"foot.{side}", ankle, toe),
            (f"toe.{side}", toe, toe + Vector((0, -0.04, 0))),
        ]:
            b = eb.get(name)
            if b:
                b.head, b.tail = h, t

    bpy.ops.object.mode_set(mode="OBJECT")


def generate_rig(metarig):
    bpy.context.view_layer.objects.active = metarig
    bpy.ops.object.mode_set(mode="POSE")
    bpy.ops.pose.rigify_generate()
    bpy.ops.object.mode_set(mode="OBJECT")
    rig = bpy.context.active_object
    if not rig or rig.type != "ARMATURE":
        raise RuntimeError("Rigify generation failed")
    print(f"[RigFlow] Generated rig: {rig.name}")
    return rig


def ensure_rig_matches_mesh_height(meshes, rig):
    mh = bbox_from_verts(all_world_verts(meshes))["size_z"]
    rh = armature_height_world(
        rig,
        preferred_names={
            "DEF-spine", "DEF-spine.001", "DEF-spine.002", "DEF-spine.003", "DEF-spine.004", "DEF-spine.005",
            "DEF-thigh.L", "DEF-thigh.R", "DEF-shin.L", "DEF-shin.R", "DEF-foot.L", "DEF-foot.R", "DEF-toe.L", "DEF-toe.R"
        },
    )
    if mh <= 1e-6 or rh <= 1e-6:
        return

    factor = mh / rh
    factor = max(0.2, min(5.0, factor))
    if abs(factor - 1.0) < 1e-3:
        return

    rig.scale = tuple(v * factor for v in rig.scale)
    bpy.context.view_layer.objects.active = rig
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    print(f"[RigFlow] Corrected rig height x{factor:.4f}")


# ---------------------------------------------------------------------------
# Bind / Export
# ---------------------------------------------------------------------------

def bind_auto(meshes, rig):
    bpy.ops.object.select_all(action="DESELECT")
    for m in meshes:
        m.select_set(True)
    rig.select_set(True)
    bpy.context.view_layer.objects.active = rig
    bpy.ops.object.parent_set(type="ARMATURE_AUTO")
    print(f"[RigFlow] Bound {len(meshes)} mesh(es) with ARMATURE_AUTO")


def clean_widgets_and_controls(rig):
    widgets = [o for o in bpy.data.objects if o.name.startswith("WGT-")]
    for obj in widgets:
        for col in list(obj.users_collection):
            col.objects.unlink(obj)
        data = obj.data
        bpy.data.objects.remove(obj, do_unlink=True)
        if data and data.users == 0:
            bpy.data.meshes.remove(data)
    for col in list(bpy.data.collections):
        if col.name.startswith("WGTS"):
            bpy.data.collections.remove(col)

    bpy.context.view_layer.objects.active = rig
    bpy.ops.object.mode_set(mode="EDIT")
    for b in [x for x in rig.data.edit_bones if not x.name.startswith("DEF-")]:
        rig.data.edit_bones.remove(b)
    bpy.ops.object.mode_set(mode="OBJECT")


def export_glb(meshes, rig, output_path):
    bpy.ops.object.select_all(action="DESELECT")
    rig.select_set(True)
    for m in meshes:
        m.select_set(True)
    bpy.context.view_layer.objects.active = rig

    bpy.ops.export_scene.gltf(
        filepath=output_path,
        export_format="GLB",
        export_animations=False,
        export_skins=True,
        use_selection=True,
        export_apply=True,
    )
    print(f"[RigFlow] Exported: {output_path}")


RIGIFY_TO_MIXAMO = {
    "DEF-spine": "Hips",
    "DEF-spine.001": "Spine",
    "DEF-spine.002": "Spine1",
    "DEF-spine.003": "Spine2",
    "DEF-spine.004": "Neck",
    "DEF-spine.005": "Head",
    "DEF-thigh.L": "LeftUpLeg",
    "DEF-shin.L": "LeftLeg",
    "DEF-foot.L": "LeftFoot",
    "DEF-toe.L": "LeftToeBase",
    "DEF-thigh.R": "RightUpLeg",
    "DEF-shin.R": "RightLeg",
    "DEF-foot.R": "RightFoot",
    "DEF-toe.R": "RightToeBase",
    "DEF-shoulder.L": "LeftShoulder",
    "DEF-upper_arm.L": "LeftArm",
    "DEF-forearm.L": "LeftForeArm",
    "DEF-hand.L": "LeftHand",
    "DEF-shoulder.R": "RightShoulder",
    "DEF-upper_arm.R": "RightArm",
    "DEF-forearm.R": "RightForeArm",
    "DEF-hand.R": "RightHand",
}


def build_bone_map(rig):
    mapping = {}
    for b in rig.data.bones:
        m = RIGIFY_TO_MIXAMO.get(b.name)
        if m:
            mapping[m] = b.name
    print(f"[RigFlow] Bone map entries: {len(mapping)}")
    return mapping


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    enable_rigify()
    args = parse_args()

    print("=" * 60)
    print(f"[RigFlow] Input:  {args.input}")
    print(f"[RigFlow] Output: {args.output}")
    print(f"[RigFlow] Mode:   {'LANDMARK' if args.landmarks else 'AUTO'}")
    print("=" * 60)

    raw_landmarks = json.loads(args.landmarks) if args.landmarks else None

    clear_scene()
    import_model(args.input, args.format)

    meshes = get_meshes()
    if not meshes:
        raise RuntimeError("No mesh objects found after import")
    print(f"[RigFlow] Mesh count: {len(meshes)}")

    props = normalize_mesh(meshes)

    metarig = create_metarig()
    remove_face_rig(metarig)
    fit_metarig_to_mesh(metarig, props)

    if raw_landmarks:
        lmk = {k: threejs_to_blender(v) for k, v in raw_landmarks.items()}
        place_from_landmarks(metarig, lmk)

    rig = generate_rig(metarig)
    ensure_rig_matches_mesh_height(meshes, rig)

    bind_auto(meshes, rig)
    clean_widgets_and_controls(rig)
    export_glb(meshes, rig, args.output)

    bone_map = build_bone_map(rig)
    Path(args.bones).write_text(json.dumps(bone_map, indent=2))

    print("=" * 60)
    print(f"[RigFlow] SUCCESS — {len(bone_map)} bones mapped")
    print("=" * 60)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n[RigFlow] FATAL ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)