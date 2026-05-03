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

// Hardcoded Mixamo → Rigify DEF map. Used as a fallback when the rig's
// bone_mapping field is empty (which happens for older rigs created before
// bone_mapping was reliably persisted, or when the Blender subprocess
// crashed before writing the bone-data JSON). Mirrors the RIGIFY_TO_MIXAMO
// dict in backend/scripts/blender_autorig.py — keep these in sync.
const FALLBACK_MIXAMO_TO_DEF: Record<string, string> = {
  Hips: "DEF-spine",
  Spine: "DEF-spine.001",
  Spine1: "DEF-spine.002",
  Spine2: "DEF-spine.003",
  Neck: "DEF-spine.004",
  Head: "DEF-spine.005",
  LeftUpLeg: "DEF-thigh.L",
  LeftLeg: "DEF-shin.L",
  LeftFoot: "DEF-foot.L",
  LeftToeBase: "DEF-toe.L",
  RightUpLeg: "DEF-thigh.R",
  RightLeg: "DEF-shin.R",
  RightFoot: "DEF-foot.R",
  RightToeBase: "DEF-toe.R",
  LeftShoulder: "DEF-shoulder.L",
  LeftArm: "DEF-upper_arm.L",
  LeftForeArm: "DEF-forearm.L",
  LeftHand: "DEF-hand.L",
  RightShoulder: "DEF-shoulder.R",
  RightArm: "DEF-upper_arm.R",
  RightForeArm: "DEF-forearm.R",
  RightHand: "DEF-hand.R",
  // Mixamo finger naming → Rigify DEF finger naming
  ...Object.fromEntries(
    (["Left", "Right"] as const).flatMap((s) => {
      const side = s === "Left" ? "L" : "R";
      const fingerMap: Record<string, string> = {
        Thumb: "thumb",
        Index: "f_index",
        Middle: "f_middle",
        Ring: "f_ring",
        Pinky: "f_pinky",
      };
      return Object.entries(fingerMap).flatMap(([mixamo, def]) =>
        [1, 2, 3].map((n) => [
          `${s}Hand${mixamo}${n}`,
          `DEF-${def}.0${n}.${side}`,
        ] as [string, string]),
      );
    }),
  ),
};

