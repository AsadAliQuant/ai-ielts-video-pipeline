#!/usr/bin/env python3
"""
IELTS Listening Test — Audio Generator.

Converts a generated IELTS Listening test (test.json) into exam-grade audio
using Fish Audio's S2.1 Pro TTS model, faithfully reproducing the structure,
pacing, pauses, narrator instructions, and multi-voice format of a real IELTS
Listening recording.

Usage:
    python generate_audio.py tests/test_007/
    python generate_audio.py tests/test_007/ --format mp3
    python generate_audio.py tests/test_007/ --no-combined

Requires:
    - FISH_AUDIO API key in .env
    - ffmpeg on PATH (for mp3 output; wav works without it)
    - pip install requests python-dotenv
"""

import argparse
import io
import json
import os
import struct
import subprocess
import sys
import time
import wave
from pathlib import Path

try:
    from dotenv import load_dotenv
    import requests
except ImportError:
    sys.exit("Missing dependencies. Run:  pip install requests python-dotenv")

ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "audio_config.json"

FISH_API = "https://api.fish.audio"


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

def load_config():
    """Load audio_config.json — all voice IDs, timing, narrator scripts."""
    if not CONFIG_PATH.exists():
        sys.exit(f"ERROR: {CONFIG_PATH} not found.\n"
                 f"       Run: python select_voices.py --auto")
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def get_api_key():
    load_dotenv(ROOT / ".env")
    key = os.getenv("FISH_AUDIO", "").strip()
    if not key or key == "your-fish-audio-api-key-here":
        sys.exit("ERROR: Set FISH_AUDIO in .env to your Fish Audio API key.")
    return key


# ---------------------------------------------------------------------------
# WAV utilities (stdlib only — no pydub, no audioop)
# ---------------------------------------------------------------------------

def make_silence_wav(duration_sec, sample_rate=44100, channels=1,
                     sample_width=2):
    """Create a silent WAV file as bytes."""
    num_samples = int(duration_sec * sample_rate) * channels
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(sample_width)
        wf.setframerate(sample_rate)
        wf.writeframes(b"\x00" * num_samples * sample_width)
    return buf.getvalue()


def read_wav_params(wav_bytes):
    """Read WAV parameters (channels, sampwidth, framerate, nframes)."""
    buf = io.BytesIO(wav_bytes)
    with wave.open(buf, "rb") as wf:
        return {
            "channels": wf.getnchannels(),
            "sampwidth": wf.getsampwidth(),
            "framerate": wf.getframerate(),
            "nframes": wf.getnframes(),
            "duration_sec": wf.getnframes() / wf.getframerate(),
        }


def read_wav_frames(wav_bytes):
    """Read raw PCM frames from a WAV file."""
    buf = io.BytesIO(wav_bytes)
    with wave.open(buf, "rb") as wf:
        return wf.readframes(wf.getnframes()), wf.getparams()


def concatenate_wavs(wav_bytes_list, target_rate=44100):
    """Concatenate multiple WAV byte strings into one.

    All inputs are assumed to be PCM WAV. If sample rates differ, ffmpeg is
    used to resample. The result is mono or stereo depending on the first
    segment's channel count.
    """
    if not wav_bytes_list:
        return make_silence_wav(0.1, target_rate)

    # Normalise all segments to the target sample rate using ffmpeg if needed
    normalised = []
    ref_channels = None
    ref_sampwidth = None

    for wav_bytes in wav_bytes_list:
        params = read_wav_params(wav_bytes)
        if ref_channels is None:
            ref_channels = params["channels"]
            ref_sampwidth = params["sampwidth"]

        if (params["framerate"] != target_rate or
                params["channels"] != ref_channels or
                params["sampwidth"] != ref_sampwidth):
            # Resample with ffmpeg
            wav_bytes = ffmpeg_resample(wav_bytes, target_rate, ref_channels,
                                        ref_sampwidth)

        frames, _ = read_wav_frames(wav_bytes)
        normalised.append(frames)

    # Write concatenated output
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(ref_channels)
        wf.setsampwidth(ref_sampwidth)
        wf.setframerate(target_rate)
        for frames in normalised:
            wf.writeframes(frames)
    return buf.getvalue()


