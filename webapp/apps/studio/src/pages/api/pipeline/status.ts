import type { APIRoute } from "astro"
import { jobManager } from "@/lib/job-manager"

export const GET: APIRoute = async () => {
  const activeJob = jobManager.getActiveJob()
  return new Response(JSON.stringify({ activeJob }), {
    status: 200,
    headers: { "Content-Type": "application/json" }
  })
}
