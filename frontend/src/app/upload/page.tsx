"use client";

import { useState, useRef } from "react";
import { useRouter } from "next/navigation";
import { uploadModel } from "@/lib/api";

export default function UploadPage() {
  const router = useRouter();
  const fileInput = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [name, setName] = useState("");
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Handle drag-drop onto the upload zone
  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
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
    setName(selected.name.replace(/\.[^.]+$/, "")); // use filename without extension as default name
    setError(null);
  };

  const handleSubmit = async () => {
    if (!file || !name.trim()) return;
    setUploading(true);
    setError(null);
    try {
      const { data } = await uploadModel(file, name);
      // Redirect to editor page with the new rig ID
      // The editor page will poll for completion and show the 3D viewer
      router.push(`/editor/${data.id}`);
    } catch (err: any) {
      const msg =
        err.response?.data?.detail ||
        (typeof err.response?.data?.error === "string"
          ? err.response.data.error
          : null) ||
        err.response?.data?.error ||
        err.message ||
        "Upload failed. Please try again.";
      setError(String(msg));
      setUploading(false);
    }
  };

  return (
    <div style={{ maxWidth: 600, margin: "4rem auto", padding: "0 1rem" }}>
      <h1
        style={{ fontSize: "1.8rem", fontWeight: 800, marginBottom: "0.5rem" }}
      >
        Upload your 3D model
      </h1>
      <p style={{ color: "#888", marginBottom: "2rem" }}>
        Supports FBX, GLB, GLTF, OBJ — up to 100MB
      </p>

      {/* Drop zone */}
      <div
        onDrop={handleDrop}
        onDragOver={(e) => e.preventDefault()}
        onClick={() => fileInput.current?.click()}
        style={{
          border: `2px dashed ${file ? "#6c63ff" : "#2a2a3d"}`,
          borderRadius: 12,
          padding: "3rem",
          textAlign: "center",
          cursor: "pointer",
          background: file ? "rgba(108,99,255,0.05)" : "transparent",
          transition: "all 0.2s",
          marginBottom: "1.5rem",
        }}
      >
        <div style={{ fontSize: "3rem", marginBottom: "1rem" }}>
          {file ? "✅" : "📦"}
        </div>
        <div style={{ fontWeight: 600, marginBottom: "0.5rem" }}>
          {file ? file.name : "Drop your model here or click to browse"}
        </div>
        {file && (
          <div style={{ color: "#888", fontSize: "0.85rem" }}>
            {(file.size / (1024 * 1024)).toFixed(1)} MB
          </div>
        )}
        <input
          ref={fileInput}
          type="file"
          accept=".fbx,.glb,.gltf,.obj"
          style={{ display: "none" }}
          onChange={(e) =>
            e.target.files?.[0] && handleFileSelect(e.target.files[0])
          }
        />
      </div>

      {/* Name input */}
      {file && (
        <div style={{ marginBottom: "1.5rem" }}>
          <label
            style={{
              display: "block",
              marginBottom: "0.5rem",
              fontWeight: 600,
            }}
          >
            Model name
          </label>
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            style={{
              width: "100%",
              padding: "0.75rem 1rem",
              background: "#12121a",
              border: "1px solid #2a2a3d",
              borderRadius: 8,
              color: "#fff",
              fontSize: "1rem",
            }}
          />
        </div>
      )}

      {error && (
        <div
          style={{
            background: "rgba(255,107,107,0.1)",
            border: "1px solid rgba(255,107,107,0.3)",
            borderRadius: 8,
            padding: "0.75rem 1rem",
            color: "#ff6b6b",
            marginBottom: "1.5rem",
            fontSize: "0.9rem",
          }}
        >
          ⚠️ {error}
        </div>
      )}

      <button
        onClick={handleSubmit}
        disabled={!file || !name.trim() || uploading}
        style={{
          width: "100%",
          padding: "0.9rem",
          background: uploading || !file ? "#2a2a3d" : "#6c63ff",
          border: "none",
          borderRadius: 10,
          color: "#fff",
          fontSize: "1rem",
          fontWeight: 700,
          cursor: uploading || !file ? "not-allowed" : "pointer",
          transition: "background 0.2s",
        }}
      >
        {uploading ? "⏳ Uploading..." : "🚀 Upload & Auto-Rig"}
      </button>
    </div>
  );
}
