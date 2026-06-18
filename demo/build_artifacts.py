"""Build the 'watch the agent fix it' artifacts for every demo surface:
annotated BEFORE (red badges on each violation) + BEFORE→AFTER composite, plus
the clicks-to-goal crawl delta. Writes to demo/artifacts/.

  python demo/build_artifacts.py
"""
import json
from pathlib import Path

from tasteless import shoot as S
from tasteless import audit as A
from tasteless import report as R

ROOT = Path(__file__).resolve().parent
ART = ROOT / "artifacts"
ART.mkdir(exist_ok=True)


def url(rel):
    return (ROOT / rel).resolve().as_uri()


SURFACES = [
    ("landing",   "landing.html",   "landing.fixed.html",   "Landing page"),
    ("pricing",   "pricing.html",   "pricing.fixed.html",   "Pricing page"),
    ("login",     "login.html",     "login.fixed.html",     "Sign-in form"),
    ("dashboard", "dashboard.html", "dashboard.fixed.html", "Dashboard / table"),
    ("settings",  "settings.html",  "settings.fixed.html",  "Settings"),
]


def audit_to_file(png_json, level, name, suffix):
    data = json.loads(Path(png_json).read_text())
    rep = A.audit(data, level)
    p = ART / f"{name}_{suffix}.score.json"
    p.write_text(json.dumps(rep, indent=2))
    return rep, p


def main():
    rows = []
    for name, broken, fixed, title in SURFACES:
        # BEFORE
        b = S.shoot(url(broken), str(ART / f"{name}_before"), 1440, 900, full_page=True)
        brep, bscore = audit_to_file(ART / f"{name}_before.json", "AA", name, "before")
        # AFTER
        a = S.shoot(url(fixed), str(ART / f"{name}_after"), 1440, 900, full_page=True)
        arep, _ = audit_to_file(ART / f"{name}_after.json", "AA", name, "after")
        # artifacts
        annotated = R.annotate(str(ART / f"{name}_before.png"), str(bscore),
                               str(ART / f"{name}_before_annotated.png"))
        R.compose(annotated, str(ART / f"{name}_after.png"), str(ART / f"{name}.png"),
                  brep["summary"]["gate_fail"], arep["summary"]["gate_fail"], title)
        rows.append((title, brep["summary"]["gate_fail"], arep["summary"]["gate_fail"]))
        print(f"  {title:20} {brep['summary']['gate_fail']:>3} → {arep['summary']['gate_fail']:>2}"
              f"   artifact: demo/artifacts/{name}.png")

    # clicks-to-goal flow
    print("\n  clicks-to-goal (crawl):")
    cb = S.crawl(url("flow/index.html"), "Checkout", max_depth=6)
    cf = S.crawl(url("flow/index.fixed.html"), "Checkout", max_depth=6)
    (ART / "flow.crawl.json").write_text(json.dumps({"before": cb, "after": cf}, indent=2))
    pb = " → ".join(s.split("/")[-1] for s in cb["path"])
    pf = " → ".join(s.split("/")[-1] for s in cf["path"])
    print(f"    broken funnel : {cb['clicks']} clicks   ({pb})")
    print(f"    with shortcut : {cf['clicks']} clicks   ({pf})")
    rows.append(("Checkout (clicks)", cb["clicks"], cf["clicks"]))

    print("\n  ── SUMMARY (before → after) ──")
    for title, bn, an in rows:
        print(f"    {title:22} {bn:>3} → {an:>2}")


if __name__ == "__main__":
    main()
