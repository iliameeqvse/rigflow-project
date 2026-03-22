"use client";

import React, { Suspense, useEffect, useRef, useState, useCallback } from "react";
import { Canvas, useLoader, useFrame } from "@react-three/fiber";
import {
  OrbitControls, Environment, Grid, Html, useGLTF,
} from "@react-three/drei";
import { FBXLoader } from "three-stdlib";
import * as THREE from "three";

// ─────────────────────────────────────────────────────────────────────────────
export interface LandmarkPositions {
  chin:        [number, number, number];
  left_wrist:  [number, number, number];
  right_wrist: [number, number, number];
  groin:       [number, number, number];
  left_ankle:  [number, number, number];
  right_ankle: [number, number, number];
}

const LANDMARK_META = [
  { key: "chin"        as const, label: "Chin",        color: "#ff4444", instruction: "Click the bottom of the chin / top of neck" },
  { key: "left_wrist"  as const, label: "Left Wrist",  color: "#ff8c00", instruction: "Click the character's LEFT wrist (your right)" },
  { key: "right_wrist" as const, label: "Right Wrist", color: "#ffd700", instruction: "Click the character's RIGHT wrist (your left)" },
  { key: "groin"       as const, label: "Groin",       color: "#00c48c", instruction: "Click the crotch point between the legs" },
  { key: "left_ankle"  as const, label: "Left Ankle",  color: "#00aaff", instruction: "Click the character's LEFT ankle" },
  { key: "right_ankle" as const, label: "Right Ankle", color: "#aa44ff", instruction: "Click the character's RIGHT ankle" },
];

function defaultLandmarks(bbox: THREE.Box3): LandmarkPositions {
  const size = new THREE.Vector3();
  bbox.getSize(size);
  const cx  = (bbox.min.x + bbox.max.x) / 2;
  const cy  = (bbox.min.y + bbox.max.y) / 2;
  const h   = size.z;
  const w   = size.x;
  return {
    chin:        [cx,          cy, bbox.min.z + h * 0.86],
    left_wrist:  [cx - w * 0.52, cy, bbox.min.z + h * 0.44],
    right_wrist: [cx + w * 0.52, cy, bbox.min.z + h * 0.44],
    groin:       [cx,          cy, bbox.min.z + h * 0.51],
    left_ankle:  [cx - w * 0.14, cy, bbox.min.z + h * 0.04],
    right_ankle: [cx + w * 0.14, cy, bbox.min.z + h * 0.04],
  };
}

