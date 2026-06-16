# Animation Rework — Milestone 0: Canonical Bone Map + Preview Fix — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the rig's `bone_mapping` the single source of truth for retargeting — complete it with fingers, extract the browser resolver into a testable module, guard client/server parity with tests, and diagnose-and-fix the runtime "0 tracks bound / stretched" preview failure.

**Architecture:** One canonical Mixamo→DEF map is generated at rig-build (`build_bone_map` over `RIGIFY_TO_MIXAMO`) and stored on `RiggedModel.bone_mapping`. Both the Blender baker (later milestones) and the browser preview consume it; hardcoded tables are legacy fallback only. The browser bone-name resolution + sanitization moves out of the React component into a pure `lib/boneMap.ts` so it can be unit-tested and kept in parity with the backend map.

**Tech Stack:** Python 3.12 / Django `SimpleTestCase` (backend, run via `manage.py test`); TypeScript / React 19 / three-stdlib / Vitest (frontend).

**Spec:** [`Docs/specs/2026-06-16-animation-rework-design.md`](../specs/2026-06-16-animation-rework-design.md) (Milestone 0, §5 and §9).

**Path conventions:** All paths are relative to the project source root `rigflow-project/`. Backend commands run from `rigflow-project/backend/`; frontend commands from `rigflow-project/frontend/`. Commit steps assume the project's git repo; if your working tree isn't a repo, commit through whatever VCS the project uses. End commit messages with:
`Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`

---

## File Structure

| File | Responsibility | Action |
|---|---|---|
| `frontend/src/lib/boneMap.ts` | Pure bone-name resolution: `sanitizeBoneName`, `FALLBACK_MIXAMO_TO_DEF`, `heuristicMapping`, `resolveTargetBone`. The single client-side home for the fallback map + matcher. | Create |
| `frontend/src/lib/boneMap.test.ts` | Vitest unit tests: resolution, finger resolution, sanitization round-trip, client-side parity over the canonical map. | Create |
| `frontend/src/components/AnimationPlayer.tsx` | Imports the resolver from `lib/boneMap.ts` instead of defining it inline. No behavior change in this milestone except the diagnosis fix (Task 4). | Modify |
| `backend/scripts/blender_autorig.py` | Extend `RIGIFY_TO_MIXAMO` with 30 finger entries so `build_bone_map` emits a complete map. | Modify |
| `backend/apps/rigging/tests/test_bone_map_sync.py` | Update drift guard: point at the new frontend module, assert the full map (52 entries incl. fingers) stays in parity. | Modify |

---

### Task 1: Extract the browser bone-map resolver into a testable module

No behavior change. Move the pure resolution helpers out of the React component so they can be unit-tested and become the single client-side map home.

**Files:**
- Create: `frontend/src/lib/boneMap.ts`
- Modify: `frontend/src/components/AnimationPlayer.tsx` (remove the moved definitions; import them)
- Modify: `backend/apps/rigging/tests/test_bone_map_sync.py` (repoint `_FRONTEND_SRC`)

- [ ] **Step 1: Create `frontend/src/lib/boneMap.ts` with the moved helpers**

Copy these four definitions **verbatim** out of `AnimationPlayer.tsx` (currently lines 20–143 and 162–164) into a new file, exported:

```ts
// Pure Mixamo/source → Rigify-DEF bone-name resolution. This is the single
// client-side home for the fallback map + heuristic matcher. The rig's saved
// `bone_mapping` is the primary source of truth (see AnimationPlayer); these
// are used only when a rig has no saved mapping (legacy rigs).
//
// Keep FALLBACK_MIXAMO_TO_DEF in parity with RIGIFY_TO_MIXAMO in
// backend/scripts/blender_autorig.py — guarded by
// backend/apps/rigging/tests/test_bone_map_sync.py.

export const FALLBACK_MIXAMO_TO_DEF: Record<string, string> = {
  Hips: "DEF-spine",
  Spine: "DEF-spine.001",
  Spine1: "DEF-spine.002",
  Spine2: "DEF-spine.003",
  Neck: "DEF-spine.004",
  Head: "DEF-spine.005",
  LeftUpLeg: "DEF-thigh.L",
  LeftLeg: "DEF-shin.L",
  LeftFoot: "DEF-foot.L",
  LeftToeBase: "DEF-toe.L",
  RightUpLeg: "DEF-thigh.R",
  RightLeg: "DEF-shin.R",
  RightFoot: "DEF-foot.R",
  RightToeBase: "DEF-toe.R",
  LeftShoulder: "DEF-shoulder.L",
  LeftArm: "DEF-upper_arm.L",
  LeftForeArm: "DEF-forearm.L",
  LeftHand: "DEF-hand.L",
  RightShoulder: "DEF-shoulder.R",
  RightArm: "DEF-upper_arm.R",
  RightForeArm: "DEF-forearm.R",
  RightHand: "DEF-hand.R",
  ...Object.fromEntries(
    (["Left", "Right"] as const).flatMap((s) => {
      const side = s === "Left" ? "L" : "R";
      const fingerMap: Record<string, string> = {
        Thumb: "thumb",
        Index: "f_index",
        Middle: "f_middle",
        Ring: "f_ring",
        Pinky: "f_pinky",
      };
      return Object.entries(fingerMap).flatMap(([mixamo, def]) =>
        [1, 2, 3].map((n) => [
          `${s}Hand${mixamo}${n}`,
          `DEF-${def}.0${n}.${side}`,
        ] as [string, string]),
      );
    }),
  ),
};

// GLTFLoader runs node names through THREE.PropertyBinding.sanitizeNodeName,
// stripping reserved chars (`.`, `:`, `/`, `[`, `]`) and replacing whitespace
// with underscores. Track names need identical treatment or PropertyBinding
// reads a dot in the bone name as a sub-object accessor and silently fails to
// bind. (Root cause of the historical "2/53 tracks bound" bug.)
export function sanitizeBoneName(name: string): string {
  return name.replace(/\s/g, "_").replace(/[[\].:/]/g, "");
}

export function heuristicMapping(rawName: string): string | null {
  // ... move the ENTIRE existing heuristicMapping body verbatim (AnimationPlayer.tsx:72–143)
}

export function resolveTargetBone(
  srcBoneName: string,
  mixamoToDef: Record<string, string>,
): string | null {
  const clean = srcBoneName
    .replace(/^.*[:|]/, "")
    .replace(/^mixamorig\d*/i, "");
  return (
    mixamoToDef[clean] ??
    mixamoToDef[srcBoneName] ??
    FALLBACK_MIXAMO_TO_DEF[clean] ??
    FALLBACK_MIXAMO_TO_DEF[srcBoneName] ??
    heuristicMapping(srcBoneName)
  );
}
```

Move `heuristicMapping`'s full body unchanged — do not paraphrase it. It is the block at `AnimationPlayer.tsx:72–143`.

- [ ] **Step 2: Update `AnimationPlayer.tsx` to import instead of define**

Delete the inline `FALLBACK_MIXAMO_TO_DEF` (lines 20–62), `heuristicMapping` (64–143), `sanitizeBoneName` (162–164), and `resolveTargetBone` (262–276) from `AnimationPlayer.tsx`. Add at the top with the other imports:

```ts
import {
  FALLBACK_MIXAMO_TO_DEF,
  sanitizeBoneName,
  heuristicMapping,
  resolveTargetBone,
} from "@/lib/boneMap";
```

`remapClipToRig` and `buildSourceToTargetNames` stay in the component (they depend on THREE) and now call the imported helpers — no signature change.

- [ ] **Step 3: Repoint the drift-guard test at the new module**

In `backend/apps/rigging/tests/test_bone_map_sync.py`, change `_FRONTEND_SRC`:

```python
_FRONTEND_SRC = _REPO_ROOT / "frontend" / "src" / "lib" / "boneMap.ts"
```

The regex blocks that parse `FALLBACK_MIXAMO_TO_DEF` and the finger comment still apply — the const moved unchanged.

- [ ] **Step 4: Typecheck, lint, and run the drift guard**

```bash
cd frontend && npx tsc --noEmit && npx eslint src/components/AnimationPlayer.tsx src/lib/boneMap.ts
```
Expected: clean.

