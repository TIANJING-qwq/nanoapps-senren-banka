#!/usr/bin/env python3
"""Inventory decrypted Senren Banka assets: sizes, dims, adler, name guess."""
import struct
import sys
import zlib
from pathlib import Path

from PIL import Image

root = Path(sys.argv[1])
rows = []
for p in sorted(root.iterdir()):
    b = p.read_bytes()
    if b[:8] != b"\x89PNG\r\n\x1a\n":
        continue
    w, h = struct.unpack_from(">II", b, 16)
    rows.append((p.name, w, h, len(b)))

sizes = {}
for n, w, h, sz in rows:
    sizes.setdefault((w, h), []).append(n)
print(f"{len(rows)} PNGs, {len(sizes)} distinct dimensions:")
for (w, h), names in sorted(sizes.items(), key=lambda kv: -len(kv[1])):
    print(f"  {w}x{h}: {len(names)}")
    if len(names) <= 12:
        for n in names:
            print(f"      {n}")

# heuristics for the title screen: full 1280x720 + right side menu area
# (Yuzusoft titles put buttons on the right) -> low edge density there
if (1280, 720) in sizes:
    print("\ntitle candidates (right-middle emptiness score, lower = emptier):")
    cand = []
    for n in sizes[(1280, 720)]:
        try:
            img = Image.open(root / n).convert("L")
        except Exception:
            continue
        px = img.load()
        score = 0
        cnt = 0
        for y in range(200, 560, 8):
            for x in range(880, 1240, 8):
                score += px[x, y]
                cnt += 1
        cand.append((score / cnt, n))
    for s, n in sorted(cand)[:10]:
        print(f"  {s:7.1f}  {n}")
