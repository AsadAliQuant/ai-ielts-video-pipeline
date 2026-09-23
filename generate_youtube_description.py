#!/usr/bin/env python3
"""
Generate YouTube Description for IELTS Listening Test Videos.

100% deterministic, zero LLM / AI calls.
Builds the description from:
- Exact exam instructions spoken at the start (from audio_config.json or canonical IELTS prompt)
- Video chapter timestamps (from chapters.txt or timeline.json)
- Standard IELTS Listening Band Score Conversion table
- Engagement hooks & hashtags

Usage:
    python generate_youtube_description.py tests/test_003
    python generate_youtube_description.py tests/test_003 --print
"""

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# Canonical spoken start script used across all tests as the fallback
DEFAULT_START_SCRIPT = (
    "This is the IELTS Listening test. You will hear four different recordings "
    "and you will have to answer questions on what you hear. There will be time "
    "for you to read the instructions and questions, and you will have a chance "
    "to check your work. You will hear each recording once only. The test is in "
    "four parts. At the end of the test, you will be given two minutes to check "
    "all of your answers."
)

DEFAULT_TIMESTAMPS = (
    "00:00 - Test Instructions\n"
    "00:45 - Section 1\n"
    "07:30 - Section 2\n"
    "14:15 - Section 3\n"
    "22:00 - Section 4\n"
    "28:30 - Answer Key"
)


def get_start_script(config_path: Path | None = None) -> str:
    """Retrieve the exact start script spoken by the narrator at test beginning."""
    cfg_file = config_path or (ROOT / "audio_config.json")
    if cfg_file.exists():
        try:
            cfg = json.loads(cfg_file.read_text(encoding="utf-8"))
            intro = cfg.get("narrator_scripts", {}).get("intro")
            if intro and intro.strip():
                return intro.strip()
        except Exception:
            pass
    return DEFAULT_START_SCRIPT


