import React, { useState } from "react"
import { Button } from "@workspace/ui/components/button"
import { Badge } from "@workspace/ui/components/badge"
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@workspace/ui/components/card"
import { Input } from "@workspace/ui/components/input"
import { VisualPromptModal } from "./VisualPromptModal"
import {
  FileText,
  Music,
  Video,
  Sparkles,
  ExternalLink,
  Play,
  RotateCw,
  CheckCircle2,
  AlertCircle,
  Copy,
  Check,
  Clock,
  Send,
  Loader2
} from "lucide-react"
import { YoutubeIcon } from "./YoutubeIcon"

interface TestInspectorProps {
  testId: string
  data: any
}

export function TestInspector({ testId, data }: TestInspectorProps) {
  const [activeTab, setActiveTab] = useState<"overview" | "audio" | "video" | "visual" | "youtube">("overview")
  const { summary, testJson, files, audioFiles, screens } = data

  // YouTube publishing state
  const [ytTitle, setYtTitle] = useState(
    `IELTS LISTENING PRACTICE TEST 2026 WITH ANSWERS | ${new Date().toLocaleDateString("en-GB").replace(/\//g, ".")}`
  )
  const [ytDescription, setYtDescription] = useState(files.youtubeDescription || "")
  const [publishing, setPublishing] = useState(false)
  const [publishResult, setPublishResult] = useState<{ success?: boolean; ytId?: string; error?: string } | null>(null)

  // Stage re-running
  const [runningStage, setRunningStage] = useState<number | null>(null)
  const [copiedTranscript, setCopiedTranscript] = useState(false)

  const handlePublishYouTube = async () => {
    setPublishing(true)
    setPublishResult(null)
    try {
      const res = await fetch(`/api/tests/${testId}/publish`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title: ytTitle })
      })
      const result = await res.json()
      if (!res.ok) throw new Error(result.error || "Publish failed")
      setPublishResult({ success: true, ytId: result.jobId })
    } catch (err: any) {
      setPublishResult({ error: err.message })
    } finally {
      setPublishing(false)
    }
  }

  const handleRunStage = async (stageNum: number) => {
    setRunningStage(stageNum)
    try {
      const res = await fetch(`/api/tests/${testId}/stage`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ stage: stageNum, fast: true })
      })
      if (res.ok) {
        window.location.href = "/pipeline"
      }
    } catch {
      // ignore
    } finally {
      setRunningStage(null)
    }
  }

  return (
    <div className="space-y-6">
      {/* Test Title Header */}
      <div className="flex flex-wrap items-center justify-between gap-4 p-5 bg-card border rounded-2xl shadow-sm">
        <div>
          <div className="flex items-center gap-2.5">
            <span className="font-mono font-extrabold text-xl text-foreground">{testId}</span>
            <Badge className="text-xs font-semibold px-2.5 py-0.5 rounded-md">
              Band {summary.band}
            </Badge>
            <Badge variant="outline" className="text-xs capitalize">
              {summary.context} Context
            </Badge>
          </div>
          <p className="text-xs text-muted-foreground mt-1">{summary.title}</p>
        </div>

        {/* Quick action badges / links */}
        <div className="flex items-center gap-2">
          {summary.youtubeId ? (
            <a
              href={`https://youtu.be/${summary.youtubeId}`}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1.5 text-xs font-semibold text-red-600 dark:text-red-400 bg-red-500/10 border border-red-500/20 px-3 py-1.5 rounded-xl hover:bg-red-500/20 transition-colors"
            >
              <YoutubeIcon className="w-4 h-4" />
              <span>Watch on YouTube</span>
              <ExternalLink className="w-3 h-3" />
            </a>
          ) : summary.hasVideo ? (
            <Button
              size="sm"
              onClick={() => setActiveTab("youtube")}
              className="gap-1.5 rounded-xl text-xs bg-red-600 hover:bg-red-700 text-white font-medium"
            >
              <YoutubeIcon className="w-4 h-4" />
              <span>Publish to YouTube</span>
            </Button>
          ) : null}

          <a href="/pipeline">
            <Button size="sm" variant="outline" className="text-xs rounded-xl">
              Live Console
            </Button>
          </a>
        </div>
      </div>

      {/* Tabs Navigation */}
      <div className="flex border-b gap-2 text-sm font-medium overflow-x-auto pb-1">
        <button
          onClick={() => setActiveTab("overview")}
          className={`px-4 py-2 rounded-xl flex items-center gap-2 transition-all ${
            activeTab === "overview"
              ? "bg-primary text-primary-foreground font-semibold shadow-sm shadow-primary/20"
              : "text-muted-foreground hover:bg-muted"
          }`}
        >
          <FileText className="w-4 h-4" />
          <span>Paper & Questions</span>
        </button>

        <button
          onClick={() => setActiveTab("audio")}
          className={`px-4 py-2 rounded-xl flex items-center gap-2 transition-all ${
            activeTab === "audio"
              ? "bg-primary text-primary-foreground font-semibold shadow-sm shadow-primary/20"
              : "text-muted-foreground hover:bg-muted"
          }`}
        >
          <Music className="w-4 h-4" />
          <span>Audio Player ({audioFiles.length} files)</span>
        </button>

        <button
          onClick={() => setActiveTab("video")}
          className={`px-4 py-2 rounded-xl flex items-center gap-2 transition-all ${
            activeTab === "video"
              ? "bg-primary text-primary-foreground font-semibold shadow-sm shadow-primary/20"
              : "text-muted-foreground hover:bg-muted"
          }`}
        >
          <Video className="w-4 h-4" />
          <span>Video & Screens</span>
        </button>

        <button
          onClick={() => setActiveTab("visual")}
          className={`px-4 py-2 rounded-xl flex items-center gap-2 transition-all ${
            activeTab === "visual"
              ? "bg-primary text-primary-foreground font-semibold shadow-sm shadow-primary/20"
              : "text-muted-foreground hover:bg-muted"
          }`}
        >
          <Sparkles className="w-4 h-4 text-amber-500" />
          <span>Visual Diagram</span>
        </button>

        <button
          onClick={() => setActiveTab("youtube")}
          className={`px-4 py-2 rounded-xl flex items-center gap-2 transition-all ${
            activeTab === "youtube"
              ? "bg-primary text-primary-foreground font-semibold shadow-sm shadow-primary/20"
              : "text-muted-foreground hover:bg-muted"
          }`}
        >
          <YoutubeIcon className="w-4 h-4 text-red-500" />
          <span>YouTube Publisher</span>
        </button>
      </div>

      {/* Tab 1: Overview & Questions */}
      {activeTab === "overview" && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Student Paper */}
          <Card className="rounded-2xl border">
            <CardHeader className="pb-3 border-b">
              <CardTitle className="text-base font-bold flex items-center gap-2">
                <FileText className="w-4 h-4 text-primary" />
                <span>Student Exam Paper</span>
              </CardTitle>
              <CardDescription className="text-xs">
                Questions as formatted for students (4 parts, 40 questions)
              </CardDescription>
            </CardHeader>
            <CardContent className="p-4 max-h-[600px] overflow-y-auto font-mono text-xs leading-relaxed whitespace-pre-wrap">
              {files.studentPaper || "No student paper found"}
            </CardContent>
          </Card>

          {/* Transcript & Answer Key */}
          <div className="space-y-6">
            <Card className="rounded-2xl border">
              <CardHeader className="pb-3 border-b flex flex-row items-center justify-between">
                <div>
                  <CardTitle className="text-base font-bold flex items-center gap-2">
                    <CheckCircle2 className="w-4 h-4 text-green-500" />
                    <span>Answer Key</span>
                  </CardTitle>
                  <CardDescription className="text-xs">
                    Official solutions and acceptable variants
                  </CardDescription>
                </div>
              </CardHeader>
              <CardContent className="p-4 max-h-[260px] overflow-y-auto font-mono text-xs leading-relaxed whitespace-pre-wrap">
                {files.answerKey || "No answer key found"}
              </CardContent>
            </Card>

            <Card className="rounded-2xl border">
              <CardHeader className="pb-3 border-b flex flex-row items-center justify-between">
                <div>
                  <CardTitle className="text-base font-bold">Audio Transcript</CardTitle>
                  <CardDescription className="text-xs">Full spoken dialogue with midbreak cues</CardDescription>
                </div>
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => {
                    navigator.clipboard.writeText(files.transcript || "")
                    setCopiedTranscript(true)
                    setTimeout(() => setCopiedTranscript(false), 2000)
                  }}
                  className="h-7 text-xs gap-1"
                >
                  {copiedTranscript ? <Check className="w-3 h-3 text-green-500" /> : <Copy className="w-3 h-3" />}
                  <span>{copiedTranscript ? "Copied" : "Copy"}</span>
                </Button>
              </CardHeader>
              <CardContent className="p-4 max-h-[260px] overflow-y-auto font-mono text-xs leading-relaxed whitespace-pre-wrap text-muted-foreground">
                {files.transcript || "No transcript found"}
              </CardContent>
            </Card>
          </div>
        </div>
      )}

      {/* Tab 2: Audio Player */}
      {activeTab === "audio" && (
        <Card className="rounded-2xl border p-6 space-y-6">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="font-bold text-lg flex items-center gap-2">
                <Music className="w-5 h-5 text-primary" />
                <span>Synthesized IELTS Audio</span>
              </h3>
              <p className="text-xs text-muted-foreground">
                Fish Audio TTS with official timing pauses (30s prep, 15s mid-break, 60s checking)
              </p>
            </div>

            <Button
              variant="outline"
              size="sm"
              disabled={runningStage === 2}
              onClick={() => handleRunStage(2)}
              className="gap-1.5 rounded-xl text-xs"
            >
              {runningStage === 2 ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <RotateCw className="w-3.5 h-3.5" />}
              <span>Re-synthesize Audio (Stage 2)</span>
            </Button>
          </div>

          {summary.hasAudio ? (
            <div className="space-y-4 p-4 rounded-xl bg-muted/30 border">
              <div className="flex items-center justify-between">
                <span className="font-semibold text-sm">Full Test Audio (`full_test.wav`)</span>
                <Badge variant="secondary" className="font-mono text-xs">
                  {Math.floor((summary.audioDurationSec || 0) / 60)} mins
                </Badge>
              </div>
              <audio
                controls
                className="w-full h-10"
                src={`/api/media/${testId}/audio/full_test.wav`}
              >
                Your browser does not support the audio element.
              </audio>
            </div>
          ) : (
            <div className="p-8 text-center border-2 border-dashed rounded-xl space-y-3">
              <Music className="w-8 h-8 text-muted-foreground mx-auto" />
              <p className="text-sm font-medium">No audio synthesized for this test yet.</p>
              <Button size="sm" onClick={() => handleRunStage(2)} className="gap-1.5 rounded-xl text-xs">
                <Play className="w-3.5 h-3.5" />
                <span>Run Stage 2 Now</span>
              </Button>
            </div>
          )}

          {/* Individual Part WAVs */}
          {audioFiles.length > 0 && (
            <div className="space-y-3 pt-4 border-t">
              <h4 className="font-semibold text-xs text-muted-foreground uppercase tracking-wider">
                Part Audio Segments
              </h4>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                {audioFiles
                  .filter((f: string) => f !== "full_test.wav")
                  .map((file: string) => (
                    <div key={file} className="p-3 border rounded-xl bg-card space-y-2">
                      <p className="font-mono text-xs font-medium text-foreground truncate">{file}</p>
                      <audio controls className="w-full h-8" src={`/api/media/${testId}/audio/${file}`} />
                    </div>
                  ))}
              </div>
            </div>
          )}
        </Card>
      )}

      {/* Tab 3: Video & Screens */}
      {activeTab === "video" && (
        <div className="space-y-6">
          <Card className="rounded-2xl border p-6 space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="font-bold text-lg flex items-center gap-2">
                  <Video className="w-5 h-5 text-primary" />
                  <span>Rendered 1080p Video</span>
                </h3>
                <p className="text-xs text-muted-foreground">
                  Playwright rendered exam screens with Pillow dynamic countdown HUD timers
                </p>
              </div>

              <Button
                variant="outline"
                size="sm"
                disabled={runningStage === 3}
                onClick={() => handleRunStage(3)}
                className="gap-1.5 rounded-xl text-xs"
              >
                {runningStage === 3 ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <RotateCw className="w-3.5 h-3.5" />}
                <span>Re-render Video (Stage 3)</span>
              </Button>
            </div>

            {summary.hasVideo ? (
              <div className="space-y-4">
                <div className="rounded-2xl overflow-hidden border bg-black shadow-lg aspect-video max-w-4xl mx-auto">
                  <video
                    controls
                    className="w-full h-full"
                    poster={`/api/media/${testId}/thumbnail.png`}
                    src={`/api/media/${testId}/video/${testId}.mp4`}
                  >
                    Your browser does not support the video element.
                  </video>
                </div>

                {/* Chapters */}
                {files.chapters && (
                  <div className="p-4 bg-muted/30 border rounded-xl space-y-2">
                    <p className="font-semibold text-xs text-foreground">YouTube Chapter Timestamps</p>
                    <pre className="font-mono text-xs text-muted-foreground whitespace-pre-wrap">
                      {files.chapters}
                    </pre>
                  </div>
                )}
              </div>
            ) : (
              <div className="p-8 text-center border-2 border-dashed rounded-xl space-y-3">
                <Video className="w-8 h-8 text-muted-foreground mx-auto" />
                <p className="text-sm font-medium">No 1080p video rendered for this test yet.</p>
                <Button size="sm" onClick={() => handleRunStage(3)} className="gap-1.5 rounded-xl text-xs">
                  <Play className="w-3.5 h-3.5" />
                  <span>Render Video (Stage 3)</span>
                </Button>
              </div>
            )}
          </Card>

          {/* Exam Screens Gallery */}
          {screens.length > 0 && (
            <Card className="rounded-2xl border p-6 space-y-4">
              <h4 className="font-bold text-sm">Exam Screen Captures ({screens.length} screens)</h4>
              <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-3">
                {screens.map((screen: string) => (
                  <div key={screen} className="border rounded-xl overflow-hidden bg-muted group relative">
                    <img
                      src={`/api/media/${testId}/video/screens/${screen}`}
                      alt={screen}
                      className="w-full aspect-video object-cover"
                      loading="lazy"
                    />
                    <div className="p-1.5 text-[10px] font-mono text-center text-muted-foreground truncate border-t bg-card">
                      {screen}
                    </div>
                  </div>
                ))}
              </div>
            </Card>
          )}
        </div>
      )}

      {/* Tab 4: Visual Diagram */}
      {activeTab === "visual" && (
        <div className="space-y-6">
          {summary.hasVisualImage && (
            <Card className="rounded-2xl border p-6 space-y-3">
              <div className="flex items-center justify-between">
                <h4 className="font-bold text-sm">Current Attached Visual Image</h4>
                <Badge className="bg-green-500/10 text-green-600 dark:text-green-400 text-xs">
                  Ready for Stage 3
                </Badge>
              </div>
              <div className="border rounded-xl overflow-hidden bg-muted max-w-md mx-auto aspect-square flex items-center justify-center">
                <img
                  src={`/api/media/${testId}/visuals/v1.png`}
                  alt="Visual v1"
                  className="w-full h-full object-contain"
                />
              </div>
            </Card>
          )}

          {summary.visualInfo ? (
            <VisualPromptModal
              visualInfo={summary.visualInfo}
              testId={testId}
              onResumed={() => window.location.reload()}
            />
          ) : (
            <Card className="rounded-2xl border p-6 text-center text-muted-foreground text-xs">
              This test does not have a map/floorplan diagram requirement in visuals.md.
            </Card>
          )}
        </div>
      )}

      {/* Tab 5: YouTube Publisher */}
      {activeTab === "youtube" && (
        <Card className="rounded-2xl border p-6 space-y-6">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="font-bold text-lg flex items-center gap-2">
                <YoutubeIcon className="w-5 h-5 text-red-500" />
                <span>Publish to YouTube</span>
              </h3>
              <p className="text-xs text-muted-foreground">
                Uploads the 1080p MP4 with custom title, thumbnail, timestamped chapters, and answers
              </p>
            </div>

            {summary.youtubeId && (
              <a
                href={`https://youtu.be/${summary.youtubeId}`}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1.5 text-xs font-semibold text-red-600 bg-red-500/10 border border-red-500/20 px-3 py-1.5 rounded-xl hover:bg-red-500/20"
              >
                <span>Live on YouTube</span>
                <ExternalLink className="w-3.5 h-3.5" />
              </a>
            )}
          </div>

          <div className="space-y-4">
            {/* Title */}
            <div className="space-y-1.5">
              <label className="text-xs font-semibold text-foreground">Video Title</label>
              <Input
                value={ytTitle}
                onChange={(e) => setYtTitle(e.target.value)}
                className="font-medium text-xs rounded-xl"
              />
              <p className="text-[10px] text-muted-foreground">Max 100 characters</p>
            </div>

            {/* Thumbnail Preview */}
            {summary.hasThumbnail && (
              <div className="space-y-1.5">
                <label className="text-xs font-semibold text-foreground">Custom Thumbnail</label>
                <div className="w-48 aspect-video border rounded-xl overflow-hidden bg-muted">
                  <img src={`/api/media/${testId}/thumbnail.png`} alt="Thumbnail" className="w-full h-full object-cover" />
                </div>
              </div>
            )}

            {/* Description */}
            <div className="space-y-1.5">
              <label className="text-xs font-semibold text-foreground">
                YouTube Description (auto-populated with chapters & answers)
              </label>
              <textarea
                value={ytDescription}
                onChange={(e) => setYtDescription(e.target.value)}
                rows={10}
                className="w-full p-3 font-mono text-xs border rounded-xl bg-muted/20 text-muted-foreground focus:outline-none focus:ring-1 focus:ring-primary"
              />
            </div>

            {publishResult?.error && (
              <div className="p-3 bg-destructive/10 text-destructive text-xs rounded-xl border border-destructive/20">
                {publishResult.error}
              </div>
            )}

            {publishResult?.success && (
              <div className="p-3 bg-green-500/10 text-green-600 dark:text-green-400 text-xs rounded-xl border border-green-500/20">
                YouTube upload initiated! Redirecting to live console...
              </div>
            )}

            <Button
              onClick={handlePublishYouTube}
              disabled={publishing || !summary.hasVideo}
              className="gap-2 rounded-xl h-10 w-full bg-red-600 hover:bg-red-700 text-white font-semibold shadow-md shadow-red-600/20"
            >
              {publishing ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
              <span>{summary.hasVideo ? "Upload Video & Set Thumbnail Now" : "Render Video First"}</span>
            </Button>
          </div>
        </Card>
      )}
    </div>
  )
}
