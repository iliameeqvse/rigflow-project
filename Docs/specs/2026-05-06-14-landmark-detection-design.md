# 14-Landmark Auto-Detection + Editor Expansion

**Status**: design approved 2026-05-06
**Drives**: rigify metarig fitting for non-human-proportion models (stylised characters, robots, stocky humanoids)

## Problem

The current auto-rig pipeline scales the Rigify metarig uniformly to the mesh's height. Every other proportion (arm length, leg length, shoulder height, elbow lerp, hip width) stays at human-typical ratios. Results misfit on any mesh whose proportions differ from the metarig — the visible failure in the test case is rig wrist bones extending past the model's actual hands.

The existing landmark editor accepts 6 user-placed points (chin, L/R wrists, groin, L/R ankles), but the shoulders, elbows, hips, knees, hand-tips and toe-tips are still computed by hardcoded human-ratio heuristics inside `place_bones_from_landmarks`. So even with manual landmark editing, those joints can't be corrected.

## Goal

Two changes that together let the rig match the mesh:

1. **Replace the implicit human-ratio heuristics with explicit editable landmarks.** Promote shoulders, elbows, hips, knees from "computed" to "specified". 6 → 14 landmarks total.
2. **Auto-detect all 14 from mesh geometry on upload**, so the first auto-rig is already proportion-fit. The user only opens the editor to override what the detector got wrong.

Out of scope:
- Non-T/A pose detection (arms-down characters fall back to AABB ratios — same fit as today, no regression).
- Auto-detection of hand-tips and toe-tips (those stay at proportional offsets from wrist/ankle; no editor handles for them).

## Architecture

Three independently testable units.

### A. Landmark detector (`backend/scripts/blender_autorig.py`)

New pure function:

```python
def detect_landmarks(meshes, pose: dict) -> dict[str, Vector]
```

Inputs: post-import, post-rotation, post-auto-correction Blender meshes; pose-classifier output (`{"name": "t_pose"|"a_pose"|...,  "confidence": float}`).

Output: dict with the 14 keys listed in §Schema, values as Blender-space `mathutils.Vector` in world coords.

**Algorithm — Approach 3 (hybrid):**

When pose is `t_pose` with confidence ≥ 0.75:

1. Compute world AABB.
2. **Wrists**: vertex with max-X (left), min-X (right).
3. **Ankles**: bottom 3% of vertices by Z; cluster into two groups by X sign; ankle = each cluster's centroid.
4. **Chin**: scanning down from max-Z, the first slice whose X-extent narrows below ~30% of full X-span (head→neck transition).
5. **Shoulders**: scanning down from chin, the first slice whose X-extent jumps from torso-only width to ≥80% of full X-span (torso+arms transition); shoulder.L/R x = arm-side max-X at that slice; shoulder z = transition height.
6. **Groin**: scanning up from ankles, the highest slice with two distinct X-clusters (gap detection on sorted X with threshold > 5% of width).
7. **Hips**: at groin Z, take the centroid X of each leg cluster from step 6.
8. **Elbow**: lerp shoulder→wrist at 0.55 (no slice refinement; user adjustable).
9. **Knee**: lerp hip→ankle at 0.50 (no slice refinement; user adjustable).

Slicing implementation: 50 horizontal Z-slices over the AABB. For each, gather vertices in that range; compute min-X/max-X and detect clusters by sorting X values and finding gaps wider than 5% of total X-span.

When pose confidence < 0.75 OR pose is anything other than `t_pose`:

Fallback to **AABB ratios** — the same human ratios the current pipeline uses today (shoulder z = groin.z + 0.82 · body_h, elbow = lerp shoulder→wrist 0.55, hip = ankle.x at groin.z, knee = lerp hip→ankle 0.50, plus AABB-derived chin/groin/wrist/ankle defaults). Result is no worse than today's behaviour, but landmarks become editable so the user can drag them into place. A-pose detection is a follow-up; for now A-pose hits this fallback too.

### B. Landmark consumer (`place_bones_from_landmarks`, modified)

Drop the heuristic computations for shoulder/elbow/hip/knee. Use explicit landmark dict keys instead. Spine ratio interpolation stays. Hand-tip and toe-tip extension offsets stay (proportional to torso height, derived from chin-groin distance).

Backward compatibility:

```python
def _promote_legacy_landmarks(d: dict) -> dict:
    """Given a dict containing at least the legacy 6 keys (chin, groin,
    left_wrist, right_wrist, left_ankle, right_ankle), return a 14-key
    dict with shoulders/elbows/hips/knees filled in via the heuristics
    that were inline in the original place_bones_from_landmarks."""
```

Callers passing a 6-key dict (legacy `/rerig-landmarks/` requests, saved DB rows, manual API users) continue to work — the adapter fills the 8 missing keys via:

- `shoulder.{L,R}` = `(wrist.x, wrist.y, groin.z + body_h * 0.82)` where `body_h = max(0.2, chin.z - groin.z)`
- `elbow.{L,R}` = `lerp(shoulder, wrist, 0.55) + (0, 0.05, -0.02)`
- `hip.{L,R}` = `(ankle.x, ankle.y, groin.z)`
- `knee.{L,R}` = `(ankle.x * 0.97, ankle.y - 0.04, (groin.z + ankle.z) / 2 + 0.02)`

