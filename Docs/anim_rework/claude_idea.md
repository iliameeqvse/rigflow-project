# RigFlow Animation Rework: Proposal & Hypothesis (Claude)

**Author**: Claude (Opus 4.8)
**Date**: June 16, 2026
**Context**: A second, independent take on the animation/retargeting rework. Written after reading the actual code, so part of its job is to correct a few assumptions in [`agy_idea.md`](./agy_idea.md) and re-rank the work by leverage.

> **Scope note / assumption**: I read this as the *3D character-animation & retargeting pipeline* (Mixamo-style clips → our Rigify rig → preview → export), matching `agy_idea.md`. It is **not** about UI motion design (framer-motion transitions), even though that library is present. If you actually meant website/UX animation, stop here and tell me — the rest of this doc is the wrong target.

---

## 1. Hypothesis

> **The core problem isn't preview fidelity — it's that retargeting is trapped in the browser and discarded on download. The highest-leverage rework is to make Blender the single source of truth for retargeting *and* baking, expose it through the two server endpoints the frontend already calls but that don't exist yet, and keep the existing three.js path as a disposable preview only. Everything else (root motion, rest-pose tuning, skinning) is secondary and should be right-sized, not rebuilt.**

The failure mode to design *against* is **two divergent retargeting implementations** (client three.js vs. server Blender) that drift apart. We already have the first symptom of that drift in the codebase today (see §2.4). agy's "dual-layer" plan is directionally right but, as written, *institutionalizes* this drift instead of preventing it. Preventing it is the whole game.

---

## 2. What the code actually does (ground truth)

I verified each of these against the source rather than inferring from symptoms. This matters because two of agy's premises are overstated, which changes the priorities.

### 2.1 The exported asset has zero animation — this is the real gap ✅
`export_glb()` hard-codes `export_animations=False` ([`blender_autorig.py:1551`](../../backend/scripts/blender_autorig.py)). The editor's "Download GLB" is a plain static-file link ([`editor/[modelId]/page.tsx:246`](../../frontend/src/app/editor/%5BmodelId%5D/page.tsx)). So a user can spend time previewing a perfect walk cycle, hit download, and get a **static T-pose**. The entire retargeting effort is browser-only and thrown away. *This is the single most valuable thing to fix, and it's the thing agy buries under root-motion and voxel skinning.*

### 2.2 The preview already does world-space retargeting (agy overstates this problem) ⚠️
agy frames the current state as "Direct Rotation Mapping" that ignores rest-pose. In reality the **primary** path is `SkeletonUtils.retargetClip(...)` ([`AnimationPlayer.tsx:456`](../../frontend/src/components/AnimationPlayer.tsx)), which samples *world* rotations per frame and re-derives target-local rotations — this already corrects bone-roll and most A-pose/T-pose mismatch. The "direct quaternion copy" is only the **fallback** when retarget throws ([`:487`](../../frontend/src/components/AnimationPlayer.tsx)). So agy's section C ("Active Rest-Pose Calibration") is **mostly already implemented** for preview. The real rest-pose gap is making the *server* bake agree with it.

### 2.3 Root motion is genuinely stripped (agy correct) ✅
Position/scale tracks are dropped in both paths ([`:193`](../../frontend/src/components/AnimationPlayer.tsx) and [`:464`](../../frontend/src/components/AnimationPlayer.tsx)). Characters animate in place. Adding scale-normalized root motion is real net-new work — but it's a *preview-nicety + export-correctness* feature, not the bottleneck.

### 2.4 The bone map already diverges — proof the drift risk is real 🚨
The server map `RIGIFY_TO_MIXAMO` ([`:1560`](../../backend/scripts/blender_autorig.py)) has **22 entries and no fingers**. The client `FALLBACK_MIXAMO_TO_DEF` ([`AnimationPlayer.tsx:20`](../../frontend/src/components/AnimationPlayer.tsx)) **does** include fingers, plus a whole heuristic matcher the server has no equivalent of. There's already a `test_bone_map_sync.py` guarding part of this — which tells you the team has *already been bitten* by client/server map drift. Adding a second retargeting engine multiplies this surface.

