# -*- coding: utf-8 -*-
"""
Lightweight Markdown-to-HTML renderer for Maya AI Agent.
No external dependencies — uses only ``re`` from the standard library.

Supported syntax:
  - Fenced code blocks (```lang ... ```)
  - Inline code (`code`)
  - Bold (**text** or __text__)
  - Italic (*text* or _text_)
  - Headings (# … ####)
  - Unordered lists (- item / * item)
  - Ordered lists (1. item)
  - Blockquotes (> text)
  - Horizontal rules (--- / ***)
"""

import re


# ── Code-block colour tokens (VS Code dark theme inspired) ────────────
_CODE_BG = "#1a1a1a"
_CODE_BORDER = "#333"
_CODE_FG = "#ce9178"
_INLINE_CODE_BG = "#2d2d2d"
_INLINE_CODE_FG = "#ce9178"


# ── Phase 1: protect fenced code blocks from further processing ───────

_FENCED_RE = re.compile(
    r"^```(\w*)\s*\n(.*?)^```\s*$",
    re.MULTILINE | re.DOTALL,
)


def _render_fenced(match):
    lang = match.group(1) or ""
    code = match.group(2).rstrip("\n")
    # Escape HTML inside code
    code = (
        code.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
    )
    lang_label = (
        '<span style="color:#858585;font-size:11px;">{}</span><br/>'.format(lang)
        if lang else ""
    )
    return (
        '<div style="background:{bg};border:1px solid {bd};border-radius:4px;'
        'padding:8px 10px;margin:6px 0;font-family:Consolas,monospace;">'
        '{label}'
        '<pre style="margin:0;color:{fg};white-space:pre-wrap;'
        'word-break:break-all;">{code}</pre>'
        '</div>'
    ).format(bg=_CODE_BG, bd=_CODE_BORDER, fg=_CODE_FG,
             label=lang_label, code=code)


# ── Phase 2: inline transformations ───────────────────────────────────

def _inline(text):
    """Apply inline Markdown formatting to *text* (which is already
    HTML-escaped except for our own tags)."""

    # Inline code  `code`
    text = re.sub(
        r"`([^`\n]+?)`",
        r'<span style="background:{bg};color:{fg};padding:1px 4px;'
        r'border-radius:3px;font-family:Consolas,monospace;">\1</span>'.format(
            bg=_INLINE_CODE_BG, fg=_INLINE_CODE_FG),
        text,
    )

    # Bold  **text** or __text__
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"__(.+?)__", r"<b>\1</b>", text)

    # Italic  *text* or _text_  (not inside words for underscore)
    text = re.sub(r"(?<!\w)\*(?!\*)(.+?)(?<!\*)\*(?!\w)", r"<i>\1</i>", text)
    text = re.sub(r"(?<!\w)_(?!_)(.+?)(?<!_)_(?!\w)", r"<i>\1</i>", text)

    return text


# ── Phase 3: block-level processing (line by line) ────────────────────

_HEADING_RE = re.compile(r"^(#{1,4})\s+(.+)$")
_UL_RE = re.compile(r"^[\-\*]\s+(.+)$")
_OL_RE = re.compile(r"^\d+\.\s+(.+)$")
_QUOTE_RE = re.compile(r"^>\s?(.*)$")
_HR_RE = re.compile(r"^(\-{3,}|\*{3,})\s*$")


def _process_blocks(text):
    """Convert block-level Markdown in *text* to HTML.

    *text* should already have fenced code blocks extracted (replaced
    with placeholders).
    """
    lines = text.split("\n")
    out = []
    in_ul = False
    in_ol = False
    in_quote = False

    def _close_lists():
        nonlocal in_ul, in_ol, in_quote
        if in_ul:
            out.append("</ul>")
            in_ul = False
        if in_ol:
            out.append("</ol>")
            in_ol = False
        if in_quote:
            out.append("</blockquote>")
            in_quote = False

    for line in lines:
        stripped = line.strip()

        # Horizontal rule
        if _HR_RE.match(stripped):
            _close_lists()
            out.append('<hr style="border:none;border-top:1px solid #444;margin:8px 0;"/>')
            continue

        # Heading
        m = _HEADING_RE.match(stripped)
        if m:
            _close_lists()
            level = len(m.group(1))
            sizes = {1: "1.4em", 2: "1.2em", 3: "1.05em", 4: "1em"}
            sz = sizes.get(level, "1em")
            out.append(
                '<div style="font-size:{sz};font-weight:bold;margin:8px 0 4px 0;'
                'color:#e0e0e0;">{t}</div>'.format(
                    sz=sz, t=_inline(stripped[level + 1:].strip()))
            )
            continue

        # Blockquote
        m = _QUOTE_RE.match(stripped)
        if m:
            if not in_quote:
                _close_lists()
                out.append(
                    '<blockquote style="border-left:3px solid #555;'
                    'padding-left:10px;margin:4px 0;color:#aaa;">'
                )
                in_quote = True
            out.append(_inline(m.group(1)) + "<br/>")
            continue
        elif in_quote:
            out.append("</blockquote>")
            in_quote = False

        # Unordered list
        m = _UL_RE.match(stripped)
        if m:
            if in_ol:
                out.append("</ol>")
                in_ol = False
            if not in_ul:
                out.append('<ul style="margin:4px 0 4px 18px;padding:0;">')
                in_ul = True
            out.append("<li>{}</li>".format(_inline(m.group(1))))
            continue
        elif in_ul:
            out.append("</ul>")
            in_ul = False

        # Ordered list
        m = _OL_RE.match(stripped)
        if m:
            if in_ul:
                out.append("</ul>")
                in_ul = False
            if not in_ol:
                out.append('<ol style="margin:4px 0 4px 18px;padding:0;">')
                in_ol = True
            out.append("<li>{}</li>".format(_inline(m.group(1))))
            continue
        elif in_ol:
            out.append("</ol>")
            in_ol = False

        # Normal line
        if stripped == "":
            _close_lists()
            out.append("<br/>")
        else:
            out.append(_inline(stripped) + "<br/>")

    _close_lists()
    return "\n".join(out)


# ── Public API ────────────────────────────────────────────────────────

def render_markdown(text):
    """Convert a Markdown string to HTML suitable for QTextEdit display.

    Returns an HTML fragment (no <html>/<body> wrapper).
    """
    if not text:
        return ""

    # Step 1: extract fenced code blocks and replace with placeholders
    placeholders = {}
    counter = [0]

    def _placeholder(m):
        key = "\x00CODEBLOCK_{}\x00".format(counter[0])
        counter[0] += 1
        placeholders[key] = _render_fenced(m)
        return key

    text = _FENCED_RE.sub(_placeholder, text)

    # Step 2: HTML-escape the remaining text
    text = (
        text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
    )

    # Step 3: block-level processing
    html = _process_blocks(text)

    # Step 4: re-insert code blocks
    for key, block_html in placeholders.items():
        html = html.replace(
            key.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"),
            block_html,
        )

    # Clean up excessive <br/> runs
    html = re.sub(r"(<br/>\s*){3,}", "<br/><br/>", html)

    return html
