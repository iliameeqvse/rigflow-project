# Auto-Rig Perfect — Spec

**Status:** approved 2026-05-12  
**Drives:** geometry + Claude Haiku 4.5 vision duo for auto-rigging

---

## 1. Status & Problem

The current auto-rig pipeline fits a Rigify human metarig to the uploaded mesh purely by geometry: pose classification, AABB extremities for wrists/ankles, and cross-section slicing for shoulders/groin. This works well for canonical-proportion humanoids but produces visible failures on stylised meshes:

- **Freddy Fazbear upload:** `_extreme_vertex` places the wrist landmark at the tip of the paw (the literal furthest X vertex) rather than at the wrist joint. Bones extend past the character's actual hands.
- **Robot/stocky character uploads:** AABB-ratio defaults for shoulders, hips, and groin are wrong for non-human proportions even when the T-pose detector fires.
- **General:** geometry alone cannot distinguish a wrist from a prop held in the hand; it cannot tell a hat from a head.

The editor landmark-drag workflow is the escape hatch when auto-rig fails. The goal of this design is to make that escape hatch rarely necessary — the first auto-rig should fit well enough to animate without manual correction for typical bipeds including stylised ones.

---

## 2. Architecture

### Round-trip overview

```
Upload → tasks._run_rig_pipeline()
  │
  ├─ Phase 1: Blender subprocess #1
  │    --render-ortho-views  →  4 × 512×512 PNGs written to tmp/ortho/
  │    --ai-request-out      →  tmp/ai_request.json written
  │    exits
  │
  ├─ Phase 2: Django (tasks.py)
  │    reads tmp/ai_request.json
  │    calls landmark_vision.get_provider().detect(request)
  │      → ClaudeProvider: sends 4 images + prompt to Haiku 4.5
  │      → NoneProvider:   returns None (geometry-only mode)
  │    if response not None:
  │        writes tmp/ai_response.json
  │        sets rig.detection_method = "llm_vision"
  │    else:
  │        sets rig.detection_method = "geometry"
  │
  └─ Phase 3: Blender subprocess #2
       same flags as today + optionally:
       --landmarks-from-ai tmp/ai_response.json
       raycasts pixel coords → 3D seeds
       refines seeds to mesh vertices
       runs sanity checks
       place_bones_from_landmarks → Rigify generate → GLB export
```

### Why the vision call happens on the Django side, not inside Blender

Blender ships its own Python interpreter (3.11 as of Blender 4.x). Installing packages into it via `blender --python-use-system-env` or `bpy`'s internal pip is fragile across versions and OS package managers. The `anthropic` SDK alone pulls in `httpx`, `pydantic`, and `certifi` — all of which interact badly with Blender's bundled stdlib on some Linux distros. This fragility is a documented constraint in `Docs/BLENDER_AUTORIG.md` under "Technical Constraints / No External Deps."

The round-trip pattern (Blender writes a request file, exits, Django calls the SDK, writes a response file, Blender re-reads) adds one extra subprocess launch but keeps both Python environments clean.

---

## 3. Provider Abstraction

Controlled by the `LANDMARK_VISION_PROVIDER` environment variable:

| Value | Behaviour |
|---|---|
| `none` (default) | `NoneProvider` — skips AI entirely, geometry-only |
| `claude` | `ClaudeProvider` — calls Haiku 4.5 if `ANTHROPIC_API_KEY` is set |
| `gemini` | Reserved for future implementation |

**Degradation rule:** if `LANDMARK_VISION_PROVIDER=claude` but `ANTHROPIC_API_KEY` is unset or empty, the dispatcher silently returns a `NoneProvider` and logs a `WARNING`-level message. The pipeline proceeds geometry-only without raising an exception or marking the rig failed.

**Developer workflow:** leave `LANDMARK_VISION_PROVIDER` unset (or `=none`) while developing and testing geometry work. Set `=claude` only once the key is in `backend/.env`. The full geometry path works identically in both modes.

---

## 4. Request JSON Schema (Blender → Django)

Written by Blender to `tmp/ai_request.json` after the ortho-render step.

