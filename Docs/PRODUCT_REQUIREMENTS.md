# RigFlow Product Requirements

## Overview
RigFlow helps game developers and 3D artists turn character models into animation-ready assets through a guided web workflow. The platform combines a Next.js/Three.js frontend with a Django/Celery backend that runs Blender Rigify automation.

## Users
- Indie and AA game developers.
- Small animation or game art teams.
- Hobbyist 3D creators who need a simpler rigging path.

## Primary Workflow
1. Upload a character model in FBX, GLB, GLTF, or OBJ format.
2. Run the Blender/Rigify auto-rigging pipeline.
3. Track processing status in the editor.
4. Review the rigged GLB output.
5. Adjust landmarks if the automatic result needs correction.
6. Preview uploaded or library animations.
7. Export or download the finished asset.

## Required Capabilities

### Model Upload & Auto-Rigging
- Validate supported model formats before upload.
- Create a rigging job with status, progress, and error reporting.
- Detect pose/rotation where possible.
- Return a rigged GLB when processing completes.

### Rig Editing
- Render models in a browser-based 3D viewer.
- Let users place or update landmark control points.
- Preserve the last successful rig while a rerig is processing.
- Show enough skeleton/model feedback to verify alignment.

### Animation Management
- Accept GLB, GLTF, and FBX animation uploads.
- Provide a browsable animation library.
- Preview or retarget animations against a rigged model.
- Report track-binding issues clearly when an animation does not match the rig.

## Success Criteria
- Standard bipedal uploads complete the rigging workflow reliably.
- Users can recover from imperfect auto-rigging through landmark edits.
- Rigged outputs and animations load without blocking the editor UI.
- Unsupported formats and processing failures produce actionable messages.

For implementation details, keep this file aligned with `rigflow-project/Docs/RIGFLOW_PRD.md` and `rigflow-project/Docs/TECHNICAL_CONTEXT.md`.
