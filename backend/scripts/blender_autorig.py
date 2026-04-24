"""
RigFlow Blender headless auto-rig script.

Pipeline:
  1. Import mesh (FBX / GLB / OBJ), bake any import-time transforms
  2. Orient: longest axis → Z (up), widest horizontal axis → X (T-pose arms)
  3. Create Rigify human metarig at its default size — this is the scale target
  4. Scale mesh to match metarig height; align feet + XY centre with metarig
  5. (Optional) Move metarig bones to user-supplied landmarks
  6. Generate the final rig from the metarig — its scale is never touched
  7. Parent mesh to rig with ARMATURE_AUTO (automatic weights)
  8. Strip non-DEF bones, export GLB, write Rigify → Mixamo bone map
"""

import argparse
import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector


# The frontend's ModelViewer rescales every preview to this many units tall,
# and the landmark picker captures clicks in that space. We reuse the ratio
# when converting landmark positions back into Blender world coords.
THREE_DISPLAY_HEIGHT = 2.0


class NotHumanoidError(RuntimeError):
    """Raised when the input mesh fails the humanoid-shape validation.
    Mapped to subprocess exit code 2 so the Django pipeline can distinguish
    a user-facing rejection from a generic Blender failure."""


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def log(msg):
    print(f"[RigFlow] {msg}")


def enable_rigify():
    try:
        bpy.ops.preferences.addon_enable(module="rigify")
    except Exception:
        import addon_utils
        addon_utils.enable("rigify", default_set=True, persistent=True)


def parse_args():
    argv = sys.argv
    argv = argv[argv.index("--") + 1:] if "--" in argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--input",     required=True)
    p.add_argument("--output",    required=True)
    p.add_argument("--bones",     required=True)
    p.add_argument("--format",    default="fbx")
    p.add_argument("--landmarks", default=None)
    return p.parse_args(argv)


def deselect_all():
    try:
        if bpy.context.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
    except RuntimeError:
        pass
    bpy.ops.object.select_all(action="DESELECT")


def activate(obj, *, solo=True):
    """Make `obj` the only selected + active object. Blender ops act on the
    selection, so every transform_apply/rotate/scale happens against a known,
    minimal target — this is what the old script got wrong."""
    if solo:
        deselect_all()
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj


def apply_transforms(objs, *, location=False, rotation=False, scale=False):
    if not objs:
        return
    deselect_all()
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    bpy.ops.object.transform_apply(
        location=location, rotation=rotation, scale=scale)


# ---------------------------------------------------------------------------
# Scene reset + import
# ---------------------------------------------------------------------------

def clear_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    enable_rigify()


def import_model(path, fmt):
    fmt = fmt.lower()
    log(f"Importing {fmt}: {path}")
    if fmt == "fbx":
        bpy.ops.import_scene.fbx(filepath=path)
    elif fmt in ("glb", "gltf"):
        bpy.ops.import_scene.gltf(filepath=path)
    elif fmt == "obj":
        bpy.ops.wm.obj_import(filepath=path)
    else:
        raise ValueError(f"Unsupported format: {fmt}")


def get_meshes():
    return [o for o in bpy.data.objects
            if o.type == "MESH" and not o.name.startswith("WGT-")]


def strip_non_meshes():
    """Drop any armatures, empties, cameras, lights the importer added. We
    only keep raw geometry — the source rig (if any) is replaced with Rigify."""
    keep = {id(m) for m in get_meshes()}
    for obj in list(bpy.data.objects):
        if id(obj) not in keep:
            bpy.data.objects.remove(obj, do_unlink=True)


# ---------------------------------------------------------------------------
# Geometry measurement
# ---------------------------------------------------------------------------

def world_vertices(meshes):
    verts = []
    for obj in meshes:
        for v in obj.data.vertices:
            verts.append(obj.matrix_world @ v.co)
    if not verts:
        raise RuntimeError("No vertices in imported mesh")
    return verts


def aabb(points):
    xs = [p.x for p in points]
    ys = [p.y for p in points]
    zs = [p.z for p in points]
    return {
        "min":  Vector((min(xs), min(ys), min(zs))),
        "max":  Vector((max(xs), max(ys), max(zs))),
        "size": Vector((max(xs) - min(xs),
                        max(ys) - min(ys),
                        max(zs) - min(zs))),
    }


