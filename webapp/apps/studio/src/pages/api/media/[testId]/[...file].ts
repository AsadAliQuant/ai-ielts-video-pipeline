import type { APIRoute } from "astro"
export const prerender = false
import path from "node:path"
import fsSync from "node:fs"
import fs from "node:fs/promises"
import { getTestsDir } from "@/lib/test-service"

export const GET: APIRoute = async ({ params, request }) => {
  const { testId, file } = params
  if (!testId || !file) {
    return new Response("Missing parameters", { status: 400 })
  }

  // Prevent path traversal
  const normalizedFile = path.normalize(file).replace(/^(\.\.(\/|\\|$))+/, "")
  const filePath = path.join(getTestsDir(), testId, normalizedFile)

  if (!fsSync.existsSync(filePath)) {
    return new Response("File not found", { status: 404 })
  }

  const stat = await fs.stat(filePath)
  const fileSize = stat.size

  // Determine mime type
  const ext = path.extname(filePath).toLowerCase()
  let contentType = "application/octet-stream"
  if (ext === ".mp4") contentType = "video/mp4"
  else if (ext === ".wav") contentType = "audio/wav"
  else if (ext === ".mp3") contentType = "audio/mpeg"
  else if (ext === ".png") contentType = "image/png"
  else if (ext === ".jpg" || ext === ".jpeg") contentType = "image/jpeg"
  else if (ext === ".txt" || ext === ".md") contentType = "text/plain; charset=utf-8"
  else if (ext === ".json") contentType = "application/json"

  // Handle Range header for video / audio seeking
  const rangeHeader = request.headers.get("range")
  if (rangeHeader && (contentType.startsWith("video/") || contentType.startsWith("audio/"))) {
    const parts = rangeHeader.replace(/bytes=/, "").split("-")
    const start = parseInt(parts[0], 10)
    const end = parts[1] ? parseInt(parts[1], 10) : fileSize - 1
    const chunkSize = end - start + 1

    const nodeStream = fsSync.createReadStream(filePath, { start, end })
    // Convert Node stream to web ReadableStream
    const webStream = new ReadableStream({
      start(controller) {
        nodeStream.on("data", (chunk) => controller.enqueue(chunk))
        nodeStream.on("end", () => controller.close())
        nodeStream.on("error", (err) => controller.error(err))
      },
      cancel() {
        nodeStream.destroy()
      }
    })

    return new Response(webStream, {
      status: 206,
      headers: {
        "Content-Range": `bytes ${start}-${end}/${fileSize}`,
        "Accept-Ranges": "bytes",
        "Content-Length": String(chunkSize),
        "Content-Type": contentType
      }
    })
  }

  // Full file response
  const nodeStream = fsSync.createReadStream(filePath)
  const webStream = new ReadableStream({
    start(controller) {
      nodeStream.on("data", (chunk) => controller.enqueue(chunk))
      nodeStream.on("end", () => controller.close())
      nodeStream.on("error", (err) => controller.error(err))
    },
    cancel() {
      nodeStream.destroy()
    }
  })

  return new Response(webStream, {
    status: 200,
    headers: {
      "Content-Length": String(fileSize),
      "Content-Type": contentType,
      "Accept-Ranges": "bytes"
    }
  })
}
