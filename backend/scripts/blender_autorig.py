"""
Blender headless auto-rig script.

Strategy:
  1. Import mesh exactly as-is
  2. normalize_mesh() → scale + rotate mesh into standard Blender humanoid space:
       Z = up, character faces -Y, height = 1.75 m, feet at Z=0, centred on XZ
  3. Create Rigify metarig and scale it to match the normalised mesh
  4. Generate full rig
  5. Bind using ARMATURE_AUTO (heat-diffusion weight painting) — works for any mesh count
  6. Export as GLB

The same normalize_mesh() is called for all three modes:
  - Auto-rig
  - Re-rig
  - Landmark-guided re-rig

Run:
  blender --background --python blender_autorig.py -- \
      --input mesh.fbx --output rigged.glb --bones bones.json --format fbx \
      [--landmarks '{"chin":[x,y,z],...}']
"""

import bpy
import sys
import json
import argparse
import math
from pathlib import Path
from mathutils import Vector, Matrix

# ── Enable Rigify ─────────────────────────────────────────────────────────────
print("[RigFlow] Enabling Rigify...")
try:
    bpy.ops.preferences.addon_enable(module="rigify")
    print("[RigFlow] Rigify OK")
except Exception:
    import addon_utils
    addon_utils.enable("rigify", default_set=True, persistent=True)
    print("[RigFlow] Rigify via addon_utils")

# ── Args ──────────────────────────────────────────────────────────────────────
argv = sys.argv
argv = argv[argv.index("--") + 1:] if "--" in argv else []
parser = argparse.ArgumentParser()
parser.add_argument("--input",     required=True)
parser.add_argument("--output",    required=True)
parser.add_argument("--bones",     required=True)
parser.add_argument("--format",    default="fbx")
parser.add_argument("--landmarks", default=None)
args = parser.parse_args(argv)

TARGET_HEIGHT = 1.75   # metres — Rigify default metarig is 2 m, we scale to this


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def clear_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    if bpy.context.active_object and bpy.context.active_object.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=True)
    try:
        bpy.ops.preferences.addon_enable(module="rigify")
    except Exception:
        import addon_utils
        addon_utils.enable("rigify", default_set=True, persistent=True)
    print("[RigFlow] Scene cleared")


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
    return [o for o in bpy.data.objects
            if o.type == "MESH" and not o.name.startswith("WGT-")]


def select_all_meshes(meshes):
    bpy.ops.object.select_all(action="DESELECT")
    for o in meshes:
        o.select_set(True)
    bpy.context.view_layer.objects.active = meshes[0]


def get_all_verts(meshes):
    verts = []
    for obj in meshes:
        for v in obj.data.vertices:
            verts.append(obj.matrix_world @ v.co)
    if not verts:
        raise RuntimeError("No vertices found — is the mesh empty?")
    return verts


def bbox(verts):
    """Returns (sx, sy, sz, min_x, min_y, min_z, max_x, max_y, max_z)."""
    xs = [v.x for v in verts]
    ys = [v.y for v in verts]
    zs = [v.z for v in verts]
    return (
        max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs),
        min(xs), min(ys), min(zs),
        max(xs), max(ys), max(zs),
    )


def apply_rotation(meshes, axis, degrees):
    select_all_meshes(meshes)
    bpy.ops.transform.rotate(
        value=math.radians(degrees),
        orient_axis=axis,
        orient_type="GLOBAL",
    )
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=False)


def apply_scale(meshes, factor):
    select_all_meshes(meshes)
    bpy.ops.transform.resize(value=(factor, factor, factor))
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)


def move_to_origin(meshes):
    """Centre on X/Z, put feet at Z=0."""
    verts = get_all_verts(meshes)
    sx, sy, sz, mnx, mny, mnz, mxx, mxy, mxz = bbox(verts)
    cx = (mxx + mnx) / 2
    cy = (mxy + mny) / 2
    for o in meshes:
        o.location.x -= cx
        o.location.y -= cy
        o.location.z -= mnz
    select_all_meshes(meshes)
    bpy.ops.object.transform_apply(location=True, rotation=False, scale=False)


# ─────────────────────────────────────────────────────────────────────────────
# Core: normalize mesh into standard Blender humanoid space
# Called identically for auto-rig, re-rig, and landmark modes.
# ─────────────────────────────────────────────────────────────────────────────

