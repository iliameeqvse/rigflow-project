# Architecture

How RigFlow's pieces fit together end-to-end. Read [PRODUCT_REQUIREMENTS](PRODUCT_REQUIREMENTS.md) first if you need the *why*.

## Services

| Service | Tech | Local | Docker |
|---|---|---|---|
| Frontend | Next.js 16 / React 19 / Three.js | `npm run dev` on `:3000` | `frontend` container on `:3000` |
| API + WS | Django 5.1 / DRF / Channels | `manage.py runserver` on `:8000` | `web` container, Daphne on `:8000` |
| Worker | Celery (queues: `default`, `rigging`, `animations`) | runs in-process via `CELERY_TASK_ALWAYS_EAGER=True` | `celery` container |
| Scheduler | Celery beat | not used locally | `beat` container |
| Worker UI | Flower | not used locally | `flower` on `:5555` |
| Database | SQLite (local) / Postgres (prod) | `backend/db.sqlite3` | `db` container |
| Cache + broker + channel layer | Redis | not required locally | `redis` container |
| Reverse proxy | Nginx | n/a | `nginx` on `:80` |

## Request flow: upload → rigged GLB

```
 ┌──────────────┐    POST /api/v1/rigs/ (multipart)
 │  Next.js UI  ├──────────────────────────────────────┐
 │ (upload page)│                                      │
 └──────┬───────┘                                      ▼
        │                                ┌──────────────────────────┐
        │  (Optional WS: ws/rig/{rig_id}/│ RiggedModelViewSet.create│
        │◄───────────────────────────────┤  • validate ext          │
        │  push_ws() progress events     │  • create RiggedModel    │
        │                                │  • auto_rig_model.delay()│
        │                                └─────────────┬────────────┘
        │                                              │ Celery (or eager locally)
        │                                              ▼
        │                                ┌──────────────────────────┐
        │                                │ tasks._run_rig_pipeline  │
        │                                │  • write upload to tmp   │
        │                                │  • subprocess: blender   │
        │                                │      --background        │
        │                                │      --python autorig.py │
        │                                │  • read GLB + bones.json │
        │                                │  • save to RiggedModel   │
        │                                └─────────────┬────────────┘
        │                                              │
        │  GET /api/v1/rigs/{id}/status/   (polled)    │
        │◄─────────────────────────────────────────────┘
        ▼
 (Editor loads /media/rigs/<user>/<rig>/output.glb)
```

