"use client";

import { useParams } from "next/navigation";
import { useRigStatus } from "@/hooks/useRigStatus";
import { ModelViewer } from "@/components/ModelViewer";

export default function EditorPage() {
  const { modelId } = useParams<{ modelId: string }>();
  const { status, pct, step, glbUrl, error } = useRigStatus(modelId);

  return (
    <div style={{ maxWidth: 1100, margin: "2rem auto", padding: "0 1rem" }}>
      <h1
        style={{ fontSize: "1.6rem", fontWeight: 800, marginBottom: "0.5rem" }}
      >
        Model Editor
      </h1>

      {/* Status bar — visible while processing */}
      {status !== "done" && (
        <div
          style={{
            background: "#12121a",
            border: "1px solid #2a2a3d",
            borderRadius: 10,
            padding: "1.25rem 1.5rem",
            marginBottom: "1.5rem",
          }}
        >
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              marginBottom: "0.75rem",
            }}
          >
            <span style={{ fontWeight: 600 }}>
              {status === "failed" ? "❌ Rigging failed" : `⚙️ ${step}`}
            </span>
            <span style={{ color: "#6c63ff", fontWeight: 700 }}>{pct}%</span>
          </div>

          {/* Progress bar */}
          <div
            style={{
              background: "#1a1a2e",
              borderRadius: 6,
              height: 8,
              overflow: "hidden",
            }}
          >
            <div
              style={{
                width: `${pct}%`,
                height: "100%",
                background:
                  status === "failed"
                    ? "#ff6b6b"
                    : "linear-gradient(90deg, #6c63ff, #00d4ff)",
                borderRadius: 6,
                transition: "width 0.5s ease",
              }}
            />
          </div>

          {error && (
            <div
              style={{
                color: "#ff6b6b",
                fontSize: "0.85rem",
                marginTop: "0.75rem",
              }}
            >
              {error}
            </div>
          )}
        </div>
      )}

      {/* 3D Viewer — only shown when rigging is complete */}
      {status === "done" && glbUrl ? (
        <div>
          <div
            style={{
              background: "rgba(0,230,118,0.08)",
              border: "1px solid rgba(0,230,118,0.2)",
              borderRadius: 8,
              padding: "0.75rem 1rem",
              color: "#00e676",
              marginBottom: "1rem",
              fontSize: "0.9rem",
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              gap: "1rem",
              flexWrap: "wrap",
            }}
          >
            <span>✅ Rigging complete! Your model is ready.</span>
            <a
              href={glbUrl}
              download
              style={{
                padding: "0.5rem 0.9rem",
                background:
                  "linear-gradient(135deg, rgba(108,99,255,0.15), rgba(0,212,255,0.25))",
                border: "1px solid rgba(108,99,255,0.7)",
                borderRadius: 999,
                color: "#ffffff",
                fontSize: "0.85rem",
                fontWeight: 600,
                textDecoration: "none",
                display: "inline-flex",
                alignItems: "center",
                gap: "0.4rem",
                whiteSpace: "nowrap",
              }}
            >
              ⬇️ Download rigged FBX
            </a>
          </div>
          <ModelViewer glbUrl={glbUrl} height={550} />
        </div>
      ) : status === "failed" ? (
        <div style={{ textAlign: "center", padding: "4rem", color: "#888" }}>
          <div style={{ fontSize: "3rem", marginBottom: "1rem" }}>😞</div>
          <div>Rigging failed. Try uploading a different model format.</div>
        </div>
      ) : (
        /* Placeholder shown while processing */
        <div
          style={{
            height: 400,
            background: "#0a0a14",
            borderRadius: 12,
            border: "1px dashed #2a2a3d",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            color: "#888",
            fontSize: "0.9rem",
          }}
        >
          3D viewer will appear when rigging is complete
        </div>
      )}
    </div>
  );
}
