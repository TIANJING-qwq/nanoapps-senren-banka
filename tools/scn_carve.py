#!/usr/bin/env python3
"""Extract all zlib streams from scenario.pck; keep those that are PSB."""
import re
import struct
import sys
import zlib
from pathlib import Path

src = Path(sys.argv[1])
outdir = Path(sys.argv[2])
outdir.mkdir(parents=True, exist_ok=True)
data = src.read_bytes()
print(f"{src.name}: {len(data):,} B")

kept = 0
sizes = []
for m in re.finditer(b"\x78[\x01\x5e\x9c\xda]", data):
    o = m.start()
    try:
        d = zlib.decompressobj()
        out = d.decompress(data[o:])
    except Exception:
        continue
    if len(out) < 64:
        continue
    if out[:4] != b"PSB\x00":
        continue
    (outdir / f"scn_{o:08x}.psb").write_bytes(out)
    kept += 1
    sizes.append((len(out), o))

sizes.sort(reverse=True)
print(f"kept {kept} PSB streams; top sizes:")
for n, o in sizes[:12]:
    print(f"  {n:>9,} B @ {o:#x}")
