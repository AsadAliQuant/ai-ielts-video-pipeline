#!/usr/bin/env python3
"""Resolve where a Listening part's recording splits for the mid-section break.

A real IELTS Listening part is played in two halves. The narrator announces the
first half ("answer questions 1 to 6"), the recording plays, the narrator says
"before you hear the rest of the conversation, you have some time to look at
questions 7 to 10", and the rest plays.

Stage 2 used to pick that boundary by cutting the transcript at the arithmetic
midpoint of its turn count, while the narrator's wording came from
``question_groups[0].to``. The two never agreed: measured across tests 001-018,
17 of 18 Part 1s played the last one or two first-half answers *after* the
break, and three Part 2 monologues got no break at all while the narrator had
already promised one.

This module is the single source of truth for both. It anchors the boundary on
the answer text itself, enforcing:

    no first-half answer is spoken after the break,
    and no second-half answer is spoken before it.

That is enforceable because generate_test.validate_part already guarantees each
non-letter answer appears verbatim, in question order, in the transcript.
``answers[].evidence`` is a secondary anchor only: ~7% of it is paraphrased and
appears nowhere in the transcript.

The split unit is a *sentence*, not a transcript turn, so a Part 2 monologue of
two long turns can still be broken in the middle. Turn boundaries are preferred
whenever one exists inside the valid window.

Run it directly to audit or backfill generated tests:

    python midbreak.py --report tests/
    python midbreak.py --report tests/test_018
    python midbreak.py --write  tests/
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import namedtuple
from pathlib import Path

from text_utils import find_phrase, norm

PART_RANGES = {1: (1, 10), 2: (11, 20), 3: (21, 30), 4: (31, 40)}

# Answer types whose answer field is a bare letter, so it cannot be located in
# the transcript. Imported by generate_test and (via generate_test) publish_test.
LETTER_ANSWER_TYPES = {"multiple_choice", "multiple_response", "matching"}

Unit = namedtuple("Unit", "turn speaker text")

MidBreak = namedtuple(
    "MidBreak",
    "q_from q_mid q_mid_next q_to units split half1 half2 resolved_by cut warnings",
)

# Words that end in a full stop without ending a sentence.
_ABBREV = {
    "mr", "mrs", "ms", "dr", "prof", "st", "rd", "ave", "no", "vs", "etc",
    "eg", "ie", "approx", "dept", "jr", "sr", "co", "inc", "ltd", "min", "max",
}

_SENT_BOUNDARY = re.compile(r"""[.!?]+["')\]]*\s+""")

# A short fragment is not worth synthesising on its own ("Yes." / "Got it.").
_MIN_SENTENCE_WORDS = 4


# ---------------------------------------------------------------------------
# Sentence and unit construction
# ---------------------------------------------------------------------------

def _is_false_stop(text, match):
    """True when the terminator at `match` does not actually end a sentence."""
    head = text[:match.start() + 1]
    word = re.search(r"([A-Za-z0-9.]+)[.!?]+$", head)
    if word:
        token = word.group(1).lower().rstrip(".")
        if token in _ABBREV:
            return True
        if len(token) == 1:          # an initial, "J. Smith"
            return True
        if token.isdigit():          # a decimal or list number
            return True
    nxt = text[match.end():match.end() + 1]
    # A real sentence restarts with a capital, a digit or an opening quote.
    return bool(nxt) and not (nxt.isupper() or nxt.isdigit() or nxt in "\"'")


def split_sentences(text):
    """Split a spoken turn into sentences, tolerating abbreviations."""
    text = str(text or "").strip()
    if not text:
        return []

    pieces, start = [], 0
    for match in _SENT_BOUNDARY.finditer(text):
        if _is_false_stop(text, match):
            continue
        piece = text[start:match.end()].strip()
        if piece:
            pieces.append(piece)
        start = match.end()
    tail = text[start:].strip()
    if tail:
        pieces.append(tail)
    if not pieces:
        return [text]

    # Fold stubs into their neighbour so a break can never land on "Got it."
    merged = []
    for piece in pieces:
        if merged and len(piece.split()) < _MIN_SENTENCE_WORDS:
            merged[-1] = merged[-1] + " " + piece
        else:
            merged.append(piece)
    while len(merged) > 1 and len(merged[0].split()) < _MIN_SENTENCE_WORDS:
        merged[1] = merged[0] + " " + merged[1]
        merged.pop(0)
    return merged


