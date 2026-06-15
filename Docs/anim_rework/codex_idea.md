# RigFlow Animation Rework: Codex Hypothesis

**Author:** Codex
**Date:** June 16, 2026
**Scope:** Character animation retargeting, preview, and animated export. This is not a proposal for landing-page or UI motion.

## Core Hypothesis

The best animation rework is to make **server-side baked animation export the product source of truth**, while keeping the browser player as a fast preview layer that is gradually forced to use the same data and decisions as the backend.

Right now the user-facing value breaks at the exact point that matters most: a character can preview an animation in the browser, but the downloadable rig is not guaranteed to contain that animation. The current frontend has a useful retargeting path in `AnimationPlayer.tsx`, but it is still a preview-only path. Meanwhile, the API client already has functions shaped like the future system, especially `retargetAnimation()` and `exportProject()`, but the backend does not yet provide the corresponding production export flow.

So the rework should not start with more visual polish in three.js. It should start with the export spine:

1. Select a rig and one or more animation clips.
2. Run Blender headless on the backend.
3. Retarget against the generated rig bone map.
4. Bake keyframes into the armature.
5. Export a GLB with animations enabled.
6. Return a download URL and a retarget report.

The browser preview remains important, but it should be treated as a convenience layer. The final answer that users take to Unity, Unreal, Godot, or Blender must come from the backend baker.

## What The Current Code Suggests

The current repo points to three important facts:

1. **The frontend already has serious preview work.**
   `AnimationPlayer.tsx` does more than naive track renaming. It attempts `SkeletonUtils.retargetClip`, builds source-to-target bone names, sanitizes bone names for three.js binding, and reports how many tracks actually bind. That is useful and should not be thrown away.

2. **The current preview intentionally drops position and scale tracks.**
   This prevents root translation from launching the rig across the scene, but it also means walks, runs, jumps, and locomotion clips become in-place animations. Root motion needs a deliberate design, not a blanket track filter.

3. **The backend is missing the production animation contract.**
   `frontend/src/lib/api.ts` exposes `retargetAnimation()` and `exportProject()`, but `backend/apps/animations/views.py` only handles list/upload/category, and `backend/apps/projects/views.py` is still a stub. That means the UI-facing contract is partly designed, but not implemented.

## Best Ideas To Keep

### 1. Build The Blender Baker First

The highest leverage work is a backend bake/export path. The baker should:

- Load the rigged model file.
- Load the selected animation file.
- Resolve animation source bones to Rigify/DEF bones using the rig's saved `bone_mapping`.
- Apply retarget constraints or equivalent pose transfer in Blender.
- Bake the result to keyframes with `bpy.ops.nla.bake`.
- Export GLB with animations enabled.
- Return a report containing mapped bones, unmapped bones, dropped tracks, frame range, FPS, and output URL.

This gives users an actual animated asset, not just a browser demonstration.

### 2. Make One Bone Map The Contract

The repo currently has multiple mapping surfaces: frontend fallback maps, backend Rigify/Mixamo assumptions, and the saved `bone_mapping` on the rig. The rework should make the saved rig `bone_mapping` the runtime contract.

Hardcoded maps can still exist as generation seeds and legacy fallbacks, but they should not be the primary truth during preview or export. The same rig should produce the same mapping decisions in both places.

Practical rule: if the backend bake and the browser preview disagree about a bone name, that is a bug.

### 3. Keep Browser Preview, But Stop Letting It Drift

The browser preview is valuable because it is instant. Keep it, but keep it bounded:

- Use the rig's saved `bone_mapping` first.
- Keep the track binding report visible.
- Preserve the existing three.js sanitization logic.
- Avoid adding a separate "smarter" client retargeter that the backend cannot match.

Longer term, the cleanest preview is a cached server-baked clip that the viewer plays back directly. That makes preview and export converge instead of becoming two permanent retargeting systems.

### 4. Add Root Motion After Export Works

Root motion is real work, but it should come after the bake/export spine. The right first version is:

- Keep rotation tracks for mapped bones.
- Keep only the root/hips translation track, not arbitrary position tracks.
- Scale root translation by leg length ratio, not whole-character height.
- Apply the same rule in preview and Blender export.
- Report whether root motion was kept, scaled, or disabled.

Scaling by total bounding-box height will fail on stylized characters with large heads, long torsos, wings, hats, or props. Leg length is a better proxy for stride.

