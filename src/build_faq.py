"""
Render FAQ.md as a standalone, accessible HTML page.

The FAQ exists because the rest of this repository is written for people who
read code. Publishing it only as Markdown would mean the one plain-English
document renders inside a code host's chrome, whose contrast and heading
semantics are not mine to control. So it is built as a real page instead.

Nothing here is hand-written HTML beyond the wrapper: the body comes from
FAQ.md through the same renderer the replay page uses for the README, so the
page cannot drift from the file.

The wrapper is where the accessibility work lives, and the heading check below
enforces it rather than asserting it. A page that claims to be accessible and
skips a heading level is worse than one that makes no claim.
"""
import html
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from markdown_lite import render as render_markdown
from site_chrome import REPO, head_assets, nav, repo_links

ROOT = Path(__file__).resolve().parent.parent
FAQ = ROOT / "FAQ.md"
OUT = ROOT / "out" / "faq.html"

TITLE = "FAQ: HR Data Migration Sandbox"

# Colours, type and the long-form text styles come from viz/base.css, whose
# tokens src/check_contrast.py holds to 4.5:1 in both themes. Only the column
# and the footer are specific to this page.
STYLE = """
.faq{max-width:46rem; margin:0 auto; padding:56px var(--gutter) 96px}
.faq .prose h2{font-size:22px; margin-top:48px}
.faq .prose h1 + p{color:var(--muted); font-size:17px}
.faq footer{margin-top:56px; padding-top:20px; border-top:1px solid var(--line-strong);
  font-size:14px; color:var(--muted)}
.faq footer a{color:var(--chrome); text-underline-offset:3px}
"""

PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<meta name="description" content="A plain-English explanation of the HR Data \
Migration Sandbox, written for readers with no technical background.">
{head}
<style>{style}</style>
</head>
<body>
<a class="skip" href="#faq">Skip to the questions</a>
{nav}
<div class="faq">
<main id="faq" class="prose" tabindex="-1">
{body}
</main>
<footer>Source for this page: <a href="{repo}/blob/main/FAQ.md">FAQ.md</a> in the
<a href="{repo}">project repository</a>. The technical detail is in the
<a href="docs.html">documentation</a>.</footer>
</div>
</body>
</html>
"""


def check_heading_order(body):
    """Fail the build if a heading level is skipped.

    A screen reader user navigates by heading, so a jump from h1 to h3 removes
    a rung from the ladder. The first draft of FAQ.md did exactly that, which
    is why this is a build failure and not a note in a checklist.
    """
    levels = [int(m) for m in re.findall(r"<h([1-6])[\s>]", body)]
    if not levels:
        raise SystemExit("FAQ.md produced no headings")
    if levels[0] != 1 or levels.count(1) != 1:
        raise SystemExit(f"expected exactly one h1 first, got levels {levels}")
    for prev, cur in zip(levels, levels[1:]):
        if cur > prev + 1:
            raise SystemExit(f"heading level skipped: h{prev} followed by h{cur}")
    return levels


def main():
    body = repo_links(render_markdown(FAQ.read_text()))
    levels = check_heading_order(body)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(PAGE.format(title=html.escape(TITLE), head=head_assets(), nav=nav("faq.html"),
                               style=STYLE, body=body, repo=REPO))
    print(f"{OUT.name}  {OUT.stat().st_size / 1024:.0f} KB  "
          f"{len(levels)} headings, no skipped levels")


if __name__ == "__main__":
    main()