// ─────────────────────────────────────────────────────────────────────────────
// Landmark sphere
// ─────────────────────────────────────────────────────────────────────────────
function LandmarkSphere({
  position, color, selected, onSelect, label,
}: {
  position: [number, number, number];
  color: string;
  selected: boolean;
  onSelect: () => void;
  label: string;
}) {
  const ref = useRef<THREE.Mesh>(null);
  const [hovered, setHovered] = useState(false);

  useFrame(() => {
    if (ref.current) ref.current.scale.setScalar(selected ? 1.4 : hovered ? 1.2 : 1.0);
  });

  return (
    <group position={position}>
      <mesh
        ref={ref}
        onClick={(e) => { e.stopPropagation(); onSelect(); }}
        onPointerOver={(e) => { e.stopPropagation(); setHovered(true); document.body.style.cursor = "pointer"; }}
        onPointerOut={() => { setHovered(false); document.body.style.cursor = "default"; }}
        renderOrder={999}
      >
        <sphereGeometry args={[0.025, 16, 16]} />
        <meshStandardMaterial
          color={selected ? "#ffffff" : color}
          emissive={selected ? color : hovered ? color : "#000"}
          emissiveIntensity={selected ? 0.9 : hovered ? 0.4 : 0}
          depthTest={false}
        />
      </mesh>
      <Html distanceFactor={6} style={{ pointerEvents: "none" }}>
        <div style={{
          background: selected ? color : "rgba(0,0,0,0.75)",
          color: "#fff", padding: "2px 7px", borderRadius: 4,
          fontSize: 10, whiteSpace: "nowrap", fontWeight: 700,
          border: `1px solid ${color}`, userSelect: "none",
        }}>
          {label}
        </div>
      </Html>
    </group>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Clickable model — attaches onClick to every child mesh via traverse
// ─────────────────────────────────────────────────────────────────────────────
function ClickableModel({
  object,
  onMeshClick,
  onBoundsReady,
}: {
  object: THREE.Object3D;
  onMeshClick: (pt: THREE.Vector3) => void;
  onBoundsReady: (bbox: THREE.Box3) => void;
}) {
  useEffect(() => {
    // Compute bbox from the raw object before any centering
    const bbox = new THREE.Box3().setFromObject(object);
    onBoundsReady(bbox);

    // Enable raycasting on every mesh child
    object.traverse((child) => {
      if (child instanceof THREE.Mesh) {
        child.raycast = THREE.Mesh.prototype.raycast.bind(child);
      }
    });
  }, [object]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <primitive
      object={object}
      onClick={(e: any) => {
        e.stopPropagation();
        if (e.point) onMeshClick(e.point.clone());
      }}
    />
  );
}

function FBXClickable(props: { url: string; onMeshClick: (pt: THREE.Vector3) => void; onBoundsReady: (b: THREE.Box3) => void }) {
  const fbx = useLoader(FBXLoader, props.url);
  return <ClickableModel object={fbx} onMeshClick={props.onMeshClick} onBoundsReady={props.onBoundsReady} />;
}

function GLBClickable(props: { url: string; onMeshClick: (pt: THREE.Vector3) => void; onBoundsReady: (b: THREE.Box3) => void }) {
  const { scene } = useGLTF(props.url);
  return <ClickableModel object={scene} onMeshClick={props.onMeshClick} onBoundsReady={props.onBoundsReady} />;
}

// ─────────────────────────────────────────────────────────────────────────────
// Main export
// ─────────────────────────────────────────────────────────────────────────────
interface LandmarkEditorProps {
  glbUrl: string;
  onSubmit: (landmarks: LandmarkPositions) => void;
  submitting?: boolean;
}

export function LandmarkEditor({ glbUrl, onSubmit, submitting = false }: LandmarkEditorProps) {
  const [landmarks, setLandmarks]     = useState<LandmarkPositions | null>(null);
  const [selectedKey, setSelectedKey] = useState<keyof LandmarkPositions | null>("chin");
  const [bbox, setBbox]               = useState<THREE.Box3 | null>(null);

  const handleBoundsReady = useCallback((b: THREE.Box3) => {
    setBbox(b);
    setLandmarks(defaultLandmarks(b));
    setSelectedKey("chin");
  }, []);

  const handleMeshClick = useCallback((pt: THREE.Vector3) => {
    if (!selectedKey) return;
    setLandmarks((prev) => prev
      ? { ...prev, [selectedKey]: [pt.x, pt.y, pt.z] as [number, number, number] }
      : prev
    );
    const keys  = LANDMARK_META.map((m) => m.key);
    const next  = keys[keys.indexOf(selectedKey) + 1] ?? null;
    setSelectedKey(next);
  }, [selectedKey]);

  const currentMeta = LANDMARK_META.find((m) => m.key === selectedKey);
  const ext = glbUrl.split("?")[0].split(".").pop()?.toLowerCase();

  return (
    <div style={{ display: "flex", gap: "1rem", alignItems: "flex-start" }}>

      {/* ── Side panel ── */}
      <div style={{
        width: 230, flexShrink: 0,
        background: "#0d0d1a", border: "1px solid #2a2a3d",
        borderRadius: 12, padding: "1rem",
        display: "flex", flexDirection: "column", gap: "0.55rem",
      }}>
        <div style={{ fontSize: "0.78rem", fontWeight: 700, color: "#888", letterSpacing: "0.08em" }}>
          LANDMARK PLACEMENT
        </div>

        {/* Current instruction */}
        <div style={{
          background: currentMeta ? "rgba(108,99,255,0.08)" : "rgba(42,42,61,0.4)",
          border: `1px solid ${currentMeta ? "rgba(108,99,255,0.35)" : "#2a2a3d"}`,
          borderRadius: 8, padding: "0.6rem 0.75rem",
          fontSize: "0.8rem", color: "#ccc", minHeight: 44,
        }}>
          {currentMeta
            ? <><span style={{ color: currentMeta.color, fontWeight: 700 }}>{currentMeta.label}:</span><br />{currentMeta.instruction}</>
            : <span style={{ color: "#00c48c" }}>✅ All placed — hit Apply!</span>
          }
        </div>

        {/* Landmark list */}
        {LANDMARK_META.map(({ key, label, color }) => {
          const placed = landmarks !== null;
          const active = selectedKey === key;
          return (
            <button key={key} onClick={() => setSelectedKey(key)} style={{
              display: "flex", alignItems: "center", gap: "0.55rem",
              padding: "0.45rem 0.7rem", borderRadius: 7,
              border: `1px solid ${active ? color : "#2a2a3d"}`,
              background: active ? `${color}18` : "transparent",
              color: "#ccc", cursor: "pointer", fontSize: "0.84rem",
              fontWeight: active ? 700 : 400, textAlign: "left",
              transition: "all 0.15s",
            }}>
              <span style={{ width: 9, height: 9, borderRadius: "50%", background: color, flexShrink: 0 }} />
              {label}
              {placed && <span style={{ marginLeft: "auto", color: "#00c48c", fontSize: 11 }}>✓</span>}
            </button>
          );
        })}

        <div style={{ flex: 1 }} />

        <button
          onClick={() => landmarks && onSubmit(landmarks)}
          disabled={!landmarks || submitting}
          style={{
            padding: "0.65rem", borderRadius: 8, border: "none",
            background: !landmarks || submitting ? "#2a2a3d" : "linear-gradient(135deg,#6c63ff,#00d4ff)",
            color: !landmarks || submitting ? "#555" : "#fff",
            fontWeight: 700, cursor: !landmarks || submitting ? "not-allowed" : "pointer",
            fontSize: "0.88rem",
          }}
        >
          {submitting ? "Applying…" : "✅ Apply rig"}
        </button>

        <button
          onClick={() => bbox && setLandmarks(defaultLandmarks(bbox))}
          style={{
            padding: "0.45rem", borderRadius: 7,
            border: "1px solid #2a2a3d", background: "transparent",
            color: "#666", cursor: "pointer", fontSize: "0.78rem",
          }}
        >
          ↺ Reset to defaults
        </button>
      </div>

      {/* ── Canvas ── */}
      <div style={{
        flex: 1, height: 560,
        background: "linear-gradient(135deg,#0a0a14,#0d0d20)",
        borderRadius: 12, overflow: "hidden",
        border: `2px solid ${selectedKey ? "rgba(108,99,255,0.5)" : "#2a2a3d"}`,
        cursor: selectedKey ? "crosshair" : "default",
        transition: "border-color 0.2s",
      }}>
        {/* Crosshair hint */}
        {selectedKey && currentMeta && (
          <div style={{
            position: "absolute", top: 8, left: "50%", transform: "translateX(-50%)",
            background: `${currentMeta.color}22`, border: `1px solid ${currentMeta.color}`,
            borderRadius: 20, padding: "4px 12px", fontSize: 11, color: currentMeta.color,
            fontWeight: 700, pointerEvents: "none", zIndex: 10, whiteSpace: "nowrap",
          }}>
            🎯 Click on the model to place: {currentMeta.label}
          </div>
        )}

        <Canvas camera={{ position: [0, 0.9, 3.2], fov: 45 }}>
          <ambientLight intensity={0.6} />
          <directionalLight position={[5, 10, 5]} intensity={1} />
          <pointLight position={[-5, 5, -5]} intensity={0.3} color="#6c63ff" />
          <Environment preset="studio" />

          <Suspense fallback={<Html center><div style={{ color: "#6c63ff" }}>⚙️ Loading…</div></Html>}>
            {ext === "fbx" || ext === "obj"
              ? <FBXClickable url={glbUrl} onMeshClick={handleMeshClick} onBoundsReady={handleBoundsReady} />
              : <GLBClickable url={glbUrl} onMeshClick={handleMeshClick} onBoundsReady={handleBoundsReady} />
            }
          </Suspense>

          {/* Landmark spheres */}
          {landmarks && LANDMARK_META.map(({ key, label, color }) => (
            <LandmarkSphere
              key={key}
              position={landmarks[key]}
              color={color}
              selected={selectedKey === key}
              label={label}
              onSelect={() => setSelectedKey(key)}
            />
          ))}

          <Grid position={[0, 0, 0]} args={[10, 10]} cellColor="#1a1a2e" sectionColor="#2a2a3d" fadeDistance={12} infiniteGrid />
          <OrbitControls makeDefault minDistance={0.3} maxDistance={10} />
        </Canvas>
      </div>
    </div>
  );
}