### 5. Ship GLB First

GLB should be the first production target. FBX can follow, but it has more export settings, axis conversion issues, unit quirks, and engine-specific differences. A reliable animated GLB is a better first milestone than two unreliable formats.

## Ideas To Deprioritize

### Heavy Skinning Rewrites

A voxel/geodesic skinning fallback sounds attractive, but it is not the main animation problem. The animation rework should not become a skinning research project unless current deformation failures are proven to dominate user outcomes after animated export works.

### Large Client-Side Retargeting Overhaul

The existing client preview is already doing useful world-space retargeting through `SkeletonUtils.retargetClip`. Rewriting the browser path first risks spending time on a preview that still cannot be exported.

### Permanent Dual Retargeting Engines

A dual-layer architecture is useful only if the layers share the same contract and are actively converging. If client and server each grow their own bone maps, rest-pose offsets, root-motion logic, and fallbacks, preview/export mismatch becomes guaranteed.

## Errors And Risks We Might Face

| Risk | Why It Matters | Mitigation |
| --- | --- | --- |
| Preview/export mismatch | The browser may look correct while the downloaded GLB is wrong. This is the worst product failure because it breaks trust. | Use one saved bone map, add parity tests, and eventually preview server-baked clips. |
| Bone-name sanitization bugs | three.js strips or interprets characters like dots in names, so tracks can silently fail to bind. | Keep `sanitizeBoneName()` behavior as an explicit compatibility rule and test exported track names in a real GLTFLoader path. |
| Missing backend endpoints | The frontend already calls future-looking retarget/export APIs, but the backend does not implement them yet. | Implement the project export route first, then decide whether animation retarget is separate or just part of export. |
| Blender bake latency | Headless Blender jobs can take seconds or minutes and may block workers under load. | Run through Celery, emit progress events, enforce timeouts, and cache by rig hash + animation id + options. |
| Rest-pose and bone-roll mismatch | Rigify DEF bones, Mixamo bones, and custom uploads may not share local axes or rest poses. | Store rest-pose offsets or calibration metadata during rig build and consume it in the baker. Keep fallback reports visible. |
| Finger and hand mapping gaps | Hands are visually obvious, and server maps often lag behind frontend maps. | Generate finger mappings into the canonical bone map and include hands in test fixtures. |
| Root-motion foot sliding | Even correctly preserved translation can look wrong when body proportions differ. | Use leg-length scaling first. Treat IK foot locking as a later feature, not v1. |
| Unit and axis mismatches | FBX, GLB, Blender, and three.js can disagree on meters/centimeters and up-axis. | Normalize in Blender, write metadata into the export report, and make GLB the first supported export target. |
| Animation files with no usable skeleton | Uploaded clips may contain unexpected names, props, constraints, or no armature animation. | Validate uploads, show a retarget report, and fail with a useful message instead of producing a silent static export. |
| Large clips and memory usage | Long clips can produce huge baked keyframe data and slow downloads. | Cap duration/frame rate in v1, resample to a standard FPS, and expose duration/FPS in the report. |

## Proposed Sequence

1. **Implement animated GLB export.**
   Add `POST /projects/{id}/export/` or a rig-scoped equivalent that accepts animation IDs and returns a task or download URL. Use Celery and the existing Blender subprocess pattern.

2. **Create a Blender bake script path.**
   Extend or companion `blender_autorig.py` with an animation-bake mode rather than mixing too much export logic into Django views.

3. **Use the rig bone map everywhere.**
   Make backend bake and frontend preview consume the same saved mapping. Keep fallback maps only for old rigs and report when fallbacks were used.

4. **Add a retarget report.**
   Every bake should say what happened: mapped bones, missing bones, dropped tracks, root-motion status, duration, FPS, and output format.

5. **Add root motion.**
   Preserve and scale only root/hips translation. Use leg-length ratio and apply the same math in both preview and export.

6. **Add parity tests.**
   Use one known rig and one known clip. Assert that preview mapping and backend mapping produce the same target bone names, and that exported GLB contains at least one animation with expected track bindings.

7. **Add FBX after GLB is stable.**
   Treat FBX as a separate compatibility milestone with its own fixtures and engine import checks.

## Recommendation

Start with the backend animated GLB export and the canonical bone-map contract. That path turns animation from a temporary browser preview into an actual RigFlow deliverable. Once that is solid, root motion and preview polish become much safer because there is a production path to compare against.

