#!/usr/bin/env python3
"""
IELTS Listening Test — Batch Pipeline Generator.

Automates running the IELTS Listening Test pipeline (Stage 1 Test Paper, 
Stage 2 Audio Synthesis, Stage 3 Video Rendering) for multiple tests in batch.

Usage:
    python batch_generate.py 3                             # Generate 3 complete IELTS tests
    python batch_generate.py --count 5 --band 7.5          # Generate 5 tests for Band 7.5
    python batch_generate.py 2 --skip-verify --fast        # 2 tests with fast video muxing
    python batch_generate.py 3 --stage 1                  # Generate 3 test papers only (Stage 1)
    python batch_generate.py 2 --provider nvidia           # Use NVIDIA NIM instead of Gemini
    python batch_generate.py 3 --dry-run                   # Show planned commands without executing
"""

import argparse
import os
import re
import subprocess
import sys
import time
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def get_existing_test_dirs(base_dir: Path) -> set:
    """Return set of existing test_NNN directory paths under base_dir."""
    if not base_dir.exists():
        return set()
    return {
        p for p in base_dir.iterdir()
        if p.is_dir() and re.fullmatch(r"test_\d+", p.name)
    }


def find_latest_test_dir(base_dir: Path) -> Path:
    """Find the test_NNN directory with the highest numerical index."""
    test_dirs = get_existing_test_dirs(base_dir)
    if not test_dirs:
        sys.exit(f"ERROR: No test_NNN directories found under {base_dir}")
    
    def get_num(p: Path) -> int:
        m = re.fullmatch(r"test_(\d+)", p.name)
        return int(m.group(1)) if m else -1

    return max(test_dirs, key=get_num)


def extract_visual_prompts(visuals_md_path: Path):
    """Parse visuals.md to extract visual ID, title, type, and GenAI image prompt."""
    if not visuals_md_path.exists():
        return []

    content = visuals_md_path.read_text(encoding="utf-8")
    visuals = []

    sections = re.split(r"^##\s+", content, flags=re.MULTILINE)
    for sec in sections[1:]:
        lines = sec.strip().splitlines()
        header = lines[0] if lines else ""

        v_type = re.search(r"\*\*Type:\*\*\s*(.+)", sec)
        v_title = re.search(r"\*\*Title:\*\*\s*(.+)", sec)
        v_prompt = re.search(r"\*\*GenAI image prompt\*\*\s*\n\n(.*?)(?=\n\n\*\*|\Z)", sec, re.DOTALL)

        type_str = v_type.group(1).strip() if v_type else "image"
        title_str = v_title.group(1).strip() if v_title else "Diagram"

        if v_prompt:
            prompt_text = v_prompt.group(1).strip()
            if type_str.lower() not in ["flowchart", "table"]:
                vid_m = re.search(r"\b(v\d+)\b", header)
                vid = vid_m.group(1) if vid_m else "v1"
                visuals.append({
                    "id": vid,
                    "header": header,
                    "type": type_str,
                    "title": title_str,
                    "prompt": prompt_text
                })

    return visuals


