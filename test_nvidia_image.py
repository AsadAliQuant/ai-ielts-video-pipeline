"""
Test Cloudflare Workers AI - Free image generation with FLUX-1-schnell
"""

import os
import requests
from dotenv import load_dotenv

# --- Load credentials from .env file ---
load_dotenv()
ACCOUNT_ID = os.environ.get("CF_ACCOUNT_ID", "")
API_TOKEN = os.environ.get("CF_API_TOKEN", "")

if not ACCOUNT_ID or ACCOUNT_ID == "YOUR_ACCOUNT_ID":
    print("ERROR: Set CF_ACCOUNT_ID in your .env file.")
    exit(1)
if not API_TOKEN or API_TOKEN == "YOUR_API_TOKEN":
    print("ERROR: Set CF_API_TOKEN in your .env file.")
    exit(1)

# --- Cloudflare Workers AI request ---
MODEL = "@cf/black-forest-labs/flux-1-schnell"
url = f"https://api.cloudflare.com/client/v4/accounts/{ACCOUNT_ID}/ai/run/{MODEL}"

headers = {"Authorization": f"Bearer {API_TOKEN}"}

# --- Prompt WITHOUT text labels (Pillow will add them) ---
payload = {
    "prompt": (
        "A simple black and white architectural floor plan of a museum building, "
        "top-down view, clean lines, no text, no labels, no writing. "
        "A large central square room connected to a long rectangular hall on the top, "
        "a right-side corridor area, a bottom open courtyard area, and a left-side pavilion room. "
        "A small detached building at the bottom-left, and an outdoor platform area at bottom-right. "
        "Minimalist line drawing style, white background, black outlines only, no shading, no furniture."
    ),
}

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
output_path = os.path.join(SCRIPT_DIR, "flux_raw_output.png")

print(f"Model: {MODEL}")
print(f"Prompt: {payload['prompt'][:80]}...")
print("Sending request to Cloudflare Workers AI...")

response = requests.post(url, headers=headers, json=payload, timeout=120)

if response.status_code == 200:
    content_type = response.headers.get("content-type", "")
    if "image" in content_type:
        # Binary image data
        with open(output_path, "wb") as f:
            f.write(response.content)
        print(f"\nSUCCESS! Image saved to: {output_path}")
    else:
        # JSON response - might contain base64
        import base64, json
        body = response.json()
        if "result" in body and "image" in body["result"]:
            img_bytes = base64.b64decode(body["result"]["image"])
            with open(output_path, "wb") as f:
                f.write(img_bytes)
            print(f"\nSUCCESS! Image saved to: {output_path}")
        else:
            print("Response:")
            print(json.dumps(body, indent=2)[:500])
else:
    print(f"\nError {response.status_code}: {response.text[:500]}")
