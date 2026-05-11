# `backend/scripts/blender_autorig.py`

This document describes the Blender auto-rig script as tested on 2026-05-10.

## Verification & Testing

The script is verified through both standalone unit tests and end-to-end Blender integration tests.

### Standalone Unit Test
A dedicated smoke test verifies the landmark promotion logic without requiring a Blender installation:
```bash
python backend/scripts/_test_landmark_promotion.py
```
**Result**: Passed. This test uses a stubbed `mathutils` and `bpy` to verify that the 6-to-14 landmark adapter produces anatomically correct positions.

### Blender Integration Test
The full pipeline can be tested headlessly using a sample model:
```bash
tmpdir=$(mktemp -d /tmp/rigflow-autorig-test.XXXXXX)
blender --background --python backend/scripts/blender_autorig.py -- \
  --input backend/media/rigs/1/0f855599-39df-487f-a827-accedd052d5d/johnny_joestar.fbx \
  --output "$tmpdir/rigged.glb" \
  --bones "$tmpdir/bones.json" \
  --pose "$tmpdir/pose.json" \
  --landmarks-out "$tmpdir/landmarks.json" \
  --format fbx
```
**Result**: Exited `0`.
- **Classification**: Identified as `t_pose` (angle: ~5.7°, confidence: 0.77).
- **Landmarks**: 14 landmarks detected and written.
- **Bone Map**: 22 Mixamo-to-Rigify mappings generated.
- **Output**: 305 KB GLB produced successfully.

### Django App Tests
Basic rigging application logic is covered by:
```bash
python backend/manage.py test apps.rigging
```
**Result**: 5 tests passed.

---

## Purpose & Scope

`backend/scripts/blender_autorig.py` is the core automation engine for RigFlow. It runs as a headless Blender subprocess to transform raw 3D geometry into an animated character.

### Key Responsibilities:
1.  **Normalization**: Standardizes orientation (Z-up) and scale.
2.  **Anatomical Detection**: Classifies pose and identifies 14 key anatomical landmarks.
3.  **Rig Generation**: Leverages the **Rigify** addon to build a professional-grade human rig.
4.  **Skinning**: Performs automatic weighting and applies custom fallbacks for failed regions.
5.  **Optimization**: Strips the rig to a clean "deform-only" skeleton for three.js compatibility.
6.  **Metadata**: Generates bone mappings for Mixamo-compatible animation retargeting.

---

## Runtime Interface

The script must be executed via Blender:
```bash
blender --background --python backend/scripts/blender_autorig.py -- [ARGS]
```

### CLI Arguments

| Argument | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `--input` | Path | Required | Path to the uploaded source model (FBX, GLB, OBJ). |
| `--output` | Path | Required | Destination for the rigged GLB. |
| `--bones` | Path | Required | Destination for the bone mapping JSON. |
| `--pose` | Path | None | Destination for pose classification results. |
| `--format` | String | `fbx` | Input file format (`fbx`, `glb`, `gltf`, `obj`). |
| `--landmarks` | JSON | None | User-edited 14-key landmarks for re-rigging. |
| `--landmarks-out` | Path | None | Destination for auto-detected landmarks. |
| `--initial-rotation-x/y/z` | Float | 0.0 | Preview-space Euler rotation (degrees). |
| `--initial-rotation-qx/qy/qz/qw` | Float | 0.0 | Preview-space quaternion. Takes precedence if non-zero. |

---

## Core Pipeline Execution

### 1. Scene Setup & Import
-   `clear_scene()`: Hard resets Blender and enables the `rigify` addon.
-   `import_model()`: Handles format-specific import logic. For FBX, it trusts Blender's header detection; for OBJ, it forces Y-up/Negative-Z-forward.
-   `strip_non_meshes()`: Deletes everything except raw geometry to ensure a clean start.

### 2. Orientation & Scaling
-   `apply_user_rotation()`: Bakes import transforms, applies optional orientation correction, then applies user-supplied rotation.
-   `_orientation_correction()`: A heuristic that detects models "lying down" (body along Y) and rotates them to stand along Z.
-   `scale_mesh_to_metarig()`: Uniformly scales the mesh so its height matches a standard Rigify metarig (~1.8m). Aligns the feet to Z=0 and centers the model on XY.

