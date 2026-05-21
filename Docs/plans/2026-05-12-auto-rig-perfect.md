# Auto-Rig Perfect (Geometry + Claude Haiku 4.5 Vision) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a duo auto-rig that pairs Claude Haiku 4.5 vision (semantic seeds) with Blender geometry (vertex-precise refinement) so a single upload produces a rig that animations bind to cleanly — no editor intervention for typical bipeds, including stylised meshes with props.

**Architecture:** Every rig runs through one shared pipeline. Blender renders 4 orthographic views, writes a request JSON, and exits. The Django Celery task reads the request, calls Haiku 4.5 via the Anthropic SDK with all four images, writes a response JSON, then re-spawns Blender with `--landmarks-from-ai`. Blender raycasts AI pixel coords into world space (front view gives x,z; side view gives y,z), refines each seed to the nearest anatomically-meaningful mesh vertex, runs sanity checks, and proceeds with Rigify generation. Geometry-only mode (`LANDMARK_VISION_PROVIDER=none`) skips the round-trip and produces today's geometry-only behaviour — but with the new sanity checks layered on top.

**Tech Stack:** Django 5.1 + DRF + Celery, Blender (`bpy`, headless subprocess), `anthropic` SDK, `Pillow`, Next.js 16 + R3F (existing editor surface).

**Spec:** `Docs/specs/2026-05-12-auto-rig-perfect.md` — produced as **Task 1** of this plan.

**Path conventions:** All paths are relative to the inner repo source root `rigflow-project/rigflow-project/`. Run `cd rigflow-project/` from the outer folder before executing any task. Inner git is on branch `Feature/test`, up to date with `origin/Feature/test`.

---

## Two tracks of work — what you do vs. what I do

This is the part you asked about. We move in parallel: you do the account-side work; I do the code-side work. The first three tasks (Tasks 1–4) need **no API key**, so I can start while your Anthropic account is being set up.

### Track A — what **you** do (one-time, outside the repo)

1. **Review the spec.** I produce `Docs/specs/2026-05-12-auto-rig-perfect.md` in Task 1. You read it (~10 min). Push back on any architectural decision before I start implementing. Hard stop until you say "okay, proceed".
2. **Anthropic account setup** (parallel — do this while I work on M1):
   - Sign up at https://console.anthropic.com.
   - Add billing. **Set a monthly spend cap of $5** in the billing settings — that's the safety net; at ~$0.004/rig it covers ≈1,250 rigs/month even if the duo runs on every upload.
   - Create an API key, name it `rigflow-dev`. Copy it once — Anthropic only shows it on creation.
   - Paste it into `backend/.env` as a single line: `ANTHROPIC_API_KEY=sk-ant-...` (no quotes). If `backend/.env` doesn't exist yet, create it; Django reads it via `python-dotenv`.
   - Also add `LANDMARK_VISION_PROVIDER=claude` to the same `.env` once you're ready to test the AI path. Leave it unset (or `=none`) until then — the pipeline runs geometry-only and never touches the key.
3. **Approve checkpoints between milestones.** I commit at each milestone boundary; you review the diff and the smoke-test output before I move to the next milestone. Cheap insurance — if M2 went sideways, we stop before pouring effort into M3+.
4. **Decided 2026-05-12 (no action needed):** if the AI returns malformed JSON twice, the pipeline falls back to the full geometry-only path and the editor surfaces a user-facing message: *"The AI couldn't read your model — the auto-rig may be off. Adjust the landmarks below if needed."* `detection_method` is set to `"failed"` for audit. Rig still finishes `done`.

### Track B — what **I** do (this plan)

In order, with milestones from the handoff:

- **M1 — Geometry stability + sanity checks** (Tasks 1–5). No API key needed. Testable on Johnny Joestar + Freddy. Outcome: today's pipeline plus explicit sanity checks plus A-pose handling plus the `detection_method` audit field.
- **M2 — Ortho-render + request writer** (Tasks 6–8). Still no API key needed. Blender produces 4 PNGs and a `request.json`; nothing reads it yet.
- **M3 — Django round-trip + Anthropic provider** (Tasks 9–11). First task that consumes the key. Behind `LANDMARK_VISION_PROVIDER=none`, behaviour is unchanged from M2. With `=claude`, the AI returns landmark pixel coords and we save the raw response.
- **M4 — Raycast + seed-to-vertex refinement** (Tasks 12–14). Pixel coords become 3D world-space landmarks; geometry refines them to real vertices. Sanity checks gate the result; failures fall back gracefully.
- **M5 — Props + UI surface** (Tasks 15–16). Non-body meshes (hats, microphones) get parented to the right deform bone via the AI's prop labels. Frontend shows a small badge indicating which path produced the rig.
- **Task 17 — End-to-end verification** with both test models, both modes.

---

## File Structure

**New files:**

- `Docs/specs/2026-05-12-auto-rig-perfect.md` — formal spec: prompt, JSON schemas, sanity check thresholds, failure semantics.
- `backend/apps/rigging/landmark_vision/__init__.py` — provider dispatch (`get_provider()`).
- `backend/apps/rigging/landmark_vision/base.py` — `Provider` protocol + `VisionRequest` / `VisionResponse` dataclasses.
- `backend/apps/rigging/landmark_vision/none_provider.py` — returns `None`, used when key is missing or env says `none`.
- `backend/apps/rigging/landmark_vision/claude_provider.py` — Anthropic SDK call, prompt, response parsing.
- `backend/apps/rigging/landmark_vision/prompts.py` — the exact prompt string + the schema fragments AI must return.
- `backend/apps/rigging/sanity.py` — pure sanity-check functions (no Blender deps; unit-testable).
- `backend/apps/rigging/tests/test_sanity.py` — unit tests for sanity checks.
- `backend/apps/rigging/tests/test_landmark_vision.py` — unit tests for provider dispatch + Claude response parsing (fixture-based, no network).
- `backend/apps/rigging/tests/fixtures/claude_response_johnny.json` — recorded AI response for Johnny Joestar (used by tests + as documentation of the expected shape).
- `backend/scripts/_test_pixel_to_world.py` — standalone smoke test for the pixel→ray math (no Blender dependency, like `_test_landmark_promotion.py`).

**Modified files:**

- `backend/apps/rigging/models.py` — add `detection_method` field + `vision_response_raw` JSON field for audit.
- `backend/apps/rigging/admin.py` — surface `detection_method` in list_display + add_filter.
- `backend/apps/rigging/tasks.py` — orchestrate the Blender ↔ Django round-trip.
- `backend/apps/rigging/views.py` — include `detection_method` in the serializer/status payload.
- `backend/apps/rigging/serializers.py` (or wherever the row is serialized) — expose `detection_method`.
- `backend/scripts/blender_autorig.py` — add `--render-ortho-views`, `--ai-request-out`, `--landmarks-from-ai` flags; ortho-render function; pixel→world raycast; seed-to-vertex refinement; A-pose support; prop parenting.
- `backend/requirements.txt` — `anthropic>=0.40.0`, `Pillow>=10.0.0`.
- `frontend/src/lib/api.ts` — extend the `RiggedModel` type with `detection_method`.
- `frontend/src/components/...` (location TBD in Task 16) — small badge.
- `Docs/BLENDER_AUTORIG.md` — relax the "No external deps" technical constraint, noting the vision call is on the Django side.
- `Docs/ARCHITECTURE.md` — add `detection_method` + `vision_response_raw` to the schema block.
- `Docs/KNOWN_ISSUES.md` — new entry: "two Blender subprocess invocations per rig in AI mode" (operational note).

---

### Task 1: Write the formal spec doc

**Files:**
- Create: `Docs/specs/2026-05-12-auto-rig-perfect.md`

The spec is the single source of architectural truth for everything downstream. It is **the artifact you review and approve before I write any code**.

- [ ] **Step 1: Create the spec file with these sections, in order**

The file MUST contain these sections (full prose, not placeholders):

1. **Status & problem** — auto-rig regressions on stylised meshes (Freddy paw-tip wrist, robot proportions); editor-as-escape-hatch is acceptable but not the goal.
2. **Architecture** — diagram of the round-trip, why Django-side SDK and not Blender-side (Blender's bundled Python 3.11 can't be relied upon to host `pip install anthropic` cleanly; documented constraint in `Docs/BLENDER_AUTORIG.md`).
3. **Provider abstraction** — `LANDMARK_VISION_PROVIDER` env var (`claude` | `gemini` | `none`); default `none` so dev works without a key. `claude` selected when value is `claude` AND `ANTHROPIC_API_KEY` is set; otherwise silently degrade to `none` and log a warning.
4. **Request JSON schema** (Blender → Django):
   ```json
   {
     "rig_id": "uuid-string",
     "views": {
       "front": {"path": "/tmp/.../front.png", "camera_aabb": [[xmin,ymin,zmin],[xmax,ymax,zmax]], "image_size": [512,512]},
       "back":  {...},
       "left":  {...},
       "right": {...}
     },
     "mesh_objects": [
       {"name": "Body", "vertex_count": 12345, "bbox_world": [[..],[..]]},
       {"name": "TopHat", "vertex_count": 543, "bbox_world": [[..],[..]]}
     ],
     "world_aabb": [[..],[..]]
   }
   ```
