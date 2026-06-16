# Animation Rework — Milestone 1: Server-Side Bake & Export — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a user select one or more library animations and download their rigged character with those animations baked in — produced by a server-side Blender retarget that uses proper rest-pose calibration, fixing the client preview's leg-flip/twist artifacts.

**Architecture:** A new `blender_retarget.py` loads the rigged GLB + each animation clip, pairs bones through the rig's saved `bone_mapping` (Mixamo↔target), transfers each source bone's motion as a **delta from its own rest pose** onto the target bone's rest (the rest-pose-correct transfer), `nla.bake`s keyframes, and exports a GLB with `export_animations=True`. A rig-scoped `POST /rigs/{id}/export/` creates an `AnimationExport` row and runs the bake on Celery (reusing the existing Blender harness); the editor polls it, then plays/downloads the baked GLB.

**Tech Stack:** Blender `bpy`/`mathutils` (headless), Django 5.1 / DRF / Celery, Next.js 16 / React 19 / three.

**Spec:** [`Docs/specs/2026-06-16-animation-rework-design.md`](../specs/2026-06-16-animation-rework-design.md) (Milestone 1: §6 baker, §7 model+endpoint, §8 report).

**Scope (this milestone):** GLB output, multi-clip, in-place (no root motion). **Deferred:** FBX (M2), leg-length root motion (M3), full preview→bake convergence (M4 — but this plan adds a "play the baked GLB" affordance so the user immediately sees correct animation).

**Path conventions:** Paths relative to `rigflow-project/`. Backend commands from `rigflow-project/backend/` using the repo venv `C:/Users/dzodz/OneDrive/Desktop/Rigflow/venv/Scripts/python.exe`. Blender-running tasks use the **celery container** (has Blender); validate there. Branch `main` (commit approved). Migrations must be applied to BOTH local SQLite (venv) and Docker Postgres (`docker compose ... exec web python manage.py migrate`). End commit messages with: `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`

---

## File Structure

| File | Responsibility | Action |
|---|---|---|
| `backend/scripts/blender_retarget.py` | NEW Blender script: load rig + clips, rest-pose-aware retarget, `nla.bake`, export animated GLB, write report. | Create |
| `backend/scripts/_test_retarget_pairs.py` | Standalone (stubbed-bpy) test for the pure bone-pairing helper. | Create |
| `backend/apps/rigging/models.py` | `AnimationExport` model. | Modify |
| `backend/apps/rigging/migrations/000N_animationexport.py` | Migration. | Create |
| `backend/apps/rigging/serializers.py` | `AnimationExportSerializer`. | Modify |
| `backend/apps/rigging/tasks.py` | `bake_animation_export` Celery task + `_run_bake_pipeline` driver. | Modify |
| `backend/apps/rigging/views.py` | `export` + `export_status` actions on the viewset. | Modify |
| `backend/apps/rigging/tests/test_retarget_e2e.py` | Blender-gated e2e: bake produces an animated GLB. | Create |
| `frontend/src/lib/api.ts` | `exportRig`, `getExport`, `AnimationExport` type. | Modify |
| `frontend/src/app/editor/[modelId]/page.tsx` | Clip multi-select + Export + progress + download + "play baked" in the animation panel. | Modify |

---

### Task 1: Pure bone-pairing helper (`pair_bones_by_mixamo`) — TDD, no Blender

The retarget needs `(target_bone, source_bone)` pairs derived from the rig's `bone_mapping` ({Mixamo: targetBone}) and the source clip's bone names. This pairing is pure logic.

**Files:**
- Create: `backend/scripts/_test_retarget_pairs.py`
- Create: `backend/scripts/blender_retarget.py` (just this helper for now)

- [ ] **Step 1: Write the failing standalone test** `backend/scripts/_test_retarget_pairs.py`:

