#!/usr/bin/env python3
"""
IELTS Listening Test Generator.

Calls an NVIDIA NIM cloud model to produce an original IELTS Listening practice
test, validates it locally, has a separate LLM verifier agent blind-solve and
audit it, then renders student paper / transcript / answer key / visuals.

Usage:
    python generate_test.py
    python generate_test.py --band 7 --difficulty "IELTS 7.0"
    python generate_test.py --model <other-model> --out tests/
    python generate_test.py --skip-verify
"""

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

try:
    from dotenv import load_dotenv
    from openai import OpenAI
except ImportError:
    sys.exit("Missing dependencies. Run:  pip install -r requirements.txt")

from generate_visual import process_test_visuals
from midbreak import (LETTER_ANSWER_TYPES, annotate_mid_break,
                      describe_mid_break, question_ranges, resolve_mid_break)
from text_utils import find_phrase, norm
import split_labeler

NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"
GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
DEFAULT_MODEL = "deepseek-ai/deepseek-v4-flash-0731"
DEFAULT_GEMINI_MODEL = "gemini-3.5-flash-lite"
ROOT = Path(__file__).resolve().parent

PART_RANGES = {1: (1, 10), 2: (11, 20), 3: (21, 30), 4: (31, 40)}

PART_BRIEF = {
    1: "Everyday/social conversation, normally 2 speakers (transactional: booking, "
       "enquiry, registration, membership). Easiest part.",
    2: "Everyday/social monologue by one main speaker (tour, facility information, "
       "community event, orientation). Often suits a map/plan labelling group.",
    3: "Educational or training conversation, 2-4 speakers (students and tutor "
       "discussing an assignment, project or research). Opinions and disagreement.",
    4: "Academic lecture or presentation, single speaker. Dense information, "
       "academic vocabulary, heavy paraphrasing. Hardest part.",
}

# section 11 of the system prompt: spoken words per part
TRANSCRIPT_TARGET = {1: (600, 900), 2: (700, 1000), 3: (800, 1100), 4: (900, 1200)}
# below this a part is rejected and repaired; above it but under target only warns
TRANSCRIPT_FLOOR = {1: 450, 2: 520, 3: 600, 4: 680}

WORD_NUM = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5}


STUDENT_INSTRUCTIONS = (
    "You will hear four recordings.\n\n"
    "You will have time to read the questions before each recording.\n\n"
    "You will hear each recording only once.\n\n"
    "Write your answers as you listen.\n\n"
    "At the end of the test, check your answers."
)


# --------------------------------------------------------------------------
# text utilities
# --------------------------------------------------------------------------

def answer_shape(answer):
    """Return (word_count, number_count) for an answer string."""
    toks = norm(answer).split()
    nums = [t for t in toks if re.fullmatch(r"[0-9][0-9.,:/']*", t)]
    return len(toks) - len(nums), len(nums)


def parse_word_limit(instruction):
    """Return (max_words, number_allowed) parsed from an IELTS instruction."""
    text = (instruction or "").upper()
    m = re.search(r"NO MORE THAN (ONE|TWO|THREE|FOUR|FIVE) WORD", text)
    if not m:
        return None, True
    return WORD_NUM[m.group(1).lower()], "NUMBER" in text


def strip_reasoning(text):
    """Remove <think>...</think> blocks that some reasoning models emit."""
    return re.sub(r"<think>.*?</think>", "", text or "", flags=re.S | re.I).strip()


def extract_json(raw):
    """Pull a JSON object out of a completion, tolerating fences and prose."""
    text = strip_reasoning(raw)
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, flags=re.S)
    if fenced:
        text = fenced.group(1)
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        return json.loads(text[start:end + 1])
    raise json.JSONDecodeError("no JSON object found", text[:200] or " ", 0)


def matches_answer(given, expected, alternatives=None):
    """Case/punctuation-insensitive comparison honouring accepted alternatives."""
    candidates = [expected] + list(alternatives or [])
    g = norm(given)
    if not g:
        return False
    return any(g == norm(c) for c in candidates if str(c).strip())


def as_list(value):
    return value if isinstance(value, list) else []


# --------------------------------------------------------------------------
# LLM client
# --------------------------------------------------------------------------

class _Backend:
    """One usable (client, model) pair the LLM class can fall back across."""

    def __init__(self, name, client, model, schema_styles=None):
        self.name = name
        self.client = client
        self.model = model
        self.json_mode = True          # switched off automatically if unsupported
        self._schema_styles = list(schema_styles or [])   # remaining styles to try, in order
        self.schema_style = self._schema_styles.pop(0) if self._schema_styles else None

    def demote_schema(self):
        """Give up on the current structured-output style and move to the next one."""
        old = self.schema_style
        self.schema_style = self._schema_styles.pop(0) if self._schema_styles else None
        if self.schema_style:
            print("    ! {} rejects '{}' schema mode - trying '{}'".format(
                self.name, old, self.schema_style))
        else:
            print("    ! {} rejects '{}' schema mode - falling back to "
                  "json_object mode".format(self.name, old))


def _nvidia_schema_styles(mode):
    """Ordered structured-output styles to probe for an NVIDIA NIM backend."""
    return {
        "auto": ["json_schema", "guided_json"],
        "json_schema": ["json_schema"],
        "guided_json": ["guided_json"],
        "off": [],
    }[mode]


def _is_schema_rejection(text):
    """True if an API error looks like it's complaining about structured-output kwargs."""
    t = text.lower()
    return any(s in t for s in (
        "json_schema", "response_format", "schema", "nvext", "guided_json",
        "extra_body", "extra inputs are not permitted", "unknown field",
    ))


def _load_gemini_keys():
    raw = os.getenv("GEMINI_API_KEYS", "") or os.getenv("GEMINI_API_KEY", "")
    return [k.strip() for k in raw.split(",") if k.strip()]