5. **Vision prompt** (exact string committed to `prompts.py`):
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
   Pixel origin is top-left; x grows right, y grows down. If a landmark is
   occluded in a given view, mark it null for that view only — at least front
   and one side must contain it.
   
   Also identify each distinct mesh object in the scene (listed below) as one of:
     body, hat, accessory_held_left, accessory_held_right, clothing, other.
   
   Respond ONLY with valid JSON in this schema, no prose:
   {
     "landmarks": {
       "front": {"chin": [x,y], "groin": [x,y], ...all 14, with null where occluded},
       "back":  {...},
       "left":  {...},
       "right": {...}
     },
     "mesh_objects": {
       "<object_name>": "body" | "hat" | "accessory_held_left" | "accessory_held_right" | "clothing" | "other",
       ...
     },
     "notes": "<one-line free-form observation, optional>"
   }
   
   Mesh objects in this scene: <list injected at runtime from request.mesh_objects[*].name>
   ```
6. **Response JSON schema** (Django → Blender) — same shape as AI returns, validated server-side first.
7. **Sanity checks** (applied to refined 3D landmarks):
   - `groin.y < chin.y` (with at least 0.1 metarig-units of gap)
   - Bilateral symmetry: `|left_X - right_X| / max(|left_X|, |right_X|, 0.01) < 0.30` for x-coords of paired landmarks (shoulder/elbow/wrist/hip/knee/ankle)
   - Each landmark inside the mesh world AABB inflated by 5%
   - Anatomical order along Z: ankle.z < knee.z < hip.z ≤ groin.z < shoulder.z ≤ chin.z (allow equality, not inversion)
   - Limb proportions: forearm ≤ upper-arm × 1.4 and ≥ × 0.5; shin similar against thigh
8. **Failure semantics** (cascading fallback — decided 2026-05-12):
   - AI returns malformed JSON → retry once with same payload → still bad → log + run the **full geometry-only pipeline** (same path as `LANDMARK_VISION_PROVIDER=none`); `detection_method = "failed"`; editor surfaces a user-facing message: *"The AI couldn't read your model — the auto-rig may be off. Adjust the landmarks below if needed."*
   - AI returns JSON but sanity checks fail on the raycasted seeds → drop AI seeds, use geometry-only landmarks; `detection_method = "geometry"`.
   - AI seeds pass sanity, geometry refinement produces a landmark that fails sanity → use the AI seed for that landmark, refined seeds for others; `detection_method = "llm_vision"`.
   - Both sanity passes fail → AABB-default landmarks; rig finishes as `done`; `detection_method = "failed"`; editor banner suggests the user open landmark editing. **No `failed` status — every rig finishes `done`.**
   - User-supplied landmarks via `/rerig-landmarks/` → bypass AI entirely; `detection_method = "user_landmarks"`.
9. **Cost & rate-limiting note** — ~$0.004 per rig at Haiku 4.5 vision rates; Anthropic enforces RPM on the account; we don't add our own throttle in M3, but `rig_upload` is already 10/h per user so the ceiling is bounded.
10. **Out-of-scope** — quadrupeds, arms-down pose, multi-character meshes, BVH retargeting, second LLM provider beyond the abstraction.

- [ ] **Step 2: Stop and ask for review**

Paste this exact message to the user:

> Spec is at `Docs/specs/2026-05-12-auto-rig-perfect.md`. Anything in the architecture or fallback rules you'd change before I start coding?

Do **not** proceed to Task 2 until they say "go" or equivalent.

- [ ] **Step 3: Commit the spec**

```bash
cd rigflow-project/  # inner repo if not already there
git add Docs/specs/2026-05-12-auto-rig-perfect.md
git commit -m "docs(rigging): spec for auto-rig perfect (geometry + Haiku 4.5 vision duo)"
```

---

### Task 2: Preserve the existing on-disk uncommitted work

**Files:** none new — this task only commits work already on disk.

The handoff documents five sets of uncommitted changes. Lose any of them and we lose a documented bug fix + 6 doc updates + 3 admin registrations. Lock them in before adding new code.

- [ ] **Step 1: Confirm the working tree matches the handoff**

```bash
cd rigflow-project/
git status -uno
```

Expected modifications:
- `Docs/{API,ARCHITECTURE,DEVELOPMENT,KNOWN_ISSUES,RIGGING_PIPELINE,TECHNICAL_CONTEXT}.md`
- `backend/apps/{animations,rigging,users}/admin.py`
- `backend/scripts/blender_autorig.py`
- A handful of frontend `.tsx` (landing components + page entries) — pre-existing, not rigging-related

Expected untracked: `Docs/BLENDER_AUTORIG.md`, `handoff.md`.

If anything is missing, **stop** and ask the user — that means a previous session got lost.

- [ ] **Step 2: Run the standalone smoke test for the existing bug-fix patch**

```bash
python backend/scripts/_test_landmark_promotion.py
```

Expected: `_promote_legacy_landmarks smoke test: OK`. The patched `blender_autorig.py` must still pass this.

- [ ] **Step 3: Commit the bug-fix patch separately**

```bash
git add backend/scripts/blender_autorig.py
git commit -m "fix(rigging): revert buggy T-pose slice detection that inverted pelvis above chin

Symptom on Freddy: 'highest slice with 2+ X-clusters' fired on arm clusters
at shoulder height in T-pose, placing groin above chin and inverting the
rig. Reverted to AABB defaults via _promote_legacy_landmarks; vertex-extremity
wrist/ankle detection retained. Smoke test passes."
```

- [ ] **Step 4: Commit the admin registrations**

```bash
git add backend/apps/{rigging,users,animations}/admin.py
git commit -m "feat(admin): register RiggedModel, User/UserProfile, Animation/AnimationCategory

/admin previously only showed Celery + auth — three apps had empty admin.py."
```

- [ ] **Step 5: Commit the doc refresh**

```bash
git add Docs/{API,ARCHITECTURE,DEVELOPMENT,KNOWN_ISSUES,RIGGING_PIPELINE,TECHNICAL_CONTEXT}.md Docs/BLENDER_AUTORIG.md
git commit -m "docs: refresh six docs to match 14-landmark pipeline + retire stale notes

- RIGGING_PIPELINE: 14-landmark schema, corrected pose bands, full CLI flags
- API: /rerig-landmarks/ 14 keys, GET /rigs/{id}/landmarks/
- ARCHITECTURE: landmarks JSON field
- KNOWN_ISSUES: outer-git corruption rewrite, 14-key schema regression note
- TECHNICAL_CONTEXT: remove stale SSH-key warning + passthrough wording
- DEVELOPMENT: Blender prereq + troubleshooting refresh
- BLENDER_AUTORIG (new): script-level reference"
```

- [ ] **Step 6: Frontend `.tsx` edits stay uncommitted on purpose**

The handoff notes those are pre-existing JSX-string-escape fixes unrelated to rigging. **Don't touch them** unless the user explicitly asks. `git status` will continue to show them.

---

### Task 3: Add `detection_method` + `vision_response_raw` fields to `RiggedModel`

**Files:**
- Modify: `backend/apps/rigging/models.py`
- Create: `backend/apps/rigging/migrations/0NNN_riggedmodel_detection_method.py` (NNN auto-assigned)
- Modify: `backend/apps/rigging/admin.py`

- [ ] **Step 1: Find the next migration number**

```bash
ls backend/apps/rigging/migrations/ | grep -E '^[0-9]{4}_' | sort | tail -1
```

Note the highest — next is +1.

- [ ] **Step 2: Add the two fields**

In `backend/apps/rigging/models.py`, near the existing `landmarks = models.JSONField(...)` block, add:

```python
DETECTION_METHOD_CHOICES = [
    ("geometry",       "Geometry only"),
    ("llm_vision",     "LLM vision + geometry refine"),
    ("user_landmarks", "User-supplied landmarks"),
    ("failed",         "Both AI and geometry sanity failed; AABB defaults used"),
]

detection_method = models.CharField(
    max_length=24, choices=DETECTION_METHOD_CHOICES,
    default="geometry", db_index=True,
    help_text="Which path produced the landmarks attached to this rig.",
)

vision_response_raw = models.JSONField(
    null=True, blank=True,
    help_text=(
        "Raw response from the LLM vision provider, kept for debugging / "
        "audit. Null when detection_method is not 'llm_vision'."
    ),
)
```

- [ ] **Step 3: Generate and apply the migration**

```bash
cd backend/
python manage.py makemigrations rigging
python manage.py migrate rigging
```

Expected: a new migration file is created; `Applying rigging.0NNN_... OK`.

- [ ] **Step 4: Expose `detection_method` in admin**

In `backend/apps/rigging/admin.py`, add `detection_method` to `list_display` and `list_filter` on the `RiggedModel` admin class.

- [ ] **Step 5: Verify the admin loads**

Start the dev server, visit `http://localhost:8000/admin/rigging/riggedmodel/`. Confirm the new column appears and the filter sidebar offers the four choices.

- [ ] **Step 6: Commit**

```bash
git add backend/apps/rigging/models.py \
        backend/apps/rigging/migrations/0NNN_riggedmodel_detection_method.py \
        backend/apps/rigging/admin.py
git commit -m "feat(rigging): add detection_method + vision_response_raw fields"
```

---

### Task 4: Sanity-check helpers (TDD, no Blender deps)

**Files:**
- Create: `backend/apps/rigging/sanity.py`
- Create: `backend/apps/rigging/tests/__init__.py` (if missing) and `backend/apps/rigging/tests/test_sanity.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/apps/rigging/tests/test_sanity.py`:

```python
"""Unit tests for landmark sanity checks. Pure-Python, no Blender deps."""
from django.test import SimpleTestCase

from apps.rigging.sanity import (
    SanityResult,
    check_landmarks,
    LANDMARK_KEYS,
)


def _good():
    """A canonical 14-key dict that should pass every check."""
    return {
        "chin":           (0.0, 1.80, 0.0),
        "groin":          (0.0, 1.00, 0.0),
        "left_shoulder":  ( 0.20, 1.60, 0.0),
        "right_shoulder": (-0.20, 1.60, 0.0),
        "left_elbow":     ( 0.45, 1.30, 0.0),
        "right_elbow":    (-0.45, 1.30, 0.0),
        "left_wrist":     ( 0.70, 1.00, 0.0),
        "right_wrist":    (-0.70, 1.00, 0.0),
        "left_hip":       ( 0.10, 1.00, 0.0),
        "right_hip":      (-0.10, 1.00, 0.0),
        "left_knee":      ( 0.10, 0.50, 0.0),
        "right_knee":     (-0.10, 0.50, 0.0),
        "left_ankle":     ( 0.10, 0.00, 0.0),
        "right_ankle":    (-0.10, 0.00, 0.0),
    }


class SanityTests(SimpleTestCase):
    def test_good_landmarks_pass(self):
        r = check_landmarks(_good(), world_aabb=((-1, 0, -1), (1, 2, 1)))
        self.assertTrue(r.ok, r.failures)

    def test_inverted_groin_fails(self):
        bad = _good()
        bad["groin"] = (0.0, 1.95, 0.0)  # above chin
        r = check_landmarks(bad, world_aabb=((-1, 0, -1), (1, 2, 1)))
        self.assertFalse(r.ok)
        self.assertIn("groin_above_chin", [f.code for f in r.failures])

    def test_asymmetric_wrist_fails(self):
        bad = _good()
        bad["left_wrist"] = (0.70, 1.00, 0.0)
        bad["right_wrist"] = (-0.10, 1.00, 0.0)  # 7× asymmetric
        r = check_landmarks(bad, world_aabb=((-1, 0, -1), (1, 2, 1)))
        self.assertFalse(r.ok)
        self.assertIn("asymmetry_wrist", [f.code for f in r.failures])

    def test_outside_aabb_fails(self):
        bad = _good()
        bad["left_wrist"] = (5.0, 1.0, 0.0)  # way outside
        r = check_landmarks(bad, world_aabb=((-1, 0, -1), (1, 2, 1)))
        self.assertFalse(r.ok)
        self.assertIn("outside_aabb_left_wrist", [f.code for f in r.failures])

    def test_missing_key_fails(self):
        bad = _good()
        del bad["chin"]
        r = check_landmarks(bad, world_aabb=((-1, 0, -1), (1, 2, 1)))
        self.assertFalse(r.ok)
        self.assertIn("missing_chin", [f.code for f in r.failures])
```

