"use client";

import React, { Suspense, useEffect, useRef, useState, useCallback, useMemo } from "react";
import { Canvas, useLoader, useFrame } from "@react-three/fiber";
import {
  OrbitControls, Environment, Grid, Html, useGLTF, Line,
} from "@react-three/drei";
import { FBXLoader } from "three-stdlib";
import * as THREE from "three";
import { type LandmarkSet, getLandmarks } from "@/lib/api";
import { snapDepthToMeshCenter } from "@/lib/landmarkDepth";
import { rayToFrontPlane } from "@/lib/landmarkDrag";
import { SKELETON_EDGES } from "@/lib/landmarkSkeleton";

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
  { key: "chin"           as const, label: "Chin",           color: "#ffd166", group: "Head"  },
  // Torso — green
  { key: "groin"          as const, label: "Groin",          color: "#06d6a0", group: "Torso" },
  // Left arm — blue
  { key: "left_shoulder"  as const, label: "Left Shoulder",  color: "#118ab2", group: "Arm L" },
  { key: "left_elbow"     as const, label: "Left Elbow",     color: "#118ab2", group: "Arm L" },
  { key: "left_wrist"     as const, label: "Left Wrist",     color: "#118ab2", group: "Arm L" },
  // Right arm — same blue (mirror; the group label disambiguates)
  { key: "right_shoulder" as const, label: "Right Shoulder", color: "#118ab2", group: "Arm R" },
  { key: "right_elbow"    as const, label: "Right Elbow",    color: "#118ab2", group: "Arm R" },
  { key: "right_wrist"    as const, label: "Right Wrist",    color: "#118ab2", group: "Arm R" },
  // Left leg — pink
  { key: "left_hip"       as const, label: "Left Hip",       color: "#ef476f", group: "Leg L" },
  { key: "left_knee"      as const, label: "Left Knee",      color: "#ef476f", group: "Leg L" },
  { key: "left_ankle"     as const, label: "Left Ankle",     color: "#ef476f", group: "Leg L" },
  // Right leg — pink
  { key: "right_hip"      as const, label: "Right Hip",      color: "#ef476f", group: "Leg R" },
  { key: "right_knee"     as const, label: "Right Knee",     color: "#ef476f", group: "Leg R" },
  { key: "right_ankle"    as const, label: "Right Ankle",    color: "#ef476f", group: "Leg R" },
];

const GROUPS = ["Head", "Torso", "Arm L", "Arm R", "Leg L", "Leg R"] as const;
type Group = typeof GROUPS[number];

function defaultLandmarks(bbox: THREE.Box3): LandmarkPositions {
  const size = new THREE.Vector3();
  bbox.getSize(size);
  const cx = (bbox.min.x + bbox.max.x) / 2;
  const cz = (bbox.min.z + bbox.max.z) / 2;
  const h  = size.y;
  const w  = size.x;
  return {
    chin:           [cx,             bbox.min.y + h * 0.92, cz],
    groin:          [cx,             bbox.min.y + h * 0.50, cz],
    left_shoulder:  [cx + w * 0.18,  bbox.min.y + h * 0.82, cz],
    right_shoulder: [cx - w * 0.18,  bbox.min.y + h * 0.82, cz],
    left_elbow:     [cx + w * 0.36,  bbox.min.y + h * 0.82, cz + 0.05],
    right_elbow:    [cx - w * 0.36,  bbox.min.y + h * 0.82, cz + 0.05],
    left_wrist:     [cx + w * 0.52,  bbox.min.y + h * 0.82, cz],
    right_wrist:    [cx - w * 0.52,  bbox.min.y + h * 0.82, cz],
    left_hip:       [cx + w * 0.10,  bbox.min.y + h * 0.50, cz],
    right_hip:      [cx - w * 0.10,  bbox.min.y + h * 0.50, cz],
    left_knee:      [cx + w * 0.10,  bbox.min.y + h * 0.25, cz],
    right_knee:     [cx - w * 0.10,  bbox.min.y + h * 0.25, cz],
    left_ankle:     [cx + w * 0.10,  bbox.min.y,            cz],
    right_ankle:    [cx - w * 0.10,  bbox.min.y,            cz],
  };
}

