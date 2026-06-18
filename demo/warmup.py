"""Week-1 warm-up content: run the audit (read-only) on real public landing
pages and stamp the cited findings onto each — "your favorite site fails the
laws of UX." Honest framing: these are specific cited violations on the rendered
hero fold, not a "non-compliant" claim.

  python demo/warmup.py

Writes demo/artifacts/warmup_<site>.png + prints the real findings.
"""
import json
import sys
from collections import Counter
from pathlib import Path

from tasteless import shoot as S
from tasteless import audit as A
from tasteless import report as R

ART = Path(__file__).resolve().parent / "artifacts"
ART.mkdir(exist_ok=True)

SITES = [
    ("stripe", "https://stripe.com"),
    ("linear", "https://linear.app"),
    ("vercel", "https://vercel.com"),
    ("notion", "https://www.notion.com"),
    ("openai", "https://openai.com"),
]


def run(name, url):
    base = ART / f"warmup_{name}"
    try:
        # full_page so contrast samples the real background of EVERY element,
        # not just the top fold (below-fold elements otherwise default to white)
        S.shoot(url, str(base), 1440, 900, full_page=True)
    except Exception as e:
        print(f"  {name:8} FAILED to load: {str(e)[:80]}")
        return None
    data = json.loads(base.with_suffix(".json").read_text())
    rep = A.audit(data, "AA")
    score = ART / f"warmup_{name}.score.json"
    score.write_text(json.dumps(rep))
    R.annotate(str(base.with_suffix(".png")), str(score), str(ART / f"warmup_{name}.png"))
    fails = [f for f in rep["findings"] if f["status"] == "FAIL"]
    by_rule = Counter(f["rule"] for f in fails)
    print(f"  {name:8} {rep['summary']['gate_fail']:>3} GATE fails  "
          f"({', '.join(f'{k}×{v}' for k, v in by_rule.most_common())})")
    # one concrete, citable example per top rule
    seen = set()
    for f in sorted(fails, key=lambda f: f["severity"] != "high"):
        if f["rule"] in seen:
            continue
        seen.add(f["rule"])
        el = f.get("element") or {}
        who = (el.get("text") or f"<{el.get('tag')}>")[:30]
        print(f"             · [{f['rule']}] '{who}'  {f['measured']} vs {f['threshold']}")
        if len(seen) >= 3:
            break
    return rep["summary"]["gate_fail"]


def main():
    only = sys.argv[1:] or None
    print("warm-up audits (real public hero folds, AA):")
    for name, url in SITES:
        if only and name not in only:
            continue
        run(name, url)
    print("\n  stills → demo/artifacts/warmup_<site>.png  (honest framing: cited "
          "findings on the rendered fold, NOT a compliance claim)")


if __name__ == "__main__":
    main()