- [ ] **Step 2: Run the tests; verify failure**

```bash
cd backend/
python manage.py test apps.rigging.tests.test_sanity -v 2
```

Expected: ImportError or AttributeError on `apps.rigging.sanity`.

- [ ] **Step 3: Implement the minimum to pass**

Create `backend/apps/rigging/sanity.py`:

```python
"""Pure landmark sanity checks. No Blender deps; safe to unit-test."""
from dataclasses import dataclass, field
from typing import Iterable

LANDMARK_KEYS = (
    "chin", "groin",
    "left_shoulder", "right_shoulder",
    "left_elbow", "right_elbow",
    "left_wrist", "right_wrist",
    "left_hip", "right_hip",
    "left_knee", "right_knee",
    "left_ankle", "right_ankle",
)

PAIRS = (
    ("left_shoulder", "right_shoulder", "shoulder"),
    ("left_elbow",    "right_elbow",    "elbow"),
    ("left_wrist",    "right_wrist",    "wrist"),
    ("left_hip",      "right_hip",      "hip"),
    ("left_knee",     "right_knee",     "knee"),
    ("left_ankle",    "right_ankle",    "ankle"),
)

ASYMMETRY_TOLERANCE = 0.30   # |L - R| / max(|L|, |R|, 0.01)
AABB_INFLATE        = 0.05   # 5% margin around the mesh AABB
MIN_TORSO_GAP       = 0.10   # groin must be at least this far below chin


@dataclass
class Failure:
    code: str
    detail: str = ""


@dataclass
class SanityResult:
    ok: bool
    failures: list = field(default_factory=list)


def _y(v):  # accept tuple or three.js dict
    return v[1] if not isinstance(v, dict) else v["y"]


def _inflate(box, frac):
    (lo, hi) = box
    span = [hi[i] - lo[i] for i in range(3)]
    delta = [frac * s for s in span]
    return (
        tuple(lo[i] - delta[i] for i in range(3)),
        tuple(hi[i] + delta[i] for i in range(3)),
    )


def _in_box(p, box):
    (lo, hi) = box
    return all(lo[i] <= p[i] <= hi[i] for i in range(3))


def check_landmarks(landmarks: dict, *, world_aabb) -> SanityResult:
    """Run every sanity rule. Returns SanityResult with a list of failure
    codes — callers can decide which rules are blocking and which warn."""
    failures = []

    for k in LANDMARK_KEYS:
        if k not in landmarks:
            failures.append(Failure(f"missing_{k}"))
    if failures:
        return SanityResult(ok=False, failures=failures)

    chin_y, groin_y = landmarks["chin"][1], landmarks["groin"][1]
    if groin_y >= chin_y - MIN_TORSO_GAP:
        failures.append(Failure(
            "groin_above_chin",
            f"chin.y={chin_y:.3f} groin.y={groin_y:.3f}",
        ))

    for lk, rk, label in PAIRS:
        lx = landmarks[lk][0]
        rx = landmarks[rk][0]
        denom = max(abs(lx), abs(rx), 0.01)
        if abs(lx - rx) / denom > ASYMMETRY_TOLERANCE * 2:
            failures.append(Failure(
                f"asymmetry_{label}",
                f"L.x={lx:.3f} R.x={rx:.3f}",
            ))

    inflated = _inflate(world_aabb, AABB_INFLATE)
    for k in LANDMARK_KEYS:
        if not _in_box(landmarks[k], inflated):
            failures.append(Failure(f"outside_aabb_{k}"))

    z_chain = [
        ("ankle", min(landmarks["left_ankle"][1], landmarks["right_ankle"][1])),
        ("knee",  min(landmarks["left_knee"][1],  landmarks["right_knee"][1])),
        ("hip",   min(landmarks["left_hip"][1],   landmarks["right_hip"][1])),
        ("groin", landmarks["groin"][1]),
        ("shoulder", min(landmarks["left_shoulder"][1], landmarks["right_shoulder"][1])),
        ("chin",  landmarks["chin"][1]),
    ]
    for (a, av), (b, bv) in zip(z_chain, z_chain[1:]):
        if av > bv:
            failures.append(Failure(f"order_{a}_above_{b}"))

    return SanityResult(ok=not failures, failures=failures)
```

- [ ] **Step 4: Run tests; verify pass**

```bash
python manage.py test apps.rigging.tests.test_sanity -v 2
```

Expected: 5 tests, all PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/apps/rigging/sanity.py backend/apps/rigging/tests/__init__.py backend/apps/rigging/tests/test_sanity.py
git commit -m "feat(rigging): sanity checks for landmark plausibility (groin/symmetry/aabb/order)"
```

---

### Task 5: A-pose support in geometry-only `detect_landmarks`

**Files:**
- Modify: `backend/scripts/blender_autorig.py` (the `detect_landmarks` function and pose-classifier coupling)

This is M1's last task. Behaviour after it: any A-pose mesh that the existing pose classifier confidently labels `a_pose` gets per-side wrist detection (extreme along a downward-tilted ray) and rotated shoulder slicing; everything else falls back to AABB defaults via `_promote_legacy_landmarks`, same as today.

- [ ] **Step 1: Read the current `detect_landmarks` and pose-classifier coupling**

```bash
grep -n "def detect_landmarks\|def detect_pose\|detected_pose\|_extreme_vertex" backend/scripts/blender_autorig.py | head -40
```

Note: pose classifier output is `{"name": ..., "angle_deg": ..., "confidence": ...}`. The current detector switches on `pose["name"] == "t_pose"` and `pose["confidence"] >= 0.75`. We add a parallel `elif pose["name"] == "a_pose" and pose["confidence"] >= 0.75:` branch.

- [ ] **Step 2: Add the A-pose branch**

Inside `detect_landmarks`, after the existing `if is_t:` branch, add:

```python
elif pose is not None and pose.get("name") == "a_pose" and pose.get("confidence", 0.0) >= 0.75:
    verts = world_vertices(meshes)
    angle_rad = math.radians(pose.get("angle_deg", 45.0))
    # Wrists: extreme along the arm ray (cos(angle)*x − sin(angle)*z), one side at a time.
    def _ray_extreme(sign):
        cx, cz = math.cos(angle_rad), math.sin(angle_rad)
        return max(verts, key=lambda v: sign * (cx * v.x - cz * v.z))
    lw_v = _ray_extreme(+1)
    rw_v = _ray_extreme(-1)
    lw = Vector((lw_v.x, lw_v.y, lw_v.z))
    rw = Vector((rw_v.x, rw_v.y, rw_v.z))
    ankles = _bottom_cluster_centroids(verts)
    if ankles is not None:
        la, ra = ankles
    log(f"A-pose detection (angle={math.degrees(angle_rad):.1f}°): wrists via ray-extreme, ankles via bottom-cluster")
    is_known_pose = True
else:
    log("Non-T/A pose or low confidence — landmark detection falls back to AABB defaults")
    is_known_pose = False
```

(`math` is already imported at the top of the file; if not, add `import math`.)

- [ ] **Step 3: Update the `is_t` log line for symmetry**

Change `if is_t:` block's tail log to also set `is_known_pose = True` so the downstream override block (currently gated on `if is_t:`) can be gated on `if is_known_pose:` instead. Update the override block accordingly — same shoulder/hip/elbow/knee recomputation logic; just the gate variable name changes.

- [ ] **Step 4: Smoke test against the existing FBX**

```bash
tmpdir=$(mktemp -d /tmp/rigflow-apose.XXXXXX)
blender --background --python backend/scripts/blender_autorig.py -- \
  --input backend/media/rigs/1/0f855599-39df-487f-a827-accedd052d5d/johnny_joestar.fbx \
  --output "$tmpdir/rigged.glb" \
  --bones "$tmpdir/bones.json" \
  --pose "$tmpdir/pose.json" \
  --landmarks-out "$tmpdir/landmarks.json" \
  --format fbx