### 3. Anatomical Analysis
-   `detect_pose()`: Calculates the angle between shoulders and wrists.
    -   `t_pose`: 0–25°
    -   `a_pose`: 25–60°
    -   `arms_down`: 60–95°
-   `detect_landmarks()`:
    -   In T-Pose, identifies wrists using vertex extremities and ankles using bottom-cluster centroids.
    -   Uses AABB-based ratios for other landmarks as a stable baseline.

### 4. Rig Generation
-   `place_bones_from_landmarks()`: Moves metarig joints to landmark coordinates.
-   `generate_rig()`: Invokes Rigify's generation engine.
-   `bind_auto_weights()`: Parents the mesh to the *full* rig (control + deform bones) to give the heat solver maximum context.

### 5. Cleanup & Export
-   `patch_orphan_vertex_weights()`: **Critical Fail-safe**. Detects vertices with zero weights (which collapse to origin in three.js) and assigns them to the nearest deform bone midpoint.
-   `strip_to_deform_bones()`: Rebuilds the parent hierarchy using only `DEF-` bones. This removes hundreds of control bones that are useless for web-based animation.
-   `export_glb()`: Exports with `export_apply=True` and `export_yup=True` for seamless three.js loading.

---

## Landmark Schema (14 Keys)

Landmarks are stored and transmitted in **Three.js Editor Space** (Y-up, model normalized to height=2.0).

| Group | Keys |
| :--- | :--- |
| **Head/Torso** | `chin`, `groin` |
| **Arms (L/R)** | `shoulder`, `elbow`, `wrist` |
| **Legs (L/R)** | `hip`, `knee`, `ankle` |

### Heuristic Fallbacks
If only 6 landmarks (legacy) are provided, the script promotes them to 14 using:
- **Shoulders**: 82% of torso height.
- **Elbows**: 55% lerp between shoulder and wrist + slight Y/Z offset.
- **Hips**: At groin height, centered over ankles.
- **Knees**: 50% midpoint between hip and ankle.

---

## Deform Bone Stripping Logic

Rigify's default skeleton is too complex for basic web playback. The script reconstructs a clean chain:
1.  **Explicit Map**: Standardizes the Spine (6 segments) and Limbs.
2.  **Suffix Heuristic**: Automatically parents sub-segments (e.g., `DEF-upper_arm.L.001` → `DEF-upper_arm.L`).
3.  **Hierarchy Crawl**: Walks the original Rigify chain until it finds a valid `DEF-` ancestor, skipping `ORG-` and `MCH-` bones.

---

## Bone Mapping Table

The generated `bones.json` allows the frontend to map Mixamo animation tracks to the Rigify skeleton.

| Mixamo Name | Rigify Bone |
| :--- | :--- |
| `Hips` | `DEF-spine` |
| `Spine` | `DEF-spine.001` |
| `Neck` | `DEF-spine.004` |
| `Head` | `DEF-spine.005` |
| `LeftArm` | `DEF-upper_arm.L` |
| `LeftForeArm` | `DEF-forearm.L` |
| ... | ... |

---

## Common Failure Modes & Troubleshooting

| Symptom | Cause | Resolution |
| :--- | :--- | :--- |
| **Collapsed Vertices** | Orphan weights (heat solver failed). | Check `patch_orphan_vertex_weights` logs. Ensure mesh is manifold. |
| **Inverted Rig** | `detect_landmarks` picked up stray geometry. | Verify `--landmarks-out` output. Scale metarig manually if needed. |
| **Missing Bones** | Rigify generation failed. | Check Blender stdout for constraint/driver errors. Ensure Rigify is enabled. |
| **Wrong Orientation** | Import axis mismatch. | Toggle AABB correction or use `--initial-rotation-x/y/z`. |
| **"Failed to find solution"** | Non-manifold geometry or self-intersections. | The script applies a midpoint-fallback, but the weights may look "stiff". |

---

## Technical Constraints
-   **No External Deps**: The script must be self-contained (only `bpy`, `mathutils`, `pathlib`, `json`, `argparse`).
-   **Performance**: Skinning fallback is $O(V \times B)$. For 50k vertices and 30 bones, this adds ~2s to the execution.
-   **Memory**: Headless Blender consumes ~200MB–800MB RAM depending on mesh complexity.
