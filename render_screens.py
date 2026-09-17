"""
Stage 3: Screen Rendering

Renders IELTS test question papers, title cards, instructions, and answer key
as responsive 1920x1080 HTML pages, and captures screenshots with Playwright.
"""

import base64
import html
import json
import re
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import fonts
from generate_audio import get_part_question_ranges
from generate_visuals import generate_visuals, load_video_config
from text_utils import clean_title


# ---------------------------------------------------------------------------
# HTML / CSS Builder
# ---------------------------------------------------------------------------

BASE_CSS = """
* {
    box-sizing: border-box;
    margin: 0;
    padding: 0;
}

body {
    width: 1920px;
    height: 1080px;
    overflow: hidden;
    background-color: #F1F5F9;
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif, 'Apple Color Emoji', 'Segoe UI Emoji', 'Noto Color Emoji';
    color: #0F172A;
    display: flex;
    flex-direction: column;
    justify-content: flex-start;
    align-items: center;
    padding-top: 84px; /* Space reserved for the top HUD bar */
    padding-bottom: 24px;
    padding-left: 48px;
    padding-right: 48px;
}

.paper-container {
    width: 1824px;
    height: 970px;
    background-color: #FFFFFF;
    border-radius: 12px;
    border: 1px solid #CBD5E1;
    box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.07), 0 4px 6px -2px rgba(0, 0, 0, 0.04);
    padding: 32px 44px;
    display: flex;
    flex-direction: column;
    overflow: hidden;
}

/* Header section */
.part-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    border-bottom: 2px solid #0F172A;
    padding-bottom: 12px;
    margin-bottom: 16px;
}

.part-title {
    font-size: 26px;
    font-weight: 800;
    letter-spacing: 0.5px;
    color: #0F172A;
    text-transform: uppercase;
}

.questions-badge {
    background-color: #1E40AF;
    color: #FFFFFF;
    font-size: 18px;
    font-weight: 700;
    padding: 6px 16px;
    border-radius: 6px;
    letter-spacing: 0.5px;
}

.situation-box {
    font-style: italic;
    font-size: 17px;
    color: #475569;
    margin-bottom: 14px;
    line-height: 1.4;
    padding-left: 12px;
    border-left: 3px solid #94A3B8;
}

.content-body {
    flex: 1;
    display: flex;
    flex-direction: column;
    gap: 16px;
    overflow: hidden;
}

/* Two-column layout if image exists */
.split-layout {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 32px;
    height: 100%;
    align-items: start;
}

.visual-col {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    background: #F8FAFC;
    border: 1px solid #E2E8F0;
    border-radius: 8px;
    padding: 12px;
    max-height: 760px;
}

.visual-img {
    max-width: 100%;
    max-height: 720px;
    object-fit: contain;
    border-radius: 4px;
}

/* Question Group styles */
.group-card {
    background: #FFFFFF;
    border: 1px solid #E2E8F0;
    border-radius: 8px;
    padding: 16px 20px;
    margin-bottom: 12px;
}

.group-header {
    font-size: 19px;
    font-weight: 700;
    color: #1E3A8A;
    margin-bottom: 6px;
}

.instruction {
    font-size: 16px;
    font-style: italic;
    color: #334155;
    margin-bottom: 12px;
}

.heading-title {
    font-size: 18px;
    font-weight: 700;
    text-transform: uppercase;
    color: #0F172A;
    margin-top: 8px;
    margin-bottom: 10px;
    border-bottom: 1px dashed #CBD5E1;
    padding-bottom: 4px;
}

/* Blank placeholders */
.blank-field {
    display: inline-flex;
    align-items: center;
    margin: 0 4px;
    font-weight: 700;
}

.q-badge {
    display: inline-block;
    background: #0F172A;
    color: #FFFFFF;
    font-size: 14px;
    font-weight: 700;
    padding: 2px 7px;
    border-radius: 4px;
    margin-right: 6px;
}

.blank-line {
    border-bottom: 2px solid #0F172A;
    display: inline-block;
    min-width: 140px;
    height: 18px;
    vertical-align: middle;
}

/* Options Box */
.options-box {
    background: #F8FAFC;
    border: 1.5px solid #CBD5E1;
    border-radius: 6px;
    padding: 12px 16px;
    margin: 10px 0;
}

.options-box-title {
    font-size: 14px;
    font-weight: 700;
    text-transform: uppercase;
    color: #475569;
    margin-bottom: 6px;
}

.options-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
    gap: 8px 16px;
}

.opt-pill {
    display: flex;
    align-items: flex-start;
    font-size: 15px;
    color: #1E293B;
}

.opt-letter {
    font-weight: 800;
    color: #1E40AF;
    margin-right: 8px;
    min-width: 18px;
}

/* Questions list */
.question-item {
    font-size: 16px;
    line-height: 1.5;
    margin: 8px 0;
    color: #1E293B;
}

.mcq-item {
    margin-bottom: 12px;
}

.mcq-question-text {
    font-weight: 600;
    font-size: 16px;
    color: #0F172A;
    margin-bottom: 4px;
}

.mcq-options-list {
    margin-left: 24px;
    display: flex;
    flex-direction: column;
    gap: 4px;
}

/* Layout text / formatted forms */
.formatted-layout {
    font-size: 16px;
    line-height: 1.8;
    color: #1E293B;
    background: #FAFAFA;
    padding: 14px 18px;
    border-radius: 6px;
    border: 1px solid #E5E7EB;
}

/* Flowchart completion */
.flowchart-container {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 0;
    padding: 12px 0;
}

.flowchart-step {
    width: 92%;
    background: #FAFAFA;
    border: 1.5px solid #CBD5E1;
    border-radius: 8px;
    padding: 12px 18px;
    font-size: 16px;
    line-height: 1.6;
    color: #1E293B;
    text-align: left;
}

.flowchart-arrow {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    height: 32px;
    color: #475569;
    font-size: 0;
    line-height: 0;
}

.flowchart-arrow svg {
    width: 22px;
    height: 32px;
}

/* Title Card */
.title-card {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    text-align: center;
    height: 100%;
    padding: 40px;
}

.brand-badge {
    background: #1E40AF;
    color: white;
    font-size: 20px;
    font-weight: 800;
    letter-spacing: 2px;
    padding: 8px 24px;
    border-radius: 30px;
    margin-bottom: 24px;
    text-transform: uppercase;
}

.main-test-title {
    font-size: 46px;
    font-weight: 900;
    color: #0F172A;
    line-height: 1.2;
    margin-bottom: 24px;
    max-width: 1200px;
}

.test-meta-pills {
    display: flex;
    gap: 16px;
    margin-bottom: 36px;
}

.meta-pill {
    background: #F1F5F9;
    border: 1px solid #CBD5E1;
    color: #334155;
    font-size: 18px;
    font-weight: 600;
    padding: 8px 20px;
    border-radius: 8px;
}

.instructions-card {
    background: #F8FAFC;
    border: 2px solid #E2E8F0;
    border-radius: 12px;
    padding: 24px 36px;
    max-width: 1000px;
    text-align: left;
}

.instructions-card h3 {
    font-size: 20px;
    font-weight: 800;
    color: #1E3A8A;
    margin-bottom: 12px;
    text-transform: uppercase;
}

.instructions-card ul {
    margin-left: 20px;
    font-size: 16px;
    line-height: 1.6;
    color: #334155;
}

/* Answer Key Layout */
.ak-container {
    height: 100%;
    display: flex;
    flex-direction: column;
}

.ak-title {
    font-size: 28px;
    font-weight: 800;
    color: #0F172A;
    text-align: center;
    margin-bottom: 16px;
}

.ak-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 24px;
    flex: 1;
    overflow: hidden;
}

.ak-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 15px;
}

.ak-table th {
    background: #1E293B;
    color: #FFFFFF;
    font-weight: 700;
    text-align: left;
    padding: 8px 12px;
}

.ak-table td {
    padding: 6px 12px;
    border-bottom: 1px solid #E2E8F0;
    color: #1E293B;
}

.ak-table tr:nth-child(even) td {
    background: #F8FAFC;
}

.ak-num {
    font-weight: 800;
    color: #1E40AF;
    width: 38px;
}

.ak-ans {
    font-weight: 700;
    color: #0F172A;
}

.ak-alt {
    color: #64748B;
    font-size: 13px;
}

.ak-type {
    color: #475569;
    font-size: 13px;
    text-transform: capitalize;
}
"""


