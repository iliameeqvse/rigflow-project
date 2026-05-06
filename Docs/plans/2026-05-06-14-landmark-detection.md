# 14-Landmark Auto-Detection + Editor Expansion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace human-ratio heuristics for shoulders / elbows / hips / knees with explicit editable landmarks (6 → 14), and auto-detect all 14 from mesh geometry on every upload so the first auto-rig fits stylised models out of the box.

**Architecture:** Three units. (A) `detect_landmarks` — pure detector in the Blender script that runs after the existing post-import auto-correction; uses vertex extremities for tip points, 50-slice cross-section analysis for transitions, lerp for elbow/knee. (B) `place_bones_from_landmarks` — modified to consume 14 keys directly, with a `_promote_legacy_landmarks` adapter for 6-key callers. (C) `LandmarkEditor.tsx` — renders 14 grouped points pre-populated from a new `GET /rigs/{id}/landmarks/` endpoint.

**Tech Stack:** Python 3 + Blender (`bpy`, `mathutils.Vector`), Django 5.1 + DRF + Celery, Next.js 16 + React 19 + `@react-three/fiber`.

**Spec:** `Docs/specs/2026-05-06-14-landmark-detection-design.md`.

**Path conventions:** All file paths below are relative to the repo's nested source root, `rigflow-project/rigflow-project/` (per `CLAUDE.md`'s repo-layout note). Run `cd rigflow-project/` once before executing the plan.

---

### Task 1: Add `landmarks` JSONField to `RiggedModel` + migration

**Files:**
- Modify: `backend/apps/rigging/models.py`
- Create: `backend/apps/rigging/migrations/0NNN_riggedmodel_landmarks.py` (auto-generated; NNN is the next sequence number)

- [ ] **Step 1: Find the highest existing migration number**

```bash
ls backend/apps/rigging/migrations/ | grep -E '^[0-9]{4}_' | sort | tail -3
```

Note the highest number (e.g., `0007_*` → next is `0008`).

- [ ] **Step 2: Add the field to `RiggedModel`**

In `backend/apps/rigging/models.py`, find the `RiggedModel` class. Add this field near the existing `bone_mapping = models.JSONField(...)` line (search for `bone_mapping`):

```python
landmarks = models.JSONField(
    null=True, blank=True,
    help_text=(
        "14 anatomical landmarks (chin, groin, L/R × {shoulder, elbow, "
        "wrist, hip, knee, ankle}) in three.js editor space, used to fit "
        "the rigify metarig to non-human-proportion meshes. Populated by "
        "auto-rig; editable via /landmarks/ + /rerig-landmarks/."
    ),
)
```

- [ ] **Step 3: Generate migration**

Run from `backend/`:

```bash
python manage.py makemigrations rigging
```

Expected output: `Migrations for 'rigging': 0NNN_riggedmodel_landmarks.py - Add field landmarks to riggedmodel`.

- [ ] **Step 4: Apply the migration**

```bash
python manage.py migrate rigging
```

Expected: `Applying rigging.0NNN_riggedmodel_landmarks... OK`.

- [ ] **Step 5: Commit**

```bash
git add backend/apps/rigging/models.py backend/apps/rigging/migrations/0NNN_riggedmodel_landmarks.py
git commit -m "feat(rigging): add landmarks JSONField to RiggedModel"
```

---

### Task 2: Add `LANDMARK_KEYS` and `_promote_legacy_landmarks` to Blender script

**Files:**
- Modify: `backend/scripts/blender_autorig.py` (insert near the top of the "Landmarks" section, around line 600)
- Create: `backend/scripts/_test_landmark_promotion.py` (standalone smoke test, no Blender dependencies)

- [ ] **Step 1: Write the failing smoke test**

Create `backend/scripts/_test_landmark_promotion.py`:

```python
"""Standalone smoke test for _promote_legacy_landmarks. Run with:
    python backend/scripts/_test_landmark_promotion.py
No Blender dependency — uses tuples instead of mathutils.Vector."""
import importlib.util
import sys
from pathlib import Path

# Load the function under test without importing bpy. We monkey-load just
# the symbols we need from blender_autorig.py.
src = Path(__file__).parent / "blender_autorig.py"
spec = importlib.util.spec_from_file_location("blender_autorig", src)
module = importlib.util.module_from_spec(spec)

# Stub out bpy / mathutils so the script can be imported in plain Python.
class _StubVec(tuple):
    def __new__(cls, xyz):
        v = tuple.__new__(cls, xyz)
        return v
    @property
    def x(self): return self[0]
    @property
    def y(self): return self[1]
    @property
    def z(self): return self[2]
    def __sub__(self, other): return _StubVec((self[0]-other[0], self[1]-other[1], self[2]-other[2]))
    def __add__(self, other): return _StubVec((self[0]+other[0], self[1]+other[1], self[2]+other[2]))
    def __mul__(self, s): return _StubVec((self[0]*s, self[1]*s, self[2]*s))

stub_mathutils = type(sys)("mathutils")
stub_mathutils.Vector = _StubVec
stub_mathutils.Quaternion = object
stub_mathutils.Matrix = object
sys.modules["mathutils"] = stub_mathutils
sys.modules["bpy"] = type(sys)("bpy")

spec.loader.exec_module(module)

# Test: 6-key dict gets promoted to 14 keys with sensible derived values.
six = {
    "chin":         _StubVec((0.0, 0.0, 1.6)),
    "groin":        _StubVec((0.0, 0.0, 0.9)),
    "left_wrist":   _StubVec((0.7, 0.0, 1.4)),
    "right_wrist":  _StubVec((-0.7, 0.0, 1.4)),
    "left_ankle":   _StubVec((0.1, 0.0, 0.0)),
    "right_ankle":  _StubVec((-0.1, 0.0, 0.0)),
}
out = module._promote_legacy_landmarks(six)

assert set(out.keys()) == set(module.LANDMARK_KEYS), f"got {set(out.keys())}"
# Spot-check shoulder z = groin.z + body_h * 0.82, body_h = chin.z - groin.z = 0.7
expected_shoulder_z = 0.9 + 0.7 * 0.82  # 1.474
assert abs(out["left_shoulder"].z - expected_shoulder_z) < 1e-6, out["left_shoulder"]
# Hip x equals ankle x (both signs)
assert out["left_hip"].x == 0.1 and out["right_hip"].x == -0.1
# Knee z is midway between groin and ankle plus 0.02 offset
assert abs(out["left_knee"].z - ((0.9 + 0.0) / 2 + 0.02)) < 1e-6
print("_promote_legacy_landmarks smoke test: OK")
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
python backend/scripts/_test_landmark_promotion.py
```

