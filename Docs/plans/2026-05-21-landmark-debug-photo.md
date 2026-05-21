# Landmark Debug Photo Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist a 2×2 annotated debug photo per rig showing where the Claude vision provider placed each landmark versus where the rig actually used it.

**Architecture:** The Blender script projects the final placed landmarks back to pixel coordinates (a new sidecar JSON), reusing its existing ortho-camera convention. The Django task then composites the four ortho PNGs — already on disk — into one annotated 2×2 image with Pillow and stores it on `RiggedModel`. The photo is produced only on the `llm_vision` path and is strictly best-effort: it never fails or slows a rig.

**Tech Stack:** Python 3.10+, Django 5.1 / DRF, Blender `bpy` (script side), Pillow 10.x.

**Reference spec:** `Docs/specs/2026-05-21-landmark-debug-photo-design.md`

**Conventions:**
- All paths below are relative to `rigflow-project/rigflow-project/` (the inner working repo — see `CLAUDE.md`). Backend commands run from `backend/`.
- Commit messages use conventional-commit prefixes (`feat(rigging):`, `test(rigging):`, etc.) and end with the line:
  `Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>`
- Django tests run with `python manage.py test` from `backend/`. Standalone script tests run with `python scripts/<name>.py` from `backend/`.

---

## File Structure

| File | Responsibility | Action |
|---|---|---|
| `backend/scripts/blender_autorig.py` | Add `world_to_pixel()`, `project_landmarks_to_pixels()`, `write_landmark_pixels_if_requested()`; new CLI flags; call sites in `main()`. | Modify |
| `backend/scripts/_test_world_to_pixel.py` | Standalone (no-Blender) round-trip test for the two projection functions. | Create |
| `backend/apps/rigging/debug_photo.py` | `build_landmark_debug_photo()` — pure Pillow compositing of the 2×2 annotated image. | Create |
| `backend/apps/rigging/tests/test_debug_photo.py` | Django tests for the compositor. | Create |
| `backend/apps/rigging/models.py` | Add `landmark_debug_image` `ImageField`. | Modify |
| `backend/apps/rigging/migrations/0005_riggedmodel_landmark_debug_image.py` | Schema migration for the new field. | Create (via `makemigrations`) |
| `backend/apps/rigging/tasks.py` | Pass new flags to Blender; build and save the photo after a successful `llm_vision` run. | Modify |
| `backend/apps/rigging/serializers.py` | Add `landmark_debug_image_url`. | Modify |
| `backend/apps/rigging/admin.py` | Expose `landmark_debug_image` in admin. | Modify |
| `backend/apps/rigging/tests/test_e2e_pipeline.py` | Blender-gated test asserting the photo is produced on the AI path. | Modify |

---

## Task 1: `world_to_pixel()` projection helper

The inverse of the existing `pixel_to_world_ray()`. Pure function — testable with stubbed `bpy`/`mathutils`, no Blender runtime.

**Files:**
- Create: `backend/scripts/_test_world_to_pixel.py`
- Modify: `backend/scripts/blender_autorig.py` (add function immediately after `pixel_to_world_ray()`, which ends around line 1641)

- [ ] **Step 1: Write the failing standalone test**

Create `backend/scripts/_test_world_to_pixel.py`:

```python
"""Standalone smoke-test for world_to_pixel / project_landmarks_to_pixels.

No Blender runtime needed. Run with:
    python scripts/_test_world_to_pixel.py   (from backend/)
"""
import importlib.util
import sys
from pathlib import Path


# Stub bpy / mathutils so blender_autorig.py imports in plain Python.
class _Vec:
    def __init__(self, xyz):
        self.x, self.y, self.z = float(xyz[0]), float(xyz[1]), float(xyz[2])

    def __iter__(self):
        return iter((self.x, self.y, self.z))

    def __getitem__(self, i):
        return (self.x, self.y, self.z)[i]


stub_mu = type(sys)("mathutils")
stub_mu.Vector = _Vec
stub_mu.Quaternion = object
stub_mu.Matrix = object
sys.modules["mathutils"] = stub_mu
sys.modules["bpy"] = type(sys)("bpy")

src = Path(__file__).parent / "blender_autorig.py"
spec = importlib.util.spec_from_file_location("blender_autorig", src)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
world_to_pixel = mod.world_to_pixel
pixel_to_world_ray = mod.pixel_to_world_ray

AABB = ((-1.0, -0.3, 0.0), (1.0, 0.2, 2.0))
OS = 2.3
IMAGE = 512

failures = []


def check(name, cond):
    status = "OK" if cond else "FAIL"
    print(f"  [{status}] {name}")
    if not cond:
        failures.append(name)


# Round-trip: a pixel → world ray origin → back to the same pixel.
for view in ("front", "back", "left", "right"):
    for (px, py) in ((256, 256), (100, 400), (10, 10), (500, 90)):
        origin, _ = pixel_to_world_ray(view, px, py, IMAGE, OS, AABB)
        back = world_to_pixel(view, origin, IMAGE, OS, AABB)
        ok = back is not None and abs(back[0] - px) < 1e-3 and abs(back[1] - py) < 1e-3
        check(f"{view} round-trip ({px},{py})", ok)

# Off-frame point projects to None.
far_origin, _ = pixel_to_world_ray("front", 256, 256, IMAGE, OS, AABB)
far = mod.Vector((far_origin.x + OS * 5, far_origin.y, far_origin.z))
check("front off-frame → None", world_to_pixel("front", far, IMAGE, OS, AABB) is None)

print()
if failures:
    print(f"FAILED: {failures}")
    sys.exit(1)
print("All world_to_pixel tests passed.")
```

