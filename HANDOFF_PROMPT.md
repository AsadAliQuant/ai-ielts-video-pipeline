# Handoff prompt — IELTS Listening Test Pipeline (Stages 1–3)

Copy everything below the line into a fresh Claude Code / Antigravity session opened in
`d:\Asad\Projects\AI IELTS`.

---

## System Overview

You are working on a complete end-to-end IELTS Listening Test generation and video rendering system at `d:\Asad\Projects\AI IELTS`.
The system transforms AI prompts into YouTube-ready 1920×1080 listening test exam videos in three distinct, modular stages:

1. **Stage 1: Test Generation** (`generate_test.py`)
   Generates complete, original IELTS Listening tests (4 parts, 40 questions, blueprints, transcripts, answer keys) using NVIDIA NIM / Gemini models.
2. **Stage 2: Audio Synthesis** (`select_voices.py`, `generate_audio.py`, `audio_config.json`)
   Assigns realistic UK/Commonwealth voices and synthesizes complete exam audio with exact IELTS pauses, preparation times, and multi-speaker dialogues using Fish Audio TTS.
3. **Stage 3: Video Rendering** (`build_timeline.py`, `generate_visuals.py`, `render_screens.py`, `generate_video.py`, `video_config.json`)
   Reconstructs the playback timeline from disk, generates exam diagrams, renders 1920×1080 exam paper screens with Playwright, bakes dynamic ticking HUD countdown frames with Pillow, and encodes YouTube-ready MP4 videos with YouTube chapter markers.

---

## File Architecture

| File | Stage | Purpose |
|---|---|---|
| `generate_test.py` | 1 | Generates `test.json`, `student_paper.md`, `transcript.txt`, `answer_key.md`, `visuals.md`. |
| `system_prompt.txt` | 1 | 905-line master IELTS test designer specification. Treated as immutable spec. |
| `select_voices.py` | 2 | Discovers, tests, and configures Fish Audio TTS voices for narrator and test roles. |
| `audio_config.json` | 2 | Voice roster, timings (prep, mid-break, checking), narrator scripts, and speaker mapping. |
| `generate_audio.py` | 2 | Synthesizes narrator & dialogue segments, assembles `part_N.wav` and `full_test.wav`. |
| `video_config.json` | 3 | Resolution (1920×1080), theme colors, typography, HUD settings, image prompts, sections. |
| `build_timeline.py` | 3 | Reconstructs exact playback timeline via byte math, validates duration within 0.05s. |
| `generate_visuals.py` | 3 | Generates Part 2/3 diagrams/maps via Gemini Image API with automatic text-card fallback. |
| `render_screens.py` | 3 | Renders exam pages in HTML/CSS and captures 1080p PNGs with Playwright Chromium. |
| `generate_video.py` | 3 | Main coordinator: HUD frame baking, MoviePy v2 & fast FFmpeg muxing, `chapters.txt`. |
| `requirements.txt` | Core | Python dependencies (`openai`, `python-dotenv`, `requests`, `moviepy`, `playwright`, `pillow`). |
| `.env` | Secrets | API keys for NVIDIA NIM, Google Gemini (`GEMINI_API_KEYS`), and Fish Audio (`FISH_AUDIO`). |

---

## Directory Structure of a Generated Test (`tests/test_NNN/`)

```
tests/test_007/
├── test.json                  # Source of truth: parts, questions, transcripts, answers, visuals
├── student_paper.md           # Student-facing exam paper (no answers)
├── transcript.txt             # Clean TTS transcript (no question numbers)
├── answer_key.md              # Markdown answer key with accepted alternatives
├── visuals.md                 # Visual descriptions and mermaid diagrams
├── audio/
│   ├── full_test.wav          # ~25-minute concatenated master test audio
│   ├── part_1.wav ... part_4.wav
│   └── segments/              # Individual WAV segments (intro, dialogue_1, narrators, etc.)
├── visuals/
│   └── v1.png                 # Generated map / floor plan / diagram
└── video/
    ├── timeline.json          # Reconstructed playback timeline with question ranges
    ├── screens.json           # Playwright screen manifest mapping question ranges
    ├── chapters.txt           # YouTube description chapters with exact timestamps
    ├── screens/               # Base 1920x1080 PNG screenshots for each part and card
    ├── frames/                # Baked HUD frames with dynamic countdown timers
    └── test_007.mp4           # Final YouTube-ready 1080p MP4 video
```

---

## How to Run Each Stage

### Stage 1: Generate Test Paper
```bash
# Full generation with LLM verification (~40-60 min)
python -u generate_test.py --band 7.0

# Fast generation skipping verification (~15 min)
python -u generate_test.py --band 7.0 --skip-verify
```

### Stage 2: Generate Audio
```bash
# Automatically discover and configure best voices in audio_config.json
python select_voices.py --auto

# Generate all WAV segments and full test audio for a test
python generate_audio.py tests/test_007
```

### Stage 3: Generate Video & YouTube Chapters
```bash
# Fast generation using FFmpeg concat demuxer (~1-2 minutes)
python generate_video.py tests/test_007 --fast

# Full generation using MoviePy v2
python generate_video.py tests/test_007

# Custom output or skip visual re-querying
python generate_video.py tests/test_007 --fast --skip-visuals --output output.mp4
```

---

## Critical Engineering Constraints & Design Choices

1. **WAV Streaming Header Bypass**:
   Fish Audio returns streaming WAV segments with placeholder chunk headers (`0xFFFFFF00`), which causes standard audio readers to report ~48695s.
   `build_timeline.py` computes all durations using exact byte math:
   ```python
   duration = (path.stat().st_size - 44) / (sample_rate * channels * 2)
   ```
   Reconstructed timelines validate against `full_test.wav` within 0.05s tolerance.

2. **Visual Fallback Resiliency**:
   If Gemini Image API keys are missing, rate-limited, or encounter errors, `generate_visuals.py` automatically synthesizes a clean, high-contrast Pillow text/table card with labelled map landmarks and answer options. Visual failures never block video rendering.

3. **Hybrid HUD Baking for Speed**:
   Playwright renders static base 1080p exam paper pages once. Dynamic elements (ticking countdown timers, progress bar, audio indicator) are baked per second via Pillow pasting (~10ms/frame) onto the base screenshot, keeping total render time under 2 minutes.

4. **MoviePy v2 Compatibility**:
   Uses the modern MoviePy v2 API (`from moviepy import ImageClip, AudioFileClip, concatenate_videoclips`, `.with_duration()`, `.with_audio()`). Fast path (`--fast`) bypasses frame iteration via an FFmpeg concat demuxer script.
