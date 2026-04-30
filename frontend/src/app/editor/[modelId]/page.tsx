"use client";

import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { useRigStatus } from "@/hooks/useRigStatus";
import { ModelViewer } from "@/components/ModelViewer";
import { LandmarkEditor, LandmarkPositions } from "@/components/LandmarkEditor";
import { AnimationPlayer } from "@/components/AnimationPlayer";
import api from "@/lib/api";

type Tab = "view" | "edit-rig" | "play";

function Btn({
  onClick, active, disabled, color = "#888", children,
}: {
  onClick: () => void; active?: boolean; disabled?: boolean;
  color?: string; children: React.ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      style={{
        padding: "0.6rem 1.1rem", borderRadius: 8,
        border: `1px solid ${active ? color : "#2a2a3d"}`,
        background: active ? `${color}22` : "transparent",
        color: active ? color : disabled ? "#444" : "#888",
        fontWeight: 600, cursor: disabled ? "not-allowed" : "pointer",
        fontSize: "0.9rem", transition: "all 0.2s",
        opacity: disabled ? 0.5 : 1,
      }}
    >
      {children}
    </button>
  );
}

export default function EditorPage() {
  const { modelId } = useParams<{ modelId: string }>();
  const { status, pct, step, glbUrl, error } = useRigStatus(modelId);

  const [tab, setTab]                               = useState<Tab>("view");
  const [playAnimation, setPlayAnimation]           = useState(false);
  const [showSkeleton, setShowSkeleton]             = useState(false);
  const [hasEmbedded, setHasEmbedded]               = useState<boolean | null>(null);
  const [rerigging, setRerigging]                   = useState(false);
  const [rerigError, setRerigError]                 = useState<string | null>(null);
  const [landmarkSubmitting, setLandmarkSubmitting] = useState(false);
  const [landmarkError, setLandmarkError]           = useState<string | null>(null);
  const [landmarkQueued, setLandmarkQueued]         = useState(false);
  const [boneMapping, setBoneMapping]               = useState<Record<string, string> | null>(null);
  const [rigLog, setRigLog]                         = useState<string>("");
  const [showLog, setShowLog]                       = useState(false);
  type DetectedPose = "t_pose" | "a_pose" | "arms_down" | "unclear";
  const [detectedPose, setDetectedPose]             = useState<DetectedPose | null>(null);
  const [poseAngle, setPoseAngle]                   = useState<number | null>(null);
  const [poseConfidence, setPoseConfidence]         = useState<number>(0);

  // Fetch the rig's Mixamo→DEF bone map, Blender stdout, and pose
  // classification once rigging completes. The status endpoint doesn't
  // carry these — only the detail endpoint does.
  useEffect(() => {
    if ((status !== "done" && status !== "failed") || !modelId) return;
    api.get<{
      bone_mapping: Record<string, string>;
      rig_log: string;
      detected_pose?: DetectedPose;
      pose_angle_deg?: number | null;
      pose_confidence?: number;
    }>(`/rigs/${modelId}/`)
      .then(({ data }) => {
        setBoneMapping(data.bone_mapping ?? {});
        setRigLog(data.rig_log ?? "");
        setDetectedPose(data.detected_pose ?? null);
        setPoseAngle(data.pose_angle_deg ?? null);
        setPoseConfidence(data.pose_confidence ?? 0);
      })
      .catch(() => {
        setBoneMapping({});
        setRigLog("");
        setDetectedPose(null);
        setPoseAngle(null);
        setPoseConfidence(0);
      });
  }, [status, modelId, landmarkQueued]);

  const modelReady = hasEmbedded !== null;
  const playLabel  = hasEmbedded ? "▶ Embedded animation" : "👋 Wave animation";

  const handleRerig = async () => {
    if (!modelId || rerigging) return;
    setRerigging(true); setRerigError(null);
    setHasEmbedded(null); setPlayAnimation(false); setShowSkeleton(false);
    try {
      await api.post(`/rigs/${modelId}/rerig/`);
      window.location.reload();
    } catch (err: any) {
      setRerigError(err.response?.data?.error || err.message || "Rerig failed.");
      setRerigging(false);
    }
  };

  const handleLandmarkSubmit = async (landmarks: LandmarkPositions) => {
    if (!modelId) return;
    setLandmarkSubmitting(true);
    setLandmarkError(null);
    console.log("[Landmarks] POST /rerig-landmarks/", landmarks);
    try {
      const r = await api.post(`/rigs/${modelId}/rerig-landmarks/`, { landmarks });
      console.log("[Landmarks] Response:", r.status, r.data);

      // Wipe the cached log so the next "Show log" press shows the new run.
      setRigLog("");
      setShowLog(false);

      // Switch back to the view tab — the progress bar will appear automatically
      // because useRigStatus will poll and see status = "pending" → "processing" → "done"
      setLandmarkQueued(true);
      setLandmarkSubmitting(false);
      setHasEmbedded(null);
      setPlayAnimation(false);
      setShowSkeleton(false);
      setTab("view");
    } catch (err: any) {
      console.error("[Landmarks] POST failed:", err);
      const status = err.response?.status;
      const detail = err.response?.data?.detail || err.response?.data?.error;
      let msg: string;
      if (status === 429) {
        // DRF includes a Retry-After hint on rate-limit responses.
        const retry = err.response?.data?.detail
          ?? "Try again later.";
        msg = `Rate limit reached. ${retry} (Local dev tip: restart Django to reset throttle counters; settings/local.py already relaxes the caps to 10000/hour.)`;
      } else if (status === 401) {
        msg = "You need to be logged in to apply landmarks.";
      } else {
        msg = detail || err.message || "Failed to apply landmarks.";
      }
      setLandmarkError(msg);
      setLandmarkSubmitting(false);
    }
  };

  // After landmarks are queued, useRigStatus drives everything.
  // Once done, clear the queued flag so the viewer shows normally.
  const effectiveStatus = landmarkQueued && status === "done" ? "done" : status;

  return (
    <div style={{ maxWidth: 1200, margin: "2rem auto", padding: "0 1rem" }}>
      <h1 style={{ fontSize: "1.6rem", fontWeight: 800, marginBottom: "0.5rem" }}>
        Model Editor
      </h1>

      {/* Progress bar — shown when processing OR just after landmark apply */}
      {(effectiveStatus !== "done" || landmarkQueued) && effectiveStatus !== "failed" && (
        <div style={{
          background: "#12121a", border: "1px solid #2a2a3d",
          borderRadius: 10, padding: "1.25rem 1.5rem", marginBottom: "1.5rem",
        }}>
          <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "0.75rem" }}>
            <span style={{ fontWeight: 600 }}>
              {landmarkQueued && status !== "done"
                ? `⚙️ ${step || "Applying landmark rig…"}`
                : `⚙️ ${step}`}
            </span>
            <span style={{ color: "#6c63ff", fontWeight: 700 }}>{pct}%</span>
          </div>
          <div style={{ background: "#1a1a2e", borderRadius: 6, height: 8, overflow: "hidden" }}>
            <div style={{
              width: `${pct || 0}%`, height: "100%",
              background: "linear-gradient(90deg,#6c63ff,#00d4ff)",
              borderRadius: 6, transition: "width 0.5s ease",
            }} />
          </div>
          {error && <div style={{ color: "#ff6b6b", fontSize: "0.85rem", marginTop: "0.75rem" }}>{error}</div>}
        </div>
      )}

      {/* Failed state */}
      {effectiveStatus === "failed" && !landmarkQueued && (
        <div style={{
          background: "#12121a", border: "1px solid #2a2a3d",
          borderRadius: 10, padding: "1.25rem 1.5rem", marginBottom: "1.5rem",
        }}>
          <div style={{ color: "#ff6b6b", fontWeight: 600, marginBottom: "1rem" }}>❌ Rigging failed</div>
          {error && <div style={{ color: "#ff6b6b", fontSize: "0.85rem", marginBottom: "1rem" }}>{error}</div>}
          <button onClick={handleRerig} disabled={rerigging} style={{
            padding: "0.6rem 1.2rem", borderRadius: 8, border: "none",
            background: rerigging ? "#2a2a3d" : "#6c63ff",
            color: rerigging ? "#666" : "#fff", fontWeight: 600,
            cursor: rerigging ? "not-allowed" : "pointer",
          }}>
            {rerigging ? "Rerigging…" : "🔄 Rerig model"}
          </button>
        </div>
      )}

      {/* Done state */}
      {effectiveStatus === "done" && glbUrl && (
        <div>
          {/* Success bar — hide while landmark re-rig is still processing */}
          {!(landmarkQueued && status !== "done") && (
            <div style={{
              background: "rgba(0,230,118,0.08)", border: "1px solid rgba(0,230,118,0.2)",
              borderRadius: 8, padding: "0.75rem 1rem", color: "#00e676",
              marginBottom: "1rem", fontSize: "0.9rem",
              display: "flex", justifyContent: "space-between",
              alignItems: "center", gap: "1rem", flexWrap: "wrap",
            }}>
              <span>✅ Rigging complete! Your model is ready.</span>
              <a href={glbUrl} download style={{
                padding: "0.5rem 0.9rem",
                background: "linear-gradient(135deg,rgba(108,99,255,.15),rgba(0,212,255,.25))",
                border: "1px solid rgba(108,99,255,0.7)", borderRadius: 999,
                color: "#fff", fontSize: "0.85rem", fontWeight: 600,
                textDecoration: "none", whiteSpace: "nowrap",
              }}>
                ⬇️ Download
              </a>
            </div>
          )}

          {/* Tabs */}
          <div style={{ display: "flex", gap: "0.5rem", marginBottom: "1rem" }}>
            <Btn onClick={() => { setTab("view"); setLandmarkQueued(false); }} active={tab === "view"} color="#6c63ff">
              🖼 View model
            </Btn>
            <Btn
              onClick={() => { setTab("edit-rig"); setPlayAnimation(false); setShowSkeleton(false); setLandmarkQueued(false); }}
              active={tab === "edit-rig"} color="#f59e0b"
            >
              🎯 Edit rig placement
            </Btn>
            <Btn
              onClick={() => { setTab("play"); setPlayAnimation(false); setShowSkeleton(false); setLandmarkQueued(false); }}
              active={tab === "play"} color="#00d4ff"
            >
              🎞 Play animation
            </Btn>
          </div>

          {/* View tab */}
          {tab === "view" && (
            <>
              <div style={{ display: "flex", gap: "0.6rem", marginBottom: "0.75rem", flexWrap: "wrap" }}>
                {modelReady && (
                  <Btn onClick={() => setPlayAnimation(v => !v)} active={playAnimation} color="#00d4ff">
                    {playAnimation ? "⏹ Stop" : playLabel}
                  </Btn>
                )}
                {modelReady && (
                  <Btn onClick={() => setShowSkeleton(v => !v)} active={showSkeleton} color="#a78bfa">
                    {showSkeleton ? "🦴 Hide skeleton" : "🦴 Show skeleton"}
                  </Btn>
                )}
                <Btn onClick={handleRerig} disabled={rerigging} color="#f87171">
                  <span style={{ color: rerigging ? "#555" : "#f87171" }}>
                    {rerigging ? "Rerigging…" : "🔄 Rerig model"}
                  </span>
                </Btn>
                {rigLog && (
                  <Btn onClick={() => setShowLog((v) => !v)} active={showLog} color="#888">
                    {showLog ? "📜 Hide log" : "📜 Show log"}
                  </Btn>
                )}
                {detectedPose && (() => {
                  const labels: Record<DetectedPose, string> = {
                    t_pose:    "T-pose",
                    a_pose:    "A-pose",
                    arms_down: "Arms down",
                    unclear:   "Pose unclear",
                  };
                  // Yellow when not T-pose: Rigify's metarig is built for T,
                  // so anything else risks weight-painting artefacts.
                  const isOk = detectedPose === "t_pose";
                  const color = isOk ? "rgba(0,230,118,0.9)" : "rgba(245,158,11,0.95)";
                  const bg    = isOk ? "rgba(0,230,118,0.08)" : "rgba(245,158,11,0.08)";
                  const tip = isOk
                    ? `Detected ${labels[detectedPose]} — Rigify weights cleanly on this pose.`
                    : `Detected ${labels[detectedPose]}. Rigify expects T-pose for cleanest weighting; arms may bind imperfectly.`;
                  const angleText =
                    poseAngle !== null && Number.isFinite(poseAngle)
                      ? ` · ${poseAngle.toFixed(0)}°`
                      : "";
                  const confText =
                    poseConfidence > 0
                      ? ` (${Math.round(poseConfidence * 100)}%)`
                      : "";
                  return (
                    <span
                      title={tip}
                      style={{
                        padding: "0.5rem 0.85rem",
                        borderRadius: 8,
                        border: `1px solid ${color}`,
                        background: bg,
                        color,
                        fontWeight: 600,
                        fontSize: "0.85rem",
                      }}
                    >
                      🧍 {labels[detectedPose]}{angleText}{confText}
                    </span>
                  );
                })()}
              </div>

              {showLog && rigLog && (
                <pre
                  style={{
                    background: "#0a0a14", border: "1px solid #2a2a3d",
                    borderRadius: 8, padding: "0.75rem 1rem",
                    color: "#9ab", fontSize: "0.72rem",
                    maxHeight: 240, overflow: "auto",
                    whiteSpace: "pre-wrap", marginBottom: "0.75rem",
                  }}
                >
                  {rigLog}
                </pre>
              )}

              {showSkeleton && (
                <p style={{ color: "#a78bfa", fontSize: "0.82rem", marginBottom: "0.75rem" }}>
                  🦴 Cyan lines show the deform bones — rotate the model to inspect coverage.
                </p>
              )}
              {rerigError && (
                <div style={{
                  background: "rgba(248,113,113,0.08)", border: "1px solid rgba(248,113,113,0.3)",
                  borderRadius: 8, padding: "0.6rem 1rem", color: "#f87171",
                  fontSize: "0.85rem", marginBottom: "0.75rem",
                }}>
                  {rerigError}
                </div>
              )}

              <ModelViewer
                key={glbUrl}
                glbUrl={glbUrl} height={560}
                playAnimation={playAnimation}
                showSkeleton={showSkeleton}
                onReady={setHasEmbedded}
              />
            </>
          )}

          {/* Edit rig tab */}
          {tab === "edit-rig" && (
            <>
              <div style={{
                background: "rgba(245,158,11,0.08)", border: "1px solid rgba(245,158,11,0.3)",
                borderRadius: 8, padding: "0.75rem 1rem",
                color: "#f59e0b", fontSize: "0.85rem", marginBottom: "1rem",
              }}>
                🎯 <strong>Rig placement editor</strong> — select a landmark on the left, click
                the spot on the model, work through all 6, then hit <strong>Apply rig</strong>.
              </div>

              {landmarkError && (
                <div style={{
                  background: "rgba(248,113,113,0.08)", border: "1px solid rgba(248,113,113,0.3)",
                  borderRadius: 8, padding: "0.6rem 1rem", color: "#f87171",
                  fontSize: "0.85rem", marginBottom: "0.75rem",
                }}>
                  {landmarkError}
                </div>
              )}

              <LandmarkEditor
                key={glbUrl}
                glbUrl={glbUrl}
                onSubmit={handleLandmarkSubmit}
                submitting={landmarkSubmitting}
              />
            </>
          )}

          {/* Play animation tab */}
          {tab === "play" && (
            <>
              <div style={{
                background: "rgba(0,212,255,0.06)", border: "1px solid rgba(0,212,255,0.3)",
                borderRadius: 8, padding: "0.75rem 1rem",
                color: "#00d4ff", fontSize: "0.85rem", marginBottom: "1rem",
              }}>
                🎞 <strong>Animation player</strong> — pick an uploaded animation
                or drop a local FBX/GLB to play it on your rig. Bone tracks are
                remapped onto this rig using its bone map.
                {" "}
                <a href="/upload-animation" style={{ color: "#fff", textDecoration: "underline" }}>
                  Upload a new animation
                </a>
              </div>

              {boneMapping === null ? (
                <div style={{ color: "#888", fontSize: "0.9rem" }}>
                  Loading rig bone map…
                </div>
              ) : (
                <AnimationPlayer
                  key={glbUrl}
                  rigGlbUrl={glbUrl}
                  boneMapping={boneMapping}
                />
              )}
            </>
          )}
        </div>
      )}

      {/* Placeholder while initial processing */}
      {effectiveStatus !== "done" && effectiveStatus !== "failed" && !landmarkQueued && (
        <div style={{
          height: 400, background: "#0a0a14", borderRadius: 12,
          border: "1px dashed #2a2a3d", display: "flex",
          alignItems: "center", justifyContent: "center",
          color: "#888", fontSize: "0.9rem",
        }}>
          3D viewer will appear when rigging is complete
        </div>
      )}
    </div>
  );
}