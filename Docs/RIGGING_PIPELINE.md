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
       --input  <tmp>/<original>.<ext> \
       --output <tmp>/rigged.glb \
       --bones  <tmp>/bones.json \
       [--initial-rotation-x ° --initial-rotation-y ° --initial-rotation-z °] \
       [--initial-rotation-qx --qy --qz --qw] \
       [--landmarks <tmp>/landmarks.json]
   ```

   - `--background` runs without UI.
   - The `--` separates Blender's args from the script's args; everything after is parsed by `argparse` inside `blender_autorig.py`.

4. **Inside Blender** (`blender_autorig.py`):
   - Import the mesh (FBX / GLB / GLTF / OBJ → corresponding `bpy.ops.import_scene.*`).
   - Normalize: align to Z-up, scale to a fixed reference height, recenter so feet sit on the ground plane.
   - **Build a Rigify metarig** fitted to either:
     - the mesh's bounding box (auto-fit), or
     - the 6 user-supplied landmarks (precise fit), if `--landmarks` is supplied.
   - Generate the rig (`bpy.ops.pose.rigify_generate`).
   - Parent mesh → armature with **automatic weights** (`bpy.ops.object.parent_set` with `ARMATURE_AUTO`).
   - **Detect pose** (T / A / arms-down / unclear) by measuring the angle of the upper-arm bones relative to the spine; record `pose_angle_deg` and `pose_confidence`.
   - Build the **bone mapping** dict — Rigify bone names → standard Mixamo names, so retargeted animations bind cleanly.
   - Export GLB → `--output`. Write bone map → `--bones`.

5. **Back in the Django process**, `_run_rig_pipeline` reads the GLB and `bones.json`, saves them onto the `RiggedModel` row, and sets `status = "done"`.
   - On any subprocess error: capture stdout into `rig_log`, save `error_message`, set `status = "failed"`.

6. **Final WS event** with `{step: "Done", pct: 100}` (or failed equivalent).

## Landmarks

Six labelled world-space points that anchor key bones. Defined in `views.py:rerig_landmarks`:

| Key | Anchors |
|---|---|
| `chin` | Top of the spine — used to place the head bone tip and clamp neck length |
| `left_wrist` | Tip of the left arm chain |
| `right_wrist` | Tip of the right arm chain |
| `groin` | Pelvis / hip pivot (root of the spine) |
| `left_ankle` | Tip of the left leg chain |
| `right_ankle` | Tip of the right leg chain |

Each value is a 3-tuple of floats in the editor's world frame (post-normalization). Missing any key → `400` with the list of missing names.

The frontend captures these points with `LandmarkEditor.tsx`, which lets the user click on the model in a Three.js scene to place markers.

## Pose detection

Stored on `RiggedModel`:

```
detected_pose      "t_pose" | "a_pose" | "arms_down" | "unclear"
pose_angle_deg     float    — angle from spine to upper-arm bone, signed
pose_confidence    float ∈ [0, 1]
```

The bands are derived from `pose_angle_deg`:

- ~ 90° from spine → T-pose.
- ~ 45° from spine → A-pose.
- ~ 0° from spine (arms hanging) → arms-down.
- Anything else, or low confidence → unclear.

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
| Rig done in milliseconds, no skeleton | Blender fallback ran | Set `BLENDER_PATH` to a real binary |
| Bones placed too high/low | Auto-fit got a bad bounding box (e.g., loose accessories inflate bounds) | Use `/rerig-landmarks/` from the editor |
| `pose_confidence < 0.5` | Model in a non-standard pose | Pose to T or A in the source DCC; or supply landmarks |
| Animation tracks unbound | `bone_mapping` missing the target name | Inspect `bone_mapping` JSON; the source animation may use a non-Mixamo naming scheme |
| `rerig` 429s | `rig_upload` throttle (10/hour) — Blender is expensive | Wait or raise the rate in `settings/base.py` |

For the full Blender script, see `backend/scripts/blender_autorig.py`.
