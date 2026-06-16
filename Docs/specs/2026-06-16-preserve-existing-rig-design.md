# Preserve Existing Rig on Upload — Design

**Status:** approved 2026-06-16
**Drives:** stop destroying good skeletons on already-rigged uploads

---

## 1. Problem

Today the pipeline calls `strip_non_meshes()` immediately after import, which **deletes the uploaded model's armature** and keeps only raw geometry; a fresh Rigify rig is then built from scratch (`backend/scripts/blender_autorig.py:214`). For models that arrive **already rigged** (e.g. marketplace/Mixamo GLBs and FBXs with a working skeleton), this throws away a good rig and replaces it with a weaker auto-rig — the observed failure mode includes `Pose: unclear`, AABB-default landmark placement, and heat-weighting that falls back on ~120K vertices, producing poor deformation.

**Goal:** if an uploaded model already has a skeleton that deforms the mesh, **keep that skeleton** and skip Rigify; otherwise the existing auto-rig path runs unchanged.

## 2. Decisions (from brainstorming)

| Question | Decision |
|---|---|
| Trigger | **Auto-detect** — no user toggle. |
| Which skeletons | **Any armature that skins the mesh** (naming-agnostic), provided it deforms the *largest* mesh. |
| Animations | **Best-effort bone map** built from the existing bone names so library animations still retarget. |
| Processing | **Normalize + clean export** — keep the skeleton, but still apply upload rotation, normalize scale/orientation, and export a clean GLB. |
| Prop-only rig | If only a prop (not the main mesh) is skinned, **auto-rig the body** as normal. |
| Landmark editor | **Hidden** for preserved-rig models (no Rigify metarig to fit). |

## 3. Architecture

```
import_model
   ↓
find_skinning_armature(meshes)
   ├── found (skins largest mesh, ≥2 bones)  → KEEP-RIG branch
   │      apply upload rotation (armature+mesh together)
   │      normalize scale/position (≈2 units, feet Z=0, XY-centered), apply transforms
   │      build_bone_map_from_existing(armature)   → {Mixamo: existingBone}
   │      export GLB with original skeleton + skinned mesh
   │      used_existing_rig = True, detection_method = "preserved"
   │
   └── not found → existing AUTO-RIG path (unchanged):
          strip_non_meshes → metarig → landmarks → generate_rig → bind → export
```

The keep-rig branch is **skeleton-agnostic** and self-contained: it never builds a metarig, detects pose, or runs `ARMATURE_AUTO` (the mesh is already skinned).

## 4. Components

### 4.1 `find_skinning_armature(meshes)` — new, `blender_autorig.py`
Returns the armature that actually skins the model, or `None`.

- Candidate armatures: all `bpy.data.objects` of type `ARMATURE` with **≥2 bones**.
- A mesh is "skinned by" an armature when it has an `ARMATURE` modifier whose `object` is that armature **and** the mesh has ≥1 vertex group whose name matches a bone in that armature.
- Identify the **largest mesh** by vertex count among `get_meshes()`. Return the armature that skins that largest mesh. If the largest mesh isn't skinned by any armature → return `None` (prop-only or unrigged → auto-rig).
- If multiple armatures skin the largest mesh (rare), pick the one contributing the most matching vertex groups.

### 4.2 `normalize_existing_rig(armature, meshes)` — new
Brings a kept rig into the app's canonical frame without disturbing skinning.

- Apply the upload rotation (the existing `apply_user_rotation` path) to the armature+mesh hierarchy.
- Compute the **mesh** AABB (the largest skinned mesh, to avoid props inflating scale), uniform-scale the whole hierarchy so its Z height ≈ `THREE_DISPLAY_HEIGHT` (2.0), translate so min-Z = 0 and XY centered.
- Apply object transforms so exported bone/vertex data is baked; verify the Armature modifier binding survives (re-bind only if Blender drops it).

### 4.3 `build_bone_map_from_existing(armature)` — new
Produces `bone_mapping = {MixamoName: existingBoneName}` (the shape the animation retargeter and `AnimationPlayer` already consume).

