# Rigging Pipeline

The Blender automation is the heart of RigFlow. This doc covers what the script actually does, how landmarks are placed, how the two rerig flows differ, and what to look at when output is wrong.

Source files:

- `backend/apps/rigging/views.py` — HTTP entrypoints.
- `backend/apps/rigging/tasks.py` — pipeline driver, calls Blender as a subprocess.
- `backend/scripts/blender_autorig.py` — runs **inside Blender**, uses the `bpy` API.

## Trigger paths

| Endpoint | Body | Behaviour |
|---|---|---|
| `POST /rigs/` | multipart, `file` + optional rotation | New `RiggedModel` row, run pipeline. |
| `POST /rigs/{id}/rerig/` | empty | Reset status, re-run on the original file. |
| `POST /rigs/{id}/rerig-landmarks/` | `{ landmarks: {...} }` | Reset status, re-run with user-placed landmarks. Returns 202 immediately. |

All three call `auto_rig_model.delay(...)` (Celery). Locally, `CELERY_TASK_ALWAYS_EAGER=True` makes it run in-process, so the call blocks the request thread. In Docker the worker picks it up.

For each one, the underlying driver is `tasks._run_rig_pipeline(rig_id, ...)`. It is a plain function (not `@shared_task`) so it can be invoked directly from views, threads, or task wrappers without Celery's `self`/bind plumbing.

## What the pipeline does

1. **Move row to `processing`**. Push a `progress` event via Channels to group `user_{user_id}`.
2. **Write the upload to a temp dir.** Blender works on disk, not file-like objects.
3. **Spawn Blender headlessly:**

   ```
   blender --background --python backend/scripts/blender_autorig.py -- \
       --input         <tmp>/<original>.<ext> \
       --output        <tmp>/rigged.glb \
       --bones         <tmp>/bones.json \
       --pose          <tmp>/pose.json \
       --landmarks-out <tmp>/landmarks.json \
       --format        <ext> \
       [--initial-rotation-x ° --initial-rotation-y ° --initial-rotation-z °] \
       [--initial-rotation-qx --qy --qz --qw] \
       [--landmarks '<14-key JSON dict>']
   ```

   - `--background` runs without UI.
   - The `--` separates Blender's args from the script's args; everything after is parsed by `argparse` inside `blender_autorig.py`.
   - `--landmarks-out` and `--pose` are sidecar paths Blender writes to so the driver can persist the auto-detected landmarks and pose classification onto the row.
   - `--landmarks` is the only flag that switches behaviour: when present, the bones are placed from the supplied landmarks instead of the auto-detected ones (used by the `/rerig-landmarks/` flow).

