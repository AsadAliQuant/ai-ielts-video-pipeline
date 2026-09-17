"""
Stage 3: Video Assembly & Orchestration

Orchestrates:
1. Timeline reconstruction (build_timeline)
2. Visual diagram generation (generate_visuals)
3. Screen rendering via Playwright (render_screens)
4. Fast HUD frame baking (Pillow)
5. Video encoding & audio muxing (MoviePy v2 / Fast FFmpeg)
6. YouTube chapters generation (chapters.txt)
"""

import argparse
import io
import json
import math
import os
import subprocess
import sys
import wave
from pathlib import Path
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import fonts
from build_timeline import build_timeline
from generate_visuals import generate_visuals, load_video_config
from render_screens import render_screens


# ---------------------------------------------------------------------------
# HUD Compositor (Pillow)
# ---------------------------------------------------------------------------

class HUDCompositor:
    """Fast HUD bar drawer that pastes onto pre-rendered screen screenshots."""

    def __init__(self, config: dict):
        self.hud_cfg = config.get("hud", {})
        self.height = self.hud_cfg.get("height", 72)
        self.bg_color = self.hud_cfg.get("bg_color", "#0F172A")
        self.text_color = self.hud_cfg.get("text_color", "#FFFFFF")
        self.badge_bg = self.hud_cfg.get("badge_bg", "#1E293B")
        self.badge_text = self.hud_cfg.get("badge_text", "#94A3B8")
        self.badge_active_bg = self.hud_cfg.get("badge_active_bg", "#1E40AF")
        self.badge_active_text = self.hud_cfg.get("badge_active_text", "#FFFFFF")
        self.countdown_color = self.hud_cfg.get("countdown_color", "#F59E0B")
        self.countdown_urgent_color = self.hud_cfg.get("countdown_urgent_color", "#EF4444")
        self.urgent_sec = self.hud_cfg.get("countdown_urgent_threshold_sec", 5)
        self.progress_bar_color = self.hud_cfg.get("progress_bar_color", "#3B82F6")
        self.progress_bar_bg = self.hud_cfg.get("progress_bar_bg", "#334155")
        self.progress_height = self.hud_cfg.get("progress_bar_height", 4)

        # Bundled fonts, never system ones: asking Pillow for "arialbd.ttf"
        # resolved on Windows and silently fell back to a ~10px bitmap font on
        # the Linux CI runner, which shrank every badge and dropped the en-dash.
        self.font_bold = fonts.pillow_font("bold", 22)
        self.font_medium = fonts.pillow_font("bold", 18)
        self.font_regular = fonts.pillow_font("regular", 16)

    def draw_hud(self, width: int, part_label: str, range_label: str,
                 status_label: str, countdown_sec: int | None,
                 progress_ratio: float) -> Image.Image:
        hud_img = Image.new("RGB", (width, self.height), color=self.bg_color)
        draw = ImageDraw.Draw(hud_img)

        # 1. Part badge (Left)
        part_w = int(draw.textlength(part_label, font=self.font_bold)) + 36
        draw.rounded_rectangle([(24, 14), (24 + part_w, 56)], radius=6, fill=self.badge_active_bg)
        draw.text((42, 23), part_label, fill=self.badge_active_text, font=self.font_bold)

        # 2. Questions range badge (Mid-left)
        if range_label:
            rx = 24 + part_w + 12
            range_w = int(draw.textlength(range_label, font=self.font_medium)) + 32
            draw.rounded_rectangle([(rx, 14), (rx + range_w, 56)], radius=6, fill=self.badge_bg)
            draw.text((rx + 16, 25), range_label, fill=self.text_color, font=self.font_medium)

        # 3. Status / Countdown (Right)
        if countdown_sec is not None and countdown_sec >= 0:
            c_color = self.countdown_urgent_color if countdown_sec <= self.urgent_sec else self.countdown_color
            timer_text = f"{countdown_sec:02d}s"
            status_text = f"{status_label}: {timer_text}" if status_label else f"TIME: {timer_text}"
            
            st_w = int(draw.textlength(status_text, font=self.font_bold)) + 36
            bx = width - 24 - st_w
            draw.rounded_rectangle([(bx, 14), (width - 24, 56)], radius=6, fill="#1E293B", outline=c_color, width=2)
            draw.text((bx + 18, 23), status_text, fill=c_color, font=self.font_bold)
        else:
            status_text = f"NOW PLAYING: {status_label}" if status_label and status_label != "LISTENING" else "NOW LISTENING"
            st_w = int(draw.textlength(status_text, font=self.font_bold)) + 36
            bx = width - 24 - st_w
            draw.rounded_rectangle([(bx, 14), (width - 24, 56)], radius=6, fill="#1E293B")
            draw.text((bx + 18, 24), status_text, fill="#10B981", font=self.font_bold)

        # 4. Progress bar (Bottom)
        bar_y1 = self.height - self.progress_height
        bar_y2 = self.height
        draw.rectangle([(0, bar_y1), (width, bar_y2)], fill=self.progress_bar_bg)
        progress_w = int(max(0.0, min(1.0, progress_ratio)) * width)
        if progress_w > 0:
            draw.rectangle([(0, bar_y1), (progress_w, bar_y2)], fill=self.progress_bar_color)

        return hud_img


