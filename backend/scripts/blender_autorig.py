"""
RigFlow Blender headless auto-rig script.

Pipeline:
  1. Import mesh (FBX / GLB / OBJ), bake any import-time transforms
  2. Apply the user's preview-space rotation (no automatic axis guessing)
  3. Create Rigify human metarig at its default size — this is the scale target
  4. Scale mesh to match metarig height; align feet + XY centre with metarig
  5. Classify pose (T / A / arms-down / unclear) and write to --pose JSON
  6. (Optional) Move metarig bones to user-supplied landmarks
  7. Generate the final rig from the metarig — its scale is never touched
  8. Parent mesh to rig with ARMATURE_AUTO (automatic weights)
  9. Strip non-DEF bones, export GLB, write Rigify → Mixamo bone map
"""

import argparse
import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Quaternion
from mathutils import Vector
from mathutils import Matrix

# The frontend's ModelViewer rescales every preview to this many units tall,
# and the landmark picker captures clicks in that space. We reuse the ratio
# when converting landmark positions back into Blender world coords.
THREE_DISPLAY_HEIGHT = 2.0


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
    p.add_argument("--pose",      default=None,
                   help="Optional path to write detected-pose JSON.")
    p.add_argument("--format",    default="fbx")
    p.add_argument("--landmarks", default=None)
    p.add_argument("--landmarks-out", default=None,
                   help="If set, write detected landmarks (14-key three.js-space "
                        "JSON) to this path after auto-correction. Used by the "
                        "Celery task to persist landmarks on the RiggedModel.")
    # Manual preview-space Euler rotation in degrees. The upload preview runs
    # in three.js Y-up; after step 1 we convert those axes back into Blender's
    # Z-up space and trust the user's orientation over auto detection.
    p.add_argument("--render-ortho-views", action="store_true",
                   help="Render 4 ortho PNGs and write --ai-request-out JSON, then exit. "
                        "Used by the Django round-trip before calling the vision provider.")
    p.add_argument("--ai-request-out", default=None,
                   help="Path to write the AI request JSON (PNG paths + mesh metadata).")
    p.add_argument("--ortho-render-dir", default=None,
                   help="Directory to write the 4 ortho PNGs into. "
                        "Defaults to the directory containing --ai-request-out.")
    p.add_argument("--landmarks-from-ai", default=None,
                   help="Path to AI vision response JSON. When set, Blender raycasts "
                        "pixel coords into 3D seeds and uses them for landmark placement. "
                        "Wired up fully in M4; stub in M2.")
    p.add_argument("--initial-rotation-x", type=float, default=0.0)
    p.add_argument("--initial-rotation-y", type=float, default=0.0)
    p.add_argument("--initial-rotation-z", type=float, default=0.0)
    p.add_argument("--initial-rotation-qx", type=float, default=0.0)
    p.add_argument("--initial-rotation-qy", type=float, default=0.0)
    p.add_argument("--initial-rotation-qz", type=float, default=0.0)
    p.add_argument("--initial-rotation-qw", type=float, default=0.0)
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
        # Let Blender read GlobalSettings.UpAxis/FrontAxis/CoordAxis from
        # the FBX itself and apply the matching conversion. The result is
        # canonical Blender Z-up regardless of whether the source was
        # Y-up (Maya/3ds Max) or Z-up (Blender export). The frontend
        # applies a parallel orientation pass before previewing the model
        # so the upload preview and the post-import Blender state agree.
        bpy.ops.import_scene.fbx(filepath=path)
    elif fmt in ("glb", "gltf"):
        # glTF spec mandates Y-up — both Blender and three.js agree, no override needed.
        bpy.ops.import_scene.gltf(filepath=path)
    elif fmt == "obj":
        bpy.ops.wm.obj_import(filepath=path, forward_axis="NEGATIVE_Z", up_axis="Y")
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


def purge_missing_image_refs():
    """Drop bpy.data.images that point to nonexistent files with no packed
    binary data. Some FBX files reference embedded textures by placeholder
    names like '*0' / '*1' which Blender records as image filepaths that
    don't resolve on disk; without cleanup Cycles prints 'Image file ...
    does not exist' for every render pass and the affected materials render
    with whatever the Image Texture node falls back to instead of the shader
    graph's default colors."""
    removed = []
    for img in list(bpy.data.images):
        if img.source != "FILE":
            continue
        if img.packed_file is not None:
            # Embedded data intact even when filepath looks broken.
            continue
        fp = img.filepath
        if not fp:
            continue
        try:
            resolved = bpy.path.abspath(fp, library=img.library)
        except Exception:
            resolved = fp
        if Path(resolved).exists():
            continue
        removed.append((img.name, fp))
        bpy.data.images.remove(img)
    if removed:
        log(f"Purged {len(removed)} unresolvable image reference(s) after import:")
        for name, fp in removed:
            log(f"  {name!r} (was {fp!r})")


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


def _bbox_world(mesh):
    """[[xmin,ymin,zmin],[xmax,ymax,zmax]] for a single mesh in world space."""
    pts = [mesh.matrix_world @ v.co for v in mesh.data.vertices]
    if not pts:
        return [[0.0, 0.0, 0.0], [0.0, 0.0, 0.0]]
    b = aabb(pts)
    mn, mx = b["min"], b["max"]
    return [[mn.x, mn.y, mn.z], [mx.x, mx.y, mx.z]]


# ---------------------------------------------------------------------------
# User-supplied rotation (the only orientation logic that runs)
# ---------------------------------------------------------------------------

def apply_matrix_world(meshes, matrix):
    for obj in meshes:
        obj.matrix_world = matrix @ obj.matrix_world


def _preview_rotation_matrix(rotation_x, rotation_y, rotation_z):
    """Convert preview-space Euler XYZ degrees into Blender-space rotation.

    Preview axes use three.js Y-up:
      preview X == blender X
      preview Y == blender Z
      preview Z == -blender Y
    """
    rx = math.radians(rotation_x)
    ry = math.radians(rotation_y)
    rz = math.radians(rotation_z)
    preview_rot = (
        Matrix.Rotation(rz, 4, "Z") @
        Matrix.Rotation(ry, 4, "Y") @
        Matrix.Rotation(rx, 4, "X")
    )
    blender_to_preview = Matrix((
        (1.0, 0.0, 0.0, 0.0),
        (0.0, 0.0, 1.0, 0.0),
        (0.0, -1.0, 0.0, 0.0),
        (0.0, 0.0, 0.0, 1.0),
    ))
    preview_to_blender = blender_to_preview.inverted()
    return preview_to_blender @ preview_rot @ blender_to_preview


def _preview_quaternion_matrix(qx, qy, qz, qw):
    blender_to_preview = Matrix((
        (1.0, 0.0, 0.0, 0.0),
        (0.0, 0.0, 1.0, 0.0),
        (0.0, -1.0, 0.0, 0.0),
        (0.0, 0.0, 0.0, 1.0),
    ))
    preview_to_blender = blender_to_preview.inverted()
    preview_rot = Quaternion((qw, qx, qy, qz)).normalized().to_matrix().to_4x4()
    return preview_to_blender @ preview_rot @ blender_to_preview


def _orientation_correction(b):
    """Return a rotation matrix that brings a non-canonical-imported humanoid
    onto Blender's Z-up axis, or None if the post-import AABB already looks
    canonical. Mirrors the frontend's autoOrientFromSize.

    A canonical standing humanoid has Z as both the height axis (largest
    span) and the only asymmetric axis (extends from feet near 0 to head at
    +Z). When an FBX with mismatched header/content goes through the
    importer, the body can end up along Blender +Y instead, with X and Z
    centred around 0. We detect that and rotate +90° around X.
    """
    sz = b["size"]
    mn = b["min"]
    mx = b["max"]

    z_mid = (mx.z + mn.z) / 2
    y_mid = (mx.y + mn.y) / 2

    # Body extends along Y if Y span dominates AND Y is the asymmetric axis.
    y_dominant = sz.y > sz.z * 1.5 and sz.y > 0.7 * sz.x
    y_asymmetric = abs(y_mid) > 0.3 * sz.y and abs(y_mid) > 2 * abs(z_mid)

    if y_dominant and y_asymmetric:
        if y_mid > 0:
            return {
                "matrix": Matrix.Rotation(math.radians(90), 4, "X"),
                "name": "+90° X (body along +Y → +Z)",
            }
        return {
            "matrix": Matrix.Rotation(math.radians(-90), 4, "X"),
            "name": "-90° X (body along -Y → +Z)",
        }

    return None


