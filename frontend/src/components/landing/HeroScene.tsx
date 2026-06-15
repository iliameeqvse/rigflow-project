"use client";

import { Canvas, useFrame } from "@react-three/fiber";
import { useMemo, useRef, useState, useEffect } from "react";
import * as THREE from "three";

const ACCENT = "#ccff00";
const ACCENT_SOFT = "#ddff66";

// Joint coordinates for a stylized humanoid skeleton (y-up).
const J = {
  hip:       [0, 0, 0],
  spine1:    [0, 0.35, 0],
  spine2:    [0, 0.7, 0],
  chest:     [0, 1.05, 0],
  neck:      [0, 1.3, 0],
  head:      [0, 1.6, 0],
  shoulderL: [0.28, 1.2, 0],
  elbowL:    [0.58, 0.85, 0.02],
  handL:     [0.72, 0.45, 0.05],
  shoulderR: [-0.28, 1.2, 0],
  elbowR:    [-0.58, 0.85, 0.02],
  handR:     [-0.72, 0.45, 0.05],
  hipL:      [0.16, -0.05, 0],
  kneeL:     [0.2, -0.65, 0.05],
  footL:     [0.22, -1.2, 0.12],
  hipR:      [-0.16, -0.05, 0],
  kneeR:     [-0.2, -0.65, 0.05],
  footR:     [-0.22, -1.2, 0.12],
} as const;

type Joint = keyof typeof J;

const BONES: [Joint, Joint, number?][] = [
  ["hip", "spine1", 0.05],
  ["spine1", "spine2", 0.05],
  ["spine2", "chest", 0.05],
  ["chest", "neck", 0.035],
  ["neck", "head", 0.04],
  ["chest", "shoulderL", 0.04],
  ["shoulderL", "elbowL", 0.035],
  ["elbowL", "handL", 0.03],
  ["chest", "shoulderR", 0.04],
  ["shoulderR", "elbowR", 0.035],
  ["elbowR", "handR", 0.03],
  ["hip", "hipL", 0.04],
  ["hipL", "kneeL", 0.045],
  ["kneeL", "footL", 0.035],
  ["hip", "hipR", 0.04],
  ["hipR", "kneeR", 0.045],
  ["kneeR", "footR", 0.035],
];

const JOINT_SIZES: Partial<Record<Joint, number>> = {
  head: 0.13,
  hip: 0.075,
  chest: 0.07,
};

function boneTransform(from: readonly number[], to: readonly number[]) {
  const start = new THREE.Vector3(from[0], from[1], from[2]);
  const end = new THREE.Vector3(to[0], to[1], to[2]);
  const mid = new THREE.Vector3().addVectors(start, end).multiplyScalar(0.5);
  const length = start.distanceTo(end);
  const dir = new THREE.Vector3().subVectors(end, start).normalize();
  const quaternion = new THREE.Quaternion().setFromUnitVectors(
    new THREE.Vector3(0, 1, 0),
    dir,
  );
  return { position: mid.toArray() as [number, number, number], quaternion, length };
}

function Bone({
  from,
  to,
  radius = 0.04,
  color = ACCENT,
  glow = false,
}: {
  from: readonly number[];
  to: readonly number[];
  radius?: number;
  color?: string;
  glow?: boolean;
}) {
  const { position, quaternion, length } = useMemo(
    () => boneTransform(from, to),
    [from, to],
  );

  return (
    <group position={position} quaternion={quaternion}>
      <mesh>
        <cylinderGeometry args={[radius, radius * 0.55, length, 10]} />
        <meshBasicMaterial color={color} toneMapped={false} />
      </mesh>
      {glow && (
        <mesh>
          <cylinderGeometry args={[radius * 2.2, radius * 1.4, length, 10]} />
          <meshBasicMaterial
            color={color}
            transparent
            opacity={0.18}
            depthWrite={false}
            toneMapped={false}
          />
        </mesh>
      )}
    </group>
  );
}