(These match the existing heuristics in `place_bones_from_landmarks` lines 654-679 verbatim.) Frontend sends 14 going forward.

### C. Editor UI (`frontend/src/components/LandmarkEditor.tsx` + `lib/api.ts`)

14 draggable landmark points instead of 6. Grouped into four side panels:

- **Head** (1 point): chin
- **Arms L** (3 points): left_shoulder, left_elbow, left_wrist
- **Arms R** (3 points): right_shoulder, right_elbow, right_wrist
- **Torso** (1 point): groin
- **Legs L** (3 points): left_hip, left_knee, left_ankle
- **Legs R** (3 points): right_hip, right_knee, right_ankle

One colour per group. Hover label on each point showing its name. The 3D drag interaction stays as today.

On editor open, fetch initial positions from `GET /rigs/{id}/landmarks/`. On save, POST 14 to `/rigs/{id}/rerig-landmarks/`.

## Data flow

```
upload FBX
  → import_model + auto-correction (existing)
  → pose_classifier (existing)
  → detect_landmarks(meshes, pose)        [NEW]
  → place_bones_from_landmarks(metarig, detected_landmarks)   [now always runs, even on first auto-rig]
  → generate_rig + parent + export GLB (existing)
  → save RiggedModel.landmarks (three.js-space POJO)        [NEW]

editor open
  → GET /rigs/{id}/landmarks/                                [NEW endpoint, reads RiggedModel.landmarks]
  → user drags points
  → POST /rigs/{id}/rerig-landmarks/ with 14-key payload    [existing endpoint, updated schema]
  → re-runs pipeline using user-edited landmarks
```

## Schema

### Backend Python

```python
LANDMARK_KEYS = (
    "chin", "groin",
    "left_shoulder", "right_shoulder",
    "left_elbow", "right_elbow",
    "left_wrist", "right_wrist",
    "left_hip", "right_hip",
    "left_knee", "right_knee",
    "left_ankle", "right_ankle",
)
```

Inside `blender_autorig.py`, landmarks are `mathutils.Vector` in Blender world-space coords.

Across the API boundary, landmarks are three.js-space `(x, y, z)` floats with the model normalized to `THREE_DISPLAY_HEIGHT = 2.0` units tall (existing convention; see `threejs_to_blender`).

### Database

New field on `apps.rigging.models.RiggedModel`:

```python
landmarks = models.JSONField(null=True, blank=True)
```

Stores the three.js-space 14-key dict. Populated by `auto_rig_model` task on completion. `null` on legacy rows; `GET /landmarks/` returns AABB-default landmarks for those instead of erroring.

### API endpoints

- `GET /api/v1/rigs/{id}/landmarks/` — serializer returns `{key: [x, y, z]}`. Public (matches `GET /rigs/{id}/`'s auth pattern). 200 with payload, or 200 with AABB defaults if `landmarks` is null.
- `POST /api/v1/rigs/{id}/rerig-landmarks/` — existing endpoint; now accepts 14-key payload. 6-key payloads still accepted (server-side `_promote_legacy_landmarks`).

## Edge cases / fallbacks

- **Pose classifier unconfident or non-T/A**: detector returns AABB-default landmarks. First auto-rig is no worse than today. Editor still works; user manually places.
- **Mesh has internal cavities or non-watertight geometry**: cross-section slicing operates on world vertices (not faces), so cavities don't break slicing. Vertex density variations might shift detected transitions slightly; user adjusts in editor.
- **Mesh has multiple disjoint pieces (e.g., gun in hand)**: the wrist-tip extremity detection might pick the gun's tip instead of the hand. Mitigation: filter wrist candidates to vertices within ±20% Z of the AABB-projected shoulder height before picking extremity. If still wrong, user drags.
- **Asymmetric models**: each side detected independently. No symmetry constraint imposed.
- **Existing rigs in DB**: migrations leave `landmarks=null`. Re-rig uses AABB defaults until user opens editor and saves edits.

## Test plan

Per unit (each independently testable):

- **detector**: synthetic meshes (cylinder, cube-arms+cube-torso, real T-pose humanoid, real A-pose humanoid, real non-T-pose). Assert detected landmarks fall within tolerance of hand-annotated ground truth.
- **consumer**: feed canned 14-key dicts; assert metarig bone heads/tails match. Feed canned 6-key dicts; assert promotion fills missing keys without breaking output.
- **editor**: load with canned 14-landmark API response; render 14 points; drag one; assert POST payload contains all 14 keys with the dragged value updated.

End-to-end: re-run the failing FBX from the May 2026 debugging session. Expected outcome: rig wrist bone position matches mesh hand position out of the box, no editor adjustment needed.

## Migration

1. Land detector + consumer changes; `auto_rig_model` saves `landmarks` to DB.
2. Land `GET /landmarks/` endpoint.
3. Land frontend editor changes.
4. Existing rigs continue to work via legacy adapter; users who re-rig get the new behaviour.
5. No data migration required (nullable JSONField).

## Open follow-ups (not in this work)

- Elbow/knee refinement via mesh-thickness inflection (deferred from Approach 3; user can drag).
- A-pose specific cross-section analysis (the detector falls back to AABB ratios for A-pose right now even though some logic could be salvaged; revisit if A-pose accuracy becomes a real complaint).
- Auto-detection for non-T/A poses (out of scope here; needs different geometric strategy entirely).
