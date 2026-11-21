#!/usr/bin/env python3
"""Universal PSB string-table decoder: v3=u16 table, v2=u24 table.
Auto-detects the table stride by scanning for a monotonic run."""
import struct
import sys
from pathlib import Path

data = Path(sys.argv[1]).read_bytes()
ver = struct.unpack_from("<H", data, 4)[0]
u = struct.unpack_from("<8I", data, 8)
stroffs, strdata = (u[2], u[3]) if ver == 2 else (u[2], u[3])
n = strdata - stroffs

best = None
for stride in (2, 3, 4):
    for skip in range(0, 12):
        cnt = (n - skip) // stride
        if cnt < 8:
            continue
        vals = []
        ok = True
        for i in range(cnt):
            o = int.from_bytes(data[stroffs + skip + i * stride:
                                    stroffs + skip + i * stride + stride],
                               "little")
            if vals and o < vals[-1]:
                ok = False
                break
            if o > len(data) - strdata:
                ok = False
                break
            vals.append(o)
        if ok and vals and vals[0] == 0:
            run = (stride, skip, vals)
            if best is None or len(vals) > len(best[2]):
                best = run
if best is None:
    print("no monotonic table found")
    sys.exit(1)
stride, skip, vals = best
print(f"ver={ver} table: u{stride * 8} stride, skip {skip}, {len(vals)} strings")

strs = []
for o in vals:
    e = data.index(b"\x00", strdata + o)
    raw = data[strdata + o:e]
    try:
        s = raw.decode("utf-8")
    except UnicodeDecodeError:
        s = raw.decode("gbk", "replace")
    strs.append(s)

cjk = sum(1 for s in strs if any("\u4e00" <= c <= "\u9fff" for c in s))
print(f"{cjk} CJK strings of {len(strs)}")
lo = int(sys.argv[2], 0) if len(sys.argv) > 2 else 0
cnt = int(sys.argv[3], 0) if len(sys.argv) > 3 else 40
for i in range(lo, min(lo + cnt, len(strs))):
    print(f"[{i:5}] {strs[i][:72]}")
