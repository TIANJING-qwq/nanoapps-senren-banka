#!/usr/bin/env python3
"""Import the real game backgrounds (bgimage720 pngs, one per scene name)
into a pack: bg/bbNN.bin (VNBI, 432x240 RGB565) + bg_names.tsv mapping
the original Japanese scene name -> bbNN.

Usage: sb_bgimport2.py <bgimage720 dir> <pack dir>
"""
import struct
import sys
from pathlib import Path

from PIL import Image

W, H = 432, 240


def pack_bg(path: Path) -> bytes:
    img = Image.open(path).convert("RGB")
    # cover-fit to 432x240
    s = max(W / img.width, H / img.height)
    nw, nh = max(W, int(img.width * s + 0.5)), max(H, int(img.height * s + 0.5))
    img = img.resize((nw, nh), Image.LANCZOS)
    x0, y0 = (nw - W) // 2, (nh - H) // 2
    img = img.crop((x0, y0, x0 + W, y0 + H))
    px = img.load()
    out = bytearray(b"VNBI") + struct.pack("<HHB", W, H, 0)
    buf = bytearray(W * H * 2)
    i = 0
    for y in range(H):
        for x in range(W):
            r, g, b = px[x, y]
            v = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
            buf[i] = v & 0xFF
            buf[i + 1] = v >> 8
            i += 2
    return bytes(out) + bytes(buf)


src = Path(sys.argv[1])
out = Path(sys.argv[2]) / "bg"
out.mkdir(parents=True, exist_ok=True)
pngs = sorted(src.glob("*.png"))
rows = []
for i, p in enumerate(pngs):
    name = f"bb{i:02d}"
    (out / (name + ".bin")).write_bytes(pack_bg(p))
    rows.append(f"{p.stem}\t{name}")
Path(sys.argv[2] + "/bg_names.tsv").write_text("\n".join(rows), encoding="utf-8")
print(f"{len(pngs)} backgrounds -> {out} "
      f"({sum((out / (r.split(chr(9))[1] + '.bin')).stat().st_size for r in rows) // 1024} KB)")