def normalize_mesh(meshes) -> dict:
    """
    Transforms the mesh so that:
      • Z  = up  (tallest axis)
      • -Y = front (character faces away from camera in front view)
      • height = TARGET_HEIGHT metres
      • feet at Z = 0, centred on X / Z

    Returns a props dict with bounding-box measurements of the
    normalised mesh, used for metarig placement.
    """

    # ── Step 0: apply all existing transforms ─────────────────────────────────
    select_all_meshes(meshes)
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)

    verts = get_all_verts(meshes)
    sx, sy, sz, *_ = bbox(verts)
    print(f"[RigFlow] Raw dims — X:{sx:.3f}  Y:{sy:.3f}  Z:{sz:.3f}")

    # ── Step 1: make Z the tallest axis ──────────────────────────────────────
    def z_is_tallest(v):
        a, b, c, *_ = bbox(v)
        return c > max(a, b) * 1.1   # 10 % threshold

    if not z_is_tallest(verts):
        # Try each 90° rotation and keep the first one that makes Z tallest
        candidates = [
            ("X", -90), ("X", 90),
            ("Z", 90),  ("Z", -90),
            ("X", 180),
        ]
        fixed = False
        for axis, deg in candidates:
            apply_rotation(meshes, axis, deg)
            v2 = get_all_verts(meshes)
            if z_is_tallest(v2):
                a, b, c, *_ = bbox(v2)
                print(f"[RigFlow] Upright: rotated {deg}° {axis}  Z:{c:.3f}")
                fixed = True
                break
            apply_rotation(meshes, axis, -deg)   # undo

        if not fixed:
            # Fallback: find the tallest axis and rotate it to Z
            verts = get_all_verts(meshes)
            sx2, sy2, sz2, *_ = bbox(verts)
            if sx2 >= sy2 and sx2 >= sz2:
                apply_rotation(meshes, "Y", 90)
                print(f"[RigFlow] Fallback: rotated X→Z")
            elif sy2 >= sx2 and sy2 >= sz2:
                apply_rotation(meshes, "X", -90)
                print(f"[RigFlow] Fallback: rotated Y→Z")
    else:
        print("[RigFlow] Already upright (Z tallest)")

    # ── Step 2: ensure character faces -Y ────────────────────────────────────
    # After step 1 the character is upright.
    # For a humanoid in T-pose the arms extend along one horizontal axis.
    # We want arms along X and front/back along Y.
    #
    # Test: rotate Z by -90° and +90° and pick whichever gives X > Y
    # (arms along X = standard T-pose orientation).
    # If neither is clearly better, don't rotate (avoids making things worse).

    verts = get_all_verts(meshes)
    sx, sy, sz, *_ = bbox(verts)

    if sy > sx * 1.15:   # model is deep front-to-back → arms are along Y
        # Try -90° (most models: original front = +X, becomes -Y after -90°)
        apply_rotation(meshes, "Z", -90)
        v2 = get_all_verts(meshes)
        a2, b2, *_ = bbox(v2)
        if b2 > a2 * 1.05:
            # Still Y-dominant → undo and try +90°
            apply_rotation(meshes, "Z", 180)   # net effect: original → +90°
            v3 = get_all_verts(meshes)
            a3, b3, *_ = bbox(v3)
            print(f"[RigFlow] Facing: +90° Z  X:{a3:.3f} Y:{b3:.3f}")
        else:
            print(f"[RigFlow] Facing: -90° Z  X:{a2:.3f} Y:{b2:.3f}")
    else:
        print(f"[RigFlow] Facing: no rotation needed  X:{sx:.3f} Y:{sy:.3f}")

    # ── Step 3: scale to TARGET_HEIGHT ───────────────────────────────────────
    move_to_origin(meshes)
    verts = get_all_verts(meshes)
    sx, sy, sz, *_ = bbox(verts)

    if sz > 0.001 and abs(sz - TARGET_HEIGHT) > 0.02:
        factor = TARGET_HEIGHT / sz
        apply_scale(meshes, factor)
        print(f"[RigFlow] Scaled ×{factor:.4f}  ({sz:.3f} → {TARGET_HEIGHT} m)")
        move_to_origin(meshes)

    # ── Final measurement ─────────────────────────────────────────────────────
    verts = get_all_verts(meshes)
    sx, sy, sz, mnx, mny, mnz, mxx, mxy, mxz = bbox(verts)
    print(f"[RigFlow] Normalised — h:{sz:.4f} m  w:{sx:.4f} m")

    return {
        "height": sz, "width": sx, "depth": sy,
        "floor_z": 0.0,
        "min_x": mnx, "max_x": mxx,
        "min_y": mny, "max_y": mxy,
        "min_z": 0.0, "max_z": mxz,
        "cx": (mxx + mnx) / 2,
        "cy": (mxy + mny) / 2,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Landmark coordinate conversion
# ─────────────────────────────────────────────────────────────────────────────

def threejs_to_blender(pt, props) -> Vector:
    """
    Convert a landmark from Three.js / GLB Y-up space → Blender Z-up space,
    then undo the AutoFit scale so the coordinate matches the normalised mesh.

    Three.js AutoFit scales the model to TARGET_DISPLAY=2.0 units.
    Our Blender mesh is at TARGET_HEIGHT=1.75 m.
    So we scale by (TARGET_HEIGHT / TARGET_DISPLAY).

    Three.js Y-up → Blender Z-up:
        Blender X =  Three.js X
        Blender Y = -Three.js Z
        Blender Z =  Three.js Y
    """
    TARGET_DISPLAY = 2.0   # must match ModelViewer.tsx TARGET_HEIGHT
    scale = TARGET_HEIGHT / TARGET_DISPLAY

    x, y, z = pt
    # Axis swap
    bx =  x * scale
    by = -z * scale
    bz =  y * scale
    return Vector((bx, by, bz))


# ─────────────────────────────────────────────────────────────────────────────
# Metarig
# ─────────────────────────────────────────────────────────────────────────────

def create_metarig(props, landmarks=None):
    print("[RigFlow] Creating metarig...")

    # Add the human metarig template
    created = False
    for op in [
        lambda: bpy.ops.object.armature_human_metarig_add(),
        lambda: bpy.ops.armature.metarig_sample_add(metarig_type="human"),
    ]:
        try:
            op()
            created = True
            break
        except Exception as e:
            print(f"[RigFlow]   op failed: {e}")
    if not created:
        raise RuntimeError("Could not create metarig")

    metarig = bpy.context.active_object
    if not metarig or metarig.type != "ARMATURE":
        raise RuntimeError("No armature after metarig creation")

    bpy.context.view_layer.objects.active = metarig
    bpy.ops.object.mode_set(mode="EDIT")

    # Remove face rig (causes spikes on most game characters)
    def _remove(bone):
        for child in list(bone.children):
            _remove(child)
        metarig.data.edit_bones.remove(bone)

    for name in ["face", "teeth.T", "teeth.B", "tongue"]:
        b = metarig.data.edit_bones.get(name)
        if b:
            _remove(b)

    eb = metarig.data.edit_bones

    if landmarks:
        _place_bones_from_landmarks(eb, props, landmarks)
    else:
        _place_bones_auto(eb, props)

    bpy.ops.object.mode_set(mode="OBJECT")
    print("[RigFlow] Metarig positioned")
    return metarig


def _place_bones_auto(eb, props):
    """Scale the entire metarig proportionally to the normalised mesh."""
    bpy.ops.object.mode_set(mode="OBJECT")
    metarig = bpy.context.active_object

    # Rigify default metarig is ~2 m tall; scale to mesh height
    scale = props["height"] / 2.0
    metarig.scale = (scale, scale, scale)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)

    # Place feet at Z=0 (mesh floor)
    metarig.location = (0, 0, 0)
    bpy.ops.object.transform_apply(location=True, rotation=False, scale=False)

    print(f"[RigFlow] Auto metarig scale: {scale:.4f}")
    bpy.ops.object.mode_set(mode="EDIT")


