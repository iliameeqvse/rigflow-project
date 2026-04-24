"use client";

import { useEffect, useRef, useState, Suspense } from "react";
import { Canvas, useFrame } from "@react-three/fiber";
import {
  OrbitControls, Environment, Grid, Html, GizmoHelper, GizmoViewport,
} from "@react-three/drei";
import { FBXLoader, GLTFLoader, SkeletonUtils } from "three-stdlib";
import * as THREE from "three";

import { listAnimations, type Animation as LibAnim } from "@/lib/api";

const TARGET_HEIGHT = 2.0;

interface Props {
  rigGlbUrl: string;
  /** Mixamo → DEF bone-name map. Comes from the rig's `bone_mapping` field. */
  boneMapping: Record<string, string>;
  height?: number;
}

// ── Clip remapping ──────────────────────────────────────────────────────────
// Animation files arrive with bone names from the source rig (Mixamo uses
// "mixamorig:Hips"; Blender's FBX export uses "Armature|Hips"; some custom
// exports use plain "Hips"). Our rig uses DEF-spine, DEF-upper_arm.L, etc.
// Re-point each track from the source bone to the corresponding DEF bone.
function remapClipToRig(
  clip: THREE.AnimationClip,
  mixamoToDef: Record<string, string>,
): THREE.AnimationClip {
  const tracks: THREE.KeyframeTrack[] = [];
  let matched = 0;
  for (const track of clip.tracks) {
    const dot = track.name.lastIndexOf(".");
    if (dot < 0) { tracks.push(track); continue; }
    const bone = track.name.slice(0, dot);
    const prop = track.name.slice(dot + 1);
    // Strip common source namespaces: "mixamorig:Hips" | "Armature|Hips" → "Hips"
    const clean = bone.replace(/^.*[:|]/, "");
    const mapped = mixamoToDef[clean] ?? mixamoToDef[bone];
    if (!mapped) continue;
    const nt = track.clone();
    nt.name = `${mapped}.${prop}`;
    tracks.push(nt);
    matched++;
  }
  const out = new THREE.AnimationClip(clip.name, clip.duration, tracks);
  // @ts-expect-error — attaching diagnostic count for the UI.
  out.__matched = matched;
  return out;
}

async function loadClip(url: string): Promise<THREE.AnimationClip | null> {
  const ext = url.split("?")[0].split(".").pop()?.toLowerCase();
  if (ext === "fbx") {
    const fbx = await new FBXLoader().loadAsync(url);
    return fbx.animations?.[0] ?? null;
  }
  const gltf = await new GLTFLoader().loadAsync(url);
  return gltf.animations?.[0] ?? null;
}

// ── Stage: loads the rig, fits it, runs the mixer ───────────────────────────
function Stage({
  rigGlbUrl,
  clip,
}: { rigGlbUrl: string; clip: THREE.AnimationClip | null }) {
  const [rig, setRig] = useState<THREE.Object3D | null>(null);
  const mixerRef = useRef<THREE.AnimationMixer | null>(null);

  useEffect(() => {
    let cancelled = false;
    // Fresh loader (bypasses drei's useGLTF cache) + SkeletonUtils.clone so
    // the AnimationMixer has its own bone copy — no interference with the
    // preview rig used elsewhere on the page.
    new GLTFLoader().loadAsync(rigGlbUrl).then((gltf) => {
      if (cancelled) return;
      const obj = SkeletonUtils.clone(gltf.scene);
      // Auto-fit to 2 units tall, XZ-centred, feet at Y=0.
      const box = new THREE.Box3().setFromObject(obj);
      const size = new THREE.Vector3();
      box.getSize(size);
      const max = Math.max(size.x, size.y, size.z);
      if (max > 0) obj.scale.setScalar(TARGET_HEIGHT / max);
      obj.updateMatrixWorld(true);
      const box2 = new THREE.Box3().setFromObject(obj);
      const c = new THREE.Vector3();
      box2.getCenter(c);
      obj.position.x -= c.x;
      obj.position.z -= c.z;
      obj.position.y -= box2.min.y;
      setRig(obj);
    });
    return () => { cancelled = true; };
  }, [rigGlbUrl]);

  useEffect(() => {
    mixerRef.current?.stopAllAction();
    mixerRef.current = null;
    if (!rig || !clip) return;
    const mixer = new THREE.AnimationMixer(rig);
    mixer.clipAction(clip).play();
    mixerRef.current = mixer;
    return () => { mixer.stopAllAction(); };
  }, [rig, clip]);

  useFrame((_, dt) => mixerRef.current?.update(dt));

  return rig ? <primitive object={rig} /> : null;
}

