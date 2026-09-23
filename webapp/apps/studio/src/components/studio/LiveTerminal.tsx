import React, { useState, useEffect, useRef } from "react"
import { Button } from "@workspace/ui/components/button"
import { Badge } from "@workspace/ui/components/badge"
import { VisualPromptModal } from "./VisualPromptModal"
import {
  Terminal,
  Play,
  Square,
  Trash2,
  Copy,
  Check,
  CheckCircle2,
  Loader2,
  AlertCircle,
  ExternalLink,
  ChevronDown
} from "lucide-react"

interface LiveTerminalProps {
  initialJobId?: string
  onJobComplete?: (testId: string) => void
}

export function LiveTerminal({ initialJobId, onJobComplete }: LiveTerminalProps) {
  const [logs, setLogs] = useState<string[]>([])
  const [jobStatus, setJobStatus] = useState<any>(null)
  const [autoScroll, setAutoScroll] = useState(true)
  const [copied, setCopied] = useState(false)
  const [cancelling, setCancelling] = useState(false)
  const logContainerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const eventSource = new EventSource("/api/pipeline/logs")

    eventSource.addEventListener("initial_state", (e) => {
      try {
        const data = JSON.parse(e.data)
        if (data) {
          setJobStatus(data)
          if (data.logs && Array.isArray(data.logs)) {
            setLogs(data.logs)
          }
        }
      } catch {
        // ignore
      }
    })

    eventSource.addEventListener("log", (e) => {
      try {
        const data = JSON.parse(e.data)
        if (data && data.message) {
          setLogs((prev) => [...prev, data.message])
        }
      } catch {
        // ignore
      }
    })

    eventSource.addEventListener("status_change", (e) => {
      try {
        const data = JSON.parse(e.data)
        if (data) {
          setJobStatus((prev: any) => ({ ...prev, ...data }))
          if (data.status === "completed" && data.testId && onJobComplete) {
            onJobComplete(data.testId)
          }
        }
      } catch {
        // ignore
      }
    })

    return () => {
      eventSource.close()
    }
  }, [])

  // Auto scroll to bottom
  useEffect(() => {
    if (autoScroll && logContainerRef.current) {
      logContainerRef.current.scrollTop = logContainerRef.current.scrollHeight
    }
  }, [logs, autoScroll])

  const handleCopyLogs = () => {
    navigator.clipboard.writeText(logs.join("\n"))
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  const handleClearLogs = () => {
    setLogs([])
  }

  const handleCancelJob = async () => {
    if (!jobStatus?.id) return
    setCancelling(true)
    try {
      await fetch("/api/pipeline/cancel", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ jobId: jobStatus.id })
      })
    } catch {
      // ignore
    } finally {
      setCancelling(false)
    }
  }

  const stages = [
    { key: "stage1_paper", label: "1. Exam Paper" },
    { key: "awaiting_visual", label: "Visual Hook" },
    { key: "stage2_audio", label: "2. TTS Audio" },
    { key: "stage3_video", label: "3. 1080p Video" },
    { key: "stage4_upload", label: "4. YouTube" }
  ]

  const getStageStatus = (stageKey: string) => {
    if (!jobStatus) return "pending"
    if (jobStatus.status === "completed") return "completed"
    if (jobStatus.status === "failed") return "failed"
    if (jobStatus.currentStage === stageKey) return "active"

    const order = ["stage1_paper", "awaiting_visual", "stage2_audio", "stage3_video", "stage4_upload"]
    const currentIndex = order.indexOf(jobStatus.currentStage)
    const stageIndex = order.indexOf(stageKey)

    if (stageIndex < currentIndex) return "completed"
    return "pending"
  }

  return (
    <div className="space-y-4">
      {/* Pipeline Stepper */}
      <div className="p-4 bg-card border rounded-2xl shadow-sm">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <span className="font-semibold text-sm text-foreground">Pipeline Status:</span>
            {jobStatus ? (
              <Badge
                variant={
                  jobStatus.status === "completed"
                    ? "default"
                    : jobStatus.status === "failed" || jobStatus.status === "cancelled"
                    ? "destructive"
                    : "secondary"
                }
                className="capitalize rounded-lg px-2.5 py-0.5 text-xs font-semibold"
              >
                {jobStatus.status}
              </Badge>
            ) : (
              <Badge variant="outline" className="text-xs">Idle</Badge>
            )}
            {jobStatus?.testId && (
              <a
                href={`/tests/${jobStatus.testId}`}
                className="text-xs font-mono text-primary underline-offset-4 hover:underline flex items-center gap-1"
              >
                <span>{jobStatus.testId}</span>
                <ExternalLink className="w-3 h-3" />
              </a>
            )}
          </div>

          {jobStatus && (jobStatus.status === "running" || jobStatus.status === "awaiting_visual") && (
            <Button
              size="sm"
              variant="destructive"
              onClick={handleCancelJob}
              disabled={cancelling}
              className="h-7 text-xs gap-1.5 rounded-xl"
            >
              {cancelling ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Square className="w-3.5 h-3.5" />}
              <span>Cancel Job</span>
            </Button>
          )}
        </div>

        {/* Visual Progress Steps */}
        <div className="grid grid-cols-2 sm:grid-cols-5 gap-2 mt-4 pt-3 border-t">
          {stages.map((stage) => {
            const status = getStageStatus(stage.key)
            return (
              <div
                key={stage.key}
                className={`p-2 rounded-xl border text-xs transition-all ${
                  status === "active"
                    ? "border-primary bg-primary/10 font-semibold text-primary"
                    : status === "completed"
                    ? "border-green-500/30 bg-green-500/5 text-muted-foreground"
                    : "border-border/60 bg-muted/20 text-muted-foreground/60"
                }`}
              >
                <div className="flex items-center gap-1.5">
                  {status === "active" ? (
                    <Loader2 className="w-3.5 h-3.5 animate-spin text-primary shrink-0" />
                  ) : status === "completed" ? (
                    <CheckCircle2 className="w-3.5 h-3.5 text-green-500 shrink-0" />
                  ) : (
                    <div className="w-3.5 h-3.5 rounded-full border border-muted-foreground/40 shrink-0" />
                  )}
                  <span className="truncate">{stage.label}</span>
                </div>
              </div>
            )
          })}
        </div>
      </div>

      {/* Visual Hook Banner if Awaiting Visual */}
      {jobStatus && jobStatus.status === "awaiting_visual" && jobStatus.visualPrompt && (
        <VisualPromptModal
          visualInfo={jobStatus.visualPrompt}
          jobId={jobStatus.id}
          testId={jobStatus.testId}
          onResumed={() => {
            // will update via SSE
          }}
        />
      )}

      {/* Terminal Window */}
      <div className="rounded-2xl border bg-zinc-950 text-zinc-100 shadow-xl overflow-hidden">
        {/* Terminal Header */}
        <div className="flex items-center justify-between px-4 py-2.5 bg-zinc-900 border-b border-zinc-800 text-xs">
          <div className="flex items-center gap-2 text-zinc-400">
            <Terminal className="w-4 h-4 text-zinc-300" />
            <span className="font-mono">Live Execution Console</span>
            <span className="text-[10px] bg-zinc-800 text-zinc-400 px-2 py-0.5 rounded-md">
              {logs.length} lines
            </span>
          </div>

          <div className="flex items-center gap-1.5">
            <Button
              variant="ghost"
              size="icon-xs"
              onClick={() => setAutoScroll(!autoScroll)}
              title={autoScroll ? "Disable Auto-scroll" : "Enable Auto-scroll"}
              className={`h-6 px-2 text-[11px] text-zinc-400 hover:text-zinc-100 hover:bg-zinc-800 rounded-lg ${
                autoScroll ? "text-primary hover:text-primary" : ""
              }`}
            >
              Auto-scroll: {autoScroll ? "ON" : "OFF"}
            </Button>

            <Button
              variant="ghost"
              size="icon-xs"
              onClick={handleCopyLogs}
              title="Copy full logs"
              className="h-6 w-6 text-zinc-400 hover:text-zinc-100 hover:bg-zinc-800 rounded-lg"
            >
              {copied ? <Check className="w-3 h-3 text-green-400" /> : <Copy className="w-3 h-3" />}
            </Button>

            <Button
              variant="ghost"
              size="icon-xs"
              onClick={handleClearLogs}
              title="Clear Console"
              className="h-6 w-6 text-zinc-400 hover:text-zinc-100 hover:bg-zinc-800 rounded-lg"
            >
              <Trash2 className="w-3 h-3" />
            </Button>
          </div>
        </div>

        {/* Terminal Body */}
        <div
          ref={logContainerRef}
          className="p-4 font-mono text-xs leading-relaxed overflow-y-auto max-h-[500px] min-h-[260px] space-y-0.5 select-text"
        >
          {logs.length === 0 ? (
            <div className="h-48 flex flex-col items-center justify-center text-zinc-600 space-y-2">
              <Terminal className="w-8 h-8 opacity-40" />
              <p>No active process output. Start a new pipeline run above.</p>
            </div>
          ) : (
            logs.map((line, idx) => {
              let colorClass = "text-zinc-300"
              if (line.startsWith("[EXEC]")) colorClass = "text-cyan-400 font-bold"
              else if (line.startsWith("[OK]") || line.startsWith("[SUCCESS]")) colorClass = "text-green-400 font-semibold"
              else if (line.startsWith("[FAIL]") || line.startsWith("[ERROR]") || line.includes("failed")) colorClass = "text-red-400 font-bold"
              else if (line.startsWith("[STDERR]")) colorClass = "text-amber-400/90"
              else if (line.startsWith(">>>") || line.startsWith("===") || line.startsWith("###")) colorClass = "text-primary-foreground/90 font-bold"
              else if (line.includes("https://youtu.be/")) colorClass = "text-yellow-300 font-bold underline"

              return (
                <div key={idx} className={`whitespace-pre-wrap break-all ${colorClass}`}>
                  {line}
                </div>
              )
            })
          )}
        </div>
      </div>
    </div>
  )
}
