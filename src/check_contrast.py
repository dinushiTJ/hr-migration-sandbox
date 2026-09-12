"""
Check the replay page's colour tokens against WCAG AA contrast.

The page failed this when it was audited: two tokens sat below 4.5:1 while
being used at 10px, and the reason they survived that long is that contrast is
invisible to the person who chose the colours. A number is the only honest way
to look at it, so this reads the tokens out of the template and computes them.

The token values are parsed from viz/template.html rather than restated here,
so the check cannot pass against colours the page no longer uses. The pairings
are declared, because which foreground is drawn on which background is a fact
about the CSS that no regex is going to establish reliably. That is the weak
joint in this check: a new token used on a new background is not caught until
someone adds it to PAIRS.

Every pair is tested at 4.5:1, the threshold for normal-size text. Nothing on
this page is large enough to earn the 3:1 exception, so nothing gets it.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = ROOT / "viz" / "template.html"

AA_NORMAL = 4.5

BACKGROUNDS = ("paper", "surface", "surface-2")

# Foreground tokens that carry text, each against every background it can land
# on. faint is included on all three because .pill.idle puts it on surface-2.
FOREGROUNDS = ("ink", "muted", "faint", "chrome", "ok", "bad", "warn")

PAIRS = [(fg, bg) for fg in FOREGROUNDS for bg in BACKGROUNDS]


def _luminance(hex_colour):
    h = hex_colour.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    channels = []
    for i in (0, 2, 4):
        v = int(h[i:i + 2], 16) / 255
        channels.append(v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4)
    r, g, b = channels
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def ratio(fg, bg):
    a, b = _luminance(fg), _luminance(bg)
    hi, lo = max(a, b), min(a, b)
    return (hi + 0.05) / (lo + 0.05)


def themes(css):
    """Pull the light and dark token blocks out of the template.

    Light lives on the bare :root. Dark is declared twice, once under a
    prefers-color-scheme query and once under [data-theme="dark"] so the
    toggle can win; they must agree, and this checks the first one it finds
    against the second rather than trusting that they were edited together.
    """
    blocks = re.findall(r"(:root[^{]*)\{([^}]*)\}", css)
    light, dark = None, []
    for selector, body in blocks:
        tokens = dict(re.findall(r"--([a-z0-9-]+)\s*:\s*(#[0-9a-fA-F]{3,6})", body))
        if not tokens:
            continue
        if selector.strip() == ":root":
            light = tokens
        elif "dark" in selector:
            dark.append(tokens)

    if light is None or not dark:
        raise SystemExit("could not find both theme blocks in the template")
    for other in dark[1:]:
        disagreements = {k for k in dark[0].keys() | other.keys()
                         if dark[0].get(k) != other.get(k)}
        if disagreements:
            raise SystemExit("dark theme blocks disagree on: "
                             + ", ".join(sorted(disagreements)))
    return {"light": light, "dark": dark[0]}


def main():
    css = TEMPLATE.read_text()
    failures = []
    print(f"contrast: {TEMPLATE.relative_to(ROOT)}, threshold {AA_NORMAL}:1\n")
    for name, tokens in themes(css).items():
        print(f"  {name}")
        for fg, bg in PAIRS:
            if fg not in tokens or bg not in tokens:
                raise SystemExit(f"{name} theme is missing token --{fg} or --{bg}")
            r = ratio(tokens[fg], tokens[bg])
            ok = r >= AA_NORMAL
            if not ok:
                failures.append(f"{name}: --{fg} on --{bg} is {r:.2f}:1")
            print(f"    {'PASS' if ok else 'FAIL'}  "
                  f"--{fg:9s} on --{bg:9s} {r:5.2f}:1")
        print()

    if failures:
        print(f"{len(failures)} pair(s) below {AA_NORMAL}:1")
        for f in failures:
            print(f"  {f}")
        return 1
    print(f"all {len(PAIRS) * 2} pairs meet {AA_NORMAL}:1")
    return 0


if __name__ == "__main__":
    sys.exit(main())
