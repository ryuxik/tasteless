"""The ONE perceptual module — surfaced, never gated.

Computes an unsupervised visual-salience map of a UI screenshot with DINOv2 (the
`reg4` registers variant, so the map is free of the high-norm background
artifacts that plague raw ViT attention — "Vision Transformers Need Registers",
arXiv:2309.16588). Patch tokens' cosine similarity to the CLS token gives a
label-free map of where the layout PULLS the eye before you read a word.

This is a proxy for visual pull, NOT a prediction of human gaze: it ignores
reading order, the top-left bias, and your top-down goals on purpose. Use it to
compare the pull you BUILT against the priority you DECLARED. The gap is the bug.

  python -m tasteless.measure shot.png --axis rows --json /tmp/hier.json
  python -m tasteless.measure shot.png --crop 0,0,1440,120   # a single unit
"""
from __future__ import annotations

import argparse
import functools
import json
from pathlib import Path

import cv2
import numpy as np

MEAN = np.array([0.485, 0.456, 0.406], np.float32)
STD = np.array([0.229, 0.224, 0.225], np.float32)
DINO_SIDE = 518
MODEL = "vit_small_patch14_reg4_dinov2.lvd142m"  # registers variant — no artifacts


def _device():
    import torch
    return "mps" if torch.backends.mps.is_available() else "cpu"


@functools.lru_cache(maxsize=2)
def _model(dev):
    """Load DINOv2 once per device and reuse it — model creation is expensive,
    and callers may measure many images in a loop."""
    import timm
    return timm.create_model(MODEL, pretrained=True, num_classes=0).eval().to(dev)


def saliency(rgb):
    import torch
    import torch.nn.functional as F
    dev = _device()
    dino = _model(dev)
    im = cv2.resize(rgb, (DINO_SIDE, DINO_SIDE), interpolation=cv2.INTER_AREA)
    x = ((im.astype(np.float32) / 255.0 - MEAN) / STD).transpose(2, 0, 1)
    with torch.no_grad():
        t = dino.forward_features(torch.from_numpy(x)[None].to(dev))
        pfx = getattr(dino, "num_prefix_tokens", 1)
        cls, pat = t[:, 0], t[:, pfx:]
        sal = F.cosine_similarity(pat, cls[:, None], dim=-1)[0]
        g = int(round(sal.shape[0] ** 0.5))
        return sal.reshape(g, g).cpu().numpy().astype(np.float32)


def measure(src: str, axis: str = "rows", crop=None):
    src = Path(src)
    bgr = cv2.imread(str(src))
    if bgr is None:
        raise SystemExit(f"could not read image: {src}")
    if crop:
        x, y, w, h = crop
        H0, W0 = bgr.shape[:2]
        x, y = max(0, min(x, W0 - 1)), max(0, min(y, H0 - 1))
        w, h = max(1, min(w, W0 - x)), max(1, min(h, H0 - y))
        bgr = bgr[y:y + h, x:x + w]
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    H, W = rgb.shape[:2]
    sal = saliency(rgb)
    s01 = (sal - sal.min()) / (np.ptp(sal) + 1e-9)
    big = np.clip(cv2.resize(s01, (W, H), interpolation=cv2.INTER_CUBIC), 0, 1)

    heat = cv2.applyColorMap((big * 255).astype(np.uint8), cv2.COLORMAP_TURBO)
    over = cv2.addWeighted(bgr, 0.55, heat, 0.45, 0)
    out_png = src.with_name(f"heat_{src.stem}.png")
    cv2.imwrite(str(out_png), over)

    if axis == "cols":
        prof = big.sum(axis=0)
        span = W
    else:
        prof = big.sum(axis=1)
        span = H
    prof = prof / (prof.sum() + 1e-9)
    idx = np.arange(span)
    centroid = float((prof * idx).sum() / span)
    bands = 8
    edges = np.linspace(0, span, bands + 1).astype(int)
    band_share = [float(prof[edges[i]:edges[i + 1]].sum()) for i in range(bands)]
    peak = int(np.argmax(prof))
    top_fold = float(prof[:span // 4].sum())
    return {
        "image": str(src), "size": [W, H], "axis": axis,
        "overlay": str(out_png),
        "peak_pct": round(100 * peak / span, 1),
        "centroid_pct": round(100 * centroid, 1),
        "top_fold_share": round(top_fold, 3),
        "bands": [round(b, 3) for b in band_share],
    }


def main():
    ap = argparse.ArgumentParser(description="Unsupervised salience heatmap (shown, not gated).")
    ap.add_argument("image")
    ap.add_argument("--axis", choices=["rows", "cols"], default="rows")
    ap.add_argument("--crop", help="x,y,w,h")
    ap.add_argument("--json", dest="out_json")
    a = ap.parse_args()
    crop = tuple(int(v) for v in a.crop.split(",")) if a.crop else None
    r = measure(a.image, a.axis, crop)
    print(f"\n  salience — {r['image']}  ({r['size'][0]}×{r['size'][1]}, axis={r['axis']})")
    lab = "left→right" if a.axis == "cols" else "top→bottom"
    print(f"  bands ({lab}):")
    for i, b in enumerate(r["bands"]):
        print(f"    {i*12:>3}-{(i+1)*12:>3}%  {b*100:5.1f}%  {'█'*int(round(b*60))}")
    print(f"  peak at {r['peak_pct']}%   centroid {r['centroid_pct']}%   "
          f"top-fold share {r['top_fold_share']*100:.0f}%")
    print(f"  overlay → {r['overlay']}\n")
    if a.out_json:
        Path(a.out_json).write_text(json.dumps(r, indent=2))


if __name__ == "__main__":
    main()
