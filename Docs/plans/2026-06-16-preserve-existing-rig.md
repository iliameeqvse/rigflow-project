# Preserve Existing Rig on Upload — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When an uploaded model already has an armature that skins the mesh, keep that skeleton (skip Rigify), normalize + export it, and build a best-effort Mixamo bone map so animations still retarget.

**Architecture:** A new detection step runs right after `import_model` (before `strip_non_meshes`). If it finds an armature skinning the largest mesh, `main()` takes a self-contained keep-rig branch — normalize scale/orientation of the armature+mesh as one unit, build a name-based bone map, export the original skeleton — and skips the entire Rigify flow. Phase 1 reports `already_rigged` so the Celery task skips the AI vision call; a new `used_existing_rig` field records the outcome.

**Tech Stack:** Blender `bpy` (headless subprocess), Python 3.12 / Django `SimpleTestCase`, DRF, Next.js 16 / React 19.

**Spec:** [`Docs/specs/2026-06-16-preserve-existing-rig-design.md`](../specs/2026-06-16-preserve-existing-rig-design.md).

**Path conventions:** Paths are relative to `rigflow-project/`. Backend commands run from `rigflow-project/backend/` using the repo venv python (`C:/Users/dzodz/OneDrive/Desktop/Rigflow/venv/Scripts/python.exe` on this machine). Standalone Blender-stub tests run with that python directly. Blender-gated tests need Blender on `BLENDER_PATH`. End commit messages with:
`Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`

---

## File Structure

| File | Responsibility | Action |
|---|---|---|
| `backend/scripts/blender_autorig.py` | Add `canonical_mixamo_name`, `build_bone_map_from_existing`, `find_skinning_armature`, `normalize_existing_rig`; branch `main()` into the keep-rig path. | Modify |
| `backend/scripts/_test_canonical_mixamo_name.py` | Standalone (no-Blender) test for the pure name resolver. | Create |
| `backend/apps/rigging/models.py` | Add `used_existing_rig` field + `"preserved"` detection_method choice. | Modify |
| `backend/apps/rigging/migrations/0006_riggedmodel_used_existing_rig.py` | Schema migration (via `makemigrations`). | Create |
| `backend/apps/rigging/tasks.py` | Read `already_rigged` from the Phase-1 request → skip vision, set `used_existing_rig`/`detection_method`. | Modify |
| `backend/apps/rigging/serializers.py` | Expose `used_existing_rig`. | Modify |
| `backend/apps/rigging/tests/test_e2e_pipeline.py` | Blender-gated e2e: rigged GLB preserved, unrigged still auto-rigs. | Modify |
| `frontend/src/lib/api.ts` | Add `used_existing_rig?: boolean` to `RiggedModel`. | Modify |
| `frontend/src/app/editor/[modelId]/page.tsx` | "Original rig preserved" badge; hide landmark-editing UI when preserved. | Modify |

---

### Task 1: Pure canonical-name resolver (`canonical_mixamo_name`) — TDD, no Blender

The name-matching brain of the bone map. Pure string logic so it's unit-testable without Blender.

**Files:**
- Create: `backend/scripts/_test_canonical_mixamo_name.py`
- Modify: `backend/scripts/blender_autorig.py` (add function near `RIGIFY_TO_MIXAMO`, ~line 1583)

- [ ] **Step 1: Write the failing standalone test**

Create `backend/scripts/_test_canonical_mixamo_name.py`:

```python
"""Standalone smoke test for canonical_mixamo_name. No Blender needed.
Run from backend/:  python scripts/_test_canonical_mixamo_name.py
"""
import importlib.util, sys
from pathlib import Path

# Stub bpy / mathutils so blender_autorig imports in plain Python.
stub_mu = type(sys)("mathutils")
stub_mu.Vector = tuple
stub_mu.Quaternion = object
stub_mu.Matrix = object
sys.modules["mathutils"] = stub_mu
sys.modules["bpy"] = type(sys)("bpy")

src = Path(__file__).parent / "blender_autorig.py"
spec = importlib.util.spec_from_file_location("blender_autorig", src)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
f = mod.canonical_mixamo_name

cases = {
    # exact Mixamo names (with namespaces) pass straight through
    "mixamorig:Hips": "Hips",
    "mixamorig:LeftHandIndex1": "LeftHandIndex1",
    "Armature|RightForeArm": "RightForeArm",
    # heuristic conventions
    "pelvis": "Hips",
    "spine_01": "Spine1",
    "L_UpperArm": "LeftArm",
    "r_forearm": "RightForeArm",
    "Left_Foot": "LeftFoot",
    "RightUpLeg": "RightUpLeg",
    "clavicle_l": "LeftShoulder",
    # control / non-deform bones → None
    "IK_Hand_L": None,
    "knee_pole_target_R": None,
    "some_random_prop": None,
}
failures = []
for raw, expected in cases.items():
    got = f(raw)
    ok = got == expected
    print(f"  [{'OK' if ok else 'FAIL'}] {raw!r} → {got!r} (expected {expected!r})")
    if not ok:
        failures.append(raw)

if failures:
    print(f"FAILED: {failures}")
    sys.exit(1)
print("canonical_mixamo_name: OK")
```

- [ ] **Step 2: Run it to verify it fails**

Run (from `backend/`): `python scripts/_test_canonical_mixamo_name.py`
Expected: `AttributeError: module 'blender_autorig' has no attribute 'canonical_mixamo_name'`.

- [ ] **Step 3: Implement `canonical_mixamo_name`**

In `backend/scripts/blender_autorig.py`, immediately AFTER the `RIGIFY_TO_MIXAMO = { ... }` dict (it ends ~line 1583, just before `def build_bone_map`), add:

```python
import re as _re

# Mixamo names we already know (the values of RIGIFY_TO_MIXAMO, incl. fingers).
_KNOWN_MIXAMO = set(RIGIFY_TO_MIXAMO.values())


def canonical_mixamo_name(raw):
    """Map an arbitrary bone name to a canonical Mixamo bone name, or None.

    Pure string logic (no bpy). Two stages:
      1. Strip namespaces ("mixamorig:Hips", "Armature|Hips"); if what's left
         is already a known Mixamo name, use it verbatim (covers Mixamo-named
         rigs exactly, fingers included).
      2. Otherwise lower-case and match common naming conventions for the body
         bones. Returns None for control/non-deform bones and anything unknown.
    """
    stripped = _re.sub(r"^.*[:|]", "", raw)
    stripped = _re.sub(r"^mixamorig\d*", "", stripped)
    if stripped in _KNOWN_MIXAMO:
        return stripped

    core = _re.sub(r"_(?:bn|bone|jnt|joint|ctrl|grp)$", "", stripped, flags=_re.I)
    core = core.lower().strip()

    side = ""
    m = _re.match(r"^(l|left|r|right)[_.\- ]", core)
    if m:
        side = "Left" if m.group(1)[0] == "l" else "Right"
        core = core[m.end():]
    else:
        m = _re.search(r"[_.\- ](l|left|r|right)$", core)
        if m:
            side = "Left" if m.group(1)[0] == "l" else "Right"
            core = core[: m.start()]
    core = core.strip("_.- ")

    # Skip control / helper bones we never want to drive.
    if _re.search(r"ik|effector|pole|target|ctrl|helper|twist|roll", core):
        return None

    # Torso (no side)
    if _re.fullmatch(r"hips?|pelvis|root", core):                 return "Hips"
    if _re.fullmatch(r"spine", core):                             return "Spine"
    if _re.fullmatch(r"spine_?0?1|chest", core):                  return "Spine1"
    if _re.fullmatch(r"spine_?0?2|upper_?chest", core):           return "Spine2"
    if _re.fullmatch(r"neck", core):                              return "Neck"
    if _re.fullmatch(r"head", core):                              return "Head"

    if not side:
        return None

    # Sided limbs
    if _re.fullmatch(r"shoulder|clavicle", core):                 return f"{side}Shoulder"
    if _re.fullmatch(r"arm|upper_?arm|uparm", core):              return f"{side}Arm"
    if _re.fullmatch(r"forearm|lower_?arm|elbow", core):          return f"{side}ForeArm"
    if _re.fullmatch(r"hand|wrist", core):                        return f"{side}Hand"
    if _re.fullmatch(r"up_?leg|upper_?leg|thigh|hip", core):      return f"{side}UpLeg"
    if _re.fullmatch(r"leg|lower_?leg|shin|calf|knee", core):     return f"{side}Leg"
    if _re.fullmatch(r"foot|ankle", core):                        return f"{side}Foot"
    if _re.fullmatch(r"toe|toe_?base|ball", core):                return f"{side}ToeBase"
    return None
```