def build_units(part):
    """Flatten a part's spoken content into sentence units.

    `turn` is the index into part["transcript"], so a resolved break can be
    written back into test.json in terms a human can read and hand-edit.
    """
    units = []
    transcript = part.get("transcript") or []
    if isinstance(transcript, dict):
        transcript = [transcript]
    for turn, entry in enumerate(transcript):
        speaker = str(entry.get("speaker", "Speaker")).strip()
        text = str(entry.get("line", "")).strip()
        if not text or speaker.lower() == "narrator":
            continue
        for sentence in split_sentences(text):
            units.append(Unit(turn, speaker, sentence))
    return units


def regroup(units):
    """Merge consecutive units of the same turn back into (speaker, text) pairs."""
    pairs = []
    last_turn = None
    for unit in units:
        if last_turn is not None and unit.turn == last_turn:
            pairs[-1] = (pairs[-1][0], pairs[-1][1] + " " + unit.text)
        else:
            pairs.append((unit.speaker, unit.text))
            last_turn = unit.turn
    return pairs


# ---------------------------------------------------------------------------
# Anchoring answers onto units
# ---------------------------------------------------------------------------

def _is_letter_answer(answer, groups):
    kind = str(answer.get("type", "")).strip().lower()
    if kind in LETTER_ANSWER_TYPES:
        return True
    number = answer.get("number")
    for group in groups:
        lo, hi = group.get("from"), group.get("to")
        if isinstance(lo, int) and isinstance(hi, int) and number is not None \
                and lo <= number <= hi:
            if str(group.get("type", "")).strip().lower() in LETTER_ANSWER_TYPES:
                return True
    # A bare "B" or "A, C" is a letter answer whatever the declared type says.
    return bool(re.fullmatch(r"[A-H](\s*[,/]\s*[A-H])*",
                             str(answer.get("answer", "")).strip()))


def _needles(answer, is_letter):
    """Search phrases for one answer, strongest anchor first."""
    out = []
    if not is_letter:
        text = norm(answer.get("answer", ""))
        if len(text) >= 2:
            out.append(("answer", text))
    evidence = norm(answer.get("evidence", ""))
    if len(evidence) >= 4:
        out.append(("evidence", evidence))
        words = evidence.split()
        if len(words) > 8:
            out.append(("evidence", " ".join(words[:8])))
    return out


def anchor_map(part, units):
    """Map question number -> unit index, scanning strictly forward.

    Forward-only scanning mirrors the ordering guarantee validate_part enforces
    and keeps the map monotonic, so the window below is always well formed.
    """
    normed = [norm(unit.text) for unit in units]
    groups = part.get("question_groups") or []
    positions, how = {}, {}
    cursor = 0
    answers = sorted((a for a in (part.get("answers") or []) if a.get("number")),
                     key=lambda a: a["number"])
    for answer in answers:
        number = answer["number"]
        is_letter = _is_letter_answer(answer, groups)
        for kind, needle in _needles(answer, is_letter):
            hit = next((i for i in range(cursor, len(normed))
                        if find_phrase(normed[i], needle) != -1), None)
            if hit is not None:
                positions[number], how[number] = hit, kind
                cursor = hit
                break
    return positions, how


# ---------------------------------------------------------------------------
# Question ranges and split selection
# ---------------------------------------------------------------------------

def question_ranges(part, part_no):
    """Return (q_from, q_mid, q_to): the part's range and its group boundary."""
    q_from, q_to = PART_RANGES.get(part_no, ((part_no - 1) * 10 + 1, part_no * 10))
    groups = part.get("question_groups") or []
    q_mid = None
    if len(groups) >= 2:
        start = groups[0].get("from")
        if isinstance(start, int) and q_from <= start < q_to:
            q_from = start
        boundary = groups[0].get("to")
        if isinstance(boundary, int) and q_from <= boundary < q_to:
            q_mid = boundary
    if q_mid is None:
        q_mid = min(q_from + 4, q_to - 1)
    return q_from, q_mid, q_to


def _turn_boundaries(units):
    """Unit indices that start a new transcript turn."""
    return {i for i in range(1, len(units)) if units[i].turn != units[i - 1].turn}