def image_to_base64(img_path: Path) -> str:
    """Convert an image file to a base64 data URI."""
    if not img_path.exists():
        return ""
    data = base64.b64encode(img_path.read_bytes()).decode("utf-8")
    ext = img_path.suffix.lstrip(".").lower()
    if ext == "jpg":
        ext = "jpeg"
    return f"data:image/{ext};base64,{data}"


def format_blank_layout(layout_str: str, question_numbers: list[int]) -> str:
    """Format {N} placeholders in group layout to HTML blank elements."""
    wanted = set(question_numbers)

    def replacer(match):
        num = int(match.group(1))
        if num in wanted:
            return f'<span class="blank-field"><span class="q-badge">{num}</span><span class="blank-line"></span></span>'
        return match.group(0)

    escaped = html.escape(str(layout_str or ""))
    formatted = re.sub(r"\{\s*(\d+)\s*\}", replacer, escaped)

    # If it is a markdown table
    lines = formatted.split("\n")
    if any("|" in line for line in lines):
        # Convert simple markdown table to HTML
        rows = [l.strip() for l in lines if l.strip() and not re.match(r"^\|?\s*:?-+:?\s*\|?", l)]
        if rows:
            html_rows = []
            for r in rows:
                cols = [c.strip() for c in r.strip("|").split("|")]
                cells = "".join(f"<td>{c}</td>" for c in cols)
                html_rows.append(f"<tr>{cells}</tr>")
            return f'<table class="layout-table">{"".join(html_rows)}</table>'

    return "<br>".join(lines)


