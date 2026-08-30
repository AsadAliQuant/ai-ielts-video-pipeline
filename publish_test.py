#!/usr/bin/env python3
"""
Publish a finished test directory (post Stage 2) to the SaaS pool: D1 + R2.

Reuses existing pipeline code rather than reimplementing it:
- generate_test.parse_word_limit / LETTER_ANSWER_TYPES / PART_RANGES
- build_timeline.build_timeline (Stage 3's MP4/Playwright/MoviePy path is
  never invoked here)

Usage:
    python publish_test.py tests/test_016
    python publish_test.py tests/test_016 --dry-run
"""

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

try:
    import boto3
    import requests
    from dotenv import load_dotenv
except ImportError:
    sys.exit("Missing dependencies. Run:  pip install -r requirements.txt")

from build_timeline import build_timeline
from generate_test import LETTER_ANSWER_TYPES, parse_word_limit

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")

D1_API_BASE = "https://api.cloudflare.com/client/v4/accounts/{account_id}/d1/database/{database_id}/query"
MP3_DURATION_DRIFT_TOLERANCE_SEC = 0.5


# --------------------------------------------------------------------------
# payload splitting
# --------------------------------------------------------------------------

def normalize_multiple_response(part, slug, warnings):
    """Collapse a multiple_response group's duplicated per-number answers into
    one row spanning the group, fixing the naive-grading overpay bug where a
    group like Q26-30 repeats the same "B,D" answer on every question number.

    Returns the list of answer dicts this part's groups should keep (letter
    and written types untouched; multiple_response groups collapsed to one
    row each, tagged with `letters_required` and `to`).
    """
    groups_by_id = {g.get("id"): g for g in part.get("question_groups", [])}
    answers_by_number = {a.get("number"): a for a in part.get("answers", [])}
    kept = []
    consumed = set()

    for group in part.get("question_groups", []):
        if group.get("type") != "multiple_response":
            continue
        g_from, g_to = group.get("from"), group.get("to")
        span_numbers = [n for n in range(g_from, g_to + 1) if n in answers_by_number]
        if not span_numbers:
            continue
        canonical = answers_by_number[span_numbers[0]]
        letters = [p for p in re.split(r"[,\s/]+", str(canonical.get("answer", ""))) if p]
        letters_required = len(letters)

        if g_to - g_from + 1 != letters_required:
            warnings.append(
                "{}: group {} spans Q{}-{} ({} questions) but answer '{}' has "
                "{} letter(s) - collapsing to one row".format(
                    slug, group.get("id"), g_from, g_to, g_to - g_from + 1,
                    canonical.get("answer"), letters_required))

        alternatives = []
        for n in span_numbers:
            for alt in answers_by_number[n].get("alternatives", []) or []:
                if alt not in alternatives:
                    alternatives.append(alt)

        kept.append({
            "number": g_from,
            "to": g_to,
            "answer": canonical.get("answer"),
            "alternatives": alternatives,
            "type": "multiple_response",
            "group": group.get("id"),
            "max_words": None,
            "number_allowed": None,
            "letters_required": letters_required,
        })
        consumed.update(span_numbers)

    for number, answer in answers_by_number.items():
        if number in consumed:
            continue
        kept.append(answer)

    return sorted(kept, key=lambda a: a["number"])


def build_answers_json(test, slug, warnings):
    rows = []
    for part in test["parts"]:
        groups_by_id = {g.get("id"): g for g in part.get("question_groups", [])}
        questions_by_number = {q.get("number"): q for q in part.get("questions", [])}

        normalized = normalize_multiple_response(part, slug, warnings)
        for answer in normalized:
            if "letters_required" in answer:
                # already fully shaped by normalize_multiple_response
                rows.append(answer)
                continue

            # answers don't carry a group id in test.json; look it up via the
            # question's group instead.
            question = questions_by_number.get(answer.get("number"), {})
            group = groups_by_id.get(question.get("group"))
            gtype = str(group.get("type") if group else answer.get("type", ""))

            max_words, number_allowed = (None, None)
            letters_required = None
            if gtype in LETTER_ANSWER_TYPES:
                letters_required = 1
            else:
                max_words, number_allowed = parse_word_limit(group.get("instruction") if group else None)

            rows.append({
                "number": answer.get("number"),
                "answer": answer.get("answer"),
                "alternatives": answer.get("alternatives", []),
                "type": gtype or answer.get("type"),
                "group": group.get("id") if group else None,
                "max_words": max_words,
                "number_allowed": number_allowed,
                "letters_required": letters_required,
            })

    return sorted(rows, key=lambda r: r["number"])