class LLM:
    """Wrapper around an OpenAI-compatible endpoint with provider fallback.

    provider="nvidia": NVIDIA NIM first, falling back to each GEMINI_API_KEYS
    entry in turn if NVIDIA errors out or every retry on it is exhausted.
    provider="gemini": GEMINI_API_KEYS only, rotating to the next key on
    failure (e.g. one account gets rate-limited).
    """

    def __init__(self, provider, model, gemini_model=DEFAULT_GEMINI_MODEL,
                 temperature=0.7, verbose=True, nvidia_schema="auto"):
        load_dotenv(ROOT / ".env")
        nvidia_key = os.getenv("NVIDIA_API_KEY", "").strip()
        gemini_keys = _load_gemini_keys()

        self.backends = []
        if provider == "nvidia":
            if not nvidia_key or nvidia_key.startswith("nvapi-xxxx"):
                sys.exit("NVIDIA_API_KEY missing. Copy .env.example to .env and add your key.")
            self.backends.append(_Backend(
                "nvidia", OpenAI(base_url=NVIDIA_BASE_URL, api_key=nvidia_key,
                                  timeout=900.0, max_retries=0), model,
                schema_styles=_nvidia_schema_styles(nvidia_schema)))
            for i, gkey in enumerate(gemini_keys, 1):
                self.backends.append(_Backend(
                    "gemini#{}".format(i), OpenAI(base_url=GEMINI_BASE_URL, api_key=gkey,
                                                   timeout=900.0, max_retries=0), gemini_model,
                    schema_styles=["json_schema"]))
        elif provider == "gemini":
            if not gemini_keys:
                sys.exit("No GEMINI_API_KEYS found in .env (comma-separated list of keys).")
            for i, gkey in enumerate(gemini_keys, 1):
                self.backends.append(_Backend(
                    "gemini#{}".format(i), OpenAI(base_url=GEMINI_BASE_URL, api_key=gkey,
                                                   timeout=900.0, max_retries=0), gemini_model,
                    schema_styles=["json_schema"]))
        else:
            sys.exit("Unknown --provider '{}' (expected nvidia or gemini)".format(provider))

        self.temperature = temperature
        self.verbose = verbose
        self.calls = 0
        self.backend_index = 0         # sticks on whichever backend last worked

    @property
    def model(self):
        return self.backends[self.backend_index].model

    def chat(self, system, user, max_tokens=8000, temperature=None, label="",
             schema=None, schema_name=""):
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        last_error = None
        n = len(self.backends)
        order = [(self.backend_index + i) % n for i in range(n)]
        for pos, bi in enumerate(order):
            backend = self.backends[bi]
            attempt = 0
            while attempt < 3:
                kwargs = dict(
                    model=backend.model,
                    messages=messages,
                    temperature=self.temperature if temperature is None else temperature,
                    max_tokens=max_tokens,
                )
                if schema is not None and backend.schema_style == "json_schema":
                    kwargs["response_format"] = {
                        "type": "json_schema",
                        "json_schema": {"name": schema_name or "response", "schema": schema},
                    }
                elif schema is not None and backend.schema_style == "guided_json":
                    kwargs["extra_body"] = {"nvext": {"guided_json": schema}}
                elif backend.json_mode:
                    kwargs["response_format"] = {"type": "json_object"}
                try:
                    self.calls += 1
                    started = time.time()
                    resp = backend.client.chat.completions.create(**kwargs)
                    content = resp.choices[0].message.content or ""
                    elapsed = time.time() - started
                    if not content.strip():
                        last_error = RuntimeError("empty completion")
                        print("    ! [{}/{}] {:.1f}s, empty completion".format(
                            backend.name, label or "call", elapsed))
                        attempt += 1
                        if attempt < 3:
                            wait = 3 * attempt
                            print("    ! retrying in {}s".format(wait))
                            time.sleep(wait)
                        continue
                    if self.verbose:
                        print("    [{}/{}] {:.1f}s, {} chars".format(
                            backend.name, label or "call", elapsed, len(content)))
                    self.backend_index = bi
                    return content
                except Exception as exc:                        # noqa: BLE001
                    last_error = exc
                    text = str(exc)
                    if backend.schema_style and schema is not None and _is_schema_rejection(text):
                        backend.demote_schema()
                        continue  # free retry - probing a style costs no attempt budget
                    if backend.json_mode and ("response_format" in text or "json_object" in text):
                        backend.json_mode = False
                        print("    ! {} rejects JSON mode - falling back to plain text".format(
                            backend.name))
                        attempt += 1
                        continue
                    is_rate_limit = "429" in text or "rate" in text.lower() or "quota" in text.lower()
                    if is_rate_limit:
                        print("    ! {} rate-limited ({}) - switching backend".format(
                            backend.name, text[:120]))
                        break
                    attempt += 1
                    if attempt < 3:
                        wait = 3 * attempt
                        print("    ! {} API error ({}) - retrying in {}s".format(
                            backend.name, text[:120], wait))
                        time.sleep(wait)
            if pos < len(order) - 1:
                print("    ! {} unavailable - falling back to {}".format(
                    backend.name, self.backends[order[pos + 1]].name))
        raise RuntimeError("API call failed on every backend ({}): {}".format(
            label or "call", last_error))

    def json_call(self, system, user, max_tokens=8000, temperature=None, label="",
                  schema=None, schema_name=""):
        """Call the model and parse JSON, with bounded repair round-trips on failure."""
        raw = self.chat(system, user, max_tokens, temperature, label,
                        schema=schema, schema_name=schema_name)
        try:
            return extract_json(raw)
        except (json.JSONDecodeError, ValueError) as exc:
            last_error = exc
            for repair_attempt in range(2):
                print("    ! invalid JSON ({}) - asking the model to repair it".format(last_error))
                try:
                    fixed = self.chat(
                        "You repair malformed JSON. Return ONLY the corrected JSON object: "
                        "no prose, no markdown fences, no explanation.",
                        "This text should have been one valid JSON object but failed to parse "
                        "({}). Return the corrected JSON with the same content:\n\n{}".format(
                            last_error, strip_reasoning(raw)),
                        max_tokens=max_tokens,
                        temperature=0.0,
                        label="{}:json-fix".format(label),
                        schema=schema,
                        schema_name=schema_name,
                    )
                    return extract_json(fixed)
                except (json.JSONDecodeError, ValueError, RuntimeError) as fix_exc:
                    last_error = fix_exc
            raise RuntimeError(
                "json_call '{}' failed: could not obtain valid JSON after repair attempts "
                "(last error: {})".format(label or "call", last_error))


# --------------------------------------------------------------------------
# prompt fragments
# --------------------------------------------------------------------------

JSON_ADDENDUM = """

==================================================
OUTPUT CONTRACT (replaces section 20 output modes)
==================================================

You are being called by an application, not by a human reader.

Return ONLY valid JSON matching the schema given in the user message.
No prose, no commentary, no markdown fences, no backticks, no trailing text.
Use straight quotes. Escape newlines inside strings as \\n.
Every field in the schema must be present; use "" or [] where not applicable.
Do not invent fields that are not in the schema.
"""

BLUEPRINT_SCHEMA = """Return JSON in exactly this shape:

{
  "title": "string - title of the whole test",
  "difficulty": "string",
  "target_band": "string",
  "parts": [
    {
      "part": 1,
      "topic": "string - short topic name",
      "setting": "string - one sentence describing the situation",
      "format": "conversation or monologue",
      "speakers": [{"name": "<SPEAKER ROLE>", "role": "<who they are>"}],
      "question_groups": [
        {
          "type": "one of: form_completion, note_completion, table_completion, flow_chart_completion, sentence_completion, summary_completion, short_answer, multiple_choice, multiple_response, matching, plan_map_labelling, diagram_labelling",
          "from": 1,
          "to": 5,
          "needs_visual": false,
          "visual_type": ""
        }
      ]
    }
  ]
}

Blueprint rules:
- Exactly 4 parts. Part 1 covers questions 1-10, part 2 covers 11-20, part 3 covers 21-30, part 4 covers 31-40.
- Question groups within a part must be contiguous and together cover that part's whole range.
- Each group covers 2 to 6 questions.
- Use a realistic mixture of types across the test (section 4 of your instructions). Do not use the same type in every part.
- At most two groups in the entire test may set needs_visual to true, and only where a visual genuinely helps (map/plan labelling, diagram labelling, flow-chart completion).
- The four topics must be original and unrelated to each other.
"""

PART_SCHEMA = """Return JSON in exactly this shape:

{
  "part": 1,
  "situation": "string - the 'You will hear ...' line shown to the student",
  "speakers": [{"name": "<SPEAKER ROLE>", "role": "string"}],
  "question_groups": [
    {
      "id": "g1",
      "type": "form_completion",
      "from": 1,
      "to": 5,
      "instruction": "Complete the form below.\\n\\nWrite NO MORE THAN TWO WORDS AND/OR A NUMBER for each answer.",
      "heading": "<HEADING IN CAPITALS>",
      "layout": "<Field label>: {1}\\n<Field label>: {2}\\n<Field label>: {3}",
      "options": [],
      "visual_id": ""
    }
  ],
  "questions": [
    {"number": 1, "group": "g1", "text": "", "options": []},
    {"number": 6, "group": "g2", "text": "<the multiple choice question>",
     "options": [{"letter": "A", "text": "<option>"}, {"letter": "B", "text": "<option>"},
                 {"letter": "C", "text": "<option>"}]}
  ],
  "visuals": [
    {
      "id": "v1",
      "type": "map, floorplan, flowchart, timeline, process or diagram",
      "title": "string",
      "purpose": "string - which questions use it",
      "mermaid": "flowchart TD\\n  A[<fixed landmark>] --> B[13]",
      "image_prompt": "string - a detailed GenAI image-generation prompt describing this visual, used when Mermaid cannot represent it (e.g. a map or floorplan). Leave empty if mermaid is filled in.",
      "answer_mapping": [{"number": 13, "label": "A", "meaning": "<what the student writes>"}],
      "questions": [13, 14]
    }
  ],
  "transcript": [
    {"speaker": "Narrator", "line": "You will hear a conversation between ..."},
    {"speaker": "<SPEAKER ROLE>", "line": "<a full spoken turn, not a one-liner>"}
  ],
  "answers": [
    {"number": 1, "answer": "<the answer>", "alternatives": [], "type": "form_completion",
     "evidence": "the exact transcript sentence that contains the answer"}
  ]
}

Hard rules for this part:
- "questions" holds exactly one entry per question number in this part's range, ascending.
- "answers" holds exactly one entry per question number, ascending.
- Completion groups (form/note/table/flow-chart/sentence/summary) use "layout": a plain-text block in which each blank is written as {N}, N being the question number. Their questions have "text": "" and "options": [].
- A table_completion layout must be a GitHub-flavoured markdown table.
- multiple_choice and multiple_response questions carry their own "options" (3 or 4 each); their answer is the option LETTER ("B", or "B,D" for multiple response).
- matching groups put the shared list in the GROUP's "options"; each question's "text" is the item being matched and its answer is the option LETTER.
- short_answer questions carry the question in "text" and take a written answer.
- plan_map_labelling and diagram_labelling groups set "visual_id" to a visual's id. If the student picks letters off the diagram, put the letter list in the group's "options" and make the answers letters. If the student writes words onto the diagram, leave options empty and make the answers words spoken in the transcript.
- For each visual: fill in "mermaid" if Mermaid can represent it (flowchart, timeline, process). If it cannot (most maps/floorplans), leave "mermaid" empty and instead write a detailed "image_prompt" describing the visual for a GenAI image generator.
- Every written (non-letter) answer must appear VERBATIM in this part's transcript, and the answers must appear in the transcript in the same order as their question numbers.
- Every answer must obey the word limit stated in its group's instruction.
- Never write an answer into "layout", "instruction", "heading", a question's "text", the "mermaid" code, or the "image_prompt". Mermaid shows blanks only - [A], [B] or the bare question number - never the correct label.
- The transcript is TTS-ready spoken English only: no question numbers, no answer markers, no bracketed stage directions, no teacher notes. Open with a short Narrator line, then natural dialogue or lecture.
- Keep the transcript within the length guidance in section 11 of your instructions.
- The recording is played in two halves with a pause between them, split at the boundary between the first question group and the second. Pace the speech so the first group's answers occupy roughly the first 55-65% of the spoken content, and none of the later groups' answers are spoken before that point. The turn that first asks about or introduces a later group's topic counts as belonging to that later group, even though its answer is spoken afterward - so end the first group's dialogue on a natural closing turn (a wrap-up, thanks, or transition line), never on a question that leads into the next group.
"""

