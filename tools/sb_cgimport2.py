#!/usr/bin/env python3
"""Import the real event CGs (evimage720 pngs) into the pack:
cg/cgNN.bin (432x240 RGB565) + cgt/cgNN.bin (84x48) + cg.idx.
Engine cap: CG_MAX=512.

Usage: sb_cgimport2.py <evimage720 dir> <pack dir>
"""
import struct
import sys
from pathlib import Path

from PIL import Image

CAP = 512


def to_vnbi(img: Image.Image, W: int, H: int) -> bytes:
    im = img.convert("RGB")
    sc = max(W / im.width, H / im.height)
    im = im.resize((max(W, round(im.width * sc)), max(H, round(im.height * sc))),
                   Image.LANCZOS)
    x, y = (im.width - W) // 2, (im.height - H) // 2
    im = im.crop((x, y, x + W, y + H))
    px = im.load()
    buf = bytearray(W * H * 2)
    i = 0
    for yy in range(H):
        for xx in range(W):
            r, g, b = px[xx, yy]
            v = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
            buf[i] = v & 0xFF
            buf[i + 1] = v >> 8
            i += 2
    return bytes(bytearray(b"VNBI") + struct.pack("<HHB", W, H, 0)) + bytes(buf)


src = Path(sys.argv[1])
pack = Path(sys.argv[2])
pngs = sorted(src.glob("*.png"))
# scene CGs first (sd*/ev*), then others; skip end_* credits art
scn = [p for p in pngs if p.stem.startswith(("sd", "ev", "cg"))]
rest = [p for p in pngs if p not in scn and not p.stem.startswith("end_")]
pick = (scn + rest)[:CAP]
(pack / "cg").mkdir(parents=True, exist_ok=True)
(pack / "cgt").mkdir(parents=True, exist_ok=True)
idx = bytearray(b"VNCG" + b"\x00\x00" + struct.pack("<H", len(pick)))
name_rows = []
for i, p in enumerate(pick):
    with Image.open(p) as im:
        (pack / f"cg/cg{i:02d}.bin").write_bytes(to_vnbi(im, 432, 240))
        (pack / f"cgt/cg{i:02d}.bin").write_bytes(to_vnbi(im, 84, 48))
    nm = f"cg{i:02d}".encode()
    idx += struct.pack("<H", len(nm)) + nm
    name_rows.append(f"{p.stem}\tcg{i:02d}")
(pack / "cg.idx").write_bytes(bytes(idx))
(pack / "cg_names.tsv").write_text("\n".join(name_rows), encoding="utf-8")
tot = sum((pack / f"cg/cg{i:02d}.bin").stat().st_size for i in range(len(pick)))
print(f"{len(pick)} CGs -> {pack} (cg {tot // 1048576} MB)")