### 2.5 The frontend is already scaffolded for the server pipeline — but the backend is empty 🔌
`api.ts` exports `retargetAnimation()` → `POST /animations/{id}/retarget/` ([`:210`](../../frontend/src/lib/api.ts)) and `exportProject()` → `POST /projects/{id}/export/` ([`:228`](../../frontend/src/lib/api.ts)). **Neither endpoint exists** — `animations/views.py` has only list/upload/categories, and `projects/views.py`/`urls.py` have no export route. So the dual-layer architecture is half-drawn on the client and absent on the server. Wiring these is the concrete Step 1, and it means the *client contract is already chosen for us*.

### 2.6 Skinning fallback is already decent (agy overstates this too) ⚠️
agy proposes a voxel/geodesic skinning solver to replace a "simplistic Euclidean nearest-bone" fallback. But the fallback is already `patch_orphan_vertex_weights` ([`:1397`](../../backend/scripts/blender_autorig.py)): K-nearest deform bones with a `1/dist^P` soft falloff, explicitly written to kill the rigid faceting of the old single-bone approach. A voxel geodesic solver is a multi-week research task for a marginal gain over what exists. **Out of scope** for this rework.

---

## 3. The best ideas (right-sized, ranked by leverage)

### A. Server-side bake = single source of truth *(highest leverage)*
Implement `POST /projects/{id}/export/` as a Celery task that runs Blender headless: load the rig GLB, import the selected clip(s), retarget with **native constraints** (`Copy Rotation`/`Copy Location` onto `DEF-` bones), `nla.bake` to keyframes, export GLB/FBX with `export_animations=True`. This is the asset users actually take to Unity/Unreal/Godot. It reuses the Blender subprocess harness that already exists in [`tasks.py`](../../backend/apps/rigging/tasks.py) (`_blender_call`, timeout, WS progress via `push_ws`).

### B. One bone map, generated — not two hand-maintained ones *(de-risks everything)*
Promote the bone mapping to a **single canonical artifact** emitted at rig-build time (it's already written to JSON via `build_bone_map` → the rig's `bone_mapping` field). The Blender baker and the three.js preview must **both consume that same JSON** — neither should carry its own hardcoded table. The current `FALLBACK_*`/`RIGIFY_TO_MIXAMO` dicts become *seed data for generation*, not runtime truth. Add a golden-file test asserting client and server resolve an identical map for a reference rig. This directly attacks the §2.4 drift.

### C. Make the preview a thin client of the bake, eventually *(convergence)*
Short term, keep `retargetClip` for instant preview. Medium term, the "best result" is for the preview to play the *same baked clip the server produces* (request a cached server bake, stream the GLB back, play it). Then preview and export are the *same code path* — zero drift by construction. This is the opposite of agy's "two independent layers" and is the single most important architectural choice in this doc.