- For each bone, resolve a **canonical Mixamo name** via name heuristics: strip namespaces (`mixamorig:`, `Armature|`), normalize case/separators, match common conventions (hips/pelvis/root → `Hips`; spine segments; L/R clavicle/arm/forearm/hand; up-leg/leg/foot/toe; fingers). Mirrors the matching family in `frontend/src/lib/boneMap.ts` (kept in spirit, not a literal port).
- Collisions (two bones → one Mixamo name) keep the first; ambiguous/unmatched bones are skipped.
- Log mapped vs unmapped counts; unmapped bones simply receive no retargeted tracks.

### 4.4 `main()` branch
After `import_model` (and before `strip_non_meshes`), call `find_skinning_armature`. If non-`None`, run the keep-rig branch and return after export; otherwise continue the current flow untouched.

## 5. Backend plumbing

### 5.1 Model
- New field `RiggedModel.used_existing_rig = models.BooleanField(default=False, db_index=True)` (+ migration).
- `detection_method` gains a `"preserved"` choice ("Original rig preserved").
- On the keep-rig path: `used_existing_rig=True`, `detection_method="preserved"`, `detected_pose="unclear"`, `landmarks=None`.

### 5.2 `tasks.py` — skip the AI phase for rigged uploads
- Phase 1 (`--render-ortho-views`) also runs `find_skinning_armature`; if it finds one it writes `"already_rigged": true` into `ai_request.json` and skips the ortho render work it doesn't need.
- `tasks.py` reads `already_rigged`; if true it **skips the Claude vision call entirely** (no wasted ~$0.006, no landmark seeds) and proceeds to Phase 2, which takes the keep-rig branch.
- Phase 2 reads `bone_mapping`, sets `used_existing_rig=True`, `detection_method="preserved"`; the debug-photo step is skipped (not `llm_vision`).

### 5.3 Serializer
- Expose `used_existing_rig` on `RiggedModelSerializer` (and in the `/status/` payload) so the frontend can branch.

## 6. Frontend (small)

- `RiggedModel` type gains `used_existing_rig?: boolean`.
- Editor: when `used_existing_rig` is true, show an **"Original rig preserved"** badge and **hide** the landmark-editing / re-rig-landmarks controls (they fit a Rigify metarig that doesn't exist for these models). Animation preview and download work normally.

## 7. Edge cases

| Case | Behaviour |
|---|---|
| Multiple armatures | Pick the one skinning the largest mesh (most matching vertex groups wins ties). |
| Armature present but no vertex groups / not bound | Treated as unrigged → auto-rig. |
| Prop-only rig (main mesh unskinned) | Auto-rig the body as normal. |
| Already-Mixamo-named skeleton | Heuristic resolves trivially → near-complete `bone_mapping`. |
| Exotic/non-standard bone names | Best-effort; unmapped bones reported; rig still preserved + exported. |
| Existing rig fails to export / normalize | Fall back to the auto-rig path so the upload still produces *a* rig (logged). |

## 8. Out of scope

- Improving the bone-map heuristic beyond name matching (no geometry-based bone classification).
- Guaranteeing animation binding for non-standard skeletons (best-effort + reported).
- Making the landmark editor / `rerig-landmarks` work on preserved rigs.
- Re-targeting or cleaning the preserved skeleton's hierarchy (we export it as-is, only normalized in scale/orientation).

## 9. Testing

- **Standalone (no Blender):** unit-test the canonical-name resolver used by `build_bone_map_from_existing` — `mixamorig:LeftArm → LeftArm`, `Hips/pelvis/root → Hips`, spine/limb/finger conventions, and `None` for unmappable control bones.
- **Blender-gated e2e:** upload a known rigged GLB (e.g. one of the marketplace models on disk) → assert `used_existing_rig=True`, exported skeleton bone count equals the source's, `bone_mapping` non-empty, status `done`. Upload an unrigged mesh → assert the auto-rig path still runs (`used_existing_rig=False`).
- **Guard:** a model with only a prop rigged → `used_existing_rig=False`.

## 10. Cross-references

- [`RIGGING_PIPELINE.md`](../RIGGING_PIPELINE.md) — current import → strip → Rigify flow this branches around.
- [`2026-06-16-animation-rework-design.md`](2026-06-16-animation-rework-design.md) — the `bone_mapping` contract preserved rigs feed into.
- `backend/scripts/blender_autorig.py` — `strip_non_meshes` (214), `import_model` (152), `main` (2123).
