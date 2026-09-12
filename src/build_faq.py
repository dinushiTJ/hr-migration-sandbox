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

ROOT = Path(__file__).resolve().parent.parent
FAQ = ROOT / "FAQ.md"
OUT = ROOT / "out" / "faq.html"

TITLE = "FAQ: HR Data Migration Sandbox"
REPLAY = "https://dinushitj.github.io/hr-migration-sandbox/"
REPO = "https://github.com/dinushiTJ/hr-migration-sandbox"

# Every colour is measured against both of its own backgrounds at 4.5:1, the
# WCAG AA threshold for normal-size text, because every size on this page is
# normal-size text. No token is used at a size that would earn the 3:1
# large-text exception, so none of them gets to rely on it.
STYLE = """
:root{
  --paper:#eef1f4; --surface:#fff; --ink:#131820; --muted:#5b6775;
  --line:#d9e0e7; --chrome:#2d4a7c;
}
@media (prefers-color-scheme: dark){
  :root{
    --paper:#0d1117; --surface:#151b23; --ink:#e7ecf2; --muted:#98a4b3;
    --line:#252d38; --chrome:#8fb0e8;
  }
}
*{box-sizing:border-box}
body{
  margin:0; background:var(--paper); color:var(--ink);
  font:16px/1.65 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
  -webkit-text-size-adjust:100%;
}
.skip{
  position:absolute; left:-9999px; top:0; padding:10px 14px; z-index:10;
  background:var(--surface); color:var(--chrome); border:2px solid var(--chrome);
}
.skip:focus{left:8px; top:8px}
.wrap{max-width:46rem; margin:0 auto; padding:32px 20px 64px}
main{background:var(--surface); border:1px solid var(--line); border-radius:6px;
  padding:8px 28px 28px}
h1{font-size:1.85rem; line-height:1.25; margin:24px 0 8px}
h2{font-size:1.15rem; line-height:1.35; margin:34px 0 0;
  padding-top:18px; border-top:1px solid var(--line)}
h1+p em, h1+p{color:var(--muted)}
p,li{margin:12px 0}
ul{padding-left:22px}
a{color:var(--chrome); text-decoration:underline; text-underline-offset:2px}
a:focus-visible,.skip:focus-visible{outline:2px solid var(--chrome); outline-offset:2px}
hr{border:0; border-top:1px solid var(--line); margin:22px 0}
code{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace; font-size:.92em}
nav.back{margin:0 0 18px; font-size:.94rem}
footer{margin:22px 4px 0; font-size:.9rem; color:var(--muted)}
@media (max-width:520px){
  .wrap{padding:20px 14px 48px}
  main{padding:4px 18px 20px}
}
"""

PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<meta name="description" content="A plain-English explanation of the HR Data \
Migration Sandbox, written for readers with no technical background.">
<style>{style}</style>
</head>
<body>
<a class="skip" href="#faq">Skip to the questions</a>
<div class="wrap">
<nav class="back"><a href="{replay}">Back to the Migration Control Room</a></nav>
<main id="faq">
{body}
</main>
<footer>Source for this page: <a href="{repo}/blob/main/FAQ.md">FAQ.md</a> in the
<a href="{repo}">project repository</a>.</footer>
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
    levels = [int(m) for m in re.findall(r"<h([1-6])>", body)]
    if not levels:
        raise SystemExit("FAQ.md produced no headings")
    if levels[0] != 1 or levels.count(1) != 1:
        raise SystemExit(f"expected exactly one h1 first, got levels {levels}")
    for prev, cur in zip(levels, levels[1:]):
        if cur > prev + 1:
            raise SystemExit(f"heading level skipped: h{prev} followed by h{cur}")
    return levels


def main():
    body = render_markdown(FAQ.read_text())
    levels = check_heading_order(body)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(PAGE.format(title=html.escape(TITLE), style=STYLE,
                               body=body, replay=REPLAY, repo=REPO))
    print(f"{OUT.name}  {OUT.stat().st_size / 1024:.0f} KB  "
          f"{len(levels)} headings, no skipped levels")


if __name__ == "__main__":
    main()
