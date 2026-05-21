import { useState, useEffect } from "react"
import { getRigStatus } from "@/lib/api"

type StatusState = {
  status: "pending" | "processing" | "done" | "failed"
  pct: number
  step: string
  glbUrl: string | null
  error: string | null
}

const TERMINAL_STATUSES: ReadonlySet<StatusState["status"]> = new Set(["done", "failed"])
const POLL_INTERVAL_MS = 3000
const WS_TIMEOUT_MS = 3000
const MAX_CONSECUTIVE_POLL_FAILURES = 5

export function useRigStatus(rigId: string | null, restartKey: number = 0) {
  const [state, setState] = useState<StatusState>({
    status: "pending",
    pct: 0,
    step: "Waiting in queue...",
    glbUrl: null,
    error: null,
  })

  useEffect(() => {
    if (!rigId) return
    // A change in restartKey (e.g. after POST /rerig-landmarks/) re-enters
    // this effect, which restarts polling. The first poll then pulls the
    // fresh server status (pending → processing → done) into state.

    let ws: WebSocket | null = null
    let pollInterval: ReturnType<typeof setInterval> | null = null
    let pollStarted = false
    let consecutiveFailures = 0
    let cancelled = false

    const stopPolling = () => {
      if (pollInterval) {
        clearInterval(pollInterval)
        pollInterval = null
      }
    }

    const poll = async () => {
      try {
        const { data } = await getRigStatus(rigId)
        if (cancelled) return
        consecutiveFailures = 0
        const status = data.status as StatusState["status"]
        setState({
          status,
          pct: data.progress?.pct ?? 50,
          step: data.progress?.step ?? "Processing...",
          glbUrl: data.rigged_glb_url,
          error: data.error_message?.trim() || null,
        })
        if (TERMINAL_STATUSES.has(status)) {
          stopPolling()
          ws?.close()
        }
      } catch {
        if (cancelled) return
        consecutiveFailures += 1
        if (consecutiveFailures >= MAX_CONSECUTIVE_POLL_FAILURES) {
          stopPolling()
          setState((prev) => ({
            ...prev,
            status: "failed",
            error: "Lost contact with the server. Check that the backend is running.",
          }))
        }
      }
    }

    const startPolling = () => {
      if (pollStarted || cancelled) return
      pollStarted = true
      poll()
      pollInterval = setInterval(poll, POLL_INTERVAL_MS)
    }

    // Only attempt WebSocket if explicitly configured. Without Channels
    // routing wired into asgi.py, opening ws://localhost:8000/ws/rig/<id>/
    // hits Django's HTTP handler, returns 404, and spams the dev console
    // every editor mount. Set NEXT_PUBLIC_WS_URL once you actually wire up
    // a Channels consumer; otherwise polling alone is fine.
    const wsBase = process.env.NEXT_PUBLIC_WS_URL
    if (wsBase) {
      const wsUrl = `${wsBase}/ws/rig/${rigId}/`
      try {
        ws = new WebSocket(wsUrl)
      } catch {
        startPolling()
      }

      if (ws) {
        ws.onmessage = (event) => {
          try {
            const data = JSON.parse(event.data)
            setState((prev) => ({
              ...prev,
              status: data.status ?? prev.status,
              pct: data.pct ?? prev.pct,
              step: data.step ?? prev.step,
              glbUrl: data.rigged_glb_url ?? prev.glbUrl,
              error: data.error ?? prev.error,
            }))
            if (data.status && TERMINAL_STATUSES.has(data.status)) {
              stopPolling()
              ws?.close()
            }
          } catch {
            // Malformed WS frame — ignore, we'll catch up via polling.
          }
        }
        ws.onerror = () => startPolling()
        ws.onclose = () => startPolling()
      }
    } else {
      // No WS configured — go straight to polling.
      startPolling()
    }

    // Fallback: if the WS isn't open within WS_TIMEOUT_MS, poll anyway.
    const wsBackstop = setTimeout(() => {
      if (!ws || ws.readyState !== WebSocket.OPEN) startPolling()
    }, WS_TIMEOUT_MS)

    return () => {
      cancelled = true
      ws?.close()
      stopPolling()
      clearTimeout(wsBackstop)
    }
  }, [rigId, restartKey])

  return state
}
