#!/usr/bin/env python3
"""Label the mid-section break boundary with an LLM read of the transcript.

midbreak.py's heuristic anchors the split on where *answers* are spoken. That
is wrong whenever the second question group's topic is first *raised* a turn
or two before its answer - which, in ask-then-answer dialogue, is always. See
the plan this implements for the concrete failures (Part 1 in every existing
test plays the opening of Q7's question before the "questions 1-6" pause).

This module asks the model which transcript turn *opens* the second question
group, then checks that answer against the same no-crossing invariant and
minimum-half-size floor midbreak.py already enforces on its own heuristic
(midbreak.split_is_valid) before trusting it. Nothing here invents a new
notion of "valid split" - it only supplies a better candidate.

Imports nothing from generate_test at module load time, so generate_test can
import this module without a cycle; the LLM instance is injected by the
caller.

Run directly for a read-only dry run against an already-generated test:

    python split_labeler.py tests/test_001
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from midbreak import (anchor_map, build_units, question_ranges,
                      split_for_boundary_turn, split_is_valid)

BOUNDARY_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "boundary_turn": {"type": "integer"},
        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
        "reason": {"type": "string"},
        "turn_labels": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "turn": {"type": "integer"},
                    "serves": {"type": "string"},
                },
                "required": ["turn", "serves"],
            },
        },
    },
    "required": ["boundary_turn", "confidence", "reason", "turn_labels"],
}

BOUNDARY_SYSTEM = """You are an IELTS Listening item-writer's assistant.

You are given one part's two question groups and its full transcript. Your
only job is to name the transcript turn that is the first one belonging to
the second question group - the moment the recording's content moves on to
that group's topic, not the moment its answer is spoken. IELTS dialogue asks
before it answers, so the topic almost always starts a turn or two before the
answer does; find that earlier turn, not the answer's turn.

