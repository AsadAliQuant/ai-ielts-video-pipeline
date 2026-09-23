import type { APIRoute } from "astro"
import { jobManager } from "@/lib/job-manager"

export const POST: APIRoute = async ({ request }) => {
  try {
    let jobId = ""
    try {
      const body = await request.json()
      jobId = body.jobId
    } catch {
      // ignore
    }

    if (!jobId) {
      const active = jobManager.getActiveJob()
      if (active) jobId = active.id
    }

    if (!jobId) {
      return new Response(JSON.stringify({ error: "No active job found" }), { status: 400 })
    }

    const success = await jobManager.cancelJob(jobId)
    return new Response(JSON.stringify({ success }), {
      status: 200,
      headers: { "Content-Type": "application/json" }
    })
  } catch (err: any) {
    return new Response(JSON.stringify({ error: err.message }), { status: 500 })
  }
}