// ── Public component ────────────────────────────────────────────────────────
export function AnimationPlayer({ rigGlbUrl, boneMapping, height = 540 }: Props) {
  const [library, setLibrary]       = useState<LibAnim[]>([]);
  const [libraryError, setLibErr]   = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string>("");
  const [clip, setClip]             = useState<THREE.AnimationClip | null>(null);
  const [loadingMsg, setLoadingMsg] = useState<string>("");
  const [statusMsg, setStatusMsg]   = useState<string>("");
  const [error, setError]           = useState<string | null>(null);

  useEffect(() => {
    listAnimations()
      .then(({ data }) => setLibrary(data))
      .catch(() => setLibErr("Could not load the animation library."));
  }, []);

  const playFromUrl = async (url: string, label: string) => {
    setLoadingMsg(`Loading ${label}…`);
    setStatusMsg("");
    setError(null);
    setClip(null);
    try {
      const raw = await loadClip(url);
      if (!raw) {
        setError("No animation tracks found in the file.");
        setLoadingMsg("");
        return;
      }
      const remapped = remapClipToRig(raw, boneMapping);
      // @ts-expect-error — diagnostic count set above.
      const matched: number = remapped.__matched ?? remapped.tracks.length;
      if (remapped.tracks.length === 0) {
        setError("No bone tracks matched this rig — animation looks incompatible.");
        setLoadingMsg("");
        return;
      }
      setClip(remapped);
      setLoadingMsg("");
      setStatusMsg(`Playing · ${matched} bone track${matched === 1 ? "" : "s"} matched`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load animation.");
      setLoadingMsg("");
    }
  };

  const handleSelect = async (id: string) => {
    setSelectedId(id);
    if (!id) {
      setClip(null); setStatusMsg(""); setError(null);
      return;
    }
    const anim = library.find((a) => a.id === id);
    if (!anim?.gltf_file) {
      setError("Animation file URL is missing.");
      return;
    }
    await playFromUrl(anim.gltf_file, anim.name);
  };

  const handleLocalFile = async (file: File) => {
    setSelectedId("");
    const url = URL.createObjectURL(file);
    await playFromUrl(url, file.name);
    // Not revoking the URL — the clip may still reference blob data.
  };

  const stop = () => {
    setClip(null);
    setSelectedId("");
    setStatusMsg("");
    setError(null);
  };

  const controlStyle: React.CSSProperties = {
    padding: "0.55rem 0.9rem",
    background: "#12121a",
    border: "1px solid #2a2a3d",
    borderRadius: 8,
    color: "#ccc",
    fontSize: ".9rem",
  };

  return (
    <div>
      <div
        style={{
          display: "flex", gap: ".65rem", alignItems: "center",
          flexWrap: "wrap", marginBottom: "1rem",
        }}
      >
        <select
          value={selectedId}
          onChange={(e) => handleSelect(e.target.value)}
          style={{ ...controlStyle, cursor: "pointer", minWidth: 240 }}
        >
          <option value="">— Pick from library —</option>
          {library.map((a) => (
            <option key={a.id} value={a.id}>
              {a.name}
              {a.is_looping ? "  · loop" : ""}
            </option>
          ))}
        </select>

        <label style={{ ...controlStyle, cursor: "pointer" }}>
          📁 Local file…
          <input
            type="file"
            accept=".glb,.gltf,.fbx"
            style={{ display: "none" }}
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) handleLocalFile(f);
            }}
          />
        </label>

        {clip && (
          <button
            type="button"
            onClick={stop}
            style={{
              ...controlStyle,
              cursor: "pointer",
              background: "transparent",
              borderColor: "#f87171",
              color: "#f87171",
            }}
          >
            ⏹ Stop
          </button>
        )}
      </div>

      {libraryError && (
        <p style={{ color: "#f87171", fontSize: ".85rem", marginBottom: ".5rem" }}>
          {libraryError}
        </p>
      )}
      {loadingMsg && (
        <p style={{ color: "#a0a0c0", fontSize: ".85rem", marginBottom: ".5rem" }}>
          {loadingMsg}
        </p>
      )}
      {statusMsg && !loadingMsg && (
        <p style={{ color: "#00d4ff", fontSize: ".85rem", marginBottom: ".5rem" }}>
          {statusMsg}
        </p>
      )}
      {error && (
        <p style={{ color: "#f87171", fontSize: ".85rem", marginBottom: ".5rem" }}>
          {error}
        </p>
      )}

      <div
        style={{
          height,
          borderRadius: 12,
          overflow: "hidden",
          background: "linear-gradient(135deg,#0a0a14,#0d0d20)",
          border: "1px solid #2a2a3d",
        }}
      >
        <Canvas camera={{ position: [0, 1.4, 3.5], fov: 45 }} shadows>
          <ambientLight intensity={0.5} />
          <directionalLight position={[5, 10, 5]} intensity={1} castShadow />
          <pointLight position={[-5, 5, -5]} intensity={0.3} color="#6c63ff" />
          <Environment preset="studio" />

          <Suspense
            fallback={
              <Html center>
                <div style={{ color: "#6c63ff", fontSize: 14 }}>⚙️ Loading…</div>
              </Html>
            }
          >
            <Stage rigGlbUrl={rigGlbUrl} clip={clip} />
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
            <GizmoViewport
              axisColors={["#ff4444", "#44ff44", "#4444ff"]}
              labelColor="white"
            />
          </GizmoHelper>
        </Canvas>
      </div>
    </div>
  );
}
