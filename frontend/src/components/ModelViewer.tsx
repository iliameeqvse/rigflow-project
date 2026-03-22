"use client";

import React, { Suspense, useEffect, useRef, useState } from "react";
import { Canvas, useLoader, useFrame, useThree } from "@react-three/fiber";
import {
  OrbitControls,
  Environment,
  Grid,
  GizmoHelper,
  GizmoViewport,
  Html,
  Center,
  useGLTF,
} from "@react-three/drei";
import { FBXLoader } from "three-stdlib";
import * as THREE from "three";

// ─────────────────────────────────────────────────────────────────────────────
// SkeletonHelper overlay — renders bone lines over the model
// ─────────────────────────────────────────────────────────────────────────────
function SkeletonOverlay({ root }: { root: THREE.Object3D }) {
  const { scene } = useThree();
  const helperRef = useRef<THREE.SkeletonHelper | null>(null);

  useEffect(() => {
    const helper = new THREE.SkeletonHelper(root);
    // Make bones bright and thick so they're easy to see
    (helper.material as THREE.LineBasicMaterial).color.set(0x00d4ff);
    (helper.material as THREE.LineBasicMaterial).linewidth = 2;
    helper.visible = true;
    scene.add(helper);
    helperRef.current = helper;

    return () => {
      scene.remove(helper);
      helper.geometry.dispose();
      (helper.material as THREE.LineBasicMaterial).dispose();
      helperRef.current = null;
    };
  }, [root, scene]);

  return null;
}

