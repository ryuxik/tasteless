"""The rule engine. Reads the JSON from `tasteless.shoot`, runs every law it can
measure on the rendered DOM, and emits a CITED scorecard: each finding names the
rule, the published threshold, the measured value, and a concrete fix.

  python -m tasteless.audit /tmp/tasteless_shot.json --level AA
  python -m tasteless.audit /tmp/tasteless_shot.json --json /tmp/score.json

Three classes of rule:
  GATE       hard pass/fail against a normative threshold, deterministic fix
  SCORE      measured cost, reported + suggested (never auto-forced)
  HEURISTIC  perceptual; surfaced, not gated (see tasteless.measure)

Nothing here is taste. Every FAIL is a number on the wrong side of a citation.
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
from pathlib import Path

import numpy as np

from . import color as C

LAW = {
    "1.4.3":  "WCAG 2.1 SC 1.4.3 Contrast (Minimum) — https://www.w3.org/WAI/WCAG21/Understanding/contrast-minimum.html",
    "1.4.6":  "WCAG 2.1 SC 1.4.6 Contrast (Enhanced) — https://www.w3.org/WAI/WCAG21/Understanding/contrast-enhanced.html",
    "1.4.11": "WCAG 2.1 SC 1.4.11 Non-text Contrast — https://www.w3.org/WAI/WCAG21/Understanding/non-text-contrast.html",
    "1.4.8":  "WCAG 2.1 SC 1.4.8 Visual Presentation (AAA) — https://www.w3.org/WAI/WCAG21/Understanding/visual-presentation.html",
    "2.5.8":  "WCAG 2.2 SC 2.5.8 Target Size (Minimum) — https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum.html",
    "2.5.5":  "WCAG 2.1 SC 2.5.5 Target Size (Enhanced) — https://www.w3.org/WAI/WCAG21/Understanding/target-size-enhanced.html",
    "hig":    "Apple HIG, Accessibility (44pt min) — https://developer.apple.com/design/human-interface-guidelines/accessibility",
    "material": "Material Design, touch targets (48dp) — https://m2.material.io/design/usability/accessibility.html#layout-typography",
    "fitts":  "Fitts's Law — https://lawsofux.com/fittss-law/",
    "hicks":  "Hick's Law — https://lawsofux.com/hicks-law/",
    "measure": "Line length 45–75 chars (Bringhurst) — https://practicaltypography.com/line-length.html",
    "aria":   "WAI-ARIA APG, Button pattern — https://www.w3.org/WAI/ARIA/apg/patterns/button/",
    "proximity": "Law of Proximity (Gestalt) — https://lawsofux.com/law-of-proximity/",
    "cost":   "Interaction Cost; the 3-click 'rule' is a myth — https://www.nngroup.com/articles/interaction-cost-definition/",
}

# CTA-ish text → likely a primary action, for the Fitts check.
CTA_WORDS = ("sign up", "signup", "get started", "start", "buy", "subscribe",
             "checkout", "check out", "try", "download", "continue", "submit",
             "join", "create account", "book", "order", "add to cart", "next")


def _rgb(s):
    p = C.parse_color(s)
    return p


def _load_shot(data):
    """Load the screenshot so contrast can be measured against the REAL rendered
    background (images, gradients, video) instead of guessing from the CSS chain."""
    p = data.get("screenshot")
    if not p or not Path(p).exists():
        return None, 1.0
    try:
        from PIL import Image
        im = Image.open(p).convert("RGB")
    except Exception:
        return None, 1.0
    vw = data.get("viewport", {}).get("w") or 1440
    return im, (im.width / vw if vw else 1.0)


def sample_bg(img, scale, rect, fg):
    """Dominant background colour behind a text element, sampled from the pixels —
    excluding colours close to the text colour so glyphs don't skew it. Returns
    None if the rect is outside the captured screenshot (e.g. below a viewport
    shot), so the caller can fall back to the CSS chain."""
    x0, y0 = int(rect["x"] * scale), int(rect["y"] * scale)
    x1, y1 = int((rect["x"] + rect["w"]) * scale), int((rect["y"] + rect["h"]) * scale)
    x0, y0 = max(0, x0), max(0, y0)
    x1, y1 = min(img.width, x1), min(img.height, y1)
    if x1 - x0 < 2 or y1 - y0 < 2:
        return None
    crop = img.crop((x0, y0, x1, y1))
    crop.thumbnail((48, 48))
    arr = (np.asarray(crop).reshape(-1, 3).astype(int) // 16) * 16
    vals, counts = np.unique(arr, axis=0, return_counts=True)
    if counts.sum() == 0:
        return None
    # conf = how much ONE colour dominates the whole box → uniform bg (high) vs
    # gradient/image (low). Measured over ALL pixels so sparse text doesn't skew it.
    conf = float(counts.max()) / float(counts.sum())
    # bg VALUE = the dominant colour that isn't the text colour (drop glyphs).
    vbg, cbg = vals, counts
    if fg is not None:
        fgq = np.array([(c // 16) * 16 for c in fg[:3]])
        keep = np.abs(vals - fgq).sum(axis=1) > 40
        if keep.any():
            vbg, cbg = vals[keep], counts[keep]
    return tuple(int(v) for v in vbg[int(cbg.argmax())]), conf


def effective_bg(el, base=(255, 255, 255), skip_self=False):
    """Flatten an element's background-colour chain (self→root) over an opaque
    base, the way the eye sees it. Returns None if a background image makes the
    colour indeterminate — we WARN rather than guess in that case."""
    if el.get("bgImage"):
        return None
    chain = el.get("bgChain", [])
    if skip_self and chain:
        chain = chain[1:]
    out = base
    for c in reversed(chain):  # root → self
        p = C.parse_color(c)
        if p:
            out = C.composite(p, out)
    return out


def _f(rule, cls, sev, law, el, measured, threshold, status, fix, note=""):
    return {
        "rule": rule, "class": cls, "severity": sev,
        "law": law, "citation": LAW.get(law, law),
        "element": {"tag": el.get("tag"), "role": el.get("role"),
                    "text": el.get("text"), "rect": el.get("rect")} if el else None,
        "measured": measured, "threshold": threshold,
        "status": status, "fix": fix, "note": note,
    }


# ---- GATE rules ----------------------------------------------------------

def rule_contrast(els, ctx):
    level = ctx["level"]
    law = "1.4.6" if level == "AAA" else "1.4.3"
    img, scale = ctx.get("img"), ctx.get("scale", 1.0)
    out = []
    for el in els:
        if not el.get("text"):
            continue
        fg_raw = C.parse_color(el.get("color") or "")
        if not fg_raw:
            continue
        sampled = sample_bg(img, scale, el["rect"], fg_raw) if img is not None else None
        if sampled is not None:
            bg, conf = sampled
            if conf < 0.5:                  # gradient/image/photo behind the text
                out.append(_f("contrast", "GATE", "low", law, el, "varies",
                              f"{C.required_ratio(el['fontPx'], el['bold'], level)}:1",
                              "WARN",
                              "Text sits on a varied background (gradient/image) — "
                              "contrast can't be a single number; review against the "
                              "lightest and darkest pixels it overlaps.",
                              "indeterminate (varied background)"))
                continue
        else:                               # outside the shot, or no screenshot
            bg = effective_bg(el)
            if bg is None:                  # CSS chain hit a background image
                out.append(_f("contrast", "GATE", "med", law, el, None, None, "WARN",
                              "Background image behind text — verify contrast manually "
                              "(can't be measured statically).",
                              "indeterminate background"))
                continue
        fg = C.composite(fg_raw, bg)
        req = C.required_ratio(el["fontPx"], el["bold"], level)
        ratio = C.contrast(fg, bg)
        if ratio < req:
            fix_rgb = C.nearest_passing(fg, bg, req)
            fix = (f"text colour {C.to_hex(fg)} → {C.to_hex(fix_rgb)} "
                   f"(or darken/lighten the background)") if fix_rgb else \
                  "background blocks any passing text colour — change the background"
            out.append(_f("contrast", "GATE", "high", law, el,
                          f"{ratio}:1", f"{req}:1", "FAIL", fix,
                          f"{el['fontPx']:.0f}px{' bold' if el['bold'] else ''}"))
    return out


def rule_non_text_contrast(els, ctx):
    """Controls must be distinguishable from their surroundings (≥3:1) — the
    classic 'ghost button' catcher. Applies to real controls, not text links."""
    out = []
    for el in els:
        if not el.get("interactive") or el.get("inlineInText"):
            continue
        self_bg = C.parse_color(el.get("selfBg") or "")
        has_fill = bool(self_bg and self_bg[3] >= 0.5)
        has_border = (el.get("borderWidth") or 0) >= 1 and bool(
            (bc0 := C.parse_color(el.get("borderColor") or "")) and bc0[3] >= 0.5)
        # 1.4.11 needs a visual boundary to measure. A control with no fill AND no
        # border is a text/link-style control, identified by its text — skip it
        # (measuring "0:1" on a bare <button> is a false positive, not a finding).
        if not (has_fill or has_border):
            continue
        parent_bg = effective_bg(el, skip_self=True)
        if parent_bg is None:
            continue
        best = 0.0
        if has_fill:
            # composite the fill over what's behind it — a translucent fill's
            # real contrast is the colour the eye sees, not the raw RGB.
            best = max(best, C.contrast(C.composite(self_bg, parent_bg), parent_bg))
        if has_border:
            best = max(best, C.contrast(C.composite(bc0, parent_bg), parent_bg))
        if best < C.NON_TEXT:
            out.append(_f("non-text-contrast", "GATE", "high", "1.4.11", el,
                          f"{best:.2f}:1", f"{C.NON_TEXT}:1", "FAIL",
                          "Give the control a background or border with ≥3:1 "
                          "contrast against the page (ghost buttons fail this).",
                          "control blends into its surroundings"))
    return out


def rule_target_size(els, ctx):
    level = ctx["level"]
    law = "2.5.5" if level == "AAA" else "2.5.8"
    T = 44 if level == "AAA" else 24
    out = []
    for el in els:
        if not el.get("interactive") or el.get("inlineInText"):
            continue
        w, h = el["rect"]["w"], el["rect"]["h"]
        if min(w, h) < T:
            out.append(_f("target-size", "GATE", "high", law, el,
                          f"{w}×{h}px", f"{T}×{T}px", "FAIL",
                          f"Grow the hit area to ≥{T}×{T}px (min-height/min-width "
                          f"or padding). Apple HIG: 44pt · Material: 48dp.",
                          ""))
    return out


def rule_target_spacing(els, ctx):
    out = []
    tgts = [e for e in els if e.get("interactive") and not e.get("inlineInText")]
    for a in tgts:
        if min(a["rect"]["w"], a["rect"]["h"]) >= 24:
            continue
        ax, ay = a["rect"]["x"] + a["rect"]["w"] / 2, a["rect"]["y"] + a["rect"]["h"] / 2
        crowded = False
        for b in tgts:
            if b is a:
                continue
            bx, by = b["rect"]["x"] + b["rect"]["w"] / 2, b["rect"]["y"] + b["rect"]["h"] / 2
            if math.hypot(ax - bx, ay - by) < 24:
                crowded = True
                break
        if crowded:
            out.append(_f("target-spacing", "GATE", "med", "2.5.8", a,
                          f"{a['rect']['w']}×{a['rect']['h']}px, neighbour <24px away",
                          "≥24px target or ≥24px spacing", "WARN",
                          "Enlarge to ≥24px or add spacing so 24px hit circles don't overlap.",
                          ""))
    return out


def _is_body_text(el):
    # prose only — code blocks legitimately run long, tight, and unwrapped, so
    # line-length / line-height / no-justify don't apply to them.
    return (el.get("text") and el.get("textLen", 0) >= 50 and el.get("fontPx", 16) <= 20
            and el.get("tag") not in ("pre", "code", "kbd", "samp", "tt"))


def rule_line_height(els, ctx):
    out = []
    for el in els:
        if not _is_body_text(el):
            continue
        r = el.get("lineHeightRatio")
        if r is not None and r < 1.5:
            out.append(_f("line-height", "GATE", "med", "1.4.8", el,
                          f"{r}× font size", "≥1.5×", "FAIL",
                          "Set line-height: 1.5 on body text (WCAG 1.4.8, AAA).",
                          ""))
    return out


def rule_line_length(els, ctx):
    out = []
    for el in els:
        if not _is_body_text(el) or el.get("cpl") is None:
            continue
        cpl = el["cpl"]
        if cpl > 80:
            out.append(_f("line-length", "GATE", "med", "1.4.8", el,
                          f"{cpl} chars/line", "≤80 (ideal ~66)", "FAIL",
                          "Constrain the text column to ~66ch (e.g. max-width: 66ch).",
                          LAW["measure"]))
        elif cpl < 40:
            out.append(_f("line-length", "GATE", "low", "1.4.8", el,
                          f"{cpl} chars/line", "45–75 ideal", "WARN",
                          "Column is very narrow; widen toward ~66ch.", LAW["measure"]))
    return out


def rule_no_justify(els, ctx):
    out = []
    for el in els:
        if _is_body_text(el) and el.get("textAlign") == "justify":
            out.append(_f("no-justify", "GATE", "med", "1.4.8", el,
                          "text-align: justify", "left/ragged-right", "FAIL",
                          "Use text-align: left. Justified body text opens rivers "
                          "of whitespace (WCAG 1.4.8, AAA).", ""))
    return out


# ---- SCORE rules ---------------------------------------------------------

def rule_min_font(els, ctx):
    out = []
    for el in els:
        if el.get("text") and el.get("textLen", 0) >= 20 and el["fontPx"] < 14:
            out.append(_f("min-font", "SCORE", "low", "hig", el,
                          f"{el['fontPx']:.0f}px", "≥16px body (≥14 min)", "WARN",
                          "Bump body text toward 16px for readability.", ""))
    return out


def rule_fitts(els, ctx):
    vw, vh = ctx["viewport"]["w"], ctx["viewport"]["h"]
    cx, cy = vw / 2, vh / 2
    out = []
    primaries = []
    for el in els:
        if not el.get("interactive") or el.get("inlineInText"):
            continue
        txt = (el.get("text") or "").lower()
        is_cta = any(w in txt for w in CTA_WORDS)
        if is_cta:
            primaries.append(el)
    for el in primaries:
        w = max(1, min(el["rect"]["w"], el["rect"]["h"]))
        ex = el["rect"]["x"] + el["rect"]["w"] / 2
        ey = el["rect"]["y"] + el["rect"]["h"] / 2
        D = math.hypot(ex - cx, ey - cy)
        ID = round(math.log2(D / w + 1), 2)  # index of difficulty
        small = min(el["rect"]["w"], el["rect"]["h"]) < 44
        if small or ID > 4.0:
            out.append(_f("fitts", "SCORE", "med" if small else "low", "fitts", el,
                          f"ID={ID} (size {el['rect']['w']}×{el['rect']['h']}, "
                          f"{int(D)}px from centre)", "lower is faster to hit", "WARN",
                          "Primary actions should be large and close to the user's "
                          "focus. Enlarge the target and/or move it nearer the content.",
                          "primary action"))
    return out


def rule_hick(els, ctx):
    nav = [e for e in els if e.get("interactive") and e["rect"]["y"] < 140
           and not e.get("inlineInText")]
    n = len(nav)
    out = []
    if n > 7:
        idx = round(math.log2(n + 1), 2)
        out.append(_f("hick", "SCORE", "low", "hicks", None,
                      f"{n} top-level choices (decision index log2(n+1)={idx})",
                      "fewer, grouped choices", "WARN",
                      "Group or progressively disclose navigation; decision time "
                      "grows with the number of equally-weighted options.", ""))
    return out


def rule_non_semantic(els, ctx):
    out = []
    for el in els:
        if el.get("interactive") and el["tag"] in ("div", "span") and not el.get("role"):
            out.append(_f("non-semantic-control", "SCORE", "med", "aria", el,
                          f"<{el['tag']}> used as a control", "native <button>/<a> or role+keyboard",
                          "WARN",
                          "Use a <button>/<a>, or add role, tabindex and keyboard "
                          "handlers — clickable <div>s are invisible to keyboard "
                          "and screen-reader users.", ""))
    return out


def rule_proximity(els, ctx):
    """Gestalt proximity: in a run of equally-ranked controls, uneven gaps make
    grouping ambiguous (which control pairs with which?). Equal spacing reads as
    one group; deliberate gaps read as separate groups — you should pick one.

    We look at *controls* aligned in a row/column, split a run wherever a gap is
    large enough to be a genuine separator, then flag the remaining tight runs
    whose internal gaps still vary a lot."""
    out = []
    cand = [e for e in els if e.get("interactive") and not e.get("inlineInText")]
    seen = set()
    for axis in ("x", "y"):
        cross = "y" if axis == "x" else "x"
        size = "w" if axis == "x" else "h"
        csize = "h" if axis == "x" else "w"
        buckets = {}
        for e in cand:
            r = e["rect"]
            c = round((r[cross] + r[csize] / 2) / 10) * 10
            buckets.setdefault(c, []).append(e)
        for grp in buckets.values():
            if len(grp) < 3:
                continue
            grp.sort(key=lambda e: e["rect"][axis])
            gseq = [grp[i + 1]["rect"][axis] - (grp[i]["rect"][axis] + grp[i]["rect"][size])
                    for i in range(len(grp) - 1)]
            pos = [g for g in gseq if g >= 0]
            med = statistics.median(pos) if pos else 0
            # split only where a gap is an OUTLIER vs the typical spacing — a
            # genuine section separator, not just the loose half of a rhythm.
            runs, cur = [], [grp[0]]
            for i, gap in enumerate(gseq):
                if gap < -2 or (med > 0 and gap > 4 * med and gap > 40):
                    runs.append(cur); cur = [grp[i + 1]]
                else:
                    cur.append(grp[i + 1])
            runs.append(cur)
            for run in runs:
                if len(run) < 3:
                    continue
                gaps = [b["rect"][axis] - (a["rect"][axis] + a["rect"][size])
                        for a, b in zip(run, run[1:])]
                gaps = [g for g in gaps if g >= 0]
                if len(gaps) < 2:
                    continue
                lo, hi = min(gaps), max(gaps)
                if lo >= 1 and hi >= lo * 1.8 and hi - lo >= 20:
                    key = (axis, run[0]["rect"]["x"], run[0]["rect"]["y"])
                    if key in seen:
                        continue
                    seen.add(key)
                    out.append(_f("proximity", "SCORE", "low", "proximity", run[0],
                                  f"{len(run)} controls in a {'row' if axis=='x' else 'column'}, "
                                  f"gaps {lo:.0f}–{hi:.0f}px (uneven)",
                                  "consistent spacing, or group intentionally", "WARN",
                                  "Even out the spacing, or widen only the gaps that "
                                  "separate true groups — uneven gaps make grouping ambiguous.",
                                  "ambiguous grouping"))
    return out


def rule_clicks_to_goal(els, ctx):
    """Reads a crawl result (shoot --crawl --goal). Reports the measured number
    of clicks to reach the declared goal. The '3-click rule' is a myth — we
    report interaction cost and flag only against a config-declared target."""
    crawl = ctx.get("crawl")
    if not crawl:
        return []
    if not crawl.get("reached"):
        return [_f("clicks-to-goal", "SCORE", "high", "cost", None,
                   f"goal '{crawl.get('goal')}' not reachable within depth "
                   f"{crawl.get('max_depth')}", "reachable", "WARN",
                   "The goal isn't reachable by link navigation in the crawl "
                   "budget — surface a direct path to it.",
                   "  →  ".join(crawl.get("path", [])) or "")]
    clicks = crawl.get("clicks")
    if clicks is None:
        return []
    target = ctx.get("goal_target")
    path = "  →  ".join(s.split("/")[-1] for s in crawl.get("path", []))
    if target is not None and clicks > target:
        return [_f("clicks-to-goal", "SCORE", "med", "cost", None,
                   f"{clicks} clicks to '{crawl.get('goal')}'", f"≤{target} (declared)",
                   "WARN", "Add a shortcut (e.g. a direct CTA) so the goal is "
                   "reachable in fewer steps.", path)]
    return [_f("clicks-to-goal", "SCORE", "low", "cost", None,
               f"{clicks} clicks to '{crawl.get('goal')}'",
               "lower interaction cost is better", "WARN",
               "Measured path; reduce steps where the goal is high-intent.", path)]


GATE_RULES = [rule_contrast, rule_non_text_contrast, rule_target_size,
              rule_target_spacing, rule_line_height, rule_line_length, rule_no_justify]
SCORE_RULES = [rule_min_font, rule_fitts, rule_hick, rule_non_semantic,
               rule_proximity, rule_clicks_to_goal]

# Modules that need inputs the static pass doesn't have are reported honestly so
# the scorecard never implies coverage it lacks.
NOT_RUN_BASE = {
    "visual-hierarchy": "perceptual; run `python -m tasteless.measure` for the salience heatmap",
}


def audit(data, level="AA", crawl=None, goal_target=None):
    els = data["elements"]
    img, scale = _load_shot(data)
    ctx = {"level": level, "viewport": data.get("viewport", {"w": 1440, "h": 900}),
           "crawl": crawl, "goal_target": goal_target, "img": img, "scale": scale}
    not_run = dict(NOT_RUN_BASE)
    if not crawl:
        not_run["clicks-to-goal"] = "no crawl supplied (shoot --crawl --goal ...)"
    findings = []
    for r in GATE_RULES + SCORE_RULES:
        findings.extend(r(els, ctx))
    gate_fails = [f for f in findings if f["class"] == "GATE" and f["status"] == "FAIL"]
    return {
        "url": data.get("url"),
        "level": level,
        # CSS width the element coords are in — lets the annotator scale boxes
        # onto a screenshot taken at any device pixel ratio.
        "render_css_width": ctx["viewport"].get("w", 1440),
        "elements_examined": len(els),
        "summary": {
            "gate_fail": len(gate_fails),
            "gate_warn": len([f for f in findings if f["class"] == "GATE" and f["status"] == "WARN"]),
            "score_warn": len([f for f in findings if f["class"] == "SCORE"]),
            "gates_clean": len(gate_fails) == 0,
        },
        "findings": findings,
        "modules_not_run": not_run,
    }


def print_report(rep):
    s = rep["summary"]
    print(f"\n  TASTELESS — {rep['url']}  ({rep['level']}, {rep['elements_examined']} elements)")
    print("  " + "─" * 64)
    by_status = {"FAIL": [], "WARN": []}
    for f in rep["findings"]:
        by_status.setdefault(f["status"], []).append(f)
    for st, marker in (("FAIL", "✗"), ("WARN", "▲")):
        for f in by_status.get(st, []):
            el = f.get("element") or {}
            who = (el.get("text") or f"<{el.get('tag','?')}>")[:42] if el else "(page)"
            print(f"  {marker} [{f['rule']}] {who}")
            print(f"      measured {f['measured']}  vs  {f['threshold']}")
            print(f"      fix: {f['fix']}")
            print(f"      {f['citation']}")
    print("  " + "─" * 64)
    verdict = "GATES CLEAN ✓" if s["gates_clean"] else f"{s['gate_fail']} GATE violation(s) ✗"
    print(f"  {verdict}   ({s['gate_warn']} gate warnings, {s['score_warn']} score notes)")
    nr = rep.get("modules_not_run") or {}
    if nr:
        print(f"  not run: {', '.join(nr)}\n")
    else:
        print()


def main():
    ap = argparse.ArgumentParser(description="Audit a rendered UI against the laws of UX.")
    ap.add_argument("json", help="elements JSON from tasteless.shoot")
    ap.add_argument("--level", choices=["AA", "AAA"], default="AA")
    ap.add_argument("--json", dest="out_json", help="write the scorecard JSON here")
    ap.add_argument("--crawl", help="crawl JSON from `shoot --crawl` (for clicks-to-goal)")
    ap.add_argument("--goal-target", type=int, help="declared max acceptable clicks to goal")
    a = ap.parse_args()
    data = json.loads(Path(a.json).read_text())
    crawl = None
    crawl_path = a.crawl
    if not crawl_path:  # auto-detect a sibling <base>.crawl.json
        sib = Path(a.json).with_suffix("").with_suffix(".crawl.json")
        if sib.exists():
            crawl_path = str(sib)
    if crawl_path and Path(crawl_path).exists():
        crawl = json.loads(Path(crawl_path).read_text())
    rep = audit(data, a.level, crawl=crawl, goal_target=a.goal_target)
    print_report(rep)
    if a.out_json:
        Path(a.out_json).write_text(json.dumps(rep, indent=2))
        print(f"  scorecard → {a.out_json}")


if __name__ == "__main__":
    main()