```bash
cd backend && python manage.py test apps.rigging.tests.test_bone_map_sync -v 2
```
Expected: 3 tests PASS (still 22 explicit entries; map content unchanged).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/boneMap.ts frontend/src/components/AnimationPlayer.tsx backend/apps/rigging/tests/test_bone_map_sync.py
git commit -m "refactor(anim): extract bone-map resolver into lib/boneMap.ts

No behavior change; makes the client resolver unit-testable and gives the
fallback map a single home. Repoints test_bone_map_sync at the new module.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: Complete the canonical bone map with fingers (backend)

The server `RIGIFY_TO_MIXAMO` has 22 entries and no fingers; the client already maps 30 finger bones. Add them so `build_bone_map` emits a complete map into `RiggedModel.bone_mapping`. TDD via the drift-guard test.

**Files:**
- Modify: `backend/apps/rigging/tests/test_bone_map_sync.py` (assert fingers present — red first)
- Modify: `backend/scripts/blender_autorig.py` (add 30 finger entries — green)

- [ ] **Step 1: Add the failing finger-parity assertions to the test**

In `backend/apps/rigging/tests/test_bone_map_sync.py`, add this helper and test class method (and update the count assertions). The expected finger set is generated by the same rule the frontend uses:

```python
def _expected_finger_pairs() -> dict:
    """{DEF-bone: Mixamo} for the 30 finger entries, mirroring the rule the
    frontend uses to generate FALLBACK_MIXAMO_TO_DEF finger keys."""
    finger_map = {
        "Thumb": "thumb", "Index": "f_index", "Middle": "f_middle",
        "Ring": "f_ring", "Pinky": "f_pinky",
    }
    out = {}
    for word, side in (("Left", "L"), ("Right", "R")):
        for mixamo_finger, def_finger in finger_map.items():
            for n in (1, 2, 3):
                mixamo = f"{word}Hand{mixamo_finger}{n}"
                def_bone = f"DEF-{def_finger}.0{n}.{side}"
                out[def_bone] = mixamo
    return out
```

Replace the existing count test and add a finger test:

```python
    def test_backend_map_has_expected_entry_count(self):
        # 22 explicit (spine/limbs) + 30 fingers = 52
        self.assertEqual(len(_backend_rigify_to_mixamo()), 52)

    def test_backend_map_includes_all_finger_bones(self):
        backend = _backend_rigify_to_mixamo()
        for def_bone, mixamo in _expected_finger_pairs().items():
            self.assertEqual(
                backend.get(def_bone), mixamo,
                f"RIGIFY_TO_MIXAMO is missing/incorrect finger entry {def_bone}",
            )
```

Leave `test_frontend_explicit_map_has_expected_entry_count` (22) and `test_maps_are_exact_inverses` as-is — they cover the explicit block, which is unchanged.

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd backend && python manage.py test apps.rigging.tests.test_bone_map_sync -v 2
```
Expected: FAIL — `test_backend_map_has_expected_entry_count` (got 22, want 52) and `test_backend_map_includes_all_finger_bones`.

- [ ] **Step 3: Add the 30 finger entries to `RIGIFY_TO_MIXAMO`**

In `backend/scripts/blender_autorig.py`, inside the `RIGIFY_TO_MIXAMO` dict (ends at line 1583, before the closing `}`), append:

```python
    # Fingers — mirrors the frontend FALLBACK_MIXAMO_TO_DEF finger block.
    # Rigify DEF finger bones: DEF-<finger>.0<segment>.<side>.
    "DEF-thumb.01.L":    "LeftHandThumb1",
    "DEF-thumb.02.L":    "LeftHandThumb2",
    "DEF-thumb.03.L":    "LeftHandThumb3",
    "DEF-f_index.01.L":  "LeftHandIndex1",
    "DEF-f_index.02.L":  "LeftHandIndex2",
    "DEF-f_index.03.L":  "LeftHandIndex3",
    "DEF-f_middle.01.L": "LeftHandMiddle1",
    "DEF-f_middle.02.L": "LeftHandMiddle2",
    "DEF-f_middle.03.L": "LeftHandMiddle3",
    "DEF-f_ring.01.L":   "LeftHandRing1",
    "DEF-f_ring.02.L":   "LeftHandRing2",
    "DEF-f_ring.03.L":   "LeftHandRing3",
    "DEF-f_pinky.01.L":  "LeftHandPinky1",
    "DEF-f_pinky.02.L":  "LeftHandPinky2",
    "DEF-f_pinky.03.L":  "LeftHandPinky3",
    "DEF-thumb.01.R":    "RightHandThumb1",
    "DEF-thumb.02.R":    "RightHandThumb2",
    "DEF-thumb.03.R":    "RightHandThumb3",
    "DEF-f_index.01.R":  "RightHandIndex1",
    "DEF-f_index.02.R":  "RightHandIndex2",
    "DEF-f_index.03.R":  "RightHandIndex3",
    "DEF-f_middle.01.R": "RightHandMiddle1",
    "DEF-f_middle.02.R": "RightHandMiddle2",
    "DEF-f_middle.03.R": "RightHandMiddle3",
    "DEF-f_ring.01.R":   "RightHandRing1",
    "DEF-f_ring.02.R":   "RightHandRing2",
    "DEF-f_ring.03.R":   "RightHandRing3",
    "DEF-f_pinky.01.R":  "RightHandPinky1",
    "DEF-f_pinky.02.R":  "RightHandPinky2",
    "DEF-f_pinky.03.R":  "RightHandPinky3",