```python
"""Standalone test for pair_bones_by_mixamo. No Blender. Run from backend/:
    python scripts/_test_retarget_pairs.py
"""
import importlib.util, sys
from pathlib import Path

stub_mu = type(sys)("mathutils"); stub_mu.Vector = tuple; stub_mu.Quaternion = object; stub_mu.Matrix = object
sys.modules["mathutils"] = stub_mu
sys.modules["bpy"] = type(sys)("bpy")

# blender_retarget imports canonical_mixamo_name from blender_autorig; make
# both importable from the scripts dir.
sys.path.insert(0, str(Path(__file__).parent))
spec = importlib.util.spec_from_file_location(
    "blender_retarget", Path(__file__).parent / "blender_retarget.py")
mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)

# bone_mapping: {Mixamo: targetBone}. source clip bone names use mixamorig.
bone_mapping = {"Hips": "DEF-spine", "LeftArm": "DEF-upper_arm.L", "Head": "DEF-spine.005"}
source_bones = ["mixamorig:Hips", "mixamorig:LeftArm", "mixamorig:Head", "mixamorig:Spine"]
pairs = mod.pair_bones_by_mixamo(bone_mapping, source_bones)
got = dict(pairs)
assert got == {"DEF-spine": "mixamorig:Hips",
               "DEF-upper_arm.L": "mixamorig:LeftArm",
               "DEF-spine.005": "mixamorig:Head"}, got
# Source bone with no mapping target is skipped (Spine not in bone_mapping).
assert all(s != "mixamorig:Spine" for _, s in pairs)
print("pair_bones_by_mixamo: OK")
```

- [ ] **Step 2: Run it; verify it fails** (from `backend/`):
`python scripts/_test_retarget_pairs.py` → fails (module/function missing).

- [ ] **Step 3: Create `backend/scripts/blender_retarget.py` with the helper + import shim**

```python
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
from mathutils import Matrix  # noqa: F401  (used in later tasks)

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
```

- [ ] **Step 4: Run it; verify it passes** → `pair_bones_by_mixamo: OK`.

- [ ] **Step 5: Commit**

```bash
git add backend/scripts/blender_retarget.py backend/scripts/_test_retarget_pairs.py
git commit -m "feat(anim): blender_retarget.py skeleton + pure bone-pairing helper

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: The rest-pose-aware bake in `blender_retarget.py`

bpy-bound; validated by Task 8's container run. This is the crux that fixes the leg-flip.

**Files:**
- Modify: `backend/scripts/blender_retarget.py`

- [ ] **Step 1: Add CLI parsing + scene helpers**

Append to `blender_retarget.py`:

```python
def _argv_after_dashes():
    return sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--rig", required=True, help="Path to the rigged GLB.")
    p.add_argument("--clips", required=True,
                   help='JSON list: [{"id","name","path","format"}].')
    p.add_argument("--output", required=True, help="Destination animated GLB.")
    p.add_argument("--bone-map", required=True,
                   help="Path to the rig bone_mapping JSON ({Mixamo: targetBone}).")
    p.add_argument("--report-out", default=None, help="Where to write the report JSON.")
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
```

- [ ] **Step 2: Add the per-clip retarget+bake**

```python
def retarget_clip_onto(target_arm, source_arm, pairs, action):
    """Bake `action` (playing on source_arm) onto target_arm using rest-pose
    deltas. For each frame and each (tgt, src) bone pair:
        delta = src_pose_armspace @ src_rest_armspace.inverted()
        tgt_pose_armspace = delta @ tgt_rest_armspace
    then set the target pose bone's matrix and keyframe its rotation. Rotation
    only (root motion is a later milestone). Returns the number of bones driven.
    """
    scene = bpy.context.scene
    src_action = action
    if not source_arm.animation_data:
        source_arm.animation_data_create()
    source_arm.animation_data.action = src_action

    f_start = int(src_action.frame_range[0])
    f_end = int(src_action.frame_range[1])

    # Rest matrices in armature (object) space.
    tgt_rest = {t: target_arm.data.bones[t].matrix_local
                for t, _ in pairs if t in target_arm.data.bones}
    src_rest = {s: source_arm.data.bones[s].matrix_local
                for _, s in pairs if s in source_arm.data.bones}

    valid = [(t, s) for (t, s) in pairs if t in tgt_rest and s in src_rest]

    bpy.context.view_layer.objects.active = target_arm
    bpy.ops.object.mode_set(mode="POSE")

    for frame in range(f_start, f_end + 1):
        scene.frame_set(frame)
        for t, s in valid:
            src_pb = source_arm.pose.bones[s]
            tgt_pb = target_arm.pose.bones[t]
            delta = src_pb.matrix_basis_to_armature() if False else (
                src_pb.matrix @ src_rest[s].inverted())
            tgt_world = delta @ tgt_rest[t]
            # Keep the target bone's rest translation; only take rotation.
            loc = tgt_rest[t].to_translation()
            rot = tgt_world.to_3x3().to_4x4()
            tgt_pb.matrix = Matrix.Translation(loc) @ rot
            tgt_pb.keyframe_insert(data_path="rotation_quaternion", frame=frame)

    bpy.ops.object.mode_set(mode="OBJECT")
    return len(valid)
