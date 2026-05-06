"use client";

import React, { Suspense, useEffect, useRef, useState, useCallback } from "react";
import { Canvas, useLoader, useFrame, ThreeEvent } from "@react-three/fiber";
import {
  OrbitControls, Environment, Grid, Html, useGLTF,
} from "@react-three/drei";
import { FBXLoader } from "three-stdlib";
import * as THREE from "three";
import { type LandmarkSet, getLandmarks } from "@/lib/api";

// ── Target display height matching ModelViewer ────────────────────────────────
const TARGET_HEIGHT = 2.0;

function autoFitObject(object: THREE.Object3D) {
  object.position.set(0, 0, 0);
  object.scale.set(1, 1, 1);
  object.updateMatrixWorld(true);
  const box  = new THREE.Box3().setFromObject(object);
  const size = new THREE.Vector3();
  box.getSize(size);
  const tallest = Math.max(size.x, size.y, size.z);
  if (tallest === 0) return;
  const scale = TARGET_HEIGHT / tallest;
  object.scale.setScalar(scale);
  object.updateMatrixWorld(true);
  const box2   = new THREE.Box3().setFromObject(object);
  const centre = new THREE.Vector3();
  box2.getCenter(centre);
  object.position.x -= centre.x;
  object.position.z -= centre.z;
  object.position.y -= box2.min.y;
  object.updateMatrixWorld(true);
}

// ─────────────────────────────────────────────────────────────────────────────
// LandmarkPositions is now the full 14-key set from the API types
export type LandmarkPositions = LandmarkSet;

const LANDMARKS = [
  // Head — yellow
  { key: "chin"           as const, label: "Chin",           color: "#ffd166", instruction: "Click the bottom of the chin / top of neck", group: "Head"  },
  // Torso — green
  { key: "groin"          as const, label: "Groin",          color: "#06d6a0", instruction: "Click the crotch point between the legs",     group: "Torso" },
  // Left arm — blue
  { key: "left_shoulder"  as const, label: "Left Shoulder",  color: "#118ab2", instruction: "Click the character's LEFT shoulder joint",   group: "Arm L" },
  { key: "left_elbow"     as const, label: "Left Elbow",     color: "#118ab2", instruction: "Click the character's LEFT elbow",           group: "Arm L" },
  { key: "left_wrist"     as const, label: "Left Wrist",     color: "#118ab2", instruction: "Click the character's LEFT wrist",           group: "Arm L" },
  // Right arm — same blue (mirror; the group label disambiguates)
  { key: "right_shoulder" as const, label: "Right Shoulder", color: "#118ab2", instruction: "Click the character's RIGHT shoulder joint",  group: "Arm R" },
  { key: "right_elbow"    as const, label: "Right Elbow",    color: "#118ab2", instruction: "Click the character's RIGHT elbow",          group: "Arm R" },
  { key: "right_wrist"    as const, label: "Right Wrist",    color: "#118ab2", instruction: "Click the character's RIGHT wrist",          group: "Arm R" },
  // Left leg — pink
  { key: "left_hip"       as const, label: "Left Hip",       color: "#ef476f", instruction: "Click the character's LEFT hip socket",      group: "Leg L" },
  { key: "left_knee"      as const, label: "Left Knee",      color: "#ef476f", instruction: "Click the character's LEFT knee",            group: "Leg L" },
  { key: "left_ankle"     as const, label: "Left Ankle",     color: "#ef476f", instruction: "Click the character's LEFT ankle",           group: "Leg L" },
  // Right leg — pink
  { key: "right_hip"      as const, label: "Right Hip",      color: "#ef476f", instruction: "Click the character's RIGHT hip socket",     group: "Leg R" },
  { key: "right_knee"     as const, label: "Right Knee",     color: "#ef476f", instruction: "Click the character's RIGHT knee",           group: "Leg R" },
  { key: "right_ankle"    as const, label: "Right Ankle",    color: "#ef476f", instruction: "Click the character's RIGHT ankle",          group: "Leg R" },
];

const GROUPS = ["Head", "Torso", "Arm L", "Arm R", "Leg L", "Leg R"] as const;
type Group = typeof GROUPS[number];

