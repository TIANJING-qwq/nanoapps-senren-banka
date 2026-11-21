#!/usr/bin/env python3
"""Dump the refs that FOLLOW dialogue refs in the instruction stream:
what are they pointing at (voice hash names?)."""
import struct
import sys
from pathlib import Path

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


data = Path(sys.argv[1]).read_bytes()
strs = strings_of(data)
print(f"{len(strs)} strings")
# scan 0x0E refs; when a dialogue ref ('「') is found, report the next 1-2 refs
p = 0x28
shown = 0
while p + 2 < len(data) and shown < 18:
    if data[p] == 0x0E:
        idx = data[p + 1] | (data[p + 2] << 8)
        s = strs[idx] if idx < len(strs) else "??"
        if s.startswith("「"):
            follow = []
            q = p + 3
            for k in (0, 1):
                if q + 2 < len(data) and data[q] == 0x0E:
                    v = data[q + 1] | (data[q + 2] << 8)
                    follow.append(strs[v] if v < len(strs) else f"?{v}")
                    q += 3
                else:
                    follow.append(f"[{data[q]:#04x}]")
            print(f"@{p:#06x} {s[:20]!r} + {follow}")
            shown += 1
    p += 1
