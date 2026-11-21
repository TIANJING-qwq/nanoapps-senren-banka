#!/usr/bin/env python3
"""Pick the Senren Banka title background: sakura-pink dominance score."""
import struct
import sys
from pathlib import Path

from PIL import Image

root = Path(sys.argv[1])
cands = []
for p in sorted(root.iterdir()):
    b = p.read_bytes()
    if b[:8] != b"\x89PNG\r\n\x1a\n":
        continue
    w, h = struct.unpack_from(">II", b, 16)
    if (w, h) not in ((1280, 720), (1920, 1080)):
        continue
    img = Image.open(p).convert("RGB")
    img.thumbnail((320, 180))
    px = img.load()
    pink = bright = total = 0
    for y in range(img.height):
        for x in range(img.width):
            r, g, bl = px[x, y]
            total += 1
            lum = (r * 299 + g * 587 + bl * 114) // 1000
            if lum > 150:
                bright += 1
            if r > 150 and g < r - 20 and bl > g - 8 and bl < r:
                pink += 1          # sakura-ish: r dominant, bl close behind
    cands.append((pink / total, bright / total, f"{w}x{h}", p.name))

print("pink%  bright%  size      file")
for pk, br, sz, n in sorted(cands, reverse=True):
    print(f"{pk*100:5.1f}  {br*100:6.1f}  {sz}  {n}")
