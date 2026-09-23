import type { APIRoute } from "astro"
import { checkSystemHealth } from "@/lib/system-service"

export const GET: APIRoute = async () => {
  try {
    const health = await checkSystemHealth()
    return new Response(JSON.stringify(health), {
      status: 200,
      headers: { "Content-Type": "application/json" }
    })
  } catch (err: any) {
    return new Response(JSON.stringify({ error: err.message }), { status: 500 })
  }
}