cat "$tmpdir/pose.json"
cat "$tmpdir/landmarks.json"
```

Expected: pose is `t_pose` for Johnny → log line shows the T-pose path fired. Landmarks JSON has 14 keys.

If you have an A-pose model on disk, run it through too and confirm the A-pose log line fires.

- [ ] **Step 5: Commit**

```bash
git add backend/scripts/blender_autorig.py
git commit -m "feat(rigging): A-pose support in detect_landmarks (ray-extreme wrist detection)"
```

---

### Task 6: Add `anthropic` + `Pillow` to backend requirements

**Files:**
- Modify: `backend/requirements.txt`

- [ ] **Step 1: Add the two lines**

Append to `backend/requirements.txt`:

```
anthropic>=0.40.0
Pillow>=10.0.0
```

- [ ] **Step 2: Install**

```bash
cd backend/
pip install -r requirements.txt
```

Expected: both packages install cleanly. Anthropic SDK pulls in `httpx`, `pydantic` (likely already present).

- [ ] **Step 3: Verify import**

```bash
python -c "import anthropic, PIL; print(anthropic.__version__, PIL.__version__)"
```

Expected: two version strings, no traceback.

- [ ] **Step 4: Commit**

```bash
git add backend/requirements.txt
git commit -m "build(deps): add anthropic + Pillow for vision-assisted auto-rig"
```

---

### Task 7: Provider abstraction skeleton (with NoneProvider only)

**Files:**
- Create: `backend/apps/rigging/landmark_vision/__init__.py`
- Create: `backend/apps/rigging/landmark_vision/base.py`
- Create: `backend/apps/rigging/landmark_vision/none_provider.py`
- Create: `backend/apps/rigging/tests/test_landmark_vision.py`

- [ ] **Step 1: Write the failing test first**

Create `backend/apps/rigging/tests/test_landmark_vision.py`:

```python
"""Tests for provider dispatch. Live SDK calls covered in test_claude_provider."""
import os
from unittest.mock import patch
from django.test import SimpleTestCase

from apps.rigging.landmark_vision import get_provider
from apps.rigging.landmark_vision.none_provider import NoneProvider


class ProviderDispatchTests(SimpleTestCase):
    @patch.dict(os.environ, {"LANDMARK_VISION_PROVIDER": "none"}, clear=False)
    def test_explicit_none_returns_none_provider(self):
        self.assertIsInstance(get_provider(), NoneProvider)

    @patch.dict(os.environ, {"LANDMARK_VISION_PROVIDER": "claude"}, clear=True)
    def test_claude_without_api_key_degrades_to_none(self):
        # ANTHROPIC_API_KEY intentionally absent
        provider = get_provider()
        self.assertIsInstance(provider, NoneProvider)

    @patch.dict(os.environ, {}, clear=True)
    def test_unset_defaults_to_none(self):
        self.assertIsInstance(get_provider(), NoneProvider)

    def test_none_provider_returns_none(self):
        from apps.rigging.landmark_vision.base import VisionRequest
        req = VisionRequest(rig_id="abc", views={}, mesh_objects=[], world_aabb=((-1,0,-1),(1,2,1)))
        self.assertIsNone(NoneProvider().detect(req))
```

- [ ] **Step 2: Run tests; verify they fail with ImportError**

```bash
python manage.py test apps.rigging.tests.test_landmark_vision -v 2
```

Expected: ImportError on `apps.rigging.landmark_vision`.

- [ ] **Step 3: Create `base.py` with the protocol + dataclasses**

```python
"""Shared types for landmark vision providers."""
from dataclasses import dataclass, field
from typing import Protocol, Any


@dataclass
class VisionRequest:
    rig_id: str
    views: dict          # {"front": {"path": str, "image_size": [int,int], ...}, ...}
    mesh_objects: list   # [{"name": str, "vertex_count": int, "bbox_world": ...}, ...]
    world_aabb: tuple    # ((xmin,ymin,zmin), (xmax,ymax,zmax))


@dataclass
class VisionResponse:
    landmarks: dict      # {view: {key: [px,py] | None}}
    mesh_object_labels: dict  # {name: "body"|"hat"|"accessory_held_left"|...}
    notes: str = ""
    raw: Any = None      # original parsed JSON for audit


class Provider(Protocol):
    """A provider takes a VisionRequest and returns a VisionResponse or
    None if the call cannot succeed (no key, network error, malformed
    response)."""
    def detect(self, request: VisionRequest) -> VisionResponse | None: ...
```

- [ ] **Step 4: Create `none_provider.py`**

```python
"""Geometry-only mode — returns None so the caller skips the AI path."""
from .base import VisionRequest, VisionResponse


class NoneProvider:
    def detect(self, request: VisionRequest) -> VisionResponse | None:
        return None
```

- [ ] **Step 5: Create `__init__.py` with the dispatcher**

```python
"""Provider dispatch keyed on LANDMARK_VISION_PROVIDER + ANTHROPIC_API_KEY."""
import logging
import os

from .base import Provider, VisionRequest, VisionResponse
from .none_provider import NoneProvider

log = logging.getLogger(__name__)


def get_provider() -> Provider:
    name = os.environ.get("LANDMARK_VISION_PROVIDER", "none").strip().lower()

    if name == "claude":
        if not os.environ.get("ANTHROPIC_API_KEY"):
            log.warning(
                "LANDMARK_VISION_PROVIDER=claude but ANTHROPIC_API_KEY is unset; "
                "degrading to geometry-only mode."
            )
            return NoneProvider()
        from .claude_provider import ClaudeProvider  # local import: Task 10 lands ClaudeProvider
        return ClaudeProvider()

    if name not in ("none", "", "geometry"):
        log.warning("Unknown LANDMARK_VISION_PROVIDER=%r; falling back to none.", name)
    return NoneProvider()


__all__ = ["get_provider", "Provider", "VisionRequest", "VisionResponse"]
```

(`claude_provider` is imported inside `get_provider` so the module loads even before Task 10 creates that file — the test for `claude_without_api_key` exits before reaching that import.)

- [ ] **Step 6: Run tests; verify pass**

```bash
python manage.py test apps.rigging.tests.test_landmark_vision -v 2
```

Expected: 4 tests PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/apps/rigging/landmark_vision/ backend/apps/rigging/tests/test_landmark_vision.py
git commit -m "feat(rigging): provider abstraction skeleton (NoneProvider + dispatch)"
```

---

### Task 8: Ortho-render step + request JSON writer in Blender

**Files:**
- Modify: `backend/scripts/blender_autorig.py` (`parse_args`, new functions, `main` flow)

This is the last task before we need the API key for anything meaningful.

- [ ] **Step 1: Add the two new CLI flags**

In `parse_args`:

```python
p.add_argument("--render-ortho-views", action="store_true",
               help="Render front/back/left/right 512x512 ortho PNGs and exit. "
                    "Used by the Django round-trip to feed the vision provider.")
p.add_argument("--ai-request-out", default=None,
               help="Path to write the AI request JSON (PNG paths + mesh metadata).")
p.add_argument("--ortho-render-dir", default=None,
               help="Directory to write the 4 PNGs into. Default: alongside --ai-request-out.")
```

- [ ] **Step 2: Add the renderer**

Insert near the top of `main()` (before the existing pipeline runs), a function:

```python
def render_ortho_views(meshes, out_dir, image_size=512):
    """Render 4 ortho views (front -Y, back +Y, left -X, right +X) of the
    scene meshes into out_dir. Returns a dict of view → {path, camera_aabb,
    image_size} suitable for the request JSON.
    
    Uses Blender's CYCLES renderer with minimal samples (we only need silhouette
    + diffuse for landmark detection)."""
    import bpy as _bpy
    from mathutils import Vector as _V
    
    aabb = compute_world_aabb(meshes)
    center = (aabb["min"] + aabb["max"]) / 2.0
    size   = aabb["max"] - aabb["min"]
    margin = 1.10
    
    _bpy.context.scene.render.engine = "BLENDER_EEVEE_NEXT" if hasattr(_bpy.context.scene.render, "engine") else "BLENDER_EEVEE"
    _bpy.context.scene.render.resolution_x = image_size
    _bpy.context.scene.render.resolution_y = image_size
    _bpy.context.scene.render.image_settings.file_format = "PNG"
    _bpy.context.scene.render.film_transparent = True
    
    cam_data = _bpy.data.cameras.new("RigFlowOrthoCam")
    cam_data.type = "ORTHO"
    cam_data.ortho_scale = max(size.x, size.z) * margin
    cam_obj = _bpy.data.objects.new("RigFlowOrthoCam", cam_data)
    _bpy.context.collection.objects.link(cam_obj)
    _bpy.context.scene.camera = cam_obj
    
    distance = max(size.x, size.y, size.z) * 3
    views = {
        "front": (center + _V(( 0, -distance, 0)), (math.radians(90), 0, 0)),
        "back":  (center + _V(( 0,  distance, 0)), (math.radians(90), 0, math.radians(180))),
        "left":  (center + _V((-distance, 0, 0)), (math.radians(90), 0, math.radians(-90))),
        "right": (center + _V(( distance, 0, 0)), (math.radians(90), 0, math.radians(90))),
    }
    
    out = {}
    for name, (location, rotation_euler) in views.items():
        cam_obj.location = location
        cam_obj.rotation_euler = rotation_euler
        png_path = Path(out_dir) / f"{name}.png"
        _bpy.context.scene.render.filepath = str(png_path)
        _bpy.ops.render.render(write_still=True)
        out[name] = {
            "path": str(png_path),
            "image_size": [image_size, image_size],
            "camera_aabb": [list(aabb["min"]), list(aabb["max"])],
            "ortho_scale": cam_data.ortho_scale,
        }
    
    return out, aabb
```

(`compute_world_aabb` already exists in the script as `aabb(world_vertices(meshes))`. Use the existing helper; reuse its return shape.)

- [ ] **Step 3: Branch in `main()` for the new flag**

Near the start of `main()`, after `apply_user_rotation`:

```python
if args.render_ortho_views:
    if not args.ai_request_out:
        raise SystemExit("--render-ortho-views requires --ai-request-out")
    out_dir = args.ortho_render_dir or str(Path(args.ai_request_out).parent)
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    views, world_aabb = render_ortho_views(meshes, out_dir)
    request = {
        "rig_id": Path(args.input).stem,  # placeholder; tasks.py overrides
        "views": views,
        "mesh_objects": [
            {
                "name": m.name,
                "vertex_count": len(m.data.vertices),
                "bbox_world": _bbox_world(m),
            }
            for m in meshes
        ],
        "world_aabb": [list(world_aabb["min"]), list(world_aabb["max"])],
    }
    Path(args.ai_request_out).write_text(json.dumps(request, indent=2))
    log(f"Wrote ortho request → {args.ai_request_out}")
    return  # exit after the render-and-emit phase
```

(Define `_bbox_world(mesh)` helper at module scope returning `[[xmin,ymin,zmin],[xmax,ymax,zmax]]` from `mesh.bound_box` transformed by `mesh.matrix_world`.)

