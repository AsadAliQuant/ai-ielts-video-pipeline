import { spawn, type ChildProcess, exec } from "node:child_process"
import { EventEmitter } from "node:events"
import path from "node:path"
import fsSync from "node:fs"
import fs from "node:fs/promises"
import { getProjectRoot, getTestsDir, getTestSummary, type TestSummary } from "./test-service"

export type JobStage = "stage1_paper" | "awaiting_visual" | "stage2_audio" | "stage3_video" | "stage4_upload" | "idle"
export type JobStatus = "running" | "awaiting_visual" | "completed" | "failed" | "cancelled"

export interface PipelineConfig {
  band?: string
  difficulty?: string
  context?: "academic" | "general"
  topics?: string
  provider?: "gemini" | "nvidia"
  model?: string
  geminiModel?: string
  skipVerify?: boolean
  fast?: boolean
  autoUpload?: boolean
  dryRun?: boolean
  targetStage?: number // 1, 2, 3, 4
  existingTestId?: string
  customTitle?: string
}

export interface PipelineJob {
  id: string
  config: PipelineConfig
  status: JobStatus
  currentStage: JobStage
  testId?: string
  startTime: number
  endTime?: number
  logs: string[]
  error?: string
  visualPrompt?: {
    id: string
    title: string
    type: string
    prompt: string
    targetPath: string
  } | null
}

class JobManager extends EventEmitter {
  private activeJob: PipelineJob | null = null
  private childProcess: ChildProcess | null = null

  getActiveJob(): PipelineJob | null {
    return this.activeJob
  }

  getJob(id: string): PipelineJob | null {
    if (this.activeJob && this.activeJob.id === id) {
      return this.activeJob
    }
    return null
  }

  private appendLog(message: string) {
    if (!this.activeJob) return
    this.activeJob.logs.push(message)
    this.emit("log", { jobId: this.activeJob.id, message })
  }

  private updateStage(stage: JobStage, status?: JobStatus) {
    if (!this.activeJob) return
    this.activeJob.currentStage = stage
    if (status) this.activeJob.status = status
    this.emit("status_change", {
      jobId: this.activeJob.id,
      stage,
      status: this.activeJob.status,
      testId: this.activeJob.testId,
      visualPrompt: this.activeJob.visualPrompt
    })
  }

  async startJob(config: PipelineConfig): Promise<PipelineJob> {
    if (this.activeJob && (this.activeJob.status === "running" || this.activeJob.status === "awaiting_visual")) {
      throw new Error("A job is already currently running or awaiting visual.")
    }

    const jobId = `job_${Date.now()}`
    this.activeJob = {
      id: jobId,
      config,
      status: "running",
      currentStage: "stage1_paper",
      startTime: Date.now(),
      logs: [],
      visualPrompt: null
    }

    this.emit("job_started", this.activeJob)

    // Execute pipeline asynchronously
    this.executePipeline().catch((err) => {
      if (this.activeJob && this.activeJob.id === jobId) {
        this.appendLog(`[ERROR] Job failed: ${err.message}`)
        this.activeJob.status = "failed"
        this.activeJob.error = err.message
        this.activeJob.endTime = Date.now()
        this.emit("status_change", this.activeJob)
      }
    })

    return this.activeJob
  }

