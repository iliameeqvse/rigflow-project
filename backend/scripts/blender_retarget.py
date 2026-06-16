"""Server-side animation retarget + bake. Runs inside Blender:

    blender --background --python blender_retarget.py -- --rig <glb> \
        --clips <json> --output <glb> --bone-map <json> --report-out <json>

Loads the rigged GLB and each animation clip, transfers each source bone's
motion as a DELTA FROM ITS OWN REST onto the target bone's rest (rest-pose
correct — this is what the browser retarget gets wrong), bakes keyframes, and
exports a GLB with animations.
"""
import argparse
import json
import sys
from pathlib import Path

import bpy
from mathutils import Matrix  # noqa: F401  (used by the bake in Task 2)

# Reuse the canonical-name resolver from the autorig script.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from blender_autorig import canonical_mixamo_name  # noqa: E402


def log(msg):
    print(f"[RigFlow-Retarget] {msg}")


def pair_bones_by_mixamo(bone_mapping, source_bone_names):
    """Return a list of (target_bone_name, source_bone_name) pairs.

    bone_mapping is {MixamoName: targetBoneName} (the rig's saved map). Each
    source bone is resolved to a canonical Mixamo name; when that Mixamo name
    is in bone_mapping, the source pairs to that target bone. First source per
    Mixamo name wins; targets with no matching source are skipped."""
    src_by_mixamo = {}
    for s in source_bone_names:
        mx = canonical_mixamo_name(s)
        if mx and mx not in src_by_mixamo:
            src_by_mixamo[mx] = s
    pairs = []
    for mixamo, target_bone in bone_mapping.items():
        src = src_by_mixamo.get(mixamo)
        if src:
            pairs.append((target_bone, src))
    return pairs


def _argv_after_dashes():
    return sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--rig", required=True)
    p.add_argument("--clips", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--bone-map", required=True)
    p.add_argument("--report-out", default=None)
    return p.parse_args(_argv_after_dashes())


def _clear_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def _import_any(path, fmt):
    fmt = (fmt or path.split(".")[-1]).lower()
    before = set(bpy.data.objects)
    if fmt == "fbx":
        bpy.ops.import_scene.fbx(filepath=path)
    elif fmt in ("glb", "gltf"):
        bpy.ops.import_scene.gltf(filepath=path)
    else:
        raise ValueError(f"Unsupported format: {fmt}")
    return [o for o in bpy.data.objects if o not in before]


def _first_armature(objs):
    for o in objs:
        if o.type == "ARMATURE":
            return o
    return None


def retarget_clip_onto(target_arm, source_arm, pairs, action):
    """Bake `action` (on source_arm) onto target_arm using a per-bone rest
    rebasing. For each source bone we take its LOCAL pose delta-from-rest
    (matrix_basis) and conjugate it by R = tgt_rest_worldrot^-1 @ src_rest_worldrot
    so the same motion is expressed in the target bone's local frame, then set
    the target's rotation_quaternion (hierarchy-safe — translation untouched).
    Rotation only (root motion is a later milestone). Returns bones driven.
    """
    scene = bpy.context.scene
    if not source_arm.animation_data:
        source_arm.animation_data_create()
    source_arm.animation_data.action = action
    f0, f1 = int(action.frame_range[0]), int(action.frame_range[1])

    rebase = {}
    for t, s in pairs:
        if t in target_arm.data.bones and s in source_arm.data.bones:
            tgt_rw = (target_arm.matrix_world @ target_arm.data.bones[t].matrix_local).to_3x3()
            src_rw = (source_arm.matrix_world @ source_arm.data.bones[s].matrix_local).to_3x3()
            rebase[(t, s)] = tgt_rw.inverted() @ src_rw
    valid = [(t, s) for (t, s) in pairs if (t, s) in rebase]

    bpy.context.view_layer.objects.active = target_arm
    bpy.ops.object.mode_set(mode="POSE")
    for tpb in target_arm.pose.bones:
        tpb.rotation_mode = "QUATERNION"

    for frame in range(f0, f1 + 1):
        scene.frame_set(frame)
        for t, s in valid:
            src_delta = source_arm.pose.bones[s].matrix_basis.to_3x3()
            R = rebase[(t, s)]
            tgt_delta = R @ src_delta @ R.inverted()
            tpb = target_arm.pose.bones[t]
            tpb.rotation_quaternion = tgt_delta.to_quaternion()
            tpb.keyframe_insert("rotation_quaternion", frame=frame)

    bpy.ops.object.mode_set(mode="OBJECT")
    return len(valid)


def main():
    args = parse_args()
    bone_mapping = json.loads(Path(args.bone_map).read_text())
    clips = json.loads(Path(args.clips).read_text())

    _clear_scene()
    rig_objs = _import_any(args.rig, "glb")
    target_arm = _first_armature(rig_objs)
    if target_arm is None:
        raise RuntimeError("No armature in rig GLB")

    report = {"format": "glb", "clips": [], "warnings": []}
    nla_tracks = []
    for clip in clips:
        src_objs = _import_any(clip["path"], clip.get("format"))
        source_arm = _first_armature(src_objs)
        if (source_arm is None or not source_arm.animation_data
                or not source_arm.animation_data.action):
            report["warnings"].append(f"clip {clip['name']}: no armature/action")
            for o in src_objs:
                bpy.data.objects.remove(o, do_unlink=True)
            continue
        action = source_arm.animation_data.action
        src_names = [b.name for b in source_arm.data.bones]
        pairs = pair_bones_by_mixamo(bone_mapping, src_names)
        driven = retarget_clip_onto(target_arm, source_arm, pairs, action)

        baked = target_arm.animation_data.action
        baked.name = clip["name"]
        # Push to an NLA track so multiple clips survive as separate animations.
        track = target_arm.animation_data.nla_tracks.new()
        track.name = clip["name"]
        track.strips.new(clip["name"], int(baked.frame_range[0]), baked)
        target_arm.animation_data.action = None
        nla_tracks.append(baked)

        report["clips"].append({
            "id": clip.get("id"), "name": clip["name"],
            "bones_driven": driven, "bones_total": len(src_names),
            "frame_range": [int(action.frame_range[0]), int(action.frame_range[1])],
        })
        log(f"Baked '{clip['name']}': {driven}/{len(src_names)} bones")
        for o in src_objs:
            bpy.data.objects.remove(o, do_unlink=True)

    if not report["clips"]:
        raise RuntimeError("No clips produced a bake")

    bpy.ops.object.select_all(action="DESELECT")
    for o in bpy.data.objects:
        o.select_set(True)
    bpy.context.view_layer.objects.active = target_arm
    bpy.ops.export_scene.gltf(
        filepath=args.output, export_format="GLB",
        export_animations=True, export_skins=True,
        use_selection=True, export_apply=False, export_yup=True,
    )
    log(f"Exported animated GLB → {args.output}")
    if args.report_out:
        Path(args.report_out).write_text(json.dumps(report, indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"[RigFlow-Retarget] FATAL: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