def _choose_split(units, positions, how, q_from, q_mid, q_to):
    """Pick a split index, or None when no index can satisfy the invariant.

    Valid indices are the window (lo, hi], where `lo` is the last unit carrying
    a first-half answer and `hi` the first unit carrying a second-half one.
    """
    count = len(units)
    bounds = _turn_boundaries(units)
    lo = max((i for q, i in positions.items() if q <= q_mid), default=None)
    hi = min((i for q, i in positions.items() if q > q_mid), default=None)

    valid = [s for s in range(1, count)
             if (lo is None or s > lo) and (hi is None or s <= hi)]
    if not valid:
        return None, "none", "none"

    share = (q_mid - q_from + 1) / max(1, q_to - q_from + 1)
    target = max(1, round(count * share))

    def by_target(pool):
        cuts = [s for s in pool if s in bounds] or pool
        return min(cuts, key=lambda s: (abs(s - target), s))

    if lo is None and hi is None:
        split, resolved_by = by_target(valid), "proportional"
    else:
        # With no upper bound, stay as close to the last first-half answer as
        # possible; otherwise take the latest boundary the window allows, so
        # the halves stay proportional to the question split.
        pick = min if hi is None else max
        turn_cuts = [s for s in valid if s in bounds]
        split = pick(turn_cuts) if turn_cuts else pick(valid)
        governing = [how.get(q) for q, i in positions.items()
                     if (lo is not None and i == lo) or (hi is not None and i == hi)]
        resolved_by = "evidence" if "evidence" in governing else "answer"

    # A half of one or two sentences is never a real IELTS break - it means the
    # anchors are noise (a stray evidence match near the end of the part). Fall
    # back to the proportional target inside the same window before giving up.
    floor = max(2, int(round(count * 0.12)))
    if min(split, count - split) < floor:
        roomy = [s for s in valid if min(s, count - s) >= floor]
        if not roomy:
            return None, "none", "none"
        split, resolved_by = by_target(roomy), "proportional"

    return split, resolved_by, ("turn" if split in bounds else "sentence")


# ---------------------------------------------------------------------------
# Public resolver
# ---------------------------------------------------------------------------

def _no_break(q_from, q_to, units, warnings):
    return MidBreak(q_from=q_from, q_mid=q_to, q_mid_next=q_to, q_to=q_to,
                    units=units, split=None, half1=regroup(units), half2=[],
                    resolved_by="none", cut="none", warnings=warnings)


def resolve_mid_break(part, part_no):
    """Resolve a part's mid-section break from its answers and transcript.

    `split is None` means this part gets no mid-break, and the question ranges
    collapse to the whole part so the narrator never promises a break that the
    recording does not contain.
    """
    q_from, q_mid, q_to = question_ranges(part, part_no)
    units = build_units(part)

    if part_no == 4:
        return _no_break(q_from, q_to, units, [])
    if len(units) < 2:
        return _no_break(q_from, q_to, units,
                         ["part {} has too little spoken content to split"
                          .format(part_no)])

    positions, how = anchor_map(part, units)
    split, resolved_by, cut = _choose_split(units, positions, how,
                                            q_from, q_mid, q_to)

    warnings = []
    unresolved = [a["number"] for a in (part.get("answers") or [])
                  if a.get("number") and a["number"] not in positions]
    if split is None:
        warnings.append(
            "part {}: no split point separates questions {}-{} from {}-{} "
            "(an answer sits in the final line); the part will play without a "
            "mid-section break".format(part_no, q_from, q_mid, q_mid + 1, q_to))
        return _no_break(q_from, q_to, units, warnings)

    if resolved_by == "proportional":
        warnings.append(
            "part {}: no answer could be located in the transcript, so the "
            "mid-break falls on a proportional estimate (unresolved answers: {})"
            .format(part_no, unresolved or "all"))
    elif unresolved:
        warnings.append(
            "part {}: answers {} could not be located in the transcript; the "
            "mid-break is anchored on the remaining ones"
            .format(part_no, unresolved))

    return MidBreak(q_from=q_from, q_mid=q_mid, q_mid_next=q_mid + 1, q_to=q_to,
                    units=units, split=split,
                    half1=regroup(units[:split]), half2=regroup(units[split:]),
                    resolved_by=resolved_by, cut=cut, warnings=warnings)


# ---------------------------------------------------------------------------
# Persisted form (test.json -> audio_cues.mid_break)
# ---------------------------------------------------------------------------

# Long enough that a real transcript will not repeat it verbatim elsewhere.
_ANCHOR_WORDS = 12


def _anchor_text(unit):
    """Tail of the first half's last unit, as a staleness guard."""
    return " ".join(norm(unit.text).split()[-_ANCHOR_WORDS:])


