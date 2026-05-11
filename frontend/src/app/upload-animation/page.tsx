"use client";

import { useState, useRef, useEffect } from "react";
import { useRouter } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import api, { extractApiError } from "@/lib/api";

interface Category {
  id: number;
  name: string;
  slug: string;
  icon: string;
}

const inputCls =
  "w-full rounded-lg border border-border bg-background/60 px-4 py-2.5 text-foreground placeholder:text-muted transition-colors focus:border-accent/50 focus:bg-background focus:outline-none focus:ring-2 focus:ring-accent/15";

const labelCls =
  "mb-1.5 block font-mono text-[10px] uppercase tracking-[0.2em] text-muted-foreground";

export default function UploadAnimationPage() {
  const router = useRouter();
  const fileInput = useRef<HTMLInputElement>(null);

  const [file, setFile] = useState<File | null>(null);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [categorySlug, setCategorySlug] = useState("");
  const [tags, setTags] = useState("");
  const [isLooping, setIsLooping] = useState(false);
  const [categories, setCategories] = useState<Category[]>([]);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dragOver, setDragOver] = useState(false);

  useEffect(() => {
    if (!localStorage.getItem("access")) router.replace("/login");
  }, [router]);

  useEffect(() => {
    api
      .get<Category[]>("/animations/categories/")
      .then(({ data }) => setCategories(data))
      .catch(() => {});
  }, []);

  const handleFileSelect = (selected: File) => {
    const ext = selected.name.split(".").pop()?.toLowerCase();
    if (!ext || !["glb", "gltf", "fbx"].includes(ext)) {
      setError(`Unsupported file type: .${ext}. Use GLB, GLTF, or FBX.`);
      return;
    }
    if (selected.size > 100 * 1024 * 1024) {
      setError("File too large. Maximum size is 100 MB.");
      return;
    }
    setFile(selected);
    if (!name) setName(selected.name.replace(/\.[^.]+$/, ""));
    setError(null);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    const dropped = e.dataTransfer.files[0];
    if (dropped) handleFileSelect(dropped);
  };

  const handleSubmit = async () => {
    if (!file || !name.trim()) {
      setError("Please select a file and enter a name.");
      return;
    }
    setUploading(true);
    setError(null);
    try {
      const form = new FormData();
      form.append("file", file);
      form.append("name", name.trim());
      form.append("description", description);
      form.append("category_slug", categorySlug);
      form.append("tags", tags);
      form.append("is_looping", String(isLooping));
      await api.post("/animations/", form);
      router.push("/animations");
    } catch (err: unknown) {
      setError(extractApiError(err, "Upload failed. Please try again."));
      setUploading(false);
    }
  };

  const ext = file?.name.split(".").pop()?.toUpperCase();
  const sizeMB = file ? (file.size / (1024 * 1024)).toFixed(1) : null;

  return (
    <div className="relative isolate min-h-[100svh] overflow-hidden pt-32 pb-20">
      <div className="pointer-events-none absolute inset-0 -z-10">
        <div className="absolute -top-1/4 left-1/4 h-[55vh] w-[55vh] rounded-full bg-accent/12 blur-[140px] [animation:var(--animate-aurora-2)]" />
      </div>

      <motion.div
        initial={{ opacity: 0, y: 16 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6, ease: [0.16, 1, 0.3, 1] }}
        className="mx-auto w-full max-w-2xl px-6"
      >
        <span className="font-mono text-xs uppercase tracking-[0.25em] text-accent">
          {"// Contribute / Animations"}
        </span>
        <h1 className="mt-3 text-balance text-4xl font-bold tracking-[-0.02em] text-foreground sm:text-5xl">
          Upload an animation
        </h1>
        <p className="mt-3 text-muted-foreground">
          GLB, GLTF, or FBX — up to 100 MB. Goes live in your team library immediately.
        </p>

        <button
          type="button"
          onDrop={handleDrop}
          onDragOver={(e) => {
            e.preventDefault();
            setDragOver(true);
          }}
          onDragLeave={() => setDragOver(false)}
          onClick={() => fileInput.current?.click()}
          className={`mt-8 group relative w-full overflow-hidden rounded-2xl border bg-surface/40 px-6 py-9 text-left backdrop-blur transition-all ${
            file
              ? "border-accent/50 bg-accent/5"
              : dragOver
                ? "border-accent border-dashed bg-accent/10"
                : "border-dashed border-border hover:border-border-strong hover:bg-surface/60"
          }`}
        >
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
              {file ? <FilmIcon /> : <UploadIcon />}
            </div>
            <div className="min-w-0 flex-1">
              {file ? (
                <>
                  <div className="truncate font-medium text-foreground">{file.name}</div>
                  <div className="mt-0.5 flex items-center gap-2 font-mono text-[11px] uppercase tracking-[0.18em] text-muted">
                    <span>{ext}</span>
                    <span className="text-border-strong">·</span>
                    <span>{sizeMB} MB</span>
                    <span className="text-border-strong">·</span>
                    <span
                      onClick={(e) => {
                        e.stopPropagation();
                        setFile(null);
                        setName("");
                      }}
                      className="cursor-pointer text-danger hover:underline"
                    >
                      Remove
                    </span>
                  </div>
                </>
              ) : (
                <>
                  <div className="font-medium text-foreground">
                    Drop your animation here, or click to browse
                  </div>
                  <div className="mt-0.5 font-mono text-[11px] uppercase tracking-[0.18em] text-muted">
                    .glb · .gltf · .fbx
                  </div>
                </>
              )}
            </div>
          </div>
          <input
            ref={fileInput}
            type="file"
            accept=".glb,.gltf,.fbx"
            className="sr-only"
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) handleFileSelect(f);
            }}
          />
        </button>

        <div className="mt-6 grid gap-5">
          <div>
            <label className={labelCls} htmlFor="anim-name">
              Animation name *
            </label>
            <input
              id="anim-name"
              className={inputCls}
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. Idle Breathing Loop"
              maxLength={255}
            />
          </div>

          <div>
            <label className={labelCls} htmlFor="anim-desc">
              Description
            </label>
            <textarea
              id="anim-desc"
              className={`${inputCls} resize-y min-h-[88px]`}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Optional — describe the animation style or use case"
            />
          </div>

          <div>
            <label className={labelCls} htmlFor="anim-cat">
              Category
            </label>
            <select
              id="anim-cat"
              className={`${inputCls} cursor-pointer`}
              value={categorySlug}
              onChange={(e) => setCategorySlug(e.target.value)}
            >
              <option value="">— None —</option>
              {categories.map((c) => (
                <option key={c.slug} value={c.slug}>
                  {c.icon} {c.name}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className={labelCls} htmlFor="anim-tags">
              Tags
            </label>
            <input
              id="anim-tags"
              className={inputCls}
              value={tags}
              onChange={(e) => setTags(e.target.value)}
              placeholder="walk, locomotion, cycle  (comma-separated)"
            />
          </div>

          <label className="flex cursor-pointer select-none items-center gap-3">
            <button
              type="button"
              onClick={() => setIsLooping((v) => !v)}
              role="switch"
              aria-checked={isLooping}
              className={`relative h-6 w-11 shrink-0 rounded-full transition-colors ${
                isLooping ? "bg-accent" : "bg-border-strong"
              }`}
            >
              <span
                className={`absolute top-[3px] h-[18px] w-[18px] rounded-full bg-background shadow-md transition-all ${
                  isLooping ? "left-[24px]" : "left-[3px]"
                }`}
              />
            </button>
            <span className="text-sm text-muted-foreground">
              Looping animation
            </span>
          </label>

          <AnimatePresence>
            {error && (
              <motion.div
                initial={{ opacity: 0, y: -8, height: 0 }}
                animate={{ opacity: 1, y: 0, height: "auto" }}
                exit={{ opacity: 0, y: -8, height: 0 }}
                className="overflow-hidden"
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
            disabled={uploading || !file || !name.trim()}
            className="group relative mt-2 flex h-12 w-full items-center justify-center overflow-hidden rounded-full bg-accent font-semibold text-background shadow-[var(--shadow-glow-accent)] transition-transform hover:scale-[1.01] active:scale-[0.99] disabled:cursor-not-allowed disabled:bg-surface disabled:text-muted disabled:shadow-none"
          >
            <span className="relative z-10 flex items-center gap-2 text-sm">
              {uploading ? (
                <>
                  <Spinner /> Uploading…
                </>
              ) : (
                <>
                  Upload animation
                  <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-0.5" />
                </>
              )}
            </span>
            {!uploading && file && name.trim() && (
              <span className="pointer-events-none absolute inset-0 -translate-x-full bg-gradient-to-r from-transparent via-white/45 to-transparent group-hover:animate-[shimmer_1.1s_ease-in-out]" />
            )}
          </button>
        </div>
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
function FilmIcon() {
  return (
    <svg viewBox="0 0 24 24" className="h-6 w-6" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
      <rect x="3" y="4" width="18" height="16" rx="2" />
      <line x1="3" y1="9" x2="21" y2="9" />
      <line x1="3" y1="15" x2="21" y2="15" />
      <line x1="8" y1="4" x2="8" y2="20" />
      <line x1="16" y1="4" x2="16" y2="20" />
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
