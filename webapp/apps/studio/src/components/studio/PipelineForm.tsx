import React, { useState } from "react"
import { Button } from "@workspace/ui/components/button"
import { Badge } from "@workspace/ui/components/badge"
import { Card, CardHeader, CardTitle, CardDescription, CardContent, CardFooter } from "@workspace/ui/components/card"
import { Input } from "@workspace/ui/components/input"
import { Checkbox } from "@workspace/ui/components/checkbox"
import { PlayCircle, Sliders, Sparkles, Zap, ShieldCheck, Eye } from "lucide-react"
import { YoutubeIcon } from "./YoutubeIcon"

export function PipelineForm({ onStarted }: { onStarted?: (job: any) => void }) {
  const [band, setBand] = useState("9.0")
  const [context, setContext] = useState<"academic" | "general">("academic")
  const [difficulty, setDifficulty] = useState("")
  const [provider, setProvider] = useState<"gemini" | "nvidia">("gemini")
  const [geminiModel, setGeminiModel] = useState("gemini-3.5-flash-lite")
  const [skipVerify, setSkipVerify] = useState(true) // default to fast mode for better UX
  const [fastMux, setFastMux] = useState(true)
  const [autoUpload, setAutoUpload] = useState(false)
  const [dryRun, setDryRun] = useState(false)
  const [targetStage, setTargetStage] = useState<number>(4)

  // Topics per part
  const [showTopics, setShowTopics] = useState(false)
  const [p1Topic, setP1Topic] = useState("")
  const [p2Topic, setP2Topic] = useState("")
  const [p3Topic, setP3Topic] = useState("")
  const [p4Topic, setP4Topic] = useState("")

  const [loading, setLoading] = useState(false)
  const [errorMsg, setErrorMsg] = useState<string | null>(null)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)
    setErrorMsg(null)

    const topicsArr = [p1Topic, p2Topic, p3Topic, p4Topic].map((t) => t.trim()).filter(Boolean)
    const topicsStr = topicsArr.length > 0 ? topicsArr.join(", ") : undefined

    try {
      const res = await fetch("/api/pipeline/start", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          band,
          context,
          difficulty: difficulty || undefined,
          provider,
          geminiModel,
          skipVerify,
          fast: fastMux,
          autoUpload,
          dryRun,
          targetStage,
          topics: topicsStr
        })
      })

      const data = await res.json()
      if (!res.ok) {
        throw new Error(data.error || "Failed to start pipeline")
      }

      if (onStarted) {
        onStarted(data.job)
      }
    } catch (err: any) {
      setErrorMsg(err.message)
    } finally {
      setLoading(false)
    }
  }

  const bandOptions = ["6.5", "7.0", "7.5", "8.0", "8.5", "9.0"]

  return (
    <Card className="rounded-2xl border shadow-sm">
      <CardHeader className="pb-4">
        <div className="flex items-center justify-between">
          <div>
            <CardTitle className="text-lg font-bold">New IELTS Video Pipeline</CardTitle>
            <CardDescription className="text-xs">
              Configure parameters to author, synthesize audio, render 1080p screens, and publish to YouTube.
            </CardDescription>
          </div>
          <Badge variant="outline" className="gap-1 text-xs">
            <Zap className="w-3 h-3 text-amber-500" />
            <span>AI Automated</span>
          </Badge>
        </div>
      </CardHeader>

      <form onSubmit={handleSubmit}>
        <CardContent className="space-y-6 text-sm">
          {/* Band Score Selector */}
          <div className="space-y-2">
            <label className="font-semibold block text-foreground">Target Band Score</label>
            <div className="flex flex-wrap gap-2">
              {bandOptions.map((b) => (
                <button
                  key={b}
                  type="button"
                  onClick={() => setBand(b)}
                  className={`px-3.5 py-1.5 rounded-xl text-xs font-semibold border transition-all ${
                    band === b
                      ? "border-primary bg-primary text-primary-foreground shadow-sm shadow-primary/20"
                      : "border-border hover:bg-muted text-muted-foreground"
                  }`}
                >
                  Band {b}
                </button>
              ))}
            </div>
          </div>

          {/* Context & Provider */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div className="space-y-2">
              <label className="font-semibold block text-foreground">Exam Context</label>
              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={() => setContext("academic")}
                  className={`flex-1 py-1.5 rounded-xl text-xs font-semibold border transition-all ${
                    context === "academic"
                      ? "border-primary bg-primary/10 text-primary"
                      : "border-border hover:bg-muted text-muted-foreground"
                  }`}
                >
                  Academic
                </button>
                <button
                  type="button"
                  onClick={() => setContext("general")}
                  className={`flex-1 py-1.5 rounded-xl text-xs font-semibold border transition-all ${
                    context === "general"
                      ? "border-primary bg-primary/10 text-primary"
                      : "border-border hover:bg-muted text-muted-foreground"
                  }`}
                >
                  General Training
                </button>
              </div>
            </div>

            <div className="space-y-2">
              <label className="font-semibold block text-foreground">LLM Provider</label>
              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={() => setProvider("gemini")}
                  className={`flex-1 py-1.5 rounded-xl text-xs font-semibold border transition-all ${
                    provider === "gemini"
                      ? "border-primary bg-primary/10 text-primary"
                      : "border-border hover:bg-muted text-muted-foreground"
                  }`}
                >
                  Google Gemini
                </button>
                <button
                  type="button"
                  onClick={() => setProvider("nvidia")}
                  className={`flex-1 py-1.5 rounded-xl text-xs font-semibold border transition-all ${
                    provider === "nvidia"
                      ? "border-primary bg-primary/10 text-primary"
                      : "border-border hover:bg-muted text-muted-foreground"
                  }`}
                >
                  NVIDIA NIM
                </button>
              </div>
            </div>
          </div>

          {/* Verification & Speed Controls */}
          <div className="p-4 rounded-xl bg-muted/40 border space-y-3">
            <div className="flex items-center justify-between">
              <div>
                <p className="font-semibold text-xs text-foreground">Fast Stage 1 Mode (--skip-verify)</p>
                <p className="text-[11px] text-muted-foreground">
                  Skips the 30-min second-pass LLM verifier. Generates test paper in ~10–15 mins instead of ~45 mins.
                </p>
              </div>
              <input
                type="checkbox"
                checked={skipVerify}
                onChange={(e) => setSkipVerify(e.target.checked)}
                className="w-4 h-4 rounded text-primary focus:ring-primary cursor-pointer"
              />
            </div>

            <div className="border-t pt-3 flex items-center justify-between">
              <div>
                <p className="font-semibold text-xs text-foreground">Fast Video Muxing (--fast)</p>
                <p className="text-[11px] text-muted-foreground">
                  Uses FFmpeg concat demuxer (~1–2 min) instead of software frame-by-frame MoviePy muxing.
                </p>
              </div>
              <input
                type="checkbox"
                checked={fastMux}
                onChange={(e) => setFastMux(e.target.checked)}
                className="w-4 h-4 rounded text-primary focus:ring-primary cursor-pointer"
              />
            </div>

            <div className="border-t pt-3 flex items-center justify-between">
              <div>
                <p className="font-semibold text-xs text-foreground flex items-center gap-1.5">
                  <YoutubeIcon className="w-3.5 h-3.5 text-red-500" />
                  <span>Auto-Publish to YouTube</span>
                </p>
                <p className="text-[11px] text-muted-foreground">
                  Automatically uploads 1080p MP4 + thumbnail + custom chapters upon Stage 3 completion.
                </p>
              </div>
              <input
                type="checkbox"
                checked={autoUpload}
                onChange={(e) => setAutoUpload(e.target.checked)}
                className="w-4 h-4 rounded text-primary focus:ring-primary cursor-pointer"
              />
            </div>
          </div>

          {/* Topics Accordion (Optional) */}
          <div className="space-y-2">
            <button
              type="button"
              onClick={() => setShowTopics(!showTopics)}
              className="text-xs text-primary font-medium hover:underline flex items-center gap-1"
            >
              <Sliders className="w-3.5 h-3.5" />
              <span>{showTopics ? "Hide custom topic hints" : "Customize part topic hints (optional)"}</span>
            </button>

            {showTopics && (
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-2">
                <div>
                  <label className="text-xs text-muted-foreground">Part 1 Topic</label>
                  <Input
                    placeholder="e.g. Booking a holiday cottage"
                    value={p1Topic}
                    onChange={(e) => setP1Topic(e.target.value)}
                    className="h-8 text-xs rounded-lg mt-1"
                  />
                </div>
                <div>
                  <label className="text-xs text-muted-foreground">Part 2 Topic</label>
                  <Input
                    placeholder="e.g. Local botanical garden tour & map"
                    value={p2Topic}
                    onChange={(e) => setP2Topic(e.target.value)}
                    className="h-8 text-xs rounded-lg mt-1"
                  />
                </div>
                <div>
                  <label className="text-xs text-muted-foreground">Part 3 Topic</label>
                  <Input
                    placeholder="e.g. University project on renewable energy"
                    value={p3Topic}
                    onChange={(e) => setP3Topic(e.target.value)}
                    className="h-8 text-xs rounded-lg mt-1"
                  />
                </div>
                <div>
                  <label className="text-xs text-muted-foreground">Part 4 Topic</label>
                  <Input
                    placeholder="e.g. Academic lecture on marine biology"
                    value={p4Topic}
                    onChange={(e) => setP4Topic(e.target.value)}
                    className="h-8 text-xs rounded-lg mt-1"
                  />
                </div>
              </div>
            )}
          </div>

          {/* Dry Run */}
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <input
              type="checkbox"
              id="dryRun"
              checked={dryRun}
              onChange={(e) => setDryRun(e.target.checked)}
              className="w-3.5 h-3.5 rounded text-primary focus:ring-primary cursor-pointer"
            />
            <label htmlFor="dryRun" className="cursor-pointer">
              Dry run preview (simulates execution without calling AI APIs or FFmpeg)
            </label>
          </div>

          {errorMsg && (
            <div className="p-3 bg-destructive/10 text-destructive text-xs rounded-xl border border-destructive/20">
              {errorMsg}
            </div>
          )}
        </CardContent>

        <CardFooter className="pt-2 pb-6 px-6">
          <Button
            type="submit"
            disabled={loading}
            className="w-full gap-2 rounded-xl h-10 font-semibold shadow-md shadow-primary/20"
          >
            <PlayCircle className="w-4 h-4" />
            <span>{dryRun ? "Preview Dry Run" : "Start Video Generation Pipeline"}</span>
          </Button>
        </CardFooter>
      </form>
    </Card>
  )
}