4. **Inside Blender** (`blender_autorig.py`):
   - Import the mesh (FBX / GLB / GLTF / OBJ → corresponding `bpy.ops.import_scene.*`).
   - Apply the user's preview-space rotation (no automatic axis guessing — both sides agree on the canonical Z-up frame before any user input).
   - **Build a Rigify human metarig** at default size — this is the canonical scale target.
   - **Scale the mesh to the metarig**: uniform scale so the mesh's Z extent equals the metarig's, then translate so feet (min Z) and XY centre align with the metarig.
   - **Detect pose** (T / A / arms-down / unclear) by measuring the angle of arm vertices in the shoulder Z-band from horizontal — see [Pose detection](#pose-detection). Records `pose_angle_deg` and `pose_confidence`.
   - **Detect 14 landmarks** unless `--landmarks` was supplied — see [Landmarks](#landmarks). For high-confidence T-poses this uses vertex extremities + Z-slice clustering; otherwise it falls back to AABB ratios. Result is written to `--landmarks-out`.
   - **Place metarig bones from landmarks** (auto-detected or user-supplied) — see `place_bones_from_landmarks` in the script.
   - Generate the rig (`bpy.ops.pose.rigify_generate`).
   - Parent mesh → armature with **automatic weights** (`bpy.ops.object.parent_set` with `ARMATURE_AUTO`).
   - **Patch orphan vertex weights** — heat-diffusion sometimes leaves verts unweighted; the script falls back to nearest-bone weight=1 so animation doesn't collapse those verts to origin.
   - **Strip to DEF-only skeleton**, rebuilding the parent chain explicitly so glTF export keeps a clean DEF hierarchy (three.js `SkeletonHelper` only draws edges where parent is a Bone).
   - Build the **bone mapping** dict — Rigify bone names → standard Mixamo names, so retargeted animations bind cleanly.
   - Export GLB → `--output`. Write bone map → `--bones`. Write pose → `--pose`. Write detected landmarks → `--landmarks-out`.

5. **Back in the Django process**, `_run_rig_pipeline` reads the GLB, `bones.json`, `pose.json`, and `landmarks.json`, saves them onto the `RiggedModel` row (`rigged_glb`, `bone_mapping`, `landmarks`, `detected_pose` / `pose_angle_deg` / `pose_confidence`), and sets `status = "done"`.
   - On any subprocess error: capture stdout into `rig_log`, save `error_message`, set `status = "failed"`.

6. **Final WS event** with `{step: "Done", pct: 100}` (or failed equivalent).

## Landmarks

**Fourteen** labelled world-space points that anchor every major bone. The schema is the `LANDMARK_KEYS` tuple in both `backend/scripts/blender_autorig.py` and `backend/apps/rigging/views.py`:

| Key | Anchors |
|---|---|
| `chin` | Top of the spine — places the head bone tip and clamps neck length |
| `groin` | Pelvis / root of the spine |
| `left_shoulder` · `right_shoulder` | Top of upper-arm chains |
| `left_elbow` · `right_elbow` | Upper arm → forearm joint |
| `left_wrist` · `right_wrist` | Forearm → hand joint |
| `left_hip` · `right_hip` | Top of thigh chains |
| `left_knee` · `right_knee` | Thigh → shin joint |
| `left_ankle` · `right_ankle` | Bottom of leg chains |

Each value is a 3-tuple of floats in the **three.js editor frame** (Y-up; the model is normalized to `THREE_DISPLAY_HEIGHT = 2.0` units tall). The script converts to/from Blender world coords using the **metarig height** as the canonical reference — *not* the live mesh AABB, because props (top hats, eye spheres, microphones) inflate the bounding box and would scale every bone position incorrectly.

### Landmark sources

| Source | When | How |
|---|---|---|
| **Auto-detect** (default) | Initial `POST /rigs/` and `POST /rigs/{id}/rerig/` | `detect_landmarks()` runs `_promote_legacy_landmarks` on a 6-point seed, then upgrades for high-confidence T-poses with vertex extremities (wrists, ankles) and Z-slice analysis (chin, shoulders, groin, hips). Stored on `RiggedModel.landmarks`. |
| **User-supplied** | `POST /rigs/{id}/rerig-landmarks/` | All 14 keys must be present (validated by `_validate_landmark_payload`). The pipeline skips auto-detect and feeds these straight into `place_bones_from_landmarks`. |
| **Legacy fallback** | `GET /rigs/{id}/landmarks/` for rigs that pre-date the feature | `legacy_landmarks.default_landmarks_for_rig()` returns AABB defaults at unit height so the editor has draggable starting points instead of all-zeros. |

Missing any of the 14 keys on `/rerig-landmarks/` → `400` with the offending key name.

The frontend captures and edits these points with `LandmarkEditor.tsx`, fetched via `GET /rigs/{id}/landmarks/`.

## Pose detection

Stored on `RiggedModel`:

```
detected_pose      "t_pose" | "a_pose" | "arms_down" | "unclear"
pose_angle_deg     float    — arm tilt from horizontal, in the shoulder Z-band
pose_confidence    float ∈ [0, 1]
```

`detect_pose()` does this **before** the rig is generated, by sampling vertices in the chest band (45–60% body height) for trunk width, then in the shoulder band (60–82%) for arm vertices outside the trunk. For each side it anchors the shoulder at the inner 5th percentile of |x| and the hand at the outer 95th, and computes `atan2(|Δz|, |Δx|)` — the arm's angle **from horizontal**.

Bands (averaged left/right; >30° asymmetry → unclear):

| Angle | Classification |
|---|---|
| 0–25° | `t_pose` |
| 25–60° | `a_pose` |
| 60–95° | `arms_down` |
| else / asymmetric / sparse vertices | `unclear` |

Confidence is `band_centeredness × min(1, total_arm_verts / 200)`. Auto-landmark detection only switches on the T-pose hybrid path when `confidence ≥ 0.75`; lower-confidence T-poses fall back to AABB ratios.

Pose is reported back to the user in the editor so they know whether the auto-rig had a chance.

## Bone mapping

`RiggedModel.bone_mapping` is a JSON dict written by Blender:

```json
{
  "DEF-spine.001":  "Spine",
  "DEF-upper_arm.L": "LeftArm",
  "DEF-forearm.L":   "LeftForeArm",
  ...
}
```

Right side is the canonical Mixamo name. The animations app uses this to retarget tracks from a Mixamo-rigged source onto the user's rig. Tracks that don't have a mapped target are reported as unbound.

## Behaviour when Blender is missing or fails

`_run_rig_pipeline` marks the row `failed` and pushes a `failed` WS event in any of these cases:

- `BLENDER_EXECUTABLE` does not resolve to a real file.
- The subprocess exits non-zero.
- The subprocess exits 0 but produced no GLB.
- The subprocess exceeds the 10-minute timeout.
- The subprocess raises (encoding errors, OS errors, etc.).

Each case sets a specific `error_message` so the editor can show what went wrong without the user having to read `rig_log`. The previous `rigged_glb` is **not** overwritten on failure — the rerig endpoints already preserve it, so a failed rerig keeps the prior good GLB serving via the same URL.

> Earlier builds silently copied the input as the "rigged" output and marked the row `done`. Any rigs still on disk in that state will surface as JSON parse errors when a GLB-only loader hits them — re-rig them to replace with a real GLB.

See [DEVELOPMENT § Blender failures](DEVELOPMENT.md#blender-failures) and [KNOWN_ISSUES § Blender failures mark the row `failed`](KNOWN_ISSUES.md#blender-failures-mark-the-row-failed-no-more-silent-passthrough).

## Why rerigs preserve the old GLB

Both rerig endpoints reset the row's `status` and clear `bone_mapping` / `error_message` / `rig_log`, but they intentionally **leave `rigged_glb` alone**. The pipeline writes the new file with a fresh name (Django storage auto-suffixes on collision), so:

- During the rerig, the editor still serves the previous output via the existing URL.
- If the rerig fails, the previous output remains valid — no dangling 404.
- The status/`?v=<timestamp>` cache-buster on the URL forces the editor to reload once the new file lands.

## Common output problems

| Symptom | Cause | Fix |
|---|---|---|
| Row marked `failed` immediately | Blender binary missing or unreachable | Set `BLENDER_PATH` to a real binary; check `error_message` |
| Bones extend past hands / feet / head | Auto-detected wrist/ankle landed on a prop or paw tip (`_extreme_vertex` picks the literal furthest vertex) | Use `/rerig-landmarks/` from the editor and drag the wrists/ankles onto the actual joints |
| Whole skeleton sized wrong (2× too tall, hands at floor) | Landmark scale used the live mesh AABB instead of the metarig height — usually means `detect_landmarks()` is being called without `reference_height=mesh_h` | Restore `reference_height=armature_aabb(metarig)["size"].z` in both call sites in `main()` |
| `pose_confidence < 0.5` | Model in a non-standard pose, or arms aren't symmetric | Pose to T or A in the source DCC; or supply landmarks |
| Animation tracks unbound | `bone_mapping` missing the target name | Inspect `bone_mapping` JSON; the source animation may use a non-Mixamo naming scheme |
| Mesh regions collapse to origin during animation ("two dots moving") | Heat-diffusion left some verts unweighted; the `patch_orphan_vertex_weights` pass should catch them | Confirm the pass ran in `rig_log`; if not, check what raised inside it |
| Finger / toe segments float disconnected | Hand or foot bone moved without shifting its descendants | `place_bones_from_landmarks` delta-shifts descendants of `hand.{L,R}` / `foot.{L,R}` / `toe.{L,R}` — make sure that block still runs |
| `rerig` 429s | `rig_upload` throttle (10/hour) — Blender is expensive | Wait or raise the rate in `settings/base.py` |

For the full Blender script, see `backend/scripts/blender_autorig.py`. For a smoke test of the 6→14 landmark adapter that runs without Blender, see `backend/scripts/_test_landmark_promotion.py`.
