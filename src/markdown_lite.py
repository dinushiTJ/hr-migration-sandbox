"""
A small Markdown to HTML renderer, covering exactly what the README uses.

A dependency would be the obvious answer, but the project's promise is that it
runs on the standard library alone, and the published page has to be one
self-contained file. So this handles headings, tables, fenced code, lists,
emphasis, inline code and links, and nothing else.
"""
import html
import re

_INLINE = (
    (re.compile(r"`([^`]+)`"), lambda m: f"<code>{html.escape(m.group(1))}</code>"),
    (re.compile(r"\*\*([^*]+)\*\*"), lambda m: f"<strong>{m.group(1)}</strong>"),
    (re.compile(r"(?<!\w)\*([^*\n]+)\*(?!\w)"), lambda m: f"<em>{m.group(1)}</em>"),
    (re.compile(r"\[([^\]]+)\]\(([^)]+)\)"),
     lambda m: f'<a href="{_safe_href(m.group(2))}">{m.group(1)}</a>'),
)


def _safe_href(value):
    """Allow only web/document links; never emit a scriptable URL scheme."""
    href = value.strip()
    if re.match(r"(?i)^(?:https?|mailto):", href):
        return html.escape(href, quote=True)
    if href.startswith(("/", "./", "../", "#")) or ":" not in href:
        return html.escape(href, quote=True)
    return "#"


def _inline(text):
    """Escape first, then apply inline markup, so code spans stay literal."""
    out, i = [], 0
    for m in re.finditer(r"`[^`]+`", text):
        out.append(html.escape(text[i:m.start()]))
        out.append(m.group(0))
        i = m.end()
    out.append(html.escape(text[i:]))
    text = "".join(out)
    for pattern, repl in _INLINE:
        text = pattern.sub(repl, text)
    return text


def _row(line):
    cells = [c.strip() for c in line.strip().strip("|").split("|")]
    return cells


def render(md):
    lines = md.split("\n")
    out, i = [], 0
    while i < len(lines):
        line = lines[i]

        if line.startswith("```"):                      # fenced code
            i += 1
            block = []
            while i < len(lines) and not lines[i].startswith("```"):
                block.append(lines[i])
                i += 1
            i += 1
            out.append("<pre><code>" + html.escape("\n".join(block)) + "</code></pre>")
            continue

        if re.fullmatch(r"-{3,}", line.strip()):          # horizontal rule
            out.append("<hr>")
            i += 1
            continue

        if re.fullmatch(r"</?details>|<summary>.*</summary>", line.strip()):  # collapsible section
            out.append(line.strip())
            i += 1
            continue

        m = re.match(r"(#{1,4})\s+(.*)", line)            # heading
        if m:
            lvl = len(m.group(1))
            out.append(f"<h{lvl}>{_inline(m.group(2))}</h{lvl}>")
            i += 1
            continue

        if line.startswith("|") and i + 1 < len(lines) and re.match(r"^\|[\s:|-]+\|?$", lines[i + 1]):
            head = _row(line)
            i += 2
            body = []
            while i < len(lines) and lines[i].startswith("|"):
                body.append(_row(lines[i]))
                i += 1
            tr = "".join("<tr>" + "".join(f"<td>{_inline(c)}</td>" for c in r) + "</tr>"
                         for r in body)
            if any(c.strip() for c in head):
                th = "".join(f"<th>{_inline(c)}</th>" for c in head)
                thead = f"<thead><tr>{th}</tr></thead>"
            else:
                thead = ""   # unlabelled table: an empty thead collapses column widths
            out.append(f'<div class="tscroll"><table>{thead}'
                       f"<tbody>{tr}</tbody></table></div>")
            continue

        if re.match(r"^\s*[-*]\s+", line) or re.match(r"^\s*\d+\.\s+", line):
            ordered = bool(re.match(r"^\s*\d+\.\s+", line))
            items, pattern = [], r"^\s*\d+\.\s+" if ordered else r"^\s*[-*]\s+"
            while i < len(lines) and (re.match(pattern, lines[i]) or
                                      (items and lines[i].startswith("  ") and lines[i].strip())):
                if re.match(pattern, lines[i]):
                    items.append(re.sub(pattern, "", lines[i]))
                else:
                    items[-1] += " " + lines[i].strip()
                i += 1
            tag = "ol" if ordered else "ul"
            out.append(f"<{tag}>" + "".join(f"<li>{_inline(x)}</li>" for x in items) + f"</{tag}>")
            continue

        if not line.strip():
            i += 1
            continue

        # A paragraph ends at the next block. Testing startswith("*") would also
        # swallow a paragraph that merely opens with bold text, so the list
        # patterns are matched properly rather than by first character.
        def _is_block(ln):
            return (not ln.strip()
                    or ln.startswith(("|", "#", "```"))
                    or re.fullmatch(r"-{3,}", ln.strip())
                    or re.fullmatch(r"</?details>|<summary>.*</summary>", ln.strip())
                    or re.match(r"^\s*[-*]\s+", ln)
                    or re.match(r"^\s*\d+\.\s+", ln))

        para = []
        while i < len(lines) and not _is_block(lines[i]):
            para.append(lines[i].strip())
            i += 1
        if para:
            out.append("<p>" + _inline(" ".join(para)) + "</p>")
        else:
            i += 1
    return "\n".join(out)