- [ ] **Step 2: Run the test to verify it fails**

Run (from `backend/`): `python scripts/_test_world_to_pixel.py`
Expected: FAIL — `AttributeError: module 'blender_autorig' has no attribute 'world_to_pixel'`.

- [ ] **Step 3: Implement `world_to_pixel()`**

In `backend/scripts/blender_autorig.py`, immediately after the `pixel_to_world_ray()` function (it returns `origin, direction` and ends just before `def _bvh_tree_for(mesh):`), add:

```python
def world_to_pixel(view_name, world_point, image_size, ortho_scale, world_aabb):
    """Project a world-space point to pixel coords in an ortho view.

    Algebraic inverse of pixel_to_world_ray — shares the same per-view camera
    convention. `world_point` is anything indexable as [x, y, z] (a
    mathutils.Vector or a 3-tuple). Returns [px, py] (floats, top-left origin)
    or None when the point projects outside the [0, image_size) frame.
    """
    (mn, mx) = world_aabb
    cx = (mn[0] + mx[0]) / 2
    cy = (mn[1] + mx[1]) / 2
    cz = (mn[2] + mx[2]) / 2
    wx, wy, wz = world_point[0], world_point[1], world_point[2]

    if view_name == "front":
        u, v = wx - cx, wz - cz
    elif view_name == "back":
        u, v = cx - wx, wz - cz
    elif view_name == "left":
        u, v = cy - wy, wz - cz
    elif view_name == "right":
        u, v = wy - cy, wz - cz
    else:
        raise ValueError(f"unknown view {view_name!r}")

    if ortho_scale <= 0:
        return None
    px = (u / ortho_scale + 0.5) * image_size
    py = (0.5 - v / ortho_scale) * image_size
    if px < 0 or px >= image_size or py < 0 or py >= image_size:
        return None
    return [px, py]
```

- [ ] **Step 4: Run the test to verify it passes**

Run (from `backend/`): `python scripts/_test_world_to_pixel.py`
Expected: PASS — `All world_to_pixel tests passed.`

- [ ] **Step 5: Commit**

```bash
git add scripts/blender_autorig.py scripts/_test_world_to_pixel.py
git commit -m "$(cat <<'EOF'
feat(rigging): add world_to_pixel ortho projection helper

Inverse of pixel_to_world_ray; projects a world point onto an ortho
view's pixel plane. Standalone round-trip test, no Blender needed.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: `project_landmarks_to_pixels()` helper

Converts the 14 three.js-editor-space landmarks back to Blender world space, then to per-view pixels.

**Files:**
- Modify: `backend/scripts/blender_autorig.py` (add function right after `world_to_pixel()`)
- Modify: `backend/scripts/_test_world_to_pixel.py` (extend with projection assertions)

- [ ] **Step 1: Extend the test with failing assertions**

In `backend/scripts/_test_world_to_pixel.py`, add the following **before** the final `print()` / `if failures:` block:

```python
# project_landmarks_to_pixels: mesh_h=2.0 → half=1.0, so three.js (tx,ty,tz)
# maps to world (tx, -tz, ty). Centred AABB, front ortho_scale=2, 512px.
project_landmarks_to_pixels = mod.project_landmarks_to_pixels
cam_params = {
    "world_aabb": [[-1.0, -1.0, -1.0], [1.0, 1.0, 1.0]],
    "views": {
        v: {"ortho_scale": 2.0, "image_size": [512, 512]}
        for v in ("front", "back", "left", "right")
    },
}
proj = project_landmarks_to_pixels(
    {"chin": [0.0, 0.0, 0.0], "groin": [0.5, 0.0, 0.0]}, 2.0, cam_params
)
check("front chin → image centre",
      proj["front"]["chin"] == [256.0, 256.0])