VERIFIER_SYSTEM = """You are an independent IELTS Listening quality assurance examiner.

You did not write the test you are given. Your job is to check it honestly and
sceptically, the way a test-taker and then a senior item writer would. You are
rewarded for finding real problems, not for being agreeable. Never assume the
test is correct because it looks professional.

You are being called by an application. Return ONLY valid JSON matching the
schema in the user message: no prose, no commentary, no markdown fences, no
backticks. Escape newlines inside strings as \\n.
"""

BLIND_SOLVE_SCHEMA = """Return JSON in exactly this shape:

{
  "answers": [
    {"number": 1, "answer": "your answer exactly as a candidate would write it",
     "confidence": "high, medium or low",
     "reasoning": "one short sentence naming the transcript evidence you used"}
  ]
}

- Answer EVERY question in the range you were given, in ascending order.
- Obey the word limit printed in each group's instruction.
- For multiple choice, matching and letter-labelling questions answer with the LETTER only.
- If the recording does not let you settle on one defensible answer, still give your best
  answer but set confidence to "low".
"""

AUDIT_SCHEMA = """Return JSON in exactly this shape:

{
  "verdicts": [
    {"number": 1, "verdict": "pass or fail",
     "issue": "empty string when it passes, otherwise one sentence naming the defect"}
  ]
}

Judge every question in the range against these checks:
1. The keyed answer is genuinely stated (or unambiguously paraphrased for multiple choice) in the transcript.
2. The keyed answer respects the word limit in its group's instruction.
3. Exactly one defensible answer exists; no second option can be argued from the transcript.
4. Distractors are plausible but not so misleading that the intended answer becomes indefensible.
5. Nothing in the student-facing text gives the answer away.
6. Where a visual is used, its Mermaid code or image prompt match the questions and the answer mapping, and expose no answers.
7. The question does not depend on outside knowledge.
Give a verdict for every question number in the range.
"""


# --------------------------------------------------------------------------
# JSON Schemas for Gemini structured output (response_format: json_schema)
#
# These mirror the prose *_SCHEMA strings above field-for-field. The prose
# stays in the prompt for business rules JSON Schema can't express (answers
# must appear verbatim in the transcript, etc); these dicts are only for
# structural enforcement via Gemini's constrained decoding, so a Gemini
# response can no longer come back as malformed or off-shape JSON.
# --------------------------------------------------------------------------

QUESTION_GROUP_TYPES = [
    "form_completion", "note_completion", "table_completion",
    "flow_chart_completion", "sentence_completion", "summary_completion",
    "short_answer", "multiple_choice", "multiple_response", "matching",
    "plan_map_labelling", "diagram_labelling",
]

_OPTION_SCHEMA = {
    "type": "object",
    "properties": {
        "letter": {"type": "string"},
        "text": {"type": "string"},
    },
    "required": ["letter", "text"],
}

_SPEAKER_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "role": {"type": "string"},
    },
    "required": ["name", "role"],
}

BLUEPRINT_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "difficulty": {"type": "string"},
        "target_band": {"type": "string"},
        "parts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "part": {"type": "integer"},
                    "topic": {"type": "string"},
                    "setting": {"type": "string"},
                    "format": {"type": "string", "enum": ["conversation", "monologue"]},
                    "speakers": {"type": "array", "items": _SPEAKER_SCHEMA},
                    "question_groups": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "type": {"type": "string", "enum": QUESTION_GROUP_TYPES},
                                "from": {"type": "integer"},
                                "to": {"type": "integer"},
                                "needs_visual": {"type": "boolean"},
                                "visual_type": {"type": "string"},
                            },
                            "required": ["type", "from", "to", "needs_visual", "visual_type"],
                        },
                    },
                },
                "required": ["part", "topic", "setting", "format", "speakers", "question_groups"],
            },
        },
    },
    "required": ["title", "difficulty", "target_band", "parts"],
}

PART_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "part": {"type": "integer"},
        "situation": {"type": "string"},
        "speakers": {"type": "array", "items": _SPEAKER_SCHEMA},
        "question_groups": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "type": {"type": "string", "enum": QUESTION_GROUP_TYPES},
                    "from": {"type": "integer"},
                    "to": {"type": "integer"},
                    "instruction": {"type": "string"},
                    "heading": {"type": "string"},
                    "layout": {"type": "string"},
                    "options": {"type": "array", "items": _OPTION_SCHEMA},
                    "visual_id": {"type": "string"},
                },
                "required": ["id", "type", "from", "to", "instruction", "heading",
                             "layout", "options", "visual_id"],
            },
        },
        "questions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "number": {"type": "integer"},
                    "group": {"type": "string"},
                    "text": {"type": "string"},
                    "options": {"type": "array", "items": _OPTION_SCHEMA},
                },
                "required": ["number", "group", "text", "options"],
            },
        },
        "visuals": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "type": {"type": "string", "enum": [
                        "map", "floorplan", "flowchart", "timeline", "process", "diagram"]},
                    "title": {"type": "string"},
                    "purpose": {"type": "string"},
                    "mermaid": {"type": "string"},
                    "image_prompt": {"type": "string"},
                    "answer_mapping": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "number": {"type": "integer"},
                                "label": {"type": "string"},
                                "meaning": {"type": "string"},
                            },
                            "required": ["number", "label", "meaning"],
                        },
                    },
                    "questions": {"type": "array", "items": {"type": "integer"}},
                },
                "required": ["id", "type", "title", "purpose", "mermaid", "image_prompt",
                             "answer_mapping", "questions"],
            },
        },
        "transcript": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "speaker": {"type": "string"},
                    "line": {"type": "string"},
                },
                "required": ["speaker", "line"],
            },
        },
        "answers": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "number": {"type": "integer"},
                    "answer": {"type": "string"},
                    "alternatives": {"type": "array", "items": {"type": "string"}},
                    "type": {"type": "string"},
                    "evidence": {"type": "string"},
                },
                "required": ["number", "answer", "alternatives", "type", "evidence"],
            },
        },
    },
    "required": ["part", "situation", "speakers", "question_groups", "questions",
                 "visuals", "transcript", "answers"],
}

BLIND_SOLVE_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "answers": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "number": {"type": "integer"},
                    "answer": {"type": "string"},
                    "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
                    "reasoning": {"type": "string"},
                },
                "required": ["number", "answer", "confidence", "reasoning"],
            },
        },
    },
    "required": ["answers"],
}

AUDIT_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "verdicts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "number": {"type": "integer"},
                    "verdict": {"type": "string", "enum": ["pass", "fail"]},
                    "issue": {"type": "string"},
                },
                "required": ["number", "verdict", "issue"],
            },
        },
    },
    "required": ["verdicts"],
}


# --------------------------------------------------------------------------
# generation
# --------------------------------------------------------------------------

def load_system_prompt():
    path = ROOT / "system_prompt.txt"
    if not path.exists():
        sys.exit("system_prompt.txt not found next to generate_test.py")
    return path.read_text(encoding="utf-8").rstrip() + JSON_ADDENDUM