function Joint({
  position,
  size = 0.05,
}: {
  position: readonly number[];
  size?: number;
}) {
  return (
    <group position={position as [number, number, number]}>
      <mesh>
        <sphereGeometry args={[size, 20, 20]} />
        <meshBasicMaterial color={ACCENT_SOFT} toneMapped={false} />
      </mesh>
      <mesh>
        <sphereGeometry args={[size * 1.8, 20, 20]} />
        <meshBasicMaterial
          color={ACCENT}
          transparent
          opacity={0.18}
          depthWrite={false}
          toneMapped={false}
        />
      </mesh>
    </group>
  );
}

function Skeleton({ mouse }: { mouse: React.RefObject<{ x: number; y: number }> }) {
  const group = useRef<THREE.Group>(null);

  useFrame((_, delta) => {
    if (!group.current) return;
    group.current.rotation.y += delta * 0.18;

    const t = performance.now() * 0.001;
    const targetX = (mouse.current?.y ?? 0) * 0.25 + Math.sin(t * 0.6) * 0.02;
    const targetTilt = (mouse.current?.x ?? 0) * 0.2;
    group.current.rotation.x += (targetX - group.current.rotation.x) * 0.05;
    group.current.rotation.z += (targetTilt - group.current.rotation.z) * 0.05;
    group.current.position.y = Math.sin(t * 0.8) * 0.04;
  });

  return (
    <group ref={group}>
      {BONES.map(([a, b, r], i) => (
        <Bone key={i} from={J[a]} to={J[b]} radius={r ?? 0.04} glow />
      ))}
      {(Object.keys(J) as Joint[]).map((name) => (
        <Joint key={name} position={J[name]} size={JOINT_SIZES[name] ?? 0.05} />
      ))}
    </group>
  );
}

function GroundGrid() {
  return (
    <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -1.5, 0]}>
      <planeGeometry args={[8, 8, 24, 24]} />
      <meshBasicMaterial
        color={ACCENT}
        wireframe
        transparent
        opacity={0.06}
        depthWrite={false}
        toneMapped={false}
      />
    </mesh>
  );
}

function Particles({ count = 60 }: { count?: number }) {
  const ref = useRef<THREE.Points>(null);
  /* eslint-disable react-hooks/purity */
  const positions = useMemo(() => {
    const arr = new Float32Array(count * 3);
    for (let i = 0; i < count; i++) {
      const r = 1.8 + Math.random() * 1.4;
      const theta = Math.random() * Math.PI * 2;
      const phi = Math.acos(2 * Math.random() - 1);
      arr[i * 3] = r * Math.sin(phi) * Math.cos(theta);
      arr[i * 3 + 1] = r * Math.sin(phi) * Math.sin(theta) - 0.3;
      arr[i * 3 + 2] = r * Math.cos(phi);
    }
    return arr;
  }, [count]);
  /* eslint-enable react-hooks/purity */

  useFrame((_, delta) => {
    if (ref.current) ref.current.rotation.y += delta * 0.06;
  });

  return (
    <points ref={ref}>
      <bufferGeometry>
        <bufferAttribute attach="attributes-position" args={[positions, 3]} />
      </bufferGeometry>
      <pointsMaterial
        size={0.025}
        color={ACCENT_SOFT}
        transparent
        opacity={0.55}
        depthWrite={false}
        toneMapped={false}
      />
    </points>
  );
}

export default function HeroScene() {
  const mouse = useRef({ x: 0, y: 0 });
  const [ready, setReady] = useState(false);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setReady(true);
    const onMove = (e: MouseEvent) => {
      mouse.current.x = (e.clientX / window.innerWidth - 0.5) * 2;
      mouse.current.y = (e.clientY / window.innerHeight - 0.5) * 2;
    };
    window.addEventListener("mousemove", onMove);
    return () => window.removeEventListener("mousemove", onMove);
  }, []);

  if (!ready) return null;

  return (
    <Canvas
      camera={{ position: [0, 0.2, 3.6], fov: 38 }}
      gl={{ antialias: true, alpha: true }}
      dpr={[1, 1.75]}
    >
      <color attach="background" args={["#0b0e14"]} />
      <fog attach="fog" args={["#0b0e14", 4, 9]} />
      <Skeleton mouse={mouse} />
      <Particles />
      <GroundGrid />
    </Canvas>
  );
}