```

`build_bone_map` (line 1586) iterates `rig.data.bones` and emits any whose name is in `RIGIFY_TO_MIXAMO`, so the fingers now flow into `bone_mapping` automatically for any rig whose DEF skeleton has them — no other change needed.

- [ ] **Step 4: Run the test to verify it passes**

```bash
cd backend && python manage.py test apps.rigging.tests.test_bone_map_sync -v 2
```
Expected: all PASS (52 entries; fingers present; explicit block still inverts the frontend).

- [ ] **Step 5: Commit**

```bash
git add backend/scripts/blender_autorig.py backend/apps/rigging/tests/test_bone_map_sync.py
git commit -m "feat(anim): add finger bones to RIGIFY_TO_MIXAMO (complete canonical map)

build_bone_map now emits all 30 finger mappings into RiggedModel.bone_mapping,
closing the client/server finger gap. Drift guard extended to 52 entries.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

> **Note:** existing rigs in the DB keep their old finger-less `bone_mapping` until re-rigged. That's acceptable — the preview falls back to `FALLBACK_MIXAMO_TO_DEF` (which has fingers) for those rigs. New/re-rigged models get fingers in `bone_mapping` directly.

---

### Task 3: Vitest tests for the bone-map resolver (parity + sanitization)

Lock the client resolver's correctness and the sanitization round-trip that caused the historical 0-bind bug.

**Files:**
- Create: `frontend/src/lib/boneMap.test.ts`

- [ ] **Step 1: Write the tests**

Create `frontend/src/lib/boneMap.test.ts`:

```ts
import { describe, it, expect } from "vitest";
import {
  FALLBACK_MIXAMO_TO_DEF,
  sanitizeBoneName,
  resolveTargetBone,
} from "./boneMap";

describe("sanitizeBoneName", () => {
  it("strips reserved chars three.js PropertyBinding would choke on", () => {
    expect(sanitizeBoneName("DEF-spine.001")).toBe("DEF-spine001");
    expect(sanitizeBoneName("DEF-shoulder.L")).toBe("DEF-shoulderL");
    expect(sanitizeBoneName("DEF-f_index.01.L")).toBe("DEF-f_index01L");
  });
  it("leaves a dot-free name unchanged", () => {
    expect(sanitizeBoneName("DEF-spine")).toBe("DEF-spine");
  });
  it("is idempotent (sanitizing twice == once)", () => {
    const once = sanitizeBoneName("DEF-thumb.02.R");
    expect(sanitizeBoneName(once)).toBe(once);
  });
});

describe("resolveTargetBone", () => {
  it("resolves a Mixamo namespaced bone via the rig's saved map", () => {
    // Rig bone_mapping is {Mixamo: DEF}; passed as the first arg.
    expect(resolveTargetBone("mixamorig:Hips", { Hips: "DEF-spine" }))
      .toBe("DEF-spine");
  });
  it("falls back to FALLBACK_MIXAMO_TO_DEF when the rig map lacks the bone", () => {
    expect(resolveTargetBone("mixamorig:LeftHand", {})).toBe("DEF-hand.L");
  });
  it("resolves finger bones from the fallback map", () => {
    expect(resolveTargetBone("mixamorig:LeftHandIndex1", {}))
      .toBe("DEF-f_index.01.L");
  });
  it("returns null for an unmappable control bone", () => {
    expect(resolveTargetBone("IK_Target_Foot", {})).toBeNull();
  });
});

describe("client/server parity (sanitization round-trip)", () => {
  it("every fallback DEF target survives sanitization without collapsing", () => {
    // Distinct DEF names must stay distinct after sanitization, else two
    // tracks bind to the same node and the rig tears.
    const sanitized = Object.values(FALLBACK_MIXAMO_TO_DEF).map(sanitizeBoneName);
    expect(new Set(sanitized).size).toBe(sanitized.length);
  });
  it("has 52 entries (22 explicit + 30 fingers) matching the backend map", () => {
    expect(Object.keys(FALLBACK_MIXAMO_TO_DEF).length).toBe(52);
  });
});
```

