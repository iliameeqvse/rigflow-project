# RigFlow Roadmap

Last updated: 2026-05-04.

Items are checked off when merged. When you complete an item, tick it here in the same PR.

## Phase 1 — Stability & Foundation (current)

Goal: get the existing surface trustworthy. No new product scope until these are done.

- [ ] Stabilize Rigify automation for non-T-pose meshes (currently pose detection drops to `unclear` more than it should).
- [ ] Fix animation player latency in the editor (large GLBs stutter on first track switch).
- [ ] Finalize landmark editing UX — fewer modes, clearer marker hit-testing.
- [ ] **Deduplicate `apps/throttles.py`** — the file is appended to itself; clean it up and verify each throttle scope still binds. ([KNOWN_ISSUES](KNOWN_ISSUES.md#appsthrottlespy-is-duplicated))
- [ ] **Move the misnamed SSH key** at the repo-root `requirements.txt` into a secret store. ([KNOWN_ISSUES](KNOWN_ISSUES.md#requirementstxt-at-the-repo-root-is-an-ssh-private-key))
- [ ] Add a baseline test suite: upload format validation, throttle behaviour, rerig-preserves-old-GLB invariant. ([KNOWN_ISSUES](KNOWN_ISSUES.md#no-real-test-suite))
- [ ] Wire CI (run tests on PR, run `npm run lint`, run `python manage.py check`).
- [ ] Reconcile the working tree with the git root layout, or document the nested-source layout in the README so `git status` stops looking broken. ([KNOWN_ISSUES](KNOWN_ISSUES.md#repo-layout))
- [ ] Add a daily cleanup job for demo-profile rigs (`demo@rigflow.local`) — they accumulate forever today.

## Phase 2 — UI overhaul & integration

Goal: ship a credible second-pass UI and tighten security posture before opening signups.

- [ ] Implement the "10k" UI redesign across upload, editor, and animation pages.
- [ ] Build a refined 3D model upload + viewer flow with drag-drop and inline format detection.
- [ ] Improve rig landmark precision (snap-to-vertex, mirror-from-other-side).
- [ ] **Enforce storage quota on upload.** `UserProfile.has_quota_for()` exists but is never called — wire it into `RiggedModelViewSet.create` and `AnimationListOrUploadView.post`. ([KNOWN_ISSUES](KNOWN_ISSUES.md#storage-quota-is-not-enforced))
- [ ] **Tighten CORS.** Replace `CORS_ALLOW_ALL_ORIGINS = True` with a real allowlist. ([KNOWN_ISSUES](KNOWN_ISSUES.md#cors_allow_all_origins--true))
- [ ] Add S3 presigned-download URLs for `rigged_glb` so we don't proxy large files through Daphne in production.
- [ ] Refresh-token blacklist on rotation (`BLACKLIST_AFTER_ROTATION = True`) before opening public signups.

## Phase 3 — Advanced features

Goal: pricing, retargeting depth, and asset library.

- [ ] **Stripe checkout** for Pro / Studio plans. Wire `UserProfile.stripe_customer_id` and a webhook for plan changes. ([KNOWN_ISSUES](KNOWN_ISSUES.md#stripe--payments-are-stubs))
- [ ] Expanded animation format support: BVH import, root-motion handling.
- [ ] Cloud-based user animation library (cross-rig retargeting with cached results).
- [ ] Advanced character skinning controls — weight painting overrides for problem joints.
- [ ] Second retarget vocabulary (Unreal Mannequin / UE5 humanoid) alongside Mixamo.

## How to use this roadmap

- When prompting Claude / Codex / Gemini for help, reference the current phase: *"I'm working on Phase 2 — implement [feature]. The relevant docs are [links]."*
- Each item should link to the relevant doc(s) when it lands so a future reader can trace why a change was made.
- If you discover a new gotcha, add it to [KNOWN_ISSUES](KNOWN_ISSUES.md) **and** add a checklist item here if it should actually be fixed.