def annotate_mid_break(part, part_no):
    """Build the audio_cues.mid_break record for a part (None when no break)."""
    resolved = resolve_mid_break(part, part_no)
    if resolved.split is None:
        return None, resolved

    units, split = resolved.units, resolved.split
    turn = units[split - 1].turn
    partial = split < len(units) and units[split].turn == turn
    sentence = sum(1 for u in units[:split] if u.turn == turn) if partial else None

    return {
        "turn": turn,
        "sentence": sentence,
        "q_mid": resolved.q_mid,
        "resolved_by": resolved.resolved_by,
        "cut": resolved.cut,
        "anchor_text": _anchor_text(units[split - 1]),
    }, resolved


def _split_from_stored(units, stored):
    """Recover a split index from a stored record, or None if it no longer fits."""
    if not isinstance(stored, dict):
        return None
    turn, sentence = stored.get("turn"), stored.get("sentence")
    indices = [i for i, u in enumerate(units) if u.turn == turn]
    if not indices:
        return None
    if sentence is None:
        split = indices[-1] + 1
    elif 1 <= sentence <= len(indices):
        split = indices[sentence - 1] + 1
    else:
        return None
    if not 1 <= split <= len(units) - 1:
        return None
    anchor = stored.get("anchor_text")
    if anchor and not norm(units[split - 1].text).endswith(anchor):
        return None
    return split


def mid_break_for(part, part_no):
    """The part's mid-break: the stored record when it still fits, else resolved.

    Stage 2 and Stage 3 both go through here, so the narrator's wording, the
    audio split and the timeline's question labels cannot drift apart.
    """
    stored = (part.get("audio_cues") or {}).get("mid_break")
    if stored is None and "mid_break" in (part.get("audio_cues") or {}):
        # Explicitly recorded as "no break for this part".
        q_from, _, q_to = question_ranges(part, part_no)
        return _no_break(q_from, q_to, build_units(part), [])

    if isinstance(stored, dict):
        units = build_units(part)
        split = _split_from_stored(units, stored)
        if split is not None:
            q_from, q_mid, q_to = question_ranges(part, part_no)
            q_mid = stored.get("q_mid", q_mid)
            return MidBreak(q_from=q_from, q_mid=q_mid, q_mid_next=q_mid + 1,
                            q_to=q_to, units=units, split=split,
                            half1=regroup(units[:split]),
                            half2=regroup(units[split:]),
                            resolved_by=stored.get("resolved_by", "stored"),
                            cut=stored.get("cut", "turn"), warnings=[])
        # The transcript changed under a stored index - recompute rather than
        # cut in the wrong place.
        resolved = resolve_mid_break(part, part_no)
        return resolved._replace(warnings=resolved.warnings + [
            "part {}: stored mid_break no longer matches the transcript; "
            "recomputed".format(part_no)])

    return resolve_mid_break(part, part_no)


def describe_mid_break(resolved, part_no):
    """One-line log summary."""
    if resolved.split is None:
        return ("[mid-break: none - part {} plays straight through, questions "
                "{}-{}]".format(part_no, resolved.q_from, resolved.q_to))
    unit = resolved.units[resolved.split - 1]
    return ("[mid-break: after transcript line {} ({}/{} sentence units), "
            "Q{}-{} | Q{}-{}, {} cut, resolved_by={}]".format(
                unit.turn, resolved.split, len(resolved.units),
                resolved.q_from, resolved.q_mid,
                resolved.q_mid_next, resolved.q_to,
                resolved.cut, resolved.resolved_by))


# ---------------------------------------------------------------------------
# CLI: audit and backfill
# ---------------------------------------------------------------------------

def _legacy_split(units):
    """The old rule, for the report's before/after column."""
    turns = []
    for unit in units:
        if not turns or turns[-1] != unit.turn:
            turns.append(unit.turn)
    return len(turns) // 2, len(turns)


def _invariant_breaches(resolved, positions, q_mid):
    breaches = []
    for number, index in sorted(positions.items()):
        if number <= q_mid and index >= resolved.split:
            breaches.append("Q{} after".format(number))
        elif number > q_mid and index < resolved.split:
            breaches.append("Q{} before".format(number))
    return breaches


def _legacy_breaches(part, units, positions, q_mid):
    """Would the old len//2 turn split have violated the invariant?"""
    legacy_turns, total_turns = _legacy_split(units)
    if total_turns <= 4:
        return None  # the old guard produced no break at all
    turn_ids = []
    for unit in units:
        if not turn_ids or turn_ids[-1] != unit.turn:
            turn_ids.append(unit.turn)
    cut_turn = turn_ids[legacy_turns] if legacy_turns < len(turn_ids) else None
    if cut_turn is None:
        return None
    boundary = next(i for i, u in enumerate(units) if u.turn == cut_turn)
    return [n for n, i in positions.items()
            if (n <= q_mid and i >= boundary) or (n > q_mid and i < boundary)]


