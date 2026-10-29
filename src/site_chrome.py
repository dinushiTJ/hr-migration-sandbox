"""
The parts every published page shares: stylesheet, theme script, fonts and
the navigation bar.

Three pages are built by two scripts. Each used to carry its own colours, and
the FAQ's had already drifted from the replay's. Building the shared parts here
means a page cannot look like it belongs to a different site.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPO = "https://github.com/dinushiTJ/hr-migration-sandbox"
BASE_CSS = ROOT / "viz" / "base.css"
THEME_JS = ROOT / "viz" / "theme.js"
MOTION_JS = ROOT / "viz" / "motion.js"

# Relative links, so the same pages work opened from out/ on disk and served
# from GitHub Pages, where CI publishes control_room.html under both names.
PAGES = (
    ("control_room.html", "Replay"),
    ("docs.html", "Docs"),
    ("faq.html", "FAQ"),
)

FONTS = (
    '<link rel="preconnect" href="https://fonts.googleapis.com">\n'
    '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>\n'
    '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?'
    'family=Geist:wght@400;500;600&family=Geist+Mono:wght@400;500;600&display=swap">'
)

_MARK = ('<svg class="ic" viewBox="0 0 24 24" aria-hidden="true"><path d="M4 7h10M4 12h16M4 17h7"></path>'
         '<circle cx="18" cy="7" r="2"></circle><circle cx="15" cy="17" r="2"></circle></svg>')

_SUN = ('<svg class="ic i-sun" viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="4.5"></circle>'
        '<path d="M12 1.5v3M12 19.5v3M4.2 4.2l2.1 2.1M17.7 17.7l2.1 2.1M1.5 12h3M19.5 12h3'
        'M4.2 19.8l2.1-2.1M17.7 6.3l2.1-2.1"></path></svg>')
_MOON = ('<svg class="ic i-moon" viewBox="0 0 24 24" aria-hidden="true">'
         '<path d="M20 14.5A8.5 8.5 0 0 1 9.5 4a8.5 8.5 0 1 0 10.5 10.5z"></path></svg>')


def head_assets():
    """Fonts, the shared stylesheet, and the theme and motion scripts, for inside <head>."""
    return (f"{FONTS}\n<style>\n{BASE_CSS.read_text()}</style>\n"
            f"<script>\n{THEME_JS.read_text()}</script>\n"
            f"<script>\n{MOTION_JS.read_text()}</script>")


def nav(active):
    """The bar across the top of every page. `active` is a file name from PAGES."""
    # Kept out of the f-string: a backslash inside the braces needs Python 3.12.
    current = ' aria-current="page"'
    links = "".join(
        f'<a href="{href}"{current if href == active else ""}>{label}</a>'
        for href, label in PAGES)
    return f"""<header class="nav">
  <div class="nav-in">
    <a class="mark" href="control_room.html"><i>{_MARK}</i><span>HR Migration Sandbox</span></a>
    <nav class="nav-links" aria-label="Site">{links}</nav>
    <button class="theme-btn" id="theme" type="button" aria-label="Switch colour mode">{_SUN}{_MOON}</button>
  </div>
</header>"""


def repo_links(body):
    """Point the Markdown's relative links at something that exists once
    published. The README and FAQ link to files beside them, which works on
    GitHub but not on Pages, where only the three pages are served. The README
    is the docs page; any other repository file goes to its GitHub view."""
    def fix(m):
        path = m.group(1)
        if path in ("README.md", "./README.md"):
            return 'href="docs.html"'
        return f'href="{REPO}/blob/main/{path.removeprefix("./")}"'
    return re.sub(r'href="((?:\./)?(?!docs\.html|faq\.html|control_room\.html)[\w./-]+\.\w+)"', fix, body)