(`RIGIFY_TO_MIXAMO` already includes finger names after the M0 change, so `_KNOWN_MIXAMO` covers fingers for Mixamo-named rigs. Non-Mixamo finger bones stay unmapped — best-effort per spec §8.)

- [ ] **Step 4: Run it to verify it passes**

Run (from `backend/`): `python scripts/_test_canonical_mixamo_name.py`
Expected: `canonical_mixamo_name: OK`.

- [ ] **Step 5: Commit**

```bash
git add backend/scripts/blender_autorig.py backend/scripts/_test_canonical_mixamo_name.py
git commit -m "feat(rigging): canonical_mixamo_name resolver for existing-rig bone maps

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: `build_bone_map_from_existing` + `find_skinning_armature`

bpy-dependent; covered by the e2e test in Task 8. Keep them small and logged.

**Files:**
- Modify: `backend/scripts/blender_autorig.py`

- [ ] **Step 1: Add `build_bone_map_from_existing`**

Immediately after `canonical_mixamo_name`, add:

```python
def build_bone_map_from_existing(armature):
    """Best-effort {MixamoName: existingBoneName} from a kept skeleton.

    First match per Mixamo name wins. Same shape as build_bone_map so the
    animation retargeter and frontend consume it identically."""
    mapping = {}
    for b in armature.data.bones:
        mx = canonical_mixamo_name(b.name)
        if mx and mx not in mapping:
            mapping[mx] = b.name
    log(
        f"Existing-rig bone map: {len(mapping)} of "
        f"{len(armature.data.bones)} bones mapped to Mixamo names"
    )
    return mapping
```

- [ ] **Step 2: Add `find_skinning_armature`**

Add near `get_meshes` (~line 188):

```python
def find_skinning_armature(meshes):
    """Return the armature that skins the LARGEST mesh, or None.

    'Skins' means the mesh has an ARMATURE modifier targeting the armature AND
    at least one vertex group whose name matches a bone in that armature. The
    armature must have >= 2 bones. Naming-agnostic. Picking the largest-mesh
    deformer ignores prop-only armatures (e.g. a one-bone sword rig)."""
    real = [m for m in meshes if not _is_rigify_widget_object(m)]
    if not real:
        return None
    largest = max(real, key=lambda m: len(m.data.vertices))
    vg_names = {vg.name for vg in largest.vertex_groups}
    if not vg_names:
        return None
    best, best_matches = None, 0
    for mod in largest.modifiers:
        if mod.type != "ARMATURE" or not mod.object or mod.object.type != "ARMATURE":
            continue
        arm = mod.object
        bone_names = {b.name for b in arm.data.bones}
        if len(bone_names) < 2:
            continue
        matches = len(vg_names & bone_names)
        if matches > best_matches:
            best, best_matches = arm, matches
    if best is not None:
        log(f"Detected existing rig '{best.name}' skinning largest mesh "
            f"'{largest.name}' ({best_matches} matching vertex groups)")
    return best
```

- [ ] **Step 3: Syntax check**

Run (from `backend/`): `python -c "import ast,io; ast.parse(io.open('scripts/blender_autorig.py',encoding='utf-8').read()); print('OK')"`
Expected: `OK`.

- [ ] **Step 4: Commit**

```bash
git add backend/scripts/blender_autorig.py
git commit -m "feat(rigging): detect skinning armature + build bone map from existing rig

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: `normalize_existing_rig` (scale armature+mesh as one unit)

The mesh-only helpers (`apply_user_rotation`, `scale_mesh_to_metarig`) bake transforms on meshes only, which would detach a kept rig. Normalize the whole hierarchy via a temporary parent Empty so skinning survives.

**Files:**
- Modify: `backend/scripts/blender_autorig.py`

- [ ] **Step 1: Add `normalize_existing_rig`**

