import { describe, it, expect } from "vitest";
import { LANDMARK_KEYS } from "@/lib/api";
import { SKELETON_EDGES } from "./landmarkSkeleton";

describe("SKELETON_EDGES", () => {
  it("defines 13 edges", () => {
    expect(SKELETON_EDGES).toHaveLength(13);
  });

  it("only references valid landmark keys", () => {
    for (const [a, b] of SKELETON_EDGES) {
      expect(LANDMARK_KEYS).toContain(a);
      expect(LANDMARK_KEYS).toContain(b);
    }
  });

  it("has no edge connecting a landmark to itself", () => {
    for (const [a, b] of SKELETON_EDGES) {
      expect(a).not.toBe(b);
    }
  });
});
