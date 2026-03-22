"""
Blender headless auto-rig script.

Run: blender --background --python blender_autorig.py -- \
     --input mesh.fbx --output rigged.glb --bones bones.json --format fbx
     [--landmarks '{"chin":[x,y,z],...}']

Landmark coordinates arrive in Three.js / glTF space (Y-up, right-handed):
  Three.js X  →  Blender X   (same)
  Three.js Y  →  Blender Z   (up axis)
  Three.js Z  →  Blender -Y  (depth)
"""

import bpy
import sys
import json
import argparse
import math
from pathlib import Path
from mathutils import Vector

# ── Enable Rigify ─────────────────────────────────────────────────────────────
print("[RigFlow] Enabling Rigify addon...")
try:
    bpy.ops.preferences.addon_enable(module="rigify")
    print("[RigFlow] Rigify enabled OK")
except Exception:
    import addon_utils
    addon_utils.enable("rigify", default_set=True, persistent=True)
    print("[RigFlow] Rigify enabled via addon_utils")

# ── Parse args ────────────────────────────────────────────────────────────────
argv = sys.argv
argv = argv[argv.index("--") + 1:] if "--" in argv else []
parser = argparse.ArgumentParser()
parser.add_argument("--input",     required=True)
parser.add_argument("--output",    required=True)
parser.add_argument("--bones",     required=True)
parser.add_argument("--format",    default="fbx")
parser.add_argument("--landmarks", default=None)
args = parser.parse_args(argv)

TARGET_HEIGHT = 1.75


def threejs_to_blender(pt) -> Vector:
    """
    Convert a [x, y, z] point from Three.js / glTF Y-up space
    to Blender Z-up space.
      Three.js X  →  Blender X
      Three.js Y  →  Blender Z  (up)
      Three.js Z  →  Blender -Y (depth)
    """
    x, y, z = pt
    return Vector((x, -z, y))


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
    print("[RigFlow] Scene cleared, Rigify re-enabled")


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
        raise ValueError(f"Unsupported: {fmt}")


def get_mesh_objects():
    return [o for o in bpy.data.objects if o.type == "MESH" and not o.name.startswith("WGT-")]


def select_meshes(meshes):
    bpy.ops.object.select_all(action="DESELECT")
    for o in meshes: o.select_set(True)
    bpy.context.view_layer.objects.active = meshes[0]


def get_verts(meshes):
    v = []
    for obj in meshes:
        for vert in obj.data.vertices:
            v.append(obj.matrix_world @ vert.co)
    if not v: raise RuntimeError("No vertices.")
    return v


def measure(verts):
    xs=[v.x for v in verts]; ys=[v.y for v in verts]; zs=[v.z for v in verts]
    return (max(xs)-min(xs), max(ys)-min(ys), max(zs)-min(zs),
            min(xs),min(ys),min(zs), max(xs),max(ys),max(zs))


def rot(meshes, rx=0, ry=0, rz=0):
    select_meshes(meshes)
    if rx: bpy.ops.transform.rotate(value=math.radians(rx), orient_axis="X", orient_type="GLOBAL")
    if ry: bpy.ops.transform.rotate(value=math.radians(ry), orient_axis="Y", orient_type="GLOBAL")
    if rz: bpy.ops.transform.rotate(value=math.radians(rz), orient_axis="Z", orient_type="GLOBAL")
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=False)


def centre_feet(meshes):
    verts = get_verts(meshes)
    sx,sy,sz,mnx,mny,mnz,mxx,mxy,mxz = measure(verts)
    cx=(mxx+mnx)/2; cy=(mxy+mny)/2
    for o in meshes:
        o.location.x -= cx; o.location.y -= cy; o.location.z -= mnz
    select_meshes(meshes)
    bpy.ops.object.transform_apply(location=True, rotation=False, scale=False)


