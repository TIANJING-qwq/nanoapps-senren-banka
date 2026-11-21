#!/usr/bin/env python3
"""Context around dialogue 0e-refs: raw hex + all 0e<u16> refs nearby."""
import struct
import sys
from pathlib import Path

data = Path(sys.argv[1]).read_bytes()
u = struct.unpack_from("<8I", data, 8)
stroffs, strdata = u[2], u[3]
n = strdata - stroffs
best = None
for stride in (2, 3, 4):
    for skip in range(0, 12):
        cnt = (n - skip) // stride
        if cnt < 8:
            continue
        vals, ok = [], True
        for i in range(cnt):
            o = int.from_bytes(data[stroffs + skip + i * stride:
                                    stroffs + skip + i * stride + stride], "little")
            if vals and o < vals[-1] or o > len(data) - strdata:
                ok = False
                break
            vals.append(o)
        if ok and vals and vals[0] == 0 and (best is None or len(vals) > len(best[2])):
            best = (stride, skip, vals)
stride, skip, vals = best
strs = []
for o in vals:
    e = data.index(b"\x00", strdata + o)
    raw = data[strdata + o:e]
    try:
        s = raw.decode("utf-8")
    except UnicodeDecodeError:
        s = raw.decode("gbk", "replace")
    strs.append(s)
cjk = lambda s: any("\u4e00" <= c <= "\u9fff" for c in s)

# collect dialogue refs
refs = []
p = 0x28
while p + 2 < stroffs:
    if data[p] == 0x0E:
        idx = data[p + 1] | (data[p + 2] << 8)
        if idx < len(strs) and cjk(strs[idx]) and len(strs[idx]) >= 4:
            refs.append((p, idx))
    p += 1

show = int(sys.argv[2], 0) if len(sys.argv) > 2 else 8
for p, idx in refs[:show]:
    lo, hi = p - 20, p + 24
    hexs = " ".join(f"{b:02x}" for b in data[lo:hi])
    print(f"@{p:#08x}  {hexs}")
    ann = []
    q = lo
    while q < hi:
        if data[q] == 0x0E and q + 2 < len(data):
            j = data[q + 1] | (data[q + 2] << 8)
            if j < len(strs):
                mark = "*" if q == p else " "
                ann.append(f"{mark}@{q - p:+d} [{j}] {strs[j][:28]!r}")
        q += 1
    for a in ann:
        print(f"    {a}")
    print()