def apply_user_rotation(
    meshes,
    user_rotation_x=0.0,
    user_rotation_y=0.0,
    user_rotation_z=0.0,
    user_rotation_quat=None,
):
    """Bake import-time transforms, then apply the user's preview-space
    rotation if non-zero. No automatic axis correction.

    Both sides of the pipeline now place the model in their respective
    canonical orientations before any user input: Blender by reading the
    FBX header (see `import_model`) and producing canonical Z-up, three.js
    by applying a parallel auto-orient pass directly on the loaded object
    so the preview shows canonical Y-up. The user's rotation is therefore
    purely a fine-tune adjustment between two already-aligned canonical
    frames, and `_preview_quaternion_matrix` translates it accordingly.
    """
    # Bake any import-time object transforms so world AABB / vertex data
    # are in a clean baseline state for the rest of the pipeline.
    apply_transforms(meshes, location=True, rotation=True, scale=True)

    b0 = aabb(world_vertices(meshes))
    log(
        f"Post-import AABB (Blender frame, before user rotation): "
        f"X[{b0['min'].x:+.2f},{b0['max'].x:+.2f}] "
        f"Y[{b0['min'].y:+.2f},{b0['max'].y:+.2f}] "
        f"Z[{b0['min'].z:+.2f},{b0['max'].z:+.2f}]"
    )

    # Auto-correction: some FBX files declare Y-up in their header but ship
    # vertices that were authored lying down (head along source +Z). Blender's
    # axis_up=Y conversion then leaves the model with body along Blender +Y
    # instead of +Z. Mirror what the frontend does: detect this from the AABB
    # and rotate to bring the body onto the +Z axis before applying the user's
    # rotation, so both sides agree on the canonical pose.
    correction = _orientation_correction(b0)
    if correction is not None:
        apply_matrix_world(meshes, correction["matrix"])
        apply_transforms(meshes, rotation=True)
        b0 = aabb(world_vertices(meshes))
        log(f"Auto-correction applied: {correction['name']}")
        log(
            f"Post-correction AABB: "
            f"X[{b0['min'].x:+.2f},{b0['max'].x:+.2f}] "
            f"Y[{b0['min'].y:+.2f},{b0['max'].y:+.2f}] "
            f"Z[{b0['min'].z:+.2f},{b0['max'].z:+.2f}]"
        )

    if not any(abs(v) > 0.5 for v in (user_rotation_x, user_rotation_y, user_rotation_z)):
        log("User rotation = identity — leaving model in loader-supplied orientation.")
        return

    if user_rotation_quat is not None:
        qx, qy, qz, qw = user_rotation_quat
        log(
            f"User quaternion (preview frame): "
            f"x={qx:+.4f}, y={qy:+.4f}, z={qz:+.4f}, w={qw:+.4f}"
        )
        rot_matrix = _preview_quaternion_matrix(qx, qy, qz, qw)
        log("Rotation source: quaternion path")
    else:
        rot_matrix = _preview_rotation_matrix(
            user_rotation_x,
            user_rotation_y,
            user_rotation_z,
        )
        log("Rotation source: Euler path (no quaternion supplied)")

    # Decompose the Blender-frame rotation so the rig_log shows what
    # actually got applied — helps debug any preview-vs-editor drift.
    as_euler = rot_matrix.to_euler("XYZ")
    log(
        f"Blender-frame rotation (XYZ Euler): "
        f"X={math.degrees(as_euler.x):+.1f}°, "
        f"Y={math.degrees(as_euler.y):+.1f}°, "
        f"Z={math.degrees(as_euler.z):+.1f}°"
    )

    apply_matrix_world(meshes, rot_matrix)
    log(
        f"Applied user rotation: X(pitch)={user_rotation_x:+.1f}°, "
        f"Y(yaw)={user_rotation_y:+.1f}°, Z(roll)={user_rotation_z:+.1f}°"
    )
    apply_transforms(meshes, rotation=True)

    b2 = aabb(world_vertices(meshes))
    log(
        f"Post-rotation AABB (Blender frame): "
        f"X[{b2['min'].x:+.2f},{b2['max'].x:+.2f}] "
        f"Y[{b2['min'].y:+.2f},{b2['max'].y:+.2f}] "
        f"Z[{b2['min'].z:+.2f},{b2['max'].z:+.2f}]"
    )


# ---------------------------------------------------------------------------
# Pose classification (T-pose / A-pose / arms-down)
# ---------------------------------------------------------------------------

def _vertices_in_z_band(meshes, z_min, z_max):
    """All world-space vertices whose Z falls within [z_min, z_max]."""
    out = []
    for obj in meshes:
        for v in obj.data.vertices:
            wv = obj.matrix_world @ v.co
            if z_min <= wv.z <= z_max:
                out.append(wv)
    return out