def ffmpeg_resample(wav_bytes, target_rate, target_channels, target_sampwidth):
    """Use ffmpeg to resample/rechannelize a WAV segment."""
    acodec = "pcm_s16le" if target_sampwidth == 2 else "pcm_s24le"
    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-f", "wav", "-i", "pipe:0",
        "-ar", str(target_rate),
        "-ac", str(target_channels),
        "-acodec", acodec,
        "-f", "wav", "pipe:1",
    ]
    try:
        result = subprocess.run(cmd, input=wav_bytes, capture_output=True,
                                timeout=30)
        if result.returncode == 0:
            return result.stdout
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    # If ffmpeg fails, return original — best effort
    print("    WARNING: ffmpeg resample failed, using original sample rate")
    return wav_bytes


def wav_to_mp3(wav_bytes, mp3_path, bitrate="192k"):
    """Convert WAV bytes to MP3 file using ffmpeg."""
    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-f", "wav", "-i", "pipe:0",
        "-b:a", bitrate,
        "-q:a", "2",
        str(mp3_path),
    ]
    try:
        result = subprocess.run(cmd, input=wav_bytes, capture_output=True,
                                timeout=120)
        if result.returncode != 0:
            print(f"    WARNING: ffmpeg mp3 conversion failed: "
                  f"{result.stderr.decode()[:200]}")
            return False
        return True
    except FileNotFoundError:
        sys.exit("ERROR: ffmpeg not found. Install it for MP3 output.\n"
                 "       WAV output works without ffmpeg.")


def save_wav(wav_bytes, path):
    """Save WAV bytes to a file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(wav_bytes)
    return path


# ---------------------------------------------------------------------------
# Fish Audio TTS client
# ---------------------------------------------------------------------------

class FishTTS:
    """Thin wrapper around Fish Audio's /v1/tts endpoint."""

    def __init__(self, api_key, config):
        self.api_key = api_key
        self.model = config.get("model", "s2.1-pro-free")
        self.sample_rate = config.get("sample_rate", 44100)
        self.calls = 0

    def _headers(self):
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "model": self.model,
        }

    def synthesize(self, text, reference_id, temperature=0.7, top_p=0.7,
                   speed=1.0, max_retries=3):
        """Synthesize text to WAV audio bytes.

        reference_id: single string for one speaker, or list of strings
                      for multi-speaker mode.
        """
        payload = {
            "text": text,
            "reference_id": reference_id,
            "temperature": temperature,
            "top_p": top_p,
            "prosody": {
                "speed": speed,
                "volume": 0,
                "normalize_loudness": True,
            },
            "format": "wav",
            "sample_rate": self.sample_rate,
            "normalize": True,
            "chunk_length": 300,
            "repetition_penalty": 1.2,
        }

        for attempt in range(1, max_retries + 1):
            try:
                resp = requests.post(
                    f"{FISH_API}/v1/tts",
                    headers=self._headers(),
                    json=payload,
                    timeout=180,
                )
                resp.raise_for_status()
                self.calls += 1
                if len(resp.content) < 100:
                    raise RuntimeError(f"TTS returned only {len(resp.content)} bytes")
                return resp.content
            except (requests.exceptions.RequestException, RuntimeError) as e:
                wait = 2 ** attempt
                print(f"    TTS attempt {attempt}/{max_retries} failed: {e}")
                if attempt < max_retries:
                    print(f"    retrying in {wait}s...")
                    time.sleep(wait)
                else:
                    raise RuntimeError(
                        f"TTS failed after {max_retries} attempts: {e}") from e


# ---------------------------------------------------------------------------
# Speaker voice assignment
# ---------------------------------------------------------------------------

class VoiceAssigner:
    """Map speaker names from transcript to Fish Audio voice IDs."""

    def __init__(self, config):
        self.roster = config.get("speaker_roster", {})
        self.hints = config.get("speaker_mapping_hints", {})
        self.narrator_id = config.get("narrator", {}).get("voice_id",
                            self.roster.get("narrator", ""))
        self._cache = {}
        self._used_roster_keys = set()

    def get_voice_id(self, speaker_name, speaker_role=""):
        """Return the Fish Audio voice ID for a given speaker name."""
        key = speaker_name.strip()
        if key in self._cache:
            return self._cache[key]

        if key.lower() == "narrator":
            self._cache[key] = self.narrator_id
            return self.narrator_id

        # Match via hints (keywords in speaker name/role)
        combined = f"{key} {speaker_role}".lower()
        for hint_keyword, roster_key in self.hints.items():
            if hint_keyword.startswith("_"):
                continue
            if hint_keyword.lower() in combined:
                voice_id = self.roster.get(roster_key, "")
                if voice_id:
                    self._cache[key] = voice_id
                    self._used_roster_keys.add(roster_key)
                    return voice_id

        # Fallback: cycle through unused roster voices
        for roster_key, voice_id in self.roster.items():
            if roster_key not in self._used_roster_keys and voice_id:
                self._cache[key] = voice_id
                self._used_roster_keys.add(roster_key)
                return voice_id

        self._cache[key] = self.narrator_id
        return self.narrator_id

    def get_narrator_id(self):
        return self.narrator_id


