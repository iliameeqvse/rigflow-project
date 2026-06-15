# RigFlow — Setup Guide

RigFlow is an AI-powered 3D character auto-rigging platform. Upload an FBX, GLB, or OBJ model and get back a fully rigged, animation-ready GLB file — driven by Claude vision + Blender's Rigify pipeline running inside Docker.

---

## Prerequisites

| Tool | Version | Notes |
|------|---------|-------|
| Docker Desktop | 4.x+ | Includes Docker Compose v2 |
| Git | any | For cloning |
| A terminal | — | PowerShell, bash, or zsh |

Blender, Python, and Node.js do **not** need to be installed on your host machine. They run inside Docker containers.

> **Windows users:** Make sure Docker Desktop is running before opening your terminal. If `docker` is not found, open a fresh terminal after Docker starts — the PATH update only applies to new shells.

---

## Quick Start (10 minutes)

### 1. Clone the repository

```bash
git clone <repo-url>
cd rigflow-project
```

### 2. Create the three required env files

**`backend/.env`** (copy from the example):

```bash
cp backend/.env.example backend/.env
```

Then open `backend/.env` and set at minimum:

```env
SECRET_KEY=any-long-random-string
LANDMARK_VISION_PROVIDER=none      # use "none" if you don't have an Anthropic key
ANTHROPIC_API_KEY=                 # optional — required only if provider=claude
```

**`docker/.env`** (copy from the example):

```bash
cp docker/.env.example docker/.env
```

Then set:

```env
DB_PASSWORD=any-password
SECRET_KEY=same-value-as-backend-env
NEXT_PUBLIC_API_URL=http://localhost:8000/api/v1
```

> `SECRET_KEY` must be identical in both files. `DB_PASSWORD` can be anything you choose — it's only used internally between containers.

**`frontend/.env.local`** (only needed for `npm run dev` outside Docker):

```bash
cp frontend/.env.local.example frontend/.env.local
```

The defaults work as-is.

### 3. Build and start all services

```bash
docker compose -f docker/docker-compose.yml up -d --build
```

The first build takes **8–15 minutes** because the Celery container downloads Blender 5.0.1 (~600 MB) from blender.org. Subsequent builds are cached and take under a minute.

Watch the logs to confirm all services started:

```bash
docker compose -f docker/docker-compose.yml logs -f
```

### 4. Create an admin user

```bash
docker compose -f docker/docker-compose.yml exec web \
  python manage.py createsuperuser
```

The user model is email-based — enter your email as the username.

### 5. Open the app

| URL | What it is |
|-----|-----------|
| `http://localhost:3000` | Next.js frontend |
| `http://localhost:80` | Nginx reverse proxy (same app, port 80) |
| `http://localhost:8000/api/docs/` | Swagger API docs |
| `http://localhost:8000/admin/` | Django admin |
| `http://localhost:5555` | Flower (Celery task monitor) |

---

## All Environment Variables

### `backend/.env`

| Variable | Required | Description |
|----------|----------|-------------|
| `SECRET_KEY` | Yes | Django secret key. Generate with `python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"` |
| `LANDMARK_VISION_PROVIDER` | Yes | `none` (geometry-only, no API key needed) or `claude` (requires `ANTHROPIC_API_KEY`) |
| `ANTHROPIC_API_KEY` | Only if `provider=claude` | Anthropic API key for Claude vision landmark detection |
| `BLENDER_PATH` | No | Full path to `blender.exe` for a native Windows install. Leave unset inside Docker. |
| `AWS_BUCKET_NAME` | No | S3 bucket for media storage. Leave blank to use local filesystem. |
| `AWS_ACCESS_KEY_ID` | No | AWS credentials (only if using S3) |
| `AWS_SECRET_ACCESS_KEY` | No | AWS credentials (only if using S3) |
| `STRIPE_SECRET_KEY` | No | Stripe API key (payments not yet wired) |
| `STRIPE_WEBHOOK_SECRET` | No | Stripe webhook secret |

