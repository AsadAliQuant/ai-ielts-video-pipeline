# CLAUDE.md

Fish Audio is 100% free for developers with the model we are using.

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

A three-stage pipeline that turns a topic/band prompt into a YouTube-ready 1920×1080 IELTS
Listening exam video: LLM-generated test paper → TTS audio → rendered exam screens + baked
HUD → muxed MP4. Each stage is a standalone script reading/writing files under `tests/test_NNN/`;
there is no shared framework or app server.

## Commands

Setup:
```bash
pip install -r requirements.txt
playwright install chromium   # required once for Stage 3 rendering
```

Stage 1 — generate test paper (`tests/test_NNN/test.json`, `student_paper.md`, `transcript.txt`, `answer_key.md`, `visuals.md`):
```bash
python -u generate_test.py --band 7.0                # full run w/ LLM verification, ~40-60 min
python -u generate_test.py --band 7.0 --skip-verify   # skip verification, ~15 min
python -u generate_test.py --provider nvidia          # use NVIDIA NIM instead of Gemini (default)
```

Stage 2 — voices + audio:
```bash
python select_voices.py --auto              # (re)populate audio_config.json with best Fish Audio voices
python generate_audio.py tests/test_007      # synthesize part_N.wav + full_test.wav
```

Stage 3 — video:
```bash
python generate_video.py tests/test_007 --fast              # FFmpeg concat muxer, ~1-2 min
python generate_video.py tests/test_007                     # full MoviePy v2 path
python generate_video.py tests/test_007 --fast --skip-visuals --output out.mp4
```

Stage 4 — YouTube description & upload:
```bash
python generate_youtube_description.py tests/test_007       # deterministic 0-AI description generator
python youtube_upload.py tests/test_007                     # upload video + custom description & thumbnail
```

Batch Generation & End-to-End Pipeline:
```bash
python run_pipeline.py                                   # 1 test, Band 9.0, ChatGPT image prompt pause, video, YouTube upload
python run_pipeline.py --band 8.5                        # custom band score
python run_pipeline.py --skip-verify                     # fast Stage 1 (~10-15 min)
python run_pipeline.py --count 3                         # 3 tests sequentially
python batch_generate.py 1 --chatgpt --upload --fast     # full pipeline via batch_generate
python batch_generate.py 3                               # batch generate 3 full tests (Stages 1..3)
python batch_generate.py 5 --band 7.5 --skip-verify      # 5 tests, band 7.5, fast Stage 1
python batch_generate.py 2 --stage 1                     # generate 2 test papers only
```

WebUI Studio (Astro + shadcn/ui):
```bash
python webui.py                                              # Launch WebUI & open browser at http://localhost:4321
# OR double click run_studio.bat
# OR from webapp/: npm run studio
```

See `CHATGPT_IMAGE_YOUTUBE_PIPELINE.md` for the full terminal workflow guide.

There is no lint/test/build tooling configured (no pytest config, no linter). `tests/` is
pipeline **output** (generated exam runs), not a unit test suite — don't confuse the two.

## Architecture

Three independently runnable stages, each consuming the previous stage's output directory:

1. **Stage 1 — `generate_test.py`** (+ `generate_visual.py`, `system_prompt.txt`): calls an
   LLM (Gemini by default, NVIDIA NIM as fallback/alt via `--provider`) to author a complete
   4-part/40-question test, validates answer formats/word limits locally, optionally runs a
   second LLM pass that blind-solves and audits the test, then renders the student paper,
   transcript, answer key, and visuals.md. `system_prompt.txt` is a 900+ line spec treated as
   immutable — don't edit it casually. `generate_visual.py` (singular) generates Stage-1
   diagram assets via Cloudflare Workers AI (FLUX-1-schnell).
2. **Stage 2 — `select_voices.py`, `generate_audio.py`, `audio_config.json`**: discovers/tests
   Fish Audio TTS voices, assigns them to narrator/speaker roles in `audio_config.json`, then
   synthesizes per-segment WAVs and concatenates them into `part_N.wav` / `full_test.wav` with
   exact IELTS pause/prep timings.
3. **Stage 3 — `build_timeline.py`, `generate_visuals.py`, `render_screens.py`,
   `generate_video.py`, `video_config.json`**: `build_timeline.py` reconstructs the exact
   playback timeline from the Stage-2 WAVs via byte math (see gotcha below);
   `generate_visuals.py` (plural — distinct from Stage 1's `generate_visual.py`) generates
   Part 2/3 maps/diagrams via the Gemini Image API with a Pillow text-card fallback;
   `render_screens.py` renders exam paper pages via Playwright/Chromium to 1080p PNGs;
   `generate_video.py` is the coordinator — bakes ticking HUD/countdown frames onto the base
   screenshots with Pillow, then muxes audio+frames via MoviePy v2 (default) or an FFmpeg
   concat demuxer (`--fast`), writes `chapters.txt` for YouTube timestamps, and generates
   `thumbnail.png` via `generate_thumbnail.py`.

Each generated test lives under `tests/test_NNN/` (gitignored) with `test.json` as the single
source of truth, plus `audio/`, `visuals/`, and `video/` subdirectories mirroring the stage
that produced them — see `HANDOFF_PROMPT.md` for the full directory layout.

### Key engineering gotchas (see `HANDOFF_PROMPT.md` for detail)

- **WAV duration**: Fish Audio streaming WAVs have placeholder headers that make standard
  readers misreport duration. Always compute duration as
  `(path.stat().st_size - 44) / (sample_rate * channels * 2)`, as `build_timeline.py` does.
  Reconstructed timelines are validated against `full_test.wav` within 0.05s.
- **Visual generation never blocks the pipeline**: both `generate_visual.py` and
  `generate_visuals.py` fall back to a Pillow-drawn text/table card if the image API is
  missing keys, rate-limited, or errors.
- **HUD baking**: Playwright renders the static base exam page once per screen; the ticking
  countdown/progress bar is baked per-frame via Pillow paste (~10ms/frame) rather than
  re-rendering the page, to keep Stage 3 under ~2 minutes.
- **MoviePy v2 API**: uses `from moviepy import ImageClip, AudioFileClip,
  concatenate_videoclips` with `.with_duration()` / `.with_audio()` — this is the v2 API, not
  the v1 one most examples online still show.

### Environment variables (`.env`, see `.env.example`)

| Var | Used by | Purpose |
|---|---|---|
| `GEMINI_API_KEYS` (comma-separated) / `GEMINI_API_KEY` | `generate_test.py` | Gemini LLM calls (default provider); rotates keys on rate limit |
| `NVIDIA_API_KEY` | `generate_test.py` | NVIDIA NIM LLM calls, used via `--provider nvidia` |
| `FISH_AUDIO` | `select_voices.py`, `generate_audio.py` | Fish Audio TTS |
| `CF_ACCOUNT_ID`, `CF_API_TOKEN` | `generate_visual.py` (Stage 1 visuals) | Cloudflare Workers AI (FLUX-1-schnell) |
| Gemini key(s) above | `generate_visuals.py` (Stage 3 visuals) | Gemini Image API for maps/diagrams |

⚠️ `.env.example` currently has a real-looking `NVIDIA_API_KEY` value committed (not a
placeholder) — rotate that key and replace it with a placeholder before this repo is ever
made public or pushed to a shared remote.

### Non-pipeline scripts

`overlay_ielts_labels.py` and `test_nvidia_image.py` are standalone experiment/scratch
scripts (untracked in git) — not imported by any pipeline stage.
