"""
Overlay clear IELTS labels & question markers onto AI-generated diagram using Pillow.
"""

import os
from PIL import Image, ImageDraw, ImageFont

def create_ielts_labeled_diagram(
    input_image_path: str,
    output_image_path: str,
    title: str = "Museum Ground Floor Plan",
):
    # Load base image
    img = Image.open(input_image_path).convert("RGBA")
    draw = ImageDraw.Draw(img)

    # Font setup
    font_path = "C:/Windows/Fonts/arial.ttf"
    font_bold_path = "C:/Windows/Fonts/arialbd.ttf"
    
    font_title = ImageFont.truetype(font_bold_path, 26)
    font_label = ImageFont.truetype(font_bold_path, 16)
    font_badge = ImageFont.truetype(font_bold_path, 18)

    # 1. Header / Title banner
    draw.rectangle([(20, 20), (1004, 75)], fill=(255, 255, 255, 240), outline=(0, 0, 0, 255), width=2)
    draw.text((40, 32), title.upper(), fill=(0, 0, 0), font=font_title)
    draw.text((760, 36), "Questions 11 - 16", fill=(80, 80, 80), font=font_label)

    # 2. Compass Rose (Top Right)
    cx, cy = 940, 130
    draw.ellipse([(cx-25, cy-25), (cx+25, cy+25)], fill=(255, 255, 255, 240), outline=(0, 0, 0), width=2)
    draw.line([(cx, cy-22), (cx, cy+22)], fill=(0, 0, 0), width=2)
    draw.line([(cx-22, cy), (cx+22, cy)], fill=(0, 0, 0), width=2)
    draw.text((cx-6, cy-42), "N", fill=(0, 0, 0), font=font_badge)

    # Helper function to draw an IELTS Question Badge (letter in a box)
    def draw_badge(x, y, letter):
        box_w, box_h = 36, 36
        draw.rectangle(
            [(x - box_w // 2, y - box_h // 2), (x + box_w // 2, y + box_h // 2)],
            fill=(255, 255, 255, 255),
            outline=(0, 0, 0),
            width=2,
        )
        bbox = draw.textbbox((0, 0), letter, font=font_badge)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        draw.text((x - tw // 2, y - th // 2 - 2), letter, fill=(0, 0, 0), font=font_badge)

    # Helper function to draw landmark text with clean background
    def draw_text_label(x, y, text, align="center"):
        bbox = draw.textbbox((0, 0), text, font=font_label)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        
        if align == "center":
            tx = x - tw // 2
        elif align == "left":
            tx = x
        else:
            tx = x - tw

        ty = y - th // 2
        pad = 4
        draw.rectangle(
            [(tx - pad, ty - pad), (tx + tw + pad, ty + th + pad)],
            fill=(255, 255, 255, 220),
            outline=(150, 150, 150),
            width=1
        )
        draw.text((tx, ty), text, fill=(0, 0, 0), font=font_label)

    # 3. Add Fixed Landmarks (known to candidate)
    draw_text_label(495, 320, "North Wing")
    draw_text_label(380, 500, "Central Corridor")
    draw_text_label(500, 605, "Main Entrance", align="center")
    draw_text_label(500, 740, "Courtyard")

    # 4. Add Question Option Badges (A - G) at diagram locations
    draw_badge(325, 320, "A")   # West Wing / Left Room
    draw_badge(495, 260, "B")   # Gallery Room
    draw_badge(720, 410, "C")   # East Gallery
    draw_badge(720, 540, "D")   # Gift Shop / Cafe
    draw_badge(600, 520, "E")   # Info Desk
    draw_badge(290, 725, "F")   # Maintenance Shed
    draw_badge(695, 755, "G")   # Station Platform

    # Convert to RGB and save
    final_img = img.convert("RGB")
    final_img.save(output_image_path, "PNG")
    print(f"IELTS labeled diagram generated: {output_image_path}")

if __name__ == "__main__":
    script_dir = os.path.dirname(os.path.abspath(__file__))
    input_file = os.path.join(script_dir, "flux_raw_output.png")
    output_file = os.path.join(script_dir, "ielts_final_diagram.png")
    create_ielts_labeled_diagram(input_file, output_file)
