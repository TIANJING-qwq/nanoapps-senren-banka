#!/usr/bin/env python3
"""Count how many dialogue 0x0E refs are followed by a hash-string ref
(32-hex = voice file name) across ALL story volumes."""
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
    out = []
    for o in vals:
        e = data.index(b"\x00", strdata + o)
        try:
            out.append(data[strdata + o:e].decode("utf-8"))
        except UnicodeDecodeError:
            out.append(data[strdata + o:e].decode("gbk", "replace"))
    return out


tot_d = tot_v = 0
hashes = []
for f in sorted(Path(sys.argv[1]).glob("scn_*.psb")):
    data = f.read_bytes()
    strs = strings_of(data)
    p = 0x28
    while p + 2 < len(data):
        if data[p] == 0x0E:
            idx = data[p + 1] | (data[p + 2] << 8)
            s = strs[idx] if idx < len(strs) else ""
            if s.startswith("「"):
                tot_d += 1
                q = p + 3
                if q + 2 < len(data) and data[q] == 0x0E:
                    v = data[q + 1] | (data[q + 2] << 8)
                    t = strs[v] if v < len(strs) else ""
                    if len(t) == 32 and all(c in "0123456789abcdef"
                                            for c in t):
                        tot_v += 1
                        hashes.append(t)
        p += 1
print(f"dialogue refs: {tot_d}; with voice-hash ref: {tot_v} "
      f"({tot_v * 100 // max(1, tot_d)}%)")
uniq = sorted(set(hashes))
Path("NanoApps/build/voice_hashes.txt").write_text("\n".join(uniq))
print(f"unique voice hashes: {len(uniq)} -> build/voice_hashes.txt")