def generate_blueprint(llm, system, args):
    user = (
        "Design the blueprint for one complete IELTS Listening practice test.\n\n"
        "Configuration:\n"
        "- Difficulty: {difficulty}\n"
        "- Target band: {band}\n"
        "- Context: {context}\n"
        "- Topics: {topics}\n\n"
        "The band drives difficulty ONLY. The \"title\" field must not "
        "contain the band, the word \"band\", or any difficulty number - "
        "it is never shown to candidates. Use a clean title such as "
        '''"IELTS Academic Listening Practice Test".\n\n'''
        "{schema}"
    ).format(
        difficulty=args.difficulty,
        band=args.band,
        context=args.context,
        topics=args.topics or "choose four fresh, unrelated topics yourself",
        schema=BLUEPRINT_SCHEMA,
    )
    return llm.json_call(system, user, max_tokens=2500, label="blueprint",
                         schema=BLUEPRINT_JSON_SCHEMA, schema_name="blueprint")


def generate_part(llm, system, blueprint, part_no, args):
    lo, hi = PART_RANGES[part_no]
    spec = next((p for p in as_list(blueprint.get("parts"))
                 if int(p.get("part", 0) or 0) == part_no), {})
    low, high = TRANSCRIPT_TARGET[part_no]
    user = (
        "Write PART {part} of the IELTS Listening test \"{title}\" in full.\n\n"
        "This part covers questions {lo}-{hi} ONLY.\n"
        "Part character: {brief}\n\n"
        "Blueprint for this part:\n{spec}\n\n"
        "Whole-test configuration: difficulty {difficulty}, target band {band}, "
        "{context} context.\n\n"
        "TRANSCRIPT LENGTH IS A HARD REQUIREMENT: this part's transcript must run to "
        "{low}-{high} spoken words. That is a substantial piece of dialogue, not a "
        "summary. Write it out in full, the way it would really be spoken:\n"
        "- speakers talk in flowing turns of one to four sentences, not clipped one-liners\n"
        "- include hesitations, self-corrections, clarifications and natural asides\n"
        "- carry at least three IELTS-style distractors of the kind in section 6 "
        "(a corrected detail, a superseded number or price, a rejected option), so a "
        "careless listener would pick the wrong answer\n"
        "- surround every answer with enough context that the part reads as a real "
        "recording rather than a list of facts\n\n"
        "Invent your own names, places, organisations and numbers for this part. Do "
        "NOT reuse any name, address, venue or scenario that appears in the schema "
        "example below - those are placeholders showing the JSON shape only.\n\n"
        "{schema}"
    ).format(
        part=part_no,
        title=blueprint.get("title", "IELTS Listening Practice Test"),
        lo=lo, hi=hi,
        brief=PART_BRIEF[part_no],
        spec=json.dumps(spec, ensure_ascii=False, indent=2),
        difficulty=args.difficulty,
        band=args.band,
        context=args.context,
        low=low, high=high,
        schema=PART_SCHEMA,
    )
    return llm.json_call(system, user, max_tokens=12000,
                         label="part{}".format(part_no),
                         schema=PART_JSON_SCHEMA, schema_name="part")


def repair_part(llm, system, part, part_no, problems, label):
    lo, hi = PART_RANGES[part_no]
    low, high = TRANSCRIPT_TARGET[part_no]
    current_words = len(" ".join(str(line.get("line", ""))
                                 for line in as_list(part.get("transcript"))).split())
    user = (
        "Part {part} of the test (questions {lo}-{hi}) failed quality checks.\n\n"
        "Problems found:\n{problems}\n\n"
        "Here is the current part JSON:\n{part_json}\n\n"
        "Fix ONLY what the problems list requires. Change as little else as possible: "
        "keep the topic, speakers, question types, group structure and every question "
        "that was not flagged exactly as they are. Where an answer is not properly "
        "supported, prefer editing the transcript so it clearly states the answer.\n\n"
        "DO NOT SHORTEN THE TRANSCRIPT. It currently runs to {current} spoken words and "
        "must still be {low}-{high} words after your fix. Rewriting it as a summary, "
        "trimming turns, or dropping dialogue counts as a failed repair - if you need to "
        "move information around, keep the surrounding speech intact.\n\n"
        "Return the COMPLETE corrected part JSON in the same schema.\n\n{schema}"
    ).format(
        part=part_no, lo=lo, hi=hi,
        problems="\n".join("- " + p for p in problems),
        part_json=json.dumps(part, ensure_ascii=False),
        current=current_words, low=low, high=high,
        schema=PART_SCHEMA,
    )
    return llm.json_call(system, user, max_tokens=12000, temperature=0.3, label=label,
                         schema=PART_JSON_SCHEMA, schema_name="part")


def is_length_error(message):
    return "transcript is only" in message and "spoken words" in message


TRANSCRIPT_EXPANSION_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "transcript": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "speaker": {"type": "string"},
                    "line": {"type": "string"},
                },
                "required": ["speaker", "line"],
            },
        },
    },
    "required": ["transcript"],
}


def expand_transcript(llm, system, part, part_no):
    """Grow a too-short transcript without touching answers, questions or their order."""
    lo, hi = PART_RANGES[part_no]
    low, high = TRANSCRIPT_TARGET[part_no]
    current_words = len(" ".join(str(line.get("line", ""))
                                 for line in as_list(part.get("transcript"))).split())
    answers = sorted(as_list(part.get("answers")), key=lambda a: a.get("number", 0))
    answer_list = [{"number": a.get("number"), "answer": a.get("answer", "")}
                   for a in answers]
    user = (
        "Part {part} of the IELTS Listening test (questions {lo}-{hi}) has a transcript "
        "that is too short: {current} spoken words, but section 11 requires {low}-{high}.\n\n"
        "Here is the current transcript:\n{transcript}\n\n"
        "Here are the answers, in question order. They MUST remain verbatim and in this "
        "exact order in your expanded transcript:\n{answers}\n\n"
        "Expand the transcript to {low}-{high} spoken words by adding natural detail: "
        "hesitations, self-corrections, clarifying questions, asides, and IELTS-style "
        "distractors. Do NOT remove or reword any of the answers above, do NOT change "
        "their order, and do NOT add, remove or renumber any question - you are only "
        "enriching the surrounding dialogue.\n\n"
        "Return ONLY JSON in exactly this shape:\n"
        '{{"transcript": [{{"speaker": "<SPEAKER ROLE>", "line": "<a full spoken turn>"}}]}}'
    ).format(
        part=part_no, lo=lo, hi=hi, current=current_words, low=low, high=high,
        transcript=json.dumps(part.get("transcript"), ensure_ascii=False),
        answers=json.dumps(answer_list, ensure_ascii=False),
    )
    result = llm.json_call(system, user, max_tokens=6000, temperature=0.3,
                           label="expand:p{}".format(part_no),
                           schema=TRANSCRIPT_EXPANSION_JSON_SCHEMA,
                           schema_name="transcript_expansion")
    new_part = dict(part)
    new_part["transcript"] = result.get("transcript") or part.get("transcript")
    return new_part


# --------------------------------------------------------------------------
# local validation
# --------------------------------------------------------------------------

def part_transcript_text(part):
    return "\n".join(
        "{}: {}".format(line.get("speaker", "Speaker"), line.get("line", ""))
        for line in as_list(part.get("transcript"))
    )


def group_index(part):
    index = {}
    for group in as_list(part.get("question_groups")):
        gid = str(group.get("id") or "")
        if gid:
            index[gid] = group
    return index


def group_for(part, question, groups):
    gid = str(question.get("group") or "")
    if gid in groups:
        return groups[gid]
    number = question.get("number")
    for group in as_list(part.get("question_groups")):
        try:
            if int(group.get("from", 0)) <= int(number) <= int(group.get("to", 0)):
                return group
        except (TypeError, ValueError):
            continue
    return {}


def is_letter_answer(group, question):
    if str(group.get("type", "")) in LETTER_ANSWER_TYPES:
        return True
    return bool(as_list(group.get("options")) or as_list(question.get("options")))


def student_text_of(group, question):
    return " ".join([
        str(group.get("layout", "")),
        str(group.get("heading", "")),
        str(group.get("instruction", "")),
        str(question.get("text", "")),
    ])