def armature_aabb(arm):
    pts = []
    for b in arm.data.bones:
        pts.append(arm.matrix_world @ b.head_local)
        pts.append(arm.matrix_world @ b.tail_local)
    return aabb(pts)


# ---------------------------------------------------------------------------
# Orientation: "spin it to the right axis"
# ---------------------------------------------------------------------------

def orient_z_up(meshes):
    """Make the tallest axis Z and the widest horizontal axis X.
    Handles Y-up FBX, Z-up FBX, glTF, OBJ without special-casing per format."""
    # Bake any import-time object transforms so world AABB is trustworthy.
    apply_transforms(meshes, location=True, rotation=True, scale=True)

    b = aabb(world_vertices(meshes))
    sx, sy, sz = b["size"].x, b["size"].y, b["size"].z

    # Step 1: longest axis becomes Z
    if sz < sx or sz < sy:
        deselect_all()
        for m in meshes:
            m.select_set(True)
        bpy.context.view_layer.objects.active = meshes[0]

        if sy >= sx:
            # Y tallest → rotate +90° about X: +Y → +Z
            bpy.ops.transform.rotate(
                value=math.radians(90),
                orient_axis="X", orient_type="GLOBAL")
            log("Rotated Y → Z (+90° X)")
        else:
            # X tallest → rotate -90° about Y: +X → +Z
            bpy.ops.transform.rotate(
                value=math.radians(-90),
                orient_axis="Y", orient_type="GLOBAL")
            log("Rotated X → Z (-90° Y)")
        apply_transforms(meshes, rotation=True)

    # Step 2: widest horizontal axis becomes X (T-pose arms extend along X).
    # Threshold of 1.1 avoids spurious rotation for near-square silhouettes.
    b = aabb(world_vertices(meshes))
    if b["size"].y > b["size"].x * 1.1:
        deselect_all()
        for m in meshes:
            m.select_set(True)
        bpy.context.view_layer.objects.active = meshes[0]
        bpy.ops.transform.rotate(
            value=math.radians(-90),
            orient_axis="Z", orient_type="GLOBAL")
        log("Rotated Y → X (-90° Z) for T-pose alignment")
        apply_transforms(meshes, rotation=True)


# ---------------------------------------------------------------------------
# Humanoid-shape gate
# ---------------------------------------------------------------------------

def validate_humanoid(meshes):
    """Reject clearly non-humanoid meshes before spending time on rigging.

    Called after orient_z_up so Z is already the tallest axis and X is the
    wider horizontal (arms / shoulders) while Y is the thinner one (body
    depth). We look at two AABB ratios:

      - longest / shortest ≥ 3    — a human is much taller than they are deep
      - middle  / shortest ≥ 1.3  — shoulder/arm span is meaningfully wider
                                    than body depth

    Together these accept T-pose, A-pose, and standing characters while
    rejecting cars, boxes, spheres, buildings, tall-thin trunks, etc.
    Raises NotHumanoidError with a user-facing message on rejection."""
    b = aabb(world_vertices(meshes))
    dims = sorted((b["size"].x, b["size"].y, b["size"].z), reverse=True)
    longest, middle, shortest = dims

    if shortest <= 1e-6:
        raise NotHumanoidError("Uploaded mesh is flat — cannot detect body.")

    if longest / shortest < 3.0:
        raise NotHumanoidError(
            f"Uploaded model is not humanoid: it's too bulky "
            f"(tallest {longest:.2f} vs thinnest {shortest:.2f}, "
            f"ratio {longest / shortest:.2f}:1 — expected at least 3:1)."
        )

    if middle / shortest < 1.3:
        raise NotHumanoidError(
            f"Uploaded model is not humanoid: body is too symmetric "
            f"(width {middle:.2f} vs depth {shortest:.2f}, "
            f"ratio {middle / shortest:.2f}:1 — expected at least 1.3:1)."
        )

    log(f"Humanoid OK: {longest:.2f} × {middle:.2f} × {shortest:.2f}")


# ---------------------------------------------------------------------------
# Metarig
# ---------------------------------------------------------------------------

def create_metarig():
    # Blender 4.x uses armature_human_metarig_add; older builds use
    # metarig_sample_add. Try both; the first that works wins.
    for op in (
        lambda: bpy.ops.object.armature_human_metarig_add(),
        lambda: bpy.ops.armature.metarig_sample_add(metarig_type="human"),
    ):
        try:
            op()
            break
        except Exception:
            continue
    mr = bpy.context.active_object
    if not mr or mr.type != "ARMATURE":
        raise RuntimeError("Failed to create Rigify metarig")
    mr.name = "metarig"
    mr.location = (0.0, 0.0, 0.0)
    return mr


