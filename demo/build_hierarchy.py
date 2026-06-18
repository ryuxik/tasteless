"""The DINOv2 visual-hierarchy loop, demonstrated.

Declared intent: the headline + CTA lead; the photo is decorative/secondary.
We render before & after, measure bottom-up salience with DINOv2 (axis=cols, the
left content column vs the right photo), and show the share of visual pull on the
photo half collapsing — the perceptual fix, MEASURED. This module is shown, not
gated: it reports the gap between measured pull and declared intent.

  python demo/build_hierarchy.py
"""
import json
from pathlib import Path

from tasteless import shoot as S
from tasteless import measure as M
from tasteless import report as R

ROOT = Path(__file__).resolve().parent
ART = ROOT / "artifacts"
ART.mkdir(exist_ok=True)


def url(rel):
    return (ROOT / rel).resolve().as_uri()


def right_share(bands):
    """Fraction of visual pull in the right half (cols bands 4..7) — where the
    decorative photo lives."""
    return round(sum(bands[4:]) / (sum(bands) or 1), 3)


def lines(tag, r):
    rs = right_share(r["bands"])
    side = "right (photo)" if r["peak_pct"] >= 55 else \
           "left (content)" if r["peak_pct"] <= 45 else "centre"
    return [
        f"pull on photo half: {rs*100:.0f}%",
        f"salience peak: {r['peak_pct']:.0f}% — {side}",
    ]


def main():
    out = {}
    for tag, page in (("before", "hierarchy.html"), ("after", "hierarchy.fixed.html")):
        S.shoot(url(page), str(ART / f"hier_{tag}"), 1440, 900)
        r = M.measure(str(ART / f"hier_{tag}.png"), "cols")
        out[tag] = r
        # measure writes heat_<stem>.png next to the image
        print(f"  {tag:6} pull-on-photo-half={right_share(r['bands'])*100:.0f}%  "
              f"peak={r['peak_pct']:.0f}%  centroid={r['centroid_pct']:.0f}%")

    bhe = ART / "heat_hier_before.png"
    ahe = ART / "heat_hier_after.png"
    R.compose_hier(str(bhe), str(ahe), str(ART / "hierarchy.png"),
                   ["intent: content leads, photo secondary"] + lines("before", out["before"]),
                   ["intent: content leads, photo secondary"] + lines("after", out["after"]),
                   "Visual hierarchy — DINOv2 salience loop")
    (ART / "hierarchy.measure.json").write_text(json.dumps(out, indent=2))
    rb, ra = right_share(out["before"]["bands"]), right_share(out["after"]["bands"])
    print(f"\n  VERDICT: visual pull trapped on the decorative photo "
          f"{rb*100:.0f}% → {ra*100:.0f}%  (intent: photo is secondary)")
    print(f"  artifact: demo/artifacts/hierarchy.png")


if __name__ == "__main__":
    main()
