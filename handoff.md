# RigFlow auto-rig redesign — handoff

Continuation doc for picking this conversation up in a fresh Claude Code session.

## TL;DR

- An auto-rig regression was found and patched today. Bones-past-hands symptom on a Freddy Fazbear upload, root cause was buggy T-pose slice detection placing the groin above the chin. **Patch is uncommitted.**
- We then designed (but did NOT yet implement) a new auto-rig architecture: **geometry + Claude Haiku 4.5 vision in a duo**, every rig pays one AI call (~$0.004), AI provides semantic seeds and geometry refines them to real mesh vertices.
- **Next step:** write the formal spec → user reviews → writing-plans skill makes an implementation plan → build.
- User is 14, will buy `ANTHROPIC_API_KEY` (Claude Haiku 4.5) soon. Code must run geometry-only when the key is missing so they can develop in parallel.

## Repo orientation (read first — easy to get wrong)

- **Git root is INNER:** `rigflow-project/rigflow-project/` — branch `Feature/test`, up to date with `origin/Feature/test`. Source lives alongside this `.git`.
- Outer `rigflow-project/.git` is **corrupted** (packfile mismatch, unreachable HEAD, 57 leftover `tmp_pack_*` files). Do not run `git` from the outer folder.
- All commands and paths below are relative to the inner folder.

## Uncommitted changes already on disk (do not lose these)

1. **`backend/scripts/blender_autorig.py`** — 1373 → 1296 lines. Removed the buggy T-pose slice-based chin/groin/shoulder/hip detection (added in commit 38c0eba9). The "highest slice with 2+ X-clusters" loop fires on arm-induced clusters at shoulder height in T-pose, placing the pelvis above the chin and inverting the rig. Reverted to AABB defaults via `_promote_legacy_landmarks`; wrist + ankle vertex-extremity detection kept. The stale "AABB defaults … hasn't been wired up for yet" comment is also cleaned up. Smoke test still passes: `python backend/scripts/_test_landmark_promotion.py`.

2. **Three previously-empty admin files now register their models** (the user noticed `/admin` only showed Celery + auth):
   - `backend/apps/rigging/admin.py` — `RiggedModel` with list_display, list_filter, search_fields.
   - `backend/apps/users/admin.py` — `User` (via DjangoUserAdmin), `UserProfile`.
   - `backend/apps/animations/admin.py` — `Animation`, `AnimationCategory`.

3. **Six docs in `Docs/` brought current with the code:**
   - `RIGGING_PIPELINE.md` — 14-landmark schema, corrected pose bands (atan2 from horizontal: 0–25° = T-pose), full CLI flag list, common-output-problems table refreshed with the wrist-on-paw-tip and reference_height pitfalls.
   - `API.md` — `/rerig-landmarks/` body 14 keys (was 6), new `GET /rigs/{id}/landmarks/` endpoint.
   - `ARCHITECTURE.md` — `landmarks` JSON field added to the RiggedModel schema.
   - `KNOWN_ISSUES.md` — outer-git corruption section rewritten, new "14-key schema, reference_height regression" entry.
   - `TECHNICAL_CONTEXT.md` — removed stale SSH-private-key warning + "passthrough fallback" wording.
   - `DEVELOPMENT.md` — Blender prereq description + troubleshooting table updated.

4. **`/home/dev/projects/rigflow-project/CLAUDE.md`** (outer folder, agent instructions) — clarified inner vs outer `.git`, 14-landmark schema bullet, refreshed pipeline summary. NOT tracked by the inner working git, so it won't show in `git status`.

5. Frontend changes (`.tsx` JSX-string escapes, apostrophe entities in landing components) — these were already uncommitted before this session, unrelated to rigging, left as-is.

## Auto-rig redesign — agreed design

**Goal:** auto-rig is the final state. The user uploads, gets a rig that animations bind to cleanly, never needs to touch the editor for ordinary models. Editor remains as escape hatch.

**Pose range supported:** anywhere between A-pose and T-pose. Arms-down out of scope for now.