You are being called by an application. Return ONLY valid JSON matching the
schema in the user message: no prose, no commentary, no markdown fences, no
backticks.
"""


def _questions_in_range(part, lo, hi):
    if not isinstance(lo, int) or not isinstance(hi, int):
        return []
    return sorted(
        (q for q in (part.get("questions") or [])
         if isinstance(q.get("number"), int) and lo <= q["number"] <= hi),
        key=lambda q: q["number"])


def _render_options(options):
    """Options are either bare strings or {"letter", "text"} dicts."""
    out = []
    for opt in options or []:
        if isinstance(opt, dict):
            out.append("{}) {}".format(opt.get("letter", "?"), opt.get("text", "")))
        else:
            out.append(str(opt))
    return "; ".join(out)


def _render_group(part, group):
    lo, hi = group.get("from"), group.get("to")
    lines = ["Questions {}-{}: {}".format(lo, hi, group.get("heading", ""))]
    if group.get("instruction"):
        lines.append("Instruction: {}".format(group["instruction"]))
    if group.get("options"):
        lines.append("Options: {}".format(_render_options(group["options"])))
    if group.get("layout"):
        lines.append("Layout:\n{}".format(group["layout"]))
    else:
        for q in _questions_in_range(part, lo, hi):
            line = "Q{}: {}".format(q.get("number"), q.get("text", ""))
            options = q.get("options") or []
            if options:
                line += "  Options: {}".format(_render_options(options))
            lines.append(line)
    return "\n".join(lines)


def _render_groups(part, q_mid, first_half):
    chunks = []
    for group in part.get("question_groups") or []:
        lo, hi = group.get("from"), group.get("to")
        if not isinstance(lo, int) or not isinstance(hi, int):
            continue
        if (hi <= q_mid) != first_half:
            continue
        chunks.append(_render_group(part, group))
    return "\n\n".join(chunks) if chunks else "(no question group data)"


def _render_transcript(part):
    lines = []
    for i, entry in enumerate(part.get("transcript") or []):
        speaker = entry.get("speaker", "Speaker")
        text = entry.get("line", "")
        lines.append("[{}] {}: {}".format(i, speaker, text))
    return "\n".join(lines)


def _build_user_prompt(part, part_no, q_mid):
    q_from, _, q_to = question_ranges(part, part_no)
    return (
        "IELTS Listening Part {part} (questions {qfrom}-{qto}) has two question "
        "groups: group 1 covers questions {qfrom}-{qmid}, group 2 covers "
        "questions {qmid1}-{qto}. A pause is inserted between the two groups' "
        "recordings.\n\n"
        "GROUP 1 (questions {qfrom}-{qmid}):\n{group1}\n\n"
        "GROUP 2 (questions {qmid1}-{qto}):\n{group2}\n\n"
        "TRANSCRIPT - each line is [turn index] Speaker: text; Narrator turns "
        "are included so you can see the full flow:\n{transcript}\n\n"
        "Name boundary_turn: the transcript turn index that FIRST belongs to "
        "group 2. Everything from that turn onward, including it, plays after "
        "the pause.\n\n"
        "Rules:\n"
        "- A turn in which a speaker asks about or introduces the topic of a "
        "group 2 question belongs to group 2, even though its answer is "
        "spoken in a later turn.\n"
        "- A transition or wrap-up line that sets up group 2 (e.g. \"before we "
        "finish, I just need a few more details\") belongs to group 2, not "
        "group 1.\n"
        "- Never choose a turn inside a group 1 exchange, and never choose a "
        "turn at or after the point where the first group 2 answer is spoken.\n"
        "- In turn_labels, classify every turn's \"serves\" as \"intro\" (scene-"
        "setting before either group starts), \"group1\", or \"group2\" - "
        "boundary_turn must be the first turn labelled \"group2\"."
    ).format(part=part_no, qfrom=q_from, qto=q_to, qmid=q_mid, qmid1=q_mid + 1,
             group1=_render_groups(part, q_mid, True),
             group2=_render_groups(part, q_mid, False),
             transcript=_render_transcript(part))


def label_boundary(llm, part, part_no, q_mid):
    """Ask the LLM which transcript turn opens the second question group.

    Returns the boundary turn once it survives the same checks midbreak.py
    applies to its own heuristic, or None if the call, its answer, or that
    check fails - callers should fall back to the heuristic in that case.
    """
    user = _build_user_prompt(part, part_no, q_mid)
    result = llm.json_call(
        BOUNDARY_SYSTEM, user, max_tokens=3000, temperature=0.0,
        label="split:p{}".format(part_no),
        schema=BOUNDARY_JSON_SCHEMA, schema_name="mid_break_boundary")

    boundary_turn = result.get("boundary_turn")
    if not isinstance(boundary_turn, int):
        print("  ! part {}: labeler boundary rejected (boundary_turn is {!r}, "
              "not an integer)".format(part_no, boundary_turn))
        return None

    units = build_units(part)
    split = split_for_boundary_turn(units, boundary_turn)
    positions, _ = anchor_map(part, units)
    if not split_is_valid(units, positions, q_mid, split):
        print("  ! part {}: labeler boundary rejected (turn {} fails the "
              "no-crossing invariant or minimum half size)"
              .format(part_no, boundary_turn))
        return None

    return boundary_turn


# ---------------------------------------------------------------------------
# CLI: read-only dry run against an already-generated test
# ---------------------------------------------------------------------------

def _dry_run(test_dir):
    import generate_test  # local import: avoids a cycle at module load time

    path = Path(test_dir) / "test.json"
    if not path.exists():
        sys.exit("No test.json found at {}".format(path))
    data = json.loads(path.read_text(encoding="utf-8"))

    llm = generate_test.LLM("gemini", generate_test.DEFAULT_MODEL,
                            gemini_model=generate_test.DEFAULT_GEMINI_MODEL,
                            temperature=0.0, verbose=False)

    for part_no, part in enumerate(data.get("parts") or [], start=1):
        if part_no not in (1, 2, 3):
            continue
        _, q_mid, _ = question_ranges(part, part_no)
        stored = (part.get("audio_cues") or {}).get("mid_break") or {}
        print("\n=== part {} (q_mid={}) ===".format(part_no, q_mid))
        print("stored turn      : {}".format(stored.get("turn")))
        try:
            boundary_turn = label_boundary(llm, part, part_no, q_mid)
        except Exception as exc:                            # noqa: BLE001
            print("labeler call failed: {}".format(exc))
            continue
        print("proposed boundary: {}".format(boundary_turn))

        transcript = part.get("transcript") or []
        around = boundary_turn if boundary_turn is not None else stored.get("turn")
        if around is None:
            continue
        lo, hi = max(0, around - 2), min(len(transcript), around + 3)
        for i in range(lo, hi):
            entry = transcript[i]
            marker = ">>" if i == boundary_turn else "  "
            print("{} [{}] {}: {}".format(marker, i, entry.get("speaker", ""),
                                          str(entry.get("line", ""))[:100]))


def main():
    parser = argparse.ArgumentParser(
        description="Dry-run the mid-break boundary labeler against an "
                    "existing test. Writes nothing.")
    parser.add_argument("target", help="a tests/test_NNN directory")
    args = parser.parse_args()
    _dry_run(args.target)
    return 0


if __name__ == "__main__":
    sys.exit(main())