# SVG downward arrow used between flowchart steps
_FLOWCHART_ARROW_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 22 32">'
    '<line x1="11" y1="0" x2="11" y2="24" stroke="#475569" stroke-width="2"/>'
    '<polygon points="4,22 11,32 18,22" fill="#475569"/>'
    '</svg>'
)

# Matches ASCII (| / v) and Unicode (│ / ▼) arrow delimiters between steps
_FLOWCHART_ARROW_RE = re.compile(
    r"\n\s*[|│]\s*\n\s*[v▼]\s*\n",
    re.UNICODE,
)


def format_flowchart_layout(layout_str: str, question_numbers: list[int]) -> str:
    """Format a flow_chart_completion layout into styled step boxes with arrows."""
    wanted = set(question_numbers)

    def replacer(match):
        num = int(match.group(1))
        if num in wanted:
            return f'<span class="blank-field"><span class="q-badge">{num}</span><span class="blank-line"></span></span>'
        return match.group(0)

    raw = str(layout_str or "")

    # Split on arrow delimiters: "|" + "v" (or Unicode equivalents)
    steps = _FLOWCHART_ARROW_RE.split(raw)

    # Fallback: if no arrows found, try double-newline (Step N: style)
    if len(steps) <= 1:
        steps = re.split(r"\n{2,}", raw)

    # If still a single chunk, fall back to normal layout rendering
    if len(steps) <= 1:
        return format_blank_layout(layout_str, question_numbers)

    arrow_html = f'<div class="flowchart-arrow">{_FLOWCHART_ARROW_SVG}</div>'
    parts = []
    for i, step in enumerate(steps):
        step = step.strip()
        if not step:
            continue
        escaped = html.escape(step)
        formatted = re.sub(r"\{\s*(\d+)\s*\}", replacer, escaped)
        parts.append(f'<div class="flowchart-step">{formatted}</div>')
        if i < len(steps) - 1:
            parts.append(arrow_html)

    return f'<div class="flowchart-container">{"".join(parts)}</div>'