**Architecture: geometry + AI duo, every rig.**

```
upload → Blender subprocess
   ↓
   render 4 orthographic views (front -Y / back +Y / left -X / right +X, 512×512 PNG)
   ↓
   Blender writes request JSON (paths to PNGs + per-mesh-object metadata)
   ↓
   tasks.py picks it up, calls Claude Haiku 4.5 vision via the anthropic SDK
   ↓ AI returns: 14 joint pixel coords per view + per-mesh-object label (body/hat/accessory_held/clothing)
   tasks.py writes response JSON → Blender re-reads it
   ↓
   raycast AI's pixel coords back to 3D world-space via orthographic camera   = SEEDS
   ↓
   geometry refines each seed to the nearest anatomically-meaningful mesh feature
   (wrist seed → walk to arm narrowing; ankle seed → snap to bottom-cluster centroid; etc.)
   ↓
   sanity checks (groin.y < chin.y, symmetry, mesh bounds, anatomical order)
   ↓
   place_bones_from_landmarks → Rigify generate → strip-to-DEF → export
```

**Why duo and not fallback:** AI alone is approximate (4-pixel jitter typical, mis-snaps left/right occasionally). Geometry alone can't tell a wrist from a paw tip. Together: AI gives "wrist is in this region"; geometry finds the actual joint inside that region.

**Props are part of the same AI call.** The model labels each separate `bpy.data.objects` mesh as body / hat / accessory_held / clothing. Non-body meshes are excluded from landmark detection and parented to the right deform bone (hat → head, microphone → matching hand) automatically.

**Provider abstraction:** behind env var `LANDMARK_VISION_PROVIDER=claude` (default) | `gemini` | `none`. `none` means geometry-only — current behavior. Lets the user develop and test the whole pipeline without an API key.

**`needs_landmarks` status: DROPPED** (we discussed and dropped it). Every successful pipeline finishes as `done`. Editor is always available.

**Cost target for Claude Haiku 4.5:** ~5K input tokens (4 images + prompt) + ~600 output tokens (14 coords × 4 views + prop labels) ≈ **$0.004/rig** → $1 buys ≈250 rigs.

## Files the implementation will touch

**New:**
- `Docs/specs/2026-05-12-auto-rig-perfect.md` — formal spec.
- `backend/apps/rigging/landmark_vision.py` — provider abstraction, Anthropic call, prompt template, response parsing.
- New migration: `RiggedModel.detection_method` (`"geometry"` | `"llm_vision"` | `"user_landmarks"` | `"failed"`) for monitoring which path fired.

**Modified:**
- `backend/scripts/blender_autorig.py` — add ortho-render step, request-file writer, response-file reader, pixel-to-3D raycast, AI-seed-to-vertex refinement, sanity checks.
- `backend/apps/rigging/tasks.py` — pick up Blender's request file between the subprocess and the response read, call `landmark_vision.detect()`, write response, resume Blender.
- `backend/requirements.txt` — `anthropic`, `Pillow`.
- `Docs/BLENDER_AUTORIG.md` — relax the "No external deps" technical constraint by clarifying that the vision call happens on the **Django side**, not inside Blender's Python. Blender's deps stay clean; the round-trip is the integration point.

## Why the round-trip (Blender ↔ Django) instead of calling Anthropic from Blender directly

Blender ships its own Python (3.11). Installing `pip install anthropic` into Blender's Python is brittle across versions and OSes, and is one of the documented technical constraints in `Docs/BLENDER_AUTORIG.md`. Cleaner pattern: Blender writes a request file (PNG paths + metadata), pauses by exiting its subprocess; `tasks.py` reads the file, calls the SDK in Django's regular venv (which already has `anthropic`), writes a response file, then re-spawns Blender with `--landmarks-from-ai <path>`. One extra subprocess but no Python-env contamination.

Alternative (simpler code, riskier install): bundle `anthropic` into Blender's Python via `--target` install. Documented but not recommended.

