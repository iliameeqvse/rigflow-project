"use client";

import { useCallback, useEffect, useRef, useState, Suspense } from "react";
import { Canvas } from "@react-three/fiber";
import { OrbitControls, Environment, Grid, Html } from "@react-three/drei";
import { FBXLoader, GLTFLoader } from "three-stdlib";
import * as THREE from "three";
import type { ModelRotation, ModelRotationQuaternion } from "@/lib/api";
import {
  buildAxisQuaternion,
  quaternionFromPojo,
  quaternionToPojo,
} from "@/lib/modelRotation";

const TARGET_HEIGHT = 2.0;

// Pick a default rotation that stands an upright character upright in the
// three.js Y-up scene. We assume the model's longest axis is its height.
// Y-dominant: already upright (no rotation). Z-dominant: lying with head
// along +Z (typical Blender Z-up export) → Pitch -90° about X stands it up.
// X-dominant: too ambiguous (can't tell which X end is the head); leave
// alone and let the user adjust manually.
function autoOrientFromSize(size: THREE.Vector3): ModelRotation | null {
  const yDominant = size.y >= size.x && size.y >= size.z;
  if (yDominant) return null;
  if (size.z > size.x) return { x: -90, y: 0, z: 0 };
  return null;
}

interface Props {
  file: File;
  rotation: ModelRotation;
  rotationQuaternion: ModelRotationQuaternion;
  onChangeRotation: (
    rotation: ModelRotation,
    rotationQuaternion: ModelRotationQuaternion,
  ) => void;
  height?: number;
}

function autoFit(obj: THREE.Object3D) {
  obj.updateMatrixWorld(true);
  const box = new THREE.Box3().setFromObject(obj);
  const size = new THREE.Vector3();
  box.getSize(size);
  const max = Math.max(size.x, size.y, size.z);
  if (max > 0) obj.scale.multiplyScalar(TARGET_HEIGHT / max);
  obj.updateMatrixWorld(true);
  const box2 = new THREE.Box3().setFromObject(obj);
  const c = new THREE.Vector3();
  box2.getCenter(c);
  obj.position.x -= c.x;
  obj.position.z -= c.z;
  obj.position.y -= box2.min.y;
}

function PreviewObject({
  file,
  rotationQuaternion,
  onLoadedSize,
}: {
  file: File;
  rotationQuaternion: ModelRotationQuaternion;
  onLoadedSize?: (rawSize: THREE.Vector3) => void;
}) {
  const [obj, setObj] = useState<THREE.Object3D | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const url = URL.createObjectURL(file);
    const ext = file.name.split(".").pop()?.toLowerCase();

    const promise: Promise<THREE.Object3D> =
      ext === "fbx"
        ? new FBXLoader().loadAsync(url)
        : ext === "glb" || ext === "gltf"
          ? new GLTFLoader().loadAsync(url).then((g) => g.scene)
          : Promise.reject(new Error(`Preview not supported for .${ext}`));

    promise
      .then((loaded) => {
        if (cancelled) return;
        // Capture the raw axis ratios BEFORE autoFit normalises scale, so
        // the parent can pick a sensible default rotation that stands the
        // model up. The user can still override with the rotation buttons.
        loaded.updateMatrixWorld(true);
        const rawBox = new THREE.Box3().setFromObject(loaded);
        const rawSize = new THREE.Vector3();
        rawBox.getSize(rawSize);
        autoFit(loaded);
        setObj(loaded);
        onLoadedSize?.(rawSize);
      })
      .catch((e) => {
        if (!cancelled) setErr(String(e?.message ?? e));
      });

    return () => {
      cancelled = true;
      URL.revokeObjectURL(url);
    };
  }, [file]); // eslint-disable-line react-hooks/exhaustive-deps

  if (err) {
    return (
      <Html center>
        <div style={{ color: "#f87171", fontSize: 13, maxWidth: 320, textAlign: "center" }}>
          Couldn&apos;t preview this file:<br />{err}
          <br />
          <small>Rotation will still be applied at upload.</small>
        </div>
      </Html>
    );
  }

  if (!obj) {
    return (
      <Html center>
        <div style={{ color: "#6c63ff", fontSize: 14 }}>⚙️ Loading preview…</div>
      </Html>
    );
  }

  return (
    <group
      quaternion={quaternionFromPojo(rotationQuaternion)}
    >
      <primitive object={obj} />
    </group>
  );
}