def remove_face_bones(metarig):
    activate(metarig)
    bpy.ops.object.mode_set(mode="EDIT")

    def kill(bone):
        for c in list(bone.children):
            kill(c)
        metarig.data.edit_bones.remove(bone)

    for name in ("face", "teeth.T", "teeth.B", "tongue"):
        b = metarig.data.edit_bones.get(name)
        if b:
            kill(b)

    bpy.ops.object.mode_set(mode="OBJECT")


# ---------------------------------------------------------------------------
# "Scale it to the rig"
# ---------------------------------------------------------------------------

def scale_mesh_to_metarig(meshes, metarig):
    """Uniform-scale every mesh so the combined height matches the metarig,
    then translate so feet (min Z) and XY centre match the metarig's frame."""
    target = armature_aabb(metarig)
    target_h = target["size"].z
    target_floor = target["min"].z
    target_cx = (target["min"].x + target["max"].x) / 2
    target_cy = (target["min"].y + target["max"].y) / 2

    m = aabb(world_vertices(meshes))
    mh = m["size"].z
    if mh <= 1e-6:
        raise RuntimeError(f"Mesh height {mh} is invalid")

    factor = target_h / mh

    # Bake location so every mesh origin sits at world (0,0,0). This makes the
    # next per-object scale pivot about world origin for ALL meshes uniformly.
    apply_transforms(meshes, location=True, rotation=True, scale=True)

    for obj in meshes:
        obj.scale = tuple(v * factor for v in obj.scale)
    apply_transforms(meshes, scale=True)

    m2 = aabb(world_vertices(meshes))
    dx = target_cx - (m2["min"].x + m2["max"].x) / 2
    dy = target_cy - (m2["min"].y + m2["max"].y) / 2
    dz = target_floor - m2["min"].z
    for obj in meshes:
        obj.location.x += dx
        obj.location.y += dy
        obj.location.z += dz
    apply_transforms(meshes, location=True)

    log(f"Scaled mesh x{factor:.4f} → {target_h:.3f}m, aligned to metarig")


# ---------------------------------------------------------------------------
# Landmarks (optional — used by /rigs/{id}/rerig-landmarks/)
# ---------------------------------------------------------------------------

def threejs_to_blender(pt, mesh_height):
    """Three.js world-space (Y-up, `THREE_DISPLAY_HEIGHT` tall) → Blender."""
    s = mesh_height / THREE_DISPLAY_HEIGHT
    x, y, z = pt
    return Vector((x * s, -z * s, y * s))


def place_bones_from_landmarks(metarig, landmarks, mesh_height):
    lmk = {k: threejs_to_blender(v, mesh_height) for k, v in landmarks.items()}
    chin, groin = lmk["chin"], lmk["groin"]
    lw, rw = lmk["left_wrist"], lmk["right_wrist"]
    la, ra = lmk["left_ankle"], lmk["right_ankle"]

    activate(metarig)
    bpy.ops.object.mode_set(mode="EDIT")
    eb = metarig.data.edit_bones

    spine = ["spine", "spine.001", "spine.002",
             "spine.003", "spine.004", "spine.005"]
    ratios = [0.0, 0.18, 0.38, 0.58, 0.78, 0.92, 1.0]
    for i, name in enumerate(spine):
        b = eb.get(name)
        if not b:
            continue
        r0, r1 = ratios[i], ratios[i + 1]
        b.head = groin + (chin - groin) * r0
        b.tail = groin + (chin - groin) * r1

    body_h = max(0.2, chin.z - groin.z)
    for side, wrist in (("L", lw), ("R", rw)):
        shoulder = Vector((wrist.x, wrist.y, groin.z + body_h * 0.82))
        elbow    = shoulder + (wrist - shoulder) * 0.55 + Vector((0, 0.05, -0.02))
        hand_end = wrist + (wrist - elbow).normalized() * 0.07
        for name, h, t in (
            (f"upper_arm.{side}", shoulder, elbow),
            (f"forearm.{side}",   elbow,    wrist),
            (f"hand.{side}",      wrist,    hand_end),
        ):
            b = eb.get(name)
            if b:
                b.head, b.tail = h, t

    for side, ankle in (("L", la), ("R", ra)):
        hip  = Vector((ankle.x, ankle.y, groin.z))
        knee = Vector((ankle.x * 0.97,
                       ankle.y - 0.04,
                       (groin.z + ankle.z) / 2 + 0.02))
        toe  = ankle + Vector((0, -0.09, 0))
        for name, h, t in (
            (f"thigh.{side}", hip,   knee),
            (f"shin.{side}",  knee,  ankle),
            (f"foot.{side}",  ankle, toe),
            (f"toe.{side}",   toe,   toe + Vector((0, -0.04, 0))),
        ):
            b = eb.get(name)
            if b:
                b.head, b.tail = h, t

    bpy.ops.object.mode_set(mode="OBJECT")


