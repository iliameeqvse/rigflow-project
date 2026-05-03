# RigFlow — Product Requirements Document

Status: living document. For a one-pager skim, see [PRODUCT_REQUIREMENTS](PRODUCT_REQUIREMENTS.md).

## 1. Executive summary

RigFlow is a web platform for preparing 3D character assets for animation. Users upload a character model, RigFlow processes it through a Blender/Rigify automation pipeline, then lets users inspect the result, adjust landmarks when needed, preview animations, and export usable rigged assets.

The product wager: most game-ready bipedal meshes can be auto-rigged correctly **most of the time**, and a thin landmark-correction UI is enough to recover the rest — without ever leaving the browser.

## 2. Target users

- **Indie and AA game developers** who need faster character setup.
- **3D artists and small studios** preparing bipedal characters at volume.
- **Hobbyist creators** who need a guided rigging workflow without deep Blender setup.

These users are comfortable with FBX/GLB pipelines and game-engine import flows. They are *not* assumed to be Rigify-fluent.

## 3. Core workflow

1. User signs in (or uses the demo-viewing path for shared rigs).
2. User uploads a supported 3D model.
3. Backend creates a `RiggedModel` row and queues the rigging task. The user can navigate away — work continues in the background.
4. User watches progress in the editor (status polling + WebSocket events).
5. User reviews the rigged output and the detected pose classification.
6. If the auto-rig needs correction, the user places 6 landmarks and triggers `/rerig-landmarks/`. The old output keeps serving until the new one lands.
7. User previews uploaded or library animations on the rig.
8. User downloads the rigged GLB and any retargeted animations.

## 4. Functional requirements

### 4.1 Model upload & auto-rigging
- Accept uploads in **FBX, GLB, GLTF, OBJ**. Reject other formats with a clear validation error.
- Preserve original format and file size on the row.
- Accept optional manual orientation overrides (Euler degrees + optional quaternion) for users whose source files load in the wrong basis.
- Run Blender + Rigify with rotation handling, mesh normalization (Z-up, fixed reference height, feet on ground), automatic-weight binding, and GLB export.
- Detect and report the model's pose (`t_pose`, `a_pose`, `arms_down`, `unclear`) with `pose_angle_deg` and `pose_confidence`.
- Produce a downloadable rigged GLB on success.
- Expose `status`, `progress.step`, `progress.pct`, `error_message`, and `rigged_glb_url` via `/rigs/{id}/status/`.
- Push live progress over a per-user Channels WebSocket group (`user_{user_id}`).

### 4.2 Rig editor & landmark adjustment
- Render the rigged model in a Three.js / R3F viewer.
- Let the user place or update **6 named landmarks**: `chin`, `left_wrist`, `right_wrist`, `groin`, `left_ankle`, `right_ankle`.
- Submit landmark updates through `/rerig-landmarks/`; return `202 Accepted` and continue progress reporting via the same status channel.
- Preserve the previous successful `rigged_glb` while the rerig runs and on failure (non-destructive rerig).
- Show enough skeleton/model overlay for the user to verify alignment.

### 4.3 Animation management
- Allow authenticated users to upload **GLB, GLTF, FBX** animations.
- Provide a browsable animation library: approved + public animations, plus the user's own uploads, with categories.
- Retarget or preview animations against a rigged model using `RiggedModel.bone_mapping` (Rigify → Mixamo names).
- Surface clear errors when tracks cannot bind to the rig skeleton (list of unbound bones).

### 4.4 Authentication & accounts
- Email-based login (`USERNAME_FIELD = "email"`).
- JWT auth — 1 h access, 7 d refresh, refresh rotation on.
- Three plan tiers: **Free** (500 MB, 3 rigs), **Pro** ($15/mo, 5 GB, unlimited rigs), **Studio** ($49/mo, 50 GB, team features). Plans are cosmetic until [ROADMAP § Phase 3](ROADMAP.md) lands billing.

## 5. Non-functional requirements