- [ ] **Step 2: Run the tests**

```bash
cd frontend && npx vitest run src/lib/boneMap.test.ts
```
Expected: all PASS. If "52 entries" fails, the fallback map drifted from the backend — reconcile before proceeding.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/lib/boneMap.test.ts
git commit -m "test(anim): unit-test bone-map resolver + sanitization round-trip

Guards the dots-in-names footgun (historical 0-bind bug) and asserts the
client fallback map stays at 52 entries in parity with the backend.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: Diagnose and fix the runtime "0 tracks / stretched" preview failure

> **REQUIRED SUB-SKILL:** Use superpowers:systematic-debugging for this task. The exact fix depends on observed data — do **not** guess-patch. Reproduce first, find the specific failing point, then apply the targeted fix. The investigation steps below are concrete; the fix step lists the most likely causes with real code, applied conditionally on what you observe.

**Files:**
- Modify: `frontend/src/components/AnimationPlayer.tsx` (fix applied per findings)

- [ ] **Step 1: Reproduce with instrumentation already in the code**

Run the stack (`docker compose -f docker/docker-compose.yml up -d --build`, or backend+frontend dev servers per [`DEVELOPMENT.md`](../DEVELOPMENT.md)). Open a `done` rig in `/editor/<id>`, open the browser console, and select a library animation. `AnimationPlayer.tsx` already logs:
- the rig's loaded bone names (`Rig loaded with N bones:` — line ~396),
- the clip's track count (line ~429),
- the retarget pair count and result (lines ~447, ~473),
- `N/total tracks bound` + the unbound track names (lines ~327–336).

Record three things: (a) the rig's actual loaded bone names, (b) whether the `usedRetarget` path or the fallback ran, (c) the unbound track names.

- [ ] **Step 2: Localize the failure to one of these documented points**

