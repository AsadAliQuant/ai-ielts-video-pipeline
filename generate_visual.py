"""
IELTS Visual Asset Generator.

Generates clean educational visuals (maps, floor plans, building layouts, diagrams)
for IELTS Listening tests using Cloudflare Workers AI (FLUX-1-schnell) for the base line
drawing, and Pillow for crisp, standardized IELTS typography, badges, and compass rose.
"""

import base64
import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests
from PIL import Image, ImageDraw, ImageFont

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent / ".env")
except ImportError:
    pass

# Cloudflare Model Configuration
CF_IMAGE_MODEL = "@cf/black-forest-labs/flux-1-schnell"


def get_cf_credentials() -> Tuple[str, str]:
    """Retrieve Cloudflare credentials from environment or .env file."""
    account_id = os.environ.get("CF_ACCOUNT_ID", "").strip()
    api_token = os.environ.get("CF_API_TOKEN", "").strip()
    if not account_id or not api_token or account_id == "YOUR_ACCOUNT_ID" or api_token == "YOUR_API_TOKEN":
        return "", ""
    return account_id, api_token


def get_fonts() -> Dict[str, ImageFont.ImageFont]:
    """Load clean sans-serif fonts for IELTS test materials."""
    candidates_regular = [
        "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/calibri.ttf",
        "C:/Windows/Fonts/segoeui.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
    ]
    candidates_bold = [
        "C:/Windows/Fonts/arialbd.ttf",
        "C:/Windows/Fonts/calibrib.ttf",
        "C:/Windows/Fonts/segoeuib.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/System/Library/Fonts/Helvetica-Bold.ttc",
    ]

    reg_path = next((p for p in candidates_regular if os.path.exists(p)), None)
    bold_path = next((p for p in candidates_bold if os.path.exists(p)), None)

    try:
        if reg_path and bold_path:
            return {
                "title": ImageFont.truetype(bold_path, 24),
                "label": ImageFont.truetype(bold_path, 15),
                "sub": ImageFont.truetype(reg_path, 13),
                "badge": ImageFont.truetype(bold_path, 18),
                "compass": ImageFont.truetype(bold_path, 16),
            }
    except Exception:
        pass

    default = ImageFont.load_default()
    return {
        "title": default,
        "label": default,
        "sub": default,
        "badge": default,
        "compass": default,
    }


def call_cloudflare_flux(prompt: str, account_id: str, api_token: str) -> Optional[Image.Image]:
    """Call Cloudflare Workers AI FLUX-1-schnell to generate raw base image."""
    url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/{CF_IMAGE_MODEL}"
    headers = {"Authorization": f"Bearer {api_token}"}
    payload = {"prompt": prompt}

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=90)
        if response.status_code != 200:
            print(f"Workers AI API error ({response.status_code}): {response.text[:200]}")
            return None

        content_type = response.headers.get("content-type", "")
        if "image" in content_type:
            from io import BytesIO
            return Image.open(BytesIO(response.content)).convert("RGBA")

        body = response.json()
        if "result" in body and "image" in body["result"]:
            from io import BytesIO
            img_bytes = base64.b64decode(body["result"]["image"])
            return Image.open(BytesIO(img_bytes)).convert("RGBA")
    except Exception as exc:
        print(f"Failed to fetch image from Cloudflare: {exc}")
    return None


def generate_fallback_layout(vtype: str = "floorplan") -> Image.Image:
    """Generate a clean architectural vector base if AI API is unavailable."""
    img = Image.new("RGBA", (1024, 1024), (255, 255, 255, 255))
    draw = ImageDraw.Draw(img)

    # Clean architectural floor plan / map outline
    wall_color = (0, 0, 0, 255)
    floor_color = (250, 250, 250, 255)

    # Outer building boundary
    rooms = [
        # (x1, y1, x2, y2)
        (220, 200, 480, 480),  # Top Left
        (480, 200, 800, 480),  # Top Right (Main Hall)
        (220, 480, 420, 780),  # Bottom Left
        (420, 480, 680, 780),  # Central Concourse
        (680, 480, 840, 640),  # Right Wing Upper
        (680, 640, 840, 780),  # Right Wing Lower
        (220, 820, 360, 920),  # Detached Outbuilding / Shed
        (560, 820, 840, 920),  # Outdoor Terrace / Station
    ]

    for r in rooms:
        draw.rectangle(r, fill=floor_color, outline=wall_color, width=4)

    # Doors / Openings
    draw.line([(420, 480), (480, 480)], fill=(255, 255, 255, 255), width=6)
    draw.line([(680, 540), (680, 580)], fill=(255, 255, 255, 255), width=6)
    draw.line([(520, 780), (580, 780)], fill=(255, 255, 255, 255), width=6)  # Main door

    return img


