# Accessibility review: WCAG 2.1 AA basics

A review of this project's two published pages against the WCAG 2.1 Level AA basics:
heading structure, alternative text for non-text content, and colour contrast. Carried out
September 2026, against
[the Migration Control Room](https://dinushitj.github.io/hr-migration-sandbox/) and
[the FAQ](https://dinushitj.github.io/hr-migration-sandbox/faq.html).

Every finding here was in my own code. I have written what was wrong, what it measured,
what changed, and what is still outstanding, because a review that only lists passes is
not a review.

## Summary

| | Before | After |
|---|---|---|
| Colour pairs meeting 4.5:1 | 33 of 42 | 42 of 42 |
| Page language declared | No | Yes |
| Viewport declared | No | Yes |
| Heading levels without a skip | No | Yes |

## Findings and fixes

### 1. The page never declared its language

**WCAG 3.1.1 Language of Page, Level A.** The generated `control_room.html` began at
`<title>`. There was no doctype, no `<html>` element and therefore no `lang` attribute, and
no character encoding declaration. Browsers recover from this, which is exactly why it
survived: nothing looked wrong. A screen reader has no such luxury. Without `lang` it
falls back to the user's default voice, so an English page can be read with the phoneme
rules of another language.

Fixed in `viz/template.html` by adding a real document head with `<!doctype html>`,
`<html lang="en">` and `<meta charset="utf-8">`, and closing the document properly. The
template was a fragment and is now a document. `src/build_viz.py` substitutes strings into
it and needed no change.

### 2. No viewport declaration

**WCAG 1.4.10 Reflow, AA.** Without `<meta name="viewport">`, a mobile browser lays the
page out at a desktop width and scales it down, so text that should reflow into one column
instead becomes small and requires zooming and horizontal scrolling. The page's CSS
already had the media queries to reflow correctly; they simply never got the chance.

Fixed by adding `<meta name="viewport" content="width=device-width, initial-scale=1">`.

### 3. Two colour tokens failed contrast

**WCAG 1.4.3 Contrast (Minimum), AA.** The `--faint` token failed in both themes and
`--warn` failed in the light theme, measured against all three surfaces they are drawn on.

| Token | Theme | Before (worst of 3 backgrounds) | After |
|---|---|---|---|
| `--faint` | light | 2.68:1 | 4.65:1 |
| `--faint` | dark | 3.61:1 | 4.69:1 |
| `--warn` | light | 3.71:1 | 4.68:1 |

There is no large-text exception available here. `--faint` is applied at 10px to 13px, to
the uppercase eyebrow labels, record field keys, tab counts, flow-figure labels and the
empty state. The 3:1 exception requires 18.66px bold or 24px regular, so the 4.5:1
threshold is the one that applies, and 2.68:1 is a long way below it.

Worth being honest about what caused it. The visual hierarchy of small labels was built by
making them *lower contrast* than body text, which is the same thing as making them harder
to read. The fix keeps the hierarchy but moves it onto properties that cost nothing in
legibility: size, weight, letter spacing and uppercasing. `--faint` is now close in
luminance to `--muted`, and the labels still read as secondary, because they were never
relying on contrast alone to say so.

Both hues were preserved. Each new value is the smallest lightness change from the
original that clears the threshold, with a small margin above 4.5 so that a rounding
difference in someone else's checker does not flip the result.

### 4. A heading level was skipped in the README

**WCAG 1.3.1 Info and Relationships, AA.** `README.md` went from its `#` title straight to
`### At a glance`. This is not only a repository concern: the README is rendered into the
replay page's Documentation section at build time, so the skip was published. Changed to
`## At a glance`.

The FAQ had the same defect in draft, `#` followed by `###`, and was corrected before it
was ever published.

### 5. Link text that did not describe its destination

**WCAG 2.4.4 Link Purpose (In Context), AA.** The FAQ draft used "see it live here" as
link text. Screen reader users commonly navigate by pulling up a list of a page's links,
where "here" carries no information at all. Replaced with "open the Migration Control
Room", which names the destination.

## What already passed, and is worth recording

- **The one non-text element that needs a name has one.** The pipeline flow figure is an
  inline SVG carrying `role="img"` and a full `aria-label` describing the whole diagram,
  including the three-way outcome and the cascade. There are no `<img>` elements anywhere
  in either page, so there is no missing alt text to report.
- **The decorative SVG sprite sheet is correctly hidden**, with `aria-hidden="true"` and
  `focusable="false"`, so it is not announced or focusable.
- **The tab interface uses real semantics**, `role="tablist"`, `role="tab"` and
  `aria-selected`, rather than styled divs. The speed and entity filters are grouped with
  `role="group"` and an `aria-label`. The expandable rows carry `aria-expanded`.
- **Five of seven colour tokens already met AA** on every background in both themes:
  `--ink`, `--muted`, `--chrome`, `--ok` and `--bad`. The lowest of those is `--ok` in the
  light theme at 4.83:1.
- **Reduced motion is respected.** The page disables its transitions and animations under
  `@media (prefers-reduced-motion: reduce)`.

## Making it stay fixed

Contrast is invisible to the person choosing the colours, which is how this defect lasted
as long as it did. So the fix is enforced rather than remembered: `src/check_contrast.py`
parses the theme tokens out of `viz/template.html`, computes all 42 foreground and
background pairs across both themes, and exits non-zero if any falls below 4.5:1. It runs
in `.github/workflows/pages.yml` as a deployment gate, alongside the existing data
validation, so a colour change that breaks AA fails the build instead of shipping.

`src/build_faq.py` does the same for structure: it fails the build if the FAQ's headings
do not start at a single `h1` or if any level is skipped.

Both checks were confirmed to fail on purpose before being trusted, by reintroducing the
original values and watching them report the original numbers.

## Outstanding

Left undone, and listed because the point of a review is the things it found.

1. **Heading depth in the injected documentation.** The replay page renders the full README
   inside its Documentation section, so the README's `h1` and `h2` headings appear
   underneath the page's own `<h2>Documentation</h2>`. The levels no longer skip, but the
   nesting misrepresents the outline: a screen reader user navigating by heading meets a
   second `h1` two thirds of the way down the page. The proper fix is for the renderer to
   demote injected headings by two levels, which means changing `src/markdown_lite.py` to
   take an offset.
2. **No keyboard audit.** This review covered structure, text alternatives and contrast,
   which is what it set out to cover. Focus order, focus visibility on every control, and
   whether the scrubber and tab list are fully operable from the keyboard have not been
   tested. The tabs use correct roles, but correct roles are not the same as correct
   arrow-key behaviour, which WCAG 2.1.1 would require.
3. **Contrast of non-text elements.** WCAG 1.4.11 Non-text Contrast requires 3:1 for
   interface components and meaningful graphics. The border tokens do not come close:
   `--line` measures 1.15:1 to 1.33:1 against the surfaces it is drawn on and
   `--line-strong` 1.43:1 to 1.72:1, in both themes. Whether that is a failure depends on
   the instance, since a purely decorative card border is out of scope while a border that
   delineates a control is not, and I have not gone through them case by case. The flow
   figure's strokes and the focus indicators are unmeasured. I have left this rather than
   darkening every border, because it changes the look of the whole page and the honest
   first step is deciding which borders are load-bearing.
4. **The replay page has no landmarks and no skip link.** It is built from `<header>`,
   `<section>` and `<div>` with no `<main>`, so there is no way to jump past the masthead
   and controls to the content. The FAQ page was built with a `<main>` and a skip link,
   which is the pattern the replay page should follow. Related to item 1: the page also
   carries two `h1` elements, its own and the injected README's, confirmed by parsing the
   built output.
5. **No testing with an actual screen reader.** Everything above is static analysis and
   arithmetic. It establishes that the markup and colours permit a good experience; it
   does not establish that there is one.
