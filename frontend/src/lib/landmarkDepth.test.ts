import { describe, it, expect } from "vitest";
import * as THREE from "three";
import { snapDepthToMeshCenter } from "./landmarkDepth";

// A box 1 wide, 2 tall, 0.4 deep, centred at the origin:
// its front face is at z = +0.2 and its back face at z = -0.2.
function makeBox(): THREE.Object3D {
  const mesh = new THREE.Mesh(new THREE.BoxGeometry(1, 2, 0.4));
  const root = new THREE.Group();
  root.add(mesh);
  return root;
}

describe("snapDepthToMeshCenter", () => {
  it("returns the front/back midpoint depth when the ray hits the mesh", () => {
    const result = snapDepthToMeshCenter(makeBox(), 0, 0, 99);
    expect(result.hit).toBe(true);
    expect(result.z).toBeCloseTo(0, 5);
  });

  it("preserves the fallback depth when the ray misses the silhouette", () => {
    const result = snapDepthToMeshCenter(makeBox(), 5, 5, 1.234);
    expect(result.hit).toBe(false);
    expect(result.z).toBe(1.234);
  });
});