```json
{
  "rig_id": "f1a8c0b2-1234-5678-abcd-ef0123456789",
  "views": {
    "front": {
      "path": "/tmp/rigflow-abc123/ortho/front.png",
      "image_size": [512, 512],
      "camera_aabb": [[-0.8, -0.1, 0.0], [0.8, 0.1, 1.8]],
      "ortho_scale": 2.0
    },
    "back":  { "path": "...", "image_size": [512, 512], "camera_aabb": [...], "ortho_scale": 2.0 },
    "left":  { "path": "...", "image_size": [512, 512], "camera_aabb": [...], "ortho_scale": 2.0 },
    "right": { "path": "...", "image_size": [512, 512], "camera_aabb": [...], "ortho_scale": 2.0 }
  },
  "mesh_objects": [
    {"name": "Body",   "vertex_count": 12543, "bbox_world": [[-0.8, -0.1, 0.0], [0.8, 0.1, 1.8]]},
    {"name": "TopHat", "vertex_count":   432, "bbox_world": [[-0.2, -0.1, 1.7], [0.2, 0.1, 2.0]]}
  ],
  "world_aabb": [[-0.8, -0.1, 0.0], [0.8, 0.1, 2.0]]
}
```

**Field notes:**
- `camera_aabb` is the world-space AABB the camera was framed around — used by the raycast to reconstruct camera parameters.
- `ortho_scale` is the camera's orthographic scale (world units across the view plane) — required for pixel→world math.
- `mesh_objects` lists every distinct mesh in the scene; the AI uses this to assign prop labels.
- `world_aabb` is the union AABB of all meshes (including props) — used for sanity-check bounds.

---

## 5. Vision Prompt

The exact prompt string committed to `backend/apps/rigging/landmark_vision/prompts.py` as `VISION_PROMPT_TEMPLATE`. The only runtime substitution is `{mesh_object_names}`.

```
You are an expert character technical director labeling a 3D character mesh
for auto-rigging. Four orthographic 512×512 renders are attached: front, back,
left, right (in that order).

Identify the pixel coordinates of these 14 anatomical landmarks IN EACH VIEW:
  chin, groin,
  left_shoulder, right_shoulder,
  left_elbow,    right_elbow,
  left_wrist,    right_wrist,
  left_hip,      right_hip,
  left_knee,     right_knee,
  left_ankle,    right_ankle.

"Left" and "right" mean the CHARACTER'S left and right, not the viewer's.
Pixel origin is top-left; x grows right, y grows down.
If a landmark is occluded or not visible in a given view, set it to null for
that view only. At least the front view must contain non-null values for all
landmarks that are anatomically visible from the front.

Also classify each distinct mesh object listed below as exactly one of:
  body, hat, accessory_held_left, accessory_held_right, clothing, other.

Respond ONLY with valid JSON matching this schema — no prose, no markdown fence:
{
  "landmarks": {
    "front": {"chin": [x, y], "groin": [x, y], "left_shoulder": [x, y], "right_shoulder": [x, y],
              "left_elbow": [x, y], "right_elbow": [x, y], "left_wrist": [x, y], "right_wrist": [x, y],
              "left_hip": [x, y], "right_hip": [x, y], "left_knee": [x, y], "right_knee": [x, y],
              "left_ankle": [x, y], "right_ankle": [x, y]},
    "back":  { ...same 14 keys, null where occluded... },
    "left":  { ...same 14 keys, null where occluded... },
    "right": { ...same 14 keys, null where occluded... }
  },
  "mesh_objects": {
    "<object_name>": "body" | "hat" | "accessory_held_left" | "accessory_held_right" | "clothing" | "other"
  },
  "notes": "<optional one-line observation>"
}

Mesh objects in this scene: {mesh_object_names}
```

---

## 6. Response JSON Schema (Django → Blender)

Written by `tasks.py` to `tmp/ai_response.json` after validating the SDK response. Same shape as the AI returns, validated before writing.

```json
{
  "landmarks": {
    "front": {
      "chin":           [256,  48],
      "groin":          [256, 256],
      "left_shoulder":  [312,  88],
      "right_shoulder": [200,  88],
      "left_elbow":     [378, 158],
      "right_elbow":    [134, 158],
      "left_wrist":     [446, 228],
      "right_wrist":    [ 66, 228],
      "left_hip":       [284, 274],
      "right_hip":      [228, 274],
      "left_knee":      [288, 382],
      "right_knee":     [224, 382],
      "left_ankle":     [288, 490],
      "right_ankle":    [224, 490]
    },
    "back":  { "...": "same 14 keys" },
    "left":  { "...": "same 14 keys, right-side entries null" },
    "right": { "...": "same 14 keys, left-side entries null" }
  },
  "mesh_objects": {
    "Body":   "body",
    "TopHat": "hat"
  },
  "notes": "T-pose, single body mesh with hat prop"
}
```

Validation before writing: all four view keys present; each non-null value is a two-element array of finite numbers in `[0, image_size)`. Any response that fails validation is treated as malformed (triggers the failure path below).

---

## 7. Sanity Checks

