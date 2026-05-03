# Known Issues & Gotchas

Things that look broken but aren't, things that *are*, and history that explains otherwise-puzzling behaviour. Skim this before debugging anything load-bearing.

## Repo layout

> **Source actually lives one directory deeper than the git root.**

The git root is `rigflow-project/`. Source lives at `rigflow-project/rigflow-project/{backend,frontend,docker,Docs}/`.

`git status` from the git root shows every tracked file as **deleted** — paths like `backend/...` look gone — because the working tree was moved into the nested folder without a matching commit. This is harmless if you know about it, deeply confusing otherwise.

**Always `cd rigflow-project/` first** before running any of the commands in [DEVELOPMENT](DEVELOPMENT.md).

## `requirements.txt` at the repo root is an SSH private key

The file at `rigflow-project/rigflow-project/requirements.txt` (the *outer* requirements) is a **PEM-formatted SSH private key**, not Python deps. There's also a `requirements.txt.pub` next to it (the public half).

The real Python deps are at `backend/requirements.txt`. Use that one.

If you ever `pip install -r requirements.txt` at the wrong location, pip will choke on the PEM headers. No real damage — just confusion.

> **Action item**: this should be moved out of the repo and into a secret store. Filed in [ROADMAP § Phase 1](ROADMAP.md).

## `apps/throttles.py` is duplicated

The entire module is **appended to itself**. Every throttle class is defined twice. Python keeps the second definition, so behaviour is correct, but:

- Edits must be made to **both halves**, or the duplicate must be cleaned up first.
- If you clean it up, run the test suite (such as it is) and a manual smoke test on each throttle scope.

> **Action item**: deduplicate. Filed in [ROADMAP § Phase 1](ROADMAP.md).

## Blender failures mark the row `failed` (no more silent passthrough)

Earlier behaviour: if `BLENDER_EXECUTABLE` (env: `BLENDER_PATH`) wasn't a real binary, or if Blender errored, `tasks._run_rig_pipeline` silently copied the input as the "rigged" output and marked the row `done`. That hid real failures behind a green checkmark.

Current behaviour: any of these conditions sets `status=failed` and writes a specific `error_message`:

| Condition | `error_message` |
|---|---|
| `BLENDER_PATH` not a file | `"Blender executable not found at '<path>'. Set the BLENDER_PATH environment variable so Django can find it."` |
| Blender exits non-zero | `"Blender exited with code <n>. See rig log for Rigify / pipeline errors."` |
| Blender exits 0 but produced no GLB | `"Blender finished cleanly but produced no GLB output."` |
| Subprocess > 10 minutes | `"Blender timed out after 10 minutes."` |
| Subprocess raised | `"Blender subprocess raised: <repr>"` |

The previous `rigged_glb` is left in place on failure (the rerig endpoints already preserve it), so a failed rerig still serves the prior good GLB. **Pre-fix rigs may still be on disk as renamed FBX/OBJ files** — those will surface as JSON parse errors in any GLB-only loader. Re-rig them once Blender is installed to get a real GLB.

See [RIGGING_PIPELINE § Behaviour when Blender is missing or fails](RIGGING_PIPELINE.md#behaviour-when-blender-is-missing-or-fails).

## Animations app — import mismatch (historical)

In earlier commits, `apps/animations/urls.py` imported `AnimationViewSet` and `CategoryListView`, but `views.py` only defined `AnimationListView` / `AnimationUploadView` / `AnimationCategoryListView`. The app would fail to boot.

The current state pairs `AnimationListOrUploadView` (single class for GET/POST) with `AnimationCategoryListView` and is consistent. **Verify after pulls** — import drift is the easiest way to bring this app back down.

## `rerig-landmarks` historical: raw threading vs Celery

Earlier code spawned a raw `threading.Thread` from `rerig_landmarks` (intentional — bypassed Celery to keep the response 202-fast). The current code calls `auto_rig_model_with_landmarks.delay(...)` like the other two endpoints. Local eager mode means it still effectively runs synchronously, but the response shape (`202 Accepted` with `{status: "pending", rig_id}`) is preserved.

If you see a `threading.Thread(...)` reference in `views.py`, the rebase undid this — fix it back to `.delay()`.

## CLAUDE.md drift

The top-level `CLAUDE.md` (project instructions for the Claude Code agent) describes the rigging endpoints as calling `_run_rig_pipeline` **inline in the request thread**. The current code calls `auto_rig_model.delay(...)` (Celery). Local has `CELERY_TASK_ALWAYS_EAGER=True` so the practical effect is identical, but in Docker/production the work is queued.

`CLAUDE.md` is intentionally terse and slightly behind the code in places. Treat the source as authoritative.

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

## No real test suite

`apps/*/tests.py` are 3-line placeholders. No CI. No coverage tracking. New code is tested manually.

> **Action item**: add a baseline test suite for upload validation, throttle behaviour, and the rerig-preserves-old-GLB invariant. Filed in [ROADMAP § Phase 1](ROADMAP.md).

## Stripe / payments are stubs

`apps.payments` is empty. `UserProfile.stripe_customer_id` exists but is never written. `PLAN_CHOICES` ("free / pro / studio") have prices in their labels but there's no checkout flow. Treat plans as cosmetic until [ROADMAP § Phase 3](ROADMAP.md).

## Files / paths that may surprise you

| Path | What it is |
|---|---|
| `gaxsenidamerewashale` (repo root) | Empty file, ka name (Georgian transliteration). Harmless cruft. |
| `package-lock.json` (repo root) | Tiny stub — actual frontend lockfile is at `frontend/package-lock.json`. |
| `backend/db.sqlite3` | Local dev DB. Checked in for a smooth first-run experience; **wipe before any serious work**. |
| `media/` (one level above `backend/`) | `MEDIA_ROOT`. User uploads land here. Not checked in. |
