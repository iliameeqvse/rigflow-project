# Technical Context

A quick-reference card. For the system architecture in depth, read [ARCHITECTURE](ARCHITECTURE.md).

## Project

- **Repository**: https://github.com/iliameeqvse/wigflow-project (mirror of `iliameeqvse/rigflow-project.git`).
- **Local source root**: `rigflow-project/rigflow-project/` — note the nested layout. See [KNOWN_ISSUES § Repo layout](KNOWN_ISSUES.md#repo-layout).
- **Documentation root**: `rigflow-project/Docs/` (this folder). Index: [README](README.md).
- **Headline workflow**: upload → Blender Rigify automation → review + (optional) landmark correction → animation preview → export.

## Stack

| Layer | Tech |
|---|---|
| Frontend | Next.js 16 (App Router), React 19, TypeScript, Tailwind CSS v4, Three.js, `@react-three/fiber`, `@react-three/drei`, Axios, TanStack Query |
| Backend | Django 5.1, Django REST Framework, `djangorestframework-simplejwt`, Channels, `django-celery-results`, `django-celery-beat`, `drf-spectacular`, `django-storages` |
| Worker | Celery (queues: `default`, `rigging`, `animations`) |
| Rigging engine | Blender (Rigify) — invoked headlessly as a subprocess from the Celery task |
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
rigflow-project/                 ← git root
├── CLAUDE.md                    ← agent instructions (terse; this folder is the long-form version)
├── rigflow-project/             ← actual source root — `cd` here
│   ├── Docs/                    ← you are here
│   ├── backend/
│   │   ├── apps/                rigging, animations, users, payments, projects, posts, throttles
│   │   ├── rigflow/             settings (base, local, production), urls, asgi, celery, wsgi
│   │   ├── scripts/blender_autorig.py
│   │   ├── manage.py
│   │   └── requirements.txt     ← real Python deps (NOT the one at the repo root)
│   ├── frontend/
│   │   └── src/{app, components, hooks, lib}/
│   ├── docker/{docker-compose.yml, nginx.conf}
│   └── requirements.txt         ← SSH private key (!) — see KNOWN_ISSUES
└── ...
```

## Local conventions

- `manage.py` and `rigflow/celery.py` default to `DJANGO_SETTINGS_MODULE=rigflow.settings.local`.
- Local settings set `CELERY_TASK_ALWAYS_EAGER = True` so Celery tasks run synchronously without a worker.
- `BLENDER_PATH` defaults to `/usr/bin/blender`. If absent, the rigging task falls back to a passthrough copy (intentional, but masks failures — see [KNOWN_ISSUES § Blender fallback hides failures](KNOWN_ISSUES.md#blender-fallback-hides-failures)).
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
