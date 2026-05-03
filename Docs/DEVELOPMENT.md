# Development

How to get RigFlow running on a fresh machine and where to look when something is wrong.

> All paths in this doc are relative to `rigflow-project/rigflow-project/`. **Always `cd` there first** — see [KNOWN_ISSUES § Repo layout](KNOWN_ISSUES.md#repo-layout).

## Prerequisites

| Tool | Version | Notes |
|---|---|---|
| Python | 3.11+ | Django 5.1 needs ≥ 3.10 |
| Node.js | 20+ | Next.js 16 |
| Blender | 3.6 LTS or 4.x | Needed for real rigging. If missing, the pipeline silently falls back to a passthrough copy — see [Blender fallback](#blender-fallback) below. |
| Docker + Compose | recent | Optional — only for full-stack local runs |

You don't need Postgres or Redis locally — `local.py` uses SQLite and runs Celery in eager (in-process) mode.

## Backend setup

```bash
cd backend/
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt      # NOT the one at the repo root — that is an SSH key (see KNOWN_ISSUES)
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver           # http://localhost:8000
```

Default settings: `rigflow.settings.local` — SQLite at `backend/db.sqlite3`, `CELERY_TASK_ALWAYS_EAGER=True`, `DEBUG=True`.

To use the production settings locally (rare): set `DJANGO_SETTINGS_MODULE=rigflow.settings.production` and provide `DATABASE_URL`, `REDIS_URL`, `SECRET_KEY`.

## Frontend setup

```bash
cd frontend/
npm install
npm run dev                          # http://localhost:3000
```

Configure the backend target via `frontend/.env.local`:

```
NEXT_PUBLIC_API_URL=http://localhost:8000/api/v1
NEXT_PUBLIC_WS_URL=ws://localhost:8000
```

Defaults work if you run the backend on `:8000`.

Other commands:

```bash
npm run build
npm run lint
```

## Full stack via Docker

```bash
cd docker/
docker compose up
```

Brings up Postgres, Redis, Django via Daphne (`:8000`), Celery worker + beat + Flower (`:5555`), Next.js (`:3000`), and Nginx (`:80`).

The worker subscribes to queues `default,rigging,animations` (see `docker-compose.yml`). The base settings override `CELERY_TASK_DEFAULT_QUEUE = "default"` so tasks land on a queue the worker actually listens to — without that override, tasks would publish to Celery's own default `"celery"` queue and sit forever.

## Environment variables

| Var | Default | Used in |
|---|---|---|
| `DJANGO_SETTINGS_MODULE` | `rigflow.settings.local` | `manage.py`, `rigflow/celery.py` |
| `SECRET_KEY` | `dev-insecure-key-change-me` | `base.py` — must be set in prod |
| `DATABASE_URL` | — | `production.py` only |
| `REDIS_URL` | `redis://redis:6379/0` | Celery broker, Channels layer |
| `BLENDER_PATH` | `/usr/bin/blender` | `BLENDER_EXECUTABLE`, used by the rigging task |
| `AWS_BUCKET_NAME` | unset | Production-only. If set, switches `DEFAULT_FILE_STORAGE` to S3. |
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000/api/v1` | Frontend |
| `NEXT_PUBLIC_WS_URL` | `ws://localhost:8000` | Frontend |

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
```

### Celery (Docker only)

```bash
celery -A rigflow worker -Q default,rigging,animations -l info
celery -A rigflow beat -l info
```

## Tests

There is no real test suite yet. Every `apps/*/tests.py` is a 3-line placeholder. If you write a test, please run it with:

```bash
python manage.py test
```

…and add coverage notes to [ROADMAP](ROADMAP.md).

## Blender failures

If `BLENDER_EXECUTABLE` doesn't point at a real binary, exits non-zero, times out, or produces no GLB, the rigging task marks the row `status="failed"` and writes a specific `error_message` (e.g. `Blender executable not found at '<path>'. Set the BLENDER_PATH environment variable so Django can find it.`). The previous `rigged_glb` (if any) is left in place.

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
| `git status` shows every file as deleted | You are at the wrong root. `cd rigflow-project/`. See [KNOWN_ISSUES § Repo layout](KNOWN_ISSUES.md#repo-layout). |
| `pip install -r requirements.txt` fails with parse errors | You ran it at the repo root. That file is an SSH private key. Use `backend/requirements.txt`. |
| Upload returns 429 immediately | Either you're unauthenticated (`anon_upload = 0/min`) or you've blown the 10/hour `rig_upload` cap. |
| Rig marked `failed` with "Blender executable not found…" | `BLENDER_PATH` not visible to the Django process. `export BLENDER_PATH=/path/to/blender` and restart the server. |
| Rig marked `failed` with "Blender exited with code <n>" | Rigify or pipeline error — open the rig in admin and read `rig_log`. |
| Rerig hangs forever in Docker | Worker isn't listening to the right queue. Confirm `CELERY_TASK_DEFAULT_QUEUE = "default"` in settings and `-Q default,rigging,animations` on the worker command. |
| 401 on `/rigs/{id}/status/` from frontend | Should never happen — that endpoint skips auth entirely. If it does, check `get_authenticators` hasn't been changed in `views.py`. |
| `editor` page reloads stale GLB | `?v=<timestamp>` cache-buster relies on `RiggedModel.updated_at`. Make sure the rerig actually wrote the row. |

For the full list of project-specific gotchas, see [KNOWN_ISSUES](KNOWN_ISSUES.md).