def handle_chatgpt_visuals(test_dir: Path, dry_run: bool = False):
    """Check visuals.md, display prompts, and pause for image placement."""
    if dry_run:
        print(f"  (dry-run: would prompt for ChatGPT visual in {test_dir.name})")
        return

    visuals_md = test_dir / "visuals.md"
    visuals = extract_visual_prompts(visuals_md)

    if not visuals:
        print("\n[INFO] No image visuals required for this test.")
        return

    visuals_dir = test_dir / "visuals"
    visuals_dir.mkdir(parents=True, exist_ok=True)

    for vis in visuals:
        vid = vis["id"]
        target_path = visuals_dir / f"{vid}.png"
        root_target_path = test_dir / f"visual_{vid}.png"

        print("\n" + "=" * 76)
        print(f"  IMAGE PROMPT FOR CHATGPT: {vis['title'].upper()} ({vis['type'].upper()})")
        print("=" * 76)
        print(f"Section     : {vis['header']}")
        print(f"Visual ID   : {vid}")
        print("\nPrompt to copy into ChatGPT:")
        print("-" * 76)
        print(vis['prompt'])
        print("-" * 76)
        print(f"\nTarget File Destination:")
        print(f"  {target_path}")
        print("=" * 76)

        while True:
            prompt_msg = (
                f"\nOptions:\n"
                f"  1. Paste or drag-and-drop the downloaded image path below\n"
                f"  2. OR save the file directly to: {target_path} and press Enter\n"
                f"  3. OR press Enter if downloaded to your Downloads folder\n"
                f"> Input path or press Enter: "
            )
            raw_input = input(prompt_msg).strip().strip('"').strip("'")

            if raw_input:
                src_path = Path(raw_input)
                if src_path.exists() and src_path.is_file():
                    shutil.copy(src_path, target_path)
                    shutil.copy(src_path, root_target_path)
                    print(f"\n[OK] Copied {src_path.name} -> {target_path}")
                    break
                else:
                    print(f"\n[ERROR] File not found at: {src_path}")
                    continue

            if target_path.exists() and target_path.stat().st_size > 0:
                shutil.copy(target_path, root_target_path)
                print(f"\n[OK] Found image at {target_path}")
                break

            downloads_dir = Path.home() / "Downloads"
            found_download = None
            if downloads_dir.exists():
                candidates = sorted(
                    [p for p in downloads_dir.glob("*.*") if p.suffix.lower() in [".png", ".jpg", ".jpeg"]],
                    key=lambda p: p.stat().st_mtime,
                    reverse=True
                )
                if candidates:
                    recent = candidates[0]
                    if time.time() - recent.stat().st_mtime < 1800:
                        found_download = recent

            if found_download:
                confirm = input(f"\nFound recent image in Downloads: '{found_download.name}'. Use this? [Y/n]: ").strip().lower()
                if confirm in ["", "y", "yes"]:
                    shutil.copy(found_download, target_path)
                    shutil.copy(found_download, root_target_path)
                    print(f"\n[OK] Copied {found_download.name} -> {target_path}")
                    break

            print(f"\n[WAITING] Image not found yet at {target_path}. Please place or paste it.")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Batch generate IELTS Listening tests using the 3-stage pipeline.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "pos_count",
        nargs="?",
        type=int,
        default=None,
        help="Number of IELTS tests to generate (positional override for --count)",
    )
    parser.add_argument(
        "--count", "-n",
        type=int,
        default=1,
        help="Number of IELTS tests to generate",
    )
    
    # Stage 1 options (generate_test.py)
    g_stage1 = parser.add_argument_group("Stage 1 (Test Paper Generation)")
    g_stage1.add_argument("--band", default="9.0", help="Target band score (e.g. 7.0, 7.5)")
    g_stage1.add_argument("--difficulty", default="", help='Difficulty label (defaults to "IELTS <band>")')
    g_stage1.add_argument("--context", default="academic", choices=["academic", "general"], help="Test context")
    g_stage1.add_argument("--topics", default="", help="Comma-separated topic hints for the 4 parts")
    g_stage1.add_argument("--provider", default="gemini", choices=["nvidia", "gemini"], help="LLM API provider")
    g_stage1.add_argument("--model", default="deepseek-ai/deepseek-v4-flash-0731", help="NVIDIA NIM model ID")
    g_stage1.add_argument("--gemini-model", default="gemini-3.5-flash-lite", help="Gemini model ID")
    g_stage1.add_argument("--skip-verify", action="store_true", help="Skip LLM verification agent pass (faster)")

    # Pipeline controls
    g_pipeline = parser.add_argument_group("Pipeline Controls")
    g_pipeline.add_argument(
        "--stage", "--stages",
        dest="max_stage",
        default="all",
        choices=["1", "2", "3", "test", "audio", "video", "all"],
        help="Maximum stage to run (1/test = paper only; 2/audio = test+audio; 3/video/all = full pipeline)",
    )
    g_pipeline.add_argument("--out", default="tests", help="Output base directory")
    g_pipeline.add_argument("--stop-on-error", action="store_true", help="Stop batch execution immediately if any stage fails")
    g_pipeline.add_argument("--dry-run", action="store_true", help="Print planned commands without running them")

    # Stage 2 options (generate_audio.py)
    g_stage2 = parser.add_argument_group("Stage 2 (Audio Synthesis)")
    g_stage2.add_argument("--format", default="wav", choices=["wav", "mp3"], help="Output audio format")

    # Stage 3 options (generate_video.py)
    g_stage3 = parser.add_argument_group("Stage 3 (Video Rendering)")
    g_stage3.add_argument("--fast", action="store_true", help="Use fast FFmpeg concat muxer for Stage 3 video")
    g_stage3.add_argument("--skip-visuals", action="store_true", help="Skip calling visual map/diagram generation")

    # Stage 4 options (youtube_upload.py)
    g_stage4 = parser.add_argument_group("Stage 4 (YouTube Upload)")
    g_stage4.add_argument("--upload", action="store_true", help="Upload rendered video to YouTube (Stage 4)")

    # Visual controls
    g_visual = parser.add_argument_group("Visuals")
    g_visual.add_argument("--chatgpt", "--interactive-visual", dest="chatgpt", action="store_true", help="Pause after Stage 1 to display prompt for ChatGPT and place image")

    args = parser.parse_args(argv)

    # Positional count takes precedence if given
    if args.pos_count is not None:
        args.count = args.pos_count

    if args.count < 1:
        parser.error("Count must be at least 1")

    # Map stage choices to numerical max stage (1, 2, 3, or 4)
    stage_map = {
        "1": 1, "test": 1,
        "2": 2, "audio": 2,
        "3": 3, "video": 3,
        "4": 4, "upload": 4,
        "all": 4 if args.upload else 3,
    }
    if args.upload and args.max_stage in ["all", "3", "video"]:
        args.target_stage = 4
    else:
        args.target_stage = stage_map.get(args.max_stage, 3)

    return args