Applied inside `tasks.py` to the final 3D landmark dict (after raycast + refinement) before writing to `RiggedModel.landmarks`.

All coordinates are in **three.js editor space** (Y-up, model normalized to ~2 units tall). The checks are implemented in `backend/apps/rigging/sanity.py` as pure functions with no Blender deps so they can be unit-tested.

| Check | Rule | Code |
|---|---|---|
| Completeness | All 14 `LANDMARK_KEYS` present | `missing_{key}` |
| Torso order | `groin.y < chin.y - 0.10` | `groin_above_chin` |
| Bilateral symmetry | `\|left_X - right_X\| / max(\|left_X\|, \|right_X\|, 0.01) < 0.60` for each paired key | `asymmetry_{label}` |
| AABB bounds | Each landmark inside world AABB inflated 5% | `outside_aabb_{key}` |
| Anatomical order (Y) | `ankle.y < knee.y < hip.y ≤ groin.y < shoulder.y ≤ chin.y` | `order_{a}_above_{b}` |

**Symmetry tolerance note:** 0.60 (60%) is intentionally loose to accommodate asymmetric stylised characters. The check catches catastrophic AI errors (wrist placed on the wrong side of the body) while allowing characters with one arm raised or holding a prop.

---

## 8. Failure Semantics

Every rig finishes with `status = "done"`. No rig is ever blocked from completing by the vision system.

**Cascading fallback (in order):**

1. **AI returns malformed JSON** → retry the Anthropic call once with the same payload.
2. **Retry also malformed** → run the **full geometry-only pipeline** (same code path as `LANDMARK_VISION_PROVIDER=none`). Set `detection_method = "failed"`. Editor shows the banner: *"The AI couldn't read your model — the auto-rig may be off. Adjust the landmarks below if needed."*
3. **AI returns valid JSON but 3D sanity checks fail** → drop AI landmarks, run geometry-only pipeline. Set `detection_method = "geometry"`.
4. **Geometry-only pipeline also fails sanity** → use `legacy_landmarks.DEFAULT_LANDMARKS_UNIT_HEIGHT` (AABB defaults). Set `detection_method = "failed"`. Editor banner fires.
5. **User submits landmarks via `/rerig-landmarks/`** → skip AI entirely. Set `detection_method = "user_landmarks"`.

**Cost implication of retry:** worst case is 2 Anthropic API calls per upload (~$0.012), after which the system gives up. The `rig_upload` throttle (10/hour per user) keeps worst-case spend bounded.

---

## 9. `detection_method` Values

| Value | Meaning |
|---|---|
| `geometry` | Geometry-only path ran successfully and passed sanity |
| `llm_vision` | AI + geometry refinement ran, passed sanity |
| `user_landmarks` | User submitted landmarks via `/rerig-landmarks/` |
| `failed` | AI failed (malformed ×2) or both AI and geometry failed sanity; AABB defaults used |

---

## 10. Prop Parenting

After Rigify generation, non-body mesh objects are automatically parented to the correct deform bone using the AI's `mesh_objects` labels:

| Label | Target deform bone |
|---|---|
| `hat` | `DEF-spine.005` (head) |
| `accessory_held_left` | `DEF-hand.L` |
| `accessory_held_right` | `DEF-hand.R` |
| `clothing` | Left with automatic weights (parented to full rig as before) |
| `other` | No change |

Prop parenting only runs when `detection_method = "llm_vision"` (i.e., the AI's labels are available). In geometry-only mode all meshes continue to get automatic weights as today.

---

## 11. Cost Target

Model: `claude-haiku-4-5-20251001`  
Pricing: $1.00/MTok input, $5.00/MTok output

| Component | Tokens | Cost |
|---|---|---|
| 4 × 512×512 PNGs (≈350 tokens each) | ~1,400 input | $0.0014 |
| Prompt text | ~600 input | $0.0006 |
| JSON response (14 × 4 views + labels) | ~800 output | $0.0040 |
| **Per rig (no retry)** | | **~$0.006** |
| **Per rig (one retry, worst case)** | | **~$0.012** |

At ~$0.006/rig with a $5/month spending cap: ~800 rigs/month before the cap triggers.

---

## 12. Out of Scope (this implementation)

- Quadrupeds, multi-character meshes, modular outfits
- Arms-down pose (geometry falls back to AABB; user can use editor)
- Elbow/knee geometry refinement (AI seeds used directly; user can drag)
- Gemini provider implementation (abstraction wired up, provider not built)
- WebSocket consumer for real-time progress (known issue; polling still used)
- Storage quota enforcement (separate roadmap item)
