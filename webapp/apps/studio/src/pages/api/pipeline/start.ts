import type { APIRoute } from "astro"
import { jobManager, type PipelineConfig } from "@/lib/job-manager"

export const POST: APIRoute = async ({ request }) => {
  try {
    const config: PipelineConfig = await request.json()
    const job = await jobManager.startJob(config)

    return new Response(JSON.stringify({ success: true, job }), {
      status: 200,
      headers: { "Content-Type": "application/json" }
    })
  } catch (err: any) {
    return new Response(JSON.stringify({ error: err.message }), {
      status: 400,
      headers: { "Content-Type": "application/json" }
    })
  }
}
