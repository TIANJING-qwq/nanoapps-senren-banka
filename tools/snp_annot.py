#!/usr/bin/env python3
"""Annotated dump of the PSB v2 tree stream: u16 references resolved to
their string-table entries, raw bytes shown for opcode context."""
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

start = int(sys.argv[2], 0) if len(sys.argv) > 2 else 0x28
count = int(sys.argv[3], 0) if len(sys.argv) > 3 else 160
p = start
end = min(start + count * 2, stroffs)


def tag(idx):
    s = strs[idx]
    if any("\u4e00" <= c <= "\u9fff" for c in s):
        return "SAY?" if len(s) >= 4 else "NAME?"
    if len(s) == 32 and all(c in "0123456789abcdef" for c in s):
        return "VOICE(hash)"
    if ".stand" in s or s.startswith("cg_"):
        return "SPR"
    if s.startswith("bgm"):
        return "BGM"
    if s.startswith("*"):
        return "LABEL"
    if s.endswith(".ks"):
        return "FILE"
    return "cmd"


while p + 1 < end:
    v = data[p] | (data[p + 1] << 8)
    if v < len(strs):
        t = tag(v)
        show = strs[v][:36].replace("\n", "\\n")
        print(f"{p:#08x} {v:5} {t:11} {show!r}")
    else:
        print(f"{p:#08x} {v:5} --")
    p += 2