// Heuristic name-matcher for clips whose bone names follow none of the
// known conventions. Handles patterns like:
//   R_Clavicle_Bn  → DEF-shoulder.R
//   L_Arm_01_Bn    → DEF-upper_arm.L  (01/02/03 = upper/fore/hand)
//   R_Leg_02_Bn    → DEF-shin.R       (01/02/03 = thigh/shin/foot)
//   Neck_Bn        → DEF-spine.004
//   spine_03       → DEF-spine.003
// Returns null when nothing plausible matches (e.g. effect/IK-target bones).
function heuristicMapping(rawName: string): string | null {
  const stripped = rawName
    .replace(/^.*[:|]/, "")                        // strip Mixamo/Blender ns prefix
    .replace(/^mixamorig\d*/i, "")                  // strip no-separator Mixamo prefix
    .replace(/_(?:bn|bone|jnt|joint|ctrl|grp)$/i, "")  // strip common suffixes
    .toLowerCase();

  let side: "L" | "R" | "" = "";
  let core = stripped;
  // Side detection: prefix or suffix
  let m = core.match(/^(l|left|r|right)[_.-]/);
  if (m) {
    side = m[1].startsWith("l") ? "L" : "R";
    core = core.slice(m[0].length);
  } else {
    m = core.match(/[_.-](l|left|r|right)$/);
    if (m) {
      side = m[1].startsWith("l") ? "L" : "R";
      core = core.slice(0, -m[0].length);
    }
  }

  // Skip control / effect bones we explicitly don't want to drive.
  if (/ik[_.]?target|effect|lightning|glow|mask|prop|cape|cloth/i.test(core)) {
    return null;
  }

  // Numbered limb segments: arm_01/02/03 or leg_01/02/03
  const limbNum = core.match(/(arm|leg)[_.-]?0?(\d+)$/);
  if (limbNum && side) {
    const part = limbNum[1];
    const idx = parseInt(limbNum[2], 10);
    if (part === "arm") {
      if (idx === 1) return `DEF-upper_arm.${side}`;
      if (idx === 2) return `DEF-forearm.${side}`;
      if (idx === 3) return `DEF-hand.${side}`;
    }
    if (part === "leg") {
      if (idx === 1) return `DEF-thigh.${side}`;
      if (idx === 2) return `DEF-shin.${side}`;
      if (idx === 3) return `DEF-foot.${side}`;
    }
  }

  // Numbered spine segments: spine_01/02/03
  const spineNum = core.match(/^spine[_.-]?0?(\d+)$/);
  if (spineNum) {
    const idx = parseInt(spineNum[1], 10);
    if (idx >= 1 && idx <= 5) return `DEF-spine.00${idx}`;
  }

  // Plain torso keywords
  if (/^(hips?|pelvis|root)$/.test(core)) return "DEF-spine";
  if (/^spine$/.test(core)) return "DEF-spine.001";
  if (/^(chest|spine1|upper_?body)$/.test(core)) return "DEF-spine.002";
  if (/^(upper_?chest|spine2)$/.test(core)) return "DEF-spine.003";
  if (/^neck/.test(core)) return "DEF-spine.004";
  if (/^head/.test(core)) return "DEF-spine.005";

  // Side-specific limbs (no number)
  if (!side) return null;
  if (/^(clavicle|shoulder)/.test(core))           return `DEF-shoulder.${side}`;
  if (/^(upper_?arm|arm)$/.test(core))             return `DEF-upper_arm.${side}`;
  if (/^(forearm|lower_?arm|elbow)$/.test(core))   return `DEF-forearm.${side}`;
  if (/^(hand|wrist|palm)$/.test(core))            return `DEF-hand.${side}`;
  if (/^(thigh|upper_?leg|upleg|hip_joint)$/.test(core)) return `DEF-thigh.${side}`;
  if (/^(shin|lower_?leg|calf|knee)$/.test(core))  return `DEF-shin.${side}`;
  if (/^(foot|ankle)/.test(core))                  return `DEF-foot.${side}`;
  if (/^(toe|ball)/.test(core))                    return `DEF-toe.${side}`;

  return null;
}

interface Props {
  rigGlbUrl: string;
  /** Mixamo → DEF bone-name map. Comes from the rig's `bone_mapping` field. */
  boneMapping: Record<string, string>;
  height?: number;
}

// GLTFLoader runs every loaded node name through
// THREE.PropertyBinding.sanitizeNodeName, which strips reserved characters
// (`.`, `:`, `/`, `[`, `]`) and replaces whitespace with underscores. So a
// Blender bone like "DEF-spine.001" becomes "DEF-spine001" in the loaded
// rig, "DEF-shoulder.L" becomes "DEF-shoulderL", "DEF-thumb.01.L" becomes
// "DEF-thumb01L". Track names need the same treatment — otherwise
// PropertyBinding.parseTrackName reads the dot inside the bone name as a
// sub-object accessor and the track silently fails to bind. (This was
// the cause of "2/53 tracks bound" — only DEF-spine, the one bone with
// no inner dot, survived round-trip unchanged.)
function sanitizeBoneName(name: string): string {
  return name.replace(/\s/g, "_").replace(/[[\].:/]/g, "");
}