# ---------------------------------------------------------------------------
# Transcript parsing and multi-speaker tag building
# ---------------------------------------------------------------------------

def parse_transcript_lines(part):
    """Extract (speaker, line) pairs from a part's transcript."""
    transcript = part.get("transcript", [])
    if isinstance(transcript, dict):
        transcript = [transcript]
    lines = []
    for entry in transcript:
        speaker = str(entry.get("speaker", "Speaker")).strip()
        text = str(entry.get("line", "")).strip()
        if text:
            lines.append((speaker, text))
    return lines


def build_speaker_roles(part):
    """Build a dict of speaker_name -> role from blueprint speakers."""
    roles = {}
    for sp in part.get("speakers", []):
        name = sp.get("name", "").strip()
        role = sp.get("role", "").strip()
        if name:
            roles[name] = role
    return roles


def split_transcript_for_midbreak(lines, part_no):
    """Split transcript lines into two halves for mid-section break.

    Parts 1-3 get a mid-section break. Part 4 does not.
    Returns (first_half, second_half) or (all_lines, []) for part 4.
    """
    if part_no == 4:
        return lines, []

    content_lines = [(s, t) for s, t in lines if s.lower() != "narrator"]
    if len(content_lines) <= 4:
        return lines, []

    # Split at the midpoint of content
    mid = len(content_lines) // 2
    narrator_lines = [(s, t) for s, t in lines if s.lower() == "narrator"]
    first_half = narrator_lines + content_lines[:mid]
    second_half = content_lines[mid:]

    return first_half, second_half


def build_multispeaker_text(lines, voice_assigner, speaker_roles):
    """Build Fish Audio multi-speaker tagged text and reference_id list.

    Returns (tagged_text, reference_id) where reference_id is:
      - a single string for one speaker
      - a list of strings for multi-speaker
    """
    speaker_order = []
    seen = set()
    for speaker, _ in lines:
        if speaker.lower() == "narrator":
            continue
        if speaker not in seen:
            speaker_order.append(speaker)
            seen.add(speaker)

    if not speaker_order:
        return "", ""

    # Single speaker
    if len(speaker_order) == 1:
        sp = speaker_order[0]
        role = speaker_roles.get(sp, "")
        voice_id = voice_assigner.get_voice_id(sp, role)
        text = " ".join(t for s, t in lines if s.lower() != "narrator")
        return text, voice_id

    # Multi-speaker
    speaker_to_idx = {sp: i for i, sp in enumerate(speaker_order)}
    voice_ids = [voice_assigner.get_voice_id(sp, speaker_roles.get(sp, ""))
                 for sp in speaker_order]

    parts = []
    for speaker, text in lines:
        if speaker.lower() == "narrator":
            continue
        idx = speaker_to_idx[speaker]
        parts.append(f"<|speaker:{idx}|>{text}")

    return "".join(parts), voice_ids


# ---------------------------------------------------------------------------
# Narrator script generation
# ---------------------------------------------------------------------------

def get_part_question_ranges(part_no, part):
    """Determine question ranges for the two halves of a part."""
    groups = part.get("question_groups", [])
    q_from = (part_no - 1) * 10 + 1
    q_to = part_no * 10

    if part_no == 4:
        # Part 4 has no mid-break
        return q_from, q_to, q_to, q_to

    if len(groups) >= 2:
        # Use exact question group boundary
        first_group = groups[0]
        q_from = first_group.get("from", q_from)
        q_mid = first_group.get("to", q_from + 4)
        q_mid_next = q_mid + 1
    else:
        q_mid = q_from + 4
        q_mid_next = q_mid + 1

    return q_from, q_mid, q_mid_next, q_to


