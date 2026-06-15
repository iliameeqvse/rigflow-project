# Known Issues & Gotchas

Things that look broken but aren't, things that *are*, and history that explains otherwise-puzzling behaviour. Skim this before debugging anything load-bearing.

## ~~Nested repo layout~~ (resolved on current machine)

Earlier the project lived inside a doubly-nested `rigflow-project/rigflow-project/` folder with a corrupted outer `.git`. **On the current machine this is resolved** — the source root is simply `rigflow-project/` (alongside `backend/`, `frontend/`, `docker/`, and `Docs/`). All paths in these docs are relative to that root.

If you are on an older checkout that still has the nested structure, `cd rigflow-project/` once inside the outer folder before running any commands.

## ~~`requirements.txt` at the repo root is an SSH private key~~ (removed)

Historical: a PEM-formatted SSH private key was committed at the repo root as `requirements.txt`. It has been removed. The real Python deps are at `backend/requirements.txt` and always were.

## ~~`apps/throttles.py` is duplicated~~ (deduplicated)

Historical: the entire module was appended to itself, so every throttle class was defined twice. The file has been deduplicated — there is now exactly one definition of each class.

## Blender failures mark the row `failed` (no more silent passthrough)

Earlier behaviour: if `BLENDER_EXECUTABLE` wasn't a real binary, or if Blender errored, `tasks._run_rig_pipeline` silently copied the input as the "rigged" output and marked the row `done`. That hid real failures behind a green checkmark.

Current behaviour: any of these conditions sets `status=failed` and writes a specific `error_message`:

| Condition | `error_message` |
|---|---|
| `BLENDER_PATH` not a file | `"Blender executable not found at '<path>'. Set the BLENDER_PATH environment variable so Django can find it."` |
| Blender exits non-zero | `"Blender exited with code <n>. See rig log for Rigify / pipeline errors."` |
| Blender exits 0 but produced no GLB | `"Blender finished cleanly but produced no GLB output."` |
| Subprocess > 10 minutes | `"Blender timed out after 10 minutes."` |
| Subprocess raised | `"Blender subprocess raised: <repr>"` |

The previous `rigged_glb` is left in place on failure, so a failed rerig still serves the prior good GLB. **Pre-fix rigs may still be on disk as renamed FBX/OBJ files** — those will surface as JSON parse errors in any GLB-only loader. Re-rig them once Blender is installed to get a real GLB.

