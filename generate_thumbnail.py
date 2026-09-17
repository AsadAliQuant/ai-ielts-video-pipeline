"""
Standalone YouTube Thumbnail Generator for IELTS Listening Test Videos.

Creates high-CTR YouTube thumbnails matching the sticker/badge style:
- Glossy Top Banner ("IELTS Listening Exam Practice" in Georgia Bold)
- Center Diagonal Date Badge (Current date e.g. "14/Sep/2026" - LARGEST font in Black & White contrast)
- Top-Left Yellow Alert Box ("New Hot Test!" in Times New Roman Bold)
- Middle-Right Stack (with even ~40px vertical gaps):
  1. Red Score Box ("Band 8-9 Test" in Impact)
  2. Blue Practice Box ("Full Practice Exam!" in Georgia Bold / Trebuchet)
  3. Cream Exam Box ("New! EXAM TEST" in 120px large font with YouTube timestamp margin)
- Lower-Left Badges ("High Band" in Impact, "Real Practice" + "Best" in Times New Roman)
- Avoids claiming "original test", "original exam", or any official IELTS affiliation.
"""

from __future__ import annotations

import argparse
from datetime import datetime
import os
import sys
from pathlib import Path
from typing import Tuple, Optional
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import fonts


# ---------------------------------------------------------------------------
# Distinct Typography System
# ---------------------------------------------------------------------------

def load_font(font_name: str, size: int, fallback_weight: str = "bold") -> ImageFont.FreeTypeFont:
    """Load a specific Windows system font or fallback to bundled Inter font."""
    font_path = Path(f"C:/Windows/Fonts/{font_name}")
    if font_path.exists():
        try:
            return ImageFont.truetype(str(font_path), size)
        except Exception:
            pass
    try:
        return fonts.pillow_font(fallback_weight, size)
    except Exception:
        return ImageFont.load_default()


# ---------------------------------------------------------------------------
# Drawing Helpers
# ---------------------------------------------------------------------------

def create_tilted_badge(
    text: str,
    font: ImageFont.FreeTypeFont,
    bg_color: tuple = (12, 12, 12, 255),
    border_color: tuple = (255, 255, 255, 255),
    text_color: tuple = (255, 255, 255, 255),
    text_border_color: Optional[tuple] = None,
    border_width: int = 10,
    padding: Tuple[int, int] = (64, 22),
    angle: float = 9.5,
) -> Image.Image:
    """Creates a tilted rectangular sticker badge sloping upwards to the right."""
    dummy_draw = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    bbox = dummy_draw.textbbox((0, 0), text, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]

    w = text_w + padding[0] * 2
    h = text_h + padding[1] * 2

    badge = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    b_draw = ImageDraw.Draw(badge)

    b_draw.rounded_rectangle(
        [(0, 0), (w - 1, h - 1)],
        radius=22,
        fill=bg_color,
        outline=border_color,
        width=border_width,
    )

    tx = (w - text_w) // 2
    ty = (h - text_h) // 2 - bbox[1]

    if text_border_color:
        b_draw.text(
            (tx, ty),
            text,
            font=font,
            fill=text_color,
            stroke_width=5,
            stroke_fill=text_border_color,
        )
    else:
        b_draw.text((tx, ty), text, font=font, fill=text_color)

    rotated = badge.rotate(angle, expand=True, resample=Image.Resampling.BICUBIC)
    return rotated


# ---------------------------------------------------------------------------
# Background Extraction
# ---------------------------------------------------------------------------

def find_best_background(test_dir: Path, custom_frame: Optional[str] = None) -> Image.Image:
    """Finds an active question frame or exam screen for the thumbnail background."""
    if custom_frame:
        p = Path(custom_frame)
        if not p.is_absolute():
            p = test_dir / p
        if p.exists():
            return Image.open(p).convert("RGBA").resize((1920, 1080), Image.Resampling.LANCZOS)

    frames_dir = test_dir / "video" / "frames"
    if frames_dir.exists():
        for c in ["frame_00045.png", "frame_00040.png", "frame_00050.png", "frame_00020.png"]:
            fp = frames_dir / c
            if fp.exists():
                return Image.open(fp).convert("RGBA").resize((1920, 1080), Image.Resampling.LANCZOS)
        pngs = sorted(frames_dir.glob("frame_*.png"))
        if len(pngs) > 20:
            return Image.open(pngs[20]).convert("RGBA").resize((1920, 1080), Image.Resampling.LANCZOS)

    screens_dir = test_dir / "video" / "screens"
    for name in ["part_1_all.png", "part_2_all.png"]:
        sp = screens_dir / name
        if sp.exists():
            return Image.open(sp).convert("RGBA").resize((1920, 1080), Image.Resampling.LANCZOS)

    return Image.new("RGBA", (1920, 1080), (241, 245, 249, 255))


