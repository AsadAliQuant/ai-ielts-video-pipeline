"""Bundled font resolution shared by every renderer in the pipeline.

Fonts live in assets/fonts/ and are committed to the repo, so a Windows dev box
and an ubuntu-latest CI runner rasterize identical typography. Nothing here
falls back to a system font: an earlier version asked Pillow for "arialbd.ttf"
by bare filename, which resolves on Windows and silently degraded to a ~10px
bitmap font on Linux, shipping broken HUD bars with no log line.
"""

from __future__ import annotations

import base64
from pathlib import Path

from PIL import ImageFont

FONT_DIR = Path(__file__).parent / "assets" / "fonts"

# Static TTFs for Pillow (Pillow cannot read woff2).
_TTF = {
    "regular": "Inter-Regular.ttf",
    "semibold": "Inter-SemiBold.ttf",
    "bold": "Inter-Bold.ttf",
}

# Variable woff2 for Chromium: one file covers weight 100-900, so the CSS
# weights 600/700/800/900 stay visually distinct (Liberation/DejaVu ship only
# 400 + 700 and collapse all of them into a single Bold face).
_WOFF2 = {
    "normal": "inter-latin-wght-normal.woff2",
    "italic": "inter-latin-wght-italic.woff2",
}

CSS_FONT_STACK = (
    "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, "
    "'Helvetica Neue', Arial, sans-serif, 'Apple Color Emoji', "
    "'Segoe UI Emoji', 'Noto Color Emoji'"
)

_css_cache: str | None = None


def font_path(weight: str) -> Path:
    try:
        name = _TTF[weight]
    except KeyError:
        raise ValueError(
            f"Unknown font weight {weight!r}; expected one of {sorted(_TTF)}"
        ) from None
    path = FONT_DIR / name
    if not path.exists():
        raise FileNotFoundError(
            f"Bundled font missing: {path}\n"
            "assets/fonts/ must be checked out with the repo -- see fonts.py."
        )
    return path


def pillow_font(weight: str, size: int) -> ImageFont.FreeTypeFont:
    """Load a bundled TrueType face at an exact pixel size.

    Raises rather than degrading; a missing font is a build error, not
    something to paper over with load_default().
    """
    return ImageFont.truetype(str(font_path(weight)), size)


def css_font_face() -> str:
    """@font-face blocks with the woff2 files inlined as base64 data: URIs.

    render_screens.py drives Chromium via page.set_content(), which leaves the
    document with no base URL, so relative url() references cannot resolve --
    the data: URI is what makes the bundled font reachable at all.
    """
    global _css_cache
    if _css_cache is not None:
        return _css_cache

    blocks = []
    for style, name in _WOFF2.items():
        path = FONT_DIR / name
        if not path.exists():
            raise FileNotFoundError(f"Bundled webfont missing: {path}")
        b64 = base64.b64encode(path.read_bytes()).decode("ascii")
        blocks.append(
            "@font-face {\n"
            "    font-family: 'Inter';\n"
            f"    font-style: {style};\n"
            "    font-weight: 100 900;\n"
            "    font-display: block;\n"
            f"    src: url(data:font/woff2;base64,{b64}) format('woff2');\n"
            "}"
        )

    _css_cache = "\n".join(blocks) + "\n"
    return _css_cache


def selftest() -> None:
    """Fail loudly if the bundled fonts are missing or not really loading.

    Run in CI before the render stage so a font regression stops the build
    instead of shipping a video with a 10px bitmap HUD.
    """
    from PIL import Image, ImageDraw

    draw = ImageDraw.Draw(Image.new("RGB", (10, 10)))

    for weight in _TTF:
        font = pillow_font(weight, 22)
        assert isinstance(font, ImageFont.FreeTypeFont), (
            f"{weight}: got {type(font).__name__}, not FreeTypeFont "
            "(this is the silent load_default() regression)"
        )
        assert font.size == 22, f"{weight}: size {font.size} != 22"
        assert str(FONT_DIR) in str(font.path), (
            f"{weight}: loaded {font.path}, not the bundled font"
        )

    # En-dash is the glyph the default bitmap font lacks, and the tiny widths
    # it reports are what collapsed the HUD badge boxes.
    width = draw.textlength("Questions 31\u201340", font=pillow_font("bold", 22))
    assert width > 150, f"en-dash label measured {width:.0f}px, expected >150px"

    css = css_font_face()
    assert css.count("@font-face") == len(_WOFF2), "missing an @font-face block"
    assert len(css) > 100_000, "webfont data: URIs look empty"

    print(f"fonts OK: {len(_TTF)} TTF weights + {len(_WOFF2)} woff2 from {FONT_DIR}")


if __name__ == "__main__":
    selftest()
