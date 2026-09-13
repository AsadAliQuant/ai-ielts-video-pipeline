"""
Side-by-side comparison: generate tests/test_002's Part 2 map visual across
every provider tested so far, for direct quality comparison.

Skipped:
- Leonardo.ai: account out of API credits (confirmed earlier)
- Gemini Image API: free-tier quota is 0 for all image models (confirmed earlier)
- Wan2.1: video-only model family, no text-to-image API exists
"""

import os
import base64
import urllib.parse
import requests
from dotenv import load_dotenv
from huggingface_hub import InferenceClient

load_dotenv()

# Real Part 2 map prompt from tests/test_002/visuals.md
PROMPT = (
    "A clear, 2D architectural map of a botanical garden conservatory zone "
    "viewed from above. It shows a central winding pathway with eight "
    "distinct buildings and pavilions clearly labeled with the letters "
    "A, B, C, D, E, F, G, H. A main entrance gate at the bottom, a central "
    "fountain plaza, and surrounding glasshouses. Clean line art, "
    "minimalist black and white style, white background, no shading."
)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
VISUALS_DIR = os.path.join(SCRIPT_DIR, "tests", "test_002", "visuals")
os.makedirs(VISUALS_DIR, exist_ok=True)


def save(path: str, content: bytes):
    with open(path, "wb") as f:
        f.write(content)
    print(f"    -> saved: {path}")


def run_pollinations():
    print("\n=== Pollinations.ai (flux) ===")
    encoded = urllib.parse.quote(PROMPT)
    url = f"https://image.pollinations.ai/prompt/{encoded}"
    params = {"width": 1920, "height": 1080, "model": "flux", "seed": 42, "nologo": "true"}
    resp = requests.get(url, params=params, timeout=120)
    if resp.status_code == 200 and "image" in resp.headers.get("content-type", ""):
        save(os.path.join(VISUALS_DIR, "v1_pollinations.png"), resp.content)
    else:
        print(f"    FAILED {resp.status_code}: {resp.text[:300]}")


def run_sd35():
    print("\n=== Stable Diffusion 3.5 Large (HF / fal-ai) ===")
    try:
        client = InferenceClient(api_key=os.environ["HF_TOKEN"], timeout=280)
        image = client.text_to_image(prompt=PROMPT, model="stabilityai/stable-diffusion-3.5-large")
        image.save(os.path.join(VISUALS_DIR, "v1_sd35.png"))
        print(f"    -> saved: {os.path.join(VISUALS_DIR, 'v1_sd35.png')}")
    except Exception as e:
        print(f"    FAILED: {e}")


def run_qwen():
    print("\n=== Qwen-Image (HF) ===")
    try:
        client = InferenceClient(api_key=os.environ["HF_TOKEN"], timeout=280)
        image = client.text_to_image(prompt=PROMPT, model="Qwen/Qwen-Image")
        image.save(os.path.join(VISUALS_DIR, "v1_qwen.png"))
        print(f"    -> saved: {os.path.join(VISUALS_DIR, 'v1_qwen.png')}")
    except Exception as e:
        print(f"    FAILED: {e}")


def run_cf_flux2dev():
    print("\n=== Cloudflare Workers AI: FLUX.2 [dev] ===")
    account_id = os.environ.get("CF_ACCOUNT_ID", "")
    api_token = os.environ.get("CF_API_TOKEN", "")
    model = "@cf/black-forest-labs/flux-2-dev"
    url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/{model}"
    headers = {"Authorization": f"Bearer {api_token}"}
    payload = {"prompt": PROMPT, "width": 1920, "height": 1080}

    resp = requests.post(url, headers=headers, json=payload, timeout=180)
    if resp.status_code == 200:
        content_type = resp.headers.get("content-type", "")
        if "image" in content_type:
            save(os.path.join(VISUALS_DIR, "v1_flux2dev_cf.png"), resp.content)
        else:
            body = resp.json()
            img_b64 = body.get("result", {}).get("image")
            if img_b64:
                save(os.path.join(VISUALS_DIR, "v1_flux2dev_cf.png"), base64.b64decode(img_b64))
            else:
                print(f"    FAILED: unexpected JSON response: {str(body)[:400]}")
    else:
        print(f"    FAILED {resp.status_code}: {resp.text[:400]}")


if __name__ == "__main__":
    print(f"Prompt: {PROMPT[:90]}...")
    run_pollinations()
    run_sd35()
    run_qwen()
    run_cf_flux2dev()
    print("\nDone. Compare images in tests/test_002/visuals/")