def build_student_json(test, answers_json):
    letters_required_by_group = {
        a["group"]: a.get("letters_required")
        for a in answers_json if a.get("type") == "multiple_response"
    }

    parts = []
    for part in test["parts"]:
        groups = []
        for g in part.get("question_groups", []):
            g = dict(g)
            if g.get("id") in letters_required_by_group:
                g["letters_required"] = letters_required_by_group[g["id"]]
            groups.append(g)

        visuals = []
        for v in part.get("visuals", []):
            v = {k: val for k, val in v.items() if k != "answer_mapping"}
            visuals.append(v)

        parts.append({
            "part": part.get("part"),
            "situation": part.get("situation"),
            "question_groups": groups,
            "questions": part.get("questions", []),
            "visuals": visuals,
        })

    return {"metadata": test["metadata"], "parts": parts}


def build_transcript_json(test):
    return {
        "parts": [
            {"part": part.get("part"), "transcript": part.get("transcript", [])}
            for part in test["parts"]
        ]
    }


def check_answer_leak(student_json, answers_json):
    """Every non-trivial answer string must be absent from student_json."""
    haystack = json.dumps(student_json, ensure_ascii=False)
    leaks = []
    for row in answers_json:
        candidates = [row.get("answer")] + list(row.get("alternatives") or [])
        for value in candidates:
            value = str(value or "").strip()
            if len(value) < 3:
                continue
            if value in haystack:
                leaks.append((row.get("number"), value))
    return leaks


# --------------------------------------------------------------------------
# audio transcode
# --------------------------------------------------------------------------

def transcode_to_mp3(test_dir, expected_duration):
    wav_path = test_dir / "audio" / "full_test.wav"
    mp3_path = test_dir / "audio" / "full_test.mp3"
    if not wav_path.exists():
        raise FileNotFoundError(f"Missing {wav_path} - run generate_audio.py first")

    subprocess.run(
        ["ffmpeg", "-y", "-i", str(wav_path), "-codec:a", "libmp3lame",
         "-b:a", "128k", "-ar", "44100", "-ac", "1", str(mp3_path)],
        check=True, capture_output=True, text=True,
    )

    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(mp3_path)],
        check=True, capture_output=True, text=True,
    )
    mp3_duration = float(probe.stdout.strip())
    drift = abs(mp3_duration - expected_duration)
    if drift > MP3_DURATION_DRIFT_TOLERANCE_SEC:
        raise RuntimeError(
            f"MP3 duration drift {drift:.3f}s exceeds "
            f"{MP3_DURATION_DRIFT_TOLERANCE_SEC}s tolerance "
            f"(mp3={mp3_duration:.2f}s, timeline={expected_duration:.2f}s)")

    return mp3_path, mp3_duration


# --------------------------------------------------------------------------
# R2 upload
# --------------------------------------------------------------------------

def r2_client():
    account_id = os.environ["CF_ACCOUNT_ID"]
    return boto3.client(
        "s3",
        endpoint_url=f"https://{account_id}.r2.cloudflarestorage.com",
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
        region_name="auto",
    )


def upload_to_r2(test_dir, slug, mp3_path):
    bucket = os.environ["R2_BUCKET_NAME"]
    client = r2_client()

    audio_key = f"tests/{slug}/full_test.mp3"
    client.upload_file(str(mp3_path), bucket, audio_key,
                        ExtraArgs={"ContentType": "audio/mpeg"})

    visual_keys = []
    for png in sorted(test_dir.glob("visual_*.png")):
        vid = png.stem.removeprefix("visual_")
        key = f"tests/{slug}/visuals/{vid}.png"
        client.upload_file(str(png), bucket, key,
                            ExtraArgs={"ContentType": "image/png"})
        visual_keys.append(key)

    return audio_key, visual_keys


