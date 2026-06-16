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
  // Mixamo finger naming → Rigify DEF finger naming
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

// Heuristic name-matcher for clips whose bone names follow none of the
// known conventions. Handles patterns like:
//   R_Clavicle_Bn  → DEF-shoulder.R
//   L_Arm_01_Bn    → DEF-upper_arm.L  (01/02/03 = upper/fore/hand)
//   R_Leg_02_Bn    → DEF-shin.R       (01/02/03 = thigh/shin/foot)
//   Neck_Bn        → DEF-spine.004
//   spine_03       → DEF-spine.003
// Returns null when nothing plausible matches (e.g. effect/IK-target bones).
export function heuristicMapping(rawName: string): string | null {
  const stripped = rawName
    .replace(/^.*[:|]/, "")                        // strip Mixamo/Blender ns prefix
    .replace(/^mixamorig\d*/i, "")                  // strip no-separator Mixamo prefix
    .replace(/_(?:bn|bone|jnt|joint|ctrl|grp)$/i, "")  // strip common suffixes
    .toLowerCase();

  let side: "L" | "R" | "" = "";
  let core = stripped;
  // Side detection: prefix or suffix
  let m = core.match(/^(l|left|r|right)[_.-]/);
  if (m) {
    side = m[1].startsWith("l") ? "L" : "R";
    core = core.slice(m[0].length);
  } else {
    m = core.match(/[_.-](l|left|r|right)$/);
    if (m) {
      side = m[1].startsWith("l") ? "L" : "R";
      core = core.slice(0, -m[0].length);
    }
  }

  // Skip control / effect bones we explicitly don't want to drive.
  if (/ik[_.]?target|effect|lightning|glow|mask|prop|cape|cloth/i.test(core)) {
    return null;
  }

  // Numbered limb segments: arm_01/02/03 or leg_01/02/03
  const limbNum = core.match(/(arm|leg)[_.-]?0?(\d+)$/);
  if (limbNum && side) {
    const part = limbNum[1];
    const idx = parseInt(limbNum[2], 10);
    if (part === "arm") {
      if (idx === 1) return `DEF-upper_arm.${side}`;
      if (idx === 2) return `DEF-forearm.${side}`;
      if (idx === 3) return `DEF-hand.${side}`;
    }
    if (part === "leg") {
      if (idx === 1) return `DEF-thigh.${side}`;
      if (idx === 2) return `DEF-shin.${side}`;
      if (idx === 3) return `DEF-foot.${side}`;
    }
  }

  // Numbered spine segments: spine_01/02/03
  const spineNum = core.match(/^spine[_.-]?0?(\d+)$/);
  if (spineNum) {
    const idx = parseInt(spineNum[1], 10);
    if (idx >= 1 && idx <= 5) return `DEF-spine.00${idx}`;
  }

  // Plain torso keywords
  if (/^(hips?|pelvis|root)$/.test(core)) return "DEF-spine";
  if (/^spine$/.test(core)) return "DEF-spine.001";
  if (/^(chest|spine1|upper_?body)$/.test(core)) return "DEF-spine.002";
  if (/^(upper_?chest|spine2)$/.test(core)) return "DEF-spine.003";
  if (/^neck/.test(core)) return "DEF-spine.004";
  if (/^head/.test(core)) return "DEF-spine.005";

  // Side-specific limbs (no number)
  if (!side) return null;
  if (/^(clavicle|shoulder)/.test(core))           return `DEF-shoulder.${side}`;
  if (/^(upper_?arm|arm)$/.test(core))             return `DEF-upper_arm.${side}`;
  if (/^(forearm|lower_?arm|elbow)$/.test(core))   return `DEF-forearm.${side}`;
  if (/^(hand|wrist|palm)$/.test(core))            return `DEF-hand.${side}`;
  if (/^(thigh|upper_?leg|upleg|hip_joint)$/.test(core)) return `DEF-thigh.${side}`;
  if (/^(shin|lower_?leg|calf|knee)$/.test(core))  return `DEF-shin.${side}`;
  if (/^(foot|ankle)/.test(core))                  return `DEF-foot.${side}`;
  if (/^(toe|ball)/.test(core))                    return `DEF-toe.${side}`;

  return null;
}

// GLTFLoader runs every loaded node name through
// THREE.PropertyBinding.sanitizeNodeName, which strips reserved characters
// (`.`, `:`, `/`, `[`, `]`) and replaces whitespace with underscores. So a
// Blender bone like "DEF-spine.001" becomes "DEF-spine001" in the loaded
// rig, "DEF-shoulder.L" becomes "DEF-shoulderL", "DEF-thumb.01.L" becomes
// "DEF-thumb01L". Track names need the same treatment — otherwise
// PropertyBinding.parseTrackName reads the dot inside the bone name as a
// sub-object accessor and the track silently fails to bind. (This was
// the cause of "2/53 tracks bound" — only DEF-spine, the one bone with
// no inner dot, survived round-trip unchanged.)
export function sanitizeBoneName(name: string): string {
  return name.replace(/\s/g, "_").replace(/[[\].:/]/g, "");
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