def render_group_html(group: dict, questions: list[dict], visuals_map: dict[str, Path]) -> str:
    """Render a single question group into HTML."""
    gid = str(group.get("id") or "")
    members = [q for q in questions if str(q.get("group") or "") == gid]
    if not members and group.get("from") is not None and group.get("to") is not None:
        members = [
            q for q in questions
            if int(group.get("from", 0)) <= int(q.get("number", 0)) <= int(group.get("to", 0))
        ]
    members = sorted(members, key=lambda q: q.get("number") or 0)
    numbers = [int(q.get("number")) for q in members if q.get("number") is not None]

    out = ['<div class="group-card">']

    # Group Header (e.g. Questions 1-6)
    if numbers:
        if len(numbers) > 1:
            q_range_label = f"Questions {min(numbers)}–{max(numbers)}"
        else:
            q_range_label = f"Question {numbers[0]}"
        out.append(f'<div class="group-header">{html.escape(q_range_label)}</div>')

    # Instructions
    instruction = str(group.get("instruction", "")).strip()
    if instruction:
        out.append(f'<div class="instruction">{html.escape(instruction)}</div>')

    # Heading
    heading = str(group.get("heading", "")).strip()
    if heading:
        out.append(f'<div class="heading-title">{html.escape(heading)}</div>')

    # Layout text / blanks
    layout = str(group.get("layout", "")).strip()
    if layout:
        gtype = str(group.get("type", ""))
        if gtype == "flow_chart_completion":
            layout_html = format_flowchart_layout(layout, numbers)
            out.append(layout_html)
        else:
            layout_html = format_blank_layout(layout, numbers)
            out.append(f'<div class="formatted-layout">{layout_html}</div>')

    # Shared Options Box (Matching / Labelling / Boxed options)
    options = group.get("options", [])
    if options:
        out.append('<div class="options-box">')
        out.append('<div class="options-box-title">Options</div>')
        out.append('<div class="options-grid">')
        for opt in options:
            let = html.escape(str(opt.get("letter", "?")))
            txt = html.escape(str(opt.get("text", "")))
            out.append(f'<div class="opt-pill"><span class="opt-letter">{let}</span> <span class="opt-text">{txt}</span></div>')
        out.append('</div></div>')

    # Individual Questions (MCQs or standalone questions)
    for q in members:
        num = q.get("number")
        text = str(q.get("text", "")).strip()
        q_options = q.get("options", [])

        if not text and layout:
            continue

        if q_options:
            # MCQ style
            out.append('<div class="mcq-item">')
            out.append(f'<div class="mcq-question-text"><span class="q-badge">{num}</span> {html.escape(text)}</div>')
            out.append('<div class="mcq-options-list">')
            for opt in q_options:
                let = html.escape(str(opt.get("letter", "?")))
                txt = html.escape(str(opt.get("text", "")))
                out.append(f'<div class="opt-pill"><span class="opt-letter">{let}</span> <span class="opt-text">{txt}</span></div>')
            out.append('</div></div>')
        elif text:
            # Standalone sentence / question with blank (only if not already embedded in layout)
            if not (layout and re.search(rf"\{{\s*{num}\s*\}}", layout)):
                out.append(f'<div class="question-item"><span class="q-badge">{num}</span> {html.escape(text)} <span class="blank-line"></span></div>')

    out.append('</div>')
    return "\n".join(out)


def fit_content(page, min_zoom: float = 0.55, passes: int = 4) -> float:
    """Shrink .content-body until it fits inside the fixed-height paper container.

    .paper-container is overflow:hidden with no fit logic, so a question-heavy
    part (two groups plus MCQ options) silently clips the last questions. That
    was tolerable when the full-part page only showed during the 30s checking
    window; now that it is the part's only screen, a clipped page means
    unanswerable questions.

    Uses CSS zoom rather than transform:scale — zoom re-runs layout so text
    rewraps and the measurement converges, whereas a transform would just scale
    a still-overflowing box. Iterates because rewrapping changes the height
    needed. Returns the applied zoom.
    """
    zoom = 1.0
    for _ in range(passes):
        need, avail = page.evaluate(
            "() => { const b = document.querySelector('.content-body');"
            "  return b ? [b.scrollHeight, b.clientHeight] : [0, 1]; }")
        if not need or need <= avail:
            break
        zoom = max(min_zoom, zoom * (avail / need) * 0.98)
        page.evaluate(
            "z => { document.querySelector('.content-body').style.zoom = z; }",
            zoom)
        if zoom <= min_zoom:
            break
    return zoom