def _report(test_dirs):
    totals = {"parts": 0, "ok": 0, "broken": 0, "nobreak": 0,
              "was_broken": 0, "was_nobreak": 0}
    part1 = {"ok": 0, "total": 0, "was_ok": 0}

    for test_dir in test_dirs:
        data = json.loads((test_dir / "test.json").read_text(encoding="utf-8"))
        for part_no, part in enumerate(data.get("parts") or [], start=1):
            if part_no == 4:
                continue
            totals["parts"] += 1
            units = build_units(part)
            positions, _ = anchor_map(part, units)
            resolved = resolve_mid_break(part, part_no)
            old = _legacy_breaches(part, units, positions, resolved.q_mid
                                   if resolved.split else question_ranges(part, part_no)[1])

            if part_no == 1:
                part1["total"] += 1

            if resolved.split is None:
                totals["nobreak"] += 1
                verdict = "NO BREAK"
            else:
                breaches = _invariant_breaches(resolved, positions, resolved.q_mid)
                if breaches:
                    totals["broken"] += 1
                    verdict = "BROKEN: " + ", ".join(breaches)
                else:
                    totals["ok"] += 1
                    if part_no == 1:
                        part1["ok"] += 1
                    verdict = "ok"

            if old is None:
                totals["was_nobreak"] += 1
                before = "no break"
            elif old:
                totals["was_broken"] += 1
                before = "was BROKEN " + ",".join("Q%d" % n for n in sorted(old))
            else:
                before = "was ok"
                if part_no == 1:
                    part1["was_ok"] += 1

            split = "-" if resolved.split is None else "{}/{}".format(
                resolved.split, len(units))
            print("{:10} p{}  {:>8}  {:<12} {:<11} {:<26} {}".format(
                test_dir.name, part_no, split, resolved.resolved_by,
                resolved.cut, verdict, before))
            for warning in resolved.warnings:
                print("{:10}      ! {}".format("", warning))

    print("\nParts 1-3 audited: {}".format(totals["parts"]))
    print("  invariant ok    : {:>3}   (before: {})".format(
        totals["ok"], totals["parts"] - totals["was_broken"] - totals["was_nobreak"]))
    print("  still broken    : {:>3}   (before: {})".format(
        totals["broken"], totals["was_broken"]))
    print("  no break at all : {:>3}   (before: {})".format(
        totals["nobreak"], totals["was_nobreak"]))
    print("  Part 1          : {}/{} ok   (before: {}/{})".format(
        part1["ok"], part1["total"], part1["was_ok"], part1["total"]))
    return totals["broken"]


def _write(test_dirs):
    changed = []
    for test_dir in test_dirs:
        path = test_dir / "test.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        dirty = False
        for part_no, part in enumerate(data.get("parts") or [], start=1):
            record, resolved = annotate_mid_break(part, part_no)
            cues = part.setdefault("audio_cues", {})
            if cues.get("mid_break") != record or "mid_break" not in cues:
                dirty = True
            cues["mid_break"] = record
            print("  {} part {}: {}".format(test_dir.name, part_no,
                                            describe_mid_break(resolved, part_no)))
            for warning in resolved.warnings:
                print("    ! {}".format(warning))
        if dirty:
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                            encoding="utf-8")
            changed.append(test_dir.name)

    print("\nUpdated {} test.json file(s).".format(len(changed)))
    if changed:
        print("These need Stage 2 re-synthesis to hear the corrected split:")
        for name in changed:
            print("  python generate_audio.py tests/{}".format(name))
    return 0


def _collect(target):
    path = Path(target)
    if (path / "test.json").exists():
        return [path]
    dirs = sorted(d for d in path.glob("test_*") if (d / "test.json").exists())
    if not dirs:
        sys.exit("No test.json found under {}".format(path))
    return dirs


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("target", nargs="?", default="tests",
                        help="a tests/ directory or a single tests/test_NNN")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--report", action="store_true",
                       help="audit only, change nothing (default)")
    group.add_argument("--write", action="store_true",
                       help="write audio_cues.mid_break into each test.json")
    args = parser.parse_args()

    dirs = _collect(args.target)
    if args.write:
        return _write(dirs)
    return _report(dirs)


if __name__ == "__main__":
    sys.exit(main())