Add after `scale_mesh_to_metarig` (~line 708):

```python
def normalize_existing_rig(armature, meshes):
    """Uniform-scale + recenter a KEPT rig (armature + skinned meshes) so the
    largest mesh is THREE_DISPLAY_HEIGHT tall, feet at Z=0, XY-centered —
    without breaking the armature→mesh skinning. Scales the whole hierarchy
    together by parenting to a temporary Empty, then bakes transforms."""
    real = [m for m in meshes if not _is_rigify_widget_object(m)]
    largest = max(real, key=lambda m: len(m.data.vertices))

    deselect_all()
    bpy.ops.object.empty_add(type="PLAIN_AXES", location=(0, 0, 0))
    pivot = bpy.context.active_object
    pivot.name = "RigFlowNormalizePivot"

    # Parent the armature and any meshes to the pivot, keeping world transform.
    members = [armature] + real
    for obj in members:
        if obj.parent is None:
            obj.parent = pivot
            obj.matrix_parent_inverse = pivot.matrix_world.inverted()

    # Measure the largest mesh in world space.
    b = aabb([armature.matrix_world @ v.co for v in []] or world_vertices([largest]))
    mh = b["size"].z
    if mh <= 1e-6:
        log("normalize_existing_rig: degenerate height, skipping scale")
    else:
        factor = THREE_DISPLAY_HEIGHT / mh
        pivot.scale = (factor, factor, factor)

    bpy.context.view_layer.update()
    b2 = aabb(world_vertices([largest]))
    pivot.location.x -= (b2["min"].x + b2["max"].x) / 2
    pivot.location.z -= (b2["min"].z + b2["max"].z) / 2  # placeholder; fixed below
    bpy.context.view_layer.update()
    b3 = aabb(world_vertices([largest]))
    pivot.location.z -= b3["min"].z  # feet to Z=0

    # Bake: select pivot + members, apply all transforms, then drop the pivot.
    bpy.context.view_layer.update()
    deselect_all()
    for obj in [pivot] + members:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = armature
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)

    for obj in members:
        obj.parent = None
    bpy.data.objects.remove(pivot, do_unlink=True)

    actual = aabb(world_vertices([largest]))["size"].z
    log(f"Normalized existing rig → {actual:.3f}m (target {THREE_DISPLAY_HEIGHT})")
```

> **Implementer note:** Blender's parent/transform-apply on rigged hierarchies is fiddly. After writing this, the Task 8 e2e test is the gate — it asserts the exported mesh stays bound (skeleton joint count preserved, mesh has skin weights). If `transform_apply` complains about the Armature modifier, apply to meshes/empty first and scale the armature's `data` separately; iterate against the e2e test, not by guessing.

- [ ] **Step 2: Syntax check**

Run (from `backend/`): `python -c "import ast,io; ast.parse(io.open('scripts/blender_autorig.py',encoding='utf-8').read()); print('OK')"`
Expected: `OK`.

- [ ] **Step 3: Commit**

```bash
git add backend/scripts/blender_autorig.py
git commit -m "feat(rigging): normalize_existing_rig scales kept rig without breaking skin

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: Branch `main()` into the keep-rig path

Detection must run BEFORE `strip_non_meshes` (line 2130) or the armature is already deleted.

**Files:**
- Modify: `backend/scripts/blender_autorig.py` (`main`, ~line 2128)

- [ ] **Step 1: Insert the keep-rig branch right after `import_model`**

In `main()`, the current opening is:

```python
    clear_scene()
    import_model(args.input, args.format)
    strip_non_meshes()
    purge_missing_image_refs()
```

Replace with:

```python
    clear_scene()
    import_model(args.input, args.format)
    purge_missing_image_refs()

    # Keep-rig path: if the upload already has an armature skinning the largest
    # mesh, preserve it and skip Rigify entirely. Explicit landmark re-rigs
    # (args.landmarks) always re-rig, so they bypass this.
    if not args.landmarks:
        _kept_arm = find_skinning_armature(get_meshes())
        if _kept_arm is not None:
            _run_keep_existing_rig(args, _kept_arm)
            return

    strip_non_meshes()