Compare (a) vs (c):
- **Loaded rig bones are NOT `DEF-*` names** (e.g. they're `mixamorig*`, `Armature|*`, or original FBX names) → the rigged GLB wasn't stripped to DEF bones, or the rig URL is a pre-Blender passthrough file. The map can never match. Fix is upstream (re-rig); confirm by re-rigging a model and retrying.
- **Loaded rig bones ARE `DEF-spine001` etc., tracks resolve to `DEF-spine001.quaternion`, but still 0 bound** → a sanitization/casing mismatch between track name and node name. Diff the exact strings.
- **`buildSourceToTargetNames` produced 0 pairs** (retarget pair count log = 0) → the source clip's bones don't resolve (DEF-named source, or `boneMapping` empty AND names not Mixamo). Then the fallback `remapClipToRig` runs; check its remapped/kept/dropped counts.
- **`finalClip.tracks.length` > 0 but bound = 0** → track names don't match any node: the binding-name bug.
- **Stretched, not zero** → tracks bind but rest-pose/scale is wrong: see Step 4.

- [ ] **Step 3: Apply the targeted binding fix**

Apply the fix that matches the localized cause. The most likely, with concrete code:

*If pairs resolve but track names don't match nodes* — ensure the retarget output is sanitized to match the loaded (sanitized) rig nodes. After the `retargetClip` call, normalize track names before filtering:

```ts
const rotOnly = retargeted.tracks
  .filter((t) => t.name.endsWith(".quaternion"))
  .map((t) => {
    const dot = t.name.lastIndexOf(".");
    const bone = t.name.slice(0, dot);
    const prop = t.name.slice(dot + 1);
    const nt = t.clone();
    nt.name = `${sanitizeBoneName(bone)}.${prop}`;
    return nt;
  });
```

*If `boneMapping` arrives empty* (older rig) and that's the cause — confirm the editor passes it (`editor/[modelId]/page.tsx:55` sets `boneMapping`); if empty, re-rig so Task 2's complete map is saved. No code change, document in the retarget report later (Milestone 1).

- [ ] **Step 4: Address "stretched" if tracks now bind but the pose is wrong**

If binding is fixed but limbs stretch/distort, the cause is the source/target rest-pose mismatch interacting with the per-axis auto-fit scale. The auto-fit at `AnimationPlayer.tsx:378–390` scales the rig by `TARGET_HEIGHT / max(size)`. Confirm rotation-only tracks are applied (position/scale already dropped). If distortion remains, capture it as a known limitation to be solved correctly by the **server bake** in Milestone 1 (rest-pose-aware world-rotation transfer) rather than over-investing in the browser path — note it in the milestone handoff. Do **not** add a speculative client rest-pose solver (out of scope per spec §3).

- [ ] **Step 5: Verify and commit**

Re-run the same rig+clip; confirm the on-screen status reads `Playing · N/total tracks bound` with N > 0 and the character animates. Run the frontend test suite:

```bash
cd frontend && npx vitest run && npx tsc --noEmit
```
Expected: green.

```bash
git add frontend/src/components/AnimationPlayer.tsx
git commit -m "fix(anim): bind retargeted tracks to the rig (preview no longer 0/total)

<one line naming the actual root cause found in Step 2>.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Self-Review

**Spec coverage (Milestone 0, spec §5 + §9):**
- Complete `RIGIFY_TO_MIXAMO` with fingers → Task 2 ✓
- Both sides consume `rig.bone_mapping` as primary truth → already true in preview (`resolveTargetBone` checks the passed map first); fingers now flow via Task 2; legacy fallback retained ✓
- Parity golden test → Task 2 (backend drift guard, 52 entries + finger set) + Task 3 (client-side parity/sanitization) ✓
- Sanitization round-trip guard (the "2/53"/"0 bound" footgun) → Task 3 ✓
- Diagnose the 0-tracks/stretch root cause → Task 4 ✓
- Make the resolver testable (it lived in a `.tsx` component) → Task 1 extraction ✓

**Placeholder scan:** Task 1 Step 1 says "move `heuristicMapping`'s full body verbatim" rather than reprinting 70 lines — this is an explicit move-unchanged instruction with the exact source line range, not a vague placeholder. Task 4 is intentionally investigation-first (gated on the systematic-debugging skill) because the precise fix depends on observed data; it lists concrete causes and real fix code per branch rather than a blanket "handle it." No "TBD"/"TODO" remain.

**Type consistency:** `resolveTargetBone(srcBoneName, mixamoToDef)`, `sanitizeBoneName(name)`, `FALLBACK_MIXAMO_TO_DEF`, `heuristicMapping(rawName)` keep identical signatures across `boneMap.ts`, its test, and `AnimationPlayer.tsx`'s remaining callers. The 52-entry count is asserted identically on both sides (backend Task 2, frontend Task 3). DEF finger naming `DEF-<finger>.0<n>.<side>` matches between the backend additions and the frontend generation rule.

---

## Execution Handoff

Plan saved to `Docs/plans/2026-06-16-animation-rework-m0.md`. Two execution options:

**1. Subagent-Driven (recommended)** — a fresh subagent per task with review between tasks. Note Task 4 needs the running app + browser console, so it's best done interactively rather than by a subagent.

**2. Inline Execution** — execute Tasks 1–3 here with checkpoints; do Task 4 interactively against the running stack.

Which approach?