# ---------------------------------------------------------------------------
# Audio helper: add silence padding for answer key / end card
# ---------------------------------------------------------------------------

def create_padded_audio(original_audio_path: Path, padding_sec: float,
                        out_audio_path: Path, sample_rate: int = 44100):
    """Create a new WAV file with additional silence padding appended at the end."""
    if padding_sec <= 0:
        out_audio_path.write_bytes(original_audio_path.read_bytes())
        return

    with wave.open(str(original_audio_path), "rb") as wf:
        nchannels = wf.getnchannels()
        sampwidth = wf.getsampwidth()
        framerate = wf.getframerate()
        frames = wf.readframes(wf.getnframes())

    silence_frames_count = int(padding_sec * framerate) * nchannels
    silence_bytes = b"\x00" * silence_frames_count * sampwidth

    with wave.open(str(out_audio_path), "wb") as wf_out:
        wf_out.setnchannels(nchannels)
        wf_out.setsampwidth(sampwidth)
        wf_out.setframerate(framerate)
        wf_out.writeframes(frames)
        wf_out.writeframes(silence_bytes)


# ---------------------------------------------------------------------------
# Video Generation Pipeline
# ---------------------------------------------------------------------------

def select_screen_for_segment(seg: dict, screens: list[dict]) -> dict:
    """Find the best matching screen for a timeline segment."""
    kind = seg.get("kind", "")
    part_num = seg.get("part")
    q_from = seg.get("q_from")
    q_to = seg.get("q_to")

    # Special screens
    if kind in ("intro", "intro_pause"):
        return next((s for s in screens if s["type"] == "title_card"), screens[0])

    if kind == "end_test":
        return next((s for s in screens if s["type"] == "end_card"), screens[0])

    if kind == "checking":
        # Full part review screen
        match = next((s for s in screens if s["part"] == part_num and s["type"] == "checking"), None)
        if match:
            return match

    # Search for matching question screen
    if part_num is not None:
        if q_from is not None and q_to is not None:
            # Exact range match
            match = next((s for s in screens if s["part"] == part_num and s.get("q_from") == q_from and s.get("q_to") == q_to), None)
            if match:
                return match

            # Sub-range match
            match = next((s for s in screens if s["part"] == part_num and s.get("q_from") is not None and s.get("q_from") <= q_from and s.get("q_to") >= q_to), None)
            if match:
                return match

        # Fallback to any screen for this part
        match = next((s for s in screens if s["part"] == part_num and s["type"] == "questions"), None)
        if match:
            return match

    return screens[0]


def format_timestamp(seconds: float) -> str:
    """Format seconds into MM:SS or HH:MM:SS format."""
    total_sec = int(seconds)
    hours = total_sec // 3600
    mins = (total_sec % 3600) // 60
    secs = total_sec % 60
    if hours > 0:
        return f"{hours:02d}:{mins:02d}:{secs:02d}"
    return f"{mins:02d}:{secs:02d}"


def write_youtube_chapters(test_dir: Path, test_data: dict, timeline: dict,
                           ak_start_time: float | None = None) -> Path:
    """Generate YouTube-compatible chapters.txt and youtube_description.txt."""
    chapters = []
    chapters.append("00:00 - Test Instructions")

    seen_parts = set()
    for seg in timeline.get("segments", []):
        part_num = seg.get("part")
        if part_num is not None and part_num not in seen_parts:
            seen_parts.add(part_num)
            start_ts = format_timestamp(seg["start"])
            chapters.append(f"{start_ts} - Section {part_num}")

    if ak_start_time is not None:
        chapters.append(f"{format_timestamp(ak_start_time)} - Answer Key")

    chapters_path = test_dir / "video" / "chapters.txt"
    chapters_path.write_text("\n".join(chapters) + "\n", encoding="utf-8")
    print(f"\nYouTube Chapters written to: {chapters_path}")
    print("\n".join(chapters))

    try:
        from generate_youtube_description import generate_youtube_description
        generate_youtube_description(test_dir)
        print(f"YouTube Description written to: {test_dir / 'video' / 'youtube_description.txt'}")
    except Exception as e:
        print(f"Note: Could not pre-generate youtube_description.txt: {e}")

    return chapters_path


