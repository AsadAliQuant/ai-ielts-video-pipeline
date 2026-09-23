import fs from "node:fs/promises"
import fsSync from "node:fs"
import path from "node:path"
import os from "node:os"

export interface DownloadImage {
  name: string
  fullPath: string
  sizeBytes: number
  modifiedTime: string
  ageMinutes: number
}

export async function getRecentDownloads(maxAgeMinutes = 120): Promise<DownloadImage[]> {
  const downloadsDir = path.join(os.homedir(), "Downloads")
  if (!fsSync.existsSync(downloadsDir)) {
    return []
  }

  try {
    const entries = await fs.readdir(downloadsDir, { withFileTypes: true })
    const now = Date.now()
    const imageExtensions = new Set([".png", ".jpg", ".jpeg", ".webp"])

    const images: DownloadImage[] = []
    for (const entry of entries) {
      if (!entry.isFile()) continue
      const ext = path.extname(entry.name).toLowerCase()
      if (!imageExtensions.has(ext)) continue

      const fullPath = path.join(downloadsDir, entry.name)
      try {
        const stat = await fs.stat(fullPath)
        const ageMinutes = Math.round((now - stat.mtimeMs) / (60 * 1000))
        if (ageMinutes <= maxAgeMinutes) {
          images.push({
            name: entry.name,
            fullPath,
            sizeBytes: stat.size,
            modifiedTime: stat.mtime.toISOString(),
            ageMinutes
          })
        }
      } catch {
        // ignore file read error
      }
    }

    // Sort newest first
    images.sort((a, b) => a.ageMinutes - b.ageMinutes)
    return images.slice(0, 10)
  } catch (err) {
    console.error("Error scanning downloads directory:", err)
    return []
  }
}
