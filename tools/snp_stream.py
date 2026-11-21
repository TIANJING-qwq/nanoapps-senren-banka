#!/usr/bin/env python3
"""Streaming snp interpreter: 0x0E = 'push u16 string-ref'.
Decode the whole tree as an opcode stream and classify each ref."""
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

# scan the tree for 0e<u16> sequences: stats of what follows a run
lo, hi = 0x28, stroffs
hits = []
p = lo
while p + 2 < hi:
    if data[p] == 0x0E:
        idx = data[p + 1] | (data[p + 2] << 8)
        if idx < len(strs):
            hits.append((p, idx))
    p += 1
cjk = [i for i, s in enumerate(strs)
       if any("\u4e00" <= c <= "\u9fff" for c in s) and len(s) >= 4]
cjk_set = set(cjk)
covered = sum(1 for _, i in hits if i in cjk_set)
print(f"0e<u16> refs: {len(hits)}, CJK-dialogue refs among them: {covered} "
      f"of {len(cjk)} dialogue strings ({covered * 100 // max(1, len(cjk))}%)")

# consecutive-run analysis: how many hits form back-to-back 0e<u16> pairs
runs = 0
for k in range(1, len(hits)):
    if hits[k][0] - hits[k - 1][0] == 3:
        runs += 1
print(f"back-to-back 0e pairs: {runs}")

for p, i in hits[:25]:
    print(f"@{p:#08x} [{i:5}] {strs[i][:52]!r}")