def generate_video(test_dir: str | Path, fast: bool = False,
                   skip_visuals: bool = False, output_path: str | Path | None = None,
                   force: bool = False):
    """Main video generation coordinator."""
    test_dir = Path(test_dir)
    test_json = test_dir / "test.json"
    if not test_json.exists():
        sys.exit(f"ERROR: {test_json} not found.")

    test_data = json.loads(test_json.read_text(encoding="utf-8"))
    config = load_video_config()
    
    video_dir = test_dir / "video"
    video_dir.mkdir(parents=True, exist_ok=True)
    frames_dir = video_dir / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n{'=' * 60}")
    print(f"IELTS Video Generator")
    print(f"Test Directory : {test_dir}")
    print(f"Title          : {test_data.get('metadata', {}).get('title', 'Unknown')}")
    print(f"Mode           : {'Fast FFmpeg Concat' if fast else 'MoviePy v2'}")
    print(f"{'=' * 60}\n")

    # Step 1: Timeline
    print(">>> Step 1: Timeline Reconstruction")
    timeline = build_timeline(test_dir)
    total_audio_duration = timeline["total_duration"]

    # Step 2: Visuals
    if not skip_visuals:
        print("\n>>> Step 2: Visual Diagrams Generation")
        generate_visuals(test_dir, force=force)

    # Step 3: Screens
    print("\n>>> Step 3: Screen Rendering")
    manifest = render_screens(test_dir, force_visuals=False)
    screens = manifest["screens"]
    screens_cache = {s["file"]: Image.open(s["path"]).convert("RGB") for s in screens}

    # Step 4: Frame Baking
    print("\n>>> Step 4: Baking Video Frames with Dynamic HUD")
    hud = HUDCompositor(config)
    res_w = config.get("resolution", {}).get("width", 1920)

    baked_frames = []  # list of (frame_image_path, duration_seconds)
    frame_counter = 0

    def bake_single_frame(base_img: Image.Image, part_lbl: str, range_lbl: str,
                          status_lbl: str, countdown_val: int | None,
                          prog_ratio: float, duration: float):
        nonlocal frame_counter
        frame_counter += 1
        out_frame_path = frames_dir / f"frame_{frame_counter:05d}.png"

        # Create combined image
        combined = base_img.copy()
        hud_strip = hud.draw_hud(res_w, part_lbl, range_lbl, status_lbl,
                                 countdown_val, prog_ratio)
        combined.paste(hud_strip, (0, 0))
        combined.save(out_frame_path, format="PNG")
        baked_frames.append((str(out_frame_path), round(duration, 4)))

    for seg in timeline["segments"]:
        screen_info = select_screen_for_segment(seg, screens)
        base_img = screens_cache[screen_info["file"]]

        part_num = seg.get("part")
        part_label = f"PART {part_num}" if part_num else "IELTS LISTENING"
        
        q_from = seg.get("q_from")
        q_to = seg.get("q_to")
        if q_from and q_to:
            range_label = f"Questions {q_from}–{q_to}"
        elif screen_info["type"] == "title_card":
            range_label = "Test Overview"
        elif screen_info["type"] == "end_card":
            range_label = "End of Test"
        else:
            range_label = ""

        kind = seg["kind"]
        seg_duration = seg["duration"]
        start_time = seg["start"]
        countdown = seg.get("countdown")

        # Determine status label
        if kind == "prep":
            status_label = "READ QUESTIONS"
        elif kind == "mid_break":
            status_label = "READ NEXT QUESTIONS"
        elif kind == "checking":
            status_label = "CHECK ANSWERS"
        elif "narr" in kind or kind == "intro" or kind == "end_test":
            status_label = "NARRATOR"
        elif "dialogue" in kind:
            status_label = "LISTENING"
        else:
            status_label = "LISTENING"

        if countdown is not None and countdown > 0:
            # Sliced 1-second countdown frames
            num_seconds = int(math.ceil(seg_duration))
            for sec_idx in range(num_seconds):
                chunk_start = start_time + sec_idx
                chunk_dur = min(1.0, seg_duration - sec_idx)
                if chunk_dur <= 0:
                    break
                rem_countdown = max(0, countdown - sec_idx)
                prog = chunk_start / total_audio_duration
                bake_single_frame(base_img, part_label, range_label,
                                  status_label, rem_countdown, prog, chunk_dur)
        else:
            # Static segment
            prog = start_time / total_audio_duration
            bake_single_frame(base_img, part_label, range_label,
                              status_label, None, prog, seg_duration)

    # Post-test Sections (Answer Key & End Card)
    sec_cfg = config.get("sections", {})
    ak_duration = sec_cfg.get("answer_key_duration_sec", 20) if sec_cfg.get("show_answer_key", True) else 0
    end_duration = sec_cfg.get("end_card_duration_sec", 10) if sec_cfg.get("show_end_card", True) else 0
    total_post_test_padding = ak_duration + end_duration

    ak_start_time = total_audio_duration if ak_duration > 0 else None

    if ak_duration > 0:
        ak_screen = next((s for s in screens if s["type"] == "answer_key"), None)
        if ak_screen:
            base_img = screens_cache[ak_screen["file"]]
            num_sec = int(ak_duration)
            for s_idx in range(num_sec):
                rem = max(0, num_sec - s_idx)
                bake_single_frame(base_img, "ANSWER KEY", "Questions 1–40",
                                  "CHECK ANSWERS", rem, 1.0, 1.0)

    if end_duration > 0:
        end_screen = next((s for s in screens if s["type"] == "end_card"), None)
        if end_screen:
            base_img = screens_cache[end_screen["file"]]
            bake_single_frame(base_img, "COMPLETED", "Final Result",
                              "END", None, 1.0, end_duration)

    print(f"Baked {len(baked_frames)} unique video frames.")

    # Prepare Audio with Silence Padding
    raw_audio_path = test_dir / "audio" / "full_test.wav"
    if not raw_audio_path.exists():
        sys.exit(f"ERROR: Audio file {raw_audio_path} does not exist!")

    final_audio_path = video_dir / "full_audio_padded.wav"
    create_padded_audio(raw_audio_path, total_post_test_padding, final_audio_path)

    # Output MP4 Path
    if output_path is None:
        test_slug = test_dir.name
        out_mp4 = video_dir / f"{test_slug}.mp4"
    else:
        out_mp4 = Path(output_path)

    # Step 5: Encoding
    print(f"\n>>> Step 5: Video Encoding -> {out_mp4}")
    fps = config.get("fps", 10)

    if fast:
        # Fast FFmpeg Concat Demuxer
        concat_file = video_dir / "concat_list.txt"
        with open(concat_file, "w", encoding="utf-8") as f:
            f.write("ffconcat version 1.0\n")
            for frame_p, dur in baked_frames:
                clean_p = Path(frame_p).resolve().as_posix()
                f.write(f"file '{clean_p}'\n")
                f.write(f"duration {dur:.4f}\n")
            # Repeat last file for ffmpeg concat bug workaround
            if baked_frames:
                clean_p = Path(baked_frames[-1][0]).resolve().as_posix()
                f.write(f"file '{clean_p}'\n")

        cmd = [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "info",
            "-f", "concat", "-safe", "0", "-i", str(concat_file),
            "-i", str(final_audio_path),
            "-c:v", "libx264", "-tune", "stillimage",
            "-pix_fmt", "yuv420p", "-crf", "23",
            "-c:a", "aac", "-b:a", "192k",
            "-shortest",
            str(out_mp4)
        ]
        print("Running FFmpeg fast muxing...")
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode != 0:
            print(f"FFmpeg Error:\n{res.stderr}")
            sys.exit("Video rendering failed in FFmpeg.")
    else:
        # MoviePy v2 Pipeline
        print("Rendering via MoviePy v2...")
        from moviepy import ImageClip, AudioFileClip, concatenate_videoclips

        clips = [ImageClip(frame_p).with_duration(dur) for frame_p, dur in baked_frames]
        video = concatenate_videoclips(clips, method="chain").with_audio(AudioFileClip(str(final_audio_path)))
        video.write_videofile(
            str(out_mp4),
            fps=fps,
            codec="libx264",
            audio_codec="aac",
            preset="veryfast",
            ffmpeg_params=["-tune", "stillimage", "-pix_fmt", "yuv420p", "-crf", "23"]
        )

    print(f"\nSUCCESS! Video generated: {out_mp4}")

    # Step 6: YouTube Chapters
    print("\n>>> Step 6: Writing YouTube Chapters")
    write_youtube_chapters(test_dir, test_data, timeline, ak_start_time)

    # Step 7: YouTube Thumbnail
    print("\n>>> Step 7: Generating YouTube Thumbnail")
    try:
        from generate_thumbnail import generate_thumbnail
        generate_thumbnail(test_dir)
    except Exception as e:
        print(f"Warning: Thumbnail generation failed: {e}")

    return out_mp4



if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="IELTS Listening Test Video Renderer")
    parser.add_argument("test_dir", help="Path to test directory (e.g. tests/test_007)")
    parser.add_argument("--fast", action="store_true", help="Use fast FFmpeg concat muxer")
    parser.add_argument("--skip-visuals", action="store_true", help="Skip calling visual generation")
    parser.add_argument("--output", help="Custom output MP4 path")
    parser.add_argument("--force", action="store_true", help="Force regenerate cached screens/visuals")

    args = parser.parse_args()
    generate_video(
        test_dir=args.test_dir,
        fast=args.fast,
        skip_visuals=args.skip_visuals,
        output_path=args.output,
        force=args.force
    )
