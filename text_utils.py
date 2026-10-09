"""Small text helpers shared by the generator, the renderers and the uploader.

Kept separate from render_screens.py so youtube_upload.py can import it without
pulling in Playwright, and so midbreak.py can import it without pulling in the
LLM client stack that generate_test.py carries.
"""

from __future__ import annotations

import re
import unicodedata

DEFAULT_TITLE = "IELTS Listening Practice Test"


def norm(text):
    """Lowercase, strip accents/punctuation/currency, collapse whitespace."""
    s = unicodedata.normalize("NFKD", str(text))
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.replace("’", "'").replace("‘", "'")
    s = s.lower()
    s = re.sub(r"[^a-z0-9' ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def find_phrase(haystack, needle, start=0):
    """Position of needle in haystack matching at word boundaries only, else -1."""
    m = re.compile(r"(?<!\S)" + re.escape(needle) + r"(?!\S)").search(haystack, start)
    return m.start() if m else -1

# Band artifacts an LLM-authored title tends to carry: "Band 7.0", "Target
# Band: 7", "(Band 7.5)", or a bare trailing "7.0" as in the real generated
# title "IELTS Listening Practice Test - Academic 7.0".
_BAND_PATTERNS = [
    re.compile(r"[\(\[\-\u2013\u2014|,:;]*\s*(?:target\s+)?band\s*[:\-\u2013]?\s*\d+(?:\.\d+)?\s*[\)\]]*",
               re.IGNORECASE),
    re.compile(r"[\(\[\-\u2013\u2014|,:;]*\s*(?:target\s+)?band\s*[:\-\u2013]?\s*\d+(?:\.\d+)?\s*[\)\]]*$",
               re.IGNORECASE),
    re.compile(r"[\(\[\-\u2013\u2014|,:;]\s*\d+\.\d+\s*[\)\]]?\s*$"),
    re.compile(r"\s+\d+\.\d+\s*$"),
]

_SEPARATOR_TAIL = re.compile(r"[\s\-\u2013\u2014|,:;\(\[]+$")
_SEPARATOR_HEAD = re.compile(r"^[\s\-\u2013\u2014|,:;\)\]]+")


def clean_title(title: str | None) -> str:
    """Strip target-band artifacts and the "Academic" qualifier from a test title.

    The band is an internal generation parameter and must never reach a viewer,
    but the model writes it into the title anyway (tests/test_009-012 all say
    "IELTS Listening Practice Test - Academic 7.0"). The "Academic" word is
    dropped from all viewer-facing titles per the 2026-10-09 request. Sanitizing
    here means already-generated tests render clean without regeneration.
    """
    text = (title or "").strip()
    if not text:
        return DEFAULT_TITLE

    for pattern in _BAND_PATTERNS:
        text = pattern.sub(" ", text)

    # Drop the "Academic" qualifier wherever it appears as a standalone word.
    text = re.sub(r"(?i)\bacademic\b", " ", text)

    text = re.sub(r"\s{2,}", " ", text).strip()
    text = _SEPARATOR_TAIL.sub("", text)
    text = _SEPARATOR_HEAD.sub("", text)
    text = re.sub(r"\s{2,}", " ", text).strip()

    # A title with no letters left (e.g. the model returned just "7.0") is
    # not a title at all.
    if not re.search(r"[A-Za-z]", text):
        return DEFAULT_TITLE

    return text
