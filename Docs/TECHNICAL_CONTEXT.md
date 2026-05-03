# Technical Context: RigFlow

## Project Overview
- Repository: https://github.com/iliameeqvse/rigflow-project.git
- Local project root: `rigflow-project/`
- Documentation path: `rigflow-project/Docs/`
- Main workflow: User upload -> Blender Rigify automation -> landmark adjustment -> animation preview -> export.

## Core Dependencies
- Engine: Blender (Rigify)
- Frontend/UI: Next.js, React, TypeScript, Three.js, React Three Fiber
- Backend: Django, Django REST Framework, Celery
- Services: Redis, PostgreSQL in Docker, SQLite for local development, Nginx
- Animation/model formats: model uploads support FBX, GLB, GLTF, and OBJ; animation uploads support GLB, GLTF, and FBX.

## CLI Workflow Instructions
1. When starting a product or architecture task, read `rigflow-project/Docs/RIGFLOW_PRD.md`, `rigflow-project/Docs/TECHNICAL_CONTEXT.md`, and `rigflow-project/Docs/ROADMAP.md`.
2. Update `rigflow-project/Docs/ROADMAP.md` whenever a major feature is completed.
3. If an error occurs in the rigging process, reference the `4.1 Model Upload & Auto-Rigging` section in the PRD while debugging.
