#!/usr/bin/env python3
"""Empirically locate the face on a stand body layer, then brute-force the
placement of an eye part TLG: the correct (dx,dy) maximizes how much of the
part's content lands on skin-colored body pixels.

No format guessing involved - pure image alignment."""
import sys
from pathlib import Path

import numpy as np
from PIL import Image

SRC = Path(r"K:/千恋＊万花/outPath/fgimage1080.xp3")


def load(p):
    return np.asarray(Image.open(p).convert("RGB")).astype(np.int16)


def skin_mask(a):
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    return ((r > 150) & (g > 110) & (b > 90) & (r > g + 12) &
            (g > b + 5) & (r - b > 25))


def body_mask(a):
    """anything not near-black"""
    return a.max(axis=2) > 18


def face_region(a):
    """rows where skin forms a face-wide band in the upper 45%"""
    sk = skin_mask(a)
    face_rows = []
    for y in range(0, int(a.shape[0] * 0.45)):
        xs = np.where(sk[y])[0]
        if 60 <= len(xs) <= 340:          # face-width skin run
            span = xs.max() - xs.min()
            if span <= len(xs) * 2:       # dense, not scattered
                face_rows.append((y, xs.min(), xs.max(), len(xs)))
    return face_rows


def part_content(p):
    a = load(p)
    m = a.max(axis=2) > 30                 # non-dark content
    ys, xs = np.where(m)
    if not len(ys):
        return None, None, None
    return a, m, (xs.min(), ys.min(), xs.max(), ys.max())


def place_score(body_skin, body_any, part_m, dx, dy):
    """part content placed with top-left at (dx,dy): skin fraction score"""
    h, w = part_m.shape
    H, W = body_skin.shape
    if dx < 0 or dy < 0 or dx + w > W or dy + h > H:
        # allow partial overhang, but at least 60% of the part on-canvas
        x0, y0 = max(0, dx), max(0, dy)
        x1, y1 = min(W, dx + w), min(H, dy + h)
        if (x1 - x0) * (y1 - y0) < 0.6 * w * h:
            return -1.0
        pm = part_m[y0 - dy:y1 - dy, x0 - dx:x1 - dx]
        sk = body_skin[y0:y1, x0:x1]
        an = body_any[y0:y1, x0:x1]
    else:
        pm = part_m
        sk = body_skin[dy:dy + h, dx:dx + w]
        an = body_any[dy:dy + h, dx:dx + w]
    n = int(pm.sum())
    if n < 40:
        return -1.0
    on_skin = int((pm & sk).sum())
    off = n - int((pm & an).sum())
    return on_skin / n - 0.6 * off / n


def search(sk, an, pm, x_rng, y_rng):
    """coarse-to-fine: stride 8 -> 2 -> 1, return best (score, x, y)"""
    best = (-2.0, 0, 0)
    for stride in (8, 2, 1):
        cx, cy = best[1], best[2]
        x0 = max(x_rng[0], cx - (16 if stride < 8 else 0))
        x1 = min(x_rng[1], cx + (16 if stride < 8 else 0)) + 1
        y0 = max(y_rng[0], cy - (16 if stride < 8 else 0))
        y1 = min(y_rng[1], cy + (16 if stride < 8 else 0)) + 1
        for dy in range(y0, y1, stride):
            for dx in range(x0, x1, stride):
                sc = place_score(sk, an, pm, dx, dy)
                if sc > best[0]:
                    best = (sc, dx, dy)
    return best


def main():
    char = sys.argv[1] if len(sys.argv) > 1 else "芳乃"
    # 1) face region on each large layer
    large = sorted(SRC.glob(f"{char}a_0_*.tlg.png"))
    big = []
    for p in large:
        with Image.open(p) as im:
            if im.width >= 500:
                big.append(p)
    print(f"{len(big)} large layers")
    best = None
    for p in big:
        a = load(p)
        fr = face_region(a)
        if fr:
            ys = [r[0] for r in fr]
            band = (min(ys), max(ys))
            n = len(fr)
            print(f"  {p.name} {a.shape[1]}x{a.shape[0]} face-rows {band} "
                  f"n={n} sample={fr[len(fr)//2]}")
            if best is None or n > best[1]:
                best = (p, n, fr)
    if not best:
        print("no face region found on any layer")
        return
    p_body, _, fr = best
    print(f"\nbody = {p_body.name}")
    a = load(p_body)
    sk = skin_mask(a)
    an = body_mask(a)
    ys = [r[0] for r in fr]
    y_lo, y_hi = min(ys), max(ys)
    xs_all = [r[1] for r in fr] + [r[2] for r in fr]
    x_lo, x_hi = min(xs_all), max(xs_all)
    print(f"face zone x {x_lo}..{x_hi} y {y_lo}..{y_hi}")

    # 2) brute-force place every small part (<=500 wide) near the face
    small = [q for q in large if q not in big]
    print(f"\n{len(small)} small parts; alignment search:")
    xrng = (max(0, x_lo - 160), min(a.shape[1] - 8, x_hi + 160))
    yrng = (max(0, y_lo - 60), min(int(a.shape[0] * 0.55), y_hi + 60))
    print(f"search window x {xrng} y {yrng}")
    results = []
    for q in small[:200]:
        pa, pm, bb = part_content(q)
        if pm is None:
            continue
        # trim part to its content bbox so dx,dy == placement of content
        pm_t = pm[bb[1]:bb[3] + 1, bb[0]:bb[2] + 1]
        sc, dx, dy = search(sk, an, pm_t, xrng, yrng)
        if sc > 0.25:
            results.append((sc, q.name, (dx, dy),
                            (bb[2] - bb[0] + 1, bb[3] - bb[1] + 1)))
    results.sort(reverse=True)
    for sc, name, xy, sz in results[:26]:
        print(f"  {sc:5.2f} {name:28s} at=({xy[0]:4d},{xy[1]:4d}) {sz[0]}x{sz[1]}")


if __name__ == "__main__":
    main()