check("front groin → x shifted right",
      abs(proj["front"]["groin"][0] - 384.0) < 1e-6)
check("all four views projected",
      set(proj) == {"front", "back", "left", "right"})
```

- [ ] **Step 2: Run the test to verify it fails**

Run (from `backend/`): `python scripts/_test_world_to_pixel.py`
Expected: FAIL — `AttributeError: module 'blender_autorig' has no attribute 'project_landmarks_to_pixels'`.

- [ ] **Step 3: Implement `project_landmarks_to_pixels()`**

In `backend/scripts/blender_autorig.py`, immediately after `world_to_pixel()`, add:

```python
def project_landmarks_to_pixels(landmarks_three, mesh_h, camera_params):
    """Project three.js-editor-space landmarks back to per-view pixel coords.

    landmarks_three  {key: [tx, ty, tz]} in three.js editor space (Y-up, model
                     normalised to height 2.0).
    mesh_h           metarig height in metres — the canonical reference used by
                     to_three_from_blender (s = 2.0 / mesh_h); needed to invert.
    camera_params    {"world_aabb": [[..],[..]],
                      "views": {view: {"ortho_scale": float,
                                        "image_size": [w, h]}}}

    Returns {view: {key: [px, py] | None}} for front/back/left/right. A landmark
    is None for a view when it projects outside that view's frame.
    """
    world_aabb = (
        tuple(camera_params["world_aabb"][0]),
        tuple(camera_params["world_aabb"][1]),
    )
    half = mesh_h / 2.0  # inverse of s = 2.0 / mesh_h in to_three_from_blender
    views = camera_params.get("views") or {}

    out = {}
    for view in ("front", "back", "left", "right"):
        vp = views.get(view) or {}
        ortho_scale = float(vp.get("ortho_scale") or 0.0)
        image_size = (vp.get("image_size") or [512, 512])[0]
        view_out = {}
        for key, tjs in landmarks_three.items():
            tx, ty, tz = float(tjs[0]), float(tjs[1]), float(tjs[2])
            # Inverse of to_three_from_blender (bx,by,bz)→(bx*s, bz*s, -by*s):
            world_point = (tx * half, -tz * half, ty * half)
            view_out[key] = world_to_pixel(
                view, world_point, image_size, ortho_scale, world_aabb
            )
        out[view] = view_out
    return out
```

- [ ] **Step 4: Run the test to verify it passes**

Run (from `backend/`): `python scripts/_test_world_to_pixel.py`
Expected: PASS — `All world_to_pixel tests passed.`

- [ ] **Step 5: Commit**

```bash
git add scripts/blender_autorig.py scripts/_test_world_to_pixel.py
git commit -m "$(cat <<'EOF'
feat(rigging): project three.js landmarks to ortho-view pixels

project_landmarks_to_pixels inverts the editor-space → world conversion
and projects each of the 14 landmarks onto all four ortho views.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: CLI flags and `main()` wiring for the pixel sidecar

Add the `--landmark-pixels-out` / `--camera-params` flags and write the projection sidecar from both the AI branch and the geometry branch.

**Files:**
- Modify: `backend/scripts/blender_autorig.py` — `parse_args()` (around line 50–88), add a helper, and two call sites in `main()`.

- [ ] **Step 1: Add the two CLI flags**

In `parse_args()`, immediately after the `--landmarks-from-ai` argument block, add:

```python
    p.add_argument("--landmark-pixels-out", default=None,
                   help="If set (with --camera-params), write the final placed "
                        "landmarks projected to per-view pixel coords as JSON. "
                        "Consumed by the Django task to build the debug photo.")
    p.add_argument("--camera-params", default=None,
                   help="Path to the Phase-1 ai_request.json — supplies world_aabb "
                        "and per-view ortho_scale for --landmark-pixels-out.")
```

- [ ] **Step 2: Add the `write_landmark_pixels_if_requested()` helper**

In `backend/scripts/blender_autorig.py`, immediately after `project_landmarks_to_pixels()`, add:

```python
def write_landmark_pixels_if_requested(args, landmarks_three, mesh_h):
    """Write the final-landmark pixel-projection sidecar when both
    --landmark-pixels-out and --camera-params were supplied.

    Best-effort: any error is logged and swallowed so it never affects the
    rig result.
    """
    if not (args.landmark_pixels_out and args.camera_params):
        return
    try:
        camera_params = json.loads(Path(args.camera_params).read_text())
        coerced = {
            k: [float(c) for c in v] for k, v in landmarks_three.items()
        }
        pixels = project_landmarks_to_pixels(coerced, mesh_h, camera_params)
        Path(args.landmark_pixels_out).write_text(json.dumps(pixels, indent=2))
        log(f"Wrote landmark pixel projection → {args.landmark_pixels_out}")
    except Exception as e:
        log(f"Landmark pixel projection failed (non-fatal): {e}")
```