def orient_normalize_scale(meshes):
    select_meshes(meshes)
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    verts = get_verts(meshes)
    sx,sy,sz,*_ = measure(verts)
    print(f"[RigFlow] Raw — X:{sx:.3f} Y:{sy:.3f} Z:{sz:.3f}")

    def z_dom(v): a,b,c,*_=measure(v); return c>max(a,b)*1.15

    if not z_dom(verts):
        candidates=[(-90,0,0),(90,0,0),(0,0,90),(0,0,-90),(180,0,0),(-90,0,180),(-90,0,90),(-90,0,-90)]
        found=False
        for rx,ry,rz in candidates:
            rot(meshes,rx,ry,rz)
            v2=get_verts(meshes); a,b,c,*_=measure(v2)
            print(f"[RigFlow]   ({rx:4},{ry:4},{rz:4})° Z:{c:.3f}",end="")
            if z_dom(v2): print(" ✓"); found=True; break
            else: print(" ✗"); rot(meshes,-rx,-ry,-rz)
        if not found:
            verts=get_verts(meshes); a,b,c,*_=measure(verts)
            if a>=b and a>=c: rot(meshes,0,0,-90)
            elif b>=a and b>=c: rot(meshes,-90,0,0)
    else:
        print("[RigFlow] Upright OK")

    verts=get_verts(meshes); sx,sy,sz,*_=measure(verts)
    if sy > sx*1.05:
        print(f"[RigFlow] Facing fix — Y:{sy:.3f}>X:{sx:.3f}, rotating 90° Z")
        rot(meshes,0,0,90)
        verts=get_verts(meshes); sx,sy,sz,*_=measure(verts)
    print(f"[RigFlow] After orient — X:{sx:.3f} Y:{sy:.3f} Z:{sz:.3f}")

    centre_feet(meshes)

    verts=get_verts(meshes); sx,sy,sz,*_=measure(verts)
    if sz>0 and abs(sz-TARGET_HEIGHT)>0.05:
        sf=TARGET_HEIGHT/sz
        print(f"[RigFlow] Scale ×{sf:.4f} ({sz:.3f}→{TARGET_HEIGHT}m)")
        select_meshes(meshes)
        bpy.ops.transform.resize(value=(sf,sf,sf))
        bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
        centre_feet(meshes)

    verts=get_verts(meshes); sx,sy,sz,mnx,mny,mnz,mxx,mxy,mxz=measure(verts)
    props={"height":sz,"width":sx,"floor_z":0.0,"min_x":mnx,"max_x":mxx,"min_z":mnz,"max_z":mxz}
    print(f"[RigFlow] Final — h={sz:.4f}m  w={sx:.4f}m")
    return props


