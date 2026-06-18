---
name: tasteless
description: >
  Audit any rendered web UI against the measurable laws of UX — WCAG contrast,
  target size (Fitts/HIG/Material), line length, line-height, justified text,
  Hick's-law overload, non-semantic controls — and AUTO-FIX the violations by
  editing the real CSS/markup in a loop until every gate passes. Each fix is
  cited to its rule. Use for "make this UI functional", "fix the design", "run
  the laws on my UI", "audit my page", "is this accessible/usable", or any
  "tasteless" request. It doesn't have taste; it has citations.
---

# TASTELESS — the laws of UX, measured and fixed

You audit the **rendered** UI (the pixels a human gets), not the source. Every
change you make is backed by a published threshold and a number — never taste,
never vibes. You edit the user's **real stylesheet/markup**; you never inject an
overlay and you never claim "WCAG/ADA compliant" (you fix *specific cited
violations*).

## Setup (first run only — bootstrap the engine before auditing)
TASTELESS is this skill plus a small Python engine. `/plugin install` ships the
skill, not the engine, so on the FIRST run make the engine importable; if it
isn't, install it once:
```
python -c "import tasteless" 2>/dev/null \
  || pip install "git+https://github.com/ryuxik/tasteless.git"
python -m playwright install chromium     # one-time headless-browser download
```
(From a clone, `./setup.sh` — or `pip install -e .` — does the same; it pulls
playwright + torch/timm + opencv.) Once `import tasteless` succeeds, run the loop.

## The loop

**0. Get the target.** A running dev server URL (e.g. `http://localhost:3000`)
or a `file://` path. Read `tasteless.config.yaml` if present for the conformance
level (AA/AAA), declared hierarchy, and any rule overrides.

**1. Shoot.** Render and extract geometry + computed styles:
```
python -m tasteless.shoot --url <URL> --out /tmp/tl
```
Add `--mobile` to also check the phone viewport (target-size matters most there).

**2. Audit.** Produce the cited scorecard:
```
python -m tasteless.audit /tmp/tl.json --level AA --json /tmp/tl.score.json
```
Read it. Each finding has `rule`, `measured`, `threshold`, `fix`, `citation`,
`class` (GATE / SCORE), `severity`, and the offending `element` (tag + text +
rect). The summary's `gates_clean` is your exit condition.

**3. Hierarchy (perceptual — shown, not gated).** Optionally measure where the
layout pulls the eye and compare to the intent declared in config:
```
python -m tasteless.measure /tmp/tl.png --axis rows --json /tmp/tl.hier.json
```
Report the heatmap + the measured-vs-intended gap. Do **not** auto-force layout
changes from this; surface it as a recommendation.

**4. Fix the GATE violations.** For each `class: GATE`, `status: FAIL`, in
severity order (high → low), edit the user's **real source** with the cited fix:
- `contrast` → change the text colour (or background) to the suggested hex.
  Prefer adjusting the design token, not a one-off override.
- `non-text-contrast` → give the control a fill or border with ≥3:1 vs the page
  (the ghost-button fix).
- `target-size` → grow the hit area to ≥24px (AA) / 44px (AAA) via min-size or
  padding.
- `line-height` → `1.5` on body blocks. `line-length` → constrain to ~66ch.
  `no-justify` → `text-align: left`.
Make minimal, token-level edits. Do not restyle for taste — fix the violation
and nothing else.

**5. Re-measure & verify no regression.** Re-run shoot + audit. Confirm
`gate_fail` went **down** and the screenshot didn't break layout (compare
`/tmp/tl.png` before/after — nothing overlapping, clipped, or reflowed badly).
If a fix caused a new violation, address it before continuing.

**6. Recurse & converge.** Repeat 1–5 until `gates_clean: true`. Then present the
remaining **SCORE** notes (Fitts on the primary CTA, Hick overload, non-semantic
controls, min-font) as recommendations for the human to decide — these are
measured costs, not pass/fail gates, so you advise, you don't force.

## Reporting
Summarize as a before→after table of GATE counts, and list each fix with its
citation. Quote the laws, not opinions. Never report a vanity "score %"; report
`gate_fail: N → 0` and the cited SCORE recommendations that remain.

## Do not
- Inject an accessibility overlay or a `<script>` shim. Edit the source.
- Claim the page is "compliant." You fixed N cited violations; say exactly that.
- Gate on debunked rules (the "3-click rule", Miller's 7±2). They are advisory
  at most.
- Optimize a metric at the expense of the human-visible result. If a fix passes
  the check but looks broken, it's not a fix.
