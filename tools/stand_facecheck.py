#!/usr/bin/env python3
"""No-scipy face check: find the widest skin row band (the head), then
print an ASCII render of it plus how much dark (eye-like) detail sits
inside the skin span."""
import sys
from pathlib import Path

import numpy as np
from PIL import Image

SRC = Path(r"K:/千恋＊万花/outPath/fgimage1080.xp3")


def load(p):
    return np.asarray(Image.open(p).convert("RGB")).astype(np.int16)


def skin(a):
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    return ((r > 150) & (g > 110) & (b > 90) & (r > g + 12) &
            (g > b + 5) & (r - b > 25))


def head_band(a):
    sk = skin(a)
    H = a.shape[0]
    best = None
    for y in range(0, int(H * 0.45)):
        xs = np.where(sk[y])[0]
        if len(xs) < 80:
            continue
        span = xs.max() - xs.min()
        if span > len(xs) * 2.2:
            continue
        score = len(xs)
        if best is None or score > best[0]:
            best = (score, y, xs.min(), xs.max())
    if not best:
        return None
    _, y, x0, x1 = best
    return y, x0, x1


def render(a, box, cols=100):
    lum = a[box[1]:box[3], box[0]:box[2]].max(axis=2)
    h, w = lum.shape
    if h < 2 or w < 2:
        return "(empty)"
    rows = max(1, int(cols * h / w / 2.1))
    im = Image.fromarray(lum.astype(np.uint8)).resize((cols, rows))
    px = np.asarray(im)
    ramp = "#@%+=-:. "
    return "\n".join("".join(ramp[min(9, int(v) * 10 // 256)] for v in row)
                     for row in px)


if __name__ == "__main__":
    char = sys.argv[1] if len(sys.argv) > 1 else "芳乃"
    which = sys.argv[2] if len(sys.argv) > 2 else None
    files = sorted(SRC.glob(f"{char}a_0_*.tlg.png"))
    for p in files:
        if which and which not in p.name:
            continue
        with Image.open(p) as im:
            if im.width < 500:
                continue
        a = load(p)
        hb = head_band(a)
        if not hb:
            print(f"{p.name}: no head band")
            continue
        y, x0, x1 = hb
        band = a[max(0, y - 60):y + 130, max(0, x0 - 20):x1 + 20]
        lum = band.max(axis=2)
        sk = skin(band)
        dark_inside = ((lum < 90) & sk).sum()
        print(f"\n===== {p.name} head band y={y} x={x0}..{x1} "
              f"dark-inside-skin={dark_inside} =====")
        print(render(a, (max(0, x0 - 30), max(0, y - 70), x1 + 30, y + 140)))
