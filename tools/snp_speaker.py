#!/usr/bin/env python3
"""Find speaker-name refs preceding dialogue refs.
Anchor: known character-name strings; measure relative offset histogram."""
import struct
import sys
from collections import Counter
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

kata = lambda s: all("\u30a0" <= c <= "\u30ff" for c in s)
cjk = lambda s: any("\u4e00" <= c <= "\u9fff" for c in s)
# name candidates: short, no quotes, not .ks, not labels/commands
names = {i for i, s in enumerate(strs)
         if 1 <= len(s) <= 6 and (kata(s) or (cjk(s) and "、" not in s))
         and not any(x in s for x in "「」『』（）.ks*#_0123456789")}
print(f"{len(names)} name candidates: "
      f"{' '.join(sorted(strs[i] for i in list(names)[:24]))}")

# dialogue refs
dref = []
p = 0x28
while p + 2 < stroffs:
    if data[p] == 0x0E:
        idx = data[p + 1] | (data[p + 2] << 8)
        if idx < len(strs) and strs[idx].startswith("「"):
            dref.append((p, idx))
    p += 1
print(f"{len(dref)} dialogue refs")

# histogram of 0e-prefixed name-refs within -12..-1 before a 0e dialogue ref
hist = Counter()
samples = []
refs = []
p = 0x28
while p + 2 < stroffs:
    if data[p] == 0x0E:
        idx = data[p + 1] | (data[p + 2] << 8)
        if idx < len(strs) and strs[idx].startswith("「"):
            refs.append((p, idx))
    p += 1
for p, idx in refs:
    found = None
    for q in range(max(0, p - 12), p - 2):
        if data[q] == 0x0E and q + 2 < len(data):
            v = data[q + 1] | (data[q + 2] << 8)
            if v in names:
                found = (p - q, v)
                break
    if found:
        hist[found[0]] += 1
        if len(samples) < 14:
            samples.append((p, idx, found))
print(f"{len(refs)} dialogue refs; name-ref hits:")
for off, c in sorted(hist.items()):
    print(f"  -{off:2}: {'#' * min(60, c)} {c}")
for p, idx, (off, v) in samples:
    print(f"@{p:#08x} name@-{off}={strs[v]!r} -> {strs[idx][:28]!r}")
