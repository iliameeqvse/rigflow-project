"use client";

import React, { Suspense } from "react";
import { Canvas, useLoader } from "@react-three/fiber";
import {
  OrbitControls,
  Environment,
  useGLTF,
  Grid,
  GizmoHelper,
  GizmoViewport,
  Html,
  Center,
} from "@react-three/drei";
import { FBXLoader } from "three-stdlib";

// ── Sub-component: loads and displays the model ──────────────────────────────
// Backend currently returns an FBX file (Kaydara FBX header), so we use FBXLoader.
function RiggedModel({ url }: { url: string }) {
  const fbx = useLoader(FBXLoader, url);
  return (
    <Center>
      <primitive object={fbx} />
    </Center>
  );
}

// ── Loading spinner shown while GLTF loads ────────────────────────────────────
function LoadingFallback() {
  return (
    <Html center>
      <div
        style={{
          color: "#6c63ff",
          fontSize: "14px",
          textAlign: "center",
          fontFamily: "sans-serif",
        }}
      >
        <div>⚙️ Loading model...</div>
      </div>
    </Html>
  );
}

// ── Error boundary so a bad/unsupported file doesn't crash the whole page ────
class ModelErrorBoundary extends React.Component<
  { children: React.ReactNode },
  { hasError: boolean }
> {
  constructor(props: { children: React.ReactNode }) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError() {
    return { hasError: true };
  }

  componentDidCatch(error: unknown) {
    console.error("ModelViewer failed to load model:", error);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div
          style={{
            width: "100%",
            height: "100%",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            background: "#0a0a14",
            color: "#ff6b6b",
            fontSize: "0.9rem",
            textAlign: "center",
            padding: "1.5rem",
          }}
        >
          We couldn&apos;t render a preview for this file yet, but your rig was
          created successfully.
        </div>
      );
    }
    return this.props.children;
  }
}

// ── Main viewer component ─────────────────────────────────────────────────────
interface ModelViewerProps {
  glbUrl: string;
  height?: number;
}

export function ModelViewer({ glbUrl, height = 500 }: ModelViewerProps) {
  return (
    <div
      style={{
        width: "100%",
        height: `${height}px`,
        background: "linear-gradient(135deg, #0a0a14, #0d0d20)",
        borderRadius: "12px",
        overflow: "hidden",
        border: "1px solid #2a2a3d",
      }}
    >
      <ModelErrorBoundary>
        <Canvas
          camera={{
            position: [0, 1.5, 4], // camera: slightly above, 4 units back
            fov: 45,
          }}
          shadows
        >
        {/* Lighting */}
        <ambientLight intensity={0.5} />
        <directionalLight
          position={[5, 10, 5]}
          intensity={1}
          castShadow
          shadow-mapSize-width={2048}
          shadow-mapSize-height={2048}
        />
        <pointLight position={[-5, 5, -5]} intensity={0.3} color="#6c63ff" />

          {/* Environment map for realistic reflections */}
          <Environment preset="studio" />

          {/* The actual model, wrapped in Suspense for async loading */}
          <Suspense fallback={<LoadingFallback />}>
            <RiggedModel url={glbUrl} />
          </Suspense>

          {/* Ground grid */}
          <Grid
            position={[0, 0, 0]}
            args={[20, 20]}
            cellColor="#1a1a2e"
            sectionColor="#2a2a3d"
            fadeDistance={15}
            infiniteGrid
          />

          {/* Mouse orbit + zoom + pan */}
          <OrbitControls
            makeDefault
            minDistance={1}
            maxDistance={20}
            target={[0, 1, 0]} // orbit around chest height
          />

          {/* 3D axis indicator in corner */}
          <GizmoHelper alignment="bottom-right" margin={[80, 80]}>
            <GizmoViewport
              axisColors={["#ff4444", "#44ff44", "#4444ff"]}
              labelColor="white"
            />
          </GizmoHelper>
        </Canvas>
      </ModelErrorBoundary>
    </div>
  );
}
