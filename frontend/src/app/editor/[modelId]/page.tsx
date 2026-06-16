"use client";

import { useParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { useRigStatus } from "@/hooks/useRigStatus";
import { ModelViewer } from "@/components/ModelViewer";
import { LandmarkEditor, LandmarkPositions } from "@/components/LandmarkEditor";
import { AnimationPlayer } from "@/components/AnimationPlayer";
import api, {
  extractApiError,
  listAnimations,
  exportRig,
  getExport,
  type Animation,
  type AnimationExport,
} from "@/lib/api";
import { isAxiosError } from "axios";

type Tab = "view" | "edit-rig" | "play";
type DetectedPose = "t_pose" | "a_pose" | "arms_down" | "unclear";

export default function EditorPage() {
  const { modelId } = useParams<{ modelId: string }>();
  // Bumped on each successful /rerig-landmarks/ POST so useRigStatus
  // re-enters its polling effect (the hook stops at the terminal state).
  const [landmarkRunId, setLandmarkRunId] = useState(0);
  const { status, pct, step, glbUrl, error } = useRigStatus(modelId, landmarkRunId);

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
  const [detectedPose, setDetectedPose]             = useState<DetectedPose | null>(null);
  const [poseAngle, setPoseAngle]                   = useState<number | null>(null);
  const [poseConfidence, setPoseConfidence]         = useState<number>(0);
  const [detectionMethod, setDetectionMethod]       = useState<string>("");
  const [usedExistingRig, setUsedExistingRig]       = useState<boolean>(false);

  // ── Export-with-animations state ──────────────────────────────────────────
  const [libraryAnims, setLibraryAnims]         = useState<Animation[]>([]);
  const [selectedAnimIds, setSelectedAnimIds]   = useState<string[]>([]);
  const [exportState, setExportState]           = useState<AnimationExport | null>(null);
  const [exporting, setExporting]               = useState(false);
  const [exportError, setExportError]           = useState<string | null>(null);
  const [bakedUrl, setBakedUrl]                 = useState<string | null>(null);
  const exportPollRef                           = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Clear export poll on unmount
  useEffect(() => {
    return () => {
      if (exportPollRef.current) clearTimeout(exportPollRef.current);
    };
  }, []);

  // Fetch the rig's bone map, Blender stdout, and pose classification once
  // rigging completes. The status endpoint doesn't carry these — only the
  // detail endpoint does.
  useEffect(() => {
    if ((status !== "done" && status !== "failed") || !modelId) return;
    api
      .get<{
        bone_mapping: Record<string, string>;
        rig_log: string;
        detected_pose?: DetectedPose;
        pose_angle_deg?: number | null;
        pose_confidence?: number;
        detection_method?: string;
        used_existing_rig?: boolean;
      }>(`/rigs/${modelId}/`)
      .then(({ data }) => {
        setBoneMapping(data.bone_mapping ?? {});
        setRigLog(data.rig_log ?? "");
        setDetectedPose(data.detected_pose ?? null);
        setPoseAngle(data.pose_angle_deg ?? null);
        setPoseConfidence(data.pose_confidence ?? 0);
        setDetectionMethod(data.detection_method ?? "");
        setUsedExistingRig(data.used_existing_rig ?? false);
      })
      .catch(() => {
        setBoneMapping({});
        setRigLog("");
        setDetectedPose(null);
        setPoseAngle(null);
        setPoseConfidence(0);
        setDetectionMethod("");
        setUsedExistingRig(false);
      });
  }, [status, modelId, landmarkQueued]);

  const modelReady = hasEmbedded !== null;
  const playLabel = hasEmbedded ? "Embedded animation" : "Wave animation";

  const handleRerig = async () => {
    if (!modelId || rerigging) return;
    setRerigging(true);
    setRerigError(null);
    setHasEmbedded(null);
    setPlayAnimation(false);
    setShowSkeleton(false);
    try {
      await api.post(`/rigs/${modelId}/rerig/`);
      window.location.reload();
    } catch (err: unknown) {
      setRerigError(extractApiError(err, "Rerig failed."));
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

      setRigLog("");
      setShowLog(false);

      setLandmarkQueued(true);
      setLandmarkRunId((n) => n + 1);   // restart useRigStatus polling
      setLandmarkSubmitting(false);
      setHasEmbedded(null);
      setPlayAnimation(false);
      setShowSkeleton(false);
      setTab("view");
    } catch (err: unknown) {
      console.error("[Landmarks] POST failed:", err);
      let msg: string;
      if (isAxiosError(err)) {
        const code = err.response?.status;
        if (code === 429) {
          const retry =
            (err.response?.data as { detail?: string } | undefined)?.detail ??
            "Try again later.";
          msg = `Rate limit reached. ${retry} (Local dev tip: restart Django to reset throttle counters; settings/local.py already relaxes the caps to 10000/hour.)`;
        } else if (code === 401) {
          msg = "You need to be logged in to apply landmarks.";
        } else {
          msg = extractApiError(err, "Failed to apply landmarks.");
        }
      } else {
        msg = err instanceof Error ? err.message : "Failed to apply landmarks.";
      }
      setLandmarkError(msg);
      setLandmarkSubmitting(false);
    }
  };

  const effectiveStatus = landmarkQueued && status === "done" ? "done" : status;

  // ── Export helpers (need effectiveStatus in scope) ────────────────────────

  useEffect(() => {
    if (tab !== "play" || effectiveStatus !== "done") return;
    listAnimations()
      .then(({ data }) => setLibraryAnims(data))
      .catch(() => setLibraryAnims([]));
  }, [tab, effectiveStatus]);

  const handleToggleAnim = (id: string) => {
    setSelectedAnimIds((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id],
    );
  };

  const scheduleExportPoll = (expId: string) => {
    exportPollRef.current = setTimeout(async () => {
      try {
        const { data } = await getExport(modelId, expId);
        setExportState(data);
        if (data.status === "done") {
          setExporting(false);
        } else if (data.status === "failed") {
          setExporting(false);
          setExportError(data.error_message ?? "Export failed.");
        } else {
          scheduleExportPoll(expId);
        }
      } catch {
        setExporting(false);
        setExportError("Failed to poll export status.");
      }
    }, 2000);
  };

  const handleExportWithAnimations = async () => {
    if (!modelId || exporting || selectedAnimIds.length === 0) return;
    setExporting(true);
    setExportError(null);
    setExportState(null);
    setBakedUrl(null);
    if (exportPollRef.current) clearTimeout(exportPollRef.current);
    try {
      const { data } = await exportRig(modelId, selectedAnimIds);
      setExportState(data);
      if (data.status === "done") {
        setExporting(false);
      } else if (data.status === "failed") {
        setExporting(false);
        setExportError(data.error_message ?? "Export failed.");
      } else {
        scheduleExportPoll(data.id);
      }
    } catch (err: unknown) {
      setExporting(false);
      setExportError(extractApiError(err, "Export failed."));
    }
  };

  return (
    <div className="relative isolate min-h-[100svh] pt-28 pb-16">
      <div className="pointer-events-none absolute inset-0 -z-10">
        <div className="absolute -top-1/3 right-0 h-[60vh] w-[60vh] rounded-full bg-accent/8 blur-[160px] [animation:var(--animate-aurora-1)]" />
      </div>

      <div className="mx-auto w-full max-w-6xl px-6">
        <div className="flex items-center gap-3">
          <span className="font-mono text-xs uppercase tracking-[0.25em] text-accent">
            {"// Editor"}
          </span>
          <span className="font-mono text-[11px] uppercase tracking-[0.18em] text-muted">
            rig: {modelId?.slice(0, 8)}
          </span>
        </div>
        <h1 className="mt-3 text-3xl font-bold tracking-[-0.02em] text-foreground sm:text-4xl">
          Model editor
        </h1>

        {/* Progress bar */}
        {(effectiveStatus !== "done" || landmarkQueued) && effectiveStatus !== "failed" && (
          <motion.div
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            className="mt-8 overflow-hidden rounded-xl border border-border bg-surface/70 p-5 backdrop-blur"
          >
            <div className="mb-3 flex items-center justify-between">
              <div className="flex items-center gap-2.5">
                <Spinner className="text-accent" />
                <span className="text-sm font-medium text-foreground">
                  {landmarkQueued && status !== "done"
                    ? step || "Applying landmark rig…"
                    : step}
                </span>
              </div>
              <span className="font-mono text-sm font-semibold text-accent">{pct}%</span>
            </div>
            <div className="h-2 overflow-hidden rounded-full bg-background">
              <motion.div
                className="h-full rounded-full bg-gradient-to-r from-accent to-accent-soft"
                style={{ width: `${pct || 0}%` }}
                animate={{ width: `${pct || 0}%` }}
                transition={{ duration: 0.5, ease: "easeOut" }}
              />
            </div>
            {error && (
              <div className="mt-3 text-xs text-danger">{error}</div>
            )}
          </motion.div>
        )}

        {/* Failed state */}
        {effectiveStatus === "failed" && !landmarkQueued && (
          <motion.div
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            className="mt-8 rounded-xl border border-danger/30 bg-danger/5 p-5"
          >
            <div className="flex items-center gap-2.5 text-danger">
              <AlertIcon />
              <span className="font-semibold">Rigging failed</span>
            </div>
            {error && <div className="mt-3 text-sm text-danger/90">{error}</div>}
            <button
              onClick={handleRerig}
              disabled={rerigging}
              className="mt-4 inline-flex items-center gap-2 rounded-full bg-accent px-5 py-2 text-sm font-semibold text-background shadow-[var(--shadow-glow-accent)] transition-transform hover:scale-[1.02] active:scale-[0.98] disabled:cursor-wait disabled:opacity-70"
            >
              {rerigging ? <Spinner /> : <RefreshIcon className="h-4 w-4" />}
              {rerigging ? "Rerigging…" : "Rerig model"}
            </button>
          </motion.div>
        )}

        {/* Done state */}
        {effectiveStatus === "done" && glbUrl && (
          <div className="mt-8">
            {/* Success banner */}
            {!(landmarkQueued && status !== "done") && (
              <motion.div
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                className="mb-5 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-accent/30 bg-accent/8 px-5 py-3.5"
              >
                <div className="flex items-center gap-2.5">
                  <span className="flex h-6 w-6 items-center justify-center rounded-full bg-accent text-background">
                    <CheckIcon className="h-3.5 w-3.5" />
                  </span>
                  <div>
                    <span className="text-sm font-medium text-foreground">
                      Rigging complete — your model is ready.
                    </span>
                    {detectionMethod && (
                      <span className={`ml-2 inline-block rounded-full px-2 py-0.5 text-xs font-medium ${
                        detectionMethod === "llm_vision"
                          ? "bg-purple-500/15 text-purple-400"
                          : detectionMethod === "geometry"
                          ? "bg-accent/15 text-accent"
                          : detectionMethod === "user_landmarks"
                          ? "bg-blue-500/15 text-blue-400"
                          : "bg-warning/15 text-warning"
                      }`}>
                        {detectionMethod === "llm_vision" && "AI vision"}
                        {detectionMethod === "geometry" && "Auto-detect"}
                        {detectionMethod === "user_landmarks" && "Manual"}
                        {detectionMethod === "failed" && "Geometry fallback"}
                        {!["llm_vision","geometry","user_landmarks","failed"].includes(detectionMethod) && detectionMethod}
                      </span>
                    )}
                    {usedExistingRig && (
                      <span className="ml-2 inline-block rounded-full border border-accent/40 bg-accent/10 px-2.5 py-0.5 text-xs text-accent">
                        Original rig preserved
                      </span>
                    )}
                  </div>
                </div>
                <a
                  href={glbUrl}
                  download
                  className="inline-flex items-center gap-2 rounded-full border border-accent/40 bg-accent/10 px-4 py-1.5 text-sm font-semibold text-accent transition-colors hover:bg-accent/20"
                >
                  <DownloadIcon className="h-4 w-4" />
                  Download GLB
                </a>
              </motion.div>
            )}

            {/* Landmark-failure soft warning */}
            {detectionMethod === "failed" && !(landmarkQueued && status !== "done") && (
              <motion.div
                initial={{ opacity: 0, y: 6 }}
                animate={{ opacity: 1, y: 0 }}
                className="mb-5 rounded-xl border border-warning/30 bg-warning/5 px-5 py-3.5"
              >
                <div className="flex items-start gap-2.5 text-warning">
                  <AlertIcon />
                  <div>
                    <p className="text-sm font-medium">Landmark detection fell back to geometry defaults</p>
                    <p className="mt-1 text-xs text-warning/80">
                      The AI-detected bone positions failed the anatomical check. The rig was built
                      using automatic geometry analysis instead. Use &ldquo;Edit rig&rdquo; to manually
                      adjust bone placement.
                    </p>
                  </div>
                </div>
              </motion.div>
            )}

            {/* Tabs (segmented control) */}
            <div className="inline-flex items-center gap-1 rounded-full border border-border bg-surface/60 p-1 backdrop-blur">
              <TabButton
                active={tab === "view"}
                onClick={() => {
                  setTab("view");
                  setLandmarkQueued(false);
                }}
                icon={<ViewIcon className="h-3.5 w-3.5" />}
              >
                View model
              </TabButton>
              {!usedExistingRig && (
                <TabButton
                  active={tab === "edit-rig"}
                  onClick={() => {
                    setTab("edit-rig");
                    setPlayAnimation(false);
                    setShowSkeleton(false);
                    setLandmarkQueued(false);
                  }}
                  icon={<TargetIcon className="h-3.5 w-3.5" />}
                >
                  Edit rig
                </TabButton>
              )}
              <TabButton
                active={tab === "play"}
                onClick={() => {
                  setTab("play");
                  setPlayAnimation(false);
                  setShowSkeleton(false);
                  setLandmarkQueued(false);
                }}
                icon={<PlayIcon className="h-3.5 w-3.5" />}
              >
                Play animation
              </TabButton>
            </div>

            <AnimatePresence mode="wait">
              {tab === "view" && (
                <motion.div
                  key="view"
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -8 }}
                  transition={{ duration: 0.25 }}
                  className="mt-5"
                >
                  <div className="mb-3 flex flex-wrap gap-2">
                    {modelReady && (
                      <ToolButton
                        active={playAnimation}
                        onClick={() => setPlayAnimation((v) => !v)}
                        icon={playAnimation ? <StopIcon /> : <PlayIcon />}
                      >
                        {playAnimation ? "Stop" : playLabel}
                      </ToolButton>
                    )}
                    {modelReady && (
                      <ToolButton
                        active={showSkeleton}
                        onClick={() => setShowSkeleton((v) => !v)}
                        icon={<SkeletonIcon />}
                      >
                        {showSkeleton ? "Hide skeleton" : "Show skeleton"}
                      </ToolButton>
                    )}
                    <ToolButton
                      onClick={handleRerig}
                      disabled={rerigging}
                      tone="danger"
                      icon={rerigging ? <Spinner /> : <RefreshIcon />}
                    >
                      {rerigging ? "Rerigging…" : "Rerig model"}
                    </ToolButton>
                    {rigLog && (
                      <ToolButton
                        active={showLog}
                        onClick={() => setShowLog((v) => !v)}
                        icon={<TerminalIcon />}
                      >
                        {showLog ? "Hide log" : "Show log"}
                      </ToolButton>
                    )}
                    {detectedPose && <PoseBadge pose={detectedPose} angle={poseAngle} confidence={poseConfidence} />}
                  </div>

                  {showLog && rigLog && (
                    <pre className="mb-3 max-h-60 overflow-auto whitespace-pre-wrap rounded-lg border border-border bg-background/80 px-4 py-3 font-mono text-[11px] leading-relaxed text-muted-foreground">
                      {rigLog}
                    </pre>
                  )}

                  {showSkeleton && (
                    <p className="mb-3 font-mono text-xs text-cyan">
                      Cyan lines show the deform bones — rotate the model to inspect coverage.
                    </p>
                  )}
                  {rerigError && (
                    <div className="mb-3 rounded-lg border border-danger/30 bg-danger/10 px-4 py-2.5 text-sm text-danger">
                      {rerigError}
                    </div>
                  )}

                  <div className="overflow-hidden rounded-2xl border border-border bg-surface/30">
                    <ModelViewer
                      key={glbUrl}
                      glbUrl={glbUrl}
                      height={560}
                      playAnimation={playAnimation}
                      showSkeleton={showSkeleton}
                      onReady={setHasEmbedded}
                    />
                  </div>
                </motion.div>
              )}

              {tab === "edit-rig" && !usedExistingRig && (
                <motion.div
                  key="edit-rig"
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -8 }}
                  transition={{ duration: 0.25 }}
                  className="mt-5"
                >
                  <Callout tone="warning">
                    <strong className="font-semibold text-foreground">
                      Rig placement editor.
                    </strong>{" "}
                    Pick a landmark on the left, click the spot on the model,
                    work through all 14, then hit{" "}
                    <strong className="text-foreground">Apply rig</strong>.
                  </Callout>

                  {landmarkError && (
                    <div className="mb-3 rounded-lg border border-danger/30 bg-danger/10 px-4 py-2.5 text-sm text-danger">
                      {landmarkError}
                    </div>
                  )}

                  <LandmarkEditor
                    key={glbUrl}
                    glbUrl={glbUrl}
                    rigId={modelId}
                    onSubmit={handleLandmarkSubmit}
                    submitting={landmarkSubmitting}
                  />
                </motion.div>
              )}

              {tab === "play" && (
                <motion.div
                  key="play"
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -8 }}
                  transition={{ duration: 0.25 }}
                  className="mt-5"
                >
                  <Callout tone="info">
                    <strong className="font-semibold text-foreground">
                      Animation player.
                    </strong>{" "}
                    Pick an uploaded animation or drop a local FBX/GLB to play
                    it on your rig. Bone tracks are remapped onto this rig
                    using its bone map.{" "}
                    <a href="/upload-animation" className="text-accent underline-offset-4 hover:underline">
                      Upload a new animation
                    </a>
                  </Callout>

                  {boneMapping === null ? (
                    <div className="rounded-lg border border-border bg-surface/40 px-5 py-4 text-sm text-muted-foreground">
                      Loading rig bone map…
                    </div>
                  ) : (
                    <AnimationPlayer
                      key={glbUrl}
                      rigGlbUrl={glbUrl}
                      boneMapping={boneMapping}
                    />
                  )}

                  {/* ── Export with animations ── */}
                  <div className="mt-6 rounded-xl border border-border bg-surface/40 p-5">
                    <h3 className="mb-3 text-sm font-semibold text-foreground">
                      Export with animations
                    </h3>
                    <p className="mb-4 text-xs text-muted-foreground">
                      Select one or more library animations to bake into a single downloadable animated GLB.
                    </p>

                    {libraryAnims.length === 0 ? (
                      <div className="text-xs text-muted-foreground">Loading animations…</div>
                    ) : (
                      <div className="mb-4 max-h-48 overflow-y-auto rounded-lg border border-border bg-background/60">
                        {libraryAnims.map((anim) => (
                          <label
                            key={anim.id}
                            className="flex cursor-pointer items-center gap-3 border-b border-border px-3 py-2.5 last:border-b-0 hover:bg-surface/60"
                          >
                            <input
                              type="checkbox"
                              checked={selectedAnimIds.includes(anim.id)}
                              onChange={() => handleToggleAnim(anim.id)}
                              className="h-3.5 w-3.5 accent-[var(--color-accent)]"
                            />
                            <span className="text-sm text-foreground">{anim.name}</span>
                            <span className="ml-auto text-xs text-muted-foreground">
                              {anim.category.name}
                            </span>
                          </label>
                        ))}
                      </div>
                    )}

                    <button
                      onClick={handleExportWithAnimations}
                      disabled={exporting || selectedAnimIds.length === 0}
                      className="inline-flex items-center gap-2 rounded-full bg-accent px-5 py-2 text-sm font-semibold text-background shadow-[var(--shadow-glow-accent)] transition-transform hover:scale-[1.02] active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      {exporting ? <Spinner /> : <DownloadIcon className="h-4 w-4" />}
                      {exporting ? "Baking…" : "Export with animations"}
                    </button>

                    {/* Status / progress */}
                    {exporting && exportState && (
                      <p className="mt-3 text-xs text-muted-foreground">
                        Status: <span className="font-medium text-accent">{exportState.status}</span>
                        {" — baking animations into GLB, this may take a moment…"}
                      </p>
                    )}

                    {/* Error */}
                    {exportError && (
                      <div className="mt-3 rounded-lg border border-danger/30 bg-danger/10 px-4 py-2.5 text-sm text-danger">
                        {exportError}
                      </div>
                    )}

                    {/* Done: download + play baked result */}
                    {exportState?.status === "done" && exportState.download_url && (
                      <div className="mt-4 flex flex-wrap items-center gap-3">
                        <a
                          href={exportState.download_url}
                          download
                          className="inline-flex items-center gap-2 rounded-full border border-accent/40 bg-accent/10 px-4 py-1.5 text-sm font-semibold text-accent transition-colors hover:bg-accent/20"
                        >
                          <DownloadIcon className="h-4 w-4" />
                          Download baked GLB
                        </a>
                        <button
                          onClick={() => setBakedUrl(exportState.download_url)}
                          className="inline-flex items-center gap-2 rounded-full border border-border bg-surface/60 px-4 py-1.5 text-sm font-medium text-muted-foreground transition-colors hover:border-border-strong hover:text-foreground"
                        >
                          <PlayIcon className="h-3.5 w-3.5" />
                          Play baked result
                        </button>
                      </div>
                    )}

                    {/* Baked GLB viewer — the baked GLB already contains the
                        animation tracks natively, so play them directly with
                        ModelViewer (playAnimation), NOT AnimationPlayer (which
                        retargets a separate clip and would show this static). */}
                    {bakedUrl && (
                      <div className="mt-5 overflow-hidden rounded-2xl border border-accent/30">
                        <p className="border-b border-border bg-accent/5 px-4 py-2 text-xs font-medium text-accent">
                          Baked animation preview
                        </p>
                        <ModelViewer
                          key={bakedUrl}
                          glbUrl={bakedUrl}
                          playAnimation
                        />
                      </div>
                    )}
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        )}

        {/* Placeholder while initial processing */}
        {effectiveStatus !== "done" && effectiveStatus !== "failed" && !landmarkQueued && (
          <div className="mt-6 flex h-[400px] items-center justify-center rounded-2xl border border-dashed border-border bg-surface/30 text-sm text-muted-foreground">
            3D viewer will appear when rigging is complete
          </div>
        )}
      </div>
    </div>
  );
}

