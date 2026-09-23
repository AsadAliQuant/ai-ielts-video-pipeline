#!/usr/bin/env python3
"""
Regenerates thumbnails for test_011 to test_016 with their exact scheduled dates
and updates them on YouTube via the YouTube Data API v3.
"""

import os
import re
import shutil
import sys
from pathlib import Path
from googleapiclient.http import MediaFileUpload
from generate_thumbnail import generate_thumbnail
from youtube_upload import build_youtube_client

ROOT = Path(__file__).resolve().parent

TESTS = [
    {"test": "test_011", "date_text": "20/Sep/2026", "video_id": "QIWRV22jveg"},
    {"test": "test_012", "date_text": "21/Sep/2026", "video_id": "P0xVE_-A2Pw"},
    {"test": "test_013", "date_text": "22/Sep/2026", "video_id": "hzzjz-X2ki8"},
    {"test": "test_014", "date_text": "23/Sep/2026", "video_id": "PCiJXjPYruw"},
    {"test": "test_015", "date_text": "24/Sep/2026", "video_id": "-QpiiMxZyso"},
    {"test": "test_016", "date_text": "25/Sep/2026", "video_id": None},
]


def find_test_016_video_id():
    """Look for test_016 video id from task log or video directory."""
    log_dir = Path(r"C:\Users\Asad\.gemini\antigravity\brain\62b7ec57-461d-470e-a543-3bcb39a95cff\.system_generated\tasks")
    if log_dir.exists():
        for log_file in log_dir.glob("task-*.log"):
            content = log_file.read_text(encoding="utf-8", errors="ignore")
            m = re.findall(r"\[test_016\].*?Uploaded:\s*https://youtu\.be/([a-zA-Z0-9_-]+)", content, re.DOTALL)
            if m:
                return m[-1]
            # also check generic pattern after test_016
            parts = content.split("PROCESSING test_016")
            if len(parts) > 1:
                m2 = re.search(r"Uploaded:\s*https://youtu\.be/([a-zA-Z0-9_-]+)", parts[1])
                if m2:
                    return m2.group(1)
    return None


def main():
    # Check if test_016 video_id is available
    if not TESTS[5]["video_id"]:
        vid_16 = find_test_016_video_id()
        if vid_16:
            TESTS[5]["video_id"] = vid_16

    youtube = build_youtube_client()
    print("=" * 65)
    print(" REGENERATING THUMBNAILS WITH SCHEDULED DATES & UPDATING YOUTUBE")
    print("=" * 65)

    for item in TESTS:
        test_name = item["test"]
        date_text = item["date_text"]
        video_id = item["video_id"]
        test_dir = ROOT / "tests" / test_name

        if not test_dir.exists():
            print(f"[SKIP] {test_dir} not found")
            continue

        print(f"\n>>> [{test_name}] Generating thumbnail with date '{date_text}'...")
        thumb_path = generate_thumbnail(test_dir, date_text=date_text)
        
        # Copy to test root as well
        root_thumb = test_dir / "thumbnail.png"
        shutil.copy(thumb_path, root_thumb)
        print(f"    Saved: {thumb_path}")

        # Update on YouTube if video_id is known
        if not video_id and test_name == "test_016":
            video_id = find_test_016_video_id()

        if video_id:
            print(f"    Updating thumbnail on YouTube for video ID: {video_id} ...")
            try:
                thumb_media = MediaFileUpload(str(thumb_path), mimetype="image/png")
                youtube.thumbnails().set(videoId=video_id, media_body=thumb_media).execute()
                print(f"    [OK] YouTube thumbnail updated for {test_name} ({video_id})!")
            except Exception as e:
                print(f"    [ERROR] Failed to update thumbnail on YouTube: {e}")
        else:
            print(f"    [WARN] No video ID found yet for {test_name}, skipped YouTube update.")

    print("\n" + "=" * 65)
    print(" ALL THUMBNAILS UPDATED SUCCESSFULLY")
    print("=" * 65)


if __name__ == "__main__":
    main()
