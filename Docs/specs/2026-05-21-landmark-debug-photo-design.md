# Landmark Debug Photo — Design

Date: 2026-05-21
Status: approved, ready for implementation planning

## Summary

When the Claude vision provider is used to detect rig landmarks, the pipeline
already renders four orthographic PNGs of the model and receives pixel
coordinates back from Claude. Today those renders and that response live in a
`TemporaryDirectory` that is deleted as soon as the rig finishes — nothing is
kept.

This feature persists a single **2×2 annotated debug photo** per rig that shows,
on top of the rendered views, **where the AI placed each landmark** and **where
the rig actually ended up placing it** after raycasting and sanity checks. It is
a debug/audit aid: stored on the model, surfaced in Django admin and on the
existing rig API, with no dedicated frontend UI.

## Scope

### In scope

- A new `world_to_pixel()` helper in `blender_autorig.py` (inverse of the
  existing `pixel_to_world_ray()`).
- A new sidecar `landmark_pixels.json` written by the Blender script: the final
  placed landmarks projected to pixel coordinates for all four views.
- A new `apps/rigging/debug_photo.py` module that composites the annotated 2×2
  image with Pillow.
- A new `landmark_debug_image` `ImageField` on `RiggedModel` plus migration.
- API exposure via a `landmark_debug_image_url` field on `RiggedModelSerializer`
  and admin exposure on the `RiggedModel` admin.
- Tests for the projection helper, the photo builder, and the pipeline wiring.

### Out of scope

- Any frontend UI (editor panel, upload-page preview). The photo is debug/audit
  only — accessed via the API field or Django admin.
- Generating the photo on the geometry-only path or on editor landmark-rerigs.
  The photo is produced **only** on the `llm_vision` path, where the AI actually
  produced landmarks. Geometry-only and `user_landmarks` runs get no photo.
- Mesh-object classification overlays. Only the 14 landmarks are drawn.
- Any change to the Claude API call itself. This feature adds **zero** extra
  model calls or tokens — it only draws on images and coordinates that already
  exist.

## Decisions (from brainstorming)

| Question | Decision |
|---|---|
| Where does the user see it? | Debug/audit only — API field + Django admin, no frontend UI. |
| How are the four views covered? | One 2×2 composite image (single file). |
| What do the markers show? | Both the AI's raw picks **and** the final landmarks the rig used. |
| When is it generated? | Only when the Claude vision provider produced landmarks (`llm_vision` path). |
| Where is the projection done? | In the Blender script (where camera params + world coords live); Django only draws and stores. |

## Architecture

### Data flow

```
Phase 1 (existing)
  render_ortho_views()        → 4 PNGs in tmp/ortho/  +  ai_request.json
  ClaudeProvider.detect()     → ai_response.json
                                {landmarks: {view: {key: [px,py] | null}}}

Phase 2 (rig run — NEW additions)
  blender_autorig.py places bones from landmarks, then:
    world_to_pixel() projects the final placed landmarks → tmp/landmark_pixels.json
    (triggered by --landmark-pixels-out; also passed to the geometry-fallback run)

Post-Blender (NEW)
  debug_photo.build_landmark_debug_photo(
      ortho_dir, ai_picks, final_pixels) → composite.png
  rig.landmark_debug_image.save(...)
```

All three inputs — the four ortho PNGs, `ai_response.json`, and
`landmark_pixels.json` — already sit in the task's `TemporaryDirectory` at the
moment the photo is drawn. No extra rendering and no extra Blender subprocess
are needed.

### Component 1 — `world_to_pixel()` in `blender_autorig.py`

A new pure function: the algebraic inverse of the existing `pixel_to_world_ray()`,
sharing its per-view camera convention.

- **Signature:** `world_to_pixel(view_name, world_point, image_size, ortho_scale, world_aabb) -> [px, py] | None`.
- Returns `None` when the projected point falls outside the `[0, image_size)`
  frame, so off-frame markers are simply omitted rather than clamped.
- Derivation: `pixel_to_world_ray()` maps a pixel to a world ray via
  `u = (px/image_size - 0.5) * ortho_scale` and
  `v = (0.5 - py/image_size) * ortho_scale`, then composes `(u, v)` into world
  coords per view. `world_to_pixel()` inverts this — recover `(u, v)` from the
  world point for that view, then `px = (u/ortho_scale + 0.5) * image_size` and
  `py = (0.5 - v/ortho_scale) * image_size`.

When the script is given `--landmark-pixels-out <path>`, after bones are placed
it writes `landmark_pixels.json` — `{view: {key: [px,py] | null}}` for the 14
final placed landmarks across all four views. The Phase-1 per-view
`ortho_scale` / `image_size` / `world_aabb` are read from the existing
`ai_request.json` (passed via a path flag) so the projection matches the
rendered PNGs exactly.

`--landmark-pixels-out` is passed to **both** the main Phase-2 rig command and
the geometry-fallback command, so the "final used" markers always reflect the
run that actually won (see Geometry-fallback note below).

### Component 2 — `apps/rigging/debug_photo.py` (new module)

One public function:

```python
build_landmark_debug_photo(ortho_dir, ai_picks, final_pixels, out_path) -> bool
```

