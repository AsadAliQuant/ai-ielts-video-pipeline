import fs from "node:fs/promises"
import fsSync from "node:fs"
import path from "node:path"

export interface TestSummary {
  id: string
  num: number
  path: string
  band: string
  context: string
  title: string
  partTopics: Record<string, string>
  createdAt: string
  hasTestJson: boolean
  hasStudentPaper: boolean
  hasTranscript: boolean
  hasAnswerKey: boolean
  hasVisualPrompt: boolean
  hasVisualImage: boolean
  visualInfo?: {
    id: string
    title: string
    type: string
    prompt: string
  } | null
  hasAudio: boolean
  audioDurationSec?: number
  hasVideo: boolean
  videoSizeMB?: number
  hasThumbnail: boolean
  hasChapters: boolean
  hasYoutubeDescription: boolean
  youtubeId?: string | null
  status: {
    stage1: "completed" | "missing"
    visual: "completed" | "required" | "none"
    stage2: "completed" | "missing"
    stage3: "completed" | "missing"
    stage4: "completed" | "ready" | "pending"
  }
}

export function getProjectRoot(): string {
  let cur = process.cwd()
  while (cur && path.dirname(cur) !== cur) {
    if (fsSync.existsSync(path.join(cur, "tests")) && fsSync.existsSync(path.join(cur, "generate_test.py"))) {
      return cur
    }
    cur = path.dirname(cur)
  }
  return path.resolve(process.cwd(), "..", "..", "..")
}

export function getTestsDir(): string {
  return path.join(getProjectRoot(), "tests")
}

export async function listAllTests(): Promise<TestSummary[]> {
  const testsDir = getTestsDir()
  try {
    const entries = await fs.readdir(testsDir, { withFileTypes: true })
    const testDirs = entries
      .filter((e) => e.isDirectory() && /^test_\d+$/.test(e.name))
      .map((e) => e.name)
      .sort((a, b) => {
        const numA = parseInt(a.replace("test_", ""), 10)
        const numB = parseInt(b.replace("test_", ""), 10)
        return numB - numA // newest first
      })

    const summaries: TestSummary[] = []
    for (const dirName of testDirs) {
      const summary = await getTestSummary(dirName)
      if (summary) summaries.push(summary)
    }
    return summaries
  } catch (err) {
    console.error("Error reading tests directory:", err)
    return []
  }
}

