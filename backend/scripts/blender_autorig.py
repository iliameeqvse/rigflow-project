"""
Blender headless auto-rig script.

How it works:
1. Imports your 3D model (FBX/GLB/OBJ)
2. Analyses the mesh proportions to estimate where bones should go
3. Creates a Rigify metarig (template armature) scaled to fit your model
4. Generates a full production rig from the metarig
5. Binds the mesh to the rig using automatic weight painting
6. Exports the result as GLB
7. Writes a bone name mapping JSON (Rigify → Mixamo naming)

Run: blender --background --python blender_autorig.py -- \
     --input mesh.fbx --output rigged.glb --bones bones.json --format fbx
"""

import bpy
import sys
import json
import argparse
from pathlib import Path
from mathutils import Vector


# ── Parse arguments passed after the "--" separator ──────────────────────────
argv = sys.argv
if "--" in argv:
    argv = argv[argv.index("--") + 1:]
else:
    argv = []

parser = argparse.ArgumentParser(description="RigFlow auto-rig script")
parser.add_argument("--input",  required=True, help="Path to input model file")
parser.add_argument("--output", required=True, help="Path for output GLB file")
parser.add_argument("--bones",  required=True, help="Path to write bone mapping JSON")
parser.add_argument("--format", default="fbx",  help="Input file format")
args = parser.parse_args(argv)


def clear_scene():
    """Remove everything in the default Blender scene."""
    bpy.ops.wm.read_factory_settings(use_empty=True)
    if bpy.context.active_object:
        bpy.ops.object.mode_set(mode="OBJECT")
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=True)


def import_model(filepath: str, fmt: str):
    """Import the user's 3D model based on file format."""
    fmt = fmt.lower()
    print(f"[RigFlow] Importing {fmt} file: {filepath}")
    if fmt == "fbx":
        bpy.ops.import_scene.fbx(filepath=filepath)
    elif fmt in ("glb", "gltf"):
        bpy.ops.import_scene.gltf(filepath=filepath)
    elif fmt == "obj":
        bpy.ops.wm.obj_import(filepath=filepath)
    else:
        raise ValueError(f"Unsupported format: {fmt}. Use fbx, glb, or obj.")


def get_mesh_objects():
    """Return all mesh objects in the scene."""
    return [o for o in bpy.data.objects if o.type == "MESH"]


def detect_body_proportions(meshes: list) -> dict:
    """
    Analyse the mesh bounding box to estimate body proportions.
    This is used to scale and position the Rigify metarig bones
    to roughly match the character's actual dimensions.
    """
    all_world_verts = []
    for obj in meshes:
        for vertex in obj.data.vertices:
            # Convert from local object space to world space
            world_pos = obj.matrix_world @ vertex.co
            all_world_verts.append(world_pos)

    if not all_world_verts:
        raise RuntimeError("No vertices found in mesh — is the model empty?")

    xs = [v.x for v in all_world_verts]
    ys = [v.y for v in all_world_verts]
    zs = [v.z for v in all_world_verts]

    height = max(zs) - min(zs)
    width  = max(xs) - min(xs)
    depth  = max(ys) - min(ys)
    floor  = min(zs)

    # Estimate bone heights as proportions of total height
    # These ratios work for most humanoid characters
    props = {
        "height":     height,
        "width":      width,
        "depth":      depth,
        "floor_z":    floor,
        "top_z":      max(zs),
        "hip_z":      floor + height * 0.52,    # hips are ~52% up
        "chest_z":    floor + height * 0.70,    # chest ~70%
        "neck_z":     floor + height * 0.86,    # neck ~86%
        "head_z":     floor + height * 0.92,    # head centre ~92%
        "shoulder_w": width  * 0.35,            # shoulder width
        "arm_len":    height * 0.30,            # arm length estimate
        "leg_len":    height * 0.48,            # leg length estimate
    }

    print(f"[RigFlow] Detected: height={height:.3f}m, width={width:.3f}m")
    print(f"[RigFlow] Hip z={props['hip_z']:.3f}, Head z={props['head_z']:.3f}")
    return props


def create_metarig_and_fit(props: dict):
    """
    Add Rigify's human metarig template and scale it to match
    the character's detected body proportions.
    """
    # This adds the standard human metarig at origin
    bpy.ops.object.armature_human_metarig_add()
    metarig = bpy.context.active_object

    # Scale uniformly to match the character height
    # Rigify's default metarig is 2m tall, we scale to match
    scale_factor = props["height"] / 2.0
    metarig.scale = (scale_factor, scale_factor, scale_factor)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)

    # Move metarig to sit on the floor (z=floor)
    metarig.location.z = props["floor_z"]
    bpy.ops.object.transform_apply(location=True, rotation=False, scale=False)

    return metarig


