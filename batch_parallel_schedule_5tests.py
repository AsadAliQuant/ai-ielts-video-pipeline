#!/usr/bin/env python3
"""
Batch Parallel & Scheduled YouTube Pipeline for 5 IELTS Tests (test_017 through test_021).
Schedules tests from 26-Sep-2026 to 30-Sep-2026 at 08:00 AM each day.
Incremented dates on thumbnails and YouTube video titles.

Usage:
    python batch_parallel_schedule_5tests.py stage1       # Run parallel test paper generation
    python batch_parallel_schedule_5tests.py prompts      # Display & export image prompts for ChatGPT
    python batch_parallel_schedule_5tests.py check        # Check status of pasted ChatGPT images
    python batch_parallel_schedule_5tests.py resume       # Run Audio, Video, Thumbnails, and Scheduled YouTube Uploads
"""

import argparse
import datetime
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent

TEST_SCHEDULE = [
    {
        "test": "test_017",
        "date": "2026-09-26T08:00:00+05:00",
        "title_date": "26.09.2026",
        "date_text": "26/Sep/2026",
    },
    {
        "test": "test_018",
        "date": "2026-09-27T08:00:00+05:00",
        "title_date": "27.09.2026",
        "date_text": "27/Sep/2026",
    },
    {
        "test": "test_019",
        "date": "2026-09-28T08:00:00+05:00",
        "title_date": "28.09.2026",
        "date_text": "28/Sep/2026",
    },
    {
        "test": "test_020",
        "date": "2026-09-29T08:00:00+05:00",
        "title_date": "29.09.2026",
        "date_text": "29/Sep/2026",
    },
    {
        "test": "test_021",
        "date": "2026-09-30T08:00:00+05:00",
        "title_date": "30.09.2026",
        "date_text": "30/Sep/2026",
    },
]


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
                    "prompt": prompt_text,
                })

    return visuals


def run_stage1_parallel(band="9.0", skip_verify=True, provider="gemini"):
    """Run Stage 1 for test_017 through test_021 simultaneously."""
    print("=" * 75)
    print(" STARTING PARALLEL STAGE 1 GENERATION FOR 5 TESTS (test_017 .. test_021)")
    print(f" Target Band: {band} | Provider: {provider} | Skip Verify: {skip_verify}")
    print("=" * 75)

    processes = []
    log_files = []

    for i, item in enumerate(TEST_SCHEDULE):
        test_name = item["test"]
        test_dir = ROOT / "tests" / test_name
        test_dir.mkdir(parents=True, exist_ok=True)
        log_path = test_dir / "stage1.log"
        log_f = open(log_path, "w", encoding="utf-8")
        log_files.append(log_f)

        cmd = [
            sys.executable, "-u", str(ROOT / "generate_test.py"),
            "--test-dir", str(test_dir),
            "--band", str(band),
            "--provider", provider,
            "--key-offset", str(i),
        ]
        if skip_verify:
            cmd.append("--skip-verify")

        print(f"Launching worker {i+1}/5: {test_name} (key offset: {i})...")
        proc = subprocess.Popen(
            cmd,
            stdout=log_f,
            stderr=subprocess.STDOUT,
            cwd=str(ROOT),
        )
        processes.append((test_name, proc, log_path))

    print(f"\nAll 5 workers launched! Monitoring progress...")

    active = list(processes)
    start_time = time.time()

    while active:
        time.sleep(5)
        still_running = []
        for test_name, proc, log_path in active:
            ret = proc.poll()
            if ret is None:
                still_running.append((test_name, proc, log_path))
            else:
                elapsed = time.time() - start_time
                status = "SUCCESS" if ret == 0 else f"FAILED (exit code {ret})"
                print(f"[{status}] {test_name} finished in {elapsed/60:.1f} min. Log: {log_path.name}")
        active = still_running

    for f in log_files:
        try:
            f.close()
        except Exception:
            pass

    print("\n" + "=" * 75)
    print(" ALL 5 STAGE 1 WORKERS COMPLETED")
    print("=" * 75)

    # Collect and display all visual prompts
    collect_and_display_prompts()