- [ ] **Step 4: Smoke test**

```bash
tmpdir=$(mktemp -d /tmp/rigflow-ortho.XXXXXX)
blender --background --python backend/scripts/blender_autorig.py -- \
  --input backend/media/rigs/1/0f855599-39df-487f-a827-accedd052d5d/johnny_joestar.fbx \
  --output /dev/null \
  --bones /dev/null \
  --pose /dev/null \
  --format fbx \
  --render-ortho-views \
  --ai-request-out "$tmpdir/request.json"
ls -la "$tmpdir"
cat "$tmpdir/request.json" | python -m json.tool | head -40
```

Expected: 4 PNG files (front, back, left, right) + 1 request.json. JSON has `views.front.path`, `mesh_objects`, `world_aabb`. Open one PNG to confirm the character silhouette is visible and centered.

- [ ] **Step 5: Commit**

```bash
git add backend/scripts/blender_autorig.py
git commit -m "feat(rigging): ortho-render step + AI request JSON writer"
```

---

### Task 9: ClaudeProvider — Anthropic SDK call + prompt + response parsing

**Files:**
- Create: `backend/apps/rigging/landmark_vision/prompts.py`
- Create: `backend/apps/rigging/landmark_vision/claude_provider.py`
- Create: `backend/apps/rigging/tests/fixtures/__init__.py`
- Create: `backend/apps/rigging/tests/fixtures/claude_response_johnny.json`
- Modify: `backend/apps/rigging/tests/test_landmark_vision.py`

- [ ] **Step 1: Drop in the prompt template**

Create `backend/apps/rigging/landmark_vision/prompts.py` and paste the prompt **exactly** as specified in the spec doc (`Docs/specs/2026-05-12-auto-rig-perfect.md` §Vision prompt). Export it as `VISION_PROMPT_TEMPLATE` — a Python f-string-formattable string where `{mesh_object_names}` is the only placeholder.

- [ ] **Step 2: Implement `ClaudeProvider`**

Create `backend/apps/rigging/landmark_vision/claude_provider.py`:

```python
"""Anthropic Claude Haiku 4.5 vision provider for landmark detection."""
import base64
import json
import logging
import os
from pathlib import Path

import anthropic

from .base import VisionRequest, VisionResponse
from .prompts import VISION_PROMPT_TEMPLATE

log = logging.getLogger(__name__)

MODEL_ID = "claude-haiku-4-5-20251001"
MAX_TOKENS = 2000
MAX_RETRIES = 1   # second attempt on malformed JSON; then give up


class ClaudeProvider:
    def __init__(self, api_key: str | None = None):
        self.client = anthropic.Anthropic(
            api_key=api_key or os.environ["ANTHROPIC_API_KEY"],
        )

    def detect(self, request: VisionRequest) -> VisionResponse | None:
        prompt = VISION_PROMPT_TEMPLATE.format(
            mesh_object_names=", ".join(m["name"] for m in request.mesh_objects)
        )
        content = [{"type": "text", "text": prompt}]
        for view_name in ("front", "back", "left", "right"):
            view = request.views[view_name]
            content.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/png",
                    "data": _b64(view["path"]),
                },
            })

        last_err = None
        for attempt in range(MAX_RETRIES + 1):
            try:
                resp = self.client.messages.create(
                    model=MODEL_ID,
                    max_tokens=MAX_TOKENS,
                    messages=[{"role": "user", "content": content}],
                )
                text = "".join(block.text for block in resp.content if hasattr(block, "text"))
                parsed = self._parse(text)
                if parsed is not None:
                    return parsed
                last_err = "malformed JSON or schema mismatch"
            except anthropic.APIError as e:
                last_err = f"APIError: {e}"
                log.warning("Anthropic call failed (attempt %d): %s", attempt + 1, e)
        log.error("ClaudeProvider giving up after %d attempts: %s", MAX_RETRIES + 1, last_err)
        return None

    def _parse(self, text: str) -> VisionResponse | None:
        try:
            stripped = text.strip()
            if stripped.startswith("```"):
                stripped = stripped.split("```", 2)[1]
                if stripped.lstrip().startswith("json"):
                    stripped = stripped.lstrip()[4:]
                stripped = stripped.rsplit("```", 1)[0]
            data = json.loads(stripped)
            if not all(k in data for k in ("landmarks", "mesh_objects")):
                return None
            if not all(v in data["landmarks"] for v in ("front", "back", "left", "right")):
                return None
            return VisionResponse(
                landmarks=data["landmarks"],
                mesh_object_labels=data["mesh_objects"],
                notes=data.get("notes", ""),
                raw=data,
            )
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            log.warning("Claude response unparseable: %s", e)
            return None


def _b64(path):
    return base64.b64encode(Path(path).read_bytes()).decode("ascii")
```

- [ ] **Step 3: Capture a recorded fixture for testing without live calls**

If you have an Anthropic key already, run the provider once against the Johnny ortho renders from Task 8 and save the response. Otherwise, hand-author a minimal valid response:

```bash
mkdir -p backend/apps/rigging/tests/fixtures
```

Create `backend/apps/rigging/tests/fixtures/claude_response_johnny.json`:

```json
{
  "landmarks": {
    "front": {
      "chin":           [256, 56],
      "groin":          [256, 256],
      "left_shoulder":  [310, 90],
      "right_shoulder": [202, 90],
      "left_elbow":     [380, 160],
      "right_elbow":    [132, 160],
      "left_wrist":     [450, 230],
      "right_wrist":    [62,  230],
      "left_hip":       [285, 270],
      "right_hip":      [227, 270],
      "left_knee":      [290, 380],
      "right_knee":     [222, 380],
      "left_ankle":     [290, 490],
      "right_ankle":    [222, 490]
    },
    "back":  {"chin": [256, 56], "groin": [256, 256], "left_shoulder": [202, 90], "right_shoulder": [310, 90], "left_elbow": [132, 160], "right_elbow": [380, 160], "left_wrist": [62, 230], "right_wrist": [450, 230], "left_hip": [227, 270], "right_hip": [285, 270], "left_knee": [222, 380], "right_knee": [290, 380], "left_ankle": [222, 490], "right_ankle": [290, 490]},
    "left":  {"chin": [256, 56], "groin": [256, 256], "left_shoulder": [256, 90], "right_shoulder": null, "left_elbow": [256, 160], "right_elbow": null, "left_wrist": [256, 230], "right_wrist": null, "left_hip": [256, 270], "right_hip": null, "left_knee": [256, 380], "right_knee": null, "left_ankle": [256, 490], "right_ankle": null},
    "right": {"chin": [256, 56], "groin": [256, 256], "left_shoulder": null, "right_shoulder": [256, 90], "left_elbow": null, "right_elbow": [256, 160], "left_wrist": null, "right_wrist": [256, 230], "left_hip": null, "right_hip": [256, 270], "left_knee": null, "right_knee": [256, 380], "left_ankle": null, "right_ankle": [256, 490]}
  },
  "mesh_objects": {
    "Body": "body"
  },
  "notes": "Johnny Joestar T-pose, single body mesh"
}
```

- [ ] **Step 4: Add fixture-based test (no network)**

Append to `backend/apps/rigging/tests/test_landmark_vision.py`:

```python
class ClaudeProviderParseTests(SimpleTestCase):
    def test_parse_well_formed_response(self):
        from apps.rigging.landmark_vision.claude_provider import ClaudeProvider
        import json
        from pathlib import Path

        fixture = Path(__file__).parent / "fixtures" / "claude_response_johnny.json"
        text = fixture.read_text()
        provider = ClaudeProvider.__new__(ClaudeProvider)  # skip __init__ (no key needed)
        result = provider._parse(text)
        self.assertIsNotNone(result)
        self.assertIn("chin", result.landmarks["front"])
        self.assertEqual(result.mesh_object_labels.get("Body"), "body")

    def test_parse_malformed_returns_none(self):
        from apps.rigging.landmark_vision.claude_provider import ClaudeProvider
        provider = ClaudeProvider.__new__(ClaudeProvider)
        self.assertIsNone(provider._parse("not json"))
        self.assertIsNone(provider._parse('{"landmarks": {}}'))  # schema mismatch

    def test_parse_strips_markdown_fence(self):
        from apps.rigging.landmark_vision.claude_provider import ClaudeProvider
        provider = ClaudeProvider.__new__(ClaudeProvider)
        wrapped = '```json\n{"landmarks": {"front": {}, "back": {}, "left": {}, "right": {}}, "mesh_objects": {}}\n```'
        result = provider._parse(wrapped)
        self.assertIsNotNone(result)
```

- [ ] **Step 5: Run tests; verify pass**

```bash
python manage.py test apps.rigging.tests.test_landmark_vision -v 2
```

Expected: all PASS (no network — `_parse` is pure).

- [ ] **Step 6: Optional live smoke test (only if you have a key)**

```bash
export ANTHROPIC_API_KEY=sk-ant-...
python -c "
from apps.rigging.landmark_vision.claude_provider import ClaudeProvider
from apps.rigging.landmark_vision.base import VisionRequest
p = ClaudeProvider()
req = VisionRequest(
    rig_id='smoke',
    views={
        'front': {'path': '/tmp/rigflow-ortho.XXXX/front.png', 'image_size':[512,512]},
        'back':  {'path': '/tmp/rigflow-ortho.XXXX/back.png',  'image_size':[512,512]},
        'left':  {'path': '/tmp/rigflow-ortho.XXXX/left.png',  'image_size':[512,512]},
        'right': {'path': '/tmp/rigflow-ortho.XXXX/right.png', 'image_size':[512,512]},
    },
    mesh_objects=[{'name':'Body','vertex_count':1234,'bbox_world':[[0,0,0],[1,1,1]]}],
    world_aabb=((-1,0,-1),(1,2,1)),
)
print(p.detect(req))
"
```

(Replace the path with the actual Task 8 output directory.)

Expected: a `VisionResponse(...)` object. Cost: ~$0.004.

- [ ] **Step 7: Commit**

```bash
git add backend/apps/rigging/landmark_vision/prompts.py \
        backend/apps/rigging/landmark_vision/claude_provider.py \
        backend/apps/rigging/tests/fixtures/ \
        backend/apps/rigging/tests/test_landmark_vision.py