def get_default_badge_positions(num_badges: int) -> List[Tuple[int, int]]:
    """Standard pre-calculated positions distributed nicely across standard layout."""
    standard_positions = [
        (330, 320),  # Top-left room
        (640, 290),  # Top-right hall (Upper)
        (740, 390),  # Top-right hall (Right)
        (320, 610),  # Left room
        (550, 610),  # Central Hall
        (760, 550),  # Right Wing 1
        (760, 700),  # Right Wing 2
        (290, 870),  # Detached shed
        (700, 870),  # Platform / Terrace
    ]
    return standard_positions[:num_badges]


def overlay_ielts_test_labels(
    base_img: Image.Image,
    title: str,
    q_range_str: str,
    answer_mappings: List[Dict[str, Any]],
    landmarks: Optional[List[Tuple[int, int, str]]] = None,
) -> Image.Image:
    """Overlay IELTS title banner, question letters (A-G), and landmark text."""
    img = base_img.copy().convert("RGBA")
    draw = ImageDraw.Draw(img)
    fonts = get_fonts()

    # 1. Header Banner
    draw.rectangle([(20, 20), (1004, 75)], fill=(255, 255, 255, 245), outline=(0, 0, 0, 255), width=2)
    display_title = (title or "MAP / PLAN LABELLING").upper()
    draw.text((40, 34), display_title, fill=(0, 0, 0), font=fonts["title"])
    if q_range_str:
        draw.text((750, 36), q_range_str, fill=(80, 80, 80), font=fonts["label"])

    # 2. Compass Rose (Top Right)
    cx, cy = 940, 135
    draw.ellipse([(cx - 24, cy - 24), (cx + 24, cy + 24)], fill=(255, 255, 255, 240), outline=(0, 0, 0), width=2)
    draw.line([(cx, cy - 20), (cx, cy + 20)], fill=(0, 0, 0), width=2)
    draw.line([(cx - 20, cy), (cx + 20, cy)], fill=(0, 0, 0), width=2)
    draw.text((cx - 6, cy - 42), "N", fill=(0, 0, 0), font=fonts["compass"])

    # Helper: Draw badge (Question letter in a square box)
    def draw_badge(x: int, y: int, label_text: str):
        box_size = 38
        draw.rectangle(
            [(x - box_size // 2, y - box_size // 2), (x + box_size // 2, y + box_size // 2)],
            fill=(255, 255, 255, 255),
            outline=(0, 0, 0),
            width=2,
        )
        bbox = draw.textbbox((0, 0), label_text, font=fonts["badge"])
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        draw.text((x - tw // 2, y - th // 2 - 2), label_text, fill=(0, 0, 0), font=fonts["badge"])

    # Helper: Draw landmark text box
    def draw_landmark(x: int, y: int, text: str):
        bbox = draw.textbbox((0, 0), text, font=fonts["label"])
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        pad = 5
        draw.rectangle(
            [(x - tw // 2 - pad, y - th // 2 - pad), (x + tw // 2 + pad, y + th // 2 + pad)],
            fill=(255, 255, 255, 230),
            outline=(140, 140, 140),
            width=1,
        )
        draw.text((x - tw // 2, y - th // 2), text, fill=(0, 0, 0), font=fonts["label"])

    # 3. Add Fixed Landmarks
    if not landmarks:
        landmarks = [
            (550, 780, "Main Entrance"),
            (550, 480, "Corridor"),
            (500, 960, "South Yard"),
        ]
    for lx, ly, ltext in landmarks:
        draw_landmark(lx, ly, ltext)

    # 4. Add Badges from answer mappings
    num_badges = len(answer_mappings)
    positions = get_default_badge_positions(max(num_badges, 6))

    for i, mapping in enumerate(answer_mappings):
        label = str(mapping.get("label") or chr(65 + i))  # e.g. "A", "B"
        pos = positions[i % len(positions)]
        draw_badge(pos[0], pos[1], label)

    return img.convert("RGB")


def generate_visual_asset(visual: Dict[str, Any], output_path: Path) -> Optional[Path]:
    """
    Generate a full IELTS visual asset for a visual dictionary and save to output_path.
    """
    vtype = str(visual.get("type", "map")).lower()
    title = visual.get("title", "Plan / Map Labelling")
    questions = visual.get("questions", [])
    mappings = visual.get("answer_mapping", [])

    q_range_str = ""
    if questions:
        q_nums = [int(q) for q in questions if isinstance(q, (int, str)) and str(q).isdigit()]
        if q_nums:
            if len(q_nums) > 1:
                q_range_str = f"Questions {min(q_nums)} - {max(q_nums)}"
            else:
                q_range_str = f"Question {q_nums[0]}"

    account_id, api_token = get_cf_credentials()
    base_img = None

    if account_id and api_token:
        prompt = (
            f"A simple black and white architectural {vtype} of a {title.lower()}, "
            "top-down 2D floor plan view, clean crisp black outlines, white background, "
            "minimalist architectural blueprint style, no text, no letters, no labels, no words, "
            "no furniture, no shading, high contrast vector illustration style."
        )
        print(f"Generating base visual with Cloudflare FLUX-1-schnell ({vtype})...")
        base_img = call_cloudflare_flux(prompt, account_id, api_token)

    if base_img is None:
        print("Using clean vector layout generator for visual asset...")
        base_img = generate_fallback_layout(vtype)

    final_img = overlay_ielts_test_labels(
        base_img=base_img,
        title=title,
        q_range_str=q_range_str,
        answer_mappings=mappings,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    final_img.save(str(output_path), "PNG")
    print(f"Saved visual asset -> {output_path}")
    return output_path


def process_test_visuals(test: Dict[str, Any], out_dir: Path) -> List[str]:
    """
    Generate and save all image visuals required by the test parts into out_dir.
    Returns list of saved image filenames.
    """
    generated_files = []
    parts = test.get("parts", [])

    for part_no, part in enumerate(parts, start=1):
        visuals = part.get("visuals", [])
        for visual in visuals:
            vid = visual.get("id", f"v{part_no}")
            mermaid = str(visual.get("mermaid", "")).strip()
            vtype = str(visual.get("type", "")).lower()

            # Generate image asset for maps, floorplans, diagrams or when image_prompt is present
            needs_image = (
                vtype in ["map", "floorplan", "diagram", "plan_map_labelling", "diagram_labelling"]
                or bool(visual.get("image_prompt"))
                or not mermaid
            )

            if needs_image:
                img_filename = f"visual_{vid}.png"
                img_path = out_dir / img_filename
                try:
                    generate_visual_asset(visual, img_path)
                    visual["image_filename"] = img_filename
                    generated_files.append(img_filename)
                except Exception as exc:
                    print(f"Error generating visual {vid}: {exc}")

    return generated_files


if __name__ == "__main__":
    # Test standalone execution
    sample_visual = {
        "id": "v1",
        "type": "floorplan",
        "title": "Museum Ground Floor",
        "questions": [16, 17, 18, 19, 20],
        "answer_mapping": [
            {"number": 16, "label": "A", "meaning": "Exhibition Hall"},
            {"number": 17, "label": "B", "meaning": "Cafe"},
            {"number": 18, "label": "C", "meaning": "Cloakroom"},
            {"number": 19, "label": "D", "meaning": "Gift Shop"},
            {"number": 20, "label": "E", "meaning": "Audio Guide Desk"},
        ],
    }
    test_out = Path(__file__).resolve().parent / "test_visual_sample.png"
    generate_visual_asset(sample_visual, test_out)
