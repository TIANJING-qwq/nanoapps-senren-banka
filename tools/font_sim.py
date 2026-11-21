#!/usr/bin/env python3
"""Simulate the ENGINE's font.bin parsing + draw_glyph byte-for-byte.
Renders a string to a PNG using exactly the C code's logic — if this is
garbled too, the file format contract is broken; if fine, the bug is in
C (types/order)."""
import struct
import sys
from pathlib import Path

from PIL import Image, ImageDraw

b = Path("NanoApps/build/sb_full/font.bin").read_bytes()
print(f"font.bin {len(b)} B, magic={b[:4]!r}")

w, h, bpp, rsvd = b[4], b[5], b[6], b[7]
n = struct.unpack_from("<H", b, 8)[0]
print(f"w={w} h={h} bpp={bpp} rsvd={rsvd} n={n}")

# engine: records are INLINE — u32 cp followed by the bitmap (h*bpr bytes)
bpr2 = (w + 7) >> 3
rec = 4 + h * bpr2
cps, offs = [], []
off = 10
for i in range(n):
    cp, = struct.unpack_from("<I", b, off)
    cps.append(cp)
    offs.append(off + 4)
    off += rec
print(f"first cp={cps[0]:#x} off={offs[0]}, last cp={cps[-1]:#x} "
      f"off={offs[-1]}, sorted={cps == sorted(cps)}, "
      f"consumed={off} <= {len(b)}")

bpr = (w + 7) >> 3

def glyph_png(cp):
    try:
        i = cps.index(cp)
    except ValueError:
        return None
    fo = offs[i]
    img = Image.new("1", (w, h), 0)
    dr = ImageDraw.Draw(img)
    for row in range(h):
        for bit in range(w):
            if b[fo + row * bpr + (bit >> 3)] & (0x80 >> (bit & 7)):
                dr.point((bit, row), 1)
    return img

text = "千恋万花"
canvas = Image.new("1", (w * len(text), h), 0)
dr = ImageDraw.Draw(canvas)
for k, ch in enumerate(text):
    g = glyph_png(ord(ch))
    if g is None:
        print(f"MISS {ch}")
        continue
    canvas.paste(g, (k * w, 0))
canvas.resize((w * len(text) * 4, h * 4)).save(
    "NanoApps/build/font_engine_sim.png")
print("wrote NanoApps/build/font_engine_sim.png")

# engine self-test reference: F:<size-hex> N:<n-hex> X:<xor-hex>
xor = 0
for k in range(0, len(b) - 3, 97):
    xor |= 0
    xor ^= int.from_bytes(b[k:k + 4], "little")
print(f"expect on device: F:{len(b):X} N:{n:X} X:{xor & 0xFFFFFFFF:08X}")
