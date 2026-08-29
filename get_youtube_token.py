"""
One-time local setup: mint a YouTube OAuth refresh token for the automated
upload pipeline (youtube_upload.py). Run this ONCE on your own machine —
never in CI.

Prerequisites:
1. https://console.cloud.google.com/apis/library/youtube.googleapis.com
   -> enable "YouTube Data API v3" on your Google Cloud project (free).
2. https://console.cloud.google.com/apis/credentials
   -> Create Credentials -> OAuth client ID -> Application type: Desktop app.
   -> Note the Client ID and Client Secret.
3. Put those two values in .env as YOUTUBE_CLIENT_ID / YOUTUBE_CLIENT_SECRET
   (or paste them when prompted below).

This opens a browser once for you to approve upload access to your own
channel, then prints a refresh token that does not expire (unless revoked).
Paste it into .env as YOUTUBE_REFRESH_TOKEN, and into your GitHub repo's
Actions secrets under the same name.
"""
import os

from dotenv import load_dotenv
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

load_dotenv()


def main():
    client_id = os.environ.get("YOUTUBE_CLIENT_ID") or input("YouTube OAuth Client ID: ").strip()
    client_secret = os.environ.get("YOUTUBE_CLIENT_SECRET") or input("YouTube OAuth Client Secret: ").strip()

    client_config = {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["http://localhost"],
        }
    }

    flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
    creds = flow.run_local_server(port=0)

    print("\n--- Success ---")
    print("Add these to .env and to your GitHub repo Settings -> Secrets and variables -> Actions:\n")
    print(f"YOUTUBE_CLIENT_ID={client_id}")
    print(f"YOUTUBE_CLIENT_SECRET={client_secret}")
    print(f"YOUTUBE_REFRESH_TOKEN={creds.refresh_token}")


if __name__ == "__main__":
    main()