// ── Clip remapping ──────────────────────────────────────────────────────────
// Animation files arrive with bone names from the source rig (Mixamo uses
// "mixamorig:Hips"; Blender's FBX export uses "Armature|Hips"; native rigs
// already use "DEF-spine"). Our rig has DEF bones. We rename tracks to the
// matching DEF bone where the bone_mapping covers it, and KEEP unrenamed
// tracks as-is — three.js will silently skip ones that don't bind, and any
// track whose name already matches a rig bone (native exports) plays directly.
function remapClipToRig(
  clip: THREE.AnimationClip,
  mixamoToDef: Record<string, string>,
): { clip: THREE.AnimationClip; remapped: number; kept: number; dropped: number } {
  const tracks: THREE.KeyframeTrack[] = [];
  let remapped = 0;
  let kept = 0;
  let dropped = 0;
  for (const track of clip.tracks) {
    const dot = track.name.lastIndexOf(".");
    if (dot < 0) { tracks.push(track); kept++; continue; }
    const bone = track.name.slice(0, dot);
    const prop = track.name.slice(dot + 1);
    // Drop position/scale tracks. Mixamo emits Hips.position in scene
    // units (often cm), and applying them to a meter-scale rig
    // teleports the root bone hundreds of meters per frame — the mesh
    // shears across the scene as some verts follow and others don't.
    // Rotation tracks are scale-invariant and capture every limb's
    // motion correctly; the character animates in place, which is the
    // right behavior for a preview viewer anyway.
    if (prop !== "quaternion") {
      dropped++;
      continue;
    }
    // Strip common source namespaces: "mixamorig:Hips" | "Armature|Hips" → "Hips"
    // Strip both the colon-style prefix ("mixamorig:Hips") AND the
    // no-separator variant ("mixamorigHips") that some FBX→glTF converters
    // produce when colons aren't allowed in node names. Same for
    // "Armature|Hips".
    const clean = bone
      .replace(/^.*[:|]/, "")
      .replace(/^mixamorig\d*/i, "");
    const mapped =
      mixamoToDef[clean] ??
      mixamoToDef[bone] ??
      FALLBACK_MIXAMO_TO_DEF[clean] ??
      FALLBACK_MIXAMO_TO_DEF[bone] ??
      heuristicMapping(bone);
    if (mapped) {
      const nt = track.clone();
      nt.name = `${sanitizeBoneName(mapped)}.${prop}`;
      tracks.push(nt);
      remapped++;
    } else {
      // Sanitize the source name too in case it had reserved chars.
      const nt = track.clone();
      nt.name = `${sanitizeBoneName(bone)}.${prop}`;
      tracks.push(nt);
      kept++;
    }
  }
  return {
    clip: new THREE.AnimationClip(clip.name, clip.duration, tracks),
    remapped,
    kept,
    dropped,
  };
}

interface AnimSource {
  root: THREE.Object3D;
  clip: THREE.AnimationClip | null;
}

async function loadAnimSource(
  url: string,
  extHint?: string,
): Promise<AnimSource> {
  const ext =
    extHint?.toLowerCase() ??
    url.split("?")[0].split(".").pop()?.toLowerCase();
  if (ext === "fbx") {
    const fbx = await new FBXLoader().loadAsync(url);
    return { root: fbx, clip: fbx.animations?.[0] ?? null };
  }
  const gltf = await new GLTFLoader().loadAsync(url);
  return { root: gltf.scene, clip: gltf.animations?.[0] ?? null };
}

function findSkinnedMesh(obj: THREE.Object3D): THREE.SkinnedMesh | null {
  let result: THREE.SkinnedMesh | null = null;
  obj.traverse((c) => {
    if (!result && (c as THREE.SkinnedMesh).isSkinnedMesh) {
      result = c as THREE.SkinnedMesh;
    }
  });
  return result;
}

function resolveTargetBone(
  srcBoneName: string,
  mixamoToDef: Record<string, string>,
): string | null {
  const clean = srcBoneName
    .replace(/^.*[:|]/, "")
    .replace(/^mixamorig\d*/i, "");
  return (
    mixamoToDef[clean] ??
    mixamoToDef[srcBoneName] ??
    FALLBACK_MIXAMO_TO_DEF[clean] ??
    FALLBACK_MIXAMO_TO_DEF[srcBoneName] ??
    heuristicMapping(srcBoneName)
  );
}

function buildSourceToTargetNames(
  sourceMesh: THREE.SkinnedMesh,
  mixamoToDef: Record<string, string>,
): Record<string, string> {
  const map: Record<string, string> = {};
  for (const bone of sourceMesh.skeleton.bones) {
    const t = resolveTargetBone(bone.name, mixamoToDef);
    if (t) map[bone.name] = sanitizeBoneName(t);
  }
  return map;
}