def validate_part(part, part_no):
    """Local structural/answer checks. Returns (errors, warnings)."""
    errors, warnings = [], []
    lo, hi = PART_RANGES[part_no]
    expected = list(range(lo, hi + 1))

    questions = sorted(as_list(part.get("questions")),
                       key=lambda q: q.get("number", 0))
    answers = sorted(as_list(part.get("answers")),
                     key=lambda a: a.get("number", 0))

    qnums = [q.get("number") for q in questions]
    anums = [a.get("number") for a in answers]
    if qnums != expected:
        errors.append("questions must be numbered {}-{} exactly once each; got {}"
                      .format(lo, hi, qnums))
    if anums != expected:
        errors.append("answers must be numbered {}-{} exactly once each; got {}"
                      .format(lo, hi, anums))

    groups = group_index(part)
    by_number = {q.get("number"): q for q in questions}
    transcript = part_transcript_text(part)
    tnorm = norm(transcript)
    spoken = " ".join(str(line.get("line", "")) for line in as_list(part.get("transcript")))
    words = len(spoken.split())
    low, high = TRANSCRIPT_TARGET[part_no]
    if words < TRANSCRIPT_FLOOR[part_no]:
        errors.append("part {} transcript is only {} spoken words; section 11 requires "
                      "roughly {}-{}. Expand the dialogue with natural detail, "
                      "hesitations, self-corrections and IELTS-style distractors - do "
                      "not add new questions or change any answer"
                      .format(part_no, words, low, high))
    elif words < low:
        warnings.append("part {} transcript is {} words, under the {}-{} guidance"
                        .format(part_no, words, low, high))

    turns = [t for t in as_list(part.get("transcript")) if str(t.get("line", "")).strip()]
    if turns and words / len(turns) < 9:
        errors.append("part {} transcript averages only {:.1f} words per turn - the "
                      "speech is unnaturally clipped. Write flowing spoken English "
                      "instead of one-line exchanges".format(part_no, words / len(turns)))

    if re.search(r"question\s*\d|answer\s*key|correct answer", transcript, re.I):
        errors.append("transcript contains question numbers or answer annotations")

    visuals = {str(v.get("id")): v for v in as_list(part.get("visuals"))}
    cursor = 0
    written_seen = {}

    for answer in answers:
        number = answer.get("number")
        value = str(answer.get("answer", "")).strip()
        alternatives = [str(a) for a in as_list(answer.get("alternatives"))]
        question = by_number.get(number, {})
        group = group_for(part, question, groups) if question else {}

        if not value:
            errors.append("Q{}: answer is empty".format(number))
            continue
        if not question:
            continue
        if not group:
            errors.append("Q{}: question does not belong to any question group".format(number))
            continue

        if is_letter_answer(group, question):
            options = as_list(question.get("options")) or as_list(group.get("options"))
            letters = {str(o.get("letter", "")).strip().upper() for o in options}
            if not letters:
                errors.append("Q{}: {} question has no options to choose from"
                              .format(number, group.get("type")))
                continue
            given = [p.strip().upper() for p in re.split(r"[,\s/]+", value) if p.strip()]
            unknown = [g for g in given if g not in letters]
            if unknown:
                errors.append("Q{}: answer '{}' is not among the options {}"
                              .format(number, value, sorted(letters)))
            wanted = 2 if str(group.get("type")) == "multiple_response" else 1
            if len(given) != wanted:
                errors.append("Q{}: expected {} option letter(s), got '{}'"
                              .format(number, wanted, value))
            continue

        # written answer: must be in the transcript, in order, within the limit
        needle = norm(value)
        if not needle:
            errors.append("Q{}: answer '{}' normalises to nothing".format(number, value))
            continue
        written_seen.setdefault(needle, []).append(number)
        position = find_phrase(tnorm, needle, cursor)
        if position == -1:
            if find_phrase(tnorm, needle) == -1:
                errors.append("Q{}: answer '{}' never appears in the part {} transcript"
                              .format(number, value, part_no))
            else:
                errors.append("Q{}: answer '{}' appears in the transcript out of order "
                              "(it is spoken before an earlier question's answer)"
                              .format(number, value))
        else:
            cursor = position + len(needle)

        max_words, allow_number = parse_word_limit(group.get("instruction"))
        word_count, number_count = answer_shape(value)
        if max_words is not None and word_count > max_words:
            errors.append("Q{}: answer '{}' has {} words but the instruction allows {}"
                          .format(number, value, word_count, max_words))
        if max_words is not None and number_count and not allow_number:
            errors.append("Q{}: answer '{}' contains a number but the instruction "
                          "does not allow one".format(number, value))

        if len(needle) >= 3 and find_phrase(norm(student_text_of(group, question)), needle) != -1:
            errors.append("Q{}: answer '{}' is visible in the student-facing text"
                          .format(number, value))

        visual = visuals.get(str(group.get("visual_id") or ""))
        if visual and len(needle) >= 3 and find_phrase(norm(visual.get("mermaid", "")), needle) != -1:
            errors.append("Q{}: answer '{}' is printed in the Mermaid code students see"
                          .format(number, value))
        if visual and len(needle) >= 3 and find_phrase(norm(visual.get("image_prompt", "")), needle) != -1:
            errors.append("Q{}: answer '{}' is printed in the image prompt students see"
                          .format(number, value))

    # Pacing: can the recording actually be split where the narrator says it is?
    if part_no != 4:
        resolved = resolve_mid_break(part, part_no)
        if resolved.split is None:
            warnings.append(
                "part {} cannot be split for the mid-section break, so it will "
                "play straight through and the narrator will announce questions "
                "{}-{} in one go - the answers are spread so that no cut "
                "separates the question groups".format(
                    part_no, resolved.q_from, resolved.q_to))
        elif resolved.resolved_by == "proportional":
            warnings.append(
                "part {} mid-break falls on a proportional estimate: no answer "
                "could be located in the transcript to anchor it".format(part_no))

    for needle, numbers in written_seen.items():
        if len(numbers) > 1:
            first, *rest = numbers
            for other in rest:
                errors.append(
                    "Q{} and Q{} share the answer '{}' - each question must have a "
                    "distinct answer; rewrite one question so it targets different "
                    "information".format(first, other, needle))

    for group in as_list(part.get("question_groups")):
        gtype = str(group.get("type", ""))
        vid = str(group.get("visual_id") or "")
        if vid and vid not in visuals:
            errors.append("group {} references visual '{}' which does not exist"
                          .format(group.get("id"), vid))
        if gtype in {"plan_map_labelling", "diagram_labelling"} and not vid:
            errors.append("group {} is {} but has no visual".format(group.get("id"), gtype))
        if not str(group.get("instruction", "")).strip():
            errors.append("group {} has no instruction line".format(group.get("id")))

        layout = str(group.get("layout", ""))
        if gtype not in LETTER_ANSWER_TYPES and layout.strip():
            placeholders = {int(n) for n in re.findall(r"\{\s*(\d+)\s*\}", layout)}
            try:
                span = set(range(int(group.get("from")), int(group.get("to")) + 1))
            except (TypeError, ValueError):
                span = set()
            missing = sorted(span - placeholders)
            if missing:
                errors.append("group {} layout has no {{N}} blank for question(s) {}"
                              .format(group.get("id"),
                                      ", ".join(str(n) for n in missing)))
        elif gtype not in LETTER_ANSWER_TYPES and gtype in {
                "form_completion", "note_completion", "table_completion",
                "flow_chart_completion", "summary_completion"}:
            errors.append("group {} is {} but has no layout block"
                          .format(group.get("id"), gtype))

    for visual in as_list(part.get("visuals")):
        mermaid = str(visual.get("mermaid", "")).strip()
        image_prompt = str(visual.get("image_prompt", "")).strip()
        if not mermaid and not image_prompt:
            warnings.append("visual {} has neither Mermaid code nor an image prompt"
                            .format(visual.get("id")))

        if mermaid and not re.match(
                r"(flowchart|graph|timeline|block-beta|architecture-beta|xychart|"
                r"stateDiagram|mindmap|sequenceDiagram|classDiagram|journey|pie|"
                r"quadrantChart|sankey|gitGraph|requirementDiagram|packet-beta|kanban)",
                mermaid.strip(), re.I):
            errors.append("visual {} Mermaid code does not start with a diagram type "
                          "declaration".format(visual.get("id")))
        for mapping in as_list(visual.get("answer_mapping")):
            if mapping.get("number") not in expected:
                warnings.append("visual {} maps question {} which is not in this part"
                                .format(visual.get("id"), mapping.get("number")))

    return errors, warnings


def validate_test(parts):
    """Whole-test checks once the parts are assembled."""
    errors = []
    numbers = []
    for part in parts:
        numbers.extend(a.get("number") for a in as_list(part.get("answers")))
    numbers = sorted(n for n in numbers if isinstance(n, int))
    if numbers != list(range(1, 41)):
        errors.append("assembled test does not have exactly 40 answers numbered 1-40 "
                      "(got {})".format(len(numbers)))
    return errors


