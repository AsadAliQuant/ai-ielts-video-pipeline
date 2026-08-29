#!/usr/bin/env python3
"""
Fish Audio voice discovery and auto-selection helper.

Browse Fish Audio's public voice library, find suitable British English voices
for IELTS Listening test narration, and populate audio_config.json.

Usage:
    python select_voices.py                     # list candidate voices
    python select_voices.py --auto              # auto-pick and save to audio_config.json
    python select_voices.py --test <voice_id>   # generate a 5-second sample
"""

import argparse
import json
import os
import sys
from pathlib import Path

try:
    from dotenv import load_dotenv
    import requests
except ImportError:
    sys.exit("Missing dependencies. Run:  pip install requests python-dotenv")

ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "audio_config.json"

FISH_API = "https://api.fish.audio"


def get_api_key():
    load_dotenv(ROOT / ".env")
    key = os.getenv("FISH_AUDIO", "").strip()
    if not key or key == "your-fish-audio-api-key-here":
        sys.exit("ERROR: Set FISH_AUDIO in .env to your Fish Audio API key.\n"
                 "       Get one at https://fish.audio")
    return key


def list_voices(api_key, language="en", page_size=100, sort_by="task_count"):
    """List voices from Fish Audio's model library."""
    headers = {"Authorization": f"Bearer {api_key}"}
    params = {
        "language": language,
        "page_size": page_size,
        "sort_by": sort_by,
        "title_language": "en",
    }
    resp = requests.get(f"{FISH_API}/model", headers=headers, params=params,
                        timeout=30)
    resp.raise_for_status()
    return resp.json().get("items", [])


def display_voices(voices):
    """Pretty-print a table of voices."""
    print(f"\n{'#':<4} {'ID':<28} {'Title':<35} {'Gender':<8} {'Tags'}")
    print("-" * 110)
    for i, v in enumerate(voices, 1):
        vid = v.get("_id", "")[:26]
        title = (v.get("title", "") or "")[:33]
        # Try to infer gender from tags or description
        tags = v.get("tags", []) or []
        tag_str = ", ".join(str(t) for t in tags[:5])
        gender = ""
        for t in tags:
            tl = str(t).lower()
            if "male" in tl and "female" not in tl:
                gender = "M"
            elif "female" in tl:
                gender = "F"
        print(f"{i:<4} {vid:<28} {title:<35} {gender:<8} {tag_str}")


def _suitability_score(voice):
    """Score a voice for IELTS narration suitability (higher = better).

    Prefers: narration, educational, documentary, professional, calm, clear,
             conversational, podcast, soft, warm.
    Penalises: character-voice, entertainment, egirl, energetic, angry, horror,
               social-media, brainrot, meme.
    """
    tags = [str(t).lower() for t in (voice.get("tags") or [])]
    title = (voice.get("title") or "").lower()
    desc = (voice.get("description") or "").lower()
    all_text = " ".join(tags) + " " + title + " " + desc

    score = 0
    # Strong positive signals
    for w in ["narration", "educational", "documentary", "professional",
              "podcast", "audiobook", "calm", "clear", "warm", "neutral"]:
        if w in all_text:
            score += 10
    # Mild positive
    for w in ["conversational", "soft", "medium", "crisp", "smooth",
              "confident", "slow"]:
        if w in all_text:
            score += 5
    # Strong negative signals
    for w in ["character-voice", "entertainment", "egirl", "e-girl",
              "energetic", "angry", "horror", "brainrot", "meme",
              "social-media", "anime", "hatsune", "mortal kombat",
              "super smash", "trump", "musk", "family guy", "markiplier"]:
        if w in all_text:
            score -= 20
    # Mild negative
    for w in ["deep", "low", "high", "bright", "cheerful"]:
        if w in all_text:
            score -= 3
    return score


