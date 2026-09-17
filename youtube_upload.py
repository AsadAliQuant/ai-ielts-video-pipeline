"""
Stage 4 (optional): upload a rendered test's video to YouTube via the Data
API v3, using a refresh token minted once by get_youtube_token.py.

    python youtube_upload.py tests/test_007

Reads YOUTUBE_CLIENT_ID / YOUTUBE_CLIENT_SECRET / YOUTUBE_REFRESH_TOKEN /
YOUTUBE_PRIVACY from the environment (.env locally, repo secrets in CI).
Builds title/description from test.json + chapters.txt so no manual entry
is needed.
"""
import argparse
from datetime import datetime
import json
import os
import re
import sys
from pathlib import Path

from dotenv import load_dotenv
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError

load_dotenv()

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


def build_youtube_client():
    required = ["YOUTUBE_CLIENT_ID", "YOUTUBE_CLIENT_SECRET", "YOUTUBE_REFRESH_TOKEN"]
    missing = [k for k in required if not os.environ.get(k)]
    if missing:
        sys.exit(f"Missing env vars: {', '.join(missing)}. Run get_youtube_token.py first.")

    creds = Credentials(
        token=None,
        refresh_token=os.environ["YOUTUBE_REFRESH_TOKEN"],
        client_id=os.environ["YOUTUBE_CLIENT_ID"],
        client_secret=os.environ["YOUTUBE_CLIENT_SECRET"],
        token_uri="https://oauth2.googleapis.com/token",
        scopes=SCOPES,
    )
    creds.refresh(Request())
    return build("youtube", "v3", credentials=creds)


from generate_youtube_description import generate_youtube_description


def build_metadata(test_dir: Path, custom_title: str | None = None, upload_date: datetime | None = None):
    test_json_path = test_dir / "test.json"
    if test_json_path.exists():
        test = json.loads(test_json_path.read_text(encoding="utf-8"))
    else:
        test = {}

    if custom_title:
        title = custom_title
    else:
        dt = upload_date or datetime.now()
        year = dt.strftime("%Y")
        date_str = dt.strftime("%d.%m.%Y")
        title = f"IELTS LISTENING PRACTICE TEST {year} WITH ANSWERS | {date_str}"

    if len(title) > 100:
        title = title[:97] + "..."

    description = generate_youtube_description(test_dir)

    return title, description


def upload(test_dir: Path, custom_title: str | None = None):
    video_path = test_dir / "video" / f"{test_dir.name}.mp4"
    if not video_path.exists():
        sys.exit(f"No rendered video found at {video_path} -- run generate_video.py first.")

    title, description = build_metadata(test_dir, custom_title=custom_title)
    privacy = os.environ.get("YOUTUBE_PRIVACY", "unlisted")

    youtube = build_youtube_client()
    body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": [
                "IELTS",
                "IELTS Listening",
                "IELTS Practice Test",
                "IELTS 2026",
                "Band 8",
                "Band 9",
                "IELTS Listening Test",
                "English Test",
                "IELTS Preparation",
            ],
            "categoryId": "27",  # Education
        },
        "status": {"privacyStatus": privacy, "selfDeclaredMadeForKids": False},
    }
    media = MediaFileUpload(str(video_path), chunksize=-1, resumable=True, mimetype="video/mp4")

    print(f"Uploading {video_path} as '{title}' ({privacy}) ...")
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

    response = None
    while response is None:
        try:
            status, response = request.next_chunk()
            if status:
                print(f"  {int(status.progress() * 100)}% uploaded")
        except HttpError as e:
            sys.exit(f"YouTube upload failed: {e}")

    video_id = response["id"]
    print(f"Uploaded: https://youtu.be/{video_id}")

    # Set custom YouTube thumbnail
    thumb_path = test_dir / "video" / "thumbnail.png"
    if not thumb_path.exists():
        thumb_path = test_dir / "thumbnail.png"
    if not thumb_path.exists():
        try:
            from generate_thumbnail import generate_thumbnail
            thumb_path = generate_thumbnail(test_dir)
        except Exception as e:
            print(f"Warning: Could not auto-generate thumbnail: {e}")
            thumb_path = None

    if thumb_path and thumb_path.exists():
        print(f"Setting custom thumbnail from {thumb_path} ...")
        try:
            thumb_media = MediaFileUpload(str(thumb_path), mimetype="image/png")
            youtube.thumbnails().set(videoId=video_id, media_body=thumb_media).execute()
            print("Custom thumbnail set successfully on YouTube!")
        except Exception as e:
            print(f"Warning: Setting custom thumbnail on YouTube failed: {e}")

    return video_id



if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("test_dir", help="Path to test directory (e.g. tests/test_007)")
    parser.add_argument("--title", help="Override YouTube video title", default=None)
    args = parser.parse_args()
    upload(Path(args.test_dir), custom_title=args.title)