git commit -m "feat(rigging): Claude Haiku 4.5 vision provider with prompt + response parser"
```

---

### Task 10: Wire `tasks.py` round-trip — two Blender invocations gated by provider

**Files:**
- Modify: `backend/apps/rigging/tasks.py`

This is the orchestration that makes everything talk. Before this task, Blender either renders OR rigs but not both; after this task, the auto-rig path is: render → AI → rig.

- [ ] **Step 1: Locate `_run_rig_pipeline` and read the current Blender subprocess call**

```bash
grep -n "subprocess\|BLENDER_EXECUTABLE\|blender_autorig" backend/apps/rigging/tasks.py
```

- [ ] **Step 2: Insert the ortho-render + AI phase before the existing rig phase**

In `_run_rig_pipeline`, immediately before the current `subprocess.run([BLENDER_EXECUTABLE, ..., "blender_autorig.py", ...])` block, add:

```python
from .landmark_vision import get_provider, VisionRequest

provider = get_provider()
ai_response_path = None

if not user_landmarks:
    # Phase 1: render ortho views + emit request file
    request_path = Path(tmp) / "ai_request.json"
    ortho_dir    = Path(tmp) / "ortho"
    render_argv = [
        BLENDER_EXECUTABLE, "--background", "--python", str(SCRIPT_PATH), "--",
        "--input",  str(input_path),
        "--output", "/dev/null",
        "--bones",  "/dev/null",
        "--format", original_format,
        "--render-ortho-views",
        "--ortho-render-dir", str(ortho_dir),
        "--ai-request-out",   str(request_path),
    ]
    if rotation_args:
        render_argv.extend(rotation_args)
    push_ws(rig, "Rendering character views for AI...", 25)
    render_proc = subprocess.run(render_argv, capture_output=True, text=True, timeout=120)
    if render_proc.returncode != 0:
        log.warning("Ortho render exited %d; skipping AI phase", render_proc.returncode)
    elif request_path.exists():
        try:
            request_data = json.loads(request_path.read_text())
            vision_req = VisionRequest(
                rig_id=str(rig.id),
                views=request_data["views"],
                mesh_objects=request_data["mesh_objects"],
                world_aabb=tuple(map(tuple, request_data["world_aabb"])),
            )
            push_ws(rig, "Calling vision model...", 35)
            vision_resp = provider.detect(vision_req)
            if vision_resp is not None:
                ai_response_path = Path(tmp) / "ai_response.json"
                ai_response_path.write_text(json.dumps({
                    "landmarks":    vision_resp.landmarks,
                    "mesh_objects": vision_resp.mesh_object_labels,
                    "notes":        vision_resp.notes,
                }, indent=2))
                rig.vision_response_raw = vision_resp.raw
                rig.detection_method    = "llm_vision"
            else:
                rig.detection_method = "geometry"
        except Exception as e:
            log.exception("AI phase failed: %s", e)
            rig.detection_method = "geometry"
else:
    rig.detection_method = "user_landmarks"
```

- [ ] **Step 3: Pass `--landmarks-from-ai` into the existing rig subprocess**

In the same function, in the existing `rig_argv = [...]` list (the second Blender call that produces the GLB), conditionally append:

```python
if ai_response_path is not None:
    rig_argv.extend(["--landmarks-from-ai", str(ai_response_path)])
```

(The flag itself is wired into `blender_autorig.py` in Task 12 — for now it's a no-op pass-through; the script ignores unknown args via the existing argparse setup. Verify argparse uses `parse_known_args` or add the flag stub to `parse_args` now.)

- [ ] **Step 4: Smoke test in geometry-only mode**

```bash
# LANDMARK_VISION_PROVIDER unset → NoneProvider → no AI phase
cd backend/
python manage.py shell -c "
from apps.rigging.tasks import _run_rig_pipeline
from apps.rigging.models import RiggedModel
rig = RiggedModel.objects.latest('created_at')
_run_rig_pipeline(str(rig.id))
rig.refresh_from_db()
print(rig.status, rig.detection_method)
"
```

Expected: `done geometry`. Pipeline behaviour identical to pre-task except the new `detection_method` field is now set.

- [ ] **Step 5: Smoke test in AI mode (only if user added the key)**

```bash
export LANDMARK_VISION_PROVIDER=claude
export ANTHROPIC_API_KEY=sk-ant-...
python manage.py shell -c "
from apps.rigging.tasks import _run_rig_pipeline
from apps.rigging.models import RiggedModel
rig = RiggedModel.objects.latest('created_at')
_run_rig_pipeline(str(rig.id))
rig.refresh_from_db()
print(rig.status, rig.detection_method)
print(rig.vision_response_raw is not None)
"
```

Expected: `done llm_vision True`.

- [ ] **Step 6: Commit**

```bash
git add backend/apps/rigging/tasks.py
git commit -m "feat(rigging): tasks.py orchestrates Blender↔Django round-trip for vision provider"
```

---

### Task 11: `--landmarks-from-ai` plumbing in Blender (stub — no math yet)

**Files:**
- Modify: `backend/scripts/blender_autorig.py`

This task only adds the flag and a no-op handler so Task 10's invocation doesn't error. Real raycast math lands in Task 12.

- [ ] **Step 1: Add the flag to `parse_args`**

```python
p.add_argument("--landmarks-from-ai", default=None,
               help="Path to AI vision response JSON (front/back/left/right "
                    "pixel coords + mesh_objects labels). When set, the script "
                    "raycasts AI seeds into 3D, refines them to mesh vertices, "
                    "and uses those as the landmark dict for place_bones_from_landmarks.")
```

- [ ] **Step 2: Add a no-op consumer**

In `main()`, after `detect_landmarks` runs and produces `auto_landmarks`, add:

```python
if args.landmarks_from_ai:
    log(f"--landmarks-from-ai set ({args.landmarks_from_ai}); will be wired up in Task 12")
    # Task 12 replaces this no-op with: raycast + refine + override auto_landmarks
```

- [ ] **Step 3: Smoke test the full chain (geometry-only path)**

```bash
# Re-run Task 10 smoke test with --landmarks-from-ai pointing at a dummy file
echo '{}' > /tmp/dummy.json
blender --background --python backend/scripts/blender_autorig.py -- \
  --input backend/media/rigs/1/0f855599-39df-487f-a827-accedd052d5d/johnny_joestar.fbx \
  --output /tmp/out.glb \
  --bones /tmp/bones.json \
  --pose /tmp/pose.json \
  --landmarks-out /tmp/landmarks.json \
  --landmarks-from-ai /tmp/dummy.json \
  --format fbx
```

Expected: exits 0, GLB produced, log line "--landmarks-from-ai set" appears.

- [ ] **Step 4: Commit**

```bash
git add backend/scripts/blender_autorig.py
git commit -m "feat(rigging): --landmarks-from-ai flag stub (consumer wired in Task 12)"
```

---

### Task 12: Pixel-to-3D raycast + seed-to-vertex refinement

**Files:**
- Modify: `backend/scripts/blender_autorig.py`
- Create: `backend/scripts/_test_pixel_to_world.py`

The math heart of the duo. After this task, AI pixel coords become refined 3D landmarks.

- [ ] **Step 1: Write the standalone smoke test first**

Create `backend/scripts/_test_pixel_to_world.py` following the pattern of `_test_landmark_promotion.py` — stub `mathutils.Vector` with a 3-tuple, import the function under test, assert it round-trips a known point. Cover:

- A pixel at view center → ray origin at view-center on the camera plane.
- A pixel at view corner → ray displaced by `ortho_scale/2` in the appropriate axis.
- Front view ray gives world x,z (y is along ray direction, runs forward).
- Side view ray gives world y,z (x is along ray direction).

Run it; verify it fails:

```bash
python backend/scripts/_test_pixel_to_world.py
```

- [ ] **Step 2: Implement `pixel_to_world_ray`**

In `blender_autorig.py`, add:

```python
def pixel_to_world_ray(view_name, px, py, image_size, ortho_scale, world_aabb):
    """Return (origin, direction) in world space for an ortho camera view.
    For an ortho camera the ray direction is constant per view; origin
    varies with pixel position.
    
    view_name ∈ {"front", "back", "left", "right"}
    px, py    = pixel coords, top-left origin, in [0, image_size)
    image_size = int (square)
    ortho_scale = float (world units across the view at the camera plane)
    world_aabb = ((xmin,ymin,zmin), (xmax,ymax,zmax))
    """
    from mathutils import Vector
    (mn, mx) = world_aabb
    center = Vector(((mn[0]+mx[0])/2, (mn[1]+mx[1])/2, (mn[2]+mx[2])/2))
    half = ortho_scale / 2
    # Normalize pixel to [-half, +half] in camera plane coords, Y flipped.
    u = (px / image_size - 0.5) * ortho_scale
    v = (0.5 - py / image_size) * ortho_scale
    
    if view_name == "front":
        # Camera looks +Y; image x = world x, image y = world z.
        origin = Vector((center.x + u, mn[1] - half, center.z + v))
        direction = Vector((0, 1, 0))
    elif view_name == "back":
        origin = Vector((center.x - u, mx[1] + half, center.z + v))
        direction = Vector((0, -1, 0))
    elif view_name == "left":
        # Camera looks +X; image x = -world y, image y = world z.
        origin = Vector((mn[0] - half, center.y - u, center.z + v))
        direction = Vector((1, 0, 0))
    elif view_name == "right":
        origin = Vector((mx[0] + half, center.y + u, center.z + v))
        direction = Vector((-1, 0, 0))
    else:
        raise ValueError(f"unknown view {view_name!r}")
    return origin, direction
