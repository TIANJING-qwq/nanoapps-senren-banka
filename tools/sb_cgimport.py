#!/usr/bin/env python3
"""Build the CG gallery: EV CGs (1480x853) from decrypted PNGs ->
cg/cgNN.bin (432x240 fmt0) + cgt/cgNN.bin (84x48 fmt0 thumbs) + cg.idx."""
import struct
import sys
from pathlib import Path

from PIL import Image

SRC = Path("NanoApps/build/sb_bg")
PACK = Path(sys.argv[1])


def to_vnbi_fmt0(img, W, H):
    im = img.convert("RGB")
    sc = min(W / im.width, H / im.height)
    im = im.resize((max(1, round(im.width * sc)),
                    max(1, round(im.height * sc))), Image.LANCZOS)
    x = (im.width - W) // 2
    y = (im.height - H) // 2
    im = im.crop((x, y, x + W, y + H))
    px = im.load()
    out = bytearray(b"VNBI" + struct.pack("<HHB", W, H, 0))
    for yy in range(H):
        for xx in range(W):
            r, g, b = px[xx, yy]
            out += struct.pack("<H", (r >> 3) << 11 | (g >> 2) << 5 | (b >> 3))
    return bytes(out)


files = [p for p in sorted(SRC.glob("*"))
         if p.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"]
cgs = []
for p in files:
    with Image.open(p) as im:
        if im.size == (1480, 853):
            cgs.append(p)
cgs.sort(key=lambda p: p.name)
print(f"{len(cgs)} EV CGs found")

( PACK / "cg").mkdir(parents=True, exist_ok=True)
(PACK / "cgt").mkdir(parents=True, exist_ok=True)
idx = bytearray(b"VNCG" + b"\x00\x00" + struct.pack("<H", len(cgs)))
for i, p in enumerate(cgs):
    with Image.open(p) as im:
        (PACK / f"cg/cg{i:02d}.bin").write_bytes(to_vnbi_fmt0(im, 432, 240))
        (PACK / f"cgt/cg{i:02d}.bin").write_bytes(to_vnbi_fmt0(im, 84, 48))
    nm = f"cg{i:02d}".encode()
    idx += struct.pack("<H", len(nm)) + nm
(PACK / "cg.idx").write_bytes(bytes(idx))
print(f"cg.idx: {len(cgs)} entries; full {len(cgs)} + thumbs written")
