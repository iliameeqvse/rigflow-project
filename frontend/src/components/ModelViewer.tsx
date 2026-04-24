"use client";

import React, { Suspense, useEffect, useRef } from "react";
import { Canvas, useLoader, useThree, useFrame } from "@react-three/fiber";
import {
  OrbitControls, Environment, Grid, GizmoHelper, GizmoViewport, Html,
} from "@react-three/drei";
import { FBXLoader } from "three-stdlib";
import { useGLTF } from "@react-three/drei";
import * as THREE from "three";

// ─────────────────────────────────────────────────────────────────────────────
// Target display height in Three.js units (camera is set up for ~2 unit models)
// ─────────────────────────────────────────────────────────────────────────────
const TARGET_HEIGHT = 2.0;

// ─────────────────────────────────────────────────────────────────────────────
// AutoFit — wraps any loaded Object3D, normalises its scale and
// translates it so its feet sit at Y=0 and it's centred on XZ.
// Works for any unit system (cm, mm, m, inches) and any up-axis.
// ─────────────────────────────────────────────────────────────────────────────
function AutoFit({
  object,
  onFitted,
}: {
  object: THREE.Object3D;
  onFitted?: () => void;
}) {
  useEffect(() => {
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

    // Final propagation — every bone's matrixWorld is now correct
    // before SkeletonOverlay reads them in its own useEffect
    object.updateMatrixWorld(true);
    onFitted?.();
  }, [object]); // eslint-disable-line react-hooks/exhaustive-deps

  return <primitive object={object} />;
}

// ─────────────────────────────────────────────────────────────────────────────
// Skeleton overlay — finds every SkinnedMesh and adds a SkeletonHelper
// ─────────────────────────────────────────────────────────────────────────────
function SkeletonOverlay({ object }: { object: THREE.Object3D }) {
  const { scene } = useThree();
  const helpersRef = useRef<THREE.SkeletonHelper[]>([]);

  useEffect(() => {
    helpersRef.current.forEach((h) => {
      scene.remove(h);
      h.geometry.dispose();
      (h.material as THREE.LineBasicMaterial).dispose();
    });
    helpersRef.current = [];

    // Force full world-matrix propagation so bone positions reflect
    // any scale/position changes made by AutoFit before we read them
    object.updateMatrixWorld(true);

       
    // Build helpers from both SkinnedMesh and bone roots.
    // Different exporters wire skeletons differently, so we support both paths.
    const seen = new Set<string>();

    function pushHelper(target: THREE.Object3D, key: string) {
      if (seen.has(key)) return;
      seen.add(key);
      const helper = new THREE.SkeletonHelper(target);
      (helper.material as THREE.LineBasicMaterial).color.set(0x00ffff);
      scene.add(helper);
      helpersRef.current.push(helper);
    }

    object.traverse((child) => {
      const sm = child as THREE.SkinnedMesh;
      if (!(sm.isSkinnedMesh && sm.skeleton?.bones?.length)) return;

      // Path A: helper from SkinnedMesh bind context.
      pushHelper(sm, `skinned:${sm.skeleton.uuid}`);

      // Path B fallback: helper from skeleton root bone chain.
      const rootBone = sm.skeleton.bones.find((b) => !b.parent || !(b.parent as THREE.Object3D).isBone)
        ?? sm.skeleton.bones[0];
      pushHelper(rootBone, `bone:${rootBone.uuid}`);
    });

    if (helpersRef.current.length === 0) {
      // Last fallback for unusual files: try the whole object container.
      pushHelper(object, `object:${object.uuid}`);
    }


    return () => {
      helpersRef.current.forEach((h) => {
        scene.remove(h);
        h.geometry.dispose();
        (h.material as THREE.LineBasicMaterial).dispose();
      });
      helpersRef.current = [];
    };
  }, [object, scene]);

  return null;
}

// ─────────────────────────────────────────────────────────────────────────────
// FBX model loader
// ─────────────────────────────────────────────────────────────────────────────
interface ModelProps {
  url: string;
  showSkeleton: boolean;
  playAnimation: boolean;
  onReady?: (hasEmbedded: boolean) => void;
}

