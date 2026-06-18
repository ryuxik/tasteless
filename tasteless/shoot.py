"""Render a URL and extract exactly what the laws need to be checked: a
screenshot (for the perceptual hierarchy module) plus a per-element record of
geometry + computed style + the background colour chain behind every piece of
text.

  python -m tasteless.shoot --url http://localhost:3000 --out /tmp/shot
  python -m tasteless.shoot --url file:///abs/path/page.html --out /tmp/shot \
      --width 1440 --height 900

Writes <out>.png and <out>.json. The JSON is the input to `tasteless.audit`.

This measures the RENDER, not the source — the same pixels a human gets. That's
the difference between this and a source-code linter.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

# The collector runs in the page. For every element it returns geometry, the
# computed styles the rules care about, whether it's an interactive target, the
# background-colour chain (self -> root) so Python can flatten it the same way a
# human eye does, and a font-accurate characters-per-line estimate.
COLLECT_JS = r"""
() => {
  const vw = window.innerWidth, vh = window.innerHeight;
  const cs = el => getComputedStyle(el);
  const interactiveTags = new Set(['A','BUTTON','INPUT','SELECT','TEXTAREA','SUMMARY']);
  const interactiveRoles = new Set(['button','link','menuitem','menuitemcheckbox',
    'menuitemradio','tab','checkbox','radio','switch','option','slider']);
  const isInteractive = el => {
    const r = (el.getAttribute('role')||'').toLowerCase();
    if (interactiveTags.has(el.tagName)) {
      if (el.tagName==='A') return el.hasAttribute('href');
      if (el.tagName==='INPUT') return el.type!=='hidden';
      return true;
    }
    if (interactiveRoles.has(r)) return true;
    if (el.hasAttribute('onclick')) return true;
    const ti = el.getAttribute('tabindex');
    if (ti!==null && parseInt(ti,10) >= 0) return true;
    return false;
  };
  // average glyph advance for an element's own font, via canvas
  const cv = document.createElement('canvas');
  const ctx = cv.getContext('2d');
  const avgGlyph = (style, sample) => {
    ctx.font = `${style.fontStyle} ${style.fontWeight} ${style.fontSize} ${style.fontFamily}`;
    const s = (sample && sample.length>=20) ? sample : 'abcdefghijklmnopqrstuvwxyz ETAOIN shrdlu,.';
    return ctx.measureText(s).width / s.length;
  };
  // direct (own) text of an element, ignoring descendants
  const ownText = el => {
    let t = '';
    for (const n of el.childNodes) if (n.nodeType===3) t += n.textContent;
    return t.replace(/\s+/g,' ').trim();
  };
  const bgChain = el => {
    const chain = []; let cur = el; let bgImage = false;
    while (cur && cur.nodeType===1) {
      const s = cs(cur);
      if (s.backgroundImage && s.backgroundImage!=='none') bgImage = true;
      const bg = s.backgroundColor;
      if (bg && bg!=='rgba(0, 0, 0, 0)' && bg!=='transparent') chain.push(bg);
      cur = cur.parentElement;
    }
    return {chain, bgImage};
  };

  const out = [];
  const all = document.body.querySelectorAll('*');
  let idx = 0;
  for (const el of all) {
    let rect;
    try { rect = el.getBoundingClientRect(); } catch(e) { continue; }
    if (rect.width<=0 || rect.height<=0) continue;
    const s = cs(el);
    if (s.display==='none' || s.visibility==='hidden' || parseFloat(s.opacity)===0) continue;
    // collect the whole document (we shoot at scroll 0, so rects are also
    // document coords). Annotation must use a --full-page screenshot to align.
    if (rect.bottom < -50) continue;

    const text = ownText(el);
    const inter = isInteractive(el);
    if (!text && !inter) continue;  // only elements the rules can speak about

    const fontPx = parseFloat(s.fontSize) || 16;
    const lhRaw = s.lineHeight;
    const lh = lhRaw==='normal' ? null : (parseFloat(lhRaw)||null);
    const padL = parseFloat(s.paddingLeft)||0, padR = parseFloat(s.paddingRight)||0;
    const contentW = Math.max(0, rect.width - padL - padR);
    let cpl = null;
    if (text) {
      const g = avgGlyph(s, text);
      if (g>0) cpl = Math.round(contentW / g);
    }
    const {chain, bgImage} = bgChain(el);

    out.push({
      i: idx++,
      tag: el.tagName.toLowerCase(),
      role: (el.getAttribute('role')||'').toLowerCase() || null,
      text: text ? text.slice(0,120) : null,
      textLen: text.length,
      rect: {x:Math.round(rect.x), y:Math.round(rect.y),
             w:Math.round(rect.width), h:Math.round(rect.height)},
      interactive: inter,
      inlineInText: inter && el.tagName==='A' &&
        ['P','LI','SPAN','TD','DD','DT','BLOCKQUOTE'].includes(
          (el.parentElement||{}).tagName||''),
      color: s.color,
      fontPx: fontPx,
      bold: (parseInt(s.fontWeight,10)||400) >= 700,
      lineHeightPx: lh,
      lineHeightRatio: lh ? +(lh/fontPx).toFixed(2) : null,
      textAlign: s.textAlign,
      cursor: s.cursor,
      cpl: cpl,
      selfBg: s.backgroundColor,
      borderColor: s.borderTopColor,
      borderWidth: parseFloat(s.borderTopWidth)||0,
      bgChain: chain,
      bgImage: bgImage,
    });
  }
  return {viewport:{w:vw,h:vh}, count:out.length, elements:out};
}
"""


def shoot(url: str, out: str, width: int, height: int,
          full_page: bool = False, mobile: bool = False) -> dict:
    from playwright.sync_api import sync_playwright

    out_png = Path(out).with_suffix(".png")
    out_json = Path(out).with_suffix(".json")
    out_png.parent.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(
            viewport={"width": width, "height": height},
            device_scale_factor=2 if mobile else 1,
            is_mobile=mobile,
        )
        page = ctx.new_page()
        page.goto(url, wait_until="load", timeout=30000)
        try:
            page.wait_for_load_state("networkidle", timeout=4000)
        except Exception:
            pass  # networkidle is best-effort; static pages never go idle-event
        page.screenshot(path=str(out_png), full_page=full_page)
        data = page.evaluate(COLLECT_JS)
        browser.close()

    data["url"] = url
    data["screenshot"] = str(out_png)
    data["request"] = {"width": width, "height": height,
                       "full_page": full_page, "mobile": mobile}
    out_json.write_text(json.dumps(data, indent=2))
    return data


# Per-page extraction for the crawler: the arrival signals (title + h1s) and the
# same-page outbound links.
PAGE_JS = r"""
() => ({
  title: document.title || '',
  h1s: Array.from(document.querySelectorAll('h1,h2,[role=heading]')).map(h=>h.innerText.trim()),
  links: Array.from(document.querySelectorAll('a[href]')).map(a=>a.getAttribute('href')),
})
"""


def _same_origin(url, start):
    from urllib.parse import urlparse
    pu, ps = urlparse(url), urlparse(start)
    if pu.scheme != ps.scheme:
        return False
    if pu.scheme in ("http", "https"):
        return pu.netloc == ps.netloc
    if pu.scheme == "file":  # stay within the start file's directory
        base = ps.path.rsplit("/", 1)[0] + "/"  # trailing slash: don't match sibling-prefix dirs
        return pu.path.startswith(base)
    return False


def crawl(start: str, goal: str, max_depth: int = 5, max_pages: int = 60) -> dict:
    """BFS over same-origin link navigation to find the shortest click-depth to a
    page whose title/heading matches `goal`. Link-following only (deterministic);
    button/JS flows are out of scope and reported as unreached."""
    from collections import deque
    from urllib.parse import urljoin, urldefrag
    from playwright.sync_api import sync_playwright

    goal_l = goal.lower()
    visited = {start}
    result = {"goal": goal, "start": start, "max_depth": max_depth,
              "reached": False, "clicks": None, "path": [], "pages_visited": 0}
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_context().new_page()
        q = deque([(start, [start])])
        while q and result["pages_visited"] < max_pages:
            url, path = q.popleft()
            depth = len(path) - 1
            if depth > max_depth:
                continue
            try:
                page.goto(url, wait_until="load", timeout=15000)
            except Exception:
                continue
            result["pages_visited"] += 1
            info = page.evaluate(PAGE_JS)
            arrived = goal_l in (info["title"] + " " + " ".join(info["h1s"])).lower()
            if arrived and depth >= 1:
                result.update(reached=True, clicks=depth, path=path)
                break
            for href in info["links"]:
                if not href or href.startswith(("#", "javascript:", "mailto:", "tel:")):
                    continue
                nxt = urldefrag(urljoin(url, href))[0]
                if nxt not in visited and _same_origin(nxt, start):
                    visited.add(nxt)
                    q.append((nxt, path + [nxt]))
        browser.close()
    return result


def main():
    ap = argparse.ArgumentParser(description="Render a UI and extract the facts the laws need.")
    ap.add_argument("--url", required=True, help="http(s):// or file:// URL")
    ap.add_argument("--out", default="/tmp/tasteless_shot", help="output basename (.png/.json)")
    ap.add_argument("--width", type=int, default=1440)
    ap.add_argument("--height", type=int, default=900)
    ap.add_argument("--full-page", action="store_true")
    ap.add_argument("--mobile", action="store_true", help="375x812-ish mobile context")
    ap.add_argument("--crawl", action="store_true", help="also crawl for clicks-to-goal")
    ap.add_argument("--goal", help="goal page title/heading text (with --crawl)")
    ap.add_argument("--max-depth", type=int, default=5)
    a = ap.parse_args()
    if a.mobile:
        a.width, a.height = 390, 844
    d = shoot(a.url, a.out, a.width, a.height, a.full_page, a.mobile)
    print(f"shot {d['url']}  →  {d['count']} elements")
    print(f"  screenshot {Path(a.out).with_suffix('.png')}")
    print(f"  elements   {Path(a.out).with_suffix('.json')}")
    if a.crawl:
        if not a.goal:
            ap.error("--crawl requires --goal")
        cr = crawl(a.url, a.goal, a.max_depth)
        out_crawl = Path(a.out).with_suffix("").with_suffix(".crawl.json")
        out_crawl.write_text(json.dumps(cr, indent=2))
        status = (f"{cr['clicks']} clicks via {' → '.join(s.split('/')[-1] for s in cr['path'])}"
                  if cr["reached"] else f"NOT reached (visited {cr['pages_visited']} pages)")
        print(f"  crawl → goal '{a.goal}': {status}")
        print(f"  crawl json {out_crawl}")


if __name__ == "__main__":
    main()