- `ortho_dir` — directory holding the four `front/back/left/right` PNGs.
- `ai_picks` — `{view: {key: [px,py] | null}}` from `ai_response.json`.
- `final_pixels` — `{view: {key: [px,py] | null}}` from `landmark_pixels.json`.
- For each of the four views: open the 512×512 PNG, draw **AI picks** as hollow
  orange circles and **final-used** as filled green dots, each with a small key
  label; draw a thin connector line between the two when both exist for a key.
- Any landmark that is `null` for a view (occluded) is skipped for that view.
- Stitch the four annotated views into a 1024×1024 2×2 grid with view-name
  captions and a one-line legend.
- Pure Pillow. Returns `True` on success; on any missing/unreadable input or
  Pillow error it logs a warning and returns `False` — never raises.

### Data model & migration

One new field on `RiggedModel`:

```python
landmark_debug_image = models.ImageField(
    upload_to=rig_upload_path, blank=True,
    help_text="2×2 annotated render showing AI-detected vs final landmark "
              "positions. Populated only on the llm_vision path.",
)
```

Plus migration `0005_riggedmodel_landmark_debug_image` (the next free number —
`0004_riggedmodel_detection_method_and_more` already exists). The file is stored under
the existing `rigs/<user_id>/<rig_id>/` path. On rerig, Django storage suffixes
the new file on collision — consistent with how `rigged_glb` already behaves.

### Pipeline integration (`_run_rig_pipeline`)

After Phase 2 succeeds and **only when `ai_response_path is not None`**:

1. The Blender rig command (and the geometry-fallback command) are given
   `--landmark-pixels-out` and the path to `ai_request.json`.
2. After the GLB / bones / landmarks reads, call
   `build_landmark_debug_photo()` against the temp dir.
3. On success, `rig.landmark_debug_image.save(f"{rig.id}_landmarks.png",
   File(f), save=False)` before the final `rig.save()`.

This slots in next to the existing `bone_mapping` / `landmarks` reads, inside
the `with tempfile.TemporaryDirectory()` block while the source files still
exist.

### API & admin exposure

- `RiggedModelSerializer`: add a `landmark_debug_image_url`
  `SerializerMethodField`, mirroring `rigged_glb_url` — absolute URI when the
  request is in context, `None` when the field is empty. This rides on the
  already-public `GET /rigs/{id}/`. This is consistent with existing precedent:
  `rig_log` (raw Blender stdout) is already exposed on that public serializer,
  so a debug image is no more sensitive.
- `admin.py`: add `landmark_debug_image` to the `RiggedModel` admin so it is
  clickable when diagnosing a bad rig.

## Geometry-fallback note

When AI landmarks fail the sanity check, the pipeline re-runs geometry-only and
that run's output wins. The debug photo is *most* useful in exactly this case —
it shows the AI's rejected picks against the geometry result. Therefore
`--landmark-pixels-out` is passed to the geometry-fallback command as well, and
the "final used" markers reflect whichever run produced the landmarks the rig
ultimately used. The "AI picks" layer still comes from `ai_response.json`
regardless.

## Error handling

The photo is **strictly best-effort** — it must never fail or slow down a rig.

- Missing or unreadable PNGs, missing sidecars, or a Pillow error →
  `build_landmark_debug_photo()` logs a warning and returns `False`; the
  `landmark_debug_image` field stays blank; the rig still completes `done`.
- `world_to_pixel()` returning `None` for an off-frame point → that single
  marker is omitted from the drawing.
- The entire photo block in `_run_rig_pipeline` is wrapped so any exception is
  caught and logged, never propagated to the rig result.

## Testing

- **`world_to_pixel()`** — a standalone test mirroring
  `_test_pixel_to_world.py` (stubbed `bpy` / `mathutils`, no Blender runtime).
  Assert it round-trips against `pixel_to_world_ray()` for known points across
  all four views, and returns `None` for off-frame points.
- **`debug_photo.py`** — a Django test with synthetic 512×512 PNGs and fake
  pick / pixel dicts. Assert the output file exists and is 1024×1024, that
  `null` landmarks are skipped, and that missing-input cases return `False`
  without raising.
- **Pipeline** — extend the existing `apps.rigging` tests to assert
  `landmark_debug_image` is populated on a mocked `llm_vision` run and stays
  blank on a geometry-only run.

## Files touched

| File | Change |
|---|---|
| `backend/scripts/blender_autorig.py` | Add `world_to_pixel()`; add `--landmark-pixels-out` flag; write `landmark_pixels.json`. |
| `backend/apps/rigging/debug_photo.py` | New module — `build_landmark_debug_photo()`. |
| `backend/apps/rigging/models.py` | Add `landmark_debug_image` field. |
| `backend/apps/rigging/migrations/0005_*.py` | New migration. |
| `backend/apps/rigging/tasks.py` | Pass new flags; call the photo builder; save the field. |
| `backend/apps/rigging/serializers.py` | Add `landmark_debug_image_url`. |
| `backend/apps/rigging/admin.py` | Expose `landmark_debug_image`. |
| `backend/scripts/_test_world_to_pixel.py` | New standalone projection test. |
| `backend/apps/rigging/tests/` | New / extended tests for the builder and pipeline. |