def narrator_situation(config, part_no, part):
    scripts = config.get("narrator_scripts", {})
    q_from, q_mid, _, _ = get_part_question_ranges(part_no, part)

    situation = str(part.get("situation", "")).strip()
    if situation.lower().startswith("you will hear"):
        situation = situation[len("you will hear"):].strip()

    if not situation:
        topic = part.get("topic", f"Part {part_no}")
        situation = (f"a conversation about {topic}" if part_no in (1, 3)
                     else f"a talk about {topic}")

    return scripts.get("situation", "").format(
        situation=situation, q_from=q_from, q_mid=q_mid)


def narrator_now_listen(config, part_no, part, first_half=True):
    scripts = config.get("narrator_scripts", {})
    q_from, q_mid, q_mid_next, q_to = get_part_question_ranges(part_no, part)

    if first_half:
        return scripts.get("now_listen_first", "").format(
            q_from=q_from, q_mid=q_mid)
    return scripts.get("now_listen_rest", "").format(
        q_mid_next=q_mid_next, q_to=q_to)


def narrator_mid_break(config, part_no, part):
    scripts = config.get("narrator_scripts", {})
    _, _, q_mid_next, q_to = get_part_question_ranges(part_no, part)
    return scripts.get("mid_break", "").format(
        q_mid_next=q_mid_next, q_to=q_to)


def narrator_end_part(config, part_no):
    scripts = config.get("narrator_scripts", {})
    return scripts.get("end_part", "").format(part_number=part_no)


def narrator_turn_to(config, next_part):
    scripts = config.get("narrator_scripts", {})
    return scripts.get("turn_to_next", "").format(next_part=next_part)


# ---------------------------------------------------------------------------
# TTS helpers
# ---------------------------------------------------------------------------

def synth_narrator(tts, config, text, label="narrator"):
    """Synthesize a narrator line with narrator-specific low-temperature settings."""
    ncfg = config.get("narrator", {})
    preview = text[:70].replace("\n", " ")
    print(f"    TTS [{label}]: {preview}...")
    return tts.synthesize(
        text=text,
        reference_id=ncfg.get("voice_id", config["speaker_roster"]["narrator"]),
        temperature=ncfg.get("temperature", 0.3),
        top_p=ncfg.get("top_p", 0.7),
        speed=ncfg.get("speed", 0.92),
    )


def synth_dialogue(tts, config, tagged_text, voice_ids, label="dialogue"):
    """Synthesize a dialogue or monologue segment."""
    defaults = config.get("speaker_defaults", {})
    preview = tagged_text[:80].replace("\n", " ")
    print(f"    TTS [{label}]: {preview}...")
    return tts.synthesize(
        text=tagged_text,
        reference_id=voice_ids,
        temperature=defaults.get("temperature", 0.7),
        top_p=defaults.get("top_p", 0.7),
        speed=defaults.get("speed", 0.95),
    )


# ---------------------------------------------------------------------------
# Assembly pipeline
# ---------------------------------------------------------------------------