def auto_pick_voices(voices):
    """Auto-select voices for each IELTS speaker archetype.

    Strategy: score each voice for IELTS suitability, separate by gender,
    then pick the best unique voice for each role.
    """
    # Categorise by inferred gender and sort by suitability
    males = []
    females = []
    neutral = []

    for v in voices:
        tags = [str(t).lower() for t in (v.get("tags") or [])]
        all_text = " ".join(tags) + " " + (v.get("title") or "").lower()
        v["_score"] = _suitability_score(v)
        if "female" in all_text or "woman" in all_text or "women" in all_text:
            females.append(v)
        elif "male" in all_text or " man " in f" {all_text} ":
            males.append(v)
        else:
            neutral.append(v)

    # Sort each pool by suitability score descending
    males.sort(key=lambda v: v["_score"], reverse=True)
    females.sort(key=lambda v: v["_score"], reverse=True)
    neutral.sort(key=lambda v: v["_score"], reverse=True)

    used_ids = set()

    def pick_one(primary_pool, *fallback_pools):
        """Pick the best unused voice from primary pool, falling back."""
        for pool in [primary_pool] + list(fallback_pools):
            for v in pool:
                if v["_id"] not in used_ids:
                    used_ids.add(v["_id"])
                    return v
        # If all used, allow reuse from primary pool
        return primary_pool[0] if primary_pool else None

    # Pick voices in priority order (narrator first, most important)
    picks = {}
    picks["narrator"]            = pick_one(females, neutral, males)
    picks["receptionist_female"] = pick_one(females, neutral)
    picks["guide_female"]        = pick_one(females, neutral)
    picks["caller_female"]       = pick_one(females, neutral)
    picks["lecturer_female"]     = pick_one(females, neutral)
    picks["student_female_young"]= pick_one(females, neutral)
    picks["caller_male"]         = pick_one(males, neutral)
    picks["lecturer_male"]       = pick_one(males, neutral)
    picks["supervisor_male"]     = pick_one(males, neutral)
    picks["student_male_young"]  = pick_one(males, neutral)
    picks["student_male_2"]      = pick_one(males, neutral)

    roster = {}
    for role, voice in picks.items():
        if voice:
            roster[role] = {
                "voice_id": voice["_id"],
                "label": voice.get("title", "Unknown"),
                "score": voice.get("_score", 0),
            }
        else:
            roster[role] = {"voice_id": "", "label": "NONE", "score": 0}

    return roster


def test_voice(api_key, voice_id, text=None):
    """Generate a short audio sample to preview a voice."""
    text = text or "Good morning. Welcome to the IELTS Listening test. You will hear a number of different recordings."
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "model": "s2.1-pro-free",
    }
    payload = {
        "text": text,
        "reference_id": voice_id,
        "format": "mp3",
        "temperature": 0.3,
        "prosody": {"speed": 0.95, "volume": 0},
    }
    print(f"Generating sample for voice {voice_id}...")
    resp = requests.post(f"{FISH_API}/v1/tts", headers=headers,
                         json=payload, timeout=60)
    resp.raise_for_status()
    out_path = ROOT / f"voice_sample_{voice_id[:8]}.mp3"
    out_path.write_bytes(resp.content)
    print(f"Saved: {out_path}  ({len(resp.content)} bytes)")
    return out_path


def save_config(roster):
    """Write or update audio_config.json with the discovered voice roster."""
    if CONFIG_PATH.exists():
        config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    else:
        config = {}

    # Update the speaker_roster section
    flat_roster = {}
    for key, info in roster.items():
        flat_roster[key] = info["voice_id"]

    config["speaker_roster"] = flat_roster
    config.setdefault("_voice_labels", {})
    for key, info in roster.items():
        config["_voice_labels"][key] = info["label"]

    CONFIG_PATH.write_text(json.dumps(config, indent=2, ensure_ascii=False),
                           encoding="utf-8")
    print(f"\nSaved voice roster to {CONFIG_PATH}")


def main():
    parser = argparse.ArgumentParser(description="Discover Fish Audio voices for IELTS TTS")
    parser.add_argument("--auto", action="store_true",
                        help="auto-pick voices and save to audio_config.json")
    parser.add_argument("--test", metavar="VOICE_ID",
                        help="generate a short audio sample with the given voice ID")
    parser.add_argument("--text", default=None,
                        help="custom text for --test mode")
    args = parser.parse_args()

    api_key = get_api_key()
    
    if args.test:
        test_voice(api_key, args.test, args.text)
        return

    print("Fetching English voices from Fish Audio...")
    voices = list_voices(api_key)
    if not voices:
        sys.exit("No voices found. Check your API key and try again.")

    print(f"Found {len(voices)} English voices")
    display_voices(voices[:40])

    if args.auto:
        print("\n--- Auto-picking voices for IELTS speaker roles ---")
        roster = auto_pick_voices(voices)
        print()
        for role, info in roster.items():
            print(f"  {role:<24} -> {info['voice_id'][:20]}  ({info['label']})")
        save_config(roster)
        print("\nYou can swap any voice ID in audio_config.json at any time.")
    else:
        print("\nRun with --auto to auto-pick and save, or pick IDs manually.")


if __name__ == "__main__":
    main()