def get_timestamps(test_dir: Path) -> str:
    """Extract and format section timestamps from chapters.txt, timeline.json, or fallback."""
    chapters_path = test_dir / "video" / "chapters.txt"
    if not chapters_path.exists():
        chapters_path = test_dir / "chapters.txt"

    if chapters_path.exists():
        raw_lines = [
            line.strip()
            for line in chapters_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        formatted_lines = []
        for line in raw_lines:
            m = re.match(r"^(\d+:\d+(?::\d+)?)\s*[-–—]?\s*(.*)$", line)
            if m:
                ts_raw, title_raw = m.group(1), m.group(2).strip()
                parts = [int(p) for p in ts_raw.split(":")]
                if len(parts) == 2:
                    ts = f"{parts[0]:02d}:{parts[1]:02d}"
                elif len(parts) == 3:
                    ts = f"{parts[0]:02d}:{parts[1]:02d}:{parts[2]:02d}"
                else:
                    ts = ts_raw

                t_lower = title_raw.lower()
                if "intro" in t_lower or "instruction" in t_lower:
                    title = "Test Instructions"
                elif "part 1" in t_lower or "section 1" in t_lower:
                    title = "Section 1"
                elif "part 2" in t_lower or "section 2" in t_lower:
                    title = "Section 2"
                elif "part 3" in t_lower or "section 3" in t_lower:
                    title = "Section 3"
                elif "part 4" in t_lower or "section 4" in t_lower:
                    title = "Section 4"
                elif "answer" in t_lower:
                    title = "Answer Key"
                else:
                    title = title_raw

                formatted_lines.append(f"{ts} - {title}")
            else:
                formatted_lines.append(line)
        if formatted_lines:
            return "\n".join(formatted_lines)

    # Fallback to timeline.json if chapters.txt does not exist
    timeline_path = test_dir / "video" / "timeline.json"
    if not timeline_path.exists():
        timeline_path = test_dir / "timeline.json"

    if timeline_path.exists():
        try:
            timeline = json.loads(timeline_path.read_text(encoding="utf-8"))
            lines = ["00:00 - Test Instructions"]
            seen_parts = set()
            for seg in timeline.get("segments", []):
                p = seg.get("part")
                if p is not None and p not in seen_parts:
                    seen_parts.add(p)
                    total_sec = int(seg.get("start", 0))
                    hours = total_sec // 3600
                    mins = (total_sec % 3600) // 60
                    secs = total_sec % 60
                    ts = f"{hours:02d}:{mins:02d}:{secs:02d}" if hours > 0 else f"{mins:02d}:{secs:02d}"
                    lines.append(f"{ts} - Section {p}")
            total_duration = timeline.get("total_duration")
            if total_duration:
                total_sec = int(total_duration)
                hours = total_sec // 3600
                mins = (total_sec % 3600) // 60
                secs = total_sec % 60
                ts = f"{hours:02d}:{mins:02d}:{secs:02d}" if hours > 0 else f"{mins:02d}:{secs:02d}"
                lines.append(f"{ts} - Answer Key")
            return "\n".join(lines)
        except Exception:
            pass

    return DEFAULT_TIMESTAMPS


def build_description_text(test_dir: Path, video_date=None) -> str:
    """Build the complete, formatted YouTube video description string without any AI calls."""
    timestamps = get_timestamps(test_dir)
    start_script = get_start_script()

    date_line = ""
    if video_date:
        # Portable day without leading zero (strftime %-d is Linux-only)
        date_line = f"\U0001F4C5 Test date: {video_date.day} {video_date.strftime('%B %Y')}\n\n"

    description = (
        f"{date_line}"
        "Practice your IELTS Listening test under real exam conditions with this complete practice session (Academic & General Training). "
        "Boost your band score with authentic timing, questions, and an official answer key at the end.\n\n"
        "🎧 For the best test experience, use headphones and write your answers down as you listen.\n\n"
        "⏱️ Timestamps:\n"
        f"{timestamps}\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "📌 TEST INSTRUCTIONS TO CANDIDATES\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{start_script}\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "📊 IELTS LISTENING BAND SCORE CONVERSION\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "Correct Answers  ➔  Band Score\n"
        "• 39–40  ➔  Band 9.0\n"
        "• 37–38  ➔  Band 8.5\n"
        "• 35–36  ➔  Band 8.0\n"
        "• 32–34  ➔  Band 7.5\n"
        "• 30–31  ➔  Band 7.0\n"
        "• 26–29  ➔  Band 6.5\n"
        "• 23–25  ➔  Band 6.0\n"
        "• 18–22  ➔  Band 5.5\n"
        "• 16–17  ➔  Band 5.0\n"
        "• 13–15  ➔  Band 4.5\n"
        "• 10–12  ➔  Band 4.0\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "💬 How many questions did you get right? Drop your score in the comments below! \n"
        "🔔 Don't forget to LIKE and SUBSCRIBE for more daily IELTS Listening tests and preparation materials.\n\n"
        "#IELTS #IELTSListening #IELTSPracticeTest #IELTS2026 #Band8 #Band9 #IELTSListeningTest"
    )
    return description


def generate_youtube_description(test_dir: str | Path, output_file: str | Path | None = None,
                                 video_date=None) -> str:
    """Generate and save the YouTube description to video/youtube_description.txt."""
    test_path = Path(test_dir)
    desc = build_description_text(test_path, video_date=video_date)

    if output_file:
        out_path = Path(output_file)
    else:
        out_path = test_path / "video" / "youtube_description.txt"

    try:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(desc, encoding="utf-8")
    except Exception as e:
        print(f"Warning: could not write description file {out_path}: {e}")

    return desc


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("test_dir", help="Path to test directory (e.g. tests/test_003)")
    parser.add_argument("--output", "-o", help="Custom output path for description text file", default=None)
    parser.add_argument("--print", "-p", action="store_true", help="Print description to stdout")

    args = parser.parse_args()
    test_dir = Path(args.test_dir)

    desc = generate_youtube_description(test_dir, output_file=args.output)
    target_out = args.output or (test_dir / "video" / "youtube_description.txt")
    print(f"Saved YouTube description to: {target_out}")

    if args.print:
        print("\n" + "=" * 60)
        print(desc)
        print("=" * 60)


if __name__ == "__main__":
    main()