# ---------------------------------------------------------------------------
# Generate, strip, bind, export
# ---------------------------------------------------------------------------

def generate_rig(metarig):
    activate(metarig)
    bpy.ops.object.mode_set(mode="POSE")
    bpy.ops.pose.rigify_generate()
    bpy.ops.object.mode_set(mode="OBJECT")
    rig = bpy.context.active_object
    if not rig or rig.type != "ARMATURE" or rig is metarig:
        raise RuntimeError("Rigify generation failed")
    log(f"Generated rig: {rig.name}")
    return rig


def strip_to_deform_bones(rig):
    """Keep only DEF-* bones, rebuilt into a clean DEF-only parent chain.

    Rigify's generated rig parents DEF bones through ORG/MCH intermediaries
    whose exact names vary by Blender/Rigify version — walking up and
    matching on "DEF-{suffix}" works for the spine and legs but not for
    arms. Rather than keep chasing that, we rebuild the DEF hierarchy
    explicitly from a hard-coded table of Rigify's human-rig topology, and
    fall back to name heuristics for twist/finger segments. Without this
    the exported skin has DEF bones whose parent is a glTF Group, and
    three.js SkeletonHelper only draws edges where parent.isBone."""
    activate(rig)
    bpy.ops.object.mode_set(mode="EDIT")
    ebs = rig.data.edit_bones

    parent_map = {
        "DEF-spine.001": "DEF-spine",
        "DEF-spine.002": "DEF-spine.001",
        "DEF-spine.003": "DEF-spine.002",
        "DEF-spine.004": "DEF-spine.003",
        "DEF-spine.005": "DEF-spine.004",
        "DEF-spine.006": "DEF-spine.005",
    }
    for side in ("L", "R"):
        parent_map.update({
            f"DEF-thigh.{side}":     "DEF-spine",
            f"DEF-shin.{side}":      f"DEF-thigh.{side}",
            f"DEF-foot.{side}":      f"DEF-shin.{side}",
            f"DEF-toe.{side}":       f"DEF-foot.{side}",
            f"DEF-shoulder.{side}":  "DEF-spine.003",
            f"DEF-upper_arm.{side}": f"DEF-shoulder.{side}",
            f"DEF-forearm.{side}":   f"DEF-upper_arm.{side}",
            f"DEF-hand.{side}":      f"DEF-forearm.{side}",
        })

    for child_name, parent_name in parent_map.items():
        c = ebs.get(child_name)
        p = ebs.get(parent_name)
        if c and p:
            c.parent = p

    # Twists/fingers + any DEF bone not in the explicit map.
    for b in list(ebs):
        if not b.name.startswith("DEF-") or b.name in parent_map:
            continue

        # DEF-upper_arm.L.001  →  DEF-upper_arm.L (trailing .NNN suffix)
        parts = b.name.rsplit(".", 1)
        if len(parts) == 2 and parts[1].isdigit():
            base = ebs.get(parts[0])
            if base is not None and base is not b and base.name.startswith("DEF-"):
                b.parent = base
                continue

        # Fallback: walk the existing chain for any DEF ancestor, or an
        # ORG-X/MCH-X whose DEF-X sibling exists.
        p = b.parent
        new_parent = None
        while p is not None:
            if p.name.startswith("DEF-") and p is not b:
                new_parent = p
                break
            cp = None
            for prefix in ("ORG-", "MCH-"):
                if p.name.startswith(prefix):
                    cp = ebs.get("DEF-" + p.name[len(prefix):])
                    break
            if cp is not None and cp is not b:
                new_parent = cp
                break
            p = p.parent
        b.parent = new_parent

    names = [b.name for b in ebs if not b.name.startswith("DEF-")]
    for n in names:
        b = ebs.get(n)
        if b:
            ebs.remove(b)

    bpy.ops.object.mode_set(mode="OBJECT")

    log(f"Stripped to {len(rig.data.bones)} DEF bones:")
    for b in rig.data.bones:
        parent_name = b.parent.name if b.parent else "(root)"
        log(f"  {b.name} ← {parent_name}")