def collect_and_display_prompts():
    """Extract visual prompts from each test and format for ChatGPT generation."""
    all_prompts = []

    for item in TEST_SCHEDULE:
        test_name = item["test"]
        test_dir = ROOT / "tests" / test_name
        visuals_md = test_dir / "visuals.md"
        visuals = extract_visual_prompts(visuals_md)

        # Fallback to test.json if visuals.md is empty or missing
        if not visuals:
            test_json = test_dir / "test.json"
            if test_json.exists():
                try:
                    t_data = json.loads(test_json.read_text(encoding="utf-8"))
                    for part in t_data.get("parts", []):
                        for v in part.get("visuals", []):
                            v_type = v.get("type", "")
                            if v_type.lower() not in ["flowchart", "table"]:
                                all_prompts.append({
                                    "test": test_name,
                                    "id": v.get("id", "v1"),
                                    "title": v.get("title", "Diagram"),
                                    "type": v_type,
                                    "part": f"PART {part.get('part', 2)}",
                                    "prompt": v.get("genai_prompt") or v.get("prompt", ""),
                                    "dest": str(test_dir / "visuals" / f"{v.get('id', 'v1')}.png"),
                                })
                except Exception:
                    pass
        else:
            for v in visuals:
                all_prompts.append({
                    "test": test_name,
                    "id": v["id"],
                    "title": v["title"],
                    "type": v["type"],
                    "part": v["header"],
                    "prompt": v["prompt"],
                    "dest": str(test_dir / "visuals" / f"{v['id']}.png"),
                })

    print("\n" + "#" * 75)
    print(" EXTRACTED IMAGE PROMPTS FOR CHATGPT GENERATION")
    print("#" * 75)

    if not all_prompts:
        print("No image visuals required for these tests!")
        return

    output_summary = []
    output_summary.append("# IELTS Test Visual Image Prompts for ChatGPT\n")
    output_summary.append("Copy each prompt into ChatGPT, download the image, and save/paste it to the Destination File.\n")

    for p in all_prompts:
        block = (
            f"### [{p['test']}] {p['title']} ({p['type'].upper()})\n"
            f"- **Visual ID**: `{p['id']}`\n"
            f"- **Section**: {p['part']}\n"
            f"- **Destination File**: `{p['dest']}`\n\n"
            f"**Prompt to copy into ChatGPT:**\n"
            f"```text\n{p['prompt']}\n```\n\n"
            f"---"
        )
        print("\n" + block)
        output_summary.append(block)

    summary_file = ROOT / "visual_prompts_for_user.md"
    summary_file.write_text("\n".join(output_summary), encoding="utf-8")
    print(f"\nSaved all prompts to: {summary_file}")


def check_and_sync_visuals():
    """Ensure images in visuals/v1.png and visual_v1.png are synchronized."""
    print("\n" + "=" * 75)
    print(" CHECKING STATUS OF CHATGPT VISUAL IMAGES")
    print("=" * 75)
    all_ready = True
    for item in TEST_SCHEDULE:
        test_name = item["test"]
        test_dir = ROOT / "tests" / test_name
        visuals_dir = test_dir / "visuals"
        v1_path = visuals_dir / "v1.png"
        root_v1_path = test_dir / "visual_v1.png"

        # Check if test has visual requirement
        visuals_md = test_dir / "visuals.md"
        prompts = extract_visual_prompts(visuals_md)
        if not prompts:
            print(f"[{test_name}] No diagram image required (table/flowchart/none).")
            continue

        for p in prompts:
            vid = p["id"]
            target_v = visuals_dir / f"{vid}.png"
            target_root = test_dir / f"visual_{vid}.png"

            # Sync if one exists and the other doesn't or has smaller size
            if target_v.exists() and target_v.stat().st_size > 5000:
                if not target_root.exists() or target_root.stat().st_size != target_v.stat().st_size:
                    shutil.copy(target_v, target_root)
                print(f"[{test_name}] OK: Found {target_v.name} ({target_v.stat().st_size // 1024} KB)")
            elif target_root.exists() and target_root.stat().st_size > 5000:
                visuals_dir.mkdir(parents=True, exist_ok=True)
                shutil.copy(target_root, target_v)
                print(f"[{test_name}] OK: Synced from {target_root.name} to {target_v.name}")
            else:
                print(f"[{test_name}] MISSING: Please place image at: {target_v}")
                all_ready = False

    return all_ready


