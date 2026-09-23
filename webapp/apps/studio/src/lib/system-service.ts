import { exec } from "node:child_process"
import { promisify } from "node:util"
import fsSync from "node:fs"
import path from "node:path"
import dotenv from "dotenv"
import { getProjectRoot } from "./test-service"

const execAsync = promisify(exec)

export interface SystemHealth {
  python: {
    available: boolean
    version?: string
    error?: string
  }
  ffmpeg: {
    available: boolean
    version?: string
    error?: string
  }
  playwright: {
    available: boolean
    error?: string
  }
  envVars: {
    geminiKeyConfigured: boolean
    geminiKeyCount: number
    nvidiaKeyConfigured: boolean
    fishAudioKeyConfigured: boolean
    youtubeOAuthConfigured: boolean
    youtubeRefreshTokenConfigured: boolean
  }
}

export async function checkSystemHealth(): Promise<SystemHealth> {
  const root = getProjectRoot()
  const envPath = path.join(root, ".env")
  let env: Record<string, string> = {}
  if (fsSync.existsSync(envPath)) {
    try {
      const parsed = dotenv.parse(fsSync.readFileSync(envPath))
      env = parsed
    } catch {
      // ignore
    }
  }

  // Check Python
  let pythonStatus: SystemHealth["python"] = { available: false }
  try {
    const { stdout } = await execAsync("python --version")
    pythonStatus = { available: true, version: stdout.trim() }
  } catch (err: any) {
    pythonStatus = { available: false, error: err?.message || "python command failed" }
  }

  // Check FFmpeg
  let ffmpegStatus: SystemHealth["ffmpeg"] = { available: false }
  try {
    const { stdout } = await execAsync("ffmpeg -version")
    const firstLine = stdout.split("\n")[0]?.trim() || "ffmpeg"
    ffmpegStatus = { available: true, version: firstLine }
  } catch (err: any) {
    ffmpegStatus = { available: false, error: err?.message || "ffmpeg not found on PATH" }
  }

  // Check Playwright
  let playwrightStatus: SystemHealth["playwright"] = { available: false }
  try {
    await execAsync("python -c \"import playwright\"")
    playwrightStatus = { available: true }
  } catch (err: any) {
    playwrightStatus = { available: false, error: err?.message || "playwright python package not installed" }
  }

  // Parse env vars
  const geminiRaw = env["GEMINI_API_KEYS"] || env["GEMINI_API_KEY"] || process.env["GEMINI_API_KEYS"] || process.env["GEMINI_API_KEY"] || ""
  const geminiKeys = geminiRaw ? geminiRaw.split(",").map((k) => k.trim()).filter(Boolean) : []
  const nvidiaKey = env["NVIDIA_API_KEY"] || process.env["NVIDIA_API_KEY"] || ""
  const fishKey = env["FISH_AUDIO"] || process.env["FISH_AUDIO"] || ""
  const ytClientId = env["YOUTUBE_CLIENT_ID"] || process.env["YOUTUBE_CLIENT_ID"] || ""
  const ytRefreshToken = env["YOUTUBE_REFRESH_TOKEN"] || process.env["YOUTUBE_REFRESH_TOKEN"] || ""

  return {
    python: pythonStatus,
    ffmpeg: ffmpegStatus,
    playwright: playwrightStatus,
    envVars: {
      geminiKeyConfigured: geminiKeys.length > 0,
      geminiKeyCount: geminiKeys.length,
      nvidiaKeyConfigured: Boolean(nvidiaKey && nvidiaKey.length > 5),
      fishAudioKeyConfigured: Boolean(fishKey && fishKey.length > 5),
      youtubeOAuthConfigured: Boolean(ytClientId && ytClientId.includes(".apps.googleusercontent.com")),
      youtubeRefreshTokenConfigured: Boolean(ytRefreshToken && ytRefreshToken.length > 10)
    }
  }
}