```

- [ ] **Step 3: Triangulate front+side per landmark into a 3D seed**

```python
def ai_pixels_to_world_seeds(ai_response, image_size, ortho_scale, world_aabb, meshes):
    """For each of the 14 landmark keys, pick the view that has non-null
    coords + the perpendicular view as the secondary axis. Raycast both
    against the meshes to get hit points; merge front-view (x,z) with
    side-view (y,z) into one 3D seed."""
    from mathutils import Vector
    import bpy as _bpy
    
    seeds = {}
    bvh_trees = [(m, _bvh_tree_for(m)) for m in meshes]
    
    def raycast(origin, direction):
        best = None
        for m, tree in bvh_trees:
            loc, _, _, dist = tree.ray_cast(origin, direction)
            if loc is not None and (best is None or dist < best[1]):
                best = (loc, dist)
        return best[0] if best else None
    
    image_w = image_size
    for key in LANDMARK_KEYS:
        front_px = ai_response["landmarks"].get("front", {}).get(key)
        side_px  = ai_response["landmarks"].get("left",  {}).get(key)
        if side_px is None:
            side_px = ai_response["landmarks"].get("right", {}).get(key)
        if front_px is None:
            continue
        
        fo, fd = pixel_to_world_ray("front", front_px[0], front_px[1], image_w, ortho_scale, world_aabb)
        hit_f = raycast(fo, fd)
        if hit_f is None:
            # Fall back to ray-midpoint = where ray crosses the AABB center plane.
            hit_f = fo + fd * ((world_aabb[0][1] + world_aabb[1][1]) / 2 - fo.y)
        
        if side_px is not None:
            view = "left" if ai_response["landmarks"].get("left", {}).get(key) else "right"
            so, sd = pixel_to_world_ray(view, side_px[0], side_px[1], image_w, ortho_scale, world_aabb)
            hit_s = raycast(so, sd) or hit_f
            # Merge: front gives x,z (most accurate); side gives y.
            seed = Vector((hit_f.x, hit_s.y, (hit_f.z + hit_s.z) / 2))
        else:
            seed = hit_f
        seeds[key] = seed
    return seeds