/* ────────────────────────────── helpers ────────────────────────────── */

function TabButton({
  active,
  onClick,
  icon,
  children,
}: {
  active?: boolean;
  onClick: () => void;
  icon?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      className={`relative inline-flex items-center gap-2 rounded-full px-4 py-1.5 text-sm font-medium transition-colors ${
        active
          ? "text-background"
          : "text-muted-foreground hover:text-foreground"
      }`}
    >
      {active && (
        <motion.span
          layoutId="tab-active"
          className="absolute inset-0 rounded-full bg-accent"
          transition={{ type: "spring", stiffness: 400, damping: 32 }}
        />
      )}
      <span className="relative z-10 flex items-center gap-1.5">
        {icon}
        {children}
      </span>
    </button>
  );
}

function ToolButton({
  active,
  disabled,
  tone = "default",
  onClick,
  icon,
  children,
}: {
  active?: boolean;
  disabled?: boolean;
  tone?: "default" | "danger";
  onClick: () => void;
  icon?: React.ReactNode;
  children: React.ReactNode;
}) {
  const base =
    "inline-flex items-center gap-2 rounded-lg border px-3.5 py-2 text-sm font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50";
  const styles =
    tone === "danger"
      ? "border-border bg-surface/40 text-danger hover:border-danger/40 hover:bg-danger/5"
      : active
        ? "border-accent/50 bg-accent/10 text-accent"
        : "border-border bg-surface/40 text-muted-foreground hover:border-border-strong hover:text-foreground";
  return (
    <button onClick={onClick} disabled={disabled} className={`${base} ${styles}`}>
      {icon}
      {children}
    </button>
  );
}