# --------------------------------------------------------------------------
# rendering
# --------------------------------------------------------------------------

BLANK = "_" * 12


def render_layout(layout, numbers):
    """Replace {N} placeholders with printed blanks, keeping the line structure."""
    wanted = set(numbers)

    def blank(match):
        number = int(match.group(1))
        if number not in wanted:
            return match.group(0)
        return "**{}** {}".format(number, BLANK)

    text = re.sub(r"\{\s*(\d+)\s*\}", blank, str(layout or ""))
    if "|" in text and re.search(r"\|\s*:?-{3,}", text):
        return text                     # markdown table: leave the pipes alone
    lines = [line.rstrip() for line in text.split("\n")]
    return "\n".join(line + "  " if line.strip() else line for line in lines)


def render_options(options, indent=""):
    lines = []
    for option in as_list(options):
        lines.append("{}- **{}** {}".format(indent, option.get("letter", "?"),
                                            option.get("text", "")))
    return "\n".join(lines)


def render_visual_block(visual):
    img_filename = visual.get("image_filename")
    if img_filename:
        return "![{}]({})".format(visual.get("title", "Visual"), img_filename)
    mermaid = str(visual.get("mermaid", "")).strip()
    if mermaid:
        return "```mermaid\n{}\n```".format(mermaid)
    vid = visual.get("id", "visual")
    return "![{}]({}.png)".format(visual.get("title", "Visual"), f"visual_{vid}")


def render_part_questions(part, part_no):
    """Student-facing markdown for one part (no answers anywhere)."""
    lo, hi = PART_RANGES[part_no]
    out = ["## PART {}".format(part_no), "", "**Questions {}-{}**".format(lo, hi), ""]
    situation = str(part.get("situation", "")).strip()
    if situation:
        out += ["*{}*".format(situation), ""]

    questions = sorted(as_list(part.get("questions")), key=lambda q: q.get("number", 0))
    visuals = {str(v.get("id")): v for v in as_list(part.get("visuals"))}

    for group in as_list(part.get("question_groups")):
        gid = str(group.get("id") or "")
        members = [q for q in questions if str(q.get("group") or "") == gid]
        if not members:
            members = [q for q in questions
                       if group.get("from") is not None
                       and int(group.get("from", 0)) <= int(q.get("number", 0))
                       <= int(group.get("to", 0))]
        numbers = [int(q.get("number")) for q in members if q.get("number") is not None]
        if numbers:
            out.append("### Questions {}-{}".format(min(numbers), max(numbers))
                       if len(numbers) > 1 else "### Question {}".format(numbers[0]))
            out.append("")
        for line in str(group.get("instruction", "")).split("\n"):
            if line.strip():
                out += ["*{}*".format(line.strip()), ""]

        visual = visuals.get(str(group.get("visual_id") or ""))
        if visual:
            out += [render_visual_block(visual), ""]

        heading = str(group.get("heading", "")).strip()
        if heading:
            out += ["**{}**".format(heading), ""]

        layout = str(group.get("layout", "")).strip()
        if layout:
            out += [render_layout(layout, numbers), ""]

        group_options = as_list(group.get("options"))
        if group_options:
            out += [render_options(group_options), ""]

        for question in members:
            number = question.get("number")
            text = str(question.get("text", "")).strip()
            options = as_list(question.get("options"))
            if not text and layout:
                continue
            if text:
                out += ["**{}** {}".format(number, text), ""]
            elif not options:
                out += ["**{}** {}".format(number, BLANK), ""]
            if options:
                out += [render_options(options), ""]
            elif text and not layout:
                out += ["{}".format(BLANK), ""]
    return "\n".join(out).rstrip() + "\n"


def render_student_paper(test):
    out = [
        "# {}".format(test["metadata"]["title"]),
        "",
        "**IELTS LISTENING PRACTICE TEST**",
        "",
        "**Instructions**",
        "",
        STUDENT_INSTRUCTIONS,
        "",
        "Time: approximately 30 minutes. Questions: 40. Marks: 40.",
        "",
        "---",
        "",
    ]
    for part_no, part in enumerate(test["parts"], start=1):
        out += [render_part_questions(part, part_no), "", "---", ""]
    return "\n".join(out).rstrip() + "\n"


def render_transcript(test):
    out = []
    for part_no, part in enumerate(test["parts"], start=1):
        out += ["PART {}".format(part_no), ""]
        for line in as_list(part.get("transcript")):
            speaker = str(line.get("speaker", "Speaker")).strip()
            spoken = " ".join(str(line.get("line", "")).split())
            if spoken:
                out.append("{}: {}".format(speaker, spoken))
        out += ["", ""]
    return "\n".join(out).rstrip() + "\n"


def render_answer_key(test):
    out = [
        "# ANSWER KEY - {}".format(test["metadata"]["title"]),
        "",
        "| # | Answer | Accepted alternatives | Question type |",
        "|---|--------|-----------------------|---------------|",
    ]
    rows = []
    for part in test["parts"]:
        groups = group_index(part)
        by_number = {q.get("number"): q for q in as_list(part.get("questions"))}
        for answer in as_list(part.get("answers")):
            number = answer.get("number")
            question = by_number.get(number, {})
            group = group_for(part, question, groups) if question else {}
            rows.append((
                number,
                str(answer.get("answer", "")),
                ", ".join(str(a) for a in as_list(answer.get("alternatives"))) or "-",
                str(answer.get("type") or group.get("type", "")).replace("_", " "),
            ))
    for number, value, alternatives, qtype in sorted(rows, key=lambda r: r[0] or 0):
        out.append("| {} | {} | {} | {} |".format(number, value, alternatives, qtype))
    out += ["", "**TOTAL MARKS: 40**", ""]

    verification = test.get("verification") or {}
    if verification.get("questions"):
        out += ["## Verifier notes", ""]
        flagged = [q for q in verification["questions"] if q.get("status") != "ok"]
        if not flagged:
            out.append("All 40 questions passed the blind solve and the audit.")
        else:
            for item in flagged:
                out.append("- Q{}: {} ({})".format(
                    item.get("number"), item.get("issue") or "flagged",
                    item.get("status")))
        out.append("")
    return "\n".join(out).rstrip() + "\n"


def render_visuals(test):
    out = ["# VISUAL SPECIFICATIONS - {}".format(test["metadata"]["title"]), ""]
    found = False
    for part_no, part in enumerate(test["parts"], start=1):
        for visual in as_list(part.get("visuals")):
            found = True
            out += [
                "## PART {} - {}".format(part_no, visual.get("id", "visual")),
                "",
                "- **Type:** {}".format(visual.get("type", "")),
                "- **Title:** {}".format(visual.get("title", "")),
                "- **Purpose:** {}".format(visual.get("purpose", "")),
                "- **Questions:** {}".format(
                    ", ".join(str(q) for q in as_list(visual.get("questions")))),
                "",
            ]
            mermaid = str(visual.get("mermaid", "")).strip()
            image_prompt = str(visual.get("image_prompt", "")).strip()
            if mermaid:
                out += ["**Mermaid (student-facing, blanks only)**", "",
                        "```mermaid\n{}\n```".format(mermaid), ""]
            if image_prompt:
                out += ["**GenAI image prompt**", "", image_prompt, ""]
            if not mermaid and not image_prompt:
                out += ["_No Mermaid code or image prompt supplied._", ""]
            out += ["**Answer mapping (internal - not for students)**", "",
                    "| Question | Label | Meaning |", "|---|---|---|"]
            for mapping in as_list(visual.get("answer_mapping")):
                out.append("| {} | {} | {} |".format(
                    mapping.get("number", ""), mapping.get("label", ""),
                    mapping.get("meaning", "")))
            out.append("")
    if not found:
        return None
    return "\n".join(out).rstrip() + "\n"


# --------------------------------------------------------------------------
# LLM verification agent
# --------------------------------------------------------------------------

