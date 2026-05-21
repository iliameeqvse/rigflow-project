# API Reference

All endpoints are mounted under `/api/v1/`. The OpenAPI schema is the source of truth — Swagger UI lives at `/api/docs/`, Redoc at `/api/redoc/`, and the raw schema at `/api/schema/`. This document is a hand-written tour of the parts you will actually use.

## Conventions

- **Base URL** in development: `http://localhost:8000/api/v1`.
- **Auth**: `Authorization: Bearer <access_token>` on protected endpoints. Get a token via `POST /auth/login/`.
- **Errors**: DRF default shape — `{ "detail": "..." }` for permission/auth/throttle errors, `{ "field": ["..."] }` for serializer validation errors. Custom views also use `{ "error": "..." }` (see `rigging.views`).
- **Throttling**: every view gets the global `AnonRateThrottle` + `UserRateThrottle` plus any per-action throttle. The most restrictive rule wins. See [Throttle table](#throttle-table) below.
- **CORS**: `CORS_ALLOW_ALL_ORIGINS = True` in base settings — fine for dev, must be tightened before prod.

## Auth

### `POST /auth/register/`

Create an account. Returns the same `{access, refresh, user}` shape as `/auth/login/` so the frontend signs the user in immediately after signup.

```json
// request
{ "email": "user@example.com", "username": "myname", "password": "securepass123" }

// 201 response
{
  "access":  "eyJhbGciOiJI...",
  "refresh": "eyJhbGciOiJI...",
  "user":    { "id": 1, "email": "user@example.com", "username": "myname" }
}
```

Side effect: a `UserProfile` row is created at the same time (via post_save signal in `apps.users`) so subsequent uploads attach to the user's own profile rather than falling back to the demo profile.

### `POST /auth/login/`

Exchange email + password for a JWT pair.

```json
// request
{ "email": "user@example.com", "password": "securepass123" }

// 200 response
{
  "access":  "eyJhbGciOiJI...",
  "refresh": "eyJhbGciOiJI...",
  "user":    { "id": 1, "email": "user@example.com", "username": "myname" }
}
```

### `POST /auth/token/` · `/auth/token/refresh/` · `/auth/token/verify/`

Vanilla SimpleJWT endpoints. Lifetimes: access 1 h, refresh 7 d. Refresh rotation is on; blacklist-after-rotation is off, so old refresh tokens stay technically valid until they expire.

### `GET /auth/me/`

Echo the current user. Bearer required.

```json
{ "id": 1, "email": "user@example.com", "username": "myname", "plan": "free" }
```

## Rigging

The rigging app exposes `RiggedModelViewSet` under `/rigs/`. The collection list and create are protected; **status and detail are public** (see [why](#why-status-and-retrieve-are-public) below).

### `POST /rigs/`

Upload a 3D model. Multipart form. Authenticated only.

| Field | Required | Notes |
|---|---|---|
| `file` | yes | `.fbx`, `.glb`, `.gltf`, `.obj` |
| `name` | no | Default `"Untitled"`, truncated to 255 chars |
| `rotation_x`, `rotation_y`, `rotation_z` | no | Manual preview-space Euler degrees. Sent only if the user adjusted orientation in the upload preview. |
| `rotation_qx`, `rotation_qy`, `rotation_qz`, `rotation_qw` | no | Optional accompanying quaternion for the same rotation, supplied for higher fidelity than Euler when the preview supports it. |

Rotation kicks in only when `|x|, |y|,` or `|z| > 0.5°`; the quaternion fields are passed through only when at least one component is non-zero.

Returns `201` with the full `RiggedModel` row. Pipeline runs asynchronously (or eagerly in local). The fresh row starts with `status: "pending"`.

If the request is unauthenticated, the view falls back to a `demo@rigflow.local` profile so anonymous demos work — but the global `AnonUploadThrottle` (`0/min`) blocks them with 429 first. Net effect: anonymous uploads always 429.

### `GET /rigs/`

List the current user's rigs. Auth required.

### `GET /rigs/{id}/`

Detail for one rig. **Public** — no auth, no throttle. Returns the same shape as create.

### `GET /rigs/{id}/status/`

Lightweight status poll. **Public, unthrottled.** The frontend polls this freely.

```json
{
  "rig_id": "f1a8c0b2-...",
  "status": "processing",
  "progress": { "step": "Auto-rigging with Blender...", "pct": 50 },
  "rigged_glb_url": "http://.../media/rigs/1/<rig>/output.glb?v=1714857600",
  "error_message": ""
}
```

`progress.step` / `pct` are derived from `status`:

| `status` | `step` | `pct` |
|---|---|---|
| `pending` | "Waiting in queue..." | 5 |
| `processing` | "Auto-rigging with Blender..." | 50 |
| `done` | "Done" | 100 |
| `failed` | "Failed" | 0 |

The `?v=<timestamp>` query string on `rigged_glb_url` is a cache-buster keyed on `updated_at` so the editor reloads after a rerig overwrites the file.

### `POST /rigs/{id}/rerig/`

Re-run auto-rig on the original file. Resets status to `pending`, clears `bone_mapping`, `rig_log`, `error_message`. Does **not** delete the existing `rigged_glb` — Django storage suffixes the new file, and a failed rerig leaves the previous good GLB serving.

### `POST /rigs/{id}/rerig-landmarks/`

Re-rig with user-placed landmarks from the editor. Required body — **all 14 keys must be present**:

```json
{
  "landmarks": {
    "chin":           [x, y, z],
    "groin":          [x, y, z],
    "left_shoulder":  [x, y, z],   "right_shoulder": [x, y, z],
    "left_elbow":     [x, y, z],   "right_elbow":    [x, y, z],
    "left_wrist":     [x, y, z],   "right_wrist":    [x, y, z],
    "left_hip":       [x, y, z],   "right_hip":      [x, y, z],
    "left_knee":      [x, y, z],   "right_knee":     [x, y, z],
    "left_ankle":     [x, y, z],   "right_ankle":    [x, y, z]
  }
}
```

Coordinates are floats in the **three.js editor frame** (Y-up; the model is normalized to ~2 units tall). Returns `202 Accepted` immediately; poll `/status/`.

Validation (in `_validate_landmark_payload`):

- Must be an object. Each value must be a 3-element array of finite numbers.
- Missing any of the 14 keys → `400` with the list of missing names.
- Non-numeric / non-finite coordinate → `400` naming the offending key.

The pipeline preserves the previous `rigged_glb` on failure for the same reason as `/rerig/`.

For the landmark anatomy and how the script consumes them, see [RIGGING_PIPELINE](RIGGING_PIPELINE.md#landmarks).

### `GET /rigs/{id}/landmarks/`

Fetch the 14-key landmark dict the editor uses to render draggable markers. **Public, no auth, no throttle.**

```json
{
  "landmarks": {
    "chin":           [0.0,  1.84, 0.0],
    "groin":          [0.0,  1.0,  0.0],
    "left_shoulder":  [0.2,  1.64, 0.0],
    ... (12 more keys)
  }
}
```

If the rig was generated by the current pipeline, this returns `RiggedModel.landmarks` (auto-detected during the run). If the rig pre-dates the feature, the view falls back to `legacy_landmarks.default_landmarks_for_rig()` — AABB defaults at unit height — so the editor never sees an empty payload.

### Why `status` and `retrieve` are public

The editor page must be loadable for anonymous users (e.g., a demo flow, or a user whose stale JWT points at a deleted row after a DB wipe). To make this work the viewset overrides `get_authenticators` so JWT auth is **skipped** entirely on those actions — otherwise a stale token would 401 before `AllowAny` ever ran. The list/create endpoints retain normal auth.

## Animations

`/animations/` is a single endpoint that switches behavior on method.

### `GET /animations/`

Browse animations. Public — returns approved + public animations, plus your own uploads if you're authenticated.

Filter: `moderation_status="approved" AND is_public=True`, OR `uploaded_by = <you>`.

### `POST /animations/`

Upload a custom animation. Authenticated. Multipart with `file` (GLB/GLTF/FBX) plus serializer fields (see `apps/animations/serializers.py`). Throttled at 15/hour per user.

### `GET /animations/categories/`

List animation categories. Public.

```json
[ { "id": 1, "name": "Locomotion", "slug": "locomotion", "icon": "..." } ]
```

> **Note**: `apps.animations.urls` and `views.py` were inconsistent in earlier commits (referenced `AnimationViewSet` / `CategoryListView` that did not exist). The current state pairs `AnimationListOrUploadView` with `AnimationCategoryListView` and is consistent. Re-verify after pulls — see [KNOWN_ISSUES](KNOWN_ISSUES.md#animations-app-import-mismatch).

## Throttle table

Defined in `rigflow/settings/base.py:DEFAULT_THROTTLE_RATES` and `apps/throttles.py`.

| Scope | Rate | Where it applies |
|---|---|---|
| `anon` | 5 / min | Every endpoint, unauthenticated requests |
| `user` | 10 / min | Every endpoint, authenticated requests |
| `anon_upload` | **0 / min** | Any upload endpoint (`anon_upload` always returns 429) |
| `rig_upload` | 10 / hour | `POST /rigs/`, `/rerig/`, `/rerig-landmarks/` |
| `animation_upload` | 15 / hour | `POST /animations/` |
| `rig_list` | 30 / min | `GET /rigs/`, `/rigs/{id}/` |
| `animation_list` | 60 / min | `GET /animations/`, `/animations/categories/` |
| `posts_list` | 20 / min | Demo-only — `GET /posts/` |
| `posts_create` | 3 / min | Demo-only — `POST /posts/create/` |
| `post_burst` | 1 / 10 s | Custom throttle on `POST /posts/create/` |

`/rigs/{id}/status/` is **not throttled** by design — the editor polls it.

## Schema, docs, admin

- `/api/schema/` — raw OpenAPI 3 JSON.
- `/api/docs/` — Swagger UI.
- `/api/redoc/` — Redoc.
- `/admin/` — Django admin (superuser only).

## Posts (demo only)

`apps.posts` is a tiny app whose only purpose is to demonstrate scoped + custom throttles. **It is not part of the product.** If you are looking at it for product reasons, you are in the wrong place.
