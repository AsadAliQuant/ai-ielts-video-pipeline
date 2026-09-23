#!/usr/bin/env python3
"""
Launch the IELTS Video Pipeline Studio WebUI.
Starts the Astro + shadcn/ui local server and opens http://localhost:4321 in your browser.
"""
import os
import subprocess
import sys
import time
import threading
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
WEBAPP_DIR = ROOT / "webapp"

def open_browser():
    time.sleep(2.5)
    webbrowser.open("http://localhost:4321")

def main():
    print("=" * 65)
    print("  🎬 Starting IELTS Video Pipeline Studio (Astro + shadcn/ui)")
    print("  🌐 WebUI Address: http://localhost:4321")
    print("=" * 65)

    if not WEBAPP_DIR.exists():
        sys.exit(f"Error: {WEBAPP_DIR} does not exist.")

    threading.Thread(target=open_browser, daemon=True).start()

    cmd = ["npm", "run", "studio"]
    try:
        subprocess.run(cmd, cwd=str(WEBAPP_DIR), shell=True)
    except KeyboardInterrupt:
        print("\nStudio WebUI server stopped.")

if __name__ == "__main__":
    main()
