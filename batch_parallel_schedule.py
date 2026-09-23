#!/usr/bin/env python3
"""
Batch Parallel & Scheduled YouTube Pipeline for 6 IELTS Tests.

Phases:
1. 'stage1': Concurrently generates test papers for test_011 through test_016,
   then extracts all GenAI visual prompts for the user.
2. 'resume' / 'full': Continues with Stage 2 (audio), Stage 3 (video), and
   Stage 4 (scheduled YouTube upload at 8:00 AM incrementing dates).
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
    {"test": "test_011", "date": "2026-09-20T08:00:00+05:00", "title_date": "20.09.2026"},
    {"test": "test_012", "date": "2026-09-21T08:00:00+05:00", "title_date": "21.09.2026"},
    {"test": "test_013", "date": "2026-09-22T08:00:00+05:00", "title_date": "22.09.2026"},
    {"test": "test_014", "date": "2026-09-23T08:00:00+05:00", "title_date": "23.09.2026"},
    {"test": "test_015", "date": "2026-09-24T08:00:00+05:00", "title_date": "24.09.2026"},
    {"test": "test_016", "date": "2026-09-25T08:00:00+05:00", "title_date": "25.09.2026"},
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
    """Run Stage 1 for all 6 tests simultaneously."""
    print("=" * 70)
    print(f" STARTING PARALLEL STAGE 1 GENERATION FOR 6 TESTS (test_011 .. test_016)")
    print(f" Target Band: {band} | Provider: {provider} | Skip Verify: {skip_verify}")
    print("=" * 70)

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

        print(f"Launching worker {i+1}/6: {test_name} (key offset: {i})...")
        proc = subprocess.Popen(
            cmd,
            stdout=log_f,
            stderr=subprocess.STDOUT,
            cwd=str(ROOT),
        )
        processes.append((test_name, proc, log_path))

    print(f"\nAll 6 workers launched! Monitoring progress...")

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

    print("\n" + "=" * 70)
    print(" ALL 6 STAGE 1 WORKERS COMPLETED")
    print("=" * 70)

    # Collect and display all visual prompts
    collect_and_display_prompts()


def collect_and_display_prompts():
    """Extract visual prompts from each test and format for user generation."""
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

    print("\n" + "#" * 70)
    print(" EXTRACTED IMAGE PROMPTS FOR USER GENERATION")
    print("#" * 70)

    if not all_prompts:
        print("No image visuals required for these tests!")
        return

    output_summary = []
    output_summary.append("# IELTS Test Visual Image Prompts for ChatGPT / Midjourney\n")

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


def run_stages_2_to_4():
    """Run Stage 2 (Audio), Stage 3 (Video), and Stage 4 (Upload) sequentially."""
    print("=" * 70)
    print(" PROCEEDING TO STAGES 2, 3, AND 4 (AUDIO, VIDEO, SCHEDULED YOUTUBE UPLOAD)")
    print("=" * 70)

    for item in TEST_SCHEDULE:
        test_name = item["test"]
        publish_at = item["date"]
        test_dir = ROOT / "tests" / test_name

        if not test_dir.exists():
            print(f"[ERROR] Test directory {test_dir} does not exist. Skipping.")
            continue

        print(f"\n" + "#" * 70)
        print(f" PROCESSING {test_name} (Scheduled for {publish_at})")
        print("#" * 70)

        # Stage 2: Audio
        print(f"\n>>> [{test_name}] STAGE 2: Synthesizing Audio...")
        cmd_audio = [sys.executable, "-u", str(ROOT / "generate_audio.py"), str(test_dir)]
        res = subprocess.run(cmd_audio, cwd=str(ROOT))
        if res.returncode != 0:
            print(f"[ERROR] Stage 2 failed for {test_name}")
            continue

        # Stage 3: Video
        print(f"\n>>> [{test_name}] STAGE 3: Rendering Video & HUD...")
        cmd_video = [sys.executable, "-u", str(ROOT / "generate_video.py"), str(test_dir), "--fast"]
        res = subprocess.run(cmd_video, cwd=str(ROOT))
        if res.returncode != 0:
            print(f"[ERROR] Stage 3 failed for {test_name}")
            continue

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
    parser.add_argument("action", choices=["stage1", "prompts", "resume", "full"], default="stage1", nargs="?")
    parser.add_argument("--band", default="9.0")
    parser.add_argument("--provider", default="gemini")
    parser.add_argument("--skip-verify", action="store_true", default=True)
    parser.add_argument("--no-skip-verify", dest="skip_verify", action="store_false")
    args = parser.parse_args()

    if args.action == "stage1":
        run_stage1_parallel(band=args.band, skip_verify=args.skip_verify, provider=args.provider)
    elif args.action == "prompts":
        collect_and_display_prompts()
    elif args.action in ["resume", "full"]:
        run_stages_2_to_4()
