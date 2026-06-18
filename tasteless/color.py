"""WCAG 2.x contrast math + a deterministic "nearest passing colour" solver.

No taste here. Just the normative formulas:

  relative luminance   https://www.w3.org/WAI/GL/wiki/Relative_luminance
  contrast ratio       https://www.w3.org/TR/WCAG21/#dfn-contrast-ratio
  (1.4.3 / 1.4.6 / 1.4.11)

The contrast ratio is (L1 + 0.05) / (L2 + 0.05) where L1 is the lighter of the
two relative luminances. Everything downstream of this file is a comparison
against a published threshold, not an opinion.
"""
from __future__ import annotations

import re

# WCAG normative thresholds (ratios). Large text = >=18pt (24px) or >=14pt
# (18.66px) bold. https://www.w3.org/TR/WCAG21/#contrast-minimum
AA_NORMAL = 4.5
AA_LARGE = 3.0
AAA_NORMAL = 7.0
AAA_LARGE = 4.5
NON_TEXT = 3.0  # UI components & graphical objects, 1.4.11

RGB = tuple  # (r, g, b) ints 0-255

_HEX = re.compile(r"^#?([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")
_RGB = re.compile(r"rgba?\(([^)]+)\)")


def parse_color(s: str) -> tuple[int, int, int, float] | None:
    """Parse a CSS colour string into (r, g, b, a). Handles the forms
    getComputedStyle actually returns (rgb()/rgba()) plus hex. Returns None for
    things we can't resolve to a flat colour (gradients, 'transparent', etc.)."""
    if not s:
        return None
    s = s.strip()
    if s in ("transparent", "rgba(0, 0, 0, 0)"):
        return (0, 0, 0, 0.0)
    m = _RGB.match(s)
    if m:
        parts = [p.strip() for p in m.group(1).split(",")]
        if len(parts) < 3:
            return None
        try:
            r, g, b = (int(round(float(parts[i]))) for i in range(3))
            a = float(parts[3]) if len(parts) > 3 else 1.0
        except ValueError:
            return None
        return (r, g, b, a)
    m = _HEX.match(s)
    if m:
        h = m.group(1)
        if len(h) == 3:
            h = "".join(c * 2 for c in h)
        return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), 1.0)
    return None


def composite(fg: tuple[int, int, int, float], bg: RGB) -> RGB:
    """Alpha-composite fg over an opaque bg → opaque rgb (the colour a human
    actually sees). Needed because a text/background colour with alpha<1 only
    has a real contrast value once flattened against what's behind it."""
    r, g, b, a = fg
    br, bg_, bb = bg
    return (
        round(r * a + br * (1 - a)),
        round(g * a + bg_ * (1 - a)),
        round(b * a + bb * (1 - a)),
    )


def _lin(c: int) -> float:
    cs = c / 255.0
    # WCAG glossary uses 0.03928; W3C's own errata corrects this to 0.04045.
    # The two differ only at one 8-bit channel value and never change a ratio
    # to 2 decimals. We use the corrected breakpoint.
    return cs / 12.92 if cs <= 0.04045 else ((cs + 0.055) / 1.055) ** 2.4


def luminance(rgb: RGB) -> float:
    r, g, b = rgb
    return 0.2126 * _lin(r) + 0.7152 * _lin(g) + 0.0722 * _lin(b)


def contrast(c1: RGB, c2: RGB) -> float:
    """WCAG contrast ratio between two opaque colours, 1.0–21.0."""
    l1, l2 = luminance(c1), luminance(c2)
    lo, hi = sorted((l1, l2))
    return round((hi + 0.05) / (lo + 0.05), 2)


def required_ratio(font_px: float, bold: bool, level: str = "AA") -> float:
    """The threshold this text must meet, per its size/weight and the target
    conformance level."""
    large = font_px >= 24 or (bold and font_px >= 18.66)
    if level == "AAA":
        return AAA_LARGE if large else AAA_NORMAL
    return AA_LARGE if large else AA_NORMAL


def _toward(fg: RGB, target: RGB, t: float) -> RGB:
    return tuple(round(fg[i] + (target[i] - fg[i]) * t) for i in range(3))


def nearest_passing(fg: RGB, bg: RGB, ratio: float) -> RGB | None:
    """Deterministic fix: the closest foreground colour to `fg` that hits
    `ratio` against `bg`, found by binary-searching a blend toward black or
    white (whichever direction the background allows). Keeps the colour family
    while guaranteeing the published threshold. Returns None if even pure
    black/white can't reach the ratio against this background."""
    if contrast(fg, bg) >= ratio:
        return fg
    bg_lum = luminance(bg)
    # Push away from the background: darken on light bg, lighten on dark bg.
    target = (0, 0, 0) if bg_lum > 0.5 else (255, 255, 255)
    if contrast(target, bg) < ratio:
        # try the opposite extreme before giving up
        target = (255, 255, 255) if target == (0, 0, 0) else (0, 0, 0)
        if contrast(target, bg) < ratio:
            return None
    lo, hi = 0.0, 1.0
    for _ in range(24):  # ~1/16M precision; plenty
        mid = (lo + hi) / 2
        if contrast(_toward(fg, target, mid), bg) >= ratio:
            hi = mid
        else:
            lo = mid
    return _toward(fg, target, hi)


def to_hex(rgb: RGB) -> str:
    return "#%02x%02x%02x" % rgb
