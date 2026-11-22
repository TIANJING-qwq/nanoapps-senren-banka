#!/usr/bin/env python3
"""Numeric sanity check for a decoded/composited image vs a known-good CG.

Compares: mean RGB, distinct-colour count (5-bit quantised), standard
deviation per channel, and the fraction of "flat" pixels. A correctly
decoded anime CG has thousands of distinct colours; a broken one has a
handful (line art on black) or is monochrome.
"""
import sys
from collections import Counter
from pathlib import Path

from PIL import Image


def stats(path, label):
    im = Image.open(path).convert("RGB")
    im.thumbnail((480, 480))
    w, h = im.size
    px = im.load()
    buckets = Counter()
    sums = [0, 0, 0]
    n = 0
    for y in range(0, h, 2):
        for x in range(0, w, 2):
            r, g, b = px[x, y]
            sums[0] += r
            sums[1] += g
            sums[2] += b
            buckets[(r >> 3, g >> 3, b >> 3)] += 1
            n += 1
    mean = tuple(s // n for s in sums)
    var = [0, 0, 0]
    for y in range(0, h, 2):
        for x in range(0, w, 2):
            r, g, b = px[x, y]
            var[0] += (r - mean[0]) ** 2
            var[1] += (g - mean[1]) ** 2
            var[2] += (b - mean[2]) ** 2
    std = tuple(int((v / n) ** 0.5) for v in var)
    top = buckets.most_common(1)[0][1] / n
    print(f"{label:22s} mean={mean} std={std} distinct={len(buckets):5d} "
          f"dominant={top*100:5.1f}%")
    return len(buckets), std


if __name__ == "__main__":
    for p in sys.argv[1:]:
        stats(Path(p), Path(p).name)
