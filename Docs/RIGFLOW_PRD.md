# RigFlow Product Requirements Document

## 1. Executive Summary
RigFlow is a web platform for preparing 3D character assets for animation. Users upload a character model, RigFlow processes it through a Blender/Rigify automation pipeline, then lets users inspect the result, adjust landmarks when needed, preview animations, and export usable rigged assets.

## 2. Target Users
- Indie and AA game developers who need faster character setup.
- 3D artists and small studios preparing bipedal characters.
- Hobbyist creators who need a guided rigging workflow without deep Blender setup.

## 3. Core Workflow
1. User uploads a supported 3D model.
2. Backend creates a rigging job and runs Blender automation through Celery.
3. User tracks progress in the editor.
4. User reviews the rigged model and skeleton preview.
5. User adjusts landmarks if the automatic rig needs correction.
6. User previews uploaded or library animations on the rig.
7. User downloads or exports the final asset.

## 4. Core Features

### 4.1 Model Upload & Auto-Rigging
- Accept model uploads in FBX, GLB, GLTF, and OBJ formats.
- Detect original format and preserve upload metadata.
- Run Blender/Rigify automation with pose and rotation handling.
- Produce a downloadable rigged GLB when processing succeeds.
- Expose job status, progress step, percentage, error state, and output URL.

### 4.2 Rig Editor & Landmark Adjustment
- Display the uploaded or rigged model in a web-based Three.js viewer.
- Allow users to place or adjust body landmarks when auto-rigging needs correction.
- Submit landmark updates to rerun or refine the rigging pipeline.
- Show skeleton and model previews clearly enough to verify placement.

### 4.3 Animation Management
- Let authenticated users upload GLB, GLTF, or FBX animation files.
- Provide a browsable animation library with categories, metadata, and uploaded user animations.
- Retarget or preview selected animations on a rigged model.
- Surface clear errors when tracks cannot bind to the rig skeleton.

## 5. Current Implementation Context
- Frontend: Next.js, React, TypeScript, Three.js, React Three Fiber, Axios, TanStack Query.
- Backend: Django REST Framework, Celery, Redis, PostgreSQL/SQLite for development.
- Runtime services: Docker Compose for web, frontend, database, Redis, Celery, Flower, and Nginx.
- Primary docs path: `rigflow-project/Docs/`.

## 6. Acceptance Criteria
- Standard bipedal FBX/GLB/GLTF/OBJ uploads create a rigging job and show live progress.
- Successful Blender runs produce a rigged GLB that loads in the editor.
- Landmark edits can be submitted without losing the previous valid rig output.
- Animation uploads reject unsupported formats with a clear validation message.
- Animation preview handles GLB/GLTF/FBX sources and reports unbound tracks.
