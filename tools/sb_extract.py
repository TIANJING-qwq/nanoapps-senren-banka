#!/usr/bin/env python3
"""Extract all dialogue (in story order) from every carved scenario PSB.
Output: TSV  file<TAB>offset<TAB>text   + summary stats."""
import struct
import sys
from pathlib import Path

indir = Path(sys.argv[1])
out = Path(sys.argv[2])


def strings_of(data):
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
                o = int.from_bytes(
                    data[stroffs + skip + i * stride:
                         stroffs + skip + i * stride + stride], "little")
                if vals and o < vals[-1] or o > len(data) - strdata:
                    ok = False
                    break
                vals.append(o)
            if ok and vals and vals[0] == 0 and (
                    best is None or len(vals) > len(best[2])):
                best = (stride, skip, vals)
    if not best:
        return []
    stride, skip, vals = best
    out_l = []
    for o in vals:
        e = data.index(b"\x00", strdata + o)
        raw = data[strdata + o:e]
        try:
            s = raw.decode("utf-8")
        except UnicodeDecodeError:
            s = raw.decode("gbk", "replace")
        out_l.append(s)
    return out_l


def cjk(s):
    return any("\u4e00" <= c <= "\u9fff" for c in s)


total = 0
rows = []
files = sorted(indir.glob("*.psb"))
for f in files:
    data = f.read_bytes()
    strs = strings_of(data)
    if not strs:
        continue
    u = struct.unpack_from("<8I", data, 8)
    stroffs = u[2]
    ks = next((s for s in strs if s.endswith(".ks")), f.name)
    p = 0x28
    n = 0
    while p + 2 < stroffs:
        if data[p] == 0x0E:
            idx = data[p + 1] | (data[p + 2] << 8)
            if idx < len(strs):
                s = strs[idx]
                if len(s) >= 4 and cjk(s) and s[0] in "「『（“(":
                    rows.append((ks, p, s))
                    n += 1
        p += 1
    total += n
    print(f"{f.name}: {n} lines ({ks})")

with open(out, "w", encoding="utf-8") as fh:
    for ks, p, s in rows:
        fh.write(f"{ks}\t{p:#x}\t{s}\n")
print(f"\nTOTAL {total} lines -> {out}")