  private async executePipeline() {
    const job = this.activeJob
    if (!job) return

    const root = getProjectRoot()
    const testsDir = getTestsDir()
    const targetStage = job.config.targetStage ?? 4

    // If target is an existing test
    if (job.config.existingTestId) {
      job.testId = job.config.existingTestId
      const testDir = path.join(testsDir, job.testId)

      // Run specific stage requested
      if (targetStage === 2) {
        await this.runStage2(testDir)
      } else if (targetStage === 3) {
        await this.runStage3(testDir, job.config.fast ?? true)
      } else if (targetStage === 4) {
        await this.runStage4(testDir, job.config.customTitle)
      } else {
        // Run full from current state
        await this.runStage2(testDir)
        await this.runStage3(testDir, job.config.fast ?? true)
        if (job.config.autoUpload) {
          await this.runStage4(testDir, job.config.customTitle)
        }
      }

      job.status = "completed"
      job.endTime = Date.now()
      this.updateStage("idle", "completed")
      return
    }

    // New test execution flow
    this.appendLog(`=======================================================`)
    this.appendLog(` IELTS Listening Test Pipeline Generator Started`)
    this.appendLog(` Target Band : ${job.config.band || "9.0"}`)
    this.appendLog(` Provider    : ${job.config.provider || "gemini"}`)
    this.appendLog(` Fast Mode   : ${job.config.skipVerify ? "Yes (Skip Verifier)" : "No (Full Verifier)"}`)
    this.appendLog(`=======================================================`)

    // Get directories before Stage 1 to detect the new test folder
    const dirsBefore = new Set(
      (await fs.readdir(testsDir, { withFileTypes: true }))
        .filter((d) => d.isDirectory() && /^test_\d+$/.test(d.name))
        .map((d) => d.name)
    )

    // Stage 1: generate_test.py
    this.updateStage("stage1_paper", "running")
    this.appendLog(`\n>>> STAGE 1: Generating IELTS Exam Paper...`)

    const stage1Args = [
      "-u",
      "generate_test.py",
      "--band", job.config.band || "9.0",
      "--provider", job.config.provider || "gemini"
    ]
    if (job.config.difficulty) stage1Args.push("--difficulty", job.config.difficulty)
    if (job.config.context) stage1Args.push("--context", job.config.context)
    if (job.config.topics) stage1Args.push("--topics", job.config.topics)
    if (job.config.model) stage1Args.push("--model", job.config.model)
    if (job.config.geminiModel) stage1Args.push("--gemini-model", job.config.geminiModel)
    if (job.config.skipVerify) stage1Args.push("--skip-verify")

    if (job.config.dryRun) {
      this.appendLog(`[DRY RUN] Would execute: python ${stage1Args.join(" ")}`)
      job.status = "completed"
      job.endTime = Date.now()
      this.updateStage("idle", "completed")
      return
    }

    await this.spawnProcess("python", stage1Args, root)

    // Detect created test directory
    const dirsAfter = (await fs.readdir(testsDir, { withFileTypes: true }))
      .filter((d) => d.isDirectory() && /^test_\d+$/.test(d.name))
      .map((d) => d.name)

    const newDirs = dirsAfter.filter((d) => !dirsBefore.has(d))
    let testId: string
    if (newDirs.length > 0) {
      testId = newDirs[0]
    } else {
      // Find highest index
      testId = dirsAfter.sort((a, b) => {
        return parseInt(b.replace("test_", ""), 10) - parseInt(a.replace("test_", ""), 10)
      })[0]
    }

    job.testId = testId
    const testDir = path.join(testsDir, testId)
    this.appendLog(`[OK] Exam paper created at: ${testDir}`)

    if (targetStage === 1) {
      job.status = "completed"
      job.endTime = Date.now()
      this.updateStage("idle", "completed")
      return
    }

    // Check visuals.md for image requirement
    const visualsMdPath = path.join(testDir, "visuals.md")
    let visualPrompt: PipelineJob["visualPrompt"] = null

    if (fsSync.existsSync(visualsMdPath)) {
      const vContent = await fs.readFile(visualsMdPath, "utf-8")
      const titleMatch = vContent.match(/\*\*Title:\*\*\s*(.+)/)
      const typeMatch = vContent.match(/\*\*Type:\*\*\s*(.+)/)
      const promptMatch = vContent.match(/\*\*GenAI image prompt\*\*\s*\n\n([\s\S]*?)(?=\n\n\*\*|\Z)/)
      const idMatch = vContent.match(/\b(v\d+)\b/)

      const typeStr = typeMatch ? typeMatch[1].trim() : "image"
      if (!["flowchart", "table"].includes(typeStr.toLowerCase()) && promptMatch) {
        const vid = idMatch ? idMatch[1] : "v1"
        visualPrompt = {
          id: vid,
          title: titleMatch ? titleMatch[1].trim() : "Diagram",
          type: typeStr,
          prompt: promptMatch[1].trim(),
          targetPath: path.join(testDir, "visuals", `${vid}.png`)
        }
      }
    }

    const hasVisualImage =
      fsSync.existsSync(path.join(testDir, "visuals", "v1.png")) ||
      fsSync.existsSync(path.join(testDir, "visual_v1.png"))

    if (visualPrompt && !hasVisualImage) {
      job.visualPrompt = visualPrompt
      this.appendLog(`\n[VISUAL REQUIRED] ${visualPrompt.title} (${visualPrompt.type})`)
      this.appendLog(`Awaiting visual image upload/confirmation in WebUI...`)
      this.updateStage("awaiting_visual", "awaiting_visual")
      return // Paused! Waiting for resumeJobWithVisual()
    }

    // Continue to audio & video
    await this.continueAfterVisual(testDir)
  }