def _place_bones_from_landmarks(eb, props, landmarks):
    """Place each bone group precisely from user-provided landmark positions."""

    chin  = landmarks["chin"]
    lw    = landmarks["left_wrist"]
    rw    = landmarks["right_wrist"]
    groin = landmarks["groin"]
    la    = landmarks["left_ankle"]
    ra    = landmarks["right_ankle"]

    print(f"[RigFlow] Landmarks (Blender Z-up):")
    for k, v in [("chin", chin), ("groin", groin), ("lw", lw),
                 ("rw", rw), ("la", la), ("ra", ra)]:
        print(f"  {k}: ({v.x:.3f}, {v.y:.3f}, {v.z:.3f})")

    body_h = chin.z - groin.z
    body_cx = (props["min_x"] + props["max_x"]) / 2.0

    # ── Spine ─────────────────────────────────────────────────────────────
    ratios = [0.0, 0.18, 0.38, 0.58, 0.78, 0.92]
    names  = ["spine", "spine.001", "spine.002", "spine.003", "spine.004", "spine.005"]
    for i, (name, r) in enumerate(zip(names, ratios)):
        bone = eb.get(name)
        if not bone:
            continue
        nr = ratios[i + 1] if i + 1 < len(ratios) else 1.0
        bone.head = groin + (chin - groin) * r
        bone.tail = groin + (chin - groin) * nr

    head_bone = eb.get("spine.006") or eb.get("spine.005")
    if head_bone:
        head_bone.head = chin
        head_bone.tail = chin + Vector((0, 0, body_h * 0.15))

    # ── Arms ──────────────────────────────────────────────────────────────
    shoulder_z = groin.z + body_h * 0.82

    # Direct mapping: user "left_wrist" = character anatomical LEFT = Rigify .L
    for side, wrist in [("L", lw), ("R", rw)]:
        sh_pos    = Vector((wrist.x, wrist.y, shoulder_z))
        neck_pos  = Vector((body_cx, wrist.y, shoulder_z))
        # Elbow: 55% along arm, slightly forward to avoid collinear crash
        elbow_pos = sh_pos + (wrist - sh_pos) * 0.55 + Vector((0, 0.06, -0.02))
        hand_tip  = wrist + (wrist - elbow_pos).normalized() * 0.07

        for bname, h, t in [
            (f"shoulder.{side}",  neck_pos,  sh_pos),
            (f"upper_arm.{side}", sh_pos,    elbow_pos),
            (f"forearm.{side}",   elbow_pos, wrist),
            (f"hand.{side}",      wrist,     hand_tip),
        ]:
            bone = eb.get(bname)
            if bone:
                bone.head, bone.tail = h, t

    # ── Legs ──────────────────────────────────────────────────────────────
    for side, ankle in [("L", la), ("R", ra)]:
        hip_pos  = Vector((ankle.x, ankle.y, groin.z))
        knee_pos = Vector((
            ankle.x * 0.97,
            ankle.y - 0.04,           # slightly forward for IK pole
            (groin.z + ankle.z) / 2 + 0.02,
        ))
        toe_pos = ankle + Vector((0, -0.09, 0))

        for bname, h, t in [
            (f"thigh.{side}", hip_pos,  knee_pos),
            (f"shin.{side}",  knee_pos, ankle),
            (f"foot.{side}",  ankle,    toe_pos),
            (f"toe.{side}",   toe_pos,  toe_pos + Vector((0, -0.04, 0))),
        ]:
            bone = eb.get(bname)
            if bone:
                bone.head, bone.tail = h, t

    print("[RigFlow] Landmark bones placed")