Expected: `AttributeError: module 'blender_autorig' has no attribute '_promote_legacy_landmarks'` (or similar — the symbol does not exist yet).

- [ ] **Step 3: Add the constant + adapter**

In `backend/scripts/blender_autorig.py`, find the "Landmarks (optional — used by /rigs/{id}/rerig-landmarks/)" section header (around line 600). Above it, add:

```python
# ---------------------------------------------------------------------------
# Landmark schema
# ---------------------------------------------------------------------------

LANDMARK_KEYS = (
    "chin", "groin",
    "left_shoulder", "right_shoulder",
    "left_elbow", "right_elbow",
    "left_wrist", "right_wrist",
    "left_hip", "right_hip",
    "left_knee", "right_knee",
    "left_ankle", "right_ankle",
)

LEGACY_LANDMARK_KEYS = (
    "chin", "groin",
    "left_wrist", "right_wrist",
    "left_ankle", "right_ankle",
)


def _promote_legacy_landmarks(d):
    """Given a dict containing at least the legacy 6 keys, return a 14-key
    dict with shoulders/elbows/hips/knees filled in via the heuristics that
    were inline in the original place_bones_from_landmarks.

    Inputs may be either mathutils.Vector or any 3-tuple; the math below
    works on either as long as +, -, * are supported (the standalone test
    uses a tuple stub)."""
    chin  = d["chin"]
    groin = d["groin"]
    body_h = max(0.2, chin.z - groin.z)

    out = dict(d)
    for side, wrist in (("left", d["left_wrist"]), ("right", d["right_wrist"])):
        s_key = f"{side}_shoulder"
        e_key = f"{side}_elbow"
        if s_key not in out:
            shoulder = _vec((wrist.x, wrist.y, groin.z + body_h * 0.82))
            out[s_key] = shoulder
        else:
            shoulder = out[s_key]
        if e_key not in out:
            out[e_key] = shoulder + (wrist - shoulder) * 0.55 + _vec((0.0, 0.05, -0.02))

    for side, ankle in (("left", d["left_ankle"]), ("right", d["right_ankle"])):
        h_key = f"{side}_hip"
        k_key = f"{side}_knee"
        if h_key not in out:
            out[h_key] = _vec((ankle.x, ankle.y, groin.z))
        if k_key not in out:
            out[k_key] = _vec((
                ankle.x * 0.97,
                ankle.y - 0.04,
                (groin.z + ankle.z) / 2 + 0.02,
            ))
    return out


def _vec(xyz):
    """Return a Vector when bpy is available, else preserve the input
    object's type (so the standalone test using tuple stubs still works)."""
    try:
        return Vector(xyz)
    except Exception:
        return type(xyz)(xyz) if isinstance(xyz, tuple) else xyz
```

Note the import of `Vector` already exists at the top of the file (line 24-25).

- [ ] **Step 4: Run the test to verify it passes**

```bash
python backend/scripts/_test_landmark_promotion.py
```

Expected: `_promote_legacy_landmarks smoke test: OK`.

- [ ] **Step 5: Commit**

```bash
git add backend/scripts/blender_autorig.py backend/scripts/_test_landmark_promotion.py
git commit -m "feat(rigging): add 14-landmark schema + legacy 6-key adapter"
```

---

### Task 3: Refactor `place_bones_from_landmarks` to consume 14 keys

**Files:**
- Modify: `backend/scripts/blender_autorig.py` (function `place_bones_from_landmarks`, lines ~609-700)

- [ ] **Step 1: Replace the function body to use 14-key inputs via promotion**

In `backend/scripts/blender_autorig.py`, replace the body of `place_bones_from_landmarks` (everything from `def place_bones_from_landmarks(metarig, landmarks, mesh_height):` to the next `def`) with:

```python
def place_bones_from_landmarks(metarig, landmarks, mesh_height):
    """Position rigify metarig bones from a 14-key landmark dict (or a
    legacy 6-key dict that gets promoted via _promote_legacy_landmarks).

    Three.js-space inputs are converted to Blender world coords first.
    All 14 keys must be present after promotion; KeyError otherwise."""
    log(f"Applying landmarks (mesh_h={mesh_height:.3f}):")
    for k, v in landmarks.items():
        log(f"  three.js {k}: ({v[0]:.3f}, {v[1]:.3f}, {v[2]:.3f})")

    lmk = {k: threejs_to_blender(v, mesh_height) for k, v in landmarks.items()}
    lmk = _promote_legacy_landmarks(lmk)
    for k, v in lmk.items():
        log(f"  blender   {k}: ({v.x:.3f}, {v.y:.3f}, {v.z:.3f})")

    chin, groin = lmk["chin"], lmk["groin"]
    lw, rw = lmk["left_wrist"], lmk["right_wrist"]
    la, ra = lmk["left_ankle"], lmk["right_ankle"]
    ls, rs = lmk["left_shoulder"], lmk["right_shoulder"]
    le, re = lmk["left_elbow"], lmk["right_elbow"]
    lh, rh = lmk["left_hip"], lmk["right_hip"]
    lk, rk = lmk["left_knee"], lmk["right_knee"]

    activate(metarig)
    bpy.ops.object.mode_set(mode="EDIT")
    eb = metarig.data.edit_bones

    pre_move = {}
    for name in ("hand.L", "hand.R", "foot.L", "foot.R", "toe.L", "toe.R"):
        b = eb.get(name)
        if b:
            pre_move[name] = b.head.copy()

    placed = set()

    spine = ["spine", "spine.001", "spine.002",
             "spine.003", "spine.004", "spine.005"]
    ratios = [0.0, 0.18, 0.38, 0.58, 0.78, 0.92, 1.0]
    for i, name in enumerate(spine):
        b = eb.get(name)
        if not b:
            continue
        r0, r1 = ratios[i], ratios[i + 1]
        b.head = groin + (chin - groin) * r0
        b.tail = groin + (chin - groin) * r1
        placed.add(name)

    body_h = max(0.2, chin.z - groin.z)
    for side, shoulder, elbow, wrist in (
        ("L", ls, le, lw),
        ("R", rs, re, rw),
    ):
        hand_end = wrist + (wrist - elbow).normalized() * 0.07
        for name, h, t in (
            (f"upper_arm.{side}", shoulder, elbow),
            (f"forearm.{side}",   elbow,    wrist),
            (f"hand.{side}",      wrist,    hand_end),
        ):
            b = eb.get(name)
            if b:
                b.head, b.tail = h, t
                placed.add(name)

    for side, hip, knee, ankle in (
        ("L", lh, lk, la),
        ("R", rh, rk, ra),
    ):
        toe = ankle + Vector((0.0, -0.09, 0.0))
        for name, h, t in (
            (f"thigh.{side}", hip,   knee),
            (f"shin.{side}",  knee,  ankle),
            (f"foot.{side}",  ankle, toe),
            (f"toe.{side}",   toe,   toe + Vector((0.0, -0.04, 0.0))),
        ):
            b = eb.get(name)
            if b:
                b.head, b.tail = h, t
                placed.add(name)

    # Shift descendants of moved hand / foot / toe bones (unchanged from
    # the pre-refactor version — see git history for context).
    for name, old_head in pre_move.items():
        b = eb.get(name)
        if not b:
            continue
        delta = b.head - old_head
        if delta.length < 1e-6:
            continue
        for child in b.children_recursive:
            if child.name in placed:
                continue
            child.head = child.head + delta
            child.tail = child.tail + delta

    # Recompute roll only for bones we placed; preserve metarig defaults
    # for fingers, face, breast etc.
    for name in placed:
        b = eb.get(name)
        if b is None:
            continue
        try:
            b.roll = 0.0
        except Exception:
            pass
    bpy.ops.object.mode_set(mode="OBJECT")
```