```

> **Implementer note (validate, don't trust):** the exact mathutils expression for "source pose delta in armature space" must be confirmed against a real Blender run (Task 8). `pose_bone.matrix` is armature-space; `bone.matrix_local` is the armature-space rest. The intended math is `tgt_pose = (src_pose @ src_rest⁻¹) @ tgt_rest`. If the legs still flip in Task 8, the bug is here — iterate on this matrix expression (e.g. whether to compose in world space via `armature.matrix_world`, or operate on `rotation_quaternion` basis) until the container run produces a correct walk. Do NOT move on from Task 8 until the baked GLB animates correctly.

- [ ] **Step 3: Add `main()`**

```python
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
    baked_any = False
    for clip in clips:
        src_objs = _import_any(clip["path"], clip.get("format"))
        source_arm = _first_armature(src_objs)
        if source_arm is None or not source_arm.animation_data \
                or not source_arm.animation_data.action:
            report["warnings"].append(f"clip {clip['name']}: no armature/action")
            for o in src_objs:
                bpy.data.objects.remove(o, do_unlink=True)
            continue
        action = source_arm.animation_data.action
        src_names = [b.name for b in source_arm.data.bones]
        pairs = pair_bones_by_mixamo(bone_mapping, src_names)
        driven = retarget_clip_onto(target_arm, source_arm, pairs, action)

        # Stash the baked action under a clip-named action so multiple clips
        # become multiple named animations in the export.
        if target_arm.animation_data and target_arm.animation_data.action:
            target_arm.animation_data.action.name = clip["name"]
        report["clips"].append({
            "id": clip.get("id"), "name": clip["name"],
            "bones_driven": driven, "bones_total": len(src_names),
            "frame_range": [int(action.frame_range[0]), int(action.frame_range[1])],
        })
        baked_any = True
        # Remove the source so the next clip imports cleanly; the baked action
        # stays on target_arm.
        for o in src_objs:
            bpy.data.objects.remove(o, do_unlink=True)

    if not baked_any:
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
        import traceback; traceback.print_exc()
        sys.exit(1)
```

> **Multi-clip note:** baking several actions into one GLB and keeping them as separate named animations may need NLA push-down per clip rather than overwriting `animation_data.action`. If the export only contains the last clip, push each baked action to an NLA strip before the next clip. Confirm in Task 8 with a 2-clip export; fix here if only one animation survives.

- [ ] **Step 4: Syntax check** (from `backend/`):
`python -c "import ast,io; ast.parse(io.open('scripts/blender_retarget.py',encoding='utf-8').read()); print('OK')"` and re-run `python scripts/_test_retarget_pairs.py`.

- [ ] **Step 5: Commit**

```bash
git add backend/scripts/blender_retarget.py
git commit -m "feat(anim): rest-pose-aware retarget + bake in blender_retarget.py

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: `AnimationExport` model + migration

**Files:**
- Modify: `backend/apps/rigging/models.py`
- Create migration.

- [ ] **Step 1: Add the model** at the end of `backend/apps/rigging/models.py`:

```python
class AnimationExport(models.Model):
    STATUS_PENDING = "pending"
    STATUS_PROCESSING = "processing"
    STATUS_DONE = "done"
    STATUS_FAILED = "failed"
    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"), (STATUS_PROCESSING, "Processing"),
        (STATUS_DONE, "Done"), (STATUS_FAILED, "Failed"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    rig = models.ForeignKey(
        "RiggedModel", on_delete=models.CASCADE, related_name="exports")
    animation_ids = models.JSONField(default=list)   # ordered Animation UUIDs
    export_format = models.CharField(max_length=8, default="glb")
    status = models.CharField(max_length=16, choices=STATUS_CHOICES,
                              default=STATUS_PENDING, db_index=True)
    output_file = models.FileField(upload_to="exports/", blank=True)
    report = models.JSONField(null=True, blank=True)
    cache_key = models.CharField(max_length=64, blank=True, db_index=True)
    celery_task_id = models.CharField(max_length=255, blank=True)
    error_message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
```

(`uuid` and `models` are already imported at the top of the file.)

- [ ] **Step 2: Migrate both DBs**

```bash
cd backend
"C:/Users/dzodz/OneDrive/Desktop/Rigflow/venv/Scripts/python.exe" manage.py makemigrations rigging
"C:/Users/dzodz/OneDrive/Desktop/Rigflow/venv/Scripts/python.exe" manage.py migrate rigging
```
Then Postgres: `docker compose -f docker/docker-compose.yml exec -T web python manage.py migrate rigging`. Expected: applies cleanly in both.

- [ ] **Step 3: `manage.py check`** → no issues.

- [ ] **Step 4: Commit** (model + migration).

---

### Task 4: `AnimationExportSerializer` + cache key helper

**Files:**
- Modify: `backend/apps/rigging/serializers.py`

- [ ] **Step 1: Add the serializer**

```python
class AnimationExportSerializer(serializers.ModelSerializer):
    download_url = serializers.SerializerMethodField()

    class Meta:
        model = RiggedModel  # placeholder corrected below
```

Replace `model = RiggedModel` with `from .models import AnimationExport` at the top and `model = AnimationExport`, fields `["id", "rig", "animation_ids", "export_format", "status", "download_url", "report", "error_message", "created_at"]`, all read-only. `get_download_url` mirrors `get_rigged_glb_url`:

```python
    def get_download_url(self, obj) -> str | None:
        if obj.output_file:
            request = self.context.get("request")
            return request.build_absolute_uri(obj.output_file.url) if request else obj.output_file.url
        return None
```

- [ ] **Step 2: Verify** `manage.py check` → no issues. **Commit.**

---

### Task 5: `_run_bake_pipeline` + `bake_animation_export` Celery task

**Files:**
- Modify: `backend/apps/rigging/tasks.py`

- [ ] **Step 1: Add a cache-key helper + the driver**

Add to `tasks.py` (reuse `_blender_call`, `push_ws`, `settings.BLENDER_*`):