  async resumeJobWithVisual(jobId: string, imagePathOrBuffer?: string | Buffer) {
    if (!this.activeJob || this.activeJob.id !== jobId) {
      throw new Error(`Job ${jobId} is not active.`)
    }
    if (this.activeJob.status !== "awaiting_visual") {
      throw new Error(`Job ${jobId} is not awaiting a visual.`)
    }

    const testId = this.activeJob.testId
    if (!testId) throw new Error("No testId associated with this job.")

    const testDir = path.join(getTestsDir(), testId)
    const visualsDir = path.join(testDir, "visuals")
    await fs.mkdir(visualsDir, { recursive: true })

    const targetV1 = path.join(visualsDir, "v1.png")
    const targetRoot = path.join(testDir, "visual_v1.png")

    if (typeof imagePathOrBuffer === "string") {
      // It's a file path (e.g. from Downloads)
      if (fsSync.existsSync(imagePathOrBuffer)) {
        await fs.copyFile(imagePathOrBuffer, targetV1)
        await fs.copyFile(imagePathOrBuffer, targetRoot)
        this.appendLog(`[OK] Imported image from ${imagePathOrBuffer} -> ${targetV1}`)
      }
    } else if (Buffer.isBuffer(imagePathOrBuffer)) {
      // It's uploaded buffer
      await fs.writeFile(targetV1, imagePathOrBuffer)
      await fs.writeFile(targetRoot, imagePathOrBuffer)
      this.appendLog(`[OK] Saved uploaded visual -> ${targetV1}`)
    }

    this.activeJob.visualPrompt = null
    this.appendLog(`[RESUMING] Visual image confirmed! Continuing pipeline...`)

    // Resume remaining stages
    this.continueAfterVisual(testDir).catch((err) => {
      if (this.activeJob) {
        this.appendLog(`[ERROR] Resumed job failed: ${err.message}`)
        this.activeJob.status = "failed"
        this.activeJob.error = err.message
        this.activeJob.endTime = Date.now()
        this.emit("status_change", this.activeJob)
      }
    })
  }

  private async continueAfterVisual(testDir: string) {
    const job = this.activeJob
    if (!job) return

    const targetStage = job.config.targetStage ?? 4

    // Stage 2: generate_audio.py
    if (targetStage >= 2) {
      await this.runStage2(testDir)
    }

    // Stage 3: generate_video.py
    if (targetStage >= 3) {
      await this.runStage3(testDir, job.config.fast ?? true)
    }

    // Stage 4: youtube_upload.py
    if (targetStage >= 4 && job.config.autoUpload) {
      await this.runStage4(testDir, job.config.customTitle)
    }

    job.status = "completed"
    job.endTime = Date.now()
    this.appendLog(`\n[SUCCESS] Pipeline execution finished successfully for ${path.basename(testDir)}!`)
    this.updateStage("idle", "completed")
  }

