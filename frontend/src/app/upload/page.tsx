"use client";

import { useState, useRef } from "react";
import { useRouter } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import { uploadModel, type ModelRotation } from "@/lib/api";
import { RotationPreview } from "@/components/RotationPreview";
import { IDENTITY_ROTATION_QUATERNION } from "@/lib/modelRotation";

export default function UploadPage() {
  const router = useRouter();
  const fileInput = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [name, setName] = useState("");
  const [rotation, setRotation] = useState<ModelRotation>({ x: 0, y: 0, z: 0 });
  const [rotationQuaternion, setRotationQuaternion] = useState(IDENTITY_ROTATION_QUATERNION);
  const [uploading, setUploading] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    const dropped = e.dataTransfer.files[0];
    if (dropped) handleFileSelect(dropped);
  };

  const handleFileSelect = (selected: File) => {
    const allowed = ["fbx", "glb", "gltf", "obj"];
    const ext = selected.name.split(".").pop()?.toLowerCase();
    if (!ext || !allowed.includes(ext)) {
      setError(`Unsupported file type: .${ext}. Use FBX, GLB, GLTF, or OBJ.`);
      return;
    }
    if (selected.size > 100 * 1024 * 1024) {
      setError("File too large. Maximum size is 100MB.");
      return;
    }
    setFile(selected);
    setName(selected.name.replace(/\.[^.]+$/, ""));
    setRotation({ x: 0, y: 0, z: 0 });
    setRotationQuaternion(IDENTITY_ROTATION_QUATERNION);
    setError(null);
  };

  const handleSubmit = async () => {
    if (!file || !name.trim()) return;
    setUploading(true);
    setError(null);
    try {
      const { data } = await uploadModel(file, name, rotation, rotationQuaternion);
      router.push(`/editor/${data.id}`);
    } catch (err: unknown) {
      const response = typeof err === "object" && err !== null && "response" in err
        ? (err as {
            response?: { data?: { detail?: string; error?: unknown } };
            message?: string;
          }).response
        : undefined;
      const message = typeof err === "object" && err !== null && "message" in err
        ? String((err as { message?: string }).message)
        : null;
      const msg =
        response?.data?.detail ||
        (typeof response?.data?.error === "string" ? response.data.error : null) ||
        response?.data?.error ||
        message ||
        "Upload failed. Please try again.";
      setError(String(msg));
      setUploading(false);
    }
  };

  const ext = file?.name.split(".").pop()?.toUpperCase();
  const sizeMB = file ? (file.size / (1024 * 1024)).toFixed(1) : null;

  return (
    <div className="relative isolate min-h-[100svh] overflow-hidden pt-32 pb-20">
      <div className="pointer-events-none absolute inset-0 -z-10">
        <div className="absolute -top-1/4 -right-1/4 h-[60vh] w-[60vh] rounded-full bg-accent/12 blur-[140px] [animation:var(--animate-aurora-1)]" />
      </div>

      <motion.div
        initial={{ opacity: 0, y: 16 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6, ease: [0.16, 1, 0.3, 1] }}
        className="mx-auto w-full max-w-2xl px-6"
      >
        <span className="font-mono text-xs uppercase tracking-[0.25em] text-accent">
          // Step 01 / Upload
        </span>
        <h1 className="mt-3 text-balance text-4xl font-bold tracking-[-0.02em] text-foreground sm:text-5xl">
          Upload your 3D model
        </h1>
        <p className="mt-3 text-muted-foreground">
          FBX, GLB, GLTF, or OBJ — up to 100MB. We&apos;ll auto-rig it the moment you submit.
        </p>

        {/* Drop zone */}
        <button
          type="button"
          onDrop={handleDrop}
          onDragOver={(e) => {
            e.preventDefault();
            setDragOver(true);
          }}
          onDragLeave={() => setDragOver(false)}
          onClick={() => fileInput.current?.click()}
          className={`mt-8 group relative w-full overflow-hidden rounded-2xl border bg-surface/40 px-6 py-10 text-left backdrop-blur transition-all ${
            file
              ? "border-accent/50 bg-accent/5"
              : dragOver
                ? "border-accent border-dashed bg-accent/10"
                : "border-dashed border-border hover:border-border-strong hover:bg-surface/60"
          }`}
        >
          {/* Animated border glow on dragOver */}
          {dragOver && (
            <span className="pointer-events-none absolute inset-0 animate-pulse rounded-2xl ring-2 ring-accent/40" />
          )}

          <div className="flex items-center gap-5">
            <div
              className={`flex h-14 w-14 shrink-0 items-center justify-center rounded-xl border transition-colors ${
                file
                  ? "border-accent/40 bg-accent/15 text-accent"
                  : "border-border bg-background text-muted-foreground"
              }`}
            >
              {file ? <CheckIcon /> : <UploadIcon />}
            </div>
            <div className="min-w-0 flex-1">
              {file ? (
                <>
                  <div className="truncate font-medium text-foreground">{file.name}</div>
                  <div className="mt-0.5 flex items-center gap-2 font-mono text-[11px] uppercase tracking-[0.18em] text-muted">
                    <span>{ext}</span>
                    <span className="text-border-strong">·</span>
                    <span>{sizeMB} MB</span>
                  </div>
                </>
              ) : (
                <>
                  <div className="font-medium text-foreground">
                    Drop your mesh here, or click to browse
                  </div>
                  <div className="mt-0.5 font-mono text-[11px] uppercase tracking-[0.18em] text-muted">
                    .fbx · .glb · .gltf · .obj
                  </div>
                </>
              )}
            </div>
            {file && (
              <span className="font-mono text-[10px] uppercase tracking-[0.2em] text-muted-foreground">
                Replace
              </span>
            )}
          </div>
          <input
            ref={fileInput}
            type="file"
            accept=".fbx,.glb,.gltf,.obj"
            className="sr-only"
            onChange={(e) => e.target.files?.[0] && handleFileSelect(e.target.files[0])}
          />
        </button>

        <AnimatePresence>
          {file && (
            <motion.div
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: 8 }}
              transition={{ duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
              className="mt-6 space-y-5"
            >
              <RotationPreview
                file={file}
                rotation={rotation}
                rotationQuaternion={rotationQuaternion}
                onChangeRotation={(nextRotation, nextQuaternion) => {
                  setRotation(nextRotation);
                  setRotationQuaternion(nextQuaternion);
                }}
              />

              <div>
                <label
                  htmlFor="model-name"
                  className="mb-1.5 block font-mono text-[10px] uppercase tracking-[0.2em] text-muted-foreground"
                >
                  Model name
                </label>
                <input
                  id="model-name"
                  type="text"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  className="w-full rounded-lg border border-border bg-background/60 px-4 py-2.5 text-foreground placeholder:text-muted transition-colors focus:border-accent/50 focus:bg-background focus:outline-none focus:ring-2 focus:ring-accent/15"
                />
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        <AnimatePresence>
          {error && (
            <motion.div
              initial={{ opacity: 0, y: -8, height: 0 }}
              animate={{ opacity: 1, y: 0, height: "auto" }}
              exit={{ opacity: 0, y: -8, height: 0 }}
              className="mt-5 overflow-hidden"
              role="alert"
            >
              <div className="flex items-start gap-2.5 rounded-lg border border-danger/30 bg-danger/10 px-4 py-2.5 text-sm text-danger">
                <AlertIcon />
                <span>{error}</span>
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        <button
          onClick={handleSubmit}
          disabled={!file || !name.trim() || uploading}
          className="group relative mt-6 flex h-12 w-full items-center justify-center overflow-hidden rounded-full bg-accent font-semibold text-background shadow-[var(--shadow-glow-accent)] transition-transform hover:scale-[1.01] active:scale-[0.99] disabled:cursor-not-allowed disabled:bg-surface disabled:text-muted disabled:shadow-none"
        >
          <span className="relative z-10 flex items-center gap-2 text-sm">
            {uploading ? (
              <>
                <Spinner /> Uploading and rigging…
              </>
            ) : (
              <>
                Upload & auto-rig
                <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-0.5" />
              </>
            )}
          </span>
          {!uploading && file && name.trim() && (
            <span className="pointer-events-none absolute inset-0 -translate-x-full bg-gradient-to-r from-transparent via-white/45 to-transparent group-hover:animate-[shimmer_1.1s_ease-in-out]" />
          )}
        </button>
      </motion.div>
    </div>
  );
}

function UploadIcon() {
  return (
    <svg viewBox="0 0 24 24" className="h-6 w-6" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 16V4" />
      <path d="M7 9l5-5 5 5" />
      <path d="M5 20h14" />
    </svg>
  );
}
function CheckIcon() {
  return (
    <svg viewBox="0 0 24 24" className="h-6 w-6" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M5 12l5 5L20 7" />
    </svg>
  );
}
function ArrowRight({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 16 16" className={className} fill="none">
      <path d="M3 8h10M9 4l4 4-4 4" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
function AlertIcon() {
  return (
    <svg viewBox="0 0 24 24" className="mt-0.5 h-4 w-4 shrink-0" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="9" />
      <line x1="12" y1="8" x2="12" y2="13" />
      <circle cx="12" cy="16.5" r="0.6" fill="currentColor" />
    </svg>
  );
}
function Spinner() {
  return (
    <svg viewBox="0 0 24 24" className="h-4 w-4 animate-spin" fill="none">
      <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="2" opacity="0.25" />
      <path d="M21 12a9 9 0 0 0-9-9" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}