def blind_solve(llm, part, part_no):
    """Verifier answers the part as a candidate would, never seeing the key."""
    lo, hi = PART_RANGES[part_no]
    user = (
        "Sit part {part} of an IELTS Listening test as a candidate.\n\n"
        "You get the questions and the full recording transcript. Answer questions "
        "{lo}-{hi}.\n\n"
        "=== QUESTIONS ===\n{questions}\n\n"
        "=== TRANSCRIPT ===\n{transcript}\n\n{schema}"
    ).format(
        part=part_no, lo=lo, hi=hi,
        questions=render_part_questions(part, part_no),
        transcript=part_transcript_text(part),
        schema=BLIND_SOLVE_SCHEMA,
    )
    data = llm.json_call(VERIFIER_SYSTEM, user, max_tokens=6000, temperature=0.0,
                         label="verify:solve:p{}".format(part_no),
                         schema=BLIND_SOLVE_JSON_SCHEMA, schema_name="blind_solve")
    return {int(a["number"]): a for a in as_list(data.get("answers"))
            if isinstance(a, dict) and str(a.get("number", "")).isdigit()}


def audit_part(llm, part, part_no):
    """Verifier audits the full package for the part, key included."""
    lo, hi = PART_RANGES[part_no]
    key_lines = []
    by_number = {q.get("number"): q for q in as_list(part.get("questions"))}
    groups = group_index(part)
    for answer in sorted(as_list(part.get("answers")), key=lambda a: a.get("number", 0)):
        question = by_number.get(answer.get("number"), {})
        group = group_for(part, question, groups) if question else {}
        key_lines.append("{}. {} [{}] (alternatives: {}) evidence: {}".format(
            answer.get("number"), answer.get("answer"),
            group.get("type", answer.get("type", "")),
            ", ".join(str(a) for a in as_list(answer.get("alternatives"))) or "none",
            answer.get("evidence", "")))
    visual_spec = json.dumps(as_list(part.get("visuals")), ensure_ascii=False, indent=2) \
        if as_list(part.get("visuals")) else "none"
    user = (
        "Audit part {part} (questions {lo}-{hi}) of an IELTS Listening test.\n\n"
        "=== STUDENT-FACING PAPER ===\n{questions}\n\n"
        "=== ANSWER KEY ===\n{key}\n\n"
        "=== TRANSCRIPT ===\n{transcript}\n\n"
        "=== VISUAL SPECIFICATION ===\n{visuals}\n\n{schema}"
    ).format(
        part=part_no, lo=lo, hi=hi,
        questions=render_part_questions(part, part_no),
        key="\n".join(key_lines),
        transcript=part_transcript_text(part),
        visuals=visual_spec,
        schema=AUDIT_SCHEMA,
    )
    data = llm.json_call(VERIFIER_SYSTEM, user, max_tokens=6000, temperature=0.0,
                         label="verify:audit:p{}".format(part_no),
                         schema=AUDIT_JSON_SCHEMA, schema_name="audit")
    return {int(v["number"]): v for v in as_list(data.get("verdicts"))
            if isinstance(v, dict) and str(v.get("number", "")).isdigit()}


def verify_part(llm, part, part_no):
    """Run both verifier passes and merge them into per-question records."""
    solved = blind_solve(llm, part, part_no)
    verdicts = audit_part(llm, part, part_no)
    records = []
    for answer in sorted(as_list(part.get("answers")), key=lambda a: a.get("number", 0)):
        number = answer.get("number")
        expected = str(answer.get("answer", ""))
        alternatives = [str(a) for a in as_list(answer.get("alternatives"))]
        attempt = solved.get(number, {})
        given = str(attempt.get("answer", ""))
        confidence = str(attempt.get("confidence", "")).lower() or "missing"
        matched = matches_answer(given, expected, alternatives) if given else False
        verdict = verdicts.get(number, {})
        passed = str(verdict.get("verdict", "")).lower().startswith("pass")

        issues = []
        if not given:
            issues.append("verifier returned no answer for this question")
        elif not matched:
            issues.append("blind solve produced '{}' but the key says '{}'"
                          .format(given, expected))
        if confidence == "low":
            issues.append("verifier was not confident the answer is determinable")
        if verdict and not passed:
            issues.append(str(verdict.get("issue") or "audit failed"))
        if not verdict:
            issues.append("audit returned no verdict for this question")

        records.append({
            "number": number,
            "key_answer": expected,
            "blind_answer": given,
            "blind_matched": matched,
            "confidence": confidence,
            "audit_verdict": "pass" if passed else "fail",
            "issue": "; ".join(issues),
            "status": "ok" if not issues else "flagged",
        })
    return records


def run_verification(llm, system, parts, verification_state):
    """Verify every part, repair flagged questions once, then re-verify."""
    for index, part in enumerate(parts):
        part_no = index + 1
        print("  verifying part {} ...".format(part_no))
        records = verify_part(llm, part, part_no)
        flagged = [r for r in records if r["status"] != "ok"]

        if flagged:
            print("    {} question(s) flagged - repairing".format(len(flagged)))
            problems = ["Q{}: {}".format(r["number"], r["issue"]) for r in flagged]
            try:
                repaired = repair_part(llm, system, part, part_no, problems,
                                       "verify:repair:p{}".format(part_no))
                errors, _ = validate_part(repaired, part_no)
                if any(is_length_error(e) for e in errors):
                    print("    repaired part undershoots the word-count floor - "
                          "expanding transcript")
                    repaired = expand_transcript(llm, system, repaired, part_no)
                    errors, _ = validate_part(repaired, part_no)
                if errors:
                    print("    repaired part fails {} local check(s) - re-verifying it "
                          "before deciding whether to keep it".format(len(errors)))
                new_records = verify_part(llm, repaired, part_no)
                new_flagged = [r for r in new_records if r["status"] != "ok"]

                if len(new_flagged) < len(flagged) and not errors:
                    parts[index] = repaired
                    records, flagged = new_records, new_flagged
                    print("    repair accepted: {} question(s) still flagged"
                          .format(len(flagged)) if flagged
                          else "    repair accepted: all questions clean")
                else:
                    # never ship a version the verifier likes less than the original
                    print("    repair rejected ({} flagged before, {} after{}) - "
                          "keeping the original part".format(
                              len(flagged), len(new_flagged),
                              ", plus new local errors" if errors else ""))
            except Exception as exc:                        # noqa: BLE001
                print("    ! repair failed ({}) - keeping the original part".format(exc))

        verification_state["questions"].extend(records)

    solved = sum(1 for r in verification_state["questions"] if r["blind_matched"])
    total = len(verification_state["questions"])
    clean = sum(1 for r in verification_state["questions"] if r["status"] == "ok")
    verification_state["blind_solve_score"] = "{}/{} solved".format(solved, total)
    verification_state["clean_questions"] = "{}/{}".format(clean, total)
    verification_state["flagged"] = [r["number"] for r in verification_state["questions"]
                                     if r["status"] != "ok"]
    return verification_state


# --------------------------------------------------------------------------
# orchestration
# --------------------------------------------------------------------------

def next_output_dir(base):
    base.mkdir(parents=True, exist_ok=True)
    existing = [int(m.group(1)) for m in
                (re.fullmatch(r"test_(\d+)", p.name) for p in base.iterdir() if p.is_dir())
                if m]
    return base / "test_{:03d}".format(max(existing, default=0) + 1)


def build_test(llm, system, args):
    print("Blueprint ...")
    blueprint = generate_blueprint(llm, system, args)

    parts, validation = [], {"parts": {}, "repaired": [], "unresolved": []}
    for part_no in (1, 2, 3, 4):
        print("Part {} ...".format(part_no))
        part = generate_part(llm, system, blueprint, part_no, args)
        errors, warnings = validate_part(part, part_no)

        if errors:
            print("    {} local error(s) - requesting a repair".format(len(errors)))
            for error in errors[:6]:
                print("      - {}".format(error))
            try:
                if any(is_length_error(e) for e in errors):
                    print("    expanding transcript to reach the word-count floor")
                    part = expand_transcript(llm, system, part, part_no)
                    errors, warnings = validate_part(part, part_no)

                if errors:
                    repaired = repair_part(llm, system, part, part_no, errors,
                                           "repair:p{}".format(part_no))
                    new_errors, new_warnings = validate_part(repaired, part_no)
                    if not new_errors or len(new_errors) < len(errors):
                        part, errors, warnings = repaired, new_errors, new_warnings
                        validation["repaired"].append(part_no)
                    else:
                        # the repair traded one defect for another - keep the known state
                        print("    repair did not reduce the error count ({} -> {}) - "
                              "keeping the original part".format(len(errors), len(new_errors)))
                else:
                    validation["repaired"].append(part_no)

                if errors:
                    print("    still {} error(s) after repair - continuing anyway"
                          .format(len(errors)))
                    validation["unresolved"].append(part_no)
                else:
                    print("    repair clean")
            except Exception as exc:                        # noqa: BLE001
                print("    ! repair failed ({}) - keeping the original part".format(exc))
                validation["unresolved"].append(part_no)
        else:
            print("    local checks passed")

        validation["parts"][str(part_no)] = {"errors": errors, "warnings": warnings}
        parts.append(part)

    validation["assembly_errors"] = validate_test(parts)

    metadata = {
        "title": blueprint.get("title", "IELTS Listening Practice Test"),
        "target_band": blueprint.get("target_band", args.band),
        "difficulty": blueprint.get("difficulty", args.difficulty),
        "context": args.context,
        "total_parts": 4,
        "total_questions": 40,
        "total_marks": 40,
        "model": llm.model,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "part_topics": {str(p.get("part")): p.get("topic")
                        for p in as_list(blueprint.get("parts"))},
        "visuals_required": any(as_list(p.get("visuals")) for p in parts),
    }
    return {"metadata": metadata, "blueprint": blueprint, "parts": parts,
            "validation": validation, "verification": None}


