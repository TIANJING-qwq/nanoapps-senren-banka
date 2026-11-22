#!/usr/bin/env python3
"""FFT-based exhaustive alignment: for every (small part x large layer) pair,
compute the skin-alignment score surface via cross-correlation and report
the best placements. Vectorised, so the full 70x15 sweep is cheap."""
import sys
from pathlib import Path

import numpy as np
from PIL import Image

SRC = Path(r"K:/千恋＊万花/outPath/fgimage1080.xp3")


def load(p):
    return np.asarray(Image.open(p).convert("RGB")).astype(np.uint8)


def masks(a):
    r = a[..., 0].astype(np.int16)
    g = a[..., 1].astype(np.int16)
    b = a[..., 2].astype(np.int16)
    skin = ((r > 150) & (g > 110) & (b > 90) & (r > g + 12) &
            (g > b + 5) & (r - b > 25))
    anym = a.max(axis=2) > 18
    return skin, anym


def xcorr(big, ker):
    """correlation of `big` with boolean kernel `ker`, valid region,
    same-mode normalised later; returns array indexed [dy, dx]"""
    H, W = big.shape
    h, w = ker.shape
    fh, fw = 1 << (H - 1).bit_length(), 1 << (W - 1).bit_length()
    A = np.fft.rfft2(big.astype(np.float32), (fh, fw))
    K = np.fft.rfft2(ker[::-1, ::-1].astype(np.float32), (fh, fw))
    C = np.fft.irfft2(A * K, (fh, fw))
    # position (dy,dx) with kernel fully inside
    out = np.full((H - h + 1, W - w + 1), -1e9, np.float32)
    valid = C[h - 1:h - 1 + out.shape[0], w - 1:w - 1 + out.shape[1]]
    out[:] = valid
    return out


def main():
    char = sys.argv[1] if len(sys.argv) > 1 else "芳乃"
    files = sorted(SRC.glob(f"{char}a_0_*.tlg.png"))
    bigs, smalls = [], []
    for p in files:
        with Image.open(p) as im:
            (bigs if im.width >= 500 else smalls).append(p)
    print(f"{len(bigs)} large, {len(smalls)} small")

    # precompute part content masks (trimmed to content bbox)
    parts = []
    for q in smalls:
        a = load(q)
        m = a.max(axis=2) > 30
        ys, xs = np.where(m)
        if len(ys) < 100:
            continue
        parts.append((q.name, m[ys.min():ys.max() + 1, xs.min():xs.max() + 1],
                      (int(xs.max() - xs.min() + 1), int(ys.max() - ys.min() + 1))))
    print(f"{len(parts)} parts with content")

    results = []
    for bp in bigs:
        a = load(bp)
        skin, anym = masks(a)
        inv = (~anym).astype(np.float32)
        for name, pm, sz in parts:
            h, w = pm.shape
            if h > a.shape[0] or w > a.shape[1]:
                continue
            n = float(pm.sum())
            cs = xcorr(skin, pm)
            ca = xcorr(anym, pm)
            ci = xcorr(inv, pm)
            score = cs / n - 0.6 * ci / n
            # require >= 85% of the part on the body
            score[ca / n < 0.85] = -1e9
            dy, dx = np.unravel_index(np.argmax(score), score.shape)
            sc = float(score[dy, dx])
            if sc > 0.30:
                results.append((sc, bp.name, name, int(dx), int(dy), sz))
    results.sort(reverse=True)
    print(f"\ntop placements (score, layer, part, dx, dy, size):")
    for r in results[:40]:
        print(f"  {r[0]:5.2f} {r[1][:16]:16s} {r[2][:26]:26s} "
              f"at=({r[3]:4d},{r[4]:4d}) {r[5][0]}x{r[5][1]}")
    print(f"\ntotal above threshold: {len(results)}")


if __name__ == "__main__":
    main()
