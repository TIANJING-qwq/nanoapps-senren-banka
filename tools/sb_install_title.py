#!/usr/bin/env python3
"""Install the real Senren Banka title art into the demo galpack.

Crops/letterboxes the 1280x720 title CG to the 432x240 landscape logical
screen and writes ui/title.bin (VNBI fmt0 RGB565).
"""
import struct
import sys
from pathlib import Path

from PIL import Image

src = Path(sys.argv[1])
pack = Path(sys.argv[2])                       # galpack dir (ui/ inside)

W, H = 432, 240
img = Image.open(src).convert("RGB")
# 1280x720 is 16:9, screen is 432x240 = 9:5 -> slight horizontal crop
scale = H / img.height
new_w = int(img.width * scale)
img = img.resize((new_w, H), Image.LANCZOS)
x0 = (new_w - W) // 2
img = img.crop((x0, 0, x0 + W, H))

px = img.load()
buf = bytearray(struct.pack("<4sHHB", b"VNBI", W, H, 0))
for y in range(H):
    for x in range(W):
        r, g, b = px[x, y]
        buf += struct.pack("<H", ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3))

out = pack / "ui" / "title.bin"
out.parent.mkdir(parents=True, exist_ok=True)
out.write_bytes(buf)
print(f"wrote {out} ({len(buf):,} B) from {src.name}")