// ─────────────────────────────────────────────────────────────────────────────
// FBX model
// ─────────────────────────────────────────────────────────────────────────────
function FBXModel({
  url,
  playAnimation,
  showSkeleton,
  waveClip,
  onReady,
}: {
  url: string;
  playAnimation: boolean;
  showSkeleton: boolean;
  waveClip: THREE.AnimationClip | null;
  onReady?: (hasEmbedded: boolean) => void;
}) {
  const fbx    = useLoader(FBXLoader, url);
  const mixer  = useRef<THREE.AnimationMixer | null>(null);
  const action = useRef<THREE.AnimationAction | null>(null);

  useEffect(() => {
    const m = new THREE.AnimationMixer(fbx);
    mixer.current = m;
    const hasEmbedded = fbx.animations.length > 0;
    onReady?.(hasEmbedded);

    const clip = hasEmbedded
      ? fbx.animations[0]
      : waveClip
      ? retargetClip(waveClip, fbx)
      : null;

    if (clip) action.current = m.clipAction(clip);

    return () => {
      m.stopAllAction();
      m.uncacheRoot(fbx);
      mixer.current = null;
      action.current = null;
    };
  }, [fbx, waveClip]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!action.current) return;
    if (playAnimation) action.current.reset().play();
    else               action.current.stop();
  }, [playAnimation]);

  useFrame((_s, delta) => {
    if (mixer.current && playAnimation) mixer.current.update(delta);
  });

  return (
    <Center>
      <primitive object={fbx} />
      {showSkeleton && <SkeletonOverlay root={fbx} />}
    </Center>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// GLB model
// ─────────────────────────────────────────────────────────────────────────────
function GLBModel({
  url,
  playAnimation,
  showSkeleton,
  waveClip,
  onReady,
}: {
  url: string;
  playAnimation: boolean;
  showSkeleton: boolean;
  waveClip: THREE.AnimationClip | null;
  onReady?: (hasEmbedded: boolean) => void;
}) {
  const { scene, animations } = useGLTF(url);
  const mixer  = useRef<THREE.AnimationMixer | null>(null);
  const action = useRef<THREE.AnimationAction | null>(null);

  useEffect(() => {
    const m = new THREE.AnimationMixer(scene);
    mixer.current = m;
    const hasEmbedded = animations.length > 0;
    onReady?.(hasEmbedded);

    const clip = hasEmbedded
      ? animations[0]
      : waveClip
      ? retargetClip(waveClip, scene)
      : null;

    if (clip) action.current = m.clipAction(clip);

    return () => {
      m.stopAllAction();
      m.uncacheRoot(scene);
      mixer.current = null;
      action.current = null;
    };
  }, [scene, animations, waveClip]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!action.current) return;
    if (playAnimation) action.current.reset().play();
    else               action.current.stop();
  }, [playAnimation]);

  useFrame((_s, delta) => {
    if (mixer.current && playAnimation) mixer.current.update(delta);
  });

  return (
    <Center>
      <primitive object={scene} />
      {showSkeleton && <SkeletonOverlay root={scene} />}
    </Center>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Retargeting helper (Mixamo → model skeleton)
// ─────────────────────────────────────────────────────────────────────────────
function normalizeName(name: string): string {
  return name.replace(/^mixamorig:/i, "").replace(/[_.\s]/g, "").toLowerCase();
}

function buildBoneMap(target: THREE.Object3D, sourceNames: string[]) {
  const targetBones: THREE.Bone[] = [];
  target.traverse((child) => {
    if (child instanceof THREE.Bone) targetBones.push(child);
  });
  const map: Record<string, THREE.Bone> = {};
  for (const src of sourceNames) {
    const norm = normalizeName(src);
    let match = targetBones.find((b) => normalizeName(b.name) === norm);
    if (!match) {
      match = targetBones.find(
        (b) => normalizeName(b.name).includes(norm) || norm.includes(normalizeName(b.name))
      );
    }
    if (match) map[src] = match;
  }
  return map;
}

function retargetClip(clip: THREE.AnimationClip, target: THREE.Object3D): THREE.AnimationClip {
  const sourceNames = clip.tracks.map((t) => t.name.split(".")[0]);
  const boneMap = buildBoneMap(target, sourceNames);
  const newTracks: THREE.KeyframeTrack[] = [];
  for (const track of clip.tracks) {
    const [boneName, property] = track.name.split(/\.(.+)/);
    const targetBone = boneMap[boneName];
    if (!targetBone) continue;
    const clone = track.clone();
    clone.name = `${targetBone.name}.${property}`;
    newTracks.push(clone);
  }
  return new THREE.AnimationClip(clip.name, clip.duration, newTracks);
}

// ─────────────────────────────────────────────────────────────────────────────
// Wave clip loader
// ─────────────────────────────────────────────────────────────────────────────
function WaveLoader({ onLoaded }: { onLoaded: (clip: THREE.AnimationClip) => void }) {
  const waveFbx = useLoader(FBXLoader, "/animations/wave.fbx");
  useEffect(() => {
    if (waveFbx.animations.length > 0) onLoaded(waveFbx.animations[0]);
  }, [waveFbx]); // eslint-disable-line react-hooks/exhaustive-deps
  return null;
}

// ─────────────────────────────────────────────────────────────────────────────
// Route by extension
// ─────────────────────────────────────────────────────────────────────────────
function RiggedModel({
  url, playAnimation, showSkeleton, waveClip, onReady,
}: {
  url: string;
  playAnimation: boolean;
  showSkeleton: boolean;
  waveClip: THREE.AnimationClip | null;
  onReady?: (hasEmbedded: boolean) => void;
}) {
  const ext = url.split("?")[0].split(".").pop()?.toLowerCase();
  if (ext === "fbx" || ext === "obj") {
    return <FBXModel url={url} playAnimation={playAnimation} showSkeleton={showSkeleton} waveClip={waveClip} onReady={onReady} />;
  }
  return <GLBModel url={url} playAnimation={playAnimation} showSkeleton={showSkeleton} waveClip={waveClip} onReady={onReady} />;
}

// ─────────────────────────────────────────────────────────────────────────────
// Fallbacks
// ─────────────────────────────────────────────────────────────────────────────
function LoadingFallback() {
  return (
    <Html center>
      <div style={{ color: "#6c63ff", fontSize: "14px", textAlign: "center" }}>
        ⚙️ Loading model...
      </div>
    </Html>
  );
}

class ModelErrorBoundary extends React.Component<
  { children: React.ReactNode },
  { hasError: boolean }
> {
  constructor(props: { children: React.ReactNode }) {
    super(props);
    this.state = { hasError: false };
  }
  static getDerivedStateFromError() { return { hasError: true }; }
  componentDidCatch(err: unknown) { console.error("ModelViewer:", err); }
  render() {
    if (this.state.hasError) {
      return (
        <div style={{
          width: "100%", height: "100%", display: "flex",
          alignItems: "center", justifyContent: "center",
          background: "#0a0a14", color: "#ff6b6b",
          fontSize: "0.9rem", textAlign: "center", padding: "1.5rem",
        }}>
          Couldn&apos;t render a preview — but your rig was saved successfully.
        </div>
      );
    }
    return this.props.children;
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Public API
// ─────────────────────────────────────────────────────────────────────────────
interface ModelViewerProps {
  glbUrl: string;
  height?: number;
  playAnimation?: boolean;
  showSkeleton?: boolean;
  onReady?: (hasEmbedded: boolean) => void;
}

export function ModelViewer({
  glbUrl,
  height = 500,
  playAnimation = false,
  showSkeleton = false,
  onReady,
}: ModelViewerProps) {
  const [waveClip, setWaveClip] = useState<THREE.AnimationClip | null>(null);

  return (
    <div style={{
      width: "100%", height: `${height}px`,
      background: "linear-gradient(135deg, #0a0a14, #0d0d20)",
      borderRadius: "12px", overflow: "hidden",
      border: "1px solid #2a2a3d",
    }}>
      <ModelErrorBoundary>
        <Canvas camera={{ position: [0, 1.5, 4], fov: 45 }} shadows>
          <ambientLight intensity={0.5} />
          <directionalLight
            position={[5, 10, 5]} intensity={1} castShadow
            shadow-mapSize-width={2048} shadow-mapSize-height={2048}
          />
          <pointLight position={[-5, 5, -5]} intensity={0.3} color="#6c63ff" />
          <Environment preset="studio" />

          <Suspense fallback={<LoadingFallback />}>
            <WaveLoader onLoaded={setWaveClip} />
            <RiggedModel
              url={glbUrl}
              playAnimation={playAnimation}
              showSkeleton={showSkeleton}
              waveClip={waveClip}
              onReady={onReady}
            />
          </Suspense>

          <Grid
            position={[0, 0, 0]} args={[20, 20]}
            cellColor="#1a1a2e" sectionColor="#2a2a3d"
            fadeDistance={15} infiniteGrid
          />
          <OrbitControls makeDefault minDistance={1} maxDistance={20} target={[0, 1, 0]} />
          <GizmoHelper alignment="bottom-right" margin={[80, 80]}>
            <GizmoViewport axisColors={["#ff4444", "#44ff44", "#4444ff"]} labelColor="white" />
          </GizmoHelper>
        </Canvas>
      </ModelErrorBoundary>
    </div>
  );
}