# ─────────────────────────────────────────────────────────────────────────────
# Rig generation
# ─────────────────────────────────────────────────────────────────────────────

def generate_rig(metarig):
    print("[RigFlow] Generating full rig...")
    bpy.context.view_layer.objects.active = metarig
    bpy.ops.object.mode_set(mode="POSE")
    try:
        bpy.ops.pose.rigify_generate()
    except Exception as e:
        raise RuntimeError(f"rigify_generate failed: {e}")
    bpy.ops.object.mode_set(mode="OBJECT")
    rig = bpy.context.active_object
    print(f"[RigFlow] Generated rig: {rig.name}")
    return rig


# ─────────────────────────────────────────────────────────────────────────────
# Binding — always ARMATURE_AUTO
# ─────────────────────────────────────────────────────────────────────────────

def bind_to_rig(meshes, rig):
    """
    Use Blender's heat-diffusion automatic weight painting.
    Works correctly for single-mesh, multi-mesh, any body shape.
    Much more reliable than manual vertex group assignment.
    """
    print(f"[RigFlow] Binding {len(meshes)} mesh(es) with ARMATURE_AUTO...")
    bpy.ops.object.select_all(action="DESELECT")
    for m in meshes:
        m.select_set(True)
    bpy.context.view_layer.objects.active = rig
    bpy.ops.object.parent_set(type="ARMATURE_AUTO")
    print("[RigFlow] Binding complete")


# ─────────────────────────────────────────────────────────────────────────────
# Export
# ─────────────────────────────────────────────────────────────────────────────