- [ ] **Step 3: Call the helper from the AI branch**

In `main()`, in the `elif args.landmarks_from_ai:` branch, find the final line of that branch:

```python
        place_bones_from_landmarks(metarig, final_landmarks, mesh_h)
```

Insert immediately **before** that line:

```python
        write_landmark_pixels_if_requested(args, final_landmarks, mesh_h)
```

- [ ] **Step 4: Call the helper from the geometry branch**

In `main()`, in the final `else:` branch, find:

```python
    else:
        auto_landmarks = detect_landmarks(meshes, pose=detected_pose, reference_height=mesh_h)
        log(f"Mode: AUTO (detected {len(auto_landmarks)} landmarks)")
        place_bones_from_landmarks(metarig, auto_landmarks, mesh_h)
```

Insert a line **before** `place_bones_from_landmarks`:

```python
    else:
        auto_landmarks = detect_landmarks(meshes, pose=detected_pose, reference_height=mesh_h)
        log(f"Mode: AUTO (detected {len(auto_landmarks)} landmarks)")
        write_landmark_pixels_if_requested(args, auto_landmarks, mesh_h)
        place_bones_from_landmarks(metarig, auto_landmarks, mesh_h)
```

- [ ] **Step 5: Verify the script still parses and the standalone test still passes**

Run (from `backend/`):
```bash
python -c "import ast; ast.parse(open('scripts/blender_autorig.py').read()); print('syntax OK')"
python scripts/_test_world_to_pixel.py
```
Expected: `syntax OK` then `All world_to_pixel tests passed.`
(The `main()` call sites are exercised end-to-end by the Blender-gated test in Task 8.)

- [ ] **Step 6: Commit**

```bash
git add scripts/blender_autorig.py
git commit -m "$(cat <<'EOF'
feat(rigging): emit landmark pixel sidecar from the autorig script

New --landmark-pixels-out / --camera-params flags. Both the AI and
geometry branches write the final placed landmarks projected to per-view
pixels, so the Django task can build the debug photo.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: `debug_photo.py` compositor module

Pure-Pillow module that draws the 2×2 annotated image. No Blender, no Django models — fully unit-testable.

**Files:**
- Create: `backend/apps/rigging/debug_photo.py`
- Create: `backend/apps/rigging/tests/test_debug_photo.py`

- [ ] **Step 1: Write the failing test**

Create `backend/apps/rigging/tests/test_debug_photo.py`:

```python
"""Tests for the landmark debug photo compositor."""
import tempfile
from pathlib import Path

from django.test import SimpleTestCase
from PIL import Image

from apps.rigging.debug_photo import build_landmark_debug_photo


def _write_ortho(dir_path):
    """Write four 512×512 placeholder ortho PNGs."""
    for view in ("front", "back", "left", "right"):
        Image.new("RGB", (512, 512), (90, 90, 90)).save(
            Path(dir_path) / f"{view}.png")


