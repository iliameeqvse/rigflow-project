import * as THREE from "three";

import type { ModelRotation, ModelRotationQuaternion } from "@/lib/api";

export const IDENTITY_ROTATION_QUATERNION: ModelRotationQuaternion = {
  x: 0,
  y: 0,
  z: 0,
  w: 1,
};

export function buildPreviewQuaternion(rotation: ModelRotation) {
  const qx = new THREE.Quaternion().setFromAxisAngle(
    new THREE.Vector3(1, 0, 0),
    THREE.MathUtils.degToRad(rotation.x),
  );
  const qy = new THREE.Quaternion().setFromAxisAngle(
    new THREE.Vector3(0, 1, 0),
    THREE.MathUtils.degToRad(rotation.y),
  );
  const qz = new THREE.Quaternion().setFromAxisAngle(
    new THREE.Vector3(0, 0, 1),
    THREE.MathUtils.degToRad(rotation.z),
  );
  return qz.multiply(qy).multiply(qx);
}

export function quaternionToPojo(q: THREE.Quaternion): ModelRotationQuaternion {
  return { x: q.x, y: q.y, z: q.z, w: q.w };
}

export function quaternionFromPojo(q: ModelRotationQuaternion): THREE.Quaternion {
  return new THREE.Quaternion(q.x, q.y, q.z, q.w);
}

export function buildAxisQuaternion(
  axis: keyof ModelRotation,
  deltaDeg: number,
): THREE.Quaternion {
  const axisVector =
    axis === "x"
      ? new THREE.Vector3(1, 0, 0)
      : axis === "y"
        ? new THREE.Vector3(0, 1, 0)
        : new THREE.Vector3(0, 0, 1);
  return new THREE.Quaternion().setFromAxisAngle(
    axisVector,
    THREE.MathUtils.degToRad(deltaDeg),
  );
}
