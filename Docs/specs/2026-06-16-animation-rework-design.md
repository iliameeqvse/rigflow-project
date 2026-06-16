# Animation Rework — Server-Side Retarget & Bake

**Status:** approved 2026-06-16
**Drives:** fixing broken retargeting + delivering engine-ready animated exports (GLB/FBX)
**Supersedes the exploration in:** [`anim_rework/agy_idea.md`](../anim_rework/agy_idea.md), [`anim_rework/claude_idea.md`](../anim_rework/claude_idea.md), [`anim_rework/codex_idea.md`](../anim_rework/codex_idea.md)

---

## 1. Problem

The animation system is broken in two ways the user feels directly:

1. **Retargeting fails.** Picking almost any library animation in the editor binds **0 tracks** to the rig — the character doesn't move. On the rare clip that binds, the result is **stretched / distorted**.
2. **The download is static.** Even when a preview works, "Download GLB" returns a static T-pose — the animation is never baked into the exported asset.

Root causes, verified against the code (not inferred):

- Retargeting lives **entirely in the browser** (`frontend/src/components/AnimationPlayer.tsx`). It attempts `SkeletonUtils.retargetClip`, silently falls back to a manual quaternion remap, drops all position/scale tracks, and depends on bone-name sanitization round-tripping (`DEF-spine.001` → `DEF-spine001`). Any mismatch in skeleton presence, bone names, or sanitization yields 0 bound tracks. The team already hit this once (the "2/53 bound" note in `sanitizeBoneName`).
- `export_glb()` hard-codes `export_animations=False` (`backend/scripts/blender_autorig.py:1551`); the editor's download is a plain static-file link (`frontend/src/app/editor/[modelId]/page.tsx:247`).
- The frontend already calls `POST /animations/{id}/retarget/` and `POST /projects/{id}/export/` (`frontend/src/lib/api.ts:210,228`), but **neither endpoint exists**: the `animations` app only does list/upload/categories, and the `projects` app is an empty stub (no model, no `urls.py`).
- The bone maps have **already drifted**: server `RIGIFY_TO_MIXAMO` has 22 entries and **no fingers** (`blender_autorig.py:1560`); the client `FALLBACK_MIXAMO_TO_DEF` has fingers plus a heuristic matcher (`AnimationPlayer.tsx:20`). The rig persists a `bone_mapping` field but neither side treats it as the single source of truth.

## 2. Goals

- Retargeting that **actually binds and looks correct** (no twisting/stretching).
- A user can **select several library animations** and **download the rigged character with those animations baked in**, in **GLB and FBX**.
- **One retarget brain**: the server (Blender) is the source of truth; the browser preview consumes the same bone map and converges onto the server result over time.
- Honest **retarget reporting**: what mapped, what dropped, frame range, FPS, format — never a silent failure.

## 3. Non-Goals (out of scope)

- Voxel / geodesic skinning solver. The existing K-nearest soft-falloff fallback (`patch_orphan_vertex_weights`) is adequate; deformation quality is a separate concern.
- IK foot-locking / advanced foot-slide correction (root motion ships later; foot-lock is a future feature).
- A separate `Project` entity — export is rig-scoped (see §7).
- A second retarget vocabulary beyond Mixamo (Unreal Mannequin, etc.).
- Quadrupeds / multi-character / arms-down poses.

## 4. Architecture — one retarget brain, two consumers

```
                ┌──────────────────────────────────────────┐
   rig build →  │ canonical bone_mapping (rig field, JSON)  │
                │  Mixamo/source name → DEF bone, full map   │
                └───────────────┬───────────────┬───────────┘
                                │ (primary truth)│
            ┌───────────────────▼──┐         ┌───▼────────────────────┐
            │ Server baker          │         │ Browser preview         │
            │ blender_retarget.py   │         │ AnimationPlayer.tsx     │
            │ world-rot transfer →  │         │ same map, fixed binding │
            │ nla.bake → export GLB │         │ instant feedback        │
            │ /FBX w/ animations    │         │ (later: plays the bake) │
            └──────────┬────────────┘         └─────────────────────────┘
                       │ download_url + report
                       ▼
                 engine-ready asset (Unity/Unreal/Godot/Blender)
```

The server bake is authoritative. The preview is a convenience layer that is forced to use the *same* bone map and is designed to eventually play the *same baked file*, so "what you see is what you get."

## 5. Canonical bone map contract

