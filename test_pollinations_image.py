"""
Test Pollinations.ai image generation (100% free, no API key) for
tests/test_003's Part 2 map visual.

Pollinations is a plain GET request -- the prompt goes in the URL path,
options as query params. No auth needed for anonymous use (rate-limited,
may carry a small watermark); a free account at auth.pollinations.ai
unlocks nologo=true and a faster rate limit via a token.
"""

import os
import urllib.parse
import requests
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.environ.get("POLLINATIONS_TOKEN", "")  # optional, free to get

# Real Part 2 map prompt from tests/test_003/visuals.md
PROMPT = (
    "A clean black and white line-drawing map of a university botanical "
    "gardens layout. The main entrance is at the bottom center. Paved "
    "walking paths loop around various garden zones labeled with letters "
    "A through H. A central fountain marks the middle of the grounds. "
    "Clear north arrow and scale bar included. No shading, minimalist "
    "line art, white background."
)

encoded_prompt = urllib.parse.quote(PROMPT)
url = f"https://image.pollinations.ai/prompt/{encoded_prompt}"

params = {
    "width": 1920,
    "height": 1080,
    "model": "flux",
    "seed": 42,
    "nologo": "true",
}
if TOKEN:
    params["token"] = TOKEN

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_PATH = os.path.join(SCRIPT_DIR, "tests", "test_003", "visuals", "v1_pollinations_test.png")

print("Requesting image from Pollinations.ai...")
print(f"Prompt: {PROMPT[:80]}...")

resp = requests.get(url, params=params, timeout=120)

if resp.status_code == 200 and "image" in resp.headers.get("content-type", ""):
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "wb") as f:
        f.write(resp.content)
    print(f"\nSUCCESS! Image saved to: {OUTPUT_PATH}")
else:
    print(f"\nError {resp.status_code}: {resp.text[:500]}")
