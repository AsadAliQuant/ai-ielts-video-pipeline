"""
Test Qwen-Image (via Hugging Face Inference Providers) for tests/test_003's
Part 2 map visual. Qwen-Image's model card specifically claims strong
text/label rendering accuracy, which is what IELTS maps/flowcharts need.
"""

import os
from dotenv import load_dotenv
from huggingface_hub import InferenceClient

load_dotenv()
HF_TOKEN = os.environ.get("HF_TOKEN", "")

if not HF_TOKEN:
    print("ERROR: Set HF_TOKEN in your .env file.")
    exit(1)

# Real Part 2 map prompt from tests/test_003/visuals.md
PROMPT = (
    "A clean black and white line-drawing map of a university botanical "
    "gardens layout, top-down view. The main entrance is at the bottom "
    "center. Paved walking paths loop around garden zones clearly labeled "
    "with the letters A, B, C, D, E, F, G, H. A central fountain marks the "
    "middle of the grounds. Clear north arrow and scale bar included. "
    "Minimalist line art, white background, no shading."
)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_PATH = os.path.join(SCRIPT_DIR, "tests", "test_003", "visuals", "v1_qwen_test.png")

print("Requesting image from Qwen-Image via HF Inference Providers...")
print(f"Prompt: {PROMPT[:80]}...")

client = InferenceClient(api_key=HF_TOKEN)

try:
    image = client.text_to_image(
        prompt=PROMPT,
        model="Qwen/Qwen-Image",
    )
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    image.save(OUTPUT_PATH)
    print(f"\nSUCCESS! Image saved to: {OUTPUT_PATH}")
except Exception as e:
    print(f"\nError: {e}")