## What the user is doing

- Signing up at **console.anthropic.com**, adding payment with **$5/month spending cap** recommended.
- Will paste the key into `backend/.env` as `ANTHROPIC_API_KEY=sk-ant-...`.
- The code should work without the key by defaulting `LANDMARK_VISION_PROVIDER=none` so the geometry side can be developed and tested in parallel.

## What the next Claude session should do

1. **Read** this handoff, `Docs/RIGGING_PIPELINE.md`, `Docs/BLENDER_AUTORIG.md`. Confirm uncommitted changes from "Uncommitted changes already on disk" are intact (run `git status` from the inner folder).
2. **Write the spec** at `Docs/specs/2026-05-12-auto-rig-perfect.md`. Cover everything under "Auto-rig redesign — agreed design" above plus:
   - The exact Claude vision prompt (with 14 landmark labels + the prop classification schema).
   - Request and response file formats for the round-trip (JSON schemas with examples).
   - Sanity-check definitions: groin.y < chin.y, |left - right| / max < 0.3, mesh-bounds tolerance.
   - Failure semantics: if AI returns malformed JSON → log + fall back to geometry-only path; if both fail sanity → still finish as `done`, leave landmarks at AABB defaults, surface "open editor to adjust" via existing UI.
3. **Pause for user review.** Don't start implementing until the user okays the spec.
4. **Then** invoke `superpowers:writing-plans` to produce an implementation plan with checkpoints. Likely milestones:
   - **M1.** A-pose support + sanity checks in pure geometry (no AI). Testable on Freddy + Johnny Joestar without any API key.
   - **M2.** Ortho-render step + request file writer.
   - **M3.** `tasks.py` round-trip + Anthropic provider behind the abstraction.
   - **M4.** 2D pixel → 3D raycast + seed-to-vertex refinement.
   - **M5.** `detection_method` migration + admin/UI surface.
5. Implement via `superpowers:subagent-driven-development` or `superpowers:executing-plans`.

## Things the next session needs to know

- **Test models on disk:**
  - `backend/media/rigs/1/0f855599-39df-487f-a827-accedd052d5d/johnny_joestar.fbx` — the documented integration test in `Docs/BLENDER_AUTORIG.md`. Should rig cleanly.
  - `backend/media/rigs/1/0355b5b9-1932-45f5-aa74-1475cd3b2b2e/` — Freddy uploads from today. Bones extend past hands because `_extreme_vertex` puts wrist at paw tip; this is the canonical test for the AI-seed + geometry-refine pipeline.
- **`CELERY_TASK_ALWAYS_EAGER=True`** locally → no Celery worker needed → `django_celery_results.TaskResult` admin table stays empty (WAI).
- **`MEDIA_ROOT`:** `ARCHITECTURE.md` says `backend/../media/`. Filesystem says `backend/media/`. Worth verifying which is actually configured in `settings/base.py` before the implementation reads paths.
- **Pipeline runs synchronously in dev** because of `CELERY_TASK_ALWAYS_EAGER`. The Blender ↔ Django round-trip will need to handle both eager (in-thread) and worker (Celery) modes.
- **No real test suite yet.** The implementation plan should add tests for: request/response JSON schemas, projection math (orthographic pixel → world ray), prop-label parsing, sanity-check definitions, geometry-only mode.
- **`_extreme_vertex` is still the wrist algorithm** in the current geometry code. After the new design, the AI seed will replace it as the primary signal; `_extreme_vertex` becomes a refinement helper or is removed.

## Starting prompt to paste into the new session

> Pick up the RigFlow auto-rig redesign. Read `handoff.md` at the inner project root, then `Docs/RIGGING_PIPELINE.md` and `Docs/BLENDER_AUTORIG.md`. Confirm the uncommitted changes are intact via `git status` from the inner folder. Then write the formal spec at `Docs/specs/2026-05-12-auto-rig-perfect.md` per section "What the next Claude session should do" in the handoff. Pause for me to review before implementing.