### `docker/.env`

| Variable | Default | Description |
|----------|---------|-------------|
| `DB_PASSWORD` | `rigflow123` | PostgreSQL password. Change in production. |
| `SECRET_KEY` | — | Same value as `backend/.env SECRET_KEY` |
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000/api/v1` | URL the browser uses to reach the API. Must be reachable from the browser, not just inside Docker. |

### `frontend/.env.local` (outside Docker only)

| Variable | Default | Description |
|----------|---------|-------------|
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000/api/v1` | Same as docker/.env |
| `NEXT_PUBLIC_WS_URL` | *(unset)* | WebSocket URL. Leave unset — WS is not yet fully wired. |

---

## Development Mode

### Editing backend code

The `web` and `celery` containers mount `../backend:/app` as a live volume. Any change to a Python file is immediately visible inside the container — but Gunicorn/Daphne won't auto-reload.

To pick up backend changes:

```bash
docker compose -f docker/docker-compose.yml restart web celery
```

### Editing frontend code

**The frontend container does not have a live volume mount.** `Dockerfile` runs `npm run build` at image-build time and serves the production bundle. Editing `frontend/src/**` on disk has no effect on the running container.

To see a frontend change:

```bash
docker compose -f docker/docker-compose.yml up -d --build frontend
```

Then hard-refresh the browser (`Ctrl+Shift+R`) to bust the Next.js asset cache.

### Running the backend locally (without Docker)

If you want to iterate on backend code with Django's `runserver` (auto-reload):

```bash
cd backend
pip install -r requirements.txt

# Requires a locally running PostgreSQL or use the default SQLite (see settings/local.py)
DJANGO_SETTINGS_MODULE=rigflow.settings.local python manage.py migrate
DJANGO_SETTINGS_MODULE=rigflow.settings.local python manage.py runserver
```

`settings/local.py` uses SQLite and sets `CELERY_TASK_ALWAYS_EAGER = True` — Celery tasks run synchronously in the same process, so you don't need a separate worker or Redis.

> **Blender is required for rigging** even in local mode. Install Blender 5.0 and set `BLENDER_PATH` in `backend/.env`, or set `LANDMARK_VISION_PROVIDER=none` and leave the system Blender on your PATH.

---

## Running Tests

### Backend (pytest via Django test runner)

```bash
docker compose -f docker/docker-compose.yml exec web \
  python manage.py test apps.rigging apps.users apps.animations
```

Or locally:

```bash
cd backend
DJANGO_SETTINGS_MODULE=rigflow.settings.local python manage.py test
```

### Frontend (Vitest)

```bash
cd frontend
npm install
npm test
```

Tests live in `frontend/src/lib/*.test.ts` and cover landmark geometry utilities.

---

## Database Migrations

Migrations run automatically when the `web` container starts (the `docker-compose.yml` `command` begins with `python manage.py migrate`). You don't need to run them manually.

To create a new migration after editing a model:

```bash
docker compose -f docker/docker-compose.yml exec web \
  python manage.py makemigrations
```

---

## Common Errors

### `docker: command not found`

Docker Desktop isn't on PATH in your current shell. Open a new terminal after starting Docker Desktop, or add `C:\Program Files\Docker\Docker\resources\bin` to your PATH.

### `docker-credential-desktop not found` during build

Same PATH issue as above. Open a fresh terminal.

### `web` container exits immediately with `SECRET_KEY setting must not be empty`

`docker/.env` was not created or `SECRET_KEY` is blank. See step 2 above.

### Frontend shows `Cannot connect to API` or all requests fail

`NEXT_PUBLIC_API_URL` is baked into the JS bundle at **build time**, not runtime. If you changed it in `docker/.env` after the first build, rebuild the frontend:

```bash
docker compose -f docker/docker-compose.yml up -d --build frontend
```

### Rig status stays `pending` forever

The Celery worker (`celery` container) isn't running or failed to start. Check:

```bash
docker compose -f docker/docker-compose.yml logs celery
```

Common causes: `backend/.env` missing, Blender download failed during image build.

### Blender download fails during `docker compose build`

The `celery` image fetches Blender 5.0.1 from `download.blender.org`. If the download times out:

```bash
docker compose -f docker/docker-compose.yml build celery --no-cache
```

Or check your internet connection / proxy settings.

### `ANTHROPIC_API_KEY` missing — rig still works?

Yes — `LANDMARK_VISION_PROVIDER=none` is the safe default. Landmark detection falls back to pure geometry. Set `provider=claude` only when you have a valid API key.

### Model rigs with bad bone placement / inverted skeleton

See `Docs/KNOWN_ISSUES.md` and `Docs/RIGGING_PIPELINE.md`. T-pose or A-pose models rig best. If the skeleton looks inverted, try uploading with a rotation correction using the rotation preview on the upload page.

---

## Production Deployment

1. Set strong, unique values for `SECRET_KEY` and `DB_PASSWORD` in `docker/.env`.
2. Set `NEXT_PUBLIC_API_URL` to your public domain (e.g., `https://api.yourdomain.com/api/v1`).
3. Configure an S3 bucket and set `AWS_*` variables in `backend/.env` to avoid losing uploads when containers restart.
4. Point a reverse proxy (or use the included `nginx` service) at your domain.
5. Restrict `ALLOWED_HOSTS` in `backend/rigflow/settings/production.py` to your domain.

> The included nginx config (`docker/nginx.conf`) handles `/api/`, `/admin/`, `/static/`, and `/media/` routing and proxies everything else to the Next.js frontend.

---

## Project Structure

```
rigflow-project/
├── backend/                 # Django + Celery
│   ├── apps/
│   │   ├── rigging/         # Core: model upload, Blender pipeline, landmarks
│   │   ├── animations/      # Animation library
│   │   ├── users/           # Auth, profiles
│   │   ├── posts/           # Throttle demo app
│   │   └── payments/        # Stub (not yet wired)
│   ├── scripts/
│   │   └── blender_autorig.py   # Blender Python script (runs inside celery container)
│   ├── rigflow/settings/
│   │   ├── base.py          # Shared settings
│   │   ├── local.py         # SQLite, eager tasks, relaxed throttling
│   │   └── production.py    # PostgreSQL, S3, WhiteNoise
│   ├── Dockerfile           # web + beat + flower image
│   ├── Dockerfile.celery    # celery image (includes Blender 5.0.1)
│   └── requirements.txt
├── frontend/                # Next.js 16 + Three.js
│   ├── src/
│   │   ├── app/             # Page routes (upload, editor, animations, auth)
│   │   ├── components/      # 3D viewer, landmark editor, landing sections
│   │   └── lib/             # API client, landmark geometry utilities
│   └── Dockerfile           # Production build (no live reload)
├── docker/
│   ├── docker-compose.yml   # Full stack: db, redis, web, celery, beat, flower, frontend, nginx
│   ├── nginx.conf           # Reverse proxy config
│   ├── .env.example         # Template — copy to docker/.env
└── Docs/                    # Architecture, API, and pipeline documentation
```

---

## API Reference

Full interactive docs at `http://localhost:8000/api/docs/` (Swagger UI).

Key endpoints:

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/auth/register/` | Create account |
| `POST` | `/api/v1/auth/login/` | Get JWT tokens |
| `POST` | `/api/v1/rigs/` | Upload model for auto-rigging |
| `GET` | `/api/v1/rigs/<id>/status/` | Poll rig progress |
| `GET` | `/api/v1/rigs/<id>/landmarks/` | Get 16 anatomical landmarks |
| `POST` | `/api/v1/rigs/<id>/rerig-landmarks/` | Re-rig with user-adjusted landmarks |
| `GET` | `/api/v1/animations/` | List animation library |
| `POST` | `/api/v1/animations/<id>/retarget/` | Apply animation to a rig |