# --------------------------------------------------------------------------
# D1 upsert
# --------------------------------------------------------------------------

def d1_query(sql, params=None):
    account_id = os.environ["CF_ACCOUNT_ID"]
    database_id = os.environ["CF_D1_DATABASE_ID"]
    api_token = os.environ["CF_API_TOKEN"]
    url = D1_API_BASE.format(account_id=account_id, database_id=database_id)
    resp = requests.post(
        url,
        headers={"Authorization": f"Bearer {api_token}"},
        json={"sql": sql, "params": params or []},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    if not data.get("success"):
        raise RuntimeError(f"D1 query failed: {data.get('errors')}")
    return data["result"][0]["results"]


def upsert_d1(slug, metadata, duration_sec, audio_key, student_json, answers_json,
              timeline_json, transcript_json):
    rows = d1_query(
        """
        INSERT INTO tests (slug, title, target_band, context, part_topics,
                            duration_sec, audio_key, generated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(slug) DO UPDATE SET
            title = excluded.title,
            target_band = excluded.target_band,
            context = excluded.context,
            part_topics = excluded.part_topics,
            duration_sec = excluded.duration_sec,
            audio_key = excluded.audio_key,
            generated_at = excluded.generated_at
        RETURNING id
        """,
        [
            slug,
            metadata.get("title"),
            metadata.get("target_band"),
            metadata.get("context"),
            json.dumps(metadata.get("part_topics", {}), ensure_ascii=False),
            duration_sec,
            audio_key,
            metadata.get("generated_at"),
        ],
    )
    test_id = rows[0]["id"]

    for table, column, payload in [
        ("test_content", "student_json", student_json),
        ("test_answers", "answers_json", answers_json),
        ("test_timeline", "timeline_json", timeline_json),
        ("test_transcript", "transcript_json", transcript_json),
    ]:
        d1_query(
            f"""
            INSERT INTO {table} (test_id, {column}) VALUES (?, ?)
            ON CONFLICT(test_id) DO UPDATE SET {column} = excluded.{column}
            """,
            [test_id, json.dumps(payload, ensure_ascii=False)],
        )

    return test_id


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------

def publish(test_dir, dry_run=False):
    test_dir = Path(test_dir)
    slug = test_dir.name
    test_json_path = test_dir / "test.json"
    if not test_json_path.exists():
        sys.exit(f"Missing {test_json_path}")
    test = json.loads(test_json_path.read_text(encoding="utf-8"))

    print(f"[{slug}] rebuilding timeline...")
    timeline_json = build_timeline(test_dir)

    warnings = []
    answers_json = build_answers_json(test, slug, warnings)
    student_json = build_student_json(test, answers_json)
    transcript_json = build_transcript_json(test)
    for w in warnings:
        print(f"  ! {w}")

    leaks = check_answer_leak(student_json, answers_json)
    if leaks:
        sys.exit(f"[{slug}] answer leak into student_json: {leaks}")

    print(f"[{slug}] transcoding audio to mp3...")
    mp3_path, mp3_duration = transcode_to_mp3(test_dir, timeline_json["total_duration"])
    print(f"  mp3 duration={mp3_duration:.2f}s (timeline={timeline_json['total_duration']:.2f}s)")

    if dry_run:
        print(f"[{slug}] dry run - skipping R2 upload and D1 upsert")
        return

    print(f"[{slug}] uploading to R2...")
    audio_key, visual_keys = upload_to_r2(test_dir, slug, mp3_path)
    print(f"  audio: {audio_key}")
    for k in visual_keys:
        print(f"  visual: {k}")

    print(f"[{slug}] upserting D1...")
    test_id = upsert_d1(
        slug, test["metadata"], mp3_duration, audio_key,
        student_json, answers_json, timeline_json, transcript_json,
    )
    print(f"[{slug}] published as test_id={test_id}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("test_dir", help="Path to a tests/test_NNN directory")
    parser.add_argument("--dry-run", action="store_true",
                         help="Build and validate payloads, skip R2/D1")
    args = parser.parse_args()
    publish(args.test_dir, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