class BuildLandmarkDebugPhotoTests(SimpleTestCase):
    def test_builds_1024_composite(self):
        with tempfile.TemporaryDirectory() as td:
            _write_ortho(td)
            out = Path(td) / "debug.png"
            views = ("front", "back", "left", "right")
            ai = {v: {"chin": [100, 50]} for v in views}
            final = {v: {"chin": [110, 60]} for v in views}
            self.assertTrue(build_landmark_debug_photo(td, ai, final, out))
            self.assertTrue(out.is_file())
            with Image.open(out) as im:
                self.assertEqual(im.size, (1024, 1024))

    def test_null_landmarks_are_skipped(self):
        with tempfile.TemporaryDirectory() as td:
            _write_ortho(td)
            out = Path(td) / "debug.png"
            views = ("front", "back", "left", "right")
            ai = {v: {"chin": None, "groin": [50, 50]} for v in views}
            self.assertTrue(build_landmark_debug_photo(td, ai, {}, out))
            self.assertTrue(out.is_file())

    def test_missing_ortho_returns_false(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "debug.png"
            self.assertFalse(build_landmark_debug_photo(td, {}, {}, out))
            self.assertFalse(out.is_file())
```

- [ ] **Step 2: Run the test to verify it fails**

Run (from `backend/`): `python manage.py test apps.rigging.tests.test_debug_photo -v 2`
Expected: FAIL — `ModuleNotFoundError: No module named 'apps.rigging.debug_photo'`.

- [ ] **Step 3: Implement `debug_photo.py`**

Create `backend/apps/rigging/debug_photo.py`:

```python
"""Compositing for the landmark debug photo (debug/audit aid).

Draws a 2×2 grid of the four ortho renders, marking where the AI placed each
landmark (hollow orange circle) versus where the rig actually used it (filled
green dot). Strictly best-effort: any failure is logged and returns False so
the rig still completes.
"""
import logging
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

log = logging.getLogger(__name__)

_VIEWS = ("front", "back", "left", "right")
# (column, row) of each view in the 2×2 grid.
_GRID = {"front": (0, 0), "back": (1, 0), "left": (0, 1), "right": (1, 1)}

_AI_COLOR = (255, 140, 0)        # orange — AI pick
_FINAL_COLOR = (40, 200, 60)     # green  — final used
_TEXT_COLOR = (255, 255, 255)
_CONNECT_COLOR = (160, 160, 160)


def build_landmark_debug_photo(ortho_dir, ai_picks, final_pixels, out_path):
    """Composite a 2×2 annotated debug photo.

    ortho_dir     directory containing front.png/back.png/left.png/right.png
    ai_picks      {view: {key: [px, py] | None}} — AI's returned pixels
    final_pixels  {view: {key: [px, py] | None}} — rig's final pixels
    out_path      destination PNG path

    Returns True on success, False on any missing input or draw error.
    """
    try:
        ortho_dir = Path(ortho_dir)
        tiles = {}
        for view in _VIEWS:
            png = ortho_dir / f"{view}.png"
            if not png.is_file():
                log.warning("Debug photo: missing ortho render %s", png)
                return False
            tiles[view] = Image.open(png).convert("RGB")

        w, h = tiles["front"].size
        canvas = Image.new("RGB", (w * 2, h * 2), (20, 20, 20))
        font = ImageFont.load_default()

        for view in _VIEWS:
            tile = tiles[view]
            draw = ImageDraw.Draw(tile)
            view_ai = (ai_picks or {}).get(view) or {}
            view_final = (final_pixels or {}).get(view) or {}
            for key in sorted(set(view_ai) | set(view_final)):
                ap = view_ai.get(key)
                fp = view_final.get(key)
                if ap and fp:
                    draw.line([tuple(ap), tuple(fp)],
                              fill=_CONNECT_COLOR, width=1)
                if ap:
                    _circle(draw, ap, 6, _AI_COLOR, 2)
                if fp:
                    _dot(draw, fp, 4, _FINAL_COLOR)
                anchor = fp or ap
                if anchor:
                    draw.text((anchor[0] + 7, anchor[1] - 5), key,
                              fill=_TEXT_COLOR, font=font)
            draw.text((6, 6), view.upper(), fill=_TEXT_COLOR, font=font)
            col, row = _GRID[view]
            canvas.paste(tile, (col * w, row * h))

        ImageDraw.Draw(canvas).text(
            (6, h * 2 - 16),
            "orange = AI pick    green = final used",
            fill=_TEXT_COLOR, font=font,
        )

        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        canvas.save(out_path, "PNG")
        return True
    except Exception as e:
        log.warning("Debug photo build failed: %s", e)
        return False


def _circle(draw, center, r, outline, width):
    x, y = center
    draw.ellipse([x - r, y - r, x + r, y + r], outline=outline, width=width)


def _dot(draw, center, r, fill):
    x, y = center
    draw.ellipse([x - r, y - r, x + r, y + r], fill=fill)
```

- [ ] **Step 4: Run the test to verify it passes**

Run (from `backend/`): `python manage.py test apps.rigging.tests.test_debug_photo -v 2`
Expected: PASS — `Ran 3 tests` / `OK`.

- [ ] **Step 5: Commit**

```bash
git add apps/rigging/debug_photo.py apps/rigging/tests/test_debug_photo.py
git commit -m "$(cat <<'EOF'
feat(rigging): add landmark debug photo compositor

build_landmark_debug_photo draws a 2x2 annotated grid of the four ortho
renders — AI picks vs final-used landmarks. Best-effort: returns False on
any error rather than raising.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: `landmark_debug_image` model field + migration

**Files:**
- Modify: `backend/apps/rigging/models.py` (`RiggedModel`, after `preview_thumbnail`)
- Create: `backend/apps/rigging/migrations/0005_riggedmodel_landmark_debug_image.py` (generated)

- [ ] **Step 1: Add the field**

In `backend/apps/rigging/models.py`, find:

```python
    # Output from Blender
    rigged_glb        = models.FileField(upload_to=rig_upload_path, blank=True)
    preview_thumbnail = models.ImageField(upload_to=rig_upload_path, blank=True)
```

Add a third line directly below `preview_thumbnail`:

```python
    # Output from Blender
    rigged_glb        = models.FileField(upload_to=rig_upload_path, blank=True)
    preview_thumbnail = models.ImageField(upload_to=rig_upload_path, blank=True)
    landmark_debug_image = models.ImageField(
        upload_to=rig_upload_path, blank=True,
        help_text=(
            "2x2 annotated render showing AI-detected vs final landmark "
            "positions. Populated only on the llm_vision path."
        ),
    )
```

- [ ] **Step 2: Generate the migration**

Run (from `backend/`): `python manage.py makemigrations rigging`
Expected: creates `apps/rigging/migrations/0005_riggedmodel_landmark_debug_image.py` with one `AddField` operation.

- [ ] **Step 3: Apply and verify the migration**

Run (from `backend/`):
```bash
python manage.py migrate rigging
python manage.py check
```
Expected: migration applies cleanly; `System check identified no issues`.

- [ ] **Step 4: Commit**

```bash
git add apps/rigging/models.py apps/rigging/migrations/0005_riggedmodel_landmark_debug_image.py
git commit -m "$(cat <<'EOF'
feat(rigging): add landmark_debug_image field to RiggedModel

Stores the 2x2 annotated debug photo. ImageField, blank by default,
populated only on the llm_vision path.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: Wire the photo into the rig pipeline (`tasks.py`)

Pass the new flags to Blender (main run + geometry fallback) and build/save the photo after a successful `llm_vision` run.

**Files:**
- Modify: `backend/apps/rigging/tasks.py` (`_run_rig_pipeline`)

- [ ] **Step 1: Declare the pixel-sidecar path**

In `_run_rig_pipeline`, find the temp-path block:

```python
            input_path     = tmp / f"input.{rig.original_format}"
            glb_output     = tmp / "rigged.glb"
            bone_data_path = tmp / "bones.json"
            pose_data_path = tmp / "pose.json"
            landmarks_path = tmp / "landmarks.json"
```

Add one line below `landmarks_path`:

```python
            landmarks_path = tmp / "landmarks.json"
            pixels_path    = tmp / "landmark_pixels.json"
```

- [ ] **Step 2: Pass the flags to the main Phase-2 rig command**

Find the block that appends `--landmarks-from-ai`:

```python
                if ai_response_path is not None:
                    rig_cmd.extend(["--landmarks-from-ai", str(ai_response_path)])
```

Replace it with:

```python
                if ai_response_path is not None:
                    rig_cmd.extend(["--landmarks-from-ai", str(ai_response_path)])
                    rig_cmd.extend([
                        "--landmark-pixels-out", str(pixels_path),
                        "--camera-params",       str(request_path),
                    ])
```

(`request_path` is defined earlier in the same `if not user_landmarks:` block; it is always in scope when `ai_response_path is not None`.)

- [ ] **Step 3: Pass the flags to the geometry-fallback command**

In the sanity-cascade block, find the geometry-fallback path declarations and command:

```python
                    _geo_glb   = tmp / "rigged_geo.glb"
                    _geo_bones = tmp / "bones_geo.json"
                    _geo_lm    = tmp / "landmarks_geo.json"
                    _geo_pose  = tmp / "pose_geo.json"
                    _geo_cmd   = [
                        blender_path, "--background", "--python", str(script_path), "--",
                        "--input",         str(input_path),
                        "--output",        str(_geo_glb),
                        "--bones",         str(_geo_bones),
                        "--landmarks-out", str(_geo_lm),
                        "--pose",          str(_geo_pose),
                        "--format",        rig.original_format,
                    ]
                    _geo_cmd.extend(_extract_rotation_args(extra_args))
```

Replace it with (adds `_geo_pixels` and two flags):

```python
                    _geo_glb    = tmp / "rigged_geo.glb"
                    _geo_bones  = tmp / "bones_geo.json"
                    _geo_lm     = tmp / "landmarks_geo.json"
                    _geo_pose   = tmp / "pose_geo.json"
                    _geo_pixels = tmp / "landmark_pixels_geo.json"
                    _geo_cmd    = [
                        blender_path, "--background", "--python", str(script_path), "--",
                        "--input",               str(input_path),
                        "--output",              str(_geo_glb),
                        "--bones",               str(_geo_bones),
                        "--landmarks-out",       str(_geo_lm),
                        "--pose",                str(_geo_pose),
                        "--format",              rig.original_format,
                        "--landmark-pixels-out", str(_geo_pixels),
                        "--camera-params",       str(request_path),
                    ]
                    _geo_cmd.extend(_extract_rotation_args(extra_args))
```

- [ ] **Step 4: Repoint `pixels_path` when the geometry fallback wins**

In the same block, find where the geometry-fallback outputs are adopted:

```python
                        if _rc_g == 0 and _geo_glb.exists():
                            glb_output     = _geo_glb
                            bone_data_path = _geo_bones
                            landmarks_path = _geo_lm
                            pose_data_path = _geo_pose
```

Add one line:

```python
                        if _rc_g == 0 and _geo_glb.exists():
                            glb_output     = _geo_glb
                            bone_data_path = _geo_bones
                            landmarks_path = _geo_lm
                            pose_data_path = _geo_pose
                            pixels_path    = _geo_pixels
```

- [ ] **Step 5: Build and save the photo after the landmarks read**

Find the landmarks read inside the `with tempfile.TemporaryDirectory()` block:

```python
            if landmarks_path.exists():
                rig.landmarks = json.loads(landmarks_path.read_text())
```

Add the photo block immediately after it:

```python
            if landmarks_path.exists():
                rig.landmarks = json.loads(landmarks_path.read_text())

            # Landmark debug photo — best-effort, llm_vision path only.
            if ai_response_path is not None and pixels_path.exists():
                try:
                    from .debug_photo import build_landmark_debug_photo
                    _ai_picks = json.loads(
                        ai_response_path.read_text()
                    ).get("landmarks", {})
                    _final_px = json.loads(pixels_path.read_text())
                    _photo = tmp / "landmark_debug.png"
                    if build_landmark_debug_photo(
                        tmp / "ortho", _ai_picks, _final_px, _photo
                    ):
                        with open(_photo, "rb") as f:
                            rig.landmark_debug_image.save(
                                f"{rig.id}_landmarks.png", File(f), save=False
                            )
                except Exception as e:
                    logger.warning(
                        "Landmark debug photo failed for rig %s: %s", rig_id, e
                    )
```

(`tmp / "ortho"` is where Phase 1 rendered the four PNGs — `ortho_dir` in the AI phase.)

- [ ] **Step 6: Verify the module imports and Django check passes**

Run (from `backend/`):
```bash
python -c "import ast; ast.parse(open('apps/rigging/tasks.py').read()); print('syntax OK')"
python manage.py check
```
Expected: `syntax OK` then `System check identified no issues`.

- [ ] **Step 7: Commit**

```bash
git add apps/rigging/tasks.py
git commit -m "$(cat <<'EOF'
feat(rigging): build landmark debug photo in the rig pipeline

Passes --landmark-pixels-out / --camera-params to the main and
geometry-fallback Blender runs, then composites the 2x2 debug photo and
saves it to landmark_debug_image. Best-effort — never fails the rig.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: Expose the photo via serializer and admin

**Files:**
- Modify: `backend/apps/rigging/serializers.py` (`RiggedModelSerializer`)
- Modify: `backend/apps/rigging/admin.py` (`RiggedModelAdmin`)

- [ ] **Step 1: Add `landmark_debug_image_url` to the serializer**

In `backend/apps/rigging/serializers.py`, replace the whole `RiggedModelSerializer` class with:

```python
class RiggedModelSerializer(serializers.ModelSerializer):
    rigged_glb_url = serializers.SerializerMethodField()
    landmark_debug_image_url = serializers.SerializerMethodField()

    class Meta:
        model = RiggedModel
        fields = [
            "id",
            "name",
            "status",
            "original_format",
            "rigged_glb_url",
            "landmark_debug_image_url",
            "bone_mapping",
            "file_size_mb",
            "error_message",
            "rig_log",
            "detected_pose",
            "pose_angle_deg",
            "pose_confidence",
            "detection_method",
            "created_at",
        ]
        read_only_fields = fields

    def get_rigged_glb_url(self, obj) -> str | None:
        if obj.rigged_glb:
            request = self.context.get("request")
            if request:
                return request.build_absolute_uri(obj.rigged_glb.url)
            return obj.rigged_glb.url
        return None

    def get_landmark_debug_image_url(self, obj) -> str | None:
        if obj.landmark_debug_image:
            request = self.context.get("request")
            if request:
                return request.build_absolute_uri(obj.landmark_debug_image.url)
            return obj.landmark_debug_image.url
        return None
```

- [ ] **Step 2: Expose the field in admin**

In `backend/apps/rigging/admin.py`, find the `readonly_fields` tuple and add `"landmark_debug_image"` to it:

```python
    readonly_fields = (
        "id", "celery_task_id", "processing_time_s",
        "vertex_count", "rig_log", "created_at", "updated_at",
        "bone_mapping", "landmarks", "bone_corrections",
        "pose_angle_deg", "pose_confidence",
        "detection_method", "vision_response_raw",
        "landmark_debug_image",
    )
```

- [ ] **Step 3: Verify**

Run (from `backend/`): `python manage.py check`
Expected: `System check identified no issues`.

- [ ] **Step 4: Commit**

```bash
git add apps/rigging/serializers.py apps/rigging/admin.py
git commit -m "$(cat <<'EOF'
feat(rigging): expose landmark_debug_image via API and admin

Adds landmark_debug_image_url to RiggedModelSerializer (mirrors
rigged_glb_url) and surfaces the field in the RiggedModel admin.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: End-to-end pipeline test + full verification

A Blender-gated test that runs the real pipeline with a mocked Claude provider and asserts the photo is produced. Then run the whole test suite.

**Files:**
- Modify: `backend/apps/rigging/tests/test_e2e_pipeline.py` (append a test class)

- [ ] **Step 1: Inspect the existing AI-mock pattern**

Read `backend/apps/rigging/tests/test_e2e_pipeline.py` and `backend/apps/rigging/tests/fixtures/claude_response_johnny.json`. Confirm: the fixture is a dict with `landmarks` (four view keys) and `mesh_objects`; `_make_rig(fbx_path)` and `_JOHNNY_FBX` are module-level helpers. The test below reuses both.

- [ ] **Step 2: Append the failing test**

Add this class to the **end** of `backend/apps/rigging/tests/test_e2e_pipeline.py`:

```python
class LandmarkDebugPhotoTest(TestCase):
    """The llm_vision path produces a landmark_debug_image."""

    def test_ai_path_produces_debug_photo(self):
        from apps.rigging.tasks import _run_rig_pipeline
        from apps.rigging.landmark_vision.base import VisionResponse

        if not Path(settings.BLENDER_EXECUTABLE).is_file():
            self.skipTest("Blender executable not available")
        if not _JOHNNY_FBX.is_file():
            self.skipTest("test FBX not available")

        fixture = json.loads(
            (FIXTURES / "claude_response_johnny.json").read_text()
        )
        fake_provider = MagicMock()
        fake_provider.detect.return_value = VisionResponse(
            landmarks=fixture["landmarks"],
            mesh_object_labels=fixture.get("mesh_objects", {}),
            notes=fixture.get("notes", ""),
            raw=fixture,
        )

        rig = _make_rig(_JOHNNY_FBX)
        with patch("apps.rigging.landmark_vision.get_provider",
                   return_value=fake_provider):
            _run_rig_pipeline(str(rig.id))

        rig.refresh_from_db()
        self.assertEqual(rig.status, "done")
        self.assertTrue(
            bool(rig.landmark_debug_image),
            "llm_vision run should populate landmark_debug_image",
        )
```

- [ ] **Step 3: Run the new test**

Run (from `backend/`): `python manage.py test apps.rigging.tests.test_e2e_pipeline.LandmarkDebugPhotoTest -v 2`
Expected: PASS — or `skipped` if Blender / the test FBX is unavailable on this machine. A `skipped` result is acceptable; a `FAIL`/`ERROR` is not.

- [ ] **Step 4: Run the full rigging test suite and the standalone projection test**

Run (from `backend/`):
```bash
python manage.py test apps.rigging -v 1
python scripts/_test_world_to_pixel.py
python scripts/_test_pixel_to_world.py
```
Expected: all Django tests pass (Blender-gated ones may skip); both standalone tests print their pass line.

- [ ] **Step 5: Commit**

```bash
git add apps/rigging/tests/test_e2e_pipeline.py
git commit -m "$(cat <<'EOF'
test(rigging): assert llm_vision runs produce a debug photo

Blender-gated e2e test: mocks the Claude provider, runs the pipeline,
asserts landmark_debug_image is populated.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Done criteria

- `python manage.py test apps.rigging` passes (Blender-gated tests may skip).
- `python scripts/_test_world_to_pixel.py` passes.
- `python manage.py check` reports no issues.
- A rig processed on the `llm_vision` path has a non-empty `landmark_debug_image`; `GET /rigs/{id}/` returns a non-null `landmark_debug_image_url`; the image is visible in Django admin.
- Geometry-only and `user_landmarks` rigs leave `landmark_debug_image` blank, and a photo failure never changes a rig's `done`/`failed` outcome.
