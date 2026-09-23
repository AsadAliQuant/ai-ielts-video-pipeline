import React, { useState, useEffect } from "react"
import { Button } from "@workspace/ui/components/button"
import { Badge } from "@workspace/ui/components/badge"
import { Card, CardHeader, CardTitle, CardDescription, CardContent, CardFooter } from "@workspace/ui/components/card"
import { Copy, Check, Upload, Image as ImageIcon, Sparkles, FolderDown, ArrowRight, Loader2 } from "lucide-react"

interface VisualInfo {
  id: string
  title: string
  type: string
  prompt: string
  targetPath?: string
}

interface DownloadImage {
  name: string
  fullPath: string
  sizeBytes: number
  modifiedTime: string
  ageMinutes: number
}

interface VisualPromptModalProps {
  visualInfo: VisualInfo
  testId?: string
  jobId?: string
  onResumed?: () => void
}

export function VisualPromptModal({ visualInfo, testId, jobId, onResumed }: VisualPromptModalProps) {
  const [copied, setCopied] = useState(false)
  const [recentDownloads, setRecentDownloads] = useState<DownloadImage[]>([])
  const [loadingDownloads, setLoadingDownloads] = useState(false)
  const [selectedDownload, setSelectedDownload] = useState<DownloadImage | null>(null)
  const [uploadedFile, setUploadedFile] = useState<File | null>(null)
  const [previewUrl, setPreviewUrl] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [errorMsg, setErrorMsg] = useState<string | null>(null)

  // Fetch recent downloads
  useEffect(() => {
    const fetchDownloads = async () => {
      setLoadingDownloads(true)
      try {
        const res = await fetch("/api/downloads/recent-images")
        if (res.ok) {
          const data = await res.json()
          setRecentDownloads(data)
          if (data.length > 0 && !previewUrl && !selectedDownload) {
            // Auto-select most recent if less than 30 mins
            if (data[0].ageMinutes <= 30) {
              setSelectedDownload(data[0])
            }
          }
        }
      } catch {
        // ignore
      } finally {
        setLoadingDownloads(false)
      }
    }

    fetchDownloads()
  }, [])

  const handleCopyPrompt = () => {
    navigator.clipboard.writeText(visualInfo.prompt)
    setCopied(true)
    setTimeout(() => setCopied(false), 2500)
  }

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      const file = e.target.files[0]
      setUploadedFile(file)
      setSelectedDownload(null)
      setPreviewUrl(URL.createObjectURL(file))
      setErrorMsg(null)
    }
  }

  const handleSelectDownload = (img: DownloadImage) => {
    setSelectedDownload(img)
    setUploadedFile(null)
    setErrorMsg(null)
  }

  const handleConfirm = async () => {
    if (!selectedDownload && !uploadedFile) {
      setErrorMsg("Please select an image or upload one first.")
      return
    }

    setSubmitting(true)
    setErrorMsg(null)

    try {
      if (jobId) {
        // Resuming active job
        const formData = new FormData()
        formData.append("jobId", jobId)
        if (selectedDownload) {
          formData.append("downloadPath", selectedDownload.fullPath)
        } else if (uploadedFile) {
          formData.append("file", uploadedFile)
        }

        const res = await fetch("/api/pipeline/resume", {
          method: "POST",
          body: formData
        })

        if (!res.ok) {
          const err = await res.json()
          throw new Error(err.error || "Failed to resume pipeline")
        }
      } else if (testId) {
        // Direct test upload
        const formData = new FormData()
        if (selectedDownload) {
          formData.append("downloadPath", selectedDownload.fullPath)
        } else if (uploadedFile) {
          formData.append("file", uploadedFile)
        }

        const res = await fetch(`/api/tests/${testId}/visual`, {
          method: "POST",
          body: formData
        })

        if (!res.ok) {
          const err = await res.json()
          throw new Error(err.error || "Failed to save visual")
        }
      }

      if (onResumed) onResumed()
    } catch (err: any) {
      setErrorMsg(err.message)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Card className="border-amber-500/40 bg-amber-500/[0.03] shadow-lg rounded-2xl overflow-hidden">
      <CardHeader className="border-b border-amber-500/20 bg-amber-500/10 pb-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="p-1.5 rounded-lg bg-amber-500/20 text-amber-600 dark:text-amber-400">
              <Sparkles className="w-5 h-5" />
            </span>
            <div>
              <CardTitle className="text-base font-bold text-foreground">
                ChatGPT Visual Required: {visualInfo.title}
              </CardTitle>
              <CardDescription className="text-xs">
                Section: {visualInfo.id.toUpperCase()} • Type: {visualInfo.type}
              </CardDescription>
            </div>
          </div>
          <Badge variant="outline" className="border-amber-500/40 text-amber-600 dark:text-amber-400">
            Action Required
          </Badge>
        </div>
      </CardHeader>

      <CardContent className="p-6 space-y-6">
        {/* Step 1: Copy Prompt */}
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <label className="text-sm font-semibold flex items-center gap-2">
              <span className="w-5 h-5 rounded-full bg-primary text-primary-foreground text-xs flex items-center justify-center font-bold">1</span>
              <span>Copy Prompt into ChatGPT / DALL-E</span>
            </label>
            <Button
              size="sm"
              variant="outline"
              onClick={handleCopyPrompt}
              className="h-8 gap-1.5 text-xs rounded-xl"
            >
              {copied ? (
                <>
                  <Check className="w-3.5 h-3.5 text-green-500" />
                  <span className="text-green-600 font-medium">Copied!</span>
                </>
              ) : (
                <>
                  <Copy className="w-3.5 h-3.5" />
                  <span>Copy Prompt</span>
                </>
              )}
            </Button>
          </div>

          <div className="p-3 bg-muted/60 rounded-xl text-xs font-mono text-muted-foreground border leading-relaxed max-h-36 overflow-y-auto select-all">
            {visualInfo.prompt}
          </div>
        </div>

        {/* Step 2: Upload or Select from Downloads */}
        <div className="space-y-3">
          <label className="text-sm font-semibold flex items-center gap-2">
            <span className="w-5 h-5 rounded-full bg-primary text-primary-foreground text-xs flex items-center justify-center font-bold">2</span>
            <span>Attach Generated Image</span>
          </label>

          {/* Option A: Recent Downloads Auto-Detector */}
          {recentDownloads.length > 0 && (
            <div className="bg-card border rounded-xl p-3.5 space-y-2">
              <div className="flex items-center justify-between text-xs text-muted-foreground font-medium">
                <span className="flex items-center gap-1.5">
                  <FolderDown className="w-4 h-4 text-primary" />
                  Recent images found in Downloads:
                </span>
                {loadingDownloads && <Loader2 className="w-3 h-3 animate-spin" />}
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                {recentDownloads.slice(0, 4).map((img) => (
                  <button
                    key={img.fullPath}
                    type="button"
                    onClick={() => handleSelectDownload(img)}
                    className={`flex items-center justify-between p-2.5 rounded-lg border text-left text-xs transition-all ${
                      selectedDownload?.fullPath === img.fullPath
                        ? "border-primary bg-primary/10 font-medium text-foreground"
                        : "border-border hover:bg-muted/50 text-muted-foreground"
                    }`}
                  >
                    <div className="truncate pr-2">
                      <p className="truncate font-mono">{img.name}</p>
                      <p className="text-[10px] text-muted-foreground">
                        {img.ageMinutes === 0 ? "Just now" : `${img.ageMinutes}m ago`} • {Math.round(img.sizeBytes / 1024)} KB
                      </p>
                    </div>
                    {selectedDownload?.fullPath === img.fullPath && (
                      <Check className="w-4 h-4 text-primary shrink-0" />
                    )}
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Option B: File Drag and Drop / Picker */}
          <div className="border-2 border-dashed rounded-xl p-4 text-center hover:border-primary/50 transition-colors bg-muted/20 relative cursor-pointer">
            <input
              type="file"
              accept="image/png, image/jpeg, image/webp"
              onChange={handleFileChange}
              className="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
            />
            <div className="flex flex-col items-center justify-center gap-1.5">
              <Upload className="w-6 h-6 text-muted-foreground" />
              <p className="text-xs font-medium">
                {uploadedFile ? uploadedFile.name : "Or drag & drop an image here, or click to browse"}
              </p>
              <p className="text-[10px] text-muted-foreground">PNG, JPG, or WEBP (1080p recommended)</p>
            </div>
          </div>

          {/* Preview */}
          {previewUrl && (
            <div className="flex items-center gap-3 p-2 border rounded-xl bg-card">
              <img src={previewUrl} alt="Preview" className="w-16 h-16 object-cover rounded-lg border" />
              <div className="text-xs">
                <p className="font-semibold text-foreground">Selected File</p>
                <p className="text-muted-foreground font-mono truncate">{uploadedFile?.name}</p>
              </div>
            </div>
          )}
        </div>

        {errorMsg && (
          <div className="p-3 bg-destructive/10 border border-destructive/20 text-destructive text-xs rounded-xl">
            {errorMsg}
          </div>
        )}
      </CardContent>

      <CardFooter className="border-t border-amber-500/20 bg-muted/30 px-6 py-4 flex items-center justify-between">
        <div className="text-xs text-muted-foreground">
          {selectedDownload ? (
            <span className="text-foreground font-medium">Ready to import: {selectedDownload.name}</span>
          ) : uploadedFile ? (
            <span className="text-foreground font-medium">Ready to upload: {uploadedFile.name}</span>
          ) : (
            "Select an image to continue"
          )}
        </div>

        <Button
          onClick={handleConfirm}
          disabled={submitting || (!selectedDownload && !uploadedFile)}
          className="gap-2 rounded-xl"
        >
          {submitting ? (
            <>
              <Loader2 className="w-4 h-4 animate-spin" />
              <span>Applying Visual...</span>
            </>
          ) : (
            <>
              <span>Continue Pipeline</span>
              <ArrowRight className="w-4 h-4" />
            </>
          )}
        </Button>
      </CardFooter>
    </Card>
  )
}
