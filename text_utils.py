"""Small text helpers shared by the renderers and the YouTube uploader.

Kept separate from render_screens.py so youtube_upload.py can import it without
pulling in Playwright.
"""

from __future__ import annotations

import re

DEFAULT_TITLE = "IELTS Academic Listening Practice Test"

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
    """Strip target-band artifacts from a test title.

    The band is an internal generation parameter and must never reach a viewer,
    but the model writes it into the title anyway (tests/test_009-012 all say
    "IELTS Listening Practice Test - Academic 7.0"). Sanitizing here means
    already-generated tests render clean without regeneration.
    """
    text = (title or "").strip()
    if not text:
        return DEFAULT_TITLE

    for pattern in _BAND_PATTERNS:
        text = pattern.sub(" ", text)

    text = re.sub(r"\s{2,}", " ", text).strip()
    text = _SEPARATOR_TAIL.sub("", text)
    text = _SEPARATOR_HEAD.sub("", text)
    text = re.sub(r"\s{2,}", " ", text).strip()

    # A title with no letters left (e.g. the model returned just "7.0") is
    # not a title at all.
    if not re.search(r"[A-Za-z]", text):
        return DEFAULT_TITLE

    return text