PHONE_HINTS = ("calling", "call the", "phone", "telephone", "hotline",
               "speaking?", "on the line", "ring")


def detect_phone_call(part):
    """True if this part's scene is a phone conversation.

    Stage 2 reads the resulting audio_cues.phone_call flag to decide whether to
    play the ring + pickup cue before the dialogue. Hand-editable in test.json.
    """
    blob = str(part.get("situation", "")).lower()
    for entry in as_list(part.get("transcript"))[:3]:
        if isinstance(entry, dict):
            blob += " " + str(entry.get("line", "")).lower()
    return any(hint in blob for hint in PHONE_HINTS)


def annotate_audio_cues(test, llm=None):
    """Tag each part with the audio cues Stage 2 needs.

    Runs from write_outputs, after every repair and verification round-trip, so
    the resolved mid-break is computed against the transcript that actually
    ships. mid_break is null for Part 4 and for any part with no usable split
    point; Stage 2 then plays that part straight through and the narrator
    announces the whole question range at once.

    When `llm` is given, parts 1-3 first ask split_labeler to name the turn
    that opens the second question group - the fix for the answer-anchored
    heuristic always landing the break between a question and its answer. A
    labeler failure or rejection falls back to that heuristic, loudly (a `!`
    line here), so the regression shows up in this log rather than only in
    the finished video.
    """
    for part_no, part in enumerate(as_list(test.get("parts")), start=1):
        cues = part.setdefault("audio_cues", {})
        cues["phone_call"] = detect_phone_call(part)

        boundary_turn = None
        use_labeler = llm is not None and part_no in (1, 2, 3)
        q_mid = question_ranges(part, part_no)[1] if use_labeler else None
        if use_labeler:
            try:
                boundary_turn = split_labeler.label_boundary(llm, part, part_no, q_mid)
            except Exception as exc:                        # noqa: BLE001
                print("  ! part {}: labeler call failed ({})".format(part_no, exc))

        record, resolved = annotate_mid_break(part, part_no, boundary_turn=boundary_turn)
        cues["mid_break"] = record
        print("  part {}: {}".format(part_no, describe_mid_break(resolved, part_no)))
        if use_labeler and boundary_turn is None:
            print("  ! part {}: mid-break fell back to {}; question {}'s lead-in "
                  "may play in the first half".format(part_no, resolved.resolved_by,
                                                       q_mid + 1))


def write_outputs(test, out_dir, llm=None):
    out_dir.mkdir(parents=True, exist_ok=True)
    annotate_audio_cues(test, llm=llm)
    visual_files = []
    try:
        visual_files = process_test_visuals(test, out_dir)
    except Exception as exc:
        print("! Error processing visuals: {}".format(exc))

    (out_dir / "test.json").write_text(
        json.dumps(test, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "student_paper.md").write_text(render_student_paper(test), encoding="utf-8")
    (out_dir / "transcript.txt").write_text(render_transcript(test), encoding="utf-8")
    (out_dir / "answer_key.md").write_text(render_answer_key(test), encoding="utf-8")
    visuals = render_visuals(test)
    written = ["test.json", "student_paper.md", "transcript.txt", "answer_key.md"]
    if visuals:
        (out_dir / "visuals.md").write_text(visuals, encoding="utf-8")
        written.append("visuals.md")
    written.extend(visual_files)
    return written


def print_summary(test, out_dir, written, llm):
    validation = test["validation"]
    local_errors = sum(len(v["errors"]) for v in validation["parts"].values())
    local_warnings = sum(len(v["warnings"]) for v in validation["parts"].values())

    print("\n" + "=" * 62)
    print(test["metadata"]["title"])
    print("=" * 62)
    print("Output      : {}".format(out_dir))
    print("Files       : {}".format(", ".join(written)))
    print("Model       : {}  ({} API calls)".format(llm.model, llm.calls))
    print("Local checks: {} error(s), {} warning(s)".format(local_errors, local_warnings))
    if validation["repaired"]:
        print("Repaired    : part(s) {}".format(
            ", ".join(str(p) for p in validation["repaired"])))
    if validation["unresolved"]:
        print("UNRESOLVED  : part(s) {} still have local errors".format(
            ", ".join(str(p) for p in validation["unresolved"])))
    if validation["assembly_errors"]:
        for error in validation["assembly_errors"]:
            print("ASSEMBLY    : {}".format(error))

    verification = test.get("verification")
    if not verification:
        print("Verifier    : skipped (--skip-verify)")
    else:
        print("Blind solve : {}".format(verification["blind_solve_score"]))
        print("Clean       : {} questions passed both verifier passes".format(
            verification["clean_questions"]))
        flagged = verification["flagged"]
        if flagged:
            print("Flagged     : Q{}".format(", Q".join(str(n) for n in flagged)))
            for record in verification["questions"]:
                if record["status"] != "ok":
                    print("   Q{:<3} {}".format(record["number"], record["issue"]))
        else:
            print("Flagged     : none")
    print("=" * 62)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Generate an original IELTS Listening practice test.")
    parser.add_argument("--band", default="9.0", help="target band, e.g. 7 or 7.5")
    parser.add_argument("--difficulty", default="",
                        help='difficulty label, e.g. "IELTS 7.0" (defaults to the band)')
    parser.add_argument("--context", default="academic",
                        choices=["academic", "general"], help="test context")
    parser.add_argument("--topics", default="",
                        help="optional comma-separated topic hints for the four parts")
    parser.add_argument("--provider", default="gemini", choices=["nvidia", "gemini"],
                        help="which API to use (default: gemini)")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="NVIDIA NIM model id")
    parser.add_argument("--gemini-model", default=DEFAULT_GEMINI_MODEL,
                        help="Gemini model id, used for --provider gemini and for the "
                             "NVIDIA->Gemini fallback")
    parser.add_argument("--out", default="tests", help="output folder (default: tests)")
    parser.add_argument("--temperature", type=float, default=0.7)
    parser.add_argument("--nvidia-schema", default="auto",
                        choices=["auto", "json_schema", "guided_json", "off"],
                        help="structured-output style to use on NVIDIA NIM (default: auto-"
                             "probe json_schema then guided_json; off restores plain "
                             "json_object mode)")
    parser.add_argument("--skip-verify", action="store_true",
                        help="skip the LLM verification agent (faster dev runs)")
    args = parser.parse_args(argv)
    if not args.difficulty:
        args.difficulty = "IELTS {}".format(args.band)
    return args


def main(argv=None):
    args = parse_args(argv)
    system = load_system_prompt()
    llm = LLM(args.provider, args.model, gemini_model=args.gemini_model,
              temperature=args.temperature, nvidia_schema=args.nvidia_schema)

    print("Generating an IELTS Listening test ({}, band {}) with provider={} model={}\n".format(
        args.difficulty, args.band, args.provider,
        args.model if args.provider == "nvidia" else args.gemini_model))

    test = build_test(llm, system, args)

    if args.skip_verify:
        print("\nSkipping LLM verification (--skip-verify)")
    else:
        print("\nLLM verification agent ...")
        state = {"questions": [], "blind_solve_score": "", "clean_questions": "",
                 "flagged": []}
        try:
            test["verification"] = run_verification(llm, system, test["parts"], state)
        except Exception as exc:                            # noqa: BLE001
            print("! verification failed ({}) - writing the test unverified".format(exc))
            state["error"] = str(exc)
            test["verification"] = state

    out_dir = next_output_dir(Path(args.out) if Path(args.out).is_absolute()
                              else ROOT / args.out)
    written = write_outputs(test, out_dir, llm=llm)
    print_summary(test, out_dir, written, llm)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit("\nInterrupted.")