def assemble_part(tts, config, part_no, part, voice_assigner, seg_dir):
    """Assemble all audio segments for one IELTS Listening part.

    Returns a list of WAV byte strings in playback order.
    """
    timing = config.get("timing", {})
    sr = config.get("sample_rate", 44100)

    print(f"\n  Part {part_no}:")

    all_lines = parse_transcript_lines(part)
    speaker_roles = build_speaker_roles(part)
    first_half, second_half = split_transcript_for_midbreak(all_lines, part_no)

    wavs = []

    # 1. Narrator: situation intro
    text = narrator_situation(config, part_no, part)
    if text:
        wav = synth_narrator(tts, config, text, f"P{part_no} intro")
        save_wav(wav, seg_dir / f"part_{part_no}_01_narrator_intro.wav")
        wavs.append(wav)

    # 2. Preparation silence (30s)
    prep = timing.get("preparation_time_sec", 30)
    wavs.append(make_silence_wav(prep, sr))
    print(f"    [silence: {prep}s preparation]")

    # 3. Narrator: "Now listen carefully..."
    text = narrator_now_listen(config, part_no, part, first_half=True)
    if text:
        wav = synth_narrator(tts, config, text, f"P{part_no} listen")
        save_wav(wav, seg_dir / f"part_{part_no}_02_narrator_listen.wav")
        wavs.append(wav)

    # 4. Dialogue first half
    dialogue_lines = first_half if second_half else all_lines
    content = [(s, t) for s, t in dialogue_lines if s.lower() != "narrator"]
    if content:
        tagged, vids = build_multispeaker_text(content, voice_assigner,
                                                speaker_roles)
        if tagged:
            wav = synth_dialogue(tts, config, tagged, vids, f"P{part_no} dial-1")
            save_wav(wav, seg_dir / f"part_{part_no}_03_dialogue_1.wav")
            wavs.append(wav)

    # 5. Mid-section break (Parts 1-3 only)
    if second_half:
        text = narrator_mid_break(config, part_no, part)
        if text:
            wav = synth_narrator(tts, config, text, f"P{part_no} mid")
            save_wav(wav, seg_dir / f"part_{part_no}_04_narrator_mid.wav")
            wavs.append(wav)

        mid_t = timing.get("mid_part_break_sec", 30)
        wavs.append(make_silence_wav(mid_t, sr))
        print(f"    [silence: {mid_t}s mid-break]")

        text = narrator_now_listen(config, part_no, part, first_half=False)
        if text:
            wav = synth_narrator(tts, config, text, f"P{part_no} listen-2")
            save_wav(wav, seg_dir / f"part_{part_no}_05_narrator_listen2.wav")
            wavs.append(wav)

        content2 = [(s, t) for s, t in second_half if s.lower() != "narrator"]
        if content2:
            tagged, vids = build_multispeaker_text(content2, voice_assigner,
                                                    speaker_roles)
            if tagged:
                wav = synth_dialogue(tts, config, tagged, vids,
                                     f"P{part_no} dial-2")
                save_wav(wav, seg_dir / f"part_{part_no}_06_dialogue_2.wav")
                wavs.append(wav)

    # 6. Narrator: end of part
    text = narrator_end_part(config, part_no)
    if text:
        wav = synth_narrator(tts, config, text, f"P{part_no} end")
        save_wav(wav, seg_dir / f"part_{part_no}_07_narrator_end.wav")
        wavs.append(wav)

    # 7. Checking silence (30s)
    chk = timing.get("checking_time_sec", 30)
    wavs.append(make_silence_wav(chk, sr))
    print(f"    [silence: {chk}s checking]")

    return wavs


