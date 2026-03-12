import { useState, useEffect, useCallback } from "react"
import { getRigStatus, RigStatus } from "@/lib/api"

type StatusState = {
  status: "pending" | "processing" | "done" | "failed"
  pct: number
  step: string
  glbUrl: string | null
  error: string | null
}

export function useRigStatus(rigId: string | null) {
  const [state, setState] = useState<StatusState>({
    status: "pending",
    pct: 0,
    step: "Waiting in queue...",
    glbUrl: null,
    error: null,
  })

  useEffect(() => {
    if (!rigId) return

    let ws: WebSocket | null = null
    let pollInterval: NodeJS.Timeout | null = null
    let wsConnected = false

    // ── Try WebSocket first (real-time updates) ───────────────────────────
    const wsUrl = `${process.env.NEXT_PUBLIC_WS_URL ?? "ws://localhost:8000"}/ws/rig/${rigId}/`

    ws = new WebSocket(wsUrl)

    ws.onopen = () => {
      wsConnected = true
      console.log("WebSocket connected for rig:", rigId)
    }

    ws.onmessage = (event) => {
      const data = JSON.parse(event.data)
      setState((prev) => ({
        ...prev,
        status: data.status ?? prev.status,
        pct: data.pct ?? prev.pct,
        step: data.step ?? prev.step,
        glbUrl: data.rigged_glb_url ?? prev.glbUrl,
        error: data.error ?? null,
      }))
    }

    ws.onerror = () => {
      // WebSocket failed (maybe Daphne not running) — fall back to polling
      console.warn("WebSocket failed, falling back to HTTP polling")
      startPolling()
    }

    // ── HTTP polling fallback ─────────────────────────────────────────────
    const startPolling = () => {
      pollInterval = setInterval(async () => {
        try {
          const { data } = await getRigStatus(rigId)
          setState({
            status: data.status as StatusState["status"],
            pct: data.progress?.pct ?? 50,
            step: data.progress?.step ?? "Processing...",
            glbUrl: data.rigged_glb_url,
            error: null,
          })
          // Stop polling once we reach a terminal state
          if (data.status === "done" || data.status === "failed") {
            if (pollInterval) clearInterval(pollInterval)
          }
        } catch (err) {
          console.error("Polling error:", err)
        }
      }, 3000) // poll every 3 seconds
    }

    // If WebSocket doesn't connect in 3s, start polling anyway
    const wsTimeout = setTimeout(() => {
      if (!wsConnected) startPolling()
    }, 3000)

    // Cleanup when component unmounts or rigId changes
    return () => {
      ws?.close()
      if (pollInterval) clearInterval(pollInterval)
      clearTimeout(wsTimeout)
    }
  }, [rigId])

  return state
}