See [RIGGING_PIPELINE § Behaviour when Blender is missing or fails](RIGGING_PIPELINE.md#behaviour-when-blender-is-missing-or-fails).

## Animations app — import mismatch (historical)

In earlier commits, `apps/animations/urls.py` imported `AnimationViewSet` and `CategoryListView`, but `views.py` only defined `AnimationListView` / `AnimationUploadView` / `AnimationCategoryListView`. The app would fail to boot.

The current state pairs `AnimationListOrUploadView` (single class for GET/POST) with `AnimationCategoryListView` and is consistent. **Verify after pulls** — import drift is the easiest way to bring this app back down.

## `rerig-landmarks` historical: raw threading vs Celery

Earlier code spawned a raw `threading.Thread` from `rerig_landmarks` (intentional — bypassed Celery to keep the response 202-fast). The current code calls `auto_rig_model_with_landmarks.delay(...)` like the other two endpoints. Local eager mode means it still effectively runs synchronously, but the response shape (`202 Accepted` with `{status: "pending", rig_id}`) is preserved.

If you see a `threading.Thread(...)` reference in `views.py`, the rebase undid this — fix it back to `.delay()`.

## WebSockets are half-wired (polling fallback is the production path)

`tasks.push_ws()` posts events to channel group `user_{user_id}` and Channels + Redis are installed and configured — but `rigflow/asgi.py` is plain `get_asgi_application()`, so there is **no `ProtocolTypeRouter`, no URL routing, and no consumer class**. A WebSocket connection to `/ws/rig/{rig_id}/` proxies straight to Django's HTTP handler and 404s.

The frontend handles this by only opening a WS when `NEXT_PUBLIC_WS_URL` is set. Both `frontend/Dockerfile` and `docker/docker-compose.yml` leave it empty by default, so `useRigStatus.ts` falls straight through to polling `GET /rigs/{id}/status/`.

Symptom if you ever set `NEXT_PUBLIC_WS_URL` without first wiring up Channels: every editor mount logs a WebSocket failure in the console and rolls back to polling (after the 3-second WS timeout in `useRigStatus.ts`).

> **Action item**: add `apps/rigging/consumers.py`, wrap `rigflow.asgi.application` in a `ProtocolTypeRouter`, and only then re-set `NEXT_PUBLIC_WS_URL`. See [ARCHITECTURE § Real-time updates](ARCHITECTURE.md#real-time-updates).

## Landmark schema is **16 keys** (heels added)

The public API and internal schema use **16 anatomical landmark keys**: `chin`, `groin`, and L/R × `{shoulder, elbow, wrist, hip, knee, ankle, heel}`. The full list is in `LANDMARK_KEYS` in `backend/apps/rigging/views.py`, `backend/scripts/blender_autorig.py`, and `frontend/src/lib/api.ts`.

Heels were the last keys added. They are present in the schema, editor, and auto-detect, but `place_bones_from_landmarks` does **not yet read them** — heel landmarks are stored and editable but don't yet move foot/shin bone placement. Wiring heel → deform bone is the pending next step.

Implications:

- `POST /rigs/{id}/rerig-landmarks/` requires all 16 keys; missing any is a `400`.
- `RiggedModel.landmarks` holds the 16-key dict in three.js editor frame (Y-up; model ~2 units tall).
- `_promote_legacy_landmarks` in the autorig script upgrades a 6-key seed to 16 internally for legacy compatibility, but the public API is 16-only.
- The `sanity.py` module intentionally uses only 14 keys (subset check, heels excluded) as an internal quality gate — this is by design.

## AI vision pipeline sanity-check cascade

The two-phase pipeline (ortho render → Claude vision → geometry sanity check → geometry fallback → AABB defaults) means a rig can succeed with `detection_method = "geometry"` or `"failed"` even when Claude vision was invoked. "failed" means AI landmarks failed sanity AND the geometry fallback also failed — AABB defaults are used so the rig finishes as `done`, never hard-fails.

If you see `detection_method = "llm_vision"` in the admin but the rig bones look off, the sanity check passed but the AI was wrong. Use `/rerig-landmarks/` from the editor.

## Public, unthrottled `/rigs/{id}/status/`

Status polling is **public** (no auth) and **not throttled**, by design — the editor polls it freely. The viewset additionally overrides `get_authenticators` to skip JWT entirely on `status_action` and `retrieve` because a stale token from a deleted user would otherwise raise 401 *before* `AllowAny` is consulted.

If you ever lock down this endpoint:

- The editor needs an alternative status surface, or
- The polling cadence needs hard rate-limiting on the viewer instead.

## Anonymous upload always 429s

`anon_upload` rate is `0/minute` — applied **before** the demo-profile fallback in `RiggedModelViewSet.create`. Net effect: anonymous uploads always 429.

The demo-profile fallback exists for a reason (status/retrieve pages must work for anonymous viewers of historical demo rigs), but the upload path itself is auth-only.

## `CORS_ALLOW_ALL_ORIGINS = True`

Set in `settings/base.py`. Fine for development, **must be tightened before production**. Filed in [ROADMAP § Phase 2](ROADMAP.md).

## Storage quota is not enforced

`UserProfile` has `storage_quota_mb`, `storage_used_mb`, and a `has_quota_for()` helper — but **nothing calls it on upload**. A free user can upload past their quota with no warning.

> **Action item**: enforce in `RiggedModelViewSet.create` and `AnimationListOrUploadView.post`. Filed in [ROADMAP § Phase 2](ROADMAP.md).

## Stripe / payments are stubs

`apps.payments` is empty. `UserProfile.stripe_customer_id` exists but is never written. `PLAN_CHOICES` ("free / pro / studio") have prices in their labels but there's no checkout flow. Treat plans as cosmetic until [ROADMAP § Phase 3](ROADMAP.md).

## Files / paths that may surprise you

| Path | What it is |
|---|---|
| `backend/staticfiles/` | `collectstatic` output — gitignored, rebuilt on container startup. Not committed. |
| `backend/media/` | User uploads and rigged GLBs — gitignored, served from a Docker named volume. Not committed. |
| `backend/db.sqlite3` | Local dev DB — gitignored. Created on first `migrate`. |
| `frontend/package-lock.json` | The real lockfile. Root-level one (if present) is a stub from an earlier layout — ignore it. |
