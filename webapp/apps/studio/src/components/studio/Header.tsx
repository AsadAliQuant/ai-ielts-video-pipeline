import React, { useEffect, useState } from "react"
import { Badge } from "@workspace/ui/components/badge"
import { Button } from "@workspace/ui/components/button"
import { PlayCircle, LayoutDashboard, Settings, Video, CheckCircle2, AlertCircle, Loader2 } from "lucide-react"

export function Header({ currentPath }: { currentPath?: string }) {
  const [jobStatus, setJobStatus] = useState<any>(null)

  useEffect(() => {
    const checkStatus = async () => {
      try {
        const res = await fetch("/api/pipeline/status")
        if (res.ok) {
          const data = await res.json()
          setJobStatus(data.activeJob)
        }
      } catch {
        // ignore
      }
    }

    checkStatus()
    const interval = setInterval(checkStatus, 4000)
    return () => clearInterval(interval)
  }, [])

  return (
    <header className="border-b bg-card/80 backdrop-blur-md sticky top-0 z-40">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 h-16 flex items-center justify-between">
        {/* Brand */}
        <div className="flex items-center gap-3">
          <div className="h-9 w-9 rounded-xl bg-primary flex items-center justify-center text-primary-foreground font-bold shadow-md shadow-primary/20">
            <Video className="w-5 h-5" />
          </div>
          <div>
            <a href="/" className="font-bold text-lg tracking-tight hover:opacity-80 transition-opacity">
              IELTS Video Studio
            </a>
            <p className="text-xs text-muted-foreground">AI Video Generation & YouTube Publisher</p>
          </div>
        </div>

        {/* Navigation */}
        <nav className="flex items-center gap-2">
          <a href="/">
            <Button
              variant={currentPath === "/" ? "secondary" : "ghost"}
              size="sm"
              className="gap-2 rounded-xl"
            >
              <LayoutDashboard className="w-4 h-4" />
              <span>Tests Archive</span>
            </Button>
          </a>

          <a href="/pipeline">
            <Button
              variant={currentPath === "/pipeline" ? "default" : "outline"}
              size="sm"
              className="gap-2 rounded-xl font-medium"
            >
              <PlayCircle className="w-4 h-4" />
              <span>New Pipeline Run</span>
            </Button>
          </a>

          <a href="/settings">
            <Button
              variant={currentPath === "/settings" ? "secondary" : "ghost"}
              size="sm"
              className="gap-2 rounded-xl"
            >
              <Settings className="w-4 h-4" />
              <span>Diagnostics</span>
            </Button>
          </a>

          {/* Job Indicator */}
          {jobStatus && (jobStatus.status === "running" || jobStatus.status === "awaiting_visual") && (
            <a href="/pipeline" className="ml-2">
              <Badge
                variant={jobStatus.status === "awaiting_visual" ? "secondary" : "default"}
                className={`py-1 px-3 text-xs gap-1.5 cursor-pointer animate-pulse ${
                  jobStatus.status === "awaiting_visual" ? "bg-amber-500/15 text-amber-600 dark:text-amber-400 border-amber-500/30" : ""
                }`}
              >
                {jobStatus.status === "awaiting_visual" ? (
                  <>
                    <AlertCircle className="w-3.5 h-3.5" />
                    <span>Visual Required</span>
                  </>
                ) : (
                  <>
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                    <span>Running ({jobStatus.currentStage.replace("_", " ")})</span>
                  </>
                )}
              </Badge>
            </a>
          )}
        </nav>
      </div>
    </header>
  )
}
