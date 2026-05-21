# RigFlow Product Requirements (Summary)

A short product brief. For the full PRD with non-functional requirements, MVP scope, and acceptance criteria, see [RIGFLOW_PRD](RIGFLOW_PRD.md).

## Overview

RigFlow turns a 3D character mesh into an animation-ready rig through a guided web workflow. The user uploads a model, the platform runs Blender's Rigify automation against it, and the user gets back a rigged GLB they can preview, correct via landmark editing, and animate from a built-in library.

The frontend is Next.js + Three.js. The backend is Django + DRF + Celery, with Blender invoked headlessly as a subprocess. See [ARCHITECTURE](ARCHITECTURE.md) for the system view.

## Users

- **Indie and AA game developers** who need faster character setup than full manual rigging.
- **Small animation and game-art teams** preparing bipedal characters in volume.
- **Hobbyist 3D creators** who want a guided rigging path without learning Blender's rigging UI.

These users are technical enough to handle FBX/GLB pipelines but not necessarily Rigify-fluent.

## Primary workflow

1. Sign in.
2. Upload a character model (`fbx`, `glb`, `gltf`, or `obj`).
3. Watch processing progress in the editor.
4. Review the auto-rigged GLB output and the detected pose classification.
5. If the auto-rig is wrong, place 6 landmarks (chin, wrists, groin, ankles) and re-run.
6. Preview animations from the library — or upload a custom one — against the rig.
7. Download or export the finished asset.

## Capabilities required for the workflow

### Model upload & auto-rigging
- Validate format before upload (`fbx`, `glb`, `gltf`, `obj`).
- Detect and report the model's pose (T-pose, A-pose, arms-down, unclear).
- Run Blender / Rigify automation, with optional initial-rotation and quaternion overrides.
- Surface job status: `pending` → `processing` → `done` / `failed`, with progress percentage and a step label.
- Produce a downloadable rigged GLB.

### Rig review & landmark correction
- Render the rigged model in a browser-based 3D viewer.
- Let the user place or update 6 named landmarks (chin, left/right wrist, groin, left/right ankle).
- Re-run the rigging pipeline with those landmarks without losing the previous valid output (rerig is non-destructive — see [RIGGING_PIPELINE § Why rerigs preserve the old GLB](RIGGING_PIPELINE.md#why-rerigs-preserve-the-old-glb)).
- Show enough skeleton/model feedback for the user to verify alignment.

### Animation library
- Browse a public, moderated animation library plus the user's own uploads.
- Upload custom animations (`glb`, `gltf`, `fbx`).
- Retarget or preview an animation against a rigged model.
- Report unbound tracks clearly when an animation's bone names don't match the rig's `bone_mapping`.

## Success criteria

- A standard bipedal mesh (T- or A-pose, single mesh, Z-up or convertible) completes the upload → auto-rig → review path **without manual intervention**.
- When auto-rigging is imperfect, the user can recover entirely through landmark editing — no need to leave the app.
- Rigged outputs and animations load in the browser viewer without blocking the editor UI.
- Unsupported formats and processing failures produce **actionable** error messages, not stack traces.

## Out of scope (for now)

- Quadrupeds, multi-character meshes, modular outfits.
- Non-Rigify rigging templates.
- Real-time multi-user editing or collaborative review.
- Stripe checkout (plans exist as labels only — see [KNOWN_ISSUES § Stripe / payments are stubs](KNOWN_ISSUES.md#stripe--payments-are-stubs)).

---

This file is meant to stay short. Keep it aligned with [RIGFLOW_PRD](RIGFLOW_PRD.md) and [TECHNICAL_CONTEXT](TECHNICAL_CONTEXT.md). When scope changes, update the PRD first; this summary should reflect it.