def generate_full_rig(metarig):
    """
    Convert the metarig template into a full production rig.
    This is Rigify's core operation — it generates all the deform
    bones, control bones, and IK/FK chains.
    """
    bpy.context.view_layer.objects.active = metarig
    bpy.ops.pose.rigify_generate()

    # After generation, the new rig is the active object
    generated_rig = bpy.context.active_object
    print(f"[RigFlow] Generated rig: {generated_rig.name}")
    return generated_rig


def bind_mesh_to_rig(meshes: list, rig):
    """
    Parent all mesh objects to the rig and apply automatic weight painting.
    This is what makes the mesh deform when bones move.
    """
    # Deselect everything
    bpy.ops.object.select_all(action="DESELECT")

    # Select all mesh objects
    for obj in meshes:
        obj.select_set(True)

    # Make the rig the active (parent) object
    bpy.context.view_layer.objects.active = rig

    # ARMATURE_AUTO = Blender calculates weights based on proximity to bones
    bpy.ops.object.parent_set(type="ARMATURE_AUTO")
    print(f"[RigFlow] Bound {len(meshes)} mesh objects to rig with auto weights")


# Mapping from Rigify internal bone names → Mixamo-compatible names
# Mixamo is the industry standard so this makes the rig compatible
# with Mixamo's animation library and most game engines
RIGIFY_TO_MIXAMO = {
    "spine":         "Hips",
    "spine.001":     "Spine",
    "spine.002":     "Spine1",
    "spine.003":     "Spine2",
    "spine.004":     "Neck",
    "spine.005":     "Head",
    "thigh.L":       "LeftUpLeg",
    "shin.L":        "LeftLeg",
    "foot.L":        "LeftFoot",
    "toe.L":         "LeftToeBase",
    "thigh.R":       "RightUpLeg",
    "shin.R":        "RightLeg",
    "foot.R":        "RightFoot",
    "toe.R":         "RightToeBase",
    "shoulder.L":    "LeftShoulder",
    "upper_arm.L":   "LeftArm",
    "forearm.L":     "LeftForeArm",
    "hand.L":        "LeftHand",
    "shoulder.R":    "RightShoulder",
    "upper_arm.R":   "RightArm",
    "forearm.R":     "RightForeArm",
    "hand.R":        "RightHand",
    "thumb.01.L":    "LeftHandThumb1",
    "f_index.01.L":  "LeftHandIndex1",
    "f_middle.01.L": "LeftHandMiddle1",
    "f_ring.01.L":   "LeftHandRing1",
    "f_pinky.01.L":  "LeftHandPinky1",
    "thumb.01.R":    "RightHandThumb1",
    "f_index.01.R":  "RightHandIndex1",
    "f_middle.01.R": "RightHandMiddle1",
    "f_ring.01.R":   "RightHandRing1",
    "f_pinky.01.R":  "RightHandPinky1",
}


def build_bone_mapping(rig) -> dict:
    """
    Create a dictionary mapping Mixamo bone names → Rigify bone names.
    This is stored in the Django database and used during retargeting
    to map incoming animation bone poses to the correct rig bones.
    """
    mapping = {}
    for bone in rig.data.bones:
        mixamo_name = RIGIFY_TO_MIXAMO.get(bone.name)
        if mixamo_name:
            mapping[mixamo_name] = bone.name

    print(f"[RigFlow] Mapped {len(mapping)} bones to Mixamo names")
    return mapping


def export_as_glb(output_path: str, rig, meshes: list):
    """Export the rigged model as a GLB file (binary GLTF)."""
    bpy.ops.object.select_all(action="DESELECT")
    rig.select_set(True)
    for m in meshes:
        m.select_set(True)

    bpy.ops.export_scene.gltf(
        filepath=output_path,
        export_format="GLB",
        export_animations=True,   # include any baked animations
        export_skins=True,        # include armature/skin data
        use_selection=True,       # only export selected objects
        export_apply=True,        # apply modifiers before export
    )
    print(f"[RigFlow] Exported GLB: {output_path}")


# ── MAIN ──────────────────────────────────────────────────────────────────────
print("=" * 60)
print("[RigFlow] Auto-rig starting...")
print(f"[RigFlow] Input:  {args.input}")
print(f"[RigFlow] Output: {args.output}")
print("=" * 60)

clear_scene()
import_model(args.input, args.format)

meshes = get_mesh_objects()
if not meshes:
    raise RuntimeError(
        "No mesh objects found after importing. "
        "Is the file valid? Does it contain visible geometry?"
    )
print(f"[RigFlow] Found {len(meshes)} mesh object(s)")

props    = detect_body_proportions(meshes)
metarig  = create_metarig_and_fit(props)
rig      = generate_full_rig(metarig)

bind_mesh_to_rig(meshes, rig)

bone_map = build_bone_mapping(rig)
Path(args.bones).write_text(json.dumps(bone_map, indent=2))

export_as_glb(args.output, rig, meshes)

print("=" * 60)
print(f"[RigFlow] SUCCESS — {len(bone_map)} bones mapped")
print("=" * 60)