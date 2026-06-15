# Development

How to get RigFlow running on a fresh machine and where to look when something is wrong.

> **First time?** See [SETUP](SETUP.md) for a complete step-by-step guide including env file creation. This doc assumes you already have the project cloned and the env files in place.

## Prerequisites

| Tool | Version | Notes |
|---|---|---|
| Python | 3.12 | Django 5.1 + Blender 5.0 both target 3.12 |
| Node.js | 20+ | Next.js 16 |
| Blender | **5.0.1** | Required for real rigging. The Docker celery image downloads it automatically. For native Windows: install from blender.org and set `BLENDER_PATH`. If missing, rig rows are marked `failed` with a specific `error_message` — there is no passthrough fallback. See [Blender failures](#blender-failures) below. |
| Docker + Compose v2 | recent | Recommended — avoids installing Python/Node/Blender on your host |

You don't need Postgres or Redis locally — `local.py` uses SQLite and runs Celery in eager (in-process) mode.

## Env files (must exist before first run)

Three gitignored files must be created. Copy from the examples:

```bash
cp backend/.env.example backend/.env
cp docker/.env.example docker/.env
cp frontend/.env.local.example frontend/.env.local
```

At minimum, set `SECRET_KEY` (same value in both `backend/.env` and `docker/.env`) and leave `LANDMARK_VISION_PROVIDER=none` unless you have an Anthropic key. See [SETUP § All Environment Variables](SETUP.md#all-environment-variables) for the full table.

## Backend setup (without Docker)

```bash
cd backend/
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver           # http://localhost:8000
```

Default settings module: `rigflow.settings.local` — SQLite at `backend/db.sqlite3`, `CELERY_TASK_ALWAYS_EAGER=True`, `DEBUG=True`, all throttle rates relaxed to 10 000/min.

The `local.py` settings file loads `backend/.env` automatically via `django-environ`, so `ANTHROPIC_API_KEY` and `LANDMARK_VISION_PROVIDER` are picked up without exporting them in your shell.

To use the production settings locally (rare): set `DJANGO_SETTINGS_MODULE=rigflow.settings.production` and provide `DATABASE_URL`, `REDIS_URL`, `SECRET_KEY`.

## Frontend setup (without Docker)

```bash
cd frontend/
npm install
npm run dev                          # http://localhost:3000
```

`frontend/.env.local` configures the backend target:

```
NEXT_PUBLIC_API_URL=http://localhost:8000/api/v1
# NEXT_PUBLIC_WS_URL — leave UNSET; asgi.py has no Channels routing yet.
```

Defaults work if the backend is on `:8000`.

Other commands:

```bash
npm run build
npm run lint
npm test        # Vitest — landmark geometry unit tests
```

## Full stack via Docker (recommended)

```bash
docker compose -f docker/docker-compose.yml up -d --build
```

Brings up Postgres, Redis, Django via Daphne (`:8000`), Celery worker + beat + Flower (`:5555`), Next.js (`:3000`), and Nginx (`:80`).

> **First build takes 8–15 min** — the Celery image downloads Blender 5.0.1 (~600 MB) from blender.org. Subsequent builds hit the Docker layer cache and take under a minute.

The worker subscribes to queues `default,rigging,animations` (see `docker-compose.yml`). `base.py` sets `CELERY_TASK_DEFAULT_QUEUE = "default"` so tasks land on a queue the worker actually listens to — without that override, tasks would publish to Celery's default `"celery"` queue and sit forever.

After starting, create an admin user:

```bash
docker compose -f docker/docker-compose.yml exec web \
  python manage.py createsuperuser
```

To see live logs:

```bash
docker compose -f docker/docker-compose.yml logs -f
```

### Editing code in Docker

**Backend** (`web` / `celery`): live volume mount `../backend:/app`. Changes are visible immediately but the server doesn't auto-reload — restart the service:

```bash
docker compose -f docker/docker-compose.yml restart web celery
```

**Frontend**: NO live volume mount. The `frontend` image is built once with `npm run build`. To pick up any change to `frontend/src/**` or `NEXT_PUBLIC_*` vars, rebuild the image:

```bash
docker compose -f docker/docker-compose.yml up -d --build frontend
```

Then hard-refresh the browser (`Ctrl+Shift+R`) to bust the `/_next/static/` cache.

## Environment variables

| Var | Default | Used in |
|---|---|---|
| `DJANGO_SETTINGS_MODULE` | `rigflow.settings.local` | `manage.py`, `rigflow/celery.py` |
| `SECRET_KEY` | `dev-insecure-key-change-me` | `base.py` — must be set in prod |
| `DATABASE_URL` | — | `production.py` only |
| `REDIS_URL` | `redis://redis:6379/0` | Celery broker, Channels layer |
| `LANDMARK_VISION_PROVIDER` | `none` | `none` = geometry-only; `claude` = Claude Haiku 4.5 vision |
| `ANTHROPIC_API_KEY` | — | Required only when `LANDMARK_VISION_PROVIDER=claude` |
| `BLENDER_PATH` | auto-detected / `/usr/local/bin/blender` | `BLENDER_EXECUTABLE` — used by the rigging task. `Dockerfile.celery` sets this automatically. |
| `AWS_BUCKET_NAME` | unset | Production-only. If set, switches file storage to S3. |
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000/api/v1` | Frontend — baked in at build time |
| `NEXT_PUBLIC_WS_URL` | *(unset)* | Frontend — leave unset until Channels consumer is wired |

## Common commands

### Backend

```bash
python manage.py shell
python manage.py makemigrations
python manage.py migrate
python manage.py runserver
python manage.py createsuperuser
python manage.py collectstatic     # production
```

### Frontend

```bash
npm run dev          # dev server with HMR
npm run build        # production build
npm run start        # serve the build
npm run lint
npm test             # Vitest unit tests
```

### Celery (Docker only)

```bash
celery -A rigflow worker -Q default,rigging,animations -l info
celery -A rigflow beat -l info
```

## Tests

### Backend

```bash
# In Docker:
docker compose -f docker/docker-compose.yml exec web \
  python manage.py test apps.rigging apps.users apps.animations

# Or locally:
cd backend/
DJANGO_SETTINGS_MODULE=rigflow.settings.local python manage.py test
```

Test files live in `backend/apps/rigging/tests/`:

| File | What it covers |
|---|---|
| `test_bone_map_sync.py` | Bone mapping round-trip |
| `test_debug_photo.py` | Landmark debug photo generation |
| `test_e2e_pipeline.py` | End-to-end rig pipeline (mocked Blender) |
| `test_landmark_vision.py` | Claude vision provider + payload parsing |
| `test_rotation_args.py` | Rotation flag extraction |
| `test_sanity.py` | Landmark sanity-check cascade |
| `test_throttle_selection.py` | Per-action throttle selection |

### Frontend

```bash
cd frontend/
npm test
```

Covers landmark geometry utilities (`landmarkDepth`, `landmarkDrag`, `landmarkSkeleton`).

## Blender failures

If `BLENDER_EXECUTABLE` doesn't point at a real binary, exits non-zero, times out, or produces no GLB, the rigging task marks the row `status="failed"` and writes a specific `error_message`. The previous `rigged_glb` (if any) is left in place.

When debugging, look at both `RiggedModel.error_message` (driver-side reason) and `RiggedModel.rig_log` (Blender stdout). Earlier builds silently copied the input as the rigged output and marked `done` — that fallback is gone.

## Quick smoke test

After running the backend:

```bash
# 1. Register
curl -X POST http://localhost:8000/api/v1/auth/register/ \
  -H 'Content-Type: application/json' \
  -d '{"email":"a@b.co","username":"a","password":"securepass123"}'

# 2. Login
curl -X POST http://localhost:8000/api/v1/auth/login/ \
  -H 'Content-Type: application/json' \
  -d '{"email":"a@b.co","password":"securepass123"}'
# copy access token

# 3. Upload
curl -X POST http://localhost:8000/api/v1/rigs/ \
  -H "Authorization: Bearer $TOKEN" \
  -F file=@/path/to/character.glb \
  -F name="Smoke test"

# 4. Poll status
curl http://localhost:8000/api/v1/rigs/<rig_id>/status/
```

For the full endpoint surface see [API](API.md).

## Troubleshooting

| Symptom | First thing to check |
|---|---|
| `docker: command not found` | Open a fresh terminal after starting Docker Desktop. |
| `web` container exits: "SECRET_KEY setting must not be empty" | `docker/.env` not created or `SECRET_KEY` blank. See [SETUP](SETUP.md). |
| Frontend shows stale content after a code change | Rebuild the frontend image: `docker compose -f docker/docker-compose.yml up -d --build frontend`, then hard-refresh. |
| Upload returns 429 immediately | Either unauthenticated (`anon_upload = 0/min`) or the 10/hour `rig_upload` cap is hit. |
| Rig marked `failed` with "Blender executable not found…" | `BLENDER_PATH` not set or points at a non-existent binary. |
| Rig marked `failed` with "Blender exited with code <n>" | Rigify or pipeline error — open the rig in admin and read `rig_log`. |
| Rerig hangs forever in Docker | Worker isn't listening to the right queue. Confirm `CELERY_TASK_DEFAULT_QUEUE = "default"` in settings and `-Q default,rigging,animations` on the worker command. |
| 401 on `/rigs/{id}/status/` from frontend | Should never happen — that endpoint skips auth entirely. If it does, check `get_authenticators` in `views.py`. |
| `editor` page reloads stale GLB | `?v=<timestamp>` cache-buster relies on `RiggedModel.updated_at`. Make sure the rerig wrote the row. |

For the full list of project-specific gotchas, see [KNOWN_ISSUES](KNOWN_ISSUES.md).
