"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { hasAuthSession } from "@/lib/auth";

interface Category {
  id: number;
  name: string;
  slug: string;
  icon: string;
}

interface ApiErrorShape {
  detail?: string;
  file?: string[];
  name?: string[];
  error?: string;
}

export default function UploadAnimationPage() {
  const router = useRouter();
  const fileInput = useRef<HTMLInputElement>(null);

  const [file, setFile] = useState<File | null>(null);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [categorySlug, setCategorySlug] = useState("");
  const [tags, setTags] = useState("");
  const [isLooping, setIsLooping] = useState(false);
  const [isPublic, setIsPublic] = useState(false);
  const [categories, setCategories] = useState<Category[]>([]);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dragOver, setDragOver] = useState(false);

  useEffect(() => {
    if (!hasAuthSession()) router.replace("/login");
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
      form.append("is_public", String(isPublic));

      await api.post("/animations/", form);
      router.push("/animations");
    } catch (err: unknown) {
      const maybeError = err as {
        response?: { data?: ApiErrorShape };
        message?: string;
      };
      const data = maybeError.response?.data;

      const msg =
        data?.detail ||
        data?.file?.[0] ||
        data?.name?.[0] ||
        (typeof data?.error === "string" ? data.error : null) ||
        maybeError.message ||
        "Upload failed. Please try again.";

      setError(String(msg));
      setUploading(false);
    }
  };

  return (
    <div className="mx-auto my-12 w-full max-w-2xl px-4 text-slate-100">
      <header className="mb-8">
        <h1 className="text-3xl font-bold">Upload animation</h1>
        <p className="mt-2 text-slate-400">
          Supports GLB, GLTF, FBX — up to 100 MB.
        </p>
      </header>

      <div
        onDrop={(e) => {
          e.preventDefault();
          setDragOver(false);
          const dropped = e.dataTransfer.files[0];
          if (dropped) handleFileSelect(dropped);
        }}
        onDragOver={(e) => {
          e.preventDefault();
          setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onClick={() => fileInput.current?.click()}
        className={`mb-6 cursor-pointer rounded-xl border-2 border-dashed p-8 text-center transition ${
          file
            ? "border-violet-500 bg-violet-500/10"
            : dragOver
              ? "border-cyan-400 bg-cyan-500/10"
              : "border-slate-700 bg-transparent"
        }`}
      >
        <div className="mb-2 text-4xl">{file ? "🎞️" : "⬆️"}</div>
        {file ? (
          <>
            <p className="font-semibold text-violet-300">{file.name}</p>
            <p className="mt-1 text-sm text-slate-400">
              {(file.size / (1024 * 1024)).toFixed(1)} MB
            </p>
          </>
        ) : (
          <>
            <p className="font-semibold">Drop your animation file here</p>
            <p className="text-sm text-slate-400">or click to browse</p>
          </>
        )}

        <input
          ref={fileInput}
          type="file"
          accept=".glb,.gltf,.fbx"
          className="hidden"
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) handleFileSelect(f);
          }}
        />
      </div>

      <div className="space-y-4">
        <input
          className="w-full rounded-lg border border-slate-700 bg-slate-900 px-4 py-3"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="Animation name *"
        />

        <textarea
          className="min-h-24 w-full rounded-lg border border-slate-700 bg-slate-900 px-4 py-3"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          placeholder="Description"
        />

        <select
          className="w-full rounded-lg border border-slate-700 bg-slate-900 px-4 py-3"
          value={categorySlug}
          onChange={(e) => setCategorySlug(e.target.value)}
        >
          <option value="">Category (optional)</option>
          {categories.map((c) => (
            <option key={c.slug} value={c.slug}>
              {c.icon} {c.name}
            </option>
          ))}
        </select>

        <input
          className="w-full rounded-lg border border-slate-700 bg-slate-900 px-4 py-3"
          value={tags}
          onChange={(e) => setTags(e.target.value)}
          placeholder="Tags (comma separated)"
        />

        <div className="flex flex-wrap gap-6 text-sm">
          <label className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={isLooping}
              onChange={(e) => setIsLooping(e.target.checked)}
            />
            Looping animation
          </label>

          <label className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={isPublic}
              onChange={(e) => setIsPublic(e.target.checked)}
            />
            Public (review required)
          </label>
        </div>

        {error && (
          <div className="rounded-lg border border-rose-500/40 bg-rose-500/10 px-4 py-3 text-rose-300">
            {error}
          </div>
        )}

        <button
          onClick={handleSubmit}
          disabled={uploading || !file || !name.trim()}
          className="w-full rounded-lg bg-gradient-to-r from-violet-500 to-cyan-400 px-4 py-3 font-semibold text-slate-950 disabled:cursor-not-allowed disabled:from-slate-700 disabled:to-slate-700 disabled:text-slate-400"
        >
          {uploading ? "Uploading…" : "Upload animation"}
        </button>
      </div>
    </div>
  );
}