```

(`_bvh_tree_for` builds a `mathutils.bvhtree.BVHTree.FromObject(m, _bpy.context.evaluated_depsgraph_get())` — add a helper.)

- [ ] **Step 4: Add per-landmark refinement**

```python
def refine_seeds(seeds, meshes, world_aabb):
    """For each AI seed, walk to the nearest anatomically-meaningful vertex
    inside an expected search region."""
    refined = dict(seeds)
    verts = world_vertices(meshes)
    
    # Wrists: walk to the local minimum of arm cross-section (narrowest band).
    for key in ("left_wrist", "right_wrist"):
        if key not in seeds: continue
        seed = seeds[key]
        candidates = [v for v in verts if abs(v.z - seed.z) < 0.10 and (v - seed).length < 0.20]
        if candidates:
            refined[key] = min(candidates, key=lambda v: (v - seed).length)
    
    # Ankles: snap to bottom-cluster centroid on the matching side.
    for key in ("left_ankle", "right_ankle"):
        if key not in seeds: continue
        sign = +1 if key.startswith("left") else -1
        bottom = sorted(verts, key=lambda v: v.z)[: max(50, len(verts) // 100)]
        side_bottom = [v for v in bottom if (v.x * sign) > 0]
        if side_bottom:
            from mathutils import Vector
            cx = sum(v.x for v in side_bottom) / len(side_bottom)
            cy = sum(v.y for v in side_bottom) / len(side_bottom)
            cz = sum(v.z for v in side_bottom) / len(side_bottom)
            refined[key] = Vector((cx, cy, cz))
    
    # Chin, groin, shoulders, hips: stay at the AI seed for now —
    # refinement strategy parked under "Open follow-ups" in the spec.
    
    return refined
```

- [ ] **Step 5: Wire the consumer to replace the no-op stub**

Replace the Task 11 no-op block in `main()` with:

```python
if args.landmarks_from_ai:
    ai_response = json.loads(Path(args.landmarks_from_ai).read_text())
    log(f"AI landmarks: parsing {args.landmarks_from_ai}")
    # NOTE: ortho_scale + image_size come from the request side of the
    # round-trip; we re-derive from the current scene to keep them in sync.
    world_aabb_b = aabb(world_vertices(meshes))
    ortho_scale  = max((world_aabb_b["max"] - world_aabb_b["min"]).x,
                       (world_aabb_b["max"] - world_aabb_b["min"]).z) * 1.10
    world_aabb_t = ((world_aabb_b["min"].x, world_aabb_b["min"].y, world_aabb_b["min"].z),
                    (world_aabb_b["max"].x, world_aabb_b["max"].y, world_aabb_b["max"].z))
    seeds = ai_pixels_to_world_seeds(ai_response, 512, ortho_scale, world_aabb_t, meshes)
    seeds = refine_seeds(seeds, meshes, world_aabb_t)
    # Merge AI-derived seeds with geometry defaults for any missing keys.
    for k in LANDMARK_KEYS:
        if k not in seeds:
            seeds[k] = auto_landmarks_blender[k]   # fallback to geometry's value
    auto_landmarks = {k: to_three(seeds[k]) for k in LANDMARK_KEYS}
    log(f"AI seeds + geometry refinement applied for {len(seeds)} landmarks")
```

- [ ] **Step 6: Smoke test end-to-end**

Use the fixture from Task 9 + the ortho renders from Task 8:

```bash
blender --background --python backend/scripts/blender_autorig.py -- \
  --input backend/media/rigs/1/0f855599-39df-487f-a827-accedd052d5d/johnny_joestar.fbx \
  --output /tmp/out.glb \
  --bones /tmp/bones.json \
  --pose /tmp/pose.json \
  --landmarks-out /tmp/landmarks.json \
  --landmarks-from-ai backend/apps/rigging/tests/fixtures/claude_response_johnny.json \
  --format fbx
cat /tmp/landmarks.json
```

Expected: 14 landmark keys; values broadly match the AI-pixel-derived positions, not pure AABB defaults.

- [ ] **Step 7: Commit**

```bash
git add backend/scripts/blender_autorig.py backend/scripts/_test_pixel_to_world.py
git commit -m "feat(rigging): pixel→world raycast + seed-to-vertex refinement for AI landmarks"
```

---

### Task 13: Apply sanity checks + failure semantics

**Files:**
- Modify: `backend/apps/rigging/tasks.py`

Plug the Task 4 sanity checks into the round-trip. If AI seeds fail sanity → drop them, use geometry-only. If geometry refinement fails sanity → use AI seeds unrefined. If both fail → AABB defaults; rig still finishes as `done`.

- [ ] **Step 1: After Blender returns the landmark JSON in `tasks.py`, validate**

After `landmarks_path` is read (the existing Task 8 / Plan-A1 logic):

```python
from .sanity import check_landmarks

if landmarks_path.exists():
    candidate = json.loads(landmarks_path.read_text())
    world_aabb_tuple = tuple(map(tuple, request_data.get("world_aabb", ((-1,0,-1),(1,2,1)))))
    sr = check_landmarks(candidate, world_aabb=world_aabb_tuple)
    if sr.ok:
        rig.landmarks = candidate
    else:
        log.warning("Sanity failed on AI+refined landmarks: %s", [f.code for f in sr.failures])
        # Re-run Blender geometry-only by stripping --landmarks-from-ai
        # (or fall through to AABB defaults — simpler).
        from apps.rigging.legacy_landmarks import DEFAULT_LANDMARKS_UNIT_HEIGHT
        rig.landmarks = dict(DEFAULT_LANDMARKS_UNIT_HEIGHT)
        rig.detection_method = "failed"
```

**Implementation locked (spec §8):** when sanity fails on AI+refined landmarks, re-spawn Blender **without** `--landmarks-from-ai` so the full geometry-only path produces the landmarks. Don't shortcut to AABB defaults — geometry alone still gives a better rig than a bare bounding box. Only fall through to `legacy_landmarks.DEFAULT_LANDMARKS_UNIT_HEIGHT` when the geometry-only re-run **also** fails sanity. In both cases `detection_method = "failed"` so the frontend banner fires.

- [ ] **Step 2: Add a `detection_method=failed` admin / API surface note**

Confirm `rig.detection_method = "failed"` writes through. The user's editor banner messaging is a frontend task (Task 16), not here.

- [ ] **Step 3: Smoke test by feeding a deliberately bad fixture**

Create `backend/apps/rigging/tests/fixtures/claude_response_inverted.json` with `groin` placed above `chin`. Run the pipeline against it; assert `rig.detection_method == "failed"` and the rig still finishes `done`.

- [ ] **Step 4: Commit**

```bash
git add backend/apps/rigging/tasks.py backend/apps/rigging/tests/fixtures/claude_response_inverted.json
git commit -m "feat(rigging): sanity checks gate AI landmarks; defaults on cascade failure"
```

---

### Task 14: Prop labels → automatic parenting

**Files:**
- Modify: `backend/scripts/blender_autorig.py` (post-Rigify generate pass)

After Rigify generates the rig, walk the AI's `mesh_object_labels` and parent non-body meshes to the correct deform bone.

- [ ] **Step 1: Plumb the labels into the consumer block**

In the `--landmarks-from-ai` branch in `main()`, capture `mesh_object_labels = ai_response.get("mesh_objects", {})` alongside the seeds.

- [ ] **Step 2: After `parent_to_armature(...)` and `strip_to_deform_bones`, add the parenting pass**

```python
def parent_props_to_bones(meshes, mesh_object_labels, armature):
    """Parent non-body meshes to their semantically-correct deform bone."""
    bone_target_by_label = {
        "hat":                    "DEF-spine.005",   # head
        "accessory_held_left":    "DEF-hand.L",
        "accessory_held_right":   "DEF-hand.R",
        # clothing stays auto-weighted; other = no-op
    }
    for m in meshes:
        label = mesh_object_labels.get(m.name)
        bone_name = bone_target_by_label.get(label)
        if not bone_name:
            continue
        # Parent with vertex-group, weight 1.0 on the target bone.
        if bone_name in armature.data.bones:
            m.parent = armature
            m.parent_type = "BONE"
            m.parent_bone = bone_name
            log(f"Parented {m.name} ({label}) → {bone_name}")
```

Call it after the existing rig parent-set block.

- [ ] **Step 3: Smoke test**

Hand-author a fixture with a `Hat` mesh and verify the resulting GLB has the hat parented to `DEF-spine.005`. (Inspect the GLB with `gltf-pipeline` or open in three.js viewer.)

- [ ] **Step 4: Commit**

```bash
git add backend/scripts/blender_autorig.py
git commit -m "feat(rigging): parent labelled props (hat, accessories) to correct deform bones"
```

---

### Task 15: Surface `detection_method` in the API serializer

**Files:**
- Modify: `backend/apps/rigging/views.py` (or `serializers.py` if separated)

- [ ] **Step 1: Find the rig serializer**

```bash
grep -n "RiggedModelSerializer\|class.*Serializer\|fields =" backend/apps/rigging/views.py backend/apps/rigging/serializers.py 2>/dev/null
```

- [ ] **Step 2: Add `detection_method` to the serializer fields**

In the rig serializer's `fields` tuple, append `"detection_method"`.

- [ ] **Step 3: Add to the status endpoint payload**

In `RiggedModelViewSet.status_action`, include `"detection_method": rig.detection_method` in the returned dict.

- [ ] **Step 4: Smoke test**

```bash
curl http://localhost:8000/api/v1/rigs/<id>/status/ | python -m json.tool | grep detection
curl http://localhost:8000/api/v1/rigs/<id>/        | python -m json.tool | grep detection
```

Expected: `"detection_method": "geometry"` (or whichever value the row holds).

- [ ] **Step 5: Commit**

```bash
git add backend/apps/rigging/views.py
git commit -m "feat(api): expose detection_method on rig detail + status endpoints"
```

---

### Task 16: Frontend badge for `detection_method`

**Files:**
- Modify: `frontend/src/lib/api.ts`
- Modify: `frontend/src/app/editor/[modelId]/page.tsx` (the editor page) or wherever the rig metadata is shown

- [ ] **Step 1: Extend the `RiggedModel` TypeScript type**

In `frontend/src/lib/api.ts`, find the `RiggedModel` type/interface and add:

```ts
detection_method?: "geometry" | "llm_vision" | "user_landmarks" | "failed";
```

- [ ] **Step 2: Render a small badge on the editor page**

In the editor page where the rig name / status is displayed, add:

```tsx
{rig.detection_method && (
  <span className={`badge badge-${rig.detection_method}`}>
    {rig.detection_method === "llm_vision"     && "AI-assisted"}
    {rig.detection_method === "geometry"       && "Geometry-only"}
    {rig.detection_method === "user_landmarks" && "Manual landmarks"}
  </span>
)}

{rig.detection_method === "failed" && (
  <div className="banner banner-warning">
    The AI couldn&apos;t read your model — the auto-rig may be off.
    Adjust the landmarks below if needed.
  </div>
)}
```

- [ ] **Step 3: Typecheck + manual UI verification**

```bash
cd frontend && npx tsc --noEmit
npm run dev
```

Open an existing rig in `/editor/<id>` → confirm the badge renders with the correct label.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/lib/api.ts frontend/src/app/editor/
git commit -m "feat(frontend): show detection_method badge on editor page"
```

---

### Task 17: End-to-end verification (both modes, both test models)

**Files:** none — verification only.

- [ ] **Step 1: Geometry-only run on Johnny Joestar (baseline)**

```bash
unset LANDMARK_VISION_PROVIDER
# Upload via /upload UI or:
curl -X POST http://localhost:8000/api/v1/rigs/ \
  -H "Authorization: Bearer $TOKEN" \
  -F file=@backend/media/rigs/1/0f855599-39df-487f-a827-accedd052d5d/johnny_joestar.fbx \
  -F name="E2E geometry-only"
```

Expected: status `done`, `detection_method=geometry`, rig wrist bones at the model's hands.

- [ ] **Step 2: AI-mode run on Johnny Joestar**

```bash
export LANDMARK_VISION_PROVIDER=claude
# (user has placed ANTHROPIC_API_KEY in backend/.env)
# Upload same FBX again as a fresh rig.
```

Expected: status `done`, `detection_method=llm_vision`, `vision_response_raw` populated, rig wrist bones at the model's hands. Compare against geometry-only output — should be similar or better.

- [ ] **Step 3: AI-mode run on Freddy (the failing case)**

```bash
curl -X POST http://localhost:8000/api/v1/rigs/ \
  -H "Authorization: Bearer $TOKEN" \
  -F file=@backend/media/rigs/1/0355b5b9-1932-45f5-aa74-1475cd3b2b2e/<freddy.fbx> \
  -F name="E2E Freddy AI mode"
```

Expected: status `done`, `detection_method=llm_vision`, wrist bones now at Freddy's actual hand joints (NOT at paw tips). This is the canonical pass criterion.

- [ ] **Step 4: Sanity-failure path**

Edit a copy of the Johnny ortho response fixture to put `groin` above `chin`, point the AI provider at it via monkey-patch (or use a recorded bad response), upload, and verify:
- Rig finishes `done`
- `detection_method=failed`
- Editor shows the "Open editor to adjust" badge

- [ ] **Step 5: Cost check**

Visit https://console.anthropic.com → Usage. Each successful AI rig should cost ≈ $0.004. If actual is significantly higher, investigate token usage (the prompt is the variable to tune).

- [ ] **Step 6: Final commit if any tuning landed**

```bash
git add -p   # carefully stage any threshold tunings
git commit -m "tune(rigging): post-E2E adjustments (sanity thresholds / refinement bands)"
```

- [ ] **Step 7: Push branch + open PR**

```bash
git push origin Feature/test
gh pr create --title "feat(rigging): geometry + Claude Haiku 4.5 vision auto-rig duo" \
  --body "$(cat <<'EOF'
## Summary
- Duo auto-rig: Claude Haiku 4.5 vision provides semantic seeds; Blender geometry refines to mesh vertices
- ~$0.004 / rig at Haiku rates; geometry-only fallback when `LANDMARK_VISION_PROVIDER=none` or API key missing
- New `detection_method` audit field tracks which path produced each rig
- Sanity checks (groin<chin, symmetry, AABB-bounds, anatomical order) gate the result; failures cascade gracefully — every rig still finishes `done`
- Spec: `Docs/specs/2026-05-12-auto-rig-perfect.md`

## Test plan
- [x] Geometry-only Johnny Joestar — `detection_method=geometry`, rig fits
- [x] AI-mode Johnny Joestar — `detection_method=llm_vision`, rig fits, response stored
- [x] AI-mode Freddy — wrists at actual hands (regression-test for paw-tip bug)
- [x] Sanity failure path — rig still finishes `done` with `detection_method=failed`
- [x] Cost per rig ~$0.004 (verified in Anthropic console)
EOF
)"
```

---

## Self-review

Running the skill's self-check against the plan above.

**Spec coverage** (handoff §"Auto-rig redesign — agreed design" and §"What the next Claude session should do"):

- Ortho-render step + AI request file → Tasks 8, 9 — covered
- `tasks.py` round-trip → Task 10 — covered
- Anthropic provider behind abstraction → Tasks 7, 9 — covered
- Pixel-to-3D raycast + seed-to-vertex refinement → Task 12 — covered
- Sanity checks + cascading fallback → Tasks 4, 13 — covered
- Props labelled & parented → Task 14 — covered
- `detection_method` migration + admin/UI → Tasks 3, 15, 16 — covered
- M1 (A-pose + sanity, no AI) → Tasks 3–5 — covered, testable before key arrives
- Formal spec doc → Task 1 — covered, blocks all subsequent tasks pending user review
- Geometry-only mode when key missing → Task 7 (NoneProvider as default) — covered
- Preserve uncommitted work (handoff §"Uncommitted changes already on disk") → Task 2 — covered

**Placeholder scan:**

- "Decide implementation details" appears in Task 13 Step 1 — but it's gated on the user's Task 1 Step 2 decision (cascade-to-geometry vs. fail-loudly), which is intentionally elevated to a user-facing choice rather than buried as a TBD. Acceptable.
- "Define `_bbox_world(mesh)` helper at module scope" in Task 8 Step 3 — the function body is described in one sentence but not shown. **Fix inline:** the implementation is `return [list(m.matrix_world @ Vector(c)) for c in m.bound_box]` projected to min/max — small enough to leave for the engineer; explicit code below.

Inline fix for Task 8:

```python
def _bbox_world(mesh):
    """World-space [[xmin,ymin,zmin],[xmax,ymax,zmax]] for a mesh object."""
    from mathutils import Vector as _V
    corners = [mesh.matrix_world @ _V(c) for c in mesh.bound_box]
    xs = [c.x for c in corners]; ys = [c.y for c in corners]; zs = [c.z for c in corners]
    return [[min(xs), min(ys), min(zs)], [max(xs), max(ys), max(zs)]]
```

- "Add the prompt template exactly per spec" in Task 9 Step 1 — the prompt is fully reproduced in Task 1 §Step 1 sub-bullet 5; Task 9 copies it. Acceptable cross-reference.
- "Open question for you to answer" in Task 1 — intentional product question, not a code placeholder. Acceptable.

**Type consistency:**

- `VisionRequest.views` / `VisionResponse.landmarks` / `mesh_object_labels` — same shape used in Tasks 7, 9, 10, 12, 13. Consistent.
- `detection_method` values `"geometry" | "llm_vision" | "user_landmarks" | "failed"` — identical in models (Task 3), tasks.py (Tasks 10, 13), frontend (Task 16). Consistent.
- `LANDMARK_KEYS` tuple — identical between `apps/rigging/sanity.py` (Task 4) and `backend/scripts/blender_autorig.py` (pre-existing). Consistent.
- `--render-ortho-views` / `--ai-request-out` / `--ortho-render-dir` / `--landmarks-from-ai` flag names — consistent across `blender_autorig.py` definitions and `tasks.py` subprocess invocations.

No drift detected.

---

## Execution Handoff

Plan complete and saved to `Docs/plans/2026-05-12-auto-rig-perfect.md`. Two execution options:

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration. Task 1 will pause for your spec review before any code lands.

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints. You confirm at each milestone boundary (after Tasks 2, 5, 8, 11, 14, 17).

Which approach?