### D. Scale-normalized root motion — by leg length, not total height
Keep root translation on the hips, scaled by the **leg-length ratio** (hip-to-foot), not total character height. Total-height scaling (agy's formula in §3.A) skids feet whenever proportions differ (big head, long torso). Apply in both the preview remap and the Blender bake so they agree. This is a small, well-bounded feature — do it *after* A/B land.

### E. Capability reporting instead of silent failure
The preview already surfaces "N/total tracks bound" ([`:517`](../../frontend/src/components/AnimationPlayer.tsx)) — excellent. Extend the same honesty to export: the bake result should report which bones/clips mapped, what was dropped, and whether root motion was applied, so a partial retarget is *visible*, not a silent mystery.

---

## 4. Where I disagree with `agy_idea.md`

| agy's claim | My finding | Consequence |
| :-- | :-- | :-- |
| Current preview is "Direct Rotation Mapping", needs rest-pose calibration (§C) | `retargetClip` world-sampling is already the primary path; direct copy is only the fallback | Rest-pose calibration is largely **done for preview**; effort belongs in the *server* bake instead |
| Skinning fallback is "simplistic Euclidean nearest-bone"; build voxel geodesic solver (§D) | Fallback is already K-nearest soft-falloff (`patch_orphan_vertex_weights`) | Voxel solver is **over-engineering**; cut it from scope |
| Dual independent layers (client preview + server bake) | Two independent retargeting engines = guaranteed drift; we already see bone-map drift today | Make them **converge** (idea C), don't run them in parallel forever |
| Root motion scaled by total character height | Total height skids feet on mismatched proportions | Scale by **leg length** |
| (not mentioned) | `retarget`/`export` endpoints are called by the client but don't exist on the server | That's literally **Step 1**, and the client contract is already fixed |
| (not mentioned) | Server bone map has **no fingers**, client does | Finger/hand retarget silently degrades on the server path |

Net: agy and I agree on the *destination* (server bake, root motion, engine-ready export). We disagree on the *bottleneck* and on how much to build. agy reranks fidelity tweaks above portability and proposes two heavy net-new systems (voxel skinning, parallel rest-pose calibration) that the code mostly already handles. I'd ship the portability spine first and right-size the rest.

---

## 5. Errors & risks we'll actually face

| Risk | Why it bites | Mitigation |
| :-- | :-- | :-- |
| **Client/server retarget drift** (the big one) | Two engines, two bone maps, two rest-pose conventions → preview looks right, export looks wrong, users lose trust | Single generated bone map (idea B); converge preview onto server bake (idea C); golden-file parity test |
| **Blender bake latency/cost** | Headless bake of long clips is CPU/RAM heavy; multiple users queue up | Celery queue + per-user rate limit (harness exists in `tasks.py`); cache baked clips keyed by (rig hash, clip id, options); the 600s subprocess timeout already there |
| **Rest-pose mismatch on the *server*** | Native constraints assume the rig's rest pose; Rigify `DEF-` rolls differ from game-engine norms | Bake a canonical rest pose at rig-build and store rest offsets in GLB `extras`; the baker reads them, so client & server share calibration |
| **`PropertyBinding` name sanitization** | Already a known footgun — dots in `DEF-spine.001` silently unbind tracks (caused the "2/53 bound" bug, see `sanitizeBoneName` comment [`:152`](../../frontend/src/components/AnimationPlayer.tsx)) | Whatever the server exports must round-trip through the *same* sanitization the loader applies; assert it in the parity test |
| **Foot sliding after root motion** | Stride length ≠ scaled translation | Leg-length scaling first; optional IK foot-lock as a later, separate task — not in v1 |
| **Finger gap on server map** | `RIGIFY_TO_MIXAMO` omits fingers; baked exports lose hand animation | Generate the full map (idea B) so fingers come for free from the client's existing finger table |
| **FBX export** | `exportProject` offers `"fbx"` but Blender FBX export has its own axis/scale quirks distinct from GLB | Ship **GLB first**, treat FBX as a fast-follow with its own test fixture |

---

## 6. Proposed sequencing (thin spine first)

1. **Wire the contract that already exists.** Implement `POST /projects/{id}/export/` (and decide whether `/animations/{id}/retarget/` is needed or folds into export). Return a `download_url` to a baked GLB. Reuse the `tasks.py` Blender harness + WS progress.
2. **Single bone map.** Generate one canonical map at rig build; make both the baker and the preview consume it. Add the parity golden test. Backfill fingers into the server side.
3. **Server bake path.** Import clip → constraint retarget onto `DEF-` bones → `nla.bake` → export with `export_animations=True`. GLB only.
4. **Root motion (leg-length scaled).** Apply identically in preview remap and bake.
5. **Converge preview onto bake** (idea C) for zero-drift, once 1–4 are stable.
6. **FBX + IK foot-lock** as separate fast-follows.

> **One-line recommendation**: Don't start with fidelity tweaks. Start by making the retarget *leave the browser* — implement the export bake behind the endpoints the frontend already calls, anchored to a single generated bone map. That delivers the actual product value (engine-ready animated assets) and structurally prevents the drift that two parallel engines would otherwise guarantee.

---

*Open questions for you before any implementation:* (1) Is "engine-ready animated export" the actual goal, or is in-browser preview polish the priority? (2) One clip per export, or multi-clip bundles / NLA tracks? (3) Must we keep instant client preview, or is a few-seconds server bake acceptable for preview too (which would let us collapse to one code path)?
