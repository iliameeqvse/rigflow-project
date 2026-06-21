"""
Generate ONE training example from a rigged Mixamo FBX.

This is the foundation of the whole ML project: it turns a model whose
skeleton is already correct into an image + the true pixel positions of every
joint. Those pixel positions are the labels the network will learn to predict.

Run it with Blender (no window needed):

    blender --background --python ml/data_gen/render_keypoints.py -- \
        --fbx "path/to/mixamo_model.fbx" --out "ml/datasets/my_model"

It writes three files into --out:

    front.png     clean front ortho render        <- network INPUT
    side.png      clean left-side ortho render     <- network INPUT
    labels.json   {view: {landmark: [px, py]|null}} <- network TARGET

IMPORTANT: the PNGs contain NO skeleton on purpose. The network has to learn
from pictures that look like a real user's upload, and real uploads have no
bones drawn on them. To eyeball whether the labels are correct, run
draw_overlay.py afterwards to get a copy with dots drawn on the joints.

The camera setup and the world->pixel formula below are copied from
backend/scripts/blender_autorig.py (render_ortho_views / world_to_pixel) so the
coordinates produced here match the real pipeline exactly.
"""
import argparse
import json
import sys
from pathlib import Path

import bpy
from mathutils import Vector


# ---------------------------------------------------------------------------
# Which Mixamo bone gives each landmark.
#
# We read each bone's HEAD (the joint end). Mixamo names bones like
# "mixamorig:LeftArm"; the prefix before ":" varies between exports, so we
# match on the part AFTER the colon, case-insensitively (see find_bone).
#
# Mixamo's "Left" already means the CHARACTER's left, which matches RigFlow's
# red-cube = character-left convention. No flipping needed.
#
# (heel / foot-tip are intentionally omitted for v1 — Mixamo has no heel bone,
#  so they'd be approximations. Add them later from mesh geometry if you want
#  the full 16-landmark schema.)
LANDMARK_BONES = {
    "chin":           "Head",       # head joint (base of skull); front view only
    "groin":          "Hips",       # pelvis centre
    "left_shoulder":  "LeftArm",
    "right_shoulder": "RightArm",
    "left_elbow":     "LeftForeArm",
    "right_elbow":    "RightForeArm",
    "left_wrist":     "LeftHand",
    "right_wrist":    "RightHand",
    "left_hip":       "LeftUpLeg",
    "right_hip":      "RightUpLeg",
    "left_knee":      "LeftLeg",
    "right_knee":     "RightLeg",
    "left_ankle":     "LeftFoot",
    "right_ankle":    "RightFoot",
}


def log(msg):
    print(f"[render_keypoints] {msg}")


def parse_args():
    # Blender passes script args after a literal "--".
    argv = sys.argv
    argv = argv[argv.index("--") + 1:] if "--" in argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--fbx", required=True, help="path to the Mixamo .fbx")
    p.add_argument("--out", required=True, help="output directory for this example")
    p.add_argument("--image-size", type=int, default=512)
    return p.parse_args(argv)


def clear_scene():
    """Remove the default cube/camera/light so only our model is present."""
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)


def import_fbx(fbx_path):
    bpy.ops.import_scene.fbx(filepath=str(fbx_path))


def get_meshes_and_armature():
    meshes = [o for o in bpy.data.objects if o.type == "MESH"]
    armatures = [o for o in bpy.data.objects if o.type == "ARMATURE"]
    if not meshes:
        raise RuntimeError("no mesh objects found in the FBX")
    if not armatures:
        raise RuntimeError("no armature found — is this a rigged Mixamo model?")
    return meshes, armatures[0]


def find_bone(armature, suffix):
    """Find a bone whose name ends in `suffix` (after stripping any 'prefix:').

    Mixamo bones are 'mixamorig:LeftArm'; we match 'LeftArm', case-insensitive.
    """
    want = suffix.lower()
    for bone in armature.data.bones:
        name = bone.name.split(":")[-1].lower()
        if name == want:
            return bone
    return None


def world_aabb(meshes):
    """Axis-aligned bounding box of all mesh vertices, in world space."""
    mn = Vector((float("inf"),) * 3)
    mx = Vector((float("-inf"),) * 3)
    for m in meshes:
        for v in m.data.vertices:
            w = m.matrix_world @ v.co
            for i in range(3):
                mn[i] = min(mn[i], w[i])
                mx[i] = max(mx[i], w[i])
    return mn, mx


