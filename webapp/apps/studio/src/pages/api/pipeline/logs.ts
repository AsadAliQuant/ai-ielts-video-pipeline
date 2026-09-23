import type { APIRoute } from "astro"
import { jobManager } from "@/lib/job-manager"

export const GET: APIRoute = async ({ request }) => {
  const activeJob = jobManager.getActiveJob()

  const stream = new ReadableStream({
    start(controller) {
      const encoder = new TextEncoder()

      const sendEvent = (event: string, data: any) => {
        try {
          controller.enqueue(encoder.encode(`event: ${event}\ndata: ${JSON.stringify(data)}\n\n`))
        } catch {
          // stream might be closed
        }
      }

      // Send initial state
      if (activeJob) {
        sendEvent("initial_state", {
          id: activeJob.id,
          status: activeJob.status,
          currentStage: activeJob.currentStage,
          testId: activeJob.testId,
          logs: activeJob.logs,
          visualPrompt: activeJob.visualPrompt
        })
      } else {
        sendEvent("initial_state", null)
      }

      // Listen for log and status updates
      const onLog = (data: { jobId: string; message: string }) => {
        sendEvent("log", data)
      }

      const onStatusChange = (data: any) => {
        sendEvent("status_change", data)
      }

      jobManager.on("log", onLog)
      jobManager.on("status_change", onStatusChange)

      // Ping interval to keep connection alive
      const interval = setInterval(() => {
        try {
          controller.enqueue(encoder.encode(": ping\n\n"))
        } catch {
          cleanup()
        }
      }, 15000)

      const cleanup = () => {
        clearInterval(interval)
        jobManager.off("log", onLog)
        jobManager.off("status_change", onStatusChange)
      }

      request.signal.addEventListener("abort", () => {
        cleanup()
        try {
          controller.close()
        } catch {
          // ignore
        }
      })
    }
  })

  return new Response(stream, {
    status: 200,
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache",
      Connection: "keep-alive"
    }
  })
}