- Extend `RIGIFY_TO_MIXAMO` in `blender_autorig.py` to include the **fingers** the client already maps (`thumb`, `f_index`, `f_middle`, `f_ring`, `f_pinky`, segments `.01/.02/.03`, both sides), so `build_bone_map` writes a **complete** map into the rig's `bone_mapping`.
- **Both** the server baker and the browser preview consume `rig.bone_mapping` as primary truth. The hardcoded `FALLBACK_MIXAMO_TO_DEF` / `RIGIFY_TO_MIXAMO` tables and the client heuristic matcher remain **only** as fallbacks for legacy rigs whose `bone_mapping` is empty; the report flags when a fallback was used.
- **Parity test (golden file):** for a reference rig, assert the client resolver and the server map resolve to the *same* DEF bone for every source name, and that the names survive three.js `PropertyBinding` sanitization identically on both sides. This is the structural guard against the drift that exists today.

## 6. Server retarget + bake — `blender_retarget.py`

A focused new Blender script, separate from the 2,300-line `blender_autorig.py` (single responsibility; shared helpers imported, not duplicated).

Responsibilities:
1. Load the rigged GLB (DEF skeleton + skinned mesh).
2. Import each selected animation clip (GLB/GLTF/FBX).
3. For each clip, resolve source bones → DEF bones via the canonical `bone_mapping`.
4. **Transfer source world-space bone rotations onto the DEF skeleton, rebased into DEF local space using both rest poses** — the same semantics as `SkeletonUtils.retargetClip`. This is what corrects bone-roll/rest-pose mismatch (the "stretched/twisted" symptom). Rest-pose offsets are derived at bake time from the rig GLB's rest pose and the clip's rest pose — no extra stored calibration data required.
5. `bpy.ops.nla.bake` to keyframes; one **named action / NLA track per selected clip** (multi-clip bundle).
6. Export with `export_animations=True` to GLB (and FBX in milestone 2).
7. Emit a **retarget report** (§8) as sidecar JSON.

Multi-clip: the user selects N clips → one output file containing N named animations.

CLI shape (argparse, mirrors autorig conventions): `--rig <glb> --clips <json list of {id,path,name}> --format glb|fbx --output <path> --bone-map <json> --report-out <path>`.

## 7. Export job model + endpoint (rig-scoped)

No `Project` model. Export is an action on the existing rig.

**New model `AnimationExport`** (in the `rigging` app), mirroring `RiggedModel`'s status lifecycle:

```
id            UUID
rig           → rigging.RiggedModel
animation_ids JSON (list of Animation UUIDs, order preserved)
format        "glb" | "fbx"
status        "pending" | "processing" | "done" | "failed"
output_file   FileField (the baked asset)
report        JSON (retarget report, §8)
cache_key     char  (hash of rig_id + sorted(animation_ids) + format + rig.updated_at)
celery_task_id char
error_message text
created_at, updated_at
```

**Endpoints** (actions on `RiggedModelViewSet`, auth required, reuse `rig_upload`-class throttling):

- `POST /api/v1/rigs/{id}/export/` — body `{ "animation_ids": [...], "format": "glb"|"fbx" }`.
  - If a `done` `AnimationExport` with a matching `cache_key` exists, return it immediately (cache hit).
  - Otherwise create the row, queue a Celery bake task, return `202` with `{ export_id, status: "pending" }`.
- `GET /api/v1/rigs/{id}/exports/{export_id}/` — poll: `{ status, progress, download_url, report, error_message }`. Public-read consistent with `/status/`.

**Celery task** reuses the existing harness: `_blender_call(cmd, timeout=600, cwd=...)`, `push_ws(user_id, ...)` progress, the `rigging` queue, and the `failed`-on-error semantics already used by `_run_rig_pipeline`. On success, save `output_file` + `report`, set `status="done"`.

**Client contract change:** repoint `exportProject(projectId, format)` → `exportRig(rigId, { animation_ids, format })`; add `getExport(rigId, exportId)` polling. `retargetAnimation()` is removed — preview does not need a server call in milestones 0–1; convergence (milestone 4) replaces it with "fetch cached bake."

## 8. Retarget report schema

Returned by the baker and stored on `AnimationExport.report`; surfaced in the editor.

