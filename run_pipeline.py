#!/usr/bin/env python3
"""
Simple CLI shortcut to run the IELTS end-to-end pipeline with ChatGPT visuals and YouTube upload.

Usage:
    python run_pipeline.py                       # 1 test, Band 9.0, full verify, upload
    python run_pipeline.py --band 8.5            # Specify target band score
    python run_pipeline.py --skip-verify         # Fast test paper generation (~15 min)
    python run_pipeline.py --count 2             # Generate 2 tests sequentially
    python run_pipeline.py --dry-run             # Dry run preview
"""
import sys
from batch_generate import main

if __name__ == "__main__":
    extra_args = []
    args_str = " ".join(sys.argv[1:])
    if "--chatgpt" not in args_str and "--interactive-visual" not in args_str:
        extra_args.append("--chatgpt")
    if "--upload" not in args_str and "--no-upload" not in args_str:
        extra_args.append("--upload")
    if "--fast" not in args_str:
        extra_args.append("--fast")

    filtered_argv = [sys.argv[0]] + [a for a in sys.argv[1:] if a != "--no-upload"] + extra_args
    sys.exit(main(filtered_argv[1:]))
