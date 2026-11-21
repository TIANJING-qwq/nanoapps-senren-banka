#!/usr/bin/env python3
"""Locate dialogue references inside the PSB v2 tree byte stream.

For each CJK string index, try candidate encodings and report which one
yields near-complete, ordered coverage. Then dump the tree context around
each hit so the SAY instruction shape (speaker/voice refs) becomes visible.
"""
import struct
import sys
from pathlib import Path

data = Path(sys.argv[1]).read_bytes()
ver = struct.unpack_from("<H", data, 4)[0]
u = struct.unpack_from("<8I", data, 8)
stroffs, strdata = u[2], u[3]
tree_lo, tree_hi = (0x28, stroffs) if ver == 2 else (0x2C, stroffs)

# ---- decode string table (universal stride) -------------------------------
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
                                    stroffs + skip + i * stride + stride],
                               "little")
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
cjk_idx = [i for i, s in enumerate(strs)
           if any("\u4e00" <= c <= "\u9fff" for c in s) and len(s) >= 4]
print(f"{len(strs)} strings, {len(cjk_idx)} dialogue-ish")

tree = data[tree_lo:tree_hi]

# ---- candidate encodings ---------------------------------------------------
def enc_u16(i): return struct.pack("<H", i)
def enc_u24(i): return struct.pack("<I", i)[:3]
def enc_u32(i): return struct.pack("<I", i)
def enc_v2(i):  # M2 varint: high nibble 2 => 2-byte int
    return bytes([0x12, i]) if i < 256 else b""
def enc_v3(i):  # 0x33 + single byte index
    return bytes([0x33, i]) if i < 256 else b""

cands = {"u16": enc_u16, "u24": enc_u24, "u32": enc_u32,
         "0x12+u8": enc_v2, "0x33+u8": enc_v3}

for name, fn in cands.items():
    hit = miss = 0
    for i in cjk_idx[:400]:
        pat = fn(i)
        if not pat:
            continue
        if pat in tree:
            hit += 1
        else:
            miss += 1
    print(f"{name:8}: {hit} hit / {miss} miss of {hit + miss}")

# ---- context dump for the winner (u16 assumed default) ---------------------
print("\n--- ordered reference dump (u16) ---")
refs = []
for i in cjk_idx:
    pat = struct.pack("<H", i)
    p = 0
    while True:
        p = tree.find(pat, p)
        if p < 0:
            break
        refs.append((p, i))
        p += 2
refs.sort()
print(f"{len(refs)} refs; first 15 with tree context:")
for p, i in refs[:15]:
    ctx = tree[max(0, p - 6):p + len(strs[i].encode("utf-8")) // 8 + 2]
    print(f"@{tree_lo + p:#08x} [{i:5}] pre={tree[max(0, p - 6):p].hex(' ')} "
          f"{strs[i][:44]!r}")
