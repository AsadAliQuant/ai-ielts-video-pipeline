# End-to-End IELTS Test Creation & YouTube Upload Guide (with ChatGPT Visuals)

This guide explains how to generate complete IELTS Listening practice tests, integrate custom ChatGPT-generated map/diagram images, and upload the final 1080p video to YouTube directly from the command line (CMD or PowerShell) without needing an AI agent or Antigravity.

---

## ⚡ Quick Start (One Command)

From the project root (`d:\Asad\Projects\AI IELTS`), run:

```powershell
python run_pipeline.py
```

This runs the entire pipeline end-to-end:
1. **Stage 1:** Generates the IELTS test paper (Band 9.0 by default, with full LLM verifier).
2. **Visual Hook:** Prints the exact prompt for ChatGPT and pauses for the image.
3. **Stage 2:** Synthesizes realistic TTS audio (`full_test.wav` and all parts).
4. **Stage 3:** Renders 1080p screens with your custom image, bakes dynamic HUD countdown timers, and muxes the MP4.
5. **Stage 4:** Generates chapters, thumbnail, and uploads the video to your YouTube channel.

---

## 🛠️ Command Options & Examples

### 1. Change Band Score
```powershell
python run_pipeline.py --band 8.5
python run_pipeline.py --band 7.5
```

### 2. Fast Mode (Skip LLM Verification Agent)
To cut generation time down from ~35 min to ~10–15 min:
```powershell
python run_pipeline.py --band 9.0 --skip-verify
```

### 3. Generate Multiple Tests Sequentially
```powershell
python run_pipeline.py --count 3 --band 9.0
```
*(The script will process each test completely before starting the next one).*

### 4. Create Video Only (No YouTube Upload)
```powershell
python run_pipeline.py --no-upload
```

### 5. Preview Commands (Dry Run)
```powershell
python run_pipeline.py --dry-run
```

---

## 🖼️ How the ChatGPT Image Step Works

When Stage 1 completes, the terminal will display a clear banner with the exact prompt:

```text
============================================================================
  IMAGE PROMPT FOR CHATGPT: HISTORIC GLASSHOUSE FLOOR PLAN (FLOORPLAN)
============================================================================
Section     : PART 2 - v1
Visual ID   : v1

Prompt to copy into ChatGPT:
----------------------------------------------------------------------------
A clean, black and white architectural floor plan of a Victorian glasshouse.
It features a central vaulted dome with symmetrical wings extending to the
left and right...
----------------------------------------------------------------------------

Target File Destination:
  D:\Asad\Projects\AI IELTS\tests\test_007\visuals\v1.png
============================================================================

Options:
  1. Paste or drag-and-drop the downloaded image path below
  2. OR save the file directly to: tests/test_007/visuals/v1.png and press Enter
  3. OR press Enter if downloaded to your Downloads folder
> Input path or press Enter: 
```

### 📁 Consistent File Placement Options:

1. **Auto-Detection (Easiest):**
   * Download the image from ChatGPT to your default `Downloads` folder.
   * Just hit **Enter** in the terminal! The script detects the newest image in Downloads and asks:
     `Found recent image in Downloads: 'image.png'. Use this? [Y/n]: `
     Press `Enter` or `Y` to confirm.

2. **Drag & Drop / Paste Path:**
   * Drag the downloaded image into your CMD/PowerShell window or paste its path (e.g. `C:\Users\Asad\Downloads\test_image.png`) and press `Enter`.

3. **Save Directly in Test Folder:**
   * Save the file directly as:
     `tests/test_NNN/visuals/v1.png`
   * Press `Enter`.

The script automatically copies the file to both `tests/test_NNN/visuals/v1.png` and `tests/test_NNN/visual_v1.png`.

---

## 🎬 What Happens Next (Automatic Stages)

Once the image is confirmed, the script continues completely hands-free:

* **Stage 2 (TTS Audio):**
  Synthesizes narrator, dialogues, and instructions with Fish Audio using standard IELTS pauses (30s preparation, 15s mid-break, 60s checking).

* **Stage 3 (Video Compilation):**
  Uses Playwright to render the exam screens embedding your ChatGPT image, bakes the ticking HUD countdown timers using Pillow, and renders the final 1080p MP4 via fast FFmpeg muxing.

* **Stage 4 (YouTube Upload):**
  Reads your OAuth credentials in `.env`, sets the title, description, and timestamps, uploads the custom thumbnail, and prints your live YouTube URL:
  ```text
  Uploading tests\test_007\video\test_007.mp4 ...
  Uploaded: https://youtu.be/xxxxxxxxxxx
  Custom thumbnail set successfully on YouTube!
  ```

---

## 🔧 Alternative: Using `batch_generate.py`

You can also use the full `batch_generate.py` script directly:

```powershell
# Run 1 test with ChatGPT pause and YouTube upload:
python batch_generate.py 1 --chatgpt --upload --fast

# Fast test without verification:
python batch_generate.py 1 --chatgpt --upload --fast --skip-verify
```