function Callout({
  tone,
  children,
}: {
  tone: "info" | "warning";
  children: React.ReactNode;
}) {
  const styles =
    tone === "warning"
      ? "border-amber-500/30 bg-amber-500/5 text-amber-200"
      : "border-cyan/30 bg-cyan/5 text-cyan/95";
  return (
    <div className={`mb-4 rounded-xl border px-4 py-3 text-sm ${styles}`}>
      {children}
    </div>
  );
}

function PoseBadge({
  pose,
  angle,
  confidence,
}: {
  pose: DetectedPose;
  angle: number | null;
  confidence: number;
}) {
  const labels: Record<DetectedPose, string> = {
    t_pose: "T-pose",
    a_pose: "A-pose",
    arms_down: "Arms down",
    unclear: "Pose unclear",
  };
  const isOk = pose === "t_pose";
  const cls = isOk
    ? "border-accent/40 bg-accent/10 text-accent"
    : "border-amber-500/40 bg-amber-500/10 text-amber-300";
  const tip = isOk
    ? `Detected ${labels[pose]} — Rigify weights cleanly on this pose.`
    : `Detected ${labels[pose]}. Rigify expects T-pose for cleanest weighting; arms may bind imperfectly.`;
  const angleText =
    angle !== null && Number.isFinite(angle) ? ` · ${angle.toFixed(0)}°` : "";
  const confText = confidence > 0 ? ` (${Math.round(confidence * 100)}%)` : "";

  return (
    <span
      title={tip}
      className={`inline-flex items-center gap-1.5 rounded-lg border px-3 py-2 text-sm font-medium ${cls}`}
    >
      <PersonIcon className="h-3.5 w-3.5" />
      {labels[pose]}
      {angleText}
      {confText}
    </span>
  );
}

