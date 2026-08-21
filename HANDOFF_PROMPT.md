# Handoff prompt — IELTS Listening Test Generator

Copy everything below the line into a fresh Claude Code session opened in
`d:\Asad\Projects\AI IELTS`.

---

## Context

You are taking over a working Python project at `d:\Asad\Projects\AI IELTS`.
It generates complete, original IELTS Listening practice tests by calling
NVIDIA NIM (model `meta/muse-glimmer-30b`) through the OpenAI-compatible SDK.
**The code works and produces usable output. Do not rewrite it.** Your job is
twofold: make the pipeline survive a full run reliably (see "Known operational
issues" — two of the last three live runs died before producing a test), and
then raise the quality of the generated tests, which are currently good but not
exam-grade.

### Files

| File | What it is |
|---|---|
| `generate_test.py` | ~1,300 lines. The entire implementation. Single script, no package. |
| `system_prompt.txt` | 905 lines. The user's own 24-section "IELTS Listening Test Designer" prompt, verbatim. **Treat this as the spec.** It is loaded at runtime and a JSON output contract is appended to it. Do not edit it unless the user asks — the user maintains it. |
| `requirements.txt` | `openai>=1.40.0`, `python-dotenv>=1.0.1` |
| `.env` | Holds `NVIDIA_API_KEY`. Gitignored. Never print it, never send it anywhere. |
| `tests/test_00N/` | Generated output folders (gitignored). |
| `run*.log` | Logs from previous live runs. Read these — they are your evidence. |

### How to run it

```bash
python -u generate_test.py --band 7.0                  # full run, ~40-60 min, ~24 API calls
python -u generate_test.py --band 7.0 --skip-verify    # generation only, ~15 min, 5 API calls
```

Always use `python -u` — output is buffered otherwise and the log stays empty.
Run it in the background and poll the log; a single API call can take 15 minutes.
The model is genuinely slow, so budget real time before concluding it hung.
(A previous run sat silent for 65 minutes and had to be killed — see
"Known operational issue" below.)

### Architecture (read `generate_test.py` before changing anything)

```
main()
 └─ build_test()
     ├─ generate_blueprint()          1 call  — plans the 4 parts and question types
     ├─ generate_part() x4            4 calls — each part generated independently
     │   └─ validate_part()                   — pure Python, no LLM
     │       └─ repair_part()         0-4 calls — one repair round per failing part
     └─ run_verification()
         └─ per part: verify_part()
             ├─ blind_solve()         — LLM solves the part WITHOUT ever seeing the answer key
             ├─ audit_part()          — LLM audits each question against 7 criteria
             └─ repair + re-verify    — repaired part is re-verified before being accepted
```

Key design decisions, all deliberate — **do not undo them**:

- **Per-part generation.** One giant JSON completion for a whole test was
  unreliable. Four smaller calls are not an accident.
- **The verifier has its own system prompt** (`VERIFIER_SYSTEM`), not the
  generator's. It must stay independent and sceptical.
- **The blind solve never receives the answer key.** There is a test that
  asserts this. If you touch `blind_solve()`, keep that property.
- **Local validation is pure Python** (`validate_part()`, ~200 lines) and does
  not trust the model. Roughly 25 distinct checks: numbering, answers present
  in transcript, answers in spoken order, word limits, answer leakage into
  student-facing text and into Mermaid, option-letter validity, transcript
  length and words-per-turn, visual/Mermaid consistency, map landmark quality.
- **Repairs must strictly improve.** `build_test()` keeps a repair only if it
  reduces the error count; `run_verification()` re-verifies before accepting.
  Both guards exist because repairs were observed making tests *worse*.
- **Outputs are separated** per section 22 of the system prompt: `test.json`
  (source of truth), `student_paper.md` (no answers), `transcript.txt`
  (TTS-ready, no question numbers), `answer_key.md`, `visuals.md`.

---

## What is actually wrong — fix these

These are confirmed defects observed in live runs, not speculation. Evidence is
in `run_full.log` and `run_final_hung.log`. Work through them in order; each is
independently shippable.

### 1. Answer form mismatch between transcript and key (highest value)

The verifier repeatedly blind-solves a question correctly in substance but the
string does not match the key, so it is scored wrong:

- `Q34`: blind solve produced `heat trapped`, key says `anthropogenic heat`
- `Q37`: blind solve produced `15 degrees Celsius`, key says `15 degrees`

`matches_answer()` (line ~119) already honours an `alternatives` list on each
answer, and the schema has an `alternatives: []` field — **the model just
leaves it empty**. Two things to do:

- Push much harder in `PART_SCHEMA` and `generate_part()` for the model to
  populate `alternatives` with every defensible surface form (with/without
  units, singular/plural, contracted forms, `Celsius`/`C`).
- Consider a local check: if the exact keyed string appears in the transcript
  surrounded by words that a candidate would plausibly include (a unit, a
  noun), flag it and ask for alternatives.

Be careful: this must not become a loophole that accepts genuinely wrong
answers. IELTS answer keys are strict; alternatives should be *orthographic
variants of the same answer*, not different answers.

### 2. The question and the transcript disagree

`Q7`: the question asked for a *number of books*, the transcript stated a
*number of items*. This is a semantic mismatch no string check catches — the
answer is technically present, so `validate_part()` passes it, and only the
LLM auditor caught it. Consider strengthening the audit criteria or adding a
generation-time instruction that every completion question must name the exact
same noun the speaker uses.

### 3. Answers spoken out of order

`Q15` and `Q30` in separate runs: the keyed answer appears in the transcript
*before* an earlier question's answer. Real IELTS Listening answers always
occur in order. The local check catches this correctly — the problem is the
model keeps producing it, and the repair sometimes fixes the ordering while
breaking something else (see #5). Fix at generation time: make the ordering
constraint far more prominent in `generate_part()`, ideally by asking the model
to lay out the transcript beat-by-beat against the question sequence.

### 4. Answers absent from the transcript entirely

`Q6`: keyed answer `4 pm` never appears in the part 1 transcript. Caught
locally, but the repair then made things worse (1 error → 3). The generation
prompt needs to make "every keyed answer must be spoken verbatim" a
non-negotiable, and the repair prompt needs to fix *only* the named defect.

### 5. Repairs are unreliable

Observed: a repair fixed an ordering error but silently cut the transcript from
~800 to 373 words; another took a part from 1 flagged question to 5. The
strict-improvement guards now catch this and keep the original — **so the
system is safe, but the repair itself is still low quality and often wasted.**
Improving `repair_part()` so repairs usually succeed would cut both runtime and
failure rate. Give it the full failing part, the exact error list, and an
explicit "change nothing else" constraint with the current word count as a
floor (some of this exists; it is not strong enough).

### 6. Map and plan labelling questions are weak

Q16–20 in one run were a map-labelling group whose visual labels were literally
`["16","17","18","19","20"]` — no entrance, no landmarks, nothing to orient by.
The task collapsed into "write five place names in order" and the verifier
correctly flagged all five as not determinable. A local check now requires ≥2
non-numeric landmark labels and ≥15 words of layout description, which forces a
repair — but the *generated* maps are still thin. Improve the prompt so map
visuals are designed around fixed reference points first, blanks second.

### 7. Mermaid theming (cosmetic, low priority)

Mermaid diagrams render correctly and leak no answers — this is verified, both
generated diagrams compiled with `mmdc` and produced clean PNGs. But Mermaid's
default lilac theme conflicts with section 16 of the system prompt, which
requires print-friendly black-and-white output. This is a render-time flag
(`mmdc -t neutral -b white`), not a generator concern. Decide whether the
script should emit a recommended render command or a theme directive in the
Mermaid source.

---

## Known operational issues — fix these first, they cost real time

These are reliability bugs, not quality bugs. Two of the last three live runs
failed to produce a test at all because of them. Fix these before touching
anything above.

### O1. No request timeout — runs hang forever

A run was observed hanging: the process stayed alive but produced no output for
65 minutes mid-verification and had to be killed with `taskkill`. The OpenAI
client in the `LLM` class (line ~136) is constructed without an explicit
timeout, so a stalled call blocks the entire run indefinitely with no error.
Partial log preserved as `run_final_hung.log`. **Add a request timeout and a
bounded retry.**

### O2. `json_call`'s repair path is unguarded and kills the whole run

**This is currently blocking. Two consecutive full runs died here and produced
no test at all** (`run3_crash.log`, `run4.log`). Identical signature both times:

1. The blueprint call returned malformed JSON — `Expecting ',' delimiter`
   (2,847 chars in run 3; 2,298 chars in run 4).
2. `json_call()` (line ~188) caught that and fired its one repair round-trip.
3. The repair call returned **0 chars** — an empty completion (after 183.1s in
   run 3, 47.7s in run 4).
4. `extract_json("")` raised `JSONDecodeError: no JSON object found`. Because
   the repair call sits **outside** the `try` block, that exception propagated
   straight out through `build_test()` → `main()` and killed the process with a
   raw traceback.

**Step 4 is the definite, reproducible-by-inspection bug and the thing to fix.**
Steps 1 and 3 are intermittent — the same blueprint prompt succeeds perhaps half
the time. Fix the guard first; that alone converts a fatal crash into a retry.

- **Guard the repair path.** An empty or still-invalid repair response must
  retry or fail with a clear message naming the label (`blueprint`, `part3`, …),
  not raise a raw `JSONDecodeError` traceback at the user. One repair attempt is
  also too few for a call this failure-prone.
- **Treat an empty completion as an API failure**, not a parse failure. A 0-char
  response means the call went wrong; it belongs in `chat()`'s existing retry
  loop, not handed to the JSON parser.

**Do not assume this is a `max_tokens` truncation — I checked, and it is not.**
I probed the exact blueprint prompt at both `max_tokens=2500` (the current
value) and `8000`. Both returned `finish_reason='stop'` at ~1,900 completion
tokens, well under the cap, and both parsed cleanly. I also probed the json-fix
prompt with deliberately malformed input at both caps; both returned valid JSON.
So the initial call is not being cut off, and raising the blueprint's
`max_tokens` is *not* the fix. The 183-second empty response in run 3 hints the
model sometimes reasons at length and emits nothing, but I could not reproduce
that in isolation — treat the empty response as a fact to defend against, not a
cause you understand yet. Probe scripts are in the scratchpad
(`probe_blueprint.py`, `probe_repair.py`) if you want to dig further.

Once O2 is fixed, **your first job is to get one full run to complete.** Nobody
has seen a clean end-to-end run since the transcript-length and map-landmark
validation was added, so the content fixes below are unverified against live
output.

### O3. No checkpointing — a late crash loses the entire run

A full run is ~24 API calls and 40–60 minutes. A crash in part 4 or during
verification throws away everything generated so far. Consider writing
`test.json` incrementally after each part completes, and/or a `--resume` flag.
Given O1 and O2 have both already destroyed runs, this is worth doing.

---

## How to verify your changes without burning 45 minutes

There are two throwaway harnesses in the scratchpad directory
(`C:\Users\Asad\AppData\Local\Temp\claude\d--Asad-Projects-AI-IELTS\86951c92-abd3-4b05-a2cc-e1d014bd0379\scratchpad\`).
If they are gone, rebuild equivalents — they are worth the 20 minutes:

- **`offline_check.py`** — 45 assertions against hand-built fixtures. Proves a
  clean part validates, and that each individual detector fires (missing
  answer, word-limit breach, out-of-order answers, leaked answer, invalid
  option letter, wrong numbering, transcript annotations, short transcript,
  clipped turns, Mermaid/custom-note conflict, Mermaid without a diagram type,
  unlabellable map). Also covers rendering and CLI parsing. **Run this after
  every change to `validate_part()`.**
- **`mock_run.py`** — end-to-end `main()` with `generate_test.LLM`
  monkeypatched, so the whole pipeline runs in seconds with zero API cost.
  Asserts the blind solve never receives the answer key, that verifier calls
  use `VERIFIER_SYSTEM`, and that generator calls carry the output contract.
  It deliberately injects a wrong answer and a low-confidence answer to prove
  both are caught.
- **`check_mermaid.py <test_dir>`** — extracts every visual from `test.json`,
  renders each with `npx mmdc`, and asserts no answer text leaks into the
  student-facing diagram.

Only after those pass should you spend a live run.

---

## Working style the user expects

- Quick concrete implementations over long explanations. The user is impatient
  and will interrupt if you overcomplicate.
- Incremental changes, tested as you go — not one giant rewrite.
- Do not add `Co-Authored-By: Claude` or any Claude attribution to commits.
- Report honestly. If a run fails or you skipped something, say so plainly with
  the output. Do not claim a fix works until you have seen it work.
- Note that the console mangles non-ASCII (`Café` displays as `Caf?`). This is
  a display limitation, not file corruption — verify at byte level before
  "fixing" an encoding bug that does not exist.
