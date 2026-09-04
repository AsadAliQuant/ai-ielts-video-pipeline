"""
Stage 3: Timeline Reconstruction

Reconstructs the exact audio playback timeline deterministically from WAV
segments and audio_config.json timing constants, with zero external API calls.
"""

import io
import json
import sys
import wave
from pathlib import Path

# Add project root to path for imports
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from generate_audio import get_part_question_ranges


def read_segment_duration_bytes(path: Path, sample_rate: int = 44100,
                                channels: int = 1, sample_width: int = 2) -> float:
    """Calculate WAV duration via raw file size byte math.

    Bypasses broken/placeholder RIFF/data chunk headers emitted by streaming TTS.
    """
    if not path.exists():
        return 0.0
    size = path.stat().st_size
    if size <= 44:
        return 0.0
    return (size - 44) / (sample_rate * channels * sample_width)


def get_ground_truth_duration(full_wav_path: Path) -> float:
    """Read the true duration of the assembled full_test.wav via wave module."""
    if not full_wav_path.exists():
        return 0.0
    with wave.open(str(full_wav_path), "rb") as wf:
        return wf.getnframes() / wf.getframerate()


def build_timeline(test_dir: str | Path, config_path: str | Path = None) -> dict:
    """Reconstruct the timeline for a given test directory.

    Writes tests/test_NNN/video/timeline.json and returns the timeline dict.
    """
    test_dir = Path(test_dir)
    test_json_path = test_dir / "test.json"
    if not test_json_path.exists():
        raise FileNotFoundError(f"Missing {test_json_path}")

    test_data = json.loads(test_json_path.read_text(encoding="utf-8"))

    if config_path is None:
        config_path = ROOT / "audio_config.json"
    else:
        config_path = Path(config_path)

    if not config_path.exists():
        raise FileNotFoundError(f"Missing audio config: {config_path}")

    audio_config = json.loads(config_path.read_text(encoding="utf-8"))
    timing = audio_config.get("timing", {})
    sample_rate = audio_config.get("sample_rate", 44100)

    audio_dir = test_dir / "audio"
    seg_dir = audio_dir / "segments"
    if not seg_dir.exists():
        raise FileNotFoundError(
            f"Missing segments directory: {seg_dir}\n"
            "Audio segments must be present in WAV format to reconstruct the timeline."
        )

    parts_data = test_data.get("parts", [])
    narrator_gap = timing.get("narrator_gap_sec", 3)
    segments = []
    current_time = 0.0

    def add_segment(kind: str, duration: float, part_num: int | None = None,
                    q_from: int | None = None, q_to: int | None = None,
                    countdown: int | None = None, audio_file: str | None = None):
        nonlocal current_time
        if duration <= 0:
            return
        start = round(current_time, 4)
        end = round(current_time + duration, 4)
        seg = {
            "kind": kind,
            "part": part_num,
            "start": start,
            "end": end,
            "duration": round(duration, 4),
            "q_from": q_from,
            "q_to": q_to,
        }
        if countdown is not None:
            seg["countdown"] = countdown
        if audio_file:
            seg["audio_file"] = audio_file
        segments.append(seg)
        current_time = end

    # 1. Test Introduction
    intro_file = seg_dir / "intro.wav"
    if intro_file.exists():
        d = read_segment_duration_bytes(intro_file, sample_rate)
        add_segment(kind="intro", duration=d, part_num=None, audio_file="intro.wav")
        intro_pause = timing.get("intro_pause_sec", 2)
        if intro_pause > 0:
            add_segment(kind="intro_pause", duration=intro_pause, part_num=None)

    def add_gap(part_num, q_from, q_to):
        """Mirror generate_audio.assemble_part's add_gap(). No countdown."""
        if narrator_gap > 0:
            add_segment(kind="gap", duration=narrator_gap, part_num=part_num,
                        q_from=q_from, q_to=q_to)

    # 2. Parts 1 through 4
    for part_no, part in enumerate(parts_data, start=1):
        q_from, q_mid, q_mid_next, q_to = get_part_question_ranges(part_no, part)

        # Part Intro Narrator
        p_intro = seg_dir / f"part_{part_no}_01_narrator_intro.wav"
        if p_intro.exists():
            d = read_segment_duration_bytes(p_intro, sample_rate)
            add_segment(kind="narr_intro", duration=d, part_num=part_no,
                        q_from=q_from, q_to=q_mid,
                        audio_file=p_intro.name)

        # Preparation Time (Silence + Countdown)
        prep_sec = timing.get("preparation_time_sec", 30)
        if prep_sec > 0:
            add_segment(kind="prep", duration=prep_sec, part_num=part_no,
                        q_from=q_from, q_to=q_mid, countdown=prep_sec)

        # Now Listen Narrator
        p_listen = seg_dir / f"part_{part_no}_02_narrator_listen.wav"
        if p_listen.exists():
            d = read_segment_duration_bytes(p_listen, sample_rate)
            add_segment(kind="narr_listen", duration=d, part_num=part_no,
                        q_from=q_from, q_to=q_mid,
                        audio_file=p_listen.name)

        add_gap(part_no, q_from, q_mid)

        # Phone ring + pickup cue (only when Stage 2 flagged the part)
        p_sfx = seg_dir / f"part_{part_no}_02b_sfx_phone.wav"
        if p_sfx.exists():
            d = read_segment_duration_bytes(p_sfx, sample_rate)
            add_segment(kind="sfx_phone", duration=d, part_num=part_no,
                        q_from=q_from, q_to=q_mid,
                        audio_file=p_sfx.name)

        # Dialogue 1
        p_dial1 = seg_dir / f"part_{part_no}_03_dialogue_1.wav"
        if p_dial1.exists():
            d = read_segment_duration_bytes(p_dial1, sample_rate)
            add_segment(kind="dialogue_1", duration=d, part_num=part_no,
                        q_from=q_from, q_to=q_mid,
                        audio_file=p_dial1.name)

        add_gap(part_no, q_from, q_mid)

        # Mid-break (Parts 1-3 when present)
        p_mid_narr = seg_dir / f"part_{part_no}_04_narrator_mid.wav"
        p_dial2 = seg_dir / f"part_{part_no}_06_dialogue_2.wav"
        if p_mid_narr.exists() or p_dial2.exists():
            if p_mid_narr.exists():
                d = read_segment_duration_bytes(p_mid_narr, sample_rate)
                add_segment(kind="narr_mid", duration=d, part_num=part_no,
                            q_from=q_mid_next, q_to=q_to,
                            audio_file=p_mid_narr.name)

            mid_break_sec = timing.get("mid_part_break_sec", 30)
            if mid_break_sec > 0:
                add_segment(kind="mid_break", duration=mid_break_sec, part_num=part_no,
                            q_from=q_mid_next, q_to=q_to, countdown=mid_break_sec)

            p_listen2 = seg_dir / f"part_{part_no}_05_narrator_listen2.wav"
            if p_listen2.exists():
                d = read_segment_duration_bytes(p_listen2, sample_rate)
                add_segment(kind="narr_listen2", duration=d, part_num=part_no,
                            q_from=q_mid_next, q_to=q_to,
                            audio_file=p_listen2.name)

            add_gap(part_no, q_mid_next, q_to)

            if p_dial2.exists():
                d = read_segment_duration_bytes(p_dial2, sample_rate)
                add_segment(kind="dialogue_2", duration=d, part_num=part_no,
                            q_from=q_mid_next, q_to=q_to,
                            audio_file=p_dial2.name)

            add_gap(part_no, q_mid_next, q_to)

        # Part End Narrator
        p_end = seg_dir / f"part_{part_no}_07_narrator_end.wav"
        if p_end.exists():
            d = read_segment_duration_bytes(p_end, sample_rate)
            add_segment(kind="narr_end", duration=d, part_num=part_no,
                        q_from=q_from, q_to=q_to,
                        audio_file=p_end.name)

        # Checking Silence
        chk_sec = timing.get("checking_time_sec", 30)
        if chk_sec > 0:
            add_segment(kind="checking", duration=chk_sec, part_num=part_no,
                        q_from=q_from, q_to=q_to, countdown=chk_sec)

        # Between parts transition
        if part_no < 4:
            between_sec = timing.get("between_parts_sec", 3)
            if between_sec > 0:
                add_segment(kind="between_parts", duration=between_sec, part_num=part_no)

            p_turn = seg_dir / f"turn_to_part_{part_no + 1}.wav"
            if p_turn.exists():
                d = read_segment_duration_bytes(p_turn, sample_rate)
                add_segment(kind="turn_to_part", duration=d, part_num=part_no + 1,
                            audio_file=p_turn.name)

    # 3. End Test Narrator
    end_test_file = seg_dir / "end_test.wav"
    if end_test_file.exists():
        d = read_segment_duration_bytes(end_test_file, sample_rate)
        add_segment(kind="end_test", duration=d, part_num=None,
                    audio_file="end_test.wav")

    total_duration = round(current_time, 2)
    timeline = {
        "sample_rate": sample_rate,
        "total_duration": total_duration,
        "segments": segments,
    }

    # Validation against full_test.wav if present
    full_wav = audio_dir / "full_test.wav"
    if full_wav.exists():
        ground_truth = get_ground_truth_duration(full_wav)
        diff = abs(total_duration - ground_truth)
        print(f"Timeline validation: Reconstructed = {total_duration:.2f}s, "
              f"Ground truth (full_test.wav) = {ground_truth:.2f}s, Diff = {diff:.4f}s")
        if diff > 0.05:
            sys.exit(
                f"ERROR: Timeline reconstruction drift exceeds threshold (0.05s)!\n"
                f"Reconstructed: {total_duration:.2f}s, Ground truth: {ground_truth:.2f}s, Diff: {diff:.4f}s"
            )

    # Save timeline.json
    video_dir = test_dir / "video"
    video_dir.mkdir(parents=True, exist_ok=True)
    out_path = video_dir / "timeline.json"
    out_path.write_text(json.dumps(timeline, indent=2), encoding="utf-8")
    print(f"Saved timeline to: {out_path} ({len(segments)} segments, {total_duration:.2f}s)")

    return timeline


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python build_timeline.py <test_directory>")
        sys.exit(1)

    target_dir = sys.argv[1]
    build_timeline(target_dir)