// ─────────────────────────────────────────────────────────────────────────────
// Draggable landmark handle. Pointer-down grabs it; pointer-move drags it in the
// front plane; pointer-up drops it and triggers a depth snap in the parent.
// ─────────────────────────────────────────────────────────────────────────────
function DraggableLandmark({
  landmarkKey, position, color, label, depthLost, pulsing,
  onDragStart, onDrag, onDragEnd,
}: {
  landmarkKey: keyof LandmarkPositions;
  position: [number, number, number];
  color: string;
  label: string;
  depthLost: boolean;
  pulsing: boolean;
  onDragStart: (key: keyof LandmarkPositions) => void;
  onDrag: (key: keyof LandmarkPositions, x: number, y: number) => void;
  onDragEnd: (key: keyof LandmarkPositions, x: number, y: number) => void;
}) {
  const ref = useRef<THREE.Mesh>(null);
  const [hovered, setHovered] = useState(false);
  const [dragging, setDragging] = useState(false);

  useFrame(() => {
    if (!ref.current) return;
    const base = dragging ? 1.5 : hovered ? 1.2 : 1.0;
    ref.current.scale.setScalar(base * (pulsing ? 1.5 : 1.0));
  });

  return (
    <group position={position}>
      <mesh
        ref={ref}
        renderOrder={999}
        onPointerOver={(e) => { e.stopPropagation(); setHovered(true); document.body.style.cursor = "grab"; }}
        onPointerOut={() => { setHovered(false); if (!dragging) document.body.style.cursor = "default"; }}
        onPointerDown={(e) => {
          e.stopPropagation();
          (e.target as Element).setPointerCapture(e.pointerId);
          setDragging(true);
          onDragStart(landmarkKey);
          document.body.style.cursor = "grabbing";
        }}
        onPointerMove={(e) => {
          if (!dragging) return;
          e.stopPropagation();
          const pt = rayToFrontPlane(e.ray);
          if (pt) onDrag(landmarkKey, pt.x, pt.y);
        }}
        onPointerUp={(e) => {
          if (!dragging) return;
          e.stopPropagation();
          (e.target as Element).releasePointerCapture(e.pointerId);
          setDragging(false);
          document.body.style.cursor = "grab";
          const pt = rayToFrontPlane(e.ray);
          onDragEnd(landmarkKey, pt ? pt.x : position[0], pt ? pt.y : position[1]);
        }}
      >
        <sphereGeometry args={[0.03, 16, 16]} />
        <meshStandardMaterial
          color={dragging ? "#ffffff" : color}
          emissive={depthLost ? "#ffae00" : dragging || hovered ? color : "#000"}
          emissiveIntensity={depthLost ? 0.8 : dragging ? 0.9 : hovered ? 0.4 : 0}
          depthTest={false}
        />
      </mesh>

      {/* amber ring: depth snap could not find the mesh under this handle */}
      {depthLost && (
        <mesh renderOrder={998}>
          <ringGeometry args={[0.045, 0.062, 24]} />
          <meshBasicMaterial color="#ffae00" side={THREE.DoubleSide} depthTest={false} transparent opacity={0.85} />
        </mesh>
      )}

      <Html distanceFactor={6} style={{ pointerEvents: "none" }}>
        <div style={{
          background: pulsing ? "#fff" : "rgba(0,0,0,0.75)",
          color: pulsing ? "#000" : "#fff", padding: "2px 7px", borderRadius: 4,
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
// Fitted model — normalises scale/position, exposes bounds + the fitted object.
// No click handler: landmarks are placed by dragging handles, not clicking mesh.
// ─────────────────────────────────────────────────────────────────────────────
function FittedModel({
  object,
  onBoundsReady,
  onModelReady,
}: {
  object: THREE.Object3D;
  onBoundsReady: (bbox: THREE.Box3) => void;
  onModelReady: (object: THREE.Object3D) => void;
}) {
  useEffect(() => {
    autoFitObject(object);
    const bbox = new THREE.Box3().setFromObject(object);
    onBoundsReady(bbox);
    object.traverse((child) => {
      if (child instanceof THREE.Mesh) {
        child.raycast = THREE.Mesh.prototype.raycast.bind(child);
      }
    });
    onModelReady(object);
  }, [object]); // eslint-disable-line react-hooks/exhaustive-deps

  return <primitive object={object} />;
}

function FBXModel(props: {
  url: string;
  onBoundsReady: (b: THREE.Box3) => void;
  onModelReady: (o: THREE.Object3D) => void;
}) {
  const fbx = useLoader(FBXLoader, props.url);
  return <FittedModel object={fbx} onBoundsReady={props.onBoundsReady} onModelReady={props.onModelReady} />;
}

function GLBModel(props: {
  url: string;
  onBoundsReady: (b: THREE.Box3) => void;
  onModelReady: (o: THREE.Object3D) => void;
}) {
  const { scene } = useGLTF(props.url);
  return <FittedModel object={scene} onBoundsReady={props.onBoundsReady} onModelReady={props.onModelReady} />;
}

// ─────────────────────────────────────────────────────────────────────────────
// Live skeleton overlay — thin always-on-top lines between landmark handles.
// A placement guide, not the final DEF rig.
// ─────────────────────────────────────────────────────────────────────────────
function Skeleton({ landmarks }: { landmarks: LandmarkPositions }) {
  return (
    <>
      {SKELETON_EDGES.map(([a, b]) => (
        <Line
          key={`${a}-${b}`}
          points={[landmarks[a], landmarks[b]]}
          color="#00e5ff"
          lineWidth={2}
          depthTest={false}
          renderOrder={997}
        />
      ))}
    </>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Non-interactive 3/4 preview. Clones the fitted model as a translucent "ghost"
// so the user can confirm the auto-snapped joints sit inside the limb volume.
// ─────────────────────────────────────────────────────────────────────────────
function GhostBody({ source }: { source: THREE.Object3D }) {
  const ghost = useMemo(() => {
    const clone = source.clone(true);
    clone.traverse((child) => {
      if (child instanceof THREE.Mesh) {
        child.material = new THREE.MeshStandardMaterial({
          color: "#6c63ff", transparent: true, opacity: 0.16,
          depthWrite: false, side: THREE.DoubleSide,
        });
      }
    });
    return clone;
  }, [source]);
  return <primitive object={ghost} />;
}

function GhostPreview({
  model, landmarks,
}: {
  model: THREE.Object3D | null;
  landmarks: LandmarkPositions;
}) {
  return (
    <div style={{
      position: "absolute", right: 10, bottom: 10,
      width: 180, height: 240, borderRadius: 10, overflow: "hidden",
      border: "1px solid #2a2a3d", background: "rgba(8,8,18,0.92)",
      pointerEvents: "none", zIndex: 10,
    }}>
      <div style={{
        position: "absolute", top: 4, left: 8, zIndex: 1,
        fontSize: 9, fontWeight: 700, letterSpacing: "0.06em", color: "#6c63ff",
      }}>
        DEPTH PREVIEW
      </div>
      <Canvas
        orthographic
        camera={{ position: [3, 1.6, 3], zoom: 95, near: 0.01, far: 100 }}
        onCreated={({ camera }) => camera.lookAt(0, 1, 0)}
      >
        <ambientLight intensity={0.8} />
        <directionalLight position={[5, 10, 5]} intensity={0.8} />
        {model && <GhostBody source={model} />}
        <Skeleton landmarks={landmarks} />
        {LANDMARKS.map(({ key, color }) => (
          <mesh key={key} position={landmarks[key]} renderOrder={999}>
            <sphereGeometry args={[0.035, 12, 12]} />
            <meshStandardMaterial color={color} emissive={color} emissiveIntensity={0.5} depthTest={false} />
          </mesh>
        ))}
      </Canvas>
    </div>
  );
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
  const [selectedKey, setSelectedKey] = useState<keyof LandmarkPositions | null>(null);
  const [bbox, setBbox]               = useState<THREE.Box3 | null>(null);
  const [model, setModel]             = useState<THREE.Object3D | null>(null);

  const handleModelReady = useCallback((o: THREE.Object3D) => setModel(o), []);

  const [depthLost, setDepthLost] = useState<Record<string, boolean>>({});
  const [pulseKey, setPulseKey]   = useState<keyof LandmarkPositions | null>(null);

  const handleDragStart = useCallback((key: keyof LandmarkPositions) => {
    setSelectedKey(key);
  }, []);

  // During a drag only x/y move; depth is left alone until the drop.
  const handleDrag = useCallback((key: keyof LandmarkPositions, x: number, y: number) => {
    setLandmarks((prev) => prev
      ? { ...prev, [key]: [x, y, prev[key][2]] as [number, number, number] }
      : prev);
  }, []);

  // On drop, raycast through the mesh and centre the handle's depth.
  const handleDragEnd = useCallback((key: keyof LandmarkPositions, x: number, y: number) => {
    const fallbackZ = landmarks?.[key]?.[2] ?? 0;
    const snap = model
      ? snapDepthToMeshCenter(model, x, y, fallbackZ)
      : { z: fallbackZ, hit: true };
    setLandmarks((prev) => prev
      ? { ...prev, [key]: [x, y, snap.z] as [number, number, number] }
      : prev);
    setDepthLost((d) => ({ ...d, [key]: !snap.hit }));
  }, [landmarks, model]);

  // Arrow keys nudge the selected handle (Shift = coarse); depth re-snaps after.
  useEffect(() => {
    if (!selectedKey) return;
    const onKey = (e: KeyboardEvent) => {
      const step = e.shiftKey ? 0.05 : 0.01;
      let dx = 0, dy = 0;
      if (e.key === "ArrowLeft")       dx = -step;
      else if (e.key === "ArrowRight") dx =  step;
      else if (e.key === "ArrowUp")    dy =  step;
      else if (e.key === "ArrowDown")  dy = -step;
      else return;
      e.preventDefault();
      setLandmarks((prev) => {
        if (!prev) return prev;
        const nx = prev[selectedKey][0] + dx;
        const ny = prev[selectedKey][1] + dy;
        const z  = model
          ? snapDepthToMeshCenter(model, nx, ny, prev[selectedKey][2]).z
          : prev[selectedKey][2];
        return { ...prev, [selectedKey]: [nx, ny, z] as [number, number, number] };
      });
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [selectedKey, model]);

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
    if (!rigId) setLandmarks(defaultLandmarks(b));
  }, [rigId]);

  const pulseTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const handleSelectRow = useCallback((key: keyof LandmarkPositions) => {
    setSelectedKey(key);
    setPulseKey(key);
    if (pulseTimer.current) clearTimeout(pulseTimer.current);
    pulseTimer.current = setTimeout(() => setPulseKey(null), 700);
  }, []);
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
          LANDMARKS
        </div>
        <div style={{
          background: "rgba(108,99,255,0.08)", border: "1px solid rgba(108,99,255,0.35)",
          borderRadius: 8, padding: "0.6rem 0.75rem", fontSize: "0.78rem", color: "#bbb",
        }}>
          Drag any handle to reposition it. Depth is set automatically on release.
          Click a row to locate its handle.
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
                return (
                  <button key={key} onClick={() => handleSelectRow(key)} style={{
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
                    {depthLost[key] && <span style={{ marginLeft: "auto", color: "#ffae00", fontSize: 11 }} title="Depth not found — drag back over the mesh">⚠</span>}
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
        flex: 1, height: 560, position: "relative",
        background: "linear-gradient(135deg,#0a0a14,#0d0d20)",
        borderRadius: 12, overflow: "hidden",
        border: "2px solid #2a2a3d",
      }}>
        <Canvas orthographic camera={{ position: [0, 1, 4], zoom: 220, near: 0.01, far: 100 }}>
          <ambientLight intensity={0.6} />
          <directionalLight position={[5, 10, 5]} intensity={1} />
          <pointLight position={[-5, 5, -5]} intensity={0.3} color="#6c63ff" />
          <Environment preset="studio" />

          <Suspense fallback={<Html center><div style={{ color: "#6c63ff" }}>Loading…</div></Html>}>
            {ext === "fbx" || ext === "obj"
              ? <FBXModel url={glbUrl} onBoundsReady={handleBoundsReady} onModelReady={handleModelReady} />
              : <GLBModel url={glbUrl} onBoundsReady={handleBoundsReady} onModelReady={handleModelReady} />
            }
          </Suspense>

          {/* Landmark spheres */}
          {landmarks && <Skeleton landmarks={landmarks} />}

          {landmarks && LANDMARKS.map(({ key, label, color }) => (
            <DraggableLandmark
              key={key}
              landmarkKey={key}
              position={landmarks[key]}
              color={color}
              label={label}
              depthLost={!!depthLost[key]}
              pulsing={pulseKey === key}
              onDragStart={handleDragStart}
              onDrag={handleDrag}
              onDragEnd={handleDragEnd}
            />
          ))}

          <Grid position={[0, 0, 0]} args={[10, 10]} cellColor="#1a1a2e" sectionColor="#2a2a3d" fadeDistance={12} infiniteGrid />
          <OrbitControls
            makeDefault
            target={[0, 1, 0]}
            enableRotate={false}
            enablePan={false}
            minZoom={80}
            maxZoom={600}
          />
        </Canvas>

        {landmarks && <GhostPreview model={model} landmarks={landmarks} />}
      </div>
    </div>
  );
}
