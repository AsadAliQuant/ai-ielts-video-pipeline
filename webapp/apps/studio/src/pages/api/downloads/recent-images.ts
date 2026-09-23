import type { APIRoute } from "astro"
import { getRecentDownloads } from "@/lib/downloads-service"

export const GET: APIRoute = async () => {
  try {
    const images = await getRecentDownloads(180) // last 3 hours
    return new Response(JSON.stringify(images), {
      status: 200,
      headers: { "Content-Type": "application/json" }
    })
  } catch (err: any) {
    return new Response(JSON.stringify({ error: err.message }), { status: 500 })
  }
}
