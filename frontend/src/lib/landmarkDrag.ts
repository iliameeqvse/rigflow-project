import * as THREE from "three";

// The front editing plane: z = 0, normal facing +Z.
const _plane = new THREE.Plane(new THREE.Vector3(0, 0, 1), 0);
const _hit = new THREE.Vector3();

/**
 * Intersect a pointer ray with the front editing plane and return the (x, y)
 * of the hit. Returns null if the ray does not reach the plane.
 */
export function rayToFrontPlane(ray: THREE.Ray): { x: number; y: number } | null {
  const hit = ray.intersectPlane(_plane, _hit);
  if (!hit) return null;
  return { x: hit.x, y: hit.y };
}