def build_page_html(content_html: str, part_num: int | None = None,
                    q_from: int | None = None, q_to: int | None = None,
                    situation: str = "") -> str:
    """Wrap content in full 1920x1080 HTML page."""
    header_html = ""
    if part_num is not None:
        range_str = f"Questions {q_from}–{q_to}" if q_from and q_to else f"Part {part_num}"
        situation_html = f'<div class="situation-box">{html.escape(situation)}</div>' if situation else ""
        header_html = f"""
        <div class="part-header">
            <div class="part-title">IELTS Listening &mdash; Part {part_num}</div>
            <div class="questions-badge">{range_str}</div>
        </div>
        {situation_html}
        """

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <style>{fonts.css_font_face()}{BASE_CSS}</style>
</head>
<body>
    <div class="paper-container">
        {header_html}
        <div class="content-body">
            {content_html}
        </div>
    </div>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Screen Renderers
# ---------------------------------------------------------------------------

def render_title_screen(test_data: dict) -> str:
    meta = test_data.get("metadata", {})
    # The target band is an internal generation parameter and is deliberately
    # not shown to viewers -- including inside the model-authored title.
    title = clean_title(meta.get("title"))
    total_q = meta.get("total_questions", 40)

    content = f"""
    <div class="title-card">
        <div class="brand-badge">Official Format &bull; Academic / General</div>
        <h1 class="main-test-title">{html.escape(title)}</h1>
        
        <div class="test-meta-pills">
            <div class="meta-pill">⏱️ Total Duration: ~30 Minutes</div>
            <div class="meta-pill">📝 {total_q} Questions (4 Parts)</div>
        </div>

        <div class="instructions-card">
            <h3>Test Instructions</h3>
            <ul>
                <li>You will hear four different recordings and you will have to answer questions on what you hear.</li>
                <li>You will hear each recording <strong>once only</strong>.</li>
                <li>There will be time for you to read the instructions and questions before each section.</li>
                <li>Write all your answers on the question paper as you listen.</li>
                <li>At the end of the test, an answer key review will be provided.</li>
            </ul>
        </div>
    </div>
    """
    return build_page_html(content)


def render_answer_key_screen(test_data: dict) -> str:
    parts = test_data.get("parts", [])
    rows = []
    for part in parts:
        for ans in part.get("answers", []):
            num = ans.get("number")
            val = str(ans.get("answer", ""))
            alts = ", ".join(str(a) for a in ans.get("alternatives", [])) or "-"
            qtype = str(ans.get("type", "")).replace("_", " ")
            rows.append((num, val, alts, qtype))

    rows = sorted(rows, key=lambda r: r[0] or 0)
    col1 = rows[:20]
    col2 = rows[20:]

    def build_table(items):
        t_rows = []
        for n, v, a, t in items:
            t_rows.append(
                f'<tr><td class="ak-num">{n}</td><td class="ak-ans">{html.escape(v)}</td><td class="ak-alt">{html.escape(a)}</td></tr>'
            )
        return f"""
        <table class="ak-table">
            <thead>
                <tr>
                    <th>#</th>
                    <th>Answer</th>
                    <th>Accepted Alternatives</th>
                </tr>
            </thead>
            <tbody>
                {"".join(t_rows)}
            </tbody>
        </table>
        """

    content = f"""
    <div class="ak-container">
        <div class="ak-title">Answer Key</div>
        <div class="ak-grid">
            <div class="ak-col">{build_table(col1)}</div>
            <div class="ak-col">{build_table(col2)}</div>
        </div>
    </div>
    """
    return build_page_html(content)


def render_end_screen(test_data: dict) -> str:
    content = f"""
    <div class="title-card">
        <div class="brand-badge" style="background: #10B981;">Test Completed</div>
        <h1 class="main-test-title">That is the end of the Listening test.</h1>
        
        <div class="instructions-card" style="text-align: center; margin-top: 20px;">
            <h3>Check Your Results</h3>
            <p style="font-size: 18px; line-height: 1.8; color: #334155;">
                Calculate your score out of 40 marks to estimate your IELTS Band Score.<br>
                Review tricky spellings, singular/plural forms, and word limits in the answer key.
            </p>
        </div>
    </div>
    """
    return build_page_html(content)


