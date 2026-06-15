# Technical Context

A quick-reference card. For the system architecture in depth, read [ARCHITECTURE](ARCHITECTURE.md).

## Project

- **Local source root**: `rigflow-project/` — contains `backend/`, `frontend/`, `docker/`, and `Docs/` at the top level.
- **Documentation root**: `Docs/` (this folder). Index: [README](README.md).
- **Headline workflow**: upload → ortho render → Claude Haiku 4.5 vision → Blender Rigify automation → review + (optional) landmark correction → animation preview → export.

## Stack

| Layer | Tech |
|---|---|
| Frontend | Next.js 16 (App Router), React 19, TypeScript, Tailwind CSS v4, Three.js, `@react-three/fiber`, `@react-three/drei`, Axios, TanStack Query |
| Backend | Django 5.1, Django REST Framework, `djangorestframework-simplejwt`, Channels, `django-celery-results`, `django-celery-beat`, `drf-spectacular`, `django-storages` |
| Worker | Celery (queues: `default`, `rigging`, `animations`) |
| Rigging engine | Blender **5.0.1** (Rigify) — invoked headlessly as a subprocess from the Celery task |
| AI vision | Anthropic Claude Haiku 4.5 (`claude-haiku-4-5-20251001`) via `anthropic` SDK — landmark detection from orthographic renders. Optional; set `LANDMARK_VISION_PROVIDER=none` to disable. |
| Database | SQLite (local) · PostgreSQL (Docker / production) |
| Cache · broker · channel layer | Redis |
| Reverse proxy | Nginx (Docker only) |
| Storage | Filesystem (local) · S3 via `django-storages` (when `AWS_BUCKET_NAME` is set) |

## Supported formats

| Surface | Accepted formats |
|---|---|
| Model uploads | `fbx`, `glb`, `gltf`, `obj` |
| Animation uploads | `glb`, `gltf`, `fbx` |
| Rigged output | `glb` |

## Repo layout (source root)

```
rigflow-project/                 ← repo root
├── Docs/                        ← you are here
├── backend/
│   ├── apps/                    rigging, animations, users, payments, projects, posts, throttles
│   ├── rigflow/                 settings (base, local, production), urls, asgi, celery, wsgi
│   ├── scripts/                 blender_autorig.py, _test_landmark_promotion.py, _test_*.py
│   ├── manage.py
│   └── requirements.txt
├── frontend/
│   └── src/{app, components, hooks, lib}/
└── docker/
    ├── docker-compose.yml
    └── nginx.conf
```

Run the full stack with: `docker compose -f docker/docker-compose.yml up -d --build`

## Local conventions

- `manage.py` and `rigflow/celery.py` default to `DJANGO_SETTINGS_MODULE=rigflow.settings.local`.
- Local settings set `CELERY_TASK_ALWAYS_EAGER = True` so Celery tasks run synchronously without a worker.
- `BLENDER_PATH` is set automatically to `/usr/local/bin/blender` by `Dockerfile.celery`. For native (non-Docker) installs, set it explicitly. If the binary is missing, errors, or produces no GLB, the rig row is marked `failed` with a specific `error_message` — there is no passthrough fallback. See [KNOWN_ISSUES § Blender failures mark the row `failed`](KNOWN_ISSUES.md#blender-failures-mark-the-row-failed-no-more-silent-passthrough).
- `LANDMARK_VISION_PROVIDER=none` disables Claude vision and uses geometry-only landmark detection. Set to `claude` (and provide `ANTHROPIC_API_KEY`) to enable the two-phase AI pipeline.
- Frontend stores `access` / `refresh` / `user` in `localStorage` and auto-refreshes on 401.

## Where to look first

| Task | Start here |
|---|---|
| Set up locally | [DEVELOPMENT](DEVELOPMENT.md) |
| Understand the system | [ARCHITECTURE](ARCHITECTURE.md) |
| Hit the API | [API](API.md) |
| Debug a bad rig | [RIGGING_PIPELINE](RIGGING_PIPELINE.md) → `RiggedModel.rig_log` |
| Debug surprising behaviour | [KNOWN_ISSUES](KNOWN_ISSUES.md) |
| Plan or scope a feature | [PRODUCT_REQUIREMENTS](PRODUCT_REQUIREMENTS.md) → [RIGFLOW_PRD](RIGFLOW_PRD.md) → [ROADMAP](ROADMAP.md) |
