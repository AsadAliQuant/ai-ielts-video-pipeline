import React from "react"
import { Badge } from "@workspace/ui/components/badge"
import { Button } from "@workspace/ui/components/button"
import { Card, CardContent } from "@workspace/ui/components/card"
import {
  FileText,
  Music,
  Video,
  ExternalLink,
  Sparkles,
  ArrowRight,
  Clock,
  Play,
  CheckCircle2,
  AlertCircle
} from "lucide-react"
import { YoutubeIcon } from "./YoutubeIcon"
import type { TestSummary } from "@/lib/test-service"

export function TestCard({ test }: { test: TestSummary }) {
  const formatDuration = (sec?: number) => {
    if (!sec) return ""
    const mins = Math.floor(sec / 60)
    const secs = sec % 60
    return `${mins}:${secs.toString().padStart(2, "0")}`
  }

  return (
    <Card className="rounded-2xl border shadow-sm hover:shadow-md transition-all overflow-hidden flex flex-col justify-between">
      <CardContent className="p-5 space-y-4">
        {/* Top Header */}
        <div className="flex items-start justify-between gap-2">
          <div>
            <div className="flex items-center gap-2">
              <span className="font-mono font-bold text-base text-foreground">{test.id}</span>
              <Badge variant="secondary" className="text-xs font-semibold px-2 py-0.5 rounded-md">
                Band {test.band}
              </Badge>
              <Badge variant="outline" className="text-[11px] capitalize">
                {test.context}
              </Badge>
            </div>
            <p className="text-xs text-muted-foreground mt-1 line-clamp-1">
              {test.title}
            </p>
          </div>

          {test.youtubeId ? (
            <a
              href={`https://youtu.be/${test.youtubeId}`}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 text-[11px] font-semibold text-red-600 dark:text-red-400 bg-red-500/10 border border-red-500/20 px-2 py-1 rounded-lg hover:bg-red-500/20 transition-colors"
            >
              <YoutubeIcon className="w-3.5 h-3.5" />
              <span>YouTube</span>
              <ExternalLink className="w-2.5 h-2.5" />
            </a>
          ) : test.hasVideo ? (
            <Badge className="bg-green-500/10 text-green-600 dark:text-green-400 border-green-500/20 text-[11px]">
              MP4 Ready
            </Badge>
          ) : (
            <Badge variant="outline" className="text-[11px] text-muted-foreground">
              In Progress
            </Badge>
          )}
        </div>

        {/* 4 Stage Pills */}
        <div className="grid grid-cols-2 gap-2 pt-2 text-xs">
          {/* Stage 1: Paper */}
          <div className="flex items-center gap-2 p-2 rounded-xl bg-muted/30 border">
            <FileText className={`w-4 h-4 ${test.hasTestJson ? "text-primary" : "text-muted-foreground/40"}`} />
            <div className="truncate">
              <p className="text-[10px] text-muted-foreground">Stage 1 Paper</p>
              <p className="font-medium text-foreground truncate">
                {test.hasTestJson ? "40 Questions" : "Missing"}
              </p>
            </div>
          </div>

          {/* Visual Hook */}
          <div className="flex items-center gap-2 p-2 rounded-xl bg-muted/30 border">
            <Sparkles className={`w-4 h-4 ${test.hasVisualImage ? "text-amber-500" : "text-muted-foreground/40"}`} />
            <div className="truncate">
              <p className="text-[10px] text-muted-foreground">Visual Diagram</p>
              <p className="font-medium text-foreground truncate">
                {test.hasVisualImage
                  ? "Image attached"
                  : test.visualInfo
                  ? "Required"
                  : "None needed"}
              </p>
            </div>
          </div>

          {/* Stage 2: Audio */}
          <div className="flex items-center gap-2 p-2 rounded-xl bg-muted/30 border">
            <Music className={`w-4 h-4 ${test.hasAudio ? "text-primary" : "text-muted-foreground/40"}`} />
            <div className="truncate">
              <p className="text-[10px] text-muted-foreground">Stage 2 Audio</p>
              <p className="font-medium text-foreground truncate">
                {test.hasAudio ? formatDuration(test.audioDurationSec) || "Synthesized" : "Missing"}
              </p>
            </div>
          </div>

          {/* Stage 3: Video */}
          <div className="flex items-center gap-2 p-2 rounded-xl bg-muted/30 border">
            <Video className={`w-4 h-4 ${test.hasVideo ? "text-primary" : "text-muted-foreground/40"}`} />
            <div className="truncate">
              <p className="text-[10px] text-muted-foreground">Stage 3 Video</p>
              <p className="font-medium text-foreground truncate">
                {test.hasVideo ? `${test.videoSizeMB} MB` : "Missing"}
              </p>
            </div>
          </div>
        </div>

        {/* Thumbnail Preview if exists */}
        {test.hasThumbnail && (
          <div className="relative rounded-xl overflow-hidden aspect-video border bg-muted">
            <img
              src={`/api/media/${test.id}/thumbnail.png`}
              alt="Thumbnail"
              className="w-full h-full object-cover"
              loading="lazy"
            />
            {test.hasVideo && (
              <div className="absolute inset-0 bg-black/20 flex items-center justify-center opacity-0 hover:opacity-100 transition-opacity">
                <a href={`/tests/${test.id}?tab=video`}>
                  <div className="w-10 h-10 rounded-full bg-primary/90 text-primary-foreground flex items-center justify-center shadow-lg">
                    <Play className="w-5 h-5 ml-0.5" />
                  </div>
                </a>
              </div>
            )}
          </div>
        )}
      </CardContent>

      {/* Footer Actions */}
      <div className="p-4 pt-0 flex items-center justify-between border-t mt-2">
        <a href={`/tests/${test.id}`} className="w-full">
          <Button variant="outline" size="sm" className="w-full gap-1.5 rounded-xl text-xs h-8">
            <span>Inspect & Review</span>
            <ArrowRight className="w-3.5 h-3.5" />
          </Button>
        </a>
      </div>
    </Card>
  )
}