```

- [ ] **Step 2: Add the `_run_keep_existing_rig` function**

Add directly above `def main():` (~line 2122):

```python
def _run_keep_existing_rig(args, armature):
    """Keep-rig branch: normalize + export the uploaded skeleton, skip Rigify.

    Handles both pipeline phases:
      - Phase 1 (--render-ortho-views): write ai_request.json with
        {"already_rigged": true} and exit so tasks.py skips the vision call.
      - Phase 2: normalize, build bone map, export the original skeleton.
    """
    meshes = get_meshes()
    if not meshes:
        raise RuntimeError("No meshes found after import")
    log(f"KEEP-RIG: preserving existing armature '{armature.name}'")

    apply_user_rotation(
        meshes,
        user_rotation_x=args.initial_rotation_x,
        user_rotation_y=args.initial_rotation_y,
        user_rotation_z=args.initial_rotation_z,
        user_rotation_quat=None,
    )

    if args.render_ortho_views:
        if not args.ai_request_out:
            log("ERROR: --render-ortho-views requires --ai-request-out")
            sys.exit(1)
        Path(args.ai_request_out).write_text(json.dumps({
            "already_rigged": True,
            "armature": armature.name,
        }, indent=2))
        log("KEEP-RIG: wrote already_rigged request; exiting phase 1.")
        sys.exit(0)

    normalize_existing_rig(armature, meshes)

    if args.pose:
        Path(args.pose).write_text(json.dumps({
            "classification": "unclear", "angle_deg": None,
            "confidence": 0.0, "reason": "existing rig preserved",
        }, indent=2))

    bone_map = build_bone_map_from_existing(armature)
    Path(args.bones).write_text(json.dumps(bone_map, indent=2))

    # No Rigify landmarks for a kept rig; emit an empty sidecar so the task's
    # landmarks read is a no-op.
    if args.landmarks_out:
        Path(args.landmarks_out).write_text(json.dumps({}, indent=2))

    export_glb(meshes, armature, args.output)
    log(f"KEEP-RIG SUCCESS — preserved skeleton, {len(bone_map)} bones mapped")
```

> Note `apply_user_rotation` currently bakes mesh-only transforms; for a kept rig the rotation is applied here BEFORE `normalize_existing_rig` re-parents everything to the pivot, so the subsequent transform-apply re-bakes the armature too. If rotation visibly detaches the rig in the e2e test, move the rotation onto the pivot inside `normalize_existing_rig` instead.

- [ ] **Step 3: Syntax check + standalone resolver test still green**

Run (from `backend/`):
```bash
python -c "import ast,io; ast.parse(io.open('scripts/blender_autorig.py',encoding='utf-8').read()); print('OK')"
python scripts/_test_canonical_mixamo_name.py
```
Expected: `OK` then `canonical_mixamo_name: OK`.

- [ ] **Step 4: Commit**

```bash
git add backend/scripts/blender_autorig.py
git commit -m "feat(rigging): main() keeps an existing rig instead of re-rigging

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: Model field `used_existing_rig` + `"preserved"` detection_method

**Files:**
- Modify: `backend/apps/rigging/models.py`
- Create: `backend/apps/rigging/migrations/0006_riggedmodel_used_existing_rig.py` (generated)

- [ ] **Step 1: Add the choice + field**

In `backend/apps/rigging/models.py`, change the `DETECTION_METHOD_CHOICES` block (lines 61–75) to add the constant + choice:

```python
    DETECTION_GEOMETRY       = "geometry"
    DETECTION_LLM_VISION     = "llm_vision"
    DETECTION_USER_LANDMARKS = "user_landmarks"
    DETECTION_FAILED         = "failed"
    DETECTION_PRESERVED      = "preserved"
    DETECTION_METHOD_CHOICES = [
        ("geometry",       "Geometry only"),
        ("llm_vision",     "LLM vision + geometry refine"),
        ("user_landmarks", "User-supplied landmarks"),
        ("failed",         "AI + geometry both failed; AABB defaults used"),
        ("preserved",      "Original uploaded rig preserved"),
    ]
```

Then immediately after the `vision_response_raw` field (ends ~line 82), add:

```python
    used_existing_rig = models.BooleanField(
        default=False, db_index=True,
        help_text=(
            "True when the upload already had a skeleton that skins the mesh; "
            "Rigify was skipped and the original rig kept."
        ),
    )
```

