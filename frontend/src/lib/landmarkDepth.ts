import * as THREE from "three";

const _box = new THREE.Box3();
const _frontRay = new THREE.Raycaster();
const _backRay = new THREE.Raycaster();
const _frontOrigin = new THREE.Vector3();
const _backOrigin = new THREE.Vector3();
const _toBack = new THREE.Vector3(0, 0, -1);
const _toFront = new THREE.Vector3(0, 0, 1);

export interface DepthSnapResult {
  /** The new depth (z). Equals `fallbackZ` when `hit` is false. */
  z: number;
  /** True when both surfaces were found and the depth was recomputed. */
  hit: boolean;
}

/**
 * Find the depth midway between the front and back surface of `root` at (x, y),
 * so a joint sits centred inside the limb volume.
 *
 * Two rays are cast — one inward from the front (+Z) and one inward from the
 * back (-Z) — and the nearest hit of each is taken. Casting from each side
 * independently makes the result correct regardless of the meshes' material
 * `side` (a single ray would miss the far surface on `FrontSide` materials,
 * because it strikes those triangles from behind).
 *
 * If either ray finds no surface, `fallbackZ` is returned unchanged and `hit`
 * is false. `root` must already be in its final (post-autoFit) world transform.
 */
export function snapDepthToMeshCenter(
  root: THREE.Object3D,
  x: number,
  y: number,
  fallbackZ: number,
): DepthSnapResult {
  root.updateMatrixWorld(true);
  _box.setFromObject(root);
  if (_box.isEmpty()) return { z: fallbackZ, hit: false };

  const span = _box.max.z - _box.min.z + 2;

  _frontOrigin.set(x, y, _box.max.z + 1);
  _frontRay.set(_frontOrigin, _toBack);
  _frontRay.far = span;
  const frontHits = _frontRay.intersectObject(root, true);
  if (frontHits.length === 0) return { z: fallbackZ, hit: false };

  _backOrigin.set(x, y, _box.min.z - 1);
  _backRay.set(_backOrigin, _toFront);
  _backRay.far = span;
  const backHits = _backRay.intersectObject(root, true);
  if (backHits.length === 0) return { z: fallbackZ, hit: false };

  const frontZ = frontHits[0].point.z;
  const backZ = backHits[0].point.z;
  return { z: (frontZ + backZ) / 2, hit: true };
}
