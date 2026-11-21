#!/usr/bin/env python3
"""Carve complete PNG streams (and count PSB/zlib) out of an EVB pck."""
import struct
import sys
import zlib

path = sys.argv[1]
outdir = sys.argv[2] if len(sys.argv) > 2 else None
data = open(path, "rb").read()
n = len(data)
print(f"{path}: {n:,} B")

PNG_SIG = b"\x89PNG\r\n\x1a\n"
i = 0
pngs = []
while True:
    i = data.find(PNG_SIG, i)
    if i < 0:
        break
    # walk chunks to IEND
    p = i + 8
    ok = False
    while p + 12 <= n:
        ln = struct.unpack_from(">I", data, p)[0]
        typ = data[p + 4:p + 8]
        if ln > 0x7FFFFFF or p + 12 + ln > n:
            break
        p += 12 + ln
        if typ == b"IEND":
            ok = True
            break
    if ok:
        w, h = struct.unpack_from(">II", data, i + 16)
        pngs.append((i, p - i, w, h))
        i = p
    else:
        i += 1

print(f"complete PNGs: {len(pngs)}")
from collections import Counter
dims = Counter((w, h) for _, _, w, h in pngs)
for (w, h), c in dims.most_common(20):
    print(f"  {w}x{h}: {c}")

if outdir:
    from pathlib import Path
    out = Path(outdir)
    out.mkdir(parents=True, exist_ok=True)
    for k, (off, size, w, h) in enumerate(pngs):
        (out / f"carve_{k:04d}_{w}x{h}.png").write_bytes(data[off:off + size])
    print(f"carved -> {out}")

# also count zlib + PSB for later
import re
psb = sum(1 for m in re.finditer(b"PSB\x00\x02", data))
print(f"PSB v2 magic occurrences: {psb}")