/* ────────────────────────────── icons ────────────────────────────── */

function Spinner({ className = "" }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" className={`h-4 w-4 animate-spin ${className}`} fill="none">
      <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="2" opacity="0.25" />
      <path d="M21 12a9 9 0 0 0-9-9" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}
function ViewIcon({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" className={className} fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
      <path d="M3 12c2-4 5-6 9-6s7 2 9 6c-2 4-5 6-9 6s-7-2-9-6z" />
      <circle cx="12" cy="12" r="2.5" />
    </svg>
  );
}
function TargetIcon({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" className={className} fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="9" />
      <circle cx="12" cy="12" r="4" />
      <circle cx="12" cy="12" r="1" fill="currentColor" />
    </svg>
  );
}
function PlayIcon({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" className={className} fill="currentColor">
      <polygon points="6,4 20,12 6,20" />
    </svg>
  );
}
function StopIcon({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" className={className} fill="currentColor">
      <rect x="6" y="6" width="12" height="12" rx="1.5" />
    </svg>
  );
}
function SkeletonIcon({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" className={className} fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="5" r="2" />
      <line x1="12" y1="7" x2="12" y2="14" />
      <line x1="8" y1="9" x2="16" y2="9" />
      <line x1="12" y1="14" x2="9" y2="20" />
      <line x1="12" y1="14" x2="15" y2="20" />
    </svg>
  );
}
function RefreshIcon({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" className={className} fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
      <path d="M3 12a9 9 0 0 1 15-6.7L21 8" />
      <path d="M21 3v5h-5" />
      <path d="M21 12a9 9 0 0 1-15 6.7L3 16" />
      <path d="M3 21v-5h5" />
    </svg>
  );
}
function TerminalIcon({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" className={className} fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
      <rect x="3" y="4" width="18" height="16" rx="2" />
      <path d="M7 9l3 3-3 3" />
      <line x1="13" y1="15" x2="17" y2="15" />
    </svg>
  );
}
function CheckIcon({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" className={className} fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round">
      <path d="M5 12l5 5L20 7" />
    </svg>
  );
}
function DownloadIcon({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" className={className} fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 4v12" />
      <path d="M7 11l5 5 5-5" />
      <path d="M5 20h14" />
    </svg>
  );
}
function AlertIcon({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" className={className ?? "h-5 w-5"} fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="9" />
      <line x1="12" y1="8" x2="12" y2="13" />
      <circle cx="12" cy="16.5" r="0.6" fill="currentColor" />
    </svg>
  );
}
function PersonIcon({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" className={className} fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="6" r="3" />
      <line x1="12" y1="9" x2="12" y2="14" />
      <line x1="6" y1="11" x2="18" y2="11" />
      <line x1="12" y1="14" x2="9" y2="20" />
      <line x1="12" y1="14" x2="15" y2="20" />
    </svg>
  );
}
