import { describe, it, expect } from "vitest";
import * as THREE from "three";
import { rayToFrontPlane } from "./landmarkDrag";

describe("rayToFrontPlane", () => {
  it("projects a -Z ray onto the front plane, preserving x/y", () => {
    const ray = new THREE.Ray(
      new THREE.Vector3(0.5, 1.2, 5),
      new THREE.Vector3(0, 0, -1),
    );
    const result = rayToFrontPlane(ray);
    expect(result).not.toBeNull();
    expect(result!.x).toBeCloseTo(0.5, 5);
    expect(result!.y).toBeCloseTo(1.2, 5);
  });

  it("returns null when the ray points away from the plane", () => {
    const ray = new THREE.Ray(
      new THREE.Vector3(0, 0, 5),
      new THREE.Vector3(0, 0, 1),
    );
    expect(rayToFrontPlane(ray)).toBeNull();
  });
});