- [ ] **Step 2: Generate and apply the migration**

Run (from `backend/`):
```bash
python manage.py makemigrations rigging
python manage.py migrate rigging
```
Expected: creates `0006_riggedmodel_used_existing_rig.py`; `Applying rigging.0006... OK`.

- [ ] **Step 3: Django check**

Run (from `backend/`): `python manage.py check`
Expected: `System check identified no issues`.

- [ ] **Step 4: Commit**

```bash
git add backend/apps/rigging/models.py backend/apps/rigging/migrations/0006_riggedmodel_used_existing_rig.py
git commit -m "feat(rigging): add used_existing_rig field + 'preserved' detection_method

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: Wire `tasks.py` — skip AI for rigged uploads, record the outcome

**Files:**
- Modify: `backend/apps/rigging/tasks.py`

- [ ] **Step 1: Detect `already_rigged` in Phase 1 and skip the vision call**

In `_run_rig_pipeline`, the Phase-1 block reads `request_data` then builds a `VisionRequest` (lines ~154–163). Replace the `elif request_path.exists():` body's start so it short-circuits on `already_rigged`. Change:

```python
                        elif request_path.exists():
                            request_data = json.loads(request_path.read_text())
                            vision_req = VisionRequest(
```

to:

```python
                        elif request_path.exists():
                            request_data = json.loads(request_path.read_text())
                            if request_data.get("already_rigged"):
                                ai_phase_log.append(
                                    "[RigFlow] Upload already rigged — skipping "
                                    "vision; preserving existing skeleton."
                                )
                                rig.used_existing_rig = True
                                rig.detection_method = "preserved"
                            else:
                                vision_req = VisionRequest(
```

Indent the existing `VisionRequest(...)` construction and everything through the `rig.detection_method = "..."` assignments in that block one level deeper so it sits under the new `else:`. (The block runs from `vision_req = VisionRequest(` through the `else: rig.detection_method = "geometry"` for the no-landmarks case — re-indent that whole span by 4 spaces.)

- [ ] **Step 2: Persist the field after a successful run**

`rig.save()` already runs at the end of the pipeline (the same place `bone_mapping`/`status` are saved). `rig.used_existing_rig` and `rig.detection_method` set in Step 1 are saved by that existing call — no new save needed. Verify by reading the save site: search `grep -n "rig.save()" backend/apps/rigging/tasks.py` and confirm it runs after this block on the success path.

- [ ] **Step 3: Smoke test in the container**

```bash
cd rigflow-project
docker compose -f docker/docker-compose.yml exec -T celery python manage.py shell -c "
from apps.rigging.models import RiggedModel
from apps.rigging.tasks import _run_rig_pipeline
r = RiggedModel.objects.filter(original_format='glb').order_by('-created_at').first()
_run_rig_pipeline(str(r.id)); r.refresh_from_db()
print('used_existing_rig=', r.used_existing_rig, 'method=', r.detection_method)
print('bones mapped=', len(r.bone_mapping or {}))
"
```
Expected (for a rigged GLB): `used_existing_rig= True method= preserved`, bones mapped > 0, status done.

- [ ] **Step 4: Commit**

```bash
git add backend/apps/rigging/tasks.py
git commit -m "feat(rigging): skip AI + record preserved rig when upload is already rigged

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 7: Expose `used_existing_rig` on the serializer

**Files:**
- Modify: `backend/apps/rigging/serializers.py`

- [ ] **Step 1: Add the field**

In `RiggedModelSerializer.Meta.fields` (lines 11–27), add `"used_existing_rig"` after `"detection_method"`:

```python
            "detection_method",
            "used_existing_rig",
            "created_at",
```

- [ ] **Step 2: Verify**

Run (from `backend/`): `python manage.py check`
Expected: `System check identified no issues`.

- [ ] **Step 3: Commit**

```bash
git add backend/apps/rigging/serializers.py
git commit -m "feat(api): expose used_existing_rig on the rig serializer

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 8: Blender-gated e2e test

**Files:**
- Modify: `backend/apps/rigging/tests/test_e2e_pipeline.py`

- [ ] **Step 1: Read the existing e2e patterns**

Run (from `backend/`): `grep -n "BLENDER_EXECUTABLE\|_make_rig\|_JOHNNY_FBX\|skipTest\|def test" apps/rigging/tests/test_e2e_pipeline.py | head -30`
Note the helper that creates a `RiggedModel` from a file and runs the pipeline, and the Blender-availability skip guard. Reuse them.

- [ ] **Step 2: Append the preserved-rig test class**

Use a rigged GLB that exists on disk (the medieval_guard upload is rigged):

```python
class PreserveExistingRigTest(TestCase):
    """An upload that already has a skinning armature keeps its skeleton."""

    _RIGGED_GLB = Path(
        "media/rigs/2/73271f33-4ed2-4a18-b794-1ed912225d31/medieval_guard.glb"
    )

    def test_existing_rig_is_preserved(self):
        from django.conf import settings
        if not Path(settings.BLENDER_EXECUTABLE).is_file():
            self.skipTest("Blender executable not available")
        if not self._RIGGED_GLB.is_file():
            self.skipTest("rigged test GLB not on disk")

        rig = _make_rig(self._RIGGED_GLB)          # reuse the module helper
        from apps.rigging.tasks import _run_rig_pipeline
        _run_rig_pipeline(str(rig.id))
        rig.refresh_from_db()

        self.assertEqual(rig.status, "done")
        self.assertTrue(rig.used_existing_rig)
        self.assertEqual(rig.detection_method, "preserved")
        self.assertGreater(len(rig.bone_mapping or {}), 0)
```

If `_make_rig` does not accept an arbitrary path / format, mirror whatever the existing tests do to construct a `RiggedModel` with `original_format="glb"` pointing at `_RIGGED_GLB`, then call `_run_rig_pipeline`.

- [ ] **Step 3: Run it**

Run (from `backend/`): `python manage.py test apps.rigging.tests.test_e2e_pipeline.PreserveExistingRigTest -v 2`
Expected: PASS (or `skipped` if Blender / the GLB is unavailable — skip is acceptable, FAIL/ERROR is not). If it fails on detached skinning or scale, iterate on `normalize_existing_rig` (Task 3) until the export keeps weights and the bone map is non-empty.

- [ ] **Step 4: Commit**

```bash
git add backend/apps/rigging/tests/test_e2e_pipeline.py
git commit -m "test(rigging): e2e asserts an already-rigged upload is preserved

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 9: Frontend — badge + hide landmark editor for preserved rigs

**Files:**
- Modify: `frontend/src/lib/api.ts`
- Modify: `frontend/src/app/editor/[modelId]/page.tsx`

- [ ] **Step 1: Add the type field**

In `frontend/src/lib/api.ts`, in the `RiggedModel` interface (after `detection_method?: DetectionMethod;`, line ~115) add:

```ts
  used_existing_rig?: boolean;
```

- [ ] **Step 2: Read the editor page's landmark-editor mount + rig metadata display**

Run: `grep -n "LandmarkEditor\|used_existing_rig\|detection_method\|bone_mapping\|RiggedModel\|setRig\|rig\." frontend/src/app/editor/[modelId]/page.tsx | head -40`
Identify (a) where rig metadata/badges render and (b) where `LandmarkEditor` (or the "edit landmarks / re-rig" control) is conditionally rendered.

- [ ] **Step 3: Add the badge and gate the landmark editor**

Where rig metadata renders, add a badge when preserved:

```tsx
{rig?.used_existing_rig && (
  <span className="rounded-full border border-accent/40 bg-accent/10 px-2.5 py-0.5 text-xs text-accent">
    Original rig preserved
  </span>
)}
```

Wrap the landmark-editing UI (the `LandmarkEditor` mount and any "re-rig with landmarks" button) so it only renders when NOT preserved:

```tsx
{!rig?.used_existing_rig && (
  /* existing LandmarkEditor / re-rig controls unchanged */
)}
```

Animation preview and "Download GLB" stay available for preserved rigs — do not gate those.

- [ ] **Step 4: Typecheck + lint**

Run (from `frontend/`): `npx tsc --noEmit && npx eslint src/app/editor/[modelId]/page.tsx src/lib/api.ts`
Expected: clean.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/api.ts "frontend/src/app/editor/[modelId]/page.tsx"
git commit -m "feat(frontend): preserved-rig badge + hide landmark editor for kept rigs

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 10: End-to-end verification (real upload)

**Files:** none.

- [ ] **Step 1: Rebuild the frontend (no live mount)**

```bash
cd rigflow-project && docker compose -f docker/docker-compose.yml up -d --build frontend
```

- [ ] **Step 2: Upload a rigged model + an unrigged model**

Via the upload page (hard-refresh first): upload a rigged GLB (e.g. medieval_guard) and a plain unrigged mesh.

- [ ] **Step 3: Confirm behaviour**

- Rigged upload → editor shows "Original rig preserved", landmark editor hidden, animation preview binds tracks, download works. In admin/DB: `used_existing_rig=True`, `detection_method="preserved"`, `bone_mapping` non-empty, and the AI/vision call did NOT run (rig_log shows the KEEP-RIG lines, no "Vision model returned landmarks").
- Unrigged upload → normal auto-rig path (`used_existing_rig=False`), landmark editor present.

- [ ] **Step 4: If a kept rig deforms wrong, triage `normalize_existing_rig`**

Most likely failure is the scale/transform-apply detaching skin. Check the GLB's skin weights and bone count vs source; fix `normalize_existing_rig` and re-run Task 8's e2e test.

---

## Self-Review

**Spec coverage:**
- §3 auto-detect before strip → Task 4 (branch before `strip_non_meshes`) ✓
- §4.1 `find_skinning_armature` (largest mesh, ≥2 bones, modifier+vgroups) → Task 2 ✓
- §4.2 `normalize_existing_rig` (scale as one unit, feet Z=0, centered) → Task 3 ✓
- §4.3 `build_bone_map_from_existing` + canonical resolver → Tasks 1–2 ✓
- §4.4 `main()` branch → Task 4 ✓
- §5.1 `used_existing_rig` + `"preserved"` choice + migration → Task 5 ✓
- §5.2 Phase-1 `already_rigged` → skip vision; set fields → Task 6 ✓
- §5.3 serializer exposure → Task 7 ✓
- §6 frontend badge + hide landmark editor → Task 9 ✓
- §7 edge cases (multiple armatures, prop-only, no vgroups) → Task 2 logic ✓
- §9 testing (standalone resolver + Blender e2e + prop guard) → Tasks 1, 8 ✓ (prop-only guard is implicit in `find_skinning_armature`; Task 8 covers preserved + unrigged — add a prop-only fixture only if one exists)

**Placeholder scan:** No "TBD"/"implement later". The two implementer notes (Task 3 transform-apply, Task 6 re-indent) point at concrete code with the e2e test as the gate, not vague instructions. Task 9 Step 2/3 say "find the existing pattern" because the editor page's exact JSX is unknown — the grep in Step 2 locates it and Step 3 gives the concrete badge + gate code.

**Type consistency:** `used_existing_rig` (snake_case) consistent across model, serializer, tasks, and the TS field; `detection_method = "preserved"` matches the new choice constant. `find_skinning_armature`/`build_bone_map_from_existing`/`normalize_existing_rig`/`canonical_mixamo_name`/`_run_keep_existing_rig` names are used identically where referenced. `bone_mapping` shape ({Mixamo: bone}) matches `build_bone_map`'s existing output.

One spec gap fixed inline: spec §9 mentions a prop-only guard test; on-disk fixtures may not include a prop-only model, so Task 8 covers preserved + unrigged and the prop-only path is guarded by `find_skinning_armature`'s largest-mesh rule (add a fixture-based test later if a prop-only model is added).

---

## Execution Handoff

Plan saved to `Docs/plans/2026-06-16-preserve-existing-rig.md`. Two execution options:

**1. Subagent-Driven (recommended)** — fresh subagent per task with review between. Tasks 1, 5, 6, 7, 9 are clean for this; Tasks 3, 4, 8, 10 touch Blender and need the running stack, so do them interactively.

**2. Inline Execution** — run the non-Blender tasks here with checkpoints; do the Blender/e2e tasks against the running celery container together.

Which approach?