def create_and_fit_metarig(props, landmarks=None):
    print("[RigFlow] Creating metarig...")
    created=False
    for op in [lambda:bpy.ops.object.armature_human_metarig_add(),
               lambda:bpy.ops.armature.metarig_sample_add(metarig_type="human")]:
        try: op(); created=True; break
        except Exception as e: print(f"[RigFlow] op failed: {e}")
    if not created: raise RuntimeError("Could not create metarig.")

    metarig=bpy.context.active_object
    if not metarig or metarig.type!="ARMATURE": raise RuntimeError("No armature.")

    bpy.context.view_layer.objects.active=metarig
    bpy.ops.object.mode_set(mode="EDIT")

    # Remove face rig
    for bn in ["face","teeth.T","teeth.B","tongue"]:
        b=metarig.data.edit_bones.get(bn)
        if b:
            def _rm(x):
                for c in list(x.children): _rm(c)
                metarig.data.edit_bones.remove(x)
            _rm(b)

    if landmarks:
        # ── Convert landmarks from Three.js Y-up → Blender Z-up ──────────────
        chin  = threejs_to_blender(landmarks["chin"])
        lw    = threejs_to_blender(landmarks["left_wrist"])
        rw    = threejs_to_blender(landmarks["right_wrist"])
        groin = threejs_to_blender(landmarks["groin"])
        la    = threejs_to_blender(landmarks["left_ankle"])
        ra    = threejs_to_blender(landmarks["right_ankle"])

        print(f"[RigFlow] Landmarks (Blender Z-up):")
        print(f"  chin={chin[:]}")
        print(f"  left_wrist={lw[:]},  right_wrist={rw[:]}")
        print(f"  groin={groin[:]}")
        print(f"  left_ankle={la[:]},  right_ankle={ra[:]}")

        eb = metarig.data.edit_bones

        # ── Spine chain ───────────────────────────────────────────────────────
        body_height = chin.z - groin.z
        spine_names = ["spine","spine.001","spine.002","spine.003","spine.004","spine.005"]
        spine_ratios = [0.0, 0.18, 0.38, 0.58, 0.78, 0.92]   # 0=groin, 1=chin

        for i, (name, ratio) in enumerate(zip(spine_names, spine_ratios)):
            bone = eb.get(name)
            if not bone: continue
            pt = groin + (chin - groin) * ratio
            next_ratio = spine_ratios[i+1] if i+1 < len(spine_ratios) else 1.0
            next_pt    = groin + (chin - groin) * next_ratio
            bone.head = pt
            bone.tail = next_pt

        # Head bone (chin → head top)
        head_bone = eb.get("spine.006")
        if not head_bone:
            head_bone = eb.get("spine.005")
        if head_bone:
            head_top = chin + Vector((0, 0, body_height * 0.15))
            head_bone.head = chin
            head_bone.tail = head_top

        # ── Arms ─────────────────────────────────────────────────────────────
        shoulder_z = groin.z + body_height * 0.82
        body_cx    = (props["min_x"] + props["max_x"]) / 2.0

        # Blender convention (character faces -Y): LEFT = +X = Rigify .L
        #                                          RIGHT = -X = Rigify .R
        # UI tells users to click character's anatomical LEFT for "Left Wrist"
        # so: lw → .L,  rw → .R  (direct mapping, no sign-based swap)
        for side, wrist in [("L", lw), ("R", rw)]:
            sh_pos      = Vector((wrist.x, wrist.y, shoulder_z))
            neck_pos    = Vector((body_cx, wrist.y, shoulder_z))
            # Elbow bent slightly forward (+Y) to avoid collinear bones
            # which crash Rigify's pole-angle calculation
            elbow_pos   = sh_pos + (wrist - sh_pos) * 0.55 + Vector((0, 0.06, -0.02))
            forearm_dir = (wrist - elbow_pos).normalized()
            hand_tip    = wrist + forearm_dir * 0.07

            for bname, h, t in [
                (f"shoulder.{side}",  neck_pos,  sh_pos),
                (f"upper_arm.{side}", sh_pos,    elbow_pos),
                (f"forearm.{side}",   elbow_pos, wrist),
                (f"hand.{side}",      wrist,     hand_tip),
            ]:
                bone = eb.get(bname)
                if bone:
                    bone.head = h
                    bone.tail = t

        # ── Legs ──────────────────────────────────────────────────────────────
        hip_z = groin.z

        # Direct mapping: la (user "left_ankle") → .L,  ra → .R
        for side, ankle in [("L", la), ("R", ra)]:
            hip_pos  = Vector((ankle.x, ankle.y, hip_z))
            knee_pos = Vector((
                ankle.x * 0.95,
                ankle.y - 0.03,
                (hip_z + ankle.z) / 2 + 0.02,
            ))
            toe_pos  = ankle + Vector((0, -0.09, 0))
            toe_tip  = toe_pos + Vector((0, -0.04, 0))

            for bname, h, t in [
                (f"thigh.{side}", hip_pos,  knee_pos),
                (f"shin.{side}",  knee_pos, ankle),
                (f"foot.{side}",  ankle,    toe_pos),
                (f"toe.{side}",   toe_pos,  toe_tip),
            ]:
                bone = eb.get(bname)
                if bone:
                    bone.head = h
                    bone.tail = t

        print("[RigFlow] Landmark bone placement applied")
        bpy.ops.object.mode_set(mode="OBJECT")

    else:
        bpy.ops.object.mode_set(mode="OBJECT")
        scale = props["height"] / 2.0
        metarig.scale = (scale, scale, scale)
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
        metarig.location = (0, 0, props["floor_z"])
        bpy.ops.object.transform_apply(location=True, rotation=False, scale=False)
        print(f"[RigFlow] Metarig auto-scaled {scale:.4f}")

    return metarig