def detect_pose(meshes):
    """Classify the mesh's pose by measuring arm-bone angle from horizontal.

    Algorithm:
      1. body_height = full mesh AABB Z size.
      2. body_half_width = half-extent of the chest-band (45-60% height) in X.
         This is the trunk's natural width; arm vertices are anything with
         |x| beyond this.
      3. For each side (L=x<0, R=x>0), take vertices in the shoulder Z-band
         (60-82% height) outside the trunk. Anchor the shoulder at the
         5th-percentile of |x| (closest-to-body), the hand at the
         95th-percentile (farthest). Angle = atan2(|Δz|, |Δx|) gives the
         arm tilt from horizontal.
      4. Average the L and R angles. Asymmetric arms (>30° apart) → unclear.
      5. Bands:
            0-25°  T-pose      (arms horizontal)
            25-60° A-pose      (arms at ~45°)
            60-95° arms-down   (arms hanging)
            else   unclear

    Returns a dict suitable for JSON serialization.
    """
    pose = {
        "classification": "unclear",
        "angle_deg": None,
        "confidence": 0.0,
        "reason": "",
    }

    # Need vertices to work with.
    try:
        all_verts = world_vertices(meshes)
    except RuntimeError:
        pose["reason"] = "Mesh has no vertices."
        return pose

    box = aabb(all_verts)
    body_height = box["size"].z
    if body_height <= 1e-6:
        pose["reason"] = "Mesh is flat — no measurable height."
        return pose

    z_floor = box["min"].z
    chest_lo = z_floor + body_height * 0.45
    chest_hi = z_floor + body_height * 0.60
    chest = _vertices_in_z_band(meshes, chest_lo, chest_hi)
    if len(chest) < 10:
        pose["reason"] = "Too few vertices in chest band to estimate trunk width."
        return pose
    chest_xs = [abs(p.x) for p in chest]
    # 80th percentile of |x| in chest band — robust against stray vertices.
    chest_xs_sorted = sorted(chest_xs)
    body_half_width = chest_xs_sorted[int(len(chest_xs_sorted) * 0.80)]
    if body_half_width <= 1e-6:
        pose["reason"] = "Trunk width is zero — mesh likely degenerate."
        return pose

    shoulder_lo = z_floor + body_height * 0.60
    shoulder_hi = z_floor + body_height * 0.82
    shoulder_band = _vertices_in_z_band(meshes, shoulder_lo, shoulder_hi)
    if len(shoulder_band) < 20:
        pose["reason"] = "Too few vertices in shoulder band."
        return pose

    side_angles = []
    side_counts = {}
    for side, sign in (("L", -1), ("R", +1)):
        # Arm vertices: shoulder-band vertices beyond the trunk on this side.
        arm = [p for p in shoulder_band
               if (sign > 0 and p.x > body_half_width)
               or (sign < 0 and p.x < -body_half_width)]
        side_counts[side] = len(arm)
        if len(arm) < 8:
            continue
        # Anchor at "closest to body" (5th percentile of |x|) and
        # "farthest from body" (95th percentile). Median Z within each
        # subset gives a stable shoulder/hand height estimate.
        arm_sorted = sorted(arm, key=lambda p: abs(p.x))
        n = len(arm_sorted)
        near = arm_sorted[: max(1, n // 20)]
        far  = arm_sorted[-max(1, n // 20):]
        shoulder_x = sum(p.x for p in near) / len(near)
        shoulder_z = sum(p.z for p in near) / len(near)
        hand_x     = sum(p.x for p in far)  / len(far)
        hand_z     = sum(p.z for p in far)  / len(far)
        dx = abs(hand_x - shoulder_x)
        dz = abs(hand_z - shoulder_z)
        if dx <= 1e-6 and dz <= 1e-6:
            continue
        angle_deg = math.degrees(math.atan2(dz, dx))  # 0=horizontal, 90=vertical
        side_angles.append(angle_deg)

    if not side_angles:
        pose["reason"] = (
            f"Could not isolate arm vertices (L={side_counts.get('L', 0)}, "
            f"R={side_counts.get('R', 0)})."
        )
        return pose

    if len(side_angles) == 2 and abs(side_angles[0] - side_angles[1]) > 30:
        pose["reason"] = (
            f"Arms are asymmetric (L={side_angles[0]:.1f}°, "
            f"R={side_angles[1]:.1f}°)."
        )
        pose["angle_deg"] = sum(side_angles) / 2
        return pose

    avg_angle = sum(side_angles) / len(side_angles)
    pose["angle_deg"] = avg_angle
    if avg_angle <= 25:
        pose["classification"] = "t_pose"
    elif avg_angle <= 60:
        pose["classification"] = "a_pose"
    elif avg_angle <= 95:
        pose["classification"] = "arms_down"
    else:
        pose["reason"] = f"Angle {avg_angle:.1f}° outside expected ranges."
        return pose

    # Confidence: how cleanly inside the band the angle sits, plus arm
    # count (more vertices = more reliable).
    band_centers = {"t_pose": 0, "a_pose": 42, "arms_down": 80}
    band_widths  = {"t_pose": 25, "a_pose": 17, "arms_down": 17}
    center = band_centers[pose["classification"]]
    width  = band_widths[pose["classification"]]
    band_conf = max(0.0, 1.0 - abs(avg_angle - center) / width)
    sample_conf = min(1.0, sum(side_counts.values()) / 200.0)
    pose["confidence"] = round(band_conf * sample_conf, 3)
    return pose


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

    actual = aabb(world_vertices(meshes))["size"].z
    log(
        f"Scaled mesh x{factor:.4f} → {target_h:.3f}m target "
        f"(combined AABB span actually {actual:.3f}m), aligned to metarig"
    )
    if abs(actual - target_h) > target_h * 0.05:
        log(
            f"  ⚠ AABB span differs from target by >5%. Likely cause: "
            f"stray imported geometry (props, eye spheres) included in the "
            f"bounding box. Landmark conversion uses the metarig height "
            f"instead, which is unaffected."
        )


# ---------------------------------------------------------------------------
# Landmark schema
# ---------------------------------------------------------------------------

LANDMARK_KEYS = (
    "chin", "groin",
    "left_shoulder", "right_shoulder",
    "left_elbow", "right_elbow",
    "left_wrist", "right_wrist",
    "left_hip", "right_hip",
    "left_knee", "right_knee",
    "left_ankle", "right_ankle",
)

LEGACY_LANDMARK_KEYS = (
    "chin", "groin",
    "left_wrist", "right_wrist",
    "left_ankle", "right_ankle",
)


def _promote_legacy_landmarks(d):
    """Given a dict containing at least the legacy 6 keys, return a 14-key
    dict with shoulders/elbows/hips/knees filled in via the heuristics that
    were inline in the original place_bones_from_landmarks.

    Inputs may be either mathutils.Vector or any 3-tuple; the math below
    works on either as long as +, -, * are supported (the standalone test
    uses a tuple stub)."""
    chin  = d["chin"]
    groin = d["groin"]
    body_h = max(0.2, chin.z - groin.z)

    out = dict(d)
    for side, wrist in (("left", d["left_wrist"]), ("right", d["right_wrist"])):
        s_key = f"{side}_shoulder"
        e_key = f"{side}_elbow"
        if s_key not in out:
            # Shoulder X must reflect actual shoulder width, NOT the wrist's X.
            # Previous behavior (`wrist.x, wrist.y, ...`) collapsed shoulder
            # onto the wrist's X — when wrist came from `_extreme_vertex`
            # (= the mesh fingertip) the whole arm chain landed at the
            # fingertip and the rig was catastrophic. 22% of trunk height
            # (chin→groin) is a sensible humanoid shoulder half-width.
            sign = 1.0 if wrist.x >= 0 else -1.0
            shoulder_x = sign * body_h * 0.22
            shoulder = _vec((shoulder_x, wrist.y, groin.z + body_h * 0.82))
            out[s_key] = shoulder
        else:
            shoulder = out[s_key]
        if e_key not in out:
            out[e_key] = shoulder + (wrist - shoulder) * 0.55 + _vec((0.0, 0.05, -0.02))

    for side, ankle in (("left", d["left_ankle"]), ("right", d["right_ankle"])):
        h_key = f"{side}_hip"
        k_key = f"{side}_knee"
        if h_key not in out:
            out[h_key] = _vec((ankle.x, ankle.y, groin.z))
        if k_key not in out:
            out[k_key] = _vec((
                ankle.x * 0.97,
                ankle.y - 0.04,
                (groin.z + ankle.z) / 2 + 0.02,
            ))
    return out


def _vec(xyz):
    """Return a Vector when bpy is available, else preserve the input
    object's type (so the standalone test using tuple stubs still works)."""
    try:
        return Vector(xyz)
    except Exception:
        return type(xyz)(xyz) if isinstance(xyz, tuple) else xyz


def _pullback_wrist_toward_elbow(wrist, elbow, fraction=0.20):
    """Move the wrist landmark toward the elbow by `fraction` of the
    wrist→elbow distance.

    For confirmed T-pose the wrist is overridden with the geometry
    extremity (`_extreme_vertex`), which lands on the mesh fingertip on
    every humanoid character (fingers are the most distal vertex in X).
    DEF-hand is then placed at wrist→`wrist + (wrist-elbow)*0.07`, i.e.
    from the fingertip extending 7 cm further into empty space. Pulling
    the wrist back puts DEF-hand inside the actual hand mesh.

    Works on tuples or mathutils.Vector — indexing only.
    """
    dx = elbow[0] - wrist[0]
    dy = elbow[1] - wrist[1]
    dz = elbow[2] - wrist[2]
    if dx * dx + dy * dy + dz * dz < 0.0025:  # < 5 cm, degenerate
        return wrist
    return _vec((
        wrist[0] + dx * fraction,
        wrist[1] + dy * fraction,
        wrist[2] + dz * fraction,
    ))


def _clamp_elbow_y_to_arm_line(shoulder, elbow, wrist):
    """For confirmed T-pose, snap elbow Y onto the linear shoulder→wrist
    line at the elbow's X fraction.

    AI vision sometimes drops the elbow ~15-20 cm below shoulder/wrist Y
    (anatomically reading the elbow as a "joint" that should sag) — that
    produces a V-shaped arm rest pose. Animation retargeting against
    that broken rest pose makes limbs barely move ("model just rotates
    in place").

    Skips when shoulder.X ≈ wrist.X (arms folded — clamp would be wrong)
    or when the elbow is already within 6 cm of the line.

    Works on tuples or mathutils.Vector — indexing only.
    """
    sx, sy = shoulder[0], shoulder[1]
    wx, wy = wrist[0], wrist[1]
    ex, ey = elbow[0], elbow[1]
    dx = wx - sx
    if abs(dx) < 0.05:
        return elbow
    t = (ex - sx) / dx
    if t < 0.0:
        t = 0.0
    elif t > 1.0:
        t = 1.0
    expected_y = sy + t * (wy - sy)
    if abs(ey - expected_y) < 0.06:
        return elbow
    return _vec((ex, expected_y, elbow[2]))


def _nudge_if_collinear(a, mid, b, y_nudge):
    """If a→mid→b are collinear in the XZ plane, nudge mid in Y by y_nudge.

    AI-derived landmarks from a single ortho view all land at the same Y
    depth (the mesh surface), so shoulder/elbow/wrist and hip/knee/ankle
    are often perfectly collinear. Rigify needs a small bend to compute
    bone rolls; without this it raises 'zero length vectors have no valid
    angle' and crashes during rig generation.
    """
    cross_xz = abs(
        (b.x - a.x) * (mid.z - a.z) - (b.z - a.z) * (mid.x - a.x)
    )
    span = max(abs(b.x - a.x), abs(b.z - a.z), 1e-3)
    if cross_xz < 0.02 * span:
        return _vec((mid.x, mid.y + y_nudge, mid.z))
    return mid


# ---------------------------------------------------------------------------
# Landmark detection (T-pose vertex-extremity hybrid — Task 5)
# ---------------------------------------------------------------------------

def _slice_z(verts, n_slices=50):
    """Bucket world vertices into n_slices evenly-spaced Z bands.
    Returns list of (z_lo, z_hi, list_of_verts_in_band)."""
    if not verts:
        return []
    z_lo = min(v.z for v in verts)
    z_hi = max(v.z for v in verts)
    span = max(z_hi - z_lo, 1e-6)
    step = span / n_slices
    buckets = [[] for _ in range(n_slices)]
    for v in verts:
        idx = min(int((v.z - z_lo) / step), n_slices - 1)
        buckets[idx].append(v)
    return [(z_lo + i*step, z_lo + (i+1)*step, b) for i, b in enumerate(buckets)]


def _x_clusters(verts_in_slice, gap_threshold):
    """Sort slice vertices by X, find gaps wider than gap_threshold,
    return list of clusters (each a list of verts). Used to detect when
    legs are still separate (two clusters) vs merged at the pelvis (one)."""
    if not verts_in_slice:
        return []
    sorted_v = sorted(verts_in_slice, key=lambda v: v.x)
    clusters = [[sorted_v[0]]]
    for v in sorted_v[1:]:
        if v.x - clusters[-1][-1].x > gap_threshold:
            clusters.append([v])
        else:
            clusters[-1].append(v)
    return clusters


def _extreme_vertex(verts, axis, sign):
    """Return the vertex furthest along a signed axis. axis ∈ {0,1,2}."""
    if sign > 0:
        return max(verts, key=lambda v: v[axis])
    return min(verts, key=lambda v: v[axis])


def _bottom_cluster_centroids(verts, bottom_frac=0.03):
    """Return (left_centroid, right_centroid) of the lowest `bottom_frac`
    of vertices, partitioned by X sign. Used for ankle detection."""
    z_threshold = sorted(v.z for v in verts)[max(0, int(len(verts) * bottom_frac) - 1)]
    bottom = [v for v in verts if v.z <= z_threshold]
    left  = [v for v in bottom if v.x >= 0]
    right = [v for v in bottom if v.x <  0]
    if not left or not right:
        return None  # caller falls back
    def centroid(vs):
        n = len(vs)
        return Vector((sum(v.x for v in vs)/n, sum(v.y for v in vs)/n, sum(v.z for v in vs)/n))
    return centroid(left), centroid(right)


def detect_landmarks(meshes, pose=None, reference_height=None):
    """Return a 14-key landmark dict in three.js editor space.

    For T-pose with confidence ≥ 0.75 use a hybrid algorithm: vertex
    extremities for wrists/ankles, AABB defaults for everything else
    (Task 6 adds slicing for chin/shoulders/groin/hips). Other poses
    fall back to AABB ratios via _promote_legacy_landmarks.
    """
    b = aabb(world_vertices(meshes))
    height_blender = max(reference_height or b["size"].z, 1e-3)
    s = THREE_DISPLAY_HEIGHT / height_blender

    def to_three(bv):
        return (bv.x * s, bv.z * s, -bv.y * s)

    mn, mx = b["min"], b["max"]
    body_h = mx.z - mn.z
    width = max(mx.x - mn.x, 1e-3)

    is_t = (pose is not None
            and pose.get("name") == "t_pose"
            and pose.get("confidence", 0.0) >= 0.75)

    # AABB defaults — used directly for non-T-pose / low-confidence inputs,
    # and as the seed for chin / groin (and downstream shoulders / elbows /
    # hips / knees via _promote_legacy_landmarks) on the T-pose path. The
    # T-pose path overrides only `lw`, `rw`, `la`, `ra` from real geometry.
    chin   = Vector((0.0, 0.0, mn.z + 0.92 * body_h))
    groin  = Vector((0.0, 0.0, mn.z + 0.50 * body_h))
    lw     = Vector((mx.x, 0.0, mn.z + 0.82 * body_h))
    rw     = Vector((mn.x, 0.0, mn.z + 0.82 * body_h))
    la     = Vector((+0.10 * width, 0.0, mn.z))
    ra     = Vector((-0.10 * width, 0.0, mn.z))

    if is_t:
        verts = world_vertices(meshes)

        # Wrists: vertex extremities. For non-humanoid silhouettes (paws,
        # accessories) this can land on the fingertip / prop rather than
        # the wrist joint — the editor's /rerig-landmarks/ flow is the
        # workaround.
        lw_v = _extreme_vertex(verts, axis=0, sign=+1)
        rw_v = _extreme_vertex(verts, axis=0, sign=-1)
        lw = Vector((lw_v.x, lw_v.y, lw_v.z))
        rw = Vector((rw_v.x, rw_v.y, rw_v.z))

        # Ankles: bottom-cluster centroids split by X sign.
        ankles = _bottom_cluster_centroids(verts)
        if ankles is not None:
            la, ra = ankles

        # Slice-based chin / groin / shoulders / hips was tried in commit
        # 38c0eba9 but the groin scan ("highest slice with 2+ X-clusters")
        # fires on arm-induced clusters at SHOULDER height in T-pose,
        # placing the pelvis above the chin and inverting the rig. We let
        # _promote_legacy_landmarks fill those in from the AABB defaults
        # below — anatomically sane and consistent with the editor's
        # starting positions.
        log("T-pose detection: wrists & ankles via vertex extremities; "
            "chin/groin/shoulders/hips via AABB defaults")

    elif (pose is not None
          and pose.get("name") == "a_pose"
          and pose.get("confidence", 0.0) >= 0.75):
        verts = world_vertices(meshes)

        # Wrists: A-pose arms hang at ~45° from horizontal. Find the vertex
        # furthest along the arm ray direction (cos θ · x − sin θ · z) where
        # θ is the measured arm angle from horizontal.
        raw_angle = pose.get("angle_deg")
        angle_rad = math.radians(float(raw_angle)) if raw_angle is not None else math.radians(45.0)
        cx = math.cos(angle_rad)
        cz = math.sin(angle_rad)
        lw_v = max(verts, key=lambda v: +(cx * v.x - cz * v.z))
        rw_v = max(verts, key=lambda v: -(cx * v.x - cz * v.z))
        lw = Vector((lw_v.x, lw_v.y, lw_v.z))
        rw = Vector((rw_v.x, rw_v.y, rw_v.z))

        # Ankles: same bottom-cluster approach as T-pose.
        ankles = _bottom_cluster_centroids(verts)
        if ankles is not None:
            la, ra = ankles

        log(f"A-pose detection (angle={math.degrees(angle_rad):.1f}deg): "
            "wrists via ray-extreme, ankles via bottom-cluster; "
            "chin/groin/shoulders/hips via AABB defaults")

    else:
        log("Non-T/A pose or low confidence — landmark detection falls back to AABB defaults")

    six = {"chin": chin, "groin": groin,
           "left_wrist": lw, "right_wrist": rw,
           "left_ankle": la, "right_ankle": ra}
    fourteen_blender = _promote_legacy_landmarks(six)

    # For confirmed T-pose, the wrist landmark from `_extreme_vertex` is
    # the mesh fingertip. Pull it back along wrist→elbow so DEF-hand
    # lands inside the actual hand, mirroring the AI-vision path's fix.
    # Safe to apply unconditionally here because the geometry T-pose
    # branch is the only one that uses _extreme_vertex for wrists.
    if is_t:
        for side in ("left", "right"):
            w_key, e_key = f"{side}_wrist", f"{side}_elbow"
            fourteen_blender[w_key] = _pullback_wrist_toward_elbow(
                fourteen_blender[w_key], fourteen_blender[e_key]
            )

    return {k: to_three(v) for k, v in fourteen_blender.items()}


# ---------------------------------------------------------------------------
# Landmarks (optional — used by /rigs/{id}/rerig-landmarks/)
# ---------------------------------------------------------------------------

def threejs_to_blender(pt, mesh_height):
    """Three.js world-space (Y-up, `THREE_DISPLAY_HEIGHT` tall) → Blender."""
    s = mesh_height / THREE_DISPLAY_HEIGHT
    x, y, z = pt
    return Vector((x * s, -z * s, y * s))


def place_bones_from_landmarks(metarig, landmarks, mesh_height):
    """Position rigify metarig bones from a 14-key landmark dict (or a
    legacy 6-key dict that gets promoted via _promote_legacy_landmarks).

    Three.js-space inputs are converted to Blender world coords first.
    All 14 keys must be present after promotion; KeyError otherwise."""
    log(f"Applying landmarks (mesh_h={mesh_height:.3f}):")
    for k, v in landmarks.items():
        log(f"  three.js {k}: ({v[0]:.3f}, {v[1]:.3f}, {v[2]:.3f})")

    lmk = {k: threejs_to_blender(v, mesh_height) for k, v in landmarks.items()}
    lmk = _promote_legacy_landmarks(lmk)
    for k, v in lmk.items():
        log(f"  blender   {k}: ({v.x:.3f}, {v.y:.3f}, {v.z:.3f})")

    chin, groin = lmk["chin"], lmk["groin"]
    lw, rw = lmk["left_wrist"], lmk["right_wrist"]
    la, ra = lmk["left_ankle"], lmk["right_ankle"]
    ls, rs = lmk["left_shoulder"], lmk["right_shoulder"]
    le, re = lmk["left_elbow"], lmk["right_elbow"]
    lh, rh = lmk["left_hip"], lmk["right_hip"]
    lk, rk = lmk["left_knee"], lmk["right_knee"]

    # AI-derived landmarks all share the same Y depth (mesh surface), which
    # makes limb triples collinear and crashes Rigify bone-roll computation.
    le = _nudge_if_collinear(ls, le, lw, y_nudge= 0.05)
    re = _nudge_if_collinear(rs, re, rw, y_nudge= 0.05)
    lk = _nudge_if_collinear(lh, lk, la, y_nudge=-0.04)
    rk = _nudge_if_collinear(rh, rk, ra, y_nudge=-0.04)

    activate(metarig)
    bpy.ops.object.mode_set(mode="EDIT")
    eb = metarig.data.edit_bones

    # Capture pre-move positions of bones whose descendants should follow
    # them. Bone heads/tails in edit mode are absolute armature-space
    # coords, not parent-relative — so when we move hand.L the finger
    # bones stay at the metarig's default hand position and end up
    # floating disconnected. We delta-shift every descendant of these
    # bones after the moves to keep the hierarchy intact.
    pre_move = {}
    for name in ("hand.L", "hand.R", "foot.L", "foot.R", "toe.L", "toe.R"):
        b = eb.get(name)
        if b:
            pre_move[name] = b.head.copy()

    # Track every bone we manually move so we can restrict the post-step
    # roll recalculation to those. Untouched bones (fingers, face, breast,
    # etc.) keep Rigify's hand-tuned default rolls — recalculating them to
    # global +Z makes finger bones point upward and the hands look broken.
    placed = set()

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
        placed.add(name)

    for side, shoulder, elbow, wrist in (
        ("L", ls, le, lw),
        ("R", rs, re, rw),
    ):
        hand_end = wrist + (wrist - elbow).normalized() * 0.07
        for name, h, t in (
            (f"upper_arm.{side}", shoulder, elbow),
            (f"forearm.{side}",   elbow,    wrist),
            (f"hand.{side}",      wrist,    hand_end),
        ):
            b = eb.get(name)
            if b:
                b.head, b.tail = h, t
                placed.add(name)

    for side, hip, knee, ankle in (
        ("L", lh, lk, la),
        ("R", rh, rk, ra),
    ):
        toe = ankle + Vector((0, -0.09, 0))
        for name, h, t in (
            (f"thigh.{side}", hip,   knee),
            (f"shin.{side}",  knee,  ankle),
            (f"foot.{side}",  ankle, toe),
            (f"toe.{side}",   toe,   toe + Vector((0, -0.04, 0))),
        ):
            b = eb.get(name)
            if b:
                b.head, b.tail = h, t
                placed.add(name)

    # Shift every descendant of the moved hand / foot / toe bones by the
    # same delta their parent moved. Without this finger and toe segments
    # stay at metarig-default coords (the "hands off" / floating fingers
    # symptom). Translation only — preserves each descendant's relative
    # length and roll, so Rigify still generates sensible bones.
    for name, old_head in pre_move.items():
        b = eb.get(name)
        if not b:
            continue
        delta = b.head - old_head
        if delta.length < 1e-6:
            continue
        stack = list(b.children)
        shifted = 0
        while stack:
            child = stack.pop()
            child.head = child.head + delta
            child.tail = child.tail + delta
            shifted += 1
            stack.extend(child.children)
        if shifted:
            log(f"Offset {shifted} descendants of {name} by {delta.length:.3f}m")

    # Recompute rolls only on bones we just moved. After head/tail edits
    # the previous roll values are arbitrary relative to the new bone
    # direction, so Rigify produces twisted limbs. Selecting only `placed`
    # leaves finger / breast / pelvis bones with Rigify's hand-tuned
    # defaults — recalcing them to global +Z is what was making the hands
    # render with bones pointing the wrong way.
    #
    # IMPORTANT: calculate_roll needs head AND tail selection, not just
    # b.select. Without all three flags set, the operator either silently
    # skips or raises depending on Blender version, which kills the
    # subprocess and dumps the pipeline into passthrough.
    for b in eb:
        sel = b.name in placed
        b.select = sel
        b.select_head = sel
        b.select_tail = sel
    if placed:
        try:
            bpy.ops.armature.calculate_roll(type="GLOBAL_POS_Z")
            log(f"Recalculated rolls on {len(placed)} placed bones")
        except Exception as e:
            log(f"calculate_roll skipped: {e}")

    bpy.ops.object.mode_set(mode="OBJECT")
    log("Landmark placement complete")


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


def patch_orphan_vertex_weights(meshes, rig):
    """Heat-diffusion ARMATURE_AUTO fails for bones it can't reach inside
    the mesh volume — they get no vertex weights, and the corresponding
    mesh regions render at origin in three.js (the "two dots moving"
    bug). For every vertex with sum-of-weights ≈ 0, fall back to assigning
    full weight to the nearest deform bone's midpoint. Slow but bounded
    (O(V × B), ~50k×30 ≈ 1.5M ops, runs in a couple of seconds)."""
    bone_targets = []
    for b in rig.data.bones:
        if not b.use_deform:
            continue
        head = rig.matrix_world @ b.head_local
        tail = rig.matrix_world @ b.tail_local
        bone_targets.append((b.name, (head + tail) / 2))
    if not bone_targets:
        return
    deform_names = {name for name, _ in bone_targets}

    patched_total = 0
    for mesh_obj in meshes:
        vg_by_name = {vg.name: vg for vg in mesh_obj.vertex_groups}
        # Pre-resolve the bone names that have a vertex group; create
        # missing ones lazily on first use.
        def vg_for(name):
            vg = vg_by_name.get(name)
            if vg is None:
                vg = mesh_obj.vertex_groups.new(name=name)
                vg_by_name[name] = vg
            return vg

        patched_here = 0
        for v in mesh_obj.data.vertices:
            total = 0.0
            for g in v.groups:
                group = mesh_obj.vertex_groups[g.group]
                if group.name in deform_names:
                    total += g.weight
            if total > 1e-4:
                continue
            world_pos = mesh_obj.matrix_world @ v.co
            nearest = min(bone_targets,
                          key=lambda bt: (bt[1] - world_pos).length_squared)
            vg_for(nearest[0]).add([v.index], 1.0, "REPLACE")
            patched_here += 1
        patched_total += patched_here
        if patched_here:
            log(f"  Patched {patched_here} orphan verts in {mesh_obj.name}")
    log(f"Skinning fallback: patched {patched_total} orphan vertices total")


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
# Ortho rendering (Task 8 — vision round-trip phase 1)
# ---------------------------------------------------------------------------

ORIENTATION_MARKER_PREFIX = "WGT-rigflow_marker_"


def add_orientation_markers(meshes):
    """Add red (character-LEFT, +X) and blue (character-RIGHT, -X) emission
    cubes just outside the body's X extent at chest height. Returns the list
    of created objects so the caller can remove them after rendering.

    The WGT- name prefix matches get_meshes()'s skip rule so the markers never
    leak into landmark detection or skinning even if removal is missed.
    """
    b = aabb(world_vertices(meshes))
    mn, mx = b["min"], b["max"]
    cy = (mn.y + mx.y) / 2
    xsize = mx.x - mn.x
    zsize = mx.z - mn.z
    # Camera frame pads max(xsize,zsize) by 15% (7.5% each side); keep total
    # marker extent under 7.5% of max(xsize,zsize) so it stays in-frame.
    scale = max(xsize, zsize)
    pad = 0.04 * scale
    size = 0.06 * scale
    chest_z = mn.z + 0.75 * zsize

    markers = []
    for suffix, x_pos, color in (
        ("L", mx.x + pad, (1.0, 0.0, 0.0, 1.0)),
        ("R", mn.x - pad, (0.0, 0.0, 1.0, 1.0)),
    ):
        bpy.ops.mesh.primitive_cube_add(size=size, location=(x_pos, cy, chest_z))
        obj = bpy.context.active_object
        obj.name = f"{ORIENTATION_MARKER_PREFIX}{suffix}"
        # Emission material — vivid color independent of scene lighting and
        # filmic tonemap, so it reads as pure red / blue at any sample count.
        mat = bpy.data.materials.new(name=f"{obj.name}_mat")
        mat.use_nodes = True
        nt = mat.node_tree
        nt.nodes.clear()
        out_node = nt.nodes.new("ShaderNodeOutputMaterial")
        emit = nt.nodes.new("ShaderNodeEmission")
        emit.inputs["Color"].default_value = color
        emit.inputs["Strength"].default_value = 5.0
        nt.links.new(emit.outputs["Emission"], out_node.inputs["Surface"])
        obj.data.materials.append(mat)
        markers.append(obj)

    return markers


def remove_orientation_markers(markers):
    """Reverse of add_orientation_markers — also frees orphan mesh + material
    data so repeated render passes don't leak datablocks."""
    for obj in markers:
        mesh_data = obj.data
        mats = [s.material for s in obj.material_slots if s.material]
        bpy.data.objects.remove(obj, do_unlink=True)
        if mesh_data and not mesh_data.users:
            bpy.data.meshes.remove(mesh_data)
        for mat in mats:
            if not mat.users:
                bpy.data.materials.remove(mat)


def render_ortho_views(meshes, out_dir, image_size=512):
    """Render front/back/left/right ortho PNGs; return views dict."""
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    b = aabb(world_vertices(meshes))
    mn, mx = b["min"], b["max"]
    cx = (mn.x + mx.x) / 2
    cy = (mn.y + mx.y) / 2
    cz = (mn.z + mx.z) / 2
    xsize = mx.x - mn.x
    ysize = mx.y - mn.y
    zsize = mx.z - mn.z
    dist = max(xsize, ysize, zsize) * 3 + 1.0

    # Each view sees a different pair of world axes; pad 15% so mesh doesn't
    # touch the image border.
    fb_scale = max(xsize, zsize) * 1.15   # front/back: X × Z plane
    lr_scale = max(ysize, zsize) * 1.15   # left/right: Y × Z plane

    view_specs = {
        "front": (Vector((cx, mn.y - dist, cz)), fb_scale),
        "back":  (Vector((cx, mx.y + dist, cz)), fb_scale),
        "left":  (Vector((mn.x - dist, cy, cz)), lr_scale),
        "right": (Vector((mx.x + dist, cy, cz)), lr_scale),
    }
    target = Vector((cx, cy, cz))

    scene = bpy.context.scene
    # CYCLES is the reliable headless choice — it doesn't need an EGL/GLX
    # context. EEVEE variants are tried as fallbacks when OpenGL is available.
    for eng in ("CYCLES", "BLENDER_EEVEE_NEXT", "BLENDER_EEVEE"):
        try:
            scene.render.engine = eng
            break
        except Exception:
            continue
    if scene.render.engine == "CYCLES":
        scene.cycles.samples = 4       # minimal; enough for landmark detection
        scene.cycles.use_denoising = False
        try:
            scene.cycles.device = "CPU"
        except Exception:
            pass

    scene.render.resolution_x = image_size
    scene.render.resolution_y = image_size
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"

    if not any(o.type == "LIGHT" for o in bpy.data.objects):
        sun_data = bpy.data.lights.new("sun", "SUN")
        sun_data.energy = 3.0
        sun_obj = bpy.data.objects.new("sun", sun_data)
        scene.collection.objects.link(sun_obj)
        sun_obj.location = Vector((cx, cy, cz + dist))

    views = {}
    for name, (loc, scale) in view_specs.items():
        cam_data = bpy.data.cameras.new(f"cam_{name}")
        cam_data.type = "ORTHO"
        cam_data.ortho_scale = max(scale, 0.01)
        cam_obj = bpy.data.objects.new(f"cam_{name}", cam_data)
        scene.collection.objects.link(cam_obj)

        cam_obj.location = loc
        rot_quat = (target - loc).to_track_quat("-Z", "Z")
        cam_obj.rotation_euler = rot_quat.to_euler()

        # Markers only in front/back — side views see a profile where the
        # markers overlap on the camera axis and add no information.
        markers = add_orientation_markers(meshes) if name in ("front", "back") else []
        try:
            scene.camera = cam_obj
            png_path = str(out_path / f"{name}.png")
            scene.render.filepath = png_path
            bpy.ops.render.render(write_still=True)
        finally:
            remove_orientation_markers(markers)

        views[name] = {
            "path": png_path,
            "image_size": [image_size, image_size],
            "ortho_scale": cam_data.ortho_scale,
            "camera_world_pos": [loc.x, loc.y, loc.z],
            "look_at": [target.x, target.y, target.z],
            "has_orientation_markers": name in ("front", "back"),
        }
        log(f"Rendered {name} → {png_path}")

        bpy.data.objects.remove(cam_obj, do_unlink=True)
        bpy.data.cameras.remove(cam_data)

    return views


# ---------------------------------------------------------------------------
# Prop parenting (Task 14)
# ---------------------------------------------------------------------------

_PROP_BONE_MAP = {
    "hat":                  "DEF-spine.005",   # head
    "accessory_held_left":  "DEF-hand.L",
    "accessory_held_right": "DEF-hand.R",
    # clothing stays with auto-weights; other = no-op
}


def parent_props_to_bones(meshes, mesh_object_labels, armature):
    """Pin non-body prop meshes rigidly to a single DEF bone.

    Instead of BONE parenting (which confuses the GLB skin exporter when
    used alongside skinned meshes), we keep the Armature modifier that
    bind_auto_weights added and simply replace all vertex group weights
    with a uniform 1.0 to the target bone.  The result is a rigid prop
    that follows the bone without distortion, fully compatible with the
    GLB skin pipeline.
    """
    for m in meshes:
        label = mesh_object_labels.get(m.name)
        bone_name = _PROP_BONE_MAP.get(label)
        if not bone_name:
            continue
        if bone_name not in armature.data.bones:
            log(f"Prop {m.name} ({label}): bone {bone_name!r} not found; skipping")
            continue
        # Clear all existing vertex groups, add a single group for the
        # target bone, and assign every vertex to it with weight=1.
        m.vertex_groups.clear()
        vg = m.vertex_groups.new(name=bone_name)
        vg.add(list(range(len(m.data.vertices))), 1.0, "REPLACE")
        # Ensure an Armature modifier pointing at the rig exists.
        arm_mod = next((mod for mod in m.modifiers if mod.type == "ARMATURE"), None)
        if arm_mod is None:
            arm_mod = m.modifiers.new(name="Armature", type="ARMATURE")
        arm_mod.object = armature
        log(f"Pinned {m.name} ({label}) → {bone_name}")


# ---------------------------------------------------------------------------
# Pixel → world raycast (Task 12)
# ---------------------------------------------------------------------------

def pixel_to_world_ray(view_name, px, py, image_size, ortho_scale, world_aabb):
    """Return (origin, direction) in world space for a pixel in an ortho view.

    Coordinate convention matches render_ortho_views cameras (to_track_quat
    with up=+Z):
      front/back cameras: +X = world +X or -X; +Y = world +Z
      left/right cameras: +X = world -Y or +Y; +Y = world +Z

    view_name ∈ {"front","back","left","right"}
    px, py    pixel coords, top-left origin, in [0, image_size)
    """
    (mn, mx) = world_aabb
    cx = (mn[0] + mx[0]) / 2
    cy = (mn[1] + mx[1]) / 2
    cz = (mn[2] + mx[2]) / 2
    # Normalise pixel to camera-plane offset in world units.
    u = (px / image_size - 0.5) * ortho_scale   # horizontal (+u = image right)
    v = (0.5 - py / image_size) * ortho_scale   # vertical   (+v = image top)

    if view_name == "front":
        # Camera at (cx, mn.y−dist, cz) looking toward +Y.
        # Camera +X = world +X, camera +Y = world +Z.
        origin    = Vector((cx + u, mn[1] - ortho_scale / 2, cz + v))
        direction = Vector((0.0, 1.0, 0.0))

    elif view_name == "back":
        # Camera at (cx, mx.y+dist, cz) looking toward -Y.
        # Camera +X = world -X (mirrored), camera +Y = world +Z.
        origin    = Vector((cx - u, mx[1] + ortho_scale / 2, cz + v))
        direction = Vector((0.0, -1.0, 0.0))

    elif view_name == "left":
        # Camera at (mn.x−dist, cy, cz) looking toward +X.
        # Camera +X = world -Y, camera +Y = world +Z.
        origin    = Vector((mn[0] - ortho_scale / 2, cy - u, cz + v))
        direction = Vector((1.0, 0.0, 0.0))

    elif view_name == "right":
        # Camera at (mx.x+dist, cy, cz) looking toward -X.
        # Camera +X = world +Y, camera +Y = world +Z.
        origin    = Vector((mx[0] + ortho_scale / 2, cy + u, cz + v))
        direction = Vector((-1.0, 0.0, 0.0))

    else:
        raise ValueError(f"unknown view {view_name!r}")

    return origin, direction


def _bvh_tree_for(mesh):
    from mathutils.bvhtree import BVHTree
    depsgraph = bpy.context.evaluated_depsgraph_get()
    return BVHTree.FromObject(mesh, depsgraph)


def build_view_ortho_scales(ai_response, fallback):
    """Return the ortho_scale to use for each camera view.

    Phase 1 (render_ortho_views) renders front/back with one ortho_scale and
    left/right with another — the image planes span different world-axis
    pairs. tasks.py forwards those per-view scales into ai_response.json under
    the "views" key. Using a single recomputed scale for every view
    mis-projects side-view pixels for meshes whose Y extent differs from their
    X extent.

    `fallback` is used for any view whose scale is missing or unparseable.
    """
    views = (ai_response or {}).get("views") or {}
    scales = {}
    for name in ("front", "back", "left", "right"):
        view = views.get(name) or {}
        raw = view.get("ortho_scale")
        try:
            scales[name] = float(raw) if raw is not None else float(fallback)
        except (TypeError, ValueError):
            scales[name] = float(fallback)
    return scales


def ai_pixels_to_world_seeds(ai_response, image_size, view_ortho_scales, world_aabb, meshes):
    """For each of the 14 landmark keys, triangulate front + side pixel coords
    into a 3D world-space seed via BVH raycasting.

    front view provides x and z; side view provides y.
    """
    bvh_trees = [(m, _bvh_tree_for(m)) for m in meshes]

    def raycast(origin, direction):
        best = None
        for m, tree in bvh_trees:
            loc, _, _, dist = tree.ray_cast(origin, direction)
            if loc is not None and (best is None or dist < best[1]):
                best = (loc, dist)
        return best[0] if best else None

    seeds = {}
    for key in LANDMARK_KEYS:
        front_px = (ai_response["landmarks"].get("front") or {}).get(key)
        if front_px is None:
            continue

        fo, fd = pixel_to_world_ray("front", front_px[0], front_px[1],
                                    image_size, view_ortho_scales["front"], world_aabb)
        hit_f = raycast(fo, fd)
        if hit_f is None:
            # Fallback: mid-plane hit estimate.
            mn, mx = world_aabb
            t = ((mn[1] + mx[1]) / 2 - fo.y) / (fd.y or 1e-6)
            hit_f = Vector((fo.x + fd.x * t, fo.y + fd.y * t, fo.z + fd.z * t))

        # Try left view first for the Y coordinate; fall back to right.
        side_name = None
        side_px = None
        for vn in ("left", "right"):
            sp = (ai_response["landmarks"].get(vn) or {}).get(key)
            if sp is not None:
                side_name, side_px = vn, sp
                break

        if side_px is not None:
            so, sd = pixel_to_world_ray(side_name, side_px[0], side_px[1],
                                        image_size, view_ortho_scales[side_name], world_aabb)
            hit_s = raycast(so, sd) or hit_f
            # Merge: front gives x,z; side gives y; average z for stability.
            seed = Vector((hit_f.x, hit_s.y, (hit_f.z + hit_s.z) / 2))
        else:
            seed = hit_f

        seeds[key] = seed

    return seeds


def refine_seeds(seeds, meshes):
    """Walk AI seeds to the nearest anatomically-plausible mesh vertex."""
    refined = dict(seeds)
    verts = world_vertices(meshes)

    for key in ("left_wrist", "right_wrist"):
        if key not in seeds:
            continue
        seed = seeds[key]
        candidates = [v for v in verts
                      if abs(v.z - seed.z) < 0.12 and (v - seed).length < 0.22]
        if candidates:
            refined[key] = min(candidates, key=lambda v: (v - seed).length)

    for key in ("left_ankle", "right_ankle"):
        if key not in seeds:
            continue
        sign = +1 if key.startswith("left") else -1
        bottom = sorted(verts, key=lambda v: v.z)[: max(50, len(verts) // 100)]
        side_bottom = [v for v in bottom if (v.x * sign) > 0]
        if side_bottom:
            n = len(side_bottom)
            cx = sum(v.x for v in side_bottom) / n
            cy2 = sum(v.y for v in side_bottom) / n
            cz2 = sum(v.z for v in side_bottom) / n
            refined[key] = Vector((cx, cy2, cz2))

    return refined


def normalize_bilateral_landmark_sides(landmarks):
    """Ensure RigFlow's landmark convention: character-left is +X.

    Vision models can interpret "left" from the viewer's perspective on
    front renders, or mix conventions across body parts. The rigging code
    expects every left/right pair to be mirrored as left.x > right.x.
    """
    normalized = dict(landmarks)
    for left_key, right_key, _ in (
        ("left_shoulder", "right_shoulder", "shoulder"),
        ("left_elbow", "right_elbow", "elbow"),
        ("left_wrist", "right_wrist", "wrist"),
        ("left_hip", "right_hip", "hip"),
        ("left_knee", "right_knee", "knee"),
        ("left_ankle", "right_ankle", "ankle"),
    ):
        left = normalized.get(left_key)
        right = normalized.get(right_key)
        if left is None or right is None:
            continue
        if left[0] < right[0]:
            normalized[left_key], normalized[right_key] = right, left
            log(f"Normalized AI landmark side labels: swapped {left_key}/{right_key}")
    return normalized


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    args = parse_args()
    log(f"Input:  {args.input}")
    log(f"Output: {args.output}")

    clear_scene()
    import_model(args.input, args.format)
    strip_non_meshes()
    purge_missing_image_refs()

    meshes = get_meshes()
    if not meshes:
        raise RuntimeError("No meshes found after import")
    log(f"Mesh count: {len(meshes)}")

    apply_user_rotation(
        meshes,
        user_rotation_x=args.initial_rotation_x,
        user_rotation_y=args.initial_rotation_y,
        user_rotation_z=args.initial_rotation_z,
        user_rotation_quat=(
            args.initial_rotation_qx,
            args.initial_rotation_qy,
            args.initial_rotation_qz,
            args.initial_rotation_qw,
        ) if abs(args.initial_rotation_qw) > 1e-6 or any(
            abs(v) > 1e-6
            for v in (
                args.initial_rotation_qx,
                args.initial_rotation_qy,
                args.initial_rotation_qz,
            )
        ) else None,
    )

    metarig = create_metarig()
    remove_face_bones(metarig)

    scale_mesh_to_metarig(meshes, metarig)

    # Ortho-render early-exit: phase 1 of the vision round-trip. Renders 4
    # PNGs, writes ai_request.json, then exits — Django calls the vision
    # provider and re-invokes Blender with --landmarks-from-ai for phase 2.
    if args.render_ortho_views:
        if not args.ai_request_out:
            log("ERROR: --render-ortho-views requires --ai-request-out")
            sys.exit(1)
        render_dir = args.ortho_render_dir or str(Path(args.ai_request_out).parent)
        views = render_ortho_views(meshes, render_dir)
        b_all = aabb(world_vertices(meshes))
        mn_all, mx_all = b_all["min"], b_all["max"]
        ai_request = {
            "rig_id": Path(args.input).stem,
            "views": views,
            "mesh_objects": [
                {
                    "name": m.name,
                    "vertex_count": len(m.data.vertices),
                    "bbox_world": _bbox_world(m),
                }
                for m in meshes
            ],
            "world_aabb": [
                [mn_all.x, mn_all.y, mn_all.z],
                [mx_all.x, mx_all.y, mx_all.z],
            ],
        }
        Path(args.ai_request_out).write_text(json.dumps(ai_request, indent=2))
        log(f"Wrote AI request JSON → {args.ai_request_out}")
        log("Phase 1 complete — exiting for vision provider call.")
        sys.exit(0)

    # Pose classification — runs after scaling so the chest/shoulder bands
    # are at predictable Z fractions of body height. Result is logged and
    # written to the --pose sidecar JSON for tasks.py to read.
    pose_info = detect_pose(meshes)
    log(
        f"Pose: {pose_info['classification']} "
        f"(angle={pose_info['angle_deg']!r}, "
        f"confidence={pose_info['confidence']:.2f})"
    )
    if pose_info.get("reason"):
        log(f"  Reason: {pose_info['reason']}")
    if args.pose:
        try:
            Path(args.pose).write_text(json.dumps(pose_info, indent=2))
        except Exception as e:
            log(f"  Failed to write pose JSON: {e}")

    # Build a pose dict in the shape detect_landmarks expects:
    # {"name": <classification>, "confidence": <float 0-1>}.
    # detect_pose returns confidence already on [0, 1].
    detected_pose = {
        "name":       pose_info["classification"],
        "confidence": pose_info["confidence"],
        "angle_deg":  pose_info.get("angle_deg"),  # arm tilt from horizontal; used by A-pose detector
    }

    # Use the metarig's height as the canonical reference instead of
    # recomputing the mesh AABB. scale_mesh_to_metarig already aligned
    # the body to this; reading the live mesh AABB here picks up stray
    # imported geometry (decorative spheres, props) that inflate the
    # bounding box and double the landmark conversion scale, which puts
    # the metarig bones at 2× their correct height.
    mesh_h = armature_aabb(metarig)["size"].z
    log(f"Landmark conversion using metarig height: {mesh_h:.3f}m")

    if args.landmarks_out:
        detected = detect_landmarks(meshes, pose=detected_pose, reference_height=mesh_h)
        Path(args.landmarks_out).write_text(json.dumps(detected, indent=2))
        log(f"Wrote {len(detected)} detected landmarks → {args.landmarks_out}")

    # Capture labels for prop parenting when --landmarks-from-ai is used.
    mesh_object_labels: dict = {}

    if args.landmarks:
        user_landmarks = json.loads(args.landmarks)
        log(f"Mode: LANDMARK (user-supplied {len(user_landmarks)} keys)")
        place_bones_from_landmarks(metarig, user_landmarks, mesh_h)
    elif args.landmarks_from_ai:
        # Phase 2 of the vision round-trip: pixel coords → 3D seeds → refine.
        ai_response = json.loads(Path(args.landmarks_from_ai).read_text())
        mesh_object_labels = ai_response.get("mesh_objects", {})
        log(f"Mode: AI (reading {args.landmarks_from_ai})")

        b_cur = aabb(world_vertices(meshes))
        mn_cur, mx_cur = b_cur["min"], b_cur["max"]
        xsize = mx_cur.x - mn_cur.x
        zsize = mx_cur.z - mn_cur.z
        os_approx = max(xsize, zsize) * 1.15
        view_ortho_scales = build_view_ortho_scales(ai_response, os_approx)
        world_aabb_t = (
            (mn_cur.x, mn_cur.y, mn_cur.z),
            (mx_cur.x, mx_cur.y, mx_cur.z),
        )

        try:
            seeds = ai_pixels_to_world_seeds(
                ai_response, 512, view_ortho_scales, world_aabb_t, meshes
            )
            seeds = refine_seeds(seeds, meshes)
            log(f"AI seeds resolved: {len(seeds)} of {len(LANDMARK_KEYS)} landmarks")
        except Exception as e:
            log(f"Raycast failed ({e}); falling back to geometry-only landmarks")
            seeds = {}

        # Geometry fallback for any key the AI didn't supply.
        geo_landmarks = detect_landmarks(meshes, pose=detected_pose, reference_height=mesh_h)

        def to_three_from_blender(bv):
            s = 2.0 / mesh_h
            return (bv.x * s, bv.z * s, -bv.y * s)

        final_landmarks = {}
        for k in LANDMARK_KEYS:
            if k in seeds:
                final_landmarks[k] = to_three_from_blender(seeds[k])
            else:
                final_landmarks[k] = geo_landmarks[k]
        final_landmarks = normalize_bilateral_landmark_sides(final_landmarks)

        if detected_pose["name"] == "t_pose" and detected_pose["confidence"] >= 0.75:
            for k in ("left_wrist", "right_wrist"):
                final_landmarks[k] = geo_landmarks[k]
            log("T-pose AI refine: using geometry extremities for wrists")

            # The geometry extremity is the fingertip on humanoid meshes,
            # not the wrist joint — pull wrist back along wrist→elbow so
            # DEF-hand lands inside the actual hand. Then clamp the AI's
            # elbow Y onto the shoulder/wrist line, since vision models
            # sometimes drop the elbow ~15-20cm and break retargeting.
            for side in ("left", "right"):
                w = final_landmarks[f"{side}_wrist"]
                e = final_landmarks[f"{side}_elbow"]
                s = final_landmarks[f"{side}_shoulder"]
                final_landmarks[f"{side}_wrist"] = _pullback_wrist_toward_elbow(w, e)
                final_landmarks[f"{side}_elbow"] = _clamp_elbow_y_to_arm_line(
                    s, e, final_landmarks[f"{side}_wrist"]
                )
            log("T-pose AI refine: pulled wrists toward elbows, "
                "clamped elbow Y onto shoulder/wrist line")

        if args.landmarks_out:
            # final_landmarks may hold mathutils.Vector values after the
            # T-pose refine block (the refine helpers return _vec()); coerce
            # every value to a plain float list so json.dumps can serialise it.
            serializable = {
                k: [float(c) for c in v] for k, v in final_landmarks.items()
            }
            Path(args.landmarks_out).write_text(json.dumps(serializable, indent=2))
            log(f"Wrote {len(final_landmarks)} AI+refined landmarks → {args.landmarks_out}")

        place_bones_from_landmarks(metarig, final_landmarks, mesh_h)
    else:
        auto_landmarks = detect_landmarks(meshes, pose=detected_pose, reference_height=mesh_h)
        log(f"Mode: AUTO (detected {len(auto_landmarks)} landmarks)")
        place_bones_from_landmarks(metarig, auto_landmarks, mesh_h)

    rig = generate_rig(metarig)

    # Bind with the FULL Rigify rig — heat-diffusion auto-weights need the
    # complete bone graph to produce smooth weights.
    bind_auto_weights(meshes, rig)

    try:
        patch_orphan_vertex_weights(meshes, rig)
    except Exception as e:
        log(f"Skinning fallback failed (non-fatal): {e}")
        import traceback
        log(traceback.format_exc())

    strip_to_deform_bones(rig)

    # Prop parenting: non-body meshes get parented to semantically-correct
    # DEF bones when the AI supplied mesh_object_labels.
    if mesh_object_labels:
        parent_props_to_bones(meshes, mesh_object_labels, rig)

    # Metarig stays in the scene but isn't selected; export uses use_selection.
    export_glb(meshes, rig, args.output)

    bone_map = build_bone_map(rig)
    Path(args.bones).write_text(json.dumps(bone_map, indent=2))

    log(f"SUCCESS — {len(bone_map)} bones mapped")
#testing branches


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"[RigFlow] FATAL: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
