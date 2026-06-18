<h1 align="center">TASTELESS</h1>
<p align="center"><em>An agent that audits your UI against the laws of UX and fixes the violations.<br>
It doesn't have taste. It has citations.</em></p>

---

## The Anti-Taste Manifesto

Design Twitter argues about taste for a living. Taste is unfalsifiable. So this
is the opposite.

Every change TASTELESS makes is backed by a published rule and a number you
can't argue with:

- **"Beautiful" is an opinion. 4.5:1 contrast is [WCAG 1.4.3](https://www.w3.org/WAI/WCAG21/Understanding/contrast-minimum.html).**
- A 24px tap target is [WCAG 2.5.8](https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum.html). 44pt is the [Apple HIG](https://developer.apple.com/design/human-interface-guidelines/accessibility). 48dp is [Material](https://m2.material.io/design/usability/accessibility.html#layout-typography).
- 45–75 characters per line is [Bringhurst](https://practicaltypography.com/line-length.html). Justified body text and sub-1.5 line-height fail [WCAG 1.4.8](https://www.w3.org/WAI/WCAG21/Understanding/visual-presentation.html).
- A small, far-away primary action costs you [Fitts's Law](https://lawsofux.com/fittss-law/). Nine equal-weight nav links cost you [Hick's Law](https://lawsofux.com/hicks-law/).

TASTELESS measures these on your **rendered** UI — the actual pixels, not the
source — and **rewrites the CSS until every gate passes.** Each fix names the
rule it satisfies and links the source.

> *Pretty is negotiable. The laws are not.*

## What it is (and isn't)

It **edits your real stylesheet/markup**, re-renders, re-measures, and loops
until clean. It is **not** an accessibility overlay (those got accessiBe a
[$1M FTC fine](https://www.ftc.gov/news-events/news/press-releases/2025/04/ftc-approves-final-order-requiring-accessibe-pay-1-million)) and it makes **no "WCAG/ADA compliant" claim** — it fixes
*specific, cited violations*, which is a different and honest thing.

Of everything it checks, exactly **one** rule is perceptual: **visual
hierarchy**. For that it *shows* you a bottom-up salience heatmap (DINOv2 with
registers — see [*Vision Transformers Need Registers*](https://arxiv.org/abs/2309.16588)). It's a proxy for where the
layout pulls the eye, **not** a prediction of human gaze — it ignores reading
order and your top-down goals on purpose, so you can compare the pull you
*built* against the priority you *declared*. The gap is the bug. Everything else
is a measured value against a published threshold.

## The rules

| Class | Rule | Threshold | Source |
|---|---|---|---|
| **GATE** | Text contrast | 4.5:1 / 3:1 (AA), 7:1 / 4.5:1 (AAA) | WCAG 1.4.3 / 1.4.6 |
| **GATE** | Non-text / control contrast | 3:1 | WCAG 1.4.11 |
| **GATE** | Target size | 24px (AA) / 44px (AAA) | WCAG 2.5.8 / 2.5.5, HIG, Material |
| **GATE** | Target spacing | 24px hit circles don't overlap | WCAG 2.5.8 |
| **GATE** | Line-height (body) | ≥ 1.5× | WCAG 1.4.8 |
| **GATE** | Line length | ≤ 80, ideal ~66 chars | WCAG 1.4.8 / Bringhurst |
| **GATE** | No justified body | ragged-right | WCAG 1.4.8 |
| **SCORE** | Fitts cost (primary action) | small + far = expensive | Fitts's Law |
| **SCORE** | Hick overload (nav) | log2(n+1) | Hick's Law |
| **SCORE** | Clicks-to-goal | measured via crawl vs declared target | Interaction Cost (NN/g) |
| **SCORE** | Proximity (ambiguous grouping) | uneven gaps in a control run | Law of Proximity |
| **SCORE** | Min body font | ≥ 16px (≥14 floor) | HIG / readability |
| **SCORE** | Non-semantic control | native element / role+keyboard | WAI-ARIA |
| **HEURISTIC** | Visual hierarchy | shown, not gated | DINOv2 salience |

*Deliberately **not** gated: Miller's 7±2 and the "3-click rule" — both
[debunked](https://www.nngroup.com/articles/3-click-rule/) as hard limits.*

## Install

As a Claude Code skill:
```
/plugin marketplace add <your-org>/tasteless
/plugin install tasteless
```

Then, in the repo (the engine needs Python):
```
pip install -e .
python -m playwright install chromium
```

## Use it standalone

```bash
# render + extract
python -m tasteless.shoot --url http://localhost:3000 --out /tmp/tl

# cited scorecard
python -m tasteless.audit /tmp/tl.json --level AA --json /tmp/tl.score.json

# the one perceptual module (shown, not gated)
python -m tasteless.measure /tmp/tl.png --axis rows
```

Or just say *"run tasteless on my dev server"* to Claude Code and it'll run the
audit → fix → re-measure loop for you (see the skill).

## See it work

**[`demo/showcase.html`](demo/showcase.html) is the whole thing on one page** —
both videos, all six before/after receipts, the DINOv2 hierarchy loop, and the
cited rules. It is itself audited by TASTELESS and passes: **0 GATE violations**.
The demo that demos the tool survives the tool. The launch hero is a before/after
still — `demo/artifacts/hero_landing.png` (33→0) and `hero_dashboard.png` (64→0) —
and the loop clips are `fix_landing.mp4` and `hierarchy_clip.mp4`.

`demo/` ships six deliberately-broken-but-good-looking surfaces and their fixed
counterparts. `python demo/build_artifacts.py` renders each, audits it, stamps
the violations onto the screenshot, and writes a BEFORE→AFTER composite to
`demo/artifacts/`. Same taste in, fixed function out:

| Surface | GATE violations | After |
|---|---|---|
| Landing page | 33 | **0** |
| Pricing page | 38 | **0** |
| Sign-in form | 11 | **0** |
| Dashboard / table | 64 | **0** |
| Settings | 15 | **0** |
| Checkout (clicks-to-goal) | 4 clicks | **1 click** |

Each `demo/artifacts/<surface>.png` is the shareable proof: the broken UI with
red, cited FAIL badges on every offender, beside the same UI with zero. The
annotated frame is the demo — "this looks fine" → badges snap on → fixed.

### The visual-hierarchy loop (DINOv2 — not a WCAG bot)

The gates are table stakes. The perceptual module is the differentiator.
`python demo/build_hierarchy.py` runs the salience loop on a hero whose
decorative photo hijacks the eye from the message:

```
intent: the headline + CTA lead; the photo is secondary
BEFORE  visual pull on the photo half: 71%   peak 100% (pinned to the photo)
AFTER   visual pull on the photo half: 51%   peak  76%   centroid → centre
```

It will never make flat text out-pull a photograph — it's not pretending to be
eye-tracking. It measures bottom-up pull and shows the photo no longer dominates
the fold. Artifact: `demo/artifacts/hierarchy.png` (the two heatmaps + metrics).

### Watch it, literally

`python demo/record.py` records real browser sessions (Playwright video → ffmpeg)
to `demo/artifacts/`:

- `fix_landing.mp4` / `.gif` — the page looks fine, cited FAIL badges snap on, then it's fixed.
- `hierarchy_clip.mp4` / `.gif` — the UI, the DINOv2 salience overlay (eye trapped on the photo), the rebalance, the re-measured overlay.

## License

MIT.