function FBXModel({ url, showSkeleton, playAnimation, onReady }: ModelProps) {
  const fbx      = useLoader(FBXLoader, url);
  const mixerRef = useRef<THREE.AnimationMixer | null>(null);
  const waveRef  = useRef<THREE.AnimationMixer | null>(null);

  useEffect(() => {
    const hasEmbedded = (fbx.animations?.length ?? 0) > 0;
    onReady?.(hasEmbedded);
    if (hasEmbedded) {
      mixerRef.current = new THREE.AnimationMixer(fbx);
      mixerRef.current.clipAction(fbx.animations[0]).play();
    }
  }, [fbx]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!playAnimation) { waveRef.current?.stopAllAction(); return; }
    const loader = new FBXLoader();
    loader.load("/animations/wave.fbx", (w) => {
      if (!w.animations?.length) return;
      const m = new THREE.AnimationMixer(fbx);
      waveRef.current = m;
      m.clipAction(w.animations[0]).play();
    });
    return () => { waveRef.current?.stopAllAction(); };
  }, [playAnimation, fbx]);

  useFrame((_, dt) => {
    mixerRef.current?.update(dt);
    waveRef.current?.update(dt);
  });

  const [fitted, setFitted] = React.useState(false);

  return (
    <>
      <AutoFit object={fbx} onFitted={() => setFitted(true)} />
      {showSkeleton && fitted && <SkeletonOverlay object={fbx} />}
    </>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// GLB model loader
// ─────────────────────────────────────────────────────────────────────────────
function GLBModel({ url, showSkeleton, playAnimation, onReady }: ModelProps) {
  const { scene: gltfScene, animations } = useGLTF(url);
  const mixerRef = useRef<THREE.AnimationMixer | null>(null);
  const waveRef  = useRef<THREE.AnimationMixer | null>(null);

  useEffect(() => {
    const hasEmbedded = (animations?.length ?? 0) > 0;
    onReady?.(hasEmbedded);
    if (hasEmbedded) {
      mixerRef.current = new THREE.AnimationMixer(gltfScene);
      mixerRef.current.clipAction(animations[0]).play();
    }
  }, [gltfScene]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!playAnimation) { waveRef.current?.stopAllAction(); return; }
    const loader = new FBXLoader();
    loader.load("/animations/wave.fbx", (w) => {
      if (!w.animations?.length) return;
      const m = new THREE.AnimationMixer(gltfScene);
      waveRef.current = m;
      m.clipAction(w.animations[0]).play();
    });
    return () => { waveRef.current?.stopAllAction(); };
  }, [playAnimation, gltfScene]);

  useFrame((_, dt) => {
    mixerRef.current?.update(dt);
    waveRef.current?.update(dt);
  });

  const [fitted, setFitted] = React.useState(false);

  return (
    <>
      <AutoFit object={gltfScene} onFitted={() => setFitted(true)} />
      {showSkeleton && fitted && <SkeletonOverlay object={gltfScene} />}
    </>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Error boundary
// ─────────────────────────────────────────────────────────────────────────────
class ModelErrorBoundary extends React.Component<
  { children: React.ReactNode },
  { hasError: boolean }
> {
  constructor(props: { children: React.ReactNode }) {
    super(props);
    this.state = { hasError: false };
  }
  static getDerivedStateFromError() { return { hasError: true }; }
  componentDidCatch(e: unknown) { console.error("ModelViewer error:", e); }
  render() {
    if (this.state.hasError) {
      return (
        <div style={{
          width: "100%", height: "100%", display: "flex",
          alignItems: "center", justifyContent: "center",
          background: "#0a0a14", color: "#ff6b6b",
          fontSize: "0.9rem", textAlign: "center", padding: "1.5rem",
        }}>
          Could not render a preview — your rig was still saved successfully.
        </div>
      );
    }
    return this.props.children;
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Public component
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
  const ext       = glbUrl.split("?")[0].split(".").pop()?.toLowerCase();
  const isFbxOrObj = ext === "fbx" || ext === "obj";

  return (
    <div style={{
      width: "100%", height: `${height}px`,
      background: "linear-gradient(135deg,#0a0a14,#0d0d20)",
      borderRadius: "12px", overflow: "hidden",
      border: "1px solid #2a2a3d",
    }}>
      <ModelErrorBoundary>
        <Canvas
          camera={{ position: [0, 1.4, 3.5], fov: 45 }}
          shadows
        >
          <ambientLight intensity={0.5} />
          <directionalLight position={[5, 10, 5]} intensity={1} castShadow />
          <pointLight position={[-5, 5, -5]} intensity={0.3} color="#6c63ff" />
          <Environment preset="studio" />

          <Suspense fallback={
            <Html center>
              <div style={{ color: "#6c63ff", fontSize: 14 }}>⚙️ Loading model…</div>
            </Html>
          }>
            {isFbxOrObj
              ? <FBXModel url={glbUrl} showSkeleton={showSkeleton} playAnimation={playAnimation} onReady={onReady} />
              : <GLBModel url={glbUrl} showSkeleton={showSkeleton} playAnimation={playAnimation} onReady={onReady} />
            }
          </Suspense>

          <Grid
            position={[0, 0, 0]} args={[20, 20]}
            cellColor="#1a1a2e" sectionColor="#2a2a3d"
            fadeDistance={15} infiniteGrid
          />
          <OrbitControls
            makeDefault
            minDistance={0.5} maxDistance={20}
            target={[0, 1.0, 0]}
          />
          <GizmoHelper alignment="bottom-right" margin={[80, 80]}>
            <GizmoViewport axisColors={["#ff4444","#44ff44","#4444ff"]} labelColor="white" />
          </GizmoHelper>
        </Canvas>
      </ModelErrorBoundary>
    </div>
  );
}