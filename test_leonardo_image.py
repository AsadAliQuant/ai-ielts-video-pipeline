"""
Test Leonardo.ai image generation for tests/test_003's Part 2 map visual.

Leonardo's API is async: POST /generations queues a job and returns a
generationId, then GET /generations/{id} must be polled until status
COMPLETE before the image URLs are available.
"""

import os
import time
import requests
from dotenv import load_dotenv

load_dotenv()
API_KEY = os.environ.get("LEONARDO_API_KEY", "")

if not API_KEY:
    print("ERROR: Set LEONARDO_API_KEY in your .env file.")
    exit(1)

BASE_URL = "https://cloud.leonardo.ai/api/rest/v1"
HEADERS = {
    "accept": "application/json",
    "authorization": f"Bearer {API_KEY}",
    "content-type": "application/json",
}

# Real Part 2 map prompt from tests/test_003/visuals.md
PROMPT = (
    "A clean black and white line-drawing map of a university botanical "
    "gardens layout. The main entrance is at the bottom center. Paved "
    "walking paths loop around various garden zones labeled with letters "
    "A through H. A central fountain marks the middle of the grounds. "
    "Clear north arrow and scale bar included."
)

payload = {
    "alchemy": False,
    "height": 1080,
    "modelId": "7b592283-e8a7-4c5a-9ba6-d18c31f258b9",
    "contrast": 3.5,
    "num_images": 1,
    "styleUUID": "111dc692-d470-4eec-b791-3475abac4c46",
    "prompt": PROMPT,
    "width": 1920,
    "ultra": False,
}

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_PATH = os.path.join(SCRIPT_DIR, "tests", "test_003", "visuals", "v1_leonardo_test.png")

print("Submitting generation job to Leonardo.ai...")
resp = requests.post(f"{BASE_URL}/generations", headers=HEADERS, json=payload, timeout=60)

if resp.status_code not in (200, 201):
    print(f"Error {resp.status_code}: {resp.text[:800]}")
    exit(1)

body = resp.json()
generation_id = body.get("sdGenerationJob", {}).get("generationId")
if not generation_id:
    print("Unexpected response, no generationId found:")
    print(body)
    exit(1)

print(f"Generation queued: {generation_id}")
print("Polling for completion...")

image_url = None
for attempt in range(30):
    time.sleep(4)
    poll = requests.get(f"{BASE_URL}/generations/{generation_id}", headers=HEADERS, timeout=30)
    if poll.status_code != 200:
        print(f"Poll error {poll.status_code}: {poll.text[:500]}")
        continue

    gen = poll.json().get("generations_by_pk", {})
    status = gen.get("status")
    print(f"  [{attempt + 1}/30] status={status}")

    if status == "COMPLETE":
        images = gen.get("generated_images", [])
        if images:
            image_url = images[0]["url"]
        break
    elif status == "FAILED":
        print("Generation failed on Leonardo's side.")
        exit(1)
else:
    print("Timed out waiting for generation to complete.")
    exit(1)

if not image_url:
    print("Generation completed but no image URL was returned.")
    exit(1)

print(f"Downloading image from {image_url}")
img_resp = requests.get(image_url, timeout=60)
os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
with open(OUTPUT_PATH, "wb") as f:
    f.write(img_resp.content)

print(f"\nSUCCESS! Image saved to: {OUTPUT_PATH}")
