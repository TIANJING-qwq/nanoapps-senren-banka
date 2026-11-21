#!/usr/bin/env python3
"""TLG5 structure probe: find where the stripe-length table ends such that
the sum of entries + data start == file size."""
import struct
import sys
from pathlib import Path

p = Path(sys.argv[1])
d = p.read_bytes()
magic = d[:10]
assert magic == b"TLG5.0\x00raw", magic
unk = struct.unpack_from("<H", d, 10)[0]
w, h = struct.unpack_from("<II", d, 12)
mark = struct.unpack_from("<I", d, 20)[0]
print(f"unk16={unk} w={w} h={h} mark={mark} file={len(d):,}")

pos = 24
total = 0
n = 0
entries = []
while pos + 4 <= len(d):
    v = struct.unpack_from("<I", d, pos)[0]
    if total + v > len(d) - 24 - 4 or v == 0:
        break
    entries.append(v)
    total += v
    pos += 4
    n += 1
print(f"table parse: {n} entries, sum={total:,}, table_end={24 + 4 * n}, "
      f"data would end at {24 + 4 * n + total} vs file {len(d)}")
print(f"entries[:16]: {entries[:16]}")
if 24 + 4 * n + total == len(d):
    print("*** EXACT MATCH: entries are stripe compressed lengths ***")
    print(f"stripes={n}, w={w} -> stripes_expected(1col)={w}, (4col)={w // 4}")