def generate_full_rig(metarig):
    print("[RigFlow] Generating full rig...")
    bpy.context.view_layer.objects.active=metarig
    bpy.ops.object.mode_set(mode="POSE")
    try: bpy.ops.pose.rigify_generate()
    except Exception as e: raise RuntimeError(f"rigify_generate: {e}")
    bpy.ops.object.mode_set(mode="OBJECT")
    rig=bpy.context.active_object
    print(f"[RigFlow] Rig: {rig.name}")
    return rig


def get_obj_center(obj):
    corners=[obj.matrix_world@Vector(c) for c in obj.bound_box]
    return sum(corners, Vector())/8.0


def region_based_binding(meshes, rig, props):
    height=props["height"]
    body_mid_x=(props["min_x"]+props["max_x"])/2.0
    body_width=props["max_x"]-props["min_x"]
    deform={b.name:b for b in rig.data.bones if b.name.startswith("DEF-")}

    def pick(n): return n if n in deform else "DEF-spine.001"

    def bone_for(cx,cz):
        nh=cz/height; nx=(cx-body_mid_x)/(body_width/2.0+1e-6)
        R,L=nx>0.15,nx<-0.15
        if nh>0.85: return pick("DEF-spine.005")
        if nh>0.78: return pick("DEF-spine.004")
        if nh>0.65:
            if R: return pick("DEF-shoulder.R")
            if L: return pick("DEF-shoulder.L")
            return pick("DEF-spine.003")
        if nh>0.50:
            if R and abs(nx)>0.40: return pick("DEF-upper_arm.R")
            if L and abs(nx)>0.40: return pick("DEF-upper_arm.L")
            if R: return pick("DEF-shoulder.R")
            if L: return pick("DEF-shoulder.L")
            return pick("DEF-spine.002")
        if nh>0.35:
            if R and abs(nx)>0.35: return pick("DEF-forearm.R")
            if L and abs(nx)>0.35: return pick("DEF-forearm.L")
            return pick("DEF-spine.001")
        if nh>0.20:
            if R and abs(nx)>0.55: return pick("DEF-hand.R")
            if L and abs(nx)>0.55: return pick("DEF-hand.L")
            if R and abs(nx)>0.30: return pick("DEF-forearm.R")
            if L and abs(nx)>0.30: return pick("DEF-forearm.L")
            return pick("DEF-spine")
        if nh>0.12:
            if R: return pick("DEF-thigh.R")
            if L: return pick("DEF-thigh.L")
            return pick("DEF-spine")
        if nh>0.05:
            if R: return pick("DEF-shin.R")
            if L: return pick("DEF-shin.L")
            return pick("DEF-shin.R")
        if R: return pick("DEF-foot.R")
        if L: return pick("DEF-foot.L")
        return pick("DEF-foot.R")

    select_meshes(meshes)
    bpy.context.view_layer.objects.active=rig
    bpy.ops.object.parent_set(type="ARMATURE_NAME")

    for obj in meshes:
        c=get_obj_center(obj); bn=bone_for(c.x,c.z)
        obj.vertex_groups.clear()
        vg=obj.vertex_groups.new(name=bn)
        vg.add([v.index for v in obj.data.vertices],1.0,"REPLACE")
        nh=c.z/height; nx=(c.x-body_mid_x)/(body_width/2.0+1e-6)
        print(f"[RigFlow]   {obj.name!r:40s} nh={nh:.2f} nx={nx:+.2f} → {bn}")

    print(f"[RigFlow] Region-bound {len(meshes)} mesh(es)")


def clean_rig_for_export(rig):
    widgets=[o for o in bpy.data.objects if o.name.startswith("WGT-")]
    print(f"[RigFlow] Removing {len(widgets)} widgets")
    for obj in widgets:
        for col in list(obj.users_collection): col.objects.unlink(obj)
        md=obj.data
        bpy.data.objects.remove(obj, do_unlink=True)
        if md and md.users==0: bpy.data.meshes.remove(md)
    for col in list(bpy.data.collections):
        if col.name.startswith("WGTS"): bpy.data.collections.remove(col)
    bpy.context.view_layer.objects.active=rig
    bpy.ops.object.mode_set(mode="EDIT")
    to_del=[b for b in rig.data.edit_bones if not b.name.startswith("DEF-")]
    for b in to_del: rig.data.edit_bones.remove(b)
    bpy.ops.object.mode_set(mode="OBJECT")
    print(f"[RigFlow] {len(rig.data.bones)} deform bones remain")


