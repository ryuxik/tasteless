"""Turn a screenshot + scorecard into the shareable artifact: the rendered UI
with red FAIL badges stamped on every offending element (each labelled with the
rule it breaks), and a before→after composite that shows GATE count collapsing
to zero.

  python -m tasteless.report annotate shot.png score.json --out before.png
  python -m tasteless.report compose before.png after.png --out delta.png \
      --before-n 33 --after-n 0 --title "Pricing page"

The annotated frame IS the demo: "this looks fine" → badges snap on → fixed.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

RED = (220, 38, 38)
AMBER = (217, 119, 6)
GREEN = (22, 163, 74)
INK = (24, 24, 27)


def _font(size, bold=False):
    for p in ("/System/Library/Fonts/SFNSDisplay.ttf",
              "/System/Library/Fonts/Helvetica.ttc",
              "/System/Library/Fonts/Supplemental/Arial Bold.ttf" if bold else
              "/System/Library/Fonts/Supplemental/Arial.ttf",
              "/Library/Fonts/Arial.ttf"):
        try:
            return ImageFont.truetype(p, size)
        except Exception:
            continue
    return ImageFont.load_default()


def _text_size(draw, text, font):
    b = draw.textbbox((0, 0), text, font=font)
    return b[2] - b[0], b[3] - b[1]


def annotate(screenshot: str, scorecard: str, out: str, show_warn=False) -> str:
    img = Image.open(screenshot).convert("RGB")
    rep = json.loads(Path(scorecard).read_text())
    # element rects are in CSS px; the screenshot may be at any device pixel
    # ratio. Scale boxes by the true ratio (screenshot width / CSS width).
    css_w = rep.get("render_css_width", 1440)
    sx = img.width / css_w if css_w else 1.0
    d = ImageDraw.Draw(img, "RGBA")
    f = _font(15, bold=True)

    # group findings by element rect so an element gets one box, many labels
    groups = {}
    for fd in rep["findings"]:
        el = fd.get("element")
        if not el or not el.get("rect"):
            continue
        if fd["status"] == "WARN" and not show_warn:
            continue
        r = el["rect"]
        key = (r["x"], r["y"], r["w"], r["h"])
        groups.setdefault(key, {"fail": False, "rules": []})
        groups[key]["rules"].append(fd["rule"])
        if fd["status"] == "FAIL":
            groups[key]["fail"] = True

    n_fail = rep["summary"]["gate_fail"]
    for (x, y, w, h), g in groups.items():
        color = RED if g["fail"] else AMBER
        x0, y0, x1, y1 = x * sx, y * sx, (x + w) * sx, (y + h) * sx
        for t in range(3):
            d.rectangle([x0 - t, y0 - t, x1 + t, y1 + t], outline=color + (255,))
        d.rectangle([x0, y0, x1, y1], fill=color + (28,))
        label = " · ".join(dict.fromkeys(g["rules"]))[:46]
        tw, th = _text_size(d, label, f)
        ly = max(0, y0 - th - 8)
        d.rectangle([x0, ly, x0 + tw + 12, ly + th + 8], fill=color + (255,))
        d.text((x0 + 6, ly + 3), label, fill=(255, 255, 255), font=f)

    # header banner
    bf = _font(34, bold=True)
    banner = f"  {n_fail} violations of the laws of UX"
    bh = 58
    band = Image.new("RGBA", (img.width, bh), INK + (235,))
    img.paste(Image.alpha_composite(img.crop((0, 0, img.width, bh)).convert("RGBA"), band).convert("RGB"), (0, 0))
    d.text((18, 12), banner, fill=(255, 255, 255), font=bf)
    img.save(out)
    return out


def compose(before: str, after: str, out: str, before_n: int, after_n: int,
            title: str = "") -> str:
    a = Image.open(before).convert("RGB")
    b = Image.open(after).convert("RGB")
    H = 760
    def fit(im):
        h = im.height or 1
        return im.resize((max(1, int(im.width * H / h)), H))
    a, b = fit(a), fit(b)
    gap, top = 24, 92
    W = a.width + b.width + gap
    canvas = Image.new("RGB", (W, H + top), (250, 250, 249))
    canvas.paste(a, (0, top))
    canvas.paste(b, (a.width + gap, top))
    d = ImageDraw.Draw(canvas)
    tf, sf = _font(30, bold=True), _font(20, bold=True)
    if title:
        d.text((4, 8), title, fill=INK, font=tf)
    d.text((4, 50), f"BEFORE — {before_n} GATE violations", fill=RED, font=sf)
    aw = a.width + gap
    d.text((aw + 4, 50), f"AFTER — {after_n} violations", fill=GREEN, font=sf)
    # big arrow in the gutter
    d.text((a.width - 8, top + H // 2 - 20), "→", fill=INK, font=_font(40, bold=True))
    canvas.save(out)
    return out


def compose_hier(before: str, after: str, out: str, before_lines, after_lines,
                 title: str = "") -> str:
    """Side-by-side of the two DINOv2 salience heatmaps with the measured
    pull-share + peak under each, and the intent verdict up top."""
    a = Image.open(before).convert("RGB")
    b = Image.open(after).convert("RGB")
    H = 720
    def fit(im):
        h = im.height or 1
        return im.resize((max(1, int(im.width * H / h)), H))
    a, b = fit(a), fit(b)
    gap, top, footer = 24, 96, 96
    W = a.width + b.width + gap
    canvas = Image.new("RGB", (W, H + top + footer), (250, 250, 249))
    canvas.paste(a, (0, top)); canvas.paste(b, (a.width + gap, top))
    d = ImageDraw.Draw(canvas)
    tf, sf, lf = _font(30, bold=True), _font(21, bold=True), _font(17)
    if title:
        d.text((4, 8), title, fill=INK, font=tf)
    d.text((4, 50), "BEFORE — DINOv2 visual salience", fill=RED, font=sf)
    d.text((a.width + gap + 4, 50), "AFTER — re-measured", fill=GREEN, font=sf)
    y0 = top + H + 10
    for i, ln in enumerate(before_lines):
        d.text((4, y0 + i * 24), ln, fill=INK, font=lf)
    for i, ln in enumerate(after_lines):
        d.text((a.width + gap + 4, y0 + i * 24), ln, fill=INK, font=lf)
    canvas.save(out)
    return out


def hero(before_annotated: str, after: str, out: str, before_n: int,
         surface: str, chips) -> str:
    """A branded static hero: dark canvas, wordmark, the cited-badge BEFORE next
    to the clean AFTER, a big N→0, and a strip of cited-rule chips."""
    BG, INK, MUT, LINE = (11, 11, 14), (238, 240, 245), (170, 176, 189), (42, 42, 52)
    a = Image.open(before_annotated).convert("RGB")
    b = Image.open(after).convert("RGB")
    SH = 660
    def fit(im):
        h = im.height or 1
        return im.resize((max(1, int(im.width * SH / h)), SH))
    a, b = fit(a), fit(b)
    pad, gap, header, footer = 64, 150, 176, 96
    W = pad * 2 + a.width + b.width + gap
    Hc = header + SH + footer
    cv = Image.new("RGB", (W, Hc), BG)
    d = ImageDraw.Draw(cv)
    wf, tf, lf = _font(42, bold=True), _font(22), _font(23, bold=True)

    # wordmark TASTE(red)LESS + tagline
    d.text((pad, 38), "TASTE", font=wf, fill=INK)
    w0 = _text_size(d, "TASTE", wf)[0]
    d.text((pad + w0, 38), "LESS", font=wf, fill=RED)
    wm = w0 + _text_size(d, "LESS", wf)[0]
    d.text((pad + wm + 20, 50), "It doesn't have taste. It has citations.", font=tf, fill=MUT)
    d.text((pad, 96), f"Audited the {surface} against the laws of UX:", font=tf, fill=MUT)

    ax, bx = pad, pad + a.width + gap
    d.text((ax, header - 34), "BEFORE", font=lf, fill=RED)
    d.text((bx, header - 34), "AFTER", font=lf, fill=GREEN)
    cv.paste(a, (ax, header)); cv.paste(b, (bx, header))
    d.rectangle([ax - 1, header - 1, ax + a.width, header + SH], outline=LINE)
    d.rectangle([bx - 1, header - 1, bx + b.width, header + SH], outline=LINE)

    # center transformation N → 0
    cxc = ax + a.width + gap // 2
    nf = _font(58, bold=True)
    midy = header + SH // 2
    nstr, zstr = str(before_n), "0"
    d.text((cxc - _text_size(d, nstr, nf)[0] // 2, midy - 100), nstr, font=nf, fill=RED)
    ay = midy - 14  # drawn down-arrow (font-independent)
    d.polygon([(cxc - 16, ay), (cxc + 16, ay), (cxc, ay + 24)], fill=INK)
    d.text((cxc - _text_size(d, zstr, nf)[0] // 2, midy + 30), zstr, font=nf, fill=GREEN)

    # cited-rule chips
    cf = _font(16)
    cx, cy = pad, header + SH + 30
    for c in chips:
        cw = _text_size(d, c, cf)[0] + 26
        d.rounded_rectangle([cx, cy, cx + cw, cy + 36], radius=18, fill=(21, 21, 27), outline=LINE)
        d.text((cx + 13, cy + 9), c, font=cf, fill=(143, 176, 255))
        cx += cw + 12
    cv.save(out)
    return out


def main():
    ap = argparse.ArgumentParser(description="Render the before/after artifacts.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    pa = sub.add_parser("annotate")
    pa.add_argument("screenshot"); pa.add_argument("scorecard")
    pa.add_argument("--out", required=True); pa.add_argument("--warn", action="store_true")
    pc = sub.add_parser("compose")
    pc.add_argument("before"); pc.add_argument("after")
    pc.add_argument("--out", required=True)
    pc.add_argument("--before-n", type=int, required=True)
    pc.add_argument("--after-n", type=int, default=0)
    pc.add_argument("--title", default="")
    a = ap.parse_args()
    if a.cmd == "annotate":
        print("annotated →", annotate(a.screenshot, a.scorecard, a.out, a.warn))
    else:
        print("composed →", compose(a.before, a.after, a.out, a.before_n, a.after_n, a.title))


if __name__ == "__main__":
    main()