The view returns `201` immediately after queuing the task. The frontend polls `/status/` for progress updates (every 3 s). The WebSocket subscription is opt-in — see [Real-time updates](#real-time-updates) below — and disabled by default because the backend's ASGI routing isn't wired up yet.

For the Blender script's internals — landmark fitting, pose detection, weight binding — see [RIGGING_PIPELINE](RIGGING_PIPELINE.md).

## Django apps

Source: `backend/apps/`. All are mounted under `/api/v1/`.

| App | Responsibility | Status |
|---|---|---|
| `users` | Custom `User` (email login), `UserProfile` (plan + storage quota), JWT register/login/me | working |
| `rigging` | `RiggedModel`, upload + rerig + landmark-rerig endpoints, Blender subprocess driver | working |
| `animations` | Animation library (browse + upload), category list, retarget hooks | working but inconsistently wired — see [KNOWN_ISSUES](KNOWN_ISSUES.md#animations-app-import-mismatch) |
| `posts` | DRF throttling demo only (scoped + custom throttles). Not part of the product. | demo |
| `projects` | Stub | empty |
| `payments` | Stub (Stripe placeholder) | empty |

## Data model (rigging)

`RiggedModel` (UUID PK) is the only meaningful row in the system. One row per upload.

```
id                   UUID
user                 → users.UserProfile
name                 char(255)
original_file        FileField   (rigs/<user_id>/<rig_id>/<name>)
original_format      "fbx" | "glb" | "gltf" | "obj"
file_size_mb         float
rigged_glb           FileField   (output)
preview_thumbnail    ImageField  (output)
bone_mapping         JSON        (Rigify→Mixamo name map, written by Blender)
bone_corrections     JSON        (user-supplied landmarks for rerig)
detected_pose        "t_pose" | "a_pose" | "arms_down" | "unclear"
pose_angle_deg       float
pose_confidence      float
status               "pending" | "processing" | "done" | "failed"
celery_task_id       char(255)
rig_log              text        (Blender stdout)
error_message        text
processing_time_s    float
created_at, updated_at
```

Indexes: `(user, status)` and `(status, created_at)`.

## Storage

- `MEDIA_ROOT = backend/../media/` (i.e., `rigflow-project/media/`).
- Upload path: `rigs/<user_id>/<rig_id>/<filename>` — see `apps/rigging/models.py:rig_upload_path`.
- Rerigs do **not** delete the previous output up front. Django's storage suffixes the new file on collision, so a failed rerig leaves the prior good GLB serving.
- In production, if `AWS_BUCKET_NAME` is set, `DEFAULT_FILE_STORAGE` flips to S3 via `django-storages`.

## Real-time updates

The pipeline pushes progress events to Channels group `user_{user_id}` from `apps/rigging/tasks.py:push_ws()`. The infrastructure is half-wired:

- Channel layer: `channels_redis.core.RedisChannelLayer`, hosts = `[REDIS_URL]` — configured.
- ASGI app: `rigflow.asgi.application` — currently `get_asgi_application()` only, **no Channels routing**.
- Consumer / URL routing: **not yet implemented**. There is no `ProtocolTypeRouter` and no consumer class for `/ws/rig/{rig_id}/`.

Net effect today: `push_ws()` calls succeed (channel layer accepts the send), but no client receives them — there's no consumer subscribed. The frontend's `hooks/useRigStatus.ts` only opens a WebSocket if `NEXT_PUBLIC_WS_URL` is set; both `frontend/Dockerfile` and `docker-compose.yml` leave it empty so the frontend falls back to polling `GET /rigs/{id}/status/` every 3 s. Polling is sufficient for the current pipeline (steps fire seconds apart, not milliseconds), so this is a known limitation, not a bug.

To turn the WebSocket flow back on:
1. Add a `URLRouter` + `RigStatusConsumer` in `apps/rigging/consumers.py` that joins `user_{user_id}` and forwards `task.update` events.
2. Wrap `rigflow.asgi.application` with `ProtocolTypeRouter({"http": ..., "websocket": ...})`.
3. Set `NEXT_PUBLIC_WS_URL` (e.g. `ws://localhost:8000` or `wss://example.com`) at frontend build time.

Daphne is the production ASGI server (`docker/docker-compose.yml`) and already handles both HTTP and WebSocket — the missing piece is the routing/consumer code, not the server.

## Auth

- JWT via `djangorestframework-simplejwt`.
- Access token: 1 hour. Refresh token: 7 days. Refresh rotation enabled. Blacklist after rotation **disabled**.
- Two login surfaces:
  - `/api/v1/auth/token/` — vanilla SimpleJWT pair.
  - `/api/v1/auth/login/` — custom view that returns `{access, refresh, user}` (used by the frontend).
- `/api/v1/auth/me/` — current-user echo, requires Bearer.

The custom user model is in `apps/users/models.py` — `USERNAME_FIELD = "email"`. `username` is still required by `AbstractUser` internals.

## Configuration & secrets

Settings module is split:

- `rigflow/settings/base.py` — shared.
- `rigflow/settings/local.py` — SQLite, eager Celery, dev defaults. Used by `manage.py` and `celery.py` by default.
- `rigflow/settings/production.py` — requires `DATABASE_URL`, `REDIS_URL`, `SECRET_KEY`. Used in Docker.

Override with `DJANGO_SETTINGS_MODULE=rigflow.settings.production`.

Key environment variables (production): `DATABASE_URL`, `REDIS_URL`, `SECRET_KEY`, `BLENDER_PATH` (defaults to `/usr/bin/blender`), `AWS_BUCKET_NAME` (optional, switches to S3).

## Frontend layout

```
frontend/src/
├── app/                 Next.js App Router routes
│   ├── animations/      Library browse
│   ├── editor/          3D editor + landmark placement
│   ├── login/  signup/
│   ├── upload/          Model upload form
│   └── upload-animation/ Animation upload form
├── components/          ModelViewer, LandmarkEditor (R3F)
├── hooks/               useRigStatus (WS + polling)
└── lib/                 api.ts (Axios + auto-refresh on 401)
```

`NEXT_PUBLIC_API_URL` (default `http://localhost:8000/api/v1`) and `NEXT_PUBLIC_WS_URL` configure the API + WebSocket targets. JWT lives in `localStorage` keys `access`, `refresh`, `user`.

## What's intentionally *not* there

- No automated test suite. `apps/*/tests.py` are 3-line placeholders.
- No CI/CD configured.
- No Stripe integration despite `apps.payments` and `UserProfile.stripe_customer_id` existing.
- No background quota enforcement — `UserProfile.has_quota_for()` exists but is not called on upload.
- No moderation queue UI for animations even though `Animation.moderation_status` exists.