// ── Stage: takes a pre-loaded rig + clip and runs the mixer ─────────────────
function Stage({
  rig,
  clip,
  onBoundReport,
}: {
  rig: THREE.Object3D | null;
  clip: THREE.AnimationClip | null;
  onBoundReport?: (bound: number, total: number, missing: string[]) => void;
}) {
  const mixerRef = useRef<THREE.AnimationMixer | null>(null);

  useEffect(() => {
    mixerRef.current?.stopAllAction();
    mixerRef.current = null;
    if (!rig || !clip) return;
    const mixer = new THREE.AnimationMixer(rig);
    const action = mixer.clipAction(clip);
    action.play();
    mixerRef.current = mixer;
    let cancelled = false;

    // Inspect what actually bound. PropertyBinding skips silently when the
    // target node doesn't exist in the rig — which is the #1 reason
    // animations "don't play". Log it AND surface to the UI.
    const frame = requestAnimationFrame(() => {
      if (cancelled) return;
      const bindings = (action as unknown as {
        _propertyBindings: Array<{ binding: { node: THREE.Object3D | null } }>;
      })._propertyBindings ?? [];
      const bound: string[] = [];
      const missing: string[] = [];
      bindings.forEach((b, i) => {
        const t = clip.tracks[i];
        if (b?.binding?.node) bound.push(t.name);
        else missing.push(t.name);
      });
      console.log(
        `[AnimationPlayer] ${bound.length}/${clip.tracks.length} tracks bound to rig.`,
      );
      if (missing.length) {
        console.warn(
          `[AnimationPlayer] ${missing.length} unbound tracks:`,
          missing,
        );
      }
      onBoundReport?.(bound.length, clip.tracks.length, missing);
    });

    return () => {
      cancelled = true;
      cancelAnimationFrame(frame);
      mixer.stopAllAction();
    };
  }, [rig, clip, onBoundReport]);

  useFrame((_, dt) => mixerRef.current?.update(dt));

  return rig ? <primitive object={rig} /> : null;
}