# ---------------------------------------------------------------------------
# Main Thumbnail Generator
# ---------------------------------------------------------------------------

def generate_thumbnail(
    test_dir: Path | str,
    output_path: Optional[Path | str] = None,
    custom_frame: Optional[str] = None,
    top_text: str = "IELTS Listening Exam Practice",
    date_text: Optional[str] = None,
    practice_text: str = "Full Practice Exam!",
    yellow_badge_text: str = "New Hot Test!",
    red_badge_text: str = "Band 8-9 Test",
    bottom_left_top: str = "High Band",
    bottom_left_mid: str = "Real Practice",
    bottom_left_right: str = "Best",
    bottom_right_new: str = "New!",
    bottom_right_exam: str = "EXAM TEST",
) -> Path:
    """Generates a complete YouTube thumbnail with distinct typography styles per strip."""
    test_dir = Path(test_dir).resolve()
    if not test_dir.exists():
        raise FileNotFoundError(f"Test directory not found: {test_dir}")

    if output_path is None:
        target_file = test_dir / "video" / "thumbnail.png"
    else:
        target_file = Path(output_path).resolve()

    if not date_text:
        date_text = datetime.now().strftime("%d/%b/%Y")

    base = find_best_background(test_dir, custom_frame)
    width, height = base.size  # 1920x1080

    overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    # -----------------------------------------------------------------------
    # Distinct Fonts with Larger Sizes:
    # -----------------------------------------------------------------------
    font_top = load_font("georgiab.ttf", 94, "bold")
    font_yellow = load_font("timesbd.ttf", 116, "bold")
    font_date = load_font("impact.ttf", 168, "bold")
    font_red = load_font("impact.ttf", 112, "bold")
    font_practice = load_font("georgiab.ttf", 80, "bold")
    font_bot_impact = load_font("impact.ttf", 96, "bold")
    font_bot_serif = load_font("timesbd.ttf", 84, "bold")
    # Enlarged bottom-right fonts (120px):
    font_br_new = load_font("timesbd.ttf", 120, "bold")
    font_br_exam = load_font("impact.ttf", 120, "bold")

    # -----------------------------------------------------------------------
    # 1. Top Blue Glossy Banner
    # -----------------------------------------------------------------------
    top_x1, top_y1 = 30, 20
    top_x2, top_y2 = width - 30, 160

    shadow_top = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    s_top_draw = ImageDraw.Draw(shadow_top)
    s_top_draw.rounded_rectangle(
        [(top_x1 + 6, top_y1 + 10), (top_x2 + 6, top_y2 + 10)],
        radius=28,
        fill=(0, 0, 0, 165),
    )
    shadow_top = shadow_top.filter(ImageFilter.GaussianBlur(radius=10))
    base.alpha_composite(shadow_top)

    draw.rounded_rectangle(
        [(top_x1, top_y1), (top_x2, top_y2)],
        radius=28,
        fill=(0, 42, 195, 250),
        outline=(255, 255, 255, 255),
        width=5,
    )

    draw.line(
        [(top_x1 + 36, top_y1 + 10), (top_x2 - 36, top_y1 + 10)],
        fill=(255, 255, 255, 130),
        width=3,
    )

    bbox_top = draw.textbbox((0, 0), top_text, font=font_top)
    top_w = bbox_top[2] - bbox_top[0]
    top_tx = (width - top_w) // 2
    top_ty = top_y1 + ((top_y2 - top_y1) - (bbox_top[3] - bbox_top[1])) // 2 - bbox_top[1]

    draw.text((top_tx + 3, top_ty + 3), top_text, font=font_top, fill=(0, 0, 0, 200))
    draw.text(
        (top_tx, top_ty),
        top_text,
        font=font_top,
        fill=(255, 255, 255, 255),
        stroke_width=2,
        stroke_fill=(0, 20, 100, 255),
    )

    # -----------------------------------------------------------------------
    # 2. Top-Left Yellow Alert Badge (Times Bold Serif)
    # -----------------------------------------------------------------------
    bbox_yellow = draw.textbbox((0, 0), yellow_badge_text, font=font_yellow)
    yw = bbox_yellow[2] - bbox_yellow[0] + 64
    yh = bbox_yellow[3] - bbox_yellow[1] + 38
    yx1, yy1 = 28, 182
    yx2, yy2 = yx1 + yw, yy1 + yh

    s_yel = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    s_ydraw = ImageDraw.Draw(s_yel)
    s_ydraw.rounded_rectangle([(yx1 + 8, yy1 + 10), (yx2 + 8, yy2 + 10)], radius=20, fill=(0, 0, 0, 150))
    s_yel = s_yel.filter(ImageFilter.GaussianBlur(radius=8))
    base.alpha_composite(s_yel)

    draw.rounded_rectangle(
        [(yx1, yy1), (yx2, yy2)],
        radius=20,
        fill=(255, 242, 0, 255),
        outline=(255, 255, 255, 255),
        width=5,
    )

    ytx = yx1 + 32
    yty = yy1 + (yh - (bbox_yellow[3] - bbox_yellow[1])) // 2 - bbox_yellow[1]
    draw.text(
        (ytx, yty),
        yellow_badge_text,
        font=font_yellow,
        fill=(195, 0, 0, 255),
        stroke_width=3,
        stroke_fill=(0, 0, 0, 255),
    )

    # -----------------------------------------------------------------------
    # 3. Middle-Right Stacked Badges:
    #    (A) Red Score Box: ry1 = 470, height = 124 -> ry2 = 594
    #    (B) Blue Practice Box: py1 = 640, height = 93 -> py2 = 733 (46px gap)
    #    (C) Cream Exam Box (Enlarged 120px): br_y1 = 785
    # -----------------------------------------------------------------------
    # (A) Red Box ("Band 8-9 Test")
    bbox_red = draw.textbbox((0, 0), red_badge_text, font=font_red)
    rw = bbox_red[2] - bbox_red[0] + 72
    rh = bbox_red[3] - bbox_red[1] + 32
    rx2 = width - 30
    rx1 = rx2 - rw
    ry1 = 470
    ry2 = ry1 + rh

    s_red = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    s_rdraw = ImageDraw.Draw(s_red)
    s_rdraw.rounded_rectangle([(rx1 + 8, ry1 + 10), (rx2 + 8, ry2 + 10)], radius=16, fill=(0, 0, 0, 160))
    s_red = s_red.filter(ImageFilter.GaussianBlur(radius=8))
    base.alpha_composite(s_red)

    draw.rounded_rectangle(
        [(rx1, ry1), (rx2, ry2)],
        radius=16,
        fill=(230, 0, 0, 255),
        outline=(255, 255, 255, 255),
        width=5,
    )

    rtx = rx1 + (rw - (bbox_red[2] - bbox_red[0])) // 2
    rty = ry1 + (rh - (bbox_red[3] - bbox_red[1])) // 2 - bbox_red[1]
    draw.text(
        (rtx, rty),
        red_badge_text,
        font=font_red,
        fill=(255, 245, 0, 255),
        stroke_width=4,
        stroke_fill=(0, 0, 0, 255),
    )

    # (B) Blue Box ("Full Practice Exam!")
    bbox_prac = draw.textbbox((0, 0), practice_text, font=font_practice)
    pw = bbox_prac[2] - bbox_prac[0] + 64
    ph = bbox_prac[3] - bbox_prac[1] + 32
    px2 = width - 30
    px1 = px2 - pw
    py1 = 640
    py2 = py1 + ph

    s_prac = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    s_pdraw = ImageDraw.Draw(s_prac)
    s_pdraw.rounded_rectangle([(px1 + 8, py1 + 10), (px2 + 8, py2 + 10)], radius=16, fill=(0, 0, 0, 160))
    s_prac = s_prac.filter(ImageFilter.GaussianBlur(radius=8))
    base.alpha_composite(s_prac)

    draw.rounded_rectangle(
        [(px1, py1), (px2, py2)],
        radius=16,
        fill=(0, 36, 215, 255),
        outline=(255, 255, 255, 255),
        width=5,
    )

    ptx = px1 + (pw - (bbox_prac[2] - bbox_prac[0])) // 2
    pty = py1 + (ph - (bbox_prac[3] - bbox_prac[1])) // 2 - bbox_prac[1]
    draw.text(
        (ptx, pty),
        practice_text,
        font=font_practice,
        fill=(255, 255, 255, 255),
        stroke_width=3,
        stroke_fill=(0, 0, 0, 255),
    )

    # (C) Bottom Right Badge ("New! EXAM TEST" - LARGER at 120px)
    bbox_br_new = draw.textbbox((0, 0), bottom_right_new, font=font_br_new)
    w_new = bbox_br_new[2] - bbox_br_new[0]
    bbox_br_exam = draw.textbbox((0, 0), bottom_right_exam, font=font_br_exam)
    w_exam = bbox_br_exam[2] - bbox_br_exam[0]
    h_br = max(bbox_br_new[3] - bbox_br_new[1], bbox_br_exam[3] - bbox_br_exam[1]) + 36
    w_br = w_new + w_exam + 84

    br_x2 = width - 240
    br_x1 = br_x2 - w_br
    br_y1 = 785
    br_y2 = br_y1 + h_br

    s_br = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    s_brdraw = ImageDraw.Draw(s_br)
    s_brdraw.rounded_rectangle([(br_x1 + 8, br_y1 + 10), (br_x2 + 8, br_y2 + 10)], radius=12, fill=(0, 0, 0, 160))
    s_br = s_br.filter(ImageFilter.GaussianBlur(radius=8))
    base.alpha_composite(s_br)

    draw.rounded_rectangle(
        [(br_x1, br_y1), (br_x2, br_y2)],
        radius=12,
        fill=(250, 240, 205, 255),
        outline=(0, 0, 0, 255),
        width=4,
    )
    tx_new = br_x1 + 28
    ty_new = br_y1 + (h_br - (bbox_br_new[3] - bbox_br_new[1])) // 2 - bbox_br_new[1]
    draw.text((tx_new, ty_new), bottom_right_new, font=font_br_new, fill=(0, 0, 0, 255))
    tx_exam = tx_new + w_new + 26
    ty_exam = br_y1 + (h_br - (bbox_br_exam[3] - bbox_br_exam[1])) // 2 - bbox_br_exam[1]
    draw.text((tx_exam, ty_exam), bottom_right_exam, font=font_br_exam, fill=(0, 0, 0, 255))

    # -----------------------------------------------------------------------
    # 4. Bottom Left Badges
    # -----------------------------------------------------------------------
    # 4a: Bottom Left Top Box ("High Band" in Impact font)
    bx1, by1 = 28, 725
    bbox_blt = draw.textbbox((0, 0), bottom_left_top, font=font_bot_impact)
    blt_w = bbox_blt[2] - bbox_blt[0] + 54
    blt_h = bbox_blt[3] - bbox_blt[1] + 32
    bx2, by2 = bx1 + blt_w, by1 + blt_h

    s_blt = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    s_bltdraw = ImageDraw.Draw(s_blt)
    s_bltdraw.rounded_rectangle([(bx1 + 6, by1 + 8), (bx2 + 6, by2 + 8)], radius=10, fill=(0, 0, 0, 150))
    s_blt = s_blt.filter(ImageFilter.GaussianBlur(radius=6))
    base.alpha_composite(s_blt)

    draw.rounded_rectangle([(bx1, by1), (bx2, by2)], radius=10, fill=(165, 15, 15, 250), outline=(0, 0, 0, 255), width=3)
    bl_tx = bx1 + 26
    bl_ty = by1 + (blt_h - (bbox_blt[3] - bbox_blt[1])) // 2 - bbox_blt[1]
    draw.text((bl_tx, bl_ty), bottom_left_top, font=font_bot_impact, fill=(255, 255, 255, 255), stroke_width=3, stroke_fill=(0, 0, 0, 255))

    # 4b: Bottom Left Split Boxes ("Real Practice" + "Best")
    by1_sub = by2 + 14
    bbox_bl_mid = draw.textbbox((0, 0), bottom_left_mid, font=font_bot_serif)
    bl_mid_w = bbox_bl_mid[2] - bbox_bl_mid[0] + 42
    bl_mid_h = bbox_bl_mid[3] - bbox_bl_mid[1] + 28
    bx2_mid = bx1 + bl_mid_w
    by2_sub = by1_sub + bl_mid_h

    draw.rounded_rectangle([(bx1, by1_sub), (bx2_mid, by2_sub)], radius=8, fill=(255, 255, 255, 255), outline=(0, 0, 0, 255), width=3)
    bl_mid_tx = bx1 + 20
    bl_mid_ty = by1_sub + (bl_mid_h - (bbox_bl_mid[3] - bbox_bl_mid[1])) // 2 - bbox_bl_mid[1]
    draw.text((bl_mid_tx, bl_mid_ty), bottom_left_mid, font=font_bot_serif, fill=(0, 0, 0, 255))

    bx1_best = bx2_mid + 8
    bbox_best = draw.textbbox((0, 0), bottom_left_right, font=font_bot_serif)
    best_w = bbox_best[2] - bbox_best[0] + 36
    bx2_best = bx1_best + best_w

    draw.rounded_rectangle([(bx1_best, by1_sub), (bx2_best, by2_sub)], radius=8, fill=(255, 225, 0, 255), outline=(0, 0, 0, 255), width=3)
    best_tx = bx1_best + 18
    best_ty = by1_sub + (bl_mid_h - (bbox_best[3] - bbox_best[1])) // 2 - bbox_best[1]
    draw.text((best_tx, best_ty), bottom_left_right, font=font_bot_serif, fill=(0, 0, 0, 255))

    base.alpha_composite(overlay)

    # -----------------------------------------------------------------------
    # 5. Center Diagonal Date Badge (Black & White Contrast, LARGEST Font: 168px)
    # -----------------------------------------------------------------------
    tilted_date_badge = create_tilted_badge(
        text=date_text,
        font=font_date,
        bg_color=(10, 10, 10, 255),
        border_color=(255, 255, 255, 255),
        text_color=(255, 255, 255, 255),
        border_width=10,
        padding=(68, 20),
        angle=9.5,
    )

    bw, bh = tilted_date_badge.size
    pos_x = (width - bw) // 2 - 30
    pos_y = 265

    tilted_shadow = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    alpha_mask = tilted_date_badge.split()[3]
    shadow_img = Image.new("RGBA", (bw, bh), (0, 0, 0, 195))
    shadow_img.putalpha(alpha_mask)
    tilted_shadow.paste(shadow_img, (pos_x + 14, pos_y + 18), shadow_img)
    tilted_shadow = tilted_shadow.filter(ImageFilter.GaussianBlur(radius=14))
    base.alpha_composite(tilted_shadow)

    base.paste(tilted_date_badge, (pos_x, pos_y), tilted_date_badge)

    final_rgb = base.convert("RGB")

    target_file.parent.mkdir(parents=True, exist_ok=True)
    final_rgb.save(target_file, "PNG", quality=95)
    print(f"Thumbnail saved to: {target_file}")

    root_copy = test_dir / "thumbnail.png"
    if root_copy != target_file:
        final_rgb.save(root_copy, "PNG", quality=95)
        print(f"Thumbnail copy saved to: {root_copy}")

    return target_file


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Generate YouTube thumbnail for IELTS test video")
    parser.add_argument("test_dir", help="Path to test directory (e.g. tests/test_004)")
    parser.add_argument("--output", "-o", help="Custom output image path (PNG)")
    parser.add_argument("--frame", help="Custom frame image path or index")
    parser.add_argument("--top-text", default="IELTS Listening Exam Practice", help="Text on the top banner")
    parser.add_argument("--date", help="Date text for the center diagonal strip (e.g. 14/Sep/2026)")
    parser.add_argument("--practice-text", default="Full Practice Exam!", help="Text on the blue practice badge")
    parser.add_argument("--yellow-text", default="New Hot Test!", help="Text on the yellow badge")
    parser.add_argument("--red-text", default="Band 8-9 Test", help="Text on the red badge")
    parser.add_argument("--bottom-left-top", default="High Band", help="Top text on bottom left")
    parser.add_argument("--bottom-left-mid", default="Real Practice", help="White box text on bottom left")
    parser.add_argument("--bottom-left-right", default="Best", help="Yellow box text on bottom left")
    parser.add_argument("--bottom-right-new", default="New!", help="First word on bottom right badge")
    parser.add_argument("--bottom-right-exam", default="EXAM TEST", help="Second word on bottom right badge")

    args = parser.parse_args()

    generate_thumbnail(
        test_dir=args.test_dir,
        output_path=args.output,
        custom_frame=args.frame,
        top_text=args.top_text,
        date_text=args.date,
        practice_text=args.practice_text,
        yellow_badge_text=args.yellow_text,
        red_badge_text=args.red_text,
        bottom_left_top=args.bottom_left_top,
        bottom_left_mid=args.bottom_left_mid,
        bottom_left_right=args.bottom_left_right,
        bottom_right_new=args.bottom_right_new,
        bottom_right_exam=args.bottom_right_exam,
    )


if __name__ == "__main__":
    main()