def run_command(cmd, dry_run=False):
    """Run command with live stdout/stderr printing and return exit code."""
    cmd_str = " ".join(f'"{arg}"' if " " in str(arg) else str(arg) for arg in cmd)
    print(f"\n[EXEC] {cmd_str}\n")
    if dry_run:
        print("  (dry-run: command skipped)")
        return 0
    
    start_t = time.time()
    res = subprocess.run(cmd, cwd=str(ROOT))
    elapsed = time.time() - start_t
    print(f"\n[DONE] Exit code {res.returncode} ({elapsed:.1f}s)")
    return res.returncode


def main(argv=None):
    args = parse_args(argv)
    out_base = Path(args.out).resolve() if Path(args.out).is_absolute() else ROOT / args.out

    print("=" * 70)
    print(f" IELTS Listening Test Batch Pipeline Generator")
    print(f" Total tests to generate : {args.count}")
    print(f" Target Band            : {args.band}")
    print(f" Target Stage           : Stage {args.target_stage} ({'Full Pipeline' if args.target_stage == 3 else 'Stage 1..' + str(args.target_stage)})")
    print(f" LLM Provider           : {args.provider}")
    print(f" Output Directory       : {out_base}")
    if args.dry_run:
        print(" MODE                   : DRY RUN (No actual execution)")
    print("=" * 70)

    success_count = 0
    start_batch_t = time.time()

    for i in range(1, args.count + 1):
        print(f"\n" + "#" * 70)
        print(f" RUNNING TEST {i}/{args.count}")
        print("#" * 70)

        existing_before = get_existing_test_dirs(out_base)

        # -------------------------------------------------------------------
        # Stage 1: generate_test.py
        # -------------------------------------------------------------------
        print(f"\n>>> [Test {i}/{args.count}] STAGE 1: Generating Test Paper")
        cmd_stage1 = [
            sys.executable, "-u", str(ROOT / "generate_test.py"),
            "--band", str(args.band),
            "--provider", args.provider,
            "--out", str(args.out),
        ]
        if args.difficulty:
            cmd_stage1.extend(["--difficulty", args.difficulty])
        if args.context:
            cmd_stage1.extend(["--context", args.context])
        if args.topics:
            cmd_stage1.extend(["--topics", args.topics])
        if args.model:
            cmd_stage1.extend(["--model", args.model])
        if args.gemini_model:
            cmd_stage1.extend(["--gemini-model", args.gemini_model])
        if args.skip_verify:
            cmd_stage1.append("--skip-verify")

        ret1 = run_command(cmd_stage1, dry_run=args.dry_run)
        if ret1 != 0:
            print(f"[FAIL] Stage 1 failed for Test {i}/{args.count}")
            if args.stop_on_error:
                sys.exit(f"Stopping batch execution due to Stage 1 error.")
            continue

        if args.dry_run:
            test_dir = out_base / f"test_{i:03d} (simulated)"
        else:
            existing_after = get_existing_test_dirs(out_base)
            new_dirs = existing_after - existing_before
            if len(new_dirs) == 1:
                test_dir = list(new_dirs)[0]
            else:
                test_dir = find_latest_test_dir(out_base)
            print(f"[OK] Test paper generated at: {test_dir}")

        # -------------------------------------------------------------------
        # Visual Prompt Hook (if --chatgpt specified)
        # -------------------------------------------------------------------
        if args.chatgpt:
            handle_chatgpt_visuals(test_dir, dry_run=args.dry_run)

        # -------------------------------------------------------------------
        # Stage 2: generate_audio.py (if stage >= 2)
        # -------------------------------------------------------------------
        if args.target_stage >= 2:
            print(f"\n>>> [Test {i}/{args.count}] STAGE 2: Synthesizing TTS Audio ({test_dir.name})")
            cmd_stage2 = [
                sys.executable, str(ROOT / "generate_audio.py"),
                str(test_dir),
                "--format", args.format,
            ]
            ret2 = run_command(cmd_stage2, dry_run=args.dry_run)
            if ret2 != 0:
                print(f"[FAIL] Stage 2 failed for {test_dir.name}")
                if args.stop_on_error:
                    sys.exit(f"Stopping batch execution due to Stage 2 error.")
                continue
            if not args.dry_run:
                print(f"[OK] Audio synthesized for: {test_dir.name}")

        # -------------------------------------------------------------------
        # Stage 3: generate_video.py (if stage >= 3)
        # -------------------------------------------------------------------
        if args.target_stage >= 3:
            print(f"\n>>> [Test {i}/{args.count}] STAGE 3: Rendering Video & Chapters ({test_dir.name})")
            cmd_stage3 = [
                sys.executable, str(ROOT / "generate_video.py"),
                str(test_dir),
            ]
            if args.fast:
                cmd_stage3.append("--fast")
            if args.skip_visuals:
                cmd_stage3.append("--skip-visuals")

            ret3 = run_command(cmd_stage3, dry_run=args.dry_run)
            if ret3 != 0:
                print(f"[FAIL] Stage 3 failed for {test_dir.name}")
                if args.stop_on_error:
                    sys.exit(f"Stopping batch execution due to Stage 3 error.")
                continue
            if not args.dry_run:
                print(f"[OK] Video rendered for: {test_dir.name}")

        # -------------------------------------------------------------------
        # Stage 4: youtube_upload.py (if stage >= 4 or --upload)
        # -------------------------------------------------------------------
        if args.target_stage >= 4 or args.upload:
            print(f"\n>>> [Test {i}/{args.count}] STAGE 4: Uploading to YouTube ({test_dir.name})")
            cmd_stage4 = [
                sys.executable, str(ROOT / "youtube_upload.py"),
                str(test_dir),
            ]
            ret4 = run_command(cmd_stage4, dry_run=args.dry_run)
            if ret4 != 0:
                print(f"[FAIL] Stage 4 YouTube upload failed for {test_dir.name}")
                if args.stop_on_error:
                    sys.exit(f"Stopping batch execution due to Stage 4 error.")
                continue
            if not args.dry_run:
                print(f"[OK] Video uploaded to YouTube for: {test_dir.name}")

        success_count += 1
        print(f"\n[SUCCESS] Completed Test {i}/{args.count}: {test_dir.name}")

    total_time = time.time() - start_batch_t
    print("\n" + "=" * 70)
    print(f" BATCH GENERATION COMPLETE")
    print(f" Successfully processed: {success_count}/{args.count} test(s)")
    print(f" Total Batch Duration  : {total_time/60:.1f} minutes ({total_time:.0f}s)")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit("\nBatch generation interrupted by user.")