// ── Public component ────────────────────────────────────────────────────────
export function AnimationPlayer({ rigGlbUrl, boneMapping, height = 540 }: Props) {
  const [rig, setRig]               = useState<THREE.Object3D | null>(null);
  const [library, setLibrary]       = useState<LibAnim[]>([]);
  const [libraryError, setLibErr]   = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string>("");
  const [clip, setClip]             = useState<THREE.AnimationClip | null>(null);
  const [loadingMsg, setLoadingMsg] = useState<string>("");
  const [statusMsg, setStatusMsg]   = useState<string>("");
  const [error, setError]           = useState<string | null>(null);
  const playRequestRef              = useRef(0);

  // Load + auto-fit rig once. Lifted out of <Stage> so playFromUrl has
  // access to the target SkinnedMesh for SkeletonUtils.retargetClip.
  useEffect(() => {
    let cancelled = false;
    // Pre-Blender (passthrough) rigs are stored with their original
    // extension, so the URL can be .fbx/.obj — feeding that into GLTFLoader
    // crashes with a JSON parse error on the FBX magic header.
    const ext = rigGlbUrl.split("?")[0].split(".").pop()?.toLowerCase();
    const loadScene =
      ext === "fbx" || ext === "obj"
        ? new FBXLoader().loadAsync(rigGlbUrl)
        : new GLTFLoader().loadAsync(rigGlbUrl).then((g) => g.scene);
    loadScene.then((scene) => {
      if (cancelled) return;
      const obj = SkeletonUtils.clone(scene);
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
      obj.updateMatrixWorld(true);

      const boneNames: string[] = [];
      obj.traverse((n) => {
        if ((n as THREE.Bone).isBone) boneNames.push(n.name);
      });
      console.log(
        `[AnimationPlayer] Rig loaded with ${boneNames.length} bones:`,
        boneNames,
      );
      setRig(obj);
    });
    return () => { cancelled = true; };
  }, [rigGlbUrl]);

  useEffect(() => {
    listAnimations()
      .then(({ data }) => setLibrary(data))
      .catch(() => setLibErr("Could not load the animation library."));
  }, []);

  const playFromUrl = async (url: string, label: string, extHint?: string) => {
    if (!rig) {
      setError("Rig is still loading — try again in a moment.");
      return;
    }
    const requestId = ++playRequestRef.current;
    setLoadingMsg(`Loading ${label}…`);
    setStatusMsg("");
    setError(null);
    setClip(null);
    try {
      const source = await loadAnimSource(url, extHint);
      if (requestId !== playRequestRef.current) return;
      if (!source.clip) {
        setError("No animation tracks found in the file.");
        setLoadingMsg("");
        return;
      }
      console.log(
        `[AnimationPlayer] Clip "${source.clip.name}" loaded — ${source.clip.tracks.length} tracks, duration ${source.clip.duration.toFixed(2)}s`,
      );

      const sourceMesh = findSkinnedMesh(source.root);
      const targetMesh = findSkinnedMesh(rig);

      let finalClip: THREE.AnimationClip | null = null;
      let usedRetarget = false;

      if (sourceMesh && targetMesh) {
        // Force matrix-world updates on both skinned meshes — retargetClip
        // reads bone world transforms and silently produces garbage if
        // they're stale.
        source.root.updateMatrixWorld(true);
        rig.updateMatrixWorld(true);

        const names = buildSourceToTargetNames(sourceMesh, boneMapping);
        console.log(
          `[AnimationPlayer] Retargeting via SkeletonUtils with ${Object.keys(names).length} bone-name pairs`,
        );

        try {
          // SkeletonUtils.retargetClip samples source bone WORLD rotations
          // per frame and rederives target-LOCAL rotations that produce
          // the same world pose. This is what corrects the bone-roll
          // mismatch (the "bent elbows pointing sideways" bug).
          const retargeted = SkeletonUtils.retargetClip(
            targetMesh,
            sourceMesh,
            source.clip,
            { names, fps: 30 },
          );
          // Drop position tracks — those still have source-rig units (cm
          // for Mixamo) and would teleport the root. Quaternion-only.
          const rotOnly = retargeted.tracks.filter((t) =>
            t.name.endsWith(".quaternion"),
          );
          finalClip = new THREE.AnimationClip(
            source.clip.name,
            retargeted.duration,
            rotOnly,
          );
          usedRetarget = true;
          console.log(
            `[AnimationPlayer] Retarget produced ${retargeted.tracks.length} tracks; kept ${rotOnly.length} rotation tracks`,
          );
        } catch (e) {
          console.warn(
            "[AnimationPlayer] retargetClip failed — falling back to direct remap:",
            e,
          );
        }
      }

      if (!finalClip) {
        // Fallback: original direct quaternion-copy path. Wrong for
        // mismatched rolls but at least keeps tracks bound.
        const { clip: remapped, remapped: r, kept: k, dropped: d } =
          remapClipToRig(source.clip, boneMapping);
        finalClip = remapped;
        console.log(
          `[AnimationPlayer] Manual remap fallback: ${r} remapped, ${k} kept, ${d} dropped`,
        );
      }

      if (!finalClip.tracks.length) {
        if (requestId !== playRequestRef.current) return;
        setError("No playable tracks after processing.");
        setLoadingMsg("");
        return;
      }

      if (requestId !== playRequestRef.current) return;
      setClip(finalClip);
      setLoadingMsg("");
      setStatusMsg(
        `Loaded · ${finalClip.tracks.length} rotation tracks (${
          usedRetarget ? "retargeted" : "direct copy"
        })`,
      );
    } catch (e) {
      if (requestId !== playRequestRef.current) return;
      setError(e instanceof Error ? e.message : "Failed to load animation.");
      setLoadingMsg("");
    }
  };

  const handleBoundReport = (bound: number, total: number, missing: string[]) => {
    if (bound === 0) {
      setError(
        `No tracks bound to the rig (0/${total}). Open the browser console — the bone-name list and the unbound track names are logged there. Likely cause: rig was built before bone_mapping was saved (re-rig the model) or animation uses bone names this rig doesn't have.`,
      );
      setStatusMsg("");
    } else {
      setStatusMsg(
        `Playing · ${bound}/${total} tracks bound${missing.length ? ` (${missing.length} skipped)` : ""}`,
      );
    }
  };

  const handleSelect = async (id: string) => {
    setSelectedId(id);
    if (!id) {
      playRequestRef.current += 1;
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
    const ext = file.name.split(".").pop()?.toLowerCase();
    await playFromUrl(url, file.name, ext);
    // Not revoking the URL — the clip may still reference blob data.
  };

  const stop = () => {
    playRequestRef.current += 1;
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
            <Stage rig={rig} clip={clip} onBoundReport={handleBoundReport} />
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