def bind_auto_weights(meshes, rig):
    deselect_all()
    for m in meshes:
        m.select_set(True)
    rig.select_set(True)
    bpy.context.view_layer.objects.active = rig
    bpy.ops.object.parent_set(type="ARMATURE_AUTO")
    log(f"Bound {len(meshes)} mesh(es) with ARMATURE_AUTO")


def export_glb(meshes, rig, path):
    deselect_all()
    rig.select_set(True)
    for m in meshes:
        m.select_set(True)
    bpy.context.view_layer.objects.active = rig

    bpy.ops.export_scene.gltf(
        filepath=path,
        export_format="GLB",
        export_animations=False,
        export_skins=True,
        use_selection=True,
        export_apply=True,
        export_yup=True,
    )
    log(f"Exported: {path}")


RIGIFY_TO_MIXAMO = {
    "DEF-spine":       "Hips",
    "DEF-spine.001":   "Spine",
    "DEF-spine.002":   "Spine1",
    "DEF-spine.003":   "Spine2",
    "DEF-spine.004":   "Neck",
    "DEF-spine.005":   "Head",
    "DEF-thigh.L":     "LeftUpLeg",
    "DEF-shin.L":      "LeftLeg",
    "DEF-foot.L":      "LeftFoot",
    "DEF-toe.L":       "LeftToeBase",
    "DEF-thigh.R":     "RightUpLeg",
    "DEF-shin.R":      "RightLeg",
    "DEF-foot.R":      "RightFoot",
    "DEF-toe.R":       "RightToeBase",
    "DEF-shoulder.L":  "LeftShoulder",
    "DEF-upper_arm.L": "LeftArm",
    "DEF-forearm.L":   "LeftForeArm",
    "DEF-hand.L":      "LeftHand",
    "DEF-shoulder.R":  "RightShoulder",
    "DEF-upper_arm.R": "RightArm",
    "DEF-forearm.R":   "RightForeArm",
    "DEF-hand.R":      "RightHand",
}


def build_bone_map(rig):
    mapping = {}
    for b in rig.data.bones:
        mixamo = RIGIFY_TO_MIXAMO.get(b.name)
        if mixamo:
            mapping[mixamo] = b.name
    return mapping


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    args = parse_args()
    log(f"Input:  {args.input}")
    log(f"Output: {args.output}")
    log(f"Mode:   {'LANDMARK' if args.landmarks else 'AUTO'}")

    clear_scene()
    import_model(args.input, args.format)
    strip_non_meshes()

    meshes = get_meshes()
    if not meshes:
        raise RuntimeError("No meshes found after import")
    log(f"Mesh count: {len(meshes)}")

    orient_z_up(meshes)
    validate_humanoid(meshes)

    metarig = create_metarig()
    remove_face_bones(metarig)

    scale_mesh_to_metarig(meshes, metarig)

    if args.landmarks:
        mesh_h = aabb(world_vertices(meshes))["size"].z
        place_bones_from_landmarks(metarig, json.loads(args.landmarks), mesh_h)

    rig = generate_rig(metarig)

    # Bind with the FULL Rigify rig — heat-diffusion auto-weights need the
    # complete bone graph to produce smooth weights. Rigify tags only DEF
    # bones use_deform=True, so weights land on DEF bones regardless.
    bind_auto_weights(meshes, rig)

    # Now that weights are baked into vertex groups (keyed by bone name),
    # prune to a clean DEF-only skeleton for retargeting.
    strip_to_deform_bones(rig)

    # Metarig stays in the scene but isn't selected; export uses use_selection
    # so it can't leak into the GLB.
    export_glb(meshes, rig, args.output)

    bone_map = build_bone_map(rig)
    Path(args.bones).write_text(json.dumps(bone_map, indent=2))

    log(f"SUCCESS — {len(bone_map)} bones mapped")


if __name__ == "__main__":
    try:
        main()
    except NotHumanoidError as e:
        # Single-line marker on stdout so tasks.py can extract the reason.
        print(f"[RigFlow] NOT_HUMANOID: {e}")
        sys.exit(2)
    except Exception as e:
        print(f"[RigFlow] FATAL: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
