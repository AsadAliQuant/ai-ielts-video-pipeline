"""
Stage 3: Visuals Generation

Generates exam diagrams (floor plans, maps, diagrams) for Part 2/3 questions
via Gemini Image API or creates a structured fallback visual card.
Caches all generated images to tests/test_NNN/visuals/{visual_id}.png.
"""

import base64
import json
import os
import sys
from pathlib import Path
import requests
from dotenv import load_dotenv
from PIL import Image, ImageDraw

# Add project root to path for imports
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import fonts
from generate_test import _load_gemini_keys


def load_video_config(config_path: Path | None = None) -> dict:
    if config_path is None:
        config_path = ROOT / "video_config.json"
    if config_path.exists():
        return json.loads(config_path.read_text(encoding="utf-8"))
    return {}


def create_fallback_card(visual: dict, out_path: Path):
    """Create a clean, exam-style fallback diagram card with Pillow."""
    width, height = 1200, 800
    img = Image.new("RGB", (width, height), color="#FFFFFF")
    draw = ImageDraw.Draw(img)

    # Draw border
    draw.rectangle([(20, 20), (width - 20, height - 20)], outline="#0F172A", width=3)
    draw.rectangle([(26, 26), (width - 26, height - 26)], outline="#94A3B8", width=1)

    # Bundled fonts -- see fonts.py for why system font names are not used.
    title_font = fonts.pillow_font("bold", 34)
    subtitle_font = fonts.pillow_font("regular", 24)
    item_font = fonts.pillow_font("bold", 22)
    text_font = fonts.pillow_font("regular", 20)

    title = visual.get("title") or "EXAM DIAGRAM / MAP"
    purpose = visual.get("purpose") or ""

    # Title header
    draw.text((60, 60), title.upper(), fill="#0F172A", font=title_font)
    if purpose:
        draw.text((60, 110), f"({purpose})", fill="#475569", font=subtitle_font)

    draw.line([(60, 155), (width - 60, 155)], fill="#CBD5E1", width=2)

    # Draw answer mappings or options box
    mapping = visual.get("answer_mapping", [])
    if mapping:
        draw.text((60, 180), "LOCATIONS & LABELS:", fill="#1E40AF", font=subtitle_font)
        y = 230
        for item in mapping:
            label = item.get("label", "?")
            meaning = item.get("meaning", "")
            q_num = item.get("number")
            q_str = f" [Q{q_num}]" if q_num else ""
            
            # Badge
            draw.rectangle([(60, y), (110, y + 40)], fill="#1E293B", outline="#0F172A")
            draw.text((75, y + 8), str(label), fill="#FFFFFF", font=item_font)
            draw.text((130, y + 10), f"{meaning}{q_str}", fill="#1E293B", font=item_font)
            y += 55
            if y > height - 100:
                break
    else:
        # If no mapping, print prompt summary
        prompt = visual.get("image_prompt", "")
        draw.text((60, 180), "DIAGRAM DESCRIPTION:", fill="#1E40AF", font=subtitle_font)
        words = prompt.split()
        lines = []
        cur = []
        for w in words:
            cur.append(w)
            if len(" ".join(cur)) > 70:
                lines.append(" ".join(cur))
                cur = []
        if cur:
            lines.append(" ".join(cur))
        
        y = 230
        for line in lines[:10]:
            draw.text((60, y), line, fill="#334155", font=text_font)
            y += 35

    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path, format="PNG")
    print(f"    -> Generated fallback visual card: {out_path.name}")


def call_gemini_image_api(prompt: str, api_key: str, model: str,
                          aspect_ratio: str = "4:3", image_size: str = "2K") -> bytes | None:
    """Call Google Gemini Image API."""
    # Try interactions endpoint
    url = "https://generativelanguage.googleapis.com/v1beta/interactions"
    headers = {
        "x-goog-api-key": api_key,
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "input": [{"type": "text", "text": prompt}],
        "response_format": {"type": "image", "aspect_ratio": aspect_ratio, "image_size": image_size}
    }

    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=60)
        if resp.status_code == 200:
            data = resp.json()
            # Extract image bytes from response
            if "outputs" in data:
                for out in data["outputs"]:
                    if out.get("type") == "image" and "data" in out:
                        return base64.b64decode(out["data"])
                    if "image" in out and "image_bytes" in out["image"]:
                        return base64.b64decode(out["image"]["image_bytes"])
            if "candidates" in data:
                for c in data["candidates"]:
                    for part in c.get("content", {}).get("parts", []):
                        if "inlineData" in part:
                            return base64.b64decode(part["inlineData"]["data"])
    except Exception as e:
        print(f"    Warning: Gemini image API interactions request failed: {e}")

    # Fallback to standard predict / generateContent if needed
    return None


def generate_visuals(test_dir: str | Path, config_path: str | Path = None,
                     force: bool = False) -> dict[str, Path]:
    """Generate and cache all visuals for a test.

    Returns a dict of visual_id -> image_path.
    """
    test_dir = Path(test_dir)
    test_json_path = test_dir / "test.json"
    if not test_json_path.exists():
        raise FileNotFoundError(f"Missing {test_json_path}")

    test_data = json.loads(test_json_path.read_text(encoding="utf-8"))
    config = load_video_config(Path(config_path) if config_path else None)
    
    vis_cfg = config.get("visual_generation", {})
    model = vis_cfg.get("model", "gemini-3.1-flash-image")
    style_suffix = vis_cfg.get("style_suffix", "")
    aspect_ratio = vis_cfg.get("aspect_ratio", "4:3")
    image_size = vis_cfg.get("image_size", "2K")

    visuals_dir = test_dir / "visuals"
    visuals_dir.mkdir(parents=True, exist_ok=True)

    load_dotenv(ROOT / ".env")
    gemini_keys = _load_gemini_keys()

    visual_paths = {}

    for part in test_data.get("parts", []):
        for visual in part.get("visuals", []):
            vid = str(visual.get("id") or "").strip()
            if not vid:
                continue

            target_path = visuals_dir / f"{vid}.png"
            visual_paths[vid] = target_path

            if target_path.exists() and not force:
                print(f"  Visual [{vid}]: Already cached at {target_path.name}")
                continue

            image_prompt = visual.get("image_prompt", "").strip()
            full_prompt = image_prompt + style_suffix if image_prompt else ""

            image_bytes = None
            if full_prompt and gemini_keys:
                for i, key in enumerate(gemini_keys, start=1):
                    print(f"  Visual [{vid}]: Requesting Gemini image generation (Key #{i})...")
                    image_bytes = call_gemini_image_api(
                        prompt=full_prompt,
                        api_key=key,
                        model=model,
                        aspect_ratio=aspect_ratio,
                        image_size=image_size
                    )
                    if image_bytes:
                        break
                    print(f"    Key #{i} failed or rate-limited, trying next key...")

            if image_bytes:
                target_path.write_bytes(image_bytes)
                print(f"  Visual [{vid}]: Successfully saved generated image to {target_path.name}")
            else:
                print(f"  Visual [{vid}]: Using structured text/table fallback card")
                create_fallback_card(visual, target_path)

    return visual_paths


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python generate_visuals.py <test_directory> [--force]")
        sys.exit(1)

    target_dir = sys.argv[1]
    is_force = "--force" in sys.argv
    generate_visuals(target_dir, force=is_force)