export function RotationPreview({
  file,
  rotation,
  rotationQuaternion,
  onChangeRotation,
  height = 360,
}: Props) {
  // Run auto-orient at most once per file. Avoids overwriting the user's
  // manual adjustments if the load completes after they've already clicked.
  const autoOrientedFileRef = useRef<File | null>(null);
  // Latest rotation in a ref so the load callback's closure isn't stale.
  const rotationRef = useRef<ModelRotation>(rotation);
  useEffect(() => {
    rotationRef.current = rotation;
  }, [rotation]);

  const handleLoadedSize = useCallback(
    (rawSize: THREE.Vector3) => {
      if (autoOrientedFileRef.current === file) return;
      autoOrientedFileRef.current = file;
      const r = rotationRef.current;
      // Don't override a rotation the user has already started touching.
      if (r.x !== 0 || r.y !== 0 || r.z !== 0) return;
      const initial = autoOrientFromSize(rawSize);
      if (!initial) return;
      const initialQuat = buildAxisQuaternion("x", initial.x)
        .multiply(buildAxisQuaternion("y", initial.y))
        .multiply(buildAxisQuaternion("z", initial.z));
      onChangeRotation(initial, quaternionToPojo(initialQuat));
    },
    [file, onChangeRotation],
  );

  const wrapSigned = (deg: number) => {
    const wrapped = ((deg + 180) % 360 + 360) % 360 - 180;
    return wrapped === -180 ? 180 : wrapped;
  };

  const axes: Array<{
    key: keyof ModelRotation;
    label: string;
    hint: string;
  }> = [
    { key: "x", label: "Pitch", hint: "Tilt forward/back" },
    { key: "y", label: "Yaw", hint: "Turn left/right" },
    { key: "z", label: "Roll", hint: "Lean side-to-side" },
  ];

  const shortestDelta = (from: number, to: number) => {
    let delta = to - from;
    if (delta > 180) delta -= 360;
    if (delta < -180) delta += 360;
    return delta;
  };

  const applyAxisDelta = (axis: keyof ModelRotation, delta: number, nextValue: number) => {
    const nextQuat = buildAxisQuaternion(axis, delta).multiply(
      quaternionFromPojo(rotationQuaternion),
    );
    onChangeRotation({
      ...rotation,
      [axis]: nextValue,
    }, quaternionToPojo(nextQuat));
  };

  const adjustAxis = (axis: keyof ModelRotation, delta: number) => {
    const current = wrapSigned(rotation[axis]);
    const next = wrapSigned(current + delta);
    applyAxisDelta(axis, shortestDelta(current, next), next);
  };

  const setAxis = (axis: keyof ModelRotation, value: number) => {
    const current = wrapSigned(rotation[axis]);
    const next = wrapSigned(value);
    applyAxisDelta(axis, shortestDelta(current, next), next);
  };

  const btnStyle: React.CSSProperties = {
    padding: "0.4rem 0.7rem",
    background: "#12121a",
    border: "1px solid #2a2a3d",
    borderRadius: 8,
    color: "#ccc",
    fontSize: ".85rem",
    cursor: "pointer",
  };

  return (
    <div>
      <div
        style={{
          height,
          borderRadius: 12,
          overflow: "hidden",
          background: "linear-gradient(135deg,#0a0a14,#0d0d20)",
          border: "1px solid #2a2a3d",
          marginBottom: "0.75rem",
        }}
      >
        <Canvas camera={{ position: [0, 1.3, 3.4], fov: 45 }}>
          <ambientLight intensity={0.55} />
          <directionalLight position={[5, 10, 5]} intensity={1} />
          <Environment preset="studio" />
          <Suspense fallback={null}>
            <PreviewObject
              key={`${file.name}:${file.size}:${file.lastModified}`}
              file={file}
              rotationQuaternion={rotationQuaternion}
              onLoadedSize={handleLoadedSize}
            />
          </Suspense>
          <Grid
            position={[0, 0, 0]}
            args={[10, 10]}
            cellColor="#1a1a2e"
            sectionColor="#2a2a3d"
            fadeDistance={12}
            infiniteGrid
          />
          <OrbitControls makeDefault target={[0, 1, 0]} minDistance={0.5} maxDistance={10} />
        </Canvas>
      </div>

      <div
        style={{
          background: "rgba(108,99,255,0.08)",
          border: "1px solid rgba(108,99,255,0.25)",
          borderRadius: 8,
          padding: "0.6rem 0.85rem",
          fontSize: ".8rem",
          color: "#a0a0c0",
          marginBottom: "0.6rem",
        }}
      >
        We pick a best-guess starting orientation. Adjust the three axes
        until the model is upright (head up) and its front faces the camera.
        The rig is built in exactly this orientation — no further correction
        is applied.
      </div>

      <div style={{ display: "grid", gap: ".75rem" }}>
        {axes.map(({ key, label, hint }) => (
          <div key={key}>
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "baseline",
                marginBottom: ".35rem",
                gap: ".75rem",
              }}
            >
              <strong style={{ color: "#ddd", fontSize: ".9rem" }}>{label}</strong>
              <span style={{ color: "#7c7ca8", fontSize: ".78rem" }}>{hint}</span>
            </div>
            <div style={{ display: "flex", gap: ".4rem", flexWrap: "wrap", alignItems: "center" }}>
              <button style={btnStyle} onClick={() => adjustAxis(key, -90)}>↺ -90°</button>
              <button style={btnStyle} onClick={() => adjustAxis(key, -15)}>↺ -15°</button>
              <button style={btnStyle} onClick={() => setAxis(key, 0)}>0°</button>
              <button style={btnStyle} onClick={() => adjustAxis(key, 15)}>+15° ↻</button>
              <button style={btnStyle} onClick={() => adjustAxis(key, 90)}>+90° ↻</button>

              <input
                type="range"
                min={-180}
                max={180}
                step={5}
                value={wrapSigned(rotation[key])}
                onChange={(e) => setAxis(key, parseInt(e.target.value, 10))}
                style={{ flex: 1, minWidth: 140 }}
              />
              <span
                style={{
                  minWidth: 56,
                  textAlign: "right",
                  color: "#6c63ff",
                  fontWeight: 700,
                  fontSize: ".9rem",
                }}
              >
                {wrapSigned(rotation[key])}°
              </span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