def world_to_pixel(view_name, world_point, image_size, ortho_scale, aabb):
    """Project a 3D world point to [px, py] in the given ortho view.

    Identical formula/convention to blender_autorig.world_to_pixel. Returns
    None if the point falls outside the frame.
    """
    mn, mx = aabb
    cx = (mn[0] + mx[0]) / 2
    cy = (mn[1] + mx[1]) / 2
    cz = (mn[2] + mx[2]) / 2
    wx, wy, wz = world_point[0], world_point[1], world_point[2]

    if view_name == "front":
        u, v = wx - cx, wz - cz
    elif view_name == "left":
        u, v = cy - wy, wz - cz
    else:
        raise ValueError(f"unsupported view {view_name!r}")

    if ortho_scale <= 0:
        return None
    px = (u / ortho_scale + 0.5) * image_size
    py = (0.5 - v / ortho_scale) * image_size
    if px < 0 or px >= image_size or py < 0 or py >= image_size:
        return None
    return [round(px, 1), round(py, 1)]


def setup_render(image_size):
    scene = bpy.context.scene
    for eng in ("CYCLES", "BLENDER_EEVEE_NEXT", "BLENDER_EEVEE"):
        try:
            scene.render.engine = eng
            break
        except Exception:
            continue
    if scene.render.engine == "CYCLES":
        scene.cycles.samples = 8
        scene.cycles.use_denoising = False
        try:
            scene.cycles.device = "CPU"
        except Exception:
            pass
    scene.render.resolution_x = image_size
    scene.render.resolution_y = image_size
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    return scene


def add_sun(center, dist):
    sun_data = bpy.data.lights.new("sun", "SUN")
    sun_data.energy = 3.0
    sun_obj = bpy.data.objects.new("sun", sun_data)
    bpy.context.scene.collection.objects.link(sun_obj)
    sun_obj.location = center + Vector((0, 0, dist))


def render_view(scene, name, loc, target, ortho_scale, out_png):
    cam_data = bpy.data.cameras.new(f"cam_{name}")
    cam_data.type = "ORTHO"
    cam_data.ortho_scale = max(ortho_scale, 0.01)
    cam_obj = bpy.data.objects.new(f"cam_{name}", cam_data)
    scene.collection.objects.link(cam_obj)
    cam_obj.location = loc
    cam_obj.rotation_euler = (target - loc).to_track_quat("-Z", "Y").to_euler()

    scene.camera = cam_obj
    scene.render.filepath = str(out_png)
    bpy.ops.render.render(write_still=True)

    bpy.data.objects.remove(cam_obj, do_unlink=True)
    bpy.data.cameras.remove(cam_data)
    log(f"rendered {name} -> {out_png}")


def main():
    args = parse_args()
    # Resolve to an ABSOLUTE path: Blender's render.filepath mangles relative
    # paths (it anchored them to the drive root, e.g. C:\datasets\...).
    out_dir = Path(args.out).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    size = args.image_size

    clear_scene()
    import_fbx(args.fbx)
    meshes, armature = get_meshes_and_armature()

    mn, mx = world_aabb(meshes)
    aabb = (mn, mx)
    center = Vector(((mn.x + mx.x) / 2, (mn.y + mx.y) / 2, (mn.z + mx.z) / 2))
    xsize, ysize, zsize = mx.x - mn.x, mx.y - mn.y, mx.z - mn.z
    dist = max(xsize, ysize, zsize) * 3 + 1.0

    # Same per-view ortho scale as render_ortho_views (15% padding).
    fb_scale = max(xsize, zsize) * 1.15   # front sees X x Z
    lr_scale = max(ysize, zsize) * 1.15   # side  sees Y x Z

    scene = setup_render(size)
    add_sun(center, dist)

    # --- render the two clean input images ---
    views = {
        "front": (Vector((center.x, mn.y - dist, center.z)), fb_scale, "front.png"),
        "left":  (Vector((mn.x - dist, center.y, center.z)), lr_scale, "side.png"),
    }
    view_scale = {}
    for name, (loc, scale, fname) in views.items():
        render_view(scene, name, loc, center, scale, out_dir / fname)
        view_scale[name] = scale

    # --- compute the labels (true joint pixel positions) ---
    labels = {"front": {}, "left": {}}
    missing = []
    for landmark, bone_suffix in LANDMARK_BONES.items():
        bone = find_bone(armature, bone_suffix)
        if bone is None:
            missing.append(f"{landmark} ({bone_suffix})")
            for view in labels:
                labels[view][landmark] = None
            continue
        world_head = armature.matrix_world @ bone.head_local
        for view in labels:
            labels[view][landmark] = world_to_pixel(
                view, world_head, size, view_scale[view], aabb
            )

    if missing:
        log(f"WARNING: bones not found, labelled null: {', '.join(missing)}")

    # Chin comes from the Head joint, which sits at the centre of the skull. In
    # the front view that lands on the jaw; in a profile it lands on the cheek
    # (depth error), so we don't label chin in the side view.
    labels["left"]["chin"] = None

    # labels.json keys: "front" and "side" (rename "left" -> "side" to match files)
    out_labels = {"front": labels["front"], "side": labels["left"]}
    (out_dir / "labels.json").write_text(json.dumps(out_labels, indent=2))
    log(f"wrote {out_dir / 'labels.json'}")
    log("done. run draw_overlay.py to check the labels visually.")


if __name__ == "__main__":
    main()
