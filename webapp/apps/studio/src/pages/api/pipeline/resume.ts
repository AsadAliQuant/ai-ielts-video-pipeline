import type { APIRoute } from "astro"
import { jobManager } from "@/lib/job-manager"

export const POST: APIRoute = async ({ request }) => {
  try {
    const contentType = request.headers.get("content-type") || ""
    let jobId = ""
    let downloadPath: string | undefined
    let fileBuffer: Buffer | undefined

    if (contentType.includes("multipart/form-data")) {
      const formData = await request.formData()
      jobId = (formData.get("jobId") as string) || ""
      downloadPath = (formData.get("downloadPath") as string) || undefined
      const file = formData.get("file") as File | null
      if (file) {
        fileBuffer = Buffer.from(await file.arrayBuffer())
      }
    } else {
      const body = await request.json()
      jobId = body.jobId
      downloadPath = body.downloadPath
    }

    if (!jobId) {
      const active = jobManager.getActiveJob()
      if (active && active.status === "awaiting_visual") {
        jobId = active.id
      } else {
        return new Response(JSON.stringify({ error: "Missing jobId" }), { status: 400 })
      }
    }

    await jobManager.resumeJobWithVisual(jobId, downloadPath || fileBuffer)

    return new Response(JSON.stringify({ success: true, message: "Pipeline resumed" }), {
      status: 200,
      headers: { "Content-Type": "application/json" }
    })
  } catch (err: any) {
    return new Response(JSON.stringify({ error: err.message }), { status: 400 })
  }
}