export async function getTestSummary(testId: string): Promise<TestSummary | null> {
  const testDir = path.join(getTestsDir(), testId)
  if (!fsSync.existsSync(testDir)) return null

  const num = parseInt(testId.replace("test_", ""), 10) || 0
  let band = "9.0"
  let context = "academic"
  let title = `IELTS Practice Test ${testId}`
  const partTopics: Record<string, string> = {}

  const testJsonPath = path.join(testDir, "test.json")
  const hasTestJson = fsSync.existsSync(testJsonPath)
  if (hasTestJson) {
    try {
      const raw = await fs.readFile(testJsonPath, "utf-8")
      const data = JSON.parse(raw)
      band = String(data.target_band || data.band || "9.0")
      context = data.context || "academic"
      title = data.title || title
      if (data.parts && Array.isArray(data.parts)) {
        data.parts.forEach((p: any, idx: number) => {
          partTopics[String(idx + 1)] = p.topic || p.title || `Part ${idx + 1}`
        })
      }
    } catch {
      // ignore json parse error
    }
  }

  const stat = await fs.stat(testDir)
  const createdAt = stat.birthtime ? stat.birthtime.toISOString() : stat.mtime.toISOString()

  const hasStudentPaper = fsSync.existsSync(path.join(testDir, "student_paper.md"))
  const hasTranscript = fsSync.existsSync(path.join(testDir, "transcript.txt"))
  const hasAnswerKey = fsSync.existsSync(path.join(testDir, "answer_key.md"))
  
  // Visuals check
  const visualsMdPath = path.join(testDir, "visuals.md")
  const hasVisualPrompt = fsSync.existsSync(visualsMdPath)
  let visualInfo: TestSummary["visualInfo"] = null

  if (hasVisualPrompt) {
    try {
      const vContent = await fs.readFile(visualsMdPath, "utf-8")
      const titleMatch = vContent.match(/\*\*Title:\*\*\s*(.+)/)
      const typeMatch = vContent.match(/\*\*Type:\*\*\s*(.+)/)
      const promptMatch = vContent.match(/\*\*GenAI image prompt\*\*\s*\n\n([\s\S]*?)(?=\n\n\*\*|\Z)/)
      const idMatch = vContent.match(/\b(v\d+)\b/)

      const typeStr = typeMatch ? typeMatch[1].trim() : "image"
      if (!["flowchart", "table"].includes(typeStr.toLowerCase()) && promptMatch) {
        visualInfo = {
          id: idMatch ? idMatch[1] : "v1",
          title: titleMatch ? titleMatch[1].trim() : "Diagram",
          type: typeStr,
          prompt: promptMatch[1].trim()
        }
      }
    } catch {
      // ignore
    }
  }

  const hasVisualImage =
    fsSync.existsSync(path.join(testDir, "visuals", "v1.png")) ||
    fsSync.existsSync(path.join(testDir, "visual_v1.png"))

  // Audio check
  const fullAudioPath = path.join(testDir, "audio", "full_test.wav")
  const hasAudio = fsSync.existsSync(fullAudioPath)
  let audioDurationSec: number | undefined
  if (hasAudio) {
    try {
      const aStat = await fs.stat(fullAudioPath)
      // Fish Audio streaming WAV duration: (size - 44) / (44100 * 2 * 2) approx
      audioDurationSec = Math.round((aStat.size - 44) / (44100 * 2 * 2))
    } catch {
      // ignore
    }
  }

  // Video check
  const videoPath = path.join(testDir, "video", `${testId}.mp4`)
  const hasVideo = fsSync.existsSync(videoPath)
  let videoSizeMB: number | undefined
  if (hasVideo) {
    try {
      const vStat = await fs.stat(videoPath)
      videoSizeMB = Math.round((vStat.size / (1024 * 1024)) * 10) / 10
    } catch {
      // ignore
    }
  }

  const hasThumbnail =
    fsSync.existsSync(path.join(testDir, "video", "thumbnail.png")) ||
    fsSync.existsSync(path.join(testDir, "thumbnail.png"))

  const hasChapters = fsSync.existsSync(path.join(testDir, "video", "chapters.txt"))
  const hasYoutubeDescription = fsSync.existsSync(
    path.join(testDir, "video", "youtube_description.txt")
  )

  // Check youtube id record
  let youtubeId: string | null = null
  const ytRecordPath = path.join(testDir, "youtube_id.txt")
  if (fsSync.existsSync(ytRecordPath)) {
    try {
      youtubeId = (await fs.readFile(ytRecordPath, "utf-8")).trim()
    } catch {
      // ignore
    }
  }

  // Calculate status
  const stage1 = hasTestJson ? "completed" : "missing"
  const visual = visualInfo
    ? hasVisualImage
      ? "completed"
      : "required"
    : "none"
  const stage2 = hasAudio ? "completed" : "missing"
  const stage3 = hasVideo ? "completed" : "missing"
  const stage4 = youtubeId
    ? "completed"
    : hasVideo
    ? "ready"
    : "pending"

  return {
    id: testId,
    num,
    path: testDir,
    band,
    context,
    title,
    partTopics,
    createdAt,
    hasTestJson,
    hasStudentPaper,
    hasTranscript,
    hasAnswerKey,
    hasVisualPrompt,
    hasVisualImage,
    visualInfo,
    hasAudio,
    audioDurationSec,
    hasVideo,
    videoSizeMB,
    hasThumbnail,
    hasChapters,
    hasYoutubeDescription,
    youtubeId,
    status: {
      stage1,
      visual,
      stage2,
      stage3,
      stage4
    }
  }
}

export async function getTestFullDetails(testId: string) {
  const summary = await getTestSummary(testId)
  if (!summary) return null

  const testDir = summary.path
  const files: Record<string, string> = {}

  const filesToRead = [
    { key: "studentPaper", file: "student_paper.md" },
    { key: "transcript", file: "transcript.txt" },
    { key: "answerKey", file: "answer_key.md" },
    { key: "visualsMd", file: "visuals.md" },
    { key: "chapters", file: path.join("video", "chapters.txt") },
    { key: "youtubeDescription", file: path.join("video", "youtube_description.txt") }
  ]

  for (const item of filesToRead) {
    const p = path.join(testDir, item.file)
    if (fsSync.existsSync(p)) {
      try {
        files[item.key] = await fs.readFile(p, "utf-8")
      } catch {
        files[item.key] = ""
      }
    }
  }

  let testJson = null
  const testJsonPath = path.join(testDir, "test.json")
  if (fsSync.existsSync(testJsonPath)) {
    try {
      testJson = JSON.parse(await fs.readFile(testJsonPath, "utf-8"))
    } catch {
      // ignore
    }
  }

  // Audio files list
  const audioDir = path.join(testDir, "audio")
  const audioFiles: string[] = []
  if (fsSync.existsSync(audioDir)) {
    try {
      const aEntries = await fs.readdir(audioDir)
      audioFiles.push(...aEntries.filter((f) => f.endsWith(".wav") || f.endsWith(".mp3")))
    } catch {
      // ignore
    }
  }

  // Video screens list
  const screensDir = path.join(testDir, "video", "screens")
  const screens: string[] = []
  if (fsSync.existsSync(screensDir)) {
    try {
      const sEntries = await fs.readdir(screensDir)
      screens.push(...sEntries.filter((f) => f.endsWith(".png")).sort())
    } catch {
      // ignore
    }
  }

  return {
    summary,
    testJson,
    files,
    audioFiles,
    screens
  }
}
