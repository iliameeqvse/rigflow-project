"use client";

import { useState, useRef, useEffect } from "react";
import { useRouter } from "next/navigation";
import { uploadAnimation } from "@/lib/api";
import api from "@/lib/api";

interface Category {
  id: number;
  name: string;
  slug: string;
  icon: string;
}

const inputStyle: React.CSSProperties = {
  width: "100%",
  background: "#0d0d1a",
  border: "1px solid #2a2a3d",
  borderRadius: 8,
  padding: "0.65rem 0.9rem",
  color: "#fff",
  fontSize: "0.95rem",
  outline: "none",
  boxSizing: "border-box",
};

const labelStyle: React.CSSProperties = {
  display: "block",
  fontSize: "0.8rem",
  fontWeight: 600,
  color: "#a0a0c0",
  marginBottom: "0.4rem",
  textTransform: "uppercase",
  letterSpacing: "0.06em",
};

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

  // Auth guard — redirect to login if no token
  useEffect(() => {
    const token = localStorage.getItem("access");
    if (!token) router.replace("/login");
  }, [router]);

  // Load categories from API
  useEffect(() => {
    api
      .get<Category[]>("/animations/categories/")
      .then(({ data }) => setCategories(data))
      .catch(() => {}); // non-fatal
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
      // uploadAnimation already exists in api.ts
      // We need to send extra fields too, so post manually
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
    } catch (err: any) {
      const data = err.response?.data;
      const msg =
        data?.detail ||
        data?.file?.[0] ||
        data?.name?.[0] ||
        (typeof data?.error === "string" ? data.error : null) ||
        err.message ||
        "Upload failed. Please try again.";
      setError(String(msg));
      setUploading(false);
    }
  };

  return (
    <div style={{ maxWidth: 620, margin: "4rem auto", padding: "0 1rem" }}>
      {/* Header */}
      <div style={{ marginBottom: "2rem" }}>
        <h1
          style={{
            fontSize: "1.8rem",
            fontWeight: 800,
            marginBottom: "0.4rem",
          }}
        >
          Upload animation
        </h1>
        <p style={{ color: "#888" }}>
          Supports GLB, GLTF, FBX — up to 100 MB.{" "}
          {!isPublic && (
            <span style={{ color: "#f59e0b" }}>
              Public animations are reviewed before appearing in the library.
            </span>
          )}
        </p>
      </div>

      {/* Drop zone */}
      <div
        onDrop={handleDrop}
        onDragOver={(e) => {
          e.preventDefault();
          setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onClick={() => fileInput.current?.click()}
        style={{
          border: `2px dashed ${file ? "#6c63ff" : dragOver ? "#00d4ff" : "#2a2a3d"}`,
          borderRadius: 12,
          padding: "2.5rem",
          textAlign: "center",
          cursor: "pointer",
          background: file
            ? "rgba(108,99,255,0.05)"
            : dragOver
              ? "rgba(0,212,255,0.04)"
              : "transparent",
          transition: "all 0.2s",
          marginBottom: "1.5rem",
        }}
      >
        <div style={{ fontSize: "2.5rem", marginBottom: "0.75rem" }}>
          {file ? "🎞️" : "⬆️"}
        </div>
        {file ? (
          <>
            <div style={{ fontWeight: 700, color: "#6c63ff" }}>{file.name}</div>
            <div
              style={{
                color: "#888",
                fontSize: "0.85rem",
                marginTop: "0.25rem",
              }}
            >
              {(file.size / (1024 * 1024)).toFixed(1)} MB ·{" "}
              <span
                onClick={(e) => {
                  e.stopPropagation();
                  setFile(null);
                  setName("");
                }}
                style={{
                  color: "#f87171",
                  cursor: "pointer",
                  textDecoration: "underline",
                }}
              >
                Remove
              </span>
            </div>
          </>
        ) : (
          <>
            <div style={{ fontWeight: 600, marginBottom: "0.3rem" }}>
              Drop your animation file here
            </div>
            <div style={{ color: "#888", fontSize: "0.85rem" }}>
              or click to browse
            </div>
          </>
        )}
        <input
          ref={fileInput}
          type="file"
          accept=".glb,.gltf,.fbx"
          style={{ display: "none" }}
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) handleFileSelect(f);
          }}
        />
      </div>

      {/* Form fields */}
      <div style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }}>
        {/* Name */}
        <div>
          <label style={labelStyle}>Animation name *</label>
          <input
            style={inputStyle}
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g. Idle Breathing Loop"
            maxLength={255}
          />
        </div>

        {/* Description */}
        <div>
          <label style={labelStyle}>Description</label>
          <textarea
            style={{ ...inputStyle, resize: "vertical", minHeight: 80 }}
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Optional — describe the animation style, use case, etc."
          />
        </div>

        {/* Category */}
        <div>
          <label style={labelStyle}>Category</label>
          <select
            style={{ ...inputStyle, cursor: "pointer" }}
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

        {/* Tags */}
        <div>
          <label style={labelStyle}>Tags</label>
          <input
            style={inputStyle}
            value={tags}
            onChange={(e) => setTags(e.target.value)}
            placeholder="walk, locomotion, cycle  (comma-separated)"
          />
        </div>

        {/* Toggles row */}
        <div style={{ display: "flex", gap: "1.5rem", flexWrap: "wrap" }}>
          {/* Looping */}
          <label
            style={{
              display: "flex",
              alignItems: "center",
              gap: "0.6rem",
              cursor: "pointer",
            }}
          >
            <div
              onClick={() => setIsLooping((v) => !v)}
              style={{
                width: 44,
                height: 24,
                borderRadius: 999,
                background: isLooping ? "#6c63ff" : "#2a2a3d",
                position: "relative",
                transition: "background 0.2s",
                flexShrink: 0,
              }}
            >
              <div
                style={{
                  position: "absolute",
                  top: 3,
                  left: isLooping ? 23 : 3,
                  width: 18,
                  height: 18,
                  borderRadius: "50%",
                  background: "#fff",
                  transition: "left 0.2s",
                }}
              />
            </div>
            <span style={{ fontSize: "0.9rem", color: "#ccc" }}>
              Looping animation
            </span>
          </label>

          {/* Public */}
          <label
            style={{
              display: "flex",
              alignItems: "center",
              gap: "0.6rem",
              cursor: "pointer",
            }}
          >
            <div
              onClick={() => setIsPublic((v) => !v)}
              style={{
                width: 44,
                height: 24,
                borderRadius: 999,
                background: isPublic ? "#00c48c" : "#2a2a3d",
                position: "relative",
                transition: "background 0.2s",
                flexShrink: 0,
              }}
            >
              <div
                style={{
                  position: "absolute",
                  top: 3,
                  left: isPublic ? 23 : 3,
                  width: 18,
                  height: 18,
                  borderRadius: "50%",
                  background: "#fff",
                  transition: "left 0.2s",
                }}
              />
            </div>
            <span style={{ fontSize: "0.9rem", color: "#ccc" }}>
              {isPublic ? "Public (pending review)" : "Private (only you)"}
            </span>
          </label>
        </div>

        {/* Error */}
        {error && (
          <div
            style={{
              background: "rgba(248,113,113,0.1)",
              border: "1px solid rgba(248,113,113,0.3)",
              borderRadius: 8,
              padding: "0.75rem 1rem",
              color: "#f87171",
              fontSize: "0.9rem",
            }}
          >
            {error}
          </div>
        )}

        {/* Submit */}
        <button
          onClick={handleSubmit}
          disabled={uploading || !file || !name.trim()}
          style={{
            padding: "0.85rem",
            borderRadius: 10,
            border: "none",
            background:
              uploading || !file || !name.trim()
                ? "#2a2a3d"
                : "linear-gradient(135deg, #6c63ff, #00d4ff)",
            color: uploading || !file || !name.trim() ? "#666" : "#fff",
            fontWeight: 700,
            fontSize: "1rem",
            cursor:
              uploading || !file || !name.trim() ? "not-allowed" : "pointer",
            transition: "all 0.2s",
          }}
        >
          {uploading ? "Uploading…" : "Upload animation"}
        </button>

        <p
          style={{
            color: "#666",
            fontSize: "0.82rem",
            textAlign: "center",
            marginTop: "-0.5rem",
          }}
        >
          By uploading you confirm you have the rights to share this file.
        </p>
      </div>
    </div>
  );
}