  private async runStage2(testDir: string) {
    this.updateStage("stage2_audio", "running")
    this.appendLog(`\n>>> STAGE 2: Synthesizing TTS Audio with Fish Audio (${path.basename(testDir)})...`)
    await this.spawnProcess("python", ["generate_audio.py", testDir], getProjectRoot())
    this.appendLog(`[OK] Audio synthesis complete.`)
  }

  private async runStage3(testDir: string, fast = true) {
    this.updateStage("stage3_video", "running")
    this.appendLog(`\n>>> STAGE 3: Rendering 1080p Video & HUD Timers (${path.basename(testDir)})...`)
    const args = ["generate_video.py", testDir]
    if (fast) args.push("--fast")
    await this.spawnProcess("python", args, getProjectRoot())
    this.appendLog(`[OK] Video rendering and chapters complete.`)
  }

  async runStage4(testDir: string, customTitle?: string) {
    this.updateStage("stage4_upload", "running")
    this.appendLog(`\n>>> STAGE 4: Uploading to YouTube (${path.basename(testDir)})...`)
    const args = ["youtube_upload.py", testDir]
    if (customTitle) args.push("--title", customTitle)
    await this.spawnProcess("python", args, getProjectRoot())
    this.appendLog(`[OK] Video uploaded to YouTube.`)
  }

  private spawnProcess(command: string, args: string[], cwd: string): Promise<number> {
    return new Promise((resolve, reject) => {
      this.appendLog(`[EXEC] ${command} ${args.join(" ")}`)
      const child = spawn(command, args, {
        cwd,
        env: { ...process.env, PYTHONUNBUFFERED: "1" }
      })

      this.childProcess = child

      child.stdout.on("data", (data: Buffer) => {
        const text = data.toString("utf-8")
        const lines = text.split(/\r?\n/)
        for (const line of lines) {
          if (line.trim()) {
            this.appendLog(line)
            // Check for youtube link
            if (line.includes("https://youtu.be/")) {
              const m = line.match(/https:\/\/youtu\.be\/([a-zA-Z0-9_-]+)/)
              if (m && this.activeJob?.testId) {
                const ytId = m[1]
                const recordPath = path.join(getTestsDir(), this.activeJob.testId, "youtube_id.txt")
                fsSync.writeFileSync(recordPath, ytId, "utf-8")
              }
            }
          }
        }
      })

      child.stderr.on("data", (data: Buffer) => {
        const text = data.toString("utf-8")
        const lines = text.split(/\r?\n/)
        for (const line of lines) {
          if (line.trim()) {
            this.appendLog(`[STDERR] ${line}`)
          }
        }
      })

      child.on("close", (code) => {
        this.childProcess = null
        if (code === 0) {
          resolve(0)
        } else {
          reject(new Error(`Command exited with error code ${code}`))
        }
      })

      child.on("error", (err) => {
        this.childProcess = null
        reject(err)
      })
    })
  }

  async cancelJob(jobId: string): Promise<boolean> {
    if (!this.activeJob || this.activeJob.id !== jobId) {
      return false
    }

    if (this.childProcess && this.childProcess.pid) {
      // Kill process tree on Windows
      const pid = this.childProcess.pid
      try {
        exec(`taskkill /pid ${pid} /T /F`)
      } catch {
        this.childProcess.kill("SIGTERM")
      }
      this.childProcess = null
    }

    this.activeJob.status = "cancelled"
    this.activeJob.endTime = Date.now()
    this.appendLog(`[CANCELLED] Job was cancelled by user.`)
    this.updateStage("idle", "cancelled")
    return true
  }
}

// Export singleton instance across requests
export const jobManager = new JobManager()
