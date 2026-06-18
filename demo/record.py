"""Record the 'watch the agent fix it' clips — natively, with Playwright video +
ffmpeg. No screen capture, no manual step.

  python demo/record.py

Produces, in demo/artifacts/:
  fix_landing.mp4 / .gif   — looks fine → cited FAIL badges snap on → fixed
  hierarchy.mp4  / .gif    — the UI → DINOv2 salience overlay (eye trapped on the
                             photo) → rebalanced → re-measured overlay
"""
import base64
import json
import os
import shutil
import subprocess
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent
ART = ROOT / "artifacts"
FFMPEG = shutil.which("ffmpeg") or str(
    Path.home() / "Library/Caches/ms-playwright/ffmpeg-1011/ffmpeg-mac")
if not (shutil.which("ffmpeg") or os.path.exists(FFMPEG)):
    raise SystemExit("ffmpeg not found — install it (brew install ffmpeg) before recording.")


def url(rel):
    return (ROOT / rel).resolve().as_uri()


def boxes_from_score(score_path):
    rep = json.loads(Path(score_path).read_text())
    groups = {}
    for f in rep["findings"]:
        el = f.get("element")
        if not el or not el.get("rect") or f["status"] != "FAIL":
            continue
        r = el["rect"]; k = (r["x"], r["y"], r["w"], r["h"])
        groups.setdefault(k, []).append(f["rule"])
    return [{"x": x, "y": y, "w": w, "h": h, "label": " · ".join(dict.fromkeys(rs))[:46]}
            for (x, y, w, h), rs in groups.items()]


ADD_BADGES = r"""
(batch) => {
  let c = document.getElementById('tl-overlay');
  if (!c) { c = document.createElement('div'); c.id='tl-overlay';
    c.style.cssText='position:absolute;left:0;top:0;width:100%;height:100%;pointer-events:none;z-index:99999';
    document.body.appendChild(c); }
  for (const b of batch) {
    const d=document.createElement('div');
    d.style.cssText=`position:absolute;left:${b.x}px;top:${b.y}px;width:${b.w}px;height:${b.h}px;`+
      `border:3px solid #dc2626;background:rgba(220,38,38,.12);box-sizing:border-box`;
    const t=document.createElement('div'); t.textContent=b.label;
    t.style.cssText=`position:absolute;left:${b.x}px;top:${Math.max(0,b.y-21)}px;background:#dc2626;`+
      `color:#fff;font:600 12px -apple-system,sans-serif;padding:2px 6px;white-space:nowrap;border-radius:2px`;
    c.appendChild(d); c.appendChild(t);
  }
}
"""

FADE_IMG = r"""
(dataurl) => {
  const i=document.createElement('img'); i.src=dataurl;
  i.style.cssText='position:fixed;inset:0;width:100vw;height:100vh;object-fit:cover;z-index:99999;opacity:0;transition:opacity .55s ease';
  document.body.appendChild(i); requestAnimationFrame(()=>{ i.style.opacity='0.9'; });
}
"""


def _save_video(page, ctx, out_stem):
    path = page.video.path()
    ctx.close()  # finalizes the webm
    webm = ART / f"{out_stem}.webm"
    shutil.move(path, webm)
    return webm


def convert(webm, stem, width=1200):
    mp4 = ART / f"{stem}.mp4"
    gif = ART / f"{stem}.gif"
    subprocess.run([FFMPEG, "-y", "-i", str(webm), "-movflags", "+faststart",
                    "-pix_fmt", "yuv420p", "-vf", f"scale={width}:-2", str(mp4)],
                   check=True, capture_output=True)
    subprocess.run([FFMPEG, "-y", "-i", str(webm),
                    "-vf", f"fps=15,scale={width//2}:-1:flags=lanczos", str(gif)],
                   check=True, capture_output=True)
    webm.unlink(missing_ok=True)
    return mp4, gif


def record_wcag(broken, fixed, score, stem, vw=1440, vh=900):
    boxes = boxes_from_score(score)
    with sync_playwright() as p:
        b = p.chromium.launch()
        ctx = b.new_context(viewport={"width": vw, "height": vh},
                            record_video_dir=str(ART), record_video_size={"width": vw, "height": vh})
        pg = ctx.new_page()
        pg.goto(url(broken), wait_until="load"); pg.wait_for_timeout(1400)
        # badges snap on in batches
        for i in range(0, len(boxes), max(1, len(boxes)//6 or 1)):
            pg.evaluate(ADD_BADGES, boxes[i:i + max(1, len(boxes)//6 or 1)])
            pg.wait_for_timeout(260)
        pg.wait_for_timeout(1500)
        pg.goto(url(fixed), wait_until="load"); pg.wait_for_timeout(1900)
        webm = _save_video(pg, ctx, stem); b.close()
    return convert(webm, stem)


def record_hierarchy(broken, fixed, before_heat, after_heat, stem, vw=1440, vh=900):
    def datauri(p):
        return "data:image/png;base64," + base64.b64encode(Path(p).read_bytes()).decode()
    bh, ah = datauri(before_heat), datauri(after_heat)
    with sync_playwright() as p:
        b = p.chromium.launch()
        ctx = b.new_context(viewport={"width": vw, "height": vh},
                            record_video_dir=str(ART), record_video_size={"width": vw, "height": vh})
        pg = ctx.new_page()
        pg.goto(url(broken), wait_until="load"); pg.wait_for_timeout(1300)
        pg.evaluate(FADE_IMG, bh); pg.wait_for_timeout(2100)
        pg.goto(url(fixed), wait_until="load"); pg.wait_for_timeout(1200)
        pg.evaluate(FADE_IMG, ah); pg.wait_for_timeout(2100)
        webm = _save_video(pg, ctx, stem); b.close()
    return convert(webm, stem)


def record_scroll(page_rel, stem, vw=1280, vh=800, steps=240, dwell=65):
    """Smooth top-to-bottom scroll of the stitched showcase page → one sizzle reel
    (the inline clips autoplay as it passes them)."""
    with sync_playwright() as p:
        b = p.chromium.launch()
        ctx = b.new_context(viewport={"width": vw, "height": vh},
                            record_video_dir=str(ART), record_video_size={"width": vw, "height": vh})
        pg = ctx.new_page()
        pg.goto(url(page_rel), wait_until="load"); pg.wait_for_timeout(2200)
        total = pg.evaluate("document.body.scrollHeight - window.innerHeight")
        for i in range(steps + 1):
            pg.evaluate(f"window.scrollTo(0,{int(total * i / steps)})")
            pg.wait_for_timeout(dwell)
        pg.wait_for_timeout(1200)
        webm = _save_video(pg, ctx, stem); b.close()
    return convert(webm, stem, width=1100)


def main():
    print("recording WCAG fix-it-live (landing)…")
    m1, g1 = record_wcag("landing.html", "landing.fixed.html",
                         ART / "landing_before.score.json", "fix_landing")
    print(f"  → {m1.name}, {g1.name}")
    print("recording DINOv2 hierarchy loop…")
    m2, g2 = record_hierarchy("hierarchy.html", "hierarchy.fixed.html",
                              ART / "heat_hier_before.png", ART / "heat_hier_after.png",
                              "hierarchy_clip")
    print(f"  → {m2.name}, {g2.name}")
    print("recording showcase sizzle (full scroll)…")
    m3, g3 = record_scroll("showcase.html", "showcase_sizzle")
    print(f"  → {m3.name}, {g3.name}")


if __name__ == "__main__":
    main()
