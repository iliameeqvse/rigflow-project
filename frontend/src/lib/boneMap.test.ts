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