def clean_and_export(rig, meshes, output_path):
    # Remove widget meshes (Rigify control shapes — not needed in export)
    widgets = [o for o in bpy.data.objects if o.name.startswith("WGT-")]
    print(f"[RigFlow] Removing {len(widgets)} widget(s)")
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

    # Strip non-deform bones (control/mechanism bones — keep only DEF-)
    bpy.context.view_layer.objects.active = rig
    bpy.ops.object.mode_set(mode="EDIT")
    to_remove = [b for b in rig.data.edit_bones if not b.name.startswith("DEF-")]
    for b in to_remove:
        rig.data.edit_bones.remove(b)
    bpy.ops.object.mode_set(mode="OBJECT")
    print(f"[RigFlow] {len(rig.data.bones)} deform bones remain")

    # Export
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
    "DEF-spine":         "Hips",
    "DEF-spine.001":     "Spine",
    "DEF-spine.002":     "Spine1",
    "DEF-spine.003":     "Spine2",
    "DEF-spine.004":     "Neck",
    "DEF-spine.005":     "Head",
    "DEF-thigh.L":       "LeftUpLeg",
    "DEF-shin.L":        "LeftLeg",
    "DEF-foot.L":        "LeftFoot",
    "DEF-toe.L":         "LeftToeBase",
    "DEF-thigh.R":       "RightUpLeg",
    "DEF-shin.R":        "RightLeg",
    "DEF-foot.R":        "RightFoot",
    "DEF-toe.R":         "RightToeBase",
    "DEF-shoulder.L":    "LeftShoulder",
    "DEF-upper_arm.L":   "LeftArm",
    "DEF-forearm.L":     "LeftForeArm",
    "DEF-hand.L":        "LeftHand",
    "DEF-shoulder.R":    "RightShoulder",
    "DEF-upper_arm.R":   "RightArm",
    "DEF-forearm.R":     "RightForeArm",
    "DEF-hand.R":        "RightHand",
    "DEF-thumb.01.L":    "LeftHandThumb1",
    "DEF-f_index.01.L":  "LeftHandIndex1",
    "DEF-f_middle.01.L": "LeftHandMiddle1",
    "DEF-f_ring.01.L":   "LeftHandRing1",
    "DEF-f_pinky.01.L":  "LeftHandPinky1",
    "DEF-thumb.01.R":    "RightHandThumb1",
    "DEF-f_index.01.R":  "RightHandIndex1",
    "DEF-f_middle.01.R": "RightHandMiddle1",
    "DEF-f_ring.01.R":   "RightHandRing1",
    "DEF-f_pinky.01.R":  "RightHandPinky1",
}


def build_bone_map(rig) -> dict:
    mapping = {}
    for bone in rig.data.bones:
        mixamo = RIGIFY_TO_MIXAMO.get(bone.name)
        if mixamo:
            mapping[mixamo] = bone.name
    print(f"[RigFlow] {len(mapping)} bones mapped to Mixamo names")
    return mapping


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────
print("=" * 60)
print(f"[RigFlow] Input:  {args.input}")
print(f"[RigFlow] Output: {args.output}")
print(f"[RigFlow] Mode:   {'LANDMARK' if args.landmarks else 'AUTO'}")
print("=" * 60)

try:
    raw_landmarks = json.loads(args.landmarks) if args.landmarks else None

    clear_scene()
    import_model(args.input, args.format)

    meshes = get_meshes()
    if not meshes:
        raise RuntimeError("No mesh objects found after import")
    print(f"[RigFlow] {len(meshes)} mesh object(s) found")

    # ── Normalise mesh (same for all modes) ───────────────────────────────
    props = normalize_mesh(meshes)

    # ── Convert landmarks if provided ─────────────────────────────────────
    landmarks = None
    if raw_landmarks:
        landmarks = {
            k: threejs_to_blender(v, props)
            for k, v in raw_landmarks.items()
        }

    # ── Build and fit metarig ─────────────────────────────────────────────
    metarig = create_metarig(props, landmarks=landmarks)

    # ── Generate full Rigify rig ──────────────────────────────────────────
    rig = generate_rig(metarig)

    # ── Bind mesh to rig ──────────────────────────────────────────────────
    bind_to_rig(meshes, rig)

    # ── Export ────────────────────────────────────────────────────────────
    clean_and_export(rig, meshes, args.output)

    bone_map = build_bone_map(rig)
    Path(args.bones).write_text(json.dumps(bone_map, indent=2))

    print("=" * 60)
    print(f"[RigFlow] SUCCESS — {len(bone_map)} bones mapped")
    print("=" * 60)

except Exception as e:
    print(f"\n[RigFlow] FATAL ERROR: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)