```python
import hashlib

def make_export_cache_key(rig, animation_ids, fmt):
    rig_stamp = rig.updated_at.isoformat() if rig.updated_at else ""
    raw = f"{rig.id}|{sorted(map(str, animation_ids))}|{fmt}|{rig_stamp}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def _run_bake_pipeline(export_id: str) -> dict:
    import json, tempfile
    from pathlib import Path
    from django.core.files import File
    from .models import AnimationExport, RiggedModel
    from apps.animations.models import Animation

    exp = AnimationExport.objects.select_related("rig").get(id=export_id)
    rig = exp.rig
    exp.status = "processing"; exp.save(update_fields=["status"])
    user_id = str(rig.user.user_id) if rig.user else ""
    push_ws(user_id, {"export_id": export_id, "step": "Baking animation…", "pct": 20})
    try:
        if not rig.rigged_glb:
            raise RuntimeError("Rig has no rigged GLB to animate")
        anims = list(Animation.objects.filter(id__in=exp.animation_ids))
        order = {str(a.id): i for i, a in enumerate(exp.animation_ids)}
        anims.sort(key=lambda a: order.get(str(a.id), 0))
        if not anims:
            raise RuntimeError("No valid animations selected")

        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            rig_path = tmp / "rig.glb"
            rig_path.write_bytes(rig.rigged_glb.read())
            bone_map_path = tmp / "bone_map.json"
            bone_map_path.write_text(json.dumps(rig.bone_mapping or {}))
            clips = []
            for a in anims:
                ext = a.gltf_file.name.split(".")[-1].lower()
                cp = tmp / f"clip_{a.id}.{ext}"
                cp.write_bytes(a.gltf_file.read())
                clips.append({"id": str(a.id), "name": a.name, "path": str(cp), "format": ext})
            clips_path = tmp / "clips.json"
            clips_path.write_text(json.dumps(clips))
            out_path = tmp / "animated.glb"
            report_path = tmp / "report.json"

            script = settings.BLENDER_SCRIPTS_DIR / "blender_retarget.py"
            cmd = [settings.BLENDER_EXECUTABLE, "--background", "--python", str(script), "--",
                   "--rig", str(rig_path), "--clips", str(clips_path),
                   "--output", str(out_path), "--bone-map", str(bone_map_path),
                   "--report-out", str(report_path)]
            rc, out, err = _blender_call(cmd, timeout=600,
                                         cwd=str(settings.BLENDER_SCRIPTS_DIR.parent))
            if rc != 0 or not out_path.exists():
                raise RuntimeError(f"Bake failed (rc={rc}). {err[-500:]}")
            with open(out_path, "rb") as f:
                exp.output_file.save(f"{exp.id}.glb", File(f), save=False)
            if report_path.exists():
                exp.report = json.loads(report_path.read_text())
        exp.status = "done"; exp.save()
        push_ws(user_id, {"export_id": export_id, "step": "Done", "pct": 100})
        return {"status": "done", "export_id": export_id}
    except Exception as e:
        logger.exception("Bake failed for export %s: %s", export_id, e)
        exp.status = "failed"; exp.error_message = str(e)[:2000]; exp.save()
        push_ws(user_id, {"export_id": export_id, "status": "failed", "error": str(e)})
        return {"status": "failed", "export_id": export_id}
```

> Verify the WS user id expression against how `push_ws`/`_run_rig_pipeline` resolve it (read the top of `tasks.py`); use the SAME pattern. `Animation.gltf_file` and `RiggedModel.rigged_glb` are FileFields — `.read()` after opening / on the field works in Django storage; if `.read()` returns empty, use `.open("rb")`.

- [ ] **Step 2: Add the Celery task**

```python
@shared_task(name="rigging.bake_animation_export")
def bake_animation_export(export_id: str) -> dict:
    return _run_bake_pipeline(export_id)
```

- [ ] **Step 3: Syntax check + `manage.py check`. Commit.**

---

### Task 6: `export` + `export_status` endpoints

**Files:**
- Modify: `backend/apps/rigging/views.py`

- [ ] **Step 1: Add the actions to `RiggedModelViewSet`**

```python
    @action(detail=True, methods=["post"], url_path="export")
    def export(self, request, id=None):
        try:
            rig = RiggedModel.objects.get(id=id)
        except RiggedModel.DoesNotExist:
            return Response({"error": "Rig not found."}, status=status.HTTP_404_NOT_FOUND)
        animation_ids = request.data.get("animation_ids") or []
        fmt = (request.data.get("format") or "glb").lower()
        if not isinstance(animation_ids, list) or not animation_ids:
            return Response({"error": "animation_ids (non-empty list) required."},
                            status=status.HTTP_400_BAD_REQUEST)
        if fmt != "glb":
            return Response({"error": "Only 'glb' is supported in this version."},
                            status=status.HTTP_400_BAD_REQUEST)
        from .models import AnimationExport
        from .tasks import bake_animation_export, make_export_cache_key
        key = make_export_cache_key(rig, animation_ids, fmt)
        cached = AnimationExport.objects.filter(
            rig=rig, cache_key=key, status="done").first()
        if cached:
            return Response(self.get_serializer_export(cached, request),
                            status=status.HTTP_200_OK)
        exp = AnimationExport.objects.create(
            rig=rig, animation_ids=[str(a) for a in animation_ids],
            export_format=fmt, cache_key=key, status="pending")
        bake_animation_export.delay(str(exp.id))
        return Response(self.get_serializer_export(exp, request),
                        status=status.HTTP_202_ACCEPTED)

    @action(detail=True, methods=["get"],
            url_path=r"exports/(?P<export_id>[0-9a-f-]+)",
            permission_classes=[AllowAny], authentication_classes=[])
    def export_status(self, request, id=None, export_id=None):
        from .models import AnimationExport
        try:
            exp = AnimationExport.objects.get(id=export_id, rig_id=id)
        except AnimationExport.DoesNotExist:
            return Response({"error": "Export not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(self.get_serializer_export(exp, request))

    def get_serializer_export(self, exp, request):
        from .serializers import AnimationExportSerializer
        return AnimationExportSerializer(exp, context={"request": request}).data
```