# ---------------------------------------------------------------------------
# Main Orchestration & Screen Capture
# ---------------------------------------------------------------------------

def render_screens(test_dir: str | Path, force_visuals: bool = False) -> dict:
    """Generate all video screens and screenshot them via Playwright."""
    test_dir = Path(test_dir)
    test_json = test_dir / "test.json"
    if not test_json.exists():
        raise FileNotFoundError(f"Missing {test_json}")

    test_data = json.loads(test_json.read_text(encoding="utf-8"))

    # Step 1: Ensure visuals exist
    visuals_map = generate_visuals(test_dir, force=force_visuals)

    screens_dir = test_dir / "video" / "screens"
    screens_dir.mkdir(parents=True, exist_ok=True)

    screens_manifest = []

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1920, "height": 1080},
                                device_scale_factor=1.0)

        def capture(screen_id: str, html_str: str, part_num=None,
                    q_from=None, q_to=None, screen_type="questions"):
            out_file = screens_dir / f"{screen_id}.png"
            page.set_content(html_str)
            page.evaluate("document.fonts.ready")  # Inter must be live before capture
            page.wait_for_timeout(100)  # Brief settle for layout
            zoom = fit_content(page)
            page.screenshot(path=str(out_file))
            fit_note = f" [fit {zoom:.2f}]" if zoom < 0.999 else ""
            print(f"  -> Captured screen: {out_file.name} [{screen_type}] "
                  f"(Q{q_from}–Q{q_to}){fit_note}")
            screens_manifest.append({
                "id": screen_id,
                "type": screen_type,
                "part": part_num,
                "q_from": q_from,
                "q_to": q_to,
                "file": out_file.name,
                "path": str(out_file),
            })

        # 1. Title Screen
        title_html = render_title_screen(test_data)
        capture("title_card", title_html, screen_type="title_card")

        # 2. Per-part Question Screens
        parts = test_data.get("parts", [])
        for part_no, part in enumerate(parts, start=1):
            q_from, q_mid, q_mid_next, q_to = get_part_question_ranges(part_no, part)
            questions = part.get("questions", [])
            groups = part.get("question_groups", [])
            situation = str(part.get("situation", "")).strip()

            # One screen per part: every question in the part stays visible for
            # the part's full duration, the way a candidate holds the booklet.
            all_groups_html = "".join(render_group_html(g, questions, visuals_map) for g in groups)
            # If visual exists in any group, split layout
            any_vis = None
            for g in groups:
                vid = str(g.get("visual_id") or "")
                if vid and vid in visuals_map:
                    any_vis = visuals_map[vid]
                    break

            if any_vis and any_vis.exists():
                b64 = image_to_base64(any_vis)
                full_content = f"""
                <div class="split-layout">
                    <div class="visual-col"><img src="{b64}" class="visual-img" /></div>
                    <div class="questions-col">{all_groups_html}</div>
                </div>
                """
            else:
                full_content = all_groups_html

            p_all_html = build_page_html(full_content, part_no, q_from, q_to, situation)
            capture(f"part_{part_no}_all", p_all_html, part_num=part_no,
                    q_from=q_from, q_to=q_to, screen_type="questions")

        # 3. Answer Key Screen
        ak_html = render_answer_key_screen(test_data)
        capture("answer_key", ak_html, screen_type="answer_key")

        # 4. End Screen
        end_html = render_end_screen(test_data)
        capture("end_card", end_html, screen_type="end_card")

        browser.close()

    manifest_path = test_dir / "video" / "screens.json"
    manifest_data = {"screens": screens_manifest}
    manifest_path.write_text(json.dumps(manifest_data, indent=2), encoding="utf-8")
    print(f"\nSaved screens manifest to: {manifest_path} ({len(screens_manifest)} screens)")

    return manifest_data


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python render_screens.py <test_directory>")
        sys.exit(1)

    target_dir = sys.argv[1]
    render_screens(target_dir)
