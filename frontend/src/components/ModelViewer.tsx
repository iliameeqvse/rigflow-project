"use client";

import { Suspense, useEffect, useRef } from "react";
import { Canvas } from "@react-three/fiber";
import {
  OrbitControls,
  Environment,
  useGLTF,
  useAnimations,
  Grid,
  GizmoHelper,
  GizmoViewport,
  Html,
  Center,
} from "@react-three/drei";

// ── Sub-component: loads and displays the GLTF model ─────────────────────────
function GLTFModel({ url }: { url: string }) {
  const { scene, animations } = useGLTF(url);
  const { actions } = useAnimations(animations, scene);

  useEffect(() => {
    // Auto-play the first animation (usually idle/T-pose)
    const firstName = Object.keys(actions)[0];
    if (firstName) {
      actions[firstName]?.reset().play();
    }
  }, [actions]);

  return (
    <Center>
      <primitive object={scene} />
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
          <GLTFModel url={glbUrl} />
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
    </div>
  );
}