RIGIFY_TO_MIXAMO = {
    "DEF-spine":"Hips","DEF-spine.001":"Spine","DEF-spine.002":"Spine1",
    "DEF-spine.003":"Spine2","DEF-spine.004":"Neck","DEF-spine.005":"Head",
    "DEF-thigh.L":"LeftUpLeg","DEF-shin.L":"LeftLeg","DEF-foot.L":"LeftFoot",
    "DEF-toe.L":"LeftToeBase","DEF-thigh.R":"RightUpLeg","DEF-shin.R":"RightLeg",
    "DEF-foot.R":"RightFoot","DEF-toe.R":"RightToeBase",
    "DEF-shoulder.L":"LeftShoulder","DEF-upper_arm.L":"LeftArm",
    "DEF-forearm.L":"LeftForeArm","DEF-hand.L":"LeftHand",
    "DEF-shoulder.R":"RightShoulder","DEF-upper_arm.R":"RightArm",
    "DEF-forearm.R":"RightForeArm","DEF-hand.R":"RightHand",
    "DEF-thumb.01.L":"LeftHandThumb1","DEF-f_index.01.L":"LeftHandIndex1",
    "DEF-f_middle.01.L":"LeftHandMiddle1","DEF-f_ring.01.L":"LeftHandRing1",
    "DEF-f_pinky.01.L":"LeftHandPinky1","DEF-thumb.01.R":"RightHandThumb1",
    "DEF-f_index.01.R":"RightHandIndex1","DEF-f_middle.01.R":"RightHandMiddle1",
    "DEF-f_ring.01.R":"RightHandRing1","DEF-f_pinky.01.R":"RightHandPinky1",
}


def build_bone_mapping(rig):
    mapping={}
    for bone in rig.data.bones:
        mn=RIGIFY_TO_MIXAMO.get(bone.name)
        if mn: mapping[mn]=bone.name
    print(f"[RigFlow] Mapped {len(mapping)} bones")
    return mapping


def export_as_glb(output_path, rig, meshes):
    bpy.ops.object.select_all(action="DESELECT")
    rig.select_set(True)
    for m in meshes: m.select_set(True)
    bpy.context.view_layer.objects.active=rig
    bpy.ops.export_scene.gltf(
        filepath=output_path, export_format="GLB",
        export_animations=False, export_skins=True,
        use_selection=True, export_apply=True,
    )
    print(f"[RigFlow] Exported: {output_path}")


# ── MAIN ──────────────────────────────────────────────────────────────────────
print("="*60)
print(f"[RigFlow] Input:  {args.input}")
print(f"[RigFlow] Output: {args.output}")
mode = "LANDMARK-GUIDED" if args.landmarks else "AUTO-DETECT"
print(f"[RigFlow] Mode:   {mode}")
print("="*60)

try:
    landmarks = json.loads(args.landmarks) if args.landmarks else None

    clear_scene()
    import_model(args.input, args.format)

    meshes=get_mesh_objects()
    if not meshes: raise RuntimeError("No mesh objects found.")
    print(f"[RigFlow] Found {len(meshes)} mesh(es)")

    props   = orient_normalize_scale(meshes)
    metarig = create_and_fit_metarig(props, landmarks=landmarks)
    rig     = generate_full_rig(metarig)

    region_based_binding(meshes, rig, props)
    clean_rig_for_export(rig)

    bone_map=build_bone_mapping(rig)
    Path(args.bones).write_text(json.dumps(bone_map, indent=2))
    export_as_glb(args.output, rig, meshes)

    print("="*60)
    print(f"[RigFlow] SUCCESS — {len(bone_map)} bones mapped")
    print("="*60)

except Exception as e:
    print(f"\n[RigFlow] FATAL ERROR: {e}")
    import traceback; traceback.print_exc()
    sys.exit(1)