(The descendant-shift and roll-reset logic existed before; if the existing function diverges from the snippet above, preserve the existing logic for those two passes — only the spine/arms/legs main bodies change.)

- [ ] **Step 2: Run the existing legacy-payload smoke test (Task 2's test)**

```bash
python backend/scripts/_test_landmark_promotion.py
```

Expected: still PASS — Task 3 doesn't touch the adapter, only the consumer.

- [ ] **Step 3: End-to-end smoke check via existing rerig-landmarks endpoint**

Pre-condition: a previous rig already exists (use any rig from a recent upload). With Django dev server running, hit the endpoint with the 6-key payload it has always accepted:

```bash
curl -X POST http://localhost:8000/api/v1/rigs/<rig-id>/rerig-landmarks/ \
  -H "Authorization: Bearer <jwt>" \
  -H "Content-Type: application/json" \
  -d '{"landmarks": {
        "chin":        [0.0, 1.6, 0.0],
        "groin":       [0.0, 0.9, 0.0],
        "left_wrist":  [0.7, 1.4, 0.0],
        "right_wrist": [-0.7, 1.4, 0.0],
        "left_ankle":  [0.1, 0.0, 0.0],
        "right_ankle": [-0.1, 0.0, 0.0]
      }}'
```

Expected: HTTP 202; rig log contains `Applying landmarks (mesh_h=...)` and lists 14 blender-frame entries (the 6 originals + 8 promoted). Rig regenerates without error.

- [ ] **Step 4: Commit**

```bash
git add backend/scripts/blender_autorig.py
git commit -m "refactor(rigging): place_bones_from_landmarks consumes 14 keys"
```

---

### Task 4: Add `--landmarks-out` CLI flag and AABB-default detector stub

**Files:**
- Modify: `backend/scripts/blender_autorig.py` (`parse_args`, new `detect_landmarks` function, `main`)

- [ ] **Step 1: Add the new CLI flag**

In `parse_args` (around line 49), after `p.add_argument("--landmarks", default=None)`, add:

```python
p.add_argument("--landmarks-out", default=None,
               help="If set, write detected landmarks (14-key three.js-space "
                    "JSON) to this path after auto-correction. Used by the "
                    "Celery task to persist landmarks on the RiggedModel.")
```

- [ ] **Step 2: Add a stub `detect_landmarks` returning AABB defaults**

Place this function above `place_bones_from_landmarks`:

```python
def detect_landmarks(meshes, pose=None):
    """Return a 14-key landmark dict in three.js editor space (Y-up,
    normalized to THREE_DISPLAY_HEIGHT units tall). For now this is the
    AABB-default fallback only — Task 5 adds T-pose hybrid detection.

    `pose` may be None, or a dict like {"name": "t_pose", "confidence": 0.84}.
    """
    b = aabb(world_vertices(meshes))
    height_blender = b["size"].z
    if height_blender < 1e-3:
        height_blender = 1.0
    s = THREE_DISPLAY_HEIGHT / height_blender

    # Convert a Blender world coord to three.js editor space.
    # threejs_to_blender does: (x*s, -z*s, y*s) where s=mesh_h/2.
    # The inverse: three_x = bx/s_inv, three_y = bz/s_inv, three_z = -by/s_inv
    # with s_inv = mesh_height_blender / THREE_DISPLAY_HEIGHT.
    def to_three(bv):
        return (bv.x * s, bv.z * s, -bv.y * s)

    mn, mx = b["min"], b["max"]
    body_h = mx.z - mn.z
    width = max(mx.x - mn.x, 1e-3)

    # AABB-derived defaults, mirroring the legacy heuristic ratios.
    chin   = Vector((0.0, 0.0, mn.z + 0.92 * body_h))
    groin  = Vector((0.0, 0.0, mn.z + 0.50 * body_h))
    lw     = Vector((mx.x, 0.0, mn.z + 0.82 * body_h))
    rw     = Vector((mn.x, 0.0, mn.z + 0.82 * body_h))
    la     = Vector((+0.10 * width, 0.0, mn.z))
    ra     = Vector((-0.10 * width, 0.0, mn.z))

    six = {"chin": chin, "groin": groin,
           "left_wrist": lw, "right_wrist": rw,
           "left_ankle": la, "right_ankle": ra}
    fourteen_blender = _promote_legacy_landmarks(six)

    return {k: to_three(v) for k, v in fourteen_blender.items()}
```

- [ ] **Step 3: Wire `detect_landmarks` to write the JSON when `--landmarks-out` is set**

In `main()`, find where `apply_user_rotation(meshes, …)` is called (around line 920). Immediately after that call:

```python
if args.landmarks_out:
    detected = detect_landmarks(meshes, pose=None)  # pose param wired up in Task 5
    Path(args.landmarks_out).write_text(json.dumps(detected, indent=2))
    log(f"Wrote {len(detected)} detected landmarks → {args.landmarks_out}")
```

(`Path` and `json` are already imported at the top of the file.)

- [ ] **Step 4: Smoke-test the flag end-to-end**

Manually invoke the script against a known FBX (use `frontend/public/animations/wave.fbx` as the test input — it's a Mixamo-rigged humanoid):

```bash
mkdir -p /tmp/rigflow-test
blender --background --python backend/scripts/blender_autorig.py -- \
  --input frontend/public/animations/wave.fbx \
  --output /tmp/rigflow-test/out.glb \
  --bones /tmp/rigflow-test/bones.json \
  --landmarks-out /tmp/rigflow-test/landmarks.json
cat /tmp/rigflow-test/landmarks.json
```

Expected: a valid 14-key JSON with three-element float arrays. Each Z value in three.js space should be ≤ ~2.0 (TARGET height); chin near +1.84 (0.92 × 2.0), ankles near 0.

- [ ] **Step 5: Commit**

```bash
git add backend/scripts/blender_autorig.py
git commit -m "feat(rigging): add detect_landmarks stub + --landmarks-out CLI flag"
```

---

### Task 5: Implement T-pose hybrid detection (extremities)

**Files:**
- Modify: `backend/scripts/blender_autorig.py` (`detect_landmarks` and helpers)

- [ ] **Step 1: Add the extremity helpers above `detect_landmarks`**

Insert before `detect_landmarks`:

```python
def _extreme_vertex(verts, axis, sign):
    """Return the vertex furthest along a signed axis. axis ∈ {0,1,2}."""
    if sign > 0:
        return max(verts, key=lambda v: v[axis])
    return min(verts, key=lambda v: v[axis])


def _bottom_cluster_centroids(verts, bottom_frac=0.03):
    """Return (left_centroid, right_centroid) of the lowest `bottom_frac`
    of vertices, partitioned by X sign. Used for ankle detection."""
    z_threshold = sorted(v.z for v in verts)[max(0, int(len(verts) * bottom_frac) - 1)]
    bottom = [v for v in verts if v.z <= z_threshold]
    left  = [v for v in bottom if v.x >= 0]
    right = [v for v in bottom if v.x <  0]
    if not left or not right:
        return None  # caller falls back
    def centroid(vs):
        n = len(vs)
        return Vector((sum(v.x for v in vs)/n, sum(v.y for v in vs)/n, sum(v.z for v in vs)/n))
    return centroid(left), centroid(right)
```

- [ ] **Step 2: Update `detect_landmarks` to use extremities for wrists + ankles when pose is T**

Replace the body of `detect_landmarks` with:

```python
def detect_landmarks(meshes, pose=None):
    """Return a 14-key landmark dict in three.js editor space.

    For T-pose with confidence ≥ 0.75 use a hybrid algorithm: vertex
    extremities for wrists/ankles, AABB defaults for everything else
    (Task 6 adds slicing for chin/shoulders/groin/hips). Other poses
    fall back to AABB ratios via _promote_legacy_landmarks.
    """
    b = aabb(world_vertices(meshes))
    height_blender = max(b["size"].z, 1e-3)
    s = THREE_DISPLAY_HEIGHT / height_blender

    def to_three(bv):
        return (bv.x * s, bv.z * s, -bv.y * s)

    mn, mx = b["min"], b["max"]
    body_h = mx.z - mn.z
    width = max(mx.x - mn.x, 1e-3)

    is_t = (pose is not None
            and pose.get("name") == "t_pose"
            and pose.get("confidence", 0.0) >= 0.75)

    # AABB defaults (used as fallbacks even on the T-pose path for the
    # landmarks slicing hasn't been wired up for yet).
    chin   = Vector((0.0, 0.0, mn.z + 0.92 * body_h))
    groin  = Vector((0.0, 0.0, mn.z + 0.50 * body_h))
    lw     = Vector((mx.x, 0.0, mn.z + 0.82 * body_h))
    rw     = Vector((mn.x, 0.0, mn.z + 0.82 * body_h))
    la     = Vector((+0.10 * width, 0.0, mn.z))
    ra     = Vector((-0.10 * width, 0.0, mn.z))

    if is_t:
        verts = world_vertices(meshes)
        # Wrists: extreme +X / -X.
        lw_v = _extreme_vertex(verts, axis=0, sign=+1)
        rw_v = _extreme_vertex(verts, axis=0, sign=-1)
        lw = Vector((lw_v.x, lw_v.y, lw_v.z))
        rw = Vector((rw_v.x, rw_v.y, rw_v.z))
        # Ankles: bottom-cluster centroids split by X sign.
        ankles = _bottom_cluster_centroids(verts)
        if ankles is not None:
            la, ra = ankles
        log(f"T-pose detection: wrists & ankles via vertex extremities")
    else:
        log("Non-T pose or low confidence — landmark detection falls back to AABB defaults")

    six = {"chin": chin, "groin": groin,
           "left_wrist": lw, "right_wrist": rw,
           "left_ankle": la, "right_ankle": ra}
    fourteen_blender = _promote_legacy_landmarks(six)
    return {k: to_three(v) for k, v in fourteen_blender.items()}
```

- [ ] **Step 3: Pass the pose-classifier output into `detect_landmarks`**

In `main()`, locate where the pose classifier is currently called and writes its result (search for `Pose:` or `pose_classify` — there's a log line `[RigFlow] Pose: a_pose (angle=…)` so the classifier is already there). Capture its return into a local, e.g. `detected_pose = {"name": classified_name, "confidence": classified_confidence}`.

Then update the `--landmarks-out` block (added in Task 4):

```python
if args.landmarks_out:
    detected = detect_landmarks(meshes, pose=detected_pose)
    Path(args.landmarks_out).write_text(json.dumps(detected, indent=2))
    log(f"Wrote {len(detected)} detected landmarks → {args.landmarks_out}")
```

- [ ] **Step 4: Smoke-test against the user's FBX**

Re-run the Task 4 smoke command with the same wave.fbx (which is T-pose-ish). Compare `landmarks.json`:

- `left_wrist` should now have a much larger |X| than `0.82 * 2.0 ≈ 1.64` if the model's actual hand reaches further; if the AABB-default and detected match closely, the model is canonical-human-proportioned and that's also fine.
- Each ankle should have a Y near 0 (three.js Y = ground in editor space).

- [ ] **Step 5: Commit**

```bash
git add backend/scripts/blender_autorig.py
git commit -m "feat(rigging): T-pose extremity detection for wrists & ankles"
```

---

### Task 6: Implement T-pose cross-section slicing for chin / shoulders / groin / hips

**Files:**
- Modify: `backend/scripts/blender_autorig.py` (`detect_landmarks` and helpers)

- [ ] **Step 1: Add slicing helper above `detect_landmarks`**

```python
def _slice_z(verts, n_slices=50):
    """Bucket world vertices into n_slices evenly-spaced Z bands.
    Returns list of (z_lo, z_hi, list_of_verts_in_band)."""
    if not verts:
        return []
    z_lo = min(v.z for v in verts)
    z_hi = max(v.z for v in verts)
    span = max(z_hi - z_lo, 1e-6)
    step = span / n_slices
    buckets = [[] for _ in range(n_slices)]
    for v in verts:
        idx = min(int((v.z - z_lo) / step), n_slices - 1)
        buckets[idx].append(v)
    return [(z_lo + i*step, z_lo + (i+1)*step, b) for i, b in enumerate(buckets)]


def _x_clusters(verts_in_slice, gap_threshold):
    """Sort slice vertices by X, find gaps wider than gap_threshold,
    return list of clusters (each a list of verts). Used to detect when
    legs are still separate (two clusters) vs merged at the pelvis (one)."""
    if not verts_in_slice:
        return []
    sorted_v = sorted(verts_in_slice, key=lambda v: v.x)
    clusters = [[sorted_v[0]]]
    for v in sorted_v[1:]:
        if v.x - clusters[-1][-1].x > gap_threshold:
            clusters.append([v])
        else:
            clusters[-1].append(v)
    return clusters
```

- [ ] **Step 2: Replace the T-pose branch in `detect_landmarks` with slicing-augmented detection**

In `detect_landmarks`, replace the `if is_t:` block with:

```python
    if is_t:
        verts = world_vertices(meshes)

        # 1. Wrists: vertex extremities (Task 5, unchanged).
        lw_v = _extreme_vertex(verts, axis=0, sign=+1)
        rw_v = _extreme_vertex(verts, axis=0, sign=-1)
        lw = Vector((lw_v.x, lw_v.y, lw_v.z))
        rw = Vector((rw_v.x, rw_v.y, rw_v.z))

        # 2. Ankles: bottom-cluster centroids split by X sign (Task 5).
        ankles = _bottom_cluster_centroids(verts)
        if ankles is not None:
            la, ra = ankles

        # 3. Slice the mesh; each slice's X-extent + cluster count drives the
        #    chin / shoulders / groin / hips landmarks.
        slices = _slice_z(verts, n_slices=50)
        gap_threshold = 0.05 * width

        # 3a. Shoulders: scan top → bottom, find first slice whose X-extent
        #     reaches ≥ 80% of the full mesh width (torso → torso+arms).
        shoulder_z = None
        shoulder_x_max = 0.0
        for z_lo, z_hi, band in reversed(slices):
            if not band:
                continue
            x_min = min(v.x for v in band)
            x_max = max(v.x for v in band)
            if (x_max - x_min) >= 0.80 * width:
                shoulder_z = (z_lo + z_hi) / 2
                shoulder_x_max = x_max
                shoulder_x_min = x_min
                break
        if shoulder_z is None:
            shoulder_z = mn.z + 0.82 * body_h
            shoulder_x_max = +0.18 * width
            shoulder_x_min = -0.18 * width

        # 3b. Chin: scan from shoulder upward, find first slice whose X-extent
        #     narrows below 30% of full width (head/neck region).
        chin_z = None
        for z_lo, z_hi, band in slices:
            if z_lo < shoulder_z + 0.05 * body_h:
                continue  # skip shoulder/torso bands
            if not band:
                continue
            x_min = min(v.x for v in band)
            x_max = max(v.x for v in band)
            if (x_max - x_min) <= 0.30 * width:
                chin_z = (z_lo + z_hi) / 2
                break
        if chin_z is None:
            chin_z = mn.z + 0.92 * body_h
        chin = Vector((0.0, 0.0, chin_z))

        # 3c. Groin: scan bottom → top, find highest slice with two distinct
        #     X-clusters (legs still separate). The slice above is the pelvis.
        groin_z = None
        leg_clusters = None
        for z_lo, z_hi, band in slices:
            clusters = _x_clusters(band, gap_threshold)
            if len(clusters) >= 2:
                groin_z = (z_lo + z_hi) / 2
                leg_clusters = clusters
                # don't break; want highest such slice
        if groin_z is None:
            groin_z = mn.z + 0.50 * body_h
        groin = Vector((0.0, 0.0, groin_z))

        # 3d. Shoulders: at shoulder_z, with X = max(L) / min(R).
        ls_v = Vector((shoulder_x_max, 0.0, shoulder_z))
        rs_v = Vector((shoulder_x_min, 0.0, shoulder_z))

        # 3e. Hips: at groin_z, X = centroid of each leg cluster.
        if leg_clusters and len(leg_clusters) >= 2:
            # Left = positive-X cluster, right = negative-X cluster.
            left_cluster  = max(leg_clusters, key=lambda c: sum(v.x for v in c)/len(c))
            right_cluster = min(leg_clusters, key=lambda c: sum(v.x for v in c)/len(c))
            lh_x = sum(v.x for v in left_cluster)  / len(left_cluster)
            rh_x = sum(v.x for v in right_cluster) / len(right_cluster)
        else:
            lh_x, rh_x = +0.10 * width, -0.10 * width
        lh = Vector((lh_x, 0.0, groin_z))
        rh = Vector((rh_x, 0.0, groin_z))

        # Override the AABB defaults for the slicing-derived landmarks.
        log(f"T-pose hybrid detection: shoulder_z={shoulder_z:.3f} chin_z={chin_z:.3f} groin_z={groin_z:.3f}")
    else:
        log("Non-T pose or low confidence — landmark detection falls back to AABB defaults")
        ls_v = None
        rs_v = None
        lh = None
        rh = None
```

Then below the `if/else`, build the final dict so that the slicing-derived `ls_v / rs_v / lh / rh` (when present) take precedence over the legacy heuristic:

```python
    six = {"chin": chin, "groin": groin,
           "left_wrist": lw, "right_wrist": rw,
           "left_ankle": la, "right_ankle": ra}
    fourteen_blender = _promote_legacy_landmarks(six)

    if is_t:
        # Override heuristic shoulders / hips with slice-derived values.
        # Elbow/knee remain heuristic (Approach 3 spec deferral).
        if ls_v is not None: fourteen_blender["left_shoulder"]  = ls_v
        if rs_v is not None: fourteen_blender["right_shoulder"] = rs_v
        if lh   is not None: fourteen_blender["left_hip"]       = lh
        if rh   is not None: fourteen_blender["right_hip"]      = rh
        # Elbows/knees are recomputed from the new shoulder/hip values.
        body_h_val = max(0.2, chin.z - groin.z)
        fourteen_blender["left_elbow"]  = ls_v + (lw - ls_v) * 0.55 + Vector((0.0, 0.05, -0.02))
        fourteen_blender["right_elbow"] = rs_v + (rw - rs_v) * 0.55 + Vector((0.0, 0.05, -0.02))
        fourteen_blender["left_knee"]   = Vector((la.x * 0.97, la.y - 0.04, (groin.z + la.z)/2 + 0.02))
        fourteen_blender["right_knee"]  = Vector((ra.x * 0.97, ra.y - 0.04, (groin.z + ra.z)/2 + 0.02))

    return {k: to_three(v) for k, v in fourteen_blender.items()}
```

- [ ] **Step 3: Smoke test with the user's robot FBX**

Run the same Task 4 smoke pipeline. Inspect `landmarks.json`:

- `chin` Z should sit slightly below the very top of the head, NOT at 1.84 default.
- `left_shoulder` and `right_shoulder` Z should be lower than 1.64 (82% of 2.0); for the robot screenshot example, more like 1.5.
- `left_hip` X should match the actual leg position, not ankle X projected upward.

- [ ] **Step 4: Commit**

```bash
git add backend/scripts/blender_autorig.py
git commit -m "feat(rigging): T-pose cross-section slicing for chin/shoulder/groin/hip"
```

---

### Task 7: Wire detector into auto-rig flow (always use detected landmarks)

**Files:**
- Modify: `backend/scripts/blender_autorig.py` (`main`, where the AUTO branch lives, ~line 1014)

- [ ] **Step 1: Replace the AUTO/LANDMARK branch**

Find this block in `main()` (around line 1010-1023):

```python
log(f"Mode:   {'LANDMARK' if args.landmarks else 'AUTO'}")
…
if args.landmarks:
    …
    place_bones_from_landmarks(metarig, json.loads(args.landmarks), mesh_h)
```

Replace the conditional with:

```python
if args.landmarks:
    user_landmarks = json.loads(args.landmarks)
    log(f"Mode: LANDMARK (user-supplied {len(user_landmarks)} keys)")
    place_bones_from_landmarks(metarig, user_landmarks, mesh_h)
else:
    auto_landmarks = detect_landmarks(meshes, pose=detected_pose)
    log(f"Mode: AUTO (detected {len(auto_landmarks)} landmarks)")
    place_bones_from_landmarks(metarig, auto_landmarks, mesh_h)
```

(Note: `detected_pose` is the local you set in Task 5 Step 3.)

- [ ] **Step 2: End-to-end smoke test against the failing FBX from May 2026**

Upload the same robot FBX via `/upload`. Wait for rig completion. Open editor; the wrist bones should now match the model's actual hands (because place_bones_from_landmarks ran with detected wrists at extreme +X / -X, not human-ratio defaults).

- [ ] **Step 3: Commit**

```bash
git add backend/scripts/blender_autorig.py
git commit -m "feat(rigging): auto-rig now uses detected landmarks (no more uniform metarig scale)"
```

---

### Task 8: Read landmarks JSON in Celery task and persist to `RiggedModel.landmarks`

**Files:**
- Modify: `backend/apps/rigging/tasks.py`

- [ ] **Step 1: Read existing `_run_rig_pipeline` to find the Blender invocation**

```bash
grep -n "blender_autorig\|--bones\|--input" backend/apps/rigging/tasks.py | head
```

- [ ] **Step 2: Add `--landmarks-out <path>` to the Blender command and read the result**

In `_run_rig_pipeline`, after `bone_data_path` is constructed, add a parallel `landmarks_path`:

```python
landmarks_path = Path(tmp) / "landmarks.json"
```

Add `"--landmarks-out", str(landmarks_path),` to the `blender ... --` argv (the same list that already contains `"--bones", str(bone_data_path)`).

After the subprocess succeeds and `bone_data` is loaded, add:

```python
if landmarks_path.exists():
    rig.landmarks = json.loads(landmarks_path.read_text())
```

(`rig` is the `RiggedModel` instance that the surrounding code already mutates; `rig.save()` is already called once the pipeline completes — no additional save call needed unless the existing flow doesn't save the model after this block. Verify by reading the surrounding context.)

- [ ] **Step 3: Smoke test via /upload**

Upload any FBX. After completion:

```bash
python manage.py shell -c "
from apps.rigging.models import RiggedModel
r = RiggedModel.objects.latest('created_at')
print(r.id, list((r.landmarks or {}).keys()))
"
```

Expected: 14 keys printed.

- [ ] **Step 4: Commit**

```bash
git add backend/apps/rigging/tasks.py
git commit -m "feat(rigging): persist detected landmarks to RiggedModel"
```

---

### Task 9: Add `GET /api/v1/rigs/{id}/landmarks/` endpoint

**Files:**
- Modify: `backend/apps/rigging/views.py`

- [ ] **Step 1: Add the action method on `RiggedModelViewSet`**

In `backend/apps/rigging/views.py`, locate the `rerig_landmarks` action (around line 270) and add a new action above it:

```python
@extend_schema(
    summary="Get the 14 detected landmarks for the rig editor",
    description=(
        "Returns 14 anatomical landmarks (chin, groin, L/R × shoulder, "
        "elbow, wrist, hip, knee, ankle) in three.js editor space. "
        "Populated when the rig was generated; if the rig predates the "
        "feature, returns AABB-default landmarks instead of 404."
    ),
)
@action(detail=True, methods=["get"], url_path="landmarks")
def landmarks(self, request, id=None):
    rig = self.get_object()
    if rig.landmarks:
        return Response({"landmarks": rig.landmarks})
    # Legacy rig with no detected landmarks — return AABB defaults so the
    # editor still has 14 draggable points to start from.
    from .legacy_landmarks import default_landmarks_for_rig
    return Response({"landmarks": default_landmarks_for_rig(rig)})
```

- [ ] **Step 2: Make the endpoint public + skip the JWT authenticator (matching `status` and `retrieve`)**

Look for the existing pattern in the same file — `status` action is annotated with `permission_classes=[AllowAny]` and the viewset's `get_authenticators` skips JWT for unauthenticated public actions. Add `landmarks` to whichever set governs that. Concretely (in `get_authenticators`):

```python
if self.action in ("status", "retrieve", "landmarks"):
    return []
```

And on the action decorator:

```python
@action(detail=True, methods=["get"], url_path="landmarks",
        permission_classes=[AllowAny], authentication_classes=[])
def landmarks(self, request, id=None):
    ...
```

- [ ] **Step 3: Add the `default_landmarks_for_rig` helper**

Create `backend/apps/rigging/legacy_landmarks.py`:

```python
"""Default 14-key landmarks for rigs that pre-date the auto-detection
feature. Computed from a unit-height humanoid silhouette so the editor
has draggable starting points instead of all-zero coordinates.
"""

DEFAULT_LANDMARKS_UNIT_HEIGHT = {
    # three.js editor space, model normalized to 2.0 units tall
    "chin":           [ 0.00, 1.84,  0.00],
    "groin":          [ 0.00, 1.00,  0.00],
    "left_shoulder":  [ 0.20, 1.64,  0.00],
    "right_shoulder": [-0.20, 1.64,  0.00],
    "left_elbow":     [ 0.50, 1.64,  0.05],
    "right_elbow":    [-0.50, 1.64,  0.05],
    "left_wrist":     [ 0.80, 1.64,  0.00],
    "right_wrist":    [-0.80, 1.64,  0.00],
    "left_hip":       [ 0.10, 1.00,  0.00],
    "right_hip":      [-0.10, 1.00,  0.00],
    "left_knee":      [ 0.10, 0.50,  0.00],
    "right_knee":     [-0.10, 0.50,  0.00],
    "left_ankle":     [ 0.10, 0.00,  0.00],
    "right_ankle":    [-0.10, 0.00,  0.00],
}


def default_landmarks_for_rig(rig):
    """Return the same defaults regardless of rig — three.js space is
    normalized to a fixed display height. The editor will autoFit and
    rescale the user's drags back into mesh-space on submit."""
    return dict(DEFAULT_LANDMARKS_UNIT_HEIGHT)
```

- [ ] **Step 4: Smoke test the new endpoint**

```bash
curl http://localhost:8000/api/v1/rigs/<rig-id>/landmarks/
```

Expected: HTTP 200, JSON `{"landmarks": {…}}` with 14 keys.

- [ ] **Step 5: Commit**

```bash
git add backend/apps/rigging/views.py backend/apps/rigging/legacy_landmarks.py
git commit -m "feat(rigging): GET /landmarks/ returns 14 detected (or default) landmarks"
```

---

### Task 10: Update frontend API surface (types + getLandmarks call)

**Files:**
- Modify: `frontend/src/lib/api.ts`

- [ ] **Step 1: Add the new types**

Near the existing `ModelRotation` / `ModelRotationQuaternion` types in `lib/api.ts`, add:

```ts
export const LANDMARK_KEYS = [
  "chin", "groin",
  "left_shoulder", "right_shoulder",
  "left_elbow", "right_elbow",
  "left_wrist", "right_wrist",
  "left_hip", "right_hip",
  "left_knee", "right_knee",
  "left_ankle", "right_ankle",
] as const;

export type LandmarkKey = typeof LANDMARK_KEYS[number];

export type LandmarkPoint = [number, number, number]; // three.js editor space

export type LandmarkSet = Record<LandmarkKey, LandmarkPoint>;
```

- [ ] **Step 2: Add the API call**

After the existing `getRigStatus` function in the same file:

```ts
export const getLandmarks = (id: string) =>
  api.get<{ landmarks: LandmarkSet }>(`/rigs/${id}/landmarks/`);
```

If a `rerigLandmarks` function already exists, leave its signature alone (the backend accepts both 6 and 14 keys). If you find it sending 6, update to send the full 14 — but only after Task 11 has the editor producing 14.

- [ ] **Step 3: Typecheck**

```bash
cd frontend && npx tsc --noEmit
```

Expected: clean.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/lib/api.ts
git commit -m "feat(frontend): add LandmarkKey types + getLandmarks API call"
```

---

### Task 11: Update `LandmarkEditor` to render 14 grouped points

**Files:**
- Modify: `frontend/src/components/LandmarkEditor.tsx`

This is the biggest UI change. Read the existing component first to understand the current 6-landmark drag pattern, then expand to 14 with grouping.

- [ ] **Step 1: Read the existing 6-landmark implementation**

```bash
grep -n "chin\|groin\|wrist\|ankle" frontend/src/components/LandmarkEditor.tsx | head -40
```

Map out: where are the 6 landmark names hard-coded, what colour/sphere mesh represents each, where does the side panel render its labels, where is the submit handler that POSTs to `/rerig-landmarks/`.

- [ ] **Step 2: Replace the hard-coded 6-landmark list with the 14-key array**

Where the existing component has e.g.:

```ts
const LANDMARKS = ["chin", "left_wrist", "right_wrist", "groin", "left_ankle", "right_ankle"];
```

Replace with an import + a grouping declaration:

```ts
import { LANDMARK_KEYS, type LandmarkKey, type LandmarkSet } from "@/lib/api";

const LANDMARK_GROUPS: Array<{ label: string; color: string; keys: LandmarkKey[] }> = [
  { label: "Head",    color: "#ffd166", keys: ["chin"] },
  { label: "Torso",   color: "#06d6a0", keys: ["groin"] },
  { label: "Arm L",   color: "#118ab2", keys: ["left_shoulder",  "left_elbow",  "left_wrist"]  },
  { label: "Arm R",   color: "#118ab2", keys: ["right_shoulder", "right_elbow", "right_wrist"] },
  { label: "Leg L",   color: "#ef476f", keys: ["left_hip",  "left_knee",  "left_ankle"]  },
  { label: "Leg R",   color: "#ef476f", keys: ["right_hip", "right_knee", "right_ankle"] },
];
```

- [ ] **Step 3: Replace the initial-state hook with a fetch from `/landmarks/`**

Where the editor currently initialises landmark positions (probably `useState({chin: [0,0,0], …})`), replace with:

```ts
import { getLandmarks } from "@/lib/api";

// Inside the component:
const [landmarks, setLandmarks] = useState<LandmarkSet | null>(null);

useEffect(() => {
  let cancelled = false;
  getLandmarks(rigId).then(({ data }) => {
    if (!cancelled) setLandmarks(data.landmarks);
  });
  return () => { cancelled = true; };
}, [rigId]);

if (!landmarks) return <div>Loading landmarks…</div>;
```

- [ ] **Step 4: Render all 14 draggable spheres**

Wherever the existing component renders a `<group>` of 6 spheres (one per landmark), expand to iterate `LANDMARK_KEYS`. Each sphere uses the colour of its group:

```tsx
{LANDMARK_GROUPS.flatMap(group =>
  group.keys.map(key => (
    <DraggableSphere
      key={key}
      label={key}
      color={group.color}
      position={landmarks[key]}
      onDrag={(next) => setLandmarks(prev => ({ ...prev!, [key]: next }))}
    />
  ))
)}
```

(Adapt `DraggableSphere` to whatever the existing component uses for its 6 handles — a `<mesh>` with click-and-drag, a Drei `<Sphere>`, or a custom helper. The pattern is the same for 14.)

- [ ] **Step 5: Replace the side panel with grouped accordions / sections**

If the existing panel just lists 6 labels, swap it for a `LANDMARK_GROUPS.map` that renders a labelled section per group with the keys inside. Each row may show the current XYZ (read-only is fine — drag is in the 3D scene).

```tsx
<aside style={{ display: "grid", gap: "0.6rem" }}>
  {LANDMARK_GROUPS.map(group => (
    <section key={group.label}>
      <h4 style={{ color: group.color }}>{group.label}</h4>
      <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
        {group.keys.map(k => (
          <li key={k} style={{ fontSize: ".8rem", color: "#aaa" }}>
            {k}: ({landmarks[k].map(n => n.toFixed(2)).join(", ")})
          </li>
        ))}
      </ul>
    </section>
  ))}
</aside>
```

- [ ] **Step 6: Update the submit handler to POST 14 keys**

Find where the editor currently POSTs `/rerig-landmarks/`. The body shape is `{landmarks: {key: [x,y,z], …}}`. With `landmarks` already a `LandmarkSet` (14 keys), the submit code is unchanged structurally:

```ts
import { api } from "@/lib/api";
await api.post(`/rigs/${rigId}/rerig-landmarks/`, { landmarks });
```

Confirm via DevTools that the POST body has 14 keys.

- [ ] **Step 7: Typecheck and lint**

```bash
cd frontend && npx tsc --noEmit && npx eslint src/components/LandmarkEditor.tsx
```

Expected: clean.

- [ ] **Step 8: Manual UI test**

In a browser:
1. Upload a model.
2. Wait for rig to complete.
3. Click "Edit rig placement".
4. Confirm 14 spheres render in the 3D scene (chin, groin, 3 per arm, 3 per leg).
5. Drag one (e.g., left_wrist) — the sphere moves; side panel updates.
6. Click "Re-rig". Confirm the rig regenerates with the new landmark.

- [ ] **Step 9: Commit**

```bash
git add frontend/src/components/LandmarkEditor.tsx
git commit -m "feat(frontend): LandmarkEditor renders 14 grouped landmarks"
```

---

### Task 12: End-to-end verification with the failing-case FBX

**Files:** none (verification only)

- [ ] **Step 1: Upload the robot FBX from the May 2026 debugging session**

Use the same FBX that produced the upside-down rig + arm-too-long screenshot. Upload via `/upload` with no manual rotation in the preview (the auto-orient + backend correction landed earlier in this conversation should still work).

- [ ] **Step 2: Inspect the rig log**

`GET /api/v1/rigs/<id>/`. Find these new lines in `rig_log`:

- `T-pose hybrid detection: shoulder_z=… chin_z=… groin_z=…` — confirms the slicing branch fired.
- `Wrote 14 detected landmarks → /tmp/.../landmarks.json` — confirms the file was written.
- `Mode: AUTO (detected 14 landmarks)` — confirms the auto-rig used them.

- [ ] **Step 3: Inspect the resulting GLB**

Open the GLB in the editor (the existing "View model" tab). The cyan rig bones should now match the model's actual proportions — wrist bones at the model's hand position, hip bones inside the model's hip mesh, etc.

- [ ] **Step 4: Open the landmark editor and inspect**

`/editor/<id>` → "Edit rig placement". 14 spheres should render at the detected positions. Drag one to verify interactivity. Click "Re-rig" to confirm the rerig path also works with 14 keys.

- [ ] **Step 5: If anything is off — document and triage**

If the rig still misfits in a specific way, note which landmark is wrong:
- Wrong wrist X → likely a non-T-pose mesh; classifier mis-fired. Check `pose` log line.
- Shoulders too high/low → slicing threshold needs tuning; widen the 80% width threshold.
- Hips at wrong X → leg cluster gap detection failed; adjust `gap_threshold`.

These are tunable constants in `detect_landmarks` — single-line fixes once the failure mode is identified.

- [ ] **Step 6: Final commit if any tunings were applied**

```bash
git add backend/scripts/blender_autorig.py
git commit -m "tune(rigging): landmark detection thresholds for screenshot-case FBX"
```

---

## Self-Review

Verifying the plan against the spec:

**Spec section coverage:**
- §Architecture Unit A (detector) → Tasks 4, 5, 6 ✓
- §Architecture Unit B (consumer) → Tasks 2, 3 ✓
- §Architecture Unit C (editor) → Tasks 10, 11 ✓
- §Data flow upload-side → Tasks 7, 8 ✓
- §Data flow editor-side → Tasks 9, 10, 11 ✓
- §Schema (LANDMARK_KEYS) → Task 2 (Python), Task 10 (TS) ✓
- §Schema (DB JSONField) → Task 1 ✓
- §Schema (API endpoints) → Task 9 ✓
- §Edge cases (legacy rigs returning AABB defaults) → Task 9 Step 3 ✓
- §Edge cases (non-T-pose fallback) → Task 5 Step 2 (`is_t` gate) ✓
- §Migration plan → Tasks land in order; no DB migration needed for legacy rows beyond null default ✓

**Placeholder scan:** No "TBD", no "implement later", no "similar to Task N", no naked "handle errors" steps. Each step has the concrete code or command. The frontend Task 11 leans on "find the existing pattern" for `DraggableSphere` because the existing UI is unknown — the worker is told exactly which file to read first to learn the pattern.

**Type consistency:** `LANDMARK_KEYS` tuple identical between Task 2 (Python) and Task 10 (TS). `LandmarkSet` keys match the 14 names. `place_bones_from_landmarks` reads landmark dict keys identical to those produced by `detect_landmarks` and `_promote_legacy_landmarks`. `RiggedModel.landmarks` is a `JSONField` storing the same shape the editor + endpoint pass around.

No issues to fix.

---

## Execution Handoff

Plan complete and saved to `Docs/plans/2026-05-06-14-landmark-detection.md`. Two execution options:

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration.

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints.

Which approach?
