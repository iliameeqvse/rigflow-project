"use client";

import { useEffect, useState, Suspense } from "react";
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

// Pick a default rotation that stands an upright humanoid upright in the
// three.js Y-up scene. We use the thinnest AABB axis as a proxy for the
// model's depth (front-to-back direction):
//   - thinnest = Z → already canonical Y-up (height along Y, depth into-screen).
//   - thinnest = Y → model is lying horizontal (depth along Y), apply -90° X
//     to swing the height axis up. Works for both Z-up authoring and
//     T-pose models where size.x marginally exceeds size.z.
//   - thinnest = X → unusual (model thin sideways); leave for manual rotation.
// The rigging backend runs a parallel correction pass on the post-import
// Blender AABB so both sides reach canonical before the user's rotation
// is composed on top.
function autoOrientFromSize(size: THREE.Vector3): ModelRotation | null {
  const min = Math.min(size.x, size.y, size.z);
  if (size.z === min) return null;
  if (size.y === min) return { x: -90, y: 0, z: 0 };
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
}: {
  file: File;
  rotationQuaternion: ModelRotationQuaternion;
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
        // Auto-orient is baked directly onto the loaded object so the
        // user's rotationQuaternion (sent to the rigging backend) stays
        // a clean fine-tune delta. The backend reaches the same canonical
        // orientation independently by reading the FBX header.
        loaded.updateMatrixWorld(true);
        const rawBox = new THREE.Box3().setFromObject(loaded);
        const rawSize = new THREE.Vector3();
        rawBox.getSize(rawSize);
        const initial = autoOrientFromSize(rawSize);
        if (initial) {
          const autoQuat = buildAxisQuaternion("x", initial.x)
            .multiply(buildAxisQuaternion("y", initial.y))
            .multiply(buildAxisQuaternion("z", initial.z));
          loaded.applyQuaternion(autoQuat);
        }
        autoFit(loaded);
        setObj(loaded);
      })
      .catch((e) => {
        if (!cancelled) setErr(String(e?.message ?? e));
      });

    return () => {
      cancelled = true;
      URL.revokeObjectURL(url);
    };
  }, [file]);

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
        <div style={{ color: "#00f0ff", fontSize: 14 }}>⚙️ Loading preview…</div>
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
    background: "#161b22",
    border: "1px solid #313b4a",
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
          background: "linear-gradient(135deg,#0b0e14,#161b22)",
          border: "1px solid #313b4a",
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
            />
          </Suspense>
          <Grid
            position={[0, 0, 0]}
            args={[10, 10]}
            cellColor="#1c2330"
            sectionColor="#313b4a"
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
                  color: "#00f0ff",
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