- [ ] **Step 2: Throttle** — add `export` to `RigUploadThrottle` in `get_throttles` (Blender-heavy): change `if self.action in ("rerig", "rerig_landmarks"):` to include `"export"`. Add `"export_status"` to the no-throttle + public auth/permission sets alongside `"status_action"` in `get_permissions`, `get_authenticators`, `get_throttles`, `get_queryset`.

- [ ] **Step 3: Smoke test** (container, after Task 8's bake works):
```bash
docker compose -f docker/docker-compose.yml exec -T web python manage.py shell -c "..."
```
create an export via the task and confirm a row + download_url. **Commit.**

---

### Task 7: Frontend — export UI in the editor

**Files:**
- Modify: `frontend/src/lib/api.ts`
- Modify: `frontend/src/app/editor/[modelId]/page.tsx`

- [ ] **Step 1: api.ts** — add types + calls:

```ts
export interface AnimationExport {
  id: string; status: "pending" | "processing" | "done" | "failed";
  download_url: string | null; report: unknown; error_message?: string;
  animation_ids: string[]; export_format: string;
}
export const exportRig = (rigId: string, animationIds: string[], format: "glb" = "glb") =>
  api.post<AnimationExport>(`/rigs/${rigId}/export/`, { animation_ids: animationIds, format });
export const getExport = (rigId: string, exportId: string) =>
  api.get<AnimationExport>(`/rigs/${rigId}/exports/${exportId}/`);
```
Remove the obsolete `exportProject`/`retargetAnimation` exports (no backend) — grep for their usages first and delete those too.

- [ ] **Step 2: editor page** — in the animation ("play") panel, add: a multi-select list of library animations (reuse the `listAnimations` data the `AnimationPlayer` already loads, or fetch here), an "Export with animations" button calling `exportRig`, a poll loop on `getExport` showing progress, and on `done` a **Download** link (`download_url`) plus a **"Play baked result"** button that loads `download_url` into the existing `AnimationPlayer`/viewer so the user sees the correct (server-baked) animation. Keep it minimal and match the page's existing styling.

- [ ] **Step 3: typecheck + lint** (`npx tsc --noEmit`, `npx eslint`). **Commit.**

---

### Task 8: Blender-gated e2e + manual correctness validation *(the gate for Task 2)*

**Files:**
- Create: `backend/apps/rigging/tests/test_retarget_e2e.py`

- [ ] **Step 1: First validate the bake by hand in the celery container** against a real rig + clip (this is where you iterate on Task 2's matrix math until the animation is correct):

```bash
docker compose -f docker/docker-compose.yml exec -T celery sh -c '
RIG=$(find /app/media -name "*_rigged.glb" | head -1)
CLIP=/app/media/animations/library/Sword_And_Shield_Impact.fbx
echo "{\"DEF-spine\":\"DEF-spine\"}" > /tmp/bm.json   # use a REAL bone_map from a rig row
echo "[{\"id\":\"x\",\"name\":\"t\",\"path\":\"$CLIP\",\"format\":\"fbx\"}]" > /tmp/clips.json
/usr/local/bin/blender --background --python /app/scripts/blender_retarget.py -- \
  --rig "$RIG" --clips /tmp/clips.json --output /tmp/anim.glb \
  --bone-map /tmp/bm.json --report-out /tmp/rep.json 2>&1 | tail -20
'
```
Pull a REAL `bone_mapping` from a rig row for `/tmp/bm.json`. Inspect `/tmp/anim.glb` (GLB JSON: `animations` length ≥ 1, channels target the rig joints). **Open it (download to host, view in the editor or a glTF viewer) and confirm the legs do NOT flip.** Iterate on `retarget_clip_onto`'s matrix expression until correct. This is the milestone's whole point — do not skip.

- [ ] **Step 2: Write the e2e test** asserting the bake produces a GLB with ≥1 animation:

```python
class RetargetBakeE2ETest(TestCase):
    def test_bake_produces_animated_glb(self):
        from django.conf import settings
        from pathlib import Path
        if not Path(settings.BLENDER_EXECUTABLE).is_file():
            self.skipTest("Blender not installed")
        # Build a rig row with a real rigged GLB + a library Animation, run
        # _run_bake_pipeline, assert export.status == "done", output_file set,
        # and report["clips"][0]["bones_driven"] > 0.
```
Flesh out using `_make_rig` patterns from `test_e2e_pipeline.py` and an `Animation` fixture pointing at a library FBX on disk; skip if absent.

- [ ] **Step 3: Run it in the container.** Skip-or-pass acceptable; FAIL is not. **Commit.**

---

### Task 9: End-to-end manual verification

**Files:** none.

- [ ] Rebuild frontend (`docker compose ... up -d --build frontend`), hard-refresh. On a rig (preserved or Rigify), select 1–2 animations, Export, wait, **Play baked result** → the character animates correctly (legs no longer fold up). Download the GLB; open in a glTF viewer/engine and confirm the animation is embedded and correct. Try a 2-clip export → both animations present.

---

## Self-Review

**Spec coverage (M1, §6/§7/§8/§11):**
- §6 baker (load rig + clips, rest-pose-correct transfer, nla.bake, export w/ animations) → Tasks 1, 2, 8 ✓
- §7 `AnimationExport` model + rig-scoped `POST /export/` + poll + cache → Tasks 3, 4, 6 ✓
- §7 Celery bake reusing the harness → Task 5 ✓
- §8 retarget report (clips, bones, frame range) → Task 2 (report dict) + Task 4 (exposed) ✓
- §11 multi-clip, GLB-only, in-place → Tasks 2/5/6 (FBX rejected with 400; root motion absent) ✓
- Preserved-rig compatibility → baker keys off `bone_mapping`, which both rig types populate (M0 + preserve-rig); the pairing test uses DEF names, real runs use whatever the rig has ✓
- User-visible correctness (the leg-flip) → Task 7 "Play baked result" + Task 8/9 validation ✓

**Placeholder scan:** The two Blender notes (Task 2 matrix math, multi-clip NLA) are explicit "validate in Task 8 and iterate" instructions with the concrete intended math, not vague TODOs — this is the honest shape for bpy code that can't be unit-verified. Task 4's serializer has a deliberately-flagged `model = RiggedModel` placeholder line immediately corrected in the same step. Task 7 Step 2 describes the UI against the page's known structure (tabs + AnimationPlayer) rather than inventing exact JSX, since the editor page's animation panel must be read first.

**Type consistency:** `pair_bones_by_mixamo(bone_mapping, source_bone_names)` signature matches its test and `main()` call; `AnimationExport` field names (`animation_ids`, `export_format`, `output_file`, `cache_key`, `report`) are identical across model, serializer, task, and views; `make_export_cache_key(rig, animation_ids, fmt)` matches its call site; endpoint shapes (`/rigs/{id}/export/`, `/rigs/{id}/exports/{export_id}/`) match `exportRig`/`getExport`.

**Known risk called out:** Task 2's retarget math is the single highest-risk item and the milestone's whole purpose; Task 8 Step 1 is its hard gate (must produce a visibly-correct animation before proceeding).

---

## Execution Handoff

Plan saved to `Docs/plans/2026-06-16-animation-rework-m1.md`. The Blender bake (Tasks 2 & 8) needs the celery container and iterative validation — best done interactively, not by a blind subagent. Two options:

**1. Subagent-Driven** — subagents for Tasks 1, 3, 4, 5, 6, 7 (model/endpoint/serializer/frontend); Tasks 2 & 8 (the baker + its correctness gate) done interactively together.

**2. Inline** — run the clean tasks here with checkpoints; do the baker + container validation together.

Which approach?