def run_stages_2_to_4():
    """Run Stage 2 (Audio), Stage 3 (Video), Thumbnail, and Stage 4 (Upload) sequentially."""
    print("=" * 75)
    print(" PROCEEDING TO STAGES 2, 3, AND 4 (AUDIO, VIDEO, THUMBNAILS, SCHEDULED UPLOADS)")
    print("=" * 75)

    # First synchronize any visuals
    check_and_sync_visuals()

    for item in TEST_SCHEDULE:
        test_name = item["test"]
        publish_at = item["date"]
        date_text = item["date_text"]
        test_dir = ROOT / "tests" / test_name

        if not test_dir.exists():
            print(f"[ERROR] Test directory {test_dir} does not exist. Skipping.")
            continue

        print(f"\n" + "#" * 75)
        print(f" PROCESSING {test_name} (Scheduled for {publish_at} | Thumbnail date: {date_text})")
        print("#" * 75)

        # Stage 2: Audio
        full_audio = test_dir / "audio" / "full_test.wav"
        if full_audio.exists() and full_audio.stat().st_size > 10000000:
            print(f">>> [{test_name}] STAGE 2: full_test.wav already exists ({full_audio.stat().st_size // 1024 // 1024} MB). Skipping synthesis.")
        else:
            print(f"\n>>> [{test_name}] STAGE 2: Synthesizing Audio...")
            cmd_audio = [sys.executable, "-u", str(ROOT / "generate_audio.py"), str(test_dir)]
            res = subprocess.run(cmd_audio, cwd=str(ROOT))
            if res.returncode != 0:
                print(f"[ERROR] Stage 2 failed for {test_name}")
                continue

        # Stage 3: Video
        out_mp4 = test_dir / "video" / f"{test_name}.mp4"
        if out_mp4.exists() and out_mp4.stat().st_size > 10000000:
            print(f">>> [{test_name}] STAGE 3: {out_mp4.name} already rendered ({out_mp4.stat().st_size // 1024 // 1024} MB). Skipping render.")
        else:
            print(f"\n>>> [{test_name}] STAGE 3: Rendering Video & HUD...")
            cmd_video = [sys.executable, "-u", str(ROOT / "generate_video.py"), str(test_dir), "--fast"]
            res = subprocess.run(cmd_video, cwd=str(ROOT))
            if res.returncode != 0:
                print(f"[ERROR] Stage 3 failed for {test_name}")
                continue

        # Generate custom thumbnail with exact scheduled date badge
        print(f"\n>>> [{test_name}] Generating thumbnail with scheduled date '{date_text}'...")
        try:
            from generate_thumbnail import generate_thumbnail
            thumb_path = generate_thumbnail(test_dir, date_text=date_text)
            root_thumb = test_dir / "thumbnail.png"
            shutil.copy(thumb_path, root_thumb)
            print(f"    [OK] Thumbnail saved: {thumb_path}")
        except Exception as exc:
            print(f"    [ERROR] Failed to generate thumbnail: {exc}")

        # Stage 4: Scheduled Upload
        print(f"\n>>> [{test_name}] STAGE 4: Uploading to YouTube scheduled for {publish_at}...")
        cmd_upload = [
            sys.executable, "-u", str(ROOT / "youtube_upload.py"),
            str(test_dir),
            "--publish-at", publish_at,
        ]
        res = subprocess.run(cmd_upload, cwd=str(ROOT))
        if res.returncode != 0:
            print(f"[ERROR] Stage 4 upload failed for {test_name}")
            continue

        print(f"\n[SUCCESS] Completed {test_name} and scheduled on YouTube for {publish_at}!")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["stage1", "prompts", "check", "resume", "full"], default="stage1", nargs="?")
    parser.add_argument("--band", default="9.0")
    parser.add_argument("--provider", default="gemini")
    parser.add_argument("--skip-verify", action="store_true", default=True)
    parser.add_argument("--no-skip-verify", dest="skip_verify", action="store_false")
    args = parser.parse_args()

    if args.action == "stage1":
        run_stage1_parallel(band=args.band, skip_verify=args.skip_verify, provider=args.provider)
    elif args.action == "prompts":
        collect_and_display_prompts()
    elif args.action == "check":
        check_and_sync_visuals()
    elif args.action in ["resume", "full"]:
        run_stages_2_to_4()
