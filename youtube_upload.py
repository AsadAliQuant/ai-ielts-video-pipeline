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
import json
import sys
from pathlib import Path

from dotenv import load_dotenv
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError
import os

from text_utils import clean_title

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


def build_metadata(test_dir: Path):
    test = json.loads((test_dir / "test.json").read_text(encoding="utf-8"))
    meta = test["metadata"]
    topics = meta.get("part_topics", {})

    # The target band is an internal generation parameter -- never shown to viewers.
    title = f"{clean_title(meta.get('title'))} | Full Test with Answers"
    if len(title) > 100:
        title = title[:97] + "..."

    topic_lines = "\n".join(f"Part {k}: {v}" for k, v in sorted(topics.items()))
    chapters_path = test_dir / "video" / "chapters.txt"
    chapters = chapters_path.read_text(encoding="utf-8") if chapters_path.exists() else ""

    description = (
        "Full IELTS Listening practice test, generated and narrated end-to-end."
        f"\n\nTopics covered:\n{topic_lines}\n\n"
        "Try it yourself before checking the answer key, then use the timestamps below to "
        "jump to any part.\n\n"
        f"{chapters}\n\n#IELTS #IELTSListening #IELTSPractice"
    ).strip()

    return title, description


def upload(test_dir: Path):
    video_path = test_dir / "video" / f"{test_dir.name}.mp4"
    if not video_path.exists():
        sys.exit(f"No rendered video found at {video_path} -- run generate_video.py first.")

    title, description = build_metadata(test_dir)
    privacy = os.environ.get("YOUTUBE_PRIVACY", "unlisted")

    youtube = build_youtube_client()
    body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": ["IELTS", "IELTS Listening", "IELTS Practice Test", "English Test"],
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
    return video_id


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("test_dir", help="Path to test directory (e.g. tests/test_007)")
    args = parser.parse_args()
    upload(Path(args.test_dir))