function defaultLandmarks(bbox: THREE.Box3): LandmarkPositions {
  const size = new THREE.Vector3();
  bbox.getSize(size);
  const cx = (bbox.min.x + bbox.max.x) / 2;
  const cy = (bbox.min.y + bbox.max.y) / 2;
  const h  = size.z;
  const w  = size.x;
  return {
    chin:           [cx,             cy, bbox.min.z + h * 0.86],
    groin:          [cx,             cy, bbox.min.z + h * 0.51],
    left_shoulder:  [cx - w * 0.18,  cy, bbox.min.z + h * 0.78],
    right_shoulder: [cx + w * 0.18,  cy, bbox.min.z + h * 0.78],
    left_elbow:     [cx - w * 0.36,  cy, bbox.min.z + h * 0.60],
    right_elbow:    [cx + w * 0.36,  cy, bbox.min.z + h * 0.60],
    left_wrist:     [cx - w * 0.52,  cy, bbox.min.z + h * 0.44],
    right_wrist:    [cx + w * 0.52,  cy, bbox.min.z + h * 0.44],
    left_hip:       [cx - w * 0.10,  cy, bbox.min.z + h * 0.51],
    right_hip:      [cx + w * 0.10,  cy, bbox.min.z + h * 0.51],
    left_knee:      [cx - w * 0.10,  cy, bbox.min.z + h * 0.27],
    right_knee:     [cx + w * 0.10,  cy, bbox.min.z + h * 0.27],
    left_ankle:     [cx - w * 0.14,  cy, bbox.min.z + h * 0.04],
    right_ankle:    [cx + w * 0.14,  cy, bbox.min.z + h * 0.04],
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
    // Normalise scale/position so landmarks match what the user sees
    autoFitObject(object);
    // Compute bbox AFTER fitting
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
      onClick={(e: ThreeEvent<MouseEvent>) => {
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
  rigId?: string;
  onSubmit: (landmarks: LandmarkPositions) => void;
  submitting?: boolean;
}

export function LandmarkEditor({ glbUrl, rigId, onSubmit, submitting = false }: LandmarkEditorProps) {
  const [landmarks, setLandmarks]     = useState<LandmarkPositions | null>(null);
  const [selectedKey, setSelectedKey] = useState<keyof LandmarkPositions | null>("chin");
  const [bbox, setBbox]               = useState<THREE.Box3 | null>(null);

  // Fetch landmarks from API on open, fall back to defaultLandmarks if fetch fails.
  // Only runs when rigId is provided; without rigId, handleBoundsReady sets defaults directly.
  useEffect(() => {
    if (!rigId || !bbox) return;
    let cancelled = false;
    getLandmarks(rigId)
      .then(({ data }) => {
        if (cancelled) return;
        setLandmarks(data.landmarks);
      })
      .catch(() => {
        if (cancelled) return;
        setLandmarks(defaultLandmarks(bbox));
      });
    return () => { cancelled = true; };
  }, [rigId, bbox]);

  const handleBoundsReady = useCallback((b: THREE.Box3) => {
    setBbox(b);
    setSelectedKey("chin");
    // If no rigId is available, set default landmarks immediately from bbox.
    // When rigId is present, the useEffect above will set landmarks after the API call.
    if (!rigId) setLandmarks(defaultLandmarks(b));
  }, [rigId]);

  const handleMeshClick = useCallback((pt: THREE.Vector3) => {
    if (!selectedKey) return;
    setLandmarks((prev) => prev
      ? { ...prev, [selectedKey]: [pt.x, pt.y, pt.z] as [number, number, number] }
      : prev
    );
    const keys  = LANDMARKS.map((m) => m.key);
    const next  = keys[keys.indexOf(selectedKey as typeof keys[number]) + 1] ?? null;
    setSelectedKey(next);
  }, [selectedKey]);

  const currentMeta = LANDMARKS.find((m) => m.key === selectedKey);
  const ext = glbUrl.split("?")[0].split(".").pop()?.toLowerCase();

  return (
    <div style={{ display: "flex", gap: "1rem", alignItems: "flex-start" }}>

      {/* ── Side panel ── */}
      <div style={{
        width: 230, flexShrink: 0,
        background: "#0d0d1a", border: "1px solid #2a2a3d",
        borderRadius: 12, padding: "1rem",
        display: "flex", flexDirection: "column", gap: "0.55rem",
        maxHeight: 560, overflowY: "auto",
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
            : <span style={{ color: "#00c48c" }}>All placed — hit Apply!</span>
          }
        </div>

        {/* Grouped landmark list */}
        {GROUPS.map((group: Group) => (
          <section key={group} style={{ marginBottom: ".75rem" }}>
            <h4 style={{
              color: "#888", fontSize: ".75rem", textTransform: "uppercase",
              letterSpacing: ".05em", margin: "0 0 .35rem", fontWeight: 700,
            }}>{group}</h4>
            <div style={{ display: "flex", flexDirection: "column", gap: ".25rem" }}>
              {LANDMARKS.filter((l) => l.group === group).map(({ key, label, color }) => {
                const active = selectedKey === key;
                const placed = landmarks !== null;
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
            </div>
          </section>
        ))}

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
          {submitting ? "Applying…" : "Apply rig"}
        </button>

        <button
          onClick={() => bbox && setLandmarks(defaultLandmarks(bbox))}
          style={{
            padding: "0.45rem", borderRadius: 7,
            border: "1px solid #2a2a3d", background: "transparent",
            color: "#666", cursor: "pointer", fontSize: "0.78rem",
          }}
        >
          Reset to defaults
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
            Click on the model to place: {currentMeta.label}
          </div>
        )}

        <Canvas camera={{ position: [0, 0.9, 3.2], fov: 45 }}>
          <ambientLight intensity={0.6} />
          <directionalLight position={[5, 10, 5]} intensity={1} />
          <pointLight position={[-5, 5, -5]} intensity={0.3} color="#6c63ff" />
          <Environment preset="studio" />

          <Suspense fallback={<Html center><div style={{ color: "#6c63ff" }}>Loading…</div></Html>}>
            {ext === "fbx" || ext === "obj"
              ? <FBXClickable url={glbUrl} onMeshClick={handleMeshClick} onBoundsReady={handleBoundsReady} />
              : <GLBClickable url={glbUrl} onMeshClick={handleMeshClick} onBoundsReady={handleBoundsReady} />
            }
          </Suspense>

          {/* Landmark spheres */}
          {landmarks && LANDMARKS.map(({ key, label, color }) => (
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