```json
{
  "format": "glb",
  "fps": 30,
  "clips": [
    {
      "id": "uuid", "name": "Walk",
      "frame_range": [0, 32],
      "bones_mapped": 53, "bones_total": 65,
      "unmapped_bones": ["mixamorig:HeadTop_End"],
      "dropped_tracks": ["mixamorig:Hips.scale"],
      "used_fallback_map": false,
      "root_motion": "stripped"
    }
  ],
  "warnings": []
}
```

`root_motion` ∈ `stripped` | `kept_scaled` | `disabled` (becomes meaningful in milestone 3).

## 9. Preview: fix now, converge later

- **Milestone 0 fix:** make the browser preview actually bind — consume `rig.bone_mapping` as primary truth, guarantee sanitization parity with the loader, and correct the scaling that produces "stretched." Keep the existing bound-track report visible.
- **Milestone 4 convergence:** the preview requests a cached server bake and *plays that GLB directly*. Preview and export become the same code path → zero drift by construction. Instant-feel is preserved via the export cache.

## 10. Data flow

```
Editor: select rig + several clips + GLB|FBX
  → POST /rigs/{id}/export/ { animation_ids, format }
  → (cache hit? return done export)
  → Celery bake: blender_retarget.py
        import clips → world-rot transfer onto DEF (bone_mapping + rest offsets)
        → nla.bake (one action per clip) → export with animations → report
  → AnimationExport: pending → processing → done
  → poll GET /rigs/{id}/exports/{export_id}/ → download_url + report
Preview (browser): same bone_mapping, fixed binding; later plays the cached bake
```

## 11. Milestones (sequencing)

0. **Fix preview + ship the canonical bone map.** Diagnose the 0-tracks/stretch root cause; complete `RIGIFY_TO_MIXAMO` (fingers); make both sides consume `rig.bone_mapping`; add the parity golden test. *(Addresses the acute pain first.)*
1. **Animated GLB export spine.** `AnimationExport` model + migration; `POST /rigs/{id}/export/` + poll endpoint; `blender_retarget.py` (multi-clip, GLB); report; editor "Export" UI with clip multi-select and progress.
2. **FBX export.** Second format with its own axis/unit/scale fixtures and engine-import sanity check.
3. **Root motion.** Preserve only root/hips translation, scaled by **leg-length ratio** (not total height), applied identically in bake and preview; reported per clip.
4. **Converge preview onto the bake.** Preview plays the cached server-baked GLB; remove the divergent client retarget path.

Each milestone is independently shippable and testable.

## 12. Risks & mitigations

| Risk | Why it bites | Mitigation |
|---|---|---|
| Preview/export drift | Two engines, two maps → preview right, export wrong, trust lost | One generated `bone_mapping`; parity golden test; converge (M4) |
| Bake latency / cost | Headless Blender is CPU/RAM heavy; users queue | Celery `rigging` queue + 600s timeout (exist); cache by `cache_key` |
| Rest-pose / bone-roll mismatch | Rigify DEF rolls differ from source skeleton | World-rotation rebase at bake time (matches three.js retarget) |
| Bone-name sanitization | three.js strips `.` `:` `[` `]` `/` → silent unbind | Assert round-trip in the parity test; baker emits names that survive it |
| FBX axis/unit quirks | Blender FBX export differs from GLB | GLB first (M1); FBX isolated to M2 with fixtures |
| Clip with no usable skeleton | Uploaded file has no armature animation | Validate; report; fail with a useful message, never a silent static export |
| Large clips / memory | Long clips → huge keyframe data | Resample to standard FPS; expose duration/FPS in report; cap in v1 |

## 13. Open decisions (resolved)

- **Export scope:** multi-clip bundle (user selects several). ✓
- **Formats:** GLB then FBX, both in scope. ✓
- **Project vs rig-scoped:** rig-scoped `/rigs/{id}/export/`; no `Project` model. ✓
- **Preview strategy:** keep instant preview now (fixed), converge onto server bake later. ✓

## 14. Cross-references

- [`anim_rework/claude_idea.md`](../anim_rework/claude_idea.md), [`anim_rework/codex_idea.md`](../anim_rework/codex_idea.md) — proposals this spec consolidates.
- [`RIGGING_PIPELINE.md`](../RIGGING_PIPELINE.md) — bone mapping, DEF-stripping, the Blender subprocess harness.
- [`ARCHITECTURE.md`](../ARCHITECTURE.md) — `RiggedModel`, Celery queues, WS progress.
- [`API.md`](../API.md) — endpoint conventions, throttle table.