| Area | Requirement |
|---|---|
| **Throttling** | Anonymous: 5 req/min global, **0 uploads** ever. Authenticated: 10 req/min global; rig uploads 10/h; animation uploads 15/h. Status polling unthrottled by design. See [API § Throttle table](API.md#throttle-table). |
| **Resilience** | A failed rerig must not erase a previously valid output. The pipeline saves new files under unique names and only points the row at the new file once it's saved. |
| **Discoverability** | OpenAPI schema served at `/api/schema/`, Swagger at `/api/docs/`, Redoc at `/api/redoc/`. Schema must remain accurate as endpoints change. |
| **Observability** | `RiggedModel.rig_log` captures Blender stdout. `error_message` captures driver-side failures. Both are surfaced to the editor. |
| **Storage** | Filesystem-backed locally; S3 in production when `AWS_BUCKET_NAME` is set. Upload paths use UUID rig IDs (`rigs/<user_id>/<rig_id>/<file>`) so a re-upload never collides with an unrelated user's path. |
| **Security** | Passwords validated by Django's standard validators. JWT secret loaded from `SECRET_KEY` env. CORS will be restricted before production (see [KNOWN_ISSUES](KNOWN_ISSUES.md#cors_allow_all_origins--true)). |
| **Performance** | A single rig completes in **< 90 s** for a 50 k-vertex bipedal mesh on a baseline Docker host (4 vCPU). Status polling round-trips in **< 100 ms**. |

## 6. MVP scope

The MVP is the upload → auto-rig → review path for one bipedal mesh per user, with landmark correction available. Animation retargeting is **stretch** for the MVP — the upload form and library browse should ship, but unbound-track reporting can lag.

What MVP does **not** need:
- Stripe / billing — plans are display-only.
- Storage quota enforcement — `has_quota_for()` exists, just isn't called.
- Real test suite (we know — see [ROADMAP § Phase 1](ROADMAP.md)).
- Studio / team features.

## 7. Acceptance criteria

- ✅ A standard bipedal FBX/GLB/GLTF/OBJ upload creates a `RiggedModel`, transitions through `pending → processing → done`, and exposes a working `rigged_glb_url`.
- ✅ Live progress is observable via either polling `/status/` or subscribing to `user_{user_id}`.
- ✅ A successful Blender run produces a rigged GLB that loads in the editor.
- ✅ Submitting landmarks via `/rerig-landmarks/` returns 202 immediately, the row resets to `pending`, and the previous `rigged_glb` keeps serving until the new one is written.
- ✅ Animation uploads reject unsupported formats with a clear validation message.
- ✅ Animation preview handles GLB/GLTF/FBX sources and reports unbound tracks via the bone map.
- ✅ Anonymous uploads return 429.
- ✅ A user blowing the 10/hour rig upload cap receives a 429 with retry guidance.

## 8. Out of scope (current cycle)

- Quadrupeds, props/non-character rigs, multi-mesh characters with separate outfit pieces.
- Non-Rigify rigging templates.
- Real-time collaborative editing.
- Native desktop builds.
- Mobile-optimized editor.

## 9. Open questions

- How do we want to handle meshes that fail pose detection? Today they get `pose: "unclear"` and proceed; should we hard-block and force the user to use landmarks?
- The Mixamo bone-name target locks us into one retarget vocabulary. Do we expose a second target (Unreal Mannequin / UE5 humanoid) before or after billing?
- Demo-profile rigs (`demo@rigflow.local`) accumulate forever today. Need a TTL or daily cleanup job — track in [ROADMAP](ROADMAP.md).

---

Cross-references:
- [PRODUCT_REQUIREMENTS](PRODUCT_REQUIREMENTS.md) — short summary
- [ARCHITECTURE](ARCHITECTURE.md) — system architecture
- [TECHNICAL_CONTEXT](TECHNICAL_CONTEXT.md) — stack and dependency context
- [API](API.md) — endpoint reference
- [RIGGING_PIPELINE](RIGGING_PIPELINE.md) — Blender pipeline detail
- [ROADMAP](ROADMAP.md) — phase plan