def assemble_full_test(tts, config, test_data, voice_assigner, audio_dir):
    """Assemble the complete IELTS Listening test audio.

    Saves:
        audio/part_1.wav ... audio/part_4.wav
        audio/segments/  (individual narrator/dialogue segments)

    Returns (full_wav_bytes, part_wavs_dict).
    """
    timing = config.get("timing", {})
    sr = config.get("sample_rate", 44100)
    seg_dir = audio_dir / "segments"
    seg_dir.mkdir(parents=True, exist_ok=True)

    parts_data = test_data.get("parts", [])
    if len(parts_data) != 4:
        print(f"  WARNING: Expected 4 parts, got {len(parts_data)}")

    full_wavs = []  # all WAV segments in playback order
    part_wavs = {}  # part_no -> concatenated WAV bytes

    # --- Test intro ---
    print("\n  Intro:")
    intro_text = config.get("narrator_scripts", {}).get("intro", "")
    if intro_text:
        wav = synth_narrator(tts, config, intro_text, "test intro")
        save_wav(wav, seg_dir / "intro.wav")
        full_wavs.append(wav)
        full_wavs.append(make_silence_wav(timing.get("intro_pause_sec", 2), sr))

    # --- Each part ---
    for part_no, part in enumerate(parts_data, start=1):
        part_segs = assemble_part(tts, config, part_no, part,
                                   voice_assigner, seg_dir)

        # Concatenate this part's segments and save
        part_wav = concatenate_wavs(part_segs, sr)
        part_path = audio_dir / f"part_{part_no}.wav"
        save_wav(part_wav, part_path)
        part_dur = read_wav_params(part_wav)["duration_sec"]
        print(f"  -> Saved: {part_path.name}  ({part_dur:.1f}s)")
        part_wavs[part_no] = part_wav

        full_wavs.extend(part_segs)

        # Between parts: gap + "Now turn to Part N"
        if part_no < 4:
            gap = timing.get("between_parts_sec", 3)
            full_wavs.append(make_silence_wav(gap, sr))

            turn_text = narrator_turn_to(config, part_no + 1)
            if turn_text:
                wav = synth_narrator(tts, config, turn_text,
                                     f"turn to P{part_no+1}")
                save_wav(wav, seg_dir / f"turn_to_part_{part_no+1}.wav")
                full_wavs.append(wav)

    # --- End of test ---
    print("\n  Closing:")
    end_text = config.get("narrator_scripts", {}).get("end_test", "")
    if end_text:
        wav = synth_narrator(tts, config, end_text, "test end")
        save_wav(wav, seg_dir / "end_test.wav")
        full_wavs.append(wav)

    # Concatenate everything
    print("\n  Assembling full test audio...")
    full_wav = concatenate_wavs(full_wavs, sr)

    return full_wav, part_wavs


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def generate_test_audio(test_dir, out_format="wav", no_combined=False):
    """Main entry: generate audio for a test directory. Returns list of files."""
    test_dir = Path(test_dir)
    test_json = test_dir / "test.json"
    if not test_json.exists():
        sys.exit(f"ERROR: {test_json} not found. Generate a test first.")

    test_data = json.loads(test_json.read_text(encoding="utf-8"))
    config = load_config()
    api_key = get_api_key()

    title = test_data.get("metadata", {}).get("title", "Unknown")
    print(f"IELTS Audio Generator")
    print(f"{'=' * 60}")
    print(f"Test      : {test_dir}")
    print(f"Title     : {title}")
    print(f"Model     : {config.get('model', 's2.1-pro-free')}")
    print(f"Format    : {out_format}")

    tts = FishTTS(api_key, config)
    voice_assigner = VoiceAssigner(config)

    audio_dir = test_dir / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)

    full_wav, part_wavs = assemble_full_test(tts, config, test_data,
                                              voice_assigner, audio_dir)

    written = []
    mp3_br = f"{config.get('mp3_bitrate', 192)}k"

    # Convert part files
    for pn in range(1, 5):
        if out_format == "mp3":
            mp3_path = audio_dir / f"part_{pn}.mp3"
            wav_path = audio_dir / f"part_{pn}.wav"
            if wav_path.exists():
                wav_to_mp3(wav_path.read_bytes(), mp3_path, mp3_br)
                wav_path.unlink()
                written.append(f"audio/part_{pn}.mp3")
        else:
            written.append(f"audio/part_{pn}.wav")

    # Convert segment files
    if out_format == "mp3":
        seg_dir = audio_dir / "segments"
        if seg_dir.exists():
            for wf in sorted(seg_dir.glob("*.wav")):
                wav_to_mp3(wf.read_bytes(), wf.with_suffix(".mp3"), mp3_br)
                wf.unlink()

    # Full combined file
    if not no_combined:
        ext = out_format
        full_path = audio_dir / f"full_test.{ext}"
        if out_format == "mp3":
            wav_to_mp3(full_wav, full_path, mp3_br)
        else:
            save_wav(full_wav, full_path)

        full_dur = read_wav_params(full_wav)["duration_sec"]
        print(f"\n  -> Saved: full_test.{ext}  ({full_dur:.1f}s = "
              f"{full_dur/60:.1f} min)")
        written.append(f"audio/full_test.{ext}")

    # Summary
    total_dur = read_wav_params(full_wav)["duration_sec"]
    print(f"\n{'=' * 60}")
    print(f"Audio generation complete")
    print(f"TTS calls : {tts.calls}")
    print(f"Output    : {audio_dir}")
    print(f"Files     : {', '.join(written)}")
    print(f"Duration  : {total_dur:.0f}s ({total_dur/60:.1f} min)")
    print(f"{'=' * 60}")

    return written


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Generate IELTS Listening test audio from test.json")
    parser.add_argument("test_dir",
                        help="path to test directory (e.g. tests/test_007)")
    parser.add_argument("--format", default="wav", choices=["wav", "mp3"],
                        help="output audio format (default: wav)")
    parser.add_argument("--no-combined", action="store_true",
                        help="skip generating the combined full_test file")
    parser.add_argument("--config", default=None,
                        help="path to audio_config.json (default: auto-detect)")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)

    global CONFIG_PATH
    if args.config:
        CONFIG_PATH = Path(args.config)

    test_dir = Path(args.test_dir)
    if not test_dir.is_absolute():
        test_dir = ROOT / test_dir

    generate_test_audio(test_dir, out_format=args.format,
                        no_combined=args.no_combined)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit("\nInterrupted.")
